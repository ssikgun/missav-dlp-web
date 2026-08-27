from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any

from flask import (
    Blueprint,
    Response,
    jsonify,
    request,
)

from teddy_discovery_availability import (
    canonical_dvd_id,
)

from teddy_discovery_cover import (
    CoverNotFound,
    CoverUnavailable,
    CoverValidationError,
    get_cover,
)


COVER_API_PREFIX = (
    "/api/discovery/media"
)

COVER_BLUEPRINT_NAME = (
    "teddy_discovery_cover_api"
)


def _error_response(
    code: str,
    message: str,
    status_code: int,
):
    return (
        jsonify({
            "status":
                "error",

            "error": {
                "code":
                    code,

                "message":
                    message,
            },
        }),
        status_code,
    )


def _configured_path(
    value: Any,
    *,
    label: str,
) -> Path:
    if value is None:
        raise ValueError(
            label
            + " path required"
        )

    raw = str(
        value
    ).strip()

    if not raw:
        raise ValueError(
            label
            + " path required"
        )

    return Path(
        raw
    ).expanduser().resolve()


def _open_readonly(
    db_path: Path,
) -> sqlite3.Connection:
    if not db_path.is_file():
        raise CoverUnavailable(
            "Discovery database unavailable"
        )

    try:
        connection = sqlite3.connect(
            "file:"
            + str(
                db_path
            )
            + "?mode=ro",
            uri=True,
        )

    except sqlite3.Error as exc:
        raise CoverUnavailable(
            "Discovery database unavailable"
        ) from exc

    connection.row_factory = (
        sqlite3.Row
    )

    return connection


def create_cover_blueprint(
    db_path: Any,
    cache_dir: Any,
    *,
    cover_getter=get_cover,
) -> Blueprint:
    database = _configured_path(
        db_path,
        label="Discovery DB",
    )

    cache_root = _configured_path(
        cache_dir,
        label="Discovery cover cache",
    )

    if not callable(
        cover_getter
    ):
        raise TypeError(
            "cover_getter must be callable"
        )

    blueprint = Blueprint(
        COVER_BLUEPRINT_NAME,
        __name__,
        url_prefix=COVER_API_PREFIX,
    )

    @blueprint.get(
        "/cover/<dvd_id>"
    )
    def cover(
        dvd_id,
    ):
        try:
            dvd_id = canonical_dvd_id(
                dvd_id
            )

        except (
            TypeError,
            ValueError,
        ):
            return _error_response(
                "invalid_request",
                "Invalid DVD ID",
                400,
            )

        connection = None

        try:
            connection = _open_readonly(
                database
            )

            payload = cover_getter(
                connection,
                cache_root,
                dvd_id,
            )

        except CoverNotFound:
            return _error_response(
                "cover_not_found",
                "Cover not found",
                404,
            )

        except (
            CoverUnavailable,
            CoverValidationError,
            sqlite3.Error,
            RuntimeError,
        ):
            return _error_response(
                "cover_unavailable",
                "Cover unavailable",
                503,
            )

        finally:
            if connection is not None:
                connection.close()

        body = payload.get(
            "body"
        )

        content_type = payload.get(
            "content_type"
        )

        sha256 = payload.get(
            "sha256"
        )

        if (
            not isinstance(
                body,
                bytes,
            )
            or not isinstance(
                content_type,
                str,
            )
            or not isinstance(
                sha256,
                str,
            )
            or len(
                sha256
            ) != 64
        ):
            return _error_response(
                "cover_unavailable",
                "Cover unavailable",
                503,
            )

        response = Response(
            body,
            status=200,
            content_type=content_type,
        )

        response.headers[
            "Cache-Control"
        ] = "private, no-cache"

        response.headers[
            "X-Content-Type-Options"
        ] = "nosniff"

        response.set_etag(
            sha256,
            weak=False,
        )

        return response.make_conditional(
            request
        )

    return blueprint
