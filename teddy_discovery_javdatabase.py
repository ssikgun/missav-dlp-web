from __future__ import annotations

from datetime import date
from html.parser import HTMLParser
import re
from typing import Any
from urllib.parse import (
    unquote,
    urljoin,
    urlparse,
)

from teddy_discovery_ids import (
    parse_dvd_id,
)


JAVDATABASE_WEEKLY_SOURCE = (
    "javdatabase-weekly"
)

JAVDATABASE_HOSTS = {
    "javdatabase.com",
    "www.javdatabase.com",
}

DEFAULT_EXPECTED_COUNT = 25


METHOD_VISITS = (
    "number of visits received to "
    "each movie in the prior seven days"
)

METHOD_WEIGHTING = (
    "weighted towards newer releases"
)


WEEK_TITLE_RE = re.compile(
    r"^Top JAV Movies"
    r"\s*[–—-]\s*"
    r"(?P<year>\d{4})"
    r"\s*[–—-]\s*"
    r"Week\s+"
    r"(?P<week>\d{1,2})"
    r"\s*"
    r"\((?P<range>.+)\)"
    r"\s*$",
    re.I,
)

RANK_PREFIX_RE = re.compile(
    r"^\s*(?P<rank>\d{1,3})"
    r"(?:\s|$)"
)

TITLE_RE = re.compile(
    r"^\s*Title\s*:\s*(.+?)\s*$",
    re.I,
)

RELEASE_DATE_RE = re.compile(
    r"^\s*Release Date\s*:\s*"
    r"(\d{4}-\d{2}-\d{2})"
    r"\s*$",
    re.I,
)


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


def _text(
    value: Any,
):
    if value is None:
        return None

    value = " ".join(
        str(value).split()
    )

    return value or None


def _classes(
    value: Any,
) -> set[str]:
    return {
        token
        for token
        in str(
            value
            or ""
        ).split()
        if token
    }


def _attrs(
    attrs,
):
    return {
        str(key):
            (
                None
                if value is None
                else str(value)
            )
        for key, value
        in attrs
    }


def _host_ok(
    value: str,
) -> bool:
    return (
        urlparse(
            value
        ).hostname
        in JAVDATABASE_HOSTS
    )


def _required_https_javdatabase_url(
    value: Any,
    label: str,
) -> str:
    value = _text(
        value
    )

    if not value:
        raise ValueError(
            f"missing {label}"
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
            f"invalid {label}"
        )

    return value


