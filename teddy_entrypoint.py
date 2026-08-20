import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

import app as core


SEGMENT_TIMEOUT_SECONDS = 45
SEGMENT_RETRY_ATTEMPTS = 6
SEGMENT_RETRY_BACKOFF = (0, 2, 4, 8, 12, 20)
PLAYLIST_RETRY_ATTEMPTS = 4
PLAYLIST_RETRY_BACKOFF = (0, 2, 4, 8)


class DownloadPaused(Exception):
    pass


def _check_task_state(task_id):
    if task_id not in core.tasks:
        raise core.DownloadCancelled()
    if core.tasks[task_id].get('status') in ('일시정지 요청 중', '일시정지'):
        raise DownloadPaused()


def _interruptible_sleep(task_id, seconds):
    end = time.monotonic() + seconds
    while True:
        _check_task_state(task_id)
        remaining = end - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.5, remaining))


def _fetch_segment(task_id, seg_url, headers):
    """Retry only the failed segment before escalating to task-level retry."""
    last = None
    for attempt in range(SEGMENT_RETRY_ATTEMPTS):
        _check_task_state(task_id)
        target = core.IMPERSONATE_TARGETS[attempt % len(core.IMPERSONATE_TARGETS)]
        try:
            response = core.cffi_requests.get(
                seg_url,
                impersonate=target,
                headers=headers,
                timeout=SEGMENT_TIMEOUT_SECONDS,
            )
            if response.status_code == 200:
                return response.content
            last = f'HTTP {response.status_code}'
        except (DownloadPaused, core.DownloadCancelled):
            raise
        except Exception as exc:
            last = str(exc)

        if attempt + 1 < SEGMENT_RETRY_ATTEMPTS:
            delay = SEGMENT_RETRY_BACKOFF[attempt + 1]
            print(
                f'[세그먼트 재시도] {attempt + 2}/{SEGMENT_RETRY_ATTEMPTS} '
                f'({delay}s 후, {target}) {os.path.basename(seg_url)}: {last}',
                flush=True,
            )
            _interruptible_sleep(task_id, delay)

    raise ValueError(f'세그먼트 반복 실패({last}): {seg_url}')


def _fetch_variant_playlist(task_id, variant_url, headers):
    last = None
    for attempt in range(PLAYLIST_RETRY_ATTEMPTS):
        _check_task_state(task_id)
        target = core.IMPERSONATE_TARGETS[attempt % len(core.IMPERSONATE_TARGETS)]
        try:
            response = core.cffi_requests.get(
                variant_url,
                impersonate=target,
                headers=headers,
                timeout=25,
            )
            if response.status_code == 200 and '#EXT' in response.text:
                return response.text
            last = f'HTTP {response.status_code}'
        except (DownloadPaused, core.DownloadCancelled):
            raise
        except Exception as exc:
            last = str(exc)

        if attempt + 1 < PLAYLIST_RETRY_ATTEMPTS:
            delay = PLAYLIST_RETRY_BACKOFF[attempt + 1]
            print(
                f'[m3u8 재시도] {attempt + 2}/{PLAYLIST_RETRY_ATTEMPTS} '
                f'({delay}s 후) {last}',
                flush=True,
            )
            _interruptible_sleep(task_id, delay)

    raise ValueError(f'변형 m3u8 반복 실패: {last}')


