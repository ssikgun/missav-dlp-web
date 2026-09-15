"""Offline synthetic tests for the deterministic HYBRID/stateful bridge."""

from copy import copy
from dataclasses import replace
import json
from unittest.mock import patch

import teddy_discovery_subtitle_v2_pipeline_smoke as fixture
from teddy_discovery_targeted_hybrid_evidence_smoke import make_binding
from teddy_discovery_stateful_hybrid import (
    StatefulHybridValidationError, build_stateful_hybrid_package,
    materialize_stateful_hybrid_srt, prepare_stateful_hybrid,
)
from teddy_discovery_stateful_translator import (
    StatefulSubtitlePackage, StatefulSubtitleResult, StatefulTranslatorError,
    bind_stateful_semantic_policy,
    serialize_stateful_package, stateful_session_id_for_package,
)
from teddy_discovery_subtitle_v2_pipeline import _build_hybrid_plan, SubtitleV2PipelineError
from teddy_discovery_subtitle_v2_orchestrator import SubtitleV2OrchestratorError
from teddy_discovery_hermes_v2 import HermesV2CueOutput
from teddy_discovery_stateful_parts import build_stateful_part_plan


def changed(value, **attributes):
    """Simulate detached frozen objects at a trust boundary."""
    result = copy(value)
    for key, item in attributes.items():
        object.__setattr__(result, key, item)
    return result


def extended_route(count=513, url="https://source.example.test/ja.srt"):
    original = fixture.accepted_hybrid_route()
    bundle = original.alignment_application.bundle
    cues = bundle.external_ja_document.cues + tuple(
        fixture.SubtitleCue(4000 + i * 1000, 4500 + i * 1000, f"追加{i}")
        for i in range(count - 4)
    )
    payload = fixture.ExternalSubtitlePayload.from_bytes(
        dvd_id=fixture.DVD_ID,
        candidate=fixture.SubtitleCandidate.validated_external_text(
            url, dvd_id=fixture.DVD_ID, language="ja", text_format="srt",
        ),
        payload=fixture.generate_korean_srt(cues).payload,
    )
    bundle = fixture.HybridEvidenceBundle.from_external_ja_and_asr(
        dvd_id=bundle.dvd_id, external_ja_payload=payload,
        external_ja_document=payload.parse(), asr_result=bundle.asr_result,
        alignment=bundle.alignment,
    )
    application = fixture.apply_alignment_acceptance(
        bundle, original.alignment_application.decision,
        alignment=original.alignment_application.alignment,
    )
    return replace(original, alignment_application=application)


def semantic_result(package):
    return StatefulSubtitleResult(
        schema_version=package.schema_version, dvd_id=package.dvd_id,
        generation_key=package.generation_key, claim_token=package.claim_token,
        session_id=stateful_session_id_for_package(package),
        cues=tuple(HermesV2CueOutput(cue.cue_id, None, f"번역 {i}")
                   for i, cue in enumerate(package.cues)),
    )


