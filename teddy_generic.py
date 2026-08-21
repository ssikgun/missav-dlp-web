import glob
import os
import shutil
import threading
import time

import teddy_routing
import teddy_storage


_save_lock = threading.Lock()
_last_saved = {}

YT_DLP_MEDIA_MODES = ('video', 'audio')
YT_DLP_VIDEO_QUALITIES = ('best', '2160', '1440', '1080', '720', '480')
YT_DLP_VIDEO_CONTAINERS = ('mp4', 'mkv')
YT_DLP_AUDIO_FORMATS = ('m4a', 'mp3')
YT_DLP_SUBTITLE_MODES = ('off', 'ko', 'en', 'ko_en')

YT_DLP_DEFAULTS = {
    'media_mode': 'video',
    'quality': 'best',
    'video_container': 'mp4',
    'audio_format': 'm4a',
    'subtitles': 'off',
}


def is_custom_site(core, url):
    try:
        return bool(core.MyCustomMissAV.suitable(url))
    except Exception:
        return False


def _task_temp_dir(core, task_id):
    return os.path.join(core.DOWNLOAD_DIR, f'.{task_id}.ytdlp')


def _pick(raw, short_key, setting_key, allowed, default):
    value = raw.get(short_key, raw.get(setting_key, default))
    value = str(value or default).lower()
    return value if value in allowed else default


def normalize_ytdlp_options(raw):
    raw = raw if isinstance(raw, dict) else {}
    quality_default = str(raw.get('video_quality', YT_DLP_DEFAULTS['quality']) or YT_DLP_DEFAULTS['quality'])
    if quality_default not in YT_DLP_VIDEO_QUALITIES:
        quality_default = YT_DLP_DEFAULTS['quality']
    return {
        'media_mode': _pick(
            raw, 'media_mode', 'yt_dlp_media_mode',
            YT_DLP_MEDIA_MODES, YT_DLP_DEFAULTS['media_mode'],
        ),
        'quality': _pick(
            raw, 'quality', 'yt_dlp_video_quality',
            YT_DLP_VIDEO_QUALITIES, quality_default,
        ),
        'video_container': _pick(
            raw, 'video_container', 'yt_dlp_video_container',
            YT_DLP_VIDEO_CONTAINERS, YT_DLP_DEFAULTS['video_container'],
        ),
        'audio_format': _pick(
            raw, 'audio_format', 'yt_dlp_audio_format',
            YT_DLP_AUDIO_FORMATS, YT_DLP_DEFAULTS['audio_format'],
        ),
        'subtitles': _pick(
            raw, 'subtitles', 'yt_dlp_subtitles',
            YT_DLP_SUBTITLE_MODES, YT_DLP_DEFAULTS['subtitles'],
        ),
    }


def _format_selector(core, options=None):
    options = normalize_ytdlp_options(options if options is not None else core.settings)
    if options['media_mode'] == 'audio':
        return 'ba/b'

    quality = options['quality']
    container = options['video_container']
    height_filter = '' if quality == 'best' else f'[height<={int(quality)}]'

    if container == 'mp4':
        return (
            f'bv*{height_filter}[ext=mp4]+ba[ext=m4a]/'
            f'b{height_filter}[ext=mp4]/'
            f'bv*{height_filter}+ba/b{height_filter}'
        )
    return f'bv*{height_filter}+ba/b{height_filter}'


def _subtitle_languages(mode):
    if mode == 'ko':
        return ['ko']
    if mode == 'en':
        return ['en']
    if mode == 'ko_en':
        return ['ko', 'en']
    return []


def _maybe_save(core, task_id, force=False):
    now = time.monotonic()
    with _save_lock:
        previous = _last_saved.get(task_id, 0.0)
        if not force and now - previous < 1.0:
            return
        _last_saved[task_id] = now
    core.save_tasks()


def yt_dlp_options_for_task(core, task_id):
    task = core.tasks.get(task_id)
    if not task:
        return normalize_ytdlp_options(core.settings)

    existing = task.get('yt_dlp_options')
    if isinstance(existing, dict):
        normalized = normalize_ytdlp_options(existing)
        if existing != normalized:
            task['yt_dlp_options'] = normalized
            _maybe_save(core, task_id, force=True)
        return normalized

    normalized = normalize_ytdlp_options(core.settings)
    task['yt_dlp_options'] = normalized
    _maybe_save(core, task_id, force=True)
    return normalized


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


def _find_final_path(core, ydl, info, home_dir):
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
        pattern = os.path.join(home_dir, f'*{glob.escape(video_id)}*')
        matches = [path for path in glob.glob(pattern) if os.path.isfile(path)]
        if matches:
            return max(matches, key=os.path.getmtime)
    return ''


