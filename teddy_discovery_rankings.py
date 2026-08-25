from __future__ import annotations

from datetime import (
    date,
    datetime,
)
import json
import re
import sqlite3
from typing import Any
from urllib.parse import (
    unquote,
    urlparse,
)

from teddy_discovery_ids import (
    parse_dvd_id,
)

from teddy_discovery_javdatabase import (
    JAVDATABASE_WEEKLY_SOURCE,
)


WEEKLY_CHART_TYPE = (
    JAVDATABASE_WEEKLY_SOURCE
)

WEEKLY_EXPECTED_COUNT = 25

MISSAV_RELEASE_SOURCE = (
    "missav-release"
)

JAVDATABASE_HOSTS = {
    "javdatabase.com",
    "www.javdatabase.com",
}

PERIOD_RE = re.compile(
    r"^\d{4}-W\d{2}$"
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


def _validated_observed_at(
    value: Any,
) -> str:
    value = _text(
        value
    )

    if not value:
        raise ValueError(
            "ranking observed_at "
            "is required"
        )

    try:
        parsed = datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00",
            )
        )

    except ValueError as exc:
        raise ValueError(
            "invalid ranking observed_at"
        ) from exc

    if parsed.tzinfo is None:
        raise ValueError(
            "ranking observed_at "
            "must be timezone-aware"
        )

    return value


def _canonical_dvd_id(
    value: Any,
) -> str:
    raw = _text(
        value
    )

    if not raw:
        raise ValueError(
            "weekly DVD ID missing"
        )

    parsed = parse_dvd_id(
        raw
    )

    if parsed is None:
        raise ValueError(
            "invalid weekly DVD ID"
        )

    if raw.upper() != (
        parsed.dvd_id
    ):
        raise ValueError(
            "weekly DVD ID "
            "is not canonical"
        )

    return parsed.dvd_id


def _javdatabase_movie_url(
    value: Any,
    dvd_id: str,
) -> str:
    value = _text(
        value
    )

    if not value:
        raise ValueError(
            "weekly movie URL missing"
        )

    parsed = urlparse(
        value
    )

    if (
        parsed.scheme != "https"
        or parsed.hostname
        not in JAVDATABASE_HOSTS
    ):
        raise ValueError(
            "weekly movie URL "
            "escaped JAV Database"
        )

    segments = [
        unquote(segment)
        for segment
        in parsed.path.split("/")
        if segment
    ]

    if (
        len(segments) != 2
        or segments[0].lower()
        != "movies"
    ):
        raise ValueError(
            "unexpected weekly "
            "movie URL path"
        )

    linked = parse_dvd_id(
        segments[1]
    )

    if (
        linked is None
        or linked.dvd_id
        != dvd_id
    ):
        raise ValueError(
            "weekly movie URL "
            "DVD ID mismatch"
        )

    return value


def _javdatabase_cover_url(
    value: Any,
) -> str:
    value = _text(
        value
    )

    if not value:
        raise ValueError(
            "weekly cover URL missing"
        )

    parsed = urlparse(
        value
    )

    if (
        parsed.scheme != "https"
        or parsed.hostname
        not in JAVDATABASE_HOSTS
    ):
        raise ValueError(
            "weekly cover URL "
            "escaped JAV Database"
        )

    return value


def _names(
    value: Any,
    label: str,
) -> list[str]:
    if not isinstance(
        value,
        list,
    ):
        raise ValueError(
            f"weekly {label} "
            "must be a list"
        )

    result = []

    for item in value:
        name = _text(
            item
        )

        if not name:
            raise ValueError(
                f"weekly {label} "
                "contains empty value"
            )

        if name not in result:
            result.append(
                name
            )

    return result


