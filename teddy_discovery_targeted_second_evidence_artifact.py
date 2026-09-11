"""Deterministic durable bytes for generic targeted second evidence.

This module is the ASR-first persistence boundary for the route-neutral
targeted second-evidence runner.  It deliberately does not use Hybrid
``ja-*`` identities or affine timing.  The baseline ASR source identity and
timing remain authoritative; targeted timings are preserved only as evidence
returned by a requested window.

The module performs no model, network, media, database, or semantic I/O.
Persistence is explicit through :func:`persist_targeted_second_evidence`.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Final

from teddy_discovery_asr import (
    ASRLimitError,
    ASRRuntimeIdentity,
    ASRSegment,
    ASRSourceSnapshot,
    ASRValidationError,
    ASRWord,
    MAX_ASR_SEGMENTS,
)
from teddy_discovery_targeted_asr_window import (
    STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1,
)
from teddy_discovery_targeted_second_evidence import (
    TARGETED_SECOND_EVIDENCE_STATUS_EMPTY_UNRESOLVED,
    TARGETED_SECOND_EVIDENCE_STATUS_NOISY_UNRESOLVED,
    TARGETED_SECOND_EVIDENCE_STATUS_PRESENT_UNRESOLVED,
    TargetedSecondEvidenceBinding,
    TargetedSecondEvidenceError,
    TargetedSecondEvidencePlan,
    TargetedSecondEvidenceSource,
    TargetedSecondEvidenceWindow,
    TargetedSecondEvidenceWindowResult,
    bind_targeted_second_evidence,
)
from teddy_discovery_targeted_second_evidence_runner import (
    TargetedSecondEvidenceExecution,
)


TARGETED_SECOND_EVIDENCE_ARTIFACT_SCHEMA_VERSION: Final[int] = 1
MAX_TARGETED_SECOND_EVIDENCE_ARTIFACT_BYTES: Final[int] = 64 * 1024 * 1024
MAX_TARGETED_SECOND_EVIDENCE_ARTIFACT_WINDOWS: Final[int] = 512
MAX_TARGETED_SECOND_EVIDENCE_ARTIFACT_SEGMENTS: Final[int] = 100_000
TARGETED_SECOND_EVIDENCE_ARTIFACT_FILE_MODE: Final[int] = 0o600

_SHA256_RE = r"[0-9a-f]{64}"
_VALID_STATUSES = frozenset(
    {
        TARGETED_SECOND_EVIDENCE_STATUS_PRESENT_UNRESOLVED,
        TARGETED_SECOND_EVIDENCE_STATUS_EMPTY_UNRESOLVED,
        TARGETED_SECOND_EVIDENCE_STATUS_NOISY_UNRESOLVED,
    }
)

_PAYLOAD_KEYS = (
    "schema_version",
    "source_snapshot",
    "baseline_asr_artifact_sha256",
    "runtime_identity",
    "engine_version",
    "policy_version",
    "binding_sha256",
    "sources",
    "windows",
    "results",
    "bindings",
)
_TOP_LEVEL_KEYS = _PAYLOAD_KEYS + ("artifact_sha256",)
_SOURCE_SNAPSHOT_KEYS = (
    "dvd_id",
    "canonical_video_relative",
    "source_size",
    "source_mtime_ns",
)
_RUNTIME_IDENTITY_KEYS = (
    "engine",
    "model",
    "device",
    "compute_type",
    "cpu_threads",
    "num_workers",
)
_SOURCE_KEYS = (
    "source_index",
    "cue_id",
    "start_ms",
    "end_ms",
    "source_text",
)
_WINDOW_KEYS = (
    "window_id",
    "start_ms",
    "end_ms",
    "source_ids",
    "source_indices",
)
_RESULT_KEYS = (
    "window_id",
    "window_start_ms",
    "window_end_ms",
    "plan_binding_sha256",
    "status",
    "segments",
)
_BINDING_KEYS = (
    "source_id",
    "window_id",
    "status",
    "provenance_digest",
)
_SEGMENT_KEYS = (
    "start_ms",
    "end_ms",
    "text",
    "words",
)
_WORD_KEYS = (
    "start_ms",
    "end_ms",
    "text",
)


class TargetedSecondEvidenceArtifactError(ValueError):
    """Base class for generic targeted second-evidence artifact failures."""


class TargetedSecondEvidenceArtifactValidationError(
    TargetedSecondEvidenceArtifactError,
):
    """Raised when an artifact is malformed or detached."""


class TargetedSecondEvidenceArtifactLimitError(
    TargetedSecondEvidenceArtifactError,
):
    """Raised when an artifact exceeds a fixed bounded resource limit."""


class TargetedSecondEvidenceArtifactPersistenceError(
    TargetedSecondEvidenceArtifactError,
):
    """Raised when a private new-file artifact cannot be installed safely."""


class _DuplicateArtifactKey(ValueError):
    """Internal JSON parser marker for duplicate object keys."""


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateArtifactKey("duplicate targeted evidence artifact key")
        result[key] = value
    return result


def _reject_nonstandard_number(value):
    raise ValueError("non-finite JSON number is not allowed")


def _require_exact_object(
    value: object,
    *,
    expected_keys: tuple[str, ...],
    field_name: str,
) -> dict[str, object]:
    if type(value) is not dict or set(value) != set(expected_keys):
        raise TargetedSecondEvidenceArtifactValidationError(
            field_name + " has an invalid exact key set"
        )
    return value


def _require_sha256(value: object, *, field_name: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise TargetedSecondEvidenceArtifactValidationError(
            field_name + " must be lowercase SHA-256"
        )
    return value


def _require_safe_string(value: object, *, field_name: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise TargetedSecondEvidenceArtifactValidationError(
            field_name + " must be a nonempty safe string"
        )
    return value


def _validated_snapshot(value: object) -> ASRSourceSnapshot:
    if type(value) is not ASRSourceSnapshot:
        raise TargetedSecondEvidenceArtifactValidationError(
            "source_snapshot has the wrong type"
        )
    try:
        validated = ASRSourceSnapshot(
            dvd_id=value.dvd_id,
            canonical_video_relative=value.canonical_video_relative,
            source_size=value.source_size,
            source_mtime_ns=value.source_mtime_ns,
        )
    except (ASRLimitError, ASRValidationError, TypeError, ValueError) as error:
        raise TargetedSecondEvidenceArtifactValidationError(
            "source_snapshot is invalid"
        ) from error
    if validated != value:
        raise TargetedSecondEvidenceArtifactValidationError(
            "source_snapshot is detached"
        )
    return validated


def _validated_runtime_identity(value: object) -> ASRRuntimeIdentity:
    if type(value) is not ASRRuntimeIdentity:
        raise TargetedSecondEvidenceArtifactValidationError(
            "runtime_identity has the wrong type"
        )
    try:
        validated = ASRRuntimeIdentity(
            engine=value.engine,
            model=value.model,
            device=value.device,
            compute_type=value.compute_type,
            cpu_threads=value.cpu_threads,
            num_workers=value.num_workers,
        )
    except (ASRLimitError, ASRValidationError, TypeError, ValueError) as error:
        raise TargetedSecondEvidenceArtifactValidationError(
            "runtime_identity is invalid"
        ) from error
    if validated != value:
        raise TargetedSecondEvidenceArtifactValidationError(
            "runtime_identity is detached"
        )
    return validated


def _validated_segment(value: object, *, field_name: str) -> ASRSegment:
    if type(value) is not ASRSegment:
        raise TargetedSecondEvidenceArtifactValidationError(
            field_name + " has the wrong type"
        )
    try:
        validated = ASRSegment(
            start_ms=value.start_ms,
            end_ms=value.end_ms,
            text=value.text,
            words=value.words,
        )
    except (ASRLimitError, ASRValidationError, TypeError, ValueError) as error:
        raise TargetedSecondEvidenceArtifactValidationError(
            field_name + " is invalid"
        ) from error
    if validated != value:
        raise TargetedSecondEvidenceArtifactValidationError(
            field_name + " is detached"
        )
    return validated


def _validated_word(value: object, *, field_name: str) -> ASRWord:
    if type(value) is not ASRWord:
        raise TargetedSecondEvidenceArtifactValidationError(
            field_name + " has the wrong type"
        )
    try:
        validated = ASRWord(
            start_ms=value.start_ms,
            end_ms=value.end_ms,
            text=value.text,
        )
    except (ASRLimitError, ASRValidationError, TypeError, ValueError) as error:
        raise TargetedSecondEvidenceArtifactValidationError(
            field_name + " is invalid"
        ) from error
    if validated != value:
        raise TargetedSecondEvidenceArtifactValidationError(
            field_name + " is detached"
        )
    return validated


def _validated_policy_version(value: object) -> str:
    value = _require_safe_string(value, field_name="policy_version")
    if value != STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1.version:
        raise TargetedSecondEvidenceArtifactValidationError(
            "unsupported targeted second-evidence policy version"
        )
    return value


def _validated_status(value: object, *, field_name: str) -> str:
    if type(value) is not str or value not in _VALID_STATUSES:
        raise TargetedSecondEvidenceArtifactValidationError(
            field_name + " is not a supported targeted status"
        )
    return value


def _validated_source(value: object) -> TargetedSecondEvidenceSource:
    if type(value) is not TargetedSecondEvidenceSource:
        raise TargetedSecondEvidenceArtifactValidationError(
            "artifact source has the wrong type"
        )
    try:
        validated = TargetedSecondEvidenceSource(
            source_index=value.source_index,
            cue_id=value.cue_id,
            start_ms=value.start_ms,
            end_ms=value.end_ms,
            source_text=value.source_text,
        )
    except (TargetedSecondEvidenceError, TypeError, ValueError) as error:
        raise TargetedSecondEvidenceArtifactValidationError(
            "artifact source is invalid"
        ) from error
    if validated != value:
        raise TargetedSecondEvidenceArtifactValidationError(
            "artifact source is detached"
        )
    return validated


def _validated_window(value: object) -> TargetedSecondEvidenceWindow:
    if type(value) is not TargetedSecondEvidenceWindow:
        raise TargetedSecondEvidenceArtifactValidationError(
            "artifact window has the wrong type"
        )
    try:
        validated = TargetedSecondEvidenceWindow(
            window_id=value.window_id,
            start_ms=value.start_ms,
            end_ms=value.end_ms,
            source_ids=value.source_ids,
            source_indices=value.source_indices,
        )
    except (TargetedSecondEvidenceError, TypeError, ValueError) as error:
        raise TargetedSecondEvidenceArtifactValidationError(
            "artifact window is invalid"
        ) from error
    if validated != value:
        raise TargetedSecondEvidenceArtifactValidationError(
            "artifact window is detached"
        )
    return validated


def _validated_result(value: object) -> TargetedSecondEvidenceWindowResult:
    if type(value) is not TargetedSecondEvidenceWindowResult:
        raise TargetedSecondEvidenceArtifactValidationError(
            "artifact result has the wrong type"
        )
    try:
        validated = TargetedSecondEvidenceWindowResult(
            source_snapshot=value.source_snapshot,
            window_id=value.window_id,
            window_start_ms=value.window_start_ms,
            window_end_ms=value.window_end_ms,
            segments=value.segments,
            plan_binding_sha256=value.plan_binding_sha256,
        )
    except (TargetedSecondEvidenceError, TypeError, ValueError) as error:
        raise TargetedSecondEvidenceArtifactValidationError(
            "artifact result is invalid"
        ) from error
    if validated != value:
        raise TargetedSecondEvidenceArtifactValidationError(
            "artifact result is detached"
        )
    return validated


def _validated_plan_and_bindings(
    *,
    source_snapshot: ASRSourceSnapshot,
    sources: tuple[TargetedSecondEvidenceSource, ...],
    windows: tuple[TargetedSecondEvidenceWindow, ...],
    results: tuple[TargetedSecondEvidenceWindowResult, ...],
    binding_sha256: str,
) -> tuple[TargetedSecondEvidencePlan, tuple[TargetedSecondEvidenceBinding, ...]]:
    try:
        plan = TargetedSecondEvidencePlan(
            source_snapshot=source_snapshot,
            sources=sources,
            windows=windows,
            binding_sha256=binding_sha256,
        )
        bindings = bind_targeted_second_evidence(plan, results)
    except (TargetedSecondEvidenceError, TypeError, ValueError) as error:
        raise TargetedSecondEvidenceArtifactValidationError(
            "artifact plan/result binding is invalid"
        ) from error
    return plan, bindings


@dataclass(frozen=True)
class TargetedSecondEvidenceArtifact:
    """Complete reusable ASR-first targeted second-evidence artifact."""

    source_snapshot: ASRSourceSnapshot
    baseline_asr_artifact_sha256: str
    runtime_identity: ASRRuntimeIdentity
    engine_version: str
    policy_version: str
    binding_sha256: str
    sources: tuple[TargetedSecondEvidenceSource, ...]
    windows: tuple[TargetedSecondEvidenceWindow, ...]
    results: tuple[TargetedSecondEvidenceWindowResult, ...]
    statuses: tuple[str, ...]

    def __post_init__(self):
        source_snapshot = _validated_snapshot(self.source_snapshot)
        baseline_sha = _require_sha256(
            self.baseline_asr_artifact_sha256,
            field_name="baseline_asr_artifact_sha256",
        )
        runtime_identity = _validated_runtime_identity(self.runtime_identity)
        engine_version = _require_safe_string(
            self.engine_version,
            field_name="engine_version",
        )
        policy_version = _validated_policy_version(self.policy_version)
        binding_sha256 = _require_sha256(
            self.binding_sha256,
            field_name="binding_sha256",
        )

        if type(self.sources) is not tuple:
            raise TargetedSecondEvidenceArtifactValidationError(
                "sources must be an immutable tuple"
            )
        if type(self.windows) is not tuple:
            raise TargetedSecondEvidenceArtifactValidationError(
                "windows must be an immutable tuple"
            )
        if type(self.results) is not tuple:
            raise TargetedSecondEvidenceArtifactValidationError(
                "results must be an immutable tuple"
            )
        if type(self.statuses) is not tuple:
            raise TargetedSecondEvidenceArtifactValidationError(
                "statuses must be an immutable tuple"
            )
        if len(self.windows) > MAX_TARGETED_SECOND_EVIDENCE_ARTIFACT_WINDOWS:
            raise TargetedSecondEvidenceArtifactLimitError(
                "artifact exceeds its window bound"
            )

        sources = tuple(_validated_source(source) for source in self.sources)
        windows = tuple(_validated_window(window) for window in self.windows)
        results = tuple(_validated_result(result) for result in self.results)
        if len(results) != len(windows):
            raise TargetedSecondEvidenceArtifactValidationError(
                "result coverage differs from window coverage"
            )
        total_segments = sum(len(result.segments) for result in results)
        if total_segments > MAX_TARGETED_SECOND_EVIDENCE_ARTIFACT_SEGMENTS:
            raise TargetedSecondEvidenceArtifactLimitError(
                "artifact exceeds its targeted segment bound"
            )
        if len(self.statuses) != len(results):
            raise TargetedSecondEvidenceArtifactValidationError(
                "status coverage differs from result coverage"
            )
        statuses = tuple(
            _validated_status(status, field_name="result status")
            for status in self.statuses
        )

        _validated_plan_and_bindings(
            source_snapshot=source_snapshot,
            sources=sources,
            windows=windows,
            results=results,
            binding_sha256=binding_sha256,
        )
        for result, status in zip(results, statuses, strict=True):
            if result.status != status:
                raise TargetedSecondEvidenceArtifactValidationError(
                    "stored status differs from deterministic result status"
                )

        object.__setattr__(self, "source_snapshot", source_snapshot)
        object.__setattr__(self, "baseline_asr_artifact_sha256", baseline_sha)
        object.__setattr__(self, "runtime_identity", runtime_identity)
        object.__setattr__(self, "engine_version", engine_version)
        object.__setattr__(self, "policy_version", policy_version)
        object.__setattr__(self, "binding_sha256", binding_sha256)
        object.__setattr__(self, "sources", sources)
        object.__setattr__(self, "windows", windows)
        object.__setattr__(self, "results", results)
        object.__setattr__(self, "statuses", statuses)

    @property
    def plan(self) -> TargetedSecondEvidencePlan:
        plan, _ = _validated_plan_and_bindings(
            source_snapshot=self.source_snapshot,
            sources=self.sources,
            windows=self.windows,
            results=self.results,
            binding_sha256=self.binding_sha256,
        )
        return plan

    @property
    def bindings(self) -> tuple[TargetedSecondEvidenceBinding, ...]:
        _, bindings = _validated_plan_and_bindings(
            source_snapshot=self.source_snapshot,
            sources=self.sources,
            windows=self.windows,
            results=self.results,
            binding_sha256=self.binding_sha256,
        )
        return bindings

    @property
    def artifact_sha256(self) -> str:
        validated = _validated_artifact(self)
        return hashlib.sha256(_canonical_payload_bytes(validated)).hexdigest()


def _validated_artifact(value: object) -> TargetedSecondEvidenceArtifact:
    if type(value) is not TargetedSecondEvidenceArtifact:
        raise TargetedSecondEvidenceArtifactValidationError(
            "artifact must be a TargetedSecondEvidenceArtifact"
        )
    try:
        validated = TargetedSecondEvidenceArtifact(
            source_snapshot=value.source_snapshot,
            baseline_asr_artifact_sha256=value.baseline_asr_artifact_sha256,
            runtime_identity=value.runtime_identity,
            engine_version=value.engine_version,
            policy_version=value.policy_version,
            binding_sha256=value.binding_sha256,
            sources=value.sources,
            windows=value.windows,
            results=value.results,
            statuses=value.statuses,
        )
    except TargetedSecondEvidenceArtifactError:
        raise
    except (TypeError, ValueError) as error:
        raise TargetedSecondEvidenceArtifactValidationError(
            "artifact is invalid or detached"
        ) from error
    if validated != value:
        raise TargetedSecondEvidenceArtifactValidationError(
            "artifact identity is detached"
        )
    return validated


def _execution_results(
    execution: TargetedSecondEvidenceExecution,
) -> tuple[TargetedSecondEvidenceWindowResult, ...]:
    if type(execution) is not TargetedSecondEvidenceExecution:
        raise TargetedSecondEvidenceArtifactValidationError(
            "execution must be a TargetedSecondEvidenceExecution"
        )
    try:
        execution.__post_init__()
    except Exception as error:
        raise TargetedSecondEvidenceArtifactValidationError(
            "execution is invalid or detached"
        ) from error
    by_window_id = {}
    for binding in execution.bindings:
        result = binding.result
        if result.window_id in by_window_id and by_window_id[result.window_id] != result:
            raise TargetedSecondEvidenceArtifactValidationError(
                "execution has conflicting results for one window"
            )
        by_window_id[result.window_id] = result
    try:
        results = tuple(by_window_id[window.window_id] for window in execution.plan.windows)
    except KeyError as error:
        raise TargetedSecondEvidenceArtifactValidationError(
            "execution is missing a planned result"
        ) from error
    return results


def targeted_second_evidence_artifact_from_execution(
    execution: TargetedSecondEvidenceExecution,
    *,
    baseline_asr_artifact_sha256: str,
    runtime_identity: ASRRuntimeIdentity,
    engine_version: str,
) -> TargetedSecondEvidenceArtifact:
    """Convert one validated in-memory execution into a durable artifact value."""

    if type(execution) is not TargetedSecondEvidenceExecution:
        raise TargetedSecondEvidenceArtifactValidationError(
            "execution must be a TargetedSecondEvidenceExecution"
        )
    results = _execution_results(execution)
    artifact = TargetedSecondEvidenceArtifact(
        source_snapshot=execution.plan.source_snapshot,
        baseline_asr_artifact_sha256=baseline_asr_artifact_sha256,
        runtime_identity=runtime_identity,
        engine_version=engine_version,
        policy_version=execution.policy_version,
        binding_sha256=execution.plan.binding_sha256,
        sources=execution.plan.sources,
        windows=execution.plan.windows,
        results=results,
        statuses=tuple(result.status for result in results),
    )
    return _validated_artifact(artifact)


def _segment_mapping(segment: ASRSegment) -> dict[str, object]:
    segment = _validated_segment(segment, field_name="targeted segment")
    return {
        "start_ms": segment.start_ms,
        "end_ms": segment.end_ms,
        "text": segment.text,
        "words": [
            {
                "start_ms": word.start_ms,
                "end_ms": word.end_ms,
                "text": word.text,
            }
            for word in (
                _validated_word(word, field_name="targeted word")
                for word in segment.words
            )
        ],
    }


def _artifact_payload_mapping(
    artifact: TargetedSecondEvidenceArtifact,
) -> dict[str, object]:
    snapshot = artifact.source_snapshot
    runtime_identity = artifact.runtime_identity
    bindings = artifact.bindings
    result_by_window_id = {
        result.window_id: result
        for result in artifact.results
    }
    return {
        "schema_version": TARGETED_SECOND_EVIDENCE_ARTIFACT_SCHEMA_VERSION,
        "source_snapshot": {
            "dvd_id": snapshot.dvd_id,
            "canonical_video_relative": snapshot.canonical_video_relative,
            "source_size": snapshot.source_size,
            "source_mtime_ns": snapshot.source_mtime_ns,
        },
        "baseline_asr_artifact_sha256": artifact.baseline_asr_artifact_sha256,
        "runtime_identity": {
            "engine": runtime_identity.engine,
            "model": runtime_identity.model,
            "device": runtime_identity.device,
            "compute_type": runtime_identity.compute_type,
            "cpu_threads": runtime_identity.cpu_threads,
            "num_workers": runtime_identity.num_workers,
        },
        "engine_version": artifact.engine_version,
        "policy_version": artifact.policy_version,
        "binding_sha256": artifact.binding_sha256,
        "sources": [
            {
                "source_index": source.source_index,
                "cue_id": source.cue_id,
                "start_ms": source.start_ms,
                "end_ms": source.end_ms,
                "source_text": source.source_text,
            }
            for source in artifact.sources
        ],
        "windows": [
            {
                "window_id": window.window_id,
                "start_ms": window.start_ms,
                "end_ms": window.end_ms,
                "source_ids": list(window.source_ids),
                "source_indices": list(window.source_indices),
            }
            for window in artifact.windows
        ],
        "results": [
            {
                "window_id": result.window_id,
                "window_start_ms": result.window_start_ms,
                "window_end_ms": result.window_end_ms,
                "plan_binding_sha256": result.plan_binding_sha256,
                "status": status,
                "segments": [_segment_mapping(segment) for segment in result.segments],
            }
            for result, status in zip(artifact.results, artifact.statuses, strict=True)
        ],
        "bindings": [
            {
                "source_id": binding.source_id,
                "window_id": binding.window.window_id,
                "status": binding.status,
                "provenance_digest": binding.result.plan_binding_sha256,
            }
            for binding in bindings
        ],
    }


def _canonical_payload_bytes(artifact: TargetedSecondEvidenceArtifact) -> bytes:
    try:
        return json.dumps(
            _artifact_payload_mapping(artifact),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (UnicodeEncodeError, TypeError, ValueError) as error:
        raise TargetedSecondEvidenceArtifactValidationError(
            "artifact cannot be encoded as deterministic JSON"
        ) from error


def _full_mapping(
    artifact: TargetedSecondEvidenceArtifact,
    payload: bytes,
) -> dict[str, object]:
    mapping = _artifact_payload_mapping(artifact)
    mapping["artifact_sha256"] = hashlib.sha256(payload).hexdigest()
    return mapping


def serialize_targeted_second_evidence_artifact(
    artifact: TargetedSecondEvidenceArtifact,
) -> bytes:
    """Serialize one complete artifact to deterministic compact UTF-8 bytes."""

    validated = _validated_artifact(artifact)
    payload = _canonical_payload_bytes(validated)
    try:
        raw = json.dumps(
            _full_mapping(validated, payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (UnicodeEncodeError, TypeError, ValueError) as error:
        raise TargetedSecondEvidenceArtifactValidationError(
            "artifact cannot be encoded as deterministic JSON"
        ) from error
    if len(raw) > MAX_TARGETED_SECOND_EVIDENCE_ARTIFACT_BYTES:
        raise TargetedSecondEvidenceArtifactLimitError(
            "serialized artifact exceeds its byte bound"
        )
    return raw


def _decode_artifact(raw: object) -> dict[str, object]:
    if type(raw) is not bytes or not raw:
        raise TargetedSecondEvidenceArtifactValidationError(
            "artifact input must be nonempty exact bytes"
        )
    if len(raw) > MAX_TARGETED_SECOND_EVIDENCE_ARTIFACT_BYTES:
        raise TargetedSecondEvidenceArtifactLimitError(
            "artifact input exceeds its byte bound"
        )
    try:
        decoded = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonstandard_number,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        _DuplicateArtifactKey,
        TypeError,
        ValueError,
    ) as error:
        raise TargetedSecondEvidenceArtifactValidationError(
            "artifact is not deterministic UTF-8 JSON"
        ) from error
    return _require_exact_object(
        decoded,
        expected_keys=_TOP_LEVEL_KEYS,
        field_name="artifact",
    )


def _parse_snapshot(value: object) -> ASRSourceSnapshot:
    mapping = _require_exact_object(
        value,
        expected_keys=_SOURCE_SNAPSHOT_KEYS,
        field_name="source_snapshot",
    )
    try:
        return ASRSourceSnapshot(**mapping)
    except (ASRLimitError, ASRValidationError, TypeError, ValueError) as error:
        raise TargetedSecondEvidenceArtifactValidationError(
            "source_snapshot violates the ASR contract"
        ) from error


def _parse_runtime_identity(value: object) -> ASRRuntimeIdentity:
    mapping = _require_exact_object(
        value,
        expected_keys=_RUNTIME_IDENTITY_KEYS,
        field_name="runtime_identity",
    )
    try:
        return ASRRuntimeIdentity(**mapping)
    except (ASRLimitError, ASRValidationError, TypeError, ValueError) as error:
        raise TargetedSecondEvidenceArtifactValidationError(
            "runtime_identity violates the ASR contract"
        ) from error


def _parse_word(value: object) -> ASRWord:
    mapping = _require_exact_object(
        value,
        expected_keys=_WORD_KEYS,
        field_name="targeted word",
    )
    try:
        word = ASRWord(**mapping)
    except (ASRLimitError, ASRValidationError, TypeError, ValueError) as error:
        raise TargetedSecondEvidenceArtifactValidationError(
            "targeted word violates the ASR contract"
        ) from error
    if (
        word.start_ms != mapping["start_ms"]
        or word.end_ms != mapping["end_ms"]
        or word.text != mapping["text"]
    ):
        raise TargetedSecondEvidenceArtifactValidationError(
            "targeted word was normalized during validation"
        )
    return word


def _parse_segment(value: object) -> ASRSegment:
    mapping = _require_exact_object(
        value,
        expected_keys=_SEGMENT_KEYS,
        field_name="targeted segment",
    )
    if type(mapping["words"]) is not list:
        raise TargetedSecondEvidenceArtifactValidationError(
            "targeted segment words must be a JSON array"
        )
    words = tuple(_parse_word(word) for word in mapping["words"])
    try:
        segment = ASRSegment(
            start_ms=mapping["start_ms"],
            end_ms=mapping["end_ms"],
            text=mapping["text"],
            words=words,
        )
    except (ASRLimitError, ASRValidationError, TypeError, ValueError) as error:
        raise TargetedSecondEvidenceArtifactValidationError(
            "targeted segment violates the ASR contract"
        ) from error
    if (
        segment.start_ms != mapping["start_ms"]
        or segment.end_ms != mapping["end_ms"]
        or segment.text != mapping["text"]
        or segment.words != words
    ):
        raise TargetedSecondEvidenceArtifactValidationError(
            "targeted segment was normalized during validation"
        )
    return segment


def _parse_sources(value: object) -> tuple[TargetedSecondEvidenceSource, ...]:
    if type(value) is not list or len(value) > MAX_ASR_SEGMENTS:
        raise TargetedSecondEvidenceArtifactValidationError(
            "sources must be a bounded JSON array"
        )
    sources = []
    for index, item in enumerate(value, start=1):
        mapping = _require_exact_object(
            item,
            expected_keys=_SOURCE_KEYS,
            field_name="source " + str(index),
        )
        try:
            sources.append(TargetedSecondEvidenceSource(**mapping))
        except (TargetedSecondEvidenceError, TypeError, ValueError) as error:
            raise TargetedSecondEvidenceArtifactValidationError(
                "source " + str(index) + " violates the binding contract"
            ) from error
    return tuple(sources)


def _parse_windows(value: object) -> tuple[TargetedSecondEvidenceWindow, ...]:
    if (
        type(value) is not list
        or len(value) > MAX_TARGETED_SECOND_EVIDENCE_ARTIFACT_WINDOWS
    ):
        raise TargetedSecondEvidenceArtifactValidationError(
            "windows must be a bounded JSON array"
        )
    windows = []
    for index, item in enumerate(value, start=1):
        mapping = _require_exact_object(
            item,
            expected_keys=_WINDOW_KEYS,
            field_name="window " + str(index),
        )
        if type(mapping["source_ids"]) is not list or type(mapping["source_indices"]) is not list:
            raise TargetedSecondEvidenceArtifactValidationError(
                "window source membership must be JSON arrays"
            )
        try:
            windows.append(
                TargetedSecondEvidenceWindow(
                    window_id=mapping["window_id"],
                    start_ms=mapping["start_ms"],
                    end_ms=mapping["end_ms"],
                    source_ids=tuple(mapping["source_ids"]),
                    source_indices=tuple(mapping["source_indices"]),
                )
            )
        except (TargetedSecondEvidenceError, TypeError, ValueError) as error:
            raise TargetedSecondEvidenceArtifactValidationError(
                "window " + str(index) + " violates the binding contract"
            ) from error
    return tuple(windows)


def _parse_results(
    value: object,
    *,
    source_snapshot: ASRSourceSnapshot,
) -> tuple[tuple[TargetedSecondEvidenceWindowResult, ...], tuple[str, ...]]:
    if (
        type(value) is not list
        or len(value) > MAX_TARGETED_SECOND_EVIDENCE_ARTIFACT_WINDOWS
    ):
        raise TargetedSecondEvidenceArtifactValidationError(
            "results must be a bounded JSON array"
        )
    results = []
    statuses = []
    total_segments = 0
    for index, item in enumerate(value, start=1):
        mapping = _require_exact_object(
            item,
            expected_keys=_RESULT_KEYS,
            field_name="result " + str(index),
        )
        if type(mapping["segments"]) is not list:
            raise TargetedSecondEvidenceArtifactValidationError(
                "result segments must be a JSON array"
            )
        segments = tuple(_parse_segment(segment) for segment in mapping["segments"])
        total_segments += len(segments)
        if total_segments > MAX_TARGETED_SECOND_EVIDENCE_ARTIFACT_SEGMENTS:
            raise TargetedSecondEvidenceArtifactLimitError(
                "artifact exceeds its targeted segment bound"
            )
        status = _validated_status(mapping["status"], field_name="result status")
        try:
            result = TargetedSecondEvidenceWindowResult(
                source_snapshot=source_snapshot,
                window_id=mapping["window_id"],
                window_start_ms=mapping["window_start_ms"],
                window_end_ms=mapping["window_end_ms"],
                segments=segments,
                plan_binding_sha256=mapping["plan_binding_sha256"],
            )
        except (TargetedSecondEvidenceError, TypeError, ValueError) as error:
            raise TargetedSecondEvidenceArtifactValidationError(
                "result " + str(index) + " violates the binding contract"
            ) from error
        if result.status != status:
            raise TargetedSecondEvidenceArtifactValidationError(
                "stored result status is detached from its segments"
            )
        results.append(result)
        statuses.append(status)
    return tuple(results), tuple(statuses)


def _expected_binding_records(
    artifact: TargetedSecondEvidenceArtifact,
) -> list[dict[str, object]]:
    return [
        {
            "source_id": binding.source_id,
            "window_id": binding.window.window_id,
            "status": binding.status,
            "provenance_digest": binding.result.plan_binding_sha256,
        }
        for binding in artifact.bindings
    ]


def _validate_binding_records(
    value: object,
    artifact: TargetedSecondEvidenceArtifact,
) -> None:
    if type(value) is not list:
        raise TargetedSecondEvidenceArtifactValidationError(
            "bindings must be a JSON array"
        )
    if len(value) != len(artifact.sources):
        raise TargetedSecondEvidenceArtifactValidationError(
            "binding coverage differs from source coverage"
        )
    records = []
    for index, item in enumerate(value, start=1):
        mapping = _require_exact_object(
            item,
            expected_keys=_BINDING_KEYS,
            field_name="binding " + str(index),
        )
        _validated_status(mapping["status"], field_name="binding status")
        _require_sha256(
            mapping["provenance_digest"],
            field_name="binding provenance_digest",
        )
        records.append(mapping)
    if records != _expected_binding_records(artifact):
        raise TargetedSecondEvidenceArtifactValidationError(
            "serialized binding records are detached"
        )


def parse_targeted_second_evidence_artifact_bytes(
    raw: bytes,
) -> TargetedSecondEvidenceArtifact:
    """Parse and fully validate one generic targeted evidence artifact."""

    decoded = _decode_artifact(raw)
    artifact_sha = _require_sha256(
        decoded["artifact_sha256"],
        field_name="artifact_sha256",
    )
    payload = {key: decoded[key] for key in _PAYLOAD_KEYS}
    try:
        payload_bytes = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (UnicodeEncodeError, TypeError, ValueError) as error:
        raise TargetedSecondEvidenceArtifactValidationError(
            "artifact payload cannot be canonicalized"
        ) from error
    if hashlib.sha256(payload_bytes).hexdigest() != artifact_sha:
        raise TargetedSecondEvidenceArtifactValidationError(
            "artifact_sha256 mismatch"
        )
    if (
        type(decoded["schema_version"]) is not int
        or decoded["schema_version"] != TARGETED_SECOND_EVIDENCE_ARTIFACT_SCHEMA_VERSION
    ):
        raise TargetedSecondEvidenceArtifactValidationError(
            "artifact schema_version is unsupported"
        )

    source_snapshot = _parse_snapshot(decoded["source_snapshot"])
    baseline_sha = _require_sha256(
        decoded["baseline_asr_artifact_sha256"],
        field_name="baseline_asr_artifact_sha256",
    )
    runtime_identity = _parse_runtime_identity(decoded["runtime_identity"])
    engine_version = _require_safe_string(
        decoded["engine_version"],
        field_name="engine_version",
    )
    policy_version = _validated_policy_version(decoded["policy_version"])
    binding_sha = _require_sha256(
        decoded["binding_sha256"],
        field_name="binding_sha256",
    )
    sources = _parse_sources(decoded["sources"])
    windows = _parse_windows(decoded["windows"])
    results, statuses = _parse_results(
        decoded["results"],
        source_snapshot=source_snapshot,
    )
    try:
        artifact = TargetedSecondEvidenceArtifact(
            source_snapshot=source_snapshot,
            baseline_asr_artifact_sha256=baseline_sha,
            runtime_identity=runtime_identity,
            engine_version=engine_version,
            policy_version=policy_version,
            binding_sha256=binding_sha,
            sources=sources,
            windows=windows,
            results=results,
            statuses=statuses,
        )
    except TargetedSecondEvidenceArtifactError:
        raise
    except (TypeError, ValueError) as error:
        raise TargetedSecondEvidenceArtifactValidationError(
            "parsed artifact violates the generic targeted evidence contract"
        ) from error
    _validate_binding_records(decoded["bindings"], artifact)
    if artifact.artifact_sha256 != artifact_sha:
        raise TargetedSecondEvidenceArtifactValidationError(
            "parsed artifact SHA differs from its canonical bytes"
        )
    return artifact


def require_matching_targeted_second_evidence_context(
    artifact: TargetedSecondEvidenceArtifact,
    *,
    source_snapshot: ASRSourceSnapshot,
    baseline_asr_artifact_sha256: str,
    policy_version: str = STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1.version,
) -> TargetedSecondEvidenceArtifact:
    """Require exact external provenance without performing any I/O."""

    validated = _validated_artifact(artifact)
    expected_snapshot = _validated_snapshot(source_snapshot)
    expected_baseline_sha = _require_sha256(
        baseline_asr_artifact_sha256,
        field_name="expected baseline_asr_artifact_sha256",
    )
    expected_policy = _validated_policy_version(policy_version)
    if validated.source_snapshot != expected_snapshot:
        raise TargetedSecondEvidenceArtifactValidationError(
            "artifact source snapshot does not match expected source"
        )
    if validated.baseline_asr_artifact_sha256 != expected_baseline_sha:
        raise TargetedSecondEvidenceArtifactValidationError(
            "artifact baseline ASR SHA does not match expected artifact"
        )
    if validated.policy_version != expected_policy:
        raise TargetedSecondEvidenceArtifactValidationError(
            "artifact policy version does not match expected policy"
        )
    return validated


def _validate_output_parent(path: Path) -> None:
    if not path.is_absolute() or path.name in {"", ".", ".."}:
        raise TargetedSecondEvidenceArtifactPersistenceError(
            "artifact output path must be an absolute file path"
        )
    current = Path(path.anchor)
    for component in path.parent.parts[1:]:
        current /= component
        try:
            info = os.lstat(current)
        except OSError as error:
            raise TargetedSecondEvidenceArtifactPersistenceError(
                "artifact output parent cannot be inspected"
            ) from error
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise TargetedSecondEvidenceArtifactPersistenceError(
                "artifact output parent contains an unsafe path component"
            )
    try:
        parent_info = os.lstat(path.parent)
    except OSError as error:
        raise TargetedSecondEvidenceArtifactPersistenceError(
            "artifact output parent cannot be inspected"
        ) from error
    if not stat.S_ISDIR(parent_info.st_mode):
        raise TargetedSecondEvidenceArtifactPersistenceError(
            "artifact output parent is not a directory"
        )
    if parent_info.st_uid != os.geteuid():
        raise TargetedSecondEvidenceArtifactPersistenceError(
            "artifact output parent is not owned by the caller"
        )
    parent_mode = stat.S_IMODE(parent_info.st_mode)
    if parent_mode & 0o022 and not (parent_mode & stat.S_ISVTX):
        raise TargetedSecondEvidenceArtifactPersistenceError(
            "artifact output parent is broadly writable without sticky protection"
        )
    try:
        existing = os.lstat(path)
    except FileNotFoundError:
        return
    except OSError as error:
        raise TargetedSecondEvidenceArtifactPersistenceError(
            "artifact output destination cannot be inspected"
        ) from error
    if existing is not None:
        raise TargetedSecondEvidenceArtifactPersistenceError(
            "artifact output destination already exists"
        )


def _fsync_directory(directory: Path) -> None:
    try:
        directory_fd = os.open(
            directory,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
    except OSError as error:
        raise TargetedSecondEvidenceArtifactPersistenceError(
            "artifact parent could not be opened for durability"
        ) from error
    try:
        os.fsync(directory_fd)
    except OSError as error:
        raise TargetedSecondEvidenceArtifactPersistenceError(
            "artifact parent could not be synchronized"
        ) from error
    finally:
        os.close(directory_fd)


def write_targeted_second_evidence_artifact(
    path: str | Path,
    artifact: TargetedSecondEvidenceArtifact,
) -> Path:
    """Install one validated artifact as a new private file without overwrite."""

    validated = _validated_artifact(artifact)
    raw = serialize_targeted_second_evidence_artifact(validated)
    output = Path(path)
    _validate_output_parent(output)

    temporary_path: str | None = None
    file_descriptor: int | None = None
    try:
        file_descriptor, temporary_path = tempfile.mkstemp(
            prefix=".stage11-targeted-second-evidence-",
            dir=str(output.parent),
        )
        os.fchmod(file_descriptor, TARGETED_SECOND_EVIDENCE_ARTIFACT_FILE_MODE)
        with os.fdopen(file_descriptor, "wb") as stream:
            file_descriptor = None
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary_path, output, follow_symlinks=False)
        except FileExistsError as error:
            raise TargetedSecondEvidenceArtifactPersistenceError(
                "artifact output destination appeared and cannot be overwritten"
            ) from error
        _fsync_directory(output.parent)
        os.unlink(temporary_path)
        temporary_path = None
        _fsync_directory(output.parent)

        final_info = os.lstat(output)
        if (
            not stat.S_ISREG(final_info.st_mode)
            or final_info.st_uid != os.geteuid()
            or stat.S_IMODE(final_info.st_mode)
            != TARGETED_SECOND_EVIDENCE_ARTIFACT_FILE_MODE
            or final_info.st_nlink != 1
        ):
            raise TargetedSecondEvidenceArtifactPersistenceError(
                "installed artifact is not a private owned regular file"
            )
        return output
    except TargetedSecondEvidenceArtifactError:
        raise
    except (OSError, TypeError, ValueError) as error:
        raise TargetedSecondEvidenceArtifactPersistenceError(
            "targeted second-evidence artifact write failed"
        ) from error
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass
            except OSError:
                pass


def persist_targeted_second_evidence(
    path: str | Path,
    execution: TargetedSecondEvidenceExecution,
    *,
    baseline_asr_artifact_sha256: str,
    runtime_identity: ASRRuntimeIdentity,
    engine_version: str,
) -> Path:
    """Explicitly convert and persist one execution; never auto-saves."""

    artifact = targeted_second_evidence_artifact_from_execution(
        execution,
        baseline_asr_artifact_sha256=baseline_asr_artifact_sha256,
        runtime_identity=runtime_identity,
        engine_version=engine_version,
    )
    return write_targeted_second_evidence_artifact(path, artifact)


__all__ = [
    "MAX_TARGETED_SECOND_EVIDENCE_ARTIFACT_BYTES",
    "MAX_TARGETED_SECOND_EVIDENCE_ARTIFACT_SEGMENTS",
    "MAX_TARGETED_SECOND_EVIDENCE_ARTIFACT_WINDOWS",
    "TARGETED_SECOND_EVIDENCE_ARTIFACT_FILE_MODE",
    "TARGETED_SECOND_EVIDENCE_ARTIFACT_SCHEMA_VERSION",
    "TargetedSecondEvidenceArtifact",
    "TargetedSecondEvidenceArtifactError",
    "TargetedSecondEvidenceArtifactLimitError",
    "TargetedSecondEvidenceArtifactPersistenceError",
    "TargetedSecondEvidenceArtifactValidationError",
    "parse_targeted_second_evidence_artifact_bytes",
    "persist_targeted_second_evidence",
    "require_matching_targeted_second_evidence_context",
    "serialize_targeted_second_evidence_artifact",
    "targeted_second_evidence_artifact_from_execution",
    "write_targeted_second_evidence_artifact",
]
