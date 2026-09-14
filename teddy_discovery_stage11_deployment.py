"""Deployment-owned wiring for the generic Stage11 live adapters.

This module owns connection values and the small bridges which connect the
already validated Stage11 components.  It does not add a pipeline, a request
schema, a classifier, or a publication boundary.  Importing it performs no
network, process, media, or database operation; those operations are reached
only through the returned injected callables.
"""

from __future__ import annotations

import base64
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import shlex
import stat
import subprocess
from types import SimpleNamespace
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlsplit

from teddy_discovery_alignment_application import (
    AlignmentAcceptanceApplicationResult,
)
from teddy_discovery_asr_artifact import serialize_asr_result
from teddy_discovery_asr_audio import iter_audio_chunks
from teddy_discovery_asr_remote import RemoteFasterWhisperASR
from teddy_discovery_asr_source import ASRMediaSourceReader
from teddy_discovery_quality_review_session import (
    QualityReviewSessionError,
    validate_canonical_review_execution_session_id,
)
from teddy_discovery_stage11_live_adapters import (
    Stage11LiveDependencies,
    build_stage11_live_dependencies,
)
from teddy_discovery_stateful_asr_quality_review_direct_runner import (
    REMOTE_HERMES_PROFILE,
    REMOTE_HERMES_PROFILE_NAME,
    REMOTE_HERMES_PYTHON,
    REMOTE_HERMES_SOURCE,
)
from teddy_discovery_stateful_live_runner import (
    build_stateful_ssh_argv,
    run as native_stateful_run,
    validate_stateful_remote_task_path,
)
from teddy_discovery_stateful_quality_review import (
    QualityReviewRequest,
    build_review_request,
)
from teddy_discovery_stateful_quality_review_runner import (
    QUALITY_REVIEW_INPUT_FILENAME,
    QUALITY_REVIEW_RESULT_FILENAME,
)
from teddy_discovery_stateful_hybrid import prepare_stateful_hybrid
from teddy_discovery_stateful_translator import (
    STATEFUL_TRANSLATOR_INPUT_FILENAME,
    STATEFUL_TRANSLATOR_PRIVATE_FILE_MODE,
    STATEFUL_TRANSLATOR_SESSION_SOURCE,
    serialize_stateful_package,
    stateful_session_id_for_package,
)
from teddy_discovery_subtitle_external import (
    ExternalSubtitleTransport,
    ExternalSubtitleTransportError,
    SubtitleCatDetailError,
    SubtitleCatDetailPage,
    SubtitleCatProvider,
    MAX_SUBTITLECAT_DETAIL_HTML_BYTES,
)
from teddy_discovery_subtitle_text import MAX_SUBTITLE_BYTES
from teddy_discovery_subtitle_source_quality import classify_source_document
from teddy_discovery_subtitlecat_discovery import (
    SubtitleCatDiscovery,
    SubtitleCatSearchError,
    validate_subtitlecat_proxy_url,
)
from teddy_discovery_subtitle_v2_orchestrator import (
    V2_READY_FOR_SEMANTIC,
    V2_ROUTE_HYBRID,
    SubtitleV2RouteDecision,
)
from teddy_discovery_targeted_second_evidence_artifact import (
    TargetedSecondEvidenceArtifact,
    targeted_second_evidence_artifact_from_execution,
)


STAGE11_STANDALONE_CANARY_CLAIM_TOKEN = 1
"""The explicit claim token reserved for the first standalone canary."""


class Stage11DeploymentError(RuntimeError):
    """A deployment-owned connection or evidence bridge failed closed."""


class Stage11DeploymentValidationError(Stage11DeploymentError):
    """A deployment value or caller-held evidence is invalid or detached."""


class Stage11DeploymentTransportError(Stage11DeploymentError):
    """A narrow process or network transport boundary failed."""


def _as_text(value: object, *, field_name: str) -> str:
    if isinstance(value, os.PathLike):
        value = os.fspath(value)
    if type(value) is not str or not value or value != value.strip():
        raise Stage11DeploymentValidationError(
            field_name + " must be a nonempty exact string"
        )
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise Stage11DeploymentValidationError(
            field_name + " contains control data"
        )
    return value


def _absolute_path(value: object, *, field_name: str) -> str:
    value = _as_text(value, field_name=field_name)
    path = PurePosixPath(value)
    if not path.is_absolute() or path == PurePosixPath("/"):
        raise Stage11DeploymentValidationError(
            field_name + " must be a non-root absolute path"
        )
    if str(path) != value or any(part in {".", ".."} for part in path.parts):
        raise Stage11DeploymentValidationError(
            field_name + " must be a normalized absolute path"
        )
    return value


def _host_or_user(value: object, *, field_name: str) -> str:
    value = _as_text(value, field_name=field_name)
    if any(character.isspace() for character in value):
        raise Stage11DeploymentValidationError(
            field_name + " must not contain whitespace"
        )
    if any(character in value for character in "@/\\"):
        raise Stage11DeploymentValidationError(
            field_name + " contains unsafe SSH syntax"
        )
    return value


def _profile_name(value: object) -> str:
    value = _as_text(value, field_name="expected_profile_name")
    if any(character.isspace() for character in value):
        raise Stage11DeploymentValidationError(
            "expected_profile_name contains unsafe whitespace"
        )
    return value


