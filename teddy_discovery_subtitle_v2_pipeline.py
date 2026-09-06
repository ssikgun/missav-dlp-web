"""Offline-composable Stage11 v2 per-title execution boundary.

This module composes the frozen R5 route, semantic, source-timing, and
generated-artifact contracts for one title.  All effectful boundaries are
injected by the caller; this module does not discover sources, run ASR,
invoke Hermes transport, publish, or perform I/O.
"""

from __future__ import annotations

from collections.abc import Callable

from teddy_discovery_alignment import RobustAffineAlignment
from teddy_discovery_asr import ASRSegment
from teddy_discovery_hermes_v2 import (
    HermesV2CueInput,
    HermesV2Request,
    HermesV2Result,
    validate_hermes_v2_result,
)
from teddy_discovery_hybrid_evidence import (
    EVIDENCE_SOURCE_ASR_SEGMENT,
    EVIDENCE_SOURCE_EXTERNAL_JA,
    NEIGHBOR_SOURCE_ASR_SEGMENT,
    NEIGHBOR_SOURCE_ASR_WORD,
    NEIGHBOR_SOURCE_EXTERNAL_EN,
    NEIGHBOR_SOURCE_EXTERNAL_JA,
    HybridCueEvidence,
    HybridCueIdentity,
    HybridEvidenceBundle,
    HybridNeighborReference,
    stable_cue_id,
)
from teddy_discovery_ko_srt import (
    GENERATED_SRT_READY,
    GeneratedKoreanSRT,
    generate_korean_srt,
)
from teddy_discovery_subtitle_text import SubtitleCue
from teddy_discovery_subtitle_v2_orchestrator import (
    V2_FAILED_CLOSED,
    V2_READY_FOR_SEMANTIC,
    V2_READY_TO_PUBLISH,
    V2_ROUTE_ASR_ONLY,
    V2_ROUTE_EXISTING_KO,
    V2_ROUTE_HYBRID,
    V2_ROUTE_LOCAL_JA,
    V2_ROUTE_UNRESOLVED,
    V2_TERMINAL_EXISTING_KO,
    SubtitleV2OrchestratorError,
    SubtitleV2OutputCue,
    SubtitleV2PrePublishResult,
    SubtitleV2RouteDecision,
    SubtitleV2SemanticBinding,
    SubtitleV2SemanticPlan,
    SubtitleV2SemanticResult,
    project_affine_timestamp_ms,
    validate_subtitle_v2_route_decision,
)


class SubtitleV2PipelineError(ValueError):
    """Base class for v2 execution-boundary failures."""


class SubtitleV2PipelineValidationError(SubtitleV2PipelineError):
    """Raised for invalid route, source, or injected-boundary input."""


class SubtitleV2PipelineBoundaryError(SubtitleV2PipelineError):
    """Raised when an injected semantic boundary violates its contract."""


def _validated_route(value: object) -> SubtitleV2RouteDecision:
    try:
        return validate_subtitle_v2_route_decision(value)
    except Exception as error:
        raise SubtitleV2PipelineValidationError(
            "route decision is invalid or detached"
        ) from error


def _reference_text(
    bundle: HybridEvidenceBundle,
    reference: HybridNeighborReference,
) -> str:
    if not isinstance(reference, HybridNeighborReference):
        raise SubtitleV2PipelineValidationError(
            "R2 context contains an invalid neighbor reference"
        )

    if reference.source == NEIGHBOR_SOURCE_EXTERNAL_JA:
        document = bundle.external_ja_document
        if document is None or reference.index >= len(document.cues):
            raise SubtitleV2PipelineValidationError(
                "R2 context points outside external JA evidence"
            )
        return document.cues[reference.index].text

    if reference.source == NEIGHBOR_SOURCE_EXTERNAL_EN:
        document = bundle.external_en_document
        if document is None or reference.index >= len(document.cues):
            raise SubtitleV2PipelineValidationError(
                "R2 context points outside external EN evidence"
            )
        return document.cues[reference.index].text

    if reference.index >= len(bundle.asr_result.segments):
        raise SubtitleV2PipelineValidationError(
            "R2 context points outside ASR evidence"
        )

    segment = bundle.asr_result.segments[reference.index]
    if reference.source == NEIGHBOR_SOURCE_ASR_SEGMENT:
        return segment.text
    if reference.source == NEIGHBOR_SOURCE_ASR_WORD:
        if reference.subindex is None or reference.subindex >= len(segment.words):
            raise SubtitleV2PipelineValidationError(
                "R2 context points outside ASR word evidence"
            )
        return segment.words[reference.subindex].text

    raise SubtitleV2PipelineValidationError(
        "R2 context source is unsupported"
    )


