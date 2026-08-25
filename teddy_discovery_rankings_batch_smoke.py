from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

import teddy_discovery_rankings as rankings


EXPECTED_PERIODS = [
    "2026-W30",
    "2026-W31",
    "2026-W32",
]


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
        destination_path
    )

    try:
        source.backup(
            target
        )

    finally:
        target.close()
        source.close()


def connect(
    path: Path,
):
    connection = sqlite3.connect(
        path
    )

    connection.row_factory = (
        sqlite3.Row
    )

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    return connection


def digest_rows(
    connection,
    sql,
    params=(),
):
    rows = [
        dict(row)
        for row
        in connection.execute(
            sql,
            params,
        ).fetchall()
    ]

    payload = json.dumps(
        rows,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode(
        "utf-8"
    )

    return hashlib.sha256(
        payload
    ).hexdigest()


def db_logical_digest(
    connection,
):
    tables = [
        "genres",
        "holdings",
        "latest_items",
        "people",
        "ranking_snapshots",
        "title_genres",
        "title_people",
        "titles",
    ]

    parts = []

    for table in tables:
        rows = [
            tuple(row)
            for row
            in connection.execute(
                "SELECT * FROM "
                + table
                + " ORDER BY rowid"
            ).fetchall()
        ]

        parts.append({
            "table":
                table,

            "rows":
                rows,
        })

    payload = json.dumps(
        parts,
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    ).encode(
        "utf-8"
    )

    return hashlib.sha256(
        payload
    ).hexdigest()


def load_entries(
    path: Path,
):
    with path.open(
        "r",
        encoding="utf-8",
    ) as fh:
        value = json.load(
            fh
        )

    articles = value.get(
        "articles"
    )

    require(
        isinstance(
            articles,
            list,
        )
        and len(articles) == 3,
        "expected exactly 3 "
        "backfill articles",
    )

    entries = []

    for article in articles:
        entries.append({
            "snapshot":
                article[
                    "snapshot"
                ],

            "observed_at":
                article[
                    "article"
                ][
                    "requested_at"
                ],
        })

    require(
        [
            entry[
                "snapshot"
            ][
                "period"
            ]
            for entry
            in entries
        ]
        == EXPECTED_PERIODS,
        "backfill periods changed",
    )

    return entries


def metadata_fingerprint(
    connection,
    dvd_id,
):
    title = connection.execute(
        """
        SELECT *
        FROM titles
        WHERE dvd_id = ?
        """,
        (
            dvd_id,
        ),
    ).fetchone()

    people = connection.execute(
        """
        SELECT
            p.name,
            tp.role
        FROM title_people AS tp
        JOIN people AS p
          ON p.person_id =
             tp.person_id
        WHERE tp.dvd_id = ?
        ORDER BY
            p.name,
            tp.role
        """,
        (
            dvd_id,
        ),
    ).fetchall()

    genres = connection.execute(
        """
        SELECT g.name
        FROM title_genres AS tg
        JOIN genres AS g
          ON g.genre_id =
             tg.genre_id
        WHERE tg.dvd_id = ?
        ORDER BY g.name
        """,
        (
            dvd_id,
        ),
    ).fetchall()

    return {
        "title":
            (
                dict(title)
                if title is not None
                else None
            ),

        "people":
            [
                tuple(row)
                for row
                in people
            ],

        "genres":
            [
                tuple(row)
                for row
                in genres
            ],
    }


def period_from_raw(
    raw_metadata,
):
    value = json.loads(
        raw_metadata
    )

    return value[
        "period"
    ]


def successful_batch_smoke(
    stage3_db: Path,
    entries,
):
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-weekly-batch-success-"
    ) as temp:
        db_path = (
            Path(temp)
            / "discovery.sqlite3"
        )

        sqlite_backup(
            stage3_db,
            db_path,
        )

        connection = connect(
            db_path
        )

        try:
            week33_ids = {
                row[
                    "dvd_id"
                ]
                for row
                in connection.execute(
                    """
                    SELECT dvd_id
                    FROM ranking_snapshots
                    WHERE chart_type =
                        'javdatabase-weekly'
                      AND period =
                        '2026-W33'
                    """
                ).fetchall()
            }

            historical = defaultdict(
                list
            )

            for entry in entries:
                period = entry[
                    "snapshot"
                ][
                    "period"
                ]

                for item in entry[
                    "snapshot"
                ][
                    "items"
                ]:
                    historical[
                        item[
                            "dvd_id"
                        ]
                    ].append(
                        period
                    )

            overlaps = sorted(
                set(
                    historical
                )
                & week33_ids
            )

            require(
                len(
                    overlaps
                )
                == 11,
                "expected 11 W33 overlaps",
            )

            before_overlap = {
                dvd_id:
                    metadata_fingerprint(
                        connection,
                        dvd_id,
                    )

                for dvd_id
                in overlaps
            }

            latest_before = digest_rows(
                connection,
                """
                SELECT *
                FROM latest_items
                ORDER BY
                    source,
                    dvd_id
                """,
            )

            holdings_before = digest_rows(
                connection,
                """
                SELECT *
                FROM holdings
                ORDER BY holding_id
                """,
            )

            titles_before = (
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM titles
                    """
                ).fetchone()[0]
            )

            existing_title_ids = {
                row[
                    "dvd_id"
                ]
                for row
                in connection.execute(
                    """
                    SELECT dvd_id
                    FROM titles
                    """
                ).fetchall()
            }

            result = (
                rankings
                .replace_weekly_snapshots_batch(
                    connection,
                    deepcopy(
                        entries
                    ),
                )
            )

            require(
                result[
                    "periods"
                ]
                == EXPECTED_PERIODS,
                "batch period order changed",
            )

            require(
                result[
                    "snapshots"
                ]
                == 3,
                "batch snapshot count changed",
            )

            require(
                result[
                    "written"
                ]
                == 75,
                "batch write count changed",
            )

            stored = connection.execute(
                """
                SELECT
                    period,
                    COUNT(*) AS row_count
                FROM ranking_snapshots
                WHERE chart_type =
                    'javdatabase-weekly'
                GROUP BY period
                ORDER BY period
                """
            ).fetchall()

            require(
                [
                    (
                        row[
                            "period"
                        ],
                        row[
                            "row_count"
                        ],
                    )
                    for row
                    in stored
                ]
                == [
                    (
                        "2026-W30",
                        25,
                    ),
                    (
                        "2026-W31",
                        25,
                    ),
                    (
                        "2026-W32",
                        25,
                    ),
                    (
                        "2026-W33",
                        25,
                    ),
                ],
                "four Weekly snapshots "
                "not stored exactly",
            )

            for dvd_id in overlaps:
                require(
                    metadata_fingerprint(
                        connection,
                        dvd_id,
                    )
                    == before_overlap[
                        dvd_id
                    ],
                    (
                        "older Weekly backfill "
                        "changed W33 metadata: "
                        + dvd_id
                    ),
                )

            for dvd_id, periods in (
                historical.items()
            ):
                row = connection.execute(
                    """
                    SELECT
                        metadata_source,
                        raw_metadata
                    FROM titles
                    WHERE dvd_id = ?
                    """,
                    (
                        dvd_id,
                    ),
                ).fetchone()

                require(
                    row is not None,
                    "historical title missing",
                )

                require(
                    row[
                        "metadata_source"
                    ]
                    == "javdatabase-weekly",
                    "historical metadata "
                    "source changed",
                )

                expected_period = (
                    "2026-W33"
                    if dvd_id
                    in week33_ids
                    else max(
                        periods
                    )
                )

                actual_period = (
                    period_from_raw(
                        row[
                            "raw_metadata"
                        ]
                    )
                )

                require(
                    actual_period
                    == expected_period,
                    (
                        "metadata freshness "
                        "period mismatch: "
                        + dvd_id
                        + " expected="
                        + expected_period
                        + " actual="
                        + actual_period
                    ),
                )

            newly_seen = (
                set(
                    historical
                )
                - existing_title_ids
            )

            titles_after = (
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM titles
                    """
                ).fetchone()[0]
            )

            require(
                titles_after
                == titles_before
                + len(
                    newly_seen
                ),
                "historical title insert "
                "count changed",
            )

            require(
                digest_rows(
                    connection,
                    """
                    SELECT *
                    FROM latest_items
                    ORDER BY
                        source,
                        dvd_id
                    """,
                )
                == latest_before,
                "batch changed Latest",
            )

            require(
                digest_rows(
                    connection,
                    """
                    SELECT *
                    FROM holdings
                    ORDER BY holding_id
                    """,
                )
                == holdings_before,
                "batch changed holdings",
            )

            integrity = (
                connection.execute(
                    "PRAGMA integrity_check"
                ).fetchone()[0]
            )

            require(
                integrity == "ok",
                "batch DB integrity failed",
            )

            #
            # Same exact batch must remain
            # idempotent.
            #
            second = (
                rankings
                .replace_weekly_snapshots_batch(
                    connection,
                    deepcopy(
                        entries
                    ),
                )
            )

            require(
                second[
                    "written"
                ]
                == 75,
                "batch idempotent write "
                "count changed",
            )

            stored_after_second = (
                connection.execute(
                    """
                    SELECT
                        period,
                        COUNT(*) AS row_count
                    FROM ranking_snapshots
                    WHERE chart_type =
                        'javdatabase-weekly'
                    GROUP BY period
                    ORDER BY period
                    """
                ).fetchall()
            )

            require(
                [
                    (
                        row[
                            "period"
                        ],
                        row[
                            "row_count"
                        ],
                    )
                    for row
                    in stored_after_second
                ]
                == [
                    (
                        "2026-W30",
                        25,
                    ),
                    (
                        "2026-W31",
                        25,
                    ),
                    (
                        "2026-W32",
                        25,
                    ),
                    (
                        "2026-W33",
                        25,
                    ),
                ],
                "batch idempotency "
                "changed ranking rows",
            )

        finally:
            connection.close()

    print(
        "BATCH_W30_W32_SUCCESS_SMOKE=PASS"
    )

    print(
        "NEWER_W33_METADATA_PRESERVED_SMOKE=PASS"
    )

    print(
        "HISTORICAL_LATEST_PERIOD_WINS_SMOKE=PASS"
    )

    print(
        "BATCH_LATEST_UNCHANGED_SMOKE=PASS"
    )

    print(
        "BATCH_HOLDINGS_UNCHANGED_SMOKE=PASS"
    )

    print(
        "BATCH_IDEMPOTENCY_SMOKE=PASS"
    )


