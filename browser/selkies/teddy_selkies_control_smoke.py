#!/usr/bin/env python3

from __future__ import annotations

import http.client
import importlib.util
import json
from pathlib import Path
import threading
import time


HERE = Path(
    __file__
).resolve().parent

MODULE_PATH = (
    HERE
    / "teddy_selkies_control.py"
)

spec = importlib.util.spec_from_file_location(
    "teddy_selkies_control",
    MODULE_PATH,
)

if (
    spec is None
    or spec.loader is None
):
    raise RuntimeError(
        "module import failed"
    )

module = importlib.util.module_from_spec(
    spec
)

spec.loader.exec_module(
    module
)


TOKEN = (
    "teddy-selkies-control-"
    "0123456789abcdef0123456789abcdef"
)

RESTART_CALLED = (
    threading.Event()
)


def fake_restart():
    RESTART_CALLED.set()


state = module.ControlState(
    token=TOKEN,
    role="desktop",
    restart_fn=fake_restart,
    restart_delay=0.01,
)

server = module.ThreadingHTTPServer(
    (
        "127.0.0.1",
        0,
    ),
    module.make_handler(
        state
    ),
)

thread = threading.Thread(
    target=server.serve_forever,
    daemon=True,
)

thread.start()

PORT = server.server_address[
    1
]


def request(
    method,
    path,
    *,
    token=None,
    body=None,
):
    conn = http.client.HTTPConnection(
        "127.0.0.1",
        PORT,
        timeout=3,
    )

    headers = {}

    if token is not None:
        headers[
            "Authorization"
        ] = (
            "Bearer "
            + token
        )

    if body is None:
        body_bytes = None

    else:
        body_bytes = body.encode(
            "utf-8"
        )

        headers[
            "Content-Length"
        ] = str(
            len(
                body_bytes
            )
        )

    conn.request(
        method,
        path,
        body=body_bytes,
        headers=headers,
    )

    response = conn.getresponse()

    raw = response.read()

    status = response.status

    response_headers = {
        key.lower():
            value
        for key, value
        in response.getheaders()
    }

    payload = (
        json.loads(
            raw.decode(
                "utf-8"
            )
        )
        if raw
        else None
    )

    conn.close()

    return (
        status,
        response_headers,
        payload,
        raw,
    )


try:
    status, headers, payload, raw = request(
        "GET",
        "/status",
    )

    assert status == 401
    assert payload[
        "message"
    ] == "unauthorized"

    print(
        "CONTROL_UNAUTH_STATUS=PASS"
    )


    status, _, payload, _ = request(
        "GET",
        "/status",
        token="wrong-token",
    )

    assert status == 401

    print(
        "CONTROL_BAD_TOKEN=PASS"
    )


    status, headers, payload, raw = request(
        "GET",
        "/status",
        token=TOKEN,
    )

    assert status == 200
    assert payload[
        "status"
    ] == "success"
    assert payload[
        "role"
    ] == "desktop"
    assert isinstance(
        payload[
            "uptime_seconds"
        ],
        int,
    )
    assert payload[
        "restart_pending"
    ] is False

    assert headers[
        "cache-control"
    ] == "no-store"

    assert TOKEN.encode(
        "utf-8"
    ) not in raw

    print(
        "CONTROL_AUTH_STATUS=PASS"
    )


    status, _, payload, _ = request(
        "GET",
        "/restart",
        token=TOKEN,
    )

    assert status == 404

    print(
        "CONTROL_RESTART_GET_BLOCKED=PASS"
    )


    status, _, payload, _ = request(
        "POST",
        "/restart",
        token=TOKEN,
        body="{}",
    )

    assert status == 400
    assert not RESTART_CALLED.is_set()

    print(
        "CONTROL_RESTART_BODY_BLOCKED=PASS"
    )


    status, _, payload, raw = request(
        "POST",
        "/restart",
        token=TOKEN,
    )

    assert status == 202
    assert payload == {
        "status":
            "accepted",

        "role":
            "desktop",

        "message":
            "restart scheduled",
    }

    assert TOKEN.encode(
        "utf-8"
    ) not in raw

    assert RESTART_CALLED.wait(
        timeout=2
    )

    print(
        "CONTROL_RESTART_ACCEPTED=PASS"
    )


    status, _, payload, _ = request(
        "POST",
        "/restart",
        token=TOKEN,
    )

    assert status == 409

    print(
        "CONTROL_DUPLICATE_RESTART_BLOCKED=PASS"
    )


    status, _, payload, _ = request(
        "PUT",
        "/status",
        token=TOKEN,
    )

    assert status == 405

    status, _, payload, _ = request(
        "DELETE",
        "/restart",
        token=TOKEN,
    )

    assert status == 405

    print(
        "CONTROL_WRITE_METHOD_BOUNDARY=PASS"
    )


    assert module.authorized(
        "Bearer "
        + TOKEN,
        TOKEN,
    )

    assert not module.authorized(
        "Basic "
        + TOKEN,
        TOKEN,
    )

    print(
        "CONTROL_BEARER_AUTH_ONLY=PASS"
    )


    print(
        "TEDDY_SELKIES_CONTROL_HELPER_SMOKE=PASS"
    )

finally:
    server.shutdown()

    server.server_close()
