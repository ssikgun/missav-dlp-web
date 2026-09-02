from contextlib import contextmanager
from pathlib import Path
import fcntl
import inspect
import stat
import tempfile

from teddy_discovery_completion import (
    CompletionPlan,
)
from teddy_discovery_completion_orchestrator import (
    process_one,
)
from teddy_discovery_completion_runner import (
    CONFIRMATION,
    run_once,
)
from teddy_discovery_db import connect, initialize
from teddy_discovery_operation_lock import (
    OperationLockBusy,
    operation_lock,
)

import teddy_discovery_jav_reconcile as reconcile_mod


def require(value, message):
    if not value:
        raise RuntimeError(message)


class FakeStat:
    def __init__(self, mode, size=0, mtime_ns=0):
        self.st_mode = mode
        self.st_size = size
        self.st_mtime_ns = mtime_ns


class FakeEntry:
    def __init__(self, name, value):
        self.name = name
        self.value = value

    def is_symlink(self):
        return stat.S_ISLNK(self.value.st_mode)

    def is_dir(self, follow_symlinks=False):
        return stat.S_ISDIR(self.value.st_mode)

    def stat(self, follow_symlinks=False):
        return self.value


def directory(name):
    return FakeEntry(
        name,
        FakeStat(stat.S_IFDIR | 0o755),
    )


def file_entry(name, size, mtime_ns):
    return FakeEntry(
        name,
        FakeStat(
            stat.S_IFREG | 0o644,
            size,
            mtime_ns,
        ),
    )


def make_tree(items, nested=None):
    tree = {
        ".": [],
    }

    for dvd_id, size, mtime_ns in items:
        prefix, dvd_dir, filename = (
            reconcile_mod.canonical_destination(
                dvd_id,
                ".mp4",
            ).parts
        )
        tree.setdefault(".", []).append(
            directory(prefix)
        ) if not any(
            entry.name == prefix
            for entry in tree["."]
        ) else None
        tree.setdefault(prefix, []).append(
            directory(dvd_dir)
        )
        tree.setdefault(
            prefix + "/" + dvd_dir,
            [],
        ).append(
            file_entry(
                filename,
                size,
                mtime_ns,
            )
        )

    for parent, name in nested or ():
        tree.setdefault(parent, []).append(
            directory(name)
        )

    for entries in tree.values():
        entries.sort(key=lambda entry: entry.name)

    return tree


class SequenceFilesystem:
    def __init__(
        self,
        snapshots,
        *,
        error_scan=None,
        writer_lock_path=None,
        trace=None,
    ):
        self.snapshots = snapshots
        self.error_scan = error_scan
        self.writer_lock_path = writer_lock_path
        self.trace = trace if trace is not None else []
        self.scan_index = -1
        self.calls = []
        self.writer_states = []

    def _writer_available(self):
        if self.writer_lock_path is None:
            return True

        handle = Path(self.writer_lock_path).open(
            "a+",
            encoding="utf-8",
        )
        try:
            try:
                fcntl.flock(
                    handle.fileno(),
                    fcntl.LOCK_EX | fcntl.LOCK_NB,
                )
                return True
            except BlockingIOError:
                return False
        finally:
            try:
                fcntl.flock(
                    handle.fileno(),
                    fcntl.LOCK_UN,
                )
            finally:
                handle.close()

    def _before_call(self, relative_path):
        self.calls.append(relative_path)
        self.writer_states.append(
            self._writer_available()
        )

        if self.trace is not None:
            self.trace.append(
                "scan:%s:%d"
                % (relative_path, self.scan_index)
            )

        if self.error_scan == self.scan_index:
            raise OSError(
                "deterministic filesystem failure"
            )

    def lstat(self, relative_path):
        if relative_path == ".":
            self.scan_index += 1

        self._before_call(relative_path)
        return FakeStat(stat.S_IFDIR | 0o755)

    def listdir(self, relative_path):
        self._before_call(relative_path)
        snapshot = self.snapshots[
            min(
                self.scan_index,
                len(self.snapshots) - 1,
            )
        ]
        return list(snapshot.get(relative_path, ()))


