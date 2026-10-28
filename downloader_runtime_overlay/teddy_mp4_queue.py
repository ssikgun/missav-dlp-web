"""Durable, single-worker MP4 post-processing queue for Downloader.

Queue records are private files on the same work volume as the task data. Each
record is written atomically and remains present until the local MP4 result is
durably attached to the task. A process restart therefore replays only the
post-processing stage; it does not enqueue the network download again.
"""

import copy
import errno
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

import teddy_download_safety as safety


SCHEMA = 1
QUEUE_DIRNAME = '.teddy-mp4-queue'
QUEUE_LOCK_NAME = '.teddy-mp4-queue.lock'
POLL_SECONDS = 0.5
_CORE = None
_PUBLISH = None
_ORIGINAL_POST_PROCESS = None
_WAKE = threading.Event()
_WORKER = None
_INSTALL_LOCK = threading.Lock()
_POSTPROCESSOR_NAMES = {
    'FFmpegMergerPP',
    'FFmpegVideoRemuxerPP',
    'FFmpegVideoConvertorPP',
    'FFmpegExtractAudioPP',
    'FFmpegFixupM4aPP',
    'FFmpegFixupM3u8PP',
    'FFmpegFixupStretchedPP',
    'FFmpegFixupDuplicateMoovPP',
    'FFmpegFixupTimestampPP',
    'FFmpegFixupDurationPP',
}


def queue_dir(root):
    return os.path.join(os.path.realpath(os.fspath(root)), QUEUE_DIRNAME)


def _task_digest(task_id):
    return hashlib.sha256(str(task_id).encode('utf-8')).hexdigest()


def _job_path(root, task_id):
    return os.path.join(queue_dir(root), _task_digest(task_id) + '.json')


def _canonical_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def _seal_job(value):
    value = dict(value)
    value.pop('record_sha256', None)
    value['record_sha256'] = hashlib.sha256(_canonical_bytes(value)).hexdigest()
    return value


def _validate_job(value):
    if not isinstance(value, dict) or value.get('schema') != SCHEMA:
        raise safety.DownloadSafetyError('MP4 대기열 작업 schema가 잘못되었습니다.')
    recorded = str(value.get('record_sha256') or '')
    unsigned = dict(value)
    unsigned.pop('record_sha256', None)
    if not recorded or hashlib.sha256(_canonical_bytes(unsigned)).hexdigest() != recorded:
        raise safety.DownloadSafetyError('MP4 대기열 작업 SHA 검증에 실패했습니다.')
    if not isinstance(value.get('payload'), dict) or not value.get('task_id'):
        raise safety.DownloadSafetyError('MP4 대기열 작업 필드가 누락되었습니다.')
    return value


def _read_job(path):
    try:
        with open(path, 'r', encoding='utf-8') as source:
            return _validate_job(json.load(source))
    except (OSError, ValueError, TypeError) as exc:
        raise safety.DownloadSafetyError(f'MP4 대기열 작업을 읽을 수 없습니다: {path}: {exc}') from exc


