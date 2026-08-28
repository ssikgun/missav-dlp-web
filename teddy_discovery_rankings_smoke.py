from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

from teddy_discovery_db import (
    connect,
    initialize,
)

from teddy_discovery_javdatabase import (
    parse_javdatabase_weekly_envelope,
)

from teddy_discovery_rankings import (
    WEEKLY_CHART_TYPE,
    list_weekly_snapshot,
    replace_weekly_snapshot,
)


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


def sqlite_backup(
    source_path: Path,
    destination_path: Path,
):
    source = sqlite3.connect(
        "file:"
        + str(source_path)
        + "?mode=ro",
        uri=True,
    )

    target = sqlite3.connect(
        str(
            destination_path
        )
    )

    try:
        source.backup(
            target
        )

    finally:
        target.close()
        source.close()


def schema_version(
    connection,
):
    return connection.execute(
        """
        SELECT COALESCE(
            MAX(version),
            0
        )
        FROM schema_migrations
        """
    ).fetchone()[0]


def index_names(
    connection,
):
    return {
        row[1]
        for row
        in connection.execute(
            """
            PRAGMA index_list(
                ranking_snapshots
            )
            """
        ).fetchall()
    }


def migration_smoke(
    base_db: Path,
):
    with tempfile.TemporaryDirectory(
        prefix="teddy-ranking-v5-"
    ) as temp:
        copied = (
            Path(temp)
            / "copied-v3.sqlite3"
        )

        sqlite_backup(
            base_db,
            copied,
        )

        connection = connect(
            copied
        )

        try:
            require(
                schema_version(
                    connection
                )
                == 3,
                "copied DB must start v3",
            )

            holdings_before = (
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM holdings
                    """
                ).fetchone()[0]
            )

            latest_before = (
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM latest_items
                    WHERE source =
                        'missav-release'
                    """
                ).fetchone()[0]
            )

            initialize(
                connection
            )

            require(
                schema_version(
                    connection
                )
                == 5,
                "v3 -> v5 migration failed",
            )

            ranking_columns = {
                row[
                    "name"
                ]
                for row
                in connection.execute(
                    """
                    PRAGMA table_info(
                        ranking_snapshots
                    )
                    """
                ).fetchall()
            }

            require(
                "period_label"
                in ranking_columns,
                "v5 period_label "
                "column missing",
            )

            indexes = (
                index_names(
                    connection
                )
            )

            require(
                "ux_ranking_period_dvd"
                in indexes,
                "DVD uniqueness index missing",
            )

            require(
                "ux_ranking_period_rank"
                in indexes,
                "rank uniqueness index missing",
            )

            holdings_after = (
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM holdings
                    """
                ).fetchone()[0]
            )

            latest_after = (
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM latest_items
                    WHERE source =
                        'missav-release'
                    """
                ).fetchone()[0]
            )

            require(
                holdings_after
                == holdings_before,
                "migration changed holdings",
            )

            require(
                latest_after
                == latest_before,
                "migration changed latest",
            )

            require(
                connection.execute(
                    "PRAGMA integrity_check"
                ).fetchone()[0]
                == "ok",
                "migrated DB integrity failed",
            )

        finally:
            connection.close()

    print(
        "SCHEMA_V3_TO_V5_SMOKE=PASS"
    )

    print(
        "RANKING_UNIQUE_INDEX_SMOKE=PASS"
    )

    print(
        "V5_EXISTING_DATA_PRESERVED_SMOKE=PASS"
    )


