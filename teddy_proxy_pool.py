import ipaddress
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse


REFRESH_TTL_SECONDS = 30 * 60
SOURCE_TIMEOUT_SECONDS = 8
CHECK_TIMEOUT_SECONDS = 4.5
MAX_CANDIDATES = 48
MAX_HEALTHY = 12
CHECK_WORKERS = 12
TEST_URL = 'https://api.ipify.org?format=json'

# Public, no-key HTTP proxy feeds. We deliberately validate every candidate
# ourselves instead of trusting source health metadata.
SOURCES = (
    (
        'monosans',
        'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt',
    ),
    (
        'proxyscrape',
        'https://cdn.jsdelivr.net/gh/proxyscrape/free-proxy-list@main/proxies/protocols/http/data.txt',
    ),
    (
        'proxifly',
        'https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/http/data.txt',
    ),
)

_lock = threading.RLock()
_refresh_lock = threading.Lock()
_refresh_done = threading.Event()
_core = None
_state = {
    'enabled': True,
    'manual_proxies': [],
    'healthy': [],
    'candidate_count': 0,
    'last_refresh_at': 0,
    'last_refresh_duration_ms': 0,
    'last_error': '',
    'refreshing': False,
    'sources': {},
    'proxy_switch_count': 0,
    'last_switch_at': 0,
    'last_switch_reason': '',
}


def _state_path(core):
    return os.path.join(core.DOWNLOAD_DIR, '.proxy-pool.json')


def _load(core):
    try:
        with open(_state_path(core), 'r', encoding='utf-8') as file_obj:
            raw = json.load(file_obj)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return
    if not isinstance(raw, dict):
        return
    manual = []
    for value in raw.get('manual_proxies') or []:
        normalized = _normalize_proxy(value)
        if normalized and normalized not in manual:
            manual.append(normalized)
    with _lock:
        _state['enabled'] = bool(raw.get('enabled', True))
        _state['manual_proxies'] = manual[:100]
        _state['proxy_switch_count'] = int(raw.get('proxy_switch_count') or 0)
        _state['last_switch_at'] = int(raw.get('last_switch_at') or 0)
        _state['last_switch_reason'] = str(raw.get('last_switch_reason') or '')[:240]


