"""Offline regressions for affine-consensus selection and numeric contracts."""

from dataclasses import replace
from fractions import Fraction
from unittest.mock import patch

import teddy_discovery_alignment as alignment_module
from teddy_discovery_alignment import (
    AlignmentAmbiguityError,
    AlignmentLimitError,
    AlignmentValidationError,
    AnchorTimingEvidence,
    JapaneseComparisonEvidence,
    MonotonicAnchorCandidate,
    infer_affine_consensus_alignments,
    infer_robust_affine_alignment,
    japanese_lexical_similarity,
    normalize_japanese_for_matching,
    select_monotonic_anchors,
)
from teddy_discovery_alignment_acceptance import (
    ACCEPT_HYBRID,
    AlignmentAcceptancePolicy,
    UNRESOLVED,
    decide_alignment_acceptance,
    select_affine_consensus_alignment,
)
from teddy_discovery_hybrid_evidence import HybridCueIdentity


def require(condition: bool, label: str):
    if not condition:
        raise AssertionError(label)


def expect_raises(error_type, callback, label: str):
    try:
        callback()
    except error_type:
        return
    except Exception as error:
        raise AssertionError(
            label + ": wrong exception " + type(error).__name__
        ) from error
    raise AssertionError(label + ": exception not raised")


def _interval_at_midpoint(value: Fraction) -> tuple[int, int]:
    if value.denominator == 1:
        midpoint = value.numerator
        return midpoint - 1, midpoint + 1
    if value.denominator == 2:
        lower = value.numerator // 2
        return lower, lower + 1
    raise AssertionError("smoke midpoint must be integer or half integer")


def candidate(
    external_index: int,
    asr_index: int,
    external_midpoint: Fraction | int,
    asr_midpoint: Fraction | int,
    *,
    lexical_match: bool = True,
) -> MonotonicAnchorCandidate:
    external_text = "abcdefghi"
    asr_text = "abcdefghi" if lexical_match else "abcdefghX"
    external_normalized = normalize_japanese_for_matching(external_text)
    asr_normalized = normalize_japanese_for_matching(asr_text)
    external_start, external_end = _interval_at_midpoint(
        Fraction(external_midpoint)
    )
    asr_start, asr_end = _interval_at_midpoint(Fraction(asr_midpoint))
    return MonotonicAnchorCandidate(
        external_identity=HybridCueIdentity.for_external_ja(external_index),
        asr_identity=HybridCueIdentity.for_asr_segment(asr_index),
        comparison=JapaneseComparisonEvidence(
            external_normalized=external_normalized,
            asr_normalized=asr_normalized,
        ),
        timing=AnchorTimingEvidence(
            external_start_ms=external_start,
            external_end_ms=external_end,
            asr_start_ms=asr_start,
            asr_end_ms=asr_end,
        ),
        score=japanese_lexical_similarity(
            external_normalized,
            asr_normalized,
        ),
    )


def policy(*, minimum_anchor_count: int = 4) -> AlignmentAcceptancePolicy:
    return AlignmentAcceptancePolicy(
        minimum_anchor_count=minimum_anchor_count,
        minimum_inlier_count=minimum_anchor_count,
        minimum_inlier_ratio=0.90,
        maximum_median_absolute_residual_ms=250.0,
        minimum_evidence_span_ms=3_000_000,
        minimum_scale=0.95,
        maximum_scale=1.05,
    )


