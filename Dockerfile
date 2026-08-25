FROM python:3.10-slim

# 1. uv 바이너리 복사
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 2. 필수 패키지 설치
RUN apt-get update && \
    apt-get install -y ffmpeg curl bash && \
    rm -rf /var/lib/apt/lists/*

# 3. SpoofDPI 설치
RUN curl -fsSL https://raw.githubusercontent.com/xvzc/SpoofDPI/main/install.sh | bash -s linux-amd64

WORKDIR /app

# 4. 파이썬 패키지 고속 설치
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Teddy custom: 런타임 핵심 의존성 import를 빌드 단계에서 검증
RUN python -c "import typing_extensions; import curl_cffi; import yt_dlp; import flask; print('dependency smoke test: OK')"

# 5. 애플리케이션 복사
COPY . .

# Source + patch scripts must all parse before any build-time mutation.
RUN python -m py_compile \
    app.py teddy_entrypoint.py teddy_network.py teddy_vpn_health.py teddy_proxy_pool.py \
    teddy_routing.py teddy_duplicates.py teddy_logging.py teddy_storage.py teddy_browser_config.py teddy_auth.py \
    teddy_generic.py teddy_123av.py teddy_bootstrap.py teddy_verify_build.py teddy_hls_transport.py teddy_hls_benchmark.py \
    teddy_patch_vpn_health.py teddy_patch_proxy_pool.py teddy_patch_proxy_speed.py \
    teddy_patch_proxy_learning.py teddy_patch_proxy_task_sync.py \
    teddy_patch_task_claim_remux.py teddy_patch_proxy_singleflight.py \
    teddy_patch_proxy_engine_recovery.py teddy_patch_extraction_pause.py \
    teddy_patch_hls_transport.py teddy_patch_hls_pool_clients.py teddy_patch_hls_transport_bridge.py \
    teddy_patch_index.py teddy_patch_logs.py teddy_patch_storage.py teddy_patch_routing.py \
    teddy_patch_ytdlp_options.py teddy_patch_browser.py teddy_patch_split_storage.py teddy_patch_mobile.py teddy_patch_browser_runtime.py \
    teddy_patch_auth.py teddy_patch_pwa.py

# Existing deterministic boundary smoke tests.
RUN python -c "import teddy_network as n; assert n.is_recoverable_failure('HTTP 403'); assert n.is_recoverable_failure('HTTP Error 403: Forbidden'); assert n.is_recoverable_failure('operation timed out'); assert n.is_recoverable_failure('connection reset by peer'); assert n.is_recoverable_failure('curl: (35) TLS connect error'); assert not n.is_recoverable_failure('HTTP 404'); assert not n.is_recoverable_failure('HTTP 401'); print('adaptive network failure boundary smoke test: OK')"
RUN python -c "import teddy_vpn_health as h; s=h.snapshot(); assert s['auto_failure_threshold'] == 10; assert s['auto_failure_segment_threshold'] == 5; assert s['auto_failure_window_seconds'] == 60; print('cumulative VPN health monitor smoke test: OK')"
RUN python -c "import teddy_proxy_pool as p; assert p._normalize_proxy('8.8.8.8:8080') == 'http://8.8.8.8:8080'; assert not p._normalize_proxy('127.0.0.1:8080'); assert not p._normalize_proxy('192.168.1.10:3128'); assert p.MAX_CANDIDATES <= 64; print('free proxy pool safety smoke test: OK')"
RUN python -c "import teddy_routing as r; assert r.canonical_site('https://youtu.be/abc') == 'youtube.com'; assert r.canonical_site('https://www.youtube.com/watch?v=abc') == 'youtube.com'; assert r.canonical_site('https://missav123.com/ko/abc') == 'missav'; assert r.proxy_for_mode('direct') is None; r.set_proxy_provider(lambda: 'http://8.8.8.8:8080'); assert r.proxy_for_mode('proxy') == 'http://8.8.8.8:8080'; assert r.fallback_modes('direct') == ['proxy', 'vpn']; assert r.fallback_modes('proxy') == ['vpn']; assert r.fallback_modes('vpn') == []; print('adaptive three-route smoke test: OK')"
RUN python -c "import teddy_duplicates as d; assert d.duplicate_key('https://youtu.be/abc') == d.duplicate_key('https://www.youtube.com/watch?v=abc'); assert d.duplicate_key('https://missav123.com/ko/ABC') == d.duplicate_key('https://missav01.com/en/ABC'); assert d.duplicate_key('https://example.com/a#one') == d.duplicate_key('https://example.com/a#two'); assert d.duplicate_key('https://example.com/a?x=1') != d.duplicate_key('https://example.com/a?x=2'); print('duplicate queue guard smoke test: OK')"
RUN python -c "import teddy_logging as l; assert l._clean_for_viewer('\\x1b[31mRED\\x1b[0m') == 'RED'; assert l._clean_for_viewer(b'hello') == 'hello'; print('web log cleanup smoke test: OK')"
RUN python -c "import teddy_generic as g; C=type('C',(),{'settings':{'video_quality':'1080'}}); s=g._format_selector(C); assert 'height<=1080' in s; assert 'ext=mp4' in s; print('generic yt-dlp engine smoke test: OK')"
RUN python -c "import teddy_123av as a; assert a.Teddy123AVIE.suitable('https://123av.com/ko/v/jur-821'); assert not a.Teddy123AVIE.suitable('https://www.youtube.com/watch?v=test'); print('123AV extractor URL boundary smoke test: OK')"
RUN python -c "import teddy_storage as s; assert s.site_key_for_url('https://youtu.be/abc') == 'youtube'; assert s.site_key_for_url('https://www.youtube.com/watch?v=abc') == 'youtube'; assert s.site_key_for_url('https://missav123.com/ko/abc', custom=True) == 'missav'; assert s.site_key_for_url('https://vimeo.com/123') == 'vimeo'; print('site-aware storage smoke test: OK')"
RUN python -c "import teddy_hls_transport as h; assert h.HLS_WORKERS == 8; assert h.ALLOWED_HLS_WORKERS == (2, 4, 8, 12, 16, 20, 24); assert h.ALLOWED_HLS_WRITE_MODES == ('parts', 'ram'); assert h.ALLOWED_HLS_TRANSPORT_MODES == ('per-worker', 'async-pool'); assert h.HLS_POOL_CLIENTS == 24; assert h.ALLOWED_HLS_POOL_CLIENTS == (4, 8, 12, 16, 24); assert h.workers_from_settings({'hls_workers': 24}) == 24; assert h.write_mode_from_settings({'hls_write_mode': 'ram'}) == 'ram'; assert h.transport_mode_from_settings({'hls_transport_mode': 'async-pool'}) == 'async-pool'; assert h.transport_mode_from_settings({'hls_transport_mode': 'bad'}) == 'per-worker'; assert h.pool_clients_from_settings({}) == 24; assert h.pool_clients_from_settings({'hls_pool_clients': 4}) == 4; assert h.pool_clients_from_settings({'hls_pool_clients': 8}) == 8; assert h.pool_clients_from_settings({'hls_pool_clients': 12}) == 12; assert h.pool_clients_from_settings({'hls_pool_clients': 16}) == 16; assert h.pool_clients_from_settings({'hls_pool_clients': 24}) == 24; assert h.pool_clients_from_settings({'hls_pool_clients': 20}) == 24; assert callable(h.get); assert callable(h.invalidate); print('persistent/async HLS transport + pool-size benchmark smoke test: OK')"

# Teddy runtime patches. Keep each major stage separate so Actions exposes the exact failing patch.
RUN python teddy_patch_vpn_health.py
RUN python teddy_patch_proxy_pool.py
RUN python teddy_patch_proxy_speed.py
RUN sed -i 's/ensure_ready(core, wait_seconds=15)/ensure_ready(core, wait_seconds=35)/' teddy_bootstrap.py
RUN python teddy_patch_task_claim_remux.py
RUN python teddy_patch_proxy_learning.py
RUN python teddy_patch_proxy_task_sync.py
RUN python teddy_patch_proxy_engine_recovery.py
RUN python teddy_patch_extraction_pause.py
# Apply the final HLS implementation after all reliability/network patches so it
# owns the finished segment transport/scheduler without overlapping patch anchors.
RUN python teddy_patch_hls_transport.py
# Keep scheduler worker width separate from AsyncSession max_clients for A/B tests.
RUN python teddy_patch_hls_pool_clients.py
RUN grep -Fq "pool_clients = teddy_hls_transport.pool_clients_from_settings(core.settings)" teddy_entrypoint.py && \
    grep -Fq "core.tasks[task_id]['hls_pool_clients'] = pool_clients" teddy_entrypoint.py && \
    grep -Fq "worker_count=pool_clients" teddy_entrypoint.py
# The bootstrap recovery wrapper replaces reliability._fetch_segment at runtime.
# Keep its call signature in lockstep with the HLS transport benchmark kwargs.
RUN python teddy_patch_hls_transport_bridge.py
RUN grep -Fq "def _fetch_segment_with_network_recovery(task_id, seg_url, headers, transport_mode='per-worker', worker_count=None):" teddy_bootstrap.py && \
    test "$(grep -Fc 'transport_mode=transport_mode, worker_count=worker_count' teddy_bootstrap.py)" -eq 3

# Patched runtime must compile and satisfy explicit semantic markers.
RUN python -m py_compile \
    app.py teddy_entrypoint.py teddy_bootstrap.py teddy_vpn_health.py teddy_network.py \
    teddy_proxy_pool.py teddy_routing.py teddy_generic.py teddy_123av.py teddy_hls_transport.py teddy_hls_benchmark.py \
    teddy_browser_config.py teddy_auth.py teddy_patch_routing.py
RUN python teddy_verify_build.py runtime

# Teddy UI / file-manager / routing patches.
RUN python teddy_patch_index.py
RUN python teddy_patch_logs.py
RUN python teddy_patch_storage.py
RUN python teddy_patch_routing.py
RUN python teddy_patch_ytdlp_options.py
RUN python teddy_patch_browser.py
# Keep the proven LXC migration order: split-storage first, then browser runtime.
RUN python teddy_patch_split_storage.py
RUN python teddy_patch_browser_runtime.py
RUN python teddy_patch_auth.py
RUN grep -Fq 'data-page="browser"' templates/index.html && \
    grep -Fq 'id="page-browser"' templates/index.html && \
    grep -Fq '/static/teddy-browser.css' templates/index.html && \
    grep -Fq '/static/teddy-browser.js' templates/index.html && \
    grep -Fq '/api/browser/config' templates/teddy-browser.js && \
    grep -Fq 'teddy_browser_config.install(core)' teddy_bootstrap.py && \
    grep -Fq 'import teddy_auth' teddy_bootstrap.py && \
    grep -Fq 'teddy_auth.install(core)' teddy_bootstrap.py
RUN grep -Fq 'id="set-ytdlp-media-mode"' templates/index.html && \
    grep -Fq 'id="set-ytdlp-video-quality"' templates/index.html && \
    grep -Fq 'id="set-ytdlp-video-container"' templates/index.html && \
    grep -Fq 'id="set-ytdlp-audio-format"' templates/index.html && \
    grep -Fq 'id="set-ytdlp-subtitles"' templates/index.html

# Static asset injection remains deterministic and idempotent inside the image build.
RUN sed -i 's#</head>#<link rel="stylesheet" href="/static/teddy-theme.css"><link rel="stylesheet" href="/static/teddy-network.css"><link rel="stylesheet" href="/static/teddy-logs.css"><link rel="stylesheet" href="/static/teddy-routing.css"></head>#' templates/index.html && \
    sed -i 's#</body>#<script src="/static/teddy-reliability.js"></script><script src="/static/teddy-theme.js"></script><script src="/static/teddy-network.js"></script><script src="/static/teddy-logs.js"></script><script src="/static/teddy-routing.js"></script><script src="/static/teddy-proxy.js"></script><script src="/static/teddy-hls-benchmark.js"></script></body>#' templates/index.html && \
    sed -i 's#<link rel="stylesheet" href="/static/teddy-mobile.css">##' templates/index.html && \
    sed -i 's#</head>#<link rel="stylesheet" href="/static/teddy-mobile.css"></head>#' templates/index.html
RUN python -c "from pathlib import Path; t=Path('templates/index.html').read_text(); assert t.count('/static/teddy-mobile.css') == 1; assert t.rfind('/static/teddy-mobile.css') > t.rfind('/static/teddy-routing.css'); print('mobile stylesheet order: OK')"

# PWA phase 1: installable/home-screen metadata only. Deliberately no service worker/offline cache.
RUN python teddy_patch_pwa.py
RUN grep -Fq 'rel="manifest" href="/static/teddy-manifest.webmanifest"' templates/index.html && \
    grep -Fq 'rel="apple-touch-icon" sizes="180x180" href="/static/teddy-icon-180.png"' templates/index.html && \
    grep -Fq '"display": "standalone"' templates/teddy-manifest.webmanifest && \
    test -s templates/teddy-icon-180.png && \
    test -s templates/teddy-icon.svg

# Split-storage production guards. /downloads remains local work/state;
# TEDDY_FINAL_DIR points completed public files at the final filesystem.
RUN grep -Fq "TEDDY_FINAL_DIR" teddy_storage.py && \
    grep -Fq "local_result_path" teddy_generic.py && \
    grep -Fq "local_result_path" teddy_entrypoint.py && \
    grep -Fq "error_kind') == 'storage'" teddy_bootstrap.py && \
    grep -Fq "Final directory:" teddy_bootstrap.py

RUN python -m py_compile \
    teddy_bootstrap.py teddy_browser_config.py teddy_auth.py teddy_storage.py \
    teddy_generic.py teddy_123av.py teddy_entrypoint.py teddy_patch_pwa.py
RUN python teddy_verify_build.py final

# 6. 폴더 생성 및 포트 노출
RUN mkdir -p /downloads /final
EXPOSE 5000

# 7. Teddy 안정성 + Direct/Proxy/VPN 적응형 라우팅 + 웹 로그 + 범용 yt-dlp 실행
CMD ["python", "teddy_bootstrap.py"]
