"""Fail-closed, offline-testable MissAV page thumbnail candidate.

The caller must supply an already verified work URL and a proxy-only fetcher.
No default transport, Jellyfin action or production wiring is provided here.
The separate approved template candidate does not establish page provenance.
"""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
import re
import hashlib
import hmac

from teddy_discovery_media_metadata import MAX_POSTER_BYTES, _detect_image_extension, _normalize_dvd_id

MAX_PAGE_BYTES = 2 * 1024 * 1024
SITE_HOSTS = frozenset({'missav123.com'})


@dataclass(frozen=True)
class Thumbnail:
    filename: str
    content_type: str
    data: bytes
    page_url: str
    image_url: str


def _url(value: str, hosts: frozenset[str]):
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError('URL_INVALID')
    try:
        value.encode('ascii')
        parsed = urlsplit(value)
        port = parsed.port
    except (UnicodeError, ValueError) as exc:
        raise ValueError('URL_INVALID') from exc
    if (parsed.scheme != 'https' or parsed.hostname not in hosts or port not in (None, 443)
            or parsed.username is not None or parsed.password is not None
            or parsed.fragment or any(ord(c) <= 32 or ord(c) == 127 for c in value)
            or re.search(r'%(?![0-9A-Fa-f]{2})', value)):
        raise ValueError('URL_UNTRUSTED')
    return parsed


class _Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.urls = []
        self.images = []
        self.twitter_images = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag.lower() == 'meta':
            prop = (attrs.get('property') or attrs.get('name') or '').strip().lower()
            if prop == 'og:url':
                self.urls.append(attrs.get('content'))
            elif prop == 'og:image':
                self.images.append(attrs.get('content'))
            elif prop == 'twitter:image':
                self.twitter_images.append(attrs.get('content'))
        elif tag.lower() == 'link' and 'canonical' in (attrs.get('rel') or '').lower().split():
            self.urls.append(attrs.get('href'))


