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

from teddy_discovery_semantic_text import project_semantic_text
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
    stateful_absorption_is_enabled,
    validate_stateful_result,
)
from teddy_discovery_subtitle_source_quality import OMIT_METADATA, SourceQualityDecision
from teddy_discovery_subtitle_text import SubtitleCue
from teddy_discovery_subtitle_v2_orchestrator import project_affine_timestamp_ms
from teddy_discovery_targeted_asr_artifact import TargetedASRArtifact
from teddy_discovery_targeted_second_evidence_artifact import (
    TargetedSecondEvidenceArtifact,
)
from teddy_discovery_stateful_absorption_review import (
    GROUP_REVIEW_AMBIGUOUS,
    GROUP_REVIEW_KEEP,
    GROUP_REVIEW_REPAIR,
    GROUP_REVIEW_UNSUPPORTED,
    AbsorptionGroupReviewError,
    AbsorptionGroupReviewExecutionEvidence,
    build_absorption_group_review_request,
    validate_absorption_group_review_execution,
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
    source_indexes: tuple[int, ...] = ()

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
        indexes = self.source_indexes
        if indexes == ():
            indexes = (self.original_source_index,)
            object.__setattr__(self, "source_indexes", indexes)
        if (
            type(indexes) is not tuple
            or not indexes
            or any(type(index) is not int or not 0 <= index < STATEFUL_TRANSLATOR_MAX_CUES
                   for index in indexes)
            or tuple(sorted(set(indexes))) != indexes
            or self.original_source_index not in indexes
            or indexes != tuple(range(indexes[0], indexes[-1] + 1))
        ):
            raise StatefulQualityReviewCleanError(
                "CLEAN source-index group is invalid"
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
        seen_source_indexes = set()
        rendered_cues = []
        for cue in self.cues:
            if type(cue) is not CleanSubtitleCue:
                raise StatefulQualityReviewCleanError(
                    "CLEAN cues contain an invalid value"
                )
            cue.__post_init__()
            first_source_index = cue.source_indexes[0]
            if (previous_source_index is not None
                    and first_source_index <= previous_source_index):
                raise StatefulQualityReviewCleanError(
                    "CLEAN cues differ from original source order"
                )
            previous_source_index = cue.source_indexes[-1]
            if seen_source_indexes.intersection(cue.source_indexes):
                raise StatefulQualityReviewCleanError(
                    "CLEAN source index is represented more than once"
                )
            seen_source_indexes.update(cue.source_indexes)
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
        return tuple(
            source_index
            for cue in self.cues
            for source_index in cue.source_indexes
        )


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
    absorption_group_review_execution: (
        AbsorptionGroupReviewExecutionEvidence | None
    ) = None,
    preserve_absorption: bool = False,
    omit_metadata: bool = False,
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

        clean_by_source_index = []
        projected = []
        previous_start_ms = None
        values = zip(
            package.cues,
            first_pass.cues,
            preparation.semantic_bindings,
            request.cues,
            result.cues,
            document.cues,
            source_quality,
            strict=True,
        )
        for source_index, (
            source,
            first,
            binding,
            review_input,
            decision,
            external,
            hint,
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
                or source.external_ja != project_semantic_text(external.text)
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
            projected.append((start_ms, end_ms))

            effective_action = effective_review_action(review_input, decision)
            if omit_metadata and hint.action == OMIT_METADATA:
                effective_action = OMIT
            if effective_action == OMIT:
                clean_by_source_index.append(None)
            elif decision.action == REPAIR:
                ja = decision.replacement_ja
                ko = decision.replacement_ko
                clean_by_source_index.append(
                    (ja, ko, decision.action)
                )
            elif effective_action == KEEP and decision.action == AMBIGUOUS:
                # Uncertain repairs are not promoted; retain the external JA.
                ja = source.external_ja
                ko = first.ko
                clean_by_source_index.append(
                    (ja, ko, decision.action)
                )
            elif effective_action == KEEP:
                ja = (
                    first.repaired_ja
                    if first.repaired_ja is not None
                    else source.external_ja
                )
                ko = first.ko
                clean_by_source_index.append(
                    (ja, ko, decision.action)
                )
            else:
                raise StatefulQualityReviewCleanError(
                    "validated review action is unsupported"
                )

        if preserve_absorption and stateful_absorption_is_enabled(
            package.generation_key
        ):
            try:
                from teddy_discovery_stateful_boundary import (
                    validate_stateful_absorption,
                )

                chains = validate_stateful_absorption(
                    first_pass.cues,
                    package,
                    first_pass.boundary_evidence,
                )
            except Exception as error:
                raise StatefulQualityReviewCleanError(
                    "CLEAN absorption relation failed original-evidence validation"
                ) from error
        else:
            from teddy_discovery_stateful_boundary import StatefulAbsorptionChain

            chains = tuple(
                StatefulAbsorptionChain(
                    package.cues[index].cue_id,
                    (package.cues[index].cue_id,),
                    (index,),
                )
                for index in range(len(package.cues))
            )

        group_review_request = None
        group_review_result = None
        if preserve_absorption and stateful_absorption_is_enabled(
            package.generation_key
        ):
            try:
                group_review_request = build_absorption_group_review_request(
                    preparation=preparation,
                    package=package,
                    first_pass_result=first_pass,
                    review_request=request,
                    review_result=result,
                    source_quality=source_quality,
                    raw_asr_context=raw_asr_context,
                    proximity_asr_artifact=proximity_asr_artifact,
                    targeted_second_evidence_artifact=(
                        targeted_second_evidence_artifact
                    ),
                )
            except AbsorptionGroupReviewError as error:
                reason = str(error)
                if reason == "parent review execution provenance is missing":
                    reason = "owner REPAIR lacks validated absorption-group review authority"
                if reason in {
                    "absorption group has unsupported repair or omission conflict",
                    "metadata omission conflicts with group repair",
                }:
                    reason = "review decision conflicts with a validated absorption group"
                raise StatefulQualityReviewCleanError(reason) from error
        if group_review_request is None:
            if absorption_group_review_execution is not None:
                raise StatefulQualityReviewCleanError(
                    "group review evidence has no matching repair scope"
                )
        elif absorption_group_review_execution is None:
            raise StatefulQualityReviewCleanError(
                "owner REPAIR lacks validated absorption-group review authority"
            )
        else:
            try:
                group_review_result = validate_absorption_group_review_execution(
                    absorption_group_review_execution,
                    group_review_request,
                )
            except AbsorptionGroupReviewError as error:
                raise StatefulQualityReviewCleanError(
                    "absorption group review result or completion receipt is invalid"
                ) from error

        group_decisions_by_id = {}
        group_scope_by_owner = {}
        if group_review_request is not None:
            group_scope_by_owner = {
                group.scope.owner_cue_id: group.scope
                for group in group_review_request.groups
            }
            group_decisions_by_id = {
                decision.group_id: decision
                for decision in group_review_result.decisions
            }

        clean_cues = []
        source_quality_by_index = {
            decision.source_index: decision for decision in source_quality
        }
        for chain in chains:
            indexes = chain.source_indexes
            metadata_indexes = {
                index for index in indexes
                if omit_metadata
                and source_quality_by_index[index].action == OMIT_METADATA
            }
            if metadata_indexes == set(indexes):
                continue
            if metadata_indexes:
                raise StatefulQualityReviewCleanError(
                    "metadata omission intersects a retained absorption group"
                )
            owner_index = next(
                index for index, cue in enumerate(package.cues)
                if cue.cue_id == chain.owner_cue_id
            )
            if len(indexes) > 1:
                group_actions = {
                    index: review_result.cues[index].action
                    for index in indexes
                }
                repair_indexes = {
                    index for index, action in group_actions.items()
                    if action == REPAIR
                }
                if (
                    repair_indexes
                    and (
                        repair_indexes != {owner_index}
                        or any(
                            action not in {KEEP, AMBIGUOUS}
                            for index, action in group_actions.items()
                            if index != owner_index
                        )
                    )
                ) or (
                    not repair_indexes
                    and any(
                        action not in {KEEP, AMBIGUOUS}
                        for action in group_actions.values()
                    )
                ):
                    raise StatefulQualityReviewCleanError(
                        "review decision conflicts with a validated absorption group"
                    )
                owner_value = clean_by_source_index[owner_index]
                if owner_value is None or owner_value[1] is None:
                    raise StatefulQualityReviewCleanError(
                        "reviewed absorption owner has no retained translation"
                    )
                ja, ko, action = owner_value
                if repair_indexes:
                    scope = group_scope_by_owner.get(chain.owner_cue_id)
                    if (
                        scope is None
                        or scope.cue_ids != chain.cue_ids
                        or scope.source_indexes != chain.source_indexes
                    ):
                        raise StatefulQualityReviewCleanError(
                            "validated group scope differs from absorption graph"
                        )
                    decision = group_decisions_by_id.get(scope.group_id)
                    if decision is None:
                        raise StatefulQualityReviewCleanError(
                            "owner REPAIR lacks validated absorption-group review authority"
                        )
                    if decision.action == GROUP_REVIEW_REPAIR:
                        ja, ko, action = (
                            decision.replacement_ja,
                            decision.replacement_ko,
                            REPAIR,
                        )
                    elif decision.action in {
                        GROUP_REVIEW_KEEP,
                        GROUP_REVIEW_AMBIGUOUS,
                    }:
                        owner_source = package.cues[owner_index]
                        owner_first = first_pass.cues[owner_index]
                        ja = (
                            owner_first.repaired_ja
                            if decision.action == GROUP_REVIEW_KEEP
                            and owner_first.repaired_ja is not None
                            else owner_source.external_ja
                        )
                        ko = owner_first.ko
                        action = (
                            AMBIGUOUS
                            if decision.action == GROUP_REVIEW_AMBIGUOUS
                            else KEEP
                        )
                    elif decision.action == GROUP_REVIEW_UNSUPPORTED:
                        raise StatefulQualityReviewCleanError(
                            "group review marked the absorption group unsupported"
                        )
                    else:
                        raise StatefulQualityReviewCleanError(
                            "validated group review action is unsupported"
                        )
                start_ms = min(projected[index][0] for index in indexes)
                end_ms = max(projected[index][1] for index in indexes)
                clean_cue_id = chain.owner_cue_id
            else:
                owner_value = clean_by_source_index[owner_index]
                if owner_value is None:
                    continue
                ja, ko, action = owner_value
                if ko is None:
                    raise StatefulQualityReviewCleanError(
                        "retained CLEAN cue has no Korean translation"
                    )
                start_ms, end_ms = projected[owner_index]
                clean_cue_id = package.cues[owner_index].cue_id
            clean_cues.append(
                CleanSubtitleCue(
                    cue_id=clean_cue_id,
                    original_source_index=owner_index,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    ja=ja,
                    ko=ko,
                    review_action=action,
                    source_indexes=indexes,
                )
            )

        clean_cues.sort(key=lambda cue: cue.source_indexes[0])

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
