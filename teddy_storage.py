import os
import re
import shutil
import uuid
from urllib.parse import urlparse


_SITE_ALIASES = {
    'youtube.com': 'youtube',
    'youtu.be': 'youtube',
    'youtube-nocookie.com': 'youtube',
    'x.com': 'twitter',
    'twitter.com': 'twitter',
    'vimeo.com': 'vimeo',
    'tiktok.com': 'tiktok',
    'instagram.com': 'instagram',
    'facebook.com': 'facebook',
    'fb.watch': 'facebook',
    'twitch.tv': 'twitch',
    'soundcloud.com': 'soundcloud',
    'dailymotion.com': 'dailymotion',
    'bilibili.com': 'bilibili',
}


class PublishError(RuntimeError):
    pass


def _sanitize_folder(value):
    value = re.sub(r'[^a-z0-9._-]+', '-', str(value or '').lower()).strip('.-_')
    return value[:64] or 'other'


def site_key_for_url(url, custom=False):
    """Return a stable, human-readable site folder for a download URL."""
    if custom:
        return 'missav'

    try:
        host = (urlparse(url).hostname or '').lower().rstrip('.')
    except Exception:
        host = ''
    if host.startswith('www.'):
        host = host[4:]

    if re.search(r'(^|\.)missav\d*\.', host):
        return 'missav'

    for domain, key in _SITE_ALIASES.items():
        if host == domain or host.endswith('.' + domain):
            return key

    parts = [part for part in host.split('.') if part]
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in {'co', 'com', 'net', 'org', 'ac', 'go'}:
        return _sanitize_folder(parts[-3])
    if len(parts) >= 2:
        return _sanitize_folder(parts[-2])
    if parts:
        return _sanitize_folder(parts[0])
    return 'other'


def work_root(core):
    return os.path.realpath(core.DOWNLOAD_DIR)


def public_root(core):
    """Return the user-visible completed-file root.

    Legacy/NAS deployments keep the old single-root behavior when
    TEDDY_FINAL_DIR is unset.  The LXC deployment sets TEDDY_FINAL_DIR=/final,
    while /downloads remains local NVMe work/state storage.
    """
    configured = str(os.environ.get('TEDDY_FINAL_DIR') or '').strip()
    return os.path.realpath(configured or core.DOWNLOAD_DIR)


def ensure_site_dir(core, url, custom=False):
    """Return a local work directory for a site (legacy helper)."""
    key = site_key_for_url(url, custom=custom)
    path = os.path.join(work_root(core), key)
    os.makedirs(path, exist_ok=True)
    return key, path


def ensure_public_site_dir(core, site_key):
    key = _sanitize_folder(site_key)
    root = public_root(core)
    if not os.path.isdir(root):
        raise PublishError(f'완료 저장소가 없습니다: {root}')
    path = os.path.join(root, key)
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as exc:
        raise PublishError(f'완료 저장소 폴더 생성 실패: {exc}') from exc
    return key, path


def relative_public_path(core, path):
    return os.path.relpath(path, public_root(core)).replace(os.sep, '/')


def relative_work_path(core, path):
    root = work_root(core)
    real = os.path.realpath(path)
    try:
        if os.path.commonpath([root, real]) != root:
            raise PublishError('로컬 완료 파일이 작업 디렉터리 밖에 있습니다.')
    except ValueError as exc:
        raise PublishError('로컬 완료 파일 경로를 확인할 수 없습니다.') from exc
    return os.path.relpath(real, root).replace(os.sep, '/')


def _safe_under(root, relative, allow_hidden=False):
    relative = str(relative or '').replace('\\', '/')
    if not relative or relative.startswith('/'):
        return None
    parts = [part for part in relative.split('/') if part not in ('', '.')]
    if not parts or any(part == '..' for part in parts):
        return None
    if not allow_hidden and any(part.startswith('.') for part in parts):
        return None
    root = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(root, *parts))
    try:
        if os.path.commonpath([root, candidate]) != root:
            return None
    except ValueError:
        return None
    return candidate


def _safe_work_path(core, relative):
    return _safe_under(work_root(core), relative, allow_hidden=True)


def _safe_public_path(core, relative):
    return _safe_under(public_root(core), relative, allow_hidden=False)


def _fsync_directory(path):
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _copy_to_partial(source, partial):
    with open(source, 'rb') as src, open(partial, 'wb') as dst:
        shutil.copyfileobj(src, dst, length=8 * 1024 * 1024)
        dst.flush()
        os.fsync(dst.fileno())
    try:
        shutil.copystat(source, partial)
    except OSError:
        pass


