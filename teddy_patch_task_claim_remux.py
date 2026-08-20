from pathlib import Path

ENTRYPOINT = Path('teddy_entrypoint.py')
BOOTSTRAP = Path('teddy_bootstrap.py')


def replace_once(path, old, new, label):
    text = path.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one patch anchor, found {count}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')


def main():
    replace_once(
        ENTRYPOINT,
        """    print('[ffmpeg] mp4 리먹스 중...', flush=True)\n    proc = subprocess.run(\n        ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0',\n         '-i', list_path, '-c', 'copy', out_path],\n        capture_output=True,\n        text=True,\n    )\n    if proc.returncode == 0 and os.path.exists(out_path):\n        shutil.rmtree(parts_dir, ignore_errors=True)\n        return out_path\n    print(\n        f'[ffmpeg] concat 실패(코드 {proc.returncode}) → ts로 저장: '\n        f'{(proc.stderr or \"\")[:300]}',\n        flush=True,\n    )\n    ts_out = (out_path[:-4] if out_path.endswith('.mp4') else out_path) + '.ts'\n    with open(ts_out, 'wb') as output_file:\n        for index in range(total):\n            with open(seg_path(index), 'rb') as segment_file:\n                output_file.write(segment_file.read())\n    shutil.rmtree(parts_dir, ignore_errors=True)\n    return ts_out\n""",
        """    print('[ffmpeg] mp4 리먹스 중...', flush=True)\n    remux_tmp = os.path.join(parts_dir, 'remux-output.mp4')\n    try:\n        if os.path.exists(remux_tmp):\n            os.remove(remux_tmp)\n    except OSError:\n        pass\n    proc = subprocess.run(\n        ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0',\n         '-i', list_path, '-c', 'copy', remux_tmp],\n        capture_output=True,\n        text=True,\n    )\n    if proc.returncode == 0 and os.path.isfile(remux_tmp) and os.path.getsize(remux_tmp) > 0:\n        os.replace(remux_tmp, out_path)\n        shutil.rmtree(parts_dir, ignore_errors=True)\n        return out_path\n\n    if proc.returncode == 0:\n        detail = 'ffmpeg는 성공을 반환했지만 임시 MP4 결과를 확인하지 못했습니다.'\n    else:\n        detail = (proc.stderr or '')[:300]\n    print(\n        f'[ffmpeg] mp4 리먹스 실패(코드 {proc.returncode}) → ts로 저장: {detail}',\n        flush=True,\n    )\n    try:\n        if os.path.exists(remux_tmp):\n            os.remove(remux_tmp)\n    except OSError:\n        pass\n    ts_out = (out_path[:-4] if out_path.endswith('.mp4') else out_path) + '.ts'\n    with open(ts_out, 'wb') as output_file:\n        for index in range(total):\n            with open(seg_path(index), 'rb') as segment_file:\n                output_file.write(segment_file.read())\n    shutil.rmtree(parts_dir, ignore_errors=True)\n    return ts_out\n""",
        'atomic remux output',
    )

    replace_once(
        BOOTSTRAP,
        "import time\n\nimport teddy_entrypoint as reliability\n",
        "import time\nimport threading\n\nimport teddy_entrypoint as reliability\n",
        'task claim threading import',
    )

    replace_once(
        BOOTSTRAP,
        """reliability._download_video = _dispatch_download\ncore.download_video = _dispatch_download\nteddy_generic.install_delete_cleanup(core)\n""",
        """_task_claim_lock = threading.Lock()\n_claimed_tasks = set()\n\n\ndef _dispatch_download_guarded(task_id, url):\n    with _task_claim_lock:\n        if task_id in _claimed_tasks:\n            print(f'[Queue] 동일 task 중복 실행 차단: {task_id}', flush=True)\n            return\n        _claimed_tasks.add(task_id)\n    try:\n        return _dispatch_download(task_id, url)\n    finally:\n        with _task_claim_lock:\n            _claimed_tasks.discard(task_id)\n\n\nreliability._download_video = _dispatch_download_guarded\ncore.download_video = _dispatch_download_guarded\nteddy_generic.install_delete_cleanup(core)\n""",
        'single execution claim',
    )

    print('task claim + atomic remux runtime patch: OK')


if __name__ == '__main__':
    main()
