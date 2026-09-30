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
    normalize_media_target_dvd_id,
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


def exact_target_selector_smoke(root):
    now = datetime.now(timezone.utc)
    current = now.isoformat()
    backoff_age = (now - timedelta(seconds=3601)).isoformat()
    fresh_failure = (now - timedelta(seconds=30)).isoformat()

    def setup(case, rows):
        db = root / f"target-{case}.sqlite3"
        writer = root / f"target-{case}.writer.lock"
        lock_dir = root / f"target-{case}.title-locks"
        lock_dir.mkdir()
        for dvd_id, status, attempts, updated in rows:
            add_job(db, dvd_id, status, attempts, updated)
        return db, writer, lock_dir

    assert normalize_media_target_dvd_id("hmn-904") == "HMN-904"

    # An earlier eligible unrelated row is neither locked nor changed.
    db, writer, locks = setup(
        "eligible",
        [
            ("AAA-111", "PENDING", 0, current),
            ("HMN-904", "PENDING", 0, current),
        ],
    )
    attempted = []
    result = run_retryable_media_jobs(
        db_path=db,
        writer_lock_path=writer,
        title_lock_dir=locks,
        processor=lambda dvd_id: attempted.append(dvd_id) or {"ok": True},
        max_items=1,
        target_dvd_id="hmn-904",
        now=now,
    )
    assert result["target_dvd_id"] == "HMN-904"
    assert result["attempted"] == 1 and attempted == ["HMN-904"]
    assert read_job(db, "HMN-904")["status"] == "COMPLETED"
    assert read_job(db, "HMN-904")["attempt_count"] == 1
    assert read_job(db, "AAA-111")["status"] == "PENDING"
    assert read_job(db, "AAA-111")["attempt_count"] == 0

    # A target inside backoff holds the whole selected operation; unrelated
    # eligible work is not used as a fallback.
    db, writer, locks = setup(
        "backoff",
        [
            ("AAA-111", "PENDING", 0, current),
            ("HMN-904", "FAILED", 1, fresh_failure),
        ],
    )
    attempted = []
    result = run_retryable_media_jobs(
        db_path=db,
        writer_lock_path=writer,
        title_lock_dir=locks,
        processor=lambda dvd_id: attempted.append(dvd_id),
        target_dvd_id="HMN-904",
        now=now,
    )
    assert result["attempted"] == 0
    assert result["held_backoff"] == 1
    assert result["jobs"] == [
        {"dvd_id": "HMN-904", "status": "HELD_BACKOFF"}
    ]
    assert attempted == []
    assert read_job(db, "HMN-904")["attempt_count"] == 1
    assert read_job(db, "AAA-111")["attempt_count"] == 0

    # Exhaustion is not bypassed and cannot fall back to an unrelated row.
    db, writer, locks = setup(
        "exhausted",
        [
            ("AAA-111", "PENDING", 0, current),
            ("HMN-904", "FAILED", 5, backoff_age),
        ],
    )
    result = run_retryable_media_jobs(
        db_path=db,
        writer_lock_path=writer,
        title_lock_dir=locks,
        processor=lambda _dvd_id: (_ for _ in ()).throw(
            AssertionError("exhausted target was processed")
        ),
        target_dvd_id="HMN-904",
        now=now,
    )
    assert result["attempted"] == 0 and result["exhausted"] == 1
    assert result["jobs"][0]["status"] == "EXHAUSTED"
    assert read_job(db, "HMN-904")["attempt_count"] == 5
    assert read_job(db, "AAA-111")["attempt_count"] == 0

    db, writer, locks = setup(
        "invalid-state",
        [
            ("AAA-111", "PENDING", 0, current),
            ("HMN-904", "FAILED", 1, "invalid-time"),
        ],
    )
    result = run_retryable_media_jobs(
        db_path=db,
        writer_lock_path=writer,
        title_lock_dir=locks,
        processor=lambda _dvd_id: (_ for _ in ()).throw(
            AssertionError("invalid target state was processed")
        ),
        target_dvd_id="HMN-904",
        now=now,
    )
    assert result["held_invalid_timestamp"] == 1
    assert result["jobs"][0]["status"] == "HELD_INVALID_TIMESTAMP"
    assert read_job(db, "HMN-904")["attempt_count"] == 1
    assert read_job(db, "AAA-111")["attempt_count"] == 0

    # Missing target returns an explicit result and never selects a fallback.
    db, writer, locks = setup(
        "missing",
        [("AAA-111", "PENDING", 0, current)],
    )
    result = run_retryable_media_jobs(
        db_path=db,
        writer_lock_path=writer,
        title_lock_dir=locks,
        processor=lambda _dvd_id: (_ for _ in ()).throw(
            AssertionError("missing target fell back")
        ),
        target_dvd_id="HMN-904",
        now=now,
    )
    assert result["target_status"] == "TARGET_NOT_FOUND"
    assert result["attempted"] == 0
    assert read_job(db, "AAA-111")["attempt_count"] == 0
    assert not writer.exists()

    # Invalid identifiers fail before any database or lock mutation.
    invalid_db = root / "target-invalid.sqlite3"
    invalid_writer = root / "target-invalid.writer.lock"
    try:
        run_retryable_media_jobs(
            db_path=invalid_db,
            writer_lock_path=invalid_writer,
            processor=lambda _dvd_id: None,
            target_dvd_id="HMN_904",
            now=now,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("invalid exact target accepted")
    assert not invalid_db.exists()
    assert not invalid_writer.exists()

    # A busy target lock holds only that target and leaves attempt accounting
    # untouched; it cannot select an unrelated eligible job.
    db, writer, locks = setup(
        "busy",
        [
            ("AAA-111", "PENDING", 0, current),
            ("HMN-904", "PENDING", 0, current),
        ],
    )
    held_lock = try_acquire_title_lock("HMN-904", lock_dir=locks)
    assert held_lock.status == ACQUIRED
    attempted = []
    try:
        result = run_retryable_media_jobs(
            db_path=db,
            writer_lock_path=writer,
            title_lock_dir=locks,
            processor=lambda dvd_id: attempted.append(dvd_id),
            target_dvd_id="HMN-904",
            now=now,
        )
    finally:
        held_lock.release()
    assert result["held_busy"] == 1 and result["attempted"] == 0
    assert result["jobs"][0]["status"] == "HELD_TITLE_BUSY"
    assert attempted == []
    assert read_job(db, "HMN-904")["attempt_count"] == 0
    assert read_job(db, "AAA-111")["attempt_count"] == 0

    # Processor failure records exactly one target attempt and does not alter
    # any unrelated media row.
    db, writer, locks = setup(
        "failed",
        [
            ("AAA-111", "PENDING", 0, current),
            ("HMN-904", "PENDING", 0, current),
        ],
    )
    result = run_retryable_media_jobs(
        db_path=db,
        writer_lock_path=writer,
        title_lock_dir=locks,
        processor=lambda _dvd_id: (_ for _ in ()).throw(
            RuntimeError("poster failure")
        ),
        target_dvd_id="HMN-904",
        now=now,
    )
    assert result["attempted"] == 1 and result["failed"] == 1
    assert read_job(db, "HMN-904")["status"] == "FAILED"
    assert read_job(db, "HMN-904")["attempt_count"] == 1
    assert read_job(db, "AAA-111")["status"] == "PENDING"
    assert read_job(db, "AAA-111")["attempt_count"] == 0


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
        exact_target_selector_smoke(root)

    print(
        "STAGE9_SEPARATE_MEDIA_DB_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
