from __future__ import annotations

import teddy_discovery_availability_batch as batch

from teddy_discovery_availability import (
    SOURCE_MISSAV,
    STATUS_FOUND,
    STATUS_NOT_FOUND,
    STATUS_UNKNOWN,
)


NOW = "2026-08-29T03:30:00+00:00"


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


def main():
    original_universe = (
        batch.full_ui_universe
    )

    original_cache = (
        batch.read_availability_cache
    )

    titles = [
        "OLD-FND",
        "FAR-001",
        "NEAR-001",
        "OLD-NEG",
        "RECENT-1",
        "TODAY-01",
        "UNDATED",
    ]

    release_dates = {
        "OLD-FND":
            "2026-07-01",

        "FAR-001":
            "2026-10-08",

        "NEAR-001":
            "2026-08-30",

        "OLD-NEG":
            "2026-08-01",

        "RECENT-1":
            "2026-08-28",

        "TODAY-01":
            "2026-08-29",

        "UNDATED":
            None,
    }

    statuses = {
        "OLD-FND":
            STATUS_FOUND,

        "NEAR-001":
            STATUS_UNKNOWN,

        "OLD-NEG":
            STATUS_NOT_FOUND,

        "RECENT-1":
            STATUS_UNKNOWN,

        "TODAY-01":
            STATUS_UNKNOWN,

        "UNDATED":
            STATUS_UNKNOWN,
    }

    cache_calls = []

    def fake_universe(
        connection,
    ):
        return {
            "total":
                len(
                    titles
                ),

            "dvd_ids":
                list(
                    titles
                ),

            "release_dates":
                dict(
                    release_dates
                ),
        }

    def fake_cache(
        connection,
        *,
        source,
        dvd_id,
        now,
    ):
        require(
            source == SOURCE_MISSAV,
            "123AV must not be "
            "consulted while MissAV "
            "is due",
        )

        require(
            dvd_id != "FAR-001",
            "far-future title reached "
            "availability cache",
        )

        cache_calls.append(
            dvd_id
        )

        status = statuses[
            dvd_id
        ]

        return {
            "known":
                status
                != STATUS_UNKNOWN,

            "due":
                True,

            "dvd_id":
                dvd_id,

            "source":
                source,

            "status":
                status,

            "fail_count":
                (
                    1
                    if status
                    == STATUS_UNKNOWN
                    else 0
                ),

            "next_check_at":
                "2026-08-29T00:00:00+00:00",
        }

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
        item[
            "dvd_id"
        ]
        for item
        in plan[
            "selected"
        ]
    ]

    require(
        selected
        == [
            "TODAY-01",
            "RECENT-1",
            "NEAR-001",
            "OLD-NEG",
            "UNDATED",
            "OLD-FND",
        ],
        (
            "R2 priority order mismatch: "
            + repr(
                selected
            )
        ),
    )

    require(
        [
            item[
                "priority_name"
            ]
            for item
            in plan[
                "selected"
            ]
        ]
        == [
            "today",
            "recent7",
            "near-future",
            "older-or-undated",
            "older-or-undated",
            "older-or-undated",
        ],
        "priority labels mismatch",
    )

    require(
        "FAR-001"
        not in cache_calls,
        "far-future title consumed "
        "availability work",
    )

    require(
        plan[
            "far_future_deferred_count"
        ] == 1,
        "far-future accounting mismatch",
    )

    require(
        plan[
            "eligible_title_count"
        ] == 6,
        "eligible title count mismatch",
    )

    require(
        plan[
            "possible_checks"
        ] == 12,
        "eligible source accounting mismatch",
    )

    require(
        plan[
            "due_count"
        ] == 6,
        "due count mismatch",
    )

    require(
        plan[
            "fallback_deferred_count"
        ] == 6,
        "fallback accounting mismatch",
    )

    require(
        all(
            item[
                "source"
            ] == SOURCE_MISSAV
            for item
            in plan[
                "selected"
            ]
        ),
        "R2 priority changed "
        "MissAV primary boundary",
    )

    print(
        "AVAILABILITY_R2_TODAY_PRIORITY_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_R2_RECENT7_PRIORITY_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_R2_NEAR_FUTURE_PRIORITY_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_R2_OLDER_NEGATIVE_PRIORITY_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_R2_OLDER_FOUND_DEPRIORITIZED_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_R2_FAR_FUTURE_DEFERRED_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_R2_MISSAV_PRIMARY_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_R2_PRIORITY_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
