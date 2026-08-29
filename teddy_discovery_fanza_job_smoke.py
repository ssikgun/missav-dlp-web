from pathlib import Path
import tempfile

from teddy_discovery_db import (
    connect,
    initialize,
)

from teddy_discovery_fanza import (
    FANZA_QUERY_URL,
    record_rapidapi_usage,
    run_fanza_seed_job,
    utc_now,
)


PROXY = (
    "http://gluetun:8888"
)

KEY = (
    "offline-test-key"
)


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


def item(
    number,
    *,
    release_date=
        "2026-09-10",
):
    value = {
        "dvdId":
            f"JOB-{number:03d}",

        "title":
            f"JOB TITLE {number}",

        "extra":
            {},
    }

    if release_date is not None:
        value[
            "releaseDate"
        ] = release_date

    return value


def payload(
    values,
):
    return {
        "source":
            "fanza",

        "count":
            len(values),

        "q":
            {},

        "results":
            values,
    }


class FakeResponse:
    def __init__(
        self,
        status,
        body,
        *,
        remaining=99,
    ):
        self.status_code = status
        self._body = body

        self.headers = {
            (
                "X-RateLimit-"
                "Request-Limit-Limit"
            ):
                "100",

            (
                "X-RateLimit-"
                "Request-Limit-Remaining"
            ):
                str(remaining),
        }

    def json(self):
        return self._body


class FakeTransport:
    def __init__(
        self,
        pages,
        *,
        remaining=None,
        fail_page=None,
    ):
        self.pages = pages

        self.remaining = (
            remaining
            or {}
        )

        self.fail_page = (
            fail_page
        )

        self.calls = []


    def post(
        self,
        url,
        **kwargs,
    ):
        require(
            url == FANZA_QUERY_URL,
            "unexpected FANZA URL",
        )

        page = kwargs[
            "json"
        ][
            "page"
        ]

        self.calls.append(
            page
        )

        if page == self.fail_page:
            raise RuntimeError(
                "offline network failure"
            )

        value = self.pages[
            page
        ]

        if isinstance(
            value,
            tuple,
        ):
            status, body = value
        else:
            status = 200
            body = value

        return FakeResponse(
            status,
            body,
            remaining=
                self.remaining.get(
                    page,
                    99 - page,
                ),
        )


def successful_job_smoke():
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-fanza-job-"
    ) as temp:

        path = (
            Path(temp)
            / "discovery.sqlite3"
        )

        connection = connect(
            path
        )

        initialize(
            connection
        )

        transport = FakeTransport({
            1:
                payload([
                    item(number)
                    for number
                    in range(
                        1,
                        51,
                    )
                ]),

            2:
                payload([
                    item(number)
                    for number
                    in range(
                        51,
                        61,
                    )
                ]),
        })

        result = run_fanza_seed_job(
            connection,
            transport=transport,
            api_key=KEY,
            proxy_url=PROXY,
            max_pages=2,
        )

        require(
            result["written"]
            == 60,
            "seed write count changed",
        )

        require(
            result[
                "request_count"
            ] == 2,
            "request count changed",
        )

        require(
            result[
                "has_more_pages"
            ] is False,
            "short final page "
            "marked incomplete",
        )

        require(
            transport.calls
            == [1, 2],
            "page order changed",
        )

        usage = connection.execute(
            """
            SELECT
                COUNT(*) AS count,
                SUM(success) AS successes
            FROM api_usage
            """
        ).fetchone()

        require(
            usage["count"] == 2,
            "API usage not persisted",
        )

        require(
            usage["successes"] == 2,
            "successful API usage "
            "telemetry changed",
        )

        title_count = (
            connection.execute(
                """
                SELECT COUNT(*)
                FROM titles
                """
            ).fetchone()[0]
        )

        require(
            title_count == 60,
            "future seeds not written",
        )

        polluted = (
            connection.execute(
                """
                SELECT COUNT(*)
                FROM titles
                WHERE
                    metadata_source
                    IS NOT NULL
                   OR title IS NOT NULL
                   OR maker IS NOT NULL
                   OR cover_url IS NOT NULL
                """
            ).fetchone()[0]
        )

        require(
            polluted == 0,
            "seed job polluted "
            "rich metadata",
        )

        connection.close()

    print(
        "FANZA_JOB_SUCCESS_PATH_SMOKE=PASS"
    )


