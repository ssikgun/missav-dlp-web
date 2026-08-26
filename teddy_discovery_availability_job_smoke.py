from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
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

from teddy_discovery_availability_job import (
    APPLIED_SUFFIX,
    PENDING_SUFFIX,
    find_pending_artifacts,
    run_cycle,
    write_pending_artifact,
)

from teddy_discovery_availability_runner import (
    collect_batch_artifact,
    replay_batch_artifact,
)


NOW = (
    "2026-08-26T12:30:00+00:00"
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

    connection.row_factory = (
        sqlite3.Row
    )

    return connection


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
        index = len(
            self.calls
        )

        if index >= len(
            self.statuses
        ):
            raise RuntimeError(
                "fake collector "
                "received extra request"
            )

        status = self.statuses[
            index
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
                "fake availability status"
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


class FailCollector:
    def __init__(
        self,
    ):
        self.calls = []

    def __call__(
        self,
        *,
        source,
        dvd_id,
    ):
        self.calls.append(
            (
                source,
                dvd_id,
            )
        )

        raise RuntimeError(
            "network collection "
            "must not occur"
        )


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


def file_sha256(
    path: Path,
) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def real_baseline_smoke(
    db_path: Path,
):
    connection = connect_ro(
        db_path
    )

    try:
        total = connection.execute(
            "SELECT COUNT(*) FROM availability"
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
        total == 52,
        "real availability "
        "baseline changed",
    )

    require(
        groups == [
            (
                "123av",
                "FOUND",
                25,
            ),
            (
                "123av",
                "NOT_FOUND",
                1,
            ),
            (
                "missav",
                "FOUND",
                26,
            ),
        ],
        "real availability "
        "groups changed",
    )

    require(
        plan[
            "due_count"
        ] == 183,
        "real due count changed",
    )

    require(
        plan[
            "fresh_count"
        ] == 51,
        "real fresh count changed",
    )

    require(
        (
            plan[
                "selected"
            ][0][
                "source"
            ],
            plan[
                "selected"
            ][0][
                "dvd_id"
            ],
        )
        == (
            "123av",
            "NAMH-074",
        ),
        "real next request changed",
    )

    require(
        integrity == "ok",
        "real DB integrity failed",
    )

    print(
        "AVAILABILITY_JOB_REAL_BASELINE_SMOKE=PASS"
    )


def successful_cycle_smoke(
    real_db: Path,
):
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-availability-job-cycle-"
    ) as temp:
        root = Path(
            temp
        )

        db_path = (
            root
            / "teddy-discovery.sqlite3"
        )

        artifact_dir = (
            root
            / "artifacts"
        )

        copy_db(
            real_db,
            db_path,
        )

        collector = FakeCollector(
            [
                STATUS_FOUND,
                STATUS_NOT_FOUND,
                STATUS_FOUND,
            ]
        )

        sleeper = FakeSleeper()

        result = run_cycle(
            db_path,
            artifact_dir,
            now=NOW,
            observed_at=
                "2026-08-26T12:31:00+00:00",
            max_requests=3,
            inter_request_delay_seconds=0.25,
            collector=collector,
            sleeper=sleeper,
        )

        require(
            result[
                "mode"
            ]
            == "collected-and-replayed",
            "job cycle mode changed",
        )

        require(
            result[
                "completed_count"
            ] == 3,
            "job completed count changed",
        )

        require(
            result[
                "applied_count"
            ] == 3,
            "job applied count changed",
        )

        require(
            result[
                "already_applied_count"
            ] == 0,
            "job unexpected "
            "already-applied rows",
        )

        require(
            result[
                "network_requests"
            ] == 3,
            "job network accounting changed",
        )

        require(
            len(
                collector.calls
            ) == 3,
            "job collector call count changed",
        )

        require(
            sleeper.calls
            == [
                0.25,
                0.25,
            ],
            "job inter-request delay changed",
        )

        require(
            not find_pending_artifacts(
                artifact_dir
            ),
            "successful job left "
            "pending artifact",
        )

        applied = list(
            artifact_dir.glob(
                "availability-runner-*"
                + APPLIED_SUFFIX
            )
        )

        require(
            len(
                applied
            ) == 1,
            "successful job applied "
            "artifact count changed",
        )

        require(
            Path(
                result[
                    "artifact"
                ]
            ) == applied[0],
            "job result artifact "
            "path changed",
        )

        with applied[0].open(
            "r",
            encoding="utf-8",
        ) as fh:
            artifact = json.load(
                fh
            )

        require(
            artifact[
                "job_version"
            ]
            == "stage4-availability-job-v1",
            "job artifact version changed",
        )

        require(
            artifact[
                "completed_count"
            ] == 3,
            "job artifact result "
            "count changed",
        )

        require(
            artifact[
                "status_counts"
            ]
            == {
                "FOUND": 2,
                "NOT_FOUND": 1,
            },
            "job artifact status "
            "distribution changed",
        )

        require(
            isinstance(
                artifact.get(
                    "job_source_sha256"
                ),
                str,
            )
            and len(
                artifact[
                    "job_source_sha256"
                ]
            ) == 64,
            "job source provenance missing",
        )

        require(
            isinstance(
                artifact.get(
                    "runner_module_sha256"
                ),
                str,
            )
            and len(
                artifact[
                    "runner_module_sha256"
                ]
            ) == 64,
            "runner source provenance missing",
        )

        connection = connect_ro(
            db_path
        )

        try:
            total = connection.execute(
                "SELECT COUNT(*) FROM availability"
            ).fetchone()[0]

            integrity = connection.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]

        finally:
            connection.close()

        require(
            total == 55,
            "successful cycle "
            "temp DB row count changed",
        )

        require(
            integrity == "ok",
            "successful cycle "
            "temp DB integrity failed",
        )

    print(
        "AVAILABILITY_JOB_SUCCESSFUL_CYCLE_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_JOB_PENDING_TO_APPLIED_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_JOB_ATOMIC_ARTIFACT_SMOKE=PASS"
    )


