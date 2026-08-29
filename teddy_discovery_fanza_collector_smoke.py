from teddy_discovery_fanza import (
    FANZA_QUERY_URL,
    collect_fanza_query_pages,
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
    release_date="2026-09-10",
):
    return {
        "dvdId":
            f"TST-{number:03d}",

        "title":
            f"TITLE {number}",

        "releaseDate":
            release_date,

        "extra": {},
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


class FakeSession:
    def __init__(
        self,
        pages,
    ):
        self.pages = pages
        self.calls = []

    def post(
        self,
        url,
        **kwargs,
    ):
        self.calls.append(
            (
                url,
                kwargs,
            )
        )

        payload = kwargs[
            "json"
        ]

        page = payload[
            "page"
        ]

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
                100 - len(
                    self.calls
                ),
        )


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


def contract_smoke():
    session = FakeSession({
        1:
            payload(
                [
                    item(number)
                    for number
                    in range(
                        1,
                        51,
                    )
                ]
            ),

        2:
            payload(
                [
                    item(number)
                    for number
                    in range(
                        51,
                        61,
                    )
                ]
            ),
    })

    result = (
        collect_fanza_query_pages(
            session,
            api_key=KEY,
            proxy_url=PROXY,
            max_pages=2,
        )
    )

    require(
        result[
            "item_count"
        ] == 60,
        "bounded FANZA item "
        "count changed",
    )

    require(
        result[
            "page_count"
        ] == 2,
        "bounded FANZA page "
        "count changed",
    )

    require(
        result[
            "request_count"
        ] == 2,
        "bounded FANZA request "
        "count changed",
    )

    require(
        result[
            "has_more_pages"
        ] is False,
        "short final page "
        "marked incomplete",
    )

    require(
        result[
            "provider_boundary"
        ] is False,
        "normal short page "
        "marked 404 boundary",
    )

    for index, (
        url,
        kwargs,
    ) in enumerate(
        session.calls,
        start=1,
    ):
        require(
            url == FANZA_QUERY_URL,
            "FANZA query URL changed",
        )

        require(
            kwargs[
                "json"
            ] == {
                "providers": [
                    "fanza"
                ],

                "filter": {
                    "censored":
                        "censored",
                },

                "sort":
                    "release",

                "page":
                    index,

                "num":
                    50,
            },
            "CP53 request payload "
            "changed",
        )

        require(
            kwargs[
                "headers"
            ][
                "X-RapidAPI-Host"
            ]
            == (
                "javinfo.p."
                "rapidapi.com"
            ),
            "RapidAPI host header "
            "changed",
        )

        require(
            kwargs[
                "headers"
            ][
                "X-RapidAPI-Key"
            ]
            == KEY,
            "RapidAPI key was not "
            "passed via header",
        )

        require(
            kwargs[
                "proxies"
            ] == {
                "http":
                    PROXY,

                "https":
                    PROXY,
            },
            "Gluetun boundary changed",
        )

    print(
        "FANZA_CP53_REQUEST_CONTRACT_SMOKE=PASS"
    )

    print(
        "FANZA_SHORT_PAGE_BOUNDARY_SMOKE=PASS"
    )


def bounded_window_smoke():
    session = FakeSession({
        1:
            payload(
                [
                    item(number)
                    for number
                    in range(
                        1,
                        51,
                    )
                ]
            )
    })

    result = (
        collect_fanza_query_pages(
            session,
            api_key=KEY,
            proxy_url=PROXY,
            max_pages=1,
        )
    )

    require(
        result[
            "item_count"
        ] == 50,
        "one-page item count "
        "changed",
    )

    require(
        result[
            "has_more_pages"
        ] is True,
        "full bounded window "
        "did not expose continuation",
    )

    require(
        len(
            session.calls
        ) == 1,
        "bounded collector "
        "fetched too many pages",
    )

    print(
        "FANZA_BOUNDED_WINDOW_SMOKE=PASS"
    )


def provider_boundary_smoke():
    session = FakeSession({
        1:
            payload(
                [
                    item(number)
                    for number
                    in range(
                        1,
                        51,
                    )
                ]
            ),

        2:
            (
                404,
                {
                    "status":
                        404,

                    "message":
                        "boundary",
                },
            ),
    })

    result = (
        collect_fanza_query_pages(
            session,
            api_key=KEY,
            proxy_url=PROXY,
            max_pages=2,
        )
    )

    require(
        result[
            "item_count"
        ] == 50,
        "404 boundary changed "
        "prior data",
    )

    require(
        result[
            "request_count"
        ] == 2,
        "404 boundary request "
        "count changed",
    )

    require(
        result[
            "provider_boundary"
        ] is True,
        "CP54 404 boundary "
        "not surfaced",
    )

    require(
        result[
            "has_more_pages"
        ] is False,
        "404 boundary marked "
        "as continuation",
    )

    require(
        result[
            "usage"
        ][1][
            "http_status"
        ] == 404,
        "404 telemetry missing",
    )

    require(
        result[
            "usage"
        ][1][
            "success"
        ] is False,
        "404 telemetry marked "
        "successful",
    )

    print(
        "FANZA_CP54_404_BOUNDARY_SMOKE=PASS"
    )


def direct_route_fail_closed_smoke():
    session = FakeSession({
        1:
            payload(
                [
                    item(1)
                ]
            )
    })

    failed = False

    try:
        collect_fanza_query_pages(
            session,
            api_key=KEY,
            proxy_url="",
            max_pages=1,
        )

    except ValueError:
        failed = True

    require(
        failed,
        "direct FANZA route "
        "did not fail closed",
    )

    require(
        len(
            session.calls
        ) == 0,
        "direct-route failure "
        "performed request",
    )

    print(
        "FANZA_FIXED_PROXY_BOUNDARY_SMOKE=PASS"
    )


def bad_source_fail_closed_smoke():
    session = FakeSession({
        1: {
            "source":
                "wrong-source",

            "count":
                1,

            "q":
                {},

            "results": [
                item(1)
            ],
        }
    })

    failed = False

    try:
        collect_fanza_query_pages(
            session,
            api_key=KEY,
            proxy_url=PROXY,
            max_pages=1,
        )

    except ValueError:
        failed = True

    require(
        failed,
        "wrong FANZA source "
        "did not fail closed",
    )

    print(
        "FANZA_SOURCE_FAIL_CLOSED_SMOKE=PASS"
    )


def main():
    contract_smoke()

    bounded_window_smoke()

    provider_boundary_smoke()

    direct_route_fail_closed_smoke()

    bad_source_fail_closed_smoke()

    print(
        "FANZA_BOUNDED_COLLECTOR_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
