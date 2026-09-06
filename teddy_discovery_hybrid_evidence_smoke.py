"""Offline smoke tests for the immutable Stage11 v2 evidence contract."""

from dataclasses import FrozenInstanceError, fields, replace
import hashlib
import math
from pathlib import Path

from teddy_discovery_asr import (
    ASRResult,
    ASRSegment,
    ASRSourceSnapshot,
    ASRWord,
)
from teddy_discovery_subtitle import (
    CanonicalVideoHolding,
    SubtitleCandidate,
    validate_canonical_holding,
)
from teddy_discovery_subtitle_external import (
    ExternalSubtitlePayload,
    ExternalSubtitleValidationError,
)
from teddy_discovery_subtitle_text import SubtitleCue, SubtitleDocument
from teddy_discovery_hybrid_evidence import (
    ALIGNMENT_PROVENANCE_ASR_ONLY,
    ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
    EVIDENCE_SOURCE_ASR_SEGMENT,
    EVIDENCE_SOURCE_EXTERNAL_JA,
    NEIGHBOR_SOURCE_ASR_SEGMENT,
    NEIGHBOR_SOURCE_ASR_WORD,
    NEIGHBOR_SOURCE_EXTERNAL_EN,
    HybridAlignmentProvenance,
    HybridCueEvidence,
    HybridCueIdentity,
    HybridEvidenceBundle,
    HybridEvidenceValidationError,
    HybridNeighborReference,
    stable_cue_id,
)


DVD_ID = "ABC-123"
OTHER_DVD_ID = "XYZ-999"

JA_URL = "https://cdn.example.test/subs/1528/TITLE.ja.whisperjav-ja.srt"
EN_URL = "https://cdn.example.test/subs/1528/TITLE.ja.whisperjav-en.srt"
KO_URL = "https://cdn.example.test/subs/1528/TITLE.ja.whisperjav-ko.srt"

JA_BYTES = (
    "1\n"
    "00:00:01,000 --> 00:00:02,500\n"
    "Japanese source\n"
    "\n"
    "2\n"
    "00:00:03,000 --> 00:00:04,500\n"
    "Second source\n"
).encode("utf-8")
EN_BYTES = (
    "1\n"
    "00:00:01,000 --> 00:00:02,500\n"
    "English support\n"
    "\n"
    "2\n"
    "00:00:03,000 --> 00:00:04,500\n"
    "Second support\n"
).encode("utf-8")


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
        source_size=123_456,
        source_mtime_ns=987_654_321,
    )
    return ASRResult(
        source_snapshot=snapshot,
        source_language="ja",
        segments=(
            ASRSegment(
                1_000,
                2_500,
                "first speech",
                (ASRWord(1_100, 1_700, "first"),),
            ),
            ASRSegment(
                3_000,
                4_500,
                "second speech",
                (ASRWord(3_100, 3_700, "second"),),
            ),
        ),
        engine_version="smoke-engine",
    )


def candidate(
    *,
    dvd_id: str = DVD_ID,
    language: str = "ja",
    source_url: str = JA_URL,
) -> SubtitleCandidate:
    return SubtitleCandidate.validated_external_text(
        source_url,
        dvd_id=dvd_id,
        language=language,
        text_format="srt",
    )


def payload(
    *,
    dvd_id: str = DVD_ID,
    language: str = "ja",
    source_url: str = JA_URL,
    payload_bytes: bytes = JA_BYTES,
) -> ExternalSubtitlePayload:
    selected_candidate = candidate(
        dvd_id=dvd_id,
        language=language,
        source_url=source_url,
    )
    return ExternalSubtitlePayload.from_bytes(
        dvd_id=dvd_id,
        candidate=selected_candidate,
        payload=payload_bytes,
    )


def alignment(provenance: str) -> HybridAlignmentProvenance:
    return HybridAlignmentProvenance(
        provenance=provenance,
        method="not_yet_aligned",
        confidence=None,
    )


