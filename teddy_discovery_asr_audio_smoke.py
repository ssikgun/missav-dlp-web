"""Offline PyAV/NumPy-injected smoke tests for bounded Stage11 audio."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from fractions import Fraction
import tempfile

import numpy as np

from teddy_discovery_asr import ASRError, ASRSourceSnapshot
from teddy_discovery_asr_source import ASRLocalMediaSource, ASRSourceError
from teddy_discovery_asr_audio import (
    ASRAudioChunk,
    ASRAudioError,
    ASRAudioLimitError,
    ASRAudioValidationError,
    ASR_AUDIO_SAMPLE_RATE,
    MAX_ASR_AUDIO_CHUNK_SECONDS,
    MAX_ASR_AUDIO_SAMPLES,
    _sample_index_to_ms,
    _ChunkAccumulator,
    _frame_to_samples,
    _timestamp_to_sample_index,
    _validate_request_range,
    _validate_sample_count,
    iter_audio_chunks,
)
from teddy_discovery_subtitle import validate_canonical_holding


def expect(error_type, function):
    try:
        function()
    except error_type:
        return
    raise AssertionError("expected " + error_type.__name__)


def snapshot() -> ASRSourceSnapshot:
    holding = validate_canonical_holding(
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
        holding,
        source_size=123,
        source_mtime_ns=456,
    )


def make_source(root: str, *, filename: str = ".media.mp4"):
    owned = Path(root) / filename.replace(".mp4", "-owned")
    owned.mkdir()
    path = owned / filename
    path.write_bytes(b"synthetic media")
    return ASRLocalMediaSource(
        local_path=str(path),
        source_snapshot=snapshot(),
        temp_directory=str(owned),
    )


class FakeFrame:
    def __init__(
        self,
        samples,
        *,
        pts=0,
        time_base=Fraction(1, ASR_AUDIO_SAMPLE_RATE),
        sample_rate=ASR_AUDIO_SAMPLE_RATE,
        source_samples=None,
    ):
        self.array = samples
        self.samples = int(
            samples.size if source_samples is None else source_samples
        )
        self.pts = pts
        self.time_base = time_base
        self.sample_rate = sample_rate

    def to_ndarray(self):
        return self.array


class FakeContainer:
    def __init__(
        self,
        frames,
        *,
        audio_streams=None,
        lazy_error=None,
        lazy_error_after=None,
    ):
        self.frames = tuple(frames)
        self.streams = SimpleNamespace(
            audio=[] if audio_streams is None else audio_streams
        )
        self.lazy_error = lazy_error
        self.lazy_error_after = lazy_error_after
        self.decode_calls = []
        self.close_calls = 0

    def decode(self, *args, **kwargs):
        self.decode_calls.append((args, kwargs))

        def lazy_frames():
            for index, frame in enumerate(self.frames):
                if (
                    self.lazy_error is not None
                    and self.lazy_error_after == index
                ):
                    raise self.lazy_error
                yield frame
            if (
                self.lazy_error is not None
                and self.lazy_error_after == len(self.frames)
            ):
                raise self.lazy_error

        return lazy_frames()

    def close(self):
        self.close_calls += 1


class FakeResampler:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []
        self.__class__.instances.append(self)

    def resample(self, frame):
        self.calls.append(frame)
        if frame is None:
            return []
        return [FakeOutputFrame(_as_s16(frame.to_ndarray()))]


def _as_s16(samples):
    return np.rint(np.asarray(samples, dtype=np.float32) * 32768.0).astype(
        np.int16
    )


class FakeOutputFrame:
    def __init__(self, samples, *, format_name="s16", layout_name="mono"):
        self.samples = samples
        self.format = SimpleNamespace(name=format_name)
        self.layout = SimpleNamespace(name=layout_name)

    def to_ndarray(self):
        return self.samples


class DelayedResampler:
    """Synthetic 16-sample PyAV delay with a real flush tail."""

    instances = []
    delay_samples = 16

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []
        self.output_sizes = []
        self.pending = None
        self.__class__.instances.append(self)

    def resample(self, frame):
        self.calls.append(frame)
        if frame is None:
            if self.pending is None:
                self.output_sizes.append(0)
                return []
            output = FakeOutputFrame(_as_s16(self.pending))
            self.output_sizes.append(int(self.pending.size))
            self.pending = None
            return [output]

        incoming = np.asarray(frame.to_ndarray(), dtype=np.float32)
        delay = self.delay_samples
        if self.pending is None:
            if incoming.size <= delay:
                self.pending = incoming.copy()
                self.output_sizes.append(0)
                return []
            output = incoming[:-delay]
            self.pending = incoming[-delay:].copy()
        else:
            output = np.concatenate((self.pending, incoming[:-delay]))
            self.pending = incoming[-delay:].copy()
        self.output_sizes.append(int(output.size))
        return [FakeOutputFrame(_as_s16(output))] if output.size else []


class BoundaryResampler:
    """First segment is delayed; a fresh post-gap instance is immediate."""

    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []
        self.delayed = not self.__class__.instances
        self.delegate = DelayedResampler(**kwargs) if self.delayed else None
        self.__class__.instances.append(self)

    def resample(self, frame):
        if self.delayed:
            # Keep the test's public instance list focused on the actual
            # boundary resamplers, while delegating the delay mechanics.
            self.delegate.calls = self.calls
            return self.delegate.resample(frame)
        self.calls.append(frame)
        if frame is None:
            return []
        return [
            FakeOutputFrame(_as_s16(frame.to_ndarray()))
        ]


class FakeAV:
    def __init__(self, container, *, resampler_class=FakeResampler):
        self.container = container
        self.open_calls = []
        self.audio = SimpleNamespace(
            resampler=SimpleNamespace(AudioResampler=resampler_class)
        )

    def open(self, path, *, mode):
        self.open_calls.append((path, mode))
        return self.container


class RecordingNumpy:
    def __init__(self):
        self.empty_sizes = []

    def empty(self, size, *, dtype):
        self.empty_sizes.append(size)
        return np.empty(size, dtype=dtype)

    @staticmethod
    def dtype(value):
        return np.dtype(value)


def valid_chunk():
    return ASRAudioChunk(
        source_snapshot=snapshot(),
        start_ms=600_000,
        end_ms=601_000,
        sample_rate=ASR_AUDIO_SAMPLE_RATE,
        samples=np.zeros(16_000, dtype=np.float32),
    )


def main():
    assert ASR_AUDIO_SAMPLE_RATE == 16_000
    assert MAX_ASR_AUDIO_CHUNK_SECONDS == 600
    assert MAX_ASR_AUDIO_SAMPLES == 9_600_000
    assert _sample_index_to_ms(9_600_000) == 600_000

    chunk = valid_chunk()
    assert chunk.source_snapshot == snapshot()
    assert chunk.start_ms == 600_000
    assert chunk.end_ms == 601_000
    assert chunk.samples.dtype == np.dtype("float32")
    assert chunk.samples.ndim == 1
    assert not chunk.samples.flags.writeable

    for sample_rate in (8_000, 16_000.0):
        expect(
            ASRAudioValidationError,
            lambda sample_rate=sample_rate: ASRAudioChunk(
                snapshot(), 0, 1_000, sample_rate, np.zeros(1, np.float32)
            ),
        )
    expect(
        ASRAudioValidationError,
        lambda: ASRAudioChunk(
            snapshot(), 0, 1_000, 16_000, np.zeros(1, np.float64)
        ),
    )
    expect(
        ASRAudioValidationError,
        lambda: ASRAudioChunk(
            snapshot(), 0, 1_000, 16_000, np.zeros(1, np.int16)
        ),
    )
    expect(
        ASRAudioValidationError,
        lambda: ASRAudioChunk(
            snapshot(), 0, 1_000, 16_000, np.zeros((1, 1), np.float32)
        ),
    )
    expect(
        ASRAudioValidationError,
        lambda: ASRAudioChunk(
            snapshot(), 0, 1_000, 16_000, np.zeros(0, np.float32)
        ),
    )
    for value in (np.nan, np.inf, -np.inf):
        expect(
            ASRAudioValidationError,
            lambda value=value: ASRAudioChunk(
                snapshot(), 0, 1_000, 16_000, np.array([value], np.float32)
            ),
        )
    expect(
        ASRAudioValidationError,
        lambda: ASRAudioChunk(
            snapshot(), 0, 1_000, 16_000, np.array([1.01], np.float32)
        ),
    )
    expect(
        ASRAudioValidationError,
        lambda: ASRAudioChunk(
            snapshot(), 1_000, 1_000, 16_000, np.zeros(1, np.float32)
        ),
    )
    expect(
        ASRAudioLimitError,
        lambda: ASRAudioChunk(
            snapshot(),
            0,
            MAX_ASR_AUDIO_CHUNK_SECONDS * 1_000 + 1,
            16_000,
            np.zeros(1, np.float32),
        ),
    )
    expect(
        ASRAudioValidationError,
        lambda: ASRAudioChunk(
            object(), 0, 1_000, 16_000, np.zeros(1, np.float32)
        ),
    )
    expect(
        ASRAudioLimitError,
        lambda: _validate_sample_count(MAX_ASR_AUDIO_SAMPLES + 1),
    )

    raw_s16 = np.array(
        [-32_768, -16_384, -1, 0, 1, 16_384, 32_767],
        dtype=np.int16,
    )
    normalized = _frame_to_samples(
        FakeOutputFrame(raw_s16),
        np,
    )
    expected_normalized = raw_s16.astype(np.float32) / 32768.0
    assert np.array_equal(normalized, expected_normalized)
    assert normalized.dtype == np.dtype("float32")
    assert normalized.ndim == 1
    assert normalized.size == raw_s16.size
    assert normalized[0] == np.float32(-1.0)
    assert normalized[-1] == np.float32(32_767 / 32_768)
    assert normalized[3] == np.float32(0.0)
    assert bool(np.isfinite(normalized).all())

    # PyAV's mono ndarray is commonly shaped (1, samples); it must flatten
    # only that explicitly validated mono channel.
    flattened = _frame_to_samples(
        FakeOutputFrame(raw_s16.reshape(1, -1)),
        np,
    )
    assert np.array_equal(flattened, expected_normalized)
    expect(
        ASRAudioValidationError,
        lambda: _frame_to_samples(
            FakeOutputFrame(raw_s16, format_name="flt"),
            np,
        ),
    )
    expect(
        ASRAudioValidationError,
        lambda: _frame_to_samples(
            FakeOutputFrame(raw_s16.astype(np.int32)),
            np,
        ),
    )
    expect(
        ASRAudioValidationError,
        lambda: _frame_to_samples(
            FakeOutputFrame(raw_s16.reshape(1, 1, -1)),
            np,
        ),
    )
    expect(
        ASRAudioValidationError,
        lambda: _frame_to_samples(
            FakeOutputFrame(raw_s16, layout_name="stereo"),
            np,
        ),
    )

    with tempfile.TemporaryDirectory() as temp_root:
        source = make_source(temp_root)
        frames = [
            FakeFrame(
                np.linspace(-0.25, 0.25, 16_000, dtype=np.float32),
                pts=0,
            ),
            FakeFrame(
                np.zeros(8_000, dtype=np.float32),
                pts=16_000,
            ),
        ]
        selected_audio_stream = SimpleNamespace(index=1)
        container = FakeContainer(
            frames,
            audio_streams=[selected_audio_stream],
        )
        FakeResampler.instances.clear()
        fake_av = FakeAV(container)
        chunks = tuple(
            iter_audio_chunks(
                source,
                chunk_seconds=1,
                av_module=fake_av,
                numpy_module=np,
            )
        )
        assert len(chunks) == 2
        assert chunks[0].start_ms == 0
        assert chunks[0].end_ms == 1_000
        assert chunks[1].start_ms == 1_000
        assert chunks[1].end_ms == 1_500
        assert chunks[1].samples.size == 8_000
        assert len(fake_av.open_calls) == 1
        assert fake_av.open_calls[0][0] == source.local_path
        assert fake_av.open_calls[0][1] == "r"
        assert len(container.decode_calls) == 1
        assert container.decode_calls[0][0] == (selected_audio_stream,)
        assert container.decode_calls[0][0][0] is selected_audio_stream
        assert container.decode_calls[0][1] == {}
        assert container.close_calls == 1
        assert FakeResampler.instances[0].kwargs == {
            "format": "s16",
            "layout": "mono",
            "rate": 16_000,
        }
        assert len(FakeResampler.instances[0].calls) == 3
        assert chunks[0].samples[0] == np.float32(-0.25)
        assert chunks[1].samples.size <= MAX_ASR_AUDIO_SAMPLES

        def run_frames(
            frames,
            *,
            chunk_seconds=1,
            start_seconds=0,
            end_seconds=None,
            audio_index=6,
            resampler_class=FakeResampler,
        ):
            stream = SimpleNamespace(index=audio_index)
            container = FakeContainer(
                frames,
                audio_streams=[stream],
            )
            output = tuple(
                iter_audio_chunks(
                    source,
                    chunk_seconds=chunk_seconds,
                    start_seconds=start_seconds,
                    end_seconds=end_seconds,
                    av_module=FakeAV(
                        container,
                        resampler_class=resampler_class,
                    ),
                    numpy_module=np,
                )
            )
            return output, container, stream

        other_audio_stream = SimpleNamespace(index=19)
        other_index_container = FakeContainer(
            [FakeFrame(np.zeros(1, dtype=np.float32), pts=0)],
            audio_streams=[other_audio_stream],
        )
        tuple(
            iter_audio_chunks(
                source,
                chunk_seconds=1,
                av_module=FakeAV(other_index_container),
                numpy_module=np,
            )
        )
        assert other_index_container.decode_calls[0][0] == (
            other_audio_stream,
        )
        assert other_index_container.decode_calls[0][1] == {}

        before = source.local_path and Path(source.local_path).read_bytes()
        requested_range_container = FakeContainer(
            [
                FakeFrame(
                    np.zeros(32_000, dtype=np.float32),
                    pts=0,
                )
            ],
            audio_streams=[SimpleNamespace(index=2)],
        )
        requested_range = tuple(
            iter_audio_chunks(
                source,
                chunk_seconds=600,
                start_seconds=0.5,
                end_seconds=1.25,
                av_module=FakeAV(requested_range_container),
                numpy_module=np,
            )
        )
        assert len(requested_range) == 1
        assert requested_range[0].start_ms == 500
        assert requested_range[0].end_ms == 1_250
        assert requested_range[0].samples.size == 12_000

        canary_container = FakeContainer(
            [
                FakeFrame(
                    np.zeros(60 * ASR_AUDIO_SAMPLE_RATE, dtype=np.float32),
                    pts=600 * ASR_AUDIO_SAMPLE_RATE,
                )
            ],
            audio_streams=[SimpleNamespace(index=3)],
        )
        canary_av = FakeAV(canary_container)
        canary = tuple(
            iter_audio_chunks(
                source,
                chunk_seconds=600,
                start_seconds=600,
                end_seconds=660,
                av_module=canary_av,
                numpy_module=np,
            )
        )
        assert len(canary) == 1
        assert canary[0].start_ms == 600_000
        assert canary[0].end_ms == 660_000
        assert canary[0].samples.size == 60 * ASR_AUDIO_SAMPLE_RATE
        assert Path(source.local_path).read_bytes() == before

        nonzero_origin_container = FakeContainer(
            [
                FakeFrame(
                    np.zeros(16_000, dtype=np.float32),
                    pts=2_000,
                )
            ],
            audio_streams=[SimpleNamespace(index=4)],
        )
        nonzero_origin = tuple(
            iter_audio_chunks(
                source,
                chunk_seconds=1,
                av_module=FakeAV(nonzero_origin_container),
                numpy_module=np,
            )
        )
        assert nonzero_origin[0].start_ms == 125

        rounded_container = FakeContainer(
            [
                FakeFrame(
                    np.zeros(5_333, dtype=np.float32),
                    pts=0,
                    time_base=Fraction(1, 10_000),
                    sample_rate=3,
                    source_samples=1,
                ),
                FakeFrame(
                    np.zeros(5_334, dtype=np.float32),
                    pts=3_333,
                    time_base=Fraction(1, 10_000),
                    sample_rate=3,
                    source_samples=1,
                ),
            ],
            audio_streams=[SimpleNamespace(index=5)],
        )
        tuple(
            iter_audio_chunks(
                source,
                chunk_seconds=1,
                av_module=FakeAV(rounded_container),
                numpy_module=np,
            )
        )

        continuous, _, _ = run_frames(
            [
                FakeFrame(np.full(16_000, 0.25, np.float32), pts=0),
                FakeFrame(np.full(16_000, -0.25, np.float32), pts=16_000),
            ],
            chunk_seconds=2,
        )
        assert len(continuous) == 1
        assert not np.any(continuous[0].samples == np.float32(0.0))
        assert np.all(continuous[0].samples[:16_000] == np.float32(0.25))
        assert np.all(continuous[0].samples[16_000:] == np.float32(-0.25))

        within_tolerance, _, _ = run_frames(
            [
                FakeFrame(np.full(16_000, 0.375, np.float32), pts=0),
                FakeFrame(np.full(16_000, -0.375, np.float32), pts=16_001),
            ],
            chunk_seconds=2,
        )
        assert len(within_tolerance) == 1
        assert not np.any(within_tolerance[0].samples == np.float32(0.0))

        # Model the measured PyAV resampler latency: the first emission is
        # short by 16 samples, ordinary emissions are 341/342-ish, and the
        # final flush emits the pending tail.  Source PTS continuity, rather
        # than the temporary emission lag, determines that there is no gap.
        DelayedResampler.instances.clear()
        delayed_frames = [
            FakeFrame(np.full(341, 0.125, np.float32), pts=0),
            FakeFrame(np.full(342, 0.25, np.float32), pts=341),
            FakeFrame(np.full(341, 0.375, np.float32), pts=683),
        ]
        delayed_continuous, _, _ = run_frames(
            delayed_frames,
            chunk_seconds=2,
            resampler_class=DelayedResampler,
        )
        assert len(delayed_continuous) == 1
        delayed_samples = delayed_continuous[0].samples
        assert delayed_samples.size == 1_024
        assert np.all(delayed_samples[:341] == np.float32(0.125))
        assert np.all(delayed_samples[341:683] == np.float32(0.25))
        assert np.all(delayed_samples[683:] == np.float32(0.375))
        delayed_resampler = DelayedResampler.instances[0]
        assert delayed_resampler.output_sizes == [325, 342, 341, 16]
        assert delayed_resampler.calls[-1] is None

        # A bounded end still flushes delayed real audio and clips the output
        # at the absolute requested media boundary.
        delayed_end_frame = FakeFrame(
            np.concatenate(
                (
                    np.full(84, 0.25, np.float32),
                    np.full(16, 0.5, np.float32),
                )
            ),
            pts=0,
        )
        DelayedResampler.instances.clear()
        delayed_end, _, _ = run_frames(
            [delayed_end_frame],
            chunk_seconds=600,
            end_seconds=90 / ASR_AUDIO_SAMPLE_RATE,
            resampler_class=DelayedResampler,
        )
        assert len(delayed_end) == 1
        assert delayed_end[0].samples.size == 90
        assert np.all(delayed_end[0].samples[:84] == np.float32(0.25))
        assert np.all(delayed_end[0].samples[84:] == np.float32(0.5))

        delayed_start, _, _ = run_frames(
            [delayed_end_frame],
            chunk_seconds=600,
            start_seconds=50 / ASR_AUDIO_SAMPLE_RATE,
            end_seconds=90 / ASR_AUDIO_SAMPLE_RATE,
            resampler_class=DelayedResampler,
        )
        assert len(delayed_start) == 1
        assert delayed_start[0].samples.size == 40
        assert np.all(delayed_start[0].samples[:34] == np.float32(0.25))
        assert np.all(delayed_start[0].samples[34:] == np.float32(0.5))

        # A real positive gap flushes the old resampler before inserting
        # silence, then creates a fresh resampler for the post-gap frame.
        BoundaryResampler.instances.clear()
        boundary_frames = [
            FakeFrame(
                np.concatenate(
                    (
                        np.full(16, 0.125, np.float32),
                        np.full(16, 0.25, np.float32),
                    )
                ),
                pts=0,
                source_samples=32,
            ),
            FakeFrame(
                np.full(16, 0.375, np.float32),
                pts=49,
            ),
        ]
        boundary_result, _, _ = run_frames(
            boundary_frames,
            chunk_seconds=1,
            resampler_class=BoundaryResampler,
        )
        assert len(boundary_result) == 1
        boundary_samples = boundary_result[0].samples
        assert boundary_samples.size == 65
        assert np.all(boundary_samples[:16] == np.float32(0.125))
        assert np.all(boundary_samples[16:32] == np.float32(0.25))
        assert np.all(boundary_samples[32:49] == np.float32(0.0))
        assert np.all(boundary_samples[49:] == np.float32(0.375))
        assert len(BoundaryResampler.instances) == 2
        assert BoundaryResampler.instances[0].calls == [
            boundary_frames[0],
            None,
        ]
        assert BoundaryResampler.instances[1].calls == [
            boundary_frames[1],
            None,
        ]

        one_second_gap, _, _ = run_frames(
            [
                FakeFrame(np.full(16_000, 0.25, np.float32), pts=0),
                FakeFrame(np.full(16_000, -0.25, np.float32), pts=32_000),
            ],
            chunk_seconds=10,
        )
        assert len(one_second_gap) == 1
        gap_samples = one_second_gap[0].samples
        assert np.all(gap_samples[:16_000] == np.float32(0.25))
        assert np.all(gap_samples[16_000:32_000] == np.float32(0.0))
        assert np.all(gap_samples[32_000:] == np.float32(-0.25))

        # AAC-like 48 kHz frame timing with the observed +74.666667 ms gap.
        jur_gap, _, _ = run_frames(
            [
                FakeFrame(
                    np.full(341, 0.25, np.float32),
                    pts=0,
                    time_base=Fraction(1, 48_000),
                    sample_rate=48_000,
                    source_samples=1_024,
                ),
                FakeFrame(
                    np.full(341, -0.25, np.float32),
                    pts=4_608,
                    time_base=Fraction(1, 48_000),
                    sample_rate=48_000,
                    source_samples=1_024,
                ),
            ],
            chunk_seconds=1,
        )
        assert len(jur_gap) == 1
        jur_samples = jur_gap[0].samples
        assert np.all(jur_samples[:341] == np.float32(0.25))
        assert np.all(jur_samples[341:1_536] == np.float32(0.0))
        assert np.all(jur_samples[1_536:] == np.float32(-0.25))
        assert jur_gap[0].start_ms == 0
        assert jur_gap[0].end_ms == _sample_index_to_ms(jur_samples.size)

        spanning_gap, _, _ = run_frames(
            [
                FakeFrame(np.full(12_000, 0.5, np.float32), pts=0),
                FakeFrame(np.full(12_000, -0.5, np.float32), pts=28_000),
            ],
            chunk_seconds=1,
        )
        assert len(spanning_gap) == 3
        assert np.all(spanning_gap[0].samples[:12_000] == np.float32(0.5))
        assert np.all(spanning_gap[0].samples[12_000:] == np.float32(0.0))
        assert np.all(spanning_gap[1].samples[:12_000] == np.float32(0.0))
        assert np.all(spanning_gap[1].samples[12_000:] == np.float32(-0.5))
        assert np.all(spanning_gap[2].samples == np.float32(-0.5))

        gap_start_inside, _, _ = run_frames(
            [
                FakeFrame(np.full(16_000, 0.5, np.float32), pts=0),
                FakeFrame(np.full(16_000, -0.5, np.float32), pts=32_000),
            ],
            chunk_seconds=600,
            start_seconds=1.5,
            end_seconds=2.5,
        )
        assert len(gap_start_inside) == 1
        assert gap_start_inside[0].start_ms == 1_500
        assert gap_start_inside[0].end_ms == 2_500
        assert np.all(gap_start_inside[0].samples[:8_000] == np.float32(0.0))
        assert np.all(gap_start_inside[0].samples[8_000:] == np.float32(-0.5))

        gap_end_inside, _, _ = run_frames(
            [
                FakeFrame(np.full(16_000, 0.5, np.float32), pts=0),
                FakeFrame(np.full(16_000, -0.5, np.float32), pts=32_000),
            ],
            chunk_seconds=600,
            start_seconds=0.5,
            end_seconds=1.5,
        )
        assert len(gap_end_inside) == 1
        assert gap_end_inside[0].start_ms == 500
        assert gap_end_inside[0].end_ms == 1_500
        assert np.all(gap_end_inside[0].samples[:8_000] == np.float32(0.5))
        assert np.all(gap_end_inside[0].samples[8_000:] == np.float32(0.0))

        gap_only, _, _ = run_frames(
            [
                FakeFrame(np.full(16_000, 0.5, np.float32), pts=0),
                FakeFrame(np.full(16_000, -0.5, np.float32), pts=32_000),
            ],
            chunk_seconds=600,
            start_seconds=1.25,
            end_seconds=1.75,
        )
        assert len(gap_only) == 1
        assert gap_only[0].start_ms == 1_250
        assert gap_only[0].end_ms == 1_750
        assert gap_only[0].samples.size == 8_000
        assert np.all(gap_only[0].samples == np.float32(0.0))

        recording_numpy = RecordingNumpy()
        accumulator = _ChunkAccumulator(
            numpy=recording_numpy,
            source_snapshot=snapshot(),
            start_sample=0,
            chunk_samples=16_000,
        )
        emitted_silence = 0
        for silent_chunk in accumulator.add_silence(
            MAX_ASR_AUDIO_SAMPLES + 123
        ):
            emitted_silence += 1
            assert accumulator.buffer is None
            assert silent_chunk.samples.size <= 16_000
            assert silent_chunk.samples.dtype == np.dtype("float32")
            assert np.all(silent_chunk.samples == np.float32(0.0))
            del silent_chunk
        for silent_chunk in accumulator.finish():
            emitted_silence += 1
            assert silent_chunk.samples.size == 123
            assert np.all(silent_chunk.samples == np.float32(0.0))
            del silent_chunk
        assert emitted_silence == 601
        assert max(recording_numpy.empty_sizes) == 16_000

        lazy_stream = SimpleNamespace(index=1)
        lazy_first_container = FakeContainer(
            [],
            audio_streams=[lazy_stream],
            lazy_error=IndexError("lazy synthetic decode failure"),
            lazy_error_after=0,
        )
        try:
            tuple(
                iter_audio_chunks(
                    source,
                    chunk_seconds=1,
                    av_module=FakeAV(lazy_first_container),
                    numpy_module=np,
                )
            )
        except ASRAudioError as error:
            assert type(error) is ASRAudioError
        else:
            raise AssertionError("lazy first decode error was not wrapped")

        lazy_after_container = FakeContainer(
            [FakeFrame(np.zeros(1, np.float32), pts=0)],
            audio_streams=[SimpleNamespace(index=1)],
            lazy_error=ValueError("lazy synthetic post-frame failure"),
            lazy_error_after=1,
        )
        try:
            tuple(
                iter_audio_chunks(
                    source,
                    chunk_seconds=1,
                    av_module=FakeAV(lazy_after_container),
                    numpy_module=np,
                )
            )
        except ASRAudioError as error:
            assert type(error) is ASRAudioError
        else:
            raise AssertionError("lazy post-frame error was not wrapped")

        expect(
            ASRAudioValidationError,
            lambda: run_frames(
                [
                    FakeFrame(np.zeros(1, np.float32), pts=1_000),
                    FakeFrame(np.zeros(1, np.float32), pts=500),
                ]
            )[0],
        )
        expect(
            ASRAudioValidationError,
            lambda: run_frames(
                [
                    FakeFrame(np.zeros(16_000, np.float32), pts=0),
                    FakeFrame(np.zeros(1, np.float32), pts=15_000),
                ]
            )[0],
        )
        expect(
            ASRAudioValidationError,
            lambda: run_frames(
                [FakeFrame(np.zeros(1, np.float32), pts=None)]
            )[0],
        )
        expect(
            ASRAudioValidationError,
            lambda: run_frames(
                [FakeFrame(np.zeros(1, np.float32), time_base=0)]
            )[0],
        )
        expect(
            ASRAudioValidationError,
            lambda: run_frames(
                [FakeFrame(np.zeros(1, np.float32), pts=float("nan"))]
            )[0],
        )
        assert _timestamp_to_sample_index(Fraction(1, 8)) == 2_000

        no_audio = FakeAV(FakeContainer([], audio_streams=[]))
        expect(
            ASRAudioValidationError,
            lambda: tuple(
                iter_audio_chunks(
                    source,
                    chunk_seconds=1,
                    av_module=no_audio,
                    numpy_module=np,
                )
            ),
        )

        inactive = make_source(temp_root, filename="inactive.mp4")
        inactive.cleanup()
        expect(
            ASRError,
            lambda: iter_audio_chunks(
                inactive,
                chunk_seconds=1,
                av_module=fake_av,
                numpy_module=np,
            ),
        )

        directory_source = make_source(temp_root, filename="directory.mp4")
        Path(directory_source.local_path).unlink()
        Path(directory_source.local_path).mkdir()
        expect(
            ASRAudioValidationError,
            lambda: iter_audio_chunks(
                directory_source,
                chunk_seconds=1,
                av_module=fake_av,
                numpy_module=np,
            ),
        )

        expect(
            ASRAudioValidationError,
            lambda: iter_audio_chunks(
                "/arbitrary/path.mp4",
                chunk_seconds=1,
                av_module=fake_av,
                numpy_module=np,
            ),
        )

    expect(
        ASRAudioLimitError,
        lambda: _validate_request_range(
            chunk_seconds=MAX_ASR_AUDIO_CHUNK_SECONDS + 1,
            start_seconds=0,
            end_seconds=None,
        ),
    )

    source_text = Path(__file__).with_name("teddy_discovery_asr_audio.py").read_text(
        encoding="utf-8"
    )
    assert "os.walk" not in source_text
    assert "rglob" not in source_text
    assert "subprocess" not in source_text
    assert "ffmpeg" not in source_text.lower()
    assert "np.concatenate" not in source_text
    assert "all_audio" not in source_text
    assert "all_chunks" not in source_text
    assert ".seek(" not in source_text
    assert "ffmpeg" not in source_text.lower()
    assert "np.clip" not in source_text
    assert ".clip(" not in source_text
    assert "peak normalization" not in source_text.lower()
    assert "audio=audio_stream.index" not in source_text
    assert "os.unlink" not in source_text
    assert "os.remove" not in source_text

    print("STAGE11_ASR_AUDIO_SMOKE=PASS")


if __name__ == "__main__":
    main()
