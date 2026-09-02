from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import PurePosixPath


class CompletionSSHError(RuntimeError):
    pass


class CompletionSSH:
    def __init__(
        self,
        *,
        host,
        user,
        key,
        known_hosts,
        downloads_root,
        library_root,
        runner=subprocess.run,
    ):
        self.host = str(host)
        self.user = str(user)
        self.key = str(key)
        self.known_hosts = str(known_hosts)
        self.downloads_root = str(downloads_root)
        self.library_root = str(library_root)
        self.runner = runner

    def _base(self):
        return [
            "ssh",
            "-i", self.key,
            "-o", "IdentitiesOnly=yes",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=10",
            "-o", "StrictHostKeyChecking=yes",
            "-o",
            "UserKnownHostsFile=" + self.known_hosts,
            self.user + "@" + self.host,
        ]

    def _run_python(self, script, *args):
        command = (
            self._base()
            + [
                "python3 - "
                + " ".join(
                    shlex.quote(str(arg))
                    for arg in args
                )
            ]
        )

        result = self.runner(
            command,
            input=script,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if result.returncode != 0:
            raise CompletionSSHError(
                str(result.stderr or "").strip()
                or "remote SSH command failed"
            )

        return str(result.stdout or "")

    def list_downloads(self):
        script = r'''
import json
import os
import sys

root = os.path.realpath(sys.argv[1])
items = []

def ignored(name):
    return name.startswith(".") or name == "@eaDir"

with os.scandir(root) as entries:
    for entry in entries:
        if ignored(entry.name) or entry.is_symlink():
            continue

        if entry.is_file(follow_symlinks=False):
            stat = entry.stat(follow_symlinks=False)
            items.append({
                "name": entry.name,
                "size": stat.st_size,
                "modified": stat.st_mtime,
                "mtime_ns": stat.st_mtime_ns,
            })
            continue

        if not entry.is_dir(follow_symlinks=False):
            continue

        with os.scandir(entry.path) as children:
            for child in children:
                if ignored(child.name) or child.is_symlink():
                    continue
                if not child.is_file(follow_symlinks=False):
                    continue

                stat = child.stat(follow_symlinks=False)

                items.append({
                    "name": entry.name + "/" + child.name,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                "mtime_ns": stat.st_mtime_ns,
                })

print(json.dumps(items, ensure_ascii=False))
'''
        raw = self._run_python(
            script,
            self.downloads_root,
        )

        data = json.loads(
            raw or "[]"
        )

        if not isinstance(data, list):
            raise CompletionSSHError(
                "invalid downloads listing"
            )

        return data

    def stat_library(self, relative):
        path = PurePosixPath(
            str(relative)
        )

        if (
            path.is_absolute()
            or ".." in path.parts
            or not path.parts
        ):
            raise CompletionSSHError(
                "invalid library relative path"
            )

        script = r'''
import json
import os
import sys

root = os.path.realpath(sys.argv[1])
relative = sys.argv[2]

candidate = os.path.realpath(
    os.path.join(root, relative)
)

prefix = root.rstrip(os.sep) + os.sep

if not candidate.startswith(prefix):
    raise SystemExit(2)

if not os.path.exists(candidate):
    print("null")
    raise SystemExit(0)

if os.path.islink(candidate) or not os.path.isfile(candidate):
    raise SystemExit(3)

stat = os.stat(candidate)

print(json.dumps({
    "size": stat.st_size,
    "modified": stat.st_mtime,
                "mtime_ns": stat.st_mtime_ns,
}))
'''

        raw = self._run_python(
            script,
            self.library_root,
            path.as_posix(),
        )

        value = json.loads(
            raw or "null"
        )

        return value
