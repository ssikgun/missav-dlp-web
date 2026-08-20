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
        """        result = _run_engine_once(task_id, url, custom=custom, mode=mode) or {}\n        status = result.get('status')\n""",
        """        attempted_proxy = ''\n        if mode == 'proxy':\n            attempted_proxy = str(teddy_proxy_pool.current_record().get('proxy') or '')\n        result = _run_engine_once(task_id, url, custom=custom, mode=mode) or {}\n        status = result.get('status')\n""",
        'capture proxy used by engine attempt',
    )

    replace_once(
        """        if (\n            mode == 'proxy'\n            and recoverable\n            and not decision['fixed']\n            and proxy_task_retries < 2\n            and teddy_proxy_pool.rotate_after_failure(core, reason=error_message)\n        ):\n            proxy_task_retries += 1\n            modes.insert(index + 1, 'proxy')\n            _reactivate_task(task_id)\n            previous_mode = 'proxy'\n            index += 1\n            continue\n""",
        """        if (\n            mode == 'proxy'\n            and recoverable\n            and proxy_task_retries < 2\n        ):\n            proxy_ready = False\n            reused_rotation = False\n            with _proxy_recovery_lock:\n                current_proxy = str(teddy_proxy_pool.current_record().get('proxy') or '')\n                if attempted_proxy and current_proxy and current_proxy != attempted_proxy:\n                    # Another task already rotated the shared pool while this\n                    # engine attempt was failing. Reuse that new candidate.\n                    proxy_ready = True\n                    reused_rotation = True\n                else:\n                    teddy_proxy_pool.note_failure(core, reason=error_message)\n                    proxy_ready = teddy_proxy_pool.rotate_after_failure(\n                        core, reason=error_message\n                    )\n                    if proxy_ready:\n                        _proxy_recovery_state['last_rotation_at'] = time.monotonic()\n\n            if proxy_ready:\n                proxy_task_retries += 1\n                modes.insert(index + 1, 'proxy')\n                _reactivate_task(task_id)\n                previous_mode = 'proxy'\n                if reused_rotation:\n                    print(\n                        '[Proxy] 엔진 단계 실패 -> 다른 작업이 바꾼 새 후보 재사용',\n                        flush=True,\n                    )\n                else:\n                    print(\n                        '[Proxy] 엔진 단계 실패 -> 다음 Proxy 후보로 재시도',\n                        flush=True,\n                    )\n                index += 1\n                continue\n""",
        'proxy engine-level candidate recovery',
    )

    print('proxy engine-level recovery runtime patch: OK')


if __name__ == '__main__':
    main()
