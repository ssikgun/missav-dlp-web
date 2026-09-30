from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import fcntl
import sqlite3

from teddy_discovery_media_metadata import (
    DVD_ID_RE,
)
from teddy_title_exclusion import (
    ACQUIRED,
    BUSY,
    configured_lock_dir,
    try_acquire_title_lock,
)


MEDIA_SCHEMA = """
CREATE TABLE IF NOT EXISTS media_jobs (
    media_job_id INTEGER
        PRIMARY KEY AUTOINCREMENT,

    dvd_id TEXT NOT NULL
        UNIQUE,

    status TEXT NOT NULL
        CHECK (
            status IN (
                'PENDING',
                'RUNNING',
                'COMPLETED',
                'FAILED'
            )
        ),

    attempt_count INTEGER
        NOT NULL DEFAULT 0
        CHECK (
            attempt_count >= 0
        ),

    error TEXT,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS
    idx_media_jobs_status
ON media_jobs(
    status,
    media_job_id
);
"""

DEFAULT_MEDIA_MAX_ATTEMPTS = 5
DEFAULT_MEDIA_RETRY_BACKOFF_SECONDS = 3600
DEFAULT_MEDIA_RUNNING_STALE_SECONDS = 7200


def normalize_media_target_dvd_id(
    value,
) -> str:
    if not isinstance(value, str):
        raise ValueError(
            "invalid media target DVD-ID"
        )

    normalized = value.strip().upper()
    if not normalized or not DVD_ID_RE.fullmatch(normalized):
        raise ValueError(
            "invalid media target DVD-ID"
        )

    return normalized


def _utc_now() -> str:
    from datetime import (
        datetime,
        timezone,
    )

    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )


def _connect_media(
    path: str | Path,
) -> sqlite3.Connection:
    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    db = sqlite3.connect(
        path,
        timeout=30,
    )

    db.row_factory = sqlite3.Row

    db.execute(
        "PRAGMA journal_mode = WAL"
    )
    db.execute(
        "PRAGMA synchronous = NORMAL"
    )

    db.executescript(
        MEDIA_SCHEMA
    )

    return db


@contextmanager
def _media_transaction(
    db_path: str | Path,
    writer_lock_path: str | Path,
):
    lock_path = Path(
        writer_lock_path
    )

    lock_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with lock_path.open(
        "a+",
        encoding="utf-8",
    ) as lock:

        fcntl.flock(
            lock.fileno(),
            fcntl.LOCK_EX,
        )

        db = _connect_media(
            db_path
        )

        try:
            db.execute(
                "BEGIN IMMEDIATE"
            )

            yield db

            db.commit()

        except Exception:
            db.rollback()
            raise

        finally:
            db.close()

            fcntl.flock(
                lock.fileno(),
                fcntl.LOCK_UN,
            )


def reconcile_media_jobs(
    discovery_db_path: str | Path,
    media_db_path: str | Path,
    writer_lock_path: str | Path,
) -> int:
    """
    Find completed Stage9 organizer jobs in the
    Discovery DB and create missing jobs in the
    separate Media state DB.
    """

    discovery = sqlite3.connect(
        "file:"
        + str(Path(discovery_db_path))
        + "?mode=ro",
        uri=True,
    )

    discovery.row_factory = sqlite3.Row

    try:
        rows = discovery.execute(
            """
            SELECT
                oj.dvd_id,
                MAX(oj.job_id)
                    AS organizer_job_id
            FROM organizer_jobs AS oj
            JOIN holdings AS h
              ON h.dvd_id = oj.dvd_id
            WHERE oj.status = 'COMPLETED'
              AND oj.dvd_id IS NOT NULL
              AND h.storage_root = 'jav'
              AND h.present = 1
              AND h.discovered_by =
                    'completion-stage9'
            GROUP BY oj.dvd_id
            ORDER BY organizer_job_id
            """
        ).fetchall()

    finally:
        discovery.close()

    created = 0
    now = _utc_now()

    with _media_transaction(
        media_db_path,
        writer_lock_path,
    ) as media:

        for row in rows:
            dvd_id = str(
                row["dvd_id"] or ""
            ).strip().upper()

            if not dvd_id:
                continue

            cursor = media.execute(
                """
                INSERT OR IGNORE
                INTO media_jobs (
                    dvd_id,
                    status,
                    attempt_count,
                    error,
                    created_at,
                    updated_at
                )
                VALUES (
                    ?,
                    'PENDING',
                    0,
                    NULL,
                    ?,
                    ?
                )
                """,
                (
                    dvd_id,
                    now,
                    now,
                ),
            )

            if cursor.rowcount == 1:
                created += 1

    return created


