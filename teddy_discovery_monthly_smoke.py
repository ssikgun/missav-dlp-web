from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import sys

from teddy_discovery_monthly import (
    MONTHLY_LABEL,
    _monthly_sort_key,
    derive_monthly_ranking,
)


EXPECTED_PERIODS = [
    "2026-W30",
    "2026-W31",
    "2026-W32",
    "2026-W33",
]

EXPECTED_TOP25 = [
    "JUR-786",
    "SNOS-334",
    "JUR-839",
    "OFJE-652",
    "ROE-558",
    "SNOS-299",
    "ROYD-340",
    "RCTD-757",
    "EBWH-350",
    "DSOD-060",
    "PRED-884",
    "SNOS-335",
    "MIDA-728",
    "DLDSS-515",
    "DSOD-001",
    "JUR-653",
    "IPZZ-986",
    "IPZZ-932",
    "RCTD-746",
    "DANDYA-043",
    "ORECS-617",
    "OFJE-655",
    "MIKR-117",
    "JUR-787",
    "EBWH-359",
]

EXPECTED_ORACLE_SHA = (
    "10a63a0ad158b2bdcb771293c9038a2e"
    "09f0dab61c5d70a66324bd9ea46b4de1"
)


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


def oracle_payload(
    result,
):
    return [
        {
            "rank":
                item[
                    "rank"
                ],

            "dvd_id":
                item[
                    "dvd_id"
                ],

            "score":
                item[
                    "score"
                ],

            "appearances":
                item[
                    "appearances"
                ],

            "weekly_ranks": {
                period:
                    item[
                        "weekly_ranks"
                    ][
                        period
                    ]

                for period
                in result[
                    "periods"
                ]
            },
        }

        for item
        in result[
            "items"
        ]
    ]


def digest_payload(
    value,
):
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode(
        "utf-8"
    )

    return hashlib.sha256(
        payload
    ).hexdigest()


def real_data_oracle_smoke(
    db_path: Path,
):
    connection = sqlite3.connect(
        "file:"
        + str(db_path)
        + "?mode=ro",
        uri=True,
    )

    connection.row_factory = (
        sqlite3.Row
    )

    try:
        result = (
            derive_monthly_ranking(
                connection,
                limit=25,
            )
        )

        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

    finally:
        connection.close()

    require(
        result[
            "label"
        ]
        == MONTHLY_LABEL,
        "monthly label changed",
    )

    require(
        result[
            "periods"
        ]
        == EXPECTED_PERIODS,
        "monthly period window changed",
    )

    require(
        result[
            "weekly_row_count"
        ]
        == 100,
        "monthly Weekly row count changed",
    )

    require(
        result[
            "total_unique_titles"
        ]
        == 68,
        "monthly unique title count changed",
    )

    require(
        result[
            "item_count"
        ]
        == 25,
        "monthly Top 25 count changed",
    )

    ids = [
        item[
            "dvd_id"
        ]
        for item
        in result[
            "items"
        ]
    ]

    require(
        ids == EXPECTED_TOP25,
        "monthly Top 25 order changed",
    )

    require(
        result[
            "items"
        ][0][
            "score"
        ]
        == 84,
        "monthly rank 1 score changed",
    )

    require(
        result[
            "items"
        ][1][
            "score"
        ]
        == 83,
        "monthly rank 2 score changed",
    )

    require(
        result[
            "items"
        ][5][
            "dvd_id"
        ]
        == "SNOS-299"
        and result[
            "items"
        ][5][
            "score"
        ]
        == 49,
        "monthly recent-title oracle changed",
    )

    digest = digest_payload(
        oracle_payload(
            result
        )
    )

    print(
        "MONTHLY_REAL_ORACLE_SHA256="
        + digest
    )

    require(
        digest
        == EXPECTED_ORACLE_SHA,
        "monthly real-data oracle "
        "hash changed",
    )

    require(
        integrity == "ok",
        "real DB integrity failed",
    )

    print(
        "MONTHLY_REAL_TOP25_ORDER_SMOKE=PASS"
    )

    print(
        "MONTHLY_REAL_DATA_ORACLE_SMOKE=PASS"
    )


