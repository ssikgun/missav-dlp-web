from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PurePosixPath
from pathlib import Path
import sqlite3

from teddy_discovery_jellyfin import (
    JellyfinPathError,
    JellyfinResponseError,
    jellyfin_media_path,
    validate_adult_media_path,
)
from teddy_discovery_media_jobs import (
    _media_transaction,
    normalize_media_target_dvd_id,
)


VISIBILITY_TABLE_SCHEMA = """CREATE TABLE IF NOT EXISTS media_jellyfin_visibility (
    dvd_id TEXT NOT NULL UNIQUE,
    media_job_id INTEGER NOT NULL,
    jellyfin_path TEXT,
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'VISIBLE', 'ATTENTION')),
    check_count INTEGER NOT NULL DEFAULT 0 CHECK (check_count >= 0),
    media_completed_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_checked_at TEXT,
    visible_at TEXT,
    last_error TEXT
);"""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _target(value):
    return normalize_media_target_dvd_id(value) if value is not None else None


def _media_path(relative_path):
    raw = str(relative_path or "")
    relative = PurePosixPath(raw)
    if (
        not raw
        or relative.is_absolute()
        or relative.as_posix() != raw
        or len(relative.parts) != 3
        or "\\" in raw
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ValueError("invalid canonical relative media path")
    return validate_adult_media_path(jellyfin_media_path(raw)).as_posix()


def _completed_jobs(db, target):
    if target is None:
        rows = db.execute(
            """SELECT media_job_id, dvd_id, updated_at
               FROM media_jobs WHERE status='COMPLETED'
               ORDER BY media_job_id"""
        ).fetchall()
    else:
        rows = db.execute(
            """SELECT media_job_id, dvd_id, updated_at
               FROM media_jobs WHERE status='COMPLETED' AND dvd_id=?""",
            (target,),
        ).fetchall()
    return rows


def reconcile_jellyfin_visibility(
    discovery_db_path: str | Path,
    media_db_path: str | Path,
    writer_lock_path: str | Path,
    jellyfin,
    *,
    max_items: int = 5,
    target_dvd_id: str | None = None,
) -> dict:
    """Seed completed media visibility and perform bounded Jellyfin GET checks only."""
    max_items = int(max_items)
    if max_items < 1 or max_items > 1000:
        raise ValueError("visibility max_items must be between 1 and 1000")
    target = _target(target_dvd_id)
    now = _now()
    seeded = 0
    skipped_no_present_holding = 0
    seeded_attention = 0

    discovery = sqlite3.connect(
        "file:" + str(Path(discovery_db_path).resolve()) + "?mode=ro",
        uri=True,
    )
    discovery.row_factory = sqlite3.Row
    try:
        with _media_transaction(media_db_path, writer_lock_path) as media:
            media.execute(VISIBILITY_TABLE_SCHEMA)
            media.execute(
                """CREATE INDEX IF NOT EXISTS idx_media_jellyfin_visibility_pending
                   ON media_jellyfin_visibility(status, updated_at, dvd_id)"""
            )
            jobs = _completed_jobs(media, target)
            for job in jobs:
                dvd_id = str(job["dvd_id"] or "").strip().upper()
                existing = media.execute(
                    "SELECT 1 FROM media_jellyfin_visibility WHERE dvd_id=?",
                    (dvd_id,),
                ).fetchone()
                if existing is not None:
                    continue
                holdings = discovery.execute(
                    """SELECT relative_path FROM holdings
                       WHERE dvd_id=? AND storage_root='jav' AND present=1""",
                    (dvd_id,),
                ).fetchall()
                if len(holdings) != 1:
                    skipped_no_present_holding += 1
                    continue
                path = None
                status = "PENDING"
                error = None
                try:
                    path = _media_path(holdings[0]["relative_path"])
                except (TypeError, ValueError, RuntimeError):
                    status = "ATTENTION"
                    error = "INVALID_MEDIA_PATH"
                    seeded_attention += 1
                cursor = media.execute(
                    """INSERT OR IGNORE INTO media_jellyfin_visibility
                       (dvd_id, media_job_id, jellyfin_path, status, check_count,
                        media_completed_at, created_at, updated_at, last_checked_at,
                        visible_at, last_error)
                       VALUES (?, ?, ?, ?, 0, ?, ?, ?, NULL, NULL, ?)""",
                    (
                        dvd_id,
                        int(job["media_job_id"]),
                        path,
                        status,
                        str(job["updated_at"]),
                        now,
                        now,
                        error,
                    ),
                )
                seeded += int(cursor.rowcount == 1)

            pending_rows = media.execute(
                """SELECT dvd_id, jellyfin_path FROM media_jellyfin_visibility
                   WHERE status='PENDING' AND (? IS NULL OR dvd_id=?)
                   ORDER BY created_at, dvd_id LIMIT ?""",
                (target, target, max_items),
            ).fetchall()
            candidates = [dict(row) for row in pending_rows]
    finally:
        discovery.close()

    result = {
        "seeded": seeded,
        "checked": 0,
        "visible": 0,
        "pending": 0,
        "attention": seeded_attention,
        "skipped_no_present_holding": skipped_no_present_holding,
        "target_dvd_id": target,
        "jellyfin_mutations": 0,
    }

    for candidate in candidates:
        dvd_id = candidate["dvd_id"]
        result["checked"] += 1
        try:
            observation = jellyfin.exact_media_visibility(
                candidate["jellyfin_path"]
            )
            if not isinstance(observation, dict):
                raise JellyfinResponseError("invalid visibility observation")
            status = observation.get("status")
            reason = observation.get("reason")
            if status not in {"VISIBLE", "PENDING", "ATTENTION"}:
                raise JellyfinResponseError("invalid visibility result")
            if status == "VISIBLE":
                if not isinstance(observation.get("item_id"), str) or not observation["item_id"].strip():
                    raise JellyfinResponseError("visible item identity missing")
                error = None
            elif status == "PENDING":
                error = "EXACT_MOVIE_NOT_VISIBLE"
            else:
                error = "ATTENTION:" + str(reason or "INVALID_VISIBILITY_RESULT")[:96]
        except (JellyfinPathError, JellyfinResponseError) as exc:
            status = "ATTENTION"
            error = "MALFORMED_GET_RESPONSE:" + type(exc).__name__
        except Exception as exc:
            # Transport/API failures stay retryable and never trigger a POST.
            status = "PENDING"
            error = "GET_ERROR:" + type(exc).__name__[:80]

        stamp = _now()
        with _media_transaction(media_db_path, writer_lock_path) as media:
            row = media.execute(
                """SELECT status FROM media_jellyfin_visibility
                   WHERE dvd_id=?""",
                (dvd_id,),
            ).fetchone()
            if row is None or row["status"] != "PENDING":
                continue
            visible_at = stamp if status == "VISIBLE" else None
            cursor = media.execute(
                """UPDATE media_jellyfin_visibility
                   SET status=?, check_count=check_count+1,
                       updated_at=?, last_checked_at=?, visible_at=?, last_error=?
                   WHERE dvd_id=? AND status='PENDING'""",
                (status, stamp, stamp, visible_at, error, dvd_id),
            )
            if cursor.rowcount != 1:
                continue
        if status == "VISIBLE":
            result["visible"] += 1
        elif status == "PENDING":
            result["pending"] += 1
        else:
            result["attention"] += 1

    summary = sqlite3.connect(
        "file:" + str(Path(media_db_path).resolve()) + "?mode=ro",
        uri=True,
    )
    try:
        rows = summary.execute(
            """SELECT status, count(*) FROM media_jellyfin_visibility
               WHERE (? IS NULL OR dvd_id=?) GROUP BY status""",
            (target, target),
        ).fetchall()
        result["visible"] = 0
        result["pending"] = 0
        result["attention"] = 0
        for status, count in rows:
            result[status.lower()] = int(count)
    finally:
        summary.close()

    return result
