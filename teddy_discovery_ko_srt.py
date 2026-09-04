"""Pure Stage11 generated Korean SRT assembly.

This module converts an immutable tuple of final subtitle cues into a bounded
canonical SRT payload.  Its hash and size describe only that generated payload;
it owns no parsed-source provenance, filesystem, network, database, model,
worker, publish, or completion behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re

from teddy_discovery_subtitle_text import (
    MAX_SUBTITLE_BYTES,
    MAX_SUBTITLE_CUES,
    SubtitleCue,
)


GENERATED_SRT_READY = "GENERATED_SRT_READY"
GENERATED_SRT_NO_ARTIFACT = "GENERATED_SRT_NO_ARTIFACT"


class GeneratedSRTError(Exception):
    """Base class for deterministic generated-SRT failures."""


class GeneratedSRTValidationError(GeneratedSRTError):
    """Raised for malformed generated-SRT input or result combinations."""


class GeneratedSRTLimitError(GeneratedSRTError):
    """Raised when generated cue or payload bounds are exceeded."""


class GeneratedSRTContractError(GeneratedSRTError):
    """Raised when a cue cannot satisfy canonical SRT framing."""


@dataclass(frozen=True)
class GeneratedKoreanSRT:
    """Immutable generated artifact metadata, or an explicit no-artifact result."""

    state: str
    payload: bytes | None
    cue_count: int
    sha256: str | None
    byte_size: int

    def __post_init__(self):
        if self.state == GENERATED_SRT_NO_ARTIFACT:
            if (
                self.payload is not None
                or type(self.cue_count) is not int
                or self.cue_count != 0
                or self.sha256 is not None
                or type(self.byte_size) is not int
                or self.byte_size != 0
            ):
                raise GeneratedSRTValidationError(
                    "no-artifact result contains artifact data"
                )
            return

        if self.state != GENERATED_SRT_READY:
            raise GeneratedSRTValidationError(
                "generated SRT state is invalid"
            )
        if not isinstance(self.payload, bytes) or not self.payload:
            raise GeneratedSRTValidationError(
                "ready result requires a nonempty bytes payload"
            )
        if type(self.cue_count) is not int or self.cue_count <= 0:
            raise GeneratedSRTValidationError(
                "ready result requires a positive cue_count"
            )
        if self.cue_count > MAX_SUBTITLE_CUES:
            raise GeneratedSRTLimitError(
                "ready result cue_count exceeds MAX_SUBTITLE_CUES"
            )
        if type(self.byte_size) is not int or self.byte_size != len(self.payload):
            raise GeneratedSRTValidationError(
                "ready result byte_size does not match its payload"
            )
        if self.byte_size <= 0:
            raise GeneratedSRTValidationError(
                "ready result byte_size must be positive"
            )
        if self.byte_size > MAX_SUBTITLE_BYTES:
            raise GeneratedSRTLimitError(
                "ready result exceeds MAX_SUBTITLE_BYTES"
            )
        if (
            not isinstance(self.sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", self.sha256) is None
        ):
            raise GeneratedSRTValidationError(
                "ready result sha256 must be lowercase SHA-256 hex"
            )
        if self.sha256 != hashlib.sha256(self.payload).hexdigest():
            raise GeneratedSRTValidationError(
                "ready result sha256 does not match its payload"
            )


def _format_srt_timestamp(milliseconds: int) -> str:
    hours, remainder = divmod(milliseconds, 60 * 60 * 1000)
    minutes, remainder = divmod(remainder, 60 * 1000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def generate_korean_srt(
    cues: tuple[SubtitleCue, ...],
) -> GeneratedKoreanSRT:
    """Generate canonical SRT bytes in supplied cue order without source metadata."""

    if not isinstance(cues, tuple):
        raise GeneratedSRTValidationError(
            "cues must be an immutable tuple"
        )
    if not cues:
        return GeneratedKoreanSRT(
            state=GENERATED_SRT_NO_ARTIFACT,
            payload=None,
            cue_count=0,
            sha256=None,
            byte_size=0,
        )
    if len(cues) > MAX_SUBTITLE_CUES:
        raise GeneratedSRTLimitError(
            "cue count exceeds MAX_SUBTITLE_CUES"
        )

    encoded_blocks: list[bytes] = []
    encoded_size = 0
    previous_start_ms = None

    for index, cue in enumerate(cues, start=1):
        if not isinstance(cue, SubtitleCue):
            raise GeneratedSRTValidationError(
                "cues must contain SubtitleCue values"
            )
        if (
            previous_start_ms is not None
            and cue.start_ms < previous_start_ms
        ):
            raise GeneratedSRTValidationError(
                "cue start times must be nondecreasing"
            )
        previous_start_ms = cue.start_ms

        if cue.text.startswith("\n") or cue.text.endswith("\n"):
            raise GeneratedSRTContractError(
                "cue text cannot start or end with a newline"
            )

        block = "\n".join(
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
        try:
            encoded_block = block.encode("utf-8")
        except UnicodeEncodeError as error:
            raise GeneratedSRTContractError(
                "cue cannot be encoded as UTF-8"
            ) from error

        separator_size = 2 if encoded_blocks else 0
        projected_size = encoded_size + separator_size + len(encoded_block) + 1
        if projected_size > MAX_SUBTITLE_BYTES:
            raise GeneratedSRTLimitError(
                "generated SRT exceeds MAX_SUBTITLE_BYTES"
            )

        encoded_blocks.append(encoded_block)
        encoded_size += separator_size + len(encoded_block)

    payload = b"\n\n".join(encoded_blocks) + b"\n"
    return GeneratedKoreanSRT(
        state=GENERATED_SRT_READY,
        payload=payload,
        cue_count=len(cues),
        sha256=hashlib.sha256(payload).hexdigest(),
        byte_size=len(payload),
    )


__all__ = [
    "GENERATED_SRT_NO_ARTIFACT",
    "GENERATED_SRT_READY",
    "GeneratedKoreanSRT",
    "GeneratedSRTContractError",
    "GeneratedSRTError",
    "GeneratedSRTLimitError",
    "GeneratedSRTValidationError",
    "generate_korean_srt",
]
