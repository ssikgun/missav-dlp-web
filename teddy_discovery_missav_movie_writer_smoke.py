from __future__ import annotations

import json
import sqlite3

from teddy_discovery_missav_movie_writer import (
    SOURCE_NAME,
    apply_missav_en_movie_metadata,
)


def make_db() -> sqlite3.Connection:
    con = sqlite3.connect(
        ":memory:"
    )

    con.executescript(
        """
        CREATE TABLE titles (
            dvd_id TEXT PRIMARY KEY,
            title TEXT,
            cover_url TEXT,
            release_date TEXT,
            maker TEXT,
            raw_metadata TEXT,
            metadata_source TEXT,
            first_seen_at TEXT,
            last_seen_at TEXT
        );

        CREATE TABLE people (
            person_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );

        CREATE TABLE genres (
            genre_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
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

        CREATE TABLE title_genres (
            dvd_id TEXT NOT NULL,
            genre_id INTEGER NOT NULL,
            PRIMARY KEY (
                dvd_id,
                genre_id
            )
        );
        """
    )

    return con


def add_title(
    con: sqlite3.Connection,
    *,
    dvd_id: str,
    release_date=None,
    maker=None,
    raw_metadata=None,
    metadata_source="missav-release",
) -> None:
    con.execute(
        """
        INSERT INTO titles(
            dvd_id,
            title,
            cover_url,
            release_date,
            maker,
            raw_metadata,
            metadata_source,
            first_seen_at,
            last_seen_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            dvd_id,
            "PRESERVE TITLE",
            "https://example.invalid/cover.jpg",
            release_date,
            maker,
            raw_metadata,
            metadata_source,
            "first",
            "last",
        ),
    )

    con.commit()


def item(
    *,
    dvd_id="GANA-3432",
    idols=None,
    genres=None,
):
    if idols is None:
        idols = [
            "Maina, 21 Years Old, "
            "Works Part-Time At A Ramen Shop."
        ]

    if genres is None:
        genres = [
            "Big Breasts",
            "Ordinary Person",
            "Exclusive",
            "G Cup",
        ]

    return {
        "dvd_id":
            dvd_id,

        "title":
            dvd_id
            + " English metadata title",

        "release_date":
            "2026-08-24",

        "studio":
            "ナンパTV",

        "idols":
            idols,

        "genres":
            genres,

        "brand_tags":
            [
                "200GANA",
                "GANA",
            ],

        "source_url":
            (
                "https://missav.ws/en/"
                + dvd_id.lower()
            ),
    }


#
# 1. Successful enrichment.
#
con = make_db()

add_title(
    con,
    dvd_id="GANA-3432",
)

before = con.execute(
    """
    SELECT *
    FROM titles
    WHERE dvd_id = 'GANA-3432'
    """
).fetchone()

result = (
    apply_missav_en_movie_metadata(
        con,
        item(),
    )
)

assert result == "updated"

after = con.execute(
    """
    SELECT *
    FROM titles
    WHERE dvd_id = 'GANA-3432'
    """
).fetchone()

assert after[1] == before[1]
assert after[2] == before[2]
assert after[7] == before[7]
assert after[8] == before[8]

assert after[3] == "2026-08-24"
assert after[4] == "ナンパTV"
assert after[6] == SOURCE_NAME

raw = json.loads(
    after[5]
)

assert raw["source"] == SOURCE_NAME
assert raw["item"] == item()

people = con.execute(
    """
    SELECT p.name, tp.role
    FROM title_people AS tp
    JOIN people AS p
      ON p.person_id = tp.person_id
    WHERE tp.dvd_id = 'GANA-3432'
    """
).fetchall()

assert people == [
    (
        "Maina, 21 Years Old, "
        "Works Part-Time At A Ramen Shop.",
        "unknown",
    )
]

genres = {
    row[0]
    for row in con.execute(
        """
        SELECT g.name
        FROM title_genres AS tg
        JOIN genres AS g
          ON g.genre_id = tg.genre_id
        WHERE tg.dvd_id = 'GANA-3432'
        """
    )
}

assert genres == {
    "Big Breasts",
    "Ordinary Person",
    "Exclusive",
    "G Cup",
}

assert "200GANA" not in genres
assert "GANA" not in genres

print(
    "MISSAV_EN_WRITER_SUCCESS_SMOKE=PASS"
)

print(
    "MISSAV_EN_WRITER_PRESENTATION_PRESERVED_SMOKE=PASS"
)

print(
    "MISSAV_EN_WRITER_BRAND_TAG_NOT_GENRE_SMOKE=PASS"
)


#
# 2. Actor-less item is valid.
#
con2 = make_db()

add_title(
    con2,
    dvd_id="IMJO-011",
)

actorless = item(
    dvd_id="IMJO-011",
    idols=[],
    genres=[
        "Slim",
        "Selfie",
        "4K",
    ],
)

actorless[
    "studio"
] = "イマドキ性事情"

actorless[
    "release_date"
] = "2026-08-22"

assert (
    apply_missav_en_movie_metadata(
        con2,
        actorless,
    )
    == "updated"
)

assert con2.execute(
    """
    SELECT COUNT(*)
    FROM title_people
    WHERE dvd_id = 'IMJO-011'
    """
).fetchone()[0] == 0

print(
    "MISSAV_EN_WRITER_ACTORLESS_SMOKE=PASS"
)


#
# 3. Richer metadata wins.
#
con3 = make_db()

add_title(
    con3,
    dvd_id="GANA-3432",
    metadata_source=
        "javdatabase-movie",
)

snapshot = con3.execute(
    """
    SELECT *
    FROM titles
    """
).fetchall()

assert (
    apply_missav_en_movie_metadata(
        con3,
        item(),
    )
    == "preserved"
)

assert con3.execute(
    """
    SELECT *
    FROM titles
    """
).fetchall() == snapshot

print(
    "MISSAV_EN_WRITER_RICHER_SOURCE_PRESERVED_SMOKE=PASS"
)


#
# 4. Partial metadata wins.
#
con4 = make_db()

add_title(
    con4,
    dvd_id="GANA-3432",
    release_date=
        "2026-08-20",
)

assert (
    apply_missav_en_movie_metadata(
        con4,
        item(),
    )
    == "preserved"
)

print(
    "MISSAV_EN_WRITER_PARTIAL_METADATA_PRESERVED_SMOKE=PASS"
)


#
# 5. Existing raw metadata wins.
#
con5 = make_db()

add_title(
    con5,
    dvd_id="GANA-3432",
    raw_metadata=
        '{"existing":true}',
)

assert (
    apply_missav_en_movie_metadata(
        con5,
        item(),
    )
    == "preserved"
)

print(
    "MISSAV_EN_WRITER_RAW_METADATA_PRESERVED_SMOKE=PASS"
)


#
# 6. Existing relations win.
#
con6 = make_db()

add_title(
    con6,
    dvd_id="GANA-3432",
)

con6.execute(
    """
    INSERT INTO people(name)
    VALUES ('Existing Person')
    """
)

person_id = con6.execute(
    """
    SELECT person_id
    FROM people
    WHERE name = 'Existing Person'
    """
).fetchone()[0]

con6.execute(
    """
    INSERT INTO title_people(
        dvd_id,
        person_id,
        role
    )
    VALUES (?, ?, 'unknown')
    """,
    (
        "GANA-3432",
        person_id,
    ),
)

con6.commit()

assert (
    apply_missav_en_movie_metadata(
        con6,
        item(),
    )
    == "preserved"
)

print(
    "MISSAV_EN_WRITER_RELATION_PRESERVED_SMOKE=PASS"
)


#
# 7. Korean actor must fail before write.
#
con7 = make_db()

add_title(
    con7,
    dvd_id="GANA-3432",
)

bad_actor = item()
bad_actor["idols"] = [
    "한국 배우"
]

try:
    apply_missav_en_movie_metadata(
        con7,
        bad_actor,
    )

except ValueError:
    print(
        "MISSAV_EN_WRITER_HANGUL_ACTOR_REJECTED_SMOKE=PASS"
    )

else:
    raise AssertionError(
        "Korean actor did not fail"
    )


#
# 8. Korean genre must fail.
#
bad_genre = item()
bad_genre["genres"] = [
    "Big Breasts",
    "아마추어",
]

try:
    apply_missav_en_movie_metadata(
        con7,
        bad_genre,
    )

except ValueError:
    print(
        "MISSAV_EN_WRITER_HANGUL_GENRE_REJECTED_SMOKE=PASS"
    )

else:
    raise AssertionError(
        "Korean genre did not fail"
    )


#
# 9. /ko/ source URL must fail.
#
bad_url = item()

bad_url[
    "source_url"
] = (
    "https://missav.ws/ko/gana-3432"
)

try:
    apply_missav_en_movie_metadata(
        con7,
        bad_url,
    )

except ValueError:
    print(
        "MISSAV_EN_WRITER_KO_SOURCE_REJECTED_SMOKE=PASS"
    )

else:
    raise AssertionError(
        "/ko/ source URL did not fail"
    )


print(
    "DISCOVERY_MISSAV_EN_WRITER_SMOKE=PASS"
)
