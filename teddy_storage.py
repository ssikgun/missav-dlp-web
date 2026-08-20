import os
import re
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


def ensure_site_dir(core, url, custom=False):
    key = site_key_for_url(url, custom=custom)
    path = os.path.join(core.DOWNLOAD_DIR, key)
    os.makedirs(path, exist_ok=True)
    return key, path


def relative_public_path(core, path):
    return os.path.relpath(path, core.DOWNLOAD_DIR).replace(os.sep, '/')


def _safe_public_path(core, relative):
    relative = str(relative or '').replace('\\', '/')
    if not relative or relative.startswith('/'):
        return None
    parts = [part for part in relative.split('/') if part not in ('', '.')]
    if not parts or any(part == '..' or part.startswith('.') for part in parts):
        return None
    root = os.path.realpath(core.DOWNLOAD_DIR)
    candidate = os.path.realpath(os.path.join(root, *parts))
    try:
        if os.path.commonpath([root, candidate]) != root:
            return None
    except ValueError:
        return None
    return candidate


def _recursive_files(core):
    items = []
    root = core.DOWNLOAD_DIR
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
            root = os.path.realpath(core.DOWNLOAD_DIR)
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

    print('[Teddy] site-aware storage enabled: recursive files + safe nested routes', flush=True)
