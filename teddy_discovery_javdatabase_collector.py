from __future__ import annotations

from collections import Counter
from datetime import (
    date,
    datetime,
    timezone,
)
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import (
    unquote,
    urljoin,
    urlparse,
)

import teddy_routing

from teddy_discovery_db import (
    connect,
    initialize,
)

from teddy_discovery_javdatabase import (
    JAVDATABASE_HOSTS,
    JAVDATABASE_WEEKLY_SOURCE,
    WEEK_TITLE_RE,
    parse_javdatabase_weekly_envelope,
)

from teddy_discovery_rankings import (
    replace_weekly_snapshot,
)


DEFAULT_CATEGORY_URL = (
    "https://www.javdatabase.com/"
    "category/top-jav-movies/"
)

DEFAULT_TIMEOUT_SECONDS = 45
DEFAULT_IMPERSONATE = "chrome"


VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


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

    value = " ".join(
        str(value).split()
    )

    return value or None


def _new_session():
    #
    # Keep offline parser/smoke usable
    # when curl_cffi exists only in
    # the production image.
    #
    from curl_cffi import (
        requests as cffi_requests,
    )

    return cffi_requests.Session()


def _validate_proxy_url(
    value: Any,
) -> str:
    value = _text(
        value
    )

    if not value:
        raise ValueError(
            "JAV Database Discovery "
            "VPN proxy is required"
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
            "invalid JAV Database "
            "Discovery VPN proxy"
        )

    return value


def vpn_proxy_url() -> str:
    #
    # There is intentionally no route
    # argument and no fallback.
    #
    return _validate_proxy_url(
        teddy_routing.proxy_for_mode(
            "vpn"
        )
    )


def _validate_category_url(
    value: Any,
    *,
    expected_host: str | None = None,
) -> str:
    value = _text(
        value
    )

    if not value:
        raise ValueError(
            "missing JAV Database "
            "category URL"
        )

    parsed = urlparse(
        value
    )

    if (
        parsed.scheme != "https"
        or parsed.hostname
        not in JAVDATABASE_HOSTS
    ):
        raise ValueError(
            "invalid JAV Database "
            "category host"
        )

    if (
        expected_host is not None
        and parsed.hostname
        != expected_host
    ):
        raise ValueError(
            "JAV Database category "
            "changed host"
        )

    if (
        parsed.path
        != "/category/top-jav-movies/"
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "JAV Database category "
            "escaped expected route"
        )

    return value


def _article_publication_date(
    value: str,
) -> date:
    parsed = urlparse(
        value
    )

    segments = [
        unquote(segment)
        for segment
        in parsed.path.split("/")
        if segment
    ]

    if len(
        segments
    ) != 4:
        raise ValueError(
            "unexpected Weekly "
            "article path"
        )

    year_raw = segments[0]
    month_raw = segments[1]
    day_raw = segments[2]
    slug = segments[3]

    if (
        len(year_raw) != 4
        or len(month_raw) != 2
        or len(day_raw) != 2
        or not year_raw.isdigit()
        or not month_raw.isdigit()
        or not day_raw.isdigit()
        or not slug.startswith(
            "top-jav-movies-"
        )
    ):
        raise ValueError(
            "invalid Weekly article "
            "date/slug path"
        )

    try:
        return date(
            int(year_raw),
            int(month_raw),
            int(day_raw),
        )

    except ValueError as exc:
        raise ValueError(
            "invalid Weekly article "
            "publication date"
        ) from exc


def _validate_article_url(
    value: Any,
    *,
    expected_host: str,
) -> str:
    value = _text(
        value
    )

    if not value:
        raise ValueError(
            "missing Weekly article URL"
        )

    parsed = urlparse(
        value
    )

    if (
        parsed.scheme != "https"
        or parsed.hostname
        not in JAVDATABASE_HOSTS
        or parsed.hostname
        != expected_host
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "invalid Weekly article URL"
        )

    _article_publication_date(
        value
    )

    return value


class _CategoryAnchorParser(
    HTMLParser
):
    def __init__(self):
        super().__init__(
            convert_charrefs=True
        )

        self.depth = 0
        self.anchor = None
        self.anchors = []

    def handle_starttag(
        self,
        tag,
        attrs,
    ):
        current_depth = (
            self.depth
        )

        if tag == "a":
            if self.anchor is not None:
                raise ValueError(
                    "nested category anchor "
                    "changed"
                )

            attributes = {
                str(key):
                    value
                for key, value
                in attrs
            }

            self.anchor = {
                "href":
                    attributes.get(
                        "href"
                    ),

                "title":
                    attributes.get(
                        "title"
                    ),

                "text_parts":
                    [],

                "depth":
                    current_depth,
            }

        if tag not in VOID_TAGS:
            self.depth += 1

    def handle_data(
        self,
        data,
    ):
        if self.anchor is not None:
            self.anchor[
                "text_parts"
            ].append(
                data
            )

    def handle_endtag(
        self,
        tag,
    ):
        if tag not in VOID_TAGS:
            self.depth -= 1

        if (
            tag == "a"
            and self.anchor is not None
            and self.depth
            == self.anchor[
                "depth"
            ]
        ):
            value = dict(
                self.anchor
            )

            value.pop(
                "depth",
                None,
            )

            value[
                "text"
            ] = _text(
                "".join(
                    value.pop(
                        "text_parts"
                    )
                )
            )

            self.anchors.append(
                value
            )

            self.anchor = None


