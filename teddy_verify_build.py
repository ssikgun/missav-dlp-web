import argparse
from pathlib import Path


def require(path, needle, label=None):
    text = Path(path).read_text(encoding='utf-8')
    if needle not in text:
        raise SystemExit(f"build verify failed: {label or needle!r} missing from {path}")


def forbid(path, needle, label=None):
    text = Path(path).read_text(encoding='utf-8')
    if needle in text:
        raise SystemExit(f"build verify failed: forbidden {label or needle!r} present in {path}")


def verify_runtime():
    import teddy_generic as g
    import teddy_hls_transport as h
    import teddy_proxy_pool as p

    assert h.HLS_WORKERS == 8
    assert h.ALLOWED_HLS_TRANSPORT_MODES == ('per-worker', 'async-pool')
    assert h.HLS_TRANSPORT_MODE == 'per-worker'
    assert h.HLS_POOL_CLIENTS == 24
    assert h.ALLOWED_HLS_POOL_CLIENTS == (4, 8, 12, 16, 24)
    assert h.pool_clients_from_settings({}) == 24
    assert h.pool_clients_from_settings({'hls_pool_clients': 12}) == 12
    assert h.pool_clients_from_settings({'hls_pool_clients': 20}) == 24
    assert h.HLS_HTTP_VERSION == 'auto'
    assert h.ALLOWED_HLS_HTTP_VERSIONS == ('auto', 'v1')
    assert h.http_version_from_settings({}) == 'auto'
    assert h.http_version_from_settings({'hls_http_version': 'v1'}) == 'v1'
    assert h.http_version_from_settings({'hls_http_version': 'bad'}) == 'auto'
    assert p.BANDWIDTH_TEST_BYTES == 512 * 1024
    assert p.BANDWIDTH_TEST_LIMIT <= 8
    assert p.BANDWIDTH_TEST_WORKERS <= 4
    assert 'speed.cloudflare.com/__down' in p.BANDWIDTH_URL

    ytdlp_defaults = g.normalize_ytdlp_options({})
    assert ytdlp_defaults == {
        'media_mode': 'video',
        'quality': 'best',
        'video_container': 'mp4',
        'audio_format': 'm4a',
        'subtitles': 'off',
    }
    ytdlp_custom = g.normalize_ytdlp_options({
        'yt_dlp_media_mode': 'audio',
        'yt_dlp_video_quality': '1080',
        'yt_dlp_video_container': 'mkv',
        'yt_dlp_audio_format': 'mp3',
        'yt_dlp_subtitles': 'ko_en',
    })
    assert ytdlp_custom['media_mode'] == 'audio'
    assert ytdlp_custom['quality'] == '1080'
    assert ytdlp_custom['video_container'] == 'mkv'
    assert ytdlp_custom['audio_format'] == 'mp3'
    assert ytdlp_custom['subtitles'] == 'ko_en'
    assert g.normalize_ytdlp_options({'yt_dlp_audio_format': 'flac'})['audio_format'] == 'm4a'
    fake_core = type('C', (), {'settings': {'yt_dlp_video_quality': '1080', 'yt_dlp_video_container': 'mp4'}})
    selector = g._format_selector(fake_core)
    assert 'height<=1080' in selector
    assert 'ext=mp4' in selector
    audio_opts = {'format': 'ba/b'}
    g._apply_media_options(audio_opts, ytdlp_custom)
    assert audio_opts['postprocessors'][0]['key'] == 'FFmpegExtractAudio'
    assert audio_opts['postprocessors'][0]['preferredcodec'] == 'mp3'

    proxy = 'http://8.8.8.8:8080'
    p._state['performance'][proxy] = {
        'learned_speed_bps': 3_000_000,
        'transfer_samples': 4,
        'task_success_count': 2,
        'failure_streak': 0,
    }
    learned = p._apply_learned_stats({
        'proxy': proxy,
        'latency_ms': 900,
        'speed_bps': 100_000,
    })
    unlearned = {
        'proxy': 'http://1.1.1.1:8080',
        'latency_ms': 100,
        'speed_bps': 200_000,
    }
    assert learned['learned_speed_bps'] == 3_000_000
    assert p._selection_key(learned) < p._selection_key(unlearned)

    checks = {
        'app.py': [
            'from yt_dlp.utils import ExtractorError',
            'teddy_check_task_state',
            "get('teddy_task_id')",
            "task.get('status') in ('일시정지 요청 중', '일시정지')",
            "elif t.get('status') == '일시정지 요청 중'",
            'except ExtractorError',
        ],
        'teddy_hls_transport.py': [
            'HLS_WORKERS = 8',
            "ALLOWED_HLS_TRANSPORT_MODES = ('per-worker', 'async-pool')",
            "ALLOWED_HLS_POOL_CLIENTS = (4, 8, 12, 16, 24)",
            'HLS_POOL_CLIENTS = 24',
            "ALLOWED_HLS_HTTP_VERSIONS = ('auto', 'v1')",
            "HLS_HTTP_VERSION = 'auto'",
            'def pool_clients_from_settings(settings):',
            'def http_version_from_settings(settings):',
            'CurlHttpVersion.V1_1',
            "task['hls_http_version_actual']",
            'cffi_requests.Session()',
            'cffi_requests.AsyncSession(max_clients=max_clients)',
            'asyncio.run_coroutine_threadsafe',
            "state.get('proxy_url') == proxy_url",
            "state.get('http_version') == http_version",
            "task.get('network_mode') == 'vpn'",
            "def invalidate(mode='per-worker')",
            'clients = normalize_pool_clients(max_clients or HLS_POOL_CLIENTS)',
            "kwargs['proxies']",
        ],
        'teddy_network.py': [
            'Gluetun proxy를 통한 공인 IP 확인',
            'auto_recover',
        ],
        'teddy_routing.py': [
            '다운로드 큐에 추가했습니다',
        ],
        'teddy_generic.py': [
            'YT_DLP_MEDIA_MODES',
            'YT_DLP_VIDEO_QUALITIES',
            'normalize_ytdlp_options',
            'yt_dlp_options_for_task',
            "'noplaylist': True",
            "'FFmpegExtractAudio'",
            "opts['remuxvideo'] = container",
            "opts['writeautomaticsub'] = True",
            'mode_label(network_mode)',
            'network_mode',
            'download_generic',
        ],
        'teddy_bootstrap.py': [
            'teddy_proxy_pool.install',
            'rotate_after_failure',
            'network_proxy_speed_bps',
            'ensure_ready(core, wait_seconds=35)',
            'observe_task_success',
            'note_failure(core',
            '_proxy_recovery_state',
            '다른 작업/세그먼트가 이미 프록시를 변경함',
            '동일 task 중복 실행 차단',
            'teddy_vpn_health.install',
            '_fetch_segment_with_network_recovery',
            '_dispatch_download_guarded',
            'teddy_duplicates.install',
            'RouteAwareRequests',
            'attempted_proxy',
            '엔진 단계 실패 -> 다음 Proxy 후보로 재시도',
            '엔진 단계 실패 -> 다른 작업이 바꾼 새 후보 재사용',
        ],
        'teddy_proxy_pool.py': [
            '_rank_by_real_speed',
            '_selection_key',
            'current_speed_bps',
            'current_learned_speed_bps',
            'network_proxy_learned_speed_bps',
            'speed.cloudflare.com/__down',
            '활성 작업',
        ],
        'teddy_entrypoint.py': [
            'import teddy_hls_transport',
            'FIRST_COMPLETED',
            'teddy_hls_transport.get(',
            'teddy_hls_transport.invalidate(transport_mode)',
            'transport_mode=transport_mode',
            'pool_clients = teddy_hls_transport.pool_clients_from_settings(core.settings)',
            'http_version = teddy_hls_transport.http_version_from_settings(core.settings)',
            "core.tasks[task_id]['hls_transport_mode'] = transport_mode",
            "core.tasks[task_id]['hls_pool_clients'] = pool_clients",
            "core.tasks[task_id]['hls_http_version'] = http_version",
            "core.tasks[task_id]['hls_http_version_actual'] = '?'",
            'worker_count=pool_clients',
            '· pool={pool_clients} · http={http_version} · write={write_mode}',
            'continuous',
            'return_when=FIRST_COMPLETED',
            'submit_one()',
            '_teddy_proxy_transfer_observer',
            'observer(task_id, window_bytes, window_elapsed)',
            'remux-output.mp4',
            'os.replace(remux_tmp, out_path)',
            '_teddy_vpn_failure_observer',
            "'teddy_task_id': task_id",
            '추출 단계 일시정지 완료',
        ],
        'teddy_hls_benchmark.py': [
            "task.get('hls_transport_mode', '?')",
            "task.get('hls_pool_clients', '?')",
            "task.get('hls_http_version', '?')",
            "task.get('hls_http_version_actual', '?')",
            'transport=',
            'pool=',
            'actual_http=',
            'proxy_changed=',
        ],
        'teddy_duplicates.py': ['duplicate queue guard enabled'],
        'teddy_storage.py': ['site_key_for_url'],
    }
    for path, needles in checks.items():
        for needle in needles:
            require(path, needle)

    forbid('teddy_entrypoint.py', 'batch_size = 16', 'legacy HLS batch barrier')
    print('Teddy runtime build verification: OK')


