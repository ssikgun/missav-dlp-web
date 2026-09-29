#!/usr/bin/env python3
"""Offline fixtures for exact read-only pending-operation eligibility checks."""
from __future__ import annotations

from pathlib import Path
import importlib.util
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from teddy_library_discovery_writer_smoke import fixture

_HELPER_PATH = Path(__file__).with_name("reconcile_discovery_pending.py")
_SPEC = importlib.util.spec_from_file_location("reconcile_discovery_pending", _HELPER_PATH)
_HELPER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HELPER)
CheckError = _HELPER.CheckError
check_operation = _HELPER.check_operation


OPERATION_ID = "op-fixture-1"
DVD_ID = "ABCD-123"


def _check(f):
    return check_operation(
        OPERATION_ID, DVD_ID,
        discovery_db=f["db_path"], provenance_db=f["provenance_path"],
        activity_check=lambda _dvd: "IDLE",
        nas_directory_absent=lambda _dvd, _relative: True,
    )


def _expect(f, code):
    try:
        _check(f)
    except CheckError as exc:
        assert exc.code == code, (exc.code, code)
    else:
        raise AssertionError("check-only accepted ineligible operation")


def main():
    with tempfile.TemporaryDirectory(prefix="pending-check-positive-") as tmp:
        f=fixture(tmp)
        f["store"].finish(OPERATION_ID, result_state="RECONCILE_PENDING",
            removed_entries=[f["media"].name], remaining_entries=[], nas_delete_complete=True,
            discovery_reconciled=False, jellyfin_reconciled=None)
        before=sqlite3.connect(f["db_path"]).execute(
            "SELECT holding_id,present FROM holdings ORDER BY holding_id").fetchall()
        result=_check(f)
        assert result["status"] == "RECOVERY_ELIGIBLE"
        assert result["recovery_phase"] == "READY_TO_MARK_ABSENT"
        assert result["operation_id"] == OPERATION_ID and result["dvd_id"] == DVD_ID
        assert result["holding_id"] == f["mark"]["holding_id"]
        db=sqlite3.connect(f["db_path"])
        assert db.execute("SELECT holding_id,present FROM holdings ORDER BY holding_id").fetchall() == before
        assert db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='library_delete_reconcile_journal'").fetchone() is None
        db.close()

        # Phase B is recognized only with the exact same operation journal.
        f["writer"].dispatch(f["mark"])
        db=sqlite3.connect(f["db_path"])
        assert db.execute("SELECT present FROM holdings WHERE holding_id=?",(f["mark"]["holding_id"],)).fetchone()[0] == 0
        db.close()
        result=_check(f)
        assert result["recovery_phase"] == "WRITER_DONE_PROVENANCE_PENDING"

    with tempfile.TemporaryDirectory(prefix="pending-check-absent-no-journal-") as tmp:
        f=fixture(tmp); f["store"].finish(OPERATION_ID, result_state="RECONCILE_PENDING",
            removed_entries=[f["media"].name], remaining_entries=[], nas_delete_complete=True,
            discovery_reconciled=False, jellyfin_reconciled=None)
        db=sqlite3.connect(f["db_path"]); db.execute("UPDATE holdings SET present=0 WHERE holding_id=?",(f["mark"]["holding_id"],)); db.commit(); db.close()
        _expect(f,"JOURNAL_STATE_CONFLICT")

    with tempfile.TemporaryDirectory(prefix="pending-check-absent-foreign-journal-") as tmp:
        f=fixture(tmp); f["store"].finish(OPERATION_ID, result_state="RECONCILE_PENDING",
            removed_entries=[f["media"].name], remaining_entries=[], nas_delete_complete=True,
            discovery_reconciled=False, jellyfin_reconciled=None)
        f["writer"].dispatch(f["mark"])
        db=sqlite3.connect(f["db_path"])
        db.execute("UPDATE library_delete_reconcile_journal SET operation_id='foreign-op'")
        db.commit(); db.close()
        _expect(f,"JOURNAL_STATE_CONFLICT")

    with tempfile.TemporaryDirectory(prefix="pending-check-activity-") as tmp:
        f=fixture(tmp); f["store"].finish(OPERATION_ID, result_state="RECONCILE_PENDING",
            removed_entries=[f["media"].name], remaining_entries=[], nas_delete_complete=True,
            discovery_reconciled=False, jellyfin_reconciled=None)
        try:
            check_operation(OPERATION_ID, DVD_ID, discovery_db=f["db_path"],
                provenance_db=f["provenance_path"], activity_check=lambda _dvd:"ACTIVE_ORGANIZER",
                nas_directory_absent=lambda _dvd,_relative:True)
        except CheckError as exc: assert exc.code == "ACTIVITY_CONFLICT"
        else: raise AssertionError("active target accepted")

    with tempfile.TemporaryDirectory(prefix="pending-check-nas-") as tmp:
        f=fixture(tmp); f["store"].finish(OPERATION_ID, result_state="RECONCILE_PENDING",
            removed_entries=[f["media"].name], remaining_entries=[], nas_delete_complete=True,
            discovery_reconciled=False, jellyfin_reconciled=None)
        try:
            check_operation(OPERATION_ID, DVD_ID, discovery_db=f["db_path"],
                provenance_db=f["provenance_path"], activity_check=lambda _dvd:"IDLE",
                nas_directory_absent=lambda _dvd,_relative:False)
        except CheckError as exc: assert exc.code == "NAS_TITLE_DIRECTORY_PRESENT"
        else: raise AssertionError("present NAS title directory accepted")

    with tempfile.TemporaryDirectory(prefix="pending-check-holding-") as tmp:
        f=fixture(tmp); f["store"].finish(OPERATION_ID, result_state="RECONCILE_PENDING",
            removed_entries=[f["media"].name], remaining_entries=[], nas_delete_complete=True,
            discovery_reconciled=False, jellyfin_reconciled=None)
        db=sqlite3.connect(f["db_path"]); db.execute("UPDATE holdings SET present=0 WHERE holding_id=?",(f["mark"]["holding_id"],)); db.commit(); db.close()
        _expect(f,"JOURNAL_STATE_CONFLICT")

    with tempfile.TemporaryDirectory(prefix="pending-check-state-") as tmp:
        f=fixture(tmp); f["store"].finish(OPERATION_ID, result_state="COMMITTED",
            removed_entries=[f["media"].name], remaining_entries=[], nas_delete_complete=True,
            discovery_reconciled=True, jellyfin_reconciled=True)
        _expect(f,"OPERATION_STATE_CHANGED")

    with tempfile.TemporaryDirectory(prefix="pending-check-duplicate-") as tmp:
        f=fixture(tmp); f["store"].finish(OPERATION_ID, result_state="RECONCILE_PENDING",
            removed_entries=[f["media"].name], remaining_entries=[], nas_delete_complete=True,
            discovery_reconciled=False, jellyfin_reconciled=None)
        db=sqlite3.connect(f["db_path"])
        db.execute("INSERT INTO holdings(storage_root,relative_path,dvd_id,parse_status,size_bytes,mtime_ns,discovered_by,present) VALUES('jav','ABCD/ABCD-123/duplicate.mp4','ABCD-123','MATCHED',1,2,'fixture',1)")
        db.commit(); db.close()
        _expect(f,"DUPLICATE_HOLDING")

    print("Stage13-F2M-C2 exact check-only helper smoke: OK")


if __name__ == "__main__":
    main()