def budget_blocks_before_network_smoke():
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-fanza-budget-block-"
    ) as temp:

        path = (
            Path(temp)
            / "discovery.sqlite3"
        )

        connection = connect(
            path
        )

        initialize(
            connection
        )

        for _ in range(79):
            record_rapidapi_usage(
                connection,
                endpoint="/query",
                requested_at=utc_now(),
                success=True,
                http_status=200,
                quota_limit=100,
                quota_remaining=50,
            )

        connection.commit()

        transport = FakeTransport({
            1:
                payload([
                    item(1)
                ]),
        })

        blocked = False

        try:
            run_fanza_seed_job(
                connection,
                transport=transport,
                api_key=KEY,
                proxy_url=PROXY,
                max_pages=1,
            )

        except RuntimeError:
            blocked = True

        require(
            blocked,
            "exhausted budget "
            "did not block",
        )

        require(
            transport.calls == [],
            "budget block still "
            "performed network",
        )

        connection.close()

    print(
        "FANZA_JOB_PRE_REQUEST_BUDGET_SMOKE=PASS"
    )


def network_failure_usage_smoke():
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-fanza-network-fail-"
    ) as temp:

        path = (
            Path(temp)
            / "discovery.sqlite3"
        )

        connection = connect(
            path
        )

        initialize(
            connection
        )

        transport = FakeTransport(
            {
                1:
                    payload([
                        item(1)
                    ]),
            },
            fail_page=1,
        )

        failed = False

        try:
            run_fanza_seed_job(
                connection,
                transport=transport,
                api_key=KEY,
                proxy_url=PROXY,
                max_pages=1,
            )

        except RuntimeError:
            failed = True

        require(
            failed,
            "network failure "
            "did not propagate",
        )

        row = connection.execute(
            """
            SELECT
                success,
                http_status
            FROM api_usage
            ORDER BY usage_id DESC
            LIMIT 1
            """
        ).fetchone()

        require(
            row is not None,
            "failed request usage "
            "was not recorded",
        )

        require(
            row["success"] == 0,
            "failed request marked "
            "successful",
        )

        require(
            row["http_status"]
            is None,
            "network failure got "
            "fake HTTP status",
        )

        require(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM titles
                """
            ).fetchone()[0]
            == 0,
            "network failure wrote "
            "catalog rows",
        )

        connection.close()

    print(
        "FANZA_JOB_NETWORK_FAILURE_LEDGER_SMOKE=PASS"
    )


def quota_stops_mid_run_smoke():
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-fanza-midrun-quota-"
    ) as temp:

        path = (
            Path(temp)
            / "discovery.sqlite3"
        )

        connection = connect(
            path
        )

        initialize(
            connection
        )

        transport = FakeTransport(
            {
                1:
                    payload([
                        item(number)
                        for number
                        in range(
                            1,
                            51,
                        )
                    ]),

                2:
                    payload([
                        item(51)
                    ]),
            },
            remaining={
                1: 20,
                2: 19,
            },
        )

        blocked = False

        try:
            run_fanza_seed_job(
                connection,
                transport=transport,
                api_key=KEY,
                proxy_url=PROXY,
                max_pages=2,
            )

        except RuntimeError:
            blocked = True

        require(
            blocked,
            "quota margin did not "
            "stop second request",
        )

        require(
            transport.calls == [1],
            "second request escaped "
            "quota protection",
        )

        require(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM api_usage
                """
            ).fetchone()[0]
            == 1,
            "first consumed request "
            "not preserved",
        )

        require(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM titles
                """
            ).fetchone()[0]
            == 0,
            "partial collection "
            "wrote catalog rows",
        )

        connection.close()

    print(
        "FANZA_JOB_MIDRUN_QUOTA_SMOKE=PASS"
    )


def seed_validation_failure_smoke():
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-fanza-seed-fail-"
    ) as temp:

        path = (
            Path(temp)
            / "discovery.sqlite3"
        )

        connection = connect(
            path
        )

        initialize(
            connection
        )

        transport = FakeTransport({
            1:
                payload([
                    item(
                        1,
                        release_date=None,
                    )
                ]),
        })

        failed = False

        try:
            run_fanza_seed_job(
                connection,
                transport=transport,
                api_key=KEY,
                proxy_url=PROXY,
                max_pages=1,
            )

        except ValueError:
            failed = True

        require(
            failed,
            "invalid seed did "
            "not fail closed",
        )

        require(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM api_usage
                """
            ).fetchone()[0]
            == 1,
            "consumed request vanished "
            "after seed failure",
        )

        require(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM titles
                """
            ).fetchone()[0]
            == 0,
            "invalid seed wrote "
            "catalog row",
        )

        connection.close()

    print(
        "FANZA_JOB_SEED_FAIL_CLOSED_SMOKE=PASS"
    )


def main():
    successful_job_smoke()

    budget_blocks_before_network_smoke()

    network_failure_usage_smoke()

    quota_stops_mid_run_smoke()

    seed_validation_failure_smoke()

    print(
        "FANZA_END_TO_END_OFFLINE_JOB_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
