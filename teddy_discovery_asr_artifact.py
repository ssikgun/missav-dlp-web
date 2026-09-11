"""Deterministic serialization and explicit persistence for Stage11 ASR results.

Serialization and parsing remain pure JSON-bytes operations.  The explicit
``persist_asr_result`` boundary owns only private, no-overwrite artifact
installation; this module performs no network, media, model, database, or
workflow I/O.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Final

from teddy_discovery_asr import (
    ASRError,
    ASRLimitError,
    ASRResult,
    ASRRuntimeIdentity,
    ASRSegment,
    ASRSourceSnapshot,
    ASRValidationError,
    ASRWord,
    MAX_ASR_SEGMENTS,
)


ASR_ARTIFACT_SCHEMA_VERSION: Final[int] = 1
MAX_ASR_ARTIFACT_BYTES: int = 64 * 1024 * 1024
ASR_ARTIFACT_FILE_MODE: Final[int] = 0o600

_TOP_LEVEL_KEYS = (
    "schema_version",
    "source_snapshot",
    "source_language",
    "engine_version",
    "runtime_identity",
    "segments",
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


class ASRArtifactError(ASRError):
    """Base class for deterministic ASR artifact failures."""


class ASRArtifactValidationError(ASRArtifactError):
    """Raised when an ASR artifact or result violates its contract."""


class ASRArtifactLimitError(ASRArtifactError, ASRLimitError):
    """Raised when an ASR artifact exceeds its fixed byte or count bound."""


class ASRArtifactPersistenceError(ASRArtifactError):
    """Raised when an ASR artifact cannot be privately installed."""


class _DuplicateArtifactKey(ValueError):
    """Internal JSON parser marker for duplicate object keys."""


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateArtifactKey("duplicate artifact object key")
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
        raise ASRArtifactValidationError(
            field_name + " has an invalid exact key set"
        )
    return value


def _wrap_asr_validation(error: Exception, *, field_name: str):
    if isinstance(error, ASRLimitError):
        raise ASRArtifactLimitError(
            field_name + " exceeds an ASR contract limit"
        ) from error
    raise ASRArtifactValidationError(
        field_name + " violates an ASR contract"
    ) from error


def _validated_result(result: object) -> ASRResult:
    if not isinstance(result, ASRResult):
        raise ASRArtifactValidationError(
            "result must be an ASRResult"
        )

    try:
        return ASRResult(
            source_snapshot=result.source_snapshot,
            source_language=result.source_language,
            segments=result.segments,
            engine_version=result.engine_version,
            engine=result.engine,
            model=result.model,
            device=result.device,
            compute_type=result.compute_type,
            cpu_threads=result.cpu_threads,
            num_workers=result.num_workers,
        )
    except (ASRLimitError, ASRValidationError, TypeError, ValueError) as error:
        _wrap_asr_validation(error, field_name="result")
    raise AssertionError("unreachable")


def _artifact_mapping(result: ASRResult) -> dict[str, object]:
    runtime_identity = result.runtime_identity
    snapshot = result.source_snapshot

    return {
        "schema_version": ASR_ARTIFACT_SCHEMA_VERSION,
        "source_snapshot": {
            "dvd_id": snapshot.dvd_id,
            "canonical_video_relative": snapshot.canonical_video_relative,
            "source_size": snapshot.source_size,
            "source_mtime_ns": snapshot.source_mtime_ns,
        },
        "source_language": result.source_language,
        "engine_version": result.engine_version,
        "runtime_identity": {
            "engine": runtime_identity.engine,
            "model": runtime_identity.model,
            "device": runtime_identity.device,
            "compute_type": runtime_identity.compute_type,
            "cpu_threads": runtime_identity.cpu_threads,
            "num_workers": runtime_identity.num_workers,
        },
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
            for segment in result.segments
        ],
    }


def serialize_asr_result(result: ASRResult) -> bytes:
    """Serialize one validated result to deterministic UTF-8 JSON bytes."""

    validated = _validated_result(result)
    mapping = _artifact_mapping(validated)
    try:
        raw = json.dumps(
            mapping,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (UnicodeEncodeError, TypeError, ValueError) as error:
        raise ASRArtifactValidationError(
            "ASR result cannot be encoded as artifact JSON"
        ) from error

    if len(raw) > MAX_ASR_ARTIFACT_BYTES:
        raise ASRArtifactLimitError(
            "serialized ASR artifact exceeds MAX_ASR_ARTIFACT_BYTES"
        )
    return raw


def _decode_artifact(raw: object) -> dict[str, object]:
    if type(raw) is not bytes:
        raise ASRArtifactValidationError(
            "artifact input must be exact bytes"
        )
    if not raw:
        raise ASRArtifactValidationError("artifact input must not be empty")
    if len(raw) > MAX_ASR_ARTIFACT_BYTES:
        raise ASRArtifactLimitError(
            "artifact exceeds MAX_ASR_ARTIFACT_BYTES"
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
        raise ASRArtifactValidationError(
            "artifact is not valid deterministic UTF-8 JSON"
        ) from error

    return _require_exact_object(
        decoded,
        expected_keys=_TOP_LEVEL_KEYS,
        field_name="artifact",
    )


def _parse_snapshot(value: object) -> ASRSourceSnapshot:
    snapshot_mapping = _require_exact_object(
        value,
        expected_keys=_SOURCE_SNAPSHOT_KEYS,
        field_name="source_snapshot",
    )
    try:
        return ASRSourceSnapshot(**snapshot_mapping)
    except (ASRLimitError, ASRValidationError, TypeError, ValueError) as error:
        _wrap_asr_validation(error, field_name="source_snapshot")
    raise AssertionError("unreachable")


def _parse_runtime_identity(value: object) -> ASRRuntimeIdentity:
    identity_mapping = _require_exact_object(
        value,
        expected_keys=_RUNTIME_IDENTITY_KEYS,
        field_name="runtime_identity",
    )
    try:
        return ASRRuntimeIdentity(**identity_mapping)
    except (ASRLimitError, ASRValidationError, TypeError, ValueError) as error:
        _wrap_asr_validation(error, field_name="runtime_identity")
    raise AssertionError("unreachable")


def _parse_segments(value: object) -> tuple[ASRSegment, ...]:
    if type(value) is not list:
        raise ASRArtifactValidationError(
            "segments must be a JSON array"
        )
    if not value:
        raise ASRArtifactValidationError(
            "artifact must contain at least one segment"
        )
    if len(value) > MAX_ASR_SEGMENTS:
        raise ASRArtifactLimitError(
            "artifact exceeds MAX_ASR_SEGMENTS"
        )

    segments = []
    for segment_index, segment_value in enumerate(value, start=1):
        segment_mapping = _require_exact_object(
            segment_value,
            expected_keys=_SEGMENT_KEYS,
            field_name="segment " + str(segment_index),
        )
        words_value = segment_mapping["words"]
        if type(words_value) is not list:
            raise ASRArtifactValidationError(
                "segment words must be a JSON array"
            )

        words = []
        for word_index, word_value in enumerate(words_value, start=1):
            word_mapping = _require_exact_object(
                word_value,
                expected_keys=_WORD_KEYS,
                field_name=(
                    "segment "
                    + str(segment_index)
                    + " word "
                    + str(word_index)
                ),
            )
            try:
                word = ASRWord(**word_mapping)
            except (
                ASRLimitError,
                ASRValidationError,
                TypeError,
                ValueError,
            ) as error:
                _wrap_asr_validation(error, field_name="ASR word")
            if (
                word.start_ms != word_mapping["start_ms"]
                or word.end_ms != word_mapping["end_ms"]
                or word.text != word_mapping["text"]
            ):
                raise ASRArtifactValidationError(
                    "ASR word payload was normalized during validation"
                )
            words.append(word)

        try:
            segment = ASRSegment(
                start_ms=segment_mapping["start_ms"],
                end_ms=segment_mapping["end_ms"],
                text=segment_mapping["text"],
                words=tuple(words),
            )
        except (
            ASRLimitError,
            ASRValidationError,
            TypeError,
            ValueError,
        ) as error:
            _wrap_asr_validation(error, field_name="ASR segment")
        if (
            segment.start_ms != segment_mapping["start_ms"]
            or segment.end_ms != segment_mapping["end_ms"]
            or segment.text != segment_mapping["text"]
            or segment.words != tuple(words)
        ):
            raise ASRArtifactValidationError(
                "ASR segment payload was normalized during validation"
            )
        segments.append(segment)

    return tuple(segments)


def parse_asr_result_bytes(raw: bytes) -> ASRResult:
    """Parse and fully validate one deterministic ASR artifact."""

    artifact = _decode_artifact(raw)
    schema_version = artifact["schema_version"]
    if (
        type(schema_version) is not int
        or schema_version != ASR_ARTIFACT_SCHEMA_VERSION
    ):
        raise ASRArtifactValidationError(
            "artifact schema_version is unsupported"
        )

    source_language = artifact["source_language"]
    if source_language != "ja":
        raise ASRArtifactValidationError(
            "artifact source_language must be exactly 'ja'"
        )

    snapshot = _parse_snapshot(artifact["source_snapshot"])
    runtime_identity = _parse_runtime_identity(artifact["runtime_identity"])
    segments = _parse_segments(artifact["segments"])

    try:
        return ASRResult(
            source_snapshot=snapshot,
            source_language=source_language,
            segments=segments,
            engine_version=artifact["engine_version"],
            engine=runtime_identity.engine,
            model=runtime_identity.model,
            device=runtime_identity.device,
            compute_type=runtime_identity.compute_type,
            cpu_threads=runtime_identity.cpu_threads,
            num_workers=runtime_identity.num_workers,
        )
    except (ASRLimitError, ASRValidationError, TypeError, ValueError) as error:
        _wrap_asr_validation(error, field_name="artifact result")
    raise AssertionError("unreachable")


def require_matching_asr_source(
    artifact_result: ASRResult,
    current_snapshot: ASRSourceSnapshot,
) -> ASRResult:
    """Require exact source provenance equality without performing I/O."""

    if not isinstance(artifact_result, ASRResult):
        raise ASRArtifactValidationError(
            "artifact_result must be an ASRResult"
        )
    if not isinstance(current_snapshot, ASRSourceSnapshot):
        raise ASRArtifactValidationError(
            "current_snapshot must be an ASRSourceSnapshot"
        )
    if artifact_result.source_snapshot != current_snapshot:
        raise ASRArtifactValidationError(
            "ASR artifact source snapshot does not match current source"
        )
    return artifact_result


def _validate_output_parent(path: Path) -> None:
    if not path.is_absolute() or path.name in {"", ".", ".."}:
        raise ASRArtifactPersistenceError(
            "ASR artifact output path must be an absolute file path"
        )

    current = Path(path.anchor)
    for component in path.parent.parts[1:]:
        if component in {"", ".", ".."}:
            raise ASRArtifactPersistenceError(
                "ASR artifact output path contains unsafe components"
            )
        current /= component
        try:
            info = os.lstat(current)
        except OSError as error:
            raise ASRArtifactPersistenceError(
                "ASR artifact output parent cannot be inspected"
            ) from error
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise ASRArtifactPersistenceError(
                "ASR artifact output parent contains an unsafe path component"
            )

    try:
        parent_info = os.lstat(path.parent)
    except OSError as error:
        raise ASRArtifactPersistenceError(
            "ASR artifact output parent cannot be inspected"
        ) from error
    if not stat.S_ISDIR(parent_info.st_mode):
        raise ASRArtifactPersistenceError(
            "ASR artifact output parent is not a directory"
        )
    if parent_info.st_uid != os.geteuid():
        raise ASRArtifactPersistenceError(
            "ASR artifact output parent is not owned by the caller"
        )
    parent_mode = stat.S_IMODE(parent_info.st_mode)
    if parent_mode & 0o022 and not (parent_mode & stat.S_ISVTX):
        raise ASRArtifactPersistenceError(
            "ASR artifact output parent is broadly writable without sticky protection"
        )

    try:
        os.lstat(path)
    except FileNotFoundError:
        return
    except OSError as error:
        raise ASRArtifactPersistenceError(
            "ASR artifact output destination cannot be inspected"
        ) from error
    raise ASRArtifactPersistenceError(
        "ASR artifact output destination already exists"
    )


def _fsync_directory(directory: Path) -> None:
    try:
        directory_fd = os.open(
            directory,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
    except OSError as error:
        raise ASRArtifactPersistenceError(
            "ASR artifact parent could not be opened for durability"
        ) from error
    try:
        os.fsync(directory_fd)
    except OSError as error:
        raise ASRArtifactPersistenceError(
            "ASR artifact parent could not be synchronized"
        ) from error
    finally:
        os.close(directory_fd)


def persist_asr_result(
    path: str | Path,
    result: ASRResult,
) -> Path:
    """Install one validated ASR result as a new private artifact.

    The destination must not exist.  A temporary private file is linked into
    place, rather than replaced, so a concurrent destination cannot be
    overwritten and no partial final artifact is exposed.
    """

    raw = serialize_asr_result(result)
    try:
        output = Path(path)
    except (TypeError, ValueError) as error:
        raise ASRArtifactPersistenceError(
            "ASR artifact output path is invalid"
        ) from error
    _validate_output_parent(output)

    temporary_path: str | None = None
    file_descriptor: int | None = None
    try:
        file_descriptor, temporary_path = tempfile.mkstemp(
            prefix=".stage11-asr-artifact-",
            dir=str(output.parent),
        )
        os.fchmod(file_descriptor, ASR_ARTIFACT_FILE_MODE)
        with os.fdopen(file_descriptor, "wb") as stream:
            file_descriptor = None
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())

        try:
            os.link(temporary_path, output, follow_symlinks=False)
        except FileExistsError as error:
            raise ASRArtifactPersistenceError(
                "ASR artifact output destination appeared and cannot be overwritten"
            ) from error
        _fsync_directory(output.parent)
        os.unlink(temporary_path)
        temporary_path = None
        _fsync_directory(output.parent)

        final_info = os.lstat(output)
        if (
            not stat.S_ISREG(final_info.st_mode)
            or final_info.st_uid != os.geteuid()
            or stat.S_IMODE(final_info.st_mode) != ASR_ARTIFACT_FILE_MODE
            or final_info.st_nlink != 1
        ):
            raise ASRArtifactPersistenceError(
                "installed ASR artifact is not a private owned regular file"
            )
        return output
    except ASRArtifactError:
        raise
    except (OSError, TypeError, ValueError) as error:
        raise ASRArtifactPersistenceError(
            "ASR artifact persistence failed"
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


__all__ = [
    "ASR_ARTIFACT_SCHEMA_VERSION",
    "ASR_ARTIFACT_FILE_MODE",
    "ASRArtifactError",
    "ASRArtifactLimitError",
    "ASRArtifactPersistenceError",
    "ASRArtifactValidationError",
    "MAX_ASR_ARTIFACT_BYTES",
    "parse_asr_result_bytes",
    "persist_asr_result",
    "require_matching_asr_source",
    "serialize_asr_result",
]
