"""Offline smoke tests for the immutable Stage11 ASR contracts."""

from dataclasses import FrozenInstanceError, replace

from teddy_discovery_asr import (
    ASRLimitError,
    ASRResult,
    ASRSegment,
    ASRSourceSnapshot,
    ASRValidationError,
    ASRWord,
    MAX_ASR_SEGMENT_TEXT_CHARS,
    MAX_ASR_SEGMENTS,
    validate_canonical_video,
)
from teddy_discovery_subtitle import (
    CanonicalVideoHolding,
    validate_canonical_holding,
)


def expect(error_type, function):
    try:
        function()
    except error_type:
        return
    raise AssertionError("expected " + error_type.__name__)


def video() -> CanonicalVideoHolding:
    return validate_canonical_holding(
        {
            "dvd_id": "JUR-750",
            "storage_root": "jav",
            "relative_path": "JUR/JUR-750/JUR-750.mp4",
            "parse_status": "MATCHED",
            "present": 1,
        },
        "JUR-750",
    )


def snapshot() -> ASRSourceSnapshot:
    return ASRSourceSnapshot.from_holding(
        video(),
        source_size=1_574_462_325,
        source_mtime_ns=1_700_000_000_000_000_000,
    )


def result(*, segments=None, **kwargs) -> ASRResult:
    return ASRResult(
        source_snapshot=snapshot(),
        source_language="ja",
        segments=(
            ASRSegment(0, 1_000, "こんにちは")
            if segments is None
            else segments
        ),
        engine_version="1.2.1",
        **kwargs,
    )


def main():
    validated_video = video()
    assert validate_canonical_video(validated_video) == validated_video
    expect(
        ASRValidationError,
        lambda: validate_canonical_video(
            CanonicalVideoHolding(
                dvd_id="JUR-750",
                relative_path="OTHER/OTHER-1/OTHER-1.mp4",
                video_format="mp4",
            )
        ),
    )

    source = snapshot()
    assert source.dvd_id == "JUR-750"
    assert source.canonical_video_relative == "JUR/JUR-750/JUR-750.mp4"
    assert source.source_size > 0

    word = ASRWord(100, 300, "こん")
    segment = ASRSegment(0, 1_000, "こんにちは", words=(word,))
    valid = result(segments=(segment,))
    assert valid.source_snapshot == source
    assert valid.source_language == "ja"
    assert valid.segments == (segment,)
    assert valid.engine == "faster-whisper"
    assert valid.model == "medium"
    assert valid.device == "cpu"
    assert valid.compute_type == "int8"
    assert valid.cpu_threads == 8
    assert valid.num_workers == 1
    try:
        valid.source_language = "en"
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError("ASRResult must be immutable")

    expect(
        ASRLimitError,
        lambda: result(segments=()),
    )
    too_many = (ASRSegment(0, 1_000, "x"),) * (MAX_ASR_SEGMENTS + 1)
    expect(ASRLimitError, lambda: result(segments=too_many))
    expect(
        ASRLimitError,
        lambda: ASRSegment(0, 1_000, "x" * (MAX_ASR_SEGMENT_TEXT_CHARS + 1)),
    )
    expect(ASRValidationError, lambda: ASRSegment(0, 1_000, " \t\n "))
    expect(ASRValidationError, lambda: ASRSegment(0, 1_000, "bad\x00text"))
    expect(
        ASRValidationError,
        lambda: result(
            segments=(
                ASRSegment(1_000, 2_000, "later"),
                ASRSegment(900, 1_500, "earlier"),
            )
        ),
    )

    overlap = result(
        segments=(
            ASRSegment(0, 2_000, "first"),
            ASRSegment(1_000, 3_000, "overlap"),
        )
    )
    assert overlap.segments[1].start_ms == 1_000
    expect(ASRValidationError, lambda: ASRSegment(100, 100, "bad"))
    expect(ASRValidationError, lambda: ASRSegment(100, 99, "bad"))

    expect(
        ASRValidationError,
        lambda: ASRSegment(
            0,
            1_000,
            "text",
            words=(ASRWord(0, 1_001, "outside"),),
        ),
    )
    expect(
        ASRValidationError,
        lambda: ASRSegment(
            0,
            1_000,
            "text",
            words=(ASRWord(500, 600, "late"), ASRWord(100, 200, "early")),
        ),
    )

    for field, value in (
        ("engine", "other"),
        ("model", "small"),
        ("device", "cuda"),
        ("compute_type", "float16"),
        ("cpu_threads", 4),
        ("num_workers", 2),
    ):
        expect(ASRValidationError, lambda field=field, value=value: replace(valid, **{field: value}))

    assert not {
        "translation",
        "ko",
        "publish_state",
        "job_state",
    }.intersection(ASRResult.__dataclass_fields__)

    print("STAGE11_ASR_SMOKE=PASS")


if __name__ == "__main__":
    main()
