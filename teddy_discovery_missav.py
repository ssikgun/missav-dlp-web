from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser
import sqlite3
from typing import Any, Iterable
from urllib.parse import (
    unquote,
    urljoin,
    urlparse,
)

from teddy_discovery_ids import (
    parse_dvd_id,
)


MISSAV_RELEASE_SOURCE = "missav-release"
DEFAULT_LANGUAGE = "ko"


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

    value = str(value).strip()

    return value or None


def _attrs_dict(
    attrs,
) -> dict:
    return {
        str(key): (
            None
            if value is None
            else str(value)
        )
        for key, value in attrs
    }


def _optional_http_url(
    value: Any,
):
    value = _text(value)

    if not value:
        return None

    parsed = urlparse(value)

    if (
        parsed.scheme
        not in {
            "http",
            "https",
        }
        or not parsed.hostname
    ):
        return None

    return value


def _required_https_url(
    value: Any,
    label: str,
) -> str:
    value = _text(value)

    if not value:
        raise ValueError(
            f"missing {label}"
        )

    parsed = urlparse(value)

    if (
        parsed.scheme != "https"
        or not parsed.hostname
    ):
        raise ValueError(
            f"invalid {label}: "
            f"{value!r}"
        )

    return value


class _MissavCardParser(
    HTMLParser
):
    def __init__(self):
        super().__init__(
            convert_charrefs=True
        )

        self.stack = []
        self.anchor = None
        self.records = []

    def handle_starttag(
        self,
        tag,
        attrs,
    ):
        attributes = _attrs_dict(
            attrs
        )

        classes = set(
            (
                attributes.get(
                    "class"
                )
                or ""
            ).split()
        )

        node = {
            "tag":
                tag,

            "classes":
                classes,
        }

        if tag == "a":
            in_thumbnail = any(
                ancestor["tag"]
                == "div"
                and {
                    "thumbnail",
                    "group",
                }.issubset(
                    ancestor[
                        "classes"
                    ]
                )
                for ancestor
                in self.stack
            )

            self.anchor = {
                "href":
                    attributes.get(
                        "href"
                    ),

                "in_thumbnail":
                    in_thumbnail,

                "text":
                    [],

                "images":
                    [],
            }

        elif (
            tag == "img"
            and self.anchor
            is not None
        ):
            self.anchor[
                "images"
            ].append(
                attributes
            )

        if tag not in VOID_TAGS:
            self.stack.append(
                node
            )

    def handle_endtag(
        self,
        tag,
    ):
        if (
            tag == "a"
            and self.anchor
            is not None
        ):
            self.anchor[
                "text"
            ] = " ".join(
                " ".join(
                    self.anchor[
                        "text"
                    ]
                ).split()
            )

            self.records.append(
                self.anchor
            )

            self.anchor = None

        for index in range(
            len(self.stack) - 1,
            -1,
            -1,
        ):
            if (
                self.stack[index][
                    "tag"
                ]
                == tag
            ):
                del self.stack[
                    index:
                ]
                break

    def handle_data(
        self,
        data,
    ):
        if self.anchor is not None:
            self.anchor[
                "text"
            ].append(
                data
            )


