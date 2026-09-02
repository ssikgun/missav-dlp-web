from pathlib import Path
import json
import inspect
import os
import shlex
import sqlite3
import stat
import tempfile
from types import SimpleNamespace

from teddy_discovery_completion_ssh import (
    CompletionSSH,
)
from teddy_discovery_db import connect, initialize
from teddy_discovery_organizer import canonical_destination

import teddy_discovery_jav_reconcile as reconcile_mod


def require(value, message):
    if not value:
        raise RuntimeError(message)


def create_db(path):
    db = connect(path)
    initialize(db)
    db.close()


def scalar(path, sql, params=()):
    db = sqlite3.connect(path)
    try:
        return db.execute(sql, params).fetchone()[0]
    finally:
        db.close()


def seed_holding(
    path,
    relative_path,
    dvd_id,
    *,
    present=1,
    size_bytes=1,
    mtime_ns=1,
):
    db = sqlite3.connect(path)
    db.execute(
        """
        INSERT INTO holdings(
            storage_root,
            relative_path,
            dvd_id,
            parse_status,
            parse_method,
            parse_candidates_json,
            size_bytes,
            mtime_ns,
            discovered_by,
            present,
            first_seen_at,
            last_seen_at,
            last_seen_run_id
        ) VALUES (
            'jav', ?, ?, 'MATCHED', 'remote-smoke', ?, ?, ?,
            'remote-smoke', ?, 'now', 'now', NULL
        )
        """,
        (
            relative_path,
            dvd_id,
            json.dumps([dvd_id]),
            size_bytes,
            mtime_ns,
            present,
        ),
    )
    db.commit()
    db.close()


def _entry(name, mode, size=0, mtime_ns=0):
    return {
        "name": name,
        "mode": int(mode),
        "size": int(size),
        "mtime_ns": int(mtime_ns),
    }


def _add_dir(tree, parent, name):
    children = tree.setdefault(parent, [])
    if not any(item["name"] == name for item in children):
        children.append(
            _entry(
                name,
                stat.S_IFDIR | 0o755,
            )
        )


def _add_file(tree, parent, name, size, mtime_ns, mode=None):
    tree.setdefault(parent, []).append(
        _entry(
            name,
            mode or (stat.S_IFREG | 0o644),
            size,
            mtime_ns,
        )
    )


def add_video(
    tree,
    dvd_id,
    suffix=".mp4",
    *,
    size=3,
    mtime_ns=3000,
):
    relative = canonical_destination(
        dvd_id,
        suffix,
    ).as_posix()
    prefix, dvd_dir, filename = relative.split("/")
    _add_dir(tree, ".", prefix)
    _add_dir(tree, prefix, dvd_dir)
    _add_file(
        tree,
        prefix + "/" + dvd_dir,
        filename,
        size,
        mtime_ns,
    )
    return relative


class FakeRemoteRunner:
    def __init__(
        self,
        tree=None,
        *,
        root_status="ok",
        error_relative=None,
        error_kind="io",
        malformed=False,
        returncode=0,
    ):
        self.tree = tree or {}
        self.root_status = root_status
        self.error_relative = set(error_relative or ())
        self.error_kind = error_kind
        self.malformed = malformed
        self.returncode = returncode
        self.calls = []
        self.relative_calls = []
        self.scripts = []

    def __call__(
        self,
        command,
        *,
        input,
        stdout,
        stderr,
        text,
    ):
        self.calls.append(command)
        self.scripts.append(input)

        if self.returncode:
            return SimpleNamespace(
                returncode=self.returncode,
                stdout="",
                stderr="simulated SSH failure",
            )

        args = shlex.split(command[-1])
        relative = args[-1]
        self.relative_calls.append(relative)

        if self.malformed:
            return SimpleNamespace(
                returncode=0,
                stdout="not-json",
                stderr="",
            )

        if relative in self.error_relative:
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({
                    "status": "error",
                    "kind": self.error_kind,
                    "detail": "simulated remote error",
                }),
                stderr="",
            )

        if "TEDDY_REMOTE_JAV_LSTAT_V1" in input:
            if self.root_status != "ok":
                return SimpleNamespace(
                    returncode=0,
                    stdout=json.dumps({
                        "status": self.root_status,
                    }),
                    stderr="",
                )

            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({
                    "status": "ok",
                    "mode": stat.S_IFDIR | 0o755,
                    "size": 0,
                    "mtime_ns": 0,
                }),
                stderr="",
            )

        if "TEDDY_REMOTE_JAV_LISTDIR_V1" in input:
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({
                    "status": "ok",
                    "entries": self.tree.get(relative, []),
                }),
                stderr="",
            )

        raise AssertionError(
            "unexpected remote script"
        )


