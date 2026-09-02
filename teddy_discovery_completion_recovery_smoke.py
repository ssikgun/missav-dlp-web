from pathlib import Path
import sqlite3
import tempfile

from teddy_discovery_completion import (
    CompletionPlan,
)
from teddy_discovery_completion_orchestrator import (
    CompletionOrchestratorError,
    process_one,
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


def make_plan(
    operation="PLAN_STAGE9_SSH_MOVE",
    collision="NONE",
    holding_count=0,
):
    return CompletionPlan(
        source_relative="missav/ABC-123.mp4",
        dvd_id="ABC-123",
        parse_method="filename",
        size_bytes=123,
        mtime_ns=1000000000000,
        destination_relative=(
            "ABC/ABC-123/ABC-123.mp4"
        ),
        metadata_ready=True,
        holding_count=holding_count,
        planned_operation=operation,
        collision_type=collision,
        reason="smoke",
    )


class FakeSSH:
    def __init__(self, existing=None):
        self.existing = existing

    def stat_library(self, relative):
        return self.existing


class FakeMutator:
    def __init__(self):
        self.calls = []

    def publish_to_library(self, **kwargs):
        self.calls.append("publish")

        return {
            "status": "PUBLISHED",
            "size": 123,
            "mtime_ns": 2000000000000,
            "source_preserved": True,
        }

    def cleanup_source(self, **kwargs):
        self.calls.append("cleanup")


# 1. Normal path.
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    db_path = root / "db.sqlite3"
    lock = root / "writer.lock"

    create_db(db_path)

    mutator = FakeMutator()

    job_id = process_one(
        make_plan(),
        ssh=FakeSSH(),
        mutator=mutator,
        db_path=db_path,
        writer_lock_path=lock,
        operation_lock_path=root / "operation.lock",
    )

    assert mutator.calls == [
        "publish",
        "cleanup",
    ]

    db = sqlite3.connect(db_path)

    assert db.execute(
        "SELECT status FROM organizer_jobs "
        "WHERE job_id = ?",
        (job_id,),
    ).fetchone() == ("COMPLETED",)

    assert db.execute(
        "SELECT COUNT(*) FROM holdings"
    ).fetchone() == (1,)

    db.close()


# 2. Publish succeeded previously, DB did not.
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    db_path = root / "db.sqlite3"
    lock = root / "writer.lock"

    create_db(db_path)

    db = sqlite3.connect(db_path)

    db.execute(
        """
        INSERT INTO organizer_jobs (
            dvd_id,
            source_path,
            destination_path,
            status,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, '', '')
        """,
        (
            "ABC-123",
            "missav/ABC-123.mp4",
            "ABC/ABC-123/ABC-123.mp4",
            "DB_FAILED_AFTER_PUBLISH",
        ),
    )

    db.commit()
    db.close()

    mutator = FakeMutator()

    process_one(
        make_plan(),
        ssh=FakeSSH({
            "size": 123,
            "mtime_ns": 3000000000000,
        }),
        mutator=mutator,
        db_path=db_path,
        writer_lock_path=lock,
        operation_lock_path=root / "operation.lock",
    )

    assert mutator.calls == [
        "cleanup",
    ]

    db = sqlite3.connect(db_path)

    assert db.execute(
        "SELECT COUNT(*) FROM holdings"
    ).fetchone() == (1,)

    assert db.execute(
        "SELECT status FROM organizer_jobs"
    ).fetchone() == ("COMPLETED",)

    db.close()


# 3. DB committed previously, cleanup did not.
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    db_path = root / "db.sqlite3"
    lock = root / "writer.lock"

    create_db(db_path)

    db = sqlite3.connect(db_path)

    db.execute(
        """
        INSERT INTO holdings (
            storage_root,
            relative_path,
            dvd_id,
            size_bytes,
            mtime_ns,
            present
        )
        VALUES ('jav', ?, ?, ?, ?, 1)
        """,
        (
            "ABC/ABC-123/ABC-123.mp4",
            "ABC-123",
            123,
            3000000000000,
        ),
    )

    db.execute(
        """
        INSERT INTO organizer_jobs (
            dvd_id,
            source_path,
            destination_path,
            status,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, '', '')
        """,
        (
            "ABC-123",
            "missav/ABC-123.mp4",
            "ABC/ABC-123/ABC-123.mp4",
            "CLEANUP_PENDING",
        ),
    )

    db.commit()
    db.close()

    mutator = FakeMutator()

    process_one(
        make_plan(
            operation="HOLD",
            collision="ALREADY_IN_LIBRARY",
            holding_count=1,
        ),
        ssh=FakeSSH({
            "size": 123,
            "mtime_ns": 3000000000000,
        }),
        mutator=mutator,
        db_path=db_path,
        writer_lock_path=lock,
        operation_lock_path=root / "operation.lock",
    )

    assert mutator.calls == [
        "cleanup",
    ]

    db = sqlite3.connect(db_path)

    assert db.execute(
        "SELECT status FROM organizer_jobs"
    ).fetchone() == ("COMPLETED",)

    db.close()


# 4. Unknown destination must fail closed.
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    db_path = root / "db.sqlite3"
    lock = root / "writer.lock"

    create_db(db_path)

    mutator = FakeMutator()

    try:
        process_one(
            make_plan(),
            ssh=FakeSSH({
                "size": 123,
                "mtime_ns": 3000000000000,
            }),
            mutator=mutator,
            db_path=db_path,
            writer_lock_path=lock,
            operation_lock_path=root / "operation.lock",
        )
    except CompletionOrchestratorError:
        pass
    else:
        raise RuntimeError(
            "unknown destination was accepted"
        )

    assert mutator.calls == []


print(
    "STAGE9_COMPLETION_RECOVERY_SMOKE=PASS"
)
