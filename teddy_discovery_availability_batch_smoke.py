from __future__ import annotations

from pathlib import Path
import sqlite3
import sys

import teddy_discovery_availability_batch as batch

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


def _assert_selected_fallbacks_valid(
    connection,
    plan,
):
    seen_dvd_ids = set()

    for item in plan[
        "selected"
    ]:
        dvd_id = item[
            "dvd_id"
        ]

        require(
            dvd_id
            not in seen_dvd_ids,
            (
                "same DVD ID selected "
                "more than once"
            ),
        )

        seen_dvd_ids.add(
            dvd_id
        )

        if item[
            "source"
        ] != SOURCE_123AV:
            continue

        missav = read_availability_cache(
            connection,
            source=
                SOURCE_MISSAV,
            dvd_id=
                dvd_id,
            now=
                NOW,
        )

        require(
            missav[
                "known"
            ]
            is True,
            (
                "123AV selected before "
                "MissAV was known"
            ),
        )

        require(
            missav[
                "status"
            ]
            == STATUS_NOT_FOUND,
            (
                "123AV selected while "
                "MissAV was not NOT_FOUND"
            ),
        )

        require(
            missav[
                "due"
            ]
            is False,
            (
                "123AV selected while "
                "MissAV itself was due"
            ),
        )


def real_plan_smoke(
    db_path: Path,
):
    connection = connect_ro(
        db_path
    )

    try:
        universe = (
            batch.full_ui_universe(
                connection
            )
        )

        plan = (
            batch.build_due_request_plan(
                connection,
                now=NOW,
                max_requests=20,
            )
        )

        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        _assert_selected_fallbacks_valid(
            connection,
            plan,
        )

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
        (
            "theoretical availability "
            "check count changed"
        ),
    )

    require(
        (
            plan[
                "due_count"
            ]
            + plan[
                "fresh_count"
            ]
            + plan[
                "fallback_deferred_count"
            ]
        )
        == plan[
            "possible_checks"
        ],
        "plan accounting mismatch",
    )

    require(
        plan[
            "selected_count"
        ]
        == min(
            20,
            plan[
                "due_count"
            ],
        ),
        "batch ceiling changed",
    )

    require(
        plan[
            "remaining_after_batch"
        ]
        == (
            plan[
                "due_count"
            ]
            - plan[
                "selected_count"
            ]
        ),
        "remaining count mismatch",
    )

    require(
        integrity == "ok",
        "real DB integrity failed",
    )

    print(
        "AVAILABILITY_FULL_UI_117_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_PLAN_ACCOUNTING_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_123AV_FALLBACK_ONLY_REAL_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_ONE_SOURCE_PER_TITLE_REAL_SMOKE=PASS"
    )


