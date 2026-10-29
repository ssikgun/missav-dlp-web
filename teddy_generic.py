import glob
import os
import shutil
import threading
import time

import teddy_routing
import teddy_storage
import teddy_123av
import teddy_download_safety


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


def _task_home_dir(core, task_id):
    return os.path.join(core.DOWNLOAD_DIR, f'.{task_id}.ytdlp-home')


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
    # YoutubeDL's Python API does not run the CLI option-conversion layer.
    # Add the same postprocessor that yt-dlp's --remux-video option generates.
    opts['postprocessors'] = [{
        'key': 'FFmpegVideoRemuxer',
        'preferedformat': container,
    }]

    subtitle_languages = _subtitle_languages(options['subtitles'])
    if subtitle_languages:
        opts['writesubtitles'] = True
        opts['writeautomaticsub'] = True
        opts['subtitleslangs'] = subtitle_languages
        opts['subtitlesformat'] = 'vtt/best'


def _youtube_dl_for_url(core, opts, url):
    """Keep the normal yt-dlp path unchanged except for Teddy site adapters."""
    if not teddy_123av.Teddy123AVIE.suitable(url):
        return core.yt_dlp.YoutubeDL(opts)

    ydl = core.yt_dlp.YoutubeDL(
        opts,
        auto_init=False,
    )
    ydl.add_info_extractor(
        teddy_123av.Teddy123AVIE()
    )
    ydl.add_default_info_extractors()
    return ydl


