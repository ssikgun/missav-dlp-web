from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import (
    unquote,
    urljoin,
    urlsplit,
)


MISSAV_HOST = "missav.ws"
MISSAV_LOCALE = "en"

_DATE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}$"
)

_VOID_TAGS = {
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


def _clean(
    value: object,
) -> str:
    return " ".join(
        str(
            value
            if value is not None
            else ""
        ).split()
    )


def _unique(
    values: list[str],
) -> list[str]:
    result: list[str] = []

    for value in values:
        cleaned = _clean(
            value
        )

        if (
            cleaned
            and cleaned not in result
        ):
            result.append(
                cleaned
            )

    return result


def _class_tokens(
    value: object,
) -> set[str]:
    return {
        token
        for token in _clean(
            value
        ).split()
        if token
    }


def normalize_dvd_id(
    value: object,
) -> str:
    from teddy_discovery_ids import (
        parse_dvd_id,
    )

    candidate = (
        _clean(value)
        .upper()
        .replace("_", "-")
        .replace(" ", "")
    )

    parsed = parse_dvd_id(
        candidate
    )

    if parsed is None:
        raise ValueError(
            "invalid dvd_id"
        )

    canonical = parsed.dvd_id

    if (
        candidate.replace("-", "")
        != canonical.replace("-", "")
    ):
        raise ValueError(
            "invalid dvd_id"
        )

    return canonical


def _validate_detail_url(
    url: object,
    expected_dvd_id: str,
) -> str:
    if not isinstance(
        url,
        str,
    ):
        raise ValueError(
            "MissAV detail URL must be a string"
        )

    parsed = urlsplit(
        url
    )

    if parsed.scheme != "https":
        raise ValueError(
            "MissAV detail URL must use https"
        )

    if parsed.hostname != MISSAV_HOST:
        raise ValueError(
            "unexpected MissAV detail host"
        )

    if (
        parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "MissAV detail query/fragment forbidden"
        )

    segments = [
        unquote(segment)
        for segment
        in parsed.path.split("/")
        if segment
    ]

    if len(segments) != 2:
        raise ValueError(
            "unexpected MissAV detail path"
        )

    if segments[0] != MISSAV_LOCALE:
        raise ValueError(
            "MissAV detail locale must be en"
        )

    actual_dvd_id = normalize_dvd_id(
        segments[1]
    )

    if (
        actual_dvd_id
        != expected_dvd_id
    ):
        raise ValueError(
            "MissAV detail dvd_id mismatch"
        )

    return (
        parsed.scheme
        + "://"
        + parsed.netloc
        + parsed.path
    )


class _MissavDetailParser(
    HTMLParser
):
    def __init__(
        self,
    ) -> None:
        super().__init__(
            convert_charrefs=True
        )

        self.stack: list[
            dict[str, object]
        ] = []

        self.metas: list[
            dict[str, str]
        ] = []

        self.anchors: list[
            dict[str, object]
        ] = []

        self.detail_rows: list[
            str
        ] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[
            tuple[
                str,
                str | None,
            ]
        ],
    ) -> None:
        lowered = tag.lower()

        attributes = {
            str(key):
                (
                    ""
                    if value is None
                    else str(value)
                )
            for key, value in attrs
        }

        if lowered == "meta":
            self.metas.append(
                attributes
            )
            return

        if lowered in _VOID_TAGS:
            return

        self.stack.append(
            {
                "tag":
                    lowered,

                "attrs":
                    attributes,

                "parts":
                    [],
            }
        )

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[
            tuple[
                str,
                str | None,
            ]
        ],
    ) -> None:
        if tag.lower() != "meta":
            return

        self.metas.append(
            {
                str(key):
                    (
                        ""
                        if value is None
                        else str(value)
                    )
                for key, value
                in attrs
            }
        )

    def handle_data(
        self,
        data: str,
    ) -> None:
        for node in self.stack:
            parts = node[
                "parts"
            ]

            assert isinstance(
                parts,
                list,
            )

            parts.append(
                data
            )

    def handle_endtag(
        self,
        tag: str,
    ) -> None:
        lowered = tag.lower()

        match_index = None

        for index in range(
            len(self.stack) - 1,
            -1,
            -1,
        ):
            if (
                self.stack[index][
                    "tag"
                ]
                == lowered
            ):
                match_index = index
                break

        if match_index is None:
            return

        node = self.stack[
            match_index
        ]

        ancestors = self.stack[
            :match_index
        ]

        del self.stack[
            match_index:
        ]

        parts = node[
            "parts"
        ]

        assert isinstance(
            parts,
            list,
        )

        value = _clean(
            "".join(
                str(part)
                for part in parts
            )
        )

        attrs = node[
            "attrs"
        ]

        assert isinstance(
            attrs,
            dict,
        )

        if lowered == "a":
            self.anchors.append(
                {
                    "href":
                        attrs.get(
                            "href"
                        ),

                    "class":
                        attrs.get(
                            "class"
                        ),

                    "text":
                        value,

                    "ancestor_classes":
                        [
                            (
                                ancestor[
                                    "attrs"
                                ].get(
                                    "class"
                                )
                                if isinstance(
                                    ancestor.get(
                                        "attrs"
                                    ),
                                    dict,
                                )
                                else None
                            )
                            for ancestor
                            in ancestors
                        ],
                }
            )

        if (
            lowered == "div"
            and "text-secondary"
            in _class_tokens(
                attrs.get(
                    "class"
                )
            )
            and value
        ):
            self.detail_rows.append(
                value
            )


