"""Offline contract proof for asynchronous Jellyfin visibility reconciliation."""

from pathlib import Path
import json
import sqlite3
import tempfile
import urllib.parse

from teddy_discovery_jellyfin import (
    JellyfinClient,
    JellyfinError,
    JellyfinResponseError,
)
from teddy_discovery_jellyfin_visibility import (
    reconcile_jellyfin_visibility,
)
from teddy_discovery_media_jobs import MEDIA_SCHEMA


ROOT_ID = "virtual-adult"
# Canonical GUID for the separate filesystem-adult Folder.
FILESYSTEM_ID = "d59216ecad5753389303717a879b33ad"
FAMILY_ID = "family-folder"
RELATIVE = "ABC/ABC-123/ABC-123.mp4"
MEDIA_PATH = "/media/adult/" + RELATIVE


class FakeResponse:
    def __init__(self, payload, status=200):
        self.status = status
        self.data = json.dumps(payload).encode("utf-8")

    def getcode(self):
        return self.status

    def read(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class FakeJellyfin:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0
        self.post_calls = 0

    def exact_media_visibility(self, _path):
        self.calls += 1
        if not self.outcomes:
            return {"status": "PENDING", "reason": None}
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def notify_created(self, _path):
        self.post_calls += 1
        raise AssertionError("visibility reconciliation must never POST")


def make_fixture(root, jobs):
    root.mkdir(parents=True, exist_ok=True)
    discovery = root / "discovery.sqlite3"
    media = root / "media.sqlite3"
    lock = root / "media.lock"
    d = sqlite3.connect(discovery)
    d.execute(
        """CREATE TABLE holdings (
            holding_id INTEGER PRIMARY KEY,
            storage_root TEXT NOT NULL,
            relative_path TEXT NOT NULL,
            dvd_id TEXT,
            present INTEGER NOT NULL
        )"""
    )
    for dvd_id, relative in jobs.get("holdings", {}).items():
        d.execute(
            "INSERT INTO holdings(storage_root,relative_path,dvd_id,present) VALUES('jav',?,?,1)",
            (relative, dvd_id),
        )
    d.commit()
    d.close()
    m = sqlite3.connect(media)
    m.executescript(MEDIA_SCHEMA)
    for index, (dvd_id, status, attempts) in enumerate(jobs.get("rows", []), 1):
        stamp = f"2026-09-30T00:00:{index:02d}+00:00"
        m.execute(
            """INSERT INTO media_jobs
               (media_job_id,dvd_id,status,attempt_count,error,created_at,updated_at)
               VALUES(?,?,?,?,NULL,?,?)""",
            (index, dvd_id, status, attempts, stamp, stamp),
        )
    m.commit()
    m.close()
    return discovery, media, lock


def visibility_row(media, dvd_id):
    db = sqlite3.connect(media)
    db.row_factory = sqlite3.Row
    row = db.execute(
        "SELECT * FROM media_jellyfin_visibility WHERE dvd_id=?", (dvd_id,)
    ).fetchone()
    result = dict(row) if row else None
    db.close()
    return result


def media_row(media, dvd_id):
    db = sqlite3.connect(media)
    row = db.execute(
        "SELECT status,attempt_count,updated_at FROM media_jobs WHERE dvd_id=?",
        (dvd_id,),
    ).fetchone()
    db.close()
    return row


def run(root, jobs, jellyfin, *, target=None, max_items=5):
    discovery, media, lock = make_fixture(root, jobs)
    return reconcile_jellyfin_visibility(
        discovery, media, lock, jellyfin,
        max_items=max_items, target_dvd_id=target,
    ), discovery, media, lock


def actual_client_smoke(temp):
    key = temp / "key"
    key.write_text("fixture-key", encoding="utf-8")
    calls = []

    def exercise(title_items, *, family_items=None, parent_item=None, parent_response=None, reconcile_root=None):
        parent_item = parent_item if parent_item is not None else {
            "Id": FILESYSTEM_ID, "Type": "Folder", "Path": "/media/adult",
        }
        def opener(request, timeout=None):
            assert request.get_method() == "GET", "visibility lookup must be GET-only"
            calls.append((request.get_method(), request.full_url, timeout))
            parsed = urllib.parse.urlsplit(request.full_url)
            if parsed.path == "/Library/VirtualFolders":
                payload = [{"Name": "Adult", "ItemId": ROOT_ID, "Locations": ["/media/adult"]}]
            elif parsed.path == "/Items":
                params = urllib.parse.parse_qs(parsed.query)
                if "Ids" in params:
                    assert params["Ids"] == [FILESYSTEM_ID]
                    assert params["Limit"] == ["1"]
                    assert params["EnableImages"] == ["false"]
                    assert params["EnableUserData"] == ["false"]
                    return FakeResponse(parent_response if parent_response is not None else {
                        "Items": [parent_item], "TotalRecordCount": 1,
                    })
                assert params.get("Recursive") == ["false"]
                assert params.get("Limit") == ["1000"]
                assert params.get("StartIndex") == ["0"]
                parent = params.get("ParentId", [None])[0]
                rows = family_items if parent == ROOT_ID and family_items is not None else (
                    [{"Id": FAMILY_ID, "Type": "Folder", "Path": "/media/adult/ABC", "ParentId": FILESYSTEM_ID}]
                    if parent == ROOT_ID else title_items
                )
                payload = {"Items": rows, "TotalRecordCount": len(rows)}
            else:
                return FakeResponse({}, status=404)
            return FakeResponse(payload)

        client = JellyfinClient(
            base_url="http://fixture.invalid", api_key_path=key, opener=opener
        )
        if reconcile_root is not None:
            return run(reconcile_root, {
                "rows": [("ABC-123", "COMPLETED", 1)],
                "holdings": {"ABC-123": RELATIVE},
            }, client)
        return client.exact_media_visibility(MEDIA_PATH)

    movie = {"Id": "movie-1", "Type": "Movie", "Path": MEDIA_PATH, "ParentId": FAMILY_ID}
    assert exercise([])["status"] == "PENDING"
    assert exercise([movie]) == {"status": "VISIBLE", "reason": None, "item_id": "movie-1"}
    assert exercise([movie, movie])["reason"] == "DUPLICATE_EXACT_PATH"
    assert exercise([{**movie, "Type": "Video"}])["reason"] == "WRONG_ITEM_TYPE"
    assert exercise([{**movie, "ParentId": "unexpected-parent"}])["reason"] == "AMBIGUOUS_MOVIE_PARENT"
    bad_family = [{"Id": FAMILY_ID, "Type": "Folder", "Path": "/media/adult/ABC", "ParentId": ""}]
    assert exercise([movie], family_items=bad_family)["reason"] == "AMBIGUOUS_FAMILY_PARENT"
    ambiguous = [
        {"Id": "family-1", "Type": "Folder", "Path": "/media/adult/ABC", "ParentId": FILESYSTEM_ID},
        {"Id": "family-2", "Type": "Folder", "Path": "/media/adult/ABC", "ParentId": FILESYSTEM_ID},
    ]
    assert exercise([movie], family_items=ambiguous)["reason"] == "AMBIGUOUS_FAMILY_FOLDER"

    # Virtual CollectionFolder != filesystem Folder is the normal production shape.
    assert ROOT_ID != FILESYSTEM_ID
    assert exercise([movie])["status"] == "VISIBLE"
    state, _, media, _ = exercise([movie], reconcile_root=temp / "alias-integrated")
    assert state["visible"] == 1 and visibility_row(media, "ABC-123")["status"] == "VISIBLE"
    state, _, media, _ = exercise([movie], family_items=[{
        "Id": FAMILY_ID, "Type": "Folder", "Path": "/media/adult/ABC",
    }], reconcile_root=temp / "missing-parent-integrated")
    assert state["attention"] == 1 and visibility_row(media, "ABC-123")["status"] == "ATTENTION"
    for parent in (
        {"Id": FILESYSTEM_ID, "Type": "CollectionFolder", "Path": "/media/adult"},
        {"Id": FILESYSTEM_ID, "Type": "Folder", "Path": "/media/other"},
    ):
        assert exercise([movie], parent_item=parent)["reason"] == "AMBIGUOUS_FAMILY_PARENT"
    assert exercise([movie], family_items=[])["status"] == "PENDING"
    for response in (
        [], {}, {"Items": [], "TotalRecordCount": 0},
        {"Items": [{}], "TotalRecordCount": 1},
        {"Items": [{"Id": FILESYSTEM_ID, "Type": "Folder"}], "TotalRecordCount": 1},
        {"Items": [{"Id": FILESYSTEM_ID, "Type": None, "Path": "/media/adult"}], "TotalRecordCount": 1},
        {"Items": [{"Id": FILESYSTEM_ID, "Type": "Folder", "Path": 42}], "TotalRecordCount": 1},
        {"Items": [{"Id": "wrong-id", "Type": "Folder", "Path": "/media/adult"}], "TotalRecordCount": 1},
        {"Items": [], "TotalRecordCount": 2},
        {"Items": [], "TotalRecordCount": True},
    ):
        assert exercise([movie], parent_response=response)["reason"] == "INVALID_FAMILY_PARENT_RESPONSE"

    # Invalid exact IDs fail before any network request. Canonical GUID forms work.
    exact_calls = []
    def exact_opener(request, timeout=None):
        assert request.get_method() == "GET"
        exact_calls.append(request.full_url)
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)
        assert params["Ids"] == [FILESYSTEM_ID] and params["Limit"] == ["1"]
        return FakeResponse({"Items": [{
            "Id": FILESYSTEM_ID, "Type": "Folder", "Path": "/media/adult",
        }], "TotalRecordCount": 1})
    exact_client = JellyfinClient(base_url="http://fixture.invalid", api_key_path=key, opener=exact_opener)
    for invalid in (None, "", " ", "../Items", "not-a-guid", FILESYSTEM_ID + "?x=1", 123):
        try:
            exact_client.item_by_id(invalid)
        except JellyfinResponseError:
            pass
        else:
            raise AssertionError("invalid item ID accepted")
    assert exact_calls == []
    assert exact_client.item_by_id(FILESYSTEM_ID)["Path"] == "/media/adult"
    assert exact_client.item_by_id("d59216ec-ad57-5338-9303-717a879b33ad")["Path"] == "/media/adult"
    print("VIRTUAL_FILESYSTEM_ALIAS_FIXTURE=PASS NEGATIVE_HIERARCHY_FIXTURES=PASS GET_ONLY=YES")

    # A truncated bounded response is malformed/incomplete, never absence.
    def overflow_opener(request, timeout=None):
        assert request.get_method() == "GET"
        parsed = urllib.parse.urlsplit(request.full_url)
        if parsed.path == "/Library/VirtualFolders":
            payload = [{"Name": "Adult", "ItemId": ROOT_ID, "Locations": ["/media/adult"]}]
        else:
            payload = {"Items": [], "TotalRecordCount": 1001}
        return FakeResponse(payload)
    client = JellyfinClient(base_url="http://fixture.invalid", api_key_path=key, opener=overflow_opener)
    try:
        client.exact_media_visibility(MEDIA_PATH)
    except JellyfinResponseError:
        pass
    else:
        raise AssertionError("bounded-query overflow was not fail-closed")

    before = len(calls)
    try:
        client.exact_media_visibility("/media/adult/../outside/file.mp4")
    except JellyfinError:
        pass
    else:
        raise AssertionError("outside/noncanonical path was accepted")
    assert len(calls) == before
    assert calls and all(method == "GET" for method, _, _ in calls)


