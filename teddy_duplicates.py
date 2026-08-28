import threading
from urllib.parse import parse_qs, urlparse


_QUEUE_LOCK = threading.Lock()


def _host(parsed):
    host = (parsed.hostname or '').lower().rstrip('.')
    if host.startswith('www.'):
        host = host[4:]
    return host


def duplicate_key(url):
    """Return a stable key for queue duplicate detection without network I/O.

    Special sites get media-aware keys so common alternate URL forms still match.
    Generic URLs keep their full path/query (fragment excluded) to avoid false
    positives on sites where query parameters identify different media.
    """
    raw = str(url or '').strip()
    if not raw:
        return ''
    try:
        parsed = urlparse(raw)
    except Exception:
        return raw

    host = _host(parsed)
    path = parsed.path or '/'

    # YouTube: youtu.be/ID, watch?v=ID, shorts/ID and live/ID are the same media.
    if host == 'youtu.be' or host.endswith('.youtu.be'):
        video_id = path.strip('/').split('/', 1)[0]
        if video_id:
            return 'youtube:' + video_id
    if host == 'youtube.com' or host.endswith('.youtube.com') or host == 'youtube-nocookie.com' or host.endswith('.youtube-nocookie.com'):
        query = parse_qs(parsed.query or '')
        video_id = (query.get('v') or [''])[0]
        if not video_id:
            parts = [part for part in path.split('/') if part]
            if len(parts) >= 2 and parts[0] in ('shorts', 'live', 'embed'):
                video_id = parts[1]
        if video_id:
            return 'youtube:' + video_id

    # MissAV mirrors change over time. The final path component is the stable
    # video code in the custom extractor, so ignore mirror host/localized prefix.
    if host.startswith('missav') or '.missav' in host:
        parts = [part for part in path.split('/') if part]
        if parts:
            return 'missav:' + parts[-1].lower()

    scheme = (parsed.scheme or 'https').lower()
    normalized_path = path.rstrip('/') or '/'
    netloc = host
    if parsed.port:
        default_port = (scheme == 'http' and parsed.port == 80) or (scheme == 'https' and parsed.port == 443)
        if not default_port:
            netloc += ':' + str(parsed.port)
    return f'{scheme}://{netloc}{normalized_path}' + (('?' + parsed.query) if parsed.query else '')


def _is_terminal(task):
    status = str((task or {}).get('status') or '')
    return status.startswith('완료') or status == '취소됨'


def find_duplicate(core, url):
    wanted = duplicate_key(url)
    if not wanted:
        return None, None
    for task_id, task in core.tasks.items():
        if _is_terminal(task):
            continue
        if duplicate_key(task.get('url')) == wanted:
            return task_id, task
    return None, None


def find_duplicate_by_key(
    core,
    wanted_key,
    task_key,
):
    wanted_key = str(
        wanted_key
        or ''
    ).strip()

    if not wanted_key:
        return None, None

    if not callable(task_key):
        raise ValueError(
            'task key function required'
        )

    for task_id, task in core.tasks.items():
        if _is_terminal(task):
            continue

        existing_key = str(
            task_key(task)
            or ''
        ).strip()

        if existing_key == wanted_key:
            return task_id, task

    return None, None


def guarded_enqueue_by_key(
    core,
    wanted_key,
    task_key,
    creator,
):
    wanted_key = str(
        wanted_key
        or ''
    ).strip()

    if not wanted_key:
        raise ValueError(
            'duplicate key required'
        )

    if not callable(task_key):
        raise ValueError(
            'task key function required'
        )

    with _QUEUE_LOCK:
        task_id, task = (
            find_duplicate_by_key(
                core,
                wanted_key,
                task_key,
            )
        )

        if task_id:
            status = str(
                task.get('status')
                or '대기 중'
            )

            title = str(
                task.get('display_title')
                or task.get('filename')
                or ''
            ).strip()

            message = (
                '이미 다운로드 큐에 있는 항목입니다.'
            )

            if status.startswith('에러'):
                message = (
                    '이미 작업 목록에 있습니다. '
                    '기존 작업의 재시작을 사용하세요.'
                )

            print(
                f'[Duplicate] 추가 차단: '
                f'{wanted_key} · '
                f'task={task_id} · '
                f'status={status}',
                flush=True,
            )

            return core.jsonify({
                'status': 'duplicate',
                'message': message,
                'task_id': task_id,
                'task_status': status,
                'title': title,
            }), 409

        return creator()


def guarded_enqueue(
    core,
    url,
    creator,
):
    """Run task creation under the canonical duplicate queue lock."""
    url = str(url or '').strip()

    if not url:
        return creator()

    # Keep duplicate check + task creation/queue insertion atomic.
    with _QUEUE_LOCK:
        task_id, task = find_duplicate(
            core,
            url,
        )

        if task_id:
            status = str(
                task.get('status')
                or '대기 중'
            )

            title = str(
                task.get('display_title')
                or task.get('filename')
                or ''
            ).strip()

            message = (
                '이미 다운로드 큐에 있는 항목입니다.'
            )

            if status.startswith('에러'):
                message = (
                    '이미 작업 목록에 있습니다. '
                    '기존 작업의 재시작을 사용하세요.'
                )

            print(
                f'[Duplicate] 추가 차단: '
                f'{duplicate_key(url)} · '
                f'task={task_id} · '
                f'status={status}',
                flush=True,
            )

            return core.jsonify({
                'status': 'duplicate',
                'message': message,
                'task_id': task_id,
                'task_status': status,
                'title': title,
            }), 409

        return creator()


def install(core):
    original = core.app.view_functions.get(
        'handle_download'
    )

    if not original:
        return

    def handle_download_without_duplicates():
        url = core.request.form.get(
            'url',
            '',
        ).strip()

        return guarded_enqueue(
            core,
            url,
            original,
        )

    core.app.view_functions[
        'handle_download'
    ] = handle_download_without_duplicates

    print(
        '[Teddy] duplicate queue guard enabled',
        flush=True,
    )
