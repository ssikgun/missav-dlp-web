from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from urllib.parse import urlsplit

from teddy_discovery_cover import (
    ALLOWED_COVER_HOSTS,
    CoverUnavailable,
    CoverValidationError,
    cover_cache_path,
    get_cover,
    lookup_cover_request,
)


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


def file_sha256(
    path: Path,
) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def connect_ro(
    path: Path,
):
    connection = sqlite3.connect(
        "file:"
        + str(path)
        + "?mode=ro",
        uri=True,
    )

    connection.row_factory = (
        sqlite3.Row
    )

    return connection


def copy_db(
    source_path: Path,
    target_path: Path,
):
    source = sqlite3.connect(
        "file:"
        + str(source_path)
        + "?mode=ro",
        uri=True,
    )

    target = sqlite3.connect(
        target_path
    )

    try:
        source.backup(
            target
        )

    finally:
        target.close()
        source.close()


JPEG_BODY = (
    b"\xff\xd8\xff\xe0"
    + b"J"
    * 300
)

WEBP_BODY = (
    b"RIFF"
    + (304).to_bytes(
        4,
        "little",
    )
    + b"WEBP"
    + b"W"
    * 300
)


class FakeResponse:
    def __init__(
        self,
        *,
        status_code=200,
        content_type="image/jpeg",
        body=JPEG_BODY,
        location=None,
        chunks=None,
        content_length=None,
    ):
        self.status_code = (
            status_code
        )

        self.headers = {
            "Content-Type":
                content_type,
        }

        if location is not None:
            self.headers[
                "Location"
            ] = location

        if content_length is not None:
            self.headers[
                "Content-Length"
            ] = str(
                content_length
            )

        self.body = body

        self.chunks = (
            chunks
            if chunks is not None
            else [
                body
            ]
        )

        self.closed = False

    def iter_content(
        self,
        chunk_size,
    ):
        require(
            chunk_size > 0,
            "invalid requested chunk size",
        )

        for chunk in self.chunks:
            yield chunk

    def close(
        self,
    ):
        self.closed = True


class FakeSession:
    def __init__(
        self,
        responses,
    ):
        self.responses = list(
            responses
        )

        self.calls = []

    def get(
        self,
        url,
        **kwargs,
    ):
        self.calls.append({
            "url":
                url,

            "kwargs":
                kwargs,
        })

        if not self.responses:
            raise RuntimeError(
                "unexpected fake network call"
            )

        return self.responses.pop(
            0
        )


def inventory(
    db_path: Path,
):
    connection = connect_ro(
        db_path
    )

    try:
        rows = connection.execute(
            """
            SELECT
                dvd_id,
                cover_url,
                metadata_source
            FROM titles
            ORDER BY dvd_id
            """
        ).fetchall()

        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

    finally:
        connection.close()

    counts = {
        host:
            0
        for host
        in ALLOWED_COVER_HOSTS
    }

    samples = {}

    for row in rows:
        require(
            row[
                "cover_url"
            ] is not None,
            "real title missing cover URL",
        )

        host = (
            urlsplit(
                row[
                    "cover_url"
                ]
            ).hostname
            or ""
        ).lower()

        require(
            host
            in ALLOWED_COVER_HOSTS,
            "real cover host escaped "
            "allowlist",
        )

        counts[
            host
        ] += 1

        samples.setdefault(
            host,
            row[
                "dvd_id"
            ],
        )

    require(
        len(rows) == 117,
        "real title count changed",
    )

    require(
        counts == {
            "fourhoi.com":
                49,

            "www.javdatabase.com":
                68,
        },
        "real cover host counts changed",
    )

    require(
        integrity == "ok",
        "real DB integrity failed",
    )

    print(
        "COVER_CORE_REAL_HOST_COUNTS="
        + repr(
            counts
        )
    )

    print(
        "COVER_CORE_REAL_INVENTORY_SMOKE=PASS"
    )

    return samples


