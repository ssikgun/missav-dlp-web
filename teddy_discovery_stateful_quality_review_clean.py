"""Pure deterministic CLEAN playback materialization from FULL plus review.

The first-pass package/result remain immutable audit artifacts.  This module
revalidates the caller-held quality-review request and result, applies only
their existing semantic decisions, and uses the frozen HYBRID preparation as
the sole timing authority.  It performs no model, filesystem, database, or
network work.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from teddy_discovery_hybrid_evidence import HybridCueIdentity
from teddy_discovery_ko_srt import GeneratedKoreanSRT, generate_korean_srt
from teddy_discovery_stateful_hybrid import StatefulHybridPreparation
from teddy_discovery_stateful_quality_review import (
    AMBIGUOUS,
    KEEP,
    OMIT,
    REPAIR,
    QualityReviewRequest,
    QualityReviewResult,
    effective_review_action,
    validate_review_request,
    validate_review_result,
)
from teddy_discovery_stateful_translator import (
    STATEFUL_TRANSLATOR_MAX_CUES,
    StatefulSubtitlePackage,
    StatefulSubtitleResult,
    validate_stateful_result,
)
from teddy_discovery_subtitle_source_quality import SourceQualityDecision
from teddy_discovery_subtitle_text import SubtitleCue
from teddy_discovery_subtitle_v2_orchestrator import project_affine_timestamp_ms
from teddy_discovery_targeted_asr_artifact import TargetedASRArtifact
from teddy_discovery_targeted_second_evidence_artifact import (
    TargetedSecondEvidenceArtifact,
)


class StatefulQualityReviewCleanError(ValueError):
    """Original evidence or deterministic CLEAN output failed closed."""


@dataclass(frozen=True)
class CleanSubtitleCue:
    """One retained playback cue with original identity and projected timing."""

    cue_id: str
    original_source_index: int
    start_ms: int
    end_ms: int
    ja: str
    ko: str
    review_action: str

    def __post_init__(self):
        if (
            type(self.original_source_index) is not int
            or not 0 <= self.original_source_index < STATEFUL_TRANSLATOR_MAX_CUES
        ):
            raise StatefulQualityReviewCleanError(
                "CLEAN original_source_index is invalid"
            )
        try:
            identity = HybridCueIdentity.for_external_ja(
                self.original_source_index
            )
        except Exception as error:
            raise StatefulQualityReviewCleanError(
                "CLEAN source identity is invalid"
            ) from error
        if type(self.cue_id) is not str or self.cue_id != identity.cue_id:
            raise StatefulQualityReviewCleanError(
                "CLEAN cue identity differs from its original source index"
            )
        if (
            type(self.review_action) is not str
            or self.review_action not in {KEEP, REPAIR, AMBIGUOUS}
        ):
            raise StatefulQualityReviewCleanError(
                "CLEAN cue has an unsupported retained action"
            )
        if type(self.ja) is not str or type(self.ko) is not str:
            raise StatefulQualityReviewCleanError(
                "CLEAN text must use exact strings"
            )
        try:
            SubtitleCue(self.start_ms, self.end_ms, self.ja)
            SubtitleCue(self.start_ms, self.end_ms, self.ko)
        except Exception as error:
            raise StatefulQualityReviewCleanError(
                "CLEAN cue text or timing is invalid"
            ) from error


@dataclass(frozen=True)
class StatefulQualityReviewCleanMaterialization:
    """Immutable CLEAN cue data and its canonical Korean SRT rendering."""

    cues: tuple[CleanSubtitleCue, ...]
    artifact: GeneratedKoreanSRT

    def __post_init__(self):
        if type(self.cues) is not tuple:
            raise StatefulQualityReviewCleanError(
                "CLEAN cues must be an immutable tuple"
            )
        previous_source_index = None
        rendered_cues = []
        for cue in self.cues:
            if type(cue) is not CleanSubtitleCue:
                raise StatefulQualityReviewCleanError(
                    "CLEAN cues contain an invalid value"
                )
            cue.__post_init__()
            if (
                previous_source_index is not None
                and cue.original_source_index <= previous_source_index
            ):
                raise StatefulQualityReviewCleanError(
                    "CLEAN cues differ from original source order"
                )
            previous_source_index = cue.original_source_index
            rendered_cues.append(
                SubtitleCue(cue.start_ms, cue.end_ms, cue.ko)
            )
        if type(self.artifact) is not GeneratedKoreanSRT:
            raise StatefulQualityReviewCleanError(
                "CLEAN artifact has the wrong exact type"
            )
        try:
            self.artifact.__post_init__()
            expected = generate_korean_srt(tuple(rendered_cues))
        except Exception as error:
            raise StatefulQualityReviewCleanError(
                "CLEAN SRT artifact is invalid"
            ) from error
        if self.artifact != expected:
            raise StatefulQualityReviewCleanError(
                "CLEAN SRT differs from deterministic cue rendering"
            )

    @property
    def source_indexes(self) -> tuple[int, ...]:
        return tuple(cue.original_source_index for cue in self.cues)


def materialize_stateful_quality_review_clean(
    package: StatefulSubtitlePackage,
    first_pass_result: StatefulSubtitleResult,
    preparation: StatefulHybridPreparation,
    review_request: QualityReviewRequest,
    review_result: QualityReviewResult,
    *,
    source_quality: tuple[SourceQualityDecision, ...],
    raw_asr_context: Mapping[str, tuple[str, ...]] | None = None,
    proximity_asr_artifact: TargetedASRArtifact | None = None,
    targeted_second_evidence_artifact: (
        TargetedSecondEvidenceArtifact | None
    ) = None,
) -> StatefulQualityReviewCleanMaterialization:
    """Revalidate FULL and review evidence, then apply decisions without I/O.

    KEEP and AMBIGUOUS retain first-pass semantics, REPAIR uses both validated
    replacements, and OMIT is absent only from the returned CLEAN data.  Every
    source cue is still timing-validated before an OMIT decision is applied.
    """

    try:
        if type(preparation) is not StatefulHybridPreparation:
            raise StatefulQualityReviewCleanError(
                "original HYBRID preparation is required"
            )
        preparation.__post_init__()
        if type(package) is not StatefulSubtitlePackage:
            raise StatefulQualityReviewCleanError(
                "original stateful package is required"
            )
        package.__post_init__()
        if package != preparation.package:
            raise StatefulQualityReviewCleanError(
                "package differs from original HYBRID preparation"
            )
        first_pass = validate_stateful_result(first_pass_result, package)
        request = validate_review_request(
            review_request,
            preparation=preparation,
            package=package,
            result=first_pass,
            source_quality=source_quality,
            raw_asr_context=raw_asr_context,
            proximity_asr_artifact=proximity_asr_artifact,
            targeted_second_evidence_artifact=(
                targeted_second_evidence_artifact
            ),
        )
        result = validate_review_result(review_result, request)

        application = preparation.route_decision.alignment_application
        if application is None or application.alignment is None:
            raise StatefulQualityReviewCleanError(
                "frozen HYBRID timing authority is missing"
            )
        document = application.bundle.external_ja_document
        if document is None:
            raise StatefulQualityReviewCleanError(
                "frozen external timing source is missing"
            )

        clean_cues = []
        previous_start_ms = None
        values = zip(
            package.cues,
            first_pass.cues,
            preparation.semantic_bindings,
            request.cues,
            result.cues,
            document.cues,
            strict=True,
        )
        for source_index, (
            source,
            first,
            binding,
            review_input,
            decision,
            external,
        ) in enumerate(values):
            identity = HybridCueIdentity.for_external_ja(source_index)
            if (
                source.cue_id != identity.cue_id
                or first.cue_id != identity.cue_id
                or binding.request_cue_id != identity.cue_id
                or binding.external_ja_identity != identity
                or binding.source_index != source_index
                or review_input.cue_id != identity.cue_id
                or review_input.source_index != source_index
                or decision.cue_id != identity.cue_id
                or source.external_ja != external.text
                or review_input.external_ja != source.external_ja
                or review_input.accepted_stt_ja != source.stt_ja
                or review_input.first_pass_repaired_ja != first.repaired_ja
                or review_input.first_pass_ko != first.ko
            ):
                raise StatefulQualityReviewCleanError(
                    "FULL, review, and source cue identity differ"
                )

            start_ms = project_affine_timestamp_ms(
                application.alignment, external.start_ms
            )
            end_ms = project_affine_timestamp_ms(
                application.alignment, external.end_ms
            )
            if (
                end_ms <= start_ms
                or (
                    previous_start_ms is not None
                    and start_ms < previous_start_ms
                )
            ):
                raise StatefulQualityReviewCleanError(
                    "frozen projected timing is invalid"
                )
            previous_start_ms = start_ms

            effective_action = effective_review_action(review_input, decision)
            if effective_action == OMIT:
                continue
            if effective_action == REPAIR:
                ja = decision.replacement_ja
                ko = decision.replacement_ko
            elif effective_action == KEEP:
                ja = (
                    first.repaired_ja
                    if first.repaired_ja is not None
                    else source.external_ja
                )
                ko = first.ko
            else:
                raise StatefulQualityReviewCleanError(
                    "validated review action is unsupported"
                )
            clean_cues.append(
                CleanSubtitleCue(
                    cue_id=identity.cue_id,
                    original_source_index=source_index,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    ja=ja,
                    ko=ko,
                    review_action=decision.action,
                )
            )

        rendered = generate_korean_srt(
            tuple(
                SubtitleCue(cue.start_ms, cue.end_ms, cue.ko)
                for cue in clean_cues
            )
        )
        return StatefulQualityReviewCleanMaterialization(
            cues=tuple(clean_cues),
            artifact=rendered,
        )
    except StatefulQualityReviewCleanError:
        raise
    except Exception as error:
        raise StatefulQualityReviewCleanError(
            "CLEAN materialization failed original-evidence validation"
        ) from error


__all__ = [
    "CleanSubtitleCue",
    "StatefulQualityReviewCleanError",
    "StatefulQualityReviewCleanMaterialization",
    "materialize_stateful_quality_review_clean",
]
