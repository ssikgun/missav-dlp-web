from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

from flask import Flask

import teddy_discovery_runtime

from teddy_discovery_cover import (
    lookup_cover_request,
    persist_cover_cache,
)

from teddy_discovery_cover_api import (
    COVER_BLUEPRINT_NAME,
)


JPEG_BODY = (
    b"\xff\xd8\xff\xe0"
    + b"R"
    * 300
)

JPEG_SHA = hashlib.sha256(
    JPEG_BODY
).hexdigest()


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


@contextmanager
def runtime_environment(
    *,
    db_path=None,
    cache_path=None,
):
    keys = (
        teddy_discovery_runtime
        .DISCOVERY_DB_ENV,

        teddy_discovery_runtime
        .DISCOVERY_COVER_CACHE_ENV,
    )

    previous = {
        key:
            os.environ.get(
                key
            )
        for key in keys
    }

    values = {
        teddy_discovery_runtime
        .DISCOVERY_DB_ENV:
            db_path,

        teddy_discovery_runtime
        .DISCOVERY_COVER_CACHE_ENV:
            cache_path,
    }

    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(
                    key,
                    None,
                )

            else:
                os.environ[
                    key
                ] = str(
                    value
                )

        yield

    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(
                    key,
                    None,
                )

            else:
                os.environ[
                    key
                ] = value


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


def main_rules():
    return [
        "/api/discovery/categories",
        "/api/discovery/category",
        "/api/discovery/latest",
        "/api/discovery/monthly",
        "/api/discovery/weekly",
    ]


def all_rules():
    return sorted(
        main_rules()
        + [
            "/api/discovery/media/cover/<dvd_id>",
        ]
    )


def assert_read_only_routes(
    app,
):
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith(
            "/api/discovery/"
        ):
            continue

        methods = set(
            rule.methods
        )

        require(
            "GET" in methods,
            "Discovery route lost GET: "
            + rule.rule,
        )

        require(
            "POST" not in methods
            and "PUT" not in methods
            and "DELETE" not in methods
            and "PATCH" not in methods,
            "Discovery runtime exposed "
            "write method: "
            + rule.rule,
        )


def seed_cover_cache(
    db_path: Path,
    cache_dir: Path,
    dvd_id="SDNM-560",
):
    connection = sqlite3.connect(
        "file:"
        + str(
            db_path
        )
        + "?mode=ro",
        uri=True,
    )

    connection.row_factory = (
        sqlite3.Row
    )

    try:
        request_value = (
            lookup_cover_request(
                connection,
                dvd_id,
            )
        )

    finally:
        connection.close()

    payload = {
        "dvd_id":
            dvd_id,

        "content_type":
            "image/jpeg",

        "magic_type":
            "jpeg",

        "body_bytes":
            len(
                JPEG_BODY
            ),

        "sha256":
            JPEG_SHA,

        "body":
            JPEG_BODY,
    }

    path = persist_cover_cache(
        cache_dir,
        request_value,
        payload,
    )

    require(
        path.is_file(),
        "runtime smoke cover "
        "cache seed missing",
    )

    return path


def disabled_smoke():
    with runtime_environment():
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

    print(
        "DISCOVERY_RUNTIME_DISABLED_COMPAT_SMOKE=PASS"
    )


def cache_only_disabled_smoke():
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-runtime-cache-only-"
    ) as temp:
        with runtime_environment(
            cache_path=
                Path(temp),
        ):
            core = Core(
                "discovery-cache-only"
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
                "cover-cache-only runtime "
                "did not remain disabled",
            )

            require(
                discovery_rules(
                    core.app
                ) == [],
                "cover cache configured "
                "routes without DB",
            )

    print(
        "DISCOVERY_RUNTIME_COVER_CACHE_ONLY_DISABLED_SMOKE=PASS"
    )


def db_only_smoke(
    db_path: Path,
):
    with runtime_environment(
        db_path=db_path,
    ):
        core = Core(
            "discovery-db-only"
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
            "DB-only first install "
            "contract changed",
        )

        require(
            discovery_rules(
                core.app
            ) == main_rules(),
            "DB-only route set changed",
        )

        require(
            COVER_BLUEPRINT_NAME
            not in core.app.blueprints,
            "cover route installed "
            "without cache configuration",
        )

        client = core.app.test_client()

        latest = client.get(
            "/api/discovery/latest"
        )

        require(
            latest.status_code == 200,
            "DB-only Latest endpoint "
            "did not return 200",
        )

        require(
            latest.get_json()[
                "data"
            ][
                "item_count"
            ] == 50,
            "DB-only Latest count changed",
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
            "DB-only idempotency changed",
        )

        require(
            discovery_rules(
                core.app
            ) == main_rules(),
            "DB-only second install "
            "changed routes",
        )

        assert_read_only_routes(
            core.app
        )

    print(
        "DISCOVERY_RUNTIME_DB_ONLY_COMPAT_SMOKE=PASS"
    )

    print(
        "DISCOVERY_RUNTIME_IDEMPOTENT_INSTALL_SMOKE=PASS"
    )