def create_db(path):
    db = connect(path)
    initialize(db)
    db.close()


def scalar(path, sql, params=()):
    db = connect(path)
    try:
        return db.execute(sql, params).fetchone()[0]
    finally:
        db.close()


def seed_holding(path, dvd_id, size, mtime_ns, present=1):
    relative = reconcile_mod.canonical_destination(
        dvd_id,
        ".mp4",
    ).as_posix()
    db = connect(path)
    db.execute(
        """
        INSERT INTO holdings(
            storage_root, relative_path, dvd_id,
            parse_status, parse_method,
            parse_candidates_json, size_bytes, mtime_ns,
            discovered_by, present, first_seen_at,
            last_seen_at, last_seen_run_id
        ) VALUES (
            'jav', ?, ?, 'MATCHED', 'smoke', ?, ?, ?,
            'smoke', ?, 'now', 'now', NULL
        )
        """,
        (
            relative,
            dvd_id,
            "[\"" + dvd_id + "\"]",
            size,
            mtime_ns,
            present,
        ),
    )
    db.commit()
    db.close()


def categories(report):
    return {
        finding.category
        for finding in report.findings
    }


def apply_expect_unsafe(
    db_path,
    filesystem,
    operation_path,
    writer_path,
):
    try:
        reconcile_mod.apply_reconciliation(
            db_path,
            "/fake/JAV",
            filesystem=filesystem,
            operation_lock_path=operation_path,
            writer_lock_path=writer_path,
        )
    except reconcile_mod.ReconciliationUnsafe as exc:
        return exc.report

    raise RuntimeError(
        "unsafe reconciliation unexpectedly applied"
    )


def no_inventory_write(path, expected_runs):
    require(
        scalar(
            path,
            "SELECT COUNT(*) FROM inventory_runs",
        ) == expected_runs,
        "failed scan wrote an inventory run",
    )


def test_stable_scan_applies_second_snapshot():
    with tempfile.TemporaryDirectory(
        prefix="teddy-jav-safety-stable-"
    ) as temp:
        base = Path(temp)
        db_path = base / "discovery.sqlite3"
        operation_path = base / "operation.lock"
        writer_path = base / "writer.lock"
        create_db(db_path)
        snapshot = make_tree(
            (
                ("ABC-123", 3, 3000),
                ("XYZ-999", 4, 4000),
            )
        )
        filesystem = SequenceFilesystem(
            [snapshot, snapshot],
            writer_lock_path=writer_path,
        )

        result = reconcile_mod.apply_reconciliation(
            db_path,
            "/fake/JAV",
            filesystem=filesystem,
            operation_lock_path=operation_path,
            writer_lock_path=writer_path,
        )

        require(result["applied"] is True, "stable scan did not apply")
        require(
            scalar(
                db_path,
                "SELECT COUNT(*) FROM holdings",
            ) == 2,
            "stable scan imported the wrong holding count",
        )
        require(
            all(filesystem.writer_states),
            "DB writer lock was held during a bounded scan",
        )
        require(
            filesystem.scan_index == 1,
            "stable apply did not perform exactly two scans",
        )


