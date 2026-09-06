"""Offline smoke tests for the Stage11 v2 execution composition boundary."""

from dataclasses import FrozenInstanceError, fields, is_dataclass
import ast
import inspect
from pathlib import Path

from teddy_discovery_alignment import AffineAnchorResidual, RobustAffineAlignment
from teddy_discovery_alignment_acceptance import (
    ACCEPT_HYBRID,
    ALIGNMENT_POLICY_SATISFIED,
    HIGH_MEDIAN_RESIDUAL,
    REJECT_EXTERNAL,
    UNRESOLVED,
    AlignmentAcceptanceDecision,
)
from teddy_discovery_alignment_application import apply_alignment_acceptance
from teddy_discovery_asr import ASRResult, ASRSegment, ASRSourceSnapshot
from teddy_discovery_hermes_v2 import (
    HermesV2CueOutput,
    HermesV2Request,
    HermesV2Result,
)
from teddy_discovery_hybrid_evidence import (
    ALIGNMENT_PROVENANCE_ASR_ONLY,
    ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
    ALIGNMENT_PROVENANCE_UNRESOLVED,
    NEIGHBOR_SOURCE_ASR_SEGMENT,
    NEIGHBOR_SOURCE_EXTERNAL_EN,
    HybridAlignmentProvenance,
    HybridEvidenceBundle,
    HybridCueIdentity,
    HybridNeighborReference,
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
    V2_READY_TO_PUBLISH,
    V2_ROUTE_ASR_ONLY,
    V2_ROUTE_EXISTING_KO,
    V2_ROUTE_HYBRID,
    V2_ROUTE_LOCAL_JA,
    V2_ROUTE_UNRESOLVED,
    V2_TERMINAL_EXISTING_KO,
    SubtitleV2OrchestratorError,
    SubtitleV2OrchestratorValidationError,
    SubtitleV2RouteDecision,
)
from teddy_discovery_subtitle_v2_pipeline import (
    SubtitleV2PipelineError,
    project_affine_timestamp_ms,
    run_subtitle_v2_pipeline,
)


DVD_ID = "GEN-123"


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
    family = dvd_id.split("-", 1)[0]
    return validate_canonical_holding(
        {
            "dvd_id": dvd_id,
            "storage_root": "jav",
            "relative_path": f"{family}/{dvd_id}/{dvd_id}.mp4",
            "parse_status": "MATCHED",
            "present": 1,
        },
        dvd_id,
    )


def srt_bytes(cues: tuple[tuple[int, int, str], ...]) -> bytes:
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
        source_size=123_456,
        source_mtime_ns=654_321,
    )
    return ASRResult(
        source_snapshot=snapshot,
        source_language="ja",
        segments=(
            ASRSegment(1_000, 1_500, "音声一"),
            ASRSegment(2_000, 2_500, "音声二"),
            ASRSegment(3_000, 3_500, "音声三"),
        ),
        engine_version="v2-pipeline-smoke",
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
        "https://source.example.test/ja.srt",
        "ja",
        (
            (900, 1_400, "日本語一"),
            (1_500, 2_400, "日本語二"),
            (1_900, 2_400, "日本語三"),
            (2_900, 3_400, "日本語四"),
        ),
    )
    en_payload = external_payload(
        "https://source.example.test/en.srt",
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
            "v2_pipeline_hybrid_fixture",
            0.8,
        ),
        external_en_payload=en_payload,
        external_en_document=en_payload.parse(),
        before_context=(
            HybridNeighborReference(NEIGHBOR_SOURCE_ASR_SEGMENT, 0),
        ),
        after_context=(
            HybridNeighborReference(NEIGHBOR_SOURCE_EXTERNAL_EN, 0),
        ),
    )


