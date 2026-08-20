from pathlib import Path


BOOTSTRAP = Path('teddy_bootstrap.py')


def replace_once(old, new, label):
    text = BOOTSTRAP.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one patch anchor, found {count}')
    BOOTSTRAP.write_text(text.replace(old, new, 1), encoding='utf-8')


def main():
    replace_once(
        """\n\ndef _fetch_segment_with_network_recovery(task_id, seg_url, headers):\n""",
        """\n\n_proxy_recovery_lock = threading.Lock()\n_proxy_last_rotation_at = {}\n\n\ndef _fetch_segment_with_network_recovery(task_id, seg_url, headers):\n""",
        'proxy recovery single-flight state',
    )

    replace_once(
        """        if mode == 'proxy':\n            print(\n                f'[Proxy] 세그먼트 재시도 소진 -> 다음 프록시 판단: {message[:180]}',\n                flush=True,\n            )\n            if not teddy_proxy_pool.rotate_after_failure(core, reason=message):\n                raise\n            reliability._check_task_state(task_id)\n            record = teddy_proxy_pool.current_record()\n            current = core.tasks.get(task_id)\n            if current:\n                current['network_proxy'] = record.get('proxy', '')\n                current['network_proxy_latency_ms'] = int(record.get('latency_ms') or 0)\n                current['network_proxy_speed_bps'] = int(record.get('speed_bps') or 0)\n                core.save_tasks()\n            print('[Proxy] 새 프록시에서 같은 세그먼트 재시도', flush=True)\n            with teddy_routing.request_route('proxy'):\n                return _original_fetch_segment(task_id, seg_url, headers)\n""",
        """        if mode == 'proxy':\n            print(\n                f'[Proxy] 세그먼트 재시도 소진 -> 다음 프록시 판단: {message[:180]}',\n                flush=True,\n            )\n            reused_rotation = False\n            with _proxy_recovery_lock:\n                last_rotation = float(_proxy_last_rotation_at.get(task_id) or 0.0)\n                if last_rotation > failed_since:\n                    reused_rotation = True\n                else:\n                    if not teddy_proxy_pool.rotate_after_failure(core, reason=message):\n                        raise\n                    _proxy_last_rotation_at[task_id] = time.monotonic()\n\n            reliability._check_task_state(task_id)\n            record = teddy_proxy_pool.current_record()\n            current = core.tasks.get(task_id)\n            if current:\n                current['network_proxy'] = record.get('proxy', '')\n                current['network_proxy_latency_ms'] = int(record.get('latency_ms') or 0)\n                current['network_proxy_speed_bps'] = int(record.get('speed_bps') or 0)\n                core.save_tasks()\n            if reused_rotation:\n                print('[Proxy] 다른 세그먼트가 이미 프록시를 변경함 -> 새 후보 재사용', flush=True)\n            else:\n                print('[Proxy] 새 프록시에서 같은 세그먼트 재시도', flush=True)\n            with teddy_routing.request_route('proxy'):\n                return _original_fetch_segment(task_id, seg_url, headers)\n""",
        'proxy recovery single-flight logic',
    )

    replace_once(
        """    finally:\n        with _task_claim_lock:\n            _claimed_tasks.discard(task_id)\n\n\nreliability._download_video = _dispatch_download_guarded\n""",
        """    finally:\n        with _task_claim_lock:\n            _claimed_tasks.discard(task_id)\n        with _proxy_recovery_lock:\n            _proxy_last_rotation_at.pop(task_id, None)\n\n\nreliability._download_video = _dispatch_download_guarded\n""",
        'proxy recovery task cleanup',
    )

    print('proxy recovery single-flight runtime patch: OK')


if __name__ == '__main__':
    main()
