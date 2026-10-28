if __name__ == '__main__':
    raise SystemExit('Use teddy_bootstrap.py; direct entrypoint execution skips the installed download and FFmpeg safety guards.')

import os
import shutil
import subprocess
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

import app as core
import teddy_hls_transport
import teddy_storage
import teddy_download_safety
import teddy_mp4_queue
import threading


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


def _fetch_segment(task_id, seg_url, headers, transport_mode='per-worker', worker_count=None):
    last = None
    for attempt in range(SEGMENT_RETRY_ATTEMPTS):
        _check_task_state(task_id)
        target = core.IMPERSONATE_TARGETS[attempt % len(core.IMPERSONATE_TARGETS)]
        try:
            response = teddy_hls_transport.get(
                core,
                task_id,
                seg_url,
                impersonate=target,
                headers=headers,
                timeout=SEGMENT_TIMEOUT_SECONDS,
                transport_mode=transport_mode,
                max_clients=worker_count,
            )
            if response.status_code == 200:
                return response.content
            last = f'HTTP {response.status_code}'
            # Per-worker mode drops only this worker's CONNECT/TLS path. Async-pool
            # mode intentionally keeps the shared pool alive for unrelated in-flight
            # requests; public-proxy rotation replaces it by proxy URL on next use.
            teddy_hls_transport.invalidate(transport_mode)
        except (DownloadPaused, core.DownloadCancelled):
            raise
        except Exception as exc:
            last = str(exc)
            teddy_hls_transport.invalidate(transport_mode)

        # Preserve the cumulative VPN health observer from the reliability layer.
        # VPN tasks use per-worker transport even when async-pool is requested.
        observer = getattr(core, '_teddy_vpn_failure_observer', None)
        if callable(observer):
            try:
                observer(task_id, os.path.basename(seg_url), last)
            except Exception as observer_exc:
                print(f'[VPN 자동복구] 오류 감지기 예외: {observer_exc}', flush=True)

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
    # Capture persisted benchmark settings once per execution. Changing the UI while
    # a download is active affects only the next HLS execution, so executor size,
    # write strategy, and connection topology stay stable during one benchmark run.
    worker_count = teddy_hls_transport.workers_from_settings(core.settings)
    write_mode = teddy_hls_transport.write_mode_from_settings(core.settings)
    transport_mode = teddy_hls_transport.transport_mode_for_task(core, task_id, core.settings)
    pool_clients = teddy_hls_transport.pool_clients_from_settings(core.settings)
    http_version = teddy_hls_transport.http_version_from_settings(core.settings)
    root = os.path.realpath(core.DOWNLOAD_DIR)
    out_path = os.path.abspath(out_path)
    parts_dir = os.path.join(root, f'.{task_id}.parts')
    ts_out = (out_path[:-4] if out_path.endswith('.mp4') else out_path) + '.ts'
    if os.path.lexists(out_path) or os.path.lexists(ts_out):
        raise teddy_download_safety.OutputCollision(
            f'기존 완료 파일을 덮어쓰지 않습니다: {out_path}'
        )
    teddy_download_safety.ensure_download_start_space(root)
    if os.path.islink(parts_dir):
        raise teddy_download_safety.DownloadSafetyError(
            f'HLS 조각 디렉터리가 심볼릭 링크여서 안전하게 열 수 없습니다: {parts_dir}'
        )
    os.makedirs(parts_dir, exist_ok=True)
    try:
        if os.path.commonpath([root, os.path.realpath(parts_dir)]) != root:
            raise teddy_download_safety.DownloadSafetyError(
                f'HLS 조각 디렉터리가 작업 루트 밖을 가리킵니다: {parts_dir}'
            )
    except ValueError as exc:
        raise teddy_download_safety.DownloadSafetyError(
            f'HLS 조각 디렉터리 경계를 확인할 수 없습니다: {parts_dir}'
        ) from exc
    task = core.tasks.get(task_id)
    if task:
        task['hls_parts_path'] = os.path.relpath(parts_dir, root)
        core.save_tasks()
    playlist_text = _fetch_variant_playlist(task_id, variant_url, headers)
    plan_sha256, seg_urls = teddy_download_safety.hls_playlist_identity(variant_url, playlist_text)
    total = len(seg_urls)
    if total == 0:
        raise ValueError('세그먼트가 없습니다')

    def seg_path(index):
        return os.path.join(parts_dir, f'{index:05d}.ts')

    list_path = os.path.join(parts_dir, 'filelist.txt')
    expected_filelist = ''.join(f"file '{seg_path(index)}'\n" for index in range(total))
    with teddy_download_safety.StorageWriteTransaction(
        root,
        output_path=parts_dir,
        required_bytes=len(expected_filelist.encode('utf-8')),
        cancel_check=lambda: _check_task_state(task_id),
    ):
        _resume_manifest, reusable_segments = teddy_download_safety.prepare_hls_resume(
            parts_dir,
            task_id,
            plan_sha256,
            total,
            expected_filelist,
            seg_path,
        )
    manifest_lock = threading.Lock()

    pending = []
    for index, url in enumerate(seg_urls):
        path = seg_path(index)
        if index not in reusable_segments:
            pending.append((index, url))
    done = total - len(pending)
    downloaded_bytes = sum(
        os.path.getsize(seg_path(index))
        for index in range(total)
        if os.path.exists(seg_path(index)) and os.path.getsize(seg_path(index)) > 0
    )
    total_bytes_estimate = int(downloaded_bytes * total / done) if done else 0
    print(
        f'[다운로드] 세그먼트 {total}개 (완료 {done} / 남음 {len(pending)}) '
        f'· continuous {worker_count} workers · transport={transport_mode} '
        f'· pool={pool_clients} · http={http_version} · write={write_mode}',
        flush=True,
    )
    if task_id in core.tasks:
        core.tasks[task_id]['progress'] = f'{int(done * 100 / total)}%'
        core.tasks[task_id]['speed_bps'] = 0
        core.tasks[task_id]['downloaded_bytes'] = downloaded_bytes
        core.tasks[task_id]['total_bytes_estimate'] = total_bytes_estimate
        core.tasks[task_id]['hls_workers'] = worker_count
        core.tasks[task_id]['hls_write_mode'] = write_mode
        core.tasks[task_id]['hls_transport_mode'] = transport_mode
        core.tasks[task_id]['hls_pool_clients'] = pool_clients
        core.tasks[task_id]['hls_http_version'] = http_version
        core.tasks[task_id]['hls_http_version_actual'] = '?'
        core.save_tasks()

    def write_part(index, data):
        _check_task_state(task_id)
        target = seg_path(index)
        if os.path.lexists(target):
            raise teddy_download_safety.OutputCollision(
                f'기존 세그먼트 파일을 덮어쓰지 않습니다: {target}'
            )
        tmp = target + f'.{os.getpid()}.{time.time_ns()}.tmp'
        try:
            with teddy_download_safety.StorageWriteTransaction(
                root,
                output_path=parts_dir,
                required_bytes=len(data),
                cancel_check=lambda: _check_task_state(task_id),
            ) as storage_write:
                with open(tmp, 'xb') as file_obj:
                    written = file_obj.write(data)
                    if written != len(data):
                        raise OSError('HLS 세그먼트 임시 파일에 전체 데이터를 기록하지 못했습니다.')
                    storage_write.consume_written(written)
                    file_obj.flush()
                    os.fsync(file_obj.fileno())
                teddy_download_safety.atomic_publish_noclobber(tmp, target)
                with manifest_lock:
                    teddy_download_safety.record_hls_segment(
                        parts_dir, task_id, plan_sha256, index, target,
                    )
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return len(data)

    def fetch_item(item):
        index, url = item
        data = _fetch_segment(
            task_id,
            url,
            headers,
            transport_mode=transport_mode,
            worker_count=pool_clients,
        )
        _check_task_state(task_id)
        if write_mode == 'parts':
            # Production-safe path: preserve the proven behavior exactly, including
            # worker-thread persistence before a segment is considered complete.
            write_part(index, data)
            return len(data)
        # RAM benchmark: the network worker returns immediately with bytes. The
        # coordinator refills that freed network slot before serially persisting the
        # payload to the same .parts layout, isolating concurrent NAS file I/O while
        # retaining completed-segment resume/crash recovery.
        return index, data

    speed_samples = []
    window_started = time.monotonic()
    window_bytes = 0
    last_speed = 0
    pending_iter = iter(pending)
    in_flight = {}
    executor = ThreadPoolExecutor(max_workers=worker_count)

    def submit_one():
        try:
            item = next(pending_iter)
        except StopIteration:
            return False
        future = executor.submit(fetch_item, item)
        in_flight[future] = item
        return True

    try:
        for _ in range(min(worker_count, len(pending))):
            submit_one()

        while in_flight:
            _check_task_state(task_id)
            completed, _ = wait(tuple(in_flight), return_when=FIRST_COMPLETED)
            for future in completed:
                in_flight.pop(future, None)
                result = future.result()
                if write_mode == 'ram':
                    index, data = result
                    # Refill the free network slot before touching NAS storage.
                    submit_one()
                    write_part(index, data)
                    byte_count = len(data)
                else:
                    byte_count = result

                done += 1
                downloaded_bytes += byte_count
                window_bytes += byte_count

                now = time.monotonic()
                window_elapsed = max(now - window_started, 0.001)
                should_sample = window_elapsed >= 1.0 or done >= total
                if should_sample:
                    sample_speed = window_bytes / window_elapsed
                    speed_samples.append(sample_speed)
                    speed_samples = speed_samples[-4:]
                    last_speed = int(sum(speed_samples) / len(speed_samples))
                    observer = getattr(core, '_teddy_proxy_transfer_observer', None)
                    if observer:
                        try:
                            observer(task_id, window_bytes, window_elapsed)
                        except Exception as exc:
                            print(f'[Proxy 학습] 전송 샘플 기록 실패: {exc}', flush=True)
                    window_started = now
                    window_bytes = 0
                elif window_elapsed >= 0.20:
                    # Give the UI an early estimate without polluting learning with
                    # sub-second samples.
                    last_speed = int(window_bytes / window_elapsed)

                total_bytes_estimate = int(downloaded_bytes * total / done) if done else 0
                if task_id in core.tasks:
                    core.tasks[task_id]['progress'] = f'{int(min(done, total) * 100 / total)}%'
                    core.tasks[task_id]['speed_bps'] = max(0, int(last_speed))
                    core.tasks[task_id]['downloaded_bytes'] = downloaded_bytes
                    core.tasks[task_id]['total_bytes_estimate'] = total_bytes_estimate

                # Existing parts mode refills after persistence; RAM mode already
                # refilled immediately after the network future completed above.
                if write_mode != 'ram':
                    submit_one()
    finally:
        executor.shutdown(wait=True, cancel_futures=True)

    # Flush any final sub-second transfer sample for UI/proxy learning.
    if window_bytes > 0:
        elapsed = max(time.monotonic() - window_started, 0.001)
        if elapsed >= 0.20:
            observer = getattr(core, '_teddy_proxy_transfer_observer', None)
            if observer:
                try:
                    observer(task_id, window_bytes, elapsed)
                except Exception as exc:
                    print(f'[Proxy 학습] 최종 전송 샘플 기록 실패: {exc}', flush=True)

    _check_task_state(task_id)
    if task_id in core.tasks:
        core.tasks[task_id]['progress'] = '99%'
        core.tasks[task_id]['speed_bps'] = 0
        core.tasks[task_id]['downloaded_bytes'] = downloaded_bytes
        core.tasks[task_id]['total_bytes_estimate'] = downloaded_bytes

    missing = [
        index for index in range(total)
        if not os.path.isfile(seg_path(index)) or os.path.getsize(seg_path(index)) <= 0
    ]
    if missing:
        raise ValueError(f'완료되지 않은 HLS 세그먼트가 있습니다: {len(missing)}개')
    teddy_mp4_queue.enqueue_hls(
        core, task_id, root, parts_dir, list_path, out_path, plan_sha256, total,
    )
    return out_path


