from __future__ import annotations

import sqlite3
from typing import Any

from teddy_discovery_availability import (
    AVAILABILITY_SOURCES,
    AVAILABILITY_STATUSES,
    STATUS_FOUND,
    STATUS_UNKNOWN,
)

from teddy_discovery_category import (
    derive_category_ranking,
    list_category_facets,
)

from teddy_discovery_missav import (
    list_latest_items,
)

from teddy_discovery_monthly import (
    derive_monthly_ranking,
)

from teddy_discovery_rankings import (
    WEEKLY_CHART_TYPE,
    WEEKLY_EXPECTED_COUNT,
    list_weekly_snapshot,
)


UI_MAX_LIMIT = 500


def _require_connection(
    connection: sqlite3.Connection,
) -> None:
    if not isinstance(
        connection,
        sqlite3.Connection,
    ):
        raise TypeError(
            "UI data connection must "
            "be sqlite3.Connection"
        )

    if (
        connection.row_factory
        is not sqlite3.Row
    ):
        raise ValueError(
            "UI data connection must "
            "use sqlite3.Row"
        )


def _validated_limit(
    value: Any,
    *,
    maximum: int = UI_MAX_LIMIT,
) -> int:
    if (
        type(value) is not int
        or value < 1
        or value > maximum
    ):
        raise ValueError(
            "UI data limit must be "
            "1.."
            + str(maximum)
        )

    return value


def _unique_dvd_ids(
    items: list[dict],
) -> list[str]:
    values = []
    seen = set()

    for item in items:
        dvd_id = item.get(
            "dvd_id"
        )

        if (
            not isinstance(
                dvd_id,
                str,
            )
            or not dvd_id.strip()
        ):
            raise ValueError(
                "UI item DVD ID missing"
            )

        dvd_id = dvd_id.strip()

        if dvd_id in seen:
            raise RuntimeError(
                "duplicate DVD ID "
                "in UI ranking"
            )

        seen.add(
            dvd_id
        )

        values.append(
            dvd_id
        )

    return values


def _placeholders(
    values: list[str],
) -> str:
    if not values:
        raise ValueError(
            "SQL value set empty"
        )

    return ",".join(
        "?"
        for _ in values
    )


def _load_enrichment(
    connection: sqlite3.Connection,
    dvd_ids: list[str],
) -> dict:
    if not dvd_ids:
        return {
            "titles": {},
            "people": {},
            "genres": {},
            "holdings": {},
            "availability": {},
        }

    placeholders = _placeholders(
        dvd_ids
    )

    title_rows = connection.execute(
        f"""
        SELECT
            dvd_id,
            title,
            release_date,
            maker,
            metadata_source
        FROM titles
        WHERE dvd_id IN (
            {placeholders}
        )
        """,
        dvd_ids,
    ).fetchall()

    titles = {
        row["dvd_id"]:
            dict(row)
        for row
        in title_rows
    }

    people = {
        dvd_id: []
        for dvd_id
        in dvd_ids
    }

    for row in connection.execute(
        f"""
        SELECT
            tp.dvd_id,
            p.name,
            p.person_id
        FROM title_people AS tp
        JOIN people AS p
          ON p.person_id = tp.person_id
        WHERE tp.dvd_id IN (
            {placeholders}
        )
        ORDER BY
            tp.dvd_id,
            p.name COLLATE NOCASE,
            p.name,
            p.person_id
        """,
        dvd_ids,
    ).fetchall():
        people[
            row["dvd_id"]
        ].append(
            row["name"]
        )

    genres = {
        dvd_id: []
        for dvd_id
        in dvd_ids
    }

    for row in connection.execute(
        f"""
        SELECT
            tg.dvd_id,
            g.name,
            g.genre_id
        FROM title_genres AS tg
        JOIN genres AS g
          ON g.genre_id = tg.genre_id
        WHERE tg.dvd_id IN (
            {placeholders}
        )
        ORDER BY
            tg.dvd_id,
            g.name COLLATE NOCASE,
            g.name,
            g.genre_id
        """,
        dvd_ids,
    ).fetchall():
        genres[
            row["dvd_id"]
        ].append(
            row["name"]
        )

    holdings = {
        dvd_id:
            0
        for dvd_id
        in dvd_ids
    }

    for row in connection.execute(
        f"""
        SELECT
            dvd_id,
            COUNT(*) AS holding_count
        FROM holdings
        WHERE dvd_id IN (
            {placeholders}
        )
          AND parse_status = 'MATCHED'
          AND present = 1
        GROUP BY dvd_id
        """,
        dvd_ids,
    ).fetchall():
        count = int(
            row["holding_count"]
        )

        if count < 1:
            raise RuntimeError(
                "invalid holding count"
            )

        holdings[
            row["dvd_id"]
        ] = count

    availability = {
        dvd_id: {}
        for dvd_id
        in dvd_ids
    }

    for row in connection.execute(
        f"""
        SELECT
            dvd_id,
            source,
            status,
            last_checked_at,
            next_check_at,
            fail_count
        FROM availability
        WHERE dvd_id IN (
            {placeholders}
        )
        ORDER BY
            dvd_id,
            source
        """,
        dvd_ids,
    ).fetchall():
        dvd_id = row[
            "dvd_id"
        ]

        source = row[
            "source"
        ]

        status = row[
            "status"
        ]

        if (
            source
            not in AVAILABILITY_SOURCES
        ):
            raise RuntimeError(
                "stored availability "
                "source invalid"
            )

        if (
            status
            not in AVAILABILITY_STATUSES
        ):
            raise RuntimeError(
                "stored availability "
                "status invalid"
            )

        if (
            source
            in availability[
                dvd_id
            ]
        ):
            raise RuntimeError(
                "duplicate availability "
                "row"
            )

        fail_count = int(
            row["fail_count"]
        )

        if fail_count < 0:
            raise RuntimeError(
                "availability fail_count "
                "invalid"
            )

        availability[
            dvd_id
        ][
            source
        ] = {
            "status":
                status,

            "known":
                True,

            "last_checked_at":
                row[
                    "last_checked_at"
                ],

            "next_check_at":
                row[
                    "next_check_at"
                ],

            "fail_count":
                fail_count,
        }

    return {
        "titles":
            titles,

        "people":
            people,

        "genres":
            genres,

        "holdings":
            holdings,

        "availability":
            availability,
    }