def main():
    # The exact fit is 1.001*x + 0.5. At this time magnitude, computing
    # residuals from exact Fractions and validating them from public floats
    # used to diverge by about 1e-9.
    numeric_anchors = tuple(
        candidate(
            index,
            index,
            Fraction(10_000_000 + index * 1_000_000),
            Fraction(10_010_000 + index * 1_001_000) + Fraction(1, 2),
        )
        for index in range(4)
    )
    numeric_alignment = infer_robust_affine_alignment(
        numeric_anchors,
        residual_threshold_ms=1,
    )
    first_numeric_residual = numeric_alignment.residuals[0]
    exact_first_signed = float(
        Fraction(first_numeric_residual.asr_midpoint_x2, 2)
        - (
            Fraction(1001, 1000)
            * Fraction(first_numeric_residual.external_midpoint_x2, 2)
            + Fraction(1, 2)
        )
    )
    exact_to_float_delta = abs(
        exact_first_signed - first_numeric_residual.signed_residual_ms
    )
    require(
        numeric_alignment.anchor_count == 4
        and numeric_alignment.inlier_count == 4
        and numeric_alignment.scale == float(Fraction(1001, 1000))
        and numeric_alignment.intercept_ms == 0.5
        and 1e-9 < exact_to_float_delta < 3e-9
        and all(
            residual.signed_residual_ms
            == float(
                Fraction(residual.asr_midpoint_x2, 2)
                - (
                    Fraction.from_float(numeric_alignment.scale)
                    * Fraction(residual.external_midpoint_x2, 2)
                    + Fraction.from_float(
                        numeric_alignment.intercept_ms
                    )
                )
            )
            for residual in numeric_alignment.residuals
        ),
        "PUBLIC_FLOAT_NUMERIC_ROUND_TRIP_PASS",
    )
    detached_first = replace(
        numeric_alignment.residuals[0],
        signed_residual_ms=(
            numeric_alignment.residuals[0].signed_residual_ms + 1e-10
        ),
        absolute_residual_ms=abs(
            numeric_alignment.residuals[0].signed_residual_ms + 1e-10
        ),
    )
    expect_raises(
        AlignmentValidationError,
        lambda: replace(
            numeric_alignment,
            residuals=(detached_first,) + numeric_alignment.residuals[1:],
        ),
        "DETACHED_RESIDUAL_STILL_REJECTED",
    )

    # The lexical maximum chain is the six high-score but nonlinear candidates.
    # A separate five-anchor lower-score affine path has valid global evidence.
    candidates = []
    for index in range(5):
        x = 1_000_000 + index * 1_000_000
        candidates.append(
            candidate(index, index, x, x + 150, lexical_match=False)
        )
    nonlinear_asr_midpoints = (
        7_000_000,
        8_200_000,
        9_000_000,
        10_200_000,
        11_000_000,
        12_200_000,
    )
    for index, asr_midpoint in enumerate(nonlinear_asr_midpoints):
        x = 1_000_000 + index * 1_000_000
        candidates.append(
            candidate(index, index + 5, x, asr_midpoint)
        )
    candidate_tuple = tuple(candidates)
    lexical_first = select_monotonic_anchors(candidate_tuple)
    require(
        tuple(item.asr_segment_index for item in lexical_first)
        == (5, 6, 7, 8, 9, 10),
        "LEXICAL_FIRST_CHAIN_IS_AFFINE_CONTAMINATED",
    )
    alternatives = infer_affine_consensus_alignments(
        candidate_tuple,
        residual_threshold_ms=1_000,
        minimum_scale=0.95,
        maximum_scale=1.05,
    )
    selected, selected_decision = select_affine_consensus_alignment(
        alternatives,
        policy(),
    )
    require(
        len(selected.anchors) == 5
        and tuple(item.asr_segment_index for item in selected.anchors)
        == (0, 1, 2, 3, 4)
        and selected_decision.verdict == ACCEPT_HYBRID,
        "AFFINE_CONSENSUS_OVERRIDES_POLLUTED_LEXICAL_MAXIMUM",
    )

    # All lexical keys now tie. Affine timing alone supports the same one path.
    repeated_ties = tuple(
        candidate(
            item.external_cue_index,
            item.asr_segment_index,
            Fraction(item.timing.external_start_ms + item.timing.external_end_ms, 2),
            Fraction(item.timing.asr_start_ms + item.timing.asr_end_ms, 2),
            lexical_match=True,
        )
        for item in candidate_tuple
    )
    expect_raises(
        AlignmentAmbiguityError,
        lambda: select_monotonic_anchors(repeated_ties),
        "REPEATED_LEXICAL_TIE_REMAINS_AMBIGUOUS",
    )
    repeated_alternatives = infer_affine_consensus_alignments(
        repeated_ties,
        residual_threshold_ms=1_000,
        minimum_scale=0.95,
        maximum_scale=1.05,
    )
    repeated_selected, repeated_decision = select_affine_consensus_alignment(
        repeated_alternatives,
        policy(),
    )
    require(
        tuple(item.asr_segment_index for item in repeated_selected.anchors)
        == (0, 1, 2, 3, 4)
        and repeated_decision.verdict == ACCEPT_HYBRID,
        "GLOBAL_AFFINE_EVIDENCE_RESOLVES_REPEATED_LEXICAL_TIE",
    )

    # Two source mappings with identical timing, lexical strength, residuals,
    # spans, and policy outcome must remain ambiguous.
    duplicate_evidence = []
    for index in range(4):
        x = 1_000_000 + index * 1_000_000
        y = x + 150
        duplicate_evidence.append(candidate(index, index, x, y))
        duplicate_evidence.append(candidate(index, index + 10, x, y))
    duplicate_alternatives = infer_affine_consensus_alignments(
        tuple(duplicate_evidence),
        residual_threshold_ms=1_000,
        minimum_scale=0.95,
        maximum_scale=1.05,
    )
    expect_raises(
        AlignmentAmbiguityError,
        lambda: select_affine_consensus_alignment(
            duplicate_alternatives,
            policy(),
        ),
        "IDENTICAL_EVIDENCE_CONSENSUS_FAILS_CLOSED",
    )

    # Three anchors can form an affine line, but unchanged four-anchor policy
    # keeps the result unresolved. Two anchors and an out-of-range scale yield
    # no production consensus.
    three_anchors = tuple(
        candidate(index, index, 1_000_000 + index * 1_000_000,
                  1_000_150 + index * 1_000_000)
        for index in range(3)
    )
    three_alternatives = infer_affine_consensus_alignments(
        three_anchors,
        residual_threshold_ms=1_000,
        minimum_scale=0.95,
        maximum_scale=1.05,
    )
    three_selected, three_decision = select_affine_consensus_alignment(
        three_alternatives,
        policy(),
    )
    require(
        len(three_selected.anchors) == 3
        and three_decision.verdict == UNRESOLVED
        and decide_alignment_acceptance(
            three_selected.alignment,
            policy(),
        ).verdict != ACCEPT_HYBRID,
        "INSUFFICIENT_ANCHORS_CANNOT_ACCEPT_HYBRID",
    )
    require(
        infer_affine_consensus_alignments(
            three_anchors[:2],
            residual_threshold_ms=1_000,
            minimum_scale=0.95,
            maximum_scale=1.05,
        ) == (),
        "INSUFFICIENT_AFFINE_ANCHORS_REJECTED",
    )
    outside_scale = tuple(
        candidate(index, index, 1_000_000 + index * 1_000_000,
                  2_000_000 + index * 1_200_000)
        for index in range(3)
    )
    require(
        infer_affine_consensus_alignments(
            outside_scale,
            residual_threshold_ms=1_000,
            minimum_scale=0.95,
            maximum_scale=1.05,
        ) == (),
        "OUT_OF_RANGE_SCALE_HYPOTHESES_REJECTED",
    )
    with patch.object(
        alignment_module,
        "MAX_AFFINE_CONSENSUS_HYPOTHESES",
        0,
    ):
        expect_raises(
            AlignmentLimitError,
            lambda: infer_affine_consensus_alignments(
                three_anchors,
                residual_threshold_ms=1_000,
                minimum_scale=0.95,
                maximum_scale=1.05,
            ),
            "PATHOLOGICAL_HYPOTHESIS_BOUND_FAILS_CLOSED",
        )

    print("AFFINE_CONSENSUS_SMOKE_PASS")


if __name__ == "__main__":
    main()
