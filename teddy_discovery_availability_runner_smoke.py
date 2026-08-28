from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import sys

from teddy_discovery_availability import (
    STATUS_FOUND,
    STATUS_NOT_FOUND,
    STATUS_UNKNOWN,
    canonical_page_url,
)

from teddy_discovery_availability_batch import (
    build_due_request_plan,
)

from teddy_discovery_availability_runner import (
    collect_batch_artifact,
    replay_batch_artifact,
    validate_batch_artifact,
)


NOW = (
    "2026-08-26T12:08:00+00:00"
)

CURRENT_OBSERVED = (
    "2026-08-26T12:10:00+00:00"
)

STALE_OBSERVED = (
    "2026-08-26T12:09:00+00:00"
)


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


def connect_ro(
    path: Path,
):
    connection = sqlite3.connect(
        "file:"
        + str(path)
        + "?mode=ro",
        uri=True,
    )

    connection.row_factory = sqlite3.Row

    return connection


class FakeCollector:
    def __init__(
        self,
        statuses,
    ):
        self.statuses = list(
            statuses
        )
        self.calls = []

    def __call__(
        self,
        *,
        source,
        dvd_id,
    ):
        number = len(
            self.calls
        )

        if number >= len(
            self.statuses
        ):
            raise RuntimeError(
                "fake collector "
                "received extra request"
            )

        status = self.statuses[
            number
        ]

        self.calls.append(
            (
                source,
                dvd_id,
            )
        )

        url = canonical_page_url(
            source,
            dvd_id,
        )

        if status == STATUS_FOUND:
            http_status = 200
            reason = (
                "page-identity-match"
            )
            error = None
            body_bytes = 1000

        elif status == STATUS_NOT_FOUND:
            http_status = 404
            reason = "http-404"
            error = None
            body_bytes = 500

        elif status == STATUS_UNKNOWN:
            http_status = None
            reason = "request-error"
            error = (
                "TimeoutError: fake"
            )
            body_bytes = 0

        else:
            raise RuntimeError(
                "fake status invalid"
            )

        return {
            "source":
                source,

            "dvd_id":
                dvd_id,

            "page_url":
                url,

            "route":
                "fixed-vpn",

            "request_attempts":
                1,

            "redirects_followed":
                0,

            "media_requests":
                0,

            "http_status":
                http_status,

            "content_type":
                (
                    None
                    if http_status is None
                    else "text/html"
                ),

            "effective_url":
                (
                    None
                    if http_status is None
                    else url
                ),

            "location":
                None,

            "error":
                error,

            "body_bytes":
                body_bytes,

            "classification":
                {
                    "status":
                        status,

                    "reason":
                        reason,
                },
        }


class FakeSleeper:
    def __init__(
        self,
    ):
        self.calls = []

    def __call__(
        self,
        seconds,
    ):
        self.calls.append(
            seconds
        )


def build_test_artifact(
    db_path: Path,
    *,
    observed_at: str,
):
    collector = FakeCollector(
        [
            STATUS_FOUND,
            STATUS_NOT_FOUND,
            STATUS_FOUND,
            STATUS_UNKNOWN,
            STATUS_FOUND,
        ]
    )

    sleeper = FakeSleeper()

    connection = connect_ro(
        db_path
    )

    try:
        artifact = collect_batch_artifact(
            connection,
            now=NOW,
            observed_at=observed_at,
            max_requests=5,
            inter_request_delay_seconds=1,
            stop_on_unknown=True,
            collector=collector,
            sleeper=sleeper,
        )

    finally:
        connection.close()

    return (
        artifact,
        collector,
        sleeper,
    )


