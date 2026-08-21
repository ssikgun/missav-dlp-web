import asyncio
import threading

from curl_cffi import requests as cffi_requests
from curl_cffi.const import CurlHttpVersion


# Hitomi's recovered M3U8 core uses a much smaller dedicated worker pool than the
# GUI's general downloader connection setting. Keep 8 as the compatibility
# default, but allow controlled A/B tests from the persisted web settings.
ALLOWED_HLS_WORKERS = (2, 4, 8, 12, 16, 20, 24)
HLS_WORKERS = 8

# Keep the proven per-segment .parts path as the production-safe default. The
# optional RAM benchmark only moves the segment payload out of worker-thread disk
# I/O; the coordinator still persists the exact same .parts files, preserving
# pause/resume and crash recovery semantics for completed segments.
ALLOWED_HLS_WRITE_MODES = ('parts', 'ram')
HLS_WRITE_MODE = 'parts'

# Existing production transport: one persistent synchronous Session per worker.
# The async-pool benchmark uses one AsyncSession/AsyncCurl pool per active proxy,
# which is the closest curl_cffi analogue to a shared connection pool without
# sharing a single synchronous Curl easy handle across worker threads.
ALLOWED_HLS_TRANSPORT_MODES = ('per-worker', 'async-pool')
HLS_TRANSPORT_MODE = 'per-worker'

# Decouple scheduler width from AsyncSession's actual curl-handle pool. The first
# async benchmark used max_clients == workers (24). Keep 24 as the compatibility
# default while allowing a controlled Hitomi-like connection-reuse A/B test.
ALLOWED_HLS_POOL_CLIENTS = (4, 8, 12, 16, 24)
HLS_POOL_CLIENTS = 24

# curl_cffi/browser impersonation normally negotiates HTTP automatically (usually
# HTTP/2 when the route supports it). Hitomi's recovered requests.Session path is
# HTTP/1.1, so keep auto as the safe default and expose only a controlled v1 A/B.
ALLOWED_HLS_HTTP_VERSIONS = ('auto', 'v1')
HLS_HTTP_VERSION = 'auto'

_thread_local = threading.local()


def normalize_workers(value):
    try:
        workers = int(value)
    except (TypeError, ValueError):
        return HLS_WORKERS
    if workers not in ALLOWED_HLS_WORKERS:
        return HLS_WORKERS
    return workers


def workers_from_settings(settings):
    if not isinstance(settings, dict):
        return HLS_WORKERS
    return normalize_workers(settings.get('hls_workers', HLS_WORKERS))


def normalize_write_mode(value):
    mode = str(value or '').strip().lower()
    if mode not in ALLOWED_HLS_WRITE_MODES:
        return HLS_WRITE_MODE
    return mode


def write_mode_from_settings(settings):
    if not isinstance(settings, dict):
        return HLS_WRITE_MODE
    return normalize_write_mode(settings.get('hls_write_mode', HLS_WRITE_MODE))


def normalize_transport_mode(value):
    mode = str(value or '').strip().lower()
    if mode not in ALLOWED_HLS_TRANSPORT_MODES:
        return HLS_TRANSPORT_MODE
    return mode


def transport_mode_from_settings(settings):
    if not isinstance(settings, dict):
        return HLS_TRANSPORT_MODE
    return normalize_transport_mode(settings.get('hls_transport_mode', HLS_TRANSPORT_MODE))


def normalize_pool_clients(value):
    try:
        clients = int(value)
    except (TypeError, ValueError):
        return HLS_POOL_CLIENTS
    if clients not in ALLOWED_HLS_POOL_CLIENTS:
        return HLS_POOL_CLIENTS
    return clients


def pool_clients_from_settings(settings):
    if not isinstance(settings, dict):
        return HLS_POOL_CLIENTS
    return normalize_pool_clients(settings.get('hls_pool_clients', HLS_POOL_CLIENTS))


def normalize_http_version(value):
    mode = str(value or '').strip().lower()
    if mode not in ALLOWED_HLS_HTTP_VERSIONS:
        return HLS_HTTP_VERSION
    return mode


def http_version_from_settings(settings):
    if not isinstance(settings, dict):
        return HLS_HTTP_VERSION
    return normalize_http_version(settings.get('hls_http_version', HLS_HTTP_VERSION))


def transport_mode_for_task(core, task_id, settings):
    """Resolve the actual transport for one HLS execution.

    The shared AsyncSession pool is intentionally benchmark-only for Direct/Proxy.
    VPN keeps the proven per-worker Session path so a VPN recovery can invalidate a
    single worker and force a fresh CONNECT/TLS path without disrupting unrelated
    in-flight requests in a shared pool.
    """
    requested = transport_mode_from_settings(settings)
    if requested != 'async-pool':
        return requested
    task = core.tasks.get(task_id) or {}
    if task.get('network_mode') == 'vpn':
        return 'per-worker'
    return requested


def _proxy_for_task(core, task_id):
    try:
        import teddy_routing
        return str(teddy_routing.proxy_for_task(core, task_id) or '')
    except Exception:
        return ''


def _http_version_for_task(core, task_id):
    task = core.tasks.get(task_id) or {}
    return normalize_http_version(task.get('hls_http_version', HLS_HTTP_VERSION))


def _http_version_arg(mode):
    mode = normalize_http_version(mode)
    if mode == 'v1':
        return CurlHttpVersion.V1_1
    return None


