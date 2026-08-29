from __future__ import annotations

from datetime import (
    date,
    datetime,
    timezone,
)
import sqlite3
from typing import Any

from teddy_discovery_availability import (
    SOURCE_123AV,
    SOURCE_MISSAV,
    STATUS_FOUND,
    STATUS_NOT_FOUND,
    STATUS_UNKNOWN,
)

from teddy_discovery_availability_store import (
    read_availability_cache,
)

from teddy_discovery_monthly import (
    derive_monthly_ranking,
)


DEFAULT_MAX_REQUESTS = 20
MAX_REQUESTS_LIMIT = 200
DEFAULT_NEAR_FUTURE_DAYS = 7


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


def _text(
    value: Any,
) -> str | None:
    if value is None:
        return None

    value = str(
        value
    ).strip()

    return value or None


def _parse_now(
    value: Any,
) -> datetime:
    if isinstance(
        value,
        datetime,
    ):
        parsed = value

    else:
        raw = _text(
            value
        )

        if not raw:
            raise ValueError(
                "now missing"
            )

        try:
            parsed = datetime.fromisoformat(
                raw
            )

        except ValueError as exc:
            raise ValueError(
                "now must be ISO-8601"
            ) from exc

    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
    ):
        raise ValueError(
            "now must be timezone-aware"
        )

    return parsed.astimezone(
        timezone.utc
    ).replace(
        microsecond=0
    )


def _parse_release_date(
    value: Any,
) -> date | None:
    raw = _text(
        value
    )

    if not raw:
        return None

    try:
        return date.fromisoformat(
            raw
        )

    except ValueError:
        return None


def _priority_for_release(
    release_date: date | None,
    *,
    today: date,
) -> tuple[int | None, str, int]:
    if release_date is None:
        return (
            3,
            "older-or-undated",
            999999,
        )

    delta = (
        release_date
        - today
    ).days

    if delta > DEFAULT_NEAR_FUTURE_DAYS:
        return (
            None,
            "far-future",
            delta,
        )

    if delta == 0:
        return (
            0,
            "today",
            0,
        )

    if -6 <= delta < 0:
        return (
            1,
            "recent7",
            abs(
                delta
            ),
        )

    if (
        1 <= delta
        <= DEFAULT_NEAR_FUTURE_DAYS
    ):
        return (
            2,
            "near-future",
            delta,
        )

    return (
        3,
        "older-or-undated",
        abs(
            delta
        ),
    )


