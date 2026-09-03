from __future__ import annotations

import hashlib

from teddy_discovery_subtitle_text import (
    MAX_CUE_TEXT_CHARS,
    MAX_SUBTITLE_BYTES,
    MAX_SUBTITLE_CUES,
    SubtitleCue,
    SubtitleDocument,
    SubtitleEncodingError,
    SubtitleInputError,
    SubtitleLimitError,
    SubtitleParseError,
    parse_subtitle_bytes,
    serialize_srt,
)


def require(condition: bool, marker: str):
    if not condition:
        raise AssertionError(marker)


def expect_raises(exception_type, callback, marker: str):
    try:
        callback()
    except exception_type:
        return

    raise AssertionError(marker)


def srt_timestamp(milliseconds: int) -> str:
    hours, remainder = divmod(milliseconds, 60 * 60 * 1000)
    minutes, remainder = divmod(remainder, 60 * 1000)
    seconds, milliseconds = divmod(remainder, 1000)
    return (
        f"{hours:02d}:{minutes:02d}:{seconds:02d},"
        f"{milliseconds:03d}"
    )


def srt_payload(cues) -> bytes:
    blocks = []

    for index, start_ms, end_ms, text in cues:
        blocks.append(
            "\n".join(
                (
                    str(index),
                    (
                        srt_timestamp(start_ms)
                        + " --> "
                        + srt_timestamp(end_ms)
                    ),
                    text,
                )
            )
        )

    return ("\n\n".join(blocks) + "\n").encode("utf-8")


