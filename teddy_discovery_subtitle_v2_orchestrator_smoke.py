"""Offline smoke tests for the pure Stage11 v2 orchestrator contract."""

from dataclasses import FrozenInstanceError, fields, is_dataclass
import hashlib
import json
from pathlib import Path

from teddy_discovery_alignment import AffineAnchorResidual, RobustAffineAlignment
from teddy_discovery_alignment_acceptance import (
    ACCEPT_HYBRID,
    ALIGNMENT_POLICY_SATISFIED,
    HIGH_MEDIAN_RESIDUAL,
    REJECT_EXTERNAL,
    UNRESOLVED,
    INSUFFICIENT_ANCHOR_COUNT,
    AlignmentAcceptanceDecision,
)
from teddy_discovery_alignment_application import (
    AlignmentAcceptanceApplicationValidationError,
    apply_alignment_acceptance,
)
from teddy_discovery_asr import (
    ASRResult,
    ASRSegment,
    ASRSourceSnapshot,
)
from teddy_discovery_hermes_v2 import (
    HermesV2CueInput,
    HermesV2CueOutput,
    HermesV2Error,
    HermesV2Request,
    HermesV2Result,
)
from teddy_discovery_hybrid_evidence import (
    ALIGNMENT_PROVENANCE_ASR_ONLY,
    ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
    ALIGNMENT_PROVENANCE_UNRESOLVED,
    HybridAlignmentProvenance,
    HybridCueIdentity,
    HybridEvidenceBundle,
)
from teddy_discovery_ko_srt import (
    GENERATED_SRT_READY,
    GeneratedKoreanSRT,
    generate_korean_srt,
)
from teddy_discovery_subtitle import (
    CanonicalVideoHolding,
    SubtitleCandidate,
    validate_canonical_holding,
)
from teddy_discovery_subtitle_external import ExternalSubtitlePayload
from teddy_discovery_subtitle_text import SubtitleCue, parse_subtitle_bytes
from teddy_discovery_subtitle_v2_orchestrator import (
    V2_FAILED_CLOSED,
    V2_READY_FOR_SEMANTIC,
    V2_READY_FOR_VALIDATION,
    V2_READY_TO_PUBLISH,
    V2_ROUTE_ASR_ONLY,
    V2_ROUTE_EXISTING_KO,
    V2_ROUTE_HYBRID,
    V2_ROUTE_LOCAL_JA,
    V2_ROUTE_UNRESOLVED,
    V2_TERMINAL_EXISTING_KO,
    SubtitleV2OrchestratorError,
    SubtitleV2OutputCue,
    SubtitleV2PrePublishResult,
    SubtitleV2RouteDecision,
    SubtitleV2SemanticBinding,
    SubtitleV2SemanticPlan,
    SubtitleV2SemanticResult,
    project_affine_timestamp_ms,
    validate_subtitle_v2_pre_publish_result,
)


DVD_ID = "GEN-123"
JA_URL = "https://source.example.test/subs/11/generic.ja.srt"
EN_URL = "https://source.example.test/subs/12/generic.en.srt"


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


def srt_bytes(
    cues: tuple[tuple[int, int, str], ...],
) -> bytes:
    blocks = []
    for index, (start_ms, end_ms, text) in enumerate(cues, start=1):
        blocks.append(
            f"{index}\n"
            f"00:00:{start_ms // 1000:02d},{start_ms % 1000:03d} "
            f"--> 00:00:{end_ms // 1000:02d},{end_ms % 1000:03d}\n"
            f"{text}"
        )
    return ("\n\n".join(blocks) + "\n").encode("utf-8")


def asr_result(dvd_id: str = DVD_ID) -> ASRResult:
    snapshot = ASRSourceSnapshot.from_holding(
        holding(dvd_id),
        source_size=456_789,
        source_mtime_ns=123_456_789,
    )
    return ASRResult(
        source_snapshot=snapshot,
        source_language="ja",
        segments=(
            ASRSegment(1_000, 1_600, "音声一"),
            ASRSegment(2_000, 2_600, "音声二"),
            ASRSegment(3_000, 3_600, "音声三"),
        ),
        engine_version="orchestrator-contract-smoke",
    )


def external_payload(
    url: str,
    language: str,
    cues: tuple[tuple[int, int, str], ...],
) -> ExternalSubtitlePayload:
    candidate = SubtitleCandidate.validated_external_text(
        url,
        dvd_id=DVD_ID,
        language=language,
        text_format="srt",
    )
    return ExternalSubtitlePayload.from_bytes(
        dvd_id=DVD_ID,
        candidate=candidate,
        payload=srt_bytes(cues),
    )


def hybrid_bundle() -> HybridEvidenceBundle:
    ja_payload = external_payload(
        JA_URL,
        "ja",
        (
            (900, 1_400, "日本語一"),
            (1_500, 2_400, "日本語二"),
            (1_900, 2_400, "日本語三"),
            (2_900, 3_400, "日本語四"),
        ),
    )
    en_payload = external_payload(
        EN_URL,
        "en",
        (
            (900, 1_400, "support one"),
            (1_500, 2_400, "support two"),
            (1_900, 2_400, "support three"),
            (2_900, 3_400, "support four"),
        ),
    )
    return HybridEvidenceBundle.from_external_ja_and_asr(
        dvd_id=DVD_ID,
        external_ja_payload=ja_payload,
        external_ja_document=ja_payload.parse(),
        asr_result=asr_result(),
        alignment=HybridAlignmentProvenance(
            ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
            "generic_hybrid_contract_fixture",
            0.8,
        ),
        external_en_payload=en_payload,
        external_en_document=en_payload.parse(),
    )