def rollback_smoke(
    stage3_db: Path,
    entries,
):
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-weekly-batch-rollback-"
    ) as temp:
        db_path = (
            Path(temp)
            / "discovery.sqlite3"
        )

        sqlite_backup(
            stage3_db,
            db_path,
        )

        connection = connect(
            db_path
        )

        before = db_logical_digest(
            connection
        )

        original = (
            rankings
            ._upsert_weekly_metadata
        )

        def injected(
            connection,
            item,
            period,
            observed_at,
        ):
            if (
                period == "2026-W31"
                and item[
                    "rank"
                ] == 1
            ):
                raise RuntimeError(
                    "injected batch failure"
                )

            return original(
                connection,
                item,
                period,
                observed_at,
            )

        rankings._upsert_weekly_metadata = (
            injected
        )

        try:
            try:
                rankings.replace_weekly_snapshots_batch(
                    connection,
                    deepcopy(
                        entries
                    ),
                )

            except RuntimeError as exc:
                require(
                    "injected batch failure"
                    in str(exc),
                    "unexpected injected "
                    "failure result",
                )

            else:
                raise RuntimeError(
                    "injected batch failure "
                    "did not fail"
                )

        finally:
            rankings._upsert_weekly_metadata = (
                original
            )

        after = db_logical_digest(
            connection
        )

        require(
            after == before,
            "failed batch left "
            "partial DB changes",
        )

        periods = connection.execute(
            """
            SELECT
                period,
                COUNT(*) AS row_count
            FROM ranking_snapshots
            WHERE chart_type =
                'javdatabase-weekly'
            GROUP BY period
            ORDER BY period
            """
        ).fetchall()

        require(
            [
                (
                    row[
                        "period"
                    ],
                    row[
                        "row_count"
                    ],
                )
                for row
                in periods
            ]
            == [
                (
                    "2026-W33",
                    25,
                ),
            ],
            "failed batch left "
            "partial historical rankings",
        )

        connection.close()

    print(
        "BATCH_MIDSTREAM_ATOMIC_ROLLBACK_SMOKE=PASS"
    )