def cache_hit_smoke(
    db_path: Path,
    sample_id: str,
):
    connection = connect_ro(
        db_path
    )

    try:
        with tempfile.TemporaryDirectory(
            prefix=
                "teddy-cover-cache-hit-"
        ) as temp:
            cache_dir = Path(
                temp
            )

            response = FakeResponse(
                content_type=
                    "image/jpeg",

                body=
                    JPEG_BODY,

                content_length=
                    len(
                        JPEG_BODY
                    ),
            )

            session = FakeSession(
                [
                    response,
                ]
            )

            first = get_cover(
                connection,
                cache_dir,
                sample_id,
                session=session,
            )

            require(
                first[
                    "cache_hit"
                ] is False,
                "first cover unexpectedly "
                "came from cache",
            )

            require(
                first[
                    "route"
                ] == "fixed-vpn",
                "first cover route changed",
            )

            require(
                first[
                    "request_attempts"
                ] == 1,
                "first cover request count "
                "changed",
            )

            require(
                len(
                    session.calls
                ) == 1,
                "first cover did not make "
                "exactly one request",
            )

            call = session.calls[0]

            require(
                call[
                    "kwargs"
                ][
                    "proxies"
                ]
                == {
                    "http":
                        "http://gluetun:8888",

                    "https":
                        "http://gluetun:8888",
                },
                "cover fixed VPN proxy "
                "changed",
            )

            require(
                call[
                    "kwargs"
                ][
                    "allow_redirects"
                ] is False,
                "cover redirect policy "
                "changed",
            )

            require(
                call[
                    "kwargs"
                ][
                    "stream"
                ] is True,
                "cover bounded stream "
                "changed",
            )

            require(
                first[
                    "content_type"
                ]
                == "image/jpeg",
                "JPEG content type changed",
            )

            require(
                first[
                    "magic_type"
                ]
                == "jpeg",
                "JPEG magic changed",
            )

            require(
                Path(
                    first[
                        "cache_path"
                    ]
                ).is_file(),
                "cover cache file missing",
            )

            require(
                (
                    Path(
                        first[
                            "cache_path"
                        ]
                    ).stat().st_mode
                    & 0o777
                )
                == 0o600,
                "cover cache permission "
                "changed",
            )

            second = get_cover(
                connection,
                cache_dir,
                sample_id,
                session=session,
            )

            require(
                second[
                    "cache_hit"
                ] is True,
                "second cover did not "
                "hit cache",
            )

            require(
                second[
                    "route"
                ] == "cache",
                "cache-hit route changed",
            )

            require(
                second[
                    "request_attempts"
                ] == 0,
                "cache hit made request",
            )

            require(
                len(
                    session.calls
                ) == 1,
                "cache hit caused fake "
                "network request",
            )

            require(
                second[
                    "sha256"
                ]
                == first[
                    "sha256"
                ],
                "cache SHA changed",
            )

            require(
                second[
                    "body"
                ]
                == first[
                    "body"
                ],
                "cache body changed",
            )

    finally:
        connection.close()

    print(
        "COVER_CORE_FIXED_VPN_REQUEST_SMOKE=PASS"
    )

    print(
        "COVER_CORE_ATOMIC_CACHE_WRITE_SMOKE=PASS"
    )

    print(
        "COVER_CORE_CACHE_HIT_NETWORK_ZERO_SMOKE=PASS"
    )


def webp_smoke(
    db_path: Path,
    sample_id: str,
):
    connection = connect_ro(
        db_path
    )

    try:
        with tempfile.TemporaryDirectory(
            prefix=
                "teddy-cover-webp-"
        ) as temp:
            session = FakeSession([
                FakeResponse(
                    content_type=
                        "image/webp",

                    body=
                        WEBP_BODY,

                    content_length=
                        len(
                            WEBP_BODY
                        ),
                ),
            ])

            value = get_cover(
                connection,
                Path(temp),
                sample_id,
                session=session,
            )

            require(
                value[
                    "content_type"
                ]
                == "image/webp",
                "WebP content type changed",
            )

            require(
                value[
                    "magic_type"
                ]
                == "webp",
                "WebP magic changed",
            )

            require(
                value[
                    "cache_hit"
                ] is False,
                "WebP first request "
                "unexpectedly cached",
            )

            require(
                len(
                    session.calls
                ) == 1,
                "WebP fake request "
                "count changed",
            )

    finally:
        connection.close()

    print(
        "COVER_CORE_WEBP_CONTENT_SMOKE=PASS"
    )


