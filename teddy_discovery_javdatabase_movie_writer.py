from __future__ import annotations

import json
import sqlite3
from typing import Any

from teddy_discovery_javdatabase_movie import (
    JAVDATABASE_MOVIE_SOURCE,
)


MISSAV_RELEASE_SOURCE = (
    "missav-release"
)


def _text(
    value: Any,
):
    if value is None:
        return None

    value = " ".join(
        str(value).split()
    )

    return value or None


def _raw_metadata(
    item: dict,
) -> str:
    return json.dumps(
        {
            "source":
                JAVDATABASE_MOVIE_SOURCE,

            "item":
                item,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _relation_counts(
    connection: sqlite3.Connection,
    dvd_id: str,
) -> tuple[int, int]:
    people = connection.execute(
        """
        SELECT COUNT(*)
        FROM title_people
        WHERE dvd_id = ?
        """,
        (dvd_id,),
    ).fetchone()[0]

    genres = connection.execute(
        """
        SELECT COUNT(*)
        FROM title_genres
        WHERE dvd_id = ?
        """,
        (dvd_id,),
    ).fetchone()[0]

    return (
        int(people),
        int(genres),
    )


def apply_direct_movie_metadata(
    connection: sqlite3.Connection,
    item: dict,
) -> str:
    dvd_id = _text(
        item.get(
            "dvd_id"
        )
    )

    release_date = _text(
        item.get(
            "release_date"
        )
    )

    studio = _text(
        item.get(
            "studio"
        )
    )

    if not dvd_id:
        raise ValueError(
            "direct movie item missing DVD ID"
        )

    if not release_date:
        raise ValueError(
            "direct movie item missing release date"
        )

    if not studio:
        raise ValueError(
            "direct movie item missing studio"
        )

    if (
        item.get(
            "source"
        )
        != JAVDATABASE_MOVIE_SOURCE
    ):
        raise ValueError(
            "unexpected direct movie source"
        )

    genres = item.get(
        "genres"
    )

    idols = item.get(
        "idols"
    )

    if not isinstance(
        genres,
        list,
    ):
        raise ValueError(
            "direct movie genres must be list"
        )

    if not isinstance(
        idols,
        list,
    ):
        raise ValueError(
            "direct movie idols must be list"
        )

    existing = connection.execute(
        """
        SELECT
            dvd_id,
            title,
            release_date,
            maker,
            cover_url,
            metadata_source,
            first_seen_at,
            last_seen_at
        FROM titles
        WHERE dvd_id = ?
        """,
        (dvd_id,),
    ).fetchone()

    if existing is None:
        return "preserved"

    existing_source = _text(
        existing[
            "metadata_source"
        ]
    )

    if (
        existing_source
        != MISSAV_RELEASE_SOURCE
    ):
        return "preserved"

    if (
        _text(
            existing[
                "release_date"
            ]
        )
        is not None
        or _text(
            existing[
                "maker"
            ]
        )
        is not None
    ):
        return "preserved"

    people_count, genre_count = (
        _relation_counts(
            connection,
            dvd_id,
        )
    )

    if (
        people_count != 0
        or genre_count != 0
    ):
        return "preserved"

    raw_metadata = (
        _raw_metadata(
            item
        )
    )

    with connection:
        connection.execute(
            """
            UPDATE titles
            SET
                release_date = ?,
                maker = ?,
                raw_metadata = ?,
                metadata_source = ?
            WHERE dvd_id = ?
              AND metadata_source = ?
              AND NULLIF(
                    TRIM(release_date),
                    ''
                  ) IS NULL
              AND NULLIF(
                    TRIM(maker),
                    ''
                  ) IS NULL
            """,
            (
                release_date,
                studio,
                raw_metadata,
                JAVDATABASE_MOVIE_SOURCE,
                dvd_id,
                MISSAV_RELEASE_SOURCE,
            ),
        )

        changed = connection.execute(
            """
            SELECT changes()
            """
        ).fetchone()[0]

        if int(changed) != 1:
            raise RuntimeError(
                "direct metadata title update "
                "lost its precondition"
            )

        for name in idols:
            name = _text(
                name
            )

            if not name:
                continue

            connection.execute(
                """
                INSERT INTO people(name)
                VALUES (?)
                ON CONFLICT(name)
                DO NOTHING
                """,
                (name,),
            )

            row = connection.execute(
                """
                SELECT person_id
                FROM people
                WHERE name = ?
                """,
                (name,),
            ).fetchone()

            if row is None:
                raise RuntimeError(
                    "direct movie person "
                    "could not be read back"
                )

            connection.execute(
                """
                INSERT INTO title_people(
                    dvd_id,
                    person_id,
                    role
                )
                VALUES (?, ?, ?)
                """,
                (
                    dvd_id,
                    int(
                        row[
                            "person_id"
                        ]
                    ),
                    "unknown",
                ),
            )

        for name in genres:
            name = _text(
                name
            )

            if not name:
                continue

            connection.execute(
                """
                INSERT INTO genres(name)
                VALUES (?)
                ON CONFLICT(name)
                DO NOTHING
                """,
                (name,),
            )

            row = connection.execute(
                """
                SELECT genre_id
                FROM genres
                WHERE name = ?
                """,
                (name,),
            ).fetchone()

            if row is None:
                raise RuntimeError(
                    "direct movie genre "
                    "could not be read back"
                )

            connection.execute(
                """
                INSERT INTO title_genres(
                    dvd_id,
                    genre_id
                )
                VALUES (?, ?)
                """,
                (
                    dvd_id,
                    int(
                        row[
                            "genre_id"
                        ]
                    ),
                ),
            )

    return "updated"
