"""Offline proof for durable at-most-once Jellyfin Deleted notifications."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
from urllib.parse import parse_qs, urlsplit

from teddy_discovery_jellyfin import JellyfinClient, JellyfinError, jellyfin_media_path
from teddy_library_delete_commit import (
    DeleteCommitError, JellyfinDeleteReconciler,
    claim_jellyfin_notification_attempt, NOTIFICATION_ATTEMPTS_TABLE,
)

RELATIVE = "VEMA/VEMA-246/VEMA-246.mp4"
EXPECTED = jellyfin_media_path(RELATIVE)
IDENTITY = {"operation_id":"op-1","dvd_id":"VEMA-246","holding_id":20,
    "source_identity_fingerprint":"source-fp","manifest_sha256":"manifest-sha"}


def response(items): return {"Items":items,"TotalRecordCount":len(items)}
def item(item_id="jf-1",path=EXPECTED): return {"Id":item_id,"Path":path,"ParentId":"parent"}
def broad(items): return response(items)
def exact(items): return response(items)


def db_fixture(root):
    path=Path(root)/"provenance.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE library_deletions(operation_id TEXT PRIMARY KEY,dvd_id TEXT,
          holding_id INTEGER,source_identity_fingerprint TEXT,manifest_sha256 TEXT,
          nas_delete_complete INTEGER,result_state TEXT)""")
        db.execute("INSERT INTO library_deletions VALUES(?,?,?,?,?,?,?)",
          (IDENTITY["operation_id"],IDENTITY["dvd_id"],IDENTITY["holding_id"],
           IDENTITY["source_identity_fingerprint"],IDENTITY["manifest_sha256"],1,"RECONCILE_PENDING"))
    return str(path)


class Client:
    def __init__(self, broad_gets=(), exact_gets=(), *, post_error=False):
        self.broad_gets=list(broad_gets);self.exact_gets=list(exact_gets)
        self.posts=[];self.post_error=post_error
    def _request(self,method,path):
        if method=="POST": self.posts.append(path);return None
        assert method=="GET" and path.startswith("/Items?")
        query=parse_qs(urlsplit(path).query)
        queue=self.exact_gets if "Ids" in query else self.broad_gets
        if not queue: raise AssertionError("unexpected GET: "+path)
        result=queue.pop(0)
        if isinstance(result,Exception):raise result
        return result
    def notify_deleted(self,path):
        self.posts.append(("/Library/Media/Updated",{"Updates":[{"Path":path,"UpdateType":"Deleted"}]}))
        if self.post_error:raise RuntimeError("fixture POST failed")


class Clock:
    def __init__(self):self.value=0.0
    def now(self):return self.value
    def sleep(self,n):self.value+=n

def reconciler(client,db,clock=None,*,timeout=4,interval=2):
    c=clock or Clock()
    return JellyfinDeleteReconciler(client,provenance_db=db,operation_identity=IDENTITY,
      timeout=timeout,interval=interval,clock=c.now,sleep=c.sleep),c


def expect_code(fn,code):
    try:fn()
    except DeleteCommitError as exc:assert exc.code==code,exc.code
    else:raise AssertionError("expected "+code)


def ledger_count(db):
    with sqlite3.connect(db) as conn:
        found=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
          (NOTIFICATION_ATTEMPTS_TABLE,)).fetchone()
        return 0 if not found else conn.execute(f"SELECT count(*) FROM {NOTIFICATION_ATTEMPTS_TABLE}").fetchone()[0]


def invoke(root,broad_gets,exact_gets,*,post_error=False,timeout=4):
    db=db_fixture(root);client=Client(broad_gets,exact_gets,post_error=post_error)
    r,_=reconciler(client,db,timeout=timeout)
    return db,client,r


