import glob
import os
import shutil
import threading
import time


_save_lock = threading.Lock()
_last_saved = {}


def is_custom_site(core, url):
    try:
        return bool(core.MyCustomMissAV.suitable(url))
    except Exception:
        return False


def _task_temp_dir(core, task_id):
    return os.path.join(core.DOWNLOAD_DIR, f'.{task_id}.ytdlp')


def _format_selector(core):
    quality = str(core.settings.get('video_quality', 'best') or 'best')
    if quality.isdigit():
        height = int(quality)
        return (
            f'bv*[height<={height}][ext=mp4]+ba[ext=m4a]/'
            f'b[height<={height}][ext=mp4]/'
            f'bv*[height<={height}]+ba/b[height<={height}]'
        )
    return 'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b'


def _maybe_save(core, task_id, force=False):
    now = time.monotonic()
    with _save_lock:
        previous = _last_saved.get(task_id, 0.0)
        if not force and now - previous < 1.0:
            return
        _last_saved[task_id] = now
    core.save_tasks()


def _store_metadata(core, task_id, info):
    task = core.tasks.get(task_id)
    if not task:
        return
    title = info.get('title') or info.get('fulltitle') or task.get('url')
    thumb = info.get('thumbnail') or ''
    extractor = info.get('extractor_key') or info.get('extractor') or ''
    task['engine'] = 'yt-dlp'
    task['display_title'] = title
    task['thumbnail_url'] = thumb
    task['extractor'] = extractor


def _progress_fraction(data):
    downloaded = int(data.get('downloaded_bytes') or 0)
    total = int(data.get('total_bytes') or data.get('total_bytes_estimate') or 0)
    if total > 0:
        return downloaded, total, min(max(downloaded / total, 0.0), 1.0)

    fragment_index = int(data.get('fragment_index') or 0)
    fragment_count = int(data.get('fragment_count') or 0)
    if fragment_count > 0:
        return downloaded, 0, min(max(fragment_index / fragment_count, 0.0), 1.0)
    return downloaded, total, None


def _find_final_path(core, ydl, info):
    candidates = []
    if isinstance(info, dict):
        for key in ('filepath', '_filename'):
            value = info.get(key)
            if value:
                candidates.append(value)
        for item in reversed(info.get('requested_downloads') or []):
            if isinstance(item, dict):
                value = item.get('filepath') or item.get('_filename')
                if value:
                    candidates.append(value)
        try:
            candidates.append(ydl.prepare_filename(info))
        except Exception:
            pass

    for path in candidates:
        if path and os.path.isfile(path):
            return path

    video_id = str((info or {}).get('id') or '')
    if video_id:
        pattern = os.path.join(core.DOWNLOAD_DIR, f'*{glob.escape(video_id)}*')
        matches = [path for path in glob.glob(pattern) if os.path.isfile(path)]
        if matches:
            return max(matches, key=os.path.getmtime)
    return ''