def hostile_host_smoke(
    real_db: Path,
    sample_id: str,
):
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-cover-hostile-"
    ) as temp:
        root = Path(
            temp
        )

        temp_db = (
            root
            / "teddy-discovery.sqlite3"
        )

        copy_db(
            real_db,
            temp_db,
        )

        connection = sqlite3.connect(
            temp_db
        )

        connection.row_factory = (
            sqlite3.Row
        )

        session = FakeSession([
            FakeResponse(),
        ])

        try:
            connection.execute(
                """
                UPDATE titles
                SET cover_url =
                    'https://evil.example/cover.jpg'
                WHERE dvd_id = ?
                """,
                (
                    sample_id,
                ),
            )

            connection.commit()

            failed = False

            try:
                get_cover(
                    connection,
                    root
                    / "cache",
                    sample_id,
                    session=session,
                )

            except CoverValidationError:
                failed = True

            require(
                failed,
                "hostile cover host "
                "did not fail closed",
            )

            require(
                session.calls == [],
                "hostile host caused "
                "network request",
            )

        finally:
            connection.close()

    print(
        "COVER_CORE_HOST_ALLOWLIST_FAIL_CLOSED_SMOKE=PASS"
    )

    print(
        "COVER_CORE_HOST_REJECTION_NETWORK_ZERO_SMOKE=PASS"
    )


def failure_boundary_smoke(
    db_path: Path,
    sample_id: str,
):
    connection = connect_ro(
        db_path
    )

    try:
        #
        # Redirect
        #
        with tempfile.TemporaryDirectory(
            prefix=
                "teddy-cover-redirect-"
        ) as temp:
            session = FakeSession([
                FakeResponse(
                    status_code=302,
                    location=
                        "https://fourhoi.com/other.jpg",
                ),
            ])

            failed = False

            try:
                get_cover(
                    connection,
                    Path(temp),
                    sample_id,
                    session=session,
                )

            except CoverUnavailable:
                failed = True

            require(
                failed,
                "cover redirect did not "
                "fail closed",
            )

            require(
                not list(
                    Path(temp).glob(
                        "*.cover"
                    )
                ),
                "redirect failure "
                "wrote cache",
            )

        #
        # MIME / magic mismatch
        #
        with tempfile.TemporaryDirectory(
            prefix=
                "teddy-cover-mismatch-"
        ) as temp:
            session = FakeSession([
                FakeResponse(
                    content_type=
                        "image/jpeg",

                    body=
                        WEBP_BODY,
                ),
            ])

            failed = False

            try:
                get_cover(
                    connection,
                    Path(temp),
                    sample_id,
                    session=session,
                )

            except CoverValidationError:
                failed = True

            require(
                failed,
                "cover MIME mismatch "
                "did not fail closed",
            )

            require(
                not list(
                    Path(temp).glob(
                        "*.cover"
                    )
                ),
                "MIME mismatch "
                "wrote cache",
            )

        #
        # Streaming hard bound.
        #
        with tempfile.TemporaryDirectory(
            prefix=
                "teddy-cover-oversize-"
        ) as temp:
            chunks = [
                (
                    b"\xff\xd8\xff"
                    + b"A"
                    * 600
                ),
                b"B"
                * 600,
            ]

            session = FakeSession([
                FakeResponse(
                    content_type=
                        "image/jpeg",

                    chunks=
                        chunks,

                    body=
                        b"".join(
                            chunks
                        ),
                ),
            ])

            failed = False

            try:
                get_cover(
                    connection,
                    Path(temp),
                    sample_id,
                    session=session,
                    max_bytes=1000,
                )

            except CoverValidationError:
                failed = True

            require(
                failed,
                "cover oversize stream "
                "did not fail closed",
            )

            require(
                not list(
                    Path(temp).glob(
                        "*.cover"
                    )
                ),
                "oversize stream "
                "wrote cache",
            )

    finally:
        connection.close()

    print(
        "COVER_CORE_REDIRECT_FAIL_CLOSED_SMOKE=PASS"
    )

    print(
        "COVER_CORE_MIME_MAGIC_FAIL_CLOSED_SMOKE=PASS"
    )

    print(
        "COVER_CORE_STREAM_SIZE_BOUND_SMOKE=PASS"
    )

    print(
        "COVER_CORE_INVALID_RESPONSE_CACHE_ZERO_SMOKE=PASS"
    )


