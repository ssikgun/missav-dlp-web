"""Bounded remote Stage11 ASR client for the GPU worker backend.

The client sends one already-decoded 16 kHz mono float32 audio chunk as a
pickle-free NumPy ``.npy`` payload.  The worker returns chunk-relative ASR
timestamps; this boundary applies the owning chunk offset exactly once and
returns the frozen :class:`ASRSegment` contract used by Stage11.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import io
import json
import math
import re
import socket
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlsplit, urlunsplit

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
    ASRAudioChunk,
    ASR_AUDIO_SAMPLE_RATE,
    MAX_ASR_AUDIO_SAMPLES,
)


REMOTE_ASR_SCHEMA_VERSION = 1
REMOTE_ASR_PATH = "/v1/asr/transcribe"
REMOTE_ASR_CONTENT_TYPE = "application/x-npy"
REMOTE_ASR_MAX_NPY_HEADER_BYTES = 4_096
REMOTE_ASR_MAX_REQUEST_BYTES = (
    MAX_ASR_AUDIO_SAMPLES * 4 + REMOTE_ASR_MAX_NPY_HEADER_BYTES
)
REMOTE_ASR_MAX_RESPONSE_BYTES = 16 * 1024 * 1024
REMOTE_ASR_DEFAULT_ENGINE_VERSION = "1.2.1"


class RemoteASRError(ASRError):
    """Base class for the bounded remote ASR boundary."""


class RemoteASRTransportError(RemoteASRError):
    """Raised when the remote HTTP exchange cannot complete safely."""


class RemoteASRProtocolError(RemoteASRError):
    """Raised when the remote response violates the frozen wire contract."""


class RemoteASRLimitError(RemoteASRError, ASRLimitError):
    """Raised when a remote request or response exceeds its bound."""


@dataclass(frozen=True)
class RemoteASRHTTPResponse:
    """Small injectable HTTP response used by the client transport boundary."""

    status_code: int
    body: bytes


def _load_numpy():
    try:
        import numpy
    except ImportError as error:
        raise RemoteASRError("NumPy is required for remote ASR") from error
    return numpy


def _has_control_characters(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _validate_timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ASRValidationError(
            "request_timeout_seconds must be a positive finite number"
        )

    timeout = float(value)
    if not math.isfinite(timeout) or timeout <= 0:
        raise ASRValidationError(
            "request_timeout_seconds must be a positive finite number"
        )
    return timeout


def _endpoint_from_base_url(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ASRValidationError("base_url must be a nonempty URL")
    if _has_control_characters(value):
        raise ASRValidationError("base_url contains a control character")

    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ASRValidationError(
            "base_url must use an explicit HTTP or HTTPS host"
        )
    if parsed.username is not None or parsed.password is not None:
        raise ASRValidationError("base_url must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ASRValidationError("base_url must not contain a query or fragment")

    path = parsed.path.rstrip("/")
    if not path.endswith(REMOTE_ASR_PATH):
        path += REMOTE_ASR_PATH
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


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


def _validate_max_response_bytes(value: object) -> int:
    if type(value) is not int or value <= 0:
        raise ASRValidationError(
            "max_response_bytes must be a positive integer"
        )
    if value > REMOTE_ASR_MAX_RESPONSE_BYTES:
        raise ASRLimitError(
            "max_response_bytes exceeds the remote response bound"
        )
    return value


def _default_transport(
    endpoint_url: str,
    body: bytes,
    headers: dict[str, str],
    timeout: float,
) -> RemoteASRHTTPResponse:
    request = urllib_request.Request(
        endpoint_url,
        data=body,
        headers=headers,
        method="POST",
    )

    class _NoRedirectHandler(urllib_request.HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            raise RemoteASRTransportError(
                "remote ASR HTTP redirect is not permitted"
            )

    opener = urllib_request.build_opener(_NoRedirectHandler())
    try:
        with opener.open(request, timeout=timeout) as response:
            status_code = response.getcode()
            if type(status_code) is not int:
                raise RemoteASRTransportError(
                    "remote ASR HTTP status is invalid"
                )
            body_bytes = response.read(REMOTE_ASR_MAX_RESPONSE_BYTES + 1)
    except RemoteASRError:
        raise
    except (
        OSError,
        ValueError,
        TimeoutError,
        socket.timeout,
        urllib_error.URLError,
    ) as error:
        raise RemoteASRTransportError("remote ASR HTTP request failed") from error

    if not isinstance(body_bytes, bytes):
        raise RemoteASRTransportError(
            "remote ASR HTTP response body must be bytes"
        )
    return RemoteASRHTTPResponse(status_code, body_bytes)


def _field(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        if name in value:
            return value[name]
    raise RemoteASRProtocolError("remote ASR response is missing " + name)


def _require_response_int(
    value: object,
    *,
    field_name: str,
    minimum: int | None = None,
) -> int:
    if type(value) is not int:
        raise RemoteASRProtocolError(field_name + " must be an integer")
    if minimum is not None and value < minimum:
        raise RemoteASRProtocolError(field_name + " is below its bound")
    return value


def _decode_response_body(body: object) -> object:
    if not isinstance(body, bytes):
        raise RemoteASRProtocolError("remote ASR response body must be bytes")
    if len(body) > REMOTE_ASR_MAX_RESPONSE_BYTES:
        raise RemoteASRLimitError("remote ASR response exceeds its byte bound")
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise RemoteASRProtocolError(
            "remote ASR response is not valid UTF-8 JSON"
        ) from error


def _decode_word(
    value: object,
    *,
    segment_start_ms: int,
    segment_end_ms: int,
) -> ASRWord:
    if not isinstance(value, dict) or set(value) != {
        "start_ms",
        "end_ms",
        "text",
    }:
        raise RemoteASRProtocolError("remote ASR word has an invalid shape")

    start_ms = _require_response_int(
        value["start_ms"],
        field_name="remote ASR word start_ms",
        minimum=0,
    )
    end_ms = _require_response_int(
        value["end_ms"],
        field_name="remote ASR word end_ms",
        minimum=1,
    )
    if start_ms < segment_start_ms or end_ms > segment_end_ms:
        raise RemoteASRProtocolError(
            "remote ASR word lies outside its segment"
        )

    try:
        return ASRWord(
            start_ms=start_ms,
            end_ms=end_ms,
            text=value["text"],
        )
    except ASRValidationError as error:
        raise RemoteASRProtocolError("remote ASR word is invalid") from error


def _decode_segment(
    value: object,
    *,
    chunk: ASRAudioChunk,
    chunk_duration_ms: int,
) -> ASRSegment:
    if not isinstance(value, dict):
        raise RemoteASRProtocolError("remote ASR segment must be an object")

    allowed = {"start_ms", "end_ms", "text", "words"}
    if set(value) - allowed or not {"start_ms", "end_ms", "text"}.issubset(value):
        raise RemoteASRProtocolError("remote ASR segment has an invalid shape")

    relative_start_ms = _require_response_int(
        value["start_ms"],
        field_name="remote ASR segment start_ms",
        minimum=0,
    )
    relative_end_ms = _require_response_int(
        value["end_ms"],
        field_name="remote ASR segment end_ms",
        minimum=1,
    )
    if (
        relative_start_ms >= relative_end_ms
        or relative_end_ms > chunk_duration_ms
    ):
        raise RemoteASRProtocolError(
            "remote ASR segment timestamp is outside its chunk"
        )

    raw_words = value.get("words", ())
    if "words" in value and not isinstance(raw_words, list):
        raise RemoteASRProtocolError("remote ASR segment words must be a list")

    relative_words = tuple(
        _decode_word(
            raw_word,
            segment_start_ms=relative_start_ms,
            segment_end_ms=relative_end_ms,
        )
        for raw_word in raw_words
    )
    try:
        relative_segment = ASRSegment(
            start_ms=relative_start_ms,
            end_ms=relative_end_ms,
            text=value["text"],
            words=relative_words,
        )
    except ASRValidationError as error:
        raise RemoteASRProtocolError("remote ASR segment is invalid") from error

    absolute_words = tuple(
        ASRWord(
            start_ms=chunk.start_ms + word.start_ms,
            end_ms=chunk.start_ms + word.end_ms,
            text=word.text,
        )
        for word in relative_segment.words
    )
    absolute_start_ms = chunk.start_ms + relative_segment.start_ms
    absolute_end_ms = chunk.start_ms + relative_segment.end_ms
    if (
        absolute_start_ms < chunk.start_ms
        or absolute_end_ms > chunk.end_ms
    ):
        raise RemoteASRProtocolError(
            "remote ASR segment absolute timestamp is outside its chunk"
        )

    try:
        return ASRSegment(
            start_ms=absolute_start_ms,
            end_ms=absolute_end_ms,
            text=relative_segment.text,
            words=absolute_words,
        )
    except ASRValidationError as error:
        raise RemoteASRProtocolError(
            "remote ASR absolute segment is invalid"
        ) from error


class RemoteFasterWhisperASR:
    """Remote ``transcribe_chunk`` adapter for the VM122 GPU worker."""

    def __init__(
        self,
        *,
        base_url: str,
        request_timeout_seconds: int | float,
        transport=None,
        max_response_bytes: int = REMOTE_ASR_MAX_RESPONSE_BYTES,
        engine_version: str = REMOTE_ASR_DEFAULT_ENGINE_VERSION,
    ):
        if transport is not None and not callable(transport):
            raise ASRValidationError("transport must be callable")

        self.endpoint_url = _endpoint_from_base_url(base_url)
        self.request_timeout_seconds = _validate_timeout(
            request_timeout_seconds
        )
        self.max_response_bytes = _validate_max_response_bytes(
            max_response_bytes
        )
        self.engine_version = _validate_engine_version(engine_version)
        self.runtime_identity = REMOTE_GPU_LARGE_V3_RUNTIME_IDENTITY
        self._transport = transport or _default_transport

    def _serialize_chunk(self, chunk: ASRAudioChunk) -> bytes:
        numpy = _load_numpy()
        output = io.BytesIO()
        try:
            numpy.save(output, chunk.samples, allow_pickle=False)
        except (OSError, TypeError, ValueError) as error:
            raise RemoteASRProtocolError(
                "audio chunk could not be serialized as NPY"
            ) from error

        body = output.getvalue()
        if len(body) > REMOTE_ASR_MAX_REQUEST_BYTES:
            raise RemoteASRLimitError(
                "remote ASR request exceeds its byte bound"
            )
        return body

    def _decode_response(
        self,
        response: RemoteASRHTTPResponse,
        *,
        chunk: ASRAudioChunk,
        request_body: bytes,
    ) -> tuple[ASRSegment, ...]:
        if type(response.status_code) is not int:
            raise RemoteASRTransportError("remote ASR HTTP status is invalid")
        if not 200 <= response.status_code < 300:
            raise RemoteASRTransportError(
                "remote ASR HTTP request returned a non-success status"
            )
        if not isinstance(response.body, bytes):
            raise RemoteASRTransportError(
                "remote ASR response body must be bytes"
            )
        if len(response.body) > self.max_response_bytes:
            raise RemoteASRLimitError(
                "remote ASR response exceeds its configured byte bound"
            )

        decoded = _decode_response_body(response.body)
        required = {
            "schema_version",
            "engine_version",
            "input_sha256",
            "sample_rate",
            "sample_count",
            "vad_region_count",
            "segments",
        }
        if not isinstance(decoded, dict) or set(decoded) != required:
            raise RemoteASRProtocolError(
                "remote ASR response has an invalid top-level shape"
            )

        schema_version = _require_response_int(
            decoded["schema_version"],
            field_name="remote ASR schema_version",
            minimum=0,
        )
        if schema_version != REMOTE_ASR_SCHEMA_VERSION:
            raise RemoteASRProtocolError(
                "remote ASR schema_version is unsupported"
            )

        response_engine_version = decoded["engine_version"]
        if (
            not isinstance(response_engine_version, str)
            or not response_engine_version.strip()
            or _has_control_characters(response_engine_version)
            or response_engine_version != self.engine_version
        ):
            raise RemoteASRProtocolError(
                "remote ASR engine_version is invalid"
            )

        input_sha256 = decoded["input_sha256"]
        if (
            not isinstance(input_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", input_sha256) is None
            or input_sha256 != hashlib.sha256(request_body).hexdigest()
        ):
            raise RemoteASRProtocolError("remote ASR input SHA-256 mismatch")

        sample_rate = _require_response_int(
            decoded["sample_rate"],
            field_name="remote ASR sample_rate",
            minimum=0,
        )
        if sample_rate != ASR_AUDIO_SAMPLE_RATE:
            raise RemoteASRProtocolError("remote ASR sample_rate is invalid")

        sample_count = _require_response_int(
            decoded["sample_count"],
            field_name="remote ASR sample_count",
            minimum=1,
        )
        if sample_count != int(chunk.samples.size):
            raise RemoteASRProtocolError("remote ASR sample_count mismatch")

        vad_region_count = _require_response_int(
            decoded["vad_region_count"],
            field_name="remote ASR vad_region_count",
            minimum=0,
        )
        if vad_region_count > sample_count:
            raise RemoteASRProtocolError(
                "remote ASR vad_region_count is outside its bound"
            )

        raw_segments = decoded["segments"]
        if not isinstance(raw_segments, list):
            raise RemoteASRProtocolError("remote ASR segments must be a list")
        if len(raw_segments) > MAX_ASR_SEGMENTS:
            raise RemoteASRLimitError(
                "remote ASR segments exceed MAX_ASR_SEGMENTS"
            )

        chunk_duration_ms = chunk.end_ms - chunk.start_ms
        converted: list[ASRSegment] = []
        previous_start_ms = None
        for raw_segment in raw_segments:
            segment = _decode_segment(
                raw_segment,
                chunk=chunk,
                chunk_duration_ms=chunk_duration_ms,
            )
            if (
                previous_start_ms is not None
                and segment.start_ms < previous_start_ms
            ):
                raise RemoteASRProtocolError(
                    "remote ASR segment starts are not nondecreasing"
                )
            previous_start_ms = segment.start_ms
            converted.append(segment)

        return tuple(converted)

    def transcribe_chunk(
        self,
        chunk: ASRAudioChunk,
    ) -> tuple[ASRSegment, ...]:
        """Send one bounded chunk and return absolute Stage11 ASR segments."""

        if not isinstance(chunk, ASRAudioChunk):
            raise ASRValidationError("chunk must be an ASRAudioChunk")

        request_body = self._serialize_chunk(chunk)
        headers = {
            "Accept": "application/json",
            "Content-Type": REMOTE_ASR_CONTENT_TYPE,
            "Content-Length": str(len(request_body)),
            "X-Stage11-ASR-Schema-Version": str(REMOTE_ASR_SCHEMA_VERSION),
            "X-Stage11-ASR-Sample-Rate": str(ASR_AUDIO_SAMPLE_RATE),
        }
        try:
            response = self._transport(
                self.endpoint_url,
                request_body,
                headers,
                self.request_timeout_seconds,
            )
        except RemoteASRError:
            raise
        except (OSError, TimeoutError, ValueError) as error:
            raise RemoteASRTransportError("remote ASR transport failed") from error

        if not isinstance(response, RemoteASRHTTPResponse):
            raise RemoteASRProtocolError(
                "remote ASR transport returned an invalid response"
            )
        return self._decode_response(
            response,
            chunk=chunk,
            request_body=request_body,
        )


__all__ = [
    "REMOTE_ASR_CONTENT_TYPE",
    "REMOTE_ASR_DEFAULT_ENGINE_VERSION",
    "REMOTE_ASR_MAX_NPY_HEADER_BYTES",
    "REMOTE_ASR_MAX_REQUEST_BYTES",
    "REMOTE_ASR_MAX_RESPONSE_BYTES",
    "REMOTE_ASR_PATH",
    "REMOTE_ASR_SCHEMA_VERSION",
    "RemoteASRError",
    "RemoteASRHTTPResponse",
    "RemoteASRLimitError",
    "RemoteASRProtocolError",
    "RemoteASRTransportError",
    "RemoteFasterWhisperASR",
]
