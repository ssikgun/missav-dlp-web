"""Offline fake-model smoke tests for bounded Stage11 Whisper input."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np

from teddy_discovery_asr import (
    ASRSourceSnapshot,
    ASRValidationError,
    ASRWord,
)
from teddy_discovery_asr_audio import (
    ASRAudioChunk,
    ASR_AUDIO_SAMPLE_RATE,
)
from teddy_discovery_asr_whisper import (
    ASRWhisperError,
    FasterWhisperASR,
    PRIMARY_VAD_SPEECH_PAD_MS,
    PRIMARY_VAD_THRESHOLD,
    SECONDARY_VAD_SPEECH_PAD_MS,
    SECONDARY_VAD_THRESHOLD,
    seconds_to_milliseconds,
)
from teddy_discovery_subtitle import validate_canonical_holding


def expect(error_type, function):
    try:
        function()
    except error_type:
        return
    raise AssertionError("expected " + error_type.__name__)


def make_snapshot() -> ASRSourceSnapshot:
    video = validate_canonical_holding(
        {
            "dvd_id": "JUR-750",
            "storage_root": "jav",
            "relative_path": "JUR/JUR-750/JUR-750.mp4",
            "parse_status": "MATCHED",
            "present": 1,
        },
        "JUR-750",
    )
    return ASRSourceSnapshot.from_holding(
        video,
        source_size=123,
        source_mtime_ns=456,
    )


def make_chunk(*, start_ms=1_200_000, end_ms=1_210_000):
    return ASRAudioChunk(
        source_snapshot=make_snapshot(),
        start_ms=start_ms,
        end_ms=end_ms,
        sample_rate=ASR_AUDIO_SAMPLE_RATE,
        samples=np.zeros(
            (end_ms - start_ms) * ASR_AUDIO_SAMPLE_RATE // 1_000,
            dtype=np.float32,
        ),
    )


class FakeModel:
    def __init__(self, raw_segments, *, language="ja", error=None):
        self.raw_segments = raw_segments
        self.language = language
        self.error = error
        self.calls = []

    def transcribe(self, audio, **kwargs):
        self.calls.append((audio, kwargs))
        if self.error is not None:
            raise self.error
        return self.raw_segments, SimpleNamespace(language=self.language)


class SequencedFakeModel:
    def __init__(self, responses, *, language="ja"):
        self.responses = list(responses)
        self.language = language
        self.calls = []

    def transcribe(self, audio, **kwargs):
        self.calls.append((audio, kwargs))
        if not self.responses:
            raise AssertionError("unexpected extra Whisper call")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response, SimpleNamespace(language=self.language)


def raw_segment(start, end, text, words=()):
    return SimpleNamespace(
        start=start,
        end=end,
        text=text,
        words=list(words),
    )


def factory_for(model, calls):
    def factory(model_name, **kwargs):
        calls.append((model_name, kwargs))
        return model

    return factory


def sequenced_adapter(responses):
    model = SequencedFakeModel(responses)
    factory_calls = []
    adapter = FasterWhisperASR(
        model_factory=factory_for(model, factory_calls),
        engine_version="test-engine-vad",
    )
    return adapter, model, factory_calls


def main():
    assert seconds_to_milliseconds(0.0005, field_name="boundary") == 1
    assert seconds_to_milliseconds(1.2345, field_name="boundary") == 1_235

    chunk = make_chunk()
    raw_words = [
        SimpleNamespace(start=0.0005, end=0.3000, word="こん"),
        SimpleNamespace(start=0.3000, end=0.3000, word="に"),
        SimpleNamespace(start=0.3000, end=1.2345, word="ちは"),
    ]
    raw_segments = [
        SimpleNamespace(
            start=0.0005,
            end=1.2345,
            text="こんにちは",
            words=raw_words,
        ),
        SimpleNamespace(
            start=1.2345,
            end=2.0,
            text="次の文",
            words=[],
        ),
    ]
    fake_model = FakeModel(raw_segments)
    factory_calls = []
    adapter = FasterWhisperASR(
        model_factory=factory_for(fake_model, factory_calls),
        engine_version="test-engine-1",
    )

    # Constructor/import must not create a model.
    assert factory_calls == []
    result = adapter.transcribe_chunk(chunk)
    assert len(factory_calls) == 1
    assert factory_calls[0][0] == "medium"
    assert factory_calls[0][1] == {
        "device": "cpu",
        "compute_type": "int8",
        "cpu_threads": 8,
        "num_workers": 1,
        "local_files_only": True,
    }
    assert len(fake_model.calls) == 1
    received_audio, received_kwargs = fake_model.calls[0]
    assert isinstance(received_audio, np.ndarray)
    assert received_audio is chunk.samples
    assert received_audio.dtype == np.dtype("float32")
    assert received_kwargs == {
        "language": "ja",
        "task": "transcribe",
        "word_timestamps": True,
        "vad_filter": True,
        "vad_parameters": {
            "threshold": PRIMARY_VAD_THRESHOLD,
            "speech_pad_ms": PRIMARY_VAD_SPEECH_PAD_MS,
        },
    }
    assert "clip_timestamps" not in received_kwargs
    assert result[0].start_ms == 1_200_001
    assert result[0].end_ms == 1_201_235
    assert result[0].text == "こんにちは"
    assert [word.text for word in result[0].words] == ["こん", "ちは"]
    assert len(result[0].words) == 2
    assert result[0].words[0].start_ms == 1_200_001
    assert result[0].words[1].end_ms == 1_201_235
    assert result[1].start_ms == 1_201_235
    assert result[1].end_ms == 1_202_000

    # A normal primary result does not trigger a secondary pass.  An empty
    # primary result is accepted as confirmed no speech for this chunk, so it
    # also does not trigger a secondary pass.
    quiet_segment = raw_segment(
        6.25,
        7.5,
        "小声",
        words=[SimpleNamespace(start=6.5, end=7.0, word="小声")],
    )
    empty_adapter, empty_model, empty_factory_calls = sequenced_adapter(
        [[]]
    )
    empty_result = empty_adapter.transcribe_chunk(chunk)
    assert len(empty_factory_calls) == 1
    assert empty_result == ()
    assert len(empty_model.calls) == 1
    assert empty_model.calls[0][0] is chunk.samples
    assert empty_model.calls[0][1]["vad_filter"] is True
    assert empty_model.calls[0][1]["vad_parameters"] == {
        "threshold": PRIMARY_VAD_THRESHOLD,
        "speech_pad_ms": PRIMARY_VAD_SPEECH_PAD_MS,
    }

    # The detector is generic: it uses an extreme repeated-short-text shape,
    # not a hard-coded hallucinated token.  A pathological primary invokes
    # one secondary pass; a pathological secondary fails closed.
    repeated_short = [
        raw_segment(index, index + 1, "la")
        for index in range(5)
    ]
    pathological_adapter, pathological_model, _ = sequenced_adapter(
        [repeated_short, [quiet_segment]]
    )
    pathological_fallback = pathological_adapter.transcribe_chunk(chunk)
    assert len(pathological_model.calls) == 2
    assert pathological_model.calls[0][1]["vad_parameters"] == {
        "threshold": PRIMARY_VAD_THRESHOLD,
        "speech_pad_ms": PRIMARY_VAD_SPEECH_PAD_MS,
    }
    assert pathological_model.calls[1][1]["vad_parameters"] == {
        "threshold": SECONDARY_VAD_THRESHOLD,
        "speech_pad_ms": SECONDARY_VAD_SPEECH_PAD_MS,
    }
    assert pathological_fallback[0].text == "小声"

    secondary_pathological_adapter, secondary_pathological_model, _ = (
        sequenced_adapter([repeated_short, repeated_short])
    )
    expect(
        ASRWhisperError,
        lambda: secondary_pathological_adapter.transcribe_chunk(chunk),
    )
    assert len(secondary_pathological_model.calls) == 2

    secondary_empty_adapter, secondary_empty_model, _ = sequenced_adapter(
        [repeated_short, []]
    )
    assert secondary_empty_adapter.transcribe_chunk(chunk) == ()
    assert len(secondary_empty_model.calls) == 2

    # A sparse result is not pathological merely because it is short or has
    # one segment.
    sparse_model = FakeModel([raw_segment(0, 1, "la")])
    sparse_adapter = FasterWhisperASR(
        model_factory=factory_for(sparse_model, []),
    )
    assert len(sparse_adapter.transcribe_chunk(chunk)) == 1
    assert len(sparse_model.calls) == 1

    # Calling the adapter again is an independent request, but one request
    # still has exactly one model invocation and no internal retry loop.
    adapter.transcribe_chunk(chunk)
    assert len(fake_model.calls) == 2

    empty_model = FakeModel([])
    empty_adapter = FasterWhisperASR(
        model_factory=factory_for(empty_model, []),
    )
    assert empty_adapter.transcribe_chunk(chunk) == ()
    assert len(empty_model.calls) == 1

    all_zero_model = FakeModel(
        [
            SimpleNamespace(
                start=2,
                end=3,
                text="ABC",
                words=[
                    SimpleNamespace(start=2.1, end=2.1, word="A"),
                    SimpleNamespace(start=2.2, end=2.2, word="B"),
                ],
            )
        ]
    )
    all_zero_adapter = FasterWhisperASR(
        model_factory=factory_for(all_zero_model, []),
    )
    all_zero_result = all_zero_adapter.transcribe_chunk(chunk)
    assert all_zero_result[0].text == "ABC"
    assert all_zero_result[0].words == ()

    # faster-whisper 1.2.1 can preserve a segment-level boundary while a
    # long first/last word extends beyond it.  The segment remains
    # authoritative and only incompatible optional word metadata is omitted.
    boundary_chunk = make_chunk(start_ms=1_200_000, end_ms=1_220_000)

    def transcribe_boundary_words(raw_words, *, text="경계"):
        model = FakeModel(
            [
                SimpleNamespace(
                    start=10.0,
                    end=12.0,
                    text=text,
                    words=raw_words,
                )
            ]
        )
        boundary_adapter = FasterWhisperASR(
            model_factory=factory_for(model, []),
        )
        return boundary_adapter.transcribe_chunk(boundary_chunk)[0]

    first_outside = transcribe_boundary_words(
        [SimpleNamespace(start=9.0, end=10.5, word="first")],
        text="first boundary",
    )
    assert first_outside.start_ms == 1_210_000
    assert first_outside.end_ms == 1_212_000
    assert first_outside.text == "first boundary"
    assert first_outside.words == ()

    last_outside = transcribe_boundary_words(
        [SimpleNamespace(start=11.5, end=13.0, word="last")],
        text="last boundary",
    )
    assert last_outside.start_ms == 1_210_000
    assert last_outside.end_ms == 1_212_000
    assert last_outside.text == "last boundary"
    assert last_outside.words == ()

    both_outside = transcribe_boundary_words(
        [SimpleNamespace(start=9.0, end=13.0, word="both")],
        text="both boundaries",
    )
    assert both_outside.start_ms == 1_210_000
    assert both_outside.end_ms == 1_212_000
    assert both_outside.text == "both boundaries"
    assert both_outside.words == ()

    mixed_words = transcribe_boundary_words(
        [
            SimpleNamespace(start=9.0, end=10.5, word="drop-first"),
            SimpleNamespace(start=10.5, end=11.0, word="keep-one"),
            SimpleNamespace(start=11.0, end=11.5, word="keep-two"),
            SimpleNamespace(start=11.5, end=13.0, word="drop-last"),
        ],
        text="mixed boundaries",
    )
    assert mixed_words.start_ms == 1_210_000
    assert mixed_words.end_ms == 1_212_000
    assert mixed_words.text == "mixed boundaries"
    assert [word.text for word in mixed_words.words] == [
        "keep-one",
        "keep-two",
    ]
    assert [word.start_ms for word in mixed_words.words] == [
        1_210_500,
        1_211_000,
    ]
    assert [word.end_ms for word in mixed_words.words] == [
        1_211_000,
        1_211_500,
    ]

    all_outside = transcribe_boundary_words(
        [
            SimpleNamespace(start=9.0, end=10.5, word="drop-first"),
            SimpleNamespace(start=11.5, end=13.0, word="drop-last"),
        ],
        text="all omitted",
    )
    assert all_outside.start_ms == 1_210_000
    assert all_outside.end_ms == 1_212_000
    assert all_outside.text == "all omitted"
    assert all_outside.words == ()

    zero_outside = transcribe_boundary_words(
        [
            SimpleNamespace(start=9.0, end=9.0, word="zero-outside"),
            SimpleNamespace(start=10.5, end=10.5, word="zero-inside"),
        ],
        text="zero duration",
    )
    assert zero_outside.start_ms == 1_210_000
    assert zero_outside.end_ms == 1_212_000
    assert zero_outside.text == "zero duration"
    assert zero_outside.words == ()

    negative_word_model = FakeModel(
        [
            SimpleNamespace(
                start=0,
                end=1,
                text="negative",
                words=[SimpleNamespace(start=0.8, end=0.7, word="x")],
            )
        ]
    )
    expect(
        ASRValidationError,
        lambda: FasterWhisperASR(
            model_factory=factory_for(negative_word_model, []),
        ).transcribe_chunk(chunk),
    )

    collapsed_word_model = FakeModel(
        [
            SimpleNamespace(
                start=0,
                end=1,
                text="collapsed",
                words=[SimpleNamespace(start=0.0001, end=0.0002, word="x")],
            )
        ]
    )
    expect(
        ASRValidationError,
        lambda: FasterWhisperASR(
            model_factory=factory_for(collapsed_word_model, []),
        ).transcribe_chunk(chunk),
    )

    nonfinite_word_model = FakeModel(
        [
            SimpleNamespace(
                start=0,
                end=1,
                text="nonfinite",
                words=[SimpleNamespace(start=float("nan"), end=1, word="x")],
            )
        ]
    )
    expect(
        ASRValidationError,
        lambda: FasterWhisperASR(
            model_factory=factory_for(nonfinite_word_model, []),
        ).transcribe_chunk(chunk),
    )

    missing_word_timestamp_model = FakeModel(
        [
            SimpleNamespace(
                start=0,
                end=1,
                text="missing",
                words=[SimpleNamespace(start=0, word="x")],
            )
        ]
    )
    expect(
        ASRValidationError,
        lambda: FasterWhisperASR(
            model_factory=factory_for(missing_word_timestamp_model, []),
        ).transcribe_chunk(chunk),
    )

    outside_word_model = FakeModel(
        [
            SimpleNamespace(
                start=0,
                end=1,
                text="outside",
                words=[SimpleNamespace(start=0.5, end=1.1, word="x")],
            )
        ]
    )
    outside_adapter = FasterWhisperASR(
        model_factory=factory_for(outside_word_model, []),
    )
    outside_result = outside_adapter.transcribe_chunk(chunk)
    assert outside_result[0].start_ms == 1_200_000
    assert outside_result[0].end_ms == 1_201_000
    assert outside_result[0].text == "outside"
    assert outside_result[0].words == ()

    decreasing_word_model = FakeModel(
        [
            SimpleNamespace(
                start=0,
                end=1,
                text="order",
                words=[
                    SimpleNamespace(start=0.8, end=0.9, word="a"),
                    SimpleNamespace(start=0.7, end=0.75, word="b"),
                ],
            )
        ]
    )
    expect(
        ASRValidationError,
        lambda: FasterWhisperASR(
            model_factory=factory_for(decreasing_word_model, []),
        ).transcribe_chunk(chunk),
    )

    # ASRWord itself remains strict; zero-duration handling belongs only to
    # the upstream faster-whisper conversion boundary.
    expect(
        ASRValidationError,
        lambda: ASRWord(start_ms=10, end_ms=10, text="x"),
    )

    malformed_model = FakeModel(
        [SimpleNamespace(start=2, end=1, text="역전", words=[])],
    )
    malformed_adapter = FasterWhisperASR(
        model_factory=factory_for(malformed_model, []),
    )
    expect(
        ASRValidationError,
        lambda: malformed_adapter.transcribe_chunk(chunk),
    )
    assert len(malformed_model.calls) == 1

    outside_model = FakeModel(
        [SimpleNamespace(start=0, end=11, text="범위 밖", words=[])],
    )
    outside_adapter = FasterWhisperASR(
        model_factory=factory_for(outside_model, []),
    )
    expect(
        ASRValidationError,
        lambda: outside_adapter.transcribe_chunk(chunk),
    )

    wrong_language_model = FakeModel(
        [SimpleNamespace(start=0, end=1, text="text", words=[])],
        language="en",
    )
    wrong_language_adapter = FasterWhisperASR(
        model_factory=factory_for(wrong_language_model, []),
    )
    expect(
        ASRValidationError,
        lambda: wrong_language_adapter.transcribe_chunk(chunk),
    )

    failing_model = FakeModel([], error=RuntimeError("synthetic failure"))
    failing_adapter = FasterWhisperASR(
        model_factory=factory_for(failing_model, []),
    )
    expect(
        ASRWhisperError,
        lambda: failing_adapter.transcribe_chunk(chunk),
    )
    assert len(failing_model.calls) == 1

    expect(
        ASRValidationError,
        lambda: adapter.transcribe_chunk("/tmp/arbitrary.mp4"),
    )

    source_text = Path(__file__).with_name(
        "teddy_discovery_asr_whisper.py"
    ).read_text(encoding="utf-8").lower()
    assert "publish" not in source_text
    assert "e4b" not in source_text
    assert "translate" not in source_text
    assert "source.local_path" not in source_text
    assert "clip_timestamps" not in source_text
    assert "model.transcribe(\n                chunk.samples" in source_text

    module_source = Path(__file__).with_name(
        "teddy_discovery_asr_whisper.py"
    ).read_text(encoding="utf-8")
    assert "from faster_whisper import WhisperModel" in module_source
    assert "def _default_model_factory" in module_source
    assert module_source.index("def _default_model_factory") < module_source.index(
        "from faster_whisper import WhisperModel"
    )

    print("STAGE11_ASR_WHISPER_SMOKE=PASS")


if __name__ == "__main__":
    main()
