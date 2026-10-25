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
    _media_transaction,
    _bind_media_job_context,
    claim_jellyfin_created_notification,
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

    artifact_old = {
        "status": "COMPLETED",
        "nfo_status": "COMPLETE",
        "poster_status": "FAILED",
        "attempt_count": 1,
        "updated_at": backoff,
    }
    assert retry_eligibility(artifact_old, now=now) == "ELIGIBLE"
    artifact_old["updated_at"] = fresh
    assert retry_eligibility(artifact_old, now=now) == "HELD_BACKOFF"
    artifact_old["poster_status"] = "RUNNING"
    artifact_old["updated_at"] = fresh
    assert retry_eligibility(artifact_old, now=now) == "HELD_FRESH_RUNNING"
    artifact_old["updated_at"] = stale
    assert retry_eligibility(artifact_old, now=now) == "ELIGIBLE"
    artifact_old["attempt_count"] = 5
    assert retry_eligibility(artifact_old, now=now) == "EXHAUSTED"

    jellyfin_check = {
        "status": "COMPLETED",
        "nfo_status": "COMPLETE",
        "poster_status": "COMPLETE",
        "attempt_count": 2,
        "jellyfin_notification_status": "NOTIFIED",
        "jellyfin_recovery_status": "CHECK_PENDING",
        "jellyfin_next_check_at": (now + timedelta(seconds=3600)).isoformat(),
        "updated_at": backoff,
    }
    assert retry_eligibility(jellyfin_check, now=now) == "HELD_BACKOFF"
    jellyfin_check["jellyfin_next_check_at"] = (now - timedelta(seconds=1)).isoformat()
    assert retry_eligibility(jellyfin_check, now=now) == "ELIGIBLE"
    jellyfin_check["attempt_count"] = 5
    assert retry_eligibility(jellyfin_check, now=now) == "EXHAUSTED"


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


