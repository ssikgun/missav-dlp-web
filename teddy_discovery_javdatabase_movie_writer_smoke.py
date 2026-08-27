from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from teddy_discovery_javdatabase_movie_writer import (
    apply_direct_movie_metadata,
)


DVD = "TEST-001"


ITEM = {
    "source":
        "javdatabase-movie",

    "dvd_id":
        DVD,

    "source_url":
        (
            "https://www.javdatabase.com/"
            "movies/test-001/"
        ),

    "title":
        "English Direct Title",

    "cover_url":
        (
            "https://www.javdatabase.com/"
            "covers/thumb/test.webp"
        ),

    "release_date":
        "2026-08-25",

    "studio":
        "Direct Studio",

    "genres":
        [
            "Genre A",
            "Genre B",
        ],

    "idols":
        [
            "Person A",
        ],
}


def require(
    condition,
    message,
):
    if not condition:
        raise AssertionError(
            message
        )


def connect(
    path,
):
    con = sqlite3.connect(
        path
    )

    con.row_factory = sqlite3.Row

    return con


def create_schema(
    con,
):
    con.executescript(
        """
        CREATE TABLE titles(
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

        CREATE TABLE people(
            person_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE genres(
            genre_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE title_people(
            dvd_id TEXT NOT NULL,
            person_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            PRIMARY KEY(
                dvd_id,
                person_id,
                role
            )
        );

        CREATE TABLE title_genres(
            dvd_id TEXT NOT NULL,
            genre_id INTEGER NOT NULL,
            PRIMARY KEY(
                dvd_id,
                genre_id
            )
        );
        """
    )


