"""Isolated V2-D connection from source-bound JA Master to private SRTs.

The module reuses the promoted V2-B/V2-C evidence contracts, Stage11's
stateful translator, NativeNormalFirstPass receipt boundary, and the existing
quality-review result/action validators.  It never owns source timing: timing
is derived from the selected source spans and rounded once, at SRT rendering.
No operation in this module starts a model by itself; model calls are supplied
through the existing ``NativeNormalFirstPass.invoke``-compatible callback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import stat
import uuid
from contextlib import nullcontext
from typing import Callable

from teddy_discovery_stage11_ja_master import (
    DECISION_ACCEPTED,
    DECISION_REJECTED,
    DECISION_UNCERTAIN,
    JAMasterReviewSet,
    JAMasterSourceReference,
)
from teddy_discovery_stage11_utterance_groups import (
    UtteranceReviewPlan,
    validate_utterance_review_plan,
)
# Keep the translator's semantic envelope and exact validators unchanged.
from teddy_discovery_hermes_v2 import HermesV2CueInput
from teddy_discovery_stateful_translator import (
    STATEFUL_TRANSLATOR_PRIVATE_FILE_MODE,
    STATEFUL_TRANSLATOR_SCHEMA_VERSION,
    StatefulCueOutput,
    StatefulSubtitlePackage,
    StatefulSubtitleResult,
    _atomic_private_write,
    bind_stateful_model_input_identity,
    bind_stateful_semantic_policy,
    parse_stateful_result,
    serialize_stateful_model_input,
    serialize_stateful_package,
    serialize_stateful_result,
    stateful_session_id_for_package,
    validate_stateful_result,
)
from teddy_discovery_stateful_policy import DEFAULT_STATEFUL_SEMANTIC_POLICY
from teddy_discovery_stateful_controller import (
    build_stateful_part_query,
    build_stateful_whole_title_query,
)
from teddy_discovery_stateful_parts import (
    StatefulPartsAssemblyError,
    assemble_stateful_result,
    build_stateful_part_plan,
    parse_stateful_part,
    serialize_stateful_part,
)
from teddy_discovery_stage11_controller import Stage11ControllerError
from teddy_discovery_stage11_hermes_profile import HermesExecutionSettings
from teddy_discovery_stage11_ja_master import ROUTE_EXTERNAL_ALIGNMENT_ACCEPTED
from teddy_discovery_asr import ASRResult, ASRRuntimeIdentity
from teddy_discovery_asr_artifact import serialize_asr_result
from teddy_discovery_asr_audio import iter_audio_chunks
from teddy_discovery_asr_source import ASRLocalMediaSource
from teddy_discovery_hybrid_evidence import EVIDENCE_SOURCE_ASR_SEGMENT, stable_cue_id
from teddy_discovery_targeted_asr_window import (
    STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1,
    TargetedASRWindow,
    TargetedASRSourceInterval,
    plan_targeted_asr_source_windows_with_policy,
    plan_targeted_asr_windows_with_policy,
)
from teddy_discovery_targeted_asr_artifact import (
    MAX_TARGETED_ASR_ARTIFACT_BYTES,
    TargetedASRArtifact,
    parse_targeted_asr_artifact_bytes,
    require_matching_targeted_asr_source,
    serialize_targeted_asr_artifact,
)
from teddy_discovery_targeted_second_evidence import (
    TargetedSecondEvidencePlan,
    TargetedSecondEvidenceSource,
    TargetedSecondEvidenceWindow,
    TargetedSecondEvidenceWindowResult,
    bind_targeted_second_evidence,
    _make_plan as _make_targeted_plan,
)
from teddy_discovery_targeted_second_evidence_runner import (
    TargetedSecondEvidenceExecution,
    build_targeted_audio_window_provider,
    run_targeted_hybrid_windows,
    transcribe_targeted_window,
)
from teddy_discovery_targeted_second_evidence_artifact import (
    MAX_TARGETED_SECOND_EVIDENCE_ARTIFACT_BYTES,
    TargetedSecondEvidenceArtifact,
    parse_targeted_second_evidence_artifact_bytes,
    serialize_targeted_second_evidence_artifact,
    targeted_second_evidence_artifact_from_execution,
    write_targeted_second_evidence_artifact,
)
from teddy_discovery_targeted_second_evidence_projection import (
    TARGETED_SECOND_EVIDENCE_STATUS_PRESENT_UNRESOLVED,
    project_targeted_second_evidence_artifact,
)
from teddy_discovery_stateful_quality_review import (
    AMBIGUOUS,
    KEEP,
    OMIT,
    REPAIR,
    QualityReviewInputCue,
    QualityReviewRequest,
    QualityReviewResult,
    QualityReviewResultCue,
    bind_review_execution_provenance,
    parse_review_result,
    review_request_sha256,
    serialize_review_request,
    serialize_review_result,
    validate_review_result,
    effective_review_action,
)
from teddy_discovery_hybrid_suspect_review import (
    merge_target_review_result,
    select_suspect_cue_ids,
)
from teddy_discovery_subtitle_source_quality import SourceQualityDecision
from teddy_discovery_subtitle_text import (
    SubtitleCue,
    SubtitleDocument,
    parse_subtitle_bytes,
    serialize_srt,
)
from teddy_discovery_ko_srt import generate_korean_srt


V2D_SCHEMA_VERSION = 1
V2D_MAX_JSON_BYTES = 16 * 1024 * 1024
V2D_MAX_PROMPT_BYTES = 128_000
V2D_SESSION_NAMESPACE = uuid.UUID("ea07da43-06a2-5412-a85b-f3b65c9f4b6d")
V2D_OUTPUT_NAMES = (
    "ja-master-v1.json",
    "clean-ja-v1.srt",
    "clean-ko-v1.srt",
    "v2d-proof-v1.json",
)


class V2DError(ValueError):
    """Invalid V2-D input, judgment, translation, review or output."""


class V2DHold(V2DError):
    """The evidence is explicitly unresolved; no translated SRT may be made."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest(value: object, name: str) -> str:
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise V2DError(name + " must be a lowercase SHA-256")
    return value


