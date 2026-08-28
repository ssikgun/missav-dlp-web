from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile

import teddy_discovery_db as discovery_db

from teddy_discovery_variants import (
    VARIANT_STANDARD,
    VARIANT_UNCENSORED,
    persist_title_variant,
    read_title_variants,
)


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


def scalar(
    connection,
    sql,
    params=(),
):
    row = connection.execute(
        sql,
        params,
    ).fetchone()

    return (
        row[0]
        if row
        else None
    )


def insert_title(
    connection,
    dvd_id,
):
    connection.execute(
        """
        INSERT INTO titles(
            dvd_id,
            title,
            first_seen_at,
            last_seen_at
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            dvd_id,
            dvd_id + " title",
            "2026-08-28T00:00:00+00:00",
            "2026-08-28T00:00:00+00:00",
        ),
    )

    connection.commit()


def fresh_schema_smoke():
    with tempfile.TemporaryDirectory(
        prefix="teddy-variant-v6-fresh-"
    ) as temp:
        db_path = (
            Path(temp)
            / "fresh.sqlite3"
        )

        connection = (
            discovery_db.connect(
                db_path
            )
        )

        try:
            discovery_db.initialize(
                connection
            )

            require(
                discovery_db.SCHEMA_VERSION
                == 6,
                "SCHEMA_VERSION is not 6",
            )

            current = scalar(
                connection,
                """
                SELECT MAX(version)
                FROM schema_migrations
                """,
            )

            require(
                current == 6,
                "fresh DB did not reach v6",
            )

            columns = {
                row["name"]:
                    row
                for row in connection.execute(
                    """
                    PRAGMA table_info(
                        title_variants
                    )
                    """
                ).fetchall()
            }

            expected = {
                "dvd_id",
                "source",
                "variant_kind",
                "variant_slug",
                "page_url",
                "confirmed",
                "first_seen_at",
                "last_seen_at",
                "last_checked_at",
            }

            require(
                set(
                    columns
                )
                == expected,
                "title_variants columns mismatch",
            )

            require(
                columns[
                    "dvd_id"
                ][
                    "pk"
                ]
                == 1,
                "dvd_id PK order changed",
            )

            require(
                columns[
                    "source"
                ][
                    "pk"
                ]
                == 2,
                "source PK order changed",
            )

            require(
                columns[
                    "variant_kind"
                ][
                    "pk"
                ]
                == 3,
                "variant_kind PK order changed",
            )

            sql = scalar(
                connection,
                """
                SELECT sql
                FROM sqlite_master
                WHERE type = 'table'
                  AND name = 'title_variants'
                """,
            )

            require(
                sql
                and "UNIQUE" in sql.upper()
                and "PAGE_URL" in sql.upper(),
                "page_url uniqueness missing",
            )

        finally:
            connection.close()

    print(
        "VARIANT_FRESH_SCHEMA_V6_SMOKE=PASS"
    )


def build_v5_fixture(
    db_path,
):
    connection = (
        discovery_db.connect(
            db_path
        )
    )

    connection.executescript(
        discovery_db.SCHEMA
    )

    connection.execute(
        """
        INSERT INTO schema_migrations(
            version,
            applied_at
        )
        VALUES (?, ?)
        """,
        (
            1,
            "2026-08-28T00:00:00+00:00",
        ),
    )

    connection.commit()

    discovery_db._migrate_1_to_2(
        connection
    )

    discovery_db._migrate_2_to_3(
        connection
    )

    discovery_db._migrate_3_to_4(
        connection
    )

    discovery_db._migrate_4_to_5(
        connection
    )

    require(
        scalar(
            connection,
            """
            SELECT MAX(version)
            FROM schema_migrations
            """,
        )
        == 5,
        "fixture did not stop at v5",
    )

    insert_title(
        connection,
        "SW-893",
    )

    return connection


def v5_to_v6_migration_smoke():
    with tempfile.TemporaryDirectory(
        prefix="teddy-variant-v6-migrate-"
    ) as temp:
        db_path = (
            Path(temp)
            / "migrate.sqlite3"
        )

        connection = (
            build_v5_fixture(
                db_path
            )
        )

        try:
            discovery_db.initialize(
                connection
            )

            require(
                scalar(
                    connection,
                    """
                    SELECT MAX(version)
                    FROM schema_migrations
                    """,
                )
                == 6,
                "v5 DB did not migrate to v6",
            )

            require(
                scalar(
                    connection,
                    """
                    SELECT COUNT(*)
                    FROM schema_migrations
                    WHERE version = 6
                    """,
                )
                == 1,
                "v6 migration marker mismatch",
            )

            require(
                scalar(
                    connection,
                    """
                    SELECT COUNT(*)
                    FROM titles
                    WHERE dvd_id = 'SW-893'
                    """,
                )
                == 1,
                "v5 title changed during migration",
            )

        finally:
            connection.close()

    print(
        "VARIANT_V5_TO_V6_MIGRATION_SMOKE=PASS"
    )


def storage_readback_smoke():
    with tempfile.TemporaryDirectory(
        prefix="teddy-variant-store-"
    ) as temp:
        db_path = (
            Path(temp)
            / "store.sqlite3"
        )

        connection = (
            discovery_db.connect(
                db_path
            )
        )

        try:
            discovery_db.initialize(
                connection
            )

            insert_title(
                connection,
                "SW-893",
            )

            standard = (
                persist_title_variant(
                    connection,
                    {
                        "dvd_id":
                            "SW-893",

                        "source":
                            "missav",

                        "variant_kind":
                            VARIANT_STANDARD,

                        "variant_slug":
                            "sw-893",

                        "page_url":
                            (
                                "https://missav123.com/"
                                "ko/sw-893"
                            ),

                        "confirmed":
                            1,
                    },
                    observed_at=(
                        "2026-08-28T01:00:00+00:00"
                    ),
                    checked_at=(
                        "2026-08-28T01:01:00+00:00"
                    ),
                )
            )

            require(
                standard[
                    "dvd_id"
                ]
                == "SW-893",
                "standard DVD ID mismatch",
            )

            uncensored = (
                persist_title_variant(
                    connection,
                    {
                        "dvd_id":
                            (
                                "sw-893-"
                                "uncensored-leak"
                            ),

                        "source":
                            "missav",

                        "variant_kind":
                            VARIANT_UNCENSORED,

                        "variant_slug":
                            (
                                "sw-893-"
                                "uncensored-leak"
                            ),

                        "page_url":
                            (
                                "https://missav123.com/"
                                "ko/"
                                "sw-893-"
                                "uncensored-leak"
                            ),

                        "confirmed":
                            True,
                    },
                    observed_at=(
                        "2026-08-28T02:00:00+00:00"
                    ),
                    checked_at=(
                        "2026-08-28T02:01:00+00:00"
                    ),
                )
            )

            require(
                uncensored[
                    "dvd_id"
                ]
                == "SW-893",
                "variant slug did not collapse",
            )

            require(
                uncensored[
                    "confirmed"
                ]
                == 1,
                "confirmed readback mismatch",
            )

            rows = read_title_variants(
                connection,
                dvd_id=(
                    "https://missav123.com/"
                    "ko/"
                    "sw-893-"
                    "uncensored-leak"
                ),
            )

            require(
                len(
                    rows
                )
                == 2,
                "variant readback row count mismatch",
            )

            by_kind = {
                row[
                    "variant_kind"
                ]:
                    row
                for row in rows
            }

            require(
                set(
                    by_kind
                )
                == {
                    VARIANT_STANDARD,
                    VARIANT_UNCENSORED,
                },
                "variant kinds mismatch",
            )

            first_seen = (
                by_kind[
                    VARIANT_UNCENSORED
                ][
                    "first_seen_at"
                ]
            )

            updated = (
                persist_title_variant(
                    connection,
                    {
                        "dvd_id":
                            "SW-893",

                        "source":
                            "missav",

                        "variant_kind":
                            VARIANT_UNCENSORED,

                        "variant_slug":
                            (
                                "sw-893-"
                                "uncensored-leak"
                            ),

                        "page_url":
                            (
                                "https://missav123.com/"
                                "ko/"
                                "sw-893-"
                                "uncensored-leak"
                            ),

                        "confirmed":
                            1,
                    },
                    observed_at=(
                        "2026-08-28T03:00:00+00:00"
                    ),
                    checked_at=(
                        "2026-08-28T03:01:00+00:00"
                    ),
                )
            )

            require(
                updated[
                    "first_seen_at"
                ]
                == first_seen,
                "first_seen_at was overwritten",
            )

            require(
                updated[
                    "last_seen_at"
                ]
                == (
                    "2026-08-28T03:00:00+00:00"
                ),
                "last_seen_at did not advance",
            )

            require(
                updated[
                    "last_checked_at"
                ]
                == (
                    "2026-08-28T03:01:00+00:00"
                ),
                "last_checked_at did not advance",
            )

            confirmed_rows = (
                read_title_variants(
                    connection,
                    dvd_id="SW-893",
                    source="missav",
                    confirmed_only=True,
                )
            )

            require(
                len(
                    confirmed_rows
                )
                == 2,
                "confirmed-only readback mismatch",
            )

        finally:
            connection.close()

    print(
        "VARIANT_STORAGE_READBACK_SMOKE=PASS"
    )


def unique_page_url_fail_closed_smoke():
    with tempfile.TemporaryDirectory(
        prefix="teddy-variant-unique-"
    ) as temp:
        db_path = (
            Path(temp)
            / "unique.sqlite3"
        )

        connection = (
            discovery_db.connect(
                db_path
            )
        )

        try:
            discovery_db.initialize(
                connection
            )

            insert_title(
                connection,
                "SW-893",
            )

            persist_title_variant(
                connection,
                {
                    "dvd_id":
                        "SW-893",

                    "source":
                        "missav",

                    "variant_kind":
                        VARIANT_STANDARD,

                    "variant_slug":
                        "sw-893",

                    "page_url":
                        (
                            "https://missav123.com/"
                            "ko/sw-893"
                        ),

                    "confirmed":
                        1,
                },
                observed_at=(
                    "2026-08-28T01:00:00+00:00"
                ),
            )

            persist_title_variant(
                connection,
                {
                    "dvd_id":
                        "SW-893",

                    "source":
                        "missav",

                    "variant_kind":
                        VARIANT_UNCENSORED,

                    "variant_slug":
                        (
                            "sw-893-"
                            "uncensored-leak"
                        ),

                    "page_url":
                        (
                            "https://missav123.com/"
                            "ko/"
                            "sw-893-"
                            "uncensored-leak"
                        ),

                    "confirmed":
                        1,
                },
                observed_at=(
                    "2026-08-28T02:00:00+00:00"
                ),
            )

            try:
                persist_title_variant(
                    connection,
                    {
                        "dvd_id":
                            "SW-893",

                        "source":
                            "missav",

                        "variant_kind":
                            VARIANT_STANDARD,

                        "variant_slug":
                            "sw-893",

                        "page_url":
                            (
                                "https://missav123.com/"
                                "ko/"
                                "sw-893-"
                                "uncensored-leak"
                            ),

                        "confirmed":
                            1,
                    },
                    observed_at=(
                        "2026-08-28T03:00:00+00:00"
                    ),
                )

            except sqlite3.IntegrityError:
                pass

            else:
                raise RuntimeError(
                    "duplicate page_url "
                    "was not rejected"
                )

            rows = (
                read_title_variants(
                    connection,
                    dvd_id="SW-893",
                )
            )

            by_kind = {
                row[
                    "variant_kind"
                ]:
                    row
                for row in rows
            }

            require(
                by_kind[
                    VARIANT_STANDARD
                ][
                    "page_url"
                ]
                == (
                    "https://missav123.com/"
                    "ko/sw-893"
                ),
                "failed unique write "
                "changed standard row",
            )

        finally:
            connection.close()

    print(
        "VARIANT_PAGE_URL_UNIQUE_FAIL_CLOSED_SMOKE=PASS"
    )


def foreign_key_fail_closed_smoke():
    with tempfile.TemporaryDirectory(
        prefix="teddy-variant-fk-"
    ) as temp:
        db_path = (
            Path(temp)
            / "fk.sqlite3"
        )

        connection = (
            discovery_db.connect(
                db_path
            )
        )

        try:
            discovery_db.initialize(
                connection
            )

            try:
                persist_title_variant(
                    connection,
                    {
                        "dvd_id":
                            "SW-894",

                        "source":
                            "missav",

                        "variant_kind":
                            VARIANT_STANDARD,

                        "variant_slug":
                            "sw-894",

                        "page_url":
                            (
                                "https://missav123.com/"
                                "ko/sw-894"
                            ),

                        "confirmed":
                            1,
                    },
                    observed_at=(
                        "2026-08-28T01:00:00+00:00"
                    ),
                )

            except sqlite3.IntegrityError:
                pass

            else:
                raise RuntimeError(
                    "orphan title variant "
                    "was not rejected"
                )

            require(
                scalar(
                    connection,
                    """
                    SELECT COUNT(*)
                    FROM title_variants
                    """
                )
                == 0,
                "orphan write left row behind",
            )

        finally:
            connection.close()

    print(
        "VARIANT_FOREIGN_KEY_FAIL_CLOSED_SMOKE=PASS"
    )


def source_family_validation_smoke():
    with tempfile.TemporaryDirectory(
        prefix="teddy-variant-source-"
    ) as temp:
        db_path = (
            Path(temp)
            / "source.sqlite3"
        )

        connection = (
            discovery_db.connect(
                db_path
            )
        )

        try:
            discovery_db.initialize(
                connection
            )

            insert_title(
                connection,
                "SW-895",
            )

            row = persist_title_variant(
                connection,
                {
                    "dvd_id":
                        "SW-895",

                    "source":
                        "123av",

                    "variant_kind":
                        VARIANT_STANDARD,

                    "variant_slug":
                        "sw-895",

                    "page_url":
                        (
                            "https://123av.com/"
                            "ko/v/sw-895"
                        ),

                    "confirmed":
                        1,
                },
                observed_at=(
                    "2026-08-28T01:00:00+00:00"
                ),
            )

            require(
                row[
                    "source"
                ]
                == "123av",
                "123AV source readback mismatch",
            )

            try:
                persist_title_variant(
                    connection,
                    {
                        "dvd_id":
                            "SW-895",

                        "source":
                            "missav",

                        "variant_kind":
                            VARIANT_UNCENSORED,

                        "variant_slug":
                            "sw-895",

                        "page_url":
                            (
                                "https://123av.com/"
                                "ko/v/sw-895"
                            ),

                        "confirmed":
                            1,
                    },
                    observed_at=(
                        "2026-08-28T02:00:00+00:00"
                    ),
                )

            except ValueError:
                pass

            else:
                raise RuntimeError(
                    "cross-family variant URL "
                    "was not rejected"
                )

        finally:
            connection.close()

    print(
        "VARIANT_SOURCE_FAMILY_VALIDATION_SMOKE=PASS"
    )


def main():
    fresh_schema_smoke()
    v5_to_v6_migration_smoke()
    storage_readback_smoke()
    unique_page_url_fail_closed_smoke()
    foreign_key_fail_closed_smoke()
    source_family_validation_smoke()

    print(
        "TEDDY_DISCOVERY_VARIANTS_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