def duplicate_migration_fail_closed_smoke(
    base_db: Path,
):
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-ranking-v4-duplicate-"
    ) as temp:
        copied = (
            Path(temp)
            / "duplicate-v3.sqlite3"
        )

        sqlite_backup(
            base_db,
            copied,
        )

        raw = sqlite3.connect(
            copied
        )

        try:
            raw.execute(
                """
                INSERT INTO ranking_snapshots(
                    chart_type,
                    period,
                    dvd_id,
                    rank,
                    score,
                    observed_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    WEEKLY_CHART_TYPE,
                    "2099-W01",
                    "TEST-001",
                    1,
                    None,
                    "2099-01-01T00:00:00+00:00",
                ),
            )

            raw.execute(
                """
                INSERT INTO ranking_snapshots(
                    chart_type,
                    period,
                    dvd_id,
                    rank,
                    score,
                    observed_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    WEEKLY_CHART_TYPE,
                    "2099-W01",
                    "TEST-001",
                    2,
                    None,
                    "2099-01-01T00:00:00+00:00",
                ),
            )

            raw.commit()

        finally:
            raw.close()

        connection = connect(
            copied
        )

        try:
            try:
                initialize(
                    connection
                )

            except RuntimeError as exc:
                require(
                    "duplicate"
                    in str(exc),
                    "unexpected migration failure",
                )

            else:
                raise RuntimeError(
                    "duplicate v3 ranking "
                    "must block v4 migration"
                )

            require(
                schema_version(
                    connection
                )
                == 3,
                "failed migration "
                "advanced schema version",
            )

        finally:
            connection.close()

    print(
        "V4_DUPLICATE_MIGRATION_FAIL_CLOSED_SMOKE=PASS"
    )


