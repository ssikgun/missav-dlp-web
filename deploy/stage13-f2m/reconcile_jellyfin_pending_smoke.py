#!/usr/bin/env python3
"""Offline fixtures for VEMA-246 exact Jellyfin recovery and finalization."""
from __future__ import annotations

from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from teddy_discovery_jellyfin import jellyfin_media_path
from teddy_library_delete_commit import JellyfinDeleteReconciler
from teddy_library_delete_dryrun import canonical_manifest, source_identity_fingerprint
from teddy_title_exclusion import ACQUIRED, BUSY

_PATH=Path(__file__).with_name("reconcile_jellyfin_pending.py")
_SPEC=importlib.util.spec_from_file_location("reconcile_jellyfin_pending",_PATH)
_MOD=importlib.util.module_from_spec(_SPEC); _SPEC.loader.exec_module(_MOD)
RecoveryError=_MOD.RecoveryError
check_operation=_MOD.check_operation
apply_operation=_MOD.apply_operation
OP=_MOD.EXPECTED_OPERATION; DVD=_MOD.EXPECTED_DVD; HID=_MOD.EXPECTED_HOLDING
REL="VEMA/VEMA-246/VEMA-246.mp4"; PATH=jellyfin_media_path(REL)
NAMES=sorted(_MOD.EXPECTED_NAMES)


def fixture(root):
    discovery=Path(root)/"discovery.sqlite3"
    db=sqlite3.connect(discovery)
    db.executescript("""
      CREATE TABLE holdings(holding_id INTEGER PRIMARY KEY,storage_root TEXT,relative_path TEXT,dvd_id TEXT,
        parse_status TEXT,present INTEGER,size_bytes INTEGER,mtime_ns INTEGER,discovered_by TEXT);
    """)
    db.execute("INSERT INTO holdings VALUES(20,'jav',?,'VEMA-246','MATCHED',0,1000,123,'fixture')",(REL,))
    db.execute("""CREATE TABLE library_delete_reconcile_journal(operation_id TEXT PRIMARY KEY,dvd_id TEXT NOT NULL,
      holding_id INTEGER NOT NULL,source_identity_fingerprint TEXT NOT NULL,reconciled_at TEXT NOT NULL)""")
    row=dict(zip(("holding_id","storage_root","relative_path","dvd_id","parse_status","present","size_bytes","mtime_ns"),
      db.execute("SELECT holding_id,storage_root,relative_path,dvd_id,parse_status,1,size_bytes,mtime_ns FROM holdings WHERE holding_id=20").fetchone()))
    fp=source_identity_fingerprint(row,REL)
    db.execute("INSERT INTO library_delete_reconcile_journal VALUES(?,?,?,?,?)",(OP,DVD,HID,fp,"2026-01-01T00:00:00Z"))
    db.commit();db.close()
    entries=[{"relative_name":name,"size_bytes":100,"mtime_ns":123,"inode":10+i,"device":1,"file_type":"regular"} for i,name in enumerate(NAMES)]
    _normalized,digest,total=canonical_manifest(entries)
    provenance=Path(root)/"provenance.sqlite3"
    db=sqlite3.connect(provenance)
    db.execute("""CREATE TABLE library_deletions(operation_id TEXT PRIMARY KEY,dvd_id TEXT,holding_id INTEGER,
      source_identity_fingerprint TEXT,manifest_sha256 TEXT,file_count INTEGER,total_bytes INTEGER,
      manifest_entries_json TEXT,removed_entries_json TEXT,remaining_entries_json TEXT,removed_file_count INTEGER,
      removed_total_bytes INTEGER,nas_delete_complete INTEGER,discovery_reconciled INTEGER,
      jellyfin_reconciled INTEGER,result_state TEXT,finished_at TEXT)""")
    db.execute("INSERT INTO library_deletions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
      (OP,DVD,HID,fp,digest,4,total,json.dumps(entries,separators=(",",":")),json.dumps(NAMES),"[]",4,total,1,1,None,"RECONCILE_PENDING",None))
    db.commit();db.close()
    _MOD.EXPECTED_MANIFEST=digest;_MOD.EXPECTED_BYTES=total
    return {"discovery":str(discovery),"provenance":str(provenance),"fp":fp,"digest":digest,"total":total}


class SSH:
    def _run_python(self,_script,*_args): return "ABSENT\n"


class Jellyfin:
    def __init__(self,gets,exact_gets=()): self.gets=list(gets);self.exact_gets=list(exact_gets);self.posts=[]
    def _request(self,method,path):
        if method=="POST": self.posts.append(path);return None
        queue=self.exact_gets if "Ids=" in path else self.gets
        if not queue: raise AssertionError("unexpected GET: "+path)
        value=queue.pop(0)
        if isinstance(value,Exception): raise value
        return value
    def notify_deleted(self,path):
        self.posts.append({"endpoint":"/Library/Media/Updated","payload":{"Updates":[{"Path":path,"UpdateType":"Deleted"}]}})


def inv(items):return {"Items":items,"TotalRecordCount":len(items)}
def exact():return {"Id":"jf-42","Path":PATH,"ParentId":"parent"}


class Lock:
    status=ACQUIRED
    def __init__(self):self.released=False
    def release(self):self.released=True


@contextmanager
def global_ok(_path):yield