def _safe_metadata_value(
    metadata: dict,
    item: dict,
    key: str,
):
    value = metadata.get(
        key
    )

    if value is not None:
        return value

    return item.get(
        key
    )


def _build_ui_items(
    connection: sqlite3.Connection,
    items: list[dict],
    *,
    ranking_builder,
) -> list[dict]:
    dvd_ids = _unique_dvd_ids(
        items
    )

    enrichment = _load_enrichment(
        connection,
        dvd_ids,
    )

    result = []

    for rank, item in enumerate(
        items,
        start=1,
    ):
        dvd_id = item[
            "dvd_id"
        ]

        metadata = (
            enrichment[
                "titles"
            ].get(
                dvd_id,
                {},
            )
        )

        holding_count = int(
            enrichment[
                "holdings"
            ].get(
                dvd_id,
                0,
            )
        )

        stored_availability = (
            enrichment[
                "availability"
            ].get(
                dvd_id,
                {},
            )
        )

        availability = {}
        available_sources = []

        for source in (
            AVAILABILITY_SOURCES
        ):
            stored = (
                stored_availability.get(
                    source
                )
            )

            if stored is None:
                value = {
                    "status":
                        STATUS_UNKNOWN,

                    "known":
                        False,

                    "last_checked_at":
                        None,

                    "next_check_at":
                        None,

                    "fail_count":
                        0,
                }

            else:
                value = dict(
                    stored
                )

            availability[
                source
            ] = value

            if (
                value[
                    "status"
                ]
                == STATUS_FOUND
            ):
                available_sources.append(
                    source
                )

        result.append({
            "rank":
                rank,

            "dvd_id":
                dvd_id,

            "title":
                _safe_metadata_value(
                    metadata,
                    item,
                    "title",
                ),

            "release_date":
                _safe_metadata_value(
                    metadata,
                    item,
                    "release_date",
                ),

            "maker":
                _safe_metadata_value(
                    metadata,
                    item,
                    "maker",
                ),

            "metadata_source":
                _safe_metadata_value(
                    metadata,
                    item,
                    "metadata_source",
                ),

            "people":
                list(
                    enrichment[
                        "people"
                    ].get(
                        dvd_id,
                        [],
                    )
                ),

            "genres":
                list(
                    enrichment[
                        "genres"
                    ].get(
                        dvd_id,
                        [],
                    )
                ),

            "owned":
                holding_count > 0,

            "holding_count":
                holding_count,

            "availability":
                availability,

            "availability_complete":
                all(
                    availability[
                        source
                    ][
                        "known"
                    ]
                    for source
                    in AVAILABILITY_SOURCES
                ),

            "available_sources":
                available_sources,

            "ranking":
                ranking_builder(
                    item,
                    rank,
                ),
        })

    return result


