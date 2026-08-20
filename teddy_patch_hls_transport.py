from pathlib import Path


ENTRYPOINT = Path('teddy_entrypoint.py')


def replace_function(text, function_name, next_function_name, replacement):
    start_marker = f'def {function_name}('
    end_marker = f'def {next_function_name}('
    start = text.find(start_marker)
    if start < 0:
        raise SystemExit(f'HLS transport patch: {function_name} start not found')
    end = text.find(end_marker, start)
    if end < 0:
        raise SystemExit(f'HLS transport patch: {next_function_name} boundary not found')
    if text.find(start_marker, start + len(start_marker)) >= 0 and text.find(start_marker, start + len(start_marker)) < end:
        raise SystemExit(f'HLS transport patch: duplicate {function_name} definition')
    return text[:start] + replacement.rstrip() + '\n\n\n' + text[end:]


def main():
    text = ENTRYPOINT.read_text(encoding='utf-8')

    old_import = 'from concurrent.futures import ThreadPoolExecutor\n'
    new_import = 'from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait\n'
    if old_import not in text:
        raise SystemExit('HLS transport patch: concurrent.futures import anchor missing')
    text = text.replace(old_import, new_import, 1)

    core_import = 'import app as core\n'
    if core_import not in text:
        raise SystemExit('HLS transport patch: app core import anchor missing')
    text = text.replace(core_import, core_import + 'import teddy_hls_transport\n', 1)

    fetch_segment = r'''def _fetch_segment(task_id, seg_url, headers):
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
            )
            if response.status_code == 200:
                return response.content
            last = f'HTTP {response.status_code}'
            # A non-200 response should not keep a potentially poisoned CONNECT/TLS
            # tunnel around for the next browser-fingerprint retry.
            teddy_hls_transport.invalidate()
        except (DownloadPaused, core.DownloadCancelled):
            raise
        except Exception as exc:
            last = str(exc)
            # VPN reconnects keep the same Gluetun proxy URL. Dropping the worker
            # Session here guarantees the retry opens a fresh CONNECT/TLS path.
            teddy_hls_transport.invalidate()
        if attempt + 1 < SEGMENT_RETRY_ATTEMPTS:
            delay = SEGMENT_RETRY_BACKOFF[attempt + 1]
            print(
                f'[세그먼트 재시도] {attempt + 2}/{SEGMENT_RETRY_ATTEMPTS} '
                f'({delay}s 후, {target}) {os.path.basename(seg_url)}: {last}',
                flush=True,
            )
            _interruptible_sleep(task_id, delay)
    raise ValueError(f'세그먼트 반복 실패({last}): {seg_url}')'''

    text = replace_function(text, '_fetch_segment', '_fetch_variant_playlist', fetch_segment)

    download_hls = r'''def _download_hls_resumable(task_id, variant_url, headers, out_path):
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
    print(
        f'[다운로드] 세그먼트 {total}개 (완료 {done} / 남음 {len(pending)}) '
        f'· persistent session + continuous {teddy_hls_transport.HLS_WORKERS} workers',
        flush=True,
    )
    if task_id in core.tasks:
        core.tasks[task_id]['progress'] = f'{int(done * 100 / total)}%'
        core.tasks[task_id]['speed_bps'] = 0
        core.tasks[task_id]['downloaded_bytes'] = downloaded_bytes
        core.tasks[task_id]['total_bytes_estimate'] = total_bytes_estimate
        core.save_tasks()

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
    window_started = time.monotonic()
    window_bytes = 0
    last_speed = 0
    pending_iter = iter(pending)
    in_flight = {}
    executor = ThreadPoolExecutor(max_workers=teddy_hls_transport.HLS_WORKERS)

    def submit_one():
        try:
            item = next(pending_iter)
        except StopIteration:
            return False
        future = executor.submit(fetch_to_file, item)
        in_flight[future] = item
        return True

    try:
        for _ in range(min(teddy_hls_transport.HLS_WORKERS, len(pending))):
            submit_one()

        while in_flight:
            _check_task_state(task_id)
            completed, _ = wait(tuple(in_flight), return_when=FIRST_COMPLETED)
            for future in completed:
                in_flight.pop(future, None)
                byte_count = future.result()
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

                # Continuous scheduler: immediately refill the slot that just
                # completed instead of waiting for a fixed 16-segment batch.
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

    list_path = os.path.join(parts_dir, 'filelist.txt')
    with open(list_path, 'w', encoding='utf-8') as list_file:
        for index in range(total):
            list_file.write(f"file '{seg_path(index)}'\n")

    print('[ffmpeg] mp4 리먹스 중...', flush=True)
    remux_tmp = os.path.join(parts_dir, 'remux-output.mp4')
    try:
        if os.path.exists(remux_tmp):
            os.remove(remux_tmp)
    except OSError:
        pass
    proc = subprocess.run(
        ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0',
         '-i', list_path, '-c', 'copy', remux_tmp],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0 and os.path.isfile(remux_tmp) and os.path.getsize(remux_tmp) > 0:
        os.replace(remux_tmp, out_path)
        shutil.rmtree(parts_dir, ignore_errors=True)
        return out_path

    if proc.returncode == 0:
        detail = 'ffmpeg는 성공을 반환했지만 임시 MP4 결과를 확인하지 못했습니다.'
    else:
        detail = (proc.stderr or '')[:300]
    print(
        f'[ffmpeg] mp4 리먹스 실패(코드 {proc.returncode}) → ts로 저장: {detail}',
        flush=True,
    )
    try:
        if os.path.exists(remux_tmp):
            os.remove(remux_tmp)
    except OSError:
        pass
    ts_out = (out_path[:-4] if out_path.endswith('.mp4') else out_path) + '.ts'
    with open(ts_out, 'wb') as output_file:
        for index in range(total):
            with open(seg_path(index), 'rb') as segment_file:
                output_file.write(segment_file.read())
    shutil.rmtree(parts_dir, ignore_errors=True)
    return ts_out'''

    text = replace_function(text, '_download_hls_resumable', '_store_info', download_hls)

    ENTRYPOINT.write_text(text, encoding='utf-8')
    print('persistent HLS sessions + continuous scheduler runtime patch: OK')


if __name__ == '__main__':
    main()
