"""Isolated V2-D connection from source-bound JA Master to private SRTs.

The module reuses the promoted V2-B/V2-C evidence contracts, Stage11's
stateful translator, NativeNormalFirstPass receipt boundary, and the existing
quality-review result/action validators.  It never owns source timing: timing
is derived from the selected source spans and rounded once, at SRT rendering.
No operation in this module starts a model by itself; model calls are supplied
through the existing ``NativeNormalFirstPass.invoke``-compatible callback.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher
from fractions import Fraction
import contextvars
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import time
from types import SimpleNamespace
import uuid
from contextlib import nullcontext
from typing import Callable

from teddy_discovery_alignment import normalize_japanese_for_matching
from teddy_discovery_asr_source_quality import (
    ASR_SOURCE_REASON_CONSECUTIVE_RUN,
    ASR_SOURCE_REASON_DOCUMENT_RECURRENCE,
    ASRSourceQualityHint,
    classify_asr_result_source_quality,
)
from teddy_discovery_stage11_ja_master import (
    DECISION_ACCEPTED,
    DECISION_REJECTED,
    DECISION_UNCERTAIN,
    EVIDENCE_SOURCE_SUPPLEMENTAL_ASR,
    JAMasterReviewSet,
    JAMasterSourceReference,
)
from teddy_discovery_stage11_utterance_groups import (
    ASRWordReference,
    SPEAKER_UNKNOWN,
    UTTERANCE_UNRESOLVED,
    UtteranceMember,
    UtteranceReviewGroup,
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
from teddy_discovery_asr import ASRResult, ASRRuntimeIdentity, ASRSegment, ASRWord
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


class V2DLimitStop(V2DError):
    """A configured per-title attempt or wall-time budget was exhausted."""


@dataclass(frozen=True)
class V2DExecutionLimits:
    """Explicit limits required for any Native-backed V2-D model execution."""

    max_hermes_attempts: int
    max_wall_seconds: int | float

    def __post_init__(self):
        if type(self.max_hermes_attempts) is not int or self.max_hermes_attempts < 1:
            raise V2DError("max_hermes_attempts must be a positive integer")
        if (type(self.max_wall_seconds) not in (int, float)
                or not math.isfinite(float(self.max_wall_seconds))
                or self.max_wall_seconds <= 0):
            raise V2DError("max_wall_seconds must be a positive finite number")


_ACTIVE_V2D_BUDGET = contextvars.ContextVar("stage11_v2d_budget", default=None)


class _V2DRunBudget:
    def __init__(self, limits: V2DExecutionLimits):
        if type(limits) is not V2DExecutionLimits:
            raise V2DError("explicit V2-D execution limits are required")
        self.limits = limits
        self.started = time.monotonic()
        self.hermes_attempts = 0
        self.targeted_asr_requests = 0

    def elapsed(self) -> float:
        return max(0.0, time.monotonic() - self.started)

    def remaining(self) -> float:
        return float(self.limits.max_wall_seconds) - self.elapsed()

    def require_time(self, seconds: int | float = 0, *, reason="WALL_TIME_LIMIT"):
        if (type(seconds) not in (int, float) or not math.isfinite(float(seconds))
                or seconds < 0 or self.remaining() < float(seconds)):
            raise V2DLimitStop(reason)

    def reserve_hermes(self, timeout_seconds: int | float):
        if self.hermes_attempts >= self.limits.max_hermes_attempts:
            raise V2DLimitStop("HERMES_ATTEMPT_LIMIT")
        self.require_time(timeout_seconds, reason="WALL_TIME_LIMIT_BEFORE_HERMES_ATTEMPT")
        self.hermes_attempts += 1

    def reserve_targeted_asr(self, timeout_seconds: int | float):
        self.require_time(timeout_seconds, reason="WALL_TIME_LIMIT_BEFORE_TARGETED_ASR")
        self.targeted_asr_requests += 1

    def evidence(self) -> dict[str, object]:
        return {
            "max_hermes_attempts": self.limits.max_hermes_attempts,
            "max_wall_seconds": self.limits.max_wall_seconds,
            "hermes_attempts_started": self.hermes_attempts,
            "targeted_asr_requests_started": self.targeted_asr_requests,
            "elapsed_seconds": round(self.elapsed(), 6),
        }


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


LIMITED_JSON_TRAILING_SUFFIX = "]}"
V2D_PRIVATE_PROVISIONAL_UNCERTAINTY_FILENAME = "v2d-private-provisional-uncertainty-v1.json"


def recover_limited_trailing_json(
    raw: bytes,
    label: str,
) -> tuple[object, dict[str, object] | None]:
    """Strict JSON parse first; only recover exact literal trailing ']}' after one complete object.

    Never edits any byte inside the JSON object body. Rejects truncation,
    multiple objects, markdown fences, or any suffix other than literal ']}'
    plus optional surrounding whitespace.
    """
    if type(raw) is not bytes or not 0 < len(raw) <= V2D_MAX_JSON_BYTES:
        raise V2DError(label + " exceeds the bounded JSON contract")
    try:
        return _load_json(raw, label), None
    except V2DError as strict_error:
        cause = strict_error.__cause__
        if not isinstance(cause, json.JSONDecodeError) or cause.msg != "Extra data":
            raise
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise V2DError(label + " is invalid JSON") from error
    stripped_lead = text.lstrip()
    start_idx = len(text) - len(stripped_lead)
    if not stripped_lead.startswith("{"):
        raise V2DError(label + " is invalid JSON")
    decoder = json.JSONDecoder(
        object_pairs_hook=_reject_duplicate_json,
        parse_constant=lambda value: (_ for _ in ()).throw(V2DError("nonfinite JSON number")),
    )
    try:
        _obj, end_idx = decoder.raw_decode(text, start_idx)
    except json.JSONDecodeError as error:
        raise V2DError(label + " is invalid JSON") from error
    remainder = text[end_idx:]
    if remainder.strip() != LIMITED_JSON_TRAILING_SUFFIX:
        raise V2DError(label + " is invalid JSON")
    isolated_bytes = text[start_idx:end_idx].encode("utf-8")
    # Re-parse isolated unchanged object bytes through the exact strict loader.
    data = _load_json(isolated_bytes, label)
    recovery_record = {
        "recovery_mode": "LIMITED_TRAILING_DELIMITERS_STRIPPED",
        "raw_sha256": _sha(raw),
        "derived_sha256": _sha(isolated_bytes),
        "removed_suffix": remainder,
        "isolated_char_start": start_idx,
        "isolated_char_end": end_idx,
        "raw_char_len": len(text),
    }
    return data, recovery_record


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


def _source_fingerprint(
    plan: UtteranceReviewPlan,
    *,
    exclude_group_ids: tuple[str, ...] = (),
    supplemental_groups: tuple[UtteranceReviewGroup, ...] = (),
) -> str:
    review = plan.review_set
    excluded = set(exclude_group_ids)
    effective_groups = tuple(
        g for g in plan.groups if g.group_id not in excluded
    ) + tuple(supplemental_groups)
    groups = []
    for group in effective_groups:
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
    if exclude_group_ids:
        identity["excluded_outside_span_group_ids"] = list(exclude_group_ids)
    return _sha(_wire(identity))


def _group_payload(
    plan: UtteranceReviewPlan,
    group,
    *,
    source_fingerprint: str | None = None,
) -> dict[str, object]:
    candidate_by_id = {item.candidate_id: item for item in plan.review_set.candidates}
    return {
        "schema_version": V2D_SCHEMA_VERSION,
        "dvd_id": plan.review_set.dvd_id,
        "source_fingerprint": _source_fingerprint(plan) if source_fingerprint is None else source_fingerprint,
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
    audio_evidence_needed: bool = False

    def __post_init__(self):
        _safe_text(self.group_id, "group id", max_chars=128)
        if type(self.candidate_decisions) is not tuple or type(self.source_decisions) is not tuple or type(self.outputs) is not tuple:
            raise V2DError("adjudication collections must be immutable tuples")
        if type(self.audio_evidence_needed) is not bool:
            raise V2DError("audio evidence need flag must be boolean")


@dataclass(frozen=True)
class V2DBatchEvidence:
    batch_id: str
    source_fingerprint: str
    group_ids: tuple[str, ...]
    input_sha256: str
    prompt_sha256: str
    native_receipt_sha256: tuple[str, ...] = ()

    def __post_init__(self):
        _digest(self.batch_id, "batch_id")
        _digest(self.source_fingerprint, "batch source_fingerprint")
        _digest(self.input_sha256, "batch input_sha256")
        _digest(self.prompt_sha256, "batch prompt_sha256")
        if type(self.group_ids) is not tuple or not self.group_ids or len(set(self.group_ids)) != len(self.group_ids):
            raise V2DError("batch group coverage is invalid")
        if type(self.native_receipt_sha256) is not tuple:
            raise V2DError("batch receipt list is invalid")
        for digest in self.native_receipt_sha256:
            _digest(digest, "batch native receipt")


@dataclass(frozen=True)
class V2DAdjudication:
    source_fingerprint: str
    groups: tuple[GroupAdjudication, ...]
    batch_evidence: tuple[V2DBatchEvidence, ...] = ()

    def __post_init__(self):
        _digest(self.source_fingerprint, "source_fingerprint")
        if type(self.groups) is not tuple or not self.groups:
            raise V2DError("adjudication groups are required")
        if type(self.batch_evidence) is not tuple or any(type(item) is not V2DBatchEvidence for item in self.batch_evidence):
            raise V2DError("adjudication batch evidence is invalid")


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
    outside_span_recovery_sha256: str | None = None
    excluded_outside_span_group_ids: tuple[str, ...] = ()
    supplemental_groups: tuple[UtteranceReviewGroup, ...] = field(default=(), repr=False)
    provisional_unresolved_group_ids: tuple[str, ...] = ()


OUTSIDE_SPAN_CANDIDATE_RATIONALE = "EXTERNAL_CUE_OUTSIDE_AFFINE_EVIDENCE_SPAN"
OUTSIDE_SPAN_DISPOSITION_BASELINE_SUPPORTED = "BASELINE_ASR_EXACT_MATCH_SUPPORTED"
OUTSIDE_SPAN_DISPOSITION_NEEDS_TARGETED_ASR = "REQUIRES_BOUNDED_TARGETED_ASR"
OUTSIDE_SPAN_OUTCOME_SPEECH_FOUND = "SPEECH_CANDIDATE_FOUND"
OUTSIDE_SPAN_OUTCOME_NO_SPEECH = "NO_DETECTED_SPEECH"
OUTSIDE_SPAN_OUTCOME_INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class OutsideSpanRecoveryLimits:
    """Explicit conservative bounds for outside-affine-span targeted ASR recovery."""

    pre_padding_ms: int = STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1.pre_padding_ms
    post_padding_ms: int = STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1.post_padding_ms
    merge_gap_ms: int = STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1.merge_gap_ms
    max_window_ms: int = 30_000
    max_total_audio_ms: int = 60_000

    def __post_init__(self):
        for name in ("pre_padding_ms", "post_padding_ms", "merge_gap_ms"):
            val = getattr(self, name)
            if type(val) is not int or val < 0:
                raise V2DError(name + " must be a nonnegative integer")
        if type(self.max_window_ms) is not int or self.max_window_ms <= 0:
            raise V2DError("max_window_ms must be a positive integer")
        if type(self.max_total_audio_ms) is not int or self.max_total_audio_ms < self.max_window_ms:
            raise V2DError("max_total_audio_ms must be >= max_window_ms")


@dataclass(frozen=True)
class OutsideSpanExternalCueAssessment:
    group_id: str
    source_reference: JAMasterSourceReference = field(repr=False)
    external_text: str = field(repr=False)
    hypothesis_start_ms: Fraction
    hypothesis_end_ms: Fraction
    disposition: str
    supporting_baseline_source_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class OutsideSpanHypothesisWindow:
    window_id: str
    start_ms: int
    end_ms: int
    external_source_keys: tuple[str, ...]
    hypothesis_intervals_ms: tuple[tuple[str, Fraction, Fraction], ...]


@dataclass(frozen=True)
class OutsideSpanRecoveryPlan:
    source_snapshot: object = field(repr=False)
    baseline_asr_sha256: str
    external_ja_sha256: str
    limits: OutsideSpanRecoveryLimits
    excluded_group_ids: tuple[str, ...]
    assessments: tuple[OutsideSpanExternalCueAssessment, ...]
    windows: tuple[OutsideSpanHypothesisWindow, ...]
    total_audio_ms: int
    exceeds_budget: bool
    budget_violation_reason: str | None = None


@dataclass(frozen=True)
class RecoveredSupplementalASRSegment:
    source_id: str
    window_id: str
    window_start_ms: int
    window_end_ms: int
    start_ms: int
    end_ms: int
    text: str = field(repr=False)
    words: tuple[ASRWord, ...] = field(default=(), repr=False)
    trigger_external_source_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class OutsideSpanWindowOutcome:
    window_id: str
    start_ms: int
    end_ms: int
    external_source_keys: tuple[str, ...]
    outcome: str
    segments: tuple[RecoveredSupplementalASRSegment, ...] = ()


@dataclass(frozen=True)
class OutsideSpanRecoveryResult:
    plan: OutsideSpanRecoveryPlan = field(repr=False)
    runtime_identity: ASRRuntimeIdentity | None
    engine_version: str | None
    verified_container_duration_ms: int | None
    artifact_sha256: str
    window_outcomes: tuple[OutsideSpanWindowOutcome, ...]
    diagnostic_only: bool = False


def split_outside_span_groups(
    plan: UtteranceReviewPlan,
) -> tuple[tuple[UtteranceReviewGroup, ...], tuple[UtteranceReviewGroup, ...]]:
    """Separate outside-affine-span untimed external-JA groups from active groups."""
    plan = validate_utterance_review_plan(plan)
    review = plan.review_set
    if review.route != ROUTE_EXTERNAL_ALIGNMENT_ACCEPTED or review._source_alignment is None:
        return plan.groups, ()
    cand_by_id = {c.candidate_id: c for c in review.candidates}
    active, outside = [], []
    for group in plan.groups:
        is_outside = (
            group.source_cardinality == "EXTERNAL_JA_ONLY"
            and bool(group.members)
            and all(
                m.source_reference.source == "external_ja"
                and m.source_reference.aligned_start_ms is None
                and m.source_reference.aligned_end_ms is None
                for m in group.members
            )
            and bool(group.candidate_ids)
            and all(
                OUTSIDE_SPAN_CANDIDATE_RATIONALE in cand_by_id[cid].rationale_codes
                for cid in group.candidate_ids
            )
        )
        if is_outside:
            outside.append(group)
        else:
            active.append(group)
    return tuple(active), tuple(outside)


def _find_baseline_comparison_candidates(
    external_text: str,
    hyp_start: Fraction,
    hyp_end: Fraction,
    tolerance_ms: Fraction,
    baseline_asr: ASRResult,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Locate comparison candidates by interval/lexical overlap; skip recovery ONLY on exact normalized equality.

    Lexical similarity is used strictly to identify comparison candidates, never as a
    conclusive speech-coverage cutoff.  Any non-exact match remains eligible for
    bounded targeted ASR recovery so short/partial utterances are not dropped.
    """
    ext_norm = normalize_japanese_for_matching(external_text)
    exact_matches: list[str] = []
    comparison_candidates: list[str] = []
    for idx, seg in enumerate(baseline_asr.segments):
        if Fraction(seg.end_ms) < hyp_start - tolerance_ms or Fraction(seg.start_ms) > hyp_end + tolerance_ms:
            continue
        key = EVIDENCE_SOURCE_ASR_SEGMENT + ":" + stable_cue_id(EVIDENCE_SOURCE_ASR_SEGMENT, idx)
        asr_norm = normalize_japanese_for_matching(seg.text)
        if ext_norm and asr_norm and ext_norm == asr_norm:
            exact_matches.append(key)
            comparison_candidates.append(key)
        elif ext_norm and asr_norm and SequenceMatcher(None, ext_norm, asr_norm, autojunk=False).find_longest_match(
            0, len(ext_norm), 0, len(asr_norm),
        ).size > 0:
            comparison_candidates.append(key)
    return tuple(exact_matches), tuple(comparison_candidates)


def _validate_recovered_word_timings(
    words: tuple[ASRWord, ...],
    *,
    seg_start_ms: int,
    seg_end_ms: int,
    win_start_ms: int,
    win_end_ms: int,
    error_cls: type[Exception] = V2DHold,
) -> None:
    if not (win_start_ms <= seg_start_ms < seg_end_ms <= win_end_ms):
        raise error_cls("OUTSIDE_SPAN_RECOVERY_SEGMENT_OUTSIDE_WINDOW")
    prev_end = seg_start_ms
    for word in words:
        if (type(word.start_ms) is not int or type(word.end_ms) is not int
                or not (win_start_ms <= seg_start_ms <= word.start_ms < word.end_ms <= seg_end_ms <= win_end_ms)
                or word.start_ms < prev_end):
            raise error_cls("OUTSIDE_SPAN_RECOVERY_WORD_TIMING_INVALID")
        prev_end = word.end_ms