def make_ssh(runner, library_root="/remote/JAV"):
    return CompletionSSH(
        host="fake-nas",
        user="tester",
        key="/fake/key",
        known_hosts="/fake/known_hosts",
        downloads_root="/remote/downloads",
        library_root=library_root,
        runner=runner,
    )


def categories(report):
    return {
        finding.category
        for finding in report.findings
    }


def apply_must_fail(db_path, ssh, library_root):
    try:
        apply_with_locks(
            db_path,
            ssh,
            library_root=library_root,
        )
    except reconcile_mod.ReconciliationUnsafe as exc:
        return exc.report

    raise RuntimeError(
        "unsafe remote reconciliation unexpectedly applied"
    )


def apply_with_locks(db_path, ssh, *, library_root):
    base = Path(db_path).parent
    return reconcile_mod.apply_remote_reconciliation(
        db_path,
        ssh,
        library_root=library_root,
        operation_lock_path=base / "operation.lock",
        writer_lock_path=base / "writer.lock",
    )


def test_clean_depth_and_missing_db_row():
    with tempfile.TemporaryDirectory(
        prefix="teddy-jav-remote-clean-"
    ) as temp:
        db_path = Path(temp) / "discovery.sqlite3"
        create_db(db_path)
        tree = {}
        add_video(tree, "ABC-123")
        add_video(tree, "XYZ-999", size=4, mtime_ns=4000)
        runner = FakeRemoteRunner(tree)
        ssh = make_ssh(runner)

        report = reconcile_mod.reconcile_remote(
            db_path,
            ssh,
            library_root="/remote/JAV",
        )

        require(report.scan_complete, "remote clean scan incomplete")
        require(report.apply_eligible, "remote clean scan not eligible")
        require(
            len(report.canonical_present_files) == 2,
            "remote canonical file count changed",
        )
        require(
            len(categories(report)) == 1
            and "FILESYSTEM_PRESENT_DB_MISSING" in categories(report),
            "remote DB-missing rows were not reported",
        )
        require(
            runner.relative_calls == [
                ".",
                ".",
                "ABC",
                "ABC/ABC-123",
                "XYZ",
                "XYZ/XYZ-999",
            ],
            "remote traversal was not exactly bounded",
        )
        require(
            all(
                relative == "."
                or len(relative.split("/")) <= 2
                for relative in runner.relative_calls
            ),
            "remote traversal exceeded JAV root/PREFIX/DVD-ID depth",
        )
        require(
            all(
                "/remote/JAV" in command[-1]
                for command in runner.calls
            ),
            "remote library root was not used",
        )
        require(
            all(
                "/remote/downloads" not in command[-1]
                for command in runner.calls
            ),
            "staging root leaked into remote library requests",
        )

        base = runner.calls[0]
        require(
            [
                "-o",
                "StrictHostKeyChecking=yes",
            ] == base[base.index("-o"):base.index("-o") + 2]
            or "StrictHostKeyChecking=yes" in base,
            "strict host key checking was not preserved",
        )
        require(
            "IdentitiesOnly=yes" in base
            and "BatchMode=yes" in base
            and "UserKnownHostsFile=/fake/known_hosts" in base,
            "SSH safety options were not preserved",
        )


