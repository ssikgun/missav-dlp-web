from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Any
from urllib.parse import urlsplit

import teddy_routing

from teddy_discovery_availability import (
    canonical_dvd_id,
)


COVER_CACHE_VERSION = "v1"

ALLOWED_COVER_HOSTS = (
    "fourhoi.com",
    "www.javdatabase.com",
)

CONTENT_TYPE_MAGIC = {
    "image/jpeg":
        "jpeg",

    "image/png":
        "png",

    "image/webp":
        "webp",

    "image/avif":
        "avif",

    "image/gif":
        "gif",
}

DEFAULT_TIMEOUT_SECONDS = 45
DEFAULT_IMPERSONATE = "chrome"

MIN_COVER_BYTES = 100
MAX_COVER_BYTES = 10 * 1024 * 1024
STREAM_CHUNK_BYTES = 64 * 1024


class CoverNotFound(
    LookupError
):
    pass


class CoverValidationError(
    RuntimeError
):
    pass


class CoverUnavailable(
    RuntimeError
):
    pass


def _text(
    value: Any,
) -> str | None:
    if value is None:
        return None

    value = str(
        value
    ).strip()

    return value or None


def _require_connection(
    connection: sqlite3.Connection,
) -> None:
    if not isinstance(
        connection,
        sqlite3.Connection,
    ):
        raise TypeError(
            "cover connection must "
            "be sqlite3.Connection"
        )

    if (
        connection.row_factory
        is not sqlite3.Row
    ):
        raise ValueError(
            "cover connection must "
            "use sqlite3.Row"
        )


def _validated_timeout(
    value: Any,
) -> int:
    if (
        type(value) is not int
        or value < 1
        or value > 120
    ):
        raise ValueError(
            "cover timeout must be "
            "1..120 seconds"
        )

    return value


def _validated_max_bytes(
    value: Any,
) -> int:
    if (
        type(value) is not int
        or value < MIN_COVER_BYTES
        or value > MAX_COVER_BYTES
    ):
        raise ValueError(
            "cover max_bytes must be "
            + str(
                MIN_COVER_BYTES
            )
            + ".."
            + str(
                MAX_COVER_BYTES
            )
        )

    return value


def _validated_impersonate(
    value: Any,
) -> str:
    value = _text(
        value
    )

    if not value:
        raise ValueError(
            "cover impersonate missing"
        )

    return value


def _validated_cover_url(
    value: Any,
) -> dict:
    url = _text(
        value
    )

    if not url:
        raise CoverValidationError(
            "cover URL missing"
        )

    try:
        parsed = urlsplit(
            url
        )

    except Exception as exc:
        raise CoverValidationError(
            "cover URL invalid"
        ) from exc

    host = (
        parsed.hostname
        or ""
    ).lower()

    try:
        port = parsed.port

    except ValueError as exc:
        raise CoverValidationError(
            "cover URL port invalid"
        ) from exc

    if parsed.scheme != "https":
        raise CoverValidationError(
            "cover URL must use https"
        )

    if host not in ALLOWED_COVER_HOSTS:
        raise CoverValidationError(
            "cover URL host not allowed"
        )

    if parsed.username or parsed.password:
        raise CoverValidationError(
            "cover URL credentials forbidden"
        )

    if port not in {
        None,
        443,
    }:
        raise CoverValidationError(
            "cover URL port forbidden"
        )

    if not parsed.path.startswith(
        "/"
    ):
        raise CoverValidationError(
            "cover URL path invalid"
        )

    if parsed.fragment:
        raise CoverValidationError(
            "cover URL fragment forbidden"
        )

    return {
        "url":
            url,

        "host":
            host,
    }


def _referer_for_host(
    host: str,
) -> str:
    if host == "fourhoi.com":
        return "https://missav.ws/"

    if host == "www.javdatabase.com":
        return "https://www.javdatabase.com/"

    raise CoverValidationError(
        "cover host has no referer policy"
    )


def lookup_cover_request(
    connection: sqlite3.Connection,
    dvd_id: Any,
) -> dict:
    _require_connection(
        connection
    )

    dvd_id = canonical_dvd_id(
        dvd_id
    )

    row = connection.execute(
        """
        SELECT
            dvd_id,
            cover_url,
            metadata_source
        FROM titles
        WHERE dvd_id = ?
        """,
        (
            dvd_id,
        ),
    ).fetchone()

    if row is None:
        raise CoverNotFound(
            "cover title not found"
        )

    validated = (
        _validated_cover_url(
            row[
                "cover_url"
            ]
        )
    )

    return {
        "dvd_id":
            dvd_id,

        "url":
            validated[
                "url"
            ],

        "host":
            validated[
                "host"
            ],

        "referer":
            _referer_for_host(
                validated[
                    "host"
                ]
            ),

        "metadata_source":
            row[
                "metadata_source"
            ],
    }


