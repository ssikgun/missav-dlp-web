"""Lazy, bounded VM122 worker lifecycle for Stage11 ASR.

The worker is started only when the first ASR chunk is submitted. Callers open
one session around source preparation and inference so the bounded worker
lifetime is not spent copying media. Runtime paths are read from one
owner-private permanent configuration file; no temporary candidate checkout is
imported or executed.
"""
from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import queue
import re
import shlex
import shutil
import socket
import stat
import subprocess
import threading
import time

from teddy_discovery_asr import REMOTE_GPU_LARGE_V3_INT8_FLOAT16_RUNTIME_IDENTITY


CANONICAL_ORIGIN = "https://github.com/ssikgun/missav-dlp-web.git"
CANONICAL_BRANCH = "teddy-subtitle-stage11"
VM122_HOST = "192.168.1.134"
VM122_USER = "teddy"
REMOTE_WORKER_PORT = 8091
LOCAL_FORWARD_PORT = 18091
WORKER_RUNTIME_SECONDS = 900
WORKER_READY_TIMEOUT_SECONDS = 120
REQUEST_TIMEOUT_SECONDS = 900
MIN_FREE_VRAM_MIB = 3500
RUNTIME_MIN_FREE_VRAM_MIB = 1500
MAX_CONFIG_BYTES = 16 * 1024
CONFIG_PATH = Path(
    "/opt/missav-dlp-web/discovery/stage11-normal-deployment/"
    "targeted-asr-worker.json"
)
CONFIG_KEYS = frozenset({
    "remote_repo_root", "remote_source_sha", "ssh_key", "known_hosts",
    "remote_python", "model_cache_root", "model_snapshot",
})


class BoundedASRWorkerError(RuntimeError):
    """Fail-closed lifecycle error containing only a fixed status code."""

    def __init__(self, code: str):
        if re.fullmatch(r"[A-Z0-9_]{1,100}", code) is None:
            code = "WORKER_LIFECYCLE_FAILED"
        super().__init__(code)
        self.code = code


def _absolute_path(value: object, field: str) -> str:
    if type(value) is not str or not value:
        raise BoundedASRWorkerError("WORKER_CONFIG_INVALID")
    path = Path(value)
    if (not path.is_absolute() or ".." in path.parts
            or Path("/tmp") == path or Path("/tmp") in path.parents
            or Path("/var/tmp") == path or Path("/var/tmp") in path.parents):
        raise BoundedASRWorkerError("WORKER_CONFIG_PATH_INVALID")
    return str(path)