def build_latest_view(
    connection: sqlite3.Connection,
    *,
    limit: int = 50,
) -> dict:
    _require_connection(
        connection
    )

    limit = _validated_limit(
        limit
    )

    raw = list_latest_items(
        connection,
        limit=limit,
    )

    items = _build_ui_items(
        connection,
        raw,
        ranking_builder=lambda item, rank: {
            "kind":
                "latest",

            "source":
                item[
                    "source"
                ],

            "first_seen_at":
                item[
                    "first_seen_at"
                ],

            "last_seen_at":
                item[
                    "last_seen_at"
                ],

            "first_position":
                item[
                    "first_position"
                ],

            "last_position":
                item[
                    "last_position"
                ],
        },
    )

    return {
        "view":
            "latest",

        "label":
            "Teddy 최신 출시 · "
            "MissAV 새로운 출시",

        "item_count":
            len(
                items
            ),

        "items":
            items,
    }


def _latest_weekly_period(
    connection: sqlite3.Connection,
) -> str:
    row = connection.execute(
        """
        SELECT period
        FROM ranking_snapshots
        WHERE chart_type = ?
        GROUP BY period
        ORDER BY period DESC
        LIMIT 1
        """,
        (
            WEEKLY_CHART_TYPE,
        ),
    ).fetchone()

    if row is None:
        raise RuntimeError(
            "Weekly snapshot missing"
        )

    period = row[
        "period"
    ]

    if (
        not isinstance(
            period,
            str,
        )
        or not period
    ):
        raise RuntimeError(
            "Weekly period invalid"
        )

    return period


def build_weekly_view(
    connection: sqlite3.Connection,
    *,
    period: str | None = None,
    limit: int = WEEKLY_EXPECTED_COUNT,
) -> dict:
    _require_connection(
        connection
    )

    limit = _validated_limit(
        limit,
        maximum=
            WEEKLY_EXPECTED_COUNT,
    )

    if period is None:
        period = _latest_weekly_period(
            connection
        )

    raw_rows = list_weekly_snapshot(
        connection,
        period,
    )

    if len(
        raw_rows
    ) != WEEKLY_EXPECTED_COUNT:
        raise RuntimeError(
            "Weekly UI requires "
            "exactly 25 rows"
        )

    raw = [
        dict(row)
        for row
        in raw_rows[
            :limit
        ]
    ]

    items = _build_ui_items(
        connection,
        raw,
        ranking_builder=lambda item, rank: {
            "kind":
                "weekly",

            "chart_type":
                item[
                    "chart_type"
                ],

            "period":
                item[
                    "period"
                ],

            "snapshot_rank":
                item[
                    "rank"
                ],

            "score":
                item[
                    "score"
                ],

            "observed_at":
                item[
                    "observed_at"
                ],
        },
    )

    for index, item in enumerate(
        items,
        start=1,
    ):
        if (
            item[
                "ranking"
            ][
                "snapshot_rank"
            ]
            != index
        ):
            raise RuntimeError(
                "Weekly ranking order "
                "changed in UI layer"
            )

    return {
        "view":
            "weekly",

        "chart_type":
            WEEKLY_CHART_TYPE,

        "period":
            period,

        "label":
            "JAV Database 주간 랭킹 · "
            + period,

        "total_items":
            WEEKLY_EXPECTED_COUNT,

        "item_count":
            len(
                items
            ),

        "items":
            items,
    }