def _magic_type(
    content: bytes,
) -> str:
    if content.startswith(
        b"\xff\xd8\xff"
    ):
        return "jpeg"

    if content.startswith(
        b"\x89PNG\r\n\x1a\n"
    ):
        return "png"

    if (
        len(content) >= 12
        and content[
            0:4
        ] == b"RIFF"
        and content[
            8:12
        ] == b"WEBP"
    ):
        return "webp"

    if (
        len(content) >= 12
        and content[
            4:8
        ] == b"ftyp"
        and content[
            8:12
        ] in {
            b"avif",
            b"avis",
        }
    ):
        return "avif"

    if content.startswith(
        (
            b"GIF87a",
            b"GIF89a",
        )
    ):
        return "gif"

    return "unknown"


def validate_cover_bytes(
    *,
    content_type: Any,
    content: bytes,
    max_bytes: int = MAX_COVER_BYTES,
) -> dict:
    max_bytes = _validated_max_bytes(
        max_bytes
    )

    content_type = _text(
        content_type
    )

    if content_type:
        content_type = (
            content_type
            .split(
                ";",
                1,
            )[0]
            .strip()
            .lower()
        )

    if (
        content_type
        not in CONTENT_TYPE_MAGIC
    ):
        raise CoverValidationError(
            "cover content type invalid"
        )

    if not isinstance(
        content,
        bytes,
    ):
        raise TypeError(
            "cover content must be bytes"
        )

    body_bytes = len(
        content
    )

    if body_bytes < MIN_COVER_BYTES:
        raise CoverValidationError(
            "cover body too small"
        )

    if body_bytes > max_bytes:
        raise CoverValidationError(
            "cover body too large"
        )

    magic = _magic_type(
        content
    )

    if magic == "unknown":
        raise CoverValidationError(
            "cover magic unknown"
        )

    if (
        CONTENT_TYPE_MAGIC[
            content_type
        ]
        != magic
    ):
        raise CoverValidationError(
            "cover content type/magic mismatch"
        )

    return {
        "content_type":
            content_type,

        "magic_type":
            magic,

        "body_bytes":
            body_bytes,

        "sha256":
            hashlib.sha256(
                content
            ).hexdigest(),

        "body":
            content,
    }


def vpn_proxy_url() -> str:
    value = _text(
        teddy_routing.proxy_for_mode(
            "vpn"
        )
    )

    if not value:
        raise CoverUnavailable(
            "cover VPN proxy unavailable"
        )

    parsed = urlsplit(
        value
    )

    if (
        parsed.scheme
        not in {
            "http",
            "https",
        }
        or not parsed.hostname
    ):
        raise CoverUnavailable(
            "cover VPN proxy invalid"
        )

    return value


def _new_session():
    #
    # Lazy import keeps all offline smoke
    # runnable on the CT108 host Python.
    #
    from curl_cffi import (
        requests as cffi_requests,
    )

    return cffi_requests.Session()


def _content_length(
    value: Any,
) -> int | None:
    value = _text(
        value
    )

    if value is None:
        return None

    try:
        parsed = int(
            value
        )

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise CoverValidationError(
            "cover Content-Length invalid"
        ) from exc

    if parsed < 0:
        raise CoverValidationError(
            "cover Content-Length invalid"
        )

    return parsed


