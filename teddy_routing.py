import json
import os
import re
import threading
import time
from contextlib import contextmanager
from urllib.parse import urlparse


VPN_PROXY_URL = os.environ.get('GLUETUN_PROXY_URL', 'http://gluetun:8888').strip()
_STATE_LOCK = threading.Lock()
_ROUTE_LOCAL = threading.local()
_STATE = {
    'manual_rules': {},
    'learned_rules': {},
}

_ALIAS_HOSTS = {
    'youtu.be': 'youtube.com',
    'youtube.com': 'youtube.com',
    'youtube-nocookie.com': 'youtube.com',
    'x.com': 'twitter.com',
    'twitter.com': 'twitter.com',
    'fb.watch': 'facebook.com',
    'facebook.com': 'facebook.com',
}


class RouteAwareRequests:
    """Proxy curl_cffi through the task-selected route without global races.

    When a route context is VPN, all explicit/implicit proxy arguments are
    overridden with Gluetun's HTTP proxy. Outside a route context requests keep
    their original behavior, which is important for control-server and UI calls.
    """
    def __init__(self, wrapped):
        self._wrapped = wrapped

    def _call(self, name, *args, **kwargs):
        proxy_url = getattr(_ROUTE_LOCAL, 'proxy_url', None)
        if proxy_url:
            kwargs['proxies'] = {'http': proxy_url, 'https': proxy_url}
        return getattr(self._wrapped, name)(*args, **kwargs)

    def get(self, *args, **kwargs):
        return self._call('get', *args, **kwargs)

    def post(self, *args, **kwargs):
        return self._call('post', *args, **kwargs)

    def put(self, *args, **kwargs):
        return self._call('put', *args, **kwargs)

    def delete(self, *args, **kwargs):
        return self._call('delete', *args, **kwargs)

    def patch(self, *args, **kwargs):
        return self._call('patch', *args, **kwargs)

    def head(self, *args, **kwargs):
        return self._call('head', *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._wrapped, name)


@contextmanager
def request_route(mode):
    previous = getattr(_ROUTE_LOCAL, 'proxy_url', None)
    _ROUTE_LOCAL.proxy_url = proxy_for_mode(mode)
    try:
        yield
    finally:
        _ROUTE_LOCAL.proxy_url = previous


def _state_path(core):
    return os.path.join(core.DOWNLOAD_DIR, '.network-routing.json')


def canonical_site(value):
    raw = str(value or '').strip()
    if not raw:
        return ''
    try:
        parsed = urlparse(raw if '://' in raw else '//' + raw)
        host = (parsed.hostname or '').lower().rstrip('.')
    except Exception:
        host = ''
    if host.startswith('www.'):
        host = host[4:]
    if not host:
        return ''

    if re.search(r'(^|\.)missav\d*\.', host):
        return 'missav'

    for domain, canonical in _ALIAS_HOSTS.items():
        if host == domain or host.endswith('.' + domain):
            return canonical
    return host


def _load(core):
    global _STATE
    try:
        with open(_state_path(core), 'r', encoding='utf-8') as file_obj:
            raw = json.load(file_obj)
        if not isinstance(raw, dict):
            return
        manual = raw.get('manual_rules') if isinstance(raw.get('manual_rules'), dict) else {}
        learned = raw.get('learned_rules') if isinstance(raw.get('learned_rules'), dict) else {}
        clean_manual = {
            str(key): value
            for key, value in manual.items()
            if value in ('direct', 'vpn') and str(key)
        }
        clean_learned = {}
        for key, value in learned.items():
            if not isinstance(value, dict) or value.get('mode') not in ('direct', 'vpn'):
                continue
            clean_learned[str(key)] = {
                'mode': value['mode'],
                'success_count': int(value.get('success_count') or 0),
                'updated_at': int(value.get('updated_at') or 0),
            }
        with _STATE_LOCK:
            _STATE = {
                'manual_rules': clean_manual,
                'learned_rules': clean_learned,
            }
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError, TypeError):
        pass


