from pathlib import Path
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3
import subprocess
import tempfile

from teddy_discovery_completion_ssh import (
    CompletionSSH,
)
from teddy_discovery_media_pipeline import (
    MediaPipelineError,
    run_media_pipeline,
)
from teddy_discovery_media_jobs import (
    MEDIA_SCHEMA,
    run_retryable_media_jobs,
)
from teddy_discovery_media_publish import (
    MediaMetadataSSHMutator,
)


def make_db(path, *, dvd_id="ABC-123", cover_url="https://example.invalid/poster.jpg"):
    db = sqlite3.connect(
        path
    )

    db.executescript(
        """
        CREATE TABLE titles (
            dvd_id TEXT PRIMARY KEY,
            title TEXT,
            release_date TEXT,
            maker TEXT,
            cover_url TEXT,
            raw_metadata TEXT,
            metadata_source TEXT,
            first_seen_at TEXT,
            last_seen_at TEXT
        );

        CREATE TABLE genres (
            genre_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        );

        CREATE TABLE title_genres (
            dvd_id TEXT NOT NULL,
            genre_id INTEGER NOT NULL,
            PRIMARY KEY (
                dvd_id,
                genre_id
            )
        );

        CREATE TABLE people (
            person_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        );

        CREATE TABLE title_people (
            dvd_id TEXT NOT NULL,
            person_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            PRIMARY KEY (
                dvd_id,
                person_id,
                role
            )
        );

        CREATE TABLE holdings (
            holding_id INTEGER PRIMARY KEY,
            storage_root TEXT NOT NULL,
            relative_path TEXT NOT NULL,
            dvd_id TEXT,
            size_bytes INTEGER,
            mtime_ns INTEGER,
            present INTEGER NOT NULL
        );
        """
    )

    raw = json.dumps(
        {
            "item": {
                "dvd_id": dvd_id,
                "title":
                    "Original Title",
            }
        }
    )

    db.execute(
        """
        INSERT INTO titles (
            dvd_id,
            title,
            release_date,
            maker,
            cover_url,
            raw_metadata,
            metadata_source
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            dvd_id,
            "한국어 제목",
            "2026-08-28",
            "Test Studio",
            cover_url,
            raw,
            "fake-source",
        ),
    )

    db.execute(
        """
        INSERT INTO genres (
            genre_id,
            name
        )
        VALUES (?, ?)
        """,
        (
            1,
            "Drama",
        ),
    )

    db.execute(
        """
        INSERT INTO title_genres (
            dvd_id,
            genre_id
        )
        VALUES (?, ?)
        """,
        (
            dvd_id,
            1,
        ),
    )

    db.execute(
        """
        INSERT INTO people (
            person_id,
            name
        )
        VALUES (?, ?)
        """,
        (
            1,
            "Test Actress",
        ),
    )

    db.execute(
        """
        INSERT INTO title_people (
            dvd_id,
            person_id,
            role
        )
        VALUES (?, ?, ?)
        """,
        (
            dvd_id,
            1,
            "unknown",
        ),
    )

    db.execute(
        """
        INSERT INTO holdings (
            storage_root,
            relative_path,
            dvd_id,
            size_bytes,
            mtime_ns,
            present
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "jav",
            f"{dvd_id.rsplit('-', 1)[0]}/{dvd_id}/{dvd_id}.mp4",
            dvd_id,
            5,
            123456,
            1,
        ),
    )

    db.commit()
    db.close()


class FakeJellyfin:
    def __init__(self, visibility=None, *, item_id="11111111111141118111111111111111"):
        self.resolves = []
        self.notifications = []
        self.visibility = list(visibility or [])
        self.visibility_paths = []
        self.item_id = item_id

    def resolve_library(
        self,
        *,
        name,
        location,
    ):
        self.resolves.append(
            (
                name,
                location,
            )
        )

        return {
            "Name": "Adult",
            "ItemId": self.item_id,
            "Locations": [
                "/media/adult"
            ],
        }

    def exact_media_visibility(self, path):
        self.visibility_paths.append(path)
        if self.visibility:
            return self.visibility.pop(0)
        return {"status": "PENDING", "reason": None}

    def notify_created(
        self,
        path,
    ):
        self.notifications.append(
            path
        )

        return {
            "status":
                "JELLYFIN_NOTIFIED",
            "path":
                path,
        }