def insert_title(
    con,
    *,
    dvd_id=DVD,
    source="missav-release",
    release_date=None,
    maker=None,
    title="Korean MissAV Title",
    cover="https://fourhoi.com/test/cover-t.jpg",
):
    con.execute(
        """
        INSERT INTO titles(
            dvd_id,
            title,
            release_date,
            maker,
            cover_url,
            raw_metadata,
            metadata_source,
            first_seen_at,
            last_seen_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            dvd_id,
            title,
            release_date,
            maker,
            cover,
            None,
            source,
            "2026-08-25T00:00:00+00:00",
            "2026-08-27T00:00:00+00:00",
        ),
    )

    con.commit()


def happy_path(
    con,
):
    insert_title(
        con
    )

    before = con.execute(
        """
        SELECT *
        FROM titles
        WHERE dvd_id = ?
        """,
        (DVD,),
    ).fetchone()

    result = (
        apply_direct_movie_metadata(
            con,
            ITEM,
        )
    )

    require(
        result == "updated",
        "happy path did not update",
    )

    after = con.execute(
        """
        SELECT *
        FROM titles
        WHERE dvd_id = ?
        """,
        (DVD,),
    ).fetchone()

    require(
        after["release_date"]
        == "2026-08-25",
        "release date not enriched",
    )

    require(
        after["maker"]
        == "Direct Studio",
        "maker not enriched",
    )

    require(
        after["metadata_source"]
        == "javdatabase-movie",
        "metadata source changed incorrectly",
    )

    require(
        after["raw_metadata"],
        "raw metadata missing",
    )

    #
    # MissAV presentation fields must remain
    # intact.
    #
    require(
        after["title"]
        == before["title"]
        == "Korean MissAV Title",
        "MissAV title was overwritten",
    )

    require(
        after["cover_url"]
        == before["cover_url"]
        == (
            "https://fourhoi.com/"
            "test/cover-t.jpg"
        ),
        "MissAV cover was overwritten",
    )

    require(
        after["first_seen_at"]
        == before["first_seen_at"],
        "first_seen_at changed",
    )

    require(
        after["last_seen_at"]
        == before["last_seen_at"],
        "last_seen_at changed",
    )

    people = [
        tuple(row)
        for row in con.execute(
            """
            SELECT
                p.name,
                tp.role
            FROM title_people AS tp
            JOIN people AS p
              ON p.person_id = tp.person_id
            WHERE tp.dvd_id = ?
            ORDER BY p.name
            """,
            (DVD,),
        )
    ]

    genres = [
        row[0]
        for row in con.execute(
            """
            SELECT g.name
            FROM title_genres AS tg
            JOIN genres AS g
              ON g.genre_id = tg.genre_id
            WHERE tg.dvd_id = ?
            ORDER BY g.name
            """,
            (DVD,),
        )
    ]

    require(
        people
        == [
            (
                "Person A",
                "unknown",
            ),
        ],
        "people changed",
    )

    require(
        genres
        == [
            "Genre A",
            "Genre B",
        ],
        "genres changed",
    )

    print(
        "DIRECT_WRITER_HAPPY_PATH=PASS"
    )


def richer_source_preserved(
    con,
):
    dvd = "TEST-002"

    insert_title(
        con,
        dvd_id=dvd,
        source="javdatabase-weekly",
        release_date="2026-08-20",
        maker="Weekly Studio",
    )

    item = dict(
        ITEM
    )
    item["dvd_id"] = dvd

    before = dict(
        con.execute(
            """
            SELECT *
            FROM titles
            WHERE dvd_id = ?
            """,
            (dvd,),
        ).fetchone()
    )

    result = (
        apply_direct_movie_metadata(
            con,
            item,
        )
    )

    after = dict(
        con.execute(
            """
            SELECT *
            FROM titles
            WHERE dvd_id = ?
            """,
            (dvd,),
        ).fetchone()
    )

    require(
        result == "preserved",
        "weekly source was not preserved",
    )

    require(
        before == after,
        "weekly row changed",
    )

    print(
        "DIRECT_WRITER_WEEKLY_PRESERVED=PASS"
    )


def partial_metadata_preserved(
    con,
):
    dvd = "TEST-003"

    insert_title(
        con,
        dvd_id=dvd,
        release_date="2026-08-20",
    )

    item = dict(
        ITEM
    )
    item["dvd_id"] = dvd

    before = dict(
        con.execute(
            """
            SELECT *
            FROM titles
            WHERE dvd_id = ?
            """,
            (dvd,),
        ).fetchone()
    )

    result = (
        apply_direct_movie_metadata(
            con,
            item,
        )
    )

    after = dict(
        con.execute(
            """
            SELECT *
            FROM titles
            WHERE dvd_id = ?
            """,
            (dvd,),
        ).fetchone()
    )

    require(
        result == "preserved",
        "partial metadata was not preserved",
    )

    require(
        before == after,
        "partial metadata row changed",
    )

    print(
        "DIRECT_WRITER_PARTIAL_METADATA_PRESERVED=PASS"
    )


def existing_relation_preserved(
    con,
):
    dvd = "TEST-004"

    insert_title(
        con,
        dvd_id=dvd,
    )

    con.execute(
        """
        INSERT INTO people(name)
        VALUES ('Existing Person')
        """
    )

    person_id = con.execute(
        """
        SELECT person_id
        FROM people
        WHERE name = 'Existing Person'
        """
    ).fetchone()[0]

    con.execute(
        """
        INSERT INTO title_people(
            dvd_id,
            person_id,
            role
        )
        VALUES (?, ?, ?)
        """,
        (
            dvd,
            person_id,
            "existing",
        ),
    )

    con.commit()

    item = dict(
        ITEM
    )
    item["dvd_id"] = dvd

    before = dict(
        con.execute(
            """
            SELECT *
            FROM titles
            WHERE dvd_id = ?
            """,
            (dvd,),
        ).fetchone()
    )

    result = (
        apply_direct_movie_metadata(
            con,
            item,
        )
    )

    after = dict(
        con.execute(
            """
            SELECT *
            FROM titles
            WHERE dvd_id = ?
            """,
            (dvd,),
        ).fetchone()
    )

    require(
        result == "preserved",
        "existing relation was not preserved",
    )

    require(
        before == after,
        "relation-bearing row changed",
    )

    count = con.execute(
        """
        SELECT COUNT(*)
        FROM title_people
        WHERE dvd_id = ?
        """,
        (dvd,),
    ).fetchone()[0]

    require(
        count == 1,
        "existing relation changed",
    )

    print(
        "DIRECT_WRITER_EXISTING_RELATION_PRESERVED=PASS"
    )


def unknown_source_preserved(
    con,
):
    dvd = "TEST-005"

    insert_title(
        con,
        dvd_id=dvd,
        source="future-rich-source",
    )

    item = dict(
        ITEM
    )
    item["dvd_id"] = dvd

    before = dict(
        con.execute(
            """
            SELECT *
            FROM titles
            WHERE dvd_id = ?
            """,
            (dvd,),
        ).fetchone()
    )

    result = (
        apply_direct_movie_metadata(
            con,
            item,
        )
    )

    after = dict(
        con.execute(
            """
            SELECT *
            FROM titles
            WHERE dvd_id = ?
            """,
            (dvd,),
        ).fetchone()
    )

    require(
        result == "preserved",
        "unknown rich source overwritten",
    )

    require(
        before == after,
        "unknown source row changed",
    )

    print(
        "DIRECT_WRITER_UNKNOWN_SOURCE_PRESERVED=PASS"
    )


def main():
    with tempfile.TemporaryDirectory(
        prefix="teddy-javmovie-writer-"
    ) as tmp:
        path = str(
            Path(tmp)
            / "writer.sqlite3"
        )

        con = connect(
            path
        )

        create_schema(
            con
        )

        happy_path(
            con
        )

        richer_source_preserved(
            con
        )

        partial_metadata_preserved(
            con
        )

        existing_relation_preserved(
            con
        )

        unknown_source_preserved(
            con
        )

        result = con.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        require(
            result == "ok",
            "temp DB integrity failed",
        )

        con.close()

    print(
        "DIRECT_MOVIE_WRITER_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
