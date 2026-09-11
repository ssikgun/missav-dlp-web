"""Offline smoke tests for the ASR-first targeted evidence adapter."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from teddy_discovery_asr import (
    ASRResult,
    ASRSegment,
    ASRSourceSnapshot,
)
from teddy_discovery_asr_source_quality import (
    classify_asr_result_source_quality,
)
from teddy_discovery_subtitle import validate_canonical_holding
from teddy_discovery_targeted_second_evidence import (
    TARGETED_SECOND_EVIDENCE_STATUS_EMPTY_UNRESOLVED,
    TARGETED_SECOND_EVIDENCE_STATUS_NOISY_UNRESOLVED,
    TARGETED_SECOND_EVIDENCE_STATUS_PRESENT_UNRESOLVED,
    TargetedSecondEvidenceError,
    TargetedSecondEvidenceWindowResult,
    bind_targeted_second_evidence,
    build_targeted_second_evidence_plan,
    build_targeted_second_evidence_plan_with_policy,
)
from teddy_discovery_targeted_asr_window import (
    STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1,
)


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


def source_snapshot() -> ASRSourceSnapshot:
    dvd_id = "GEN-123"
    holding = validate_canonical_holding(
        {
            "dvd_id": dvd_id,
            "storage_root": "jav",
            "relative_path": "GEN/GEN-123/GEN-123.mp4",
            "parse_status": "MATCHED",
            "present": 1,
        },
        dvd_id,
    )
    return ASRSourceSnapshot.from_holding(
        holding,
        source_size=123_456,
        source_mtime_ns=654_321,
    )


def asr_result() -> ASRResult:
    return ASRResult(
        source_snapshot=source_snapshot(),
        source_language="ja",
        segments=(
            ASRSegment(100, 190, "今日は"),
            ASRSegment(300, 390, "あ、あ、あ、あ"),
            ASRSegment(500, 590, "うん"),
            ASRSegment(700, 790, "一旦、一旦、一旦、一旦"),
        ),
        engine_version="synthetic-second-evidence-1",
    )


def result_for(plan, window, segments):
    return TargetedSecondEvidenceWindowResult(
        source_snapshot=plan.source_snapshot,
        window_id=window.window_id,
        window_start_ms=window.start_ms,
        window_end_ms=window.end_ms,
        segments=tuple(segments),
        plan_binding_sha256=plan.binding_sha256,
    )


def main():
    source = asr_result()
    decisions = classify_asr_result_source_quality(source)
    plan = build_targeted_second_evidence_plan(
        source,
        decisions,
        padding_before_ms=50,
        padding_after_ms=50,
        merge_gap_ms=0,
        max_window_ms=400,
    )
    repeated_plan = build_targeted_second_evidence_plan(
        source,
        decisions,
        padding_before_ms=50,
        padding_after_ms=50,
        merge_gap_ms=0,
        max_window_ms=400,
    )

    check(
        tuple(item.cue_id for item in plan.sources)
        == ("asr-000002", "asr-000004"),
        "REQUIRE_ONLY_CANONICAL_ASR_IDS",
    )
    check(
        tuple(
            (window.window_id, window.start_ms, window.end_ms,
             window.source_ids, window.source_indices)
            for window in plan.windows
        )
        == (
            (
                "targeted-window-000001",
                250,
                440,
                ("asr-000002",),
                (1,),
            ),
            (
                "targeted-window-000002",
                650,
                840,
                ("asr-000004",),
                (3,),
            ),
        ),
        "CALLER_OWNED_PADDING_AND_NO_MERGE",
    )
    check(
        sum(window.end_ms - window.start_ms for window in plan.windows) == 380
        and plan.sources[0].start_ms == 300
        and plan.sources[0].end_ms == 390,
        "ORIGINAL_TIMING_REMAINS_AUTHORITY",
    )
    check(plan == repeated_plan, "DETERMINISTIC_PLAN_REPEAT")

    v1_plan = build_targeted_second_evidence_plan_with_policy(
        source,
        decisions,
        policy=STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1,
    )
    check(
        len(v1_plan.windows) == 1
        and v1_plan.windows[0].start_ms == 0
        and v1_plan.windows[0].end_ms == 5_790
        and v1_plan.windows[0].source_ids
        == ("asr-000002", "asr-000004")
        and tuple(
            (item.start_ms, item.end_ms) for item in v1_plan.sources
        )
        == ((300, 390), (700, 790)),
        "EXPLICIT_V1_POLICY_ADAPTER_PRESERVES_SOURCE_TIMING",
    )
    expect(
        TargetedSecondEvidenceError,
        lambda: build_targeted_second_evidence_plan(
            source,
            decisions,
            padding_before_ms=-1,
            padding_after_ms=50,
            merge_gap_ms=0,
            max_window_ms=400,
        ),
        "INVALID_WINDOW_POLICY_FAILS_CLOSED",
    )

    normal_results = (
        result_for(
            plan,
            plan.windows[0],
            (ASRSegment(300, 350, "短い発話"),),
        ),
        result_for(
            plan,
            plan.windows[1],
            (
                ASRSegment(700, 720, "第一"),
                ASRSegment(730, 780, "第二"),
            ),
        ),
    )
    normal_bindings = bind_targeted_second_evidence(plan, normal_results)
    check(
        len(normal_bindings) == 2
        and normal_bindings[0].status
        == TARGETED_SECOND_EVIDENCE_STATUS_PRESENT_UNRESOLVED
        and normal_bindings[1].targeted_text_evidence == ("第一", "第二")
        and normal_bindings[0].source.start_ms == 300
        and normal_bindings[0].window.start_ms == 250,
        "NORMAL_SINGLE_AND_MULTI_SEGMENT_BINDING",
    )

    empty_results = (
        result_for(plan, plan.windows[0], ()),
        normal_results[1],
    )
    empty_bindings = bind_targeted_second_evidence(plan, empty_results)
    check(
        empty_bindings[0].status
        == TARGETED_SECOND_EVIDENCE_STATUS_EMPTY_UNRESOLVED
        and empty_bindings[0].targeted_text_evidence == (),
        "EMPTY_IS_VALID_UNRESOLVED",
    )

    noisy_results = (
        result_for(
            plan,
            plan.windows[0],
            (ASRSegment(300, 390, "ん" * 64),),
        ),
        normal_results[1],
    )
    noisy_bindings = bind_targeted_second_evidence(plan, noisy_results)
    check(
        noisy_bindings[0].status
        == TARGETED_SECOND_EVIDENCE_STATUS_NOISY_UNRESOLVED,
        "NOISY_IS_VALID_BUT_UNTRUSTED",
    )

    expect(
        TargetedSecondEvidenceError,
        lambda: TargetedSecondEvidenceWindowResult(
            source_snapshot=plan.source_snapshot,
            window_id=plan.windows[0].window_id,
            window_start_ms=plan.windows[0].start_ms,
            window_end_ms=plan.windows[0].end_ms,
            segments=(ASRSegment(249, 300, "outside"),),
            plan_binding_sha256=plan.binding_sha256,
        ),
        "OUTSIDE_WINDOW_FAILS_CLOSED",
    )
    expect(
        TargetedSecondEvidenceError,
        lambda: bind_targeted_second_evidence(
            plan,
            (
                replace(
                    normal_results[0],
                    window_id="targeted-window-000999",
                ),
                normal_results[1],
            ),
        ),
        "UNKNOWN_WINDOW_ID_FAILS_CLOSED",
    )
    expect(
        TargetedSecondEvidenceError,
        lambda: bind_targeted_second_evidence(
            plan,
            (normal_results[0], normal_results[0]),
        ),
        "DUPLICATE_WINDOW_ID_FAILS_CLOSED",
    )
    expect(
        TargetedSecondEvidenceError,
        lambda: replace(
            plan.windows[0],
            source_ids=("asr-000002", "asr-000002"),
            source_indices=(1, 1),
        ),
        "DUPLICATE_SOURCE_MEMBERSHIP_FAILS_CLOSED",
    )
    expect(
        TargetedSecondEvidenceError,
        lambda: replace(
            plan,
            sources=(
                replace(plan.sources[0], start_ms=301),
                plan.sources[1],
            ),
        ),
        "SOURCE_TIMING_MUTATION_FAILS_CLOSED",
    )
    expect(
        TargetedSecondEvidenceError,
        lambda: bind_targeted_second_evidence(
            plan,
            (
                replace(normal_results[0], plan_binding_sha256="0" * 64),
                normal_results[1],
            ),
        ),
        "PROVENANCE_DIGEST_MISMATCH_FAILS_CLOSED",
    )

    merged_plan = build_targeted_second_evidence_plan(
        source,
        decisions,
        padding_before_ms=50,
        padding_after_ms=50,
        merge_gap_ms=300,
        max_window_ms=1_000,
    )
    check(
        len(merged_plan.windows) == 1
        and merged_plan.windows[0].source_ids
        == ("asr-000002", "asr-000004")
        and merged_plan.windows[0].source_indices == (1, 3),
        "DETERMINISTIC_MERGED_MEMBERSHIP",
    )

    source_text = Path(
        "teddy_discovery_targeted_second_evidence.py"
    ).read_text(encoding="utf-8")
    check(
        "transcribe" not in source_text
        and "RemoteFasterWhisperASR" not in source_text,
        "NO_REMOTE_OR_MODEL_CALL_IN_ADAPTER",
    )
    check(
        "EVIDENCE_SOURCE_EXTERNAL_JA" not in source_text
        and "RobustAffineAlignment" not in source_text,
        "NO_HYBRID_IDENTITY_OR_AFFINE_DEPENDENCY",
    )

    print("SMOKE_PASS_COUNT=" + str(passes))
    print("SMOKE_FAIL_COUNT=" + str(fails))


if __name__ == "__main__":
    main()
