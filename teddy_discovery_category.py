from __future__ import annotations

from collections import defaultdict
import sqlite3
from typing import Any

from teddy_discovery_monthly import (
    MONTHLY_FORMULA,
    MONTHLY_TIEBREAK,
    MONTHLY_WINDOW_WEEKS,
    derive_monthly_ranking,
)


CATEGORY_DEFAULT_LIMIT = 25
CATEGORY_MAX_LIMIT = 500


def _text(
    value: Any,
) -> str | None:
    if value is None:
        return None

    value = " ".join(
        str(value).split()
    )

    return value or None


def _validated_limit(
    value: Any,
) -> int:
    if (
        type(value) is not int
        or value < 1
        or value > CATEGORY_MAX_LIMIT
    ):
        raise ValueError(
            "category limit must be 1..500"
        )

    return value


def _monthly_genre_map(
    connection: sqlite3.Connection,
    monthly_items: list[dict],
) -> tuple[
    dict[str, set[str]],
    dict[str, set[str]],
]:
    dvd_ids = [
        item[
            "dvd_id"
        ]
        for item
        in monthly_items
    ]

    if not dvd_ids:
        return (
            {},
            {},
        )

    placeholders = ",".join(
        "?"
        for _ in dvd_ids
    )

    rows = connection.execute(
        f"""
        SELECT
            tg.dvd_id,
            g.name
        FROM title_genres AS tg
        JOIN genres AS g
          ON g.genre_id =
             tg.genre_id
        WHERE tg.dvd_id IN (
            {placeholders}
        )
        ORDER BY
            tg.dvd_id,
            g.name
        """,
        dvd_ids,
    ).fetchall()

    genres_by_id = defaultdict(
        set
    )

    ids_by_genre = defaultdict(
        set
    )

    normalized_names = {}

    for row in rows:
        dvd_id = _text(
            row[
                "dvd_id"
            ]
        )

        genre = _text(
            row[
                "name"
            ]
        )

        if not dvd_id:
            raise RuntimeError(
                "category genre link "
                "DVD ID missing"
            )

        if not genre:
            raise RuntimeError(
                "category genre name missing"
            )

        normalized = (
            genre.casefold()
        )

        previous = (
            normalized_names.get(
                normalized
            )
        )

        if (
            previous is not None
            and previous != genre
        ):
            raise RuntimeError(
                "ambiguous normalized "
                "genre names: "
                + repr(
                    previous
                )
                + " / "
                + repr(
                    genre
                )
            )

        normalized_names[
            normalized
        ] = genre

        genres_by_id[
            dvd_id
        ].add(
            genre
        )

        ids_by_genre[
            genre
        ].add(
            dvd_id
        )

    return (
        dict(
            genres_by_id
        ),
        dict(
            ids_by_genre
        ),
    )


def list_category_facets(
    connection: sqlite3.Connection,
) -> dict:
    monthly = derive_monthly_ranking(
        connection,
        limit=CATEGORY_MAX_LIMIT,
    )

    items = monthly[
        "items"
    ]

    (
        genres_by_id,
        ids_by_genre,
    ) = _monthly_genre_map(
        connection,
        items,
    )

    monthly_positions = {
        item[
            "dvd_id"
        ]:
            int(
                item[
                    "rank"
                ]
            )
        for item
        in items
    }

    categories = []

    for genre, dvd_ids in (
        ids_by_genre.items()
    ):
        ordered_ids = sorted(
            dvd_ids,
            key=lambda dvd_id:
                monthly_positions[
                    dvd_id
                ],
        )

        categories.append({
            "name":
                genre,

            "title_count":
                len(
                    ordered_ids
                ),

            "top_dvd_id":
                ordered_ids[0],

            "top_monthly_rank":
                monthly_positions[
                    ordered_ids[0]
                ],
        })

    categories.sort(
        key=lambda value: (
            -value[
                "title_count"
            ],
            value[
                "name"
            ].casefold(),
            value[
                "name"
            ],
        )
    )

    covered = {
        dvd_id
        for dvd_id, genres
        in genres_by_id.items()
        if genres
    }

    all_ids = {
        item[
            "dvd_id"
        ]
        for item
        in items
    }

    uncovered = sorted(
        all_ids - covered
    )

    return {
        "source":
            "teddy-category-facets",

        "basis_source":
            monthly[
                "source"
            ],

        "periods":
            list(
                monthly[
                    "periods"
                ]
            ),

        "window_weeks":
            MONTHLY_WINDOW_WEEKS,

        "monthly_unique_titles":
            monthly[
                "total_unique_titles"
            ],

        "covered_titles":
            len(
                covered
            ),

        "uncovered_titles":
            len(
                uncovered
            ),

        "uncovered_dvd_ids":
            uncovered,

        "category_count":
            len(
                categories
            ),

        "categories":
            categories,
    }


