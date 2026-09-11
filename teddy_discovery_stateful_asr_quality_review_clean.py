"""Deterministic CLEAN materialization for ASR-only semantic review.

This is the ASR counterpart to the existing external-JA CLEAN sidecar.  It
reuses the same action semantics and SRT renderer, but resolves every retained
sparse ASR cue directly to its original segment timing.  No affine projection,
external document, model, file, or publication I/O is used.
"""

from __future__ import annotations

from dataclasses import dataclass

from teddy_discovery_asr import ASRResult, MAX_ASR_SEGMENTS
from teddy_discovery_ko_srt import GeneratedKoreanSRT, generate_korean_srt
from teddy_discovery_stateful_asr_srt import source_index_for_asr_cue_id
from teddy_discovery_stateful_asr_quality_review import (
    AMBIGUOUS,
    KEEP,
    OMIT,
    REPAIR,
    ASRQualityReviewRequest,
    validate_asr_quality_review_request,
    validate_asr_quality_review_result,
)
from teddy_discovery_stateful_quality_review import QualityReviewResult, effective_review_action
from teddy_discovery_stateful_translator import (
    StatefulSubtitlePackage,
    StatefulSubtitleResult,
    validate_stateful_result,
)
from teddy_discovery_subtitle_text import SubtitleCue
from teddy_discovery_targeted_second_evidence_artifact import (
    TargetedSecondEvidenceArtifact,
)


class StatefulASRQualityReviewCleanError(ValueError):
    """Original ASR/review evidence or CLEAN output failed closed."""


@dataclass(frozen=True)
class ASRQualityReviewCleanCue:
    cue_id: str
    original_source_index: int
    start_ms: int
    end_ms: int
    ja: str
    ko: str
    review_action: str

    def __post_init__(self):
        try:
            resolved = source_index_for_asr_cue_id(self.cue_id)
        except Exception as error:
            raise StatefulASRQualityReviewCleanError(
                "CLEAN cue identity is not a sparse ASR identity"
            ) from error
        if (
            type(self.original_source_index) is not int
            or not 0 <= self.original_source_index < MAX_ASR_SEGMENTS
            or resolved != self.original_source_index
        ):
            raise StatefulASRQualityReviewCleanError(
                "CLEAN ASR source identity differs from cue ID"
            )
        if self.review_action not in {KEEP, REPAIR, AMBIGUOUS}:
            raise StatefulASRQualityReviewCleanError(
                "CLEAN ASR cue has an unsupported retained action"
            )
        if type(self.ja) is not str or type(self.ko) is not str:
            raise StatefulASRQualityReviewCleanError(
                "CLEAN ASR text must use exact strings"
            )
        try:
            SubtitleCue(self.start_ms, self.end_ms, self.ja)
            SubtitleCue(self.start_ms, self.end_ms, self.ko)
        except Exception as error:
            raise StatefulASRQualityReviewCleanError(
                "CLEAN ASR cue text or timing is invalid"
            ) from error


@dataclass(frozen=True)
class StatefulASRQualityReviewCleanMaterialization:
    cues: tuple[ASRQualityReviewCleanCue, ...]
    artifact: GeneratedKoreanSRT

    def __post_init__(self):
        if type(self.cues) is not tuple:
            raise StatefulASRQualityReviewCleanError(
                "CLEAN ASR cues must be an immutable tuple"
            )
        previous = None
        rendered = []
        for cue in self.cues:
            if type(cue) is not ASRQualityReviewCleanCue:
                raise StatefulASRQualityReviewCleanError(
                    "CLEAN ASR cues contain an invalid value"
                )
            cue.__post_init__()
            if previous is not None and cue.original_source_index <= previous:
                raise StatefulASRQualityReviewCleanError(
                    "CLEAN ASR cues differ from original source order"
                )
            previous = cue.original_source_index
            rendered.append(SubtitleCue(cue.start_ms, cue.end_ms, cue.ko))
        if type(self.artifact) is not GeneratedKoreanSRT:
            raise StatefulASRQualityReviewCleanError(
                "CLEAN ASR artifact has the wrong exact type"
            )
        try:
            self.artifact.__post_init__()
            expected = generate_korean_srt(tuple(rendered))
        except Exception as error:
            raise StatefulASRQualityReviewCleanError(
                "CLEAN ASR SRT artifact is invalid"
            ) from error
        if self.artifact != expected:
            raise StatefulASRQualityReviewCleanError(
                "CLEAN ASR SRT differs from deterministic cue rendering"
            )

    @property
    def source_indexes(self) -> tuple[int, ...]:
        return tuple(cue.original_source_index for cue in self.cues)


