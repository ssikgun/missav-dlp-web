from pathlib import Path
import inspect
import os
import sqlite3
import tempfile

import teddy_discovery_jav_reconcile as reconcile_mod
from teddy_discovery_db import connect, initialize
from teddy_discovery_organizer import canonical_destination


def require(value, message):
    if not value:
        raise RuntimeError(message)


def create_db(path):
    db = connect(path)
    initialize(db)
    db.close()


def seed_holding(
    path,
    relative_path,
    dvd_id,
    *,
    present=1,
    size_bytes=1,
    mtime_ns=1,
    parse_status="MATCHED",
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
            'jav', ?, ?, ?, 'smoke', ?, ?, ?,
            'smoke', ?, 'now', 'now', NULL
        )
        """,
        (
            relative_path,
            dvd_id,
            parse_status,
            "[\"" + dvd_id + "\"]",
            size_bytes,
            mtime_ns,
            present,
        ),
    )
    db.commit()
    db.close()


def scalar(path, sql, params=()):
    db = sqlite3.connect(path)
    try:
        return db.execute(sql, params).fetchone()[0]
    finally:
        db.close()


def make_video(root, dvd_id, suffix=".mp4", data=b"x"):
    relative = canonical_destination(
        dvd_id,
        suffix,
    )
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path, relative.as_posix()


def categories(report):
    return [
        finding.category
        for finding in report.findings
    ]


def apply_must_fail(db_path, root, **kwargs):
    try:
        reconcile_mod.apply_reconciliation(
            db_path,
            root,
            **kwargs,
        )
    except reconcile_mod.ReconciliationUnsafe as exc:
        return exc.report

    raise RuntimeError(
        "unsafe reconciliation unexpectedly applied"
    )


def test_clean_and_missing_db_row():
    with tempfile.TemporaryDirectory(
        prefix="teddy-jav-reconcile-clean-"
    ) as temp:
        root = Path(temp) / "jav"
        db_path = Path(temp) / "discovery.sqlite3"
        root.mkdir()
        create_db(db_path)

        make_video(root, "ABC-123", data=b"abc")
        make_video(root, "XYZ-999", data=b"xyz")

        report = reconcile_mod.reconcile(
            db_path,
            root,
        )

        require(
            report.scan_complete,
            "canonical scan was not complete",
        )
        require(
            report.apply_eligible,
            "DB-missing canonical files should be repairable",
        )
        require(
            len(report.canonical_present_files) == 2,
            "canonical file count changed",
        )
        require(
            categories(report).count(
                "FILESYSTEM_PRESENT_DB_MISSING"
            ) == 2,
            "DB-missing rows were not reported",
        )


def test_db_missing_file_and_apply_semantics():
    with tempfile.TemporaryDirectory(
        prefix="teddy-jav-reconcile-apply-"
    ) as temp:
        root = Path(temp) / "jav"
        db_path = Path(temp) / "discovery.sqlite3"
        root.mkdir()
        create_db(db_path)

        _, live_relative = make_video(
            root,
            "LIVE-001",
            data=b"live",
        )
        missing_relative = (
            "MISS/MISS-001/MISS-001.mp4"
        )
        seed_holding(
            db_path,
            missing_relative,
            "MISS-001",
            size_bytes=4,
            mtime_ns=4,
        )

        report = reconcile_mod.reconcile(
            db_path,
            root,
        )
        require(
            "DB_PRESENT_FILESYSTEM_MISSING"
            in categories(report),
            "DB-present filesystem-missing row was not reported",
        )

        result = reconcile_mod.apply_reconciliation(
            db_path,
            root,
        )
        require(
            result["applied"] is True,
            "clean complete apply did not run",
        )
        require(
            scalar(
                db_path,
                "SELECT present FROM holdings "
                "WHERE relative_path = ?",
                (missing_relative,),
            ) == 0,
            "missing holding did not transition to present=0",
        )
        require(
            scalar(
                db_path,
                "SELECT present FROM holdings "
                "WHERE relative_path = ?",
                (live_relative,),
            ) == 1,
            "canonical live holding was not present",
        )


def test_same_path_revive():
    with tempfile.TemporaryDirectory(
        prefix="teddy-jav-reconcile-revive-"
    ) as temp:
        root = Path(temp) / "jav"
        db_path = Path(temp) / "discovery.sqlite3"
        root.mkdir()
        create_db(db_path)

        path, relative = make_video(
            root,
            "REV-001",
            data=b"revive",
        )
        seed_holding(
            db_path,
            relative,
            "REV-001",
            present=0,
            size_bytes=0,
            mtime_ns=0,
        )

        report = reconcile_mod.reconcile(
            db_path,
            root,
        )
        require(
            "ABSENT_HOLDING_REAPPEARED"
            in categories(report),
            "same-path absent row was not reported",
        )

        reconcile_mod.apply_reconciliation(
            db_path,
            root,
        )
        require(
            scalar(
                db_path,
                "SELECT present FROM holdings "
                "WHERE relative_path = ?",
                (relative,),
            ) == 1,
            "same-path absent row was not revived",
        )
        require(
            path.is_file(),
            "smoke file unexpectedly disappeared",
        )


def test_empty_root_and_unavailable_root():
    with tempfile.TemporaryDirectory(
        prefix="teddy-jav-reconcile-empty-"
    ) as temp:
        base = Path(temp)
        empty_root = base / "empty"
        db_path = base / "discovery.sqlite3"
        empty_root.mkdir()
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
        report = apply_must_fail(
            db_path,
            empty_root,
        )
        after_runs = scalar(
            db_path,
            "SELECT COUNT(*) FROM inventory_runs",
        )
        require(
            "EMPTY_ROOT_WITH_PRESENT_HOLDINGS"
            in categories(report),
            "empty root was not fail-closed",
        )
        require(
            before_runs == after_runs,
            "empty fail-closed path wrote an inventory run",
        )
        require(
            scalar(
                db_path,
                "SELECT present FROM holdings",
            ) == 1,
            "empty fail-closed path marked absent",
        )

        unavailable = base / "does-not-exist"
        report = apply_must_fail(
            db_path,
            unavailable,
        )
        require(
            "ROOT_UNAVAILABLE"
            in categories(report),
            "unavailable root was not fail-closed",
        )
        require(
            scalar(
                db_path,
                "SELECT COUNT(*) FROM inventory_runs",
            ) == before_runs,
            "unavailable root wrote an inventory run",
        )


def test_expected_mount_and_permission_io():
    with tempfile.TemporaryDirectory(
        prefix="teddy-jav-reconcile-errors-"
    ) as temp:
        base = Path(temp)
        root = base / "jav"
        db_path = base / "discovery.sqlite3"
        root.mkdir()
        create_db(db_path)
        seed_holding(
            db_path,
            "OLD/OLD-001/OLD-001.mp4",
            "OLD-001",
        )

        report = apply_must_fail(
            db_path,
            root,
            expected_mount=base / "not-mounted",
        )
        require(
            "MOUNT_UNAVAILABLE"
            in categories(report),
            "unavailable expected mount was not blocked",
        )

        original_scandir = reconcile_mod.os.scandir

        def permission_denied(path):
            raise PermissionError(
                "smoke permission denied"
            )

        reconcile_mod.os.scandir = permission_denied
        try:
            report = apply_must_fail(
                db_path,
                root,
            )
        finally:
            reconcile_mod.os.scandir = original_scandir

        require(
            "PERMISSION_ERROR"
            in categories(report),
            "permission error was not fail-closed",
        )
        require(
            scalar(
                db_path,
                "SELECT present FROM holdings",
            ) == 1,
            "permission error marked absent",
        )

        def io_error(path):
            raise OSError(
                "smoke I/O error"
            )

        reconcile_mod.os.scandir = io_error
        try:
            report = reconcile_mod.reconcile(
                db_path,
                root,
            )
        finally:
            reconcile_mod.os.scandir = original_scandir

        require(
            "IO_ERROR"
            in categories(report),
            "I/O error was not reported",
        )


def test_duplicate_nested_symlink_unmatched():
    with tempfile.TemporaryDirectory(
        prefix="teddy-jav-reconcile-layout-"
    ) as temp:
        base = Path(temp)

        duplicate_root = base / "duplicate"
        duplicate_db = base / "duplicate.sqlite3"
        duplicate_root.mkdir()
        create_db(duplicate_db)
        make_video(
            duplicate_root,
            "DUP-001",
            ".mp4",
            b"one",
        )
        make_video(
            duplicate_root,
            "DUP-001",
            ".mkv",
            b"two",
        )
        report = reconcile_mod.reconcile(
            duplicate_db,
            duplicate_root,
        )
        require(
            "DUPLICATE_PHYSICAL_MEDIA"
            in categories(report),
            "duplicate physical media was not held",
        )
        require(
            not report.apply_eligible,
            "duplicate physical media was apply-eligible",
        )

        nested_root = base / "nested"
        nested_db = base / "nested.sqlite3"
        nested_root.mkdir()
        create_db(nested_db)
        nested = (
            nested_root
            / "NEST/NEST-001/NESTED"
        )
        nested.mkdir(parents=True)
        (nested / "NEST-001.mp4").write_bytes(
            b"nested"
        )
        report = reconcile_mod.reconcile(
            nested_db,
            nested_root,
        )
        require(
            "UNEXPECTED_LAYOUT"
            in categories(report),
            "nested directory was not held",
        )

        symlink_root = base / "symlink"
        symlink_db = base / "symlink.sqlite3"
        symlink_root.mkdir()
        create_db(symlink_db)
        target = base / "target.mp4"
        target.write_bytes(b"target")
        symlink_parent = (
            symlink_root / "SYM/SYM-001"
        )
        symlink_parent.mkdir(parents=True)
        os.symlink(
            target,
            symlink_parent / "SYM-001.mp4",
        )
        report = reconcile_mod.reconcile(
            symlink_db,
            symlink_root,
        )
        require(
            "SYMLINK"
            in categories(report),
            "symlink was not held",
        )

        unmatched_root = base / "unmatched"
        unmatched_db = base / "unmatched.sqlite3"
        unmatched_root.mkdir()
        create_db(unmatched_db)
        unmatched_parent = (
            unmatched_root / "BAD/BAD-001"
        )
        unmatched_parent.mkdir(parents=True)
        (unmatched_parent / "not-a-dvd-id.mp4").write_bytes(
            b"bad"
        )
        report = reconcile_mod.reconcile(
            unmatched_db,
            unmatched_root,
        )
        require(
            "UNMATCHED_DVD_ID"
            in categories(report),
            "malformed DVD-ID was not held",
        )


def test_size_mtime_bounded_and_incomplete_apply():
    with tempfile.TemporaryDirectory(
        prefix="teddy-jav-reconcile-drift-"
    ) as temp:
        base = Path(temp)

        drift_root = base / "drift"
        drift_db = base / "drift.sqlite3"
        drift_root.mkdir()
        create_db(drift_db)
        path, relative = make_video(
            drift_root,
            "DRIFT-001",
            data=b"drift",
        )
        actual = path.stat()
        seed_holding(
            drift_db,
            relative,
            "DRIFT-001",
            size_bytes=999,
            mtime_ns=actual.st_mtime_ns - 1,
        )
        report = reconcile_mod.reconcile(
            drift_db,
            drift_root,
        )
        require(
            "SIZE_MISMATCH"
            in categories(report),
            "size mismatch was not reported",
        )
        require(
            "MTIME_MISMATCH"
            in categories(report),
            "mtime mismatch was not reported",
        )

        incomplete_root = base / "incomplete"
        incomplete_db = base / "incomplete.sqlite3"
        incomplete_root.mkdir()
        create_db(incomplete_db)
        seed_holding(
            incomplete_db,
            "OLD/OLD-001/OLD-001.mp4",
            "OLD-001",
        )
        nested = (
            incomplete_root
            / "NEW/NEW-001/deeper"
        )
        nested.mkdir(parents=True)
        before_runs = scalar(
            incomplete_db,
            "SELECT COUNT(*) FROM inventory_runs",
        )
        apply_must_fail(
            incomplete_db,
            incomplete_root,
        )
        require(
            scalar(
                incomplete_db,
                "SELECT present FROM holdings "
                "WHERE dvd_id = 'OLD-001'",
            ) == 1,
            "incomplete scan marked absent",
        )
        require(
            scalar(
                incomplete_db,
                "SELECT COUNT(*) FROM inventory_runs",
            ) == before_runs,
            "incomplete scan wrote an inventory run",
        )

        source = inspect.getsource(
            reconcile_mod.scan_bounded
        )
        for forbidden in (
            "rglob(",
            "os.walk(",
            "find(",
            "du(",
        ):
            require(
                forbidden not in source,
                "bounded scanner contains recursive traversal: "
                + forbidden,
            )

        original_rglob = Path.rglob
        original_walk = os.walk

        def forbidden_traversal(*args, **kwargs):
            raise AssertionError(
                "recursive traversal was called"
            )

        Path.rglob = forbidden_traversal
        os.walk = forbidden_traversal
        try:
            report = reconcile_mod.reconcile(
                drift_db,
                drift_root,
            )
        finally:
            Path.rglob = original_rglob
            os.walk = original_walk

        require(
            report.root_available,
            "bounded scanner did not inspect root",
        )


def main():
    test_clean_and_missing_db_row()
    test_db_missing_file_and_apply_semantics()
    test_same_path_revive()
    test_empty_root_and_unavailable_root()
    test_expected_mount_and_permission_io()
    test_duplicate_nested_symlink_unmatched()
    test_size_mtime_bounded_and_incomplete_apply()

    print("JAV_RECONCILIATION_CANONICAL_SCAN=PASS")
    print("JAV_RECONCILIATION_FAIL_CLOSED=PASS")
    print("JAV_RECONCILIATION_APPLY_SEMANTICS=PASS")
    print("JAV_RECONCILIATION_BOUNDED_DEPTH=PASS")
    print("JAV_RECONCILIATION_SMOKE=PASS")


if __name__ == "__main__":
    main()
