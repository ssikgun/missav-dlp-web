from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any

from flask import (
    Blueprint,
    jsonify,
    request,
)

import teddy_duplicates
import teddy_routing

from teddy_discovery_availability import (
    AVAILABILITY_SOURCES,
    AVAILABILITY_STATUSES,
    SOURCE_123AV,
    SOURCE_MISSAV,
    STATUS_FOUND,
    canonical_dvd_id,
    canonical_page_url,
)


BLUEPRINT_NAME = (
    "teddy_discovery_download_api"
)

API_PREFIX = "/api/discovery"

PREFERENCE_AUTO = "auto"

DOWNLOAD_PREFERENCES = (
    PREFERENCE_AUTO,
    SOURCE_MISSAV,
    SOURCE_123AV,
)


class DiscoveryDownloadRequestError(
    ValueError
):
    pass


class DiscoveryDownloadUnavailable(
    RuntimeError
):
    pass


class DiscoveryTitleNotFound(
    LookupError
):
    pass


def normalize_preference(
    value: Any,
) -> str:
    value = str(
        value or PREFERENCE_AUTO
    ).strip().lower()

    if value not in DOWNLOAD_PREFERENCES:
        return PREFERENCE_AUTO

    return value


def select_source(
    available_sources: Any,
    preference: Any = PREFERENCE_AUTO,
) -> str | None:
    if not isinstance(
        available_sources,
        (list, tuple, set),
    ):
        raise ValueError(
            "available sources must be a collection"
        )

    available = set()

    for source in available_sources:
        if source not in AVAILABILITY_SOURCES:
            raise ValueError(
                "unsupported availability source"
            )

        available.add(
            source
        )

    if not available:
        return None

    if len(available) == 1:
        for source in AVAILABILITY_SOURCES:
            if source in available:
                return source

    preference = normalize_preference(
        preference
    )

    if preference == SOURCE_123AV:
        return SOURCE_123AV

    # Auto intentionally defaults to MissAV
    # when both verified sources exist.
    return SOURCE_MISSAV


def _open_readonly(
    db_path: Any,
) -> sqlite3.Connection:
    database = Path(
        str(db_path or "").strip()
    ).expanduser().resolve()

    if not database.is_file():
        raise DiscoveryDownloadUnavailable(
            "Discovery database unavailable"
        )

    try:
        connection = sqlite3.connect(
            "file:"
            + str(database)
            + "?mode=ro",
            uri=True,
        )

    except sqlite3.Error as exc:
        raise DiscoveryDownloadUnavailable(
            "Discovery database unavailable"
        ) from exc

    connection.row_factory = sqlite3.Row

    return connection


def load_available_sources(
    db_path: Any,
    dvd_id: Any,
) -> tuple[str, list[str]]:
    try:
        dvd_id = canonical_dvd_id(
            dvd_id
        )

    except ValueError as exc:
        raise DiscoveryDownloadRequestError(
            "invalid DVD ID"
        ) from exc

    connection = _open_readonly(
        db_path
    )

    try:
        title = connection.execute(
            """
            SELECT dvd_id
            FROM titles
            WHERE dvd_id = ?
            LIMIT 1
            """,
            (dvd_id,),
        ).fetchone()

        if title is None:
            raise DiscoveryTitleNotFound(
                "Discovery title not found"
            )

        rows = connection.execute(
            """
            SELECT
                source,
                status
            FROM availability
            WHERE dvd_id = ?
            ORDER BY source
            """,
            (dvd_id,),
        ).fetchall()

        seen = set()
        available = []

        for row in rows:
            source = row["source"]
            status = row["status"]

            if source not in AVAILABILITY_SOURCES:
                raise DiscoveryDownloadUnavailable(
                    "stored availability source invalid"
                )

            if status not in AVAILABILITY_STATUSES:
                raise DiscoveryDownloadUnavailable(
                    "stored availability status invalid"
                )

            if source in seen:
                raise DiscoveryDownloadUnavailable(
                    "duplicate availability row"
                )

            seen.add(
                source
            )

            if status == STATUS_FOUND:
                available.append(
                    source
                )

        # Keep the canonical source order,
        # independent of SQLite sort order.
        available = [
            source
            for source in AVAILABILITY_SOURCES
            if source in available
        ]

        return (
            dvd_id,
            available,
        )

    except sqlite3.Error as exc:
        raise DiscoveryDownloadUnavailable(
            "Discovery data unavailable"
        ) from exc

    finally:
        connection.close()


def create_discovery_download_blueprint(
    core,
    db_path: Any,
) -> Blueprint:
    if core is None:
        raise ValueError(
            "Downloader core required"
        )

    blueprint = Blueprint(
        BLUEPRINT_NAME,
        __name__,
        url_prefix=API_PREFIX,
    )

    @blueprint.post(
        "/download"
    )
    def discovery_download():
        payload = request.get_json(
            silent=True
        )

        if not isinstance(
            payload,
            dict,
        ):
            return jsonify({
                "status": "error",
                "message": "JSON 요청이 필요합니다.",
            }), 400

        if set(payload) != {
            "dvd_id",
        }:
            return jsonify({
                "status": "error",
                "message": "DVD ID만 전송할 수 있습니다.",
            }), 400

        try:
            dvd_id, available_sources = (
                load_available_sources(
                    db_path,
                    payload.get(
                        "dvd_id"
                    ),
                )
            )

        except DiscoveryDownloadRequestError:
            return jsonify({
                "status": "error",
                "message": "잘못된 DVD ID입니다.",
            }), 400

        except DiscoveryTitleNotFound:
            return jsonify({
                "status": "error",
                "message": "Discovery 항목을 찾을 수 없습니다.",
            }), 404

        except DiscoveryDownloadUnavailable:
            return jsonify({
                "status": "error",
                "message": "Discovery 데이터를 확인할 수 없습니다.",
            }), 503

        preference = normalize_preference(
            getattr(
                core,
                "settings",
                {},
            ).get(
                "discovery_download_preference",
                PREFERENCE_AUTO,
            )
        )

        source = select_source(
            available_sources,
            preference,
        )

        if source is None:
            return jsonify({
                "status": "error",
                "message": "확인된 다운로드 소스가 없습니다.",
            }), 409

        # Browser never receives or constructs
        # an upstream source URL.
        page_url = canonical_page_url(
            source,
            dvd_id,
        )

        return teddy_duplicates.guarded_enqueue(
            core,
            page_url,
            lambda: teddy_routing.enqueue_download(
                core,
                page_url,
                "auto",
            ),
        )

    return blueprint
