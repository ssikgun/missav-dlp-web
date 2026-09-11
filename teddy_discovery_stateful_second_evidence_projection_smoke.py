"""Offline smoke for the generic second-pass evidence projection.

This smoke reads the durable cross-title artifacts but never calls a model,
opens media, contacts VM122/Hermes, or writes an artifact.  The synthetic
builder checks exercise both stateful review routes and their trust boundary.
"""

from __future__ import annotations

from dataclasses import fields, replace
import hashlib
import json
from pathlib import Path

from teddy_discovery_asr import ASRResult, ASRSegment
from teddy_discovery_asr_artifact import (
    parse_asr_result_bytes,
    serialize_asr_result,
)
from teddy_discovery_asr_source_quality import (
    ASR_SOURCE_REQUIRE_SECOND_EVIDENCE,
    classify_asr_result_source_quality,
)
from teddy_discovery_hermes_v2 import (
    HermesV2CueInput,
    HermesV2CueOutput,
    HermesV2Request,
    serialize_hermes_v2_request,
)
from teddy_discovery_stateful_asr import (
    build_stateful_asr_package,
    prepare_stateful_asr_package,
)
from teddy_discovery_stateful_asr_quality_review import (
    build_asr_prefilter_provenance,
    build_asr_quality_review_request,
    parse_asr_quality_review_request,
    serialize_asr_quality_review_request,
)
from teddy_discovery_stateful_hybrid import prepare_stateful_hybrid
from teddy_discovery_stateful_hybrid_smoke import semantic_result
from teddy_discovery_stateful_quality_review import (
    build_review_request,
    parse_review_request,
    serialize_review_request,
)
from teddy_discovery_stateful_translator import (
    StatefulSubtitleResult,
    stateful_session_id_for_package,
)
from teddy_discovery_subtitle_v2_pipeline_smoke import accepted_hybrid_route, asr_result
from teddy_discovery_targeted_asr_window import (
    STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1,
)
from teddy_discovery_targeted_second_evidence import (
    TargetedSecondEvidenceWindowResult,
    bind_targeted_second_evidence,
    build_targeted_second_evidence_plan_with_policy,
)
from teddy_discovery_targeted_second_evidence_artifact import (
    TargetedSecondEvidenceArtifact,
    parse_targeted_second_evidence_artifact_bytes,
    targeted_second_evidence_artifact_from_execution,
)
from teddy_discovery_targeted_second_evidence_projection import (
    TARGETED_SECOND_EVIDENCE_REVIEW_FIELDS,
    TargetedSecondEvidenceProjectionError,
    parse_targeted_second_evidence_review_projection,
    project_targeted_second_evidence_artifact,
)
from teddy_discovery_targeted_second_evidence_runner import (
    TargetedSecondEvidenceExecution,
)
from teddy_discovery_subtitle_source_quality import classify_source_document


FIXTURE_ROOT = Path("/var/tmp")
FIXTURES = {
    "ADN-785": (
        FIXTURE_ROOT / "ADN-785.large-v3.stage11-asr-v1.json",
        FIXTURE_ROOT / "ADN-785.r6d-targeted-second-evidence-v1.json",
    ),
    "HSODA-104": (
        FIXTURE_ROOT / "HSODA-104.large-v3.stage11-asr-v1.json",
        FIXTURE_ROOT / "HSODA-104.r6d-targeted-second-evidence-v1.json",
    ),
    "DVDMS-117": (
        FIXTURE_ROOT / "DVDMS-117.large-v3.stage11-asr-v1.json",
        FIXTURE_ROOT / "DVDMS-117.r6d-targeted-second-evidence-v1.json",
    ),
}


def check(condition: bool, marker: str):
    if not condition:
        raise AssertionError(marker)
    print("PASS=" + marker)


def expect(error_type, callback, marker: str):
    try:
        callback()
    except error_type:
        print("PASS=" + marker)
        return
    except Exception as error:
        raise AssertionError(
            marker + ": wrong exception " + type(error).__name__
        ) from error
    raise AssertionError(marker + ": accepted invalid input")


def _baseline_sha256(asr: ASRResult) -> str:
    return hashlib.sha256(serialize_asr_result(asr)).hexdigest()