def _due_sort_key(
    item: dict,
) -> tuple:
    #
    # Inside the older bucket, negative
    # and uncertain results stay ahead of
    # already-FOUND rows.
    #
    older_found = (
        1
        if (
            item[
                "priority"
            ] == 3
            and item[
                "status"
            ] == STATUS_FOUND
        )
        else 0
    )

    return (
        item[
            "priority"
        ],
        older_found,
        item[
            "priority_distance_days"
        ],
        item[
            "dvd_id"
        ],
        item[
            "source"
        ],
    )


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

    catalog_rows = connection.execute(
        """
        SELECT
            dvd_id,
            release_date
        FROM titles
        ORDER BY
            CASE
                WHEN release_date IS NULL
                THEN 1
                ELSE 0
            END,
            release_date DESC,
            dvd_id ASC
        """
    ).fetchall()

    catalog_ids = [
        row[
            "dvd_id"
        ]
        for row in catalog_rows
    ]

    release_dates = {
        row[
            "dvd_id"
        ]:
            row[
                "release_date"
            ]
        for row in catalog_rows
    }

    ordered = []
    seen = set()

    #
    # Keep the former UI members first only
    # as a stable legacy tie-break order.
    #
    # The full catalog is appended so the
    # availability worker is no longer
    # limited to Latest / Weekly / Monthly.
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

    _append_unique(
        ordered,
        seen,
        catalog_ids,
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

        "catalog_count":
            len(
                catalog_ids
            ),

        "release_dates":
            release_dates,

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

    now_dt = _parse_now(
        now
    )

    release_dates = universe.get(
        "release_dates",
        {},
    )

    sources = (
        SOURCE_MISSAV,
        SOURCE_123AV,
    )

    primary_due = []
    fallback_due = []
    fresh = []

    fallback_deferred_count = 0
    far_future_deferred_count = 0
    eligible_title_count = 0

    for dvd_id in universe[
        "dvd_ids"
    ]:
        release = _parse_release_date(
            release_dates.get(
                dvd_id
            )
        )

        (
            priority,
            priority_name,
            priority_distance_days,
        ) = _priority_for_release(
            release,
            today=now_dt.date(),
        )

        #
        # Do not spend availability requests
        # on FANZA seeds that are still more
        # than seven days from release.
        #
        if priority is None:
            far_future_deferred_count += 1
            continue

        eligible_title_count += 1
        #
        # MissAV is always the primary
        # availability source.
        #
        # A 123AV request is eligible only
        # while a recent, known MissAV result
        # says NOT_FOUND.
        #
        # If MissAV itself is due for a
        # re-check, re-check MissAV first and
        # defer 123AV until a later cycle.
        #
        missav_cache = (
            read_availability_cache(
                connection,
                source=
                    SOURCE_MISSAV,
                dvd_id=
                    dvd_id,
                now=
                    now,
            )
        )

        missav_item = {
            "dvd_id":
                dvd_id,

            "source":
                SOURCE_MISSAV,

            "release_date":
                (
                    release.isoformat()
                    if release is not None
                    else None
                ),

            "priority":
                priority,

            "priority_name":
                priority_name,

            "priority_distance_days":
                priority_distance_days,

            "known":
                missav_cache[
                    "known"
                ],

            "status":
                missav_cache[
                    "status"
                ],

            "fail_count":
                missav_cache[
                    "fail_count"
                ],

            "next_check_at":
                missav_cache[
                    "next_check_at"
                ],
        }

        if missav_cache[
            "due"
        ]:
            primary_due.append(
                missav_item
            )

        else:
            fresh.append(
                missav_item
            )

        fallback_allowed = (
            missav_cache[
                "known"
            ]
            and missav_cache[
                "status"
            ] == STATUS_NOT_FOUND
            and not missav_cache[
                "due"
            ]
        )

        if not fallback_allowed:
            fallback_deferred_count += 1
            continue

        fallback_cache = (
            read_availability_cache(
                connection,
                source=
                    SOURCE_123AV,
                dvd_id=
                    dvd_id,
                now=
                    now,
            )
        )

        fallback_item = {
            "dvd_id":
                dvd_id,

            "source":
                SOURCE_123AV,

            "release_date":
                (
                    release.isoformat()
                    if release is not None
                    else None
                ),

            "priority":
                priority,

            "priority_name":
                priority_name,

            "priority_distance_days":
                priority_distance_days,

            "known":
                fallback_cache[
                    "known"
                ],

            "status":
                fallback_cache[
                    "status"
                ],

            "fail_count":
                fallback_cache[
                    "fail_count"
                ],

            "next_check_at":
                fallback_cache[
                    "next_check_at"
                ],
        }

        if fallback_cache[
            "due"
        ]:
            fallback_due.append(
                fallback_item
            )

        else:
            fresh.append(
                fallback_item
            )

    #
    # R2 title priority:
    #
    # today
    # -> recent seven released dates
    # -> near future (<= 7 days)
    # -> older negative / uncertain
    # -> older FOUND
    #
    # MissAV remains globally ahead of
    # 123AV fallback.
    #
    primary_due.sort(
        key=_due_sort_key
    )

    fallback_due.sort(
        key=_due_sort_key
    )

    due = (
        primary_due
        + fallback_due
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

        "catalog_title_count":
            universe[
                "total"
            ],

        "eligible_title_count":
            eligible_title_count,

        "far_future_deferred_count":
            far_future_deferred_count,

        "near_future_days":
            DEFAULT_NEAR_FUTURE_DAYS,

        "possible_checks":
            eligible_title_count
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

        "fallback_deferred_count":
            fallback_deferred_count,

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
