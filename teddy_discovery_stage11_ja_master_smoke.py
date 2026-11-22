"""Small offline checks for the Stage11 JA Master evidence boundary."""

from fractions import Fraction
from dataclasses import replace

from teddy_discovery_alignment import (
    AnchorTimingEvidence,
    JapaneseComparisonEvidence,
    MonotonicAnchorCandidate,
    infer_robust_affine_alignment,
    japanese_lexical_similarity,
)
from teddy_discovery_alignment_acceptance import (
    ACCEPT_HYBRID,
    AlignmentAcceptancePolicy,
    REJECT_EXTERNAL,
    decide_alignment_acceptance,
)
from teddy_discovery_alignment_application import apply_alignment_acceptance
from teddy_discovery_asr import ASRResult, ASRSegment, ASRSourceSnapshot
from teddy_discovery_hybrid_evidence import (
    ALIGNMENT_PROVENANCE_UNRESOLVED,
    HybridAlignmentProvenance,
    HybridCueIdentity,
    HybridEvidenceBundle,
)
from teddy_discovery_stage11_ja_master import (
    DECISION_ACCEPTED,
    DECISION_REJECTED,
    DECISION_UNCERTAIN,
    JAMasterDecision,
    JAMasterValidationError,
    RELATION_ASR_ONLY,
    RELATION_EXTERNAL_ONLY,
    RELATION_MATCHED,
    RELATION_POTENTIAL_CONFLICT,
    ROUTE_EXTERNAL_ALIGNMENT_ACCEPTED,
    ROUTE_EXTERNAL_ALIGNMENT_REJECTED,
    ROUTE_ASR_ONLY_NO_EXTERNAL,
    apply_ja_master_decisions,
    build_ja_master_review_set,
)
from teddy_discovery_subtitle import (
    CanonicalVideoHolding,
    SubtitleCandidate,
    validate_canonical_holding,
)
from teddy_discovery_subtitle_external import ExternalSubtitlePayload


DVD_ID = "HSODA-104"
TEXTS = ("ひとつ", "ふたつ", "みっつ", "よっつ", "いつつ", "むっつ")
EXTERNAL_INTERVALS = ((1_000, 1_400), (3_000, 3_400), (5_000, 5_400), (6_500, 8_000), (7_600, 7_800), (10_000, 10_400))
ASR_INTERVALS = ((1_500, 1_900), (3_500, 3_900), (5_500, 5_900), (7_000, 8_500), (8_100, 8_300), (15_000, 15_400))


def require(condition: bool, marker: str) -> None:
    if not condition:
        raise AssertionError(marker)


def expect_raises(exception_type, callback, marker: str) -> None:
    try:
        callback()
    except exception_type:
        return
    except Exception as error:
        raise AssertionError(marker + ": " + type(error).__name__) from error
    raise AssertionError(marker)


