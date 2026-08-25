from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

from teddy_discovery_javdatabase import (
    JAVDATABASE_WEEKLY_SOURCE,
    parse_javdatabase_weekly_envelope,
    parse_javdatabase_weekly_html,
)


EXPECTED_IDS = [
    "JUR-786",
    "SNOS-299",
    "DSOD-060",
    "IPZZ-986",
    "RCTD-757",
    "OFJE-652",
    "ORECS-617",
    "PRED-884",
    "JUR-839",
    "IPZZ-960",
    "EBWH-365",
    "SNOS-334",
    "ROE-558",
    "SNOS-335",
    "START-624",
    "ATKD-414",
    "NSODN-025",
    "JUR-824",
    "FAVR-008",
    "ROE-560",
    "EBWH-367",
    "DLDSS-515",
    "SNOS-313",
    "EKAI-023",
    "JUMS-186",
]


METHOD = (
    "The data is based on the number "
    "of visits received to each movie "
    "in the prior seven days. "
    "The data is slightly weighted "
    "towards newer releases to ensure "
    "the data is useful."
)


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


def synthetic_html(
    *,
    rank=1,
    h5="JUR-786",
    movie_slug="jur-786",
    image_alt="JUR-786",
):
    movie_url = (
        "https://www.javdatabase.com/"
        f"movies/{movie_slug}/"
    )

    cover_url = (
        "https://www.javdatabase.com/"
        "covers/thumb/test.webp"
    )

    genre_url = (
        "https://www.javdatabase.com/"
        "genres/test-genre/"
    )

    studio_url = (
        "https://www.javdatabase.com/"
        "studios/test-studio/"
    )

    idol_url = (
        "https://www.javdatabase.com/"
        "idols/test-idol/"
    )

    return f"""
<html>
<body>

<h1>
Top JAV Movies – 2026 – Week 33
(13th – 19th August 2026)
</h1>

<p>{METHOD}</p>

<div class="container">
<div class="list-group">

<div class="list-group-item d-flex flex-column flex-md-row align-items-center">

    {rank}

    <a href="{movie_url}">
        <img
            src="{cover_url}"
            alt="{image_alt}"
        >
    </a>

    <div>

        <a href="{movie_url}">
            <h5 class="mb-2">
                {h5}
            </h5>

            <p class="mb-1">
                Title: Synthetic Weekly Title
            </p>
        </a>

        <a
            rel="tag"
            href="{genre_url}"
        >
            Test Genre
        </a>

        <a
            rel="tag"
            href="{studio_url}"
        >
            Test Studio
        </a>

        <a href="{idol_url}">
            Test Idol
        </a>

        <p class="mb-1">
            Release Date: 2026-08-07
        </p>

    </div>

</div>

</div>
</div>

</body>
</html>
"""

def real_fixture_smoke(
    path: Path,
):
    with path.open(
        "r",
        encoding="utf-8",
    ) as fh:
        forensic = json.load(
            fh
        )

    selected = (
        forensic.get(
            "selected_article"
        )
        or {}
    )

    article = (
        forensic.get(
            "article"
        )
        or {}
    )

    result = (
        parse_javdatabase_weekly_envelope(
            article
        )
    )

    require(
        result[
            "source"
        ]
        == JAVDATABASE_WEEKLY_SOURCE,
        "weekly source changed",
    )

    require(
        result[
            "period"
        ]
        == "2026-W33",
        "weekly period changed",
    )

    require(
        result[
            "week"
        ]
        == 33,
        "weekly number changed",
    )

    require(
        result[
            "item_count"
        ]
        == 25,
        "weekly item count changed",
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
        ids == EXPECTED_IDS,
        "weekly exact ranking changed",
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
                26,
            )
        ),
        "weekly rank sequence changed",
    )

    first = result[
        "items"
    ][0]

    require(
        first[
            "dvd_id"
        ]
        == "JUR-786",
        "rank 1 DVD ID changed",
    )

    require(
        first[
            "source_url"
        ]
        == (
            "https://www.javdatabase.com/"
            "movies/jur-786/"
        ),
        "rank 1 canonical movie URL changed",
    )

    require(
        first[
            "cover_url"
        ]
        == (
            "https://www.javdatabase.com/"
            "covers/thumb/ju/"
            "jur00786ps.webp"
        ),
        "rank 1 cover URL changed",
    )

    require(
        first[
            "release_date"
        ]
        == "2026-08-07",
        "rank 1 release date changed",
    )

    require(
        first[
            "studio"
        ]
        == "MADONNA",
        "rank 1 studio changed",
    )

    require(
        first[
            "idols"
        ]
        == [
            "Meguri (Megu Fujiura)",
        ],
        "rank 1 idols changed",
    )

    require(
        "Big Tits"
        in first[
            "genres"
        ],
        "rank 1 genres changed",
    )

    require(
        "JUR-00786PS"
        not in ids,
        (
            "cover filename leaked "
            "into DVD IDs"
        ),
    )

    require(
        "SNOS-00334PS"
        not in ids,
        (
            "zero-padded cover ID "
            "leaked into ranking"
        ),
    )

    require(
        selected.get(
            "title"
        )
        == result[
            "article_title"
        ],
        "selected article title mismatch",
    )

    print(
        "WEEK33_EXACT_25_SMOKE=PASS"
    )

    print(
        "DOCUMENT_RANK_ORDER_SMOKE=PASS"
    )

    print(
        "H5_CANONICAL_DVD_ID_SMOKE=PASS"
    )

    print(
        "MOVIE_LINK_CROSSCHECK_SMOKE=PASS"
    )

    print(
        "IMAGE_ALT_CROSSCHECK_SMOKE=PASS"
    )

    print(
        "COVER_FILENAME_NOT_ID_SMOKE=PASS"
    )

    print(
        "WEEKLY_METADATA_EXTRACTION_SMOKE=PASS"
    )

    print(
        "WEEKLY_METHOD_SEMANTICS_SMOKE=PASS"
    )