def main():
    with tempfile.TemporaryDirectory(prefix="teddy-jellyfin-visibility-") as temp_dir:
        temp = Path(temp_dir)
        actual_client_smoke(temp)

        # A: a completed row with one exact present holding seeds PENDING.
        state, _, media, _ = run(
            temp / "a", {"rows": [("ABC-123", "COMPLETED", 1)], "holdings": {"ABC-123": RELATIVE}},
            FakeJellyfin({"status": "PENDING", "reason": None}),
        )
        assert state["seeded"] == 1 and state["checked"] == 1 and state["pending"] == 1
        row = visibility_row(media, "ABC-123")
        assert row["status"] == "PENDING" and row["check_count"] == 1
        assert row["jellyfin_path"] == MEDIA_PATH and row["media_completed_at"]

        # B: non-completed statuses never seed visibility rows.
        for status in ("FAILED", "PENDING", "RUNNING"):
            root = temp / ("noncompleted-" + status.lower())
            state, _, media, _ = run(
                root, {"rows": [("ABC-123", status, 1)], "holdings": {"ABC-123": RELATIVE}},
                FakeJellyfin(),
            )
            assert state["seeded"] == 0 and state["checked"] == 0
            db = sqlite3.connect(media)
            count = db.execute("SELECT count(*) FROM media_jellyfin_visibility").fetchone()[0]
            db.close()
            assert count == 0

        # C/D: absent Movie remains PENDING, later exact Movie is terminal VISIBLE.
        root = temp / "eventual"
        jobs = {"rows": [("ABC-123", "COMPLETED", 1)], "holdings": {"ABC-123": RELATIVE}}
        state, discovery, media, lock = run(root, jobs, FakeJellyfin({"status": "PENDING", "reason": None}))
        later = FakeJellyfin({"status": "VISIBLE", "reason": None, "item_id": "movie-1"})
        state = reconcile_jellyfin_visibility(discovery, media, lock, later, max_items=1)
        assert state["visible"] == 1 and visibility_row(media, "ABC-123")["status"] == "VISIBLE"
        check_count = visibility_row(media, "ABC-123")["check_count"]
        state = reconcile_jellyfin_visibility(discovery, media, lock, later, max_items=1)
        assert state["checked"] == 0 and visibility_row(media, "ABC-123")["check_count"] == check_count

        # E/F: duplicates and wrong type are terminal ATTENTION, no automatic mutation.
        for reason in ("DUPLICATE_EXACT_PATH", "WRONG_ITEM_TYPE"):
            root = temp / ("attention-" + reason.lower())
            state, _, media, _ = run(
                root, jobs,
                FakeJellyfin({"status": "ATTENTION", "reason": reason}),
            )
            assert state["attention"] == 1 and visibility_row(media, "ABC-123")["status"] == "ATTENTION"

        root = temp / "malformed-response"
        state, _, media, _ = run(
            root, jobs, FakeJellyfin(JellyfinResponseError("unsafe detail"))
        )
        assert state["attention"] == 1
        assert visibility_row(media, "ABC-123")["status"] == "ATTENTION"
        assert visibility_row(media, "ABC-123")["last_error"].startswith(
            "MALFORMED_GET_RESPONSE:"
        )

        # G/H: GET error stays PENDING and never invokes a POST/retry path.
        root = temp / "get-error"
        original_media = ("COMPLETED", 2)
        state, _, media, _ = run(
            root, {"rows": [("ABC-123", *original_media)], "holdings": {"ABC-123": RELATIVE}},
            FakeJellyfin(TimeoutError("private URL detail must not persist")),
        )
        row = visibility_row(media, "ABC-123")
        assert state["pending"] == 1 and row["status"] == "PENDING"
        assert row["last_error"] == "GET_ERROR:TimeoutError"
        assert media_row(media, "ABC-123")[:2] == original_media

        # J/K: exact target mode changes only the selected DVD-ID.
        root = temp / "target"
        two_jobs = {
            "rows": [("ABC-123", "COMPLETED", 1), ("XYZ-999", "COMPLETED", 4)],
            "holdings": {"ABC-123": RELATIVE, "XYZ-999": "XYZ/XYZ-999/XYZ-999.mp4"},
        }
        client = FakeJellyfin({"status": "VISIBLE", "reason": None, "item_id": "xyz-movie"})
        state, _, media, _ = run(root, two_jobs, client, target="xyz-999", max_items=1)
        assert state["seeded"] == 1 and state["checked"] == 1 and state["target_dvd_id"] == "XYZ-999"
        assert visibility_row(media, "ABC-123") is None
        assert visibility_row(media, "XYZ-999")["status"] == "VISIBLE"
        assert client.calls == 1 and client.post_calls == 0
        assert media_row(media, "ABC-123") == ("COMPLETED", 1, "2026-09-30T00:00:01+00:00")
        assert media_row(media, "XYZ-999") == ("COMPLETED", 4, "2026-09-30T00:00:02+00:00")

        # L: process-crash recovery is an idempotent seed from COMPLETED + present holding.
        root = temp / "crash-recovery"
        state, _, media, _ = run(
            root, jobs, FakeJellyfin({"status": "PENDING", "reason": None})
        )
        assert state["seeded"] == 1 and visibility_row(media, "ABC-123")["status"] == "PENDING"

        # Missing/ambiguous holding cannot create a visibility row.
        root = temp / "no-holding"
        state, _, media, _ = run(
            root, {"rows": [("ABC-123", "COMPLETED", 1)]}, FakeJellyfin()
        )
        assert state["seeded"] == 0 and state["skipped_no_present_holding"] == 1

        # Invalid/non-Adult path is recorded as ATTENTION without a network request.
        root = temp / "invalid-path"
        offline = FakeJellyfin()
        state, _, media, _ = run(
            root,
            {"rows": [("ABC-123", "COMPLETED", 1)], "holdings": {"ABC-123": "../outside/file.mp4"}},
            offline,
        )
        invalid = visibility_row(media, "ABC-123")
        assert state["attention"] == 1 and invalid["status"] == "ATTENTION"
        assert invalid["jellyfin_path"] is None and offline.calls == 0

    print("STAGE9_JELLYFIN_VISIBILITY_SMOKE=PASS")


if __name__ == "__main__":
    main()
