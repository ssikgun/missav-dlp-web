import json
import os
import threading
import time

import teddy_routing


_control_override = os.environ.get('GLUETUN_CONTROL_URL', '').strip().rstrip('/')
CONTROL_URLS = (
    [_control_override]
    if _control_override
    else ['http://gluetun:8000', 'http://127.0.0.1:8000']
)
ROTATE_TIMEOUT_SECONDS = 55
AUTO_ROTATE_COOLDOWN_SECONDS = 90

_rotate_lock = threading.Lock()
_identity_lock = threading.Lock()
_state_lock = threading.Lock()
_identity_cache = {'at': 0.0, 'data': {}}
_rotation_in_progress = False
_last_rotation_monotonic = 0.0
_last_auto_rotation_monotonic = 0.0
_auto_state = {
    'auto_rotate_count': 0,
    'last_auto_rotate_at': 0,
    'last_auto_reason': '',
    'last_auto_old_ip': '',
    'last_auto_ip': '',
    'last_auto_changed': False,
}


def _state_file(core):
    return os.path.join(core.DOWNLOAD_DIR, '.network-state.json')


def _load_auto_state(core):
    global _auto_state
    try:
        with open(_state_file(core), 'r', encoding='utf-8') as file_obj:
            saved = json.load(file_obj)
        if isinstance(saved, dict):
            with _state_lock:
                _auto_state.update({
                    key: saved[key]
                    for key in _auto_state
                    if key in saved
                })
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass


def _save_auto_state(core):
    try:
        path = _state_file(core)
        tmp = path + '.tmp'
        with _state_lock:
            payload = dict(_auto_state)
        with open(tmp, 'w', encoding='utf-8') as file_obj:
            json.dump(payload, file_obj, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError as exc:
        print(f'[VPN] network state 저장 실패: {exc}', flush=True)


def _control_request(core, method, path, payload=None, timeout=4):
    last_error = None
    for base in CONTROL_URLS:
        url = base + path
        kwargs = {'timeout': timeout}
        if payload is not None:
            kwargs['json'] = payload
        try:
            response = getattr(core.cffi_requests, method.lower())(url, **kwargs)
        except Exception as exc:
            last_error = exc
            continue
        if response.status_code in (401, 403):
            raise PermissionError('Gluetun control API 인증 설정이 필요합니다.')
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f'Gluetun control API HTTP {response.status_code}')
        if not response.content:
            return {}
        try:
            return response.json()
        except Exception:
            return {}
    raise RuntimeError(f'Gluetun control API 연결 실패: {last_error or "unreachable"}')


def _external_identity(core, force=False):
    now = time.monotonic()
    with _identity_lock:
        if not force and now - _identity_cache['at'] < 60 and _identity_cache['data']:
            return dict(_identity_cache['data'])

    data = {}
    proxy_url = teddy_routing.proxy_for_mode('vpn')
    proxy_kwargs = (
        {'proxies': {'http': proxy_url, 'https': proxy_url}}
        if proxy_url else {}
    )
    try:
        response = core.cffi_requests.get(
            'https://ipinfo.io/json',
            impersonate='firefox135',
            timeout=7,
            **proxy_kwargs,
        )
        if response.status_code == 200:
            raw = response.json()
            data = {
                'public_ip': raw.get('ip') or '',
                'city': raw.get('city') or '',
                'region': raw.get('region') or '',
                'country': raw.get('country') or '',
            }
    except Exception:
        pass

    if not data.get('public_ip'):
        try:
            response = core.cffi_requests.get(
                'https://api.ipify.org?format=json',
                impersonate='firefox135',
                timeout=7,
                **proxy_kwargs,
            )
            if response.status_code == 200:
                data = {'public_ip': (response.json().get('ip') or '')}
        except Exception:
            pass

    if data.get('public_ip'):
        with _identity_lock:
            _identity_cache['at'] = now
            _identity_cache['data'] = dict(data)
    return data


def _clear_identity_cache():
    with _identity_lock:
        _identity_cache['at'] = 0.0
        _identity_cache['data'] = {}


def _active_task_count(core):
    active_statuses = {'다운로드 중', '일시정지 요청 중', '대기 중'}
    return sum(1 for task in core.tasks.values() if task.get('status') in active_statuses)


def _active_vpn_task_count(core):
    active_statuses = {'다운로드 중', '일시정지 요청 중', '대기 중'}
    return sum(
        1 for task in core.tasks.values()
        if task.get('status') in active_statuses and task.get('network_mode') == 'vpn'
    )