def build_pending_artifact(
    db_path: Path,
    *,
    artifact_dir: Path,
    observed_at: str,
    statuses,
):
    collector = FakeCollector(
        statuses
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
            max_requests=
                len(
                    statuses
                ),
            inter_request_delay_seconds=0,
            stop_on_unknown=True,
            collector=collector,
            sleeper=sleeper,
        )

    finally:
        connection.close()

    artifact[
        "job_version"
    ] = "stage4-availability-job-v1"

    pending = write_pending_artifact(
        artifact_dir,
        artifact,
    )

    return (
        pending,
        artifact,
    )


def pending_recovery_smoke(
    real_db: Path,
):
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-availability-job-recovery-"
    ) as temp:
        root = Path(
            temp
        )

        db_path = (
            root
            / "teddy-discovery.sqlite3"
        )

        artifact_dir = (
            root
            / "artifacts"
        )

        copy_db(
            real_db,
            db_path,
        )

        (
            pending,
            artifact,
        ) = build_pending_artifact(
            db_path,
            artifact_dir=
                artifact_dir,
            observed_at=
                "2026-08-26T12:32:00+00:00",
            statuses=[
                STATUS_FOUND,
                STATUS_UNKNOWN,
                STATUS_FOUND,
            ],
        )

        require(
            pending.exists(),
            "pending recovery "
            "fixture missing",
        )

        require(
            artifact[
                "completed_count"
            ] == 2,
            "UNKNOWN fixture "
            "circuit breaker changed",
        )

        fail_collector = (
            FailCollector()
        )

        result = run_cycle(
            db_path,
            artifact_dir,
            now=NOW,
            max_requests=20,
            collector=
                fail_collector,
            sleeper=
                FakeSleeper(),
        )

        require(
            result[
                "mode"
            ]
            == "recovered-pending",
            "pending recovery mode changed",
        )

        require(
            result[
                "network_collection_performed"
            ]
            is False,
            "pending recovery "
            "performed network collection",
        )

        require(
            result[
                "network_requests"
            ] == 0,
            "pending recovery "
            "network accounting changed",
        )

        require(
            len(
                fail_collector.calls
            ) == 0,
            "pending recovery called "
            "collector",
        )

        require(
            result[
                "applied_count"
            ] == 2,
            "pending recovery "
            "applied count changed",
        )

        require(
            not find_pending_artifacts(
                artifact_dir
            ),
            "pending recovery did not "
            "clear journal",
        )

        applied = list(
            artifact_dir.glob(
                "availability-runner-*"
                + APPLIED_SUFFIX
            )
        )

        require(
            len(
                applied
            ) == 1,
            "pending recovery applied "
            "artifact count changed",
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

        connection = connect_ro(
            db_path
        )

        try:
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
            unknown_row[
                "status"
            ] == STATUS_UNKNOWN,
            "recovered UNKNOWN "
            "status changed",
        )

        require(
            unknown_row[
                "fail_count"
            ] == 1,
            "recovered UNKNOWN "
            "backoff changed",
        )

    print(
        "AVAILABILITY_JOB_PENDING_RECOVERY_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_JOB_RECOVERY_NETWORK_ZERO_SMOKE=PASS"
    )


