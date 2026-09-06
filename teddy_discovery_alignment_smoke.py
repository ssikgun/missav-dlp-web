"""Offline smoke tests for the isolated Stage11 R3 alignment foundation."""

from dataclasses import FrozenInstanceError, fields, replace
import math
from pathlib import Path

from teddy_discovery_alignment import (
    AlignmentAmbiguityError,
    AlignmentLimitError,
    AlignmentValidationError,
    AffineAnchorResidual,
    AnchorTimingEvidence,
    DEFAULT_MINIMUM_LEXICAL_SCORE,
    JapaneseComparisonEvidence,
    MAX_AFFINE_ANCHORS,
    MAX_ALIGNMENT_TEXT_CHARS,
    MAX_ANCHOR_CANDIDATES,
    MAX_LEXICAL_PAIR_COMPARISONS,
    MIN_AFFINE_ANCHORS,
    MonotonicAnchorCandidate,
    RobustAffineAlignment,
    generate_monotonic_anchor_candidates,
    infer_robust_affine_alignment,
    japanese_lexical_similarity,
    normalize_japanese_for_matching,
    select_monotonic_anchors,
)
from teddy_discovery_asr import (
    ASRResult,
    ASRSegment,
    ASRSourceSnapshot,
    ASRWord,
)
from teddy_discovery_hybrid_evidence import (
    ALIGNMENT_PROVENANCE_ASR_ONLY,
    ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
    HybridAlignmentProvenance,
    HybridEvidenceBundle,
    HybridCueIdentity,
    HybridEvidenceValidationError,
)
from teddy_discovery_subtitle import (
    CanonicalVideoHolding,
    SubtitleCandidate,
    validate_canonical_holding,
)
from teddy_discovery_subtitle_external import ExternalSubtitlePayload


DVD_ID = "ABC-123"
JA_URL = "https://cdn.example.test/subs/123/TITLE.ja.srt"
JA_BYTES = (
    "1\n"
    "00:00:01,000 --> 00:00:02,500\n"
    "猫です\n"
    "\n"
    "2\n"
    "00:00:03,000 --> 00:00:04,500\n"
    "こんにちは\n"
    "\n"
    "3\n"
    "00:00:05,000 --> 00:00:06,500\n"
    "さようなら\n"
).encode("utf-8")


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


def holding(dvd_id: str = DVD_ID) -> CanonicalVideoHolding:
    prefix = dvd_id.split("-", 1)[0]
    return validate_canonical_holding(
        {
            "dvd_id": dvd_id,
            "storage_root": "jav",
            "relative_path": f"{prefix}/{dvd_id}/{dvd_id}.mp4",
            "parse_status": "MATCHED",
            "present": 1,
        },
        dvd_id,
    )


def asr_result(dvd_id: str = DVD_ID) -> ASRResult:
    snapshot = ASRSourceSnapshot.from_holding(
        holding(dvd_id),
        source_size=123_456,
        source_mtime_ns=987_654_321,
    )
    return ASRResult(
        source_snapshot=snapshot,
        source_language="ja",
        segments=(
            ASRSegment(
                1_000,
                2_500,
                "猫です",
                (ASRWord(1_100, 1_700, "猫"),),
            ),
            ASRSegment(
                3_000,
                4_500,
                "こんにちは",
                (ASRWord(3_100, 3_700, "こんにちは"),),
            ),
            ASRSegment(
                5_000,
                6_500,
                "さようなら",
                (ASRWord(5_100, 5_700, "さようなら"),),
            ),
        ),
        engine_version="smoke-engine",
    )


def asr_result_for_texts(
    texts: tuple[str, ...],
    dvd_id: str = DVD_ID,
) -> ASRResult:
    snapshot = ASRSourceSnapshot.from_holding(
        holding(dvd_id),
        source_size=123_456,
        source_mtime_ns=987_654_321,
    )
    segments = tuple(
        ASRSegment(
            index * 1_000 + 1_000,
            index * 1_000 + 1_500,
            text,
        )
        for index, text in enumerate(texts)
    )
    return ASRResult(
        source_snapshot=snapshot,
        source_language="ja",
        segments=segments,
        engine_version="smoke-engine",
    )


