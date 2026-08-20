import time

import teddy_entrypoint as reliability
import teddy_network


core = reliability.core
teddy_network.install(core)


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


if __name__ == '__main__':
    print(f"\n{'=' * 50}")
    print('Downloader Started (Teddy Custom)')
    print(f'Download directory: {core.DOWNLOAD_DIR}')
    print('Open: http://localhost:5000')
    print(f"{'=' * 50}\n")
    core.app.run(host='0.0.0.0', port=5000, debug=False)