def test_remote_missing_apply_and_revive():
    with tempfile.TemporaryDirectory(
        prefix="teddy-jav-remote-apply-"
    ) as temp:
        db_path = Path(temp) / "discovery.sqlite3"
        create_db(db_path)
        tree = {}
        live_relative = add_video(
            tree,
            "LIVE-001",
            size=4,
            mtime_ns=4000,
        )
        missing_relative = "MISS/MISS-001/MISS-001.mp4"
        seed_holding(
            db_path,
            missing_relative,
            "MISS-001",
            size_bytes=4,
            mtime_ns=4,
        )
        runner = FakeRemoteRunner(tree)
        ssh = make_ssh(runner)

        report = reconcile_mod.reconcile_remote(
            db_path,
            ssh,
            library_root="/remote/JAV",
        )
        require(
            "DB_PRESENT_FILESYSTEM_MISSING" in categories(report),
            "remote DB-present missing file was not reported",
        )

        apply_with_locks(
            db_path,
            ssh,
            library_root="/remote/JAV",
        )
        require(
            scalar(
                db_path,
                "SELECT present FROM holdings WHERE relative_path = ?",
                (missing_relative,),
            ) == 0,
            "remote missing holding did not transition to present=0",
        )
        require(
            scalar(
                db_path,
                "SELECT present FROM holdings WHERE relative_path = ?",
                (live_relative,),
            ) == 1,
            "remote canonical file was not inserted as present",
        )

    with tempfile.TemporaryDirectory(
        prefix="teddy-jav-remote-revive-"
    ) as temp:
        db_path = Path(temp) / "discovery.sqlite3"
        create_db(db_path)
        tree = {}
        relative = add_video(
            tree,
            "REV-001",
            size=6,
            mtime_ns=6000,
        )
        seed_holding(
            db_path,
            relative,
            "REV-001",
            present=0,
            size_bytes=0,
            mtime_ns=0,
        )
        runner = FakeRemoteRunner(tree)
        ssh = make_ssh(runner)

        report = reconcile_mod.reconcile_remote(
            db_path,
            ssh,
            library_root="/remote/JAV",
        )
        require(
            "ABSENT_HOLDING_REAPPEARED" in categories(report),
            "remote absent holding reappearance was not reported",
        )
        apply_with_locks(
            db_path,
            ssh,
            library_root="/remote/JAV",
        )
        require(
            scalar(
                db_path,
                "SELECT present FROM holdings WHERE relative_path = ?",
                (relative,),
            ) == 1,
            "remote same-path holding was not revived",
        )


def test_fail_closed_empty_unavailable_and_errors():
    with tempfile.TemporaryDirectory(
        prefix="teddy-jav-remote-fail-"
    ) as temp:
        base = Path(temp)
        db_path = base / "discovery.sqlite3"
        create_db(db_path)
        seed_holding(
            db_path,
            "OLD/OLD-001/OLD-001.mp4",
            "OLD-001",
        )
        before_runs = scalar(
            db_path,
            "SELECT COUNT(*) FROM inventory_runs",
        )

        empty_runner = FakeRemoteRunner({})
        empty_ssh = make_ssh(empty_runner)
        report = apply_must_fail(
            db_path,
            empty_ssh,
            "/remote/JAV",
        )
        require(
            "EMPTY_ROOT_WITH_PRESENT_HOLDINGS" in categories(report),
            "empty remote root was not fail-closed",
        )
        require(
            scalar(
                db_path,
                "SELECT COUNT(*) FROM inventory_runs",
            ) == before_runs,
            "empty remote root wrote an inventory run",
        )
        require(
            scalar(
                db_path,
                "SELECT present FROM holdings",
            ) == 1,
            "empty remote root marked a holding absent",
        )

        missing_runner = FakeRemoteRunner(
            root_status="missing"
        )
        missing_ssh = make_ssh(missing_runner)
        report = apply_must_fail(
            db_path,
            missing_ssh,
            "/remote/JAV",
        )
        require(
            "ROOT_UNAVAILABLE" in categories(report),
            "unavailable remote root was not fail-closed",
        )
        require(
            scalar(
                db_path,
                "SELECT COUNT(*) FROM inventory_runs",
            ) == before_runs,
            "unavailable remote root wrote an inventory run",
        )

        permission_runner = FakeRemoteRunner(
            error_relative={"."},
            error_kind="permission",
        )
        permission_ssh = make_ssh(permission_runner)
        report = apply_must_fail(
            db_path,
            permission_ssh,
            "/remote/JAV",
        )
        require(
            "PERMISSION_ERROR" in categories(report),
            "remote permission error was not fail-closed",
        )

        ssh_runner = FakeRemoteRunner(returncode=1)
        ssh = make_ssh(ssh_runner)
        report = apply_must_fail(
            db_path,
            ssh,
            "/remote/JAV",
        )
        require(
            "IO_ERROR" in categories(report),
            "SSH error was not fail-closed",
        )

        malformed_runner = FakeRemoteRunner(malformed=True)
        malformed_ssh = make_ssh(malformed_runner)
        report = apply_must_fail(
            db_path,
            malformed_ssh,
            "/remote/JAV",
        )
        require(
            "IO_ERROR" in categories(report),
            "remote protocol error was not fail-closed",
        )


