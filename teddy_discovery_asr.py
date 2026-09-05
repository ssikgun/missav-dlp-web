"""Immutable, deterministic Japanese ASR contracts for Stage11 Slice 4A.

This module contains no filesystem, network, database, media, or model I/O.
It represents one validated source snapshot and the Japanese transcript that
will later be passed to the translation/publishing stages.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import math
import unicodedata

from teddy_discovery_subtitle import (
    CanonicalHoldingValidationError,
    CanonicalVideoHolding,
    validate_canonical_holding,
)


MAX_ASR_SEGMENTS = 50_000
MAX_ASR_SEGMENT_TEXT_CHARS = 16_384

ASR_RUNTIME_PROFILE_LOCAL_CPU_MEDIUM = "LOCAL_CPU_MEDIUM"
ASR_RUNTIME_PROFILE_REMOTE_GPU_LARGE_V3 = "REMOTE_GPU_LARGE_V3"


class ASRError(Exception):
    """Base class for deterministic Stage11 ASR failures."""


class ASRValidationError(ASRError):
    """Raised when an ASR identity, runtime, timestamp, or text is invalid."""


class ASRLimitError(ASRError):
    """Raised when a bounded ASR result exceeds a fixed resource limit."""


@dataclass(frozen=True)
class ASRRuntimeIdentity:
    """One of the explicitly approved Stage11 ASR runtime profiles."""

    engine: str
    model: str
    device: str
    compute_type: str
    cpu_threads: int | None
    num_workers: int

    def __post_init__(self):
        if any(
            type(value) is not str
            for value in (
                self.engine,
                self.model,
                self.device,
                self.compute_type,
            )
        ):
            raise ASRValidationError(
                "runtime identity string fields must be exact strings"
            )
        if self.cpu_threads is not None and type(self.cpu_threads) is not int:
            raise ASRValidationError(
                "runtime identity cpu_threads must be an integer or None"
            )
        if type(self.num_workers) is not int:
            raise ASRValidationError(
                "runtime identity num_workers must be an integer"
            )

        if self._fields() not in _APPROVED_RUNTIME_PROFILES:
            raise ASRValidationError(
                "runtime identity is not an approved Stage11 profile"
            )

    def _fields(self) -> tuple[object, ...]:
        return (
            self.engine,
            self.model,
            self.device,
            self.compute_type,
            self.cpu_threads,
            self.num_workers,
        )

    @property
    def profile(self) -> str:
        return _APPROVED_RUNTIME_PROFILES[self._fields()]


_APPROVED_RUNTIME_PROFILES = {
    (
        "faster-whisper",
        "medium",
        "cpu",
        "int8",
        8,
        1,
    ): ASR_RUNTIME_PROFILE_LOCAL_CPU_MEDIUM,
    (
        "faster-whisper",
        "large-v3",
        "cuda",
        "float16",
        None,
        1,
    ): ASR_RUNTIME_PROFILE_REMOTE_GPU_LARGE_V3,
}


LOCAL_CPU_MEDIUM_RUNTIME_IDENTITY = ASRRuntimeIdentity(
    engine="faster-whisper",
    model="medium",
    device="cpu",
    compute_type="int8",
    cpu_threads=8,
    num_workers=1,
)

REMOTE_GPU_LARGE_V3_RUNTIME_IDENTITY = ASRRuntimeIdentity(
    engine="faster-whisper",
    model="large-v3",
    device="cuda",
    compute_type="float16",
    cpu_threads=None,
    num_workers=1,
)


def _has_disallowed_control_characters(value: str) -> bool:
    return any(
        character not in {"\n", "\t"}
        and (
            ord(character) < 32
            or ord(character) == 127
            or unicodedata.category(character) == "Cc"
        )
        for character in value
    )


def _normalize_transcript_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ASRValidationError(field_name + " must be a string")

    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()

    if not normalized:
        raise ASRValidationError(field_name + " must not be empty")

    if _has_disallowed_control_characters(normalized):
        raise ASRValidationError(
            field_name + " contains a disallowed control character"
        )

    if len(normalized) > MAX_ASR_SEGMENT_TEXT_CHARS:
        raise ASRLimitError(
            field_name + " exceeds MAX_ASR_SEGMENT_TEXT_CHARS"
        )

    return normalized


def _require_nonnegative_int(value: object, *, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise ASRValidationError(
            field_name + " must be a nonnegative integer"
        )

    return value


def _require_positive_int(value: object, *, field_name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ASRValidationError(
            field_name + " must be a positive integer"
        )

    return value


def _require_canonical_video(
    canonical_video: CanonicalVideoHolding,
) -> CanonicalVideoHolding:
    """Revalidate a frozen identity without accepting or repairing a path."""

    if not isinstance(canonical_video, CanonicalVideoHolding):
        raise ASRValidationError(
            "canonical_video must be a CanonicalVideoHolding"
        )

    row = {
        "dvd_id": canonical_video.dvd_id,
        "storage_root": "jav",
        "relative_path": canonical_video.relative_path,
        "parse_status": "MATCHED",
        "present": 1,
    }

    try:
        validated = validate_canonical_holding(
            row,
            canonical_video.dvd_id,
        )
    except (CanonicalHoldingValidationError, TypeError, ValueError) as error:
        raise ASRValidationError(
            "canonical_video is not an exact canonical holding"
        ) from error

    if validated != canonical_video:
        raise ASRValidationError(
            "canonical_video identity is not exactly validated"
        )

    return validated


def validate_canonical_video(
    canonical_video: CanonicalVideoHolding,
) -> CanonicalVideoHolding:
    """Return an exact validated video identity for ASR callers."""

    return _require_canonical_video(canonical_video)


@dataclass(frozen=True)
class ASRSourceSnapshot:
    """Stable metadata for one validated canonical video source."""

    dvd_id: str
    canonical_video_relative: str
    source_size: int
    source_mtime_ns: int

    def __post_init__(self):
        if not isinstance(self.dvd_id, str) or not self.dvd_id:
            raise ASRValidationError("source snapshot dvd_id is invalid")

        if not isinstance(self.canonical_video_relative, str):
            raise ASRValidationError(
                "source snapshot canonical path must be a string"
            )

        canonical_video = CanonicalVideoHolding(
            dvd_id=self.dvd_id,
            relative_path=self.canonical_video_relative,
            video_format=self.canonical_video_relative.rsplit(".", 1)[-1]
            if "." in self.canonical_video_relative
            else "",
        )
        _require_canonical_video(canonical_video)

        _require_positive_int(
            self.source_size,
            field_name="source snapshot source_size",
        )
        _require_nonnegative_int(
            self.source_mtime_ns,
            field_name="source snapshot source_mtime_ns",
        )

    @classmethod
    def from_holding(
        cls,
        canonical_video: CanonicalVideoHolding,
        *,
        source_size: int,
        source_mtime_ns: int,
    ) -> "ASRSourceSnapshot":
        validated = _require_canonical_video(canonical_video)
        return cls(
            dvd_id=validated.dvd_id,
            canonical_video_relative=validated.relative_path,
            source_size=source_size,
            source_mtime_ns=source_mtime_ns,
        )


@dataclass(frozen=True)
class ASRWord:
    """One optional immutable word/token timing inside an ASR segment."""

    start_ms: int
    end_ms: int
    text: str

    def __post_init__(self):
        _require_nonnegative_int(self.start_ms, field_name="word start_ms")
        _require_positive_int(self.end_ms, field_name="word end_ms")
        if self.end_ms <= self.start_ms:
            raise ASRValidationError("word end_ms must be greater than start_ms")

        normalized = _normalize_transcript_text(
            self.text,
            field_name="word text",
        )
        object.__setattr__(self, "text", normalized)


@dataclass(frozen=True)
class ASRSegment:
    """One immutable timed Japanese transcript segment."""

    start_ms: int
    end_ms: int
    text: str
    words: tuple[ASRWord, ...] = ()

    def __post_init__(self):
        _require_nonnegative_int(
            self.start_ms,
            field_name="segment start_ms",
        )
        _require_positive_int(
            self.end_ms,
            field_name="segment end_ms",
        )
        if self.end_ms <= self.start_ms:
            raise ASRValidationError(
                "segment end_ms must be greater than start_ms"
            )

        normalized = _normalize_transcript_text(
            self.text,
            field_name="segment text",
        )
        object.__setattr__(self, "text", normalized)

        if not isinstance(self.words, tuple):
            raise ASRValidationError("segment words must be an immutable tuple")

        previous_word_start = None
        for word in self.words:
            if not isinstance(word, ASRWord):
                raise ASRValidationError(
                    "segment words must contain ASRWord values"
                )

            if word.start_ms < self.start_ms or word.end_ms > self.end_ms:
                raise ASRValidationError(
                    "word timestamp lies outside its segment"
                )

            if (
                previous_word_start is not None
                and word.start_ms < previous_word_start
            ):
                raise ASRValidationError(
                    "word start times must be nondecreasing"
                )

            previous_word_start = word.start_ms


@dataclass(frozen=True)
class ASRResult:
    """Immutable Japanese ASR output before translation or publication."""

    source_snapshot: ASRSourceSnapshot
    source_language: str
    segments: tuple[ASRSegment, ...]
    engine_version: str
    engine: str = "faster-whisper"
    model: str = "medium"
    device: str = "cpu"
    compute_type: str = "int8"
    cpu_threads: int | None = 8
    num_workers: int = 1

    def __post_init__(self):
        if not isinstance(self.source_snapshot, ASRSourceSnapshot):
            raise ASRValidationError(
                "source_snapshot must be an ASRSourceSnapshot"
            )

        if self.source_language != "ja":
            raise ASRValidationError(
                "source_language must be exactly 'ja'"
            )

        if not isinstance(self.segments, tuple):
            raise ASRValidationError(
                "segments must be an immutable tuple"
            )

        if not self.segments:
            raise ASRLimitError("ASR result must contain at least one segment")

        if len(self.segments) > MAX_ASR_SEGMENTS:
            raise ASRLimitError(
                "ASR result exceeds MAX_ASR_SEGMENTS"
            )

        previous_start_ms = None
        for segment in self.segments:
            if not isinstance(segment, ASRSegment):
                raise ASRValidationError(
                    "segments must contain ASRSegment values"
                )

            if (
                previous_start_ms is not None
                and segment.start_ms < previous_start_ms
            ):
                raise ASRValidationError(
                    "segment start times must be nondecreasing"
                )

            previous_start_ms = segment.start_ms

        if (
            not isinstance(self.engine_version, str)
            or not self.engine_version.strip()
            or _has_disallowed_control_characters(self.engine_version)
        ):
            raise ASRValidationError(
                "engine_version must be a nonempty safe string"
            )

        ASRRuntimeIdentity(
            engine=self.engine,
            model=self.model,
            device=self.device,
            compute_type=self.compute_type,
            cpu_threads=self.cpu_threads,
            num_workers=self.num_workers,
        )

    @property
    def runtime_identity(self) -> ASRRuntimeIdentity:
        """Return the exact approved profile represented by this result."""

        return ASRRuntimeIdentity(
            engine=self.engine,
            model=self.model,
            device=self.device,
            compute_type=self.compute_type,
            cpu_threads=self.cpu_threads,
            num_workers=self.num_workers,
        )


__all__ = [
    "ASRError",
    "ASRLimitError",
    "ASRResult",
    "ASRRuntimeIdentity",
    "ASRSegment",
    "ASRSourceSnapshot",
    "ASRValidationError",
    "ASRWord",
    "MAX_ASR_SEGMENT_TEXT_CHARS",
    "MAX_ASR_SEGMENTS",
    "ASR_RUNTIME_PROFILE_LOCAL_CPU_MEDIUM",
    "ASR_RUNTIME_PROFILE_REMOTE_GPU_LARGE_V3",
    "LOCAL_CPU_MEDIUM_RUNTIME_IDENTITY",
    "REMOTE_GPU_LARGE_V3_RUNTIME_IDENTITY",
    "validate_canonical_video",
]