def _resolve_category(
    facets: dict,
    value: Any,
) -> str:
    requested = _text(
        value
    )

    if not requested:
        raise ValueError(
            "category name missing"
        )

    exact = [
        item[
            "name"
        ]
        for item
        in facets[
            "categories"
        ]
        if item[
            "name"
        ] == requested
    ]

    if len(exact) == 1:
        return exact[0]

    folded = [
        item[
            "name"
        ]
        for item
        in facets[
            "categories"
        ]
        if item[
            "name"
        ].casefold()
        == requested.casefold()
    ]

    if len(folded) == 1:
        return folded[0]

    if len(folded) > 1:
        raise RuntimeError(
            "category name is ambiguous"
        )

    raise ValueError(
        "unknown category: "
        + requested
    )


def derive_category_ranking(
    connection: sqlite3.Connection,
    category: str,
    *,
    limit: int = CATEGORY_DEFAULT_LIMIT,
) -> dict:
    limit = _validated_limit(
        limit
    )

    monthly = derive_monthly_ranking(
        connection,
        limit=CATEGORY_MAX_LIMIT,
    )

    facets = list_category_facets(
        connection
    )

    canonical_category = (
        _resolve_category(
            facets,
            category,
        )
    )

    (
        genres_by_id,
        ids_by_genre,
    ) = _monthly_genre_map(
        connection,
        monthly[
            "items"
        ],
    )

    allowed = ids_by_genre.get(
        canonical_category,
        set(),
    )

    filtered = [
        item
        for item
        in monthly[
            "items"
        ]
        if item[
            "dvd_id"
        ]
        in allowed
    ]

    selected = []

    for category_rank, item in enumerate(
        filtered[
            :limit
        ],
        start=1,
    ):
        value = dict(
            item
        )

        value[
            "weekly_ranks"
        ] = dict(
            item[
                "weekly_ranks"
            ]
        )

        value[
            "monthly_rank"
        ] = int(
            item[
                "rank"
            ]
        )

        value[
            "category_rank"
        ] = category_rank

        #
        # Generic ranking consumers can
        # display `rank`, while the global
        # Monthly rank remains explicit.
        #
        value[
            "rank"
        ] = category_rank

        value[
            "category"
        ] = (
            canonical_category
        )

        value[
            "genres"
        ] = sorted(
            genres_by_id.get(
                item[
                    "dvd_id"
                ],
                set(),
            ),
            key=lambda name:
                (
                    name.casefold(),
                    name,
                ),
        )

        selected.append(
            value
        )

    return {
        "source":
            "teddy-category",

        "basis_source":
            monthly[
                "source"
            ],

        "basis_chart_type":
            monthly[
                "basis_chart_type"
            ],

        "category":
            canonical_category,

        "label":
            (
                "Teddy 장르 랭킹 · "
                + canonical_category
            ),

        #
        # Category introduces no new
        # score. It filters the full
        # Teddy Monthly ranking.
        #
        "formula":
            MONTHLY_FORMULA,

        "tie_break":
            MONTHLY_TIEBREAK,

        "periods":
            list(
                monthly[
                    "periods"
                ]
            ),

        "latest_period":
            monthly[
                "latest_period"
            ],

        "window_weeks":
            MONTHLY_WINDOW_WEEKS,

        "monthly_unique_titles":
            monthly[
                "total_unique_titles"
            ],

        "total_category_titles":
            len(
                filtered
            ),

        "item_count":
            len(
                selected
            ),

        "items":
            selected,
    }