def subtitle_bytes(texts: tuple[str, ...]) -> bytes:
    def timestamp(milliseconds: int) -> str:
        hours, remainder = divmod(milliseconds, 60 * 60 * 1_000)
        minutes, remainder = divmod(remainder, 60 * 1_000)
        seconds, milliseconds = divmod(remainder, 1_000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

    blocks = []
    for index, text in enumerate(texts, start=1):
        start_ms = index * 1_000
        end_ms = start_ms + 500

        start_timestamp = timestamp(start_ms)
        end_timestamp = timestamp(end_ms)
        blocks.append(
            f"{index}\n"
            f"{start_timestamp} --> {end_timestamp}\n"
            f"{text}"
        )
    return ("\n\n".join(blocks) + "\n").encode("utf-8")


def hybrid_bundle_for_texts(
    external_texts: tuple[str, ...],
    asr_texts: tuple[str, ...],
) -> HybridEvidenceBundle:
    candidate = SubtitleCandidate.validated_external_text(
        JA_URL,
        dvd_id=DVD_ID,
        language="ja",
        text_format="srt",
    )
    payload = ExternalSubtitlePayload.from_bytes(
        dvd_id=DVD_ID,
        candidate=candidate,
        payload=subtitle_bytes(external_texts),
    )
    return HybridEvidenceBundle.from_external_ja_and_asr(
        dvd_id=DVD_ID,
        external_ja_payload=payload,
        external_ja_document=payload.parse(),
        asr_result=asr_result_for_texts(asr_texts),
        alignment=HybridAlignmentProvenance(
            ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
            "not_yet_aligned",
        ),
    )


def hybrid_bundle() -> HybridEvidenceBundle:
    candidate = SubtitleCandidate.validated_external_text(
        JA_URL,
        dvd_id=DVD_ID,
        language="ja",
        text_format="srt",
    )
    payload = ExternalSubtitlePayload.from_bytes(
        dvd_id=DVD_ID,
        candidate=candidate,
        payload=JA_BYTES,
    )
    document = payload.parse()
    return HybridEvidenceBundle.from_external_ja_and_asr(
        dvd_id=DVD_ID,
        external_ja_payload=payload,
        external_ja_document=document,
        asr_result=asr_result(),
        alignment=HybridAlignmentProvenance(
            ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
            "not_yet_aligned",
        ),
    )


def candidate(
    external_index: int,
    asr_index: int,
    external_text: str,
    asr_text: str,
) -> MonotonicAnchorCandidate:
    external_normalized = normalize_japanese_for_matching(external_text)
    asr_normalized = normalize_japanese_for_matching(asr_text)
    return MonotonicAnchorCandidate(
        external_identity=HybridCueIdentity.for_external_ja(external_index),
        asr_identity=HybridCueIdentity.for_asr_segment(asr_index),
        comparison=JapaneseComparisonEvidence(
            external_normalized=external_normalized,
            asr_normalized=asr_normalized,
        ),
        timing=AnchorTimingEvidence(
            external_start_ms=external_index * 1_000 + 1,
            external_end_ms=external_index * 1_000 + 500,
            asr_start_ms=asr_index * 1_000 + 1,
            asr_end_ms=asr_index * 1_000 + 500,
        ),
        score=japanese_lexical_similarity(
            external_normalized,
            asr_normalized,
        ),
    )


def timed_candidate(
    external_index: int,
    asr_index: int,
    external_start_ms: int,
    external_end_ms: int,
    asr_start_ms: int,
    asr_end_ms: int,
) -> MonotonicAnchorCandidate:
    return replace(
        candidate(external_index, asr_index, "同じ", "同じ"),
        timing=AnchorTimingEvidence(
            external_start_ms=external_start_ms,
            external_end_ms=external_end_ms,
            asr_start_ms=asr_start_ms,
            asr_end_ms=asr_end_ms,
        ),
    )


def main():
    # Matching normalization is NFKC + case-fold + removal of Unicode
    # whitespace/punctuation, while Japanese lexical content remains intact.
    require(
        normalize_japanese_for_matching("ＡＢＣ　猫") == "abc猫",
        "NFKC_FULLWIDTH_HALFWIDTH_AND_CASE",
    )
    require(
        normalize_japanese_for_matching("猫  です")
        == normalize_japanese_for_matching("猫\u3000です"),
        "ORDINARY_WHITESPACE_DIFFERENCE",
    )
    require(
        normalize_japanese_for_matching("猫。です！")
        == normalize_japanese_for_matching("猫,です"),
        "UNICODE_PUNCTUATION_DIFFERENCE",
    )
    require(
        normalize_japanese_for_matching("ABC")
        == normalize_japanese_for_matching("abc"),
        "LATIN_CASE_DIFFERENCE",
    )
    require(
        normalize_japanese_for_matching("漢字かなカナ") == "漢字かなカナ",
        "JAPANESE_LEXICAL_CONTENT_PRESERVED",
    )
    require(
        normalize_japanese_for_matching("ｶﾅ") == "カナ",
        "HALFWIDTH_KATAKANA_NFKC_ONLY",
    )
    require(
        normalize_japanese_for_matching("") == ""
        and normalize_japanese_for_matching("　。!?") == "",
        "EMPTY_AFTER_NORMALIZATION_UNUSABLE",
    )
    expect_raises(
        AlignmentValidationError,
        lambda: normalize_japanese_for_matching("猫\nです"),
        "CONTROL_CHARACTER_REJECTED",
    )
    expect_raises(
        AlignmentValidationError,
        lambda: normalize_japanese_for_matching("猫".encode("utf-8")),
        "NON_STRING_REJECTED",
    )
    expect_raises(
        AlignmentLimitError,
        lambda: normalize_japanese_for_matching("猫" * (MAX_ALIGNMENT_TEXT_CHARS + 1)),
        "NORMALIZATION_INPUT_BOUND_REJECTED",
    )

    # Similarity is deterministic lexical evidence and does not inspect
    # timestamps.
    repeated_left = japanese_lexical_similarity("ＡＢＣ。", "abc")
    repeated_right = japanese_lexical_similarity("ＡＢＣ。", "abc")
    require(
        repeated_left == repeated_right == 1.0,
        "DETERMINISTIC_SCORE_AND_IDENTICAL_SCORE",
    )
    different_score = japanese_lexical_similarity("猫", "犬")
    require(
        math.isfinite(different_score)
        and 0.0 <= different_score <= 1.0
        and different_score < 1.0,
        "DIFFERENT_TEXT_LOWER_SCORE",
    )
    expect_raises(
        AlignmentValidationError,
        lambda: japanese_lexical_similarity("。", "!"),
        "EMPTY_NORMALIZED_SIMILARITY_REJECTED",
    )

    bundle = hybrid_bundle()
    generated = generate_monotonic_anchor_candidates(
        bundle,
        minimum_score=1.0,
    )
    require(
        isinstance(generated, tuple)
        and len(generated) == 3
        and len(generated) <= MAX_ANCHOR_CANDIDATES
        and tuple(
            (item.external_cue_index, item.asr_segment_index, item.score)
            for item in generated
        )
        == ((0, 0, 1.0), (1, 1, 1.0), (2, 2, 1.0)),
        "BOUNDED_ORDERED_CANDIDATE_GENERATION",
    )
    selected_generated = select_monotonic_anchors(generated)
    require(
        selected_generated == generated
        and tuple(item.external_cue_index for item in selected_generated)
        == (0, 1, 2)
        and tuple(item.asr_segment_index for item in selected_generated)
        == (0, 1, 2),
        "VALID_ONE_TO_ONE_MONOTONIC_ANCHORS",
    )
    require(
        generated[0].timing.external_start_ms == 1_000
        and generated[0].timing.asr_start_ms == 1_000,
        "SOURCE_TIMESTAMPS_RETAINED_AS_EVIDENCE",
    )

    # Cardinality is intentionally unrelated to ordinal proximity: the early
    # external cue matches a later ASR segment, while the late external cue
    # matches the first ASR segment.  Both pairs must be discovered.
    cardinality_bundle = hybrid_bundle_for_texts(
        (
            "早い対象",
            "外れ一",
            "外れ二",
            "外れ三",
            "外れ四",
            "外れ五",
            "外れ六",
            "遅い対象",
        ),
        ("遅い対象", "早い対象"),
    )
    cardinality_candidates = generate_monotonic_anchor_candidates(
        cardinality_bundle,
        minimum_score=1.0,
    )
    cardinality_pairs = tuple(
        (item.external_cue_index, item.asr_segment_index)
        for item in cardinality_candidates
    )
    require(
        len(cardinality_bundle.external_ja_cues) == 8
        and len(cardinality_bundle.asr_result.segments) == 2
        and cardinality_pairs == ((0, 1), (7, 0)),
        "CARDINALITY_INDEPENDENT_ALL_PAIR_DISCOVERY",
    )
    expect_raises(
        AlignmentAmbiguityError,
        lambda: select_monotonic_anchors(cardinality_candidates),
        "GENERATED_CROSSING_PAIRS_FAIL_CLOSED",
    )

    # The known real cardinality remains under the generic resource bound.
    require(
        MAX_LEXICAL_PAIR_COMPARISONS == 256_000
        and
        661 * 166 <= MAX_LEXICAL_PAIR_COMPARISONS,
        "V2_3B_PAIR_BOUND_UNCHANGED_AND_KNOWN_CARDINALITY_SAFE",
    )

    # Exact product boundary: pair evaluation is allowed at the cap, while
    # one additional ASR segment crosses it and fails before any sampling.
    boundary_external_count = 8
    boundary_asr_count = MAX_LEXICAL_PAIR_COMPARISONS // boundary_external_count
    require(
        boundary_external_count * boundary_asr_count
        == MAX_LEXICAL_PAIR_COMPARISONS,
        "PAIR_BOUNDARY_FIXTURE_EXACT",
    )
    boundary_bundle = hybrid_bundle_for_texts(
        tuple("外部" for _ in range(boundary_external_count)),
        tuple("ASR" for _ in range(boundary_asr_count)),
    )
    require(
        generate_monotonic_anchor_candidates(
            boundary_bundle,
            minimum_score=1.0,
        )
        == (),
        "PAIR_COMPARISON_BOUNDARY_ACCEPTED",
    )
    over_bound_bundle = hybrid_bundle_for_texts(
        tuple("外部" for _ in range(boundary_external_count)),
        tuple("ASR" for _ in range(boundary_asr_count + 1)),
    )
    expect_raises(
        AlignmentLimitError,
        lambda: generate_monotonic_anchor_candidates(
            over_bound_bundle,
            minimum_score=1.0,
        ),
        "PAIR_COMPARISON_BOUNDARY_EXCEEDED_REJECTED",
    )

    # The product may be safe while the retained candidate collection is not.
    candidate_overflow_bundle = hybrid_bundle_for_texts(
        tuple("동일" for _ in range(65)),
        tuple("동일" for _ in range(65)),
    )
    expect_raises(
        AlignmentLimitError,
        lambda: generate_monotonic_anchor_candidates(
            candidate_overflow_bundle,
            minimum_score=1.0,
        ),
        "CANDIDATE_COUNT_BOUND_REJECTED",
    )

    # Crossing mappings cannot both be selected; the stronger one wins when
    # there is no equal-strength ambiguity.
    crossing = (
        candidate(0, 1, "猫", "猫"),
        candidate(1, 0, "犬", "犬犬"),
    )
    crossing_selected = select_monotonic_anchors(crossing)
    require(
        len(crossing_selected) == 1
        and crossing_selected[0].external_cue_index == 0
        and crossing_selected[0].asr_segment_index == 1,
        "CROSSING_CANDIDATES_NOT_BOTH_SELECTED",
    )

    duplicate_source = (
        candidate(0, 0, "猫", "猫"),
        candidate(0, 1, "猫", "猫犬"),
        candidate(1, 2, "犬", "犬"),
    )
    duplicate_source_selected = select_monotonic_anchors(duplicate_source)
    require(
        tuple(
            (item.external_cue_index, item.asr_segment_index)
            for item in duplicate_source_selected
        )
        == ((0, 0), (1, 2)),
        "DUPLICATE_SOURCE_USAGE_NOT_SELECTED",
    )

    # Equal-strength crossing mappings have two optimal answers and therefore
    # fail closed instead of receiving an arbitrary deterministic guess.
    ambiguous = (
        candidate(0, 1, "猫", "猫"),
        candidate(1, 0, "犬", "犬"),
    )
    expect_raises(
        AlignmentAmbiguityError,
        lambda: select_monotonic_anchors(ambiguous),
        "AMBIGUOUS_EQUAL_STRENGTH_REJECTED",
    )

    # Candidate order is canonicalized by source indexes, so a unique result
    # is stable even when callers supply candidates in another order.
    deterministic_tie = (
        candidate(0, 0, "猫", "猫"),
        candidate(0, 1, "猫", "犬猫"),
        candidate(1, 1, "犬", "犬"),
    )
    forward = select_monotonic_anchors(deterministic_tie)
    reverse = select_monotonic_anchors(tuple(reversed(deterministic_tie)))
    require(
        forward == reverse
        and tuple(
            (item.external_cue_index, item.asr_segment_index)
            for item in forward
        )
        == ((0, 0), (1, 1)),
        "DETERMINISTIC_TIE_ORDER",
    )
    expect_raises(
        AlignmentValidationError,
        lambda: select_monotonic_anchors((deterministic_tie[0], deterministic_tie[0])),
        "DUPLICATE_CANDIDATE_PAIR_REJECTED",
    )

    # Invalid identities/indexes are rejected before lexical selection.
    expect_raises(
        HybridEvidenceValidationError,
        lambda: HybridCueIdentity.for_external_ja(-1),
        "NEGATIVE_SOURCE_INDEX_REJECTED",
    )
    expect_raises(
        HybridEvidenceValidationError,
        lambda: HybridCueIdentity.for_external_ja(True),
        "BOOLEAN_SOURCE_INDEX_REJECTED",
    )
    expect_raises(
        HybridEvidenceValidationError,
        lambda: HybridCueIdentity(
            cue_id="wrong-id",
            source="external_ja",
            source_index=0,
        ),
        "UNSTABLE_SOURCE_ID_REJECTED",
    )

    # The minimum score is an explicit exact-float boundary.  The generic
    # default is only a conservative smoke-level policy, not a production
    # qualification.
    require(
        isinstance(DEFAULT_MINIMUM_LEXICAL_SCORE, float)
        and len(generate_monotonic_anchor_candidates(bundle, minimum_score=1.0)) == 3,
        "THRESHOLD_INCLUSIVE_BOUNDARY",
    )
    for invalid_threshold, marker in (
        (True, "BOOLEAN_THRESHOLD_REJECTED"),
        (1, "INTEGER_THRESHOLD_REJECTED"),
        (-0.01, "NEGATIVE_THRESHOLD_REJECTED"),
        (1.01, "OVER_ONE_THRESHOLD_REJECTED"),
        (math.nan, "NAN_THRESHOLD_REJECTED"),
        (math.inf, "INFINITE_THRESHOLD_REJECTED"),
    ):
        expect_raises(
            AlignmentValidationError,
            lambda value=invalid_threshold: generate_monotonic_anchor_candidates(
                bundle,
                minimum_score=value,
            ),
            marker,
        )
    expect_raises(
        AlignmentValidationError,
        lambda: JapaneseComparisonEvidence("猫。", "猫"),
        "UNNORMALIZED_COMPARISON_EVIDENCE_REJECTED",
    )
    expect_raises(
        AlignmentValidationError,
        lambda: AnchorTimingEvidence(1, 2, True, 3),
        "BOOLEAN_TIMESTAMP_REJECTED",
    )

    # V2-3D uses exact doubled-integer midpoint evidence and a deterministic
    # Theil-Sen-style fit.  Source intervals deliberately have different
    # durations and their starts do not carry the tested affine relationship.
    exact_affine_anchors = (
        timed_candidate(0, 0, 0, 1_000, 650, 800),
        timed_candidate(1, 1, 1_200, 1_800, 1_880, 2_070),
        timed_candidate(2, 2, 2_500, 3_500, 3_750, 3_950),
        timed_candidate(3, 3, 4_100, 4_500, 5_300, 5_650),
    )
    exact_affine = infer_robust_affine_alignment(
        exact_affine_anchors,
        residual_threshold_ms=1,
    )
    require(
        math.isclose(exact_affine.scale, 1.25, abs_tol=1e-12)
        and math.isclose(exact_affine.intercept_ms, 100.0, abs_tol=1e-12)
        and exact_affine.anchor_count == 4
        and exact_affine.inlier_count == 4
        and all(
            residual.absolute_residual_ms == 0.0
            and residual.is_inlier
            for residual in exact_affine.residuals
        ),
        "EXACT_AFFINE_RECOVERED_FROM_MIDPOINTS",
    )
    require(
        tuple(
            residual.external_identity.source_index
            for residual in exact_affine.residuals
        )
        == (0, 1, 2, 3)
        and tuple(
            residual.asr_identity.source_index
            for residual in exact_affine.residuals
        )
        == (0, 1, 2, 3)
        and exact_affine.residuals[0].external_midpoint_x2 == 1_000
        and exact_affine.residuals[0].asr_midpoint_x2 == 1_450
        and exact_affine.residuals[0].external_midpoint_ms == 500.0
        and exact_affine.residuals[0].asr_midpoint_ms == 725.0,
        "MIDPOINT_EVIDENCE_AND_SELECTED_ORDER_PRESERVED",
    )

    offset_only_anchors = (
        timed_candidate(0, 0, 0, 1_000, 700, 800),
        timed_candidate(1, 1, 1_200, 1_800, 1_600, 1_900),
        timed_candidate(2, 2, 2_500, 3_500, 3_150, 3_350),
        timed_candidate(3, 3, 4_100, 4_500, 4_400, 4_700),
    )
    offset_only = infer_robust_affine_alignment(
        offset_only_anchors,
        residual_threshold_ms=1,
    )
    require(
        math.isclose(offset_only.scale, 1.0, abs_tol=1e-12)
        and math.isclose(offset_only.intercept_ms, 250.0, abs_tol=1e-12)
        and offset_only.inlier_count == 4,
        "OFFSET_ONLY_AFFINE_RECOVERED",
    )

    drift_anchors = (
        timed_candidate(0, 0, 0, 1_000, 540, 640),
        timed_candidate(1, 1, 1_200, 1_800, 1_550, 1_670),
        timed_candidate(2, 2, 2_500, 3_500, 3_040, 3_240),
        timed_candidate(3, 3, 4_100, 4_500, 4_350, 4_582),
    )
    drift = infer_robust_affine_alignment(
        drift_anchors,
        residual_threshold_ms=1,
    )
    require(
        math.isclose(drift.scale, 1.02, abs_tol=1e-12)
        and math.isclose(drift.intercept_ms, 80.0, abs_tol=1e-12)
        and drift.inlier_count == 4,
        "DRIFT_AFFINE_RECOVERED",
    )

    robust_outlier_anchors = (
        timed_candidate(0, 0, 50, 150, 110, 210),
        timed_candidate(1, 1, 650, 750, 770, 870),
        timed_candidate(2, 2, 1_250, 1_350, 1_430, 1_530),
        timed_candidate(3, 3, 1_950, 2_050, 2_200, 2_300),
        timed_candidate(4, 4, 2_750, 2_850, 3_080, 3_180),
        timed_candidate(5, 5, 3_450, 3_550, 11_950, 12_050),
    )
    robust_outlier = infer_robust_affine_alignment(
        robust_outlier_anchors,
        residual_threshold_ms=5,
    )
    require(
        math.isclose(robust_outlier.scale, 1.1, abs_tol=1e-12)
        and math.isclose(robust_outlier.intercept_ms, 50.0, abs_tol=1e-12)
        and robust_outlier.inlier_count == 5
        and all(
            residual.is_inlier
            for residual in robust_outlier.residuals[:5]
        )
        and not robust_outlier.residuals[-1].is_inlier
        and robust_outlier.residuals[-1].absolute_residual_ms > 5.0,
        "ROBUST_OUTLIER_RETAINED_AS_OUTLIER",
    )

    boundary_anchors = (
        timed_candidate(0, 0, 50, 150, 50, 150),
        timed_candidate(1, 1, 150, 250, 150, 250),
        timed_candidate(2, 2, 250, 350, 250, 350),
        timed_candidate(3, 3, 350, 450, 350, 450),
        timed_candidate(4, 4, 450, 550, 460, 560),
    )
    residual_at_boundary = infer_robust_affine_alignment(
        boundary_anchors,
        residual_threshold_ms=10,
    )
    residual_over_boundary = infer_robust_affine_alignment(
        boundary_anchors,
        residual_threshold_ms=9,
    )
    require(
        residual_at_boundary.residuals[-1].absolute_residual_ms == 10.0
        and residual_at_boundary.residuals[-1].is_inlier
        and not residual_over_boundary.residuals[-1].is_inlier,
        "RESIDUAL_THRESHOLD_EQUALITY_BOUNDARY",
    )

    require(
        MIN_AFFINE_ANCHORS == 3
        and 89 <= MAX_AFFINE_ANCHORS == 512,
        "AFFINE_RESOURCE_BOUNDS_COVER_PRIOR_EVIDENCE",
    )
    max_affine_anchors = tuple(
        timed_candidate(
            index,
            index,
            index * 2_000,
            index * 2_000 + 1_000,
            index * 2_000 + 100,
            index * 2_000 + 1_100,
        )
        for index in range(MAX_AFFINE_ANCHORS)
    )
    max_affine = infer_robust_affine_alignment(
        max_affine_anchors,
        residual_threshold_ms=1,
    )
    require(
        max_affine.anchor_count == MAX_AFFINE_ANCHORS,
        "MAX_AFFINE_ANCHOR_BOUNDARY_ACCEPTED",
    )
    expect_raises(
        AlignmentLimitError,
        lambda: infer_robust_affine_alignment(
            max_affine_anchors
            + (
                timed_candidate(
                    MAX_AFFINE_ANCHORS,
                    MAX_AFFINE_ANCHORS,
                    MAX_AFFINE_ANCHORS * 2_000,
                    MAX_AFFINE_ANCHORS * 2_000 + 1_000,
                    MAX_AFFINE_ANCHORS * 2_000 + 100,
                    MAX_AFFINE_ANCHORS * 2_000 + 1_100,
                ),
            ),
            residual_threshold_ms=1,
        ),
        "OVER_MAX_AFFINE_ANCHOR_BOUND_REJECTED",
    )

    # Affine input is already selected monotonic evidence: malformed order,
    # duplicate source use, non-tuple input, and unsupported members fail
    # closed without reordering or repair.
    expect_raises(
        AlignmentValidationError,
        lambda: infer_robust_affine_alignment(
            exact_affine_anchors[:2],
            residual_threshold_ms=1,
        ),
        "TOO_FEW_AFFINE_ANCHORS_REJECTED",
    )
    expect_raises(
        AlignmentValidationError,
        lambda: infer_robust_affine_alignment(
            list(exact_affine_anchors),
            residual_threshold_ms=1,
        ),
        "NON_TUPLE_AFFINE_INPUT_REJECTED",
    )
    expect_raises(
        AlignmentValidationError,
        lambda: infer_robust_affine_alignment(
            (object(), exact_affine_anchors[1], exact_affine_anchors[2]),
            residual_threshold_ms=1,
        ),
        "WRONG_AFFINE_MEMBER_REJECTED",
    )
    expect_raises(
        AlignmentValidationError,
        lambda: infer_robust_affine_alignment(
            (
                exact_affine_anchors[0],
                exact_affine_anchors[0],
                exact_affine_anchors[2],
            ),
            residual_threshold_ms=1,
        ),
        "DUPLICATE_AFFINE_SOURCE_REJECTED",
    )
    expect_raises(
        AlignmentValidationError,
        lambda: infer_robust_affine_alignment(
            (
                exact_affine_anchors[0],
                exact_affine_anchors[2],
                exact_affine_anchors[1],
            ),
            residual_threshold_ms=1,
        ),
        "OUT_OF_ORDER_AFFINE_INPUT_REJECTED",
    )
    expect_raises(
        AlignmentValidationError,
        lambda: infer_robust_affine_alignment(
            (
                timed_candidate(0, 0, 100, 300, 100, 200),
                timed_candidate(1, 1, 100, 300, 300, 400),
                timed_candidate(2, 2, 100, 300, 500, 600),
            ),
            residual_threshold_ms=1,
        ),
        "NO_DISTINCT_EXTERNAL_MIDPOINTS_REJECTED",
    )

    zero_scale_anchors = (
        timed_candidate(0, 0, 50, 150, 450, 550),
        timed_candidate(1, 1, 150, 250, 450, 550),
        timed_candidate(2, 2, 250, 350, 450, 550),
    )
    expect_raises(
        AlignmentValidationError,
        lambda: infer_robust_affine_alignment(
            zero_scale_anchors,
            residual_threshold_ms=1,
        ),
        "ZERO_AFFINE_SCALE_REJECTED",
    )
    negative_scale_anchors = (
        timed_candidate(0, 0, 50, 150, 250, 350),
        timed_candidate(1, 1, 150, 250, 150, 250),
        timed_candidate(2, 2, 250, 350, 50, 150),
    )
    expect_raises(
        AlignmentValidationError,
        lambda: infer_robust_affine_alignment(
            negative_scale_anchors,
            residual_threshold_ms=1,
        ),
        "NEGATIVE_AFFINE_SCALE_REJECTED",
    )
    for invalid_residual_threshold, marker in (
        (True, "BOOLEAN_RESIDUAL_THRESHOLD_REJECTED"),
        (0, "ZERO_RESIDUAL_THRESHOLD_REJECTED"),
        (-1, "NEGATIVE_RESIDUAL_THRESHOLD_REJECTED"),
        (1.0, "FLOAT_RESIDUAL_THRESHOLD_REJECTED"),
    ):
        expect_raises(
            AlignmentValidationError,
            lambda value=invalid_residual_threshold: infer_robust_affine_alignment(
                exact_affine_anchors,
                residual_threshold_ms=value,
            ),
            marker,
        )

    malformed_timing = object.__new__(AnchorTimingEvidence)
    object.__setattr__(malformed_timing, "external_start_ms", 10**400)
    object.__setattr__(malformed_timing, "external_end_ms", 10**400 + 2)
    object.__setattr__(malformed_timing, "asr_start_ms", 1)
    object.__setattr__(malformed_timing, "asr_end_ms", 2)
    expect_raises(
        AlignmentValidationError,
        lambda: infer_robust_affine_alignment(
            (
                replace(exact_affine_anchors[0], timing=malformed_timing),
                exact_affine_anchors[1],
                exact_affine_anchors[2],
            ),
            residual_threshold_ms=1,
        ),
        "NONFINITE_MIDPOINT_CONVERSION_REJECTED",
    )

    # A frozen result cannot be mutated, and its residual collection is an
    # immutable tuple of source identities rather than dialogue or output
    # subtitle timing.
    require(
        isinstance(exact_affine.residuals, tuple)
        and exact_affine.anchor_residuals is exact_affine.residuals,
        "IMMUTABLE_AFFINE_RESIDUAL_TUPLE",
    )
    expect_raises(
        FrozenInstanceError,
        lambda: setattr(exact_affine, "scale", 2.0),
        "ROBUST_AFFINE_RESULT_FROZEN",
    )

    # ASR_ONLY has no external document, so candidate generation remains an
    # empty immutable result and cannot fabricate external anchors.
    asr_only = HybridEvidenceBundle.from_asr_only(
        dvd_id=DVD_ID,
        asr_result=asr_result(),
        alignment=HybridAlignmentProvenance(
            ALIGNMENT_PROVENANCE_ASR_ONLY,
            "asr_source_only",
        ),
    )
    require(
        generate_monotonic_anchor_candidates(asr_only) == (),
        "ASR_ONLY_DOES_NOT_FABRICATE_EXTERNAL_ANCHORS",
    )

    # All public contract objects are frozen, and there is no output timestamp
    # owner or title-specific production branch in this checkpoint.
    for contract_type in (
        JapaneseComparisonEvidence,
        AnchorTimingEvidence,
        MonotonicAnchorCandidate,
        AffineAnchorResidual,
        RobustAffineAlignment,
    ):
        require(
            getattr(contract_type.__dataclass_params__, "frozen", False),
            contract_type.__name__ + "_FROZEN",
        )
        field_names = {field.name for field in fields(contract_type)}
        require(
            not field_names.intersection(
                {
                    "output_start_ms",
                    "output_end_ms",
                    "generated_start_ms",
                    "generated_end_ms",
                    "llm_start_ms",
                    "llm_end_ms",
                }
            ),
            contract_type.__name__ + "_NO_OUTPUT_TIMESTAMP_OWNER",
        )

    alignment_source = Path(__file__).with_name("teddy_discovery_alignment.py")
    source_text = alignment_source.read_text(encoding="utf-8").lower()
    for forbidden, marker in (
        ("jur", "NO_TITLE_SPECIFIC_PRODUCTION_STRING"),
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

    print("ALIGNMENT_SMOKE_PASS")


if __name__ == "__main__":
    main()
