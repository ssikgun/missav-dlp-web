from __future__ import annotations

import sqlite3
from typing import Any

from teddy_discovery_availability import (
    SOURCE_123AV,
    SOURCE_MISSAV,
)

from teddy_discovery_availability_store import (
    read_availability_cache,
)

from teddy_discovery_monthly import (
    derive_monthly_ranking,
)


DEFAULT_MAX_REQUESTS = 20
MAX_REQUESTS_LIMIT = 200


def _validated_max_requests(
    value: Any,
) -> int:
    if (
        type(value) is not int
        or value < 1
        or value > MAX_REQUESTS_LIMIT
    ):
        raise ValueError(
            "max_requests must be 1..200"
        )

    return value


def _append_unique(
    target: list[str],
    seen: set[str],
    values,
) -> None:
    for dvd_id in values:
        if dvd_id in seen:
            continue

        seen.add(
            dvd_id
        )

        target.append(
            dvd_id
        )


def full_ui_universe(
    connection: sqlite3.Connection,
) -> dict:
    latest = [
        row[
            "dvd_id"
        ]
        for row
        in connection.execute(
            """
            SELECT dvd_id
            FROM latest_items
            WHERE source =
                'missav-release'
            ORDER BY
                last_seen_at DESC,
                last_position ASC
            """
        ).fetchall()
    ]

    latest_week = connection.execute(
        """
        SELECT MAX(period)
        FROM ranking_snapshots
        WHERE chart_type =
            'javdatabase-weekly'
        """
    ).fetchone()[0]

    if latest_week is None:
        raise RuntimeError(
            "availability Weekly period missing"
        )

    weekly = [
        row[
            "dvd_id"
        ]
        for row
        in connection.execute(
            """
            SELECT dvd_id
            FROM ranking_snapshots
            WHERE chart_type =
                'javdatabase-weekly'
              AND period = ?
            ORDER BY rank
            """,
            (
                latest_week,
            ),
        ).fetchall()
    ]

    monthly = derive_monthly_ranking(
        connection,
        limit=500,
    )

    monthly_ids = [
        item[
            "dvd_id"
        ]
        for item
        in monthly[
            "items"
        ]
    ]

    ordered = []
    seen = set()

    #
    # Priority intentionally follows UI:
    # Latest first, then current Weekly,
    # then remaining full Monthly universe.
    #
    _append_unique(
        ordered,
        seen,
        latest,
    )

    _append_unique(
        ordered,
        seen,
        weekly,
    )

    _append_unique(
        ordered,
        seen,
        monthly_ids,
    )

    return {
        "latest_count":
            len(
                latest
            ),

        "weekly_period":
            latest_week,

        "weekly_count":
            len(
                weekly
            ),

        "monthly_full_count":
            len(
                monthly_ids
            ),

        "total":
            len(
                ordered
            ),

        "dvd_ids":
            ordered,
    }


def build_due_request_plan(
    connection: sqlite3.Connection,
    *,
    now: Any,
    max_requests: int = DEFAULT_MAX_REQUESTS,
) -> dict:
    max_requests = (
        _validated_max_requests(
            max_requests
        )
    )

    universe = full_ui_universe(
        connection
    )

    sources = (
        SOURCE_MISSAV,
        SOURCE_123AV,
    )

    due = []
    fresh = []

    for dvd_id in universe[
        "dvd_ids"
    ]:
        for source in sources:
            cache = read_availability_cache(
                connection,
                source=source,
                dvd_id=dvd_id,
                now=now,
            )

            item = {
                "dvd_id":
                    dvd_id,

                "source":
                    source,

                "known":
                    cache[
                        "known"
                    ],

                "status":
                    cache[
                        "status"
                    ],

                "fail_count":
                    cache[
                        "fail_count"
                    ],

                "next_check_at":
                    cache[
                        "next_check_at"
                    ],
            }

            if cache[
                "due"
            ]:
                due.append(
                    item
                )

            else:
                fresh.append(
                    item
                )

    selected = due[
        :max_requests
    ]

    return {
        "universe":
            universe,

        "source_count":
            len(
                sources
            ),

        "possible_checks":
            universe[
                "total"
            ]
            * len(
                sources
            ),

        "due_count":
            len(
                due
            ),

        "fresh_count":
            len(
                fresh
            ),

        "max_requests":
            max_requests,

        "selected_count":
            len(
                selected
            ),

        "remaining_after_batch":
            len(
                due
            )
            - len(
                selected
            ),

        "selected":
            selected,
    }