def _artifact_for(
    asr: ASRResult,
    targeted_texts: tuple[str, ...],
) -> TargetedSecondEvidenceArtifact:
    decisions = classify_asr_result_source_quality(asr)
    plan = build_targeted_second_evidence_plan_with_policy(
        asr,
        decisions,
        policy=STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1,
    )
    if len(targeted_texts) != len(plan.sources):
        raise AssertionError("synthetic target text coverage differs")
    target_segments = tuple(
        ASRSegment(
            source.start_ms,
            min(source.start_ms + 100, source.end_ms),
            text,
        )
        for source, text in zip(plan.sources, targeted_texts, strict=True)
    )
    result = TargetedSecondEvidenceWindowResult(
        source_snapshot=plan.source_snapshot,
        window_id=plan.windows[0].window_id,
        window_start_ms=plan.windows[0].start_ms,
        window_end_ms=plan.windows[0].end_ms,
        segments=target_segments,
        plan_binding_sha256=plan.binding_sha256,
    )
    bindings = bind_targeted_second_evidence(plan, (result,))
    execution = TargetedSecondEvidenceExecution(
        plan=plan,
        policy_version=STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1.version,
        bindings=bindings,
    )
    return targeted_second_evidence_artifact_from_execution(
        execution,
        baseline_asr_artifact_sha256=_baseline_sha256(asr),
        runtime_identity=asr.runtime_identity,
        engine_version=asr.engine_version,
    )


def _projection_for(
    artifact: TargetedSecondEvidenceArtifact,
    asr: ASRResult,
) -> dict[str, object]:
    require_indexes = tuple(
        decision.source_index
        for decision in classify_asr_result_source_quality(asr)
        if decision.action == ASR_SOURCE_REQUIRE_SECOND_EVIDENCE
    )
    return project_targeted_second_evidence_artifact(
        artifact,
        asr_result=asr,
        require_source_indexes=require_indexes,
    )


def _cross_title_replay():
    all_source_ids = set()
    for title, (baseline_path, targeted_path) in FIXTURES.items():
        baseline_raw = baseline_path.read_bytes()
        targeted_raw = targeted_path.read_bytes()
        baseline = parse_asr_result_bytes(baseline_raw)
        targeted = parse_targeted_second_evidence_artifact_bytes(targeted_raw)
        projected = _projection_for(targeted, baseline)
        check(
            set(projected) == {source.cue_id for source in targeted.sources}
            and len(projected) == len(targeted.sources),
            title + "_GENERIC_ID_MAPPING",
        )
        check(
            all(
                set(value.__dict__) == TARGETED_SECOND_EVIDENCE_REVIEW_FIELDS
                and not any(
                    name in value.__dict__
                    for name in ("start_ms", "end_ms", "timing")
                )
                for value in projected.values()
            ),
            title + "_TIMING_FREE_PROJECTION",
        )
        all_source_ids.update(projected)
    check(bool(all_source_ids), "CROSS_TITLE_REQUIRE_PROJECTION_NONEMPTY")


