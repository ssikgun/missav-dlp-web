from pathlib import Path
from datetime import datetime, timedelta, timezone
import sqlite3
import tempfile

from teddy_discovery_db import (
    connect,
    initialize,
)
from teddy_discovery_media_jobs import (
    MEDIA_SCHEMA,
    list_retryable_media_jobs,
    reconcile_media_jobs,
    run_retryable_media_jobs,
    retry_eligibility,
)
from teddy_title_exclusion import (
    ACQUIRED,
    BUSY,
    try_acquire_title_lock,
)


def add_job(db_path, dvd_id, status, attempts, updated_at):
    db = sqlite3.connect(db_path)
    db.executescript(MEDIA_SCHEMA)
    db.execute(
        """
        INSERT INTO media_jobs(dvd_id,status,attempt_count,error,created_at,updated_at)
        VALUES(?,?,?,NULL,?,?)
        """,
        (dvd_id, status, attempts, updated_at, updated_at),
    )
    db.commit()
    db.close()


def read_job(db_path, dvd_id):
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    row = db.execute(
        "SELECT * FROM media_jobs WHERE dvd_id=?", (dvd_id,)
    ).fetchone()
    db.close()
    return dict(row) if row else None


def retry_policy_smoke(root):
    now = datetime.now(timezone.utc)
    fresh = (now - timedelta(seconds=30)).isoformat()
    backoff = (now - timedelta(seconds=3601)).isoformat()
    stale = (now - timedelta(seconds=7201)).isoformat()
    cases = [
        ({"status": "PENDING", "attempt_count": 0}, "ELIGIBLE"),
        ({"status": "PENDING", "attempt_count": 5}, "EXHAUSTED"),
        ({"status": "FAILED", "attempt_count": 1, "updated_at": backoff}, "ELIGIBLE"),
        ({"status": "FAILED", "attempt_count": 1, "updated_at": fresh}, "HELD_BACKOFF"),
        ({"status": "FAILED", "attempt_count": 5, "updated_at": backoff}, "EXHAUSTED"),
        ({"status": "FAILED", "attempt_count": 17161, "updated_at": backoff}, "EXHAUSTED"),
        ({"status": "RUNNING", "attempt_count": 1, "updated_at": fresh}, "HELD_FRESH_RUNNING"),
        ({"status": "RUNNING", "attempt_count": 1, "updated_at": stale}, "ELIGIBLE"),
        ({"status": "RUNNING", "attempt_count": 5, "updated_at": stale}, "EXHAUSTED"),
        ({"status": "COMPLETED", "attempt_count": 1, "updated_at": fresh}, "COMPLETED"),
        ({"status": "FAILED", "attempt_count": 1, "updated_at": "broken"}, "HELD_INVALID_TIMESTAMP"),
        ({"status": "RUNNING", "attempt_count": 1, "updated_at": "2026-09-29T00:00:00"}, "HELD_INVALID_TIMESTAMP"),
    ]
    for job, expected in cases:
        assert retry_eligibility(job, now=now) == expected, (job.get("status"), expected)

    db_path = root / "policy.sqlite3"
    lock_path = root / "policy-writer.lock"
    title_root = root / "title-locks"
    title_root.mkdir(exist_ok=True)
    stamp = now.isoformat()
    add_job(db_path, "ABC-123", "FAILED", 17161, backoff)
    add_job(db_path, "XYZ-789", "PENDING", 0, stamp)
    called = []
    result = run_retryable_media_jobs(
        db_path=db_path,
        writer_lock_path=lock_path,
        title_lock_dir=title_root,
        processor=lambda dvd_id: called.append(dvd_id),
        max_items=1,
        now=now,
    )
    assert result["exhausted"] == 1
    assert result["attempted"] == 1
    assert called == ["XYZ-789"]
    assert read_job(db_path, "ABC-123")["attempt_count"] == 17161