def _write_job(root, task_id, job):
    directory = queue_dir(root)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    path = _job_path(root, task_id)
    if os.path.lexists(path):
        current = _read_job(path)
        if current.get('task_id') == str(task_id):
            if (current.get('kind') == job.get('kind')
                    and current.get('payload') == job.get('payload')):
                return path, False
            raise safety.OutputCollision(
                f'같은 task_id의 MP4 대기열 기록이 다른 입력/설정에 연결되어 있습니다: {task_id}'
            )
        raise safety.OutputCollision(f'MP4 대기열 경로 충돌: {path}')
    value = _seal_job(job)
    temp = f'{path}.{os.getpid()}.{time.time_ns()}.tmp'
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temp, path)
        except FileExistsError:
            current = _read_job(path)
            if current.get('task_id') != str(task_id):
                raise safety.OutputCollision(f'MP4 대기열 경로 충돌: {path}')
            return path, False
        directory_fd = os.open(directory, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return path, True
    except BaseException:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise
    finally:
        try:
            os.unlink(temp)
        except OSError:
            pass


def _write_job_guarded(root, task_id, job):
    """Commit output capacity and queue record under the shared volume lock."""
    guard = safety.InterProcessFileLock(safety.storage_lock_path(root))
    guard.acquire()
    try:
        usage = shutil.disk_usage(root)
        device = os.stat(root).st_dev
        own_digest = safety._reservation_paths(root, task_id)[3]
        active = safety._active_reserved_bytes(root, device, exclude_digest=own_digest)
        queued = pending_output_bytes(root, exclude_task_id=task_id)
        required = int(job.get('payload', {}).get('required_output_bytes') or 0)
        reserve = safety.reserve_bytes(usage.total)
        enough = usage.free >= active + queued + required + reserve
        path, created = _write_job(root, task_id, job)
        return path, created, enough
    finally:
        guard.release()


def _update_job(path, job, *, stage=None, output_record=None):
    value = dict(job)
    if stage is not None:
        value['stage'] = str(stage)
    if output_record is not None:
        value['output_record'] = dict(output_record)
        payload = dict(value.get('payload') or {})
        payload['required_output_bytes'] = 0
        value['payload'] = payload
    sealed = _seal_job(value)
    temp = f'{path}.{os.getpid()}.{time.time_ns()}.tmp'
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(sealed, stream, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        directory_fd = os.open(os.path.dirname(path), os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return sealed
    except BaseException:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise


def _delete_job(root, path):
    guard = safety.InterProcessFileLock(safety.storage_lock_path(root))
    guard.acquire()
    try:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
    finally:
        guard.release()


def _job_files(root):
    directory = queue_dir(root)
    if not os.path.isdir(directory):
        return []
    return [os.path.join(directory, name) for name in sorted(os.listdir(directory)) if name.endswith('.json')]


def pending_output_bytes(root, exclude_task_id=''):
    total = 0
    excluded = str(exclude_task_id or '')
    for path in _job_files(root):
        job = _read_job(path)
        if job.get('task_id') == excluded:
            continue
        if job.get('stage') in ('output_ready', 'publish_pending'):
            continue
        try:
            amount = int(job['payload']['required_output_bytes'])
        except (KeyError, TypeError, ValueError) as exc:
            raise safety.DownloadSafetyError(f'MP4 대기열 용량 예약이 손상되었습니다: {path}') from exc
        if amount < 0:
            raise safety.DownloadSafetyError(f'MP4 대기열 용량 예약이 음수입니다: {path}')
        total += amount
    return total


def _within(root, path):
    root = os.path.realpath(os.fspath(root))
    path = os.path.abspath(os.fspath(path))
    try:
        return os.path.commonpath([root, path]) == root
    except ValueError:
        return False


def _file_record(root, path):
    absolute = os.path.abspath(os.fspath(path))
    if not _within(root, absolute) or os.path.islink(absolute) or not os.path.isfile(absolute):
        raise safety.DownloadSafetyError(f'MP4 입력이 안전한 일반 파일이 아닙니다: {absolute}')
    return {
        'path': os.path.relpath(absolute, root),
        'size': os.path.getsize(absolute),
        'sha256': safety.sha256_file(absolute),
    }


def _verify_files(root, records):
    if not isinstance(records, list) or not records:
        raise safety.DownloadSafetyError('MP4 입력 파일 기록이 없습니다.')
    checked = set()
    for record in records:
        if not isinstance(record, dict):
            raise safety.DownloadSafetyError('MP4 입력 파일 기록 구조가 잘못되었습니다.')
        relative = str(record.get('path') or '')
        if not relative or os.path.isabs(relative) or relative in ('.', '..'):
            raise safety.DownloadSafetyError('MP4 입력 파일 경로가 잘못되었습니다.')
        path = os.path.abspath(os.path.join(root, relative))
        if not _within(root, path) or path in checked or os.path.islink(path) or not os.path.isfile(path):
            raise safety.DownloadSafetyError(f'MP4 입력 파일이 없거나 중복/비안전 경로입니다: {relative}')
        checked.add(path)
        if os.path.getsize(path) != int(record.get('size', -1)) or safety.sha256_file(path) != record.get('sha256'):
            raise safety.DownloadSafetyError(f'MP4 입력 SHA/크기가 대기열 기록과 다릅니다: {relative}')


def _verified_ytdlp_inputs(root, task_id, records):
    """Verify yt-dlp sources before/after its temp-to-home move."""
    if not isinstance(records, list) or not records:
        raise safety.DownloadSafetyError('yt-dlp MP4 입력 파일 기록이 없습니다.')
    root = os.path.realpath(root)
    temp_dir = os.path.realpath(os.path.join(root, f'.{task_id}.ytdlp'))
    home_dir = os.path.realpath(os.path.join(root, f'.{task_id}.ytdlp-home'))
    resolved = []
    checked = set()
    for record in records:
        if not isinstance(record, dict):
            raise safety.DownloadSafetyError('yt-dlp MP4 입력 파일 기록 구조가 잘못되었습니다.')
        relative = str(record.get('path') or '')
        if not relative or os.path.isabs(relative) or relative in ('.', '..'):
            raise safety.DownloadSafetyError('yt-dlp MP4 입력 경로가 잘못되었습니다.')
        original = os.path.abspath(os.path.join(root, relative))
        candidates = [original]
        try:
            if os.path.commonpath([temp_dir, original]) == temp_dir:
                candidates.append(os.path.join(home_dir, os.path.basename(original)))
        except ValueError:
            pass
        verified = None
        for path in candidates:
            if (not _within(root, path) or path in checked or os.path.islink(path)
                    or not os.path.isfile(path)):
                continue
            if (os.path.getsize(path) == int(record.get('size', -1))
                    and safety.sha256_file(path) == record.get('sha256')):
                verified = path
                break
        if verified is None:
            raise safety.DownloadSafetyError(
                f'yt-dlp 원본 입력이 없거나 SHA가 달라 보존/재개를 중단했습니다: {relative}'
            )
        checked.add(verified)
        resolved.append(verified)
    return resolved


def _filter_ytdlp_info(info):
    """Keep fields used by yt-dlp PPs while dropping volatile URLs and credentials."""
    clean = copy.deepcopy({key: value for key, value in info.items() if key != '__postprocessors'})
    clean.pop('formats', None)
    clean.pop('thumbnails', None)
    clean.pop('requested_subtitles', None)
    requested = clean.get('requested_formats')
    if isinstance(requested, list):
        keep = {
            'format_id', 'format', 'ext', 'protocol', 'vcodec', 'acodec', 'filepath',
            'filesize', 'filesize_approx', 'container', 'language', 'format_note',
            'width', 'height', 'fps', 'audio_channels', 'sample_rate', 'tbr',
        }
        clean['requested_formats'] = [
            {key: value for key, value in item.items() if key in keep}
            for item in requested if isinstance(item, dict)
        ]
    for key in ('url', 'webpage_url', 'original_url', 'manifest_url', 'http_headers', 'cookies', 'fragments', 'fragment_base_url'):
        clean.pop(key, None)
    return clean


def _postprocessor_names(info):
    objects = info.get('__postprocessors') or []
    names = []
    for pp in objects:
        name = pp.__class__.__name__
        if name not in _POSTPROCESSOR_NAMES or not pp.__class__.__module__.startswith('yt_dlp.postprocessor'):
            raise safety.DownloadSafetyError(f'재시작 후 복원할 수 없는 yt-dlp 후처리기가 있습니다: {name}')
        names.append(name)
    return names


def _is_mp4_job(ydl, filename, info):
    if str(info.get('ext') or '').lower() == 'mp4':
        return True
    if os.path.splitext(str(filename))[1].lower() == '.mp4':
        return True
    if str(ydl.params.get('merge_output_format') or '').lower() == 'mp4':
        return True
    for spec in ydl.params.get('postprocessors') or []:
        if not isinstance(spec, dict):
            continue
        if spec.get('key') in ('FFmpegVideoRemuxer', 'FFmpegVideoConvertor') and str(
            spec.get('preferedformat') or spec.get('preferredformat') or ''
        ).lower() == 'mp4':
            return True
    return False


def enqueue_ytdlp(core, task_id, filename, info, files_to_move, ydl):
    root = os.path.realpath(core.DOWNLOAD_DIR)
    if not _is_mp4_job(ydl, filename, info):
        return False
    task = core.tasks.get(task_id)
    if not task or task.get('status') == '취소됨':
        raise core.DownloadCancelled()
    if task.get('status') in ('일시정지 요청 중', '일시정지'):
        raise safety.TaskPauseRequested('MP4 변환 대기 전에 일시정지 요청')
    if not _within(root, filename):
        raise safety.DownloadSafetyError('yt-dlp 후처리 결과가 로컬 작업 경로 밖에 있습니다.')
    names = _postprocessor_names(info)
    info_copy = _filter_ytdlp_info(info)
    input_paths = []
    for value in info.get('__files_to_merge') or []:
        if value and value not in input_paths:
            input_paths.append(value)
    if not input_paths:
        input_paths.append(filename)
    records = [_file_record(root, path) for path in input_paths]
    filtered_info = _filter_ytdlp_info(info_copy)
    filtered_info['__files_to_move'] = dict(files_to_move or {})
    pp_payload = {
        'filename': os.path.relpath(os.path.abspath(filename), root),
        'info': filtered_info,
        'files_to_move': dict(files_to_move or {}),
        'additional_postprocessors': names,
        'yt_dlp_options': dict(task.get('yt_dlp_options') or {}),
        'filename_template': str(core.settings.get('filename_template') or '[%(id)s] %(title).60s.%(ext)s'),
        'network_mode': str(task.get('network_mode') or 'direct'),
        'input_files': records,
    }
    try:
        json.dumps(pp_payload, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise safety.DownloadSafetyError(f'yt-dlp MP4 대기열을 안전하게 저장할 수 없습니다: {exc}') from exc
    input_bytes = sum(int(row['size']) for row in records)
    configured_postprocessors = ydl.params.get('postprocessors') or []
    has_configured_mp4_stage = (
        bool(names or configured_postprocessors)
        or str(ydl.params.get('merge_output_format') or '').lower() == 'mp4'
    )
    output_bytes = safety.estimated_remux_output_bytes(input_bytes) if has_configured_mp4_stage else 0
    now = time.time_ns()
    payload = {
        'required_output_bytes': output_bytes,
        'input_bytes': input_bytes,
        'input_files': records,
        'ytdlp': pp_payload,
    }
    job = {
        'schema': SCHEMA,
        'task_id': str(task_id),
        'kind': 'ytdlp',
        'queued_ns': now,
        'attempt': 0,
        'payload': payload,
    }
    _path, created, enough_space = _write_job_guarded(root, task_id, job)
    with safety.task_state_guard():
        task = core.tasks.get(task_id)
        if not task or task.get('status') == '취소됨':
            raise core.DownloadCancelled()
        task['status'] = 'MP4 변환 대기' if enough_space else 'MP4 저장 대기'
        task['progress'] = '99%'
        task['speed_bps'] = 0
        task['mp4_stage'] = 'queued'
        task['mp4_queued_ns'] = now
        task['mp4_required_output_bytes'] = output_bytes
        task['mp4_queue_kind'] = 'ytdlp'
        core.save_tasks()
    _WAKE.set()
    return created


def enqueue_hls(core, task_id, root, parts_dir, list_path, out_path, plan_sha256, segment_count):
    root = os.path.realpath(os.fspath(root))
    parts_dir = os.path.realpath(os.fspath(parts_dir))
    if not _within(root, parts_dir) or not _within(root, out_path):
        raise safety.DownloadSafetyError('HLS MP4 대기열 경로가 작업 루트 밖에 있습니다.')
    task = core.tasks.get(task_id)
    if not task or task.get('status') == '취소됨':
        raise core.DownloadCancelled()
    if task.get('status') in ('일시정지 요청 중', '일시정지'):
        raise safety.TaskPauseRequested('HLS MP4 변환 대기 전에 일시정지 요청')
    manifest_path = os.path.join(parts_dir, 'resume-plan.json')
    try:
        with open(manifest_path, 'r', encoding='utf-8') as source:
            manifest = json.load(source)
    except (OSError, ValueError) as exc:
        raise safety.DownloadSafetyError(f'HLS 재개 manifest를 확인할 수 없습니다: {exc}') from exc
    if (manifest.get('schema') != 1 or manifest.get('task_id') != str(task_id)
            or manifest.get('plan_sha256') != str(plan_sha256)
            or manifest.get('segment_count') != int(segment_count)):
        raise safety.DownloadSafetyError('HLS MP4 대기열 source plan 결속 검증에 실패했습니다.')
    segments = []
    for index in range(int(segment_count)):
        path = os.path.join(parts_dir, f'{index:05d}.ts')
        segments.append(_file_record(root, path))
    filelist_record = _file_record(root, list_path)
    input_bytes = sum(int(row['size']) for row in segments)
    output_bytes = safety.estimated_remux_output_bytes(input_bytes)
    now = time.time_ns()
    payload = {
        'required_output_bytes': output_bytes,
        'input_bytes': input_bytes,
        'parts_dir': os.path.relpath(parts_dir, root),
        'list_path': os.path.relpath(os.path.abspath(list_path), root),
        'output_path': os.path.relpath(os.path.abspath(out_path), root),
        'plan_sha256': str(plan_sha256),
        'segment_count': int(segment_count),
        'manifest_sha256': safety.sha256_file(manifest_path),
        'filelist': filelist_record,
        'input_files': segments,
    }
    job = {'schema': SCHEMA, 'task_id': str(task_id), 'kind': 'hls', 'queued_ns': now,
           'attempt': 0, 'payload': payload}
    _path, created, enough_space = _write_job_guarded(root, task_id, job)
    with safety.task_state_guard():
        task = core.tasks.get(task_id)
        if not task or task.get('status') == '취소됨':
            raise core.DownloadCancelled()
        task['status'] = 'MP4 변환 대기' if enough_space else 'MP4 저장 대기'
        task['progress'] = '99%'
        task['speed_bps'] = 0
        task['mp4_stage'] = 'queued'
        task['mp4_queued_ns'] = now
        task['mp4_required_output_bytes'] = output_bytes
        task['mp4_queue_kind'] = 'hls'
        task['hls_parts_path'] = os.path.relpath(parts_dir, root)
        core.save_tasks()
    _WAKE.set()
    return created


def legacy_ts_retry_source(core, task_id):
    """Recognize a user-requested retry blocked only by its own legacy root TS.

    Old HLS jobs predate resume manifests, so never infer that their loose parts
    can be reused. Only the exact output path recorded by the original safety
    error may identify an already backed-up TS for a separate MP4-only job.
    """
    task = core.tasks.get(task_id)
    if not isinstance(task, dict):
        return None
    detail = str(task.get('last_error_detail') or '')
    prefix = '기존 완료 파일을 덮어쓰지 않습니다: '
    if (task.get('error_kind') != 'safety'
            or not str(task.get('status') or '').startswith('에러')
            or not detail.startswith(prefix)):
        return None
    root = os.path.realpath(core.DOWNLOAD_DIR)
    out_path = detail[len(prefix):]
    if (not os.path.isabs(out_path) or os.path.normpath(out_path) != out_path
            or os.path.dirname(out_path) != root or not out_path.endswith('.mp4')):
        raise safety.DownloadSafetyError('기존 MP4 충돌 경로가 안전하지 않아 재시도를 보류했습니다.')
    ts_path = out_path[:-4] + '.ts'
    if not os.path.lexists(ts_path):
        return None
    if (task.get('engine') != 'custom-hls' or os.path.lexists(out_path)
            or os.path.islink(ts_path) or not os.path.isfile(ts_path)
            or os.path.getsize(ts_path) <= 0 or task.get('local_result_path')):
        raise safety.DownloadSafetyError('기존 TS를 작업에 안전하게 연결할 수 없어 재시도를 보류했습니다.')
    return ts_path


def enqueue_legacy_ts(core, task_id, ts_path):
    """Queue the immutable local TS as one MP4 worker job; preserve all parts."""
    expected = legacy_ts_retry_source(core, task_id)
    if not expected or os.path.abspath(ts_path) != expected:
        raise safety.DownloadSafetyError('TS 전용 MP4 재시도 대상이 변경되어 등록을 차단했습니다.')
    root = os.path.realpath(core.DOWNLOAD_DIR)
    out_path = os.path.splitext(expected)[0] + '.mp4'
    if os.path.lexists(out_path):
        raise safety.OutputCollision(f'기존 완료 파일을 덮어쓰지 않습니다: {out_path}')
    input_record = _file_record(root, expected)
    output_bytes = safety.estimated_remux_output_bytes(input_record['size'])
    now = time.time_ns()
    job = {
        'schema': SCHEMA, 'task_id': str(task_id), 'kind': 'legacy_ts',
        'queued_ns': now, 'attempt': 0,
        'payload': {
            'required_output_bytes': output_bytes,
            'input_bytes': input_record['size'],
            'input_files': [input_record],
            'output_path': os.path.relpath(out_path, root),
        },
    }
    _path, created, enough_space = _write_job_guarded(root, task_id, job)
    with safety.task_state_guard():
        task = core.tasks.get(task_id)
        if not task or task.get('status') == '취소됨':
            raise core.DownloadCancelled()
        task['status'] = 'MP4 변환 대기' if enough_space else 'MP4 저장 대기'
        task['progress'] = '99%'
        task['speed_bps'] = 0
        task['mp4_stage'] = 'queued'
        task['mp4_queued_ns'] = now
        task['mp4_required_output_bytes'] = output_bytes
        task['mp4_queue_kind'] = 'legacy_ts'
        task['teddy_legacy_ts_preserve_source'] = input_record['path']
        core.save_tasks()
    _WAKE.set()
    return created


class MP4RecoveryHeld(safety.DownloadSafetyError):
    """A failure/ambiguous record must remain untouched until explicit retry."""


def owns_task_record(root, task_id, task):
    """Even an untrusted queue entry prevents fallback to network auto-retry."""
    return safety.has_mp4_record(root, task_id, task)


def _require_recoverable(core, task_id, *, allow_paused=False):
    task = core.tasks.get(task_id)
    if not task or task.get('status') == '취소됨':
        raise core.DownloadCancelled()
    reason = safety.mp4_recovery_hold_reason(task)
    if allow_paused and task.get('status') in ('일시정지', '일시정지 요청 중'):
        # A completed remux may still be journaled before respecting a pause.
        copy_task = dict(task, status='MP4 변환 대기')
        reason = safety.mp4_recovery_hold_reason(copy_task)
    if reason:
        raise MP4RecoveryHeld('MP4 자동 재개 보류: ' + reason)
    return task


def _check_task(core, task_id):
    task = core.tasks.get(task_id)
    if not task or task.get('status') == '취소됨':
        raise core.DownloadCancelled()
    if task.get('status') in ('일시정지 요청 중', '일시정지'):
        raise safety.TaskPauseRequested('MP4 변환 일시정지 요청')
    _require_recoverable(core, task_id)


def _queue_lock(root):
    path = os.path.join(os.path.realpath(root), QUEUE_LOCK_NAME)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        return fd
    except BaseException:
        os.close(fd)
        raise


def _release_queue_lock(fd):
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _eligible_job(core, root):
    rows = []
    for path in _job_files(root):
        job = _read_job(path)
        task_id = str(job['task_id'])
        task = core.tasks.get(task_id)
        if not task:
            continue
        if safety.mp4_recovery_hold_reason(task):
            continue
        if (job.get('kind') not in ('hls', 'ytdlp', 'legacy_ts')
                or task.get('mp4_queue_kind') not in (None, '', job.get('kind'))):
            continue
        stage = job.get('stage') or task.get('mp4_stage') or 'queued'
        if stage not in ('queued', 'running', 'output_ready', 'publish_pending'):
            continue
        if stage in ('queued', 'running'):
            usage = shutil.disk_usage(root)
            device = os.stat(root).st_dev
            active = safety._active_reserved_bytes(root, device)
            queued = pending_output_bytes(root, exclude_task_id=task_id)
            required = int(job['payload'].get('required_output_bytes') or 0)
            if usage.free < active + queued + required + safety.reserve_bytes(usage.total):
                continue
        rows.append((int(job.get('queued_ns') or 0), path, job, task))
    rows.sort(key=lambda row: (row[0], row[1]))
    return rows


def _set_error(core, task_id, exc):
    with safety.task_state_guard():
        task = core.tasks.get(task_id)
        if not task or safety.mp4_recovery_hold_reason(task):
            return
        kind = 'storage' if safety.is_storage_error(exc) else 'mp4'
        task['status'] = ('MP4 저장 대기' if kind == 'storage' else f'에러: MP4 처리 실패: {str(exc)[:80]}')
        task['mp4_stage'] = 'queued' if kind == 'storage' else 'failed'
        task['error_kind'] = kind
        task['last_error_detail'] = str(exc)[:1000]
        task['speed_bps'] = 0
        core.save_tasks()


def _set_paused(core, task_id):
    with safety.task_state_guard():
        task = core.tasks.get(task_id)
        if (task and task.get('status') != '취소됨'
                and not safety.mp4_recovery_hold_reason(dict(task, status='MP4 변환 대기'))):
            task['status'] = '일시정지'
            task['mp4_stage'] = 'queued'
            task['speed_bps'] = 0
            core.save_tasks()


def _input_bytes(records):
    return sum(int(row['size']) for row in records)


def _hls_manifest_check(root, job):
    payload = job['payload']
    parts = os.path.abspath(os.path.join(root, payload['parts_dir']))
    manifest_path = os.path.join(parts, 'resume-plan.json')
    if not _within(root, parts) or os.path.islink(parts) or os.path.islink(manifest_path):
        raise safety.DownloadSafetyError('HLS 원본 경로가 안전하지 않아 조각을 보존했습니다.')
    with open(manifest_path, 'r', encoding='utf-8') as source:
        manifest = json.load(source)
    if (manifest.get('task_id') != str(job['task_id'])
            or manifest.get('plan_sha256') != payload.get('plan_sha256')
            or manifest.get('segment_count') != payload.get('segment_count')
            or safety.sha256_file(manifest_path) != payload.get('manifest_sha256')):
        raise safety.DownloadSafetyError('HLS 재개 manifest가 대기열 기록과 다릅니다; 기존 조각을 보존했습니다.')
    _verify_files(root, payload.get('input_files'))
    _verify_files(root, [payload.get('filelist')])


def _process_hls(core, job):
    root = os.path.realpath(core.DOWNLOAD_DIR)
    payload = job['payload']
    task_id = str(job['task_id'])
    _check_task(core, task_id)
    _hls_manifest_check(root, job)
    required = int(payload['required_output_bytes'])
    out_path = os.path.abspath(os.path.join(root, payload['output_path']))
    parts = os.path.abspath(os.path.join(root, payload['parts_dir']))
    list_path = os.path.abspath(os.path.join(root, payload['list_path']))
    if not _within(root, out_path) or not _within(root, list_path):
        raise safety.DownloadSafetyError('HLS MP4 출력 경로가 작업 루트 밖에 있습니다.')
    if os.path.lexists(out_path):
        raise safety.OutputCollision(f'기존 완료 파일을 덮어쓰지 않습니다: {out_path}')
    temp = os.path.join(parts, f'remux-{os.getpid()}-{time.time_ns()}.mp4')
    remux_error = None
    with safety.task_context(task_id, input_records=payload['input_files']):
        with safety.RemuxTransaction(root, output_path=root, required_output_bytes=required,
                                     cancel_check=lambda: _check_task(core, task_id)) as remux_transaction:
            recovered = safety.recover_mp4_attempts(
                root, task_id, payload['input_files'], allow_complete=True,
            )
            if recovered:
                with safety.task_state_guard():
                    _check_task(core, task_id)
                    output = os.path.abspath(os.path.join(root, recovered['path']))
                    _hls_manifest_check(root, job)
                    _update_job(_job_path(root, task_id), job, stage='output_ready', output_record=recovered)
                    safety.finalize_mp4_attempts(
                        root, task_id, payload['input_files'], preserve_paths=[output],
                    )
                    return output
            input_paths = [os.path.join(root, row['path']) for row in payload['input_files']]
            attempt = safety.begin_mp4_attempt(
                root, task_id, input_paths, [temp], payload['input_files'],
            )
            stage_path = attempt['stage_map'][os.path.abspath(temp)]
            remux_transaction.set_output_paths([stage_path])
            try:
                proc = safety.run_process_interruptibly(
                    ['ffmpeg', '-n', '-loglevel', 'error', '-f', 'concat', '-safe', '0',
                     '-i', list_path, '-c', 'copy', stage_path],
                    cancel_check=lambda: _check_task(core, task_id),
                    progress_check=remux_transaction.refresh_output_reservation,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                )
            except OSError as exc:
                safety.recover_mp4_attempts(root, task_id, payload['input_files'])
                if safety.is_enospc(exc):
                    raise safety.StorageSpaceError(root, shutil.disk_usage(root).free,
                                                   int(payload['required_output_bytes']),
                                                   safety.reserve_bytes(shutil.disk_usage(root).total)) from exc
                raise
            if proc.returncode == 0 and os.path.isfile(stage_path) and os.path.getsize(stage_path) > 0:
                with safety.task_state_guard():
                    _check_task(core, task_id)
                    _hls_manifest_check(root, job)
                    _check_task(core, task_id)
                    safety.complete_mp4_attempt_outputs(root, attempt)
                    safety.update_mp4_attempt(attempt, 'ffmpeg_complete')
                    safety.commit_mp4_attempt_outputs(root, attempt)
                    output_record = _file_record(root, temp)
                    queue_path = _job_path(root, task_id)
                    _update_job(queue_path, job, stage='output_ready', output_record=output_record)
                    safety.finalize_mp4_attempts(root, task_id, payload['input_files'], preserve_paths=[temp])
                    return temp
            detail = (proc.stderr or '')[:500]
            safety.recover_mp4_attempts(root, task_id, payload['input_files'])
            if safety.is_enospc(detail):
                usage = shutil.disk_usage(root)
                raise safety.StorageSpaceError(root, usage.free, int(payload['required_output_bytes']),
                                               safety.reserve_bytes(usage.total))
            remux_error = detail or f'ffmpeg 종료 코드 {proc.returncode}'

    if remux_error:
        _check_task(core, task_id)
        ts_out = os.path.splitext(out_path)[0] + '.ts'
        if os.path.lexists(ts_out):
            raise safety.OutputCollision(f'기존 TS 파일을 덮어쓰지 않습니다: {ts_out}')
        ts_tmp = os.path.join(parts, f'fallback-{os.getpid()}-{time.time_ns()}.ts')
        try:
            with safety.StorageWriteTransaction(root, output_path=root,
                    required_bytes=_input_bytes(payload['input_files']),
                    cancel_check=lambda: _check_task(core, task_id)) as storage_write:
                with open(ts_tmp, 'xb') as output:
                    for record in payload['input_files']:
                        source = os.path.join(root, record['path'])
                        with open(source, 'rb') as inp:
                            while True:
                                chunk = inp.read(1024 * 1024)
                                if not chunk:
                                    break
                                written = output.write(chunk)
                                if written != len(chunk):
                                    raise OSError('TS fallback 임시 파일에 전체 데이터를 기록하지 못했습니다.')
                                storage_write.consume_written(written)
                        _check_task(core, task_id)
                    output.flush()
                    os.fsync(output.fileno())
            out_path = ts_tmp
        except BaseException:
            try:
                os.unlink(ts_tmp)
            except OSError:
                pass
            raise
    _hls_manifest_check(root, job)
    return out_path


def _process_legacy_ts(core, job):
    """Remux a verified legacy root TS under the existing global MP4 lock."""
    root = os.path.realpath(core.DOWNLOAD_DIR)
    task_id = str(job['task_id'])
    payload = job['payload']
    records = payload.get('input_files')
    if not isinstance(records, list) or len(records) != 1:
        raise safety.DownloadSafetyError('기존 TS 입력 증거가 잘못되었습니다.')
    _verify_files(root, records)
    source = os.path.abspath(os.path.join(root, records[0]['path']))
    output = os.path.abspath(os.path.join(root, payload['output_path']))
    if (os.path.dirname(source) != root or not source.endswith('.ts')
            or output != os.path.splitext(source)[0] + '.mp4'
            or os.path.dirname(output) != root or os.path.lexists(output)):
        raise safety.OutputCollision('기존 TS의 MP4 출력 경로를 안전하게 확정할 수 없습니다.')
    _check_task(core, task_id)
    temp = os.path.join(queue_dir(root), f'legacy-{_task_digest(task_id)}-{time.time_ns()}.mp4')
    required = int(payload['required_output_bytes'])
    with safety.task_context(task_id, input_records=records):
        with safety.RemuxTransaction(
            root, output_path=root, required_output_bytes=required,
            cancel_check=lambda: _check_task(core, task_id),
        ) as remux:
            recovered = safety.recover_mp4_attempts(
                root, task_id, records, allow_complete=True,
            )
            if recovered:
                _check_task(core, task_id)
                existing = os.path.abspath(os.path.join(root, recovered['path']))
                _update_job(_job_path(root, task_id), job,
                            stage='output_ready', output_record=recovered)
                safety.finalize_mp4_attempts(root, task_id, records,
                                             preserve_paths=[existing])
                return existing
            attempt = safety.begin_mp4_attempt(
                root, task_id, [source], [temp], records,
            )
            stage_path = attempt['stage_map'][os.path.abspath(temp)]
            remux.set_output_paths([stage_path])
            try:
                proc = safety.run_process_interruptibly(
                    ['ffmpeg', '-n', '-loglevel', 'error', '-i', source,
                     '-map', '0:v:0', '-map', '0:a?', '-c', 'copy',
                     '-movflags', '+faststart', stage_path],
                    cancel_check=lambda: _check_task(core, task_id),
                    progress_check=remux.refresh_output_reservation,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                )
            except OSError as exc:
                safety.recover_mp4_attempts(root, task_id, records)
                if safety.is_enospc(exc):
                    usage = shutil.disk_usage(root)
                    raise safety.StorageSpaceError(
                        root, usage.free, required, safety.reserve_bytes(usage.total),
                    ) from exc
                raise
            if proc.returncode != 0 or not os.path.isfile(stage_path) or os.path.getsize(stage_path) <= 0:
                safety.recover_mp4_attempts(root, task_id, records)
                detail = (proc.stderr or '')[:400] or f'ffmpeg 종료 코드 {proc.returncode}'
                if safety.is_enospc(detail):
                    usage = shutil.disk_usage(root)
                    raise safety.StorageSpaceError(
                        root, usage.free, required, safety.reserve_bytes(usage.total),
                    )
                raise safety.DownloadSafetyError('기존 TS MP4 변환 실패, 원본은 보존했습니다: ' + detail)
            _check_task(core, task_id)
            _verify_files(root, records)
            safety.complete_mp4_attempt_outputs(root, attempt)
            safety.update_mp4_attempt(attempt, 'ffmpeg_complete')
            safety.commit_mp4_attempt_outputs(root, attempt)
            output_record = _file_record(root, temp)
            _update_job(_job_path(root, task_id), job,
                        stage='output_ready', output_record=output_record)
            safety.finalize_mp4_attempts(root, task_id, records, preserve_paths=[temp])
            return temp


def _make_ytdlp(core, task_id, record):
    import yt_dlp
    import teddy_generic
    task = core.tasks.get(task_id) or {}
    ytdlp_options = record.get('yt_dlp_options') or task.get('yt_dlp_options') or {}
    home = os.path.join(core.DOWNLOAD_DIR, f'.{task_id}.ytdlp-home')
    temp = os.path.join(core.DOWNLOAD_DIR, f'.{task_id}.ytdlp')
    opts = {
        'quiet': True,
        'no_warnings': False,
        'noplaylist': True,
        'continuedl': True,
        'nopart': False,
        'keepvideo': True,
        'paths': {'home': home, 'temp': temp},
        'outtmpl': {'default': record.get('filename_template') or '[%(id)s] %(title).60s.%(ext)s'},
    }
    teddy_generic._apply_media_options(opts, ytdlp_options)
    return yt_dlp.YoutubeDL(opts)


def _rehydrate_additional_pps(ydl, names):
    from yt_dlp.postprocessor import ffmpeg as ffmpeg_module
    pps = []
    for name in names:
        if name not in _POSTPROCESSOR_NAMES:
            raise safety.DownloadSafetyError(f'yt-dlp 후처리기 복원 목록에 없는 class입니다: {name}')
        cls = getattr(ffmpeg_module, name, None)
        if cls is None:
            raise safety.DownloadSafetyError(f'설치된 yt-dlp에서 후처리기를 복원할 수 없습니다: {name}')
        pps.append(cls(ydl))
    return pps


def _process_ytdlp(core, job):
    root = os.path.realpath(core.DOWNLOAD_DIR)
    task_id = str(job['task_id'])
    payload = job['payload']
    record = payload['ytdlp']
    _check_task(core, task_id)
    input_paths = _verified_ytdlp_inputs(root, task_id, payload.get('input_files'))
    filename = os.path.abspath(os.path.join(root, record['filename']))
    if not _within(root, filename):
        raise safety.DownloadSafetyError('yt-dlp 후처리 경로가 작업 루트 밖에 있습니다.')
    if not os.path.isfile(filename):
        recorded_name = os.path.relpath(filename, root)
        matching = [path for row, path in zip(payload.get('input_files') or [], input_paths)
                    if row.get('path') == recorded_name]
        if len(matching) != 1:
            raise safety.DownloadSafetyError('재시작 후 yt-dlp 후처리 입력 경로를 안전하게 복원할 수 없습니다.')
        filename = matching[0]
    with _make_ytdlp(core, task_id, record) as ydl:
        info = record['info']
        info['__postprocessors'] = _rehydrate_additional_pps(ydl, record.get('additional_postprocessors') or [])
        with safety.task_context(task_id, input_records=payload.get('input_files')):
            _check_task(core, task_id)
            result = _ORIGINAL_POST_PROCESS(ydl, filename, info, record.get('files_to_move') or {})
            # Once yt-dlp has returned a complete local output, journal its SHA
            # before honoring a pause/cancel at the publication boundary.
            # _complete_job persists output_ready before _store_local_result
            # rechecks task state, so resume does not rerun the conversion.
    _verified_ytdlp_inputs(root, task_id, payload.get('input_files'))
    output = str(result.get('filepath') or info.get('filepath') or '')
    if not output or not _within(root, output) or os.path.islink(output) or not os.path.isfile(output):
        raise safety.DownloadSafetyError('yt-dlp MP4 후처리 결과를 검증할 수 없습니다.')
    _fsync_file(output)
    directory_fd = os.open(os.path.dirname(output) or root, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    output_record = _file_record(root, output)
    with safety.task_state_guard():
        _require_recoverable(core, task_id, allow_paused=True)
        _update_job(_job_path(root, task_id), job, stage='output_ready', output_record=output_record)
    return output


def _local_outputs(core, task_id, main_path, files_to_move=None, excluded_paths=None,
                   result_kind='ytdlp'):
    root = os.path.realpath(os.fspath(core.DOWNLOAD_DIR))
    main_path = os.path.abspath(os.fspath(main_path))
    if (not _within(root, main_path) or os.path.islink(main_path)
            or not os.path.isfile(main_path)):
        raise safety.DownloadSafetyError('후처리 결과가 안전한 작업 디렉터리의 일반 파일이 아닙니다.')
    excluded = {os.path.abspath(path) for path in (excluded_paths or [])}
    outputs = []
    if result_kind == 'ytdlp':
        home = os.path.abspath(os.path.join(root, f'.{task_id}.ytdlp-home'))
        if not _within(root, home) or os.path.islink(home):
            raise safety.DownloadSafetyError('yt-dlp 후처리 결과 폴더 경로가 안전하지 않습니다.')
        try:
            for entry in os.scandir(home):
                if not entry.is_file(follow_symlinks=False):
                    continue
                name = entry.name
                if name.endswith(('.part', '.ytdl', '.tmp')) or '.part-Frag' in name:
                    continue
                if name == '.teddy-storage-guard.lock':
                    continue
                if os.path.abspath(entry.path) in excluded:
                    continue
                outputs.append(entry.path)
        except OSError as exc:
            raise safety.DownloadSafetyError(f'후처리 결과 폴더를 읽을 수 없습니다: {exc}') from exc
    elif result_kind in ('hls', 'legacy_ts'):
        # HLS/legacy TS jobs publish only one verified output, never old inputs.
        # Do not infer publishable files from a directory owned by another engine.
        if files_to_move or excluded_paths:
            raise safety.DownloadSafetyError('HLS 후처리에 승인되지 않은 부가 결과 경로가 있습니다.')
    else:
        raise safety.DownloadSafetyError('알 수 없는 후처리 결과 종류입니다.')
    if main_path not in outputs:
        outputs.append(main_path)
    if result_kind == 'ytdlp':
        for path in (files_to_move or {}).values():
            if isinstance(path, str) and os.path.isfile(path) and path not in outputs:
                outputs.append(path)
    return outputs


def _store_local_result(core, task_id, final_path, files_to_move=None, excluded_paths=None,
                        result_kind='ytdlp'):
    import teddy_storage
    task = core.tasks.get(task_id)
    if not task:
        raise core.DownloadCancelled()
    if task.get('status') in ('일시정지 요청 중', '일시정지'):
        raise safety.TaskPauseRequested('MP4 결과 저장 직전 일시정지 요청')
    _require_recoverable(core, task_id)
    main_rel = teddy_storage.relative_work_path(core, final_path)
    local_paths = []
    for path in _local_outputs(core, task_id, final_path, files_to_move, excluded_paths,
                               result_kind=result_kind):
        try:
            rel = teddy_storage.relative_work_path(core, path)
        except teddy_storage.PublishError:
            continue
        if rel not in local_paths:
            local_paths.append(rel)
    local_paths = [path for path in local_paths if path != main_rel] + [main_rel]
    size = os.path.getsize(final_path)
    with safety.task_state_guard():
        task = core.tasks.get(task_id)
        if not task or task.get('status') == '취소됨':
            raise core.DownloadCancelled()
        if task.get('status') in ('일시정지 요청 중', '일시정지'):
            raise safety.TaskPauseRequested('MP4 결과 저장 직전 일시정지 요청')
        _require_recoverable(core, task_id)
        task['status'] = '다운로드 중'
        task['progress'] = '99%'
        task['speed_bps'] = 0
        task['filename'] = os.path.basename(final_path)
        task['filesize'] = size
        task['downloaded_bytes'] = size
        task['total_bytes_estimate'] = size
        task['local_result_path'] = main_rel
        task['local_result_paths'] = local_paths
        task['mp4_stage'] = 'publish_pending'
        task.pop('mp4_queue_kind', None)
        task.pop('mp4_required_output_bytes', None)
        core.save_tasks()


def _mark_running(core, task_id):
    with safety.task_state_guard():
        task = core.tasks.get(task_id)
        if not task or safety.mp4_recovery_hold_reason(task):
            return False
        task['status'] = 'MP4 변환 중'
        task['mp4_stage'] = 'running'
        task['speed_bps'] = 0
        core.save_tasks()
    return True


def _output_record(root, output_path):
    return _file_record(root, output_path)


def _fsync_file(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _verified_output_path(root, job):
    record = job.get('output_record')
    if not isinstance(record, dict):
        return ''
    _verify_files(root, [record])
    return os.path.abspath(os.path.join(root, record['path']))


def _materialize_hls_output(root, job, output_path, output_record):
    """Recoverably attach a verified staged remux to its no-clobber public name."""
    payload = job['payload']
    target = os.path.abspath(os.path.join(root, payload['output_path']))
    if str(job.get('output_kind') or '') == 'ts' or str(output_path).endswith('.ts'):
        target = os.path.splitext(target)[0] + '.ts'
    if not _within(root, target) or os.path.islink(target):
        raise safety.DownloadSafetyError('HLS 완료 출력 경로가 안전하지 않습니다.')

    if output_record.get('staging_path'):
        # A previous attempt already committed the target record. Remove only
        # the exact verified staging artifact left by a crash after that commit.
        _verify_files(root, [output_record])
        stage_rel = str(output_record['staging_path'])
        stage_path = os.path.abspath(os.path.join(root, stage_rel))
        if _within(root, stage_path) and os.path.isfile(stage_path) and not os.path.islink(stage_path):
            if safety.sha256_file(stage_path) != output_record.get('sha256'):
                raise safety.DownloadSafetyError('HLS 임시 결과가 기록된 SHA와 달라 보존했습니다.')
            os.unlink(stage_path)
        return os.path.abspath(os.path.join(root, output_record['path'])), output_record

    source = os.path.abspath(os.fspath(output_path))
    _verify_files(root, [output_record])
    if os.path.abspath(os.path.join(root, output_record['path'])) != source:
        raise safety.DownloadSafetyError('HLS 임시 출력 경로가 기록과 다릅니다.')
    try:
        os.link(source, target)
        directory_fd = os.open(os.path.dirname(target), os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except FileExistsError:
        if os.path.islink(target) or not os.path.isfile(target):
            raise safety.OutputCollision(f'기존 완료 경로가 안전한 일반 파일이 아닙니다: {target}')
        target_record = _file_record(root, target)
        if target_record['size'] != output_record['size'] or target_record['sha256'] != output_record['sha256']:
            raise safety.OutputCollision(f'기존 완료 파일을 덮어쓰지 않습니다: {target}')
    except OSError as exc:
        raise safety.DownloadSafetyError(f'HLS 결과를 원자적으로 확정할 수 없습니다: {exc}') from exc

    target_record = _file_record(root, target)
    target_record['staging_path'] = output_record['path']
    return target, target_record


def _complete_job(core, path, job, output_path):
    task_id = str(job['task_id'])
    root = os.path.realpath(core.DOWNLOAD_DIR)
    result_kind = job.get('kind')
    if result_kind not in ('hls', 'ytdlp', 'legacy_ts'):
        raise safety.DownloadSafetyError('알 수 없는 MP4 후처리 작업 종류입니다.')
    with safety.task_state_guard():
        _require_recoverable(core, task_id, allow_paused=True)
        record = _output_record(root, output_path)
        _fsync_file(output_path)
        record = _output_record(root, output_path)
        _require_recoverable(core, task_id, allow_paused=True)
        updated = _update_job(path, job, stage='output_ready', output_record=record)
        if result_kind == 'ytdlp':
            safety.finalize_mp4_attempts(
                root,
                task_id,
                job.get('payload', {}).get('input_files') or [],
                preserve_paths=[output_path],
            )
        if result_kind in ('hls', 'legacy_ts'):
            output_path, record = _materialize_hls_output(root, updated, output_path, record)
            updated = _update_job(path, updated, stage='output_ready', output_record=record)
        files_to_move = updated.get('payload', {}).get('ytdlp', {}).get('files_to_move')
        source_paths = []
        if result_kind == 'ytdlp':
            source_paths = _verified_ytdlp_inputs(root, task_id, job.get('payload', {}).get('input_files'))
        _store_local_result(core, task_id, output_path, files_to_move, source_paths,
                            result_kind=result_kind)
        _update_job(path, updated, stage='publish_pending')
    return 'publish'


def _run_one(core, path, job):
    task_id = str(job['task_id'])
    _check_task(core, task_id)
    if job.get('kind') == 'legacy_ts':
        try:
            _validate_resume_artifacts(core, job)
        except safety.DownloadSafetyError as exc:
            # Preserve the source and hold a bad legacy job instead of hashing
            # the same multi-GB TS on every 0.5-second worker wake-up.
            _set_error(core, task_id, exc)
            return 'held'
    else:
        _validate_resume_artifacts(core, job)
    task = core.tasks.get(task_id) or {}
    stage = job.get('stage') or task.get('mp4_stage') or 'queued'
    if stage == 'publish_pending' and task.get('local_result_path'):
        return 'publish'
    if stage == 'output_ready':
        output_path = _verified_output_path(core.DOWNLOAD_DIR, job)
        return _complete_job(core, path, job, output_path)
    if not _mark_running(core, task_id):
        return 'skip'
    try:
        required = int(job['payload']['required_output_bytes'])
        if shutil.disk_usage(core.DOWNLOAD_DIR).free < safety.reserve_bytes(shutil.disk_usage(core.DOWNLOAD_DIR).total):
            raise safety.StorageSpaceError(core.DOWNLOAD_DIR, shutil.disk_usage(core.DOWNLOAD_DIR).free,
                                           required, safety.reserve_bytes(shutil.disk_usage(core.DOWNLOAD_DIR).total))
        if job['kind'] == 'hls':
            output = _process_hls(core, job)
        elif job['kind'] == 'legacy_ts':
            output = _process_legacy_ts(core, job)
        elif job['kind'] == 'ytdlp':
            output = _process_ytdlp(core, job)
        else:
            raise safety.DownloadSafetyError(f'알 수 없는 MP4 queue 작업 종류: {job.get("kind")}')
        _complete_job(core, path, job, output)
        return 'publish'
    except MP4RecoveryHeld:
        return 'held'
    except safety.TaskPauseRequested:
        _set_paused(core, task_id)
        return 'paused'
    except core.DownloadCancelled:
        task = core.tasks.get(task_id)
        if task:
            task['status'] = '취소됨'
            task['mp4_stage'] = 'queued'
            task['speed_bps'] = 0
            core.save_tasks()
        return 'cancelled'
    except BaseException as exc:
        _set_error(core, task_id, exc)
        return 'blocked' if safety.is_storage_error(exc) else 'failed'


def _worker_loop(core, publish):
    root = os.path.realpath(core.DOWNLOAD_DIR)
    while True:
        _WAKE.clear()
        action = None
        task_id = ''
        path = ''
        job = None
        try:
            lock_fd = _queue_lock(root)
            try:
                rows = _eligible_job(core, root)
                if rows:
                    _queued, path, job, task = rows[0]
                    action = _run_one(core, path, job)
                    task_id = str(job['task_id'])
                    if action == 'publish' and task_id and publish:
                        _check_task(core, task_id)
                        result = publish(task_id) or {}
                        if result.get('status') == 'complete':
                            _delete_job(root, path)
                        elif result.get('status') == 'paused':
                            _set_paused(core, task_id)
                        elif result.get('status') == 'error':
                            with safety.task_state_guard():
                                task = core.tasks.get(task_id)
                                if task and not safety.mp4_recovery_hold_reason(task):
                                    task['mp4_stage'] = 'publish_pending'
                                    task['error_kind'] = result.get('error_kind') or 'storage'
                                    core.save_tasks()
                else:
                    task_id = ''
            finally:
                _release_queue_lock(lock_fd)
        except Exception as exc:
            print(f'[MP4 queue] 처리 오류: {exc}', flush=True)
        _WAKE.wait(POLL_SECONDS)


def _deferred_post_process(self, filename, info, files_to_move=None):
    task_id = safety.current_task_id()
    if not task_id or _CORE is None:
        return _ORIGINAL_POST_PROCESS(self, filename, info, files_to_move)
    if not _is_mp4_job(self, filename, info):
        return _ORIGINAL_POST_PROCESS(self, filename, info, files_to_move)
    enqueue_ytdlp(_CORE, task_id, filename, info, files_to_move or {}, self)
    info['filepath'] = filename
    info['__files_to_move'] = files_to_move or {}
    return info


def _validate_resume_artifacts(core, job):
    """Read-only checks before any resume transition or output action."""
    root = os.path.realpath(core.DOWNLOAD_DIR)
    task_id = str(job.get('task_id') or '')
    _validate_job(job)
    kind = job.get('kind')
    task = core.tasks.get(task_id) or {}
    if kind not in ('hls', 'ytdlp', 'legacy_ts') or task.get('mp4_queue_kind') not in (None, '', kind):
        raise MP4RecoveryHeld('MP4 작업 종류가 모호하여 기존 기록을 보존합니다.')
    stage = job.get('stage') or task.get('mp4_stage') or 'queued'
    if stage not in ('queued', 'running', 'output_ready', 'publish_pending'):
        raise MP4RecoveryHeld('MP4 작업 단계가 모호하여 기존 기록을 보존합니다.')
    if kind == 'hls':
        _hls_manifest_check(root, job)
    elif kind == 'legacy_ts':
        records = job.get('payload', {}).get('input_files')
        if not isinstance(records, list) or len(records) != 1:
            raise MP4RecoveryHeld('기존 TS 원본 증거가 불완전합니다.')
        _verify_files(root, records)
        source = os.path.abspath(os.path.join(root, records[0]['path']))
        output = os.path.abspath(os.path.join(root, job['payload'].get('output_path', '')))
        if (os.path.dirname(source) != root or not source.endswith('.ts')
                or output != os.path.splitext(source)[0] + '.mp4'):
            raise MP4RecoveryHeld('기존 TS와 MP4 출력 경로가 일치하지 않습니다.')
    else:
        _verified_ytdlp_inputs(root, task_id, job.get('payload', {}).get('input_files'))
        if stage in ('queued', 'running'):
            descriptor = job.get('payload', {}).get('ytdlp')
            if (not isinstance(descriptor, dict) or not isinstance(descriptor.get('info'), dict)
                    or not isinstance(descriptor.get('filename'), str)):
                raise MP4RecoveryHeld('yt-dlp 실행 기록이 불완전하여 자동 재개를 보류합니다.')
    if stage in ('output_ready', 'publish_pending'):
        output = _verified_output_path(root, job)
        if not output:
            raise MP4RecoveryHeld('MP4 결과 SHA 기록이 없어 자동 재개를 보류합니다.')
        if stage == 'publish_pending':
            if task.get('local_result_path') != os.path.relpath(output, root):
                raise MP4RecoveryHeld('MP4 게시 결과와 작업 기록이 달라 보존합니다.')


def _recover(core):
    """Wake durable work without rewriting any task or queue on service startup.

    A running record is replayable by _run_one under the existing worker lock.
    Its source/result hashes are checked there before the first mutation. This
    also preserves the distinction between stored failure and normal interruption
    across a second crash before the worker starts.
    """
    root = os.path.realpath(core.DOWNLOAD_DIR)
    for path in _job_files(root):
        try:
            _read_job(path)
        except safety.DownloadSafetyError:
            print('[MP4 queue] 손상 job 보존 및 자동 재개 보류', flush=True)
    _WAKE.set()


def retry_task(core, task_id):
    # This function is reached only by the existing explicit retry/resume API.
    path = _job_path(core.DOWNLOAD_DIR, task_id)
    if not os.path.isfile(path):
        return False
    job = _read_job(path)
    with safety.task_state_guard():
        task = core.tasks.get(task_id)
        if not task:
            return False
        persist = getattr(core, 'persist_retry_state_and_enqueue', None)
        if not callable(persist):
            raise MP4RecoveryHeld('확인 가능한 재시도 상태 저장 경로가 없습니다.')
        _validate_resume_artifacts(core, job)
        previous = copy.deepcopy(task)
        job_stage = job.get('stage')
        is_publish = job_stage in ('output_ready', 'publish_pending') or bool(task.get('local_result_path'))
        task['status'] = '다운로드 중' if is_publish else 'MP4 변환 대기'
        task['mp4_stage'] = (job_stage if is_publish else 'queued') or 'queued'
        task.pop('error_kind', None)
        task.pop('last_error_detail', None)
        task['speed_bps'] = 0
        try:
            persist(task_id, previous, enqueue_download=False)
        except Exception:
            task.clear()
            task.update(previous)
            raise
    _WAKE.set()
    return True


def resume_task(core, task_id):
    path = _job_path(core.DOWNLOAD_DIR, task_id)
    if os.path.isfile(path):
        return retry_task(core, task_id)
    return False


def has_task(core, task_id):
    return os.path.isfile(_job_path(core.DOWNLOAD_DIR, task_id))


def pause_task(core, task_id):
    if not has_task(core, task_id):
        return False
    task = core.tasks.get(task_id)
    if not task:
        return False
    if task.get('status') in ('MP4 변환 대기', 'MP4 저장 대기'):
        with safety.task_state_guard():
            task = core.tasks.get(task_id)
            if not task:
                return False
            task['status'] = '일시정지'
            task['speed_bps'] = 0
            core.save_tasks()
    _WAKE.set()
    return True


def cleanup_after_publish(core, task_id):
    task = core.tasks.get(task_id) or {}
    if task.get('status') != '완료' or task.get('local_result_path') or task.get('local_result_paths'):
        return False
    for suffix in ('.ytdlp', '.ytdlp-home'):
        path = os.path.abspath(os.path.join(core.DOWNLOAD_DIR, f'.{task_id}{suffix}'))
        if not _within(core.DOWNLOAD_DIR, path) or os.path.islink(path):
            continue
        if os.path.isdir(path):
            shutil.rmtree(path)
    for key in ('mp4_stage', 'mp4_queued_ns', 'mp4_required_output_bytes', 'mp4_queue_kind'):
        task.pop(key, None)
    core.save_tasks()
    return True


def install(core, publish_callback=None):
    global _CORE, _PUBLISH, _ORIGINAL_POST_PROCESS, _WORKER
    with _INSTALL_LOCK:
        _CORE = core
        _PUBLISH = publish_callback
        os.makedirs(queue_dir(core.DOWNLOAD_DIR), mode=0o700, exist_ok=True)
        safety.set_additional_space_provider(pending_output_bytes)
        if _ORIGINAL_POST_PROCESS is None:
            from yt_dlp import YoutubeDL
            _ORIGINAL_POST_PROCESS = YoutubeDL.post_process
            if not getattr(_ORIGINAL_POST_PROCESS, '_teddy_queue_wrapped', False):
                _deferred_post_process._teddy_queue_wrapped = True
                YoutubeDL.post_process = _deferred_post_process
        _recover(core)
        if _WORKER is None or not _WORKER.is_alive():
            _WORKER = threading.Thread(target=_worker_loop, args=(core, publish_callback),
                                       name='teddy-mp4-worker', daemon=True)
            _WORKER.start()
        return _WORKER

