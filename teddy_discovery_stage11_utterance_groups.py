"""Source-bound pre-translation utterance review groups for Stage11 V2-C.

This is an in-memory adapter only. Links mean an affine candidate relation or
strict timeline overlap; neither asserts utterance equivalence. Speaker turns
are retained as evidence, not assigned to subtitle cues. No I/O or inference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
import hashlib
import json
import re

from teddy_discovery_alignment import MAX_LEXICAL_PAIR_COMPARISONS
from teddy_discovery_asr import ASRSourceSnapshot
from teddy_discovery_hybrid_evidence import (
    EVIDENCE_SOURCE_ASR_SEGMENT,
    EVIDENCE_SOURCE_EXTERNAL_JA,
)
from teddy_discovery_stage11_ja_master import (
    JAMasterReviewSet,
    JAMasterSourceReference,
    RELATION_MATCHED,
    RELATION_POTENTIAL_CONFLICT,
)

LINK_CANDIDATE_RELATION = "JA_MASTER_CANDIDATE_RELATION"
LINK_TIMELINE_OVERLAP = "STRICT_TIMELINE_OVERLAP"
ASSOCIATION_OVERLAP_ONLY = "TEMPORAL_OVERLAP_ONLY"
UTTERANCE_UNRESOLVED = "UNRESOLVED"
SPEAKER_UNKNOWN = "UNKNOWN"
SPEAKER_EVIDENCE_UNASSIGNED = "TURN_EVIDENCE_UNASSIGNED"
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_SPEAKER_LABEL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")


class UtteranceGroupingError(ValueError):
    """Invalid source relationship, timing, or speaker-evidence attachment."""


def _sha(value: object, name: str) -> None:
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        raise UtteranceGroupingError(name + " must be a lowercase SHA-256")


def _interval(start: object, end: object, name: str) -> None:
    if type(start) is not Fraction or type(end) is not Fraction or start < 0 or end <= start:
        raise UtteranceGroupingError(name + " must be a valid exact Fraction interval")


def _wire_time(value: Fraction) -> tuple[int, int]:
    return value.numerator, value.denominator


def _ordered_pair(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left < right else (right, left)


@dataclass(frozen=True)
class SpeakerTurnEvidence:
    """One exact speaker-turn interval, bound to the same ASR/source snapshot."""

    source_snapshot: ASRSourceSnapshot = field(repr=False)
    asr_sha256: str
    source_audio_sha256: str
    evidence_sha256: str
    start_ms: Fraction
    end_ms: Fraction
    speaker_label: str | None = None

    def __post_init__(self) -> None:
        if type(self.source_snapshot) is not ASRSourceSnapshot:
            raise UtteranceGroupingError("speaker source snapshot is invalid")
        self.source_snapshot.__post_init__()
        _sha(self.asr_sha256, "speaker ASR identity")
        _sha(self.source_audio_sha256, "speaker audio identity")
        _sha(self.evidence_sha256, "speaker artifact identity")
        _interval(self.start_ms, self.end_ms, "speaker interval")
        if self.speaker_label is not None and (
            type(self.speaker_label) is not str
            or _SPEAKER_LABEL_RE.fullmatch(self.speaker_label) is None
        ):
            raise UtteranceGroupingError("speaker label is invalid")

    @property
    def turn_id(self) -> str:
        identity = {
            "dvd_id": self.source_snapshot.dvd_id,
            "video_relative": self.source_snapshot.canonical_video_relative,
            "source_size": self.source_snapshot.source_size,
            "source_mtime_ns": self.source_snapshot.source_mtime_ns,
            "asr_sha256": self.asr_sha256,
            "source_audio_sha256": self.source_audio_sha256,
            "evidence_sha256": self.evidence_sha256,
            "start_ms": _wire_time(self.start_ms),
            "end_ms": _wire_time(self.end_ms),
            "speaker_label": self.speaker_label,
        }
        raw = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class SpeakerEvidenceLink:
    """Temporal overlap only; it does not assign a turn to a whole cue."""

    source_reference: JAMasterSourceReference = field(repr=False)
    owner_kind: str
    owner_index: int | None
    owner_start_ms: Fraction
    owner_end_ms: Fraction
    turn: SpeakerTurnEvidence = field(repr=False)
    overlap_start_ms: Fraction
    overlap_end_ms: Fraction
    association: str = ASSOCIATION_OVERLAP_ONLY


@dataclass(frozen=True)
class ASRWordReference:
    """Original ASR token and exact timing, including optional turn evidence."""

    source_reference: JAMasterSourceReference = field(repr=False)
    word_index: int
    text: str = field(repr=False)
    start_ms: Fraction
    end_ms: Fraction
    speaker_links: tuple[SpeakerEvidenceLink, ...] = field(default=(), repr=False)


@dataclass(frozen=True)
class UtteranceMember:
    """One original cue; repeated text remains distinct by source identity."""

    source_reference: JAMasterSourceReference = field(repr=False)
    text: str = field(repr=False)
    word_references: tuple[ASRWordReference, ...] = field(default=(), repr=False)
    speaker_links: tuple[SpeakerEvidenceLink, ...] = field(default=(), repr=False)


@dataclass(frozen=True)
class SourceRelationshipEvidence:
    """Link provenance; no relationship type means the cues are one utterance."""

    left_source_key: str
    right_source_key: str
    kind: str
    candidate_id: str | None = None
    candidate_relation: str | None = None
    overlap_start_ms: Fraction | None = None
    overlap_end_ms: Fraction | None = None


@dataclass(frozen=True)
class UtteranceReviewGroup:
    """Connected source evidence for V2-D; utterance and speaker stay unresolved."""

    group_id: str
    source_cardinality: str
    candidate_ids: tuple[str, ...]
    members: tuple[UtteranceMember, ...]
    relationships: tuple[SourceRelationshipEvidence, ...]
    utterance_status: str = UTTERANCE_UNRESOLVED
    speaker_status: str = SPEAKER_UNKNOWN


@dataclass(frozen=True)
class UtteranceReviewPlan:
    """In-memory V2-D handoff; it never writes or materializes subtitles."""

    review_set: JAMasterReviewSet = field(repr=False, compare=False)
    groups: tuple[UtteranceReviewGroup, ...]
    speaker_turns: tuple[SpeakerTurnEvidence, ...] = field(default=(), repr=False)


def _cardinality(members: tuple[UtteranceMember, ...]) -> str:
    asr_count = sum(m.source_reference.source == EVIDENCE_SOURCE_ASR_SEGMENT for m in members)
    ja_count = sum(m.source_reference.source == EVIDENCE_SOURCE_EXTERNAL_JA for m in members)
    if asr_count and not ja_count:
        return "ASR_ONLY"
    if ja_count and not asr_count:
        return "EXTERNAL_JA_ONLY"
    if asr_count == 1 and ja_count == 1:
        return "ASR_TO_JA_ONE_TO_ONE"
    if asr_count == 1:
        return "ASR_TO_JA_ONE_TO_MANY"
    if ja_count == 1:
        return "ASR_TO_JA_MANY_TO_ONE"
    return "ASR_TO_JA_MANY_TO_MANY"


def _speaker_links(reference, turns, *, owner_kind, owner_index, start_ms, end_ms):
    if start_ms is None or end_ms is None:
        return ()
    links = []
    for turn in turns:
        start = max(start_ms, turn.start_ms)
        end = min(end_ms, turn.end_ms)
        if start < end:
            links.append(SpeakerEvidenceLink(
                reference, owner_kind, owner_index, start_ms, end_ms, turn,
                start, end, ASSOCIATION_OVERLAP_ONLY,
            ))
    return tuple(sorted(links, key=lambda item: (
        item.overlap_start_ms, item.overlap_end_ms, item.turn.turn_id
    )))


def _group_id(review_set, keys, candidate_ids, relationships) -> str:
    links = [{
        "left": item.left_source_key,
        "right": item.right_source_key,
        "kind": item.kind,
        "candidate_id": item.candidate_id,
        "candidate_relation": item.candidate_relation,
        "overlap_start": None if item.overlap_start_ms is None else _wire_time(item.overlap_start_ms),
        "overlap_end": None if item.overlap_end_ms is None else _wire_time(item.overlap_end_ms),
    } for item in relationships]
    identity = {
        "dvd_id": review_set.dvd_id,
        "source_size": review_set.source_snapshot.source_size,
        "source_mtime_ns": review_set.source_snapshot.source_mtime_ns,
        "asr_sha256": review_set.asr_sha256,
        "external_ja_sha256": review_set.external_ja_sha256,
        "source_keys": keys,
        "candidate_ids": candidate_ids,
        "relationships": links,
    }
    raw = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("ascii")
    return "group-" + hashlib.sha256(raw).hexdigest()


def _build_groups(review_set, speaker_turns):
    references = {}
    candidate_ids_by_key = {}
    for candidate in review_set.candidates:
        for reference in candidate.source_references:
            key = reference.key
            if key in references and references[key] != reference:
                raise UtteranceGroupingError("source key has conflicting references")
            references[key] = reference
            candidate_ids_by_key.setdefault(key, set()).add(candidate.candidate_id)

    parent = {key: key for key in references}

    def find(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def union(left, right):
        a, b = find(left), find(right)
        if a != b:
            low, high = sorted((a, b))
            parent[high] = low

    relationships = []
    for candidate in review_set.candidates:
        if len(candidate.source_references) == 2:
            left, right = _ordered_pair(*(ref.key for ref in candidate.source_references))
            relationships.append(SourceRelationshipEvidence(
                left, right, LINK_CANDIDATE_RELATION,
                candidate.candidate_id, candidate.relation,
            ))
            union(left, right)

    asr_refs = sorted(
        (ref for ref in references.values() if ref.source == EVIDENCE_SOURCE_ASR_SEGMENT),
        key=lambda ref: (ref.aligned_start_ms, ref.source_index),
    )
    ja_refs = sorted(
        (ref for ref in references.values()
         if ref.source == EVIDENCE_SOURCE_EXTERNAL_JA
         and ref.aligned_start_ms is not None and ref.aligned_end_ms is not None),
        key=lambda ref: (ref.aligned_start_ms, ref.source_index),
    )
    comparisons = 0
    for asr in asr_refs:
        if asr.aligned_start_ms is None or asr.aligned_end_ms is None:
            raise UtteranceGroupingError("ASR source has no canonical timeline")
        for ja in ja_refs:
            if ja.aligned_start_ms >= asr.aligned_end_ms:
                break
            comparisons += 1
            if comparisons > MAX_LEXICAL_PAIR_COMPARISONS:
                raise UtteranceGroupingError("timeline comparison bound exceeded")
            start, end = max(asr.aligned_start_ms, ja.aligned_start_ms), min(asr.aligned_end_ms, ja.aligned_end_ms)
            if start < end:
                left, right = _ordered_pair(asr.key, ja.key)
                relationships.append(SourceRelationshipEvidence(
                    left, right, LINK_TIMELINE_OVERLAP,
                    overlap_start_ms=start, overlap_end_ms=end,
                ))
                union(left, right)

    components = {}
    for key in references:
        components.setdefault(find(key), []).append(key)

    groups = []
    bundle = review_set._source_bundle
    for component in components.values():
        keys = tuple(sorted(component))
        key_set = set(keys)
        candidates = tuple(sorted({cid for key in keys for cid in candidate_ids_by_key[key]}))
        links = tuple(sorted(
            (item for item in relationships if item.left_source_key in key_set and item.right_source_key in key_set),
            key=lambda item: (item.left_source_key, item.right_source_key, item.kind, item.candidate_id or "",
                              () if item.overlap_start_ms is None else _wire_time(item.overlap_start_ms)),
        ))
        members = []
        for key in keys:
            reference = references[key]
            if reference.source == EVIDENCE_SOURCE_ASR_SEGMENT:
                segment = bundle.asr_result.segments[reference.source_index]
                text = segment.text
                words = tuple(ASRWordReference(
                    reference, index, word.text, Fraction(word.start_ms), Fraction(word.end_ms),
                    _speaker_links(reference, speaker_turns, owner_kind="ASR_WORD", owner_index=index,
                                   start_ms=Fraction(word.start_ms), end_ms=Fraction(word.end_ms)),
                ) for index, word in enumerate(segment.words))
            else:
                document = bundle.external_ja_document
                if document is None:
                    raise UtteranceGroupingError("external source document is missing")
                text = document.cues[reference.source_index].text
                words = ()
            cue_links = _speaker_links(
                reference, speaker_turns, owner_kind="SOURCE_CUE", owner_index=None,
                start_ms=reference.aligned_start_ms, end_ms=reference.aligned_end_ms,
            )
            members.append(UtteranceMember(reference, text, words, cue_links))
        member_tuple = tuple(members)
        all_turn_links = tuple(link for member in member_tuple for link in member.speaker_links) + tuple(
            link for member in member_tuple for word in member.word_references for link in word.speaker_links
        )
        label_present = any(link.turn.speaker_label is not None for link in all_turn_links)
        groups.append(UtteranceReviewGroup(
            group_id=_group_id(review_set, keys, candidates, links),
            source_cardinality=_cardinality(member_tuple),
            candidate_ids=candidates,
            members=member_tuple,
            relationships=links,
            utterance_status=UTTERANCE_UNRESOLVED,
            speaker_status=SPEAKER_EVIDENCE_UNASSIGNED if label_present else SPEAKER_UNKNOWN,
        ))
    return tuple(sorted(groups, key=lambda group: group.group_id))


def build_utterance_review_plan(
    review_set: JAMasterReviewSet,
    *,
    speaker_turns: tuple[SpeakerTurnEvidence, ...] = (),
) -> UtteranceReviewPlan:
    """Group V2-B sources while preserving every cue; do not resolve content."""
    if type(review_set) is not JAMasterReviewSet or type(speaker_turns) is not tuple:
        raise UtteranceGroupingError("exact review set and immutable speaker evidence are required")
    review_set.__post_init__()
    for turn in speaker_turns:
        if type(turn) is not SpeakerTurnEvidence:
            raise UtteranceGroupingError("unsupported speaker evidence type")
        turn.__post_init__()
        if turn.source_snapshot != review_set.source_snapshot or turn.asr_sha256 != review_set.asr_sha256:
            raise UtteranceGroupingError("speaker evidence is detached from the ASR source")
    plan = UtteranceReviewPlan(review_set, _build_groups(review_set, speaker_turns), speaker_turns)
    return validate_utterance_review_plan(plan, review_set)


def validate_utterance_review_plan(plan, review_set=None) -> UtteranceReviewPlan:
    """Rebuild the complete ledger before a downstream semantic adapter uses it."""
    if type(plan) is not UtteranceReviewPlan or type(plan.groups) is not tuple or not plan.groups:
        raise UtteranceGroupingError("review plan is invalid")
    expected_review = plan.review_set if review_set is None else review_set
    if type(expected_review) is not JAMasterReviewSet or plan.review_set != expected_review:
        raise UtteranceGroupingError("review plan is detached from its JA Master input")
    expected_review.__post_init__()
    if type(plan.speaker_turns) is not tuple:
        raise UtteranceGroupingError("speaker evidence collection is invalid")
    turn_ids = set()
    for turn in plan.speaker_turns:
        if type(turn) is not SpeakerTurnEvidence:
            raise UtteranceGroupingError("speaker evidence type is invalid")
        turn.__post_init__()
        if turn.source_snapshot != expected_review.source_snapshot or turn.asr_sha256 != expected_review.asr_sha256:
            raise UtteranceGroupingError("speaker evidence source is detached")
        if turn.turn_id in turn_ids:
            raise UtteranceGroupingError("duplicate speaker evidence is prohibited")
        turn_ids.add(turn.turn_id)
    if plan.groups != _build_groups(expected_review, plan.speaker_turns):
        raise UtteranceGroupingError("group ledger differs from source-bound evidence")
    member_keys = [member.source_reference.key for group in plan.groups for member in group.members]
    expected_keys = {ref.key for candidate in expected_review.candidates for ref in candidate.source_references}
    if len(member_keys) != len(set(member_keys)) or set(member_keys) != expected_keys:
        raise UtteranceGroupingError("source references were duplicated or dropped")
    candidate_ids = [cid for group in plan.groups for cid in group.candidate_ids]
    expected_candidate_ids = {candidate.candidate_id for candidate in expected_review.candidates}
    if len(candidate_ids) != len(set(candidate_ids)) or set(candidate_ids) != expected_candidate_ids:
        raise UtteranceGroupingError("review candidates were duplicated or dropped")
    return plan


__all__ = [
    "ASRWordReference",
    "ASSOCIATION_OVERLAP_ONLY",
    "LINK_CANDIDATE_RELATION",
    "LINK_TIMELINE_OVERLAP",
    "SPEAKER_EVIDENCE_UNASSIGNED",
    "SPEAKER_UNKNOWN",
    "SpeakerEvidenceLink",
    "SpeakerTurnEvidence",
    "UTTERANCE_UNRESOLVED",
    "UtteranceGroupingError",
    "UtteranceMember",
    "UtteranceReviewGroup",
    "UtteranceReviewPlan",
    "build_utterance_review_plan",
    "validate_utterance_review_plan",
]