def validate_weekly_snapshot(
    snapshot: dict,
) -> dict:
    if not isinstance(
        snapshot,
        dict,
    ):
        raise ValueError(
            "weekly snapshot "
            "must be object"
        )

    source = _text(
        snapshot.get(
            "source"
        )
    )

    if source != (
        JAVDATABASE_WEEKLY_SOURCE
    ):
        raise ValueError(
            "weekly snapshot "
            "source mismatch"
        )

    period = _text(
        snapshot.get(
            "period"
        )
    )

    if (
        not period
        or not PERIOD_RE.fullmatch(
            period
        )
    ):
        raise ValueError(
            "invalid weekly period"
        )

    items = snapshot.get(
        "items"
    )

    if (
        not isinstance(
            items,
            list,
        )
        or len(items)
        != WEEKLY_EXPECTED_COUNT
    ):
        raise ValueError(
            "weekly snapshot "
            "must contain 25 items"
        )

    values = []

    seen_ids = set()
    seen_ranks = set()

    for expected_rank, item in enumerate(
        items,
        start=1,
    ):
        if not isinstance(
            item,
            dict,
        ):
            raise ValueError(
                "weekly ranking item "
                "must be object"
            )

        if _text(
            item.get(
                "source"
            )
        ) != source:
            raise ValueError(
                "weekly item "
                "source mismatch"
            )

        dvd_id = _canonical_dvd_id(
            item.get(
                "dvd_id"
            )
        )

        rank = item.get(
            "rank"
        )

        if (
            type(rank) is not int
            or rank
            != expected_rank
        ):
            raise ValueError(
                "weekly item ranks "
                "must be exact 1..25"
            )

        if dvd_id in seen_ids:
            raise ValueError(
                "duplicate weekly "
                "DVD ID"
            )

        if rank in seen_ranks:
            raise ValueError(
                "duplicate weekly rank"
            )

        title = _text(
            item.get(
                "title"
            )
        )

        if not title:
            raise ValueError(
                "weekly title missing"
            )

        release_date = _text(
            item.get(
                "release_date"
            )
        )

        if not release_date:
            raise ValueError(
                "weekly release date missing"
            )

        try:
            date.fromisoformat(
                release_date
            )

        except ValueError as exc:
            raise ValueError(
                "invalid weekly "
                "release date"
            ) from exc

        studio = _text(
            item.get(
                "studio"
            )
        )

        if not studio:
            raise ValueError(
                "weekly studio missing"
            )

        source_url = (
            _javdatabase_movie_url(
                item.get(
                    "source_url"
                ),
                dvd_id,
            )
        )

        cover_url = (
            _javdatabase_cover_url(
                item.get(
                    "cover_url"
                )
            )
        )

        genres = _names(
            item.get(
                "genres"
            ),
            "genres",
        )

        idols = _names(
            item.get(
                "idols"
            ),
            "idols",
        )

        seen_ids.add(
            dvd_id
        )

        seen_ranks.add(
            rank
        )

        values.append({
            "source":
                source,

            "dvd_id":
                dvd_id,

            "rank":
                rank,

            "source_url":
                source_url,

            "title":
                title,

            "cover_url":
                cover_url,

            "release_date":
                release_date,

            "studio":
                studio,

            "genres":
                genres,

            "idols":
                idols,
        })

    return {
        "chart_type":
            WEEKLY_CHART_TYPE,

        "period":
            period,

        "items":
            values,
    }


def _weekly_raw_metadata(
    item: dict,
    period: str,
) -> str:
    value = {
        "source":
            JAVDATABASE_WEEKLY_SOURCE,

        "period":
            period,

        "item":
            item,
    }

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
    )


