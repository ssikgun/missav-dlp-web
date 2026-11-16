"""Isolated offline contract smoke for the opt-in Stage11 GPU int8 profile.

No network, media, GPU model loading, or production state access.
"""
from __future__ import annotations

import hashlib
import io
import json
from types import SimpleNamespace

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
    Stage11ASRRequestHandler,
)
from teddy_discovery_asr_remote import (
    REMOTE_ASR_MAX_RESPONSE_BYTES,
    REMOTE_ASR_CONTENT_TYPE,
    REMOTE_ASR_PATH,
    REMOTE_ASR_SCHEMA_VERSION,
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

    # The live server only accepts a real GPU worker. Invoke its HTTP
    # handler against the actual opt-in worker with synthetic request bytes:
    # mismatched headers must be rejected before VAD/model loading.
    class FakeHTTPHandler:
        path = REMOTE_ASR_PATH

        def __init__(self, server_worker, profile_header):
            self.server = SimpleNamespace(worker=server_worker)
            self.headers = {
                "Content-Type": REMOTE_ASR_CONTENT_TYPE,
                "Content-Length": str(len(raw)),
                "X-Stage11-ASR-Schema-Version": str(REMOTE_ASR_SCHEMA_VERSION),
                "X-Stage11-ASR-Sample-Rate": str(ASR_AUDIO_SAMPLE_RATE),
            }
            if profile_header is not None:
                self.headers["X-Stage11-ASR-Runtime-Profile"] = profile_header
            self.rfile = io.BytesIO(raw)
            self.wfile = io.BytesIO()
            self.status = None

        def send_response(self, status):
            self.status = status

        def send_header(self, name, value):
            pass

        def end_headers(self):
            pass

    isolated = FasterWhisperGPUWorker(
        model_factory=FakeFactory(),
        runtime_identity=identity,
        model_path=local_path,
    )
    for bad_profile in (None, "REMOTE_GPU_LARGE_V3", "UNKNOWN"):
        handler = FakeHTTPHandler(isolated, bad_profile)
        Stage11ASRRequestHandler.do_POST(handler)
        assert handler.status == 400
        assert isolated._model is None

    wrong_legacy = FakeHTTPHandler(default_worker, identity.profile)
    Stage11ASRRequestHandler.do_POST(wrong_legacy)
    assert wrong_legacy.status == 400

    # The accepted header can reach a synthetic handler function; still no
    # audio processing or real model initialization.
    isolated.process_request = lambda body, schema_version, sample_rate: b'{"mock":true}'
    matching = FakeHTTPHandler(isolated, identity.profile)
    Stage11ASRRequestHandler.do_POST(matching)
    assert matching.status == 200
    assert matching.wfile.getvalue() == b'{"mock":true}'
    assert isolated._model is None

    print("STAGE11_ASR_INT8_PROFILE_CANDIDATE_SMOKE=PASS")
    print("GPU_MODEL_LOAD=0")
    print("NETWORK_REQUESTS=0")
    print("PRODUCTION_WRITES=0")


if __name__ == "__main__":
    main()
