from __future__ import annotations

from pathlib import Path
import sqlite3
import sys

from teddy_discovery_availability_batch import (
    build_due_request_plan,
    full_ui_universe,
)


NOW = (
    "2026-08-26T08:59:44+00:00"
)


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


def connect_ro(
    path: Path,
):
    connection = sqlite3.connect(
        "file:"
        + str(path)
        + "?mode=ro",
        uri=True,
    )

    connection.row_factory = (
        sqlite3.Row
    )

    return connection


def real_plan_smoke(
    db_path: Path,
):
    connection = connect_ro(
        db_path
    )

    try:
        universe = full_ui_universe(
            connection
        )

        plan = build_due_request_plan(
            connection,
            now=NOW,
            max_requests=20,
        )

        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

    finally:
        connection.close()

    require(
        universe[
            "latest_count"
        ]
        == 50,
        "Latest universe changed",
    )

    require(
        universe[
            "weekly_period"
        ]
        == "2026-W33",
        "Weekly period changed",
    )

    require(
        universe[
            "weekly_count"
        ]
        == 25,
        "Weekly count changed",
    )

    require(
        universe[
            "monthly_full_count"
        ]
        == 68,
        "Monthly universe changed",
    )

    require(
        universe[
            "total"
        ]
        == 117,
        "Full UI universe changed",
    )

    require(
        plan[
            "possible_checks"
        ]
        == 234,
        "possible availability "
        "check count changed",
    )

    require(
        plan[
            "due_count"
        ]
        == 233,
        "current due count changed",
    )

    require(
        plan[
            "fresh_count"
        ]
        == 1,
        "current fresh count changed",
    )

    require(
        plan[
            "selected_count"
        ]
        == 20,
        "batch request ceiling changed",
    )

    require(
        plan[
            "remaining_after_batch"
        ]
        == 213,
        "remaining request count changed",
    )

    expected_first = [
        (
            "SDNM-560",
            "123av",
        ),
        (
            "SDMM-238",
            "missav",
        ),
        (
            "SDMM-238",
            "123av",
        ),
        (
            "SDAB-356",
            "missav",
        ),
        (
            "SDAB-356",
            "123av",
        ),
    ]

    observed_first = [
        (
            item[
                "dvd_id"
            ],
            item[
                "source"
            ],
        )
        for item
        in plan[
            "selected"
        ][
            :5
        ]
    ]

    require(
        observed_first
        == expected_first,
        "availability priority "
        "order changed",
    )

    require(
        integrity == "ok",
        "real DB integrity failed",
    )

    print(
        "AVAILABILITY_FULL_UI_117_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_DUE_233_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_BATCH_LIMIT_20_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_PRIORITY_ORDER_SMOKE=PASS"
    )


def limit_smoke(
    db_path: Path,
):
    connection = connect_ro(
        db_path
    )

    try:
        one = build_due_request_plan(
            connection,
            now=NOW,
            max_requests=1,
        )

        require(
            one[
                "selected_count"
            ]
            == 1,
            "single request batch changed",
        )

        require(
            one[
                "selected"
            ][0][
                "dvd_id"
            ]
            == "SDNM-560",
            "single request priority changed",
        )

        require(
            one[
                "selected"
            ][0][
                "source"
            ]
            == "123av",
            "single request source changed",
        )

        for invalid in (
            0,
            -1,
            201,
            True,
            "20",
        ):
            try:
                build_due_request_plan(
                    connection,
                    now=NOW,
                    max_requests=invalid,
                )

            except ValueError:
                pass

            else:
                raise RuntimeError(
                    "invalid max_requests "
                    "must fail closed"
                )

    finally:
        connection.close()

    print(
        "AVAILABILITY_BATCH_LIMIT_FAIL_CLOSED_SMOKE=PASS"
    )


def main():
    if len(
        sys.argv
    ) != 2:
        raise RuntimeError(
            "usage: "
            "teddy_discovery_availability_batch_smoke.py "
            "<stage4-db>"
        )

    db_path = Path(
        sys.argv[1]
    )

    real_plan_smoke(
        db_path
    )

    limit_smoke(
        db_path
    )

    print(
        "TEDDY_AVAILABILITY_BATCH_PLANNER_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
