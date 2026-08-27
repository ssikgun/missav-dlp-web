from __future__ import annotations

import os

from teddy_discovery_api import (
    create_discovery_blueprint,
)

from teddy_discovery_download_api import (
    BLUEPRINT_NAME as DOWNLOAD_BLUEPRINT_NAME,
    create_discovery_download_blueprint,
)

from teddy_discovery_cover_api import (
    COVER_BLUEPRINT_NAME,
    create_cover_blueprint,
)

from teddy_discovery_preview_api import (
    PREVIEW_BLUEPRINT_NAME,
    create_preview_blueprint,
)


DISCOVERY_DB_ENV = (
    "TEDDY_DISCOVERY_DB"
)

DISCOVERY_COVER_CACHE_ENV = (
    "TEDDY_DISCOVERY_COVER_CACHE"
)

DISCOVERY_PREVIEW_CACHE_ENV = (
    "TEDDY_DISCOVERY_PREVIEW_CACHE"
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


def configured_preview_cache_path() -> str:
    return os.environ.get(
        DISCOVERY_PREVIEW_CACHE_ENV,
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
    # Discovery download is available only
    # when the canonical Discovery DB is
    # configured. It receives only a DVD ID;
    # source URL selection stays server-side.
    #
    if (
        db_path
        and DOWNLOAD_BLUEPRINT_NAME
        not in app.blueprints
    ):
        app.register_blueprint(
            create_discovery_download_blueprint(
                core,
                db_path,
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

    #
    # Preview serving is independently
    # opt-in. It shares only the Discovery
    # DB front door with Cover serving.
    #
    preview_cache_path = (
        configured_preview_cache_path()
    )

    if (
        db_path
        and preview_cache_path
        and PREVIEW_BLUEPRINT_NAME
        not in app.blueprints
    ):
        app.register_blueprint(
            create_preview_blueprint(
                db_path,
                preview_cache_path,
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