def main():
    with tempfile.TemporaryDirectory(
        prefix="teddy-stage9-media-pipeline-"
    ) as temp:

        root = Path(temp)

        db_path = (
            root
            / "test.sqlite3"
        )

        make_db(
            db_path
        )

        library = (
            root
            / "library"
        )

        movie = (
            library
            / "ABC"
            / "ABC-123"
        )

        movie.mkdir(
            parents=True
        )

        video = (
            movie
            / "ABC-123.mp4"
        )

        video.write_bytes(
            b"VIDEO"
        )

        def fake_runner(
            command,
            **kwargs,
        ):
            return subprocess.run(
                [
                    "/bin/sh",
                    "-c",
                    command[-1],
                ],
                **kwargs,
            )

        ssh = CompletionSSH(
            host="fake",
            user="fake",
            key="/fake/key",
            known_hosts=(
                "/fake/known_hosts"
            ),
            downloads_root=str(
                root / "downloads"
            ),
            library_root=str(
                library
            ),
            runner=fake_runner,
        )

        mutator = (
            MediaMetadataSSHMutator(
                ssh
            )
        )

        def fake_fetcher(
            url,
        ):
            assert url == (
                "https://example.invalid/"
                "poster.jpg"
            )

            return (
                "image/jpeg",
                b"\xff\xd8\xff"
                b"FAKEJPEG",
            )

        jellyfin = (
            FakeJellyfin(
                [
                    {"status": "PENDING", "reason": None},
                    {"status": "VISIBLE", "reason": None, "item_id": "movie-1"},
                    {"status": "VISIBLE", "reason": None, "item_id": "movie-1"},
                ]
            )
        )

        first = run_media_pipeline(
            db_path=db_path,
            dvd_id="ABC-123",
            ssh=ssh,
            metadata_mutator=(
                mutator
            ),
            jellyfin=jellyfin,
            fetcher=fake_fetcher,
        )

        assert (
            first["status"]
            == "MEDIA_PIPELINE_COMPLETE"
        )

        assert (
            first[
                "metadata"
            ][
                "nfo"
            ][
                "status"
            ]
            == "CREATED"
        )

        assert (
            first[
                "metadata"
            ][
                "poster"
            ][
                "status"
            ]
            == "CREATED"
        )

        assert (
            movie
            / "ABC-123.nfo"
        ).is_file()

        assert (
            movie
            / "poster.jpg"
        ).is_file()

        assert jellyfin.notifications == [
            "/media/adult/"
            "ABC/ABC-123/"
            "ABC-123.mp4"
        ]

        second = run_media_pipeline(
            db_path=db_path,
            dvd_id="ABC-123",
            ssh=ssh,
            metadata_mutator=(
                mutator
            ),
            jellyfin=jellyfin,
            fetcher=fake_fetcher,
        )

        assert (
            second[
                "metadata"
            ][
                "nfo"
            ][
                "status"
            ]
            == "ALREADY_PRESENT"
        )

        assert (
            second[
                "metadata"
            ][
                "poster"
            ][
                "status"
            ]
            == "ALREADY_PRESENT"
        )

        assert (
            len(
                jellyfin.notifications
            )
            == 1
        )

        before_collision = len(
            jellyfin.notifications
        )

        (
            movie
            / "poster.jpg"
        ).write_bytes(
            b"COLLISION"
        )

        collision = run_media_pipeline(
            db_path=db_path,
            dvd_id="ABC-123",
            ssh=ssh,
            metadata_mutator=mutator,
            jellyfin=jellyfin,
            fetcher=fake_fetcher,
        )
        assert collision["poster_status"] == "ATTENTION"
        assert collision["metadata"]["poster"]["status"] == "ATTENTION"

        assert (
            len(
                jellyfin.notifications
            )
            == before_collision
        )

        missing = False

        try:
            run_media_pipeline(
                db_path=db_path,
                dvd_id="XYZ-999",
                ssh=ssh,
                metadata_mutator=(
                    mutator
                ),
                jellyfin=jellyfin,
                fetcher=(
                    fake_fetcher
                ),
            )

        except MediaPipelineError:
            missing = True

        assert missing

        def seed_media_job(path, dvd_id):
            db = sqlite3.connect(path)
            db.executescript(MEDIA_SCHEMA)
            stamp = datetime.now(timezone.utc).isoformat()
            db.execute(
                """INSERT INTO media_jobs
                   (dvd_id,status,attempt_count,error,nfo_status,poster_status,
                    jellyfin_notification_status,created_at,updated_at)
                   VALUES(?, 'PENDING', 0, NULL, 'PENDING', 'PENDING',
                          'UNKNOWN', ?, ?)""",
                (dvd_id, stamp, stamp),
            )
            db.commit()
            db.close()

        def read_media_job(path, dvd_id):
            db = sqlite3.connect(path)
            db.row_factory = sqlite3.Row
            row = db.execute(
                "SELECT * FROM media_jobs WHERE dvd_id=?", (dvd_id,)
            ).fetchone()
            db.close()
            return dict(row)

        def run_job(discovery_db, media_db, dvd_id, job_jellyfin, fetcher, *, now=None):
            return run_retryable_media_jobs(
                db_path=media_db,
                discovery_db_path=discovery_db,
                writer_lock_path=root / (dvd_id + ".media.lock"),
                title_lock_dir=root / "job-title-locks",
                target_dvd_id=dvd_id,
                max_items=1,
                now=now,
                processor=lambda target: run_media_pipeline(
                    db_path=discovery_db,
                    dvd_id=target,
                    ssh=ssh,
                    metadata_mutator=mutator,
                    jellyfin=job_jellyfin,
                    fetcher=fetcher,
                ),
            )

        lock_root = root / "job-title-locks"
        lock_root.mkdir()

        # A posterless work completes its NFO and is retried as a poster-only
        # supplement when a canonical URL appears, across persisted job state.
        posterless_db = root / "posterless.sqlite3"
        posterless_media_db = root / "posterless-media.sqlite3"
        make_db(posterless_db, dvd_id="XYZ-789", cover_url=None)
        posterless_dir = library / "XYZ" / "XYZ-789"
        posterless_dir.mkdir(parents=True)
        posterless_video = posterless_dir / "XYZ-789.mp4"
        posterless_video.write_bytes(b"VXYZ!")
        seed_media_job(posterless_media_db, "XYZ-789")
        posterless_jellyfin = FakeJellyfin(
            [
                {"status": "PENDING", "reason": None},
                {"status": "PENDING", "reason": None},
            ]
        )
        posterless_video_hash = hashlib.sha256(posterless_video.read_bytes()).hexdigest()
        first_nfo = run_job(
            posterless_db,
            posterless_media_db,
            "XYZ-789",
            posterless_jellyfin,
            lambda _url: (_ for _ in ()).throw(AssertionError("missing cover fetched")),
        )
        assert first_nfo["completed"] == 1
        first_row = read_media_job(posterless_media_db, "XYZ-789")
        assert first_row["status"] == "COMPLETED"
        assert first_row["nfo_status"] == "COMPLETE"
        assert first_row["poster_status"] == "PENDING"
        assert first_row["poster_error"] == "COVER_URL_MISSING"
        assert first_row["jellyfin_notification_status"] == "NOTIFIED"
        posterless_nfo = posterless_dir / "XYZ-789.nfo"
        assert posterless_nfo.is_file()
        assert not (posterless_dir / "poster.jpg").exists()
        nfo_hash = hashlib.sha256(posterless_nfo.read_bytes()).hexdigest()
        nfo_mtime = posterless_nfo.stat().st_mtime_ns

        waiting = run_job(
            posterless_db,
            posterless_media_db,
            "XYZ-789",
            posterless_jellyfin,
            lambda _url: (_ for _ in ()).throw(AssertionError("missing cover fetched")),
        )
        assert waiting["held_cover_url_missing"] == 1
        assert waiting["attempted"] == 0
        assert read_media_job(posterless_media_db, "XYZ-789")["attempt_count"] == 1

        db = sqlite3.connect(posterless_db)
        db.execute(
            "UPDATE titles SET cover_url=? WHERE dvd_id=?",
            ("https://example.invalid/XYZ-789.jpg", "XYZ-789"),
        )
        db.commit()
        db.close()

        def xyz_fetcher(url):
            assert url == "https://example.invalid/XYZ-789.jpg"
            return "image/jpeg", b"\xff\xd8\xffXYZ-POSTER"

        supplement = run_job(
            posterless_db,
            posterless_media_db,
            "XYZ-789",
            posterless_jellyfin,
            xyz_fetcher,
        )
        assert supplement["completed"] == 1, supplement
        after_row = read_media_job(posterless_media_db, "XYZ-789")
        assert after_row["nfo_status"] == "COMPLETE"
        assert after_row["poster_status"] == "COMPLETE"
        assert after_row["attempt_count"] == 2
        assert after_row["jellyfin_notification_status"] == "NOTIFIED"
        assert len(posterless_jellyfin.notifications) == 1
        assert hashlib.sha256(posterless_nfo.read_bytes()).hexdigest() == nfo_hash
        assert posterless_nfo.stat().st_mtime_ns == nfo_mtime
        assert hashlib.sha256(posterless_video.read_bytes()).hexdigest() == posterless_video_hash
        assert (posterless_dir / "poster.jpg").read_bytes() == b"\xff\xd8\xffXYZ-POSTER"

        # A valid URL that fails download still records NFO completion. The
        # retry after backoff can later add the poster without a second alert.
        failed_db = root / "poster-failed.sqlite3"
        failed_media_db = root / "poster-failed-media.sqlite3"
        make_db(
            failed_db,
            dvd_id="RST-333",
            cover_url="https://example.invalid/RST-333.jpg",
        )
        failed_dir = library / "RST" / "RST-333"
        failed_dir.mkdir(parents=True)
        failed_video = failed_dir / "RST-333.mp4"
        failed_video.write_bytes(b"VRST!")
        seed_media_job(failed_media_db, "RST-333")
        attention_jellyfin = FakeJellyfin(
            [
                {"status": "ATTENTION", "reason": "AMBIGUOUS_FAMILY_FOLDER"},
                {"status": "PENDING", "reason": None},
            ]
        )
        failed_result = run_job(
            failed_db,
            failed_media_db,
            "RST-333",
            attention_jellyfin,
            lambda _url: (_ for _ in ()).throw(TimeoutError()),
        )
        assert failed_result["completed"] == 1
        failed_row = read_media_job(failed_media_db, "RST-333")
        assert failed_row["status"] == "COMPLETED"
        assert failed_row["nfo_status"] == "COMPLETE"
        assert failed_row["poster_status"] == "FAILED"
        assert failed_row["poster_error"] == "POSTER_FETCH_FAILED:TimeoutError"
        assert failed_row["jellyfin_notification_status"] == "ATTENTION"
        assert attention_jellyfin.notifications == []
        failed_nfo = failed_dir / "RST-333.nfo"
        failed_nfo_hash = hashlib.sha256(failed_nfo.read_bytes()).hexdigest()
        failed_nfo_mtime = failed_nfo.stat().st_mtime_ns
        failed_video_hash = hashlib.sha256(failed_video.read_bytes()).hexdigest()

        retry = run_job(
            failed_db,
            failed_media_db,
            "RST-333",
            attention_jellyfin,
            lambda _url: ("image/jpeg", b"\xff\xd8\xffRST-POSTER"),
            now=datetime.now(timezone.utc) + timedelta(seconds=3601),
        )
        assert retry["completed"] == 1
        final_failed_row = read_media_job(failed_media_db, "RST-333")
        assert final_failed_row["nfo_status"] == "COMPLETE"
        assert final_failed_row["poster_status"] == "COMPLETE"
        assert final_failed_row["jellyfin_notification_status"] == "ATTENTION"
        assert attention_jellyfin.notifications == []
        assert hashlib.sha256(failed_nfo.read_bytes()).hexdigest() == failed_nfo_hash
        assert failed_nfo.stat().st_mtime_ns == failed_nfo_mtime
        assert hashlib.sha256(failed_video.read_bytes()).hexdigest() == failed_video_hash
        assert (failed_dir / "poster.jpg").read_bytes() == b"\xff\xd8\xffRST-POSTER"

    print(
        "STAGE9_MEDIA_PIPELINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
