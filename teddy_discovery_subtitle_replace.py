"""Explicit SHA-bound replacement, separate from the no-overwrite publisher."""
from dataclasses import dataclass
import inspect
import json
import re
import shlex
import subprocess

from teddy_discovery_subtitle import derive_target_ko_relative
from teddy_discovery_subtitle_publish import (
    _validated_artifact, _validated_canonical_video,
    SubtitlePublishValidationError, SubtitlePublishTransportError,
)


@dataclass(frozen=True)
class ReplacementWitness:
    sha256: str
    source_size_bytes: int
    source_mtime_ns: int

    def __post_init__(self):
        if type(self.sha256) is not str or re.fullmatch('[0-9a-f]{64}', self.sha256) is None:
            raise SubtitlePublishValidationError('invalid replacement SHA witness')
        if (type(self.source_size_bytes) is not int or self.source_size_bytes <= 0
                or type(self.source_mtime_ns) is not int or self.source_mtime_ns < 0):
            raise SubtitlePublishValidationError('invalid replacement source witness')


def replacement_worker(root, video_relative, target_relative, action, old_sha, new_sha,
                       operation_id, payload, checkpoint=None, expected_source_size=None, expected_source_mtime=None):
    """Linux native atomic exchange; displaced bytes stay private until verified.

    This function is self-contained so the SSH bridge executes the same code.
    A process crash leaves the displaced old file at the operation's temp name.
    Retry verifies that backup before cleanup. A detected exchange race is
    rolled back only while both exchanged inode identities remain unchanged.
    """
    import ctypes
    import fcntl
    import hashlib
    import os
    import re
    import stat
    from pathlib import PurePosixPath

    def fail():
        raise ValueError('unsafe replacement witness or operation')

    def digest(data):
        return hashlib.sha256(data).hexdigest()

    def key(info):
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    def safe_fd(name, directory):
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            os.close(fd)
            fail()
        return fd

    def read(name, directory, limit):
        fd = safe_fd(name, directory)
        try:
            before = os.fstat(fd)
            if not 0 < before.st_size <= limit:
                fail()
            data = b''
            while len(data) <= limit:
                block = os.read(fd, min(65536, limit + 1 - len(data)))
                if not block:
                    break
                data += block
            if len(data) != before.st_size or key(before) != key(os.fstat(fd)):
                fail()
            after_path = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if key(after_path) != key(before):
                fail()
            return data, before
        finally:
            os.close(fd)

    def directory(path):
        parts = PurePosixPath(path).parts
        if not parts or '..' in parts:
            fail()
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        try:
            for part in parts:
                if part == '/':
                    continue
                next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = next_fd
            return fd
        except BaseException:
            os.close(fd)
            raise

    root_parts = PurePosixPath(root)
    video = PurePosixPath(video_relative)
    target = PurePosixPath(target_relative)
    if (not root_parts.is_absolute() or video.is_absolute() or target.is_absolute()
            or '..' in video.parts or '..' in target.parts or video.parent != target.parent
            or target.name != video.parent.name + '.ko.srt'):
        fail()
    if action not in ('inspect', 'replace', 'reconcile'):
        fail()
    parent = directory(str(root_parts / target.parent))
    lock_fd = None
    temp = None
    created = False
    exchanged = False
    try:
        video_fd = safe_fd(video.name, parent)
        try:
            video_info = os.fstat(video_fd)
        finally:
            os.close(video_fd)
        def verify_parent_and_video():
            reopened = directory(str(root_parts / target.parent))
            try:
                actual, held = os.fstat(reopened), os.fstat(parent)
                if (actual.st_dev, actual.st_ino) != (held.st_dev, held.st_ino):
                    fail()
            finally:
                os.close(reopened)
            media_fd = safe_fd(video.name, parent)
            try:
                if key(os.fstat(media_fd)) != key(video_info):
                    fail()
            finally:
                os.close(media_fd)
        if action != 'inspect' and expected_source_size is not None:
            if video_info.st_size != expected_source_size or video_info.st_mtime_ns != expected_source_mtime:
                fail()
        current, old_info = read(target.name, parent, 8 * 1024 * 1024)
        if action == 'inspect':
            return dict(sha256=digest(current), source_size_bytes=video_info.st_size,
                        source_mtime_ns=video_info.st_mtime_ns)
        if (any(re.fullmatch('[0-9a-f]{64}', v or '') is None for v in (old_sha, new_sha, operation_id))
                or old_sha == new_sha or type(payload) is not bytes
                or not 0 < len(payload) <= 8 * 1024 * 1024 or digest(payload) != new_sha):
            fail()
        # Canonical bounded SRT is validated by the caller before this transport.
        # This independent boundary verifies exact UTF-8 and payload identity.
        payload.decode('utf-8', errors='strict')
        lock_name = '.' + target.name + '.replacement.lock'
        lock_fd = os.open(lock_name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        lock_info = os.fstat(lock_fd)
        if not stat.S_ISREG(lock_info.st_mode) or lock_info.st_nlink != 1 or stat.S_IMODE(lock_info.st_mode) != 0o600:
            fail()
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        current, old_info = read(target.name, parent, 8 * 1024 * 1024)
        temp = '.' + target.name + '.replacement-' + operation_id
        def finish_permissions(expected_inode, old_mode):
            descriptor = safe_fd(target.name, parent)
            try:
                if os.fstat(descriptor).st_ino != expected_inode:
                    fail()
                # Keep the old subtitle's read access without propagating
                # executable or group/world writable permission bits.
                os.fchmod(descriptor, 0o600 | (old_mode & 0o044))
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        if digest(current) == new_sha:
            try:
                backup, backup_info = read(temp, parent, 8 * 1024 * 1024)
            except FileNotFoundError:
                backup_info = None
            else:
                if digest(backup) != old_sha:
                    fail()
            verify_parent_and_video()
            finish_permissions(old_info.st_ino, backup_info.st_mode if backup_info else old_info.st_mode)
            final_check, _ = read(target.name,parent,8 * 1024 * 1024)
            if final_check != payload:
                fail()
            if backup_info is not None:
                backup_check, backup_now = read(temp,parent,8 * 1024 * 1024)
                if backup_check != backup or backup_now.st_ino != backup_info.st_ino:
                    fail()
                os.unlink(temp, dir_fd=parent)
            os.fsync(parent)
            verify_parent_and_video()
            return dict(sha256=new_sha, replaced=False)
        if action == 'reconcile':
            fail()
        if digest(current) != old_sha:
            fail()
        try:
            fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                         0o600, dir_fd=parent)
        except FileExistsError:
            temp_data, temp_info = read(temp, parent, 8 * 1024 * 1024)
            if temp_data != payload or stat.S_IMODE(temp_info.st_mode) != 0o600:
                fail()
        else:
            created = True
            try:
                view = memoryview(payload)
                while view:
                    written = os.write(fd, view)
                    if written <= 0:
                        fail()
                    view = view[written:]
                os.fsync(fd)
            finally:
                os.close(fd)
        temp_data, temp_info = read(temp, parent, 8 * 1024 * 1024)
        if temp_data != payload or digest(temp_data) != new_sha:
            fail()
        if checkpoint:
            checkpoint('before_exchange')
        temp_check, temp_check_info = read(temp, parent, 8 * 1024 * 1024)
        if temp_check != payload or key(temp_check_info) != key(temp_info):
            fail()
        current_check, current_info = read(target.name, parent, 8 * 1024 * 1024)
        if current_check != current or key(current_info) != key(old_info):
            fail()
        verify_parent_and_video()
        libc = ctypes.CDLL(None, use_errno=True)
        exchange = getattr(libc, 'renameat2', None)
        if exchange is None:
            fail()  # Never fall back to deleting the old target or a non-atomic install.
        def swap():
            if exchange(parent, temp.encode(), parent, target.name.encode(), 2) != 0:
                raise OSError(ctypes.get_errno(), 'atomic exchange failed')
        swap()
        exchanged = True
        os.fsync(parent)
        displaced, displaced_info = read(temp, parent, 8 * 1024 * 1024)
        installed, installed_info = read(target.name, parent, 8 * 1024 * 1024)
        # rename changes ctime, so compare inode identity plus exact bytes here.
        if (displaced != current or (displaced_info.st_dev, displaced_info.st_ino, displaced_info.st_size, displaced_info.st_mtime_ns)
                != (old_info.st_dev, old_info.st_ino, old_info.st_size, old_info.st_mtime_ns)
                or installed != payload or installed_info.st_ino != temp_info.st_ino):
            # Preserve both sides unless a rollback is still proven safe.
            if (installed_info.st_ino == temp_info.st_ino and installed == payload
                    and key(os.stat(temp, dir_fd=parent, follow_symlinks=False)) == key(displaced_info)
                    and key(os.stat(target.name, dir_fd=parent, follow_symlinks=False)) == key(installed_info)):
                swap()
                os.fsync(parent)
                exchanged = False
            fail()
        if checkpoint:
            checkpoint('after_exchange')
        finish_permissions(installed_info.st_ino, old_info.st_mode)
        final, _ = read(target.name, parent, 8 * 1024 * 1024)
        if final != payload or digest(final) != new_sha:
            fail()
        verify_parent_and_video()
        backup_check, backup_info = read(temp, parent, 8 * 1024 * 1024)
        if backup_check != current or backup_info.st_ino != old_info.st_ino:
            fail()
        os.unlink(temp, dir_fd=parent)
        temp = None
        os.fsync(parent)
        return dict(sha256=new_sha, replaced=True)
    finally:
        # Never discard displaced old bytes after an unverified exchange.
        if temp is not None and created and not exchanged:
            try:
                os.unlink(temp, dir_fd=parent)
                os.fsync(parent)
            except FileNotFoundError:
                pass
        if lock_fd is not None:
            os.close(lock_fd)
        os.close(parent)