def real_baseline_smoke(
    db_path: Path,
):
    connection = connect_ro(
        db_path
    )

    try:
        total = connection.execute(
            """
            SELECT COUNT(*)
            FROM availability
            """
        ).fetchone()[0]

        groups = [
            tuple(row)
            for row
            in connection.execute(
                """
                SELECT
                    source,
                    status,
                    COUNT(*)
                FROM availability
                GROUP BY
                    source,
                    status
                ORDER BY
                    source,
                    status
                """
            ).fetchall()
        ]

        plan = build_due_request_plan(
            connection,
            now=NOW,
            max_requests=20,
        )

        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

    finally:
        connection.close()

    require(
        total == 32,
        "real availability "
        "baseline changed",
    )

    require(
        groups
        == [
            (
                "123av",
                "FOUND",
                16,
            ),
            (
                "missav",
                "FOUND",
                16,
            ),
        ],
        "real availability "
        "groups changed",
    )

    require(
        plan[
            "due_count"
        ]
        == 101,
        "real R2 due count changed",
    )

    require(
        plan[
            "fresh_count"
        ]
        == 16,
        "real R2 fresh count changed",
    )

    require(
        plan[
            "fallback_deferred_count"
        ]
        == 117,
        "real R2 fallback deferred count changed",
    )

    require(
        plan[
            "selected"
        ][0][
            "source"
        ]
        == "missav",
        "real R2 next source changed",
    )

    require(
        plan[
            "selected"
        ][0][
            "dvd_id"
        ]
        == "EROFV-387",
        "real R2 next dvd_id changed",
    )

    require(
        integrity == "ok",
        "real DB integrity failed",
    )

    print(
        "AVAILABILITY_RUNNER_REAL_BASELINE_SMOKE=PASS"
    )


def collection_smoke(
    db_path: Path,
):
    (
        artifact,
        collector,
        sleeper,
    ) = build_test_artifact(
        db_path,
        observed_at=
            CURRENT_OBSERVED,
    )

    validate_batch_artifact(
        artifact
    )

    require(
        artifact[
            "planned_count"
        ]
        == 5,
        "runner planned count changed",
    )

    require(
        artifact[
            "completed_count"
        ]
        == 4,
        "runner circuit-break "
        "count changed",
    )

    require(
        artifact[
            "aborted_on_unknown"
        ]
        is True,
        "runner UNKNOWN "
        "circuit breaker changed",
    )

    require(
        artifact[
            "status_counts"
        ]
        == {
            "FOUND":
                2,

            "NOT_FOUND":
                1,

            "UNKNOWN":
                1,
        },
        "runner status distribution changed",
    )

    require(
        len(
            collector.calls
        )
        == 4,
        "runner made request "
        "after UNKNOWN",
    )

    require(
        sleeper.calls
        == [
            1.0,
            1.0,
            1.0,
        ],
        "runner request delay changed",
    )

    print(
        "AVAILABILITY_RUNNER_CIRCUIT_BREAKER_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_RUNNER_ARTIFACT_VALIDATION_SMOKE=PASS"
    )

    return artifact