def materialize_stateful_asr_quality_review_clean(
    package: StatefulSubtitlePackage,
    first_pass_result: StatefulSubtitleResult,
    asr_result: ASRResult,
    review_request: ASRQualityReviewRequest,
    review_result: QualityReviewResult,
    *,
    targeted_second_evidence_artifact: (
        TargetedSecondEvidenceArtifact | None
    ) = None,
) -> StatefulASRQualityReviewCleanMaterialization:
    """Apply review actions while retaining original ASR timing ownership."""

    try:
        if type(package) is not StatefulSubtitlePackage or type(asr_result) is not ASRResult:
            raise StatefulASRQualityReviewCleanError("exact ASR CLEAN originals are required")
        package.__post_init__()
        asr_result.__post_init__()
        first_pass = validate_stateful_result(first_pass_result, package)
        request = validate_asr_quality_review_request(
            review_request,
            asr_result=asr_result,
            package=package,
            result=first_pass,
            targeted_second_evidence_artifact=(
                targeted_second_evidence_artifact
            ),
        )
        result = validate_asr_quality_review_result(review_result, request)
        if package.dvd_id != asr_result.source_snapshot.dvd_id:
            raise StatefulASRQualityReviewCleanError(
                "ASR CLEAN timing belongs to another DVD-ID"
            )

        clean_cues = []
        previous_source_index = None
        previous_start_ms = None
        for source, first, review_input, decision in zip(
            package.cues,
            first_pass.cues,
            request.cues,
            result.cues,
            strict=True,
        ):
            source_index = source_index_for_asr_cue_id(source.cue_id)
            if (
                source_index >= len(asr_result.segments)
                or previous_source_index is not None
                and source_index <= previous_source_index
                or first.cue_id != source.cue_id
                or review_input.cue_id != source.cue_id
                or decision.cue_id != source.cue_id
                or review_input.source_index != source_index
                or review_input.stt_ja != source.stt_ja
                or review_input.first_pass_repaired_ja != first.repaired_ja
                or review_input.first_pass_ko != first.ko
            ):
                raise StatefulASRQualityReviewCleanError(
                    "ASR FULL, review, and source cue identity differ"
                )
            segment = asr_result.segments[source_index]
            if source.external_ja is not None or source.stt_ja != segment.text:
                raise StatefulASRQualityReviewCleanError(
                    "ASR source text is detached from timing evidence"
                )
            if previous_start_ms is not None and segment.start_ms < previous_start_ms:
                raise StatefulASRQualityReviewCleanError(
                    "ASR CLEAN timing is not source ordered"
                )
            previous_source_index = source_index
            previous_start_ms = segment.start_ms

            effective_action = effective_review_action(review_input, decision)
            if effective_action == OMIT:
                continue
            if effective_action == REPAIR:
                ja = decision.replacement_ja
                ko = decision.replacement_ko
            elif effective_action == KEEP:
                ja = first.repaired_ja if first.repaired_ja is not None else source.stt_ja
                ko = first.ko
            else:
                raise StatefulASRQualityReviewCleanError(
                    "validated ASR review action is unsupported"
                )
            clean_cues.append(
                ASRQualityReviewCleanCue(
                    cue_id=source.cue_id,
                    original_source_index=source_index,
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    ja=ja,
                    ko=ko,
                    review_action=decision.action,
                )
            )

        rendered = generate_korean_srt(
            tuple(SubtitleCue(cue.start_ms, cue.end_ms, cue.ko) for cue in clean_cues)
        )
        return StatefulASRQualityReviewCleanMaterialization(
            cues=tuple(clean_cues),
            artifact=rendered,
        )
    except StatefulASRQualityReviewCleanError:
        raise
    except Exception as error:
        raise StatefulASRQualityReviewCleanError(
            "ASR CLEAN materialization failed original-evidence validation"
        ) from error


__all__ = [
    "ASRQualityReviewCleanCue",
    "StatefulASRQualityReviewCleanError",
    "StatefulASRQualityReviewCleanMaterialization",
    "materialize_stateful_asr_quality_review_clean",
]
