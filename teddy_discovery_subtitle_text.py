"""Deterministic bounded subtitle byte validation and text parsing.

This module consumes already-bounded bytes supplied by a future transport
adapter.  It performs no filesystem, network, NAS, database, media, or model
I/O.  It validates only the ordinary SRT/WebVTT text subset needed by Stage11;
it does not interpret dialogue, markup, CSS, or cue settings semantically.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
import unicodedata


MAX_SUBTITLE_BYTES = 8 * 1024 * 1024
MAX_SUBTITLE_CUES = 50_000
MAX_CUE_TEXT_CHARS = 16_384

SUPPORTED_SUBTITLE_FORMATS = frozenset({"srt", "vtt"})


class SubtitleTextError(ValueError):
    """Base class for deterministic subtitle byte/content failures."""


class SubtitleInputError(SubtitleTextError):
    """Raised for non-bytes, empty, or oversized subtitle input."""


class SubtitleEncodingError(SubtitleTextError):
    """Raised when subtitle bytes are not strict UTF-8."""


class SubtitleParseError(SubtitleTextError):
    """Raised when the explicitly requested subtitle format is malformed."""


class SubtitleLimitError(SubtitleTextError):
    """Raised when a cue or serialized payload exceeds a fixed safety bound."""


class SubtitleSerializationError(SubtitleTextError):
    """Raised when an immutable document cannot be serialized safely."""


@dataclass(frozen=True)
class SubtitleCue:
    """One parsed subtitle cue with millisecond timestamps and raw text."""

    start_ms: int
    end_ms: int
    text: str

    def __post_init__(self):
        if type(self.start_ms) is not int or type(self.end_ms) is not int:
            raise SubtitleParseError(
                "cue timestamps must be integers"
            )

        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise SubtitleParseError(
                "cue end_ms must be greater than start_ms"
            )

        if not isinstance(self.text, str):
            raise SubtitleParseError(
                "cue text must be a string"
            )

        _validate_cue_text(self.text)


@dataclass(frozen=True)
class SubtitleDocument:
    """Immutable parsed subtitle document metadata and cue tuple."""

    format: str
    cues: tuple[SubtitleCue, ...]
    source_sha256: str
    byte_size: int

    def __post_init__(self):
        if self.format not in SUPPORTED_SUBTITLE_FORMATS:
            raise SubtitleParseError(
                "document format must be 'srt' or 'vtt'"
            )

        if not isinstance(self.cues, tuple):
            raise SubtitleParseError(
                "document cues must be an immutable tuple"
            )

        if not self.cues or len(self.cues) > MAX_SUBTITLE_CUES:
            raise SubtitleLimitError(
                "document cue count is outside the allowed bounds"
            )

        previous_start_ms = None

        for cue in self.cues:
            if not isinstance(cue, SubtitleCue):
                raise SubtitleParseError(
                    "document cues must contain SubtitleCue values"
                )

            if (
                previous_start_ms is not None
                and cue.start_ms < previous_start_ms
            ):
                raise SubtitleParseError(
                    "cue start times must be nondecreasing"
                )

            previous_start_ms = cue.start_ms

        if (
            not isinstance(self.source_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", self.source_sha256)
        ):
            raise SubtitleParseError(
                "source_sha256 must be a lowercase SHA-256 hex digest"
            )

        if type(self.byte_size) is not int or self.byte_size <= 0:
            raise SubtitleParseError(
                "byte_size must be a positive integer"
            )


def _validate_cue_text(text: str) -> None:
    if not text.strip():
        raise SubtitleParseError(
            "cue text must be nonempty after trimming outer whitespace"
        )

    if len(text) > MAX_CUE_TEXT_CHARS:
        raise SubtitleLimitError(
            "cue text exceeds MAX_CUE_TEXT_CHARS"
        )

    for character in text:
        if character in {"\n", "\t"}:
            continue

        if (
            ord(character) < 32
            or ord(character) == 127
            or unicodedata.category(character) == "Cc"
        ):
            raise SubtitleParseError(
                "cue text contains a disallowed control character"
            )


def _decode_subtitle_bytes(payload: bytes) -> str:
    if not isinstance(payload, bytes):
        raise SubtitleInputError(
            "subtitle payload must be bytes"
        )

    byte_size = len(payload)

    if byte_size == 0:
        raise SubtitleInputError(
            "subtitle payload must not be empty"
        )

    if byte_size > MAX_SUBTITLE_BYTES:
        raise SubtitleLimitError(
            "subtitle payload exceeds MAX_SUBTITLE_BYTES"
        )

    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SubtitleEncodingError(
            "subtitle payload is not valid UTF-8"
        ) from error

    if text.startswith("\ufeff"):
        text = text[1:]

    if "\x00" in text:
        raise SubtitleParseError(
            "subtitle payload contains NUL"
        )

    return text.replace("\r\n", "\n").replace("\r", "\n")


def _split_nonempty_blocks(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []

    for line in lines:
        if not line.strip():
            if current:
                blocks.append(current)
                current = []
            continue

        current.append(line)

    if current:
        blocks.append(current)

    return blocks


def _require_format(text_format: str) -> str:
    if text_format not in SUPPORTED_SUBTITLE_FORMATS:
        raise SubtitleInputError(
            "expected text_format must be exactly 'srt' or 'vtt'"
        )

    return text_format


def _parse_srt_index(line: str) -> int:
    value = line.strip()

    if not re.fullmatch(r"[0-9]+", value):
        raise SubtitleParseError(
            "SRT cue index must be numeric"
        )

    try:
        index = int(value)
    except ValueError as error:
        raise SubtitleParseError(
            "SRT cue index is not representable"
        ) from error

    if index <= 0:
        raise SubtitleParseError(
            "SRT cue index must be positive"
        )

    return index


_SRT_TIMESTAMP_LINE_RE = re.compile(
    r"^"
    r"([0-9]{2,}):([0-9]{2}):([0-9]{2}),([0-9]{3})"
    r" --> "
    r"([0-9]{2,}):([0-9]{2}):([0-9]{2}),([0-9]{3})"
    r"$"
)


def _timestamp_parts_to_ms(
    hours: str,
    minutes: str,
    seconds: str,
    milliseconds: str,
) -> int:
    try:
        hours_value = int(hours)
        minutes_value = int(minutes)
        seconds_value = int(seconds)
        milliseconds_value = int(milliseconds)
    except ValueError as error:
        raise SubtitleParseError(
            "timestamp contains an invalid number"
        ) from error

    if minutes_value > 59 or seconds_value > 59:
        raise SubtitleParseError(
            "timestamp minutes and seconds must be 00..59"
        )

    return (
        ((hours_value * 60 + minutes_value) * 60 + seconds_value)
        * 1000
        + milliseconds_value
    )


def _parse_srt_timestamp_line(line: str) -> tuple[int, int]:
    match = _SRT_TIMESTAMP_LINE_RE.fullmatch(line)

    if match is None:
        raise SubtitleParseError(
            "SRT timestamp line is malformed"
        )

    start_ms = _timestamp_parts_to_ms(*match.groups()[:4])
    end_ms = _timestamp_parts_to_ms(*match.groups()[4:])

    if end_ms <= start_ms:
        raise SubtitleParseError(
            "cue end timestamp must be after start timestamp"
        )

    return start_ms, end_ms


def _make_document(
    *,
    text_format: str,
    cues: list[SubtitleCue],
    payload: bytes,
) -> SubtitleDocument:
    if not cues:
        raise SubtitleParseError(
            "subtitle must contain at least one cue"
        )

    if len(cues) > MAX_SUBTITLE_CUES:
        raise SubtitleLimitError(
            "subtitle cue count exceeds MAX_SUBTITLE_CUES"
        )

    return SubtitleDocument(
        format=text_format,
        cues=tuple(cues),
        source_sha256=hashlib.sha256(payload).hexdigest(),
        byte_size=len(payload),
    )


def _parse_srt(text: str, payload: bytes) -> SubtitleDocument:
    blocks = _split_nonempty_blocks(text.split("\n"))
    seen_indexes: set[int] = set()
    cues: list[SubtitleCue] = []
    previous_start_ms = None

    for block in blocks:
        if len(block) < 3:
            raise SubtitleParseError(
                "SRT cue must contain index, timestamp, and text"
            )

        index = _parse_srt_index(block[0])

        if index in seen_indexes:
            raise SubtitleParseError(
                "SRT cue indexes must be unique"
            )

        seen_indexes.add(index)

        start_ms, end_ms = _parse_srt_timestamp_line(block[1])

        if (
            previous_start_ms is not None
            and start_ms < previous_start_ms
        ):
            raise SubtitleParseError(
                "cue start times must be nondecreasing"
            )

        previous_start_ms = start_ms
        cue_text = "\n".join(block[2:])

        cue = SubtitleCue(
            start_ms=start_ms,
            end_ms=end_ms,
            text=cue_text,
        )
        cues.append(cue)

        if len(cues) > MAX_SUBTITLE_CUES:
            raise SubtitleLimitError(
                "subtitle cue count exceeds MAX_SUBTITLE_CUES"
            )

    return _make_document(
        text_format="srt",
        cues=cues,
        payload=payload,
    )


_VTT_TIMESTAMP_LINE_RE = re.compile(
    r"^(\S+)\s+-->\s+(\S+)(?:\s+.*)?$"
)

_VTT_HMS_TIMESTAMP_RE = re.compile(
    r"^([0-9]{2,}):([0-9]{2}):([0-9]{2})\.([0-9]{3})$"
)

_VTT_MS_TIMESTAMP_RE = re.compile(
    r"^([0-9]{2}):([0-9]{2})\.([0-9]{3})$"
)


def _parse_vtt_timestamp(value: str) -> int:
    hms_match = _VTT_HMS_TIMESTAMP_RE.fullmatch(value)

    if hms_match is not None:
        return _timestamp_parts_to_ms(*hms_match.groups())

    ms_match = _VTT_MS_TIMESTAMP_RE.fullmatch(value)

    if ms_match is not None:
        minutes, seconds, milliseconds = ms_match.groups()
        return _timestamp_parts_to_ms(
            "0" * 2,
            minutes,
            seconds,
            milliseconds,
        )

    raise SubtitleParseError(
        "VTT timestamp is malformed"
    )


def _parse_vtt_timestamp_line(line: str) -> tuple[int, int]:
    match = _VTT_TIMESTAMP_LINE_RE.fullmatch(line)

    if match is None:
        raise SubtitleParseError(
            "VTT timestamp line is malformed"
        )

    start_ms = _parse_vtt_timestamp(match.group(1))
    end_ms = _parse_vtt_timestamp(match.group(2))

    if end_ms <= start_ms:
        raise SubtitleParseError(
            "cue end timestamp must be after start timestamp"
        )

    return start_ms, end_ms


_VTT_REJECTED_BLOCK_RE = re.compile(
    r"^(?:NOTE|STYLE|REGION)(?:[ \t].*)?$"
)


def _is_rejected_vtt_block(block: list[str]) -> bool:
    return _VTT_REJECTED_BLOCK_RE.fullmatch(block[0]) is not None


def _parse_vtt(text: str, payload: bytes) -> SubtitleDocument:
    lines = text.split("\n")
    header_index = next(
        (
            index
            for index, line in enumerate(lines)
            if line.strip()
        ),
        None,
    )

    if header_index is None:
        raise SubtitleParseError(
            "VTT payload has no nonempty header"
        )

    header = lines[header_index]

    if not (
        header == "WEBVTT"
        or header.startswith("WEBVTT ")
    ):
        raise SubtitleParseError(
            "VTT header must be WEBVTT"
        )

    blocks = _split_nonempty_blocks(
        lines[header_index + 1:]
    )
    cues: list[SubtitleCue] = []
    previous_start_ms = None

    for block in blocks:
        if _is_rejected_vtt_block(block):
            raise SubtitleParseError(
                "VTT NOTE, STYLE, and REGION blocks are unsupported"
            )

        if _VTT_TIMESTAMP_LINE_RE.fullmatch(block[0]) is not None:
            timestamp_index = 0
        else:
            if len(block) < 2 or "-->" in block[0]:
                raise SubtitleParseError(
                    "VTT cue identifier/timestamp structure is malformed"
                )

            timestamp_index = 1

        if len(block) <= timestamp_index + 1:
            raise SubtitleParseError(
                "VTT cue must contain nonempty text"
            )

        start_ms, end_ms = _parse_vtt_timestamp_line(
            block[timestamp_index]
        )

        if (
            previous_start_ms is not None
            and start_ms < previous_start_ms
        ):
            raise SubtitleParseError(
                "cue start times must be nondecreasing"
            )

        previous_start_ms = start_ms
        cue_text = "\n".join(block[timestamp_index + 1:])

        cue = SubtitleCue(
            start_ms=start_ms,
            end_ms=end_ms,
            text=cue_text,
        )
        cues.append(cue)

        if len(cues) > MAX_SUBTITLE_CUES:
            raise SubtitleLimitError(
                "subtitle cue count exceeds MAX_SUBTITLE_CUES"
            )

    return _make_document(
        text_format="vtt",
        cues=cues,
        payload=payload,
    )


def parse_subtitle_bytes(
    payload: bytes,
    text_format: str,
) -> SubtitleDocument:
    """Parse strictly bounded UTF-8 bytes in the explicitly requested format."""

    expected_format = _require_format(text_format)
    text = _decode_subtitle_bytes(payload)

    if expected_format == "srt":
        return _parse_srt(text, payload)

    return _parse_vtt(text, payload)


def _format_srt_timestamp(milliseconds: int) -> str:
    hours, remainder = divmod(milliseconds, 60 * 60 * 1000)
    minutes, remainder = divmod(remainder, 60 * 1000)
    seconds, milliseconds = divmod(remainder, 1000)

    return (
        f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
    )


def serialize_srt(document: SubtitleDocument) -> bytes:
    """Serialize a parsed SRT/VTT document into canonical UTF-8 SRT bytes."""

    if not isinstance(document, SubtitleDocument):
        raise SubtitleSerializationError(
            "document must be a SubtitleDocument"
        )

    blocks: list[str] = []

    for index, cue in enumerate(document.cues, start=1):
        if cue.text.startswith("\n") or cue.text.endswith("\n"):
            raise SubtitleSerializationError(
                "cue text has outer newline content that cannot be serialized"
            )

        blocks.append(
            "\n".join(
                (
                    str(index),
                    (
                        _format_srt_timestamp(cue.start_ms)
                        + " --> "
                        + _format_srt_timestamp(cue.end_ms)
                    ),
                    cue.text,
                )
            )
        )

    payload = (
        "\n\n".join(blocks) + "\n"
    ).encode("utf-8")

    if len(payload) > MAX_SUBTITLE_BYTES:
        raise SubtitleLimitError(
            "serialized SRT exceeds MAX_SUBTITLE_BYTES"
        )

    return payload


__all__ = [
    "MAX_CUE_TEXT_CHARS",
    "MAX_SUBTITLE_BYTES",
    "MAX_SUBTITLE_CUES",
    "SUPPORTED_SUBTITLE_FORMATS",
    "SubtitleCue",
    "SubtitleDocument",
    "SubtitleEncodingError",
    "SubtitleInputError",
    "SubtitleLimitError",
    "SubtitleParseError",
    "SubtitleSerializationError",
    "SubtitleTextError",
    "parse_subtitle_bytes",
    "serialize_srt",
]
