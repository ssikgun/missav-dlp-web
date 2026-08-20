import re
import sys
import threading
import time
from collections import deque


MAX_LOG_LINES = 2000

_lock = threading.Lock()
_lines = deque(maxlen=MAX_LOG_LINES)
_next_seq = 1
_installed = False

# ANSI terminal styling is useful in docker logs but should not be rendered as
# raw escape sequences in the browser log viewer.
_ANSI_ESCAPE_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

# High-frequency browser polling/static traffic is still written to real
# stdout/stderr, but omitted from the in-app viewer so useful events stay clear.
_VIEWER_NOISE = (
    'GET /api/logs',
    'GET /api/tasks',
    'GET /api/network/status',
    'GET /api/routing/resolve',
    'GET /static/',
    'GET /favicon.ico',
)


def _to_text(data):
    if isinstance(data, bytes):
        return data.decode('utf-8', errors='replace')
    return str(data)


def _clean_for_viewer(text):
    clean = _ANSI_ESCAPE_RE.sub('', _to_text(text)).rstrip('\r')
    # Some libraries hand a bytes repr to text streams; unwrap the common
    # b'...' / b"..." form only when it is obviously a single bytes literal.
    if len(clean) >= 3 and clean[:2] in ("b'", 'b"') and clean[-1] == clean[1]:
        try:
            import ast
            value = ast.literal_eval(clean)
            if isinstance(value, bytes):
                clean = value.decode('utf-8', errors='replace').rstrip('\r\n')
        except Exception:
            pass
    return clean


def _append_line(stream_name, text):
    global _next_seq
    clean = _clean_for_viewer(text)
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
        text = _to_text(data)
        written = self._original.write(text)
        with self._pending_lock:
            self._pending += text
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