def plan_outside_span_recovery(
    plan: UtteranceReviewPlan,
    *,
    limits: OutsideSpanRecoveryLimits = OutsideSpanRecoveryLimits(),
) -> OutsideSpanRecoveryPlan:
    """Assess outside-affine-span untimed external JA cues and plan bounded hypothesis windows."""
    if type(limits) is not OutsideSpanRecoveryLimits:
        raise V2DError("OutsideSpanRecoveryLimits is required")
    plan = validate_utterance_review_plan(plan)
    review = plan.review_set
    _, outside_groups = split_outside_span_groups(plan)
    if not outside_groups:
        return OutsideSpanRecoveryPlan(
            source_snapshot=review.source_snapshot,
            baseline_asr_sha256=review.asr_sha256,
            external_ja_sha256=review.external_ja_sha256 or ("0" * 64),
            limits=limits,
            excluded_group_ids=(),
            assessments=(),
            windows=(),
            total_audio_ms=0,
            exceeds_budget=False,
        )
    alignment = review._source_alignment
    if review.route != ROUTE_EXTERNAL_ALIGNMENT_ACCEPTED or alignment is None or review.external_ja_sha256 is None:
        raise V2DHold("OUTSIDE_SPAN_ALIGNMENT_UNAVAILABLE")
    scale = Fraction.from_float(alignment.scale)
    intercept = Fraction.from_float(alignment.intercept_ms)
    tolerance_ms = Fraction(int(alignment.residual_threshold_ms))
    baseline_asr = review._source_bundle.asr_result

    assessments: list[OutsideSpanExternalCueAssessment] = []
    raw_windows: list[tuple[int, int, str, Fraction, Fraction]] = []
    for group in outside_groups:
        for member in group.members:
            ref = member.source_reference
            hyp_start = scale * ref.original_start_ms + intercept
            hyp_end = scale * ref.original_end_ms + intercept
            if hyp_end <= hyp_start:
                raise V2DHold("OUTSIDE_SPAN_HYPOTHESIS_INTERVAL_INVALID")
            exact_matches, comparison_candidates = _find_baseline_comparison_candidates(
                member.text, hyp_start, hyp_end, tolerance_ms, baseline_asr,
            )
            if exact_matches:
                assessments.append(OutsideSpanExternalCueAssessment(
                    group_id=group.group_id,
                    source_reference=ref,
                    external_text=member.text,
                    hypothesis_start_ms=hyp_start,
                    hypothesis_end_ms=hyp_end,
                    disposition=OUTSIDE_SPAN_DISPOSITION_BASELINE_SUPPORTED,
                    supporting_baseline_source_keys=exact_matches,
                ))
            else:
                assessments.append(OutsideSpanExternalCueAssessment(
                    group_id=group.group_id,
                    source_reference=ref,
                    external_text=member.text,
                    hypothesis_start_ms=hyp_start,
                    hypothesis_end_ms=hyp_end,
                    disposition=OUTSIDE_SPAN_DISPOSITION_NEEDS_TARGETED_ASR,
                    supporting_baseline_source_keys=comparison_candidates,
                ))
                w_start = max(0, math.floor(hyp_start) - limits.pre_padding_ms)
                w_end = math.ceil(hyp_end) + limits.post_padding_ms
                raw_windows.append((w_start, w_end, ref.key, hyp_start, hyp_end))

    raw_windows.sort(key=lambda item: (item[0], item[1], item[2]))
    merged: list[OutsideSpanHypothesisWindow] = []
    exceeds_budget = False
    budget_reason = None
    for w_start, w_end, key, hyp_start, hyp_end in raw_windows:
        if w_end - w_start > limits.max_window_ms:
            exceeds_budget = True
            budget_reason = "SINGLE_WINDOW_EXCEEDS_MAX_WINDOW_MS"
        if (merged
                and w_start - merged[-1].end_ms <= limits.merge_gap_ms
                and max(merged[-1].end_ms, w_end) - merged[-1].start_ms <= limits.max_window_ms):
            prev = merged[-1]
            merged[-1] = OutsideSpanHypothesisWindow(
                window_id=prev.window_id,
                start_ms=prev.start_ms,
                end_ms=max(prev.end_ms, w_end),
                external_source_keys=prev.external_source_keys + (key,),
                hypothesis_intervals_ms=prev.hypothesis_intervals_ms + ((key, hyp_start, hyp_end),),
            )
        else:
            merged.append(OutsideSpanHypothesisWindow(
                window_id=f"outside-span-window-{len(merged) + 1:06d}",
                start_ms=w_start,
                end_ms=w_end,
                external_source_keys=(key,),
                hypothesis_intervals_ms=((key, hyp_start, hyp_end),),
            ))
    total_audio_ms = sum(w.end_ms - w.start_ms for w in merged)
    if total_audio_ms > limits.max_total_audio_ms:
        exceeds_budget = True
        budget_reason = budget_reason or "TOTAL_AUDIO_EXCEEDS_MAX_TOTAL_AUDIO_MS"
    return OutsideSpanRecoveryPlan(
        source_snapshot=review.source_snapshot,
        baseline_asr_sha256=review.asr_sha256,
        external_ja_sha256=review.external_ja_sha256,
        limits=limits,
        excluded_group_ids=tuple(g.group_id for g in outside_groups),
        assessments=tuple(assessments),
        windows=tuple(merged),
        total_audio_ms=total_audio_ms,
        exceeds_budget=exceeds_budget,
        budget_violation_reason=budget_reason,
    )


def _common_affix_length(left: str, right: str) -> int:
    prefix = 0
    limit = min(len(left), len(right))
    while prefix < limit and left[prefix] == right[prefix]:
        prefix += 1
    suffix = 0
    while suffix < limit and left[len(left) - 1 - suffix] == right[len(right) - 1 - suffix]:
        suffix += 1
    return max(prefix, suffix)


def _match_supplemental_baseline_overlap(
    seg_start_ms: int,
    seg_end_ms: int,
    seg_text: str,
    baseline_segments: tuple[ASRSegment, ...],
) -> dict[str, object] | None:
    """Identify when a recovered segment matches a baseline ASR utterance on time and wording."""
    seg_norm = normalize_japanese_for_matching(seg_text)
    if not seg_norm or seg_end_ms <= seg_start_ms:
        return None
    seg_dur = seg_end_ms - seg_start_ms
    best: dict[str, object] | None = None
    best_score = -1.0
    for base_index, base_seg in enumerate(baseline_segments):
        if base_seg.end_ms < seg_start_ms or base_seg.start_ms > seg_end_ms:
            continue
        base_norm = normalize_japanese_for_matching(base_seg.text)
        if not base_norm:
            continue
        ov_ms = max(0, min(seg_end_ms, base_seg.end_ms) - max(seg_start_ms, base_seg.start_ms))
        base_dur = max(1, base_seg.end_ms - base_seg.start_ms)
        containment = ov_ms / min(seg_dur, base_dur)
        end_delta_ms = abs(seg_end_ms - base_seg.end_ms)
        if seg_norm == base_norm:
            return {
                "match_kind": "EXACT_TEXT_MATCH",
                "baseline_source_index": base_index,
                "baseline_text": base_seg.text,
                "overlap_ms": ov_ms,
                "containment_ratio": round(containment, 4),
                "text_similarity": 1.0,
                "affix_ratio": 1.0,
                "end_delta_ms": end_delta_ms,
            }
        if ov_ms <= 0:
            continue
        sim = SequenceMatcher(None, seg_norm, base_norm).ratio()
        affix_ratio = _common_affix_length(seg_norm, base_norm) / min(len(seg_norm), len(base_norm))
        match_kind = None
        if containment >= 0.70 and sim >= 0.75:
            match_kind = "HIGH_OVERLAP_SIMILAR_TEXT"
        elif containment >= 0.90 and affix_ratio >= 0.50 and end_delta_ms <= 250:
            match_kind = "CONTAINED_PHONETIC_NEAR_MATCH"
        if match_kind is not None:
            score = containment * (sim + affix_ratio)
            if score > best_score:
                best_score = score
                best = {
                    "match_kind": match_kind,
                    "baseline_source_index": base_index,
                    "baseline_text": base_seg.text,
                    "overlap_ms": ov_ms,
                    "containment_ratio": round(containment, 4),
                    "text_similarity": round(sim, 4),
                    "affix_ratio": round(affix_ratio, 4),
                    "end_delta_ms": end_delta_ms,
                }
    return best


def build_supplemental_asr_groups(
    plan: UtteranceReviewPlan,
    recovery: OutsideSpanRecoveryResult,
    *,
    deduplicate_similar_overlaps: bool = True,
) -> tuple[UtteranceReviewGroup, ...]:
    """Convert ASR-verified recovered speech into deduplicated supplemental groups."""
    plan = validate_utterance_review_plan(plan)
    baseline_asr = plan.review_set._source_bundle.asr_result
    snapshot = plan.review_set.source_snapshot
    groups: list[UtteranceReviewGroup] = []
    seen_keys: set[str] = set()
    sup_index = 0
    for outcome in recovery.window_outcomes:
        if outcome.outcome != OUTSIDE_SPAN_OUTCOME_SPEECH_FOUND:
            continue
        for seg in outcome.segments:
            _validate_recovered_word_timings(
                seg.words,
                seg_start_ms=seg.start_ms,
                seg_end_ms=seg.end_ms,
                win_start_ms=outcome.start_ms,
                win_end_ms=outcome.end_ms,
                error_cls=V2DError,
            )
            overlap_match = _match_supplemental_baseline_overlap(
                seg.start_ms, seg.end_ms, seg.text, baseline_asr.segments,
            )
            if overlap_match is not None and (
                overlap_match["match_kind"] == "EXACT_TEXT_MATCH"
                or deduplicate_similar_overlaps
            ):
                continue
            ref = JAMasterSourceReference(
                source=EVIDENCE_SOURCE_SUPPLEMENTAL_ASR,
                source_id=seg.source_id,
                source_locator=snapshot.canonical_video_relative,
                source_index=sup_index,
                source_sha256=recovery.artifact_sha256,
                original_start_ms=seg.start_ms,
                original_end_ms=seg.end_ms,
                aligned_start_ms=Fraction(seg.start_ms),
                aligned_end_ms=Fraction(seg.end_ms),
            )
            if ref.key in seen_keys:
                continue
            seen_keys.add(ref.key)
            sup_index += 1
            word_refs = tuple(
                ASRWordReference(
                    source_reference=ref,
                    word_index=w_idx,
                    text=w.text,
                    start_ms=Fraction(w.start_ms),
                    end_ms=Fraction(w.end_ms),
                )
                for w_idx, w in enumerate(seg.words)
            )
            member = UtteranceMember(
                source_reference=ref,
                text=seg.text,
                word_references=word_refs,
            )
            group_id = "group-" + _sha(_wire([
                "supplemental_asr", recovery.artifact_sha256, ref.key, seg.start_ms, seg.end_ms,
            ]))
            groups.append(UtteranceReviewGroup(
                group_id=group_id,
                source_cardinality="SUPPLEMENTAL_ASR_ONLY",
                candidate_ids=(),
                members=(member,),
                relationships=(),
                utterance_status=UTTERANCE_UNRESOLVED,
                speaker_status=SPEAKER_UNKNOWN,
            ))
    return tuple(groups)


def load_validated_outside_span_diagnostic_evidence(
    path: str | Path,
    *,
    recovery_plan: OutsideSpanRecoveryPlan,
    expected_sha256: str,
    expected_runtime_identity: ASRRuntimeIdentity | None = None,
) -> OutsideSpanRecoveryResult:
    """Validate a saved private diagnostic JSON read-only for offline verification only."""
    raw = Path(path).read_bytes()
    actual_sha = _sha(raw)
    if actual_sha != _digest(expected_sha256, "expected_sha256"):
        raise V2DError("diagnostic artifact SHA-256 differs")
    data = _load_json(raw, "outside-span diagnostic evidence")
    if type(data) is not dict or data.get("diagnostic_kind") != "HYPOTHESIS_ONLY_UNTIMED_EXTERNAL_JA_TARGETED_ASR":
        raise V2DError("diagnostic artifact kind is invalid")
    snap = data.get("source_snapshot", {})
    exp_snap = recovery_plan.source_snapshot
    if (snap.get("canonical_video_relative") != exp_snap.canonical_video_relative
            or snap.get("source_size") != exp_snap.source_size
            or snap.get("source_mtime_ns") != exp_snap.source_mtime_ns):
        raise V2DError("diagnostic artifact source snapshot differs")
    dur_ms = snap.get("verified_container_duration_ms")
    if type(dur_ms) is not int or dur_ms <= 0:
        raise V2DError("diagnostic artifact container duration is invalid")
    rt = data.get("runtime_identity", {})
    runtime_id = ASRRuntimeIdentity(
        engine=rt["engine"], model=rt["model"], device=rt["device"],
        compute_type=rt["compute_type"], cpu_threads=rt.get("cpu_threads"),
        num_workers=rt["num_workers"],
    )
    engine_ver = rt.get("engine_version")
    if expected_runtime_identity is not None and runtime_id != expected_runtime_identity:
        raise V2DError("diagnostic artifact runtime identity differs")
    if type(engine_ver) is not str or not engine_ver:
        raise V2DError("diagnostic artifact engine_version is invalid")
    diag_by_cue = {w["cue_id"]: w for w in data.get("windows", []) if isinstance(w, dict) and "cue_id" in w}
    outcomes: list[OutsideSpanWindowOutcome] = []
    for win in recovery_plan.windows:
        # Match diagnostic entry by external cue_id
        matched_entries = [diag_by_cue[k.split(":", 1)[1]] for k in win.external_source_keys if k.split(":", 1)[1] in diag_by_cue]
        if not matched_entries:
            outcomes.append(OutsideSpanWindowOutcome(
                window_id=win.window_id, start_ms=win.start_ms, end_ms=win.end_ms,
                external_source_keys=win.external_source_keys, outcome=OUTSIDE_SPAN_OUTCOME_INCONCLUSIVE,
            ))
            continue
        entry = matched_entries[0]
        if entry.get("status") != "EXECUTED_ONCE":
            outcomes.append(OutsideSpanWindowOutcome(
                window_id=win.window_id, start_ms=win.start_ms, end_ms=win.end_ms,
                external_source_keys=win.external_source_keys, outcome=OUTSIDE_SPAN_OUTCOME_INCONCLUSIVE,
            ))
            continue
        w_s, w_e = entry["decoded_chunk_start_ms"], entry["decoded_chunk_end_ms"]
        if not (0 <= w_s < w_e <= dur_ms) or w_s != win.start_ms or w_e != win.end_ms:
            raise V2DError("diagnostic window bounds differ from recovery plan")
        segs = []
        for idx, s in enumerate(entry.get("segments", [])):
            s_start, s_end, s_text = s["start_ms"], s["end_ms"], s["text"]
            words = tuple(ASRWord(start_ms=wd["start_ms"], end_ms=wd["end_ms"], text=wd["text"]) for wd in s.get("words", ()))
            _validate_recovered_word_timings(
                words, seg_start_ms=s_start, seg_end_ms=s_end,
                win_start_ms=w_s, win_end_ms=w_e, error_cls=V2DError,
            )
            sid = "sup-asr-" + _sha(_wire([actual_sha, win.window_id, idx, s_start, s_end, s_text]))[:24]
            segs.append(RecoveredSupplementalASRSegment(
                source_id=sid, window_id=win.window_id, window_start_ms=w_s, window_end_ms=w_e,
                start_ms=s_start, end_ms=s_end, text=s_text, words=words,
                trigger_external_source_keys=win.external_source_keys,
            ))
        outcome_kind = OUTSIDE_SPAN_OUTCOME_SPEECH_FOUND if segs else OUTSIDE_SPAN_OUTCOME_NO_SPEECH
        outcomes.append(OutsideSpanWindowOutcome(
            window_id=win.window_id, start_ms=w_s, end_ms=w_e,
            external_source_keys=win.external_source_keys, outcome=outcome_kind, segments=tuple(segs),
        ))
    return OutsideSpanRecoveryResult(
        plan=recovery_plan,
        runtime_identity=runtime_id,
        engine_version=engine_ver,
        verified_container_duration_ms=dur_ms,
        artifact_sha256=actual_sha,
        window_outcomes=tuple(outcomes),
        diagnostic_only=True,
    )


@dataclass(frozen=True)
class _V2DTargetedRequest:
    plan: TargetedSecondEvidencePlan = field(repr=False)
    asr_result: ASRResult = field(repr=False)
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
        plan=plan, asr_result=asr_result, cue_ids=requested,
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
        elif any(ref.source == EVIDENCE_SOURCE_SUPPLEMENTAL_ASR for ref in refs):
            raise V2DHold("TARGETED_ASR_NO_SOURCE_BOUND_BASELINE_SEGMENT")
        else:
            raise V2DHold("TARGETED_ASR_NO_SOURCE_BOUND_INTERVAL")
    result = []
    if baseline_ids:
        result.append(_build_targeted_request(master, translated, tuple(baseline_ids)))
    if external_ids:
        result.append(_build_external_targeted_request(master, translated, tuple(external_ids)))
    return tuple(result)


