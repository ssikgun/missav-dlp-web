"""Offline smoke tests for the isolated Stage11 R3 alignment foundation."""

from dataclasses import FrozenInstanceError, fields
import math
from pathlib import Path

from teddy_discovery_alignment import (
    AlignmentAmbiguityError,
    AlignmentLimitError,
    AlignmentValidationError,
    AnchorTimingEvidence,
    DEFAULT_MINIMUM_LEXICAL_SCORE,
    JapaneseComparisonEvidence,
    MAX_ALIGNMENT_TEXT_CHARS,
    MAX_ANCHOR_CANDIDATES,
    MAX_LEXICAL_PAIR_COMPARISONS,
    MonotonicAnchorCandidate,
    generate_monotonic_anchor_candidates,
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
        661 * 166 <= MAX_LEXICAL_PAIR_COMPARISONS,
        "KNOWN_CARDINALITY_WITHIN_PAIR_BOUND",
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
        ("affine", "NO_AFFINE_LOGIC"),
        ("scale", "NO_SCALE_LOGIC"),
        ("intercept", "NO_INTERCEPT_LOGIC"),
        ("residual", "NO_RESIDUAL_LOGIC"),
        ("inlier", "NO_INLIER_LOGIC"),
        ("open(", "NO_FILESYSTEM_IO"),
        ("urllib", "NO_NETWORK_IO"),
        ("subprocess", "NO_SUBPROCESS_IO"),
        ("sqlite", "NO_DATABASE_IO"),
    ):
        require(forbidden not in source_text, marker)

    print("ALIGNMENT_SMOKE_PASS")


if __name__ == "__main__":
    main()
