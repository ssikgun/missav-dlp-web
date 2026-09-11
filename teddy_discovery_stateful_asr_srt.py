"""Deterministic ASR timing materialization for stateful Stage11 results."""

from __future__ import annotations

from dataclasses import dataclass
import re

from teddy_discovery_asr_artifact import ASRResult
from teddy_discovery_ko_srt import (
    GeneratedKoreanSRT,
    generate_korean_srt,
)
from teddy_discovery_stateful_translator import (
    StatefulSubtitlePackage,
    StatefulSubtitleResult,
    validate_stateful_result,
)
from teddy_discovery_subtitle_text import SubtitleCue


_ASR_CUE_ID_RE = re.compile(r"^asr-([0-9]{4,})$")


class StatefulASRSRTError(Exception):
    """Base error for deterministic stateful ASR SRT materialization."""


class StatefulASRSRTValidationError(StatefulASRSRTError):
    """Raised when semantic or timing identity is invalid."""


@dataclass(frozen=True)
class StatefulASRSRTMaterialization:
    artifact: GeneratedKoreanSRT
    source_indexes: tuple[int, ...]


def _source_index_for_cue_id(cue_id: str) -> int:
    if type(cue_id) is not str:
        raise StatefulASRSRTValidationError(
            "stateful ASR cue_id must be an exact string"
        )

    match = _ASR_CUE_ID_RE.fullmatch(cue_id)
    if match is None:
        raise StatefulASRSRTValidationError(
            "stateful ASR cue_id has an unsupported format"
        )

    ordinal = int(match.group(1))

    if ordinal < 1:
        raise StatefulASRSRTValidationError(
            "stateful ASR cue ordinal must be positive"
        )

    return ordinal - 1


def source_index_for_asr_cue_id(cue_id: str) -> int:
    """Resolve one sparse ``asr-######`` identity to its ASR ordinal."""

    return _source_index_for_cue_id(cue_id)


def materialize_stateful_asr_srt(
    package: StatefulSubtitlePackage,
    result: StatefulSubtitleResult,
    asr_result: ASRResult,
) -> StatefulASRSRTMaterialization:
    """Bind validated stateful KO cues to immutable ASR timing evidence."""

    validated_result = validate_stateful_result(
        result,
        package,
    )

    if not isinstance(asr_result, ASRResult):
        raise StatefulASRSRTValidationError(
            "asr_result must be an ASRResult"
        )

    if asr_result.source_snapshot.dvd_id != package.dvd_id:
        raise StatefulASRSRTValidationError(
            "ASR timing evidence belongs to a different DVD-ID"
        )

    source_indexes: list[int] = []
    artifact_cues: list[SubtitleCue] = []
    previous_index = None

    for semantic_cue in validated_result.cues:
        source_index = source_index_for_asr_cue_id(
            semantic_cue.cue_id
        )

        if source_index >= len(asr_result.segments):
            raise StatefulASRSRTValidationError(
                "stateful ASR cue points outside ASR timing evidence"
            )

        if (
            previous_index is not None
            and source_index <= previous_index
        ):
            raise StatefulASRSRTValidationError(
                "stateful ASR source indexes must be strictly increasing"
            )

        previous_index = source_index
        segment = asr_result.segments[source_index]

        artifact_cues.append(
            SubtitleCue(
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                text=semantic_cue.ko,
            )
        )
        source_indexes.append(source_index)

    artifact = generate_korean_srt(
        tuple(artifact_cues)
    )

    if artifact.cue_count != len(validated_result.cues):
        raise StatefulASRSRTValidationError(
            "generated SRT cue count does not match stateful result"
        )

    return StatefulASRSRTMaterialization(
        artifact=artifact,
        source_indexes=tuple(source_indexes),
    )


__all__ = [
    "StatefulASRSRTError",
    "StatefulASRSRTMaterialization",
    "StatefulASRSRTValidationError",
    "materialize_stateful_asr_srt",
    "source_index_for_asr_cue_id",
]
