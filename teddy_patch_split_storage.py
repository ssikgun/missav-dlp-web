from pathlib import Path


GENERIC = Path('teddy_generic.py')
ENTRYPOINT = Path('teddy_entrypoint.py')
BOOTSTRAP = Path('teddy_bootstrap.py')


def replace_once(path, old, new, label):
    text = path.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'split storage patch failed: {label}: expected 1 match, got {count}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')


def replace_function(path, function_name, next_function_name, replacement):
    text = path.read_text(encoding='utf-8')
    start_marker = f'def {function_name}('
    end_marker = f'def {next_function_name}('
    start = text.find(start_marker)
    if start < 0:
        raise SystemExit(f'split storage patch failed: {function_name} start not found')
    end = text.find(end_marker, start)
    if end < 0:
        raise SystemExit(f'split storage patch failed: {next_function_name} boundary not found')
    path.write_text(text[:start] + replacement.rstrip() + '\n\n\n' + text[end:], encoding='utf-8')


def patch_generic():
    replace_once(
        GENERIC,
        """def _task_temp_dir(core, task_id):\n    return os.path.join(core.DOWNLOAD_DIR, f'.{task_id}.ytdlp')\n""",
        """def _task_temp_dir(core, task_id):\n    return os.path.join(core.DOWNLOAD_DIR, f'.{task_id}.ytdlp')\n\n\ndef _task_home_dir(core, task_id):\n    return os.path.join(core.DOWNLOAD_DIR, f'.{task_id}.ytdlp-home')\n""",
        'generic per-task home helper',
    )

    replace_once(
        GENERIC,
        """    temp_dir = _task_temp_dir(core, task_id)\n    os.makedirs(temp_dir, exist_ok=True)\n    site_key, site_dir = teddy_storage.ensure_site_dir(core, url, custom=False)\n    last_filename = {'path': ''}\n""",
        """    temp_dir = _task_temp_dir(core, task_id)\n    home_dir = _task_home_dir(core, task_id)\n    os.makedirs(temp_dir, exist_ok=True)\n    os.makedirs(home_dir, exist_ok=True)\n    site_key = teddy_storage.site_key_for_url(url, custom=False)\n    last_filename = {'path': ''}\n""",
        'generic local task directories',
    )

    replace_once(
        GENERIC,
        """        'paths': {\n            'home': site_dir,\n            'temp': temp_dir,\n        },\n""",
        """        'paths': {\n            # Keep every in-progress/finalized yt-dlp artifact on local NVMe.\n            # The bootstrap publishes completed outputs to TEDDY_FINAL_DIR only\n            # after yt-dlp postprocessing has fully finished.\n            'home': home_dir,\n            'temp': temp_dir,\n        },\n""",
        'generic local yt-dlp home',
    )

    replace_once(
        GENERIC,
        "final_path = _find_final_path(core, ydl, info, site_dir)",
        "final_path = _find_final_path(core, ydl, info, home_dir)",
        'generic final path local home',
    )

    old_final = """        final_size = os.path.getsize(final_path)\n        task['status'] = '완료'\n        task['progress'] = '100%'\n        task['speed_bps'] = 0\n        task['filename'] = teddy_storage.relative_public_path(core, final_path)\n        task['filesize'] = final_size\n        task['downloaded_bytes'] = final_size\n        task['total_bytes_estimate'] = final_size\n        task['engine'] = 'yt-dlp'\n        task['storage_folder'] = site_key\n        task['network_mode'] = network_mode\n        task['yt_dlp_options'] = ytdlp_options\n        task.pop('last_error_detail', None)\n        _maybe_save(core, task_id, force=True)\n        shutil.rmtree(temp_dir, ignore_errors=True)\n        print(f\"[완료][yt-dlp][{route_label}] {task['filename']}\", flush=True)\n        return {'status': 'complete'}\n"""
    new_final = """        outputs = []\n        try:\n            for entry in os.scandir(home_dir):\n                if not entry.is_file():\n                    continue\n                name = entry.name\n                if name.endswith(('.part', '.ytdl', '.tmp')) or '.part-Frag' in name:\n                    continue\n                outputs.append(entry.path)\n        except OSError:\n            outputs = []\n        if final_path not in outputs:\n            outputs.append(final_path)\n\n        main_rel = teddy_storage.relative_work_path(core, final_path)\n        local_paths = []\n        for path in outputs:\n            try:\n                relative = teddy_storage.relative_work_path(core, path)\n            except teddy_storage.PublishError:\n                continue\n            if relative not in local_paths:\n                local_paths.append(relative)\n        local_paths = [path for path in local_paths if path != main_rel] + [main_rel]\n\n        final_size = os.path.getsize(final_path)\n        # 99% remains non-terminal until every completed output (including subtitle\n        # sidecars) is atomically published to final storage by the bootstrap.\n        task['status'] = '다운로드 중'\n        task['progress'] = '99%'\n        task['speed_bps'] = 0\n        task['filename'] = os.path.basename(final_path)\n        task['filesize'] = final_size\n        task['downloaded_bytes'] = final_size\n        task['total_bytes_estimate'] = final_size\n        task['engine'] = 'yt-dlp'\n        task['storage_folder'] = site_key\n        task['network_mode'] = network_mode\n        task['yt_dlp_options'] = ytdlp_options\n        task['local_result_path'] = main_rel\n        task['local_result_paths'] = local_paths\n        task.pop('last_error_detail', None)\n        _maybe_save(core, task_id, force=True)\n        shutil.rmtree(temp_dir, ignore_errors=True)\n        print(f\"[로컬 완료][yt-dlp][{route_label}] {main_rel} -> publish pending\", flush=True)\n        return {'status': 'local-complete'}\n"""
    replace_once(GENERIC, old_final, new_final, 'generic defer completion until publish')

    replace_once(
        GENERIC,
        """        if task and not active:\n            shutil.rmtree(_task_temp_dir(core, task_id), ignore_errors=True)\n        return original_delete(task_id)\n""",
        """        if task and not active:\n            shutil.rmtree(_task_temp_dir(core, task_id), ignore_errors=True)\n            shutil.rmtree(_task_home_dir(core, task_id), ignore_errors=True)\n        return original_delete(task_id)\n""",
        'generic delete local task directories',
    )


