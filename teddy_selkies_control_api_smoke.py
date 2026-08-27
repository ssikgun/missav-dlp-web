#!/usr/bin/env python3

from __future__ import annotations

import json
import urllib.error

from flask import Flask

import teddy_selkies_control_api as api


TOKEN = (
    "backend-control-"
    "0123456789abcdef"
    "0123456789abcdef"
)


class FakeHeaders:
    def __init__(
        self,
        content_type=(
            "application/json; "
            "charset=utf-8"
        ),
    ):
        self.content_type = (
            content_type
        )

    def get(
        self,
        key,
        default=None,
    ):
        if (
            key.lower()
            == "content-type"
        ):
            return self.content_type

        return default


class FakeResponse:
    def __init__(
        self,
        status,
        payload,
        *,
        content_type=(
            "application/json"
        ),
    ):
        self.status = status

        self.raw = json.dumps(
            payload,
            separators=(",", ":"),
        ).encode(
            "utf-8"
        )

        self.headers = FakeHeaders(
            content_type
        )

    def getcode(
        self,
    ):
        return self.status

    def read(
        self,
        size=-1,
    ):
        if size is None or size < 0:
            return self.raw

        return self.raw[
            :size
        ]

    def __enter__(
        self,
    ):
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        tb,
    ):
        return False


class FakeOpener:
    def __init__(
        self,
    ):
        self.calls = []
        self.mode = "normal"

    def open(
        self,
        request,
        timeout=None,
    ):
        self.calls.append(
            {
                "url":
                    request.full_url,

                "method":
                    request.get_method(),

                "authorization":
                    request.get_header(
                        "Authorization"
                    ),

                "timeout":
                    timeout,

                "data":
                    request.data,
            }
        )

        if self.mode == "redirect":
            raise urllib.error.HTTPError(
                request.full_url,
                302,
                "Found",
                {
                    "Location":
                        "http://example.invalid/"
                },
                None,
            )

        if self.mode == "bad-json":
            response = FakeResponse(
                200,
                {},
            )

            response.raw = (
                b"not-json"
            )

            return response

        if self.mode == "wrong-role":
            return FakeResponse(
                200,
                {
                    "status":
                        "success",

                    "role":
                        "mobile",

                    "uptime_seconds":
                        10,

                    "restart_pending":
                        False,
                },
            )

        if (
            request.full_url
            == (
                api.TARGETS[
                    "desktop"
                ]
                + "/status"
            )
        ):
            return FakeResponse(
                200,
                {
                    "status":
                        "success",

                    "role":
                        "desktop",

                    "uptime_seconds":
                        123,

                    "restart_pending":
                        False,
                },
            )

        if (
            request.full_url
            == (
                api.TARGETS[
                    "mobile"
                ]
                + "/status"
            )
        ):
            return FakeResponse(
                200,
                {
                    "status":
                        "success",

                    "role":
                        "mobile",

                    "uptime_seconds":
                        456,

                    "restart_pending":
                        False,
                },
            )

        if (
            request.full_url
            == (
                api.TARGETS[
                    "desktop"
                ]
                + "/restart"
            )
        ):
            return FakeResponse(
                202,
                {
                    "status":
                        "accepted",

                    "role":
                        "desktop",

                    "message":
                        "restart scheduled",
                },
            )

        if (
            request.full_url
            == (
                api.TARGETS[
                    "mobile"
                ]
                + "/restart"
            )
        ):
            return FakeResponse(
                202,
                {
                    "status":
                        "accepted",

                    "role":
                        "mobile",

                    "message":
                        "restart scheduled",
                },
            )

        raise AssertionError(
            "unexpected outbound URL: "
            + request.full_url
        )


def make_app(
    opener,
    token_loader=(
        lambda: TOKEN
    ),
):
    app = Flask(
        __name__
    )

    app.register_blueprint(
        api.create_blueprint(
            token_loader=(
                token_loader
            ),
            opener=opener,
        )
    )

    return app


opener = FakeOpener()
app = make_app(
    opener
)
client = app.test_client()


response = client.get(
    "/api/system/selkies/"
    "desktop/status"
)

assert response.status_code == 200

payload = response.get_json()

assert payload == {
    "status":
        "success",

    "role":
        "desktop",

    "uptime_seconds":
        123,

    "restart_pending":
        False,
}

assert opener.calls[-1][
    "url"
] == (
    "http://"
    "vpn-browser-selkies"
    ":18080/status"
)

assert opener.calls[-1][
    "method"
] == "GET"

assert opener.calls[-1][
    "authorization"
] == (
    "Bearer "
    + TOKEN
)

assert opener.calls[-1][
    "timeout"
] == 3

print(
    "BACKEND_DESKTOP_STATUS_FIXED_TARGET=PASS"
)


response = client.get(
    "/api/system/selkies/"
    "mobile/status"
    "?target=http://example.invalid/"
)

assert response.status_code == 200

assert opener.calls[-1][
    "url"
] == (
    "http://"
    "vpn-browser-mobile-selkies"
    ":18080/status"
)

assert (
    "example.invalid"
    not in opener.calls[-1][
        "url"
    ]
)

print(
    "BACKEND_QUERY_CANNOT_OVERRIDE_TARGET=PASS"
)


response = client.post(
    "/api/system/selkies/"
    "desktop/restart"
)

assert response.status_code == 202

payload = response.get_json()

assert payload == {
    "status":
        "accepted",

    "role":
        "desktop",

    "message":
        "restart scheduled",
}

