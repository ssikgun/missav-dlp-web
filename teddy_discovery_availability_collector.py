from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import teddy_routing

from teddy_discovery_availability import (
    AVAILABILITY_SOURCES,
    canonical_dvd_id,
    canonical_page_url,
    classify_page_response,
)


DEFAULT_TIMEOUT_SECONDS = 45
DEFAULT_IMPERSONATE = "chrome"


def _text(
    value: Any,
) -> str | None:
    if value is None:
        return None

    value = str(
        value
    ).strip()

    return value or None


def _validated_source(
    value: Any,
) -> str:
    source = _text(
        value
    )

    if source not in (
        AVAILABILITY_SOURCES
    ):
        raise ValueError(
            "unsupported availability source"
        )

    return source


def _validated_timeout(
    value: Any,
) -> int:
    if (
        type(value) is not int
        or value < 1
        or value > 120
    ):
        raise ValueError(
            "availability timeout "
            "must be 1..120 seconds"
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
            "availability impersonate "
            "value missing"
        )

    return value


def _new_session():
    #
    # Keep curl_cffi lazy so all offline
    # smoke tests remain runnable directly
    # on CT108 without making a request.
    #
    from curl_cffi import (
        requests as cffi_requests,
    )

    return cffi_requests.Session()


def vpn_proxy_url() -> str:
    #
    # Discovery availability is intentionally
    # fixed to Teddy's VPN route.
    #
    # There is no auto/direct/public-proxy
    # fallback in this collector.
    #
    value = _text(
        teddy_routing.proxy_for_mode(
            "vpn"
        )
    )

    if not value:
        raise RuntimeError(
            "availability VPN proxy "
            "is unavailable"
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
        raise RuntimeError(
            "availability VPN proxy "
            "is invalid"
        )

    return value


def collect_availability_page(
    *,
    source: Any,
    dvd_id: Any,
    session=None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    impersonate: str = DEFAULT_IMPERSONATE,
) -> dict:
    source = _validated_source(
        source
    )

    dvd_id = canonical_dvd_id(
        dvd_id
    )

    timeout = _validated_timeout(
        timeout
    )

    impersonate = (
        _validated_impersonate(
            impersonate
        )
    )

    requested_url = canonical_page_url(
        source,
        dvd_id,
    )

    #
    # Resolve VPN before constructing an owned
    # network session. If VPN is unavailable,
    # fail before any external request.
    #
    proxy_url = vpn_proxy_url()

    owned_session = (
        session is None
    )

    if owned_session:
        session = _new_session()

    request_attempts = 0

    try:
        request_attempts += 1

        try:
            response = session.get(
                requested_url,

                proxies={
                    "http":
                        proxy_url,

                    "https":
                        proxy_url,
                },

                timeout=timeout,

                impersonate=
                    impersonate,

                allow_redirects=False,

                headers={
                    "Accept":
                        "text/html,"
                        "application/xhtml+xml",

                    "Accept-Language":
                        "ko-KR,ko;q=0.9,"
                        "en;q=0.5",
                },
            )

        except Exception as exc:
            error = (
                type(exc).__name__
                + ": "
                + str(exc)
            )

            classification = (
                classify_page_response(
                    source=source,
                    dvd_id=dvd_id,
                    requested_url=
                        requested_url,
                    http_status=None,
                    content_type=None,
                    effective_url=None,
                    location=None,
                    error=error,
                    body=None,
                )
            )

            return {
                "source":
                    source,

                "dvd_id":
                    dvd_id,

                "page_url":
                    requested_url,

                "route":
                    "fixed-vpn",

                "request_attempts":
                    request_attempts,

                "redirects_followed":
                    0,

                "media_requests":
                    0,

                "http_status":
                    None,

                "content_type":
                    None,

                "effective_url":
                    None,

                "location":
                    None,

                "error":
                    error,

                "body_bytes":
                    0,

                "classification":
                    classification,
            }

        status = int(
            response.status_code
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

        content_type = headers.get(
            "content-type"
        )

        location = headers.get(
            "location"
        )

        effective_url = _text(
            getattr(
                response,
                "url",
                None,
            )
        )

        body = str(
            getattr(
                response,
                "text",
                "",
            )
        )

        classification = (
            classify_page_response(
                source=source,
                dvd_id=dvd_id,
                requested_url=
                    requested_url,
                http_status=status,
                content_type=
                    content_type,
                effective_url=
                    effective_url,
                location=location,
                error=None,
                body=body,
            )
        )

        return {
            "source":
                source,

            "dvd_id":
                dvd_id,

            "page_url":
                requested_url,

            "route":
                "fixed-vpn",

            "request_attempts":
                request_attempts,

            #
            # Redirect following is forbidden.
            # A Location response becomes
            # UNKNOWN in the classifier.
            #
            "redirects_followed":
                0,

            "media_requests":
                0,

            "http_status":
                status,

            "content_type":
                content_type,

            "effective_url":
                effective_url,

            "location":
                location,

            "error":
                None,

            #
            # Raw HTML is deliberately not
            # returned/persisted by the
            # collector.
            #
            "body_bytes":
                len(
                    body.encode(
                        "utf-8",
                        errors="replace",
                    )
                ),

            "classification":
                classification,
        }

    finally:
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
