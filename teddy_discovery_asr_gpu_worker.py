"""HTTP GPU worker for bounded Stage11 faster-whisper ASR chunks.

The worker accepts one pickle-free NumPy ``.npy`` payload containing a bounded
16 kHz mono float32 chunk.  Silero VAD first identifies speech regions.  Each
region is then transcribed independently by one lazy, reused large-v3 CUDA
adapter, and its sample offset is restored into chunk-relative timestamps.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, HTTPServer
import hashlib
import io
import json
import math

from teddy_discovery_asr import (
    ASRError,
    ASRLimitError,
    ASRSegment,
    ASRValidationError,
    ASRWord,
    REMOTE_GPU_LARGE_V3_RUNTIME_IDENTITY,
    MAX_ASR_SEGMENTS,
)
from teddy_discovery_asr_audio import (
    ASR_AUDIO_SAMPLE_RATE,
    MAX_ASR_AUDIO_SAMPLES,
    _sample_index_to_ms,
)
from teddy_discovery_asr_remote import (
    REMOTE_ASR_CONTENT_TYPE,
    REMOTE_ASR_DEFAULT_ENGINE_VERSION,
    REMOTE_ASR_MAX_NPY_HEADER_BYTES,
    REMOTE_ASR_MAX_REQUEST_BYTES,
    REMOTE_ASR_MAX_RESPONSE_BYTES,
    REMOTE_ASR_PATH,
    REMOTE_ASR_SCHEMA_VERSION,
)
from teddy_discovery_asr_whisper import seconds_to_milliseconds


GPU_ASR_MODEL = "large-v3"
GPU_ASR_DEVICE = "cuda"
GPU_ASR_COMPUTE_TYPE = "float16"
GPU_ASR_ENGINE_VERSION = REMOTE_ASR_DEFAULT_ENGINE_VERSION
GPU_ASR_VAD_THRESHOLD = 0.54
GPU_ASR_SPEECH_PAD_MS = 2_500
GPU_ASR_RUNTIME_IDENTITY = REMOTE_GPU_LARGE_V3_RUNTIME_IDENTITY


class GPUASRError(ASRError):
    """Base class for worker-side ASR protocol and runtime failures."""


class GPUASRProtocolError(GPUASRError):
    """Raised when an input payload or model response is malformed."""


class GPUASRRuntimeError(GPUASRError):
    """Raised when the worker VAD/model runtime cannot complete a request."""


def _load_numpy():
    try:
        import numpy
    except ImportError as error:
        raise GPUASRError("NumPy is required for the GPU ASR worker") from error
    return numpy


def _default_model_factory(model_name: str, **kwargs):
    from faster_whisper import WhisperModel

    return WhisperModel(model_name, **kwargs)


def _default_vad_options_factory(*, threshold: float, speech_pad_ms: int):
    from faster_whisper.vad import VadOptions

    return VadOptions(
        threshold=threshold,
        speech_pad_ms=speech_pad_ms,
    )


def _default_vad_getter(samples, vad_options, *, sampling_rate: int):
    from faster_whisper.vad import get_speech_timestamps

    return get_speech_timestamps(
        samples,
        vad_options,
        sampling_rate=sampling_rate,
    )


def _has_control_characters(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _validate_engine_version(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or _has_control_characters(value)
    ):
        raise ASRValidationError(
            "engine_version must be a nonempty safe string"
        )
    return value


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
    raise GPUASRProtocolError("Whisper output is missing " + name)


def _finite_seconds(value: object, *, field_name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ASRValidationError(field_name + " must be a finite number")
    try:
        numeric = float(value)
        decimal_value = Decimal(str(value))
    except (InvalidOperation, OverflowError, ValueError) as error:
        raise ASRValidationError(field_name + " is invalid") from error
    if not math.isfinite(numeric) or not decimal_value.is_finite():
        raise ASRValidationError(field_name + " must be finite")
    if decimal_value < 0:
        raise ASRValidationError(field_name + " must be nonnegative")
    return decimal_value


def _decode_npy(payload: object):
    if type(payload) is not bytes or not payload:
        raise GPUASRProtocolError("ASR request body must be nonempty bytes")
    if len(payload) > REMOTE_ASR_MAX_REQUEST_BYTES:
        raise ASRLimitError("ASR request body exceeds its byte bound")

    numpy = _load_numpy()
    header_stream = io.BytesIO(payload)
    try:
        version = numpy.lib.format.read_magic(header_stream)
        if version == (1, 0):
            shape, fortran_order, dtype = (
                numpy.lib.format.read_array_header_1_0(header_stream)
            )
        elif version == (2, 0):
            shape, fortran_order, dtype = (
                numpy.lib.format.read_array_header_2_0(header_stream)
            )
        else:
            raise GPUASRProtocolError("unsupported NPY version")
    except GPUASRError:
        raise
    except (EOFError, OSError, TypeError, ValueError, UnicodeError) as error:
        raise GPUASRProtocolError("ASR request is not a valid NPY payload") from error

    if header_stream.tell() > REMOTE_ASR_MAX_NPY_HEADER_BYTES:
        raise ASRLimitError("ASR NPY header exceeds its byte bound")
    if (
        not isinstance(shape, tuple)
        or len(shape) != 1
        or type(shape[0]) is not int
        or shape[0] <= 0
        or shape[0] > MAX_ASR_AUDIO_SAMPLES
    ):
        raise GPUASRProtocolError("ASR NPY sample shape is invalid")
    if type(fortran_order) is not bool:
        raise GPUASRProtocolError("ASR NPY order flag is invalid")
    if dtype != numpy.dtype("float32"):
        raise GPUASRProtocolError("ASR NPY dtype must be float32")

    expected_data_end = (
        header_stream.tell() + shape[0] * numpy.dtype("float32").itemsize
    )
    if expected_data_end != len(payload):
        raise GPUASRProtocolError("ASR NPY payload has unexpected data size")

    try:
        samples = numpy.load(
            io.BytesIO(payload),
            allow_pickle=False,
        )
    except (EOFError, OSError, TypeError, ValueError, UnicodeError) as error:
        raise GPUASRProtocolError("ASR NPY payload could not be decoded") from error

    if (
        not isinstance(samples, numpy.ndarray)
        or samples.ndim != 1
        or samples.dtype != numpy.dtype("float32")
        or int(samples.size) != shape[0]
    ):
        raise GPUASRProtocolError("decoded ASR samples violate the NPY contract")
    if not bool(numpy.isfinite(samples).all()):
        raise GPUASRProtocolError("decoded ASR samples are not finite")
    if bool(numpy.any(samples < -1.0)) or bool(numpy.any(samples > 1.0)):
        raise GPUASRProtocolError("decoded ASR samples are outside [-1, 1]")

    return samples


def _validate_vad_regions(raw_regions: object, *, sample_count: int):
    if not isinstance(raw_regions, list):
        raise GPUASRProtocolError("VAD result must be a list")

    regions = []
    previous_end = 0
    for raw_region in raw_regions:
        if not isinstance(raw_region, dict) or set(raw_region) != {
            "start",
            "end",
        }:
            raise GPUASRProtocolError("VAD region has an invalid shape")
        start = raw_region["start"]
        end = raw_region["end"]
        if (
            type(start) is not int
            or type(end) is not int
            or start < 0
            or end <= start
            or end > sample_count
            or start < previous_end
        ):
            raise GPUASRProtocolError("VAD region bounds are invalid")
        regions.append((start, end))
        previous_end = end

    if len(regions) > sample_count:
        raise ASRLimitError("VAD region count exceeds its bound")
    return tuple(regions)


def _convert_region_words(
    raw_words: object,
    *,
    segment_start_ms: int,
    segment_end_ms: int,
    region_offset_ms: int,
    chunk_duration_ms: int,
) -> tuple[ASRWord, ...]:
    if raw_words is None:
        return ()
    if isinstance(raw_words, (str, bytes, Mapping)):
        raise GPUASRProtocolError("Whisper words must be iterable")
    try:
        iterator = iter(raw_words)
    except TypeError as error:
        raise GPUASRProtocolError("Whisper words must be iterable") from error

    converted = []
    previous_start_ms = None
    for raw_word in iterator:
        raw_start = _field(raw_word, "start")
        raw_end = _field(raw_word, "end")
        raw_start_seconds = _finite_seconds(
            raw_start,
            field_name="Whisper word start",
        )
        raw_end_seconds = _finite_seconds(
            raw_end,
            field_name="Whisper word end",
        )
        if raw_end_seconds < raw_start_seconds:
            raise ASRValidationError("Whisper word end precedes start")

        raw_text = _field(raw_word, "word")
        relative_start_ms = seconds_to_milliseconds(
            raw_start,
            field_name="Whisper word start",
        )
        if raw_end_seconds == raw_start_seconds:
            continue

        relative_end_ms = seconds_to_milliseconds(
            raw_end,
            field_name="Whisper word end",
        )
        if relative_end_ms <= relative_start_ms:
            raise ASRValidationError(
                "positive Whisper word duration collapsed to milliseconds"
            )
        if (
            relative_start_ms < segment_start_ms
            or relative_end_ms > segment_end_ms
        ):
            continue

        word = ASRWord(
            start_ms=region_offset_ms + relative_start_ms,
            end_ms=region_offset_ms + relative_end_ms,
            text=raw_text,
        )
        if (
            previous_start_ms is not None
            and relative_start_ms < previous_start_ms
        ):
            raise ASRValidationError(
                "Whisper word start times must be nondecreasing"
            )
        if word.start_ms < 0 or word.end_ms > chunk_duration_ms:
            raise ASRValidationError(
                "Whisper word lies outside the audio chunk"
            )
        previous_start_ms = relative_start_ms
        converted.append(word)

    return tuple(converted)


def _convert_region_segments(
    raw_segments: object,
    *,
    region_start_sample: int,
    region_end_sample: int,
    sample_count: int,
    aggregate_count: int,
) -> tuple[ASRSegment, ...]:
    if isinstance(raw_segments, (str, bytes, Mapping)):
        raise GPUASRProtocolError("Whisper segments must be iterable")
    try:
        iterator = iter(raw_segments)
    except TypeError as error:
        raise GPUASRProtocolError("Whisper segments must be iterable") from error

    region_offset_ms = _sample_index_to_ms(region_start_sample)
    region_duration_ms = _sample_index_to_ms(
        region_end_sample - region_start_sample
    )
    chunk_duration_ms = _sample_index_to_ms(sample_count)
    converted = []
    previous_start_ms = None
    for raw_segment in iterator:
        if aggregate_count + len(converted) >= MAX_ASR_SEGMENTS:
            raise ASRLimitError("Whisper result exceeds MAX_ASR_SEGMENTS")

        raw_start = _field(raw_segment, "start")
        raw_end = _field(raw_segment, "end")
        raw_start_seconds = _finite_seconds(
            raw_start,
            field_name="Whisper segment start",
        )
        raw_end_seconds = _finite_seconds(
            raw_end,
            field_name="Whisper segment end",
        )
        if raw_end_seconds <= raw_start_seconds:
            raise ASRValidationError("Whisper segment duration is invalid")

        relative_start_ms = seconds_to_milliseconds(
            raw_start,
            field_name="Whisper segment start",
        )
        relative_end_ms = seconds_to_milliseconds(
            raw_end,
            field_name="Whisper segment end",
        )
        if (
            relative_start_ms >= relative_end_ms
            or relative_end_ms > region_duration_ms
        ):
            raise ASRValidationError(
                "Whisper segment lies outside its speech region"
            )
        if (
            previous_start_ms is not None
            and relative_start_ms < previous_start_ms
        ):
            raise ASRValidationError(
                "Whisper segment starts must be nondecreasing"
            )

        segment_start_ms = region_offset_ms + relative_start_ms
        segment_end_ms = region_offset_ms + relative_end_ms
        if segment_end_ms > chunk_duration_ms:
            raise ASRValidationError(
                "Whisper segment lies outside its audio chunk"
            )
        words = _convert_region_words(
            _field(raw_segment, "words", None),
            segment_start_ms=relative_start_ms,
            segment_end_ms=relative_end_ms,
            region_offset_ms=region_offset_ms,
            chunk_duration_ms=chunk_duration_ms,
        )
        try:
            segment = ASRSegment(
                start_ms=segment_start_ms,
                end_ms=segment_end_ms,
                text=_field(raw_segment, "text"),
                words=words,
            )
        except ASRValidationError as error:
            raise GPUASRProtocolError("Whisper segment is invalid") from error

        previous_start_ms = relative_start_ms
        converted.append(segment)

    return tuple(converted)


class FasterWhisperGPUWorker:
    """Lazy, single-model VM122 worker for VAD-region ASR requests."""

    def __init__(
        self,
        *,
        model_factory=None,
        vad_getter=None,
        vad_options_factory=None,
        engine_version: str = GPU_ASR_ENGINE_VERSION,
        max_response_bytes: int = REMOTE_ASR_MAX_RESPONSE_BYTES,
    ):
        if model_factory is not None and not callable(model_factory):
            raise ASRValidationError("model_factory must be callable")
        if vad_getter is not None and not callable(vad_getter):
            raise ASRValidationError("vad_getter must be callable")
        if vad_options_factory is not None and not callable(vad_options_factory):
            raise ASRValidationError(
                "vad_options_factory must be callable"
            )
        if type(max_response_bytes) is not int or max_response_bytes <= 0:
            raise ASRValidationError(
                "max_response_bytes must be a positive integer"
            )
        if max_response_bytes > REMOTE_ASR_MAX_RESPONSE_BYTES:
            raise ASRLimitError(
                "max_response_bytes exceeds the worker response bound"
            )

        self.engine_version = _validate_engine_version(engine_version)
        self.max_response_bytes = max_response_bytes
        self.runtime_identity = GPU_ASR_RUNTIME_IDENTITY
        self._model_factory = model_factory or _default_model_factory
        self._vad_getter = vad_getter or _default_vad_getter
        self._vad_options_factory = (
            vad_options_factory or _default_vad_options_factory
        )
        self._model = None

    def _get_model(self):
        if self._model is None:
            try:
                self._model = self._model_factory(
                    GPU_ASR_MODEL,
                    device=GPU_ASR_DEVICE,
                    compute_type=GPU_ASR_COMPUTE_TYPE,
                )
            except Exception as error:
                raise GPUASRRuntimeError(
                    "GPU faster-whisper model could not be created"
                ) from error
        return self._model

    def _speech_regions(self, samples):
        try:
            options = self._vad_options_factory(
                threshold=GPU_ASR_VAD_THRESHOLD,
                speech_pad_ms=GPU_ASR_SPEECH_PAD_MS,
            )
            raw_regions = self._vad_getter(
                samples,
                options,
                sampling_rate=ASR_AUDIO_SAMPLE_RATE,
            )
        except (ASRValidationError, ASRLimitError, GPUASRError):
            raise
        except Exception as error:
            raise GPUASRRuntimeError("Silero VAD could not process audio") from error

        return _validate_vad_regions(
            raw_regions,
            sample_count=int(samples.size),
        )

    def _transcribe_region(
        self,
        model: object,
        samples,
        *,
        region_start_sample: int,
        region_end_sample: int,
        sample_count: int,
        aggregate_count: int,
    ) -> tuple[ASRSegment, ...]:
        region_samples = samples[region_start_sample:region_end_sample]
        try:
            response = model.transcribe(
                region_samples,
                language="ja",
                task="transcribe",
                temperature=0.0,
                word_timestamps=True,
                vad_filter=False,
            )
        except (ASRValidationError, ASRLimitError, GPUASRError):
            raise
        except Exception as error:
            raise GPUASRRuntimeError(
                "GPU faster-whisper region transcription failed"
            ) from error

        if not isinstance(response, tuple) or len(response) != 2:
            raise GPUASRProtocolError(
                "faster-whisper response must be a two-item tuple"
            )
        info = response[1]
        detected_language = _field(info, "language", None)
        if detected_language is not None and detected_language != "ja":
            raise ASRValidationError(
                "faster-whisper detected a non-Japanese language"
            )

        return _convert_region_segments(
            response[0],
            region_start_sample=region_start_sample,
            region_end_sample=region_end_sample,
            sample_count=sample_count,
            aggregate_count=aggregate_count,
        )

    def process_request(
        self,
        payload: bytes,
        *,
        schema_version: int,
        sample_rate: int,
    ) -> bytes:
        """Process one validated wire request and return deterministic JSON."""

        if type(schema_version) is not int or schema_version != REMOTE_ASR_SCHEMA_VERSION:
            raise GPUASRProtocolError("unsupported ASR schema_version")
        if type(sample_rate) is not int or sample_rate != ASR_AUDIO_SAMPLE_RATE:
            raise GPUASRProtocolError("unsupported ASR sample_rate")
        if type(payload) is not bytes:
            raise GPUASRProtocolError("ASR request body must be bytes")
        if len(payload) > REMOTE_ASR_MAX_REQUEST_BYTES:
            raise ASRLimitError("ASR request body exceeds its byte bound")

        input_sha256 = hashlib.sha256(payload).hexdigest()
        samples = _decode_npy(payload)
        sample_count = int(samples.size)
        regions = self._speech_regions(samples)
        aggregated: list[ASRSegment] = []
        previous_start_ms = None
        previous_end_ms = None

        if regions:
            model = self._get_model()
            for region_start_sample, region_end_sample in regions:
                region_segments = self._transcribe_region(
                    model,
                    samples,
                    region_start_sample=region_start_sample,
                    region_end_sample=region_end_sample,
                    sample_count=sample_count,
                    aggregate_count=len(aggregated),
                )
                for segment in region_segments:
                    if (
                        previous_start_ms is not None
                        and segment.start_ms < previous_start_ms
                    ):
                        raise ASRValidationError(
                            "ASR segment starts are not nondecreasing"
                        )
                    if (
                        previous_end_ms is not None
                        and segment.start_ms < previous_end_ms
                    ):
                        raise ASRValidationError(
                            "ASR regions produced overlapping segments"
                        )
                    if len(aggregated) >= MAX_ASR_SEGMENTS:
                        raise ASRLimitError(
                            "ASR result exceeds MAX_ASR_SEGMENTS"
                        )
                    aggregated.append(segment)
                    previous_start_ms = segment.start_ms
                    previous_end_ms = segment.end_ms

        response = {
            "schema_version": REMOTE_ASR_SCHEMA_VERSION,
            "engine_version": self.engine_version,
            "input_sha256": input_sha256,
            "sample_rate": ASR_AUDIO_SAMPLE_RATE,
            "sample_count": sample_count,
            "vad_region_count": len(regions),
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
                for segment in aggregated
            ],
        }
        try:
            response_body = json.dumps(
                response,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise GPUASRProtocolError(
                "ASR response could not be serialized"
            ) from error
        if len(response_body) > self.max_response_bytes:
            raise ASRLimitError("ASR response exceeds its byte bound")
        return response_body


def _error_response(handler: BaseHTTPRequestHandler, *, status: int):
    body = b'{"error":"stage11_asr_request_failed"}'
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class Stage11ASRRequestHandler(BaseHTTPRequestHandler):
    """Minimal HTTP boundary with bounded body reads and no transcript logs."""

    protocol_version = "HTTP/1.0"

    def log_message(self, format, *args):
        return

    def do_POST(self):
        if self.path != REMOTE_ASR_PATH:
            _error_response(self, status=404)
            return
        if self.headers.get("Content-Type") != REMOTE_ASR_CONTENT_TYPE:
            _error_response(self, status=415)
            return

        content_length = self.headers.get("Content-Length")
        if content_length is None or not content_length.isdigit():
            _error_response(self, status=400)
            return
        body_length = int(content_length)
        if body_length <= 0 or body_length > REMOTE_ASR_MAX_REQUEST_BYTES:
            _error_response(self, status=413)
            return
        body = self.rfile.read(body_length)
        if len(body) != body_length:
            _error_response(self, status=400)
            return

        schema_header = self.headers.get("X-Stage11-ASR-Schema-Version")
        sample_rate_header = self.headers.get("X-Stage11-ASR-Sample-Rate")
        if schema_header != str(REMOTE_ASR_SCHEMA_VERSION):
            _error_response(self, status=400)
            return
        if sample_rate_header != str(ASR_AUDIO_SAMPLE_RATE):
            _error_response(self, status=400)
            return

        try:
            response_body = self.server.worker.process_request(
                body,
                schema_version=REMOTE_ASR_SCHEMA_VERSION,
                sample_rate=ASR_AUDIO_SAMPLE_RATE,
            )
        except ASRLimitError:
            _error_response(self, status=413)
            return
        except (ASRValidationError, GPUASRProtocolError):
            _error_response(self, status=400)
            return
        except GPUASRRuntimeError:
            _error_response(self, status=503)
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)


class Stage11ASRHTTPServer(HTTPServer):
    """Single-request-at-a-time server preserving one model execution stream."""

    def __init__(self, server_address, worker: FasterWhisperGPUWorker):
        if not isinstance(worker, FasterWhisperGPUWorker):
            raise ASRValidationError("worker must be a FasterWhisperGPUWorker")
        self.worker = worker
        super().__init__(server_address, Stage11ASRRequestHandler)


def serve_http(
    worker: FasterWhisperGPUWorker,
    *,
    host: str,
    port: int,
) -> None:
    """Serve the worker until the embedding process stops it."""

    if not isinstance(host, str) or not host or _has_control_characters(host):
        raise ASRValidationError("host must be a safe nonempty string")
    if type(port) is not int or not 0 <= port <= 65_535:
        raise ASRValidationError("port must be between 0 and 65535")

    server = Stage11ASRHTTPServer((host, port), worker)
    try:
        server.serve_forever()
    finally:
        server.server_close()


__all__ = [
    "GPU_ASR_COMPUTE_TYPE",
    "GPU_ASR_DEVICE",
    "GPU_ASR_ENGINE_VERSION",
    "GPU_ASR_MODEL",
    "GPU_ASR_RUNTIME_IDENTITY",
    "GPU_ASR_SPEECH_PAD_MS",
    "GPU_ASR_VAD_THRESHOLD",
    "FasterWhisperGPUWorker",
    "GPUASRError",
    "GPUASRProtocolError",
    "GPUASRRuntimeError",
    "Stage11ASRHTTPServer",
    "Stage11ASRRequestHandler",
    "serve_http",
]