def _replace_weekly_people(
    connection: sqlite3.Connection,
    dvd_id: str,
    idols: list[str],
) -> None:
    connection.execute(
        """
        DELETE FROM title_people
        WHERE dvd_id = ?
        """,
        (
            dvd_id,
        ),
    )

    for name in idols:
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

        if row is None:
            raise RuntimeError(
                "weekly person insert "
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


def _replace_weekly_genres(
    connection: sqlite3.Connection,
    dvd_id: str,
    genres: list[str],
) -> None:
    connection.execute(
        """
        DELETE FROM title_genres
        WHERE dvd_id = ?
        """,
        (
            dvd_id,
        ),
    )

    for name in genres:
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

        if row is None:
            raise RuntimeError(
                "weekly genre insert "
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


def _weekly_period_key(
    period: str,
) -> tuple[int, int]:
    period = _text(
        period
    )

    if (
        not period
        or not PERIOD_RE.fullmatch(
            period
        )
    ):
        raise ValueError(
            "invalid weekly period"
        )

    year_raw, week_raw = (
        period.split(
            "-W",
            1,
        )
    )

    year = int(
        year_raw
    )

    week = int(
        week_raw
    )

    if (
        year < 2000
        or year > 2100
        or week < 1
        or week > 53
    ):
        raise ValueError(
            "invalid weekly period"
        )

    return (
        year,
        week,
    )


def _existing_weekly_metadata_period(
    raw_metadata: Any,
) -> str:
    if not isinstance(
        raw_metadata,
        str,
    ) or not raw_metadata.strip():
        raise RuntimeError(
            "existing Weekly metadata "
            "provenance missing"
        )

    try:
        value = json.loads(
            raw_metadata
        )

    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "existing Weekly metadata "
            "provenance malformed"
        ) from exc

    if not isinstance(
        value,
        dict,
    ):
        raise RuntimeError(
            "existing Weekly metadata "
            "provenance must be object"
        )

    if _text(
        value.get(
            "source"
        )
    ) != (
        JAVDATABASE_WEEKLY_SOURCE
    ):
        raise RuntimeError(
            "existing Weekly metadata "
            "source provenance mismatch"
        )

    period = _text(
        value.get(
            "period"
        )
    )

    #
    # This validates both syntax and
    # semantic week bounds.
    #
    _weekly_period_key(
        period
    )

    return period


def _upsert_weekly_metadata(
    connection: sqlite3.Connection,
    item: dict,
    period: str,
    observed_at: str,
) -> str:
    existing = connection.execute(
        """
        SELECT
            metadata_source,
            raw_metadata
        FROM titles
        WHERE dvd_id = ?
        """,
        (
            item[
                "dvd_id"
            ],
        ),
    ).fetchone()

    existing_source = (
        _text(
            existing[
                "metadata_source"
            ]
        )
        if existing is not None
        else None
    )

    can_replace = False
    preserve_without_touch = False

    if (
        existing is None
        or existing_source is None
        or existing_source
        == MISSAV_RELEASE_SOURCE
    ):
        can_replace = True

    elif existing_source == (
        JAVDATABASE_WEEKLY_SOURCE
    ):
        existing_period = (
            _existing_weekly_metadata_period(
                existing[
                    "raw_metadata"
                ]
            )
        )

        incoming_key = (
            _weekly_period_key(
                period
            )
        )

        existing_key = (
            _weekly_period_key(
                existing_period
            )
        )

        if incoming_key >= existing_key:
            #
            # Same-period recollection may
            # refresh corrected metadata.
            # Newer Weekly always supersedes
            # older Weekly.
            #
            can_replace = True

        else:
            #
            # Historical backfill must not
            # make newer Weekly metadata,
            # people, genres or provenance
            # move backwards.
            #
            preserve_without_touch = True

    else:
        #
        # Any richer metadata source keeps
        # precedence over Weekly metadata.
        #
        can_replace = False

    if not can_replace:
        if not preserve_without_touch:
            #
            # Preserve the existing behavior
            # for richer sources: seeing the
            # title again can advance its
            # observation timestamp without
            # replacing rich metadata.
            #
            connection.execute(
                """
                UPDATE titles
                SET last_seen_at = ?
                WHERE dvd_id = ?
                """,
                (
                    observed_at,
                    item[
                        "dvd_id"
                    ],
                ),
            )

        return "preserved"

    raw_metadata = (
        _weekly_raw_metadata(
            item,
            period,
        )
    )

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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(dvd_id)
        DO UPDATE SET
            title =
                excluded.title,

            release_date =
                excluded.release_date,

            maker =
                excluded.maker,

            cover_url =
                excluded.cover_url,

            raw_metadata =
                excluded.raw_metadata,

            metadata_source =
                excluded.metadata_source,

            first_seen_at =
                COALESCE(
                    titles.first_seen_at,
                    excluded.first_seen_at
                ),

            last_seen_at =
                excluded.last_seen_at
        """,
        (
            item[
                "dvd_id"
            ],
            item[
                "title"
            ],
            item[
                "release_date"
            ],
            item[
                "studio"
            ],
            item[
                "cover_url"
            ],
            raw_metadata,
            JAVDATABASE_WEEKLY_SOURCE,
            observed_at,
            observed_at,
        ),
    )

    _replace_weekly_people(
        connection,
        item[
            "dvd_id"
        ],
        item[
            "idols"
        ],
    )

    _replace_weekly_genres(
        connection,
        item[
            "dvd_id"
        ],
        item[
            "genres"
        ],
    )

    return "updated"


def _write_validated_weekly_snapshot(
    connection: sqlite3.Connection,
    values: dict,
    observed_at: str,
) -> dict:
    chart_type = values[
        "chart_type"
    ]

    period = values[
        "period"
    ]

    items = values[
        "items"
    ]

    metadata_updated = 0
    metadata_preserved = 0

    for item in items:
        result = (
            _upsert_weekly_metadata(
                connection,
                item,
                period,
                observed_at,
            )
        )

        if result == "updated":
            metadata_updated += 1

        elif result == "preserved":
            metadata_preserved += 1

        else:
            raise RuntimeError(
                "unexpected weekly "
                "metadata result"
            )

    connection.execute(
        """
        DELETE FROM ranking_snapshots
        WHERE chart_type = ?
          AND period = ?
        """,
        (
            chart_type,
            period,
        ),
    )

    connection.executemany(
        """
        INSERT INTO ranking_snapshots(
            chart_type,
            period,
            dvd_id,
            rank,
            score,
            observed_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                chart_type,
                period,
                item[
                    "dvd_id"
                ],
                item[
                    "rank"
                ],
                None,
                observed_at,
            )
            for item
            in items
        ],
    )

    stored = (
        connection.execute(
            """
            SELECT
                dvd_id,
                rank
            FROM ranking_snapshots
            WHERE chart_type = ?
              AND period = ?
            ORDER BY rank ASC
            """,
            (
                chart_type,
                period,
            ),
        ).fetchall()
    )

    if len(
        stored
    ) != WEEKLY_EXPECTED_COUNT:
        raise RuntimeError(
            "weekly snapshot "
            "write count mismatch"
        )

    stored_ids = [
        row[
            "dvd_id"
        ]
        for row
        in stored
    ]

    expected_ids = [
        item[
            "dvd_id"
        ]
        for item
        in items
    ]

    if stored_ids != expected_ids:
        raise RuntimeError(
            "weekly snapshot "
            "stored order mismatch"
        )

    stored_ranks = [
        int(
            row[
                "rank"
            ]
        )
        for row
        in stored
    ]

    if stored_ranks != list(
        range(
            1,
            WEEKLY_EXPECTED_COUNT + 1,
        )
    ):
        raise RuntimeError(
            "weekly snapshot "
            "stored rank mismatch"
        )

    return {
        "chart_type":
            chart_type,

        "period":
            period,

        "written":
            WEEKLY_EXPECTED_COUNT,

        "metadata_updated":
            metadata_updated,

        "metadata_preserved":
            metadata_preserved,

        "observed_at":
            observed_at,
    }


