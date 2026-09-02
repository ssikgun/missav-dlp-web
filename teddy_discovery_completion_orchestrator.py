from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from teddy_discovery_completion import (
    CompletionPlan,
)
from teddy_discovery_organizer_apply import (
    create_job,
    set_job_status,
    writer_transaction,
)


class CompletionOrchestratorError(RuntimeError):
    pass


def _read_job(
    db_path: Path,
    plan: CompletionPlan,
):
    db = sqlite3.connect(
        "file:" + str(db_path) + "?mode=ro",
        uri=True,
    )
    db.row_factory = sqlite3.Row

    try:
        row = db.execute(
            """
            SELECT
                job_id,
                status,
                source_path,
                destination_path
            FROM organizer_jobs
            WHERE dvd_id = ?
              AND source_path = ?
              AND destination_path = ?
            ORDER BY job_id DESC
            LIMIT 1
            """,
            (
                plan.dvd_id,
                str(Path(plan.source_relative)),
                str(Path(plan.destination_relative)),
            ),
        ).fetchone()

        return (
            None
            if row is None
            else dict(row)
        )

    finally:
        db.close()


def _read_holding(
    db_path: Path,
    dvd_id: str,
):
    db = sqlite3.connect(
        "file:" + str(db_path) + "?mode=ro",
        uri=True,
    )
    db.row_factory = sqlite3.Row

    try:
        rows = db.execute(
            """
            SELECT
                relative_path,
                size_bytes,
                mtime_ns
            FROM holdings
            WHERE dvd_id = ?
              AND present = 1
            """,
            (dvd_id,),
        ).fetchall()

        if len(rows) > 1:
            raise CompletionOrchestratorError(
                "multiple holdings present"
            )

        return (
            None
            if not rows
            else dict(rows[0])
        )

    finally:
        db.close()


def commit_remote_holding(
    db_path: Path,
    writer_lock_path: Path,
    *,
    plan: CompletionPlan,
    job_id: int,
    published: dict,
) -> None:

    size = int(
        published["size"]
    )

    mtime_ns = int(
        published["mtime_ns"]
    )

    parse_candidates = json.dumps(
        [plan.dvd_id],
        ensure_ascii=False,
    )

    with writer_transaction(
        db_path,
        writer_lock_path,
    ) as db:

        duplicate = db.execute(
            """
            SELECT COUNT(*)
            FROM holdings
            WHERE dvd_id = ?
              AND present = 1
            """,
            (plan.dvd_id,),
        ).fetchone()[0]

        if int(duplicate) != 0:
            raise CompletionOrchestratorError(
                "holding appeared before DB commit"
            )

        from datetime import (
            datetime,
            timezone,
        )

        now = datetime.now(
            timezone.utc
        ).isoformat(
            timespec="seconds"
        )

        db.execute(
            """
            INSERT INTO holdings (
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
                last_seen_at,
                last_seen_run_id
            )
            VALUES (
                'jav',
                ?,
                ?,
                'MATCHED',
                ?,
                ?,
                ?,
                ?,
                'completion-stage9',
                1,
                ?,
                ?,
                NULL
            )
            """,
            (
                plan.destination_relative,
                plan.dvd_id,
                plan.parse_method,
                parse_candidates,
                size,
                mtime_ns,
                now,
                now,
            ),
        )

        cursor = db.execute(
            """
            UPDATE organizer_jobs
            SET
                status = 'PUBLISHED',
                error = NULL,
                updated_at = ?
            WHERE job_id = ?
            """,
            (
                now,
                job_id,
            ),
        )

        if cursor.rowcount != 1:
            raise CompletionOrchestratorError(
                "organizer job missing"
            )


def _verify_destination(
    existing,
    plan,
):
    if existing is None:
        raise CompletionOrchestratorError(
            "destination missing"
        )

    if int(existing["size"]) != int(
        plan.size_bytes
    ):
        raise CompletionOrchestratorError(
            "destination size mismatch"
        )