def title_lock_smoke(root):
    db_path = root / "locks.sqlite3"
    writer = root / "locks-writer.lock"
    lock_root = root / "shared-title-locks"
    lock_root.mkdir()
    stamp = datetime.now(timezone.utc).isoformat()
    add_job(db_path, "ABC-123", "PENDING", 0, stamp)
    add_job(db_path, "XYZ-789", "PENDING", 0, stamp)
    called = []

    # Delete-side holder blocks a same-title retry without touching its row.
    delete_lock = try_acquire_title_lock("ABC-123", lock_dir=lock_root)
    assert delete_lock.status == ACQUIRED
    result = run_retryable_media_jobs(
        db_path=db_path, writer_lock_path=writer, title_lock_dir=lock_root,
        processor=lambda dvd_id: called.append(dvd_id), max_items=1,
    )
    assert result["held_busy"] == 1
    assert called == ["XYZ-789"]
    assert read_job(db_path, "ABC-123")["attempt_count"] == 0
    delete_lock.release()

    # A retry holds the title lock through processor and final durable status.
    observed = []
    def processor(dvd_id):
        contender = try_acquire_title_lock(dvd_id, lock_dir=lock_root)
        observed.append(contender.status)
        contender.release()
        other = try_acquire_title_lock("XYZ-789", lock_dir=lock_root)
        observed.append(other.status)
        other.release()
        called.append(dvd_id)
        return {"ok": True}

    result = run_retryable_media_jobs(
        db_path=db_path, writer_lock_path=writer, title_lock_dir=lock_root,
        processor=processor, max_items=1,
    )
    assert result["completed"] == 1
    assert observed == [BUSY, ACQUIRED]
    assert read_job(db_path, "ABC-123")["status"] == "COMPLETED"

    # Missing/unavailable lock infrastructure fails before attempt accounting.
    add_job(
        db_path,
        "QWE-456",
        "PENDING",
        0,
        datetime.now(timezone.utc).isoformat(),
    )
    missing = root / "missing-lock-root"
    result = run_retryable_media_jobs(
        db_path=db_path, writer_lock_path=writer, title_lock_dir=missing,
        processor=lambda dvd_id: called.append("unexpected"), max_items=1,
    )
    assert result["held_lock_unavailable"] == 1
    assert read_job(db_path, "QWE-456")["attempt_count"] == 0

    # Processor failure still releases flock and records FAILED under the lock.
    def fail(_dvd_id):
        raise RuntimeError("fixture failure")
    result = run_retryable_media_jobs(
        db_path=db_path, writer_lock_path=writer, title_lock_dir=lock_root,
        processor=fail, max_items=1,
    )
    assert result["failed"] == 1
    after = try_acquire_title_lock("QWE-456", lock_dir=lock_root)
    assert after.status == ACQUIRED
    after.release()


def conditional_race_smoke(root):
    import teddy_discovery_media_jobs as media_jobs

    for suffix, mutate in (
        ("status", "UPDATE media_jobs SET status='FAILED',updated_at='2026-01-01T00:00:00+00:00' WHERE dvd_id='ABC-123'"),
        ("attempt", "UPDATE media_jobs SET attempt_count=1 WHERE dvd_id='ABC-123'"),
        ("updated", "UPDATE media_jobs SET updated_at='2026-01-01T00:00:00+00:00' WHERE dvd_id='ABC-123'"),
        ("removed", "DELETE FROM media_jobs WHERE dvd_id='ABC-123'"),
    ):
        db_path = root / ("race-" + suffix + ".sqlite3")
        writer = root / ("race-" + suffix + ".lock")
        lock_root = root / ("race-locks-" + suffix)
        lock_root.mkdir()
        stamp = datetime.now(timezone.utc).isoformat()
        add_job(db_path, "ABC-123", "PENDING", 0, stamp)
        original = media_jobs.list_retryable_media_jobs
        def candidate_then_race(path, _mutate=mutate):
            rows = original(path)
            db = sqlite3.connect(path)
            db.execute(_mutate)
            db.commit()
            db.close()
            return rows
        media_jobs.list_retryable_media_jobs = candidate_then_race
        called = []
        try:
            result = run_retryable_media_jobs(
                db_path=db_path, writer_lock_path=writer, title_lock_dir=lock_root,
                processor=lambda dvd_id: called.append(dvd_id), max_items=1,
            )
        finally:
            media_jobs.list_retryable_media_jobs = original
        assert result["held_conflict"] == 1
        assert result["attempted"] == 0 and called == []