def test_changed_scan_is_fail_closed():
    cases = (
        (
            "added",
            make_tree((("ABC-123", 3, 3000),)),
            make_tree(
                (
                    ("ABC-123", 3, 3000),
                    ("XYZ-999", 4, 4000),
                )
            ),
            (),
            (),
            "STABILITY_CHANGED",
        ),
        (
            "removed",
            make_tree(
                (
                    ("ABC-123", 3, 3000),
                    ("XYZ-999", 4, 4000),
                )
            ),
            make_tree((("ABC-123", 3, 3000),)),
            (
                ("ABC-123", 3, 3000),
                ("XYZ-999", 4, 4000),
            ),
            ("XYZ-999",),
            "STABILITY_CHANGED",
        ),
        (
            "size",
            make_tree((("ABC-123", 3, 3000),)),
            make_tree((("ABC-123", 8, 3000),)),
            (("ABC-123", 3, 3000),),
            (),
            "STABILITY_CHANGED",
        ),
        (
            "mtime",
            make_tree((("ABC-123", 3, 3000),)),
            make_tree((("ABC-123", 3, 8000),)),
            (("ABC-123", 3, 3000),),
            (),
            "STABILITY_CHANGED",
        ),
        (
            "blocking",
            make_tree((("ABC-123", 3, 3000),)),
            make_tree(
                (("ABC-123", 3, 3000),),
                nested=(("ABC/ABC-123", "deeper"),),
            ),
            (),
            (),
            "UNEXPECTED_LAYOUT",
        ),
    )

    for (
        name,
        first,
        second,
        seeded,
        absent_expectations,
        expected_category,
    ) in cases:
        with tempfile.TemporaryDirectory(
            prefix="teddy-jav-safety-%s-" % name
        ) as temp:
            base = Path(temp)
            db_path = base / "discovery.sqlite3"
            operation_path = base / "operation.lock"
            writer_path = base / "writer.lock"
            create_db(db_path)

            for dvd_id, size, mtime_ns in seeded:
                seed_holding(
                    db_path,
                    dvd_id,
                    size,
                    mtime_ns,
                )

            filesystem = SequenceFilesystem(
                [first, second],
                writer_lock_path=writer_path,
            )
            report = apply_expect_unsafe(
                db_path,
                filesystem,
                operation_path,
                writer_path,
            )

            require(
                expected_category in categories(report),
                name + " changed scan was not reported",
            )
            no_inventory_write(db_path, 0)

            for dvd_id in absent_expectations:
                require(
                    scalar(
                        db_path,
                        "SELECT present FROM holdings "
                        "WHERE dvd_id = ?",
                        (dvd_id,),
                    ) == 1,
                    name + " scan marked a holding absent",
                )


def test_second_scan_failure_and_empty_root():
    with tempfile.TemporaryDirectory(
        prefix="teddy-jav-safety-errors-"
    ) as temp:
        base = Path(temp)
        db_path = base / "discovery.sqlite3"
        operation_path = base / "operation.lock"
        writer_path = base / "writer.lock"
        create_db(db_path)
        seed_holding(db_path, "ABC-123", 3, 3000)
        snapshot = make_tree((("ABC-123", 3, 3000),))

        filesystem = SequenceFilesystem(
            [snapshot, snapshot],
            error_scan=1,
            writer_lock_path=writer_path,
        )
        report = apply_expect_unsafe(
            db_path,
            filesystem,
            operation_path,
            writer_path,
        )
        require(
            "IO_ERROR" in categories(report),
            "second scan I/O error was not fail-closed",
        )
        no_inventory_write(db_path, 0)
        require(
            scalar(
                db_path,
                "SELECT present FROM holdings",
            ) == 1,
            "second scan I/O error marked absent",
        )

        filesystem = SequenceFilesystem(
            [snapshot, {".": []}],
            writer_lock_path=writer_path,
        )
        report = apply_expect_unsafe(
            db_path,
            filesystem,
            operation_path,
            writer_path,
        )
        require(
            "EMPTY_ROOT_WITH_PRESENT_HOLDINGS" in categories(report),
            "empty second root was not fail-closed",
        )
        no_inventory_write(db_path, 0)
        require(
            scalar(
                db_path,
                "SELECT present FROM holdings",
            ) == 1,
            "empty second root marked absent",
        )