def _meta_values(
    parser: _MissavDetailParser,
    key: str,
) -> list[str]:
    values: list[str] = []

    for attrs in parser.metas:
        name = (
            attrs.get(
                "property"
            )
            or attrs.get(
                "name"
            )
        )

        if name != key:
            continue

        value = _clean(
            attrs.get(
                "content"
            )
        )

        if value:
            values.append(
                value
            )

    return _unique(
        values
    )


def _is_detail_anchor(
    anchor: dict[str, object],
) -> bool:
    own = _class_tokens(
        anchor.get(
            "class"
        )
    )

    if not {
        "text-nord13",
        "font-medium",
    } <= own:
        return False

    ancestor_tokens: set[str] = set()

    values = anchor.get(
        "ancestor_classes",
        [],
    )

    if isinstance(
        values,
        list,
    ):
        for value in values:
            ancestor_tokens.update(
                _class_tokens(
                    value
                )
            )

    return (
        "text-secondary"
        in ancestor_tokens
        and "space-y-2"
        in ancestor_tokens
    )


def _classify_detail_anchor(
    base_url: str,
    anchor: dict[str, object],
) -> tuple[
    str,
    str,
] | None:
    if not _is_detail_anchor(
        anchor
    ):
        return None

    href = anchor.get(
        "href"
    )

    if not isinstance(
        href,
        str,
    ):
        return None

    absolute = urljoin(
        base_url,
        href,
    )

    parsed = urlsplit(
        absolute
    )

    base = urlsplit(
        base_url
    )

    if parsed.hostname != base.hostname:
        return None

    segments = [
        unquote(segment)
        for segment
        in parsed.path.split("/")
        if segment
    ]

    for category in (
        "actresses",
        "genres",
        "makers",
    ):
        if category not in segments:
            continue

        index = segments.index(
            category
        )

        if (
            index + 1
            >= len(segments)
        ):
            return None

        value = _clean(
            anchor.get(
                "text"
            )
        )

        if not value:
            return None

        return (
            category,
            value,
        )

    return None


def _detail_link_values(
    parser: _MissavDetailParser,
    base_url: str,
) -> dict[
    str,
    list[str],
]:
    result = {
        "actresses":
            [],

        "genres":
            [],

        "makers":
            [],
    }

    for anchor in parser.anchors:
        classified = (
            _classify_detail_anchor(
                base_url,
                anchor,
            )
        )

        if classified is None:
            continue

        category, value = classified

        result[
            category
        ].append(
            value
        )

    for category in result:
        result[
            category
        ] = _unique(
            result[
                category
            ]
        )

    return result


def _labeled_values(
    parser: _MissavDetailParser,
    label: str,
) -> list[str]:
    prefix = (
        label
        + ":"
    )

    values: list[str] = []

    for row in parser.detail_rows:
        cleaned = _clean(
            row
        )

        if not cleaned.startswith(
            prefix
        ):
            continue

        value = _clean(
            cleaned[
                len(prefix):
            ]
        )

        if value:
            values.append(
                value
            )

    return _unique(
        values
    )