def parse_missav_release_html(
    html: str,
    base_url: str,
    language: str = DEFAULT_LANGUAGE,
) -> list[dict]:
    if not isinstance(
        html,
        str,
    ):
        raise ValueError(
            "MissAV HTML must be text"
        )

    if not html.strip():
        raise ValueError(
            "MissAV HTML is empty"
        )

    base_url = (
        _required_https_url(
            base_url,
            "base URL",
        )
    )

    base = urlparse(
        base_url
    )

    language = _text(
        language
    )

    if not language:
        raise ValueError(
            "missing language"
        )

    parser = _MissavCardParser()
    parser.feed(html)

    items = []
    seen = {}

    for record in parser.records:
        if not record[
            "in_thumbnail"
        ]:
            continue

        href = _text(
            record.get(
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

        if (
            parsed.scheme != "https"
            or parsed.hostname
            != base.hostname
        ):
            continue

        segments = [
            unquote(segment)
            for segment
            in parsed.path.split("/")
            if segment
        ]

        if len(segments) != 2:
            continue

        if segments[0] != language:
            continue

        slug = segments[1]

        dvd = parse_dvd_id(
            slug
        )

        if dvd is None:
            continue

        images = record.get(
            "images"
        ) or []

        if not images:
            continue

        image = images[0]

        title = (
            _text(
                image.get(
                    "alt"
                )
            )
            or _text(
                record.get(
                    "text"
                )
            )
        )

        cover_url = (
            _optional_http_url(
                image.get(
                    "data-src"
                )
            )
        )

        if cover_url is None:
            src = _text(
                image.get(
                    "src"
                )
            )

            if (
                src
                and not src.lower().startswith(
                    "data:"
                )
            ):
                cover_url = (
                    _optional_http_url(
                        src
                    )
                )

        canonical_url = (
            f"{parsed.scheme}://"
            f"{parsed.netloc}"
            f"{parsed.path}"
        )

        candidate = {
            "source":
                MISSAV_RELEASE_SOURCE,

            "dvd_id":
                dvd.dvd_id,

            "source_url":
                canonical_url,

            "title":
                title,

            "cover_url":
                cover_url,

            "position":
                len(items) + 1,
        }

        previous = seen.get(
            dvd.dvd_id
        )

        if previous is not None:
            if (
                previous["source_url"]
                != candidate[
                    "source_url"
                ]
            ):
                raise ValueError(
                    "conflicting duplicate "
                    f"MissAV DVD ID: "
                    f"{dvd.dvd_id}"
                )

            continue

        seen[
            dvd.dvd_id
        ] = candidate

        items.append(
            candidate
        )

    return items


def parse_missav_release_envelope(
    envelope: dict,
    language: str = DEFAULT_LANGUAGE,
) -> list[dict]:
    if not isinstance(
        envelope,
        dict,
    ):
        raise ValueError(
            "forensic envelope must be object"
        )

    status = envelope.get(
        "status"
    )

    if status != 200:
        raise ValueError(
            "cannot parse MissAV "
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
            "MissAV envelope body "
            "must be text"
        )

    base_url = (
        envelope.get(
            "final_url"
        )
        or envelope.get(
            "requested_url"
        )
    )

    return parse_missav_release_html(
        body,
        base_url,
        language=language,
    )


def _validated_items(
    items: Iterable[dict],
    source: str,
) -> list[dict]:
    source = _text(
        source
    )

    if not source:
        raise ValueError(
            "missing latest source"
        )

    values = list(
        items
    )

    if not values:
        raise ValueError(
            "refusing empty latest import"
        )

    seen = set()
    result = []

    for expected_position, item in enumerate(
        values,
        start=1,
    ):
        if not isinstance(
            item,
            dict,
        ):
            raise ValueError(
                "latest item must be object"
            )

        if (
            _text(
                item.get(
                    "source"
                )
            )
            != source
        ):
            raise ValueError(
                "latest source mismatch"
            )

        dvd_id = _text(
            item.get(
                "dvd_id"
            )
        )

        parsed = (
            parse_dvd_id(
                dvd_id
            )
            if dvd_id
            else None
        )

        if (
            parsed is None
            or parsed.dvd_id
            != dvd_id
        ):
            raise ValueError(
                "latest item has "
                f"invalid dvd_id: "
                f"{dvd_id!r}"
            )

        if dvd_id in seen:
            raise ValueError(
                "duplicate latest dvd_id: "
                + dvd_id
            )

        seen.add(
            dvd_id
        )

        position = item.get(
            "position"
        )

        if (
            not isinstance(
                position,
                int,
            )
            or position
            != expected_position
        ):
            raise ValueError(
                "latest positions must "
                "be consecutive from 1"
            )

        source_url = (
            _required_https_url(
                item.get(
                    "source_url"
                ),
                "source URL",
            )
        )

        cover_url = (
            _optional_http_url(
                item.get(
                    "cover_url"
                )
            )
        )

        result.append({
            "source":
                source,

            "dvd_id":
                dvd_id,

            "source_url":
                source_url,

            "title":
                _text(
                    item.get(
                        "title"
                    )
                ),

            "cover_url":
                cover_url,

            "position":
                position,
        })

    return result


def upsert_latest_items(
    connection: sqlite3.Connection,
    items: Iterable[dict],
    source: str = MISSAV_RELEASE_SOURCE,
    observed_at: str | None = None,
) -> int:
    values = _validated_items(
        items,
        source,
    )

    observed_at = (
        _text(
            observed_at
        )
        or utc_now()
    )

    with connection:
        for item in values:
            connection.execute(
                """
                INSERT INTO titles(
                    dvd_id,
                    title,
                    cover_url,
                    metadata_source,
                    first_seen_at,
                    last_seen_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(dvd_id)
                DO UPDATE SET
                    title =
                        CASE
                            WHEN
                                titles.metadata_source
                                IS NULL
                                OR
                                titles.metadata_source
                                =
                                excluded.metadata_source
                            THEN
                                COALESCE(
                                    excluded.title,
                                    titles.title
                                )
                            ELSE
                                titles.title
                        END,

                    cover_url =
                        CASE
                            WHEN
                                titles.metadata_source
                                IS NULL
                                OR
                                titles.metadata_source
                                =
                                excluded.metadata_source
                            THEN
                                COALESCE(
                                    excluded.cover_url,
                                    titles.cover_url
                                )
                            ELSE
                                titles.cover_url
                        END,

                    metadata_source =
                        COALESCE(
                            titles.metadata_source,
                            excluded.metadata_source
                        ),

                    first_seen_at =
                        COALESCE(
                            titles.first_seen_at,
                            excluded.first_seen_at
                        ),

                    last_seen_at =
                        excluded.last_seen_at
                """,
                (
                    item[
                        "dvd_id"
                    ],
                    item[
                        "title"
                    ],
                    item[
                        "cover_url"
                    ],
                    source,
                    observed_at,
                    observed_at,
                ),
            )

            connection.execute(
                """
                INSERT INTO latest_items(
                    source,
                    dvd_id,
                    source_url,
                    title,
                    cover_url,
                    first_seen_at,
                    last_seen_at,
                    first_position,
                    last_position
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(
                    source,
                    dvd_id
                )
                DO UPDATE SET
                    source_url =
                        excluded.source_url,

                    title =
                        COALESCE(
                            excluded.title,
                            latest_items.title
                        ),

                    cover_url =
                        COALESCE(
                            excluded.cover_url,
                            latest_items.cover_url
                        ),

                    last_seen_at =
                        excluded.last_seen_at,

                    last_position =
                        excluded.last_position
                """,
                (
                    source,
                    item[
                        "dvd_id"
                    ],
                    item[
                        "source_url"
                    ],
                    item[
                        "title"
                    ],
                    item[
                        "cover_url"
                    ],
                    observed_at,
                    observed_at,
                    item[
                        "position"
                    ],
                    item[
                        "position"
                    ],
                ),
            )

    return len(values)


def list_latest_items(
    connection: sqlite3.Connection,
    source: str = MISSAV_RELEASE_SOURCE,
    limit: int = 50,
) -> list[dict]:
    if (
        not isinstance(
            limit,
            int,
        )
        or limit < 1
        or limit > 500
    ):
        raise ValueError(
            "latest limit must "
            "be 1..500"
        )

    rows = connection.execute(
        """
        SELECT
            source,
            dvd_id,
            source_url,
            title,
            cover_url,
            first_seen_at,
            last_seen_at,
            first_position,
            last_position
        FROM latest_items
        WHERE source = ?
        ORDER BY
            last_seen_at DESC,
            last_position ASC,
            dvd_id ASC
        LIMIT ?
        """,
        (
            source,
            limit,
        ),
    ).fetchall()

    return [
        dict(row)
        for row in rows
    ]