def process_one(
    plan: CompletionPlan,
    *,
    ssh,
    mutator,
    db_path: Path,
    writer_lock_path: Path,
) -> int:

    if (
        not plan.dvd_id
        or not plan.destination_relative
    ):
        raise CompletionOrchestratorError(
            "plan identity missing"
        )

    job = _read_job(
        db_path,
        plan,
    )

    holding = _read_holding(
        db_path,
        plan.dvd_id,
    )

    existing = ssh.stat_library(
        plan.destination_relative
    )

    # Recovery: DB already committed, but source cleanup failed.
    if holding is not None:

        if (
            not job
            or job["status"]
            not in {
                "PUBLISHED",
                "CLEANUP_PENDING",
            }
        ):
            raise CompletionOrchestratorError(
                "existing holding is not recoverable"
            )

        if (
            holding["relative_path"]
            != plan.destination_relative
        ):
            raise CompletionOrchestratorError(
                "holding path mismatch"
            )

        _verify_destination(
            existing,
            plan,
        )

        mutator.cleanup_source(
            source_relative=
                plan.source_relative,
            expected_size=
                plan.size_bytes,
            expected_mtime_ns=
                plan.mtime_ns,
        )

        set_job_status(
            db_path,
            writer_lock_path,
            int(job["job_id"]),
            "COMPLETED",
            None,
        )

        return int(
            job["job_id"]
        )

    # Recovery: NAS publish succeeded, DB commit did not.
    if existing is not None:

        if (
            not job
            or job["status"]
            not in {
                "RUNNING",
                "DB_FAILED_AFTER_PUBLISH",
            }
        ):
            raise CompletionOrchestratorError(
                "destination exists without "
                "recoverable job"
            )

        _verify_destination(
            existing,
            plan,
        )

        job_id = int(
            job["job_id"]
        )

        commit_remote_holding(
            db_path,
            writer_lock_path,
            plan=plan,
            job_id=job_id,
            published=existing,
        )

        try:
            mutator.cleanup_source(
                source_relative=
                    plan.source_relative,
                expected_size=
                    plan.size_bytes,
                expected_mtime_ns=
                    plan.mtime_ns,
            )

        except Exception as exc:
            set_job_status(
                db_path,
                writer_lock_path,
                job_id,
                "CLEANUP_PENDING",
                str(exc),
            )
            raise

        set_job_status(
            db_path,
            writer_lock_path,
            job_id,
            "COMPLETED",
            None,
        )

        return job_id

    if (
        plan.planned_operation
        != "PLAN_STAGE9_SSH_MOVE"
    ):
        raise CompletionOrchestratorError(
            "plan is not apply eligible"
        )

    if job:
        status = str(
            job["status"]
        )

        if status == "RUNNING":
            job_id = int(
                job["job_id"]
            )

        elif status == "FAILED":
            job_id = create_job(
                db_path,
                writer_lock_path,
                dvd_id=plan.dvd_id,
                source_path=Path(
                    plan.source_relative
                ),
                destination_path=Path(
                    plan.destination_relative
                ),
            )

        else:
            raise CompletionOrchestratorError(
                "unexpected previous job state: "
                + status
            )

    else:
        job_id = create_job(
            db_path,
            writer_lock_path,
            dvd_id=plan.dvd_id,
            source_path=Path(
                plan.source_relative
            ),
            destination_path=Path(
                plan.destination_relative
            ),
        )

    try:
        published = (
            mutator.publish_to_library(
                source_relative=
                    plan.source_relative,
                destination_relative=
                    plan.destination_relative,
                expected_size=
                    plan.size_bytes,
                expected_mtime_ns=
                    plan.mtime_ns,
            )
        )

    except Exception as exc:
        set_job_status(
            db_path,
            writer_lock_path,
            job_id,
            "FAILED",
            str(exc),
        )
        raise

    try:
        commit_remote_holding(
            db_path,
            writer_lock_path,
            plan=plan,
            job_id=job_id,
            published=published,
        )

    except Exception as exc:
        set_job_status(
            db_path,
            writer_lock_path,
            job_id,
            "DB_FAILED_AFTER_PUBLISH",
            str(exc),
        )
        raise

    try:
        mutator.cleanup_source(
            source_relative=
                plan.source_relative,
            expected_size=
                plan.size_bytes,
            expected_mtime_ns=
                plan.mtime_ns,
        )

    except Exception as exc:
        set_job_status(
            db_path,
            writer_lock_path,
            job_id,
            "CLEANUP_PENDING",
            str(exc),
        )
        raise

    set_job_status(
        db_path,
        writer_lock_path,
        job_id,
        "COMPLETED",
        None,
    )

    return job_id
