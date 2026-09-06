"""Apply an alignment acceptance decision to immutable hybrid evidence.

This module is a small pure application boundary.  It preserves the existing
source-owned evidence for ACCEPT_HYBRID and UNRESOLVED, and creates the
canonical ASR-only representation only for REJECT_EXTERNAL.  It does not
publish, invoke models or ASR, modify timestamps, or perform I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import math
from types import MappingProxyType
from typing import Final

from teddy_discovery_alignment import RobustAffineAlignment
from teddy_discovery_alignment_acceptance import (
    ACCEPT_HYBRID,
    AlignmentAcceptanceDecision,
    REJECT_EXTERNAL,
    UNRESOLVED,
)
from teddy_discovery_hybrid_evidence import (
    ALIGNMENT_PROVENANCE_ASR_ONLY,
    ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
    ALIGNMENT_PROVENANCE_UNRESOLVED,
    HybridAlignmentProvenance,
    HybridCueIdentity,
    HybridEvidenceBundle,
)


_DECISION_PROVENANCE: Final = MappingProxyType(
    {
        ACCEPT_HYBRID: ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
        REJECT_EXTERNAL: ALIGNMENT_PROVENANCE_ASR_ONLY,
        UNRESOLVED: ALIGNMENT_PROVENANCE_UNRESOLVED,
    }
)


class AlignmentAcceptanceApplicationError(ValueError):
    """Base class for deterministic decision-application failures."""


class AlignmentAcceptanceApplicationValidationError(
    AlignmentAcceptanceApplicationError
):
    """Raised when decision and immutable evidence cannot be applied safely."""


def _validated_decision(value: object) -> AlignmentAcceptanceDecision:
    if not isinstance(value, AlignmentAcceptanceDecision):
        raise AlignmentAcceptanceApplicationValidationError(
            "decision must be an AlignmentAcceptanceDecision"
        )
    try:
        return AlignmentAcceptanceDecision(
            verdict=value.verdict,
            recommended_provenance=value.recommended_provenance,
            reason_codes=value.reason_codes,
            anchor_count=value.anchor_count,
            inlier_count=value.inlier_count,
            inlier_ratio=value.inlier_ratio,
            median_absolute_residual_ms=value.median_absolute_residual_ms,
            external_evidence_span_ms=value.external_evidence_span_ms,
            asr_evidence_span_ms=value.asr_evidence_span_ms,
            scale=value.scale,
        )
    except (AttributeError, TypeError, ValueError, OverflowError) as error:
        raise AlignmentAcceptanceApplicationValidationError(
            "decision is invalid or detached"
        ) from error


def _validated_bundle(value: object) -> HybridEvidenceBundle:
    if not isinstance(value, HybridEvidenceBundle):
        raise AlignmentAcceptanceApplicationValidationError(
            "bundle must be a HybridEvidenceBundle"
        )
    try:
        return HybridEvidenceBundle(
            dvd_id=value.dvd_id,
            asr_result=value.asr_result,
            cue_evidence=value.cue_evidence,
            alignment=value.alignment,
            external_ja_payload=value.external_ja_payload,
            external_ja_document=value.external_ja_document,
            external_en_payload=value.external_en_payload,
            external_en_document=value.external_en_document,
        )
    except Exception as error:
        raise AlignmentAcceptanceApplicationValidationError(
            "bundle evidence is invalid or detached"
        ) from error


def _validated_alignment(value: object) -> RobustAffineAlignment:
    if not isinstance(value, RobustAffineAlignment):
        raise AlignmentAcceptanceApplicationValidationError(
            "alignment must be a RobustAffineAlignment"
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
        raise AlignmentAcceptanceApplicationValidationError(
            "alignment evidence is invalid or detached"
        ) from error


def _evidence_span_ms(
    first_midpoint_x2: int,
    last_midpoint_x2: int,
    *,
    field_name: str,
) -> float:
    if type(first_midpoint_x2) is not int or type(last_midpoint_x2) is not int:
        raise AlignmentAcceptanceApplicationValidationError(
            field_name + " midpoint evidence must use exact integers"
        )
    delta_x2 = last_midpoint_x2 - first_midpoint_x2
    if delta_x2 < 0:
        raise AlignmentAcceptanceApplicationValidationError(
            field_name + " midpoint evidence is not ordered"
        )
    try:
        span_ms = float(Fraction(delta_x2, 2))
    except (OverflowError, ValueError) as error:
        raise AlignmentAcceptanceApplicationValidationError(
            field_name + " midpoint span is not finite"
        ) from error
    if not math.isfinite(span_ms):
        raise AlignmentAcceptanceApplicationValidationError(
            field_name + " midpoint span is not finite"
        )
    return span_ms


def _validated_alignment_for_decision(
    value: object,
    decision: AlignmentAcceptanceDecision,
    bundle: HybridEvidenceBundle,
) -> RobustAffineAlignment:
    alignment = _validated_alignment(value)
    if alignment.scale != decision.scale:
        raise AlignmentAcceptanceApplicationValidationError(
            "alignment scale is detached from decision"
        )
    if alignment.anchor_count != decision.anchor_count:
        raise AlignmentAcceptanceApplicationValidationError(
            "alignment anchor_count is detached from decision"
        )
    if alignment.inlier_count != decision.inlier_count:
        raise AlignmentAcceptanceApplicationValidationError(
            "alignment inlier_count is detached from decision"
        )
    if alignment.inlier_count / alignment.anchor_count != decision.inlier_ratio:
        raise AlignmentAcceptanceApplicationValidationError(
            "alignment inlier_ratio is detached from decision"
        )
    if alignment.median_absolute_residual_ms != decision.median_absolute_residual_ms:
        raise AlignmentAcceptanceApplicationValidationError(
            "alignment residual quality is detached from decision"
        )

    if (
        bundle.external_ja_document is None
        or bundle.external_ja_payload is None
    ):
        raise AlignmentAcceptanceApplicationValidationError(
            "accepted alignment has no external JA source evidence"
        )
    for residual in alignment.residuals:
        external_index = residual.external_identity.source_index
        asr_index = residual.asr_identity.source_index
        if external_index >= len(bundle.cue_evidence):
            raise AlignmentAcceptanceApplicationValidationError(
                "alignment external identity is detached from bundle evidence"
            )
        if asr_index >= len(bundle.asr_result.segments):
            raise AlignmentAcceptanceApplicationValidationError(
                "alignment ASR identity is detached from bundle evidence"
            )
        evidence = bundle.cue_evidence[external_index]
        if evidence.identity != residual.external_identity:
            raise AlignmentAcceptanceApplicationValidationError(
                "alignment external identity is detached from bundle evidence"
            )
        if residual.asr_identity.cue_id != (
            HybridCueIdentity.for_asr_segment(asr_index).cue_id
        ):
            raise AlignmentAcceptanceApplicationValidationError(
                "alignment ASR identity is not source-stable"
            )
        external_cue = bundle.external_ja_document.cues[external_index]
        asr_segment = bundle.asr_result.segments[asr_index]
        if residual.external_midpoint_x2 != external_cue.start_ms + external_cue.end_ms:
            raise AlignmentAcceptanceApplicationValidationError(
                "alignment external midpoint is detached from source timing"
            )
        if residual.asr_midpoint_x2 != asr_segment.start_ms + asr_segment.end_ms:
            raise AlignmentAcceptanceApplicationValidationError(
                "alignment ASR midpoint is detached from source timing"
            )

    first_residual = alignment.residuals[0]
    last_residual = alignment.residuals[-1]
    external_span_ms = _evidence_span_ms(
        first_residual.external_midpoint_x2,
        last_residual.external_midpoint_x2,
        field_name="external evidence",
    )
    asr_span_ms = _evidence_span_ms(
        first_residual.asr_midpoint_x2,
        last_residual.asr_midpoint_x2,
        field_name="ASR evidence",
    )
    if external_span_ms != decision.external_evidence_span_ms:
        raise AlignmentAcceptanceApplicationValidationError(
            "alignment external evidence span is detached from decision"
        )
    if asr_span_ms != decision.asr_evidence_span_ms:
        raise AlignmentAcceptanceApplicationValidationError(
            "alignment ASR evidence span is detached from decision"
        )
    return alignment


def _provenance_for(
    bundle: HybridEvidenceBundle,
    provenance: str,
) -> HybridAlignmentProvenance:
    return HybridAlignmentProvenance(
        provenance=provenance,
        method=bundle.alignment.method,
        confidence=bundle.alignment.confidence,
    )


def _preserve_evidence_with_provenance(
    bundle: HybridEvidenceBundle,
    provenance: str,
) -> HybridEvidenceBundle:
    return HybridEvidenceBundle(
        dvd_id=bundle.dvd_id,
        asr_result=bundle.asr_result,
        cue_evidence=bundle.cue_evidence,
        alignment=_provenance_for(bundle, provenance),
        external_ja_payload=bundle.external_ja_payload,
        external_ja_document=bundle.external_ja_document,
        external_en_payload=bundle.external_en_payload,
        external_en_document=bundle.external_en_document,
    )


@dataclass(frozen=True)
class AlignmentAcceptanceApplicationResult:
    """Immutable applied decision and resulting evidence bundle."""

    decision: AlignmentAcceptanceDecision
    bundle: HybridEvidenceBundle
    alignment: RobustAffineAlignment | None

    def __post_init__(self):
        decision = _validated_decision(self.decision)
        bundle = _validated_bundle(self.bundle)
        expected_provenance = _DECISION_PROVENANCE[decision.verdict]
        if decision.recommended_provenance != expected_provenance:
            raise AlignmentAcceptanceApplicationValidationError(
                "decision recommended provenance is inconsistent"
            )
        if bundle.alignment.provenance != decision.recommended_provenance:
            raise AlignmentAcceptanceApplicationValidationError(
                "decision and applied bundle provenance are detached"
            )
        if decision.verdict == ACCEPT_HYBRID:
            alignment = _validated_alignment_for_decision(
                self.alignment,
                decision,
                bundle,
            )
        else:
            if self.alignment is not None:
                raise AlignmentAcceptanceApplicationValidationError(
                    "non-hybrid application result must not retain alignment"
                )
            alignment = None
        object.__setattr__(self, "decision", decision)
        object.__setattr__(self, "bundle", bundle)
        object.__setattr__(self, "alignment", alignment)


def apply_alignment_acceptance(
    bundle: HybridEvidenceBundle,
    decision: AlignmentAcceptanceDecision,
    *,
    alignment: RobustAffineAlignment | None = None,
) -> AlignmentAcceptanceApplicationResult:
    """Apply one decision without executing any downstream routing."""

    validated_bundle = _validated_bundle(bundle)
    validated_decision = _validated_decision(decision)
    expected_provenance = _DECISION_PROVENANCE[validated_decision.verdict]
    if validated_decision.recommended_provenance != expected_provenance:
        raise AlignmentAcceptanceApplicationValidationError(
            "decision recommended provenance is inconsistent"
        )

    if validated_decision.verdict == ACCEPT_HYBRID:
        if (
            validated_bundle.external_ja_payload is None
            or validated_bundle.external_ja_document is None
        ):
            raise AlignmentAcceptanceApplicationValidationError(
                "ACCEPT_HYBRID requires external JA evidence"
            )
        validated_alignment = _validated_alignment_for_decision(
            alignment,
            validated_decision,
            validated_bundle,
        )
        applied_bundle = _preserve_evidence_with_provenance(
            validated_bundle,
            ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
        )
    elif validated_decision.verdict == REJECT_EXTERNAL:
        if alignment is not None:
            raise AlignmentAcceptanceApplicationValidationError(
                "REJECT_EXTERNAL must not retain alignment"
            )
        if (
            validated_bundle.asr_result is None
            or not validated_bundle.asr_result.segments
        ):
            raise AlignmentAcceptanceApplicationValidationError(
                "REJECT_EXTERNAL requires valid ASR evidence"
            )
        try:
            applied_bundle = HybridEvidenceBundle.from_asr_only(
                dvd_id=validated_bundle.dvd_id,
                asr_result=validated_bundle.asr_result,
                alignment=_provenance_for(
                    validated_bundle,
                    ALIGNMENT_PROVENANCE_ASR_ONLY,
                ),
                external_en_payload=validated_bundle.external_en_payload,
                external_en_document=validated_bundle.external_en_document,
            )
        except Exception as error:
            raise AlignmentAcceptanceApplicationValidationError(
                "could not construct the canonical ASR-only bundle"
            ) from error
        validated_alignment = None
    elif validated_decision.verdict == UNRESOLVED:
        if alignment is not None:
            raise AlignmentAcceptanceApplicationValidationError(
                "UNRESOLVED must not retain alignment"
            )
        applied_bundle = _preserve_evidence_with_provenance(
            validated_bundle,
            ALIGNMENT_PROVENANCE_UNRESOLVED,
        )
        validated_alignment = None
    else:
        raise AlignmentAcceptanceApplicationValidationError(
            "decision verdict is unsupported"
        )

    return AlignmentAcceptanceApplicationResult(
        decision=validated_decision,
        bundle=applied_bundle,
        alignment=validated_alignment,
    )


__all__ = [
    "AlignmentAcceptanceApplicationError",
    "AlignmentAcceptanceApplicationResult",
    "AlignmentAcceptanceApplicationValidationError",
    "apply_alignment_acceptance",
]
