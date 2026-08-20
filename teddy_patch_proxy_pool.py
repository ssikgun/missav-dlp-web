from pathlib import Path


GENERIC = Path('teddy_generic.py')
BOOTSTRAP = Path('teddy_bootstrap.py')
PROXY_POOL = Path('teddy_proxy_pool.py')


def replace_once(path, old, new, label):
    text = path.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one patch anchor, found {count}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')


def main():
    replace_once(
        GENERIC,
        "    route_label = 'VPN' if network_mode == 'vpn' else 'Direct'\n",
        "    route_label = teddy_routing.mode_label(network_mode)\n",
        'generic proxy route label',
    )

    # Selecting Proxy explicitly fixes the route category, not one volatile IP.
    # Allow the pool to try another verified candidate while still preventing
    # fallback to Direct/VPN for a one-off Proxy override.
    replace_once(
        BOOTSTRAP,
        """            mode == 'proxy'\n            and recoverable\n            and not decision['fixed']\n            and proxy_task_retries < 2\n""",
        """            mode == 'proxy'\n            and recoverable\n            and proxy_task_retries < 2\n""",
        'fixed proxy candidate rotation',
    )

    # Clear the completion event before spawning a refresh worker and mark the
    # refresh as in-flight immediately. Otherwise ensure_ready() could observe a
    # stale completion event from the previous run and fall through too early.
    replace_once(
        PROXY_POOL,
        """def start_refresh(core=None, delay=0.0):\n    core = core or _core\n    if core is None:\n        return False\n    with _lock:\n        if _state['refreshing']:\n            return False\n    worker = threading.Thread(\n""",
        """def start_refresh(core=None, delay=0.0):\n    core = core or _core\n    if core is None:\n        return False\n    with _lock:\n        if _state['refreshing']:\n            return False\n        _state['refreshing'] = True\n        _refresh_done.clear()\n    worker = threading.Thread(\n""",
        'proxy refresh event race',
    )

    print('proxy pool runtime patch: OK')


if __name__ == '__main__':
    main()
