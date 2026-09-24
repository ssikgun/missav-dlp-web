"""Offline fake-VAD/fake-model smoke tests for the VM122 ASR worker."""

from __future__ import annotations

from contextlib import redirect_stdout
from pathlib import Path
import hashlib
import io
import json
from types import SimpleNamespace

import numpy as np

from teddy_discovery_asr import (
    ASRLimitError,
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
    GPUASRRuntimeError,
    Stage11ASRRequestHandler,
)
from teddy_discovery_asr_remote import (
    REMOTE_ASR_CONTENT_TYPE,
    REMOTE_ASR_SCHEMA_VERSION,
    REMOTE_ASR_PATH,
    REMOTE_ASR_TARGETED_PATH,
    REMOTE_ASR_TARGETED_DIAGNOSTIC_PATH,
)


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


def raw_segment(
    start, end, text, words=(), *, avg_logprob=-0.25,
    no_speech_prob=0.02, compression_ratio=1.1, temperature=0.0,
):
    return SimpleNamespace(
        start=start,
        end=end,
        text=text,
        words=list(words),
        avg_logprob=avg_logprob,
        no_speech_prob=no_speech_prob,
        compression_ratio=compression_ratio,
        temperature=temperature,
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

    empty_word_model = FakeModel(
        [
            [
                raw_segment(
                    0.005,
                    0.015,
                    "empty word segment",
                    [SimpleNamespace(start=0.006, end=0.014, word="")],
                ),
                raw_segment(
                    0.020,
                    0.030,
                    "whitespace word segment",
                    [SimpleNamespace(start=0.021, end=0.029, word="   ")],
                ),
                raw_segment(
                    0.035,
                    0.055,
                    "mixed word segment",
                    [
                        SimpleNamespace(
                            start=0.036,
                            end=0.040,
                            word="before",
                        ),
                        SimpleNamespace(
                            start=0.041,
                            end=0.045,
                            word="\r\n\t",
                        ),
                        SimpleNamespace(
                            start=0.046,
                            end=0.054,
                            word="after",
                        ),
                    ],
                ),
                raw_segment(
                    0.060,
                    0.080,
                    "all empty word segment",
                    [
                        SimpleNamespace(start=0.061, end=0.064, word=""),
                        SimpleNamespace(start=0.065, end=0.069, word="   "),
                        SimpleNamespace(
                            start=0.070,
                            end=0.079,
                            word="\r\n",
                        ),
                    ],
                ),
                raw_segment(
                    0.085,
                    0.095,
                    "zero duration word segment",
                    [
                        SimpleNamespace(start=0.086, end=0.086, word="zero"),
                        SimpleNamespace(start=0.087, end=0.094, word="valid"),
                    ],
                ),
                raw_segment(
                    0.100,
                    0.120,
                    "outside segment word segment",
                    [SimpleNamespace(start=0.090, end=0.095, word="outside")],
                ),
            ],
        ]
    )
    empty_word_worker = FasterWhisperGPUWorker(
        model_factory=FakeModelFactory(empty_word_model),
        vad_getter=FakeVAD([{"start": 0, "end": 3_200}]),
    )
    empty_word_response = json.loads(
        empty_word_worker.process_request(
            payload,
            schema_version=REMOTE_ASR_SCHEMA_VERSION,
            sample_rate=ASR_AUDIO_SAMPLE_RATE,
        ).decode("utf-8")
    )
    assert empty_word_response["segments"] == [
        {
            "start_ms": 5,
            "end_ms": 15,
            "text": "empty word segment",
            "words": [],
        },
        {
            "start_ms": 20,
            "end_ms": 30,
            "text": "whitespace word segment",
            "words": [],
        },
        {
            "start_ms": 35,
            "end_ms": 55,
            "text": "mixed word segment",
            "words": [
                {"start_ms": 36, "end_ms": 40, "text": "before"},
                {"start_ms": 46, "end_ms": 54, "text": "after"},
            ],
        },
        {
            "start_ms": 60,
            "end_ms": 80,
            "text": "all empty word segment",
            "words": [],
        },
        {
            "start_ms": 85,
            "end_ms": 95,
            "text": "zero duration word segment",
            "words": [
                {"start_ms": 87, "end_ms": 94, "text": "valid"},
            ],
        },
        {
            "start_ms": 100,
            "end_ms": 120,
            "text": "outside segment word segment",
            "words": [],
        },
    ]

    invalid_word_worker = FasterWhisperGPUWorker(
        model_factory=FakeModelFactory(
            FakeModel(
                [
                    [
                        raw_segment(
                            0.010,
                            0.020,
                            "invalid word segment",
                            [
                                SimpleNamespace(
                                    start=0.011,
                                    end=0.019,
                                    word=None,
                                ),
                            ],
                        ),
                    ],
                ]
            )
        ),
        vad_getter=FakeVAD([{"start": 0, "end": 1_600}]),
    )
    expect(
        ASRValidationError,
        lambda: invalid_word_worker.process_request(
            payload,
            schema_version=REMOTE_ASR_SCHEMA_VERSION,
            sample_rate=ASR_AUDIO_SAMPLE_RATE,
        ),
    )

    for invalid_segment in (
        raw_segment(0.010, float("nan"), "invalid timestamp"),
        raw_segment(0.030, 0.020, "invalid timestamp"),
        raw_segment(
            0.001,
            0.010,
            "collapsed timestamp",
            [SimpleNamespace(start=0.0001, end=0.0002, word="word")],
        ),
    ):
        timestamp_worker = FasterWhisperGPUWorker(
            model_factory=FakeModelFactory(FakeModel([[invalid_segment]])),
            vad_getter=FakeVAD([{"start": 0, "end": 1_600}]),
        )
        expect(
            ASRValidationError,
            lambda timestamp_worker=timestamp_worker: timestamp_worker.process_request(
                payload,
                schema_version=REMOTE_ASR_SCHEMA_VERSION,
                sample_rate=ASR_AUDIO_SAMPLE_RATE,
            ),
        )

    targeted_vad = FakeVAD([
        {"start": 0, "end": 1_000},
    ])
    targeted_model = FakeModel(
        [
            [
                raw_segment(
                    0.125,
                    0.175,
                    "targeted",
                    [SimpleNamespace(start=0.130, end=0.160, word="targeted")],
                ),
            ],
            [
                raw_segment(
                    0.125,
                    0.175,
                    "targeted",
                    [SimpleNamespace(start=0.130, end=0.160, word="targeted")],
                ),
            ],
        ]
    )
    targeted_worker = FasterWhisperGPUWorker(
        model_factory=FakeModelFactory(targeted_model),
        vad_getter=targeted_vad,
    )
    targeted_first = targeted_worker.process_targeted_request(
        payload,
        schema_version=REMOTE_ASR_SCHEMA_VERSION,
        sample_rate=ASR_AUDIO_SAMPLE_RATE,
    )
    targeted_second = targeted_worker.process_targeted_request(
        payload,
        schema_version=REMOTE_ASR_SCHEMA_VERSION,
        sample_rate=ASR_AUDIO_SAMPLE_RATE,
    )
    targeted_response = json.loads(targeted_first.decode("utf-8"))
    assert targeted_first == targeted_second
    assert targeted_vad.calls == []
    assert len(targeted_model.calls) == 2
    assert all(
        np.array_equal(call[0], samples)
        and call[0].dtype == samples.dtype
        and call[0].size == samples.size
        for call in targeted_model.calls
    )
    assert all(
        call[1] == {
            "language": "ja",
            "task": "transcribe",
            "temperature": 0.0,
            "word_timestamps": True,
            "vad_filter": False,
        }
        for call in targeted_model.calls
    )
    assert targeted_response["vad_region_count"] == 0
    assert targeted_response["segments"] == [
        {
            "start_ms": 125,
            "end_ms": 175,
            "text": "targeted",
            "words": [
                {"start_ms": 130, "end_ms": 160, "text": "targeted"},
            ],
        },
    ]

    diagnostic_model = FakeModel([[
        raw_segment(
            0.125, 0.175, "must-not-leak",
            [SimpleNamespace(start=0.130, end=0.160, word="secret-token")],
            avg_logprob=-0.375,
            no_speech_prob=0.125,
            compression_ratio=1.25,
            temperature=0.0,
        ),
    ]])
    diagnostic_worker = FasterWhisperGPUWorker(
        model_factory=FakeModelFactory(diagnostic_model),
        vad_getter=FakeVAD([]),
    )
    diagnostic_body = diagnostic_worker.process_targeted_diagnostic_request(
        payload,
        schema_version=REMOTE_ASR_SCHEMA_VERSION,
        sample_rate=ASR_AUDIO_SAMPLE_RATE,
    )
    diagnostic_response = json.loads(diagnostic_body.decode("utf-8"))
    assert set(diagnostic_response) == {
        "schema_version", "engine_version", "input_sha256", "sample_rate",
        "sample_count", "segment_count", "segments",
    }
    assert diagnostic_response["segment_count"] == 1
    assert diagnostic_response["segments"] == [{
        "start_ms": 125,
        "end_ms": 175,
        "avg_logprob": -0.375,
        "no_speech_prob": 0.125,
        "compression_ratio": 1.25,
        "temperature": 0.0,
    }]
    assert b"must-not-leak" not in diagnostic_body
    assert b"secret-token" not in diagnostic_body
    assert b'"text"' not in diagnostic_body
    assert b'"words"' not in diagnostic_body

    # Targeted requests run the model without VAD; an empty model iterable is
    # a successful response, not an error or a missing planned window.
    empty_targeted_model = FakeModel([[]])
    empty_targeted_vad = FakeVAD([])
    empty_targeted_worker = FasterWhisperGPUWorker(
        model_factory=FakeModelFactory(empty_targeted_model),
        vad_getter=empty_targeted_vad,
    )
    empty_targeted_response = json.loads(
        empty_targeted_worker.process_targeted_request(
            payload,
            schema_version=REMOTE_ASR_SCHEMA_VERSION,
            sample_rate=ASR_AUDIO_SAMPLE_RATE,
        ).decode("utf-8")
    )
    assert empty_targeted_response["segments"] == []
    assert empty_targeted_response["vad_region_count"] == 0
    assert len(empty_targeted_model.calls) == 1
    assert empty_targeted_vad.calls == []

    class UnknownEndpointHandler:
        path = "/v1/asr/unknown"
        headers = {}
        wfile = io.BytesIO()

        def __init__(self):
            self.status = None

        def send_response(self, status):
            self.status = status

        def send_header(self, name, value):
            return None

        def end_headers(self):
            return None

    unknown_handler = UnknownEndpointHandler()
    Stage11ASRRequestHandler.do_POST(unknown_handler)
    assert unknown_handler.status == 404
    assert REMOTE_ASR_TARGETED_PATH != unknown_handler.path
    assert REMOTE_ASR_TARGETED_DIAGNOSTIC_PATH != unknown_handler.path

    class FailingWorker:
        def __init__(self, error):
            self.error = error

        def process_request(self, body, *, schema_version, sample_rate):
            assert body == b"request-audio-secret"
            assert schema_version == REMOTE_ASR_SCHEMA_VERSION
            assert sample_rate == ASR_AUDIO_SAMPLE_RATE
            raise self.error

    class ErrorHandler:
        path = REMOTE_ASR_PATH

        def __init__(self, error):
            payload = b"request-audio-secret"
            self.headers = {
                "Content-Type": REMOTE_ASR_CONTENT_TYPE,
                "Content-Length": str(len(payload)),
                "X-Stage11-ASR-Schema-Version": str(REMOTE_ASR_SCHEMA_VERSION),
                "X-Stage11-ASR-Sample-Rate": str(ASR_AUDIO_SAMPLE_RATE),
            }
            self.rfile = io.BytesIO(payload)
            self.wfile = io.BytesIO()
            self.server = SimpleNamespace(worker=FailingWorker(error))
            self.status = None
            self.response_headers = []

        def send_response(self, status):
            self.status = status

        def send_header(self, name, value):
            self.response_headers.append((name, value))

        def end_headers(self):
            return None

    for error, expected_status in (
        (ASRLimitError("safe limit reason"), 413),
        (ASRValidationError("safe validation reason"), 400),
        (GPUASRProtocolError("safe protocol reason"), 400),
        (GPUASRRuntimeError("safe runtime reason"), 503),
    ):
        handler = ErrorHandler(error)
        diagnostic = io.StringIO()
        with redirect_stdout(diagnostic):
            Stage11ASRRequestHandler.do_POST(handler)
        log_line = diagnostic.getvalue()
        assert handler.status == expected_status
        assert log_line.startswith("ASR_REQUEST_ERROR ")
        assert "path=" + REMOTE_ASR_PATH in log_line
        assert "status=" + str(expected_status) in log_line
        assert "error_type=" + type(error).__name__ in log_line
        assert "safe " in log_line
        assert "request-audio-secret" not in log_line
        assert "transcript" not in log_line
        assert "DVDMS-117" not in log_line
        assert b"stage11_asr_request_failed" in handler.wfile.getvalue()

    class SuccessWorker:
        def process_request(self, body, *, schema_version, sample_rate):
            assert body == b"success-payload"
            return b'{"success":true}'

    class SuccessHandler:
        path = REMOTE_ASR_PATH

        def __init__(self):
            payload = b"success-payload"
            self.headers = {
                "Content-Type": REMOTE_ASR_CONTENT_TYPE,
                "Content-Length": str(len(payload)),
                "X-Stage11-ASR-Schema-Version": str(REMOTE_ASR_SCHEMA_VERSION),
                "X-Stage11-ASR-Sample-Rate": str(ASR_AUDIO_SAMPLE_RATE),
            }
            self.rfile = io.BytesIO(payload)
            self.wfile = io.BytesIO()
            self.server = SimpleNamespace(worker=SuccessWorker())
            self.status = None

        def send_response(self, status):
            self.status = status

        def send_header(self, _name, _value):
            return None

        def end_headers(self):
            return None

    success_handler = SuccessHandler()
    Stage11ASRRequestHandler.do_POST(success_handler)
    assert success_handler.status == 200
    assert success_handler.wfile.getvalue() == b'{"success":true}'

    class DiagnosticSuccessWorker(SuccessWorker):
        def process_targeted_diagnostic_request(
            self, body, *, schema_version, sample_rate
        ):
            assert body == b"success-payload"
            return b'{"segment_count":0,"segments":[]}'

    diagnostic_success_handler = SuccessHandler()
    diagnostic_success_handler.path = REMOTE_ASR_TARGETED_DIAGNOSTIC_PATH
    diagnostic_success_handler.server = SimpleNamespace(
        worker=DiagnosticSuccessWorker()
    )
    Stage11ASRRequestHandler.do_POST(diagnostic_success_handler)
    assert diagnostic_success_handler.status == 200
    assert diagnostic_success_handler.wfile.getvalue() == (
        b'{"segment_count":0,"segments":[]}'
    )

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
    assert "_log_request_error" in source_text
    assert "_safe_exception_reason" in source_text
    assert "traceback" not in source_text

    print("STAGE11_GPU_ASR_WORKER_SMOKE=PASS")


if __name__ == "__main__":
    main()
