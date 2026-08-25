from pathlib import Path
import json
import sys
import tempfile

from teddy_discovery_db import (
    SCHEMA_VERSION,
    connect,
    initialize,
)

from teddy_discovery_missav import (
    MISSAV_RELEASE_SOURCE,
    list_latest_items,
    merge_missav_release_envelopes,
    missav_release_next_url_from_envelope,
    parse_missav_release_envelope,
    upsert_latest_items,
)


EXPECTED_IDS = [
    "SDNM-560",
    "SDMM-238",
    "SDAB-356",
    "SDAB-358",
    "SDAM-179",
    "PRIAN-057",
    "PRIAN-058",
    "PRIAN-055",
    "PRIAN-056",
    "NXGS-025",
    "KIR-079",
    "HNBR-014",
]


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


def synthetic_release_envelope(
    page: int,
    count: int = 12,
):
    if page < 1:
        raise ValueError(
            "page must be >= 1"
        )

    first = (
        (page - 1)
        * count
        + 1
    )

    cards = []

    for number in range(
        first,
        first + count,
    ):
        dvd_id = (
            f"TST-{number:03d}"
        )

        slug = dvd_id.lower()

        cards.append(
            (
                '<div class="thumbnail group">'
                '<div>'
                f'<a href="/ko/{slug}">'
                '<img '
                f'data-src="https://example.invalid/{slug}.jpg" '
                f'alt="Synthetic {dvd_id}">'
                '</a>'
                '</div>'
                '</div>'
            )
        )

    if page < 5:
        next_page = page + 1

        cards.append(
            (
                '<nav>'
                '<a '
                'rel="next" '
                f'href="https://missav.ws/'
                f'dm635/ko/release?page={next_page}"'
                '>'
                'Next'
                '</a>'
                '</nav>'
            )
        )

    requested = (
        "https://missav.ws/ko/release"
        if page == 1
        else (
            "https://missav.ws/dm635/"
            f"ko/release?page={page}"
        )
    )

    final_url = (
        "https://missav.ws/dm635/"
        "ko/release"
        if page == 1
        else (
            "https://missav.ws/dm635/"
            f"ko/release?page={page}"
        )
    )

    return {
        "status":
            200,

        "requested_url":
            requested,

        "final_url":
            final_url,

        "body":
            "<html><body>"
            + "".join(cards)
            + "</body></html>",
    }


def pagination_smoke(
    real_envelope,
):
    next_url = (
        missav_release_next_url_from_envelope(
            real_envelope
        )
    )

    require(
        next_url is not None,
        "real release next URL missing",
    )

    require(
        next_url.startswith(
            "https://missav.ws/"
        ),
        "real next URL host changed",
    )

    require(
        "/ko/release"
        in next_url,
        "real next URL route changed",
    )

    require(
        "page=2"
        in next_url,
        "real next URL is not page 2",
    )

    print(
        "MISSAV_REAL_NEXT_LINK_SMOKE=PASS"
    )

    synthetic = [
        synthetic_release_envelope(
            page
        )
        for page in range(
            1,
            6,
        )
    ]

    for index in range(
        4
    ):
        expected = (
            "page="
            + str(
                index + 2
            )
        )

        actual = (
            missav_release_next_url_from_envelope(
                synthetic[index]
            )
        )

        require(
            actual
            and expected
            in actual,
            (
                "synthetic next link "
                f"failed at page "
                f"{index + 1}"
            ),
        )

    require(
        missav_release_next_url_from_envelope(
            synthetic[4]
        )
        is None,
        "last synthetic page "
        "must not have next",
    )

    merged = (
        merge_missav_release_envelopes(
            synthetic,
            limit=50,
        )
    )

    require(
        len(merged) == 50,
        "merged latest count changed",
    )

    require(
        [
            item[
                "dvd_id"
            ]
            for item in merged
        ]
        == [
            f"TST-{number:03d}"
            for number in range(
                1,
                51,
            )
        ],
        "merged page ordering changed",
    )

    require(
        [
            item[
                "position"
            ]
            for item in merged
        ]
        == list(
            range(
                1,
                51,
            )
        ),
        "global positions changed",
    )

    try:
        merge_missav_release_envelopes(
            synthetic[:4],
            limit=50,
        )

    except ValueError as exc:
        require(
            "insufficient unique"
            in str(exc),
            (
                "unexpected insufficient "
                "page failure"
            ),
        )

    else:
        raise RuntimeError(
            "four 12-card pages "
            "must not satisfy limit 50"
        )

    print(
        "MISSAV_PAGINATION_CHAIN_SMOKE=PASS"
    )

    print(
        "MISSAV_GLOBAL_POSITION_SMOKE=PASS"
    )

    print(
        "MISSAV_LIMIT_50_SMOKE=PASS"
    )

    print(
        "MISSAV_INSUFFICIENT_PAGES_FAIL_CLOSED_SMOKE=PASS"
    )