def test_layout_holds():
    cases = []

    symlink_tree = {}
    _add_dir(symlink_tree, ".", "SYM")
    _add_dir(symlink_tree, "SYM", "SYM-001")
    _add_file(
        symlink_tree,
        "SYM/SYM-001",
        "SYM-001.mp4",
        1,
        1,
        mode=stat.S_IFLNK | 0o777,
    )
    cases.append((symlink_tree, "SYMLINK"))

    nested_tree = {}
    add_video(nested_tree, "NEST-001")
    _add_dir(nested_tree, "NEST/NEST-001", "deeper")
    cases.append((nested_tree, "UNEXPECTED_LAYOUT"))

    unmatched_tree = {}
    _add_dir(unmatched_tree, ".", "BAD")
    _add_dir(unmatched_tree, "BAD", "BAD-001")
    _add_file(
        unmatched_tree,
        "BAD/BAD-001",
        "not-a-dvd-id.mp4",
        1,
        1,
    )
    cases.append((unmatched_tree, "UNMATCHED_DVD_ID"))

    duplicate_tree = {}
    add_video(duplicate_tree, "DUP-001", ".mp4")
    add_video(duplicate_tree, "DUP-001", ".mkv")
    cases.append((duplicate_tree, "DUPLICATE_PHYSICAL_MEDIA"))

    with tempfile.TemporaryDirectory(
        prefix="teddy-jav-remote-layout-"
    ) as temp:
        for index, (tree, category) in enumerate(cases):
            db_path = Path(temp) / ("case-%d.sqlite3" % index)
            create_db(db_path)
            runner = FakeRemoteRunner(tree)
            ssh = make_ssh(runner)
            report = reconcile_mod.reconcile_remote(
                db_path,
                ssh,
                library_root="/remote/JAV",
            )
            require(
                category in categories(report),
                category + " was not held",
            )
            require(
                not report.apply_eligible,
                category + " was apply-eligible",
            )


def test_size_mtime_incomplete_and_read_only():
    with tempfile.TemporaryDirectory(
        prefix="teddy-jav-remote-drift-"
    ) as temp:
        base = Path(temp)
        db_path = base / "discovery.sqlite3"
        create_db(db_path)
        tree = {}
        relative = add_video(
            tree,
            "DRIFT-001",
            size=8,
            mtime_ns=8000,
        )
        seed_holding(
            db_path,
            relative,
            "DRIFT-001",
            size_bytes=9,
            mtime_ns=9000,
        )
        runner = FakeRemoteRunner(tree)
        ssh = make_ssh(runner)
        report = reconcile_mod.reconcile_remote(
            db_path,
            ssh,
            library_root="/remote/JAV",
        )
        require(
            "SIZE_MISMATCH" in categories(report),
            "remote size mismatch was not reported",
        )
        require(
            "MTIME_MISMATCH" in categories(report),
            "remote mtime mismatch was not reported",
        )

        incomplete_runner = FakeRemoteRunner(
            tree,
            error_relative={"DRIFT"},
        )
        incomplete_ssh = make_ssh(incomplete_runner)
        before_runs = scalar(
            db_path,
            "SELECT COUNT(*) FROM inventory_runs",
        )
        report = apply_must_fail(
            db_path,
            incomplete_ssh,
            "/remote/JAV",
        )
        require(
            not report.scan_complete,
            "incomplete remote scan was marked complete",
        )
        require(
            scalar(
                db_path,
                "SELECT present FROM holdings WHERE dvd_id = ?",
                ("DRIFT-001",),
            ) == 1,
            "incomplete remote scan marked absent",
        )
        require(
            scalar(
                db_path,
                "SELECT COUNT(*) FROM inventory_runs",
            ) == before_runs,
            "incomplete remote scan wrote an inventory run",
        )

        all_remote_text = "\n".join(
            [
                " ".join(command)
                for command in runner.calls
            ]
            + runner.scripts
        )
        for forbidden in (
            "mkdir",
            "rename",
            "unlink",
            "remove",
            "os.replace",
            "mv ",
            "rm ",
            "write(",
        ):
            require(
                forbidden not in all_remote_text,
                "remote adapter generated write command: " + forbidden,
            )


