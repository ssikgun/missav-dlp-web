"""Offline tests for process-shared, non-blocking DVD-ID flock exclusion."""
from __future__ import annotations

import multiprocessing
import os
from pathlib import Path
import tempfile

from teddy_title_exclusion import (
    ACQUIRED, BUSY, UNAVAILABLE, try_acquire_title_lock,
)


def _hold(root: str, dvd_id: str, ready, release) -> None:
    attempt = try_acquire_title_lock(dvd_id, root)
    ready.put(attempt.status)
    if attempt.status == ACQUIRED:
        release.wait(10)
        attempt.release()


def _attempt(root: str, dvd_id: str, output) -> None:
    attempt = try_acquire_title_lock(dvd_id, root)
    output.put(attempt.status)
    attempt.release()


def main() -> None:
    context = multiprocessing.get_context("fork")
    with tempfile.TemporaryDirectory(prefix="title-exclusion-") as temp:
        root = Path(temp) / "locks"
        root.mkdir(mode=0o750)

        # Distinct processes contend on the same DVD-ID lock inode.
        ready = context.Queue()
        release = context.Event()
        holder = context.Process(target=_hold, args=(str(root), "ADN-785", ready, release))
        holder.start()
        assert ready.get(timeout=3) == ACQUIRED
        result = context.Queue()
        contender = context.Process(target=_attempt, args=(str(root), "ADN-785", result))
        contender.start()
        assert result.get(timeout=3) == BUSY
        contender.join(timeout=3)
        assert contender.exitcode == 0

        # Different DVD-ID locks remain concurrently acquirable.
        other = try_acquire_title_lock("SONE-978", root)
        assert other.status == ACQUIRED
        other.release()

        # A dead process releases kernel flock ownership; the lock file may
        # remain and is deliberately not treated as an owner marker.
        holder.terminate()
        holder.join(timeout=3)
        assert holder.exitcode is not None
        reclaimed = try_acquire_title_lock("ADN-785", root)
        assert reclaimed.status == ACQUIRED
        reclaimed.release()

        # Normal context/exception exit also releases the descriptor.
        try:
            with try_acquire_title_lock("JUR-750", root) as attempt:
                assert attempt.status == ACQUIRED
                raise RuntimeError("fixture")
        except RuntimeError:
            pass
        released = try_acquire_title_lock("JUR-750", root)
        assert released.status == ACQUIRED
        released.release()

        assert try_acquire_title_lock("../ADN-785", root).status == UNAVAILABLE
        assert try_acquire_title_lock("ADN-785", None).status == UNAVAILABLE
        assert try_acquire_title_lock("ADN-785", str(root) + "/../locks").status == UNAVAILABLE

        symlink_root = Path(temp) / "link-root"
        symlink_root.symlink_to(root, target_is_directory=True)
        assert try_acquire_title_lock("ADN-785", symlink_root).status == UNAVAILABLE

        symlink_file_root = Path(temp) / "symlink-file-root"
        symlink_file_root.mkdir(mode=0o750)
        (symlink_file_root / "HMN-899.lock").symlink_to(root / "ADN-785.lock")
        assert try_acquire_title_lock("HMN-899", symlink_file_root).status == UNAVAILABLE

        unsafe_root = Path(temp) / "world-writable"
        unsafe_root.mkdir(mode=0o777)
        os.chmod(unsafe_root, 0o777)
        assert try_acquire_title_lock("ADN-785", unsafe_root).status == UNAVAILABLE

    print("TITLE_EXCLUSION_PROCESS_FLOCK=PASS")
    print("SAME_TITLE=BUSY_OTHER_PROCESS")
    print("DIFFERENT_TITLE=PARALLEL")
    print("CRASH_RELEASE=PASS")
    print("ROOT_FILE_SAFETY=PASS")


if __name__ == "__main__":
    main()
