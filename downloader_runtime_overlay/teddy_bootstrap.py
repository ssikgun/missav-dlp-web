import os

import teddy_logging

# Install the stdout/stderr tee before importing the application so startup,
# downloader, retry and VPN messages are all available in the web log viewer.
teddy_logging.install_capture()

import time
import threading

import teddy_entrypoint as reliability
import teddy_duplicates
import teddy_generic
import teddy_network
import teddy_routing
import teddy_vpn_health
import teddy_proxy_pool
import teddy_storage
import teddy_download_safety
import teddy_mp4_queue
import teddy_browser_config
import teddy_auth
import teddy_downloader_admin
import teddy_discovery_runtime
import teddy_selkies_control_api


core = reliability.core

if core.STARTUP_HEALTH_ONLY:
    print('[Teddy] health-only startup: data, cleanup, and workers disabled', flush=True)
    if __name__ == '__main__':
        core.app.run(host='127.0.0.1', port=5000, debug=False)
    raise SystemExit(0)

teddy_download_safety.install_ytdlp_ffmpeg_guard(core)

# Route curl_cffi calls through a thread-local proxy context. Outside a download
# route context the wrapped client behaves exactly like curl_cffi did before.
core.cffi_requests = teddy_routing.RouteAwareRequests(core.cffi_requests)

teddy_routing.install(core)
teddy_duplicates.install(core)
teddy_network.install(core)
teddy_vpn_health.install(core, teddy_network)

# Any successful manual or automatic VPN rotation invalidates the recent
# failure window so stale failures cannot immediately trigger another change.
_original_vpn_rotation = teddy_network._perform_rotation_locked
def _perform_rotation_with_health_reset(*args, **kwargs):
    result = _original_vpn_rotation(*args, **kwargs)
    if result.get('ok'):
        teddy_vpn_health.clear()
    return result
teddy_network._perform_rotation_locked = _perform_rotation_with_health_reset

teddy_logging.install_routes(core)
teddy_storage.install_file_routes(core)
teddy_browser_config.install(core)
teddy_discovery_runtime.install(core)
teddy_selkies_control_api.install(core)
teddy_proxy_pool.install(core, teddy_routing, teddy_network)
teddy_auth.install(core)
teddy_downloader_admin.install(core)


# Keep the proven segment retry implementation intact and add route context plus
# VPN/proxy recovery around it. Direct tasks never rotate another route.
_original_fetch_segment = reliability._fetch_segment
_original_fetch_variant_playlist = reliability._fetch_variant_playlist


def _fetch_variant_playlist_routed(task_id, variant_url, headers):
    task = core.tasks.get(task_id) or {}
    mode = task.get('network_mode') or 'direct'
    with teddy_routing.request_route(mode):
        return _original_fetch_variant_playlist(task_id, variant_url, headers)


_proxy_recovery_lock = threading.Lock()
_proxy_recovery_state = {'last_rotation_at': 0.0}
_proxy_last_rotation_at = {}


