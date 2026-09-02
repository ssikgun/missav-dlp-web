from __future__ import annotations

import json
from pathlib import PurePosixPath

from teddy_discovery_completion_ssh import (
    CompletionSSH,
    CompletionSSHError,
)


class CompletionApplyError(RuntimeError):
    pass


def _safe_relative(value: str) -> str:
    raw = str(value or "").strip()
    path = PurePosixPath(raw)

    if (
        not raw
        or path.is_absolute()
        or ".." in path.parts
        or any(
            part in ("", ".")
            or part.startswith(".")
            or part == "@eaDir"
            for part in path.parts
        )
    ):
        raise CompletionApplyError(
            "unsafe relative path"
        )

    return path.as_posix()


class CompletionSSHMutator:
    def __init__(
        self,
        ssh: CompletionSSH,
    ):
        self.ssh = ssh

    def publish_to_library(
        self,
        *,
        source_relative: str,
        destination_relative: str,
        expected_size: int,
        expected_mtime_ns: int,
    ) -> dict:

        source_relative = _safe_relative(
            source_relative
        )
        destination_relative = _safe_relative(
            destination_relative
        )

        script = r'''
import json
import os
import shutil
import sys
import uuid

downloads_root = os.path.realpath(sys.argv[1])
library_root = os.path.realpath(sys.argv[2])
source_relative = sys.argv[3]
destination_relative = sys.argv[4]
expected_size = int(sys.argv[5])
expected_mtime_ns = int(sys.argv[6])


def inside(path, root):
    root_prefix = root.rstrip(os.sep) + os.sep
    return path == root or path.startswith(root_prefix)


source = os.path.join(
    downloads_root,
    source_relative,
)

source_real = os.path.realpath(
    source
)

if not inside(
    source_real,
    downloads_root,
):
    raise SystemExit("source escapes downloads root")

if (
    os.path.islink(source)
    or not os.path.isfile(source)
):
    raise SystemExit("source is not a regular file")

source_before = os.stat(
    source,
    follow_symlinks=False,
)

if (
    int(source_before.st_size)
    != expected_size
    or int(source_before.st_mtime_ns)
    != expected_mtime_ns
):
    raise SystemExit(
        "source changed before publish"
    )

destination = os.path.join(
    library_root,
    destination_relative,
)

destination_parent = os.path.dirname(
    destination
)

os.makedirs(
    destination_parent,
    exist_ok=True,
)

parent_real = os.path.realpath(
    destination_parent
)

if not inside(
    parent_real,
    library_root,
):
    raise SystemExit(
        "destination escapes library root"
    )

if os.path.exists(destination):
    raise SystemExit(
        "destination already exists"
    )

partial = os.path.join(
    destination_parent,
    "."
    + os.path.basename(destination)
    + ".teddy-stage9-"
    + uuid.uuid4().hex
    + ".partial",
)

published = False

try:
    with open(
        source,
        "rb",
    ) as src, open(
        partial,
        "xb",
    ) as dst:

        shutil.copyfileobj(
            src,
            dst,
            length=16 * 1024 * 1024,
        )

        dst.flush()
        os.fsync(
            dst.fileno()
        )

    partial_stat = os.stat(
        partial,
        follow_symlinks=False,
    )

    if (
        int(partial_stat.st_size)
        != expected_size
    ):
        raise RuntimeError(
            "partial size mismatch"
        )

    source_after = os.stat(
        source,
        follow_symlinks=False,
    )

    if (
        int(source_after.st_size)
        != expected_size
        or int(source_after.st_mtime_ns)
        != expected_mtime_ns
    ):
        raise RuntimeError(
            "source changed during publish"
        )

    if os.path.exists(destination):
        raise RuntimeError(
            "destination appeared during publish"
        )

    os.rename(
        partial,
        destination,
    )

    published = True

    with open(
        destination,
        "rb",
    ) as final_handle:
        os.fsync(
            final_handle.fileno()
        )

    directory_fd = os.open(
        destination_parent,
        os.O_RDONLY,
    )

    try:
        os.fsync(
            directory_fd
        )
    finally:
        os.close(
            directory_fd
        )

    final_stat = os.stat(
        destination,
        follow_symlinks=False,
    )

    if (
        int(final_stat.st_size)
        != expected_size
    ):
        raise RuntimeError(
            "published size mismatch"
        )

    print(
        json.dumps({
            "status": "PUBLISHED",
            "size": int(
                final_stat.st_size
            ),
            "mtime_ns": int(
                final_stat.st_mtime_ns
            ),
            "source_preserved": True,
        })
    )

except Exception:
    if (
        not published
        and os.path.exists(partial)
    ):
        try:
            os.unlink(
                partial
            )
        except OSError:
            pass

    raise
'''

        try:
            raw = self.ssh._run_python(
                script,
                self.ssh.downloads_root,
                self.ssh.library_root,
                source_relative,
                destination_relative,
                int(expected_size),
                int(expected_mtime_ns),
            )
        except CompletionSSHError as exc:
            raise CompletionApplyError(
                str(exc)
            ) from exc

        try:
            result = json.loads(
                raw or "{}"
            )
        except json.JSONDecodeError as exc:
            raise CompletionApplyError(
                "invalid publish response"
            ) from exc

        if (
            result.get("status")
            != "PUBLISHED"
            or not result.get(
                "source_preserved"
            )
        ):
            raise CompletionApplyError(
                "publish verification failed"
            )

        return result

    def cleanup_source(
        self,
        *,
        source_relative: str,
        expected_size: int,
        expected_mtime_ns: int,
    ) -> None:

        source_relative = _safe_relative(
            source_relative
        )

        script = r'''
import os
import sys

root = os.path.realpath(
    sys.argv[1]
)

relative = sys.argv[2]
expected_size = int(sys.argv[3])
expected_mtime_ns = int(sys.argv[4])

source = os.path.join(
    root,
    relative,
)

source_real = os.path.realpath(
    source
)

prefix = root.rstrip(os.sep) + os.sep

if not source_real.startswith(prefix):
    raise SystemExit(
        "source escapes downloads root"
    )

if (
    os.path.islink(source)
    or not os.path.isfile(source)
):
    raise SystemExit(
        "source is not a regular file"
    )

stat = os.stat(
    source,
    follow_symlinks=False,
)

if (
    int(stat.st_size)
    != expected_size
    or int(stat.st_mtime_ns)
    != expected_mtime_ns
):
    raise SystemExit(
        "source changed before cleanup"
    )

os.unlink(
    source
)

parent = os.path.dirname(
    source
)

fd = os.open(
    parent,
    os.O_RDONLY,
)

try:
    os.fsync(fd)
finally:
    os.close(fd)

print("CLEANED")
'''

        try:
            raw = self.ssh._run_python(
                script,
                self.ssh.downloads_root,
                source_relative,
                int(expected_size),
                int(expected_mtime_ns),
            )
        except CompletionSSHError as exc:
            raise CompletionApplyError(
                str(exc)
            ) from exc

        if str(raw).strip() != "CLEANED":
            raise CompletionApplyError(
                "cleanup verification failed"
            )
