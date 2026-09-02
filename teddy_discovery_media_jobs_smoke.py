from pathlib import Path
import sqlite3
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
        )

        assert first["failed"] == 1

        second = run_retryable_media_jobs(
            db_path=media_db,
            writer_lock_path=media_lock,
            processor=flaky_processor,
            max_items=1,
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

    print(
        "STAGE9_SEPARATE_MEDIA_DB_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