def source_change_cache_smoke(
    real_db: Path,
    sample_id: str,
):
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-cover-source-change-"
    ) as temp:
        root = Path(
            temp
        )

        temp_db = (
            root
            / "teddy-discovery.sqlite3"
        )

        cache_dir = (
            root
            / "cache"
        )

        copy_db(
            real_db,
            temp_db,
        )

        connection = sqlite3.connect(
            temp_db
        )

        connection.row_factory = (
            sqlite3.Row
        )

        try:
            original = lookup_cover_request(
                connection,
                sample_id,
            )

            first_session = FakeSession([
                FakeResponse(
                    content_type=
                        "image/jpeg",

                    body=
                        JPEG_BODY,
                ),
            ])

            first = get_cover(
                connection,
                cache_dir,
                sample_id,
                session=first_session,
            )

            old_path = Path(
                first[
                    "cache_path"
                ]
            )

            separator = (
                "&"
                if "?"
                in original[
                    "url"
                ]
                else "?"
            )

            changed_url = (
                original[
                    "url"
                ]
                + separator
                + "teddy_cache_version=2"
            )

            connection.execute(
                """
                UPDATE titles
                SET cover_url = ?
                WHERE dvd_id = ?
                """,
                (
                    changed_url,
                    sample_id,
                ),
            )

            connection.commit()

            changed = lookup_cover_request(
                connection,
                sample_id,
            )

            new_expected_path = (
                cover_cache_path(
                    cache_dir,
                    changed,
                )
            )

            require(
                new_expected_path
                != old_path,
                "cover source URL change "
                "did not change cache key",
            )

            second_session = FakeSession([
                FakeResponse(
                    content_type=
                        "image/jpeg",

                    body=
                        (
                            b"\xff\xd8\xff\xe1"
                            + b"N"
                            * 300
                        ),
                ),
            ])

            second = get_cover(
                connection,
                cache_dir,
                sample_id,
                session=second_session,
            )

            require(
                second[
                    "cache_hit"
                ] is False,
                "changed source URL "
                "reused stale cache",
            )

            require(
                len(
                    second_session.calls
                ) == 1,
                "changed source URL "
                "did not refetch",
            )

            require(
                Path(
                    second[
                        "cache_path"
                    ]
                )
                == new_expected_path,
                "changed source URL "
                "cache path mismatch",
            )

            require(
                second[
                    "sha256"
                ]
                != first[
                    "sha256"
                ],
                "changed source payload "
                "did not change SHA",
            )

        finally:
            connection.close()

    print(
        "COVER_CORE_SOURCE_URL_KEYED_CACHE_SMOKE=PASS"
    )

    print(
        "COVER_CORE_STALE_CACHE_AVOIDANCE_SMOKE=PASS"
    )


def main():
    if len(
        sys.argv
    ) != 2:
        raise RuntimeError(
            "usage: "
            "teddy_discovery_cover_smoke.py "
            "<stage5-db>"
        )

    db_path = Path(
        sys.argv[1]
    )

    before = file_sha256(
        db_path
    )

    samples = inventory(
        db_path
    )

    fourhoi_id = samples[
        "fourhoi.com"
    ]

    javdb_id = samples[
        "www.javdatabase.com"
    ]

    cache_hit_smoke(
        db_path,
        fourhoi_id,
    )

    webp_smoke(
        db_path,
        javdb_id,
    )

    hostile_host_smoke(
        db_path,
        fourhoi_id,
    )

    failure_boundary_smoke(
        db_path,
        fourhoi_id,
    )

    source_change_cache_smoke(
        db_path,
        fourhoi_id,
    )

    after = file_sha256(
        db_path
    )

    require(
        after == before,
        "cover smoke changed "
        "real Stage 5 DB bytes",
    )

    oracle_payload = {
        "allowed_hosts":
            list(
                ALLOWED_COVER_HOSTS
            ),

        "host_counts": {
            "fourhoi.com":
                49,

            "www.javdatabase.com":
                68,
        },

        "fourhoi_sample":
            fourhoi_id,

        "javdatabase_sample":
            javdb_id,

        "jpeg_sha256":
            hashlib.sha256(
                JPEG_BODY
            ).hexdigest(),

        "webp_sha256":
            hashlib.sha256(
                WEBP_BODY
            ).hexdigest(),
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
        "COVER_CORE_ORACLE_SHA256="
        + oracle
    )

    print(
        "COVER_CORE_REAL_DB_BYTE_UNCHANGED_SMOKE=PASS"
    )

    print(
        "TEDDY_DISCOVERY_COVER_CORE_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
