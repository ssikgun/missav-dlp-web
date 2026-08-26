from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import sys

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
    list_weekly_snapshot,
)

from teddy_discovery_ui_data import (
    build_category_facets_view,
    build_category_view,
    build_latest_view,
    build_monthly_view,
    build_weekly_view,
)


EXPECTED_WEEKLY_PERIOD = (
    "2026-W33"
)

EXPECTED_MONTHLY_PERIODS = [
    "2026-W30",
    "2026-W31",
    "2026-W32",
    "2026-W33",
]

TEST_CATEGORY = (
    "Big Tits"
)


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


def file_sha256(
    path: Path,
) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


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


def copy_db(
    source_path: Path,
    target_path: Path,
):
    source = sqlite3.connect(
        "file:"
        + str(source_path)
        + "?mode=ro",
        uri=True,
    )

    target = sqlite3.connect(
        target_path
    )

    try:
        source.backup(
            target
        )

    finally:
        target.close()
        source.close()


def assert_browser_safe(
    value,
):
    forbidden = {
        "cover_url",
        "source_url",
        "page_url",
        "raw_metadata",
        "relative_path",
        "storage_root",
    }

    if isinstance(
        value,
        dict,
    ):
        bad = (
            forbidden
            & set(
                value
            )
        )

        require(
            not bad,
            "browser-facing model "
            "contains upstream/path key: "
            + repr(
                sorted(
                    bad
                )
            ),
        )

        for child in (
            value.values()
        ):
            assert_browser_safe(
                child
            )

    elif isinstance(
        value,
        list,
    ):
        for child in value:
            assert_browser_safe(
                child
            )


def assert_common_items(
    view,
):
    items = view[
        "items"
    ]

    require(
        view[
            "item_count"
        ] == len(
            items
        ),
        "UI item_count mismatch",
    )

    require(
        [
            item[
                "rank"
            ]
            for item
            in items
        ]
        == list(
            range(
                1,
                len(
                    items
                )
                + 1,
            )
        ),
        "UI ranks not contiguous",
    )

    for item in items:
        required = {
            "rank",
            "dvd_id",
            "title",
            "release_date",
            "maker",
            "metadata_source",
            "people",
            "genres",
            "owned",
            "holding_count",
            "availability",
            "availability_complete",
            "available_sources",
            "ranking",
        }

        require(
            required.issubset(
                item
            ),
            "UI common row contract "
            "missing fields",
        )

        require(
            isinstance(
                item[
                    "dvd_id"
                ],
                str,
            )
            and bool(
                item[
                    "dvd_id"
                ]
            ),
            "UI DVD ID invalid",
        )

        require(
            isinstance(
                item[
                    "people"
                ],
                list,
            ),
            "UI people invalid",
        )

        require(
            isinstance(
                item[
                    "genres"
                ],
                list,
            ),
            "UI genres invalid",
        )

        require(
            type(
                item[
                    "holding_count"
                ]
            ) is int
            and item[
                "holding_count"
            ] >= 0,
            "UI holding count invalid",
        )

        require(
            item[
                "owned"
            ]
            is (
                item[
                    "holding_count"
                ]
                > 0
            ),
            "UI owned state mismatch",
        )

        availability = item[
            "availability"
        ]

        require(
            tuple(
                availability
            )
            == tuple(
                AVAILABILITY_SOURCES
            ),
            "UI availability source "
            "order changed",
        )

        expected_found = []

        for source in (
            AVAILABILITY_SOURCES
        ):
            state = availability[
                source
            ]

            require(
                state[
                    "status"
                ]
                in AVAILABILITY_STATUSES,
                "UI availability status "
                "invalid",
            )

            require(
                type(
                    state[
                        "known"
                    ]
                ) is bool,
                "UI availability known "
                "flag invalid",
            )

            require(
                type(
                    state[
                        "fail_count"
                    ]
                ) is int
                and state[
                    "fail_count"
                ] >= 0,
                "UI availability "
                "fail_count invalid",
            )

            if not state[
                "known"
            ]:
                require(
                    state[
                        "status"
                    ]
                    == STATUS_UNKNOWN,
                    "cache miss must "
                    "present as UNKNOWN",
                )

                require(
                    state[
                        "last_checked_at"
                    ]
                    is None,
                    "cache miss has "
                    "checked timestamp",
                )

                require(
                    state[
                        "next_check_at"
                    ]
                    is None,
                    "cache miss has "
                    "next-check timestamp",
                )

                require(
                    state[
                        "fail_count"
                    ]
                    == 0,
                    "cache miss fail_count "
                    "must be zero",
                )

            if (
                state[
                    "status"
                ]
                == STATUS_FOUND
            ):
                expected_found.append(
                    source
                )

        require(
            item[
                "available_sources"
            ]
            == expected_found,
            "UI available source "
            "derivation changed",
        )

        require(
            item[
                "availability_complete"
            ]
            is all(
                availability[
                    source
                ][
                    "known"
                ]
                for source
                in AVAILABILITY_SOURCES
            ),
            "UI availability_complete "
            "changed",
        )

    assert_browser_safe(
        view
    )


