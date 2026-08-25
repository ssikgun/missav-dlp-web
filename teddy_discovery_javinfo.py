from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
from typing import Any

from teddy_discovery_ids import parse_dvd_id


PERSON_FIELDS = (
    ("actresses", "actress"),
    ("actors", "actor"),
    ("directors", "director"),
    ("authors", "author"),
)


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat(timespec="seconds")


def _text(value: Any):
    if value is None:
        return None

    value = str(value).strip()

    return value or None


def _name(value: Any):
    if isinstance(value, dict):
        return _text(
            value.get("name")
        )

    return _text(value)


def normalize_dvd_id(value: Any) -> str:
    raw = _text(value)

    if not raw:
        raise ValueError(
            "missing dvdId"
        )

    parsed = parse_dvd_id(raw)

    if parsed is None:
        raise ValueError(
            f"unrecognized dvdId: {raw!r}"
        )

    return parsed.dvd_id


def normalize_movie_response(
    payload: dict,
) -> dict:
    if not isinstance(payload, dict):
        raise ValueError(
            "movie response must be an object"
        )

    result = payload.get("result")

    if not isinstance(result, dict):
        raise ValueError(
            "movie response missing result object"
        )

    dvd_id = normalize_dvd_id(
        result.get("dvdId")
    )

    title = (
        _text(result.get("titleEn"))
        or _text(result.get("titleJa"))
    )

    makers = result.get("makers") or []

    if isinstance(makers, str):
        makers = [makers]

    maker = None

    for item in makers:
        maker = _name(item)
        if maker:
            break

    cover_url = (
        _text(
            result.get(
                "jacketFullUrl"
            )
        )
        or _text(
            result.get(
                "jacketThumbUrl"
            )
        )
    )

    people = []

    for field, role in PERSON_FIELDS:
        values = result.get(field) or []

        if not isinstance(
            values,
            list,
        ):
            values = [values]

        for item in values:
            name = _name(item)

            if name:
                people.append(
                    (
                        name,
                        role,
                    )
                )

    genres = []

    categories = (
        result.get("categories")
        or []
    )

    if not isinstance(
        categories,
        list,
    ):
        categories = [categories]

    for item in categories:
        name = _name(item)

        if name:
            genres.append(name)

    source = (
        _text(payload.get("source"))
        or _text(result.get("site"))
        or "unknown"
    )

    return {
        "dvd_id": dvd_id,
        "title": title,
        "release_date":
            _text(
                result.get(
                    "releaseDate"
                )
            ),
        "maker": maker,
        "cover_url": cover_url,
        "metadata_source": source,
        "raw_metadata": json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
        ),
        "people": sorted(
            set(people)
        ),
        "genres": sorted(
            set(genres)
        ),
    }


def movie_payload_from_envelope(
    envelope: dict,
) -> dict:
    if not isinstance(
        envelope,
        dict,
    ):
        raise ValueError(
            "forensic envelope must be object"
        )

    status = envelope.get(
        "status"
    )

    if status != 200:
        raise ValueError(
            f"cannot import HTTP "
            f"status {status!r}"
        )

    body = envelope.get(
        "body"
    )

    if isinstance(body, str):
        payload = json.loads(body)
    elif isinstance(body, dict):
        payload = body
    else:
        raise ValueError(
            "forensic envelope body "
            "must be JSON string/object"
        )

    return payload


def upsert_movie_metadata(
    connection: sqlite3.Connection,
    payload: dict,
) -> str:
    item = normalize_movie_response(
        payload
    )

    now = utc_now()

    with connection:
        connection.execute(
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
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT(dvd_id)
            DO UPDATE SET
                title =
                    COALESCE(
                        excluded.title,
                        titles.title
                    ),
                release_date =
                    COALESCE(
                        excluded.release_date,
                        titles.release_date
                    ),
                maker =
                    COALESCE(
                        excluded.maker,
                        titles.maker
                    ),
                cover_url =
                    COALESCE(
                        excluded.cover_url,
                        titles.cover_url
                    ),
                raw_metadata =
                    excluded.raw_metadata,
                metadata_source =
                    excluded.metadata_source,
                last_seen_at =
                    excluded.last_seen_at
            """,
            (
                item["dvd_id"],
                item["title"],
                item["release_date"],
                item["maker"],
                item["cover_url"],
                item["raw_metadata"],
                item["metadata_source"],
                now,
                now,
            ),
        )

        connection.execute(
            """
            DELETE FROM title_people
            WHERE dvd_id = ?
            """,
            (
                item["dvd_id"],
            ),
        )

        for name, role in item["people"]:
            connection.execute(
                """
                INSERT INTO people(name)
                VALUES (?)
                ON CONFLICT(name)
                DO NOTHING
                """,
                (
                    name,
                ),
            )

            row = connection.execute(
                """
                SELECT person_id
                FROM people
                WHERE name = ?
                """,
                (
                    name,
                ),
            ).fetchone()

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
                    item["dvd_id"],
                    int(row["person_id"]),
                    role,
                ),
            )

        connection.execute(
            """
            DELETE FROM title_genres
            WHERE dvd_id = ?
            """,
            (
                item["dvd_id"],
            ),
        )

        for name in item["genres"]:
            connection.execute(
                """
                INSERT INTO genres(name)
                VALUES (?)
                ON CONFLICT(name)
                DO NOTHING
                """,
                (
                    name,
                ),
            )

            row = connection.execute(
                """
                SELECT genre_id
                FROM genres
                WHERE name = ?
                """,
                (
                    name,
                ),
            ).fetchone()

            connection.execute(
                """
                INSERT INTO title_genres(
                    dvd_id,
                    genre_id
                )
                VALUES (?, ?)
                """,
                (
                    item["dvd_id"],
                    int(row["genre_id"]),
                ),
            )

    return item["dvd_id"]