def _positive_number(value: object, *, field_name: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Stage11DeploymentValidationError(
            field_name + " must be a positive finite number"
        )
    try:
        numeric = float(value)
    except OverflowError as error:
        raise Stage11DeploymentValidationError(
            field_name + " must be a positive finite number"
        ) from error
    if not math.isfinite(numeric) or numeric <= 0:
        raise Stage11DeploymentValidationError(
            field_name + " must be a positive finite number"
        )
    return value


@dataclass(frozen=True)
class Stage11DeploymentConfig:
    """Explicit deployment-owned connection values.

    The ASR timeout is deliberately required from the caller.  The value
    ``1200`` is therefore a first-canary choice, not a module production
    default.  SSH keys are retained as paths only; their contents are never
    loaded by this configuration object.
    """

    nas_host: str
    nas_user: str
    nas_key: str
    nas_known_hosts: str
    nas_library_root: str
    asr_base_url: str
    request_timeout_seconds: int | float
    remote_host: str
    remote_user: str
    ssh_key: str
    known_hosts: str
    remote_task_root: str
    expected_profile_name: str = REMOTE_HERMES_PROFILE_NAME
    subtitlecat_timeout_seconds: int | float = 20.0
    subtitlecat_proxy_url: str | None = None

    def __post_init__(self):
        for name in ("nas_host", "nas_user", "remote_host", "remote_user"):
            object.__setattr__(
                self,
                name,
                _host_or_user(getattr(self, name), field_name=name),
            )
        for name in (
            "nas_key",
            "nas_known_hosts",
            "nas_library_root",
            "ssh_key",
            "known_hosts",
            "remote_task_root",
        ):
            object.__setattr__(
                self,
                name,
                _absolute_path(getattr(self, name), field_name=name),
            )
        object.__setattr__(
            self,
            "asr_base_url",
            _as_text(self.asr_base_url, field_name="asr_base_url"),
        )
        object.__setattr__(
            self,
            "request_timeout_seconds",
            _positive_number(
                self.request_timeout_seconds,
                field_name="request_timeout_seconds",
            ),
        )
        object.__setattr__(
            self,
            "subtitlecat_timeout_seconds",
            _positive_number(
                self.subtitlecat_timeout_seconds,
                field_name="subtitlecat_timeout_seconds",
            ),
        )
        try:
            subtitlecat_proxy_url = validate_subtitlecat_proxy_url(
                self.subtitlecat_proxy_url
            )
        except SubtitleCatSearchError as error:
            raise Stage11DeploymentValidationError(
                "subtitlecat_proxy_url is invalid"
            ) from error
        object.__setattr__(
            self,
            "subtitlecat_proxy_url",
            subtitlecat_proxy_url,
        )
        object.__setattr__(
            self,
            "expected_profile_name",
            _profile_name(self.expected_profile_name),
        )


def _require_session_id(value: object) -> str:
    try:
        return validate_canonical_review_execution_session_id(value)
    except QualityReviewSessionError as error:
        raise Stage11DeploymentValidationError(
            "remote session ID is not canonical"
        ) from error


def _normalized_remote_root(value: str) -> PurePosixPath:
    root = PurePosixPath(_absolute_path(value, field_name="remote_task_root"))
    return root


def _make_remote_task_factory(config: Stage11DeploymentConfig) -> Callable[[str], str]:
    root = _normalized_remote_root(config.remote_task_root)

    def remote_task_for_session(session_id: str) -> str:
        session_id = _require_session_id(session_id)
        task = root / session_id
        if task.parent != root or task.name != session_id:
            raise Stage11DeploymentValidationError(
                "remote session task escaped its configured root"
            )
        return validate_stateful_remote_task_path(task.as_posix())

    return remote_task_for_session


class _NoRedirectHandler(urllib_request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise ExternalSubtitleTransportError(
            "SubtitleCat redirect is not permitted"
        )


def _http_bytes(
    url: str,
    *,
    timeout: int | float,
    max_bytes: int,
    proxy_url: str | None = None,
) -> bytes:
    try:
        parsed = urlsplit(url)
    except ValueError as error:
        raise ExternalSubtitleTransportError(
            "SubtitleCat URL could not be parsed"
        ) from error
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ExternalSubtitleTransportError(
            "SubtitleCat transport requires an HTTP(S) URL"
        )
    request = urllib_request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 Teddy-Downloader-SubtitleDiscovery/1.0",
            "Accept": "text/html,application/x-subrip,text/plain,*/*",
        },
        method="GET",
    )
    handlers = []
    if proxy_url is not None:
        handlers.append(
            urllib_request.ProxyHandler(
                {"http": proxy_url, "https": proxy_url}
            )
        )
    handlers.append(_NoRedirectHandler())
    opener = urllib_request.build_opener(*handlers)
    try:
        with opener.open(request, timeout=timeout) as response:
            status = response.getcode()
            final_url = response.geturl()
            if type(status) is not int or not 200 <= status < 300:
                raise ExternalSubtitleTransportError(
                    "SubtitleCat HTTP status is not successful"
                )
            if final_url != url:
                raise ExternalSubtitleTransportError(
                    "SubtitleCat redirect is not permitted"
                )
            payload = response.read(max_bytes + 1)
    except ExternalSubtitleTransportError:
        raise
    except (
        OSError,
        TimeoutError,
        urllib_error.URLError,
        urllib_error.HTTPError,
    ) as error:
        raise ExternalSubtitleTransportError(
            "SubtitleCat HTTP transport failed"
        ) from error
    if type(payload) is not bytes or not 0 < len(payload) <= max_bytes:
        raise ExternalSubtitleTransportError(
            "SubtitleCat response exceeded its bounded byte limit"
        )
    return payload


def _default_detail_fetcher(
    timeout: int | float,
    *,
    proxy_url: str | None = None,
) -> Callable[[str], SubtitleCatDetailPage]:
    def fetch_detail(url: str) -> SubtitleCatDetailPage:
        raw = _http_bytes(
            url,
            timeout=timeout,
            max_bytes=MAX_SUBTITLECAT_DETAIL_HTML_BYTES,
            proxy_url=proxy_url,
        )
        try:
            html = raw.decode("utf-8", errors="strict")
            return SubtitleCatDetailPage(final_url=url, html=html)
        except (UnicodeError, SubtitleCatDetailError):
            raise
        except (TypeError, ValueError) as error:
            raise SubtitleCatDetailError(
                "SubtitleCat detail HTML is invalid"
            ) from error

    return fetch_detail