def fetch_cover_payload(
    request_value: dict,
    *,
    session=None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    impersonate: str = DEFAULT_IMPERSONATE,
    max_bytes: int = MAX_COVER_BYTES,
) -> dict:
    if not isinstance(
        request_value,
        dict,
    ):
        raise TypeError(
            "cover request must be dict"
        )

    dvd_id = canonical_dvd_id(
        request_value.get(
            "dvd_id"
        )
    )

    validated_url = (
        _validated_cover_url(
            request_value.get(
                "url"
            )
        )
    )

    host = validated_url[
        "host"
    ]

    expected_referer = (
        _referer_for_host(
            host
        )
    )

    if (
        request_value.get(
            "referer"
        )
        != expected_referer
    ):
        raise CoverValidationError(
            "cover referer policy changed"
        )

    timeout = _validated_timeout(
        timeout
    )

    impersonate = (
        _validated_impersonate(
            impersonate
        )
    )

    max_bytes = _validated_max_bytes(
        max_bytes
    )

    #
    # Resolve the fixed VPN route before
    # constructing/using a network session.
    #
    proxy_url = vpn_proxy_url()

    owned_session = (
        session is None
    )

    if owned_session:
        session = _new_session()

    response = None
    request_attempts = 0

    try:
        request_attempts += 1

        try:
            response = session.get(
                validated_url[
                    "url"
                ],

                proxies={
                    "http":
                        proxy_url,

                    "https":
                        proxy_url,
                },

                headers={
                    "Accept":
                        "image/avif,"
                        "image/webp,"
                        "image/apng,"
                        "image/*,"
                        "*/*;q=0.8",

                    "Referer":
                        expected_referer,
                },

                timeout=timeout,

                impersonate=
                    impersonate,

                allow_redirects=False,

                stream=True,
            )

        except Exception as exc:
            raise CoverUnavailable(
                "cover request failed"
            ) from exc

        status = int(
            response.status_code
        )

        location = _text(
            response.headers.get(
                "Location"
            )
        )

        if location:
            raise CoverUnavailable(
                "cover redirect forbidden"
            )

        if status != 200:
            raise CoverUnavailable(
                "cover HTTP status "
                + str(
                    status
                )
            )

        content_type = _text(
            response.headers.get(
                "Content-Type"
            )
        )

        if content_type is None:
            raise CoverValidationError(
                "cover Content-Type missing"
            )

        normalized_type = (
            content_type
            .split(
                ";",
                1,
            )[0]
            .strip()
            .lower()
        )

        if (
            normalized_type
            not in CONTENT_TYPE_MAGIC
        ):
            raise CoverValidationError(
                "cover Content-Type invalid"
            )

        length = _content_length(
            response.headers.get(
                "Content-Length"
            )
        )

        if (
            length is not None
            and length > max_bytes
        ):
            raise CoverValidationError(
                "cover Content-Length "
                "exceeds limit"
            )

        chunks = []
        total = 0

        try:
            iterator = response.iter_content(
                chunk_size=
                    STREAM_CHUNK_BYTES
            )

            for chunk in iterator:
                if not chunk:
                    continue

                if not isinstance(
                    chunk,
                    bytes,
                ):
                    chunk = bytes(
                        chunk
                    )

                total += len(
                    chunk
                )

                if total > max_bytes:
                    raise CoverValidationError(
                        "cover stream "
                        "exceeds limit"
                    )

                chunks.append(
                    chunk
                )

        except CoverValidationError:
            raise

        except Exception as exc:
            raise CoverUnavailable(
                "cover stream failed"
            ) from exc

        content = b"".join(
            chunks
        )

        validated = (
            validate_cover_bytes(
                content_type=
                    normalized_type,

                content=
                    content,

                max_bytes=
                    max_bytes,
            )
        )

        return {
            "dvd_id":
                dvd_id,

            "route":
                "fixed-vpn",

            "request_attempts":
                request_attempts,

            "redirects_followed":
                0,

            "content_type":
                validated[
                    "content_type"
                ],

            "magic_type":
                validated[
                    "magic_type"
                ],

            "body_bytes":
                validated[
                    "body_bytes"
                ],

            "sha256":
                validated[
                    "sha256"
                ],

            "body":
                validated[
                    "body"
                ],
        }

    finally:
        if response is not None:
            try:
                response.close()

            except Exception:
                pass

        if owned_session:
            try:
                session.close()

            except Exception:
                pass


def _cover_cache_key(
    request_value: dict,
) -> str:
    dvd_id = canonical_dvd_id(
        request_value.get(
            "dvd_id"
        )
    )

    validated = _validated_cover_url(
        request_value.get(
            "url"
        )
    )

    canonical = (
        COVER_CACHE_VERSION
        + "\n"
        + dvd_id
        + "\n"
        + validated[
            "url"
        ]
    ).encode(
        "utf-8"
    )

    return hashlib.sha256(
        canonical
    ).hexdigest()


def cover_cache_path(
    cache_dir: Any,
    request_value: dict,
) -> Path:
    root_text = _text(
        cache_dir
    )

    if not root_text:
        raise ValueError(
            "cover cache directory missing"
        )

    root = Path(
        root_text
    )

    key = _cover_cache_key(
        request_value
    )

    return (
        root
        / (
            key
            + ".cover"
        )
    )


def _cache_root(
    cache_dir: Any,
) -> Path:
    root_text = _text(
        cache_dir
    )

    if not root_text:
        raise ValueError(
            "cover cache directory missing"
        )

    root = Path(
        root_text
    )

    if (
        root.exists()
        and root.is_symlink()
    ):
        raise CoverUnavailable(
            "cover cache root "
            "must not be symlink"
        )

    return root