def _save(core):
    with _lock:
        payload = {
            'enabled': bool(_state['enabled']),
            'manual_proxies': list(_state['manual_proxies']),
            'proxy_switch_count': int(_state['proxy_switch_count']),
            'last_switch_at': int(_state['last_switch_at']),
            'last_switch_reason': str(_state['last_switch_reason']),
        }
    path = _state_path(core)
    tmp = path + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as file_obj:
            json.dump(payload, file_obj, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError as exc:
        print(f'[Proxy] 설정 저장 실패: {exc}', flush=True)


def _normalize_proxy(value):
    raw = str(value or '').strip()
    if not raw or raw.startswith('#'):
        return ''
    if '://' not in raw:
        raw = 'http://' + raw
    try:
        parsed = urlparse(raw)
        if parsed.scheme.lower() not in ('http', 'https'):
            return ''
        host = parsed.hostname or ''
        port = int(parsed.port or 0)
    except (ValueError, TypeError):
        return ''
    if not host or port < 1 or port > 65535:
        return ''

    # Automated public lists should never be allowed to point at the NAS/LAN.
    # Restrict the pool to globally routable IP literals.
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return ''
    if not address.is_global:
        return ''
    return f'{parsed.scheme.lower()}://{address.compressed}:{port}'


def _fetch_source(core, name, url):
    started = time.monotonic()
    try:
        response = core.cffi_requests.get(
            url,
            impersonate='firefox135',
            timeout=SOURCE_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            raise RuntimeError(f'HTTP {response.status_code}')
        proxies = []
        for line in response.text.splitlines():
            normalized = _normalize_proxy(line)
            if normalized and normalized not in proxies:
                proxies.append(normalized)
        return name, proxies, '', int((time.monotonic() - started) * 1000)
    except Exception as exc:
        return name, [], str(exc), int((time.monotonic() - started) * 1000)


def _candidate_list(core):
    with _lock:
        manual = list(_state['manual_proxies'])

    source_rows = {}
    source_meta = {}
    with ThreadPoolExecutor(max_workers=len(SOURCES)) as executor:
        futures = [executor.submit(_fetch_source, core, name, url) for name, url in SOURCES]
        for future in as_completed(futures):
            name, proxies, error, elapsed_ms = future.result()
            source_rows[name] = proxies
            source_meta[name] = {
                'count': len(proxies),
                'error': error,
                'elapsed_ms': elapsed_ms,
            }

    candidates = []
    origins = {}

    def add(proxy, origin):
        if proxy and proxy not in origins and len(candidates) < MAX_CANDIDATES:
            candidates.append(proxy)
            origins[proxy] = origin

    for proxy in manual:
        add(proxy, 'manual')

    # Interleave sources so one feed cannot monopolize the validation budget.
    depth = 0
    while len(candidates) < MAX_CANDIDATES:
        added = False
        for name, _url in SOURCES:
            rows = source_rows.get(name) or []
            if depth < len(rows):
                add(rows[depth], name)
                added = True
                if len(candidates) >= MAX_CANDIDATES:
                    break
        if not added:
            break
        depth += 1

    return candidates, origins, source_meta


def _check_proxy(core, proxy, origin):
    started = time.monotonic()
    try:
        response = core.cffi_requests.get(
            TEST_URL,
            impersonate='firefox135',
            timeout=CHECK_TIMEOUT_SECONDS,
            proxies={'http': proxy, 'https': proxy},
        )
        if response.status_code != 200:
            return None
        data = response.json()
        exit_ip = str(data.get('ip') or '').strip()
        try:
            if not ipaddress.ip_address(exit_ip).is_global:
                return None
        except ValueError:
            return None
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return {
            'proxy': proxy,
            'source': origin,
            'latency_ms': elapsed_ms,
            'exit_ip': exit_ip,
            'checked_at': int(time.time()),
        }
    except Exception:
        return None


def refresh(core=None):
    core = core or _core
    if core is None:
        return False
    if not _refresh_lock.acquire(blocking=False):
        return False

    started = time.monotonic()
    _refresh_done.clear()
    with _lock:
        _state['refreshing'] = True
        _state['last_error'] = ''
    try:
        candidates, origins, source_meta = _candidate_list(core)
        healthy = []
        if candidates:
            with ThreadPoolExecutor(max_workers=min(CHECK_WORKERS, len(candidates))) as executor:
                futures = {
                    executor.submit(_check_proxy, core, proxy, origins.get(proxy, 'unknown')): proxy
                    for proxy in candidates
                }
                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        healthy.append(result)
        healthy.sort(key=lambda row: row.get('latency_ms', 999999))
        healthy = healthy[:MAX_HEALTHY]

        with _lock:
            _state['healthy'] = healthy
            _state['candidate_count'] = len(candidates)
            _state['sources'] = source_meta
            _state['last_refresh_at'] = int(time.time())
            _state['last_refresh_duration_ms'] = int((time.monotonic() - started) * 1000)
            _state['last_error'] = '' if healthy else '검증을 통과한 HTTP 프록시가 없습니다.'
        print(
            f'[Proxy] pool 갱신 완료: 후보 {len(candidates)}개 -> 정상 {len(healthy)}개'
            + (f" · 최고 {healthy[0]['latency_ms']}ms" if healthy else ''),
            flush=True,
        )
        return bool(healthy)
    except Exception as exc:
        with _lock:
            _state['last_error'] = str(exc)[:300]
        print(f'[Proxy] pool 갱신 실패: {exc}', flush=True)
        return False
    finally:
        with _lock:
            _state['refreshing'] = False
        _refresh_done.set()
        _refresh_lock.release()


def _refresh_worker(core, delay=0.0):
    if delay:
        time.sleep(delay)
    refresh(core)


def start_refresh(core=None, delay=0.0):
    core = core or _core
    if core is None:
        return False
    with _lock:
        if _state['refreshing']:
            return False
    worker = threading.Thread(
        target=_refresh_worker,
        args=(core, delay),
        name='free-proxy-refresh',
        daemon=True,
    )
    worker.start()
    return True


def _needs_refresh_locked():
    last = int(_state.get('last_refresh_at') or 0)
    return not last or time.time() - last >= REFRESH_TTL_SECONDS


def ensure_ready(core=None, wait_seconds=15):
    core = core or _core
    if core is None:
        return False
    with _lock:
        if not _state['enabled']:
            return False
        if _state['healthy'] and not _needs_refresh_locked():
            return True
        has_healthy = bool(_state['healthy'])
        refreshing = bool(_state['refreshing'])
    if has_healthy:
        if not refreshing:
            start_refresh(core)
        return True
    if not refreshing:
        start_refresh(core)
    _refresh_done.wait(max(0, float(wait_seconds)))
    with _lock:
        return bool(_state['enabled'] and _state['healthy'])


def current_proxy(core=None):
    core = core or _core
    if core is not None:
        with _lock:
            if _state['healthy'] and _needs_refresh_locked() and not _state['refreshing']:
                start_refresh(core)
    with _lock:
        if not _state['enabled'] or not _state['healthy']:
            return None
        return _state['healthy'][0]['proxy']


def current_record():
    with _lock:
        return dict(_state['healthy'][0]) if _state['healthy'] else {}


def rotate_after_failure(core=None, reason=''):
    core = core or _core
    if core is None:
        return False
    with _lock:
        if not _state['enabled'] or not _state['healthy']:
            return False
        old = _state['healthy'].pop(0)
        if not _state['healthy']:
            new = None
        else:
            new = dict(_state['healthy'][0])
            _state['proxy_switch_count'] = int(_state['proxy_switch_count']) + 1
            _state['last_switch_at'] = int(time.time())
            _state['last_switch_reason'] = str(reason or '')[:240]
    if not new:
        print(f"[Proxy] 사용 가능 후보 소진: {old.get('proxy', '')}", flush=True)
        start_refresh(core)
        return False
    _save(core)
    print(
        f"[Proxy] 실패 프록시 제외 -> 다음 후보: {old.get('proxy', '')} -> {new.get('proxy', '')} "
        f"({new.get('latency_ms', 0)}ms)",
        flush=True,
    )
    return True


def snapshot():
    with _lock:
        current = dict(_state['healthy'][0]) if _state['healthy'] else {}
        return {
            'enabled': bool(_state['enabled']),
            'ready': bool(_state['healthy']),
            'refreshing': bool(_state['refreshing']),
            'candidate_count': int(_state['candidate_count']),
            'healthy_count': len(_state['healthy']),
            'current_proxy': current.get('proxy', ''),
            'current_exit_ip': current.get('exit_ip', ''),
            'current_latency_ms': int(current.get('latency_ms') or 0),
            'current_source': current.get('source', ''),
            'last_refresh_at': int(_state['last_refresh_at']),
            'last_refresh_duration_ms': int(_state['last_refresh_duration_ms']),
            'last_error': str(_state['last_error']),
            'sources': {key: dict(value) for key, value in _state['sources'].items()},
            'manual_proxies': list(_state['manual_proxies']),
            'proxy_switch_count': int(_state['proxy_switch_count']),
            'last_switch_at': int(_state['last_switch_at']),
            'last_switch_reason': str(_state['last_switch_reason']),
        }


def install(core, routing_module, network_module):
    global _core
    _core = core
    _load(core)
    routing_module.set_proxy_provider(lambda: current_proxy(core))

    @core.app.route('/api/proxy/status', methods=['GET'])
    def teddy_proxy_status():
        return core.jsonify(snapshot())

    @core.app.route('/api/proxy/refresh', methods=['POST'])
    def teddy_proxy_refresh():
        started = start_refresh(core)
        return core.jsonify({
            'status': 'success',
            'started': bool(started),
            'message': '무료 프록시 갱신을 시작했습니다.' if started else '이미 프록시를 갱신하는 중입니다.',
        })

    @core.app.route('/api/proxy/enabled', methods=['PUT'])
    def teddy_proxy_enabled():
        payload = core.request.get_json(silent=True) or {}
        enabled = payload.get('enabled')
        if not isinstance(enabled, bool):
            return core.jsonify({'status': 'error', 'message': 'enabled 값이 필요합니다.'}), 400
        with _lock:
            _state['enabled'] = enabled
        _save(core)
        if enabled:
            start_refresh(core)
        return core.jsonify({'status': 'success', 'enabled': enabled})

    @core.app.route('/api/proxy/manual', methods=['POST'])
    def teddy_proxy_manual_add():
        payload = core.request.get_json(silent=True) or {}
        values = payload.get('proxies')
        if isinstance(values, str):
            values = re.split(r'[\s,]+', values)
        if not isinstance(values, list):
            return core.jsonify({'status': 'error', 'message': '프록시 목록이 필요합니다.'}), 400
        added = []
        with _lock:
            for value in values:
                normalized = _normalize_proxy(value)
                if normalized and normalized not in _state['manual_proxies']:
                    _state['manual_proxies'].append(normalized)
                    added.append(normalized)
            _state['manual_proxies'] = _state['manual_proxies'][:100]
        _save(core)
        if added:
            start_refresh(core)
        return core.jsonify({'status': 'success', 'added': added, 'count': len(added)})

    @core.app.route('/api/proxy/manual', methods=['DELETE'])
    def teddy_proxy_manual_delete():
        payload = core.request.get_json(silent=True) or {}
        normalized = _normalize_proxy(payload.get('proxy') or '')
        if not normalized:
            return core.jsonify({'status': 'error', 'message': '삭제할 프록시가 필요합니다.'}), 400
        with _lock:
            existed = normalized in _state['manual_proxies']
            _state['manual_proxies'] = [p for p in _state['manual_proxies'] if p != normalized]
        _save(core)
        return core.jsonify({'status': 'success', 'removed': existed})

    # Refresh in the background so app startup and existing task restoration are
    # never blocked by volatile public proxy feeds.
    if _state['enabled']:
        start_refresh(core, delay=2.0)

    print('[Teddy] free proxy pool enabled: auto collect -> HTTPS verify -> fastest candidates', flush=True)