def verify_final():
    checks = {
        'templates/index.html': [
            '<title>Downloader</title>',
            'teddyEffectiveSpeed',
            '남은 시간 약',
            'Ⅱ 일시정지',
            'teddy-network.js',
            'teddy-proxy.js',
            'teddy-hls-benchmark.js',
            'value="proxy"',
            'teddyProxyPoolMount',
            '실사용 ',
            'teddyEncodeFilePath',
            'downloadNetworkMode',
            'teddyRoutingTarget',
            'teddy-routing.js',
            'data-page="logs"',
            'id="page-logs"',
            'teddy-logs.js',
            'data-page="browser"',
            'id="page-browser"',
            'teddy-browser.js',
            '일반 사이트 yt-dlp 옵션',
            'id="set-ytdlp-media-mode"',
            'id="set-ytdlp-video-quality"',
            'id="set-ytdlp-video-container"',
            'id="set-ytdlp-audio-format"',
            'id="set-ytdlp-subtitles"',
            "yt_dlp_media_mode: 'video'",
            "yt_dlp_video_container: 'mp4'",
            "yt_dlp_audio_format: 'm4a'",
            "yt_dlp_subtitles: 'off'",
            'teddyUpdateYtDlpVisibility',
        ],
        'templates/teddy-hls-benchmark.js': [
            'HLS 성능 모드',
            '🚀 최고속',
            '⚖️ 균형 (권장)',
            '🛡️ 보수',
            '직접 설정됨 (터미널/진단)',
            'hls_workers: preset.workers',
            'hls_pool_clients: preset.pool',
            "hls_transport_mode: 'async-pool'",
            "hls_http_version: 'v1'",
            "hls_write_mode: 'parts'",
            'defaultSettings.hls_workers = 16',
            'defaultSettings.hls_pool_clients = 16',
            "defaultSettings.hls_transport_mode = 'async-pool'",
            "defaultSettings.hls_http_version = 'v1'",
            "defaultSettings.hls_write_mode = 'parts'",
        ],
        'templates/teddy-reliability.js': [
            'isHlsRemuxing',
            "task.progress === '99%'",
            "task.hls_transport_mode",
            "progress: '100%'",
            '다운로드 완료 · MP4 생성 중',
            'MP4 생성 중…',
            '__teddyRemuxUiWrapped',
        ],
        'templates/teddy-network.js': [
            '누적 자동 IP 변경',
            '자동 복구',
            'auto_failure_count',
        ],
        'templates/teddy-proxy.js': [
            '무료 Proxy Pool',
            '실사용 학습',
            'current_learned_speed_bps',
            "'/api/proxy/status'",
        ],
        'teddy_proxy_pool.py': ["'/api/proxy/status'"],
        'teddy_logging.py': ["'/api/logs'"],
        'teddy_storage.py': ['install_file_routes'],
        'teddy_routing.py': ['adaptive routing enabled'],
    }
    for path, needles in checks.items():
        for needle in needles:
            require(path, needle)

    forbid('templates/index.html', 'MissAV')
    forbid('templates/index.html', 'taskList.innerHTML = entries.map')
    forbid('templates/teddy-hls-benchmark.js', 'HLS 연결 방식 (성능 테스트)', 'legacy detailed HLS transport selector')
    forbid('templates/teddy-hls-benchmark.js', 'Async pool 연결 수 (성능 테스트)', 'legacy detailed HLS pool selector')
    forbid('templates/teddy-hls-benchmark.js', 'HLS 저장 방식 (성능 테스트)', 'legacy detailed HLS write selector')
    print('Teddy final UI build verification: OK')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=('runtime', 'final'))
    args = parser.parse_args()
    if args.phase == 'runtime':
        verify_runtime()
    else:
        verify_final()


if __name__ == '__main__':
    main()