def parse_weekly_category_html(
    html: str,
    category_url: str,
) -> dict:
    if (
        not isinstance(
            html,
            str,
        )
        or not html.strip()
    ):
        raise ValueError(
            "JAV Database category "
            "HTML is empty"
        )

    category_url = (
        _validate_category_url(
            category_url
        )
    )

    category_host = urlparse(
        category_url
    ).hostname

    parser = (
        _CategoryAnchorParser()
    )

    parser.feed(
        html
    )

    raw = []

    for anchor_index, anchor in enumerate(
        parser.anchors,
        start=1,
    ):
        matched_title = None
        title_source = None

        for source_name, value in (
            (
                "anchor-text",
                _text(
                    anchor.get(
                        "text"
                    )
                ),
            ),
            (
                "title-attr",
                _text(
                    anchor.get(
                        "title"
                    )
                ),
            ),
        ):
            if (
                value
                and WEEK_TITLE_RE.fullmatch(
                    value
                )
            ):
                matched_title = value
                title_source = source_name
                break

        if matched_title is None:
            continue

        href = _text(
            anchor.get(
                "href"
            )
        )

        if not href:
            raise ValueError(
                "Weekly category candidate "
                "has no href"
            )

        absolute = urljoin(
            category_url,
            href,
        )

        absolute = (
            _validate_article_url(
                absolute,
                expected_host=
                    category_host,
            )
        )

        match = WEEK_TITLE_RE.fullmatch(
            matched_title
        )

        year = int(
            match.group(
                "year"
            )
        )

        week = int(
            match.group(
                "week"
            )
        )

        if (
            year < 2000
            or year > 2100
            or week < 1
            or week > 53
        ):
            raise ValueError(
                "invalid Weekly period "
                "on category page"
            )

        published = (
            _article_publication_date(
                absolute
            )
        )

        raw.append({
            "anchor_index":
                anchor_index,

            "title":
                matched_title,

            "title_source":
                title_source,

            "url":
                absolute,

            "year":
                year,

            "week":
                week,

            "period":
                f"{year}-W{week:02d}",

            "publication_date":
                published.isoformat(),
        })

    if not raw:
        raise ValueError(
            "no Weekly articles found "
            "on category page"
        )

    key_counts = Counter(
        (
            item[
                "url"
            ],
            item[
                "title"
            ],
        )
        for item
        in raw
    )

    candidates = []
    seen = set()

    for item in raw:
        key = (
            item[
                "url"
            ],
            item[
                "title"
            ],
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        value = dict(
            item
        )

        value[
            "anchor_occurrences"
        ] = key_counts[
            key
        ]

        candidates.append(
            value
        )

    period_map = {}

    for item in candidates:
        period = item[
            "period"
        ]

        if period in period_map:
            raise ValueError(
                "duplicate Weekly period "
                "on category page: "
                + period
            )

        period_map[
            period
        ] = item

    #
    # The chart period itself is the
    # semantic identity of "latest".
    #
    # Publication date is validated and
    # retained as provenance, but is not
    # allowed to make an older corrected
    # article outrank a newer chart week.
    #
    selected = max(
        candidates,
        key=lambda item: (
            item[
                "year"
            ],
            item[
                "week"
            ],
        ),
    )

    return {
        "source":
            JAVDATABASE_WEEKLY_SOURCE,

        "category_url":
            category_url,

        "candidate_count":
            len(candidates),

        "candidates":
            candidates,

        "selected":
            selected,
    }


def parse_weekly_category_envelope(
    envelope: dict,
) -> dict:
    if not isinstance(
        envelope,
        dict,
    ):
        raise ValueError(
            "category envelope "
            "must be object"
        )

    if envelope.get(
        "status"
    ) != 200:
        raise ValueError(
            "cannot parse category "
            "non-200 response"
        )

    body = envelope.get(
        "body"
    )

    if not isinstance(
        body,
        str,
    ):
        raise ValueError(
            "category envelope body "
            "must be text"
        )

    url = (
        envelope.get(
            "final_url"
        )
        or envelope.get(
            "requested_url"
        )
    )

    return (
        parse_weekly_category_html(
            body,
            url,
        )
    )


def _fetch_html_envelope(
    session,
    url: str,
    *,
    proxy_url: str,
    timeout: int,
    impersonate: str,
    kind: str,
) -> dict:
    if kind == "category":
        requested_url = (
            _validate_category_url(
                url
            )
        )

    elif kind == "article":
        requested_host = (
            urlparse(
                url
            ).hostname
        )

        requested_url = (
            _validate_article_url(
                url,
                expected_host=
                    requested_host,
            )
        )

    else:
        raise ValueError(
            "unknown JAV Database "
            "request kind"
        )

    requested_host = urlparse(
        requested_url
    ).hostname

    requested_at = utc_now()

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
                "en-US,en;q=0.9",
        },
    )

    status = int(
        response.status_code
    )

    response_url = str(
        response.url
    )

    if kind == "category":
        final_url = (
            _validate_category_url(
                response_url,
                expected_host=
                    requested_host,
            )
        )

    else:
        final_url = (
            _validate_article_url(
                response_url,
                expected_host=
                    requested_host,
            )
        )

        if final_url != requested_url:
            raise RuntimeError(
                "Weekly article redirected "
                "to a different article"
            )

    if status != 200:
        raise RuntimeError(
            "JAV Database "
            + kind
            + " HTTP "
            + str(status)
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
            "JAV Database "
            + kind
            + " response is not HTML"
        )

    body = str(
        response.text
    )

    if not body.strip():
        raise RuntimeError(
            "JAV Database "
            + kind
            + " returned empty HTML"
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


def collect_weekly_snapshot(
    *,
    session=None,
    category_url: str = (
        DEFAULT_CATEGORY_URL
    ),
    timeout: int = (
        DEFAULT_TIMEOUT_SECONDS
    ),
    impersonate: str = (
        DEFAULT_IMPERSONATE
    ),
) -> dict:
    if (
        type(timeout) is not int
        or timeout < 1
        or timeout > 120
    ):
        raise ValueError(
            "timeout must be 1..120"
        )

    category_url = (
        _validate_category_url(
            category_url
        )
    )

    proxy_url = (
        vpn_proxy_url()
    )

    own_session = (
        session is None
    )

    if own_session:
        session = (
            _new_session()
        )

    try:
        category = (
            _fetch_html_envelope(
                session,
                category_url,
                proxy_url=
                    proxy_url,
                timeout=
                    timeout,
                impersonate=
                    impersonate,
                kind="category",
            )
        )

        selection = (
            parse_weekly_category_envelope(
                category
            )
        )

        selected = selection[
            "selected"
        ]

        article = (
            _fetch_html_envelope(
                session,
                selected[
                    "url"
                ],
                proxy_url=
                    proxy_url,
                timeout=
                    timeout,
                impersonate=
                    impersonate,
                kind="article",
            )
        )

        snapshot = (
            parse_javdatabase_weekly_envelope(
                article
            )
        )

        if snapshot[
            "period"
        ] != selected[
            "period"
        ]:
            raise RuntimeError(
                "Weekly category/article "
                "period mismatch"
            )

        if snapshot[
            "article_title"
        ] != selected[
            "title"
        ]:
            raise RuntimeError(
                "Weekly category/article "
                "title mismatch"
            )

        if snapshot[
            "item_count"
        ] != 25:
            raise RuntimeError(
                "Weekly article did not "
                "contain exactly 25 items"
            )

        return {
            "source":
                JAVDATABASE_WEEKLY_SOURCE,

            "proxy_url":
                proxy_url,

            "observed_at":
                article[
                    "requested_at"
                ],

            "request_count":
                2,

            "category":
                category,

            "candidate_count":
                selection[
                    "candidate_count"
                ],

            "selected_article":
                selected,

            "article":
                article,

            "snapshot":
                snapshot,
        }

    finally:
        if (
            own_session
            and session is not None
            and hasattr(
                session,
                "close",
            )
        ):
            session.close()


def run_weekly_collection(
    db_path: str | Path,
    *,
    session=None,
    category_url: str = (
        DEFAULT_CATEGORY_URL
    ),
    timeout: int = (
        DEFAULT_TIMEOUT_SECONDS
    ),
    impersonate: str = (
        DEFAULT_IMPERSONATE
    ),
) -> dict:
    #
    # Network + category selection +
    # complete 25-card article parsing
    # all happen before DB open.
    #
    collection = (
        collect_weekly_snapshot(
            session=session,
            category_url=
                category_url,
            timeout=
                timeout,
            impersonate=
                impersonate,
        )
    )

    connection = connect(
        db_path
    )

    try:
        initialize(
            connection
        )

        write_result = (
            replace_weekly_snapshot(
                connection,
                collection[
                    "snapshot"
                ],
                observed_at=
                    collection[
                        "observed_at"
                    ],
            )
        )

        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

    finally:
        connection.close()

    if integrity != "ok":
        raise RuntimeError(
            "Weekly collection DB "
            "integrity failed"
        )

    return {
        "source":
            collection[
                "source"
            ],

        "period":
            collection[
                "snapshot"
            ][
                "period"
            ],

        "article_url":
            collection[
                "selected_article"
            ][
                "url"
            ],

        "candidate_count":
            collection[
                "candidate_count"
            ],

        "request_count":
            collection[
                "request_count"
            ],

        "written":
            write_result[
                "written"
            ],

        "metadata_updated":
            write_result[
                "metadata_updated"
            ],

        "metadata_preserved":
            write_result[
                "metadata_preserved"
            ],

        "observed_at":
            collection[
                "observed_at"
            ],

        "db_integrity":
            integrity,
    }
