"""Apply an alignment acceptance decision to immutable hybrid evidence.

This module is a small pure application boundary.  It preserves the existing
source-owned evidence for ACCEPT_HYBRID and UNRESOLVED, and creates the
canonical ASR-only representation only for REJECT_EXTERNAL.  It does not
publish, invoke models or ASR, modify timestamps, or perform I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

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


def apply_alignment_acceptance(
    bundle: HybridEvidenceBundle,
    decision: AlignmentAcceptanceDecision,
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
        applied_bundle = _preserve_evidence_with_provenance(
            validated_bundle,
            ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
        )
    elif validated_decision.verdict == REJECT_EXTERNAL:
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
    elif validated_decision.verdict == UNRESOLVED:
        applied_bundle = _preserve_evidence_with_provenance(
            validated_bundle,
            ALIGNMENT_PROVENANCE_UNRESOLVED,
        )
    else:
        raise AlignmentAcceptanceApplicationValidationError(
            "decision verdict is unsupported"
        )

    return AlignmentAcceptanceApplicationResult(
        decision=validated_decision,
        bundle=applied_bundle,
    )


__all__ = [
    "AlignmentAcceptanceApplicationError",
    "AlignmentAcceptanceApplicationResult",
    "AlignmentAcceptanceApplicationValidationError",
    "apply_alignment_acceptance",
]
