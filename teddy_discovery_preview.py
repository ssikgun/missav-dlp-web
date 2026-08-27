from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
from typing import Any
from urllib.parse import urlsplit

import teddy_routing

from teddy_discovery_availability import (
    canonical_dvd_id,
)


PREVIEW_CACHE_VERSION = "v1"

PREVIEW_HOST = "fourhoi.com"

DEFAULT_TIMEOUT_SECONDS = 45
DEFAULT_IMPERSONATE = "chrome"

MIN_PREVIEW_BYTES = 32
MAX_PREVIEW_BYTES = 2 * 1024 * 1024

STREAM_CHUNK_BYTES = 64 * 1024


_PREVIEW_LOCKS_GUARD = threading.Lock()
_PREVIEW_LOCKS = {}


def _preview_lock(
    dvd_id: Any,
) -> threading.Lock:
    dvd_id = canonical_dvd_id(
        dvd_id
    )

    with _PREVIEW_LOCKS_GUARD:
        lock = _PREVIEW_LOCKS.get(
            dvd_id
        )

        if lock is None:
            lock = threading.Lock()

            _PREVIEW_LOCKS[
                dvd_id
            ] = lock

        return lock


class PreviewNotFound(
    LookupError
):
    pass


class PreviewValidationError(
    RuntimeError
):
    pass


class PreviewUnavailable(
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
            "preview connection must "
            "be sqlite3.Connection"
        )

    if (
        connection.row_factory
        is not sqlite3.Row
    ):
        raise ValueError(
            "preview connection must "
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
            "preview timeout must be "
            "1..120 seconds"
        )

    return value