def artifact_retry_and_migration_smoke(root):
    now = datetime.now(timezone.utc)
    db_path = root / "artifact-retry.sqlite3"
    writer = root / "artifact-retry.writer.lock"
    locks = root / "artifact-retry-locks"
    locks.mkdir()
    old = (now - timedelta(seconds=3601)).isoformat()
    add_job(db_path, "RST-333", "COMPLETED", 1, old)
    db = sqlite3.connect(db_path)
    db.execute(
        """UPDATE media_jobs SET nfo_status='COMPLETE', poster_status='FAILED',
           poster_error='POSTER_FETCH_FAILED:TimeoutError' WHERE dvd_id='RST-333'"""
    )
    db.commit()
    db.close()

    failed = run_retryable_media_jobs(
        db_path=db_path,
        writer_lock_path=writer,
        title_lock_dir=locks,
        processor=lambda _dvd_id: (_ for _ in ()).throw(TimeoutError("retry failure")),
        target_dvd_id="RST-333",
        now=now,
    )
    assert failed["completed"] == 1 and failed["failed"] == 0
    row = read_job(db_path, "RST-333")
    assert row["status"] == "COMPLETED"
    assert row["nfo_status"] == "COMPLETE"
    assert row["poster_status"] == "FAILED"
    assert row["attempt_count"] == 2

    held = run_retryable_media_jobs(
        db_path=db_path,
        writer_lock_path=writer,
        title_lock_dir=locks,
        processor=lambda _dvd_id: {"unexpected": True},
        target_dvd_id="RST-333",
        now=now,
    )
    assert held["held_backoff"] == 1 and held["attempted"] == 0

    completed = run_retryable_media_jobs(
        db_path=db_path,
        writer_lock_path=writer,
        title_lock_dir=locks,
        processor=lambda _dvd_id: {
            "nfo_status": "COMPLETE",
            "poster_status": "COMPLETE",
        },
        target_dvd_id="RST-333",
        now=datetime.now(timezone.utc) + timedelta(seconds=3601),
    )
    assert completed["completed"] == 1
    row = read_job(db_path, "RST-333")
    assert row["status"] == "COMPLETED"
    assert row["nfo_status"] == "COMPLETE"
    assert row["poster_status"] == "COMPLETE"
    assert row["attempt_count"] == 3

    notice_db = root / "notice-state.sqlite3"
    notice_lock = root / "notice-state.lock"
    add_job(notice_db, "UVW-555", "PENDING", 0, now.isoformat())
    notice_row = read_job(notice_db, "UVW-555")
    context = {
        "db_path": notice_db,
        "writer_lock_path": notice_lock,
        "media_job_id": notice_row["media_job_id"],
        "dvd_id": "UVW-555",
        "jellyfin_notification_status": "UNKNOWN",
    }
    with _bind_media_job_context(context):
        assert claim_jellyfin_created_notification()
        assert not claim_jellyfin_created_notification()
    notice = read_job(notice_db, "UVW-555")
    assert notice["jellyfin_notification_status"] == "ATTEMPTED"
    assert notice["jellyfin_recovery_status"] == "CHECK_PENDING"
    assert notice["jellyfin_next_check_at"] is not None

    # Simulate a pre-change database. Migration adds UNKNOWN state without
    # changing completed status or the historical retry counter.
    legacy_db = root / "legacy-media.sqlite3"
    legacy_lock = root / "legacy-media.lock"
    connection = sqlite3.connect(legacy_db)
    connection.executescript(
        """CREATE TABLE media_jobs (
               media_job_id INTEGER PRIMARY KEY AUTOINCREMENT,
               dvd_id TEXT NOT NULL UNIQUE,
               status TEXT NOT NULL,
               attempt_count INTEGER NOT NULL DEFAULT 0,
               error TEXT,
               created_at TEXT NOT NULL,
               updated_at TEXT NOT NULL
           );
           CREATE INDEX idx_media_jobs_status ON media_jobs(status,media_job_id);"""
    )
    connection.execute(
        """INSERT INTO media_jobs
           (dvd_id,status,attempt_count,error,created_at,updated_at)
           VALUES('OLD-777','COMPLETED',4,NULL,?,?)""",
        (now.isoformat(), now.isoformat()),
    )
    for dvd_id, status, attempts, error in (
        ("OLD-778", "PENDING", 2, "pending-evidence"),
        ("OLD-779", "FAILED", 3, "failed-evidence"),
        ("OLD-780", "RUNNING", 1, "running-evidence"),
    ):
        connection.execute(
            """INSERT INTO media_jobs
               (dvd_id,status,attempt_count,error,created_at,updated_at)
               VALUES(?,?,?,?,?,?)""",
            (dvd_id, status, attempts, error, now.isoformat(), now.isoformat()),
        )
    connection.commit()
    connection.close()
    with _media_transaction(legacy_db, legacy_lock) as migrated:
        migrated_row = dict(
            migrated.execute(
                "SELECT * FROM media_jobs WHERE dvd_id='OLD-777'"
            ).fetchone()
        )
    assert migrated_row["status"] == "COMPLETED"
    assert migrated_row["attempt_count"] == 4
    assert migrated_row["nfo_status"] == "UNKNOWN"
    assert migrated_row["poster_status"] == "UNKNOWN"
    assert migrated_row["jellyfin_notification_status"] == "UNKNOWN"
    assert migrated_row["jellyfin_recovery_status"] == "UNKNOWN"
    assert migrated_row["jellyfin_next_check_at"] is None
    connection = sqlite3.connect(legacy_db)
    connection.execute(
        """INSERT INTO media_jobs
           (dvd_id,status,attempt_count,error,nfo_status,poster_status,
            jellyfin_notification_status,created_at,updated_at)
           VALUES('OLD-781','COMPLETED',2,NULL,'COMPLETE','COMPLETE',
                  'ATTEMPTED',?,?)""",
        (now.isoformat(), old),
    )
    connection.commit()
    connection.close()
    migrated_rows = {row["dvd_id"]: row for row in list_retryable_media_jobs(legacy_db)}
    assert set(migrated_rows) == {"OLD-778", "OLD-779", "OLD-780", "OLD-781"}
    for dvd_id, status, attempts, error in (
        ("OLD-778", "PENDING", 2, "pending-evidence"),
        ("OLD-779", "FAILED", 3, "failed-evidence"),
        ("OLD-780", "RUNNING", 1, "running-evidence"),
    ):
        migrated = migrated_rows[dvd_id]
        assert (migrated["status"], migrated["attempt_count"], migrated["error"]) == (
            status, attempts, error
        )
    legacy_notification = migrated_rows["OLD-781"]
    assert legacy_notification["jellyfin_notification_status"] == "ATTEMPTED"
    assert legacy_notification["jellyfin_recovery_status"] == "UNKNOWN"
    assert retry_eligibility(legacy_notification, now=now) == "ELIGIBLE"


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



