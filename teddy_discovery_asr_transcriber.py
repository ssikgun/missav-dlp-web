"""Bounded full-title Japanese ASR orchestration for Stage11.

This module owns only the in-memory wiring between one validated canonical
video source, the frozen sequential audio iterator, and one lazy
faster-whisper chunk adapter.  It returns one immutable :class:`ASRResult`;
it does not own translation, subtitle output, jobs, or media cleanup.
"""

from __future__ import annotations

from collections.abc import Callable
import math
import sys

from teddy_discovery_asr import (
    ASRError,
    ASRLimitError,
    ASRResult,
    ASRSegment,
    ASRSourceSnapshot,
    ASRValidationError,
    MAX_ASR_SEGMENTS,
    validate_canonical_video,
)
from teddy_discovery_asr_audio import (
    ASRAudioChunk,
    MAX_ASR_AUDIO_CHUNK_SECONDS,
    iter_audio_chunks,
)
from teddy_discovery_asr_source import ASRLocalMediaSource
from teddy_discovery_asr_whisper import FasterWhisperASR
from teddy_discovery_subtitle import CanonicalVideoHolding


class FullTitleASRError(ASRError):
    """Base class for full-title ASR orchestration failures."""


class FullTitleASRValidationError(FullTitleASRError):
    """Raised for invalid adapter configuration or canonical input."""


class FullTitleASRContractError(FullTitleASRError):
    """Raised when an injected full-title dependency violates its contract."""


def _require_copy_to_temp(source_provider: object) -> Callable:
    copy_to_temp = getattr(source_provider, "copy_to_temp", None)
    if not callable(copy_to_temp):
        raise FullTitleASRValidationError(
            "source_provider.copy_to_temp must be callable"
        )
    return copy_to_temp


def _require_transcribe_chunk(whisper: object) -> Callable:
    transcribe_chunk = getattr(whisper, "transcribe_chunk", None)
    if not callable(transcribe_chunk):
        raise FullTitleASRValidationError(
            "whisper.transcribe_chunk must be callable"
        )
    return transcribe_chunk


def _validate_max_media_bytes(value: object) -> int:
    if type(value) is not int or value <= 0:
        raise FullTitleASRValidationError(
            "max_media_bytes must be a positive integer"
        )
    return value


def _validate_positive_finite(
    value: object,
    *,
    field_name: str,
    maximum: float | None = None,
) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FullTitleASRValidationError(
            field_name + " must be a finite positive number"
        )

    numeric = float(value)
    if not math.isfinite(numeric) or numeric <= 0:
        raise FullTitleASRValidationError(
            field_name + " must be a finite positive number"
        )
    if maximum is not None and numeric > maximum:
        raise FullTitleASRValidationError(
            field_name + " exceeds its frozen maximum"
        )

    return value


def _validate_source_timeout(value: object) -> int | float | None:
    if value is None:
        return None
    return _validate_positive_finite(
        value,
        field_name="source_timeout",
    )


def _validate_chunk_seconds(value: object) -> int | float:
    return _validate_positive_finite(
        value,
        field_name="chunk_seconds",
        maximum=MAX_ASR_AUDIO_CHUNK_SECONDS,
    )


def _validated_canonical_video(value: object) -> CanonicalVideoHolding:
    if not isinstance(value, CanonicalVideoHolding):
        raise FullTitleASRValidationError(
            "canonical_video must be a CanonicalVideoHolding"
        )

    try:
        validated = validate_canonical_video(value)
    except (ASRError, TypeError, ValueError) as error:
        raise FullTitleASRValidationError(
            "canonical_video does not satisfy the frozen ASR contract"
        ) from error

    if validated != value:
        raise FullTitleASRValidationError(
            "canonical_video identity changed during validation"
        )

    if validated.video_format != "mp4":
        raise FullTitleASRValidationError(
            "canonical_video must identify a canonical MP4"
        )

    return validated


def _source_snapshot(local_source: ASRLocalMediaSource) -> ASRSourceSnapshot:
    try:
        snapshot = local_source.source_snapshot
    except AttributeError as error:
        raise FullTitleASRContractError(
            "local ASR source is missing source_snapshot"
        ) from error

    if not isinstance(snapshot, ASRSourceSnapshot):
        raise FullTitleASRContractError(
            "local ASR source has an invalid source_snapshot"
        )
    return snapshot


