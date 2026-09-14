"""Offline smoke for the isolated Stage12 128-cue benchmark policy.

This smoke uses synthetic semantic packages and a temporary benchmark root.
It does not invoke Hermes, STT, SubtitleCat, NAS, Jellyfin, or the Stage12
rollout state store.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from teddy_discovery_hermes_v2 import HermesV2CueInput
from teddy_discovery_stateful_parts import STATEFUL_PART_BATCH_SIZE
from teddy_discovery_stateful_translator import (
    StatefulSubtitlePackage,
    serialize_stateful_package,
)
from teddy_discovery_stage12_performance_benchmark import (
    BENCHMARK_CUE128_MAX_CUES_PER_PART,
    BENCHMARK_CUE128_POLICY_ID,
    BENCHMARK_CUE64_MAX_CUES_PER_PART,
    BENCHMARK_CUE64_POLICY_ID,
    BENCHMARK_REMOTE_ROOT,
    BenchmarkResumeMismatchError,
    assert_benchmark_resume_compatible,
    benchmark_remote_task_path,
    build_benchmark_manifest,
    create_benchmark_layout,
    install_benchmark_input,
    parse_benchmark_manifest,
    validate_isolated_root,
    write_benchmark_manifest,
)


passes = 0


def check(condition: bool, marker: str):
    global passes
    if not condition:
        raise AssertionError(marker)
    passes += 1
    print("PASS=" + marker)


def expect_raises(exception_type, callback, marker: str):
    try:
        callback()
    except exception_type:
        check(True, marker)
        return
    raise AssertionError(marker)


def package_for(dvd_id: str, count: int) -> StatefulSubtitlePackage:
    return StatefulSubtitlePackage(
        schema_version=1,
        dvd_id=dvd_id,
        generation_key="synthetic-" + dvd_id,
        claim_token=1,
        cues=tuple(
            HermesV2CueInput(
                cue_id=f"{dvd_id.lower()}-{index:06d}",
                external_ja=None,
                stt_ja=f"日本語テスト{index}",
                en=None,
                before_context=(),
                after_context=(),
            )
            for index in range(1, count + 1)
        ),
    )


check(STATEFUL_PART_BATCH_SIZE == 16, "PRODUCTION_PART_BATCH_SIZE_REMAINS_16")
check(
    BENCHMARK_CUE64_POLICY_ID == "benchmark-stateful-cue64-v1",
    "CUE64_POLICY_REMAINS_FROZEN",
)
check(
    BENCHMARK_CUE64_MAX_CUES_PER_PART == 64,
    "CUE64_MAX_REMAINS_FROZEN",
)
check(
    BENCHMARK_CUE128_POLICY_ID == "benchmark-stateful-cue128-v1",
    "CUE128_POLICY_ID",
)
check(
    BENCHMARK_CUE128_MAX_CUES_PER_PART == 128,
    "CUE128_MAX_CUES",
)

cases = (
    ("AT-099", 1471, 12, 63),
    ("BLOR-289", 830, 7, 62),
    ("DROP-141", 173, 2, 45),
)
manifests = {}

for dvd_id, cue_count, expected_parts, expected_last_count in cases:
    package = package_for(dvd_id, cue_count)
    semantic_input = serialize_stateful_package(package)
    manifest64 = build_benchmark_manifest(package, semantic_input)
    manifest128 = build_benchmark_manifest(
        package,
        semantic_input,
        policy_id=BENCHMARK_CUE128_POLICY_ID,
    )
    manifests[dvd_id] = (package, semantic_input, manifest64, manifest128)
    check(manifest64.policy_id == BENCHMARK_CUE64_POLICY_ID, dvd_id + "_64_POLICY")
    check(manifest64.part_count == (23 if cue_count == 1471 else 13 if cue_count == 830 else 3), dvd_id + "_64_PARTS")
    check(manifest128.policy_id == BENCHMARK_CUE128_POLICY_ID, dvd_id + "_128_POLICY")
    check(manifest128.semantic_cue_count == cue_count, dvd_id + "_128_CUE_COUNT")
    check(manifest128.part_count == expected_parts, dvd_id + "_128_PART_COUNT")
    check(
        max(part.cue_count for part in manifest128.parts) <= 128,
        dvd_id + "_128_PART_LIMIT",
    )
    check(
        manifest128.parts[-1].cue_count == expected_last_count,
        dvd_id + "_128_LAST_PART_COUNT",
    )
    check(
        manifest128.cue_ids == tuple(cue.cue_id for cue in package.cues),
        dvd_id + "_128_CUE_ORDER_EXACT",
    )
    check(
        build_benchmark_manifest(
            package,
            semantic_input,
            policy_id=BENCHMARK_CUE128_POLICY_ID,
        ).to_bytes()
        == manifest128.to_bytes(),
        dvd_id + "_128_DETERMINISTIC",
    )
    check(
        parse_benchmark_manifest(manifest128.to_bytes()) == manifest128,
        dvd_id + "_128_MANIFEST_ROUNDTRIP",
    )
    check(
        manifest64.benchmark_session_id != manifest128.benchmark_session_id,
        dvd_id + "_64_128_SESSION_ISOLATED",
    )
    remote64 = benchmark_remote_task_path(manifest64)
    remote128 = benchmark_remote_task_path(manifest128)
    check(remote128.startswith(BENCHMARK_REMOTE_ROOT + "/"), dvd_id + "_128_REMOTE_ROOT")
    check(
        "/benchmark-stateful-cue128-v1/" in remote128
        and remote128 != remote64,
        dvd_id + "_64_128_REMOTE_PATH_ISOLATED",
    )
    expect_raises(
        BenchmarkResumeMismatchError,
        lambda: assert_benchmark_resume_compatible(manifest64, manifest128),
        dvd_id + "_64_128_RESUME_REUSE_REJECTED",
    )

check(
    sum(manifest128.part_count for _, _, _, manifest128 in manifests.values()) == 21,
    "TOTAL_128_PARTS_21",
)

with TemporaryDirectory() as temporary:
    root = Path(temporary) / "stage12-performance-benchmark"
    check(validate_isolated_root(root) == root.resolve(), "CUE128_ROOT_ISOLATED")
    package, semantic_input, manifest64, manifest128 = manifests["AT-099"]
    layout64 = create_benchmark_layout(
        root,
        dvd_id=manifest64.dvd_id,
        policy_id=manifest64.policy_id,
    )
    layout128 = create_benchmark_layout(
        root,
        dvd_id=manifest128.dvd_id,
        policy_id=manifest128.policy_id,
    )
    check(layout64.title_root != layout128.title_root, "CUE64_CUE128_LOCAL_ROOT_ISOLATED")
    install_benchmark_input(layout64, package, semantic_input)
    install_benchmark_input(layout128, package, semantic_input)
    write_benchmark_manifest(layout64, manifest64)
    write_benchmark_manifest(layout128, manifest128)
    check(layout64.input_path != layout128.input_path, "CUE64_CUE128_INPUT_PATH_ISOLATED")
    check(layout128.manifest_path.is_file(), "CUE128_MANIFEST_STAGED")
    check(parse_benchmark_manifest(layout128.manifest_path.read_bytes()) == manifest128, "CUE128_MANIFEST_EXACT")

print("CP7C_128_SMOKE_PASS")
print("SMOKE_PASS_COUNT=" + str(passes))
print("SMOKE_FAIL_COUNT=0")
