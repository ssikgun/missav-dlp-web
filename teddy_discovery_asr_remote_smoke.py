"""Offline contract smoke tests for the Stage11 remote ASR client."""

from __future__ import annotations

from pathlib import Path
import hashlib
import io
import json
from types import SimpleNamespace

import numpy as np

from teddy_discovery_asr import (
    ASRSourceSnapshot,
    ASRSegment,
    ASRValidationError,
    ASRWord,
    REMOTE_GPU_LARGE_V3_RUNTIME_IDENTITY,
)
from teddy_discovery_asr_audio import ASRAudioChunk, ASR_AUDIO_SAMPLE_RATE
from teddy_discovery_asr_remote import (
    REMOTE_ASR_CONTENT_TYPE,
    REMOTE_ASR_MAX_RESPONSE_BYTES,
    REMOTE_ASR_PATH,
    REMOTE_ASR_SCHEMA_VERSION,
    RemoteASRHTTPResponse,
    RemoteASRLimitError,
    RemoteASRProtocolError,
    RemoteASRTransportError,
    RemoteFasterWhisperASR,
)
from teddy_discovery_subtitle import validate_canonical_holding


def expect(error_type, function):
    try:
        function()
    except error_type:
        return
    raise AssertionError("expected " + error_type.__name__)


def make_chunk() -> ASRAudioChunk:
    video = validate_canonical_holding(
        {
            "dvd_id": "REM-101",
            "storage_root": "jav",
            "relative_path": "REM/REM-101/REM-101.mp4",
            "parse_status": "MATCHED",
            "present": 1,
        },
        "REM-101",
    )
    snapshot = ASRSourceSnapshot.from_holding(
        video,
        source_size=123,
        source_mtime_ns=456,
    )
    return ASRAudioChunk(
        source_snapshot=snapshot,
        start_ms=100_000,
        end_ms=110_000,
        sample_rate=ASR_AUDIO_SAMPLE_RATE,
        samples=np.linspace(
            -0.25,
            0.25,
            ASR_AUDIO_SAMPLE_RATE * 10,
            dtype=np.float32,
        ),
    )


