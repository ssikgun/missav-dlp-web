"""Offline smoke tests for deterministic alignment-decision application."""

from dataclasses import FrozenInstanceError, fields
from pathlib import Path

from teddy_discovery_alignment import (
    AnchorTimingEvidence,
    JapaneseComparisonEvidence,
    MonotonicAnchorCandidate,
)
from teddy_discovery_alignment_acceptance import (
    ACCEPT_HYBRID,
    ALIGNMENT_POLICY_SATISFIED,
    AlignmentAcceptanceDecision,
    AlignmentAcceptancePolicy,
    INSUFFICIENT_ANCHOR_COUNT,
    REJECT_EXTERNAL,
    UNRESOLVED,
)
from teddy_discovery_alignment_application import (
    AlignmentAcceptanceApplicationResult,
    AlignmentAcceptanceApplicationValidationError,
    apply_alignment_acceptance,
)
from teddy_discovery_asr import (
    ASRResult,
    ASRSegment,
    ASRSourceSnapshot,
)
from teddy_discovery_hybrid_evidence import (
    ALIGNMENT_PROVENANCE_ASR_ONLY,
    ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
    ALIGNMENT_PROVENANCE_UNRESOLVED,
    HybridAlignmentProvenance,
    HybridCueIdentity,
    HybridEvidenceBundle,
)
from teddy_discovery_subtitle import (
    CanonicalVideoHolding,
    SubtitleCandidate,
    validate_canonical_holding,
)
from teddy_discovery_subtitle_external import ExternalSubtitlePayload


DVD_ID = "GEN-123"
JA_URL = "https://source.example.test/subs/17/generic.ja.srt"
EN_URL = "https://source.example.test/subs/18/generic.en.srt"


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
            ASRSegment(1_000, 2_000, "同じ"),
            ASRSegment(3_000, 4_000, "同じ"),
            ASRSegment(5_000, 6_000, "同じ"),
        ),
        engine_version="application-smoke-engine",
    )


def subtitle_bytes(texts: tuple[str, ...]) -> bytes:
    blocks = []
    for index, text in enumerate(texts, start=1):
        start_ms = index * 1_000
        end_ms = start_ms + 500
        blocks.append(
            f"{index}\n"
            f"00:00:{start_ms // 1_000:02d},{start_ms % 1_000:03d} "
            f"--> 00:00:{end_ms // 1_000:02d},{end_ms % 1_000:03d}\n"
            f"{text}"
        )
    return ("\n\n".join(blocks) + "\n").encode("utf-8")


def external_payload(
    url: str,
    language: str,
    texts: tuple[str, ...],
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
        payload=subtitle_bytes(texts),
    )


def hybrid_bundle() -> HybridEvidenceBundle:
    ja_payload = external_payload(JA_URL, "ja", ("日本語", "字幕"))
    en_payload = external_payload(EN_URL, "en", ("support", "evidence"))
    return HybridEvidenceBundle.from_external_ja_and_asr(
        dvd_id=DVD_ID,
        external_ja_payload=ja_payload,
        external_ja_document=ja_payload.parse(),
        asr_result=asr_result(),
        alignment=HybridAlignmentProvenance(
            ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
            "generic_application_fixture",
            0.42,
        ),
        external_en_payload=en_payload,
        external_en_document=en_payload.parse(),
    )


def decision(
    verdict: str,
    recommended_provenance: str,
    reason_codes: tuple[str, ...],
    *,
    anchor_count: int = 3,
    inlier_count: int = 3,
    inlier_ratio: float = 1.0,
) -> AlignmentAcceptanceDecision:
    return AlignmentAcceptanceDecision(
        verdict=verdict,
        recommended_provenance=recommended_provenance,
        reason_codes=reason_codes,
        anchor_count=anchor_count,
        inlier_count=inlier_count,
        inlier_ratio=inlier_ratio,
        median_absolute_residual_ms=0.0,
        external_evidence_span_ms=2_000.0,
        asr_evidence_span_ms=2_000.0,
        scale=1.0,
    )


def tampered_bundle(bundle: HybridEvidenceBundle, **overrides):
    values = {
        "dvd_id": bundle.dvd_id,
        "asr_result": bundle.asr_result,
        "cue_evidence": bundle.cue_evidence,
        "alignment": bundle.alignment,
        "external_ja_payload": bundle.external_ja_payload,
        "external_ja_document": bundle.external_ja_document,
        "external_en_payload": bundle.external_en_payload,
        "external_en_document": bundle.external_en_document,
    }
    values.update(overrides)
    value = object.__new__(HybridEvidenceBundle)
    for field_name, field_value in values.items():
        object.__setattr__(value, field_name, field_value)
    return value