def _asr_only_request_path():
    base = asr_result()
    asr = replace(
        base,
        segments=(
            ASRSegment(1_000, 1_500, "せいせいせいせい"),
            ASRSegment(2_000, 2_500, "通常の発話"),
            ASRSegment(3_000, 3_500, "別の発話"),
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
        generation_key="projection-source",
        claim_token=1,
    )
    prepared = prepare_stateful_asr_package(
        source_package,
        generation_key="projection-filtered",
        asr_result=asr,
    )
    package = prepared.package
    first_pass = StatefulSubtitleResult(
        schema_version=package.schema_version,
        dvd_id=package.dvd_id,
        generation_key=package.generation_key,
        claim_token=package.claim_token,
        session_id=stateful_session_id_for_package(package),
        cues=tuple(
            HermesV2CueOutput(cue.cue_id, None, "번역")
            for cue in package.cues
        ),
    )
    provenance = build_asr_prefilter_provenance(
        asr,
        prepared,
        asr_artifact_sha256=_baseline_sha256(asr),
    )
    target = _artifact_for(asr, ("targeted lexical recovery",))
    plain = build_asr_quality_review_request(
        asr_result=asr,
        package=package,
        result=first_pass,
        prefilter_provenance=provenance,
    )
    attached = build_asr_quality_review_request(
        asr_result=asr,
        package=package,
        result=first_pass,
        prefilter_provenance=provenance,
        targeted_second_evidence_artifact=target,
    )
    check(
        "targeted_second_evidence" not in json.loads(
            serialize_asr_quality_review_request(plain)
        )["cues"][0],
        "ASR_ONLY_ABSENT_TARGET_BACKWARD_WIRE",
    )
    attached_wire = json.loads(serialize_asr_quality_review_request(attached))
    target_wire = attached_wire["cues"][0]["targeted_second_evidence"]
    decision = classify_asr_result_source_quality(asr)[0]
    check(
        attached.cues[0].targeted_second_evidence.text_evidence
        == ("targeted lexical recovery",)
        and target_wire["status"] == "PRESENT_UNRESOLVED"
        and target_wire["segment_count"] == 1
        and target_wire["text_evidence"] == ["targeted lexical recovery"]
        and target_wire["provenance_digest"] == target.binding_sha256
        and attached.cues[0].source_quality.evidence_reasons
        == decision.evidence_reasons,
        "ASR_ONLY_TARGET_AND_EVIDENCE_REASONS",
    )
    check(
        parse_asr_quality_review_request(
            serialize_asr_quality_review_request(attached),
            asr_result=asr,
            package=package,
            result=first_pass,
            targeted_second_evidence_artifact=target,
        )
        == attached,
        "ASR_ONLY_TARGET_ROUND_TRIP",
    )
    expect(
        TargetedSecondEvidenceProjectionError,
        lambda: project_targeted_second_evidence_artifact(
            target,
            asr_result=asr,
            require_source_indexes=(1,),
        ),
        "ASR_ONLY_UNRELATED_TARGET_FAILS_CLOSED",
    )
    expect(
        TargetedSecondEvidenceProjectionError,
        lambda: build_asr_quality_review_request(
            asr_result=asr,
            package=package,
            result=first_pass,
            prefilter_provenance=provenance,
            targeted_second_evidence_artifact=replace(
                target,
                baseline_asr_artifact_sha256="f" * 64,
            ),
        ),
        "ASR_ONLY_WRONG_BASELINE_FAILS_CLOSED",
    )
    return asr, target


def _hybrid_request_path():
    original_route = accepted_hybrid_route()
    original_bundle = original_route.alignment_application.bundle
    asr = replace(
        original_bundle.asr_result,
        segments=(
            ASRSegment(1_000, 1_500, "せいせいせいせい"),
            ASRSegment(2_000, 2_500, "音声二"),
            ASRSegment(3_000, 3_500, "音声三"),
        ),
    )
    route = replace(
        original_route,
        alignment_application=replace(
            original_route.alignment_application,
            bundle=replace(original_bundle, asr_result=asr),
        ),
    )
    preparation = prepare_stateful_hybrid(
        route,
        generation_key="projection-hybrid",
        claim_token=2,
    )
    package = preparation.package
    first_pass = semantic_result(package)
    source_quality = classify_source_document(
        route.alignment_application.bundle.external_ja_document
    )
    target = _artifact_for(asr, ("hybrid targeted recovery",))
    plain = build_review_request(
        preparation=preparation,
        package=package,
        result=first_pass,
        source_quality=source_quality,
    )
    attached = build_review_request(
        preparation=preparation,
        package=package,
        result=first_pass,
        source_quality=source_quality,
        targeted_second_evidence_artifact=target,
    )
    plain_wire = json.loads(serialize_review_request(plain))
    attached_wire = json.loads(serialize_review_request(attached))
    target_cue = next(
        cue for cue in attached.cues if cue.asr_source_quality is not None
    )
    check(
        "targeted_second_evidence" not in plain_wire["cues"][0]
        and all(
            "targeted_second_evidence" not in cue
            for cue in plain_wire["cues"]
        ),
        "HYBRID_ABSENT_TARGET_BACKWARD_WIRE",
    )
    check(
        target_cue.targeted_second_evidence.text_evidence
        == ("hybrid targeted recovery",)
        and attached_wire["cues"][0]["targeted_second_evidence"]["status"]
        == "PRESENT_UNRESOLVED"
        and attached_wire["cues"][0]["targeted_second_evidence"]["segment_count"]
        == 1,
        "HYBRID_ASR_ID_TARGET_MAPPING",
    )
    check(
        parse_review_request(
            serialize_review_request(attached),
            preparation=preparation,
            package=package,
            result=first_pass,
            source_quality=source_quality,
            targeted_second_evidence_artifact=target,
        )
        == attached,
        "HYBRID_TARGET_ROUND_TRIP",
    )

    multi_asr = replace(
        asr,
        segments=(
            ASRSegment(1_000, 1_500, "せいせいせいせい"),
            ASRSegment(2_000, 2_500, "これはこれはこれはこれは"),
            asr.segments[2],
        ),
    )
    multi_route = replace(
        route,
        alignment_application=replace(
            route.alignment_application,
            bundle=replace(route.alignment_application.bundle, asr_result=multi_asr),
        ),
    )
    multi_preparation = prepare_stateful_hybrid(
        multi_route,
        generation_key="projection-hybrid-two",
        claim_token=3,
    )
    multi_package = multi_preparation.package
    multi_first_pass = semantic_result(multi_package)
    multi_target = _artifact_for(
        multi_asr,
        ("targeted first", "targeted second"),
    )
    multi_request = build_review_request(
        preparation=multi_preparation,
        package=multi_package,
        result=multi_first_pass,
        source_quality=source_quality,
        targeted_second_evidence_artifact=multi_target,
    )
    mapped = tuple(
        (
            cue.cue_id,
            cue.asr_source_quality.source_index,
            cue.targeted_second_evidence.text_evidence,
        )
        for cue in multi_request.cues
        if cue.targeted_second_evidence is not None
    )
    check(
        mapped
        == (
            ("ja-000001", 0, ("targeted first", "targeted second")),
            ("ja-000003", 1, ("targeted first", "targeted second")),
        ),
        "HYBRID_MERGED_WINDOW_DETERMINISTIC_MAPPING",
    )
    expect(
        ValueError,
        lambda: build_review_request(
            preparation=preparation,
            package=package,
            result=first_pass,
            source_quality=source_quality,
            targeted_second_evidence_artifact=replace(
                target,
                source_snapshot=replace(
                    target.source_snapshot,
                    source_size=target.source_snapshot.source_size + 1,
                ),
            ),
        ),
        "HYBRID_WRONG_SNAPSHOT_FAILS_CLOSED",
    )
    return target


def _contract_checks():
    optional_digest = parse_targeted_second_evidence_review_projection(
        {
            "status": "PRESENT_UNRESOLVED",
            "text_evidence": ["evidence"],
            "segment_count": 1,
        }
    )
    check(
        optional_digest is not None
        and optional_digest.provenance_digest is None,
        "TARGETED_PROVENANCE_DIGEST_OPTIONAL",
    )
    cue_fields = tuple(field.name for field in fields(HermesV2CueInput))
    request_fields = tuple(field.name for field in fields(HermesV2Request))
    check(
        cue_fields
        == (
            "cue_id",
            "external_ja",
            "stt_ja",
            "en",
            "before_context",
            "after_context",
        )
        and request_fields == ("cues",),
        "HERMES_V2_CONTRACT_UNCHANGED",
    )
    request = HermesV2Request(
        cues=(
            HermesV2CueInput(
                "cue-1", "原文", None, None, (), ()
            ),
        ),
    )
    wire = json.loads(serialize_hermes_v2_request(request))
    check(
        set(wire) == {"cues"}
        and set(wire["cues"][0])
        == {
            "cue_id",
            "external_ja",
            "stt_ja",
            "en",
            "before_context",
            "after_context",
        },
        "HERMES_V2_WIRE_UNCHANGED",
    )


def main():
    _cross_title_replay()
    _asr_only_request_path()
    _hybrid_request_path()
    _contract_checks()
    print("STATEFUL_SECOND_EVIDENCE_PROJECTION_SMOKE_PASS")


if __name__ == "__main__":
    main()