def real_model_smoke(
    db_path: Path,
):
    connection = connect_ro(
        db_path
    )

    try:
        latest = build_latest_view(
            connection,
            limit=50,
        )

        weekly = build_weekly_view(
            connection,
        )

        monthly = build_monthly_view(
            connection,
            limit=25,
        )

        monthly_full = (
            build_monthly_view(
                connection,
                limit=500,
            )
        )

        facets = (
            build_category_facets_view(
                connection
            )
        )

        category = (
            build_category_view(
                connection,
                TEST_CATEGORY,
                limit=500,
            )
        )

        direct_latest = (
            list_latest_items(
                connection,
                limit=50,
            )
        )

        direct_weekly = [
            dict(row)
            for row
            in list_weekly_snapshot(
                connection,
                EXPECTED_WEEKLY_PERIOD,
            )
        ]

        direct_monthly = (
            derive_monthly_ranking(
                connection,
                limit=25,
            )
        )

        direct_monthly_full = (
            derive_monthly_ranking(
                connection,
                limit=500,
            )
        )

        direct_facets = (
            list_category_facets(
                connection
            )
        )

        direct_category = (
            derive_category_ranking(
                connection,
                TEST_CATEGORY,
                limit=500,
            )
        )

        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

    finally:
        connection.close()

    require(
        integrity == "ok",
        "real DB integrity failed",
    )

    require(
        latest[
            "item_count"
        ] == 50,
        "Latest UI count changed",
    )

    require(
        [
            item["dvd_id"]
            for item
            in latest["items"]
        ]
        == [
            item["dvd_id"]
            for item
            in direct_latest
        ],
        "Latest canonical order changed",
    )

    require(
        weekly[
            "period"
        ] == EXPECTED_WEEKLY_PERIOD,
        "Weekly latest period changed",
    )

    require(
        weekly[
            "item_count"
        ] == 25,
        "Weekly UI count changed",
    )

    require(
        [
            item["dvd_id"]
            for item
            in weekly["items"]
        ]
        == [
            item["dvd_id"]
            for item
            in direct_weekly
        ],
        "Weekly canonical order changed",
    )

    require(
        monthly[
            "periods"
        ] == EXPECTED_MONTHLY_PERIODS,
        "Monthly periods changed",
    )

    require(
        monthly[
            "item_count"
        ] == 25,
        "Monthly top-25 count changed",
    )

    require(
        monthly[
            "total_unique_titles"
        ] == 68,
        "Monthly unique-title "
        "count changed",
    )

    require(
        [
            item["dvd_id"]
            for item
            in monthly["items"]
        ]
        == [
            item["dvd_id"]
            for item
            in direct_monthly[
                "items"
            ]
        ],
        "Monthly canonical order changed",
    )

    require(
        monthly_full[
            "item_count"
        ] == 68,
        "Full Monthly count changed",
    )

    require(
        [
            item["dvd_id"]
            for item
            in monthly_full[
                "items"
            ]
        ]
        == [
            item["dvd_id"]
            for item
            in direct_monthly_full[
                "items"
            ]
        ],
        "Full Monthly order changed",
    )

    require(
        facets[
            "category_count"
        ] == 96,
        "Category facet count changed",
    )

    require(
        facets[
            "covered_titles"
        ] == 68,
        "Category covered-title "
        "count changed",
    )

    require(
        facets[
            "uncovered_titles"
        ] == 0,
        "Category uncovered-title "
        "count changed",
    )

    require(
        facets[
            "categories"
        ]
        == direct_facets[
            "categories"
        ],
        "Category facets changed",
    )

    require(
        category[
            "category"
        ] == TEST_CATEGORY,
        "Category canonical name changed",
    )

    require(
        category[
            "item_count"
        ] > 0,
        "Big Tits category empty",
    )

    require(
        [
            item["dvd_id"]
            for item
            in category["items"]
        ]
        == [
            item["dvd_id"]
            for item
            in direct_category[
                "items"
            ]
        ],
        "Category canonical order changed",
    )

    require(
        [
            item[
                "ranking"
            ][
                "monthly_rank"
            ]
            for item
            in category[
                "items"
            ]
        ]
        == sorted(
            item[
                "ranking"
            ][
                "monthly_rank"
            ]
            for item
            in category[
                "items"
            ]
        ),
        "Category Monthly-order "
        "preservation changed",
    )

    require(
        all(
            TEST_CATEGORY
            in item[
                "genres"
            ]
            for item
            in category[
                "items"
            ]
        ),
        "Category genre enrichment "
        "changed",
    )

    for view in (
        latest,
        weekly,
        monthly,
        monthly_full,
        category,
    ):
        assert_common_items(
            view
        )

    assert_browser_safe(
        facets
    )

    known_count = 0
    missing_count = 0

    for view in (
        latest,
        weekly,
        monthly_full,
    ):
        for item in view[
            "items"
        ]:
            for source in (
                AVAILABILITY_SOURCES
            ):
                if item[
                    "availability"
                ][
                    source
                ][
                    "known"
                ]:
                    known_count += 1

                else:
                    missing_count += 1

    require(
        known_count > 0,
        "UI data has no known "
        "availability sample",
    )

    require(
        missing_count > 0,
        "UI data has no cache-miss "
        "availability sample",
    )

    oracle_payload = {
        "latest":
            latest,

        "weekly":
            weekly,

        "monthly":
            monthly,

        "facets":
            facets,

        "category":
            category,
    }

    canonical = json.dumps(
        oracle_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
    ).encode(
        "utf-8"
    )

    oracle = hashlib.sha256(
        canonical
    ).hexdigest()

    print(
        "UI_DATA_KNOWN_AVAILABILITY_STATES="
        + str(
            known_count
        )
    )

    print(
        "UI_DATA_MISSING_AVAILABILITY_STATES="
        + str(
            missing_count
        )
    )

    print(
        "UI_DATA_ORACLE_SHA256="
        + oracle
    )

    print(
        "UI_DATA_LATEST_CANONICAL_ORDER_SMOKE=PASS"
    )

    print(
        "UI_DATA_WEEKLY_CANONICAL_ORDER_SMOKE=PASS"
    )

    print(
        "UI_DATA_MONTHLY_CANONICAL_ORDER_SMOKE=PASS"
    )

    print(
        "UI_DATA_CATEGORY_CANONICAL_ORDER_SMOKE=PASS"
    )

    print(
        "UI_DATA_ENRICHMENT_SMOKE=PASS"
    )

    print(
        "UI_DATA_AVAILABILITY_CACHE_MISS_SMOKE=PASS"
    )

    print(
        "UI_DATA_BROWSER_SAFE_NO_UPSTREAM_URL_SMOKE=PASS"
    )

    return oracle