def _timestamp(milliseconds: int) -> str:
    hours, remaining = divmod(milliseconds, 3_600_000)
    minutes, remaining = divmod(remaining, 60_000)
    seconds, millis = divmod(remaining, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _subtitle_bytes(intervals, texts) -> bytes:
    blocks = []
    for index, ((start, end), text) in enumerate(zip(intervals, texts), start=1):
        blocks.append(f"{index}\n{_timestamp(start)} --> {_timestamp(end)}\n{text}")
    return ("\n\n".join(blocks) + "\n").encode("utf-8")


def _holding() -> CanonicalVideoHolding:
    return validate_canonical_holding(
        {
            "dvd_id": DVD_ID,
            "storage_root": "jav",
            "relative_path": f"HSODA/{DVD_ID}/{DVD_ID}.mp4",
            "parse_status": "MATCHED",
            "present": 1,
        },
        DVD_ID,
    )


def _asr_result(intervals=ASR_INTERVALS) -> ASRResult:
    return ASRResult(
        source_snapshot=ASRSourceSnapshot.from_holding(
            _holding(), source_size=1_024, source_mtime_ns=1_700_000_000_000
        ),
        source_language="ja",
        segments=tuple(
            ASRSegment(start, end, TEXTS[index % len(TEXTS)])
            for index, (start, end) in enumerate(intervals)
        ),
        engine_version="ja-master-offline-smoke",
    )


def _external_payload() -> ExternalSubtitlePayload:
    return ExternalSubtitlePayload.from_bytes(
        dvd_id=DVD_ID,
        candidate=SubtitleCandidate.validated_external_text(
            "synthetic-ja-source",
            dvd_id=DVD_ID,
            language="ja",
            text_format="srt",
        ),
        payload=_subtitle_bytes(EXTERNAL_INTERVALS, TEXTS),
    )


def _bundle(asr=None, payload=None) -> HybridEvidenceBundle:
    asr = asr or _asr_result()
    provenance = HybridAlignmentProvenance(
        ALIGNMENT_PROVENANCE_UNRESOLVED,
        "source-evidence-before-alignment",
    )
    if payload is None:
        return HybridEvidenceBundle.from_asr_only(
            dvd_id=DVD_ID,
            asr_result=asr,
            alignment=HybridAlignmentProvenance("ASR_ONLY", "external-source-absent"),
        )
    return HybridEvidenceBundle.from_external_ja_and_asr(
        dvd_id=DVD_ID,
        external_ja_payload=payload,
        asr_result=asr,
        alignment=provenance,
    )


def _accepted_application(bundle):
    document = bundle.external_ja_document
    segments = bundle.asr_result.segments
    anchors = []
    for index in range(4):
        ja = document.cues[index]
        asr = segments[index]
        ja_text = ja.text
        asr_text = asr.text
        anchors.append(
            MonotonicAnchorCandidate(
                external_identity=HybridCueIdentity.for_external_ja(index),
                asr_identity=HybridCueIdentity.for_asr_segment(index),
                comparison=JapaneseComparisonEvidence(ja_text, asr_text),
                timing=AnchorTimingEvidence(
                    external_start_ms=ja.start_ms,
                    external_end_ms=ja.end_ms,
                    asr_start_ms=asr.start_ms,
                    asr_end_ms=asr.end_ms,
                ),
                score=japanese_lexical_similarity(ja_text, asr_text),
            )
        )
    alignment = infer_robust_affine_alignment(tuple(anchors), residual_threshold_ms=1)
    policy = AlignmentAcceptancePolicy(4, 4, 1.0, 1.0, 1_000, 0.95, 1.05)
    decision = decide_alignment_acceptance(alignment, policy)
    require(decision.verdict == ACCEPT_HYBRID, "SYNTHETIC_ALIGNMENT_ACCEPTED")
    return apply_alignment_acceptance(bundle, decision, alignment=alignment), alignment


def _decisions(review_set, *, accepted_candidate=None, source_key=None, rejected_candidate=None):
    decisions = []
    for candidate in review_set.candidates:
        if candidate.candidate_id == accepted_candidate:
            decisions.append(
                JAMasterDecision(
                    candidate_id=candidate.candidate_id,
                    status=DECISION_ACCEPTED,
                    selected_source_key=source_key,
                    rationale_code="REVIEW_ACCEPTED",
                )
            )
        elif candidate.candidate_id == rejected_candidate:
            decisions.append(
                JAMasterDecision(
                    candidate_id=candidate.candidate_id,
                    status=DECISION_REJECTED,
                    selected_source_key=None,
                    rationale_code="REVIEW_REJECTED",
                )
            )
        else:
            decisions.append(
                JAMasterDecision(
                    candidate_id=candidate.candidate_id,
                    status=DECISION_UNCERTAIN,
                    selected_source_key=None,
                    rationale_code="REVIEW_PENDING",
                )
            )
    return tuple(decisions)


def main() -> None:
    base = _bundle(payload=_external_payload())
    accepted_application, _ = _accepted_application(base)
    review = build_ja_master_review_set(base, alignment_application=accepted_application)
    repeated = build_ja_master_review_set(base, alignment_application=accepted_application)
    require(
        tuple(item.candidate_id for item in review.candidates)
        == tuple(item.candidate_id for item in repeated.candidates),
        "STABLE_CANDIDATE_IDS",
    )
    relations = [candidate.relation for candidate in review.candidates]
    require(review.route == ROUTE_EXTERNAL_ALIGNMENT_ACCEPTED, "ACCEPTED_ROUTE")
    require(relations.count(RELATION_MATCHED) == 4, "SELECTED_ANCHORS_RETAINED")
    require(relations.count(RELATION_POTENTIAL_CONFLICT) == 1, "PROJECTED_OVERLAP_RETAINED")
    require(relations.count(RELATION_EXTERNAL_ONLY) == 1, "EXTERNAL_ONLY_RETAINED")
    require(all(item.decision_status == DECISION_UNCERTAIN for item in review.candidates), "NO_AUTOMATIC_DECISIONS")

    matched = next(item for item in review.candidates if item.relation == RELATION_MATCHED)
    external_only = next(item for item in review.candidates if item.relation == RELATION_EXTERNAL_ONLY)
    selected_ref = next(ref for ref in matched.source_references if ref.source == "external_ja")
    master = apply_ja_master_decisions(
        review,
        _decisions(
            review,
            accepted_candidate=matched.candidate_id,
            source_key=selected_ref.key,
            rejected_candidate=external_only.candidate_id,
        ),
    )
    require(len(master.cues) == 1 and master.cues[0].start_ms == Fraction(1_500), "EXPLICIT_SOURCE_MATERIALIZED")
    statuses = {candidate.decision_status for candidate in master.candidates}
    require(statuses == {DECISION_ACCEPTED, DECISION_REJECTED, DECISION_UNCERTAIN}, "DECISIONS_RETAINED")

    changed_snapshot = replace(
        base.asr_result.source_snapshot,
        source_size=base.asr_result.source_snapshot.source_size + 1,
    )
    detached_asr = replace(base.asr_result, source_snapshot=changed_snapshot)
    detached_bundle = _bundle(asr=detached_asr, payload=_external_payload())
    detached_application = apply_alignment_acceptance(
        detached_bundle, accepted_application.decision, alignment=accepted_application.alignment
    )
    expect_raises(
        JAMasterValidationError,
        lambda: build_ja_master_review_set(base, alignment_application=detached_application),
        "DETACHED_ASR_SOURCE_REJECTED",
    )

    reject_policy = AlignmentAcceptancePolicy(3, 3, 1.0, 1.0, 1_000, 1.1, 1.2)
    rejected_decision = decide_alignment_acceptance(accepted_application.alignment, reject_policy)
    require(rejected_decision.verdict == REJECT_EXTERNAL, "REJECTED_DECISION_FIXTURE")
    rejected_app = apply_alignment_acceptance(base, rejected_decision)
    rejected_review = build_ja_master_review_set(base, alignment_application=rejected_app)
    require(rejected_review.route == ROUTE_EXTERNAL_ALIGNMENT_REJECTED, "REJECTED_EXTERNAL_ASR_FIRST_ROUTE")
    require(sum(ref.source == "external_ja" for c in rejected_review.candidates for ref in c.source_references) >= len(EXTERNAL_INTERVALS), "REJECTED_EXTERNAL_EVIDENCE_RETAINED")
    rejected_external = next(c for c in rejected_review.candidates if c.relation == RELATION_EXTERNAL_ONLY)
    rejected_ref = rejected_external.source_references[0]
    rejected_decisions = list(_decisions(rejected_review))
    rejected_decisions[rejected_review.candidates.index(rejected_external)] = JAMasterDecision(
        candidate_id=rejected_external.candidate_id,
        status=DECISION_ACCEPTED,
        selected_source_key=rejected_ref.key,
        rationale_code="REVIEW_ACCEPTED",
    )
    expect_raises(
        JAMasterValidationError,
        lambda: apply_ja_master_decisions(rejected_review, tuple(rejected_decisions)),
        "UNALIGNED_EXTERNAL_CANNOT_ENTER_MASTER",
    )

    asr_only = build_ja_master_review_set(_bundle(payload=None))
    require(asr_only.route == ROUTE_ASR_ONLY_NO_EXTERNAL, "MISSING_EXTERNAL_ASR_FIRST_ROUTE")
    require(all(candidate.relation == RELATION_ASR_ONLY for candidate in asr_only.candidates), "ASR_ONLY_CANDIDATES_RETAINED")
    first = asr_only.candidates[0]
    asr_ref = first.source_references[0]
    asr_master = apply_ja_master_decisions(
        asr_only,
        _decisions(asr_only, accepted_candidate=first.candidate_id, source_key=asr_ref.key),
    )
    require(len(asr_master.cues) == 1, "ASR_ONLY_MASTER_INTERFACE")

    expect_raises(
        JAMasterValidationError,
        lambda: apply_ja_master_decisions(review, _decisions(review)[:-1]),
        "DECISION_SET_MUST_BE_COMPLETE",
    )
    print("JA_MASTER_SMOKE=PASS")
    print("SYNTHETIC_MATCHED=4")
    print("SYNTHETIC_POTENTIAL_CONFLICT=1")
    print("SYNTHETIC_EXTERNAL_ONLY=1")
    print("MISSING_AND_REJECTED_EXTERNAL_ROUTES=PASS")
    print("SEMANTIC_AUTO_DECISIONS=0")
    print("MODEL_CALLS=0")


if __name__ == "__main__":
    main()
