from pathlib import Path


GENERIC = Path('teddy_generic.py')
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

    # Clear the completion event before spawning a refresh worker and mark the
    # refresh as in-flight immediately. Otherwise ensure_ready() could observe a
    # stale completion event from the previous run and fall through too early.
    replace_once(
        PROXY_POOL,
        """def start_refresh(core=None, delay=0.0):
    core = core or _core
    if core is None:
        return False
    with _lock:
        if _state['refreshing']:
            return False
    worker = threading.Thread(
""",
        """def start_refresh(core=None, delay=0.0):
    core = core or _core
    if core is None:
        return False
    with _lock:
        if _state['refreshing']:
            return False
        _state['refreshing'] = True
        _refresh_done.clear()
    worker = threading.Thread(
""",
        'proxy refresh event race',
    )

    print('proxy pool runtime patch: OK')


if __name__ == '__main__':
    main()
