from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import teddy_discovery_availability_collector as collector

from teddy_discovery_availability import (
    SOURCE_123AV,
    SOURCE_MISSAV,
    STATUS_FOUND,
    STATUS_NOT_FOUND,
    STATUS_UNKNOWN,
    canonical_page_url,
)


GLUETUN_PROXY = (
    "http://gluetun:8888"
)


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


@dataclass
class FakeResponse:
    status_code: int
    url: str
    text: str
    headers: dict


class FakeSession:
    def __init__(
        self,
        *,
        response=None,
        error=None,
    ):
        self.response = response
        self.error = error
        self.calls = []

    def get(
        self,
        url,
        **kwargs,
    ):
        self.calls.append({
            "url":
                url,

            "kwargs":
                kwargs,
        })

        if self.error is not None:
            raise self.error

        return self.response


def with_fixed_proxy(
    callback,
):
    original = (
        collector.teddy_routing
        .proxy_for_mode
    )

    calls = []

    def fake_proxy_for_mode(
        mode,
    ):
        calls.append(
            mode
        )

        return GLUETUN_PROXY

    collector.teddy_routing.proxy_for_mode = (
        fake_proxy_for_mode
    )

    try:
        result = callback(
            calls
        )

    finally:
        collector.teddy_routing.proxy_for_mode = (
            original
        )

    return result


def found_transport_smoke():
    dvd_id = "SDNM-560"

    url = canonical_page_url(
        SOURCE_MISSAV,
        dvd_id,
    )

    session = FakeSession(
        response=FakeResponse(
            status_code=200,
            url=url,
            text=(
                "<html>"
                "<title>"
                "SDNM-560 example - MissAV"
                "</title>"
                "<h1>"
                "SDNM-560 example"
                "</h1>"
                "</html>"
            ),
            headers={
                "Content-Type":
                    "text/html; charset=utf-8",
            },
        )
    )

    def run(
        route_calls,
    ):
        result = (
            collector.collect_availability_page(
                source=SOURCE_MISSAV,
                dvd_id=dvd_id,
                session=session,
            )
        )

        require(
            route_calls
            == [
                "vpn",
            ],
            "collector did not request "
            "exact VPN route",
        )

        return result

    result = with_fixed_proxy(
        run
    )

    require(
        len(
            session.calls
        )
        == 1,
        "FOUND collector GET count changed",
    )

    call = session.calls[0]

    require(
        call[
            "url"
        ]
        == url,
        "collector canonical URL changed",
    )

    kwargs = call[
        "kwargs"
    ]

    require(
        kwargs[
            "proxies"
        ]
        == {
            "http":
                GLUETUN_PROXY,

            "https":
                GLUETUN_PROXY,
        },
        "collector proxy map changed",
    )

    require(
        kwargs[
            "allow_redirects"
        ]
        is False,
        "collector redirect policy changed",
    )

    require(
        kwargs[
            "timeout"
        ]
        == 45,
        "collector timeout changed",
    )

    require(
        kwargs[
            "impersonate"
        ]
        == "chrome",
        "collector impersonate changed",
    )

    require(
        result[
            "request_attempts"
        ]
        == 1,
        "collector request accounting changed",
    )

    require(
        result[
            "redirects_followed"
        ]
        == 0,
        "collector redirect accounting changed",
    )

    require(
        result[
            "media_requests"
        ]
        == 0,
        "collector media boundary changed",
    )

    require(
        result[
            "classification"
        ][
            "status"
        ]
        == STATUS_FOUND,
        "FOUND classification changed",
    )

    print(
        "AVAILABILITY_COLLECTOR_FIXED_VPN_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_COLLECTOR_EXACT_ONE_GET_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_COLLECTOR_NO_REDIRECT_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_COLLECTOR_FOUND_SMOKE=PASS"
    )


def not_found_smoke():
    dvd_id = "ZZZZ-999999"

    url = canonical_page_url(
        SOURCE_123AV,
        dvd_id,
    )

    session = FakeSession(
        response=FakeResponse(
            status_code=404,
            url=url,
            text=(
                "<html>"
                "<title>404 — 123AV</title>"
                "</html>"
            ),
            headers={
                "Content-Type":
                    "text/html; charset=utf-8",
            },
        )
    )

    result = with_fixed_proxy(
        lambda route_calls:
            collector.collect_availability_page(
                source=SOURCE_123AV,
                dvd_id=dvd_id,
                session=session,
            )
    )

    require(
        len(
            session.calls
        )
        == 1,
        "404 collector GET count changed",
    )

    require(
        result[
            "classification"
        ][
            "status"
        ]
        == STATUS_NOT_FOUND,
        "404 classification changed",
    )

    print(
        "AVAILABILITY_COLLECTOR_NOT_FOUND_SMOKE=PASS"
    )


def redirect_unknown_smoke():
    dvd_id = "JUR-821"

    url = canonical_page_url(
        SOURCE_MISSAV,
        dvd_id,
    )

    session = FakeSession(
        response=FakeResponse(
            status_code=302,
            url=url,
            text="<html></html>",
            headers={
                "Content-Type":
                    "text/html",

                "Location":
                    "https://example.invalid/",
            },
        )
    )

    result = with_fixed_proxy(
        lambda route_calls:
            collector.collect_availability_page(
                source=SOURCE_MISSAV,
                dvd_id=dvd_id,
                session=session,
            )
    )

    require(
        result[
            "classification"
        ][
            "status"
        ]
        == STATUS_UNKNOWN,
        "redirect must classify UNKNOWN",
    )

    require(
        result[
            "classification"
        ][
            "reason"
        ]
        == "redirect-location",
        "redirect UNKNOWN reason changed",
    )

    require(
        result[
            "redirects_followed"
        ]
        == 0,
        "redirect was followed",
    )

    print(
        "AVAILABILITY_COLLECTOR_REDIRECT_UNKNOWN_SMOKE=PASS"
    )


