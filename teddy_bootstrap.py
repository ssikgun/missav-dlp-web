import os

import teddy_logging

# Install the stdout/stderr tee before importing the application so startup,
# downloader, retry and VPN messages are all available in the web log viewer.
teddy_logging.install_capture()

import time

import teddy_entrypoint as reliability
import teddy_generic
import teddy_network
import teddy_routing
import teddy_storage


core = reliability.core

# Route curl_cffi calls through a thread-local proxy context. Outside a download
# route context the wrapped client behaves exactly like curl_cffi did before.
core.cffi_requests = teddy_routing.RouteAwareRequests(core.cffi_requests)

teddy_routing.install(core)
teddy_network.install(core)
teddy_logging.install_routes(core)
teddy_storage.install_file_routes(core)


# Keep the proven segment retry implementation intact and add route context plus
# the existing VPN rotation layer around it. Direct tasks never rotate Gluetun;
# a terminal Direct failure is handled later by the task-level VPN fallback.
_original_fetch_segment = reliability._fetch_segment
_original_fetch_variant_playlist = reliability._fetch_variant_playlist


def _fetch_variant_playlist_routed(task_id, variant_url, headers):
    task = core.tasks.get(task_id) or {}
    mode = task.get('network_mode') or 'direct'
    with teddy_routing.request_route(mode):
        return _original_fetch_variant_playlist(task_id, variant_url, headers)


def _fetch_segment_with_network_recovery(task_id, seg_url, headers):
    task = core.tasks.get(task_id) or {}
    mode = task.get('network_mode') or 'direct'
    failed_since = time.monotonic()
    try:
        with teddy_routing.request_route(mode):
            return _original_fetch_segment(task_id, seg_url, headers)
    except (reliability.DownloadPaused, core.DownloadCancelled):
        raise
    except Exception as exc:
        message = str(exc)
        if mode != 'vpn' or not teddy_network.is_recoverable_failure(message):
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
        with teddy_routing.request_route('vpn'):
            return _original_fetch_segment(task_id, seg_url, headers)


reliability._fetch_variant_playlist = _fetch_variant_playlist_routed
reliability._fetch_segment = _fetch_segment_with_network_recovery
core._fetch_variant_playlist = _fetch_variant_playlist_routed
core._fetch_segment = _fetch_segment_with_network_recovery


# Route only the site that needs the proven custom HLS path to that engine.
# Everything else goes through yt-dlp's maintained extractor/downloader stack.
_custom_download_video = reliability._download_video


def _move_custom_result_to_site_folder(task_id, url):
    task = core.tasks.get(task_id)
    if not task or task.get('status') != '완료' or not task.get('filename'):
        return

    current_name = str(task.get('filename') or '').replace('\\', '/')
    if '/' in current_name:
        task['storage_folder'] = current_name.split('/', 1)[0]
        core.save_tasks()
        return

    source = os.path.join(core.DOWNLOAD_DIR, current_name)
    if not os.path.isfile(source):
        return

    try:
        site_key, site_dir = teddy_storage.ensure_site_dir(core, url, custom=True)
        destination = os.path.join(site_dir, os.path.basename(source))
        os.replace(source, destination)
        task['filename'] = teddy_storage.relative_public_path(core, destination)
        task['storage_folder'] = site_key
        core.save_tasks()
        print(f"[Storage] custom-hls 완료 파일 이동: {task['filename']}", flush=True)
    except OSError as exc:
        print(f'[Storage] 사이트 폴더 이동 실패 → 루트 파일 유지: {exc}', flush=True)


def _custom_result(task_id):
    task = core.tasks.get(task_id)
    if not task:
        return {'status': 'cancelled'}
    status = str(task.get('status') or '')
    if status == '완료':
        return {'status': 'complete'}
    if status in ('일시정지', '일시정지 요청 중'):
        return {'status': 'paused'}
    if status == '취소됨':
        return {'status': 'cancelled'}
    if status.startswith('에러'):
        return {
            'status': 'error',
            'error': str(task.get('last_error_detail') or status),
        }
    return {'status': 'unknown'}