def main():
    envelope_path = Path(
        sys.argv[1]
    )

    envelope = json.loads(
        envelope_path.read_text(
            encoding="utf-8"
        )
    )

    pagination_smoke(
        envelope
    )

    items = (
        parse_missav_release_envelope(
            envelope
        )
    )

    ids = [
        item["dvd_id"]
        for item in items
    ]

    require(
        ids == EXPECTED_IDS,
        (
            "MissAV release IDs changed: "
            + repr(ids)
        ),
    )

    require(
        len(items) == 12,
        (
            "expected 12 release cards, "
            f"got {len(items)}"
        ),
    )

    require(
        all(
            item["source"]
            == MISSAV_RELEASE_SOURCE
            for item in items
        ),
        "release source mapping changed",
    )

    require(
        all(
            item["source_url"].startswith(
                "https://missav.ws/ko/"
            )
            for item in items
        ),
        "canonical MissAV URL changed",
    )

    require(
        all(
            item["title"]
            for item in items
        ),
        "release title missing",
    )

    require(
        all(
            item["cover_url"]
            and item[
                "cover_url"
            ].startswith(
                "https://fourhoi.com/"
            )
            for item in items
        ),
        "release cover missing",
    )

    require(
        [
            item["position"]
            for item in items
        ]
        == list(
            range(
                1,
                13,
            )
        ),
        "release DOM order changed",
    )

    print(
        "MISSAV_RELEASE_CARD_SMOKE=PASS"
    )

    print(
        "MISSAV_RELEASE_TITLE_COVER_SMOKE=PASS"
    )

    print(
        "MISSAV_RELEASE_ORDER_SMOKE=PASS"
    )

    first_observed = (
        "2026-08-25T10:00:00+00:00"
    )

    second_observed = (
        "2026-08-26T10:00:00+00:00"
    )

    with tempfile.TemporaryDirectory(
        prefix="teddy-missav-release-"
    ) as temp:
        db_path = (
            Path(temp)
            / "discovery.sqlite3"
        )

        connection = connect(
            db_path
        )

        initialize(
            connection
        )

        schema = connection.execute(
            """
            SELECT MAX(version)
            FROM schema_migrations
            """
        ).fetchone()[0]

        require(
            schema == SCHEMA_VERSION,
            (
                "schema expected "
                f"{SCHEMA_VERSION}, "
                f"got {schema}"
            ),
        )

        #
        # Seed one rich FANZA row.
        #
        # MissAV release collection must
        # not overwrite its rich metadata.
        #
        connection.execute(
            """
            INSERT INTO titles(
                dvd_id,
                title,
                release_date,
                maker,
                cover_url,
                raw_metadata,
                metadata_source,
                first_seen_at,
                last_seen_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                "SDNM-560",
                "FANZA PRESERVED TITLE",
                "2026-01-01",
                "FANZA PRESERVED MAKER",
                (
                    "https://example.invalid/"
                    "fanza-cover.jpg"
                ),
                '{"source":"fanza"}',
                "fanza",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )

        connection.commit()

        first_count = (
            upsert_latest_items(
                connection,
                items,
                observed_at=
                    first_observed,
            )
        )

        require(
            first_count == 12,
            "first release import count",
        )

        first_latest = (
            list_latest_items(
                connection,
                limit=50,
            )
        )

        require(
            [
                item["dvd_id"]
                for item
                in first_latest
            ]
            == EXPECTED_IDS,
            "first release page order changed",
        )

        #
        # Simulate MissAV changing its
        # release ordering on the next run.
        #
        # Current/latest ordering must follow
        # the NEW page order, not freeze the
        # first observation forever.
        #
        second_items = []

        for position, item in enumerate(
            reversed(items),
            start=1,
        ):
            value = dict(item)
            value["position"] = position

            second_items.append(
                value
            )

        second_count = (
            upsert_latest_items(
                connection,
                second_items,
                observed_at=
                    second_observed,
            )
        )

        require(
            second_count == 12,
            "second release import count",
        )

        require(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM latest_items
                """
            ).fetchone()[0]
            == 12,
            "latest rows duplicated",
        )

        require(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM titles
                """
            ).fetchone()[0]
            == 12,
            "title rows duplicated",
        )

        rich = connection.execute(
            """
            SELECT
                title,
                release_date,
                maker,
                cover_url,
                raw_metadata,
                metadata_source
            FROM titles
            WHERE dvd_id = 'SDNM-560'
            """
        ).fetchone()

        require(
            rich["title"]
            == "FANZA PRESERVED TITLE",
            "MissAV clobbered FANZA title",
        )

        require(
            rich["release_date"]
            == "2026-01-01",
            "MissAV clobbered release date",
        )

        require(
            rich["maker"]
            == "FANZA PRESERVED MAKER",
            "MissAV clobbered maker",
        )

        require(
            rich["cover_url"]
            == (
                "https://example.invalid/"
                "fanza-cover.jpg"
            ),
            "MissAV clobbered FANZA cover",
        )

        require(
            rich["metadata_source"]
            == "fanza",
            "MissAV clobbered metadata source",
        )

        latest_rich = connection.execute(
            """
            SELECT
                source,
                source_url,
                title,
                cover_url,
                first_seen_at,
                last_seen_at,
                first_position,
                last_position
            FROM latest_items
            WHERE
                source = ?
                AND dvd_id = ?
            """,
            (
                MISSAV_RELEASE_SOURCE,
                "SDNM-560",
            ),
        ).fetchone()

        require(
            latest_rich["source"]
            == MISSAV_RELEASE_SOURCE,
            "release provenance missing",
        )

        require(
            latest_rich["source_url"]
            == (
                "https://missav.ws/"
                "ko/sdnm-560"
            ),
            "release source URL missing",
        )

        require(
            latest_rich["title"]
            == items[0]["title"],
            "release source title missing",
        )

        require(
            latest_rich["cover_url"]
            == items[0]["cover_url"],
            "release source cover missing",
        )

        require(
            latest_rich["first_seen_at"]
            == first_observed,
            "release first_seen changed",
        )

        require(
            latest_rich["last_seen_at"]
            == second_observed,
            "release last_seen not updated",
        )

        require(
            latest_rich["first_position"]
            == 1,
            "release first position changed",
        )

        require(
            latest_rich["last_position"]
            == 12,
            "release last position not updated",
        )

        fallback = connection.execute(
            """
            SELECT
                title,
                cover_url,
                metadata_source
            FROM titles
            WHERE dvd_id = 'SDMM-238'
            """
        ).fetchone()

        require(
            fallback["title"]
            == items[1]["title"],
            "MissAV fallback title missing",
        )

        require(
            fallback["cover_url"]
            == items[1]["cover_url"],
            "MissAV fallback cover missing",
        )

        require(
            fallback["metadata_source"]
            == MISSAV_RELEASE_SOURCE,
            "MissAV fallback provenance missing",
        )

        latest = list_latest_items(
            connection,
            limit=50,
        )

        expected_second = list(
            reversed(
                EXPECTED_IDS
            )
        )

        require(
            [
                item["dvd_id"]
                for item in latest
            ]
            == expected_second,
            (
                "current MissAV release "
                "order not followed"
            ),
        )

        connection.close()

    print(
        "SCHEMA_CURRENT_RELEASE_SMOKE=PASS"
    )

    print(
        "LATEST_IDEMPOTENCY_SMOKE=PASS"
    )

    print(
        "LATEST_CURRENT_ORDER_SMOKE=PASS"
    )

    print(
        "RICH_METADATA_PRESERVATION_SMOKE=PASS"
    )

    print(
        "MISSAV_RELEASE_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