def download_generic(core, reliability, task_id, url):
    temp_dir = _task_temp_dir(core, task_id)
    os.makedirs(temp_dir, exist_ok=True)
    last_filename = {'path': ''}

    def progress_hook(data):
        task = core.tasks.get(task_id)
        if not task:
            raise core.DownloadCancelled()
        if task.get('status') in ('일시정지 요청 중', '일시정지'):
            raise reliability.DownloadPaused()

        info = data.get('info_dict') or {}
        _store_metadata(core, task_id, info)
        status = data.get('status')

        if status == 'downloading':
            downloaded, total, fraction = _progress_fraction(data)
            task['downloaded_bytes'] = downloaded
            task['total_bytes_estimate'] = total
            task['speed_bps'] = int(data.get('speed') or 0)
            if fraction is not None:
                task['progress'] = f'{int(fraction * 100)}%'
            filename = data.get('filename')
            if filename:
                last_filename['path'] = filename
            _maybe_save(core, task_id)
        elif status == 'finished':
            task['speed_bps'] = 0
            task['progress'] = '99%'
            filename = data.get('filename')
            if filename:
                last_filename['path'] = filename
            _maybe_save(core, task_id, force=True)

    opts = {
        'quiet': False,
        'no_warnings': False,
        'noplaylist': True,
        'continuedl': True,
        'nopart': False,
        'retries': 8,
        'fragment_retries': 8,
        'socket_timeout': 30,
        'format': _format_selector(core),
        'merge_output_format': 'mp4',
        'paths': {
            'home': core.DOWNLOAD_DIR,
            'temp': temp_dir,
        },
        'outtmpl': {
            'default': core.settings.get(
                'filename_template',
                '[%(id)s] %(title).60s.%(ext)s',
            ),
        },
        'progress_hooks': [progress_hook],
    }

    print(f'[yt-dlp] generic download 시작: {url}', flush=True)
    try:
        with core.yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                raise ValueError('yt-dlp가 다운로드 정보를 반환하지 않았습니다.')
            if info.get('_type') == 'playlist':
                entries = [entry for entry in (info.get('entries') or []) if entry]
                if len(entries) == 1:
                    info = entries[0]
            _store_metadata(core, task_id, info)
            final_path = _find_final_path(core, ydl, info)

        task = core.tasks.get(task_id)
        if not task:
            return
        if not final_path:
            candidate = last_filename.get('path') or ''
            if candidate and os.path.isfile(candidate):
                final_path = candidate
        if not final_path:
            raise ValueError('다운로드는 끝났지만 최종 파일 경로를 확인하지 못했습니다.')

        final_size = os.path.getsize(final_path)
        task['status'] = '완료'
        task['progress'] = '100%'
        task['speed_bps'] = 0
        task['filename'] = os.path.basename(final_path)
        task['filesize'] = final_size
        task['downloaded_bytes'] = final_size
        task['total_bytes_estimate'] = final_size
        task['engine'] = 'yt-dlp'
        _maybe_save(core, task_id, force=True)
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"[완료][yt-dlp] {task['filename']}", flush=True)
    except reliability.DownloadPaused:
        task = core.tasks.get(task_id)
        if task:
            task['status'] = '일시정지'
            task['speed_bps'] = 0
            task['engine'] = 'yt-dlp'
            _maybe_save(core, task_id, force=True)
        print(f'[Pause][yt-dlp] 일시정지 완료: {url}', flush=True)
    except core.DownloadCancelled:
        task = core.tasks.get(task_id)
        if task:
            task['status'] = '취소됨'
            task['speed_bps'] = 0
            _maybe_save(core, task_id, force=True)
    except Exception as exc:
        task = core.tasks.get(task_id)
        # yt-dlp may wrap an exception raised from a progress hook. Preserve the
        # user's pause request rather than converting it into an error task.
        if task and task.get('status') in ('일시정지 요청 중', '일시정지'):
            task['status'] = '일시정지'
            task['speed_bps'] = 0
            task['engine'] = 'yt-dlp'
            _maybe_save(core, task_id, force=True)
            print(f'[Pause][yt-dlp] 일시정지 완료: {url}', flush=True)
            return
        print(f'[Error][yt-dlp] {url}: {exc}', flush=True)
        if task:
            task['status'] = f'에러: {str(exc)[:100]}'
            task['speed_bps'] = 0
            task['engine'] = 'yt-dlp'
            _maybe_save(core, task_id, force=True)


def install_delete_cleanup(core):
    original_delete = core.app.view_functions.get('delete_task')
    if not original_delete:
        return

    def delete_with_generic_cleanup(task_id):
        task = core.tasks.get(task_id)
        active = task and task.get('status') in ('다운로드 중', '일시정지 요청 중', '대기 중')
        if task and not active:
            shutil.rmtree(_task_temp_dir(core, task_id), ignore_errors=True)
        return original_delete(task_id)

    core.app.view_functions['delete_task'] = delete_with_generic_cleanup