def main():
    source_bundle = hybrid_bundle()
    accept_decision = decision(
        ACCEPT_HYBRID,
        ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
        (ALIGNMENT_POLICY_SATISFIED,),
    )
    reject_decision = decision(
        REJECT_EXTERNAL,
        ALIGNMENT_PROVENANCE_ASR_ONLY,
        ("LOW_INLIER_RATIO",),
        inlier_count=1,
        inlier_ratio=1 / 3,
    )
    unresolved_decision = decision(
        UNRESOLVED,
        ALIGNMENT_PROVENANCE_UNRESOLVED,
        (INSUFFICIENT_ANCHOR_COUNT,),
    )

    accepted = apply_alignment_acceptance(source_bundle, accept_decision)
    require(
        accepted.bundle.external_ja_payload is source_bundle.external_ja_payload
        and accepted.bundle.external_ja_document is source_bundle.external_ja_document
        and accepted.bundle.asr_result is source_bundle.asr_result
        and accepted.bundle.external_en_payload is source_bundle.external_en_payload
        and accepted.bundle.external_en_document is source_bundle.external_en_document
        and accepted.bundle.cue_evidence is source_bundle.cue_evidence
        and accepted.bundle.alignment.provenance
        == ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
        "ACCEPT_PRESERVES_ALL_SOURCE_EVIDENCE",
    )

    rejected = apply_alignment_acceptance(source_bundle, reject_decision)
    require(
        rejected.bundle is not source_bundle
        and rejected.bundle.external_ja_payload is None
        and rejected.bundle.external_ja_document is None
        and rejected.bundle.asr_result is source_bundle.asr_result
        and rejected.bundle.external_en_payload is source_bundle.external_en_payload
        and rejected.bundle.external_en_document is source_bundle.external_en_document
        and rejected.bundle.alignment.provenance == ALIGNMENT_PROVENANCE_ASR_ONLY
        and tuple(cue.source for cue in rejected.bundle.cue_evidence)
        == ("asr_segment", "asr_segment", "asr_segment")
        and tuple(cue.source_index for cue in rejected.bundle.cue_evidence)
        == (0, 1, 2),
        "REJECT_BUILDS_FRESH_ASR_ONLY_BUNDLE",
    )
    require(
        source_bundle.external_ja_payload is not None
        and source_bundle.external_ja_document is not None
        and source_bundle.alignment.provenance
        == ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
        "REJECT_DOES_NOT_MUTATE_ORIGINAL_BUNDLE",
    )

    unresolved = apply_alignment_acceptance(source_bundle, unresolved_decision)
    require(
        unresolved.bundle.external_ja_payload is source_bundle.external_ja_payload
        and unresolved.bundle.external_ja_document is source_bundle.external_ja_document
        and unresolved.bundle.asr_result is source_bundle.asr_result
        and unresolved.bundle.cue_evidence is source_bundle.cue_evidence
        and unresolved.bundle.alignment.provenance
        == ALIGNMENT_PROVENANCE_UNRESOLVED
        and all(
            cue.source == "external_ja"
            for cue in unresolved.bundle.cue_evidence
        ),
        "UNRESOLVED_RETAINS_EXTERNAL_AND_ASR_EVIDENCE",
    )
    require(
        unresolved.bundle.external_ja_payload is not None
        and unresolved.bundle.alignment.provenance != ALIGNMENT_PROVENANCE_ASR_ONLY,
        "UNRESOLVED_NEVER_BECOMES_ASR_ONLY",
    )

    for applied_decision in (
        accepted,
        rejected,
        unresolved,
    ):
        require(
            applied_decision.bundle.alignment.method
            == source_bundle.alignment.method
            and applied_decision.bundle.alignment.confidence
            == source_bundle.alignment.confidence,
            "METHOD_AND_CONFIDENCE_PRESERVED_" + applied_decision.decision.verdict,
        )

    require(
        accepted == apply_alignment_acceptance(source_bundle, accept_decision)
        and rejected == apply_alignment_acceptance(source_bundle, reject_decision)
        and unresolved
        == apply_alignment_acceptance(source_bundle, unresolved_decision),
        "APPLICATION_REPEATABILITY",
    )

    asr_only_bundle = HybridEvidenceBundle.from_asr_only(
        dvd_id=DVD_ID,
        asr_result=asr_result(),
        alignment=HybridAlignmentProvenance(
            ALIGNMENT_PROVENANCE_ASR_ONLY,
            "asr_fixture",
            0.42,
        ),
        external_en_payload=source_bundle.external_en_payload,
        external_en_document=source_bundle.external_en_document,
    )
    expect_raises(
        AlignmentAcceptanceApplicationValidationError,
        lambda: apply_alignment_acceptance(asr_only_bundle, accept_decision),
        "ACCEPT_WITHOUT_EXTERNAL_JA_REJECTED",
    )

    malformed_en = tampered_bundle(
        source_bundle,
        external_en_document=object(),
    )
    expect_raises(
        AlignmentAcceptanceApplicationValidationError,
        lambda: apply_alignment_acceptance(malformed_en, accept_decision),
        "MALFORMED_OPTIONAL_EN_REJECTED",
    )
    detached_dvd = tampered_bundle(
        source_bundle,
        dvd_id="GEN-999",
    )
    expect_raises(
        AlignmentAcceptanceApplicationValidationError,
        lambda: apply_alignment_acceptance(detached_dvd, accept_decision),
        "DETACHED_DVD_ID_REJECTED",
    )

    detached_decision = decision(
        ACCEPT_HYBRID,
        ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
        (ALIGNMENT_POLICY_SATISFIED,),
    )
    object.__setattr__(detached_decision, "recommended_provenance", ALIGNMENT_PROVENANCE_ASR_ONLY)
    expect_raises(
        AlignmentAcceptanceApplicationValidationError,
        lambda: apply_alignment_acceptance(source_bundle, detached_decision),
        "DETACHED_DECISION_REJECTED",
    )
    expect_raises(
        AlignmentAcceptanceApplicationValidationError,
        lambda: AlignmentAcceptanceApplicationResult(
            accept_decision,
            unresolved.bundle,
        ),
        "DETACHED_RESULT_PROVENANCE_REJECTED",
    )
    expect_raises(
        AlignmentAcceptanceApplicationValidationError,
        lambda: apply_alignment_acceptance(object(), accept_decision),
        "WRONG_BUNDLE_TYPE_REJECTED",
    )
    expect_raises(
        AlignmentAcceptanceApplicationValidationError,
        lambda: apply_alignment_acceptance(source_bundle, object()),
        "WRONG_DECISION_TYPE_REJECTED",
    )

    require(
        getattr(
            AlignmentAcceptanceApplicationResult.__dataclass_params__,
            "frozen",
            False,
        )
        and isinstance(accepted.bundle, HybridEvidenceBundle)
        and isinstance(accepted.decision, AlignmentAcceptanceDecision),
        "APPLICATION_RESULT_FROZEN",
    )
    expect_raises(
        FrozenInstanceError,
        lambda: setattr(accepted, "bundle", source_bundle),
        "APPLICATION_RESULT_IMMUTABLE",
    )
    for field in fields(AlignmentAcceptanceApplicationResult):
        require(
            field.name in {"decision", "bundle"},
            "APPLICATION_RESULT_FIELD_BOUNDARY",
        )

    application_source = Path(__file__).with_name(
        "teddy_discovery_alignment_application.py"
    )
    source_text = application_source.read_text(encoding="utf-8").lower()
    for forbidden, marker in (
        ("jur", "NO_TITLE_SPECIFIC_BEHAVIOR"),
        ("project_timestamp", "NO_TIMESTAMP_PROJECTION"),
        ("transform_timestamp", "NO_TIMESTAMP_TRANSFORMATION"),
        ("aligned_start_ms", "NO_ALIGNED_START_OWNERSHIP"),
        ("aligned_end_ms", "NO_ALIGNED_END_OWNERSHIP"),
        ("rewrite_cue_timing", "NO_CUE_TIMING_REWRITE"),
        ("open(", "NO_FILESYSTEM_IO"),
        ("urllib", "NO_NETWORK_IO"),
        ("subprocess", "NO_SUBPROCESS_IO"),
        ("sqlite", "NO_DATABASE_IO"),
        ("hermes", "NO_MODEL_ROUTING"),
        ("asrresult", "NO_ASR_EXECUTION"),
    ):
        require(forbidden not in source_text, marker)

    print("ALIGNMENT_ACCEPTANCE_APPLICATION_SMOKE_PASS")


if __name__ == "__main__":
    main()