def test_operation_lock_busy_and_lock_order():
    with tempfile.TemporaryDirectory(
        prefix="teddy-jav-safety-lock-"
    ) as temp:
        base = Path(temp)
        db_path = base / "discovery.sqlite3"
        operation_path = base / "operation.lock"
        writer_path = base / "writer.lock"
        create_db(db_path)
        snapshot = make_tree((("ABC-123", 3, 3000),))
        filesystem = SequenceFilesystem(
            [snapshot, snapshot],
            writer_lock_path=writer_path,
        )

        with operation_lock(operation_path):
            report = apply_expect_unsafe(
                db_path,
                filesystem,
                operation_path,
                writer_path,
            )

        require(
            "OPERATION_LOCK_BUSY" in categories(report),
            "busy operation lock was not held",
        )
        require(
            not filesystem.calls,
            "busy operation lock still started a scan",
        )
        no_inventory_write(db_path, 0)

        events = []
        traced_filesystem = SequenceFilesystem(
            [snapshot, snapshot],
            writer_lock_path=writer_path,
            trace=events,
        )
        original_operation_lock = reconcile_mod.operation_lock
        original_writer_lock = reconcile_mod.exclusive_lock

        @contextmanager
        def traced_operation_lock(path):
            events.append("operation-enter")
            with original_operation_lock(path):
                yield
            events.append("operation-exit")

        @contextmanager
        def traced_writer_lock(path):
            events.append("writer-enter")
            with original_writer_lock(path):
                yield
            events.append("writer-exit")

        reconcile_mod.operation_lock = traced_operation_lock
        reconcile_mod.exclusive_lock = traced_writer_lock
        try:
            result = reconcile_mod.apply_reconciliation(
                db_path,
                "/fake/JAV",
                filesystem=traced_filesystem,
                operation_lock_path=operation_path,
                writer_lock_path=writer_path,
            )
        finally:
            reconcile_mod.operation_lock = original_operation_lock
            reconcile_mod.exclusive_lock = original_writer_lock

        require(result["applied"] is True, "lock-order apply failed")
        writer_index = events.index("writer-enter")
        scan_indexes = [
            index
            for index, value in enumerate(events)
            if value.startswith("scan:")
        ]
        require(
            scan_indexes
            and writer_index > max(scan_indexes),
            "writer lock was acquired before bounded scans ended",
        )
        require(
            events.index("operation-enter")
            < writer_index
            < events.index("writer-exit")
            < events.index("operation-exit"),
            "lock ordering was not operation -> writer",
        )

        source = inspect.getsource(
            reconcile_mod.apply_reconciliation
        )
        require(
            source.index("with operation_lock")
            < source.index("stable_report = reconcile")
            < source.index("with exclusive_lock"),
            "apply lock ordering changed",
        )


class ProbeSSH:
    def stat_library(self, relative):
        return None


class ProbeMutator:
    def __init__(self, operation_path, reconcile_probe=None):
        self.operation_path = operation_path
        self.reconcile_probe = reconcile_probe
        self.calls = []
        self.lock_was_busy_during_publish = False
        self.reconcile_was_blocked = False

    def publish_to_library(self, **kwargs):
        self.calls.append("publish")
        try:
            with operation_lock(self.operation_path):
                raise RuntimeError(
                    "operation lock unexpectedly re-entered"
                )
        except OperationLockBusy:
            self.lock_was_busy_during_publish = True

        if self.reconcile_probe is not None:
            report = self.reconcile_probe()
            self.reconcile_was_blocked = (
                "OPERATION_LOCK_BUSY" in categories(report)
            )

        return {
            "status": "PUBLISHED",
            "size": 123,
            "mtime_ns": 1000,
            "source_preserved": True,
        }

    def cleanup_source(self, **kwargs):
        self.calls.append("cleanup")