class _WeeklyArticleParser(
    HTMLParser
):
    def __init__(self):
        super().__init__(
            convert_charrefs=True
        )

        self.depth = 0

        self.page_text = []

        self.h1 = None
        self.h1_parts = None
        self.h1_depth = None

        self.card = None
        self.card_depth = None

        self.element = None
        self.element_depth = None

        self.anchor = None
        self.anchor_depth = None

        self.cards = []

    def handle_starttag(
        self,
        tag,
        attrs,
    ):
        attributes = _attrs(
            attrs
        )

        current_depth = (
            self.depth
        )

        if tag == "h1":
            if (
                self.h1 is not None
                or self.h1_parts
                is not None
            ):
                raise ValueError(
                    "multiple weekly h1 "
                    "elements changed"
                )

            self.h1_parts = []
            self.h1_depth = (
                current_depth
            )

        if (
            self.card is None
            and tag == "div"
            and "list-group-item"
            in _classes(
                attributes.get(
                    "class"
                )
            )
        ):
            self.card = {
                "root_class":
                    attributes.get(
                        "class"
                    ),

                "text_parts":
                    [],

                "elements":
                    [],

                "anchors":
                    [],

                "images":
                    [],
            }

            self.card_depth = (
                current_depth
            )

        if self.card is not None:

            if (
                tag == "h5"
                or (
                    tag == "p"
                    and "mb-1"
                    in _classes(
                        attributes.get(
                            "class"
                        )
                    )
                )
            ):
                if self.element is not None:
                    raise ValueError(
                        "nested weekly text "
                        "element changed"
                    )

                self.element = {
                    "tag":
                        tag,

                    "class":
                        attributes.get(
                            "class"
                        ),

                    "id":
                        attributes.get(
                            "id"
                        ),

                    "text_parts":
                        [],
                }

                self.element_depth = (
                    current_depth
                )

            if tag == "a":
                if self.anchor is not None:
                    raise ValueError(
                        "nested weekly anchor "
                        "changed"
                    )

                self.anchor = {
                    "href":
                        attributes.get(
                            "href"
                        ),

                    "class":
                        attributes.get(
                            "class"
                        ),

                    "rel":
                        attributes.get(
                            "rel"
                        ),

                    "text_parts":
                        [],
                }

                self.anchor_depth = (
                    current_depth
                )

            elif tag == "img":
                self.card[
                    "images"
                ].append({
                    "src":
                        attributes.get(
                            "src"
                        ),

                    "data_src":
                        attributes.get(
                            "data-src"
                        ),

                    "alt":
                        attributes.get(
                            "alt"
                        ),

                    "title":
                        attributes.get(
                            "title"
                        ),

                    "class":
                        attributes.get(
                            "class"
                        ),
                })

        if tag not in VOID_TAGS:
            self.depth += 1

    def handle_data(
        self,
        data,
    ):
        self.page_text.append(
            data
        )

        if self.h1_parts is not None:
            self.h1_parts.append(
                data
            )

        if self.card is not None:
            self.card[
                "text_parts"
            ].append(
                data
            )

        if self.element is not None:
            self.element[
                "text_parts"
            ].append(
                data
            )

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
            self.anchor is not None
            and tag == "a"
            and self.depth
            == self.anchor_depth
        ):
            value = dict(
                self.anchor
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

            self.card[
                "anchors"
            ].append(
                value
            )

            self.anchor = None
            self.anchor_depth = None

        if (
            self.element is not None
            and self.element[
                "tag"
            ] == tag
            and self.depth
            == self.element_depth
        ):
            value = dict(
                self.element
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

            if value[
                "text"
            ]:
                self.card[
                    "elements"
                ].append(
                    value
                )

            self.element = None
            self.element_depth = None

        if (
            self.h1_parts is not None
            and tag == "h1"
            and self.depth
            == self.h1_depth
        ):
            self.h1 = _text(
                "".join(
                    self.h1_parts
                )
            )

            self.h1_parts = None
            self.h1_depth = None

        if (
            self.card is not None
            and tag == "div"
            and self.depth
            == self.card_depth
        ):
            value = dict(
                self.card
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

            self.cards.append(
                value
            )

            self.card = None
            self.card_depth = None
            self.element = None
            self.element_depth = None
            self.anchor = None
            self.anchor_depth = None


def _parse_week_title(
    value: Any,
) -> dict:
    value = _text(
        value
    )

    if not value:
        raise ValueError(
            "missing weekly article title"
        )

    match = WEEK_TITLE_RE.fullmatch(
        value
    )

    if not match:
        raise ValueError(
            "unexpected weekly article title: "
            + repr(value)
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
            "invalid weekly period"
        )

    return {
        "article_title":
            value,

        "year":
            year,

        "week":
            week,

        "period":
            f"{year}-W{week:02d}",

        "period_label":
            _text(
                match.group(
                    "range"
                )
            ),
    }


def _movie_id_from_path(
    absolute_url: str,
):
    parsed = urlparse(
        absolute_url
    )

    if parsed.hostname not in (
        JAVDATABASE_HOSTS
    ):
        return None

    segments = [
        unquote(segment)
        for segment
        in parsed.path.split("/")
        if segment
    ]

    if (
        len(segments) != 2
        or segments[0].lower()
        != "movies"
    ):
        return None

    match = parse_dvd_id(
        segments[1]
    )

    if match is None:
        raise ValueError(
            "invalid JAV Database "
            "movie slug: "
            + repr(
                segments[1]
            )
        )

    return match.dvd_id


def _path_kind(
    absolute_url: str,
    kind: str,
) -> bool:
    parsed = urlparse(
        absolute_url
    )

    if parsed.hostname not in (
        JAVDATABASE_HOSTS
    ):
        return False

    segments = [
        unquote(segment)
        for segment
        in parsed.path.split("/")
        if segment
    ]

    return (
        len(segments) == 2
        and segments[0].lower()
        == kind
    )


def _parse_card(
    card: dict,
    *,
    document_rank: int,
    base_url: str,
) -> dict:
    card_text = _text(
        card.get(
            "text"
        )
    )

    if not card_text:
        raise ValueError(
            "weekly card has no text"
        )

    rank_match = (
        RANK_PREFIX_RE.match(
            card_text
        )
    )

    if not rank_match:
        raise ValueError(
            "weekly card missing "
            "displayed rank"
        )

    displayed_rank = int(
        rank_match.group(
            "rank"
        )
    )

    if (
        displayed_rank
        != document_rank
    ):
        raise ValueError(
            "weekly displayed rank "
            "does not match "
            "document order: "
            f"displayed={displayed_rank}, "
            f"document={document_rank}"
        )

    h5_values = [
        element[
            "text"
        ]
        for element
        in card[
            "elements"
        ]
        if (
            element[
                "tag"
            ] == "h5"
            and "mb-2"
            in _classes(
                element.get(
                    "class"
                )
            )
            and element.get(
                "text"
            )
        )
    ]

    if len(
        h5_values
    ) != 1:
        raise ValueError(
            "weekly card must have "
            "exactly one h5.mb-2 "
            "DVD ID"
        )

    id_match = parse_dvd_id(
        h5_values[0]
    )

    if id_match is None:
        raise ValueError(
            "invalid weekly h5 DVD ID"
        )

    dvd_id = (
        id_match.dvd_id
    )

    if (
        h5_values[0].upper()
        != dvd_id
    ):
        raise ValueError(
            "weekly h5 DVD ID "
            "is not canonical"
        )

    movie_urls = []

    genre_names = []
    studio_names = []
    idol_names = []

    for anchor in card[
        "anchors"
    ]:
        href = _text(
            anchor.get(
                "href"
            )
        )

        if not href:
            continue

        absolute = urljoin(
            base_url,
            href,
        )

        parsed = urlparse(
            absolute
        )

        if parsed.hostname not in (
            JAVDATABASE_HOSTS
        ):
            continue

        movie_id = (
            _movie_id_from_path(
                absolute
            )
        )

        if movie_id is not None:
            if movie_id != dvd_id:
                raise ValueError(
                    "weekly movie link "
                    "DVD ID mismatch"
                )

            if absolute not in (
                movie_urls
            ):
                movie_urls.append(
                    absolute
                )

            continue

        anchor_text = _text(
            anchor.get(
                "text"
            )
        )

        if not anchor_text:
            continue

        if _path_kind(
            absolute,
            "genres",
        ):
            if anchor_text not in (
                genre_names
            ):
                genre_names.append(
                    anchor_text
                )

        elif _path_kind(
            absolute,
            "studios",
        ):
            if anchor_text not in (
                studio_names
            ):
                studio_names.append(
                    anchor_text
                )

        elif _path_kind(
            absolute,
            "idols",
        ):
            if anchor_text not in (
                idol_names
            ):
                idol_names.append(
                    anchor_text
                )

    if not movie_urls:
        raise ValueError(
            "weekly card missing "
            "canonical movie link"
        )

    if len(
        studio_names
    ) != 1:
        raise ValueError(
            "weekly card must have "
            "exactly one studio"
        )

    title_values = []

    release_values = []

    for element in card[
        "elements"
    ]:
        if (
            element[
                "tag"
            ] != "p"
        ):
            continue

        text = _text(
            element.get(
                "text"
            )
        )

        if not text:
            continue

        title_match = (
            TITLE_RE.fullmatch(
                text
            )
        )

        if title_match:
            title_values.append(
                _text(
                    title_match.group(
                        1
                    )
                )
            )

            continue

        release_match = (
            RELEASE_DATE_RE.fullmatch(
                text
            )
        )

        if release_match:
            release_values.append(
                release_match.group(
                    1
                )
            )

    if (
        len(title_values) != 1
        or not title_values[0]
    ):
        raise ValueError(
            "weekly card must have "
            "exactly one title"
        )

    if len(
        release_values
    ) != 1:
        raise ValueError(
            "weekly card must have "
            "exactly one release date"
        )

    try:
        date.fromisoformat(
            release_values[0]
        )

    except ValueError as exc:
        raise ValueError(
            "invalid weekly "
            "release date"
        ) from exc

    cover_urls = []

    for image in card[
        "images"
    ]:
        alt = _text(
            image.get(
                "alt"
            )
        )

        if alt != dvd_id:
            continue

        source = (
            _text(
                image.get(
                    "data_src"
                )
            )
            or _text(
                image.get(
                    "src"
                )
            )
        )

        if not source:
            continue

        absolute = urljoin(
            base_url,
            source,
        )

        parsed = urlparse(
            absolute
        )

        if (
            parsed.scheme != "https"
            or parsed.hostname
            not in JAVDATABASE_HOSTS
        ):
            raise ValueError(
                "weekly cover escaped "
                "JAV Database host"
            )

        if absolute not in (
            cover_urls
        ):
            cover_urls.append(
                absolute
            )

    if len(
        cover_urls
    ) != 1:
        raise ValueError(
            "weekly card must have "
            "exactly one DVD-ID-matched "
            "cover image"
        )

    return {
        "source":
            JAVDATABASE_WEEKLY_SOURCE,

        "rank":
            displayed_rank,

        "dvd_id":
            dvd_id,

        "source_url":
            movie_urls[0],

        "title":
            title_values[0],

        "cover_url":
            cover_urls[0],

        "release_date":
            release_values[0],

        "studio":
            studio_names[0],

        "genres":
            genre_names,

        "idols":
            idol_names,
    }


def parse_javdatabase_weekly_html(
    html: str,
    base_url: str,
    *,
    expected_count: int = (
        DEFAULT_EXPECTED_COUNT
    ),
) -> dict:
    if not isinstance(
        html,
        str,
    ) or not html.strip():
        raise ValueError(
            "JAV Database weekly "
            "HTML is empty"
        )

    base_url = (
        _required_https_javdatabase_url(
            base_url,
            "weekly article URL",
        )
    )

    if (
        not isinstance(
            expected_count,
            int,
        )
        or expected_count < 1
        or expected_count > 100
    ):
        raise ValueError(
            "expected_count must "
            "be 1..100"
        )

    parser = (
        _WeeklyArticleParser()
    )

    parser.feed(
        html
    )

    period = (
        _parse_week_title(
            parser.h1
        )
    )

    page_text = (
        _text(
            "".join(
                parser.page_text
            )
        )
        or ""
    ).lower()

    if (
        METHOD_VISITS.lower()
        not in page_text
        or METHOD_WEIGHTING.lower()
        not in page_text
    ):
        raise ValueError(
            "JAV Database weekly "
            "ranking methodology changed"
        )

    if len(
        parser.cards
    ) != expected_count:
        raise ValueError(
            "unexpected JAV Database "
            "weekly card count: "
            f"expected {expected_count}, "
            f"got {len(parser.cards)}"
        )

    items = [
        _parse_card(
            card,
            document_rank=index,
            base_url=base_url,
        )
        for index, card
        in enumerate(
            parser.cards,
            start=1,
        )
    ]

    dvd_ids = [
        item[
            "dvd_id"
        ]
        for item
        in items
    ]

    if len(
        set(dvd_ids)
    ) != len(
        dvd_ids
    ):
        raise ValueError(
            "duplicate weekly DVD ID"
        )

    if [
        item[
            "rank"
        ]
        for item
        in items
    ] != list(
        range(
            1,
            expected_count + 1,
        )
    ):
        raise ValueError(
            "weekly ranks are "
            "not consecutive"
        )

    return {
        "source":
            JAVDATABASE_WEEKLY_SOURCE,

        **period,

        "source_url":
            base_url,

        "method":
            (
                "prior-seven-day "
                "movie-page visits; "
                "slightly weighted "
                "towards newer releases"
            ),

        "item_count":
            len(items),

        "items":
            items,
    }


def parse_javdatabase_weekly_envelope(
    envelope: dict,
    *,
    expected_count: int = (
        DEFAULT_EXPECTED_COUNT
    ),
) -> dict:
    if not isinstance(
        envelope,
        dict,
    ):
        raise ValueError(
            "weekly envelope must "
            "be object"
        )

    if envelope.get(
        "status"
    ) != 200:
        raise ValueError(
            "cannot parse weekly "
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
            "weekly envelope body "
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
        parse_javdatabase_weekly_html(
            body,
            url,
            expected_count=
                expected_count,
        )
    )
