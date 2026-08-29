from __future__ import annotations

from html.parser import HTMLParser
from typing import Any

from teddy_discovery_ids import (
    parse_dvd_id,
)


SOURCE_MISSAV = "missav"
SOURCE_123AV = "123av"

AVAILABILITY_SOURCES = (
    SOURCE_MISSAV,
    SOURCE_123AV,
)

STATUS_FOUND = "FOUND"
STATUS_NOT_FOUND = "NOT_FOUND"
STATUS_UNKNOWN = "UNKNOWN"

AVAILABILITY_STATUSES = (
    STATUS_FOUND,
    STATUS_NOT_FOUND,
    STATUS_UNKNOWN,
)


def _text(
    value: Any,
) -> str | None:
    if value is None:
        return None

    value = " ".join(
        str(value).split()
    )

    return value or None


def canonical_dvd_id(
    value: Any,
) -> str:
    raw = _text(
        value
    )

    if not raw:
        raise ValueError(
            "DVD ID missing"
        )

    parsed = parse_dvd_id(
        raw
    )

    if parsed is None:
        raise ValueError(
            "invalid DVD ID"
        )

    canonical = (
        parsed.dvd_id
    )

    #
    # Availability receives canonical IDs,
    # not filenames or arbitrary title text.
    #
    # Case differences are accepted for
    # callers such as UI/search input, but
    # trailing prose, filenames, suffixes,
    # etc. must fail closed.
    #
    if (
        raw.casefold()
        != canonical.casefold()
    ):
        raise ValueError(
            "availability requires "
            "a canonical DVD ID"
        )

    return canonical


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


def canonical_page_url(
    source: Any,
    dvd_id: Any,
) -> str:
    source = _validated_source(
        source
    )

    dvd_id = canonical_dvd_id(
        dvd_id
    )

    slug = dvd_id.lower()

    if source == SOURCE_MISSAV:
        return (
            "https://missav123.com/ko/"
            + slug
        )

    if source == SOURCE_123AV:
        return (
            "https://123av.com/ko/v/"
            + slug
        )

    raise RuntimeError(
        "unreachable availability source"
    )


class _IdentityParser(
    HTMLParser
):
    def __init__(
        self,
    ):
        super().__init__(
            convert_charrefs=True
        )

        self._in_title = False
        self._h1_depth = 0

        self._title_parts = []
        self._h1_parts = []

    def handle_starttag(
        self,
        tag,
        attrs,
    ):
        tag = tag.lower()

        if tag == "title":
            self._in_title = True

        if tag == "h1":
            self._h1_depth += 1

    def handle_endtag(
        self,
        tag,
    ):
        tag = tag.lower()

        if tag == "title":
            self._in_title = False

        if (
            tag == "h1"
            and self._h1_depth > 0
        ):
            self._h1_depth -= 1

    def handle_data(
        self,
        data,
    ):
        value = _text(
            data
        )

        if not value:
            return

        if self._in_title:
            self._title_parts.append(
                value
            )

        if self._h1_depth:
            self._h1_parts.append(
                value
            )

    def result(
        self,
    ) -> dict:
        return {
            "title":
                " ".join(
                    self._title_parts
                ),

            "h1":
                " ".join(
                    self._h1_parts
                ),
        }


def extract_page_identity(
    html: Any,
) -> dict:
    if not isinstance(
        html,
        str,
    ):
        raise ValueError(
            "availability HTML must be text"
        )

    parser = _IdentityParser()

    try:
        parser.feed(
            html
        )

        parser.close()

    except Exception:
        return {
            "title":
                "",

            "h1":
                "",
        }

    return parser.result()


def _unknown_result(
    *,
    source: str,
    dvd_id: str,
    page_url: str,
    reason: str,
    http_status: int | None,
    title: str = "",
    h1: str = "",
) -> dict:
    return {
        "source":
            source,

        "dvd_id":
            dvd_id,

        "page_url":
            page_url,

        "status":
            STATUS_UNKNOWN,

        "reason":
            reason,

        "http_status":
            http_status,

        "title":
            title,

        "h1":
            h1,
    }


def classify_page_response(
    *,
    source: Any,
    dvd_id: Any,
    requested_url: Any,
    http_status: Any,
    content_type: Any,
    effective_url: Any,
    location: Any = None,
    error: Any = None,
    body: Any = None,
) -> dict:
    source = _validated_source(
        source
    )

    dvd_id = canonical_dvd_id(
        dvd_id
    )

    expected_url = canonical_page_url(
        source,
        dvd_id,
    )

    requested_url = _text(
        requested_url
    )

    if requested_url != expected_url:
        raise ValueError(
            "availability request escaped "
            "canonical page URL"
        )

    error = _text(
        error
    )

    if error:
        return _unknown_result(
            source=source,
            dvd_id=dvd_id,
            page_url=expected_url,
            reason="request-error",
            http_status=None,
        )

    if (
        type(http_status)
        is not int
    ):
        return _unknown_result(
            source=source,
            dvd_id=dvd_id,
            page_url=expected_url,
            reason="invalid-http-status",
            http_status=None,
        )

    location = _text(
        location
    )

    if location:
        return _unknown_result(
            source=source,
            dvd_id=dvd_id,
            page_url=expected_url,
            reason="redirect-location",
            http_status=http_status,
        )

    effective_url = _text(
        effective_url
    )

    if effective_url != expected_url:
        return _unknown_result(
            source=source,
            dvd_id=dvd_id,
            page_url=expected_url,
            reason="effective-url-mismatch",
            http_status=http_status,
        )

    content_type = (
        _text(
            content_type
        )
        or ""
    ).casefold()

    if "text/html" not in content_type:
        return _unknown_result(
            source=source,
            dvd_id=dvd_id,
            page_url=expected_url,
            reason="non-html",
            http_status=http_status,
        )

    if http_status == 404:
        return {
            "source":
                source,

            "dvd_id":
                dvd_id,

            "page_url":
                expected_url,

            "status":
                STATUS_NOT_FOUND,

            "reason":
                "http-404",

            "http_status":
                404,

            "title":
                "",

            "h1":
                "",
        }

    if http_status != 200:
        return _unknown_result(
            source=source,
            dvd_id=dvd_id,
            page_url=expected_url,
            reason=(
                "http-"
                + str(
                    http_status
                )
            ),
            http_status=http_status,
        )

    if not isinstance(
        body,
        str,
    ):
        return _unknown_result(
            source=source,
            dvd_id=dvd_id,
            page_url=expected_url,
            reason="missing-html-body",
            http_status=200,
        )

    identity = extract_page_identity(
        body
    )

    title = identity[
        "title"
    ]

    h1 = identity[
        "h1"
    ]

    token = dvd_id.casefold()

    title_match = (
        token
        in title.casefold()
    )

    h1_match = (
        token
        in h1.casefold()
    )

    #
    # FOUND requires explicit page identity.
    #
    # Either document title or the page H1 is
    # sufficient. Arbitrary body hits are not
    # used because MissAV's real 404 page was
    # proven to echo the requested DVD ID.
    #
    if (
        title_match
        or h1_match
    ):
        return {
            "source":
                source,

            "dvd_id":
                dvd_id,

            "page_url":
                expected_url,

            "status":
                STATUS_FOUND,

            "reason":
                "page-identity-match",

            "http_status":
                200,

            "title":
                title,

            "h1":
                h1,
        }

    return _unknown_result(
        source=source,
        dvd_id=dvd_id,
        page_url=expected_url,
        reason="page-identity-mismatch",
        http_status=200,
        title=title,
        h1=h1,
    )
