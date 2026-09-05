"""Offline smoke tests for the full-title Stage11 ASR transcriber."""

from __future__ import annotations

from pathlib import Path
import tempfile

import teddy_discovery_asr_transcriber as transcriber_module
from teddy_discovery_asr import (
    ASRError,
    ASRLimitError,
    ASRResult,
    ASRSegment,
    ASRSourceSnapshot,
)
from teddy_discovery_asr_audio import ASRAudioChunk, ASRAudioError
from teddy_discovery_asr_source import (
    ASRLocalMediaSource,
)
from teddy_discovery_asr_whisper import ASRWhisperError, FasterWhisperASR
from teddy_discovery_subtitle import CanonicalVideoHolding
from teddy_discovery_translation import (
    TRANSLATION_ACCEPTED,
    TranslationOutcome,
)
from teddy_discovery_subtitle_pipeline import (
    PIPELINE_PUBLISHED,
    run_subtitle_pipeline,
)
from teddy_discovery_subtitle_publish import (
    SUBTITLE_PUBLISHED,
    SubtitlePublishResult,
)
from teddy_discovery_subtitle_text import SubtitleCue


def require(condition, label):
    if not condition:
        raise AssertionError(label)


def expect(exception_type, function, label):
    try:
        function()
    except exception_type:
        return
    raise AssertionError(label)


def video(dvd_id="JUR-750"):
    family = dvd_id.rsplit("-", 1)[0]
    return CanonicalVideoHolding(
        dvd_id=dvd_id,
        relative_path=f"{family}/{dvd_id}/{dvd_id}.mp4",
        video_format="mp4",
    )


def snapshot_for(canonical_video, *, source_size=123, source_mtime_ns=456):
    return ASRSourceSnapshot.from_holding(
        canonical_video,
        source_size=source_size,
        source_mtime_ns=source_mtime_ns,
    )


def forced_chunk(snapshot, start_ms, end_ms):
    """Build an observable-valid chunk without importing NumPy in system Python."""

    chunk = object.__new__(ASRAudioChunk)
    object.__setattr__(chunk, "source_snapshot", snapshot)
    object.__setattr__(chunk, "start_ms", start_ms)
    object.__setattr__(chunk, "end_ms", end_ms)
    object.__setattr__(chunk, "sample_rate", 16_000)
    object.__setattr__(chunk, "samples", object())
    return chunk


class FakeSourceProvider:
    def __init__(self, local_source):
        self.local_source = local_source
        self.calls = []

    def copy_to_temp(self, canonical_video, *, max_media_bytes, timeout):
        self.calls.append((canonical_video, max_media_bytes, timeout))
        return self.local_source


class RotatingSourceProvider:
    def __init__(self, local_sources):
        self.local_sources = list(local_sources)
        self.calls = []

    def copy_to_temp(self, canonical_video, *, max_media_bytes, timeout):
        self.calls.append((canonical_video, max_media_bytes, timeout))
        if not self.local_sources:
            raise AssertionError("source provider was called too many times")
        return self.local_sources.pop(0)


class OnePassChunks:
    def __init__(self, chunks, error=None):
        self.chunks = tuple(chunks)
        self.error = error
        self.iterations = 0
        self.position = 0

    def __iter__(self):
        self.iterations += 1
        if self.iterations != 1:
            raise AssertionError("audio iterator was restarted")
        return self

    def __next__(self):
        if self.position >= len(self.chunks):
            if self.error is not None:
                error = self.error
                self.error = None
                raise error
            raise StopIteration
        chunk = self.chunks[self.position]
        self.position += 1
        return chunk


class FakeWhisper:
    def __init__(self, responses, *, engine_version="smoke-whisper"):
        self.responses = tuple(responses)
        self.engine_version = engine_version
        self.calls = []

    def transcribe_chunk(self, chunk):
        self.calls.append(chunk)
        return self.responses[len(self.calls) - 1]


def local_source(canonical_video, *, source_snapshot=None):
    directory = tempfile.mkdtemp(prefix="teddy-stage11-transcriber-smoke-")
    path = Path(directory) / "media.mp4"
    path.write_bytes(b"synthetic media witness")
    return ASRLocalMediaSource(
        local_path=str(path),
        source_snapshot=source_snapshot or snapshot_for(canonical_video),
        temp_directory=directory,
    ), path, Path(directory)


