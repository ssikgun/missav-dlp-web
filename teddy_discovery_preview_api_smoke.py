from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
import tempfile

from flask import Flask

from teddy_discovery_preview import (
    PreviewNotFound,
    PreviewUnavailable,
)

from teddy_discovery_preview_api import (
    PREVIEW_BLUEPRINT_NAME,
    create_preview_blueprint,
)


MP4_BODY = (
    b"\x00\x00\x00\x20"
    b"ftyp"
    b"isom"
    b"\x00\x00\x02\x00"
    b"isom"
    b"iso2"
    b"mp41"
    + bytes(
        range(
            256
        )
    )
    + b"R" * 300
)

MP4_SHA = hashlib.sha256(
    MP4_BODY
).hexdigest()

ETAG = (
    '"'
    + MP4_SHA
    + '"'
)


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


class FakePreviewGetter:
    def __init__(
        self,
    ):
        self.calls = []
        self.readonly_observed = False

    def __call__(
        self,
        connection,
        cache_root,
        dvd_id,
    ):
        require(
            connection.row_factory
            is sqlite3.Row,
            "API DB row factory changed",
        )

        if not self.readonly_observed:
            try:
                connection.execute(
                    """
                    CREATE TABLE
                    __preview_write_probe (
                        id INTEGER
                    )
                    """
                )

            except sqlite3.OperationalError:
                self.readonly_observed = True

            else:
                raise RuntimeError(
                    "API database was writable"
                )

        self.calls.append(
            {
                "dvd_id":
                    dvd_id,

                "cache_root":
                    str(
                        cache_root
                    ),
            }
        )

        if dvd_id == "JUR-821":
            raise PreviewNotFound(
                "fixture not found"
            )

        if dvd_id == "EROFV-387":
            raise PreviewUnavailable(
                "fixture unavailable"
            )

        return {
            "dvd_id":
                dvd_id,

            "content_type":
                "video/mp4",

            "body_bytes":
                len(
                    MP4_BODY
                ),

            "sha256":
                MP4_SHA,

            "body":
                MP4_BODY,

            "cache_hit":
                True,

            "route":
                "cache",

            "request_attempts":
                0,

            "redirects_followed":
                0,
        }