def main():
    with tempfile.TemporaryDirectory(
        prefix="teddy-stage9-media-db-"
    ) as temp:

        root = Path(temp)

        discovery_db = (
            root / "discovery.sqlite3"
        )

        media_db = (
            root / "stage9-media.sqlite3"
        )

        media_lock = (
            root / "stage9-media.lock"
        )
        title_lock_dir = root / "title-locks"
        title_lock_dir.mkdir()

        db = connect(
            discovery_db
        )

        initialize(
            db
        )

        version = db.execute(
            """
            SELECT MAX(version)
            FROM schema_migrations
            """
        ).fetchone()[0]

        assert int(version) == 6

        db.execute(
            """
            INSERT INTO titles(dvd_id)
            VALUES ('ABC-123')
            """
        )

        db.execute(
            """
            INSERT INTO holdings(
                storage_root,
                relative_path,
                dvd_id,
                parse_status,
                parse_method,
                parse_candidates_json,
                size_bytes,
                mtime_ns,
                discovered_by,
                present,
                first_seen_at,
                last_seen_at
            )
            VALUES(
                'jav',
                'ABC/ABC-123/ABC-123.mp4',
                'ABC-123',
                'MATCHED',
                'standard-leading',
                '["ABC-123"]',
                123,
                456,
                'completion-stage9',
                1,
                '2026-09-02T00:00:00+00:00',
                '2026-09-02T00:00:00+00:00'
            )
            """
        )

        db.execute(
            """
            INSERT INTO organizer_jobs(
                dvd_id,
                source_path,
                destination_path,
                status,
                error,
                created_at,
                updated_at
            )
            VALUES(
                'ABC-123',
                'missav/ABC-123.mp4',
                'ABC/ABC-123/ABC-123.mp4',
                'COMPLETED',
                NULL,
                '2026-09-02T00:00:00+00:00',
                '2026-09-02T00:00:00+00:00'
            )
            """
        )

        db.commit()
        db.close()

        created = reconcile_media_jobs(
            discovery_db,
            media_db,
            media_lock,
        )

        assert created == 1

        jobs = list_retryable_media_jobs(
            media_db
        )

        assert len(jobs) == 1
        assert jobs[0]["status"] == "PENDING"

        attempts = []

        def flaky_processor(dvd_id):
            attempts.append(dvd_id)

            if len(attempts) == 1:
                raise RuntimeError(
                    "temporary jellyfin failure"
                )

            return {
                "status":
                    "MEDIA_PIPELINE_COMPLETE",
            }

        first = run_retryable_media_jobs(
            db_path=media_db,
            writer_lock_path=media_lock,
            processor=flaky_processor,
            max_items=1,
            title_lock_dir=title_lock_dir,
        )

        assert first["failed"] == 1

        second = run_retryable_media_jobs(
            db_path=media_db,
            writer_lock_path=media_lock,
            processor=flaky_processor,
            max_items=1,
            title_lock_dir=title_lock_dir,
            now=datetime.now(timezone.utc) + timedelta(seconds=3601),
        )

        assert second["completed"] == 1

        media = sqlite3.connect(
            media_db
        )

        row = media.execute(
            """
            SELECT
                status,
                attempt_count,
                error
            FROM media_jobs
            WHERE dvd_id = 'ABC-123'
            """
        ).fetchone()

        assert row[0] == "COMPLETED"
        assert int(row[1]) == 2
        assert row[2] is None

        media.close()

        discovery = sqlite3.connect(
            discovery_db
        )

        media_table = discovery.execute(
            """
            SELECT COUNT(*)
            FROM sqlite_master
            WHERE type='table'
              AND name='media_jobs'
            """
        ).fetchone()[0]

        version = discovery.execute(
            """
            SELECT MAX(version)
            FROM schema_migrations
            """
        ).fetchone()[0]

        discovery.close()

        assert int(media_table) == 0
        assert int(version) == 6

        retry_policy_smoke(root)
        title_lock_smoke(root)
        conditional_race_smoke(root)

    print(
        "STAGE9_SEPARATE_MEDIA_DB_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