def patch_entrypoint():
    old_success = """        out_name = os.path.basename(final_path)\n        core.tasks[task_id]['status'] = '완료'\n        core.tasks[task_id]['progress'] = '100%'\n        core.tasks[task_id]['speed_bps'] = 0\n        core.tasks[task_id]['filename'] = out_name\n        try:\n            final_size = os.path.getsize(final_path)\n            core.tasks[task_id]['filesize'] = final_size\n            core.tasks[task_id]['downloaded_bytes'] = final_size\n            core.tasks[task_id]['total_bytes_estimate'] = final_size\n        except OSError:\n            pass\n        core.save_tasks()\n        print(f'[완료] {out_name}', flush=True)\n"""
    new_success = """        out_name = os.path.basename(final_path)\n        task = core.tasks[task_id]\n        task['status'] = '다운로드 중'\n        task['progress'] = '99%'\n        task['speed_bps'] = 0\n        task['filename'] = out_name\n        task['local_result_path'] = teddy_storage.relative_work_path(core, final_path)\n        task['local_result_paths'] = [task['local_result_path']]\n        try:\n            final_size = os.path.getsize(final_path)\n            task['filesize'] = final_size\n            task['downloaded_bytes'] = final_size\n            task['total_bytes_estimate'] = final_size\n        except OSError:\n            pass\n        core.save_tasks()\n        print(f\"[로컬 완료][custom-hls] {task['local_result_path']} -> publish pending\", flush=True)\n        return {'status': 'local-complete'}\n"""
    replace_once(ENTRYPOINT, old_success, new_success, 'custom HLS defer completion until publish')

    replace_once(
        ENTRYPOINT,
        "import teddy_hls_transport\n",
        "import teddy_hls_transport\nimport teddy_storage\n",
        'custom HLS storage import',
    )


def patch_bootstrap():
    publish_helper = r'''def _publish_pending_result(task_id):
    try:
        published = teddy_storage.publish_pending_task(core, task_id)
        task = core.tasks.get(task_id) or {}
        print(
            f"[Storage] 완료 파일 게시 성공: {task.get('filename') or published}",
            flush=True,
        )
        return {'status': 'complete'}
    except teddy_storage.PublishError as exc:
        return teddy_storage.mark_publish_error(core, task_id, exc)'''
    replace_function(
        BOOTSTRAP,
        '_move_custom_result_to_site_folder',
        '_custom_result',
        publish_helper,
    )

    replace_once(
        BOOTSTRAP,
        """def _run_engine_once(task_id, url, custom, mode):\n    if mode == 'proxy' and not teddy_proxy_pool.ensure_ready(core, wait_seconds=35):\n""",
        """def _run_engine_once(task_id, url, custom, mode):\n    # A previous run may have completed all local work but failed while publishing\n    # to NAS. Retry the pending publish before touching the network again.\n    if teddy_storage.has_pending_result(core, task_id):\n        return _publish_pending_result(task_id)\n\n    if mode == 'proxy' and not teddy_proxy_pool.ensure_ready(core, wait_seconds=35):\n""",
        'publish recovery before network',
    )

    old_custom = """    if custom:\n        with teddy_routing.request_route(mode):\n            _custom_download_video(task_id, url)\n        result = _custom_result(task_id)\n        if result.get('status') == 'complete':\n            _move_custom_result_to_site_folder(task_id, url)\n        return result\n\n    return teddy_generic.download_generic(\n        core,\n        reliability,\n        task_id,\n        url,\n        network_mode=mode,\n    )\n"""
    new_custom = """    if custom:\n        with teddy_routing.request_route(mode):\n            _custom_download_video(task_id, url)\n        if teddy_storage.has_pending_result(core, task_id):\n            return _publish_pending_result(task_id)\n        return _custom_result(task_id)\n\n    result = teddy_generic.download_generic(\n        core,\n        reliability,\n        task_id,\n        url,\n        network_mode=mode,\n    )\n    if result.get('status') == 'local-complete' or teddy_storage.has_pending_result(core, task_id):\n        return _publish_pending_result(task_id)\n    return result\n"""
    replace_once(BOOTSTRAP, old_custom, new_custom, 'publish both engines after local completion')

    replace_once(
        BOOTSTRAP,
        """        if status != 'error':\n            return\n\n        error_message = result.get('error') or ''\n""",
        """        if status != 'error':\n            return\n        if result.get('error_kind') == 'storage':\n            # Storage failures must never trigger Direct/Proxy/VPN route fallback.\n            # local_result_path is intentionally retained for publish-only retry.\n            return\n\n        error_message = result.get('error') or ''\n""",
        'storage failures never route fallback',
    )

    replace_once(
        BOOTSTRAP,
        "print(f'Download directory: {core.DOWNLOAD_DIR}')",
        "print(f'Work directory: {core.DOWNLOAD_DIR}')\n    print(f'Final directory: {teddy_storage.public_root(core)}')",
        'startup split storage paths',
    )


def main():
    patch_generic()
    patch_entrypoint()
    patch_bootstrap()
    print('split local-work / final-storage runtime patch: OK')


if __name__ == '__main__':
    main()