def create_database(
    path: Path,
):
    connection = sqlite3.connect(
        path
    )

    try:
        connection.execute(
            """
            CREATE TABLE titles (
                dvd_id TEXT PRIMARY KEY
            )
            """
        )

        connection.executemany(
            """
            INSERT INTO titles (
                dvd_id
            )
            VALUES (?)
            """,
            [
                (
                    "SDNM-560",
                ),
                (
                    "JUR-821",
                ),
                (
                    "EROFV-387",
                ),
            ],
        )

        connection.commit()

    finally:
        connection.close()


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(
            tmp
        )

        db = (
            root
            / "discovery.sqlite3"
        )

        cache = (
            root
            / "preview-cache"
        )

        create_database(
            db
        )

        getter = FakePreviewGetter()

        app = Flask(
            __name__
        )

        app.config[
            "TESTING"
        ] = True

        app.register_blueprint(
            create_preview_blueprint(
                db,
                cache,
                preview_getter=
                    getter,
            )
        )

        require(
            PREVIEW_BLUEPRINT_NAME
            in app.blueprints,
            "preview blueprint missing",
        )

        client = app.test_client()

        path = (
            "/api/discovery/media/"
            "preview/SDNM-560"
        )

        full = client.get(
            path
        )

        require(
            full.status_code == 200,
            "full GET status changed",
        )

        require(
            full.data == MP4_BODY,
            "full GET body changed",
        )

        require(
            full.headers[
                "Content-Type"
            ].startswith(
                "video/mp4"
            ),
            "full GET content type changed",
        )

        require(
            full.headers[
                "Content-Length"
            ]
            ==
            str(
                len(
                    MP4_BODY
                )
            ),
            "full GET length changed",
        )

        require(
            full.headers[
                "Accept-Ranges"
            ] == "bytes",
            "Accept-Ranges missing",
        )

        require(
            full.headers[
                "ETag"
            ] == ETAG,
            "strong ETag changed",
        )

        require(
            full.headers[
                "Cache-Control"
            ]
            == "private, no-cache",
            "cache policy changed",
        )

        require(
            full.headers[
                "X-Content-Type-Options"
            ]
            == "nosniff",
            "nosniff missing",
        )

        print(
            "PREVIEW_API_FULL_GET_SMOKE=PASS"
        )

        head = client.open(
            path,
            method="HEAD",
        )

        require(
            head.status_code == 200,
            "HEAD status changed",
        )

        require(
            head.data == b"",
            "HEAD returned a body",
        )

        require(
            head.headers[
                "Content-Length"
            ]
            ==
            str(
                len(
                    MP4_BODY
                )
            ),
            "HEAD length changed",
        )

        require(
            head.headers[
                "ETag"
            ] == ETAG,
            "HEAD ETag changed",
        )

        print(
            "PREVIEW_API_HEAD_SMOKE=PASS"
        )

        not_modified = client.get(
            path,
            headers={
                "If-None-Match":
                    ETAG,
            },
        )

        require(
            not_modified.status_code == 304,
            "ETag conditional status changed",
        )

        require(
            not_modified.data == b"",
            "304 returned a body",
        )

        require(
            not_modified.headers[
                "ETag"
            ] == ETAG,
            "304 ETag changed",
        )

        print(
            "PREVIEW_API_ETAG_304_SMOKE=PASS"
        )

        partial = client.get(
            path,
            headers={
                "Range":
                    "bytes=0-31",
            },
        )

        require(
            partial.status_code == 206,
            "bounded Range status changed",
        )

        require(
            partial.data
            == MP4_BODY[
                0:32
            ],
            "bounded Range body changed",
        )

        require(
            partial.headers[
                "Content-Range"
            ]
            ==
            (
                "bytes 0-31/"
                + str(
                    len(
                        MP4_BODY
                    )
                )
            ),
            "bounded Content-Range changed",
        )

        require(
            partial.headers[
                "Content-Length"
            ] == "32",
            "bounded Range length changed",
        )

        print(
            "PREVIEW_API_RANGE_BOUNDED_SMOKE=PASS"
        )

        open_ended = client.get(
            path,
            headers={
                "Range":
                    "bytes=32-",
            },
        )

        require(
            open_ended.status_code == 206,
            "open Range status changed",
        )

        require(
            open_ended.data
            == MP4_BODY[
                32:
            ],
            "open Range body changed",
        )

        require(
            open_ended.headers[
                "Content-Range"
            ]
            ==
            (
                "bytes 32-"
                + str(
                    len(
                        MP4_BODY
                    )
                    - 1
                )
                + "/"
                + str(
                    len(
                        MP4_BODY
                    )
                )
            ),
            "open Content-Range changed",
        )

        print(
            "PREVIEW_API_RANGE_OPEN_SMOKE=PASS"
        )

        suffix = client.get(
            path,
            headers={
                "Range":
                    "bytes=-16",
            },
        )

        require(
            suffix.status_code == 206,
            "suffix Range status changed",
        )

        require(
            suffix.data
            == MP4_BODY[
                -16:
            ],
            "suffix Range body changed",
        )

        require(
            suffix.headers[
                "Content-Range"
            ]
            ==
            (
                "bytes "
                + str(
                    len(
                        MP4_BODY
                    )
                    - 16
                )
                + "-"
                + str(
                    len(
                        MP4_BODY
                    )
                    - 1
                )
                + "/"
                + str(
                    len(
                        MP4_BODY
                    )
                )
            ),
            "suffix Content-Range changed",
        )

        print(
            "PREVIEW_API_RANGE_SUFFIX_SMOKE=PASS"
        )

        if_range_match = client.get(
            path,
            headers={
                "Range":
                    "bytes=4-19",

                "If-Range":
                    ETAG,
            },
        )

        require(
            if_range_match.status_code == 206,
            "If-Range match status changed",
        )

        require(
            if_range_match.data
            == MP4_BODY[
                4:20
            ],
            "If-Range match body changed",
        )

        if_range_miss = client.get(
            path,
            headers={
                "Range":
                    "bytes=4-19",

                "If-Range":
                    '"different-etag"',
            },
        )

        require(
            if_range_miss.status_code == 200,
            "If-Range mismatch "
            "did not return full body",
        )

        require(
            if_range_miss.data
            == MP4_BODY,
            "If-Range mismatch body changed",
        )

        print(
            "PREVIEW_API_IF_RANGE_SMOKE=PASS"
        )

        unsatisfiable = client.get(
            path,
            headers={
                "Range":
                    "bytes=999999-",
            },
        )

        require(
            unsatisfiable.status_code == 416,
            "unsatisfiable Range "
            "status changed",
        )

        require(
            unsatisfiable.data == b"",
            "416 returned body",
        )

        require(
            unsatisfiable.headers[
                "Content-Range"
            ]
            ==
            (
                "bytes */"
                + str(
                    len(
                        MP4_BODY
                    )
                )
            ),
            "416 Content-Range changed",
        )

        multiple = client.get(
            path,
            headers={
                "Range":
                    "bytes=0-1,4-5",
            },
        )

        require(
            multiple.status_code == 416,
            "multi-range was accepted",
        )

        print(
            "PREVIEW_API_RANGE_416_SMOKE=PASS"
        )

        invalid = client.get(
            (
                "/api/discovery/media/"
                "preview/not-a-dvd-id"
            )
        )

        require(
            invalid.status_code == 400,
            "invalid DVD ID status changed",
        )

        not_found = client.get(
            (
                "/api/discovery/media/"
                "preview/JUR-821"
            )
        )

        require(
            not_found.status_code == 404,
            "not-found status changed",
        )

        unavailable = client.get(
            (
                "/api/discovery/media/"
                "preview/EROFV-387"
            )
        )

        require(
            unavailable.status_code == 503,
            "unavailable status changed",
        )

        print(
            "PREVIEW_API_ERROR_MAPPING_SMOKE=PASS"
        )

        for method in (
            "POST",
            "PUT",
            "DELETE",
        ):
            response = client.open(
                path,
                method=method,
            )

            require(
                response.status_code == 405,
                method
                + " did not fail read-only",
            )

        print(
            "PREVIEW_API_READ_ONLY_METHODS_SMOKE=PASS"
        )

        require(
            getter.readonly_observed,
            "API did not prove DB read-only",
        )

        print(
            "PREVIEW_API_DB_READ_ONLY_SMOKE=PASS"
        )

        #
        # API responses and error envelopes
        # must not reveal any upstream URL.
        #
        combined = (
            full.data
            + invalid.data
            + not_found.data
            + unavailable.data
        ).lower()

        for forbidden in (
            b"fourhoi",
            b"javplayer",
            b"m3u8",
            b"missav.ws",
        ):
            require(
                forbidden
                not in combined,
                "upstream detail leaked "
                "to browser response",
            )

        print(
            "PREVIEW_API_BROWSER_UPSTREAM_LEAK=0"
        )

        print(
            "PREVIEW_API_REAL_NETWORK_REQUESTS=0"
        )

        print(
            "TEDDY_DISCOVERY_PREVIEW_HTTP_API_OFFLINE_SMOKE=PASS"
        )


if __name__ == "__main__":
    main()
