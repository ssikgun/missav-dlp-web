import threading
import time
from collections import deque


FAILURE_WINDOW_SECONDS = 60
FAILURE_COUNT_THRESHOLD = 10
FAILURE_SEGMENT_THRESHOLD = 5
TRIGGER_THROTTLE_SECONDS = 10

_lock = threading.Lock()
_events = {}
_last_trigger = {}


def _prune_locked(now):
    cutoff = now - FAILURE_WINDOW_SECONDS
    for task_id in list(_events):
        queue = _events[task_id]
        while queue and queue[0][0] < cutoff:
            queue.popleft()
        if not queue:
            _events.pop(task_id, None)
            _last_trigger.pop(task_id, None)


def _clear_locked():
    _events.clear()
    _last_trigger.clear()


def clear():
    with _lock:
        _clear_locked()


def snapshot():
    now = time.monotonic()
    with _lock:
        _prune_locked(now)
        rows = [
            (task_id, ts, segment)
            for task_id, queue in _events.items()
            for ts, segment, _reason in queue
        ]
    return {
        'auto_failure_count': len(rows),
        'auto_failure_segments': len({(task_id, segment) for task_id, _ts, segment in rows}),
        'auto_failure_threshold': FAILURE_COUNT_THRESHOLD,
        'auto_failure_segment_threshold': FAILURE_SEGMENT_THRESHOLD,
        'auto_failure_window_seconds': FAILURE_WINDOW_SECONDS,
    }


def note_failure(core, network_module, task_id, segment, reason):
    """Observe a recoverable VPN segment failure and rotate on sustained degradation."""
    if not core.settings.get('network_auto_recover', True):
        return False
    task = core.tasks.get(task_id)
    if not task or task.get('network_mode') != 'vpn':
        return False
    if task.get('status') in ('일시정지 요청 중', '일시정지'):
        return False
    if not network_module.is_recoverable_failure(reason):
        return False

    now = time.monotonic()
    segment = str(segment or 'unknown')
    reason = str(reason or '')
    with _lock:
        _prune_locked(now)
        queue = _events.setdefault(task_id, deque())
        queue.append((now, segment, reason))
        count = len(queue)
        distinct = len({item[1] for item in queue})
        oldest = queue[0][0]
        last_trigger = _last_trigger.get(task_id, 0.0)
        if count < FAILURE_COUNT_THRESHOLD or distinct < FAILURE_SEGMENT_THRESHOLD:
            return False
        if now - last_trigger < TRIGGER_THROTTLE_SECONDS:
            return False
        _last_trigger[task_id] = now

    summary = (
        f'{FAILURE_WINDOW_SECONDS}s 내 recoverable 오류 {count}회 / '
        f'서로 다른 세그먼트 {distinct}개 · 최근: {reason[:160]}'
    )
    print(f'[VPN 자동복구] 누적 오류 임계치 도달: {summary}', flush=True)
    recovered = network_module.auto_recover(
        core,
        task_id=task_id,
        reason=summary,
        failed_since=oldest,
    )
    if recovered:
        clear()
    return recovered


def install(core, network_module):
    core._teddy_vpn_failure_observer = lambda task_id, segment, reason: note_failure(
        core, network_module, task_id, segment, reason
    )

    original_status = core.app.view_functions.get('teddy_network_status')
    if original_status:
        def teddy_network_status_with_health():
            response = original_status()
            try:
                payload = response.get_json() or {}
            except Exception:
                return response
            payload.update(snapshot())
            return core.jsonify(payload)
        core.app.view_functions['teddy_network_status'] = teddy_network_status_with_health

    print(
        '[Teddy] VPN health monitor enabled: '
        f'{FAILURE_COUNT_THRESHOLD} failures / {FAILURE_SEGMENT_THRESHOLD} segments / '
        f'{FAILURE_WINDOW_SECONDS}s',
        flush=True,
    )
