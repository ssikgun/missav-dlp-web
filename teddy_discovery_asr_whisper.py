"""Thin lazy faster-whisper adapter for bounded Stage11 audio chunks.

The adapter deliberately never gives faster-whisper a media filename.  The
caller must first decode a bounded :class:`ASRAudioChunk`; ndarray input then
uses faster-whisper's NumPy path and avoids whole-media ``decode_audio``.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import math

from teddy_discovery_asr import (
    ASRError,
    ASRLimitError,
    ASRSegment,
    ASRValidationError,
    ASRWord,
    MAX_ASR_SEGMENTS,
)
from teddy_discovery_asr_audio import ASRAudioChunk


MODEL_NAME = "medium"
DEVICE = "cpu"
COMPUTE_TYPE = "int8"
CPU_THREADS = 8
NUM_WORKERS = 1
LOCAL_FILES_ONLY = True
DEFAULT_ENGINE_VERSION = "1.2.1"


class ASRWhisperError(ASRError):
    """Raised when one bounded faster-whisper request cannot complete."""


def _default_model_factory(model_name: str, **kwargs):
    # Keep this import lazy: ordinary repository smoke tests do not require
    # the STT virtual environment or a model load.
    from faster_whisper import WhisperModel

    return WhisperModel(model_name, **kwargs)


def _require_finite_seconds(value: object, *, field_name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ASRValidationError(field_name + " must be a finite number")

    try:
        numeric = float(value)
    except (OverflowError, ValueError) as error:
        raise ASRValidationError(field_name + " is not a valid timestamp") from error

    if not math.isfinite(numeric) or numeric < 0:
        raise ASRValidationError(
            field_name + " must be a finite nonnegative number"
        )

    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ASRValidationError(field_name + " is not a valid timestamp") from error

    if not decimal_value.is_finite() or decimal_value < 0:
        raise ASRValidationError(
            field_name + " must be a finite nonnegative number"
        )

    return decimal_value


def seconds_to_milliseconds(value: object, *, field_name: str) -> int:
    """Convert decimal seconds with deterministic nonnegative half-up rounding."""

    seconds = _require_finite_seconds(value, field_name=field_name)
    try:
        milliseconds = (seconds * Decimal("1000")).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    except (InvalidOperation, ValueError, OverflowError) as error:
        raise ASRValidationError(
            field_name + " is outside the supported timestamp range"
        ) from error
    return int(milliseconds)


_MISSING = object()


def _field(value: object, name: str, default: object = _MISSING) -> object:
    if isinstance(value, Mapping):
        if name in value:
            return value[name]
    else:
        try:
            return getattr(value, name)
        except AttributeError:
            pass

    if default is not _MISSING:
        return default

    raise ASRValidationError("Whisper output is missing " + name)


def _convert_words(
    raw_words: object,
    *,
    segment_start_ms: int,
    segment_end_ms: int,
    chunk: ASRAudioChunk,
) -> tuple[ASRWord, ...]:
    if raw_words is None:
        return ()

    if isinstance(raw_words, (str, bytes, Mapping)):
        raise ASRValidationError("Whisper words must be an iterable of words")

    try:
        iterator = iter(raw_words)
    except TypeError as error:
        raise ASRValidationError("Whisper words must be iterable") from error

    words: list[ASRWord] = []
    previous_start_ms = None
    for raw_word in iterator:
        raw_start = _field(raw_word, "start")
        raw_end = _field(raw_word, "end")
        raw_start_seconds = _require_finite_seconds(
            raw_start,
            field_name="Whisper word start",
        )
        raw_end_seconds = _require_finite_seconds(
            raw_end,
            field_name="Whisper word end",
        )
        # Keep ASRWord's strict end_ms > start_ms invariant.  faster-whisper
        # can emit exact zero-duration word metadata; that metadata is
        # unusable, while the containing segment text remains authoritative.
        if raw_end_seconds < raw_start_seconds:
            raise ASRValidationError(
                "Whisper word end precedes start"
            )

        # Preserve the existing missing-field boundary even when the timing
        # metadata is omitted below.  The word text is not reconstructed or
        # edited; only its unusable zero-duration timing is discarded.
        raw_word_text = _field(raw_word, "word")
        relative_start_ms = seconds_to_milliseconds(
            raw_start,
            field_name="Whisper word start",
        )
        if raw_end_seconds == raw_start_seconds:
            if (
                relative_start_ms < segment_start_ms
                or relative_start_ms > segment_end_ms
            ):
                raise ASRValidationError(
                    "Whisper word timestamp lies outside its segment"
                )
            continue

        relative_end_ms = seconds_to_milliseconds(
            raw_end,
            field_name="Whisper word end",
        )
        if relative_end_ms <= relative_start_ms:
            raise ASRValidationError(
                "positive Whisper word duration collapsed to milliseconds"
            )

        relative_word = ASRWord(
            start_ms=relative_start_ms,
            end_ms=relative_end_ms,
            text=raw_word_text,
        )

        if (
            relative_word.start_ms < segment_start_ms
            or relative_word.end_ms > segment_end_ms
        ):
            raise ASRValidationError(
                "Whisper word timestamp lies outside its segment"
            )

        if (
            previous_start_ms is not None
            and relative_word.start_ms < previous_start_ms
        ):
            raise ASRValidationError(
                "Whisper word start times must be nondecreasing"
            )

        previous_start_ms = relative_word.start_ms
        word = ASRWord(
            start_ms=chunk.start_ms + relative_word.start_ms,
            end_ms=chunk.start_ms + relative_word.end_ms,
            text=relative_word.text,
        )
        if word.start_ms < chunk.start_ms or word.end_ms > chunk.end_ms:
            raise ASRValidationError(
                "Whisper word timestamp lies outside its audio chunk"
            )
        words.append(word)

    return tuple(words)


def _convert_segments(
    raw_segments: object,
    *,
    chunk: ASRAudioChunk,
) -> tuple[ASRSegment, ...]:
    if isinstance(raw_segments, (str, bytes, Mapping)):
        raise ASRValidationError("Whisper segments must be iterable")

    try:
        iterator = iter(raw_segments)
    except TypeError as error:
        raise ASRValidationError("Whisper segments must be iterable") from error

    converted: list[ASRSegment] = []
    previous_start_ms = None
    chunk_duration_ms = chunk.end_ms - chunk.start_ms

    for raw_segment in iterator:
        if len(converted) >= MAX_ASR_SEGMENTS:
            raise ASRLimitError("Whisper result exceeds MAX_ASR_SEGMENTS")

        relative_start_ms = seconds_to_milliseconds(
            _field(raw_segment, "start"),
            field_name="Whisper segment start",
        )
        relative_end_ms = seconds_to_milliseconds(
            _field(raw_segment, "end"),
            field_name="Whisper segment end",
        )
        if relative_end_ms > chunk_duration_ms:
            raise ASRValidationError(
                "Whisper segment lies outside its audio chunk"
            )

        if (
            previous_start_ms is not None
            and relative_start_ms < previous_start_ms
        ):
            raise ASRValidationError(
                "Whisper segment start times must be nondecreasing"
            )

        previous_start_ms = relative_start_ms
        words = _convert_words(
            _field(raw_segment, "words", ()),
            segment_start_ms=relative_start_ms,
            segment_end_ms=relative_end_ms,
            chunk=chunk,
        )
        converted.append(
            ASRSegment(
                start_ms=chunk.start_ms + relative_start_ms,
                end_ms=chunk.start_ms + relative_end_ms,
                text=_field(raw_segment, "text"),
                words=words,
            )
        )

    return tuple(converted)


class FasterWhisperASR:
    """One frozen-runtime, one-call faster-whisper chunk adapter."""

    def __init__(
        self,
        *,
        model_factory=None,
        engine_version: str = DEFAULT_ENGINE_VERSION,
    ):
        if model_factory is not None and not callable(model_factory):
            raise ASRValidationError("model_factory must be callable")

        if (
            not isinstance(engine_version, str)
            or not engine_version.strip()
            or any(ord(character) < 32 for character in engine_version)
        ):
            raise ASRValidationError(
                "engine_version must be a nonempty safe string"
            )

        self._model_factory = model_factory or _default_model_factory
        self.engine_version = engine_version
        self._model = None

    def _get_model(self):
        if self._model is None:
            try:
                self._model = self._model_factory(
                    MODEL_NAME,
                    device=DEVICE,
                    compute_type=COMPUTE_TYPE,
                    cpu_threads=CPU_THREADS,
                    num_workers=NUM_WORKERS,
                    local_files_only=LOCAL_FILES_ONLY,
                )
            except Exception as error:
                raise ASRWhisperError(
                    "faster-whisper model could not be created"
                ) from error

        return self._model

    @staticmethod
    def _validate_response(response: object) -> tuple[object, object]:
        if not isinstance(response, tuple) or len(response) != 2:
            raise ASRWhisperError(
                "faster-whisper response must be a two-item tuple"
            )
        return response[0], response[1]

    def transcribe_chunk(
        self,
        chunk: ASRAudioChunk,
    ) -> tuple[ASRSegment, ...]:
        """Transcribe one bounded audio chunk as Japanese speech."""

        if not isinstance(chunk, ASRAudioChunk):
            raise ASRValidationError(
                "chunk must be an ASRAudioChunk"
            )

        model = self._get_model()
        try:
            response = model.transcribe(
                chunk.samples,
                language="ja",
                task="transcribe",
                word_timestamps=True,
            )
        except (ASRValidationError, ASRLimitError):
            raise
        except Exception as error:
            raise ASRWhisperError(
                "faster-whisper chunk transcription failed"
            ) from error

        raw_segments, info = self._validate_response(response)
        detected_language = _field(info, "language", None)
        if detected_language is not None and detected_language != "ja":
            raise ASRValidationError(
                "faster-whisper detected a non-Japanese language"
            )

        return _convert_segments(raw_segments, chunk=chunk)


__all__ = [
    "ASRWhisperError",
    "COMPUTE_TYPE",
    "CPU_THREADS",
    "DEFAULT_ENGINE_VERSION",
    "DEVICE",
    "FasterWhisperASR",
    "LOCAL_FILES_ONLY",
    "MODEL_NAME",
    "NUM_WORKERS",
    "seconds_to_milliseconds",
]