def completion_plan():
    return CompletionPlan(
        source_relative="missav/ABC-123.mp4",
        dvd_id="ABC-123",
        parse_method="filename",
        size_bytes=123,
        mtime_ns=1000,
        destination_relative="ABC/ABC-123/ABC-123.mp4",
        metadata_ready=True,
        holding_count=0,
        planned_operation="PLAN_STAGE9_SSH_MOVE",
        collision_type="NONE",
        reason="safety smoke",
    )


def test_stage9_and_stage10_exclusion():
    with tempfile.TemporaryDirectory(
        prefix="teddy-jav-safety-stage9-"
    ) as temp:
        base = Path(temp)
        db_path = base / "discovery.sqlite3"
        operation_path = base / "operation.lock"
        writer_path = base / "writer.lock"
        create_db(db_path)

        reconcile_db_path = base / "reconcile.sqlite3"
        reconcile_writer_path = base / "reconcile-writer.lock"
        create_db(reconcile_db_path)
        snapshot = make_tree((("XYZ-999", 4, 4000),))
        reconcile_filesystem = SequenceFilesystem(
            [snapshot, snapshot],
            writer_lock_path=reconcile_writer_path,
        )

        def reconcile_probe():
            return apply_expect_unsafe(
                reconcile_db_path,
                reconcile_filesystem,
                operation_path,
                reconcile_writer_path,
            )

        mutator = ProbeMutator(
            operation_path,
            reconcile_probe,
        )
        process_one(
            completion_plan(),
            ssh=ProbeSSH(),
            mutator=mutator,
            db_path=db_path,
            writer_lock_path=writer_path,
            operation_lock_path=operation_path,
        )
        require(
            mutator.lock_was_busy_during_publish,
            "Stage9 publish did not hold operation lock",
        )
        require(
            mutator.reconcile_was_blocked,
            "Stage10 reconciliation overlapped Stage9 publish",
        )
        require(
            mutator.calls == ["publish", "cleanup"],
            "Stage9 publish/recovery semantics changed",
        )

        blocked_mutator = ProbeMutator(operation_path)
        with operation_lock(operation_path):
            try:
                process_one(
                    completion_plan(),
                    ssh=ProbeSSH(),
                    mutator=blocked_mutator,
                    db_path=db_path,
                    writer_lock_path=writer_path,
                    operation_lock_path=operation_path,
                )
            except OperationLockBusy:
                pass
            else:
                raise RuntimeError(
                    "Stage9 ran while Stage10 owned operation lock"
                )

        require(
            blocked_mutator.calls == [],
            "Stage9 attempted publish while operation lock was busy",
        )


def test_stage9_runner_busy_is_safe_skip():
    def planner(items, db_path):
        return [completion_plan()]

    def busy_processor(plan, **kwargs):
        raise OperationLockBusy("smoke busy")

    result = run_once(
        items=[],
        db_path=Path("/fake/db"),
        ssh=object(),
        mutator=object(),
        writer_lock_path=Path("/fake/writer.lock"),
        operation_lock_path=Path("/fake/operation.lock"),
        apply=True,
        confirm=CONFIRMATION,
        planner=planner,
        processor=busy_processor,
    )

    require(
        result["applied"] == 0,
        "busy Stage9 operation lock reported an apply",
    )
    require(
        result["operation_lock_skipped"] == 1,
        "busy Stage9 operation lock was not skipped",
    )


def main():
    test_stable_scan_applies_second_snapshot()
    test_changed_scan_is_fail_closed()
    test_second_scan_failure_and_empty_root()
    test_operation_lock_busy_and_lock_order()
    test_stage9_and_stage10_exclusion()
    test_stage9_runner_busy_is_safe_skip()

    print("STAGE10_B1_STABLE_RECHECK=PASS")
    print("STAGE10_B1_OPERATION_LOCK=PASS")
    print("STAGE10_B1_FAIL_CLOSED=PASS")
    print("STAGE10_B1_LOCK_ORDER=PASS")
    print("STAGE10_B1_SAFETY_SMOKE=PASS")


if __name__ == "__main__":
    main()