def hybrid_alignment() -> RobustAffineAlignment:
    residuals = tuple(
        AffineAnchorResidual(
            external_identity=HybridCueIdentity.for_external_ja(external_index),
            asr_identity=HybridCueIdentity.for_asr_segment(asr_index),
            external_midpoint_x2=external_midpoint_x2,
            asr_midpoint_x2=external_midpoint_x2 + 200,
            predicted_asr_midpoint_ms=(external_midpoint_x2 / 2) + 100.0,
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
        intercept_ms=100.0,
        anchor_count=3,
        inlier_count=3,
        residual_threshold_ms=1,
        residuals=residuals,
        median_absolute_residual_ms=0.0,
    )


def affine_fixture(scale: float, intercept_ms: float) -> RobustAffineAlignment:
    residuals = tuple(
        AffineAnchorResidual(
            external_identity=HybridCueIdentity.for_external_ja(index),
            asr_identity=HybridCueIdentity.for_asr_segment(index),
            external_midpoint_x2=external_midpoint_x2,
            asr_midpoint_x2=int(
                scale * external_midpoint_x2 + 2 * intercept_ms
            ),
            predicted_asr_midpoint_ms=(
                scale * (external_midpoint_x2 / 2) + intercept_ms
            ),
            signed_residual_ms=0.0,
            absolute_residual_ms=0.0,
            is_inlier=True,
        )
        for index, external_midpoint_x2 in enumerate((2_300, 4_300, 6_300))
    )
    return RobustAffineAlignment(
        scale=scale,
        intercept_ms=intercept_ms,
        anchor_count=3,
        inlier_count=3,
        residual_threshold_ms=1,
        residuals=residuals,
        median_absolute_residual_ms=0.0,
    )


def direct_asr_bundle() -> HybridEvidenceBundle:
    return HybridEvidenceBundle.from_asr_only(
        dvd_id=DVD_ID,
        asr_result=asr_result(),
        alignment=HybridAlignmentProvenance(
            ALIGNMENT_PROVENANCE_ASR_ONLY,
            "v2_pipeline_direct_asr_fixture",
            0.7,
        ),
    )


def decision(
    verdict: str,
    provenance: str,
    reason: str,
) -> AlignmentAcceptanceDecision:
    return AlignmentAcceptanceDecision(
        verdict=verdict,
        recommended_provenance=provenance,
        reason_codes=(reason,),
        anchor_count=3,
        inlier_count=3,
        inlier_ratio=1.0,
        median_absolute_residual_ms=0.0,
        external_evidence_span_ms=2_000.0,
        asr_evidence_span_ms=2_000.0,
        scale=1.0,
    )


def local_route() -> SubtitleV2RouteDecision:
    source = srt_bytes(
        (
            (1_000, 1_500, "ローカル一"),
            (2_000, 2_500, "ローカル二"),
        )
    )
    return SubtitleV2RouteDecision(
        canonical_video=holding(),
        route=V2_ROUTE_LOCAL_JA,
        state=V2_READY_FOR_SEMANTIC,
        selected_source=SubtitleCandidate.sibling_text(
            "GEN/GEN-123/GEN-123.ja.srt",
            "ja",
        ),
        source_document=parse_subtitle_bytes(source, "srt"),
    )


def existing_ko_route() -> SubtitleV2RouteDecision:
    return SubtitleV2RouteDecision(
        canonical_video=holding(),
        route=V2_ROUTE_EXISTING_KO,
        state=V2_TERMINAL_EXISTING_KO,
        selected_source=SubtitleCandidate.sibling_text(
            "GEN/GEN-123/GEN-123.ko.srt",
            "ko",
        ),
        source_document=parse_subtitle_bytes(
            srt_bytes(((1_000, 1_500, "기존 한국어"),)),
            "srt",
        ),
    )


def accepted_hybrid_route() -> SubtitleV2RouteDecision:
    bundle = hybrid_bundle()
    application = apply_alignment_acceptance(
        bundle,
        decision(
            ACCEPT_HYBRID,
            ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
            ALIGNMENT_POLICY_SATISFIED,
        ),
        alignment=hybrid_alignment(),
    )
    return SubtitleV2RouteDecision(
        canonical_video=holding(),
        route=V2_ROUTE_HYBRID,
        state=V2_READY_FOR_SEMANTIC,
        alignment_application=application,
    )


def rejected_asr_route() -> SubtitleV2RouteDecision:
    application = apply_alignment_acceptance(
        hybrid_bundle(),
        decision(
            REJECT_EXTERNAL,
            ALIGNMENT_PROVENANCE_ASR_ONLY,
            HIGH_MEDIAN_RESIDUAL,
        ),
    )
    return SubtitleV2RouteDecision(
        canonical_video=holding(),
        route=V2_ROUTE_ASR_ONLY,
        state=V2_READY_FOR_SEMANTIC,
        alignment_application=application,
    )


def direct_asr_route() -> SubtitleV2RouteDecision:
    return SubtitleV2RouteDecision(
        canonical_video=holding(),
        route=V2_ROUTE_ASR_ONLY,
        state=V2_READY_FOR_SEMANTIC,
        evidence_bundle=direct_asr_bundle(),
    )


def unresolved_route() -> SubtitleV2RouteDecision:
    return SubtitleV2RouteDecision(
        canonical_video=holding(),
        route=V2_ROUTE_UNRESOLVED,
        state=V2_FAILED_CLOSED,
        alignment_application=apply_alignment_acceptance(
            hybrid_bundle(),
            decision(
                UNRESOLVED,
                ALIGNMENT_PROVENANCE_UNRESOLVED,
                "INSUFFICIENT_ANCHOR_COUNT",
            ),
        ),
    )


class FakeSemanticBoundary:
    def __init__(self, mode: str = "valid"):
        self.mode = mode
        self.calls = 0
        self.requests: list[HermesV2Request] = []

    def __call__(self, request: HermesV2Request) -> HermesV2Result:
        self.calls += 1
        self.requests.append(request)
        outputs = tuple(
            HermesV2CueOutput(cue.cue_id, None, f"한국어-{index + 1}")
            for index, cue in enumerate(request.cues)
        )
        if self.mode == "missing":
            return HermesV2Result(cues=outputs[:-1])
        if self.mode == "extra":
            return HermesV2Result(
                cues=outputs
                + (HermesV2CueOutput("extra-cue", None, "추가"),)
            )
        if self.mode == "reordered":
            return HermesV2Result(cues=tuple(reversed(outputs)))
        if self.mode == "duplicate":
            result = HermesV2Result(cues=outputs)
            object.__setattr__(result, "cues", (outputs[0], outputs[0]))
            return result
        if self.mode == "empty_ko":
            empty_output = outputs[0]
            object.__setattr__(empty_output, "ko", "")
            return HermesV2Result(cues=(empty_output,) + outputs[1:])
        return HermesV2Result(cues=outputs)


def artifact_texts(result) -> tuple[str, ...]:
    require(result.artifact is not None, "ARTIFACT_EXISTS")
    parsed = parse_subtitle_bytes(result.artifact.payload, "srt")
    return tuple(cue.text for cue in parsed.cues)


def main():
    production_path = Path(__file__).with_name(
        "teddy_discovery_subtitle_v2_pipeline.py"
    )
    production_source = production_path.read_text(encoding="utf-8")

    require(
        "hybrid_asr_indices" not in production_source
        and "hybrid_asr_indices"
        not in str(inspect.signature(run_subtitle_v2_pipeline)),
        "HYBRID_ASR_INDICES_REMOVED_FROM_PUBLIC_API",
    )
    require(
        "def project_affine_timestamp_ms" not in production_source
        and "project_affine_timestamp_ms," in production_source,
        "AFFINE_HELPER_REUSED_FROM_ORCHESTRATOR_CONTRACT",
    )
    half_up_alignment = affine_fixture(1.0, 0.5)
    require(
        project_affine_timestamp_ms(half_up_alignment, 0) == 1
        and project_affine_timestamp_ms(half_up_alignment, 1) == 2,
        "AFFINE_HALF_UP_TIES_AWAY_FROM_ZERO",
    )
    require(
        project_affine_timestamp_ms(hybrid_alignment(), 900) == 1_000
        and project_affine_timestamp_ms(hybrid_alignment(), 1_400) == 1_500,
        "AFFINE_PROJECTION_USES_SCALE_AND_INTERCEPT",
    )
    expect_raises(
        (SubtitleV2PipelineError, SubtitleV2OrchestratorValidationError),
        lambda: project_affine_timestamp_ms(hybrid_alignment(), -1),
        "AFFINE_NEGATIVE_SOURCE_REJECTED",
    )
    expect_raises(
        (SubtitleV2PipelineError, SubtitleV2OrchestratorValidationError),
        lambda: project_affine_timestamp_ms(affine_fixture(1.0, -200.0), 0),
        "AFFINE_NEGATIVE_CONTINUOUS_PROJECTION_REJECTED",
    )
    short_scale_alignment = affine_fixture(0.1, 0.0)
    projected_equal_start_cues = (
        SubtitleCue(
            start_ms=project_affine_timestamp_ms(short_scale_alignment, 0),
            end_ms=project_affine_timestamp_ms(short_scale_alignment, 5),
            text="一",
        ),
        SubtitleCue(
            start_ms=project_affine_timestamp_ms(short_scale_alignment, 1),
            end_ms=project_affine_timestamp_ms(short_scale_alignment, 10),
            text="二",
        ),
    )
    equal_start_artifact = generate_korean_srt(projected_equal_start_cues)
    require(
        equal_start_artifact.state == GENERATED_SRT_READY
        and tuple(
            (cue.start_ms, cue.end_ms)
            for cue in parse_subtitle_bytes(equal_start_artifact.payload, "srt").cues
        )
        == ((0, 1), (0, 1)),
        "AFFINE_EQUAL_START_AND_OVERLAP_ACCEPTED",
    )
    expect_raises(
        ValueError,
        lambda: SubtitleCue(
            start_ms=project_affine_timestamp_ms(short_scale_alignment, 0),
            end_ms=project_affine_timestamp_ms(short_scale_alignment, 1),
            text="零",
        ),
        "AFFINE_ZERO_MATERIALIZED_DURATION_REJECTED",
    )

    contract_types = (
        SubtitleV2RouteDecision,
        GeneratedKoreanSRT,
    )
    require(
        all(is_dataclass(contract_type) for contract_type in contract_types)
        and all(
            getattr(contract_type, "__dataclass_params__").frozen
            for contract_type in contract_types
        ),
        "FROZEN_CONTRACTS_AVAILABLE",
    )
    require(
        all(
            field.name not in {
                "timestamp",
                "start_ms",
                "end_ms",
                "aligned_start_ms",
                "aligned_end_ms",
            }
            for field in fields(GeneratedKoreanSRT)
        ),
        "NO_MODEL_TIMESTAMP_FIELDS",
    )

    existing_boundary = FakeSemanticBoundary()
    existing_result = run_subtitle_v2_pipeline(
        existing_ko_route(),
        semantic_boundary=existing_boundary,
    )
    require(
        existing_result.state == V2_TERMINAL_EXISTING_KO
        and existing_result.artifact is None
        and existing_boundary.calls == 0,
        "EXISTING_KO_TERMINATES_WITHOUT_SEMANTIC_CALL",
    )
    expect_raises(
        SubtitleV2OrchestratorError,
        lambda: SubtitleV2RouteDecision(
            canonical_video=holding(),
            route=V2_ROUTE_EXISTING_KO,
            state=V2_TERMINAL_EXISTING_KO,
            selected_source=SubtitleCandidate.sibling_text(
                "GEN/GEN-123/GEN-123.ko.srt",
                "ko",
            ),
        ),
        "EXISTING_KO_MALFORMED_DOCUMENT_FAILS_CLOSED",
    )
    non_srt_route = lambda: SubtitleV2RouteDecision(
        canonical_video=holding(),
        route=V2_ROUTE_EXISTING_KO,
        state=V2_TERMINAL_EXISTING_KO,
        selected_source=SubtitleCandidate.sibling_text(
            "GEN/GEN-123/GEN-123.ko.srt",
            "ko",
        ),
        source_document=parse_subtitle_bytes(
            b"WEBVTT\n\n00:00:01.000 --> 00:00:01.500\nnot srt\n",
            "vtt",
        ),
    )
    expect_raises(
        SubtitleV2OrchestratorError,
        non_srt_route,
        "EXISTING_KO_UNTRUSTED_DOCUMENT_FAILS_CLOSED",
    )

    local_boundary = FakeSemanticBoundary()
    local_result = run_subtitle_v2_pipeline(
        local_route(),
        semantic_boundary=local_boundary,
    )
    local_request = local_boundary.requests[0]
    require(
        local_boundary.calls == 1
        and local_result.state == V2_READY_TO_PUBLISH
        and tuple(cue.cue_id for cue in local_request.cues)
        == ("ja-000001", "ja-000002")
        and tuple(cue.external_ja for cue in local_request.cues)
        == ("ローカル一", "ローカル二")
        and all(cue.stt_ja is None for cue in local_request.cues)
        and artifact_texts(local_result) == ("한국어-1", "한국어-2"),
        "LOCAL_JA_REQUEST_AND_ARTIFACT_ACCEPTED",
    )
    local_artifact_cues = parse_subtitle_bytes(
        local_result.artifact.payload,
        "srt",
    ).cues
    require(
        tuple((cue.start_ms, cue.end_ms) for cue in local_artifact_cues)
        == ((1_000, 1_500), (2_000, 2_500)),
        "LOCAL_JA_TIMESTAMPS_OWNED_BY_SOURCE",
    )
    require(
        local_request.cues[0].before_context == ()
        and local_request.cues[0].after_context == ("ローカル二",)
        and local_request.cues[1].before_context == ("ローカル一",)
        and local_request.cues[1].after_context == (),
        "LOCAL_CONTEXT_IS_SOURCE_DERIVED",
    )

    hybrid_boundary = FakeSemanticBoundary()
    hybrid_result = run_subtitle_v2_pipeline(
        accepted_hybrid_route(),
        semantic_boundary=hybrid_boundary,
    )
    hybrid_request = hybrid_boundary.requests[0]
    require(
        hybrid_boundary.calls == 1
        and tuple(cue.cue_id for cue in hybrid_request.cues)
        == ("ja-000001", "ja-000002", "ja-000003", "ja-000004")
        and tuple(cue.external_ja for cue in hybrid_request.cues)
        == ("日本語一", "日本語二", "日本語三", "日本語四")
        and tuple(cue.stt_ja for cue in hybrid_request.cues)
        == ("音声一", None, "音声二", "音声三")
        and tuple(cue.en for cue in hybrid_request.cues)
        == ("support one", "support one", "support one", "support one")
        and hybrid_result.state == V2_READY_TO_PUBLISH,
        "HYBRID_REQUEST_USES_RESIDUAL_EVIDENCE",
    )
    hybrid_artifact_cues = parse_subtitle_bytes(
        hybrid_result.artifact.payload,
        "srt",
    ).cues
    require(
        tuple((cue.start_ms, cue.end_ms) for cue in hybrid_artifact_cues)
        == (
            (1_000, 1_500),
            (1_600, 2_500),
            (2_000, 2_500),
            (3_000, 3_500),
        )
        and all(
            type(output.timing_evidence) is SubtitleCue
            for output in hybrid_result.output_cues
        ),
        "HYBRID_TIMING_IS_AFFINE_PROJECTED_EXTERNAL_EVIDENCE",
    )
    require(
        tuple(binding.asr_identity.source_index if binding.asr_identity else None
              for binding in hybrid_result.semantic_result.semantic_plan.semantic_bindings)
        == (0, None, 1, 2),
        "HYBRID_BINDINGS_USE_ONLY_PRESERVED_RESIDUALS",
    )
    require(
        hybrid_request.cues[0].before_context == ("音声一",)
        and hybrid_request.cues[0].after_context == ("support one",),
        "HYBRID_CONTEXT_IS_R2_REFERENCE_DERIVED",
    )
    arbitrary_mapping_boundary = FakeSemanticBoundary()
    expect_raises(
        TypeError,
        lambda: run_subtitle_v2_pipeline(
            accepted_hybrid_route(),
            semantic_boundary=arbitrary_mapping_boundary,
            hybrid_asr_indices=(2, 0, 1, 2),
        ),
        "HYBRID_CALLER_MAPPING_REJECTED",
    )
    require(
        arbitrary_mapping_boundary.calls == 0,
        "HYBRID_CALLER_MAPPING_NO_SEMANTIC_CALL",
    )

    direct_boundary = FakeSemanticBoundary()
    direct_result = run_subtitle_v2_pipeline(
        direct_asr_route(),
        semantic_boundary=direct_boundary,
    )
    rejected_boundary = FakeSemanticBoundary()
    rejected_result = run_subtitle_v2_pipeline(
        rejected_asr_route(),
        semantic_boundary=rejected_boundary,
    )
    for marker, boundary, result in (
        ("DIRECT_ASR_ONLY", direct_boundary, direct_result),
        ("REJECTED_ASR_ONLY", rejected_boundary, rejected_result),
    ):
        request = boundary.requests[0]
        require(
            boundary.calls == 1
            and result.state == V2_READY_TO_PUBLISH
            and tuple(cue.cue_id for cue in request.cues)
            == ("asr-000001", "asr-000002", "asr-000003")
            and tuple(cue.external_ja for cue in request.cues)
            == (None, None, None)
            and tuple(cue.stt_ja for cue in request.cues)
            == ("音声一", "音声二", "音声三")
            and tuple(
                (cue.start_ms, cue.end_ms)
                for cue in parse_subtitle_bytes(
                    result.artifact.payload,
                    "srt",
                ).cues
            )
            == ((1_000, 1_500), (2_000, 2_500), (3_000, 3_500)),
            marker + "_SOURCE_BINDING_AND_TIMING",
        )
    require(
        tuple(cue.cue_id for cue in direct_result.output_cues)
        == tuple(cue.cue_id for cue in rejected_result.output_cues)
        and direct_result.artifact.payload == rejected_result.artifact.payload,
        "DIRECT_AND_REJECTED_ASR_ONLY_HAVE_EQUIVALENT_OWNERSHIP",
    )

    unresolved_boundary = FakeSemanticBoundary()
    unresolved_result = run_subtitle_v2_pipeline(
        unresolved_route(),
        semantic_boundary=unresolved_boundary,
    )
    require(
        unresolved_boundary.calls == 0
        and unresolved_result.state == V2_FAILED_CLOSED
        and unresolved_result.semantic_result is None
        and unresolved_result.artifact is None,
        "UNRESOLVED_FAILS_CLOSED_WITHOUT_SEMANTIC_CALL",
    )

    for mode, marker in (
        ("missing", "FAKE_HERMES_MISSING_CUE_REJECTED"),
        ("extra", "FAKE_HERMES_EXTRA_CUE_REJECTED"),
        ("reordered", "FAKE_HERMES_REORDERED_CUE_REJECTED"),
        ("duplicate", "FAKE_HERMES_DUPLICATE_CUE_REJECTED"),
        ("empty_ko", "FAKE_HERMES_EMPTY_KOREAN_REJECTED"),
    ):
        boundary = FakeSemanticBoundary(mode)
        expect_raises(
            SubtitleV2PipelineError,
            lambda boundary=boundary: run_subtitle_v2_pipeline(
                local_route(),
                semantic_boundary=boundary,
            ),
            marker,
        )
        require(boundary.calls == 1, marker + "_NO_RETRY")

    require(
        all(
            isinstance(result.artifact, GeneratedKoreanSRT)
            and result.artifact.state == GENERATED_SRT_READY
            and result.artifact.cue_count == len(result.semantic_result.hermes_result.cues)
            for result in (local_result, hybrid_result, direct_result, rejected_result)
        ),
        "ARTIFACT_CUE_COUNT_MATCHES_SEMANTIC_RESULT",
    )
    require(
        tuple(result.semantic_result.hermes_result.cues[index].ko for index in range(2))
        == artifact_texts(local_result),
        "ARTIFACT_TEXT_ORDER_MATCHES_HERMES_RESULT",
    )

    try:
        setattr(local_result, "state", V2_FAILED_CLOSED)
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError("EXECUTION_RESULT_MUST_BE_FROZEN")

    imported_modules = {
        alias.name.split(".")[0]
        for node in ast.walk(ast.parse(production_source))
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_modules.update(
        alias.name.split(".")[0]
        for node in ast.walk(ast.parse(production_source))
        if isinstance(node, ast.ImportFrom)
        and node.module is not None
        for alias in node.names
    )
    require(
        not imported_modules.intersection(
            {"sqlite3", "subprocess", "urllib", "requests", "socket"}
        ),
        "NO_EFFECTFUL_MODULE_IMPORTS",
    )
    for forbidden, marker in (
        ("teddy_discovery_hermes_v2_transport", "NO_LIVE_HERMES_TRANSPORT"),
        ("teddy_discovery_subtitle_publish", "NO_PUBLICATION_MODULE"),
        ("run_subtitle_pipeline", "NO_LEGACY_PIPELINE_CALL"),
        ("open(", "NO_FILESYSTEM_OPEN"),
        ("jur-", "NO_TITLE_SPECIFIC_LOGIC"),
    ):
        require(forbidden not in production_source.lower(), marker)

    print("SUBTITLE_V2_PIPELINE_SMOKE_PASS")


if __name__ == "__main__":
    main()