def _store_info(task_id, info):
    if task_id not in core.tasks:
        return
    task = core.tasks[task_id]
    task['display_title'] = info.get('title') or task.get('url')
    task['thumbnail_url'] = info.get('thumbnail') or ''
    core.save_tasks()


def _download_video(task_id, url):
    try:
        _check_task_state(task_id)
        with core.yt_dlp.YoutubeDL(
            {
                'quiet': True,
                'no_warnings': True,
                'proxy': None,
                'teddy_task_id': task_id,
            },
            auto_init=False,
        ) as ydl:
            ydl.add_info_extractor(core.MyCustomMissAV())
            print(f'[Download] 시작: {url}', flush=True)
            info = ydl.extract_info(url, download=False)
        _store_info(task_id, info)
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
        queued_task = core.tasks.get(task_id) or {}
        if queued_task.get('mp4_stage') == 'queued':
            return
        if task_id not in core.tasks:
            return
        with teddy_download_safety.task_state_guard():
            _check_task_state(task_id)
            task = core.tasks.get(task_id)
            if not task:
                raise core.DownloadCancelled()
            out_name = os.path.basename(final_path)
            task['progress'] = '99%'
            task['speed_bps'] = 0
            task['filename'] = out_name
            task['local_result_path'] = teddy_storage.relative_work_path(core, final_path)
            task['local_result_paths'] = [task['local_result_path']]
            try:
                final_size = os.path.getsize(final_path)
                task['filesize'] = final_size
                task['downloaded_bytes'] = final_size
                task['total_bytes_estimate'] = final_size
            except OSError:
                pass
            core.save_tasks()
        print(f"[로컬 완료][custom-hls] {task['local_result_path']} -> publish pending", flush=True)
        return {'status': 'local-complete'}
    except DownloadPaused:
        with teddy_download_safety.task_state_guard():
            teddy_download_safety.complete_pause_request(core, task_id)
            task = core.tasks.get(task_id)
            if task:
                task['speed_bps'] = 0
                core.save_tasks()
        print(f'[Pause] 일시정지 완료: {url}', flush=True)
    except core.DownloadCancelled:
        if task_id in core.tasks:
            core.tasks[task_id]['status'] = '취소됨'
            core.tasks[task_id]['speed_bps'] = 0
            core.save_tasks()
    except Exception as exc:
        task = core.tasks.get(task_id)
        if task and task.get('status') in ('일시정지 요청 중', '일시정지'):
            task['status'] = '일시정지'
            task['speed_bps'] = 0
            core.save_tasks()
            print(f'[Pause] 추출 단계 일시정지 완료: {url}', flush=True)
            return
        print(f'[Error] {url}: {exc}', flush=True)
        if task_id in core.tasks:
            kind = teddy_download_safety.failure_kind(exc)
            prefix = '에러: 저장 공간/잠금 보호: ' if kind in ('storage', 'safety') else '에러: '
            core.tasks[task_id]['status'] = f'{prefix}{str(exc)[:100]}'
            core.tasks[task_id]['error_kind'] = kind
            core.tasks[task_id]['last_error_detail'] = str(exc)[:1000]
            core.tasks[task_id]['speed_bps'] = 0
            core.save_tasks()


