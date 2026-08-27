from __future__ import annotations

import json
import re
import sqlite3
from urllib.parse import (
    unquote,
    urlsplit,
)

from teddy_discovery_missav_movie import (
    normalize_dvd_id,
)


SOURCE_NAME = "missav-en-movie"

_DATE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}$"
)

_HANGUL_RE = re.compile(
    r"[\uac00-\ud7a3]"
)

_ITEM_KEYS = {
    "dvd_id",
    "title",
    "release_date",
    "studio",
    "idols",
    "genres",
    "brand_tags",
    "source_url",
}


def _clean(
    value: object,
) -> str:
    return " ".join(
        str(
            value
            if value is not None
            else ""
        ).split()
    )


def _blank(
    value: object,
) -> bool:
    return _clean(
        value
    ) == ""


def _string_list(
    value: object,
    *,
    field: str,
    allow_empty: bool,
    reject_hangul: bool,
) -> list[str]:
    if not isinstance(
        value,
        list,
    ):
        raise ValueError(
            field
            + " must be a list"
        )

    result: list[str] = []

    for raw in value:
        if not isinstance(
            raw,
            str,
        ):
            raise ValueError(
                field
                + " entries must be strings"
            )

        cleaned = _clean(
            raw
        )

        if not cleaned:
            raise ValueError(
                field
                + " contains blank entry"
            )

        if cleaned in result:
            raise ValueError(
                field
                + " contains duplicate entry"
            )

        if (
            reject_hangul
            and _HANGUL_RE.search(
                cleaned
            )
            is not None
        ):
            raise ValueError(
                field
                + " contains localized Korean value"
            )

        result.append(
            cleaned
        )

    if (
        not allow_empty
        and not result
    ):
        raise ValueError(
            field
            + " must not be empty"
        )

    return result


def _validate_source_url(
    value: object,
    dvd_id: str,
) -> str:
    if not isinstance(
        value,
        str,
    ):
        raise ValueError(
            "source_url must be a string"
        )

    parsed = urlsplit(
        value
    )

    if (
        parsed.scheme != "https"
        or parsed.hostname != "missav.ws"
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "invalid MissAV English source URL"
        )

    segments = [
        unquote(segment)
        for segment
        in parsed.path.split("/")
        if segment
    ]

    if (
        len(segments) != 2
        or segments[0] != "en"
    ):
        raise ValueError(
            "MissAV fallback source must use /en/"
        )

    actual = normalize_dvd_id(
        segments[1]
    )

    if actual != dvd_id:
        raise ValueError(
            "source_url dvd_id mismatch"
        )

    return (
        parsed.scheme
        + "://"
        + parsed.netloc
        + parsed.path
    )


def normalize_missav_en_item(
    item: object,
) -> dict[str, object]:
    if not isinstance(
        item,
        dict,
    ):
        raise ValueError(
            "item must be a dict"
        )

    if set(
        item
    ) != _ITEM_KEYS:
        raise ValueError(
            "unexpected item key universe"
        )

    dvd_id = normalize_dvd_id(
        item[
            "dvd_id"
        ]
    )

    title = _clean(
        item[
            "title"
        ]
    )

    if not title:
        raise ValueError(
            "title must not be blank"
        )

    release_date = _clean(
        item[
            "release_date"
        ]
    )

    if (
        _DATE_RE.fullmatch(
            release_date
        )
        is None
    ):
        raise ValueError(
            "invalid release_date"
        )

    studio = _clean(
        item[
            "studio"
        ]
    )

    if not studio:
        raise ValueError(
            "studio must not be blank"
        )

    idols = _string_list(
        item[
            "idols"
        ],
        field="idols",
        allow_empty=True,
        reject_hangul=True,
    )

    genres = _string_list(
        item[
            "genres"
        ],
        field="genres",
        allow_empty=False,
        reject_hangul=True,
    )

    brand_tags = _string_list(
        item[
            "brand_tags"
        ],
        field="brand_tags",
        allow_empty=True,
        reject_hangul=False,
    )

    source_url = _validate_source_url(
        item[
            "source_url"
        ],
        dvd_id,
    )

    return {
        "dvd_id":
            dvd_id,

        "title":
            title,

        "release_date":
            release_date,

        "studio":
            studio,

        "idols":
            idols,

        "genres":
            genres,

        "brand_tags":
            brand_tags,

        "source_url":
            source_url,
    }