def _build_initial_targeted_requests(
    plan: UtteranceReviewPlan, group_ids: tuple[str, ...],
) -> tuple[_V2DTargetedRequest | _V2DExternalTargetedRequest, ...]:
    """Plan early evidence from genuine source references, before master creation."""
    plan = validate_utterance_review_plan(plan)
    if (type(group_ids) is not tuple or not group_ids or len(set(group_ids)) != len(group_ids)):
        raise V2DHold("INITIAL_TARGETED_GROUP_SELECTION_INVALID")
    groups = {group.group_id: group for group in plan.groups}
    if set(group_ids) - set(groups):
        raise V2DHold("INITIAL_TARGETED_GROUP_UNBOUND")
    review = plan.review_set
    bundle = review._source_bundle
    asr_result = bundle.asr_result
    try:
        asr_result.__post_init__()
        asr_raw = serialize_asr_result(asr_result)
    except Exception as error:
        raise V2DHold("INITIAL_TARGETED_BASELINE_ASR_INVALID") from error
    asr_sha = _sha(asr_raw)
    if asr_sha != review.asr_sha256 or asr_result.source_snapshot != review.source_snapshot:
        raise V2DHold("INITIAL_TARGETED_BASELINE_ASR_MISMATCH")

    asr_links: dict[int, set[str]] = {}
    external_links: dict[int, set[str]] = {}
    for group_id in group_ids:
        group = groups[group_id]
        valid_interval_found = False
        for member in group.members:
            ref = member.source_reference
            if ref.source == EVIDENCE_SOURCE_ASR_SEGMENT:
                index = ref.source_index
                if index >= len(asr_result.segments):
                    raise V2DHold("INITIAL_TARGETED_ASR_SOURCE_INDEX_INVALID")
                segment = asr_result.segments[index]
                if (ref.source_id != stable_cue_id(EVIDENCE_SOURCE_ASR_SEGMENT, index)
                        or ref.source_sha256 != asr_sha
                        or ref.source_locator != review.source_snapshot.canonical_video_relative
                        or ref.original_start_ms != segment.start_ms
                        or ref.original_end_ms != segment.end_ms
                        or ref.aligned_start_ms != Fraction(segment.start_ms)
                        or ref.aligned_end_ms != Fraction(segment.end_ms)
                        or member.text != segment.text):
                    raise V2DHold("INITIAL_TARGETED_ASR_SOURCE_IDENTITY_MISMATCH")
                asr_links.setdefault(index, set()).add(group_id)
                valid_interval_found = True
            elif ref.source == "external_ja":
                # Unaligned external cues have no legitimate audio window.
                # A timed ASR member in the same group may still supply one.
                if (review.route != ROUTE_EXTERNAL_ALIGNMENT_ACCEPTED
                        or review._source_alignment is None
                        or bundle.external_ja_payload is None
                        or bundle.external_ja_document is None):
                    continue
                payload = bundle.external_ja_payload
                document = bundle.external_ja_document
                index = ref.source_index
                if index >= len(document.cues):
                    raise V2DHold("INITIAL_TARGETED_EXTERNAL_SOURCE_INDEX_INVALID")
                cue = document.cues[index]
                if (ref.source_id != stable_cue_id("external_ja", index)
                        or ref.source_sha256 != payload.sha256
                        or ref.source_locator != payload.candidate.external_source_id
                        or ref.original_start_ms != cue.start_ms
                        or ref.original_end_ms != cue.end_ms
                        or ref.aligned_start_ms is None or ref.aligned_end_ms is None
                        or member.text != cue.text):
                    continue
                external_links.setdefault(index, set()).add(group_id)
                valid_interval_found = True
        if not valid_interval_found:
            raise V2DHold("INITIAL_TARGETED_NO_VERIFIED_SOURCE_INTERVAL")

    requests: list[_V2DTargetedRequest | _V2DExternalTargetedRequest] = []
    if asr_links:
        sources, intervals, links = [], [], []
        for index, owners in sorted(asr_links.items()):
            segment = asr_result.segments[index]
            source_id = stable_cue_id(EVIDENCE_SOURCE_ASR_SEGMENT, index)
            sources.append(TargetedSecondEvidenceSource(
                source_index=index, cue_id=source_id, start_ms=segment.start_ms,
                end_ms=segment.end_ms, source_text=segment.text,
            ))
            intervals.append(TargetedASRSourceInterval(
                source_id=source_id, source_index=index,
                start_ms=segment.start_ms, end_ms=segment.end_ms,
            ))
            links.append((source_id, index, (), tuple(sorted(owners))))
        geometry = plan_targeted_asr_source_windows_with_policy(
            tuple(intervals), policy=STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1,
        )
        windows = tuple(TargetedSecondEvidenceWindow(
            window_id="targeted-window-" + f"{index + 1:06d}",
            start_ms=window.start_ms, end_ms=window.end_ms,
            source_ids=window.source_ids, source_indices=window.source_indices,
        ) for index, window in enumerate(geometry))
        targeted_plan = _make_targeted_plan(review.source_snapshot, tuple(sources), windows)
        context_raw = _wire({
            "schema_version": 1,
            "source_fingerprint": _source_fingerprint(plan),
            "group_ids": list(group_ids),
            "source_cue_links": [[source_id, index, list(cue_ids), list(owner_ids)]
                                  for source_id, index, cue_ids, owner_ids in links],
            "baseline_asr_sha256": asr_sha,
            "plan_binding_sha256": targeted_plan.binding_sha256,
        })
        requests.append(_V2DTargetedRequest(
            plan=targeted_plan, asr_result=asr_result, cue_ids=(),
            source_cue_links=tuple(links), baseline_asr_sha256=asr_sha,
            context_raw=context_raw, context_sha256=_sha(context_raw),
        ))
    if external_links:
        review = plan.review_set
        bundle = review._source_bundle
        payload, document, alignment = (bundle.external_ja_payload,
                                        bundle.external_ja_document,
                                        review._source_alignment)
        if (review.route != ROUTE_EXTERNAL_ALIGNMENT_ACCEPTED or payload is None
                or document is None or alignment is None):
            raise V2DHold("INITIAL_TARGETED_EXTERNAL_ALIGNMENT_UNAVAILABLE")
        target_ids = tuple(stable_cue_id("external_ja", index)
                           for index in sorted(external_links))
        windows = plan_targeted_asr_windows_with_policy(
            tuple(document.cues), alignment,
            policy=STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1,
            target_cue_ids=target_ids,
        )
        links = tuple((stable_cue_id("external_ja", index), (),
                       tuple(sorted(owners)))
                      for index, owners in sorted(external_links.items()))
        context_raw = _wire({
            "schema_version": 1,
            "source_fingerprint": _source_fingerprint(plan),
            "group_ids": list(group_ids),
            "external_ja_sha256": payload.sha256,
            "source_cue_links": [[source_id, list(cue_ids), list(owner_ids)]
                                  for source_id, cue_ids, owner_ids in links],
            "windows": [[window.start_ms, window.end_ms, list(window.external_cue_ids)]
                        for window in windows],
        })
        requests.append(_V2DExternalTargetedRequest(
            source_snapshot=review.source_snapshot, windows=windows, cue_ids=(),
            source_cue_links=links, context_raw=context_raw,
            context_sha256=_sha(context_raw),
        ))
    if not requests:
        raise V2DHold("INITIAL_TARGETED_NO_VERIFIED_SOURCE_INTERVAL")
    return tuple(requests)


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

    def execute_for_snapshot(source_snapshot, operation, *, window_count: int):
        from teddy_discovery_stage11_live_adapters import _snapshot
        try:
            video, current = _snapshot(holding_resolver(source_snapshot.dvd_id), source_snapshot.dvd_id)
        except Exception as error:
            raise V2DHold("TARGETED_ASR_CURRENT_SOURCE_UNAVAILABLE") from error
        if current != source_snapshot:
            raise V2DHold("TARGETED_ASR_CURRENT_SOURCE_CHANGED")
        budget = _ACTIVE_V2D_BUDGET.get()
        request_timeout = getattr(targeted_transport, "request_timeout_seconds", None)
        if (type(window_count) is not int or window_count < 1
                or type(request_timeout) not in (int, float)
                or not math.isfinite(float(request_timeout))
                or request_timeout <= 0 or request_timeout > 900):
            raise V2DHold("TARGETED_ASR_EXISTING_TIMEOUT_BOUND_UNAVAILABLE")
        reserve = window_count * float(request_timeout)
        copy_timeout = None
        if budget is not None:
            budget.require_time(reserve, reason="WALL_TIME_LIMIT_BEFORE_TARGETED_ASR")
            copy_timeout = budget.remaining() - reserve
            if copy_timeout <= 0:
                raise V2DLimitStop("WALL_TIME_LIMIT_BEFORE_SOURCE_COPY")
        try:
            with source_provider.copy_to_temp(
                    video, max_media_bytes=current.source_size, timeout=copy_timeout) as local_source:
                if not isinstance(local_source, ASRLocalMediaSource) or local_source.source_snapshot != current:
                    raise V2DHold("TARGETED_ASR_LOCAL_SOURCE_CHANGED")
                if budget is not None:
                    budget.require_time(reserve, reason="WALL_TIME_LIMIT_AFTER_SOURCE_COPY")
                session_factory = getattr(targeted_transport, "session", None)
                session = session_factory() if callable(session_factory) else nullcontext(targeted_transport)
                with session as active_transport:
                    if (getattr(active_transport, "runtime_identity", None) != runtime_identity
                            or getattr(active_transport, "engine_version", None) != engine_version):
                        raise V2DHold("TARGETED_ASR_RUNTIME_CHANGED")
                    if budget is not None:
                        budget.require_time(reserve, reason="WALL_TIME_LIMIT_BEFORE_TARGETED_ASR")
                        active_transport = _BudgetedTargetedTransport(
                            active_transport, budget, request_timeout_seconds=request_timeout,
                        )
                    active_audio_iterator = audio_chunk_iterator
                    if budget is not None:
                        def active_audio_iterator(*args, **kwargs):
                            budget.require_time(request_timeout,
                                                reason="WALL_TIME_LIMIT_BEFORE_TARGETED_AUDIO_DECODE")
                            yield from audio_chunk_iterator(*args, **kwargs)
                    provider = build_targeted_audio_window_provider(
                        local_source, audio_chunk_iterator=active_audio_iterator,
                    )
                    return operation(local_source, active_transport, provider, active_audio_iterator)
        except (V2DHold, V2DLimitStop):
            raise
        except Exception as error:
            cause = error
            while cause is not None:
                if isinstance(cause, V2DLimitStop):
                    raise cause
                cause = cause.__cause__
            if budget is not None and budget.remaining() <= 0:
                raise V2DLimitStop("WALL_TIME_LIMIT_DURING_TARGETED_ASR") from error
            raise V2DHold("TARGETED_ASR_EXECUTION_OR_CLEANUP_FAILED") from error

    def targeted(asr_result: ASRResult, plan: TargetedSecondEvidencePlan):
        if type(asr_result) is not ASRResult or asr_result.source_snapshot != plan.source_snapshot:
            raise V2DHold("TARGETED_ASR_BASELINE_IDENTITY_MISMATCH")
        return execute_for_snapshot(
            asr_result.source_snapshot,
            lambda _source, active, provider, _audio_iterator: _execute_targeted_plan(
                plan, asr_result=asr_result, targeted_transport=active,
                audio_window_provider=provider,
            ),
            window_count=len(plan.windows),
        )

    def targeted_external_ja(request):
        if type(request) is not _V2DExternalTargetedRequest:
            raise V2DHold("TARGETED_ASR_EXTERNAL_REQUEST_INVALID")
        if not request.windows or any(type(window) is not TargetedASRWindow for window in request.windows):
            raise V2DHold("TARGETED_ASR_EXTERNAL_WINDOWS_INVALID")
        def run(_source, active, _provider, active_audio_iterator):
            return run_targeted_hybrid_windows(
                request.windows, local_source=_source, targeted_transport=active,
                audio_chunk_iterator=active_audio_iterator,
            )
        return execute_for_snapshot(request.source_snapshot, run,
                                    window_count=len(request.windows))

    def targeted_outside_span(recovery_plan: OutsideSpanRecoveryPlan):
        if type(recovery_plan) is not OutsideSpanRecoveryPlan:
            raise V2DHold("OUTSIDE_SPAN_RECOVERY_PLAN_INVALID")
        if recovery_plan.exceeds_budget:
            raise V2DHold("OUTSIDE_SPAN_TARGETED_ASR_BUDGET_EXCEEDED")
        if not recovery_plan.windows:
            raise V2DHold("OUTSIDE_SPAN_RECOVERY_WINDOWS_EMPTY")

        def run(local_source, active, _provider, active_audio_iterator):
            import av
            with av.open(str(local_source.local_path)) as container:
                dur_ms = int(round((float(container.duration) / float(av.time_base)) * 1000))
            if dur_ms <= 0:
                raise V2DHold("OUTSIDE_SPAN_CONTAINER_DURATION_INVALID")
            raw_windows = []
            for win in recovery_plan.windows:
                if not (0 <= win.start_ms < win.end_ms <= dur_ms):
                    raise V2DHold("OUTSIDE_SPAN_WINDOW_OUTSIDE_VIDEO_DURATION")
                dur_sec = (win.end_ms - win.start_ms) / 1000.0
                chunks = tuple(active_audio_iterator(
                    local_source,
                    chunk_seconds=dur_sec,
                    start_seconds=win.start_ms / 1000.0,
                    end_seconds=win.end_ms / 1000.0,
                ))
                if len(chunks) != 1:
                    raise V2DHold("OUTSIDE_SPAN_AUDIO_DECODE_CHUNK_COUNT_INVALID")
                chunk = chunks[0]
                if chunk.start_ms != win.start_ms or chunk.end_ms != win.end_ms:
                    raise V2DHold("OUTSIDE_SPAN_AUDIO_DECODE_BOUNDS_MISMATCH")
                # Transcribe and immediately materialize raw segment data before optional metadata.
                segs = active.transcribe_targeted_chunk(chunk)
                seg_rows = []
                for s in segs:
                    if type(s) is not ASRSegment:
                        raise V2DHold("OUTSIDE_SPAN_SEGMENT_TYPE_INVALID")
                    words_tuple = tuple(s.words or ())
                    _validate_recovered_word_timings(
                        words_tuple, seg_start_ms=s.start_ms, seg_end_ms=s.end_ms,
                        win_start_ms=win.start_ms, win_end_ms=win.end_ms, error_cls=V2DHold,
                    )
                    seg_rows.append({
                        "start_ms": s.start_ms,
                        "end_ms": s.end_ms,
                        "text": s.text,
                        "words": [
                            {"start_ms": w.start_ms, "end_ms": w.end_ms, "text": w.text}
                            for w in words_tuple
                        ],
                    })
                raw_windows.append({
                    "window_id": win.window_id,
                    "start_ms": win.start_ms,
                    "end_ms": win.end_ms,
                    "external_source_keys": list(win.external_source_keys),
                    "outcome": OUTSIDE_SPAN_OUTCOME_SPEECH_FOUND if seg_rows else OUTSIDE_SPAN_OUTCOME_NO_SPEECH,
                    "segments": seg_rows,
                    "decoded_sample_rate": chunk.sample_rate,
                    "decoded_sample_count": int(len(chunk.samples)),
                })
            return {
                "schema_version": V2D_SCHEMA_VERSION,
                "verified_container_duration_ms": dur_ms,
                "runtime_identity": {
                    "engine": runtime_identity.engine,
                    "model": runtime_identity.model,
                    "device": runtime_identity.device,
                    "compute_type": runtime_identity.compute_type,
                    "cpu_threads": runtime_identity.cpu_threads,
                    "num_workers": runtime_identity.num_workers,
                },
                "engine_version": engine_version,
                "windows": raw_windows,
            }

        return execute_for_snapshot(
            recovery_plan.source_snapshot, run, window_count=len(recovery_plan.windows),
        )

    targeted.runtime_identity = runtime_identity
    targeted.engine_version = engine_version
    targeted.bounded_worker_lifecycle = getattr(targeted_transport, "bounded_worker_lifecycle", False) is True
    targeted.targeted_external_ja = targeted_external_ja
    targeted.targeted_outside_span = targeted_outside_span
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


