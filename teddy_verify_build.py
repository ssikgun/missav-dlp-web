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
    import teddy_hls_transport as h
    import teddy_proxy_pool as p

    assert h.HLS_WORKERS == 8
    assert p.BANDWIDTH_TEST_BYTES == 512 * 1024
    assert p.BANDWIDTH_TEST_LIMIT <= 8
    assert p.BANDWIDTH_TEST_WORKERS <= 4
    assert 'speed.cloudflare.com/__down' in p.BANDWIDTH_URL

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
            'cffi_requests.Session()',
            "state.get('proxy_url') == proxy_url",
            'def invalidate()',
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
            'teddy_hls_transport.invalidate()',
            'persistent session + continuous',
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