def is_recoverable_failure(message):
    """Return True only for failures where changing Direct/VPN route can help."""
    text = str(message or '').lower()

    recoverable_http = (
        'http 403', 'http error 403', '403 forbidden',
        'http 408', 'http error 408',
        'http 425', 'http error 425',
        'http 429', 'http error 429', '429 too many requests',
        'http 500', 'http error 500',
        'http 502', 'http error 502', '502 bad gateway',
        'http 503', 'http error 503',
        'http 504', 'http error 504',
        'http 520', 'http 521', 'http 522', 'http 523', 'http 524',
    )
    if any(token in text for token in recoverable_http):
        return True

    network_tokens = (
        'timeout', 'timed out', 'connection reset', 'connection refused',
        'failed to connect', 'could not connect', "couldn't connect",
        'tunnel connection failed',
        'network is unreachable', 'network error', 'recv failure',
        'empty reply', 'ssl connect', 'tls connect',
        'curl: (7)', 'curl: (28)', 'curl: (35)', 'curl: (52)', 'curl: (56)',
        'operation too slow', 'connection closed', 'cloudflare',
        'access denied', 'geo restricted', 'geo-restricted', 'georestricted',
        'not available in your country', 'not available from your location',
        'blocked in your country', 'region restriction',
    )
    return any(token in text for token in network_tokens)


def _perform_rotation_locked(core, automatic=False, reason=''):
    global _rotation_in_progress, _last_rotation_monotonic, _last_auto_rotation_monotonic

    before = _control_request(core, 'GET', '/v1/publicip/ip').get('public_ip') or ''
    _control_request(core, 'GET', '/v1/vpn/status')

    _rotation_in_progress = True
    mode = '자동 복구' if automatic else '수동 변경'
    print(f'[VPN] {mode} 요청: 현재 {before or "unknown"}', flush=True)
    try:
        _control_request(core, 'PUT', '/v1/vpn/status', {'status': 'stopped'}, timeout=7)
        time.sleep(1.0)
        _control_request(core, 'PUT', '/v1/vpn/status', {'status': 'running'}, timeout=7)

        deadline = time.monotonic() + ROTATE_TIMEOUT_SECONDS
        new_ip = ''
        last_error = ''
        while time.monotonic() < deadline:
            try:
                vpn = _control_request(core, 'GET', '/v1/vpn/status', timeout=4)
                if vpn.get('status') == 'running':
                    ip_data = _control_request(core, 'GET', '/v1/publicip/ip', timeout=4)
                    candidate = ip_data.get('public_ip') or ''
                    if candidate:
                        new_ip = candidate
                        if not before or candidate != before:
                            break
            except Exception as exc:
                last_error = str(exc)
            time.sleep(2.0)

        if not new_ip:
            raise RuntimeError(
                'VPN은 재연결했지만 공인 IP를 확인하지 못했습니다.'
                + (f' ({last_error})' if last_error else '')
            )

        _clear_identity_cache()
        identity = _external_identity(core, force=True)
        changed = bool(before and new_ip != before)
        _last_rotation_monotonic = time.monotonic()

        if automatic:
            _last_auto_rotation_monotonic = _last_rotation_monotonic
            with _state_lock:
                _auto_state['auto_rotate_count'] = int(_auto_state.get('auto_rotate_count', 0)) + 1
                _auto_state['last_auto_rotate_at'] = int(time.time())
                _auto_state['last_auto_reason'] = str(reason or '')[:240]
                _auto_state['last_auto_old_ip'] = before
                _auto_state['last_auto_ip'] = new_ip
                _auto_state['last_auto_changed'] = changed
            _save_auto_state(core)

        print(
            f'[VPN] {mode} 완료: {before or "unknown"} -> {new_ip} '
            f'(changed={changed})',
            flush=True,
        )
        return {
            'ok': True,
            'old_ip': before,
            'public_ip': new_ip,
            'changed': changed,
            'city': identity.get('city') or '',
            'region': identity.get('region') or '',
            'country': identity.get('country') or '',
        }
    except Exception:
        try:
            _control_request(core, 'PUT', '/v1/vpn/status', {'status': 'running'}, timeout=7)
        except Exception:
            pass
        raise
    finally:
        _rotation_in_progress = False


