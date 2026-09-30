from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import ipaddress
import json
import re
import sqlite3
from urllib.parse import urlsplit
import urllib.request
import xml.etree.ElementTree as ET


DVD_ID_RE = re.compile(
    r"^[A-Z0-9]+(?:-[A-Z0-9]+)+$"
)

MAX_POSTER_BYTES = 25 * 1024 * 1024


@dataclass(frozen=True)
class MediaMetadata:
    dvd_id: str
    title: str
    original_title: str
    release_date: str
    maker: str
    cover_url: str
    metadata_source: str
    genres: tuple[str, ...]
    people: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class PosterPayload:
    filename: str
    content_type: str
    data: bytes


@dataclass(frozen=True)
class MediaBundle:
    dvd_id: str
    nfo_filename: str
    nfo_data: bytes
    poster: PosterPayload


def _normalize_dvd_id(value: str) -> str:
    dvd_id = str(value or "").strip().upper()

    if not DVD_ID_RE.fullmatch(dvd_id):
        raise ValueError(
            "invalid dvd_id"
        )

    return dvd_id


def _extract_original_title(
    raw_metadata: str,
) -> str:
    if not raw_metadata:
        return ""

    try:
        payload = json.loads(raw_metadata)
    except Exception:
        return ""

    if not isinstance(payload, dict):
        return ""

    item = payload.get("item")

    if isinstance(item, dict):
        value = item.get("title")

        if value:
            return str(value).strip()

    return ""


def load_media_metadata(
    db_path: str | Path,
    dvd_id: str,
) -> MediaMetadata:
    dvd_id = _normalize_dvd_id(
        dvd_id
    )

    path = Path(db_path)

    db = sqlite3.connect(
        "file:"
        + str(path)
        + "?mode=ro",
        uri=True,
    )

    db.row_factory = sqlite3.Row

    try:
        row = db.execute(
            """
            SELECT
                dvd_id,
                title,
                release_date,
                maker,
                cover_url,
                raw_metadata,
                metadata_source
            FROM titles
            WHERE dvd_id = ?
            """,
            (dvd_id,),
        ).fetchone()

        if row is None:
            raise LookupError(
                "metadata not found: "
                + dvd_id
            )

        genres = tuple(
            str(item["name"]).strip()
            for item in db.execute(
                """
                SELECT DISTINCT g.name
                FROM title_genres tg
                JOIN genres g
                  ON g.genre_id = tg.genre_id
                WHERE tg.dvd_id = ?
                ORDER BY g.name COLLATE NOCASE
                """,
                (dvd_id,),
            )
            if str(
                item["name"] or ""
            ).strip()
        )

        people = tuple(
            (
                str(item["name"]).strip(),
                str(
                    item["role"] or "unknown"
                ).strip(),
            )
            for item in db.execute(
                """
                SELECT DISTINCT
                    p.name,
                    tp.role
                FROM title_people tp
                JOIN people p
                  ON p.person_id = tp.person_id
                WHERE tp.dvd_id = ?
                ORDER BY p.name COLLATE NOCASE
                """,
                (dvd_id,),
            )
            if str(
                item["name"] or ""
            ).strip()
        )

        title = str(
            row["title"] or ""
        ).strip()

        if not title:
            raise ValueError(
                "title missing: "
                + dvd_id
            )

        release_date = str(
            row["release_date"] or ""
        ).strip()

        maker = str(
            row["maker"] or ""
        ).strip()

        cover_url = str(
            row["cover_url"] or ""
        ).strip()

        metadata_source = str(
            row["metadata_source"] or ""
        ).strip()

        original_title = (
            _extract_original_title(
                str(
                    row["raw_metadata"]
                    or ""
                )
            )
        )

        return MediaMetadata(
            dvd_id=dvd_id,
            title=title,
            original_title=(
                original_title
                if original_title
                != title
                else ""
            ),
            release_date=release_date,
            maker=maker,
            cover_url=cover_url,
            metadata_source=(
                metadata_source
            ),
            genres=genres,
            people=people,
        )

    finally:
        db.close()


