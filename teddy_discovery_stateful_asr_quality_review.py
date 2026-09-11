"""Generic ASR-only semantic-review evidence and result contracts.

This sidecar is deliberately separate from the external-JA review request.  It
keeps the existing action/result contract while binding review evidence to the
retained sparse ASR identities, the immutable first pass, and deterministic
nonlexical-filter provenance.  It owns no model, file, timing, or publication
I/O.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
import hashlib
import json
import re
import unicodedata

from teddy_discovery_asr import ASRResult, MAX_ASR_SEGMENTS
from teddy_discovery_asr_source_quality import (
    ASR_SOURCE_KEEP,
    ASR_SOURCE_OMIT,
    ASR_SOURCE_REQUIRE_SECOND_EVIDENCE,
    ASRSourceQualityDecision,
    ASRSourceQualityHint,
    ASR_SOURCE_FEATURE_ORDER,
    ASR_SOURCE_KNOWN_FEATURES,
    classify_asr_result_source_quality,
)
from teddy_discovery_nonlexical import (
    NONLEXICAL_KEEP,
    NONLEXICAL_OMIT,
    NonLexicalDecision,
    classify_nonlexical,
)
from teddy_discovery_stateful_asr_srt import source_index_for_asr_cue_id
from teddy_discovery_stateful_prepare import StatefulPrepareResult
from teddy_discovery_hybrid_evidence import EVIDENCE_SOURCE_ASR_SEGMENT, stable_cue_id
from teddy_discovery_stateful_quality_review import (
    AMBIGUOUS,
    KEEP,
    OMIT,
    REPAIR,
    MAX_REVIEW_BYTES,
    MAX_REVIEW_CONTEXT_ITEMS,
    MAX_REVIEW_CUES,
    MAX_REVIEW_REASON_CHARS,
    MAX_REVIEW_IDENTIFIER_CHARS,
    QualityReviewError,
    QualityReviewResult,
    QualityReviewResultCue,
    STATEFUL_QUALITY_REVIEW_SCHEMA_VERSION,
    effective_review_action,
)
from teddy_discovery_quality_review_session import (
    encode_source_translation_session_id,
    resolve_source_translation_session_id,
)
from teddy_discovery_stateful_translator import (
    STATEFUL_TRANSLATOR_MAX_CUES,
    StatefulSubtitlePackage,
    StatefulSubtitleResult,
    serialize_stateful_package,
    serialize_stateful_result,
    validate_stateful_result,
)
from teddy_discovery_subtitle_text import MAX_CUE_TEXT_CHARS
from teddy_discovery_targeted_second_evidence_artifact import (
    TargetedSecondEvidenceArtifact,
)
from teddy_discovery_targeted_second_evidence_projection import (
    TargetedSecondEvidenceProjectionError,
    TargetedSecondEvidenceReviewProjection,
    parse_targeted_second_evidence_review_projection,
    project_targeted_second_evidence_artifact,
)


_ASR_CUE_ID_RE = re.compile(r"^asr-[0-9]{4,}$")
_PROVENANCE_FIELDS_LEGACY = {
    "asr_artifact_sha256",
    "original_cue_count",
    "retained_cue_count",
    "omissions",
}
_PROVENANCE_FIELDS = _PROVENANCE_FIELDS_LEGACY | {
    "source_quality_hints",
}
_OMISSION_FIELDS = {"cue_id", "source_index", "reason"}
_OMISSION_FIELDS_WITH_FEATURES = _OMISSION_FIELDS | {"features"}
_NEIGHBOR_FIELDS = {"cue_id", "stt_ja", "repaired_ja", "ko"}
_INPUT_FIELDS_LEGACY = {
    "cue_id",
    "source_index",
    "stt_ja",
    "first_pass_repaired_ja",
    "first_pass_ko",
    "before_context",
    "after_context",
}
_INPUT_FIELDS = _INPUT_FIELDS_LEGACY | {"source_quality"}
_INPUT_FIELDS = _INPUT_FIELDS | {"targeted_second_evidence"}
_REQUEST_FIELDS_LEGACY = {
    "schema_version",
    "package_sha256",
    "first_pass_sha256",
    "source_sha256",
    "session_id",
    "prefilter_provenance",
    "cues",
}
_REQUEST_FIELDS = {
    "schema_version",
    "package_sha256",
    "first_pass_sha256",
    "source_sha256",
    "source_translation_session_id",
    "prefilter_provenance",
    "cues",
}
_RESULT_FIELDS_LEGACY = {"schema_version", "request_sha256", "cues"}
_RESULT_FIELDS_WITH_EXECUTION = _RESULT_FIELDS_LEGACY | {
    "source_translation_session_id",
    "review_execution_session_id",
}


def _text(value, *, optional=False, limit=MAX_CUE_TEXT_CHARS):
    if optional and value is None:
        return
    if type(value) is not str or not value.strip() or len(value) > limit:
        raise QualityReviewError("expected bounded nonempty exact ASR review text")
    if any(
        unicodedata.category(character) in {"Cc", "Cs"}
        and character not in "\n\r\t"
        for character in value
    ):
        raise QualityReviewError("invalid ASR review text control character")


def _identifier(value):
    if type(value) is not str or not value or len(value) > MAX_REVIEW_IDENTIFIER_CHARS:
        raise QualityReviewError("invalid ASR review identifier")
    if value != value.strip() or any(character.isspace() for character in value):
        raise QualityReviewError("ASR review identifier contains whitespace")


def _digest(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise QualityReviewError("expected lowercase SHA256 digest")


def _source_index(cue_id: str) -> int:
    _identifier(cue_id)
    if _ASR_CUE_ID_RE.fullmatch(cue_id) is None:
        raise QualityReviewError("cue identity is not a sparse ASR identity")
    try:
        index = source_index_for_asr_cue_id(cue_id)
    except Exception as error:
        raise QualityReviewError("cue identity is not a valid ASR ordinal") from error
    if not 0 <= index < MAX_ASR_SEGMENTS:
        raise QualityReviewError("ASR source index is outside its bound")
    return index


def _version(value):
    if type(value) is not int or value != STATEFUL_QUALITY_REVIEW_SCHEMA_VERSION:
        raise QualityReviewError("unsupported ASR quality-review schema")


def _validate_source_quality_features(value: object) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise QualityReviewError("source-quality features must be immutable")
    if any(type(feature) is not str for feature in value):
        raise QualityReviewError("source-quality feature is not an exact string")
    if any(feature not in ASR_SOURCE_KNOWN_FEATURES for feature in value):
        raise QualityReviewError("source-quality feature is unknown")
    if len(set(value)) != len(value):
        raise QualityReviewError("source-quality features must be unique")
    expected_order = tuple(
        feature for feature in ASR_SOURCE_FEATURE_ORDER if feature in value
    )
    if value != expected_order:
        raise QualityReviewError("source-quality features are not source ordered")
    return value


def _encode(value) -> bytes:
    data = asdict(value)
    # The source-quality hint is additive.  Keep legacy ASR review request
    # bytes stable when the caller has no generic source-quality provenance.
    if isinstance(value, ASRQualityReviewRequest):
        legacy_wire = data.pop("_legacy_session_wire", False)
        source_session = data.pop("source_translation_session_id")
        encode_source_translation_session_id(
            data, source_session, legacy_wire_field=legacy_wire
        )
        provenance = data["prefilter_provenance"]
        if not provenance.get("source_quality_hints"):
            provenance.pop("source_quality_hints", None)
        for omission in provenance["omissions"]:
            if not omission.get("features"):
                omission.pop("features", None)
        for cue in data["cues"]:
            if cue.get("source_quality") is None:
                cue.pop("source_quality", None)
            if cue.get("targeted_second_evidence") is None:
                cue.pop("targeted_second_evidence", None)
    elif isinstance(value, QualityReviewResult):
        if data.get("source_translation_session_id") is None:
            data.pop("source_translation_session_id", None)
        if data.get("review_execution_session_id") is None:
            data.pop("review_execution_session_id", None)
    try:
        payload = json.dumps(
            data,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, UnicodeError, ValueError) as error:
        raise QualityReviewError("ASR quality-review value is not serializable") from error
    if len(payload) > MAX_REVIEW_BYTES:
        raise QualityReviewError("ASR quality-review value exceeds byte bound")
    return payload


@dataclass(frozen=True)
class ASRPrefilterOmission:
    cue_id: str
    source_index: int
    reason: str
    features: tuple[str, ...] = ()

    def __post_init__(self):
        if _source_index(self.cue_id) != self.source_index:
            raise QualityReviewError("prefilter omission identity/index differs")
        if type(self.source_index) is not int or not 0 <= self.source_index < MAX_ASR_SEGMENTS:
            raise QualityReviewError("prefilter omission source index is invalid")
        _text(self.reason, limit=MAX_REVIEW_REASON_CHARS)
        _validate_source_quality_features(self.features)


@dataclass(frozen=True)
class ASRPrefilterProvenance:
    asr_artifact_sha256: str
    original_cue_count: int
    retained_cue_count: int
    omissions: tuple[ASRPrefilterOmission, ...]
    source_quality_hints: tuple[ASRSourceQualityHint, ...] = ()

    def __post_init__(self):
        _digest(self.asr_artifact_sha256)
        if (
            type(self.original_cue_count) is not int
            or not 0 < self.original_cue_count <= MAX_ASR_SEGMENTS
            or type(self.retained_cue_count) is not int
            or not 0 < self.retained_cue_count <= STATEFUL_TRANSLATOR_MAX_CUES
            or self.retained_cue_count > self.original_cue_count
        ):
            raise QualityReviewError("invalid ASR prefilter counts")
        if type(self.omissions) is not tuple:
            raise QualityReviewError("prefilter omissions must be immutable")
        if type(self.source_quality_hints) is not tuple:
            raise QualityReviewError("source-quality hints must be immutable")
        if self.source_quality_hints:
            if len(self.source_quality_hints) != self.original_cue_count:
                raise QualityReviewError(
                    "source-quality hints do not cover original ASR"
                )
            for source_index, hint in enumerate(self.source_quality_hints):
                if type(hint) is not ASRSourceQualityHint:
                    raise QualityReviewError("invalid source-quality hint")
                hint.__post_init__()
                if hint.source_index != source_index:
                    raise QualityReviewError(
                        "source-quality hints are not source ordered"
                    )
        expected_count = self.original_cue_count - self.retained_cue_count
        if len(self.omissions) != expected_count:
            raise QualityReviewError("prefilter omission count is detached")
        previous = None
        seen = set()
        for omission in self.omissions:
            if type(omission) is not ASRPrefilterOmission:
                raise QualityReviewError("invalid prefilter omission")
            omission.__post_init__()
            if omission.cue_id in seen or (
                previous is not None and omission.source_index <= previous
            ):
                raise QualityReviewError("prefilter omissions are not source ordered")
            if omission.source_index >= self.original_cue_count:
                raise QualityReviewError("prefilter omission is outside original ASR")
            if self.source_quality_hints:
                source_quality = self.source_quality_hints[omission.source_index]
                if (
                    omission.reason != source_quality.reason
                    or omission.features != source_quality.features
                    or source_quality.action != ASR_SOURCE_OMIT
                ):
                    raise QualityReviewError(
                        "prefilter omission is detached from source quality"
                    )
            seen.add(omission.cue_id)
            previous = omission.source_index


@dataclass(frozen=True)
class ASRReviewNeighbor:
    cue_id: str
    stt_ja: str
    repaired_ja: str | None
    ko: str

    def __post_init__(self):
        _source_index(self.cue_id)
        _text(self.stt_ja)
        _text(self.repaired_ja, optional=True)
        _text(self.ko)


@dataclass(frozen=True)
class ASRQualityReviewInputCue:
    cue_id: str
    source_index: int
    stt_ja: str
    first_pass_repaired_ja: str | None
    first_pass_ko: str
    before_context: tuple[ASRReviewNeighbor, ...] = ()
    after_context: tuple[ASRReviewNeighbor, ...] = ()
    source_quality: ASRSourceQualityHint | None = None
    targeted_second_evidence: TargetedSecondEvidenceReviewProjection | None = None

    def __post_init__(self):
        if _source_index(self.cue_id) != self.source_index:
            raise QualityReviewError("ASR review cue identity/index differs")
        if type(self.source_index) is not int or not 0 <= self.source_index < MAX_ASR_SEGMENTS:
            raise QualityReviewError("ASR review source index is invalid")
        _text(self.stt_ja)
        _text(self.first_pass_repaired_ja, optional=True)
        _text(self.first_pass_ko)
        if self.source_quality is not None:
            if type(self.source_quality) is not ASRSourceQualityHint:
                raise QualityReviewError("invalid ASR source-quality hint")
            self.source_quality.__post_init__()
            if self.source_quality.source_index != self.source_index:
                raise QualityReviewError(
                    "ASR source-quality hint is detached from review cue"
                )
        if self.targeted_second_evidence is not None:
            if type(self.targeted_second_evidence) is not TargetedSecondEvidenceReviewProjection:
                raise QualityReviewError(
                    "invalid targeted second-evidence projection"
                )
            self.targeted_second_evidence.__post_init__()
            if (
                self.source_quality is None
                or self.source_quality.action != ASR_SOURCE_REQUIRE_SECOND_EVIDENCE
            ):
                raise QualityReviewError(
                    "targeted evidence is attached to a non-REQUIRE cue"
                )
        for name, context, direction in (
            ("before_context", self.before_context, -1),
            ("after_context", self.after_context, 1),
        ):
            if type(context) is not tuple or len(context) > MAX_REVIEW_CONTEXT_ITEMS:
                raise QualityReviewError(name + " exceeds its bounded context")
            seen = set()
            indexes = []
            for neighbor in context:
                if type(neighbor) is not ASRReviewNeighbor:
                    raise QualityReviewError(name + " contains an invalid neighbor")
                neighbor.__post_init__()
                index = _source_index(neighbor.cue_id)
                if index == self.source_index or index in seen:
                    raise QualityReviewError(name + " contains the current/duplicate cue")
                if direction < 0 and index >= self.source_index:
                    raise QualityReviewError(name + " contains a non-before cue")
                if direction > 0 and index <= self.source_index:
                    raise QualityReviewError(name + " contains a non-after cue")
                seen.add(index)
                indexes.append(index)
            if indexes != sorted(indexes):
                raise QualityReviewError(name + " is not in retained source order")


@dataclass(frozen=True)
class ASRQualityReviewRequest:
    schema_version: int
    package_sha256: str
    first_pass_sha256: str
    source_sha256: str
    source_translation_session_id: str
    prefilter_provenance: ASRPrefilterProvenance
    cues: tuple[ASRQualityReviewInputCue, ...]
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
        if type(self.prefilter_provenance) is not ASRPrefilterProvenance:
            raise QualityReviewError("ASR prefilter provenance is required")
        self.prefilter_provenance.__post_init__()
        if self.prefilter_provenance.asr_artifact_sha256 != self.source_sha256:
            raise QualityReviewError("ASR provenance hash differs from source hash")
        if type(self.cues) is not tuple or not 0 < len(self.cues) <= MAX_REVIEW_CUES:
            raise QualityReviewError("invalid ASR review cue collection")
        if len(self.cues) != self.prefilter_provenance.retained_cue_count:
            raise QualityReviewError("ASR review cue count differs from provenance")
        previous = None
        seen = set()
        for cue in self.cues:
            if type(cue) is not ASRQualityReviewInputCue:
                raise QualityReviewError("invalid ASR review input cue")
            cue.__post_init__()
            if cue.cue_id in seen or (
                previous is not None and cue.source_index <= previous
            ):
                raise QualityReviewError("ASR review cues are not source ordered")
            seen.add(cue.cue_id)
            previous = cue.source_index
        if seen & {item.cue_id for item in self.prefilter_provenance.omissions}:
            raise QualityReviewError("prefilter omitted cue re-entered review")
        with_quality = tuple(cue.source_quality is not None for cue in self.cues)
        if any(with_quality) and not all(with_quality):
            raise QualityReviewError(
                "ASR source-quality provenance must cover all review cues"
            )
        if any(with_quality):
            if not self.prefilter_provenance.source_quality_hints:
                raise QualityReviewError(
                    "review cue source quality lacks complete provenance"
                )
            by_index = {
                hint.source_index: hint
                for hint in self.prefilter_provenance.source_quality_hints
            }
            for cue in self.cues:
                if cue.source_quality != by_index.get(cue.source_index):
                    raise QualityReviewError(
                        "review cue source quality differs from provenance"
                    )


def build_asr_prefilter_provenance(
    asr_result: ASRResult,
    prepared: StatefulPrepareResult,
    *,
    asr_artifact_sha256: str,
) -> ASRPrefilterProvenance:
    """Bind existing classifier decisions to the complete ASR source order."""

    if type(asr_result) is not ASRResult or type(prepared) is not StatefulPrepareResult:
        raise QualityReviewError("ASR prefilter provenance requires exact source models")
    asr_result.__post_init__()
    prepared.package.__post_init__()
    if prepared.package.dvd_id != asr_result.source_snapshot.dvd_id:
        raise QualityReviewError("prefilter package belongs to another ASR source")
    if type(prepared.decisions) is not tuple or len(prepared.decisions) != len(asr_result.segments):
        raise QualityReviewError("classifier decisions do not cover ASR source")

    source_quality_hints = ()
    if prepared.source_quality_decisions:
        if len(prepared.source_quality_decisions) != len(asr_result.segments):
            raise QualityReviewError("source-quality decisions do not cover ASR source")
        quality_decisions = []
        for item in prepared.source_quality_decisions:
            if type(item) is not tuple or len(item) != 2:
                raise QualityReviewError("malformed source-quality decision binding")
            cue_id, decision = item
            if type(decision) is not ASRSourceQualityDecision:
                raise QualityReviewError("invalid source-quality decision")
            decision.__post_init__()
            source_index = _source_index(cue_id)
            if decision.source_index != source_index:
                raise QualityReviewError("source-quality decision identity is detached")
            quality_decisions.append(decision)
        try:
            expected_quality = classify_asr_result_source_quality(asr_result)
        except Exception as error:
            raise QualityReviewError("ASR source-quality classification failed") from error
        if tuple(quality_decisions) != expected_quality:
            raise QualityReviewError("source-quality decisions differ from classifier")
        source_quality_hints = tuple(
            ASRSourceQualityHint.from_decision(decision)
            for decision in quality_decisions
        )
        if any(
            cue_id != stable_cue_id(EVIDENCE_SOURCE_ASR_SEGMENT, source_index)
            for source_index, (cue_id, _) in enumerate(prepared.source_quality_decisions)
        ):
            raise QualityReviewError("source-quality decision IDs are detached")

    kept_ids = []
    omissions = []
    for source_index, item in enumerate(prepared.decisions):
        if type(item) is not tuple or len(item) != 2:
            raise QualityReviewError("malformed prefilter classifier decision")
        cue_id, decision = item
        expected_id = stable_cue_id(EVIDENCE_SOURCE_ASR_SEGMENT, source_index)
        if cue_id != expected_id or type(decision) is not NonLexicalDecision:
            raise QualityReviewError("prefilter classifier identity is detached")
        if source_quality_hints:
            quality = source_quality_hints[source_index]
            if quality.action == ASR_SOURCE_OMIT:
                omissions.append(
                    ASRPrefilterOmission(
                        cue_id, source_index, quality.reason, quality.features
                    )
                )
            elif quality.action in {ASR_SOURCE_KEEP, ASR_SOURCE_REQUIRE_SECOND_EVIDENCE}:
                kept_ids.append(cue_id)
            else:
                raise QualityReviewError("source-quality action is unsupported")
        else:
            expected = classify_nonlexical(asr_result.segments[source_index].text)
            if decision != expected:
                raise QualityReviewError("prefilter decision differs from classifier")
            if decision.action == NONLEXICAL_OMIT:
                omissions.append(ASRPrefilterOmission(cue_id, source_index, decision.reason))
            elif decision.action == NONLEXICAL_KEEP:
                kept_ids.append(cue_id)
            else:
                raise QualityReviewError("prefilter classifier action is unsupported")

    actual_ids = tuple(cue.cue_id for cue in prepared.package.cues)
    if actual_ids != tuple(kept_ids):
        raise QualityReviewError("prefilter retained IDs are detached")
    for cue in prepared.package.cues:
        source_index = _source_index(cue.cue_id)
        if cue.external_ja is not None or cue.stt_ja != asr_result.segments[source_index].text:
            raise QualityReviewError("prefilter retained ASR text is detached")

    return ASRPrefilterProvenance(
        asr_artifact_sha256=asr_artifact_sha256,
        original_cue_count=len(asr_result.segments),
        retained_cue_count=len(prepared.package.cues),
        omissions=tuple(omissions),
        source_quality_hints=source_quality_hints,
    )


def _validate_originals(
    asr_result: ASRResult,
    package: StatefulSubtitlePackage,
    result: StatefulSubtitleResult,
    provenance: ASRPrefilterProvenance,
) -> StatefulSubtitleResult:
    if type(asr_result) is not ASRResult or type(package) is not StatefulSubtitlePackage:
        raise QualityReviewError("ASR review originals have invalid exact types")
    asr_result.__post_init__()
    package.__post_init__()
    if package.dvd_id != asr_result.source_snapshot.dvd_id:
        raise QualityReviewError("ASR review package belongs to another source")
    validated = validate_stateful_result(result, package)
    if provenance.original_cue_count != len(asr_result.segments):
        raise QualityReviewError("prefilter original count differs from ASR source")
    if provenance.retained_cue_count != len(package.cues):
        raise QualityReviewError("prefilter retained count differs from package")

    package_by_index = {}
    for cue in package.cues:
        if cue.external_ja is not None or cue.stt_ja is None:
            raise QualityReviewError("ASR review package contains non-ASR evidence")
        source_index = _source_index(cue.cue_id)
        if source_index in package_by_index or cue.stt_ja != asr_result.segments[source_index].text:
            raise QualityReviewError("ASR review package text or identity differs")
        package_by_index[source_index] = cue

    omissions = {item.source_index: item for item in provenance.omissions}
    if len(omissions) != len(provenance.omissions):
        raise QualityReviewError("duplicate prefilter omission index")
    source_quality_hints = provenance.source_quality_hints
    if source_quality_hints:
        try:
            expected_quality = classify_asr_result_source_quality(asr_result)
            expected_hints = tuple(
                ASRSourceQualityHint.from_decision(decision)
                for decision in expected_quality
            )
        except Exception as error:
            raise QualityReviewError("ASR source-quality classification failed") from error
        if source_quality_hints != expected_hints:
            raise QualityReviewError("source-quality hints differ from classifier")
    for source_index, segment in enumerate(asr_result.segments):
        if source_quality_hints:
            decision = source_quality_hints[source_index]
            is_omit = decision.action == ASR_SOURCE_OMIT
            reason = decision.reason
            features = decision.features
        else:
            decision = classify_nonlexical(segment.text)
            is_omit = decision.action == NONLEXICAL_OMIT
            reason = decision.reason
            features = ()
        if is_omit:
            omission = omissions.get(source_index)
            if (
                omission is None
                or omission.reason != reason
                or omission.features != features
            ):
                raise QualityReviewError("prefilter omission differs from classifier")
        else:
            if source_index not in package_by_index or source_index in omissions:
                raise QualityReviewError("prefilter KEEP cue coverage differs")
            if source_quality_hints:
                valid_retained = decision.action in {
                    ASR_SOURCE_KEEP,
                    ASR_SOURCE_REQUIRE_SECOND_EVIDENCE,
                }
            else:
                valid_retained = decision.action == NONLEXICAL_KEEP
            if not valid_retained:
                raise QualityReviewError("prefilter classifier action is unsupported")
    if len(package_by_index) + len(omissions) != len(asr_result.segments):
        raise QualityReviewError("prefilter source coverage is incomplete")
    return validated


def _neighbor(cue, first, source_index: int) -> ASRReviewNeighbor:
    return ASRReviewNeighbor(
        cue_id=cue.cue_id,
        stt_ja=cue.stt_ja,
        repaired_ja=first.repaired_ja,
        ko=first.ko,
    )


def build_asr_quality_review_request(
    *,
    asr_result: ASRResult,
    package: StatefulSubtitlePackage,
    result: StatefulSubtitleResult,
    prefilter_provenance: ASRPrefilterProvenance,
    targeted_second_evidence_artifact: TargetedSecondEvidenceArtifact | None = None,
) -> ASRQualityReviewRequest:
    """Create a pure-ASR request with retained-sequence neighbor evidence."""

    if type(prefilter_provenance) is not ASRPrefilterProvenance:
        raise QualityReviewError("ASR prefilter provenance is required")
    validated_result = _validate_originals(
        asr_result, package, result, prefilter_provenance
    )
    require_source_indexes = tuple(
        hint.source_index
        for hint in prefilter_provenance.source_quality_hints
        if hint.action == ASR_SOURCE_REQUIRE_SECOND_EVIDENCE
    )
    targeted_by_source_id = project_targeted_second_evidence_artifact(
        targeted_second_evidence_artifact,
        asr_result=asr_result,
        require_source_indexes=require_source_indexes,
    )
    retained = tuple(package.cues)
    first_by_id = {cue.cue_id: cue for cue in validated_result.cues}
    quality_by_index = {
        hint.source_index: hint
        for hint in prefilter_provenance.source_quality_hints
    }
    cues = []
    for index, source in enumerate(retained):
        first = first_by_id.get(source.cue_id)
        if first is None:
            raise QualityReviewError("first-pass result cue is missing")
        before = tuple(
            _neighbor(retained[neighbor_index], validated_result.cues[neighbor_index], index)
            for neighbor_index in range(max(0, index - MAX_REVIEW_CONTEXT_ITEMS), index)
        )
        after = tuple(
            _neighbor(retained[neighbor_index], validated_result.cues[neighbor_index], index)
            for neighbor_index in range(
                index + 1,
                min(len(retained), index + 1 + MAX_REVIEW_CONTEXT_ITEMS),
            )
        )
        source_index = _source_index(source.cue_id)
        cues.append(
            ASRQualityReviewInputCue(
                cue_id=source.cue_id,
                source_index=source_index,
                stt_ja=source.stt_ja,
                first_pass_repaired_ja=first.repaired_ja,
                first_pass_ko=first.ko,
                before_context=before,
                after_context=after,
                source_quality=quality_by_index.get(source_index),
                targeted_second_evidence=targeted_by_source_id.get(source.cue_id),
            )
        )
    request = ASRQualityReviewRequest(
        schema_version=STATEFUL_QUALITY_REVIEW_SCHEMA_VERSION,
        package_sha256=hashlib.sha256(serialize_stateful_package(package)).hexdigest(),
        first_pass_sha256=hashlib.sha256(serialize_stateful_result(validated_result)).hexdigest(),
        source_sha256=prefilter_provenance.asr_artifact_sha256,
        source_translation_session_id=validated_result.session_id,
        prefilter_provenance=prefilter_provenance,
        cues=tuple(cues),
    )
    serialize_asr_quality_review_request(request)
    return request


def validate_asr_quality_review_request(
    request: ASRQualityReviewRequest,
    *,
    asr_result: ASRResult,
    package: StatefulSubtitlePackage,
    result: StatefulSubtitleResult,
    targeted_second_evidence_artifact: TargetedSecondEvidenceArtifact | None = None,
) -> ASRQualityReviewRequest:
    if type(request) is not ASRQualityReviewRequest:
        raise QualityReviewError("wrong ASR quality-review request type")
    request.__post_init__()
    expected = build_asr_quality_review_request(
        asr_result=asr_result,
        package=package,
        result=result,
        prefilter_provenance=request.prefilter_provenance,
        targeted_second_evidence_artifact=targeted_second_evidence_artifact,
    )
    if request != expected:
        raise QualityReviewError("ASR quality-review request differs from originals")
    return request


def serialize_asr_quality_review_request(request: ASRQualityReviewRequest) -> bytes:
    if type(request) is not ASRQualityReviewRequest:
        raise QualityReviewError("wrong ASR quality-review request type")
    request.__post_init__()
    return _encode(request)


def asr_quality_review_request_sha256(request: ASRQualityReviewRequest) -> str:
    return hashlib.sha256(serialize_asr_quality_review_request(request)).hexdigest()


def validate_asr_quality_review_result(
    result: QualityReviewResult,
    request: ASRQualityReviewRequest,
) -> QualityReviewResult:
    if type(result) is not QualityReviewResult:
        raise QualityReviewError("wrong ASR quality-review result type")
    result.__post_init__()
    if result.request_sha256 != asr_quality_review_request_sha256(request):
        raise QualityReviewError("ASR quality-review result belongs to another request")
    if tuple(cue.cue_id for cue in result.cues) != tuple(cue.cue_id for cue in request.cues):
        raise QualityReviewError("ASR quality-review result IDs/order differ")
    if (
        result.source_translation_session_id is not None
        and result.source_translation_session_id
        != request.source_translation_session_id
    ):
        raise QualityReviewError("ASR review result source session differs from request")
    _encode(result)
    return result


def serialize_asr_quality_review_result(
    result: QualityReviewResult,
    request: ASRQualityReviewRequest,
) -> bytes:
    return _encode(validate_asr_quality_review_result(result, request))


def _reject_constant(value):
    raise QualityReviewError("nonfinite ASR quality-review JSON number")


def _unique_object(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise QualityReviewError("duplicate ASR quality-review JSON key")
        output[key] = value
    return output


def _load(payload):
    if type(payload) is not bytes or not payload or len(payload) > MAX_REVIEW_BYTES:
        raise QualityReviewError("invalid ASR quality-review JSON bytes")
    try:
        return json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (ValueError, UnicodeError, RecursionError) as error:
        raise QualityReviewError("invalid ASR quality-review JSON") from error


def _exact_fields(value, expected):
    if type(value) is not dict or set(value) != expected:
        raise QualityReviewError("ASR quality-review JSON fields are not exact")


def _parse_neighbor(value):
    _exact_fields(value, _NEIGHBOR_FIELDS)
    return ASRReviewNeighbor(**value)


_HINT_FIELDS_LEGACY = {"source_index", "action", "reason", "features"}
_HINT_FIELDS = _HINT_FIELDS_LEGACY | {"evidence_reasons"}


def _parse_source_quality_hint(value):
    if value is None:
        return None
    if type(value) is not dict or set(value) not in (
        _HINT_FIELDS_LEGACY,
        _HINT_FIELDS,
    ):
        raise QualityReviewError("ASR source-quality hint fields are not exact")
    if type(value["features"]) is not list:
        raise QualityReviewError("source-quality hint features must be a JSON array")
    evidence_reasons = value.get("evidence_reasons", [])
    if type(evidence_reasons) is not list:
        raise QualityReviewError(
            "source-quality evidence reasons must be a JSON array"
        )
    return ASRSourceQualityHint(
        source_index=value["source_index"],
        action=value["action"],
        reason=value["reason"],
        features=tuple(value["features"]),
        evidence_reasons=tuple(evidence_reasons),
    )


def _parse_targeted_second_evidence(value):
    try:
        return parse_targeted_second_evidence_review_projection(value)
    except TargetedSecondEvidenceProjectionError as error:
        raise QualityReviewError(
            "invalid targeted second-evidence projection"
        ) from error


def _parse_input(value):
    if (
        type(value) is not dict
        or not _INPUT_FIELDS_LEGACY <= set(value)
        or not set(value) - _INPUT_FIELDS_LEGACY <= {
            "source_quality",
            "targeted_second_evidence",
        }
    ):
        raise QualityReviewError("ASR quality-review input fields are not exact")
    if type(value["before_context"]) is not list or type(value["after_context"]) is not list:
        raise QualityReviewError("ASR review neighbor context must be JSON arrays")
    return ASRQualityReviewInputCue(
        cue_id=value["cue_id"],
        source_index=value["source_index"],
        stt_ja=value["stt_ja"],
        first_pass_repaired_ja=value["first_pass_repaired_ja"],
        first_pass_ko=value["first_pass_ko"],
        before_context=tuple(_parse_neighbor(item) for item in value["before_context"]),
        after_context=tuple(_parse_neighbor(item) for item in value["after_context"]),
        source_quality=(
            None
            if "source_quality" not in value
            else _parse_source_quality_hint(value["source_quality"])
        ),
        targeted_second_evidence=(
            None
            if "targeted_second_evidence" not in value
            else _parse_targeted_second_evidence(value["targeted_second_evidence"])
        ),
    )


def _parse_provenance(value):
    if type(value) is not dict or set(value) not in (
        _PROVENANCE_FIELDS_LEGACY,
        _PROVENANCE_FIELDS,
    ):
        raise QualityReviewError("ASR provenance fields are not exact")
    if type(value["omissions"]) is not list:
        raise QualityReviewError("ASR prefilter omissions must be a JSON array")
    omissions = []
    for item in value["omissions"]:
        if type(item) is not dict or set(item) not in (
            _OMISSION_FIELDS,
            _OMISSION_FIELDS_WITH_FEATURES,
        ):
            raise QualityReviewError("ASR omission fields are not exact")
        if "features" in item:
            if type(item["features"]) is not list:
                raise QualityReviewError("ASR omission features must be a JSON array")
            item["features"] = tuple(item["features"])
        omissions.append(ASRPrefilterOmission(**item))
    hints = ()
    if "source_quality_hints" in value:
        if type(value["source_quality_hints"]) is not list:
            raise QualityReviewError("ASR source-quality hints must be a JSON array")
        hints = tuple(
            _parse_source_quality_hint(item)
            for item in value["source_quality_hints"]
        )
    return ASRPrefilterProvenance(
        asr_artifact_sha256=value["asr_artifact_sha256"],
        original_cue_count=value["original_cue_count"],
        retained_cue_count=value["retained_cue_count"],
        omissions=tuple(omissions),
        source_quality_hints=hints,
    )


def parse_asr_quality_review_request(
    payload: bytes,
    *,
    asr_result: ASRResult,
    package: StatefulSubtitlePackage,
    result: StatefulSubtitleResult,
    targeted_second_evidence_artifact: TargetedSecondEvidenceArtifact | None = None,
) -> ASRQualityReviewRequest:
    request = parse_asr_quality_review_request_structure(payload)
    return validate_asr_quality_review_request(
        request,
        asr_result=asr_result,
        package=package,
        result=result,
        targeted_second_evidence_artifact=targeted_second_evidence_artifact,
    )


def parse_asr_quality_review_request_structure(
    payload: bytes,
) -> ASRQualityReviewRequest:
    """Parse and validate the self-contained ASR-only request structure.

    This boundary proves the exact wire schema and all internal identity,
    provenance, and sparse-order invariants.  Callers that hold the original
    ASR/package/result artifacts should additionally use
    ``parse_asr_quality_review_request`` for detached-evidence revalidation.
    """

    data = _load(payload)
    if type(data) is not dict or set(data) not in {
        frozenset(_REQUEST_FIELDS_LEGACY), frozenset(_REQUEST_FIELDS)
    }:
        raise QualityReviewError("ASR quality-review request fields are not exact")
    try:
        source_session, legacy_session_wire = resolve_source_translation_session_id(data)
    except ValueError as error:
        raise QualityReviewError(str(error)) from error
    data = dict(data)
    data.pop("session_id", None)
    data.pop("source_translation_session_id", None)
    data["source_translation_session_id"] = source_session
    if type(data["cues"]) is not list:
        raise QualityReviewError("ASR review cues must be a JSON array")
    request = ASRQualityReviewRequest(
        schema_version=data["schema_version"],
        package_sha256=data["package_sha256"],
        first_pass_sha256=data["first_pass_sha256"],
        source_sha256=data["source_sha256"],
        source_translation_session_id=data["source_translation_session_id"],
        prefilter_provenance=_parse_provenance(data["prefilter_provenance"]),
        cues=tuple(_parse_input(item) for item in data["cues"]),
    )
    object.__setattr__(request, "_legacy_session_wire", legacy_session_wire)
    return request


def parse_asr_quality_review_result(
    payload: bytes,
    request: ASRQualityReviewRequest,
) -> QualityReviewResult:
    data = _load(payload)
    if type(data) is not dict or set(data) not in {
        frozenset(_RESULT_FIELDS_LEGACY), frozenset(_RESULT_FIELDS_WITH_EXECUTION)
    }:
        raise QualityReviewError("ASR quality-review result fields are not exact")
    if type(data["cues"]) is not list:
        raise QualityReviewError("ASR review result cues must be a JSON array")
    cues = []
    expected = {field.name for field in fields(QualityReviewResultCue)}
    for item in data["cues"]:
        _exact_fields(item, expected)
        cues.append(QualityReviewResultCue(**item))
    result = QualityReviewResult(
        schema_version=data["schema_version"],
        request_sha256=data["request_sha256"],
        cues=tuple(cues),
        source_translation_session_id=data.get("source_translation_session_id"),
        review_execution_session_id=data.get("review_execution_session_id"),
    )
    return validate_asr_quality_review_result(result, request)


__all__ = [
    "ASRPrefilterOmission",
    "ASRPrefilterProvenance",
    "ASRQualityReviewInputCue",
    "ASRQualityReviewRequest",
    "ASRReviewNeighbor",
    "asr_quality_review_request_sha256",
    "build_asr_prefilter_provenance",
    "build_asr_quality_review_request",
    "parse_asr_quality_review_request",
    "parse_asr_quality_review_request_structure",
    "parse_asr_quality_review_result",
    "serialize_asr_quality_review_request",
    "serialize_asr_quality_review_result",
    "validate_asr_quality_review_request",
    "validate_asr_quality_review_result",
    "effective_review_action",
]
