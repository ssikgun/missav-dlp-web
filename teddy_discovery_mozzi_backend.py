"""CT121 Mozzi Stage11 subtitle translation backend over restricted SSH.

Reuses the staged ``mozzi-subtitle-v1`` forced-command SSH transport without
sending any model, provider, reasoning, temporary config, environment, or CLI
overrides.  CT121's ``subtitle-translator`` profile is the sole authority for
model/provider/reasoning; any profile metadata returned by CT121 is validated
and recorded strictly as execution evidence, never as an invocation override.
"""

from __future__ import annotations

import base64
from collections.abc import Callable, Mapping
from dataclasses import dataclass
import hashlib
import json
import re
import subprocess
from typing import Final


MOZZI_BACKEND_ID: Final[str] = "ct121-mozzi-subtitle-v1"
MOZZI_TARGET_SERVER: Final[str] = "ct121-mozzi"
MOZZI_TARGET_HOST: Final[str] = "192.168.1.25"
MOZZI_TRANSPORT_PROTOCOL: Final[str] = "mozzi-subtitle-v1"
MOZZI_PROFILE_NAME: Final[str] = "subtitle-translator"
MOZZI_PROFILE_AUTHORITY: Final[str] = "server_profile_only"

MOZZI_HEALTH_TIMEOUT_SECONDS: Final[int] = 40
MOZZI_TRANSLATE_TIMEOUT_SECONDS: Final[int] = 3690
MOZZI_MAX_PROMPT_BYTES: Final[int] = 128_000
MOZZI_MAX_STDOUT_BYTES: Final[int] = 16 * 1024 * 1024
MOZZI_MAX_WIRE_BYTES: Final[int] = 24 * 1024 * 1024

MOZZI_FORBIDDEN_REQUEST_KEYS: Final[frozenset[str]] = frozenset({
    "model",
    "provider",
    "reasoning",
    "reasoning_effort",
    "config",
    "config_yaml",
    "timeout_env",
    "fallback_model",
    "fallback_providers",
    "cli_args",
    "env",
    "hermes_execution_settings",
})

_SAFE_TEXT_RE = re.compile(r"^[^\x00-\x20\x7f]{1,256}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,120}$")


class MozziSubtitleBackendError(RuntimeError):
    """Fail-closed error for the CT121 Mozzi restricted-SSH backend."""


SSH: Final[tuple[str, ...]] = (
    "ssh", "-F", "/dev/null", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
    "-o", "StrictHostKeyChecking=yes", "-o", "UpdateHostKeys=no", "-o", "IdentitiesOnly=yes",
    "-o", "GlobalKnownHostsFile=/dev/null", "-o", "ClearAllForwardings=yes", "-o", "ForwardAgent=no",
    "-o", "RequestTTY=no", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3",
    "-o", "UserKnownHostsFile=/root/.ssh/mozzi_stage11_candidate/known_hosts",
    "-i", "/root/.ssh/mozzi_stage11_candidate/id_ed25519",
    f"teddy@{MOZZI_TARGET_HOST}", MOZZI_TRANSPORT_PROTOCOL,
)


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _validate_no_model_overrides(req: Mapping[str, object]) -> None:
    if not isinstance(req, Mapping):
        raise MozziSubtitleBackendError("Mozzi request must be a JSON object")
    forbidden = MOZZI_FORBIDDEN_REQUEST_KEYS.intersection(req.keys())
    if forbidden:
        raise MozziSubtitleBackendError(
            "Mozzi backend forbids model/config override fields: "
            + ",".join(sorted(forbidden))
        )


def _extract_server_profile_evidence(raw: Mapping[str, object]) -> dict[str, str] | None:
    """Extract optional server-reported profile metadata strictly as evidence."""
    evidence: dict[str, str] = {}
    for key in ("provider", "model", "reasoning_effort", "reasoning", "hermes_version"):
        if key in raw and raw[key] is not None:
            val = raw[key]
            if type(val) is not str or not _SAFE_TEXT_RE.fullmatch(val):
                raise MozziSubtitleBackendError(f"Invalid server-reported {key} evidence")
            canonical_key = "reasoning_effort" if key == "reasoning" else key
            if canonical_key in evidence and evidence[canonical_key] != val:
                raise MozziSubtitleBackendError("Conflicting server-reported reasoning evidence")
            evidence[canonical_key] = val
    if "profile_config_sha256" in raw and raw["profile_config_sha256"] is not None:
        digest = raw["profile_config_sha256"]
        if type(digest) is not str or not _SHA256_RE.fullmatch(digest):
            raise MozziSubtitleBackendError("Invalid server-reported profile_config_sha256")
        evidence["profile_config_sha256"] = digest
    return evidence or None


def _call(
    req: Mapping[str, object],
    timeout: int,
    *,
    ssh_argv: tuple[str, ...] = SSH,
    runner: Callable[..., object] = subprocess.run,
) -> dict[str, object]:
    _validate_no_model_overrides(req)
    payload = json.dumps(req, separators=(",", ":"), allow_nan=False).encode("ascii")
    try:
        result = runner(ssh_argv, input=payload, capture_output=True, timeout=timeout)
        stdout = getattr(result, "stdout", b"")
        returncode = getattr(result, "returncode", 1)
        if not isinstance(stdout, bytes) or len(stdout) > MOZZI_MAX_WIRE_BYTES:
            raise ValueError("wire stdout invalid")
        parsed = json.loads(stdout)
        if returncode or not isinstance(parsed, dict):
            raise ValueError("nonzero returncode or non-object response")
        return parsed
    except MozziSubtitleBackendError:
        raise
    except (ValueError, subprocess.SubprocessError, OSError) as exc:
        raise MozziSubtitleBackendError("Mozzi subtitle candidate transport failed") from None