def _download_hls_resumable(task_id, variant_url, headers, out_path):
    """Resumable HLS downloader with per-segment retries and pause support."""
    parts_dir = os.path.join(core.DOWNLOAD_DIR, f'.{task_id}.parts')
    os.makedirs(parts_dir, exist_ok=True)

    playlist_text = _fetch_variant_playlist(task_id, variant_url, headers)
    base = variant_url.rsplit('/', 1)[0] + '/'
    seg_urls = [
        (segment if segment.startswith('http') else base + segment)
        for segment in (line.strip() for line in playlist_text.splitlines())
        if segment and not segment.startswith('#')
    ]
    total = len(seg_urls)
    if total == 0:
        raise ValueError('세그먼트가 없습니다')

    def seg_path(index):
        return os.path.join(parts_dir, f'{index:05d}.ts')

    pending = [
        (index, url)
        for index, url in enumerate(seg_urls)
        if not (os.path.exists(seg_path(index)) and os.path.getsize(seg_path(index)) > 0)
    ]
    done = total - len(pending)
    downloaded_bytes = sum(
        os.path.getsize(seg_path(index))
        for index in range(total)
        if os.path.exists(seg_path(index)) and os.path.getsize(seg_path(index)) > 0
    )
    total_bytes_estimate = int(downloaded_bytes * total / done) if done else 0

    print(f'[다운로드] 세그먼트 {total}개 (완료 {done} / 남음 {len(pending)})', flush=True)
    if task_id in core.tasks:
        core.tasks[task_id]['progress'] = f'{int(done * 100 / total)}%'
        core.tasks[task_id]['speed_bps'] = 0
        core.tasks[task_id]['downloaded_bytes'] = downloaded_bytes
        core.tasks[task_id]['total_bytes_estimate'] = total_bytes_estimate

    def fetch_to_file(item):
        index, url = item
        data = _fetch_segment(task_id, url, headers)
        _check_task_state(task_id)
        tmp = seg_path(index) + '.tmp'
        with open(tmp, 'wb') as file_obj:
            file_obj.write(data)
        os.replace(tmp, seg_path(index))
        return len(data)

    speed_samples = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        batch_size = 16
        for start in range(0, len(pending), batch_size):
            _check_task_state(task_id)
            batch = pending[start:start + batch_size]
            batch_started = time.monotonic()
            byte_counts = list(executor.map(fetch_to_file, batch))
            elapsed = max(time.monotonic() - batch_started, 0.001)
            batch_bytes = sum(byte_counts)
            batch_speed = batch_bytes / elapsed
            speed_samples.append(batch_speed)
            speed_samples = speed_samples[-4:]
            smoothed_speed = sum(speed_samples) / len(speed_samples)

            done += len(batch)
            downloaded_bytes += batch_bytes
            total_bytes_estimate = int(downloaded_bytes * total / done) if done else 0
            if task_id in core.tasks:
                core.tasks[task_id]['progress'] = f'{int(min(done, total) * 100 / total)}%'
                core.tasks[task_id]['speed_bps'] = int(smoothed_speed)
                core.tasks[task_id]['downloaded_bytes'] = downloaded_bytes
                core.tasks[task_id]['total_bytes_estimate'] = total_bytes_estimate

    _check_task_state(task_id)
    if task_id in core.tasks:
        core.tasks[task_id]['progress'] = '99%'
        core.tasks[task_id]['speed_bps'] = 0
        core.tasks[task_id]['downloaded_bytes'] = downloaded_bytes
        core.tasks[task_id]['total_bytes_estimate'] = downloaded_bytes

    list_path = os.path.join(parts_dir, 'filelist.txt')
    with open(list_path, 'w', encoding='utf-8') as list_file:
        for index in range(total):
            list_file.write(f"file '{seg_path(index)}'\n")

    print('[ffmpeg] mp4 리먹스 중...', flush=True)
    proc = subprocess.run(
        [
            'ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0',
            '-i', list_path, '-c', 'copy', out_path,
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0 and os.path.exists(out_path):
        shutil.rmtree(parts_dir, ignore_errors=True)
        return out_path

    print(
        f'[ffmpeg] concat 실패(코드 {proc.returncode}) → ts로 저장: '
        f'{(proc.stderr or "")[:300]}',
        flush=True,
    )
    ts_out = (out_path[:-4] if out_path.endswith('.mp4') else out_path) + '.ts'
    with open(ts_out, 'wb') as output_file:
        for index in range(total):
            with open(seg_path(index), 'rb') as segment_file:
                output_file.write(segment_file.read())
    shutil.rmtree(parts_dir, ignore_errors=True)
    return ts_out


def _download_video(task_id, url):
    try:
        _check_task_state(task_id)
        with core.yt_dlp.YoutubeDL(
            {'quiet': True, 'no_warnings': True, 'proxy': None},
            auto_init=False,
        ) as ydl:
            ydl.add_info_extractor(core.MyCustomMissAV())
            print(f'[Download] 시작: {url}', flush=True)
            info = ydl.extract_info(url, download=False)

        _check_task_state(task_id)
        fmt = core._pick_format(info.get('formats', []), core.settings.get('video_quality', 'best'))
        if not fmt:
            raise ValueError('사용 가능한 화질이 없습니다')
        variant_url = fmt['url']
        headers = dict(fmt.get('http_headers') or {})
        for key, value in core.CROSS_SITE_HEADERS.items():
            headers.setdefault(key, value)
        print(f"[선택] {fmt.get('height')}p -> {variant_url}", flush=True)

        out_name = core._safe_filename(info)
        out_path = os.path.join(core.DOWNLOAD_DIR, out_name)
        final_path = _download_hls_resumable(task_id, variant_url, headers, out_path)
        if task_id not in core.tasks:
            return

        out_name = os.path.basename(final_path)
        core.tasks[task_id]['status'] = '완료'
        core.tasks[task_id]['progress'] = '100%'
        core.tasks[task_id]['speed_bps'] = 0
        core.tasks[task_id]['filename'] = out_name
        try:
            final_size = os.path.getsize(final_path)
            core.tasks[task_id]['filesize'] = final_size
            core.tasks[task_id]['downloaded_bytes'] = final_size
            core.tasks[task_id]['total_bytes_estimate'] = final_size
        except OSError:
            pass
        core.save_tasks()
        print(f'[완료] {out_name}', flush=True)
    except DownloadPaused:
        if task_id in core.tasks:
            core.tasks[task_id]['status'] = '일시정지'
            core.tasks[task_id]['speed_bps'] = 0
            core.save_tasks()
        print(f'[Pause] 일시정지 완료: {url}', flush=True)
    except core.DownloadCancelled:
        if task_id in core.tasks:
            core.tasks[task_id]['status'] = '취소됨'
            core.tasks[task_id]['speed_bps'] = 0
            core.save_tasks()
    except Exception as exc:
        print(f'[Error] {url}: {exc}', flush=True)
        if task_id in core.tasks:
            core.tasks[task_id]['status'] = f'에러: {str(exc)[:100]}'
            core.tasks[task_id]['speed_bps'] = 0
            core.save_tasks()


def _install_routes():
    @core.app.route('/api/tasks/<task_id>/pause', methods=['POST'])
    def teddy_pause_task(task_id):
        task = core.tasks.get(task_id)
        if not task:
            return core.jsonify({'status': 'error', 'message': '작업 없음'}), 404
        if task.get('status') != '다운로드 중':
            return core.jsonify({'status': 'error', 'message': '다운로드 중인 작업만 일시정지할 수 있습니다.'}), 400
        task['status'] = '일시정지 요청 중'
        task['speed_bps'] = 0
        core.save_tasks()
        print(f"[Pause] 요청: {task.get('url')}", flush=True)
        return core.jsonify({'status': 'success', 'message': '안전하게 일시정지하는 중입니다.'})

    @core.app.route('/api/tasks/<task_id>/resume', methods=['POST'])
    def teddy_resume_task(task_id):
        task = core.tasks.get(task_id)
        if not task:
            return core.jsonify({'status': 'error', 'message': '작업 없음'}), 404
        if task.get('status') != '일시정지':
            return core.jsonify({'status': 'error', 'message': '일시정지된 작업만 재개할 수 있습니다.'}), 400
        task['status'] = '대기 중'
        task['speed_bps'] = 0
        core.save_tasks()
        core.download_queue.put(task_id)
        print(f"[Resume] 재개 큐 추가: {task.get('url')}", flush=True)
        return core.jsonify({'status': 'success', 'message': '재개 대기 중'})

    original_delete = core.app.view_functions.get('delete_task')
    if original_delete:
        def safe_delete_task(task_id):
            task = core.tasks.get(task_id)
            if task and task.get('status') in ('다운로드 중', '일시정지 요청 중'):
                return core.jsonify({
                    'status': 'error',
                    'message': '다운로드가 완전히 일시정지된 뒤 삭제하세요.',
                }), 409
            return original_delete(task_id)
        core.app.view_functions['delete_task'] = safe_delete_task

    def safe_retry_task(task_id):
        task = core.tasks.get(task_id)
        if not task:
            return core.jsonify({'status': 'error', 'message': '작업 없음'}), 404
        current = task.get('status', '')
        if current in ('다운로드 중', '대기 중', '일시정지 요청 중'):
            return core.jsonify({'status': 'error', 'message': '이미 진행 중인 작업'}), 400
        if current == '일시정지':
            return core.jsonify({'status': 'error', 'message': '일시정지 작업은 재개 버튼을 사용하세요.'}), 400
        task['status'] = '대기 중'
        task['speed_bps'] = 0
        task['retries'] = 0
        core.save_tasks()
        core.download_queue.put(task_id)
        print(f"[Retry] 재시도 큐 추가: {task.get('url')}", flush=True)
        return core.jsonify({'status': 'success', 'message': '재시도 대기 중'})

    if 'retry_task' in core.app.view_functions:
        core.app.view_functions['retry_task'] = safe_retry_task


def install():
    core._fetch_segment = _fetch_segment
    core._download_hls_resumable = _download_hls_resumable
    core.download_video = _download_video
    _install_routes()
    print(
        '[Teddy] reliability layer enabled: segment retry/backoff + pause/resume + safe delete',
        flush=True,
    )


install()


if __name__ == '__main__':
    print(f"\n{'=' * 50}")
    print('MissAV Downloader Started (Teddy Custom)')
    print(f'Download directory: {core.DOWNLOAD_DIR}')
    print('Open: http://localhost:5000')
    print(f"{'=' * 50}\n")
    core.app.run(host='0.0.0.0', port=5000, debug=False)