def accepted_alignment() -> RobustAffineAlignment:
    residuals = tuple(
        AffineAnchorResidual(
            external_identity=HybridCueIdentity.for_external_ja(external_index),
            asr_identity=HybridCueIdentity.for_asr_segment(asr_index),
            external_midpoint_x2=external_midpoint_x2,
            asr_midpoint_x2=external_midpoint_x2 + 300,
            predicted_asr_midpoint_ms=(external_midpoint_x2 / 2) + 150.0,
            signed_residual_ms=0.0,
            absolute_residual_ms=0.0,
            is_inlier=True,
        )
        for external_index, asr_index, external_midpoint_x2 in (
            (0, 0, 2_300),
            (2, 1, 4_300),
            (3, 2, 6_300),
        )
    )
    return RobustAffineAlignment(
        scale=1.0,
        intercept_ms=150.0,
        anchor_count=3,
        inlier_count=3,
        residual_threshold_ms=1,
        residuals=residuals,
        median_absolute_residual_ms=0.0,
    )


def direct_asr_only_bundle() -> HybridEvidenceBundle:
    return HybridEvidenceBundle.from_asr_only(
        dvd_id=DVD_ID,
        asr_result=asr_result(),
        alignment=HybridAlignmentProvenance(
            ALIGNMENT_PROVENANCE_ASR_ONLY,
            "direct_asr_only_contract_fixture",
            0.7,
        ),
    )


def acceptance_decision(
    verdict: str,
    recommended_provenance: str,
    reason_codes: tuple[str, ...],
) -> AlignmentAcceptanceDecision:
    return AlignmentAcceptanceDecision(
        verdict=verdict,
        recommended_provenance=recommended_provenance,
        reason_codes=reason_codes,
        anchor_count=3,
        inlier_count=3,
        inlier_ratio=1.0,
        median_absolute_residual_ms=0.0,
        external_evidence_span_ms=2_000.0,
        asr_evidence_span_ms=2_000.0,
        scale=1.0,
    )


def hermes_request(
    cue_ids: tuple[str, ...],
    *,
    external: bool = True,
    stt: bool = True,
    external_texts: tuple[str, ...] | None = None,
    stt_texts: tuple[str | None, ...] | None = None,
) -> HermesV2Request:
    resolved_external = external_texts or tuple(
        "外部日本語" for _ in cue_ids
    )
    resolved_stt = stt_texts or tuple("音声日本語" for _ in cue_ids)
    return HermesV2Request(
        cues=tuple(
            HermesV2CueInput(
                cue_id=cue_id,
                external_ja=(resolved_external[index] if external else None),
                stt_ja=(resolved_stt[index] if stt else None),
                en="support evidence",
                before_context=(),
                after_context=(),
            )
            for index, cue_id in enumerate(cue_ids)
        )
    )


def local_bindings(request: HermesV2Request) -> tuple[SubtitleV2SemanticBinding, ...]:
    return tuple(
        SubtitleV2SemanticBinding(cue.cue_id, index)
        for index, cue in enumerate(request.cues)
    )


def asr_only_bindings(
    route: SubtitleV2RouteDecision,
    request: HermesV2Request,
) -> tuple[SubtitleV2SemanticBinding, ...]:
    bundle = (
        route.alignment_application.bundle
        if route.alignment_application is not None
        else route.evidence_bundle
    )
    require(bundle is not None, "ASR_BINDING_FIXTURE_HAS_BUNDLE")
    return tuple(
        SubtitleV2SemanticBinding(
            cue.cue_id,
            index,
            asr_identity=bundle.cue_evidence[index].identity,
        )
        for index, cue in enumerate(request.cues)
    )


def hybrid_bindings(
    route: SubtitleV2RouteDecision,
    request: HermesV2Request,
) -> tuple[SubtitleV2SemanticBinding, ...]:
    require(route.alignment_application is not None, "HYBRID_BINDING_FIXTURE_HAS_APPLICATION")
    bundle = route.alignment_application.bundle
    alignment = route.alignment_application.alignment
    require(alignment is not None, "HYBRID_BINDING_FIXTURE_HAS_ALIGNMENT")
    residuals_by_external_index = {
        residual.external_identity.source_index: residual
        for residual in alignment.residuals
    }
    return tuple(
        SubtitleV2SemanticBinding(
            cue.cue_id,
            index,
            external_ja_identity=bundle.cue_evidence[index].identity,
            asr_identity=(
                residuals_by_external_index[index].asr_identity
                if cue.stt_ja is not None
                else None
            ),
        )
        for index, cue in enumerate(request.cues)
    )


def hermes_result(
    request: HermesV2Request,
    *,
    cue_ids: tuple[str, ...] | None = None,
) -> HermesV2Result:
    ids = cue_ids or tuple(cue.cue_id for cue in request.cues)
    return HermesV2Result(
        cues=tuple(
            HermesV2CueOutput(cue_id, None, "한국어 결과")
            for cue_id in ids
        )
    )


def ready_artifact(
    semantic_result: SubtitleV2SemanticResult,
    timing_evidence: tuple[SubtitleCue | ASRSegment, ...],
) -> tuple[tuple[SubtitleV2OutputCue, ...], GeneratedKoreanSRT]:
    result_cues = semantic_result.hermes_result.cues
    output_cues = tuple(
        SubtitleV2OutputCue(
            cue_id=cue.cue_id,
            source_index=index,
            timing_evidence=evidence,
        )
        for index, (cue, evidence) in enumerate(
            zip(result_cues, timing_evidence)
        )
    )
    artifact = generate_korean_srt(
        tuple(
            SubtitleCue(evidence.start_ms, evidence.end_ms, cue.ko)
            for cue, evidence in zip(result_cues, timing_evidence)
        )
    )
    return output_cues, artifact


