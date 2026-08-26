from __future__ import annotations

from pathlib import Path
import re
import sqlite3
from typing import Any

from flask import (
    Blueprint,
    jsonify,
    request,
)

from teddy_discovery_ui_data import (
    build_category_facets_view,
    build_category_view,
    build_latest_view,
    build_monthly_view,
    build_weekly_view,
)


API_PREFIX = "/api/discovery"

LIMIT_RE = re.compile(
    r"^[0-9]+$"
)

PERIOD_RE = re.compile(
    r"^\d{4}-W\d{2}$"
)


class DiscoveryRequestError(
    ValueError
):
    pass


class DiscoveryUnavailable(
    RuntimeError
):
    pass


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


def _parse_limit(
    value: Any,
    *,
    default: int,
    maximum: int,
) -> int:
    if value is None:
        return default

    if (
        not isinstance(
            value,
            str,
        )
        or not LIMIT_RE.fullmatch(
            value
        )
    ):
        raise DiscoveryRequestError(
            "limit must be an integer"
        )

    parsed = int(
        value
    )

    if (
        parsed < 1
        or parsed > maximum
    ):
        raise DiscoveryRequestError(
            "limit must be 1.."
            + str(maximum)
        )

    return parsed


def _parse_period(
    value: Any,
) -> str | None:
    if value is None:
        return None

    if (
        not isinstance(
            value,
            str,
        )
        or not PERIOD_RE.fullmatch(
            value
        )
    ):
        raise DiscoveryRequestError(
            "period must use YYYY-Www"
        )

    return value


def _parse_category(
    value: Any,
) -> str:
    if not isinstance(
        value,
        str,
    ):
        raise DiscoveryRequestError(
            "category name is required"
        )

    value = " ".join(
        value.split()
    )

    if not value:
        raise DiscoveryRequestError(
            "category name is required"
        )

    if len(
        value
    ) > 200:
        raise DiscoveryRequestError(
            "category name is too long"
        )

    return value


def _open_readonly(
    db_path: Path,
) -> sqlite3.Connection:
    if not db_path.is_file():
        raise DiscoveryUnavailable(
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
        raise DiscoveryUnavailable(
            "Discovery database unavailable"
        ) from exc

    connection.row_factory = (
        sqlite3.Row
    )

    return connection


def _read_model(
    db_path: Path,
    builder,
):
    connection = _open_readonly(
        db_path
    )

    try:
        return builder(
            connection
        )

    except (
        sqlite3.Error,
        RuntimeError,
    ) as exc:
        raise DiscoveryUnavailable(
            "Discovery data unavailable"
        ) from exc

    finally:
        connection.close()


def _success(
    data: dict,
):
    return jsonify({
        "status":
            "success",

        "data":
            data,
    })


def create_discovery_blueprint(
    db_path: Any,
) -> Blueprint:
    if db_path is None:
        raise ValueError(
            "Discovery DB path required"
        )

    raw_path = str(
        db_path
    ).strip()

    if not raw_path:
        raise ValueError(
            "Discovery DB path required"
        )

    database = Path(
        raw_path
    ).expanduser().resolve()

    blueprint = Blueprint(
        "teddy_discovery_api",
        __name__,
        url_prefix=API_PREFIX,
    )

    @blueprint.get(
        "/latest"
    )
    def latest():
        try:
            limit = _parse_limit(
                request.args.get(
                    "limit"
                ),
                default=50,
                maximum=500,
            )

        except DiscoveryRequestError as exc:
            return _error_response(
                "invalid_request",
                str(exc),
                400,
            )

        try:
            data = _read_model(
                database,
                lambda connection:
                    build_latest_view(
                        connection,
                        limit=limit,
                    ),
            )

        except DiscoveryUnavailable:
            return _error_response(
                "discovery_unavailable",
                "Discovery data unavailable",
                503,
            )

        return _success(
            data
        )

    @blueprint.get(
        "/weekly"
    )
    def weekly():
        try:
            limit = _parse_limit(
                request.args.get(
                    "limit"
                ),
                default=25,
                maximum=25,
            )

            period = _parse_period(
                request.args.get(
                    "period"
                )
            )

        except DiscoveryRequestError as exc:
            return _error_response(
                "invalid_request",
                str(exc),
                400,
            )

        try:
            data = _read_model(
                database,
                lambda connection:
                    build_weekly_view(
                        connection,
                        period=period,
                        limit=limit,
                    ),
            )

        except DiscoveryUnavailable:
            return _error_response(
                "discovery_unavailable",
                "Discovery data unavailable",
                503,
            )

        return _success(
            data
        )

    @blueprint.get(
        "/monthly"
    )
    def monthly():
        try:
            limit = _parse_limit(
                request.args.get(
                    "limit"
                ),
                default=25,
                maximum=500,
            )

        except DiscoveryRequestError as exc:
            return _error_response(
                "invalid_request",
                str(exc),
                400,
            )

        try:
            data = _read_model(
                database,
                lambda connection:
                    build_monthly_view(
                        connection,
                        limit=limit,
                    ),
            )

        except DiscoveryUnavailable:
            return _error_response(
                "discovery_unavailable",
                "Discovery data unavailable",
                503,
            )

        return _success(
            data
        )

    @blueprint.get(
        "/categories"
    )
    def categories():
        try:
            data = _read_model(
                database,
                build_category_facets_view,
            )

        except DiscoveryUnavailable:
            return _error_response(
                "discovery_unavailable",
                "Discovery data unavailable",
                503,
            )

        return _success(
            data
        )

    @blueprint.get(
        "/category"
    )
    def category():
        try:
            name = _parse_category(
                request.args.get(
                    "name"
                )
            )

            limit = _parse_limit(
                request.args.get(
                    "limit"
                ),
                default=25,
                maximum=500,
            )

        except DiscoveryRequestError as exc:
            return _error_response(
                "invalid_request",
                str(exc),
                400,
            )

        connection = None

        try:
            connection = _open_readonly(
                database
            )

            data = build_category_view(
                connection,
                name,
                limit=limit,
            )

        except ValueError as exc:
            message = str(
                exc
            )

            if message.startswith(
                "unknown category:"
            ):
                return _error_response(
                    "category_not_found",
                    "Unknown category",
                    404,
                )

            return _error_response(
                "discovery_unavailable",
                "Discovery data unavailable",
                503,
            )

        except (
            sqlite3.Error,
            RuntimeError,
            DiscoveryUnavailable,
        ):
            return _error_response(
                "discovery_unavailable",
                "Discovery data unavailable",
                503,
            )

        finally:
            if connection is not None:
                connection.close()

        return _success(
            data
        )

    return blueprint
