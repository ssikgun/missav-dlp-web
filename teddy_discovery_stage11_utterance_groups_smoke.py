"""Representative offline checks for V2-C source-bound utterance groups."""

from dataclasses import replace
from fractions import Fraction
import hashlib

from teddy_discovery_alignment import (
    AnchorTimingEvidence,
    JapaneseComparisonEvidence,
    MonotonicAnchorCandidate,
    infer_robust_affine_alignment,
    japanese_lexical_similarity,
)
from teddy_discovery_alignment_acceptance import (
    AlignmentAcceptancePolicy,
    decide_alignment_acceptance,
)
from teddy_discovery_alignment_application import apply_alignment_acceptance
from teddy_discovery_asr import ASRResult, ASRSegment, ASRSourceSnapshot, ASRWord
from teddy_discovery_hybrid_evidence import (
    ALIGNMENT_PROVENANCE_UNRESOLVED,
    HybridAlignmentProvenance,
    HybridCueIdentity,
    HybridEvidenceBundle,
)
from teddy_discovery_stage11_ja_master import build_ja_master_review_set
from teddy_discovery_stage11_ja_master_smoke import _holding, _timestamp
from teddy_discovery_subtitle import SubtitleCandidate
from teddy_discovery_subtitle_external import ExternalSubtitlePayload
from teddy_discovery_stage11_utterance_groups import (
    ASSOCIATION_OVERLAP_ONLY,
    LINK_TIMELINE_OVERLAP,
    SPEAKER_EVIDENCE_UNASSIGNED,
    SPEAKER_UNKNOWN,
    UTTERANCE_UNRESOLVED,
    SpeakerTurnEvidence,
    UtteranceGroupingError,
    build_utterance_review_plan,
    validate_utterance_review_plan,
)


def require(value, marker):
    if not value:
        raise AssertionError(marker)


def expect_raises(exception_type, function, marker):
    try:
        function()
    except exception_type:
        return
    except Exception as error:
        raise AssertionError(marker + ":" + type(error).__name__) from error
    raise AssertionError(marker)


def _payload():
    intervals = ((1_000, 1_400), (3_000, 3_400), (5_000, 5_400),
                 (6_500, 8_000), (7_600, 7_800), (10_000, 10_400))
    texts = ("one", "two", "three", "four", "four", "six")
    body = "\n\n".join(
        f"{index}\n{_timestamp(start)} --> {_timestamp(end)}\n{text}"
        for index, ((start, end), text) in enumerate(zip(intervals, texts), start=1)
    ).encode("utf-8") + b"\n"
    return ExternalSubtitlePayload.from_bytes(
        dvd_id="HSODA-104",
        candidate=SubtitleCandidate.validated_external_text(
            "synthetic-v2c-ja", dvd_id="HSODA-104", language="ja", text_format="srt"
        ),
        payload=body,
    )


def _review_set():
    intervals = (
        (1_500, 1_900),
        (3_500, 3_900),
        (5_500, 5_900),
        (5_600, 5_700),  # second ASR interval in JA cue 3's time
        (7_000, 8_500),  # one ASR interval spanning two JA cues
        (15_000, 15_400),
    )
    text = ("one", "two", "three", "four-alt", "four", "unmatched")
    words = (
        (), (),
        (ASRWord(5_500, 5_700, "three"), ASRWord(5_700, 5_900, "tail")),
        (ASRWord(5_600, 5_700, "four-alt"),),
        (ASRWord(7_000, 7_500, "four"), ASRWord(7_500, 8_500, "tail")),
        (),
    )
    snapshot = ASRSourceSnapshot.from_holding(
        _holding(), source_size=1_024, source_mtime_ns=1_700_000_000_000
    )
    asr = ASRResult(
        source_snapshot=snapshot,
        source_language="ja",
        segments=tuple(
            ASRSegment(start, end, text[index], words[index])
            for index, (start, end) in enumerate(intervals)
        ),
        engine_version="synthetic-v2c",
    )
    payload = _payload()
    bundle = HybridEvidenceBundle.from_external_ja_and_asr(
        dvd_id="HSODA-104",
        external_ja_payload=payload,
        asr_result=asr,
        alignment=HybridAlignmentProvenance(
            ALIGNMENT_PROVENANCE_UNRESOLVED, "synthetic-source-evidence"
        ),
    )
    document = bundle.external_ja_document
    anchors = []
    for external_index, asr_index in ((0, 0), (1, 1), (2, 2), (3, 4)):
        ja = document.cues[external_index]
        segment = asr.segments[asr_index]
        anchors.append(MonotonicAnchorCandidate(
            external_identity=HybridCueIdentity.for_external_ja(external_index),
            asr_identity=HybridCueIdentity.for_asr_segment(asr_index),
            comparison=JapaneseComparisonEvidence(ja.text, segment.text),
            timing=AnchorTimingEvidence(
                external_start_ms=ja.start_ms,
                external_end_ms=ja.end_ms,
                asr_start_ms=segment.start_ms,
                asr_end_ms=segment.end_ms,
            ),
            score=japanese_lexical_similarity(ja.text, segment.text),
        ))
    alignment = infer_robust_affine_alignment(tuple(anchors), residual_threshold_ms=1)
    decision = decide_alignment_acceptance(
        alignment,
        AlignmentAcceptancePolicy(4, 4, 1.0, 1.0, 1_000, 0.95, 1.05),
    )
    application = apply_alignment_acceptance(bundle, decision, alignment=alignment)
    return build_ja_master_review_set(bundle, alignment_application=application)