def current_input_guard_smoke(root):
    from teddy_discovery_media_metadata import media_input_eligibility

    now = datetime.now(timezone.utc)
    old = (now - timedelta(seconds=3601)).isoformat()
    current = now.isoformat()

    def setup(name, status, cover, *, error=None, attempts=1, other=False):
        case = root / ("input-" + name)
        case.mkdir()
        discovery = case / "discovery.sqlite3"
        media = case / "media.sqlite3"
        locks = case / "title-locks"
        locks.mkdir()
        db = sqlite3.connect(discovery)
        db.execute("CREATE TABLE titles(dvd_id TEXT PRIMARY KEY, cover_url TEXT)")
        if cover != "NO_TITLE":
            db.execute("INSERT INTO titles VALUES(?,?)", ("HMN-904", cover))
        if other:
            db.execute("INSERT INTO titles VALUES(?,?)", ("AAA-111", "https://cover.example/a.jpg"))
        db.commit()
        db.close()
        add_job(media, "HMN-904", status, attempts, old if status == "FAILED" else current)
        if other:
            add_job(media, "AAA-111", "PENDING", 0, current)
        if error:
            db = sqlite3.connect(media)
            db.execute("UPDATE media_jobs SET error=? WHERE dvd_id='HMN-904'", (error,))
            db.commit()
            db.close()
        return discovery, media, case / "media.lock", locks

    def run_case(name, status, cover, expected, *, error=None, attempts=1, other=False):
        discovery, media, writer, locks = setup(name, status, cover, error=error, attempts=attempts, other=other)
        before = read_job(media, "HMN-904")
        unrelated = read_job(media, "AAA-111") if other else None
        called = []

        def processor(dvd_id):
            called.append(dvd_id)
            if expected == "NFO_ONLY":
                return {
                    "nfo_status": "COMPLETE",
                    "poster_status": "PENDING",
                    "poster_error": "COVER_URL_MISSING",
                }
            return {"ok": True}

        result = run_retryable_media_jobs(
            db_path=media, discovery_db_path=discovery, writer_lock_path=writer,
            title_lock_dir=locks, target_dvd_id="HMN-904", max_items=1,
            processor=processor, now=now,
        )
        expected_input = (
            "HELD_COVER_URL_MISSING" if expected == "NFO_ONLY" else expected
        )
        assert media_input_eligibility(discovery, "HMN-904") == expected_input
        runnable = expected in {"READY", "NFO_ONLY"}
        assert result["jobs"][0]["status"] == ("COMPLETED" if runnable else expected)
        if runnable:
            assert result["attempted"] == 1 and called == ["HMN-904"]
            assert read_job(media, "HMN-904")["attempt_count"] == attempts + 1
        else:
            assert result["attempted"] == 0 and called == []
            assert read_job(media, "HMN-904") == before
            assert result[{
                "HELD_METADATA_NOT_FOUND": "held_metadata_not_found",
                "HELD_COVER_URL_MISSING": "held_cover_url_missing",
                "HELD_COVER_URL_INVALID": "held_cover_url_invalid",
            }[expected]] == 1
        if other:
            assert read_job(media, "AAA-111") == unrelated
        return discovery, media, writer, locks

    # Old error text is never used for current input decisions.
    discovery, media, writer, locks = run_case(
        "old-missing-still-missing", "FAILED", None, "NFO_ONLY",
        error="cover_url missing: HMN-904", other=True,
    )
    db = sqlite3.connect(discovery)
    db.execute("UPDATE titles SET cover_url=? WHERE dvd_id='HMN-904'", ("https://cover.example/now.jpg",))
    db.commit()
    db.close()
    assert media_input_eligibility(discovery, "HMN-904") == "READY"
    result = run_retryable_media_jobs(
        db_path=media, discovery_db_path=discovery, writer_lock_path=writer,
        title_lock_dir=locks, target_dvd_id="HMN-904", max_items=1,
        processor=lambda dvd_id: {
            "nfo_status": "COMPLETE",
            "poster_status": "COMPLETE",
        }, now=now,
    )
    assert result["completed"] == 1 and read_job(media, "HMN-904")["attempt_count"] == 3
    assert read_job(media, "AAA-111")["attempt_count"] == 0

    run_case("reset-ready", "FAILED", "https://cover.example/poster.jpg", "READY", error="Connection reset by peer")
    run_case("reset-missing", "FAILED", None, "NFO_ONLY", error="Connection reset by peer")
    run_case("pending-missing", "PENDING", "", "NFO_ONLY", attempts=0)
    run_case("pending-ready", "PENDING", "http://cover.example/poster.png", "READY", attempts=0)
    for index, value in enumerate(("ftp://cover.example/a", "https:///a", "https://cover.example:bad/a", "https://cover.example/a b", "https://user:pass@cover.example/a", "https://cover.example/%ZZ")):
        run_case("invalid-" + str(index), "FAILED", value, "HELD_COVER_URL_INVALID", other=True)
    run_case("metadata-missing", "PENDING", "NO_TITLE", "HELD_METADATA_NOT_FOUND", attempts=0, other=True)

    # A missing cover does not hold first-time NFO generation.
    discovery, media, writer, locks = setup("normal-selection", "PENDING", None, attempts=0, other=True)
    called = []
    result = run_retryable_media_jobs(
        db_path=media, discovery_db_path=discovery, writer_lock_path=writer,
        title_lock_dir=locks, processor=lambda dvd_id: called.append(dvd_id), max_items=1, now=now,
    )
    assert result["held_cover_url_missing"] == 0 and result["attempted"] == 1
    assert called == ["HMN-904"] and read_job(media, "HMN-904")["attempt_count"] == 1
    assert read_job(media, "AAA-111")["attempt_count"] == 0

    # The current input is read under the title lock, after retry eligibility.
    import teddy_discovery_media_jobs as media_module
    discovery, media, writer, locks = setup("guard-order", "FAILED", "https://cover.example/a")
    real_guard = media_module.media_input_eligibility
    observed = []
    def locked_guard(path, dvd_id):
        contender = try_acquire_title_lock(dvd_id, lock_dir=locks)
        observed.append(contender.status)
        contender.release()
        return real_guard(path, dvd_id)
    media_module.media_input_eligibility = locked_guard
    try:
        result = run_retryable_media_jobs(
            db_path=media, discovery_db_path=discovery, writer_lock_path=writer,
            title_lock_dir=locks, target_dvd_id="HMN-904",
            processor=lambda dvd_id: {"ok": dvd_id}, now=now,
        )
    finally:
        media_module.media_input_eligibility = real_guard
    assert observed == [BUSY] and result["completed"] == 1

    discovery, media, writer, locks = setup("backoff-before-input", "FAILED", None)
    db = sqlite3.connect(media)
    db.execute("UPDATE media_jobs SET updated_at=? WHERE dvd_id='HMN-904'", (current,))
    db.commit()
    db.close()
    media_module.media_input_eligibility = lambda *_args: (_ for _ in ()).throw(
        AssertionError("backoff bypassed before current-input guard")
    )
    try:
        result = run_retryable_media_jobs(
            db_path=media, discovery_db_path=discovery, writer_lock_path=writer,
            title_lock_dir=locks, target_dvd_id="HMN-904",
            processor=lambda dvd_id: {"unexpected": dvd_id}, now=now,
        )
    finally:
        media_module.media_input_eligibility = real_guard
    assert result["held_backoff"] == 1 and result["attempted"] == 0

    # A completed NFO with no current cover waits without consuming attempts.
    discovery, media, writer, locks = setup("completed-nfo-missing", "COMPLETED", None)
    db = sqlite3.connect(media)
    db.execute(
        """UPDATE media_jobs SET nfo_status='COMPLETE', poster_status='PENDING'
           WHERE dvd_id='HMN-904'"""
    )
    db.commit()
    db.close()
    called = []
    result = run_retryable_media_jobs(
        db_path=media, discovery_db_path=discovery, writer_lock_path=writer,
        title_lock_dir=locks, target_dvd_id="HMN-904",
        processor=lambda dvd_id: called.append(dvd_id), now=now,
    )
    assert result["held_cover_url_missing"] == 1
    assert result["attempted"] == 0 and called == []
    assert read_job(media, "HMN-904")["status"] == "COMPLETED"
    assert read_job(media, "HMN-904")["attempt_count"] == 1

    print("CURRENT_INPUT_GUARD_SMOKE=PASS")


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
        artifact_retry_and_migration_smoke(root)
        conditional_race_smoke(root)
        exact_target_selector_smoke(root)
        current_input_guard_smoke(root)

    print(
        "STAGE9_SEPARATE_MEDIA_DB_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
