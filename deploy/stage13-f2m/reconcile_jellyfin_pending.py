#!/usr/bin/env python3
"""Check/apply Jellyfin reconciliation for the one completed VEMA-246 delete."""
from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import sys

from teddy_discovery_completion_ssh import CompletionSSH
from teddy_discovery_jellyfin import JellyfinClient, jellyfin_media_path
from teddy_discovery_operation_lock import (
    DEFAULT_OPERATION_LOCK_PATH, OperationLockBusy, OperationLockError, operation_lock,
)
from teddy_library_delete_activity import (
    ACTIVE_ORGANIZER, ACTIVE_SUBTITLE, IDLE, DeleteTargetActivityGuard,
    OrganizerActivitySource, SubtitleActivitySource,
)
from teddy_library_delete_commit import JellyfinDeleteReconciler, canonical_media_path, utc_now
from teddy_library_delete_dryrun import canonical_manifest, source_identity_fingerprint
from teddy_library_discovery_writer import JOURNAL_COLUMNS, JOURNAL_TABLE
from teddy_title_exclusion import ACQUIRED, BUSY, try_acquire_title_lock

DISCOVERY_DB = "/opt/missav-dlp-web/discovery/teddy-discovery.sqlite3"
PROVENANCE_DB = "/opt/missav-dlp-web/work/teddy-library-delete-provenance.sqlite3"
ROLLOUT_DB = "/opt/missav-dlp-web/discovery/stage12-rollout-state.sqlite3"
HEARTBEAT_PATH = "/opt/missav-dlp-web/discovery/stage12-runtime/status.json"
NAS_LIBRARY_ROOT = "/volume1/video/video2/JAV"
TITLE_LOCK_DIR = "/opt/missav-dlp-web/title-locks"
EXPECTED_OPERATION = "e8b5ba23-cb6d-4e5e-81f6-c1e5fdb79873"
EXPECTED_DVD = "VEMA-246"
EXPECTED_HOLDING = 20
EXPECTED_MANIFEST = "121aefa01eb2d6cd9ae6b99695892cf4652aa4b33d50e65a4c3208b6ef3c8677"
EXPECTED_NAMES = {"VEMA-246.ko.srt", "VEMA-246.mp4", "movie.nfo", "poster.webp"}
EXPECTED_BYTES = 2844317586


class RecoveryError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _ro(path: str) -> sqlite3.Connection:
    db=sqlite3.connect(Path(path).resolve().as_uri()+"?mode=ro",uri=True,timeout=3.0)
    db.row_factory=sqlite3.Row; db.execute("PRAGMA busy_timeout=3000"); db.execute("PRAGMA query_only=ON")
    return db


def _dependencies(environ=None):
    env=os.environ if environ is None else environ
    nas_names=("TEDDY_NAS_HOST","TEDDY_NAS_USER","TEDDY_NAS_KEY","TEDDY_NAS_KNOWN_HOSTS")
    if not all(env.get(name) for name in nas_names): raise RecoveryError("NAS_CONFIG_UNAVAILABLE")
    if not env.get("TEDDY_JELLYFIN_URL") or not env.get("TEDDY_JELLYFIN_KEY"):
        raise RecoveryError("JELLYFIN_CONFIG_UNAVAILABLE")
    ssh=CompletionSSH(host=env[nas_names[0]],user=env[nas_names[1]],key=env[nas_names[2]],
        known_hosts=env[nas_names[3]],downloads_root="/",library_root=NAS_LIBRARY_ROOT)
    client=JellyfinClient(base_url=env["TEDDY_JELLYFIN_URL"],api_key_path=env["TEDDY_JELLYFIN_KEY"])
    return ssh,client


def _nas_absent(ssh,relative):
    title=PurePosixPath(NAS_LIBRARY_ROOT)/PurePosixPath(relative).parent
    script='''import os,stat,sys\np=sys.argv[1]\ntry: s=os.lstat(p)\nexcept FileNotFoundError: print("ABSENT"); raise SystemExit(0)\nif stat.S_ISLNK(s.st_mode) or not stat.S_ISDIR(s.st_mode): print("UNSAFE")\nelse: print("PRESENT")'''
    result=ssh._run_python(script,title.as_posix()).strip()
    if result=="ABSENT": return True
    if result=="PRESENT": return False
    raise RecoveryError("NAS_PROBE_UNAVAILABLE")