assert opener.calls[-1][
    "url"
] == (
    "http://"
    "vpn-browser-selkies"
    ":18080/restart"
)

assert opener.calls[-1][
    "method"
] == "POST"

assert opener.calls[-1][
    "data"
] == b""

print(
    "BACKEND_DESKTOP_RESTART_FIXED_TARGET=PASS"
)


response = client.post(
    "/api/system/selkies/"
    "mobile/restart"
)

assert response.status_code == 202

assert opener.calls[-1][
    "url"
] == (
    "http://"
    "vpn-browser-mobile-selkies"
    ":18080/restart"
)

print(
    "BACKEND_MOBILE_RESTART_FIXED_TARGET=PASS"
)


before_calls = len(
    opener.calls
)

response = client.get(
    "/api/system/selkies/"
    "anything/status"
)

assert response.status_code == 404
assert len(
    opener.calls
) == before_calls

response = client.post(
    "/api/system/selkies/"
    "http:%2F%2Fevil/restart"
)

assert response.status_code == 404
assert len(
    opener.calls
) == before_calls

print(
    "BACKEND_UNKNOWN_TARGET_NO_NETWORK=PASS"
)


response = client.post(
    "/api/system/selkies/"
    "desktop/status"
)

assert response.status_code == 405

response = client.get(
    "/api/system/selkies/"
    "desktop/restart"
)

assert response.status_code == 405

response = client.put(
    "/api/system/selkies/"
    "desktop/restart"
)

assert response.status_code == 405

response = client.delete(
    "/api/system/selkies/"
    "desktop/restart"
)

assert response.status_code == 405

print(
    "BACKEND_METHOD_BOUNDARY=PASS"
)


redirect_opener = FakeOpener()
redirect_opener.mode = (
    "redirect"
)

redirect_app = make_app(
    redirect_opener
)

redirect_client = (
    redirect_app.test_client()
)

response = redirect_client.get(
    "/api/system/selkies/"
    "desktop/status"
)

assert response.status_code == 503

payload = response.get_json()

assert payload == {
    "status":
        "error",

    "message":
        (
            "Selkies control "
            "unavailable"
        ),
}

assert (
    "example.invalid"
    not in json.dumps(
        payload
    )
)

print(
    "BACKEND_REDIRECT_FAIL_CLOSED=PASS"
)


bad_json_opener = FakeOpener()
bad_json_opener.mode = (
    "bad-json"
)

bad_json_app = make_app(
    bad_json_opener
)

response = (
    bad_json_app.test_client().get(
        "/api/system/selkies/"
        "desktop/status"
    )
)

assert response.status_code == 503

print(
    "BACKEND_BAD_HELPER_RESPONSE_FAIL_CLOSED=PASS"
)


wrong_role_opener = FakeOpener()
wrong_role_opener.mode = (
    "wrong-role"
)

wrong_role_app = make_app(
    wrong_role_opener
)

response = (
    wrong_role_app.test_client().get(
        "/api/system/selkies/"
        "desktop/status"
    )
)

assert response.status_code == 503

print(
    "BACKEND_HELPER_ROLE_MISMATCH_FAIL_CLOSED=PASS"
)


missing_token_app = make_app(
    FakeOpener(),
    token_loader=(
        lambda: (
            (_ for _ in ())
            .throw(
                FileNotFoundError(
                    "missing token"
                )
            )
        )
    ),
)

response = (
    missing_token_app
    .test_client()
    .get(
        "/api/system/selkies/"
        "desktop/status"
    )
)

assert response.status_code == 503

payload_text = response.get_data(
    as_text=True
)

assert TOKEN not in payload_text

assert (
    "vpn-browser-selkies"
    not in payload_text
)

print(
    "BACKEND_TOKEN_FAILURE_NO_SECRET_LEAK=PASS"
)


all_urls = [
    call[
        "url"
    ]
    for call
    in opener.calls
]

assert all(
    url.startswith(
        (
            "http://"
            "vpn-browser-selkies"
            ":18080/"
        )
    )
    or url.startswith(
        (
            "http://"
            "vpn-browser-mobile-selkies"
            ":18080/"
        )
    )
    for url
    in all_urls
)

assert set(
    api.TARGETS
) == {
    "desktop",
    "mobile",
}

print(
    "BACKEND_FIXED_TARGET_SET_EXACT=PASS"
)


original_getproxies = (
    api.urllib.request.getproxies
)

sentinel_proxy = (
    "http://127.0.0.1:48888"
)

api.urllib.request.getproxies = (
    lambda: {
        "http":
            sentinel_proxy,
    }
)

try:
    direct_opener = api._opener()

finally:
    api.urllib.request.getproxies = (
        original_getproxies
    )

proxy_handlers = [
    handler
    for handler
    in direct_opener.handlers
    if isinstance(
        handler,
        api.urllib.request.ProxyHandler,
    )
]

assert not any(
    handler.proxies.get(
        "http"
    )
    == sentinel_proxy
    for handler
    in proxy_handlers
)

print(
    "BACKEND_ENV_PROXY_BYPASS=PASS"
)


assert (
    api.DEFAULT_TOKEN_FILE
    == (
        "/run/secrets/"
        "teddy-selkies-control/token"
    )
)

assert (
    "/var/run/docker.sock"
    not in open(
        "teddy_selkies_control_api.py",
        encoding="utf-8",
    ).read()
)

print(
    "BACKEND_DOCKER_SOCKET_DEPENDENCY=0"
)


print(
    "TEDDY_SELKIES_BACKEND_CONTROL_API_SMOKE=PASS"
)
