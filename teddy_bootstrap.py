import os

import teddy_logging

# Install the stdout/stderr tee before importing the application so startup,
# downloader, retry and VPN messages are all available in the web log viewer.
teddy_logging.install_capture()

import time

import teddy_entrypoint as reliability
import teddy_generic
import teddy_network
import teddy_storage


core = reliability.core
teddy_network.install(core)
teddy_logging.install_routes(core)
teddy_storage.install_file_routes(core)


# Keep the proven segment retry implementation intact and add one recovery layer
# around it. The original function still performs all six retry/backoff attempts
# first; only a network-like terminal failure can trigger a VPN route change.
_original_fetch_segment = reliability._fetch_segment


def _fetch_segment_with_network_recovery(task_id, seg_url, headers):
    failed_since = time.monotonic()
    try:
        return _original_fetch_segment(task_id, seg_url, headers)
    except (reliability.DownloadPaused, core.DownloadCancelled):
        raise
    except Exception as exc:
        message = str(exc)
        if not teddy_network.is_recoverable_failure(message):
            raise

        print(
            f'[VPN 자동복구] 세그먼트 재시도 소진 → 네트워크 복구 판단: {message[:180]}',
            flush=True,
        )
        recovered = teddy_network.auto_recover(
            core,
            task_id=task_id,
            reason=message,
            failed_since=failed_since,
        )
        if not recovered:
            raise

        reliability._check_task_state(task_id)
        print('[VPN 자동복구] 새 VPN 경로에서 같은 세그먼트 재시도', flush=True)
        return _original_fetch_segment(task_id, seg_url, headers)


reliability._fetch_segment = _fetch_segment_with_network_recovery
core._fetch_segment = _fetch_segment_with_network_recovery


# Route only the site that needs the proven custom HLS path to that engine.
# Everything else goes through yt-dlp's maintained extractor/downloader stack.
_custom_download_video = reliability._download_video


def _move_custom_result_to_site_folder(task_id, url):
    task = core.tasks.get(task_id)
    if not task or task.get('status') != '완료' or not task.get('filename'):
        return

    current_name = str(task.get('filename') or '').replace('\\', '/')
    # Old/root-style custom completion gives only a basename. If it is already
    # nested, leave it alone so retries and future storage implementations remain compatible.
    if '/' in current_name:
        task['storage_folder'] = current_name.split('/', 1)[0]
        core.save_tasks()
        return

    source = os.path.join(core.DOWNLOAD_DIR, current_name)
    if not os.path.isfile(source):
        return

    site_key, site_dir = teddy_storage.ensure_site_dir(core, url, custom=True)
    destination = os.path.join(site_dir, os.path.basename(source))
    os.replace(source, destination)
    task['filename'] = teddy_storage.relative_public_path(core, destination)
    task['storage_folder'] = site_key
    core.save_tasks()
    print(f"[Storage] custom-hls 완료 파일 이동: {task['filename']}", flush=True)


def _dispatch_download(task_id, url):
    task = core.tasks.get(task_id)
    if teddy_generic.is_custom_site(core, url):
        if task:
            task['engine'] = 'custom-hls'
            task['storage_folder'] = 'missav'
            core.save_tasks()
        print(f'[Engine] custom-hls: {url}', flush=True)
        result = _custom_download_video(task_id, url)
        _move_custom_result_to_site_folder(task_id, url)
        return result

    if task:
        task['engine'] = 'yt-dlp'
        task['storage_folder'] = teddy_storage.site_key_for_url(url)
        core.save_tasks()
    print(f'[Engine] yt-dlp: {url}', flush=True)
    return teddy_generic.download_generic(core, reliability, task_id, url)


reliability._download_video = _dispatch_download
core.download_video = _dispatch_download
teddy_generic.install_delete_cleanup(core)


if __name__ == '__main__':
    print(f"\n{'=' * 50}")
    print('Downloader Started (Teddy Custom)')
    print(f'Download directory: {core.DOWNLOAD_DIR}')
    print('Open: http://localhost:5000')
    print(f"{'=' * 50}\n")
    core.app.run(host='0.0.0.0', port=5000, debug=False)
