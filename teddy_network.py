import os
import threading
import time


CONTROL_URL = os.environ.get('GLUETUN_CONTROL_URL', 'http://127.0.0.1:8000').rstrip('/')
ROTATE_TIMEOUT_SECONDS = 55

_rotate_lock = threading.Lock()
_identity_lock = threading.Lock()
_identity_cache = {'at': 0.0, 'data': {}}


def _control_request(core, method, path, payload=None, timeout=4):
    url = CONTROL_URL + path
    kwargs = {'timeout': timeout}
    if payload is not None:
        kwargs['json'] = payload
    response = getattr(core.cffi_requests, method.lower())(url, **kwargs)
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


def _external_identity(core, force=False):
    now = time.monotonic()
    with _identity_lock:
        if not force and now - _identity_cache['at'] < 60 and _identity_cache['data']:
            return dict(_identity_cache['data'])

    data = {}
    try:
        response = core.cffi_requests.get(
            'https://ipinfo.io/json',
            impersonate='firefox135',
            timeout=7,
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


def _network_status(core, force_identity=False):
    result = {
        'control_ready': False,
        'vpn_status': 'unknown',
        'public_ip': '',
        'city': '',
        'region': '',
        'country': '',
        'message': '',
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
        result['message'] = f'Gluetun control API 연결 실패: {exc}'

    identity = _external_identity(core, force=force_identity)
    if not result['public_ip']:
        result['public_ip'] = identity.get('public_ip') or ''
    if not identity.get('public_ip') or identity.get('public_ip') == result['public_ip']:
        result['city'] = identity.get('city') or ''
        result['region'] = identity.get('region') or ''
        result['country'] = identity.get('country') or ''

    result['active_tasks'] = _active_task_count(core)
    result['can_rotate'] = bool(result['control_ready'] and result['active_tasks'] == 0)
    return result


def install(core):
    @core.app.route('/api/network/status', methods=['GET'])
    def teddy_network_status():
        return core.jsonify(_network_status(core))

    @core.app.route('/api/network/rotate', methods=['POST'])
    def teddy_network_rotate():
        if _active_task_count(core):
            return core.jsonify({
                'status': 'error',
                'message': '먼저 진행 중인 다운로드를 일시정지하세요.',
            }), 409

        if not _rotate_lock.acquire(blocking=False):
            return core.jsonify({
                'status': 'error',
                'message': '이미 VPN IP를 변경하는 중입니다.',
            }), 409

        try:
            try:
                before = _control_request(core, 'GET', '/v1/publicip/ip').get('public_ip') or ''
                _control_request(core, 'GET', '/v1/vpn/status')
            except PermissionError as exc:
                return core.jsonify({'status': 'error', 'message': str(exc)}), 503
            except Exception as exc:
                return core.jsonify({
                    'status': 'error',
                    'message': f'Gluetun control API를 사용할 수 없습니다: {exc}',
                }), 503

            print(f'[VPN] IP 변경 요청: 현재 {before or "unknown"}', flush=True)
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
                return core.jsonify({
                    'status': 'error',
                    'message': 'VPN은 재연결했지만 새 공인 IP를 확인하지 못했습니다.' + (f' ({last_error})' if last_error else ''),
                }), 504

            _clear_identity_cache()
            identity = _external_identity(core, force=True)
            changed = bool(before and new_ip != before)
            print(f'[VPN] 재연결 완료: {before or "unknown"} -> {new_ip} (changed={changed})', flush=True)
            return core.jsonify({
                'status': 'success',
                'old_ip': before,
                'public_ip': new_ip,
                'changed': changed,
                'city': identity.get('city') or '',
                'region': identity.get('region') or '',
                'country': identity.get('country') or '',
            })
        except Exception as exc:
            # Best effort: if a stop succeeded but start failed, try to bring VPN back.
            try:
                _control_request(core, 'PUT', '/v1/vpn/status', {'status': 'running'}, timeout=7)
            except Exception:
                pass
            print(f'[VPN] IP 변경 실패: {exc}', flush=True)
            return core.jsonify({
                'status': 'error',
                'message': f'VPN IP 변경 실패: {exc}',
            }), 500
        finally:
            _rotate_lock.release()

    print('[Teddy] VPN network manager enabled', flush=True)