def extract_thumbnail(*, dvd_id, page_url, fetcher):
    """Return a thumbnail from a verified page or raise ValueError.

    fetcher(url, max_bytes) must enforce the approved proxy and return
    (status, final_url, content_type, bytes). Redirects fail closed.
    """
    dvd_id = _normalize_dvd_id(dvd_id)
    if not callable(fetcher):
        raise ValueError('PROXY_FETCHER_REQUIRED')
    page = _url(page_url, SITE_HOSTS)
    parts = page.path.strip('/').split('/')
    if len(parts) != 2 or parts[0] != 'ko' or parts[1].upper() != dvd_id or page.query:
        raise ValueError('PAGE_IDENTITY_INVALID')
    status, final, content_type, data = fetcher(page_url, MAX_PAGE_BYTES)
    if status != 200 or final != page_url:
        raise ValueError('PAGE_UNAVAILABLE_OR_REDIRECTED')
    if str(content_type).split(';', 1)[0].lower().strip() != 'text/html' or not isinstance(data, bytes) or not 0 < len(data) <= MAX_PAGE_BYTES:
        raise ValueError('PAGE_RESPONSE_INVALID')
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ValueError('PAGE_ENCODING_INVALID') from exc
    parser = _Page()
    parser.feed(text)
    if not parser.urls or len(parser.images) != 1 or not parser.images[0]:
        raise ValueError('PAGE_PROVENANCE_MISSING')
    if any(urljoin(page_url, value or '') != page_url for value in parser.urls):
        raise ValueError('PAGE_PROVENANCE_MISMATCH')
    image_url = urljoin(page_url, parser.images[0])
    if any(not value or urljoin(page_url, value) != image_url for value in parser.twitter_images):
        raise ValueError('IMAGE_METADATA_CONFLICT')
    image = _url(image_url, frozenset({page.hostname, 'fourhoi.com'}))
    if image.hostname == 'fourhoi.com' and (image.query or image.path.lower() != '/' + dvd_id.lower() + '/cover-n.jpg'):
        raise ValueError('IMAGE_IDENTITY_INVALID')
    status, final, content_type, data = fetcher(image_url, MAX_POSTER_BYTES)
    if status != 200 or final != image_url:
        raise ValueError('IMAGE_UNAVAILABLE_OR_REDIRECTED')
    mime = str(content_type).split(';', 1)[0].lower().strip()
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_POSTER_BYTES:
        raise ValueError('IMAGE_SIZE_INVALID')
    valid = ((mime == 'image/jpeg' and data.startswith(b'\xff\xd8\xff')) or
             (mime == 'image/png' and data.startswith(b'\x89PNG\r\n\x1a\n')) or
             (mime == 'image/webp' and len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP'))
    if not valid:
        raise ValueError('IMAGE_FORMAT_INVALID')
    ext = _detect_image_extension(mime, data)
    return Thumbnail('thumb' + ext, mime, data, page_url, image_url)


def store_injected_thumbnail(*, dvd_id, video_relative, page_url, fetcher, file_station, official_poster_verified):
    """Explicit injection only; no default transport or production pipeline wiring.

    The caller must independently establish that this is a preview and whether
    an authentic poster exists. Unknown poster status must not cause a write.
    """
    dvd_id = _normalize_dvd_id(dvd_id)
    if official_poster_verified is True:
        return {'status': 'POSTER_PRESENT'}
    if official_poster_verified is not False:
        raise ValueError('POSTER_STATUS_UNKNOWN')
    if page_url is None:
        return {'status': 'PENDING'}
    thumbnail = extract_thumbnail(dvd_id=dvd_id, page_url=page_url, fetcher=fetcher)
    return file_station.create_thumbnail(dvd_id=dvd_id, video_relative=video_relative,
        content_type=thumbnail.content_type, data=thumbnail.data)


def candidate_thumbnail_url(dvd_id):
    """A permitted candidate only; does not prove image or page identity."""
    return 'https://fourhoi.com/' + _normalize_dvd_id(dvd_id).lower() + '/cover-n.jpg'


def make_candidate_proxy_fetcher(proxy_url):
    """Strictly bounded transport through the configured loopback proxy."""
    import urllib.request
    from teddy_discovery_media_metadata import _PosterOnlyProxyHandler, _validate_poster_proxy_url

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    proxy = _validate_poster_proxy_url(proxy_url)
    opener = urllib.request.build_opener(
        _PosterOnlyProxyHandler({'http': proxy, 'https': proxy}), NoRedirect())

    def fetch(url, maximum):
        parsed = _url(url, frozenset({'fourhoi.com'}))
        parts = parsed.path.split('/')
        if (len(parts) != 3 or parsed.query or parsed.netloc != 'fourhoi.com'
                or url != candidate_thumbnail_url(parts[1]) or maximum != MAX_POSTER_BYTES):
            raise ValueError('CANDIDATE_URL_INVALID')
        request = urllib.request.Request(url, headers={'Accept': 'image/jpeg'})
        with opener.open(request, timeout=20) as response:
            return (response.status, response.geturl(), response.headers.get('Content-Type', ''),
                    response.read(MAX_POSTER_BYTES + 1))
    return fetch


def store_candidate_thumbnail(*, dvd_id, video_relative, fetcher, file_station, official_poster_verified):
    """Store explicit template candidate; neither page identity nor decoding is claimed."""
    url = candidate_thumbnail_url(dvd_id)
    if official_poster_verified is True:
        return {'status': 'POSTER_PRESENT'}
    if official_poster_verified is not False:
        raise ValueError('POSTER_STATUS_UNKNOWN')
    if not callable(fetcher):
        raise ValueError('PROXY_FETCHER_REQUIRED')
    try:
        status, final, content_type, data = fetcher(url, MAX_POSTER_BYTES)
    except Exception:
        return {'status': 'PENDING', 'error': 'CANDIDATE_FETCH_FAILED'}
    if (status != 200 or final != url or str(content_type).split(';', 1)[0].strip().lower() != 'image/jpeg'
            or not isinstance(data, bytes) or not 4 <= len(data) <= MAX_POSTER_BYTES
            or not data.startswith(b'\xff\xd8\xff') or not data.endswith(b'\xff\xd9')):
        return {'status': 'PENDING', 'error': 'CANDIDATE_RESPONSE_INVALID'}
    return file_station.create_thumbnail(dvd_id=_normalize_dvd_id(dvd_id), video_relative=video_relative,
        content_type='image/jpeg', data=data)


def one_shot_verified_fetch(fetch, *, exact_url, expected_size, expected_sha256):
    if not callable(fetch) or not isinstance(exact_url, str) or not isinstance(expected_size, int) or expected_size <= 0:
        raise ValueError('INVALID_GATE_CONFIG')
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64 or any(c not in '0123456789abcdef' for c in expected_sha256):
        raise ValueError('INVALID_GATE_HASH')
    used = False
    def guarded(url, maximum):
        nonlocal used
        if used or url != exact_url or maximum < expected_size:
            raise ValueError('ONE_SHOT_OR_TARGET_MISMATCH')
        used = True
        status, final, content_type, data = fetch(url, maximum)
        if (status != 200 or final != exact_url or str(content_type).split(';', 1)[0].strip().lower() != 'image/jpeg'
                or not isinstance(data, bytes) or len(data) != expected_size
                or not hmac.compare_digest(hashlib.sha256(data).hexdigest(), expected_sha256)):
            raise ValueError('CANDIDATE_IDENTITY_MISMATCH')
        return status, final, content_type, data
    return guarded
