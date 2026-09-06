"""Pure Stage11 v2 per-title orchestrator-facing contracts.

This module freezes data ownership and route vocabulary for a future v2
orchestrator.  It deliberately does not select sources, invoke R1--R4
transport, run ASR or Hermes, generate output, publish, or perform I/O.

Existing immutable source objects remain authoritative:

* ``CanonicalVideoHolding`` owns canonical title/video identity.
* ``HybridEvidenceBundle`` and its R3 application result own aligned evidence.
* ``HermesV2Request`` and ``HermesV2Result`` own semantic model data.
* ``SubtitleCue``/``ASRSegment`` own route-specific deterministic timing
  evidence.
* ``GeneratedKoreanSRT`` owns the supplied pre-publication artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, DecimalException, ROUND_HALF_UP
from pathlib import PurePosixPath
import unicodedata
from typing import Final

from teddy_discovery_alignment import RobustAffineAlignment
from teddy_discovery_alignment_acceptance import (
    ACCEPT_HYBRID,
    REJECT_EXTERNAL,
    UNRESOLVED,
)
from teddy_discovery_alignment_application import (
    AlignmentAcceptanceApplicationResult,
)
from teddy_discovery_asr import ASRResult, ASRSegment
from teddy_discovery_ids import parse_dvd_id
from teddy_discovery_hermes_v2 import (
    HermesV2Request,
    HermesV2Result,
    MAX_HERMES_V2_CUE_ID_CHARS,
    validate_hermes_v2_result,
)
from teddy_discovery_hybrid_evidence import (
    ALIGNMENT_PROVENANCE_ASR_ONLY,
    ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
    ALIGNMENT_PROVENANCE_UNRESOLVED,
    EVIDENCE_SOURCE_ASR_SEGMENT,
    EVIDENCE_SOURCE_EXTERNAL_JA,
    HybridCueIdentity,
    HybridEvidenceBundle,
)
from teddy_discovery_ko_srt import (
    GENERATED_SRT_READY,
    GeneratedKoreanSRT,
)
from teddy_discovery_subtitle import (
    SOURCE_KIND_SIBLING_TEXT,
    CanonicalVideoHolding,
    SubtitleCandidate,
    derive_target_ko_relative,
    normalize_language,
    validate_canonical_holding,
)
from teddy_discovery_subtitle_text import (
    MAX_SUBTITLE_CUES,
    SubtitleCue,
    SubtitleDocument,
    parse_subtitle_bytes,
    serialize_srt,
)


# Route values describe v2 source families only; they are not R6 job states.
V2_ROUTE_EXISTING_KO: Final[str] = "EXISTING_KO"
V2_ROUTE_LOCAL_JA: Final[str] = "LOCAL_JA"
V2_ROUTE_HYBRID: Final[str] = "HYBRID"
V2_ROUTE_ASR_ONLY: Final[str] = "ASR_ONLY"
V2_ROUTE_UNRESOLVED: Final[str] = "UNRESOLVED"

V2_TERMINAL_EXISTING_KO: Final[str] = "TERMINAL_EXISTING_KO"
V2_READY_FOR_SEMANTIC: Final[str] = "READY_FOR_SEMANTIC"
V2_READY_FOR_VALIDATION: Final[str] = "READY_FOR_VALIDATION"
V2_READY_TO_PUBLISH: Final[str] = "READY_TO_PUBLISH"
V2_FAILED_CLOSED: Final[str] = "FAILED_CLOSED"

V2_ROUTES: Final[frozenset[str]] = frozenset(
    {
        V2_ROUTE_EXISTING_KO,
        V2_ROUTE_LOCAL_JA,
        V2_ROUTE_HYBRID,
        V2_ROUTE_ASR_ONLY,
        V2_ROUTE_UNRESOLVED,
    }
)
V2_STATES: Final[frozenset[str]] = frozenset(
    {
        V2_TERMINAL_EXISTING_KO,
        V2_READY_FOR_SEMANTIC,
        V2_READY_FOR_VALIDATION,
        V2_READY_TO_PUBLISH,
        V2_FAILED_CLOSED,
    }
)

_ROUTE_STATE: Final[dict[str, str]] = {
    V2_ROUTE_EXISTING_KO: V2_TERMINAL_EXISTING_KO,
    V2_ROUTE_LOCAL_JA: V2_READY_FOR_SEMANTIC,
    V2_ROUTE_HYBRID: V2_READY_FOR_SEMANTIC,
    V2_ROUTE_ASR_ONLY: V2_READY_FOR_SEMANTIC,
    V2_ROUTE_UNRESOLVED: V2_FAILED_CLOSED,
}


class SubtitleV2OrchestratorError(ValueError):
    """Base class for invalid or detached v2 orchestrator contracts."""


class SubtitleV2OrchestratorValidationError(SubtitleV2OrchestratorError):
    """Raised when a route, semantic value, or artifact is unsafe."""


def _validated_alignment(value: object) -> RobustAffineAlignment:
    if not isinstance(value, RobustAffineAlignment):
        raise SubtitleV2OrchestratorValidationError(
            "alignment must be a RobustAffineAlignment"
        )
    try:
        return RobustAffineAlignment(
            scale=value.scale,
            intercept_ms=value.intercept_ms,
            anchor_count=value.anchor_count,
            inlier_count=value.inlier_count,
            residual_threshold_ms=value.residual_threshold_ms,
            residuals=value.residuals,
            median_absolute_residual_ms=value.median_absolute_residual_ms,
        )
    except (AttributeError, TypeError, ValueError, OverflowError) as error:
        raise SubtitleV2OrchestratorValidationError(
            "alignment is invalid or detached"
        ) from error


def project_affine_timestamp_ms(
    alignment: RobustAffineAlignment,
    source_ms: int,
) -> int:
    """Materialize one accepted affine source timestamp deterministically."""

    validated_alignment = _validated_alignment(alignment)
    if type(source_ms) is not int or source_ms < 0:
        raise SubtitleV2OrchestratorValidationError(
            "source_ms must be an exact nonnegative integer"
        )

    try:
        projected = (
            Decimal(str(validated_alignment.scale)) * Decimal(source_ms)
            + Decimal(str(validated_alignment.intercept_ms))
        )
    except (DecimalException, TypeError, ValueError, OverflowError) as error:
        raise SubtitleV2OrchestratorValidationError(
            "affine timestamp projection is not representable"
        ) from error

    if not projected.is_finite() or projected < 0:
        raise SubtitleV2OrchestratorValidationError(
            "affine timestamp projection is negative or nonfinite"
        )

    try:
        materialized = projected.quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
        result = int(materialized)
    except (DecimalException, TypeError, ValueError, OverflowError) as error:
        raise SubtitleV2OrchestratorValidationError(
            "affine timestamp materialization is not representable"
        ) from error

    if type(result) is not int or result < 0:
        raise SubtitleV2OrchestratorValidationError(
            "affine timestamp materialization is negative or invalid"
        )
    return result


def _has_control_characters(value: str) -> bool:
    return any(
        ord(character) < 32
        or ord(character) == 127
        or unicodedata.category(character) == "Cc"
        for character in value
    )


def _validate_cue_id(value: object, *, field_name: str = "cue_id") -> str:
    if type(value) is not str:
        raise SubtitleV2OrchestratorValidationError(
            field_name + " must be an exact string"
        )
    if (
        not value
        or len(value) > MAX_HERMES_V2_CUE_ID_CHARS
        or value != value.strip()
        or any(character.isspace() for character in value)
        or _has_control_characters(value)
    ):
        raise SubtitleV2OrchestratorValidationError(
            field_name + " is not a bounded safe cue identity"
        )
    return value


def _require_exact_nonnegative_int(value: object, *, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise SubtitleV2OrchestratorValidationError(
            field_name + " must be an exact nonnegative integer"
        )
    return value


def _validated_canonical_video(value: object) -> CanonicalVideoHolding:
    if not isinstance(value, CanonicalVideoHolding):
        raise SubtitleV2OrchestratorValidationError(
            "canonical_video must be a CanonicalVideoHolding"
        )

    row = {
        "dvd_id": value.dvd_id,
        "storage_root": "jav",
        "relative_path": value.relative_path,
        "parse_status": "MATCHED",
        "present": 1,
    }
    try:
        validated = validate_canonical_holding(row, value.dvd_id)
    except Exception as error:
        raise SubtitleV2OrchestratorValidationError(
            "canonical_video is not an exact canonical holding"
        ) from error

    if validated != value:
        raise SubtitleV2OrchestratorValidationError(
            "canonical_video identity is detached"
        )
    return validated


def _validated_candidate(value: object) -> SubtitleCandidate:
    if not isinstance(value, SubtitleCandidate):
        raise SubtitleV2OrchestratorValidationError(
            "selected_source must be a SubtitleCandidate"
        )
    try:
        validated = SubtitleCandidate(
            source_kind=value.source_kind,
            language=value.language,
            text_format=value.text_format,
            relative_path=value.relative_path,
            external_source_id=value.external_source_id,
            validated_for_dvd_id=value.validated_for_dvd_id,
        )
    except Exception as error:
        raise SubtitleV2OrchestratorValidationError(
            "selected_source is invalid or detached"
        ) from error
    if validated != value:
        raise SubtitleV2OrchestratorValidationError(
            "selected_source identity is detached"
        )
    return validated


def _validated_document(value: object, *, field_name: str) -> SubtitleDocument:
    if not isinstance(value, SubtitleDocument):
        raise SubtitleV2OrchestratorValidationError(
            field_name + " must be a SubtitleDocument"
        )
    try:
        validated = SubtitleDocument(
            format=value.format,
            cues=value.cues,
            source_sha256=value.source_sha256,
            byte_size=value.byte_size,
        )
    except Exception as error:
        raise SubtitleV2OrchestratorValidationError(
            field_name + " is invalid or detached"
        ) from error
    if validated != value:
        raise SubtitleV2OrchestratorValidationError(
            field_name + " identity is detached"
        )
    return validated


def _validate_sibling_source(
    candidate: SubtitleCandidate,
    canonical_video: CanonicalVideoHolding,
    *,
    language: str,
) -> None:
    if candidate.source_kind != SOURCE_KIND_SIBLING_TEXT:
        raise SubtitleV2OrchestratorValidationError(
            "local route requires a sibling subtitle candidate"
        )
    if candidate.language != language:
        raise SubtitleV2OrchestratorValidationError(
            "selected sibling language does not match the v2 route"
        )
    if not isinstance(candidate.relative_path, str):
        raise SubtitleV2OrchestratorValidationError(
            "selected sibling has no relative path"
        )

    candidate_path = PurePosixPath(candidate.relative_path)
    video_path = PurePosixPath(canonical_video.relative_path)
    if candidate_path.parent != video_path.parent:
        raise SubtitleV2OrchestratorValidationError(
            "selected sibling is outside the canonical DVD directory"
        )

    if candidate_path.suffix.lower() not in {".srt", ".vtt"}:
        raise SubtitleV2OrchestratorValidationError(
            "selected sibling has an unsupported subtitle suffix"
        )

    try:
        parsed = parse_dvd_id(candidate_path.name)
    except Exception as error:
        raise SubtitleV2OrchestratorValidationError(
            "selected sibling DVD identity is malformed"
        ) from error
    if parsed is None or parsed.dvd_id != canonical_video.dvd_id:
        raise SubtitleV2OrchestratorValidationError(
            "selected sibling DVD identity does not match canonical video"
        )

    text_format = candidate_path.suffix[1:].lower()
    stem = candidate_path.name[: -(len(text_format) + 1)]
    parts = stem.split(".")
    if parts[0] != canonical_video.dvd_id or len(parts) not in {1, 2}:
        raise SubtitleV2OrchestratorValidationError(
            "selected sibling is not a canonical sidecar name"
        )
    if len(parts) == 2 and normalize_language(parts[1]) != language:
        raise SubtitleV2OrchestratorValidationError(
            "selected sibling filename language conflicts with route"
        )


def _validated_application(
    value: object,
) -> AlignmentAcceptanceApplicationResult:
    if not isinstance(value, AlignmentAcceptanceApplicationResult):
        raise SubtitleV2OrchestratorValidationError(
            "alignment_application must be an R3 application result"
        )
    try:
        validated = AlignmentAcceptanceApplicationResult(
            decision=value.decision,
            bundle=value.bundle,
            alignment=value.alignment,
        )
    except Exception as error:
        raise SubtitleV2OrchestratorValidationError(
            "alignment_application is invalid or detached"
        ) from error
    if validated != value:
        raise SubtitleV2OrchestratorValidationError(
            "alignment_application identity is detached"
        )
    return validated


def _validated_bundle(value: object) -> HybridEvidenceBundle:
    if not isinstance(value, HybridEvidenceBundle):
        raise SubtitleV2OrchestratorValidationError(
            "evidence_bundle must be a HybridEvidenceBundle"
        )
    try:
        validated = HybridEvidenceBundle(
            dvd_id=value.dvd_id,
            asr_result=value.asr_result,
            cue_evidence=value.cue_evidence,
            alignment=value.alignment,
            external_ja_payload=value.external_ja_payload,
            external_ja_document=value.external_ja_document,
            external_en_payload=value.external_en_payload,
            external_en_document=value.external_en_document,
        )
    except Exception as error:
        raise SubtitleV2OrchestratorValidationError(
            "evidence_bundle is invalid or detached"
        ) from error
    if validated != value:
        raise SubtitleV2OrchestratorValidationError(
            "evidence_bundle identity is detached"
        )
    return validated


def _validate_application_identity(
    application: AlignmentAcceptanceApplicationResult,
    canonical_video: CanonicalVideoHolding,
    *,
    verdict: str,
    provenance: str,
) -> None:
    if application.decision.verdict != verdict:
        raise SubtitleV2OrchestratorValidationError(
            "alignment decision does not match v2 route"
        )
    if application.decision.recommended_provenance != provenance:
        raise SubtitleV2OrchestratorValidationError(
            "alignment recommendation does not match v2 route"
        )
    bundle = application.bundle
    if bundle.dvd_id != canonical_video.dvd_id:
        raise SubtitleV2OrchestratorValidationError(
            "R3 evidence DVD identity does not match canonical video"
        )
    if bundle.asr_result.source_snapshot.dvd_id != canonical_video.dvd_id:
        raise SubtitleV2OrchestratorValidationError(
            "ASR source snapshot DVD identity is detached"
        )
    if bundle.alignment.provenance != provenance:
        raise SubtitleV2OrchestratorValidationError(
            "applied evidence provenance does not match v2 route"
        )


def _validate_asr_only_bundle_identity(
    bundle: HybridEvidenceBundle,
    canonical_video: CanonicalVideoHolding,
) -> None:
    if bundle.dvd_id != canonical_video.dvd_id:
        raise SubtitleV2OrchestratorValidationError(
            "ASR-only evidence DVD identity does not match canonical video"
        )
    if bundle.asr_result.source_snapshot.dvd_id != canonical_video.dvd_id:
        raise SubtitleV2OrchestratorValidationError(
            "ASR-only source snapshot DVD identity is detached"
        )
    if bundle.alignment.provenance != ALIGNMENT_PROVENANCE_ASR_ONLY:
        raise SubtitleV2OrchestratorValidationError(
            "direct ASR-only evidence must have ASR_ONLY provenance"
        )
    if (
        bundle.external_ja_payload is not None
        or bundle.external_ja_document is not None
    ):
        raise SubtitleV2OrchestratorValidationError(
            "ASR-only evidence cannot carry external JA"
        )


def _validated_identity(
    value: object,
    *,
    field_name: str,
) -> HybridCueIdentity:
    if not isinstance(value, HybridCueIdentity):
        raise SubtitleV2OrchestratorValidationError(
            field_name + " must be a HybridCueIdentity"
        )
    try:
        validated = HybridCueIdentity(
            cue_id=value.cue_id,
            source=value.source,
            source_index=value.source_index,
        )
    except Exception as error:
        raise SubtitleV2OrchestratorValidationError(
            field_name + " is invalid or detached"
        ) from error
    if validated != value:
        raise SubtitleV2OrchestratorValidationError(
            field_name + " identity is detached"
        )
    return validated


@dataclass(frozen=True)
class SubtitleV2SemanticBinding:
    """Index-only binding from one Hermes cue to existing source evidence.

    The binding carries no dialogue or timing copy.  ``source_index`` refers
    to the local document ordinal, or to the selected R2 external-JA ordinal
    for ASR-backed routes.  Existing ``HybridCueIdentity`` values identify R2
    sources when the route has them.
    """

    request_cue_id: str
    source_index: int
    external_ja_identity: HybridCueIdentity | None = None
    asr_identity: HybridCueIdentity | None = None

    def __post_init__(self):
        _validate_cue_id(self.request_cue_id, field_name="request_cue_id")
        _require_exact_nonnegative_int(
            self.source_index,
            field_name="semantic binding source_index",
        )
        if self.external_ja_identity is not None:
            _validated_identity(
                self.external_ja_identity,
                field_name="external_ja_identity",
            )
        if self.asr_identity is not None:
            _validated_identity(
                self.asr_identity,
                field_name="asr_identity",
            )


def _validated_binding(value: object) -> SubtitleV2SemanticBinding:
    if not isinstance(value, SubtitleV2SemanticBinding):
        raise SubtitleV2OrchestratorValidationError(
            "semantic_bindings must contain SubtitleV2SemanticBinding values"
        )
    try:
        validated = SubtitleV2SemanticBinding(
            request_cue_id=value.request_cue_id,
            source_index=value.source_index,
            external_ja_identity=value.external_ja_identity,
            asr_identity=value.asr_identity,
        )
    except Exception as error:
        raise SubtitleV2OrchestratorValidationError(
            "semantic binding is invalid or detached"
        ) from error
    if validated != value:
        raise SubtitleV2OrchestratorValidationError(
            "semantic binding identity is detached"
        )
    return validated


def _asr_bundle(route_decision: "SubtitleV2RouteDecision") -> HybridEvidenceBundle:
    if route_decision.route == V2_ROUTE_HYBRID:
        application = route_decision.alignment_application
        if application is None:
            raise SubtitleV2OrchestratorValidationError(
                "hybrid route has no accepted evidence"
            )
        return application.bundle
    if route_decision.route == V2_ROUTE_ASR_ONLY:
        if route_decision.alignment_application is not None:
            return route_decision.alignment_application.bundle
        if route_decision.evidence_bundle is not None:
            return route_decision.evidence_bundle
    raise SubtitleV2OrchestratorValidationError(
        "route has no ASR-backed evidence"
    )


def _validate_semantic_bindings(
    bindings: object,
    route_decision: "SubtitleV2RouteDecision",
    request: HermesV2Request,
) -> tuple[SubtitleV2SemanticBinding, ...]:
    if type(bindings) is not tuple:
        raise SubtitleV2OrchestratorValidationError(
            "semantic_bindings must be an immutable tuple"
        )
    if len(bindings) != len(request.cues):
        raise SubtitleV2OrchestratorValidationError(
            "semantic binding count must equal Hermes request cue count"
        )

    validated = tuple(_validated_binding(binding) for binding in bindings)
    request_ids = tuple(cue.cue_id for cue in request.cues)
    binding_ids = tuple(binding.request_cue_id for binding in validated)
    if binding_ids != request_ids:
        raise SubtitleV2OrchestratorValidationError(
            "semantic binding IDs must equal Hermes request IDs in order"
        )
    if len(set(binding_ids)) != len(binding_ids):
        raise SubtitleV2OrchestratorValidationError(
            "semantic binding IDs must be unique"
        )

    if route_decision.route == V2_ROUTE_LOCAL_JA:
        source_document = route_decision.source_document
        if source_document is None:
            raise SubtitleV2OrchestratorValidationError(
                "local JA route has no source document"
            )
        if len(validated) != len(source_document.cues):
            raise SubtitleV2OrchestratorValidationError(
                "local JA request must cover every source cue"
            )
        for index, (binding, request_cue) in enumerate(
            zip(validated, request.cues)
        ):
            if (
                binding.source_index != index
                or binding.external_ja_identity is not None
                or binding.asr_identity is not None
            ):
                raise SubtitleV2OrchestratorValidationError(
                    "local JA binding is not a direct source ordinal"
                )
            if request_cue.external_ja != source_document.cues[index].text:
                raise SubtitleV2OrchestratorValidationError(
                    "local JA request text is detached from its source cue"
                )
            if request_cue.stt_ja is not None:
                raise SubtitleV2OrchestratorValidationError(
                    "local JA route cannot fabricate STT evidence"
                )
        return validated

    if route_decision.route not in {V2_ROUTE_HYBRID, V2_ROUTE_ASR_ONLY}:
        raise SubtitleV2OrchestratorValidationError(
            "semantic bindings are unsupported for this route"
        )

    bundle = _asr_bundle(route_decision)
    asr_result = bundle.asr_result
    seen_asr_ids = set()

    if route_decision.route == V2_ROUTE_ASR_ONLY:
        if (
            bundle.external_ja_payload is not None
            or bundle.external_ja_document is not None
        ):
            raise SubtitleV2OrchestratorValidationError(
                "ASR-only semantic plan cannot carry external JA"
            )
        if len(validated) != len(bundle.cue_evidence):
            raise SubtitleV2OrchestratorValidationError(
                "ASR-only request must cover every R2 ASR cue"
            )
        for index, (binding, request_cue, evidence) in enumerate(
            zip(validated, request.cues, bundle.cue_evidence)
        ):
            identity = binding.asr_identity
            if (
                identity is None
                or identity.source != EVIDENCE_SOURCE_ASR_SEGMENT
                or identity != evidence.identity
                or binding.source_index != index
                or identity.source_index != index
                or request_cue.cue_id != identity.cue_id
                or request_cue.external_ja is not None
                or request_cue.stt_ja != asr_result.segments[index].text
            ):
                raise SubtitleV2OrchestratorValidationError(
                    "ASR-only semantic evidence is detached"
                )
            if identity.cue_id in seen_asr_ids:
                raise SubtitleV2OrchestratorValidationError(
                    "ASR-only semantic bindings reuse an ASR identity"
                )
            seen_asr_ids.add(identity.cue_id)
            if binding.external_ja_identity is not None:
                raise SubtitleV2OrchestratorValidationError(
                    "ASR-only semantic binding cannot identify external JA"
                )
        return validated

    external_document = bundle.external_ja_document
    if external_document is None or bundle.external_ja_payload is None:
        raise SubtitleV2OrchestratorValidationError(
            "hybrid semantic plan has no external JA evidence"
        )
    if len(validated) != len(bundle.cue_evidence):
        raise SubtitleV2OrchestratorValidationError(
            "hybrid request must cover every R2 external JA cue"
        )
    for index, (binding, request_cue, evidence) in enumerate(
        zip(validated, request.cues, bundle.cue_evidence)
    ):
        external_identity = binding.external_ja_identity
        if (
            external_identity is None
            or external_identity.source != EVIDENCE_SOURCE_EXTERNAL_JA
            or external_identity != evidence.identity
            or binding.source_index != index
            or external_identity.source_index != index
            or request_cue.cue_id != external_identity.cue_id
            or request_cue.external_ja != external_document.cues[index].text
        ):
            raise SubtitleV2OrchestratorValidationError(
                "hybrid external JA evidence is detached"
            )
        asr_identity = binding.asr_identity
        if request_cue.stt_ja is None:
            if asr_identity is not None:
                raise SubtitleV2OrchestratorValidationError(
                    "hybrid ASR binding exists without STT evidence"
                )
        else:
            if (
                asr_identity is None
                or asr_identity.source != EVIDENCE_SOURCE_ASR_SEGMENT
                or asr_identity.source_index >= len(asr_result.segments)
                or asr_identity != HybridCueIdentity.for_asr_segment(
                    asr_identity.source_index
                )
                or request_cue.stt_ja
                != asr_result.segments[asr_identity.source_index].text
            ):
                raise SubtitleV2OrchestratorValidationError(
                    "hybrid STT evidence is detached"
                )
            if asr_identity.cue_id in seen_asr_ids:
                raise SubtitleV2OrchestratorValidationError(
                    "hybrid semantic bindings reuse an ASR identity"
                )
            seen_asr_ids.add(asr_identity.cue_id)
    return validated


def _validated_request(value: object) -> HermesV2Request:
    if not isinstance(value, HermesV2Request):
        raise SubtitleV2OrchestratorValidationError(
            "hermes_request must be a HermesV2Request"
        )
    try:
        validated = HermesV2Request(cues=value.cues)
    except Exception as error:
        raise SubtitleV2OrchestratorValidationError(
            "hermes_request is invalid or detached"
        ) from error
    if validated != value:
        raise SubtitleV2OrchestratorValidationError(
            "hermes_request identity is detached"
        )
    return validated


def _validated_result(value: object, request: HermesV2Request) -> HermesV2Result:
    if not isinstance(value, HermesV2Result):
        raise SubtitleV2OrchestratorValidationError(
            "hermes_result must be a HermesV2Result"
        )
    try:
        validated = HermesV2Result(cues=value.cues)
        validate_hermes_v2_result(validated, request)
    except Exception as error:
        raise SubtitleV2OrchestratorValidationError(
            "hermes_result does not exactly match its request"
        ) from error
    if validated != value:
        raise SubtitleV2OrchestratorValidationError(
            "hermes_result identity is detached"
        )
    return validated


@dataclass(frozen=True)
class SubtitleV2RouteDecision:
    """One canonical v2 route decision and its source-owned evidence."""

    canonical_video: CanonicalVideoHolding
    route: str
    state: str
    selected_source: SubtitleCandidate | None = None
    source_document: SubtitleDocument | None = None
    alignment_application: AlignmentAcceptanceApplicationResult | None = None
    evidence_bundle: HybridEvidenceBundle | None = None

    def __post_init__(self):
        canonical_video = _validated_canonical_video(self.canonical_video)
        if type(self.route) is not str or self.route not in V2_ROUTES:
            raise SubtitleV2OrchestratorValidationError(
                "v2 route is unsupported"
            )
        if type(self.state) is not str or self.state not in V2_STATES:
            raise SubtitleV2OrchestratorValidationError(
                "v2 route state is unsupported"
            )
        if self.state != _ROUTE_STATE[self.route]:
            raise SubtitleV2OrchestratorValidationError(
                "v2 route and state are inconsistent"
            )

        selected_source = self.selected_source
        if selected_source is not None:
            selected_source = _validated_candidate(selected_source)

        source_document = self.source_document
        if source_document is not None:
            source_document = _validated_document(
                source_document,
                field_name="source_document",
            )

        application = self.alignment_application
        if application is not None:
            application = _validated_application(application)

        evidence_bundle = self.evidence_bundle
        if evidence_bundle is not None:
            evidence_bundle = _validated_bundle(evidence_bundle)

        if self.route == V2_ROUTE_EXISTING_KO:
            if selected_source is None:
                raise SubtitleV2OrchestratorValidationError(
                    "existing KO terminal route requires its selected source"
                )
            _validate_sibling_source(
                selected_source,
                canonical_video,
                language="ko",
            )
            if selected_source.relative_path != derive_target_ko_relative(canonical_video):
                raise SubtitleV2OrchestratorValidationError(
                    "existing KO source is not the canonical target"
                )
            if source_document is None:
                raise SubtitleV2OrchestratorValidationError(
                    "existing KO terminal route requires parsed source evidence"
                )
            if (
                source_document.format != "srt"
                or source_document.format != selected_source.text_format
            ):
                raise SubtitleV2OrchestratorValidationError(
                    "existing KO source document must be SRT"
                )
            if application is not None or evidence_bundle is not None:
                raise SubtitleV2OrchestratorValidationError(
                    "existing KO terminal route cannot carry alignment work"
                )
        elif self.route == V2_ROUTE_LOCAL_JA:
            if selected_source is None or source_document is None:
                raise SubtitleV2OrchestratorValidationError(
                    "local JA route requires source candidate and document"
                )
            _validate_sibling_source(
                selected_source,
                canonical_video,
                language="ja",
            )
            if source_document.format != selected_source.text_format:
                raise SubtitleV2OrchestratorValidationError(
                    "local JA document format does not match source"
                )
            if application is not None or evidence_bundle is not None:
                raise SubtitleV2OrchestratorValidationError(
                    "local JA route cannot carry downstream alignment evidence"
                )
        elif self.route == V2_ROUTE_HYBRID:
            if (
                selected_source is not None
                or source_document is not None
                or evidence_bundle is not None
            ):
                raise SubtitleV2OrchestratorValidationError(
                    "hybrid route must use R2 external evidence ownership"
                )
            if application is None:
                raise SubtitleV2OrchestratorValidationError(
                    "hybrid route requires accepted hybrid evidence"
                )
            _validate_application_identity(
                application,
                canonical_video,
                verdict=ACCEPT_HYBRID,
                provenance=ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
            )
            if (
                application.bundle.external_ja_payload is None
                or application.bundle.external_ja_document is None
            ):
                raise SubtitleV2OrchestratorValidationError(
                    "hybrid route requires external JA evidence"
                )
        elif self.route == V2_ROUTE_ASR_ONLY:
            if (
                selected_source is not None
                or source_document is not None
                or (application is not None and evidence_bundle is not None)
            ):
                raise SubtitleV2OrchestratorValidationError(
                    "ASR-only route cannot carry detached or duplicate evidence"
                )
            if application is None:
                if evidence_bundle is None:
                    raise SubtitleV2OrchestratorValidationError(
                        "direct ASR-only route requires canonical R2 evidence"
                    )
                _validate_asr_only_bundle_identity(
                    evidence_bundle,
                    canonical_video,
                )
            else:
                _validate_application_identity(
                    application,
                    canonical_video,
                    verdict=REJECT_EXTERNAL,
                    provenance=ALIGNMENT_PROVENANCE_ASR_ONLY,
                )
                if (
                    application.bundle.external_ja_payload is not None
                    or application.bundle.external_ja_document is not None
                ):
                    raise SubtitleV2OrchestratorValidationError(
                        "ASR-only route cannot carry external JA evidence"
                    )
        else:
            if (
                selected_source is not None
                or source_document is not None
                or evidence_bundle is not None
            ):
                raise SubtitleV2OrchestratorValidationError(
                    "unresolved route cannot carry downstream source work"
                )
            if application is not None:
                _validate_application_identity(
                    application,
                    canonical_video,
                    verdict=UNRESOLVED,
                    provenance=ALIGNMENT_PROVENANCE_UNRESOLVED,
                )

        object.__setattr__(self, "canonical_video", canonical_video)
        object.__setattr__(self, "selected_source", selected_source)
        object.__setattr__(self, "source_document", source_document)
        object.__setattr__(self, "alignment_application", application)
        object.__setattr__(self, "evidence_bundle", evidence_bundle)


@dataclass(frozen=True)
class SubtitleV2SemanticPlan:
    """A v2 route plus one immutable semantic request, before model output."""

    route_decision: SubtitleV2RouteDecision
    hermes_request: HermesV2Request
    semantic_bindings: tuple[SubtitleV2SemanticBinding, ...] = ()

    def __post_init__(self):
        if not isinstance(self.route_decision, SubtitleV2RouteDecision):
            raise SubtitleV2OrchestratorValidationError(
                "route_decision must be a SubtitleV2RouteDecision"
            )
        route_decision = SubtitleV2RouteDecision(
            canonical_video=self.route_decision.canonical_video,
            route=self.route_decision.route,
            state=self.route_decision.state,
            selected_source=self.route_decision.selected_source,
            source_document=self.route_decision.source_document,
            alignment_application=self.route_decision.alignment_application,
            evidence_bundle=self.route_decision.evidence_bundle,
        )
        if route_decision.state != V2_READY_FOR_SEMANTIC:
            raise SubtitleV2OrchestratorValidationError(
                "semantic plan requires a route ready for semantic work"
            )
        hermes_request = _validated_request(self.hermes_request)
        semantic_bindings = _validate_semantic_bindings(
            self.semantic_bindings,
            route_decision,
            hermes_request,
        )
        object.__setattr__(self, "route_decision", route_decision)
        object.__setattr__(self, "hermes_request", hermes_request)
        object.__setattr__(self, "semantic_bindings", semantic_bindings)


@dataclass(frozen=True)
class SubtitleV2SemanticResult:
    """A validated Hermes result tied to its exact immutable semantic plan."""

    semantic_plan: SubtitleV2SemanticPlan
    hermes_result: HermesV2Result

    def __post_init__(self):
        if not isinstance(self.semantic_plan, SubtitleV2SemanticPlan):
            raise SubtitleV2OrchestratorValidationError(
                "semantic_plan must be a SubtitleV2SemanticPlan"
            )
        plan = SubtitleV2SemanticPlan(
            route_decision=self.semantic_plan.route_decision,
            hermes_request=self.semantic_plan.hermes_request,
            semantic_bindings=self.semantic_plan.semantic_bindings,
        )
        hermes_result = _validated_result(
            self.hermes_result,
            plan.hermes_request,
        )
        object.__setattr__(self, "semantic_plan", plan)
        object.__setattr__(self, "hermes_result", hermes_result)


@dataclass(frozen=True)
class SubtitleV2OutputCue:
    """Deterministic output identity plus route-owned timing evidence.

    Korean text is intentionally not copied here: it remains owned by the
    Hermes result and the supplied ``GeneratedKoreanSRT`` artifact.  The
    timing object is either an original source object or a deterministic
    affine-projected ``SubtitleCue``; it is never an LLM timestamp field.
    """

    cue_id: str
    source_index: int
    timing_evidence: SubtitleCue | ASRSegment

    def __post_init__(self):
        _validate_cue_id(self.cue_id)
        _require_exact_nonnegative_int(
            self.source_index,
            field_name="source_index",
        )
        if not isinstance(self.timing_evidence, (SubtitleCue, ASRSegment)):
            raise SubtitleV2OrchestratorValidationError(
                "timing_evidence must be a SubtitleCue or ASRSegment"
            )


def _validated_output_cue(value: object) -> SubtitleV2OutputCue:
    if not isinstance(value, SubtitleV2OutputCue):
        raise SubtitleV2OrchestratorValidationError(
            "output_cues must contain SubtitleV2OutputCue values"
        )
    try:
        validated = SubtitleV2OutputCue(
            cue_id=value.cue_id,
            source_index=value.source_index,
            timing_evidence=value.timing_evidence,
        )
    except Exception as error:
        raise SubtitleV2OrchestratorValidationError(
            "output cue is invalid or detached"
        ) from error
    if validated != value:
        raise SubtitleV2OrchestratorValidationError(
            "output cue identity is detached"
        )
    return validated


def _validated_artifact(value: object) -> GeneratedKoreanSRT:
    if not isinstance(value, GeneratedKoreanSRT):
        raise SubtitleV2OrchestratorValidationError(
            "artifact must be a GeneratedKoreanSRT"
        )
    try:
        validated = GeneratedKoreanSRT(
            state=value.state,
            payload=value.payload,
            cue_count=value.cue_count,
            sha256=value.sha256,
            byte_size=value.byte_size,
        )
    except Exception as error:
        raise SubtitleV2OrchestratorValidationError(
            "artifact is invalid or detached"
        ) from error
    if validated != value:
        raise SubtitleV2OrchestratorValidationError(
            "artifact identity is detached"
        )
    return validated


def _validate_ready_artifact(
    artifact: GeneratedKoreanSRT,
    semantic_result: SubtitleV2SemanticResult,
    output_cues: tuple[SubtitleV2OutputCue, ...],
    route_decision: SubtitleV2RouteDecision,
) -> None:
    if artifact.state != GENERATED_SRT_READY:
        raise SubtitleV2OrchestratorValidationError(
            "ready-to-publish state requires a ready Korean SRT artifact"
        )
    try:
        parsed = parse_subtitle_bytes(artifact.payload, "srt")
        canonical_payload = serialize_srt(parsed)
    except Exception as error:
        raise SubtitleV2OrchestratorValidationError(
            "pre-publication artifact is not a canonical SRT"
        ) from error
    if canonical_payload != artifact.payload:
        raise SubtitleV2OrchestratorValidationError(
            "pre-publication artifact is not canonically serialized"
        )

    result_cues = semantic_result.hermes_result.cues
    if (
        artifact.cue_count != len(parsed.cues)
        or artifact.byte_size != len(artifact.payload)
        or len(parsed.cues) != len(result_cues)
        or len(output_cues) != len(result_cues)
    ):
        raise SubtitleV2OrchestratorValidationError(
            "artifact, semantic result, and output cue counts must match"
        )

    expected_ids = tuple(cue.cue_id for cue in result_cues)
    actual_ids = tuple(cue.cue_id for cue in output_cues)
    if actual_ids != expected_ids or len(set(actual_ids)) != len(actual_ids):
        raise SubtitleV2OrchestratorValidationError(
            "output cue identities do not exactly match Hermes result order"
        )

    previous_source_index = None
    previous_projected_start_ms = None
    semantic_bindings = semantic_result.semantic_plan.semantic_bindings
    if route_decision.route == V2_ROUTE_LOCAL_JA:
        timing_source = route_decision.source_document
        if timing_source is None:
            raise SubtitleV2OrchestratorValidationError(
                "local JA output has no deterministic timing source"
            )
        timing_values = timing_source.cues
    elif route_decision.route == V2_ROUTE_HYBRID:
        application = route_decision.alignment_application
        if application is None or application.alignment is None:
            raise SubtitleV2OrchestratorValidationError(
                "hybrid output has no accepted affine alignment"
            )
        timing_source = _asr_bundle(route_decision).external_ja_document
        if timing_source is None:
            raise SubtitleV2OrchestratorValidationError(
                "hybrid output has no external JA timing source"
            )
        timing_values = timing_source.cues
    elif route_decision.route == V2_ROUTE_ASR_ONLY:
        timing_source = _asr_bundle(route_decision).asr_result
        timing_values = timing_source.segments
    else:
        raise SubtitleV2OrchestratorValidationError(
            "ready artifact route has no deterministic timing ownership"
        )

    for output_cue, artifact_cue, semantic_cue, binding in zip(
        output_cues,
        parsed.cues,
        result_cues,
        semantic_bindings,
    ):
        if route_decision.route == V2_ROUTE_LOCAL_JA:
            expected_source_index = binding.source_index
            if not isinstance(output_cue.timing_evidence, SubtitleCue):
                raise SubtitleV2OrchestratorValidationError(
                    "LOCAL_JA output timing must be a SubtitleCue"
                )
        elif route_decision.route == V2_ROUTE_HYBRID:
            expected_source_index = binding.source_index
            if not isinstance(output_cue.timing_evidence, SubtitleCue):
                raise SubtitleV2OrchestratorValidationError(
                    "HYBRID output timing must be a SubtitleCue"
                )
            external_identity = binding.external_ja_identity
            if (
                external_identity is None
                or external_identity.source != EVIDENCE_SOURCE_EXTERNAL_JA
                or external_identity.source_index != expected_source_index
                or expected_source_index >= len(timing_values)
            ):
                raise SubtitleV2OrchestratorValidationError(
                    "HYBRID output source is detached from external JA"
                )
            source_cue = timing_values[expected_source_index]
            projected_start_ms = project_affine_timestamp_ms(
                route_decision.alignment_application.alignment,
                source_cue.start_ms,
            )
            projected_end_ms = project_affine_timestamp_ms(
                route_decision.alignment_application.alignment,
                source_cue.end_ms,
            )
            try:
                expected_timing = SubtitleCue(
                    start_ms=projected_start_ms,
                    end_ms=projected_end_ms,
                    text=source_cue.text,
                )
            except Exception as error:
                raise SubtitleV2OrchestratorValidationError(
                    "HYBRID projected timing is invalid"
                ) from error
            if (
                previous_projected_start_ms is not None
                and projected_start_ms < previous_projected_start_ms
            ):
                raise SubtitleV2OrchestratorValidationError(
                    "HYBRID projected starts must be nondecreasing"
                )
            previous_projected_start_ms = projected_start_ms
        else:
            if not isinstance(output_cue.timing_evidence, ASRSegment):
                raise SubtitleV2OrchestratorValidationError(
                    "ASR_ONLY output timing must be an ASRSegment"
                )
            if binding.asr_identity is None:
                raise SubtitleV2OrchestratorValidationError(
                    "ASR_ONLY output lacks deterministic ASR binding"
                )
            expected_source_index = binding.asr_identity.source_index
        if expected_source_index >= len(timing_values):
            raise SubtitleV2OrchestratorValidationError(
                "output timing source index is outside deterministic evidence"
            )
        if output_cue.source_index != expected_source_index:
            raise SubtitleV2OrchestratorValidationError(
                "output timing index is detached from semantic source binding"
            )
        if previous_source_index is not None and output_cue.source_index <= previous_source_index:
            raise SubtitleV2OrchestratorValidationError(
                "output timing source indexes must be strictly ordered"
            )
        previous_source_index = output_cue.source_index
        if route_decision.route == V2_ROUTE_LOCAL_JA:
            expected_timing = timing_values[output_cue.source_index]
        elif route_decision.route == V2_ROUTE_ASR_ONLY:
            expected_timing = timing_values[output_cue.source_index]
        if output_cue.timing_evidence != expected_timing:
            raise SubtitleV2OrchestratorValidationError(
                "output timing evidence is detached from its source"
            )
        if (
            artifact_cue.start_ms != expected_timing.start_ms
            or artifact_cue.end_ms != expected_timing.end_ms
        ):
            raise SubtitleV2OrchestratorValidationError(
                "artifact timing does not equal deterministic source timing"
            )
        if artifact_cue.text != semantic_cue.ko:
            raise SubtitleV2OrchestratorValidationError(
                "artifact Korean text does not match semantic result order"
            )


@dataclass(frozen=True)
class SubtitleV2PrePublishResult:
    """Immutable final pre-publication state; no publication is performed."""

    route_decision: SubtitleV2RouteDecision
    state: str
    semantic_result: SubtitleV2SemanticResult | None = None
    output_cues: tuple[SubtitleV2OutputCue, ...] = ()
    artifact: GeneratedKoreanSRT | None = None

    def __post_init__(self):
        if not isinstance(self.route_decision, SubtitleV2RouteDecision):
            raise SubtitleV2OrchestratorValidationError(
                "route_decision must be a SubtitleV2RouteDecision"
            )
        route_decision = SubtitleV2RouteDecision(
            canonical_video=self.route_decision.canonical_video,
            route=self.route_decision.route,
            state=self.route_decision.state,
            selected_source=self.route_decision.selected_source,
            source_document=self.route_decision.source_document,
            alignment_application=self.route_decision.alignment_application,
            evidence_bundle=self.route_decision.evidence_bundle,
        )
        if type(self.state) is not str or self.state not in V2_STATES:
            raise SubtitleV2OrchestratorValidationError(
                "pre-publication state is unsupported"
            )
        if type(self.output_cues) is not tuple:
            raise SubtitleV2OrchestratorValidationError(
                "output_cues must be an immutable tuple"
            )
        if len(self.output_cues) > MAX_SUBTITLE_CUES:
            raise SubtitleV2OrchestratorValidationError(
                "output_cues exceed the bounded cue limit"
            )
        validated_output_cues = tuple(
            _validated_output_cue(output_cue)
            for output_cue in self.output_cues
        )

        semantic_result = self.semantic_result
        if semantic_result is not None:
            if not isinstance(semantic_result, SubtitleV2SemanticResult):
                raise SubtitleV2OrchestratorValidationError(
                    "semantic_result must be a SubtitleV2SemanticResult"
                )
            semantic_result = SubtitleV2SemanticResult(
                semantic_plan=semantic_result.semantic_plan,
                hermes_result=semantic_result.hermes_result,
            )
            if semantic_result.semantic_plan.route_decision != route_decision:
                raise SubtitleV2OrchestratorValidationError(
                    "semantic result route is detached"
                )

        artifact = self.artifact
        if artifact is not None:
            artifact = _validated_artifact(artifact)

        if self.state == V2_TERMINAL_EXISTING_KO:
            if route_decision.route != V2_ROUTE_EXISTING_KO:
                raise SubtitleV2OrchestratorValidationError(
                    "existing-KO terminal state requires existing-KO route"
                )
            if semantic_result is not None or validated_output_cues or artifact is not None:
                raise SubtitleV2OrchestratorValidationError(
                    "existing-KO terminal state cannot carry downstream work"
                )
        elif self.state == V2_FAILED_CLOSED:
            if route_decision.route != V2_ROUTE_UNRESOLVED:
                raise SubtitleV2OrchestratorValidationError(
                    "failed-closed state requires unresolved route"
                )
            if semantic_result is not None or validated_output_cues or artifact is not None:
                raise SubtitleV2OrchestratorValidationError(
                    "failed-closed state cannot carry semantic or publication work"
                )
        elif self.state == V2_READY_FOR_VALIDATION:
            if route_decision.state != V2_READY_FOR_SEMANTIC or semantic_result is None:
                raise SubtitleV2OrchestratorValidationError(
                    "validation-ready state requires a semantic result"
                )
            if validated_output_cues or artifact is not None:
                raise SubtitleV2OrchestratorValidationError(
                    "validation-ready state cannot carry a final artifact"
                )
        elif self.state == V2_READY_TO_PUBLISH:
            if route_decision.state != V2_READY_FOR_SEMANTIC:
                raise SubtitleV2OrchestratorValidationError(
                    "publish-ready state requires a semantic route"
                )
            if semantic_result is None or not validated_output_cues or artifact is None:
                raise SubtitleV2OrchestratorValidationError(
                    "publish-ready state requires semantic result, output cues, and artifact"
                )
            _validate_ready_artifact(
                artifact,
                semantic_result,
                validated_output_cues,
                route_decision,
            )
        else:
            raise SubtitleV2OrchestratorValidationError(
                "READY_FOR_SEMANTIC belongs to route decisions, not pre-publication results"
            )

        object.__setattr__(self, "route_decision", route_decision)
        object.__setattr__(self, "semantic_result", semantic_result)
        object.__setattr__(self, "output_cues", validated_output_cues)
        object.__setattr__(self, "artifact", artifact)


def validate_subtitle_v2_route_decision(
    value: SubtitleV2RouteDecision,
) -> SubtitleV2RouteDecision:
    """Revalidate and return one immutable route decision."""

    if not isinstance(value, SubtitleV2RouteDecision):
        raise SubtitleV2OrchestratorValidationError(
            "value must be a SubtitleV2RouteDecision"
        )
    return SubtitleV2RouteDecision(
        canonical_video=value.canonical_video,
        route=value.route,
        state=value.state,
        selected_source=value.selected_source,
        source_document=value.source_document,
        alignment_application=value.alignment_application,
        evidence_bundle=value.evidence_bundle,
    )


def validate_subtitle_v2_semantic_plan(
    value: SubtitleV2SemanticPlan,
) -> SubtitleV2SemanticPlan:
    """Revalidate and return one immutable semantic plan."""

    if not isinstance(value, SubtitleV2SemanticPlan):
        raise SubtitleV2OrchestratorValidationError(
            "value must be a SubtitleV2SemanticPlan"
        )
    return SubtitleV2SemanticPlan(
        route_decision=value.route_decision,
        hermes_request=value.hermes_request,
        semantic_bindings=value.semantic_bindings,
    )


def validate_subtitle_v2_semantic_result(
    value: SubtitleV2SemanticResult,
) -> SubtitleV2SemanticResult:
    """Revalidate and return one immutable semantic result."""

    if not isinstance(value, SubtitleV2SemanticResult):
        raise SubtitleV2OrchestratorValidationError(
            "value must be a SubtitleV2SemanticResult"
        )
    return SubtitleV2SemanticResult(
        semantic_plan=value.semantic_plan,
        hermes_result=value.hermes_result,
    )


def validate_subtitle_v2_pre_publish_result(
    value: SubtitleV2PrePublishResult,
) -> SubtitleV2PrePublishResult:
    """Revalidate and return one immutable pre-publication result."""

    if not isinstance(value, SubtitleV2PrePublishResult):
        raise SubtitleV2OrchestratorValidationError(
            "value must be a SubtitleV2PrePublishResult"
        )
    return SubtitleV2PrePublishResult(
        route_decision=value.route_decision,
        state=value.state,
        semantic_result=value.semantic_result,
        output_cues=value.output_cues,
        artifact=value.artifact,
    )


__all__ = [
    "V2_FAILED_CLOSED",
    "V2_READY_FOR_SEMANTIC",
    "V2_READY_FOR_VALIDATION",
    "V2_READY_TO_PUBLISH",
    "V2_ROUTES",
    "V2_ROUTE_ASR_ONLY",
    "V2_ROUTE_EXISTING_KO",
    "V2_ROUTE_HYBRID",
    "V2_ROUTE_LOCAL_JA",
    "V2_ROUTE_UNRESOLVED",
    "V2_STATES",
    "V2_TERMINAL_EXISTING_KO",
    "SubtitleV2OrchestratorError",
    "SubtitleV2OrchestratorValidationError",
    "SubtitleV2OutputCue",
    "SubtitleV2PrePublishResult",
    "SubtitleV2RouteDecision",
    "SubtitleV2SemanticBinding",
    "SubtitleV2SemanticPlan",
    "SubtitleV2SemanticResult",
    "project_affine_timestamp_ms",
    "validate_subtitle_v2_pre_publish_result",
    "validate_subtitle_v2_route_decision",
    "validate_subtitle_v2_semantic_plan",
    "validate_subtitle_v2_semantic_result",
]
