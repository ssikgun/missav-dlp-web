from pathlib import Path


ENTRYPOINT = Path('teddy_entrypoint.py')
BOOTSTRAP = Path('teddy_bootstrap.py')


def replace_once(path, old, new, label):
    text = path.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one patch anchor, found {count}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')


def main():
    replace_once(
        ENTRYPOINT,
        """        except Exception as exc:\n            last = str(exc)\n        if attempt + 1 < SEGMENT_RETRY_ATTEMPTS:\n""",
        """        except Exception as exc:\n            last = str(exc)\n\n        observer = getattr(core, '_teddy_vpn_failure_observer', None)\n        if callable(observer):\n            try:\n                observer(task_id, os.path.basename(seg_url), last)\n            except Exception as observer_exc:\n                print(f'[VPN 자동복구] 오류 감지기 예외: {observer_exc}', flush=True)\n\n        if attempt + 1 < SEGMENT_RETRY_ATTEMPTS:\n""",
        'segment failure observer',
    )

    replace_once(
        BOOTSTRAP,
        """import teddy_network\nimport teddy_routing\n""",
        """import teddy_network\nimport teddy_routing\nimport teddy_vpn_health\n""",
        'vpn health import',
    )

    replace_once(
        BOOTSTRAP,
        """teddy_duplicates.install(core)\nteddy_network.install(core)\nteddy_logging.install_routes(core)\n""",
        """teddy_duplicates.install(core)\nteddy_network.install(core)\nteddy_vpn_health.install(core, teddy_network)\n\n# Any successful manual or automatic VPN rotation invalidates the recent\n# failure window so stale failures cannot immediately trigger another change.\n_original_vpn_rotation = teddy_network._perform_rotation_locked\ndef _perform_rotation_with_health_reset(*args, **kwargs):\n    result = _original_vpn_rotation(*args, **kwargs)\n    if result.get('ok'):\n        teddy_vpn_health.clear()\n    return result\nteddy_network._perform_rotation_locked = _perform_rotation_with_health_reset\n\nteddy_logging.install_routes(core)\n""",
        'vpn health install',
    )

    print('vpn health runtime patch: OK')


if __name__ == '__main__':
    main()
