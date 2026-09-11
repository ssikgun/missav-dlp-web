"""Offline targeted second-evidence and HYBRID binding smoke tests."""

from pathlib import Path

from teddy_discovery_alignment import AffineAnchorResidual, RobustAffineAlignment
from teddy_discovery_asr import ASRSegment, ASRSourceSnapshot
from teddy_discovery_hybrid_evidence import HybridCueIdentity
from teddy_discovery_subtitle_text import SubtitleCue
from teddy_discovery_subtitle_v2_pipeline import (
    SubtitleV2PipelineError,
    run_subtitle_v2_pipeline,
)
from teddy_discovery_targeted_hybrid_evidence import (
    TargetedASRBinding,
    TargetedASRWindowEvidence,
    TargetedHybridEvidenceError,
    build_targeted_asr_bindings,
)

import teddy_discovery_subtitle_v2_pipeline_smoke as fixture


passes = 0
fails = 0


def check(condition: bool, marker: str):
    global passes, fails
    if not condition:
        fails += 1
        raise AssertionError(marker)
    passes += 1
    print("PASS=" + marker)


def expect(error_type, callback, marker: str):
    global passes, fails
    try:
        callback()
    except error_type:
        passes += 1
        print("PASS=" + marker)
        return
    except Exception as error:
        fails += 1
        raise AssertionError(
            marker + ": wrong exception " + type(error).__name__
        ) from error
    fails += 1
    raise AssertionError(marker)


def make_binding(
    route,
    external_index: int,
    text: str,
    *,
    source_snapshot: ASRSourceSnapshot | None = None,
    external_cue_ids: tuple[str, ...] | None = None,
    segment_start_ms: int = 1_700,
    segment_end_ms: int = 1_800,
    segments: tuple[ASRSegment, ...] | None = None,
    segment_index: int = 0,
) -> TargetedASRBinding:
    bundle = route.alignment_application.bundle
    snapshot = source_snapshot or bundle.asr_result.source_snapshot
    cue_id = HybridCueIdentity.for_external_ja(external_index)
    evidence = TargetedASRWindowEvidence(
        source_snapshot=snapshot,
        window_start_ms=1_600,
        window_end_ms=2_600,
        external_cue_ids=external_cue_ids or (cue_id.cue_id,),
        segments=segments
        or (
            ASRSegment(
                segment_start_ms,
                segment_end_ms,
                text,
            ),
        ),
    )
    return TargetedASRBinding(
        external_identity=cue_id,
        evidence=evidence,
        segment_index=segment_index,
    )


def run_with(route, *bindings):
    boundary = fixture.FakeSemanticBoundary()
    result = run_subtitle_v2_pipeline(
        route,
        semantic_boundary=boundary,
        targeted_bindings=tuple(bindings),
    )
    return result, boundary


def timing_cues() -> tuple[SubtitleCue, ...]:
    return tuple(
        SubtitleCue(start_ms, end_ms, "external text " + str(index))
        for index, (start_ms, end_ms) in enumerate(
            (
                (100, 200),
                (300, 400),
                (500, 600),
                (700, 800),
                (900, 1_000),
            )
        )
    )


def timing_alignment(
    external_cues: tuple[SubtitleCue, ...],
    *,
    intercept_ms: int = 0,
) -> RobustAffineAlignment:
    residuals = tuple(
        AffineAnchorResidual(
            external_identity=HybridCueIdentity.for_external_ja(external_index),
            asr_identity=HybridCueIdentity.for_asr_segment(asr_index),
            external_midpoint_x2=(
                external_cues[external_index].start_ms
                + external_cues[external_index].end_ms
            ),
            asr_midpoint_x2=(
                external_cues[external_index].start_ms
                + external_cues[external_index].end_ms
                + (2 * intercept_ms)
            ),
            predicted_asr_midpoint_ms=(
                (
                    external_cues[external_index].start_ms
                    + external_cues[external_index].end_ms
                )
                / 2
                + intercept_ms
            ),
            signed_residual_ms=0.0,
            absolute_residual_ms=0.0,
            is_inlier=True,
        )
        for asr_index, external_index in enumerate((0, 2, 4))
    )
    return RobustAffineAlignment(
        scale=1.0,
        intercept_ms=float(intercept_ms),
        anchor_count=3,
        inlier_count=3,
        residual_threshold_ms=1,
        residuals=residuals,
        median_absolute_residual_ms=0.0,
    )


def make_timing_evidence(
    route,
    external_cue_ids: tuple[str, ...],
    segments: tuple[ASRSegment, ...],
    *,
    window_start_ms: int = 0,
    window_end_ms: int = 2_000,
) -> TargetedASRWindowEvidence:
    return TargetedASRWindowEvidence(
        source_snapshot=route.alignment_application.bundle.asr_result.source_snapshot,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        external_cue_ids=external_cue_ids,
        segments=segments,
    )