def build_monthly_view(
    connection: sqlite3.Connection,
    *,
    limit: int = 25,
) -> dict:
    _require_connection(
        connection
    )

    limit = _validated_limit(
        limit
    )

    monthly = derive_monthly_ranking(
        connection,
        limit=limit,
    )

    raw = [
        dict(item)
        for item
        in monthly[
            "items"
        ]
    ]

    items = _build_ui_items(
        connection,
        raw,
        ranking_builder=lambda item, rank: {
            "kind":
                "monthly",

            "score":
                item[
                    "score"
                ],

            "appearances":
                item[
                    "appearances"
                ],

            "weekly_ranks":
                dict(
                    item[
                        "weekly_ranks"
                    ]
                ),

            "latest_appearance":
                item[
                    "latest_appearance"
                ],

            "latest_appearance_rank":
                item[
                    "latest_appearance_rank"
                ],

            "latest_week_rank":
                item[
                    "latest_week_rank"
                ],
        },
    )

    for index, item in enumerate(
        items,
        start=1,
    ):
        if item["rank"] != index:
            raise RuntimeError(
                "Monthly UI rank changed"
            )

        if (
            raw[
                index - 1
            ][
                "rank"
            ]
            != index
        ):
            raise RuntimeError(
                "Monthly source rank "
                "changed"
            )

    return {
        "view":
            "monthly",

        "source":
            monthly[
                "source"
            ],

        "basis_chart_type":
            monthly[
                "basis_chart_type"
            ],

        "label":
            monthly[
                "label"
            ],

        "formula":
            monthly[
                "formula"
            ],

        "tie_break":
            monthly[
                "tie_break"
            ],

        "periods":
            list(
                monthly[
                    "periods"
                ]
            ),

        "latest_period":
            monthly[
                "latest_period"
            ],

        "window_weeks":
            monthly[
                "window_weeks"
            ],

        "total_unique_titles":
            monthly[
                "total_unique_titles"
            ],

        "item_count":
            len(
                items
            ),

        "items":
            items,
    }


def build_category_facets_view(
    connection: sqlite3.Connection,
) -> dict:
    _require_connection(
        connection
    )

    facets = list_category_facets(
        connection
    )

    return {
        "view":
            "category-facets",

        "source":
            facets[
                "source"
            ],

        "basis_source":
            facets[
                "basis_source"
            ],

        "periods":
            list(
                facets[
                    "periods"
                ]
            ),

        "window_weeks":
            facets[
                "window_weeks"
            ],

        "monthly_unique_titles":
            facets[
                "monthly_unique_titles"
            ],

        "covered_titles":
            facets[
                "covered_titles"
            ],

        "uncovered_titles":
            facets[
                "uncovered_titles"
            ],

        "category_count":
            facets[
                "category_count"
            ],

        "categories": [
            dict(item)
            for item
            in facets[
                "categories"
            ]
        ],
    }


def build_category_view(
    connection: sqlite3.Connection,
    category: str,
    *,
    limit: int = 25,
) -> dict:
    _require_connection(
        connection
    )

    limit = _validated_limit(
        limit
    )

    category_result = (
        derive_category_ranking(
            connection,
            category,
            limit=limit,
        )
    )

    raw = [
        dict(item)
        for item
        in category_result[
            "items"
        ]
    ]

    items = _build_ui_items(
        connection,
        raw,
        ranking_builder=lambda item, rank: {
            "kind":
                "category",

            "category":
                item[
                    "category"
                ],

            "category_rank":
                item[
                    "category_rank"
                ],

            "monthly_rank":
                item[
                    "monthly_rank"
                ],

            "score":
                item[
                    "score"
                ],

            "appearances":
                item[
                    "appearances"
                ],

            "weekly_ranks":
                dict(
                    item[
                        "weekly_ranks"
                    ]
                ),

            "latest_appearance":
                item[
                    "latest_appearance"
                ],

            "latest_appearance_rank":
                item[
                    "latest_appearance_rank"
                ],

            "latest_week_rank":
                item[
                    "latest_week_rank"
                ],
        },
    )

    for index, item in enumerate(
        items,
        start=1,
    ):
        ranking = item[
            "ranking"
        ]

        if (
            ranking[
                "category_rank"
            ]
            != index
        ):
            raise RuntimeError(
                "Category ranking order "
                "changed in UI layer"
            )

    return {
        "view":
            "category",

        "source":
            category_result[
                "source"
            ],

        "basis_source":
            category_result[
                "basis_source"
            ],

        "basis_chart_type":
            category_result[
                "basis_chart_type"
            ],

        "category":
            category_result[
                "category"
            ],

        "label":
            category_result[
                "label"
            ],

        "formula":
            category_result[
                "formula"
            ],

        "tie_break":
            category_result[
                "tie_break"
            ],

        "periods":
            list(
                category_result[
                    "periods"
                ]
            ),

        "latest_period":
            category_result[
                "latest_period"
            ],

        "window_weeks":
            category_result[
                "window_weeks"
            ],

        "monthly_unique_titles":
            category_result[
                "monthly_unique_titles"
            ],

        "total_category_titles":
            category_result[
                "total_category_titles"
            ],

        "item_count":
            len(
                items
            ),

        "items":
            items,
    }
