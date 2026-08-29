from pathlib import Path
import tempfile

from teddy_discovery_db import (
    connect,
    initialize,
)

from teddy_discovery_javinfo import (
    upsert_future_release_seeds,
    upsert_movie_metadata,
)


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


def rich_payload(
    dvd_id,
    *,
    release_date=None,
    actress,
    genre,
):
    result = {
        "dvdId":
            dvd_id,

        "titleEn":
            "RICH TITLE "
            + dvd_id,

        "makers": [
            {
                "name":
                    "RICH MAKER"
            }
        ],

        "jacketFullUrl":
            (
                "https://example.invalid/"
                + dvd_id.lower()
                + ".jpg"
            ),

        "actresses": [
            {
                "name":
                    actress
            }
        ],

        "categories": [
            {
                "name":
                    genre
            }
        ],
    }

    if release_date is not None:
        result[
            "releaseDate"
        ] = release_date

    return {
        "source":
            "javdatabase-movie",

        "result":
            result,
    }


def main():
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-fanza-seed-smoke-"
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

        upsert_movie_metadata(
            connection,
            rich_payload(
                "SSIS-001",
                release_date=
                    "2021-02-19",
                actress=
                    "RICH ACTRESS A",
                genre=
                    "RICH GENRE A",
            ),
        )

        upsert_movie_metadata(
            connection,
            rich_payload(
                "JUR-821",
                release_date=None,
                actress=
                    "RICH ACTRESS B",
                genre=
                    "RICH GENRE B",
            ),
        )

        before_ssis = (
            connection.execute(
                """
                SELECT
                    title,
                    release_date,
                    maker,
                    cover_url,
                    raw_metadata,
                    metadata_source,
                    first_seen_at,
                    last_seen_at
                FROM titles
                WHERE dvd_id = 'SSIS-001'
                """
            ).fetchone()
        )

        before_jur = (
            connection.execute(
                """
                SELECT
                    title,
                    release_date,
                    maker,
                    cover_url,
                    raw_metadata,
                    metadata_source,
                    first_seen_at,
                    last_seen_at
                FROM titles
                WHERE dvd_id = 'JUR-821'
                """
            ).fetchone()
        )

        before_people = (
            connection.execute(
                """
                SELECT COUNT(*)
                FROM title_people
                """
            ).fetchone()[0]
        )

        before_genres = (
            connection.execute(
                """
                SELECT COUNT(*)
                FROM title_genres
                """
            ).fetchone()[0]
        )

        items = [
            {
                "dvd_id":
                    "SSIS-001",

                "release_date":
                    "2026-09-20",

                "metadata_source":
                    "fanza",
            },
            {
                "dvd_id":
                    "JUR-821",

                "release_date":
                    "2026-09-10",

                "metadata_source":
                    "fanza",
            },
            {
                "dvd_id":
                    "SONE-978",

                "release_date":
                    "2026-09-05",

                "metadata_source":
                    "fanza",
            },
        ]

        observed_at = (
            "2026-08-29T01:23:45+00:00"
        )

        first = (
            upsert_future_release_seeds(
                connection,
                items,
                observed_at=
                    observed_at,
            )
        )

        second = (
            upsert_future_release_seeds(
                connection,
                items,
                observed_at=
                    observed_at,
            )
        )

        require(
            first == 3,
            "first seed write "
            "count changed",
        )

        require(
            second == 3,
            "second seed write "
            "count changed",
        )

        ssis = connection.execute(
            """
            SELECT
                title,
                release_date,
                maker,
                cover_url,
                raw_metadata,
                metadata_source,
                first_seen_at,
                last_seen_at
            FROM titles
            WHERE dvd_id = 'SSIS-001'
            """
        ).fetchone()

        require(
            ssis[
                "release_date"
            ]
            == "2021-02-19",
            "existing release date "
            "was clobbered",
        )

        for field in (
            "title",
            "maker",
            "cover_url",
            "raw_metadata",
            "metadata_source",
            "first_seen_at",
        ):
            require(
                ssis[field]
                == before_ssis[field],
                (
                    "existing rich field "
                    "was clobbered: "
                    + field
                ),
            )

        require(
            ssis[
                "last_seen_at"
            ]
            == observed_at,
            "existing last_seen_at "
            "was not refreshed",
        )

        jur = connection.execute(
            """
            SELECT
                title,
                release_date,
                maker,
                cover_url,
                raw_metadata,
                metadata_source,
                first_seen_at,
                last_seen_at
            FROM titles
            WHERE dvd_id = 'JUR-821'
            """
        ).fetchone()

        require(
            before_jur[
                "release_date"
            ] is None,
            "JUR fixture unexpectedly "
            "had release date",
        )

        require(
            jur[
                "release_date"
            ]
            == "2026-09-10",
            "missing release date "
            "was not filled",
        )

        for field in (
            "title",
            "maker",
            "cover_url",
            "raw_metadata",
            "metadata_source",
            "first_seen_at",
        ):
            require(
                jur[field]
                == before_jur[field],
                (
                    "JUR rich field "
                    "was clobbered: "
                    + field
                ),
            )

        seed = connection.execute(
            """
            SELECT
                dvd_id,
                title,
                release_date,
                maker,
                cover_url,
                raw_metadata,
                metadata_source,
                first_seen_at,
                last_seen_at
            FROM titles
            WHERE dvd_id = 'SONE-978'
            """
        ).fetchone()

        require(
            seed is not None,
            "new FANZA seed missing",
        )

        require(
            seed[
                "release_date"
            ]
            == "2026-09-05",
            "new seed release date "
            "changed",
        )

        require(
            seed[
                "metadata_source"
            ] is None,
            "release discovery source "
            "leaked into metadata_source",
        )

        for field in (
            "title",
            "maker",
            "cover_url",
            "raw_metadata",
        ):
            require(
                seed[field] is None,
                (
                    "future seed wrote "
                    "metadata field: "
                    + field
                ),
            )

        require(
            seed[
                "first_seen_at"
            ]
            == observed_at,
            "new seed first_seen_at "
            "changed",
        )

        require(
            seed[
                "last_seen_at"
            ]
            == observed_at,
            "new seed last_seen_at "
            "changed",
        )

        require(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM title_people
                """
            ).fetchone()[0]
            == before_people,
            "future seed changed "
            "title_people",
        )

        require(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM title_genres
                """
            ).fetchone()[0]
            == before_genres,
            "future seed changed "
            "title_genres",
        )

        require(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM latest_items
                """
            ).fetchone()[0]
            == 0,
            "future seed polluted "
            "MissAV latest_items",
        )

        before_count = (
            connection.execute(
                """
                SELECT COUNT(*)
                FROM titles
                """
            ).fetchone()[0]
        )

        duplicate_failed = False

        try:
            upsert_future_release_seeds(
                connection,
                [
                    {
                        "dvd_id":
                            "SONE-978",

                        "release_date":
                            "2026-09-05",
                    },
                    {
                        "dvd_id":
                            "SONE-978",

                        "release_date":
                            "2026-09-05",
                    },
                ],
                observed_at=
                    observed_at,
            )

        except ValueError:
            duplicate_failed = True

        require(
            duplicate_failed,
            "duplicate FANZA seed "
            "did not fail closed",
        )

        require(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM titles
                """
            ).fetchone()[0]
            == before_count,
            "failed duplicate seed "
            "changed DB",
        )

        invalid_date_failed = False

        try:
            upsert_future_release_seeds(
                connection,
                [
                    {
                        "dvd_id":
                            "SONE-979",

                        "release_date":
                            "2026/09/06",
                    }
                ],
                observed_at=
                    observed_at,
            )

        except ValueError:
            invalid_date_failed = True

        require(
            invalid_date_failed,
            "invalid release date "
            "did not fail closed",
        )

        require(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM titles
                """
            ).fetchone()[0]
            == before_count,
            "failed date validation "
            "changed DB",
        )

        connection.close()

    print(
        "FANZA_SEED_MINIMAL_WRITE_SMOKE=PASS"
    )

    print(
        "FANZA_SEED_EXISTING_METADATA_PRESERVED_SMOKE=PASS"
    )

    print(
        "FANZA_SEED_RELEASE_DATE_PRESERVED_SMOKE=PASS"
    )

    print(
        "FANZA_SEED_MISSING_DATE_FILL_SMOKE=PASS"
    )

    print(
        "FANZA_SEED_SOURCE_BOUNDARY_SMOKE=PASS"
    )

    print(
        "FANZA_SEED_RELATION_PRESERVATION_SMOKE=PASS"
    )

    print(
        "FANZA_SEED_FAIL_CLOSED_SMOKE=PASS"
    )

    print(
        "FANZA_FUTURE_SEED_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