def health(
    *,
    ssh_argv: tuple[str, ...] = SSH,
    runner: Callable[..., object] = subprocess.run,
) -> dict[str, object]:
    r = _call({"operation": "health"}, MOZZI_HEALTH_TIMEOUT_SECONDS, ssh_argv=ssh_argv, runner=runner)
    if (
        r.get("status") != "ready"
        or r.get("profile") != MOZZI_PROFILE_NAME
        or r.get("tools_count") != 0
    ):
        raise MozziSubtitleBackendError("Mozzi subtitle profile did not pass the tool guard")
    evidence = _extract_server_profile_evidence(r)
    out = dict(r)
    if evidence is not None:
        out["server_reported_profile_evidence"] = evidence
    return out


def run_native_candidate(
    prompt: bytes,
    *,
    ssh_argv: tuple[str, ...] = SSH,
    runner: Callable[..., object] = subprocess.run,
) -> tuple[bytes, bytes, dict[str, object]]:
    """Return (stdout bytes, stderr bytes, verified receipt) for the Stage11 semantic validator."""
    if not isinstance(prompt, bytes) or not 1 <= len(prompt) <= MOZZI_MAX_PROMPT_BYTES:
        raise MozziSubtitleBackendError("Invalid Stage11 prompt length")
    try:
        prompt.decode("utf-8", "strict")
    except UnicodeDecodeError:
        raise MozziSubtitleBackendError("Stage11 prompt must be UTF-8") from None

    prompt_digest = sha(prompt)
    request = {
        "operation": "translate",
        "prompt": base64.b64encode(prompt).decode("ascii"),
        "prompt_sha256": prompt_digest,
    }
    r = _call(request, MOZZI_TRANSLATE_TIMEOUT_SECONDS, ssh_argv=ssh_argv, runner=runner)
    try:
        if (
            r["status"] != "ok"
            or r["tools_count"] != 0
            or r["profile"] != MOZZI_PROFILE_NAME
            or r["returncode"] != 0
            or r["timeout_reason"] is not None
            or r["prompt_sha256"] != prompt_digest
        ):
            raise ValueError("receipt status/guard mismatch")
        out = base64.b64decode(r["stdout"], validate=True)
        if not out or len(out) > MOZZI_MAX_STDOUT_BYTES or sha(out) != r["stdout_sha256"] or r["stderr"] != "":
            raise ValueError("stdout/stderr validation failed")
        sid = r.get("runtime_session_id")
        if not isinstance(sid, str) or not _SESSION_ID_RE.fullmatch(sid):
            raise ValueError("invalid runtime_session_id")
        server_profile_evidence = _extract_server_profile_evidence(r)
        receipt = {k: v for k, v in r.items() if k not in ("stdout", "stderr")}
        receipt["backend"] = MOZZI_BACKEND_ID
        receipt["target_server"] = MOZZI_TARGET_SERVER
        receipt["target_host"] = MOZZI_TARGET_HOST
        receipt["transport"] = MOZZI_TRANSPORT_PROTOCOL
        receipt["profile_authority"] = MOZZI_PROFILE_AUTHORITY
        receipt["model_override_count"] = 0
        receipt["server_reported_profile_evidence"] = server_profile_evidence
        return out, b"", receipt
    except MozziSubtitleBackendError:
        raise
    except (KeyError, TypeError, ValueError):
        raise MozziSubtitleBackendError("Invalid or incomplete Mozzi subtitle receipt") from None


@dataclass(frozen=True)
class MozziSubtitleBackend:
    """Isolated opt-in CT121 Mozzi translation backend adapter."""

    ssh_argv: tuple[str, ...] = SSH
    runner: Callable[..., object] = subprocess.run

    def __post_init__(self) -> None:
        if (
            type(self.ssh_argv) is not tuple
            or not self.ssh_argv
            or self.ssh_argv[-1] != MOZZI_TRANSPORT_PROTOCOL
        ):
            raise MozziSubtitleBackendError("Mozzi backend requires forced-command SSH argv")
        if not callable(self.runner):
            raise MozziSubtitleBackendError("Mozzi backend runner must be callable")

    def backend_identity(self) -> dict[str, object]:
        return {
            "backend": MOZZI_BACKEND_ID,
            "target_server": MOZZI_TARGET_SERVER,
            "target_host": MOZZI_TARGET_HOST,
            "transport": MOZZI_TRANSPORT_PROTOCOL,
            "profile": MOZZI_PROFILE_NAME,
            "profile_authority": MOZZI_PROFILE_AUTHORITY,
            "model_override_count": 0,
        }

    def health(self) -> dict[str, object]:
        return health(ssh_argv=self.ssh_argv, runner=self.runner)

    def run_native_candidate(self, prompt: bytes) -> tuple[bytes, bytes, dict[str, object]]:
        return run_native_candidate(prompt, ssh_argv=self.ssh_argv, runner=self.runner)


__all__ = [
    "MOZZI_BACKEND_ID",
    "MOZZI_FORBIDDEN_REQUEST_KEYS",
    "MOZZI_HEALTH_TIMEOUT_SECONDS",
    "MOZZI_MAX_PROMPT_BYTES",
    "MOZZI_MAX_STDOUT_BYTES",
    "MOZZI_MAX_WIRE_BYTES",
    "MOZZI_PROFILE_AUTHORITY",
    "MOZZI_PROFILE_NAME",
    "MOZZI_TARGET_HOST",
    "MOZZI_TARGET_SERVER",
    "MOZZI_TRANSLATE_TIMEOUT_SECONDS",
    "MOZZI_TRANSPORT_PROTOCOL",
    "MozziSubtitleBackend",
    "MozziSubtitleBackendError",
    "SSH",
    "health",
    "run_native_candidate",
    "sha",
]