def post_replay_crash_recovery_smoke(
    real_db: Path,
):
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-availability-job-postreplay-"
    ) as temp:
        root = Path(
            temp
        )

        db_path = (
            root
            / "teddy-discovery.sqlite3"
        )

        artifact_dir = (
            root
            / "artifacts"
        )

        copy_db(
            real_db,
            db_path,
        )

        (
            pending,
            artifact,
        ) = build_pending_artifact(
            db_path,
            artifact_dir=
                artifact_dir,
            observed_at=
                "2026-08-26T12:33:00+00:00",
            statuses=[
                STATUS_UNKNOWN,
            ],
        )

        first = replay_batch_artifact(
            db_path,
            artifact,
        )

        require(
            first[
                "applied_count"
            ] == 1,
            "post-replay crash "
            "fixture apply changed",
        )

        require(
            pending.exists(),
            "post-replay crash "
            "pending fixture missing",
        )

        unknown_item = artifact[
            "results"
        ][0]

        connection = connect_ro(
            db_path
        )

        try:
            before = (
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
            before[
                "fail_count"
            ] == 1,
            "initial UNKNOWN "
            "backoff changed",
        )

        fail_collector = (
            FailCollector()
        )

        recovered = run_cycle(
            db_path,
            artifact_dir,
            now=NOW,
            collector=
                fail_collector,
            sleeper=
                FakeSleeper(),
        )

        require(
            recovered[
                "mode"
            ]
            == "recovered-pending",
            "post-replay recovery "
            "mode changed",
        )

        require(
            recovered[
                "applied_count"
            ] == 0,
            "post-replay recovery "
            "rewrote result",
        )

        require(
            recovered[
                "already_applied_count"
            ] == 1,
            "post-replay recovery "
            "idempotency changed",
        )

        require(
            len(
                fail_collector.calls
            ) == 0,
            "post-replay recovery "
            "performed network request",
        )

        connection = connect_ro(
            db_path
        )

        try:
            after = (
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
            after[
                "fail_count"
            ] == 1,
            "recovery double-incremented "
            "UNKNOWN backoff",
        )

        require(
            after[
                "last_checked_at"
            ] == before[
                "last_checked_at"
            ],
            "recovery changed "
            "UNKNOWN timestamp",
        )

        require(
            not find_pending_artifacts(
                artifact_dir
            ),
            "post-replay pending "
            "journal not cleared",
        )

    print(
        "AVAILABILITY_JOB_POST_REPLAY_CRASH_RECOVERY_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_JOB_UNKNOWN_NO_DOUBLE_BACKOFF_SMOKE=PASS"
    )


def multiple_pending_fail_closed_smoke(
    real_db: Path,
):
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-availability-job-multipending-"
    ) as temp:
        root = Path(
            temp
        )

        db_path = (
            root
            / "teddy-discovery.sqlite3"
        )

        artifact_dir = (
            root
            / "artifacts"
        )

        copy_db(
            real_db,
            db_path,
        )

        (
            first_pending,
            _,
        ) = build_pending_artifact(
            db_path,
            artifact_dir=
                artifact_dir,
            observed_at=
                "2026-08-26T12:34:00+00:00",
            statuses=[
                STATUS_FOUND,
            ],
        )

        second_pending = (
            artifact_dir
            / (
                "availability-runner-"
                "manual-second"
                + PENDING_SUFFIX
            )
        )

        shutil.copy2(
            first_pending,
            second_pending,
        )

        os_mode = (
            second_pending.stat().st_mode
            & 0o777
        )

        require(
            os_mode == 0o600,
            "second pending "
            "permissions changed",
        )

        fail_collector = (
            FailCollector()
        )

        try:
            run_cycle(
                db_path,
                artifact_dir,
                now=NOW,
                collector=
                    fail_collector,
                sleeper=
                    FakeSleeper(),
            )

        except RuntimeError as exc:
            require(
                "multiple pending"
                in str(
                    exc
                ),
                "multiple-pending "
                "failed for wrong reason",
            )

        else:
            raise RuntimeError(
                "multiple pending "
                "artifacts must fail closed"
            )

        require(
            len(
                fail_collector.calls
            ) == 0,
            "multiple pending "
            "performed network request",
        )

        connection = connect_ro(
            db_path
        )

        try:
            total = connection.execute(
                "SELECT COUNT(*) FROM availability"
            ).fetchone()[0]

        finally:
            connection.close()

        require(
            total == 52,
            "multiple-pending "
            "changed temp DB",
        )

    print(
        "AVAILABILITY_JOB_MULTIPLE_PENDING_FAIL_CLOSED_SMOKE=PASS"
    )


def main():
    if len(
        sys.argv
    ) != 2:
        raise RuntimeError(
            "usage: "
            "teddy_discovery_availability_job_smoke.py "
            "<stage4-db>"
        )

    real_db = Path(
        sys.argv[1]
    )

    real_sha_before = (
        file_sha256(
            real_db
        )
    )

    real_baseline_smoke(
        real_db
    )

    successful_cycle_smoke(
        real_db
    )

    pending_recovery_smoke(
        real_db
    )

    post_replay_crash_recovery_smoke(
        real_db
    )

    multiple_pending_fail_closed_smoke(
        real_db
    )

    real_sha_after = (
        file_sha256(
            real_db
        )
    )

    require(
        real_sha_after
        == real_sha_before,
        "offline job smoke "
        "changed real DB bytes",
    )

    print(
        "AVAILABILITY_JOB_REAL_DB_BYTE_UNCHANGED_SMOKE=PASS"
    )

    print(
        "TEDDY_AVAILABILITY_JOB_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
