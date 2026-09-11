"""Deterministic JSON bytes for reusable targeted-ASR window evidence.

This module owns only an in-memory artifact boundary.  It preserves every
targeted window and every absolute ASR segment/word so a later caller can
reconstruct the original :class:`TargetedASRWindowEvidence` values without
rerunning ASR.  It performs no filesystem, network, media, model, database,
or semantic I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Final

from teddy_discovery_asr import (
    ASRLimitError,
    ASRRuntimeIdentity,
    ASRSourceSnapshot,
    ASRValidationError,
    ASRWord,
    ASRSegment,
    MAX_ASR_SEGMENTS,
)
from teddy_discovery_hybrid_evidence import HybridCueIdentity
from teddy_discovery_targeted_hybrid_evidence import (
    TargetedASRWindowEvidence,
    TargetedHybridEvidenceError,
    TargetedHybridEvidenceLimitError,
)


TARGETED_ASR_ARTIFACT_SCHEMA_VERSION: Final[int] = 1
MAX_TARGETED_ASR_ARTIFACT_BYTES: Final[int] = 64 * 1024 * 1024
MAX_TARGETED_ASR_WINDOWS: Final[int] = 512
MAX_TARGETED_ASR_TOTAL_SEGMENTS: Final[int] = 100_000

_TOP_LEVEL_KEYS = (
    "schema_version",
    "source_snapshot",
    "runtime_identity",
    "engine_version",
    "windows",
)
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
_WINDOW_KEYS = (
    "window_start_ms",
    "window_end_ms",
    "external_cue_ids",
    "segments",
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


class TargetedASRArtifactError(ValueError):
    """Base class for targeted-ASR artifact failures."""


class TargetedASRArtifactValidationError(TargetedASRArtifactError):
    """Raised when an artifact violates its exact JSON/evidence contract."""


class TargetedASRArtifactLimitError(
    TargetedASRArtifactError,
    ASRLimitError,
):
    """Raised when an artifact exceeds a fixed byte or count bound."""


class _DuplicateArtifactKey(ValueError):
    """Internal JSON parser marker for duplicate object keys."""


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateArtifactKey("duplicate targeted artifact key")
        result[key] = value
    return result


def _reject_nonstandard_number(value):
    raise ValueError("non-finite JSON number is not allowed")


def _reject_nonfinite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("non-finite JSON number is not allowed")
    return parsed


def _require_exact_object(
    value: object,
    *,
    expected_keys: tuple[str, ...],
    field_name: str,
) -> dict[str, object]:
    if type(value) is not dict or set(value) != set(expected_keys):
        raise TargetedASRArtifactValidationError(
            field_name + " has an invalid exact key set"
        )
    return value


def _validate_engine_version(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise TargetedASRArtifactValidationError(
            "engine_version must be a nonempty safe string"
        )
    return value


def _validated_snapshot(
    value: object,
    *,
    field_name: str,
) -> ASRSourceSnapshot:
    if not isinstance(value, ASRSourceSnapshot):
        raise TargetedASRArtifactValidationError(
            field_name + " must be an ASRSourceSnapshot"
        )
    try:
        validated = ASRSourceSnapshot(
            dvd_id=value.dvd_id,
            canonical_video_relative=value.canonical_video_relative,
            source_size=value.source_size,
            source_mtime_ns=value.source_mtime_ns,
        )
    except (ASRLimitError, ASRValidationError, TypeError, ValueError) as error:
        raise TargetedASRArtifactValidationError(
            field_name + " is invalid or detached"
        ) from error
    if validated != value:
        raise TargetedASRArtifactValidationError(
            field_name + " identity is detached"
        )
    return validated


def _validated_runtime_identity(
    value: object,
) -> ASRRuntimeIdentity:
    if not isinstance(value, ASRRuntimeIdentity):
        raise TargetedASRArtifactValidationError(
            "runtime_identity must be an ASRRuntimeIdentity"
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
        raise TargetedASRArtifactValidationError(
            "runtime_identity is invalid or detached"
        ) from error
    if validated != value:
        raise TargetedASRArtifactValidationError(
            "runtime_identity identity is detached"
        )
    return validated


def _wrap_targeted_evidence_error(
    error: Exception,
    *,
    field_name: str,
):
    if isinstance(error, TargetedHybridEvidenceLimitError):
        raise TargetedASRArtifactLimitError(
            field_name + " exceeds a targeted evidence limit"
        ) from error
    raise TargetedASRArtifactValidationError(
        field_name + " violates the targeted evidence contract"
    ) from error


def _validated_window(
    value: object,
    *,
    source_snapshot: ASRSourceSnapshot,
    window_index: int,
) -> TargetedASRWindowEvidence:
    if not isinstance(value, TargetedASRWindowEvidence):
        raise TargetedASRArtifactValidationError(
            "window " + str(window_index) + " is not targeted evidence"
        )
    if value.source_snapshot != source_snapshot:
        raise TargetedASRArtifactValidationError(
            "window " + str(window_index) + " source snapshot is detached"
        )
    try:
        validated = TargetedASRWindowEvidence(
            source_snapshot=value.source_snapshot,
            window_start_ms=value.window_start_ms,
            window_end_ms=value.window_end_ms,
            external_cue_ids=value.external_cue_ids,
            segments=value.segments,
        )
    except (TargetedHybridEvidenceError, TypeError, ValueError) as error:
        _wrap_targeted_evidence_error(
            error,
            field_name="window " + str(window_index),
        )
    if validated != value:
        raise TargetedASRArtifactValidationError(
            "window " + str(window_index) + " identity is detached"
        )
    return validated


def _external_cue_source_index(cue_id: object) -> int:
    if type(cue_id) is not str:
        raise TargetedASRArtifactValidationError(
            "external cue identity must be an exact string"
        )
    if (
        len(cue_id) != 9
        or cue_id[:3] != "ja-"
        or any(character < "0" or character > "9" for character in cue_id[3:])
    ):
        raise TargetedASRArtifactValidationError(
            "external cue identity is not source-stable"
        )

    source_index = int(cue_id[3:]) - 1
    try:
        identity = HybridCueIdentity.for_external_ja(source_index)
    except (TypeError, ValueError, OverflowError) as error:
        raise TargetedASRArtifactValidationError(
            "external cue identity is outside its bound"
        ) from error
    if identity.cue_id != cue_id:
        raise TargetedASRArtifactValidationError(
            "external cue identity is not source-stable"
        )
    return source_index


def _validated_windows(
    value: object,
    *,
    source_snapshot: ASRSourceSnapshot,
) -> tuple[TargetedASRWindowEvidence, ...]:
    if type(value) is not tuple or not value:
        raise TargetedASRArtifactValidationError(
            "windows must be a nonempty immutable tuple"
        )
    if len(value) > MAX_TARGETED_ASR_WINDOWS:
        raise TargetedASRArtifactLimitError(
            "artifact exceeds MAX_TARGETED_ASR_WINDOWS"
        )

    validated_windows = tuple(
        _validated_window(
            window,
            source_snapshot=source_snapshot,
            window_index=index,
        )
        for index, window in enumerate(value, start=1)
    )

    previous_window_start_ms = None
    previous_cue_source_index = None
    seen_cue_ids = set()
    total_segment_count = 0

    for window_index, window in enumerate(validated_windows, start=1):
        if (
            previous_window_start_ms is not None
            and window.window_start_ms <= previous_window_start_ms
        ):
            raise TargetedASRArtifactValidationError(
                "targeted windows must be strictly ordered"
            )
        # The planner may split overlapping padded windows when their merge
        # would exceed max_window_ms.  Only starts, not disjointness, order
        # windows; each cue ID still belongs to exactly one planned window.

        for cue_id in window.external_cue_ids:
            if cue_id in seen_cue_ids:
                raise TargetedASRArtifactValidationError(
                    "external cue identity is reused across windows"
                )
            source_index = _external_cue_source_index(cue_id)
            if (
                previous_cue_source_index is not None
                and source_index <= previous_cue_source_index
            ):
                raise TargetedASRArtifactValidationError(
                    "external cue identities must be source-ordered"
                )
            seen_cue_ids.add(cue_id)
            previous_cue_source_index = source_index

        total_segment_count += len(window.segments)
        if total_segment_count > MAX_TARGETED_ASR_TOTAL_SEGMENTS:
            raise TargetedASRArtifactLimitError(
                "artifact exceeds MAX_TARGETED_ASR_TOTAL_SEGMENTS"
            )

        previous_window_start_ms = window.window_start_ms

    return validated_windows


@dataclass(frozen=True)
class TargetedASRArtifact:
    """Complete reusable targeted-ASR evidence for one source snapshot."""

    source_snapshot: ASRSourceSnapshot
    runtime_identity: ASRRuntimeIdentity
    engine_version: str
    windows: tuple[TargetedASRWindowEvidence, ...]

    def __post_init__(self):
        source_snapshot = _validated_snapshot(
            self.source_snapshot,
            field_name="artifact source_snapshot",
        )
        runtime_identity = _validated_runtime_identity(self.runtime_identity)
        engine_version = _validate_engine_version(self.engine_version)
        windows = _validated_windows(
            self.windows,
            source_snapshot=source_snapshot,
        )
        object.__setattr__(self, "source_snapshot", source_snapshot)
        object.__setattr__(self, "runtime_identity", runtime_identity)
        object.__setattr__(self, "engine_version", engine_version)
        object.__setattr__(self, "windows", windows)


def _validated_artifact(value: object) -> TargetedASRArtifact:
    if not isinstance(value, TargetedASRArtifact):
        raise TargetedASRArtifactValidationError(
            "artifact must be a TargetedASRArtifact"
        )
    try:
        validated = TargetedASRArtifact(
            source_snapshot=value.source_snapshot,
            runtime_identity=value.runtime_identity,
            engine_version=value.engine_version,
            windows=value.windows,
        )
    except TargetedASRArtifactError:
        raise
    except (TypeError, ValueError) as error:
        raise TargetedASRArtifactValidationError(
            "artifact is invalid or detached"
        ) from error
    if validated != value:
        raise TargetedASRArtifactValidationError(
            "artifact identity is detached"
        )
    return validated


def _artifact_mapping(artifact: TargetedASRArtifact) -> dict[str, object]:
    snapshot = artifact.source_snapshot
    runtime_identity = artifact.runtime_identity
    return {
        "schema_version": TARGETED_ASR_ARTIFACT_SCHEMA_VERSION,
        "source_snapshot": {
            "dvd_id": snapshot.dvd_id,
            "canonical_video_relative": snapshot.canonical_video_relative,
            "source_size": snapshot.source_size,
            "source_mtime_ns": snapshot.source_mtime_ns,
        },
        "runtime_identity": {
            "engine": runtime_identity.engine,
            "model": runtime_identity.model,
            "device": runtime_identity.device,
            "compute_type": runtime_identity.compute_type,
            "cpu_threads": runtime_identity.cpu_threads,
            "num_workers": runtime_identity.num_workers,
        },
        "engine_version": artifact.engine_version,
        "windows": [
            {
                "window_start_ms": window.window_start_ms,
                "window_end_ms": window.window_end_ms,
                "external_cue_ids": list(window.external_cue_ids),
                "segments": [
                    {
                        "start_ms": segment.start_ms,
                        "end_ms": segment.end_ms,
                        "text": segment.text,
                        "words": [
                            {
                                "start_ms": word.start_ms,
                                "end_ms": word.end_ms,
                                "text": word.text,
                            }
                            for word in segment.words
                        ],
                    }
                    for segment in window.segments
                ],
            }
            for window in artifact.windows
        ],
    }


def serialize_targeted_asr_artifact(
    artifact: TargetedASRArtifact,
) -> bytes:
    """Serialize complete targeted evidence to compact deterministic UTF-8."""

    validated = _validated_artifact(artifact)
    try:
        raw = json.dumps(
            _artifact_mapping(validated),
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (UnicodeEncodeError, TypeError, ValueError) as error:
        raise TargetedASRArtifactValidationError(
            "targeted artifact cannot be encoded as JSON"
        ) from error

    if len(raw) > MAX_TARGETED_ASR_ARTIFACT_BYTES:
        raise TargetedASRArtifactLimitError(
            "serialized artifact exceeds MAX_TARGETED_ASR_ARTIFACT_BYTES"
        )
    return raw


def _decode_artifact(raw: object) -> dict[str, object]:
    if type(raw) is not bytes:
        raise TargetedASRArtifactValidationError(
            "artifact input must be exact bytes"
        )
    if not raw:
        raise TargetedASRArtifactValidationError(
            "artifact input must not be empty"
        )
    if len(raw) > MAX_TARGETED_ASR_ARTIFACT_BYTES:
        raise TargetedASRArtifactLimitError(
            "artifact exceeds MAX_TARGETED_ASR_ARTIFACT_BYTES"
        )
    try:
        decoded = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonstandard_number,
            parse_float=_reject_nonfinite_float,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        _DuplicateArtifactKey,
        TypeError,
        ValueError,
    ) as error:
        raise TargetedASRArtifactValidationError(
            "artifact is not valid deterministic UTF-8 JSON"
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
        raise TargetedASRArtifactValidationError(
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
        raise TargetedASRArtifactValidationError(
            "runtime_identity violates the ASR contract"
        ) from error


def _parse_word(value: object) -> ASRWord:
    mapping = _require_exact_object(
        value,
        expected_keys=_WORD_KEYS,
        field_name="ASR word",
    )
    try:
        word = ASRWord(**mapping)
    except (ASRLimitError, ASRValidationError, TypeError, ValueError) as error:
        if isinstance(error, ASRLimitError):
            raise TargetedASRArtifactLimitError(
                "ASR word exceeds an ASR contract limit"
            ) from error
        raise TargetedASRArtifactValidationError(
            "ASR word violates the ASR contract"
        ) from error
    if (
        word.start_ms != mapping["start_ms"]
        or word.end_ms != mapping["end_ms"]
        or word.text != mapping["text"]
    ):
        raise TargetedASRArtifactValidationError(
            "ASR word payload was normalized during validation"
        )
    return word


def _parse_segment(value: object) -> ASRSegment:
    mapping = _require_exact_object(
        value,
        expected_keys=_SEGMENT_KEYS,
        field_name="ASR segment",
    )
    words_value = mapping["words"]
    if type(words_value) is not list:
        raise TargetedASRArtifactValidationError(
            "ASR segment words must be a JSON array"
        )
    words = tuple(_parse_word(word) for word in words_value)
    try:
        segment = ASRSegment(
            start_ms=mapping["start_ms"],
            end_ms=mapping["end_ms"],
            text=mapping["text"],
            words=words,
        )
    except (ASRLimitError, ASRValidationError, TypeError, ValueError) as error:
        if isinstance(error, ASRLimitError):
            raise TargetedASRArtifactLimitError(
                "ASR segment exceeds an ASR contract limit"
            ) from error
        raise TargetedASRArtifactValidationError(
            "ASR segment violates the ASR contract"
        ) from error
    if (
        segment.start_ms != mapping["start_ms"]
        or segment.end_ms != mapping["end_ms"]
        or segment.text != mapping["text"]
        or segment.words != words
    ):
        raise TargetedASRArtifactValidationError(
            "ASR segment payload was normalized during validation"
        )
    return segment


def _parse_windows(
    value: object,
    *,
    source_snapshot: ASRSourceSnapshot,
) -> tuple[TargetedASRWindowEvidence, ...]:
    if type(value) is not list:
        raise TargetedASRArtifactValidationError(
            "windows must be a JSON array"
        )
    if not value:
        raise TargetedASRArtifactValidationError(
            "artifact must contain at least one window"
        )
    if len(value) > MAX_TARGETED_ASR_WINDOWS:
        raise TargetedASRArtifactLimitError(
            "artifact exceeds MAX_TARGETED_ASR_WINDOWS"
        )

    windows = []
    total_segment_count = 0
    for window_index, window_value in enumerate(value, start=1):
        mapping = _require_exact_object(
            window_value,
            expected_keys=_WINDOW_KEYS,
            field_name="window " + str(window_index),
        )
        cue_ids_value = mapping["external_cue_ids"]
        if type(cue_ids_value) is not list:
            raise TargetedASRArtifactValidationError(
                "window external_cue_ids must be a JSON array"
            )
        if not cue_ids_value:
            raise TargetedASRArtifactValidationError(
                "window external_cue_ids must not be empty"
            )
        if any(type(cue_id) is not str for cue_id in cue_ids_value):
            raise TargetedASRArtifactValidationError(
                "window external_cue_ids must contain strings"
            )

        segments_value = mapping["segments"]
        if type(segments_value) is not list:
            raise TargetedASRArtifactValidationError(
                "window segments must be a JSON array"
            )
        if len(segments_value) > MAX_ASR_SEGMENTS:
            raise TargetedASRArtifactLimitError(
                "window exceeds MAX_ASR_SEGMENTS"
            )

        segments = tuple(_parse_segment(segment) for segment in segments_value)
        total_segment_count += len(segments)
        if total_segment_count > MAX_TARGETED_ASR_TOTAL_SEGMENTS:
            raise TargetedASRArtifactLimitError(
                "artifact exceeds MAX_TARGETED_ASR_TOTAL_SEGMENTS"
            )
        try:
            windows.append(
                TargetedASRWindowEvidence(
                    source_snapshot=source_snapshot,
                    window_start_ms=mapping["window_start_ms"],
                    window_end_ms=mapping["window_end_ms"],
                    external_cue_ids=tuple(cue_ids_value),
                    segments=segments,
                )
            )
        except (TargetedHybridEvidenceError, TypeError, ValueError) as error:
            _wrap_targeted_evidence_error(
                error,
                field_name="window " + str(window_index),
            )

    return tuple(windows)


def parse_targeted_asr_artifact_bytes(raw: bytes) -> TargetedASRArtifact:
    """Parse and fully validate one reusable targeted-ASR artifact."""

    artifact = _decode_artifact(raw)
    schema_version = artifact["schema_version"]
    if (
        type(schema_version) is not int
        or schema_version != TARGETED_ASR_ARTIFACT_SCHEMA_VERSION
    ):
        raise TargetedASRArtifactValidationError(
            "artifact schema_version is unsupported"
        )

    source_snapshot = _parse_snapshot(artifact["source_snapshot"])
    runtime_identity = _parse_runtime_identity(artifact["runtime_identity"])
    engine_version = _validate_engine_version(artifact["engine_version"])
    windows = _parse_windows(
        artifact["windows"],
        source_snapshot=source_snapshot,
    )
    try:
        return TargetedASRArtifact(
            source_snapshot=source_snapshot,
            runtime_identity=runtime_identity,
            engine_version=engine_version,
            windows=windows,
        )
    except TargetedASRArtifactError:
        raise
    except (TypeError, ValueError) as error:
        raise TargetedASRArtifactValidationError(
            "parsed targeted artifact is invalid"
        ) from error


def require_matching_targeted_asr_source(
    artifact: TargetedASRArtifact,
    current_snapshot: ASRSourceSnapshot,
) -> TargetedASRArtifact:
    """Require exact source provenance equality without performing I/O."""

    validated_artifact = _validated_artifact(artifact)
    validated_snapshot = _validated_snapshot(
        current_snapshot,
        field_name="current source_snapshot",
    )
    if validated_artifact.source_snapshot != validated_snapshot:
        raise TargetedASRArtifactValidationError(
            "targeted artifact source snapshot does not match current source"
        )
    return validated_artifact


__all__ = [
    "MAX_TARGETED_ASR_ARTIFACT_BYTES",
    "MAX_TARGETED_ASR_TOTAL_SEGMENTS",
    "MAX_TARGETED_ASR_WINDOWS",
    "TARGETED_ASR_ARTIFACT_SCHEMA_VERSION",
    "TargetedASRArtifact",
    "TargetedASRArtifactError",
    "TargetedASRArtifactLimitError",
    "TargetedASRArtifactValidationError",
    "parse_targeted_asr_artifact_bytes",
    "require_matching_targeted_asr_source",
    "serialize_targeted_asr_artifact",
]