def replace_weekly_snapshot(
    connection: sqlite3.Connection,
    snapshot: dict,
    *,
    observed_at: str,
) -> dict:
    #
    # Preserve the existing public API:
    # one Weekly snapshot owns one
    # transaction.
    #
    values = (
        validate_weekly_snapshot(
            snapshot
        )
    )

    observed_at = (
        _validated_observed_at(
            observed_at
        )
    )

    connection.execute(
        "BEGIN IMMEDIATE"
    )

    try:
        result = (
            _write_validated_weekly_snapshot(
                connection,
                values,
                observed_at,
            )
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    return result


def replace_weekly_snapshots_batch(
    connection: sqlite3.Connection,
    entries: list[dict],
) -> dict:
    #
    # Validate the entire batch before
    # acquiring a write transaction.
    #
    if (
        not isinstance(
            entries,
            list,
        )
        or not entries
    ):
        raise ValueError(
            "weekly batch must be "
            "non-empty list"
        )

    validated = []
    seen_periods = set()

    for entry in entries:
        if not isinstance(
            entry,
            dict,
        ):
            raise ValueError(
                "weekly batch entry "
                "must be object"
            )

        if "snapshot" not in entry:
            raise ValueError(
                "weekly batch snapshot "
                "missing"
            )

        if "observed_at" not in entry:
            raise ValueError(
                "weekly batch observed_at "
                "missing"
            )

        values = (
            validate_weekly_snapshot(
                entry[
                    "snapshot"
                ]
            )
        )

        observed_at = (
            _validated_observed_at(
                entry[
                    "observed_at"
                ]
            )
        )

        period = values[
            "period"
        ]

        if period in seen_periods:
            raise ValueError(
                "duplicate weekly batch "
                "period: "
                + period
            )

        seen_periods.add(
            period
        )

        validated.append({
            "period":
                period,

            "values":
                values,

            "observed_at":
                observed_at,
        })

    #
    # Oldest to newest is intentional.
    # If a title appears in multiple
    # historical weeks, its newest
    # metadata wins deterministically.
    #
    validated.sort(
        key=lambda value:
            _weekly_period_key(
                value[
                    "period"
                ]
            )
    )

    connection.execute(
        "BEGIN IMMEDIATE"
    )

    results = []

    try:
        for value in validated:
            results.append(
                _write_validated_weekly_snapshot(
                    connection,
                    value[
                        "values"
                    ],
                    value[
                        "observed_at"
                    ],
                )
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    return {
        "chart_type":
            WEEKLY_CHART_TYPE,

        "periods":
            [
                result[
                    "period"
                ]
                for result
                in results
            ],

        "snapshots":
            len(
                results
            ),

        "written":
            sum(
                result[
                    "written"
                ]
                for result
                in results
            ),

        "metadata_updated":
            sum(
                result[
                    "metadata_updated"
                ]
                for result
                in results
            ),

        "metadata_preserved":
            sum(
                result[
                    "metadata_preserved"
                ]
                for result
                in results
            ),

        "results":
            results,
    }




def list_weekly_snapshot(
    connection: sqlite3.Connection,
    period: str,
) -> list[sqlite3.Row]:
    period = _text(
        period
    )

    if (
        not period
        or not PERIOD_RE.fullmatch(
            period
        )
    ):
        raise ValueError(
            "invalid weekly period"
        )

    return list(
        connection.execute(
            """
            SELECT
                snapshot_id,
                chart_type,
                period,
                dvd_id,
                rank,
                score,
                observed_at
            FROM ranking_snapshots
            WHERE chart_type = ?
              AND period = ?
            ORDER BY rank ASC
            """,
            (
                WEEKLY_CHART_TYPE,
                period,
            ),
        ).fetchall()
    )
