"""Offline fake-VAD/fake-model smoke tests for the VM122 ASR worker."""

from __future__ import annotations

from pathlib import Path
import hashlib
import io
import json
from types import SimpleNamespace

import numpy as np

from teddy_discovery_asr import (
    ASRValidationError,
    REMOTE_GPU_LARGE_V3_RUNTIME_IDENTITY,
)
from teddy_discovery_asr_audio import ASR_AUDIO_SAMPLE_RATE
from teddy_discovery_asr_gpu_worker import (
    GPU_ASR_COMPUTE_TYPE,
    GPU_ASR_DEVICE,
    GPU_ASR_MODEL,
    GPU_ASR_SPEECH_PAD_MS,
    GPU_ASR_VAD_THRESHOLD,
    FasterWhisperGPUWorker,
    GPUASRProtocolError,
)
from teddy_discovery_asr_remote import REMOTE_ASR_SCHEMA_VERSION


def expect(error_type, function):
    try:
        function()
    except error_type:
        return
    raise AssertionError("expected " + error_type.__name__)


def npy_payload(samples):
    output = io.BytesIO()
    np.save(output, samples, allow_pickle=False)
    return output.getvalue()


class FakeVAD:
    def __init__(self, regions):
        self.regions = regions
        self.calls = []

    def __call__(self, samples, options, *, sampling_rate):
        self.calls.append((samples, options, sampling_rate))
        return self.regions


class FakeModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def transcribe(self, audio, **kwargs):
        self.calls.append((audio, kwargs))
        if not self.responses:
            raise AssertionError("unexpected extra model call")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response, SimpleNamespace(language="ja")


class FakeModelFactory:
    def __init__(self, model):
        self.model = model
        self.calls = []

    def __call__(self, model_name, **kwargs):
        self.calls.append((model_name, kwargs))
        return self.model


def raw_segment(start, end, text, words=()):
    return SimpleNamespace(
        start=start,
        end=end,
        text=text,
        words=list(words),
    )


