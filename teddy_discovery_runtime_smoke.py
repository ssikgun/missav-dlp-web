from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import tempfile

from flask import Flask

import teddy_discovery_runtime


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


def file_sha256(
    path: Path,
) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


class Core:
    def __init__(
        self,
        name,
    ):
        self.app = Flask(
            name
        )


def discovery_rules(
    app,
):
    return sorted(
        rule.rule
        for rule
        in app.url_map.iter_rules()
        if rule.rule.startswith(
            "/api/discovery/"
        )
    )


def disabled_smoke():
    previous = os.environ.pop(
        teddy_discovery_runtime.DISCOVERY_DB_ENV,
        None,
    )

    try:
        core = Core(
            "discovery-disabled"
        )

        result = (
            teddy_discovery_runtime.install(
                core
            )
        )

        require(
            result == {
                "enabled":
                    False,

                "installed":
                    False,

                "reason":
                    "not-configured",
            },
            "disabled runtime result changed",
        )

        require(
            discovery_rules(
                core.app
            ) == [],
            "Discovery routes installed "
            "without DB configuration",
        )

    finally:
        if previous is not None:
            os.environ[
                teddy_discovery_runtime.DISCOVERY_DB_ENV
            ] = previous

    print(
        "DISCOVERY_RUNTIME_DISABLED_COMPAT_SMOKE=PASS"
    )


def configured_smoke(
    db_path: Path,
):
    previous = os.environ.get(
        teddy_discovery_runtime.DISCOVERY_DB_ENV
    )

    os.environ[
        teddy_discovery_runtime.DISCOVERY_DB_ENV
    ] = str(
        db_path
    )

    try:
        core = Core(
            "discovery-configured"
        )

        first = (
            teddy_discovery_runtime.install(
                core
            )
        )

        require(
            first == {
                "enabled":
                    True,

                "installed":
                    True,

                "reason":
                    "configured",
            },
            "configured runtime "
            "install result changed",
        )

        expected_rules = [
            "/api/discovery/categories",
            "/api/discovery/category",
            "/api/discovery/latest",
            "/api/discovery/monthly",
            "/api/discovery/weekly",
        ]

        require(
            discovery_rules(
                core.app
            ) == expected_rules,
            "Discovery route set changed",
        )

        second = (
            teddy_discovery_runtime.install(
                core
            )
        )

        require(
            second == {
                "enabled":
                    True,

                "installed":
                    False,

                "reason":
                    "already-installed",
            },
            "Discovery runtime "
            "idempotency changed",
        )

        require(
            discovery_rules(
                core.app
            ) == expected_rules,
            "duplicate install changed "
            "Discovery routes",
        )

        client = core.app.test_client()

        latest = client.get(
            "/api/discovery/latest"
        )

        require(
            latest.status_code == 200,
            "configured Latest endpoint "
            "did not return 200",
        )

        latest_json = (
            latest.get_json()
        )

        require(
            latest_json[
                "status"
            ] == "success",
            "configured Latest envelope "
            "changed",
        )

        require(
            latest_json[
                "data"
            ][
                "item_count"
            ] == 50,
            "configured Latest count changed",
        )

        for path in expected_rules:
            methods = None

            for rule in (
                core.app.url_map.iter_rules()
            ):
                if rule.rule == path:
                    methods = set(
                        rule.methods
                    )
                    break

            require(
                methods is not None,
                "Discovery rule disappeared",
            )

            require(
                "GET" in methods,
                "Discovery route lost GET",
            )

            require(
                "POST" not in methods
                and "PUT" not in methods
                and "DELETE" not in methods,
                "Discovery runtime exposed "
                "write method",
            )

    finally:
        if previous is None:
            os.environ.pop(
                teddy_discovery_runtime.DISCOVERY_DB_ENV,
                None,
            )
        else:
            os.environ[
                teddy_discovery_runtime.DISCOVERY_DB_ENV
            ] = previous

    print(
        "DISCOVERY_RUNTIME_CONFIGURED_INSTALL_SMOKE=PASS"
    )

    print(
        "DISCOVERY_RUNTIME_IDEMPOTENT_INSTALL_SMOKE=PASS"
    )

    print(
        "DISCOVERY_RUNTIME_GET_ONLY_ROUTE_SMOKE=PASS"
    )


def missing_db_smoke():
    previous = os.environ.get(
        teddy_discovery_runtime.DISCOVERY_DB_ENV
    )

    try:
        with tempfile.TemporaryDirectory(
            prefix=
                "teddy-discovery-runtime-missing-"
        ) as temp:
            missing = (
                Path(temp)
                / "missing.sqlite3"
            )

            os.environ[
                teddy_discovery_runtime.DISCOVERY_DB_ENV
            ] = str(
                missing
            )

            core = Core(
                "discovery-missing-db"
            )

            result = (
                teddy_discovery_runtime.install(
                    core
                )
            )

            require(
                result[
                    "enabled"
                ] is True,
                "configured missing DB "
                "unexpectedly disabled",
            )

            response = (
                core.app.test_client().get(
                    "/api/discovery/latest"
                )
            )

            require(
                response.status_code == 503,
                "missing DB did not "
                "fail closed with 503",
            )

            value = response.get_json()

            require(
                value[
                    "status"
                ] == "error",
                "missing DB error "
                "envelope changed",
            )

            require(
                value[
                    "error"
                ][
                    "code"
                ]
                == "discovery_unavailable",
                "missing DB error "
                "code changed",
            )

    finally:
        if previous is None:
            os.environ.pop(
                teddy_discovery_runtime.DISCOVERY_DB_ENV,
                None,
            )
        else:
            os.environ[
                teddy_discovery_runtime.DISCOVERY_DB_ENV
            ] = previous

    print(
        "DISCOVERY_RUNTIME_MISSING_DB_FAIL_CLOSED_SMOKE=PASS"
    )


def main():
    if len(
        sys.argv
    ) != 2:
        raise RuntimeError(
            "usage: "
            "teddy_discovery_runtime_smoke.py "
            "<stage5-db>"
        )

    db_path = Path(
        sys.argv[1]
    )

    before = file_sha256(
        db_path
    )

    disabled_smoke()

    configured_smoke(
        db_path
    )

    missing_db_smoke()

    after = file_sha256(
        db_path
    )

    require(
        after == before,
        "runtime smoke changed "
        "real Stage 5 DB bytes",
    )

    print(
        "DISCOVERY_RUNTIME_REAL_DB_BYTE_UNCHANGED_SMOKE=PASS"
    )

    print(
        "TEDDY_DISCOVERY_RUNTIME_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
