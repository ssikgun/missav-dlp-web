from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import sys

from teddy_discovery_category import (
    derive_category_ranking,
    list_category_facets,
)

from teddy_discovery_monthly import (
    derive_monthly_ranking,
)


EXPECTED_FACETS_TOP5 = [
    (
        "Hi-Def",
        64,
    ),
    (
        "Exclusive Distribution",
        48,
    ),
    (
        "Featured Actress",
        47,
    ),
    (
        "Big Tits",
        41,
    ),
    (
        "4K",
        38,
    ),
]


EXPECTED_BIG_TITS_TOP10 = [
    (
        "JUR-786",
        1,
        84,
    ),
    (
        "SNOS-334",
        2,
        83,
    ),
    (
        "JUR-839",
        3,
        64,
    ),
    (
        "OFJE-652",
        4,
        61,
    ),
    (
        "ROE-558",
        5,
        53,
    ),
    (
        "SNOS-299",
        6,
        49,
    ),
    (
        "ROYD-340",
        7,
        49,
    ),
    (
        "EBWH-350",
        9,
        45,
    ),
    (
        "DSOD-060",
        10,
        41,
    ),
    (
        "PRED-884",
        11,
        40,
    ),
]


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


def ro_connect(
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


def real_facets_smoke(
    db_path: Path,
):
    connection = ro_connect(
        db_path
    )

    try:
        facets = list_category_facets(
            connection
        )

        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

    finally:
        connection.close()

    require(
        facets[
            "monthly_unique_titles"
        ]
        == 68,
        "category Monthly universe changed",
    )

    require(
        facets[
            "covered_titles"
        ]
        == 68,
        "category coverage changed",
    )

    require(
        facets[
            "uncovered_titles"
        ]
        == 0,
        "category uncovered titles changed",
    )

    require(
        facets[
            "uncovered_dvd_ids"
        ]
        == [],
        "category uncovered IDs changed",
    )

    require(
        facets[
            "category_count"
        ]
        == 96,
        "category count changed",
    )

    top5 = [
        (
            item[
                "name"
            ],
            item[
                "title_count"
            ],
        )
        for item
        in facets[
            "categories"
        ][
            :5
        ]
    ]

    require(
        top5
        == EXPECTED_FACETS_TOP5,
        "category facet Top 5 changed",
    )

    require(
        integrity == "ok",
        "real DB integrity failed",
    )

    print(
        "CATEGORY_REAL_COVERAGE_SMOKE=PASS"
    )

    print(
        "CATEGORY_REAL_FACETS_SMOKE=PASS"
    )


def big_tits_oracle_smoke(
    db_path: Path,
):
    connection = ro_connect(
        db_path
    )

    try:
        result = derive_category_ranking(
            connection,
            "Big Tits",
            limit=10,
        )

    finally:
        connection.close()

    require(
        result[
            "category"
        ]
        == "Big Tits",
        "category canonical name changed",
    )

    require(
        result[
            "total_category_titles"
        ]
        == 41,
        "Big Tits title count changed",
    )

    require(
        result[
            "item_count"
        ]
        == 10,
        "Big Tits Top 10 count changed",
    )

    observed = [
        (
            item[
                "dvd_id"
            ],
            item[
                "monthly_rank"
            ],
            item[
                "score"
            ],
        )
        for item
        in result[
            "items"
        ]
    ]

    require(
        observed
        == EXPECTED_BIG_TITS_TOP10,
        "Big Tits real ranking "
        "oracle changed",
    )

    require(
        [
            item[
                "category_rank"
            ]
            for item
            in result[
                "items"
            ]
        ]
        == list(
            range(
                1,
                11,
            )
        ),
        "category rank sequence changed",
    )

    require(
        [
            item[
                "rank"
            ]
            for item
            in result[
                "items"
            ]
        ]
        == list(
            range(
                1,
                11,
            )
        ),
        "generic rank sequence changed",
    )

    payload = [
        {
            "category_rank":
                item[
                    "category_rank"
                ],

            "monthly_rank":
                item[
                    "monthly_rank"
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
        }
        for item
        in result[
            "items"
        ]
    ]

    digest = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode(
            "utf-8"
        )
    ).hexdigest()

    print(
        "CATEGORY_BIG_TITS_TOP10_SHA256="
        + digest
    )

    print(
        "CATEGORY_BIG_TITS_REAL_ORACLE_SMOKE=PASS"
    )


def monthly_order_preservation_smoke(
    db_path: Path,
):
    connection = ro_connect(
        db_path
    )

    try:
        monthly = derive_monthly_ranking(
            connection,
            limit=500,
        )

        facets = list_category_facets(
            connection
        )

        monthly_positions = {
            item[
                "dvd_id"
            ]:
                item[
                    "rank"
                ]
            for item
            in monthly[
                "items"
            ]
        }

        for facet in facets[
            "categories"
        ]:
            result = derive_category_ranking(
                connection,
                facet[
                    "name"
                ],
                limit=500,
            )

            positions = [
                item[
                    "monthly_rank"
                ]
                for item
                in result[
                    "items"
                ]
            ]

            require(
                positions
                == sorted(
                    positions
                ),
                (
                    "category changed "
                    "Monthly ordering: "
                    + facet[
                        "name"
                    ]
                ),
            )

            for item in result[
                "items"
            ]:
                require(
                    monthly_positions[
                        item[
                            "dvd_id"
                        ]
                    ]
                    == item[
                        "monthly_rank"
                    ],
                    (
                        "category Monthly rank "
                        "provenance changed: "
                        + item[
                            "dvd_id"
                        ]
                    ),
                )

    finally:
        connection.close()

    print(
        "CATEGORY_REUSES_MONTHLY_SCORE_SMOKE=PASS"
    )

    print(
        "CATEGORY_PRESERVES_MONTHLY_ORDER_SMOKE=PASS"
    )


def lookup_and_limit_smoke(
    db_path: Path,
):
    connection = ro_connect(
        db_path
    )

    try:
        folded = derive_category_ranking(
            connection,
            "big tits",
            limit=5,
        )

        require(
            folded[
                "category"
            ]
            == "Big Tits",
            "case-insensitive category "
            "resolution changed",
        )

        require(
            folded[
                "item_count"
            ]
            == 5,
            "category limit changed",
        )

        try:
            derive_category_ranking(
                connection,
                "Definitely Not A Real Genre",
            )

        except ValueError:
            pass

        else:
            raise RuntimeError(
                "unknown category must "
                "fail closed"
            )

        for invalid in (
            0,
            -1,
            501,
            True,
            "25",
        ):
            try:
                derive_category_ranking(
                    connection,
                    "Big Tits",
                    limit=invalid,
                )

            except ValueError:
                pass

            else:
                raise RuntimeError(
                    "invalid category limit "
                    "must fail closed"
                )

    finally:
        connection.close()

    print(
        "CATEGORY_CASEFOLD_LOOKUP_SMOKE=PASS"
    )

    print(
        "CATEGORY_LIMIT_SMOKE=PASS"
    )

    print(
        "CATEGORY_UNKNOWN_FAIL_CLOSED_SMOKE=PASS"
    )


def main():
    if len(
        sys.argv
    ) != 2:
        raise RuntimeError(
            "usage: "
            "teddy_discovery_category_smoke.py "
            "<stage3-db>"
        )

    db_path = Path(
        sys.argv[1]
    )

    real_facets_smoke(
        db_path
    )

    big_tits_oracle_smoke(
        db_path
    )

    monthly_order_preservation_smoke(
        db_path
    )

    lookup_and_limit_smoke(
        db_path
    )

    print(
        "TEDDY_CATEGORY_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