def _context_values(
    bundle: HybridEvidenceBundle,
    references: tuple[HybridNeighborReference, ...],
) -> tuple[str, ...]:
    if type(references) is not tuple:
        raise SubtitleV2PipelineValidationError(
            "R2 context references must remain an immutable tuple"
        )
    return tuple(_reference_text(bundle, reference) for reference in references)


def _supporting_en(
    bundle: HybridEvidenceBundle,
    evidence: HybridCueEvidence,
) -> str | None:
    """Return EN only when one bounded R2 reference identifies it unambiguously."""

    references = evidence.before_context + evidence.after_context
    en_references = tuple(
        reference
        for reference in references
        if reference.source == NEIGHBOR_SOURCE_EXTERNAL_EN
    )
    if len(en_references) != 1:
        return None
    return _reference_text(bundle, en_references[0])


def _local_context(
    cues: tuple[SubtitleCue, ...],
    index: int,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    before = (cues[index - 1].text,) if index else ()
    after = (cues[index + 1].text,) if index + 1 < len(cues) else ()
    return before, after


def _asr_bundle(route_decision: SubtitleV2RouteDecision) -> HybridEvidenceBundle:
    if route_decision.route == V2_ROUTE_HYBRID:
        application = route_decision.alignment_application
        if application is None:
            raise SubtitleV2PipelineValidationError(
                "hybrid route has no accepted R3 evidence"
            )
        return application.bundle

    if route_decision.route == V2_ROUTE_ASR_ONLY:
        if route_decision.alignment_application is not None:
            return route_decision.alignment_application.bundle
        if route_decision.evidence_bundle is not None:
            return route_decision.evidence_bundle

    raise SubtitleV2PipelineValidationError(
        "route has no ASR-backed evidence"
    )


def _validated_alignment(value: object) -> RobustAffineAlignment:
    if not isinstance(value, RobustAffineAlignment):
        raise SubtitleV2PipelineValidationError(
            "HYBRID route has no accepted RobustAffineAlignment"
        )
    try:
        return RobustAffineAlignment(
            scale=value.scale,
            intercept_ms=value.intercept_ms,
            anchor_count=value.anchor_count,
            inlier_count=value.inlier_count,
            residual_threshold_ms=value.residual_threshold_ms,
            residuals=value.residuals,
            median_absolute_residual_ms=value.median_absolute_residual_ms,
        )
    except (AttributeError, TypeError, ValueError, OverflowError) as error:
        raise SubtitleV2PipelineValidationError(
            "HYBRID alignment evidence is invalid or detached"
        ) from error


def _build_local_plan(
    route_decision: SubtitleV2RouteDecision,
) -> SubtitleV2SemanticPlan:
    document = route_decision.source_document
    if document is None:
        raise SubtitleV2PipelineValidationError(
            "local JA route has no parsed source document"
        )

    request_cues: list[HermesV2CueInput] = []
    bindings: list[SubtitleV2SemanticBinding] = []
    for index, source_cue in enumerate(document.cues):
        cue_id = stable_cue_id(EVIDENCE_SOURCE_EXTERNAL_JA, index)
        before_context, after_context = _local_context(document.cues, index)
        request_cues.append(
            HermesV2CueInput(
                cue_id=cue_id,
                external_ja=source_cue.text,
                stt_ja=None,
                en=None,
                before_context=before_context,
                after_context=after_context,
            )
        )
        bindings.append(
            SubtitleV2SemanticBinding(
                request_cue_id=cue_id,
                source_index=index,
            )
        )

    try:
        request = HermesV2Request(cues=tuple(request_cues))
        return SubtitleV2SemanticPlan(
            route_decision=route_decision,
            hermes_request=request,
            semantic_bindings=tuple(bindings),
        )
    except Exception as error:
        raise SubtitleV2PipelineValidationError(
            "local JA semantic request could not be built"
        ) from error


def _build_asr_plan(
    route_decision: SubtitleV2RouteDecision,
) -> SubtitleV2SemanticPlan:
    bundle = _asr_bundle(route_decision)
    request_cues: list[HermesV2CueInput] = []
    bindings: list[SubtitleV2SemanticBinding] = []

    for evidence in bundle.cue_evidence:
        if evidence.identity.source != EVIDENCE_SOURCE_ASR_SEGMENT:
            raise SubtitleV2PipelineValidationError(
                "ASR-only evidence does not contain ASR identities"
            )
        index = evidence.identity.source_index
        segment = bundle.asr_result.segments[index]
        request_cues.append(
            HermesV2CueInput(
                cue_id=evidence.identity.cue_id,
                external_ja=None,
                stt_ja=segment.text,
                en=_supporting_en(bundle, evidence),
                before_context=_context_values(bundle, evidence.before_context),
                after_context=_context_values(bundle, evidence.after_context),
            )
        )
        bindings.append(
            SubtitleV2SemanticBinding(
                request_cue_id=evidence.identity.cue_id,
                source_index=index,
                asr_identity=evidence.identity,
            )
        )

    try:
        request = HermesV2Request(cues=tuple(request_cues))
        return SubtitleV2SemanticPlan(
            route_decision=route_decision,
            hermes_request=request,
            semantic_bindings=tuple(bindings),
        )
    except Exception as error:
        raise SubtitleV2PipelineValidationError(
            "ASR-only semantic request could not be built"
        ) from error


def _build_hybrid_plan(
    route_decision: SubtitleV2RouteDecision,
) -> SubtitleV2SemanticPlan:
    bundle = _asr_bundle(route_decision)
    application = route_decision.alignment_application
    if application is None:
        raise SubtitleV2PipelineValidationError(
            "hybrid route has no alignment application"
        )
    alignment = _validated_alignment(application.alignment)
    document = bundle.external_ja_document
    if bundle.external_ja_payload is None or document is None:
        raise SubtitleV2PipelineValidationError(
            "hybrid route has no parsed external JA evidence"
        )

    request_cues: list[HermesV2CueInput] = []
    bindings: list[SubtitleV2SemanticBinding] = []
    residuals_by_external_index = {
        residual.external_identity.source_index: residual
        for residual in alignment.residuals
    }
    for residual in alignment.residuals:
        external_index = residual.external_identity.source_index
        asr_index = residual.asr_identity.source_index
        if external_index >= len(document.cues):
            raise SubtitleV2PipelineValidationError(
                "hybrid residual external identity is outside source evidence"
            )
        if (
            bundle.cue_evidence[external_index].identity
            != residual.external_identity
        ):
            raise SubtitleV2PipelineValidationError(
                "hybrid residual external identity is detached"
            )
        if asr_index >= len(bundle.asr_result.segments):
            raise SubtitleV2PipelineValidationError(
                "hybrid residual ASR identity is outside the ASR result"
            )
        if residual.asr_identity != HybridCueIdentity.for_asr_segment(asr_index):
            raise SubtitleV2PipelineValidationError(
                "hybrid residual ASR identity is not source-stable"
            )
    for external_index, evidence in enumerate(bundle.cue_evidence):
        if evidence.identity.source != EVIDENCE_SOURCE_EXTERNAL_JA:
            raise SubtitleV2PipelineValidationError(
                "hybrid evidence does not contain external JA identities"
            )
        if evidence.identity.source_index != external_index:
            raise SubtitleV2PipelineValidationError(
                "hybrid external JA identity is detached from source order"
            )
        residual = residuals_by_external_index.get(external_index)
        asr_identity = None
        stt_ja = None
        if residual is not None:
            if residual.external_identity != evidence.identity:
                raise SubtitleV2PipelineValidationError(
                    "hybrid residual external identity is detached"
                )
            asr_identity = residual.asr_identity
            if asr_identity.source_index >= len(bundle.asr_result.segments):
                raise SubtitleV2PipelineValidationError(
                    "hybrid residual ASR identity is outside the ASR result"
                )
            if asr_identity != HybridCueIdentity.for_asr_segment(
                asr_identity.source_index
            ):
                raise SubtitleV2PipelineValidationError(
                    "hybrid residual ASR identity is not source-stable"
                )
            stt_ja = bundle.asr_result.segments[asr_identity.source_index].text
        request_cues.append(
            HermesV2CueInput(
                cue_id=evidence.identity.cue_id,
                external_ja=document.cues[external_index].text,
                stt_ja=stt_ja,
                en=_supporting_en(bundle, evidence),
                before_context=_context_values(bundle, evidence.before_context),
                after_context=_context_values(bundle, evidence.after_context),
            )
        )
        bindings.append(
            SubtitleV2SemanticBinding(
                request_cue_id=evidence.identity.cue_id,
                source_index=external_index,
                external_ja_identity=evidence.identity,
                asr_identity=asr_identity,
            )
        )

    try:
        request = HermesV2Request(cues=tuple(request_cues))
        return SubtitleV2SemanticPlan(
            route_decision=route_decision,
            hermes_request=request,
            semantic_bindings=tuple(bindings),
        )
    except Exception as error:
        raise SubtitleV2PipelineValidationError(
            "hybrid semantic request could not be built"
        ) from error


def _build_semantic_plan(
    route_decision: SubtitleV2RouteDecision,
) -> SubtitleV2SemanticPlan:
    if route_decision.route == V2_ROUTE_LOCAL_JA:
        return _build_local_plan(route_decision)

    if route_decision.route == V2_ROUTE_ASR_ONLY:
        return _build_asr_plan(route_decision)

    if route_decision.route == V2_ROUTE_HYBRID:
        return _build_hybrid_plan(route_decision)

    raise SubtitleV2PipelineValidationError(
        "route does not require semantic work"
    )


def _call_semantic_boundary(
    semantic_boundary: object,
    request: HermesV2Request,
) -> HermesV2Result:
    if not callable(semantic_boundary):
        raise SubtitleV2PipelineValidationError(
            "semantic_boundary must be callable for semantic routes"
        )
    try:
        result = semantic_boundary(request)
    except Exception as error:
        raise SubtitleV2PipelineBoundaryError(
            "semantic boundary execution failed"
        ) from error

    if not isinstance(result, HermesV2Result):
        raise SubtitleV2PipelineBoundaryError(
            "semantic boundary returned an invalid result type"
        )
    return result


def _validated_semantic_result(
    plan: SubtitleV2SemanticPlan,
    result: HermesV2Result,
) -> SubtitleV2SemanticResult:
    try:
        validate_hermes_v2_result(result, plan.hermes_request)
        return SubtitleV2SemanticResult(
            semantic_plan=plan,
            hermes_result=result,
        )
    except Exception as error:
        raise SubtitleV2PipelineBoundaryError(
            "semantic boundary result failed exact cue validation"
        ) from error


def _timing_pairs(
    route_decision: SubtitleV2RouteDecision,
    plan: SubtitleV2SemanticPlan,
) -> tuple[tuple[int, SubtitleCue | ASRSegment], ...]:
    if route_decision.route == V2_ROUTE_LOCAL_JA:
        document = route_decision.source_document
        if document is None:
            raise SubtitleV2PipelineValidationError(
                "local JA route has no deterministic timing source"
            )
        return tuple(
            (binding.source_index, document.cues[binding.source_index])
            for binding in plan.semantic_bindings
        )

    if route_decision.route == V2_ROUTE_HYBRID:
        bundle = _asr_bundle(route_decision)
        application = route_decision.alignment_application
        if application is None:
            raise SubtitleV2PipelineValidationError(
                "hybrid route has no alignment application"
            )
        alignment = _validated_alignment(application.alignment)
        document = bundle.external_ja_document
        if document is None:
            raise SubtitleV2PipelineValidationError(
                "hybrid route has no external JA timing source"
            )

        pairs: list[tuple[int, SubtitleCue]] = []
        previous_start_ms = None
        for binding in plan.semantic_bindings:
            source_cue = document.cues[binding.source_index]
            projected_start_ms = project_affine_timestamp_ms(
                alignment,
                source_cue.start_ms,
            )
            projected_end_ms = project_affine_timestamp_ms(
                alignment,
                source_cue.end_ms,
            )
            if (
                previous_start_ms is not None
                and projected_start_ms < previous_start_ms
            ):
                raise SubtitleV2PipelineValidationError(
                    "projected HYBRID cue starts are decreasing"
                )
            previous_start_ms = projected_start_ms
            try:
                projected_cue = SubtitleCue(
                    start_ms=projected_start_ms,
                    end_ms=projected_end_ms,
                    text=source_cue.text,
                )
            except Exception as error:
                raise SubtitleV2PipelineValidationError(
                    "projected HYBRID cue interval is invalid"
                ) from error
            pairs.append((binding.source_index, projected_cue))
        return tuple(pairs)

    bundle = _asr_bundle(route_decision)
    pairs: list[tuple[int, SubtitleCue | ASRSegment]] = []
    for binding in plan.semantic_bindings:
        if binding.asr_identity is None:
            raise SubtitleV2PipelineValidationError(
                "ASR-backed semantic binding has no deterministic timing identity"
            )
        index = binding.asr_identity.source_index
        segment = bundle.asr_result.segments[index]
        pairs.append((index, segment))
    return tuple(pairs)


def _build_pre_publish_result(
    route_decision: SubtitleV2RouteDecision,
    semantic_result: SubtitleV2SemanticResult,
) -> SubtitleV2PrePublishResult:
    timing_pairs = _timing_pairs(
        route_decision,
        semantic_result.semantic_plan,
    )
    result_cues = semantic_result.hermes_result.cues
    if len(timing_pairs) != len(result_cues):
        raise SubtitleV2PipelineValidationError(
            "semantic result and deterministic timing counts differ"
        )

    output_cues: list[SubtitleV2OutputCue] = []
    artifact_cues: list[SubtitleCue] = []
    previous_source_index = None
    for result_cue, (source_index, timing_cue) in zip(
        result_cues,
        timing_pairs,
    ):
        if (
            previous_source_index is not None
            and source_index <= previous_source_index
        ):
            raise SubtitleV2PipelineValidationError(
                "deterministic output timing indexes are not strictly ordered"
            )
        previous_source_index = source_index
        output_cues.append(
            SubtitleV2OutputCue(
                cue_id=result_cue.cue_id,
                source_index=source_index,
                timing_evidence=timing_cue,
            )
        )
        artifact_cues.append(
            SubtitleCue(
                start_ms=timing_cue.start_ms,
                end_ms=timing_cue.end_ms,
                text=result_cue.ko,
            )
        )

    try:
        artifact = generate_korean_srt(tuple(artifact_cues))
        if not isinstance(artifact, GeneratedKoreanSRT):
            raise SubtitleV2PipelineBoundaryError(
                "generated artifact builder returned an invalid type"
            )
        if artifact.state != GENERATED_SRT_READY:
            raise SubtitleV2PipelineBoundaryError(
                "semantic result did not produce a ready artifact"
            )
        return SubtitleV2PrePublishResult(
            route_decision=route_decision,
            state=V2_READY_TO_PUBLISH,
            semantic_result=semantic_result,
            output_cues=tuple(output_cues),
            artifact=artifact,
        )
    except SubtitleV2PipelineError:
        raise
    except Exception as error:
        raise SubtitleV2PipelineBoundaryError(
            "generated artifact failed deterministic validation"
        ) from error


def run_subtitle_v2_pipeline(
    route_decision: SubtitleV2RouteDecision,
    *,
    semantic_boundary: Callable[[HermesV2Request], HermesV2Result] | None = None,
) -> SubtitleV2PrePublishResult:
    """Execute one already-decided v2 route using injected semantic work."""

    route = _validated_route(route_decision)

    if route.route == V2_ROUTE_EXISTING_KO:
        return SubtitleV2PrePublishResult(
            route_decision=route,
            state=V2_TERMINAL_EXISTING_KO,
        )

    if route.route == V2_ROUTE_UNRESOLVED:
        return SubtitleV2PrePublishResult(
            route_decision=route,
            state=V2_FAILED_CLOSED,
        )

    plan = _build_semantic_plan(route)
    result = _call_semantic_boundary(
        semantic_boundary,
        plan.hermes_request,
    )
    semantic_result = _validated_semantic_result(plan, result)
    return _build_pre_publish_result(route, semantic_result)


__all__ = [
    "SubtitleV2PipelineBoundaryError",
    "SubtitleV2PipelineError",
    "SubtitleV2PipelineValidationError",
    "project_affine_timestamp_ms",
    "run_subtitle_v2_pipeline",
]
