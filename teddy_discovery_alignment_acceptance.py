"""Deterministic acceptance decisions for completed Stage11 alignment evidence.

This module is a pure decision boundary.  It consumes an immutable
``RobustAffineAlignment`` and explicit caller-owned policy values, then emits
an immutable verdict and recommended provenance.  It does not mutate hybrid
evidence, execute fallback routing, create subtitle output, or transform
source timing evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import math
from types import MappingProxyType
from typing import Final

from teddy_discovery_alignment import (
    MAX_AFFINE_ANCHORS,
    MIN_AFFINE_ANCHORS,
    RobustAffineAlignment,
)
from teddy_discovery_hybrid_evidence import (
    ALIGNMENT_PROVENANCE_ASR_ONLY,
    ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
    ALIGNMENT_PROVENANCE_UNRESOLVED,
)


ACCEPT_HYBRID: Final[str] = "ACCEPT_HYBRID"
REJECT_EXTERNAL: Final[str] = "REJECT_EXTERNAL"
UNRESOLVED: Final[str] = "UNRESOLVED"

INSUFFICIENT_ANCHOR_COUNT: Final[str] = "INSUFFICIENT_ANCHOR_COUNT"
INSUFFICIENT_INLIER_COUNT: Final[str] = "INSUFFICIENT_INLIER_COUNT"
INSUFFICIENT_EXTERNAL_SPAN: Final[str] = "INSUFFICIENT_EXTERNAL_SPAN"
INSUFFICIENT_ASR_SPAN: Final[str] = "INSUFFICIENT_ASR_SPAN"
LOW_INLIER_RATIO: Final[str] = "LOW_INLIER_RATIO"
HIGH_MEDIAN_RESIDUAL: Final[str] = "HIGH_MEDIAN_RESIDUAL"
SCALE_BELOW_POLICY: Final[str] = "SCALE_BELOW_POLICY"
SCALE_ABOVE_POLICY: Final[str] = "SCALE_ABOVE_POLICY"
ALIGNMENT_POLICY_SATISFIED: Final[str] = "ALIGNMENT_POLICY_SATISFIED"

_SUFFICIENCY_REASON_ORDER: Final[tuple[str, ...]] = (
    INSUFFICIENT_ANCHOR_COUNT,
    INSUFFICIENT_INLIER_COUNT,
    INSUFFICIENT_EXTERNAL_SPAN,
    INSUFFICIENT_ASR_SPAN,
)
_QUALITY_REASON_ORDER: Final[tuple[str, ...]] = (
    LOW_INLIER_RATIO,
    HIGH_MEDIAN_RESIDUAL,
    SCALE_BELOW_POLICY,
    SCALE_ABOVE_POLICY,
)
_VERDICT_PROVENANCE: Final = MappingProxyType(
    {
        ACCEPT_HYBRID: ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
        REJECT_EXTERNAL: ALIGNMENT_PROVENANCE_ASR_ONLY,
        UNRESOLVED: ALIGNMENT_PROVENANCE_UNRESOLVED,
    }
)


class AlignmentAcceptanceError(ValueError):
    """Base class for deterministic acceptance-boundary failures."""


class AlignmentAcceptanceValidationError(AlignmentAcceptanceError):
    """Raised when policy or affine evidence is invalid or detached."""


def _require_exact_positive_int(value: object, *, field_name: str) -> int:
    if type(value) is not int or value <= 0:
        raise AlignmentAcceptanceValidationError(
            field_name + " must be an exact positive integer"
        )
    return value


def _require_exact_nonnegative_int(value: object, *, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise AlignmentAcceptanceValidationError(
            field_name + " must be an exact nonnegative integer"
        )
    return value


def _require_policy_anchor_count(value: object, *, field_name: str) -> int:
    value = _require_exact_positive_int(value, field_name=field_name)
    if not MIN_AFFINE_ANCHORS <= value <= MAX_AFFINE_ANCHORS:
        raise AlignmentAcceptanceValidationError(
            field_name + " is outside the affine anchor bounds"
        )
    return value


def _require_policy_float(
    value: object,
    *,
    field_name: str,
    strictly_positive: bool = False,
    ratio: bool = False,
) -> float:
    if type(value) is not float or not math.isfinite(value):
        raise AlignmentAcceptanceValidationError(
            field_name + " must be a finite float"
        )
    if strictly_positive and value <= 0.0:
        raise AlignmentAcceptanceValidationError(
            field_name + " must be strictly positive"
        )
    if ratio and not 0.0 < value <= 1.0:
        raise AlignmentAcceptanceValidationError(
            field_name + " must be within (0.0, 1.0]"
        )
    return value


def _require_finite_nonnegative_float(
    value: object,
    *,
    field_name: str,
) -> float:
    if type(value) is not float or not math.isfinite(value) or value < 0.0:
        raise AlignmentAcceptanceValidationError(
            field_name + " must be a finite nonnegative float"
        )
    return value


@dataclass(frozen=True)
class AlignmentAcceptancePolicy:
    """Explicit immutable gates for one alignment acceptance decision."""

    minimum_anchor_count: int
    minimum_inlier_count: int
    minimum_inlier_ratio: float
    maximum_median_absolute_residual_ms: float
    minimum_evidence_span_ms: int
    minimum_scale: float
    maximum_scale: float

    def __post_init__(self):
        minimum_anchor_count = _require_policy_anchor_count(
            self.minimum_anchor_count,
            field_name="minimum_anchor_count",
        )
        minimum_inlier_count = _require_exact_positive_int(
            self.minimum_inlier_count,
            field_name="minimum_inlier_count",
        )
        if minimum_inlier_count > MAX_AFFINE_ANCHORS:
            raise AlignmentAcceptanceValidationError(
                "minimum_inlier_count exceeds MAX_AFFINE_ANCHORS"
            )
        if minimum_inlier_count > minimum_anchor_count:
            raise AlignmentAcceptanceValidationError(
                "minimum_inlier_count cannot exceed minimum_anchor_count"
            )
        _require_policy_float(
            self.minimum_inlier_ratio,
            field_name="minimum_inlier_ratio",
            ratio=True,
        )
        _require_policy_float(
            self.maximum_median_absolute_residual_ms,
            field_name="maximum_median_absolute_residual_ms",
            strictly_positive=True,
        )
        _require_exact_nonnegative_int(
            self.minimum_evidence_span_ms,
            field_name="minimum_evidence_span_ms",
        )
        minimum_scale = _require_policy_float(
            self.minimum_scale,
            field_name="minimum_scale",
            strictly_positive=True,
        )
        maximum_scale = _require_policy_float(
            self.maximum_scale,
            field_name="maximum_scale",
            strictly_positive=True,
        )
        if minimum_scale > maximum_scale:
            raise AlignmentAcceptanceValidationError(
                "minimum_scale cannot exceed maximum_scale"
            )


def _require_reason_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise AlignmentAcceptanceValidationError(
            field_name + " must be an immutable tuple"
        )
    for reason in value:
        if type(reason) is not str:
            raise AlignmentAcceptanceValidationError(
                field_name + " must contain exact strings"
            )
    if len(set(value)) != len(value):
        raise AlignmentAcceptanceValidationError(
            field_name + " must not contain duplicate reason codes"
        )
    return value


@dataclass(frozen=True)
class AlignmentAcceptanceDecision:
    """Immutable verdict and metrics; it does not execute the recommendation."""

    verdict: str
    recommended_provenance: str
    reason_codes: tuple[str, ...]
    anchor_count: int
    inlier_count: int
    inlier_ratio: float
    median_absolute_residual_ms: float
    external_evidence_span_ms: float
    asr_evidence_span_ms: float
    scale: float

    def __post_init__(self):
        if type(self.verdict) is not str or self.verdict not in _VERDICT_PROVENANCE:
            raise AlignmentAcceptanceValidationError(
                "verdict is unsupported"
            )
        if (
            type(self.recommended_provenance) is not str
            or self.recommended_provenance != _VERDICT_PROVENANCE[self.verdict]
        ):
            raise AlignmentAcceptanceValidationError(
                "recommended_provenance does not match verdict"
            )

        reason_codes = _require_reason_tuple(
            self.reason_codes,
            field_name="reason_codes",
        )
        if self.verdict == ACCEPT_HYBRID:
            expected_reason_codes = (ALIGNMENT_POLICY_SATISFIED,)
        elif self.verdict == UNRESOLVED:
            expected_reason_codes = tuple(
                reason
                for reason in _SUFFICIENCY_REASON_ORDER
                if reason in reason_codes
            )
            if any(reason not in _SUFFICIENCY_REASON_ORDER for reason in reason_codes):
                raise AlignmentAcceptanceValidationError(
                    "UNRESOLVED may contain only sufficiency reason codes"
                )
        else:
            expected_reason_codes = tuple(
                reason
                for reason in _QUALITY_REASON_ORDER
                if reason in reason_codes
            )
            if any(reason not in _QUALITY_REASON_ORDER for reason in reason_codes):
                raise AlignmentAcceptanceValidationError(
                    "REJECT_EXTERNAL may contain only quality reason codes"
                )

        if not expected_reason_codes or reason_codes != expected_reason_codes:
            raise AlignmentAcceptanceValidationError(
                "reason_codes are not in deterministic verdict order"
            )

        anchor_count = _require_policy_anchor_count(
            self.anchor_count,
            field_name="anchor_count",
        )
        inlier_count = _require_exact_nonnegative_int(
            self.inlier_count,
            field_name="inlier_count",
        )
        if inlier_count > anchor_count:
            raise AlignmentAcceptanceValidationError(
                "inlier_count cannot exceed anchor_count"
            )
        inlier_ratio = _require_policy_float(
            self.inlier_ratio,
            field_name="inlier_ratio",
        )
        if not 0.0 <= inlier_ratio <= 1.0:
            raise AlignmentAcceptanceValidationError(
                "inlier_ratio must be within [0.0, 1.0]"
            )
        expected_inlier_ratio = inlier_count / anchor_count
        if inlier_ratio != expected_inlier_ratio:
            raise AlignmentAcceptanceValidationError(
                "inlier_ratio does not match inlier_count and anchor_count"
            )
        median_absolute_residual_ms = _require_finite_nonnegative_float(
            self.median_absolute_residual_ms,
            field_name="median_absolute_residual_ms",
        )
        _require_finite_nonnegative_float(
            self.external_evidence_span_ms,
            field_name="external_evidence_span_ms",
        )
        _require_finite_nonnegative_float(
            self.asr_evidence_span_ms,
            field_name="asr_evidence_span_ms",
        )
        _require_policy_float(
            self.scale,
            field_name="scale",
            strictly_positive=True,
        )


def _validated_policy(value: object) -> AlignmentAcceptancePolicy:
    if not isinstance(value, AlignmentAcceptancePolicy):
        raise AlignmentAcceptanceValidationError(
            "policy must be an AlignmentAcceptancePolicy"
        )
    try:
        return AlignmentAcceptancePolicy(
            minimum_anchor_count=value.minimum_anchor_count,
            minimum_inlier_count=value.minimum_inlier_count,
            minimum_inlier_ratio=value.minimum_inlier_ratio,
            maximum_median_absolute_residual_ms=(
                value.maximum_median_absolute_residual_ms
            ),
            minimum_evidence_span_ms=value.minimum_evidence_span_ms,
            minimum_scale=value.minimum_scale,
            maximum_scale=value.maximum_scale,
        )
    except (AttributeError, TypeError, ValueError, OverflowError) as error:
        raise AlignmentAcceptanceValidationError(
            "policy is invalid"
        ) from error


def _validated_alignment(value: object) -> RobustAffineAlignment:
    if not isinstance(value, RobustAffineAlignment):
        raise AlignmentAcceptanceValidationError(
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
        raise AlignmentAcceptanceValidationError(
            "alignment evidence is invalid or detached"
        ) from error


def _evidence_span_ms(
    first_midpoint_x2: int,
    last_midpoint_x2: int,
    *,
    field_name: str,
) -> float:
    if type(first_midpoint_x2) is not int or type(last_midpoint_x2) is not int:
        raise AlignmentAcceptanceValidationError(
            field_name + " midpoint evidence must use exact integers"
        )
    delta_x2 = last_midpoint_x2 - first_midpoint_x2
    if delta_x2 < 0:
        raise AlignmentAcceptanceValidationError(
            field_name + " midpoint evidence is not ordered"
        )
    try:
        span_ms = float(Fraction(delta_x2, 2))
    except (OverflowError, ValueError) as error:
        raise AlignmentAcceptanceValidationError(
            field_name + " midpoint span is not finite"
        ) from error
    if not math.isfinite(span_ms):
        raise AlignmentAcceptanceValidationError(
            field_name + " midpoint span is not finite"
        )
    return span_ms


def decide_alignment_acceptance(
    alignment: RobustAffineAlignment,
    policy: AlignmentAcceptancePolicy,
) -> AlignmentAcceptanceDecision:
    """Return a deterministic verdict for completed affine evidence.

    Sufficiency gates are evaluated first.  Quality failures are considered
    only when the sample is sufficiently supported, so weak evidence remains
    ``UNRESOLVED`` rather than being mislabeled as external-release failure.
    The recommendation is data only; this function performs no fallback.
    """

    validated_policy = _validated_policy(policy)
    validated_alignment = _validated_alignment(alignment)
    residuals = validated_alignment.residuals
    first_residual = residuals[0]
    last_residual = residuals[-1]
    external_evidence_span_ms = _evidence_span_ms(
        first_residual.external_midpoint_x2,
        last_residual.external_midpoint_x2,
        field_name="external evidence",
    )
    asr_evidence_span_ms = _evidence_span_ms(
        first_residual.asr_midpoint_x2,
        last_residual.asr_midpoint_x2,
        field_name="ASR evidence",
    )
    inlier_ratio = validated_alignment.inlier_count / validated_alignment.anchor_count

    insufficiency_reasons = []
    if validated_alignment.anchor_count < validated_policy.minimum_anchor_count:
        insufficiency_reasons.append(INSUFFICIENT_ANCHOR_COUNT)
    if validated_alignment.inlier_count < validated_policy.minimum_inlier_count:
        insufficiency_reasons.append(INSUFFICIENT_INLIER_COUNT)
    if external_evidence_span_ms < validated_policy.minimum_evidence_span_ms:
        insufficiency_reasons.append(INSUFFICIENT_EXTERNAL_SPAN)
    if asr_evidence_span_ms < validated_policy.minimum_evidence_span_ms:
        insufficiency_reasons.append(INSUFFICIENT_ASR_SPAN)

    if insufficiency_reasons:
        return AlignmentAcceptanceDecision(
            verdict=UNRESOLVED,
            recommended_provenance=ALIGNMENT_PROVENANCE_UNRESOLVED,
            reason_codes=tuple(insufficiency_reasons),
            anchor_count=validated_alignment.anchor_count,
            inlier_count=validated_alignment.inlier_count,
            inlier_ratio=inlier_ratio,
            median_absolute_residual_ms=(
                validated_alignment.median_absolute_residual_ms
            ),
            external_evidence_span_ms=external_evidence_span_ms,
            asr_evidence_span_ms=asr_evidence_span_ms,
            scale=validated_alignment.scale,
        )

    quality_reasons = []
    if inlier_ratio < validated_policy.minimum_inlier_ratio:
        quality_reasons.append(LOW_INLIER_RATIO)
    if (
        validated_alignment.median_absolute_residual_ms
        > validated_policy.maximum_median_absolute_residual_ms
    ):
        quality_reasons.append(HIGH_MEDIAN_RESIDUAL)
    if validated_alignment.scale < validated_policy.minimum_scale:
        quality_reasons.append(SCALE_BELOW_POLICY)
    if validated_alignment.scale > validated_policy.maximum_scale:
        quality_reasons.append(SCALE_ABOVE_POLICY)

    if quality_reasons:
        return AlignmentAcceptanceDecision(
            verdict=REJECT_EXTERNAL,
            recommended_provenance=ALIGNMENT_PROVENANCE_ASR_ONLY,
            reason_codes=tuple(quality_reasons),
            anchor_count=validated_alignment.anchor_count,
            inlier_count=validated_alignment.inlier_count,
            inlier_ratio=inlier_ratio,
            median_absolute_residual_ms=(
                validated_alignment.median_absolute_residual_ms
            ),
            external_evidence_span_ms=external_evidence_span_ms,
            asr_evidence_span_ms=asr_evidence_span_ms,
            scale=validated_alignment.scale,
        )

    return AlignmentAcceptanceDecision(
        verdict=ACCEPT_HYBRID,
        recommended_provenance=ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
        reason_codes=(ALIGNMENT_POLICY_SATISFIED,),
        anchor_count=validated_alignment.anchor_count,
        inlier_count=validated_alignment.inlier_count,
        inlier_ratio=inlier_ratio,
        median_absolute_residual_ms=(
            validated_alignment.median_absolute_residual_ms
        ),
        external_evidence_span_ms=external_evidence_span_ms,
        asr_evidence_span_ms=asr_evidence_span_ms,
        scale=validated_alignment.scale,
    )


__all__ = [
    "ACCEPT_HYBRID",
    "ALIGNMENT_POLICY_SATISFIED",
    "AlignmentAcceptanceDecision",
    "AlignmentAcceptanceError",
    "AlignmentAcceptancePolicy",
    "AlignmentAcceptanceValidationError",
    "HIGH_MEDIAN_RESIDUAL",
    "INSUFFICIENT_ANCHOR_COUNT",
    "INSUFFICIENT_ASR_SPAN",
    "INSUFFICIENT_EXTERNAL_SPAN",
    "INSUFFICIENT_INLIER_COUNT",
    "LOW_INLIER_RATIO",
    "REJECT_EXTERNAL",
    "SCALE_ABOVE_POLICY",
    "SCALE_BELOW_POLICY",
    "UNRESOLVED",
    "decide_alignment_acceptance",
]