def copy_db(
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


def replay_idempotency_smoke(
    db_path: Path,
    artifact,
):
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-availability-runner-"
    ) as temp:
        temp_db = (
            Path(temp)
            / "teddy-discovery.sqlite3"
        )

        copy_db(
            db_path,
            temp_db,
        )

        first = replay_batch_artifact(
            temp_db,
            artifact,
        )

        require(
            first[
                "completed_count"
            ]
            == 4,
            "first replay completed "
            "count changed",
        )

        require(
            first[
                "applied_count"
            ]
            == 4,
            "first replay applied "
            "count changed",
        )

        require(
            first[
                "already_applied_count"
            ]
            == 0,
            "first replay already-applied "
            "count changed",
        )

        connection = connect_ro(
            temp_db
        )

        try:
            total_after_first = (
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM availability
                    """
                ).fetchone()[0]
            )

            unknown_item = next(
                item
                for item
                in artifact[
                    "results"
                ]
                if item[
                    "classification_status"
                ] == STATUS_UNKNOWN
            )

            unknown_row = (
                connection.execute(
                    """
                    SELECT
                        status,
                        fail_count,
                        last_checked_at
                    FROM availability
                    WHERE dvd_id = ?
                      AND source = ?
                    """,
                    (
                        unknown_item[
                            "dvd_id"
                        ],
                        unknown_item[
                            "source"
                        ],
                    ),
                ).fetchone()
            )

        finally:
            connection.close()

        require(
            total_after_first == 36,
            "first temp replay "
            "row count changed",
        )

        require(
            unknown_row[
                "status"
            ] == STATUS_UNKNOWN,
            "UNKNOWN replay "
            "status changed",
        )

        require(
            unknown_row[
                "fail_count"
            ] == 1,
            "first UNKNOWN replay "
            "fail_count changed",
        )

        require(
            unknown_row[
                "last_checked_at"
            ] == CURRENT_OBSERVED,
            "UNKNOWN replay "
            "timestamp changed",
        )

        second = replay_batch_artifact(
            temp_db,
            artifact,
        )

        require(
            second[
                "applied_count"
            ]
            == 0,
            "second replay must "
            "not write rows",
        )

        require(
            second[
                "already_applied_count"
            ]
            == 4,
            "second replay idempotency changed",
        )

        connection = connect_ro(
            temp_db
        )

        try:
            total_after_second = (
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM availability
                    """
                ).fetchone()[0]
            )

            unknown_after_second = (
                connection.execute(
                    """
                    SELECT
                        fail_count,
                        last_checked_at
                    FROM availability
                    WHERE dvd_id = ?
                      AND source = ?
                    """,
                    (
                        unknown_item[
                            "dvd_id"
                        ],
                        unknown_item[
                            "source"
                        ],
                    ),
                ).fetchone()
            )

        finally:
            connection.close()

        require(
            total_after_second == 36,
            "idempotent replay "
            "changed row count",
        )

        require(
            unknown_after_second[
                "fail_count"
            ] == 1,
            "duplicate UNKNOWN replay "
            "incremented fail_count",
        )

        require(
            unknown_after_second[
                "last_checked_at"
            ] == CURRENT_OBSERVED,
            "duplicate replay "
            "changed timestamp",
        )

        (
            stale_artifact,
            _,
            _,
        ) = build_test_artifact(
            db_path,
            observed_at=
                STALE_OBSERVED,
        )

        try:
            replay_batch_artifact(
                temp_db,
                stale_artifact,
            )

        except RuntimeError as exc:
            require(
                "stale availability artifact"
                in str(
                    exc
                ),
                "stale replay failed "
                "for wrong reason",
            )

        else:
            raise RuntimeError(
                "stale artifact "
                "must fail closed"
            )

        print(
            "AVAILABILITY_RUNNER_FIRST_REPLAY_SMOKE=PASS"
        )

        print(
            "AVAILABILITY_RUNNER_IDEMPOTENT_REPLAY_SMOKE=PASS"
        )

        print(
            "AVAILABILITY_RUNNER_UNKNOWN_NO_DOUBLE_BACKOFF_SMOKE=PASS"
        )

        print(
            "AVAILABILITY_RUNNER_STALE_ARTIFACT_FAIL_CLOSED_SMOKE=PASS"
        )

        print(
            "AVAILABILITY_RUNNER_TEMP_DB_ONLY_SMOKE=PASS"
        )


def main():
    if len(
        sys.argv
    ) != 2:
        raise RuntimeError(
            "usage: "
            "teddy_discovery_availability_runner_smoke.py "
            "<stage4-db>"
        )

    db_path = Path(
        sys.argv[1]
    )

    real_baseline_smoke(
        db_path
    )

    artifact = collection_smoke(
        db_path
    )

    replay_idempotency_smoke(
        db_path,
        artifact,
    )

    print(
        "TEDDY_AVAILABILITY_RUNNER_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
