from pathlib import Path


ENTRYPOINT = Path('teddy_entrypoint.py')
BOOTSTRAP = Path('teddy_bootstrap.py')
NETWORK = Path('teddy_network.py')
ROUTING = Path('teddy_routing.py')


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

    # Gluetun's public-IP endpoint can briefly be empty while the tunnel is being
    # restarted. Reuse the already observed VPN identity as a best-effort old IP
    # instead of turning a real reconnect into "current unknown".
    replace_once(
        NETWORK,
        """    before = _control_request(core, 'GET', '/v1/publicip/ip').get('public_ip') or ''\n    _control_request(core, 'GET', '/v1/vpn/status')\n""",
        """    before = ''\n    try:\n        before = _control_request(core, 'GET', '/v1/publicip/ip').get('public_ip') or ''\n    except Exception:\n        pass\n    if not before:\n        before = (_external_identity(core) or {}).get('public_ip') or ''\n    _control_request(core, 'GET', '/v1/vpn/status')\n""",
        'vpn old-ip fallback',
    )

    # Confirm reconnect success from either Gluetun control public-IP or a real
    # HTTP request through Gluetun's proxy. The latter is important during the
    # short window where /v1/publicip/ip is unavailable even though VPN traffic
    # already works with the new exit IP.
    replace_once(
        NETWORK,
        """        deadline = time.monotonic() + ROTATE_TIMEOUT_SECONDS\n        new_ip = ''\n        last_error = ''\n        while time.monotonic() < deadline:\n            try:\n                vpn = _control_request(core, 'GET', '/v1/vpn/status', timeout=4)\n                if vpn.get('status') == 'running':\n                    ip_data = _control_request(core, 'GET', '/v1/publicip/ip', timeout=4)\n                    candidate = ip_data.get('public_ip') or ''\n                    if candidate:\n                        new_ip = candidate\n                        if not before or candidate != before:\n                            break\n            except Exception as exc:\n                last_error = str(exc)\n            time.sleep(2.0)\n\n        if not new_ip:\n            raise RuntimeError(\n                'VPN은 재연결했지만 공인 IP를 확인하지 못했습니다.'\n                + (f' ({last_error})' if last_error else '')\n            )\n\n        _clear_identity_cache()\n        identity = _external_identity(core, force=True)\n""",
        """        deadline = time.monotonic() + ROTATE_TIMEOUT_SECONDS\n        new_ip = ''\n        last_error = ''\n        identity = {}\n        same_ip_seen_at = 0.0\n        while time.monotonic() < deadline:\n            try:\n                vpn = _control_request(core, 'GET', '/v1/vpn/status', timeout=4)\n                if vpn.get('status') == 'running':\n                    candidate = ''\n                    try:\n                        ip_data = _control_request(core, 'GET', '/v1/publicip/ip', timeout=4)\n                        candidate = ip_data.get('public_ip') or ''\n                    except Exception as exc:\n                        last_error = str(exc)\n\n                    if not candidate:\n                        _clear_identity_cache()\n                        identity = _external_identity(core, force=True)\n                        candidate = identity.get('public_ip') or ''\n\n                    if candidate:\n                        new_ip = candidate\n                        if not before or candidate != before:\n                            break\n                        if not same_ip_seen_at:\n                            same_ip_seen_at = time.monotonic()\n                        elif time.monotonic() - same_ip_seen_at >= 8:\n                            # Reconnecting to the same exit is still a successful\n                            # tunnel recovery, even if it may not improve routing.\n                            break\n            except Exception as exc:\n                last_error = str(exc)\n            time.sleep(2.0)\n\n        if not new_ip:\n            raise RuntimeError(\n                'VPN은 재연결했지만 Gluetun proxy를 통한 공인 IP 확인에 실패했습니다.'\n                + (f' ({last_error})' if last_error else '')\n            )\n\n        if not identity or identity.get('public_ip') != new_ip:\n            _clear_identity_cache()\n            identity = _external_identity(core, force=True)\n""",
        'vpn reconnect confirmation fallback',
    )

    # The adaptive download front-door historically returned no success message,
    # which made the existing toast renderer show an empty green box.
    replace_once(
        ROUTING,
        """        return core.jsonify({\n            'status': 'success',\n            'task_id': task_id,\n""",
        """        return core.jsonify({\n            'status': 'success',\n            'message': '다운로드 큐에 추가했습니다.',\n            'task_id': task_id,\n""",
        'download success toast message',
    )

    print('vpn health runtime patch: OK')


if __name__ == '__main__':
    main()
