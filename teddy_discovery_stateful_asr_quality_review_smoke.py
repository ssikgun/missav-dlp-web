"""Offline smoke for the generic ASR-only review and CLEAN bridges."""

from dataclasses import asdict, replace
import json
import uuid

from teddy_discovery_asr import ASRSegment
from teddy_discovery_hermes_v2 import HermesV2CueInput, HermesV2CueOutput
from teddy_discovery_stateful_asr import (
    build_stateful_asr_package,
    prepare_stateful_asr_package,
)
from teddy_discovery_stateful_asr_quality_review import (
    AMBIGUOUS,
    KEEP,
    OMIT,
    REPAIR,
    ASRQualityReviewRequest,
    asr_quality_review_request_sha256,
    build_asr_prefilter_provenance,
    build_asr_quality_review_request,
    parse_asr_quality_review_request,
    parse_asr_quality_review_request_structure,
    parse_asr_quality_review_result,
    serialize_asr_quality_review_request,
    serialize_asr_quality_review_result,
)
from teddy_discovery_stateful_asr_quality_review_clean import (
    materialize_stateful_asr_quality_review_clean,
)
from teddy_discovery_stateful_quality_review import (
    QualityReviewResult,
    QualityReviewResultCue,
    STATEFUL_QUALITY_REVIEW_SCHEMA_VERSION,
    bind_review_execution_provenance,
    effective_review_action,
)
from teddy_discovery_stateful_quality_review_runner import (
    ASR_ONLY_QUALITY_REVIEW_QUERY,
    QUALITY_REVIEW_QUERY,
    build_asr_quality_review_command,
    build_quality_review_command,
)
from teddy_discovery_stateful_translator import (
    StatefulSubtitleResult,
    stateful_session_id_for_package,
)
from teddy_discovery_subtitle_v2_pipeline_smoke import asr_result


