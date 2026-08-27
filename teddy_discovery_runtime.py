from __future__ import annotations

import os

from teddy_discovery_api import (
    create_discovery_blueprint,
)

from teddy_discovery_cover_api import (
    COVER_BLUEPRINT_NAME,
    create_cover_blueprint,
)


DISCOVERY_DB_ENV = (
    "TEDDY_DISCOVERY_DB"
)

DISCOVERY_COVER_CACHE_ENV = (
    "TEDDY_DISCOVERY_COVER_CACHE"
)

DISCOVERY_BLUEPRINT_NAME = (
    "teddy_discovery_api"
)


def configured_db_path() -> str:
    return os.environ.get(
        DISCOVERY_DB_ENV,
        "",
    ).strip()


def configured_cover_cache_path() -> str:
    return os.environ.get(
        DISCOVERY_COVER_CACHE_ENV,
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

    discovery_installed = (
        DISCOVERY_BLUEPRINT_NAME
        in app.blueprints
    )

    db_path = configured_db_path()

    #
    # Preserve the original disabled
    # behavior when no Discovery DB has
    # ever been installed/configured.
    #
    if (
        not discovery_installed
        and not db_path
    ):
        return {
            "enabled":
                False,

            "installed":
                False,

            "reason":
                "not-configured",
        }

    installed_any = False

    if not discovery_installed:
        app.register_blueprint(
            create_discovery_blueprint(
                db_path
            )
        )

        installed_any = True

    #
    # Cover serving is deliberately
    # opt-in. The DB alone keeps the
    # pre-cover runtime behavior.
    #
    cover_cache_path = (
        configured_cover_cache_path()
    )

    if (
        db_path
        and cover_cache_path
        and COVER_BLUEPRINT_NAME
        not in app.blueprints
    ):
        app.register_blueprint(
            create_cover_blueprint(
                db_path,
                cover_cache_path,
            )
        )

        installed_any = True

    if installed_any:
        return {
            "enabled":
                True,

            "installed":
                True,

            "reason":
                "configured",
        }

    return {
        "enabled":
            True,

        "installed":
            False,

        "reason":
            "already-installed",
    }
