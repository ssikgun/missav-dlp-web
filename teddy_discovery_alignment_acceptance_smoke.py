"""Offline smoke tests for deterministic alignment acceptance decisions."""

from dataclasses import FrozenInstanceError, MISSING, fields
import math
from pathlib import Path

from teddy_discovery_alignment import (
    AnchorTimingEvidence,
    JapaneseComparisonEvidence,
    MonotonicAnchorCandidate,
    infer_robust_affine_alignment,
    japanese_lexical_similarity,
)
from teddy_discovery_alignment_acceptance import (
    ACCEPT_HYBRID,
    ALIGNMENT_POLICY_SATISFIED,
    AlignmentAcceptanceDecision,
    AlignmentAcceptancePolicy,
    AlignmentAcceptanceValidationError,
    HIGH_MEDIAN_RESIDUAL,
    INSUFFICIENT_ANCHOR_COUNT,
    INSUFFICIENT_ASR_SPAN,
    INSUFFICIENT_EXTERNAL_SPAN,
    INSUFFICIENT_INLIER_COUNT,
    LOW_INLIER_RATIO,
    REJECT_EXTERNAL,
    SCALE_ABOVE_POLICY,
    SCALE_BELOW_POLICY,
    UNRESOLVED,
    decide_alignment_acceptance,
)
from teddy_discovery_hybrid_evidence import (
    ALIGNMENT_PROVENANCE_ASR_ONLY,
    ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
    ALIGNMENT_PROVENANCE_UNRESOLVED,
    HybridCueIdentity,
)


BASE_POLICY_VALUES = {
    "minimum_anchor_count": 3,
    "minimum_inlier_count": 3,
    "minimum_inlier_ratio": 0.75,
    "maximum_median_absolute_residual_ms": 1.0,
    "minimum_evidence_span_ms": 1_000,
    "minimum_scale": 1.0,
    "maximum_scale": 2.0,
}


def require(condition: bool, marker: str):
    if not condition:
        raise AssertionError(marker)


def expect_raises(exception_type, callback, marker: str):
    try:
        callback()
    except exception_type:
        return
    except Exception as error:
        raise AssertionError(
            marker + ": wrong exception " + type(error).__name__
        ) from error
    raise AssertionError(marker)


def timed_candidate(
    index: int,
    external_midpoint_ms: int,
    asr_midpoint_ms: int,
) -> MonotonicAnchorCandidate:
    external_normalized = japanese_lexical_similarity("同じ", "同じ")
    return MonotonicAnchorCandidate(
        external_identity=HybridCueIdentity.for_external_ja(index),
        asr_identity=HybridCueIdentity.for_asr_segment(index),
        comparison=JapaneseComparisonEvidence(
            external_normalized="同じ",
            asr_normalized="同じ",
        ),
        timing=AnchorTimingEvidence(
            external_start_ms=external_midpoint_ms - 50,
            external_end_ms=external_midpoint_ms + 50,
            asr_start_ms=asr_midpoint_ms - 50,
            asr_end_ms=asr_midpoint_ms + 50,
        ),
        score=external_normalized,
    )


def alignment_for(
    external_midpoints: tuple[int, ...],
    asr_midpoints: tuple[int, ...],
    *,
    residual_threshold_ms: int,
):
    require(
        len(external_midpoints) == len(asr_midpoints),
        "ALIGNMENT_FIXTURE_CARDINALITY",
    )
    return infer_robust_affine_alignment(
        tuple(
            timed_candidate(index, external_midpoint, asr_midpoint)
            for index, (external_midpoint, asr_midpoint) in enumerate(
                zip(external_midpoints, asr_midpoints)
            )
        ),
        residual_threshold_ms=residual_threshold_ms,
    )


def policy_with(**overrides) -> AlignmentAcceptancePolicy:
    values = dict(BASE_POLICY_VALUES)
    values.update(overrides)
    return AlignmentAcceptancePolicy(**values)