def synthetic_boundary_smoke():
    base = (
        "https://www.javdatabase.com/"
        "2026/08/25/"
        "top-jav-movies-test/"
    )

    good = (
        parse_javdatabase_weekly_html(
            synthetic_html(),
            base,
            expected_count=1,
        )
    )

    require(
        good[
            "items"
        ][0][
            "dvd_id"
        ]
        == "JUR-786",
        "synthetic canonical ID failed",
    )

    try:
        parse_javdatabase_weekly_html(
            synthetic_html(
                rank=2,
            ),
            base,
            expected_count=1,
        )

    except ValueError as exc:
        require(
            "displayed rank"
            in str(exc),
            "unexpected rank failure",
        )

    else:
        raise RuntimeError(
            "rank/document mismatch "
            "must fail closed"
        )

    try:
        parse_javdatabase_weekly_html(
            synthetic_html(
                h5="JUR-787",
            ),
            base,
            expected_count=1,
        )

    except ValueError as exc:
        require(
            (
                "DVD ID mismatch"
                in str(exc)
                or "cover"
                in str(exc)
            ),
            "unexpected H5 mismatch failure",
        )

    else:
        raise RuntimeError(
            "H5/movie mismatch "
            "must fail closed"
        )

    try:
        parse_javdatabase_weekly_html(
            synthetic_html(
                image_alt="JUR-787",
            ),
            base,
            expected_count=1,
        )

    except ValueError as exc:
        require(
            "cover"
            in str(exc),
            "unexpected image-alt failure",
        )

    else:
        raise RuntimeError(
            "image ALT mismatch "
            "must fail closed"
        )

    try:
        parse_javdatabase_weekly_html(
            synthetic_html(
                movie_slug="jur-787",
            ),
            base,
            expected_count=1,
        )

    except ValueError as exc:
        require(
            "movie link"
            in str(exc),
            "unexpected movie-link failure",
        )

    else:
        raise RuntimeError(
            "movie URL mismatch "
            "must fail closed"
        )

    html_without_method = (
        synthetic_html().replace(
            METHOD,
            "method removed",
        )
    )

    try:
        parse_javdatabase_weekly_html(
            html_without_method,
            base,
            expected_count=1,
        )

    except ValueError as exc:
        require(
            "methodology changed"
            in str(exc),
            "unexpected method failure",
        )

    else:
        raise RuntimeError(
            "missing weekly method "
            "must fail closed"
        )

    print(
        "RANK_MISMATCH_FAIL_CLOSED_SMOKE=PASS"
    )

    print(
        "DVD_ID_CROSSCHECK_FAIL_CLOSED_SMOKE=PASS"
    )

    print(
        "METHOD_CHANGE_FAIL_CLOSED_SMOKE=PASS"
    )


def main():
    if len(
        sys.argv
    ) != 2:
        raise RuntimeError(
            "usage: "
            "teddy_discovery_"
            "javdatabase_smoke.py "
            "<forensic-json>"
        )

    real_fixture_smoke(
        Path(
            sys.argv[1]
        )
    )

    synthetic_boundary_smoke()

    print(
        "JAVDATABASE_WEEKLY_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