def response_body(request_body, *, sample_count, **updates):
    response = {
        "schema_version": REMOTE_ASR_SCHEMA_VERSION,
        "engine_version": "1.2.1",
        "input_sha256": hashlib.sha256(request_body).hexdigest(),
        "sample_rate": ASR_AUDIO_SAMPLE_RATE,
        "sample_count": sample_count,
        "vad_region_count": 1,
        "segments": [
            {
                "start_ms": 250,
                "end_ms": 1_250,
                "text": "発話",
                "words": [
                    {
                        "start_ms": 400,
                        "end_ms": 900,
                        "text": "発話",
                    },
                ],
            },
        ],
    }
    response.update(updates)
    return json.dumps(
        response,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


class FakeTransport:
    def __init__(self, responder, *, status_code=200):
        self.responder = responder
        self.status_code = status_code
        self.calls = []

    def __call__(self, endpoint_url, body, headers, timeout):
        self.calls.append((endpoint_url, body, headers, timeout))
        return RemoteASRHTTPResponse(
            self.status_code,
            self.responder(body),
        )


def adapter_for(transport):
    return RemoteFasterWhisperASR(
        base_url="http://vm122.test:8082",
        request_timeout_seconds=7.5,
        transport=transport,
    )


def main():
    chunk = make_chunk()
    transport = FakeTransport(
        lambda body: response_body(body, sample_count=int(chunk.samples.size))
    )
    client = adapter_for(transport)
    assert client.runtime_identity == REMOTE_GPU_LARGE_V3_RUNTIME_IDENTITY
    result = client.transcribe_chunk(chunk)

    assert len(transport.calls) == 1
    endpoint_url, body, headers, timeout = transport.calls[0]
    assert endpoint_url == "http://vm122.test:8082" + REMOTE_ASR_PATH
    assert timeout == 7.5
    assert headers == {
        "Accept": "application/json",
        "Content-Type": REMOTE_ASR_CONTENT_TYPE,
        "Content-Length": str(len(body)),
        "X-Stage11-ASR-Schema-Version": str(REMOTE_ASR_SCHEMA_VERSION),
        "X-Stage11-ASR-Sample-Rate": str(ASR_AUDIO_SAMPLE_RATE),
    }
    encoded = np.load(io.BytesIO(body), allow_pickle=False)
    assert encoded.ndim == 1
    assert encoded.dtype == np.dtype("float32")
    assert encoded.shape == chunk.samples.shape
    assert np.array_equal(encoded, chunk.samples)
    assert result == (
        ASRSegment(
            start_ms=100_250,
            end_ms=101_250,
            text="発話",
            words=(
                ASRWord(
                    start_ms=100_400,
                    end_ms=100_900,
                    text="発話",
                ),
            ),
        ),
    )
    assert result[0].start_ms == chunk.start_ms + 250
    assert result[0].end_ms == chunk.start_ms + 1_250
    assert result[0].words[0].start_ms == chunk.start_ms + 400

    def client_with(updates, *, status_code=200, raw=False):
        if raw:
            transport = FakeTransport(lambda body: b"not-json")
        else:
            transport = FakeTransport(
                lambda body: response_body_with_updates(body, updates),
                status_code=status_code,
            )
        return adapter_for(transport), transport

    def response_body_with_updates(body, updates):
        values = dict(updates)
        values.setdefault("sample_count", int(chunk.samples.size))
        return response_body(body, **values)

    mismatch_client, mismatch_transport = client_with(
        {"input_sha256": "0" * 64}
    )
    expect(RemoteASRProtocolError, lambda: mismatch_client.transcribe_chunk(chunk))
    assert len(mismatch_transport.calls) == 1

    schema_client, _ = client_with({"schema_version": 2})
    expect(RemoteASRProtocolError, lambda: schema_client.transcribe_chunk(chunk))

    malformed_client, _ = client_with({}, raw=True)
    expect(RemoteASRProtocolError, lambda: malformed_client.transcribe_chunk(chunk))

    oversized_transport = FakeTransport(
        lambda body: b"x" * (REMOTE_ASR_MAX_RESPONSE_BYTES + 1)
    )
    oversized_client = adapter_for(oversized_transport)
    expect(RemoteASRLimitError, lambda: oversized_client.transcribe_chunk(chunk))

    sample_rate_client, _ = client_with({"sample_rate": 8_000})
    expect(
        RemoteASRProtocolError,
        lambda: sample_rate_client.transcribe_chunk(chunk),
    )
    sample_count_client, _ = client_with(
        {"sample_count": int(chunk.samples.size) + 1}
    )
    expect(
        RemoteASRProtocolError,
        lambda: sample_count_client.transcribe_chunk(chunk),
    )

    outside_client, _ = client_with(
        {
            "segments": [
                {
                    "start_ms": 0,
                    "end_ms": chunk.end_ms - chunk.start_ms + 1,
                    "text": "범위 밖",
                    "words": [],
                },
            ],
        }
    )
    expect(
        RemoteASRProtocolError,
        lambda: outside_client.transcribe_chunk(chunk),
    )

    nonmonotonic_client, _ = client_with(
        {
            "segments": [
                {"start_ms": 2_000, "end_ms": 2_500, "text": "첫째"},
                {"start_ms": 1_000, "end_ms": 1_500, "text": "둘째"},
            ],
        }
    )
    expect(
        RemoteASRProtocolError,
        lambda: nonmonotonic_client.transcribe_chunk(chunk),
    )

    status_client, _ = client_with({}, status_code=503)
    expect(RemoteASRTransportError, lambda: status_client.transcribe_chunk(chunk))

    for invalid_url in ("", "vm122.test:8082", "ftp://vm122.test:8082"):
        expect(
            ASRValidationError,
            lambda invalid_url=invalid_url: RemoteFasterWhisperASR(
                base_url=invalid_url,
                request_timeout_seconds=1,
                transport=FakeTransport(lambda body: b""),
            ),
        )

    source_text = Path(__file__).with_name(
        "teddy_discovery_asr_remote.py"
    ).read_text(encoding="utf-8").lower()
    assert "print(" not in source_text
    assert "logging" not in source_text

    print("STAGE11_REMOTE_ASR_SMOKE=PASS")


if __name__ == "__main__":
    main()
