"""Isolated offline contract smoke for the opt-in Stage11 GPU int8 profile.

No network, media, GPU model loading, or production state access.
"""
from __future__ import annotations

import hashlib
import io
import json

import numpy as np

from teddy_discovery_asr import (
    ASRRuntimeIdentity,
    ASRSourceSnapshot,
    ASRValidationError,
    ASR_RUNTIME_PROFILE_REMOTE_GPU_LARGE_V3_INT8_FLOAT16,
    REMOTE_GPU_LARGE_V3_RUNTIME_IDENTITY,
    REMOTE_GPU_LARGE_V3_INT8_FLOAT16_RUNTIME_IDENTITY,
)
from teddy_discovery_asr_audio import ASRAudioChunk, ASR_AUDIO_SAMPLE_RATE
from teddy_discovery_asr_gpu_worker import (
    FasterWhisperGPUWorker,
    _serialize_response_body,
)
from teddy_discovery_asr_remote import (
    REMOTE_ASR_MAX_RESPONSE_BYTES,
    RemoteASRHTTPResponse,
    RemoteASRProtocolError,
    RemoteFasterWhisperASR,
)
from teddy_discovery_subtitle import validate_canonical_holding


def expect(error_type, callback):
    try:
        callback()
    except error_type:
        return
    raise AssertionError("expected " + error_type.__name__)


class FakeFactory:
    def __init__(self):
        self.calls = []
        self.model = object()

    def __call__(self, reference, **kwargs):
        self.calls.append((reference, kwargs))
        return self.model


def make_chunk():
    holding = validate_canonical_holding({
        "dvd_id": "ASR-101",
        "storage_root": "jav",
        "relative_path": "ASR/ASR-101/ASR-101.mp4",
        "parse_status": "MATCHED",
        "present": 1,
    }, "ASR-101")
    snapshot = ASRSourceSnapshot.from_holding(
        holding, source_size=123, source_mtime_ns=456
    )
    return ASRAudioChunk(
        source_snapshot=snapshot,
        start_ms=0,
        end_ms=1000,
        sample_rate=ASR_AUDIO_SAMPLE_RATE,
        samples=np.zeros(ASR_AUDIO_SAMPLE_RATE, dtype=np.float32),
    )


def as_bytes(chunk):
    buffer = io.BytesIO()
    np.save(buffer, chunk.samples, allow_pickle=False)
    return buffer.getvalue()


def make_response(request_body, chunk, runtime_profile):
    return _serialize_response_body(
        input_sha256=hashlib.sha256(request_body).hexdigest(),
        engine_version="1.2.1",
        sample_count=int(chunk.samples.size),
        vad_region_count=0,
        segments=(),
        max_response_bytes=REMOTE_ASR_MAX_RESPONSE_BYTES,
        runtime_profile=runtime_profile,
    )


def main():
    identity = REMOTE_GPU_LARGE_V3_INT8_FLOAT16_RUNTIME_IDENTITY
    assert identity.profile == ASR_RUNTIME_PROFILE_REMOTE_GPU_LARGE_V3_INT8_FLOAT16
    assert identity.compute_type == "int8_float16"
    assert REMOTE_GPU_LARGE_V3_RUNTIME_IDENTITY.compute_type == "float16"
    expect(ASRValidationError, lambda: ASRRuntimeIdentity(
        engine="faster-whisper", model="large-v3", device="cuda",
        compute_type="int8", cpu_threads=None, num_workers=1
    ))
    expect(ASRValidationError, lambda: FasterWhisperGPUWorker(
        runtime_identity=identity
    ))
    expect(ASRValidationError, lambda: FasterWhisperGPUWorker(
        runtime_identity=identity, model_path="relative/snapshot"
    ))
    expect(ASRValidationError, lambda: FasterWhisperGPUWorker(
        model_path="/tmp/other-model"
    ))

    local_path = "/private/cache/snapshots/pinned"
    fake = FakeFactory()
    worker = FasterWhisperGPUWorker(
        model_factory=fake,
        runtime_identity=identity,
        model_path=local_path,
    )
    assert worker.runtime_identity == identity
    assert worker._get_model() is fake.model
    assert fake.calls == [(local_path, {
        "device": "cuda", "compute_type": "int8_float16",
        "local_files_only": True,
    })]
    assert worker._get_model() is fake.model and len(fake.calls) == 1

    default_factory = FakeFactory()
    default_worker = FasterWhisperGPUWorker(model_factory=default_factory)
    assert default_worker.runtime_identity == REMOTE_GPU_LARGE_V3_RUNTIME_IDENTITY
    assert default_worker._get_model() is default_factory.model
    assert default_factory.calls == [(
        "large-v3", {"device": "cuda", "compute_type": "float16"},
    )]

    chunk = make_chunk()
    raw = as_bytes(chunk)
    correct = make_response(raw, chunk, identity.profile)
    assert json.loads(correct)["runtime_profile"] == identity.profile
    legacy = make_response(raw, chunk, None)
    assert "runtime_profile" not in json.loads(legacy)
    requests = []

    def int8_transport(url, body, headers, timeout):
        requests.append((url, headers))
        assert body == raw
        assert headers["X-Stage11-ASR-Runtime-Profile"] == identity.profile
        return RemoteASRHTTPResponse(200, correct)

    client = RemoteFasterWhisperASR(
        base_url="http://localhost:8091",
        request_timeout_seconds=5,
        transport=int8_transport,
        runtime_identity=identity,
    )
    assert client.runtime_identity == identity
    assert client.transcribe_chunk(chunk) == ()
    assert len(requests) == 1

    def legacy_transport(url, body, headers, timeout):
        assert "X-Stage11-ASR-Runtime-Profile" not in headers
        return RemoteASRHTTPResponse(200, legacy)

    normal = RemoteFasterWhisperASR(
        base_url="http://localhost:8091",
        request_timeout_seconds=5,
        transport=legacy_transport,
    )
    assert normal.runtime_identity == REMOTE_GPU_LARGE_V3_RUNTIME_IDENTITY
    assert normal.transcribe_chunk(chunk) == ()

    for bad in (legacy, make_response(raw, chunk, "REMOTE_GPU_LARGE_V3")):
        rejected = RemoteFasterWhisperASR(
            base_url="http://localhost:8091",
            request_timeout_seconds=5,
            runtime_identity=identity,
            transport=lambda url, body, headers, timeout, bad=bad:
                RemoteASRHTTPResponse(200, bad),
        )
        expect(RemoteASRProtocolError, lambda rejected=rejected:
            rejected.transcribe_chunk(chunk))

    print("STAGE11_ASR_INT8_PROFILE_CANDIDATE_SMOKE=PASS")
    print("GPU_MODEL_LOAD=0")
    print("NETWORK_REQUESTS=0")
    print("PRODUCTION_WRITES=0")


if __name__ == "__main__":
    main()