def parse_missav_movie_html(
    html: str,
    *,
    requested_url: str,
    expected_dvd_id: str,
) -> dict[str, object]:
    dvd_id = normalize_dvd_id(
        expected_dvd_id
    )

    source_url = _validate_detail_url(
        requested_url,
        dvd_id,
    )

    if not isinstance(
        html,
        str,
    ):
        raise ValueError(
            "MissAV detail HTML must be text"
        )

    parser = _MissavDetailParser()

    parser.feed(
        html
    )

    titles = _meta_values(
        parser,
        "og:title",
    )

    if len(titles) != 1:
        raise ValueError(
            "MissAV detail og:title must be unique"
        )

    if (
        dvd_id.lower()
        not in titles[0].lower()
    ):
        raise ValueError(
            "MissAV detail identity mismatch"
        )

    releases = _meta_values(
        parser,
        "og:video:release_date",
    )

    release_labels = (
        _labeled_values(
            parser,
            "Release date",
        )
    )

    #
    # The visible Release date is the catalog
    # field used by Teddy. MissAV's OG video
    # date can represent a different publication
    # timestamp on current shard pages, so it
    # remains structurally validated but is not
    # required to equal the catalog field.
    #
    if (
        len(releases) != 1
        or len(release_labels) != 1
        or _DATE_RE.fullmatch(
            releases[0]
        )
        is None
        or _DATE_RE.fullmatch(
            release_labels[0]
        )
        is None
    ):
        raise ValueError(
            "MissAV detail release contract mismatch"
        )

    release_date = (
        release_labels[0]
    )

    links = _detail_link_values(
        parser,
        source_url,
    )

    makers = links[
        "makers"
    ]

    maker_labels = (
        _labeled_values(
            parser,
            "Maker",
        )
    )

    #
    # Maker is optional on sparse catalog pages.
    # Absence is valid only when BOTH structural
    # representations are absent. Partial or
    # conflicting maker data remains fail-closed.
    #
    studio = None

    if makers or maker_labels:
        if (
            len(makers) != 1
            or len(maker_labels) != 1
            or makers[0]
                != maker_labels[0]
        ):
            raise ValueError(
                "MissAV detail maker contract mismatch"
            )

        studio = makers[0]

    actor_meta = _meta_values(
        parser,
        "og:video:actor",
    )

    idols = links[
        "actresses"
    ]

    actress_labels = (
        _labeled_values(
            parser,
            "Actress",
        )
    )

    if set(
        actor_meta
    ) != set(
        idols
    ):
        raise ValueError(
            "MissAV detail actor contract mismatch"
        )

    actress_label_matches = (
        not actress_labels
        or set(
            actress_labels
        ) == set(
            idols
        )
        or (
            len(
                actress_labels
            ) == 1
            and actress_labels[0]
                == ", ".join(
                    idols
                )
        )
    )

    if not actress_label_matches:
        raise ValueError(
            "MissAV detail actress label mismatch"
        )

    genres = links[
        "genres"
    ]

    genre_labels_raw = (
        _labeled_values(
            parser,
            "Genre",
        )
    )

    genre_labels: list[str] = []

    for raw in genre_labels_raw:
        genre_labels.extend(
            [
                _clean(item)
                for item
                in raw.split(",")
                if _clean(item)
            ]
        )

    genre_labels = _unique(
        genre_labels
    )

    #
    # Genre is also optional when BOTH the
    # detail links and Genre label are absent.
    # Tag/brand fields are deliberately NOT
    # promoted into genres.
    #
    if set(genres) != set(genre_labels):
        raise ValueError(
            "MissAV detail genre contract mismatch"
        )

    #
    # Locale trust comes from the exact /en/
    # source URL plus the English structural
    # labels and cross-field equality checks
    # above. Character script is not a locale
    # selector: preserve Unicode values exactly
    # as supplied by the English page.
    #

    #
    # CP32/33/35/36 proved these are catalog or
    # brand tags, not genres.
    #
    brand_tags = _meta_values(
        parser,
        "og:video:tag",
    )

    return {
        "dvd_id":
            dvd_id,

        "title":
            titles[0],

        "release_date":
            release_date,

        "studio":
            studio,

        "idols":
            idols,

        "genres":
            genres,

        "brand_tags":
            brand_tags,

        "source_url":
            source_url,
    }


def parse_missav_movie_envelope(
    envelope: dict[str, object],
    *,
    expected_dvd_id: str,
) -> dict[str, object]:
    if not isinstance(
        envelope,
        dict,
    ):
        raise ValueError(
            "MissAV detail envelope must be a dict"
        )

    if envelope.get(
        "status"
    ) != 200:
        raise ValueError(
            "MissAV detail status must be 200"
        )

    requested_url = envelope.get(
        "requested_url"
    )

    final_url = envelope.get(
        "final_url"
    )

    body = envelope.get(
        "body"
    )

    dvd_id = normalize_dvd_id(
        expected_dvd_id
    )

    requested = _validate_detail_url(
        requested_url,
        dvd_id,
    )

    final = _validate_detail_url(
        final_url,
        dvd_id,
    )

    if requested != final:
        raise ValueError(
            "MissAV detail redirect forbidden"
        )

    if not isinstance(
        body,
        str,
    ):
        raise ValueError(
            "MissAV detail body must be text"
        )

    return parse_missav_movie_html(
        body,
        requested_url=requested,
        expected_dvd_id=dvd_id,
    )
