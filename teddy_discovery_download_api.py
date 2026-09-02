from __future__ import annotations

from typing import Any

from flask import (
    Blueprint,
    jsonify,
    request,
)

import teddy_duplicates
import teddy_routing

from teddy_discovery_download_resolver import (
    DiscoveryResolveNoTarget,
    DiscoveryResolveRequestError,
    DiscoveryResolveTitleNotFound,
    DiscoveryResolveUnavailable,
    resolve_discovery_download,
)

from teddy_discovery_ids import (
    parse_dvd_id,
)

from teddy_discovery_availability import (
    SOURCE_MISSAV,
)


BLUEPRINT_NAME = (
    "teddy_discovery_download_api"
)

API_PREFIX = "/api/discovery"

def discovery_task_dvd_id(
    task: Any,
) -> str | None:
    if not isinstance(
        task,
        dict,
    ):
        return None

    url = str(
        task.get(
            "url"
        )
        or ""
    ).strip()

    if not url:
        return None

    site = teddy_routing.canonical_site(
        url
    )

    if site not in {
        SOURCE_MISSAV,
        "123av.com",
    }:
        return None

    parsed = parse_dvd_id(
        url
    )

    if parsed is None:
        return None

    return parsed.dvd_id


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
            target = resolve_discovery_download(
                db_path,
                payload.get(
                    "dvd_id"
                ),
            )

        except DiscoveryResolveRequestError:
            return jsonify({
                "status": "error",
                "message": "잘못된 DVD ID입니다.",
            }), 400

        except DiscoveryResolveTitleNotFound:
            return jsonify({
                "status": "error",
                "message": "Discovery 항목을 찾을 수 없습니다.",
            }), 404

        except DiscoveryResolveNoTarget:
            return jsonify({
                "status": "error",
                "message": "확인된 다운로드 소스가 없습니다.",
            }), 409

        except DiscoveryResolveUnavailable:
            return jsonify({
                "status": "error",
                "message": "Discovery 데이터를 확인할 수 없습니다.",
            }), 503

        dvd_id = target[
            "dvd_id"
        ]

        page_url = target[
            "page_url"
        ]

        return teddy_duplicates.guarded_enqueue_by_key(
            core,
            dvd_id,
            discovery_task_dvd_id,
            lambda: teddy_routing.enqueue_download(
                core,
                page_url,
                "auto",
            ),
            ownership_dvd_id=dvd_id,
            ownership_db_path=db_path,
        )

    return blueprint