def _actual_http_label(value):
    try:
        if value == CurlHttpVersion.V1_0:
            return '1.0'
        if value == CurlHttpVersion.V1_1:
            return '1.1'
        if value == CurlHttpVersion.V2_0:
            return '2'
        if hasattr(CurlHttpVersion, 'V3') and value == CurlHttpVersion.V3:
            return '3'
    except Exception:
        pass
    try:
        return str(int(value))
    except Exception:
        return str(value or '?')


def _record_actual_http(core, task_id, response):
    try:
        task = core.tasks.get(task_id)
        if task is not None:
            task['hls_http_version_actual'] = _actual_http_label(response.http_version)
    except Exception:
        pass


def _close_state(state):
    if not state:
        return
    session = state.get('session')
    if session is None:
        return
    try:
        session.close()
    except Exception:
        pass


def _invalidate_per_worker():
    state = getattr(_thread_local, 'state', None)
    _close_state(state)
    _thread_local.state = None


def _session_for(proxy_url, http_version):
    state = getattr(_thread_local, 'state', None)
    if (
        state
        and state.get('proxy_url') == proxy_url
        and state.get('http_version') == http_version
        and state.get('session') is not None
    ):
        return state['session']

    _close_state(state)
    session = cffi_requests.Session()
    _thread_local.state = {
        'proxy_url': proxy_url,
        'http_version': http_version,
        'session': session,
    }
    return session


class _AsyncPoolBridge:
    """Run one curl_cffi AsyncSession pool on a dedicated event-loop thread."""

    def __init__(self):
        self._loop = None
        self._thread = None
        self._start_lock = threading.Lock()
        self._state = None
        self._session_lock = None

    def _ensure_loop(self):
        if self._loop is not None and self._thread is not None and self._thread.is_alive():
            return
        with self._start_lock:
            if self._loop is not None and self._thread is not None and self._thread.is_alive():
                return
            ready = threading.Event()
            loop = asyncio.new_event_loop()

            def runner():
                asyncio.set_event_loop(loop)
                self._loop = loop
                ready.set()
                loop.run_forever()

            thread = threading.Thread(target=runner, name='teddy-hls-async-pool', daemon=True)
            self._thread = thread
            thread.start()
            if not ready.wait(5):
                raise RuntimeError('HLS async pool event loop failed to start')

    async def _ensure_session(self, proxy_url, max_clients, http_version):
        if self._session_lock is None:
            self._session_lock = asyncio.Lock()
        async with self._session_lock:
            state = self._state
            if (
                state
                and state.get('proxy_url') == proxy_url
                and state.get('max_clients') == max_clients
                and state.get('http_version') == http_version
                and state.get('session') is not None
            ):
                return state['session']

            old = state.get('session') if state else None
            self._state = None
            if old is not None:
                try:
                    await old.close()
                except Exception:
                    pass

            session = cffi_requests.AsyncSession(max_clients=max_clients)
            self._state = {
                'proxy_url': proxy_url,
                'max_clients': max_clients,
                'http_version': http_version,
                'session': session,
            }
            return session

    async def _get_async(self, proxy_url, max_clients, http_version, url, kwargs):
        session = await self._ensure_session(proxy_url, max_clients, http_version)
        return await session.get(url, **kwargs)

    def get(self, proxy_url, max_clients, http_version, url, kwargs, timeout):
        self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(
            self._get_async(proxy_url, max_clients, http_version, url, kwargs),
            self._loop,
        )
        return future.result(timeout=max(float(timeout) + 10.0, 20.0))


_async_pool = _AsyncPoolBridge()


def invalidate(mode='per-worker'):
    """Invalidate failed transport state without weakening VPN recovery semantics."""
    mode = normalize_transport_mode(mode)
    if mode == 'async-pool':
        # AsyncSession/AsyncCurl resets failed easy handles itself. Do not close the
        # whole shared pool for one segment failure because that would abort other
        # in-flight requests. A public-proxy rotation changes proxy_url and causes
        # _ensure_session() to replace the pool before the next request.
        return
    _invalidate_per_worker()


def get(core, task_id, url, *, impersonate, headers=None, timeout=45,
        transport_mode='per-worker', max_clients=None):
    """GET through the task's current route using the selected HLS transport.

    per-worker keeps one persistent synchronous Session per worker. async-pool uses
    one AsyncSession pool (up to max_clients curl handles) shared by the HLS task's
    worker calls. Public-proxy rotation is keyed by proxy_url; VPN tasks deliberately
    stay on per-worker transport through transport_mode_for_task(). HTTP version is
    captured per HLS execution in the task and keyed into session reuse so an A/B
    change starts a fresh connection topology after pause/resume.
    """
    proxy_url = _proxy_for_task(core, task_id)
    mode = normalize_transport_mode(transport_mode)
    http_version = _http_version_for_task(core, task_id)
    kwargs = {
        'impersonate': impersonate,
        'headers': headers or {},
        'timeout': timeout,
    }
    version_arg = _http_version_arg(http_version)
    if version_arg is not None:
        kwargs['http_version'] = version_arg
    if proxy_url:
        kwargs['proxies'] = {
            'http': proxy_url,
            'https': proxy_url,
        }

    if mode == 'async-pool':
        clients = normalize_pool_clients(max_clients or HLS_POOL_CLIENTS)
        response = _async_pool.get(proxy_url, clients, http_version, url, kwargs, timeout)
        _record_actual_http(core, task_id, response)
        return response

    session = _session_for(proxy_url, http_version)
    response = session.get(url, **kwargs)
    _record_actual_http(core, task_id, response)
    return response