def main():
    passed = 0

    def check(value, label):
        nonlocal passed
        assert value, label
        passed += 1
        print("PASS=" + label)

    def reject(callback, label):
        try:
            callback()
        except (StatefulHybridValidationError, StatefulTranslatorError,
                SubtitleV2PipelineError, SubtitleV2OrchestratorError):
            check(True, label)
        else:
            raise AssertionError(label)

    kwargs = dict(generation_key="hybrid-fixture-v1", claim_token=7)
    route = fixture.accepted_hybrid_route()
    target = make_binding(route, 1, "補助音声")
    prepared = prepare_stateful_hybrid(route, targeted_bindings=(target,), **kwargs)
    package = prepared.package
    result = semantic_result(package)

    def finish(p=package, r=result, source=route, proof=prepared):
        return materialize_stateful_hybrid_srt(p, r, source, proof)

    plan = _build_hybrid_plan(route, targeted_bindings=(target,))
    check(
        len(prepared.asr_source_quality_decisions)
        == len(route.alignment_application.bundle.asr_result.segments)
        and plan.asr_source_quality_decisions
        == prepared.asr_source_quality_decisions,
        "generic-asr-source-quality-provenance",
    )
    noisy_asr = replace(
        route.alignment_application.bundle.asr_result,
        segments=(fixture.ASRSegment(1000, 1500, "ああああ"),)
        + route.alignment_application.bundle.asr_result.segments[1:],
    )
    noisy_bundle = replace(
        route.alignment_application.bundle,
        asr_result=noisy_asr,
    )
    noisy_application = replace(
        route.alignment_application,
        bundle=noisy_bundle,
    )
    noisy_route = replace(route, alignment_application=noisy_application)
    suppressed = prepare_stateful_hybrid(
        noisy_route,
        generation_key="hybrid-noisy-source",
        claim_token=7,
    )
    check(
        suppressed.asr_source_quality_decisions[0].action == "OMIT"
        and suppressed.package.cues[0].external_ja
        == route.alignment_application.bundle.external_ja_document.cues[0].text
        and suppressed.package.cues[0].stt_ja is None
        and suppressed.semantic_bindings[0].external_ja_identity
        == route.alignment_application.bundle.cue_evidence[0].identity
        and suppressed.semantic_bindings[0].asr_identity is None,
        "hybrid-omit-suppresses-only-baseline-asr",
    )
    check(package.cues == plan.hermes_request.cues, "exact-one-shot-cue-equality")
    check(prepared.semantic_bindings == plan.semantic_bindings, "exact-binding-equality")
    check(type(package) is StatefulSubtitlePackage, "existing-stateful-exact-type")
    check(build_stateful_hybrid_package(route, targeted_bindings=(target,), **kwargs)
          == package, "public-package-builder")
    check(package.cues[0].stt_ja == route.alignment_application.bundle.asr_result.segments[0].text,
          "baseline-stt")
    check(package.cues[1].stt_ja == target.segment.text, "targeted-fallback")
    empty = prepare_stateful_hybrid(route, **kwargs)
    check(empty.package.cues[1].stt_ja is None and len(empty.package.cues) == 4,
          "external-only-preserved")
    repeated = prepare_stateful_hybrid(
        route, targeted_bindings=(make_binding(route, 1, "あ" * 64),), **kwargs,
    )
    check(repeated.package.cues[1].stt_ja is None
          and repeated.semantic_bindings[1].targeted_asr_evidence is None,
          "existing-runaway-skip")
    baseline_target = make_binding(route, 0, "ignored baseline competitor")
    baseline = prepare_stateful_hybrid(route, targeted_bindings=(baseline_target,), **kwargs)
    check(baseline.package == empty.package
          and baseline.semantic_bindings[0].targeted_asr_evidence is None,
          "baseline-precedence-no-double-ownership")
    bad_binding = replace(prepared.semantic_bindings[0], targeted_asr_evidence=baseline_target)
    reject(lambda: replace(prepared, semantic_bindings=(bad_binding,) + prepared.semantic_bindings[1:]),
           "simultaneous-semantic-ownership-rejected")
    snapshot = replace(target.evidence.source_snapshot, source_size=987654)
    detached = replace(target, evidence=replace(target.evidence, source_snapshot=snapshot))
    reject(lambda: prepare_stateful_hybrid(route, targeted_bindings=(detached,), **kwargs),
           "detached-targeted-snapshot")
    reject(lambda: prepare_stateful_hybrid(fixture.direct_asr_route(), **kwargs), "non-hybrid-route")
    reject(lambda: prepare_stateful_hybrid(changed(route, state=fixture.V2_FAILED_CLOSED), **kwargs),
           "not-ready-route")
    reject(lambda: prepare_stateful_hybrid(route, targeted_bindings=(target, target), **kwargs),
           "duplicate-targeted-cue-rejected")
    reject(lambda: prepare_stateful_hybrid(route, targeted_bindings=(replace(
        target, evidence=changed(target.evidence, window_start_ms=1800)),), **kwargs),
        "detached-targeted-window")
    reject(lambda: prepare_stateful_hybrid(route, targeted_bindings=(changed(
        target, external_identity=fixture.HybridCueIdentity.for_external_ja(2)),), **kwargs),
        "detached-targeted-cue-identity")
    competing = make_binding(route, 1, "unused", segments=(
        fixture.ASRSegment(1700, 1800, "first"), fixture.ASRSegment(1900, 1950, "second"),
    ))
    check(prepare_stateful_hybrid(route, targeted_bindings=(competing,), **kwargs).package.cues[1].stt_ja is None,
          "canonical-ambiguous-competition-omitted")
    noncanonical = make_binding(route, 1, "unused", segments=(
        fixture.ASRSegment(1700, 1800, "canonical"), fixture.ASRSegment(2550, 2600, "detached"),
    ), segment_index=1)
    check(prepare_stateful_hybrid(route, targeted_bindings=(noncanonical,), **kwargs).package.cues[1].stt_ja
          == "canonical", "canonical-reconstruction-not-caller-segment-index")

    large_route = extended_route()
    with patch("teddy_discovery_subtitle_v2_pipeline.HermesV2Request",
               side_effect=AssertionError("one-shot transport used")):
        large = prepare_stateful_hybrid(large_route, **kwargs)
        check(build_stateful_hybrid_package(large_route, **kwargs) == large.package,
              "large-public-builder-no-HermesV2Request")
    check(len(large.package.cues) == 513, "513-cues-without-one-shot-request")
    reject(lambda: _build_hybrid_plan(large_route, targeted_bindings=()), "one-shot-512-limit-unchanged")
    wire = json.loads(serialize_stateful_package(large.package))
    check(len(wire["cues"]) == 513 and "route_decision" not in wire,
          "ordinary-stateful-wire-no-timing-proof")
    bound_large = bind_stateful_semantic_policy(large.package)
    parts = build_stateful_part_plan(
        bound_large,
        serialize_stateful_package(bound_large),
    )
    check(parts.part_count == 9, "fixed64-part-planner")
    check(len(build_stateful_hybrid_package(extended_route(4096), **kwargs).cues) == 4096,
          "stateful-4096-limit-supported")
    reject(lambda: build_stateful_hybrid_package(extended_route(4097), **kwargs),
           "stateful-over-limit-rejected")
    large_srt = materialize_stateful_hybrid_srt(
        large.package, semantic_result(large.package), large_route, large,
    )
    check(large_srt.artifact.cue_count == 513, "large-finalizer-count")

    final = finish()
    document = fixture.parse_subtitle_bytes(final.artifact.payload, text_format="srt")
    check(final.source_indexes == (0, 1, 2, 3), "ja-identity-source-order")
    check(tuple((c.start_ms, c.end_ms) for c in document.cues)
          == ((1000, 1500), (1600, 2500), (2000, 2500), (3000, 3500)),
          "accepted-affine-external-timing")
    check((document.cues[1].start_ms, document.cues[1].end_ms)
          != (target.segment.start_ms, target.segment.end_ms), "targeted-not-timing-authority")
    check(tuple(c.text for c in document.cues) == tuple(c.ko for c in result.cues),
          "korean-only-from-result")
    reject(lambda: finish(r=replace(result, cues=result.cues[:-1])), "result-missing-cue")
    reject(lambda: finish(r=replace(result, cues=tuple(reversed(result.cues)))), "result-reordered")
    reject(lambda: finish(r=replace(result, cues=(replace(result.cues[0], cue_id="ja-9999"),)
                                    + result.cues[1:])), "result-wrong-id")
    reject(lambda: finish(p=replace(package, dvd_id="OTHER-123")), "wrong-dvd")
    reject(lambda: finish(p=replace(package, generation_key="other")), "wrong-generation")
    reject(lambda: finish(r=replace(result, claim_token=8)), "wrong-result-claim")
    reject(lambda: finish(proof=changed(prepared, semantic_bindings=(changed(
        prepared.semantic_bindings[0], source_index=False),) + prepared.semantic_bindings[1:])),
        "non-exact-binding-source-index")
    reject(lambda: finish(proof=changed(prepared, semantic_bindings=(replace(
        prepared.semantic_bindings[0], external_ja_identity=fixture.HybridCueIdentity.for_external_ja(1)),)
        + prepared.semantic_bindings[1:])), "wrong-external-identity")
    reject(lambda: finish(p=replace(package, cues=tuple(reversed(package.cues)))), "package-reordered")
    app = route.alignment_application
    reject(lambda: finish(source=changed(route, alignment_application=changed(
        app, alignment=changed(app.alignment, intercept_ms=500)))), "detached-alignment")
    reject(lambda: finish(source=changed(route, alignment_application=changed(
        app, bundle=changed(app.bundle, external_ja_document=large_route.alignment_application.bundle.external_ja_document)))),
        "detached-external-document")
    alternate = extended_route(4, "https://other.example.test/ja.srt")
    alt_prepared = prepare_stateful_hybrid(extended_route(4), **kwargs)
    check(prepare_stateful_hybrid(alternate, **kwargs).package == alt_prepared.package,
          "same-semantics-different-source-fixture")
    reject(lambda: materialize_stateful_hybrid_srt(
        alt_prepared.package, semantic_result(alt_prepared.package), alternate, alt_prepared),
        "valid-but-different-external-source-rejected")
    reject(lambda: finish(proof=changed(prepared, semantic_bindings=(bad_binding,)
                                      + prepared.semantic_bindings[1:])), "detached-proof-revalidated")
    with patch("teddy_discovery_stateful_hybrid.project_affine_timestamp_ms", side_effect=[2000, 1000]):
        reject(finish, "projected-duration-inversion")
    with patch("teddy_discovery_stateful_hybrid.project_affine_timestamp_ms", side_effect=[1000, 1500, 900, 1600]):
        reject(finish, "projected-start-order-inversion")
    segments = app.bundle.asr_result.segments
    shifted_asr = replace(app.bundle.asr_result, segments=(replace(segments[0], start_ms=900, end_ms=1600),)
                          + segments[1:])
    shifted_bundle = replace(app.bundle, asr_result=shifted_asr)
    shifted_route = replace(route, alignment_application=replace(app, bundle=shifted_bundle))
    shifted = prepare_stateful_hybrid(shifted_route, **kwargs)
    shifted_final = materialize_stateful_hybrid_srt(
        shifted.package, semantic_result(shifted.package), shifted_route, shifted)
    check(shifted_final.artifact == materialize_stateful_hybrid_srt(
        empty.package, semantic_result(empty.package), route, empty).artifact,
        "baseline-segment-not-timing-authority")
    print(f"PASS={passed} FAIL=0")


if __name__ == "__main__":
    main()