def tie_break_smoke():
    latest_period = (
        "2026-W33"
    )

    common = {
        "weekly_ranks": {
            "2026-W30":
                None,

            "2026-W31":
                None,

            "2026-W32":
                None,

            "2026-W33":
                None,
        },
    }

    #
    # Same score:
    # current/latest week rank wins.
    #
    first = {
        **common,
        "dvd_id":
            "AAA-001",

        "score":
            50,

        "latest_appearance":
            "2026-W33",

        "weekly_ranks": {
            **common[
                "weekly_ranks"
            ],
            "2026-W33":
                2,
        },
    }

    second = {
        **common,
        "dvd_id":
            "BBB-001",

        "score":
            50,

        "latest_appearance":
            "2026-W33",

        "weekly_ranks": {
            **common[
                "weekly_ranks"
            ],
            "2026-W33":
                3,
        },
    }

    ordered = sorted(
        [
            second,
            first,
        ],
        key=lambda item:
            _monthly_sort_key(
                item,
                latest_period,
            ),
    )

    require(
        [
            item[
                "dvd_id"
            ]
            for item
            in ordered
        ]
        == [
            "AAA-001",
            "BBB-001",
        ],
        "latest-week rank "
        "tie-break changed",
    )

    #
    # Both absent from latest week:
    # latest appearance wins.
    #
    recent = {
        **common,
        "dvd_id":
            "CCC-001",

        "score":
            40,

        "latest_appearance":
            "2026-W32",
    }

    older = {
        **common,
        "dvd_id":
            "DDD-001",

        "score":
            40,

        "latest_appearance":
            "2026-W31",
    }

    ordered = sorted(
        [
            older,
            recent,
        ],
        key=lambda item:
            _monthly_sort_key(
                item,
                latest_period,
            ),
    )

    require(
        [
            item[
                "dvd_id"
            ]
            for item
            in ordered
        ]
        == [
            "CCC-001",
            "DDD-001",
        ],
        "latest-appearance "
        "tie-break changed",
    )

    #
    # Same score, both absent W33,
    # same latest appearance:
    # deterministic dvd_id fallback.
    #
    alpha = {
        **common,
        "dvd_id":
            "EEE-001",

        "score":
            30,

        "latest_appearance":
            "2026-W32",
    }

    beta = {
        **common,
        "dvd_id":
            "FFF-001",

        "score":
            30,

        "latest_appearance":
            "2026-W32",
    }

    ordered = sorted(
        [
            beta,
            alpha,
        ],
        key=lambda item:
            _monthly_sort_key(
                item,
                latest_period,
            ),
    )

    require(
        [
            item[
                "dvd_id"
            ]
            for item
            in ordered
        ]
        == [
            "EEE-001",
            "FFF-001",
        ],
        "dvd-id fallback "
        "tie-break changed",
    )

    print(
        "MONTHLY_LATEST_WEEK_TIEBREAK_SMOKE=PASS"
    )

    print(
        "MONTHLY_LATEST_APPEARANCE_TIEBREAK_SMOKE=PASS"
    )

    print(
        "MONTHLY_DVD_ID_TIEBREAK_SMOKE=PASS"
    )


def limit_smoke(
    db_path: Path,
):
    connection = sqlite3.connect(
        "file:"
        + str(db_path)
        + "?mode=ro",
        uri=True,
    )

    connection.row_factory = (
        sqlite3.Row
    )

    try:
        result = (
            derive_monthly_ranking(
                connection,
                limit=10,
            )
        )

    finally:
        connection.close()

    require(
        result[
            "item_count"
        ]
        == 10,
        "monthly limit changed",
    )

    require(
        [
            item[
                "dvd_id"
            ]
            for item
            in result[
                "items"
            ]
        ]
        == EXPECTED_TOP25[
            :10
        ],
        "monthly Top 10 changed",
    )

    print(
        "MONTHLY_LIMIT_SMOKE=PASS"
    )


def main():
    if len(
        sys.argv
    ) != 2:
        raise RuntimeError(
            "usage: "
            "teddy_discovery_monthly_smoke.py "
            "<stage3-db>"
        )

    db_path = Path(
        sys.argv[1]
    )

    real_data_oracle_smoke(
        db_path
    )

    tie_break_smoke()

    limit_smoke(
        db_path
    )

    print(
        "TEDDY_MONTHLY_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