def _fetch_segment_with_network_recovery(task_id, seg_url, headers, transport_mode='per-worker', worker_count=None):
    task = core.tasks.get(task_id) or {}
    mode = task.get('network_mode') or 'direct'
    failed_since = time.monotonic()
    try:
        with teddy_routing.request_route(mode):
            return _original_fetch_segment(task_id, seg_url, headers, transport_mode=transport_mode, worker_count=worker_count)
    except (reliability.DownloadPaused, core.DownloadCancelled):
        raise
    except Exception as exc:
        message = str(exc)
        if not teddy_network.is_recoverable_failure(message):
            raise

        if mode == 'proxy':
            print(
                f'[Proxy] 세그먼트 재시도 소진 -> 다음 프록시 판단: {message[:180]}',
                flush=True,
            )
            reused_rotation = False
            with _proxy_recovery_lock:
                last_rotation = float(_proxy_recovery_state.get('last_rotation_at') or 0.0)
                if last_rotation > failed_since:
                    reused_rotation = True
                else:
                    teddy_proxy_pool.note_failure(core, reason=message)
                    if not teddy_proxy_pool.rotate_after_failure(core, reason=message):
                        raise
                    _proxy_last_rotation_at[task_id] = time.monotonic()
                    _proxy_recovery_state['last_rotation_at'] = _proxy_last_rotation_at[task_id]

            reliability._check_task_state(task_id)
            record = teddy_proxy_pool.current_record()
            current = core.tasks.get(task_id)
            if current:
                current['network_proxy'] = record.get('proxy', '')
                current['network_proxy_latency_ms'] = int(record.get('latency_ms') or 0)
                current['network_proxy_speed_bps'] = int(record.get('speed_bps') or 0)
                core.save_tasks()
            if reused_rotation:
                print('[Proxy] 다른 작업/세그먼트가 이미 프록시를 변경함 -> 새 후보 재사용', flush=True)
            else:
                print('[Proxy] 새 프록시에서 같은 세그먼트 재시도', flush=True)
            with teddy_routing.request_route('proxy'):
                return _original_fetch_segment(task_id, seg_url, headers, transport_mode=transport_mode, worker_count=worker_count)

        if mode != 'vpn':
            raise

        print(
            f'[VPN 자동복구] 세그먼트 재시도 소진 -> 네트워크 복구 판단: {message[:180]}',
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
            return _original_fetch_segment(task_id, seg_url, headers, transport_mode=transport_mode, worker_count=worker_count)


reliability._fetch_variant_playlist = _fetch_variant_playlist_routed
reliability._fetch_segment = _fetch_segment_with_network_recovery
core._fetch_variant_playlist = _fetch_variant_playlist_routed
core._fetch_segment = _fetch_segment_with_network_recovery


# Route only the site that needs the proven custom HLS path to that engine.
# Everything else goes through yt-dlp's maintained extractor/downloader stack.
_custom_download_video = reliability._download_video


def _publish_pending_result(task_id):
    if not teddy_download_safety.begin_final_publish(core, task_id):
        task = core.tasks.get(task_id) or {}
        if task.get('status') in ('일시정지 요청 중', '일시정지'):
            teddy_download_safety.complete_pause_request(core, task_id)
            return {'status': 'paused'}
        return {'status': 'error', 'error': '최종 저장 전 작업 상태가 바뀌어 게시를 보류했습니다.', 'error_kind': 'safety'}
    try:
        published = teddy_storage.publish_pending_task(core, task_id)
        if teddy_download_safety.cleanup_parts_after_verified_publish(core, task_id):
            print(f'[Storage] 최종 저장 검증 후 HLS 조각 정리 완료: {task_id}', flush=True)
        teddy_mp4_queue.cleanup_after_publish(core, task_id)
        task = core.tasks.get(task_id) or {}
        print(f"[Storage] 완료 파일 게시 성공: {task.get('filename') or published}", flush=True)
        return {'status': 'complete'}
    except teddy_storage.PublishError as exc:
        return teddy_storage.mark_publish_error(core, task_id, exc)
    finally:
        teddy_download_safety.end_final_publish(task_id)


def _custom_result(task_id):
    task = core.tasks.get(task_id)
    if not task:
        return {'status': 'cancelled'}
    status = str(task.get('status') or '')
    if status == '완료':
        return {'status': 'complete'}
    if status in ('일시정지', '일시정지 요청 중'):
        return {'status': 'paused'}
    if task.get('mp4_stage') in ('queued', 'running', 'output_ready', 'publish_pending'):
        return {'status': 'mp4-queued'}
    if status == '취소됨':
        return {'status': 'cancelled'}
    if status.startswith('에러'):
        return {
            'status': 'error',
            'error': str(task.get('last_error_detail') or status),
            'error_kind': task.get('error_kind'),
        }
    return {'status': 'unknown'}


def _run_engine_once(task_id, url, custom, mode):
    # A previous run may have completed all local work but failed while publishing
    # to NAS. Retry the pending publish before touching the network again.
    if teddy_storage.has_pending_result(core, task_id):
        return _publish_pending_result(task_id)

    if mode == 'proxy' and not teddy_proxy_pool.ensure_ready(core, wait_seconds=35):
        return {
            'status': 'error',
            'error': 'Proxy Pool unavailable: 검증을 통과한 무료 프록시가 없습니다.',
        }

    task = core.tasks.get(task_id)
    if task:
        task['network_mode'] = mode
        task['engine'] = 'custom-hls' if custom else 'yt-dlp'
        task['storage_folder'] = (
            'missav' if custom else teddy_storage.site_key_for_url(url)
        )
        if mode == 'proxy':
            record = teddy_proxy_pool.current_record()
            task['network_proxy'] = record.get('proxy', '')
            task['network_proxy_latency_ms'] = int(record.get('latency_ms') or 0)
            task['network_proxy_speed_bps'] = int(record.get('speed_bps') or 0)
            task['network_proxy_exit_ip'] = record.get('exit_ip', '')
        else:
            task.pop('network_proxy', None)
            task.pop('network_proxy_latency_ms', None)
            task.pop('network_proxy_speed_bps', None)
            task.pop('network_proxy_exit_ip', None)
        core.save_tasks()

    route_label = teddy_routing.mode_label(mode)
    engine_label = 'custom-hls' if custom else 'yt-dlp'
    print(f'[Engine] {engine_label} · {route_label}: {url}', flush=True)

    if custom:
        with teddy_routing.request_route(mode):
            _custom_download_video(task_id, url)
        if teddy_storage.has_pending_result(core, task_id):
            return _publish_pending_result(task_id)
        return _custom_result(task_id)

    result = teddy_generic.download_generic(
        core,
        reliability,
        task_id,
        url,
        network_mode=mode,
    )
    if result.get('status') == 'local-complete' or teddy_storage.has_pending_result(core, task_id):
        return _publish_pending_result(task_id)
    return result


def _reactivate_task(task_id):
    current = core.tasks.get(task_id)
    if current:
        current['status'] = '다운로드 중'
        current['speed_bps'] = 0
        core.save_tasks()


def _dispatch_download(task_id, url):
    task = core.tasks.get(task_id)
    if not task:
        return

    custom = teddy_generic.is_custom_site(core, url)
    override = str(task.get('network_override') or 'auto').lower()

    # New tasks already contain a resolved mode. Existing tasks from older images
    # are resolved here once. Paused/error retries keep their persisted last mode.
    if task.get('network_mode') in teddy_routing.VALID_MODES and task.get('network_route_source'):
        decision = {
            'site': task.get('network_site') or teddy_routing.canonical_site(url),
            'mode': task['network_mode'],
            'source': task.get('network_route_source') or 'default',
            'fixed': override in teddy_routing.VALID_MODES or task.get('network_route_source') == 'manual',
        }
    else:
        decision = teddy_routing.resolve(url, override=override)
        task['network_site'] = decision['site']
        task['network_mode'] = decision['mode']
        task['network_route_source'] = decision['source']
        core.save_tasks()

    primary = decision['mode']
    source = decision['source']
    proxy_enabled = bool(teddy_proxy_pool.snapshot().get('enabled'))
    modes = [primary]
    if not decision['fixed']:
        modes.extend(teddy_routing.fallback_modes(primary, proxy_enabled=proxy_enabled))

    # A volatile free proxy may disappear between validation and use. Allow two
    # additional verified proxy candidates before falling back to VPN.
    proxy_task_retries = 0
    index = 0
    previous_mode = None
    while index < len(modes):
        if task_id not in core.tasks:
            return
        mode = modes[index]
        if index:
            teddy_routing.prepare_fallback(core, task_id, mode)
            print(
                f'[Routing] 네트워크 fallback: {previous_mode or primary} -> {mode} '
                f'({decision.get("site") or "unknown"})',
                flush=True,
            )
        else:
            teddy_routing.apply_task_mode(core, task_id, mode, source)

        attempted_proxy = ''
        if mode == 'proxy':
            attempted_proxy = str(teddy_proxy_pool.current_record().get('proxy') or '')
        result = _run_engine_once(task_id, url, custom=custom, mode=mode) or {}
        status = result.get('status')
        if status == 'complete':
            if mode == 'proxy':
                teddy_proxy_pool.observe_task_success(core, task_id)
            teddy_routing.learn_success(core, url, mode, source)
            return
        if status in ('paused', 'cancelled'):
            return
        if status != 'error':
            return
        if result.get('error_kind') in ('storage', 'safety'):
            # Storage failures must never trigger Direct/Proxy/VPN route fallback.
            # local_result_path is intentionally retained for publish-only retry.
            return

        error_message = result.get('error') or ''
        recoverable = teddy_routing.should_fallback(teddy_network, error_message)

        if (
            mode == 'proxy'
            and recoverable
            and proxy_task_retries < 2
        ):
            proxy_ready = False
            reused_rotation = False
            with _proxy_recovery_lock:
                current_proxy = str(teddy_proxy_pool.current_record().get('proxy') or '')
                if attempted_proxy and current_proxy and current_proxy != attempted_proxy:
                    # Another task already rotated the shared pool while this
                    # engine attempt was failing. Reuse that new candidate.
                    proxy_ready = True
                    reused_rotation = True
                else:
                    teddy_proxy_pool.note_failure(core, reason=error_message)
                    proxy_ready = teddy_proxy_pool.rotate_after_failure(
                        core, reason=error_message
                    )
                    if proxy_ready:
                        _proxy_recovery_state['last_rotation_at'] = time.monotonic()

            if proxy_ready:
                proxy_task_retries += 1
                modes.insert(index + 1, 'proxy')
                _reactivate_task(task_id)
                previous_mode = 'proxy'
                if reused_rotation:
                    print(
                        '[Proxy] 엔진 단계 실패 -> 다른 작업이 바꾼 새 후보 재사용',
                        flush=True,
                    )
                else:
                    print(
                        '[Proxy] 엔진 단계 실패 -> 다음 Proxy 후보로 재시도',
                        flush=True,
                    )
                index += 1
                continue

        if decision['fixed'] or index + 1 >= len(modes):
            return
        if not recoverable:
            print(
                f'[Routing] fallback 생략: 네트워크성 오류가 아님 · {error_message[:180]}',
                flush=True,
            )
            return

        _reactivate_task(task_id)
        previous_mode = mode
        index += 1


_task_claim_lock = threading.Lock()
_claimed_tasks = set()


def _set_safety_failure(task_id, exc):
    task = core.tasks.get(task_id)
    if not task:
        return
    kind = teddy_download_safety.failure_kind(exc) or 'safety'
    prefix = '저장 공간 부족' if kind == 'storage' else '안전 잠금 실패'
    task['status'] = f'에러: {prefix}: {str(exc)[:100]}'
    task['error_kind'] = kind
    task['last_error_detail'] = str(exc)[:1000]
    task['speed_bps'] = 0
    core.save_tasks()


def _dispatch_download_guarded(task_id, url):
    with _task_claim_lock:
        if task_id in _claimed_tasks:
            print(f'[Queue] 동일 task 중복 실행 차단: {task_id}', flush=True)
            return
        _claimed_tasks.add(task_id)
    claim = None
    try:
        claim = teddy_download_safety.try_task_claim(core.DOWNLOAD_DIR, task_id)
        if claim is None:
            print(f'[Queue] 다른 프로세스가 보유한 task 실행 잠금: {task_id}', flush=True)
            return
        teddy_download_safety.ensure_download_start_space(core.DOWNLOAD_DIR)
        return _dispatch_download(task_id, url)
    except teddy_download_safety.DownloadSafetyError as exc:
        _set_safety_failure(task_id, exc)
        return
    except OSError as exc:
        if teddy_download_safety.is_enospc(exc):
            _set_safety_failure(task_id, exc)
            return
        raise
    finally:
        try:
            if claim is not None:
                claim.release()
        finally:
            with _task_claim_lock:
                _claimed_tasks.discard(task_id)


reliability._download_video = _dispatch_download_guarded
core.download_video = _dispatch_download_guarded
teddy_generic.install_delete_cleanup(core)
_delete_view = core.app.view_functions.get('delete_task')
if _delete_view:
    def _delete_with_mp4_guard(task_id):
        if teddy_mp4_queue.has_task(core, task_id):
            return core.jsonify({'status': 'error', 'message': 'MP4 변환 대기/복구 작업은 삭제할 수 없습니다.'}), 409
        return _delete_view(task_id)
    core.app.view_functions['delete_task'] = _delete_with_mp4_guard
teddy_mp4_queue.install(core, _publish_pending_result)
core.start_download_workers()


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
    print(f'Work directory: {core.DOWNLOAD_DIR}')
    print(f'Final directory: {teddy_storage.public_root(core)}')
    print('Open: http://localhost:5000')
    print(f"{'=' * 50}\n")
    core.app.run(host='0.0.0.0', port=5000, debug=False)
