from __future__ import annotations

import re
import sqlite3
from typing import Any

from teddy_discovery_rankings import (
    WEEKLY_CHART_TYPE,
    WEEKLY_EXPECTED_COUNT,
)


MONTHLY_WINDOW_WEEKS = 4
MONTHLY_DEFAULT_LIMIT = 25

MONTHLY_LABEL = (
    "Teddy 월간 랭킹 · "
    "JAV Database 최근 4주 합산"
)

MONTHLY_FORMULA = (
    "26-rank"
)

MONTHLY_TIEBREAK = (
    "latest-week-rank,"
    "latest-appearance,"
    "dvd-id"
)


PERIOD_RE = re.compile(
    r"^(?P<year>\d{4})"
    r"-W(?P<week>\d{2})$"
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


def _period_key(
    period: Any,
) -> tuple[int, int]:
    period = _text(
        period
    )

    if not period:
        raise ValueError(
            "monthly Weekly period missing"
        )

    match = PERIOD_RE.fullmatch(
        period
    )

    if match is None:
        raise ValueError(
            "invalid monthly Weekly period"
        )

    year = int(
        match.group(
            "year"
        )
    )

    week = int(
        match.group(
            "week"
        )
    )

    if (
        year < 2000
        or year > 2100
        or week < 1
        or week > 53
    ):
        raise ValueError(
            "invalid monthly Weekly period"
        )

    return (
        year,
        week,
    )


def _validated_limit(
    value: Any,
) -> int:
    if (
        type(value) is not int
        or value < 1
        or value > 500
    ):
        raise ValueError(
            "monthly limit must be 1..500"
        )

    return value


def _latest_four_periods(
    connection: sqlite3.Connection,
) -> list[str]:
    rows = connection.execute(
        """
        SELECT DISTINCT period
        FROM ranking_snapshots
        WHERE chart_type = ?
        """,
        (
            WEEKLY_CHART_TYPE,
        ),
    ).fetchall()

    periods = sorted(
        {
            str(
                row[
                    "period"
                ]
            )
            for row
            in rows
        },
        key=_period_key,
    )

    if len(
        periods
    ) < MONTHLY_WINDOW_WEEKS:
        raise RuntimeError(
            "monthly ranking requires "
            "at least four Weekly snapshots"
        )

    return periods[
        -MONTHLY_WINDOW_WEEKS:
    ]


def _monthly_sort_key(
    item: dict,
    latest_period: str,
):
    latest_week_rank = (
        item[
            "weekly_ranks"
        ].get(
            latest_period
        )
    )

    if latest_week_rank is None:
        latest_week_rank = (
            WEEKLY_EXPECTED_COUNT
            + 1
        )

    latest_year, latest_week = (
        _period_key(
            item[
                "latest_appearance"
            ]
        )
    )

    return (
        -int(
            item[
                "score"
            ]
        ),

        int(
            latest_week_rank
        ),

        -latest_year,
        -latest_week,

        item[
            "dvd_id"
        ],
    )


def _derive_items(
    rows: list[dict],
    periods: list[str],
) -> list[dict]:
    if len(
        periods
    ) != MONTHLY_WINDOW_WEEKS:
        raise ValueError(
            "monthly derivation requires "
            "exactly four periods"
        )

    periods = sorted(
        periods,
        key=_period_key,
    )

    latest_period = (
        periods[-1]
    )

    period_counts = {
        period:
            0
        for period
        in periods
    }

    period_ranks = {
        period:
            set()
        for period
        in periods
    }

    period_ids = {
        period:
            set()
        for period
        in periods
    }

    by_title = {}

    for row in rows:
        period = _text(
            row.get(
                "period"
            )
        )

        if period not in period_counts:
            raise ValueError(
                "monthly row escaped "
                "selected periods"
            )

        dvd_id = _text(
            row.get(
                "dvd_id"
            )
        )

        if not dvd_id:
            raise ValueError(
                "monthly DVD ID missing"
            )

        rank = row.get(
            "rank"
        )

        if (
            type(rank) is not int
            or rank < 1
            or rank
            > WEEKLY_EXPECTED_COUNT
        ):
            raise ValueError(
                "invalid monthly Weekly rank"
            )

        if rank in period_ranks[
            period
        ]:
            raise ValueError(
                "duplicate monthly Weekly rank"
            )

        if dvd_id in period_ids[
            period
        ]:
            raise ValueError(
                "duplicate monthly Weekly DVD ID"
            )

        period_counts[
            period
        ] += 1

        period_ranks[
            period
        ].add(
            rank
        )

        period_ids[
            period
        ].add(
            dvd_id
        )

        value = by_title.setdefault(
            dvd_id,
            {
                "dvd_id":
                    dvd_id,

                "title":
                    row.get(
                        "title"
                    ),

                "release_date":
                    row.get(
                        "release_date"
                    ),

                "maker":
                    row.get(
                        "maker"
                    ),

                "cover_url":
                    row.get(
                        "cover_url"
                    ),

                "metadata_source":
                    row.get(
                        "metadata_source"
                    ),

                "weekly_ranks": {
                    selected_period:
                        None
                    for selected_period
                    in periods
                },

                "score":
                    0,

                "appearances":
                    0,
            },
        )

        value[
            "weekly_ranks"
        ][
            period
        ] = rank

        value[
            "score"
        ] += (
            WEEKLY_EXPECTED_COUNT
            + 1
            - rank
        )

        value[
            "appearances"
        ] += 1

    for period in periods:
        if period_counts[
            period
        ] != WEEKLY_EXPECTED_COUNT:
            raise RuntimeError(
                period
                + " must contain "
                "exactly 25 Weekly rows"
            )

        if period_ranks[
            period
        ] != set(
            range(
                1,
                WEEKLY_EXPECTED_COUNT + 1,
            )
        ):
            raise RuntimeError(
                period
                + " Weekly ranks must "
                "be exact 1..25"
            )

    for value in (
        by_title.values()
    ):
        appearances = [
            period
            for period
            in periods
            if value[
                "weekly_ranks"
            ][
                period
            ]
            is not None
        ]

        if not appearances:
            raise RuntimeError(
                "monthly title has "
                "no appearances"
            )

        value[
            "latest_appearance"
        ] = max(
            appearances,
            key=_period_key,
        )

        value[
            "latest_appearance_rank"
        ] = value[
            "weekly_ranks"
        ][
            value[
                "latest_appearance"
            ]
        ]

        value[
            "latest_week_rank"
        ] = value[
            "weekly_ranks"
        ][
            latest_period
        ]

    ranking = sorted(
        by_title.values(),
        key=lambda item:
            _monthly_sort_key(
                item,
                latest_period,
            ),
    )

    for monthly_rank, value in enumerate(
        ranking,
        start=1,
    ):
        value[
            "rank"
        ] = monthly_rank

    return ranking


def derive_monthly_ranking(
    connection: sqlite3.Connection,
    *,
    limit: int = MONTHLY_DEFAULT_LIMIT,
) -> dict:
    limit = _validated_limit(
        limit
    )

    periods = (
        _latest_four_periods(
            connection
        )
    )

    placeholders = ",".join(
        "?"
        for _ in periods
    )

    rows = connection.execute(
        f"""
        SELECT
            r.period,
            r.dvd_id,
            r.rank,
            t.title,
            t.release_date,
            t.maker,
            t.cover_url,
            t.metadata_source
        FROM ranking_snapshots AS r
        LEFT JOIN titles AS t
          ON t.dvd_id = r.dvd_id
        WHERE r.chart_type = ?
          AND r.period IN (
              {placeholders}
          )
        ORDER BY
            r.period,
            r.rank
        """,
        (
            WEEKLY_CHART_TYPE,
            *periods,
        ),
    ).fetchall()

    values = [
        dict(row)
        for row
        in rows
    ]

    expected_rows = (
        MONTHLY_WINDOW_WEEKS
        * WEEKLY_EXPECTED_COUNT
    )

    if len(
        values
    ) != expected_rows:
        raise RuntimeError(
            "monthly derivation requires "
            "exactly 100 Weekly rows"
        )

    ranking = (
        _derive_items(
            values,
            periods,
        )
    )

    selected = ranking[
        :limit
    ]

    return {
        "source":
            "teddy-monthly",

        "basis_chart_type":
            WEEKLY_CHART_TYPE,

        "label":
            MONTHLY_LABEL,

        "formula":
            MONTHLY_FORMULA,

        "tie_break":
            MONTHLY_TIEBREAK,

        "periods":
            periods,

        "latest_period":
            periods[-1],

        "window_weeks":
            MONTHLY_WINDOW_WEEKS,

        "weekly_row_count":
            expected_rows,

        "total_unique_titles":
            len(
                ranking
            ),

        "item_count":
            len(
                selected
            ),

        "items":
            selected,
    }