def request_error_smoke():
    session = FakeSession(
        error=TimeoutError(
            "synthetic timeout"
        )
    )

    result = with_fixed_proxy(
        lambda route_calls:
            collector.collect_availability_page(
                source=SOURCE_123AV,
                dvd_id="JUR-821",
                session=session,
            )
    )

    require(
        len(
            session.calls
        )
        == 1,
        "request error was retried",
    )

    require(
        result[
            "request_attempts"
        ]
        == 1,
        "request error accounting changed",
    )

    require(
        result[
            "classification"
        ][
            "status"
        ]
        == STATUS_UNKNOWN,
        "request error must be UNKNOWN",
    )

    require(
        result[
            "classification"
        ][
            "reason"
        ]
        == "request-error",
        "request error reason changed",
    )

    print(
        "AVAILABILITY_COLLECTOR_REQUEST_ERROR_UNKNOWN_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_COLLECTOR_NO_RETRY_SMOKE=PASS"
    )


def bad_http_and_identity_smoke():
    dvd_id = "JUR-821"

    url = canonical_page_url(
        SOURCE_MISSAV,
        dvd_id,
    )

    cases = [
        FakeResponse(
            status_code=403,
            url=url,
            text="<html></html>",
            headers={
                "Content-Type":
                    "text/html",
            },
        ),
        FakeResponse(
            status_code=429,
            url=url,
            text="<html></html>",
            headers={
                "Content-Type":
                    "text/html",
            },
        ),
        FakeResponse(
            status_code=500,
            url=url,
            text="<html></html>",
            headers={
                "Content-Type":
                    "text/html",
            },
        ),
        FakeResponse(
            status_code=200,
            url=url,
            text=(
                "<html>"
                "<title>OTHER-001</title>"
                "<h1>OTHER-001</h1>"
                "</html>"
            ),
            headers={
                "Content-Type":
                    "text/html",
            },
        ),
        FakeResponse(
            status_code=200,
            url=url,
            text='{"dvd":"JUR-821"}',
            headers={
                "Content-Type":
                    "application/json",
            },
        ),
    ]

    for response in cases:
        session = FakeSession(
            response=response
        )

        result = with_fixed_proxy(
            lambda route_calls:
                collector.collect_availability_page(
                    source=SOURCE_MISSAV,
                    dvd_id=dvd_id,
                    session=session,
                )
        )

        require(
            result[
                "classification"
            ][
                "status"
            ]
            == STATUS_UNKNOWN,
            (
                "bad response escaped "
                "UNKNOWN boundary: "
                + repr(
                    result
                )
            ),
        )

        require(
            len(
                session.calls
            )
            == 1,
            "bad response was retried",
        )

    print(
        "AVAILABILITY_COLLECTOR_UNKNOWN_BOUNDARY_SMOKE=PASS"
    )


def vpn_unavailable_fail_before_get_smoke():
    original = (
        collector.teddy_routing
        .proxy_for_mode
    )

    session = FakeSession(
        response=None
    )

    collector.teddy_routing.proxy_for_mode = (
        lambda mode:
            None
    )

    try:
        try:
            collector.collect_availability_page(
                source=SOURCE_MISSAV,
                dvd_id="JUR-821",
                session=session,
            )

        except RuntimeError as exc:
            require(
                "VPN proxy"
                in str(exc),
                "unexpected missing VPN error",
            )

        else:
            raise RuntimeError(
                "missing VPN must "
                "fail before GET"
            )

    finally:
        collector.teddy_routing.proxy_for_mode = (
            original
        )

    require(
        session.calls == [],
        "collector requested network "
        "without VPN",
    )

    print(
        "AVAILABILITY_COLLECTOR_VPN_REQUIRED_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_COLLECTOR_FAIL_BEFORE_GET_SMOKE=PASS"
    )


def invalid_input_fail_before_get_smoke():
    session = FakeSession(
        response=None
    )

    original = (
        collector.teddy_routing
        .proxy_for_mode
    )

    route_calls = []

    def fake_proxy(
        mode,
    ):
        route_calls.append(
            mode
        )

        return GLUETUN_PROXY

    collector.teddy_routing.proxy_for_mode = (
        fake_proxy
    )

    try:
        cases = [
            {
                "source":
                    "direct",

                "dvd_id":
                    "JUR-821",
            },
            {
                "source":
                    SOURCE_MISSAV,

                "dvd_id":
                    "JUR-821 extra",
            },
        ]

        for case in cases:
            try:
                collector.collect_availability_page(
                    source=case[
                        "source"
                    ],
                    dvd_id=case[
                        "dvd_id"
                    ],
                    session=session,
                )

            except ValueError:
                pass

            else:
                raise RuntimeError(
                    "invalid collector input "
                    "must fail closed"
                )

    finally:
        collector.teddy_routing.proxy_for_mode = (
            original
        )

    require(
        session.calls == [],
        "invalid input caused GET",
    )

    require(
        route_calls == [],
        "invalid input reached routing",
    )

    print(
        "AVAILABILITY_COLLECTOR_INPUT_FAIL_CLOSED_SMOKE=PASS"
    )


def main():
    found_transport_smoke()

    not_found_smoke()

    redirect_unknown_smoke()

    request_error_smoke()

    bad_http_and_identity_smoke()

    vpn_unavailable_fail_before_get_smoke()

    invalid_input_fail_before_get_smoke()

    print(
        "TEDDY_AVAILABILITY_COLLECTOR_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
