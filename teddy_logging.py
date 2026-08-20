import sys
import threading
import time
from collections import deque


MAX_LOG_LINES = 2000

_lock = threading.Lock()
_lines = deque(maxlen=MAX_LOG_LINES)
_next_seq = 1
_installed = False

# High-frequency browser polling is still written to real stdout/stderr, but
# omitted from the in-app viewer so useful download/VPN events stay readable.
_VIEWER_NOISE = (
    'GET /api/logs',
    'GET /api/tasks',
    'GET /api/network/status',
)


def _append_line(stream_name, text):
    global _next_seq
    clean = str(text).rstrip('\r')
    if not clean:
        return
    if any(token in clean for token in _VIEWER_NOISE):
        return
    with _lock:
        _lines.append({
            'seq': _next_seq,
            'ts': time.time(),
            'stream': stream_name,
            'text': clean,
        })
        _next_seq += 1


class _TeeStream:
    def __init__(self, original, stream_name):
        self._original = original
        self._stream_name = stream_name
        self._pending = ''
        self._pending_lock = threading.Lock()

    def write(self, data):
        if not isinstance(data, str):
            data = str(data)
        written = self._original.write(data)
        with self._pending_lock:
            self._pending += data
            while '\n' in self._pending:
                line, self._pending = self._pending.split('\n', 1)
                _append_line(self._stream_name, line)
        return written

    def flush(self):
        self._original.flush()

    def isatty(self):
        return bool(getattr(self._original, 'isatty', lambda: False)())

    def fileno(self):
        return self._original.fileno()

    @property
    def encoding(self):
        return getattr(self._original, 'encoding', 'utf-8')

    def __getattr__(self, name):
        return getattr(self._original, name)


def install_capture():
    """Tee Python stdout/stderr into a bounded in-memory ring buffer."""
    global _installed
    if _installed:
        return
    sys.stdout = _TeeStream(sys.stdout, 'stdout')
    sys.stderr = _TeeStream(sys.stderr, 'stderr')
    _installed = True
    print(f'[Teddy] web log capture enabled (last {MAX_LOG_LINES} lines)', flush=True)


def _snapshot(after=0, limit=400):
    limit = max(1, min(int(limit), 1000))
    after = max(0, int(after))
    with _lock:
        current = list(_lines)
        latest_seq = (_next_seq - 1)
    if after:
        selected = [item for item in current if item['seq'] > after][:limit]
    else:
        selected = current[-limit:]
    return selected, latest_seq


def install_routes(core):
    @core.app.route('/api/logs', methods=['GET'])
    def teddy_get_logs():
        try:
            after = int(core.request.args.get('after', '0') or 0)
        except (TypeError, ValueError):
            after = 0
        try:
            limit = int(core.request.args.get('limit', '400') or 400)
        except (TypeError, ValueError):
            limit = 400

        entries, latest_seq = _snapshot(after=after, limit=limit)
        return core.jsonify({
            'entries': entries,
            'latest_seq': latest_seq,
            'capacity': MAX_LOG_LINES,
        })

    print('[Teddy] web log API enabled', flush=True)
