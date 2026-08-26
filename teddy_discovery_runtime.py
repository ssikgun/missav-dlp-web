from __future__ import annotations

import os

from teddy_discovery_api import (
    create_discovery_blueprint,
)


DISCOVERY_DB_ENV = (
    "TEDDY_DISCOVERY_DB"
)

DISCOVERY_BLUEPRINT_NAME = (
    "teddy_discovery_api"
)


def configured_db_path() -> str:
    return os.environ.get(
        DISCOVERY_DB_ENV,
        "",
    ).strip()


def install(core) -> dict:
    app = getattr(
        core,
        "app",
        None,
    )

    if app is None:
        raise ValueError(
            "Discovery runtime requires "
            "core.app"
        )

    if (
        DISCOVERY_BLUEPRINT_NAME
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

    db_path = configured_db_path()

    if not db_path:
        return {
            "enabled":
                False,

            "installed":
                False,

            "reason":
                "not-configured",
        }

    app.register_blueprint(
        create_discovery_blueprint(
            db_path
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