def _validate_local_source_identity(
    local_source: ASRLocalMediaSource,
    canonical_video: CanonicalVideoHolding,
) -> ASRSourceSnapshot:
    snapshot = _source_snapshot(local_source)
    if (
        snapshot.dvd_id != canonical_video.dvd_id
        or snapshot.canonical_video_relative
        != canonical_video.relative_path
    ):
        raise FullTitleASRContractError(
            "local ASR source identity does not match canonical video"
        )
    return snapshot


def _validate_chunk(
    chunk: object,
    *,
    snapshot: ASRSourceSnapshot,
    previous_end_ms: int | None,
) -> tuple[ASRAudioChunk, int]:
    if not isinstance(chunk, ASRAudioChunk):
        raise FullTitleASRContractError(
            "audio iterator yielded an invalid ASRAudioChunk"
        )

    if chunk.source_snapshot != snapshot:
        raise FullTitleASRContractError(
            "audio chunk source_snapshot does not match local source"
        )

    if type(chunk.start_ms) is not int or chunk.start_ms < 0:
        raise FullTitleASRContractError(
            "audio chunk start_ms is invalid"
        )
    if type(chunk.end_ms) is not int or chunk.end_ms <= chunk.start_ms:
        raise FullTitleASRContractError(
            "audio chunk end_ms is invalid"
        )
    if (
        chunk.end_ms - chunk.start_ms
        > MAX_ASR_AUDIO_CHUNK_SECONDS * 1_000
    ):
        raise FullTitleASRContractError(
            "audio chunk exceeds the frozen duration bound"
        )

    if previous_end_ms is not None and chunk.start_ms != previous_end_ms:
        raise FullTitleASRContractError(
            "audio chunks are not exactly contiguous"
        )

    return chunk, chunk.end_ms


def _validate_segments(
    segments: object,
    *,
    chunk: ASRAudioChunk,
    previous_segment_start_ms: int | None,
    previous_segment_end_ms: int | None,
    aggregate_count: int,
) -> tuple[tuple[ASRSegment, ...], int | None, int | None]:
    if not isinstance(segments, tuple):
        raise FullTitleASRContractError(
            "whisper.transcribe_chunk must return a tuple"
        )

    if aggregate_count + len(segments) > MAX_ASR_SEGMENTS:
        raise ASRLimitError(
            "full-title ASR result exceeds MAX_ASR_SEGMENTS"
        )

    previous_start = previous_segment_start_ms
    previous_end = previous_segment_end_ms
    for segment in segments:
        if not isinstance(segment, ASRSegment):
            raise FullTitleASRContractError(
                "whisper returned a non-ASRSegment value"
            )

        if type(segment.start_ms) is not int or segment.start_ms < 0:
            raise FullTitleASRContractError(
                "ASR segment start_ms is invalid"
            )
        if type(segment.end_ms) is not int or segment.end_ms <= segment.start_ms:
            raise FullTitleASRContractError(
                "ASR segment end_ms is invalid"
            )
        if (
            segment.start_ms < chunk.start_ms
            or segment.end_ms > chunk.end_ms
        ):
            raise FullTitleASRContractError(
                "ASR segment lies outside its audio chunk"
            )
        if previous_start is not None and segment.start_ms < previous_start:
            raise FullTitleASRContractError(
                "ASR segment starts are not nondecreasing"
            )

        previous_start = segment.start_ms
        previous_end = segment.end_ms

    return segments, previous_start, previous_end


def _cleanup_source_preserving_primary(
    local_source: ASRLocalMediaSource,
) -> None:
    """Clean the owned source without masking an active typed failure."""

    primary_active = sys.exc_info()[0] is not None
    try:
        local_source.cleanup()
    except ASRError:
        if primary_active:
            return
        raise


