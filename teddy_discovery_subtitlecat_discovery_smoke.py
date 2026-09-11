"""Offline boundary checks; no live search, detail, or payload downloads."""
from dataclasses import FrozenInstanceError
from pathlib import Path
import re
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

import teddy_discovery_subtitlecat_discovery as discovery
from teddy_discovery_subtitle_external import (
    ExternalSubtitleValidationError, SubtitleCatDetailPage, SubtitleCatProvider,
)

DVD_ID = "ABC-123"
URL = discovery.build_search_url(DVD_ID)
DETAIL = "https://subtitlecat.com/subs/example/ABC-123.html"
HTML = '<html><a href="/subs/example/ABC-123.html">ABC-123</a></html>'


def parse(html=HTML, *, dvd_id=DVD_ID, status=200, final_url=None, body=None):
    return discovery.parse_search_response(
        dvd_id=dvd_id,
        response=discovery.SubtitleCatSearchResponse(
            status, final_url if final_url is not None else discovery.build_search_url(dvd_id),
            html.encode() if body is None else body,
        ),
    )


def raises(kind, callback):
    try:
        callback()
    except kind:
        return True
    return False


def main():
    passed = failed = 0

    def check(name, callback):
        nonlocal passed, failed
        try:
            assert callback()
        except Exception as error:
            failed += 1
            print(f"FAIL {name}: {type(error).__name__}: {error}")
        else:
            passed += 1
            print(f"PASS {name}")

    check("exact candidate", lambda: parse().candidates[0].detail_url == DETAIL)
    multiple = HTML + '<a href="/subs/other/local_abc-123_extra.html">local</a>'
    check("multiple candidates and generic prefix", lambda: len(parse(multiple).candidates) == 2)
    check("encoded href preserved", lambda: parse('<a href="/subs/test/%41BC%2D123.html">x</a>').candidates[0].detail_url.endswith('%41BC%2D123.html'))
    check("anchor text evidence", lambda: parse('<a href="/subs/test/opaque.html"><b>ABC-123</b></a>').found)
    check("search index load-more excluded", lambda: not parse('<a href="index.php?search=ABC-123">Load More ABC-123</a><a href="index.html">ABC-123</a>').found)
    check("unrelated and token boundaries", lambda: not parse('<a href="/subs/test/XABC-123.html">x</a><a href="/subs/test/ABC-1234.html">x</a><a href="/subs/test/DEF-456.html">x</a>').found)
    check("parent text not inherited", lambda: not parse('<div>ABC-123<a href="/subs/test/opaque.html">download</a></div>').found)
    check("deterministic dedupe and ordering", lambda: parse(multiple + HTML).candidates == parse('<a href="/subs/other/local_abc-123_extra.html">x</a>' + HTML).candidates)
    for name, href in [
        ("external host", "https://evil.test/ABC-123.html"),
        ("protocol relative external", "//evil.test/ABC-123.html"),
        ("credentials", "https://user@subtitlecat.com/ABC-123.html"),
        ("fragment", "/ABC-123.html#part"),
        ("empty fragment", "/ABC-123.html#"),
        ("unsafe href", "/ABC-123%0a.html"),
        ("malformed href", "https://[broken/ABC-123.html"),
        ("malformed escape", "/ABC-123%xx.html"),
        ("unsafe scheme", "javascript:ABC-123.html"),
        ("raw whitespace", " /ABC-123.html"),
        ("backslash", "/ABC-123\\file.html"),
    ]:
        check(name, lambda href=href: raises(discovery.SubtitleCatSearchError, lambda: parse(f'<a href="{href}">ABC-123</a>')))
    for name, html in [
        ("duplicate href attributes", '<a href="/ABC-123.html" href="/other.html">ABC-123</a>'),
        ("missing href", '<a>ABC-123</a>'),
        ("unclosed relevant anchor", '<a href="/ABC-123.html">ABC-123'),
        ("nested relevant anchor", '<a href="/ABC-123.html"><a href="/other.html">x</a>'),
    ]:
        check(name, lambda html=html: raises(discovery.SubtitleCatSearchError, lambda: parse(html)))
    check("empty no-match HTML", lambda: not parse('<html><body></body></html>').found)
    check("non HTML rejected", lambda: raises(discovery.SubtitleCatSearchError, lambda: parse('plain text')))
    for body in [b'\xff', b'<html>\x00</html>', 'text', b'x' * (discovery.MAX_SEARCH_HTML_BYTES + 1)]:
        check("invalid or oversized body", lambda body=body: raises(discovery.SubtitleCatSearchError, lambda: parse(body=body)))
    check("candidate bound", lambda: raises(discovery.SubtitleCatSearchError, lambda: parse(''.join(f'<a href="/subs/test/ABC-123_{i}.html">x</a>' for i in range(discovery.MAX_SEARCH_CANDIDATES + 1)))))
    for status in [301, 404, 500, True, '200']:
        check(f"status {status}", lambda status=status: raises(discovery.SubtitleCatSearchTransportError, lambda: parse(status=status)))
    for final_url in ["https://evil.test/index.php", URL + '#', URL.replace('https://', 'https://user@'), URL + '&page=2']:
        check("final URL rejected", lambda final_url=final_url: raises((discovery.SubtitleCatSearchError, discovery.SubtitleCatSearchTransportError), lambda: parse(final_url=final_url)))
    for timeout in [0, -1, float('inf'), float('nan'), True, '2', 10**1000]:
        check("invalid timeout", lambda timeout=timeout: raises(discovery.SubtitleCatSearchError, lambda: discovery.SubtitleCatDiscovery(timeout=timeout)))
    for dvd_id in ['', ' ABC-123', 'ABC/123', 'ABC\\123', None]:
        check("shared DVD-ID validation", lambda dvd_id=dvd_id: raises(ExternalSubtitleValidationError, lambda: discovery.build_search_url(dvd_id)))
    check("exact query encoding", lambda: discovery.build_search_url('AbC&+?#=한') == 'https://subtitlecat.com/index.php?search=AbC%26%2B%3F%23%3D%ED%95%9C')
    check("original ID retained", lambda: parse('<html></html>', dvd_id='aBc-123').dvd_id == 'aBc-123')

    def offline_fetch(request, timeout):
        assert isinstance(request, Request) and request.get_method() == 'GET'
        assert request.full_url == URL and request.data is None and timeout == 3.0
        assert request.get_header('User-agent') == discovery.SEARCH_USER_AGENT
        return discovery.SubtitleCatSearchResponse(200, URL, HTML.encode())

    check("injected fetch offline", lambda: discovery.SubtitleCatDiscovery(fetch=offline_fetch, timeout=3).discover(dvd_id=DVD_ID).found)
    for error in [TimeoutError(), URLError('offline'), HTTPError(URL, 500, 'error', {}, None)]:
        def bad_fetch(request, timeout, error=error):
            raise error
        check("transport failure wrapped", lambda: raises(discovery.SubtitleCatSearchTransportError, lambda: discovery.SubtitleCatDiscovery(fetch=bad_fetch).discover(dvd_id=DVD_ID)))
    check("fetch response type", lambda: raises(discovery.SubtitleCatSearchError, lambda: discovery.SubtitleCatDiscovery(fetch=lambda *args: b'html').discover(dvd_id=DVD_ID)))

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def getcode(self):
            return 200
        def geturl(self):
            return URL
        def read(self, size):
            assert size == discovery.MAX_SEARCH_HTML_BYTES + 1
            return HTML.encode()

    class Opener:
        def open(self, request, timeout):
            assert isinstance(request, Request)
            assert request.get_method() == 'GET' and timeout > 0
            assert request.full_url == URL and request.data is None
            assert request.get_header('User-agent') == discovery.SEARCH_USER_AGENT
            return Response()

    def bounded_default():
        with patch.object(discovery.urllib_request, 'build_opener', return_value=Opener()) as build:
            result = discovery.SubtitleCatDiscovery().discover(dvd_id=DVD_ID)
            handler = build.call_args.args[0]
            assert raises(discovery.SubtitleCatSearchTransportError, lambda: handler.redirect_request(Request(URL), None, 302, '', {}, 'https://evil.test/'))
            return result.found

    check("default GET MAX+1 and redirect handler", bounded_default)
    check("immutable result", lambda: raises(FrozenInstanceError, lambda: setattr(parse(), 'dvd_id', 'changed')))
    check("immutable candidate", lambda: raises(FrozenInstanceError, lambda: setattr(parse().candidates[0], 'detail_url', 'changed')))

    def provider_boundary():
        seen = []
        def detail_fetch(url):
            seen.append(url)
            return SubtitleCatDetailPage(final_url=url, html='<a href="original.ja.srt">Japanese</a>')
        provider = SubtitleCatProvider(fetch_detail=detail_fetch)
        provider.find_original_japanese_candidate(dvd_id=DVD_ID, detail_url=parse().candidates[0].detail_url)
        return seen == [DETAIL]

    check("existing provider exact detail boundary", provider_boundary)
    source = Path(discovery.__file__).read_text()
    check("no title or numeric subs hardcode", lambda: not re.search(r'JUR-750|/subs/\d+|ABC-123', source, re.I))
    print(f"SubtitleCat discovery smoke: PASS={passed} FAIL={failed}")
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