def publish_completed_file(core, source_path, site_key):
    """Publish one fully finished local file to the completed-file root.

    Same-filesystem deployments use os.replace directly.  Cross-filesystem
    deployments (local NVMe -> NAS NFS) copy to a hidden partial file first and
    only then rename inside the final filesystem.  The local source is removed
    only after the final rename succeeds.
    """
    source = os.path.realpath(source_path)
    root = work_root(core)
    try:
        if os.path.commonpath([root, source]) != root:
            raise PublishError('게시 원본이 로컬 작업 디렉터리 밖에 있습니다.')
    except ValueError as exc:
        raise PublishError('게시 원본 경로를 확인할 수 없습니다.') from exc
    if not os.path.isfile(source):
        raise PublishError(f'로컬 완료 파일이 없습니다: {source}')

    _key, final_dir = ensure_public_site_dir(core, site_key)
    destination = os.path.join(final_dir, os.path.basename(source))
    if os.path.realpath(destination) == source:
        return destination

    try:
        same_filesystem = os.stat(source).st_dev == os.stat(final_dir).st_dev
    except OSError as exc:
        raise PublishError(f'저장소 상태 확인 실패: {exc}') from exc

    if same_filesystem:
        try:
            os.replace(source, destination)
            return destination
        except OSError as exc:
            raise PublishError(f'완료 파일 이동 실패: {exc}') from exc

    partial = os.path.join(
        final_dir,
        f'.{os.path.basename(source)}.{uuid.uuid4().hex}.partial',
    )
    try:
        _copy_to_partial(source, partial)
        if os.path.getsize(partial) != os.path.getsize(source):
            raise PublishError('NAS 복사 후 파일 크기 검증에 실패했습니다.')
        os.replace(partial, destination)
        _fsync_directory(final_dir)
        os.remove(source)
        return destination
    except PublishError:
        try:
            os.remove(partial)
        except OSError:
            pass
        raise
    except OSError as exc:
        try:
            os.remove(partial)
        except OSError:
            pass
        raise PublishError(f'NAS 완료 파일 게시 실패: {exc}') from exc


def has_pending_result(core, task_id):
    task = core.tasks.get(task_id) or {}
    return bool(task.get('local_result_path'))


def _pending_paths(task):
    main = str(task.get('local_result_path') or '').strip()
    raw = task.get('local_result_paths')
    paths = []
    if isinstance(raw, list):
        for value in raw:
            value = str(value or '').strip()
            if value and value not in paths:
                paths.append(value)
    if main and main not in paths:
        paths.append(main)
    if main in paths:
        paths = [value for value in paths if value != main] + [main]
    return main, paths


def publish_pending_task(core, task_id):
    """Publish every completed local output for a task, main media last."""
    task = core.tasks.get(task_id)
    if not task:
        raise PublishError('작업이 없습니다.')
    main_rel, paths = _pending_paths(task)
    if not main_rel or not paths:
        raise PublishError('게시할 로컬 완료 결과가 없습니다.')

    site_key = str(task.get('storage_folder') or 'other')
    _key, final_dir = ensure_public_site_dir(core, site_key)
    published_main = ''
    local_parents = set()

    for relative in paths:
        source = _safe_work_path(core, relative)
        if not source:
            raise PublishError(f'잘못된 로컬 완료 경로입니다: {relative}')
        local_parents.add(os.path.dirname(source))
        destination = os.path.join(final_dir, os.path.basename(source))
        if os.path.isfile(source):
            published = publish_completed_file(core, source, site_key)
        elif os.path.isfile(destination):
            # Crash recovery: the NAS rename may have completed just before the
            # task state was persisted.  Treat the already-present final file as
            # published instead of downloading it again.
            published = destination
        else:
            raise PublishError(f'로컬/최종 완료 파일을 찾을 수 없습니다: {relative}')
        if relative == main_rel:
            published_main = published

    if not published_main:
        raise PublishError('주 완료 파일 게시 결과를 확인하지 못했습니다.')

    final_size = os.path.getsize(published_main)
    task['status'] = '완료'
    task['progress'] = '100%'
    task['speed_bps'] = 0
    task['filename'] = relative_public_path(core, published_main)
    task['filesize'] = final_size
    task['downloaded_bytes'] = final_size
    task['total_bytes_estimate'] = final_size
    task.pop('local_result_path', None)
    task.pop('local_result_paths', None)
    task.pop('last_error_detail', None)
    core.save_tasks()

    work = work_root(core)
    for parent in sorted(local_parents, key=len, reverse=True):
        if parent == work:
            continue
        try:
            if os.path.commonpath([work, parent]) == work and os.path.basename(parent).startswith('.'):
                os.rmdir(parent)
        except (OSError, ValueError):
            pass
    return published_main