def synthetic_priority_smoke():
    original_universe = (
        batch.full_ui_universe
    )

    original_cache = (
        batch.read_availability_cache
    )

    titles = (
        "AAA-001",
        "BBB-002",
        "CCC-003",
        "DDD-004",
        "EEE-005",
    )

    missav_states = {
        "AAA-001": {
            "known":
                False,
            "due":
                True,
            "status":
                STATUS_UNKNOWN,
            "fail_count":
                0,
            "next_check_at":
                None,
        },

        "BBB-002": {
            "known":
                True,
            "due":
                False,
            "status":
                STATUS_FOUND,
            "fail_count":
                0,
            "next_check_at":
                "future",
        },

        "CCC-003": {
            "known":
                True,
            "due":
                False,
            "status":
                STATUS_NOT_FOUND,
            "fail_count":
                0,
            "next_check_at":
                "future",
        },

        "DDD-004": {
            "known":
                True,
            "due":
                True,
            "status":
                STATUS_NOT_FOUND,
            "fail_count":
                0,
            "next_check_at":
                "past",
        },

        "EEE-005": {
            "known":
                True,
            "due":
                False,
            "status":
                STATUS_UNKNOWN,
            "fail_count":
                1,
            "next_check_at":
                "future",
        },
    }

    fallback_calls = []

    def fake_universe(
        connection,
    ):
        return {
            "latest_count":
                5,

            "weekly_period":
                "synthetic",

            "weekly_count":
                0,

            "monthly_full_count":
                0,

            "total":
                5,

            "dvd_ids":
                list(
                    titles
                ),
        }

    def fake_cache(
        connection,
        *,
        source,
        dvd_id,
        now,
    ):
        if source == SOURCE_MISSAV:
            value = dict(
                missav_states[
                    dvd_id
                ]
            )

        elif source == SOURCE_123AV:
            #
            # Only CCC-003 is allowed to
            # reach 123AV because its
            # MissAV result is known,
            # NOT_FOUND and still fresh.
            #
            if dvd_id != "CCC-003":
                raise RuntimeError(
                    (
                        "123AV was consulted "
                        "for ineligible title "
                        + dvd_id
                    )
                )

            fallback_calls.append(
                dvd_id
            )

            value = {
                "known":
                    False,

                "due":
                    True,

                "status":
                    STATUS_UNKNOWN,

                "fail_count":
                    0,

                "next_check_at":
                    None,
            }

        else:
            raise RuntimeError(
                "unexpected source"
            )

        value.update({
            "dvd_id":
                dvd_id,

            "source":
                source,
        })

        return value

    batch.full_ui_universe = (
        fake_universe
    )

    batch.read_availability_cache = (
        fake_cache
    )

    try:
        plan = (
            batch.build_due_request_plan(
                None,
                now=NOW,
                max_requests=20,
            )
        )

    finally:
        batch.full_ui_universe = (
            original_universe
        )

        batch.read_availability_cache = (
            original_cache
        )

    selected = [
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
        ]
    ]

    require(
        selected
        == [
            (
                "AAA-001",
                SOURCE_MISSAV,
            ),
            (
                "DDD-004",
                SOURCE_MISSAV,
            ),
            (
                "CCC-003",
                SOURCE_123AV,
            ),
        ],
        (
            "primary/fallback priority "
            "order mismatch: "
            + repr(
                selected
            )
        ),
    )

    require(
        fallback_calls
        == [
            "CCC-003",
        ],
        "unexpected 123AV consultation",
    )

    require(
        plan[
            "due_count"
        ]
        == 3,
        "synthetic due count mismatch",
    )

    require(
        plan[
            "fresh_count"
        ]
        == 3,
        "synthetic fresh count mismatch",
    )

    require(
        plan[
            "fallback_deferred_count"
        ]
        == 4,
        (
            "synthetic deferred "
            "count mismatch"
        ),
    )

    require(
        plan[
            "possible_checks"
        ]
        == 10,
        (
            "synthetic theoretical "
            "count mismatch"
        ),
    )

    require(
        (
            plan[
                "due_count"
            ]
            + plan[
                "fresh_count"
            ]
            + plan[
                "fallback_deferred_count"
            ]
        )
        == 10,
        "synthetic accounting mismatch",
    )

    print(
        "AVAILABILITY_UNKNOWN_BLOCKS_123AV_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_FOUND_BLOCKS_123AV_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_NOT_FOUND_UNLOCKS_123AV_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_DUE_NOT_FOUND_RECHECKS_MISSAV_FIRST_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_ALL_PRIMARY_BEFORE_FALLBACK_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_123AV_FALLBACK_ONLY_SMOKE=PASS"
    )


def limit_smoke():
    original_universe = (
        batch.full_ui_universe
    )

    original_cache = (
        batch.read_availability_cache
    )

    def fake_universe(
        connection,
    ):
        return {
            "total":
                2,

            "dvd_ids": [
                "AAA-001",
                "BBB-002",
            ],
        }

    def fake_cache(
        connection,
        *,
        source,
        dvd_id,
        now,
    ):
        if source != SOURCE_MISSAV:
            raise RuntimeError(
                "fallback must not be read"
            )

        return {
            "known":
                False,

            "due":
                True,

            "dvd_id":
                dvd_id,

            "source":
                source,

            "status":
                STATUS_UNKNOWN,

            "fail_count":
                0,

            "next_check_at":
                None,
        }

    batch.full_ui_universe = (
        fake_universe
    )

    batch.read_availability_cache = (
        fake_cache
    )

    try:
        one = (
            batch.build_due_request_plan(
                None,
                now=NOW,
                max_requests=1,
            )
        )

        require(
            one[
                "selected_count"
            ]
            == 1,
            "single request limit changed",
        )

        require(
            one[
                "selected"
            ][0][
                "source"
            ]
            == SOURCE_MISSAV,
            "single request did not prefer MissAV",
        )

        for invalid in (
            0,
            -1,
            201,
            True,
            "20",
        ):
            try:
                batch.build_due_request_plan(
                    None,
                    now=NOW,
                    max_requests=invalid,
                )

            except ValueError:
                pass

            else:
                raise RuntimeError(
                    (
                        "invalid max_requests "
                        "must fail closed"
                    )
                )

    finally:
        batch.full_ui_universe = (
            original_universe
        )

        batch.read_availability_cache = (
            original_cache
        )

    print(
        "AVAILABILITY_BATCH_LIMIT_FAIL_CLOSED_SMOKE=PASS"
    )


def main():
    synthetic_priority_smoke()
    limit_smoke()

    if len(
        sys.argv
    ) == 2:
        real_plan_smoke(
            Path(
                sys.argv[1]
            )
        )

    elif len(
        sys.argv
    ) != 1:
        raise RuntimeError(
            (
                "usage: "
                "teddy_discovery_availability_batch_smoke.py "
                "[stage-db]"
            )
        )

    print(
        "TEDDY_AVAILABILITY_BATCH_PLANNER_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