def _validated_max_bytes(
    value: Any,
) -> int:
    if (
        type(value) is not int
        or value < MIN_PREVIEW_BYTES
        or value > MAX_PREVIEW_BYTES
    ):
        raise ValueError(
            "preview max_bytes must be "
            + str(
                MIN_PREVIEW_BYTES
            )
            + ".."
            + str(
                MAX_PREVIEW_BYTES
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
            "preview impersonate missing"
        )

    return value


def preview_url_for_dvd_id(
    dvd_id: Any,
) -> str:
    dvd_id = canonical_dvd_id(
        dvd_id
    )

    return (
        "https://"
        + PREVIEW_HOST
        + "/"
        + dvd_id.lower()
        + "/preview.mp4"
    )


def _validated_preview_url(
    value: Any,
    *,
    dvd_id: Any,
) -> str:
    dvd_id = canonical_dvd_id(
        dvd_id
    )

    expected = preview_url_for_dvd_id(
        dvd_id
    )

    value = _text(
        value
    )

    if value != expected:
        raise PreviewValidationError(
            "preview URL escaped "
            "deterministic path"
        )

    try:
        parsed = urlsplit(
            value
        )

    except Exception as exc:
        raise PreviewValidationError(
            "preview URL invalid"
        ) from exc

    try:
        port = parsed.port

    except ValueError as exc:
        raise PreviewValidationError(
            "preview URL port invalid"
        ) from exc

    if parsed.scheme != "https":
        raise PreviewValidationError(
            "preview URL must use https"
        )

    if (
        parsed.hostname
        != PREVIEW_HOST
    ):
        raise PreviewValidationError(
            "preview URL host invalid"
        )

    if (
        parsed.username
        or parsed.password
    ):
        raise PreviewValidationError(
            "preview URL credentials forbidden"
        )

    if port not in {
        None,
        443,
    }:
        raise PreviewValidationError(
            "preview URL port forbidden"
        )

    if (
        parsed.query
        or parsed.fragment
    ):
        raise PreviewValidationError(
            "preview URL query/fragment forbidden"
        )

    return value


def lookup_preview_request(
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
        SELECT dvd_id
        FROM titles
        WHERE dvd_id = ?
        """,
        (
            dvd_id,
        ),
    ).fetchone()

    if row is None:
        raise PreviewNotFound(
            "preview title not found"
        )

    url = preview_url_for_dvd_id(
        dvd_id
    )

    return {
        "dvd_id":
            dvd_id,

        "url":
            url,

        "host":
            PREVIEW_HOST,

        "referer":
            (
                "https://missav.ws/ko/"
                + dvd_id.lower()
            ),
    }


def _mp4_magic(
    content: bytes,
) -> bool:
    return (
        len(content) >= 12
        and content[
            4:8
        ] == b"ftyp"
    )


def validate_preview_bytes(
    *,
    content_type: Any,
    content: bytes,
    max_bytes: int = MAX_PREVIEW_BYTES,
) -> dict:
    max_bytes = _validated_max_bytes(
        max_bytes
    )

    if not isinstance(
        content,
        bytes,
    ):
        raise TypeError(
            "preview content must be bytes"
        )

    content_type = (
        _text(
            content_type
        )
        or ""
    )

    content_type = (
        content_type
        .split(
            ";",
            1,
        )[0]
        .strip()
        .lower()
    )

    if content_type != "video/mp4":
        raise PreviewValidationError(
            "preview content type invalid"
        )

    body_bytes = len(
        content
    )

    if (
        body_bytes
        < MIN_PREVIEW_BYTES
    ):
        raise PreviewValidationError(
            "preview body too small"
        )

    if body_bytes > max_bytes:
        raise PreviewValidationError(
            "preview body too large"
        )

    if not _mp4_magic(
        content
    ):
        raise PreviewValidationError(
            "preview MP4 magic invalid"
        )

    return {
        "content_type":
            "video/mp4",

        "magic_type":
            "mp4",

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
        raise PreviewUnavailable(
            "preview VPN proxy unavailable"
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
        raise PreviewUnavailable(
            "preview VPN proxy invalid"
        )

    return value


def _new_session():
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
        raise PreviewValidationError(
            "preview Content-Length invalid"
        ) from exc

    if parsed < 0:
        raise PreviewValidationError(
            "preview Content-Length invalid"
        )

    return parsed


def fetch_preview_payload(
    request_value: dict,
    *,
    session=None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    impersonate: str = DEFAULT_IMPERSONATE,
    max_bytes: int = MAX_PREVIEW_BYTES,
) -> dict:
    if not isinstance(
        request_value,
        dict,
    ):
        raise TypeError(
            "preview request must be dict"
        )

    dvd_id = canonical_dvd_id(
        request_value.get(
            "dvd_id"
        )
    )

    url = _validated_preview_url(
        request_value.get(
            "url"
        ),
        dvd_id=dvd_id,
    )

    expected_referer = (
        "https://missav.ws/ko/"
        + dvd_id.lower()
    )

    if (
        request_value.get(
            "host"
        )
        != PREVIEW_HOST
    ):
        raise PreviewValidationError(
            "preview host policy changed"
        )

    if (
        request_value.get(
            "referer"
        )
        != expected_referer
    ):
        raise PreviewValidationError(
            "preview referer policy changed"
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

    proxy_url = vpn_proxy_url()

    owned_session = (
        session is None
    )

    if owned_session:
        session = _new_session()

    response = None

    try:
        try:
            response = session.get(
                url,

                proxies={
                    "http":
                        proxy_url,

                    "https":
                        proxy_url,
                },

                headers={
                    "Accept":
                        "video/mp4,"
                        "video/*;q=0.9,"
                        "*/*;q=0.5",

                    "Accept-Encoding":
                        "identity",

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
            raise PreviewUnavailable(
                "preview request failed"
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
            raise PreviewUnavailable(
                "preview redirect forbidden"
            )

        if status == 404:
            raise PreviewNotFound(
                "preview asset not found"
            )

        if status != 200:
            raise PreviewUnavailable(
                "preview HTTP status "
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
            raise PreviewValidationError(
                "preview Content-Type missing"
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

        if normalized_type != "video/mp4":
            raise PreviewValidationError(
                "preview Content-Type invalid"
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
            raise PreviewValidationError(
                "preview Content-Length "
                "exceeds limit"
            )

        chunks = []
        total = 0

        for chunk in (
            response.iter_content(
                chunk_size=
                    STREAM_CHUNK_BYTES
            )
        ):
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
                raise PreviewValidationError(
                    "preview stream "
                    "exceeds limit"
                )

            chunks.append(
                chunk
            )

        content = b"".join(
            chunks
        )

        validated = validate_preview_bytes(
            content_type=
                normalized_type,

            content=
                content,

            max_bytes=
                max_bytes,
        )

        validated.update(
            {
                "dvd_id":
                    dvd_id,

                "url":
                    url,

                "host":
                    PREVIEW_HOST,

                "referer":
                    expected_referer,

                "route":
                    "fixed-vpn",

                "request_attempts":
                    1,

                "redirects_followed":
                    0,
            }
        )

        return validated

    finally:
        if response is not None:
            close = getattr(
                response,
                "close",
                None,
            )

            if callable(
                close
            ):
                close()

        if owned_session:
            close = getattr(
                session,
                "close",
                None,
            )

            if callable(
                close
            ):
                close()


def preview_cache_path(
    cache_root: Any,
    dvd_id: Any,
) -> Path:
    dvd_id = canonical_dvd_id(
        dvd_id
    )

    root = Path(
        cache_root
    )

    return (
        root
        / PREVIEW_CACHE_VERSION
        / (
            dvd_id.lower()
            + ".mp4"
        )
    )


def persist_preview_cache(
    cache_root: Any,
    payload: dict,
) -> Path:
    if not isinstance(
        payload,
        dict,
    ):
        raise TypeError(
            "preview payload must be dict"
        )

    dvd_id = canonical_dvd_id(
        payload.get(
            "dvd_id"
        )
    )

    validated = validate_preview_bytes(
        content_type=
            payload.get(
                "content_type"
            ),

        content=
            payload.get(
                "body"
            ),
    )

    expected_sha = _text(
        payload.get(
            "sha256"
        )
    )

    if (
        expected_sha
        and expected_sha
        != validated[
            "sha256"
        ]
    ):
        raise PreviewValidationError(
            "preview SHA mismatch"
        )

    target = preview_cache_path(
        cache_root,
        dvd_id,
    )

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fd = None
    temp_name = None

    try:
        fd, temp_name = tempfile.mkstemp(
            prefix=
                ".preview.",

            suffix=
                ".tmp",

            dir=
                str(
                    target.parent
                ),
        )

        os.fchmod(
            fd,
            0o600,
        )

        with os.fdopen(
            fd,
            "wb",
        ) as file_obj:
            fd = None

            file_obj.write(
                validated[
                    "body"
                ]
            )

            file_obj.flush()

            os.fsync(
                file_obj.fileno()
            )

        os.replace(
            temp_name,
            target,
        )

        temp_name = None

        os.chmod(
            target,
            0o600,
        )

        return target

    finally:
        if fd is not None:
            os.close(
                fd
            )

        if temp_name is not None:
            try:
                os.unlink(
                    temp_name
                )
            except FileNotFoundError:
                pass


def read_preview_cache(
    cache_root: Any,
    dvd_id: Any,
) -> dict | None:
    path = preview_cache_path(
        cache_root,
        dvd_id,
    )

    try:
        content = path.read_bytes()

    except FileNotFoundError:
        return None

    validated = validate_preview_bytes(
        content_type=
            "video/mp4",

        content=
            content,
    )

    validated[
        "path"
    ] = path

    validated[
        "dvd_id"
    ] = canonical_dvd_id(
        dvd_id
    )

    return validated



def get_preview(
    connection: sqlite3.Connection,
    cache_root: Any,
    dvd_id: Any,
    *,
    session=None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    impersonate: str = DEFAULT_IMPERSONATE,
    max_bytes: int = MAX_PREVIEW_BYTES,
) -> dict:
    request_value = lookup_preview_request(
        connection,
        dvd_id,
    )

    dvd_id = request_value[
        "dvd_id"
    ]

    #
    # Fast path before taking the
    # per-title singleflight lock.
    #
    cached = read_preview_cache(
        cache_root,
        dvd_id,
    )

    if cached is not None:
        result = dict(
            cached
        )

        result[
            "route"
        ] = "cache"

        result[
            "cache_hit"
        ] = True

        result[
            "request_attempts"
        ] = 0

        result[
            "redirects_followed"
        ] = 0

        return result

    lock = _preview_lock(
        dvd_id
    )

    with lock:
        #
        # Another request may have filled
        # the cache while this request was
        # waiting for the title lock.
        #
        cached = read_preview_cache(
            cache_root,
            dvd_id,
        )

        if cached is not None:
            result = dict(
                cached
            )

            result[
                "route"
            ] = "cache"

            result[
                "cache_hit"
            ] = True

            result[
                "request_attempts"
            ] = 0

            result[
                "redirects_followed"
            ] = 0

            return result

        payload = fetch_preview_payload(
            request_value,
            session=session,
            timeout=timeout,
            impersonate=impersonate,
            max_bytes=max_bytes,
        )

        cache_path = persist_preview_cache(
            cache_root,
            payload,
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
