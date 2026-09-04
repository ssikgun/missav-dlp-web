from __future__ import annotations

import hashlib
from pathlib import Path

from teddy_discovery_ko_srt import (
    GENERATED_SRT_NO_ARTIFACT,
    GENERATED_SRT_READY,
    GeneratedKoreanSRT,
    GeneratedSRTContractError,
    GeneratedSRTLimitError,
    GeneratedSRTValidationError,
    generate_korean_srt,
)
from teddy_discovery_subtitle_text import (
    MAX_CUE_TEXT_CHARS,
    MAX_SUBTITLE_BYTES,
    MAX_SUBTITLE_CUES,
    SubtitleCue,
    parse_subtitle_bytes,
    serialize_srt,
)


def expect_raises(exception_type, callback, marker: str):
    try:
        callback()
    except exception_type:
        return
    raise AssertionError(marker)


def main():
    assert GENERATED_SRT_READY == "GENERATED_SRT_READY"
    assert GENERATED_SRT_NO_ARTIFACT == "GENERATED_SRT_NO_ARTIFACT"

    # A/D. One cue uses exact canonical framing and integer milliseconds.
    one_cue = SubtitleCue(
        start_ms=1_234,
        end_ms=5_678,
        text="정확한 밀리초",
    )
    one = generate_korean_srt((one_cue,))
    expected_one = (
        "1\n"
        "00:00:01,234 --> 00:00:05,678\n"
        "정확한 밀리초\n"
    ).encode("utf-8")
    assert one.state == GENERATED_SRT_READY
    assert one.payload == expected_one
    assert one.cue_count == 1

    # B. Surviving source routes 1 and 3 become sequential SRT entries 1 and 2.
    first = SubtitleCue(
        start_ms=100,
        end_ms=400,
        text="첫 번째 대사",
    )
    third = SubtitleCue(
        start_ms=800,
        end_ms=1_200,
        text="세 번째 원본에서 살아남은 대사",
    )
    two = generate_korean_srt((first, third))
    blocks = two.payload.rstrip(b"\n").split(b"\n\n")
    assert len(blocks) == 2
    assert blocks[0].split(b"\n", 1)[0] == b"1"
    assert blocks[1].split(b"\n", 1)[0] == b"2"

    # C. Internal newlines and tabs are preserved exactly.
    multiline_text = "first line\nsecond\tline"
    multiline_cue = SubtitleCue(
        start_ms=2_000,
        end_ms=3_000,
        text=multiline_text,
    )
    multiline = generate_korean_srt((multiline_cue,))
    assert multiline_text.encode("utf-8") in multiline.payload
    assert parse_subtitle_bytes(multiline.payload, "srt").cues == (
        multiline_cue,
    )

    # E. Hours of 100 or more follow the frozen serializer's formatting.
    long_start = 100 * 60 * 60 * 1_000 + 2_345
    long_end = long_start + 4_321
    long_hours = generate_korean_srt(
        (
            SubtitleCue(
                start_ms=long_start,
                end_ms=long_end,
                text="긴 시간",
            ),
        )
    )
    assert b"100:00:02,345 --> 100:00:06,666" in long_hours.payload

    # F/G/N. UTF-8 has no BOM, exactly one final LF, and truthful metadata.
    assert one.payload.decode("utf-8").endswith("정확한 밀리초\n")
    assert not one.payload.startswith(b"\xef\xbb\xbf")
    assert one.payload.endswith(b"\n")
    assert not one.payload.endswith(b"\n\n")
    assert one.sha256 == hashlib.sha256(one.payload).hexdigest()
    assert one.byte_size == len(one.payload)
    assert 0 < one.byte_size <= MAX_SUBTITLE_BYTES

    # H. The exact cue-count limit remains valid when the byte limit permits it.
    minimal_cue = SubtitleCue(start_ms=0, end_ms=1, text="x")
    maximum_cues = tuple(minimal_cue for _ in range(MAX_SUBTITLE_CUES))
    maximum = generate_korean_srt(maximum_cues)
    assert maximum.state == GENERATED_SRT_READY
    assert maximum.cue_count == MAX_SUBTITLE_CUES
    expect_raises(
        GeneratedSRTLimitError,
        lambda: generate_korean_srt(maximum_cues + (minimal_cue,)),
        "CUE_COUNT_LIMIT_REJECTED",
    )

    # I. A shared maximum-size cue exceeds the byte bound without huge source data.
    large_cue = SubtitleCue(
        start_ms=0,
        end_ms=1,
        text="x" * MAX_CUE_TEXT_CHARS,
    )
    byte_limit_input = tuple(large_cue for _ in range(513))
    expect_raises(
        GeneratedSRTLimitError,
        lambda: generate_korean_srt(byte_limit_input),
        "BYTE_SIZE_LIMIT_REJECTED",
    )

    # Exact byte boundary: 8 MiB is accepted and one additional byte is not.
    boundary_count = 512
    boundary_seed_cues = tuple(
        SubtitleCue(start_ms=0, end_ms=1, text="x")
        for _ in range(boundary_count)
    )
    boundary_seed = generate_korean_srt(boundary_seed_cues)
    remaining_text_bytes = MAX_SUBTITLE_BYTES - boundary_seed.byte_size
    boundary_cues_list = []
    for cue in boundary_seed_cues:
        added_bytes = min(
            remaining_text_bytes,
            MAX_CUE_TEXT_CHARS - len(cue.text),
        )
        boundary_cues_list.append(
            SubtitleCue(
                start_ms=cue.start_ms,
                end_ms=cue.end_ms,
                text=cue.text + ("x" * added_bytes),
            )
        )
        remaining_text_bytes -= added_bytes
    assert remaining_text_bytes == 0

    boundary_cues = tuple(boundary_cues_list)
    at_byte_limit = generate_korean_srt(boundary_cues)
    assert at_byte_limit.byte_size == MAX_SUBTITLE_BYTES

    expandable_index = next(
        index
        for index, cue in enumerate(boundary_cues)
        if len(cue.text) < MAX_CUE_TEXT_CHARS
    )
    over_boundary_cues = list(boundary_cues)
    expandable_cue = over_boundary_cues[expandable_index]
    over_boundary_cues[expandable_index] = SubtitleCue(
        start_ms=expandable_cue.start_ms,
        end_ms=expandable_cue.end_ms,
        text=expandable_cue.text + "x",
    )
    expect_raises(
        GeneratedSRTLimitError,
        lambda: generate_korean_srt(tuple(over_boundary_cues)),
        "EXACT_BYTE_BOUNDARY_REJECTED",
    )

    # J. Decreasing starts fail instead of being sorted.
    decreasing = (
        SubtitleCue(start_ms=5_000, end_ms=6_000, text="first"),
        SubtitleCue(start_ms=4_000, end_ms=7_000, text="second"),
    )
    expect_raises(
        GeneratedSRTValidationError,
        lambda: generate_korean_srt(decreasing),
        "DECREASING_START_REJECTED",
    )

    # K. Nondecreasing starts may overlap and retain supplied order/timing.
    overlapping = (
        SubtitleCue(start_ms=1_000, end_ms=5_000, text="first"),
        SubtitleCue(start_ms=2_000, end_ms=3_000, text="second"),
    )
    overlap_result = generate_korean_srt(overlapping)
    assert parse_subtitle_bytes(overlap_result.payload, "srt").cues == overlapping

    # L. SubtitleCue permits outer newlines; generated SRT framing rejects them.
    for outer_text in ("\ntext", "text\n"):
        outer_cue = SubtitleCue(start_ms=0, end_ms=1, text=outer_text)
        expect_raises(
            GeneratedSRTContractError,
            lambda value=outer_cue: generate_korean_srt((value,)),
            "OUTER_NEWLINE_REJECTED",
        )

    # M. Empty input explicitly means no artifact and does not hash empty bytes.
    empty = generate_korean_srt(())
    assert empty == GeneratedKoreanSRT(
        state=GENERATED_SRT_NO_ARTIFACT,
        payload=None,
        cue_count=0,
        sha256=None,
        byte_size=0,
    )

    # O/P. Parsing proves roundtrip identity and supplies honest parity metadata.
    parity_cues = (
        one_cue,
        SubtitleCue(
            start_ms=6_000,
            end_ms=8_000,
            text="두 번째\n줄",
        ),
    )
    generated = generate_korean_srt(parity_cues)
    parsed_generated = parse_subtitle_bytes(generated.payload, "srt")
    assert parsed_generated.cues == parity_cues
    assert parsed_generated.source_sha256 == generated.sha256
    assert parsed_generated.byte_size == generated.byte_size
    assert serialize_srt(parsed_generated) == generated.payload

    # Q. Result combinations and public input types validate themselves.
    valid_payload = one.payload
    valid_hash = hashlib.sha256(valid_payload).hexdigest()
    invalid_results = (
        dict(
            state=GENERATED_SRT_READY,
            payload=None,
            cue_count=1,
            sha256=None,
            byte_size=0,
        ),
        dict(
            state=GENERATED_SRT_READY,
            payload=valid_payload,
            cue_count=0,
            sha256=valid_hash,
            byte_size=len(valid_payload),
        ),
        dict(
            state=GENERATED_SRT_READY,
            payload=valid_payload,
            cue_count=1,
            sha256="0" * 64,
            byte_size=len(valid_payload),
        ),
        dict(
            state=GENERATED_SRT_READY,
            payload=valid_payload,
            cue_count=1,
            sha256=valid_hash,
            byte_size=len(valid_payload) + 1,
        ),
        dict(
            state=GENERATED_SRT_NO_ARTIFACT,
            payload=b"unexpected",
            cue_count=0,
            sha256=None,
            byte_size=0,
        ),
        dict(
            state="UNKNOWN_GENERATED_STATE",
            payload=None,
            cue_count=0,
            sha256=None,
            byte_size=0,
        ),
    )
    for values in invalid_results:
        expect_raises(
            GeneratedSRTValidationError,
            lambda values=values: GeneratedKoreanSRT(**values),
            "INVALID_RESULT_COMBINATION_REJECTED",
        )

    expect_raises(
        GeneratedSRTValidationError,
        lambda: generate_korean_srt([one_cue]),
        "MUTABLE_CUE_SEQUENCE_REJECTED",
    )
    expect_raises(
        GeneratedSRTValidationError,
        lambda: generate_korean_srt(("not a cue",)),
        "INVALID_CUE_MEMBER_REJECTED",
    )

    try:
        one.state = GENERATED_SRT_NO_ARTIFACT
    except (AttributeError, TypeError):
        pass
    else:
        raise AssertionError("GeneratedKoreanSRT must be frozen")

    production_source = Path("teddy_discovery_ko_srt.py").read_text(
        encoding="utf-8"
    )
    for forbidden in (
        "SubtitleDocument",
        "serialize_srt",
        "source_sha256",
        "pathlib",
        "tempfile",
        "subprocess",
        "socket",
        "urllib",
        "requests",
        "sqlite",
        "Jellyfin",
        "E4B",
        "Whisper",
    ):
        assert forbidden not in production_source

    print("STAGE11_GENERATED_SRT_SMOKE=PASS")


if __name__ == "__main__":
    main()