def _raw_metadata(
    item: dict[str, object],
) -> str:
    return json.dumps(
        {
            "source":
                SOURCE_NAME,

            "item":
                item,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def apply_missav_en_movie_metadata(
    connection: sqlite3.Connection,
    item: object,
) -> str:
    normalized = (
        normalize_missav_en_item(
            item
        )
    )

    dvd_id = str(
        normalized[
            "dvd_id"
        ]
    )

    row = connection.execute(
        """
        SELECT
            release_date,
            maker,
            raw_metadata,
            metadata_source
        FROM titles
        WHERE dvd_id = ?
        """,
        (dvd_id,),
    ).fetchone()

    if row is None:
        raise ValueError(
            "target title does not exist"
        )

    release_date = row[0]
    maker = row[1]
    raw_metadata = row[2]
    metadata_source = row[3]

    people_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM title_people
        WHERE dvd_id = ?
        """,
        (dvd_id,),
    ).fetchone()[0]

    genre_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM title_genres
        WHERE dvd_id = ?
        """,
        (dvd_id,),
    ).fetchone()[0]

    #
    # Fallback may ONLY enrich an untouched
    # missav-release row. Any partial/richer
    # metadata or pre-existing relations win.
    #
    if (
        metadata_source
        != "missav-release"
        or not _blank(
            release_date
        )
        or not _blank(
            maker
        )
        or not _blank(
            raw_metadata
        )
        or int(
            people_count
        ) != 0
        or int(
            genre_count
        ) != 0
    ):
        return "preserved"

    raw = _raw_metadata(
        normalized
    )

    with connection:
        cursor = connection.execute(
            """
            UPDATE titles
            SET
                release_date = ?,
                maker = ?,
                raw_metadata = ?,
                metadata_source = ?
            WHERE dvd_id = ?
              AND metadata_source = 'missav-release'
              AND NULLIF(
                    TRIM(
                        COALESCE(
                            release_date,
                            ''
                        )
                    ),
                    ''
                  ) IS NULL
              AND NULLIF(
                    TRIM(
                        COALESCE(
                            maker,
                            ''
                        )
                    ),
                    ''
                  ) IS NULL
              AND NULLIF(
                    TRIM(
                        COALESCE(
                            raw_metadata,
                            ''
                        )
                    ),
                    ''
                  ) IS NULL
            """,
            (
                normalized[
                    "release_date"
                ],
                normalized[
                    "studio"
                ],
                raw,
                SOURCE_NAME,
                dvd_id,
            ),
        )

        if cursor.rowcount != 1:
            raise RuntimeError(
                "target changed during guarded update"
            )

        for name in normalized[
            "idols"
        ]:
            connection.execute(
                """
                INSERT OR IGNORE
                INTO people(name)
                VALUES (?)
                """,
                (name,),
            )

            person = connection.execute(
                """
                SELECT person_id
                FROM people
                WHERE name = ?
                """,
                (name,),
            ).fetchone()

            if person is None:
                raise RuntimeError(
                    "person upsert failed"
                )

            connection.execute(
                """
                INSERT OR IGNORE
                INTO title_people(
                    dvd_id,
                    person_id,
                    role
                )
                VALUES (?, ?, 'unknown')
                """,
                (
                    dvd_id,
                    person[0],
                ),
            )

        for name in normalized[
            "genres"
        ]:
            connection.execute(
                """
                INSERT OR IGNORE
                INTO genres(name)
                VALUES (?)
                """,
                (name,),
            )

            genre = connection.execute(
                """
                SELECT genre_id
                FROM genres
                WHERE name = ?
                """,
                (name,),
            ).fetchone()

            if genre is None:
                raise RuntimeError(
                    "genre upsert failed"
                )

            connection.execute(
                """
                INSERT OR IGNORE
                INTO title_genres(
                    dvd_id,
                    genre_id
                )
                VALUES (?, ?)
                """,
                (
                    dvd_id,
                    genre[0],
                ),
            )

    return "updated"
