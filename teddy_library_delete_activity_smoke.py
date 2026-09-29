"""Offline fixtures for target-specific delete activity decisions."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import time

from teddy_library_delete_activity import (
    ACTIVITY_STATE_UNAVAILABLE, ACTIVE_ORGANIZER, ACTIVE_SUBTITLE, IDLE,
    DeleteTargetActivityGuard, OrganizerActivitySource, SubtitleActivitySource,
)


DVD = "ABCD-123"
OTHER = "EFGH-456"


def _db(path, schema, rows):
    db = sqlite3.connect(path)
    db.executescript(schema)
    db.executemany(rows[0], rows[1])
    db.commit()
    db.close()


def _sources(tmp, organizer_rows=(), subtitle_rows=(), heartbeat=None):
    organizer = Path(tmp) / "discovery.sqlite3"
    rollout = Path(tmp) / "rollout.sqlite3"
    heartbeat_path = Path(tmp) / "heartbeat.json"
    _db(organizer, """CREATE TABLE organizer_jobs(
        job_id INTEGER PRIMARY KEY, dvd_id TEXT, status TEXT NOT NULL)""",
        ("INSERT INTO organizer_jobs(dvd_id,status) VALUES(?,?)", organizer_rows))
    _db(rollout, """CREATE TABLE stage12_rollout_titles(
        dvd_id TEXT PRIMARY KEY, status TEXT NOT NULL)""",
        ("INSERT INTO stage12_rollout_titles(dvd_id,status) VALUES(?,?)", subtitle_rows))
    if heartbeat is not None:
        heartbeat_path.write_text(json.dumps(heartbeat), encoding="utf-8")
    return OrganizerActivitySource(organizer), SubtitleActivitySource(
        rollout, heartbeat_path, now_epoch=time.time())


def _guard(tmp, organizer_rows=(), subtitle_rows=(), heartbeat=None):
    organizer, subtitle = _sources(
        tmp, organizer_rows=organizer_rows, subtitle_rows=subtitle_rows,
        heartbeat=heartbeat)
    return DeleteTargetActivityGuard(organizer, subtitle)


def _heartbeat(*, runner="COMPLETE", current=None, updated=None):
    timestamp = updated or datetime.now(timezone.utc).isoformat()
    return {"runner_state": runner, "current_dvd_id": current,
            "updated_at": timestamp, "stage": "fixture", "part_index": 0,
            "part_count": 1}


def main():
    # Organizer authoritative transitions: RUNNING -> PUBLISHED -> COMPLETED;
    # FAILED is terminal. Recovery-incomplete and unknown states fail closed.
    with tempfile.TemporaryDirectory(prefix="delete-activity-organizer-") as tmp:
        assert _guard(tmp).check(DVD).status == IDLE
    with tempfile.TemporaryDirectory(prefix="delete-activity-organizer-") as tmp:
        g = _guard(tmp, organizer_rows=[(DVD, "COMPLETED"), (DVD, "FAILED")])
        assert g.check(DVD).status == IDLE
    for status in ("RUNNING", "PUBLISHED"):
        with tempfile.TemporaryDirectory(prefix="delete-activity-organizer-") as tmp:
            g = _guard(tmp, organizer_rows=[(DVD, status)])
            assert g.check(DVD).status == ACTIVE_ORGANIZER
    with tempfile.TemporaryDirectory(prefix="delete-activity-organizer-") as tmp:
        g = _guard(tmp, organizer_rows=[(DVD, "FAILED"), (DVD, "RUNNING")])
        assert g.check(DVD).status == ACTIVE_ORGANIZER
    for status in ("CLEANUP_PENDING", "DB_FAILED_AFTER_PUBLISH", "ALIEN"):
        with tempfile.TemporaryDirectory(prefix="delete-activity-organizer-") as tmp:
            g = _guard(tmp, organizer_rows=[(DVD, status)])
            assert g.check(DVD).status == ACTIVITY_STATE_UNAVAILABLE
    with tempfile.TemporaryDirectory(prefix="delete-activity-organizer-") as tmp:
        g = _guard(tmp, organizer_rows=[(OTHER, "RUNNING")])
        assert g.check(DVD).status == IDLE
    assert OrganizerActivitySource("/missing/discovery.sqlite3").check(DVD).status == ACTIVITY_STATE_UNAVAILABLE

    # Stage12 durable rows are per DVD-ID; RUNNING and GENERATED remain active
    # even when the runner heartbeat is stale.
    with tempfile.TemporaryDirectory(prefix="delete-activity-subtitle-") as tmp:
        assert _guard(tmp).check(DVD).status == IDLE
    with tempfile.TemporaryDirectory(prefix="delete-activity-subtitle-") as tmp:
        g = _guard(tmp, subtitle_rows=[(DVD, "PUBLISHED")])
        assert g.check(DVD).status == IDLE
    for status in ("RUNNING", "GENERATED"):
        with tempfile.TemporaryDirectory(prefix="delete-activity-subtitle-") as tmp:
            stale = _heartbeat(updated="2000-01-01T00:00:00+00:00")
            g = _guard(tmp, subtitle_rows=[(DVD, status)], heartbeat=stale)
            assert g.check(DVD).status == ACTIVE_SUBTITLE
    with tempfile.TemporaryDirectory(prefix="delete-activity-subtitle-") as tmp:
        g = _guard(tmp, subtitle_rows=[(OTHER, "RUNNING")])
        assert g.check(DVD).status == IDLE
    with tempfile.TemporaryDirectory(prefix="delete-activity-subtitle-") as tmp:
        g = _guard(tmp, heartbeat=_heartbeat(runner="RUNNING", current=DVD))
        assert g.check(DVD).status == ACTIVE_SUBTITLE
    with tempfile.TemporaryDirectory(prefix="delete-activity-subtitle-") as tmp:
        g = _guard(tmp, heartbeat=_heartbeat(runner="RUNNING", current=OTHER))
        assert g.check(DVD).status == IDLE
    for heartbeat in ({"runner_state": "RUNNING", "current_dvd_id": DVD},
                      _heartbeat(runner="MYSTERY", current=DVD)):
        with tempfile.TemporaryDirectory(prefix="delete-activity-subtitle-") as tmp:
            g = _guard(tmp, heartbeat=heartbeat)
            assert g.check(DVD).status == ACTIVITY_STATE_UNAVAILABLE
    with tempfile.TemporaryDirectory(prefix="delete-activity-subtitle-") as tmp:
        _sources(tmp)
        Path(tmp, "heartbeat.json").write_text("{bad", encoding="utf-8")
        org = OrganizerActivitySource(Path(tmp) / "discovery.sqlite3")
        sub = SubtitleActivitySource(Path(tmp) / "rollout.sqlite3",
                                     Path(tmp) / "heartbeat.json")
        assert DeleteTargetActivityGuard(org, sub).check(DVD).status == ACTIVITY_STATE_UNAVAILABLE
    with tempfile.TemporaryDirectory(prefix="delete-activity-subtitle-") as tmp:
        g = DeleteTargetActivityGuard(
            OrganizerActivitySource(Path(tmp) / "missing.sqlite3"),
            SubtitleActivitySource(Path(tmp) / "missing-rollout.sqlite3",
                                   Path(tmp) / "missing-heartbeat.json"))
        assert g.check(DVD).status == ACTIVITY_STATE_UNAVAILABLE

    print("Stage13-F2E offline target activity guard smoke: OK")


if __name__ == "__main__":
    main()
