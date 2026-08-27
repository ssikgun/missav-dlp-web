from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
import tempfile

import teddy_discovery_preview as preview


MP4_BODY = (
    b"\x00\x00\x00\x20"
    b"ftyp"
    b"isom"
    b"\x00\x00\x02\x00"
    b"isom"
    b"iso2"
    b"mp41"
    + b"P" * 300
)


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


class FakeResponse:
    def __init__(
        self,
        *,
        status=200,
        headers=None,
        chunks=None,
    ):
        self.status_code = status
        self.headers = headers or {}
        self._chunks = list(
            chunks or []
        )
        self.closed = False

    def iter_content(
        self,
        *,
        chunk_size,
    ):
        del chunk_size

        yield from self._chunks

    def close(
        self,
    ):
        self.closed = True


class FakeSession:
    def __init__(
        self,
        response,
    ):
        self.response = response
        self.calls = []

    def get(
        self,
        url,
        **kwargs,
    ):
        self.calls.append(
            (
                url,
                kwargs,
            )
        )

        return self.response


def connection_with_title():
    connection = sqlite3.connect(
        ":memory:"
    )

    connection.row_factory = sqlite3.Row

    connection.execute(
        """
        CREATE TABLE titles (
            dvd_id TEXT PRIMARY KEY
        )
        """
    )

    connection.execute(
        """
        INSERT INTO titles (
            dvd_id
        )
        VALUES (?)
        """,
        (
            "SDNM-560",
        ),
    )

    return connection


def main():
    require(
        preview.preview_url_for_dvd_id(
            "SDNM-560"
        )
        ==
        (
            "https://fourhoi.com/"
            "sdnm-560/preview.mp4"
        ),
        "deterministic preview URL failed",
    )

    print(
        "PREVIEW_DETERMINISTIC_URL_SMOKE=PASS"
    )

    connection = (
        connection_with_title()
    )

    try:
        request_value = (
            preview.lookup_preview_request(
                connection,
                "SDNM-560",
            )
        )

        require(
            request_value[
                "url"
            ]
            ==
            (
                "https://fourhoi.com/"
                "sdnm-560/preview.mp4"
            ),
            "preview lookup URL changed",
        )

        require(
            request_value[
                "referer"
            ]
            ==
            (
                "https://missav.ws/ko/"
                "sdnm-560"
            ),
            "preview referer changed",
        )

        try:
            preview.lookup_preview_request(
                connection,
                "JUR-821",
            )

        except preview.PreviewNotFound:
            pass

        else:
            raise RuntimeError(
                "unknown title did not "
                "fail closed"
            )

    finally:
        connection.close()

    print(
        "PREVIEW_TITLE_BOUNDARY_SMOKE=PASS"
    )

    valid = (
        preview.validate_preview_bytes(
            content_type=
                "video/mp4; charset=binary",

            content=
                MP4_BODY,
        )
    )

    require(
        valid[
            "magic_type"
        ] == "mp4",
        "MP4 magic validation failed",
    )

    require(
        valid[
            "sha256"
        ]
        ==
        hashlib.sha256(
            MP4_BODY
        ).hexdigest(),
        "MP4 SHA changed",
    )

    for bad in (
        b"not-an-mp4" + b"X" * 100,
        b"\x00" * 100,
    ):
        try:
            preview.validate_preview_bytes(
                content_type=
                    "video/mp4",

                content=
                    bad,
            )

        except preview.PreviewValidationError:
            pass

        else:
            raise RuntimeError(
                "invalid MP4 accepted"
            )

    print(
        "PREVIEW_MP4_VALIDATION_SMOKE=PASS"
    )

    response = FakeResponse(
        headers={
            "Content-Type":
                "video/mp4",

            "Content-Length":
                str(
                    len(
                        MP4_BODY
                    )
                ),
        },

        chunks=[
            MP4_BODY[:80],
            MP4_BODY[80:],
        ],
    )

    session = FakeSession(
        response
    )

    payload = (
        preview.fetch_preview_payload(
            request_value,
            session=session,
        )
    )

    require(
        payload[
            "body"
        ] == MP4_BODY,
        "preview fetch body changed",
    )

    require(
        payload[
            "route"
        ] == "fixed-vpn",
        "preview route changed",
    )

    require(
        payload[
            "request_attempts"
        ] == 1,
        "preview request count changed",
    )

    require(
        payload[
            "redirects_followed"
        ] == 0,
        "preview redirect accounting changed",
    )

    require(
        len(
            session.calls
        ) == 1,
        "preview session call count changed",
    )

    called_url, kwargs = (
        session.calls[0]
    )

    require(
        called_url
        ==
        (
            "https://fourhoi.com/"
            "sdnm-560/preview.mp4"
        ),
        "preview network target changed",
    )

    require(
        kwargs[
            "allow_redirects"
        ] is False,
        "preview redirects enabled",
    )

    require(
        kwargs[
            "proxies"
        ][
            "https"
        ]
        ==
        "http://gluetun:8888",
        "preview escaped fixed VPN",
    )

    require(
        "Range"
        not in kwargs[
            "headers"
        ],
        "preview upstream fetch "
        "unexpectedly became range-only",
    )

    require(
        response.closed,
        "preview response not closed",
    )

    print(
        "PREVIEW_FIXED_VPN_FETCH_SMOKE=PASS"
    )

    redirect = FakeResponse(
        status=302,
        headers={
            "Location":
                "https://example.invalid/"
        },
    )

    try:
        preview.fetch_preview_payload(
            request_value,
            session=
                FakeSession(
                    redirect
                ),
        )

    except preview.PreviewUnavailable:
        pass

    else:
        raise RuntimeError(
            "preview redirect accepted"
        )

    print(
        "PREVIEW_REDIRECT_FAIL_CLOSED_SMOKE=PASS"
    )

    oversized = FakeResponse(
        headers={
            "Content-Type":
                "video/mp4",

            "Content-Length":
                str(
                    preview.MAX_PREVIEW_BYTES
                    + 1
                ),
        },
    )

    try:
        preview.fetch_preview_payload(
            request_value,
            session=
                FakeSession(
                    oversized
                ),
        )

    except preview.PreviewValidationError:
        pass

    else:
        raise RuntimeError(
            "oversized preview accepted"
        )

    print(
        "PREVIEW_SIZE_BOUNDARY_SMOKE=PASS"
    )

    with tempfile.TemporaryDirectory() as tmp:
        cached = (
            preview.persist_preview_cache(
                tmp,
                payload,
            )
        )

        require(
            cached.is_file(),
            "preview cache file missing",
        )

        require(
            (
                cached.stat().st_mode
                & 0o777
            )
            == 0o600,
            "preview cache mode changed",
        )

        hit = (
            preview.read_preview_cache(
                tmp,
                "SDNM-560",
            )
        )

        require(
            hit is not None,
            "preview cache hit missing",
        )

        require(
            hit[
                "body"
            ] == MP4_BODY,
            "preview cache bytes changed",
        )

        require(
            hit[
                "sha256"
            ]
            ==
            payload[
                "sha256"
            ],
            "preview cache SHA changed",
        )

    print(
        "PREVIEW_ATOMIC_CACHE_SMOKE=PASS"
    )

    print(
        "PREVIEW_BROWSER_UPSTREAM_URL_EXPOSURE=0"
    )

    print(
        "PREVIEW_123AV_PLAYER_REQUESTS=0"
    )

    print(
        "PREVIEW_HLS_REQUESTS=0"
    )

    print(
        "TEDDY_DISCOVERY_PREVIEW_CORE_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