def cover_configured_smoke(
    db_path: Path,
):
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-runtime-cover-"
    ) as temp:
        cache_dir = Path(
            temp
        )

        seed_cover_cache(
            db_path,
            cache_dir,
        )

        with runtime_environment(
            db_path=db_path,
            cache_path=cache_dir,
        ):
            core = Core(
                "discovery-cover-configured"
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
                "cover-configured runtime "
                "install result changed",
            )

            require(
                discovery_rules(
                    core.app
                ) == all_rules(),
                "cover-configured route "
                "set changed",
            )

            require(
                COVER_BLUEPRINT_NAME
                in core.app.blueprints,
                "cover blueprint missing",
            )

            client = core.app.test_client()

            response = client.get(
                "/api/discovery/media/cover/SDNM-560"
            )

            require(
                response.status_code == 200,
                "cached cover endpoint "
                "did not return 200",
            )

            require(
                response.data
                == JPEG_BODY,
                "cached cover endpoint "
                "bytes changed",
            )

            require(
                response.content_type
                == "image/jpeg",
                "cached cover endpoint "
                "MIME changed",
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
                "cover-configured "
                "idempotency changed",
            )

            require(
                discovery_rules(
                    core.app
                ) == all_rules(),
                "duplicate cover install "
                "changed routes",
            )

            assert_read_only_routes(
                core.app
            )

    print(
        "DISCOVERY_RUNTIME_COVER_CONFIGURED_INSTALL_SMOKE=PASS"
    )

    print(
        "DISCOVERY_RUNTIME_COVER_CACHE_HIT_NETWORK_ZERO_SMOKE=PASS"
    )

    print(
        "DISCOVERY_RUNTIME_ALL_ROUTES_READ_ONLY_SMOKE=PASS"
    )


def late_cover_enable_smoke(
    db_path: Path,
):
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-runtime-late-cover-"
    ) as temp:
        cache_dir = Path(
            temp
        )

        seed_cover_cache(
            db_path,
            cache_dir,
        )

        core = Core(
            "discovery-late-cover"
        )

        with runtime_environment(
            db_path=db_path,
        ):
            first = (
                teddy_discovery_runtime.install(
                    core
                )
            )

        require(
            first[
                "installed"
            ] is True,
            "late-cover first "
            "Discovery install failed",
        )

        require(
            discovery_rules(
                core.app
            ) == main_rules(),
            "late-cover DB-only "
            "route set changed",
        )

        with runtime_environment(
            db_path=db_path,
            cache_path=cache_dir,
        ):
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
                        True,

                    "reason":
                        "configured",
                },
                "late cover enable "
                "did not install cover",
            )

            require(
                discovery_rules(
                    core.app
                ) == all_rules(),
                "late cover enable "
                "route set changed",
            )

            response = (
                core.app
                .test_client()
                .get(
                    "/api/discovery/media/cover/SDNM-560"
                )
            )

            require(
                response.status_code == 200,
                "late-enabled cached cover "
                "did not return 200",
            )

            third = (
                teddy_discovery_runtime.install(
                    core
                )
            )

            require(
                third == {
                    "enabled":
                        True,

                    "installed":
                        False,

                    "reason":
                        "already-installed",
                },
                "late cover third install "
                "idempotency changed",
            )

    print(
        "DISCOVERY_RUNTIME_LATE_COVER_ENABLE_SMOKE=PASS"
    )


def missing_db_smoke():
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-runtime-missing-db-"
    ) as temp:
        missing = (
            Path(temp)
            / "missing.sqlite3"
        )

        with runtime_environment(
            db_path=missing,
        ):
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
                core.app
                .test_client()
                .get(
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

    cache_only_disabled_smoke()

    db_only_smoke(
        db_path
    )

    cover_configured_smoke(
        db_path
    )

    late_cover_enable_smoke(
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

    oracle_payload = {
        "db_env":
            teddy_discovery_runtime
            .DISCOVERY_DB_ENV,

        "cover_cache_env":
            teddy_discovery_runtime
            .DISCOVERY_COVER_CACHE_ENV,

        "main_rules":
            main_rules(),

        "all_rules":
            all_rules(),

        "cover_blueprint":
            COVER_BLUEPRINT_NAME,

        "cached_cover_sha256":
            JPEG_SHA,

        "late_cover_enable":
            True,

        "write_methods":
            0,
    }

    oracle = hashlib.sha256(
        json.dumps(
            oracle_payload,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
        ).encode(
            "utf-8"
        )
    ).hexdigest()

    print(
        "DISCOVERY_RUNTIME_COVER_ORACLE_SHA256="
        + oracle
    )

    print(
        "DISCOVERY_RUNTIME_REAL_DB_BYTE_UNCHANGED_SMOKE=PASS"
    )

    print(
        "TEDDY_DISCOVERY_RUNTIME_COVER_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