def prevalidation_smoke(
    stage3_db: Path,
    entries,
):
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-weekly-batch-validation-"
    ) as temp:
        db_path = (
            Path(temp)
            / "discovery.sqlite3"
        )

        sqlite_backup(
            stage3_db,
            db_path,
        )

        connection = connect(
            db_path
        )

        before = db_logical_digest(
            connection
        )

        broken = deepcopy(
            entries
        )

        broken[1][
            "snapshot"
        ][
            "items"
        ][0][
            "rank"
        ] = 2

        try:
            rankings.replace_weekly_snapshots_batch(
                connection,
                broken,
            )

        except ValueError:
            pass

        else:
            raise RuntimeError(
                "invalid batch must "
                "fail before write"
            )

        require(
            db_logical_digest(
                connection
            )
            == before,
            "validation failure "
            "changed DB",
        )

        duplicate = [
            deepcopy(
                entries[0]
            ),
            deepcopy(
                entries[0]
            ),
        ]

        try:
            rankings.replace_weekly_snapshots_batch(
                connection,
                duplicate,
            )

        except ValueError as exc:
            require(
                "duplicate weekly "
                "batch period"
                in str(exc),
                "unexpected duplicate "
                "period failure",
            )

        else:
            raise RuntimeError(
                "duplicate batch period "
                "must fail"
            )

        require(
            db_logical_digest(
                connection
            )
            == before,
            "duplicate period failure "
            "changed DB",
        )

        connection.close()

    print(
        "BATCH_PREVALIDATION_FAIL_CLOSED_SMOKE=PASS"
    )

    print(
        "BATCH_DUPLICATE_PERIOD_FAIL_CLOSED_SMOKE=PASS"
    )