def temporary_ownership_smoke(
    real_db: Path,
):
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-ui-data-owned-"
    ) as temp:
        root = Path(
            temp
        )

        temp_db = (
            root
            / "teddy-discovery.sqlite3"
        )

        copy_db(
            real_db,
            temp_db,
        )

        connection = sqlite3.connect(
            temp_db
        )

        connection.row_factory = (
            sqlite3.Row
        )

        try:
            latest = (
                list_latest_items(
                    connection,
                    limit=50,
                )
            )

            candidate = None

            for item in latest:
                count = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM holdings
                    WHERE dvd_id = ?
                      AND parse_status = 'MATCHED'
                      AND present = 1
                    """,
                    (
                        item[
                            "dvd_id"
                        ],
                    ),
                ).fetchone()[0]

                if count == 0:
                    candidate = item[
                        "dvd_id"
                    ]
                    break

            require(
                candidate is not None,
                "ownership smoke has "
                "no unowned Latest title",
            )

            connection.execute(
                """
                INSERT INTO holdings(
                    storage_root,
                    relative_path,
                    dvd_id,
                    parse_status,
                    parse_method,
                    parse_candidates_json,
                    size_bytes,
                    mtime_ns,
                    discovered_by,
                    present,
                    first_seen_at,
                    last_seen_at,
                    last_seen_run_id
                )
                VALUES(
                    'stage5-ui-smoke',
                    ?,
                    ?,
                    'MATCHED',
                    'stage5-ui-smoke',
                    '[]',
                    1,
                    1,
                    'stage5-ui-smoke',
                    1,
                    '2026-08-26T14:00:00+00:00',
                    '2026-08-26T14:00:00+00:00',
                    NULL
                )
                """,
                (
                    candidate
                    + ".mp4",
                    candidate,
                ),
            )

            connection.commit()

            view = build_latest_view(
                connection,
                limit=50,
            )

            row = next(
                item
                for item
                in view[
                    "items"
                ]
                if item[
                    "dvd_id"
                ] == candidate
            )

            require(
                row[
                    "owned"
                ] is True,
                "synthetic owned state "
                "not reflected",
            )

            require(
                row[
                    "holding_count"
                ] == 1,
                "synthetic holding count "
                "not reflected",
            )

            integrity = (
                connection.execute(
                    "PRAGMA integrity_check"
                ).fetchone()[0]
            )

        finally:
            connection.close()

        require(
            integrity == "ok",
            "temp ownership DB "
            "integrity failed",
        )

    print(
        "UI_DATA_OWNERSHIP_TEMP_DB_SMOKE=PASS"
    )


def main():
    if len(
        sys.argv
    ) != 2:
        raise RuntimeError(
            "usage: "
            "teddy_discovery_ui_data_smoke.py "
            "<stage5-db>"
        )

    real_db = Path(
        sys.argv[1]
    )

    before = file_sha256(
        real_db
    )

    real_model_smoke(
        real_db
    )

    temporary_ownership_smoke(
        real_db
    )

    after = file_sha256(
        real_db
    )

    require(
        after == before,
        "UI data smoke changed "
        "real Stage 5 DB bytes",
    )

    print(
        "UI_DATA_REAL_DB_BYTE_UNCHANGED_SMOKE=PASS"
    )

    print(
        "TEDDY_DISCOVERY_UI_DATA_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
