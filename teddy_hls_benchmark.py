import argparse
import json
import time
from urllib.request import urlopen


API_BASE = 'http://127.0.0.1:5000'
MB = 1_000_000


def get_json(path):
    with urlopen(API_BASE + path, timeout=5) as response:
        return json.load(response)


def select_task(task_id=None):
    tasks = get_json('/api/tasks')
    if task_id:
        task = tasks.get(task_id)
        if not task:
            raise RuntimeError(f'task not found: {task_id}')
        return task_id, task

    active = [
        (tid, task)
        for tid, task in tasks.items()
        if task.get('status') == '다운로드 중' and task.get('engine') == 'custom-hls'
    ]
    if not active:
        raise RuntimeError('active custom-hls task not found')
    if len(active) > 1:
        ids = ', '.join(tid for tid, _ in active)
        raise RuntimeError(f'multiple active custom-hls tasks: {ids} (use --task-id)')
    return active[0]


def proxy_snapshot():
    try:
        status = get_json('/api/proxy/status')
    except Exception:
        return '', 0
    return str(status.get('current_proxy') or ''), int(status.get('current_latency_ms') or 0)


def task_snapshot(task_id):
    tasks = get_json('/api/tasks')
    task = tasks.get(task_id)
    if not task:
        raise RuntimeError('task disappeared during benchmark')
    return task


def main():
    parser = argparse.ArgumentParser(description='Read-only Teddy HLS throughput sampler')
    parser.add_argument('duration', nargs='?', type=float, default=60.0,
                        help='measurement seconds (default: 60)')
    parser.add_argument('--interval', type=float, default=2.0,
                        help='sample interval seconds (default: 2)')
    parser.add_argument('--warmup', type=float, default=10.0,
                        help='warm-up seconds excluded from average (default: 10)')
    parser.add_argument('--task-id', default=None,
                        help='task id when multiple custom-hls downloads are active')
    args = parser.parse_args()

    if args.duration <= 0 or args.interval <= 0 or args.warmup < 0:
        raise SystemExit('duration/interval must be > 0 and warmup must be >= 0')

    task_id, task = select_task(args.task_id)
    workers = task.get('hls_workers', '?')
    proxy_start, latency_start = proxy_snapshot()
    print(
        f'Teddy HLS benchmark: task={task_id} workers={workers} '
        f'proxy={proxy_start or "-"} latency={latency_start or "-"}ms',
        flush=True,
    )
    print(
        f'warmup={args.warmup:.0f}s measure={args.duration:.0f}s interval={args.interval:.1f}s '
        f'(MB/s = 1,000,000 bytes/s)',
        flush=True,
    )

    if args.warmup:
        warmup_until = time.monotonic() + args.warmup
        while True:
            remaining = warmup_until - time.monotonic()
            if remaining <= 0:
                break
            task = task_snapshot(task_id)
            if task.get('status') != '다운로드 중':
                raise RuntimeError(f'task stopped during warmup: {task.get("status")}')
            time.sleep(min(args.interval, remaining))

    task = task_snapshot(task_id)
    if task.get('status') != '다운로드 중':
        raise RuntimeError(f'task is not downloading: {task.get("status")}')

    start_bytes = int(task.get('downloaded_bytes') or 0)
    start_time = time.monotonic()
    prev_bytes = start_bytes
    prev_time = start_time
    proxy_changed = False
    observed_workers = {task.get('hls_workers', '?')}

    deadline = start_time + args.duration
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(args.interval, remaining))

        now = time.monotonic()
        task = task_snapshot(task_id)
        if task.get('status') != '다운로드 중':
            print(f'task stopped: {task.get("status")}', flush=True)
            break

        current_bytes = int(task.get('downloaded_bytes') or 0)
        elapsed = max(now - start_time, 0.001)
        delta_elapsed = max(now - prev_time, 0.001)
        current_speed = max(0, current_bytes - prev_bytes) / delta_elapsed
        average_speed = max(0, current_bytes - start_bytes) / elapsed
        api_speed = int(task.get('speed_bps') or 0)
        observed_workers.add(task.get('hls_workers', '?'))

        proxy_now, latency_now = proxy_snapshot()
        if proxy_start and proxy_now and proxy_now != proxy_start:
            proxy_changed = True

        stamp = time.strftime('%H:%M:%S')
        print(
            f'[{stamp}] workers={task.get("hls_workers", "?")} '
            f'progress={task.get("progress", "?")} '
            f'actual={current_speed / MB:6.2f} MB/s '
            f'api={api_speed / MB:6.2f} MB/s '
            f'avg={average_speed / MB:6.2f} MB/s '
            f'proxy={proxy_now or "-"} {latency_now or "-"}ms'
            + ('  ⚠ PROXY CHANGED' if proxy_changed else ''),
            flush=True,
        )

        prev_bytes = current_bytes
        prev_time = now

    end_time = time.monotonic()
    task = task_snapshot(task_id)
    end_bytes = int(task.get('downloaded_bytes') or 0)
    measured = max(end_time - start_time, 0.001)
    transferred = max(0, end_bytes - start_bytes)
    average = transferred / measured

    print('-' * 88, flush=True)
    print(
        f'RESULT workers={sorted(str(v) for v in observed_workers)} '
        f'avg={average / MB:.2f} MB/s '
        f'transferred={transferred / MB:.1f} MB '
        f'elapsed={measured:.1f}s '
        f'proxy_changed={"YES" if proxy_changed else "NO"}',
        flush=True,
    )
    if proxy_changed:
        print('WARNING: proxy changed during the sample; do not use this run for strict A/B comparison.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        raise SystemExit(f'benchmark failed: {exc}')
