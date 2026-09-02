from pathlib import Path
import tempfile

from teddy_discovery_db import (
    connect,
    initialize,
)
from teddy_discovery_media_jobs import (
    list_retryable_media_jobs,
    reconcile_media_jobs,
    run_retryable_media_jobs,
)


def main():
    with tempfile.TemporaryDirectory(
        prefix="teddy-stage9-media-jobs-"
    ) as temp:
        root = Path(temp)
        db_path = root / "test.sqlite3"
        lock_path = root / "writer.lock"

        db = connect(db_path)
        initialize(db)

        version = db.execute(
            """
            SELECT MAX(version)
            FROM schema_migrations
            """
        ).fetchone()[0]

        assert int(version) == 7

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
            db_path,
            lock_path,
        )

        assert created == 1

        jobs = list_retryable_media_jobs(
            db_path
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
                "dvd_id":
                    dvd_id,
            }

        first = run_retryable_media_jobs(
            db_path=db_path,
            writer_lock_path=lock_path,
            processor=flaky_processor,
            max_items=1,
        )

        assert first["failed"] == 1
        assert first["completed"] == 0

        second = run_retryable_media_jobs(
            db_path=db_path,
            writer_lock_path=lock_path,
            processor=flaky_processor,
            max_items=1,
        )

        assert second["failed"] == 0
        assert second["completed"] == 1

        assert (
            reconcile_media_jobs(
                db_path,
                lock_path,
            )
            == 0
        )

        db = connect(db_path)

        row = db.execute(
            """
            SELECT
                status,
                attempt_count,
                error
            FROM media_jobs
            WHERE dvd_id = 'ABC-123'
            """
        ).fetchone()

        assert row["status"] == "COMPLETED"
        assert int(row["attempt_count"]) == 2
        assert row["error"] is None

        count = db.execute(
            """
            SELECT COUNT(*)
            FROM media_jobs
            """
        ).fetchone()[0]

        assert int(count) == 1

        db.close()

    print(
        "STAGE9_MEDIA_JOBS_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
