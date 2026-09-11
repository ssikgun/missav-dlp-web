"""Independent full-title semantic review sidecar, never a translation schema.

Strange dialogue is not automatically deleted: consider evidence-based repair
first. Repair requires source/STT/context support, never hallucinated dialogue
invented to fit context. Breaths, moans and exclamations are not inherently
noise; meaningful reactions can KEEP. Uncertainty is AMBIGUOUS with KEEP
fallback. Source-quality KEEP never exempts a cue from full-title review.
The LLM owns neither timing, source identity nor publication. Raw ASR context
is reference evidence only. Semantic truth cannot be proven by this structural
validator; it does not implement automatic CLEAN application or materialization.
"""
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, fields, replace
import hashlib
import json
import re
import unicodedata

from teddy_discovery_stateful_hybrid import StatefulHybridPreparation
from teddy_discovery_stateful_parts import has_runaway_repetition
from teddy_discovery_asr_source_quality import (
    ASR_SOURCE_REQUIRE_SECOND_EVIDENCE,
    ASRSourceQualityHint,
)
from teddy_discovery_stateful_translator import (
    STATEFUL_TRANSLATOR_MAX_CUES, StatefulSubtitlePackage, StatefulSubtitleResult,
    serialize_stateful_package, serialize_stateful_result, validate_stateful_result,
)
from teddy_discovery_subtitle_source_quality import SourceQualityDecision, classify_source_document
from teddy_discovery_subtitle_text import MAX_CUE_TEXT_CHARS
from teddy_discovery_subtitle_v2_orchestrator import project_affine_timestamp_ms
from teddy_discovery_targeted_asr_artifact import (
    TargetedASRArtifact, require_matching_targeted_asr_source,
)
from teddy_discovery_targeted_second_evidence_artifact import (
    TargetedSecondEvidenceArtifact,
)
from teddy_discovery_targeted_second_evidence_projection import (
    TargetedSecondEvidenceProjectionError,
    TargetedSecondEvidenceReviewProjection,
    parse_targeted_second_evidence_review_projection,
    project_targeted_second_evidence_artifact,
)
from teddy_discovery_quality_review_session import (
    encode_source_translation_session_id,
    resolve_source_translation_session_id,
)

STATEFUL_QUALITY_REVIEW_SCHEMA_VERSION = 2
MAX_REVIEW_BYTES = 32 * 1024 * 1024
MAX_REVIEW_CUES = STATEFUL_TRANSLATOR_MAX_CUES
MAX_REVIEW_CONTEXT_ITEMS = 4
MAX_REVIEW_REASON_CHARS = 1024
MAX_REVIEW_IDENTIFIER_CHARS = 256

KEEP = "KEEP"
REPAIR = "REPAIR"
OMIT = "OMIT"
AMBIGUOUS = "AMBIGUOUS"
_CATEGORIES = {
    KEEP: frozenset({"DIALOGUE", "MEANINGFUL_REACTION"}),
    REPAIR: frozenset({"SEMANTIC_REPAIR"}),
    OMIT: frozenset({"NONVERBAL_NOISE", "SOURCE_NOISE", "METADATA"}),
    AMBIGUOUS: frozenset({"AMBIGUOUS"}),
}
_REQUEST_FIELDS_LEGACY = frozenset({
    "schema_version", "package_sha256", "first_pass_sha256", "source_sha256",
    "session_id", "cues",
})
_REQUEST_FIELDS = frozenset({
    "schema_version", "package_sha256", "first_pass_sha256", "source_sha256",
    "source_translation_session_id", "cues",
})
_RESULT_FIELDS_LEGACY = frozenset({"schema_version", "request_sha256", "cues"})
_RESULT_FIELDS_WITH_EXECUTION = _RESULT_FIELDS_LEGACY | frozenset({
    "source_translation_session_id", "review_execution_session_id",
})


class QualityReviewError(ValueError):
    """Malformed, oversized or detached review contract."""


def _text(value, *, limit=MAX_CUE_TEXT_CHARS, optional=False):
    if optional and value is None:
        return
    if type(value) is not str or not value.strip() or len(value) > limit:
        raise QualityReviewError("expected bounded nonempty exact string")
    if any(unicodedata.category(c) in {"Cc", "Cs"} and c not in "\n\r\t" for c in value):
        raise QualityReviewError("invalid Unicode or text control")


