from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import fcntl
import sqlite3


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


def _mark_running(
    media_db_path,
    writer_lock_path,
    media_job_id,
) -> None:
    with _media_transaction(
        media_db_path,
        writer_lock_path,
    ) as db:

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
            """,
            (
                _utc_now(),
                int(media_job_id),
            ),
        )

        if cursor.rowcount != 1:
            raise RuntimeError(
                "media job missing"
            )


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
) -> dict:
    if int(max_items) < 1:
        raise RuntimeError(
            "media max_items must be >= 1"
        )

    jobs = list_retryable_media_jobs(
        db_path
    )

    result = {
        "retryable": len(jobs),
        "attempted": 0,
        "completed": 0,
        "failed": 0,
        "jobs": [],
    }

    for job in jobs[:int(max_items)]:
        job_id = int(
            job["media_job_id"]
        )

        dvd_id = str(
            job["dvd_id"]
        )

        _mark_running(
            db_path,
            writer_lock_path,
            job_id,
        )

        result["attempted"] += 1

        try:
            payload = processor(
                dvd_id
            )

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

            result["jobs"].append(
                {
                    "dvd_id": dvd_id,
                    "status": "FAILED",
                    "error": message,
                }
            )

            continue

        _finish(
            db_path,
            writer_lock_path,
            job_id,
            status="COMPLETED",
        )

        result["completed"] += 1

        result["jobs"].append(
            {
                "dvd_id": dvd_id,
                "status": "COMPLETED",
                "result": payload,
            }
        )

    return result
