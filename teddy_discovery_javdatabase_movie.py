from __future__ import annotations

from datetime import date
from html.parser import HTMLParser
from typing import Any
from urllib.parse import (
    urljoin,
    urlparse,
)

from teddy_discovery_ids import (
    parse_dvd_id,
)

from teddy_discovery_javdatabase import (
    JAVDATABASE_HOSTS,
)


JAVDATABASE_MOVIE_SOURCE = (
    "javdatabase-movie"
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


def _canonical_dvd_id(
    value: Any,
) -> str:
    value = _text(
        value
    )

    if not value:
        raise ValueError(
            "missing DVD ID"
        )

    match = parse_dvd_id(
        value
    )

    if match is None:
        raise ValueError(
            "invalid DVD ID"
        )

    return match.dvd_id


def _validate_movie_url(
    value: Any,
    *,
    expected_dvd_id: str,
) -> str:
    value = _text(
        value
    )

    if not value:
        raise ValueError(
            "missing movie URL"
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
            "movie URL host"
        )

    segments = [
        segment
        for segment
        in parsed.path.split("/")
        if segment
    ]

    if (
        len(segments) != 2
        or segments[0].lower()
        != "movies"
    ):
        raise ValueError(
            "invalid JAV Database "
            "movie URL path"
        )

    actual = _canonical_dvd_id(
        segments[1]
    )

    if actual != expected_dvd_id:
        raise ValueError(
            "movie URL DVD ID mismatch"
        )

    return value


def _path_kind(
    value: str,
    kind: str,
) -> bool:
    parsed = urlparse(
        value
    )

    if parsed.hostname not in (
        JAVDATABASE_HOSTS
    ):
        return False

    segments = [
        segment
        for segment
        in parsed.path.split("/")
        if segment
    ]

    return (
        len(segments) == 2
        and segments[0].lower()
        == kind
    )


class _MoviePageParser(
    HTMLParser
):
    def __init__(self):
        super().__init__(
            convert_charrefs=True
        )

        self.depth = 0

        self.paragraph = None
        self.paragraph_depth = None

        self.bold_parts = None
        self.bold_depth = None

        self.anchor = None
        self.anchor_depth = None

        self.paragraphs = []
        self.images = []

        self.thumbnail_depth = None
        self.thumbnail_count = 0

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

        if (
            tag == "div"
            and attributes.get(
                "id"
            )
            == "thumbnailContainer"
        ):
            if (
                self.thumbnail_depth
                is not None
                or self.thumbnail_count
                != 0
            ):
                raise ValueError(
                    "multiple movie thumbnail "
                    "containers changed"
                )

            self.thumbnail_depth = (
                current_depth
            )

            self.thumbnail_count += 1

        if (
            self.paragraph is None
            and tag == "p"
            and "mb-1"
            in _classes(
                attributes.get(
                    "class"
                )
            )
        ):
            self.paragraph = {
                "text_parts": [],
                "label_parts": [],
                "anchors": [],
            }

            self.paragraph_depth = (
                current_depth
            )

        if (
            self.paragraph
            is not None
            and tag == "b"
        ):
            if (
                self.bold_parts
                is not None
            ):
                raise ValueError(
                    "nested movie metadata "
                    "bold element changed"
                )

            self.bold_parts = []
            self.bold_depth = (
                current_depth
            )

        if (
            self.paragraph
            is not None
            and tag == "a"
        ):
            if self.anchor is not None:
                raise ValueError(
                    "nested movie metadata "
                    "anchor changed"
                )

            self.anchor = {
                "href":
                    attributes.get(
                        "href"
                    ),

                "text_parts":
                    [],
            }

            self.anchor_depth = (
                current_depth
            )

        if tag == "img":
            self.images.append({
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

                "inside_thumbnail":
                    (
                        self.thumbnail_depth
                        is not None
                    ),
            })

        if tag not in VOID_TAGS:
            self.depth += 1

    def handle_data(
        self,
        data,
    ):
        if (
            self.paragraph
            is not None
        ):
            self.paragraph[
                "text_parts"
            ].append(
                data
            )

        if self.bold_parts is not None:
            self.bold_parts.append(
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
            self.thumbnail_depth
            is not None
            and tag == "div"
            and self.depth
            == self.thumbnail_depth
        ):
            self.thumbnail_depth = None

        if (
            self.anchor is not None
            and tag == "a"
            and self.depth
            == self.anchor_depth
        ):
            value = dict(
                self.anchor
            )

            value["text"] = _text(
                "".join(
                    value.pop(
                        "text_parts"
                    )
                )
            )

            self.paragraph[
                "anchors"
            ].append(
                value
            )

            self.anchor = None
            self.anchor_depth = None

        if (
            self.bold_parts
            is not None
            and tag == "b"
            and self.depth
            == self.bold_depth
        ):
            self.paragraph[
                "label_parts"
            ].extend(
                self.bold_parts
            )

            self.bold_parts = None
            self.bold_depth = None

        if (
            self.paragraph
            is not None
            and tag == "p"
            and self.depth
            == self.paragraph_depth
        ):
            value = dict(
                self.paragraph
            )

            value["text"] = _text(
                "".join(
                    value.pop(
                        "text_parts"
                    )
                )
            )

            value["label"] = _text(
                "".join(
                    value.pop(
                        "label_parts"
                    )
                )
            )

            self.paragraphs.append(
                value
            )

            self.paragraph = None
            self.paragraph_depth = None
            self.bold_parts = None
            self.bold_depth = None
            self.anchor = None
            self.anchor_depth = None


def _normalized_label(
    value: Any,
):
    value = _text(
        value
    )

    if not value:
        return None

    return value.rstrip(
        ":"
    ).strip()


def _field_rows(
    parser: _MoviePageParser,
    label: str,
):
    return [
        row
        for row
        in parser.paragraphs
        if _normalized_label(
            row.get(
                "label"
            )
        )
        == label
    ]


def _required_single_row(
    parser: _MoviePageParser,
    label: str,
):
    rows = _field_rows(
        parser,
        label,
    )

    if len(rows) != 1:
        raise ValueError(
            "movie metadata must have "
            f"exactly one {label!r} field"
        )

    return rows[0]


def _field_text(
    row: dict,
):
    label = _text(
        row.get(
            "label"
        )
    )

    text = _text(
        row.get(
            "text"
        )
    )

    if not label or not text:
        return None

    if not text.startswith(
        label
    ):
        raise ValueError(
            "movie metadata label/text "
            "boundary changed"
        )

    return _text(
        text[
            len(label):
        ]
    )


def _link_names(
    row: dict,
    *,
    kind: str,
    base_url: str,
):
    values = []

    for anchor in row[
        "anchors"
    ]:
        href = _text(
            anchor.get(
                "href"
            )
        )

        name = _text(
            anchor.get(
                "text"
            )
        )

        if not href or not name:
            continue

        absolute = urljoin(
            base_url,
            href,
        )

        if not _path_kind(
            absolute,
            kind,
        ):
            continue

        if name not in values:
            values.append(
                name
            )

    return values


def parse_javdatabase_movie_html(
    html: str,
    source_url: str,
    *,
    expected_dvd_id: str,
) -> dict:
    if not isinstance(
        html,
        str,
    ):
        raise ValueError(
            "movie HTML must be text"
        )

    expected_dvd_id = (
        _canonical_dvd_id(
            expected_dvd_id
        )
    )

    source_url = (
        _validate_movie_url(
            source_url,
            expected_dvd_id=
                expected_dvd_id,
        )
    )

    parser = _MoviePageParser()

    parser.feed(
        html
    )

    parser.close()

    title_row = (
        _required_single_row(
            parser,
            "Title",
        )
    )

    dvd_row = (
        _required_single_row(
            parser,
            "DVD ID",
        )
    )

    release_row = (
        _required_single_row(
            parser,
            "Release Date",
        )
    )

    studio_row = (
        _required_single_row(
            parser,
            "Studio",
        )
    )

    genre_row = (
        _required_single_row(
            parser,
            "Genre(s)",
        )
    )

    idol_row = (
        _required_single_row(
            parser,
            "Idol(s)/Actress(es)",
        )
    )

    title = _field_text(
        title_row
    )

    if not title:
        raise ValueError(
            "movie title is empty"
        )

    dvd_id = _canonical_dvd_id(
        _field_text(
            dvd_row
        )
    )

    if dvd_id != expected_dvd_id:
        raise ValueError(
            "movie metadata DVD ID "
            "mismatch"
        )

    release_date = _field_text(
        release_row
    )

    if not release_date:
        raise ValueError(
            "movie release date "
            "is empty"
        )

    try:
        date.fromisoformat(
            release_date
        )

    except ValueError as exc:
        raise ValueError(
            "invalid movie release date"
        ) from exc

    studios = _link_names(
        studio_row,
        kind="studios",
        base_url=
            source_url,
    )

    if len(studios) != 1:
        raise ValueError(
            "movie metadata must have "
            "exactly one studio"
        )

    genres = _link_names(
        genre_row,
        kind="genres",
        base_url=
            source_url,
    )

    idols = _link_names(
        idol_row,
        kind="idols",
        base_url=
            source_url,
    )

    cover_urls = []

    for image in parser.images:
        if not image.get(
            "inside_thumbnail"
        ):
            continue

        alt = _text(
            image.get(
                "alt"
            )
        )

        if (
            not alt
            or expected_dvd_id
            not in alt.upper()
        ):
            continue

        value = (
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

        if not value:
            continue

        absolute = urljoin(
            source_url,
            value,
        )

        parsed = urlparse(
            absolute
        )

        if (
            parsed.scheme != "https"
            or parsed.hostname
            not in JAVDATABASE_HOSTS
        ):
            continue

        if (
            "/covers/"
            not in parsed.path
        ):
            continue

        if absolute not in cover_urls:
            cover_urls.append(
                absolute
            )

    if len(cover_urls) != 1:
        raise ValueError(
            "movie metadata must have "
            "exactly one DVD-matched "
            "cover image"
        )

    return {
        "source":
            JAVDATABASE_MOVIE_SOURCE,

        "dvd_id":
            dvd_id,

        "source_url":
            source_url,

        "title":
            title,

        "cover_url":
            cover_urls[0],

        "release_date":
            release_date,

        "studio":
            studios[0],

        "genres":
            genres,

        "idols":
            idols,
    }


def parse_javdatabase_movie_envelope(
    envelope: dict,
    *,
    expected_dvd_id: str,
) -> dict:
    if not isinstance(
        envelope,
        dict,
    ):
        raise ValueError(
            "movie envelope must "
            "be an object"
        )

    status = envelope.get(
        "status"
    )

    if status != 200:
        raise ValueError(
            "cannot parse movie "
            f"HTTP status {status!r}"
        )

    body = envelope.get(
        "body"
    )

    if not isinstance(
        body,
        str,
    ):
        raise ValueError(
            "movie envelope body "
            "must be text"
        )

    source_url = (
        _text(
            envelope.get(
                "final_url"
            )
        )
        or _text(
            envelope.get(
                "requested_url"
            )
        )
        or _text(
            envelope.get(
                "url"
            )
        )
    )

    return parse_javdatabase_movie_html(
        body,
        source_url,
        expected_dvd_id=
            expected_dvd_id,
    )