def _identifier(value):
    _text(value, limit=MAX_REVIEW_IDENTIFIER_CHARS)
    if any(c.isspace() for c in value):
        raise QualityReviewError("identifier contains whitespace")


def _digest(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise QualityReviewError("expected SHA256 digest")


def _version(value):
    if type(value) is not int or value != STATEFUL_QUALITY_REVIEW_SCHEMA_VERSION:
        raise QualityReviewError("unsupported review schema")


def _validate(value, model):
    if type(value) is not model:
        raise QualityReviewError("wrong exact review model type")
    value.__post_init__()


def _cues(value, model):
    if type(value) is not tuple or not 0 < len(value) <= MAX_REVIEW_CUES:
        raise QualityReviewError("expected bounded nonempty immutable cue tuple")
    seen = set()
    for cue in value:
        _validate(cue, model)
        if cue.cue_id in seen:
            raise QualityReviewError("duplicate cue ID")
        seen.add(cue.cue_id)


@dataclass(frozen=True)
class ReviewProximityASREvidence:
    """Read-only non-overlap reference, never accepted STT or transcript truth.

    Distance alone never proves speech identity. Semantic mismatch may mean
    neighboring speech; metadata remains metadata despite nearby narration.
    Strong semantic agreement plus whole-title order/context can support actual
    speech, but uncertainty must preserve the first pass (AMBIGUOUS -> KEEP).
    Runaway and source-quality hints are not semantic truth or deletion rules.
    """
    text: str
    relation: str
    distance_ms: int
    mutual_nearest: bool
    runaway: bool

    def __post_init__(self):
        _text(self.text)
        if type(self.relation) is not str or self.relation not in {'BEFORE', 'AFTER'}:
            raise QualityReviewError('invalid proximity relation')
        if type(self.distance_ms) is not int or self.distance_ms < 0:
            raise QualityReviewError('proximity distance must be an exact nonnegative integer')
        if self.mutual_nearest is not True:
            raise QualityReviewError('proximity evidence must be mutual nearest')
        if type(self.runaway) is not bool or self.runaway != has_runaway_repetition(self.text):
            raise QualityReviewError('invalid proximity runaway hint')


@dataclass(frozen=True)
class QualityReviewInputCue:
    cue_id: str
    source_index: int
    external_ja: str
    accepted_stt_ja: str | None
    first_pass_repaired_ja: str | None
    first_pass_ko: str
    source_quality_action: str
    source_quality_reason: str
    raw_asr_context: tuple[str, ...] = ()
    proximity_asr_evidence: ReviewProximityASREvidence | None = None
    asr_source_quality: ASRSourceQualityHint | None = None
    targeted_second_evidence: TargetedSecondEvidenceReviewProjection | None = None

    def __post_init__(self):
        _identifier(self.cue_id)
        if type(self.source_index) is not int or not 0 <= self.source_index < MAX_REVIEW_CUES:
            raise QualityReviewError("invalid original source index")
        _text(self.external_ja)
        _text(self.accepted_stt_ja, optional=True)
        _text(self.first_pass_repaired_ja, optional=True)
        _text(self.first_pass_ko)
        try:
            SourceQualityDecision(self.source_index, self.source_quality_action,
                                  self.source_quality_reason, self.external_ja)
        except ValueError as error:
            raise QualityReviewError("invalid source-quality hint") from error
        if type(self.raw_asr_context) is not tuple or len(self.raw_asr_context) > MAX_REVIEW_CONTEXT_ITEMS:
            raise QualityReviewError("raw ASR context must be a bounded immutable tuple")
        for text in self.raw_asr_context:
            _text(text)
        if self.proximity_asr_evidence is not None:
            _validate(self.proximity_asr_evidence, ReviewProximityASREvidence)
        if self.asr_source_quality is not None:
            _validate(self.asr_source_quality, ASRSourceQualityHint)
        if self.targeted_second_evidence is not None:
            if type(self.targeted_second_evidence) is not TargetedSecondEvidenceReviewProjection:
                raise QualityReviewError(
                    "invalid targeted second-evidence projection"
                )
            self.targeted_second_evidence.__post_init__()
            if (
                self.asr_source_quality is None
                or self.asr_source_quality.action
                != ASR_SOURCE_REQUIRE_SECOND_EVIDENCE
            ):
                raise QualityReviewError(
                    "targeted evidence is attached to a non-REQUIRE cue"
                )


@dataclass(frozen=True)
class QualityReviewResultCue:
    cue_id: str
    action: str
    category: str
    reason: str
    replacement_ja: str | None
    replacement_ko: str | None

    def __post_init__(self):
        _identifier(self.cue_id)
        if (type(self.action) is not str or self.action not in _CATEGORIES
                or type(self.category) is not str or self.category not in _CATEGORIES[self.action]):
            raise QualityReviewError("invalid action/category combination")
        _text(self.reason, limit=MAX_REVIEW_REASON_CHARS)
        if self.action != REPAIR:
            if self.replacement_ja is not None or self.replacement_ko is not None:
                raise QualityReviewError("only REPAIR permits replacement text")
        else:
            _text(self.replacement_ja)
            _text(self.replacement_ko)
            if any("HANGUL" in unicodedata.name(c, "") for c in self.replacement_ja):
                raise QualityReviewError("replacement Japanese contains Korean script")
            if has_runaway_repetition(self.replacement_ja) or has_runaway_repetition(self.replacement_ko):
                raise QualityReviewError("runaway replacement output")


@dataclass(frozen=True)
class QualityReviewRequest:
    schema_version: int
    package_sha256: str
    first_pass_sha256: str
    source_sha256: str
    source_translation_session_id: str
    cues: tuple[QualityReviewInputCue, ...]
    _legacy_session_wire: bool = field(default=False, compare=False, repr=False)

    @property
    def session_id(self) -> str:
        """Backward-compatible alias for source translation provenance."""

        return self.source_translation_session_id

    def __post_init__(self):
        _version(self.schema_version)
        for digest in (self.package_sha256, self.first_pass_sha256, self.source_sha256):
            _digest(digest)
        _identifier(self.source_translation_session_id)
        _cues(self.cues, QualityReviewInputCue)
        # This is a complete original document, not a filtered subset.
        if tuple(c.source_index for c in self.cues) != tuple(range(len(self.cues))):
            raise QualityReviewError("full-title source order/indexes differ")


@dataclass(frozen=True)
class QualityReviewResult:
    schema_version: int
    request_sha256: str
    cues: tuple[QualityReviewResultCue, ...]
    source_translation_session_id: str | None = None
    review_execution_session_id: str | None = None

    def __post_init__(self):
        _version(self.schema_version)
        _digest(self.request_sha256)
        _cues(self.cues, QualityReviewResultCue)
        if self.source_translation_session_id is None:
            if self.review_execution_session_id is not None:
                raise QualityReviewError(
                    "review execution identity requires source provenance"
                )
        else:
            _identifier(self.source_translation_session_id)
            if self.review_execution_session_id is None:
                raise QualityReviewError(
                    "source provenance requires review execution identity"
                )
            _identifier(self.review_execution_session_id)


def _encode(value):
    try:
        data = asdict(value)
        if isinstance(value, QualityReviewRequest):
            legacy_wire = data.pop("_legacy_session_wire", False)
            source_session = data.pop("source_translation_session_id")
            encode_source_translation_session_id(
                data, source_session, legacy_wire_field=legacy_wire
            )
            for cue in data["cues"]:
                if cue.get("asr_source_quality") is None:
                    cue.pop("asr_source_quality", None)
                if cue.get("targeted_second_evidence") is None:
                    cue.pop("targeted_second_evidence", None)
        elif isinstance(value, QualityReviewResult):
            if data.get("source_translation_session_id") is None:
                data.pop("source_translation_session_id", None)
            if data.get("review_execution_session_id") is None:
                data.pop("review_execution_session_id", None)
        payload = json.dumps(data, ensure_ascii=False, allow_nan=False,
                             sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        raise QualityReviewError("review cannot be serialized") from error
    if len(payload) > MAX_REVIEW_BYTES:
        raise QualityReviewError("review exceeds byte bound")
    return payload


def serialize_review_request(request: QualityReviewRequest) -> bytes:
    """Structural serialization; validate against originals at trust boundaries."""
    _validate(request, QualityReviewRequest)
    return _encode(request)


def review_request_sha256(request: QualityReviewRequest) -> str:
    return hashlib.sha256(serialize_review_request(request)).hexdigest()


def build_full_window_raw_asr_context(
    artifact: TargetedASRArtifact, *, preparation: StatefulHybridPreparation,
) -> dict[str, tuple[str, ...]]:
    """Attach full-window reference evidence to every mapped source cue.

    This is NOT a direct cue transcript or accepted STT. Classifier decisions
    never filter coverage. Segment order, exact text and duplicates are retained;
    newline joins segments, and ''.join(context_items) reconstructs that text.
    Fixed character slices use the existing review bounds, without truncation
    or normalization. Unrepresentable (including whitespace-only) items fail
    closed. Empty segment windows explicitly map to (); uncovered cues are
    absent and build_review_request gives them its existing empty default.

    The native artifact validator allows overlapping time windows but rejects
    duplicate/multiple cue assignments. No merge or timing inference is added.
    Original preparation binds source provenance and known cue identities;
    dictionary insertion order follows its unchanged package cue order.
    """
    if type(preparation) is not StatefulHybridPreparation:
        raise QualityReviewError('original HYBRID preparation required')
    try:
        preparation.__post_init__()
        bundle = preparation.route_decision.alignment_application.bundle
        validated = require_matching_targeted_asr_source(
            artifact, bundle.asr_result.source_snapshot,
        )
    except Exception as error:
        raise QualityReviewError('invalid or detached targeted context evidence') from error
    cue_ids = tuple(cue.cue_id for cue in preparation.package.cues)
    known = set(cue_ids)
    contexts = {}
    for window in validated.windows:
        if not set(window.external_cue_ids) <= known:
            raise QualityReviewError('unknown targeted context cue ID')
        texts = tuple(segment.text for segment in window.segments)
        # Check before allocating the joined full-window string. Duplicates,
        # including noisy repetitions, consume the same bound as all evidence.
        size = sum(len(text) for text in texts) + max(0, len(texts) - 1)
        if size > MAX_CUE_TEXT_CHARS * MAX_REVIEW_CONTEXT_ITEMS:
            raise QualityReviewError('full-window context exceeds item count bound')
        full_text = '\n'.join(texts)
        chunks = tuple(full_text[start:start + MAX_CUE_TEXT_CHARS]
                       for start in range(0, len(full_text), MAX_CUE_TEXT_CHARS))
        for chunk in chunks:
            _text(chunk, limit=MAX_CUE_TEXT_CHARS)
        for cue_id in window.external_cue_ids:
            contexts[cue_id] = chunks
    return {cue_id: contexts[cue_id] for cue_id in cue_ids if cue_id in contexts}


def build_review_proximity_asr_evidence(
    artifact: TargetedASRArtifact, *, preparation: StatefulHybridPreparation,
) -> dict[str, ReviewProximityASREvidence]:
    """Find unique mutual nearest non-overlap pairs within exact owned windows.

    Every cue/segment pair participates in nearest competition: positive overlap
    has distance zero, while before/after pairs use interval gap (endpoint
    contact is non-overlap with distance zero). Only after unique mutual nearest
    selection are overlap pairs rejected from materialization. Thus a segment
    owned by another overlapping cue cannot be stolen as proximity evidence.
    Ties in either direction yield no evidence. No text matching, distance
    threshold or binding promotion occurs. Text/order are untouched; runaway is
    only a boolean reference hint. All cues use the existing accepted affine
    projection, never model timing.
    """
    if type(preparation) is not StatefulHybridPreparation:
        raise QualityReviewError('original HYBRID preparation required')
    try:
        preparation.__post_init__()
        application = preparation.route_decision.alignment_application
        bundle = application.bundle
        validated = require_matching_targeted_asr_source(artifact, bundle.asr_result.source_snapshot)
        intervals = {}
        for binding in preparation.semantic_bindings:
            cue = bundle.external_ja_document.cues[binding.source_index]
            start = project_affine_timestamp_ms(application.alignment, cue.start_ms)
            end = project_affine_timestamp_ms(application.alignment, cue.end_ms)
            if end <= start:
                raise QualityReviewError('invalid projected cue duration')
            intervals[binding.request_cue_id] = (start, end)
        output = {}
        for window in validated.windows:
            by_cue, by_segment = {}, {}
            for cue_id in window.external_cue_ids:
                if cue_id not in intervals:
                    raise QualityReviewError('unknown proximity cue ID')
                start, end = intervals[cue_id]
                if start < window.window_start_ms or end > window.window_end_ms:
                    raise QualityReviewError('projected cue outside its targeted window')
                for index, segment in enumerate(window.segments):
                    overlaps = (
                        segment.start_ms < end
                        and start < segment.end_ms
                    )
                    if overlaps:
                        distance = 0
                    elif segment.end_ms <= start:
                        distance = start - segment.end_ms
                    elif segment.start_ms >= end:
                        distance = segment.start_ms - end
                    else:
                        raise QualityReviewError('invalid cue/segment interval relation')
                    # Keep only each minimum and its uniqueness. Every pair,
                    # including overlap pairs, reaches both nearest tables.
                    for table, key, peer in ((by_cue, cue_id, index), (by_segment, index, cue_id)):
                        previous = table.get(key)
                        if previous is None or distance < previous[0]:
                            table[key] = (distance, peer)
                        elif distance == previous[0]:
                            table[key] = (distance, None)
            for cue_id in window.external_cue_ids:
                nearest = by_cue.get(cue_id)
                if nearest is None or nearest[1] is None:
                    continue
                distance, index = nearest
                if by_segment[index][1] != cue_id:
                    continue
                segment = window.segments[index]
                cue_start, cue_end = intervals[cue_id]
                if segment.start_ms < cue_end and cue_start < segment.end_ms:
                    # Overlap participated in nearest competition but cannot
                    # become review-only temporal proximity evidence.
                    continue
                if segment.end_ms <= cue_start:
                    relation = 'BEFORE'
                elif segment.start_ms >= cue_end:
                    relation = 'AFTER'
                else:
                    raise QualityReviewError('mutual candidate has invalid relation')
                output[cue_id] = ReviewProximityASREvidence(
                    segment.text, relation,
                    distance, True, has_runaway_repetition(segment.text),
                )
        return {cue_id: output[cue_id] for cue_id in intervals if cue_id in output}
    except QualityReviewError:
        raise
    except Exception as error:
        raise QualityReviewError('invalid or detached proximity evidence') from error


def _targeted_artifact_binding_for_semantic_binding(
    semantic_binding,
    targeted_artifact: TargetedSecondEvidenceArtifact,
):
    """Resolve one target-only semantic binding by exact window/result identity."""

    targeted = semantic_binding.targeted_asr_evidence
    if targeted is None:
        raise QualityReviewError("targeted semantic binding is missing")
    evidence = targeted.evidence
    candidates = tuple(
        artifact_binding
        for artifact_binding in targeted_artifact.bindings
        if (
            artifact_binding.window.start_ms == evidence.window_start_ms
            and artifact_binding.window.end_ms == evidence.window_end_ms
            and artifact_binding.result.source_snapshot
            == evidence.source_snapshot
            and artifact_binding.result.segments == evidence.segments
        )
    )
    if len(candidates) != 1:
        raise QualityReviewError(
            "targeted semantic binding does not identify one artifact source"
        )
    return candidates[0]


def build_review_request(*, preparation: StatefulHybridPreparation,
                         package: StatefulSubtitlePackage, result: StatefulSubtitleResult,
                         source_quality: tuple[SourceQualityDecision, ...],
                         raw_asr_context: Mapping[str, tuple[str, ...]] | None = None,
                         proximity_asr_artifact: TargetedASRArtifact | None = None,
                         targeted_second_evidence_artifact: TargetedSecondEvidenceArtifact | None = None,
                         ) -> QualityReviewRequest:
    """Bind every cue to original proof and complete, unmodified first pass.

    Context mapping keys are existing cue IDs only. No timing or source identity
    is inferred from context. Hashes bind the original serialized artifacts;
    request parsing must re-prove this binding with the caller-held originals.
    Optional proximity evidence is recomputed from the caller-held typed artifact
    at every trust boundary; callers cannot supply unproven proximity decisions.
    """
    if type(preparation) is not StatefulHybridPreparation:
        raise QualityReviewError("original HYBRID preparation required")
    try:
        preparation.__post_init__()
        if type(package) is not StatefulSubtitlePackage or package != preparation.package:
            raise QualityReviewError("package detached from preparation")
        validated_result = validate_stateful_result(result, package)
        document = preparation.route_decision.alignment_application.bundle.external_ja_document
        expected_quality = classify_source_document(document)
        if (type(source_quality) is not tuple
                or any(type(c) is not SourceQualityDecision for c in source_quality)
                or source_quality != expected_quality):
            raise QualityReviewError("source-quality decisions detached from original document")
        if raw_asr_context is None:
            context = {}
        elif isinstance(raw_asr_context, Mapping):
            context = dict(raw_asr_context)
        else:
            raise QualityReviewError("context must be a cue-ID mapping")
        if any(type(key) is not str for key in context) or not set(context) <= {c.cue_id for c in package.cues}:
            raise QualityReviewError("unknown context cue ID")
        proximity = ({} if proximity_asr_artifact is None else
                     build_review_proximity_asr_evidence(proximity_asr_artifact, preparation=preparation))
        asr_result = preparation.route_decision.alignment_application.bundle.asr_result
        require_source_indexes = tuple(
            decision.source_index
            for decision in preparation.asr_source_quality_decisions
            if decision.action == ASR_SOURCE_REQUIRE_SECOND_EVIDENCE
        )
        targeted_by_source_id = project_targeted_second_evidence_artifact(
            targeted_second_evidence_artifact,
            asr_result=asr_result,
            require_source_indexes=require_source_indexes,
        )
        asr_decision_by_index = {
            decision.source_index: decision
            for decision in preparation.asr_source_quality_decisions
        }
        mapped_targeted_source_ids = set()
        seen_asr_source_ids = set()
        cues = []
        for source, first, binding, hint in zip(package.cues, validated_result.cues,
                                               preparation.semantic_bindings, source_quality, strict=True):
            if (binding.source_index != hint.source_index or binding.request_cue_id != source.cue_id
                    or source.external_ja != hint.source_text):
                raise QualityReviewError("source index/text detached")
            asr_source_quality = None
            targeted_second_evidence = None
            if binding.asr_identity is not None:
                asr_source_id = binding.asr_identity.cue_id
                if asr_source_id in seen_asr_source_ids:
                    raise QualityReviewError("duplicate ASR semantic binding")
                seen_asr_source_ids.add(asr_source_id)
                by_source_index = {
                    decision.source_index: decision
                    for decision in preparation.asr_source_quality_decisions
                }
                decision = by_source_index.get(binding.asr_identity.source_index)
                if decision is None:
                    raise QualityReviewError("baseline ASR source-quality evidence is missing")
                asr_source_quality = ASRSourceQualityHint.from_decision(decision)
                targeted_second_evidence = targeted_by_source_id.get(asr_source_id)
                if targeted_second_evidence is not None:
                    mapped_targeted_source_ids.add(asr_source_id)
            elif binding.targeted_asr_evidence is not None:
                if targeted_second_evidence_artifact is None:
                    raise QualityReviewError(
                        "targeted semantic binding has no artifact"
                    )
                artifact_binding = _targeted_artifact_binding_for_semantic_binding(
                    binding,
                    targeted_second_evidence_artifact,
                )
                asr_source_id = artifact_binding.source_id
                if asr_source_id in seen_asr_source_ids:
                    raise QualityReviewError("duplicate ASR semantic binding")
                seen_asr_source_ids.add(asr_source_id)
                decision = asr_decision_by_index.get(
                    artifact_binding.source.source_index
                )
                if (
                    decision is None
                    or decision.action != ASR_SOURCE_REQUIRE_SECOND_EVIDENCE
                ):
                    raise QualityReviewError(
                        "targeted semantic binding is not a REQUIRE source"
                    )
                asr_source_quality = ASRSourceQualityHint.from_decision(decision)
                targeted_second_evidence = targeted_by_source_id.get(asr_source_id)
                if targeted_second_evidence is None:
                    raise QualityReviewError(
                        "targeted semantic binding is detached from artifact projection"
                    )
                mapped_targeted_source_ids.add(asr_source_id)
            cues.append(QualityReviewInputCue(
                source.cue_id, binding.source_index, source.external_ja, source.stt_ja,
                first.repaired_ja, first.ko, hint.action, hint.reason,
                context.get(source.cue_id, ()),
                proximity.get(source.cue_id),
                asr_source_quality,
                targeted_second_evidence,
            ))
        if mapped_targeted_source_ids != set(targeted_by_source_id):
            raise QualityReviewError(
                "targeted second-evidence binding is detached from Hybrid review cues"
            )
        request = QualityReviewRequest(
            schema_version=STATEFUL_QUALITY_REVIEW_SCHEMA_VERSION,
            package_sha256=hashlib.sha256(serialize_stateful_package(package)).hexdigest(),
            first_pass_sha256=hashlib.sha256(serialize_stateful_result(validated_result)).hexdigest(),
            source_sha256=document.source_sha256,
            source_translation_session_id=validated_result.session_id,
            cues=tuple(cues),
        )
        serialize_review_request(request)
        return request
    except QualityReviewError:
        raise
    except Exception as error:
        raise QualityReviewError("invalid or detached original review evidence") from error


def validate_review_request(request: QualityReviewRequest, **originals) -> QualityReviewRequest:
    _validate(request, QualityReviewRequest)
    if request != build_review_request(**originals):
        raise QualityReviewError("review request differs from original evidence")
    return request


def validate_review_result(result: QualityReviewResult, request: QualityReviewRequest) -> QualityReviewResult:
    """Requires the caller's exact validated request, not an LLM-supplied copy."""
    _validate(result, QualityReviewResult)
    if result.request_sha256 != review_request_sha256(request):
        raise QualityReviewError("review result belongs to another request")
    if tuple(c.cue_id for c in result.cues) != tuple(c.cue_id for c in request.cues):
        raise QualityReviewError("review result cue count/IDs/order differ")
    if (
        result.source_translation_session_id is not None
        and result.source_translation_session_id
        != request.source_translation_session_id
    ):
        raise QualityReviewError("review result source session differs from request")
    _encode(result)
    return result


def serialize_review_result(result: QualityReviewResult, request: QualityReviewRequest) -> bytes:
    return _encode(validate_review_result(result, request))


def bind_review_execution_provenance(
    result: QualityReviewResult,
    request: object,
    review_execution_session_id: str,
) -> QualityReviewResult:
    """Attach runtime execution identity without changing review decisions."""

    if not hasattr(request, "source_translation_session_id"):
        raise QualityReviewError("review request has no source session provenance")
    try:
        request.__post_init__()
    except AttributeError as error:
        raise QualityReviewError("invalid review request provenance") from error
    _validate(result, QualityReviewResult)
    _identifier(review_execution_session_id)
    if (
        result.source_translation_session_id is not None
        and result.source_translation_session_id
        != request.source_translation_session_id
    ):
        raise QualityReviewError("review result source session differs from request")
    if (
        result.review_execution_session_id is not None
        and result.review_execution_session_id != review_execution_session_id
    ):
        raise QualityReviewError("review result execution session differs from caller")
    bound = replace(
        result,
        source_translation_session_id=request.source_translation_session_id,
        review_execution_session_id=review_execution_session_id,
    )
    return bound


def _reject_constant(value):
    raise QualityReviewError("nonfinite JSON number")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise QualityReviewError("duplicate JSON key")
        result[key] = value
    return result


def _load(payload):
    if type(payload) is not bytes or not payload or len(payload) > MAX_REVIEW_BYTES:
        raise QualityReviewError("expected bounded nonempty UTF-8 bytes")
    try:
        return json.loads(payload.decode("utf-8", errors="strict"),
                          object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise QualityReviewError("invalid review JSON") from error


def _fields(value, model):
    if type(value) is not dict:
        raise QualityReviewError("review JSON must have exact field set")
    if model is QualityReviewRequest:
        allowed = (_REQUEST_FIELDS_LEGACY, _REQUEST_FIELDS)
    elif model is QualityReviewResult:
        allowed = (_RESULT_FIELDS_LEGACY, _RESULT_FIELDS_WITH_EXECUTION)
    else:
        allowed = ({field.name for field in fields(model)},)
    if set(value) not in allowed:
        raise QualityReviewError("review JSON must have exact field set")


def _parse(payload, model, cue_model):
    data = _load(payload)
    _fields(data, model)
    legacy_session_wire = False
    if model is QualityReviewRequest:
        try:
            source_session, legacy_session_wire = resolve_source_translation_session_id(data)
        except ValueError as error:
            raise QualityReviewError(str(error)) from error
        data = dict(data)
        data.pop("session_id", None)
        data.pop("source_translation_session_id", None)
        data["source_translation_session_id"] = source_session
    _version(data['schema_version'])  # V1 forensic bytes are never reinterpreted.
    raw_cues = data["cues"]
    if type(raw_cues) is not list or not 0 < len(raw_cues) <= MAX_REVIEW_CUES:
        raise QualityReviewError("invalid JSON cue collection")
    cues = []
    for cue in raw_cues:
        if cue_model is QualityReviewInputCue:
            optional_fields = {"asr_source_quality", "targeted_second_evidence"}
            required_fields = {field.name for field in fields(cue_model)} - optional_fields
            if (
                type(cue) is not dict
                or not required_fields <= set(cue)
                or not set(cue) - required_fields <= optional_fields
            ):
                raise QualityReviewError("review input cue fields are not exact")
        else:
            _fields(cue, cue_model)
        if cue_model is QualityReviewInputCue:
            if type(cue["raw_asr_context"]) is not list:
                raise QualityReviewError("context must be a JSON array")
            cue["raw_asr_context"] = tuple(cue["raw_asr_context"])
            proximity = cue['proximity_asr_evidence']
            if proximity is not None:
                _fields(proximity, ReviewProximityASREvidence)
                cue['proximity_asr_evidence'] = ReviewProximityASREvidence(**proximity)
            if "asr_source_quality" in cue:
                hint = cue["asr_source_quality"]
                if hint is not None:
                    hint_fields_legacy = {
                        "source_index", "action", "reason", "features"
                    }
                    hint_fields = hint_fields_legacy | {"evidence_reasons"}
                    if type(hint) is not dict or set(hint) not in (
                        hint_fields_legacy, hint_fields
                    ):
                        raise QualityReviewError(
                            "ASR source-quality hint fields are not exact"
                        )
                    if type(hint["features"]) is not list:
                        raise QualityReviewError("ASR source-quality features must be an array")
                    evidence_reasons = hint.get("evidence_reasons", [])
                    if type(evidence_reasons) is not list:
                        raise QualityReviewError(
                            "ASR source-quality evidence reasons must be an array"
                        )
                    cue["asr_source_quality"] = ASRSourceQualityHint(
                        source_index=hint["source_index"],
                        action=hint["action"],
                        reason=hint["reason"],
                        features=tuple(hint["features"]),
                        evidence_reasons=tuple(evidence_reasons),
                    )
            if "targeted_second_evidence" in cue:
                try:
                    cue["targeted_second_evidence"] = (
                        parse_targeted_second_evidence_review_projection(
                            cue["targeted_second_evidence"]
                        )
                    )
                except TargetedSecondEvidenceProjectionError as error:
                    raise QualityReviewError(
                        "invalid targeted second-evidence projection"
                    ) from error
        cues.append(cue_model(**cue))
    data["cues"] = tuple(cues)
    value = model(**data)
    if model is QualityReviewRequest:
        object.__setattr__(value, "_legacy_session_wire", legacy_session_wire)
    return value


def parse_review_request(payload: bytes, **originals) -> QualityReviewRequest:
    """No detached parsing: caller must supply the same builder originals."""
    return validate_review_request(_parse(payload, QualityReviewRequest, QualityReviewInputCue), **originals)


def parse_review_result(payload: bytes, request: QualityReviewRequest) -> QualityReviewResult:
    return validate_review_result(_parse(payload, QualityReviewResult, QualityReviewResultCue), request)


def effective_review_action(
    request_cue: object,
    result_cue: QualityReviewResultCue | None = None,
) -> str:
    """Return the deterministic downstream action without mutating raw review.

    The one-argument form preserves the pre-existing AMBIGUOUS -> KEEP
    fallback for callers that do not hold the review input.  Callers applying
    a review result should pass both the request cue and result cue so an
    exact no-op REPAIR can be treated as KEEP.  No text normalization or
    semantic equivalence is performed.
    """
    if result_cue is None:
        result_cue = request_cue
        request_cue = None
    _validate(result_cue, QualityReviewResultCue)
    if result_cue.action == AMBIGUOUS:
        return KEEP
    if result_cue.action != REPAIR or request_cue is None:
        return result_cue.action

    missing = object()
    first_pass_repaired_ja = getattr(
        request_cue, "first_pass_repaired_ja", missing
    )
    first_pass_ko = getattr(request_cue, "first_pass_ko", missing)
    if first_pass_repaired_ja is missing or first_pass_ko is missing:
        raise QualityReviewError(
            "REPAIR normalization requires a validated review input cue"
        )
    if (
        type(first_pass_ko) is not str
        or (
            first_pass_repaired_ja is not None
            and type(first_pass_repaired_ja) is not str
        )
    ):
        raise QualityReviewError(
            "REPAIR normalization found invalid first-pass text"
        )
    if (
        result_cue.replacement_ko == first_pass_ko
        and result_cue.replacement_ja == first_pass_repaired_ja
    ):
        return KEEP
    return REPAIR