def make_transcriber(
    canonical_video,
    chunks,
    responses,
    *,
    source_override=None,
    whisper=None,
    iterator_error=None,
    max_media_bytes=987_654,
    source_timeout=7.5,
    chunk_seconds=600,
):
    if source_override is None:
        source_snapshot = next(
            (
                chunk.source_snapshot
                for chunk in chunks
                if getattr(chunk.source_snapshot, "dvd_id", None)
                == canonical_video.dvd_id
                and getattr(chunk.source_snapshot, "canonical_video_relative", None)
                == canonical_video.relative_path
            ),
            None,
        )
        source, path, directory = local_source(
            canonical_video,
            source_snapshot=source_snapshot,
        )
    else:
        source = source_override
        path = Path(source.local_path)
        directory = path.parent
    provider = FakeSourceProvider(source)
    fake_whisper = whisper or FakeWhisper(responses)
    one_pass = OnePassChunks(chunks, error=iterator_error)

    def iterator(local, *, chunk_seconds, start_seconds, end_seconds):
        require(local is source_override or local is source, "ITERATOR_SOURCE")
        require(chunk_seconds == chunk_seconds_value, "ITERATOR_CHUNK_SECONDS")
        require(start_seconds == 0, "ITERATOR_START")
        require(end_seconds is None, "ITERATOR_END")
        return one_pass

    chunk_seconds_value = chunk_seconds
    adapter = transcriber_module.FullTitleASRTranscriber(
        source_provider=provider,
        max_media_bytes=max_media_bytes,
        source_timeout=source_timeout,
        chunk_seconds=chunk_seconds,
        whisper=fake_whisper,
        audio_chunk_iterator=iterator,
    )
    return adapter, provider, fake_whisper, one_pass, path, directory


def accepted_translation(cue):
    return TranslationOutcome(
        cue=cue,
        action=TRANSLATION_ACCEPTED,
        attempts=1,
        ko_text="한국어",
        reason=None,
    )