def main():
    samples = np.linspace(
        -0.25,
        0.25,
        ASR_AUDIO_SAMPLE_RATE * 10,
        dtype=np.float32,
    )
    regions = [
        {"start": 1_600, "end": 3_200},
        {"start": 80_000, "end": 81_600},
    ]
    model = FakeModel(
        [
            [
                raw_segment(
                    0.025,
                    0.075,
                    "第一",
                    [SimpleNamespace(start=0.030, end=0.060, word="第一")],
                ),
            ],
            [
                raw_segment(
                    0.025,
                    0.075,
                    "第二",
                    [SimpleNamespace(start=0.030, end=0.060, word="第二")],
                ),
            ],
        ]
    )
    vad = FakeVAD(regions)
    factory = FakeModelFactory(model)
    worker = FasterWhisperGPUWorker(
        model_factory=factory,
        vad_getter=vad,
    )
    assert worker.runtime_identity == REMOTE_GPU_LARGE_V3_RUNTIME_IDENTITY
    payload = npy_payload(samples)
    response_body = worker.process_request(
        payload,
        schema_version=REMOTE_ASR_SCHEMA_VERSION,
        sample_rate=ASR_AUDIO_SAMPLE_RATE,
    )
    response = json.loads(response_body.decode("utf-8"))

    assert factory.calls == [
        (
            GPU_ASR_MODEL,
            {
                "device": GPU_ASR_DEVICE,
                "compute_type": GPU_ASR_COMPUTE_TYPE,
            },
        ),
    ]
    assert len(vad.calls) == 1
    vad_samples, vad_options, vad_rate = vad.calls[0]
    assert vad_samples.shape == samples.shape
    assert vad_rate == ASR_AUDIO_SAMPLE_RATE
    assert vad_options.threshold == GPU_ASR_VAD_THRESHOLD
    assert vad_options.speech_pad_ms == GPU_ASR_SPEECH_PAD_MS
    assert len(model.calls) == 2
    assert np.shares_memory(model.calls[0][0], vad_samples)
    assert np.shares_memory(model.calls[1][0], vad_samples)
    assert model.calls[0][0].size == 1_600
    assert model.calls[1][0].size == 1_600
    for _, kwargs in model.calls:
        assert kwargs == {
            "language": "ja",
            "task": "transcribe",
            "temperature": 0.0,
            "word_timestamps": True,
            "vad_filter": False,
        }

    assert response == {
        "schema_version": REMOTE_ASR_SCHEMA_VERSION,
        "engine_version": "1.2.1",
        "input_sha256": hashlib.sha256(payload).hexdigest(),
        "sample_rate": ASR_AUDIO_SAMPLE_RATE,
        "sample_count": samples.size,
        "vad_region_count": 2,
        "segments": [
            {
                "start_ms": 125,
                "end_ms": 175,
                "text": "第一",
                "words": [
                    {"start_ms": 130, "end_ms": 160, "text": "第一"},
                ],
            },
            {
                "start_ms": 5_025,
                "end_ms": 5_075,
                "text": "第二",
                "words": [
                    {"start_ms": 5_030, "end_ms": 5_060, "text": "第二"},
                ],
            },
        ],
    }
    assert response["segments"][1]["start_ms"] > response["segments"][0]["end_ms"]

    silent_vad = FakeVAD([])
    silent_factory = FakeModelFactory(FakeModel([]))
    silent_worker = FasterWhisperGPUWorker(
        model_factory=silent_factory,
        vad_getter=silent_vad,
    )
    silent_response = json.loads(
        silent_worker.process_request(
            payload,
            schema_version=REMOTE_ASR_SCHEMA_VERSION,
            sample_rate=ASR_AUDIO_SAMPLE_RATE,
        ).decode("utf-8")
    )
    assert silent_response["vad_region_count"] == 0
    assert silent_response["segments"] == []
    assert silent_factory.calls == []

    invalid_float_payload = npy_payload(
        np.zeros(10, dtype=np.float64)
    )
    expect(
        GPUASRProtocolError,
        lambda: worker.process_request(
            invalid_float_payload,
            schema_version=REMOTE_ASR_SCHEMA_VERSION,
            sample_rate=ASR_AUDIO_SAMPLE_RATE,
        ),
    )
    invalid_shape_payload = npy_payload(
        np.zeros((2, 5), dtype=np.float32)
    )
    expect(
        GPUASRProtocolError,
        lambda: worker.process_request(
            invalid_shape_payload,
            schema_version=REMOTE_ASR_SCHEMA_VERSION,
            sample_rate=ASR_AUDIO_SAMPLE_RATE,
        ),
    )

    bad_schema_worker = FasterWhisperGPUWorker(
        model_factory=FakeModelFactory(FakeModel([])),
        vad_getter=FakeVAD([]),
    )
    expect(
        GPUASRProtocolError,
        lambda: bad_schema_worker.process_request(
            payload,
            schema_version=2,
            sample_rate=ASR_AUDIO_SAMPLE_RATE,
        ),
    )
    expect(
        GPUASRProtocolError,
        lambda: bad_schema_worker.process_request(
            payload,
            schema_version=REMOTE_ASR_SCHEMA_VERSION,
            sample_rate=8_000,
        ),
    )

    overlapping_vad = FakeVAD([
        {"start": 1_000, "end": 2_000},
        {"start": 1_999, "end": 3_000},
    ])
    overlapping_worker = FasterWhisperGPUWorker(vad_getter=overlapping_vad)
    expect(
        GPUASRProtocolError,
        lambda: overlapping_worker.process_request(
            payload,
            schema_version=REMOTE_ASR_SCHEMA_VERSION,
            sample_rate=ASR_AUDIO_SAMPLE_RATE,
        ),
    )

    source_text = Path(__file__).with_name(
        "teddy_discovery_asr_gpu_worker.py"
    ).read_text(encoding="utf-8").lower()
    assert "print(" not in source_text
    assert "logging" not in source_text

    print("STAGE11_GPU_ASR_WORKER_SMOKE=PASS")


if __name__ == "__main__":
    main()
