"""Cross-process guards for Downloader work files and media post-processing.

Lock files live beside the work data so every process/container that shares the
download volume also shares the same lock inode.  Locks are advisory and are
never unlinked: unlinking a held lock file could let another process lock a new
inode and enter concurrently.
"""

import errno
import fcntl
import hashlib
import inspect
import json
import os
import re
import signal
import shutil
import subprocess
import time
import threading
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit


DEFAULT_RESERVE_FLOOR = 512 * 1024 * 1024
DEFAULT_RESERVE_CAP = 5 * 1024 * 1024 * 1024
DEFAULT_RESERVE_RATIO = 0.05
LOCK_POLL_SECONDS = 0.2
_CURRENT_TASK_ID = ContextVar('teddy_download_task_id', default='')
_CURRENT_RESERVATION = ContextVar('teddy_download_space_reservation', default=None)
_CURRENT_FFMPEG_CANCEL_CHECK = ContextVar('teddy_ffmpeg_cancel_check', default=None)
_CURRENT_TASK_INPUTS = ContextVar('teddy_download_task_inputs', default=None)
_CURRENT_MP4_LOCK_FD = ContextVar('teddy_mp4_lock_fd', default=None)
_CURRENT_SPACE_LEASE_FD = ContextVar('teddy_space_lease_fd', default=None)
_CURRENT_REMUX_TRANSACTION = ContextVar('teddy_remux_transaction', default=None)
_TASK_STATE_LOCK = threading.RLock()
_FINAL_PUBLISHING = set()
_ADDITIONAL_SPACE_PROVIDER = None


class DownloadSafetyError(RuntimeError):
    """A fail-closed guard prevented a download or output mutation."""


class StorageSpaceError(DownloadSafetyError):
    def __init__(self, path, free_bytes, required_bytes, reserve_bytes):
        self.path = os.fspath(path)
        self.free_bytes = int(free_bytes)
        self.required_bytes = int(required_bytes)
        self.reserve_bytes = int(reserve_bytes)
        super().__init__(
            '저장 공간 부족: '
            f'{self.path} free={self.free_bytes} '
            f'required={self.required_bytes} reserve={self.reserve_bytes}'
        )


class LockUnavailable(DownloadSafetyError):
    pass


class OutputCollision(DownloadSafetyError):
    pass


class TaskPauseRequested(DownloadSafetyError):
    """Raised after an FFmpeg child is stopped for a user's pause request."""


@contextmanager
def task_state_guard():
    """Serialize task-state transitions with pause and final-publication gates."""
    with _TASK_STATE_LOCK:
        yield


def current_task_id():
    return str(_CURRENT_TASK_ID.get() or '')


def current_task_inputs():
    records = _CURRENT_TASK_INPUTS.get()
    return list(records) if isinstance(records, (list, tuple)) else None


def set_additional_space_provider(provider):
    """Install a read-only source of durable output reservations."""
    global _ADDITIONAL_SPACE_PROVIDER
    if provider is not None and not callable(provider):
        raise DownloadSafetyError('저장 공간 예약 제공자가 호출 가능한 함수가 아닙니다.')
    _ADDITIONAL_SPACE_PROVIDER = provider


def _additional_reserved_bytes(root, exclude_task_id=''):
    provider = _ADDITIONAL_SPACE_PROVIDER
    if provider is None:
        return 0
    amount = int(provider(root, exclude_task_id=exclude_task_id) or 0)
    if amount < 0:
        raise DownloadSafetyError('추가 저장 공간 예약이 음수입니다.')
    return amount


def has_mp4_record(root, task_id, task):
    """Identify MP4-owned records without reading or modifying the queue."""
    import hashlib
    marked = isinstance(task, dict) and (
        task.get('mp4_stage') is not None or bool(task.get('mp4_queue_kind'))
        or task.get('error_kind') == 'mp4'
    )
    digest = hashlib.sha256(str(task_id).encode('utf-8')).hexdigest()
    path = os.path.join(os.path.realpath(root), '.teddy-mp4-queue', digest + '.json')
    return bool(marked) or os.path.lexists(path)


def mp4_recovery_hold_reason(task):
    """Read-only MP4 admission policy; progress records never erase failure intent."""
    if not isinstance(task, dict):
        return 'ambiguous task record'
    status = task.get('status')
    stage = task.get('mp4_stage')
    kind = task.get('mp4_queue_kind')
    if (isinstance(status, str) and status.strip().lower().startswith(('에러', 'error', 'failed'))
            or stage == 'failed' or task.get('error_kind') == 'mp4'):
        return 'explicit MP4 failure'
    if status in ('일시정지', '일시정지 요청 중', '취소됨', '완료'):
        return 'inactive task'
    if status not in ('다운로드 중', '대기 중', 'MP4 변환 대기', 'MP4 변환 중', 'MP4 저장 대기'):
        return 'ambiguous task status'
    if stage not in (None, '', 'queued', 'running', 'output_ready', 'publish_pending'):
        return 'ambiguous MP4 stage'
    if kind not in (None, '', 'hls', 'ytdlp', 'legacy_ts'):
        return 'ambiguous MP4 kind'
    return ''


def begin_final_publish(core, task_id):
    """Atomically claim the transition from local completion to final publish."""
    with _TASK_STATE_LOCK:
        task = core.tasks.get(task_id)
        if not task or task.get('status') == '취소됨':
            raise core.DownloadCancelled()
        if task.get('status') in ('일시정지 요청 중', '일시정지'):
            return False
        if task_id in _FINAL_PUBLISHING:
            return False
        if has_mp4_record(core.DOWNLOAD_DIR, task_id, task):
            if mp4_recovery_hold_reason(task):
                return False
        if task.get('status') != '다운로드 중':
            if not task.get('local_result_path') or not (
                task.get('status') == '대기 중' or str(task.get('status') or '').startswith('에러')
            ):
                return False
            # A previously completed local result may be awaiting publish after a
            # storage error or restart. Resume that result without network work.
            task['status'] = '다운로드 중'
            task['speed_bps'] = 0
            core.save_tasks()
        _FINAL_PUBLISHING.add(task_id)
        return True


def end_final_publish(task_id):
    with _TASK_STATE_LOCK:
        _FINAL_PUBLISHING.discard(task_id)


def final_publish_started(task_id):
    with _TASK_STATE_LOCK:
        return task_id in _FINAL_PUBLISHING


def complete_pause_request(core, task_id):
    """A worker may complete pause only if the request was not superseded."""
    with _TASK_STATE_LOCK:
        task = core.tasks.get(task_id)
        if not task:
            return False
        if task.get('status') == '일시정지 요청 중':
            task['status'] = '일시정지'
            task['speed_bps'] = 0
            core.save_tasks()
            return True
        return task.get('status') == '일시정지'


def mark_pending_local_result(core, task_id, result_fields):
    """Store a finished local result without racing a pause/cancel request."""
    with _TASK_STATE_LOCK:
        task = core.tasks.get(task_id)
        if not task or task.get('status') == '취소됨':
            return 'cancelled'
        if task.get('status') in ('일시정지 요청 중', '일시정지'):
            complete_pause_request(core, task_id)
            return 'paused'
        task.update(result_fields)
        core.save_tasks()
        return 'recorded'


@contextmanager
def task_context(task_id, reservation=None, input_records=None):
    task_token = _CURRENT_TASK_ID.set(str(task_id or ''))
    reservation_token = _CURRENT_RESERVATION.set(reservation)
    input_token = _CURRENT_TASK_INPUTS.set(list(input_records) if input_records is not None else None)
    try:
        yield
    finally:
        _CURRENT_TASK_INPUTS.reset(input_token)
        _CURRENT_RESERVATION.reset(reservation_token)
        _CURRENT_TASK_ID.reset(task_token)


def configured_download_worker_count(settings):
    """Return the persisted download worker count; MP4 serialization is separate."""
    try:
        value = int((settings or {}).get('max_concurrent', 4))
    except (TypeError, ValueError):
        value = 4
    return max(0, min(value, 4))


def estimated_download_size_bytes(progress_data):
    """Return yt-dlp's exact or documented approximate media size, if available."""
    if not isinstance(progress_data, dict):
        return None
    info = progress_data.get('info_dict') or {}
    if not isinstance(info, dict):
        info = {}
    for raw in (
        progress_data.get('total_bytes'),
        progress_data.get('total_bytes_estimate'),
        info.get('filesize'),
        info.get('filesize_approx'),
    ):
        try:
            size = int(raw)
        except (TypeError, ValueError, OverflowError):
            continue
        if size > 0:
            return size
    return None