def main():
    exact_alignment = alignment_for(
        (500, 1_500, 2_500, 3_500),
        (850, 2_350, 3_850, 5_350),
        residual_threshold_ms=1,
    )
    exact_policy = policy_with()
    accepted = decide_alignment_acceptance(exact_alignment, exact_policy)
    require(
        accepted.verdict == ACCEPT_HYBRID
        and accepted.recommended_provenance
        == ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID
        and accepted.reason_codes == (ALIGNMENT_POLICY_SATISFIED,)
        and accepted.anchor_count == 4
        and accepted.inlier_count == 4
        and accepted.inlier_ratio == 1.0
        and accepted.median_absolute_residual_ms == 0.0
        and accepted.external_evidence_span_ms == 3_000.0
        and accepted.asr_evidence_span_ms == 4_500.0
        and math.isclose(accepted.scale, 1.5, abs_tol=1e-12),
        "CLEAR_ACCEPT_HYBRID",
    )

    insufficient_anchors = decide_alignment_acceptance(
        exact_alignment,
        policy_with(minimum_anchor_count=5),
    )
    require(
        insufficient_anchors.verdict == UNRESOLVED
        and insufficient_anchors.recommended_provenance
        == ALIGNMENT_PROVENANCE_UNRESOLVED
        and insufficient_anchors.reason_codes == (INSUFFICIENT_ANCHOR_COUNT,),
        "INSUFFICIENT_ANCHORS_UNRESOLVED",
    )

    insufficient_inliers_alignment = alignment_for(
        (500, 1_500, 2_500),
        (600, 1_600, 10_000),
        residual_threshold_ms=1,
    )
    require(
        insufficient_inliers_alignment.inlier_count == 2,
        "INSUFFICIENT_INLIERS_FIXTURE",
    )
    insufficient_inliers = decide_alignment_acceptance(
        insufficient_inliers_alignment,
        policy_with(
            minimum_inlier_count=3,
            minimum_inlier_ratio=0.1,
            maximum_median_absolute_residual_ms=10_000.0,
            minimum_scale=0.1,
            maximum_scale=10.0,
        ),
    )
    require(
        insufficient_inliers.verdict == UNRESOLVED
        and insufficient_inliers.reason_codes == (INSUFFICIENT_INLIER_COUNT,),
        "INSUFFICIENT_INLIERS_UNRESOLVED",
    )

    external_span_alignment = alignment_for(
        (500, 600, 700),
        (850, 2_350, 3_850),
        residual_threshold_ms=10_000,
    )
    external_span_decision = decide_alignment_acceptance(
        external_span_alignment,
        policy_with(
            minimum_inlier_ratio=0.1,
            maximum_median_absolute_residual_ms=100_000.0,
            minimum_evidence_span_ms=1_000,
            minimum_scale=0.1,
            maximum_scale=100.0,
        ),
    )
    require(
        external_span_decision.verdict == UNRESOLVED
        and external_span_decision.reason_codes == (INSUFFICIENT_EXTERNAL_SPAN,),
        "INSUFFICIENT_EXTERNAL_SPAN_UNRESOLVED",
    )

    asr_span_alignment = alignment_for(
        (500, 1_500, 2_500),
        (850, 950, 1_050),
        residual_threshold_ms=10_000,
    )
    asr_span_decision = decide_alignment_acceptance(
        asr_span_alignment,
        policy_with(
            minimum_inlier_ratio=0.1,
            maximum_median_absolute_residual_ms=100_000.0,
            minimum_evidence_span_ms=1_000,
            minimum_scale=0.01,
            maximum_scale=1.0,
        ),
    )
    require(
        asr_span_decision.verdict == UNRESOLVED
        and asr_span_decision.reason_codes == (INSUFFICIENT_ASR_SPAN,),
        "INSUFFICIENT_ASR_SPAN_UNRESOLVED",
    )

    outlier_alignment = alignment_for(
        (500, 1_500, 2_500, 3_500, 4_500, 5_500),
        (850, 2_350, 3_850, 5_350, 6_850, 12_000),
        residual_threshold_ms=100,
    )
    require(
        outlier_alignment.inlier_count == 5
        and outlier_alignment.residuals[-1].is_inlier is False,
        "QUALITY_REJECTION_OUTLIER_FIXTURE",
    )
    low_ratio = decide_alignment_acceptance(
        outlier_alignment,
        policy_with(
            minimum_inlier_ratio=0.99,
            maximum_median_absolute_residual_ms=1.0,
        ),
    )
    require(
        low_ratio.verdict == REJECT_EXTERNAL
        and low_ratio.recommended_provenance == ALIGNMENT_PROVENANCE_ASR_ONLY
        and low_ratio.reason_codes == (LOW_INLIER_RATIO,),
        "LOW_INLIER_RATIO_REJECTS_EXTERNAL",
    )

    non_affine_alignment = alignment_for(
        (500, 1_500, 2_500, 3_500),
        (600, 2_200, 2_400, 3_600),
        residual_threshold_ms=1_000,
    )
    require(
        non_affine_alignment.inlier_count == 4
        and math.isclose(
            non_affine_alignment.median_absolute_residual_ms,
            125.0,
            abs_tol=1e-12,
        ),
        "HIGH_RESIDUAL_FIXTURE",
    )
    high_residual = decide_alignment_acceptance(
        non_affine_alignment,
        policy_with(
            maximum_median_absolute_residual_ms=124.0,
            minimum_scale=0.5,
            maximum_scale=2.0,
        ),
    )
    require(
        high_residual.verdict == REJECT_EXTERNAL
        and high_residual.reason_codes == (HIGH_MEDIAN_RESIDUAL,),
        "HIGH_MEDIAN_RESIDUAL_REJECTS_EXTERNAL",
    )

    scale_below = decide_alignment_acceptance(
        exact_alignment,
        policy_with(minimum_scale=1.6, maximum_scale=2.0),
    )
    scale_above = decide_alignment_acceptance(
        exact_alignment,
        policy_with(minimum_scale=1.0, maximum_scale=1.4),
    )
    require(
        scale_below.verdict == REJECT_EXTERNAL
        and scale_below.reason_codes == (SCALE_BELOW_POLICY,)
        and scale_above.verdict == REJECT_EXTERNAL
        and scale_above.reason_codes == (SCALE_ABOVE_POLICY,),
        "SCALE_POLICY_REJECTIONS",
    )

    # Every sufficiency and quality comparison is inclusive at its stated
    # boundary.  This fixture has equal external/ASR spans and nonzero
    # residual evidence so all policy fields can be tested at equality.
    boundary_alignment = non_affine_alignment
    boundary_policy = policy_with(
        minimum_anchor_count=4,
        minimum_inlier_count=4,
        minimum_inlier_ratio=1.0,
        maximum_median_absolute_residual_ms=(
            boundary_alignment.median_absolute_residual_ms
        ),
        minimum_evidence_span_ms=3_000,
        minimum_scale=0.95,
        maximum_scale=0.95,
    )
    boundary_decision = decide_alignment_acceptance(
        boundary_alignment,
        boundary_policy,
    )
    require(
        math.isclose(boundary_alignment.scale, 0.95, abs_tol=1e-12)
        and boundary_decision.verdict == ACCEPT_HYBRID
        and boundary_decision.anchor_count
        == boundary_policy.minimum_anchor_count
        and boundary_decision.inlier_count
        == boundary_policy.minimum_inlier_count
        and boundary_decision.inlier_ratio
        == boundary_policy.minimum_inlier_ratio
        and boundary_decision.external_evidence_span_ms == 3_000.0
        and boundary_decision.asr_evidence_span_ms == 3_000.0
        and boundary_decision.median_absolute_residual_ms
        == boundary_policy.maximum_median_absolute_residual_ms
        and boundary_decision.scale == boundary_policy.minimum_scale
        == boundary_policy.maximum_scale,
        "ALL_POLICY_BOUNDARIES_INCLUSIVE",
    )

    ordered_reasons = decide_alignment_acceptance(
        exact_alignment,
        policy_with(
            minimum_anchor_count=5,
            minimum_inlier_count=5,
            minimum_evidence_span_ms=5_000,
        ),
    )
    require(
        ordered_reasons.verdict == UNRESOLVED
        and ordered_reasons.reason_codes
        == (
            INSUFFICIENT_ANCHOR_COUNT,
            INSUFFICIENT_INLIER_COUNT,
            INSUFFICIENT_EXTERNAL_SPAN,
            INSUFFICIENT_ASR_SPAN,
        ),
        "DETERMINISTIC_REASON_ORDER",
    )

    precedence = decide_alignment_acceptance(
        exact_alignment,
        policy_with(
            minimum_anchor_count=5,
            minimum_inlier_count=5,
            minimum_evidence_span_ms=5_000,
            maximum_median_absolute_residual_ms=0.1,
            minimum_scale=2.0,
            maximum_scale=3.0,
        ),
    )
    require(
        precedence.verdict == UNRESOLVED
        and precedence.recommended_provenance == ALIGNMENT_PROVENANCE_UNRESOLVED
        and precedence.reason_codes == ordered_reasons.reason_codes
        and LOW_INLIER_RATIO not in precedence.reason_codes
        and HIGH_MEDIAN_RESIDUAL not in precedence.reason_codes
        and SCALE_BELOW_POLICY not in precedence.reason_codes
        and SCALE_ABOVE_POLICY not in precedence.reason_codes,
        "SUFFICIENCY_PRECEDES_QUALITY_REJECTION",
    )

    # Policy fields are explicit, required, frozen values.  Exact type checks
    # reject booleans and accidental implicit numeric coercion.
    for field in fields(AlignmentAcceptancePolicy):
        require(
            field.default is MISSING and field.default_factory is MISSING,
            "POLICY_FIELD_HAS_NO_HIDDEN_DEFAULT_" + field.name.upper(),
        )
    invalid_policy_values = (
        ({"minimum_anchor_count": True}, "POLICY_BOOLEAN_ANCHOR_REJECTED"),
        ({"minimum_anchor_count": 2}, "POLICY_LOW_ANCHOR_REJECTED"),
        ({"minimum_anchor_count": 513}, "POLICY_HIGH_ANCHOR_REJECTED"),
        ({"minimum_inlier_count": True}, "POLICY_BOOLEAN_INLIER_REJECTED"),
        ({"minimum_inlier_count": 0}, "POLICY_ZERO_INLIER_REJECTED"),
        ({"minimum_inlier_count": 3.0}, "POLICY_FLOAT_INLIER_REJECTED"),
        ({"minimum_inlier_count": 4}, "POLICY_INLIER_NOT_COHERENT_REJECTED"),
        ({"minimum_inlier_ratio": True}, "POLICY_BOOLEAN_RATIO_REJECTED"),
        ({"minimum_inlier_ratio": 0.0}, "POLICY_ZERO_RATIO_REJECTED"),
        ({"minimum_inlier_ratio": math.nan}, "POLICY_NAN_RATIO_REJECTED"),
        ({"minimum_inlier_ratio": math.inf}, "POLICY_INF_RATIO_REJECTED"),
        ({"minimum_inlier_ratio": 1}, "POLICY_INTEGER_RATIO_REJECTED"),
        (
            {"maximum_median_absolute_residual_ms": True},
            "POLICY_BOOLEAN_RESIDUAL_REJECTED",
        ),
        (
            {"maximum_median_absolute_residual_ms": 0.0},
            "POLICY_ZERO_RESIDUAL_REJECTED",
        ),
        (
            {"maximum_median_absolute_residual_ms": math.nan},
            "POLICY_NAN_RESIDUAL_REJECTED",
        ),
        (
            {"maximum_median_absolute_residual_ms": 1},
            "POLICY_INTEGER_RESIDUAL_REJECTED",
        ),
        (
            {"minimum_evidence_span_ms": True},
            "POLICY_BOOLEAN_SPAN_REJECTED",
        ),
        (
            {"minimum_evidence_span_ms": -1},
            "POLICY_NEGATIVE_SPAN_REJECTED",
        ),
        (
            {"minimum_evidence_span_ms": 1.0},
            "POLICY_FLOAT_SPAN_REJECTED",
        ),
        ({"minimum_scale": True}, "POLICY_BOOLEAN_MIN_SCALE_REJECTED"),
        ({"minimum_scale": 0.0}, "POLICY_ZERO_MIN_SCALE_REJECTED"),
        ({"minimum_scale": math.nan}, "POLICY_NAN_MIN_SCALE_REJECTED"),
        ({"minimum_scale": 1}, "POLICY_INTEGER_MIN_SCALE_REJECTED"),
        ({"maximum_scale": True}, "POLICY_BOOLEAN_MAX_SCALE_REJECTED"),
        ({"maximum_scale": math.inf}, "POLICY_INF_MAX_SCALE_REJECTED"),
        ({"maximum_scale": 2}, "POLICY_INTEGER_MAX_SCALE_REJECTED"),
        (
            {"minimum_scale": 2.0, "maximum_scale": 1.0},
            "POLICY_REVERSED_SCALE_RANGE_REJECTED",
        ),
    )
    for overrides, marker in invalid_policy_values:
        values = dict(BASE_POLICY_VALUES)
        values.update(overrides)
        expect_raises(
            AlignmentAcceptanceValidationError,
            lambda values=values: AlignmentAcceptancePolicy(**values),
            marker,
        )

    expect_raises(
        AlignmentAcceptanceValidationError,
        lambda: decide_alignment_acceptance(exact_alignment, object()),
        "WRONG_POLICY_TYPE_REJECTED",
    )
    expect_raises(
        AlignmentAcceptanceValidationError,
        lambda: decide_alignment_acceptance(object(), exact_policy),
        "WRONG_ALIGNMENT_TYPE_REJECTED",
    )

    require(
        getattr(AlignmentAcceptancePolicy.__dataclass_params__, "frozen", False)
        and getattr(AlignmentAcceptanceDecision.__dataclass_params__, "frozen", False)
        and isinstance(accepted.reason_codes, tuple)
        and accepted == decide_alignment_acceptance(exact_alignment, exact_policy),
        "FROZEN_DETERMINISTIC_POLICY_AND_RESULT",
    )
    expect_raises(
        FrozenInstanceError,
        lambda: setattr(exact_policy, "minimum_scale", 0.5),
        "POLICY_FROZEN",
    )
    expect_raises(
        FrozenInstanceError,
        lambda: setattr(accepted, "verdict", REJECT_EXTERNAL),
        "DECISION_FROZEN",
    )

    acceptance_source = Path(__file__).with_name(
        "teddy_discovery_alignment_acceptance.py"
    )
    source_text = acceptance_source.read_text(encoding="utf-8").lower()
    for forbidden, marker in (
        ("jur-750", "NO_TITLE_SPECIFIC_BEHAVIOR"),
        ("hybridevidencebundle", "NO_BUNDLE_MUTATION_OR_ROUTING"),
        ("project_timestamp", "NO_TIMESTAMP_PROJECTION"),
        ("transform_timestamp", "NO_TIMESTAMP_TRANSFORMATION"),
        ("aligned_start_ms", "NO_ALIGNED_START_OWNERSHIP"),
        ("aligned_end_ms", "NO_ALIGNED_END_OWNERSHIP"),
        ("rewrite_cue_timing", "NO_CUE_TIMING_REWRITE"),
        ("open(", "NO_FILESYSTEM_IO"),
        ("urllib", "NO_NETWORK_IO"),
        ("subprocess", "NO_SUBPROCESS_IO"),
        ("sqlite", "NO_DATABASE_IO"),
    ):
        require(forbidden not in source_text, marker)

    for contract_type in (
        AlignmentAcceptancePolicy,
        AlignmentAcceptanceDecision,
    ):
        field_names = {field.name for field in fields(contract_type)}
        require(
            not field_names.intersection(
                {
                    "output_start_ms",
                    "output_end_ms",
                    "generated_start_ms",
                    "generated_end_ms",
                    "aligned_start_ms",
                    "aligned_end_ms",
                }
            ),
            contract_type.__name__ + "_NO_OUTPUT_TIMESTAMP_OWNER",
        )

    # The acceptance call is pure: it returns a decision only and leaves the
    # affine evidence object unchanged.  REJECT_EXTERNAL is not execution.
    before_alignment = exact_alignment
    rejected_provenance = low_ratio.recommended_provenance
    require(
        before_alignment == exact_alignment
        and rejected_provenance == ALIGNMENT_PROVENANCE_ASR_ONLY,
        "NO_ASR_ONLY_FALLBACK_EXECUTION",
    )

    print("ALIGNMENT_ACCEPTANCE_SMOKE_PASS")


if __name__ == "__main__":
    main()