def main():
    require(
        (
            V2_ROUTE_EXISTING_KO,
            V2_ROUTE_LOCAL_JA,
            V2_ROUTE_HYBRID,
            V2_ROUTE_ASR_ONLY,
            V2_ROUTE_UNRESOLVED,
        )
        == (
            "EXISTING_KO",
            "LOCAL_JA",
            "HYBRID",
            "ASR_ONLY",
            "UNRESOLVED",
        )
        and (
            V2_TERMINAL_EXISTING_KO,
            V2_READY_FOR_SEMANTIC,
            V2_READY_FOR_VALIDATION,
            V2_READY_TO_PUBLISH,
            V2_FAILED_CLOSED,
        )
        == (
            "TERMINAL_EXISTING_KO",
            "READY_FOR_SEMANTIC",
            "READY_FOR_VALIDATION",
            "READY_TO_PUBLISH",
            "FAILED_CLOSED",
        ),
        "ROUTE_AND_STATE_CONSTANTS_STABLE",
    )

    contract_types = (
        SubtitleV2RouteDecision,
        SubtitleV2SemanticBinding,
        SubtitleV2SemanticPlan,
        SubtitleV2SemanticResult,
        SubtitleV2OutputCue,
        SubtitleV2PrePublishResult,
    )
    require(
        all(is_dataclass(contract_type) for contract_type in contract_types)
        and all(
            getattr(contract_type, "__dataclass_params__").frozen
            for contract_type in contract_types
        ),
        "CONTRACT_DATACLASSES_FROZEN",
    )
    require(
        tuple(field.name for field in fields(SubtitleV2RouteDecision))
        == (
            "canonical_video",
            "route",
            "state",
            "selected_source",
            "source_document",
            "alignment_application",
            "evidence_bundle",
        )
        and tuple(field.name for field in fields(SubtitleV2SemanticPlan))
        == ("route_decision", "hermes_request", "semantic_bindings")
        and tuple(field.name for field in fields(SubtitleV2SemanticResult))
        == ("semantic_plan", "hermes_result")
        and tuple(field.name for field in fields(SubtitleV2OutputCue))
        == ("cue_id", "source_index", "timing_evidence")
        and tuple(field.name for field in fields(SubtitleV2PrePublishResult))
        == (
            "route_decision",
            "state",
            "semantic_result",
            "output_cues",
            "artifact",
        ),
        "CONTRACT_FIELDS_STABLE",
    )

    canonical = holding()
    ko_candidate = SubtitleCandidate.sibling_text(
        "GEN/GEN-123/GEN-123.ko.srt",
        "ko",
    )
    ko_document = parse_subtitle_bytes(
        srt_bytes(((1_000, 1_500, "기존 한국어"),)),
        "srt",
    )
    existing_route = SubtitleV2RouteDecision(
        canonical_video=canonical,
        route=V2_ROUTE_EXISTING_KO,
        state=V2_TERMINAL_EXISTING_KO,
        selected_source=ko_candidate,
        source_document=ko_document,
    )
    require(
        existing_route.route == V2_ROUTE_EXISTING_KO
        and existing_route.state == V2_TERMINAL_EXISTING_KO
        and existing_route.alignment_application is None,
        "VALID_EXISTING_KO_TERMINAL_ACCEPTED",
    )
    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2RouteDecision(
            canonical_video=canonical,
            route=V2_ROUTE_EXISTING_KO,
            state=V2_TERMINAL_EXISTING_KO,
            selected_source=ko_candidate,
        ),
        "EXISTING_KO_REQUIRES_PARSED_DOCUMENT",
    )
    non_srt_ko_document = parse_subtitle_bytes(
        b"WEBVTT\n\n00:00:01.000 --> 00:00:01.500\nexisting\n",
        "vtt",
    )
    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2RouteDecision(
            canonical_video=canonical,
            route=V2_ROUTE_EXISTING_KO,
            state=V2_TERMINAL_EXISTING_KO,
            selected_source=ko_candidate,
            source_document=non_srt_ko_document,
        ),
        "EXISTING_KO_REJECTS_NON_SRT_DOCUMENT",
    )

    bundle = hybrid_bundle()
    direct_bundle = direct_asr_only_bundle()
    alignment = accepted_alignment()
    expect_raises(
        AlignmentAcceptanceApplicationValidationError,
        lambda: apply_alignment_acceptance(
            bundle,
            acceptance_decision(
                ACCEPT_HYBRID,
                ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
                (ALIGNMENT_POLICY_SATISFIED,),
            ),
        ),
        "ACCEPT_HYBRID_MISSING_ALIGNMENT_REJECTED",
    )
    accepted_application = apply_alignment_acceptance(
        bundle,
        acceptance_decision(
            ACCEPT_HYBRID,
            ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
            (ALIGNMENT_POLICY_SATISFIED,),
        ),
        alignment=alignment,
    )
    rejected_application = apply_alignment_acceptance(
        bundle,
        acceptance_decision(
            REJECT_EXTERNAL,
            ALIGNMENT_PROVENANCE_ASR_ONLY,
            (HIGH_MEDIAN_RESIDUAL,),
        ),
    )
    unresolved_application = apply_alignment_acceptance(
        bundle,
        acceptance_decision(
            UNRESOLVED,
            ALIGNMENT_PROVENANCE_UNRESOLVED,
            (INSUFFICIENT_ANCHOR_COUNT,),
        ),
    )

    local_ja_bytes = srt_bytes(
        (
            (1_000, 1_500, "ローカル一"),
            (2_000, 2_500, "ローカル二"),
        )
    )
    local_route = SubtitleV2RouteDecision(
        canonical_video=canonical,
        route=V2_ROUTE_LOCAL_JA,
        state=V2_READY_FOR_SEMANTIC,
        selected_source=SubtitleCandidate.sibling_text(
            "GEN/GEN-123/GEN-123.ja.srt",
            "ja",
        ),
        source_document=parse_subtitle_bytes(local_ja_bytes, "srt"),
    )
    hybrid_route = SubtitleV2RouteDecision(
        canonical_video=canonical,
        route=V2_ROUTE_HYBRID,
        state=V2_READY_FOR_SEMANTIC,
        alignment_application=accepted_application,
    )
    require(
        hybrid_route.alignment_application is not None
        and hybrid_route.alignment_application.alignment == alignment,
        "VALIDATED_APPLICATION_PRESERVES_ACCEPTED_ALIGNMENT",
    )
    detached_application = object.__new__(type(accepted_application))
    object.__setattr__(detached_application, "decision", accepted_application.decision)
    object.__setattr__(detached_application, "bundle", accepted_application.bundle)
    object.__setattr__(detached_application, "alignment", None)
    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2RouteDecision(
            canonical_video=canonical,
            route=V2_ROUTE_HYBRID,
            state=V2_READY_FOR_SEMANTIC,
            alignment_application=detached_application,
        ),
        "DETACHED_ACCEPTED_ALIGNMENT_REJECTED",
    )
    asr_only_route = SubtitleV2RouteDecision(
        canonical_video=canonical,
        route=V2_ROUTE_ASR_ONLY,
        state=V2_READY_FOR_SEMANTIC,
        alignment_application=rejected_application,
    )
    direct_asr_only_route = SubtitleV2RouteDecision(
        canonical_video=canonical,
        route=V2_ROUTE_ASR_ONLY,
        state=V2_READY_FOR_SEMANTIC,
        evidence_bundle=direct_bundle,
    )
    unresolved_route = SubtitleV2RouteDecision(
        canonical_video=canonical,
        route=V2_ROUTE_UNRESOLVED,
        state=V2_FAILED_CLOSED,
        alignment_application=unresolved_application,
    )
    require(
        rejected_application.alignment is None
        and unresolved_application.alignment is None,
        "REJECTED_AND_UNRESOLVED_APPLICATIONS_HAVE_NO_ALIGNMENT",
    )

    local_request = hermes_request(
        ("local-001", "local-002"),
        stt=False,
        external_texts=("ローカル一", "ローカル二"),
    )
    local_plan = SubtitleV2SemanticPlan(
        route_decision=local_route,
        hermes_request=local_request,
        semantic_bindings=local_bindings(local_request),
    )
    hybrid_request = hermes_request(
        ("ja-000001", "ja-000002", "ja-000003", "ja-000004"),
        external_texts=("日本語一", "日本語二", "日本語三", "日本語四"),
        stt_texts=("音声一", None, "音声二", "音声三"),
    )
    hybrid_plan = SubtitleV2SemanticPlan(
        route_decision=hybrid_route,
        hermes_request=hybrid_request,
        semantic_bindings=hybrid_bindings(hybrid_route, hybrid_request),
    )
    asr_only_request = hermes_request(
        ("asr-000001", "asr-000002", "asr-000003"),
        external=False,
        stt_texts=("音声一", "音声二", "音声三"),
    )
    asr_plan = SubtitleV2SemanticPlan(
        route_decision=asr_only_route,
        hermes_request=asr_only_request,
        semantic_bindings=asr_only_bindings(
            asr_only_route,
            asr_only_request,
        ),
    )
    direct_asr_request = hermes_request(
        ("asr-000001", "asr-000002", "asr-000003"),
        external=False,
        stt_texts=("音声一", "音声二", "音声三"),
    )
    direct_asr_plan = SubtitleV2SemanticPlan(
        route_decision=direct_asr_only_route,
        hermes_request=direct_asr_request,
        semantic_bindings=asr_only_bindings(
            direct_asr_only_route,
            direct_asr_request,
        ),
    )
    require(
        local_plan.route_decision == local_route
        and hybrid_plan.route_decision == hybrid_route
        and asr_plan.route_decision == asr_only_route,
        "VALID_LOCAL_HYBRID_AND_BOTH_ASR_ONLY_PLANS_ACCEPTED",
    )
    require(
        direct_asr_only_route.alignment_application is None
        and direct_asr_only_route.evidence_bundle == direct_bundle
        and direct_asr_plan.route_decision == direct_asr_only_route,
        "DIRECT_ASR_ONLY_R2_ROUTE_ACCEPTED_WITHOUT_R3",
    )

    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2RouteDecision(
            canonical_video=canonical,
            route=V2_ROUTE_ASR_ONLY,
            state=V2_READY_FOR_SEMANTIC,
            evidence_bundle=bundle,
        ),
        "DIRECT_ASR_ONLY_REJECTS_EXTERNAL_JA",
    )
    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2RouteDecision(
            canonical_video=holding("GEN-124"),
            route=V2_ROUTE_ASR_ONLY,
            state=V2_READY_FOR_SEMANTIC,
            evidence_bundle=direct_bundle,
        ),
        "DIRECT_ASR_ONLY_DVD_DETACHMENT_REJECTED",
    )

    bad_local_request = hermes_request(
        ("local-001", "local-002"),
        stt=False,
        external_texts=("無関係な日本語", "ローカル二"),
    )
    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2SemanticPlan(
            route_decision=local_route,
            hermes_request=bad_local_request,
            semantic_bindings=local_bindings(bad_local_request),
        ),
        "LOCAL_JA_UNRELATED_TEXT_REJECTED",
    )
    one_local_request = hermes_request(
        ("local-001",),
        stt=False,
        external_texts=("ローカル一",),
    )
    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2SemanticPlan(
            route_decision=local_route,
            hermes_request=one_local_request,
            semantic_bindings=local_bindings(one_local_request),
        ),
        "LOCAL_JA_CUE_COUNT_MISMATCH_REJECTED",
    )
    reordered_local_request = hermes_request(
        ("local-001", "local-002"),
        stt=False,
        external_texts=("ローカル二", "ローカル一"),
    )
    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2SemanticPlan(
            route_decision=local_route,
            hermes_request=reordered_local_request,
            semantic_bindings=local_bindings(reordered_local_request),
        ),
        "LOCAL_JA_ORDER_OR_EVIDENCE_DETACHMENT_REJECTED",
    )
    local_with_fabricated_stt = hermes_request(
        ("local-001", "local-002"),
        stt=True,
        external_texts=("ローカル一", "ローカル二"),
        stt_texts=("偽STT一", "偽STT二"),
    )
    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2SemanticPlan(
            route_decision=local_route,
            hermes_request=local_with_fabricated_stt,
            semantic_bindings=local_bindings(local_with_fabricated_stt),
        ),
        "LOCAL_JA_FABRICATED_STT_REJECTED",
    )

    arbitrary_asr_request = hermes_request(
        ("arbitrary-001", "arbitrary-002", "arbitrary-003"),
        external=False,
        stt_texts=("音声一", "音声二", "音声三"),
    )
    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2SemanticPlan(
            route_decision=asr_only_route,
            hermes_request=arbitrary_asr_request,
            semantic_bindings=asr_only_bindings(
                asr_only_route,
                arbitrary_asr_request,
            ),
        ),
        "ASR_ONLY_ARBITRARY_CUE_ID_REJECTED",
    )
    arbitrary_stt_request = hermes_request(
        ("asr-000001", "asr-000002", "asr-000003"),
        external=False,
        stt_texts=("無関係なSTT", "音声二", "音声三"),
    )
    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2SemanticPlan(
            route_decision=asr_only_route,
            hermes_request=arbitrary_stt_request,
            semantic_bindings=asr_only_bindings(
                asr_only_route,
                arbitrary_stt_request,
            ),
        ),
        "ASR_ONLY_ARBITRARY_STT_REJECTED",
    )
    reordered_asr_request = hermes_request(
        ("asr-000002", "asr-000001", "asr-000003"),
        external=False,
        stt_texts=("音声二", "音声一", "音声三"),
    )
    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2SemanticPlan(
            route_decision=asr_only_route,
            hermes_request=reordered_asr_request,
            semantic_bindings=asr_only_bindings(
                asr_only_route,
                reordered_asr_request,
            ),
        ),
        "ASR_ONLY_REORDERED_SOURCE_EVIDENCE_REJECTED",
    )

    arbitrary_hybrid_request = hermes_request(
        ("arbitrary-001", "arbitrary-002", "arbitrary-003", "arbitrary-004"),
        external_texts=("日本語一", "日本語二", "日本語三", "日本語四"),
        stt_texts=("音声一", None, "音声二", "音声三"),
    )
    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2SemanticPlan(
            route_decision=hybrid_route,
            hermes_request=arbitrary_hybrid_request,
            semantic_bindings=hybrid_bindings(
                hybrid_route,
                arbitrary_hybrid_request,
            ),
        ),
        "HYBRID_ARBITRARY_CUE_ID_REJECTED",
    )
    unrelated_hybrid_request = hermes_request(
        ("ja-000001", "ja-000002", "ja-000003", "ja-000004"),
        external_texts=("無関係な外部", "日本語二", "日本語三", "日本語四"),
        stt_texts=("音声一", None, "音声二", "音声三"),
    )
    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2SemanticPlan(
            route_decision=hybrid_route,
            hermes_request=unrelated_hybrid_request,
            semantic_bindings=hybrid_bindings(
                hybrid_route,
                unrelated_hybrid_request,
            ),
        ),
        "HYBRID_UNRELATED_EXTERNAL_JA_REJECTED",
    )
    unrelated_hybrid_stt_request = hermes_request(
        ("ja-000001", "ja-000002", "ja-000003", "ja-000004"),
        external_texts=("日本語一", "日本語二", "日本語三", "日本語四"),
        stt_texts=("無関係なSTT", None, "音声二", "音声三"),
    )
    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2SemanticPlan(
            route_decision=hybrid_route,
            hermes_request=unrelated_hybrid_stt_request,
            semantic_bindings=hybrid_bindings(
                hybrid_route,
                unrelated_hybrid_stt_request,
            ),
        ),
        "HYBRID_UNRELATED_STT_REJECTED",
    )
    duplicate_hybrid_bindings = (
        hybrid_plan.semantic_bindings[0],
        hybrid_plan.semantic_bindings[1],
        SubtitleV2SemanticBinding(
            "ja-000003",
            2,
            external_ja_identity=bundle.cue_evidence[2].identity,
            asr_identity=HybridCueIdentity.for_asr_segment(0),
        ),
        hybrid_plan.semantic_bindings[3],
    )
    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2SemanticPlan(
            route_decision=hybrid_route,
            hermes_request=hybrid_request,
            semantic_bindings=duplicate_hybrid_bindings,
        ),
        "HYBRID_DUPLICATE_ASR_BINDING_REJECTED",
    )
    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2SemanticPlan(
            route_decision=local_route,
            hermes_request=local_request,
            semantic_bindings=local_plan.semantic_bindings[:1],
        ),
        "MISSING_SEMANTIC_BINDING_REJECTED",
    )
    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2SemanticPlan(
            route_decision=local_route,
            hermes_request=local_request,
            semantic_bindings=local_plan.semantic_bindings
            + (SubtitleV2SemanticBinding("extra", 2),),
        ),
        "EXTRA_SEMANTIC_BINDING_REJECTED",
    )

    local_semantic_result = SubtitleV2SemanticResult(
        semantic_plan=local_plan,
        hermes_result=hermes_result(local_plan.hermes_request),
    )
    hybrid_semantic_result = SubtitleV2SemanticResult(
        semantic_plan=hybrid_plan,
        hermes_result=hermes_result(hybrid_plan.hermes_request),
    )
    asr_semantic_result = SubtitleV2SemanticResult(
        semantic_plan=asr_plan,
        hermes_result=hermes_result(asr_plan.hermes_request),
    )
    direct_asr_semantic_result = SubtitleV2SemanticResult(
        semantic_plan=direct_asr_plan,
        hermes_result=hermes_result(direct_asr_plan.hermes_request),
    )
    require(
        local_semantic_result.hermes_result.cues[0].cue_id == "local-001"
        and hybrid_semantic_result.hermes_result.cues[1].cue_id == "ja-000002",
        "HERMES_REQUEST_RESULT_CUE_ID_ORDER_BOUND",
    )

    local_output_cues, local_artifact = ready_artifact(
        local_semantic_result,
        local_route.source_document.cues,
    )
    hybrid_source_cues = hybrid_route.alignment_application.bundle.external_ja_document.cues
    hybrid_projected_timing = tuple(
        SubtitleCue(
            start_ms=project_affine_timestamp_ms(
                alignment,
                source_cue.start_ms,
            ),
            end_ms=project_affine_timestamp_ms(
                alignment,
                source_cue.end_ms,
            ),
            text=source_cue.text,
        )
        for source_cue in hybrid_source_cues
    )
    hybrid_output_cues, hybrid_artifact = ready_artifact(
        hybrid_semantic_result,
        hybrid_projected_timing,
    )
    hybrid_pre_publish = SubtitleV2PrePublishResult(
        route_decision=hybrid_route,
        state=V2_READY_TO_PUBLISH,
        semantic_result=hybrid_semantic_result,
        output_cues=hybrid_output_cues,
        artifact=hybrid_artifact,
    )
    asr_output_cues, asr_artifact = ready_artifact(
        asr_semantic_result,
        asr_only_route.alignment_application.bundle.asr_result.segments,
    )
    asr_pre_publish = SubtitleV2PrePublishResult(
        route_decision=asr_only_route,
        state=V2_READY_TO_PUBLISH,
        semantic_result=asr_semantic_result,
        output_cues=asr_output_cues,
        artifact=asr_artifact,
    )
    direct_asr_output_cues, direct_asr_artifact = ready_artifact(
        direct_asr_semantic_result,
        direct_asr_only_route.evidence_bundle.asr_result.segments,
    )
    direct_asr_pre_publish = SubtitleV2PrePublishResult(
        route_decision=direct_asr_only_route,
        state=V2_READY_TO_PUBLISH,
        semantic_result=direct_asr_semantic_result,
        output_cues=direct_asr_output_cues,
        artifact=direct_asr_artifact,
    )
    require(
        tuple(type(output.timing_evidence) for output in hybrid_output_cues)
        == (SubtitleCue, SubtitleCue, SubtitleCue, SubtitleCue)
        and tuple(output.source_index for output in hybrid_output_cues)
        == (0, 1, 2, 3)
        and tuple(
            binding.asr_identity.source_index
            if binding.asr_identity is not None
            else None
            for binding in hybrid_plan.semantic_bindings
        )
        == (0, None, 1, 2)
        and tuple(
            (cue.start_ms, cue.end_ms)
            for cue in parse_subtitle_bytes(hybrid_artifact.payload, "srt").cues
        )
        == tuple(
            (cue.start_ms, cue.end_ms)
            for cue in hybrid_projected_timing
        )
        and (
            hybrid_projected_timing[0].start_ms,
            hybrid_projected_timing[0].end_ms,
        )
        != (
            asr_result().segments[0].start_ms,
            asr_result().segments[0].end_ms,
        )
        and asr_pre_publish.artifact is not None
        and direct_asr_pre_publish.artifact is not None,
        "ROUTE_SPECIFIC_TIMING_OWNERSHIP_ACCEPTED",
    )
    wrong_projected_timing = (
        SubtitleCue(
            hybrid_projected_timing[0].start_ms + 1,
            hybrid_projected_timing[0].end_ms,
            hybrid_projected_timing[0].text,
        ),
        *hybrid_projected_timing[1:],
    )
    wrong_output_cues, wrong_artifact = ready_artifact(
        hybrid_semantic_result,
        wrong_projected_timing,
    )
    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2PrePublishResult(
            route_decision=hybrid_route,
            state=V2_READY_TO_PUBLISH,
            semantic_result=hybrid_semantic_result,
            output_cues=wrong_output_cues,
            artifact=wrong_artifact,
        ),
        "HYBRID_ARTIFACT_TIMING_NOT_AFFINE_PROJECTION_REJECTED",
    )
    arbitrary_projected_timing = tuple(
        SubtitleCue(source_cue.start_ms, source_cue.end_ms, source_cue.text)
        for source_cue in hybrid_source_cues
    )
    arbitrary_output_cues, arbitrary_artifact = ready_artifact(
        hybrid_semantic_result,
        arbitrary_projected_timing,
    )
    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2PrePublishResult(
            route_decision=hybrid_route,
            state=V2_READY_TO_PUBLISH,
            semantic_result=hybrid_semantic_result,
            output_cues=arbitrary_output_cues,
            artifact=arbitrary_artifact,
        ),
        "HYBRID_ARBITRARY_SUBTITLE_CUE_REJECTED",
    )
    local_pre_publish = SubtitleV2PrePublishResult(
        route_decision=local_route,
        state=V2_READY_TO_PUBLISH,
        semantic_result=local_semantic_result,
        output_cues=local_output_cues,
        artifact=local_artifact,
    )
    validation_ready = SubtitleV2PrePublishResult(
        route_decision=local_route,
        state=V2_READY_FOR_VALIDATION,
        semantic_result=local_semantic_result,
    )
    existing_pre_publish = SubtitleV2PrePublishResult(
        route_decision=existing_route,
        state=V2_TERMINAL_EXISTING_KO,
    )
    unresolved_pre_publish = SubtitleV2PrePublishResult(
        route_decision=unresolved_route,
        state=V2_FAILED_CLOSED,
    )
    require(
        local_pre_publish.artifact is not None
        and local_pre_publish.artifact.state == GENERATED_SRT_READY
        and validation_ready.semantic_result == local_semantic_result
        and existing_pre_publish.artifact is None
        and unresolved_pre_publish.state == V2_FAILED_CLOSED,
        "VALID_PREPUBLICATION_STATES_ACCEPTED",
    )

    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2RouteDecision(
            canonical_video=canonical,
            route=V2_ROUTE_EXISTING_KO,
            state=V2_TERMINAL_EXISTING_KO,
            selected_source=ko_candidate,
            alignment_application=accepted_application,
        ),
        "EXISTING_KO_REJECTS_DOWNSTREAM_ALIGNMENT",
    )
    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2SemanticPlan(
            route_decision=existing_route,
            hermes_request=local_plan.hermes_request,
        ),
        "EXISTING_KO_REJECTS_SEMANTIC_PLAN",
    )
    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2PrePublishResult(
            route_decision=existing_route,
            state=V2_READY_TO_PUBLISH,
            semantic_result=local_semantic_result,
            output_cues=local_output_cues,
            artifact=local_artifact,
        ),
        "EXISTING_KO_REJECTS_PUBLISH_READY_STATE",
    )
    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2RouteDecision(
            canonical_video=canonical,
            route=V2_ROUTE_HYBRID,
            state=V2_READY_FOR_SEMANTIC,
            alignment_application=rejected_application,
        ),
        "HYBRID_REJECTS_ASR_ONLY_PROVENANCE",
    )
    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2RouteDecision(
            canonical_video=canonical,
            route=V2_ROUTE_ASR_ONLY,
            state=V2_READY_FOR_SEMANTIC,
            alignment_application=accepted_application,
        ),
        "ASR_ONLY_REJECTS_HYBRID_PROVENANCE",
    )
    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2SemanticPlan(
            route_decision=unresolved_route,
            hermes_request=local_plan.hermes_request,
        ),
        "UNRESOLVED_REJECTS_SEMANTIC_PLAN",
    )
    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2PrePublishResult(
            route_decision=unresolved_route,
            state=V2_READY_TO_PUBLISH,
        ),
        "UNRESOLVED_CANNOT_BE_PUBLISH_READY",
    )
    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2RouteDecision(
            canonical_video=holding("GEN-124"),
            route=V2_ROUTE_HYBRID,
            state=V2_READY_FOR_SEMANTIC,
            alignment_application=accepted_application,
        ),
        "CANONICAL_DVD_DETACHMENT_REJECTED",
    )

    for malformed_result, marker in (
        (
            hermes_result(local_plan.hermes_request, cue_ids=("local-001",)),
            "MISSING_HERMES_CUE_REJECTED",
        ),
        (
            hermes_result(
                local_plan.hermes_request,
                cue_ids=("local-001", "local-002", "extra"),
            ),
            "EXTRA_HERMES_CUE_REJECTED",
        ),
        (
            hermes_result(
                local_plan.hermes_request,
                cue_ids=("local-002", "local-001"),
            ),
            "REORDERED_HERMES_CUE_REJECTED",
        ),
        (
            hermes_result(
                local_plan.hermes_request,
                cue_ids=("wrong", "local-002"),
            ),
            "MISMATCHED_HERMES_CUE_REJECTED",
        ),
    ):
        expect_raises(
            SubtitleV2OrchestratorError,
            lambda malformed=malformed_result: SubtitleV2SemanticResult(
                semantic_plan=local_plan,
                hermes_result=malformed,
            ),
            marker,
        )
    expect_raises(
        (SubtitleV2OrchestratorError, HermesV2Error),
        lambda: hermes_result(
            local_plan.hermes_request,
            cue_ids=("local-001", "local-001"),
        ),
        "DUPLICATE_HERMES_CUE_REJECTED",
    )

    mismatched_output_cues, mismatched_artifact = ready_artifact(
        local_semantic_result,
        local_route.source_document.cues[:1],
    )
    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2PrePublishResult(
            route_decision=local_route,
            state=V2_READY_TO_PUBLISH,
            semantic_result=local_semantic_result,
            output_cues=mismatched_output_cues,
            artifact=mismatched_artifact,
        ),
        "TIMING_AND_OUTPUT_CUE_COUNT_MISMATCH_REJECTED",
    )
    duplicate_output = (
        local_output_cues[0],
        SubtitleV2OutputCue(
            cue_id=local_output_cues[0].cue_id,
            source_index=1,
            timing_evidence=local_output_cues[1].timing_evidence,
        ),
    )
    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2PrePublishResult(
            route_decision=local_route,
            state=V2_READY_TO_PUBLISH,
            semantic_result=local_semantic_result,
            output_cues=duplicate_output,
            artifact=local_artifact,
        ),
        "DUPLICATE_OUTPUT_CUE_ID_REJECTED",
    )

    for callback, marker in (
        (
            lambda: SubtitleV2RouteDecision(
                canonical_video=canonical,
                route=V2_ROUTE_LOCAL_JA,
                state=V2_READY_FOR_SEMANTIC,
                selected_source=[],
                source_document=local_route.source_document,
            ),
            "MUTABLE_SOURCE_OBJECT_REJECTED",
        ),
        (
            lambda: SubtitleV2RouteDecision(
                canonical_video=canonical,
                route=V2_ROUTE_LOCAL_JA,
                state=V2_READY_FOR_SEMANTIC,
                selected_source=local_route.selected_source,
                source_document={},
            ),
            "MUTABLE_DOCUMENT_OBJECT_REJECTED",
        ),
        (
            lambda: SubtitleV2SemanticPlan(
                route_decision=local_route,
                hermes_request=[],
            ),
            "MUTABLE_HERMES_REQUEST_REJECTED",
        ),
        (
            lambda: SubtitleV2SemanticPlan(
                route_decision=local_route,
                hermes_request=local_request,
                semantic_bindings=list(local_plan.semantic_bindings),
            ),
            "MUTABLE_SEMANTIC_BINDINGS_REJECTED",
        ),
        (
            lambda: SubtitleV2SemanticPlan(
                route_decision=local_route,
                hermes_request=local_request,
                semantic_bindings=("not-a-binding", "not-a-binding"),
            ),
            "WRONG_SEMANTIC_BINDING_TYPE_REJECTED",
        ),
        (
            lambda: SubtitleV2PrePublishResult(
                route_decision=local_route,
                state=V2_READY_TO_PUBLISH,
                semantic_result=local_semantic_result,
                output_cues=list(local_output_cues),
                artifact=local_artifact,
            ),
            "MUTABLE_OUTPUT_CUES_REJECTED",
        ),
    ):
        expect_raises(SubtitleV2OrchestratorError, callback, marker)

    require(
        not {
            field.name
            for contract_type in (
                *contract_types,
            )
            for field in fields(contract_type)
        }.intersection({"timestamp", "start_ms", "end_ms", "aligned_start_ms", "aligned_end_ms"}),
        "NO_LLM_TIMESTAMP_FIELDS",
    )
    hermes_field_names = {
        field.name
        for contract_type in (
            HermesV2CueInput,
            HermesV2CueOutput,
        )
        for field in fields(contract_type)
    }
    require(
        not hermes_field_names.intersection(
            {"timestamp", "start_ms", "end_ms", "timing", "timing_evidence"}
        ),
        "HERMES_OBJECTS_HAVE_NO_TIMESTAMP_OWNERSHIP",
    )

    orchestrator_source = Path(__file__).with_name(
        "teddy_discovery_subtitle_v2_orchestrator.py"
    ).read_text(encoding="utf-8").lower()
    for forbidden, marker in (
        ("jur-750", "NO_TITLE_SPECIFIC_PRODUCTION_LOGIC"),
        ("run_subtitle_pipeline", "NO_LEGACY_PIPELINE_WIRING"),
        ("subprocess", "NO_SUBPROCESS_EXECUTION"),
        ("sqlite3", "NO_DATABASE_ACCESS"),
        ("urllib", "NO_NETWORK_ACCESS"),
        ("requests", "NO_HTTP_ACCESS"),
        ("socket", "NO_SOCKET_ACCESS"),
        ("open(", "NO_FILESYSTEM_ACCESS"),
        ("hermes_v2_transport", "NO_HERMES_TRANSPORT_WIRING"),
        ("teddy_discovery_subtitle_publish", "NO_PUBLICATION_WIRING"),
        ("asr_transcribe", "NO_ASR_EXECUTION"),
        ("invoke_hermes", "NO_MODEL_EXECUTION"),
    ):
        require(forbidden not in orchestrator_source, marker)
    require(
        "192.168." not in orchestrator_source
        and "/home/teddy" not in orchestrator_source
        and "credential" not in orchestrator_source,
        "NO_REMOTE_CREDENTIAL_OR_SSH_OWNERSHIP",
    )
    require(
        "stable_cue_id" not in orchestrator_source
        and "hybridcueidentity.for_" in orchestrator_source,
        "NO_ALTERNATE_CUE_ID_ALGORITHM",
    )

    # The final artifact is checked, never generated, written, or published by
    # the production contract.  Its existing owner remains the only artifact
    # object held here.
    require(
        isinstance(local_pre_publish.artifact, GeneratedKoreanSRT)
        and hashlib.sha256(local_pre_publish.artifact.payload).hexdigest()
        == local_pre_publish.artifact.sha256,
        "ARTIFACT_IS_EXISTING_IMMUTABLE_OWNER",
    )
    require(
        validate_subtitle_v2_pre_publish_result(local_pre_publish)
        == local_pre_publish,
        "DETERMINISTIC_REVALIDATION",
    )
    try:
        setattr(local_pre_publish, "state", V2_FAILED_CLOSED)
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError("PREPUBLISH_RESULT_MUST_BE_FROZEN")

    print("SUBTITLE_V2_ORCHESTRATOR_SMOKE_PASS")


if __name__ == "__main__":
    main()