def read_cached_cover(
    cache_dir: Any,
    request_value: dict,
    *,
    max_bytes: int = MAX_COVER_BYTES,
) -> dict | None:
    max_bytes = _validated_max_bytes(
        max_bytes
    )

    root = _cache_root(
        cache_dir
    )

    path = cover_cache_path(
        root,
        request_value,
    )

    if not path.exists():
        return None

    if (
        path.is_symlink()
        or not path.is_file()
    ):
        raise CoverUnavailable(
            "cover cache entry invalid"
        )

    with path.open(
        "rb"
    ) as fh:
        content = fh.read(
            max_bytes + 1
        )

    if len(
        content
    ) > max_bytes:
        raise CoverUnavailable(
            "cached cover exceeds limit"
        )

    magic = _magic_type(
        content
    )

    type_by_magic = {
        value:
            key
        for key, value
        in CONTENT_TYPE_MAGIC.items()
    }

    content_type = (
        type_by_magic.get(
            magic
        )
    )

    if content_type is None:
        raise CoverUnavailable(
            "cached cover magic invalid"
        )

    try:
        validated = validate_cover_bytes(
            content_type=
                content_type,

            content=
                content,

            max_bytes=
                max_bytes,
        )

    except CoverValidationError as exc:
        raise CoverUnavailable(
            "cached cover invalid"
        ) from exc

    return {
        "dvd_id":
            canonical_dvd_id(
                request_value.get(
                    "dvd_id"
                )
            ),

        "route":
            "cache",

        "cache_hit":
            True,

        "request_attempts":
            0,

        "redirects_followed":
            0,

        "content_type":
            validated[
                "content_type"
            ],

        "magic_type":
            validated[
                "magic_type"
            ],

        "body_bytes":
            validated[
                "body_bytes"
            ],

        "sha256":
            validated[
                "sha256"
            ],

        "body":
            validated[
                "body"
            ],

        "cache_path":
            path,
    }


def persist_cover_cache(
    cache_dir: Any,
    request_value: dict,
    payload: dict,
    *,
    max_bytes: int = MAX_COVER_BYTES,
) -> Path:
    max_bytes = _validated_max_bytes(
        max_bytes
    )

    root = _cache_root(
        cache_dir
    )

    content = payload.get(
        "body"
    )

    validated = validate_cover_bytes(
        content_type=
            payload.get(
                "content_type"
            ),

        content=
            content,

        max_bytes=
            max_bytes,
    )

    if (
        payload.get(
            "sha256"
        )
        != validated[
            "sha256"
        ]
    ):
        raise CoverValidationError(
            "cover payload SHA mismatch"
        )

    path = cover_cache_path(
        root,
        request_value,
    )

    root.mkdir(
        parents=True,
        exist_ok=True,
    )

    if root.is_symlink():
        raise CoverUnavailable(
            "cover cache root "
            "must not be symlink"
        )

    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=root,
            prefix=".cover-",
            suffix=".tmp",
            delete=False,
        ) as fh:
            temp_path = Path(
                fh.name
            )

            fh.write(
                validated[
                    "body"
                ]
            )

            fh.flush()

            os.fsync(
                fh.fileno()
            )

        os.chmod(
            temp_path,
            0o600,
        )

        os.replace(
            temp_path,
            path,
        )

        temp_path = None

        try:
            directory_fd = os.open(
                root,
                os.O_RDONLY,
            )

            try:
                os.fsync(
                    directory_fd
                )

            finally:
                os.close(
                    directory_fd
                )

        except OSError:
            #
            # Directory fsync is best-effort
            # across filesystems.
            #
            pass

    finally:
        if (
            temp_path is not None
            and temp_path.exists()
        ):
            try:
                temp_path.unlink()

            except OSError:
                pass

    return path


def get_cover(
    connection: sqlite3.Connection,
    cache_dir: Any,
    dvd_id: Any,
    *,
    session=None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    impersonate: str = DEFAULT_IMPERSONATE,
    max_bytes: int = MAX_COVER_BYTES,
) -> dict:
    request_value = lookup_cover_request(
        connection,
        dvd_id,
    )

    cached = read_cached_cover(
        cache_dir,
        request_value,
        max_bytes=
            max_bytes,
    )

    if cached is not None:
        return cached

    payload = fetch_cover_payload(
        request_value,
        session=session,
        timeout=timeout,
        impersonate=impersonate,
        max_bytes=max_bytes,
    )

    cache_path = persist_cover_cache(
        cache_dir,
        request_value,
        payload,
        max_bytes=max_bytes,
    )

    result = dict(
        payload
    )

    result[
        "cache_hit"
    ] = False

    result[
        "cache_path"
    ] = cache_path

    return result
