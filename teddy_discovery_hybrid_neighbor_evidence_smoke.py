from teddy_discovery_hybrid_neighbor_evidence import (
    ASRTimingEvidence,
    HybridNeighborError,
    project_external_interval,
    select_asr_neighbors,
)


passes = 0


def check(value, marker):
    global passes

    if not value:
        raise AssertionError(marker)

    passes += 1
    print("PASS=" + marker)


projected = project_external_interval(
    10000,
    11000,
    scale=1.0,
    intercept_ms=0.0,
)

check(
    projected.start_ms == 10000
    and projected.end_ms == 11000,
    "IDENTITY_PROJECTION",
)


segments = (
    ASRTimingEvidence(
        source_index=0,
        start_ms=7000,
        end_ms=8000,
    ),
    ASRTimingEvidence(
        source_index=1,
        start_ms=9500,
        end_ms=10200,
    ),
    ASRTimingEvidence(
        source_index=2,
        start_ms=10500,
        end_ms=11200,
    ),
    ASRTimingEvidence(
        source_index=3,
        start_ms=12000,
        end_ms=12500,
    ),
    ASRTimingEvidence(
        source_index=4,
        start_ms=30000,
        end_ms=31000,
    ),
)

selection = select_asr_neighbors(
    projected,
    segments,
    maximum_distance_ms=2000,
)

check(
    selection.overlapping_indices == (1, 2),
    "OVERLAPPING_SEGMENTS_SELECTED",
)

check(
    selection.before_indices == (0,),
    "NEAR_BEFORE_SELECTED_WITHOUT_OVERLAP_DUPLICATE",
)

check(
    selection.after_indices == (3,),
    "NEAR_AFTER_SELECTED",
)

check(
    4 not in selection.all_indices,
    "DISTANT_AFTER_REJECTED",
)


gap_projected = project_external_interval(
    15000,
    16000,
    scale=1.0,
    intercept_ms=0.0,
)

gap_selection = select_asr_neighbors(
    gap_projected,
    segments,
    maximum_distance_ms=3000,
)

check(
    gap_selection.before_indices == (3,),
    "GAP_NEAREST_BEFORE_SELECTED",
)

check(
    gap_selection.after_indices == (),
    "GAP_DISTANT_AFTER_REJECTED",
)


strict_gap = select_asr_neighbors(
    gap_projected,
    segments,
    maximum_distance_ms=1000,
)

check(
    strict_gap.all_indices == (),
    "STRICT_DISTANCE_CAN_RETURN_NO_STT",
)


affine = project_external_interval(
    10000,
    11000,
    scale=1.02,
    intercept_ms=-200.0,
)

check(
    affine.start_ms == 10000
    and affine.end_ms == 11020,
    "AFFINE_SCALE_AND_OFFSET",
)


try:
    select_asr_neighbors(
        projected,
        segments,
        maximum_distance_ms=2000,
        maximum_overlapping=1,
    )
except HybridNeighborError:
    print("PASS=OVERLAP_BOUND_FAILS_CLOSED")
    passes += 1
else:
    raise AssertionError(
        "OVERLAP_BOUND_DID_NOT_FAIL"
    )


source = open(
    "teddy_discovery_hybrid_neighbor_evidence.py",
    encoding="utf-8",
).read()

check(
    "JUR-750" not in source,
    "NO_TITLE_SPECIFIC_ID",
)

check(
    "661" not in source
    and "42" not in source,
    "NO_TITLE_SPECIFIC_COUNTS",
)

check(
    "maximum_distance_ms" in source,
    "DISTANCE_POLICY_IS_PARAMETERIZED",
)

print(
    "SMOKE_PASS_COUNT="
    + str(passes)
)

print("SMOKE_FAIL_COUNT=0")
