from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable
import urllib.error
import urllib.request

from flask import (
    Blueprint,
    jsonify,
)


BLUEPRINT_NAME = (
    "teddy_selkies_control_api"
)

DEFAULT_TOKEN_FILE = (
    "/run/secrets/"
    "teddy-selkies-control/token"
)

TOKEN_FILE_ENV = (
    "TEDDY_SELKIES_CONTROL_TOKEN_FILE"
)

CONTROL_TIMEOUT_SECONDS = 3

MAX_RESPONSE_BYTES = (
    64 * 1024
)

PUBLIC_UNAVAILABLE_MESSAGE = (
    "Selkies control unavailable"
)

TARGETS = {
    "desktop": (
        "http://"
        "vpn-browser-selkies"
        ":18080"
    ),

    "mobile": (
        "http://"
        "vpn-browser-mobile-selkies"
        ":18080"
    ),
}


class ControlUnavailable(
    RuntimeError
):
    pass


class NoRedirectHandler(
    urllib.request.HTTPRedirectHandler
):
    def redirect_request(
        self,
        req,
        fp,
        code,
        msg,
        headers,
        newurl,
    ):
        return None


def configured_token_file() -> str:
    return os.environ.get(
        TOKEN_FILE_ENV,
        DEFAULT_TOKEN_FILE,
    ).strip()


def load_token(
    path: str | None = None,
) -> str:
    token_path = Path(
        path
        or configured_token_file()
    )

    token = token_path.read_text(
        encoding="utf-8"
    ).strip()

    if len(token) < 32:
        raise ControlUnavailable(
            "invalid control token"
        )

    return token


def _opener():
    return urllib.request.build_opener(
        NoRedirectHandler()
    )


def _read_json_response(
    response,
) -> dict:
    status = int(
        response.getcode()
    )

    content_type = str(
        response.headers.get(
            "Content-Type",
            "",
        )
    ).split(
        ";",
        1,
    )[0].strip().lower()

    if content_type != "application/json":
        raise ControlUnavailable(
            "invalid helper content type"
        )

    raw = response.read(
        MAX_RESPONSE_BYTES + 1
    )

    if len(raw) > MAX_RESPONSE_BYTES:
        raise ControlUnavailable(
            "helper response too large"
        )

    try:
        payload = json.loads(
            raw.decode(
                "utf-8"
            )
        )

    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ControlUnavailable(
            "invalid helper response"
        ) from exc

    if not isinstance(
        payload,
        dict,
    ):
        raise ControlUnavailable(
            "invalid helper payload"
        )

    payload[
        "_http_status"
    ] = status

    return payload


def request_helper(
    role: str,
    action: str,
    token: str,
    *,
    opener=None,
) -> dict:
    if role not in TARGETS:
        raise KeyError(
            role
        )

    if action == "status":
        path = "/status"
        method = "GET"
        data = None
        expected_status = 200

    elif action == "restart":
        path = "/restart"
        method = "POST"
        data = b""
        expected_status = 202

    else:
        raise ValueError(
            "unsupported control action"
        )

    url = (
        TARGETS[
            role
        ]
        + path
    )

    request = urllib.request.Request(
        url,
        method=method,
        data=data,
        headers={
            "Authorization":
                "Bearer "
                + token,

            "Accept":
                "application/json",
        },
    )

    client = (
        opener
        if opener is not None
        else _opener()
    )

    try:
        with client.open(
            request,
            timeout=(
                CONTROL_TIMEOUT_SECONDS
            ),
        ) as response:
            payload = (
                _read_json_response(
                    response
                )
            )

    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        OSError,
    ) as exc:
        raise ControlUnavailable(
            "helper request failed"
        ) from exc

    status = payload.pop(
        "_http_status"
    )

    if status != expected_status:
        raise ControlUnavailable(
            "unexpected helper status"
        )

    if payload.get(
        "role"
    ) != role:
        raise ControlUnavailable(
            "helper role mismatch"
        )

    if action == "status":
        if payload.get(
            "status"
        ) != "success":
            raise ControlUnavailable(
                "invalid status response"
            )

        uptime = payload.get(
            "uptime_seconds"
        )

        pending = payload.get(
            "restart_pending"
        )

        if (
            not isinstance(
                uptime,
                int,
            )
            or isinstance(
                uptime,
                bool,
            )
            or uptime < 0
            or not isinstance(
                pending,
                bool,
            )
        ):
            raise ControlUnavailable(
                "invalid status payload"
            )

        return {
            "status":
                "success",

            "role":
                role,

            "uptime_seconds":
                uptime,

            "restart_pending":
                pending,
        }

    if payload.get(
        "status"
    ) != "accepted":
        raise ControlUnavailable(
            "invalid restart response"
        )

    return {
        "status":
            "accepted",

        "role":
            role,

        "message":
            "restart scheduled",
    }


def create_blueprint(
    *,
    token_loader: Callable[[], str]
        = load_token,
    opener=None,
):
    blueprint = Blueprint(
        BLUEPRINT_NAME,
        __name__,
    )

    def unavailable():
        return jsonify(
            {
                "status":
                    "error",

                "message":
                    PUBLIC_UNAVAILABLE_MESSAGE,
            }
        ), 503

    def unknown_role():
        return jsonify(
            {
                "status":
                    "error",

                "message":
                    "unknown Selkies target",
            }
        ), 404

    @blueprint.get(
        "/api/system/selkies/"
        "<role>/status"
    )
    def status(
        role,
    ):
        if role not in TARGETS:
            return unknown_role()

        try:
            token = token_loader()

            payload = request_helper(
                role,
                "status",
                token,
                opener=opener,
            )

        except Exception:
            return unavailable()

        return jsonify(
            payload
        ), 200

    @blueprint.post(
        "/api/system/selkies/"
        "<role>/restart"
    )
    def restart(
        role,
    ):
        if role not in TARGETS:
            return unknown_role()

        try:
            token = token_loader()

            payload = request_helper(
                role,
                "restart",
                token,
                opener=opener,
            )

        except Exception:
            return unavailable()

        return jsonify(
            payload
        ), 202

    return blueprint

def install(
    core,
    *,
    token_loader: Callable[[], str]
        = load_token,
    opener=None,
) -> dict:
    app = getattr(
        core,
        "app",
        None,
    )

    if app is None:
        raise ValueError(
            "Selkies control runtime "
            "requires core.app"
        )

    if (
        BLUEPRINT_NAME
        in app.blueprints
    ):
        return {
            "enabled":
                True,

            "installed":
                False,

            "reason":
                "already-installed",
        }

    app.register_blueprint(
        create_blueprint(
            token_loader=token_loader,
            opener=opener,
        )
    )

    return {
        "enabled":
            True,

        "installed":
            True,

        "reason":
            "configured",
    }

