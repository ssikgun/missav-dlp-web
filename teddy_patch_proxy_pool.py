from pathlib import Path


GENERIC = Path('teddy_generic.py')
BOOTSTRAP = Path('teddy_bootstrap.py')


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

    print('proxy pool runtime patch: OK')


if __name__ == '__main__':
    main()