@dataclass(frozen=True)
class BoundedASRWorkerConfig:
    remote_repo_root: str
    remote_source_sha: str
    ssh_key: str
    known_hosts: str
    remote_python: str
    model_cache_root: str
    model_snapshot: str

    @classmethod
    def load(cls, config_path: str | Path = CONFIG_PATH) -> "BoundedASRWorkerConfig":
        path = Path(config_path)
        try:
            # Refuse symlinked path components and writable parent directories.
            current = Path(path.anchor)
            for part in path.parts[1:-1]:
                current /= part
                info = os.lstat(current)
                if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
                    raise BoundedASRWorkerError("WORKER_CONFIG_PATH_INVALID")
                if info.st_mode & 0o022:
                    raise BoundedASRWorkerError("WORKER_CONFIG_PATH_INVALID")
            before = os.lstat(path)
            if (not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode)
                    or before.st_nlink != 1 or before.st_uid != os.geteuid()
                    or stat.S_IMODE(before.st_mode) != 0o600
                    or not 0 < before.st_size <= MAX_CONFIG_BYTES):
                raise BoundedASRWorkerError("WORKER_CONFIG_PERMISSIONS_INVALID")
            descriptor = os.open(
                path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            )
            try:
                info = os.fstat(descriptor)
                if ((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
                        != (before.st_dev, before.st_ino, before.st_size,
                            before.st_mtime_ns)
                        or info.st_uid != os.geteuid()
                        or stat.S_IMODE(info.st_mode) != 0o600
                        or info.st_nlink != 1):
                    raise BoundedASRWorkerError("WORKER_CONFIG_CHANGED")
                with os.fdopen(descriptor, "rb", closefd=False) as stream:
                    raw = stream.read(MAX_CONFIG_BYTES + 1)
                after = os.fstat(descriptor)
                if ((after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                        != (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
                        or len(raw) != info.st_size or len(raw) > MAX_CONFIG_BYTES):
                    raise BoundedASRWorkerError("WORKER_CONFIG_CHANGED")
            finally:
                os.close(descriptor)
            value = json.loads(raw)
        except BoundedASRWorkerError:
            raise
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            raise BoundedASRWorkerError("WORKER_CONFIG_UNAVAILABLE") from error
        if type(value) is not dict or set(value) != CONFIG_KEYS:
            raise BoundedASRWorkerError("WORKER_CONFIG_FIELDS_INVALID")
        if type(value["remote_source_sha"]) is not str or re.fullmatch(
                r"[0-9a-f]{40}", value["remote_source_sha"]) is None:
            raise BoundedASRWorkerError("WORKER_SOURCE_IDENTITY_INVALID")
        paths = {
            name: _absolute_path(value[name], name)
            for name in CONFIG_KEYS - {"remote_source_sha"}
        }
        if not paths["remote_python"].endswith("/python"):
            raise BoundedASRWorkerError("WORKER_PYTHON_PATH_INVALID")
        return cls(remote_source_sha=value["remote_source_sha"], **paths)


def _validate_local_ssh_file(path_text: str, *, private_key: bool) -> None:
    path = Path(path_text)
    try:
        info = os.lstat(path)
    except OSError as error:
        raise BoundedASRWorkerError("SSH_IDENTITY_UNAVAILABLE") from error
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise BoundedASRWorkerError("SSH_IDENTITY_INVALID")
    if private_key and (info.st_uid != os.geteuid() or info.st_mode & 0o077):
        raise BoundedASRWorkerError("SSH_PRIVATE_KEY_PERMISSIONS_INVALID")
    if not private_key and info.st_mode & 0o022:
        raise BoundedASRWorkerError("SSH_KNOWN_HOSTS_PERMISSIONS_INVALID")


class WorkerSession:
    """Own one SSH PTY and require the existing remote SAFE_STOP evidence."""

    def __init__(self, process: subprocess.Popen):
        self.process = process
        self.lines: deque[str] = deque(maxlen=200)
        self.messages: queue.Queue[str] = queue.Queue()
        self.remote_supervisor_pid: int | None = None
        self.remote_identity_valid = True
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _record(self, line: str) -> None:
        if line.startswith("REMOTE_SUPERVISOR_PID="):
            raw = line.partition("=")[2]
            if not raw.isascii() or not raw.isdigit() or int(raw) <= 0:
                self.remote_identity_valid = False
                return
            pid = int(raw)
            if self.remote_supervisor_pid not in (None, pid):
                self.remote_identity_valid = False
                return
            self.remote_supervisor_pid = pid

    def _read(self) -> None:
        stream = self.process.stdout
        if stream is None:
            return
        for raw in iter(stream.readline, b""):
            line = raw.decode("utf-8", errors="replace").strip()
            self._record(line)
            # Remote output is held only for fixed-marker checks and is never printed.
            self.lines.append(line)
            self.messages.put(line)

    def wait_ready(self) -> None:
        deadline = time.monotonic() + WORKER_READY_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise BoundedASRWorkerError("VM122_WORKER_START_FAILED")
            try:
                line = self.messages.get(timeout=0.25)
            except queue.Empty:
                continue
            if "SAFE_STOP_" in line:
                raise BoundedASRWorkerError("VM122_WORKER_START_FAILED")
            if (line == "WORKER=LISTENING_LOOPBACK INT8_FLOAT16=OPT_IN"
                    and self.remote_identity_valid
                    and self.remote_supervisor_pid is not None):
                return
        raise BoundedASRWorkerError("VM122_WORKER_READY_TIMEOUT")

    def _stop_owned_ssh_client(self) -> bool:
        if self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    self.process.kill()
                    self.process.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    return False
        return self.process.poll() is not None

    def stop(self) -> bool:
        if self.process.poll() is None:
            try:
                if self.process.stdin is None:
                    self._stop_owned_ssh_client()
                    return False
                self.process.stdin.write(b"\x03")
                self.process.stdin.flush()
                self.process.stdin.close()
                self.process.wait(timeout=30)
            except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                self._stop_owned_ssh_client()
                return False
        self.reader.join(timeout=5)
        if self.reader.is_alive():
            return False
        combined = "\n".join(self.lines)
        return bool(
            self.process.poll() is not None
            and self.remote_identity_valid
            and self.remote_supervisor_pid is not None
            and "REMOTE_SOURCE=PASS" in combined
            and self.process.returncode == 2
            and "WORKER_STOP_UNVERIFIED" not in combined
            and any(line.startswith("RESULT=SAFE_STOP_") for line in self.lines)
        )


class BoundedASRWorkerLifecycle:
    """SSH/tunnel operations copied from the verified lifecycle, parameterized."""

    def __init__(self, config: BoundedASRWorkerConfig, *, popen=subprocess.Popen,
                 runner=subprocess.run,
                 clock=time.monotonic, sleep=time.sleep, socket_factory=socket.socket):
        self.config = config
        self._popen = popen
        self._runner = runner
        self._clock = clock
        self._sleep = sleep
        self._socket_factory = socket_factory

    def _ssh_base(self) -> list[str]:
        ssh = shutil.which("ssh")
        if not ssh:
            raise BoundedASRWorkerError("SSH_CLIENT_UNAVAILABLE")
        return [ssh, "-i", self.config.ssh_key,
                "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
                "-o", "StrictHostKeyChecking=yes",
                "-o", "UserKnownHostsFile=" + self.config.known_hosts,
                "-o", "ConnectTimeout=10",
                VM122_USER + "@" + VM122_HOST]

    def _stop_process(self, process: subprocess.Popen | None) -> bool:
        if process is None or process.poll() is not None:
            return True
        try:
            process.terminate()
            process.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                return False
        return process.poll() is not None

    def _wait_for_forward(self, process: subprocess.Popen, *, timeout=15.0) -> None:
        deadline = self._clock() + timeout
        while self._clock() < deadline:
            if process.poll() is not None:
                raise BoundedASRWorkerError("SSH_FORWARD_START_FAILED")
            probe = self._socket_factory(socket.AF_INET, socket.SOCK_STREAM)
            try:
                probe.settimeout(0.4)
                if probe.connect_ex(("127.0.0.1", LOCAL_FORWARD_PORT)) == 0:
                    return
            finally:
                probe.close()
            self._sleep(0.2)
        raise BoundedASRWorkerError("SSH_FORWARD_START_TIMEOUT")

    def start_tunnel(self):
        command = self._ssh_base()
        command[1:1] = ["-N", "-o", "ExitOnForwardFailure=yes", "-L",
                        f"127.0.0.1:{LOCAL_FORWARD_PORT}:127.0.0.1:{REMOTE_WORKER_PORT}"]
        try:
            process = self._popen(
                command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, start_new_session=True,
            )
        except OSError as error:
            raise BoundedASRWorkerError("SSH_FORWARD_START_FAILED") from error
        try:
            self._wait_for_forward(process)
        except BaseException as error:
            if not self._stop_process(process):
                raise BoundedASRWorkerError("SSH_FORWARD_CLEANUP_UNVERIFIED") from error
            raise
        return process

    def start_worker(self) -> WorkerSession:
        c = self.config
        launcher = " ".join(shlex.quote(value) for value in (
            c.remote_python,
            str(Path(c.remote_repo_root) / "teddy_discovery_asr_int8_ephemeral_launcher.py"),
            "serve", "--cache-root", c.model_cache_root,
            "--snapshot", c.model_snapshot,
            "--min-free-vram-mib", str(MIN_FREE_VRAM_MIB),
            "--runtime-min-free-vram-mib", str(RUNTIME_MIN_FREE_VRAM_MIB),
            "--max-runtime-seconds", str(WORKER_RUNTIME_SECONDS),
            "--live-approved",
        ))
        remote = " ".join((
            "set -eu;",
            "cd -- " + shlex.quote(c.remote_repo_root) + ";",
            "test \"$(git rev-parse --show-toplevel)\" = "
            + shlex.quote(c.remote_repo_root)
            + " || { echo SAFE_STOP_REMOTE_SOURCE_ROOT; exit 2; };",
            "test \"$(git branch --show-current)\" = "
            + shlex.quote(CANONICAL_BRANCH)
            + " || { echo SAFE_STOP_REMOTE_SOURCE_BRANCH; exit 2; };",
            "test \"$(git rev-parse HEAD)\" = "
            + shlex.quote(c.remote_source_sha)
            + " || { echo SAFE_STOP_REMOTE_SOURCE_SHA; exit 2; };",
            "test \"$(git remote get-url origin)\" = "
            + shlex.quote(CANONICAL_ORIGIN)
            + " || { echo SAFE_STOP_REMOTE_SOURCE_ORIGIN; exit 2; };",
            "test -z \"$(git status --porcelain)\""
            + " || { echo SAFE_STOP_REMOTE_SOURCE_DIRTY; exit 2; };",
            "echo REMOTE_SOURCE=PASS;",
            "printf 'REMOTE_SUPERVISOR_PID=%s\\n' \"$$\";",
            "exec " + launcher,
        ))
        command = self._ssh_base()
        command[1:1] = ["-tt"]
        command.append(remote)
        try:
            process = self._popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, bufsize=0, start_new_session=True,
            )
        except OSError as error:
            raise BoundedASRWorkerError("VM122_WORKER_START_FAILED") from error
        session = WorkerSession(process)
        try:
            session.wait_ready()
        except BaseException as error:
            if not session.stop():
                raise BoundedASRWorkerError(
                    "VM122_WORKER_CLEANUP_UNVERIFIED"
                ) from error
            raise
        return session

    def read_only_preflight(self) -> None:
        """Verify remote source/runtime/model files without starting a worker."""
        c = self.config
        launcher = str(
            Path(c.remote_repo_root)
            / "teddy_discovery_asr_int8_ephemeral_launcher.py"
        )
        verify_snapshot = (
            "import sys; from teddy_discovery_asr_int8_ephemeral_launcher "
            "import verified_snapshot; "
            "verified_snapshot(sys.argv[1], sys.argv[2])"
        )
        python_check = " ".join((
            shlex.quote(c.remote_python), "-B", "-c", shlex.quote(verify_snapshot),
            shlex.quote(c.model_cache_root), shlex.quote(c.model_snapshot),
        ))
        remote = " ".join((
            "set -eu;",
            "cd -- " + shlex.quote(c.remote_repo_root) + ";",
            "test \"$(git rev-parse --show-toplevel)\" = "
            + shlex.quote(c.remote_repo_root) + ";",
            "test \"$(git branch --show-current)\" = "
            + shlex.quote(CANONICAL_BRANCH) + ";",
            "test \"$(git rev-parse HEAD)\" = "
            + shlex.quote(c.remote_source_sha) + ";",
            "test \"$(git remote get-url origin)\" = "
            + shlex.quote(CANONICAL_ORIGIN) + ";",
            "test -z \"$(git status --porcelain)\";",
            "test -x " + shlex.quote(c.remote_python) + ";",
            "test -f " + shlex.quote(launcher) + ";",
            python_check + ";",
            "printf '%s\\n' STAGE11_ASR_PREFLIGHT=PASS",
        ))
        command = self._ssh_base()
        command.append(remote)
        try:
            result = self._runner(
                command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, timeout=30, check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise BoundedASRWorkerError(
                "VM122_ASR_PREFLIGHT_UNAVAILABLE"
            ) from error
        if (getattr(result, "returncode", None) != 0
                or "STAGE11_ASR_PREFLIGHT=PASS" not in
                str(getattr(result, "stdout", "")).splitlines()):
            raise BoundedASRWorkerError("VM122_ASR_PREFLIGHT_FAILED")


class BoundedTargetedASRSession:
    def __init__(self, *, client, lifecycle: BoundedASRWorkerLifecycle):
        self._client = client
        self._lifecycle = lifecycle
        self._state = "NOT_STARTED"
        self._tunnel = None
        self._worker: WorkerSession | None = None
        self._cleanup_attempted = False
        self._cleanup_ok: bool | None = None
        self.request_count = 0
        self.runtime_identity = client.runtime_identity
        self.engine_version = client.engine_version

    def __enter__(self):
        return self

    def _start(self):
        if self._state == "READY":
            if self._worker is None or self._worker.process.poll() is not None:
                raise BoundedASRWorkerError("VM122_WORKER_EXITED_BEFORE_REQUEST")
            return
        if self._state != "NOT_STARTED":
            raise BoundedASRWorkerError("VM122_WORKER_START_NOT_RETRIED")
        self._state = "STARTING"
        try:
            self._tunnel = self._lifecycle.start_tunnel()
            self._worker = self._lifecycle.start_worker()
            self._state = "READY"
        except BaseException as error:
            self._state = "START_FAILED"
            if not self._cleanup():
                raise BoundedASRWorkerError(
                    "WORKER_START_CLEANUP_UNVERIFIED"
                ) from error
            self._state = "START_FAILED"
            raise

    def _transcribe(self, method: str, chunk):
        self._start()
        self.request_count += 1
        callback = getattr(self._client, method, None)
        if not callable(callback):
            raise BoundedASRWorkerError("ASR_REQUEST_METHOD_UNAVAILABLE")
        return callback(chunk)

    def transcribe_chunk(self, chunk):
        """Submit one full-title baseline chunk through the owned worker."""
        return self._transcribe("transcribe_chunk", chunk)

    def transcribe_targeted_chunk(self, chunk):
        """Submit one HYBRID targeted chunk through the owned worker."""
        return self._transcribe("transcribe_targeted_chunk", chunk)

    def _cleanup(self) -> bool:
        if self._cleanup_attempted:
            return self._cleanup_ok is True
        self._cleanup_attempted = True
        worker_ok = True
        tunnel_ok = True
        worker, tunnel = self._worker, self._tunnel
        self._worker = self._tunnel = None
        if worker is not None:
            try:
                worker_ok = worker.stop() is True
            except BaseException:
                worker_ok = False
        if tunnel is not None:
            try:
                tunnel_ok = self._lifecycle._stop_process(tunnel) is True
            except BaseException:
                tunnel_ok = False
        self._cleanup_ok = worker_ok and tunnel_ok
        self._state = "CLOSED" if self._cleanup_ok else "CLEANUP_UNKNOWN"
        return self._cleanup_ok

    def close(self):
        if self._state == "CLOSED":
            return
        if self._cleanup():
            return
        raise BoundedASRWorkerError("WORKER_OR_TUNNEL_CLEANUP_UNVERIFIED")

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False


class BoundedTargetedASRTransport:
    """Session factory injected into normal and one-title Stage11 adapters."""

    bounded_worker_lifecycle = True

    def __init__(self, *, config_path: str | Path = CONFIG_PATH,
                 request_timeout_seconds: int | float = REQUEST_TIMEOUT_SECONDS,
                 client_factory=None, lifecycle_factory=BoundedASRWorkerLifecycle):
        self.config_path = Path(config_path)
        timeout = float(request_timeout_seconds)
        if not 0 < timeout <= REQUEST_TIMEOUT_SECONDS:
            timeout = REQUEST_TIMEOUT_SECONDS
        self.request_timeout_seconds = timeout
        self._client_factory = client_factory
        self._lifecycle_factory = lifecycle_factory
        self.runtime_identity = REMOTE_GPU_LARGE_V3_INT8_FLOAT16_RUNTIME_IDENTITY
        self.engine_version = "1.2.1"

    def read_only_preflight(self) -> None:
        """Check local identity and remote execution files without ASR/model use."""
        config = BoundedASRWorkerConfig.load(self.config_path)
        _validate_local_ssh_file(config.ssh_key, private_key=True)
        _validate_local_ssh_file(config.known_hosts, private_key=False)
        if not shutil.which("ssh"):
            raise BoundedASRWorkerError("SSH_CLIENT_UNAVAILABLE")
        lifecycle = self._lifecycle_factory(config)
        lifecycle.read_only_preflight()

    @contextmanager
    def session(self):
        config = BoundedASRWorkerConfig.load(self.config_path)
        _validate_local_ssh_file(config.ssh_key, private_key=True)
        _validate_local_ssh_file(config.known_hosts, private_key=False)
        if self._client_factory is None:
            from teddy_discovery_asr_remote import RemoteFasterWhisperASR
            client = RemoteFasterWhisperASR(
                base_url=f"http://127.0.0.1:{LOCAL_FORWARD_PORT}",
                request_timeout_seconds=self.request_timeout_seconds,
                runtime_identity=REMOTE_GPU_LARGE_V3_INT8_FLOAT16_RUNTIME_IDENTITY,
            )
        else:
            client = self._client_factory(config)
        lifecycle = self._lifecycle_factory(config)
        with BoundedTargetedASRSession(client=client, lifecycle=lifecycle) as active:
            yield active


__all__ = [
    "BoundedASRWorkerConfig", "BoundedASRWorkerError",
    "BoundedASRWorkerLifecycle", "BoundedTargetedASRSession",
    "BoundedTargetedASRTransport", "CONFIG_PATH", "WORKER_RUNTIME_SECONDS",
]