class FullTitleASRTranscriber:
    """Transcribe one canonical title through one bounded Whisper instance."""

    def __init__(
        self,
        *,
        source_provider: object,
        max_media_bytes: int,
        source_timeout: int | float | None = None,
        chunk_seconds: int | float = MAX_ASR_AUDIO_CHUNK_SECONDS,
        whisper: object | None = None,
        audio_chunk_iterator: Callable = iter_audio_chunks,
    ):
        self._copy_to_temp = _require_copy_to_temp(source_provider)
        self.max_media_bytes = _validate_max_media_bytes(max_media_bytes)
        self.source_timeout = _validate_source_timeout(source_timeout)
        self.chunk_seconds = _validate_chunk_seconds(chunk_seconds)

        if not callable(audio_chunk_iterator):
            raise FullTitleASRValidationError(
                "audio_chunk_iterator must be callable"
            )
        self.audio_chunk_iterator = audio_chunk_iterator

        self.whisper = whisper if whisper is not None else FasterWhisperASR()
        self._transcribe_chunk = _require_transcribe_chunk(self.whisper)

    def _transcribe_local_source(
        self,
        local_source: ASRLocalMediaSource,
        canonical_video: CanonicalVideoHolding,
    ) -> ASRResult:
        try:
            local_source.__enter__()
            snapshot = _validate_local_source_identity(
                local_source,
                canonical_video,
            )

            chunks = self.audio_chunk_iterator(
                local_source,
                chunk_seconds=self.chunk_seconds,
                start_seconds=0,
                end_seconds=None,
            )
            try:
                chunk_iterator = iter(chunks)
            except TypeError as error:
                raise FullTitleASRContractError(
                    "audio_chunk_iterator did not return an iterable"
                ) from error

            aggregated: list[ASRSegment] = []
            previous_chunk_end_ms = None
            previous_segment_start_ms = None
            previous_segment_end_ms = None

            while True:
                try:
                    raw_chunk = next(chunk_iterator)
                except StopIteration:
                    break
                except TypeError as error:
                    raise FullTitleASRContractError(
                        "audio iterator did not yield through __next__"
                    ) from error

                chunk, previous_chunk_end_ms = _validate_chunk(
                    raw_chunk,
                    snapshot=snapshot,
                    previous_end_ms=previous_chunk_end_ms,
                )
                if (
                    previous_segment_end_ms is not None
                    and previous_segment_end_ms > chunk.start_ms
                ):
                    raise FullTitleASRContractError(
                        "ASR segment extends beyond the prior audio chunk"
                    )
                raw_segments = self._transcribe_chunk(chunk)
                segments, previous_segment_start_ms, previous_segment_end_ms = (
                    _validate_segments(
                        raw_segments,
                        chunk=chunk,
                        previous_segment_start_ms=previous_segment_start_ms,
                        previous_segment_end_ms=previous_segment_end_ms,
                        aggregate_count=len(aggregated),
                    )
                )
                aggregated.extend(segments)

            if not aggregated:
                raise FullTitleASRError(
                    "full-title ASR produced no speech segments"
                )

            try:
                engine_version = self.whisper.engine_version
            except AttributeError as error:
                raise FullTitleASRContractError(
                    "whisper is missing engine_version"
                ) from error

            return ASRResult(
                source_snapshot=snapshot,
                source_language="ja",
                segments=tuple(aggregated),
                engine_version=engine_version,
            )
        finally:
            _cleanup_source_preserving_primary(local_source)

    def __call__(
        self,
        canonical_video: CanonicalVideoHolding,
    ) -> ASRResult:
        """Copy, sequentially transcribe, aggregate, and clean one title."""

        validated_video = _validated_canonical_video(canonical_video)
        local_source = self._copy_to_temp(
            validated_video,
            max_media_bytes=self.max_media_bytes,
            timeout=self.source_timeout,
        )
        if not isinstance(local_source, ASRLocalMediaSource):
            raise FullTitleASRContractError(
                "source_provider returned an invalid ASRLocalMediaSource"
            )

        return self._transcribe_local_source(
            local_source,
            validated_video,
        )


__all__ = [
    "FullTitleASRError",
    "FullTitleASRContractError",
    "FullTitleASRTranscriber",
    "FullTitleASRValidationError",
]
