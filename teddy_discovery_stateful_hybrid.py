"""Pure HYBRID/stateful bridge; external JA alone owns final timing.

The preparation retains immutable source proof locally. The existing stateful
serializer sends only the ordinary semantic package to the translator.
No model, storage, publication, or other I/O is owned here.
"""

from dataclasses import dataclass

from teddy_discovery_asr_source_quality import (
    ASRSourceQualityDecision,
    classify_asr_result_source_quality,
    validate_asr_source_quality_decisions,
)
from teddy_discovery_hybrid_evidence import HybridCueIdentity
from teddy_discovery_ko_srt import GeneratedKoreanSRT, generate_korean_srt
from teddy_discovery_stateful_translator import (
    STATEFUL_TRANSLATOR_SCHEMA_VERSION,
    StatefulSubtitlePackage,
    StatefulSubtitleResult,
    validate_stateful_result,
)
from teddy_discovery_subtitle_text import SubtitleCue
from teddy_discovery_subtitle_v2_orchestrator import (
    _validated_binding,
    V2_READY_FOR_SEMANTIC,
    V2_ROUTE_HYBRID,
    SubtitleV2RouteDecision,
    SubtitleV2SemanticBinding,
    project_affine_timestamp_ms,
    validate_subtitle_v2_route_decision,
)
from teddy_discovery_subtitle_v2_pipeline import _build_hybrid_cues
from teddy_discovery_targeted_hybrid_evidence import TargetedASRBinding


class StatefulHybridValidationError(Exception):
    """HYBRID semantics or their immutable timing source are detached."""


def _accepted_route(route: SubtitleV2RouteDecision) -> SubtitleV2RouteDecision:
    validated = validate_subtitle_v2_route_decision(route)
    if validated.route != V2_ROUTE_HYBRID or validated.state != V2_READY_FOR_SEMANTIC:
        raise StatefulHybridValidationError("accepted semantic-ready HYBRID route required")
    return validated


@dataclass(frozen=True)
class StatefulHybridPreparation:
    """Ordinary stateful package plus caller-retained, non-LLM source proof."""

    package: StatefulSubtitlePackage
    route_decision: SubtitleV2RouteDecision
    targeted_bindings: tuple[TargetedASRBinding, ...]
    semantic_bindings: tuple[SubtitleV2SemanticBinding, ...]
    asr_source_quality_decisions: tuple[ASRSourceQualityDecision, ...] = ()

    def __post_init__(self):
        if type(self.package) is not StatefulSubtitlePackage:
            raise StatefulHybridValidationError("ordinary stateful package required")
        StatefulSubtitlePackage(
            schema_version=self.package.schema_version,
            dvd_id=self.package.dvd_id,
            generation_key=self.package.generation_key,
            claim_token=self.package.claim_token,
            cues=self.package.cues,
        )
        if type(self.semantic_bindings) is not tuple:
            raise StatefulHybridValidationError("immutable semantic bindings required")
        for binding in self.semantic_bindings:
            _validated_binding(binding)
        route = _accepted_route(self.route_decision)
        asr_result = route.alignment_application.bundle.asr_result
        if type(self.asr_source_quality_decisions) is not tuple:
            raise StatefulHybridValidationError(
                "ASR source-quality decisions must be immutable"
            )
        if self.asr_source_quality_decisions:
            try:
                source_quality = validate_asr_source_quality_decisions(
                    asr_result.segments,
                    self.asr_source_quality_decisions,
                )
            except Exception as error:
                raise StatefulHybridValidationError(
                    "ASR source-quality decisions are invalid or detached"
                ) from error
        else:
            try:
                source_quality = classify_asr_result_source_quality(asr_result)
            except Exception as error:
                raise StatefulHybridValidationError(
                    "ASR source-quality classification failed"
                ) from error
        cues, bindings = _build_hybrid_cues(
            route,
            targeted_bindings=self.targeted_bindings,
            asr_source_quality_decisions=source_quality,
        )
        if (
            self.package.dvd_id != route.canonical_video.dvd_id
            or self.package.cues != cues
            or self.semantic_bindings != bindings
        ):
            raise StatefulHybridValidationError("package is detached from canonical HYBRID evidence")
        object.__setattr__(self, "asr_source_quality_decisions", source_quality)


