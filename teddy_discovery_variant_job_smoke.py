from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile

import teddy_discovery_db as db
import teddy_discovery_variant_collector as collector

from teddy_discovery_variant_job import (
    run_variant_probe_batch,
)

from teddy_discovery_variants import (
    VARIANT_STANDARD,
    VARIANT_UNCENSORED,
    persist_title_variant,
    read_title_variants,
)


NOW = (
    "2026-08-28T12:00:00+00:00"
)


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


class FakeResponse:
    def __init__(
        self,
        *,
        url,
        text,
        status_code=200,
    ):
        self.status_code = (
            status_code
        )

        self.url = url

        self.text = text

        self.headers = {
            "content-type":
                "text/html; charset=utf-8",
        }


class FakeSession:
    def __init__(
        self,
        *,
        fail_dvd_id=None,
    ):
        self.calls = []
        self.fail_dvd_id = (
            fail_dvd_id
        )

    def get(
        self,
        url,
        **kwargs,
    ):
        self.calls.append(
            url
        )

        slug = (
            url.rstrip("/")
            .split("/")[-1]
        )

        dvd_id = slug.upper()

        if (
            self.fail_dvd_id
            and dvd_id
            == self.fail_dvd_id
        ):
            raise RuntimeError(
                "synthetic probe failure "
                + dvd_id
            )

        if dvd_id == "REC-002":
            return FakeResponse(
                url=(
                    "https://missav123.com/"
                    "dm13/ko/rec-002"
                ),
                text="""
                    <html>
                      <body>
                        <a href="/ko/rec-002-uncensored-leak">
                          confirmed
                        </a>
                      </body>
                    </html>
                """,
            )

        return FakeResponse(
            url=(
                "https://missav123.com/"
                "dm13/ko/"
                + slug
            ),
            text=(
                "<html><body>"
                "<a href=\"/ko/"
                + slug
                + "\">standard</a>"
                "</body></html>"
            ),
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


def add_title(
    connection,
    dvd_id,
    release_date,
    status="FOUND",
):
    connection.execute(
        """
        INSERT INTO titles(
            dvd_id,
            title,
            release_date,
            first_seen_at,
            last_seen_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            dvd_id,
            dvd_id + " test",
            release_date,
            NOW,
            NOW,
        ),
    )

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
            "missav",
            status,
            (
                "https://missav123.com/"
                "ko/"
                + dvd_id.lower()
            ),
            NOW,
            (
                "2026-08-29"
                "T12:00:00+00:00"
            ),
            0,
        ),
    )


def add_standard(
    connection,
    dvd_id,
    checked_at,
):
    persist_title_variant(
        connection,
        {
            "dvd_id":
                dvd_id,

            "source":
                "missav",

            "variant_kind":
                VARIANT_STANDARD,

            "variant_slug":
                dvd_id.lower(),

            "page_url": (
                "https://missav123.com/"
                "ko/"
                + dvd_id.lower()
            ),

            "confirmed":
                1,
        },
        observed_at=
            checked_at,
        checked_at=
            checked_at,
    )


def add_uncensored(
    connection,
    dvd_id,
):
    slug = (
        dvd_id.lower()
        + "-uncensored-leak"
    )

    persist_title_variant(
        connection,
        {
            "dvd_id":
                dvd_id,

            "source":
                "missav",

            "variant_kind":
                VARIANT_UNCENSORED,

            "variant_slug":
                slug,

            "page_url": (
                "https://missav123.com/"
                "ko/"
                + slug
            ),

            "confirmed":
                1,
        },
        observed_at=NOW,
        checked_at=NOW,
    )


def create_fixture(
    path,
):
    connection = db.connect(
        path
    )

    try:
        db.initialize(
            connection
        )

        add_title(
            connection,
            "TOD-001",
            "2026-08-28",
        )

        add_title(
            connection,
            "REC-002",
            "2026-08-27",
        )

        add_title(
            connection,
            "FUT-003",
            "2026-08-30",
        )

        add_title(
            connection,
            "FRS-004",
            "2026-08-26",
        )

        add_title(
            connection,
            "UNC-005",
            "2026-08-28",
        )

        add_title(
            connection,
            "NFA-006",
            "2026-08-28",
            status="NOT_FOUND",
        )

        connection.commit()

        add_standard(
            connection,
            "FRS-004",
            (
                "2026-08-28"
                "T10:00:00+00:00"
            ),
        )

        add_uncensored(
            connection,
            "UNC-005",
        )

        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

    finally:
        connection.close()

    require(
        integrity == "ok",
        "fixture integrity failed",
    )


def read_variants(
    path,
    dvd_id,
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

    try:
        return read_title_variants(
            connection,
            dvd_id=dvd_id,
            confirmed_only=True,
        )

    finally:
        connection.close()


def integration_smoke():
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-variant-job-"
    ) as temp:

        path = (
            Path(temp)
            / "discovery.sqlite3"
        )

        create_fixture(
            path
        )

        session = FakeSession()
        sleeper = FakeSleeper()

        original_utc_now = (
            collector.utc_now
        )

        collector.utc_now = (
            lambda: NOW
        )

        try:
            first = run_variant_probe_batch(
                path,
                now=NOW,
                max_items=2,
                recheck_after_hours=6,
                near_future_days=7,
                delay_seconds=0.25,
                timeout=45,
                session=session,
                sleeper=sleeper,
            )

            second = run_variant_probe_batch(
                path,
                now=NOW,
                max_items=2,
                recheck_after_hours=6,
                near_future_days=7,
                delay_seconds=0.25,
                timeout=45,
                session=session,
                sleeper=sleeper,
            )

            third = run_variant_probe_batch(
                path,
                now=NOW,
                max_items=2,
                recheck_after_hours=6,
                near_future_days=7,
                delay_seconds=0.25,
                timeout=45,
                session=session,
                sleeper=sleeper,
            )

        finally:
            collector.utc_now = (
                original_utc_now
            )

        require(
            [
                item[
                    "dvd_id"
                ]
                for item
                in first[
                    "plan"
                ][
                    "selected"
                ]
            ]
            == [
                "TOD-001",
                "REC-002",
            ],
            "first planner selection changed",
        )

        require(
            first[
                "selected_count"
            ]
            == 2,
            "first selected count changed",
        )

        require(
            first[
                "completed_count"
            ]
            == 2,
            "first completed count changed",
        )

        require(
            first[
                "failed_count"
            ]
            == 0,
            "first batch unexpectedly failed",
        )

        require(
            first[
                "found_uncensored_count"
            ]
            == 1,
            "uncensored count changed",
        )

        require(
            first[
                "standard_watermark_count"
            ]
            == 1,
            "standard watermark count changed",
        )

        require(
            first[
                "degraded"
            ]
            is False,
            "healthy batch became degraded",
        )

        tod_rows = read_variants(
            path,
            "TOD-001",
        )

        rec_rows = read_variants(
            path,
            "REC-002",
        )

        require(
            len(
                tod_rows
            )
            == 1
            and tod_rows[0][
                "variant_kind"
            ]
            == VARIANT_STANDARD,
            "TOD standard watermark missing",
        )

        require(
            len(
                rec_rows
            )
            == 1
            and rec_rows[0][
                "variant_kind"
            ]
            == VARIANT_UNCENSORED,
            "REC uncensored variant missing",
        )

        require(
            [
                item[
                    "dvd_id"
                ]
                for item
                in second[
                    "plan"
                ][
                    "selected"
                ]
            ]
            == [
                "FUT-003",
            ],
            (
                "watermark/uncensored "
                "did not suppress re-probe"
            ),
        )

        require(
            second[
                "completed_count"
            ]
            == 1,
            "second completed count changed",
        )

        require(
            second[
                "standard_watermark_count"
            ]
            == 1,
            "future standard watermark missing",
        )

        require(
            third[
                "selected_count"
            ]
            == 0,
            "fully fresh plan was not empty",
        )

        require(
            len(
                session.calls
            )
            == 3,
            "actual collector call count changed",
        )

        require(
            session.calls
            == [
                (
                    "https://missav123.com/"
                    "ko/tod-001"
                ),
                (
                    "https://missav123.com/"
                    "ko/rec-002"
                ),
                (
                    "https://missav123.com/"
                    "ko/fut-003"
                ),
            ],
            "collector URLs changed",
        )

        require(
            sleeper.calls
            == [
                0.25,
            ],
            "inter-request delay changed",
        )

        connection = sqlite3.connect(
            "file:"
            + str(path)
            + "?mode=ro",
            uri=True,
        )

        try:
            integrity = connection.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]

        finally:
            connection.close()

        require(
            integrity == "ok",
            "integration DB integrity failed",
        )

    print(
        "VARIANT_JOB_PLANNER_TO_COLLECTOR_SMOKE=PASS"
    )

    print(
        "VARIANT_JOB_BOUNDED_SELECTION_SMOKE=PASS"
    )

    print(
        "VARIANT_JOB_STANDARD_WATERMARK_RECHECK_SKIP_SMOKE=PASS"
    )

    print(
        "VARIANT_JOB_UNCENSORED_RECHECK_SKIP_SMOKE=PASS"
    )

    print(
        "VARIANT_JOB_INTER_REQUEST_DELAY_SMOKE=PASS"
    )


def failure_isolation_smoke():
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-variant-job-failure-"
    ) as temp:

        path = (
            Path(temp)
            / "discovery.sqlite3"
        )

        connection = db.connect(
            path
        )

        try:
            db.initialize(
                connection
            )

            add_title(
                connection,
                "TOD-011",
                "2026-08-28",
            )

            add_title(
                connection,
                "REC-012",
                "2026-08-27",
            )

            connection.commit()

        finally:
            connection.close()

        session = FakeSession(
            fail_dvd_id=
                "TOD-011"
        )

        sleeper = FakeSleeper()

        original_utc_now = (
            collector.utc_now
        )

        collector.utc_now = (
            lambda: NOW
        )

        try:
            result = run_variant_probe_batch(
                path,
                now=NOW,
                max_items=2,
                recheck_after_hours=6,
                delay_seconds=0.5,
                session=session,
                sleeper=sleeper,
            )

        finally:
            collector.utc_now = (
                original_utc_now
            )

        require(
            result[
                "selected_count"
            ]
            == 2,
            "failure batch selection changed",
        )

        require(
            result[
                "failed_count"
            ]
            == 1,
            "failure count changed",
        )

        require(
            result[
                "completed_count"
            ]
            == 1,
            "later candidate did not continue",
        )

        require(
            result[
                "degraded"
            ]
            is True,
            "failure did not mark degraded",
        )

        require(
            result[
                "failures"
            ][0][
                "dvd_id"
            ]
            == "TOD-011",
            "failure identity changed",
        )

        require(
            len(
                session.calls
            )
            == 2,
            "batch stopped after first failure",
        )

        require(
            sleeper.calls
            == [
                0.5,
            ],
            "failure path delay changed",
        )

        rec_rows = read_variants(
            path,
            "REC-012",
        )

        require(
            len(
                rec_rows
            )
            == 1
            and rec_rows[0][
                "variant_kind"
            ]
            == VARIANT_STANDARD,
            (
                "successful candidate after "
                "failure was not persisted"
            ),
        )

    print(
        "VARIANT_JOB_FAILURE_ISOLATION_SMOKE=PASS"
    )

    print(
        "VARIANT_JOB_CONTINUES_AFTER_FAILURE_SMOKE=PASS"
    )


def validation_smoke():
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-variant-job-validation-"
    ) as temp:

        path = (
            Path(temp)
            / "discovery.sqlite3"
        )

        connection = db.connect(
            path
        )

        try:
            db.initialize(
                connection
            )

        finally:
            connection.close()

        for invalid in (
            -1,
            31,
            True,
            "1",
        ):
            try:
                run_variant_probe_batch(
                    path,
                    now=NOW,
                    delay_seconds=invalid,
                )

            except ValueError:
                pass

            else:
                raise RuntimeError(
                    "invalid delay must fail closed"
                )

        for invalid in (
            0,
            121,
            True,
            45.0,
        ):
            try:
                run_variant_probe_batch(
                    path,
                    now=NOW,
                    timeout=invalid,
                )

            except ValueError:
                pass

            else:
                raise RuntimeError(
                    "invalid timeout must fail closed"
                )

    print(
        "VARIANT_JOB_ARGUMENT_VALIDATION_SMOKE=PASS"
    )


def main():
    integration_smoke()
    failure_isolation_smoke()
    validation_smoke()

    print(
        "LIVE_SITE_REQUESTS=0"
    )

    print(
        "MEDIA_DOWNLOAD=0"
    )

    print(
        "TEDDY_DISCOVERY_VARIANT_JOB_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