def check_operation(operation_id, expected_dvd_id, *, discovery_db=DISCOVERY_DB,
                    provenance_db=PROVENANCE_DB, ssh=None, jellyfin_client=None,
                    activity_check=None):
    if operation_id!=EXPECTED_OPERATION or expected_dvd_id!=EXPECTED_DVD:
        raise RecoveryError("OPERATION_NOT_ALLOWLISTED")
    if ssh is None or jellyfin_client is None:
        ssh,jellyfin_client=_dependencies()
    try:
        with closing(_ro(provenance_db)) as db:
            p=db.execute("""SELECT operation_id,dvd_id,holding_id,source_identity_fingerprint,
                manifest_sha256,file_count,total_bytes,manifest_entries_json,removed_entries_json,
                remaining_entries_json,removed_file_count,removed_total_bytes,nas_delete_complete,
                discovery_reconciled,jellyfin_reconciled,result_state FROM library_deletions
                WHERE operation_id=?""",(operation_id,)).fetchone()
            if p is None: raise RecoveryError("PROVENANCE_NOT_FOUND")
            p=dict(p)
    except RecoveryError: raise
    except Exception as exc: raise RecoveryError("PROVENANCE_UNAVAILABLE") from exc
    if (p["dvd_id"]!=EXPECTED_DVD or p["holding_id"]!=EXPECTED_HOLDING
        or p["result_state"]!="RECONCILE_PENDING" or p["nas_delete_complete"]!=1
        or p["discovery_reconciled"]!=1 or p["jellyfin_reconciled"] not in (None,0)):
        raise RecoveryError("OPERATION_STATE_CHANGED")
    try:
        entries=json.loads(p["manifest_entries_json"])
        removed=json.loads(p["removed_entries_json"])
        remaining=json.loads(p["remaining_entries_json"])
        normalized,digest,total=canonical_manifest(entries)
        names={entry["relative_name"] for entry in normalized}
    except Exception as exc: raise RecoveryError("PROVENANCE_NOT_READY") from exc
    if (digest!=EXPECTED_MANIFEST or p["manifest_sha256"]!=EXPECTED_MANIFEST
        or total!=EXPECTED_BYTES or p["total_bytes"]!=EXPECTED_BYTES
        or p["file_count"]!=4 or p["removed_file_count"]!=4
        or p["removed_total_bytes"]!=EXPECTED_BYTES or names!=EXPECTED_NAMES
        or set(removed)!=EXPECTED_NAMES or len(removed)!=4 or remaining!=[]):
        raise RecoveryError("PROVENANCE_NOT_READY")
    try:
        with closing(_ro(discovery_db)) as db:
            h=db.execute("""SELECT holding_id,storage_root,relative_path,dvd_id,parse_status,
                present,size_bytes,mtime_ns FROM holdings WHERE holding_id=?""",(EXPECTED_HOLDING,)).fetchone()
            if h is None: raise RecoveryError("HOLDING_NOT_FOUND")
            h=dict(h)
            if (h["dvd_id"]!=EXPECTED_DVD or h["storage_root"]!="jav"
                or h["parse_status"]!="MATCHED" or h["present"]!=0):
                raise RecoveryError("HOLDING_CHANGED")
            relative=canonical_media_path(h,EXPECTED_DVD)
            identity=dict(h); identity["present"]=1
            fingerprint=source_identity_fingerprint(identity,relative)
            if relative!=h["relative_path"] or fingerprint!=p["source_identity_fingerprint"]:
                raise RecoveryError("HOLDING_CHANGED")
            if db.execute("SELECT COUNT(*) FROM holdings WHERE dvd_id=? AND storage_root='jav' AND present=1",(EXPECTED_DVD,)).fetchone()[0]!=0:
                raise RecoveryError("DUPLICATE_HOLDING")
            exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(JOURNAL_TABLE,)).fetchone()
            if not exists: raise RecoveryError("JOURNAL_NOT_FOUND")
            cols=tuple(row[1] for row in db.execute(f"PRAGMA table_info({JOURNAL_TABLE})").fetchall())
            if cols!=JOURNAL_COLUMNS: raise RecoveryError("JOURNAL_SCHEMA_INVALID")
            journals=db.execute(f"SELECT operation_id,dvd_id,holding_id,source_identity_fingerprint FROM {JOURNAL_TABLE} WHERE operation_id=? OR holding_id=? OR dvd_id=?",(operation_id,EXPECTED_HOLDING,EXPECTED_DVD)).fetchall()
            if (len(journals)!=1 or journals[0]["operation_id"]!=operation_id
                or journals[0]["dvd_id"]!=EXPECTED_DVD or journals[0]["holding_id"]!=EXPECTED_HOLDING
                or journals[0]["source_identity_fingerprint"]!=fingerprint):
                raise RecoveryError("JOURNAL_STATE_CONFLICT")
    except RecoveryError: raise
    except Exception as exc: raise RecoveryError("DISCOVERY_UNAVAILABLE") from exc
    if activity_check is None:
        activity_check=DeleteTargetActivityGuard(OrganizerActivitySource(discovery_db),
            SubtitleActivitySource(ROLLOUT_DB,HEARTBEAT_PATH)).check
    try: activity=activity_check(EXPECTED_DVD)
    except Exception as exc: raise RecoveryError("ACTIVITY_UNAVAILABLE") from exc
    status=getattr(activity,"status",activity)
    if status!=IDLE:
        raise RecoveryError("ACTIVITY_CONFLICT" if status in {ACTIVE_ORGANIZER,ACTIVE_SUBTITLE} else "ACTIVITY_UNAVAILABLE")
    if not _nas_absent(ssh,relative): raise RecoveryError("NAS_TITLE_DIRECTORY_PRESENT")
    media_path=jellyfin_media_path(relative)
    try:
        reconciler=JellyfinDeleteReconciler(jellyfin_client,timeout=0)
        matches=reconciler._matches(media_path)
    except Exception as exc: raise RecoveryError("JELLYFIN_QUERY_FAILED") from exc
    if len(matches)>1: raise RecoveryError("JELLYFIN_PATH_AMBIGUOUS")
    return {"operation_id":operation_id,"dvd_id":EXPECTED_DVD,"holding_id":EXPECTED_HOLDING,
        "source_identity_fingerprint":fingerprint,"manifest_sha256":digest,"file_count":4,
        "total_bytes":total,"relative_path":relative,"jellyfin_item_count":len(matches)}


