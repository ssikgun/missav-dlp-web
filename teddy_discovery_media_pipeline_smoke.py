from pathlib import Path
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
from teddy_discovery_media_publish import (
    MediaMetadataPublishError,
    MediaMetadataSSHMutator,
)


def make_db(path):
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
                "dvd_id":
                    "ABC-123",
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
            "ABC-123",
            "한국어 제목",
            "2026-08-28",
            "Test Studio",
            "https://example.invalid/"
            "poster.jpg",
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
            "ABC-123",
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
            "ABC-123",
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
            "ABC/ABC-123/"
            "ABC-123.mp4",
            "ABC-123",
            5,
            123456,
            1,
        ),
    )

    db.commit()
    db.close()


class FakeJellyfin:
    def __init__(self):
        self.resolves = []
        self.notifications = []

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
            "ItemId":
                "adult-item-id",
            "Locations": [
                "/media/adult"
            ],
        }

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
            FakeJellyfin()
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
            == 2
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

        collision = False

        try:
            run_media_pipeline(
                db_path=db_path,
                dvd_id="ABC-123",
                ssh=ssh,
                metadata_mutator=(
                    mutator
                ),
                jellyfin=jellyfin,
                fetcher=(
                    fake_fetcher
                ),
            )

        except (
            MediaMetadataPublishError
        ):
            collision = True

        assert collision

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

    print(
        "STAGE9_MEDIA_PIPELINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
