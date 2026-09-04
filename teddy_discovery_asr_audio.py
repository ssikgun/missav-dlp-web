"""Bounded sequential audio decoding for Stage11 Slice 4B.

The module deliberately imports neither PyAV nor NumPy at module import time.
It opens one validated local media source, decodes one selected audio stream
sequentially, and retains only the current bounded 16 kHz mono chunk.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from fractions import Fraction
import math
import os
import stat

from teddy_discovery_asr import (
    ASRError,
    ASRSourceSnapshot,
    ASRValidationError,
)
from teddy_discovery_asr_source import ASRLocalMediaSource


ASR_AUDIO_SAMPLE_RATE = 16_000
MAX_ASR_AUDIO_CHUNK_SECONDS = 600
MAX_ASR_AUDIO_SAMPLES = (
    ASR_AUDIO_SAMPLE_RATE * MAX_ASR_AUDIO_CHUNK_SECONDS
)
_ONE_OUTPUT_SAMPLE_SECONDS = Fraction(1, ASR_AUDIO_SAMPLE_RATE)
_MAX_TIMESTAMP_ROUNDING_TOLERANCE = Fraction(1, 1_000)


class ASRAudioError(ASRError):
    """Base class for bounded audio contract and decode failures."""


class ASRAudioValidationError(ASRAudioError):
    """Raised when a source, range, frame, or chunk is malformed."""


class ASRAudioLimitError(ASRAudioError):
    """Raised when a bounded audio request or chunk is too large."""


def _load_numpy(numpy_module):
    if numpy_module is not None:
        return numpy_module

    try:
        import numpy
    except ImportError as error:
        raise ASRAudioError("NumPy is required for Stage11 audio") from error

    return numpy


def _load_av(av_module):
    if av_module is not None:
        return av_module

    try:
        import av
    except ImportError as error:
        raise ASRAudioError("PyAV is required for Stage11 audio") from error

    return av


def _validate_sample_count(value: object) -> int:
    if type(value) is not int or value <= 0:
        raise ASRAudioValidationError(
            "audio sample count must be a positive integer"
        )
    if value > MAX_ASR_AUDIO_SAMPLES:
        raise ASRAudioLimitError(
            "audio sample count exceeds MAX_ASR_AUDIO_SAMPLES"
        )
    return value


def _seconds_to_samples(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ASRAudioValidationError(
            field_name + " must be a finite nonnegative number"
        )

    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        raise ASRAudioValidationError(
            field_name + " must be a finite nonnegative number"
        )

    try:
        decimal_value = Decimal(str(value))
        samples = (decimal_value * ASR_AUDIO_SAMPLE_RATE).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    except (InvalidOperation, ValueError) as error:
        raise ASRAudioValidationError(
            field_name + " is not a valid time"
        ) from error

    sample_index = int(samples)
    if sample_index < 0:
        raise ASRAudioValidationError(
            field_name + " must not be negative"
        )
    return sample_index


def _validate_request_range(
    *,
    chunk_seconds: object,
    start_seconds: object,
    end_seconds: object | None,
) -> tuple[int, int, int | None]:
    chunk_decimal = _validate_seconds_value(
        chunk_seconds,
        field_name="chunk_seconds",
        require_positive=True,
    )
    if chunk_decimal > Decimal(str(MAX_ASR_AUDIO_CHUNK_SECONDS)):
        raise ASRAudioLimitError(
            "chunk_seconds exceeds MAX_ASR_AUDIO_CHUNK_SECONDS"
        )

    chunk_samples = _seconds_to_samples(
        chunk_seconds,
        field_name="chunk_seconds",
    )
    _validate_sample_count(chunk_samples)

    start_decimal = _validate_seconds_value(
        start_seconds,
        field_name="start_seconds",
        require_positive=False,
    )
    start_sample = _seconds_to_samples(
        start_seconds,
        field_name="start_seconds",
    )

    end_sample = None
    if end_seconds is not None:
        end_decimal = _validate_seconds_value(
            end_seconds,
            field_name="end_seconds",
            require_positive=False,
        )
        if end_decimal <= start_decimal:
            raise ASRAudioValidationError(
                "end_seconds must be greater than start_seconds"
            )
        end_sample = _seconds_to_samples(
            end_seconds,
            field_name="end_seconds",
        )
        if end_sample <= start_sample:
            raise ASRAudioValidationError(
                "requested range must contain at least one sample"
            )
        if end_sample - start_sample > MAX_ASR_AUDIO_SAMPLES:
            raise ASRAudioLimitError(
                "requested range exceeds the 600 second audio bound"
            )

    return chunk_samples, start_sample, end_sample


def _validate_seconds_value(
    value: object,
    *,
    field_name: str,
    require_positive: bool,
) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ASRAudioValidationError(
            field_name + " must be a finite number"
        )

    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        raise ASRAudioValidationError(
            field_name + " must be a finite nonnegative number"
        )
    if require_positive and numeric <= 0:
        raise ASRAudioValidationError(
            field_name + " must be greater than zero"
        )

    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ASRAudioValidationError(
            field_name + " is not a valid time"
        ) from error

    if not decimal_value.is_finite() or decimal_value < 0:
        raise ASRAudioValidationError(
            field_name + " must be finite and nonnegative"
        )
    if require_positive and decimal_value <= 0:
        raise ASRAudioValidationError(
            field_name + " must be greater than zero"
        )

    return decimal_value


def _sample_index_to_ms(sample_index: int) -> int:
    # At 16 kHz there are exactly 16 samples per millisecond.  Half-up
    # rounding is performed with integer arithmetic, avoiding float drift.
    milliseconds, remainder = divmod(sample_index, 16)
    if remainder >= 8:
        milliseconds += 1
    return milliseconds


def _fraction_from_value(value: object, *, field_name: str) -> Fraction:
    if isinstance(value, bool):
        raise ASRAudioValidationError(field_name + " is invalid")

    try:
        if isinstance(value, Fraction):
            result = value
        elif isinstance(value, int):
            result = Fraction(value, 1)
        elif isinstance(value, Decimal):
            if not value.is_finite():
                raise ValueError
            result = Fraction(value)
        elif isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError
            result = Fraction(str(value))
        else:
            raise TypeError
    except (TypeError, ValueError, ZeroDivisionError) as error:
        raise ASRAudioValidationError(field_name + " is invalid") from error

    if result.denominator <= 0:
        raise ASRAudioValidationError(field_name + " is invalid")
    return result


def _frame_timing(frame: object) -> tuple[Fraction, Fraction, Fraction]:
    pts = _fraction_from_value(
        getattr(frame, "pts", None),
        field_name="audio frame pts",
    )
    time_base = _fraction_from_value(
        getattr(frame, "time_base", None),
        field_name="audio frame time_base",
    )
    if pts < 0 or time_base <= 0:
        raise ASRAudioValidationError(
            "audio frame pts/time_base must be nonnegative and positive"
        )

    sample_count = getattr(frame, "samples", None)
    sample_rate = getattr(frame, "sample_rate", None)
    if type(sample_count) is not int or sample_count <= 0:
        raise ASRAudioValidationError(
            "audio frame sample count is invalid"
        )
    if type(sample_rate) is not int or sample_rate <= 0:
        raise ASRAudioValidationError(
            "audio frame sample rate is invalid"
        )

    return pts * time_base, time_base, Fraction(sample_count, sample_rate)


def _round_fraction(value: Fraction) -> int:
    if value < 0:
        raise ASRAudioValidationError("audio timeline value is negative")
    quotient, remainder = divmod(value.numerator, value.denominator)
    if remainder * 2 >= value.denominator:
        quotient += 1
    return quotient


def _timestamp_to_sample_index(timestamp: Fraction) -> int:
    return _round_fraction(timestamp * ASR_AUDIO_SAMPLE_RATE)


def _timestamp_tolerance(
    previous_time_base: Fraction,
    current_time_base: Fraction,
) -> Fraction:
    # PTS values are quantized to their time bases.  Permit half a tick from
    # each adjacent frame plus one output sample, capped at one millisecond;
    # any larger uncertainty is not safe for this sequential extractor.
    quantization = (
        previous_time_base + current_time_base
    ) / 2
    return min(
        _MAX_TIMESTAMP_ROUNDING_TOLERANCE,
        max(_ONE_OUTPUT_SAMPLE_SECONDS, quantization),
    )


def _validate_frame_timeline(
    *,
    timestamp: Fraction,
    time_base: Fraction,
    duration: Fraction,
    previous_timestamp: Fraction | None,
    previous_time_base: Fraction | None,
    expected_timestamp: Fraction | None,
) -> Fraction:
    if previous_timestamp is not None:
        if timestamp < previous_timestamp:
            raise ASRAudioValidationError(
                "audio frame timestamps moved backwards"
            )

        if expected_timestamp is None or previous_time_base is None:
            raise ASRAudioValidationError(
                "audio frame timeline state is incomplete"
            )

        tolerance = _timestamp_tolerance(
            previous_time_base,
            time_base,
        )
        deviation = timestamp - expected_timestamp
        if deviation < -tolerance:
            raise ASRAudioValidationError(
                "audio frame timestamp has an unsafe discontinuity"
            )

    return timestamp + duration


def _iter_decoded_frames(decoded_frames: object):
    """Convert lazy PyAV demux/decode failures to the audio error boundary."""

    try:
        iterator = iter(decoded_frames)
    except Exception as error:
        raise ASRAudioError(
            "PyAV audio decode iteration could not start"
        ) from error

    while True:
        try:
            frame = next(iterator)
        except StopIteration:
            return
        except (ASRAudioValidationError, ASRAudioLimitError):
            raise
        except ASRAudioError:
            raise
        except Exception as error:
            raise ASRAudioError(
                "PyAV audio decode iteration failed"
            ) from error

        yield frame


@dataclass(frozen=True)
class ASRAudioChunk:
    """One bounded immutable-ish 16 kHz mono float32 audio chunk."""

    source_snapshot: ASRSourceSnapshot
    start_ms: int
    end_ms: int
    sample_rate: int
    samples: object

    def __post_init__(self):
        if not isinstance(self.source_snapshot, ASRSourceSnapshot):
            raise ASRAudioValidationError(
                "audio chunk source_snapshot is invalid"
            )
        if type(self.start_ms) is not int or self.start_ms < 0:
            raise ASRAudioValidationError(
                "audio chunk start_ms must be a nonnegative integer"
            )
        if type(self.end_ms) is not int or self.end_ms <= self.start_ms:
            raise ASRAudioValidationError(
                "audio chunk end_ms must be greater than start_ms"
            )
        if self.end_ms - self.start_ms > MAX_ASR_AUDIO_CHUNK_SECONDS * 1_000:
            raise ASRAudioLimitError(
                "audio chunk duration exceeds MAX_ASR_AUDIO_CHUNK_SECONDS"
            )
        if type(self.sample_rate) is not int or self.sample_rate != ASR_AUDIO_SAMPLE_RATE:
            raise ASRAudioValidationError(
                "audio chunk sample_rate must be exactly 16000"
            )

        numpy = _load_numpy(None)
        if not isinstance(self.samples, numpy.ndarray):
            raise ASRAudioValidationError(
                "audio chunk samples must be a NumPy ndarray"
            )
        if self.samples.ndim != 1:
            raise ASRAudioValidationError(
                "audio chunk samples must be one-dimensional"
            )
        if self.samples.dtype != numpy.dtype("float32"):
            raise ASRAudioValidationError(
                "audio chunk samples must have float32 dtype"
            )
        _validate_sample_count(int(self.samples.size))
        if not bool(numpy.isfinite(self.samples).all()):
            raise ASRAudioValidationError(
                "audio chunk samples must be finite"
            )
        if bool(numpy.any(self.samples < -1.0)) or bool(
            numpy.any(self.samples > 1.0)
        ):
            raise ASRAudioValidationError(
                "audio chunk samples must be normalized to [-1, 1]"
            )

        owned_samples = numpy.array(self.samples, copy=True)
        owned_samples.setflags(write=False)
        object.__setattr__(self, "samples", owned_samples)


def _require_local_source(local_source: object) -> ASRLocalMediaSource:
    if not isinstance(local_source, ASRLocalMediaSource):
        raise ASRAudioValidationError(
            "local_source must be an ASRLocalMediaSource"
        )
    local_source.require_active()

    path = local_source.local_path
    if not isinstance(path, str) or not path:
        raise ASRAudioValidationError("local_source local_path is invalid")

    try:
        value = os.lstat(path)
    except OSError as error:
        raise ASRAudioValidationError(
            "local ASR media source does not exist"
        ) from error

    if stat.S_ISLNK(value.st_mode) or not stat.S_ISREG(value.st_mode):
        raise ASRAudioValidationError(
            "local ASR media source must be a regular file"
        )

    return local_source


def _resampled_frames(resampler: object, frame: object):
    try:
        output = resampler.resample(frame)
    except Exception as error:
        raise ASRAudioError("PyAV audio resampling failed") from error

    if output is None:
        return ()
    if isinstance(output, (list, tuple)):
        return output
    return (output,)


def _frame_to_samples(frame: object, numpy):
    format_object = getattr(frame, "format", None)
    if getattr(format_object, "name", None) != "s16":
        raise ASRAudioValidationError(
            "resampler must produce signed 16-bit PCM"
        )

    layout_object = getattr(frame, "layout", None)
    if getattr(layout_object, "name", None) != "mono":
        raise ASRAudioValidationError(
            "resampler must produce mono audio"
        )

    try:
        array = numpy.asarray(frame.to_ndarray())
    except Exception as error:
        raise ASRAudioError("PyAV audio frame conversion failed") from error

    if array.ndim == 2 and array.shape[0] == 1:
        array = array[0]
    elif array.ndim != 1:
        raise ASRAudioValidationError(
            "resampled audio frame must be mono and one-dimensional"
        )

    if array.dtype != numpy.dtype("int16"):
        raise ASRAudioValidationError(
            "resampler must produce int16 samples"
        )

    # Match faster-whisper's native decode boundary exactly: signed 16-bit
    # PCM is converted to float32 and divided by the fixed full-scale value.
    # The operation is deliberately not clipped or peak-normalized.
    array = array.astype(numpy.dtype("float32"), copy=True)
    array /= 32768.0
    if array.size == 0:
        return array
    if not bool(numpy.isfinite(array).all()):
        raise ASRAudioValidationError(
            "resampled audio contains non-finite samples"
        )
    if bool(numpy.any(array < -1.0)) or bool(
        numpy.any(array > 32767 / 32768)
    ):
        raise ASRAudioValidationError(
            "resampled audio is outside normalized Whisper range"
        )
    return array


def _new_resampler(av_module):
    try:
        return av_module.audio.resampler.AudioResampler(
            format="s16",
            layout="mono",
            rate=ASR_AUDIO_SAMPLE_RATE,
        )
    except Exception as error:
        raise ASRAudioError(
            "PyAV audio resampler could not be created"
        ) from error


@dataclass
class _EmissionCursor:
    """Mutable absolute 16 kHz cursor for one sequential extraction."""

    value: int


def _route_resampler_output(
    resampler: object,
    frame: object,
    *,
    cursor: _EmissionCursor,
    accumulator: "_ChunkAccumulator",
    start_sample: int,
    end_sample: int | None,
    numpy,
):
    """Route real resampler output while advancing only actual emissions."""

    for resampled_frame in _resampled_frames(resampler, frame):
        samples = _frame_to_samples(resampled_frame, numpy)
        frame_start = cursor.value
        cursor.value += int(samples.size)
        frame_end = cursor.value

        if not samples.size or frame_end <= start_sample:
            continue

        left = max(0, start_sample - frame_start)
        right = samples.size
        if end_sample is not None:
            right = min(right, end_sample - frame_start)
        if right <= left:
            continue

        for chunk in accumulator.add(samples[left:right]):
            yield chunk


class _ChunkAccumulator:
    def __init__(self, *, numpy, source_snapshot, start_sample, chunk_samples):
        self.numpy = numpy
        self.source_snapshot = source_snapshot
        self.chunk_start_sample = start_sample
        self.chunk_samples = chunk_samples
        self.buffer = numpy.empty(chunk_samples, dtype=numpy.dtype("float32"))
        self.filled = 0

    def _ensure_buffer(self):
        if self.buffer is None:
            self.buffer = self.numpy.empty(
                self.chunk_samples,
                dtype=self.numpy.dtype("float32"),
            )

    def add(self, samples):
        offset = 0
        while offset < samples.size:
            self._ensure_buffer()
            take = min(self.chunk_samples - self.filled, samples.size - offset)
            self.buffer[self.filled : self.filled + take] = samples[
                offset : offset + take
            ]
            self.filled += take
            offset += take

            if self.filled != self.chunk_samples:
                continue

            finished = self._finish_chunk(self.filled)
            self.chunk_start_sample += self.filled
            self.filled = 0
            # Do not retain the just-emitted accumulation while the caller
            # owns the returned chunk.  Allocate the next bounded buffer only
            # when iteration resumes.
            self.buffer = None
            yield finished

    def add_silence(self, sample_count: int):
        """Fill bounded output buffers with exact normalized digital silence."""

        if type(sample_count) is not int or sample_count < 0:
            raise ASRAudioValidationError(
                "silence sample count must be a nonnegative integer"
            )

        remaining = sample_count
        while remaining:
            self._ensure_buffer()
            take = min(self.chunk_samples - self.filled, remaining)
            self.buffer[self.filled : self.filled + take].fill(0.0)
            self.filled += take
            remaining -= take

            if self.filled != self.chunk_samples:
                continue

            finished = self._finish_chunk(self.filled)
            self.chunk_start_sample += self.filled
            self.filled = 0
            self.buffer = None
            yield finished

    def finish(self):
        if self.filled:
            finished = self._finish_chunk(self.filled)
            self.chunk_start_sample += self.filled
            self.filled = 0
            self.buffer = None
            yield finished

    def _finish_chunk(self, sample_count):
        start_sample = self.chunk_start_sample
        end_sample = start_sample + sample_count
        start_ms = _sample_index_to_ms(start_sample)
        end_ms = _sample_index_to_ms(end_sample)
        if end_ms <= start_ms:
            end_ms = start_ms + 1

        return ASRAudioChunk(
            source_snapshot=self.source_snapshot,
            start_ms=start_ms,
            end_ms=end_ms,
            sample_rate=ASR_AUDIO_SAMPLE_RATE,
            samples=self.buffer[:sample_count],
        )


def _iter_audio_chunks(
    local_source: ASRLocalMediaSource,
    *,
    chunk_samples: int,
    start_sample: int,
    end_sample: int | None,
    av_module,
    numpy_module,
):
    container = None
    try:
        try:
            container = av_module.open(local_source.local_path, mode="r")
        except Exception as error:
            raise ASRAudioError("PyAV could not open local ASR media") from error

        try:
            audio_streams = container.streams.audio
            audio_stream = audio_streams[0]
        except (AttributeError, IndexError, TypeError) as error:
            raise ASRAudioValidationError(
                "local ASR media has no audio stream"
            ) from error

        resampler = _new_resampler(av_module)

        accumulator = None
        emission_cursor = None
        previous_timestamp = None
        previous_time_base = None
        expected_timestamp = None
        saw_decoded_frame = False
        fed_source_frame = False
        last_fed_expected_timestamp = None
        resampler_flushed = False

        try:
            decoded_frames = container.decode(audio_stream)
        except (ASRAudioValidationError, ASRAudioLimitError):
            raise
        except ASRAudioError:
            raise
        except Exception as error:
            raise ASRAudioError(
                "PyAV audio stream decode could not start"
            ) from error

        for frame in _iter_decoded_frames(decoded_frames):
            timestamp, time_base, duration = _frame_timing(frame)
            prior_expected_timestamp = expected_timestamp
            prior_time_base = previous_time_base
            expected_timestamp = _validate_frame_timeline(
                timestamp=timestamp,
                time_base=time_base,
                duration=duration,
                previous_timestamp=previous_timestamp,
                previous_time_base=previous_time_base,
                expected_timestamp=expected_timestamp,
            )
            previous_timestamp = timestamp
            previous_time_base = time_base
            saw_decoded_frame = True
            frame_sample = _timestamp_to_sample_index(timestamp)
            if emission_cursor is None:
                emission_cursor = _EmissionCursor(frame_sample)
                accumulator = _ChunkAccumulator(
                    numpy=numpy_module,
                    source_snapshot=local_source.source_snapshot,
                    start_sample=max(start_sample, frame_sample),
                    chunk_samples=chunk_samples,
                )
            else:
                if prior_expected_timestamp is None:
                    raise ASRAudioValidationError(
                        "audio frame timeline state is incomplete"
                    )

                deviation = timestamp - prior_expected_timestamp
                tolerance = _timestamp_tolerance(
                    prior_time_base,
                    time_base,
                )
                if deviation > tolerance:
                    # A source gap is handled only at a continuous-segment
                    # boundary.  First flush delayed real audio from the
                    # preceding segment, then reconcile that emission cursor
                    # to the expected source boundary.
                    if accumulator is None or emission_cursor is None:
                        raise ASRAudioValidationError(
                            "audio gap has no output timeline"
                        )
                    for chunk in _route_resampler_output(
                        resampler,
                        None,
                        cursor=emission_cursor,
                        accumulator=accumulator,
                        start_sample=start_sample,
                        end_sample=end_sample,
                        numpy=numpy_module,
                    ):
                        yield chunk

                    boundary_sample = _timestamp_to_sample_index(
                        prior_expected_timestamp
                    )
                    if abs(emission_cursor.value - boundary_sample) > 1:
                        raise ASRAudioValidationError(
                            "resampler output cannot reconcile to source boundary"
                        )
                    last_fed_expected_timestamp = None

                    silence_samples = frame_sample - emission_cursor.value
                    if silence_samples < 0:
                        raise ASRAudioValidationError(
                            "source gap has a negative output interval"
                        )

                    silence_start = emission_cursor.value
                    silence_end = frame_sample
                    visible_start = max(start_sample, silence_start)
                    visible_end = silence_end
                    if end_sample is not None:
                        visible_end = min(visible_end, end_sample)
                    if visible_end > visible_start:
                        for chunk in accumulator.add_silence(
                            visible_end - visible_start
                        ):
                            yield chunk

                    emission_cursor.value = frame_sample
                    if (
                        end_sample is not None
                        and emission_cursor.value >= end_sample
                    ):
                        resampler_flushed = True
                        break

                    # A flushed resampler must not be reused across a source
                    # discontinuity.  The current frame begins a new segment.
                    resampler = _new_resampler(av_module)
                    resampler_flushed = False
                elif (
                    end_sample is not None
                    and frame_sample >= end_sample
                ):
                    # The requested absolute end occurs before this frame.
                    # Flush pending real audio from the current segment, but
                    # do not feed an out-of-range frame to the resampler.
                    if accumulator is None or emission_cursor is None:
                        raise ASRAudioValidationError(
                            "audio end has no output timeline"
                        )
                    for chunk in _route_resampler_output(
                        resampler,
                        None,
                        cursor=emission_cursor,
                        accumulator=accumulator,
                        start_sample=start_sample,
                        end_sample=end_sample,
                        numpy=numpy_module,
                    ):
                        yield chunk
                    boundary_sample = _timestamp_to_sample_index(
                        prior_expected_timestamp
                    )
                    if abs(emission_cursor.value - boundary_sample) > 1:
                        raise ASRAudioValidationError(
                            "resampler output cannot reconcile to source boundary"
                        )
                    resampler_flushed = True
                    break

            if (
                end_sample is not None
                and frame_sample >= end_sample
            ):
                break

            if accumulator is None or emission_cursor is None:
                raise ASRAudioValidationError(
                    "audio frame has no output timeline"
                )
            fed_source_frame = True
            for chunk in _route_resampler_output(
                resampler,
                frame,
                cursor=emission_cursor,
                accumulator=accumulator,
                start_sample=start_sample,
                end_sample=end_sample,
                numpy=numpy_module,
            ):
                yield chunk
            last_fed_expected_timestamp = expected_timestamp
            resampler_flushed = False

            if (
                end_sample is not None
                and expected_timestamp >= Fraction(end_sample, ASR_AUDIO_SAMPLE_RATE)
            ):
                break

        if not saw_decoded_frame:
            raise ASRAudioValidationError(
                "local ASR media produced no timestamped audio frame"
            )

        if fed_source_frame and accumulator is not None and emission_cursor is not None:
            if not resampler_flushed:
                for chunk in _route_resampler_output(
                    resampler,
                    None,
                    cursor=emission_cursor,
                    accumulator=accumulator,
                    start_sample=start_sample,
                    end_sample=end_sample,
                    numpy=numpy_module,
                ):
                    yield chunk
                resampler_flushed = True

            if last_fed_expected_timestamp is not None:
                boundary_sample = _timestamp_to_sample_index(
                    last_fed_expected_timestamp
                )
                if abs(emission_cursor.value - boundary_sample) > 1:
                    raise ASRAudioValidationError(
                        "resampler output cannot reconcile to source end"
                    )

            yield from accumulator.finish()
        elif accumulator is not None:
            yield from accumulator.finish()
    finally:
        if container is not None:
            try:
                container.close()
            except Exception:
                pass


def iter_audio_chunks(
    local_source: ASRLocalMediaSource,
    *,
    chunk_seconds,
    start_seconds=0,
    end_seconds=None,
    av_module=None,
    numpy_module=None,
):
    """Return a one-pass iterator of bounded sequential audio chunks."""

    source = _require_local_source(local_source)
    chunk_samples, start_sample, end_sample = _validate_request_range(
        chunk_seconds=chunk_seconds,
        start_seconds=start_seconds,
        end_seconds=end_seconds,
    )
    numpy = _load_numpy(numpy_module)
    av = _load_av(av_module)

    return _iter_audio_chunks(
        source,
        chunk_samples=chunk_samples,
        start_sample=start_sample,
        end_sample=end_sample,
        av_module=av,
        numpy_module=numpy,
    )


__all__ = [
    "ASRAudioChunk",
    "ASRAudioError",
    "ASRAudioLimitError",
    "ASRAudioValidationError",
    "ASR_AUDIO_SAMPLE_RATE",
    "MAX_ASR_AUDIO_CHUNK_SECONDS",
    "MAX_ASR_AUDIO_SAMPLES",
    "iter_audio_chunks",
]