def auto_recover(core, task_id, reason, failed_since):
    """Rotate once after repeated recoverable failures on a VPN-routed task."""
    global _last_rotation_monotonic

    if not core.settings.get('network_auto_recover', True):
        return False
    if task_id not in core.tasks:
        return False
    task = core.tasks[task_id]
    if task.get('network_mode') != 'vpn':
        return False
    if task.get('status') in ('일시정지 요청 중', '일시정지'):
        return False

    now = time.monotonic()
    if _last_rotation_monotonic > failed_since:
        print('[VPN 자동복구] 다른 세그먼트가 이미 VPN을 변경함 → 새 경로 재사용', flush=True)
        return True
    if _last_auto_rotation_monotonic and now - _last_auto_rotation_monotonic < AUTO_ROTATE_COOLDOWN_SECONDS:
        remaining = int(AUTO_ROTATE_COOLDOWN_SECONDS - (now - _last_auto_rotation_monotonic))
        print(f'[VPN 자동복구] cooldown 중 ({remaining}s 남음) → task 재시도로 넘김', flush=True)
        return False

    with _rotate_lock:
        if _last_rotation_monotonic > failed_since:
            print('[VPN 자동복구] 대기 중 다른 세그먼트가 복구 완료 → 새 경로 재사용', flush=True)
            return True

        now = time.monotonic()
        if _last_auto_rotation_monotonic and now - _last_auto_rotation_monotonic < AUTO_ROTATE_COOLDOWN_SECONDS:
            return False

        try:
            result = _perform_rotation_locked(core, automatic=True, reason=reason)
        except Exception as exc:
            print(f'[VPN 자동복구] 실패: {exc}', flush=True)
            return False

    if result.get('ok') and task_id in core.tasks:
        task = core.tasks[task_id]
        task['network_recoveries'] = int(task.get('network_recoveries', 0)) + 1
        task['last_network_recovery_at'] = int(time.time())
        core.save_tasks()
        return True
    return False


def _network_status(core, force_identity=False):
    result = {
        'control_ready': False,
        'vpn_status': 'unknown',
        'public_ip': '',
        'city': '',
        'region': '',
        'country': '',
        'message': '',
        'rotation_in_progress': _rotation_in_progress,
        'auto_recovery_enabled': bool(core.settings.get('network_auto_recover', True)),
    }

    try:
        vpn = _control_request(core, 'GET', '/v1/vpn/status')
        result['vpn_status'] = vpn.get('status') or 'unknown'
        ip_data = _control_request(core, 'GET', '/v1/publicip/ip')
        result['public_ip'] = ip_data.get('public_ip') or ''
        result['control_ready'] = True
    except PermissionError as exc:
        result['message'] = str(exc)
    except Exception as exc:
        result['message'] = str(exc)

    identity = _external_identity(core, force=force_identity)
    if not result['public_ip']:
        result['public_ip'] = identity.get('public_ip') or ''
    if not identity.get('public_ip') or identity.get('public_ip') == result['public_ip']:
        result['city'] = identity.get('city') or ''
        result['region'] = identity.get('region') or ''
        result['country'] = identity.get('country') or ''

    result['active_tasks'] = _active_task_count(core)
    result['active_vpn_tasks'] = _active_vpn_task_count(core)
    result['can_rotate'] = bool(
        result['control_ready']
        and result['active_vpn_tasks'] == 0
        and not _rotation_in_progress
    )
    with _state_lock:
        result.update(dict(_auto_state))
    return result


def install(core):
    if 'network_auto_recover' not in core.settings:
        core.settings['network_auto_recover'] = True
        core.save_settings(core.settings)
    _load_auto_state(core)

    @core.app.route('/api/network/status', methods=['GET'])
    def teddy_network_status():
        return core.jsonify(_network_status(core))

    @core.app.route('/api/network/auto-recovery', methods=['PUT'])
    def teddy_network_auto_recovery():
        payload = core.request.get_json(silent=True) or {}
        enabled = payload.get('enabled')
        if not isinstance(enabled, bool):
            return core.jsonify({'status': 'error', 'message': 'enabled 값이 필요합니다.'}), 400
        core.settings['network_auto_recover'] = enabled
        core.save_settings(core.settings)
        print(f'[VPN 자동복구] 설정: {"ON" if enabled else "OFF"}', flush=True)
        return core.jsonify({'status': 'success', 'enabled': enabled})

    @core.app.route('/api/network/rotate', methods=['POST'])
    def teddy_network_rotate():
        if _active_vpn_task_count(core):
            return core.jsonify({
                'status': 'error',
                'message': '먼저 진행 중인 VPN 다운로드를 일시정지하세요.',
            }), 409

        if not _rotate_lock.acquire(blocking=False):
            return core.jsonify({
                'status': 'error',
                'message': '이미 VPN IP를 변경하는 중입니다.',
            }), 409

        try:
            try:
                result = _perform_rotation_locked(core, automatic=False)
            except PermissionError as exc:
                return core.jsonify({'status': 'error', 'message': str(exc)}), 503
            except Exception as exc:
                print(f'[VPN] IP 변경 실패: {exc}', flush=True)
                return core.jsonify({
                    'status': 'error',
                    'message': f'VPN IP 변경 실패: {exc}',
                }), 500

            return core.jsonify({
                'status': 'success',
                'old_ip': result.get('old_ip', ''),
                'public_ip': result.get('public_ip', ''),
                'changed': bool(result.get('changed')),
                'city': result.get('city', ''),
                'region': result.get('region', ''),
                'country': result.get('country', ''),
            })
        finally:
            _rotate_lock.release()

    print(
        '[Teddy] VPN network manager enabled: split-route proxy + manual rotate + automatic recovery',
        flush=True,
    )
