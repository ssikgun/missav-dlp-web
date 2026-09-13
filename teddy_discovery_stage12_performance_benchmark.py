"""Isolated Stage12 performance benchmark partition and telemetry contract.

This module is benchmark-only.  It does not invoke Hermes, a subtitle
provider, STT, NAS, Jellyfin, or the Stage12 rollout state store.  Production
stateful translation continues to use ``STATEFUL_PART_BATCH_SIZE == 16`` and
its existing plan/validator/resume contract.

The benchmark input is the exact serialized semantic package already supplied
to the production controller.  A 64-cue manifest is derived from those bytes
and can be staged under a separately configured benchmark root.  The manifest
and identity checks are deliberately independent of the production 16-cue
``ExpectedStatefulPart`` type so that the two state spaces cannot be mixed.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import time
import uuid
from typing import Final

from teddy_discovery_stateful_translator import (
    StatefulSubtitlePackage,
    StatefulTranslatorError,
    parse_stateful_package,
)


BENCHMARK_MANIFEST_SCHEMA_VERSION: Final[int] = 1
BENCHMARK_POLICY_ID: Final[str] = "benchmark-stateful-cue64-v1"
BENCHMARK_MAX_CUES_PER_PART: Final[int] = 64
BENCHMARK_ROOT: Final[Path] = Path(
    "/opt/missav-dlp-web/discovery/stage12-performance-benchmark"
)
BENCHMARK_REMOTE_ROOT: Final[str] = (
    "/home/teddy/stage12-performance-benchmark"
)
BENCHMARK_INPUT_FILENAME: Final[str] = "stage11-semantic-input.json"
BENCHMARK_MANIFEST_FILENAME: Final[str] = "partition-manifest.json"
BENCHMARK_REPORT_FILENAME: Final[str] = "benchmark-result.json"
BENCHMARK_SESSION_NAMESPACE: Final[uuid.UUID] = uuid.UUID(
    "d4b7c3d3-4de7-5fb8-a8a8-9c20f4aa6d42"
)
TOKEN_USAGE_UNAVAILABLE: Final[str] = "TOKEN_USAGE_UNAVAILABLE"
TOKEN_USAGE_AVAILABLE: Final[str] = "AVAILABLE"
PRIVATE_DIRECTORY_MODE: Final[int] = 0o700
PRIVATE_FILE_MODE: Final[int] = 0o600
MAX_MANIFEST_BYTES: Final[int] = 16 * 1024 * 1024
MAX_REPORT_BYTES: Final[int] = 16 * 1024 * 1024

PRODUCTION_PROTECTED_PATHS: Final[tuple[Path, ...]] = (
    Path("/opt/missav-dlp-web/discovery/stage12-rollout-state.sqlite3"),
    Path("/opt/missav-dlp-web/discovery/stage11-canary-artifacts"),
    Path("/opt/missav-dlp-web/discovery/stage11-canary-staging"),
    Path("/opt/missav-dlp-web/discovery/teddy-discovery.sqlite3"),
)

_SAFE_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CUE_ID_MAX_CHARS = 256


class BenchmarkHarnessError(ValueError):
    """Base class for benchmark-only contract failures."""


class BenchmarkPolicyError(BenchmarkHarnessError):
    """Raised when a benchmark policy is not the supported 64-cue policy."""


class BenchmarkIsolationError(BenchmarkHarnessError):
    """Raised when a benchmark path or identity could cross production state."""


class BenchmarkInputMismatchError(BenchmarkIsolationError):
    """Raised when staged input bytes do not match an existing input file."""


class BenchmarkResumeMismatchError(BenchmarkIsolationError):
    """Raised when existing benchmark state cannot resume this manifest."""


class BenchmarkManifestError(BenchmarkHarnessError):
    """Raised when a partition manifest is malformed or inconsistent."""


class BenchmarkTelemetryError(BenchmarkHarnessError):
    """Raised when benchmark telemetry violates its recording contract."""


def _require_exact_text(
    value: object,
    field_name: str,
    *,
    max_chars: int = _CUE_ID_MAX_CHARS,
) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise BenchmarkManifestError(field_name + " must be a nonempty string")
    if len(value) > max_chars:
        raise BenchmarkManifestError(field_name + " exceeds its bounded length")
    if any(
        ord(character) < 32
        or ord(character) == 127
        or character.isspace()
        for character in value
    ):
        raise BenchmarkManifestError(
            field_name + " contains unsafe whitespace or control data"
        )
    return value


def _require_component(value: object, field_name: str) -> str:
    text = _require_exact_text(value, field_name)
    if _SAFE_COMPONENT_RE.fullmatch(text) is None:
        raise BenchmarkIsolationError(field_name + " is not a safe path component")
    return text


def _require_sha256(value: object, field_name: str = "input_sha256") -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise BenchmarkManifestError(field_name + " must be lowercase SHA256")
    return value


def _require_uuid(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise BenchmarkManifestError(field_name + " must be a canonical UUID")
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, TypeError, ValueError) as error:
        raise BenchmarkManifestError(
            field_name + " must be a canonical UUID"
        ) from error
    if str(parsed) != value:
        raise BenchmarkManifestError(field_name + " must be a canonical UUID")
    return value


def _validate_supported_policy(policy_id: object) -> str:
    policy = _require_component(policy_id, "policy_id")
    if not policy.startswith("benchmark-"):
        raise BenchmarkPolicyError("policy_id must identify a benchmark policy")
    return policy


def _resolved_absolute_path(value: Path | str, field_name: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        raise BenchmarkIsolationError(field_name + " must be absolute")
    return candidate.resolve(strict=False)


def _paths_overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def validate_isolated_root(root: Path | str) -> Path:
    """Validate a benchmark root without creating or touching it."""

    resolved = _resolved_absolute_path(root, "benchmark root")
    if resolved == Path("/"):
        raise BenchmarkIsolationError("benchmark root is too broad")
    for protected in PRODUCTION_PROTECTED_PATHS:
        if _paths_overlap(resolved, protected.resolve(strict=False)):
            raise BenchmarkIsolationError(
                "benchmark root overlaps protected production path"
            )
    return resolved


def _validate_package_and_input(
    package: StatefulSubtitlePackage,
    semantic_input_bytes: bytes,
) -> StatefulSubtitlePackage:
    if type(package) is not StatefulSubtitlePackage:
        raise BenchmarkInputMismatchError("package has the wrong exact type")
    if type(semantic_input_bytes) is not bytes or not semantic_input_bytes:
        raise BenchmarkInputMismatchError("semantic input must be exact bytes")
    try:
        parsed = parse_stateful_package(semantic_input_bytes)
    except StatefulTranslatorError as error:
        raise BenchmarkInputMismatchError(
            "semantic input is not a valid stateful package"
        ) from error
    if parsed != package:
        raise BenchmarkInputMismatchError(
            "semantic input does not match the supplied package"
        )
    return parsed


@dataclass(frozen=True)
class BenchmarkPartition:
    """One ordered 64-cue range in the isolated benchmark manifest."""

    part_index: int
    first_cue_id: str
    last_cue_id: str
    cue_ids: tuple[str, ...]

    def __post_init__(self):
        if type(self.part_index) is not int or self.part_index <= 0:
            raise BenchmarkManifestError("part_index must be positive")
        _require_exact_text(self.first_cue_id, "first_cue_id")
        _require_exact_text(self.last_cue_id, "last_cue_id")
        if type(self.cue_ids) is not tuple or not self.cue_ids:
            raise BenchmarkManifestError("cue_ids must be a nonempty tuple")
        if len(self.cue_ids) > BENCHMARK_MAX_CUES_PER_PART:
            raise BenchmarkPolicyError("benchmark part exceeds 64 cues")
        for cue_id in self.cue_ids:
            _require_exact_text(cue_id, "cue_id")
        if self.cue_ids[0] != self.first_cue_id:
            raise BenchmarkManifestError("first cue identity is detached")
        if self.cue_ids[-1] != self.last_cue_id:
            raise BenchmarkManifestError("last cue identity is detached")
        if len(set(self.cue_ids)) != len(self.cue_ids):
            raise BenchmarkManifestError("part cue IDs must be unique")

    @property
    def cue_count(self) -> int:
        return len(self.cue_ids)

    def to_dict(self) -> dict[str, object]:
        return {
            "part_index": self.part_index,
            "first_cue_id": self.first_cue_id,
            "last_cue_id": self.last_cue_id,
            "cue_count": self.cue_count,
            "cue_ids": list(self.cue_ids),
        }


@dataclass(frozen=True)
class BenchmarkPartitionManifest:
    """Deterministic identity and ranges for one benchmark input."""

    manifest_schema_version: int
    policy_id: str
    max_cues_per_part: int
    dvd_id: str
    generation_key: str
    claim_token: int
    benchmark_session_id: str
    input_sha256: str
    semantic_cue_count: int
    parts: tuple[BenchmarkPartition, ...]

    def __post_init__(self):
        if self.manifest_schema_version != BENCHMARK_MANIFEST_SCHEMA_VERSION:
            raise BenchmarkManifestError("unsupported benchmark manifest version")
        _validate_supported_policy(self.policy_id)
        if self.max_cues_per_part != BENCHMARK_MAX_CUES_PER_PART:
            raise BenchmarkPolicyError("only the 64-cue policy is supported")
        _require_component(self.dvd_id, "dvd_id")
        _require_exact_text(self.generation_key, "generation_key")
        if type(self.claim_token) is not int or self.claim_token < 0:
            raise BenchmarkManifestError("claim_token must be nonnegative")
        _require_uuid(self.benchmark_session_id, "benchmark_session_id")
        _require_sha256(self.input_sha256)
        if type(self.semantic_cue_count) is not int or self.semantic_cue_count <= 0:
            raise BenchmarkManifestError("semantic_cue_count must be positive")
        if type(self.parts) is not tuple or not self.parts:
            raise BenchmarkManifestError("parts must be a nonempty tuple")
        if any(type(part) is not BenchmarkPartition for part in self.parts):
            raise BenchmarkManifestError("parts contain a detached partition")
        if tuple(part.part_index for part in self.parts) != tuple(
            range(1, len(self.parts) + 1)
        ):
            raise BenchmarkManifestError("part indices must be contiguous")
        flattened = tuple(
            cue_id for part in self.parts for cue_id in part.cue_ids
        )
        if len(flattened) != self.semantic_cue_count:
            raise BenchmarkManifestError("part cue counts do not cover the input")
        if len(set(flattened)) != len(flattened):
            raise BenchmarkManifestError("manifest contains duplicate cue IDs")

    @property
    def part_count(self) -> int:
        return len(self.parts)

    @property
    def cue_ids(self) -> tuple[str, ...]:
        return tuple(cue_id for part in self.parts for cue_id in part.cue_ids)

    def to_dict(self) -> dict[str, object]:
        return {
            "manifest_schema_version": self.manifest_schema_version,
            "policy_id": self.policy_id,
            "max_cues_per_part": self.max_cues_per_part,
            "dvd_id": self.dvd_id,
            "generation_key": self.generation_key,
            "claim_token": self.claim_token,
            "benchmark_session_id": self.benchmark_session_id,
            "input_sha256": self.input_sha256,
            "semantic_cue_count": self.semantic_cue_count,
            "part_count": self.part_count,
            "parts": [part.to_dict() for part in self.parts],
        }

    def to_bytes(self) -> bytes:
        try:
            payload = json.dumps(
                self.to_dict(),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, UnicodeError, ValueError) as error:
            raise BenchmarkManifestError(
                "manifest cannot be serialized deterministically"
            ) from error
        if len(payload) > MAX_MANIFEST_BYTES:
            raise BenchmarkManifestError("manifest exceeds its bounded size")
        return payload


def _reject_json_constant(value: str):
    raise BenchmarkManifestError("JSON constants are not accepted")


def _reject_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise BenchmarkManifestError("duplicate JSON object key")
        result[key] = value
    return result


def parse_benchmark_manifest(payload: bytes) -> BenchmarkPartitionManifest:
    if type(payload) is not bytes or not payload or len(payload) > MAX_MANIFEST_BYTES:
        raise BenchmarkManifestError("manifest payload is outside its bound")
    try:
        parsed = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except BenchmarkManifestError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise BenchmarkManifestError("manifest is not valid JSON") from error
    if type(parsed) is not dict:
        raise BenchmarkManifestError("manifest root must be an object")
    expected_fields = {
        "manifest_schema_version",
        "policy_id",
        "max_cues_per_part",
        "dvd_id",
        "generation_key",
        "claim_token",
        "benchmark_session_id",
        "input_sha256",
        "semantic_cue_count",
        "part_count",
        "parts",
    }
    if set(parsed) != expected_fields:
        raise BenchmarkManifestError("manifest fields are not exact")
    raw_parts = parsed["parts"]
    if type(raw_parts) is not list:
        raise BenchmarkManifestError("manifest parts must be an array")
    parts: list[BenchmarkPartition] = []
    for raw_part in raw_parts:
        if type(raw_part) is not dict:
            raise BenchmarkManifestError("manifest part must be an object")
        if set(raw_part) != {
            "part_index",
            "first_cue_id",
            "last_cue_id",
            "cue_count",
            "cue_ids",
        }:
            raise BenchmarkManifestError("manifest part fields are not exact")
        cue_ids = raw_part["cue_ids"]
        if type(cue_ids) is not list:
            raise BenchmarkManifestError("manifest cue_ids must be an array")
        part = BenchmarkPartition(
            part_index=raw_part["part_index"],
            first_cue_id=raw_part["first_cue_id"],
            last_cue_id=raw_part["last_cue_id"],
            cue_ids=tuple(cue_ids),
        )
        if raw_part["cue_count"] != part.cue_count:
            raise BenchmarkManifestError("manifest cue_count is detached")
        parts.append(part)
    try:
        manifest = BenchmarkPartitionManifest(
            manifest_schema_version=parsed["manifest_schema_version"],
            policy_id=parsed["policy_id"],
            max_cues_per_part=parsed["max_cues_per_part"],
            dvd_id=parsed["dvd_id"],
            generation_key=parsed["generation_key"],
            claim_token=parsed["claim_token"],
            benchmark_session_id=parsed["benchmark_session_id"],
            input_sha256=parsed["input_sha256"],
            semantic_cue_count=parsed["semantic_cue_count"],
            parts=tuple(parts),
        )
    except (TypeError, ValueError, OverflowError) as error:
        raise BenchmarkManifestError("manifest values are invalid") from error
    if parsed["part_count"] != manifest.part_count:
        raise BenchmarkManifestError("manifest part_count is detached")
    return manifest


def benchmark_session_id_for_identity(
    *,
    dvd_id: str,
    policy_id: str,
    input_sha256: str,
) -> str:
    """Return a benchmark-only deterministic session identity."""

    dvd = _require_component(dvd_id, "dvd_id")
    policy = _validate_supported_policy(policy_id)
    source_sha = _require_sha256(input_sha256)
    return str(
        uuid.uuid5(
            BENCHMARK_SESSION_NAMESPACE,
            dvd + "\x00" + policy + "\x00" + source_sha,
        )
    )


def build_benchmark_manifest(
    package: StatefulSubtitlePackage,
    semantic_input_bytes: bytes,
    *,
    policy_id: str = BENCHMARK_POLICY_ID,
) -> BenchmarkPartitionManifest:
    """Build a deterministic 64-cue manifest from exact production input."""

    validated_package = _validate_package_and_input(
        package,
        semantic_input_bytes,
    )
    policy = _validate_supported_policy(policy_id)
    input_sha256 = hashlib.sha256(semantic_input_bytes).hexdigest()
    cue_ids = tuple(cue.cue_id for cue in validated_package.cues)
    parts = tuple(
        BenchmarkPartition(
            part_index=part_index,
            first_cue_id=cue_ids[start],
            last_cue_id=cue_ids[
                min(start + BENCHMARK_MAX_CUES_PER_PART, len(cue_ids)) - 1
            ],
            cue_ids=cue_ids[
                start : start + BENCHMARK_MAX_CUES_PER_PART
            ],
        )
        for part_index, start in enumerate(
            range(0, len(cue_ids), BENCHMARK_MAX_CUES_PER_PART),
            start=1,
        )
    )
    return BenchmarkPartitionManifest(
        manifest_schema_version=BENCHMARK_MANIFEST_SCHEMA_VERSION,
        policy_id=policy,
        max_cues_per_part=BENCHMARK_MAX_CUES_PER_PART,
        dvd_id=validated_package.dvd_id,
        generation_key=validated_package.generation_key,
        claim_token=validated_package.claim_token,
        benchmark_session_id=benchmark_session_id_for_identity(
            dvd_id=validated_package.dvd_id,
            policy_id=policy,
            input_sha256=input_sha256,
        ),
        input_sha256=input_sha256,
        semantic_cue_count=len(cue_ids),
        parts=parts,
    )


def assert_benchmark_resume_compatible(
    existing: BenchmarkPartitionManifest,
    current: BenchmarkPartitionManifest,
) -> None:
    """Fail closed unless an existing benchmark state is the same identity."""

    if type(existing) is not BenchmarkPartitionManifest:
        raise BenchmarkResumeMismatchError("existing manifest has wrong type")
    if type(current) is not BenchmarkPartitionManifest:
        raise BenchmarkResumeMismatchError("current manifest has wrong type")
    if existing.policy_id != current.policy_id:
        raise BenchmarkResumeMismatchError("benchmark policy identity changed")
    if existing.input_sha256 != current.input_sha256:
        raise BenchmarkResumeMismatchError("benchmark input SHA changed")
    if existing.to_bytes() != current.to_bytes():
        raise BenchmarkResumeMismatchError(
            "benchmark manifest identity or partition boundaries changed"
        )


@dataclass(frozen=True)
class BenchmarkLayout:
    """Private filesystem layout for one title and benchmark policy."""

    root: Path
    title_root: Path
    manifests: Path
    inputs: Path
    pending: Path
    promoted: Path
    reports: Path
    logs: Path
    dvd_id: str
    policy_id: str

    @property
    def manifest_path(self) -> Path:
        return self.manifests / BENCHMARK_MANIFEST_FILENAME

    @property
    def input_path(self) -> Path:
        return self.inputs / BENCHMARK_INPUT_FILENAME

    @property
    def report_path(self) -> Path:
        return self.reports / BENCHMARK_REPORT_FILENAME

    def pending_part_path(self, part_index: int) -> Path:
        return self.pending / benchmark_part_filename(part_index, pending=True)

    def promoted_part_path(self, part_index: int) -> Path:
        return self.promoted / benchmark_part_filename(part_index, pending=False)


def benchmark_part_filename(part_index: int, *, pending: bool) -> str:
    if type(part_index) is not int or part_index <= 0 or part_index > 9999:
        raise BenchmarkManifestError("part_index is outside filename bounds")
    suffix = ".pending.json" if pending else ".json"
    return f"benchmark-part-{part_index:04d}{suffix}"


def create_benchmark_layout(
    root: Path | str,
    *,
    dvd_id: str,
    policy_id: str = BENCHMARK_POLICY_ID,
) -> BenchmarkLayout:
    """Create only the isolated benchmark directories requested by the caller."""

    isolated_root = validate_isolated_root(root)
    safe_dvd_id = _require_component(dvd_id, "dvd_id")
    safe_policy = _validate_supported_policy(policy_id)
    title_root = isolated_root / safe_dvd_id / safe_policy
    directories = {
        "manifests": title_root / "manifests",
        "inputs": title_root / "inputs",
        "pending": title_root / "pending",
        "promoted": title_root / "promoted",
        "reports": title_root / "reports",
        "logs": title_root / "logs",
    }
    for directory in (isolated_root, isolated_root / safe_dvd_id, title_root):
        if directory.is_symlink():
            raise BenchmarkIsolationError("benchmark path must not be a symlink")
        if directory.exists() and not directory.is_dir():
            raise BenchmarkIsolationError("benchmark path is not a directory")
        directory.mkdir(mode=PRIVATE_DIRECTORY_MODE, parents=True, exist_ok=True)
        os.chmod(directory, PRIVATE_DIRECTORY_MODE)
    for directory in directories.values():
        if directory.is_symlink():
            raise BenchmarkIsolationError(
                "benchmark subpath must not be a symlink"
            )
        if directory.exists() and not directory.is_dir():
            raise BenchmarkIsolationError("benchmark subpath is not a directory")
        directory.mkdir(mode=PRIVATE_DIRECTORY_MODE, exist_ok=True)
        os.chmod(directory, PRIVATE_DIRECTORY_MODE)
    return BenchmarkLayout(
        root=isolated_root,
        title_root=title_root,
        manifests=directories["manifests"],
        inputs=directories["inputs"],
        pending=directories["pending"],
        promoted=directories["promoted"],
        reports=directories["reports"],
        logs=directories["logs"],
        dvd_id=safe_dvd_id,
        policy_id=safe_policy,
    )


def _write_immutable_private(path: Path, payload: bytes, *, label: str) -> Path:
    if type(payload) is not bytes or not payload:
        raise BenchmarkIsolationError(label + " must be nonempty bytes")
    if path.is_symlink():
        raise BenchmarkIsolationError(label + " path must not be a symlink")
    path.parent.mkdir(mode=PRIVATE_DIRECTORY_MODE, parents=True, exist_ok=True)
    temporary = path.with_name(
        "." + path.name + ".tmp-" + uuid.uuid4().hex
    )
    file_descriptor = None
    try:
        file_descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            PRIVATE_FILE_MODE,
        )
        with os.fdopen(file_descriptor, "wb", closefd=True) as output:
            file_descriptor = None
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink():
                raise BenchmarkIsolationError(
                    label + " path must not be a symlink"
                )
            if not path.is_file() or path.read_bytes() != payload:
                raise BenchmarkIsolationError(label + " conflicts with existing file")
        return path
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def install_benchmark_input(
    layout: BenchmarkLayout,
    package: StatefulSubtitlePackage,
    semantic_input_bytes: bytes,
) -> Path:
    """Install exact semantic input bytes without overwriting existing input."""

    _validate_package_and_input(package, semantic_input_bytes)
    return _write_immutable_private(
        layout.input_path,
        semantic_input_bytes,
        label="benchmark input",
    )


def write_benchmark_manifest(
    layout: BenchmarkLayout,
    manifest: BenchmarkPartitionManifest,
) -> Path:
    if manifest.dvd_id != layout.dvd_id or manifest.policy_id != layout.policy_id:
        raise BenchmarkIsolationError("manifest does not match benchmark layout")
    return _write_immutable_private(
        layout.manifest_path,
        manifest.to_bytes(),
        label="benchmark manifest",
    )


def read_benchmark_manifest(layout: BenchmarkLayout) -> BenchmarkPartitionManifest:
    try:
        payload = layout.manifest_path.read_bytes()
    except OSError as error:
        raise BenchmarkManifestError("benchmark manifest cannot be read") from error
    return parse_benchmark_manifest(payload)


def benchmark_remote_task_path(
    manifest: BenchmarkPartitionManifest,
    *,
    remote_root: str = BENCHMARK_REMOTE_ROOT,
) -> str:
    """Return a benchmark-only remote task identity; no remote call is made."""

    root = PurePosixPath(remote_root)
    if not root.is_absolute() or ".." in root.parts:
        raise BenchmarkIsolationError("remote benchmark root is unsafe")
    _require_component(manifest.dvd_id, "dvd_id")
    _validate_supported_policy(manifest.policy_id)
    return str(
        root
        / manifest.dvd_id
        / manifest.policy_id
        / manifest.benchmark_session_id
    )


def evaluate_cue_identity(
    expected_cue_ids: Sequence[str],
    observed_cue_ids: Sequence[str],
) -> tuple[bool, bool]:
    """Return ``(coverage_pass, order_pass)`` with duplicate detection."""

    expected = tuple(expected_cue_ids)
    observed = tuple(observed_cue_ids)
    coverage_pass = len(observed) == len(expected) and Counter(observed) == Counter(
        expected
    )
    return coverage_pass, coverage_pass and observed == expected


def _json_safe_mapping(value: Mapping[str, object]) -> dict[str, object]:
    if type(value) is not dict:
        value = dict(value)
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        )
        parsed = json.loads(encoded)
    except (TypeError, UnicodeError, ValueError) as error:
        raise BenchmarkTelemetryError("token usage is not JSON-safe") from error
    if type(parsed) is not dict:
        raise BenchmarkTelemetryError("token usage must remain an object")
    return parsed


class BenchmarkTelemetryRecorder:
    """Monotonic-clock telemetry collector for a future isolated live run."""

    def __init__(
        self,
        manifest: BenchmarkPartitionManifest,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ):
        if type(manifest) is not BenchmarkPartitionManifest:
            raise BenchmarkTelemetryError("telemetry requires a benchmark manifest")
        self.manifest = manifest
        self._monotonic = monotonic
        self._started_at: float | None = None
        self._finished_at: float | None = None
        self._active_parts: dict[int, float] = {}
        self._part_elapsed: dict[int, float] = {}
        self._hermes_invocations = 0
        self._retry_count = 0
        self._timeout_count = 0
        self._validation_failure_count = 0
        self._resume_recovery_events: list[str] = []
        self._cue_coverage_pass = False
        self._cue_order_pass = False
        self._token_usage: dict[str, object] | None = None
        self._token_usage_status = TOKEN_USAGE_UNAVAILABLE

    def _require_started(self):
        if self._started_at is None:
            raise BenchmarkTelemetryError("telemetry has not started")

    def start(self) -> None:
        if self._started_at is not None:
            raise BenchmarkTelemetryError("telemetry already started")
        self._started_at = self._monotonic()

    def start_part(self, part_index: int) -> None:
        self._require_started()
        if part_index not in {part.part_index for part in self.manifest.parts}:
            raise BenchmarkTelemetryError("unknown benchmark part")
        if part_index in self._active_parts or part_index in self._part_elapsed:
            raise BenchmarkTelemetryError("benchmark part timing already recorded")
        self._active_parts[part_index] = self._monotonic()

    def finish_part(self, part_index: int) -> float:
        self._require_started()
        started = self._active_parts.pop(part_index, None)
        if started is None:
            raise BenchmarkTelemetryError("benchmark part timing was not started")
        elapsed = self._monotonic() - started
        if elapsed < 0:
            raise BenchmarkTelemetryError("monotonic clock moved backwards")
        self._part_elapsed[part_index] = elapsed
        return elapsed

    def finish(self) -> float:
        self._require_started()
        if self._active_parts:
            raise BenchmarkTelemetryError("active benchmark part was not finished")
        if self._finished_at is not None:
            raise BenchmarkTelemetryError("telemetry already finished")
        self._finished_at = self._monotonic()
        elapsed = self._finished_at - self._started_at
        if elapsed < 0:
            raise BenchmarkTelemetryError("monotonic clock moved backwards")
        return elapsed

    @staticmethod
    def _increment(value: int, amount: int, field_name: str) -> int:
        if type(amount) is not int or amount < 0:
            raise BenchmarkTelemetryError(field_name + " increment must be nonnegative")
        return value + amount

    def record_invocation(self, count: int = 1) -> None:
        self._require_started()
        self._hermes_invocations = self._increment(
            self._hermes_invocations,
            count,
            "Hermes invocation",
        )

    def record_retry(self, count: int = 1) -> None:
        self._require_started()
        self._retry_count = self._increment(self._retry_count, count, "retry")

    def record_timeout(self, count: int = 1) -> None:
        self._require_started()
        self._timeout_count = self._increment(
            self._timeout_count,
            count,
            "timeout",
        )

    def record_validation_failure(self, count: int = 1) -> None:
        self._require_started()
        self._validation_failure_count = self._increment(
            self._validation_failure_count,
            count,
            "validation failure",
        )

    def record_resume_recovery(self, event: str) -> None:
        self._require_started()
        self._resume_recovery_events.append(
            _require_exact_text(event, "resume recovery event", max_chars=256)
        )

    def record_cue_identity(self, observed_cue_ids: Sequence[str]) -> None:
        self._require_started()
        self._cue_coverage_pass, self._cue_order_pass = evaluate_cue_identity(
            self.manifest.cue_ids,
            observed_cue_ids,
        )

    def record_token_usage(self, usage: Mapping[str, object]) -> None:
        self._require_started()
        self._token_usage = _json_safe_mapping(usage)
        self._token_usage_status = TOKEN_USAGE_AVAILABLE

    def mark_token_usage_unavailable(self) -> None:
        self._require_started()
        self._token_usage = None
        self._token_usage_status = TOKEN_USAGE_UNAVAILABLE

    def build_report(self) -> dict[str, object]:
        if self._started_at is None or self._finished_at is None:
            raise BenchmarkTelemetryError("telemetry must be finished before reporting")
        elapsed = self._finished_at - self._started_at
        return {
            "dvd_id": self.manifest.dvd_id,
            "policy_id": self.manifest.policy_id,
            "semantic_cue_count": self.manifest.semantic_cue_count,
            "planned_parts": self.manifest.part_count,
            "hermes_invocations": self._hermes_invocations,
            "retry_count": self._retry_count,
            "timeout_count": self._timeout_count,
            "validation_failure_count": self._validation_failure_count,
            "elapsed_seconds": elapsed,
            "per_part_elapsed_seconds": [
                {
                    "part_index": part_index,
                    "elapsed_seconds": self._part_elapsed[part_index],
                }
                for part_index in sorted(self._part_elapsed)
            ],
            "resume_recovery_events": list(self._resume_recovery_events),
            "cue_coverage_pass": self._cue_coverage_pass,
            "cue_order_pass": self._cue_order_pass,
            "token_usage": self._token_usage,
            "token_usage_status": self._token_usage_status,
        }


def serialize_benchmark_report(report: Mapping[str, object]) -> bytes:
    if type(report) is not dict:
        report = dict(report)
    try:
        payload = json.dumps(
            report,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, UnicodeError, ValueError) as error:
        raise BenchmarkTelemetryError("benchmark report is not JSON-safe") from error
    if not payload or len(payload) > MAX_REPORT_BYTES:
        raise BenchmarkTelemetryError("benchmark report exceeds its bound")
    return payload


def write_benchmark_report(
    layout: BenchmarkLayout,
    report: Mapping[str, object],
) -> Path:
    if report.get("dvd_id") != layout.dvd_id:
        raise BenchmarkIsolationError("benchmark report title does not match layout")
    if report.get("policy_id") != layout.policy_id:
        raise BenchmarkIsolationError(
            "benchmark report policy does not match layout"
        )
    return _write_immutable_private(
        layout.report_path,
        serialize_benchmark_report(report),
        label="benchmark report",
    )


__all__ = [
    "BENCHMARK_MANIFEST_SCHEMA_VERSION",
    "BENCHMARK_POLICY_ID",
    "BENCHMARK_MAX_CUES_PER_PART",
    "BENCHMARK_ROOT",
    "BENCHMARK_REMOTE_ROOT",
    "BENCHMARK_INPUT_FILENAME",
    "BENCHMARK_MANIFEST_FILENAME",
    "BENCHMARK_REPORT_FILENAME",
    "PRODUCTION_PROTECTED_PATHS",
    "TOKEN_USAGE_UNAVAILABLE",
    "TOKEN_USAGE_AVAILABLE",
    "BenchmarkHarnessError",
    "BenchmarkPolicyError",
    "BenchmarkIsolationError",
    "BenchmarkInputMismatchError",
    "BenchmarkResumeMismatchError",
    "BenchmarkManifestError",
    "BenchmarkTelemetryError",
    "BenchmarkPartition",
    "BenchmarkPartitionManifest",
    "BenchmarkLayout",
    "BenchmarkTelemetryRecorder",
    "benchmark_session_id_for_identity",
    "build_benchmark_manifest",
    "parse_benchmark_manifest",
    "assert_benchmark_resume_compatible",
    "validate_isolated_root",
    "create_benchmark_layout",
    "install_benchmark_input",
    "write_benchmark_manifest",
    "read_benchmark_manifest",
    "benchmark_part_filename",
    "benchmark_remote_task_path",
    "evaluate_cue_identity",
    "serialize_benchmark_report",
    "write_benchmark_report",
]