def _default_payload_fetcher(
    timeout: int | float,
    *,
    proxy_url: str | None = None,
) -> Callable:
    def fetch_payload(candidate) -> bytes:
        url = getattr(candidate, "external_source_id", None)
        if type(url) is not str:
            raise ExternalSubtitleTransportError(
                "SubtitleCat candidate has no source URL"
            )
        return _http_bytes(
            url,
            timeout=timeout,
            max_bytes=MAX_SUBTITLE_BYTES,
            proxy_url=proxy_url,
        )

    return fetch_payload


def build_subtitlecat_provider(
    *,
    timeout: int | float = 20.0,
    fetch_detail: Callable[[str], object] | None = None,
    payload_fetcher: Callable | None = None,
    proxy_url: str | None = None,
) -> SubtitleCatProvider:
    """Compose the existing provider with bounded GET-only transports."""

    timeout = _positive_number(timeout, field_name="SubtitleCat timeout")
    proxy_url = validate_subtitlecat_proxy_url(proxy_url)
    detail = fetch_detail or _default_detail_fetcher(
        timeout,
        proxy_url=proxy_url,
    )
    payload = payload_fetcher or _default_payload_fetcher(
        timeout,
        proxy_url=proxy_url,
    )
    return SubtitleCatProvider(
        fetch_detail=detail,
        payload_transport=ExternalSubtitleTransport(payload),
    )


def _private_local_read(path: Path, *, max_bytes: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | os.O_NONBLOCK
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise Stage11DeploymentValidationError(
            "private local deployment input cannot be opened"
        ) from error
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != STATEFUL_TRANSLATOR_PRIVATE_FILE_MODE
            or not 0 < info.st_size <= max_bytes
        ):
            raise Stage11DeploymentValidationError(
                "private local deployment input has unsafe identity"
            )
        payload = os.read(descriptor, max_bytes + 1)
        if len(payload) != info.st_size or not 0 < len(payload) <= max_bytes:
            raise Stage11DeploymentValidationError(
                "private local deployment input readback differs"
            )
        return payload
    except OSError as error:
        raise Stage11DeploymentValidationError(
            "private local deployment input could not be read"
        ) from error
    finally:
        os.close(descriptor)


def _private_local_read_at(fd: int, filename: str, *, max_bytes: int) -> bytes:
    try:
        descriptor = os.open(
            filename,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | os.O_NONBLOCK,
            dir_fd=fd,
        )
    except OSError as error:
        raise Stage11DeploymentValidationError(
            "private review input cannot be opened"
        ) from error
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != STATEFUL_TRANSLATOR_PRIVATE_FILE_MODE
            or not 0 < info.st_size <= max_bytes
        ):
            raise Stage11DeploymentValidationError(
                "private review input has unsafe identity"
            )
        payload = os.read(descriptor, max_bytes + 1)
        if len(payload) != info.st_size or not 0 < len(payload) <= max_bytes:
            raise Stage11DeploymentValidationError(
                "private review input readback differs"
            )
        return payload
    except OSError as error:
        raise Stage11DeploymentValidationError(
            "private review input could not be read"
        ) from error
    finally:
        os.close(descriptor)


def _private_local_write_at(fd: int, filename: str, payload: bytes) -> None:
    if type(payload) is not bytes or not payload:
        raise Stage11DeploymentValidationError(
            "private review result must be nonempty bytes"
        )
    try:
        descriptor = os.open(
            filename,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            STATEFUL_TRANSLATOR_PRIVATE_FILE_MODE,
            dir_fd=fd,
        )
    except OSError as error:
        raise Stage11DeploymentValidationError(
            "private review result destination is not absent"
        ) from error
    try:
        os.fchmod(descriptor, STATEFUL_TRANSLATOR_PRIVATE_FILE_MODE)
        written = os.write(descriptor, payload)
        if written != len(payload):
            raise Stage11DeploymentValidationError(
                "private review result write was short"
            )
        os.fsync(descriptor)
    except OSError as error:
        raise Stage11DeploymentValidationError(
            "private review result write failed"
        ) from error
    finally:
        os.close(descriptor)
    try:
        os.fsync(fd)
    except OSError as error:
        raise Stage11DeploymentValidationError(
            "private review task directory sync failed"
        ) from error


def _local_task_from_fd(fd: int) -> Path:
    try:
        value = Path(os.readlink(f"/proc/self/fd/{fd}"))
    except OSError as error:
        raise Stage11DeploymentValidationError(
            "pinned review task directory cannot be resolved"
        ) from error
    if not value.is_absolute() or value == Path("/"):
        raise Stage11DeploymentValidationError(
            "pinned review task directory is not absolute"
        )
    return value


