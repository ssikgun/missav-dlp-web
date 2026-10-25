from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from pathlib import Path
import fcntl
import sqlite3

from teddy_discovery_media_metadata import (
    DVD_ID_RE,
    media_input_eligibility,
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

    nfo_status TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (nfo_status IN ('UNKNOWN', 'PENDING', 'COMPLETE', 'ATTENTION')),

    poster_status TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (poster_status IN ('UNKNOWN', 'PENDING', 'RUNNING', 'FAILED', 'COMPLETE', 'ATTENTION')),

    poster_error TEXT,

    jellyfin_notification_status TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (jellyfin_notification_status IN ('UNKNOWN', 'ATTEMPTED', 'NOTIFIED', 'VISIBLE', 'ATTENTION')),

    jellyfin_error TEXT,

    jellyfin_recovery_status TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (jellyfin_recovery_status IN (
            'UNKNOWN', 'CHECK_PENDING', 'VISIBLE', 'ATTENTION',
            'MANUAL_ACTION_REQUIRED'
        )),

    jellyfin_next_check_at TEXT,

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

_MEDIA_JOB_CONTEXT = ContextVar("stage9_media_job_context", default=None)


def current_media_job_context():
    """Return the active retry context for Stage9 pipeline integrations."""
    return _MEDIA_JOB_CONTEXT.get()


def _utc_after(seconds: int, now=None) -> str:
    base = _now_utc(now) if now is not None else datetime.now(timezone.utc)
    return (base + timedelta(seconds=int(seconds))).isoformat(
        timespec="seconds"
    )


@contextmanager
def _bind_media_job_context(context):
    token = _MEDIA_JOB_CONTEXT.set(context)
    try:
        yield
    finally:
        _MEDIA_JOB_CONTEXT.reset(token)


def claim_jellyfin_created_notification() -> bool:
    """Persist an at-most-once Created intent before calling Jellyfin."""
    context = current_media_job_context()
    if context is None:
        return True
    if context.get("jellyfin_notification_status") != "UNKNOWN":
        return False

    with _media_transaction(
        context["db_path"],
        context["writer_lock_path"],
    ) as db:
        cursor = db.execute(
            """UPDATE media_jobs
               SET jellyfin_notification_status='ATTEMPTED',
                   jellyfin_recovery_status='CHECK_PENDING',
                   jellyfin_next_check_at=?,
                   jellyfin_error=NULL
               WHERE media_job_id=?
                 AND jellyfin_notification_status='UNKNOWN'
                 AND jellyfin_recovery_status='UNKNOWN'""",
            (
                _utc_after(
                    DEFAULT_MEDIA_RETRY_BACKOFF_SECONDS,
                    context.get("now"),
                ),
                int(context["media_job_id"]),
            ),
        )
    if cursor.rowcount == 1:
        context["jellyfin_notification_status"] = "ATTEMPTED"
        context["jellyfin_recovery_status"] = "CHECK_PENDING"
        return True
    return False


def record_jellyfin_notification_status(
    status: str,
    error: str | None = None,
) -> None:
    context = current_media_job_context()
    if context is None:
        return
    if status not in {"NOTIFIED", "VISIBLE", "ATTENTION"}:
        raise ValueError("invalid Jellyfin notification state")

    with _media_transaction(
        context["db_path"],
        context["writer_lock_path"],
    ) as db:
        recovery_status = "CHECK_PENDING" if status == "NOTIFIED" else status
        next_check = (
            _utc_after(
                DEFAULT_MEDIA_RETRY_BACKOFF_SECONDS,
                context.get("now"),
            )
            if status == "NOTIFIED"
            else None
        )
        cursor = db.execute(
            """UPDATE media_jobs
               SET jellyfin_notification_status=?, jellyfin_error=?,
                   jellyfin_recovery_status=?, jellyfin_next_check_at=?
               WHERE media_job_id=?""",
            (
                status,
                str(error or "")[:500] or None,
                recovery_status,
                next_check,
                int(context["media_job_id"]),
            ),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("Jellyfin recovery state changed concurrently")
    context["jellyfin_notification_status"] = status
    context["jellyfin_recovery_status"] = recovery_status
    context["jellyfin_next_check_at"] = next_check


def record_jellyfin_visibility_pending(error: str | None = None) -> str:
    """Schedule a bounded exact-visibility recheck; never resend Created."""
    context = current_media_job_context()
    if context is None:
        return "CHECK_PENDING"
    attempts = int(context.get("attempt_count", 0))
    max_attempts = int(context.get("max_attempts", DEFAULT_MEDIA_MAX_ATTEMPTS))
    recovery_status = (
        "MANUAL_ACTION_REQUIRED" if attempts >= max_attempts else "CHECK_PENDING"
    )
    next_check = (
        None
        if recovery_status == "MANUAL_ACTION_REQUIRED"
        else _utc_after(
            DEFAULT_MEDIA_RETRY_BACKOFF_SECONDS,
            context.get("now"),
        )
    )
    detail = str(error or "EXACT_PATH_NOT_VISIBLE")
    if recovery_status == "MANUAL_ACTION_REQUIRED":
        detail = "MANUAL_ACTION_REQUIRED: " + detail
    detail = detail[:500]

    with _media_transaction(
        context["db_path"],
        context["writer_lock_path"],
    ) as db:
        cursor = db.execute(
            """UPDATE media_jobs
               SET jellyfin_recovery_status=?, jellyfin_next_check_at=?,
                   jellyfin_error=?
               WHERE media_job_id=?
                 AND jellyfin_notification_status IN ('ATTEMPTED', 'NOTIFIED')
                 AND jellyfin_recovery_status IN ('UNKNOWN', 'CHECK_PENDING')""",
            (
                recovery_status,
                next_check,
                detail,
                int(context["media_job_id"]),
            ),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("Jellyfin recovery state changed concurrently")
    context["jellyfin_recovery_status"] = recovery_status
    context["jellyfin_next_check_at"] = next_check
    return recovery_status


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

    _migrate_media_artifact_columns(db)

    return db


def _migrate_media_artifact_columns(db: sqlite3.Connection) -> None:
    """Additive migration: legacy artifact outcomes remain explicitly unknown."""
    required = {
        "nfo_status": "TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK (nfo_status IN ('UNKNOWN', 'PENDING', 'COMPLETE', 'ATTENTION'))",
        "poster_status": "TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK (poster_status IN ('UNKNOWN', 'PENDING', 'RUNNING', 'FAILED', 'COMPLETE', 'ATTENTION'))",
        "poster_error": "TEXT",
        "jellyfin_notification_status": "TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK (jellyfin_notification_status IN ('UNKNOWN', 'ATTEMPTED', 'NOTIFIED', 'VISIBLE', 'ATTENTION'))",
        "jellyfin_error": "TEXT",
        "jellyfin_recovery_status": "TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK (jellyfin_recovery_status IN ('UNKNOWN', 'CHECK_PENDING', 'VISIBLE', 'ATTENTION', 'MANUAL_ACTION_REQUIRED'))",
        "jellyfin_next_check_at": "TEXT",
    }
    existing = {
        str(row[1])
        for row in db.execute("PRAGMA table_info(media_jobs)")
    }
    missing = [name for name in required if name not in existing]
    db.execute("BEGIN IMMEDIATE")
    try:
        for name in missing:
            db.execute(
                "ALTER TABLE media_jobs ADD COLUMN "
                + name
                + " "
                + required[name]
            )
        db.execute(
            """CREATE INDEX IF NOT EXISTS idx_media_jobs_poster_retry
               ON media_jobs(status, nfo_status, poster_status, updated_at)"""
        )
        db.commit()
    except Exception:
        db.rollback()
        raise


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
                    nfo_status,
                    poster_status,
                    jellyfin_notification_status,
                    created_at,
                    updated_at
                )
                VALUES (
                    ?,
                    'PENDING',
                    0,
                    NULL,
                    'PENDING',
                    'PENDING',
                    'UNKNOWN',
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
                nfo_status,
                poster_status,
                poster_error,
                jellyfin_notification_status,
                jellyfin_error,
                jellyfin_recovery_status,
                jellyfin_next_check_at,
                created_at,
                updated_at
            FROM media_jobs
            WHERE status IN (
                'PENDING',
                'FAILED',
                'RUNNING'
            )
               OR (status='COMPLETED'
                   AND nfo_status='COMPLETE'
                   AND (poster_status IN ('PENDING', 'FAILED', 'RUNNING')
                        OR jellyfin_recovery_status='CHECK_PENDING'
                        OR (jellyfin_recovery_status='UNKNOWN'
                            AND jellyfin_notification_status IN ('ATTEMPTED', 'NOTIFIED'))))
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
                nfo_status,
                poster_status,
                poster_error,
                jellyfin_notification_status,
                jellyfin_error,
                jellyfin_recovery_status,
                jellyfin_next_check_at,
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


def _jellyfin_visibility_due(job, retry_backoff_seconds):
    raw_due = job.get("jellyfin_next_check_at")
    if raw_due is not None:
        return _as_utc(raw_due)
    updated = _as_utc(job.get("updated_at"))
    if updated is None:
        return None
    return updated + timedelta(seconds=retry_backoff_seconds)


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
    notification_status = job.get("jellyfin_notification_status", "UNKNOWN")
    recovery_status = job.get("jellyfin_recovery_status", "UNKNOWN")
    legacy_notification_pending = (
        recovery_status == "UNKNOWN"
        and notification_status in {"ATTEMPTED", "NOTIFIED"}
    )
    visibility_check_pending = (
        recovery_status == "CHECK_PENDING" or legacy_notification_pending
    )
    if status == "COMPLETED":
        poster_status = job.get("poster_status", "UNKNOWN")
        poster_retry_pending = (
            job.get("nfo_status") == "COMPLETE"
            and poster_status in {"PENDING", "FAILED", "RUNNING"}
        )
        if not poster_retry_pending and not visibility_check_pending:
            return "COMPLETED"
        if attempts >= max_attempts:
            return "EXHAUSTED"
        if visibility_check_pending:
            due = _jellyfin_visibility_due(job, retry_backoff_seconds)
            if due is None and not poster_retry_pending:
                return "HELD_INVALID_TIMESTAMP"
            if due is not None and now_utc >= due:
                return "ELIGIBLE"
            if not poster_retry_pending:
                return "HELD_BACKOFF"
        if poster_status == "PENDING":
            return "ELIGIBLE"
        updated = _as_utc(job.get("updated_at"))
        if updated is None:
            return "HELD_INVALID_TIMESTAMP"
        age = (now_utc - updated).total_seconds()
        if poster_status == "FAILED":
            return "ELIGIBLE" if age >= retry_backoff_seconds else "HELD_BACKOFF"
        if poster_status == "RUNNING":
            return "ELIGIBLE" if age >= running_stale_seconds else "HELD_FRESH_RUNNING"
        return "HELD_INVALID_STATE"
    if status not in {"PENDING", "FAILED", "RUNNING"}:
        return "HELD_INVALID_STATE"
    if attempts >= max_attempts:
        return "EXHAUSTED"
    if status == "PENDING":
        if visibility_check_pending:
            due = _jellyfin_visibility_due(job, retry_backoff_seconds)
            if due is None:
                return "HELD_INVALID_TIMESTAMP"
            if now_utc < due:
                return "HELD_BACKOFF"
        return "ELIGIBLE"
    updated = _as_utc(job.get("updated_at"))
    if updated is None:
        return "HELD_INVALID_TIMESTAMP"
    age = (now_utc - updated).total_seconds()
    if status == "FAILED":
        if age < retry_backoff_seconds:
            return "HELD_BACKOFF"
        if visibility_check_pending:
            due = _jellyfin_visibility_due(job, retry_backoff_seconds)
            if due is None:
                return "HELD_INVALID_TIMESTAMP"
            if now_utc < due:
                return "HELD_BACKOFF"
        return "ELIGIBLE"
    if status == "RUNNING":
        if age < running_stale_seconds:
            return "HELD_FRESH_RUNNING"
        if visibility_check_pending:
            due = _jellyfin_visibility_due(job, retry_backoff_seconds)
            if due is None:
                return "HELD_INVALID_TIMESTAMP"
            if now_utc < due:
                return "HELD_BACKOFF"
        return "ELIGIBLE"
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
            SELECT media_job_id, dvd_id, status, attempt_count, updated_at,
                   nfo_status, poster_status, jellyfin_notification_status,
                   jellyfin_recovery_status, jellyfin_next_check_at
            FROM media_jobs
            WHERE media_job_id = ?
            """,
            (int(candidate["media_job_id"]),),
        ).fetchone()
        if current is None:
            return "HELD_CONFLICT"
        current = dict(current)
        expected = (
            "media_job_id",
            "dvd_id",
            "status",
            "attempt_count",
            "updated_at",
            "nfo_status",
            "poster_status",
            "jellyfin_notification_status",
            "jellyfin_recovery_status",
            "jellyfin_next_check_at",
        )
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
        if (
            current["status"] == "COMPLETED"
            and current["nfo_status"] == "COMPLETE"
            and current["poster_status"] in {"PENDING", "FAILED", "RUNNING"}
        ):
            cursor = db.execute(
                """UPDATE media_jobs
                   SET poster_status='RUNNING',
                       attempt_count=attempt_count+1, updated_at=?,
                       jellyfin_recovery_status=CASE
                           WHEN jellyfin_recovery_status='UNKNOWN'
                            AND jellyfin_notification_status IN ('ATTEMPTED','NOTIFIED')
                           THEN 'CHECK_PENDING'
                           ELSE jellyfin_recovery_status END,
                       jellyfin_next_check_at=CASE
                           WHEN jellyfin_recovery_status='UNKNOWN'
                            AND jellyfin_notification_status IN ('ATTEMPTED','NOTIFIED')
                            AND jellyfin_next_check_at IS NULL
                           THEN ? ELSE jellyfin_next_check_at END
                   WHERE media_job_id=? AND dvd_id=? AND status='COMPLETED'
                     AND attempt_count=? AND updated_at=?
                     AND nfo_status='COMPLETE' AND poster_status=?
                     AND jellyfin_notification_status=?
                     AND jellyfin_recovery_status=?
                     AND jellyfin_next_check_at IS ?""",
                (
                    now_stamp,
                    now_stamp,
                    int(candidate["media_job_id"]),
                    candidate["dvd_id"],
                    int(candidate["attempt_count"]),
                    candidate["updated_at"],
                    candidate["poster_status"],
                    candidate["jellyfin_notification_status"],
                    candidate["jellyfin_recovery_status"],
                    candidate["jellyfin_next_check_at"],
                ),
            )
            return "MARKED_RUNNING" if cursor.rowcount == 1 else "HELD_CONFLICT"
        if current["status"] == "COMPLETED" and current["nfo_status"] == "COMPLETE":
            cursor = db.execute(
                """UPDATE media_jobs
                   SET status='RUNNING', attempt_count=attempt_count+1,
                       error=NULL, updated_at=?,
                       jellyfin_recovery_status=CASE
                           WHEN jellyfin_recovery_status='UNKNOWN'
                            AND jellyfin_notification_status IN ('ATTEMPTED','NOTIFIED')
                           THEN 'CHECK_PENDING'
                           ELSE jellyfin_recovery_status END,
                       jellyfin_next_check_at=CASE
                           WHEN jellyfin_recovery_status='UNKNOWN'
                            AND jellyfin_notification_status IN ('ATTEMPTED','NOTIFIED')
                            AND jellyfin_next_check_at IS NULL
                           THEN ? ELSE jellyfin_next_check_at END
                   WHERE media_job_id=? AND dvd_id=? AND status='COMPLETED'
                     AND attempt_count=? AND updated_at=?
                     AND nfo_status='COMPLETE' AND poster_status=?
                     AND jellyfin_notification_status=?
                     AND jellyfin_recovery_status=?
                     AND jellyfin_next_check_at IS ?""",
                (
                    now_stamp,
                    now_stamp,
                    int(candidate["media_job_id"]),
                    candidate["dvd_id"],
                    int(candidate["attempt_count"]),
                    candidate["updated_at"],
                    candidate["poster_status"],
                    candidate["jellyfin_notification_status"],
                    candidate["jellyfin_recovery_status"],
                    candidate["jellyfin_next_check_at"],
                ),
            )
            return "MARKED_RUNNING" if cursor.rowcount == 1 else "HELD_CONFLICT"
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
                AND nfo_status = ?
                AND poster_status = ?
                AND jellyfin_notification_status = ?
                AND jellyfin_recovery_status = ?
                AND jellyfin_next_check_at IS ?
            """,
            (
                now_stamp,
                int(candidate["media_job_id"]),
                candidate["dvd_id"],
                candidate["status"],
                int(candidate["attempt_count"]),
                candidate["updated_at"],
                candidate["nfo_status"],
                candidate["poster_status"],
                candidate["jellyfin_notification_status"],
                candidate["jellyfin_recovery_status"],
                candidate["jellyfin_next_check_at"],
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
    result=None,
) -> str:
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
        result = result if isinstance(result, dict) else {}
        current = db.execute(
            """SELECT status, nfo_status, poster_status
               FROM media_jobs WHERE media_job_id=?""",
            (int(media_job_id),),
        ).fetchone()
        if current is None:
            raise RuntimeError("media job missing")

        final_status = status
        if status == "COMPLETED":
            nfo_status = (result or {}).get("nfo_status")
            poster_status = (result or {}).get("poster_status")
            poster_error = (result or {}).get("poster_error")
            if nfo_status not in {"UNKNOWN", "PENDING", "COMPLETE", "ATTENTION"}:
                nfo_status = current["nfo_status"]
            if poster_status not in {
                "UNKNOWN", "PENDING", "RUNNING", "FAILED", "COMPLETE", "ATTENTION"
            }:
                poster_status = current["poster_status"]
            if poster_status == "COMPLETE":
                poster_error = None
            cursor = db.execute(
                """UPDATE media_jobs
                   SET status='COMPLETED', error=NULL, nfo_status=?,
                       poster_status=?, poster_error=?, updated_at=?
                   WHERE media_job_id=?""",
                (
                    nfo_status,
                    poster_status,
                    str(poster_error or "")[:500] or None,
                    _utc_now(),
                    int(media_job_id),
                ),
            )
        elif (
            current["status"] == "COMPLETED"
            and current["nfo_status"] == "COMPLETE"
            and current["poster_status"] == "RUNNING"
        ):
            final_status = "COMPLETED"
            cursor = db.execute(
                """UPDATE media_jobs
                   SET status='COMPLETED', error=NULL, poster_status='FAILED',
                       poster_error=?, updated_at=? WHERE media_job_id=?""",
                (
                    str(error or "poster attempt outcome unknown")[:500],
                    _utc_now(),
                    int(media_job_id),
                ),
            )
        else:
            cursor = db.execute(
                """UPDATE media_jobs
                   SET status='FAILED', error=?, updated_at=?
                   WHERE media_job_id=?""",
                (
                    error,
                    _utc_now(),
                    int(media_job_id),
                ),
            )

        if cursor.rowcount != 1:
            raise RuntimeError(
                "media job missing"
            )
        return final_status


def _mark_jellyfin_manual_action_if_exhausted(
    media_db_path,
    writer_lock_path,
    media_job_id,
    max_attempts,
) -> None:
    """Persist a terminal manual state when bounded recovery is exhausted."""
    with _media_transaction(media_db_path, writer_lock_path) as db:
        db.execute(
            """UPDATE media_jobs
               SET jellyfin_recovery_status='MANUAL_ACTION_REQUIRED',
                   jellyfin_next_check_at=NULL,
                   jellyfin_error='MANUAL_ACTION_REQUIRED: retry limit reached'
               WHERE media_job_id=? AND attempt_count>=?
                 AND (jellyfin_recovery_status='CHECK_PENDING'
                      OR (jellyfin_recovery_status='UNKNOWN'
                          AND jellyfin_notification_status IN ('ATTEMPTED','NOTIFIED')))""",
            (int(media_job_id), int(max_attempts)),
        )


def run_retryable_media_jobs(
    *,
    db_path,
    discovery_db_path=None,
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
                "held_metadata_not_found": 0,
                "held_cover_url_missing": 0,
                "held_cover_url_invalid": 0,
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
        "held_metadata_not_found": 0,
        "held_cover_url_missing": 0,
        "held_cover_url_invalid": 0,
        "poster_pending": 0,
        "poster_attention": 0,
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
            if initial_state == "EXHAUSTED":
                _mark_jellyfin_manual_action_if_exhausted(
                    db_path,
                    writer_lock_path,
                    int(job["media_job_id"]),
                    max_attempts,
                )
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
            if discovery_db_path is not None:
                input_state = media_input_eligibility(discovery_db_path, dvd_id)
                if input_state != "READY":
                    notification_pending = (
                        job.get("jellyfin_recovery_status") == "CHECK_PENDING"
                        or (
                            job.get("jellyfin_recovery_status", "UNKNOWN") == "UNKNOWN"
                            and job.get("jellyfin_notification_status") in {"ATTEMPTED", "NOTIFIED"}
                        )
                    )
                    check_due = False
                    if notification_pending:
                        due = _jellyfin_visibility_due(job, retry_backoff_seconds)
                        check_due = due is not None and now_utc >= due
                    if (
                        input_state == "HELD_COVER_URL_MISSING"
                        and (
                            job.get("nfo_status") != "COMPLETE"
                            or (notification_pending and check_due)
                        )
                    ):
                        input_state = "READY"
                    else:
                        counters = {
                            "HELD_METADATA_NOT_FOUND": "held_metadata_not_found",
                            "HELD_COVER_URL_MISSING": "held_cover_url_missing",
                            "HELD_COVER_URL_INVALID": "held_cover_url_invalid",
                        }
                        result[counters[input_state]] += 1
                        result["jobs"].append({"dvd_id": dvd_id, "status": input_state})
                        continue
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
                context = {
                    "db_path": db_path,
                    "writer_lock_path": writer_lock_path,
                    "media_job_id": job_id,
                    "dvd_id": dvd_id,
                    "jellyfin_notification_status": job.get(
                        "jellyfin_notification_status", "UNKNOWN"
                    ),
                    "jellyfin_recovery_status": (
                        "CHECK_PENDING"
                        if job.get("jellyfin_recovery_status", "UNKNOWN") == "UNKNOWN"
                        and job.get("jellyfin_notification_status") in {"ATTEMPTED", "NOTIFIED"}
                        else job.get("jellyfin_recovery_status", "UNKNOWN")
                    ),
                    "jellyfin_next_check_at": job.get("jellyfin_next_check_at"),
                    "attempt_count": int(job["attempt_count"]) + 1,
                    "max_attempts": int(max_attempts),
                    "now": now_utc,
                }
                with _bind_media_job_context(context):
                    payload = processor(dvd_id)
            except Exception as exc:
                message = str(exc)[:2000]
                final_status = _finish(
                    db_path,
                    writer_lock_path,
                    job_id,
                    status="FAILED",
                    error=message,
                )
                if final_status == "COMPLETED":
                    result["completed"] += 1
                    result["poster_pending"] += 1
                    result["jobs"].append(
                        {
                            "dvd_id": dvd_id,
                            "status": "COMPLETED",
                            "poster_status": "FAILED",
                            "error": message,
                        }
                    )
                else:
                    result["failed"] += 1
                    result["jobs"].append({"dvd_id": dvd_id, "status": "FAILED"})
                continue

            _finish(
                db_path,
                writer_lock_path,
                job_id,
                status="COMPLETED",
                result=payload,
            )
            result["completed"] += 1
            if isinstance(payload, dict):
                if payload.get("poster_status") in {"PENDING", "FAILED"}:
                    result["poster_pending"] += 1
                elif payload.get("poster_status") == "ATTENTION":
                    result["poster_attention"] += 1
            result["jobs"].append(
                {"dvd_id": dvd_id, "status": "COMPLETED", "result": payload}
            )

    return result