def list_retryable_media_jobs(
    media_db_path: str | Path,
) -> list[dict]:
    db = sqlite3.connect(
        "file:"
        + str(Path(media_db_path))
        + "?mode=ro",
        uri=True,
    )

    db.row_factory = sqlite3.Row

    try:
        rows = db.execute(
            """
            SELECT
                media_job_id,
                dvd_id,
                status,
                attempt_count,
                error,
                created_at,
                updated_at
            FROM media_jobs
            WHERE status IN (
                'PENDING',
                'FAILED',
                'RUNNING'
            )
            ORDER BY media_job_id
            """
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:
        db.close()


def _get_media_job_for_target(
    media_db_path: str | Path,
    target_dvd_id: str,
) -> dict | None:
    path = Path(media_db_path).resolve()
    db = sqlite3.connect(
        "file:"
        + str(path)
        + "?mode=ro",
        uri=True,
    )

    db.row_factory = sqlite3.Row

    try:
        row = db.execute(
            """
            SELECT
                media_job_id,
                dvd_id,
                status,
                attempt_count,
                error,
                created_at,
                updated_at
            FROM media_jobs
            WHERE dvd_id = ?
            """,
            (target_dvd_id,),
        ).fetchone()

        return dict(row) if row is not None else None

    finally:
        db.close()


def _as_utc(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _now_utc(value=None):
    if value is None:
        return datetime.now(timezone.utc)
    parsed = value if hasattr(value, "tzinfo") else _as_utc(value)
    if parsed is None or parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def retry_eligibility(
    job,
    *,
    now=None,
    max_attempts=DEFAULT_MEDIA_MAX_ATTEMPTS,
    retry_backoff_seconds=DEFAULT_MEDIA_RETRY_BACKOFF_SECONDS,
    running_stale_seconds=DEFAULT_MEDIA_RUNNING_STALE_SECONDS,
):
    """Return ELIGIBLE or a bounded safe hold reason for one media job."""
    now_utc = _now_utc(now)
    try:
        attempts = int(job.get("attempt_count"))
        max_attempts = int(max_attempts)
        retry_backoff_seconds = int(retry_backoff_seconds)
        running_stale_seconds = int(running_stale_seconds)
    except (TypeError, ValueError):
        return "HELD_INVALID_STATE"
    if (
        attempts < 0
        or max_attempts < 1
        or retry_backoff_seconds < 0
        or running_stale_seconds < 1
    ):
        return "HELD_INVALID_STATE"
    status = job.get("status")
    if status == "COMPLETED":
        return "COMPLETED"
    if status not in {"PENDING", "FAILED", "RUNNING"}:
        return "HELD_INVALID_STATE"
    if attempts >= max_attempts:
        return "EXHAUSTED"
    if status == "PENDING":
        return "ELIGIBLE"
    updated = _as_utc(job.get("updated_at"))
    if updated is None:
        return "HELD_INVALID_TIMESTAMP"
    age = (now_utc - updated).total_seconds()
    if status == "FAILED":
        return "ELIGIBLE" if age >= retry_backoff_seconds else "HELD_BACKOFF"
    if status == "RUNNING":
        return "ELIGIBLE" if age >= running_stale_seconds else "HELD_FRESH_RUNNING"
    return "HELD_INVALID_STATE"


def _mark_running_if_unchanged(
    media_db_path,
    writer_lock_path,
    candidate,
    *,
    now,
    max_attempts,
    retry_backoff_seconds,
    running_stale_seconds,
) -> str:
    with _media_transaction(
        media_db_path,
        writer_lock_path,
    ) as db:
        current = db.execute(
            """
            SELECT media_job_id, dvd_id, status, attempt_count, updated_at
            FROM media_jobs
            WHERE media_job_id = ?
            """,
            (int(candidate["media_job_id"]),),
        ).fetchone()
        if current is None:
            return "HELD_CONFLICT"
        current = dict(current)
        expected = ("media_job_id", "dvd_id", "status", "attempt_count", "updated_at")
        if any(current[key] != candidate.get(key) for key in expected):
            return "HELD_CONFLICT"
        eligibility = retry_eligibility(
            current,
            now=now,
            max_attempts=max_attempts,
            retry_backoff_seconds=retry_backoff_seconds,
            running_stale_seconds=running_stale_seconds,
        )
        if eligibility != "ELIGIBLE":
            return eligibility
        now_stamp = now.astimezone(timezone.utc).isoformat(timespec="seconds")
        cursor = db.execute(
            """
            UPDATE media_jobs
            SET
                status = 'RUNNING',
                attempt_count =
                    attempt_count + 1,
                error = NULL,
                updated_at = ?
            WHERE media_job_id = ?
              AND dvd_id = ?
              AND status = ?
              AND attempt_count = ?
              AND updated_at = ?
            """,
            (
                now_stamp,
                int(candidate["media_job_id"]),
                candidate["dvd_id"],
                candidate["status"],
                int(candidate["attempt_count"]),
                candidate["updated_at"],
            ),
        )
        return "MARKED_RUNNING" if cursor.rowcount == 1 else "HELD_CONFLICT"


def _finish(
    media_db_path,
    writer_lock_path,
    media_job_id,
    *,
    status,
    error=None,
) -> None:
    if status not in {
        "COMPLETED",
        "FAILED",
    }:
        raise RuntimeError(
            "invalid media job final status"
        )

    with _media_transaction(
        media_db_path,
        writer_lock_path,
    ) as db:

        cursor = db.execute(
            """
            UPDATE media_jobs
            SET
                status = ?,
                error = ?,
                updated_at = ?
            WHERE media_job_id = ?
            """,
            (
                status,
                error,
                _utc_now(),
                int(media_job_id),
            ),
        )

        if cursor.rowcount != 1:
            raise RuntimeError(
                "media job missing"
            )


def run_retryable_media_jobs(
    *,
    db_path,
    writer_lock_path,
    processor,
    max_items=1,
    title_lock_dir=None,
    now=None,
    max_attempts=DEFAULT_MEDIA_MAX_ATTEMPTS,
    retry_backoff_seconds=DEFAULT_MEDIA_RETRY_BACKOFF_SECONDS,
    running_stale_seconds=DEFAULT_MEDIA_RUNNING_STALE_SECONDS,
    target_dvd_id=None,
) -> dict:
    if int(max_items) < 1:
        raise RuntimeError(
            "media max_items must be >= 1"
        )

    target = (
        normalize_media_target_dvd_id(
            target_dvd_id
        )
        if target_dvd_id is not None
        else None
    )

    now_utc = _now_utc(now)
    if target is None:
        jobs = list_retryable_media_jobs(
            db_path
        )
    else:
        target_job = _get_media_job_for_target(
            db_path,
            target,
        )
        if target_job is None:
            return {
                "target_dvd_id": target,
                "target_status": "TARGET_NOT_FOUND",
                "retryable": 0,
                "attempted": 0,
                "completed": 0,
                "failed": 0,
                "held_busy": 0,
                "held_lock_unavailable": 0,
                "held_backoff": 0,
                "held_fresh_running": 0,
                "held_invalid_timestamp": 0,
                "held_conflict": 0,
                "held_invalid_state": 0,
                "exhausted": 0,
                "jobs": [
                    {
                        "dvd_id": target,
                        "status": "TARGET_NOT_FOUND",
                    }
                ],
            }
        jobs = [target_job]

    states = [
        (
            job,
            retry_eligibility(
                job,
                now=now_utc,
                max_attempts=max_attempts,
                retry_backoff_seconds=retry_backoff_seconds,
                running_stale_seconds=running_stale_seconds,
            ),
        )
        for job in jobs
    ]
    result = {
        # Number eligible before acquiring title locks and rechecking rows.
        "retryable": sum(state == "ELIGIBLE" for _, state in states),
        "attempted": 0,
        "completed": 0,
        "failed": 0,
        "held_busy": 0,
        "held_lock_unavailable": 0,
        "held_backoff": sum(state == "HELD_BACKOFF" for _, state in states),
        "held_fresh_running": sum(state == "HELD_FRESH_RUNNING" for _, state in states),
        "held_invalid_timestamp": sum(state == "HELD_INVALID_TIMESTAMP" for _, state in states),
        "held_conflict": 0,
        "held_invalid_state": sum(state == "HELD_INVALID_STATE" for _, state in states),
        "exhausted": sum(state == "EXHAUSTED" for _, state in states),
        "jobs": [],
    }
    if target is not None:
        result["target_dvd_id"] = target

    lock_dir = title_lock_dir if title_lock_dir is not None else configured_lock_dir()
    for job, initial_state in states:
        if result["attempted"] >= int(max_items):
            break
        if initial_state != "ELIGIBLE":
            if target is not None:
                result["jobs"].append(
                    {
                        "dvd_id": target,
                        "status": initial_state,
                    }
                )
            continue
        job_id = int(
            job["media_job_id"]
        )

        dvd_id = str(
            job["dvd_id"]
        )

        title_lock = try_acquire_title_lock(dvd_id, lock_dir=lock_dir)
        if title_lock.status == BUSY:
            result["held_busy"] += 1
            result["jobs"].append({"dvd_id": dvd_id, "status": "HELD_TITLE_BUSY"})
            continue
        if title_lock.status != ACQUIRED:
            result["held_lock_unavailable"] += 1
            result["jobs"].append({"dvd_id": dvd_id, "status": "TITLE_LOCK_UNAVAILABLE"})
            continue

        with title_lock:
            marked = _mark_running_if_unchanged(
                db_path,
                writer_lock_path,
                job,
                now=now_utc,
                max_attempts=max_attempts,
                retry_backoff_seconds=retry_backoff_seconds,
                running_stale_seconds=running_stale_seconds,
            )
            if marked != "MARKED_RUNNING":
                if marked == "HELD_CONFLICT":
                    result["held_conflict"] += 1
                elif marked == "HELD_BACKOFF":
                    result["held_backoff"] += 1
                elif marked == "HELD_FRESH_RUNNING":
                    result["held_fresh_running"] += 1
                elif marked == "HELD_INVALID_TIMESTAMP":
                    result["held_invalid_timestamp"] += 1
                elif marked == "EXHAUSTED":
                    result["exhausted"] += 1
                else:
                    result["held_invalid_state"] += 1
                result["jobs"].append({"dvd_id": dvd_id, "status": marked})
                continue

            result["attempted"] += 1
            try:
                payload = processor(dvd_id)
            except Exception as exc:
                message = str(exc)[:2000]
                _finish(
                    db_path,
                    writer_lock_path,
                    job_id,
                    status="FAILED",
                    error=message,
                )
                result["failed"] += 1
                result["jobs"].append({"dvd_id": dvd_id, "status": "FAILED"})
                continue

            _finish(
                db_path,
                writer_lock_path,
                job_id,
                status="COMPLETED",
            )
            result["completed"] += 1
            result["jobs"].append(
                {"dvd_id": dvd_id, "status": "COMPLETED", "result": payload}
            )

    return result
