"""Offline bounded exact Jellyfin deletion reconciliation fixtures."""
from __future__ import annotations

from teddy_discovery_jellyfin import jellyfin_media_path
from teddy_library_delete_commit import DeleteCommitError, JellyfinDeleteReconciler


DVD = "VEMA-246"
RELATIVE = "VEMA/VEMA-246/VEMA-246.mp4"
EXPECTED = jellyfin_media_path(RELATIVE)


def response(items):
    return {"Items": items, "TotalRecordCount": len(items)}


def item(item_id="jf-1", path=EXPECTED):
    return {"Id": item_id, "Path": path}


class Clock:
    def __init__(self): self.value=0.0; self.sleeps=[]
    def now(self): return self.value
    def sleep(self, seconds): self.sleeps.append(seconds); self.value += seconds


class Client:
    def __init__(self, gets, *, post_error=False):
        self.gets=list(gets); self.posts=[]; self.post_error=post_error; self.get_count=0
    def _request(self, method, path):
        if method == "POST":
            self.posts.append(path)
            if self.post_error: raise RuntimeError("fixture POST failed")
            return None
        assert method == "GET" and path.startswith("/Items?")
        self.get_count += 1
        if not self.gets: raise AssertionError("unexpected extra GET")
        value=self.gets.pop(0)
        if isinstance(value, Exception): raise value
        return value


def reconciler(client, clock=None, *, timeout=60, interval=2):
    clock=clock or Clock()
    return JellyfinDeleteReconciler(client,timeout=timeout,interval=interval,
                                    clock=clock.now,sleep=clock.sleep),clock


def fails(call, expected):
    try: call()
    except (DeleteCommitError, RuntimeError) as exc:
        if isinstance(exc, DeleteCommitError): assert exc.code == expected, exc.code
    else: raise AssertionError("unsafe Jellyfin state accepted")


def main():
    # A: already absent performs GET only.
    c=Client([response([])]); r,_=reconciler(c)
    assert r(RELATIVE) is True and c.get_count==1 and len(c.posts)==0

    # B: one exact item, one refresh, gone on first delayed poll.
    c=Client([response([item()]),response([])]); r,clock=reconciler(c)
    assert r(RELATIVE) is True and len(c.posts)==1 and c.get_count==2
    assert clock.sleeps==[2.0]

    # C: eventual removal after several polls; refresh remains exactly once.
    c=Client([response([item()]),response([item()]),response([item()]),response([])])
    r,clock=reconciler(c)
    assert r(RELATIVE) is True and len(c.posts)==1 and c.get_count==4
    assert clock.value==6.0

    # D: bounded timeout returns pending without another POST.
    clock=Clock(); c=Client([response([item()])]+[response([item()]) for _ in range(4)])
    r,_=reconciler(c,clock,timeout=6,interval=2)
    assert r(RELATIVE) is False and len(c.posts)==1 and clock.value==6

    # E: ambiguous exact path is rejected before mutation.
    c=Client([response([item(),item("jf-2")])]); r,_=reconciler(c)
    fails(lambda:r(RELATIVE),"JELLYFIN_PATH_AMBIGUOUS"); assert not c.posts

    # F: exact match missing its item ID is rejected before mutation.
    c=Client([response([item("")])]); r,_=reconciler(c)
    fails(lambda:r(RELATIVE),"JELLYFIN_ITEM_ID_MISSING"); assert not c.posts

    # G: incomplete/invalid GET is rejected before mutation.
    c=Client([{"Items":[],"TotalRecordCount":1}]); r,_=reconciler(c)
    fails(lambda:r(RELATIVE),"JELLYFIN_INVENTORY_INCOMPLETE"); assert not c.posts
    c=Client([{"Items":[{"Id":"bad"}],"TotalRecordCount":1}]); r,_=reconciler(c)
    fails(lambda:r(RELATIVE),"JELLYFIN_RESPONSE_INVALID"); assert not c.posts

    # H: Refresh POST failures propagate; I: a successful POST occurs once.
    c=Client([response([item()])],post_error=True); r,_=reconciler(c)
    fails(lambda:r(RELATIVE),"POST_FAILURE"); assert len(c.posts)==1
    c=Client([response([item()]),response([])]); r,_=reconciler(c)
    assert r(RELATIVE) and len(c.posts)==1

    print("Stage13-F2M-D bounded exact Jellyfin reconciler smoke: OK")


if __name__ == "__main__":
    main()