class InterProcessFileLock:
    """A POSIX flock that is safe across threads, processes and shared mounts."""

    def __init__(self, path):
        self.path = os.path.abspath(os.fspath(path))
        self.fd = None
        self.acquired = False
        self.owner_pid = None

    def acquire(self, blocking=True, cancel_check=None, poll_seconds=LOCK_POLL_SECONDS):
        if self.fd is not None:
            raise LockUnavailable('잠금 객체를 두 번 획득할 수 없습니다.')
        parent = os.path.dirname(self.path)
        try:
            os.makedirs(parent, exist_ok=True)
            self.fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        except OSError as exc:
            self.fd = None
            raise LockUnavailable(f'잠금 파일을 열 수 없습니다: {self.path}: {exc}') from exc

        while True:
            if cancel_check:
                try:
                    cancel_check()
                except BaseException:
                    self._close_fd()
                    raise
            try:
                # Poll when cancellation is observable; a blocking flock syscall
                # cannot run the caller's pause/cancel callback while it waits.
                nonblocking = not blocking or cancel_check is not None
                flags = fcntl.LOCK_EX | (fcntl.LOCK_NB if nonblocking else 0)
                fcntl.flock(self.fd, flags)
                self.acquired = True
                self.owner_pid = os.getpid()
                return True
            except BlockingIOError:
                if not blocking:
                    self._close_fd()
                    return False
                time.sleep(max(0.01, float(poll_seconds)))
            except OSError as exc:
                self._close_fd()
                raise LockUnavailable(f'잠금 획득 실패: {self.path}: {exc}') from exc

    def _close_fd(self):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
        self.fd = None
        self.acquired = False
        self.owner_pid = None

    def release(self):
        fd = self.fd
        if fd is None:
            return
        if self.acquired and self.owner_pid != os.getpid():
            # flock state follows the shared open-file description across fork.
            # A child may close its inherited descriptor, but must not issue
            # LOCK_UN against the parent's lock.
            self._close_fd()
            return
        try:
            if self.acquired:
                fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError as exc:
            raise LockUnavailable(f'잠금 해제 실패: {self.path}: {exc}') from exc
        finally:
            self._close_fd()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.release()
        return False


def _lock_root(root):
    root = os.path.realpath(os.fspath(root))
    if not os.path.isdir(root):
        raise LockUnavailable(f'잠금 공유 작업 디렉터리가 없습니다: {root}')
    return root


def mp4_lock_path(root):
    root = _lock_root(root)
    return os.path.join(root, '.teddy-mp4-remux.lock')


def storage_lock_path(root):
    root = _lock_root(root)
    return os.path.join(root, '.teddy-storage-guard.lock')


def task_lock_path(root, task_id):
    root = _lock_root(root)
    digest = hashlib.sha256(str(task_id).encode('utf-8')).hexdigest()[:24]
    return os.path.join(root, f'.teddy-task-{digest}.lock')


def _reservation_paths(root, task_id):
    digest = hashlib.sha256(str(task_id).encode('utf-8')).hexdigest()
    directory = os.path.join(_lock_root(root), '.teddy-space-reservations')
    return directory, os.path.join(directory, f'{digest}.json'), os.path.join(directory, f'{digest}.lock'), digest


def _active_reserved_bytes(root, device, exclude_digest=''):
    """Read active per-task reservations while the shared storage guard is held."""
    directory = os.path.join(_lock_root(root), '.teddy-space-reservations')
    os.makedirs(directory, exist_ok=True)
    total = 0
    try:
        entries = list(os.scandir(directory))
    except OSError as exc:
        raise DownloadSafetyError(f'저장 공간 예약 목록을 읽을 수 없습니다: {exc}') from exc
    for entry in entries:
        if not entry.name.endswith('.json'):
            continue
        digest = entry.name[:-5]
        if digest == exclude_digest:
            continue
        lock = InterProcessFileLock(os.path.join(directory, f'{digest}.lock'))
        if lock.acquire(blocking=False):
            try:
                try:
                    os.unlink(entry.path)
                except FileNotFoundError:
                    pass
                except OSError as exc:
                    raise DownloadSafetyError(f'만료된 공간 예약을 정리할 수 없습니다: {exc}') from exc
            finally:
                lock.release()
            continue
        try:
            with open(entry.path, 'r', encoding='utf-8') as record_file:
                record = json.load(record_file)
            reserved = int(record['remaining_bytes'])
            record_device = int(record['device'])
            if reserved < 0:
                raise ValueError('negative remaining_bytes')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise DownloadSafetyError(f'활성 저장 공간 예약이 손상되었습니다: {entry.name}: {exc}') from exc
        if record_device == int(device):
            total += reserved
    return total