def _finalize_provenance(provenance_db,checked):
    uri=Path(provenance_db).resolve().as_uri()+"?mode=rw"
    db=None
    try:
        db=sqlite3.connect(uri,uri=True,timeout=3.0,isolation_level=None); db.execute("PRAGMA busy_timeout=3000")
        db.execute("BEGIN IMMEDIATE")
        cursor=db.execute("""UPDATE library_deletions SET result_state='COMMITTED',jellyfin_reconciled=1,finished_at=?
            WHERE operation_id=? AND dvd_id=? AND holding_id=? AND source_identity_fingerprint=?
              AND manifest_sha256=? AND result_state='RECONCILE_PENDING' AND nas_delete_complete=1
              AND discovery_reconciled=1 AND (jellyfin_reconciled IS NULL OR jellyfin_reconciled=0)
              AND file_count=4 AND total_bytes=? AND removed_file_count=4 AND removed_total_bytes=?
              AND remaining_entries_json='[]'""",(utc_now(),checked["operation_id"],checked["dvd_id"],
              checked["holding_id"],checked["source_identity_fingerprint"],checked["manifest_sha256"],
              EXPECTED_BYTES,EXPECTED_BYTES))
        if cursor.rowcount!=1:
            db.execute("ROLLBACK"); raise RecoveryError("PROVENANCE_CONFLICT")
        db.execute("COMMIT")
    except RecoveryError: raise
    except sqlite3.OperationalError as exc:
        if db is not None and db.in_transaction: db.execute("ROLLBACK")
        raise RecoveryError("DB_BUSY" if "locked" in str(exc).lower() or "busy" in str(exc).lower() else "PROVENANCE_UNAVAILABLE") from exc
    except Exception as exc:
        if db is not None and db.in_transaction: db.execute("ROLLBACK")
        raise RecoveryError("PROVENANCE_UNAVAILABLE") from exc
    finally:
        if db is not None: db.close()


