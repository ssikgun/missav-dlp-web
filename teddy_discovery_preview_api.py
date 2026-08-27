from __future__ import annotations

import hashlib
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

from teddy_discovery_preview import (
    PreviewNotFound,
    PreviewUnavailable,
    PreviewValidationError,
    get_preview,
)


PREVIEW_API_PREFIX = (
    "/api/discovery/media"
)

PREVIEW_BLUEPRINT_NAME = (
    "teddy_discovery_preview_api"
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
        raise PreviewUnavailable(
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
        raise PreviewUnavailable(
            "Discovery database unavailable"
        ) from exc

    connection.row_factory = (
        sqlite3.Row
    )

    return connection


def _validated_payload(
    payload: Any,
) -> dict:
    if not isinstance(
        payload,
        dict,
    ):
        raise PreviewValidationError(
            "preview payload invalid"
        )

    body = payload.get(
        "body"
    )

    content_type = payload.get(
        "content_type"
    )

    sha256 = payload.get(
        "sha256"
    )

    if not isinstance(
        body,
        bytes,
    ):
        raise PreviewValidationError(
            "preview body invalid"
        )

    if content_type != "video/mp4":
        raise PreviewValidationError(
            "preview content type invalid"
        )

    if (
        not isinstance(
            sha256,
            str,
        )
        or len(
            sha256
        ) != 64
    ):
        raise PreviewValidationError(
            "preview SHA invalid"
        )

    try:
        int(
            sha256,
            16,
        )

    except ValueError as exc:
        raise PreviewValidationError(
            "preview SHA invalid"
        ) from exc

    actual_sha = hashlib.sha256(
        body
    ).hexdigest()

    if actual_sha != sha256:
        raise PreviewValidationError(
            "preview SHA mismatch"
        )

    if not body:
        raise PreviewValidationError(
            "preview body empty"
        )

    return {
        "body":
            body,

        "content_type":
            content_type,

        "sha256":
            sha256,

        "body_bytes":
            len(
                body
            ),
    }


def _apply_media_headers(
    response: Response,
    *,
    sha256: str,
) -> Response:
    response.headers[
        "Accept-Ranges"
    ] = "bytes"

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

    return response


def _parse_single_range(
    value: Any,
    *,
    size: int,
) -> tuple[int, int] | None:
    if value is None:
        return None

    raw = str(
        value
    ).strip()

    if not raw:
        return None

    if not raw.lower().startswith(
        "bytes="
    ):
        raise ValueError(
            "unsupported range unit"
        )

    spec = raw[
        len(
            "bytes="
        ):
    ].strip()

    if (
        not spec
        or "," in spec
        or "-" not in spec
    ):
        raise ValueError(
            "invalid range"
        )

    first, last = spec.split(
        "-",
        1,
    )

    first = first.strip()
    last = last.strip()

    if not first:
        if (
            not last.isdigit()
            or int(
                last
            ) <= 0
        ):
            raise ValueError(
                "invalid suffix range"
            )

        suffix = int(
            last
        )

        length = min(
            suffix,
            size,
        )

        return (
            size - length,
            size - 1,
        )

    if not first.isdigit():
        raise ValueError(
            "invalid range start"
        )

    start = int(
        first
    )

    if start >= size:
        raise ValueError(
            "range start beyond body"
        )

    if not last:
        return (
            start,
            size - 1,
        )

    if not last.isdigit():
        raise ValueError(
            "invalid range end"
        )

    end = int(
        last
    )

    if end < start:
        raise ValueError(
            "range end before start"
        )

    end = min(
        end,
        size - 1,
    )

    return (
        start,
        end,
    )


def _if_range_allows(
    value: Any,
    *,
    sha256: str,
) -> bool:
    if value is None:
        return True

    raw = str(
        value
    ).strip()

    if not raw:
        return True

    expected = (
        '"'
        + sha256
        + '"'
    )

    #
    # Date-form If-Range and weak tags
    # deliberately fail closed to a full
    # representation rather than a partial.
    #
    return raw in {
        expected,
        sha256,
    }


def _not_modified(
    *,
    sha256: str,
) -> Response:
    response = Response(
        status=304
    )

    return _apply_media_headers(
        response,
        sha256=sha256,
    )


def _range_not_satisfiable(
    *,
    size: int,
    sha256: str,
) -> Response:
    response = Response(
        status=416
    )

    response.headers[
        "Content-Range"
    ] = (
        "bytes */"
        + str(
            size
        )
    )

    response.headers[
        "Content-Length"
    ] = "0"

    return _apply_media_headers(
        response,
        sha256=sha256,
    )


def create_preview_blueprint(
    db_path: Any,
    cache_dir: Any,
    *,
    preview_getter=get_preview,
) -> Blueprint:
    database = _configured_path(
        db_path,
        label="Discovery DB",
    )

    cache_root = _configured_path(
        cache_dir,
        label="Discovery preview cache",
    )

    if not callable(
        preview_getter
    ):
        raise TypeError(
            "preview_getter must be callable"
        )

    blueprint = Blueprint(
        PREVIEW_BLUEPRINT_NAME,
        __name__,
        url_prefix=
            PREVIEW_API_PREFIX,
    )

    @blueprint.route(
        "/preview/<dvd_id>",
        methods=[
            "GET",
            "HEAD",
        ],
    )
    def preview(
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

            payload = preview_getter(
                connection,
                cache_root,
                dvd_id,
            )

            media = _validated_payload(
                payload
            )

        except PreviewNotFound:
            return _error_response(
                "preview_not_found",
                "Preview not found",
                404,
            )

        except (
            PreviewUnavailable,
            PreviewValidationError,
            sqlite3.Error,
            RuntimeError,
        ):
            return _error_response(
                "preview_unavailable",
                "Preview unavailable",
                503,
            )

        finally:
            if connection is not None:
                connection.close()

        body = media[
            "body"
        ]

        size = media[
            "body_bytes"
        ]

        sha256 = media[
            "sha256"
        ]

        if (
            request.headers.get(
                "If-None-Match"
            )
            and request.if_none_match.contains(
                sha256
            )
        ):
            return _not_modified(
                sha256=sha256,
            )

        range_value = request.headers.get(
            "Range"
        )

        if (
            range_value
            and not _if_range_allows(
                request.headers.get(
                    "If-Range"
                ),
                sha256=sha256,
            )
        ):
            range_value = None

        try:
            byte_range = _parse_single_range(
                range_value,
                size=size,
            )

        except ValueError:
            return _range_not_satisfiable(
                size=size,
                sha256=sha256,
            )

        is_head = (
            request.method == "HEAD"
        )

        if byte_range is None:
            response = Response(
                (
                    b""
                    if is_head
                    else body
                ),
                status=200,
                content_type=
                    "video/mp4",
            )

            response.headers[
                "Content-Length"
            ] = str(
                size
            )

            return _apply_media_headers(
                response,
                sha256=sha256,
            )

        start, end = byte_range

        partial = body[
            start:
            end + 1
        ]

        response = Response(
            (
                b""
                if is_head
                else partial
            ),
            status=206,
            content_type=
                "video/mp4",
        )

        response.headers[
            "Content-Range"
        ] = (
            "bytes "
            + str(
                start
            )
            + "-"
            + str(
                end
            )
            + "/"
            + str(
                size
            )
        )

        response.headers[
            "Content-Length"
        ] = str(
            len(
                partial
            )
        )

        return _apply_media_headers(
            response,
            sha256=sha256,
        )

    return blueprint