def main():
    review = _review_set()
    asr_sha = review.asr_sha256
    audio_sha = hashlib.sha256(b"synthetic-audio-input").hexdigest()
    speaker_artifact_sha = hashlib.sha256(b"synthetic-speaker-output").hexdigest()
    turns = (
        SpeakerTurnEvidence(
            review.source_snapshot, asr_sha, audio_sha, speaker_artifact_sha,
            Fraction(7_000), Fraction(7_500), "SPEAKER_00",
        ),
        SpeakerTurnEvidence(
            review.source_snapshot, asr_sha, audio_sha, speaker_artifact_sha,
            Fraction(7_500), Fraction(8_500), "SPEAKER_01",
        ),
        SpeakerTurnEvidence(
            review.source_snapshot, asr_sha, audio_sha, speaker_artifact_sha,
            Fraction(7_400 * 3 + 1, 3), Fraction(7_600 * 3 - 1, 3), "SPEAKER_02",
        ),
    )
    plan = build_utterance_review_plan(review, speaker_turns=turns)
    validate_utterance_review_plan(plan, review)
    by_cardinality = {group.source_cardinality: group for group in plan.groups
                      if group.source_cardinality in {
                          "ASR_TO_JA_ONE_TO_MANY", "ASR_TO_JA_MANY_TO_ONE"
                      }}
    require(set(by_cardinality) == {
        "ASR_TO_JA_ONE_TO_MANY", "ASR_TO_JA_MANY_TO_ONE"
    }, "SPLIT_MERGE_CARDINALITY")
    require(any(group.source_cardinality == "ASR_TO_JA_ONE_TO_ONE" for group in plan.groups), "ONE_TO_ONE_CONTROL")
    one_to_many = by_cardinality["ASR_TO_JA_ONE_TO_MANY"]
    many_to_one = by_cardinality["ASR_TO_JA_MANY_TO_ONE"]
    require(one_to_many.utterance_status == UTTERANCE_UNRESOLVED, "OVERLAP_NOT_SAME_UTTERANCE")
    require(many_to_one.utterance_status == UTTERANCE_UNRESOLVED, "MANY_TO_ONE_NOT_AUTO_MERGED")
    require(any(link.kind == LINK_TIMELINE_OVERLAP for link in one_to_many.relationships), "STRICT_OVERLAP_RECORDED")
    require(len(one_to_many.members) == 3, "ONE_ASR_TWO_JA_MEMBERS_RETAINED")
    require(len(many_to_one.members) == 3, "TWO_ASR_ONE_JA_MEMBERS_RETAINED")
    repeated_text_members = [member for member in one_to_many.members if member.text == "four"]
    require(len(repeated_text_members) == 3, "DUPLICATE_TEXT_SOURCES_NOT_COLLAPSED")
    require(all(member.source_reference.source_index >= 0 for group in plan.groups for member in group.members), "SOURCE_INDEXES_RETAINED")
    require(one_to_many.speaker_status == SPEAKER_EVIDENCE_UNASSIGNED, "SPEAKER_EVIDENCE_NOT_ASSIGNED_TO_CUE")
    asr_main = next(member for member in one_to_many.members if member.source_reference.source == "asr_segment")
    observed_labels = {link.turn.speaker_label for link in asr_main.speaker_links}
    require(observed_labels == {"SPEAKER_00", "SPEAKER_01", "SPEAKER_02"}, "OVERLAPPING_TURNS_RETAINED")
    require([word.start_ms for word in asr_main.word_references] == [Fraction(7_000), Fraction(7_500)], "ASR_WORD_TIMES_EXACT")
    require(all(link.association == ASSOCIATION_OVERLAP_ONLY for word in asr_main.word_references for link in word.speaker_links), "WORD_SPEAKER_LINKS_ARE_OVERLAP_ONLY")
    require(asr_main.word_references[0].speaker_links[0].overlap_start_ms == Fraction(7_000), "WORD_TURN_START_PRESERVED")
    fractional_turn_link = next(
        link for link in asr_main.speaker_links
        if link.turn.speaker_label == "SPEAKER_02"
    )
    require(fractional_turn_link.overlap_start_ms == Fraction(22_201, 3), "FRACTIONAL_TURN_TIME_PRESERVED")

    no_speaker_plan = build_utterance_review_plan(review)
    require(all(group.speaker_status == SPEAKER_UNKNOWN for group in no_speaker_plan.groups), "UNKNOWN_SPEAKER_RETAINED")
    unlabeled_turn = SpeakerTurnEvidence(
        review.source_snapshot, asr_sha, audio_sha, speaker_artifact_sha,
        Fraction(7_000), Fraction(8_500), None,
    )
    unlabeled_plan = build_utterance_review_plan(review, speaker_turns=(unlabeled_turn,))
    unlabeled_group = next(group for group in unlabeled_plan.groups if group.group_id == one_to_many.group_id)
    require(unlabeled_group.speaker_status == SPEAKER_UNKNOWN, "UNLABELED_TURN_REMAINS_UNKNOWN")
    require(any(member.speaker_links for member in unlabeled_group.members), "UNKNOWN_TURN_EVIDENCE_PRESERVED")
    require(
        {member.source_reference.key for group in plan.groups for member in group.members}
        == {reference.key for candidate in review.candidates for reference in candidate.source_references},
        "ALL_SOURCE_REFS_COVERED_ONCE",
    )
    require(
        sum(len(group.candidate_ids) for group in plan.groups) == len(review.candidates),
        "ALL_CANDIDATES_OWNED_ONCE",
    )
    outside_anchor = next(
        member for group in plan.groups for member in group.members
        if member.source_reference.source == "external_ja"
        and member.source_reference.source_index == 5
    )
    require(outside_anchor.source_reference.aligned_start_ms is None, "OUTSIDE_ANCHOR_TIME_NOT_PROJECTED")
    require(any(
        group.source_cardinality == "EXTERNAL_JA_ONLY"
        and outside_anchor in group.members
        for group in plan.groups
    ), "UNPROJECTED_JA_CUE_RETAINED")

    bad_turn = replace(turns[0], asr_sha256="0" * 64)
    expect_raises(
        UtteranceGroupingError,
        lambda: build_utterance_review_plan(review, speaker_turns=(bad_turn,)),
        "DETACHED_SPEAKER_EVIDENCE_REJECTED",
    )
    group_index = plan.groups.index(one_to_many)
    tampered_member = replace(one_to_many.members[0], text="changed")
    tampered_group = replace(
        one_to_many,
        members=(tampered_member,) + one_to_many.members[1:],
    )
    tampered_groups = list(plan.groups)
    tampered_groups[group_index] = tampered_group
    tampered_plan = replace(plan, groups=tuple(tampered_groups))
    expect_raises(
        UtteranceGroupingError,
        lambda: validate_utterance_review_plan(tampered_plan, review),
        "SOURCE_TEXT_TAMPER_REJECTED",
    )
    print("UTTERANCE_GROUPS_SMOKE=PASS")
    print("ONE_TO_MANY=PASS")
    print("MANY_TO_ONE=PASS")
    print("ASR_WORD_AND_FRACTIONAL_TIMING=PASS")
    print("SPEAKER_EVIDENCE=UNASSIGNED_SOURCE_BOUND_LINKS")
    print("UNKNOWN_SPEAKER=PASS")
    print("DUPLICATE_SOURCE_PRESERVED=PASS")
    print("MODEL_CALLS=0")
    print("FILE_WRITES=0")


if __name__ == "__main__":
    main()