def download_generic(core, reliability, task_id, url, network_mode='direct'):
    temp_dir = _task_temp_dir(core, task_id)
    home_dir = _task_home_dir(core, task_id)
    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(home_dir, exist_ok=True)
    site_key = teddy_storage.site_key_for_url(url, custom=False)
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

    space_reservation = {'manager': None}
    unknown_downloaded_by_file = {}

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
            reservation = space_reservation.get('manager')
            estimated_total = teddy_download_safety.estimated_download_size_bytes(data)
            if reservation is None:
                raise teddy_download_safety.DownloadSafetyError('다운로드 공간 예약이 초기화되지 않았습니다.')
            if estimated_total is not None and downloaded <= estimated_total:
                reservation.reset_unknown()
                reservation.update(max(0, estimated_total - downloaded))
            else:
                filename_key = str(data.get('filename') or 'stream')
                unknown_downloaded_by_file[filename_key] = max(
                    int(unknown_downloaded_by_file.get(filename_key, 0)), downloaded)
                reservation.observe_unknown_size(sum(unknown_downloaded_by_file.values()))
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
            # Keep every in-progress/finalized yt-dlp artifact on local NVMe.
            # The bootstrap publishes completed outputs to TEDDY_FINAL_DIR only
            # after yt-dlp postprocessing has fully finished.
            'home': home_dir,
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
    if ytdlp_options['media_mode'] == 'video' and ytdlp_options['video_container'] == 'mp4':
        # The MP4 stage runs after the network worker returns; retain source streams for restart recovery.
        opts['keepvideo'] = True
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
        teddy_download_safety.ensure_download_start_space(home_dir)
        teddy_download_safety.ensure_download_start_space(temp_dir)
        with _youtube_dl_for_url(core, opts, url) as ydl:
            with teddy_download_safety.StorageReservation(core.DOWNLOAD_DIR, task_id, home_dir) as reservation:
                space_reservation['manager'] = reservation
                try:
                    with teddy_download_safety.task_context(task_id, reservation=reservation):
                        info = ydl.extract_info(url, download=True)
                finally:
                    space_reservation['manager'] = None
            current_task = core.tasks.get(task_id)
            if not current_task:
                raise core.DownloadCancelled()
            if current_task.get('status') in ('일시정지 요청 중', '일시정지'):
                raise reliability.DownloadPaused()
            if info is None:
                raise ValueError('yt-dlp가 다운로드 정보를 반환하지 않았습니다.')
            if info.get('_type') == 'playlist':
                entries = [entry for entry in (info.get('entries') or []) if entry]
                if len(entries) == 1:
                    info = entries[0]
            _store_metadata(core, task_id, info)
            queued_task = core.tasks.get(task_id) or {}
            if queued_task.get('mp4_stage') == 'queued':
                return {'status': 'mp4-queued'}
            final_path = _find_final_path(core, ydl, info, home_dir)

        task = core.tasks.get(task_id)
        if not task:
            return {'status': 'cancelled'}
        if not final_path:
            candidate = last_filename.get('path') or ''
            if candidate and os.path.isfile(candidate):
                final_path = candidate
        if not final_path:
            raise ValueError('다운로드는 끝났지만 최종 파일 경로를 확인하지 못했습니다.')

        storage_guard_path = teddy_download_safety.storage_lock_path(home_dir)
        outputs = []
        try:
            for entry in os.scandir(home_dir):
                if not entry.is_file():
                    continue
                name = entry.name
                if (
                    name == os.path.basename(storage_guard_path)
                    and not entry.is_symlink()
                    and os.path.realpath(entry.path) == storage_guard_path
                ):
                    continue
                if name.endswith(('.part', '.ytdl', '.tmp')) or '.part-Frag' in name:
                    continue
                outputs.append(entry.path)
        except OSError:
            outputs = []
        if final_path not in outputs:
            outputs.append(final_path)

        main_rel = teddy_storage.relative_work_path(core, final_path)
        local_paths = []
        for path in outputs:
            try:
                relative = teddy_storage.relative_work_path(core, path)
            except teddy_storage.PublishError:
                continue
            if relative not in local_paths:
                local_paths.append(relative)
        local_paths = [path for path in local_paths if path != main_rel] + [main_rel]

        with teddy_download_safety.task_state_guard():
            task = core.tasks.get(task_id)
            if not task or task.get('status') == '취소됨':
                raise core.DownloadCancelled()
            if task.get('status') in ('일시정지 요청 중', '일시정지'):
                teddy_download_safety.complete_pause_request(core, task_id)
                raise reliability.DownloadPaused()
            if task.get('status') != '다운로드 중':
                raise teddy_download_safety.DownloadSafetyError(
                    '최종 로컬 결과를 확정하기 전 작업 상태가 변경되어 게시를 보류했습니다.'
                )
            final_size = os.path.getsize(final_path)
            task['progress'] = '99%'
            task['speed_bps'] = 0
            task['filename'] = os.path.basename(final_path)
            task['filesize'] = final_size
            task['downloaded_bytes'] = final_size
            task['total_bytes_estimate'] = final_size
            task['engine'] = 'yt-dlp'
            task['storage_folder'] = site_key
            task['network_mode'] = network_mode
            task['yt_dlp_options'] = ytdlp_options
            task['local_result_path'] = main_rel
            task['local_result_paths'] = local_paths
            task.pop('last_error_detail', None)
            _maybe_save(core, task_id, force=True)
        # Keep yt-dlp temp fragments until final storage has been verified.
        print(f"[로컬 완료][yt-dlp][{route_label}] {main_rel} -> publish pending", flush=True)
        return {'status': 'local-complete'}
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
        if task and task.get('status') == '취소됨':
            return {'status': 'cancelled'}
        # yt-dlp may wrap an exception raised from a progress hook. Preserve the
        # user's pause request rather than converting it into an error task.
        pause_interrupt = isinstance(exc, (reliability.DownloadPaused, teddy_download_safety.TaskPauseRequested))
        if task and (pause_interrupt or task.get('status') in ('일시정지 요청 중', '일시정지')):
            teddy_download_safety.complete_pause_request(core, task_id)
            task = core.tasks.get(task_id)
            if task:
                task['speed_bps'] = 0
                task['engine'] = 'yt-dlp'
                task['storage_folder'] = site_key
                task['network_mode'] = network_mode
                task['yt_dlp_options'] = ytdlp_options
                _maybe_save(core, task_id, force=True)
            print(f'[Pause][yt-dlp] 일시정지 완료: {url}', flush=True)
            return {'status': 'paused'}
        message = str(exc)
        kind = teddy_download_safety.failure_kind(exc)
        print(f'[Error][yt-dlp][{route_label}] {url}: {message}', flush=True)
        if task:
            prefix = '에러: 저장 공간/잠금 보호: ' if kind in ('storage', 'safety') else '에러: '
            task['status'] = f'{prefix}{message[:100]}'
            task['error_kind'] = kind
            task['last_error_detail'] = message[:1000]
            task['speed_bps'] = 0
            task['engine'] = 'yt-dlp'
            task['storage_folder'] = site_key
            task['network_mode'] = network_mode
            task['yt_dlp_options'] = ytdlp_options
            _maybe_save(core, task_id, force=True)
        return {'status': 'error', 'error': message, 'error_kind': kind}


def install_delete_cleanup(core):
    original_delete = core.app.view_functions.get('delete_task')
    if not original_delete:
        return

    def delete_with_generic_cleanup(task_id):
        task = core.tasks.get(task_id)
        active = task and task.get('status') in ('다운로드 중', '일시정지 요청 중', '대기 중')
        if task and not active:
            shutil.rmtree(_task_temp_dir(core, task_id), ignore_errors=True)
            shutil.rmtree(_task_home_dir(core, task_id), ignore_errors=True)
        return original_delete(task_id)

    core.app.view_functions['delete_task'] = delete_with_generic_cleanup
