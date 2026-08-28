from __future__ import annotations

from datetime import (
    datetime,
    timezone,
)
from pathlib import Path
from typing import Any
from urllib.parse import (
    unquote,
    urlparse,
    urlunparse,
)

from teddy_discovery_db import (
    connect,
    initialize,
)

from teddy_discovery_ids import (
    parse_dvd_id,
)

from teddy_discovery_variant_classifier import (
    PREFERRED_MISSAV_HOST,
    SOURCE_MISSAV,
    is_owned_uncensored_missav_url,
    preferred_owned_uncensored_missav_variant,
)

from teddy_discovery_variants import (
    VARIANT_UNCENSORED,
    canonical_variant_dvd_id,
    persist_title_variant,
)

from teddy_routing import (
    canonical_site,
)


DEFAULT_TIMEOUT_SECONDS = 45
DEFAULT_IMPERSONATE = "chrome"


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )


def _text(
    value: Any,
) -> str | None:
    if value is None:
        return None

    value = str(
        value
    ).strip()

    return value or None


def canonical_standard_missav_url(
    dvd_id: Any,
) -> str:
    dvd_id = canonical_variant_dvd_id(
        dvd_id
    )

    return (
        "https://"
        + PREFERRED_MISSAV_HOST
        + "/ko/"
        + dvd_id.lower()
    )


def _new_session():
    from curl_cffi import (
        requests as cffi_requests,
    )

    return cffi_requests.Session()


def _clean_response_url(
    value: Any,
    *,
    dvd_id: str,
) -> str:
    value = _text(
        value
    )

    if not value:
        raise RuntimeError(
            "MissAV response URL missing"
        )

    parsed = urlparse(
        value
    )

    if (
        parsed.scheme.lower()
        not in {
            "http",
            "https",
        }
        or not parsed.hostname
    ):
        raise RuntimeError(
            "MissAV response URL invalid"
        )

    cleaned = urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc,
            parsed.path,
            "",
            "",
            "",
        )
    )

    if canonical_site(
        cleaned
    ) != SOURCE_MISSAV:
        raise RuntimeError(
            "MissAV response escaped "
            "MissAV family"
        )

    parsed_id = parse_dvd_id(
        cleaned
    )

    if (
        parsed_id is None
        or parsed_id.dvd_id
        != dvd_id
    ):
        raise RuntimeError(
            "MissAV response DVD ID mismatch"
        )

    return cleaned


def _variant_from_final_url(
    *,
    dvd_id: str,
    final_url: str,
) -> dict | None:
    if not is_owned_uncensored_missav_url(
        dvd_id=dvd_id,
        page_url=final_url,
    ):
        return None

    path_parts = [
        part
        for part
        in urlparse(
            final_url
        ).path.split("/")
        if part
    ]

    if not path_parts:
        raise RuntimeError(
            "variant redirect slug missing"
        )

    slug = unquote(
        path_parts[-1]
    ).strip()

    if not slug:
        raise RuntimeError(
            "variant redirect slug empty"
        )

    return {
        "dvd_id":
            dvd_id,

        "source":
            SOURCE_MISSAV,

        "variant_kind":
            VARIANT_UNCENSORED,

        "variant_slug":
            slug,

        "page_url":
            final_url,

        "confirmed":
            1,
    }


