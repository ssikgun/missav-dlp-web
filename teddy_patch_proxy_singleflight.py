from pathlib import Path


BOOTSTRAP = Path('teddy_bootstrap.py')
NETWORK_JS = Path('templates/teddy-network.js')


def replace_once(path, old, new, label):
    text = path.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one patch anchor, found {count}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')


def main():
    replace_once(
        BOOTSTRAP,
        """\n\ndef _fetch_segment_with_network_recovery(task_id, seg_url, headers):\n""",
        """\n\n_proxy_recovery_lock = threading.Lock()\n_proxy_recovery_state = {'last_rotation_at': 0.0}\n\n\ndef _fetch_segment_with_network_recovery(task_id, seg_url, headers):\n""",
        'proxy recovery global single-flight state',
    )

    replace_once(
        BOOTSTRAP,
        """        if mode == 'proxy':\n            print(\n                f'[Proxy] 세그먼트 재시도 소진 -> 다음 프록시 판단: {message[:180]}',\n                flush=True,\n            )\n            if not teddy_proxy_pool.rotate_after_failure(core, reason=message):\n                raise\n            reliability._check_task_state(task_id)\n            record = teddy_proxy_pool.current_record()\n            current = core.tasks.get(task_id)\n            if current:\n                current['network_proxy'] = record.get('proxy', '')\n                current['network_proxy_latency_ms'] = int(record.get('latency_ms') or 0)\n                current['network_proxy_speed_bps'] = int(record.get('speed_bps') or 0)\n                core.save_tasks()\n            print('[Proxy] 새 프록시에서 같은 세그먼트 재시도', flush=True)\n            with teddy_routing.request_route('proxy'):\n                return _original_fetch_segment(task_id, seg_url, headers)\n""",
        """        if mode == 'proxy':\n            print(\n                f'[Proxy] 세그먼트 재시도 소진 -> 다음 프록시 판단: {message[:180]}',\n                flush=True,\n            )\n            reused_rotation = False\n            with _proxy_recovery_lock:\n                last_rotation = float(_proxy_recovery_state.get('last_rotation_at') or 0.0)\n                if last_rotation > failed_since:\n                    reused_rotation = True\n                else:\n                    if not teddy_proxy_pool.rotate_after_failure(core, reason=message):\n                        raise\n                    _proxy_recovery_state['last_rotation_at'] = time.monotonic()\n\n            reliability._check_task_state(task_id)\n            record = teddy_proxy_pool.current_record()\n            current = core.tasks.get(task_id)\n            if current:\n                current['network_proxy'] = record.get('proxy', '')\n                current['network_proxy_latency_ms'] = int(record.get('latency_ms') or 0)\n                current['network_proxy_speed_bps'] = int(record.get('speed_bps') or 0)\n                core.save_tasks()\n            if reused_rotation:\n                print('[Proxy] 다른 작업/세그먼트가 이미 프록시를 변경함 -> 새 후보 재사용', flush=True)\n            else:\n                print('[Proxy] 새 프록시에서 같은 세그먼트 재시도', flush=True)\n            with teddy_routing.request_route('proxy'):\n                return _original_fetch_segment(task_id, seg_url, headers)\n""",
        'proxy recovery pool-wide single-flight logic',
    )

    replace_once(
        NETWORK_JS,
        "' · 자동 IP 변경 ' + autoCount + '회' +",
        "' · 누적 자동 IP 변경 ' + autoCount + '회' +",
        'cumulative VPN recovery label',
    )

    print('proxy recovery pool-wide single-flight + cumulative VPN label patch: OK')


if __name__ == '__main__':
    main()