def weekly_write_smoke(
    base_db: Path,
    fixture_path: Path,
):
    with fixture_path.open(
        "r",
        encoding="utf-8",
    ) as fh:
        forensic = json.load(
            fh
        )

    article = forensic[
        "article"
    ]

    parsed = (
        parse_javdatabase_weekly_envelope(
            article
        )
    )

    observed_at = article.get(
        "requested_at"
    )

    require(
        observed_at,
        "fixture requested_at missing",
    )

    with tempfile.TemporaryDirectory(
        prefix="teddy-weekly-write-"
    ) as temp:
        copied = (
            Path(temp)
            / "weekly-v5.sqlite3"
        )

        sqlite_backup(
            base_db,
            copied,
        )

        connection = connect(
            copied
        )

        try:
            initialize(
                connection
            )

            holdings_before = (
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM holdings
                    """
                ).fetchone()[0]
            )

            latest_before = (
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM latest_items
                    WHERE source =
                        'missav-release'
                    """
                ).fetchone()[0]
            )

            first = (
                replace_weekly_snapshot(
                    connection,
                    parsed,
                    observed_at=
                        observed_at,
                )
            )

            require(
                first[
                    "written"
                ]
                == 25,
                "first weekly write "
                "count changed",
            )

            rows = (
                list_weekly_snapshot(
                    connection,
                    parsed[
                        "period"
                    ],
                )
            )

            require(
                len(rows) == 25,
                "weekly row count changed",
            )

            expected_ids = [
                item[
                    "dvd_id"
                ]
                for item
                in parsed[
                    "items"
                ]
            ]

            stored_ids = [
                row[
                    "dvd_id"
                ]
                for row
                in rows
            ]

            require(
                stored_ids
                == expected_ids,
                "weekly DB order changed",
            )

            require(
                parsed.get(
                    "period_label"
                )
                == (
                    "13th – 19th "
                    "August 2026"
                ),
                "fixture period_label "
                "changed",
            )

            require(
                {
                    row[
                        "period_label"
                    ]
                    for row
                    in rows
                }
                == {
                    parsed[
                        "period_label"
                    ]
                },
                "weekly period_label "
                "was not persisted",
            )


            second = (
                replace_weekly_snapshot(
                    connection,
                    parsed,
                    observed_at=
                        observed_at,
                )
            )

            require(
                second[
                    "written"
                ]
                == 25,
                "second weekly write "
                "count changed",
            )

            count_after_second = (
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM ranking_snapshots
                    WHERE chart_type = ?
                      AND period = ?
                    """,
                    (
                        WEEKLY_CHART_TYPE,
                        parsed[
                            "period"
                        ],
                    ),
                ).fetchone()[0]
            )

            require(
                count_after_second
                == 25,
                "weekly idempotency failed",
            )

            duplicate_id = deepcopy(
                parsed
            )

            duplicate_id[
                "items"
            ][1][
                "dvd_id"
            ] = duplicate_id[
                "items"
            ][0][
                "dvd_id"
            ]

            try:
                replace_weekly_snapshot(
                    connection,
                    duplicate_id,
                    observed_at=
                        observed_at,
                )

            except ValueError:
                pass

            else:
                raise RuntimeError(
                    "duplicate weekly DVD "
                    "must fail validation"
                )

            duplicate_rank = deepcopy(
                parsed
            )

            duplicate_rank[
                "items"
            ][1][
                "rank"
            ] = 1

            try:
                replace_weekly_snapshot(
                    connection,
                    duplicate_rank,
                    observed_at=
                        observed_at,
                )

            except ValueError:
                pass

            else:
                raise RuntimeError(
                    "duplicate weekly rank "
                    "must fail validation"
                )

            still_rows = (
                list_weekly_snapshot(
                    connection,
                    parsed[
                        "period"
                    ],
                )
            )

            require(
                [
                    row[
                        "dvd_id"
                    ]
                    for row
                    in still_rows
                ]
                == expected_ids,
                "failed validation "
                "changed stored snapshot",
            )

            try:
                connection.execute(
                    "BEGIN IMMEDIATE"
                )

                connection.execute(
                    """
                    INSERT INTO ranking_snapshots(
                        chart_type,
                        period,
                        dvd_id,
                        rank,
                        score,
                        observed_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        WEEKLY_CHART_TYPE,
                        parsed[
                            "period"
                        ],
                        expected_ids[0],
                        99,
                        None,
                        observed_at,
                    ),
                )

            except sqlite3.IntegrityError:
                connection.rollback()

            else:
                connection.rollback()

                raise RuntimeError(
                    "DVD unique index "
                    "did not reject duplicate"
                )

            try:
                connection.execute(
                    "BEGIN IMMEDIATE"
                )

                connection.execute(
                    """
                    INSERT INTO ranking_snapshots(
                        chart_type,
                        period,
                        dvd_id,
                        rank,
                        score,
                        observed_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        WEEKLY_CHART_TYPE,
                        parsed[
                            "period"
                        ],
                        "TEST-999",
                        1,
                        None,
                        observed_at,
                    ),
                )

            except sqlite3.IntegrityError:
                connection.rollback()

            else:
                connection.rollback()

                raise RuntimeError(
                    "rank unique index "
                    "did not reject duplicate"
                )

            holdings_after = (
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM holdings
                    """
                ).fetchone()[0]
            )

            latest_after = (
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM latest_items
                    WHERE source =
                        'missav-release'
                    """
                ).fetchone()[0]
            )

            require(
                holdings_after
                == holdings_before,
                "weekly write "
                "changed holdings",
            )

            require(
                latest_after
                == latest_before,
                "weekly write "
                "changed latest",
            )

            require(
                connection.execute(
                    "PRAGMA integrity_check"
                ).fetchone()[0]
                == "ok",
                "weekly DB "
                "integrity failed",
            )

        finally:
            connection.close()

    print(
        "WEEK33_TEMP_DB_WRITE_SMOKE=PASS"
    )

    print(
        "WEEKLY_PERIOD_LABEL_STORAGE_SMOKE=PASS"
    )

    print(
        "WEEKLY_SNAPSHOT_IDEMPOTENCY_SMOKE=PASS"
    )

    print(
        "WEEKLY_VALIDATION_FAIL_CLOSED_SMOKE=PASS"
    )

    print(
        "WEEKLY_UNIQUE_CONSTRAINT_SMOKE=PASS"
    )

    print(
        "WEEKLY_EXISTING_DATA_PRESERVED_SMOKE=PASS"
    )


def main():
    if len(
        sys.argv
    ) != 3:
        raise RuntimeError(
            "usage: "
            "teddy_discovery_rankings_smoke.py "
            "<stage2-v3-db> "
            "<javdatabase-forensic-json>"
        )

    base_db = Path(
        sys.argv[1]
    )

    fixture = Path(
        sys.argv[2]
    )

    migration_smoke(
        base_db
    )

    duplicate_migration_fail_closed_smoke(
        base_db
    )

    weekly_write_smoke(
        base_db,
        fixture,
    )

    print(
        "RANKING_DB_V5_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