def build_nfo_bytes(
    metadata: MediaMetadata,
) -> bytes:
    root = ET.Element(
        "movie"
    )

    ET.SubElement(
        root,
        "title",
    ).text = metadata.title

    if metadata.original_title:
        ET.SubElement(
            root,
            "originaltitle",
        ).text = (
            metadata.original_title
        )

    ET.SubElement(
        root,
        "id",
    ).text = metadata.dvd_id

    unique = ET.SubElement(
        root,
        "uniqueid",
        {
            "type": "dvd_id",
            "default": "true",
        },
    )

    unique.text = metadata.dvd_id

    if metadata.release_date:
        ET.SubElement(
            root,
            "premiered",
        ).text = (
            metadata.release_date
        )

        year = (
            metadata.release_date[:4]
        )

        if (
            len(year) == 4
            and year.isdigit()
        ):
            ET.SubElement(
                root,
                "year",
            ).text = year

    if metadata.maker:
        ET.SubElement(
            root,
            "studio",
        ).text = metadata.maker

    for genre in metadata.genres:
        ET.SubElement(
            root,
            "genre",
        ).text = genre

    for name, role in metadata.people:
        actor = ET.SubElement(
            root,
            "actor",
        )

        ET.SubElement(
            actor,
            "name",
        ).text = name

        if (
            role
            and role.lower()
            != "unknown"
        ):
            ET.SubElement(
                actor,
                "role",
            ).text = role

    if metadata.metadata_source:
        ET.SubElement(
            root,
            "tag",
        ).text = (
            "metadata-source:"
            + metadata.metadata_source
        )

    ET.indent(
        root,
        space="  ",
    )

    return ET.tostring(
        root,
        encoding="utf-8",
        xml_declaration=True,
    )


def _fetch_response(
    url: str,
    *,
    opener=None,
) -> tuple[str, bytes]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent":
                "Teddy-Downloader/Stage9",
            "Accept":
                "image/avif,image/webp,"
                "image/png,image/jpeg,"
                "image/*;q=0.8",
        },
    )

    if opener is None:
        response = urllib.request.urlopen(
            request,
            timeout=20,
        )
    else:
        response = opener.open(
            request,
            timeout=20,
        )

    with response:
        content_type = str(
            response.headers.get(
                "Content-Type",
                "",
            )
        ).split(
            ";",
            1,
        )[0].strip().lower()

        data = response.read(
            MAX_POSTER_BYTES + 1
        )

    return content_type, data


def _validate_poster_proxy_url(
    proxy_url: str,
) -> str:
    if not isinstance(proxy_url, str):
        raise ValueError(
            "media poster proxy URL must be a loopback HTTP URL"
        )

    value = proxy_url.strip()

    if not value or value != proxy_url:
        raise ValueError(
            "media poster proxy URL must be a loopback HTTP URL"
        )

    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError(
            "media poster proxy URL must be a loopback HTTP URL"
        ) from exc

    if (
        parsed.scheme != "http"
        or hostname is None
        or "@" in parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or "?" in value
        or "#" in value
        or port is None
        or not 1 <= port <= 65535
    ):
        raise ValueError(
            "media poster proxy URL must be a loopback HTTP URL"
        )

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError as exc:
        raise ValueError(
            "media poster proxy URL must use 127.0.0.1"
        ) from exc

    if address != ipaddress.IPv4Address("127.0.0.1"):
        raise ValueError(
            "media poster proxy URL must use 127.0.0.1"
        )

    return value