class SubtitleReplacementMutator:
    """Explicit operation; normal SubtitleSSHMutator has no overwrite option."""
    def __init__(self, ssh):
        from teddy_discovery_subtitle_publish import SubtitleSSHMutator
        self.transport = SubtitleSSHMutator(ssh)

    def _invoke(self, video, action, old_sha='', new_sha='', operation_id='', payload=b'', source_witness=None):
        base, runner, root = self.transport._transport_details()
        video = _validated_canonical_video(video)
        script = inspect.getsource(replacement_worker) + '''
import json,sys
try:
    args=sys.argv[1:]
    result=replacement_worker(*args[:7],payload=sys.stdin.buffer.read(8*1024*1024+1),
        expected_source_size=int(args[7]) if args[7] else None,
        expected_source_mtime=int(args[8]) if args[8] else None)
except Exception:
    print('{"status":"REJECTED"}')
    raise SystemExit(1)
print(json.dumps(result,sort_keys=True,separators=(",",":")))
'''
        command = 'python3 -c ' + shlex.quote(script) + ' ' + ' '.join(shlex.quote(v) for v in
            (root, video.relative_path, derive_target_ko_relative(video), action, old_sha, new_sha, operation_id,
             str(source_witness.source_size_bytes) if source_witness else '',
             str(source_witness.source_mtime_ns) if source_witness else ''))
        try:
            result = runner(base + [command], input=payload, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=False)
            if result.returncode != 0:
                raise SubtitlePublishTransportError('replacement remote operation rejected')
            if len(result.stdout) > 4096:
                raise ValueError()
            return json.loads(result.stdout)
        except SubtitlePublishTransportError:
            raise
        except Exception as error:
            raise SubtitlePublishTransportError('replacement transport failed') from error

    def inspect(self, video, destination):
        if destination != derive_target_ko_relative(video):
            raise SubtitlePublishValidationError('noncanonical replacement destination')
        value = self._invoke(video, 'inspect')
        if type(value) is not dict or set(value) != {'sha256','source_size_bytes','source_mtime_ns'}:
            raise SubtitlePublishValidationError('detached replacement witness')
        return ReplacementWitness(**value)

    def replace(self, video, artifact, *, expected_old_sha256, expected_new_sha256, operation_id, source_witness):
        if type(source_witness) is not ReplacementWitness or source_witness.sha256 != expected_old_sha256:
            raise SubtitlePublishValidationError('replacement requires exact source/old SHA witness')
        source_witness.__post_init__()
        validated = _validated_artifact(artifact)
        if validated is None or validated[2] != expected_new_sha256 or expected_old_sha256 == expected_new_sha256:
            raise SubtitlePublishValidationError('replacement artifact identity invalid')
        if any(type(v) is not str or re.fullmatch('[0-9a-f]{64}', v) is None
               for v in (expected_old_sha256, expected_new_sha256, operation_id)):
            raise SubtitlePublishValidationError('replacement requires exact old/new operation identity')
        value = self._invoke(video, 'replace', expected_old_sha256, expected_new_sha256, operation_id, validated[0], source_witness)
        if (type(value) is not dict or set(value) != {'sha256','replaced'}
                or value['sha256'] != expected_new_sha256 or type(value['replaced']) is not bool):
            raise SubtitlePublishValidationError('replacement read-back invalid')
        return value

    def reconcile(self, video, artifact, *, expected_old_sha256, expected_new_sha256, operation_id, source_witness):
        """New SHA only; verify/clean crash backup without exchanging the target."""
        validated = _validated_artifact(artifact)
        if (validated is None or validated[2] != expected_new_sha256
                or expected_old_sha256 == expected_new_sha256
                or type(source_witness) is not ReplacementWitness or source_witness.sha256 != expected_new_sha256
                or any(type(v) is not str or re.fullmatch('[0-9a-f]{64}', v) is None
                       for v in (expected_old_sha256,expected_new_sha256,operation_id))):
            raise SubtitlePublishValidationError('replacement reconciliation identity invalid')
        source_witness.__post_init__()
        value = self._invoke(video,'reconcile',expected_old_sha256,expected_new_sha256,operation_id,validated[0],source_witness)
        if value != {'sha256':expected_new_sha256,'replaced':False}:
            raise SubtitlePublishValidationError('replacement reconciliation witness invalid')
        return value