def main():
    route = fixture.accepted_hybrid_route()
    external_cues = timing_cues()
    alignment = timing_alignment(external_cues, intercept_ms=100)
    clear = build_targeted_asr_bindings(
        external_cues,
        alignment,
        make_timing_evidence(
            route,
            ("ja-000002",),
            (ASRSegment(420, 480, "unrelated wording"),),
        ),
    )
    check(
        len(clear) == 1
        and clear[0].external_identity == HybridCueIdentity.for_external_ja(1)
        and clear[0].segment_index == 0,
        "ONE_CUE_ONE_SEGMENT_TIMING_BINDING",
    )

    multiple_unique = build_targeted_asr_bindings(
        external_cues,
        alignment,
        make_timing_evidence(
            route,
            ("ja-000002", "ja-000004"),
            (
                ASRSegment(420, 480, "first wording"),
                ASRSegment(820, 880, "second wording"),
            ),
        ),
    )
    check(
        tuple(binding.external_identity.source_index for binding in multiple_unique)
        == (1, 3)
        and tuple(binding.segment_index for binding in multiple_unique) == (0, 1),
        "MULTIPLE_CUES_UNIQUE_BY_TIME",
    )

    far = build_targeted_asr_bindings(
        external_cues,
        alignment,
        make_timing_evidence(
            route,
            ("ja-000002",),
            (ASRSegment(600, 650, "far away"),),
        ),
    )
    check(not far, "NON_OVERLAPPING_SEGMENT_IS_UNBOUND")

    ambiguous_cues = (
        SubtitleCue(100, 200, "zero"),
        SubtitleCue(300, 450, "one"),
        SubtitleCue(350, 380, "two"),
        SubtitleCue(400, 550, "three"),
        SubtitleCue(600, 700, "four"),
    )
    ambiguous_segment = build_targeted_asr_bindings(
        ambiguous_cues,
        timing_alignment(ambiguous_cues),
        make_timing_evidence(
            route,
            ("ja-000002", "ja-000004"),
            (ASRSegment(425, 475, "overlap"),),
        ),
    )
    check(not ambiguous_segment, "ONE_SEGMENT_OVERLAPPING_TWO_CUES_UNBOUND")

    competing_segments = build_targeted_asr_bindings(
        external_cues,
        timing_alignment(external_cues),
        make_timing_evidence(
            route,
            ("ja-000002",),
            (
                ASRSegment(320, 350, "first competition"),
                ASRSegment(360, 390, "second competition"),
            ),
        ),
    )
    check(not competing_segments, "TWO_SEGMENTS_COMPETING_FOR_CUE_UNBOUND")

    baseline_priority = build_targeted_asr_bindings(
        external_cues,
        timing_alignment(external_cues),
        make_timing_evidence(
            route,
            ("ja-000001", "ja-000002"),
            (
                ASRSegment(120, 180, "baseline overlap"),
                ASRSegment(320, 380, "targeted gap"),
            ),
        ),
    )
    check(
        tuple(binding.external_identity.source_index for binding in baseline_priority)
        == (1,),
        "BASELINE_RESIDUAL_CUE_IS_NOT_TARGETED",
    )

    expect(
        TargetedHybridEvidenceError,
        lambda: build_targeted_asr_bindings(
            external_cues,
            timing_alignment(external_cues),
            make_timing_evidence(
                route,
                ("ja-000002",),
                (ASRSegment(320, 340, "detached window"),),
                window_start_ms=0,
                window_end_ms=350,
            ),
        ),
        "PROJECTED_CUE_OUTSIDE_WINDOW_FAILS_CLOSED",
    )
    expect(
        TargetedHybridEvidenceError,
        lambda: build_targeted_asr_bindings(
            external_cues,
            timing_alignment(external_cues),
            make_timing_evidence(
                route,
                ("ja-999999",),
                (ASRSegment(320, 380, "detached identity"),),
            ),
        ),
        "DETACHED_TARGETED_CUE_ID_FAILS_CLOSED",
    )

    baseline_and_targeted = (
        make_binding(route, 0, "targeted override"),
        make_binding(route, 1, "targeted evidence"),
    )
    result, boundary = run_with(route, *baseline_and_targeted)
    request = boundary.requests[0]
    check(
        request.cues[0].stt_ja == route.alignment_application.bundle.asr_result.segments[0].text,
        "BASELINE_EVIDENCE_REMAINS_AUTHORITATIVE",
    )
    check(
        request.cues[1].stt_ja == "targeted evidence",
        "TARGETED_EVIDENCE_FILLS_BASELINE_GAP",
    )
    check(
        request.cues[1].external_ja
        == route.alignment_application.bundle.external_ja_document.cues[1].text,
        "EXTERNAL_JA_BACKBONE_REMAINS_EXACT",
    )
    bindings = result.semantic_result.semantic_plan.semantic_bindings
    check(
        bindings[0].asr_identity is not None
        and bindings[0].targeted_asr_evidence is None,
        "BASELINE_BINDING_WINS_OVER_TARGETED",
    )
    check(
        bindings[1].asr_identity is None
        and bindings[1].targeted_asr_evidence is not None,
        "TARGETED_BINDING_IS_SEPARATE_FROM_ASR_IDENTITY",
    )

    wrong_timing_result, wrong_timing_boundary = run_with(
        route,
        make_binding(
            route,
            1,
            "window membership is insufficient",
            segment_start_ms=2_500,
            segment_end_ms=2_550,
        ),
    )
    check(
        wrong_timing_boundary.requests[0].cues[1].stt_ja is None
        and wrong_timing_result.semantic_result.semantic_plan.semantic_bindings[
            1
        ].targeted_asr_evidence
        is None,
        "WINDOW_MEMBERSHIP_ONLY_BINDING_IS_OMITTED",
    )

    arbitrary_index_result, arbitrary_index_boundary = run_with(
        route,
        make_binding(
            route,
            1,
            "caller-selected wrong segment",
            segments=(
                ASRSegment(1_700, 1_800, "canonical timing segment"),
                ASRSegment(2_500, 2_550, "caller-selected wrong segment"),
            ),
            segment_index=1,
        ),
    )
    arbitrary_index_binding = (
        arbitrary_index_result.semantic_result.semantic_plan.semantic_bindings[1]
    )
    check(
        arbitrary_index_boundary.requests[0].cues[1].stt_ja
        == "canonical timing segment"
        and arbitrary_index_binding.targeted_asr_evidence is not None
        and arbitrary_index_binding.targeted_asr_evidence.segment_index == 0,
        "ARBITRARY_SEGMENT_INDEX_IS_REPLACED_BY_TIMING_BINDING",
    )

    repeated = make_binding(route, 1, "あ" * 64)
    repeated_result, repeated_boundary = run_with(route, repeated)
    check(
        repeated_boundary.requests[0].cues[1].stt_ja is None,
        "RUNAWAY_TARGETED_TEXT_IS_OMITTED",
    )
    check(
        repeated_boundary.requests[0].cues[1].external_ja
        == route.alignment_application.bundle.external_ja_document.cues[1].text
        and repeated_result.semantic_result.semantic_plan.semantic_bindings[1].targeted_asr_evidence
        is None,
        "OMITTED_TARGETED_EVIDENCE_LEAVES_EXTERNAL_CUE",
    )

    detached_snapshot = ASRSourceSnapshot(
        dvd_id=route.alignment_application.bundle.asr_result.source_snapshot.dvd_id,
        canonical_video_relative=route.alignment_application.bundle.asr_result.source_snapshot.canonical_video_relative,
        source_size=route.alignment_application.bundle.asr_result.source_snapshot.source_size + 1,
        source_mtime_ns=route.alignment_application.bundle.asr_result.source_snapshot.source_mtime_ns,
    )
    expect(
        SubtitleV2PipelineError,
        lambda: run_with(make_binding(route, 1, "detached", source_snapshot=detached_snapshot)),
        "DETACHED_SOURCE_SNAPSHOT_FAILS_CLOSED",
    )
    expect(
        TargetedHybridEvidenceError,
        lambda: make_binding(
            route,
            1,
            "outside",
            external_cue_ids=("ja-000002",),
            segment_start_ms=1_500,
            segment_end_ms=2_700,
        ),
        "DETACHED_ABSOLUTE_WINDOW_FAILS_CLOSED",
    )
    expect(
        TargetedHybridEvidenceError,
        lambda: make_binding(
            route,
            1,
            "missing association",
            external_cue_ids=("ja-000001",),
        ),
        "MISSING_CUE_ASSOCIATION_FAILS_CLOSED",
    )
    expect(
        SubtitleV2PipelineError,
        lambda: run_with(route, baseline_and_targeted[1], baseline_and_targeted[1]),
        "DUPLICATE_CUE_ASSOCIATION_FAILS_CLOSED",
    )
    expect(
        SubtitleV2PipelineError,
        lambda: run_with(make_binding(route, 99, "out of range")),
        "OUT_OF_RANGE_CUE_ASSOCIATION_FAILS_CLOSED",
    )

    for path in (
        "teddy_discovery_targeted_hybrid_evidence.py",
        "teddy_discovery_subtitle_v2_pipeline.py",
        "teddy_discovery_subtitle_v2_orchestrator.py",
    ):
        source = Path(path).read_text(encoding="utf-8")
        check("JUR-750" not in source, "NO_TITLE_SPECIFIC_LOGIC_" + path)

    print("SMOKE_PASS_COUNT=" + str(passes))
    print("SMOKE_FAIL_COUNT=" + str(fails))


if __name__ == "__main__":
    main()