def malformed_provenance_smoke(
    stage3_db: Path,
    entries,
):
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-weekly-provenance-"
    ) as temp:
        db_path = (
            Path(temp)
            / "discovery.sqlite3"
        )

        sqlite_backup(
            stage3_db,
            db_path,
        )

        connection = connect(
            db_path
        )

        #
        # Choose an overlap proven to be
        # present in both W32 and W33.
        #
        connection.execute(
            """
            UPDATE titles
            SET raw_metadata = ?
            WHERE dvd_id = ?
            """,
            (
                "{broken-json",
                "SNOS-299",
            ),
        )

        connection.commit()

        before = db_logical_digest(
            connection
        )

        try:
            rankings.replace_weekly_snapshots_batch(
                connection,
                deepcopy(
                    entries
                ),
            )

        except RuntimeError as exc:
            require(
                "provenance malformed"
                in str(exc),
                "unexpected malformed "
                "provenance failure",
            )

        else:
            raise RuntimeError(
                "malformed Weekly provenance "
                "must fail closed"
            )

        require(
            db_logical_digest(
                connection
            )
            == before,
            "malformed provenance "
            "failure changed DB",
        )

        connection.close()

    print(
        "MALFORMED_WEEKLY_PROVENANCE_FAIL_CLOSED_SMOKE=PASS"
    )


def main():
    if len(
        sys.argv
    ) != 3:
        raise RuntimeError(
            "usage: "
            "teddy_discovery_"
            "rankings_batch_smoke.py "
            "<stage3-db> "
            "<live-backfill-json>"
        )

    stage3_db = Path(
        sys.argv[1]
    )

    backfill = Path(
        sys.argv[2]
    )

    entries = load_entries(
        backfill
    )

    successful_batch_smoke(
        stage3_db,
        entries,
    )

    rollback_smoke(
        stage3_db,
        entries,
    )

    prevalidation_smoke(
        stage3_db,
        entries,
    )

    malformed_provenance_smoke(
        stage3_db,
        entries,
    )

    print(
        "WEEKLY_BATCH_FRESHNESS_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
