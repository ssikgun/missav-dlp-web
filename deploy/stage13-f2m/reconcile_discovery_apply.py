#!/usr/bin/env python3
"""Apply Discovery reconciliation for an already completed exact delete.

This operator helper cannot start deletion, touch NAS contents, or contact
Jellyfin. Its sole durable effects are the narrow writer transition and the
conditional provenance discovery_reconciled flag.
"""
from __future__ import annotations

import argparse
from contextlib import closing, nullcontext
import os
import sqlite3
import sys

from teddy_discovery_operation_lock import (
    DEFAULT_OPERATION_LOCK_PATH, OperationLockBusy, OperationLockError,
    operation_lock,
)
from teddy_library_discovery_writer import (
    JOURNAL_COLUMNS, JOURNAL_TABLE, UnixSocketDiscoveryWriterClient, WriterError,
)
from teddy_title_exclusion import ACQUIRED, BUSY, try_acquire_title_lock
from reconcile_discovery_pending import (
    CheckError, DISCOVERY_DB, PROVENANCE_DB, check_operation,
)

WRITER_SOCKET = "/run/teddy-library-discovery-writer/writer.sock"
TITLE_LOCK_DIR = "/opt/missav-dlp-web/title-locks"


class ApplyError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _verify_writer_result(phase: str, result: dict) -> str:
    expected = "RECONCILED" if phase == "READY_TO_MARK_ABSENT" else "ALREADY_RECONCILED"
    status = result.get("status") if isinstance(result, dict) else None
    if status != expected:
        raise ApplyError("WRITER_RESULT_MISMATCH")
    return status


def _verify_discovery(discovery_db: str, checked: dict) -> None:
    uri = "file:" + os.path.abspath(discovery_db) + "?mode=ro"
    try:
        with closing(sqlite3.connect(uri, uri=True, timeout=3.0)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA busy_timeout=3000")
            db.execute("PRAGMA query_only=ON")
            row = db.execute(
                "SELECT holding_id,dvd_id,storage_root,relative_path,parse_status,present,"
                "size_bytes,mtime_ns FROM holdings WHERE holding_id=?",
                (checked["holding_id"],),
            ).fetchone()
            if (row is None or row["dvd_id"] != checked["dvd_id"]
                    or row["storage_root"] != "jav"
                    or row["relative_path"] != checked["relative_path"]
                    or row["parse_status"] != "MATCHED" or row["present"] != 0):
                raise ApplyError("DISCOVERY_VERIFY_FAILED")
            count = db.execute(
                "SELECT COUNT(*) FROM holdings WHERE dvd_id=? AND storage_root='jav' AND present=1",
                (checked["dvd_id"],),
            ).fetchone()[0]
            if count != 0:
                raise ApplyError("DISCOVERY_VERIFY_FAILED")
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (JOURNAL_TABLE,),
            ).fetchone()
            if not exists:
                raise ApplyError("JOURNAL_VERIFY_FAILED")
            columns = tuple(row[1] for row in db.execute(
                f"PRAGMA table_info({JOURNAL_TABLE})").fetchall())
            if columns != JOURNAL_COLUMNS:
                raise ApplyError("JOURNAL_VERIFY_FAILED")
            journals = db.execute(
                f"SELECT operation_id,dvd_id,holding_id,source_identity_fingerprint "
                f"FROM {JOURNAL_TABLE} WHERE operation_id=? OR holding_id=? OR dvd_id=?",
                (checked["operation_id"], checked["holding_id"], checked["dvd_id"]),
            ).fetchall()
            if (len(journals) != 1
                    or journals[0]["operation_id"] != checked["operation_id"]
                    or journals[0]["dvd_id"] != checked["dvd_id"]
                    or int(journals[0]["holding_id"]) != checked["holding_id"]
                    or journals[0]["source_identity_fingerprint"] != checked["source_identity_fingerprint"]):
                raise ApplyError("JOURNAL_VERIFY_FAILED")
    except ApplyError:
        raise
    except (OSError, sqlite3.Error) as exc:
        raise ApplyError("DISCOVERY_UNAVAILABLE") from exc


def _mark_provenance_discovery_reconciled(provenance_db: str, checked: dict) -> None:
    uri = "file:" + os.path.abspath(provenance_db) + "?mode=rw"
    db = None
    try:
        db = sqlite3.connect(uri, uri=True, timeout=3.0, isolation_level=None)
        with closing(db):
            db.execute("PRAGMA busy_timeout=3000")
            db.execute("BEGIN IMMEDIATE")
            cursor = db.execute("""UPDATE library_deletions
                SET discovery_reconciled=1
                WHERE operation_id=? AND dvd_id=? AND holding_id=?
                  AND source_identity_fingerprint=? AND manifest_sha256=?
                  AND result_state='RECONCILE_PENDING' AND nas_delete_complete=1
                  AND discovery_reconciled=0 AND jellyfin_reconciled IS NULL
                  AND file_count=? AND total_bytes=? AND removed_file_count=?
                  AND removed_total_bytes=? AND remaining_entries_json='[]'""",
                (checked["operation_id"], checked["dvd_id"], checked["holding_id"],
                 checked["source_identity_fingerprint"], checked["manifest_sha256"],
                 checked["file_count"], checked["total_bytes"], checked["file_count"],
                 checked["total_bytes"]))
            if cursor.rowcount != 1:
                db.execute("ROLLBACK")
                raise ApplyError("PROVENANCE_CONFLICT")
            db.execute("COMMIT")
    except ApplyError:
        raise
    except sqlite3.OperationalError as exc:
        try:
            if db is not None and db.in_transaction:
                db.execute("ROLLBACK")
        except Exception:
            pass
        code = "DB_BUSY" if "locked" in str(exc).lower() or "busy" in str(exc).lower() else "PROVENANCE_UNAVAILABLE"
        raise ApplyError(code) from exc
    except (OSError, sqlite3.Error) as exc:
        raise ApplyError("PROVENANCE_UNAVAILABLE") from exc


