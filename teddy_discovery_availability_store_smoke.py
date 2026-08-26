from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
    timezone,
)
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

from teddy_discovery_availability import (
    SOURCE_123AV,
    SOURCE_MISSAV,
    STATUS_FOUND,
    STATUS_NOT_FOUND,
    STATUS_UNKNOWN,
    canonical_page_url,
)

from teddy_discovery_availability_store import (
    persist_availability_result,
    read_availability_cache,
)


BASE_TIME = datetime(
    2026,
    8,
    25,
    15,
    0,
    0,
    tzinfo=timezone.utc,
)


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


def iso(
    value,
):
    return (
        value.astimezone(
            timezone.utc
        )
        .replace(
            microsecond=0
        )
        .isoformat()
    )


def result(
    source,
    dvd_id,
    status,
):
    return {
        "source":
            source,

        "dvd_id":
            dvd_id,

        "page_url":
            canonical_page_url(
                source,
                dvd_id,
            ),

        "status":
            status,
    }


def clone_db(
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


def connect(
    path: Path,
):
    connection = sqlite3.connect(
        path
    )

    connection.row_factory = (
        sqlite3.Row
    )

    return connection


def availability_digest(
    connection,
):
    rows = [
        tuple(row)
        for row
        in connection.execute(
            """
            SELECT
                dvd_id,
                source,
                status,
                page_url,
                last_checked_at,
                next_check_at,
                fail_count
            FROM availability
            ORDER BY
                dvd_id,
                source
            """
        ).fetchall()
    ]

    return hashlib.sha256(
        json.dumps(
            rows,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode(
            "utf-8"
        )
    ).hexdigest()


def cache_miss_smoke(
    connection,
):
    value = read_availability_cache(
        connection,
        source=SOURCE_MISSAV,
        dvd_id="JUR-821",
        now=iso(
            BASE_TIME
        ),
    )

    require(
        value[
            "known"
        ]
        is False,
        "cache miss must not be known",
    )

    require(
        value[
            "due"
        ]
        is True,
        "cache miss must be due",
    )

    require(
        value[
            "status"
        ]
        == STATUS_UNKNOWN,
        "cache miss status changed",
    )

    require(
        value[
            "fail_count"
        ]
        == 0,
        "cache miss fail_count changed",
    )

    print(
        "AVAILABILITY_CACHE_MISS_SMOKE=PASS"
    )


def success_recheck_smoke(
    connection,
):
    stored = persist_availability_result(
        connection,
        result(
            SOURCE_MISSAV,
            "JUR-821",
            STATUS_FOUND,
        ),
        checked_at=iso(
            BASE_TIME
        ),
    )

    require(
        stored[
            "fail_count"
        ]
        == 0,
        "FOUND fail_count changed",
    )

    require(
        stored[
            "next_check_at"
        ]
        == iso(
            BASE_TIME
            + timedelta(
                days=7
            )
        ),
        "FOUND weekly recheck changed",
    )

    before_due = read_availability_cache(
        connection,
        source=SOURCE_MISSAV,
        dvd_id="JUR-821",
        now=iso(
            BASE_TIME
            + timedelta(
                days=6,
                hours=23,
                minutes=59,
            )
        ),
    )

    require(
        before_due[
            "due"
        ]
        is False,
        "FOUND cache became due early",
    )

    exactly_due = read_availability_cache(
        connection,
        source=SOURCE_MISSAV,
        dvd_id="JUR-821",
        now=iso(
            BASE_TIME
            + timedelta(
                days=7
            )
        ),
    )

    require(
        exactly_due[
            "due"
        ]
        is True,
        "FOUND cache exact due "
        "boundary changed",
    )

    print(
        "AVAILABILITY_SUCCESS_WEEKLY_RECHECK_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_DUE_BOUNDARY_SMOKE=PASS"
    )


def unknown_backoff_smoke(
    connection,
):
    source = SOURCE_123AV
    dvd_id = "JUR-821"

    schedule = [
        (
            BASE_TIME,
            1,
            1,
        ),
        (
            BASE_TIME
            + timedelta(
                days=1
            ),
            2,
            2,
        ),
        (
            BASE_TIME
            + timedelta(
                days=3
            ),
            3,
            4,
        ),
        (
            BASE_TIME
            + timedelta(
                days=7
            ),
            4,
            7,
        ),
        (
            BASE_TIME
            + timedelta(
                days=14
            ),
            5,
            7,
        ),
    ]

    for (
        checked,
        expected_fail_count,
        expected_delay,
    ) in schedule:
        stored = persist_availability_result(
            connection,
            result(
                source,
                dvd_id,
                STATUS_UNKNOWN,
            ),
            checked_at=iso(
                checked
            ),
        )

        require(
            stored[
                "fail_count"
            ]
            == expected_fail_count,
            (
                "UNKNOWN fail_count changed "
                + str(
                    expected_fail_count
                )
            ),
        )

        require(
            stored[
                "next_check_at"
            ]
            == iso(
                checked
                + timedelta(
                    days=expected_delay
                )
            ),
            (
                "UNKNOWN backoff changed "
                + str(
                    expected_fail_count
                )
            ),
        )

    print(
        "AVAILABILITY_UNKNOWN_1_2_4_7_BACKOFF_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_UNKNOWN_WEEKLY_CAP_SMOKE=PASS"
    )


def success_reset_smoke(
    connection,
):
    checked = (
        BASE_TIME
        + timedelta(
            days=21
        )
    )

    stored = persist_availability_result(
        connection,
        result(
            SOURCE_123AV,
            "JUR-821",
            STATUS_FOUND,
        ),
        checked_at=iso(
            checked
        ),
    )

    require(
        stored[
            "fail_count"
        ]
        == 0,
        "FOUND did not reset "
        "UNKNOWN fail_count",
    )

    require(
        stored[
            "next_check_at"
        ]
        == iso(
            checked
            + timedelta(
                days=7
            )
        ),
        "post-reset weekly check changed",
    )

    checked_404 = (
        checked
        + timedelta(
            days=7
        )
    )

    stored_404 = persist_availability_result(
        connection,
        result(
            SOURCE_123AV,
            "JUR-821",
            STATUS_NOT_FOUND,
        ),
        checked_at=iso(
            checked_404
        ),
    )

    require(
        stored_404[
            "fail_count"
        ]
        == 0,
        "NOT_FOUND fail_count changed",
    )

    require(
        stored_404[
            "next_check_at"
        ]
        == iso(
            checked_404
            + timedelta(
                days=7
            )
        ),
        "NOT_FOUND weekly "
        "recheck changed",
    )

    count = connection.execute(
        """
        SELECT COUNT(*)
        FROM availability
        WHERE dvd_id = ?
          AND source = ?
        """,
        (
            "JUR-821",
            SOURCE_123AV,
        ),
    ).fetchone()[0]

    require(
        count == 1,
        "availability upsert created "
        "duplicate cache rows",
    )

    print(
        "AVAILABILITY_SUCCESS_RESETS_FAILURES_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_NOT_FOUND_WEEKLY_RECHECK_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_UPSERT_IDEMPOTENCY_SMOKE=PASS"
    )


def prevalidation_fail_closed_smoke(
    connection,
):
    before = availability_digest(
        connection
    )

    invalid = result(
        SOURCE_MISSAV,
        "SDNM-560",
        STATUS_FOUND,
    )

    invalid[
        "status"
    ] = "BROKEN"

    try:
        persist_availability_result(
            connection,
            invalid,
            checked_at=iso(
                BASE_TIME
            ),
        )

    except ValueError:
        pass

    else:
        raise RuntimeError(
            "invalid status must "
            "fail closed"
        )

    after = availability_digest(
        connection
    )

    require(
        after == before,
        "prevalidation failure "
        "changed availability cache",
    )

    try:
        persist_availability_result(
            connection,
            result(
                SOURCE_MISSAV,
                "SDNM-560",
                STATUS_FOUND,
            ),
            checked_at=(
                "2026-08-25T15:00:00"
            ),
        )

    except ValueError:
        pass

    else:
        raise RuntimeError(
            "naive checked_at "
            "must fail closed"
        )

    require(
        availability_digest(
            connection
        )
        == before,
        "invalid timestamp "
        "changed availability cache",
    )

    print(
        "AVAILABILITY_PREVALIDATION_FAIL_CLOSED_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_TIMEZONE_REQUIRED_SMOKE=PASS"
    )


def rollback_after_begin_smoke(
    connection,
):
    dvd_id = "SDNM-560"
    source = SOURCE_MISSAV

    connection.execute(
        """
        INSERT INTO availability(
            dvd_id,
            source,
            status,
            page_url,
            last_checked_at,
            next_check_at,
            fail_count
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            dvd_id,
            source,
            STATUS_UNKNOWN,
            canonical_page_url(
                source,
                dvd_id,
            ),
            iso(
                BASE_TIME
            ),
            iso(
                BASE_TIME
                + timedelta(
                    days=1
                )
            ),
            -1,
        ),
    )

    connection.commit()

    before = availability_digest(
        connection
    )

    try:
        persist_availability_result(
            connection,
            result(
                source,
                dvd_id,
                STATUS_UNKNOWN,
            ),
            checked_at=iso(
                BASE_TIME
                + timedelta(
                    days=1
                )
            ),
        )

    except RuntimeError as exc:
        require(
            "fail_count"
            in str(exc),
            "unexpected rollback "
            "failure reason",
        )

    else:
        raise RuntimeError(
            "corrupt stored fail_count "
            "must fail"
        )

    after = availability_digest(
        connection
    )

    require(
        after == before,
        "transaction rollback failed"
    )

    require(
        connection.in_transaction
        is False,
        "failed persistence left "
        "transaction open",
    )

    print(
        "AVAILABILITY_TRANSACTION_ROLLBACK_SMOKE=PASS"
    )


def transaction_ownership_smoke(
    connection,
):
    connection.execute(
        "BEGIN"
    )

    try:
        try:
            persist_availability_result(
                connection,
                result(
                    SOURCE_MISSAV,
                    "JUR-786",
                    STATUS_FOUND,
                ),
                checked_at=iso(
                    BASE_TIME
                ),
            )

        except RuntimeError as exc:
            require(
                "transaction-free"
                in str(exc),
                "unexpected nested "
                "transaction failure",
            )

        else:
            raise RuntimeError(
                "nested transaction "
                "must fail closed"
            )

    finally:
        connection.rollback()

    print(
        "AVAILABILITY_TRANSACTION_OWNERSHIP_SMOKE=PASS"
    )


def main():
    if len(
        sys.argv
    ) != 2:
        raise RuntimeError(
            "usage: "
            "teddy_discovery_availability_store_smoke.py "
            "<real-stage4-db>"
        )

    source_db = Path(
        sys.argv[1]
    )

    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-availability-store-"
    ) as temp:
        temp_db = (
            Path(temp)
            / "availability.sqlite3"
        )

        clone_db(
            source_db,
            temp_db,
        )

        connection = connect(
            temp_db
        )

        try:
            initial = connection.execute(
                """
                SELECT COUNT(*)
                FROM availability
                """
            ).fetchone()[0]

            require(
                initial == 0,
                "temp availability "
                "must start empty",
            )

            cache_miss_smoke(
                connection
            )

            success_recheck_smoke(
                connection
            )

            unknown_backoff_smoke(
                connection
            )

            success_reset_smoke(
                connection
            )

            prevalidation_fail_closed_smoke(
                connection
            )

            rollback_after_begin_smoke(
                connection
            )

            transaction_ownership_smoke(
                connection
            )

            integrity = connection.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]

            require(
                integrity == "ok",
                "temp DB integrity failed",
            )

        finally:
            connection.close()

    print(
        "AVAILABILITY_TEMP_DB_ONLY_SMOKE=PASS"
    )

    print(
        "TEDDY_AVAILABILITY_STORE_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
