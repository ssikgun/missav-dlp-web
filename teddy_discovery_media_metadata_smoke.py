from pathlib import Path
import json
import sqlite3
import tempfile
import xml.etree.ElementTree as ET

from teddy_discovery_media_metadata import (
    build_media_bundle,
    load_media_metadata,
)


def main():
    with tempfile.TemporaryDirectory(
        prefix="teddy-stage9-media-"
    ) as temp:
        db_path = (
            Path(temp)
            / "test.sqlite3"
        )

        db = sqlite3.connect(
            db_path
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
            """
        )

        raw = json.dumps(
            {
                "item": {
                    "dvd_id": "ABC-123",
                    "title":
                        "Original English Title",
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
                "poster.webp",
                raw,
                "fake-source",
            ),
        )

        db.executemany(
            """
            INSERT INTO genres (
                genre_id,
                name
            )
            VALUES (?, ?)
            """,
            [
                (1, "Drama"),
                (2, "Hi-Def"),
            ],
        )

        db.executemany(
            """
            INSERT INTO title_genres (
                dvd_id,
                genre_id
            )
            VALUES (?, ?)
            """,
            [
                ("ABC-123", 1),
                ("ABC-123", 2),
            ],
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

        db.commit()
        db.close()

        metadata = (
            load_media_metadata(
                db_path,
                "abc-123",
            )
        )

        assert (
            metadata.dvd_id
            == "ABC-123"
        )

        assert (
            metadata.title
            == "한국어 제목"
        )

        assert (
            metadata.original_title
            == "Original English Title"
        )

        assert (
            metadata.genres
            == (
                "Drama",
                "Hi-Def",
            )
        )

        assert (
            metadata.people
            == (
                (
                    "Test Actress",
                    "unknown",
                ),
            )
        )

        calls = []

        def fake_fetcher(url):
            calls.append(url)

            data = (
                b"RIFF"
                + (4).to_bytes(
                    4,
                    "little",
                )
                + b"WEBP"
                + b"TEST"
            )

            return (
                "image/webp",
                data,
            )

        bundle = (
            build_media_bundle(
                db_path,
                "ABC-123",
                fetcher=fake_fetcher,
            )
        )

        assert (
            calls
            == [
                "https://example.invalid/"
                "poster.webp"
            ]
        )

        assert (
            bundle.nfo_filename
            == "ABC-123.nfo"
        )

        assert (
            bundle.poster.filename
            == "poster.webp"
        )

        root = ET.fromstring(
            bundle.nfo_data
        )

        assert (
            root.tag
            == "movie"
        )

        assert (
            root.findtext("title")
            == "한국어 제목"
        )

        assert (
            root.findtext(
                "originaltitle"
            )
            == "Original English Title"
        )

        assert (
            root.findtext("premiered")
            == "2026-08-28"
        )

        assert (
            root.findtext("year")
            == "2026"
        )

        assert (
            root.findtext("studio")
            == "Test Studio"
        )

        assert (
            [
                item.text
                for item
                in root.findall("genre")
            ]
            == [
                "Drama",
                "Hi-Def",
            ]
        )

        actors = root.findall(
            "actor"
        )

        assert len(actors) == 1

        assert (
            actors[0].findtext(
                "name"
            )
            == "Test Actress"
        )

        assert (
            actors[0].find(
                "role"
            )
            is None
        )

        unique = root.find(
            "uniqueid"
        )

        assert unique is not None

        assert (
            unique.text
            == "ABC-123"
        )

        assert (
            unique.attrib["type"]
            == "dvd_id"
        )

    print(
        "STAGE9_MEDIA_METADATA_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