def apply_operation(operation_id, expected_dvd_id, *, discovery_db=DISCOVERY_DB,
                    provenance_db=PROVENANCE_DB, title_lock_dir=TITLE_LOCK_DIR,
                    check_fn=check_operation, ssh=None, jellyfin_client=None,
                    activity_check=None, title_lock_fn=try_acquire_title_lock,
                    global_lock_fn=operation_lock, global_lock_path=DEFAULT_OPERATION_LOCK_PATH,
                    reconciler_factory=JellyfinDeleteReconciler):
    kwargs={"ssh":ssh,"jellyfin_client":jellyfin_client,"activity_check":activity_check}
    try: before=check_fn(operation_id,expected_dvd_id,discovery_db=discovery_db,provenance_db=provenance_db,**kwargs)
    except RecoveryError: raise
    except Exception as exc: raise RecoveryError("CHECK_UNAVAILABLE") from exc
    lock=title_lock_fn(expected_dvd_id,title_lock_dir)
    if getattr(lock,"status",None)!=ACQUIRED:
        raise RecoveryError("TITLE_LOCK_BUSY" if getattr(lock,"status",None)==BUSY else "TITLE_LOCK_UNAVAILABLE")
    try:
        try:
            with global_lock_fn(global_lock_path):
                try: checked=check_fn(operation_id,expected_dvd_id,discovery_db=discovery_db,provenance_db=provenance_db,**kwargs)
                except RecoveryError: raise
                except Exception as exc: raise RecoveryError("CHECK_UNAVAILABLE") from exc
                if checked["manifest_sha256"]!=before["manifest_sha256"] or checked["jellyfin_item_count"]!=before["jellyfin_item_count"]:
                    raise RecoveryError("OPERATION_STATE_CHANGED")
                client=jellyfin_client
                if client is None: _,client=_dependencies()
                try:
                    reconciler=reconciler_factory(client)
                    if checked["jellyfin_item_count"]==1:
                        if not reconciler(checked["relative_path"]):
                            return {"status":"RECONCILE_PENDING","deleted_notifications":1,"poll_complete":False}
                    # Re-read exact path after notification, or skip POST when already absent.
                    final_matches=reconciler._matches(jellyfin_media_path(checked["relative_path"]))
                except Exception as exc:
                    raise RecoveryError("JELLYFIN_RECONCILE_FAILED") from exc
                if final_matches:
                    if len(final_matches)>1: raise RecoveryError("JELLYFIN_PATH_AMBIGUOUS")
                    return {"status":"RECONCILE_PENDING","deleted_notifications":checked["jellyfin_item_count"],"poll_complete":False}
                _finalize_provenance(provenance_db,checked)
                return {"status":"COMMITTED","deleted_notifications":checked["jellyfin_item_count"],"poll_complete":True}
        except OperationLockBusy as exc: raise RecoveryError("GLOBAL_LOCK_BUSY") from exc
        except OperationLockError as exc: raise RecoveryError("GLOBAL_LOCK_UNAVAILABLE") from exc
    finally:
        lock.release()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check-only",action="store_true")
    modes.add_argument("--apply",action="store_true")
    parser.add_argument("--operation-id",required=True)
    parser.add_argument("--expected-dvd-id",required=True)
    args=parser.parse_args(argv)
    try:
        ssh,client=_dependencies()
        if args.check_only:
            checked=check_operation(args.operation_id,args.expected_dvd_id,ssh=ssh,jellyfin_client=client)
            print("JELLYFIN_RECOVERY_ELIGIBLE=YES")
            print("EXACT_ITEM_COUNT="+str(checked["jellyfin_item_count"]))
            return 0
        lock_dir=os.environ.get("TEDDY_TITLE_LOCK_DIR") or TITLE_LOCK_DIR
        result=apply_operation(args.operation_id,args.expected_dvd_id,title_lock_dir=lock_dir,ssh=ssh,jellyfin_client=client)
        print("JELLYFIN_APPLY="+result["status"])
        print("DELETED_NOTIFICATION_POSTS="+str(result["deleted_notifications"]))
        print("POLL_COMPLETE="+str(result["poll_complete"]))
        return 0 if result["status"]=="COMMITTED" else 3
    except RecoveryError as exc:
        print("JELLYFIN_RECOVERY_ELIGIBLE=NO" if args.check_only else "JELLYFIN_APPLY=REFUSED")
        print("SAFE_CODE="+exc.code)
        return 2
    except Exception:
        print("JELLYFIN_RECOVERY_ELIGIBLE=NO" if args.check_only else "JELLYFIN_APPLY=REFUSED")
        print("SAFE_CODE=RECOVERY_UNAVAILABLE")
        return 2


if __name__=="__main__":
    raise SystemExit(main())
