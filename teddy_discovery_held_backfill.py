from __future__ import annotations

import sqlite3

from teddy_discovery_ids import parse_dvd_id
from teddy_discovery_javinfo import upsert_movie_metadata


DIRECT_ROUTE = "javdatabase-movie"
FALLBACK_ROUTE = "missav-en-movie"


def _text(value):
    if value is None:
        return None

    value = str(value).strip()
    return value or None


def collected_to_javinfo_payload(
    collected: dict,
) -> dict:
    if not isinstance(collected, dict):
        raise ValueError(
            "collected metadata must be object"
        )

    if collected.get("status") != "FOUND":
        raise ValueError(
            "only FOUND metadata may be written"
        )

    route = collected.get("route")

    if route not in {
        DIRECT_ROUTE,
        FALLBACK_ROUTE,
    }:
        raise ValueError(
            "unsupported metadata route"
        )

    dvd_id = _text(
        collected.get("dvd_id")
    )

    parsed = parse_dvd_id(
        dvd_id or ""
    )

    if parsed is None:
        raise ValueError(
            "invalid DVD-ID"
        )

    dvd_id = parsed.dvd_id

    item = collected.get("item")

    if not isinstance(item, dict):
        raise ValueError(
            "metadata item missing"
        )

    item_id = _text(
        item.get("dvd_id")
    )

    parsed_item = parse_dvd_id(
        item_id or ""
    )

    if (
        parsed_item is None
        or parsed_item.dvd_id != dvd_id
    ):
        raise ValueError(
            "DVD-ID mismatch"
        )

    title = _text(
        item.get("title")
    )

    release_date = _text(
        item.get("release_date")
    )

    studio = _text(
        item.get("studio")
    )

    source_url = _text(
        item.get("source_url")
    )

    idols = item.get("idols")
    genres = item.get("genres")
    cover_url = _text(
        item.get("cover_url")
    )

    if not title:
        raise ValueError(
            "title missing"
        )

    if not release_date:
        raise ValueError(
            "release date missing"
        )

    if (
        route == DIRECT_ROUTE
        and not studio
    ):
        raise ValueError(
            "direct metadata studio missing"
        )

    if not source_url:
        raise ValueError(
            "source URL missing"
        )

    if not isinstance(idols, list):
        raise ValueError(
            "idols must be list"
        )

    if not isinstance(genres, list):
        raise ValueError(
            "genres must be list"
        )

    if (
        route == DIRECT_ROUTE
        and not cover_url
    ):
        raise ValueError(
            "direct metadata cover missing"
        )

    result = {
        "dvdId": dvd_id,
        "titleEn": title,
        "releaseDate": release_date,
        "makers":
            (
                [studio]
                if studio
                else []
            ),
        "actresses": list(idols),
        "actors": [],
        "directors": [],
        "authors": [],
        "categories": list(genres),
        "sourceUrl": source_url,
    }

    if cover_url:
        result["jacketFullUrl"] = (
            cover_url
        )

    return {
        "source": route,
        "result": result,
    }


def apply_held_collected_metadata(
    connection: sqlite3.Connection,
    collected: dict,
) -> str:
    payload = (
        collected_to_javinfo_payload(
            collected
        )
    )

    return upsert_movie_metadata(
        connection,
        payload,
    )
