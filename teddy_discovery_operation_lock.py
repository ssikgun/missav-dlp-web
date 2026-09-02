from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import errno
import fcntl


DEFAULT_OPERATION_LOCK_PATH = Path(
    "/run/lock/teddy-discovery-jav-library-operation.lock"
)


class OperationLockError(RuntimeError):
    pass


class OperationLockBusy(OperationLockError):
    pass


@contextmanager
def operation_lock(path=DEFAULT_OPERATION_LOCK_PATH):
    lock_path = Path(path)

    try:
        lock_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        handle = lock_path.open(
            "a+",
            encoding="utf-8",
        )
    except OSError as exc:
        raise OperationLockError(
            "unable to open operation lock: "
            + str(lock_path)
        ) from exc

    acquired = False

    try:
        try:
            fcntl.flock(
                handle.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
            acquired = True

        except OSError as exc:
            if exc.errno in {
                errno.EACCES,
                errno.EAGAIN,
            }:
                raise OperationLockBusy(
                    "operation lock is busy: "
                    + str(lock_path)
                ) from exc

            raise OperationLockError(
                "unable to acquire operation lock: "
                + str(lock_path)
            ) from exc

        yield

    finally:
        if acquired:
            fcntl.flock(
                handle.fileno(),
                fcntl.LOCK_UN,
            )

        handle.close()
