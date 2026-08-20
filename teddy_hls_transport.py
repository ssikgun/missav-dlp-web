import threading

from curl_cffi import requests as cffi_requests


# Keep the first performance comparison apples-to-apples with Hitomi's 8-connection test.
HLS_WORKERS = 8

_thread_local = threading.local()


def _proxy_for_task(core, task_id):
    try:
        import teddy_routing
        return str(teddy_routing.proxy_for_task(core, task_id) or '')
    except Exception:
        return ''


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


def invalidate():
    """Drop this worker thread's connection pool after a transport failure."""
    state = getattr(_thread_local, 'state', None)
    _close_state(state)
    _thread_local.state = None


def _session_for(proxy_url):
    state = getattr(_thread_local, 'state', None)
    if state and state.get('proxy_url') == proxy_url and state.get('session') is not None:
        return state['session']

    _close_state(state)
    session = cffi_requests.Session()
    _thread_local.state = {
        'proxy_url': proxy_url,
        'session': session,
    }
    return session


def get(core, task_id, url, *, impersonate, headers=None, timeout=45):
    """GET through the task's current route using one persistent Session per worker.

    A public-proxy rotation changes proxy_url and therefore replaces the Session.
    VPN rotations keep the same Gluetun proxy URL, so callers must invalidate()
    after a failed request before retrying; that guarantees a fresh CONNECT/TLS path.
    """
    proxy_url = _proxy_for_task(core, task_id)
    session = _session_for(proxy_url)
    kwargs = {
        'impersonate': impersonate,
        'headers': headers or {},
        'timeout': timeout,
    }
    if proxy_url:
        kwargs['proxies'] = {
            'http': proxy_url,
            'https': proxy_url,
        }
    return session.get(url, **kwargs)
