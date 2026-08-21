from pathlib import Path


ENTRYPOINT = Path('teddy_entrypoint.py')


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'HLS pool-size patch: {label}: expected one anchor, found {count}')
    return text.replace(old, new, 1)


def main():
    text = ENTRYPOINT.read_text(encoding='utf-8')

    text = replace_once(
        text,
        "    transport_mode = teddy_hls_transport.transport_mode_for_task(core, task_id, core.settings)\n",
        "    transport_mode = teddy_hls_transport.transport_mode_for_task(core, task_id, core.settings)\n"
        "    pool_clients = teddy_hls_transport.pool_clients_from_settings(core.settings)\n"
        "    http_version = teddy_hls_transport.http_version_from_settings(core.settings)\n",
        'capture async pool size and HTTP version',
    )

    text = replace_once(
        text,
        "        f'· continuous {worker_count} workers · transport={transport_mode} · write={write_mode}',\n",
        "        f'· continuous {worker_count} workers · transport={transport_mode} '\n"
        "        f'· pool={pool_clients} · http={http_version} · write={write_mode}',\n",
        'runtime log pool size and HTTP version',
    )

    text = replace_once(
        text,
        "        core.tasks[task_id]['hls_transport_mode'] = transport_mode\n",
        "        core.tasks[task_id]['hls_transport_mode'] = transport_mode\n"
        "        core.tasks[task_id]['hls_pool_clients'] = pool_clients\n"
        "        core.tasks[task_id]['hls_http_version'] = http_version\n"
        "        core.tasks[task_id]['hls_http_version_actual'] = '?'\n",
        'persist task pool size and HTTP version',
    )

    text = replace_once(
        text,
        "            worker_count=worker_count,\n",
        "            worker_count=pool_clients,\n",
        'pass pool size to transport max_clients compatibility argument',
    )

    ENTRYPOINT.write_text(text, encoding='utf-8')
    print('configurable HLS async pool-size + HTTP-version runtime patch: OK')


if __name__ == '__main__':
    main()