def collect_uncensored_missav_variant(
    dvd_id: Any,
    *,
    session=None,
    proxy_url: Any = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    impersonate: str = DEFAULT_IMPERSONATE,
) -> dict:
    dvd_id = canonical_variant_dvd_id(
        dvd_id
    )

    if (
        type(timeout) is not int
        or timeout < 1
        or timeout > 120
    ):
        raise ValueError(
            "timeout must be 1..120"
        )

    start_url = (
        canonical_standard_missav_url(
            dvd_id
        )
    )

    requested_at = utc_now()

    own_session = (
        session is None
    )

    if own_session:
        session = _new_session()

    request_kwargs = {
        "impersonate":
            impersonate,

        "timeout":
            timeout,

        "allow_redirects":
            True,

        "headers": {
            "Accept":
                (
                    "text/html,"
                    "application/xhtml+xml"
                ),

            "Accept-Language":
                "ko-KR,ko;q=0.9,en;q=0.5",
        },
    }

    proxy_url = _text(
        proxy_url
    )

    if proxy_url:
        request_kwargs[
            "proxies"
        ] = {
            "http":
                proxy_url,

            "https":
                proxy_url,
        }

    try:
        response = session.get(
            start_url,
            **request_kwargs,
        )

        status = int(
            response.status_code
        )

        final_url = (
            _clean_response_url(
                response.url,
                dvd_id=dvd_id,
            )
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
            ).casefold()
        )

        if status == 404:
            return {
                "dvd_id":
                    dvd_id,

                "requested_at":
                    requested_at,

                "requested_url":
                    start_url,

                "final_url":
                    final_url,

                "http_status":
                    404,

                "found":
                    False,

                "method":
                    None,

                "variant":
                    None,
            }

        if status != 200:
            raise RuntimeError(
                "MissAV title HTTP "
                + str(
                    status
                )
            )

        if (
            content_type
            and "text/html"
            not in content_type
        ):
            raise RuntimeError(
                "MissAV title response "
                "is not HTML"
            )

        body = getattr(
            response,
            "text",
            None,
        )

        if (
            not isinstance(
                body,
                str,
            )
            or not body.strip()
        ):
            raise RuntimeError(
                "MissAV title HTML missing"
            )

        variant = (
            _variant_from_final_url(
                dvd_id=dvd_id,
                final_url=final_url,
            )
        )

        method = None

        if variant is not None:
            method = "redirect-target"

        else:
            variant = (
                preferred_owned_uncensored_missav_variant(
                    body,
                    dvd_id=dvd_id,
                    page_url=final_url,
                )
            )

            if variant is not None:
                method = "page-link"

        return {
            "dvd_id":
                dvd_id,

            "requested_at":
                requested_at,

            "requested_url":
                start_url,

            "final_url":
                final_url,

            "http_status":
                status,

            "found":
                variant is not None,

            "method":
                method,

            "variant":
                variant,
        }

    finally:
        if own_session:
            try:
                session.close()

            except Exception:
                pass


def persist_variant_collection(
    connection,
    collected: Any,
) -> dict | None:
    if not isinstance(
        collected,
        dict,
    ):
        raise ValueError(
            "variant collection "
            "must be an object"
        )

    found = collected.get(
        "found"
    )

    if type(found) is not bool:
        raise ValueError(
            "variant collection "
            "found flag invalid"
        )

    if not found:
        if collected.get(
            "variant"
        ) is not None:
            raise ValueError(
                "not-found collection "
                "contains variant"
            )

        return None

    variant = collected.get(
        "variant"
    )

    if not isinstance(
        variant,
        dict,
    ):
        raise ValueError(
            "found collection "
            "variant missing"
        )

    observed_at = _text(
        collected.get(
            "requested_at"
        )
    )

    if not observed_at:
        raise ValueError(
            "collection timestamp missing"
        )

    return persist_title_variant(
        connection,
        variant,
        observed_at=observed_at,
        checked_at=observed_at,
    )


def run_variant_collection(
    db_path: str | Path,
    dvd_id: Any,
    *,
    session=None,
    proxy_url: Any = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    impersonate: str = DEFAULT_IMPERSONATE,
) -> dict:
    #
    # Read the external page first.
    #
    # DB is opened only after the network
    # result has been fully validated.
    #
    collected = (
        collect_uncensored_missav_variant(
            dvd_id,
            session=session,
            proxy_url=proxy_url,
            timeout=timeout,
            impersonate=impersonate,
        )
    )

    connection = connect(
        db_path
    )

    try:
        initialize(
            connection
        )

        stored = persist_variant_collection(
            connection,
            collected,
        )

        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        if integrity != "ok":
            raise RuntimeError(
                "Discovery DB "
                "integrity failed"
            )

        result = dict(
            collected
        )

        result["stored"] = (
            stored is not None
        )

        result["stored_variant"] = (
            stored
        )

        result["db_integrity"] = (
            integrity
        )

        return result

    finally:
        connection.close()