def _load_or_run_targeted_evidence(request: _V2DTargetedRequest, *, master: V2DMaster | None = None,
                                   targeted_runner: Callable | None,
                                   staging_root: str | Path,
                                   reuse_only: bool) -> _V2DTargetedEvidence:
    asr_result = request.asr_result
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
        except V2DLimitStop:
            raise
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
        if not group_ids:
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
    request: _V2DExternalTargetedRequest, *, master: V2DMaster | None = None,
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
        except V2DLimitStop:
            raise
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
            if not group_ids:
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
                                  reuse_only: bool,
                                  batch_groups: bool | None = None,
                                  exclude_group_ids: tuple[str, ...] = (),
                                  supplemental_groups: tuple[UtteranceReviewGroup, ...] = (),
                                  allow_limited_json_recovery: bool = False,
                                  recovery_log: list[dict[str, object]] | None = None,
                                  use_short_id_mapping_for_uncached: bool = False) -> V2DAdjudication:
    """Revisit only affected groups; ASR output stays supporting evidence."""
    evidence_by_group = dict(evidence.group_payloads)
    original_by_group = {item.group_id: item for item in original.groups}
    if not evidence_by_group or set(evidence_by_group) - set(original_by_group):
        raise V2DHold("TARGETED_ASR_GROUP_EVIDENCE_UNBOUND")
    excluded = set(exclude_group_ids)
    effective_groups = tuple(g for g in plan.groups if g.group_id not in excluded) + tuple(supplemental_groups)
    effective_fp = _source_fingerprint(
        plan, exclude_group_ids=exclude_group_ids, supplemental_groups=supplemental_groups,
    )
    root = _private_dir(staging_root)
    context_sha = _sha(_wire({
        "source_fingerprint": effective_fp,
        "artifact_sha256": evidence.artifact_sha256,
        "linkage_sha256": evidence.linkage_sha256,
        "claim_token": claim_token,
    }))
    try:
        task = _private_child(root, "targeted-readjudication-" + context_sha, create=not reuse_only)
    except V2DError as error:
        raise V2DHold("TARGETED_ASR_READJUDICATION_RESUME_STAGE_MISSING") from error
    if batch_groups is None:
        batch_groups = getattr(invoke, "_v2d_native_owner", None) is not None
    expected_groups = {group.group_id: group for group in effective_groups}
    if batch_groups:
        payloads = []
        for group in effective_groups:
            if group.group_id not in evidence_by_group:
                continue
            payload = _group_payload(plan, group, source_fingerprint=effective_fp)
            payload["targeted_second_evidence"] = evidence_by_group[group.group_id]
            payloads.append((group.group_id, payload))
        revised, receipts = _adjudicate_group_batches(
            tuple(payloads), expected_groups=expected_groups,
            source_fingerprint=effective_fp, invoke=invoke,
            hermes_settings=hermes_settings, task=task,
            label="ja-master-targeted-readjudication-batch", reuse_only=reuse_only,
            instruction=SEMANTIC_TARGETED_READJUDICATION_BATCH_INSTRUCTION,
            allow_limited_json_recovery=allow_limited_json_recovery,
            recovery_log=recovery_log,
            use_short_id_mapping_for_uncached=use_short_id_mapping_for_uncached,
        )
        revised_by_group = {item.group_id: item for item in revised}
        resolved_groups = tuple(revised_by_group.get(group.group_id, original_by_group[group.group_id])
                                for group in effective_groups)
        batch_evidence = original.batch_evidence + receipts
    else:
        resolved = {}
        for group in effective_groups:
            if group.group_id not in evidence_by_group:
                continue
            group_payload = _group_payload(plan, group, source_fingerprint=effective_fp)
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
            def validator(raw, group=group):
                parsed = _parse_group_response(raw, group)
                _validate_group_source_spans(group, parsed)
                return parsed
            adjudicated = invoke(
                prompt, group_dir, "ja-master-targeted-readjudication", validator,
                hermes_settings=hermes_settings, reuse_only=reuse_only,
            )
            if type(adjudicated) is not GroupAdjudication:
                raise V2DHold("TARGETED_ASR_READJUDICATION_RESULT_INVALID")
            resolved[group.group_id] = adjudicated
        resolved_groups = tuple(resolved.get(group.group_id, original_by_group[group.group_id])
                                for group in effective_groups)
        batch_evidence = original.batch_evidence
    return validate_adjudication(
        plan, V2DAdjudication(effective_fp, resolved_groups, batch_evidence),
        exclude_group_ids=exclude_group_ids, supplemental_groups=supplemental_groups,
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

    stage_invoke._v2d_native_owner = owner
    return stage_invoke, owner


def _budgeted_invoke(invoke: Callable, budget: _V2DRunBudget, owner):
    """Gate each actual Native transport attempt; count fake offline calls too."""
    def call(prompt, directory, label, validator, *, hermes_settings, reuse_only=False):
        budget.require_time(reason="WALL_TIME_LIMIT_BEFORE_STAGE")
        if owner is None:
            if not reuse_only:
                budget.reserve_hermes(0)
            result = invoke(prompt, directory, label, validator,
                            hermes_settings=hermes_settings, reuse_only=reuse_only)
        else:
            bridge = getattr(owner, "bridge", None)
            original = getattr(bridge, "_python", None)
            if not callable(original):
                raise V2DHold("NATIVE_HERMES_TRANSPORT_BOUND_UNAVAILABLE")

            def bounded_python(*args, **kwargs):
                timeout = kwargs.get("timeout")
                if type(timeout) not in (int, float) or not math.isfinite(float(timeout)) or timeout <= 0:
                    raise V2DHold("NATIVE_HERMES_TIMEOUT_BOUND_UNAVAILABLE")
                budget.reserve_hermes(timeout)
                return original(*args, **kwargs)

            # The legacy Normal Mode path remains unchanged. Only the
            # budgeted V2-D native call uses the parent-loss remote guard.
            prior_guard = getattr(owner, "_v2d_remote_guard", False)
            owner._v2d_remote_guard = True
            bridge._python = bounded_python
            try:
                result = invoke(prompt, directory, label, validator,
                                hermes_settings=hermes_settings, reuse_only=reuse_only)
            finally:
                bridge._python = original
                owner._v2d_remote_guard = prior_guard
        budget.require_time(reason="WALL_TIME_LIMIT_AFTER_STAGE")
        return result

    call._v2d_native_owner = owner
    return call


class _BudgetedTargetedTransport:
    def __init__(self, transport, budget: _V2DRunBudget,
                 *, request_timeout_seconds: int | float | None = None):
        self._transport = transport
        self._budget = budget
        self.runtime_identity = transport.runtime_identity
        self.engine_version = transport.engine_version
        timeout = (
            transport.request_timeout_seconds
            if request_timeout_seconds is None
            else request_timeout_seconds
        )
        if (type(timeout) not in (int, float)
                or not math.isfinite(float(timeout))
                or timeout <= 0 or timeout > 900):
            raise V2DHold("TARGETED_ASR_EXISTING_TIMEOUT_BOUND_UNAVAILABLE")
        self.request_timeout_seconds = float(timeout)

    def transcribe_targeted_chunk(self, chunk):
        self._budget.reserve_targeted_asr(self.request_timeout_seconds)
        return self._transport.transcribe_targeted_chunk(chunk)

    @property
    def _budget(self):
        return self.__dict__["__budget"]

    @_budget.setter
    def _budget(self, value):
        self.__dict__["__budget"] = value


def _parse_group_response(raw: bytes, group, *, require_audio_flag: bool = False) -> GroupAdjudication:
    data = _load_json(raw, "JA Master adjudication")
    base_fields = {"group_id", "candidate_decisions", "source_decisions", "outputs"}
    if type(data) is not dict or set(data) not in (base_fields, base_fields | {"audio_evidence_needed"}):
        raise V2DError("JA Master response fields differ")
    if require_audio_flag and "audio_evidence_needed" not in data:
        raise V2DError("JA Master response lacks the explicit audio evidence disposition")
    if data["group_id"] != group.group_id:
        raise V2DError("JA Master response group differs")
    audio_evidence_needed = data.get("audio_evidence_needed", False)
    if type(audio_evidence_needed) is not bool:
        raise V2DError("audio evidence disposition is invalid")
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
    result = GroupAdjudication(
        group.group_id, tuple(candidates), tuple(sources), tuple(outputs),
        audio_evidence_needed,
    )
    has_uncertain = any(item.status == DECISION_UNCERTAIN
                        for item in (*result.candidate_decisions, *result.source_decisions))
    if result.audio_evidence_needed and not has_uncertain:
        raise V2DError("audio evidence was requested without an unresolved decision")
    return result


def _outside_span_result_from_payload(
    recovery_plan: OutsideSpanRecoveryPlan,
    payload: dict[str, object],
    artifact_sha: str,
) -> OutsideSpanRecoveryResult:
    rt = payload.get("runtime_identity", {})
    runtime_id = ASRRuntimeIdentity(
        engine=rt["engine"], model=rt["model"], device=rt["device"],
        compute_type=rt["compute_type"], cpu_threads=rt.get("cpu_threads"),
        num_workers=rt["num_workers"],
    )
    engine_ver = payload.get("engine_version")
    dur_ms = payload.get("verified_container_duration_ms")
    if type(engine_ver) is not str or not engine_ver or type(dur_ms) is not int or dur_ms <= 0:
        raise V2DHold("OUTSIDE_SPAN_RECOVERY_ARTIFACT_INVALID")
    expected_by_id = {w.window_id: w for w in recovery_plan.windows}
    outcomes: list[OutsideSpanWindowOutcome] = []
    seen_ids: set[str] = set()
    for row in payload.get("windows", []):
        wid = row.get("window_id")
        exp = expected_by_id.get(wid)
        if exp is None or wid in seen_ids:
            raise V2DHold("OUTSIDE_SPAN_RECOVERY_WINDOW_MISMATCH")
        seen_ids.add(wid)
        if row.get("start_ms") != exp.start_ms or row.get("end_ms") != exp.end_ms:
            raise V2DHold("OUTSIDE_SPAN_RECOVERY_WINDOW_BOUNDS_MISMATCH")
        segs = []
        for idx, s in enumerate(row.get("segments", [])):
            s_start, s_end, s_text = s["start_ms"], s["end_ms"], s["text"]
            words = tuple(ASRWord(start_ms=wd["start_ms"], end_ms=wd["end_ms"], text=wd["text"]) for wd in s.get("words", ()))
            _validate_recovered_word_timings(
                words, seg_start_ms=s_start, seg_end_ms=s_end,
                win_start_ms=exp.start_ms, win_end_ms=exp.end_ms, error_cls=V2DHold,
            )
            sid = "sup-asr-" + _sha(_wire([artifact_sha, wid, idx, s_start, s_end, s_text]))[:24]
            segs.append(RecoveredSupplementalASRSegment(
                source_id=sid, window_id=wid, window_start_ms=exp.start_ms, window_end_ms=exp.end_ms,
                start_ms=s_start, end_ms=s_end, text=s_text, words=words,
                trigger_external_source_keys=exp.external_source_keys,
            ))
        outcome_kind = row.get("outcome")
        if outcome_kind not in {OUTSIDE_SPAN_OUTCOME_SPEECH_FOUND, OUTSIDE_SPAN_OUTCOME_NO_SPEECH, OUTSIDE_SPAN_OUTCOME_INCONCLUSIVE}:
            raise V2DHold("OUTSIDE_SPAN_RECOVERY_OUTCOME_INVALID")
        if outcome_kind == OUTSIDE_SPAN_OUTCOME_SPEECH_FOUND and not segs:
            raise V2DHold("OUTSIDE_SPAN_RECOVERY_SPEECH_EMPTY")
        outcomes.append(OutsideSpanWindowOutcome(
            window_id=wid, start_ms=exp.start_ms, end_ms=exp.end_ms,
            external_source_keys=exp.external_source_keys, outcome=outcome_kind, segments=tuple(segs),
        ))
    if seen_ids != set(expected_by_id):
        raise V2DHold("OUTSIDE_SPAN_RECOVERY_WINDOW_COVERAGE_MISMATCH")
    return OutsideSpanRecoveryResult(
        plan=recovery_plan, runtime_identity=runtime_id, engine_version=engine_ver,
        verified_container_duration_ms=dur_ms, artifact_sha256=artifact_sha,
        window_outcomes=tuple(outcomes), diagnostic_only=False,
    )


def _load_or_run_outside_span_recovery(
    recovery_plan: OutsideSpanRecoveryPlan,
    *,
    targeted_runner: Callable | None,
    staging_root: str | Path,
    reuse_only: bool,
) -> OutsideSpanRecoveryResult:
    if recovery_plan.exceeds_budget:
        raise V2DHold("OUTSIDE_SPAN_TARGETED_ASR_BUDGET_EXCEEDED")
    context_raw = _wire({
        "schema_version": V2D_SCHEMA_VERSION,
        "baseline_asr_sha256": recovery_plan.baseline_asr_sha256,
        "external_ja_sha256": recovery_plan.external_ja_sha256,
        "windows": [[w.window_id, w.start_ms, w.end_ms, list(w.external_source_keys)] for w in recovery_plan.windows],
    })
    context_sha = _sha(context_raw)
    root = _private_dir(staging_root)
    try:
        top = _private_child(root, "outside-span-targeted-asr", create=not reuse_only)
        stage = _private_child(top, context_sha, create=not reuse_only)
    except V2DError as error:
        if reuse_only:
            raise V2DHold("OUTSIDE_SPAN_RECOVERY_RESUME_MISSING") from error
        raise
    artifact_path = stage / "outside-span-targeted-asr-v1.json"
    if artifact_path.exists() or artifact_path.is_symlink():
        raw = _read_private_owned(artifact_path, max_bytes=MAX_TARGETED_ASR_ARTIFACT_BYTES)
        payload = _load_json(raw, "outside-span targeted ASR artifact")
        if payload.get("context_sha256") != context_sha:
            raise V2DHold("OUTSIDE_SPAN_RECOVERY_ARTIFACT_DETACHED")
        return _outside_span_result_from_payload(recovery_plan, payload, _sha(raw))
    if reuse_only:
        raise V2DHold("OUTSIDE_SPAN_RECOVERY_RESUME_MISSING")
    run_outside = getattr(targeted_runner, "targeted_outside_span", None)
    if not callable(run_outside):
        raise V2DHold("OUTSIDE_SPAN_TARGETED_ASR_ADAPTER_UNAVAILABLE")
    try:
        payload = run_outside(recovery_plan)
        if type(payload) is not dict:
            raise V2DHold("OUTSIDE_SPAN_RECOVERY_RESULT_INVALID")
        payload = dict(payload, context_sha256=context_sha)
        raw = _wire(payload)
        # Persist raw ASR results immediately before optional diagnostics.
        _write_exclusive(artifact_path, raw)
        readback_raw = _read_private_owned(artifact_path, max_bytes=MAX_TARGETED_ASR_ARTIFACT_BYTES)
        if readback_raw != raw:
            raise V2DHold("OUTSIDE_SPAN_RECOVERY_READBACK_MISMATCH")
        return _outside_span_result_from_payload(recovery_plan, payload, _sha(readback_raw))
    except (V2DLimitStop, V2DHold):
        raise
    except Exception as error:
        raise V2DHold("OUTSIDE_SPAN_TARGETED_ASR_EXECUTION_FAILED") from error


def validate_adjudication(
    plan: UtteranceReviewPlan,
    adjudication: V2DAdjudication,
    *,
    exclude_group_ids: tuple[str, ...] = (),
    supplemental_groups: tuple[UtteranceReviewGroup, ...] = (),
) -> V2DAdjudication:
    plan = validate_utterance_review_plan(plan)
    excluded = set(exclude_group_ids)
    effective_groups = tuple(g for g in plan.groups if g.group_id not in excluded) + tuple(supplemental_groups)
    expected_fp = _source_fingerprint(
        plan, exclude_group_ids=exclude_group_ids, supplemental_groups=supplemental_groups,
    )
    if type(adjudication) is not V2DAdjudication or adjudication.source_fingerprint != expected_fp:
        raise V2DError("adjudication is detached from source evidence")
    if tuple(item.group_id for item in adjudication.groups) != tuple(group.group_id for group in effective_groups):
        raise V2DError("adjudication group coverage/order differs")
    for group, resolved in zip(effective_groups, adjudication.groups, strict=True):
        expected_candidates = tuple(group.candidate_ids)
        expected_sources = tuple(member.source_reference.key for member in group.members)
        if tuple(item.candidate_id for item in resolved.candidate_decisions) != expected_candidates:
            raise V2DError("candidate coverage/order differs")
        if tuple(item.source_key for item in resolved.source_decisions) != expected_sources:
            raise V2DError("source coverage/order differs")
        if type(resolved.audio_evidence_needed) is not bool:
            raise V2DError("audio evidence disposition is invalid")
    return adjudication


SEMANTIC_ADJUDICATION_INSTRUCTION = """Interpret this one source-bound utterance group for a Japanese master. Return JSON only with exactly: group_id, candidate_decisions, source_decisions, outputs. Every candidate relation and every source must receive ACCEPTED, REJECTED, or UNCERTAIN plus a reason. A candidate relation is evidence, not proof of same utterance. Do not merge merely from overlap or identical text; preserve repeated spoken dialogue unless context supports a duplicate. Decide whether to merge or split semantic dialogue. Outputs contain Japanese text and source_spans only; each span has source_key and optional half-open word_start_index/word_end_index. Do not provide cue IDs, timestamps, speakers, ordering, or confidence. Source spans are claims the validator checks: only ASR word references may be split, with all words partitioned exactly once. Do not assign speakers; retain speaker evidence as supplied. If evidence is insufficient use UNCERTAIN. The caller owns IDs, time, ordering, source ownership, and files."""

SEMANTIC_BATCH_ADJUDICATION_INSTRUCTION = """Interpret each source-bound utterance group independently for a Japanese master. Return JSON only with exactly: batch_id, source_fingerprint, groups. Return one group object for every input group, in exactly the input order; each group object must have exactly group_id, audio_evidence_needed, candidate_decisions, source_decisions, outputs. For each group, return candidate_decisions in exact input candidate_relations order with exact keys candidate_id, status, rationale, and source_decisions in exact input members order with exact keys source_key, status, rationale; status must be ACCEPTED, REJECTED, or UNCERTAIN, and rationale must be a non-empty string. A candidate relation is evidence, not proof of same utterance. Do not merge merely from overlap or identical text; preserve repeated spoken dialogue unless context supports a duplicate. Decide whether to merge or split semantic dialogue. Each item in outputs must have exact keys japanese_text, source_spans, rationale (non-empty strings and non-empty source_spans). Each item in source_spans must have exact keys source_key, word_start_index, word_end_index; set both word_start_index and word_end_index to null for a whole source, or to half-open integer word indexes for a split ASR source. Do not omit or add keys. Outputs must reference only sources with status ACCEPTED (never REJECTED or UNCERTAIN) and must cover every ACCEPTED source. Do not provide cue IDs, timestamps, speakers, ordering, or confidence. Source spans are claims the validator checks: only ASR word references may be split, with all words partitioned exactly once. Do not assign speakers; retain speaker evidence as supplied. Set audio_evidence_needed true only when all three hold: at least one candidate_decisions or source_decisions item in that group has status UNCERTAIN, at least one member in that group has non-null aligned_start_ms and aligned_end_ms (original times alone do not count), and checking that timed audio could materially resolve the uncertainty; otherwise false. This field does not decide acceptance; never change an honest status to satisfy it. Do not invent timing for untimed or uncertain sources, force ACCEPTED or REJECTED, or drop plausible dialogue just to pass validation; if evidence is insufficient, preserve UNCERTAIN. The caller owns IDs, time, ordering, source ownership, and files."""

SEMANTIC_TARGETED_READJUDICATION_BATCH_INSTRUCTION = (
    SEMANTIC_BATCH_ADJUDICATION_INSTRUCTION
    + " This is a second-pass re-adjudication where targeted_second_evidence provides supporting time-bound ASR hypotheses already collected for this group; treat targeted_second_evidence as an ASR hypothesis, not absolute ground truth."
    + " Actively consider targeted_second_evidence together with baseline ASR and external JA: preserve sufficiently supported dialogue and refine wording in outputs[].japanese_text on ACCEPTED time-bearing source spans when corroborated by evidence, without inventing speech, timing, or unsupported portions of another interval."
    + " Judge source acceptance and candidate relations independently from evidence; do not automatically mark a candidate relation REJECTED merely because a source is REJECTED, as an inaccurate source can still refer to the same spoken utterance."
    + " Do not drop existing dialogue merely because it was not detected in targeted_second_evidence, do not mechanically ACCEPT from agreement, and do not force resolution; when evidence still materially conflicts or is insufficient, honestly preserve UNCERTAIN."
    + " Set audio_evidence_needed true only if a genuinely unresolved UNCERTAIN decision could still be materially helped by additional timed audio beyond the already-supplied windows; otherwise false, without suppressing honest UNCERTAIN."
)


def _make_batch_material(
    source_fingerprint: str,
    payloads: tuple[tuple[str, dict[str, object]], ...],
    *,
    instruction: str = SEMANTIC_BATCH_ADJUDICATION_INSTRUCTION,
):
    input_raw = _wire({
        "source_fingerprint": source_fingerprint,
        "groups": [{"group_id": group_id, "payload": payload}
                   for group_id, payload in payloads],
    })
    batch_id = _sha(input_raw)
    envelope = {
        "batch_id": batch_id,
        "source_fingerprint": source_fingerprint,
        "groups": [payload for _, payload in payloads],
    }
    prompt = (instruction
              + "\nSOURCE_BOUND_BATCH=" + _wire(envelope).decode("utf-8")).encode("utf-8")
    return batch_id, input_raw, prompt


def _pack_group_batches(
    source_fingerprint: str,
    payloads: tuple[tuple[str, dict[str, object]], ...],
    *,
    instruction: str = SEMANTIC_BATCH_ADJUDICATION_INSTRUCTION,
):
    if not payloads or len({group_id for group_id, _ in payloads}) != len(payloads):
        raise V2DError("group batch input is empty or duplicated")
    batches = []
    pending = []
    for item in payloads:
        trial = tuple((*pending, item))
        material = _make_batch_material(source_fingerprint, trial, instruction=instruction)
        if len(material[2]) <= V2D_MAX_PROMPT_BYTES:
            pending.append(item)
            continue
        if not pending:
            raise V2DHold("ONE_UTTERANCE_GROUP_EXCEEDS_EXISTING_PROMPT_LIMIT")
        batches.append(tuple(pending))
        pending = [item]
        if len(_make_batch_material(source_fingerprint, tuple(pending), instruction=instruction)[2]) > V2D_MAX_PROMPT_BYTES:
            raise V2DHold("ONE_UTTERANCE_GROUP_EXCEEDS_EXISTING_PROMPT_LIMIT")
    if pending:
        batches.append(tuple(pending))
    # Complete the packing and size validation before the first model call.
    return tuple((batch, *_make_batch_material(source_fingerprint, batch, instruction=instruction)) for batch in batches)


SHORT_ID_INSTRUCTION_ADDENDUM = (
    "\nUse the exact short identifiers provided in SOURCE_BOUND_GROUP_BATCH "
    "(batch_id, source_fingerprint, group_id such as G01, and candidate_id such as C01) "
    "verbatim without altering, omitting, or duplicating any identifier. "
    "Output pretty-printed JSON with standard indentation."
)


def _build_short_id_batch_material(
    batch: tuple[tuple[str, dict[str, object]], ...],
    *,
    batch_id: str,
    source_fingerprint: str,
    instruction: str,
) -> dict[str, object]:
    """Build deterministic short-ID batch prompt for uncached batches without mutating originals."""
    short_batch_id = "B-" + batch_id[:8]
    short_fp = "FP-SHORT"
    short_to_real_gid: dict[str, str] = {}
    expected_short_gids: list[str] = []
    short_to_real_cid_by_gid: dict[str, dict[str, str]] = {}
    expected_short_cids_by_gid: dict[str, tuple[str, ...]] = {}
    short_groups: list[dict[str, object]] = []
    cand_counter = 0

    for g_idx, (real_gid, payload) in enumerate(batch, 1):
        short_gid = f"G{g_idx:02d}"
        short_to_real_gid[short_gid] = real_gid
        expected_short_gids.append(short_gid)
        copied = json.loads(json.dumps(payload))
        copied["source_fingerprint"] = short_fp
        grp = copied["group"]
        grp["group_id"] = short_gid
        c_map: dict[str, str] = {}
        c_order: list[str] = []
        for cr in grp.get("candidate_relations", ()):
            cand_counter += 1
            short_cid = f"C{cand_counter:02d}"
            real_cid = cr["candidate_id"]
            if short_cid in c_map:
                raise V2DError("duplicate short candidate_id generated")
            c_map[short_cid] = real_cid
            c_order.append(short_cid)
            cr["candidate_id"] = short_cid
        short_to_real_cid_by_gid[real_gid] = c_map
        expected_short_cids_by_gid[real_gid] = tuple(c_order)
        short_groups.append(copied)

    short_input_raw = _wire({
        "batch_id": short_batch_id,
        "source_fingerprint": short_fp,
        "groups": short_groups,
    })
    short_prompt = (
        instruction + SHORT_ID_INSTRUCTION_ADDENDUM
        + "\nSOURCE_BOUND_GROUP_BATCH=" + short_input_raw.decode("utf-8")
    ).encode("utf-8")
    if len(short_prompt) > V2D_MAX_PROMPT_BYTES:
        raise V2DError("short-ID batch prompt exceeds the existing native prompt bound")
    return {
        "short_batch_id": short_batch_id,
        "short_fp": short_fp,
        "expected_short_gids": tuple(expected_short_gids),
        "short_to_real_gid": short_to_real_gid,
        "expected_short_cids_by_gid": expected_short_cids_by_gid,
        "short_to_real_cid_by_gid": short_to_real_cid_by_gid,
        "input_raw": short_input_raw,
        "prompt": short_prompt,
    }


def _restore_short_id_batch_response(
    data: object,
    *,
    short_batch_id: str,
    short_fp: str,
    real_batch_id: str,
    real_fp: str,
    expected_short_gids: tuple[str, ...],
    short_to_real_gid: dict[str, str],
    expected_short_cids_by_gid: dict[str, tuple[str, ...]],
    short_to_real_cid_by_gid: dict[str, dict[str, str]],
) -> dict[str, object]:
    """Deterministically restore short IDs to exact original SHA256 IDs; reject any mismatch."""
    if (type(data) is not dict
            or set(data) != {"batch_id", "source_fingerprint", "groups"}
            or data["batch_id"] != short_batch_id
            or data["source_fingerprint"] != short_fp
            or type(data["groups"]) is not list):
        raise V2DError("short-ID batch envelope differs")
    seen_gids: set[str] = set()
    obs_short_gids: list[str] = []
    for row in data["groups"]:
        if type(row) is not dict or type(row.get("group_id")) is not str:
            raise V2DError("short-ID batch group entry invalid")
        sgid = row["group_id"]
        if sgid not in short_to_real_gid or sgid in seen_gids:
            raise V2DError("short-ID batch group reference is unknown or duplicated")
        seen_gids.add(sgid)
        obs_short_gids.append(sgid)
    if tuple(obs_short_gids) != expected_short_gids:
        raise V2DError("short-ID batch group coverage/order differs")

    restored_groups = []
    for row in data["groups"]:
        sgid = row["group_id"]
        real_gid = short_to_real_gid[sgid]
        c_decs = row.get("candidate_decisions")
        if type(c_decs) is not list:
            raise V2DError("short-ID batch candidate_decisions invalid")
        c_map = short_to_real_cid_by_gid[real_gid]
        seen_cids: set[str] = set()
        obs_short_cids: list[str] = []
        restored_c_decs = []
        for cd in c_decs:
            if type(cd) is not dict or type(cd.get("candidate_id")) is not str:
                raise V2DError("short-ID batch candidate_decision entry invalid")
            scid = cd["candidate_id"]
            if scid not in c_map or scid in seen_cids:
                raise V2DError("short-ID batch candidate reference is unknown, cross-group, or duplicated")
            seen_cids.add(scid)
            obs_short_cids.append(scid)
            restored_cd = dict(cd)
            restored_cd["candidate_id"] = c_map[scid]
            restored_c_decs.append(restored_cd)
        if tuple(obs_short_cids) != expected_short_cids_by_gid[real_gid]:
            raise V2DError("short-ID batch candidate coverage/order differs")
        restored_row = dict(row)
        restored_row["group_id"] = real_gid
        restored_row["candidate_decisions"] = restored_c_decs
        restored_groups.append(restored_row)

    return {
        "batch_id": real_batch_id,
        "source_fingerprint": real_fp,
        "groups": restored_groups,
    }


def _adjudicate_group_batches(
    payloads: tuple[tuple[str, dict[str, object]], ...], *,
    expected_groups: dict[str, object], source_fingerprint: str,
    invoke: Callable, hermes_settings: HermesExecutionSettings,
    task: Path, label: str, reuse_only: bool,
    instruction: str = SEMANTIC_BATCH_ADJUDICATION_INSTRUCTION,
    allow_limited_json_recovery: bool = False,
    recovery_log: list[dict[str, object]] | None = None,
    use_short_id_mapping_for_uncached: bool = False,
) -> tuple[tuple[GroupAdjudication, ...], tuple[V2DBatchEvidence, ...]]:
    batches = _pack_group_batches(source_fingerprint, payloads, instruction=instruction)
    resolved_by_id = {}
    receipts = []
    owner = getattr(invoke, "_v2d_native_owner", getattr(invoke, "__self__", None))
    for batch, batch_id, input_raw, prompt in batches:
        expected_ids = tuple(group_id for group_id, _ in batch)
        if set(expected_ids) - set(expected_groups):
            raise V2DError("batch references an unknown source group")
        try:
            batch_dir = _private_child(task, "batch-" + batch_id, create=not reuse_only)
        except V2DError as error:
            if reuse_only:
                raise V2DHold("GROUP_BATCH_RESUME_STAGE_MISSING") from error
            raise

        def validate_batch(raw, *, expected_ids=expected_ids, batch_id=batch_id, label=label):
            recovery_record = None
            if allow_limited_json_recovery:
                data, recovery_record = recover_limited_trailing_json(raw, "JA Master batch adjudication")
            else:
                data = _load_json(raw, "JA Master batch adjudication")
            if (type(data) is not dict or set(data) != {"batch_id", "source_fingerprint", "groups"}
                    or data["batch_id"] != batch_id
                    or data["source_fingerprint"] != source_fingerprint
                    or type(data["groups"]) is not list):
                raise V2DError("JA Master batch envelope differs")
            observed = tuple(item.get("group_id") if type(item) is dict else None
                             for item in data["groups"])
            if observed != expected_ids:
                raise V2DError("JA Master batch group coverage/order differs")
            group_results = []
            for row, group_id in zip(data["groups"], expected_ids, strict=True):
                parsed = _parse_group_response(
                    _wire(row), SimpleNamespace(group_id=group_id), require_audio_flag=True,
                )
                group = expected_groups[group_id]
                if (tuple(item.candidate_id for item in parsed.candidate_decisions)
                        != tuple(group.candidate_ids)
                        or tuple(item.source_key for item in parsed.source_decisions)
                        != tuple(member.source_reference.key for member in group.members)):
                    raise V2DError("JA Master batch candidate/source coverage differs")
                _validate_group_source_spans(group, parsed)
                group_results.append(parsed)
            if recovery_record is not None and recovery_log is not None:
                recovery_log.append({
                    **recovery_record,
                    "batch_id": batch_id,
                    "label": label,
                    "source_fingerprint": source_fingerprint,
                    "group_count": len(group_results),
                })
            return tuple(group_results)

        has_existing_receipts = any(batch_dir.glob(f"{label}-attempt-*.receipt.json"))
        active_prompt = prompt
        active_input_raw = input_raw
        active_validator = validate_batch
        use_short_for_this_batch = False
        short_mat = None
        if use_short_id_mapping_for_uncached:
            short_mat = _build_short_id_batch_material(
                batch, batch_id=batch_id, source_fingerprint=source_fingerprint,
                instruction=instruction,
            )
            if not has_existing_receipts and not reuse_only:
                use_short_for_this_batch = True
            elif has_existing_receipts:
                first_prompt_path = batch_dir / f"{label}-attempt-1.prompt.txt"
                if first_prompt_path.is_file() and first_prompt_path.read_bytes() == short_mat["prompt"]:
                    use_short_for_this_batch = True
        if use_short_for_this_batch and short_mat is not None:
            active_prompt = short_mat["prompt"]
            active_input_raw = short_mat["input_raw"]

            def validate_short_batch(
                raw,
                *,
                _short_mat=short_mat,
                _batch_id=batch_id,
                _validate_batch=validate_batch,
                _label=label,
            ):
                recovery_record = None
                if allow_limited_json_recovery:
                    data, recovery_record = recover_limited_trailing_json(raw, "JA Master batch adjudication")
                else:
                    data = _load_json(raw, "JA Master batch adjudication")
                restored = _restore_short_id_batch_response(
                    data,
                    short_batch_id=_short_mat["short_batch_id"],
                    short_fp=_short_mat["short_fp"],
                    real_batch_id=_batch_id,
                    real_fp=source_fingerprint,
                    expected_short_gids=_short_mat["expected_short_gids"],
                    short_to_real_gid=_short_mat["short_to_real_gid"],
                    expected_short_cids_by_gid=_short_mat["expected_short_cids_by_gid"],
                    short_to_real_cid_by_gid=_short_mat["short_to_real_cid_by_gid"],
                )
                results = _validate_batch(_wire(restored))
                if recovery_record is not None and recovery_log is not None:
                    recovery_log.append({
                        **recovery_record,
                        "batch_id": _batch_id,
                        "label": _label,
                        "source_fingerprint": source_fingerprint,
                        "group_count": len(results),
                        "short_id_mapped": True,
                    })
                return results

            active_validator = validate_short_batch

        before = len(getattr(owner, "_verified_attempts", ()))
        resolved = invoke(
            active_prompt, batch_dir, label, active_validator,
            hermes_settings=hermes_settings, reuse_only=reuse_only,
        )
        if type(resolved) is not tuple or tuple(item.group_id for item in resolved) != expected_ids:
            raise V2DError("group batch executor returned invalid coverage")
        receipts_after = tuple(getattr(owner, "_verified_attempts", ()))
        receipt_hashes = tuple(item["receipt_sha256"] for item in receipts_after[before:]
                               if item.get("label") == label
                               and type(item.get("receipt_sha256")) is str)
        receipts.append(V2DBatchEvidence(
            batch_id=batch_id, source_fingerprint=source_fingerprint,
            group_ids=expected_ids, input_sha256=_sha(active_input_raw),
            prompt_sha256=_sha(active_prompt), native_receipt_sha256=receipt_hashes,
        ))
        for item in resolved:
            if item.group_id in resolved_by_id:
                raise V2DError("group was adjudicated in more than one batch")
            resolved_by_id[item.group_id] = item
    expected_all = tuple(group_id for group_id, _ in payloads)
    if tuple(group_id for group_id, _ in payloads if group_id in resolved_by_id) != expected_all:
        raise V2DError("group batches omitted a source group")
    return tuple(resolved_by_id[group_id] for group_id in expected_all), tuple(receipts)


def adjudicate_ja_master(
    plan: UtteranceReviewPlan,
    *,
    invoke: Callable,
    hermes_settings: HermesExecutionSettings,
    staging_root: str | Path,
    claim_token: int,
    reuse_only: bool = False,
    batch_groups: bool | None = None,
    exclude_group_ids: tuple[str, ...] = (),
    supplemental_groups: tuple[UtteranceReviewGroup, ...] = (),
) -> V2DAdjudication:
    """Run source-bound adjudication, batching Native-backed title requests."""
    plan = validate_utterance_review_plan(plan)
    if type(hermes_settings) is not HermesExecutionSettings:
        raise V2DError("resolved Hermes profile settings are required")
    if type(claim_token) is not int or claim_token < 1:
        raise V2DError("claim token is invalid")
    root = _private_dir(staging_root)
    excluded = set(exclude_group_ids)
    effective_groups = tuple(g for g in plan.groups if g.group_id not in excluded) + tuple(supplemental_groups)
    fingerprint = _source_fingerprint(
        plan, exclude_group_ids=exclude_group_ids, supplemental_groups=supplemental_groups,
    )
    session = str(uuid.uuid5(V2D_SESSION_NAMESPACE, fingerprint + ":" + str(claim_token)))
    task = _private_child(root, session, create=not reuse_only)
    if batch_groups is None:
        batch_groups = getattr(invoke, "_v2d_native_owner", None) is not None
    if type(batch_groups) is not bool:
        raise V2DError("batch_groups must be boolean when specified")
    if batch_groups:
        payloads = tuple(
            (group.group_id, _group_payload(plan, group, source_fingerprint=fingerprint))
            for group in effective_groups
        )
        groups, evidence = _adjudicate_group_batches(
            payloads, expected_groups={group.group_id: group for group in effective_groups},
            source_fingerprint=fingerprint, invoke=invoke,
            hermes_settings=hermes_settings, task=task,
            label="ja-master-adjudication-batch", reuse_only=reuse_only,
        )
        return validate_adjudication(
            plan, V2DAdjudication(fingerprint, groups, evidence),
            exclude_group_ids=exclude_group_ids, supplemental_groups=supplemental_groups,
        )
    results = []
    for group in effective_groups:
        payload = _wire(_group_payload(plan, group, source_fingerprint=fingerprint))
        prompt = (SEMANTIC_ADJUDICATION_INSTRUCTION + "\nSOURCE_BOUND_GROUP=" + payload.decode("utf-8")).encode("utf-8")
        if len(prompt) > V2D_MAX_PROMPT_BYTES:
            raise V2DError("one utterance group exceeds the existing native prompt bound")
        group_dir = _private_child(task, "group-" + group.group_id.removeprefix("group-")[:32], create=not reuse_only)
        def validator(raw, group=group):
            parsed = _parse_group_response(raw, group)
            _validate_group_source_spans(group, parsed)
            return parsed
        resolved = invoke(prompt, group_dir, "ja-master-adjudication", validator,
                          hermes_settings=hermes_settings, reuse_only=reuse_only)
        if type(resolved) is not GroupAdjudication:
            raise V2DError("semantic executor did not return a validated group response")
        results.append(resolved)
    return validate_adjudication(
        plan, V2DAdjudication(fingerprint, tuple(results)),
        exclude_group_ids=exclude_group_ids, supplemental_groups=supplemental_groups,
    )


def _validate_group_source_spans(
    group: UtteranceReviewGroup,
    decisions: GroupAdjudication,
) -> dict[str, list[tuple[int | None, int | None]]]:
    """Validate deterministic per-group source-span ownership and ASR word partitions.

    Reused at both the response-validation boundary (initial and targeted
    adjudication) and materialize_ja_master. Honest UNCERTAIN decisions and
    canonical-time HOLD checks remain enforced by materialize_ja_master.
    """
    member_by_key = {item.source_reference.key: item for item in group.members}
    decision_by_key = {item.source_key: item for item in decisions.source_decisions}
    if set(decision_by_key) != set(member_by_key):
        raise V2DError("source decision coverage changed")
    accepted = {key for key, item in decision_by_key.items() if item.status == DECISION_ACCEPTED}
    used: dict[str, list[tuple[int | None, int | None]]] = {key: [] for key in accepted}
    for proposal in decisions.outputs:
        source_keys = tuple(span.source_key for span in proposal.source_spans)
        if any(key not in accepted for key in source_keys):
            raise V2DError("output uses a rejected or unknown source")
        for span in proposal.source_spans:
            member = member_by_key[span.source_key]
            ref = member.source_reference
            if span.word_start_index is None:
                if used[span.source_key]:
                    raise V2DError("source appears in multiple outputs without a complete ASR word split")
            else:
                if ref.source not in {"asr_segment", EVIDENCE_SOURCE_SUPPLEMENTAL_ASR} or not member.word_references:
                    raise V2DError("only timed ASR words can own a split")
                if span.word_end_index > len(member.word_references):
                    raise V2DError("ASR split extends beyond source word references")
                selected_words = member.word_references[span.word_start_index:span.word_end_index]
                if len(selected_words) != span.word_end_index - span.word_start_index:
                    raise V2DError("ASR split word coverage is incomplete")
            used[span.source_key].append((span.word_start_index, span.word_end_index))
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
    return used


def _build_private_provisional_uncertainty_report(
    effective_groups: tuple[UtteranceReviewGroup, ...],
    adjudication: V2DAdjudication,
    targeted_evidence: _V2DTargetedEvidence | None = None,
) -> tuple[dict[str, object], ...]:
    """Build explicit audit records for groups with residual uncertainty after targeted ASR.

    Preserves original source texts, canonical/hypothesis timings, original
    audio_evidence_needed flag, source/candidate decisions, and rationales
    without altering or forcing any adjudication field.
    """
    targeted_by_group = dict(targeted_evidence.group_payloads) if targeted_evidence is not None else {}
    entries = []
    for group, decisions in zip(effective_groups, adjudication.groups, strict=True):
        has_uncertain_decision = any(
            item.status == DECISION_UNCERTAIN
            for item in (*decisions.candidate_decisions, *decisions.source_decisions)
        )
        if not decisions.audio_evidence_needed and not has_uncertain_decision:
            continue
        member_by_key = {m.source_reference.key: m for m in group.members}
        sources_report = []
        for sd in decisions.source_decisions:
            member = member_by_key[sd.source_key]
            ref = member.source_reference
            sources_report.append({
                "source_key": sd.source_key,
                "source": ref.source,
                "text": member.text,
                "aligned_start_ms": None if ref.aligned_start_ms is None else _fraction(ref.aligned_start_ms),
                "aligned_end_ms": None if ref.aligned_end_ms is None else _fraction(ref.aligned_end_ms),
                "status": sd.status,
                "rationale": sd.rationale,
                "provisional_master_disposition": (
                    "INCLUDED_SUPPORTED_ACCEPTED"
                    if sd.status == DECISION_ACCEPTED
                    else ("EXCLUDED_REJECTED" if sd.status == DECISION_REJECTED
                          else "EXCLUDED_UNRESOLVED_PRESERVED")
                ),
            })
        entries.append({
            "group_id": group.group_id,
            "original_audio_evidence_needed": decisions.audio_evidence_needed,
            "has_uncertain_decision": has_uncertain_decision,
            "retained_supported_output_count": len(decisions.outputs),
            "sources": sources_report,
            "candidate_decisions": [{
                "candidate_id": cd.candidate_id,
                "status": cd.status,
                "rationale": cd.rationale,
            } for cd in decisions.candidate_decisions],
            "targeted_second_evidence_present": group.group_id in targeted_by_group,
        })
    return tuple(entries)


def materialize_ja_master(
    plan: UtteranceReviewPlan,
    adjudication: V2DAdjudication,
    *,
    targeted_evidence_sha256: str | None = None,
    outside_span_recovery_sha256: str | None = None,
    exclude_group_ids: tuple[str, ...] = (),
    supplemental_groups: tuple[UtteranceReviewGroup, ...] = (),
    allow_private_provisional_unresolved: bool = False,
) -> V2DMaster:
    """Resolve source ownership and exact time from validated semantic spans."""
    plan = validate_utterance_review_plan(plan)
    adjudication = validate_adjudication(
        plan, adjudication, exclude_group_ids=exclude_group_ids, supplemental_groups=supplemental_groups,
    )
    if targeted_evidence_sha256 is not None:
        _digest(targeted_evidence_sha256, "targeted_evidence_sha256")
    if outside_span_recovery_sha256 is not None:
        _digest(outside_span_recovery_sha256, "outside_span_recovery_sha256")
    unresolved_group_ids = tuple(
        group.group_id for group in adjudication.groups
        if (group.audio_evidence_needed
            or any(item.status == DECISION_UNCERTAIN
                   for item in (*group.candidate_decisions, *group.source_decisions)))
    )
    if any(item.status == DECISION_UNCERTAIN for group in adjudication.groups
           for item in (*group.candidate_decisions, *group.source_decisions)):
        if not allow_private_provisional_unresolved:
            raise V2DHold("JA_MASTER_UNRESOLVED")
    excluded = set(exclude_group_ids)
    effective_groups = tuple(g for g in plan.groups if g.group_id not in excluded) + tuple(supplemental_groups)
    cues = []
    for group, decisions in zip(effective_groups, adjudication.groups, strict=True):
        _validate_group_source_spans(group, decisions)
        member_by_key = {item.source_reference.key: item for item in group.members}
        decision_by_key = {item.source_key: item for item in decisions.source_decisions}
        accepted = {key for key, item in decision_by_key.items() if item.status == DECISION_ACCEPTED}
        pending = []
        for output_index, proposal in enumerate(decisions.outputs):
            starts, ends, refs, evidence_ids = [], [], [], []
            for span in proposal.source_spans:
                member = member_by_key[span.source_key]
                ref = member.source_reference
                if ref.aligned_start_ms is None or ref.aligned_end_ms is None:
                    raise V2DHold("ACCEPTED_SOURCE_HAS_NO_CANONICAL_TIME")
                if span.word_start_index is None:
                    start, end = ref.aligned_start_ms, ref.aligned_end_ms
                else:
                    selected_words = member.word_references[span.word_start_index:span.word_end_index]
                    start, end = selected_words[0].start_ms, selected_words[-1].end_ms
                starts.append(start); ends.append(end); refs.append(ref)
                evidence_ids.extend(link.turn.turn_id for link in member.speaker_links)
                for word in member.word_references:
                    evidence_ids.extend(link.turn.turn_id for link in word.speaker_links)
            pending.append((min(starts), max(ends), proposal, tuple(refs), tuple(sorted(set(evidence_ids))), output_index))
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
    fingerprint = _source_fingerprint(
        plan, exclude_group_ids=exclude_group_ids, supplemental_groups=supplemental_groups,
    )
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
    provisional_ids = unresolved_group_ids if allow_private_provisional_unresolved else ()
    return V2DMaster(
        plan.review_set, plan, adjudication, tuple(cues), fingerprint,
        _sha(_wire(identity)), targeted_evidence_sha256,
        outside_span_recovery_sha256, exclude_group_ids, supplemental_groups,
        provisional_ids,
    )


def _validate_master(master: V2DMaster) -> V2DMaster:
    if type(master) is not V2DMaster:
        raise V2DError("exact V2-D master is required")
    rebuilt = materialize_ja_master(
        master.utterance_plan, master.adjudication,
        targeted_evidence_sha256=master.targeted_evidence_sha256,
        outside_span_recovery_sha256=master.outside_span_recovery_sha256,
        exclude_group_ids=master.excluded_outside_span_group_ids,
        supplemental_groups=master.supplemental_groups,
        allow_private_provisional_unresolved=bool(master.provisional_unresolved_group_ids),
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
               for group in (*master.utterance_plan.groups, *master.supplemental_groups)
               for member in group.members}
    cues = []
    for index, cue in enumerate(master.cues):
        asr_texts = [members[ref.key].text for ref in cue.source_references
                     if ref.source in {"asr_segment", EVIDENCE_SOURCE_SUPPLEMENTAL_ASR}]
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


def _is_correlated_uncorroborated_repeat(
    left_text: str,
    right_text: str,
    *,
    left_has_ext: bool,
    right_has_ext: bool,
    right_doc_freq: int,
    right_consec_run: int,
) -> bool:
    if left_has_ext or right_has_ext:
        return False
    left_norm = normalize_japanese_for_matching(left_text)
    right_norm = normalize_japanese_for_matching(right_text)
    if len(left_norm) < 3 or len(right_norm) < 4:
        return False
    if right_doc_freq < 3 and right_consec_run < 3:
        return False
    return (
        left_norm == right_norm
        or right_norm.startswith(left_norm)
        or left_norm.startswith(right_norm)
    )


def _cue_asr_quality_context(
    master: V2DMaster,
) -> tuple[dict[str, dict[str, object]], dict[str, ASRSourceQualityHint]]:
    """Compute source-bound recurrence, isolation, timing-skew, and dup signals."""
    baseline_asr = master.review_set._source_bundle.asr_result
    baseline_segs = baseline_asr.segments
    decisions = classify_asr_result_source_quality(baseline_asr)
    intervals = [(_round_ms(c.start_ms), _round_ms(c.end_ms)) for c in master.cues]
    baseline_index_to_cue = {}
    for idx, mc in enumerate(master.cues):
        for ref in mc.source_references:
            if ref.source == "asr_segment":
                baseline_index_to_cue.setdefault(ref.source_index, (idx, mc))

    signals_by_cue: dict[str, dict[str, object]] = {}
    hints_by_cue: dict[str, ASRSourceQualityHint] = {}
    for idx, mc in enumerate(master.cues):
        has_ext_ja = any(ref.source == "external_ja" for ref in mc.source_references)
        asr_refs = [ref for ref in mc.source_references if ref.source == "asr_segment"]
        sup_refs = [ref for ref in mc.source_references if ref.source == EVIDENCE_SOURCE_SUPPLEMENTAL_ASR]
        clean_len = len(normalize_japanese_for_matching(mc.text))

        max_doc_freq = 0
        max_consec_run = 0
        feat_set: set[str] = set()
        selected_hint: ASRSourceQualityHint | None = None
        max_word_ms = 0
        min_word_ms: int | None = None
        word_count = 0
        word_texts: list[str] = []
        word_truncated = False

        for ref in asr_refs:
            d = decisions[ref.source_index]
            seg = baseline_segs[ref.source_index]
            max_doc_freq = max(max_doc_freq, d.evidence.document_frequency)
            max_consec_run = max(max_consec_run, d.evidence.consecutive_run_length)
            feat_set.update(d.features)
            if selected_hint is None and (d.features or d.action != "KEEP"):
                selected_hint = ASRSourceQualityHint.from_decision(d)
            if seg.words:
                w_joined = "".join(w.text for w in seg.words)
                word_texts.append(w_joined)
                seg_norm = normalize_japanese_for_matching(seg.text)
                w_norm = normalize_japanese_for_matching(w_joined)
                if seg_norm and w_norm and len(w_norm) + 3 <= len(seg_norm) and seg_norm.startswith(w_norm):
                    word_truncated = True
                for w in seg.words:
                    dur = w.end_ms - w.start_ms
                    word_count += 1
                    max_word_ms = max(max_word_ms, dur)
                    min_word_ms = dur if min_word_ms is None else min(min_word_ms, dur)

        if selected_hint is not None:
            hints_by_cue[mc.cue_id] = selected_hint

        prev_gap_ms = None if idx == 0 else max(0, intervals[idx][0] - intervals[idx - 1][1])
        next_gap_ms = None if idx + 1 >= len(intervals) else max(0, intervals[idx + 1][0] - intervals[idx][1])

        has_recurrence = (max_consec_run >= 3) or (max_doc_freq >= 3 and clean_len >= 4)
        is_isolated = (not has_ext_ja) and (
            (prev_gap_ms is not None and prev_gap_ms >= 30_000)
            or (next_gap_ms is not None and next_gap_ms >= 30_000)
        )
        has_word_skew = (not has_ext_ja) and bool(word_count) and (
            word_truncated
            or max_word_ms >= 1500
            or (word_count >= 3 and min_word_ms is not None and min_word_ms <= 30 and max_word_ms >= 500)
        )

        sup_dup = None
        if sup_refs:
            ov = _match_supplemental_baseline_overlap(
                intervals[idx][0], intervals[idx][1], mc.text, baseline_segs,
            )
            if ov is not None:
                sup_dup = dict(ov)
                counterpart = baseline_index_to_cue.get(ov["baseline_source_index"])
                if counterpart is not None:
                    sup_dup["counterpart_cue_id"] = counterpart[1].cue_id
                    sup_dup["counterpart_text"] = counterpart[1].text

        if has_recurrence or is_isolated or (has_word_skew and (has_recurrence or is_isolated)) or sup_dup is not None:
            entry: dict[str, object] = {"ext_ja": has_ext_ja}
            if has_recurrence or feat_set:
                entry["asr_recurrence"] = {
                    "doc_freq": max_doc_freq,
                    "consec_run": max_consec_run,
                    "features": sorted(feat_set),
                }
            if is_isolated or has_recurrence:
                entry["isolation_gaps_ms"] = {"prev": prev_gap_ms, "next": next_gap_ms}
            if has_word_skew:
                entry["word_timing_anomaly"] = {
                    "max_ms": max_word_ms,
                    "min_ms": min_word_ms,
                    "word_text": "".join(word_texts)[:64],
                }
            if sup_dup is not None:
                entry["supplemental_duplicate_candidate"] = sup_dup
            signals_by_cue[mc.cue_id] = entry
    return signals_by_cue, hints_by_cue


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
                     for group in (*master.utterance_plan.groups, *master.supplemental_groups)
                     for member in group.members}
    baseline_decisions = classify_asr_result_source_quality(master.review_set._source_bundle.asr_result)
    _, hints_by_cue = _cue_asr_quality_context(master)
    cue_has_ext = [any(ref.source == "external_ja" for ref in c.source_references) for c in master.cues]
    cue_doc_stats = []
    for c in master.cues:
        dfs = [baseline_decisions[r.source_index].evidence.document_frequency
               for r in c.source_references if r.source == "asr_segment"]
        runs = [baseline_decisions[r.source_index].evidence.consecutive_run_length
                for r in c.source_references if r.source == "asr_segment"]
        cue_doc_stats.append((max(dfs, default=0), max(runs, default=0)))

    review_cues = []
    for index, (master_cue, output) in enumerate(zip(master.cues, validated.cues, strict=True)):
        asr_texts = [member_by_key[ref.key].text for ref in master_cue.source_references
                     if ref.source in {"asr_segment", EVIDENCE_SOURCE_SUPPLEMENTAL_ASR}]
        supporting = " / ".join(asr_texts) if asr_texts else None
        before = tuple(
            " / ".join(member_by_key[ref.key].text for ref in master.cues[ni].source_references
                       if ref.source in {"asr_segment", EVIDENCE_SOURCE_SUPPLEMENTAL_ASR})
            for ni in range(max(0, index - 2), index)
            if (any(ref.source in {"asr_segment", EVIDENCE_SOURCE_SUPPLEMENTAL_ASR}
                    for ref in master.cues[ni].source_references)
                and not _is_correlated_uncorroborated_repeat(
                    master_cue.text, master.cues[ni].text,
                    left_has_ext=cue_has_ext[index], right_has_ext=cue_has_ext[ni],
                    right_doc_freq=cue_doc_stats[ni][0], right_consec_run=cue_doc_stats[ni][1],
                ))
        )
        after = tuple(
            " / ".join(member_by_key[ref.key].text for ref in master.cues[ni].source_references
                       if ref.source in {"asr_segment", EVIDENCE_SOURCE_SUPPLEMENTAL_ASR})
            for ni in range(index + 1, min(len(master.cues), index + 3))
            if (any(ref.source in {"asr_segment", EVIDENCE_SOURCE_SUPPLEMENTAL_ASR}
                    for ref in master.cues[ni].source_references)
                and not _is_correlated_uncorroborated_repeat(
                    master_cue.text, master.cues[ni].text,
                    left_has_ext=cue_has_ext[index], right_has_ext=cue_has_ext[ni],
                    right_doc_freq=cue_doc_stats[ni][0], right_consec_run=cue_doc_stats[ni][1],
                ))
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
            asr_source_quality=hints_by_cue.get(master_cue.cue_id),
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


V2D_REVIEW_HALLUCINATION_AND_DEDUP_ADDENDUM = (
    "\nV2D_EVIDENCE_DISCIPLINE: Do NOT delete or repair cues based solely on a specific phrase, recurrence count, "
    "or external_ja absence. However, note that raw_asr_context comes from adjacent cues in this same transcript, "
    "NOT an independent audio pass: never treat adjacent identical uncorroborated ASR repeats as confirming speech "
    "or use them to REPAIR a truncated fragment into boilerplate. When ja_master_source_summary provides "
    "asr_signals (doc_freq/consec_run without external_ja, long isolation_gaps_ms, word_timing_anomaly), treat them "
    "together conservatively: only classify uncorroborated non-speech-gap boilerplate as OMIT/SOURCE_NOISE when combined "
    "evidence outweighs real-speech plausibility; otherwise preserve plausible greetings/farewells/short reactions via KEEP "
    "or AMBIGUOUS (note audio verification unresolved in reason). If supplemental_duplicate_candidate (sup_dup) shows a "
    "supplemental_asr cue matching a retained baseline counterpart cue on high time containment and wording as the same single "
    "utterance, classify only the redundant supplemental duplicate as OMIT/SOURCE_NOISE while keeping its retained baseline "
    "counterpart; preserve distinct speakers, short interjections, overlapping turns, and genuine repeated dialogue."
)


def _review_source_manifest(
    master: V2DMaster,
    *,
    signals_by_cue: dict[str, dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    rows = []
    for cue in master.cues:
        entry = {
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
        }
        if signals_by_cue and cue.cue_id in signals_by_cue:
            entry["asr_signals"] = signals_by_cue[cue.cue_id]
        rows.append(entry)
    return rows


def _review_prompt(request: QualityReviewRequest, master: V2DMaster,
                   *, target_cue_ids: tuple[str, ...] | None,
                   signals_by_cue: dict[str, dict[str, object]] | None = None) -> bytes:
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
    query += V2D_REVIEW_HALLUCINATION_AND_DEDUP_ADDENDUM
    payload = {
        "request": json.loads(serialize_review_request(request)),
        "request_sha256": review_request_sha256(request),
        "ja_master_source_manifest": _review_source_manifest(master, signals_by_cue=signals_by_cue),
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


SHORT_REVIEW_ID_ADDENDUM = (
    "\nUse the exact short cue_id identifiers provided in V2D_SOURCE_BOUND_INPUT "
    "(such as Q001) verbatim in exact order without altering, omitting, or duplicating any cue_id. "
    "Return ONLY the exact top-level fields schema_version (2), request_sha256 (\"REQ-SHORT\"), and cues. "
    "Output pretty-printed JSON with standard indentation."
)


def _build_short_id_review_chunk_prompt(
    request: QualityReviewRequest,
    master: V2DMaster,
    *,
    cue_indices: tuple[int, ...],
    target_indices: tuple[int, ...] | None,
    real_to_short: dict[str, str],
    signals_by_cue: dict[str, dict[str, object]] | None = None,
) -> bytes:
    from teddy_discovery_stateful_quality_review_runner import QUALITY_REVIEW_QUERY
    query = QUALITY_REVIEW_QUERY.replace(
        "Review EVERY cue in source order, including source-quality KEEP.",
        "Review every Japanese Master cue in this chunk in source order, including non-filtering KEEP hints.",
    ).replace("external JA", "Japanese Master").replace("External JA", "Japanese Master")
    target_short_ids = None
    if target_indices is not None:
        target_short_ids = [real_to_short[request.cues[i].cue_id] for i in target_indices]
        query = query.replace(
            "Review every Japanese Master cue in this chunk in source order, including non-filtering KEEP hints.",
            "Read every cue in this chunk for context; adjudicate only the caller target cue IDs.",
        ).replace(
            "Return exactly the same cue IDs, count and order;",
            "Return exactly the caller target cue IDs, count and order;",
        )
        query += "\nV2D_TARGET_ONLY: Preserve every non-target first-pass value. Targets in order: " + json.dumps(target_short_ids)
    query += V2D_REVIEW_HALLUCINATION_AND_DEDUP_ADDENDUM
    req_dict = json.loads(serialize_review_request(request))
    chunk_cues = []
    chunk_manifest = []
    for i in cue_indices:
        c = dict(req_dict["cues"][i])
        mc = master.cues[i]
        sid = real_to_short[mc.cue_id]
        c["cue_id"] = sid
        chunk_cues.append(c)
        manifest_row: dict[str, object] = {
            "cue_id": sid,
            "speaker_status": mc.speaker_status,
            "source_keys": [ref.key for ref in mc.source_references],
            "aligned_interval_ms": [_fraction(mc.start_ms), _fraction(mc.end_ms)],
        }
        if signals_by_cue and mc.cue_id in signals_by_cue:
            sig = json.loads(json.dumps(signals_by_cue[mc.cue_id]))
            dup = sig.get("supplemental_duplicate_candidate")
            if isinstance(dup, dict) and dup.get("counterpart_cue_id") in real_to_short:
                dup["counterpart_cue_id"] = real_to_short[dup["counterpart_cue_id"]]
            manifest_row["asr_signals"] = sig
        chunk_manifest.append(manifest_row)
    payload = {
        "schema_version": 2,
        "request_sha256": "REQ-SHORT",
        "cues": chunk_cues,
        "ja_master_source_summary": chunk_manifest,
        "target_cue_ids": target_short_ids,
        "source_quality_field_note": "Legacy compatibility field only; KEEP/no_quality_objection is a neutral placeholder, not a classifier verdict.",
    }
    return (query + SHORT_REVIEW_ID_ADDENDUM + "\nV2D_SOURCE_BOUND_INPUT=" + _wire(payload).decode("utf-8")).encode("utf-8")


def _restore_short_id_review_payload(
    raw: bytes,
    *,
    request: QualityReviewRequest,
    expected_short_ids: tuple[str, ...],
    short_to_real: dict[str, str],
    allow_limited_json_recovery: bool = False,
) -> bytes:
    if allow_limited_json_recovery:
        data, _ = recover_limited_trailing_json(raw, "V2-D quality review")
    else:
        data = _load_json(raw, "V2-D quality review")
    if type(data) is not dict or type(data.get("cues")) is not list:
        raise V2DError("short-ID review response envelope is invalid")
    seen: set[str] = set()
    obs_short: list[str] = []
    restored_cues = []
    for row in data["cues"]:
        if type(row) is not dict or type(row.get("cue_id")) is not str:
            raise V2DError("short-ID review cue entry is invalid")
        sid = row["cue_id"]
        if sid not in short_to_real or sid in seen:
            raise V2DError("short-ID review cue_id is unknown or duplicated")
        seen.add(sid)
        obs_short.append(sid)
        restored_row = dict(row)
        restored_row["cue_id"] = short_to_real[sid]
        restored_cues.append(restored_row)
    if tuple(obs_short) != expected_short_ids:
        raise V2DError("short-ID review cue coverage/order differs")
    restored = dict(data)
    if restored.get("request_sha256") == "REQ-SHORT":
        restored["request_sha256"] = review_request_sha256(request)
    restored["cues"] = restored_cues
    return _wire(restored)


def _pack_short_id_review_chunks(
    request: QualityReviewRequest,
    master: V2DMaster,
    real_to_short: dict[str, str],
    *,
    signals_by_cue: dict[str, dict[str, object]] | None = None,
) -> tuple[tuple[tuple[int, ...], bytes], ...]:
    chunks: list[tuple[tuple[int, ...], bytes]] = []
    pending: list[int] = []
    pending_prompt: bytes | None = None
    for idx in range(len(request.cues)):
        candidate = tuple(pending + [idx])
        prompt = _build_short_id_review_chunk_prompt(
            request, master, cue_indices=candidate, target_indices=None,
            real_to_short=real_to_short, signals_by_cue=signals_by_cue,
        )
        if len(prompt) <= V2D_MAX_PROMPT_BYTES:
            pending.append(idx)
            pending_prompt = prompt
        else:
            if not pending or pending_prompt is None:
                raise V2DError("single review cue exceeds the existing native prompt bound")
            chunks.append((tuple(pending), pending_prompt))
            single_prompt = _build_short_id_review_chunk_prompt(
                request, master, cue_indices=(idx,), target_indices=None,
                real_to_short=real_to_short, signals_by_cue=signals_by_cue,
            )
            if len(single_prompt) > V2D_MAX_PROMPT_BYTES:
                raise V2DError("single review cue exceeds the existing native prompt bound")
            pending = [idx]
            pending_prompt = single_prompt
    if pending and pending_prompt is not None:
        chunks.append((tuple(pending), pending_prompt))
    return tuple(chunks)


def run_targeted_review(
    master: V2DMaster,
    package: StatefulSubtitlePackage,
    first_pass: StatefulSubtitleResult,
    *,
    invoke: Callable,
    hermes_settings: HermesExecutionSettings,
    staging_root: str | Path,
    reuse_only: bool = False,
    extra_target_cue_ids: tuple[str, ...] = (),
    allow_limited_json_recovery: bool = False,
) -> V2DReviewOutcome:
    """Run existing full-title triage, then existing bounded suspect review."""
    if type(hermes_settings) is not HermesExecutionSettings:
        raise V2DError("resolved Hermes profile settings are required")
    master = _validate_master(master)
    request = build_v2d_review_request(master, package, first_pass)
    signals_by_cue, _ = _cue_asr_quality_context(master)
    signal_suspect_ids = {
        cid for cid, sig in signals_by_cue.items()
        if "asr_recurrence" in sig or "supplemental_duplicate_candidate" in sig
    }
    root = _private_dir(staging_root)
    request_sha = review_request_sha256(request)
    request_dir = _private_child(root, request_sha, create=not reuse_only)
    triage_dir = _private_child(request_dir, "triage", create=not reuse_only)
    triage_id = str(uuid.uuid5(V2D_SESSION_NAMESPACE, request_sha + ":triage"))
    use_chunked = False
    try:
        triage_prompt = _review_prompt(
            request, master, target_cue_ids=None, signals_by_cue=signals_by_cue,
        )
    except V2DError as error:
        if "exceeds the existing native prompt bound" not in str(error):
            raise
        use_chunked = True
        triage_prompt = b""

    if not use_chunked:
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
        combined = set(target_ids) | set(extra_target_cue_ids) | signal_suspect_ids
        if combined:
            target_ids = tuple(cue.cue_id for cue in request.cues if cue.cue_id in combined)
        if not target_ids:
            final = triage
        else:
            final_dir = _private_child(request_dir, "targeted-final", create=not reuse_only)
            final_id = str(uuid.uuid5(V2D_SESSION_NAMESPACE, request_sha + ":targeted-final"))
            final_prompt = _review_prompt(
                request, master, target_cue_ids=target_ids, signals_by_cue=signals_by_cue,
            )
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

    # Chunked short-ID fallback when whole-title review prompt exceeds 128KB bound.
    real_to_short = {cue.cue_id: f"Q{i + 1:03d}" for i, cue in enumerate(request.cues)}
    short_to_real = {short: real for real, short in real_to_short.items()}
    chunks = _pack_short_id_review_chunks(
        request, master, real_to_short, signals_by_cue=signals_by_cue,
    )
    merged_triage_cues = []
    for part_idx, (cue_indices, chunk_prompt) in enumerate(chunks, 1):
        chunk_dir = _private_child(triage_dir, f"chunk-{part_idx:02d}", create=not reuse_only)
        chunk_real_ids = tuple(request.cues[i].cue_id for i in cue_indices)
        chunk_short_ids = tuple(real_to_short[cid] for cid in chunk_real_ids)

        def validate_chunk(raw, *, _sids=chunk_short_ids, _rids=chunk_real_ids):
            restored = _restore_short_id_review_payload(
                raw, request=request, expected_short_ids=_sids, short_to_real=short_to_real,
                allow_limited_json_recovery=allow_limited_json_recovery,
            )
            return parse_review_result(restored, request, target_cue_ids=_rids)

        part_res = invoke(
            chunk_prompt, chunk_dir, f"v2d-triage-chunk-{part_idx:02d}",
            validate_chunk, hermes_settings=hermes_settings, reuse_only=reuse_only,
        )
        if type(part_res) is not QualityReviewResult:
            raise V2DError("chunked triage executor returned an invalid review result")
        merged_triage_cues.extend(part_res.cues)
    triage = QualityReviewResult(
        schema_version=2,
        request_sha256=request_sha,
        cues=tuple(merged_triage_cues),
        source_translation_session_id=None,
        review_execution_session_id=None,
    )
    triage = bind_review_execution_provenance(triage, request, triage_id)
    triage_raw = serialize_review_result(triage, request)
    target_ids = select_suspect_cue_ids(request, triage)
    combined = set(target_ids) | set(extra_target_cue_ids) | signal_suspect_ids
    if combined:
        target_ids = tuple(cue.cue_id for cue in request.cues if cue.cue_id in combined)
    if not target_ids:
        final = triage
    else:
        final_dir = _private_child(request_dir, "targeted-final", create=not reuse_only)
        final_id = str(uuid.uuid5(V2D_SESSION_NAMESPACE, request_sha + ":targeted-final"))
        id_to_index = {cue.cue_id: i for i, cue in enumerate(request.cues)}
        target_indices = tuple(id_to_index[cid] for cid in target_ids)
        ctx_indices_set: set[int] = set()
        for ti in target_indices:
            for ci in range(max(0, ti - 2), min(len(request.cues), ti + 3)):
                ctx_indices_set.add(ci)
        ctx_indices = tuple(sorted(ctx_indices_set))
        final_prompt = _build_short_id_review_chunk_prompt(
            request, master, cue_indices=ctx_indices, target_indices=target_indices,
            real_to_short=real_to_short, signals_by_cue=signals_by_cue,
        )
        if len(final_prompt) > V2D_MAX_PROMPT_BYTES:
            # Drop surrounding context if many targets; keep exact targets within bound.
            final_prompt = _build_short_id_review_chunk_prompt(
                request, master, cue_indices=target_indices, target_indices=target_indices,
                real_to_short=real_to_short, signals_by_cue=signals_by_cue,
            )
        if len(final_prompt) > V2D_MAX_PROMPT_BYTES:
            raise V2DError("targeted final review prompt exceeds the existing native prompt bound")
        target_short_ids = tuple(real_to_short[cid] for cid in target_ids)

        def validate_final(raw, *, _sids=target_short_ids, _rids=target_ids):
            restored = _restore_short_id_review_payload(
                raw, request=request, expected_short_ids=_sids, short_to_real=short_to_real,
                allow_limited_json_recovery=allow_limited_json_recovery,
            )
            return parse_review_result(restored, request, target_cue_ids=_rids)

        target_result = invoke(
            final_prompt, final_dir, "v2d-targeted-final-review",
            validate_final, hermes_settings=hermes_settings, reuse_only=reuse_only,
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
    hermes_attempts_started: int = 0
    targeted_asr_requests_started: int = 0
    elapsed_seconds: float = 0.0


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
    execution_limits: V2DExecutionLimits | None = None,
    outside_span_limits: OutsideSpanRecoveryLimits = OutsideSpanRecoveryLimits(),
    allow_limited_json_recovery: bool = False,
    private_provisional_completion: bool = False,
    use_short_id_mapping_for_uncached: bool = False,
    reuse_verified_translation: bool = False,
    preserve_legacy_supplemental_grouping: bool = False,
) -> V2DPipelineResult:
    """Connected offline/live-injectable V2-D path; never bypasses validators."""
    budget = None
    budget_token = None
    json_recovery_log: list[dict[str, object]] = []
    preserved_uncertainty_report: tuple[dict[str, object], ...] = ()
    preserved_translation_uncertainty_report: tuple[dict[str, object], ...] = ()
    try:
        requested_batching = getattr(invoke, "_v2d_batch_groups", None)
        invoke, executor_owner = _stage_bound_native_invoke(invoke, hermes_settings)
        if executor_owner is not None and execution_limits is None:
            return V2DPipelineResult("LIMIT_STOP", "EXECUTION_LIMITS_REQUIRED",
                                      None, None, None, None)
        if execution_limits is not None:
            budget = _V2DRunBudget(execution_limits)
            budget_token = _ACTIVE_V2D_BUDGET.set(budget)
            invoke = _budgeted_invoke(invoke, budget, executor_owner)
            invoke._v2d_batch_groups = (executor_owner is not None or requested_batching is True)
        verified_before = len(getattr(executor_owner, "_verified_attempts", ()))
        plan = validate_utterance_review_plan(plan)
        output = _private_dir(output_directory)
        collisions = [name for name in V2D_OUTPUT_NAMES if (output / name).exists() or (output / name).is_symlink()]
        if collisions:
            raise V2DError("V2-D output collision")
        batch_groups = executor_owner is not None or requested_batching is True
        active_groups, outside_span_groups = split_outside_span_groups(plan)
        excluded_outside_span_ids = tuple(g.group_id for g in outside_span_groups)
        outside_span_plan: OutsideSpanRecoveryPlan | None = None
        outside_span_recovery: OutsideSpanRecoveryResult | None = None
        supplemental_groups: tuple[UtteranceReviewGroup, ...] = ()
        if outside_span_groups:
            outside_span_plan = plan_outside_span_recovery(plan, limits=outside_span_limits)
            if outside_span_plan.exceeds_budget:
                raise V2DHold("OUTSIDE_SPAN_TARGETED_ASR_BUDGET_EXCEEDED")
            if outside_span_plan.windows:
                if budget is not None:
                    budget.require_time(reason="WALL_TIME_LIMIT_BEFORE_OUTSIDE_SPAN_TARGETED_ASR")
                outside_span_recovery = _load_or_run_outside_span_recovery(
                    outside_span_plan, targeted_runner=targeted_runner,
                    staging_root=staging_root, reuse_only=reuse_only,
                )
                if any(o.outcome != OUTSIDE_SPAN_OUTCOME_SPEECH_FOUND for o in outside_span_recovery.window_outcomes):
                    raise V2DHold("OUTSIDE_SPAN_SPEECH_UNRESOLVED")
                supplemental_groups = build_supplemental_asr_groups(
                    plan,
                    outside_span_recovery,
                    deduplicate_similar_overlaps=not preserve_legacy_supplemental_grouping,
                )
        effective_groups = active_groups + supplemental_groups
        adjudication = adjudicate_ja_master(
            plan, invoke=invoke, hermes_settings=hermes_settings,
            staging_root=staging_root, claim_token=claim_token, reuse_only=reuse_only,
            batch_groups=batch_groups,
            exclude_group_ids=excluded_outside_span_ids,
            supplemental_groups=supplemental_groups,
        )
        targeted_evidence = None
        initial_audio_groups = tuple(
            group.group_id for group, resolved in zip(effective_groups, adjudication.groups, strict=True)
            if resolved.audio_evidence_needed
        )
        if initial_audio_groups:
            supplemental_ids = {g.group_id for g in supplemental_groups}
            if any(gid in supplemental_ids for gid in initial_audio_groups):
                raise V2DHold("SUPPLEMENTAL_ASR_ADDITIONAL_AUDIO_UNSUPPORTED")
            initial_requests = _build_initial_targeted_requests(plan, initial_audio_groups)
            early_items = []
            for request in initial_requests:
                if budget is not None:
                    budget.require_time(reason="WALL_TIME_LIMIT_BEFORE_INITIAL_TARGETED_ASR")
                if type(request) is _V2DTargetedRequest:
                    early_items.append(_load_or_run_targeted_evidence(
                        request, targeted_runner=targeted_runner,
                        staging_root=staging_root, reuse_only=reuse_only,
                    ))
                else:
                    early_items.append(_load_or_run_external_targeted_evidence(
                        request, targeted_runner=targeted_runner,
                        staging_root=staging_root, reuse_only=reuse_only,
                    ))
            targeted_evidence = _combine_targeted_evidence(tuple(early_items))
            adjudication = _readjudicate_targeted_groups(
                plan, adjudication, targeted_evidence,
                invoke=invoke, hermes_settings=hermes_settings,
                staging_root=staging_root, claim_token=claim_token,
                reuse_only=reuse_only, batch_groups=batch_groups,
                exclude_group_ids=excluded_outside_span_ids,
                supplemental_groups=supplemental_groups,
                allow_limited_json_recovery=allow_limited_json_recovery,
                recovery_log=json_recovery_log,
                use_short_id_mapping_for_uncached=use_short_id_mapping_for_uncached,
            )
            if any(item.audio_evidence_needed for item in adjudication.groups):
                if not private_provisional_completion:
                    raise V2DHold("INITIAL_TARGETED_ASR_UNCERTAINTY_REMAINS")
        if private_provisional_completion:
            preserved_uncertainty_report = _build_private_provisional_uncertainty_report(
                effective_groups, adjudication, targeted_evidence,
            )
        master = materialize_ja_master(
            plan, adjudication,
            targeted_evidence_sha256=(None if targeted_evidence is None
                                      else targeted_evidence.linkage_sha256),
            outside_span_recovery_sha256=(None if outside_span_recovery is None
                                          else outside_span_recovery.artifact_sha256),
            exclude_group_ids=excluded_outside_span_ids,
            supplemental_groups=supplemental_groups,
            allow_private_provisional_unresolved=private_provisional_completion,
        )
        initial_translation_evidence = (None if targeted_evidence is None
                                        else _targeted_translation_evidence(master, targeted_evidence))
        package, translated = translate_ja_master(
            master, invoke=invoke, hermes_settings=hermes_settings,
            staging_root=staging_root, claim_token=claim_token,
            semantic_policy=semantic_policy, reuse_only=(reuse_only or reuse_verified_translation),
            targeted_evidence_by_cue=initial_translation_evidence,
            targeted_evidence_sha256=(targeted_evidence.linkage_sha256
                                      if targeted_evidence is not None and initial_translation_evidence else None),
        )
        post_translation_audio_cues = tuple(
            cue for cue in translated.cues
            if isinstance(cue, StatefulCueOutput) and cue.needs_audio_evidence
        )
        extra_review_cue_ids: tuple[str, ...] = ()
        if post_translation_audio_cues and private_provisional_completion:
            master_by_id = {cue.cue_id: cue for cue in master.cues}
            preserved_translation_uncertainty_report = tuple({
                "cue_id": cue.cue_id,
                "group_id": master_by_id[cue.cue_id].group_id,
                "ja_text": master_by_id[cue.cue_id].text,
                "first_pass_ko": getattr(cue, "ko", None),
                "repaired_ja": getattr(cue, "repaired_ja", None),
                "start_ms": _fraction(master_by_id[cue.cue_id].start_ms),
                "end_ms": _fraction(master_by_id[cue.cue_id].end_ms),
                "source_keys": [ref.key for ref in master_by_id[cue.cue_id].source_references],
                "original_needs_audio_evidence": True,
                "provisional_disposition": "PRESERVED_FOR_TARGETED_REVIEW_NO_LATE_ASR",
            } for cue in post_translation_audio_cues)
            extra_review_cue_ids = tuple(cue.cue_id for cue in post_translation_audio_cues)
        elif post_translation_audio_cues:
            requested_translation = translated
            if targeted_evidence is not None:
                covered_sources = {source_id for source_id, _, _ in targeted_evidence.source_window_evidence}
                master_by_id = {cue.cue_id: cue for cue in master.cues}
                filtered_cues = []
                for cue in translated.cues:
                    if not (isinstance(cue, StatefulCueOutput) and cue.needs_audio_evidence):
                        filtered_cues.append(cue)
                        continue
                    source_ids = {ref.source_id for ref in master_by_id[cue.cue_id].source_references}
                    targetable = {source_id for source_id in source_ids
                                  if source_id.startswith("asr_segment:")
                                  or source_id.startswith("external_ja:")}
                    if targetable and targetable.issubset(covered_sources):
                        filtered_cues.append(replace(cue, needs_audio_evidence=False))
                    else:
                        filtered_cues.append(cue)
                requested_translation = replace(translated, cues=tuple(filtered_cues))
                if not any(isinstance(cue, StatefulCueOutput) and cue.needs_audio_evidence
                           for cue in requested_translation.cues):
                    raise V2DHold("TARGETED_ASR_STILL_REQUIRED_AFTER_EARLY_EVIDENCE")
            targeted_requests = _build_targeted_requests(master, requested_translation)
            evidence_items = []
            for targeted_request in targeted_requests:
                if budget is not None:
                    budget.require_time(reason="WALL_TIME_LIMIT_BEFORE_TARGETED_ASR")
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
            later_evidence = _combine_targeted_evidence(tuple(evidence_items))
            targeted_evidence = (later_evidence if targeted_evidence is None else
                                 _combine_targeted_evidence((targeted_evidence, later_evidence)))
            adjudication = _readjudicate_targeted_groups(
                plan, adjudication, targeted_evidence,
                invoke=invoke, hermes_settings=hermes_settings,
                staging_root=staging_root, claim_token=claim_token,
                reuse_only=reuse_only, batch_groups=batch_groups,
                exclude_group_ids=excluded_outside_span_ids,
                supplemental_groups=supplemental_groups,
            )
            master = materialize_ja_master(
                plan, adjudication,
                targeted_evidence_sha256=targeted_evidence.linkage_sha256,
                outside_span_recovery_sha256=(None if outside_span_recovery is None
                                              else outside_span_recovery.artifact_sha256),
                exclude_group_ids=excluded_outside_span_ids,
                supplemental_groups=supplemental_groups,
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
            extra_target_cue_ids=extra_review_cue_ids,
            allow_limited_json_recovery=allow_limited_json_recovery,
        )
        ja_cues, ko_cues = _materialized_cues(master, translated, review)
        ja_raw, ko_generated = _srt_bytes(ja_cues), generate_korean_srt(ko_cues)
        if ko_generated.payload is None or ko_generated.cue_count != len(ko_cues):
            raise V2DError("Korean SRT generator returned no complete artifact")
        ko_raw = ko_generated.payload
        if parse_subtitle_bytes(ko_raw, "srt").cues != ko_cues:
            raise V2DError("Korean SRT failed round-trip validation")
        master_raw = _master_artifact_bytes(master)
        if budget is not None:
            budget.require_time(reason="WALL_TIME_LIMIT_BEFORE_FINAL_OUTPUT")
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
        is_private_provisional = bool(
            private_provisional_completion and (
                preserved_uncertainty_report
                or preserved_translation_uncertainty_report
                or json_recovery_log
            )
        ) or bool(json_recovery_log)
        result_state = "PRIVATE_PROVISIONAL_SRT_READY" if is_private_provisional else "CLEAN_SRT_READY"
        review_signals_by_cue, _ = _cue_asr_quality_context(master)
        review_dispositions = []
        for mc, req_c, rev_c in zip(master.cues, review.request.cues, review.final.cues, strict=True):
            eff_action = effective_review_action(req_c, rev_c)
            sig = review_signals_by_cue.get(mc.cue_id)
            if eff_action != KEEP or rev_c.action != KEEP or sig is not None:
                review_dispositions.append({
                    "cue_id": mc.cue_id,
                    "ja_text": mc.text,
                    "review_action": rev_c.action,
                    "effective_action": eff_action,
                    "category": rev_c.category,
                    "reason": rev_c.reason,
                    "has_asr_signals": sig is not None,
                    "asr_signals": sig,
                })
        uncertainty_report_raw = None
        if is_private_provisional:
            uncertainty_report_raw = _wire({
                "schema_version": V2D_SCHEMA_VERSION,
                "dvd_id": master.review_set.dvd_id,
                "state": result_state,
                "stage12_publish_eligible": False,
                "provisional_trial_only": True,
                "source_fingerprint": master.source_fingerprint,
                "master_sha256": master.master_sha256,
                "limited_json_recoveries": list(json_recovery_log),
                "preserved_unresolved_uncertainty": list(preserved_uncertainty_report),
                "preserved_post_translation_audio_requests": list(preserved_translation_uncertainty_report),
                "review_dispositions": review_dispositions,
            })
        proof_payload = {
            "schema_version": V2D_SCHEMA_VERSION,
            "dvd_id": master.review_set.dvd_id,
            "state": result_state,
            "source_fingerprint": master.source_fingerprint,
            "master_sha256": master.master_sha256,
            "targeted_asr_artifact_sha256": (None if targeted_evidence is None
                                               else targeted_evidence.artifact_sha256),
            "targeted_asr_linkage_sha256": (None if targeted_evidence is None
                                              else targeted_evidence.linkage_sha256),
            "targeted_readjudicated_group_count": (0 if targeted_evidence is None
                                                   else len(targeted_evidence.group_payloads)),
            "outside_span_recovery": (None if outside_span_plan is None else {
                "excluded_outside_span_group_ids": list(excluded_outside_span_ids),
                "assessments": [{
                    "group_id": a.group_id,
                    "source_key": a.source_reference.key,
                    "disposition": a.disposition,
                    "supporting_baseline_source_keys": list(a.supporting_baseline_source_keys),
                } for a in outside_span_plan.assessments],
                "recovery_artifact_sha256": (None if outside_span_recovery is None
                                             else outside_span_recovery.artifact_sha256),
                "supplemental_asr_group_ids": [g.group_id for g in supplemental_groups],
            }),
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
            "semantic_batches": [{
                "batch_id": item.batch_id,
                "source_fingerprint": item.source_fingerprint,
                "group_ids": list(item.group_ids),
                "input_sha256": item.input_sha256,
                "prompt_sha256": item.prompt_sha256,
                "native_receipt_sha256": list(item.native_receipt_sha256),
            } for item in adjudication.batch_evidence],
            "execution_limits": None if budget is None else budget.evidence(),
            "outputs": {
                V2D_OUTPUT_NAMES[0]: _sha(master_raw),
                V2D_OUTPUT_NAMES[1]: _sha(ja_raw),
                V2D_OUTPUT_NAMES[2]: _sha(ko_raw),
            },
        }
        if is_private_provisional:
            proof_payload["stage12_publish_eligible"] = False
            proof_payload["provisional_trial_only"] = True
            proof_payload["limited_json_recoveries"] = list(json_recovery_log)
            proof_payload["preserved_unresolved_uncertainty_count"] = len(preserved_uncertainty_report)
            proof_payload["preserved_post_translation_audio_request_count"] = len(preserved_translation_uncertainty_report)
            proof_payload["outputs"][V2D_PRIVATE_PROVISIONAL_UNCERTAINTY_FILENAME] = _sha(uncertainty_report_raw)
        proof_raw = _wire(proof_payload)
        output_names = (
            V2D_OUTPUT_NAMES + (V2D_PRIVATE_PROVISIONAL_UNCERTAINTY_FILENAME,)
            if is_private_provisional else V2D_OUTPUT_NAMES
        )
        payloads = (
            (master_raw, ja_raw, ko_raw, proof_raw, uncertainty_report_raw)
            if is_private_provisional else (master_raw, ja_raw, ko_raw, proof_raw)
        )
        # Check all names again before the first exclusive write.
        if any((output / name).exists() or (output / name).is_symlink() for name in output_names):
            raise V2DError("V2-D output collision")
        for name, raw in zip(output_names, payloads, strict=True):
            _write_exclusive(output / name, raw)
        hashes = tuple((name, _sha(raw)) for name, raw in zip(output_names, payloads, strict=True))
        return V2DPipelineResult(
            result_state, None, master, package, translated, review, hashes,
            0 if budget is None else budget.hermes_attempts,
            0 if budget is None else budget.targeted_asr_requests,
            0.0 if budget is None else round(budget.elapsed(), 6),
        )
    except V2DLimitStop as stop:
        return V2DPipelineResult(
            "LIMIT_STOP", str(stop), None, None, None, None, (),
            0 if budget is None else budget.hermes_attempts,
            0 if budget is None else budget.targeted_asr_requests,
            0.0 if budget is None else round(budget.elapsed(), 6),
        )
    except V2DHold as hold:
        return V2DPipelineResult(
            "HOLD", str(hold), None, None, None, None, (),
            0 if budget is None else budget.hermes_attempts,
            0 if budget is None else budget.targeted_asr_requests,
            0.0 if budget is None else round(budget.elapsed(), 6),
        )
    finally:
        if budget_token is not None:
            _ACTIVE_V2D_BUDGET.reset(budget_token)


__all__ = [
    "CandidateDecision", "GroupAdjudication", "MasterOutputProposal",
    "OutsideSpanExternalCueAssessment", "OutsideSpanHypothesisWindow",
    "OutsideSpanRecoveryLimits", "OutsideSpanRecoveryPlan", "OutsideSpanRecoveryResult",
    "OutsideSpanWindowOutcome", "RecoveredSupplementalASRSegment",
    "SourceDecision", "SourceSpan", "V2DAdjudication", "V2DError", "V2DExecutionLimits",
    "V2DHold", "V2DLimitStop", "V2DMaster", "V2DPipelineResult",
    "adjudicate_ja_master", "build_supplemental_asr_groups", "build_v2d_review_request",
    "build_v2d_targeted_asr_adapter", "load_validated_outside_span_diagnostic_evidence",
    "materialize_ja_master", "plan_outside_span_recovery", "run_targeted_review",
    "run_v2d_pipeline", "split_outside_span_groups", "translate_ja_master",
    "validate_adjudication",
]
