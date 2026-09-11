"""Offline proof for the explicit SubtitleCat-only proxy boundary."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.request import ProxyHandler, Request

import teddy_discovery_stage11_deployment as deployment
import teddy_discovery_subtitlecat_discovery as discovery
from teddy_discovery_alignment_acceptance import AlignmentAcceptancePolicy
from teddy_discovery_subtitle_external import (
    SubtitleCatDetailPage,
)
from teddy_discovery_subtitlecat_discovery import SubtitleCatSearchError


DVD_ID = "ABC-123"
PROXY = "http://127.0.0.1:58888"
SEARCH_URL = discovery.build_search_url(DVD_ID)
DETAIL_URL = "https://subtitlecat.com/subs/ABC-123.html"
PAYLOAD_URL = "https://subtitlecat.com/subs/original.ja.srt"
SEARCH_BODY = f'<html><a href="{DETAIL_URL}">{DVD_ID}</a></html>'.encode()
DETAIL_BODY = b'<html><a href="original.ja.srt">Japanese</a></html>'
PAYLOAD_BODY = b"1\n00:00:00,000 --> 00:00:00,100\n\xe6\x97\xa5\xe6\x9c\xac\xe8\xaa\x9e\n"


class _Response:
    def __init__(self, url: str, body: bytes):
        self.url = url
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def getcode(self):
        return 200

    def geturl(self):
        return self.url

    def read(self, limit):
        assert len(self.body) <= limit
        return self.body


class _Opener:
    def __init__(self, responses):
        self.responses = responses

    def open(self, request: Request, timeout):
        assert isinstance(request, Request)
        assert request.get_method() == "GET"
        assert request.data is None
        return _Response(request.full_url, self.responses[request.full_url])


def _assert_proxy_handlers(handlers):
    proxy_handlers = [
        handler for handler in handlers if isinstance(handler, ProxyHandler)
    ]
    assert len(proxy_handlers) == 1
    assert proxy_handlers[0].proxies == {
        "http": PROXY,
        "https": PROXY,
    }


def _assert_direct_handlers(handlers):
    assert not any(isinstance(handler, ProxyHandler) for handler in handlers)


def _search_smoke(proxy_url):
    builder_calls = []

    def build_opener(*handlers):
        builder_calls.append(handlers)
        return _Opener({SEARCH_URL: SEARCH_BODY})

    with patch.object(
        discovery.urllib_request,
        "build_opener",
        side_effect=build_opener,
    ):
        result = discovery.SubtitleCatDiscovery(
            timeout=3,
            proxy_url=proxy_url,
        ).discover(dvd_id=DVD_ID)

    assert result.candidates[0].detail_url == DETAIL_URL
    assert len(builder_calls) == 1
    if proxy_url is None:
        _assert_direct_handlers(builder_calls[0])
    else:
        _assert_proxy_handlers(builder_calls[0])


def _provider_smoke(proxy_url):
    builder_calls = []

    def build_opener(*handlers):
        builder_calls.append(handlers)
        return _Opener({
            DETAIL_URL: DETAIL_BODY,
            PAYLOAD_URL: PAYLOAD_BODY,
        })

    with patch.object(
        deployment.urllib_request,
        "build_opener",
        side_effect=build_opener,
    ):
        provider = deployment.build_subtitlecat_provider(
            timeout=3,
            proxy_url=proxy_url,
        )
        payload = provider.fetch_original_japanese_payload(
            dvd_id=DVD_ID,
            detail_url=DETAIL_URL,
        )

    assert payload.candidate.language == "ja"
    assert payload.parse().cues
    assert len(builder_calls) == 2
    for handlers in builder_calls:
        if proxy_url is None:
            _assert_direct_handlers(handlers)
        else:
            _assert_proxy_handlers(handlers)


def _config(proxy_url):
    return deployment.Stage11DeploymentConfig(
        nas_host="192.0.2.10",
        nas_user="nas-user",
        nas_key="/key",
        nas_known_hosts="/known-hosts",
        nas_library_root="/volume1/video/video2/JAV",
        asr_base_url="http://192.0.2.20:8091",
        request_timeout_seconds=1200,
        remote_host="192.0.2.30",
        remote_user="hermes-user",
        ssh_key="/hermes-key",
        known_hosts="/hermes-known-hosts",
        remote_task_root="/srv/hermes/stage11",
        subtitlecat_proxy_url=proxy_url,
    )


class _NoOpBridge:
    def ensure_task(self, remote_task):
        del remote_task

    def ensure_file(self, remote_path, payload):
        del remote_path, payload

    def read_regular(self, remote_path, *, max_bytes):
        del remote_path, max_bytes
        raise deployment.Stage11DeploymentTransportError("absent")

    def ensure_stateful_session(self, session_id):
        del session_id

    def get_session(self, session_id):
        del session_id
        return None

    def create_session(self, *, session_id, source, profile_name):
        del source, profile_name
        return session_id

    def get_messages(self, session_id, *, include_inactive=False):
        del session_id, include_inactive
        return []

    def launch_quality_review(self, command, *, remote_task, timeout):
        del command, remote_task, timeout
        return SimpleNamespace(returncode=0)


def _factory_isolation_smoke():
    deps = deployment.build_stage11_deployment_dependencies(
        _config(PROXY),
        acceptance_policy=AlignmentAcceptancePolicy(
            3, 3, 0.8, 100.0, 0, 0.9, 1.1
        ),
        residual_threshold_ms=100,
        holding_resolver=lambda title: {},
        remote_bridge=_NoOpBridge(),
        native_first_pass_run=lambda args: 0,
    )
    assert deps.config.subtitlecat_proxy_url == PROXY
    assert deps.discovery.proxy_url == PROXY
    assert not hasattr(deps.whisper, "proxy_url")
    assert not hasattr(deps.source_provider, "proxy_url")


def main():
    _search_smoke(None)
    print("PASS=PROXY_NONE_SEARCH_DIRECT_COMPATIBILITY")
    _search_smoke(PROXY)
    print("PASS=EXPLICIT_PROXY_SEARCH")
    _provider_smoke(None)
    print("PASS=PROXY_NONE_DETAIL_PAYLOAD_DIRECT_COMPATIBILITY")
    _provider_smoke(PROXY)
    print("PASS=EXPLICIT_PROXY_DETAIL_AND_PAYLOAD")

    for value in (
        "",
        "ftp://127.0.0.1:58888",
        "http://user@127.0.0.1:58888",
        "http://127.0.0.1:0",
        "http://127.0.0.1/path",
        "http://127.0.0.1:58888?query",
    ):
        try:
            discovery.SubtitleCatDiscovery(proxy_url=value)
        except SubtitleCatSearchError:
            pass
        else:
            raise AssertionError("malformed discovery proxy was accepted")
        try:
            deployment.build_subtitlecat_provider(proxy_url=value)
        except SubtitleCatSearchError:
            pass
        else:
            raise AssertionError("malformed provider proxy was accepted")
        try:
            _config(value)
        except deployment.Stage11DeploymentValidationError:
            pass
        else:
            raise AssertionError("malformed deployment proxy was accepted")
    print("PASS=MALFORMED_PROXY_FAIL_CLOSED")

    _factory_isolation_smoke()
    print("PASS=DEPLOYMENT_PROXY_ISOLATION")
    print("SUBTITLECAT_PROXY_SMOKE_PASS=6")
    print("SUBTITLECAT_PROXY_SMOKE_FAIL=0")


if __name__ == "__main__":
    main()