def _apply_media_options(opts, options):
    if options['media_mode'] == 'audio':
        postprocessor = {
            'key': 'FFmpegExtractAudio',
            'preferredcodec': options['audio_format'],
        }
        if options['audio_format'] == 'mp3':
            postprocessor['preferredquality'] = '192'
        opts['postprocessors'] = [postprocessor]
        return

    container = options['video_container']
    opts['merge_output_format'] = container
    # Enforce the user's selected final video container even when yt-dlp can
    # satisfy the selector with a single already-muxed fallback format.
    opts['remuxvideo'] = container

    subtitle_languages = _subtitle_languages(options['subtitles'])
    if subtitle_languages:
        opts['writesubtitles'] = True
        opts['writeautomaticsub'] = True
        opts['subtitleslangs'] = subtitle_languages
        opts['subtitlesformat'] = 'vtt/best'


def download_generic(core, reliability, task_id, url, network_mode='direct'):
    temp_dir = _task_temp_dir(core, task_id)
    os.makedirs(temp_dir, exist_ok=True)
    site_key, site_dir = teddy_storage.ensure_site_dir(core, url, custom=False)
    last_filename = {'path': ''}
    proxy_url = teddy_routing.proxy_for_mode(network_mode)
    ytdlp_options = yt_dlp_options_for_task(core, task_id)

    task = core.tasks.get(task_id)
    if task:
        task['storage_folder'] = site_key
        task['engine'] = 'yt-dlp'
        task['network_mode'] = network_mode
        task['yt_dlp_options'] = ytdlp_options
        _maybe_save(core, task_id, force=True)

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
        # Playlist support is intentionally a separate roadmap item.
        'noplaylist': True,
        'continuedl': True,
        'nopart': False,
        'retries': 8,
        'fragment_retries': 8,
        'socket_timeout': 30,
        'format': _format_selector(core, ytdlp_options),
        'paths': {
            'home': site_dir,
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
    _apply_media_options(opts, ytdlp_options)
    if proxy_url:
        opts['proxy'] = proxy_url

    route_label = teddy_routing.mode_label(network_mode)
    option_label = (
        f"mode={ytdlp_options['media_mode']} "
        f"quality={ytdlp_options['quality']} "
        f"video={ytdlp_options['video_container']} "
        f"audio={ytdlp_options['audio_format']} "
        f"subs={ytdlp_options['subtitles']}"
    )
    print(
        f'[yt-dlp] generic download 시작 ({route_label}; {option_label}): '
        f'{url} -> {site_key}/',
        flush=True,
    )
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
            final_path = _find_final_path(core, ydl, info, site_dir)

        task = core.tasks.get(task_id)
        if not task:
            return {'status': 'cancelled'}
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
        task['filename'] = teddy_storage.relative_public_path(core, final_path)
        task['filesize'] = final_size
        task['downloaded_bytes'] = final_size
        task['total_bytes_estimate'] = final_size
        task['engine'] = 'yt-dlp'
        task['storage_folder'] = site_key
        task['network_mode'] = network_mode
        task['yt_dlp_options'] = ytdlp_options
        task.pop('last_error_detail', None)
        _maybe_save(core, task_id, force=True)
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"[완료][yt-dlp][{route_label}] {task['filename']}", flush=True)
        return {'status': 'complete'}
    except reliability.DownloadPaused:
        task = core.tasks.get(task_id)
        if task:
            task['status'] = '일시정지'
            task['speed_bps'] = 0
            task['engine'] = 'yt-dlp'
            task['storage_folder'] = site_key
            task['network_mode'] = network_mode
            task['yt_dlp_options'] = ytdlp_options
            _maybe_save(core, task_id, force=True)
        print(f'[Pause][yt-dlp] 일시정지 완료: {url}', flush=True)
        return {'status': 'paused'}
    except core.DownloadCancelled:
        task = core.tasks.get(task_id)
        if task:
            task['status'] = '취소됨'
            task['speed_bps'] = 0
            _maybe_save(core, task_id, force=True)
        return {'status': 'cancelled'}
    except Exception as exc:
        task = core.tasks.get(task_id)
        # yt-dlp may wrap an exception raised from a progress hook. Preserve the
        # user's pause request rather than converting it into an error task.
        if task and task.get('status') in ('일시정지 요청 중', '일시정지'):
            task['status'] = '일시정지'
            task['speed_bps'] = 0
            task['engine'] = 'yt-dlp'
            task['storage_folder'] = site_key
            task['network_mode'] = network_mode
            task['yt_dlp_options'] = ytdlp_options
            _maybe_save(core, task_id, force=True)
            print(f'[Pause][yt-dlp] 일시정지 완료: {url}', flush=True)
            return {'status': 'paused'}
        message = str(exc)
        print(f'[Error][yt-dlp][{route_label}] {url}: {message}', flush=True)
        if task:
            task['status'] = f'에러: {message[:100]}'
            task['last_error_detail'] = message[:1000]
            task['speed_bps'] = 0
            task['engine'] = 'yt-dlp'
            task['storage_folder'] = site_key
            task['network_mode'] = network_mode
            task['yt_dlp_options'] = ytdlp_options
            _maybe_save(core, task_id, force=True)
        return {'status': 'error', 'error': message}


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
