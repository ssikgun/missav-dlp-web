from __future__ import annotations

from datetime import (
    datetime,
    timezone,
)
from pathlib import Path
from typing import Any
from urllib.parse import (
    parse_qs,
    unquote,
    urlparse,
)

import teddy_routing

from teddy_discovery_db import (
    connect,
    initialize,
)

from teddy_discovery_missav import (
    MISSAV_RELEASE_SOURCE,
    merge_missav_release_envelopes,
    missav_release_next_url_from_envelope,
    parse_missav_release_envelope,
    upsert_latest_items,
)


DEFAULT_RELEASE_URL = (
    "https://missav.ws/ko/release"
)

DEFAULT_LIMIT = 50
DEFAULT_MAX_PAGES = 5
DEFAULT_TIMEOUT_SECONDS = 45
DEFAULT_IMPERSONATE = "chrome"
DEFAULT_LANGUAGE = "ko"


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )


def _text(
    value: Any,
):
    if value is None:
        return None

    value = str(value).strip()

    return value or None


def _new_session():
    #
    # Lazy import keeps offline parser/smoke
    # usable on the CT108 host even when
    # curl_cffi exists only in the image.
    #
    from curl_cffi import (
        requests as cffi_requests,
    )

    return cffi_requests.Session()


def _validate_proxy_url(
    value: Any,
) -> str:
    value = _text(value)

    if not value:
        raise ValueError(
            "Discovery VPN proxy is required"
        )

    parsed = urlparse(
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
        raise ValueError(
            "invalid Discovery VPN proxy"
        )

    return value


def vpn_proxy_url() -> str:
    return _validate_proxy_url(
        teddy_routing.proxy_for_mode(
            "vpn"
        )
    )


def _validate_release_page_url(
    value: Any,
    *,
    language: str = DEFAULT_LANGUAGE,
    expected_host: str | None = None,
) -> str:
    value = _text(value)

    if not value:
        raise ValueError(
            "missing MissAV release URL"
        )

    parsed = urlparse(
        value
    )

    if (
        parsed.scheme != "https"
        or not parsed.hostname
    ):
        raise ValueError(
            "MissAV release URL "
            "must be HTTPS"
        )

    if (
        expected_host is not None
        and parsed.hostname
        != expected_host
    ):
        raise ValueError(
            "MissAV release URL "
            "changed host"
        )

    segments = [
        unquote(segment)
        for segment
        in parsed.path.split("/")
        if segment
    ]

    if (
        len(segments) < 2
        or segments[-2:]
        != [
            language,
            "release",
        ]
    ):
        raise ValueError(
            "MissAV release URL "
            "escaped release route"
        )

    query = parse_qs(
        parsed.query,
        keep_blank_values=True,
    )

    unknown = (
        set(query)
        - {
            "page",
        }
    )

    if unknown:
        raise ValueError(
            "unexpected MissAV release "
            "query keys: "
            + repr(
                sorted(unknown)
            )
        )

    if "page" in query:
        values = query[
            "page"
        ]

        if (
            len(values) != 1
            or not values[0].isdigit()
            or int(values[0]) < 2
        ):
            raise ValueError(
                "invalid MissAV "
                "release page number"
            )

    return value


def _page_number(
    url: str,
) -> int:
    parsed = urlparse(
        url
    )

    query = parse_qs(
        parsed.query
    )

    values = query.get(
        "page"
    )

    if not values:
        return 1

    if (
        len(values) != 1
        or not values[0].isdigit()
    ):
        raise ValueError(
            "invalid release page query"
        )

    return int(
        values[0]
    )


def _fetch_release_envelope(
    session,
    url: str,
    *,
    proxy_url: str,
    timeout: int,
    impersonate: str,
    language: str,
) -> dict:
    requested_url = (
        _validate_release_page_url(
            url,
            language=language,
        )
    )

    requested_host = (
        urlparse(
            requested_url
        ).hostname
    )

    requested_at = (
        utc_now()
    )

    response = session.get(
        requested_url,

        proxies={
            "http":
                proxy_url,

            "https":
                proxy_url,
        },

        impersonate=
            impersonate,

        allow_redirects=True,

        timeout=timeout,

        headers={
            "Accept":
                "text/html,"
                "application/xhtml+xml",

            "Accept-Language":
                "ko-KR,ko;q=0.9,"
                "en;q=0.5",
        },
    )

    status = int(
        response.status_code
    )

    final_url = (
        _validate_release_page_url(
            str(
                response.url
            ),
            language=language,
            expected_host=
                requested_host,
        )
    )

    if status != 200:
        raise RuntimeError(
            "MissAV release HTTP "
            f"{status}"
        )

    headers = {
        str(key).lower():
            str(value)

        for key, value
        in (
            getattr(
                response,
                "headers",
                {},
            )
            or {}
        ).items()
    }

    content_type = (
        headers.get(
            "content-type",
            ""
        ).lower()
    )

    if (
        content_type
        and "text/html"
        not in content_type
    ):
        raise RuntimeError(
            "MissAV release response "
            "is not HTML"
        )

    body = str(
        response.text
    )

    if not body.strip():
        raise RuntimeError(
            "MissAV release "
            "returned empty HTML"
        )

    history = (
        getattr(
            response,
            "history",
            [],
        )
        or []
    )

    return {
        "requested_at":
            requested_at,

        "requested_url":
            requested_url,

        "status":
            status,

        "final_url":
            final_url,

        "redirect_count":
            len(history),

        "response_headers":
            headers,

        "body":
            body,
    }


def collect_release_pages(
    *,
    session=None,
    proxy_url: str | None = None,
    start_url: str = DEFAULT_RELEASE_URL,
    limit: int = DEFAULT_LIMIT,
    max_pages: int = DEFAULT_MAX_PAGES,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    impersonate: str = DEFAULT_IMPERSONATE,
    language: str = DEFAULT_LANGUAGE,
) -> dict:
    if (
        not isinstance(
            limit,
            int,
        )
        or limit < 1
        or limit > 500
    ):
        raise ValueError(
            "release limit must "
            "be 1..500"
        )

    if (
        not isinstance(
            max_pages,
            int,
        )
        or max_pages < 1
        or max_pages > 20
    ):
        raise ValueError(
            "max_pages must be 1..20"
        )

    if (
        not isinstance(
            timeout,
            int,
        )
        or timeout < 1
        or timeout > 120
    ):
        raise ValueError(
            "timeout must be 1..120"
        )

    proxy_url = (
        _validate_proxy_url(
            proxy_url
        )
        if proxy_url is not None
        else vpn_proxy_url()
    )

    current_url = (
        _validate_release_page_url(
            start_url,
            language=language,
        )
    )

    initial_host = (
        urlparse(
            current_url
        ).hostname
    )

    own_session = (
        session is None
    )

    if own_session:
        session = _new_session()

    envelopes = []
    seen_urls = set()
    seen_ids = set()

    try:
        for page_number in range(
            1,
            max_pages + 1,
        ):
            if current_url in seen_urls:
                raise RuntimeError(
                    "MissAV pagination loop"
                )

            seen_urls.add(
                current_url
            )

            envelope = (
                _fetch_release_envelope(
                    session,
                    current_url,
                    proxy_url=
                        proxy_url,
                    timeout=
                        timeout,
                    impersonate=
                        impersonate,
                    language=
                        language,
                )
            )

            if (
                urlparse(
                    envelope[
                        "final_url"
                    ]
                ).hostname
                != initial_host
            ):
                raise RuntimeError(
                    "MissAV release "
                    "redirected off host"
                )

            page_items = (
                parse_missav_release_envelope(
                    envelope,
                    language=language,
                )
            )

            if not page_items:
                raise RuntimeError(
                    "empty MissAV "
                    f"release page "
                    f"{page_number}"
                )

            envelopes.append(
                envelope
            )

            for item in page_items:
                seen_ids.add(
                    item[
                        "dvd_id"
                    ]
                )

            if len(
                seen_ids
            ) >= limit:
                break

            next_url = (
                missav_release_next_url_from_envelope(
                    envelope,
                    language=language,
                )
            )

            if not next_url:
                raise RuntimeError(
                    "MissAV release "
                    "ended before limit"
                )

            next_url = (
                _validate_release_page_url(
                    next_url,
                    language=language,
                    expected_host=
                        initial_host,
                )
            )

            expected_page = (
                page_number + 1
            )

            actual_page = (
                _page_number(
                    next_url
                )
            )

            if (
                actual_page
                != expected_page
            ):
                raise RuntimeError(
                    "MissAV pagination "
                    "is not sequential: "
                    f"expected "
                    f"{expected_page}, "
                    f"got {actual_page}"
                )

            current_url = (
                next_url
            )

        items = (
            merge_missav_release_envelopes(
                envelopes,
                limit=limit,
                language=language,
            )
        )

        if len(items) != limit:
            raise RuntimeError(
                "MissAV release merge "
                "did not reach limit"
            )

        return {
            "source":
                MISSAV_RELEASE_SOURCE,

            "proxy_url":
                proxy_url,

            "observed_at":
                envelopes[0][
                    "requested_at"
                ],

            "page_count":
                len(envelopes),

            "item_count":
                len(items),

            "page_urls": [
                envelope[
                    "final_url"
                ]
                for envelope
                in envelopes
            ],

            "envelopes":
                envelopes,

            "items":
                items,
        }

    finally:
        if own_session:
            try:
                session.close()
            except Exception:
                pass


def run_release_collection(
    db_path: str | Path,
    *,
    session=None,
    proxy_url: str | None = None,
    start_url: str = DEFAULT_RELEASE_URL,
    limit: int = DEFAULT_LIMIT,
    max_pages: int = DEFAULT_MAX_PAGES,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    impersonate: str = DEFAULT_IMPERSONATE,
    language: str = DEFAULT_LANGUAGE,
) -> dict:
    #
    # Critical fail-closed boundary:
    #
    # Network + all pages + parser + 50-item
    # merge must finish BEFORE opening the DB.
    #
    collected = (
        collect_release_pages(
            session=session,
            proxy_url=proxy_url,
            start_url=start_url,
            limit=limit,
            max_pages=max_pages,
            timeout=timeout,
            impersonate=
                impersonate,
            language=language,
        )
    )

    connection = connect(
        db_path
    )

    try:
        initialize(
            connection
        )

        written = upsert_latest_items(
            connection,
            collected[
                "items"
            ],
            source=
                MISSAV_RELEASE_SOURCE,
            observed_at=
                collected[
                    "observed_at"
                ],
        )

        if (
            written
            != collected[
                "item_count"
            ]
        ):
            raise RuntimeError(
                "latest DB write "
                "count mismatch"
            )

        integrity = (
            connection.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )

        if integrity != "ok":
            raise RuntimeError(
                "Discovery DB "
                "integrity failed"
            )

        result = dict(
            collected
        )

        result.pop(
            "envelopes",
            None,
        )

        result["written"] = (
            written
        )

        result["db_integrity"] = (
            integrity
        )

        return result

    finally:
        connection.close()