def main():
    # 1: broad absent is read-only success (no ledger schema, no POST).
    with tempfile.TemporaryDirectory() as t:
        db,c,r=invoke(t,[broad([])],[])
        assert r(RELATIVE) and ledger_count(db)==0 and not c.posts

    # 2/18: broad exact-path candidate whose exact ID is absent is a ghost.
    with tempfile.TemporaryDirectory() as t:
        db,c,r=invoke(t,[broad([item()])],[exact([])])
        assert r(RELATIVE) and r.last_code=="BROAD_INVENTORY_GHOST" and not c.posts and ledger_count(db)==0

    # 18: the old same-ID broad row may remain after exact-ID removal.
    with tempfile.TemporaryDirectory() as t:
        db,c,r=invoke(t,[broad([item()])]*3,[exact([item()]),exact([]),exact([])])
        assert r(RELATIVE) and r.last_post_count==1 and len(c.posts)==1 and ledger_count(db)==1

    # 3/4: live item claims before the one POST, then exact-ID absence succeeds.
    with tempfile.TemporaryDirectory() as t:
        db,c,r=invoke(t,[broad([item()]),broad([])],[exact([item()]),exact([])])
        assert r(RELATIVE) and r.last_post_count==1 and len(c.posts)==1 and ledger_count(db)==1
        with sqlite3.connect(db) as conn:
            assert conn.execute(f"SELECT accepted_at FROM {NOTIFICATION_ATTEMPTS_TABLE}").fetchone()[0]

    # 5/6: crash after durable claim, before POST: retry only verifies and stays pending.
    with tempfile.TemporaryDirectory() as t:
        db=db_fixture(t)
        assert claim_jellyfin_notification_attempt(db,**IDENTITY,jellyfin_item_id="jf-1")=="CLAIMED_NEW"
        c=Client([broad([item()])],[exact([item()]),exact([item()])]);r,_=reconciler(c,db)
        assert r(RELATIVE) is False and r.last_code=="JELLYFIN_NOTIFICATION_OUTCOME_UNKNOWN"
        assert not c.posts and ledger_count(db)==1

    # 7/8: server accepted, caller crashed before accepted_at; absent ID closes without POST.
    with tempfile.TemporaryDirectory() as t:
        db=db_fixture(t);claim_jellyfin_notification_attempt(db,**IDENTITY,jellyfin_item_id="jf-1")
        prior=Client();prior.notify_deleted(EXPECTED)  # server accepted; caller crashes before accepted_at
        c=Client([broad([item()])],[exact([]),exact([])])
        r,_=reconciler(c,db)
        assert r(RELATIVE) and not c.posts and len(prior.posts)==1 and ledger_count(db)==1

    # 9/10: timeout leaves claim durable; subsequent live-ID retry is GET-only pending.
    with tempfile.TemporaryDirectory() as t:
        db=db_fixture(t);c=Client([broad([item()])],[exact([item()])]+[exact([item()])]*3)
        r,_=reconciler(c,db,timeout=2,interval=1)
        assert r(RELATIVE) is False and r.last_post_count==1 and len(c.posts)==1
        retry=Client([broad([item()])],[exact([item()]),exact([item()])]);rr,_=reconciler(retry,db)
        assert rr(RELATIVE) is False and not retry.posts and ledger_count(db)==1

    # 11/12: transport exception still leaves the attempt durable; retry never POSTs.
    with tempfile.TemporaryDirectory() as t:
        db,c,r=invoke(t,[broad([item()])],[exact([item()])],post_error=True)
        expect_code(lambda:r(RELATIVE),"JELLYFIN_DELETE_NOTIFICATION_FAILED")
        assert ledger_count(db)==1 and len(c.posts)==1
        retry=Client([broad([item()])],[exact([item()]),exact([item()])]);rr,_=reconciler(retry,db)
        assert rr(RELATIVE) is False and not retry.posts

    # 13: separate apply invocations share a DB claim, cumulative POST count <= 1.
    with tempfile.TemporaryDirectory() as t:
        db=db_fixture(t);total=0
        c=Client([broad([item()]),broad([])],[exact([item()]),exact([])]);r,_=reconciler(c,db)
        assert r(RELATIVE) is True;total+=len(c.posts)
        c=Client([broad([item()])],[exact([])]);r,_=reconciler(c,db)
        assert r(RELATIVE) is True;total+=len(c.posts)
        assert total<=1 and total==1

    # 14: operation/item identity conflict cannot create a second attempt.
    with tempfile.TemporaryDirectory() as t:
        db=db_fixture(t);claim_jellyfin_notification_attempt(db,**IDENTITY,jellyfin_item_id="jf-1")
        try:claim_jellyfin_notification_attempt(db,**IDENTITY,jellyfin_item_id="jf-2")
        except DeleteCommitError as exc:assert exc.code=="JELLYFIN_NOTIFICATION_CLAIM_CONFLICT"
        else:raise AssertionError("claim identity conflict accepted")

    # 15/16: ambiguity and missing ID fail before any claim or POST.
    with tempfile.TemporaryDirectory() as t:
        db,c,r=invoke(t,[broad([item(),item("jf-2")])],[])
        expect_code(lambda:r(RELATIVE),"JELLYFIN_PATH_AMBIGUOUS");assert not c.posts and ledger_count(db)==0
    with tempfile.TemporaryDirectory() as t:
        db,c,r=invoke(t,[broad([{"Path":EXPECTED}])],[])
        expect_code(lambda:r(RELATIVE),"JELLYFIN_RESPONSE_INVALID");assert not c.posts and ledger_count(db)==0

    # 17: malformed and wrong-path exact-ID responses fail closed before claim.
    for bad in ({"Items":[item("jf-2")],"TotalRecordCount":1},
                {"Items":[item("jf-1","/wrong")],"TotalRecordCount":1},
                {"Items":[],"TotalRecordCount":1},
                {"Items":[item(),item("jf-2")],"TotalRecordCount":2}):
        with tempfile.TemporaryDirectory() as t:
            db,c,r=invoke(t,[broad([item()])],[bad])
            expect_code(lambda:r(RELATIVE),"JELLYFIN_RESPONSE_INVALID")
            assert not c.posts and ledger_count(db)==0

    # 19: same path with a different live ID after removal is fail-closed.
    with tempfile.TemporaryDirectory() as t:
        db,c,r=invoke(t,[broad([item()]),broad([item("jf-new")])],
                       [exact([item()]),exact([]),exact([item("jf-new")])])
        expect_code(lambda:r(RELATIVE),"JELLYFIN_PATH_REAPPEARED_DIFFERENT_ID")
        assert len(c.posts)==1 and ledger_count(db)==1

    # Created remains unchanged and distinct from the at-most-once Deleted path.
    with tempfile.TemporaryDirectory(prefix="jf-notification-") as tmp:
        key=Path(tmp)/"key";key.write_text("fixture-key");requests=[]
        class Response:
            status=200
            def __enter__(self):return self
            def __exit__(self,*_args):return False
            def read(self):return b"{}"
            def getcode(self):return self.status
        def opener(req,timeout):requests.append((req,timeout));return Response()
        live=JellyfinClient(base_url="http://fixture",api_key_path=key,opener=opener)
        live.notify_created(EXPECTED);live.notify_deleted(EXPECTED)
        assert json.loads(requests[0][0].data)=={"Updates":[{"Path":EXPECTED,"UpdateType":"Created"}]}
        assert json.loads(requests[1][0].data)=={"Updates":[{"Path":EXPECTED,"UpdateType":"Deleted"}]}
        for unsafe in ("/media/adult","/media/adult/../other/movie.mp4","/media/adult/foo/*.mp4"):
            try:live.notify_deleted(unsafe)
            except JellyfinError:pass
            else:raise AssertionError("unsafe Deleted path accepted")

    print("Stage13-F2M-D9 durable at-most-once Jellyfin smoke: OK")


if __name__=="__main__":main()