def main():
    title = video()
    snapshot = snapshot_for(title)

    # A. One chunk, two already-absolute ASR segments.
    chunk = forced_chunk(snapshot, 1_000, 2_000)
    segments = (
        ASRSegment(1_100, 1_300, "一"),
        ASRSegment(1_500, 1_800, "二"),
    )
    adapter, provider, whisper, one_pass, path, directory = make_transcriber(
        title,
        [chunk],
        [segments],
    )
    result = adapter(title)
    require(isinstance(result, ASRResult), "ONE_RESULT_TYPE")
    require(result.source_snapshot is snapshot, "ONE_SNAPSHOT_IDENTITY")
    require(result.source_language == "ja", "ONE_LANGUAGE")
    require(result.segments == segments, "ONE_SEGMENTS")
    require(result.engine_version == "smoke-whisper", "ONE_ENGINE_VERSION")
    require(len(provider.calls) == 1, "ONE_SOURCE_CALL")
    require(len(whisper.calls) == 1 and whisper.calls[0] is chunk, "ONE_WHISPER_CALL")
    require(one_pass.iterations == 1, "ONE_PASS")
    require(not path.exists() and not directory.exists(), "ONE_CLEANUP")

    # B. Three contiguous chunks, including a silent middle chunk.  The same
    # fake Whisper instance receives all chunks in order.
    chunks = [
        forced_chunk(snapshot, 0, 1_000),
        forced_chunk(snapshot, 1_000, 2_000),
        forced_chunk(snapshot, 2_000, 3_000),
    ]
    multi_segments = (
        (ASRSegment(100, 300, "첫"),),
        (),
        (ASRSegment(2_100, 2_400, "셋"),),
    )
    adapter, provider, whisper, one_pass, path, directory = make_transcriber(
        title,
        chunks,
        multi_segments,
    )
    result = adapter(title)
    require(result.segments == (multi_segments[0][0], multi_segments[2][0]), "MULTI_APPEND")
    require(tuple(whisper.calls) == tuple(chunks), "MULTI_SAME_WHISPER")
    require(one_pass.iterations == 1, "MULTI_ONE_PASS")
    require(not path.exists() and not directory.exists(), "MULTI_CLEANUP")

    # C. The later segment already has an absolute timestamp.  No second
    # chunk offset is applied by the full-title adapter.
    absolute_chunk = forced_chunk(snapshot, 10_000, 11_000)
    absolute_segment = ASRSegment(10_123, 10_456, "절대")
    adapter, _provider, _whisper, _one_pass, path, directory = make_transcriber(
        title,
        [absolute_chunk],
        [(absolute_segment,)],
    )
    require(adapter(title).segments == (absolute_segment,), "ABSOLUTE_NO_DOUBLE_OFFSET")
    require(not path.exists() and not directory.exists(), "ABSOLUTE_CLEANUP")

    # D. A chunk from another source snapshot stops before later transcription.
    other_snapshot = snapshot_for(video("ABC-123"))
    bad_chunk = forced_chunk(other_snapshot, 0, 1_000)
    adapter, provider, whisper, _one_pass, path, directory = make_transcriber(
        title,
        [bad_chunk, chunk],
        [(ASRSegment(100, 200, "잘못"),), (ASRSegment(1_100, 1_200, "후속"),)],
    )
    expect(
        transcriber_module.FullTitleASRContractError,
        lambda: adapter(title),
        "CHUNK_SOURCE_MISMATCH",
    )
    require(not whisper.calls, "CHUNK_MISMATCH_NO_WHISPER")
    require(not path.exists() and not directory.exists(), "CHUNK_MISMATCH_CLEANUP")

    # E. Gaps and overlaps are not repaired.
    for bad_next, label in (
        (forced_chunk(snapshot, 1_100, 2_000), "GAP"),
        (forced_chunk(snapshot, 900, 2_000), "OVERLAP"),
    ):
        adapter, _provider, whisper, _one_pass, path, directory = make_transcriber(
            title,
            [forced_chunk(snapshot, 0, 1_000), bad_next],
            [(ASRSegment(100, 200, "첫"),), (ASRSegment(1_200, 1_300, "둘"),)],
        )
        expect(
            transcriber_module.FullTitleASRContractError,
            lambda adapter=adapter: adapter(title),
            label + "_FAIL_CLOSED",
        )
        require(len(whisper.calls) == 1, label + "_NO_LATER_TRANSCRIPTION")
        require(not path.exists() and not directory.exists(), label + "_CLEANUP")

    # F. Whisper must return an immutable tuple of ASRSegment values.
    for response, label in (([ASRSegment(100, 200, "목록")], "LIST"), ((object(),), "MEMBER")):
        adapter, _provider, _whisper, _one_pass, path, directory = make_transcriber(
            title,
            [forced_chunk(snapshot, 0, 1_000)],
            [response],
        )
        expect(
            transcriber_module.FullTitleASRContractError,
            lambda adapter=adapter: adapter(title),
            "WHISPER_" + label,
        )
        require(not path.exists() and not directory.exists(), "WHISPER_" + label + "_CLEANUP")

    # G. Segment containment is strict and never clamped.
    for response, label in (
        ((ASRSegment(900, 1_100, "앞"),), "SEGMENT_BEFORE"),
        ((ASRSegment(900, 1_100, "뒤"),), "SEGMENT_AFTER"),
    ):
        if label == "SEGMENT_AFTER":
            response = (ASRSegment(900, 1_100, "뒤"),)
            bad_chunk_for_segment = forced_chunk(snapshot, 0, 1_000)
        else:
            bad_chunk_for_segment = forced_chunk(snapshot, 1_000, 2_000)
        adapter, _provider, _whisper, _one_pass, path, directory = make_transcriber(
            title,
            [bad_chunk_for_segment],
            [response],
        )
        expect(
            transcriber_module.FullTitleASRContractError,
            lambda adapter=adapter: adapter(title),
            label,
        )
        require(not path.exists() and not directory.exists(), label + "_CLEANUP")

    # H. Nondecreasing segment starts are enforced without sorting.
    regressing = (
        ASRSegment(100, 200, "앞"),
        ASRSegment(50, 90, "뒤"),
    )
    adapter, _provider, _whisper, _one_pass, path, directory = make_transcriber(
        title,
        [forced_chunk(snapshot, 0, 1_000)],
        [regressing],
    )
    expect(
        transcriber_module.FullTitleASRContractError,
        lambda: adapter(title),
        "SEGMENT_TIMELINE_REGRESSION",
    )
    require(not path.exists() and not directory.exists(), "REGRESSION_CLEANUP")

    # I. Aggregate bound is checked before extension.  Shrink only the smoke
    # module's imported witness temporarily; restore it immediately.
    old_limit = transcriber_module.MAX_ASR_SEGMENTS
    transcriber_module.MAX_ASR_SEGMENTS = 1
    try:
        adapter, _provider, _whisper, _one_pass, path, directory = make_transcriber(
            title,
            [
                forced_chunk(snapshot, 0, 1_000),
                forced_chunk(snapshot, 1_000, 2_000),
            ],
            [
                (ASRSegment(100, 200, "첫"),),
                (ASRSegment(1_100, 1_200, "둘"),),
            ],
        )
        expect(
            ASRLimitError,
            lambda: adapter(title),
            "AGGREGATE_LIMIT",
        )
        require(not path.exists() and not directory.exists(), "AGGREGATE_LIMIT_CLEANUP")
    finally:
        transcriber_module.MAX_ASR_SEGMENTS = old_limit

    # J. Zero audio chunks are a typed no-speech failure, not an empty result.
    adapter, _provider, whisper, one_pass, path, directory = make_transcriber(
        title,
        [],
        [],
    )
    expect(
        transcriber_module.FullTitleASRError,
        lambda: adapter(title),
        "ZERO_CHUNKS",
    )
    require(not whisper.calls, "ZERO_CHUNKS_NO_WHISPER")
    require(one_pass.iterations == 1, "ZERO_CHUNKS_ONE_PASS")
    require(not path.exists() and not directory.exists(), "ZERO_CHUNKS_CLEANUP")

    # K. All chunks silent is a typed no-speech failure, not an empty result.
    adapter, _provider, _whisper, _one_pass, path, directory = make_transcriber(
        title,
        [forced_chunk(snapshot, 0, 1_000)],
        [()],
    )
    expect(
        transcriber_module.FullTitleASRError,
        lambda: adapter(title),
        "ALL_SILENT",
    )
    require(not path.exists() and not directory.exists(), "ALL_SILENT_CLEANUP")

    # K/L. Failure during iteration or Whisper still cleans the source and
    # keeps the original typed failure visible.
    iterator_failure = ASRAudioError("synthetic audio failure")
    adapter, _provider, _whisper, _one_pass, path, directory = make_transcriber(
        title,
        [forced_chunk(snapshot, 0, 1_000)],
        [()],
        iterator_error=iterator_failure,
    )
    expect(ASRAudioError, lambda: adapter(title), "ITERATOR_FAILURE")
    require(not path.exists() and not directory.exists(), "ITERATOR_FAILURE_CLEANUP")

    class FailingWhisper:
        engine_version = "smoke-whisper"

        def __init__(self):
            self.calls = 0

        def transcribe_chunk(self, _chunk):
            self.calls += 1
            raise ASRWhisperError("synthetic whisper failure")

    failing_whisper = FailingWhisper()
    adapter, _provider, _whisper, _one_pass, path, directory = make_transcriber(
        title,
        [forced_chunk(snapshot, 0, 1_000)],
        [()],
        whisper=failing_whisper,
    )
    expect(ASRWhisperError, lambda: adapter(title), "WHISPER_FAILURE")
    require(failing_whisper.calls == 1, "WHISPER_FAILURE_CALL")
    require(not path.exists() and not directory.exists(), "WHISPER_FAILURE_CLEANUP")

    # M. Source identity mismatch fails before the iterator/Whisper.
    wrong_source, wrong_path, wrong_directory = local_source(video("ABC-123"))
    adapter, provider, whisper, one_pass, _path, _directory = make_transcriber(
        title,
        [chunk],
        [segments],
        source_override=wrong_source,
    )
    expect(
        transcriber_module.FullTitleASRContractError,
        lambda: adapter(title),
        "SOURCE_IDENTITY_MISMATCH",
    )
    require(not whisper.calls and one_pass.iterations == 0, "SOURCE_MISMATCH_NO_AUDIO")
    require(not wrong_path.exists() and not wrong_directory.exists(), "SOURCE_MISMATCH_CLEANUP")

    # N. Invalid configuration is rejected before source access.
    for kwargs, label in (
        ({"max_media_bytes": 0}, "MAX_MEDIA_ZERO"),
        ({"chunk_seconds": 0}, "CHUNK_ZERO"),
        ({"chunk_seconds": 601}, "CHUNK_TOO_LARGE"),
        ({"source_timeout": 0}, "TIMEOUT_ZERO"),
        ({"source_timeout": float("nan")}, "TIMEOUT_NAN"),
    ):
        source, path, directory = local_source(title)
        provider = FakeSourceProvider(source)
        values = {
            "source_provider": provider,
            "max_media_bytes": 100,
            "whisper": FakeWhisper([()]),
            "audio_chunk_iterator": lambda *_args, **_kwargs: (),
        }
        values.update(kwargs)
        expect(
            transcriber_module.FullTitleASRValidationError,
            lambda values=values: transcriber_module.FullTitleASRTranscriber(**values),
            label,
        )
        require(not provider.calls, label + "_NO_SOURCE")
        source.cleanup()
        require(not path.exists() and not directory.exists(), label + "_CLEANUP")

    # O. Reusing one transcriber for different titles does not leak aggregate
    # segments, chunk boundaries, or source snapshots between calls.
    title_a = video("JUR-750")
    title_b = video("ABC-123")
    snapshot_a = snapshot_for(title_a, source_size=101, source_mtime_ns=1_001)
    snapshot_b = snapshot_for(title_b, source_size=202, source_mtime_ns=2_002)
    source_a, path_a, directory_a = local_source(
        title_a,
        source_snapshot=snapshot_a,
    )
    source_b, path_b, directory_b = local_source(
        title_b,
        source_snapshot=snapshot_b,
    )
    rotating_provider = RotatingSourceProvider([source_a, source_b])
    chunk_a = forced_chunk(snapshot_a, 0, 1_000)
    chunk_b = forced_chunk(snapshot_b, 5_000, 6_000)
    streams = [
        OnePassChunks([chunk_a]),
        OnePassChunks([chunk_b]),
    ]
    iterator_calls = []

    def rotating_iterator(local, **_kwargs):
        index = len(iterator_calls)
        require(index < len(streams), "CROSS_TITLE_ITERATOR_COUNT")
        iterator_calls.append(local)
        return streams[index]

    reused_whisper = FakeWhisper(
        [
            (ASRSegment(100, 200, "甲"),),
            (ASRSegment(5_100, 5_200, "乙"),),
        ]
    )
    reused_transcriber = transcriber_module.FullTitleASRTranscriber(
        source_provider=rotating_provider,
        max_media_bytes=100,
        whisper=reused_whisper,
        audio_chunk_iterator=rotating_iterator,
    )
    result_a = reused_transcriber(title_a)
    result_b = reused_transcriber(title_b)
    require(result_a.source_snapshot is snapshot_a, "CROSS_TITLE_SNAPSHOT_A")
    require(result_b.source_snapshot is snapshot_b, "CROSS_TITLE_SNAPSHOT_B")
    require(
        result_a.segments == (reused_whisper.responses[0][0],),
        "CROSS_TITLE_SEGMENTS_A",
    )
    require(
        result_b.segments == (reused_whisper.responses[1][0],),
        "CROSS_TITLE_SEGMENTS_B",
    )
    require(
        tuple(reused_whisper.calls) == (chunk_a, chunk_b),
        "CROSS_TITLE_WHISPER_REUSE",
    )
    require(len(rotating_provider.calls) == 2, "CROSS_TITLE_SOURCE_CALLS")
    require(
        tuple(iterator_calls) == (source_a, source_b),
        "CROSS_TITLE_ITERATOR_SOURCES",
    )
    require(
        streams[0].iterations == 1 and streams[1].iterations == 1,
        "CROSS_TITLE_ONE_PASS",
    )
    require(
        not path_a.exists() and not directory_a.exists(),
        "CROSS_TITLE_CLEANUP_A",
    )
    require(
        not path_b.exists() and not directory_b.exists(),
        "CROSS_TITLE_CLEANUP_B",
    )

    # P. The constructor keeps the default iterator one-pass boundary and
    # passes the configured source arguments unchanged.
    source, path, directory = local_source(title)
    provider = FakeSourceProvider(source)
    custom_whisper = FakeWhisper([(ASRSegment(100, 200, "한"),)])
    custom_chunks = OnePassChunks([forced_chunk(snapshot, 0, 1_000)])
    iterator_calls = []

    def custom_iterator(local, *, chunk_seconds, start_seconds, end_seconds):
        iterator_calls.append((local, chunk_seconds, start_seconds, end_seconds))
        return custom_chunks

    adapter = transcriber_module.FullTitleASRTranscriber(
        source_provider=provider,
        max_media_bytes=333,
        source_timeout=4,
        chunk_seconds=12.5,
        whisper=custom_whisper,
        audio_chunk_iterator=custom_iterator,
    )
    adapter(title)
    require(provider.calls == [(title, 333, 4)], "SOURCE_ARGUMENTS_UNCHANGED")
    require(iterator_calls == [(source, 12.5, 0, None)], "ITERATOR_ARGUMENTS")
    require(custom_chunks.iterations == 1, "CUSTOM_ONE_PASS")
    require(not path.exists() and not directory.exists(), "CUSTOM_CLEANUP")

    # The production default creates one lazy Whisper adapter without loading
    # its model during construction.
    source, path, directory = local_source(title)
    default_provider = FakeSourceProvider(source)
    default_adapter = transcriber_module.FullTitleASRTranscriber(
        source_provider=default_provider,
        max_media_bytes=100,
        audio_chunk_iterator=lambda *_args, **_kwargs: (),
    )
    require(isinstance(default_adapter.whisper, FasterWhisperASR), "DEFAULT_WHISPER_TYPE")
    require(default_adapter.whisper._model is None, "DEFAULT_WHISPER_LAZY")
    source.cleanup()
    require(not path.exists() and not directory.exists(), "DEFAULT_WHISPER_CLEANUP")

    # Q. The callable returns the exact ASRResult shape accepted by the frozen
    # per-title pipeline; a minimal fake integration avoids real downstream IO.
    source, path, directory = local_source(title)
    provider = FakeSourceProvider(source)
    pipeline_whisper = FakeWhisper([(ASRSegment(100, 200, "日本語"),)])
    pipeline_chunks = OnePassChunks([forced_chunk(snapshot, 0, 1_000)])

    def pipeline_iterator(_local, **_kwargs):
        return pipeline_chunks

    pipeline_transcriber = transcriber_module.FullTitleASRTranscriber(
        source_provider=provider,
        max_media_bytes=100,
        whisper=pipeline_whisper,
        audio_chunk_iterator=pipeline_iterator,
    )

    class EmptyReader:
        def list_subtitle_candidates(self, _canonical_video):
            return ()

        def read_subtitle_bytes(self, _canonical_video, _candidate):
            raise AssertionError("ASR pipeline should not read subtitles")

    class PipelinePublisher:
        def __init__(self):
            self.calls = []

        def publish_korean_srt(self, *, canonical_video, artifact, target_relative):
            self.calls.append((canonical_video, artifact, target_relative))
            return SubtitlePublishResult(
                state=SUBTITLE_PUBLISHED,
                target_relative=target_relative,
                sha256=artifact.sha256,
                byte_size=artifact.byte_size,
            )

    publisher = PipelinePublisher()
    pipeline_result = run_subtitle_pipeline(
        canonical_video=title,
        subtitle_reader=EmptyReader(),
        translate_ja_cue=accepted_translation,
        translate_en_cue=accepted_translation,
        asr_transcriber=pipeline_transcriber,
        publisher=publisher,
    )
    require(pipeline_result.state == PIPELINE_PUBLISHED, "PIPELINE_COMPATIBILITY")
    require(len(publisher.calls) == 1, "PIPELINE_PUBLISH")
    require(not path.exists() and not directory.exists(), "PIPELINE_CLEANUP")

    # Public ownership/static audit.
    production_source = Path(transcriber_module.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "teddy_discovery_translation",
        "teddy_discovery_ko_guard",
        "teddy_discovery_ko_srt",
        "teddy_discovery_subtitle_publish",
        "teddy_discovery_completion",
        "sqlite3",
        "jellyfin",
        "os.unlink",
        "Path.unlink",
    ):
        require(forbidden not in production_source, "NO_OWNERSHIP_" + forbidden.upper().replace(".", "_"))

    require(
        set(transcriber_module.FullTitleASRTranscriber.__dict__) >= {
            "__call__",
            "_transcribe_local_source",
        },
        "PUBLIC_CALLABLE_CLASS",
    )
    print("STAGE11_FULL_TITLE_ASR_SMOKE=PASS")


if __name__ == "__main__":
    main()
