from __future__ import annotations

from datetime import (
    date,
    datetime,
    timedelta,
    timezone,
)
import sqlite3
from typing import Any

from teddy_discovery_availability import (
    SOURCE_MISSAV,
    STATUS_FOUND,
)

from teddy_discovery_variants import (
    VARIANT_STANDARD,
    VARIANT_UNCENSORED,
)


DEFAULT_NEAR_FUTURE_DAYS = 7


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
            parsed = (
                datetime.fromisoformat(
                    raw
                )
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


def _parse_checked_at(
    value: Any,
) -> datetime | None:
    raw = _text(
        value
    )

    if not raw:
        return None

    try:
        parsed = datetime.fromisoformat(
            raw
        )

    except ValueError:
        return None

    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
    ):
        return None

    return parsed.astimezone(
        timezone.utc
    ).replace(
        microsecond=0
    )


def _priority_for_release(
    release_date: date | None,
    *,
    today: date,
    near_future_days: int,
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

    if delta > near_future_days:
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

    if 1 <= delta <= near_future_days:
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


def build_variant_probe_plan(
    connection: sqlite3.Connection,
    *,
    now: Any,
    max_items: int,
    recheck_after_hours: int,
    near_future_days: int = (
        DEFAULT_NEAR_FUTURE_DAYS
    ),
) -> dict:
    if (
        type(max_items) is not int
        or max_items < 1
        or max_items > 100
    ):
        raise ValueError(
            "max_items must be 1..100"
        )

    if (
        type(recheck_after_hours)
        is not int
        or recheck_after_hours < 1
        or recheck_after_hours > 168
    ):
        raise ValueError(
            "recheck_after_hours "
            "must be 1..168"
        )

    if (
        type(near_future_days)
        is not int
        or near_future_days < 1
        or near_future_days > 30
    ):
        raise ValueError(
            "near_future_days "
            "must be 1..30"
        )

    now_dt = _parse_now(
        now
    )

    cutoff = (
        now_dt
        - timedelta(
            hours=
                recheck_after_hours
        )
    )

    rows = connection.execute(
        """
        SELECT
            t.dvd_id,
            t.release_date,

            a.status
                AS missav_status,

            standard.last_checked_at
                AS standard_last_checked_at,

            uncensored.confirmed
                AS uncensored_confirmed

        FROM titles AS t

        JOIN availability AS a
          ON a.dvd_id = t.dvd_id
         AND a.source = ?

        LEFT JOIN title_variants
            AS standard
          ON standard.dvd_id =
                t.dvd_id
         AND standard.source = ?
         AND standard.variant_kind = ?

        LEFT JOIN title_variants
            AS uncensored
          ON uncensored.dvd_id =
                t.dvd_id
         AND uncensored.source = ?
         AND uncensored.variant_kind = ?
         AND uncensored.confirmed = 1

        WHERE a.status = ?

        ORDER BY
            t.dvd_id ASC
        """,
        (
            SOURCE_MISSAV,
            SOURCE_MISSAV,
            VARIANT_STANDARD,
            SOURCE_MISSAV,
            VARIANT_UNCENSORED,
            STATUS_FOUND,
        ),
    ).fetchall()

    due = []

    fresh_count = 0
    uncensored_confirmed_count = 0
    far_future_count = 0

    for row in rows:
        dvd_id = str(
            row[
                "dvd_id"
            ]
        )

        if row[
            "uncensored_confirmed"
        ] == 1:
            uncensored_confirmed_count += 1
            continue

        release = (
            _parse_release_date(
                row[
                    "release_date"
                ]
            )
        )

        (
            priority,
            priority_name,
            distance_days,
        ) = _priority_for_release(
            release,
            today=
                now_dt.date(),
            near_future_days=
                near_future_days,
        )

        if priority is None:
            far_future_count += 1
            continue

        checked = (
            _parse_checked_at(
                row[
                    "standard_last_checked_at"
                ]
            )
        )

        if (
            checked is not None
            and checked > cutoff
        ):
            fresh_count += 1
            continue

        due.append({
            "dvd_id":
                dvd_id,

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
                distance_days,

            "standard_last_checked_at":
                (
                    checked.isoformat()
                    if checked is not None
                    else None
                ),
        })

    minimum_time = datetime(
        1970,
        1,
        1,
        tzinfo=timezone.utc,
    )

    due.sort(
        key=lambda item: (
            item[
                "priority"
            ],

            0
            if item[
                "standard_last_checked_at"
            ] is None
            else 1,

            item[
                "priority_distance_days"
            ],

            (
                _parse_checked_at(
                    item[
                        "standard_last_checked_at"
                    ]
                )
                or minimum_time
            ),

            item[
                "dvd_id"
            ],
        )
    )

    selected = due[
        :max_items
    ]

    return {
        "generated_at":
            now_dt.isoformat(),

        "policy": (
            "today>recent7>"
            "near-future>"
            "older-or-undated"
        ),

        "max_items":
            max_items,

        "recheck_after_hours":
            recheck_after_hours,

        "near_future_days":
            near_future_days,

        "missav_found_count":
            len(
                rows
            ),

        "uncensored_confirmed_count":
            uncensored_confirmed_count,

        "fresh_watermark_count":
            fresh_count,

        "far_future_count":
            far_future_count,

        "due_count":
            len(
                due
            ),

        "selected_count":
            len(
                selected
            ),

        "remaining_due_count":
            max(
                0,
                len(
                    due
                )
                - len(
                    selected
                ),
            ),

        "selected":
            selected,
    }