def _write_reservation_record(path, device, remaining_bytes):
    temp_path = f'{path}.{os.getpid()}.{time.time_ns()}.tmp'
    try:
        with open(temp_path, 'x', encoding='utf-8') as record_file:
            json.dump(
                {'device': int(device), 'remaining_bytes': int(remaining_bytes)},
                record_file,
                separators=(',', ':'),
            )
            record_file.flush()
            os.fsync(record_file.fileno())
        os.replace(temp_path, path)
        directory_fd = os.open(os.path.dirname(path), os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise DownloadSafetyError(f'저장 공간 예약을 기록할 수 없습니다: {exc}') from exc


class StorageReservation:
    """Track estimated remaining bytes for a live download across processes."""
    def __init__(self, root, task_id, path=None):
        self.root = _lock_root(root)
        self.task_id = str(task_id)
        self.path = os.path.realpath(os.fspath(path or root))
        self.directory, self.record_path, lock_path, self.digest = _reservation_paths(root, self.task_id)
        self.task_lock = InterProcessFileLock(lock_path)
        self.device = None
        self.remaining_bytes = 0
        self._unknown_remaining = None
        self._unknown_last_downloaded = None

    def __enter__(self):
        self.task_lock.acquire()
        try:
            os.makedirs(self.directory, exist_ok=True)
            self.device = os.stat(self.path).st_dev
            self.update(0)
        except BaseException:
            self.task_lock.release()
            raise
        return self

    def update(self, remaining_bytes):
        remaining = int(remaining_bytes)
        if remaining < 0:
            raise DownloadSafetyError('남은 저장 공간 예약은 음수일 수 없습니다.')
        guard = InterProcessFileLock(storage_lock_path(self.root))
        guard.acquire()
        try:
            reserved = _active_reserved_bytes(self.root, self.device, exclude_digest=self.digest)
            queued = _additional_reserved_bytes(
                self.root,
                exclude_task_id=current_task_id() or self.task_id,
            )
            ensure_space(self.path, required_bytes=reserved + queued + remaining)
            _write_reservation_record(self.record_path, self.device, remaining)
            self.remaining_bytes = remaining
        finally:
            guard.release()

    def reset_unknown(self):
        self._unknown_remaining = None
        self._unknown_last_downloaded = None

    def observe_unknown_size(self, downloaded_bytes):
        """Lease current free headroom to a size-unknown stream and consume it.

        yt-dlp progress hooks run after a write. This bounds later writes and
        reserves the observed free headroom against other jobs; it cannot undo
        a single write that already consumed the last available blocks.
        """
        downloaded = max(0, int(downloaded_bytes or 0))
        if self.device is None:
            raise DownloadSafetyError('크기 미상 다운로드 공간 예약이 초기화되지 않았습니다.')
        if self._unknown_remaining is None:
            guard = InterProcessFileLock(storage_lock_path(self.root))
            guard.acquire()
            try:
                usage = shutil.disk_usage(self.path)
                reserved = _active_reserved_bytes(self.root, self.device, exclude_digest=self.digest)
                queued = _additional_reserved_bytes(self.root, exclude_task_id=self.task_id)
                reserve = reserve_bytes(usage.total)
                available = usage.free - reserve - reserved - queued
                if available <= 0:
                    raise StorageSpaceError(self.path, usage.free, reserved + queued + 1, reserve)
            finally:
                guard.release()
            self.update(available)
            self._unknown_remaining = available
            self._unknown_last_downloaded = downloaded
            return available

        previous = int(self._unknown_last_downloaded or 0)
        delta = max(0, downloaded - previous)
        remaining = int(self._unknown_remaining)
        if delta > remaining:
            self.update(0)
            self._unknown_remaining = 0
            self._unknown_last_downloaded = downloaded
            usage = shutil.disk_usage(self.path)
            raise StorageSpaceError(self.path, usage.free, delta, reserve_bytes(usage.total))
        remaining -= delta
        self.update(remaining)
        self._unknown_remaining = remaining
        self._unknown_last_downloaded = downloaded
        return remaining

    def __exit__(self, exc_type, exc, traceback):
        guard = InterProcessFileLock(storage_lock_path(self.root))
        try:
            guard.acquire()
            try:
                os.unlink(self.record_path)
            except FileNotFoundError:
                pass
            finally:
                guard.release()
        finally:
            self.task_lock.release()
        return False


def try_task_claim(root, task_id):
    lock = InterProcessFileLock(task_lock_path(root, task_id))
    if not lock.acquire(blocking=False):
        return None
    return lock


def reserve_bytes(total_bytes):
    configured = os.environ.get('TEDDY_STORAGE_RESERVE_BYTES')
    if configured not in (None, ''):
        try:
            value = int(configured)
        except (TypeError, ValueError) as exc:
            raise DownloadSafetyError('TEDDY_STORAGE_RESERVE_BYTES가 정수가 아닙니다.') from exc
        if value < 0:
            raise DownloadSafetyError('TEDDY_STORAGE_RESERVE_BYTES는 음수일 수 없습니다.')
        return value
    proportional = int(max(0, int(total_bytes)) * DEFAULT_RESERVE_RATIO)
    return max(DEFAULT_RESERVE_FLOOR, min(proportional, DEFAULT_RESERVE_CAP))


def ensure_space(path, required_bytes=0, reserve=None):
    path = os.path.realpath(os.fspath(path))
    if not os.path.exists(path):
        raise DownloadSafetyError(f'저장 공간 경로가 없습니다: {path}')
    usage = shutil.disk_usage(path)
    required = int(required_bytes)
    if required < 0:
        raise DownloadSafetyError('필요 저장 공간은 음수일 수 없습니다.')
    reserve = reserve_bytes(usage.total) if reserve is None else int(reserve)
    if reserve < 0:
        raise DownloadSafetyError('저장 공간 여유분은 음수일 수 없습니다.')
    if usage.free < required + reserve:
        raise StorageSpaceError(path, usage.free, required, reserve)
    return usage


def ensure_download_start_space(path):
    """Check the configured safety reserve before a new or resumed download."""
    with StorageWriteTransaction(path, output_path=path, required_bytes=0):
        return shutil.disk_usage(path)


class StorageWriteTransaction:
    def __init__(self, root, output_path=None, required_bytes=0, cancel_check=None):
        self.root = _lock_root(root)
        self.output_path = os.path.realpath(os.fspath(output_path or root))
        self.required_bytes = int(required_bytes)
        if self.required_bytes < 0:
            raise DownloadSafetyError('필요 저장 공간은 음수일 수 없습니다.')
        self.cancel_check = cancel_check
        self.reservation = None
        self.remaining_bytes = self.required_bytes

    def __enter__(self):
        lease_id = f'write-{uuid.uuid4().hex}'
        reservation = StorageReservation(self.root, lease_id, self.output_path)
        reservation.__enter__()
        try:
            if self.cancel_check:
                self.cancel_check()
            reservation.update(self.required_bytes)
        except BaseException:
            import sys
            reservation.__exit__(*sys.exc_info())
            raise
        self.reservation = reservation
        self.remaining_bytes = self.required_bytes
        return self

    def set_remaining(self, remaining_bytes):
        remaining = int(remaining_bytes)
        if remaining < 0:
            raise DownloadSafetyError('남은 저장 공간 예약은 음수일 수 없습니다.')
        if self.reservation is None:
            raise DownloadSafetyError('활성 저장 공간 예약 없이 사용량을 갱신할 수 없습니다.')
        if self.cancel_check:
            self.cancel_check()
        self.reservation.update(remaining)
        self.remaining_bytes = remaining

    def consume_written(self, written_bytes):
        written = int(written_bytes)
        if written < 0:
            raise DownloadSafetyError('기록한 저장 공간 사용량은 음수일 수 없습니다.')
        self.set_remaining(max(0, self.remaining_bytes - written))

    def __exit__(self, exc_type, exc, traceback):
        reservation = self.reservation
        self.reservation = None
        if reservation is not None:
            reservation.__exit__(exc_type, exc, traceback)
        return False


class RemuxTransaction:
    """Serializes MP4 work while holding only a durable space lease during FFmpeg."""

    def __init__(self, root, output_path=None, required_output_bytes=0, cancel_check=None):
        self.root = _lock_root(root)
        self.cancel_check = cancel_check
        self.mp4_lock = InterProcessFileLock(mp4_lock_path(root))
        self.storage = StorageWriteTransaction(
            root,
            output_path=output_path,
            required_bytes=required_output_bytes,
            cancel_check=cancel_check,
        )
        self._lock_fd_token = None
        self._space_fd_token = None
        self._transaction_token = None
        self.output_paths = []
        self._observed_output_bytes = 0

    def __enter__(self):
        self.mp4_lock.acquire(cancel_check=self.cancel_check)
        self._lock_fd_token = _CURRENT_MP4_LOCK_FD.set(self.mp4_lock.fd)
        try:
            self.storage.__enter__()
            lease_fd = self.storage.reservation.task_lock.fd
            self._space_fd_token = _CURRENT_SPACE_LEASE_FD.set(lease_fd)
            self._transaction_token = _CURRENT_REMUX_TRANSACTION.set(self)
        except BaseException:
            try:
                if self.storage.reservation is not None:
                    self.storage.__exit__(None, None, None)
            finally:
                try:
                    if self._transaction_token is not None:
                        _CURRENT_REMUX_TRANSACTION.reset(self._transaction_token)
                        self._transaction_token = None
                    if self._space_fd_token is not None:
                        _CURRENT_SPACE_LEASE_FD.reset(self._space_fd_token)
                        self._space_fd_token = None
                    if self._lock_fd_token is not None:
                        _CURRENT_MP4_LOCK_FD.reset(self._lock_fd_token)
                        self._lock_fd_token = None
                finally:
                    self.mp4_lock.release()
            raise
        return self

    def set_output_paths(self, paths):
        normalized = []
        device_ids = set()
        for value in paths:
            path = os.path.abspath(os.fspath(value))
            try:
                if os.path.commonpath([self.root, path]) != self.root:
                    raise DownloadSafetyError(f'MP4 출력 경로가 작업 루트 밖에 있습니다: {path}')
            except ValueError as exc:
                raise DownloadSafetyError(f'MP4 출력 경로를 검증할 수 없습니다: {path}') from exc
            parent = os.path.realpath(os.path.dirname(path) or self.root)
            try:
                if os.path.commonpath([self.root, parent]) != self.root:
                    raise DownloadSafetyError(f'MP4 출력 디렉터리가 작업 루트 밖에 있습니다: {parent}')
            except ValueError as exc:
                raise DownloadSafetyError(f'MP4 출력 디렉터리를 검증할 수 없습니다: {parent}') from exc
            if not os.path.isdir(parent):
                raise DownloadSafetyError(f'MP4 출력 디렉터리가 없습니다: {parent}')
            device_ids.add(os.stat(parent).st_dev)
            normalized.append(path)
        if len(device_ids) > 1 or (
            device_ids and self.storage.reservation.device not in device_ids
        ):
            raise DownloadSafetyError('여러 파일시스템에 걸친 MP4 출력을 단일 공간 예약으로 보호할 수 없습니다.')
        self.output_paths = normalized
        self.refresh_output_reservation()

    def refresh_output_reservation(self):
        if not self.output_paths:
            return
        used = 0
        for path in self.output_paths:
            if not os.path.lexists(path):
                continue
            if os.path.islink(path) or not os.path.isfile(path):
                raise DownloadSafetyError(f'MP4 출력이 일반 파일이 아닙니다: {path}')
            if os.stat(path).st_dev != self.storage.reservation.device:
                raise DownloadSafetyError(f'MP4 출력 파일시스템이 예약 대상과 다릅니다: {path}')
            used += os.path.getsize(path)
        self._observed_output_bytes = used
        self.storage.set_remaining(max(0, self.storage.required_bytes - used))

    def __exit__(self, exc_type, exc, traceback):
        try:
            self.storage.__exit__(exc_type, exc, traceback)
        finally:
            if self._transaction_token is not None:
                _CURRENT_REMUX_TRANSACTION.reset(self._transaction_token)
                self._transaction_token = None
            if self._space_fd_token is not None:
                _CURRENT_SPACE_LEASE_FD.reset(self._space_fd_token)
                self._space_fd_token = None
            if self._lock_fd_token is not None:
                _CURRENT_MP4_LOCK_FD.reset(self._lock_fd_token)
                self._lock_fd_token = None
            self.mp4_lock.release()
        return False


def directory_size(path, suffix=None):
    total = 0
    for entry in os.scandir(path):
        if not entry.is_file(follow_symlinks=False):
            continue
        if suffix and not entry.name.endswith(suffix):
            continue
        total += entry.stat(follow_symlinks=False).st_size
    return total


_VOLATILE_HLS_QUERY_KEYS = {
    'access_token', 'auth', 'authorization', 'exp', 'expire', 'expires',
    'hdnea', 'hdnts', 'jwt', 'key-pair-id', 'policy', 'sig', 'signature',
    'token', '__gda__',
}


def resolve_hls_uri(base_url, uri):
    resolved = urljoin(str(base_url), str(uri).strip())
    parsed = urlsplit(resolved)
    if parsed.scheme.lower() not in ('http', 'https') or not parsed.hostname:
        raise DownloadSafetyError('HLS 재생목록에 안전하지 않거나 확인할 수 없는 URI가 있습니다.')
    if parsed.username is not None or parsed.password is not None:
        raise DownloadSafetyError('HLS URI의 사용자 인증 정보는 재개 식별에 사용할 수 없습니다.')
    return resolved


def _canonical_hls_uri(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or '').lower()
    if not host or parsed.scheme.lower() not in ('http', 'https'):
        raise DownloadSafetyError('HLS 원본 URI를 정규화할 수 없습니다.')
    try:
        port = parsed.port
    except ValueError as exc:
        raise DownloadSafetyError('HLS 원본 URI의 포트를 확인할 수 없습니다.') from exc
    default_port = (parsed.scheme.lower() == 'http' and port == 80) or (
        parsed.scheme.lower() == 'https' and port == 443
    )
    netloc = host if port is None or default_port else f'{host}:{port}'
    query = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.casefold()
        is_known_auth = (
            lowered in _VOLATILE_HLS_QUERY_KEYS
            or lowered.startswith('x-amz-')
            or lowered.startswith('x-goog-')
        )
        if not is_known_auth:
            query.append((key, value))
    # Preserve stable query order and duplicate values; unknown parameters can
    # select a different representation and therefore remain identity-bearing.
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or '/', urlencode(query), ''))