def apply_operation(operation_id: str, expected_dvd_id: str, *,
                    discovery_db: str = DISCOVERY_DB,
                    provenance_db: str = PROVENANCE_DB,
                    writer_socket: str = WRITER_SOCKET,
                    title_lock_dir: str = TITLE_LOCK_DIR,
                    check_fn=check_operation,
                    writer_client=None,
                    title_lock_fn=try_acquire_title_lock,
                    global_lock_fn=operation_lock,
                    global_lock_path=DEFAULT_OPERATION_LOCK_PATH,
                    check_kwargs=None) -> dict:
    """Recheck, lock, and apply only the exact existing operation."""
    kwargs = dict(check_kwargs or {})
    try:
        initial = check_fn(operation_id, expected_dvd_id,
                           discovery_db=discovery_db, provenance_db=provenance_db,
                           **kwargs)
    except CheckError as exc:
        raise ApplyError(exc.code) from exc
    lock = title_lock_fn(expected_dvd_id, title_lock_dir)
    if getattr(lock, "status", None) != ACQUIRED:
        status = getattr(lock, "status", None)
        raise ApplyError("TITLE_LOCK_BUSY" if status == BUSY else "TITLE_LOCK_UNAVAILABLE")
    try:
        # Fixed order: target title lock, then existing global JAV lock.
        try:
            with global_lock_fn(global_lock_path):
                try:
                    checked = check_fn(operation_id, expected_dvd_id,
                                       discovery_db=discovery_db, provenance_db=provenance_db,
                                       **kwargs)
                except CheckError as exc:
                    raise ApplyError(exc.code) from exc
                if checked["recovery_phase"] != initial["recovery_phase"]:
                    raise ApplyError("OPERATION_STATE_CHANGED")
                if writer_client is None:
                    writer_client = UnixSocketDiscoveryWriterClient(writer_socket)
                try:
                    result = writer_client.mark_absent(
                        operation_id=operation_id, dvd_id=expected_dvd_id,
                        holding_id=checked["holding_id"],
                        source_identity_fingerprint=checked["source_identity_fingerprint"],
                    )
                except WriterError as exc:
                    raise ApplyError(exc.code) from exc
                writer_result = _verify_writer_result(checked["recovery_phase"], result)
                _verify_discovery(discovery_db, checked)
                _mark_provenance_discovery_reconciled(provenance_db, checked)
                return {"writer_result": writer_result, "recovery_phase": checked["recovery_phase"],
                        "operation_id": operation_id, "dvd_id": expected_dvd_id,
                        "holding_id": checked["holding_id"]}
        except OperationLockBusy as exc:
            raise ApplyError("GLOBAL_LOCK_BUSY") from exc
        except OperationLockError as exc:
            raise ApplyError("GLOBAL_LOCK_UNAVAILABLE") from exc
    finally:
        lock.release()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--expected-dvd-id", required=True)
    args = parser.parse_args(argv)
    try:
        if not os.environ.get("TEDDY_TITLE_LOCK_DIR"):
            raise ApplyError("TITLE_LOCK_UNAVAILABLE")
        result = apply_operation(
            args.operation_id, args.expected_dvd_id,
            title_lock_dir=os.environ["TEDDY_TITLE_LOCK_DIR"],
            check_kwargs={"nas_directory_absent": _nas_probe_from_environment()},
        )
        print("DISCOVERY_APPLY=OK")
        print("RECOVERY_PHASE=" + result["recovery_phase"])
        print("WRITER_RESULT=" + result["writer_result"])
        print("DVD_ID=" + result["dvd_id"])
        print("HOLDING_ID=" + str(result["holding_id"]))
        return 0
    except ApplyError as exc:
        print("DISCOVERY_APPLY=REFUSED")
        print("SAFE_CODE=" + exc.code)
        return 2
    except Exception:
        print("DISCOVERY_APPLY=REFUSED")
        print("SAFE_CODE=APPLY_UNAVAILABLE")
        return 2


def _nas_probe_from_environment():
    from pathlib import PurePosixPath

    from teddy_discovery_completion_ssh import CompletionSSH
    from reconcile_discovery_pending import NAS_LIBRARY_ROOT, _nas_absent_probe

    names = ("TEDDY_NAS_HOST", "TEDDY_NAS_USER", "TEDDY_NAS_KEY", "TEDDY_NAS_KNOWN_HOSTS")
    if not all(os.environ.get(name) for name in names):
        raise ApplyError("NAS_CONFIG_UNAVAILABLE")
    ssh = CompletionSSH(
        host=os.environ[names[0]], user=os.environ[names[1]], key=os.environ[names[2]],
        known_hosts=os.environ[names[3]], downloads_root="/", library_root=NAS_LIBRARY_ROOT,
    )
    return lambda _dvd, relative: _nas_absent_probe(ssh, relative)


if __name__ == "__main__":
    raise SystemExit(main())