class SSHRemoteHermesBridge:
    """Native CT120 bridge; all state access remains in Hermes' SessionDB API."""

    def __init__(
        self,
        config: Stage11DeploymentConfig,
        *,
        runner: Callable = subprocess.run,
    ):
        if not callable(runner):
            raise Stage11DeploymentValidationError("remote runner must be callable")
        self.config = config
        self.runner = runner

    def _base(self) -> list[str]:
        return build_stateful_ssh_argv(
            f"{self.config.remote_user}@{self.config.remote_host}",
            self.config.ssh_key,
            self.config.known_hosts,
        )

    def _run(
        self,
        command: str,
        *,
        input_payload: bytes | None = None,
        capture: bool = False,
        timeout: int | float | None = None,
    ) -> bytes:
        kwargs = {
            "input": input_payload,
            "stdout": subprocess.PIPE if capture else subprocess.DEVNULL,
            "stderr": subprocess.PIPE,
            "check": False,
        }
        if timeout is not None:
            kwargs["timeout"] = timeout
        try:
            completed = self.runner(self._base() + [command], **kwargs)
        except (OSError, subprocess.SubprocessError) as error:
            raise Stage11DeploymentTransportError(
                "CT120 SSH transport failed"
            ) from error
        if getattr(completed, "returncode", None) != 0:
            raise Stage11DeploymentTransportError(
                "CT120 native command failed"
            )
        output = getattr(completed, "stdout", b"")
        if capture and type(output) is not bytes:
            raise Stage11DeploymentTransportError(
                "CT120 captured output is not bytes"
            )
        return output if capture else b""

    def _python(
        self,
        script: str,
        *arguments: str,
        input_payload: bytes | None = None,
        capture: bool = False,
        timeout: int | float | None = None,
        python_executable: str = "python3",
    ) -> bytes:
        command = " ".join(
            shlex.quote(value)
            for value in (python_executable, "-c", script, *arguments)
        )
        return self._run(
            command,
            input_payload=input_payload,
            capture=capture,
            timeout=timeout,
        )

    def ensure_task(self, remote_task: str) -> None:
        remote_task = validate_stateful_remote_task_path(remote_task)
        script = """
import os, stat, sys
path = sys.argv[1]
try:
    info = os.lstat(path)
except FileNotFoundError:
    os.mkdir(path, 0o700)
    info = os.lstat(path)
if (stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700):
    raise SystemExit(2)
"""
        self._python(script, remote_task)

    def write_exclusive(self, remote_path: str, payload: bytes) -> None:
        remote_path = validate_stateful_remote_task_path(remote_path)
        if type(payload) is not bytes or not payload:
            raise Stage11DeploymentValidationError(
                "remote payload must be nonempty bytes"
            )
        digest = hashlib.sha256(payload).hexdigest()
        script = """
import hashlib, os, stat, sys
path, expected_size, expected_sha = sys.argv[1], int(sys.argv[2]), sys.argv[3]
payload = sys.stdin.buffer.read(expected_size + 1)
if len(payload) != expected_size or hashlib.sha256(payload).hexdigest() != expected_sha:
    raise SystemExit(2)
if os.path.lexists(path):
    raise SystemExit(3)
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "wb") as stream:
        fd = None
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
finally:
    if fd is not None:
        os.close(fd)
info = os.lstat(path)
if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
        or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_size != expected_size):
    raise SystemExit(4)
"""
        self._python(
            script,
            remote_path,
            str(len(payload)),
            digest,
            input_payload=payload,
        )

    def ensure_file(self, remote_path: str, payload: bytes) -> None:
        """Install exact input once, or reuse an exact existing input."""

        try:
            existing = self.read_regular(remote_path, max_bytes=len(payload))
        except Stage11DeploymentTransportError:
            existing = None
        if existing is not None:
            if existing != payload:
                raise Stage11DeploymentValidationError(
                    "existing remote input is detached"
                )
            return
        self.write_exclusive(remote_path, payload)

    def read_regular(self, remote_path: str, *, max_bytes: int) -> bytes:
        remote_path = validate_stateful_remote_task_path(remote_path)
        if type(max_bytes) is not int or max_bytes <= 0:
            raise Stage11DeploymentValidationError("remote read bound is invalid")
        script = """
import os, stat, sys
path, bound = sys.argv[1], int(sys.argv[2])
fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
try:
    info = os.fstat(fd)
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600
            or not 0 < info.st_size <= bound):
        raise SystemExit(2)
    payload = os.read(fd, bound + 1)
finally:
    os.close(fd)
if len(payload) != info.st_size or not 0 < len(payload) <= bound:
    raise SystemExit(3)
sys.stdout.buffer.write(payload)
"""
        return self._python(script, remote_path, str(max_bytes), capture=True)

    def _native_session(
        self,
        operation: str,
        session_id: str,
        *,
        source: str | None = None,
        profile_name: str | None = None,
        timeout: int | float | None = None,
    ) -> object:
        session_id = _require_session_id(session_id)
        profile_name = self.config.expected_profile_name if profile_name is None else profile_name
        profile_name = _profile_name(profile_name)
        if source is not None:
            source = _as_text(source, field_name="native session source")
        profile_home = str(Path(REMOTE_HERMES_PROFILE).parent)
        script = """
import json, os, sys
from pathlib import Path
profile_home, source_root, operation, session_id, expected_profile, expected_source = sys.argv[1:]
os.environ["HERMES_HOME"] = profile_home
sys.path.insert(0, source_root)
from hermes_cli.profiles import get_active_profile_name
from hermes_state import SessionDB
if get_active_profile_name() != expected_profile:
    raise SystemExit(20)
db = SessionDB(db_path=Path(profile_home) / "state.db")
try:
    if operation == "get":
        row = db.get_session(session_id)
        if row is None:
            print("null")
        else:
            print(json.dumps({
                "id": row.get("id"),
                "source": row.get("source"),
                "profile_name": row.get("profile_name"),
                "parent_session_id": row.get("parent_session_id"),
            }, sort_keys=True, separators=(",", ":")))
    elif operation == "messages":
        messages = db.get_messages(session_id, include_inactive=True)
        if not isinstance(messages, list):
            raise SystemExit(21)
        print(len(messages))
    elif operation in {"ensure", "fresh"}:
        existing = db.get_session(session_id)
        if operation == "fresh" and existing is not None:
            raise SystemExit(22)
        if operation == "ensure" and existing is None:
            returned_id = db.create_session(
                session_id=session_id,
                source=expected_source,
                profile_name=expected_profile,
            )
            if type(returned_id) is not str or returned_id != session_id:
                raise SystemExit(23)
            existing = db.get_session(session_id)
        if existing is None:
            raise SystemExit(24)
        if (existing.get("id") != session_id
                or existing.get("source") != expected_source
                or existing.get("profile_name") != expected_profile
                or existing.get("parent_session_id") is not None):
            raise SystemExit(25)
        if operation == "fresh":
            messages = db.get_messages(session_id, include_inactive=True)
            if not isinstance(messages, list) or messages:
                raise SystemExit(26)
        print(session_id)
    else:
        raise SystemExit(27)
finally:
    close = getattr(db, "close", None)
    if callable(close):
        close()
"""
        output = self._python(
            script,
            profile_home,
            REMOTE_HERMES_SOURCE,
            operation,
            session_id,
            profile_name,
            source or "",
            capture=True,
            timeout=timeout,
            python_executable=REMOTE_HERMES_PYTHON,
        )
        return output.decode("utf-8", errors="strict").strip()

    def get_session(self, session_id: str) -> Mapping[str, object] | None:
        raw = self._native_session("get", session_id)
        if raw == "null":
            return None
        try:
            value = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise Stage11DeploymentTransportError(
                "CT120 SessionDB read-back is malformed"
            ) from error
        if type(value) is not dict:
            raise Stage11DeploymentTransportError(
                "CT120 SessionDB read-back is not a mapping"
            )
        return value

    def create_session(
        self,
        *,
        session_id: str,
        source: str,
        profile_name: str,
    ) -> str:
        raw = self._native_session(
            "fresh",
            session_id,
            source=source,
            profile_name=profile_name,
        )
        if raw != session_id:
            raise Stage11DeploymentTransportError(
                "CT120 SessionDB created a different session ID"
            )
        return session_id

    def ensure_stateful_session(self, session_id: str) -> None:
        raw = self._native_session(
            "ensure",
            session_id,
            source=STATEFUL_TRANSLATOR_SESSION_SOURCE,
            profile_name=self.config.expected_profile_name,
        )
        if raw != session_id:
            raise Stage11DeploymentTransportError(
                "CT120 stateful session read-back differs"
            )

    def get_messages(
        self,
        session_id: str,
        *,
        include_inactive: bool = False,
    ) -> list[object]:
        del include_inactive
        raw = self._native_session("messages", session_id)
        try:
            count = int(raw)
        except (TypeError, ValueError) as error:
            raise Stage11DeploymentTransportError(
                "CT120 SessionDB message count is malformed"
            ) from error
        if count < 0:
            raise Stage11DeploymentTransportError(
                "CT120 SessionDB message count is negative"
            )
        # Only emptiness is needed by the shared validator.  Do not return
        # remote dialogue contents to CT108.
        return [None] * count

    def launch_quality_review(
        self,
        command: list[str],
        *,
        remote_task: str,
        timeout: int | float,
    ) -> SimpleNamespace:
        remote_task = validate_stateful_remote_task_path(remote_task)
        if type(command) is not list or not command or not all(
            type(item) is str and item for item in command
        ):
            raise Stage11DeploymentValidationError(
                "native review command is malformed"
            )
        encoded = base64.b64encode(
            json.dumps(command, ensure_ascii=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).decode("ascii")
        script = """
import base64, json, os, stat, subprocess, sys
task, encoded = sys.argv[1], sys.argv[2]
info = os.lstat(task)
if (stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700):
    raise SystemExit(2)
command = json.loads(base64.b64decode(encoded).decode("utf-8"))
if type(command) is not list or not all(type(item) is str for item in command):
    raise SystemExit(3)
completed = subprocess.run(command, cwd=task, stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           check=False)
if completed.returncode != 0:
    raise SystemExit(completed.returncode if completed.returncode > 0 else 1)
"""
        self._python(
            script,
            remote_task,
            encoded,
            timeout=timeout,
        )
        return SimpleNamespace(returncode=0)


class RemoteNativeSessionDB:
    """SessionDB-shaped proxy backed by the native CT120 API bridge."""

    def __init__(self, bridge: object, *, expected_profile_name: str):
        if not callable(getattr(bridge, "get_session", None)) or not callable(
            getattr(bridge, "create_session", None)
        ) or not callable(getattr(bridge, "get_messages", None)):
            raise Stage11DeploymentValidationError(
                "native remote bridge lacks SessionDB methods"
            )
        self.bridge = bridge
        self.expected_profile_name = _profile_name(expected_profile_name)

    def get_session(self, session_id: str):
        return self.bridge.get_session(session_id)

    def create_session(self, *, session_id: str, source: str, profile_name: str):
        if profile_name != self.expected_profile_name:
            raise Stage11DeploymentValidationError(
                "Hybrid requested an unexpected Hermes profile"
            )
        return self.bridge.create_session(
            session_id=session_id,
            source=source,
            profile_name=profile_name,
        )

    def get_messages(self, session_id: str, *, include_inactive: bool = False):
        return self.bridge.get_messages(
            session_id,
            include_inactive=include_inactive,
        )


def _prepare_remote_factory(
    config: Stage11DeploymentConfig,
    bridge: object,
    remote_task_for_session: Callable[[str], str],
) -> Callable:
    ensure_task = getattr(bridge, "ensure_task", None)
    ensure_file = getattr(bridge, "ensure_file", None)
    ensure_session = getattr(bridge, "ensure_stateful_session", None)
    if not callable(ensure_task) or not callable(ensure_file) or not callable(
        ensure_session
    ):
        raise Stage11DeploymentValidationError(
            "remote bridge lacks first-pass preparation methods"
        )

    def prepare_remote(package, paths, *, route: str):
        if route not in {"ASR_ONLY", "HYBRID"}:
            raise Stage11DeploymentValidationError(
                "first-pass route is unsupported"
            )
        try:
            package.__post_init__()
        except AttributeError as error:
            raise Stage11DeploymentValidationError(
                "first-pass package is invalid"
            ) from error
        expected_payload = serialize_stateful_package(package)
        if _private_local_read(paths.input_path, max_bytes=len(expected_payload)) != expected_payload:
            raise Stage11DeploymentValidationError(
                "local first-pass input differs from package"
            )
        session_id = stateful_session_id_for_package(package)
        remote_task = remote_task_for_session(session_id)
        ensure_task(remote_task)
        ensure_session(session_id)
        ensure_file(
            remote_task + "/" + STATEFUL_TRANSLATOR_INPUT_FILENAME,
            expected_payload,
        )
        return remote_task

    return prepare_remote


def _hybrid_launcher_factory(
    bridge: object,
    remote_task_for_session: Callable[[str], str],
) -> Callable:
    ensure_task = getattr(bridge, "ensure_task", None)
    ensure_file = getattr(bridge, "ensure_file", None)
    read_regular = getattr(bridge, "read_regular", None)
    launch = getattr(bridge, "launch_quality_review", None)
    if not all(callable(value) for value in (ensure_task, ensure_file, read_regular, launch)):
        raise Stage11DeploymentValidationError(
            "remote bridge lacks Hybrid review methods"
        )

    def launcher(command, *, cwd, timeout):
        if type(cwd) is not int or cwd < 0:
            raise Stage11DeploymentValidationError(
                "Hybrid launcher received an invalid pinned directory"
            )
        if type(command) is not list or not all(type(item) is str for item in command):
            raise Stage11DeploymentValidationError(
                "Hybrid launcher command is malformed"
            )
        try:
            resume_index = command.index("--resume")
            session_id = _require_session_id(command[resume_index + 1])
        except (ValueError, IndexError) as error:
            raise Stage11DeploymentValidationError(
                "Hybrid launcher command has no canonical session"
            ) from error
        query_indexes = [index for index, value in enumerate(command) if value == "-q"]
        if len(query_indexes) != 1 or query_indexes[0] + 1 >= len(command):
            raise Stage11DeploymentValidationError(
                "Hybrid launcher command has no unique query"
            )
        local_task = _local_task_from_fd(cwd)
        local_input = str(local_task / QUALITY_REVIEW_INPUT_FILENAME)
        local_result = str(local_task / QUALITY_REVIEW_RESULT_FILENAME)
        query_index = query_indexes[0] + 1
        query = command[query_index]
        if local_input not in query or local_result not in query:
            raise Stage11DeploymentValidationError(
                "Hybrid query lacks exact local file authority"
            )
        payload = _private_local_read_at(
            cwd,
            QUALITY_REVIEW_INPUT_FILENAME,
            max_bytes=16 * 1024 * 1024,
        )
        remote_task = remote_task_for_session(session_id)
        remote_input = remote_task + "/" + QUALITY_REVIEW_INPUT_FILENAME
        remote_result = remote_task + "/" + QUALITY_REVIEW_RESULT_FILENAME
        ensure_task(remote_task)
        ensure_file(remote_input, payload)
        remote_command = list(command)
        remote_command[query_index] = query.replace(str(local_task), remote_task)
        if local_input in remote_command[query_index] or local_result in remote_command[query_index]:
            raise Stage11DeploymentValidationError(
                "Hybrid query retained local file authority"
            )
        launch(remote_command, remote_task=remote_task, timeout=timeout)
        result_payload = read_regular(remote_result, max_bytes=16 * 1024 * 1024)
        _private_local_write_at(cwd, QUALITY_REVIEW_RESULT_FILENAME, result_payload)
        return SimpleNamespace(returncode=0)

    return launcher


@dataclass
class _HybridOriginalRegistry:
    """One-title caller-held originals; no semantic evidence is synthesized."""

    targeted_artifact_provider: Callable | None = None

    def __post_init__(self):
        self._applications: dict[str, tuple[object, AlignmentAcceptanceApplicationResult]] = {}
        self._first_pass: dict[str, tuple[object, object]] = {}
        self._targeted: dict[str, TargetedSecondEvidenceArtifact] = {}

    def capture_external(self, callback: Callable) -> Callable:
        def wrapped(canonical_video, asr_result):
            application = callback(canonical_video, asr_result)
            if application is None:
                return None
            if type(application) is not AlignmentAcceptanceApplicationResult:
                raise Stage11DeploymentValidationError(
                    "external callback returned an invalid application"
                )
            application.__post_init__()
            if (
                application.bundle.dvd_id != canonical_video.dvd_id
                or application.bundle.asr_result != asr_result
            ):
                raise Stage11DeploymentValidationError(
                    "captured external application is detached"
                )
            self._applications[canonical_video.dvd_id] = (
                canonical_video,
                application,
            )
            return application

        return wrapped

    def capture_first_pass(self, callback: Callable) -> Callable:
        def wrapped(
            package,
            *,
            route,
            staging_root,
            semantic_policy=None,
        ):
            callback_kwargs = {
                "route": route,
                "staging_root": staging_root,
            }
            if semantic_policy is not None:
                callback_kwargs["semantic_policy"] = semantic_policy
            result = callback(package, **callback_kwargs)
            if route == V2_ROUTE_HYBRID:
                try:
                    session_id = stateful_session_id_for_package(package)
                except Exception as error:
                    raise Stage11DeploymentValidationError(
                        "Hybrid package session identity is invalid"
                    ) from error
                self._first_pass[session_id] = (package, result)
            return result

        return wrapped

    def capture_targeted(self, callback: Callable) -> Callable:
        def wrapped(asr_result, decisions):
            execution = callback(asr_result, decisions)
            try:
                execution.__post_init__()
                artifact = targeted_second_evidence_artifact_from_execution(
                    execution,
                    baseline_asr_artifact_sha256=hashlib.sha256(
                        serialize_asr_result(asr_result)
                    ).hexdigest(),
                    runtime_identity=asr_result.runtime_identity,
                    engine_version=asr_result.engine_version,
                )
                artifact.__post_init__()
            except Exception as error:
                raise Stage11DeploymentValidationError(
                    "targeted execution could not be retained for review"
                ) from error
            self._targeted[asr_result.source_snapshot.dvd_id] = artifact
            return execution

        return wrapped

    def originals_provider(self, request: QualityReviewRequest) -> Mapping[str, object]:
        if type(request) is not QualityReviewRequest:
            raise Stage11DeploymentValidationError(
                "Hybrid originals provider received an invalid request"
            )
        request.__post_init__()
        source_session = request.source_translation_session_id
        package_result = self._first_pass.get(source_session)
        if package_result is None:
            raise Stage11DeploymentValidationError(
                "Hybrid first-pass originals are not retained"
            )
        package, result = package_result
        dvd_id = package.dvd_id
        external = self._applications.get(dvd_id)
        if external is None:
            raise Stage11DeploymentValidationError(
                "Hybrid external application is not retained"
            )
        canonical_video, application = external
        if application.decision.verdict != "ACCEPT_HYBRID":
            raise Stage11DeploymentValidationError(
                "Hybrid originals require an accepted external application"
            )
        route = SubtitleV2RouteDecision(
            canonical_video=canonical_video,
            route=V2_ROUTE_HYBRID,
            state=V2_READY_FOR_SEMANTIC,
            alignment_application=application,
        )
        preparation = prepare_stateful_hybrid(
            route,
            generation_key=package.generation_key,
            claim_token=package.claim_token,
        )
        if preparation.package != package:
            raise Stage11DeploymentValidationError(
                "Hybrid package is detached from retained route evidence"
            )
        source_quality = classify_source_document(
            application.bundle.external_ja_document
        )
        targeted = self._targeted.get(dvd_id)
        has_targeted_projection = any(
            cue.targeted_second_evidence is not None for cue in request.cues
        )
        if has_targeted_projection and targeted is None:
            if self.targeted_artifact_provider is None:
                raise Stage11DeploymentValidationError(
                    "Hybrid targeted artifact is not retained"
                )
            targeted = self.targeted_artifact_provider(request, asr_result=application.bundle.asr_result)
            if type(targeted) is not TargetedSecondEvidenceArtifact:
                raise Stage11DeploymentValidationError(
                    "targeted artifact provider returned an invalid artifact"
                )
            targeted.__post_init__()
        originals = {
            "preparation": preparation,
            "package": package,
            "result": result,
            "source_quality": source_quality,
            "targeted_second_evidence_artifact": targeted,
        }
        try:
            expected = build_review_request(**originals)
        except Exception as error:
            raise Stage11DeploymentValidationError(
                "Hybrid originals failed native request revalidation"
            ) from error
        if expected != request:
            raise Stage11DeploymentValidationError(
                "Hybrid review request is detached from retained originals"
            )
        return originals


def _merge_options(
    defaults: Mapping[str, object],
    overrides: Mapping[str, object] | None,
    *,
    field_name: str,
) -> dict[str, object]:
    if overrides is None:
        return dict(defaults)
    if not isinstance(overrides, Mapping):
        raise Stage11DeploymentValidationError(field_name + " must be a mapping")
    result = dict(defaults)
    result.update(overrides)
    return result


def _reject_owned_option_overrides(
    overrides: Mapping[str, object] | None,
    owned: Mapping[str, object],
    *,
    field_name: str,
) -> None:
    if overrides is None:
        return
    for key, expected in owned.items():
        if key not in overrides:
            continue
        actual = overrides[key]
        same = actual is expected if callable(expected) else actual == expected
        if not same:
            raise Stage11DeploymentValidationError(
                field_name + " contains a deployment-owned override"
            )


@dataclass(frozen=True)
class Stage11DeploymentDependencies:
    """Resolved deployment components plus the native live adapter bundle."""

    config: Stage11DeploymentConfig
    source_provider: object
    whisper: object
    targeted_transport: object
    discovery: object
    provider: SubtitleCatProvider
    remote_bridge: object
    remote_task_for_session: Callable
    prepare_remote: Callable
    originals_provider: Callable
    live: Stage11LiveDependencies

    def controller_kwargs(self) -> dict[str, Callable]:
        """Return only the existing controller-facing callable contract."""

        return {
            "holding_resolver": self.live.holding_resolver,
            "baseline_transcriber": self.live.baseline_transcriber,
            "external_ja_attempt": self.live.external_ja_attempt,
            "targeted_runner": self.live.targeted_runner,
            "first_pass_runner": self.live.first_pass_runner,
            "asr_review_runner": self.live.asr_review_runner,
            "hybrid_review_runner": self.live.hybrid_review_runner,
        }


def build_stage11_deployment_dependencies(
    config: Stage11DeploymentConfig,
    *,
    acceptance_policy,
    residual_threshold_ms,
    holding_resolver: Callable | None = None,
    source_provider: object | None = None,
    whisper: object | None = None,
    targeted_transport: object | None = None,
    discovery: object | None = None,
    provider: SubtitleCatProvider | None = None,
    remote_bridge: object | None = None,
    remote_runner: Callable = subprocess.run,
    native_first_pass_run: Callable = native_stateful_run,
    first_pass_options: Mapping[str, object] | None = None,
    asr_review_options: Mapping[str, object] | None = None,
    hybrid_review_options: Mapping[str, object] | None = None,
    targeted_artifact_provider: Callable | None = None,
    audio_chunk_iterator: Callable = iter_audio_chunks,
) -> Stage11DeploymentDependencies:
    """Build deployment values and feed them into the existing live factory."""

    if type(config) is not Stage11DeploymentConfig:
        raise Stage11DeploymentValidationError(
            "deployment config must be Stage11DeploymentConfig"
        )
    if not callable(native_first_pass_run):
        raise Stage11DeploymentValidationError(
            "native_first_pass_run must be callable"
        )
    if targeted_artifact_provider is not None and not callable(
        targeted_artifact_provider
    ):
        raise Stage11DeploymentValidationError(
            "targeted_artifact_provider must be callable"
        )

    resolver = holding_resolver
    if resolver is None:
        from teddy_discovery_stage11_live_adapters import build_holding_resolver

        resolver = build_holding_resolver()
    if not callable(resolver):
        raise Stage11DeploymentValidationError("holding_resolver must be callable")

    source = source_provider
    if source is None:
        source = ASRMediaSourceReader(
            host=config.nas_host,
            user=config.nas_user,
            key=config.nas_key,
            known_hosts=config.nas_known_hosts,
            library_root=config.nas_library_root,
        )
    live_whisper = whisper
    if live_whisper is None:
        live_whisper = RemoteFasterWhisperASR(
            base_url=config.asr_base_url,
            request_timeout_seconds=config.request_timeout_seconds,
        )
    live_targeted = live_whisper if targeted_transport is None else targeted_transport
    live_discovery = discovery
    if live_discovery is None:
        live_discovery = SubtitleCatDiscovery(
            timeout=config.subtitlecat_timeout_seconds,
            proxy_url=config.subtitlecat_proxy_url,
        )
    live_provider = provider
    if live_provider is None:
        live_provider = build_subtitlecat_provider(
            timeout=config.subtitlecat_timeout_seconds,
            proxy_url=config.subtitlecat_proxy_url,
        )

    bridge = remote_bridge
    if bridge is None:
        bridge = SSHRemoteHermesBridge(config, runner=remote_runner)
    remote_task_for_session = _make_remote_task_factory(config)
    prepare_remote = _prepare_remote_factory(
        config,
        bridge,
        remote_task_for_session,
    )
    originals_registry = _HybridOriginalRegistry(
        targeted_artifact_provider=targeted_artifact_provider,
    )
    hybrid_launcher = _hybrid_launcher_factory(bridge, remote_task_for_session)

    first_options = _merge_options(
        {
            "remote": f"{config.remote_user}@{config.remote_host}",
            "ssh_key": config.ssh_key,
            "known_hosts": config.known_hosts,
            "prepare_remote": prepare_remote,
            "native_run": native_first_pass_run,
        },
        first_pass_options,
        field_name="first_pass_options",
    )
    for key, expected in {
        "remote": f"{config.remote_user}@{config.remote_host}",
        "ssh_key": config.ssh_key,
        "known_hosts": config.known_hosts,
        "prepare_remote": prepare_remote,
        "native_run": native_first_pass_run,
    }.items():
        if first_options[key] is not expected and key in {
            "prepare_remote",
            "native_run",
        }:
            raise Stage11DeploymentValidationError(
                "first-pass deployment-owned option cannot be replaced"
            )
        if key in {"remote", "ssh_key", "known_hosts"} and first_options[key] != expected:
            raise Stage11DeploymentValidationError(
                "first-pass connection option differs from deployment config"
            )

    asr_native_defaults = {
        "remote_host": config.remote_host,
        "remote_user": config.remote_user,
        "ssh_key": config.ssh_key,
        "known_hosts": config.known_hosts,
    }
    _reject_owned_option_overrides(
        asr_review_options,
        asr_native_defaults,
        field_name="asr_review_options",
    )
    asr_native_options = _merge_options(
        asr_native_defaults,
        asr_review_options,
        field_name="asr_review_options",
    )
    hybrid_native_defaults = {
        "fresh_session_db": RemoteNativeSessionDB(
            bridge,
            expected_profile_name=config.expected_profile_name,
        ),
        "expected_profile_name": config.expected_profile_name,
        "launcher": hybrid_launcher,
    }
    _reject_owned_option_overrides(
        hybrid_review_options,
        hybrid_native_defaults,
        field_name="hybrid_review_options",
    )
    hybrid_native_options = _merge_options(
        hybrid_native_defaults,
        hybrid_review_options,
        field_name="hybrid_review_options",
    )

    live = build_stage11_live_dependencies(
        source_provider=source,
        whisper=live_whisper,
        targeted_transport=live_targeted,
        discovery=live_discovery,
        provider=live_provider,
        acceptance_policy=acceptance_policy,
        residual_threshold_ms=residual_threshold_ms,
        holding_resolver=resolver,
        audio_chunk_iterator=audio_chunk_iterator,
        first_pass_options=first_options,
        asr_review_options={
            "remote_task_for_session": remote_task_for_session,
            "runner_options": asr_native_options,
        },
        hybrid_review_options={
            "originals_provider": originals_registry.originals_provider,
            "runner_options": hybrid_native_options,
        },
    )
    live = replace(
        live,
        external_ja_attempt=originals_registry.capture_external(
            live.external_ja_attempt
        ),
        targeted_runner=originals_registry.capture_targeted(live.targeted_runner),
        first_pass_runner=originals_registry.capture_first_pass(
            live.first_pass_runner
        ),
    )
    return Stage11DeploymentDependencies(
        config=config,
        source_provider=source,
        whisper=live_whisper,
        targeted_transport=live_targeted,
        discovery=live_discovery,
        provider=live_provider,
        remote_bridge=bridge,
        remote_task_for_session=remote_task_for_session,
        prepare_remote=prepare_remote,
        originals_provider=originals_registry.originals_provider,
        live=live,
    )


__all__ = [
    "SSHRemoteHermesBridge",
    "RemoteNativeSessionDB",
    "Stage11DeploymentConfig",
    "Stage11DeploymentDependencies",
    "Stage11DeploymentError",
    "Stage11DeploymentTransportError",
    "Stage11DeploymentValidationError",
    "STAGE11_STANDALONE_CANARY_CLAIM_TOKEN",
    "build_stage11_deployment_dependencies",
    "build_subtitlecat_provider",
]