def hls_playlist_identity(variant_url, playlist_text):
    """Hash ordered HLS source semantics while normalizing known auth query fields."""
    variant = _canonical_hls_uri(resolve_hls_uri(variant_url, variant_url))
    entries = []
    segment_urls = []
    uri_attribute = re.compile(r'(?i)(\bURI\s*=\s*)("|\')([^"\']*)(\2)')
    for raw_line in str(playlist_text).lstrip('\ufeff').splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith('#'):
            if line.startswith('#EXT'):
                if uri_attribute.search(line):
                    matches = list(uri_attribute.finditer(line))
                    if not matches:
                        raise DownloadSafetyError('HLS URI 태그 구조를 해석할 수 없어 재개를 중단했습니다.')
                    def normalize_uri(match):
                        resolved = resolve_hls_uri(variant_url, match.group(3))
                        return match.group(1) + match.group(2) + _canonical_hls_uri(resolved) + match.group(4)
                    line = uri_attribute.sub(normalize_uri, line)
                entries.append({'kind': 'tag', 'value': line})
            # Non-EXT comments do not affect the media plan.
            continue
        resolved = resolve_hls_uri(variant_url, line)
        segment_urls.append(resolved)
        entries.append({'kind': 'segment', 'uri': _canonical_hls_uri(resolved)})
    if not segment_urls:
        raise DownloadSafetyError('HLS 재생목록에서 세그먼트 계획을 확인할 수 없습니다.')
    serialized = json.dumps(
        {'schema': 1, 'variant': variant, 'entries': entries},
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return hashlib.sha256(serialized).hexdigest(), segment_urls


def _hls_manifest_path(parts_dir):
    return os.path.join(parts_dir, 'resume-plan.json')


def _atomic_write_json(path, value, *, no_clobber=False):
    temp_path = f'{path}.{os.getpid()}.{time.time_ns()}.tmp'
    try:
        with open(temp_path, 'x', encoding='utf-8') as out:
            json.dump(value, out, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
            out.write('\n')
            out.flush()
            os.fsync(out.fileno())
        if no_clobber:
            atomic_publish_noclobber(temp_path, path)
        else:
            if os.path.islink(path):
                raise DownloadSafetyError(f'재개 매니페스트가 심볼릭 링크여서 기록할 수 없습니다: {path}')
            os.replace(temp_path, path)
            directory_fd = os.open(os.path.dirname(path), os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    except BaseException:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def prepare_hls_resume(parts_dir, task_id, plan_sha256, segment_count, expected_filelist, segment_path):
    """Validate source-plan identity and hashes before reusing any old segment."""
    manifest_path = _hls_manifest_path(parts_dir)
    filelist_path = os.path.join(parts_dir, 'filelist.txt')
    if os.path.islink(manifest_path) or os.path.islink(filelist_path):
        raise DownloadSafetyError('기존 HLS 재개 메타데이터가 심볼릭 링크여서 조각을 보존했습니다.')
    if os.path.lexists(manifest_path):
        try:
            with open(manifest_path, 'r', encoding='utf-8') as src:
                manifest = json.load(src)
        except (OSError, ValueError) as exc:
            raise DownloadSafetyError(f'HLS 재개 매니페스트를 읽을 수 없어 조각을 보존했습니다: {exc}') from exc
        if not isinstance(manifest, dict) or manifest.get('schema') != 1:
            raise DownloadSafetyError('HLS 재개 매니페스트 schema가 달라 조각을 보존했습니다.')
        if manifest.get('task_id') != str(task_id):
            raise DownloadSafetyError('HLS 재개 매니페스트의 작업 ID가 달라 조각을 보존했습니다.')
        if manifest.get('plan_sha256') != plan_sha256:
            raise DownloadSafetyError('HLS 세그먼트 계획이 기존 재개 자료와 달라 조각을 보존했습니다.')
        if manifest.get('segment_count') != int(segment_count):
            raise DownloadSafetyError('HLS 세그먼트 수가 기존 재개 자료와 달라 조각을 보존했습니다.')
        completed = manifest.get('completed_segments')
        if not isinstance(completed, dict):
            raise DownloadSafetyError('HLS 완료 조각 목록이 잘못되어 기존 조각을 보존했습니다.')
    else:
        entries = os.listdir(parts_dir)
        if entries:
            raise DownloadSafetyError(
                '기존 HLS 조각에 원본 계획 결속 정보가 없어 자동 재사용하지 않습니다. '
                '기존 조각을 그대로 보존했습니다.'
            )
        manifest = {
            'schema': 1,
            'task_id': str(task_id),
            'plan_sha256': plan_sha256,
            'segment_count': int(segment_count),
            'completed_segments': {},
        }
        _atomic_write_json(manifest_path, manifest, no_clobber=True)
        completed = manifest['completed_segments']

    for key, record in completed.items():
        try:
            index = int(key)
            valid_record = (
                0 <= index < int(segment_count)
                and isinstance(record, dict)
                and int(record['size']) > 0
                and re.fullmatch(r'[0-9a-f]{64}', str(record['sha256'])) is not None
            )
        except (TypeError, ValueError, KeyError):
            valid_record = False
        if not valid_record:
            raise DownloadSafetyError('HLS 완료 조각 식별 정보가 잘못되어 조각을 보존했습니다.')

    expected_names = {os.path.basename(segment_path(i)) for i in range(int(segment_count))}
    for name in os.listdir(parts_dir):
        if name.endswith('.ts') and name not in expected_names:
            raise DownloadSafetyError(f'현재 계획에 없는 HLS 조각이 있어 자동 재사용을 중단했습니다: {name}')

    reused = []
    for index in range(int(segment_count)):
        path = segment_path(index)
        if os.path.islink(path):
            raise DownloadSafetyError(f'기존 HLS 조각이 심볼릭 링크여서 보존했습니다: {path}')
        if not os.path.lexists(path):
            continue
        if not os.path.isfile(path) or os.path.getsize(path) <= 0:
            raise DownloadSafetyError(f'기존 HLS 조각이 비어 있거나 일반 파일이 아니어서 보존했습니다: {path}')
        record = completed.get(str(index))
        if not record:
            raise DownloadSafetyError(f'기존 HLS 조각의 완료 기록이 없어 자동 재사용하지 않습니다: {path}')
        if os.path.getsize(path) != int(record['size']) or sha256_file(path) != record['sha256']:
            raise DownloadSafetyError(f'기존 HLS 조각 SHA/크기가 재개 기록과 달라 보존했습니다: {path}')
        reused.append(index)

    if os.path.lexists(filelist_path):
        if not os.path.isfile(filelist_path):
            raise DownloadSafetyError('HLS filelist가 일반 파일이 아니어서 조각을 보존했습니다.')
        with open(filelist_path, 'r', encoding='utf-8') as src:
            if src.read() != expected_filelist:
                raise DownloadSafetyError('HLS filelist가 현재 세그먼트 순서와 달라 조각을 보존했습니다.')
    else:
        temp_path = f'{filelist_path}.{os.getpid()}.{time.time_ns()}.tmp'
        try:
            with open(temp_path, 'x', encoding='utf-8') as out:
                out.write(expected_filelist)
                out.flush()
                os.fsync(out.fileno())
            atomic_publish_noclobber(temp_path, filelist_path)
        except BaseException:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise
    return manifest, reused


def record_hls_segment(parts_dir, task_id, plan_sha256, index, path):
    manifest_path = _hls_manifest_path(parts_dir)
    with open(manifest_path, 'r', encoding='utf-8') as src:
        manifest = json.load(src)
    if (manifest.get('task_id') != str(task_id)
            or manifest.get('plan_sha256') != plan_sha256
            or manifest.get('schema') != 1):
        raise DownloadSafetyError('HLS 재개 매니페스트가 쓰기 직전에 변경되어 조각을 보존했습니다.')
    if os.path.islink(path) or not os.path.isfile(path) or os.path.getsize(path) <= 0:
        raise DownloadSafetyError('HLS 저장 조각을 검증할 수 없어 재개 기록을 갱신하지 않았습니다.')
    manifest.setdefault('completed_segments', {})[str(int(index))] = {
        'size': os.path.getsize(path),
        'sha256': sha256_file(path),
    }
    _atomic_write_json(manifest_path, manifest)


def sha256_file(path, chunk_size=1024 * 1024):
    digest = hashlib.sha256()
    with open(path, 'rb') as source:
        while True:
            chunk = source.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def estimated_remux_output_bytes(input_bytes):
    """Conservative copy-remux estimate: input bytes, 10%, and 64 MiB overhead."""
    value = int(input_bytes)
    if value < 0:
        raise DownloadSafetyError('입력 크기는 음수일 수 없습니다.')
    return value + max(value // 10, 64 * 1024 * 1024)


def _terminate_process_group(process, grace_seconds=2.0):
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except OSError:
        try:
            process.terminate()
        except OSError:
            pass
    try:
        process.communicate(timeout=max(0.1, float(grace_seconds)))
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.communicate()
    except OSError:
        pass


MP4_ATTEMPT_SCHEMA = 1
MP4_ATTEMPT_DIRNAME = '.teddy-mp4-attempts'


def _attempt_dir(root, task_id):
    digest = hashlib.sha256(str(task_id).encode('utf-8')).hexdigest()
    return os.path.join(_lock_root(root), MP4_ATTEMPT_DIRNAME, digest)


def _attempt_seal(value):
    sealed = dict(value)
    sealed.pop('record_sha256', None)
    canonical = json.dumps(sealed, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    sealed['record_sha256'] = hashlib.sha256(canonical).hexdigest()
    return sealed


def _write_attempt(path, value, *, exclusive=False):
    directory = os.path.dirname(path)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    if os.path.islink(directory) or os.path.islink(path):
        raise DownloadSafetyError('MP4 복구 기록 경로에 symlink가 있습니다.')
    sealed = _attempt_seal(value)
    temp = f'{path}.{os.getpid()}.{time.time_ns()}.tmp'
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(temp, flags, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(sealed, stream, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            try:
                os.link(temp, path)
            except FileExistsError as exc:
                raise OutputCollision(f'MP4 복구 기록 충돌: {path}') from exc
            os.unlink(temp)
        else:
            os.replace(temp, path)
        directory_fd = os.open(directory, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
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


def _read_attempt(path):
    try:
        with open(path, 'r', encoding='utf-8') as stream:
            value = json.load(stream)
    except (OSError, ValueError, TypeError) as exc:
        raise DownloadSafetyError(f'MP4 복구 기록을 읽을 수 없습니다: {path}: {exc}') from exc
    if not isinstance(value, dict) or value.get('schema') != MP4_ATTEMPT_SCHEMA:
        raise DownloadSafetyError(f'MP4 복구 기록 schema가 잘못되었습니다: {path}')
    recorded = str(value.get('record_sha256') or '')
    if _attempt_seal(value).get('record_sha256') != recorded:
        raise DownloadSafetyError(f'MP4 복구 기록 SHA 검증에 실패했습니다: {path}')
    return value


def _relative_file_record(root, path):
    root = os.path.realpath(os.fspath(root))
    absolute = os.path.abspath(os.fspath(path))
    real = os.path.realpath(absolute)
    if (not os.path.commonpath([root, absolute]) == root or real != absolute
            or os.path.islink(absolute)
            or not os.path.isfile(absolute)):
        raise DownloadSafetyError(f'MP4 작업 파일이 안전한 일반 파일이 아닙니다: {absolute}')
    return {
        'path': os.path.relpath(absolute, root),
        'size': os.path.getsize(absolute),
        'sha256': sha256_file(absolute),
    }


def _input_records_equal(left, right):
    def key(record):
        return (str(record.get('path') or ''), int(record.get('size', -1)), str(record.get('sha256') or ''))
    try:
        return sorted(key(row) for row in left) == sorted(key(row) for row in right)
    except (TypeError, ValueError, AttributeError):
        return False


def begin_mp4_attempt(root, task_id, input_paths, output_paths, base_input_records=None):
    """Durably bind unique FFmpeg staging outputs to one task and its inputs."""
    root = os.path.realpath(os.fspath(root))
    task_id = str(task_id or '')
    inputs = []
    input_abs = set()
    for raw_path in input_paths:
        path = os.path.abspath(os.fspath(raw_path))
        record = _relative_file_record(root, path)
        inputs.append(record)
        input_abs.add(path)
    if not inputs:
        raise DownloadSafetyError('MP4 변환 입력 증거가 없어 복구 기록을 만들 수 없습니다.')
    base = list(base_input_records) if base_input_records is not None else inputs
    attempt_id = uuid.uuid4().hex
    output_rows = []
    stage_map = {}
    for raw_path in output_paths:
        target = os.path.abspath(os.fspath(raw_path))
        if target in input_abs:
            # Preserve yt-dlp's existing in-place fixup semantics; its global
            # lock is still inherited by the child, but no output is owned here.
            continue
        if (os.path.commonpath([root, target]) != root or os.path.realpath(target) != target
                or os.path.islink(target)):
            raise DownloadSafetyError(f'MP4 출력 경로가 작업 루트 밖이거나 symlink입니다: {target}')
        if os.path.lexists(target):
            raise OutputCollision(f'기존 완료 파일을 덮어쓰지 않습니다: {target}')
        parent = os.path.dirname(target) or root
        if not os.path.isdir(parent):
            raise DownloadSafetyError(f'MP4 출력 디렉터리가 없습니다: {parent}')
        stage = os.path.join(parent, f'.{os.path.basename(target)}.teddy-{attempt_id[:16]}.partial.mp4')
        if os.path.lexists(stage):
            raise OutputCollision(f'MP4 임시 출력 경로가 이미 존재합니다: {stage}')
        target_rel = os.path.relpath(target, root)
        stage_rel = os.path.relpath(stage, root)
        output_rows.append({'target_path': target_rel, 'stage_path': stage_rel})
        stage_map[target] = stage
    if not output_rows:
        raise DownloadSafetyError('관리 가능한 MP4 출력 경로가 없습니다.')
    attempt = {
        'schema': MP4_ATTEMPT_SCHEMA,
        'attempt_id': attempt_id,
        'task_id': task_id,
        'state': 'running',
        'created_ns': time.time_ns(),
        'base_input_files': base,
        'ffmpeg_input_files': inputs,
        'outputs': output_rows,
    }
    path = os.path.join(_attempt_dir(root, task_id), f'{attempt_id}.json')
    sealed = _write_attempt(path, attempt, exclusive=True)
    return {'path': path, 'record': sealed, 'stage_map': stage_map}


def update_mp4_attempt(attempt, state):
    if not attempt:
        return None
    value = dict(attempt['record'])
    value.pop('record_sha256', None)
    value['state'] = str(state)
    attempt['record'] = _write_attempt(attempt['path'], value)
    return attempt['record']


def complete_mp4_attempt_outputs(root, attempt):
    if not attempt:
        return []
    root = os.path.realpath(os.fspath(root))
    value = dict(attempt['record'])
    rows = []
    for row in value.get('outputs') or []:
        stage = os.path.abspath(os.path.join(root, row['stage_path']))
        target = os.path.abspath(os.path.join(root, row['target_path']))
        if (not os.path.commonpath([root, stage]) == root or not os.path.commonpath([root, target]) == root
                or os.path.islink(stage) or not os.path.isfile(stage) or os.path.getsize(stage) <= 0):
            raise DownloadSafetyError(f'FFmpeg 임시 결과를 확인할 수 없습니다: {stage}')
        fd = os.open(stage, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        rows.append({
            'target_path': row['target_path'],
            'stage_path': row['stage_path'],
            'size': os.path.getsize(stage),
            'sha256': sha256_file(stage),
        })
    value['outputs'] = rows
    value.pop('record_sha256', None)
    attempt['record'] = _write_attempt(attempt['path'], value)
    return rows


def commit_mp4_attempt_outputs(root, attempt):
    if not attempt:
        return []
    if attempt['record'].get('state') != 'ffmpeg_complete':
        update_mp4_attempt(attempt, 'ffmpeg_complete')
    root = os.path.realpath(os.fspath(root))
    committed = []
    for row in attempt['record'].get('outputs') or []:
        target = os.path.abspath(os.path.join(root, row['target_path']))
        stage = os.path.abspath(os.path.join(root, row['stage_path']))
        if os.path.lexists(target):
            raise OutputCollision(f'기존 완료 파일을 덮어쓰지 않습니다: {target}')
        if not os.path.isfile(stage) or os.path.islink(stage) or sha256_file(stage) != row.get('sha256'):
            raise DownloadSafetyError(f'MP4 임시 결과가 기록된 SHA와 다릅니다: {stage}')
        atomic_publish_noclobber(stage, target)
        committed.append(target)
    return committed


def _attempt_files(root, task_id):
    directory = _attempt_dir(root, task_id)
    if not os.path.isdir(directory):
        return []
    if os.path.islink(directory):
        raise DownloadSafetyError(f'MP4 복구 기록 디렉터리가 symlink입니다: {directory}')
    return [os.path.join(directory, name) for name in sorted(os.listdir(directory)) if name.endswith('.json')]


def recover_mp4_attempts(root, task_id, base_input_records, *, allow_complete=False):
    """Called only while holding the global MP4 lock; clean or reuse owned crash leftovers."""
    root = os.path.realpath(os.fspath(root))
    task_id = str(task_id or '')
    complete = []
    for path in _attempt_files(root, task_id):
        attempt = _read_attempt(path)
        if attempt.get('task_id') != task_id or not _input_records_equal(
                attempt.get('base_input_files') or [], base_input_records or []):
            raise DownloadSafetyError(f'임시 MP4 소유 작업/입력 증거가 달라 파일을 보존했습니다: {path}')
        state = attempt.get('state')
        if state not in ('running', 'ffmpeg_complete'):
            raise DownloadSafetyError(f'임시 MP4 상태를 검증할 수 없어 파일을 보존했습니다: {path}')
        rows = attempt.get('outputs')
        if not isinstance(rows, list) or not rows:
            raise DownloadSafetyError(f'임시 MP4 출력 소유 정보가 없어 파일을 보존했습니다: {path}')
        valid_rows = []
        for row in rows:
            target = os.path.abspath(os.path.join(root, str(row.get('target_path') or '')))
            stage = os.path.abspath(os.path.join(root, str(row.get('stage_path') or '')))
            if (not row.get('target_path') or not row.get('stage_path')
                    or os.path.commonpath([root, target]) != root
                    or os.path.commonpath([root, stage]) != root
                    or os.path.realpath(target) != target
                    or os.path.realpath(stage) != stage
                    or os.path.islink(target) or os.path.islink(stage)):
                raise DownloadSafetyError(f'임시 MP4 경로를 검증할 수 없어 보존했습니다: {path}')
            if state == 'ffmpeg_complete':
                size = int(row.get('size', -1))
                digest = str(row.get('sha256') or '')
                if size <= 0 or len(digest) != 64:
                    raise DownloadSafetyError(f'임시 MP4 완료 SHA가 없어 보존했습니다: {path}')
                for candidate in (stage, target):
                    if os.path.lexists(candidate):
                        if not os.path.isfile(candidate) or os.path.getsize(candidate) != size or sha256_file(candidate) != digest:
                            raise DownloadSafetyError(f'임시 MP4가 소유 기록과 달라 보존했습니다: {candidate}')
                if os.path.isfile(target):
                    valid_rows.append((target, row))
                elif os.path.isfile(stage):
                    try:
                        atomic_publish_noclobber(stage, target)
                    except OutputCollision as exc:
                        raise DownloadSafetyError(f'임시 MP4 결과를 안전하게 복구하지 못했습니다: {target}') from exc
                    valid_rows.append((target, row))
            else:
                # A running attempt has no completion SHA. Its randomly named
                # staging path is owned by this durable record; final targets
                # must not exist until a completed SHA has been journaled.
                if os.path.lexists(target):
                    raise DownloadSafetyError(f'검증되지 않은 임시 MP4가 최종 경로에 있어 보존했습니다: {target}')
                if os.path.lexists(stage):
                    if not os.path.isfile(stage):
                        raise DownloadSafetyError(f'임시 MP4가 일반 파일이 아니어서 보존했습니다: {stage}')
                    os.unlink(stage)
                    parent_fd = os.open(os.path.dirname(stage), os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
                    try:
                        os.fsync(parent_fd)
                    finally:
                        os.close(parent_fd)
        if state == 'ffmpeg_complete' and len(valid_rows) == len(rows):
            complete.append((path, attempt, valid_rows))
        else:
            # Only completed HLS output can be promoted. yt-dlp's full PP chain
            # has not yet returned, so an FFmpeg-only result is not final.
            os.unlink(path)
    if allow_complete and complete:
        if len(complete) != 1 or len(complete[0][2]) != 1:
            raise DownloadSafetyError('복구 가능한 MP4 완성 결과가 하나로 특정되지 않습니다.')
        _path, _attempt, rows = complete[0]
        target, row = rows[0]
        return {'path': os.path.relpath(target, root), 'size': int(row['size']), 'sha256': row['sha256']}
    if complete:
        for path, _attempt, rows in complete:
            for target, row in rows:
                if os.path.lexists(target):
                    if os.path.getsize(target) != int(row['size']) or sha256_file(target) != row['sha256']:
                        raise DownloadSafetyError(f'완료된 임시 MP4가 소유 SHA와 달라 보존했습니다: {target}')
                    os.unlink(target)
            os.unlink(path)
    return None


def finalize_mp4_attempts(root, task_id, base_input_records, *, preserve_paths=()):
    """Drop journals only after the queue has durably recorded its final output SHA."""
    root = os.path.realpath(os.fspath(root))
    preserve = {os.path.abspath(os.fspath(path)) for path in preserve_paths}
    for path in _attempt_files(root, task_id):
        attempt = _read_attempt(path)
        if attempt.get('task_id') != str(task_id) or not _input_records_equal(
                attempt.get('base_input_files') or [], base_input_records or []):
            raise DownloadSafetyError(f'최종 MP4 잠금 연결이 달라 복구 기록을 유지했습니다: {path}')
        for row in attempt.get('outputs') or []:
            stage = os.path.abspath(os.path.join(root, str(row.get('stage_path') or '')))
            if os.path.commonpath([root, stage]) != root or os.path.islink(stage):
                raise DownloadSafetyError(f'완료 후 임시 MP4 경로가 비안전하여 보존했습니다: {stage}')
            if os.path.lexists(stage):
                if (not os.path.isfile(stage) or not row.get('sha256')
                        or os.path.getsize(stage) != int(row.get('size', -1))
                        or sha256_file(stage) != row.get('sha256')):
                    raise DownloadSafetyError(f'완료 후 임시 MP4 SHA 불일치로 보존했습니다: {stage}')
                os.unlink(stage)
            target = os.path.abspath(os.path.join(root, str(row.get('target_path') or '')))
            if (os.path.commonpath([root, target]) != root or os.path.realpath(target) != target):
                raise DownloadSafetyError(f'완료 후 MP4 결과 경로가 작업 루트 밖입니다: {target}')
            if target not in preserve and os.path.lexists(target):
                if (not os.path.isfile(target) or not row.get('sha256')
                        or os.path.getsize(target) != int(row.get('size', -1))
                        or sha256_file(target) != row.get('sha256')):
                    raise DownloadSafetyError(f'완료 후 MP4 결과가 소유 SHA와 달라 보존했습니다: {target}')
            elif target in preserve:
                if (not os.path.isfile(target) or os.path.islink(target)
                        or not row.get('sha256')
                        or os.path.getsize(target) != int(row.get('size', -1))
                        or sha256_file(target) != row.get('sha256')):
                    raise DownloadSafetyError(f'기록된 최종 MP4가 소유 SHA와 달라 보존했습니다: {target}')
        os.unlink(path)


def quarantine_unjournaled_mp4(root, task_id, input_paths, target_path):
    """Preserve a legacy task-local MP4 orphan without letting it block a retry."""
    root = os.path.realpath(os.fspath(root))
    task_id = str(task_id or '')
    target = os.path.abspath(os.fspath(target_path))
    if not task_id or not os.path.lexists(target):
        return None
    if os.path.islink(target) or not os.path.isfile(target):
        raise DownloadSafetyError(f'기존 MP4 출력이 일반 파일이 아니어서 보존했습니다: {target}')
    work_components = {f'.{task_id}.ytdlp', f'.{task_id}.ytdlp-home'}

    def owned_work_dir(path):
        absolute = os.path.abspath(os.fspath(path))
        if os.path.commonpath([root, absolute]) != root or os.path.realpath(absolute) != absolute:
            return None
        relative = os.path.relpath(absolute, root)
        parts = relative.split(os.sep)
        for index, part in enumerate(parts[:-1]):
            if part in work_components:
                return os.path.join(root, *parts[:index + 1])
        return None

    home = owned_work_dir(target)
    input_homes = [owned_work_dir(path) for path in input_paths]
    if not home or not any(input_homes):
        raise OutputCollision(
            f'기존 MP4가 작업 ID/입력 경로로 결속되지 않아 보존했습니다: {target}'
        )
    quarantine_dir = os.path.join(home, '.teddy-unverified-mp4')
    if os.path.lexists(quarantine_dir) and (os.path.islink(quarantine_dir) or not os.path.isdir(quarantine_dir)):
        raise DownloadSafetyError(f'미검증 MP4 보관 경로가 안전하지 않습니다: {quarantine_dir}')
    os.makedirs(quarantine_dir, mode=0o700, exist_ok=True)
    if os.path.realpath(quarantine_dir) != quarantine_dir:
        raise DownloadSafetyError(f'미검증 MP4 보관 경로가 작업 디렉터리 밖을 가리킵니다: {quarantine_dir}')

    prefix = hashlib.sha256(os.path.basename(target).encode('utf-8')).hexdigest()[:16]
    orphan = None
    for name in os.listdir(quarantine_dir):
        if not name.startswith(f'orphan-{prefix}-') or name.endswith('.json'):
            continue
        candidate = os.path.join(quarantine_dir, name)
        if not os.path.islink(candidate) and os.path.isfile(candidate) and os.path.samefile(target, candidate):
            orphan = candidate
            break
    if orphan is None:
        orphan = os.path.join(quarantine_dir, f'orphan-{prefix}-{uuid.uuid4().hex}.bin')
        try:
            os.link(target, orphan)
        except OSError as exc:
            raise DownloadSafetyError(f'미검증 MP4를 보존 경로로 원자 분리할 수 없습니다: {exc}') from exc
    if not os.path.samefile(target, orphan):
        raise DownloadSafetyError('미검증 MP4 보관 사본이 원본 inode와 달라 원본을 보존했습니다.')
    file_record = _relative_file_record(root, orphan)
    manifest_path = orphan + '.json'
    manifest = {
        'schema': 1,
        'task_id': task_id,
        'reason': 'legacy_mp4_without_completion_journal',
        'original_path': os.path.relpath(target, root),
        'quarantine_path': file_record['path'],
        'size': file_record['size'],
        'sha256': file_record['sha256'],
        'input_paths': [os.path.relpath(os.path.abspath(os.fspath(path)), root) for path in input_paths],
        'created_ns': time.time_ns(),
    }
    if os.path.exists(manifest_path):
        with open(manifest_path, 'r', encoding='utf-8') as stream:
            old = json.load(stream)
        if old != manifest:
            # A retry may have reached the same inode but generated a later
            # timestamp; validate the identity fields and retain the first record.
            if any(old.get(key) != manifest.get(key) for key in (
                'task_id', 'original_path', 'quarantine_path', 'size', 'sha256',
            )):
                raise DownloadSafetyError('기존 미검증 MP4 보관 기록이 다른 파일을 가리킵니다.')
    else:
        _atomic_write_json(manifest_path, manifest, no_clobber=True)
    if os.path.samefile(target, orphan):
        os.unlink(target)
        for directory in (os.path.dirname(target), quarantine_dir):
            directory_fd = os.open(directory, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    return manifest


def _inherit_mp4_lock(kwargs):
    fds = {
        int(fd) for fd in (
            _CURRENT_MP4_LOCK_FD.get(),
            _CURRENT_SPACE_LEASE_FD.get(),
        ) if fd is not None
    }
    if not fds:
        return kwargs
    copied = dict(kwargs)
    pass_fds = set(copied.get('pass_fds') or ())
    pass_fds.update(fds)
    copied['pass_fds'] = tuple(sorted(pass_fds))
    copied['close_fds'] = True
    return copied


def run_process_interruptibly(args, *, cancel_check, popen_factory=subprocess.Popen,
                              timeout=None, poll_seconds=0.2, terminate_seconds=2.0,
                              progress_check=None,
                              **kwargs):
    """Run one child in its own process group and stop/reap it on pause/cancel."""
    if os.name != 'posix':
        raise DownloadSafetyError('FFmpeg 일시정지 보호는 POSIX 프로세스 그룹이 필요합니다.')
    cancel_check()
    if progress_check:
        progress_check()
    kwargs = _inherit_mp4_lock(kwargs)
    kwargs['start_new_session'] = True
    started = time.monotonic()
    process = popen_factory(args, **kwargs)
    try:
        while True:
            try:
                cancel_check()
                if progress_check:
                    progress_check()
            except BaseException:
                _terminate_process_group(process, grace_seconds=terminate_seconds)
                raise
            remaining = None if timeout is None else max(0.0, timeout - (time.monotonic() - started))
            if remaining == 0:
                _terminate_process_group(process, grace_seconds=terminate_seconds)
                raise subprocess.TimeoutExpired(args, timeout)
            wait_seconds = max(0.01, float(poll_seconds))
            if remaining is not None:
                wait_seconds = min(wait_seconds, remaining)
            try:
                stdout, stderr = process.communicate(timeout=wait_seconds)
                cancel_check()
                return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
            except subprocess.TimeoutExpired:
                continue
    except BaseException:
        _terminate_process_group(process, grace_seconds=terminate_seconds)
        raise


def _run_ytdlp_popen_interruptibly(popen_cls, args, *, timeout=None, input=None,
                                  cancel_check, poll_seconds=0.2, terminate_seconds=2.0,
                                  progress_check=None,
                                  **kwargs):
    """Equivalent to yt-dlp Popen.run for the signature used by FFmpeg PP."""
    if input is not None and kwargs.get('stdin') is None:
        kwargs['stdin'] = subprocess.PIPE
    text_mode = bool(
        kwargs.get('encoding') or kwargs.get('errors') or kwargs.get('text')
        or kwargs.get('universal_newlines')
    )
    if os.name != 'posix':
        raise DownloadSafetyError('yt-dlp FFmpeg 일시정지 보호는 POSIX 프로세스 그룹이 필요합니다.')
    cancel_check()
    if progress_check:
        progress_check()
    kwargs = _inherit_mp4_lock(kwargs)
    kwargs['start_new_session'] = True
    started = time.monotonic()
    process = popen_cls(*args, **kwargs)
    try:
        while True:
            try:
                cancel_check()
                if progress_check:
                    progress_check()
            except BaseException:
                _terminate_process_group(process, grace_seconds=terminate_seconds)
                raise
            remaining = None if timeout is None else max(0.0, timeout - (time.monotonic() - started))
            if remaining == 0:
                _terminate_process_group(process, grace_seconds=terminate_seconds)
                raise subprocess.TimeoutExpired(args[0] if args else '', timeout)
            wait_seconds = max(0.01, float(poll_seconds))
            if remaining is not None:
                wait_seconds = min(wait_seconds, remaining)
            try:
                stdout, stderr = process.communicate(input=input, timeout=wait_seconds)
                input = None
                cancel_check()
                empty = '' if text_mode else b''
                return stdout or empty, stderr or empty, process.returncode
            except subprocess.TimeoutExpired:
                input = None
                continue
    except BaseException:
        _terminate_process_group(process, grace_seconds=terminate_seconds)
        raise


def is_enospc(error):
    seen = set()
    current = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if getattr(current, 'errno', None) == errno.ENOSPC:
            return True
        text = str(current).lower()
        if 'enospc' in text or 'no space left on device' in text or 'errno 28' in text:
            return True
        current = getattr(current, '__cause__', None) or getattr(current, '__context__', None)
    return False


def is_storage_error(error):
    if isinstance(error, StorageSpaceError) or is_enospc(error):
        return True
    current = error
    seen = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if '저장 공간 부족' in str(current):
            return True
        current = getattr(current, '__cause__', None) or getattr(current, '__context__', None)
    return False


def failure_kind(error):
    if is_storage_error(error):
        return 'storage'
    if isinstance(error, DownloadSafetyError):
        return 'safety'
    return ''


def atomic_publish_noclobber(source, destination):
    """Atomically expose a completed same-filesystem output without overwriting."""
    source = os.path.abspath(os.fspath(source))
    destination = os.path.abspath(os.fspath(destination))
    if not os.path.isfile(source) or os.path.getsize(source) <= 0:
        raise DownloadSafetyError(f'완료 파일 검증 실패: {source}')
    try:
        os.link(source, destination)
    except FileExistsError as exc:
        raise OutputCollision(f'기존 완료 파일을 덮어쓰지 않습니다: {destination}') from exc
    except OSError as exc:
        raise DownloadSafetyError(f'완료 파일 원자 확정 실패: {exc}') from exc
    try:
        directory_fd = os.open(os.path.dirname(destination) or '.', os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        raise DownloadSafetyError(f'완료 파일 디렉터리 동기화 실패: {exc}') from exc
    try:
        os.unlink(source)
    except OSError:
        # The destination is already atomically linked and durable. Keeping the
        # second name is safer than reporting failure after publication.
        pass
    return destination


def _ffmpeg_path_options_bytes(path_options, label):
    """Return (paths, bytes) from yt-dlp's (path, opts) FFmpeg input/output pairs."""
    if not isinstance(path_options, (list, tuple)):
        raise DownloadSafetyError(f'FFmpeg {label} 경로 구조를 확인할 수 없습니다.')
    paths = []
    total = 0
    for item in path_options:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise DownloadSafetyError(f'FFmpeg {label} 행 구조를 확인할 수 없습니다.')
        raw_path, _options = item
        if not raw_path:
            continue
        path = os.fspath(raw_path)
        if path.startswith(('http://', 'https://', 'pipe:', 'concat:')):
            raise DownloadSafetyError(f'FFmpeg {label} 크기를 확인할 수 없습니다: {path}')
        paths.append(path)
        if label == '입력':
            try:
                if not os.path.isfile(path):
                    raise OSError(f'입력 파일이 없습니다: {path}')
                total += os.path.getsize(path)
            except OSError as exc:
                raise DownloadSafetyError(f'FFmpeg 입력 크기를 확인할 수 없습니다: {path}: {exc}') from exc
    if not paths:
        raise DownloadSafetyError(f'FFmpeg {label} 파일을 확인할 수 없어 공간을 검증하지 못했습니다.')
    return paths, total


def ffmpeg_task_id(root, input_path_opts, output_path_opts):
    root = os.path.realpath(os.fspath(root))
    candidates = []
    for path_options in (input_path_opts, output_path_opts):
        if isinstance(path_options, (list, tuple)):
            for item in path_options:
                if isinstance(item, (list, tuple)) and len(item) == 2 and item[0]:
                    candidates.append(os.fspath(item[0]))
    for raw_path in candidates:
        if raw_path.startswith(('http://', 'https://', 'pipe:', 'concat:')):
            continue
        absolute = os.path.realpath(raw_path)
        try:
            relative = os.path.relpath(absolute, root)
        except ValueError:
            continue
        if relative == os.pardir or relative.startswith(os.pardir + os.sep):
            continue
        for component in relative.split(os.sep):
            if component.startswith('.') and component.endswith('.ytdlp-home'):
                return component[1:-len('.ytdlp-home')]
    return ''


def _remove_failed_mp4_outputs(paths, existed_before, root):
    """Remove only newly-created partial MP4 files inside the task work root."""
    root = os.path.realpath(os.fspath(root))
    for path in paths:
        absolute = os.path.abspath(os.fspath(path))
        if existed_before.get(absolute):
            continue
        if not os.path.lexists(absolute) or os.path.islink(absolute) or not os.path.isfile(absolute):
            continue
        parent = os.path.realpath(os.path.dirname(absolute) or '.')
        try:
            if os.path.commonpath([root, parent]) != root:
                continue
        except ValueError:
            continue
        try:
            os.unlink(absolute)
            directory_fd = os.open(parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            # The incomplete output remains untrusted; source inputs are untouched.
            pass


def install_ytdlp_ffmpeg_guard(core):
    """Guard yt-dlp's real FFmpeg invocation without changing its arguments/settings."""
    try:
        from yt_dlp.postprocessor import ffmpeg as ffmpeg_module
        FFmpegPostProcessor = ffmpeg_module.FFmpegPostProcessor
        popen_cls = ffmpeg_module.Popen
    except Exception as exc:
        raise DownloadSafetyError(f'yt-dlp FFmpeg 보호기를 설치할 수 없습니다: {exc}') from exc

    original = FFmpegPostProcessor.real_run_ffmpeg
    if getattr(original, '_teddy_global_remux_guard', False):
        installed_popen_run = popen_cls.run
        if getattr(installed_popen_run, '_teddy_interruptible_ffmpeg', False):
            return False
        raise DownloadSafetyError(
            'yt-dlp FFmpeg 보호기가 일부만 설치되어 상태를 확인할 수 없습니다.'
        )
    try:
        signature = inspect.signature(original)
        if not {'self', 'input_path_opts', 'output_path_opts'}.issubset(signature.parameters):
            raise TypeError(f'unexpected signature: {signature}')
        signature.bind(None, [], [])
        implementation = inspect.getsource(original)
        if 'Popen.run(' not in implementation:
            raise TypeError('real_run_ffmpeg no longer exposes the verified Popen.run child boundary')
    except (TypeError, ValueError) as exc:
        raise DownloadSafetyError(
            f'yt-dlp FFmpeg 호출 규약이 검증되지 않아 보호기를 설치하지 못했습니다: {exc}'
        ) from exc

    if not inspect.isclass(popen_cls) or not issubclass(popen_cls, subprocess.Popen):
        raise DownloadSafetyError('yt-dlp FFmpeg Popen 구현을 검증할 수 없어 실행을 차단했습니다.')
    original_popen_run = popen_cls.run
    if not getattr(original_popen_run, '_teddy_interruptible_ffmpeg', False):
        try:
            popen_signature = inspect.signature(original_popen_run)
            if not {'timeout', 'input'}.issubset(popen_signature.parameters):
                raise TypeError(f'unexpected Popen.run signature: {popen_signature}')
            popen_signature.bind(timeout=None, input=None)
        except (TypeError, ValueError) as exc:
            raise DownloadSafetyError(
                f'yt-dlp Popen.run 규약이 검증되지 않아 FFmpeg를 실행하지 않습니다: {exc}'
            ) from exc

        def guarded_popen_run(cls, *args, timeout=None, input=None, **kwargs):
            kwargs = _inherit_mp4_lock(kwargs)
            cancel_check = _CURRENT_FFMPEG_CANCEL_CHECK.get()
            if cancel_check is None:
                return original_popen_run(*args, timeout=timeout, input=input, **kwargs)
            transaction = _CURRENT_REMUX_TRANSACTION.get()
            return _run_ytdlp_popen_interruptibly(
                cls,
                args,
                timeout=timeout,
                input=input,
                cancel_check=cancel_check,
                progress_check=(transaction.refresh_output_reservation if transaction else None),
                **kwargs,
            )

        guarded_popen_run._teddy_interruptible_ffmpeg = True
        guarded_popen_run._teddy_original = original_popen_run
        popen_cls.run = classmethod(guarded_popen_run)
    elif getattr(original, '_teddy_global_remux_guard', False):
        return False

    def guarded_real_run_ffmpeg(self, input_path_opts, output_path_opts, *args, **kwargs):
        outputs, _ = _ffmpeg_path_options_bytes(output_path_opts, '출력')
        mp4_outputs = [path for path in outputs if os.path.splitext(path)[1].lower() == '.mp4']
        if not mp4_outputs:
            return original(self, input_path_opts, output_path_opts, *args, **kwargs)

        input_paths, input_bytes = _ffmpeg_path_options_bytes(input_path_opts, '입력')
        input_abs = {os.path.abspath(path) for path in input_paths}
        required = estimated_remux_output_bytes(input_bytes) * len(mp4_outputs)
        task_id = _CURRENT_TASK_ID.get() or ffmpeg_task_id(core.DOWNLOAD_DIR, input_path_opts, output_path_opts)
        if not task_id:
            raise DownloadSafetyError('MP4 변환 작업 ID를 확인할 수 없어 충돌/복구 보호를 적용하지 못했습니다.')
        base_input_records = current_task_inputs()
        if base_input_records is None:
            base_input_records = [_relative_file_record(core.DOWNLOAD_DIR, path) for path in input_paths]
        reservation = _CURRENT_RESERVATION.get()
        if reservation is not None:
            reservation.update(0)

        def cancel_check():
            task = core.tasks.get(task_id)
            if not task or task.get('status') == '취소됨':
                raise core.DownloadCancelled()
            if task.get('status') in ('일시정지 요청 중', '일시정지'):
                raise TaskPauseRequested('yt-dlp MP4 처리 일시정지 요청')

        root = os.path.realpath(core.DOWNLOAD_DIR)
        attempt = None
        try:
            with RemuxTransaction(
                root,
                output_path=os.path.dirname(os.path.abspath(mp4_outputs[0])) or root,
                required_output_bytes=required,
                cancel_check=cancel_check,
            ) as remux_transaction:
                # The FFmpeg child inherits the flock fd. If its parent is
                # force-killed, a new converter cannot start until the child
                # exits and releases its inherited descriptor.
                recover_mp4_attempts(root, task_id, base_input_records, allow_complete=False)
                for path in mp4_outputs:
                    absolute = os.path.abspath(path)
                    if os.path.lexists(absolute) and absolute not in input_abs:
                        quarantine_unjournaled_mp4(root, task_id, input_paths, absolute)
                        if os.path.lexists(absolute):
                            raise OutputCollision(f'검증되지 않은 기존 MP4를 안전하게 격리하지 못했습니다: {absolute}')
                attempt = begin_mp4_attempt(root, task_id, input_paths, mp4_outputs, base_input_records)
                staged_opts = []
                for path, opts in output_path_opts:
                    absolute = os.path.abspath(os.fspath(path)) if path else ''
                    staged_opts.append((attempt['stage_map'].get(absolute, path), opts))
                remux_transaction.set_output_paths([
                    path for path, _opts in staged_opts
                    if os.path.splitext(os.fspath(path))[1].lower() == '.mp4'
                ])
                token = _CURRENT_FFMPEG_CANCEL_CHECK.set(cancel_check)
                try:
                    result = original(self, input_path_opts, staged_opts, *args, **kwargs)
                    cancel_check()
                    complete_mp4_attempt_outputs(root, attempt)
                    update_mp4_attempt(attempt, 'ffmpeg_complete')
                    commit_mp4_attempt_outputs(root, attempt)
                    return result
                finally:
                    _CURRENT_FFMPEG_CANCEL_CHECK.reset(token)
        except Exception as exc:
            if attempt is not None:
                recovery_lock = InterProcessFileLock(mp4_lock_path(root))
                try:
                    recovery_lock.acquire()
                    recover_mp4_attempts(root, task_id, base_input_records, allow_complete=False)
                except Exception as cleanup_exc:
                    print(f'[MP4 recovery] 임시 출력 보존: {cleanup_exc}', flush=True)
                finally:
                    if recovery_lock.acquired:
                        recovery_lock.release()
            if is_enospc(exc):
                output_dir = os.path.dirname(os.path.abspath(mp4_outputs[0])) or core.DOWNLOAD_DIR
                usage = shutil.disk_usage(output_dir)
                raise StorageSpaceError(
                    output_dir,
                    usage.free,
                    required,
                    reserve_bytes(usage.total),
                ) from exc
            raise

    guarded_real_run_ffmpeg._teddy_global_remux_guard = True
    guarded_real_run_ffmpeg._teddy_original = original
    FFmpegPostProcessor.real_run_ffmpeg = guarded_real_run_ffmpeg
    return True


def cleanup_parts_after_verified_publish(core, task_id):
    """Delete only the task's recorded HLS fragments after publisher marks success."""
    task = core.tasks.get(task_id)
    if not task or task.get('status') != '완료':
        return False
    if task.get('teddy_legacy_ts_preserve_source'):
        # Manual TS recovery never authorizes deletion of older loose HLS parts.
        return False
    if task.get('local_result_path') or task.get('local_result_paths'):
        return False
    relative = str(task.get('hls_parts_path') or '').strip()
    if not relative:
        return False
    root = os.path.realpath(core.DOWNLOAD_DIR)
    if os.path.isabs(relative) or relative in ('.', '..') or os.path.basename(relative) != relative:
        return False
    candidate = os.path.abspath(os.path.join(root, relative))
    try:
        if os.path.commonpath([root, candidate]) != root:
            return False
    except ValueError:
        return False
    name = os.path.basename(candidate)
    if not (name.startswith('.') and name.endswith('.parts')):
        return False
    if candidate == root or os.path.islink(candidate) or not os.path.isdir(candidate):
        return False
    try:
        for walk_root, dirs, files in os.walk(candidate, followlinks=False):
            entries = list(os.scandir(walk_root))
            if any(entry.is_symlink() for entry in entries):
                return False
    except OSError:
        return False
    try:
        shutil.rmtree(candidate)
    except OSError:
        return False
    if os.path.exists(candidate):
        return False
    task.pop('hls_parts_path', None)
    core.save_tasks()
    return True
