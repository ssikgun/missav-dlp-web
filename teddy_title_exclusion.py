"""Non-blocking, process-shared exclusion for one canonical DVD-ID.

All participating processes must point TEDDY_TITLE_LOCK_DIR at the same
host-backed directory. Lock files carry no payload; flock ownership is held
only by the open file descriptor, so a stale file is harmless.
"""
from __future__ import annotations

from dataclasses import dataclass
import errno
import fcntl
import os
from pathlib import Path
import re
import stat

from teddy_discovery_ids import parse_dvd_id


ACQUIRED = "ACQUIRED"
BUSY = "BUSY"
UNAVAILABLE = "UNAVAILABLE"
_DVD_SAFE = re.compile(r"^[A-Z0-9][A-Z0-9-]{2,31}$")


class TitleLockError(RuntimeError):
    pass


def canonical_dvd_id(value: object) -> str:
    if type(value) is not str or not _DVD_SAFE.fullmatch(value):
        raise TitleLockError("invalid_dvd_id")
    parsed = parse_dvd_id(value)
    if parsed is None or parsed.dvd_id != value:
        raise TitleLockError("invalid_dvd_id")
    return value


def _validated_root(lock_dir: str | os.PathLike[str] | None) -> Path:
    if not isinstance(lock_dir, (str, os.PathLike)):
        raise TitleLockError("lock_root_unconfigured")
    raw = os.fspath(lock_dir)
    if not raw or not os.path.isabs(raw) or ".." in raw.split(os.sep):
        raise TitleLockError("lock_root_invalid")
    normalized = os.path.normpath(raw)
    if normalized != raw:
        raise TitleLockError("lock_root_invalid")
    root = Path(raw)
    current = Path(root.anchor)
    info = None
    try:
        for part in root.parts[1:]:
            current = current / part
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise TitleLockError("lock_root_invalid")
    except OSError as exc:
        raise TitleLockError("lock_root_unavailable") from exc
    if info is None:
        raise TitleLockError("lock_root_invalid")
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise TitleLockError("lock_root_invalid")
    if info.st_mode & stat.S_IWOTH:
        raise TitleLockError("lock_root_world_writable")
    return root


@dataclass
class TitleLockAttempt:
    status: str
    fd: int | None = None
    code: str | None = None

    @property
    def acquired(self) -> bool:
        return self.status == ACQUIRED and self.fd is not None

    def release(self) -> None:
        fd, self.fd = self.fd, None
        if fd is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def __enter__(self) -> "TitleLockAttempt":
        return self

    def __exit__(self, *_exc) -> None:
        self.release()


def try_acquire_title_lock(
    dvd_id: object,
    lock_dir: str | os.PathLike[str] | None = None,
) -> TitleLockAttempt:
    """Acquire a DVD-ID lock without waiting; errors are fail-closed."""
    try:
        canonical = canonical_dvd_id(dvd_id)
        root = _validated_root(lock_dir)
        lock_path = root / (canonical + ".lock")
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(lock_path, flags, 0o600)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            os.close(fd)
            return TitleLockAttempt(UNAVAILABLE, code="lock_file_invalid")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            if exc.errno in (errno.EACCES, errno.EAGAIN):
                return TitleLockAttempt(BUSY, code="title_busy")
            return TitleLockAttempt(UNAVAILABLE, code="lock_unavailable")
        return TitleLockAttempt(ACQUIRED, fd=fd)
    except (OSError, TitleLockError, ValueError, TypeError):
        return TitleLockAttempt(UNAVAILABLE, code="lock_unavailable")


def configured_lock_dir() -> str | None:
    return os.environ.get("TEDDY_TITLE_LOCK_DIR")


__all__ = [
    "ACQUIRED", "BUSY", "UNAVAILABLE", "TitleLockAttempt",
    "TitleLockError", "canonical_dvd_id", "configured_lock_dir",
    "try_acquire_title_lock",
]
