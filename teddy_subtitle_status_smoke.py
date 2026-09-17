from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from teddy_subtitle_status import build_status_snapshot


def write_db(path, rows):
    con = sqlite3.connect(path)

    con.executescript("""
        CREATE TABLE stage12_rollout_titles (
            dvd_id TEXT PRIMARY KEY,
            status TEXT NOT NULL
        );

        CREATE TABLE stage12_rollout_events (
            event_id INTEGER PRIMARY KEY,
            dvd_id TEXT NOT NULL,
            to_status TEXT,
            transitioned_at TEXT NOT NULL
        );
    """)

    for dvd_id, status in rows:
        con.execute(
            """
            INSERT INTO stage12_rollout_titles(
                dvd_id, status
            ) VALUES (?, ?)
            """,
            (dvd_id, status),
        )

    con.execute(
        """
        INSERT INTO stage12_rollout_events(
            event_id, dvd_id, to_status, transitioned_at
        ) VALUES (1, 'AAA-001', 'PUBLISHED',
                  '1970-01-01T00:16:00+00:00')
        """
    )

    con.commit()
    con.close()


def main():
    with TemporaryDirectory(
        prefix="subtitle-status-smoke-"
    ) as raw:
        root = Path(raw)
        db = root / "state.sqlite3"
        heartbeat = root / "runtime.json"

        write_db(
            db,
            (
                ("AAA-001", "PUBLISHED"),
                ("BBB-001", "PENDING"),
                ("CCC-001", "UNRESOLVED"),
            ),
        )

        idle = build_status_snapshot(
            state_path=db,
            heartbeat_path=heartbeat,
            now_epoch=1000,
        )

        assert idle["status"] == "idle"
        assert idle["completed"] == 1
        assert idle["remaining"] == 1
        assert idle["unresolved"] == 1
        assert idle["heartbeat"]["present"] is False

        heartbeat.write_text(
            json.dumps({
                "schema_version": 1,
                "runner_state": "RUNNING",
                "current_dvd_id": "BBB-001",
                "stage": "HERMES",
                "part_index": 2,
                "part_count": 5,
                "updated_at":
                    "1970-01-01T00:16:20+00:00",
            }),
            encoding="utf-8",
        )

        running = build_status_snapshot(
            state_path=db,
            heartbeat_path=heartbeat,
            now_epoch=1000,
        )

        assert running["status"] == "running"
        assert running["current_dvd_id"] == "BBB-001"
        assert running["progress"]["part_index"] == 2
        assert running["progress"]["part_count"] == 5
        assert running["heartbeat"]["fresh"] is True

        heartbeat.write_text(
            json.dumps({
                "schema_version": 1,
                "runner_state": "RUNNING",
                "current_dvd_id": "BBB-001",
                "updated_at":
                    "1970-01-01T00:10:00+00:00",
            }),
            encoding="utf-8",
        )

        con = sqlite3.connect(db)
        con.execute(
            """
            UPDATE stage12_rollout_titles
            SET status = 'RUNNING'
            WHERE dvd_id = 'BBB-001'
            """
        )
        con.commit()
        con.close()

        stale = build_status_snapshot(
            state_path=db,
            heartbeat_path=heartbeat,
            now_epoch=1000,
        )

        assert stale["status"] == "stale"
        assert stale["current_dvd_id"] == "BBB-001"
        assert stale["heartbeat"]["fresh"] is False

    print("SUBTITLE_STATUS_SMOKE=PASS")


if __name__ == "__main__":
    main()