def main():
    base_asr = asr_result()
    asr = replace(
        base_asr,
        segments=tuple(
            ASRSegment(index * 1000, index * 1000 + 700, text)
            for index, text in enumerate(
                ("普通の文です", "ああああ", "次の文です", "三番目", "最後です"),
                start=1,
            )
        ),
    )
    source_package = build_stateful_asr_package(
        tuple(
            HermesV2CueInput(
                cue_id=f"asr-{index:06d}",
                external_ja=None,
                stt_ja=segment.text,
                en=None,
                before_context=(),
                after_context=(),
            )
            for index, segment in enumerate(asr.segments, start=1)
        ),
        dvd_id=asr.source_snapshot.dvd_id,
        generation_key="review-source",
        claim_token=3,
    )
    prepared = prepare_stateful_asr_package(
        source_package,
        generation_key="review-filtered",
        asr_result=asr,
    )
    package = prepared.package
    result = StatefulSubtitleResult(
        schema_version=package.schema_version,
        dvd_id=package.dvd_id,
        generation_key=package.generation_key,
        claim_token=package.claim_token,
        session_id=stateful_session_id_for_package(package),
        cues=tuple(
            HermesV2CueOutput(
                cue.cue_id,
                "修正版" if cue.cue_id == "asr-000001" else None,
                "첫 번역 " + cue.cue_id,
            )
            for cue in package.cues
        ),
    )
    provenance = build_asr_prefilter_provenance(
        asr,
        prepared,
        asr_artifact_sha256="a" * 64,
    )
    request = build_asr_quality_review_request(
        asr_result=asr,
        package=package,
        result=result,
        prefilter_provenance=provenance,
    )

    assert isinstance(request, ASRQualityReviewRequest)
    assert len(request.cues) == 4
    assert tuple(cue.source_index for cue in request.cues) == (0, 2, 3, 4)
    assert request.prefilter_provenance.omissions[0].cue_id == "asr-000002"
    assert request.prefilter_provenance.omissions[0].reason == "repeated_pure_vocalic_run"
    assert request.prefilter_provenance.omissions[0].features == (
        "repeated_pure_vocalic_run",
        "intra_cue_structural_repetition",
    )
    assert all(cue.cue_id != "asr-000002" for cue in request.cues)
    assert all(cue.source_quality is not None for cue in request.cues)
    assert request.cues[0].source_quality.action == "KEEP"
    assert request.cues[1].source_quality.action == "KEEP"
    assert request.cues[1].source_index == 2
    assert request.cues[1].before_context[0].cue_id == "asr-000001"
    assert request.cues[1].after_context[0].cue_id == "asr-000004"
    assert request.cues[0].first_pass_repaired_ja == "修正版"
    assert all("external_ja" not in asdict(cue) for cue in request.cues)
    request_payload = serialize_asr_quality_review_request(request)
    assert parse_asr_quality_review_request(
        request_payload, asr_result=asr, package=package, result=result
    ) == request
    legacy_request_object = json.loads(request_payload)
    legacy_request_object['session_id'] = legacy_request_object.pop(
        'source_translation_session_id'
    )
    legacy_request_payload = json.dumps(
        legacy_request_object, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')
    ).encode()
    legacy_request = parse_asr_quality_review_request_structure(legacy_request_payload)
    assert legacy_request == request
    assert serialize_asr_quality_review_request(legacy_request) == legacy_request_payload
    try:
        replace(request, cues=(request.cues[0],) + request.cues[:-1])
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate ASR review cue was accepted")
    assert b"external_ja" not in request_payload
    assert b"source_quality" in request_payload

    categories = {
        KEEP: "DIALOGUE",
        REPAIR: "SEMANTIC_REPAIR",
        OMIT: "SOURCE_NOISE",
        AMBIGUOUS: "AMBIGUOUS",
    }
    actions = (KEEP, REPAIR, OMIT, AMBIGUOUS)
    review_result = QualityReviewResult(
        STATEFUL_QUALITY_REVIEW_SCHEMA_VERSION,
        asr_quality_review_request_sha256(request),
        tuple(
            QualityReviewResultCue(
                cue.cue_id,
                action,
                categories[action],
                "synthetic evidence for smoke",
                "修正" if action == REPAIR else None,
                "검수 수정" if action == REPAIR else None,
            )
            for cue, action in zip(request.cues, actions, strict=True)
        ),
    )
    result_payload = serialize_asr_quality_review_result(review_result, request)
    assert parse_asr_quality_review_result(result_payload, request) == review_result
    execution_session_id = str(uuid.uuid4())
    bound_result = bind_review_execution_provenance(
        review_result, request, execution_session_id
    )
    bound_result_payload = serialize_asr_quality_review_result(bound_result, request)
    assert parse_asr_quality_review_result(bound_result_payload, request) == bound_result
    assert bound_result.source_translation_session_id == request.source_translation_session_id
    assert bound_result.review_execution_session_id == execution_session_id
    missing = asdict(review_result)
    missing["cues"] = missing["cues"][:-1]
    try:
        parse_asr_quality_review_result(
            json.dumps(missing, ensure_ascii=False).encode(), request
        )
    except ValueError:
        pass
    else:
        raise AssertionError("missing review result was accepted")

    clean = materialize_stateful_asr_quality_review_clean(
        package, result, asr, request, review_result
    )
    assert clean.source_indexes == (0, 2, 4)
    assert clean.artifact.cue_count == 3
    assert clean.cues[0].ja == "修正版"
    assert clean.cues[1].ja == "修正"
    assert clean.cues[1].ko == "검수 수정"
    assert clean.cues[2].review_action == AMBIGUOUS
    assert "00:00:01,000 --> 00:00:01,700" in clean.artifact.payload.decode()
    assert materialize_stateful_asr_quality_review_clean(
        package, result, asr, request, review_result
    ) == clean

    identity_result = replace(
        review_result,
        cues=(
            replace(
                review_result.cues[0],
                action=REPAIR,
                category="SEMANTIC_REPAIR",
                replacement_ja=result.cues[0].repaired_ja,
                replacement_ko=result.cues[0].ko,
            ),
        ) + review_result.cues[1:],
    )
    identity_clean = materialize_stateful_asr_quality_review_clean(
        package, result, asr, request, identity_result
    )
    assert effective_review_action(request.cues[0], identity_result.cues[0]) == KEEP
    assert identity_clean.cues[0].ja == result.cues[0].repaired_ja
    assert identity_clean.cues[0].ko == result.cues[0].ko
    assert identity_clean.artifact == clean.artifact

    assert "external_ja" not in ASR_ONLY_QUALITY_REVIEW_QUERY
    assert "compare both sources" not in ASR_ONLY_QUALITY_REVIEW_QUERY
    assert "stt_ja" in ASR_ONLY_QUALITY_REVIEW_QUERY
    assert "before_context" in ASR_ONLY_QUALITY_REVIEW_QUERY
    assert "prefilter_provenance" in ASR_ONLY_QUALITY_REVIEW_QUERY
    assert build_quality_review_command(result.session_id)[-1] == QUALITY_REVIEW_QUERY
    assert build_asr_quality_review_command(result.session_id)[-1] == ASR_ONLY_QUALITY_REVIEW_QUERY

    print("STATEFUL_ASR_QUALITY_REVIEW_SMOKE_PASS")
    print("ASR_REVIEW_REQUEST_CUES=4")
    print("ASR_REVIEW_PREFILTER_OMISSIONS=1")
    print("ASR_CLEAN_CUES=3")


if __name__ == "__main__":
    main()