def prepare_stateful_hybrid(
    route_decision: SubtitleV2RouteDecision,
    *,
    targeted_bindings: tuple[TargetedASRBinding, ...] = (),
    generation_key: str,
    claim_token: int,
) -> StatefulHybridPreparation:
    """Build all HYBRID cues and retain this preparation for finalization.

    Send only ``preparation.package`` through the existing stateful path. Keep
    the original preparation locally: a parsed semantic package alone cannot
    prove which accepted alignment and external payload supplied its timing.
    """
    route = _accepted_route(route_decision)
    source_quality = classify_asr_result_source_quality(
        route.alignment_application.bundle.asr_result
    )
    cues, bindings = _build_hybrid_cues(
        route,
        targeted_bindings=targeted_bindings,
        asr_source_quality_decisions=source_quality,
    )
    package = StatefulSubtitlePackage(
        schema_version=STATEFUL_TRANSLATOR_SCHEMA_VERSION,
        dvd_id=route.canonical_video.dvd_id,
        generation_key=generation_key,
        claim_token=claim_token,
        cues=cues,
    )
    return StatefulHybridPreparation(
        package=package,
        route_decision=route,
        targeted_bindings=targeted_bindings,
        semantic_bindings=bindings,
        asr_source_quality_decisions=source_quality,
    )


def build_stateful_hybrid_package(
    route_decision: SubtitleV2RouteDecision,
    *,
    targeted_bindings: tuple[TargetedASRBinding, ...] = (),
    generation_key: str,
    claim_token: int,
) -> StatefulSubtitlePackage:
    """Return an ordinary stateful package; use prepare to retain finalizer proof."""
    return prepare_stateful_hybrid(
        route_decision, targeted_bindings=targeted_bindings,
        generation_key=generation_key, claim_token=claim_token,
    ).package


@dataclass(frozen=True)
class StatefulHybridSRTMaterialization:
    artifact: GeneratedKoreanSRT
    source_indexes: tuple[int, ...]


def materialize_stateful_hybrid_srt(
    package: StatefulSubtitlePackage,
    result: StatefulSubtitleResult,
    route_decision: SubtitleV2RouteDecision,
    preparation: StatefulHybridPreparation,
) -> StatefulHybridSRTMaterialization:
    """Re-prove original package/source identity and project external JA timing."""
    if type(preparation) is not StatefulHybridPreparation:
        raise StatefulHybridValidationError("original HYBRID package with source proof required")
    StatefulHybridPreparation.__post_init__(preparation)
    if package != preparation.package:
        raise StatefulHybridValidationError("package differs from original preparation")
    validated_result = validate_stateful_result(result, package)
    route = _accepted_route(route_decision)
    if route != preparation.route_decision:
        raise StatefulHybridValidationError("timing route differs from original package source")
    application = route.alignment_application
    document = application.bundle.external_ja_document
    cues = []
    previous_start = None
    for index, (semantic, binding, external) in enumerate(zip(
        validated_result.cues, preparation.semantic_bindings, document.cues,
        strict=True,
    )):
        identity = HybridCueIdentity.for_external_ja(index)
        if (
            semantic.cue_id != identity.cue_id
            or binding.external_ja_identity != identity
            or binding.source_index != index
            or binding.request_cue_id != identity.cue_id
            or (binding.asr_identity is not None and binding.targeted_asr_evidence is not None)
        ):
            raise StatefulHybridValidationError("HYBRID cue identity or ownership is invalid")
        start = project_affine_timestamp_ms(application.alignment, external.start_ms)
        end = project_affine_timestamp_ms(application.alignment, external.end_ms)
        if start >= end or (previous_start is not None and start < previous_start):
            raise StatefulHybridValidationError("projected HYBRID timing is invalid")
        previous_start = start
        cues.append(SubtitleCue(start, end, semantic.ko))
    artifact = generate_korean_srt(tuple(cues))
    if artifact.cue_count != len(validated_result.cues):
        raise StatefulHybridValidationError("generated HYBRID cue count differs from result")
    return StatefulHybridSRTMaterialization(artifact, tuple(range(len(cues))))


__all__ = [
    "StatefulHybridPreparation",
    "StatefulHybridSRTMaterialization",
    "StatefulHybridValidationError",
    "build_stateful_hybrid_package",
    "materialize_stateful_hybrid_srt",
    "prepare_stateful_hybrid",
]
