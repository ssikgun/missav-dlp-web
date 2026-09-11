"""Bounded official search discovery; detail/JA/payload remain provider-owned.

Only the requested search page is collected (no pagination). Candidate order is
lexical URL order, never a ranking or a claim of subtitle correctness.
"""

from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
import math
import re
from urllib import request as urllib_request
from urllib.parse import unquote, urlencode, urljoin, urlsplit

from teddy_discovery_subtitle_external import (
    ExternalSubtitleValidationError,
    ExternalSubtitleTransportError,
    _validate_dvd_id,
)

SEARCH_ENDPOINT = "https://subtitlecat.com/index.php"
SEARCH_USER_AGENT = "Mozilla/5.0 Teddy-Downloader-SubtitleDiscovery/1.0"
# Generic resource budgets, independent of any title or observed response.
MAX_SEARCH_HTML_BYTES = 4 * 1024 * 1024
MAX_SEARCH_CANDIDATES = 128


class SubtitleCatSearchError(ExternalSubtitleValidationError):
    """Invalid search response, relevant evidence, or resource limit."""


class SubtitleCatSearchTransportError(ExternalSubtitleTransportError):
    """Search HTTP transport failed or redirected."""


@dataclass(frozen=True)
class SubtitleCatSearchResponse:
    status: int
    final_url: str
    body: bytes


@dataclass(frozen=True)
class SubtitleCatSearchCandidate:
    detail_url: str


@dataclass(frozen=True)
class SubtitleCatSearchResult:
    dvd_id: str
    candidates: tuple[SubtitleCatSearchCandidate, ...]

    @property
    def found(self) -> bool:
        return bool(self.candidates)


def build_search_url(dvd_id: str) -> str:
    return SEARCH_ENDPOINT + "?" + urlencode({"search": _validate_dvd_id(dvd_id)})


def _safe_url(value: str):
    if (type(value) is not str or not value
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)
            or any(c in value for c in "\\<>\"'#")
            or re.search(r"%(?![0-9a-fA-F]{2})", value)):
        raise SubtitleCatSearchError("malformed or unsafe URL")
    try:
        decoded = unquote(value, errors="strict")
        if any(ord(c) < 32 or ord(c) == 127 or c in "\\<>\"" for c in decoded):
            raise ValueError("unsafe decoded URL")
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or parsed.hostname != "subtitlecat.com"
                or parsed.username is not None or parsed.password is not None
                or parsed.port not in (None, 443)):
            raise ValueError("URL must stay on the official HTTPS host")
    except (ValueError, UnicodeError) as error:
        raise SubtitleCatSearchError("malformed or unsafe URL") from error
    return parsed


class _NoRedirectHandler(urllib_request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise SubtitleCatSearchTransportError("search redirect is not permitted")


def _fetch(request: urllib_request.Request, timeout: float) -> SubtitleCatSearchResponse:
    opener = urllib_request.build_opener(_NoRedirectHandler())
    with opener.open(request, timeout=timeout) as response:
        status, final_url = response.getcode(), response.geturl()
        if type(status) is not int or not 200 <= status < 300:
            raise SubtitleCatSearchTransportError("search HTTP status is not successful")
        if final_url != request.full_url:
            raise SubtitleCatSearchTransportError("search redirect is not permitted")
        return SubtitleCatSearchResponse(
            status, final_url, response.read(MAX_SEARCH_HTML_BYTES + 1)
        )


class _SearchParser(HTMLParser):
    def __init__(self, dvd_id: str, base_url: str):
        super().__init__(convert_charrefs=True)
        self.token = re.compile(r"(?<![^\W_])" + re.escape(dvd_id.casefold()) + r"(?![^\W_])")
        self.base_url = base_url
        self.anchor = None
        self.urls = set()
        self.saw_tag = False

    def matches(self, value: str) -> bool:
        return self.token.search(value.casefold()) is not None

    def handle_starttag(self, tag, attrs):
        self.saw_tag = True
        if tag == "a":
            if self.anchor is not None:
                self.finish(malformed=True)
            self.anchor = ([v for k, v in attrs if k == "href"], [])

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data):
        if self.anchor is not None:
            self.anchor[1].append(data)

    def handle_endtag(self, tag):
        if tag == "a":
            self.finish()

    def finish(self, malformed=False):
        if self.anchor is None:
            return
        hrefs, text = self.anchor
        self.anchor = None
        relevant = self.matches("".join(text))
        for href in hrefs:
            try:
                basename = unquote(urlsplit(href or "").path.rsplit("/", 1)[-1])
            except ValueError:
                basename = unquote(href or "")
            relevant = relevant or self.matches(basename)
        if not relevant:
            return
        if malformed or len(hrefs) != 1 or not hrefs[0]:
            raise SubtitleCatSearchError("malformed relevant anchor")
        href = hrefs[0]
        # Validate raw input before urljoin can strip controls or repair it.
        _safe_url(href if urlsplit(href).scheme else "https://subtitlecat.com/" + href)
        resolved = urljoin(self.base_url, href)
        parsed = _safe_url(resolved)
        if (parsed.query or not parsed.path.casefold().endswith(".html")
                or parsed.path.rsplit("/", 1)[-1].casefold() == "index.html"):
            return
        self.urls.add(resolved)
        if len(self.urls) > MAX_SEARCH_CANDIDATES:
            raise SubtitleCatSearchError("search candidate limit exceeded")