def main():
    one_cue = srt_payload(
        [
            (1, 1_000, 2_500, "안녕 / こんにちは / hello"),
        ]
    )
    document = parse_subtitle_bytes(one_cue, text_format="srt")
    require(
        document.format == "srt"
        and document.byte_size == len(one_cue)
        and len(document.cues) == 1
        and document.cues[0].start_ms == 1_000
        and document.cues[0].end_ms == 2_500
        and document.cues[0].text == "안녕 / こんにちは / hello",
        "SRT_VALID_ONE_CUE",
    )
    require(
        isinstance(document.cues, tuple)
        and isinstance(document.cues[0], SubtitleCue),
        "IMMUTABLE_PARSED_MODEL",
    )

    multi_cue = srt_payload(
        [
            (7, 0, 2_000, "first\nline"),
            (10, 1_000, 3_000, "second"),
        ]
    )
    multi_document = parse_subtitle_bytes(multi_cue, "srt")
    require(
        [cue.start_ms for cue in multi_document.cues] == [0, 1_000]
        and [cue.end_ms for cue in multi_document.cues] == [2_000, 3_000]
        and multi_document.cues[0].text == "first\nline",
        "SRT_MULTI_OVERLAP_NONCONSECUTIVE_INDEX",
    )

    crlf = one_cue.replace(b"\n", b"\r\n")
    crlf_document = parse_subtitle_bytes(crlf, "srt")
    require(
        crlf_document.cues[0].text == one_cue.decode("utf-8").split("\n")[2]
        and "\r" not in crlf_document.cues[0].text,
        "SRT_CRLF_NORMALIZED",
    )

    bom_document = parse_subtitle_bytes(b"\xef\xbb\xbf" + one_cue, "srt")
    require(
        bom_document.cues == document.cues,
        "SRT_OPTIONAL_UTF8_BOM",
    )

    hours_document = parse_subtitle_bytes(
        srt_payload(
            [
                (1, 24 * 60 * 60 * 1000, 24 * 60 * 60 * 1000 + 1_000, "late"),
            ]
        ),
        "srt",
    )
    require(
        hours_document.cues[0].start_ms == 24 * 60 * 60 * 1000,
        "SRT_HOURS_GREATER_THAN_23",
    )

    expect_raises(
        SubtitleParseError,
        lambda: parse_subtitle_bytes(
            srt_payload([(1, 0, 1_000, "one"), (1, 2_000, 3_000, "two")]),
            "srt",
        ),
        "SRT_DUPLICATE_INDEX_REJECTED",
    )
    expect_raises(
        SubtitleParseError,
        lambda: parse_subtitle_bytes(
            srt_payload([(0, 0, 1_000, "zero")]),
            "srt",
        ),
        "SRT_ZERO_INDEX_REJECTED",
    )
    expect_raises(
        SubtitleParseError,
        lambda: parse_subtitle_bytes(
            b"-1\n00:00:00,000 --> 00:00:01,000\nnegative\n",
            "srt",
        ),
        "SRT_NEGATIVE_INDEX_REJECTED",
    )

    for payload, marker in (
        (
            b"1\n00:00:00.000 --> 00:00:01,000\nwrong comma\n",
            "SRT_MALFORMED_TIMESTAMP_REJECTED",
        ),
        (
            b"1\n00:60:00,000 --> 00:61:00,000\nminute\n",
            "SRT_MINUTE_60_REJECTED",
        ),
        (
            b"1\n00:00:60,000 --> 00:01:00,000\nsecond\n",
            "SRT_SECOND_60_REJECTED",
        ),
        (
            b"1\n00:00:00,00 --> 00:00:01,000\nmillis\n",
            "SRT_MILLISECOND_MALFORMED_REJECTED",
        ),
        (
            b"1\n00:00:01,000 --> 00:00:01,000\norder\n",
            "SRT_END_NOT_AFTER_START_REJECTED",
        ),
        (
            srt_payload([(1, 2_000, 3_000, "first"), (2, 1_000, 2_000, "back")]),
            "SRT_DECREASING_START_REJECTED",
        ),
        (
            b"1\n00:00:00,000 --> 00:00:01,000\n   \n",
            "SRT_EMPTY_TEXT_REJECTED",
        ),
    ):
        expect_raises(
            SubtitleParseError,
            lambda payload=payload: parse_subtitle_bytes(payload, "srt"),
            marker,
        )

    expect_raises(
        SubtitleEncodingError,
        lambda: parse_subtitle_bytes(
            b"1\n00:00:00,000 --> 00:00:01,000\n\xff\n",
            "srt",
        ),
        "SRT_INVALID_UTF8_REJECTED",
    )
    expect_raises(
        SubtitleParseError,
        lambda: parse_subtitle_bytes(
            b"1\n00:00:00,000 --> 00:00:01,000\nnull\x00byte\n",
            "srt",
        ),
        "SRT_NUL_REJECTED",
    )
    expect_raises(
        SubtitleLimitError,
        lambda: parse_subtitle_bytes(
            b"x" * (MAX_SUBTITLE_BYTES + 1),
            "srt",
        ),
        "SUBTITLE_BYTE_LIMIT_REJECTED",
    )

    too_many_cues = srt_payload(
        (
            index,
            index * 1_000,
            index * 1_000 + 500,
            "cue",
        )
        for index in range(1, MAX_SUBTITLE_CUES + 2)
    )
    expect_raises(
        SubtitleLimitError,
        lambda: parse_subtitle_bytes(too_many_cues, "srt"),
        "SRT_CUE_COUNT_LIMIT_REJECTED",
    )
    expect_raises(
        SubtitleLimitError,
        lambda: parse_subtitle_bytes(
            srt_payload(
                [
                    (1, 0, 1_000, "x" * (MAX_CUE_TEXT_CHARS + 1)),
                ]
            ),
            "srt",
        ),
        "SRT_CUE_TEXT_LIMIT_REJECTED",
    )

    vtt_basic = (
        "WEBVTT\n\n"
        "00:01.000 --> 00:03.000\n"
        "기본 자막\n"
    ).encode("utf-8")
    vtt_document = parse_subtitle_bytes(vtt_basic, "vtt")
    require(
        vtt_document.format == "vtt"
        and vtt_document.cues[0].start_ms == 1_000
        and vtt_document.cues[0].end_ms == 3_000
        and vtt_document.cues[0].text == "기본 자막",
        "VTT_VALID_BASIC_MM_SS",
    )

    vtt_identifier = (
        "WEBVTT\n\n"
        "chapter-1\n"
        "01:02:03.004 --> 01:02:04.005\n"
        "identified\n"
    ).encode("utf-8")
    identifier_document = parse_subtitle_bytes(vtt_identifier, "vtt")
    require(
        identifier_document.cues[0].start_ms
        == ((1 * 60 + 2) * 60 + 3) * 1_000 + 4
        and identifier_document.cues[0].end_ms
        == ((1 * 60 + 2) * 60 + 4) * 1_000 + 5,
        "VTT_OPTIONAL_IDENTIFIER_HH_MM_SS",
    )

    vtt_settings = (
        "WEBVTT - Stage11\n\n"
        "00:00:01.000 --> 00:00:02.000 align:start position:50%\n"
        "settings are ignored\n"
    ).encode("utf-8")
    settings_document = parse_subtitle_bytes(vtt_settings, "vtt")
    require(
        settings_document.cues[0].start_ms == 1_000
        and settings_document.cues[0].end_ms == 2_000,
        "VTT_CUE_SETTINGS_IGNORED",
    )

    for identifier, marker in (
        ("NOTEBOOK", "VTT_NOTEBOOK_IDENTIFIER_ACCEPTED"),
        ("STYLEGUIDE", "VTT_STYLEGUIDE_IDENTIFIER_ACCEPTED"),
        ("REGIONAL", "VTT_REGIONAL_IDENTIFIER_ACCEPTED"),
    ):
        identifier_document = parse_subtitle_bytes(
            (
                "WEBVTT\n\n"
                + identifier
                + "\n"
                "00:00.000 --> 00:01.000\n"
                "ordinary cue\n"
            ).encode("utf-8"),
            "vtt",
        )
        require(
            len(identifier_document.cues) == 1
            and identifier_document.cues[0].text == "ordinary cue",
            marker,
        )

    for payload, marker in (
        (
            b"NOTWEBVTT\n\n00:00.000 --> 00:01.000\nno\n",
            "VTT_BAD_HEADER_REJECTED",
        ),
        (
            b"WEBVTT\twrong\n\n00:00.000 --> 00:01.000\nno\n",
            "VTT_NONCANONICAL_HEADER_REJECTED",
        ),
        (
            b"WEBVTT\n\nNOTE comment\nnot a cue\n",
            "VTT_NOTE_REJECTED",
        ),
        (
            b"WEBVTT\n\nNOTE\tcomment\n"
            b"00:00.000 --> 00:01.000\nnot a cue\n",
            "VTT_NOTE_TAB_REJECTED",
        ),
        (
            b"WEBVTT\n\nSTYLE\n::cue { color: red }\n",
            "VTT_STYLE_REJECTED",
        ),
        (
            b"WEBVTT\n\nSTYLE\tmetadata\n"
            b"00:00.000 --> 00:01.000\nnot a cue\n",
            "VTT_STYLE_TAB_REJECTED",
        ),
        (
            b"WEBVTT\n\nREGION\nid:foo\n",
            "VTT_REGION_REJECTED",
        ),
        (
            b"WEBVTT\n\nREGION\tmetadata\n"
            b"00:00.000 --> 00:01.000\nnot a cue\n",
            "VTT_REGION_TAB_REJECTED",
        ),
        (
            b"WEBVTT\n\n00:60.000 --> 01:00.000\nminute\n",
            "VTT_INVALID_TIMESTAMP_REJECTED",
        ),
        (
            (
                "WEBVTT\n\n"
                "00:02.000 --> 00:03.000\nfirst\n\n"
                "00:01.000 --> 00:02.000\nback\n"
            ).encode("utf-8"),
            "VTT_DECREASING_START_REJECTED",
        ),
    ):
        expect_raises(
            SubtitleParseError,
            lambda payload=payload: parse_subtitle_bytes(payload, "vtt"),
            marker,
        )

    expect_raises(
        SubtitleParseError,
        lambda: parse_subtitle_bytes(vtt_basic, "srt"),
        "VTT_AS_SRT_REJECTED",
    )
    expect_raises(
        SubtitleParseError,
        lambda: parse_subtitle_bytes(one_cue, "vtt"),
        "SRT_AS_VTT_REJECTED",
    )
    expect_raises(
        SubtitleInputError,
        lambda: parse_subtitle_bytes(b"", "srt"),
        "ZERO_BYTE_REJECTED",
    )
    expect_raises(
        SubtitleInputError,
        lambda: parse_subtitle_bytes("not bytes", "srt"),
        "NON_BYTES_REJECTED",
    )
    expect_raises(
        SubtitleInputError,
        lambda: parse_subtitle_bytes(one_cue, "srtx"),
        "UNSUPPORTED_EXPECTED_FORMAT_REJECTED",
    )

    canonical_srt = serialize_srt(multi_document)
    require(
        canonical_srt.decode("utf-8")
        == (
            "1\n"
            "00:00:00,000 --> 00:00:02,000\n"
            "first\n"
            "line\n\n"
            "2\n"
            "00:00:01,000 --> 00:00:03,000\n"
            "second\n"
        ),
        "SRT_CANONICAL_SERIALIZATION",
    )
    require(
        parse_subtitle_bytes(canonical_srt, "srt").cues
        == multi_document.cues,
        "SRT_SERIALIZATION_ROUNDTRIP",
    )

    vtt_srt = serialize_srt(vtt_document)
    require(
        vtt_srt
        == (
            "1\n00:00:01,000 --> 00:00:03,000\n"
            "기본 자막\n"
        ).encode("utf-8"),
        "VTT_TO_CANONICAL_SRT",
    )
    require(
        vtt_srt.count(b"\r") == 0
        and vtt_srt.endswith(b"\n")
        and b"\n\n" not in vtt_srt,
        "SERIALIZATION_LF_FINAL_NEWLINE",
    )
    require(
        parse_subtitle_bytes(vtt_srt, "srt").cues == vtt_document.cues,
        "VTT_TIMESTAMP_TEXT_PRESERVATION",
    )

    require(
        document.source_sha256 == hashlib.sha256(one_cue).hexdigest()
        and bom_document.source_sha256
        == hashlib.sha256(b"\xef\xbb\xbf" + one_cue).hexdigest(),
        "SOURCE_SHA256_ORIGINAL_BYTES",
    )

    large_cue = SubtitleCue(
        start_ms=0,
        end_ms=1,
        text="x" * MAX_CUE_TEXT_CHARS,
    )
    large_document = SubtitleDocument(
        format="srt",
        cues=tuple(large_cue for _ in range(600)),
        source_sha256="0" * 64,
        byte_size=1,
    )
    expect_raises(
        SubtitleLimitError,
        lambda: serialize_srt(large_document),
        "SERIALIZATION_BYTE_LIMIT_REJECTED",
    )

    print("STAGE11_SUBTITLE_TEXT_SMOKE=PASS")


if __name__ == "__main__":
    main()