def mark_publish_error(core, task_id, exc):
    message = str(exc or 'unknown storage error')
    task = core.tasks.get(task_id)
    if task:
        task['status'] = f'에러: NAS 저장 실패: {message[:80]}'
        task['progress'] = '99%'
        task['speed_bps'] = 0
        task['last_error_detail'] = f'완료 파일 게시 실패: {message}'[:1000]
        core.save_tasks()
    print(f'[Storage] 완료 파일 게시 실패: {message}', flush=True)
    return {
        'status': 'error',
        'error': f'완료 저장소 게시 실패: {message}',
        'error_kind': 'storage',
    }


def cleanup_local_results(core, task):
    _main, paths = _pending_paths(task or {})
    for relative in paths:
        path = _safe_work_path(core, relative)
        if not path or not os.path.isfile(path):
            continue
        try:
            os.remove(path)
        except OSError:
            pass


def _recursive_files(core):
    items = []
    root = public_root(core)
    if not os.path.isdir(root):
        return items

    for current, dirs, files in os.walk(root):
        dirs[:] = [name for name in dirs if not name.startswith('.')]
        for name in files:
            if name.startswith('.'):
                continue
            path = os.path.join(current, name)
            if not os.path.isfile(path):
                continue
            try:
                stat = os.stat(path)
            except OSError:
                continue
            items.append({
                'name': relative_public_path(core, path),
                'size': stat.st_size,
                'modified': stat.st_mtime,
            })
    items.sort(key=lambda item: item['modified'], reverse=True)
    return items


def install_file_routes(core):
    """Make the existing file manager recursive and safe for site subfolders."""
    def list_files_recursive():
        return core.jsonify(_recursive_files(core))

    if 'list_files' in core.app.view_functions:
        core.app.view_functions['list_files'] = list_files_recursive

    def delete_file_nested(filename):
        path = _safe_public_path(core, filename)
        if not path:
            return core.jsonify({'status': 'error', 'message': '잘못된 파일 경로입니다.'}), 400
        if not os.path.isfile(path):
            return core.jsonify({'status': 'error', 'message': '파일이 없습니다.'}), 404
        try:
            os.remove(path)
            parent = os.path.dirname(path)
            root = public_root(core)
            while parent != root and os.path.commonpath([root, parent]) == root:
                try:
                    os.rmdir(parent)
                except OSError:
                    break
                parent = os.path.dirname(parent)
            return core.jsonify({'status': 'success', 'message': '파일을 삭제했습니다.'})
        except OSError as exc:
            return core.jsonify({'status': 'error', 'message': f'파일 삭제 실패: {exc}'}), 500

    if 'delete_file' in core.app.view_functions:
        core.app.view_functions['delete_file'] = delete_file_nested

    def download_file_nested(filename):
        path = _safe_public_path(core, filename)
        if not path:
            return core.Response(status=400)
        if not os.path.isfile(path):
            return core.Response(status=404)
        return core.send_file(path, as_attachment=True, download_name=os.path.basename(path), conditional=True)

    def stream_file_nested(filename):
        path = _safe_public_path(core, filename)
        if not path:
            return core.Response(status=400)
        if not os.path.isfile(path):
            return core.Response(status=404)
        return core.send_file(path, conditional=True)

    existing_rules = {rule.rule for rule in core.app.url_map.iter_rules()}
    if '/api/files/<path:filename>/download' not in existing_rules:
        core.app.add_url_rule(
            '/api/files/<path:filename>/download',
            endpoint='teddy_download_file',
            view_func=download_file_nested,
            methods=['GET'],
        )
    if '/api/files/<path:filename>/stream' not in existing_rules:
        core.app.add_url_rule(
            '/api/files/<path:filename>/stream',
            endpoint='teddy_stream_file',
            view_func=stream_file_nested,
            methods=['GET'],
        )

    original_delete_task = core.app.view_functions.get('delete_task')
    if original_delete_task:
        def delete_task_with_local_cleanup(task_id):
            task = core.tasks.get(task_id)
            active = task and task.get('status') in ('다운로드 중', '일시정지 요청 중', '대기 중')
            if task and not active:
                cleanup_local_results(core, task)
            return original_delete_task(task_id)
        core.app.view_functions['delete_task'] = delete_task_with_local_cleanup

    print(
        f'[Teddy] site-aware storage enabled: work={work_root(core)} '
        f'final={public_root(core)}',
        flush=True,
    )