def _install_routes():
    @core.app.route('/api/tasks/<task_id>/pause', methods=['POST'])
    def teddy_pause_task(task_id):
        task = core.tasks.get(task_id)
        if not task:
            return core.jsonify({'status': 'error', 'message': '작업 없음'}), 404
        with teddy_download_safety.task_state_guard():
            task = core.tasks.get(task_id)
            if not task:
                return core.jsonify({'status': 'error', 'message': '작업 없음'}), 404
            if teddy_download_safety.final_publish_started(task_id):
                return core.jsonify({'status': 'error', 'message': '최종 저장 검증이 시작되어 지금은 일시정지할 수 없습니다.'}), 409
            if task.get('status') in ('MP4 변환 대기', 'MP4 저장 대기'):
                teddy_mp4_queue.pause_task(core, task_id)
                return core.jsonify({'status': 'success', 'message': 'MP4 대기 작업을 일시정지했습니다.'})
            if task.get('status') not in ('다운로드 중', 'MP4 변환 중'):
                return core.jsonify({'status': 'error', 'message': '진행 중인 작업만 일시정지할 수 있습니다.'}), 400
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
        with teddy_download_safety.task_state_guard():
            task = core.tasks.get(task_id)
            if not task:
                return core.jsonify({'status': 'error', 'message': '작업 없음'}), 404
            if task.get('status') != '일시정지':
                return core.jsonify({'status': 'error', 'message': '일시정지된 작업만 재개할 수 있습니다.'}), 400
            with core.download_queue.mutex:
                if task_id in core.download_queue.queue:
                    return core.jsonify({'status': 'error', 'message': '이미 큐에 등록된 작업'}), 409
            if teddy_mp4_queue.resume_task(core, task_id):
                return core.jsonify({'status': 'success', 'message': 'MP4 단계 재개 대기 중'})
            task['status'] = '대기 중'
            task['speed_bps'] = 0
            task.pop('error_kind', None)
            task.pop('last_error_detail', None)
            core.save_tasks()
            core.download_queue.put(task_id)
        print(f"[Resume] 재개 큐 추가: {task.get('url')}", flush=True)
        return core.jsonify({'status': 'success', 'message': '재개 대기 중'})

    @core.app.route('/api/tasks/<task_id>/thumbnail', methods=['GET'])
    def teddy_task_thumbnail(task_id):
        task = core.tasks.get(task_id)
        if not task or not task.get('thumbnail_url'):
            return core.Response(status=404)
        url = task['thumbnail_url']
        try:
            parsed = core.urlparse(url)
            if parsed.scheme not in ('http', 'https'):
                return core.Response(status=400)
            response = core.cffi_requests.get(url, impersonate='chrome110', timeout=15)
            if response.status_code != 200:
                return core.Response(status=502)
            content_type = response.headers.get('content-type', 'image/jpeg')
            return core.Response(response.content, mimetype=content_type.split(';')[0])
        except Exception as exc:
            print(f'[Thumbnail] 실패: {exc}', flush=True)
            return core.Response(status=502)

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
        with core.queue_admission_lock:
            task = core.tasks.get(task_id)
            if not task:
                return core.jsonify({'status': 'error', 'message': '작업 없음'}), 404
            persist_and_enqueue = getattr(core, 'persist_retry_state_and_enqueue', None)
            if not callable(persist_and_enqueue):
                return core.jsonify({'status': 'error', 'message': '작업 상태 저장을 확인할 수 없어 재시도를 차단했습니다.'}), 503
            current = task.get('status', '')
            with core.download_queue.mutex:
                if task_id in core.download_queue.queue:
                    return core.jsonify({'status': 'error', 'message': '이미 큐에 등록된 작업'}), 409
            if teddy_mp4_queue.has_task(core, task_id):
                if teddy_mp4_queue.retry_task(core, task_id):
                    return core.jsonify({'status': 'success', 'message': 'MP4 단계 재시도 대기 중'})
            if current in ('다운로드 중', '대기 중', '일시정지 요청 중'):
                return core.jsonify({'status': 'error', 'message': '이미 진행 중인 작업'}), 400
            if current == '일시정지':
                return core.jsonify({'status': 'error', 'message': '일시정지 작업은 재개 버튼을 사용하세요.'}), 400
            try:
                legacy_ts = teddy_mp4_queue.legacy_ts_retry_source(core, task_id)
                if legacy_ts is not None:
                    teddy_mp4_queue.enqueue_legacy_ts(core, task_id, legacy_ts)
                    return core.jsonify({
                        'status': 'success',
                        'message': '기존 TS를 보존하고 MP4 전용 대기열에 등록했습니다.',
                    })
            except (teddy_download_safety.DownloadSafetyError, OSError) as exc:
                return core.jsonify({'status': 'error', 'message': str(exc)}), 409
            previous = dict(task)
            task['status'] = '대기 중'
            task['speed_bps'] = 0
            task['retries'] = 0
            task.pop('error_kind', None)
            task.pop('last_error_detail', None)
            try:
                persist_and_enqueue(task_id, previous)
            except Exception:
                return core.jsonify({'status': 'error', 'message': '재시도 큐 등록에 실패했습니다.'}), 503
            print(f"[Retry] 재시도 큐 추가: {task.get('url')}", flush=True)
            return core.jsonify({'status': 'success', 'message': '재시도 대기 중'})

    if 'retry_task' in core.app.view_functions:
        core.app.view_functions['retry_task'] = safe_retry_task
        core._teddy_safe_retry_task = safe_retry_task


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
