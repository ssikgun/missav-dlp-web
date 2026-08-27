#!/usr/bin/env python3

from __future__ import annotations

import hmac
from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer,
)
import json
import os
from pathlib import Path
import signal
import threading
import time
from typing import Callable


DEFAULT_BIND = "0.0.0.0"
DEFAULT_PORT = 18080
DEFAULT_TOKEN_FILE = (
    "/run/secrets/teddy-selkies-control/token"
)


class ControlState:
    def __init__(
        self,
        *,
        token: str,
        role: str,
        restart_fn: Callable[[], None],
        restart_delay: float = 0.25,
    ):
        self.token = token
        self.role = role
        self.restart_fn = restart_fn
        self.restart_delay = restart_delay

        self.started_wall = time.time()
        self.started_mono = time.monotonic()

        self._restart_lock = threading.Lock()
        self._restart_scheduled = False


    def uptime_seconds(
        self,
    ) -> int:
        return max(
            0,
            int(
                time.monotonic()
                - self.started_mono
            ),
        )


    def schedule_restart(
        self,
    ) -> bool:
        with self._restart_lock:
            if self._restart_scheduled:
                return False

            self._restart_scheduled = True

        thread = threading.Thread(
            target=self._restart_after_response,
            name="teddy-selkies-self-restart",
            daemon=True,
        )

        thread.start()

        return True


    def _restart_after_response(
        self,
    ):
        time.sleep(
            self.restart_delay
        )

        self.restart_fn()


def load_token(
    path: str,
) -> str:
    token_path = Path(
        path
    )

    token = token_path.read_text(
        encoding="utf-8"
    ).strip()

    if len(token) < 32:
        raise RuntimeError(
            "Selkies control token must be "
            "at least 32 characters"
        )

    return token


def authorized(
    supplied_header: str | None,
    expected_token: str,
) -> bool:
    if not supplied_header:
        return False

    prefix = "Bearer "

    if not supplied_header.startswith(
        prefix
    ):
        return False

    supplied = supplied_header[
        len(prefix):
    ]

    return hmac.compare_digest(
        supplied,
        expected_token,
    )


def make_handler(
    state: ControlState,
):
    class Handler(
        BaseHTTPRequestHandler
    ):
        server_version = (
            "TeddySelkiesControl"
        )

        sys_version = ""


        def log_message(
            self,
            format,
            *args,
        ):
            return


        def _json(
            self,
            status_code: int,
            payload: dict,
        ):
            body = json.dumps(
                payload,
                ensure_ascii=False,
                separators=(
                    ",",
                    ":",
                ),
            ).encode(
                "utf-8"
            )

            self.send_response(
                status_code
            )

            self.send_header(
                "Content-Type",
                "application/json; charset=utf-8",
            )

            self.send_header(
                "Cache-Control",
                "no-store",
            )

            self.send_header(
                "X-Content-Type-Options",
                "nosniff",
            )

            self.send_header(
                "Content-Length",
                str(
                    len(body)
                ),
            )

            self.end_headers()

            self.wfile.write(
                body
            )


        def _require_auth(
            self,
        ) -> bool:
            if authorized(
                self.headers.get(
                    "Authorization"
                ),
                state.token,
            ):
                return True

            self._json(
                401,
                {
                    "status":
                        "error",

                    "message":
                        "unauthorized",
                },
            )

            return False


        def do_GET(
            self,
        ):
            if self.path != "/status":
                self._json(
                    404,
                    {
                        "status":
                            "error",

                        "message":
                            "not found",
                    },
                )

                return

            if not self._require_auth():
                return

            self._json(
                200,
                {
                    "status":
                        "success",

                    "role":
                        state.role,

                    "uptime_seconds":
                        state.uptime_seconds(),

                    "restart_pending":
                        state._restart_scheduled,
                },
            )


        def do_POST(
            self,
        ):
            if self.path != "/restart":
                self._json(
                    404,
                    {
                        "status":
                            "error",

                        "message":
                            "not found",
                    },
                )

                return

            if not self._require_auth():
                return

            try:
                content_length = int(
                    self.headers.get(
                        "Content-Length",
                        "0",
                    )
                )

            except ValueError:
                content_length = -1

            if content_length != 0:
                self._json(
                    400,
                    {
                        "status":
                            "error",

                        "message":
                            "request body not allowed",
                    },
                )

                return

            scheduled = (
                state.schedule_restart()
            )

            if not scheduled:
                self._json(
                    409,
                    {
                        "status":
                            "error",

                        "message":
                            "restart already pending",
                    },
                )

                return

            self._json(
                202,
                {
                    "status":
                        "accepted",

                    "role":
                        state.role,

                    "message":
                        "restart scheduled",
                },
            )


        def do_PUT(
            self,
        ):
            self._json(
                405,
                {
                    "status":
                        "error",

                    "message":
                        "method not allowed",
                },
            )


        def do_DELETE(
            self,
        ):
            self._json(
                405,
                {
                    "status":
                        "error",

                    "message":
                        "method not allowed",
                },
            )


        def do_PATCH(
            self,
        ):
            self._json(
                405,
                {
                    "status":
                        "error",

                    "message":
                        "method not allowed",
                },
            )


    return Handler


def serve(
    *,
    bind: str,
    port: int,
    token: str,
    role: str,
    restart_fn: Callable[[], None],
):
    state = ControlState(
        token=token,
        role=role,
        restart_fn=restart_fn,
    )

    server = ThreadingHTTPServer(
        (
            bind,
            port,
        ),
        make_handler(
            state
        ),
    )

    server.serve_forever()


def main():
    bind = os.environ.get(
        "TEDDY_SELKIES_CONTROL_BIND",
        DEFAULT_BIND,
    )

    port = int(
        os.environ.get(
            "TEDDY_SELKIES_CONTROL_PORT",
            str(
                DEFAULT_PORT
            ),
        )
    )

    role = os.environ.get(
        "TEDDY_SELKIES_ROLE",
        "unknown",
    ).strip()

    if role not in {
        "desktop",
        "mobile",
    }:
        raise RuntimeError(
            "TEDDY_SELKIES_ROLE must be "
            "desktop or mobile"
        )

    token_file = os.environ.get(
        "TEDDY_SELKIES_CONTROL_TOKEN_FILE",
        DEFAULT_TOKEN_FILE,
    )

    token = load_token(
        token_file
    )

    print(
        (
            "Teddy Selkies control listening "
            f"on {bind}:{port} "
            f"role={role}"
        ),
        flush=True,
    )

    serve(
        bind=bind,
        port=port,
        token=token,
        role=role,
        restart_fn=lambda: os.kill(
            1,
            signal.SIGTERM,
        ),
    )


if __name__ == "__main__":
    main()