def _wire(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _fraction(value: Fraction | None):
    return None if value is None else [value.numerator, value.denominator]


def _round_ms(value: Fraction) -> int:
    """One nonnegative half-up conversion, reserved for final SRT output."""
    if type(value) is not Fraction or value < 0:
        raise V2DError("SRT time is not a nonnegative exact Fraction")
    quotient, remainder = divmod(value.numerator, value.denominator)
    return quotient + (1 if 2 * remainder >= value.denominator else 0)


def _reject_duplicate_json(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise V2DError("duplicate JSON key")
        out[key] = value
    return out


def _load_json(raw: bytes, label: str):
    if type(raw) is not bytes or not 0 < len(raw) <= V2D_MAX_JSON_BYTES:
        raise V2DError(label + " exceeds the bounded JSON contract")
    try:
        return json.loads(raw, object_pairs_hook=_reject_duplicate_json,
                          parse_constant=lambda value: (_ for _ in ()).throw(V2DError("nonfinite JSON number")))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise V2DError(label + " is invalid JSON") from error


def _safe_text(value: object, label: str, *, max_chars: int = 16_000):
    if type(value) is not str or not value.strip() or len(value) > max_chars:
        raise V2DError(label + " is empty or exceeds its text bound")
    if any(ord(ch) < 32 and ch not in "\n\r\t" or ord(ch) == 127 for ch in value):
        raise V2DError(label + " contains a control character")
    return value


def _private_dir(path: str | Path, *, create: bool = False) -> Path:
    target = Path(path)
    if create:
        try:
            os.mkdir(target, 0o700)
        except FileExistsError:
            pass
        except OSError as error:
            raise V2DError("private V2-D directory could not be created") from error
    try:
        info = os.lstat(target)
    except OSError as error:
        raise V2DError("private V2-D directory is unavailable") from error
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise V2DError("private V2-D directory must be owned and mode 0700")
    return target


def _private_child(parent: Path, name: str, *, create: bool) -> Path:
    if not name or "/" in name or name in {".", ".."}:
        raise V2DError("invalid private stage directory name")
    return _private_dir(parent / name, create=create)


def _source_fingerprint(plan: UtteranceReviewPlan) -> str:
    review = plan.review_set
    groups = []
    for group in plan.groups:
        members = []
        for member in group.members:
            ref = member.source_reference
            members.append({
                "key": ref.key,
                "source": ref.source,
                "source_index": ref.source_index,
                "source_sha256": ref.source_sha256,
                "locator_sha256": _sha(ref.source_locator.encode("utf-8")),
                "original_ms": [ref.original_start_ms, ref.original_end_ms],
                "aligned_ms": [_fraction(ref.aligned_start_ms), _fraction(ref.aligned_end_ms)],
                "text": member.text,
                "words": [{"index": word.word_index, "text": word.text,
                           "start_ms": _fraction(word.start_ms), "end_ms": _fraction(word.end_ms)}
                          for word in member.word_references],
                "speaker_links": [{
                    "turn_id": link.turn.turn_id,
                    "label": link.turn.speaker_label,
                    "overlap_start_ms": _fraction(link.overlap_start_ms),
                    "overlap_end_ms": _fraction(link.overlap_end_ms),
                } for link in member.speaker_links],
            })
        groups.append({
            "group_id": group.group_id,
            "cardinality": group.source_cardinality,
            "candidate_ids": list(group.candidate_ids),
            "speaker_status": group.speaker_status,
            "members": members,
            "relationships": [{
                "left": item.left_source_key, "right": item.right_source_key,
                "kind": item.kind, "candidate_id": item.candidate_id,
                "candidate_relation": item.candidate_relation,
                "overlap_start_ms": _fraction(item.overlap_start_ms),
                "overlap_end_ms": _fraction(item.overlap_end_ms),
            } for item in group.relationships],
        })
    snapshot = review.source_snapshot
    identity = {
        "dvd_id": review.dvd_id,
        "source_snapshot": [snapshot.dvd_id, snapshot.canonical_video_relative,
                            snapshot.source_size, snapshot.source_mtime_ns],
        "asr_sha256": review.asr_sha256,
        "external_ja_sha256": review.external_ja_sha256,
        "route": review.route,
        "groups": groups,
    }
    return _sha(_wire(identity))


def _group_payload(plan: UtteranceReviewPlan, group) -> dict[str, object]:
    candidate_by_id = {item.candidate_id: item for item in plan.review_set.candidates}
    return {
        "schema_version": V2D_SCHEMA_VERSION,
        "dvd_id": plan.review_set.dvd_id,
        "source_fingerprint": _source_fingerprint(plan),
        "route": plan.review_set.route,
        "group": {
            "group_id": group.group_id,
            "source_cardinality": group.source_cardinality,
            "utterance_status": group.utterance_status,
            "speaker_status": group.speaker_status,
            "members": [{
                "source_key": member.source_reference.key,
                "source_kind": member.source_reference.source,
                "source_id": member.source_reference.source_id,
                "source_index": member.source_reference.source_index,
                "source_sha256": member.source_reference.source_sha256,
                "locator_sha256": _sha(member.source_reference.source_locator.encode("utf-8")),
                "original_start_ms": member.source_reference.original_start_ms,
                "original_end_ms": member.source_reference.original_end_ms,
                "aligned_start_ms": _fraction(member.source_reference.aligned_start_ms),
                "aligned_end_ms": _fraction(member.source_reference.aligned_end_ms),
                "text": member.text,
                "word_references": [{
                    "word_index": word.word_index, "text": word.text,
                    "start_ms": _fraction(word.start_ms), "end_ms": _fraction(word.end_ms),
                    "speaker_turns": [{"turn_id": link.turn.turn_id,
                                       "speaker_label": link.turn.speaker_label,
                                       "association": link.association}
                                      for link in word.speaker_links],
                } for word in member.word_references],
                "speaker_turns": [{"turn_id": link.turn.turn_id,
                                   "speaker_label": link.turn.speaker_label,
                                   "association": link.association,
                                   "overlap_start_ms": _fraction(link.overlap_start_ms),
                                   "overlap_end_ms": _fraction(link.overlap_end_ms)}
                                  for link in member.speaker_links],
            } for member in group.members],
            "candidate_relations": [{
                "candidate_id": candidate_id,
                "relation": candidate_by_id[candidate_id].relation,
                "source_keys": [ref.key for ref in candidate_by_id[candidate_id].source_references],
                "rationale_codes": list(candidate_by_id[candidate_id].rationale_codes),
            } for candidate_id in group.candidate_ids],
            "relationships": [{"left_source_key": item.left_source_key,
                               "right_source_key": item.right_source_key,
                               "kind": item.kind,
                               "candidate_id": item.candidate_id,
                               "candidate_relation": item.candidate_relation,
                               "overlap_start_ms": _fraction(item.overlap_start_ms),
                               "overlap_end_ms": _fraction(item.overlap_end_ms)}
                              for item in group.relationships],
        },
    }


@dataclass(frozen=True)
class CandidateDecision:
    candidate_id: str
    status: str
    rationale: str

    def __post_init__(self):
        _digest(self.candidate_id, "candidate_id")
        if self.status not in {DECISION_ACCEPTED, DECISION_REJECTED, DECISION_UNCERTAIN}:
            raise V2DError("unsupported candidate decision")
        _safe_text(self.rationale, "candidate rationale", max_chars=1024)


@dataclass(frozen=True)
class SourceDecision:
    source_key: str
    status: str
    rationale: str

    def __post_init__(self):
        _safe_text(self.source_key, "source key", max_chars=256)
        if self.status not in {DECISION_ACCEPTED, DECISION_REJECTED, DECISION_UNCERTAIN}:
            raise V2DError("unsupported source decision")
        _safe_text(self.rationale, "source rationale", max_chars=1024)


@dataclass(frozen=True)
class SourceSpan:
    source_key: str
    word_start_index: int | None = None
    word_end_index: int | None = None

    def __post_init__(self):
        _safe_text(self.source_key, "source span key", max_chars=256)
        if (self.word_start_index is None) != (self.word_end_index is None):
            raise V2DError("word span must specify both bounds")
        if self.word_start_index is not None and (
            type(self.word_start_index) is not int or type(self.word_end_index) is not int
            or self.word_start_index < 0 or self.word_end_index <= self.word_start_index
        ):
            raise V2DError("word span is invalid")


@dataclass(frozen=True)
class MasterOutputProposal:
    japanese_text: str = field(repr=False)
    source_spans: tuple[SourceSpan, ...]
    rationale: str

    def __post_init__(self):
        _safe_text(self.japanese_text, "JA Master text")
        if type(self.source_spans) is not tuple or not self.source_spans:
            raise V2DError("master output must own source spans")
        if any(type(span) is not SourceSpan for span in self.source_spans):
            raise V2DError("master output source span type is invalid")
        if len({span.source_key for span in self.source_spans}) != len(self.source_spans):
            raise V2DError("one output cannot repeat a source span")
        _safe_text(self.rationale, "master output rationale", max_chars=1024)


@dataclass(frozen=True)
class GroupAdjudication:
    group_id: str
    candidate_decisions: tuple[CandidateDecision, ...]
    source_decisions: tuple[SourceDecision, ...]
    outputs: tuple[MasterOutputProposal, ...]

    def __post_init__(self):
        _safe_text(self.group_id, "group id", max_chars=128)
        if type(self.candidate_decisions) is not tuple or type(self.source_decisions) is not tuple or type(self.outputs) is not tuple:
            raise V2DError("adjudication collections must be immutable tuples")


@dataclass(frozen=True)
class V2DAdjudication:
    source_fingerprint: str
    groups: tuple[GroupAdjudication, ...]

    def __post_init__(self):
        _digest(self.source_fingerprint, "source_fingerprint")
        if type(self.groups) is not tuple or not self.groups:
            raise V2DError("adjudication groups are required")


@dataclass(frozen=True)
class V2DMasterCue:
    cue_id: str
    group_id: str
    text: str = field(repr=False)
    source_references: tuple[JAMasterSourceReference, ...] = field(repr=False)
    start_ms: Fraction
    end_ms: Fraction
    speaker_status: str
    speaker_evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class V2DMaster:
    review_set: JAMasterReviewSet = field(repr=False)
    utterance_plan: UtteranceReviewPlan = field(repr=False)
    adjudication: V2DAdjudication = field(repr=False)
    cues: tuple[V2DMasterCue, ...]
    source_fingerprint: str
    master_sha256: str
    targeted_evidence_sha256: str | None = None


@dataclass(frozen=True)
class _V2DTargetedRequest:
    plan: TargetedSecondEvidencePlan = field(repr=False)
    cue_ids: tuple[str, ...]
    source_cue_links: tuple[tuple[str, int, tuple[str, ...], tuple[str, ...]], ...]
    baseline_asr_sha256: str
    context_raw: bytes = field(repr=False)
    context_sha256: str


@dataclass(frozen=True)
class _V2DExternalTargetedRequest:
    """Targeted audio request anchored to validated aligned external-JA cues."""
    source_snapshot: object = field(repr=False)
    windows: tuple[TargetedASRWindow, ...]
    cue_ids: tuple[str, ...]
    source_cue_links: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...]
    context_raw: bytes = field(repr=False)
    context_sha256: str


@dataclass(frozen=True)
class _V2DTargetedEvidence:
    artifact: object = field(repr=False)
    artifact_sha256: str
    linkage_sha256: str
    group_payloads: tuple[tuple[str, dict[str, object]], ...] = field(repr=False)
    source_window_evidence: tuple[tuple[str, str, tuple[str, ...]], ...] = field(repr=False)


def _build_targeted_request(master: V2DMaster, translated: StatefulSubtitleResult,
                            requested_override: tuple[str, ...] | None = None) -> _V2DTargetedRequest:
    """Bind audio requests only to already accepted, source-backed ASR refs."""
    master = _validate_master(master)
    if len(master.cues) != len(translated.cues) or tuple(cue.cue_id for cue in master.cues) != tuple(
        cue.cue_id for cue in translated.cues
    ):
        raise V2DError("audio-evidence request is detached from the JA Master")
    requested = (tuple(cue.cue_id for cue in translated.cues
                       if isinstance(cue, StatefulCueOutput) and cue.needs_audio_evidence)
                 if requested_override is None else requested_override)
    if not requested:
        raise V2DError("targeted request builder requires at least one audio request")

    bundle = master.review_set._source_bundle
    asr_result = bundle.asr_result
    if type(asr_result) is not ASRResult:
        raise V2DHold("TARGETED_ASR_BASELINE_UNAVAILABLE")
    try:
        asr_result.__post_init__()
        baseline_raw = serialize_asr_result(asr_result)
    except Exception as error:
        raise V2DHold("TARGETED_ASR_BASELINE_INVALID") from error
    baseline_sha = _sha(baseline_raw)
    if (asr_result.source_snapshot != master.review_set.source_snapshot
            or baseline_sha != master.review_set.asr_sha256):
        raise V2DHold("TARGETED_ASR_BASELINE_IDENTITY_MISMATCH")

    master_by_id = {cue.cue_id: cue for cue in master.cues}
    group_by_id = {group.group_id: group for group in master.utterance_plan.groups}
    member_by_key = {
        member.source_reference.key: member
        for group in master.utterance_plan.groups for member in group.members
    }
    index_links: dict[int, dict[str, set[str]]] = {}
    for cue_id in requested:
        master_cue = master_by_id.get(cue_id)
        if master_cue is None or master_cue.group_id not in group_by_id:
            raise V2DHold("TARGETED_ASR_MASTER_CUE_UNBOUND")
        group = group_by_id[master_cue.group_id]
        asr_refs = tuple(ref for ref in master_cue.source_references
                         if ref.source == EVIDENCE_SOURCE_ASR_SEGMENT)
        if not asr_refs:
            # An external-only or unaligned cue cannot supply a fabricated
            # baseline ASR ordinal. The V1 artifact schema is ASR-source-bound.
            raise V2DHold("TARGETED_ASR_NO_SOURCE_BOUND_BASELINE_SEGMENT")
        for ref in asr_refs:
            member = member_by_key.get(ref.key)
            if member is None or member.source_reference != ref:
                raise V2DHold("TARGETED_ASR_GROUP_SOURCE_MISMATCH")
            index = ref.source_index
            if not 0 <= index < len(asr_result.segments):
                raise V2DHold("TARGETED_ASR_SOURCE_INDEX_OUT_OF_RANGE")
            segment = asr_result.segments[index]
            if (ref.source_id != stable_cue_id(EVIDENCE_SOURCE_ASR_SEGMENT, index)
                    or ref.source_sha256 != baseline_sha
                    or ref.source_locator != asr_result.source_snapshot.canonical_video_relative
                    or ref.original_start_ms != segment.start_ms
                    or ref.original_end_ms != segment.end_ms
                    or member.text != segment.text):
                raise V2DHold("TARGETED_ASR_SOURCE_REFERENCE_MISMATCH")
            links = index_links.setdefault(index, {"cue_ids": set(), "group_ids": set()})
            links["cue_ids"].add(cue_id)
            links["group_ids"].add(group.group_id)

    if not index_links:
        raise V2DHold("TARGETED_ASR_NO_SOURCE_BOUND_BASELINE_SEGMENT")
    sources = []
    intervals = []
    source_cue_links = []
    for index in sorted(index_links):
        segment = asr_result.segments[index]
        source_id = stable_cue_id(EVIDENCE_SOURCE_ASR_SEGMENT, index)
        sources.append(TargetedSecondEvidenceSource(
            source_index=index, cue_id=source_id,
            start_ms=segment.start_ms, end_ms=segment.end_ms,
            source_text=segment.text,
        ))
        intervals.append(TargetedASRSourceInterval(
            source_id=source_id, source_index=index,
            start_ms=segment.start_ms, end_ms=segment.end_ms,
        ))
        source_cue_links.append((
            source_id, index,
            tuple(sorted(index_links[index]["cue_ids"])),
            tuple(sorted(index_links[index]["group_ids"])),
        ))
    policy = STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1
    geometry = plan_targeted_asr_source_windows_with_policy(tuple(intervals), policy=policy)
    windows = tuple(TargetedSecondEvidenceWindow(
        window_id="targeted-window-" + f"{index + 1:06d}",
        start_ms=window.start_ms, end_ms=window.end_ms,
        source_ids=window.source_ids, source_indices=window.source_indices,
    ) for index, window in enumerate(geometry))
    plan = _make_targeted_plan(asr_result.source_snapshot, tuple(sources), windows)
    context = {
        "schema_version": 1,
        "source_fingerprint": master.source_fingerprint,
        "master_sha256": master.master_sha256,
        "translation_session_id": translated.session_id,
        "translation_result_sha256": _sha(serialize_stateful_result(translated)),
        "target_cue_ids": list(requested),
        "source_cue_links": [[source_id, index, list(cue_ids), list(group_ids)]
                              for source_id, index, cue_ids, group_ids in source_cue_links],
        "baseline_asr_sha256": baseline_sha,
        "plan_binding_sha256": plan.binding_sha256,
    }
    context_raw = _wire(context)
    return _V2DTargetedRequest(
        plan=plan, cue_ids=requested,
        source_cue_links=tuple(source_cue_links),
        baseline_asr_sha256=baseline_sha,
        context_raw=context_raw,
        context_sha256=_sha(context_raw),
    )


def _build_external_targeted_request(master: V2DMaster, translated: StatefulSubtitleResult,
                                     requested: tuple[str, ...]) -> _V2DExternalTargetedRequest:
    """Plan target ASR for genuine aligned external-JA-only master cues.

    This path uses the existing external-cue planner/artifact contract. It
    never assigns a baseline ASR ordinal to the supplemental speech.
    """
    master = _validate_master(master)
    if (type(requested) is not tuple or not requested or len(set(requested)) != len(requested)
            or tuple(cue.cue_id for cue in translated.cues) != tuple(cue.cue_id for cue in master.cues)):
        raise V2DHold("TARGETED_ASR_EXTERNAL_REQUEST_DETACHED")
    review = master.review_set
    bundle = review._source_bundle
    payload = bundle.external_ja_payload
    document = bundle.external_ja_document
    alignment = review._source_alignment
    if (review.route != ROUTE_EXTERNAL_ALIGNMENT_ACCEPTED or alignment is None
            or payload is None or document is None or payload.sha256 != review.external_ja_sha256):
        raise V2DHold("TARGETED_ASR_EXTERNAL_ALIGNMENT_UNAVAILABLE")
    master_by_id = {cue.cue_id: cue for cue in master.cues}
    group_by_id = {group.group_id: group for group in master.utterance_plan.groups}
    member_by_key = {member.source_reference.key: member
                     for group in master.utterance_plan.groups for member in group.members}
    links: dict[int, dict[str, set[str]]] = {}
    for cue_id in requested:
        master_cue = master_by_id.get(cue_id)
        if master_cue is None or master_cue.group_id not in group_by_id:
            raise V2DHold("TARGETED_ASR_EXTERNAL_MASTER_CUE_UNBOUND")
        refs = tuple(ref for ref in master_cue.source_references
                     if ref.source == "external_ja")
        if not refs or any(ref.source == EVIDENCE_SOURCE_ASR_SEGMENT
                           for ref in master_cue.source_references):
            raise V2DHold("TARGETED_ASR_EXTERNAL_REQUEST_NOT_JA_ONLY")
        for ref in refs:
            member = member_by_key.get(ref.key)
            index = ref.source_index
            if member is None or member.source_reference != ref or not 0 <= index < len(document.cues):
                raise V2DHold("TARGETED_ASR_EXTERNAL_SOURCE_UNBOUND")
            cue = document.cues[index]
            if (ref.source_id != stable_cue_id("external_ja", index)
                    or ref.source_sha256 != payload.sha256
                    or ref.source_locator != payload.candidate.external_source_id
                    or ref.original_start_ms != cue.start_ms or ref.original_end_ms != cue.end_ms
                    or ref.aligned_start_ms is None or ref.aligned_end_ms is None
                    or member.text != cue.text):
                raise V2DHold("TARGETED_ASR_EXTERNAL_SOURCE_IDENTITY_MISMATCH")
            item = links.setdefault(index, {"cue_ids": set(), "group_ids": set()})
            item["cue_ids"].add(cue_id)
            item["group_ids"].add(master_cue.group_id)
    if not links:
        raise V2DHold("TARGETED_ASR_EXTERNAL_SOURCE_UNAVAILABLE")
    target_ids = tuple(stable_cue_id("external_ja", index) for index in sorted(links))
    windows = plan_targeted_asr_windows_with_policy(
        tuple(document.cues), alignment,
        policy=STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1,
        target_cue_ids=target_ids,
    )
    source_cue_links = tuple((stable_cue_id("external_ja", index),
                              tuple(sorted(value["cue_ids"])),
                              tuple(sorted(value["group_ids"])))
                             for index, value in sorted(links.items()))
    context = {
        "schema_version": 1,
        "source_fingerprint": master.source_fingerprint,
        "master_sha256": master.master_sha256,
        "translation_session_id": translated.session_id,
        "translation_result_sha256": _sha(serialize_stateful_result(translated)),
        "external_ja_sha256": payload.sha256,
        "target_cue_ids": list(requested),
        "source_cue_links": [[source_id, list(cue_ids), list(group_ids)]
                              for source_id, cue_ids, group_ids in source_cue_links],
        "windows": [[window.start_ms, window.end_ms, list(window.external_cue_ids)]
                    for window in windows],
    }
    context_raw = _wire(context)
    return _V2DExternalTargetedRequest(
        source_snapshot=review.source_snapshot, windows=windows, cue_ids=requested,
        source_cue_links=source_cue_links, context_raw=context_raw,
        context_sha256=_sha(context_raw),
    )


def _build_targeted_requests(master: V2DMaster, translated: StatefulSubtitleResult):
    requested = tuple(cue.cue_id for cue in translated.cues
                      if isinstance(cue, StatefulCueOutput) and cue.needs_audio_evidence)
    if not requested:
        raise V2DError("targeted request builder requires at least one audio request")
    refs_by_cue = {cue.cue_id: cue.source_references for cue in master.cues}
    baseline_ids, external_ids = [], []
    for cue_id in requested:
        refs = refs_by_cue.get(cue_id)
        if not refs:
            raise V2DHold("TARGETED_ASR_MASTER_CUE_UNBOUND")
        if any(ref.source == EVIDENCE_SOURCE_ASR_SEGMENT for ref in refs):
            baseline_ids.append(cue_id)
        elif any(ref.source == "external_ja" for ref in refs):
            external_ids.append(cue_id)
        else:
            raise V2DHold("TARGETED_ASR_NO_SOURCE_BOUND_INTERVAL")
    result = []
    if baseline_ids:
        result.append(_build_targeted_request(master, translated, tuple(baseline_ids)))
    if external_ids:
        result.append(_build_external_targeted_request(master, translated, tuple(external_ids)))
    return tuple(result)


def _execute_targeted_plan(plan: TargetedSecondEvidencePlan, *, asr_result: ASRResult,
                           targeted_transport, audio_window_provider) -> TargetedSecondEvidenceExecution:
    """Use the existing bounded window runner and binding contracts."""
    if type(plan) is not TargetedSecondEvidencePlan or plan.source_snapshot != asr_result.source_snapshot:
        raise V2DHold("TARGETED_ASR_PLAN_SOURCE_MISMATCH")
    if not callable(audio_window_provider):
        raise V2DHold("TARGETED_ASR_AUDIO_PROVIDER_UNAVAILABLE")
    results = []
    for window in plan.windows:
        segments = transcribe_targeted_window(
            window, source_snapshot=plan.source_snapshot,
            targeted_transport=targeted_transport,
            audio_window_provider=audio_window_provider,
        )
        results.append(TargetedSecondEvidenceWindowResult(
            source_snapshot=plan.source_snapshot,
            window_id=window.window_id,
            window_start_ms=window.start_ms,
            window_end_ms=window.end_ms,
            segments=segments,
            plan_binding_sha256=plan.binding_sha256,
        ))
    bindings = bind_targeted_second_evidence(plan, tuple(results))
    return TargetedSecondEvidenceExecution(
        plan=plan,
        policy_version=STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1.version,
        bindings=tuple(bindings),
    )


def build_v2d_targeted_asr_adapter(*, holding_resolver, source_provider, targeted_transport,
                                   audio_chunk_iterator=iter_audio_chunks):
    """Lazily reuse Stage11's protected source copy and bounded worker session.

    The adapter is called only after translation explicitly requests audio
    evidence. The protected video is prepared before opening the targeted
    transport session, so its worker lifetime does not include the copy.
    """
    runtime_identity = getattr(targeted_transport, "runtime_identity", None)
    engine_version = getattr(targeted_transport, "engine_version", None)
    if type(runtime_identity) is not ASRRuntimeIdentity or type(engine_version) is not str or not engine_version:
        raise V2DError("targeted ASR runtime identity is unavailable")

    def execute_for_snapshot(source_snapshot, operation):
        from teddy_discovery_stage11_live_adapters import _snapshot
        try:
            video, current = _snapshot(holding_resolver(source_snapshot.dvd_id), source_snapshot.dvd_id)
        except Exception as error:
            raise V2DHold("TARGETED_ASR_CURRENT_SOURCE_UNAVAILABLE") from error
        if current != source_snapshot:
            raise V2DHold("TARGETED_ASR_CURRENT_SOURCE_CHANGED")
        try:
            with source_provider.copy_to_temp(video, max_media_bytes=current.source_size) as local_source:
                if not isinstance(local_source, ASRLocalMediaSource) or local_source.source_snapshot != current:
                    raise V2DHold("TARGETED_ASR_LOCAL_SOURCE_CHANGED")
                session_factory = getattr(targeted_transport, "session", None)
                session = session_factory() if callable(session_factory) else nullcontext(targeted_transport)
                with session as active_transport:
                    if (getattr(active_transport, "runtime_identity", None) != runtime_identity
                            or getattr(active_transport, "engine_version", None) != engine_version):
                        raise V2DHold("TARGETED_ASR_RUNTIME_CHANGED")
                    provider = build_targeted_audio_window_provider(
                        local_source, audio_chunk_iterator=audio_chunk_iterator,
                    )
                    return operation(local_source, active_transport, provider)
        except V2DHold:
            raise
        except Exception as error:
            raise V2DHold("TARGETED_ASR_EXECUTION_OR_CLEANUP_FAILED") from error

    def targeted(asr_result: ASRResult, plan: TargetedSecondEvidencePlan):
        if type(asr_result) is not ASRResult or asr_result.source_snapshot != plan.source_snapshot:
            raise V2DHold("TARGETED_ASR_BASELINE_IDENTITY_MISMATCH")
        return execute_for_snapshot(
            asr_result.source_snapshot,
            lambda _source, active, provider: _execute_targeted_plan(
                plan, asr_result=asr_result, targeted_transport=active,
                audio_window_provider=provider,
            ),
        )

    def targeted_external_ja(request):
        if type(request) is not _V2DExternalTargetedRequest:
            raise V2DHold("TARGETED_ASR_EXTERNAL_REQUEST_INVALID")
        if not request.windows or any(type(window) is not TargetedASRWindow for window in request.windows):
            raise V2DHold("TARGETED_ASR_EXTERNAL_WINDOWS_INVALID")
        def run(_source, active, _provider):
            return run_targeted_hybrid_windows(
                request.windows, local_source=_source, targeted_transport=active,
                audio_chunk_iterator=audio_chunk_iterator,
            )
        return execute_for_snapshot(request.source_snapshot, run)

    targeted.runtime_identity = runtime_identity
    targeted.engine_version = engine_version
    targeted.bounded_worker_lifecycle = getattr(targeted_transport, "bounded_worker_lifecycle", False) is True
    targeted.targeted_external_ja = targeted_external_ja
    return targeted


def _read_private_owned(path: Path, *, max_bytes: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as error:
        raise V2DHold("TARGETED_ASR_PRIVATE_ARTIFACT_UNAVAILABLE") from error
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                or info.st_size <= 0 or info.st_size > max_bytes):
            raise V2DHold("TARGETED_ASR_PRIVATE_ARTIFACT_INVALID")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(max_bytes + 1)
        if len(raw) != info.st_size or len(raw) > max_bytes:
            raise V2DHold("TARGETED_ASR_PRIVATE_ARTIFACT_CHANGED")
        return raw
    finally:
        os.close(fd)


def _targeted_linkage_raw(request, artifact_sha256: str) -> bytes:
    return _wire({
        "schema_version": 1,
        "context_sha256": request.context_sha256,
        "context": json.loads(request.context_raw),
        "artifact_sha256": artifact_sha256,
    })


def _validate_targeted_v2d_artifact(artifact: TargetedSecondEvidenceArtifact, *,
                                    request: _V2DTargetedRequest,
                                    asr_result: ASRResult) -> dict[str, object]:
    if type(artifact) is not TargetedSecondEvidenceArtifact:
        raise V2DHold("TARGETED_ASR_ARTIFACT_TYPE_INVALID")
    try:
        from teddy_discovery_stage11_controller import _validate_targeted_artifact
        artifact = _validate_targeted_artifact(
            artifact,
            asr_result=asr_result,
            baseline_sha256=request.baseline_asr_sha256,
            expected_plan=request.plan,
            require_indexes=tuple(source.source_index for source in request.plan.sources),
        )
        projection = project_targeted_second_evidence_artifact(
            artifact,
            asr_result=asr_result,
            require_source_indexes=tuple(source.source_index for source in request.plan.sources),
        )
    except Exception as error:
        raise V2DHold("TARGETED_ASR_ARTIFACT_SOURCE_OR_PLAN_MISMATCH") from error
    if set(projection) != {source.cue_id for source in request.plan.sources}:
        raise V2DHold("TARGETED_ASR_PROJECTION_COVERAGE_MISMATCH")
    if any(item.status != TARGETED_SECOND_EVIDENCE_STATUS_PRESENT_UNRESOLVED
           for item in projection.values()):
        raise V2DHold("TARGETED_ASR_EVIDENCE_EMPTY_OR_NOISY")
    return projection


def _load_or_run_targeted_evidence(request: _V2DTargetedRequest, *, master: V2DMaster,
                                   targeted_runner: Callable | None,
                                   staging_root: str | Path,
                                   reuse_only: bool) -> _V2DTargetedEvidence:
    bundle = master.review_set._source_bundle
    asr_result = bundle.asr_result
    try:
        root = _private_dir(staging_root)
    except V2DError as error:
        if reuse_only:
            raise V2DHold("TARGETED_ASR_RESUME_ROOT_UNAVAILABLE") from error
        raise
    try:
        target_root = _private_child(root, "targeted-second-evidence", create=not reuse_only)
        stage = _private_child(target_root, request.context_sha256, create=not reuse_only)
    except V2DError as error:
        if reuse_only:
            raise V2DHold("TARGETED_ASR_RESUME_ARTIFACT_MISSING") from error
        raise
    artifact_path = stage / "targeted-second-evidence-v1.json"
    linkage_path = stage / "v2d-targeted-linkage-v1.json"
    artifact_present = artifact_path.exists() or artifact_path.is_symlink()
    linkage_present = linkage_path.exists() or linkage_path.is_symlink()
    if artifact_present != linkage_present:
        raise V2DHold("TARGETED_ASR_ARTIFACT_LINKAGE_INCOMPLETE")

    if artifact_present:
        artifact_raw = _read_private_owned(
            artifact_path, max_bytes=MAX_TARGETED_SECOND_EVIDENCE_ARTIFACT_BYTES,
        )
        linkage_raw = _read_private_owned(linkage_path, max_bytes=V2D_MAX_JSON_BYTES)
        try:
            artifact = parse_targeted_second_evidence_artifact_bytes(artifact_raw)
            if serialize_targeted_second_evidence_artifact(artifact) != artifact_raw:
                raise ValueError("noncanonical artifact")
            artifact_sha = _sha(artifact_raw)
            if linkage_raw != _targeted_linkage_raw(request, artifact_sha):
                raise ValueError("detached linkage")
        except Exception as error:
            raise V2DHold("TARGETED_ASR_ARTIFACT_OR_LINKAGE_INVALID") from error
    else:
        if reuse_only:
            raise V2DHold("TARGETED_ASR_RESUME_ARTIFACT_MISSING")
        if not callable(targeted_runner):
            raise V2DHold("TARGETED_ASR_ADAPTER_UNAVAILABLE")
        try:
            execution = targeted_runner(asr_result, request.plan)
            if type(execution) is not TargetedSecondEvidenceExecution:
                raise ValueError("invalid targeted execution")
            execution.__post_init__()
            if (execution.plan != request.plan
                    or execution.policy_version != STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1.version):
                raise ValueError("detached targeted execution")
            runtime_identity = getattr(targeted_runner, "runtime_identity", None)
            engine_version = getattr(targeted_runner, "engine_version", None)
            if type(runtime_identity) is not ASRRuntimeIdentity or type(engine_version) is not str or not engine_version:
                raise ValueError("missing targeted runtime provenance")
            artifact = targeted_second_evidence_artifact_from_execution(
                execution,
                baseline_asr_artifact_sha256=request.baseline_asr_sha256,
                runtime_identity=runtime_identity,
                engine_version=engine_version,
            )
            _validate_targeted_v2d_artifact(artifact, request=request, asr_result=asr_result)
            write_targeted_second_evidence_artifact(artifact_path, artifact)
            artifact_raw = _read_private_owned(
                artifact_path, max_bytes=MAX_TARGETED_SECOND_EVIDENCE_ARTIFACT_BYTES,
            )
            readback = parse_targeted_second_evidence_artifact_bytes(artifact_raw)
            if readback != artifact or serialize_targeted_second_evidence_artifact(readback) != artifact_raw:
                raise ValueError("targeted artifact readback differs")
            artifact_sha = _sha(artifact_raw)
            _write_exclusive(linkage_path, _targeted_linkage_raw(request, artifact_sha))
            linkage_raw = _read_private_owned(linkage_path, max_bytes=V2D_MAX_JSON_BYTES)
            if linkage_raw != _targeted_linkage_raw(request, artifact_sha):
                raise ValueError("targeted linkage readback differs")
        except V2DHold:
            raise
        except Exception as error:
            raise V2DHold("TARGETED_ASR_ADAPTER_VALIDATION_OR_PERSISTENCE_FAILED") from error

    projection = _validate_targeted_v2d_artifact(artifact, request=request, asr_result=asr_result)
    artifact_sha = _sha(serialize_targeted_second_evidence_artifact(artifact))
    # Map each genuine source/window response back only to the V2-C groups and
    # translation cues that own the selected baseline ASR source references.
    link_by_source = {source_id: (cue_ids, group_ids)
                      for source_id, _index, cue_ids, group_ids in request.source_cue_links}
    result_by_window = {result.window_id: result for result in artifact.results}
    group_payloads: dict[str, dict[str, dict[str, object]]] = {}
    source_window_evidence = []
    for binding in artifact.bindings:
        cue_ids, group_ids = link_by_source.get(binding.source_id, ((), ()))
        if not cue_ids or not group_ids:
            raise V2DHold("TARGETED_ASR_ARTIFACT_SOURCE_LINK_MISSING")
        result = result_by_window[binding.window.window_id]
        projection[binding.source_id].__post_init__()
        source_window_evidence.append((binding.source_id, binding.window.window_id,
                                       tuple(segment.text for segment in result.segments)))
        for group_id in group_ids:
            per_window = group_payloads.setdefault(group_id, {})
            payload = per_window.setdefault(binding.window.window_id, {
                "window_id": binding.window.window_id,
                "window_start_ms": binding.window.start_ms,
                "window_end_ms": binding.window.end_ms,
                "baseline_source_ids": [],
                "segments": [{"start_ms": segment.start_ms, "end_ms": segment.end_ms,
                              "text": segment.text} for segment in result.segments],
            })
            payload["baseline_source_ids"].append(binding.source_id)
    if (not group_payloads
            or {source_id for source_id, _, _ in source_window_evidence}
            != {source.cue_id for source in request.plan.sources}):
        raise V2DHold("TARGETED_ASR_EVIDENCE_NOT_PROJECTABLE")
    return _V2DTargetedEvidence(
        artifact=artifact,
        artifact_sha256=artifact_sha,
        linkage_sha256=_sha(linkage_raw),
        group_payloads=tuple((key, {"artifact_sha256": artifact_sha,
                                    "windows": [dict(item, baseline_source_ids=sorted(set(item["baseline_source_ids"])))
                                                for _, item in sorted(values.items())]})
                             for key, values in sorted(group_payloads.items())),
        source_window_evidence=tuple(sorted(source_window_evidence)),
    )


def _validate_external_targeted_artifact(artifact: TargetedASRArtifact, *,
                                         request: _V2DExternalTargetedRequest,
                                         targeted_runner) -> TargetedASRArtifact:
    if type(artifact) is not TargetedASRArtifact:
        raise V2DHold("TARGETED_ASR_EXTERNAL_ARTIFACT_TYPE_INVALID")
    try:
        artifact.__post_init__()
        require_matching_targeted_asr_source(artifact, request.source_snapshot)
    except Exception as error:
        raise V2DHold("TARGETED_ASR_EXTERNAL_SOURCE_MISMATCH") from error
    runtime_identity = getattr(targeted_runner, "runtime_identity", None)
    engine_version = getattr(targeted_runner, "engine_version", None)
    if (type(runtime_identity) is not ASRRuntimeIdentity or type(engine_version) is not str
            or not engine_version or artifact.runtime_identity != runtime_identity
            or artifact.engine_version != engine_version):
        raise V2DHold("TARGETED_ASR_EXTERNAL_RUNTIME_MISMATCH")
    if len(artifact.windows) != len(request.windows):
        raise V2DHold("TARGETED_ASR_EXTERNAL_WINDOW_COVERAGE_MISMATCH")
    expected_ids = {source_id for source_id, _, _ in request.source_cue_links}
    observed_ids = set()
    for expected, actual in zip(request.windows, artifact.windows, strict=True):
        if (actual.window_start_ms != expected.start_ms or actual.window_end_ms != expected.end_ms
                or actual.external_cue_ids != expected.external_cue_ids):
            raise V2DHold("TARGETED_ASR_EXTERNAL_WINDOW_MISMATCH")
        if observed_ids.intersection(actual.external_cue_ids):
            raise V2DHold("TARGETED_ASR_EXTERNAL_SOURCE_DUPLICATED")
        observed_ids.update(actual.external_cue_ids)
    if observed_ids != expected_ids:
        raise V2DHold("TARGETED_ASR_EXTERNAL_SOURCE_COVERAGE_MISMATCH")
    if not any(window.segments for window in artifact.windows):
        raise V2DHold("TARGETED_ASR_EXTERNAL_EVIDENCE_EMPTY")
    return artifact


def _load_or_run_external_targeted_evidence(
    request: _V2DExternalTargetedRequest, *, master: V2DMaster,
    targeted_runner: Callable | None, staging_root: str | Path,
    reuse_only: bool,
) -> _V2DTargetedEvidence:
    try:
        root = _private_dir(staging_root)
        target_root = _private_child(root, "targeted-external-ja-evidence", create=not reuse_only)
        stage = _private_child(target_root, request.context_sha256, create=not reuse_only)
    except V2DError as error:
        if reuse_only:
            raise V2DHold("TARGETED_ASR_EXTERNAL_RESUME_ARTIFACT_MISSING") from error
        raise
    artifact_path = stage / "targeted-external-ja-asr-v1.json"
    linkage_path = stage / "v2d-targeted-linkage-v1.json"
    artifact_present = artifact_path.exists() or artifact_path.is_symlink()
    linkage_present = linkage_path.exists() or linkage_path.is_symlink()
    if artifact_present != linkage_present:
        raise V2DHold("TARGETED_ASR_EXTERNAL_LINKAGE_INCOMPLETE")

    if artifact_present:
        artifact_raw = _read_private_owned(artifact_path, max_bytes=MAX_TARGETED_ASR_ARTIFACT_BYTES)
        linkage_raw = _read_private_owned(linkage_path, max_bytes=V2D_MAX_JSON_BYTES)
        try:
            artifact = parse_targeted_asr_artifact_bytes(artifact_raw)
            if serialize_targeted_asr_artifact(artifact) != artifact_raw:
                raise ValueError("noncanonical external targeted artifact")
            artifact_sha = _sha(artifact_raw)
            if linkage_raw != _targeted_linkage_raw(request, artifact_sha):
                raise ValueError("external targeted evidence is detached")
        except Exception as error:
            raise V2DHold("TARGETED_ASR_EXTERNAL_ARTIFACT_OR_LINKAGE_INVALID") from error
    else:
        if reuse_only:
            raise V2DHold("TARGETED_ASR_EXTERNAL_RESUME_ARTIFACT_MISSING")
        run_external = getattr(targeted_runner, "targeted_external_ja", None)
        if not callable(run_external):
            raise V2DHold("TARGETED_ASR_EXTERNAL_ADAPTER_UNAVAILABLE")
        try:
            artifact = run_external(request)
            artifact = _validate_external_targeted_artifact(
                artifact, request=request, targeted_runner=targeted_runner,
            )
            artifact_raw = serialize_targeted_asr_artifact(artifact)
            _write_exclusive(artifact_path, artifact_raw)
            artifact_raw = _read_private_owned(artifact_path, max_bytes=MAX_TARGETED_ASR_ARTIFACT_BYTES)
            readback = parse_targeted_asr_artifact_bytes(artifact_raw)
            if readback != artifact or serialize_targeted_asr_artifact(readback) != artifact_raw:
                raise ValueError("external targeted artifact readback differs")
            artifact_sha = _sha(artifact_raw)
            _write_exclusive(linkage_path, _targeted_linkage_raw(request, artifact_sha))
            linkage_raw = _read_private_owned(linkage_path, max_bytes=V2D_MAX_JSON_BYTES)
            if linkage_raw != _targeted_linkage_raw(request, artifact_sha):
                raise ValueError("external targeted linkage readback differs")
        except V2DHold:
            raise
        except Exception as error:
            raise V2DHold("TARGETED_ASR_EXTERNAL_VALIDATION_OR_PERSISTENCE_FAILED") from error

    artifact = _validate_external_targeted_artifact(
        artifact, request=request, targeted_runner=targeted_runner,
    )
    artifact_raw = serialize_targeted_asr_artifact(artifact)
    artifact_sha = _sha(artifact_raw)
    link_by_source = {source_id: (cue_ids, group_ids)
                      for source_id, cue_ids, group_ids in request.source_cue_links}
    group_payloads: dict[str, dict[str, dict[str, object]]] = {}
    source_window_evidence = []
    for window_index, result in enumerate(artifact.windows, start=1):
        window_id = f"external-ja-window-{window_index:06d}"
        segments = []
        for segment_index, segment in enumerate(result.segments, start=1):
            candidate_id = _sha(_wire([
                request.context_sha256, artifact_sha, window_id, segment_index,
                segment.start_ms, segment.end_ms, _sha(segment.text.encode("utf-8")),
            ]))
            segments.append({
                "targeted_candidate_id": candidate_id,
                "start_ms": segment.start_ms,
                "end_ms": segment.end_ms,
                "text": segment.text,
            })
        for source_id in result.external_cue_ids:
            cue_ids, group_ids = link_by_source.get(source_id, ((), ()))
            if not cue_ids or not group_ids:
                raise V2DHold("TARGETED_ASR_EXTERNAL_SOURCE_LINK_MISSING")
            source_window_evidence.append((source_id, window_id,
                                          tuple(segment.text for segment in result.segments)))
            for group_id in group_ids:
                per_window = group_payloads.setdefault(group_id, {})
                payload = per_window.setdefault(window_id, {
                    "window_id": window_id,
                    "window_start_ms": result.window_start_ms,
                    "window_end_ms": result.window_end_ms,
                    "external_ja_source_ids": [],
                    "segments": segments,
                })
                payload["external_ja_source_ids"].append(source_id)
    if not group_payloads or {item[0] for item in source_window_evidence} != {
        source_id for source_id, _, _ in request.source_cue_links
    }:
        raise V2DHold("TARGETED_ASR_EXTERNAL_EVIDENCE_NOT_PROJECTABLE")
    return _V2DTargetedEvidence(
        artifact=artifact,
        artifact_sha256=artifact_sha,
        linkage_sha256=_sha(linkage_raw),
        group_payloads=tuple((group_id, {
            "artifact_sha256": artifact_sha,
            "windows": [dict(item, external_ja_source_ids=sorted(set(item["external_ja_source_ids"])))
                        for _, item in sorted(windows.items())],
        }) for group_id, windows in sorted(group_payloads.items())),
        source_window_evidence=tuple(sorted(source_window_evidence)),
    )


def _combine_targeted_evidence(items: tuple[_V2DTargetedEvidence, ...]) -> _V2DTargetedEvidence:
    if not items:
        raise V2DHold("TARGETED_ASR_EVIDENCE_NOT_FOUND")
    if len(items) == 1:
        return items[0]
    artifact_sha = _sha(_wire([item.artifact_sha256 for item in items]))
    linkage_sha = _sha(_wire([item.linkage_sha256 for item in items]))
    groups: dict[str, dict[str, dict[str, object]]] = {}
    for item in items:
        for group_id, payload in item.group_payloads:
            windows = groups.setdefault(group_id, {})
            for window in payload["windows"]:
                window_id = window["window_id"]
                if window_id in windows:
                    raise V2DHold("TARGETED_ASR_COMBINED_WINDOW_COLLISION")
                windows[window_id] = window
    return _V2DTargetedEvidence(
        artifact=tuple(item.artifact for item in items),
        artifact_sha256=artifact_sha,
        linkage_sha256=linkage_sha,
        group_payloads=tuple((group_id, {"artifact_sha256": artifact_sha,
                                         "windows": [windows[key] for key in sorted(windows)]})
                             for group_id, windows in sorted(groups.items())),
        source_window_evidence=tuple(sorted(
            evidence for item in items for evidence in item.source_window_evidence
        )),
    )


def _readjudicate_targeted_groups(plan: UtteranceReviewPlan,
                                  original: V2DAdjudication,
                                  evidence: _V2DTargetedEvidence, *,
                                  invoke: Callable,
                                  hermes_settings: HermesExecutionSettings,
                                  staging_root: str | Path,
                                  claim_token: int,
                                  reuse_only: bool) -> V2DAdjudication:
    """Revisit only affected groups; ASR output stays supporting evidence."""
    evidence_by_group = dict(evidence.group_payloads)
    original_by_group = {item.group_id: item for item in original.groups}
    if not evidence_by_group or set(evidence_by_group) - set(original_by_group):
        raise V2DHold("TARGETED_ASR_GROUP_EVIDENCE_UNBOUND")
    root = _private_dir(staging_root)
    context_sha = _sha(_wire({
        "source_fingerprint": _source_fingerprint(plan),
        "artifact_sha256": evidence.artifact_sha256,
        "linkage_sha256": evidence.linkage_sha256,
        "claim_token": claim_token,
    }))
    try:
        task = _private_child(root, "targeted-readjudication-" + context_sha, create=not reuse_only)
    except V2DError as error:
        raise V2DHold("TARGETED_ASR_READJUDICATION_RESUME_STAGE_MISSING") from error
    resolved_groups = []
    for group in plan.groups:
        if group.group_id not in evidence_by_group:
            resolved_groups.append(original_by_group[group.group_id])
            continue
        group_payload = _group_payload(plan, group)
        group_payload["targeted_second_evidence"] = evidence_by_group[group.group_id]
        prompt = (
            SEMANTIC_ADJUDICATION_INSTRUCTION
            + "\nSupplemental targeted ASR is source-bound corroboration only. "
              "It may clarify existing source members; do not invent source IDs, indexes, times, or outputs without an existing source span."
            + "\nSOURCE_BOUND_GROUP=" + _wire(group_payload).decode("utf-8")
        ).encode("utf-8")
        if len(prompt) > V2D_MAX_PROMPT_BYTES:
            raise V2DHold("TARGETED_ASR_READJUDICATION_PROMPT_TOO_LARGE")
        group_key = _sha(group.group_id.encode("utf-8"))[:24]
        try:
            group_dir = _private_child(task, "group-" + group_key, create=not reuse_only)
        except V2DError as error:
            raise V2DHold("TARGETED_ASR_READJUDICATION_STAGE_MISSING") from error
        validator = lambda raw, group=group: _parse_group_response(raw, group)
        adjudicated = invoke(
            prompt, group_dir, "ja-master-targeted-readjudication", validator,
            hermes_settings=hermes_settings, reuse_only=reuse_only,
        )
        if type(adjudicated) is not GroupAdjudication:
            raise V2DHold("TARGETED_ASR_READJUDICATION_RESULT_INVALID")
        resolved_groups.append(adjudicated)
    return validate_adjudication(
        plan, V2DAdjudication(_source_fingerprint(plan), tuple(resolved_groups)),
    )


def _targeted_translation_evidence(master: V2DMaster,
                                   evidence: _V2DTargetedEvidence) -> dict[str, tuple[str, ...]]:
    """Project validated window text only to master cues owning the source."""
    evidence_by_source = {source_id: (window_id, texts)
                          for source_id, window_id, texts in evidence.source_window_evidence}
    projected = {}
    for cue in master.cues:
        cue_source_ids = {
            ref.source_id for ref in cue.source_references
        }
        selected = cue_source_ids & set(evidence_by_source)
        window_ids = tuple(sorted({evidence_by_source[source_id][0] for source_id in selected}))
        texts = []
        for window_id in window_ids:
            source_entry = next((entry for entry in evidence.source_window_evidence
                                 if entry[1] == window_id and entry[0] in selected), None)
            if source_entry is None:
                raise V2DHold("TARGETED_ASR_TRANSLATION_PROJECTION_MISSING")
            texts.extend(source_entry[2])
        if texts:
            projected[cue.cue_id] = tuple(texts)
    return projected


def _stage_bound_native_invoke(invoke: Callable, current_settings: HermesExecutionSettings):
    """Reuse stored NativeNormalFirstPass settings per exact prompt stage.

    Existing receipts remain authoritative for completed/in-progress Native
    attempts. A stage with no receipt starts with the current resolved profile;
    a stage with receipts continues using the exact stored profile. The
    existing NativeNormalFirstPass still validates prompt, receipt, return
    code, tool count and output. No receipt or retry format is added here.
    """
    owner = getattr(invoke, "__self__", None)
    if type(current_settings) is not HermesExecutionSettings:
        raise V2DError("resolved Hermes settings are required for stage invocation")
    if owner is None or type(getattr(owner, "_verified_attempts", None)) is not list:
        return invoke, owner
    from teddy_discovery_stage11_normal_mode import (
        MAX_NATIVE_PROMPT_BYTES,
        MAX_VALIDATION_ATTEMPTS,
        _settings_object_from_evidence,
    )
    from teddy_discovery_stage11_controller import _read_private_file

    def stage_invoke(prompt, directory, label, validator, *, hermes_settings,
                     reuse_only=False):
        if type(hermes_settings) is not HermesExecutionSettings or hermes_settings != current_settings:
            raise V2DError("V2-D stage settings differ from the pinned pipeline profile")
        saved_settings = None
        for attempt in range(1, MAX_VALIDATION_ATTEMPTS + 1):
            prefix = Path(directory) / f"{label}-attempt-{attempt}"
            receipt_path = prefix.with_suffix(".receipt.json")
            if receipt_path.is_symlink():
                raise V2DHold("NATIVE_STAGE_RECEIPT_IS_SYMLINK")
            if not receipt_path.exists():
                continue
            try:
                receipt = json.loads(_read_private_file(receipt_path, max_bytes=1024 * 1024))
                prompt_raw = _read_private_file(
                    prefix.with_suffix(".prompt.txt"), max_bytes=MAX_NATIVE_PROMPT_BYTES,
                )
                evidence = receipt["hermes_execution_settings"]
                stored = _settings_object_from_evidence(evidence)
            except Exception as error:
                raise V2DHold("NATIVE_STAGE_RECEIPT_SETTINGS_UNVERIFIABLE") from error
            if prompt_raw != prompt or stored.evidence() != evidence:
                raise V2DHold("NATIVE_STAGE_RECEIPT_INPUT_OR_SETTINGS_MISMATCH")
            if saved_settings is not None and stored != saved_settings:
                raise V2DHold("NATIVE_STAGE_ATTEMPTS_MIX_HERMES_PROFILES")
            saved_settings = stored
        selected_settings = current_settings if saved_settings is None else saved_settings
        before = len(owner._verified_attempts)
        try:
            return invoke(
                prompt, directory, label, validator,
                hermes_settings=selected_settings,
                reuse_only=reuse_only,
            )
        finally:
            for item in owner._verified_attempts[before:]:
                if item.get("label") == label:
                    item["hermes_execution_settings"] = selected_settings.evidence()

    return stage_invoke, owner


def _parse_group_response(raw: bytes, group) -> GroupAdjudication:
    data = _load_json(raw, "JA Master adjudication")
    if type(data) is not dict or set(data) != {"group_id", "candidate_decisions", "source_decisions", "outputs"}:
        raise V2DError("JA Master response fields differ")
    if data["group_id"] != group.group_id:
        raise V2DError("JA Master response group differs")
    if type(data["candidate_decisions"]) is not list or type(data["source_decisions"]) is not list or type(data["outputs"]) is not list:
        raise V2DError("JA Master response arrays are invalid")
    candidates = []
    for item in data["candidate_decisions"]:
        if type(item) is not dict or set(item) != {"candidate_id", "status", "rationale"}:
            raise V2DError("candidate decision fields differ")
        candidates.append(CandidateDecision(item["candidate_id"], item["status"], item["rationale"]))
    sources = []
    for item in data["source_decisions"]:
        if type(item) is not dict or set(item) != {"source_key", "status", "rationale"}:
            raise V2DError("source decision fields differ")
        sources.append(SourceDecision(item["source_key"], item["status"], item["rationale"]))
    outputs = []
    for item in data["outputs"]:
        if type(item) is not dict or set(item) != {"japanese_text", "source_spans", "rationale"} or type(item["source_spans"]) is not list:
            raise V2DError("JA Master output fields differ")
        spans = []
        for span in item["source_spans"]:
            if type(span) is not dict or set(span) != {"source_key", "word_start_index", "word_end_index"}:
                raise V2DError("JA Master source span fields differ")
            spans.append(SourceSpan(span["source_key"], span["word_start_index"], span["word_end_index"]))
        outputs.append(MasterOutputProposal(item["japanese_text"], tuple(spans), item["rationale"]))
    return GroupAdjudication(group.group_id, tuple(candidates), tuple(sources), tuple(outputs))


def validate_adjudication(plan: UtteranceReviewPlan, adjudication: V2DAdjudication) -> V2DAdjudication:
    plan = validate_utterance_review_plan(plan)
    if type(adjudication) is not V2DAdjudication or adjudication.source_fingerprint != _source_fingerprint(plan):
        raise V2DError("adjudication is detached from source evidence")
    if tuple(item.group_id for item in adjudication.groups) != tuple(group.group_id for group in plan.groups):
        raise V2DError("adjudication group coverage/order differs")
    for group, resolved in zip(plan.groups, adjudication.groups, strict=True):
        expected_candidates = tuple(group.candidate_ids)
        expected_sources = tuple(member.source_reference.key for member in group.members)
        if tuple(item.candidate_id for item in resolved.candidate_decisions) != expected_candidates:
            raise V2DError("candidate coverage/order differs")
        if tuple(item.source_key for item in resolved.source_decisions) != expected_sources:
            raise V2DError("source coverage/order differs")
    return adjudication


SEMANTIC_ADJUDICATION_INSTRUCTION = """Interpret this one source-bound utterance group for a Japanese master. Return JSON only with exactly: group_id, candidate_decisions, source_decisions, outputs. Every candidate relation and every source must receive ACCEPTED, REJECTED, or UNCERTAIN plus a reason. A candidate relation is evidence, not proof of same utterance. Do not merge merely from overlap or identical text; preserve repeated spoken dialogue unless context supports a duplicate. Decide whether to merge or split semantic dialogue. Outputs contain Japanese text and source_spans only; each span has source_key and optional half-open word_start_index/word_end_index. Do not provide cue IDs, timestamps, speakers, ordering, or confidence. Source spans are claims the validator checks: only ASR word references may be split, with all words partitioned exactly once. Do not assign speakers; retain speaker evidence as supplied. If evidence is insufficient use UNCERTAIN. The caller owns IDs, time, ordering, source ownership, and files."""


def adjudicate_ja_master(
    plan: UtteranceReviewPlan,
    *,
    invoke: Callable,
    hermes_settings: HermesExecutionSettings,
    staging_root: str | Path,
    claim_token: int,
    reuse_only: bool = False,
) -> V2DAdjudication:
    """Run/replay one bounded semantic request per V2-C group via Native invoke."""
    plan = validate_utterance_review_plan(plan)
    if type(hermes_settings) is not HermesExecutionSettings:
        raise V2DError("resolved Hermes profile settings are required")
    if type(claim_token) is not int or claim_token < 1:
        raise V2DError("claim token is invalid")
    root = _private_dir(staging_root)
    fingerprint = _source_fingerprint(plan)
    session = str(uuid.uuid5(V2D_SESSION_NAMESPACE, fingerprint + ":" + str(claim_token)))
    task = _private_child(root, session, create=not reuse_only)
    results = []
    for group in plan.groups:
        payload = _wire(_group_payload(plan, group))
        prompt = (SEMANTIC_ADJUDICATION_INSTRUCTION + "\nSOURCE_BOUND_GROUP=" + payload.decode("utf-8")).encode("utf-8")
        if len(prompt) > V2D_MAX_PROMPT_BYTES:
            raise V2DError("one utterance group exceeds the existing native prompt bound")
        group_dir = _private_child(task, "group-" + group.group_id.removeprefix("group-")[:32], create=not reuse_only)
        validator = lambda raw, group=group: _parse_group_response(raw, group)
        resolved = invoke(prompt, group_dir, "ja-master-adjudication", validator,
                          hermes_settings=hermes_settings, reuse_only=reuse_only)
        if type(resolved) is not GroupAdjudication:
            raise V2DError("semantic executor did not return a validated group response")
        results.append(resolved)
    return validate_adjudication(plan, V2DAdjudication(fingerprint, tuple(results)))


def materialize_ja_master(plan: UtteranceReviewPlan, adjudication: V2DAdjudication, *,
                          targeted_evidence_sha256: str | None = None) -> V2DMaster:
    """Resolve source ownership and exact time from validated semantic spans."""
    plan = validate_utterance_review_plan(plan)
    adjudication = validate_adjudication(plan, adjudication)
    if targeted_evidence_sha256 is not None:
        _digest(targeted_evidence_sha256, "targeted_evidence_sha256")
    if any(item.status == DECISION_UNCERTAIN for group in adjudication.groups
           for item in (*group.candidate_decisions, *group.source_decisions)):
        raise V2DHold("JA_MASTER_UNRESOLVED")
    cues = []
    for group, decisions in zip(plan.groups, adjudication.groups, strict=True):
        member_by_key = {item.source_reference.key: item for item in group.members}
        decision_by_key = {item.source_key: item for item in decisions.source_decisions}
        accepted = {key for key, item in decision_by_key.items() if item.status == DECISION_ACCEPTED}
        used: dict[str, list[tuple[int | None, int | None]]] = {key: [] for key in accepted}
        pending = []
        for output_index, proposal in enumerate(decisions.outputs):
            starts, ends, refs, evidence_ids = [], [], [], []
            source_keys = tuple(span.source_key for span in proposal.source_spans)
            if any(key not in accepted for key in source_keys):
                raise V2DError("output uses a rejected or unknown source")
            for span in proposal.source_spans:
                member = member_by_key[span.source_key]
                ref = member.source_reference
                if ref.aligned_start_ms is None or ref.aligned_end_ms is None:
                    raise V2DHold("ACCEPTED_SOURCE_HAS_NO_CANONICAL_TIME")
                if span.word_start_index is None:
                    if used[span.source_key]:
                        raise V2DError("source appears in multiple outputs without a complete ASR word split")
                    start, end = ref.aligned_start_ms, ref.aligned_end_ms
                else:
                    if ref.source != "asr_segment" or not member.word_references:
                        raise V2DError("only timed ASR words can own a split")
                    if span.word_end_index > len(member.word_references):
                        raise V2DError("ASR split extends beyond source word references")
                    selected_words = member.word_references[span.word_start_index:span.word_end_index]
                    if len(selected_words) != span.word_end_index - span.word_start_index:
                        raise V2DError("ASR split word coverage is incomplete")
                    start, end = selected_words[0].start_ms, selected_words[-1].end_ms
                used[span.source_key].append((span.word_start_index, span.word_end_index))
                starts.append(start); ends.append(end); refs.append(ref)
                evidence_ids.extend(link.turn.turn_id for link in member.speaker_links)
                for word in member.word_references:
                    evidence_ids.extend(link.turn.turn_id for link in word.speaker_links)
            pending.append((min(starts), max(ends), proposal, tuple(refs), tuple(sorted(set(evidence_ids))), output_index))
        for key in accepted:
            spans = used[key]
            member = member_by_key[key]
            if not spans:
                raise V2DError("accepted source is absent from JA Master outputs")
            if len(spans) == 1 and spans[0] == (None, None):
                continue
            words = member.word_references
            if not words or any(start is None or end is None for start, end in spans):
                raise V2DError("source split lacks ASR word evidence")
            ordered = sorted(spans)
            cursor = 0
            for start, end in ordered:
                if start != cursor or end <= start:
                    raise V2DError("ASR split ranges overlap or leave a gap")
                cursor = end
            if cursor != len(words):
                raise V2DError("ASR split does not cover all source words")
        if set(decision_by_key) != set(member_by_key):
            raise V2DError("source decision coverage changed")
        for start, end, proposal, refs, evidence_ids, output_index in sorted(
            pending, key=lambda item: (item[0], item[1], tuple(ref.key for ref in item[3]), item[5])
        ):
            source_keys = tuple(ref.key for ref in refs)
            cue_id = "v2d-" + _sha(_wire([group.group_id, source_keys,
                                          [_fraction(start), _fraction(end)], output_index]))
            cues.append(V2DMasterCue(cue_id, group.group_id, proposal.japanese_text,
                                     refs, start, end, group.speaker_status, evidence_ids))
    if not cues:
        raise V2DHold("JA_MASTER_HAS_NO_ACCEPTED_CUES")
    cues.sort(key=lambda cue: (cue.start_ms, cue.end_ms, cue.cue_id))
    if len({cue.cue_id for cue in cues}) != len(cues):
        raise V2DError("duplicate deterministic JA Master cue identity")
    fingerprint = _source_fingerprint(plan)
    identity = {
        "source_fingerprint": fingerprint,
        "route": plan.review_set.route,
        "asr_sha256": plan.review_set.asr_sha256,
        "external_ja_sha256": plan.review_set.external_ja_sha256,
        "candidate_decisions": [[item.candidate_id, item.status, item.rationale]
                                for group in adjudication.groups for item in group.candidate_decisions],
        "source_decisions": [[item.source_key, item.status, item.rationale]
                             for group in adjudication.groups for item in group.source_decisions],
        "cues": [[cue.cue_id, cue.text, [ref.key for ref in cue.source_references],
                  _fraction(cue.start_ms), _fraction(cue.end_ms), cue.speaker_status,
                  list(cue.speaker_evidence_ids)] for cue in cues],
    }
    return V2DMaster(plan.review_set, plan, adjudication, tuple(cues), fingerprint,
                     _sha(_wire(identity)), targeted_evidence_sha256)


def _validate_master(master: V2DMaster) -> V2DMaster:
    if type(master) is not V2DMaster:
        raise V2DError("exact V2-D master is required")
    rebuilt = materialize_ja_master(
        master.utterance_plan, master.adjudication,
        targeted_evidence_sha256=master.targeted_evidence_sha256,
    )
    if rebuilt != master:
        raise V2DError("JA Master differs from its validated source decisions")
    return rebuilt


def _build_translation_package(master: V2DMaster, claim_token: int,
                               semantic_policy=DEFAULT_STATEFUL_SEMANTIC_POLICY, *,
                               targeted_evidence_by_cue: dict[str, tuple[str, ...]] | None = None,
                               targeted_evidence_sha256: str | None = None):
    master = _validate_master(master)
    if type(claim_token) is not int or claim_token < 1:
        raise V2DError("claim token is invalid")
    targeted_evidence_by_cue = {} if targeted_evidence_by_cue is None else targeted_evidence_by_cue
    if type(targeted_evidence_by_cue) is not dict:
        raise V2DError("targeted translation evidence map is invalid")
    if targeted_evidence_by_cue:
        _digest(targeted_evidence_sha256, "targeted_evidence_sha256")
        if set(targeted_evidence_by_cue) - {cue.cue_id for cue in master.cues}:
            raise V2DError("targeted translation evidence is detached from JA Master cues")
    elif targeted_evidence_sha256 is not None:
        raise V2DError("targeted evidence digest has no translation evidence")
    members = {member.source_reference.key: member
               for group in master.utterance_plan.groups for member in group.members}
    cues = []
    for index, cue in enumerate(master.cues):
        asr_texts = [members[ref.key].text for ref in cue.source_references if ref.source == "asr_segment"]
        asr_texts.extend(targeted_evidence_by_cue.get(cue.cue_id, ()))
        primary = cue.text
        # The semantic master is the Japanese translation source regardless of
        # whether its accepted evidence began with external JA or ASR-only.
        supporting = " / ".join(asr_texts) if asr_texts else None
        cues.append(HermesV2CueInput(
            cue_id=cue.cue_id,
            external_ja=primary,
            stt_ja=supporting,
            en=None,
            before_context=tuple(item.text for item in master.cues[max(0, index - 4):index]),
            after_context=tuple(item.text for item in master.cues[index + 1:index + 5]),
        ))
    # Reuse the existing explicit audio-evidence flag so translation can ask
    # for bounded targeted ASR instead of silently guessing when needed.
    generation = "v2d-ja-master-v1:" + master.master_sha256
    if targeted_evidence_sha256 is not None:
        generation += ":targeted-" + targeted_evidence_sha256
    generation += "::aud1"
    package = StatefulSubtitlePackage(
        schema_version=STATEFUL_TRANSLATOR_SCHEMA_VERSION,
        dvd_id=master.review_set.dvd_id,
        generation_key=generation,
        claim_token=claim_token,
        cues=tuple(cues),
    )
    return bind_stateful_semantic_policy(bind_stateful_model_input_identity(package), semantic_policy)


def _native_prompt(query: str, package: StatefulSubtitlePackage, *, part_ids=None) -> bytes:
    # Reuse the existing zero-tool inline prompt builder and its exact size cap.
    from teddy_discovery_stage11_normal_mode import MAX_NATIVE_PROMPT_BYTES, native_prompt
    payload = native_prompt(query, package, part_ids=part_ids)
    if len(payload) > MAX_NATIVE_PROMPT_BYTES:
        raise V2DError("native translation prompt exceeds the established bound")
    return payload


def translate_ja_master(
    master: V2DMaster,
    *,
    invoke: Callable,
    hermes_settings: HermesExecutionSettings,
    staging_root: str | Path,
    claim_token: int,
    semantic_policy=DEFAULT_STATEFUL_SEMANTIC_POLICY,
    reuse_only: bool = False,
    targeted_evidence_by_cue: dict[str, tuple[str, ...]] | None = None,
    targeted_evidence_sha256: str | None = None,
) -> tuple[StatefulSubtitlePackage, StatefulSubtitleResult]:
    """Use existing whole-title translation then fixed-64 part fallback."""
    if type(hermes_settings) is not HermesExecutionSettings:
        raise V2DError("resolved Hermes profile settings are required")
    package = _build_translation_package(
        master, claim_token, semantic_policy,
        targeted_evidence_by_cue=targeted_evidence_by_cue,
        targeted_evidence_sha256=targeted_evidence_sha256,
    )
    root = _private_dir(staging_root)
    stage = _private_child(root, stateful_session_id_for_package(package), create=not reuse_only)
    result_path = stage / "stage11-semantic-result.json"
    result = None
    fallback_path = stage / "whole-title-fallback.json"
    fallback_record = _wire({"policy": "EXISTING_FIXED_64", "source_sha256": master.source_fingerprint,
                             "master_sha256": master.master_sha256, "user_intervention": 0})
    if reuse_only:
        if fallback_path.exists() or fallback_path.is_symlink():
            if fallback_path.is_symlink() or fallback_path.read_bytes() != fallback_record:
                raise V2DError("fixed-part fallback record is invalid")
        elif not stage.exists():
            raise V2DError("translation resume directory is missing")
    else:
        if fallback_path.exists() or fallback_path.is_symlink():
            raise V2DError("translation fallback record already exists")
    if not (reuse_only and fallback_path.exists()):
        query = build_stateful_whole_title_query(package)
        try:
            prompt = _native_prompt(query, package)
        except V2DError:
            prompt = b""
        if prompt:
            try:
                result = invoke(prompt, stage, "whole-title",
                                lambda raw: parse_stateful_result(raw, package),
                                hermes_settings=hermes_settings, reuse_only=reuse_only)
            except Stage11ControllerError:
                if reuse_only and (not fallback_path.exists() or fallback_path.read_bytes() != fallback_record):
                    raise V2DError("whole-title resume lacks its fixed-part fallback record")
                if not reuse_only:
                    _atomic_private_write(fallback_path, fallback_record)
        else:
            if reuse_only and (not fallback_path.exists() or fallback_path.read_bytes() != fallback_record):
                raise V2DError("oversized whole-title resume lacks its fixed-part fallback record")
            if not reuse_only:
                _atomic_private_write(fallback_path, fallback_record)
    if result is not None:
        if any(not isinstance(cue, StatefulCueOutput) for cue in result.cues):
            raise V2DError("translation omitted the existing audio-evidence decision field")
        raw = serialize_stateful_result(result)
        if result_path.exists() or result_path.is_symlink():
            if reuse_only and not result_path.is_symlink() and result_path.read_bytes() == raw:
                reused = parse_stateful_result(raw, package)
                if any(not isinstance(cue, StatefulCueOutput) for cue in reused.cues):
                    raise V2DError("resumed translation omitted the audio-evidence decision field")
                return package, reused
            raise V2DError("translation result collision")
        if reuse_only:
            # The existing executor has just returned output only after its
            # stored prompt, execution receipt, settings, hashes and validator
            # passed. Materialize that verified result as the missing local
            # cache with the translator's existing exclusive private writer.
            # Any pre-existing path, including a symlink, is still rejected.
            reused = parse_stateful_result(raw, package)
            if any(not isinstance(cue, StatefulCueOutput) for cue in reused.cues):
                raise V2DError("resumed translation omitted the audio-evidence decision field")
            _atomic_private_write(result_path, raw)
            return package, reused
        _atomic_private_write(result_path, raw)
        return package, result
    model_input = serialize_stateful_model_input(package)
    plan = build_stateful_part_plan(package, model_input, semantic_policy=semantic_policy)
    parts = []
    for expected in plan.parts:
        part_dir = _private_child(stage, "part-stage-" + str(expected.part_index).zfill(4), create=not reuse_only)
        query = build_stateful_part_query(package, model_input, expected.part_index, semantic_policy=semantic_policy)
        prompt = _native_prompt(query, package, part_ids=expected.cue_ids)
        validator = lambda raw, expected=expected: parse_stateful_part(raw, expected, plan)
        part = invoke(prompt, part_dir, "part-" + str(expected.part_index).zfill(4), validator,
                      hermes_settings=hermes_settings, reuse_only=reuse_only)
        part_raw = serialize_stateful_part(part)
        canonical_path = stage / expected.canonical_filename
        if canonical_path.exists() or canonical_path.is_symlink():
            if reuse_only and not canonical_path.is_symlink() and canonical_path.read_bytes() == part_raw:
                parts.append(part)
                continue
            raise V2DError("canonical translation part collision")
        if reuse_only:
            raise V2DError("canonical translation part is missing during resume")
        _atomic_private_write(canonical_path, part_raw)
        parts.append(part)
    if reuse_only and result_path.exists():
        final = parse_stateful_result(result_path.read_bytes(), package)
        expected_cues = tuple(cue for part in parts for cue in part.cues)
        if final.cues != expected_cues:
            raise V2DError("resumed final translation differs from verified parts")
        if any(not isinstance(cue, StatefulCueOutput) for cue in final.cues):
            raise V2DError("translation omitted the existing audio-evidence decision field")
        return package, final
    if reuse_only:
        # The existing assembler writes the exact canonical final result.
        final = assemble_stateful_result(stage, package, plan)
        return package, final
    final = assemble_stateful_result(stage, package, plan)
    if any(not isinstance(cue, StatefulCueOutput) for cue in final.cues):
        raise V2DError("translation omitted the existing audio-evidence decision field")
    return package, final


def build_v2d_review_request(master: V2DMaster, package: StatefulSubtitlePackage,
                             first_pass: StatefulSubtitleResult) -> QualityReviewRequest:
    """Bind review inputs to this JA Master, translation package and result."""
    master = _validate_master(master)
    validated = validate_stateful_result(first_pass, package)
    if package.dvd_id != master.review_set.dvd_id or len(master.cues) != len(package.cues):
        raise V2DError("translation package is detached from JA Master")
    if tuple(cue.cue_id for cue in package.cues) != tuple(cue.cue_id for cue in master.cues):
        raise V2DError("translation cue identity/order differs from JA Master")
    member_by_key = {member.source_reference.key: member
                     for group in master.utterance_plan.groups for member in group.members}
    review_cues = []
    for index, (master_cue, output) in enumerate(zip(master.cues, validated.cues, strict=True)):
        asr_texts = [member_by_key[ref.key].text for ref in master_cue.source_references
                     if ref.source == "asr_segment"]
        supporting = " / ".join(asr_texts) if asr_texts else None
        before = tuple(
            " / ".join(member_by_key[ref.key].text for ref in prior.source_references
                       if ref.source == "asr_segment")
            for prior in master.cues[max(0, index - 2):index]
            if any(ref.source == "asr_segment" for ref in prior.source_references)
        )
        after = tuple(
            " / ".join(member_by_key[ref.key].text for ref in following.source_references
                       if ref.source == "asr_segment")
            for following in master.cues[index + 1:index + 3]
            if any(ref.source == "asr_segment" for ref in following.source_references)
        )
        raw_context = (before + after)[:4]
        first_ja = getattr(output, "repaired_ja", None)
        first_ko = getattr(output, "ko", None)
        if first_ko is None or getattr(output, "absorbed_into", None) is not None:
            raise V2DHold("FIRST_PASS_REQUIRES_UNSUPPORTED_ABSORPTION_OR_AUDIO_EVIDENCE")
        review_cues.append(QualityReviewInputCue(
            cue_id=master_cue.cue_id,
            source_index=index,
            external_ja=master_cue.text,
            accepted_stt_ja=supporting,
            first_pass_repaired_ja=first_ja,
            first_pass_ko=first_ko,
            # The legacy request contract requires a source-quality field.
            # The V2-D prompt explicitly marks this as a neutral compatibility
            # placeholder; it is not presented as a classifier result.
            source_quality_action="KEEP",
            source_quality_reason="no_quality_objection",
            raw_asr_context=raw_context,
        ))
    request = QualityReviewRequest(
        schema_version=2,
        package_sha256=_sha(serialize_stateful_package(package)),
        first_pass_sha256=_sha(serialize_stateful_result(validated)),
        source_sha256=master.master_sha256,
        source_translation_session_id=validated.session_id,
        cues=tuple(review_cues),
    )
    serialize_review_request(request)
    return request


def _review_source_manifest(master: V2DMaster) -> list[dict[str, object]]:
    return [{
        "cue_id": cue.cue_id,
        "group_id": cue.group_id,
        "speaker_status": cue.speaker_status,
        "speaker_evidence_ids": list(cue.speaker_evidence_ids),
        "source_references": [{
            "source_key": ref.key,
            "source_kind": ref.source,
            "source_index": ref.source_index,
            "sha256": ref.source_sha256,
            "locator_sha256": _sha(ref.source_locator.encode("utf-8")),
            "original_interval_ms": [ref.original_start_ms, ref.original_end_ms],
            "aligned_interval_ms": [_fraction(ref.aligned_start_ms), _fraction(ref.aligned_end_ms)],
        } for ref in cue.source_references],
    } for cue in master.cues]


def _review_prompt(request: QualityReviewRequest, master: V2DMaster,
                   *, target_cue_ids: tuple[str, ...] | None) -> bytes:
    from teddy_discovery_stateful_quality_review_runner import QUALITY_REVIEW_QUERY
    query = QUALITY_REVIEW_QUERY.replace(
        "Review EVERY cue in source order, including source-quality KEEP.",
        "Review every Japanese Master cue in source order, including non-filtering KEEP hints.",
    ).replace("external JA", "Japanese Master").replace("External JA", "Japanese Master")
    if target_cue_ids is not None:
        query = query.replace(
            "Review EVERY cue in source order, including source-quality KEEP.",
            "Read every cue for full-title context; adjudicate only the caller target cue IDs.",
        ).replace(
            "Return exactly the same cue IDs, count and order;",
            "Return exactly the caller target cue IDs, count and order;",
        )
        query += "\nV2D_TARGET_ONLY: Preserve every non-target first-pass value. Targets in order: " + json.dumps(target_cue_ids)
    payload = {
        "request": json.loads(serialize_review_request(request)),
        "request_sha256": review_request_sha256(request),
        "ja_master_source_manifest": _review_source_manifest(master),
        "target_cue_ids": None if target_cue_ids is None else list(target_cue_ids),
        "source_quality_field_note": "Legacy compatibility field only; KEEP/no_quality_objection is a neutral placeholder, not a classifier verdict.",
    }
    prompt = (query + "\nV2D_SOURCE_BOUND_INPUT=" + _wire(payload).decode("utf-8")).encode("utf-8")
    if len(prompt) > V2D_MAX_PROMPT_BYTES:
        raise V2DError("review prompt exceeds the existing native prompt bound")
    return prompt


@dataclass(frozen=True)
class V2DReviewOutcome:
    request: QualityReviewRequest
    triage: QualityReviewResult
    final: QualityReviewResult
    triage_sha256: str
    final_sha256: str
    targeted_cue_ids: tuple[str, ...]


def run_targeted_review(
    master: V2DMaster,
    package: StatefulSubtitlePackage,
    first_pass: StatefulSubtitleResult,
    *,
    invoke: Callable,
    hermes_settings: HermesExecutionSettings,
    staging_root: str | Path,
    reuse_only: bool = False,
) -> V2DReviewOutcome:
    """Run existing full-title triage, then existing bounded suspect review."""
    if type(hermes_settings) is not HermesExecutionSettings:
        raise V2DError("resolved Hermes profile settings are required")
    master = _validate_master(master)
    request = build_v2d_review_request(master, package, first_pass)
    root = _private_dir(staging_root)
    request_sha = review_request_sha256(request)
    request_dir = _private_child(root, request_sha, create=not reuse_only)
    triage_dir = _private_child(request_dir, "triage", create=not reuse_only)
    triage_id = str(uuid.uuid5(V2D_SESSION_NAMESPACE, request_sha + ":triage"))
    triage_prompt = _review_prompt(request, master, target_cue_ids=None)
    triage = invoke(
        triage_prompt, triage_dir, "v2d-triage",
        lambda raw: parse_review_result(raw, request),
        hermes_settings=hermes_settings, reuse_only=reuse_only,
    )
    if type(triage) is not QualityReviewResult:
        raise V2DError("triage executor returned an invalid review result")
    triage = bind_review_execution_provenance(triage, request, triage_id)
    triage_raw = serialize_review_result(triage, request)
    target_ids = select_suspect_cue_ids(request, triage)
    if not target_ids:
        final = triage
    else:
        final_dir = _private_child(request_dir, "targeted-final", create=not reuse_only)
        final_id = str(uuid.uuid5(V2D_SESSION_NAMESPACE, request_sha + ":targeted-final"))
        final_prompt = _review_prompt(request, master, target_cue_ids=target_ids)
        target_result = invoke(
            final_prompt, final_dir, "v2d-targeted-final-review",
            lambda raw: parse_review_result(raw, request, target_cue_ids=target_ids),
            hermes_settings=hermes_settings, reuse_only=reuse_only,
        )
        if type(target_result) is not QualityReviewResult:
            raise V2DError("targeted review executor returned an invalid result")
        target_result = bind_review_execution_provenance(target_result, request, final_id)
        final = merge_target_review_result(request, target_ids, target_result)
        final = bind_review_execution_provenance(final, request, final_id)
    final_raw = serialize_review_result(final, request)
    return V2DReviewOutcome(request, triage, final, _sha(triage_raw), _sha(final_raw), target_ids)


def _materialized_cues(master: V2DMaster, first_pass: StatefulSubtitleResult,
                       review: V2DReviewOutcome) -> tuple[tuple[SubtitleCue, ...], tuple[SubtitleCue, ...]]:
    if len(master.cues) != len(first_pass.cues) or len(master.cues) != len(review.final.cues):
        raise V2DError("final materialization cue coverage differs")
    japanese, korean = [], []
    for master_cue, first, request_cue, review_cue in zip(
        master.cues, first_pass.cues, review.request.cues, review.final.cues, strict=True
    ):
        if master_cue.cue_id != first.cue_id or master_cue.cue_id != review_cue.cue_id:
            raise V2DError("final materialization cue identity differs")
        action = effective_review_action(request_cue, review_cue)
        if action == OMIT:
            continue
        if action == REPAIR:
            ja_text, ko_text = review_cue.replacement_ja, review_cue.replacement_ko
        else:  # KEEP and the existing AMBIGUOUS -> KEEP preservation rule.
            ja_text = master_cue.text
            ko_text = getattr(first, "ko", None)
        if not ja_text or not ko_text:
            raise V2DError("final review left an empty JA or KO cue")
        start_ms, end_ms = _round_ms(master_cue.start_ms), _round_ms(master_cue.end_ms)
        if end_ms <= start_ms:
            raise V2DError("final millisecond rounding produced a zero-length cue")
        japanese.append(SubtitleCue(start_ms, end_ms, ja_text))
        korean.append(SubtitleCue(start_ms, end_ms, ko_text))
    if not japanese or not korean:
        raise V2DHold("FINAL_OUTPUT_HAS_NO_CUES")
    return tuple(japanese), tuple(korean)


def _srt_bytes(cues: tuple[SubtitleCue, ...]) -> bytes:
    placeholder_sha = "0" * 64
    document = SubtitleDocument("srt", cues, placeholder_sha, 1)
    raw = serialize_srt(document)
    parsed = parse_subtitle_bytes(raw, "srt")
    if parsed.cues != cues:
        raise V2DError("serialized SRT failed round-trip structure validation")
    return raw


def _master_artifact_bytes(master: V2DMaster) -> bytes:
    return _wire({
        "schema_version": V2D_SCHEMA_VERSION,
        "dvd_id": master.review_set.dvd_id,
        "route": master.review_set.route,
        "source_snapshot": {
            "dvd_id": master.review_set.source_snapshot.dvd_id,
            "video_relative_sha256": _sha(master.review_set.source_snapshot.canonical_video_relative.encode()),
            "source_size": master.review_set.source_snapshot.source_size,
            "source_mtime_ns": master.review_set.source_snapshot.source_mtime_ns,
        },
        "source_fingerprint": master.source_fingerprint,
        "master_sha256": master.master_sha256,
        "targeted_evidence_sha256": master.targeted_evidence_sha256,
        "asr_sha256": master.review_set.asr_sha256,
        "external_ja_sha256": master.review_set.external_ja_sha256,
        "candidate_decisions": [[item.candidate_id, item.status, item.rationale]
                                for group in master.adjudication.groups for item in group.candidate_decisions],
        "source_decisions": [[item.source_key, item.status, item.rationale]
                             for group in master.adjudication.groups for item in group.source_decisions],
        "cues": [{
            "cue_id": cue.cue_id,
            "group_id": cue.group_id,
            "japanese_text": cue.text,
            "source_references": [{
                "source_key": ref.key, "source_kind": ref.source,
                "source_index": ref.source_index, "source_sha256": ref.source_sha256,
                "locator_sha256": _sha(ref.source_locator.encode()),
                "original_start_ms": ref.original_start_ms,
                "original_end_ms": ref.original_end_ms,
                "aligned_start_ms": _fraction(ref.aligned_start_ms),
                "aligned_end_ms": _fraction(ref.aligned_end_ms),
            } for ref in cue.source_references],
            "start_ms": _fraction(cue.start_ms), "end_ms": _fraction(cue.end_ms),
            "speaker_status": cue.speaker_status,
            "speaker_evidence_ids": list(cue.speaker_evidence_ids),
        } for cue in master.cues],
    })


def _write_exclusive(path: Path, raw: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except FileExistsError as error:
        raise V2DError("private V2-D output already exists") from error
    except OSError as error:
        raise V2DError("private V2-D output could not be written") from error


@dataclass(frozen=True)
class V2DPipelineResult:
    state: str
    reason_code: str | None
    master: V2DMaster | None = field(repr=False)
    package: StatefulSubtitlePackage | None = field(repr=False)
    translation: StatefulSubtitleResult | None = field(repr=False)
    review: V2DReviewOutcome | None = field(repr=False)
    output_hashes: tuple[tuple[str, str], ...] = ()


def run_v2d_pipeline(
    plan: UtteranceReviewPlan,
    *,
    invoke: Callable,
    hermes_settings: HermesExecutionSettings,
    staging_root: str | Path,
    output_directory: str | Path,
    claim_token: int,
    reuse_only: bool = False,
    semantic_policy=DEFAULT_STATEFUL_SEMANTIC_POLICY,
    targeted_runner: Callable | None = None,
) -> V2DPipelineResult:
    """Connected offline/live-injectable V2-D path; never bypasses validators."""
    try:
        invoke, executor_owner = _stage_bound_native_invoke(invoke, hermes_settings)
        verified_before = len(getattr(executor_owner, "_verified_attempts", ()))
        plan = validate_utterance_review_plan(plan)
        output = _private_dir(output_directory)
        collisions = [name for name in V2D_OUTPUT_NAMES if (output / name).exists() or (output / name).is_symlink()]
        if collisions:
            raise V2DError("V2-D output collision")
        adjudication = adjudicate_ja_master(
            plan, invoke=invoke, hermes_settings=hermes_settings,
            staging_root=staging_root, claim_token=claim_token, reuse_only=reuse_only,
        )
        master = materialize_ja_master(plan, adjudication)
        package, translated = translate_ja_master(
            master, invoke=invoke, hermes_settings=hermes_settings,
            staging_root=staging_root, claim_token=claim_token,
            semantic_policy=semantic_policy, reuse_only=reuse_only,
        )
        targeted_evidence = None
        if any(isinstance(cue, StatefulCueOutput) and cue.needs_audio_evidence for cue in translated.cues):
            targeted_requests = _build_targeted_requests(master, translated)
            evidence_items = []
            for targeted_request in targeted_requests:
                if type(targeted_request) is _V2DTargetedRequest:
                    evidence_items.append(_load_or_run_targeted_evidence(
                        targeted_request, master=master, targeted_runner=targeted_runner,
                        staging_root=staging_root, reuse_only=reuse_only,
                    ))
                elif type(targeted_request) is _V2DExternalTargetedRequest:
                    evidence_items.append(_load_or_run_external_targeted_evidence(
                        targeted_request, master=master, targeted_runner=targeted_runner,
                        staging_root=staging_root, reuse_only=reuse_only,
                    ))
                else:
                    raise V2DHold("TARGETED_ASR_REQUEST_TYPE_UNSUPPORTED")
            targeted_evidence = _combine_targeted_evidence(tuple(evidence_items))
            adjudication = _readjudicate_targeted_groups(
                plan, adjudication, targeted_evidence,
                invoke=invoke, hermes_settings=hermes_settings,
                staging_root=staging_root, claim_token=claim_token,
                reuse_only=reuse_only,
            )
            master = materialize_ja_master(
                plan, adjudication,
                targeted_evidence_sha256=targeted_evidence.linkage_sha256,
            )
            translation_evidence = _targeted_translation_evidence(
                master, targeted_evidence,
            )
            package, translated = translate_ja_master(
                master, invoke=invoke, hermes_settings=hermes_settings,
                staging_root=staging_root, claim_token=claim_token,
                semantic_policy=semantic_policy, reuse_only=reuse_only,
                targeted_evidence_by_cue=translation_evidence,
                targeted_evidence_sha256=(targeted_evidence.linkage_sha256
                                          if translation_evidence else None),
            )
            if any(isinstance(cue, StatefulCueOutput) and cue.needs_audio_evidence
                   for cue in translated.cues):
                raise V2DHold("TARGETED_ASR_STILL_REQUIRED_AFTER_ONE_SUPPLEMENTAL_PASS")
        review = run_targeted_review(
            master, package, translated, invoke=invoke,
            hermes_settings=hermes_settings, staging_root=staging_root,
            reuse_only=reuse_only,
        )
        ja_cues, ko_cues = _materialized_cues(master, translated, review)
        ja_raw, ko_generated = _srt_bytes(ja_cues), generate_korean_srt(ko_cues)
        if ko_generated.payload is None or ko_generated.cue_count != len(ko_cues):
            raise V2DError("Korean SRT generator returned no complete artifact")
        ko_raw = ko_generated.payload
        if parse_subtitle_bytes(ko_raw, "srt").cues != ko_cues:
            raise V2DError("Korean SRT failed round-trip validation")
        master_raw = _master_artifact_bytes(master)
        settings_evidence = hermes_settings.evidence()
        native_attempts = getattr(executor_owner, "_verified_attempts", ())
        verified_attempts = []
        for item in tuple(native_attempts)[verified_before:]:
            # NativeNormalFirstPass already verified these receipt fields.
            # Copy only digests and fixed status values into the private proof;
            # do not include runtime IDs, prompts, output, or error messages.
            verified_attempts.append({
                "label": item.get("label"),
                "attempt": item.get("attempt"),
                "receipt_sha256": item.get("receipt_sha256"),
                "prompt_sha256": item.get("prompt_sha256"),
                "stdout_sha256": item.get("stdout_sha256"),
                "stderr_sha256": item.get("stderr_sha256"),
                "runtime_session_id_sha256": item.get("runtime_session_id_sha256"),
                "returncode": item.get("returncode"),
                "timeout_observed": item.get("timeout_reason") is not None,
                "tools_count": item.get("tools_count"),
                "hermes_execution_settings": item.get("hermes_execution_settings"),
            })
        proof_raw = _wire({
            "schema_version": V2D_SCHEMA_VERSION,
            "dvd_id": master.review_set.dvd_id,
            "state": "CLEAN_SRT_READY",
            "source_fingerprint": master.source_fingerprint,
            "master_sha256": master.master_sha256,
            "targeted_asr_artifact_sha256": (None if targeted_evidence is None
                                               else targeted_evidence.artifact_sha256),
            "targeted_asr_linkage_sha256": (None if targeted_evidence is None
                                              else targeted_evidence.linkage_sha256),
            "targeted_readjudicated_group_count": (0 if targeted_evidence is None
                                                   else len(targeted_evidence.group_payloads)),
            "asr_sha256": master.review_set.asr_sha256,
            "external_ja_sha256": master.review_set.external_ja_sha256,
            "translation_package_sha256": _sha(serialize_stateful_package(package)),
            "translation_result_sha256": _sha(serialize_stateful_result(translated)),
            "translation_session_id": translated.session_id,
            "review_request_sha256": review_request_sha256(review.request),
            "triage_result_sha256": review.triage_sha256,
            "final_review_result_sha256": review.final_sha256,
            "review_execution_session_id": review.final.review_execution_session_id,
            "targeted_review_cue_count": len(review.targeted_cue_ids),
            "hermes_settings_resolved_for_unstarted_stages": settings_evidence,
            "verified_native_attempts": verified_attempts,
            "outputs": {
                V2D_OUTPUT_NAMES[0]: _sha(master_raw),
                V2D_OUTPUT_NAMES[1]: _sha(ja_raw),
                V2D_OUTPUT_NAMES[2]: _sha(ko_raw),
            },
        })
        payloads = (master_raw, ja_raw, ko_raw, proof_raw)
        # Check all names again before the first exclusive write.
        if any((output / name).exists() or (output / name).is_symlink() for name in V2D_OUTPUT_NAMES):
            raise V2DError("V2-D output collision")
        for name, raw in zip(V2D_OUTPUT_NAMES, payloads, strict=True):
            _write_exclusive(output / name, raw)
        hashes = tuple((name, _sha(raw)) for name, raw in zip(V2D_OUTPUT_NAMES, payloads, strict=True))
        return V2DPipelineResult("CLEAN_SRT_READY", None, master, package, translated, review, hashes)
    except V2DHold as hold:
        return V2DPipelineResult("HOLD", str(hold), None, None, None, None)


__all__ = [
    "CandidateDecision", "GroupAdjudication", "MasterOutputProposal", "SourceDecision",
    "SourceSpan", "V2DAdjudication", "V2DError", "V2DHold", "V2DMaster",
    "V2DPipelineResult", "adjudicate_ja_master", "build_v2d_review_request",
    "build_v2d_targeted_asr_adapter", "materialize_ja_master", "run_targeted_review", "run_v2d_pipeline",
    "translate_ja_master", "validate_adjudication",
]
