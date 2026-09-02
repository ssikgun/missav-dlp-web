from __future__ import annotations

from pathlib import Path
import sqlite3

from teddy_discovery_organizer_apply import (
    writer_transaction,
)


RETRYABLE_STATUSES = (
    "PENDING",
    "FAILED",
    "RUNNING",
)


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


def reconcile_media_jobs(
    db_path: str | Path,
    writer_lock_path: str | Path,
) -> int:
    """
    Create missing media jobs for completed
    Stage9 organizer holdings.

    This also repairs the small crash window
    between organizer completion and media queueing.
    """

    created = 0

    with writer_transaction(
        Path(db_path),
        Path(writer_lock_path),
    ) as db:

        rows = db.execute(
            """
            SELECT
                oj.dvd_id,
                MAX(oj.job_id) AS organizer_job_id
            FROM organizer_jobs AS oj
            JOIN holdings AS h
              ON h.dvd_id = oj.dvd_id
            WHERE oj.status = 'COMPLETED'
              AND oj.dvd_id IS NOT NULL
              AND h.storage_root = 'jav'
              AND h.present = 1
              AND h.discovered_by =
                    'completion-stage9'
              AND NOT EXISTS (
                    SELECT 1
                    FROM media_jobs AS mj
                    WHERE mj.dvd_id = oj.dvd_id
              )
            GROUP BY oj.dvd_id
            ORDER BY organizer_job_id
            """
        ).fetchall()

        now = _utc_now()

        for row in rows:
            dvd_id = str(
                row["dvd_id"]
            ).strip().upper()

            if not dvd_id:
                continue

            cursor = db.execute(
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
    db_path: str | Path,
) -> list[dict]:
    db = sqlite3.connect(
        "file:"
        + str(Path(db_path))
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
    db_path,
    writer_lock_path,
    media_job_id,
) -> None:
    with writer_transaction(
        Path(db_path),
        Path(writer_lock_path),
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
    db_path,
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

    with writer_transaction(
        Path(db_path),
        Path(writer_lock_path),
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
            error=None,
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
