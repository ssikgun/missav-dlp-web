"""Source-bound Japanese master evidence for Stage11 ASR-first HYBRID v2.

This module combines existing ASR and validated external-JA evidence into a
review ledger.  It does not infer semantic truth, call models, perform I/O, or
publish subtitles.  A master cue is materialized only from an explicit
ACCEPTED decision tied to one source reference.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from fractions import Fraction
import hashlib
import json
import re
from typing import Final

from teddy_discovery_alignment import (
    MAX_LEXICAL_PAIR_COMPARISONS,
    RobustAffineAlignment,
)
from teddy_discovery_alignment_acceptance import (
    ACCEPT_HYBRID,
    AlignmentAcceptanceDecision,
    REJECT_EXTERNAL,
    UNRESOLVED,
)
from teddy_discovery_alignment_application import (
    AlignmentAcceptanceApplicationResult,
)
from teddy_discovery_asr import ASRSourceSnapshot
from teddy_discovery_asr_artifact import serialize_asr_result
from teddy_discovery_hybrid_evidence import (
    EVIDENCE_SOURCE_ASR_SEGMENT,
    EVIDENCE_SOURCE_EXTERNAL_JA,
    HybridEvidenceBundle,
    stable_cue_id,
)


EVIDENCE_SOURCE_SUPPLEMENTAL_ASR: Final = "supplemental_asr"
_SUPPLEMENTAL_ASR_ID_RE: Final = re.compile(r"^sup-asr-[0-9a-f]{24}$")

RELATION_MATCHED: Final = "MATCHED"
RELATION_ASR_ONLY: Final = "ASR_ONLY"
RELATION_EXTERNAL_ONLY: Final = "EXTERNAL_ONLY"
RELATION_POTENTIAL_CONFLICT: Final = "POTENTIAL_CONFLICT"
RELATIONS: Final = frozenset(
    {
        RELATION_MATCHED,
        RELATION_ASR_ONLY,
        RELATION_EXTERNAL_ONLY,
        RELATION_POTENTIAL_CONFLICT,
    }
)

DECISION_ACCEPTED: Final = "ACCEPTED"
DECISION_REJECTED: Final = "REJECTED"
DECISION_UNCERTAIN: Final = "UNCERTAIN"
DECISIONS: Final = frozenset(
    {DECISION_ACCEPTED, DECISION_REJECTED, DECISION_UNCERTAIN}
)

ROUTE_ASR_ONLY_NO_EXTERNAL: Final = "ASR_ONLY_NO_EXTERNAL_JA"
ROUTE_EXTERNAL_ALIGNMENT_ACCEPTED: Final = "EXTERNAL_ALIGNMENT_ACCEPTED"
ROUTE_EXTERNAL_ALIGNMENT_REJECTED: Final = "EXTERNAL_ALIGNMENT_REJECTED_ASR_FIRST"
ROUTE_EXTERNAL_ALIGNMENT_UNRESOLVED: Final = "EXTERNAL_ALIGNMENT_UNRESOLVED_ASR_FIRST"
ROUTE_EXTERNAL_ALIGNMENT_MISSING: Final = "EXTERNAL_ALIGNMENT_NOT_PROVIDED_ASR_FIRST"
ROUTES: Final = frozenset(
    {
        ROUTE_ASR_ONLY_NO_EXTERNAL,
        ROUTE_EXTERNAL_ALIGNMENT_ACCEPTED,
        ROUTE_EXTERNAL_ALIGNMENT_REJECTED,
        ROUTE_EXTERNAL_ALIGNMENT_UNRESOLVED,
        ROUTE_EXTERNAL_ALIGNMENT_MISSING,
    }
)

_SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
_CODE_RE: Final = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


class JAMasterError(ValueError):
    """Base error for invalid JA master evidence or decisions."""


class JAMasterValidationError(JAMasterError):
    """Raised when source identity, candidate, or decision is invalid."""


def _sha256(value: object, *, field: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise JAMasterValidationError(field + " must be a lowercase SHA-256")
    return value


@dataclass(frozen=True)
class JAMasterSourceReference:
    """Stable source cue identity and original/aligned timing evidence."""

    source: str
    source_id: str
    source_locator: str = field(repr=False)
    source_index: int
    source_sha256: str
    original_start_ms: int
    original_end_ms: int
    aligned_start_ms: Fraction | None
    aligned_end_ms: Fraction | None

    def __post_init__(self):
        if self.source not in {
            EVIDENCE_SOURCE_ASR_SEGMENT,
            EVIDENCE_SOURCE_EXTERNAL_JA,
            EVIDENCE_SOURCE_SUPPLEMENTAL_ASR,
        }:
            raise JAMasterValidationError("source kind is unsupported")
        if type(self.source_index) is not int or self.source_index < 0:
            raise JAMasterValidationError("source index is invalid")
        if self.source == EVIDENCE_SOURCE_SUPPLEMENTAL_ASR:
            if type(self.source_id) is not str or _SUPPLEMENTAL_ASR_ID_RE.fullmatch(self.source_id) is None:
                raise JAMasterValidationError("supplemental ASR source ID is invalid")
        else:
            expected_id = stable_cue_id(self.source, self.source_index)
            if self.source_id != expected_id:
                raise JAMasterValidationError("source ID is detached from source index")
        if (
            type(self.source_locator) is not str
            or not self.source_locator
            or any(ord(character) < 32 or ord(character) == 127 for character in self.source_locator)
        ):
            raise JAMasterValidationError("source locator is invalid")
        _sha256(self.source_sha256, field="source_sha256")
        if (
            type(self.original_start_ms) is not int
            or type(self.original_end_ms) is not int
            or self.original_start_ms < 0
            or self.original_end_ms <= self.original_start_ms
        ):
            raise JAMasterValidationError("original source interval is invalid")
        if (self.aligned_start_ms is None) != (self.aligned_end_ms is None):
            raise JAMasterValidationError("aligned interval must be complete")
        if self.aligned_start_ms is not None:
            if (
                type(self.aligned_start_ms) is not Fraction
                or type(self.aligned_end_ms) is not Fraction
                or self.aligned_end_ms <= self.aligned_start_ms
            ):
                raise JAMasterValidationError("aligned interval is invalid")
        if self.source == EVIDENCE_SOURCE_SUPPLEMENTAL_ASR and (
            self.aligned_start_ms != Fraction(self.original_start_ms)
            or self.aligned_end_ms != Fraction(self.original_end_ms)
        ):
            raise JAMasterValidationError("supplemental ASR reference must use exact verified audio offsets")

    @property
    def key(self) -> str:
        return self.source + ":" + self.source_id


@dataclass(frozen=True)
class JAMasterCandidate:
    """One deterministic relationship candidate; review starts uncertain."""

    candidate_id: str
    relation: str
    source_references: tuple[JAMasterSourceReference, ...]
    rationale_codes: tuple[str, ...]
    decision_status: str = DECISION_UNCERTAIN

    def __post_init__(self):
        _sha256(self.candidate_id, field="candidate_id")
        if self.relation not in RELATIONS:
            raise JAMasterValidationError("candidate relation is unsupported")
        if type(self.source_references) is not tuple or not self.source_references:
            raise JAMasterValidationError("candidate source references are required")
        if any(not isinstance(ref, JAMasterSourceReference) for ref in self.source_references):
            raise JAMasterValidationError("candidate source reference is invalid")
        keys = tuple(ref.key for ref in self.source_references)
        if len(set(keys)) != len(keys):
            raise JAMasterValidationError("candidate contains duplicate source references")
        expected_sources = {
            RELATION_MATCHED: {EVIDENCE_SOURCE_ASR_SEGMENT, EVIDENCE_SOURCE_EXTERNAL_JA},
            RELATION_POTENTIAL_CONFLICT: {EVIDENCE_SOURCE_ASR_SEGMENT, EVIDENCE_SOURCE_EXTERNAL_JA},
            RELATION_ASR_ONLY: {EVIDENCE_SOURCE_ASR_SEGMENT},
            RELATION_EXTERNAL_ONLY: {EVIDENCE_SOURCE_EXTERNAL_JA},
        }[self.relation]
        if {ref.source for ref in self.source_references} != expected_sources:
            raise JAMasterValidationError("candidate relation does not match its sources")
        expected_count = 1 if self.relation in {RELATION_ASR_ONLY, RELATION_EXTERNAL_ONLY} else 2
        if len(self.source_references) != expected_count:
            raise JAMasterValidationError("candidate source reference count is invalid")
        if type(self.rationale_codes) is not tuple or not self.rationale_codes:
            raise JAMasterValidationError("candidate rationale codes are required")
        if any(type(code) is not str or _CODE_RE.fullmatch(code) is None for code in self.rationale_codes):
            raise JAMasterValidationError("candidate rationale code is invalid")
        if self.decision_status not in DECISIONS:
            raise JAMasterValidationError("candidate decision status is unsupported")


@dataclass(frozen=True)
class JAMasterReviewSet:
    """Immutable source-bound candidate ledger before reviewer decisions."""

    dvd_id: str
    source_snapshot: ASRSourceSnapshot = field(repr=False)
    asr_sha256: str
    external_ja_sha256: str | None
    route: str
    alignment_decision: AlignmentAcceptanceDecision | None
    candidates: tuple[JAMasterCandidate, ...]
    _source_bundle: HybridEvidenceBundle = field(repr=False, compare=False)
    _source_alignment: RobustAffineAlignment | None = field(repr=False, compare=False)

    def __post_init__(self):
        if type(self.dvd_id) is not str or not self.dvd_id:
            raise JAMasterValidationError("dvd_id is invalid")
        if self._source_bundle.dvd_id != self.dvd_id:
            raise JAMasterValidationError("review set is detached from source bundle")
        bundle = _validated_bundle(self._source_bundle)
        if not isinstance(self.source_snapshot, ASRSourceSnapshot) or self.source_snapshot != bundle.asr_result.source_snapshot:
            raise JAMasterValidationError("review set source snapshot is detached")
        expected_asr_sha = hashlib.sha256(serialize_asr_result(bundle.asr_result)).hexdigest()
        if _sha256(self.asr_sha256, field="asr_sha256") != expected_asr_sha:
            raise JAMasterValidationError("review set ASR digest is detached from source")
        payload = bundle.external_ja_payload
        expected_external_sha = None if payload is None else payload.sha256
        if self.external_ja_sha256 != expected_external_sha:
            raise JAMasterValidationError("review set external JA digest is detached from source")
        if self.external_ja_sha256 is not None:
            _sha256(self.external_ja_sha256, field="external_ja_sha256")
        if self.route not in ROUTES:
            raise JAMasterValidationError("review set route is unsupported")
        if (payload is None) != (self.route == ROUTE_ASR_ONLY_NO_EXTERNAL):
            raise JAMasterValidationError("review set route does not match external source presence")
        alignment = self._source_alignment
        document = bundle.external_ja_document
        anchor_start = anchor_end = None
        if self.route == ROUTE_EXTERNAL_ALIGNMENT_ACCEPTED:
            if (
                not isinstance(alignment, RobustAffineAlignment)
                or not isinstance(self.alignment_decision, AlignmentAcceptanceDecision)
                or self.alignment_decision.verdict != ACCEPT_HYBRID
                or document is None
            ):
                raise JAMasterValidationError("accepted route requires affine and JA source evidence")
            try:
                alignment = RobustAffineAlignment(
                    scale=alignment.scale,
                    intercept_ms=alignment.intercept_ms,
                    anchor_count=alignment.anchor_count,
                    inlier_count=alignment.inlier_count,
                    residual_threshold_ms=alignment.residual_threshold_ms,
                    residuals=alignment.residuals,
                    median_absolute_residual_ms=alignment.median_absolute_residual_ms,
                )
            except (AttributeError, TypeError, ValueError) as error:
                raise JAMasterValidationError("stored affine evidence is invalid") from error
            for residual in alignment.residuals:
                ext_index = residual.external_identity.source_index
                asr_index = residual.asr_identity.source_index
                if ext_index >= len(document.cues) or asr_index >= len(bundle.asr_result.segments):
                    raise JAMasterValidationError("stored affine anchor is outside source bounds")
                ext_cue = document.cues[ext_index]
                asr_segment = bundle.asr_result.segments[asr_index]
                if (
                    residual.external_midpoint_x2 != ext_cue.start_ms + ext_cue.end_ms
                    or residual.asr_midpoint_x2 != asr_segment.start_ms + asr_segment.end_ms
                ):
                    raise JAMasterValidationError("stored affine anchor is detached from source timing")
            anchor_start = min(document.cues[item.external_identity.source_index].start_ms for item in alignment.residuals)
            anchor_end = max(document.cues[item.external_identity.source_index].end_ms for item in alignment.residuals)
        else:
            expected_verdict = {
                ROUTE_EXTERNAL_ALIGNMENT_REJECTED: REJECT_EXTERNAL,
                ROUTE_EXTERNAL_ALIGNMENT_UNRESOLVED: UNRESOLVED,
            }.get(self.route)
            if expected_verdict is None:
                if self.alignment_decision is not None or alignment is not None:
                    raise JAMasterValidationError("route without a verdict carries alignment state")
            elif (
                not isinstance(self.alignment_decision, AlignmentAcceptanceDecision)
                or self.alignment_decision.verdict != expected_verdict
                or alignment is not None
            ):
                raise JAMasterValidationError("route and alignment verdict are detached")
        if type(self.candidates) is not tuple or not self.candidates:
            raise JAMasterValidationError("review set candidates are required")
        if any(not isinstance(candidate, JAMasterCandidate) for candidate in self.candidates):
            raise JAMasterValidationError("review set candidate is invalid")
        if len({candidate.candidate_id for candidate in self.candidates}) != len(self.candidates):
            raise JAMasterValidationError("review set candidate IDs must be unique")
        document = bundle.external_ja_document
        covered: set[str] = set()
        for candidate in self.candidates:
            if candidate.decision_status != DECISION_UNCERTAIN:
                raise JAMasterValidationError("new review candidates must start uncertain")
            if candidate.candidate_id != _candidate_id(
                dvd_id=self.dvd_id,
                asr_sha256=self.asr_sha256,
                external_ja_sha256=self.external_ja_sha256,
                relation=candidate.relation,
                references=candidate.source_references,
            ):
                raise JAMasterValidationError("candidate ID is detached from source references")
            for ref in candidate.source_references:
                covered.add(ref.key)
                if ref.source == EVIDENCE_SOURCE_ASR_SEGMENT:
                    if ref.source_index >= len(bundle.asr_result.segments):
                        raise JAMasterValidationError("ASR source reference is outside source bounds")
                    segment = bundle.asr_result.segments[ref.source_index]
                    if (
                        ref.source_sha256 != self.asr_sha256
                        or ref.source_locator != bundle.asr_result.source_snapshot.canonical_video_relative
                        or ref.original_start_ms != segment.start_ms
                        or ref.original_end_ms != segment.end_ms
                        or ref.aligned_start_ms != Fraction(segment.start_ms)
                        or ref.aligned_end_ms != Fraction(segment.end_ms)
                    ):
                        raise JAMasterValidationError("ASR source reference is detached")
                else:
                    if document is None or payload is None or ref.source_index >= len(document.cues):
                        raise JAMasterValidationError("external source reference is outside source bounds")
                    cue = document.cues[ref.source_index]
                    if (
                        ref.source_sha256 != payload.sha256
                        or ref.source_locator != payload.candidate.external_source_id
                        or ref.original_start_ms != cue.start_ms
                        or ref.original_end_ms != cue.end_ms
                    ):
                        raise JAMasterValidationError("external source reference is detached")
                    if self.route == ROUTE_EXTERNAL_ALIGNMENT_ACCEPTED:
                        assert alignment is not None and anchor_start is not None and anchor_end is not None
                        inside_evidence_span = cue.start_ms >= anchor_start and cue.end_ms <= anchor_end
                        if inside_evidence_span:
                            scale = Fraction.from_float(alignment.scale)
                            intercept = Fraction.from_float(alignment.intercept_ms)
                            expected_start = scale * cue.start_ms + intercept
                            expected_end = scale * cue.end_ms + intercept
                            if ref.aligned_start_ms != expected_start or ref.aligned_end_ms != expected_end:
                                raise JAMasterValidationError("external projected timing is detached")
                        elif ref.aligned_start_ms is not None or ref.aligned_end_ms is not None:
                            raise JAMasterValidationError("external cue outside affine evidence span was projected")
                    elif ref.aligned_start_ms is not None or ref.aligned_end_ms is not None:
                        raise JAMasterValidationError("unaccepted route has aligned external timing")
        expected_coverage = {
            stable_cue_id(EVIDENCE_SOURCE_ASR_SEGMENT, index)
            for index in range(len(bundle.asr_result.segments))
        }
        if document is not None:
            expected_coverage.update(
                stable_cue_id(EVIDENCE_SOURCE_EXTERNAL_JA, index)
                for index in range(len(document.cues))
            )
        actual_coverage = {key.split(":", 1)[1] for key in covered}
        if actual_coverage != expected_coverage:
            raise JAMasterValidationError("candidate ledger does not preserve every source cue")


@dataclass(frozen=True)
class JAMasterDecision:
    """Explicit structural decision; reason code records, not proves, judgment."""

    candidate_id: str
    status: str
    selected_source_key: str | None
    rationale_code: str

    def __post_init__(self):
        _sha256(self.candidate_id, field="candidate_id")
        if self.status not in DECISIONS:
            raise JAMasterValidationError("decision status is unsupported")
        if type(self.rationale_code) is not str or _CODE_RE.fullmatch(self.rationale_code) is None:
            raise JAMasterValidationError("decision rationale code is invalid")
        if self.status == DECISION_ACCEPTED:
            if type(self.selected_source_key) is not str or not self.selected_source_key:
                raise JAMasterValidationError("accepted decision requires one selected source")
        elif self.selected_source_key is not None:
            raise JAMasterValidationError("non-accepted decision must not select a source")


@dataclass(frozen=True)
class JAMasterCue:
    """One explicitly accepted Japanese text and exact master-time interval."""

    cue_id: str
    source_reference: JAMasterSourceReference
    text: str = field(repr=False)
    start_ms: Fraction
    end_ms: Fraction

    def __post_init__(self):
        if type(self.cue_id) is not str or not self.cue_id.startswith("master-"):
            raise JAMasterValidationError("master cue ID is invalid")
        if not isinstance(self.source_reference, JAMasterSourceReference):
            raise JAMasterValidationError("master cue source reference is invalid")
        if type(self.text) is not str or not self.text.strip():
            raise JAMasterValidationError("master cue text is invalid")
        if (
            type(self.start_ms) is not Fraction
            or type(self.end_ms) is not Fraction
            or self.start_ms < 0
            or self.end_ms <= self.start_ms
        ):
            raise JAMasterValidationError("master cue interval is invalid")


@dataclass(frozen=True)
class JAMaster:
    """In-memory JA Master interface; it is not a file or publication."""

    review_set: JAMasterReviewSet
    decisions: tuple[JAMasterDecision, ...]
    candidates: tuple[JAMasterCandidate, ...]
    cues: tuple[JAMasterCue, ...]

    def __post_init__(self):
        if not isinstance(self.review_set, JAMasterReviewSet):
            raise JAMasterValidationError("master review set is invalid")
        if type(self.decisions) is not tuple or type(self.candidates) is not tuple or type(self.cues) is not tuple:
            raise JAMasterValidationError("master collections must be immutable tuples")
        expected = {candidate.candidate_id for candidate in self.review_set.candidates}
        decision_map = {decision.candidate_id: decision for decision in self.decisions}
        if set(decision_map) != expected or len(decision_map) != len(self.decisions):
            raise JAMasterValidationError("master decisions are detached from review candidates")
        candidate_map = {candidate.candidate_id: candidate for candidate in self.candidates}
        if set(candidate_map) != expected or len(candidate_map) != len(self.candidates):
            raise JAMasterValidationError("resolved candidate set is incomplete")
        selected: dict[str, tuple[JAMasterDecision, JAMasterCandidate]] = {}
        for candidate_id, decision in decision_map.items():
            candidate = candidate_map[candidate_id]
            if candidate.decision_status != decision.status:
                raise JAMasterValidationError("resolved candidate status is detached")
            if decision.status == DECISION_ACCEPTED:
                refs = {ref.key: ref for ref in candidate.source_references}
                ref = refs.get(decision.selected_source_key)
                if ref is None or ref.key in selected:
                    raise JAMasterValidationError("accepted source selection is invalid or duplicated")
                selected[ref.key] = (decision, candidate)
        if len(self.cues) != len(selected):
            raise JAMasterValidationError("master cues do not match accepted decisions")
        cue_sources = set()
        for cue in self.cues:
            if not isinstance(cue, JAMasterCue):
                raise JAMasterValidationError("master cue is invalid")
            key = cue.source_reference.key
            accepted = selected.get(key)
            if accepted is None or key in cue_sources:
                raise JAMasterValidationError("master cue is detached from accepted decision")
            decision, candidate = accepted
            expected_id = "master-" + hashlib.sha256(
                (candidate.candidate_id + ":" + key).encode("ascii")
            ).hexdigest()
            if (
                cue.cue_id != expected_id
                or cue.start_ms != cue.source_reference.aligned_start_ms
                or cue.end_ms != cue.source_reference.aligned_end_ms
            ):
                raise JAMasterValidationError("master cue identity or timing is detached")
            ref = cue.source_reference
            if ref.source == EVIDENCE_SOURCE_ASR_SEGMENT:
                expected_text = self.review_set._source_bundle.asr_result.segments[ref.source_index].text
            else:
                document = self.review_set._source_bundle.external_ja_document
                if document is None:
                    raise JAMasterValidationError("master cue has no external source document")
                expected_text = document.cues[ref.source_index].text
            if cue.text != expected_text:
                raise JAMasterValidationError("master cue text is detached from source")
            cue_sources.add(key)


def _validated_bundle(bundle: object) -> HybridEvidenceBundle:
    if not isinstance(bundle, HybridEvidenceBundle):
        raise JAMasterValidationError("source bundle must be HybridEvidenceBundle")
    try:
        return HybridEvidenceBundle(
            dvd_id=bundle.dvd_id,
            asr_result=bundle.asr_result,
            cue_evidence=bundle.cue_evidence,
            alignment=bundle.alignment,
            external_ja_payload=bundle.external_ja_payload,
            external_ja_document=bundle.external_ja_document,
            external_en_payload=bundle.external_en_payload,
            external_en_document=bundle.external_en_document,
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise JAMasterValidationError("source bundle failed reconstruction") from error


def _validated_application(
    application: object,
    source_bundle: HybridEvidenceBundle,
) -> AlignmentAcceptanceApplicationResult:
    if not isinstance(application, AlignmentAcceptanceApplicationResult):
        raise JAMasterValidationError("alignment application is invalid")
    try:
        validated = AlignmentAcceptanceApplicationResult(
            decision=application.decision,
            bundle=_validated_bundle(application.bundle),
            alignment=application.alignment,
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise JAMasterValidationError("alignment application failed reconstruction") from error
    if (
        validated.bundle.dvd_id != source_bundle.dvd_id
        or validated.bundle.asr_result != source_bundle.asr_result
        or serialize_asr_result(validated.bundle.asr_result)
        != serialize_asr_result(source_bundle.asr_result)
    ):
        raise JAMasterValidationError("alignment application uses different ASR source")
    raw_payload = source_bundle.external_ja_payload
    applied_payload = validated.bundle.external_ja_payload
    if validated.decision.verdict == ACCEPT_HYBRID:
        if raw_payload is None or applied_payload is None or raw_payload.sha256 != applied_payload.sha256:
            raise JAMasterValidationError("accepted alignment is detached from original JA source")
        if raw_payload.candidate != applied_payload.candidate:
            raise JAMasterValidationError("accepted alignment JA identity changed")
    elif validated.decision.verdict == REJECT_EXTERNAL:
        if raw_payload is None or applied_payload is not None:
            raise JAMasterValidationError("rejected alignment does not match original JA evidence")
    elif validated.decision.verdict == UNRESOLVED:
        if raw_payload is None or applied_payload is None or raw_payload.sha256 != applied_payload.sha256:
            raise JAMasterValidationError("unresolved alignment lost original JA evidence")
    else:
        raise JAMasterValidationError("alignment verdict is unsupported")
    return validated


def _candidate_id(
    *,
    dvd_id: str,
    asr_sha256: str,
    external_ja_sha256: str | None,
    relation: str,
    references: tuple[JAMasterSourceReference, ...],
) -> str:
    identity = {
        "dvd_id": dvd_id,
        "asr_sha256": asr_sha256,
        "external_ja_sha256": external_ja_sha256,
        "relation": relation,
        "sources": [
            {
                "source": ref.source,
                "source_id": ref.source_id,
                "source_sha256": ref.source_sha256,
            }
            for ref in sorted(references, key=lambda item: (item.source, item.source_index))
        ],
    }
    raw = json.dumps(identity, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


def _candidate(
    *,
    dvd_id: str,
    asr_sha256: str,
    external_ja_sha256: str | None,
    relation: str,
    references: tuple[JAMasterSourceReference, ...],
    rationale: str,
) -> JAMasterCandidate:
    ordered = tuple(sorted(references, key=lambda item: (item.source, item.source_index)))
    return JAMasterCandidate(
        candidate_id=_candidate_id(
            dvd_id=dvd_id,
            asr_sha256=asr_sha256,
            external_ja_sha256=external_ja_sha256,
            relation=relation,
            references=ordered,
        ),
        relation=relation,
        source_references=ordered,
        rationale_codes=(rationale,),
    )


def build_ja_master_review_set(
    source_bundle: HybridEvidenceBundle,
    *,
    alignment_application: AlignmentAcceptanceApplicationResult | None = None,
) -> JAMasterReviewSet:
    """Build a two-source candidate ledger without resolving semantic policy."""

    bundle = _validated_bundle(source_bundle)
    asr = bundle.asr_result
    asr_raw = serialize_asr_result(asr)
    asr_sha = hashlib.sha256(asr_raw).hexdigest()
    payload = bundle.external_ja_payload
    document = bundle.external_ja_document
    external_sha = None if payload is None else payload.sha256
    if alignment_application is None:
        alignment_decision = None
        if payload is None:
            route = ROUTE_ASR_ONLY_NO_EXTERNAL
        else:
            route = ROUTE_EXTERNAL_ALIGNMENT_MISSING
        alignment = None
    else:
        if payload is None:
            raise JAMasterValidationError("alignment application cannot be attached without external JA")
        applied = _validated_application(alignment_application, bundle)
        alignment_decision = applied.decision
        verdict = applied.decision.verdict
        if verdict == ACCEPT_HYBRID:
            route = ROUTE_EXTERNAL_ALIGNMENT_ACCEPTED
            alignment = applied.alignment
        elif verdict == REJECT_EXTERNAL:
            route = ROUTE_EXTERNAL_ALIGNMENT_REJECTED
            alignment = None
        else:
            route = ROUTE_EXTERNAL_ALIGNMENT_UNRESOLVED
            alignment = None

    asr_refs = tuple(
        JAMasterSourceReference(
            source=EVIDENCE_SOURCE_ASR_SEGMENT,
            source_id=stable_cue_id(EVIDENCE_SOURCE_ASR_SEGMENT, index),
            source_locator=asr.source_snapshot.canonical_video_relative,
            source_index=index,
            source_sha256=asr_sha,
            original_start_ms=segment.start_ms,
            original_end_ms=segment.end_ms,
            aligned_start_ms=Fraction(segment.start_ms),
            aligned_end_ms=Fraction(segment.end_ms),
        )
        for index, segment in enumerate(asr.segments)
    )
    ja_refs_list = []
    if document is not None and payload is not None:
        alignment_external_start = alignment_external_end = None
        if alignment is not None:
            anchor_indexes = tuple(
                item.external_identity.source_index for item in alignment.residuals
            )
            if not anchor_indexes or any(index >= len(document.cues) for index in anchor_indexes):
                raise JAMasterValidationError("alignment evidence lacks valid external source anchors")
            alignment_external_start = min(document.cues[index].start_ms for index in anchor_indexes)
            alignment_external_end = max(document.cues[index].end_ms for index in anchor_indexes)
        for index, cue in enumerate(document.cues):
            aligned_start = aligned_end = None
            if (
                alignment is not None
                and alignment_external_start is not None
                and cue.start_ms >= alignment_external_start
                and cue.end_ms <= alignment_external_end
            ):
                scale = Fraction.from_float(alignment.scale)
                intercept = Fraction.from_float(alignment.intercept_ms)
                aligned_start = scale * cue.start_ms + intercept
                aligned_end = scale * cue.end_ms + intercept
            ja_refs_list.append(
                JAMasterSourceReference(
                    source=EVIDENCE_SOURCE_EXTERNAL_JA,
                    source_id=stable_cue_id(EVIDENCE_SOURCE_EXTERNAL_JA, index),
                    source_locator=payload.candidate.external_source_id,
                    source_index=index,
                    source_sha256=payload.sha256,
                    original_start_ms=cue.start_ms,
                    original_end_ms=cue.end_ms,
                    aligned_start_ms=aligned_start,
                    aligned_end_ms=aligned_end,
                )
            )
    ja_refs = tuple(ja_refs_list)

    candidates: list[JAMasterCandidate] = []
    used_asr: set[int] = set()
    used_ja: set[int] = set()
    if alignment is not None:
        for residual in alignment.residuals:
            ai = residual.asr_identity.source_index
            ji = residual.external_identity.source_index
            if ai >= len(asr_refs) or ji >= len(ja_refs):
                raise JAMasterValidationError("alignment anchor references are outside source bounds")
            if ai in used_asr or ji in used_ja:
                raise JAMasterValidationError("alignment anchors reuse a source identity")
            used_asr.add(ai)
            used_ja.add(ji)
            if residual.is_inlier:
                relation, rationale = RELATION_MATCHED, "SELECTED_AFFINE_ANCHOR_INLIER"
            else:
                relation, rationale = RELATION_POTENTIAL_CONFLICT, "SELECTED_AFFINE_ANCHOR_OUTLIER"
            candidates.append(
                _candidate(
                    dvd_id=bundle.dvd_id,
                    asr_sha256=asr_sha,
                    external_ja_sha256=external_sha,
                    relation=relation,
                    references=(asr_refs[ai], ja_refs[ji]),
                    rationale=rationale,
                )
            )

    unmatched_asr = [i for i in range(len(asr_refs)) if i not in used_asr]
    unmatched_ja = [i for i in range(len(ja_refs)) if i not in used_ja]
    paired_asr: set[int] = set()
    paired_ja: set[int] = set()
    if alignment is not None and unmatched_asr and unmatched_ja:
        comparisons = 0
        for ji in unmatched_ja:
            ja_ref = ja_refs[ji]
            for ai in unmatched_asr:
                comparisons += 1
                if comparisons > MAX_LEXICAL_PAIR_COMPARISONS:
                    raise JAMasterValidationError("unmatched source comparison bound exceeded")
                asr_ref = asr_refs[ai]
                if (
                    ja_ref.aligned_start_ms is not None
                    and ja_ref.aligned_end_ms is not None
                    and ja_ref.aligned_start_ms < asr_ref.aligned_end_ms
                    and asr_ref.aligned_start_ms < ja_ref.aligned_end_ms
                ):
                    candidates.append(
                        _candidate(
                            dvd_id=bundle.dvd_id,
                            asr_sha256=asr_sha,
                            external_ja_sha256=external_sha,
                            relation=RELATION_POTENTIAL_CONFLICT,
                            references=(asr_ref, ja_ref),
                            rationale="UNMATCHED_PROJECTED_INTERVAL_OVERLAP",
                        )
                    )
                    paired_asr.add(ai)
                    paired_ja.add(ji)

    for ai in unmatched_asr:
        if ai not in paired_asr:
            rationale = "EXTERNAL_JA_ABSENT" if payload is None else "ASR_SEGMENT_WITHOUT_SELECTED_JA_MATCH"
            candidates.append(
                _candidate(
                    dvd_id=bundle.dvd_id,
                    asr_sha256=asr_sha,
                    external_ja_sha256=external_sha,
                    relation=RELATION_ASR_ONLY,
                    references=(asr_refs[ai],),
                    rationale=rationale,
                )
            )
    for ji in unmatched_ja:
        if ji not in paired_ja:
            rationale = (
                "EXTERNAL_JA_RETAINED_WITHOUT_ACCEPTED_ALIGNMENT"
                if alignment is None
                else (
                    "EXTERNAL_CUE_OUTSIDE_AFFINE_EVIDENCE_SPAN"
                    if ja_refs[ji].aligned_start_ms is None
                    else "EXTERNAL_CUE_WITHOUT_SELECTED_ASR_MATCH"
                )
            )
            candidates.append(
                _candidate(
                    dvd_id=bundle.dvd_id,
                    asr_sha256=asr_sha,
                    external_ja_sha256=external_sha,
                    relation=RELATION_EXTERNAL_ONLY,
                    references=(ja_refs[ji],),
                    rationale=rationale,
                )
            )

    relation_order = {
        RELATION_MATCHED: 0,
        RELATION_POTENTIAL_CONFLICT: 1,
        RELATION_ASR_ONLY: 2,
        RELATION_EXTERNAL_ONLY: 3,
    }
    candidates.sort(
        key=lambda item: (
            min(ref.source_index for ref in item.source_references),
            relation_order[item.relation],
            item.candidate_id,
        )
    )
    return JAMasterReviewSet(
        dvd_id=bundle.dvd_id,
        source_snapshot=asr.source_snapshot,
        asr_sha256=asr_sha,
        external_ja_sha256=external_sha,
        route=route,
        alignment_decision=alignment_decision,
        candidates=tuple(candidates),
        _source_bundle=bundle,
        _source_alignment=alignment,
    )


def apply_ja_master_decisions(
    review_set: JAMasterReviewSet,
    decisions: tuple[JAMasterDecision, ...],
) -> JAMaster:
    """Create an in-memory master only from complete, explicit decisions."""

    if not isinstance(review_set, JAMasterReviewSet):
        raise JAMasterValidationError("review_set must be a JAMasterReviewSet")
    if type(decisions) is not tuple:
        raise JAMasterValidationError("decisions must be an immutable tuple")
    by_id: dict[str, JAMasterDecision] = {}
    for decision in decisions:
        if not isinstance(decision, JAMasterDecision):
            raise JAMasterValidationError("decision has an unsupported type")
        if decision.candidate_id in by_id:
            raise JAMasterValidationError("candidate has duplicate decisions")
        by_id[decision.candidate_id] = decision
    expected_ids = {candidate.candidate_id for candidate in review_set.candidates}
    if set(by_id) != expected_ids:
        raise JAMasterValidationError("decisions must cover the exact candidate set")

    resolved_candidates = []
    selected_refs: set[str] = set()
    cues = []
    bundle = review_set._source_bundle
    for candidate in review_set.candidates:
        decision = by_id[candidate.candidate_id]
        refs = {ref.key: ref for ref in candidate.source_references}
        if decision.status == DECISION_ACCEPTED:
            ref = refs.get(decision.selected_source_key)
            if ref is None:
                raise JAMasterValidationError("accepted source is not attached to its candidate")
            if ref.key in selected_refs:
                raise JAMasterValidationError("accepted decisions duplicate a source cue")
            selected_refs.add(ref.key)
            if ref.aligned_start_ms is None or ref.aligned_end_ms is None:
                raise JAMasterValidationError("accepted source has no validated master time")
            if ref.source == EVIDENCE_SOURCE_ASR_SEGMENT:
                text = bundle.asr_result.segments[ref.source_index].text
            else:
                document = bundle.external_ja_document
                if document is None:
                    raise JAMasterValidationError("accepted external cue has no original document")
                text = document.cues[ref.source_index].text
            cue_id = "master-" + hashlib.sha256(
                (candidate.candidate_id + ":" + ref.key).encode("ascii")
            ).hexdigest()
            cues.append(
                JAMasterCue(
                    cue_id=cue_id,
                    source_reference=ref,
                    text=text,
                    start_ms=ref.aligned_start_ms,
                    end_ms=ref.aligned_end_ms,
                )
            )
        resolved_candidates.append(replace(candidate, decision_status=decision.status))
    cues.sort(key=lambda cue: (cue.start_ms, cue.end_ms, cue.cue_id))
    return JAMaster(
        review_set=review_set,
        decisions=decisions,
        candidates=tuple(resolved_candidates),
        cues=tuple(cues),
    )


__all__ = [
    "DECISION_ACCEPTED",
    "DECISION_REJECTED",
    "DECISION_UNCERTAIN",
    "EVIDENCE_SOURCE_SUPPLEMENTAL_ASR",
    "JAMaster",
    "JAMasterCandidate",
    "JAMasterCue",
    "JAMasterDecision",
    "JAMasterError",
    "JAMasterReviewSet",
    "JAMasterSourceReference",
    "JAMasterValidationError",
    "RELATION_ASR_ONLY",
    "RELATION_EXTERNAL_ONLY",
    "RELATION_MATCHED",
    "RELATION_POTENTIAL_CONFLICT",
    "ROUTE_ASR_ONLY_NO_EXTERNAL",
    "ROUTE_EXTERNAL_ALIGNMENT_ACCEPTED",
    "ROUTE_EXTERNAL_ALIGNMENT_MISSING",
    "ROUTE_EXTERNAL_ALIGNMENT_REJECTED",
    "ROUTE_EXTERNAL_ALIGNMENT_UNRESOLVED",
    "apply_ja_master_decisions",
    "build_ja_master_review_set",
]