def valid_bundle(
    *,
    with_en: bool = False,
    dvd_id: str = DVD_ID,
) -> HybridEvidenceBundle:
    ja_payload = payload(dvd_id=dvd_id)
    ja_document = ja_payload.parse()
    asr = asr_result(dvd_id)

    if with_en:
        en_payload = payload(
            dvd_id=dvd_id,
            language="en",
            source_url=EN_URL,
            payload_bytes=EN_BYTES,
        )
        en_document = en_payload.parse()
    else:
        en_payload = None
        en_document = None

    before_context = (
        HybridNeighborReference(NEIGHBOR_SOURCE_ASR_SEGMENT, 0),
        HybridNeighborReference(NEIGHBOR_SOURCE_ASR_WORD, 0, 0),
    )
    after_context = (
        HybridNeighborReference(NEIGHBOR_SOURCE_EXTERNAL_EN, 0),
    ) if with_en else ()

    return HybridEvidenceBundle.from_external_ja_and_asr(
        dvd_id=dvd_id,
        external_ja_payload=ja_payload,
        external_ja_document=ja_document,
        asr_result=asr,
        alignment=alignment(ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID),
        external_en_payload=en_payload,
        external_en_document=en_document,
        before_context=before_context,
        after_context=after_context,
    )


def main():
    ja_payload = payload()
    ja_document = ja_payload.parse()
    asr = asr_result()

    # Valid exact JA + ASR evidence, with bounded references and no copied
    # neighboring dialogue text.
    bundle = valid_bundle()
    require(
        bundle.dvd_id == DVD_ID
        and bundle.external_ja_payload is not None
        and bundle.external_ja_document == ja_document
        and bundle.external_ja_cues == ja_document.cues
        and bundle.asr_result is not None
        and bundle.asr_source_snapshot == asr.source_snapshot
        and bundle.evidence_mode == ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID
        and tuple(cue.cue_id for cue in bundle.cue_evidence)
        == ("ja-000001", "ja-000002")
        and bundle.cue_evidence[0].before_context[0].reference_id
        == "asr-segment-000001",
        "VALID_JA_ASR_BUNDLE",
    )

    # Optional EN is parsed from its exact payload but remains a supporting
    # source; the bundle has no translation-truth field for it.
    with_en = valid_bundle(with_en=True)
    require(
        with_en.external_en_payload is not None
        and with_en.external_en_payload.candidate.language == "en"
        and with_en.external_en_document is not None
        and with_en.external_en_cues == with_en.external_en_document.cues
        and not hasattr(with_en, "translation_source")
        and not with_en.external_en_payload.is_translation_source,
        "VALID_JA_ASR_OPTIONAL_EN_SUPPORT",
    )

    # Exact DVD identity is checked independently for JA, ASR, and EN.
    other_ja = payload(dvd_id=OTHER_DVD_ID)
    expect_raises(
        HybridEvidenceValidationError,
        lambda: HybridEvidenceBundle(
            dvd_id=DVD_ID,
            asr_result=asr,
            cue_evidence=bundle.cue_evidence,
            alignment=alignment(ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID),
            external_ja_payload=other_ja,
            external_ja_document=other_ja.parse(),
        ),
        "JA_DVD_ID_MISMATCH_REJECTED",
    )

    other_asr = asr_result(OTHER_DVD_ID)
    asr_only_cues = tuple(
        HybridCueEvidence(HybridCueIdentity.for_asr_segment(index))
        for index in range(len(other_asr.segments))
    )
    expect_raises(
        HybridEvidenceValidationError,
        lambda: HybridEvidenceBundle(
            dvd_id=DVD_ID,
            asr_result=other_asr,
            cue_evidence=asr_only_cues,
            alignment=alignment(ALIGNMENT_PROVENANCE_ASR_ONLY),
        ),
        "ASR_DVD_ID_MISMATCH_REJECTED",
    )

    other_en = payload(
        dvd_id=OTHER_DVD_ID,
        language="en",
        source_url=EN_URL,
        payload_bytes=EN_BYTES,
    )
    expect_raises(
        HybridEvidenceValidationError,
        lambda: HybridEvidenceBundle(
            dvd_id=DVD_ID,
            asr_result=asr,
            cue_evidence=bundle.cue_evidence,
            alignment=alignment(ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID),
            external_ja_payload=ja_payload,
            external_ja_document=ja_document,
            external_en_payload=other_en,
            external_en_document=other_en.parse(),
        ),
        "EN_DVD_ID_MISMATCH_REJECTED",
    )

    # ExternalSubtitlePayload itself rejects KO, and this contract only accepts
    # the two language roles explicitly allowed by Stage11 v2.
    expect_raises(
        ExternalSubtitleValidationError,
        lambda: payload(
            language="ko",
            source_url=KO_URL,
            payload_bytes=JA_BYTES,
        ),
        "KO_REJECTED",
    )

    # The metadata may look right while cues are detached; exact reparsing is
    # required, so both changed cues and changed metadata fail closed.
    detached_document = SubtitleDocument(
        format=ja_document.format,
        cues=(SubtitleCue(1_000, 2_500, "detached cue"),),
        source_sha256=ja_document.source_sha256,
        byte_size=ja_document.byte_size,
    )
    expect_raises(
        HybridEvidenceValidationError,
        lambda: HybridEvidenceBundle(
            dvd_id=DVD_ID,
            asr_result=asr,
            cue_evidence=bundle.cue_evidence,
            alignment=alignment(ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID),
            external_ja_payload=ja_payload,
            external_ja_document=detached_document,
        ),
        "DETACHED_DOCUMENT_REJECTED",
    )
    mismatched_metadata = replace(
        ja_document,
        source_sha256="0" * 64,
    )
    expect_raises(
        HybridEvidenceValidationError,
        lambda: HybridEvidenceBundle(
            dvd_id=DVD_ID,
            asr_result=asr,
            cue_evidence=bundle.cue_evidence,
            alignment=alignment(ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID),
            external_ja_payload=ja_payload,
            external_ja_document=mismatched_metadata,
        ),
        "DOCUMENT_METADATA_MISMATCH_REJECTED",
    )

    # The payload hash is the stable digest of the exact immutable bytes.
    expected_sha = hashlib.sha256(JA_BYTES).hexdigest()
    require(
        ja_payload.sha256 == expected_sha
        and ja_document.source_sha256 == expected_sha
        and ja_payload.byte_size == len(JA_BYTES)
        and ja_document.byte_size == len(JA_BYTES),
        "PAYLOAD_DOCUMENT_SHA_AND_SIZE_STABLE",
    )

    # Mutable lists cannot cross the contract boundary.
    expect_raises(
        HybridEvidenceValidationError,
        lambda: replace(bundle, cue_evidence=list(bundle.cue_evidence)),
        "IMMUTABLE_CUE_TUPLE_REQUIRED",
    )
    expect_raises(
        HybridEvidenceValidationError,
        lambda: replace(
            bundle.cue_evidence[0],
            before_context=list(bundle.cue_evidence[0].before_context),
        ),
        "IMMUTABLE_CONTEXT_TUPLE_REQUIRED",
    )
    expect_raises(
        FrozenInstanceError,
        lambda: setattr(bundle, "dvd_id", OTHER_DVD_ID),
        "FROZEN_BUNDLE",
    )

    # Duplicate and out-of-order identities are rejected even though the
    # underlying source objects remain valid.
    duplicate_cues = (bundle.cue_evidence[0], bundle.cue_evidence[0])
    expect_raises(
        HybridEvidenceValidationError,
        lambda: replace(bundle, cue_evidence=duplicate_cues),
        "DUPLICATE_CUE_ID_REJECTED",
    )
    out_of_order = (bundle.cue_evidence[1], bundle.cue_evidence[0])
    expect_raises(
        HybridEvidenceValidationError,
        lambda: replace(bundle, cue_evidence=out_of_order),
        "OUT_OF_ORDER_CUE_ID_REJECTED",
    )
    require(
        stable_cue_id(EVIDENCE_SOURCE_EXTERNAL_JA, 0) == "ja-000001"
        and stable_cue_id(EVIDENCE_SOURCE_ASR_SEGMENT, 0) == "asr-000001",
        "TITLE_INDEPENDENT_STABLE_CUE_IDS",
    )

    # Neighbor references are bounded IDs into existing source objects; they
    # cannot point beyond those objects or be nondeterministically ordered.
    invalid_reference = HybridNeighborReference(NEIGHBOR_SOURCE_ASR_SEGMENT, 99)
    invalid_context_cue = HybridCueEvidence(
        HybridCueIdentity.for_external_ja(0),
        before_context=(invalid_reference,),
    )
    expect_raises(
        HybridEvidenceValidationError,
        lambda: replace(bundle, cue_evidence=(invalid_context_cue, bundle.cue_evidence[1])),
        "INVALID_NEIGHBOR_REFERENCE_REJECTED",
    )
    expect_raises(
        HybridEvidenceValidationError,
        lambda: HybridCueEvidence(
            HybridCueIdentity.for_external_ja(0),
            before_context=(
                HybridNeighborReference(NEIGHBOR_SOURCE_ASR_WORD, 0, 0),
                HybridNeighborReference(NEIGHBOR_SOURCE_ASR_SEGMENT, 0),
            ),
        ),
        "NONDETERMINISTIC_NEIGHBOR_ORDER_REJECTED",
    )

    expect_raises(
        HybridEvidenceValidationError,
        lambda: HybridNeighborReference("unknown_source", 0),
        "UNKNOWN_NEIGHBOR_SOURCE_REJECTED",
    )

    # Confidence is optional storage only, but a supplied value is exact,
    # finite, and bounded; provenance is an explicit closed set.
    expect_raises(
        HybridEvidenceValidationError,
        lambda: HybridAlignmentProvenance(
            ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
            "not_yet_aligned",
            math.nan,
        ),
        "NAN_CONFIDENCE_REJECTED",
    )
    expect_raises(
        HybridEvidenceValidationError,
        lambda: HybridAlignmentProvenance(
            ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
            "not_yet_aligned",
            1,
        ),
        "INTEGER_CONFIDENCE_REJECTED",
    )
    expect_raises(
        HybridEvidenceValidationError,
        lambda: HybridAlignmentProvenance("made_up", "not_yet_aligned"),
        "UNKNOWN_PROVENANCE_REJECTED",
    )
    require(
        HybridAlignmentProvenance(
            ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
            "later_deterministic_alignment",
            0.75,
        ).confidence
        == 0.75,
        "FINITE_BOUNDED_CONFIDENCE_ACCEPTED",
    )

    # The frozen roadmap keeps an explicit ASR-only representation available
    # when external JA is unusable.
    asr_only = HybridEvidenceBundle.from_asr_only(
        dvd_id=DVD_ID,
        asr_result=asr,
        alignment=alignment(ALIGNMENT_PROVENANCE_ASR_ONLY),
    )
    require(
        asr_only.external_ja_payload is None
        and asr_only.external_ja_document is None
        and asr_only.evidence_mode == ALIGNMENT_PROVENANCE_ASR_ONLY
        and tuple(cue.cue_id for cue in asr_only.cue_evidence)
        == ("asr-000001", "asr-000002"),
        "ASR_ONLY_REPRESENTATION",
    )

    # Source timestamps remain inside deterministic source contracts.  No
    # hybrid contract object has an LLM timestamp owner or arbitrary cue text.
    for contract_type in (
        HybridCueIdentity,
        HybridNeighborReference,
        HybridCueEvidence,
        HybridAlignmentProvenance,
        HybridEvidenceBundle,
    ):
        require(
            getattr(contract_type.__dataclass_params__, "frozen", False),
            contract_type.__name__ + "_FROZEN",
        )
        field_names = {field.name for field in fields(contract_type)}
        require(
            not field_names.intersection(
                {
                    "llm_start_ms",
                    "llm_end_ms",
                    "translated_start_ms",
                    "translated_end_ms",
                }
            ),
            contract_type.__name__ + "_HAS_NO_LLM_TIMESTAMP_OWNER",
        )

    hybrid_source = Path(__file__).with_name("teddy_discovery_hybrid_evidence.py")
    require(
        "JUR-750" not in hybrid_source.read_text(encoding="utf-8"),
        "NO_TITLE_SPECIFIC_PRODUCTION_STRING",
    )

    print("HYBRID_EVIDENCE_SMOKE_PASS")


if __name__ == "__main__":
    main()
