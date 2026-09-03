"""Stage10-B4 isolated apply preflight canary.

The source database is opened read-only and copied with SQLite's backup API.
Every apply assertion runs against an independent temporary database copy and
an injected bounded filesystem.  This test must never be pointed at a live
database as its destination.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import os
import sqlite3
import stat
import shutil
import tempfile

import teddy_discovery_import as import_mod
import teddy_discovery_jav_reconcile as reconcile_mod
from teddy_discovery_db import connect as db_connect
from teddy_discovery_operation_lock import (
    OperationLockBusy,
    OperationLockError,
    operation_lock,
)
from teddy_discovery_organizer import canonical_destination
from teddy_ownership import is_owned


DEFAULT_SOURCE_DB = Path(
    "/opt/missav-dlp-web/discovery/teddy-discovery.sqlite3"
)
STORAGE_ROOT = "jav"
VIDEO_FIELDS = (
    "holding_id",
    "storage_root",
    "relative_path",
    "dvd_id",
    "parse_status",
    "parse_method",
    "parse_candidates_json",
    "size_bytes",
    "mtime_ns",
    "discovered_by",
    "present",
    "first_seen_at",
)
SEMANTIC_FIELDS = (
    "holding_id",
    "storage_root",
    "relative_path",
    "dvd_id",
    "parse_status",
    "parse_method",
    "parse_candidates_json",
    "size_bytes",
    "mtime_ns",
    "discovered_by",
    "present",
    "first_seen_at",
)


def require(value, message):
    if not value:
        raise RuntimeError(message)


def ro_connect(path):
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    db = sqlite3.connect(uri, uri=True)
    db.row_factory = sqlite3.Row
    return db


def source_summary(path):
    with ro_connect(path) as db:
        integrity = db.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
        row = db.execute(
            """
            SELECT
                COUNT(*) AS holdings,
                SUM(CASE WHEN present = 1 THEN 1 ELSE 0 END)
                    AS present
            FROM holdings
            WHERE storage_root = ?
            """,
            (STORAGE_ROOT,),
        ).fetchone()
        latest = db.execute(
            """
            SELECT run_id, status, video_files, matched,
                   ambiguous, unmatched
            FROM inventory_runs
            WHERE storage_root = ?
            ORDER BY run_id DESC
            LIMIT 1
            """,
            (STORAGE_ROOT,),
        ).fetchone()

    return {
        "integrity": integrity,
        "holdings": int(row["holdings"] or 0),
        "present": int(row["present"] or 0),
        "latest": tuple(latest) if latest else None,
    }


def backup_snapshot(source, destination):
    destination = Path(destination)
    require(not destination.exists(), "snapshot destination exists")

    source_db = ro_connect(source)
    destination_db = sqlite3.connect(destination)
    try:
        source_db.backup(destination_db, pages=64)
        destination_db.commit()
    finally:
        destination_db.close()
        source_db.close()

    with ro_connect(destination) as db:
        require(
            db.execute("PRAGMA integrity_check").fetchone()[0]
            == "ok",
            "SQLite backup snapshot failed integrity_check",
        )

    return destination


def stat_signature(path):
    path = Path(path)
    if not path.exists():
        return None

    value = path.stat()
    return (
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
    )


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _entry(tree, parent, name):
    for value in tree.setdefault(parent, ()):
        if value.name == name:
            return value

    value = FakeEntry(
        name,
        FakeStat(stat.S_IFDIR | 0o755),
    )
    tree[parent] = [*tree.get(parent, ()), value]
    tree.setdefault(_join(parent, name), [])
    return value


def _join(parent, name):
    if parent in ("", "."):
        return name
    return parent + "/" + name


def _ensure_parent(tree, relative):
    parts = PurePosixPath(relative).parts
    parent = "."
    for part in parts[:-1]:
        _entry(tree, parent, part)
        parent = _join(parent, part)
    return parent, parts[-1]


def empty_tree():
    return {".": []}


def add_file(tree, relative, size, mtime_ns, mode=None):
    parent, name = _ensure_parent(tree, relative)
    value = FakeStat(
        mode if mode is not None else stat.S_IFREG | 0o644,
        size,
        mtime_ns,
    )
    tree.setdefault(parent, []).append(FakeEntry(name, value))


def add_directory(tree, relative):
    parts = PurePosixPath(relative).parts
    parent = "."
    for part in parts:
        _entry(tree, parent, part)
        parent = _join(parent, part)


def record_for(dvd_id, suffix=".mp4", size=1, mtime_ns=1):
    relative = canonical_destination(
        dvd_id,
        suffix,
    ).as_posix()
    return {
        "classification": "CANONICAL_PRESENT",
        "entry_type": "regular_file",
        "relative_path": relative,
        "dvd_id": dvd_id,
        "parse_status": "MATCHED",
        "parse_method": "synthetic",
        "parse_candidates_json": json.dumps(
            [dvd_id],
            ensure_ascii=False,
        ),
        "size_bytes": size,
        "mtime_ns": mtime_ns,
    }


def tree_for_records(records):
    tree = empty_tree()
    for record in records:
        add_file(
            tree,
            record["relative_path"],
            record["size_bytes"],
            record["mtime_ns"],
        )

    for entries in tree.values():
        entries.sort(key=lambda item: item.name)
    return tree


class SequenceFilesystem:
    def __init__(self, snapshots):
        self.snapshots = snapshots
        self.scan_count = 0
        self.calls = []
        self._scan_index = -1

    def lstat(self, relative_path):
        self.calls.append(relative_path)
        if relative_path == ".":
            self._scan_index += 1
        return FakeStat(stat.S_IFDIR | 0o755)

    def listdir(self, relative_path):
        self.calls.append(relative_path)
        snapshot = self.snapshots[
            min(self._scan_index, len(self.snapshots) - 1)
        ]
        return list(snapshot.get(relative_path, ()))


def records_from_db(path):
    with ro_connect(path) as db:
        rows = db.execute(
            """
            SELECT relative_path, dvd_id, parse_status,
                   parse_method, parse_candidates_json,
                   size_bytes, mtime_ns
            FROM holdings
            WHERE storage_root = ? AND present = 1
            ORDER BY relative_path
            """,
            (STORAGE_ROOT,),
        ).fetchall()

    return [
        {
            "classification": "CANONICAL_PRESENT",
            "entry_type": "regular_file",
            "relative_path": row["relative_path"],
            "dvd_id": row["dvd_id"],
            "parse_status": row["parse_status"],
            "parse_method": row["parse_method"],
            "parse_candidates_json": row[
                "parse_candidates_json"
            ],
            "size_bytes": int(row["size_bytes"]),
            "mtime_ns": int(row["mtime_ns"]),
        }
        for row in rows
    ]


def holding_rows(path):
    with ro_connect(path) as db:
        return [
            dict(row)
            for row in db.execute(
                """
                SELECT holding_id, storage_root, relative_path,
                       dvd_id, parse_status, parse_method,
                       parse_candidates_json, size_bytes, mtime_ns,
                       discovered_by, present, first_seen_at,
                       last_seen_at, last_seen_run_id
                FROM holdings
                ORDER BY holding_id
                """
            )
        ]


def semantic_map(path):
    values = {}
    for row in holding_rows(path):
        values[(row["storage_root"], row["relative_path"])] = tuple(
            row[field] for field in SEMANTIC_FIELDS
        )
    return values


def semantic_hash(path):
    payload = [
        [key, value]
        for key, value in sorted(semantic_map(path).items())
    ]
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def counts(path):
    with ro_connect(path) as db:
        row = db.execute(
            """
            SELECT COUNT(*),
                   SUM(CASE WHEN present = 1 THEN 1 ELSE 0 END)
            FROM holdings
            WHERE storage_root = ?
            """,
            (STORAGE_ROOT,),
        ).fetchone()
    return int(row[0]), int(row[1] or 0)


def run_count(path):
    with ro_connect(path) as db:
        return db.execute(
            "SELECT COUNT(*) FROM inventory_runs"
        ).fetchone()[0]


def apply_ok(path, filesystem, base):
    return reconcile_mod.apply_reconciliation(
        path,
        base / "synthetic-jav",
        filesystem=filesystem,
        operation_lock_path=base / "operation.lock",
        writer_lock_path=base / "writer.lock",
    )


def expect_unsafe(path, filesystem, base):
    try:
        apply_ok(path, filesystem, base)
    except reconcile_mod.ReconciliationUnsafe as exc:
        return exc.report
    raise RuntimeError("unsafe canary unexpectedly applied")


def categories(report):
    return {finding.category for finding in report.findings}


def no_mutation(path, before_hash, before_counts, before_runs):
    require(
        semantic_hash(path) == before_hash,
        "unsafe path mutated holdings semantic state",
    )
    require(
        counts(path) == before_counts,
        "unsafe path changed holdings count",
    )
    require(
        run_count(path) == before_runs,
        "unsafe path wrote an inventory run",
    )


def unrelated_unchanged(before, after, excluded=()):
    excluded = set(excluded)
    before = {
        key: value
        for key, value in before.items()
        if key not in excluded
    }
    after = {
        key: value
        for key, value in after.items()
        if key not in excluded
    }
    require(before == after, "unrelated holding changed")


def fresh(snapshot, base, name):
    path = base / (name + ".sqlite3")
    shutil.copy2(snapshot, path)
    return path


def test_a_baseline(snapshot, base, baseline):
    path = fresh(snapshot, base, "a-baseline")
    before_hash = semantic_hash(path)
    before_counts = counts(path)
    before_runs = run_count(path)
    result = apply_ok(
        path,
        SequenceFilesystem([tree_for_records(baseline)] * 2),
        base,
    )
    require(result["applied"] is True, "baseline did not apply")
    require(result["counts"]["MATCHED"] == 148, "baseline count")
    require(semantic_hash(path) == before_hash, "baseline semantic drift")
    require(counts(path) == before_counts == (148, 148), "baseline counts")
    require(run_count(path) == before_runs + 1, "baseline run audit")


def test_b_insert(snapshot, base, baseline):
    path = fresh(snapshot, base, "b-insert")
    before = semantic_map(path)
    new = record_for("B4C-001", size=11, mtime_ns=202609030001)
    records = [*baseline, new]
    result = apply_ok(
        path,
        SequenceFilesystem([tree_for_records(records)] * 2),
        base,
    )
    require(result["applied"] is True, "new canonical did not apply")
    with ro_connect(path) as db:
        row = db.execute(
            """
            SELECT storage_root, relative_path, dvd_id,
                   parse_status, present
            FROM holdings
            WHERE relative_path = ?
            """,
            (new["relative_path"],),
        ).fetchone()
    require(row is not None, "new canonical row missing")
    require(tuple(row) == (
        "jav",
        new["relative_path"],
        "B4C-001",
        "MATCHED",
        1,
    ), "new canonical row semantics")
    require(counts(path) == (149, 149), "new canonical counts")
    unrelated_unchanged(
        before,
        semantic_map(path),
        excluded={(STORAGE_ROOT, new["relative_path"])},
    )
    require(
        is_owned("B4C-001", db_path=path),
        "inserted present=1 holding is not owned",
    )


def test_c_absent(snapshot, base, baseline):
    path = fresh(snapshot, base, "c-absent")
    selected = baseline[0]
    before = semantic_map(path)
    records = baseline[1:]
    result = apply_ok(
        path,
        SequenceFilesystem([tree_for_records(records)] * 2),
        base,
    )
    require(result["applied"] is True, "missing canonical did not apply")
    with ro_connect(path) as db:
        row = db.execute(
            "SELECT present FROM holdings WHERE relative_path = ?",
            (selected["relative_path"],),
        ).fetchone()
    require(row is not None and row[0] == 0, "holding was not marked absent")
    require(counts(path) == (148, 147), "absent counts")
    unrelated_unchanged(
        before,
        semantic_map(path),
        excluded={(STORAGE_ROOT, selected["relative_path"])},
    )
    require(
        not is_owned(selected["dvd_id"], db_path=path),
        "absent holding still owns DVD-ID",
    )


def set_present(path, relative_path, present):
    with sqlite3.connect(path) as db:
        db.execute(
            "UPDATE holdings SET present = ? WHERE relative_path = ?",
            (present, relative_path),
        )
        db.commit()


def test_d_revive(snapshot, base, baseline):
    path = fresh(snapshot, base, "d-revive")
    selected = baseline[0]
    set_present(path, selected["relative_path"], 0)
    before_rows = holding_rows(path)
    holding_id = next(
        row["holding_id"]
        for row in before_rows
        if row["relative_path"] == selected["relative_path"]
    )
    result = apply_ok(
        path,
        SequenceFilesystem([tree_for_records(baseline)] * 2),
        base,
    )
    require(result["applied"] is True, "reappearance did not apply")
    with ro_connect(path) as db:
        row = db.execute(
            """
            SELECT holding_id, present
            FROM holdings
            WHERE relative_path = ?
            """,
            (selected["relative_path"],),
        ).fetchone()
    require(row is not None, "revived row missing")
    require(tuple(row) == (holding_id, 1), "revive created duplicate row")
    require(counts(path) == (148, 148), "revive counts")
    require(
        is_owned(selected["dvd_id"], db_path=path),
        "revived present=1 holding is not owned",
    )


def test_e_metadata(snapshot, base, baseline):
    path = fresh(snapshot, base, "e-metadata")
    selected = baseline[0]
    before_rows = {
        row["relative_path"]: row
        for row in holding_rows(path)
    }
    changed = dict(selected)
    changed["size_bytes"] += 101
    changed["mtime_ns"] += 101
    records = [
        changed if item["relative_path"] == selected["relative_path"]
        else item
        for item in baseline
    ]
    result = apply_ok(
        path,
        SequenceFilesystem([tree_for_records(records)] * 2),
        base,
    )
    require(result["applied"] is True, "metadata drift did not apply")
    after_rows = {
        row["relative_path"]: row
        for row in holding_rows(path)
    }
    before_row = before_rows[selected["relative_path"]]
    after_row = after_rows[selected["relative_path"]]
    require(
        after_row["holding_id"] == before_row["holding_id"],
        "metadata drift changed holding identity",
    )
    for field in VIDEO_FIELDS:
        if field in {"size_bytes", "mtime_ns"}:
            continue
        require(
            after_row[field] == before_row[field],
            "unexpected metadata field changed: " + field,
        )
    require(
        (after_row["size_bytes"], after_row["mtime_ns"])
        == (changed["size_bytes"], changed["mtime_ns"]),
        "size/mtime were not updated",
    )
    require(counts(path) == (148, 148), "metadata counts")


def unsafe_case(snapshot, base, name, tree, expected):
    path = fresh(snapshot, base, name)
    before_hash = semantic_hash(path)
    before_counts = counts(path)
    before_runs = run_count(path)
    report = expect_unsafe(
        path,
        SequenceFilesystem([tree, tree]),
        base,
    )
    require(expected in categories(report), name + " was not held")
    no_mutation(path, before_hash, before_counts, before_runs)


def test_f_unsafe(snapshot, base):
    malformed = empty_tree()
    add_file(
        malformed,
        "BAD/BAD-001/not-a-dvd-id.mp4",
        1,
        1,
    )
    unsafe_case(
        snapshot,
        base,
        "f-malformed",
        malformed,
        "UNMATCHED_DVD_ID",
    )

    duplicate = empty_tree()
    add_file(duplicate, "DUP/DUP-001/DUP-001.mp4", 1, 1)
    add_file(duplicate, "DUP/DUP-001/DUP-001.mkv", 2, 2)
    unsafe_case(
        snapshot,
        base,
        "f-duplicate",
        duplicate,
        "DUPLICATE_PHYSICAL_MEDIA",
    )

    nested = tree_for_records([record_for("NEST-001")])
    add_directory(nested, "NEST/NEST-001/deeper")
    unsafe_case(
        snapshot,
        base,
        "f-nested",
        nested,
        "UNEXPECTED_LAYOUT",
    )

    symlink = tree_for_records([record_for("SYM-001")])
    add_file(
        symlink,
        "SYM/SYM-001/SYM-001-link.mp4",
        0,
        0,
        mode=stat.S_IFLNK | 0o777,
    )
    unsafe_case(
        snapshot,
        base,
        "f-symlink",
        symlink,
        "SYMLINK",
    )


def test_g_stability(snapshot, base, baseline):
    path = fresh(snapshot, base, "g-stability")
    before_hash = semantic_hash(path)
    before_counts = counts(path)
    before_runs = run_count(path)
    first = tree_for_records(baseline)
    second = tree_for_records(
        [*baseline, record_for("STB-001", size=7, mtime_ns=7)]
    )
    report = expect_unsafe(
        path,
        SequenceFilesystem([first, second]),
        base,
    )
    require(
        "STABILITY_CHANGED" in categories(report),
        "changed scan was not held",
    )
    no_mutation(path, before_hash, before_counts, before_runs)


def test_h_locks(snapshot, base, baseline):
    path = fresh(snapshot, base, "h-operation-busy")
    before_hash = semantic_hash(path)
    before_counts = counts(path)
    before_runs = run_count(path)
    filesystem = SequenceFilesystem([tree_for_records(baseline)] * 2)
    operation_path = base / "operation.lock"
    with operation_lock(operation_path):
        report = expect_unsafe(path, filesystem, base)
    require(
        "OPERATION_LOCK_BUSY" in categories(report),
        "operation lock busy was not fail-closed",
    )
    require(not filesystem.calls, "operation-busy path scanned filesystem")
    no_mutation(path, before_hash, before_counts, before_runs)

    original_operation_lock = reconcile_mod.operation_lock

    @contextmanager
    def operation_error(path):
        raise OperationLockError("synthetic operation lock error")
        yield

    reconcile_mod.operation_lock = operation_error
    try:
        path = fresh(snapshot, base, "h-operation-error")
        before_hash = semantic_hash(path)
        before_counts = counts(path)
        before_runs = run_count(path)
        report = expect_unsafe(
            path,
            SequenceFilesystem([tree_for_records(baseline)] * 2),
            base,
        )
        require(
            "OPERATION_LOCK_ERROR" in categories(report),
            "operation lock error was not fail-closed",
        )
        no_mutation(path, before_hash, before_counts, before_runs)
    finally:
        reconcile_mod.operation_lock = original_operation_lock

    original_writer_lock = reconcile_mod.exclusive_lock

    @contextmanager
    def writer_error(path):
        raise BlockingIOError("synthetic writer lock busy")
        yield

    reconcile_mod.exclusive_lock = writer_error
    try:
        path = fresh(snapshot, base, "h-writer-busy")
        before_hash = semantic_hash(path)
        before_counts = counts(path)
        before_runs = run_count(path)
        try:
            apply_ok(
                path,
                SequenceFilesystem([tree_for_records(baseline)] * 2),
                base,
            )
        except BlockingIOError:
            pass
        else:
            raise RuntimeError("writer lock busy unexpectedly applied")
        no_mutation(path, before_hash, before_counts, before_runs)
    finally:
        reconcile_mod.exclusive_lock = original_writer_lock


class FaultConnection:
    def __init__(self, connection, fail_on_holding_insert):
        self.connection = connection
        self.fail_on_holding_insert = fail_on_holding_insert
        self.holding_inserts = 0

    def execute(self, sql, parameters=()):
        normalized = " ".join(str(sql).upper().split())
        if "INSERT INTO HOLDINGS" in normalized:
            self.holding_inserts += 1
            if self.holding_inserts == self.fail_on_holding_insert:
                raise RuntimeError("synthetic mid-transaction fault")
        return self.connection.execute(sql, parameters)

    def __enter__(self):
        self.connection.__enter__()
        return self

    def __exit__(self, exc_type, exc, traceback):
        return self.connection.__exit__(exc_type, exc, traceback)

    def __getattr__(self, name):
        return getattr(self.connection, name)


def test_transaction_rollback(snapshot, base, baseline):
    path = fresh(snapshot, base, "transaction-rollback")
    before_hash = semantic_hash(path)
    before_counts = counts(path)
    before_runs = run_count(path)
    original_connect = import_mod.connect

    def fault_connect(db_path):
        return FaultConnection(
            db_connect(db_path),
            fail_on_holding_insert=2,
        )

    import_mod.connect = fault_connect
    try:
        try:
            apply_ok(
                path,
                SequenceFilesystem([tree_for_records(baseline)] * 2),
                base,
            )
        except RuntimeError as exc:
            require(
                "mid-transaction fault" in str(exc),
                "unexpected transaction fault",
            )
        else:
            raise RuntimeError("fault injection unexpectedly applied")
    finally:
        import_mod.connect = original_connect

    require(
        semantic_hash(path) == before_hash,
        "partial holdings mutation survived rollback",
    )
    require(counts(path) == before_counts, "rollback changed holdings count")
    require(
        run_count(path) == before_runs + 1,
        "failed inventory audit row was not retained",
    )
    with ro_connect(path) as db:
        latest = db.execute(
            "SELECT status FROM inventory_runs ORDER BY run_id DESC LIMIT 1"
        ).fetchone()[0]
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
    require(latest == "FAILED", "fault run was not marked FAILED")
    require(integrity == "ok", "rollback database integrity failed")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-db",
        type=Path,
        default=Path(
            os.environ.get(
                "TEDDY_B4_SOURCE_DB",
                DEFAULT_SOURCE_DB,
            )
        ),
    )
    args = parser.parse_args()
    source = args.source_db
    require(source.is_file(), "Production source DB is unavailable")

    source_before = {
        "signature": stat_signature(source),
        "sha256": sha256_file(source),
    }
    summary = source_summary(source)
    require(summary["integrity"] == "ok", "source DB integrity failed")
    require(
        summary["holdings"] == 148 and summary["present"] == 148,
        "source jav baseline is not 148/148",
    )

    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    temp_path = Path(
        tempfile.mkdtemp(prefix="stage10-b4-" + timestamp + "-")
    )
    try:
        baseline_path = backup_snapshot(
            source,
            temp_path / "baseline.sqlite3",
        )
        baseline = records_from_db(baseline_path)
        require(len(baseline) == 148, "baseline snapshot is not 148 files")

        test_a_baseline(baseline_path, temp_path, baseline)
        print("B4_A_BASELINE_NO_DRIFT=PASS")
        test_b_insert(baseline_path, temp_path, baseline)
        print("B4_B_FILESYSTEM_ONLY_INSERT=PASS")
        test_c_absent(baseline_path, temp_path, baseline)
        print("B4_C_DB_ONLY_ABSENT=PASS")
        test_d_revive(baseline_path, temp_path, baseline)
        print("B4_D_REAPPEARANCE_REVIVE=PASS")
        test_e_metadata(baseline_path, temp_path, baseline)
        print("B4_E_METADATA_DRIFT=PASS")
        test_f_unsafe(baseline_path, temp_path)
        print("B4_F_UNSAFE_FINDINGS=PASS")
        test_g_stability(baseline_path, temp_path, baseline)
        print("B4_G_STABILITY_CHANGED=PASS")
        test_h_locks(baseline_path, temp_path, baseline)
        print("B4_H_LOCK_CONTENTION=PASS")
        test_transaction_rollback(baseline_path, temp_path, baseline)
        print("B4_TRANSACTION_ROLLBACK=PASS")
    finally:
        for path in sorted(temp_path.rglob("*"), reverse=True):
            if path.is_file() or path.is_symlink():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        temp_path.rmdir()

    source_after = {
        "signature": stat_signature(source),
        "sha256": sha256_file(source),
    }
    require(
        source_after == source_before,
        "Production source DB changed during canary",
    )
    print("B4_PRODUCTION_DB_WRITE=0")
    print("B4_CANARY=PASS")


if __name__ == "__main__":
    main()
