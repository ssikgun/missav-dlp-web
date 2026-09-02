from pathlib import Path
import sqlite3
import tempfile

from teddy_discovery_completion import (
    CompletionPlan,
)
from teddy_discovery_completion_orchestrator import (
    process_one,
)


class FakeSSH:
    def stat_library(
        self,
        relative,
    ):
        return None


class FakeMutator:
    def __init__(self):
        self.calls = []

    def publish_to_library(
        self,
        **kwargs,
    ):
        self.calls.append(
            "publish"
        )

        return {
            "status": "PUBLISHED",
            "size": 123,
            "mtime_ns": 1000000000000,
            "source_preserved": True,
        }

    def cleanup_source(
        self,
        **kwargs,
    ):
        self.calls.append(
            "cleanup"
        )


def create_db(path):
    db = sqlite3.connect(path)

    db.executescript(
        """
        CREATE TABLE holdings (
            holding_id INTEGER PRIMARY KEY,
            storage_root TEXT,
            relative_path TEXT,
            dvd_id TEXT,
            parse_status TEXT,
            parse_method TEXT,
            parse_candidates_json TEXT,
            size_bytes INTEGER,
            mtime_ns INTEGER,
            discovered_by TEXT,
            present INTEGER,
            first_seen_at TEXT,
            last_seen_at TEXT,
            last_seen_run_id INTEGER
        );

        CREATE TABLE organizer_jobs (
            job_id INTEGER PRIMARY KEY,
            dvd_id TEXT,
            source_path TEXT,
            destination_path TEXT,
            status TEXT,
            error TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        """
    )

    db.commit()
    db.close()


plan = CompletionPlan(
    source_relative=(
        "missav/ABC-123.mp4"
    ),
    dvd_id="ABC-123",
    parse_method="filename",
    size_bytes=123,
    mtime_ns=1000000000000,
    destination_relative=(
        "ABC/ABC-123/ABC-123.mp4"
    ),
    metadata_ready=True,
    holding_count=0,
    planned_operation=(
        "PLAN_STAGE9_SSH_MOVE"
    ),
    collision_type="NONE",
    reason="smoke",
)


with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    db_path = root / "test.sqlite3"
    lock = root / "writer.lock"

    create_db(
        db_path
    )

    mutator = FakeMutator()

    job_id = process_one(
        plan,
        ssh=FakeSSH(),
        mutator=mutator,
        db_path=db_path,
        writer_lock_path=lock,
    )

    assert mutator.calls == [
        "publish",
        "cleanup",
    ]

    db = sqlite3.connect(
        db_path
    )

    job = db.execute(
        """
        SELECT status
        FROM organizer_jobs
        WHERE job_id = ?
        """,
        (job_id,),
    ).fetchone()

    assert job == (
        "COMPLETED",
    )

    holding = db.execute(
        """
        SELECT
            storage_root,
            relative_path,
            dvd_id,
            size_bytes,
            mtime_ns
        FROM holdings
        """
    ).fetchone()

    assert holding == (
        "jav",
        "ABC/ABC-123/ABC-123.mp4",
        "ABC-123",
        123,
        1000000000000,
    )

    db.close()


print(
    "STAGE9_COMPLETION_ORCHESTRATOR_SMOKE=PASS"
)