def test_library_root_configuration_and_bounded_source():
    saved_library = os.environ.pop(
        reconcile_mod.REMOTE_LIBRARY_ROOT_ENV,
        None,
    )
    saved_staging = os.environ.get(
        reconcile_mod.STAGING_ROOT_ENV
    )
    os.environ[reconcile_mod.STAGING_ROOT_ENV] = (
        "/remote/downloads"
    )

    try:
        with tempfile.TemporaryDirectory(
            prefix="teddy-jav-remote-config-"
        ) as temp:
            db_path = Path(temp) / "discovery.sqlite3"
            create_db(db_path)
            runner = FakeRemoteRunner({})
            ssh = make_ssh(runner)

            report = reconcile_mod.reconcile_remote(
                db_path,
                ssh,
                library_root=None,
            )
            require(
                "REMOTE_LIBRARY_ROOT_UNAVAILABLE" in categories(report),
                "missing dedicated library root was not fail-closed",
            )
            require(
                not runner.calls,
                "missing library root attempted remote I/O",
            )
            require(
                not report.apply_eligible,
                "missing library root was apply-eligible",
            )

            try:
                reconcile_mod.remote_library_root(
                    "/remote/downloads"
                )
            except reconcile_mod.RemoteLibraryRootError:
                pass
            else:
                raise RuntimeError(
                    "staging root was accepted as library root"
                )

            for source in (
                inspect.getsource(reconcile_mod.scan_bounded),
                reconcile_mod._REMOTE_LSTAT_SCRIPT,
                reconcile_mod._REMOTE_LISTDIR_SCRIPT,
            ):
                for forbidden in (
                    "rglob(",
                    "os.walk(",
                    "find(",
                    "du(",
                ):
                    require(
                        forbidden not in source,
                        "remote/local scanner contains recursive traversal: "
                        + forbidden,
                    )

    finally:
        if saved_library is not None:
            os.environ[
                reconcile_mod.REMOTE_LIBRARY_ROOT_ENV
            ] = saved_library
        if saved_staging is None:
            os.environ.pop(
                reconcile_mod.STAGING_ROOT_ENV,
                None,
            )
        else:
            os.environ[
                reconcile_mod.STAGING_ROOT_ENV
            ] = saved_staging


def main():
    test_clean_depth_and_missing_db_row()
    test_remote_missing_apply_and_revive()
    test_fail_closed_empty_unavailable_and_errors()
    test_layout_holds()
    test_size_mtime_incomplete_and_read_only()
    test_library_root_configuration_and_bounded_source()

    print("JAV_REMOTE_RECONCILIATION_SMOKE=PASS")
    print("JAV_REMOTE_RECONCILIATION_BOUNDED_DEPTH=PASS")
    print("JAV_REMOTE_RECONCILIATION_FAIL_CLOSED=PASS")
    print("JAV_REMOTE_RECONCILIATION_READ_ONLY=PASS")


if __name__ == "__main__":
    main()
