"""Bounded read-only canonical MP4 source adapter for Stage11 Slice 4A.

Only one validated canonical video is read.  Remote metadata is requested as
small JSON responses, while the media payload itself is streamed through an
SSH stdout pipe into a private local temporary file.  This module never
writes to the remote filesystem and never buffers the media payload in RAM.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import PurePosixPath
import selectors
import shlex
import subprocess
import tempfile
import time

from teddy_discovery_asr import (
    ASRLimitError,
    ASRSourceSnapshot,
    ASRValidationError,
    ASRError,
    validate_canonical_video,
)
from teddy_discovery_subtitle import CanonicalVideoHolding


MEDIA_TRANSFER_CHUNK_BYTES = 1 * 1024 * 1024
PROCESS_CLEANUP_TIMEOUT_SECONDS = 1.0


class ASRSourceError(ASRError):
    """Raised for SSH, remote metadata, stream, and local temp failures."""


REMOTE_STAT_SCRIPT = r'''
import json
import os
import stat
import sys

root = os.path.realpath(sys.argv[1])
relative = sys.argv[2]
max_media_bytes = int(sys.argv[3])
candidate = os.path.join(root, relative)
resolved = os.path.realpath(candidate)

if (
    resolved == root
    or os.path.commonpath((root, resolved)) != root
):
    raise SystemExit(2)

current = root
for component in relative.split(os.sep):
    current = os.path.join(current, component)
    if os.path.islink(current):
        raise SystemExit(3)

if not os.path.lexists(candidate) or os.path.islink(candidate):
    raise SystemExit(4)

value = os.lstat(candidate)
if not stat.S_ISREG(value.st_mode):
    raise SystemExit(5)

if value.st_size <= 0 or value.st_size > max_media_bytes:
    raise SystemExit(6)

print(json.dumps({
    "size": value.st_size,
    "mtime_ns": value.st_mtime_ns,
}, separators=(",", ":")))
'''


REMOTE_STREAM_SCRIPT = r'''
import os
import stat
import sys

root = os.path.realpath(sys.argv[1])
relative = sys.argv[2]
max_media_bytes = int(sys.argv[3])
candidate = os.path.join(root, relative)
resolved = os.path.realpath(candidate)

if (
    resolved == root
    or os.path.commonpath((root, resolved)) != root
):
    raise SystemExit(2)

current = root
for component in relative.split(os.sep):
    current = os.path.join(current, component)
    if os.path.islink(current):
        raise SystemExit(3)

if not os.path.lexists(candidate) or os.path.islink(candidate):
    raise SystemExit(4)

value = os.lstat(candidate)
if not stat.S_ISREG(value.st_mode):
    raise SystemExit(5)

if value.st_size <= 0 or value.st_size > max_media_bytes:
    raise SystemExit(6)

remaining = value.st_size
with open(candidate, "rb") as source:
    while remaining:
        chunk = source.read(min(1024 * 1024, remaining))
        if not chunk:
            raise SystemExit(7)
        sys.stdout.buffer.write(chunk)
        remaining -= len(chunk)
    sys.stdout.buffer.flush()
'''


def _validate_max_media_bytes(value: object) -> int:
    if type(value) is not int or value <= 0:
        raise ASRValidationError(
            "max_media_bytes must be a positive integer"
        )

    return value


def _validate_canonical_mp4(
    canonical_video: CanonicalVideoHolding,
) -> CanonicalVideoHolding:
    validated = validate_canonical_video(canonical_video)
    if validated.video_format != "mp4":
        raise ASRValidationError(
            "ASR media source accepts canonical MP4 holdings only"
        )
    return validated


def _validate_timeout(value: object) -> float | None:
    if value is None:
        return None

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ASRValidationError(
            "timeout must be a positive finite number or None"
        )

    timeout = float(value)
    if not math.isfinite(timeout) or timeout <= 0:
        raise ASRValidationError(
            "timeout must be a positive finite number or None"
        )

    return timeout


def _remaining_timeout(deadline: float | None) -> float | None:
    if deadline is None:
        return None

    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ASRSourceError("ASR media operation timed out")

    return remaining


def _validate_stat_payload(
    payload: object,
    *,
    max_media_bytes: int,
) -> tuple[int, int]:
    if not isinstance(payload, dict) or set(payload) != {"size", "mtime_ns"}:
        raise ASRSourceError("remote media stat response has an invalid shape")

    size = payload["size"]
    mtime_ns = payload["mtime_ns"]

    if type(size) is not int or size <= 0:
        raise ASRSourceError("remote media size is invalid")

    if type(mtime_ns) is not int or mtime_ns < 0:
        raise ASRSourceError("remote media mtime_ns is invalid")

    if size > max_media_bytes:
        raise ASRLimitError("remote media exceeds max_media_bytes")

    return size, mtime_ns


def _decode_stat_output(raw: object) -> object:
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ASRSourceError("remote media stat is not UTF-8 JSON") from error

    if not isinstance(raw, str) or not raw:
        raise ASRSourceError("remote media stat output is malformed")

    try:
        return json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ASRSourceError("remote media stat JSON could not be decoded") from error


def _close_quietly(value: object) -> None:
    if value is None:
        return

    try:
        value.close()
    except (AttributeError, OSError, ValueError):
        return


def _abort_process(process: object) -> None:
    """Best-effort bounded child cleanup that never raises."""

    def poll_exited() -> bool:
        poll = getattr(process, "poll", None)
        if poll is None:
            return False
        try:
            return poll() is not None
        except Exception:
            return False

    def wait_bounded() -> bool:
        wait = getattr(process, "wait", None)
        if wait is None:
            return False
        try:
            wait(timeout=PROCESS_CLEANUP_TIMEOUT_SECONDS)
            return True
        except Exception:
            return False

    try:
        if poll_exited():
            wait_bounded()
            return

        terminate = getattr(process, "terminate", None)
        if terminate is not None:
            try:
                terminate()
            except (OSError, ProcessLookupError, subprocess.SubprocessError):
                pass

        if wait_bounded():
            return

        kill = getattr(process, "kill", None)
        if kill is not None:
            try:
                kill()
            except (OSError, ProcessLookupError, subprocess.SubprocessError):
                pass

        wait_bounded()
    except Exception:
        # Cleanup must never mask the original transport/limit exception.
        return


class ASRLocalMediaSource:
    """A private local media file whose lifetime is controlled by a context."""

    __slots__ = (
        "_local_path",
        "_source_snapshot",
        "_temp_directory",
        "_cleaned",
    )

    def __init__(
        self,
        *,
        local_path: str,
        source_snapshot: ASRSourceSnapshot,
        temp_directory: str,
    ):
        self._local_path = str(local_path)
        self._source_snapshot = source_snapshot
        self._temp_directory = str(temp_directory)
        self._cleaned = False

    @property
    def local_path(self) -> str:
        return self._local_path

    @property
    def source_snapshot(self) -> ASRSourceSnapshot:
        return self._source_snapshot

    @property
    def snapshot(self) -> ASRSourceSnapshot:
        return self._source_snapshot

    def require_active(self) -> None:
        if self._cleaned:
            raise ASRSourceError("local ASR media source is no longer active")

    def __enter__(self) -> "ASRLocalMediaSource":
        self.require_active()
        return self

    def cleanup(self) -> None:
        if self._cleaned:
            return

        try:
            os.unlink(self._local_path)
        except FileNotFoundError:
            pass
        except OSError as error:
            raise ASRSourceError("local ASR media cleanup failed") from error
        finally:
            self._cleaned = True

        try:
            os.rmdir(self._temp_directory)
        except FileNotFoundError:
            pass
        except OSError:
            # The directory is ours, but never remove unexpected contents.
            pass

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.cleanup()


class ASRMediaSourceReader:
    """Read exactly one canonical MP4 from a remote JAV library."""

    def __init__(
        self,
        *,
        host,
        user,
        key,
        known_hosts,
        library_root,
        runner=subprocess.run,
        popen_factory=subprocess.Popen,
        temp_root=None,
    ):
        self.host = str(host)
        self.user = str(user)
        self.key = str(key)
        self.known_hosts = str(known_hosts)
        self.library_root = str(library_root)
        self.runner = runner
        self.popen_factory = popen_factory
        self.temp_root = None if temp_root is None else str(temp_root)

    def _base_argv(self) -> list[str]:
        return [
            "ssh",
            "-i",
            self.key,
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "UserKnownHostsFile=" + self.known_hosts,
            self.user + "@" + self.host,
        ]

    def _command(self, script: str, *args: object) -> list[str]:
        remote_command = "python3 -"
        if args:
            remote_command += " " + " ".join(
                shlex.quote(str(argument))
                for argument in args
            )
        return self._base_argv() + [remote_command]

    def _stat_remote(
        self,
        canonical_video: CanonicalVideoHolding,
        *,
        max_media_bytes: int,
        deadline: float | None,
    ) -> tuple[int, int]:
        validated = _validate_canonical_mp4(canonical_video)
        command = self._command(
            REMOTE_STAT_SCRIPT,
            self.library_root,
            validated.relative_path,
            max_media_bytes,
        )

        kwargs = {
            "input": REMOTE_STAT_SCRIPT,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "shell": False,
            "text": True,
        }
        timeout = _remaining_timeout(deadline)
        if timeout is not None:
            kwargs["timeout"] = timeout

        try:
            result = self.runner(command, **kwargs)
        except (OSError, subprocess.SubprocessError) as error:
            raise ASRSourceError("remote media stat could not be started") from error

        if getattr(result, "returncode", None) != 0:
            raise ASRSourceError("remote media stat command failed")

        payload = _decode_stat_output(getattr(result, "stdout", None))
        return _validate_stat_payload(
            payload,
            max_media_bytes=max_media_bytes,
        )

    def _read_one_chunk(
        self,
        stream: object,
        selector: selectors.BaseSelector | None,
        deadline: float | None,
    ) -> object:
        if selector is not None:
            timeout = _remaining_timeout(deadline)
            try:
                events = selector.select(timeout)
            except (OSError, ValueError) as error:
                raise ASRSourceError("remote media stream polling failed") from error
            if not events:
                raise ASRSourceError("remote media transfer timed out")

        try:
            return stream.read(MEDIA_TRANSFER_CHUNK_BYTES)
        except (OSError, ValueError, AttributeError) as error:
            raise ASRSourceError("remote media stream could not be read") from error

    def _stream_to_file(
        self,
        process: object,
        local_path: str,
        *,
        expected_size: int,
        max_media_bytes: int,
        deadline: float | None,
    ) -> int:
        stdout = getattr(process, "stdout", None)
        if stdout is None:
            raise ASRSourceError("remote media process has no stdout pipe")

        selector = None
        if deadline is not None:
            selector = selectors.DefaultSelector()
            try:
                selector.register(stdout, selectors.EVENT_READ)
            except (OSError, ValueError) as error:
                selector.close()
                raise ASRSourceError(
                    "remote media stdout is not pollable"
                ) from error

        written = 0
        try:
            with open(local_path, "wb") as output:
                while True:
                    chunk = self._read_one_chunk(
                        stdout,
                        selector,
                        deadline,
                    )

                    if chunk == b"":
                        break

                    if not isinstance(chunk, bytes):
                        raise ASRSourceError(
                            "remote media stdout must contain bytes"
                        )

                    next_size = written + len(chunk)
                    if next_size > max_media_bytes:
                        raise ASRLimitError(
                            "remote media stream exceeds max_media_bytes"
                        )
                    if next_size > expected_size:
                        raise ASRSourceError(
                            "remote media stream contains unexpected bytes"
                        )

                    count = output.write(chunk)
                    if count != len(chunk):
                        raise ASRSourceError(
                            "local media write was short"
                        )
                    written = next_size
        except OSError as error:
            raise ASRSourceError("local media temporary write failed") from error
        finally:
            if selector is not None:
                selector.close()

        return written

    def _stream_remote(
        self,
        canonical_video: CanonicalVideoHolding,
        *,
        max_media_bytes: int,
        local_path: str,
        expected_size: int,
        deadline: float | None,
    ) -> int:
        validated = _validate_canonical_mp4(canonical_video)
        command = self._command(
            REMOTE_STREAM_SCRIPT,
            self.library_root,
            validated.relative_path,
            max_media_bytes,
        )

        process = None
        try:
            process = self.popen_factory(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                text=False,
            )

            stdin = getattr(process, "stdin", None)
            if stdin is None:
                raise ASRSourceError("remote media process has no stdin pipe")

            stdin.write(REMOTE_STREAM_SCRIPT.encode("utf-8"))
            stdin.close()

            written = self._stream_to_file(
                process,
                local_path,
                expected_size=expected_size,
                max_media_bytes=max_media_bytes,
                deadline=deadline,
            )

            wait_timeout = _remaining_timeout(deadline)
            try:
                if wait_timeout is None:
                    return_code = process.wait()
                else:
                    return_code = process.wait(timeout=wait_timeout)
            except (OSError, subprocess.SubprocessError) as error:
                raise ASRSourceError("remote media process did not finish") from error

            if return_code != 0:
                raise ASRSourceError("remote media transfer command failed")

            return written
        except (ASRSourceError, ASRLimitError):
            if process is not None:
                _abort_process(process)
            raise
        except (OSError, subprocess.SubprocessError) as error:
            if process is not None:
                _abort_process(process)
            raise ASRSourceError("remote media transfer could not be started") from error
        finally:
            if process is not None:
                _close_quietly(getattr(process, "stdin", None))
                _close_quietly(getattr(process, "stdout", None))
                _close_quietly(getattr(process, "stderr", None))

    @staticmethod
    def _create_temp_paths(temp_root: str | None, suffix: str) -> tuple[str, str]:
        directory = tempfile.mkdtemp(
            prefix=".teddy-stage11-asr-",
            dir=temp_root,
        )
        try:
            descriptor, path = tempfile.mkstemp(
                prefix=".media-",
                suffix=suffix,
                dir=directory,
            )
            os.close(descriptor)
        except BaseException:
            try:
                os.rmdir(directory)
            except OSError:
                pass
            raise

        return directory, path

    @staticmethod
    def _cleanup_temp_paths(directory: str | None, path: str | None) -> None:
        if path is not None:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
            except OSError:
                pass

        if directory is not None:
            try:
                os.rmdir(directory)
            except OSError:
                pass

    def copy_to_temp(
        self,
        canonical_video: CanonicalVideoHolding,
        *,
        max_media_bytes: int,
        timeout: int | float | None = None,
    ) -> ASRLocalMediaSource:
        """Copy one stable canonical video into a caller-owned context."""

        validated = _validate_canonical_mp4(canonical_video)
        max_media_bytes = _validate_max_media_bytes(max_media_bytes)
        timeout = _validate_timeout(timeout)
        deadline = None if timeout is None else time.monotonic() + timeout

        directory = None
        path = None
        try:
            before_size, before_mtime_ns = self._stat_remote(
                validated,
                max_media_bytes=max_media_bytes,
                deadline=deadline,
            )

            directory, path = self._create_temp_paths(
                self.temp_root,
                "." + validated.video_format,
            )

            written = self._stream_remote(
                validated,
                max_media_bytes=max_media_bytes,
                local_path=path,
                expected_size=before_size,
                deadline=deadline,
            )

            if written != before_size:
                raise ASRSourceError(
                    "remote media stream was truncated"
                )

            after_size, after_mtime_ns = self._stat_remote(
                validated,
                max_media_bytes=max_media_bytes,
                deadline=deadline,
            )

            if (
                after_size != before_size
                or after_mtime_ns != before_mtime_ns
            ):
                raise ASRSourceError(
                    "remote media changed during transfer"
                )

            try:
                local_size = os.stat(path).st_size
            except OSError as error:
                raise ASRSourceError(
                    "local media temporary file could not be stated"
                ) from error

            if local_size != before_size:
                raise ASRSourceError(
                    "local media size does not match remote source"
                )

            snapshot = ASRSourceSnapshot.from_holding(
                validated,
                source_size=before_size,
                source_mtime_ns=before_mtime_ns,
            )

            return ASRLocalMediaSource(
                local_path=path,
                source_snapshot=snapshot,
                temp_directory=directory,
            )
        except (ASRValidationError, ASRLimitError, ASRSourceError):
            self._cleanup_temp_paths(directory, path)
            raise
        except (OSError, subprocess.SubprocessError) as error:
            self._cleanup_temp_paths(directory, path)
            raise ASRSourceError("canonical media copy failed") from error


__all__ = [
    "ASRLocalMediaSource",
    "ASRMediaSourceReader",
    "ASRSourceError",
    "MEDIA_TRANSFER_CHUNK_BYTES",
    "PROCESS_CLEANUP_TIMEOUT_SECONDS",
    "REMOTE_STAT_SCRIPT",
    "REMOTE_STREAM_SCRIPT",
]