def parse_search_response(*, dvd_id: str, response: SubtitleCatSearchResponse) -> SubtitleCatSearchResult:
    """Validate one exact search response and collect actual anchor targets.

    Empty candidates is normal not-found. Unsafe relevant evidence raises;
    callers must not interpret an error as a complete or partial collection.
    """
    expected_url = build_search_url(dvd_id)
    if not isinstance(response, SubtitleCatSearchResponse):
        raise SubtitleCatSearchError("fetch must return SubtitleCatSearchResponse")
    if type(response.status) is not int or not 200 <= response.status < 300:
        raise SubtitleCatSearchTransportError("search HTTP status is not successful")
    _safe_url(response.final_url)
    if response.final_url != expected_url:
        raise SubtitleCatSearchTransportError("search final URL differs from request")
    if type(response.body) is not bytes or len(response.body) > MAX_SEARCH_HTML_BYTES:
        raise SubtitleCatSearchError("search body must be bounded bytes")
    try:
        html = response.body.decode("utf-8", errors="strict")
    except UnicodeError as error:
        raise SubtitleCatSearchError("search HTML must be UTF-8") from error
    if any((ord(c) < 32 and c not in "\t\r\n") or ord(c) == 127 for c in html):
        raise SubtitleCatSearchError("search HTML contains invalid text controls")
    parser = _SearchParser(dvd_id, response.final_url)
    try:
        parser.feed(html)
        parser.close()
        parser.finish(malformed=True)
    except (ValueError, UnicodeError) as error:
        raise SubtitleCatSearchError("invalid search HTML or relevant href") from error
    if not parser.saw_tag:
        raise SubtitleCatSearchError("search response is not HTML")
    return SubtitleCatSearchResult(dvd_id, tuple(
        SubtitleCatSearchCandidate(url) for url in sorted(parser.urls)
    ))


class SubtitleCatDiscovery:
    """GET-only search boundary. Inject fetch(Request, timeout) for offline use.

    Injected fetchers must also fail closed on redirects and bound their reads.
    Every returned response is revalidated here, including its exact final URL.
    Pass each candidate.detail_url to the existing SubtitleCatProvider; discovery
    neither chooses among candidates nor fetches detail pages or payloads.
    """

    def __init__(self, *, timeout: float = 20.0,
                 fetch: Callable = _fetch):
        try:
            valid = (not isinstance(timeout, bool) and isinstance(timeout, (int, float))
                     and math.isfinite(timeout) and timeout > 0)
        except OverflowError:
            valid = False
        if not valid:
            raise SubtitleCatSearchError("timeout must be positive and finite")
        if not callable(fetch):
            raise SubtitleCatSearchError("fetch must be callable")
        self.timeout = float(timeout)
        self.fetch = fetch

    def discover(self, *, dvd_id: str) -> SubtitleCatSearchResult:
        request = urllib_request.Request(
            build_search_url(dvd_id),
            headers={"User-Agent": SEARCH_USER_AGENT},
            method="GET",
        )
        try:
            response = self.fetch(request, self.timeout)
        except (SubtitleCatSearchError, SubtitleCatSearchTransportError):
            raise
        except Exception as error:
            raise SubtitleCatSearchTransportError("search request failed") from error
        return parse_search_response(dvd_id=dvd_id, response=response)
