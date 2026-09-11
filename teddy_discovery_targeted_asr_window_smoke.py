from dataclasses import FrozenInstanceError

from teddy_discovery_alignment import (
    AffineAnchorResidual,
    RobustAffineAlignment,
)
from teddy_discovery_subtitle_text import SubtitleCue
from teddy_discovery_targeted_asr_window import (
    MAX_TARGETED_ASR_WINDOW_MS,
    STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1,
    TargetedSecondEvidenceWindowPolicy,
    TargetedASRWindowError,
    plan_targeted_asr_windows,
    plan_targeted_asr_windows_with_policy,
    validate_targeted_second_evidence_window_policy,
)
from teddy_discovery_hybrid_evidence import HybridCueIdentity


passes = 0
fails = 0


def check(condition: bool, marker: str):
    global passes, fails
    if not condition:
        fails += 1
        raise AssertionError(marker)
    passes += 1
    print("PASS=" + marker)


def expect_error(callback, marker: str):
    global passes, fails
    try:
        callback()
    except TargetedASRWindowError:
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


def alignment() -> RobustAffineAlignment:
    residuals = tuple(
        AffineAnchorResidual(
            external_identity=HybridCueIdentity.for_external_ja(index),
            asr_identity=HybridCueIdentity.for_asr_segment(index),
            external_midpoint_x2=external_midpoint_x2,
            asr_midpoint_x2=external_midpoint_x2,
            predicted_asr_midpoint_ms=external_midpoint_x2 / 2,
            signed_residual_ms=0.0,
            absolute_residual_ms=0.0,
            is_inlier=True,
        )
        for index, external_midpoint_x2 in enumerate((200, 600, 1000))
    )
    return RobustAffineAlignment(
        scale=1.0,
        intercept_ms=0.0,
        anchor_count=3,
        inlier_count=3,
        residual_threshold_ms=1,
        residuals=residuals,
        median_absolute_residual_ms=0.0,
    )


def cues(*intervals: tuple[int, int]) -> tuple[SubtitleCue, ...]:
    return tuple(
        SubtitleCue(start_ms, end_ms, "synthetic cue " + str(index))
        for index, (start_ms, end_ms) in enumerate(intervals)
    )


v1_policy = STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1
check(
    (
        v1_policy.pre_padding_ms,
        v1_policy.post_padding_ms,
        v1_policy.merge_gap_ms,
        v1_policy.max_window_ms,
        v1_policy.version,
    )
    == (5_000, 5_000, 10_000, 60_000, "v1"),
    "V1_POLICY_EXACT_VALUES",
)
check(
    validate_targeted_second_evidence_window_policy(v1_policy)
    == v1_policy,
    "V1_POLICY_VALIDATES",
)
try:
    v1_policy.pre_padding_ms = 1
except FrozenInstanceError:
    check(True, "V1_POLICY_IMMUTABLE")
else:
    check(False, "V1_POLICY_IMMUTABLE")

expect_error(
    lambda: TargetedSecondEvidenceWindowPolicy(
        pre_padding_ms=-1,
        post_padding_ms=5_000,
        merge_gap_ms=10_000,
        max_window_ms=60_000,
        version="v1",
    ),
    "V1_POLICY_NEGATIVE_PADDING_REJECTED",
)
expect_error(
    lambda: TargetedSecondEvidenceWindowPolicy(
        pre_padding_ms=0,
        post_padding_ms=0,
        merge_gap_ms=0,
        max_window_ms=MAX_TARGETED_ASR_WINDOW_MS + 1,
        version="v1",
    ),
    "V1_POLICY_OVERSIZED_VALUE_REJECTED",
)
expect_error(
    lambda: TargetedSecondEvidenceWindowPolicy(
        pre_padding_ms=500,
        post_padding_ms=500,
        merge_gap_ms=0,
        max_window_ms=1_000,
        version="v1",
    ),
    "V1_POLICY_IMPOSSIBLE_PADDING_REJECTED",
)
expect_error(
    lambda: TargetedSecondEvidenceWindowPolicy(
        pre_padding_ms=5_000,
        post_padding_ms=5_000,
        merge_gap_ms=10_000,
        max_window_ms=60_000,
        version="",
    ),
    "V1_POLICY_MALFORMED_VERSION_REJECTED",
)

v1_single = plan_targeted_asr_windows_with_policy(
    cues((100, 200)),
    alignment(),
    policy=v1_policy,
)
check(
    len(v1_single) == 1
    and v1_single[0].start_ms == 0
    and v1_single[0].end_ms == 5_200
    and v1_single[0].external_cue_ids == ("ja-000001",),
    "V1_POLICY_ADAPTER_REUSES_EXISTING_GEOMETRY",
)