def _run_engine_once(task_id, url, custom, mode):
    task = core.tasks.get(task_id)
    if task:
        task['network_mode'] = mode
        task['engine'] = 'custom-hls' if custom else 'yt-dlp'
        task['storage_folder'] = (
            'missav' if custom else teddy_storage.site_key_for_url(url)
        )
        core.save_tasks()

    route_label = 'VPN' if mode == 'vpn' else 'Direct'
    engine_label = 'custom-hls' if custom else 'yt-dlp'
    print(f'[Engine] {engine_label} · {route_label}: {url}', flush=True)

    if custom:
        with teddy_routing.request_route(mode):
            _custom_download_video(task_id, url)
        result = _custom_result(task_id)
        if result.get('status') == 'complete':
            _move_custom_result_to_site_folder(task_id, url)
        return result

    return teddy_generic.download_generic(
        core,
        reliability,
        task_id,
        url,
        network_mode=mode,
    )


def _dispatch_download(task_id, url):
    task = core.tasks.get(task_id)
    if not task:
        return

    custom = teddy_generic.is_custom_site(core, url)
    override = str(task.get('network_override') or 'auto').lower()

    # New tasks already contain a resolved mode. Existing tasks from older images
    # are resolved here once. Paused/error retries keep their persisted last mode.
    if task.get('network_mode') in ('direct', 'vpn') and task.get('network_route_source'):
        decision = {
            'site': task.get('network_site') or teddy_routing.canonical_site(url),
            'mode': task['network_mode'],
            'source': task.get('network_route_source') or 'default',
            'fixed': override in ('direct', 'vpn') or task.get('network_route_source') == 'manual',
        }
    else:
        decision = teddy_routing.resolve(url, override=override)
        task['network_site'] = decision['site']
        task['network_mode'] = decision['mode']
        task['network_route_source'] = decision['source']
        core.save_tasks()

    primary = decision['mode']
    source = decision['source']
    modes = [primary]
    if not decision['fixed']:
        modes.append(teddy_routing.fallback_mode(primary))

    for index, mode in enumerate(modes):
        if task_id not in core.tasks:
            return
        if index:
            teddy_routing.prepare_fallback(core, task_id, mode)
            print(
                f'[Routing] 네트워크 fallback: {primary} -> {mode} '
                f'({decision.get("site") or "unknown"})',
                flush=True,
            )
        else:
            teddy_routing.apply_task_mode(core, task_id, mode, source)

        result = _run_engine_once(task_id, url, custom=custom, mode=mode) or {}
        status = result.get('status')
        if status == 'complete':
            teddy_routing.learn_success(core, url, mode, source)
            return
        if status in ('paused', 'cancelled'):
            return
        if status != 'error':
            return

        error_message = result.get('error') or ''
        if decision['fixed'] or index + 1 >= len(modes):
            return
        if not teddy_routing.should_fallback(teddy_network, error_message):
            print(
                f'[Routing] VPN fallback 생략: 네트워크성 오류가 아님 · {error_message[:180]}',
                flush=True,
            )
            return

        # A failed attempt may have left status=error. Put it back into an active
        # state before trying the alternate route; partial files remain intact.
        current = core.tasks.get(task_id)
        if current:
            current['status'] = '다운로드 중'
            current['speed_bps'] = 0
            core.save_tasks()


reliability._download_video = _dispatch_download
core.download_video = _dispatch_download
teddy_generic.install_delete_cleanup(core)


# Thumbnail fetches should follow the last successful/current route of the task.
_original_thumbnail = core.app.view_functions.get('teddy_task_thumbnail')
if _original_thumbnail:
    def _thumbnail_routed(task_id):
        task = core.tasks.get(task_id) or {}
        mode = task.get('network_mode') or 'direct'
        with teddy_routing.request_route(mode):
            return _original_thumbnail(task_id)
    core.app.view_functions['teddy_task_thumbnail'] = _thumbnail_routed


if __name__ == '__main__':
    print(f"\n{'=' * 50}")
    print('Downloader Started (Teddy Custom)')
    print(f'Download directory: {core.DOWNLOAD_DIR}')
    print('Open: http://localhost:5000')
    print(f"{'=' * 50}\n")
    core.app.run(host='0.0.0.0', port=5000, debug=False)
