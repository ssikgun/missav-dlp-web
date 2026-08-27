from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

from flask import Flask

from teddy_discovery_cover import (
    CoverNotFound,
    CoverUnavailable,
    CoverValidationError,
)

from teddy_discovery_cover_api import (
    COVER_BLUEPRINT_NAME,
    create_cover_blueprint,
)


JPEG_BODY = (
    b"\xff\xd8\xff\xe0"
    + b"T"
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


class FakeCoverGetter:
    def __init__(
        self,
    ):
        self.calls = []

    def __call__(
        self,
        connection,
        cache_dir,
        dvd_id,
    ):
        require(
            isinstance(
                connection,
                sqlite3.Connection,
            ),
            "cover API did not pass "
            "sqlite connection",
        )

        require(
            connection.row_factory
            is sqlite3.Row,
            "cover API connection "
            "row_factory changed",
        )

        self.calls.append({
            "dvd_id":
                dvd_id,

            "cache_dir":
                str(
                    cache_dir
                ),
        })

        if dvd_id == "MISS-404":
            raise CoverNotFound(
                "synthetic"
            )

        if dvd_id == "FAIL-503":
            raise CoverUnavailable(
                "synthetic"
            )

        if dvd_id == "BAD-503":
            raise CoverValidationError(
                "synthetic"
            )

        return {
            "dvd_id":
                dvd_id,

            "route":
                "cache",

            "cache_hit":
                True,

            "request_attempts":
                0,

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

            "cache_path":
                Path(
                    cache_dir
                )
                / "synthetic.cover",
        }


def file_sha256(
    path: Path,
) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def main():
    if len(
        sys.argv
    ) != 2:
        raise RuntimeError(
            "usage: "
            "teddy_discovery_cover_api_smoke.py "
            "<stage5-db>"
        )

    db_path = Path(
        sys.argv[1]
    )

    before = file_sha256(
        db_path
    )

    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-cover-api-cache-"
    ) as temp:
        cache_dir = Path(
            temp
        )

        getter = FakeCoverGetter()

        app = Flask(
            "teddy-cover-api-smoke"
        )

        app.testing = True

        app.register_blueprint(
            create_cover_blueprint(
                db_path,
                cache_dir,
                cover_getter=getter,
            )
        )

        require(
            COVER_BLUEPRINT_NAME
            in app.blueprints,
            "cover blueprint missing",
        )

        client = app.test_client()

        #
        # Successful browser-safe image.
        #
        response = client.get(
            "/api/discovery/media/cover/SDNM-560"
        )

        require(
            response.status_code == 200,
            "cover success status changed",
        )

        require(
            response.data == JPEG_BODY,
            "cover response bytes changed",
        )

        require(
            response.content_type
            == "image/jpeg",
            "cover response MIME changed",
        )

        require(
            response.headers.get(
                "Cache-Control"
            )
            == "private, no-cache",
            "cover browser cache "
            "policy changed",
        )

        require(
            response.headers.get(
                "X-Content-Type-Options"
            )
            == "nosniff",
            "cover nosniff header missing",
        )

        etag = response.headers.get(
            "ETag"
        )

        require(
            etag
            == '"'
            + JPEG_SHA
            + '"',
            "cover ETag changed",
        )

        require(
            len(
                getter.calls
            )
            == 1,
            "cover getter call count changed",
        )

        require(
            getter.calls[
                0
            ][
                "dvd_id"
            ]
            == "SDNM-560",
            "cover DVD ID changed",
        )

        #
        # Conditional request.
        #
        conditional = client.get(
            "/api/discovery/media/cover/SDNM-560",
            headers={
                "If-None-Match":
                    etag,
            },
        )

        require(
            conditional.status_code
            == 304,
            "cover conditional "
            "response changed",
        )

        require(
            conditional.data == b"",
            "304 response leaked body",
        )

        #
        # Errors remain generic and never
        # expose source/cache URLs.
        #
        not_found = client.get(
            "/api/discovery/media/cover/MISS-404"
        )

        unavailable = client.get(
            "/api/discovery/media/cover/FAIL-503"
        )

        invalid_source = client.get(
            "/api/discovery/media/cover/BAD-503"
        )

        invalid_id = client.get(
            "/api/discovery/media/cover/%20"
        )

        require(
            not_found.status_code == 404,
            "cover not-found status changed",
        )

        require(
            unavailable.status_code == 503,
            "cover unavailable status changed",
        )

        require(
            invalid_source.status_code == 503,
            "cover validation status changed",
        )

        require(
            invalid_id.status_code == 400,
            "invalid DVD ID status changed",
        )

        for error_response in (
            not_found,
            unavailable,
            invalid_source,
            invalid_id,
        ):
            require(
                error_response.is_json,
                "cover error is not JSON",
            )

            body = error_response.get_data(
                as_text=True
            )

            for forbidden in (
                "http://",
                "https://",
                ".stage1-data",
                "cover-cache",
                "fourhoi.com",
                "javdatabase.com",
            ):
                require(
                    forbidden
                    not in body,
                    "cover error leaked "
                    "internal/upstream detail: "
                    + forbidden,
                )

        #
        # GET/HEAD only. Flask's GET route
        # automatically permits HEAD.
        #
        post = client.post(
            "/api/discovery/media/cover/SDNM-560"
        )

        put = client.put(
            "/api/discovery/media/cover/SDNM-560"
        )

        delete = client.delete(
            "/api/discovery/media/cover/SDNM-560"
        )

        require(
            post.status_code == 405,
            "cover POST boundary changed",
        )

        require(
            put.status_code == 405,
            "cover PUT boundary changed",
        )

        require(
            delete.status_code == 405,
            "cover DELETE boundary changed",
        )

        #
        # Missing DB fails closed before
        # any cover getter call.
        #
        missing_getter = (
            FakeCoverGetter()
        )

        missing_app = Flask(
            "teddy-cover-api-missing-db"
        )

        missing_app.testing = True

        missing_app.register_blueprint(
            create_cover_blueprint(
                cache_dir
                / "missing.sqlite3",
                cache_dir,
                cover_getter=
                    missing_getter,
            )
        )

        missing_client = (
            missing_app.test_client()
        )

        missing = missing_client.get(
            "/api/discovery/media/cover/SDNM-560"
        )

        require(
            missing.status_code == 503,
            "missing DB did not "
            "fail closed",
        )

        require(
            missing_getter.calls == [],
            "missing DB reached "
            "cover getter",
        )

    after = file_sha256(
        db_path
    )

    require(
        after == before,
        "cover API smoke changed "
        "real Stage 5 DB",
    )

    oracle_payload = {
        "route":
            "/api/discovery/media/cover/<dvd_id>",

        "success_status":
            200,

        "not_found_status":
            404,

        "unavailable_status":
            503,

        "invalid_status":
            400,

        "etag":
            JPEG_SHA,

        "cache_control":
            "private, no-cache",

        "nosniff":
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
        "COVER_HTTP_API_ORACLE_SHA256="
        + oracle
    )

    print(
        "COVER_HTTP_API_SUCCESS_CONTRACT_SMOKE=PASS"
    )

    print(
        "COVER_HTTP_API_ETAG_CONDITIONAL_SMOKE=PASS"
    )

    print(
        "COVER_HTTP_API_GENERIC_ERROR_SMOKE=PASS"
    )

    print(
        "COVER_HTTP_API_INTERNAL_URL_NOT_LEAKED_SMOKE=PASS"
    )

    print(
        "COVER_HTTP_API_GET_HEAD_ONLY_SMOKE=PASS"
    )

    print(
        "COVER_HTTP_API_MISSING_DB_FAIL_CLOSED_SMOKE=PASS"
    )

    print(
        "COVER_HTTP_API_REAL_DB_BYTE_UNCHANGED_SMOKE=PASS"
    )

    print(
        "TEDDY_DISCOVERY_COVER_HTTP_API_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