single = plan_targeted_asr_windows(
    cues((100, 200)),
    alignment(),
    padding_before_ms=50,
    padding_after_ms=75,
    merge_gap_ms=0,
    max_window_ms=500,
)
check(
    single[0].start_ms == 50
    and single[0].end_ms == 275
    and single[0].external_cue_ids == ("ja-000001",),
    "SINGLE_CUE_PADDING_AND_ID",
)


close = plan_targeted_asr_windows(
    cues((100, 200), (250, 350)),
    alignment(),
    padding_before_ms=10,
    padding_after_ms=10,
    merge_gap_ms=50,
    max_window_ms=500,
)
check(
    close == (
        close[0],
    )
    and close[0].start_ms == 90
    and close[0].end_ms == 360
    and close[0].external_cue_ids == ("ja-000001", "ja-000002"),
    "CLOSE_CUES_MERGED",
)


far = plan_targeted_asr_windows(
    cues((100, 200), (1000, 1100)),
    alignment(),
    padding_before_ms=10,
    padding_after_ms=10,
    merge_gap_ms=50,
    max_window_ms=500,
)
check(
    len(far) == 2
    and far[0].external_cue_ids == ("ja-000001",)
    and far[1].external_cue_ids == ("ja-000002",),
    "DISTANT_CUES_SEPARATED",
)


boundary = plan_targeted_asr_windows(
    cues((10, 100)),
    alignment(),
    padding_before_ms=50,
    padding_after_ms=0,
    merge_gap_ms=0,
    max_window_ms=100,
)
check(boundary[0].start_ms == 0, "ZERO_BOUNDARY_CLAMP")


max_split = plan_targeted_asr_windows(
    cues((100, 300), (350, 550)),
    alignment(),
    padding_before_ms=0,
    padding_after_ms=0,
    merge_gap_ms=100,
    max_window_ms=250,
)
check(
    len(max_split) == 2
    and all(
        window.end_ms - window.start_ms <= 250
        for window in max_split
    ),
    "MAX_WINDOW_VETOES_OVERSIZE_MERGE",
)


deterministic_first = plan_targeted_asr_windows(
    cues((100, 200), (250, 350), (1000, 1100)),
    alignment(),
    padding_before_ms=10,
    padding_after_ms=20,
    merge_gap_ms=60,
    max_window_ms=500,
)
deterministic_second = plan_targeted_asr_windows(
    cues((100, 200), (250, 350), (1000, 1100)),
    alignment(),
    padding_before_ms=10,
    padding_after_ms=20,
    merge_gap_ms=60,
    max_window_ms=500,
)
check(deterministic_first == deterministic_second, "DETERMINISTIC_REPEAT")


expect_error(
    lambda: plan_targeted_asr_windows(
        [(100, 200)],
        alignment(),
        padding_before_ms=0,
        padding_after_ms=0,
        merge_gap_ms=0,
        max_window_ms=500,
    ),
    "MALFORMED_INPUT_TUPLE_REQUIRED",
)
expect_error(
    lambda: plan_targeted_asr_windows(
        cues((200, 300), (100, 150)),
        alignment(),
        padding_before_ms=0,
        padding_after_ms=0,
        merge_gap_ms=0,
        max_window_ms=500,
    ),
    "DECREASING_SOURCE_START_FAILS",
)
expect_error(
    lambda: plan_targeted_asr_windows(
        cues((100, 200)),
        alignment(),
        padding_before_ms=0,
        padding_after_ms=0,
        merge_gap_ms=0,
        max_window_ms=0,
    ),
    "INVALID_MAX_BOUND_FAILS",
)
expect_error(
    lambda: plan_targeted_asr_windows(
        cues((100, 300)),
        alignment(),
        padding_before_ms=0,
        padding_after_ms=0,
        merge_gap_ms=0,
        max_window_ms=100,
    ),
    "SINGLE_CUE_OVER_MAX_FAILS",
)


source = open(
    "teddy_discovery_targeted_asr_window.py",
    encoding="utf-8",
).read()
check("JUR-750" not in source, "NO_TITLE_SPECIFIC_ID")
check("ASR" in source and "project_affine_timestamp_ms" in source, "NO_ASR_CALL")
check("teddy_discovery_subtitle_v2_pipeline" not in source, "PIPELINE_UNCHANGED_BOUNDARY")

print("SMOKE_PASS_COUNT=" + str(passes))
print("SMOKE_FAIL_COUNT=" + str(fails))
