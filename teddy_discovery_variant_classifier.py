from __future__ import annotations

from html.parser import HTMLParser
import re
from typing import Any
from urllib.parse import (
    unquote,
    urljoin,
    urlparse,
    urlunparse,
)

from teddy_discovery_ids import (
    parse_dvd_id,
)

from teddy_discovery_variants import (
    VARIANT_UNCENSORED,
)

from teddy_routing import (
    canonical_site,
)


SOURCE_MISSAV = "missav"

PREFERRED_MISSAV_HOST = (
    "missav123.com"
)

UNCENSORED_TOKEN_RE = re.compile(
    r"(?<![a-z0-9])"
    r"uncensored"
    r"(?![a-z0-9])",
    flags=re.I,
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


def _canonical_dvd_id(
    value: Any,
) -> str:
    value = _text(
        value
    )

    if not value:
        raise ValueError(
            "DVD ID missing"
        )

    parsed = parse_dvd_id(
        value
    )

    if parsed is None:
        raise ValueError(
            "invalid DVD ID"
        )

    return parsed.dvd_id


def _clean_http_url(
    value: Any,
) -> str | None:
    value = _text(
        value
    )

    if not value:
        return None

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
        return None

    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc,
            parsed.path,
            "",
            "",
            "",
        )
    )


def _variant_slug(
    page_url: str,
) -> str | None:
    parsed = urlparse(
        page_url
    )

    segments = [
        segment
        for segment
        in parsed.path.split("/")
        if segment
    ]

    if not segments:
        return None

    slug = unquote(
        segments[-1]
    ).strip()

    if (
        not slug
        or "/" in slug
    ):
        return None

    return slug


def _slug_owned_by_dvd_id(
    slug: str,
    dvd_id: str,
) -> bool:
    parsed = parse_dvd_id(
        slug
    )

    if (
        parsed is None
        or parsed.dvd_id != dvd_id
    ):
        return False

    prefix = re.compile(
        r"^"
        + re.escape(
            dvd_id
        )
        + r"(?:$|[-_.])",
        flags=re.I,
    )

    return bool(
        prefix.search(
            slug
        )
    )


def has_uncensored_token(
    value: Any,
) -> bool:
    value = _text(
        value
    )

    if not value:
        return False

    return bool(
        UNCENSORED_TOKEN_RE.search(
            value
        )
    )


def is_owned_uncensored_missav_url(
    *,
    dvd_id: Any,
    page_url: Any,
) -> bool:
    try:
        dvd_id = (
            _canonical_dvd_id(
                dvd_id
            )
        )

    except ValueError:
        return False

    page_url = _clean_http_url(
        page_url
    )

    if not page_url:
        return False

    if canonical_site(
        page_url
    ) != SOURCE_MISSAV:
        return False

    slug = _variant_slug(
        page_url
    )

    if not slug:
        return False

    if not _slug_owned_by_dvd_id(
        slug,
        dvd_id,
    ):
        return False

    if not has_uncensored_token(
        slug
    ):
        return False

    return True


class _HrefCollector(
    HTMLParser,
):
    def __init__(
        self,
    ):
        super().__init__(
            convert_charrefs=True
        )

        self.hrefs: list[str] = []

    def handle_starttag(
        self,
        tag,
        attrs,
    ):
        for key, value in attrs:
            if (
                str(
                    key
                ).lower()
                != "href"
            ):
                continue

            value = _text(
                value
            )

            if value:
                self.hrefs.append(
                    value
                )


def _validate_context_page(
    *,
    dvd_id: str,
    page_url: Any,
) -> str:
    page_url = _clean_http_url(
        page_url
    )

    if not page_url:
        raise ValueError(
            "MissAV context page URL invalid"
        )

    if canonical_site(
        page_url
    ) != SOURCE_MISSAV:
        raise ValueError(
            "context page is outside "
            "MissAV family"
        )

    parsed = parse_dvd_id(
        page_url
    )

    if (
        parsed is None
        or parsed.dvd_id
        != dvd_id
    ):
        raise ValueError(
            "context page DVD ID mismatch"
        )

    return page_url


def extract_owned_uncensored_missav_variants(
    html: Any,
    *,
    dvd_id: Any,
    page_url: Any,
) -> list[dict]:
    html = _text(
        html
    )

    if not html:
        raise ValueError(
            "MissAV HTML missing"
        )

    dvd_id = _canonical_dvd_id(
        dvd_id
    )

    page_url = _validate_context_page(
        dvd_id=dvd_id,
        page_url=page_url,
    )

    parser = _HrefCollector()

    parser.feed(
        html
    )

    parser.close()

    by_url: dict[str, dict] = {}

    for href in parser.hrefs:
        absolute = urljoin(
            page_url,
            href,
        )

        absolute = _clean_http_url(
            absolute
        )

        if not absolute:
            continue

        if not is_owned_uncensored_missav_url(
            dvd_id=dvd_id,
            page_url=absolute,
        ):
            continue

        slug = _variant_slug(
            absolute
        )

        if not slug:
            continue

        by_url[
            absolute
        ] = {
            "dvd_id":
                dvd_id,

            "source":
                SOURCE_MISSAV,

            "variant_kind":
                VARIANT_UNCENSORED,

            "variant_slug":
                slug,

            "page_url":
                absolute,

            "confirmed":
                1,
        }

    def preference_key(
        item: dict,
    ):
        host = (
            urlparse(
                item[
                    "page_url"
                ]
            ).hostname
            or ""
        ).lower().rstrip(".")

        if host.startswith(
            "www."
        ):
            host = host[4:]

        preferred = (
            0
            if host
            == PREFERRED_MISSAV_HOST
            else 1
        )

        return (
            preferred,
            item[
                "page_url"
            ],
        )

    return sorted(
        by_url.values(),
        key=preference_key,
    )


def preferred_owned_uncensored_missav_variant(
    html: Any,
    *,
    dvd_id: Any,
    page_url: Any,
) -> dict | None:
    variants = (
        extract_owned_uncensored_missav_variants(
            html,
            dvd_id=dvd_id,
            page_url=page_url,
        )
    )

    if not variants:
        return None

    return dict(
        variants[0]
    )
