"""Offline V1 policy regression for targeted second-evidence geometry.

This smoke only parses frozen local artifacts and uses the existing planning
and source-quality contracts.  It never reads media, calls VM122, invokes
Whisper/Hermes, or writes an artifact.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from teddy_discovery_alignment import (
    AffineAnchorResidual,
    RobustAffineAlignment,
)
from teddy_discovery_asr_artifact import parse_asr_result_bytes
from teddy_discovery_asr_source_quality import (
    ASR_SOURCE_REQUIRE_SECOND_EVIDENCE,
    classify_asr_result_source_quality,
)
from teddy_discovery_hybrid_evidence import HybridCueIdentity
from teddy_discovery_subtitle_text import parse_subtitle_bytes
from teddy_discovery_targeted_asr_artifact import (
    parse_targeted_asr_artifact_bytes,
)
from teddy_discovery_targeted_asr_window import (
    STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1,
    plan_targeted_asr_windows_with_policy,
)
from teddy_discovery_targeted_second_evidence import (
    build_targeted_second_evidence_plan_with_policy,
)


JUR_TARGETED_ARTIFACT = Path(
    "/var/tmp/JUR-750.r6d-targeted-asr-v1.json"
)
JUR_EXTERNAL_SRT = Path("/var/tmp/JUR-750.subtitlecat.ja.srt")
ADN_ASR_ARTIFACT = Path("/var/tmp/ADN-785.large-v3.stage11-asr-v1.json")
JUR_TARGETED_SHA256 = (
    "d872145778c1c108b87031bfde2357c05d224be8b907a572fdc8777390a928c0"
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


def jur_alignment() -> RobustAffineAlignment:
    """Use the frozen JUR affine transform only for this artifact replay."""

    scale = 1.0173232835064605
    intercept_ms = -181.3896630352166
    midpoint_x2_values = (200_000, 2_000_000, 6_000_000)
    residuals = []
    for index, external_midpoint_x2 in enumerate(midpoint_x2_values):
        external_midpoint_ms = external_midpoint_x2 / 2
        predicted = scale * external_midpoint_ms + intercept_ms
        asr_midpoint_x2 = round(predicted * 2)
        asr_midpoint_ms = asr_midpoint_x2 / 2
        signed = asr_midpoint_ms - predicted
        residuals.append(
            AffineAnchorResidual(
                external_identity=HybridCueIdentity.for_external_ja(index),
                asr_identity=HybridCueIdentity.for_asr_segment(index),
                external_midpoint_x2=external_midpoint_x2,
                asr_midpoint_x2=asr_midpoint_x2,
                predicted_asr_midpoint_ms=predicted,
                signed_residual_ms=signed,
                absolute_residual_ms=abs(signed),
                is_inlier=abs(signed) <= 1_000,
            )
        )
    absolute = sorted(item.absolute_residual_ms for item in residuals)
    return RobustAffineAlignment(
        scale=scale,
        intercept_ms=intercept_ms,
        anchor_count=len(residuals),
        inlier_count=sum(item.is_inlier for item in residuals),
        residual_threshold_ms=1_000,
        residuals=tuple(residuals),
        median_absolute_residual_ms=absolute[len(absolute) // 2],
    )


def main():
    policy = STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1
    check(
        (
            policy.pre_padding_ms,
            policy.post_padding_ms,
            policy.merge_gap_ms,
            policy.max_window_ms,
            policy.version,
        )
        == (5_000, 5_000, 10_000, 60_000, "v1"),
        "V1_POLICY_EXACT_VALUES",
    )

    jur_raw = JUR_TARGETED_ARTIFACT.read_bytes()
    check(
        hashlib.sha256(jur_raw).hexdigest() == JUR_TARGETED_SHA256,
        "JUR_ARTIFACT_SHA_UNCHANGED",
    )
    jur_artifact = parse_targeted_asr_artifact_bytes(jur_raw)
    external = parse_subtitle_bytes(
        JUR_EXTERNAL_SRT.read_bytes(),
        "srt",
    )
    jur_windows = plan_targeted_asr_windows_with_policy(
        external.cues,
        jur_alignment(),
        policy=policy,
    )
    expected_jur = tuple(
        (
            window.window_start_ms,
            window.window_end_ms,
            window.external_cue_ids,
        )
        for window in jur_artifact.windows
    )
    actual_jur = tuple(
        (window.start_ms, window.end_ms, window.external_cue_ids)
        for window in jur_windows
    )
    check(
        len(jur_windows) == 118 and actual_jur == expected_jur,
        "JUR_118_WINDOW_EXACT_REPLAY",
    )
    jur_durations = tuple(
        window.end_ms - window.start_ms for window in jur_windows
    )
    check(
        max(jur_durations) == 59_942,
        "JUR_MAX_WINDOW_59942_MS",
    )

    adn = parse_asr_result_bytes(ADN_ASR_ARTIFACT.read_bytes())
    decisions = classify_asr_result_source_quality(adn)
    require = tuple(
        decision
        for decision in decisions
        if decision.action == ASR_SOURCE_REQUIRE_SECOND_EVIDENCE
    )
    expected_require = (
        ("asr-000262", 261, 1_352_152, 1_355_572),
        ("asr-000473", 472, 2_767_472, 2_776_892),
        ("asr-000503", 502, 2_909_852, 2_914_472),
        ("asr-000511", 510, 3_057_628, 3_061_628),
    )
    check(
        tuple(
            (
                decision.source_index,
                decision.start_ms,
                decision.end_ms,
            )
            for decision in require
        )
        == tuple(item[1:] for item in expected_require),
        "ADN_REQUIRE_SOURCE_TIMINGS",
    )

    adn_plan = build_targeted_second_evidence_plan_with_policy(
        adn,
        decisions,
        policy=policy,
    )
    actual_adn = []
    for expected_id, source_index, start_ms, end_ms in expected_require:
        source = next(
            source
            for source in adn_plan.sources
            if source.cue_id == expected_id
        )
        window = next(
            window
            for window in adn_plan.windows
            if expected_id in window.source_ids
        )
        actual_adn.append(
            (
                source.cue_id,
                source.source_index,
                source.start_ms,
                source.end_ms,
                window.window_id,
                window.start_ms,
                window.end_ms,
                window.end_ms - window.start_ms,
            )
        )
    expected_adn = (
        ("asr-000262", 261, 1_352_152, 1_355_572,
         "targeted-window-000001", 1_347_152, 1_360_572, 13_420),
        ("asr-000473", 472, 2_767_472, 2_776_892,
         "targeted-window-000002", 2_762_472, 2_781_892, 19_420),
        ("asr-000503", 502, 2_909_852, 2_914_472,
         "targeted-window-000003", 2_904_852, 2_919_472, 14_620),
        ("asr-000511", 510, 3_057_628, 3_061_628,
         "targeted-window-000004", 3_052_628, 3_066_628, 14_000),
    )
    check(tuple(actual_adn) == expected_adn, "ADN_V1_WINDOW_PLAN_EXACT")
    check(
        len(adn_plan.sources) == 4
        and len(adn_plan.windows) == 4
        and len(adn_plan.sources) - len(adn_plan.windows) == 0
        and sum(
            window.end_ms - window.start_ms
            for window in adn_plan.windows
        )
        == 61_460
        and max(
            window.end_ms - window.start_ms
            for window in adn_plan.windows
        )
        == 19_420,
        "ADN_V1_PLAN_SUMMARY",
    )

    print("JUR_WINDOWS=" + str(len(jur_windows)))
    print("JUR_MAX_WINDOW_MS=" + str(max(jur_durations)))
    print("ADN_SOURCE_CUES=" + str(len(adn_plan.sources)))
    print("ADN_DISTINCT_WINDOWS=" + str(len(adn_plan.windows)))
    print("ADN_MERGE_COUNT=" + str(len(adn_plan.sources) - len(adn_plan.windows)))
    print(
        "ADN_TOTAL_PADDED_AUDIO_SECONDS="
        + f"{sum(window.end_ms - window.start_ms for window in adn_plan.windows) / 1000:.3f}"
    )
    print(
        "ADN_MAX_WINDOW_MS="
        + str(max(window.end_ms - window.start_ms for window in adn_plan.windows))
    )
    print("SMOKE_PASS_COUNT=" + str(passes))
    print("SMOKE_FAIL_COUNT=" + str(fails))


if __name__ == "__main__":
    main()
