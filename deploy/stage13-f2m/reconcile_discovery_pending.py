#!/usr/bin/env python3
"""Read-only eligibility check for one durable pending Discovery reconcile.

This tool deliberately has no apply mode. It never calls the writer mutation
operation, creates provenance, or changes either SQLite database.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import sys

from teddy_discovery_completion_ssh import CompletionSSH
from teddy_library_delete_activity import (
    ACTIVE_ORGANIZER, ACTIVE_SUBTITLE, IDLE, DeleteTargetActivityGuard,
    OrganizerActivitySource, SubtitleActivitySource,
)
from teddy_library_delete_commit import canonical_media_path
from teddy_library_delete_dryrun import canonical_manifest, source_identity_fingerprint
from teddy_library_discovery_writer import JOURNAL_COLUMNS, JOURNAL_TABLE


DISCOVERY_DB = "/opt/missav-dlp-web/discovery/teddy-discovery.sqlite3"
PROVENANCE_DB = "/opt/missav-dlp-web/work/teddy-library-delete-provenance.sqlite3"
ROLLOUT_DB = "/opt/missav-dlp-web/discovery/stage12-rollout-state.sqlite3"
HEARTBEAT_PATH = "/opt/missav-dlp-web/discovery/stage12-runtime/status.json"
NAS_LIBRARY_ROOT = "/volume1/video/video2/JAV"


class CheckError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _ro(path: str | Path) -> sqlite3.Connection:
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    db = sqlite3.connect(uri, uri=True, timeout=3.0)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=3000")
    db.execute("PRAGMA query_only=ON")
    return db


def check_operation(operation_id: str, expected_dvd_id: str, *,
                    discovery_db: str | Path = DISCOVERY_DB,
                    provenance_db: str | Path = PROVENANCE_DB,
                    activity_check=None, nas_directory_absent=None) -> dict:
    """Validate one pending operation using read-only stores and probes."""
    if (not isinstance(operation_id, str) or not operation_id
            or len(operation_id) > 64
            or not all(c.isalnum() or c == "-" for c in operation_id)):
        raise CheckError("OPERATION_ID_INVALID")
    if (not isinstance(expected_dvd_id, str) or not expected_dvd_id
            or len(expected_dvd_id) > 32
            or any(not (c.isupper() or c.isdigit() or c == "-") for c in expected_dvd_id)):
        raise CheckError("DVD_ID_INVALID")

    try:
        with closing(_ro(provenance_db)) as db:
            db.execute("PRAGMA query_only=ON")
            row = db.execute(
                "SELECT operation_id,dvd_id,holding_id,source_identity_fingerprint,"
                "manifest_sha256,file_count,total_bytes,manifest_entries_json,"
                "removed_entries_json,remaining_entries_json,removed_file_count,"
                "removed_total_bytes,nas_delete_complete,discovery_reconciled,"
                "jellyfin_reconciled,result_state FROM library_deletions WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if row is None:
                raise CheckError("PROVENANCE_NOT_FOUND")
            provenance = dict(row)
    except CheckError:
        raise
    except (OSError, sqlite3.Error, ValueError) as exc:
        raise CheckError("PROVENANCE_UNAVAILABLE") from exc

    if provenance["dvd_id"] != expected_dvd_id:
        raise CheckError("OPERATION_MISMATCH")
    if (provenance["result_state"] != "RECONCILE_PENDING"
            or provenance["nas_delete_complete"] != 1
            or provenance["discovery_reconciled"] != 0
            or provenance["jellyfin_reconciled"] is not None):
        raise CheckError("OPERATION_STATE_CHANGED")
    if (int(provenance["holding_id"]) <= 0
            or int(provenance["file_count"]) <= 0
            or int(provenance["removed_file_count"]) != int(provenance["file_count"])):
        raise CheckError("PROVENANCE_NOT_READY")
    try:
        manifest_entries = json.loads(provenance["manifest_entries_json"])
        removed_entries = json.loads(provenance["removed_entries_json"])
        remaining_entries = json.loads(provenance["remaining_entries_json"])
        normalized, digest, total = canonical_manifest(manifest_entries)
    except Exception as exc:
        raise CheckError("PROVENANCE_NOT_READY") from exc
    names = [entry["relative_name"] for entry in normalized]
    if (digest != provenance["manifest_sha256"]
            or total != int(provenance["total_bytes"])
            or int(provenance["removed_total_bytes"]) != total
            or len(names) != int(provenance["file_count"])
            or not isinstance(removed_entries, list)
            or len(removed_entries) != len(names)
            or len(set(removed_entries)) != len(removed_entries)
            or set(removed_entries) != set(names)
            or remaining_entries != []):
        raise CheckError("PROVENANCE_NOT_READY")

    try:
        with closing(_ro(discovery_db)) as db:
            db.execute("PRAGMA query_only=ON")
            held = db.execute(
                "SELECT holding_id,storage_root,relative_path,dvd_id,parse_status,"
                "present,size_bytes,mtime_ns FROM holdings WHERE holding_id=?",
                (int(provenance["holding_id"]),),
            ).fetchone()
            if held is None:
                raise CheckError("HOLDING_NOT_FOUND")
            holding = dict(held)
            if (holding["dvd_id"] != expected_dvd_id or holding["storage_root"] != "jav"
                    or holding["parse_status"] != "MATCHED"
                    or holding["present"] not in (0, 1)):
                raise CheckError("HOLDING_CHANGED")
            relative = canonical_media_path(holding, expected_dvd_id)
            fingerprint_identity = dict(holding)
            # The delete fingerprint is bound to the pre-delete present holding;
            # preserve that identity when inspecting the journal recovery phase.
            fingerprint_identity["present"] = 1
            current_fingerprint = source_identity_fingerprint(fingerprint_identity, relative)
            if (relative != holding["relative_path"]
                    or current_fingerprint != provenance["source_identity_fingerprint"]):
                raise CheckError("HOLDING_CHANGED")
            count = db.execute(
                "SELECT COUNT(*) FROM holdings WHERE dvd_id=? AND storage_root='jav' AND present=1",
                (expected_dvd_id,),
            ).fetchone()[0]
            if ((holding["present"] == 1 and count != 1)
                    or (holding["present"] == 0 and count != 0)):
                raise CheckError("DUPLICATE_HOLDING")
            journal_rows = []
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (JOURNAL_TABLE,),
            ).fetchone()
            if exists:
                columns = tuple(row[1] for row in db.execute(
                    f"PRAGMA table_info({JOURNAL_TABLE})").fetchall())
                if columns != JOURNAL_COLUMNS:
                    raise CheckError("JOURNAL_SCHEMA_INVALID")
                journal_rows = db.execute(
                    f"SELECT operation_id,dvd_id,holding_id,source_identity_fingerprint "
                    f"FROM {JOURNAL_TABLE} WHERE operation_id=? OR holding_id=? OR dvd_id=?",
                    (operation_id, int(provenance["holding_id"]), expected_dvd_id),
                ).fetchall()
            exact_journal = (
                len(journal_rows) == 1
                and journal_rows[0]["operation_id"] == operation_id
                and journal_rows[0]["dvd_id"] == expected_dvd_id
                and int(journal_rows[0]["holding_id"]) == int(provenance["holding_id"])
                and journal_rows[0]["source_identity_fingerprint"] == current_fingerprint
            )
            if holding["present"] == 1:
                if journal_rows:
                    raise CheckError("JOURNAL_STATE_CONFLICT")
                phase = "READY_TO_MARK_ABSENT"
            else:
                if not exact_journal:
                    raise CheckError("JOURNAL_STATE_CONFLICT")
                phase = "WRITER_DONE_PROVENANCE_PENDING"
    except CheckError:
        raise
    except Exception as exc:
        raise CheckError("DISCOVERY_UNAVAILABLE") from exc

    if activity_check is None:
        activity_check = DeleteTargetActivityGuard(
            OrganizerActivitySource(discovery_db),
            SubtitleActivitySource(ROLLOUT_DB, HEARTBEAT_PATH),
        ).check
    try:
        activity = activity_check(expected_dvd_id)
    except Exception as exc:
        raise CheckError("ACTIVITY_UNAVAILABLE") from exc
    activity_status = getattr(activity, "status", activity)
    if activity_status != IDLE:
        if activity_status in {ACTIVE_ORGANIZER, ACTIVE_SUBTITLE}:
            raise CheckError("ACTIVITY_CONFLICT")
        raise CheckError("ACTIVITY_UNAVAILABLE")

    if nas_directory_absent is None:
        raise CheckError("NAS_PROBE_UNAVAILABLE")
    try:
        if not nas_directory_absent(expected_dvd_id, relative):
            raise CheckError("NAS_TITLE_DIRECTORY_PRESENT")
    except CheckError:
        raise
    except Exception as exc:
        raise CheckError("NAS_PROBE_UNAVAILABLE") from exc

    return {
        "status": "RECOVERY_ELIGIBLE",
        "operation_id": operation_id,
        "dvd_id": expected_dvd_id,
        "holding_id": int(provenance["holding_id"]),
        "manifest_sha256": digest,
        "file_count": len(names),
        "total_bytes": total,
        "relative_path": relative,
        "source_identity_fingerprint": current_fingerprint,
        "recovery_phase": phase,
    }


def _nas_absent_probe(ssh: CompletionSSH, relative: str) -> bool:
    title_dir = PurePosixPath(NAS_LIBRARY_ROOT) / PurePosixPath(relative).parent
    script = r'''import json,os,stat,sys
p=sys.argv[1]
try: st=os.lstat(p)
except FileNotFoundError:
 print("ABSENT"); raise SystemExit(0)
if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
 print("UNSAFE"); raise SystemExit(0)
print("PRESENT")'''
    result = ssh._run_python(script, title_dir.as_posix()).strip()
    if result == "ABSENT":
        return True
    if result == "PRESENT":
        return False
    raise RuntimeError("NAS exact path unsafe or probe invalid")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true", required=True)
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--expected-dvd-id", required=True)
    args = parser.parse_args(argv)
    try:
        required = ("TEDDY_NAS_HOST", "TEDDY_NAS_USER", "TEDDY_NAS_KEY", "TEDDY_NAS_KNOWN_HOSTS")
        if not all(os.environ.get(name) for name in required):
            raise CheckError("NAS_CONFIG_UNAVAILABLE")
        ssh = CompletionSSH(
            host=os.environ["TEDDY_NAS_HOST"], user=os.environ["TEDDY_NAS_USER"],
            key=os.environ["TEDDY_NAS_KEY"], known_hosts=os.environ["TEDDY_NAS_KNOWN_HOSTS"],
            downloads_root="/", library_root=NAS_LIBRARY_ROOT,
        )
        result = check_operation(
            args.operation_id, args.expected_dvd_id,
            nas_directory_absent=lambda dvd, relative: _nas_absent_probe(ssh, relative),
        )
        print("RECOVERY_ELIGIBLE=YES")
        print("RECOVERY_PHASE=" + result["recovery_phase"])
        print("OPERATION_ID=" + result["operation_id"])
        print("DVD_ID=" + result["dvd_id"])
        print("HOLDING_ID=" + str(result["holding_id"]))
        print("FILE_COUNT=" + str(result["file_count"]))
        print("TOTAL_BYTES=" + str(result["total_bytes"]))
        return 0
    except CheckError as exc:
        print("RECOVERY_ELIGIBLE=NO")
        print("SAFE_CODE=" + exc.code)
        return 2
    except Exception:
        print("RECOVERY_ELIGIBLE=NO")
        print("SAFE_CODE=CHECK_UNAVAILABLE")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