class _PosterOnlyProxyHandler(
    urllib.request.ProxyHandler
):
    def proxy_open(
        self,
        request,
        proxy,
        _proxy_protocol,
    ):
        # urllib's standard ProxyHandler may bypass configured proxies when
        # HTTP(S)_PROXY bypass settings match the target. Poster mode must be
        # proxy-only, so apply the explicit proxy without consulting bypass env.
        original_type = request.type
        parsed_proxy = urlsplit(proxy)
        proxy_type = parsed_proxy.scheme
        proxy_host = parsed_proxy.netloc
        request.set_proxy(
            proxy_host,
            proxy_type,
        )

        if (
            original_type == proxy_type
            or original_type == "https"
        ):
            return None

        return self.parent.open(
            request,
            timeout=request.timeout,
        )


def make_poster_fetcher(
    proxy_url: str | None = None,
):
    """Build a fetcher scoped to poster requests only.

    An omitted proxy preserves the legacy direct urllib behavior. A configured
    proxy is validated as a host-loopback HTTP endpoint and is used exclusively
    for this fetcher; failures are allowed to propagate without direct fallback.
    """
    if proxy_url is None:
        return None

    validated_url = _validate_poster_proxy_url(
        proxy_url
    )
    proxy_handler = _PosterOnlyProxyHandler(
        {
            "http": validated_url,
            "https": validated_url,
        }
    )
    opener = urllib.request.build_opener(
        proxy_handler
    )

    def fetcher(
        url: str,
    ) -> tuple[str, bytes]:
        return _fetch_response(
            url,
            opener=opener,
        )

    return fetcher


def _default_fetcher(
    url: str,
) -> tuple[str, bytes]:
    return _fetch_response(url)


def _detect_image_extension(
    content_type: str,
    data: bytes,
) -> str:
    ct = (
        content_type
        or ""
    ).lower()

    if (
        ct == "image/jpeg"
        or data.startswith(
            b"\xff\xd8\xff"
        )
    ):
        return ".jpg"

    if (
        ct == "image/png"
        or data.startswith(
            b"\x89PNG\r\n\x1a\n"
        )
    ):
        return ".png"

    if (
        ct == "image/webp"
        or (
            len(data) >= 12
            and data[:4] == b"RIFF"
            and data[8:12] == b"WEBP"
        )
    ):
        return ".webp"

    raise ValueError(
        "unsupported poster format"
    )


def fetch_poster(
    url: str,
    *,
    fetcher=None,
) -> PosterPayload:
    url = str(
        url or ""
    ).strip()

    if not (
        url.startswith("https://")
        or url.startswith("http://")
    ):
        raise ValueError(
            "invalid poster URL"
        )

    if fetcher is None:
        fetcher = _default_fetcher

    content_type, data = fetcher(
        url
    )

    if not isinstance(
        data,
        (bytes, bytearray),
    ):
        raise TypeError(
            "poster payload must be bytes"
        )

    data = bytes(data)

    if not data:
        raise ValueError(
            "empty poster"
        )

    if len(data) > MAX_POSTER_BYTES:
        raise ValueError(
            "poster too large"
        )

    extension = (
        _detect_image_extension(
            str(content_type or ""),
            data,
        )
    )

    return PosterPayload(
        filename=(
            "poster" + extension
        ),
        content_type=str(
            content_type or ""
        ),
        data=data,
    )


def build_media_bundle(
    db_path: str | Path,
    dvd_id: str,
    *,
    fetcher=None,
) -> MediaBundle:
    metadata = load_media_metadata(
        db_path,
        dvd_id,
    )

    if not metadata.cover_url:
        raise ValueError(
            "cover_url missing: "
            + metadata.dvd_id
        )

    nfo = build_nfo_bytes(
        metadata
    )

    poster = fetch_poster(
        metadata.cover_url,
        fetcher=fetcher,
    )

    return MediaBundle(
        dvd_id=metadata.dvd_id,
        nfo_filename=(
            metadata.dvd_id
            + ".nfo"
        ),
        nfo_data=nfo,
        poster=poster,
    )
