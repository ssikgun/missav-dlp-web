from pathlib import Path
import json
import sqlite3
import socket
import socketserver
import threading
import tempfile
import xml.etree.ElementTree as ET

from teddy_discovery_media_metadata import (
    MAX_POSTER_BYTES,
    build_media_bundle,
    fetch_poster,
    load_media_metadata,
    make_poster_fetcher,
)
import teddy_discovery_media_metadata as media_metadata


class FakeResponse:
    def __init__(self, content_type, data):
        self.headers = {
            "Content-Type": content_type,
        }
        self.status = 200
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size=-1):
        return self.data if size < 0 else self.data[:size]


def proxy_fetcher_smoke():
    direct_calls = []
    opener_calls = []
    install_calls = []
    bypass_calls = []
    built_handlers = []
    payload = b"\xff\xd8\xfffixture"

    class FakeOpener:
        def __init__(self, handler, failure=None):
            self.handler = handler
            self.failure = failure

        def open(self, request, timeout):
            opener_calls.append((request, timeout))
            if self.failure is not None:
                raise self.failure
            original_host = request.host
            self.handler.proxy_open(
                request,
                "http://127.0.0.1:58888",
                request.type,
            )
            assert request.host == "127.0.0.1:58888"
            if request.type == "https":
                assert request._tunnel_host == original_host
            return FakeResponse("image/jpeg; charset=binary", payload)

    def fake_build_opener(handler):
        built_handlers.append(handler)
        return FakeOpener(handler)

    def forbidden_direct(*_args, **_kwargs):
        direct_calls.append(True)
        raise AssertionError("proxy mode attempted direct fetch")

    original_build_opener = media_metadata.urllib.request.build_opener
    original_urlopen = media_metadata.urllib.request.urlopen
    original_install_opener = media_metadata.urllib.request.install_opener
    original_proxy_bypass = media_metadata.urllib.request.proxy_bypass

    try:
        media_metadata.urllib.request.build_opener = fake_build_opener
        media_metadata.urllib.request.urlopen = forbidden_direct
        media_metadata.urllib.request.install_opener = (
            lambda opener: install_calls.append(opener)
        )
        media_metadata.urllib.request.proxy_bypass = (
            lambda host: bypass_calls.append(host)
            or True
        )

        assert make_poster_fetcher(None) is None
        proxy_fetcher = make_poster_fetcher(
            "http://127.0.0.1:58888"
        )
        assert callable(proxy_fetcher)
        assert len(built_handlers) == 1
        assert built_handlers[0].proxies == {
            "http": "http://127.0.0.1:58888",
            "https": "http://127.0.0.1:58888",
        }

        content_type, data = proxy_fetcher(
            "https://poster.example.invalid/image.jpg"
        )
        assert content_type == "image/jpeg"
        assert data == payload
        request, timeout = opener_calls[-1]
        assert request.full_url == (
            "https://poster.example.invalid/image.jpg"
        )
        assert request.get_header("User-agent") == (
            "Teddy-Downloader/Stage9"
        )
        assert request.get_header("Accept") == (
            "image/avif,image/webp,image/png,image/jpeg,image/*;q=0.8"
        )
        assert timeout == 20
        assert direct_calls == []
        assert install_calls == []
        assert bypass_calls == []

        # A failed explicit proxy request propagates and never falls back.
        def failing_build_opener(handler):
            built_handlers.append(handler)
            return FakeOpener(
                handler,
                OSError("proxy fixture failure"),
            )

        media_metadata.urllib.request.build_opener = (
            failing_build_opener
        )
        failing_fetcher = make_poster_fetcher(
            "http://127.0.0.1:58888"
        )
        try:
            failing_fetcher("https://poster.example.invalid/image.jpg")
        except OSError as exc:
            assert str(exc) == "proxy fixture failure"
        else:
            raise AssertionError("proxy failure did not propagate")
        assert direct_calls == []

        # Invalid proxy configuration fails before an opener/network is created.
        build_count = len(built_handlers)
        for invalid in (
            "http://proxy.example.invalid:8888",
            "https://127.0.0.1:58888",
            "http://user:pass@127.0.0.1:58888",
            "http://127.0.0.1:58888/path",
            "http://127.0.0.1:58888/?q=1",
            "http://127.0.0.1:58888?",
            "http://127.0.0.1:58888#",
            "http://127.0.0.1",
            "http://127.0.0.2:58888",
            "http://[::1]:58888",
        ):
            try:
                make_poster_fetcher(invalid)
            except ValueError as exc:
                assert invalid not in str(exc)
            else:
                raise AssertionError("malformed proxy accepted")
        assert len(built_handlers) == build_count

        # Direct mode keeps the old urllib request contract.
        direct_response = FakeResponse("image/webp; x=y", b"RIFF\x04\x00\x00\x00WEBPtest")
        direct_request_calls = []

        def fake_urlopen(request, timeout):
            direct_request_calls.append((request, timeout))
            return direct_response

        media_metadata.urllib.request.urlopen = fake_urlopen
        content_type, data = media_metadata._default_fetcher(
            "https://poster.example.invalid/direct.webp"
        )
        assert content_type == "image/webp"
        assert data.startswith(b"RIFF")
        direct_request, direct_timeout = direct_request_calls[0]
        assert direct_timeout == 20
        assert direct_request.get_header("User-agent") == (
            "Teddy-Downloader/Stage9"
        )
    finally:
        media_metadata.urllib.request.build_opener = original_build_opener
        media_metadata.urllib.request.urlopen = original_urlopen
        media_metadata.urllib.request.install_opener = original_install_opener
        media_metadata.urllib.request.proxy_bypass = original_proxy_bypass

    # Exercise urllib's real opener against a local CONNECT proxy. A simulated
    # no_proxy match must not bypass the explicit poster proxy.
    target_host = "poster.example.invalid"
    proxy_requests = []
    bypass_calls = []

    class ConnectProxyHandler(
        socketserver.StreamRequestHandler
    ):
        def handle(self):
            request_line = self.rfile.readline().decode(
                "ascii",
                errors="replace",
            ).strip()
            headers = []
            while True:
                line = self.rfile.readline()
                if not line or line in (b"\r\n", b"\n"):
                    break
                headers.append(line.decode("ascii", errors="replace").strip())
            proxy_requests.append((request_line, headers))
            self.wfile.write(
                b"HTTP/1.1 502 Proxy Fixture\r\n"
                b"Content-Length: 0\r\n"
                b"Connection: close\r\n\r\n"
            )

    class ConnectProxyServer(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    proxy_server = ConnectProxyServer(
        ("127.0.0.1", 0),
        ConnectProxyHandler,
    )
    proxy_thread = threading.Thread(
        target=proxy_server.serve_forever,
        daemon=True,
    )
    proxy_thread.start()
    proxy_port = proxy_server.server_address[1]
    original_proxy_bypass = media_metadata.urllib.request.proxy_bypass
    original_getaddrinfo = socket.getaddrinfo

    def forbidden_target_resolution(host, *args, **kwargs):
        if host == target_host:
            raise AssertionError("poster target was resolved directly")
        return original_getaddrinfo(host, *args, **kwargs)

    try:
        media_metadata.urllib.request.proxy_bypass = (
            lambda host: bypass_calls.append(host)
            or True
        )
        socket.getaddrinfo = forbidden_target_resolution
        local_fetcher = make_poster_fetcher(
            f"http://127.0.0.1:{proxy_port}"
        )
        try:
            local_fetcher(
                f"https://{target_host}/poster.webp"
            )
        except Exception:
            pass
        else:
            raise AssertionError("proxy fixture failure was not propagated")
    finally:
        socket.getaddrinfo = original_getaddrinfo
        media_metadata.urllib.request.proxy_bypass = original_proxy_bypass
        proxy_server.shutdown()
        proxy_server.server_close()
        proxy_thread.join(timeout=2)

    assert proxy_requests
    assert proxy_requests[0][0].startswith(
        f"CONNECT {target_host}:443 "
    )
    assert bypass_calls == []

    try:
        fetch_poster(
            "https://poster.example.invalid/unsupported",
            fetcher=lambda _url: ("application/octet-stream", b"not-image"),
        )
    except ValueError as exc:
        assert str(exc) == "unsupported poster format"
    else:
        raise AssertionError("unsupported poster type accepted")

    try:
        fetch_poster(
            "https://poster.example.invalid/oversized",
            fetcher=lambda _url: (
                "image/jpeg",
                b"x" * (MAX_POSTER_BYTES + 1),
            ),
        )
    except ValueError as exc:
        assert str(exc) == "poster too large"
    else:
        raise AssertionError("oversized poster accepted")


def main():
    with tempfile.TemporaryDirectory(
        prefix="teddy-stage9-media-"
    ) as temp:
        db_path = (
            Path(temp)
            / "test.sqlite3"
        )

        db = sqlite3.connect(
            db_path
        )

        db.executescript(
            """
            CREATE TABLE titles (
                dvd_id TEXT PRIMARY KEY,
                title TEXT,
                release_date TEXT,
                maker TEXT,
                cover_url TEXT,
                raw_metadata TEXT,
                metadata_source TEXT,
                first_seen_at TEXT,
                last_seen_at TEXT
            );

            CREATE TABLE genres (
                genre_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );

            CREATE TABLE title_genres (
                dvd_id TEXT NOT NULL,
                genre_id INTEGER NOT NULL,
                PRIMARY KEY (
                    dvd_id,
                    genre_id
                )
            );

            CREATE TABLE people (
                person_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );

            CREATE TABLE title_people (
                dvd_id TEXT NOT NULL,
                person_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                PRIMARY KEY (
                    dvd_id,
                    person_id,
                    role
                )
            );
            """
        )

        raw = json.dumps(
            {
                "item": {
                    "dvd_id": "ABC-123",
                    "title":
                        "Original English Title",
                }
            }
        )

        db.execute(
            """
            INSERT INTO titles (
                dvd_id,
                title,
                release_date,
                maker,
                cover_url,
                raw_metadata,
                metadata_source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ABC-123",
                "한국어 제목",
                "2026-08-28",
                "Test Studio",
                "https://example.invalid/"
                "poster.webp",
                raw,
                "fake-source",
            ),
        )

        db.executemany(
            """
            INSERT INTO genres (
                genre_id,
                name
            )
            VALUES (?, ?)
            """,
            [
                (1, "Drama"),
                (2, "Hi-Def"),
            ],
        )

        db.executemany(
            """
            INSERT INTO title_genres (
                dvd_id,
                genre_id
            )
            VALUES (?, ?)
            """,
            [
                ("ABC-123", 1),
                ("ABC-123", 2),
            ],
        )

        db.execute(
            """
            INSERT INTO people (
                person_id,
                name
            )
            VALUES (?, ?)
            """,
            (
                1,
                "Test Actress",
            ),
        )

        db.execute(
            """
            INSERT INTO title_people (
                dvd_id,
                person_id,
                role
            )
            VALUES (?, ?, ?)
            """,
            (
                "ABC-123",
                1,
                "unknown",
            ),
        )

        db.commit()
        db.close()

        metadata = (
            load_media_metadata(
                db_path,
                "abc-123",
            )
        )

        assert (
            metadata.dvd_id
            == "ABC-123"
        )

        assert (
            metadata.title
            == "한국어 제목"
        )

        assert (
            metadata.original_title
            == "Original English Title"
        )

        assert (
            metadata.genres
            == (
                "Drama",
                "Hi-Def",
            )
        )

        assert (
            metadata.people
            == (
                (
                    "Test Actress",
                    "unknown",
                ),
            )
        )

        calls = []

        def fake_fetcher(url):
            calls.append(url)

            data = (
                b"RIFF"
                + (4).to_bytes(
                    4,
                    "little",
                )
                + b"WEBP"
                + b"TEST"
            )

            return (
                "image/webp",
                data,
            )

        bundle = (
            build_media_bundle(
                db_path,
                "ABC-123",
                fetcher=fake_fetcher,
            )
        )

        assert (
            calls
            == [
                "https://example.invalid/"
                "poster.webp"
            ]
        )

        assert (
            bundle.nfo_filename
            == "ABC-123.nfo"
        )

        assert (
            bundle.poster.filename
            == "poster.webp"
        )

        root = ET.fromstring(
            bundle.nfo_data
        )

        assert (
            root.tag
            == "movie"
        )

        assert (
            root.findtext("title")
            == "한국어 제목"
        )

        assert (
            root.findtext(
                "originaltitle"
            )
            == "Original English Title"
        )

        assert (
            root.findtext("premiered")
            == "2026-08-28"
        )

        assert (
            root.findtext("year")
            == "2026"
        )

        assert (
            root.findtext("studio")
            == "Test Studio"
        )

        assert (
            [
                item.text
                for item
                in root.findall("genre")
            ]
            == [
                "Drama",
                "Hi-Def",
            ]
        )

        actors = root.findall(
            "actor"
        )

        assert len(actors) == 1

        assert (
            actors[0].findtext(
                "name"
            )
            == "Test Actress"
        )

        assert (
            actors[0].find(
                "role"
            )
            is None
        )

        unique = root.find(
            "uniqueid"
        )

        assert unique is not None

        assert (
            unique.text
            == "ABC-123"
        )

        assert (
            unique.attrib["type"]
            == "dvd_id"
        )

        db = sqlite3.connect(db_path)
        db.execute(
            "UPDATE titles SET cover_url = NULL WHERE dvd_id = ?",
            ("ABC-123",),
        )
        db.commit()
        db.close()
        missing_cover_fetches = []
        try:
            build_media_bundle(
                db_path,
                "ABC-123",
                fetcher=lambda url: missing_cover_fetches.append(url),
            )
        except ValueError as exc:
            assert str(exc) == "cover_url missing: ABC-123"
        else:
            raise AssertionError("missing cover URL was accepted")
        assert missing_cover_fetches == []

    proxy_fetcher_smoke()

    print(
        "STAGE9_MEDIA_METADATA_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