def _save(core):
    path = _state_path(core)
    tmp = path + '.tmp'
    with _STATE_LOCK:
        payload = {
            'manual_rules': dict(_STATE['manual_rules']),
            'learned_rules': {
                key: dict(value)
                for key, value in _STATE['learned_rules'].items()
            },
        }
    try:
        with open(tmp, 'w', encoding='utf-8') as file_obj:
            json.dump(payload, file_obj, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError as exc:
        print(f'[Routing] 규칙 저장 실패: {exc}', flush=True)


def snapshot():
    with _STATE_LOCK:
        return {
            'manual_rules': dict(_STATE['manual_rules']),
            'learned_rules': {
                key: dict(value)
                for key, value in _STATE['learned_rules'].items()
            },
        }


def resolve(url, override='auto'):
    override = str(override or 'auto').lower()
    site = canonical_site(url)
    if override in ('direct', 'vpn'):
        return {
            'site': site,
            'mode': override,
            'source': 'override',
            'fixed': True,
        }

    with _STATE_LOCK:
        manual = _STATE['manual_rules'].get(site)
        learned = _STATE['learned_rules'].get(site)

    if manual in ('direct', 'vpn'):
        return {
            'site': site,
            'mode': manual,
            'source': 'manual',
            'fixed': True,
        }
    if isinstance(learned, dict) and learned.get('mode') in ('direct', 'vpn'):
        return {
            'site': site,
            'mode': learned['mode'],
            'source': 'learned',
            'fixed': False,
        }
    return {
        'site': site,
        'mode': 'direct',
        'source': 'default',
        'fixed': False,
    }


def fallback_mode(mode):
    return 'vpn' if mode == 'direct' else 'direct'


def proxy_for_mode(mode):
    return VPN_PROXY_URL if mode == 'vpn' and VPN_PROXY_URL else None


def proxy_for_task(core, task_id):
    task = core.tasks.get(task_id) or {}
    return proxy_for_mode(task.get('network_mode'))


def apply_task_mode(core, task_id, mode, source):
    task = core.tasks.get(task_id)
    if not task:
        return
    task['network_mode'] = mode
    task['network_route_source'] = source
    core.save_tasks()


def prepare_fallback(core, task_id, next_mode):
    task = core.tasks.get(task_id)
    if not task:
        return
    task['status'] = '다운로드 중'
    task['speed_bps'] = 0
    task['network_fallbacks'] = int(task.get('network_fallbacks') or 0) + 1
    task['network_mode'] = next_mode
    core.save_tasks()


def learn_success(core, url, mode, source):
    if mode not in ('direct', 'vpn'):
        return
    # Explicit one-off overrides and manual rules are authoritative and should
    # never mutate the automatic learning table.
    if source in ('override', 'manual'):
        return
    site = canonical_site(url)
    if not site:
        return
    with _STATE_LOCK:
        current = _STATE['learned_rules'].get(site) or {}
        _STATE['learned_rules'][site] = {
            'mode': mode,
            'success_count': int(current.get('success_count') or 0) + 1,
            'updated_at': int(time.time()),
        }
    _save(core)
    print(f'[Routing] 학습 저장: {site} -> {mode}', flush=True)


def should_fallback(network_module, error_message):
    return bool(network_module.is_recoverable_failure(error_message))


def install(core):
    _load(core)

    # Replace the original download front-door so network selection is persisted
    # before a worker can pick the queued task.
    def handle_download_with_network():
        url = core.request.form.get('url', '').strip()
        if not url:
            return core.jsonify({'status': 'error', 'message': 'URL 입력'}), 400
        override = str(core.request.form.get('network_mode', 'auto') or 'auto').lower()
        if override not in ('auto', 'direct', 'vpn'):
            return core.jsonify({'status': 'error', 'message': '잘못된 네트워크 모드입니다.'}), 400

        task_id = str(core.uuid.uuid4())
        decision = resolve(url, override=override)
        core.tasks[task_id] = {
            'url': url,
            'status': '대기 중',
            'progress': '0%',
            'speed_bps': 0,
            'downloaded_bytes': 0,
            'total_bytes_estimate': 0,
            'network_override': override,
            'network_mode': decision['mode'],
            'network_route_source': decision['source'],
            'network_site': decision['site'],
            'network_fallbacks': 0,
        }
        core.save_tasks()
        core.download_queue.put(task_id)
        return core.jsonify({
            'status': 'success',
            'task_id': task_id,
            'network_mode': decision['mode'],
            'network_source': decision['source'],
        })

    if 'handle_download' in core.app.view_functions:
        core.app.view_functions['handle_download'] = handle_download_with_network

    @core.app.route('/api/routing', methods=['GET'])
    def teddy_routing_state():
        data = snapshot()
        data.update({
            'default_mode': 'direct',
            'fallback_mode': 'vpn',
            'learning_enabled': True,
        })
        return core.jsonify(data)

    @core.app.route('/api/routing/resolve', methods=['GET'])
    def teddy_routing_resolve():
        url = core.request.args.get('url', '')
        override = core.request.args.get('mode', 'auto')
        return core.jsonify(resolve(url, override=override))

    @core.app.route('/api/routing/manual', methods=['POST'])
    def teddy_routing_manual_add():
        payload = core.request.get_json(silent=True) or {}
        target = canonical_site(payload.get('target') or payload.get('url') or '')
        mode = str(payload.get('mode') or '').lower()
        if not target:
            return core.jsonify({'status': 'error', 'message': '사이트 URL 또는 도메인을 입력하세요.'}), 400
        if mode not in ('direct', 'vpn'):
            return core.jsonify({'status': 'error', 'message': 'Direct 또는 VPN을 선택하세요.'}), 400
        with _STATE_LOCK:
            _STATE['manual_rules'][target] = mode
        _save(core)
        print(f'[Routing] 수동 규칙 저장: {target} -> {mode}', flush=True)
        return core.jsonify({'status': 'success', 'site': target, 'mode': mode})

    @core.app.route('/api/routing/manual', methods=['DELETE'])
    def teddy_routing_manual_delete():
        payload = core.request.get_json(silent=True) or {}
        target = canonical_site(payload.get('target') or '') or str(payload.get('target') or '').strip().lower()
        if not target:
            return core.jsonify({'status': 'error', 'message': '삭제할 사이트가 필요합니다.'}), 400
        with _STATE_LOCK:
            existed = target in _STATE['manual_rules']
            _STATE['manual_rules'].pop(target, None)
        _save(core)
        return core.jsonify({'status': 'success', 'removed': existed})

    @core.app.route('/api/routing/learned', methods=['DELETE'])
    def teddy_routing_learned_delete():
        payload = core.request.get_json(silent=True) or {}
        target = canonical_site(payload.get('target') or '') or str(payload.get('target') or '').strip().lower()
        if not target:
            return core.jsonify({'status': 'error', 'message': '삭제할 사이트가 필요합니다.'}), 400
        with _STATE_LOCK:
            existed = target in _STATE['learned_rules']
            _STATE['learned_rules'].pop(target, None)
        _save(core)
        return core.jsonify({'status': 'success', 'removed': existed})

    print(
        '[Teddy] adaptive routing enabled: Direct first -> VPN fallback -> learn success',
        flush=True,
    )