def run_check(f,jf):
    return check_operation(OP,DVD,discovery_db=f["discovery"],provenance_db=f["provenance"],
        ssh=SSH(),jellyfin_client=jf,activity_check=lambda _dvd:"IDLE")


def run_apply(f,jf,**kwargs):
    kwargs.setdefault("title_lock_fn",lambda *_a:Lock())
    return apply_operation(OP,DVD,discovery_db=f["discovery"],provenance_db=f["provenance"],
      title_lock_dir="/tmp/fixture-title-lock",check_fn=check_operation,ssh=SSH(),jellyfin_client=jf,
      activity_check=lambda _dvd:"IDLE",global_lock_fn=global_ok,
      reconciler_factory=kwargs.pop("reconciler_factory",JellyfinDeleteReconciler),**kwargs)


def state(f):
    db=sqlite3.connect(f["provenance"]);v=db.execute("SELECT result_state,jellyfin_reconciled,discovery_reconciled FROM library_deletions WHERE operation_id=?",(OP,)).fetchone();db.close();return v


def main():
    # Check-only accepts only the exact pending operation and reports the GET count.
    with tempfile.TemporaryDirectory(prefix="jf-pending-check-") as tmp:
        f=fixture(tmp);j=Jellyfin([inv([exact()])],[inv([exact()])]);r=run_check(f,j)
        assert r["jellyfin_item_count"]==1 and r["broad_item_count"]==1 and state(f)==("RECONCILE_PENDING",None,1) and not j.posts

    # One exact Deleted notification, bounded poll to zero, then strict provenance commit.
    with tempfile.TemporaryDirectory(prefix="jf-apply-post-") as tmp:
        f=fixture(tmp);j=Jellyfin([inv([exact()]),inv([exact()]),inv([exact()]),inv([]),inv([])],
          [inv([exact()]),inv([exact()]),inv([exact()]),inv([])])
        result=run_apply(f,j)
        assert result=={"status":"COMMITTED","deleted_notifications":1,
          "poll_complete":True,"jellyfin_classification":None}
        assert j.posts==[{"endpoint":"/Library/Media/Updated","payload":{"Updates":[{"Path":PATH,"UpdateType":"Deleted"}]}}]
        assert state(f)==("COMMITTED",1,1)

    # Broad inventory ghost is exact-ID absent: commit without claim or notification.
    with tempfile.TemporaryDirectory(prefix="jf-apply-ghost-") as tmp:
        f=fixture(tmp);ghost=exact()
        j=Jellyfin([inv([ghost])]*7,[inv([])]*4)
        result=run_apply(f,j)
        assert result=={"status":"COMMITTED","deleted_notifications":0,
          "poll_complete":True,"jellyfin_classification":"BROAD_INVENTORY_GHOST"}
        assert not j.posts and state(f)==("COMMITTED",1,1)
        with sqlite3.connect(f["provenance"]) as db:
            assert db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='library_delete_jellyfin_notification_attempts'").fetchone() is None

    # Already gone (including a crash after notification, before provenance commit): no POST, finalize.
    with tempfile.TemporaryDirectory(prefix="jf-apply-crash-retry-") as tmp:
        f=fixture(tmp);j=Jellyfin([inv([]),inv([]),inv([])])
        result=run_apply(f,j)
        assert result["status"]=="COMMITTED" and result["deleted_notifications"]==0 and not j.posts
        assert state(f)==("COMMITTED",1,1)

    # Deleted notification timeout leaves the exact operation pending and does not update provenance.
    with tempfile.TemporaryDirectory(prefix="jf-apply-timeout-") as tmp:
        f=fixture(tmp);one=inv([exact()]);j=Jellyfin([one,one,one],[one,one,one]+[one]*32)
        class Clock:
            value=0.0
            def now(self):return self.value
            def sleep(self,n):self.value+=n
        clock=Clock()
        factory=lambda client,**kw:JellyfinDeleteReconciler(client,timeout=6,interval=2,
            clock=clock.now,sleep=clock.sleep,**kw)
        result=run_apply(f,j,reconciler_factory=factory)
        assert result["status"]=="RECONCILE_PENDING" and result["deleted_notifications"]==1
        assert len(j.posts)==1 and state(f)==("RECONCILE_PENDING",None,1)

    # Ambiguity and lock contention fail before refresh or provenance update.
    with tempfile.TemporaryDirectory(prefix="jf-apply-ambiguous-") as tmp:
        f=fixture(tmp);j=Jellyfin([inv([exact(),dict(exact(),Id="jf-43")])])
        try:run_apply(f,j)
        except RecoveryError as exc:assert exc.code=="JELLYFIN_PATH_AMBIGUOUS"
        else:raise AssertionError("ambiguous exact path accepted")
        assert not j.posts and state(f)==("RECONCILE_PENDING",None,1)

    with tempfile.TemporaryDirectory(prefix="jf-apply-busy-") as tmp:
        f=fixture(tmp);j=Jellyfin([inv([])])
        class Busy:status=BUSY
        try:run_apply(f,j,title_lock_fn=lambda *_a:Busy())
        except RecoveryError as exc:assert exc.code=="TITLE_LOCK_BUSY"
        else:raise AssertionError("busy title accepted")
        assert not j.posts and state(f)==("RECONCILE_PENDING",None,1)

    print("Stage13-F2M-D9 ghost-aware Jellyfin recovery helper smoke: OK")


if __name__=="__main__":main()
