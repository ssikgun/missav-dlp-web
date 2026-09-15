"""Offline smoke for the isolated Stage12 64-cue benchmark harness.

This smoke uses only synthetic semantic packages and a temporary benchmark
root.  It does not invoke Hermes, STT, SubtitleCat, NAS, Jellyfin, or the
Stage12 rollout state store.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from teddy_discovery_hermes_v2 import HermesV2CueInput
from teddy_discovery_stateful_parts import STATEFUL_PART_BATCH_SIZE
from teddy_discovery_stateful_policy import DEFAULT_STATEFUL_SEMANTIC_POLICY
from teddy_discovery_stateful_translator import (
    StatefulSubtitlePackage,
    stateful_session_id_for_package,
    serialize_stateful_package,
)
from teddy_discovery_stage12_performance_benchmark import (
    BENCHMARK_MAX_CUES_PER_PART,
    BENCHMARK_POLICY_ID,
    BENCHMARK_REMOTE_ROOT,
    TOKEN_USAGE_AVAILABLE,
    TOKEN_USAGE_UNAVAILABLE,
    BenchmarkResumeMismatchError,
    BenchmarkTelemetryRecorder,
    assert_benchmark_resume_compatible,
    benchmark_remote_task_path,
    build_benchmark_manifest,
    create_benchmark_layout,
    evaluate_cue_identity,
    install_benchmark_input,
    parse_benchmark_manifest,
    read_benchmark_manifest,
    serialize_benchmark_report,
    validate_isolated_root,
    write_benchmark_manifest,
    write_benchmark_report,
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


def package_for(count: int, *, generation_key: str) -> StatefulSubtitlePackage:
    return StatefulSubtitlePackage(
        schema_version=1,
        dvd_id="BENCHMARK-SYNTHETIC",
        generation_key=generation_key,
        claim_token=1,
        cues=tuple(
            HermesV2CueInput(
                cue_id=f"asr-{index:06d}",
                external_ja=None,
                stt_ja=f"日本語テスト{index}",
                en=None,
                before_context=(),
                after_context=(),
            )
            for index in range(1, count + 1)
        ),
    )


check(
    STATEFUL_PART_BATCH_SIZE == 64
    and DEFAULT_STATEFUL_SEMANTIC_POLICY.max_cues_per_part == 64,
    "PRODUCTION_DEFAULT_PART_BATCH_SIZE_IS_64",
)
check(
    BENCHMARK_MAX_CUES_PER_PART == 64,
    "BENCHMARK_PART_BATCH_SIZE_IS_64",
)
check(
    BENCHMARK_POLICY_ID != DEFAULT_STATEFUL_SEMANTIC_POLICY.policy_id,
    "BENCHMARK_FIXED64_ID_REMAINS_DISTINCT_FROM_PRODUCTION",
)

at_package = package_for(1471, generation_key="synthetic-at-099")
at_input = serialize_stateful_package(at_package)
at_manifest = build_benchmark_manifest(at_package, at_input)

check(at_manifest.policy_id == BENCHMARK_POLICY_ID, "AT_POLICY_ID")
check(at_manifest.semantic_cue_count == 1471, "AT_SEMANTIC_CUE_COUNT")
check(at_manifest.part_count == 23, "AT_1471_CUES_23_PARTS")
check(
    max(part.cue_count for part in at_manifest.parts) <= 64,
    "AT_NO_PART_EXCEEDS_64",
)
check(at_manifest.parts[-1].cue_count == 63, "AT_LAST_PART_COUNT")
check(
    at_manifest.cue_ids == tuple(cue.cue_id for cue in at_package.cues),
    "AT_CUE_ORDER_EXACT",
)
check(
    len(set(at_manifest.cue_ids)) == 1471,
    "AT_DUPLICATE_CUE_COUNT_ZERO",
)

drop_package = package_for(173, generation_key="synthetic-drop-141")
drop_input = serialize_stateful_package(drop_package)
drop_manifest = build_benchmark_manifest(drop_package, drop_input)

check(drop_manifest.semantic_cue_count == 173, "DROP_SEMANTIC_CUE_COUNT")
check(drop_manifest.part_count == 3, "DROP_173_CUES_3_PARTS")
check(
    tuple(part.cue_count for part in drop_manifest.parts) == (64, 64, 45),
    "DROP_PART_COUNTS",
)
check(
    drop_manifest.cue_ids == tuple(cue.cue_id for cue in drop_package.cues),
    "DROP_CUE_ORDER_EXACT",
)
check(
    all(len(part.cue_ids) == len(set(part.cue_ids)) for part in drop_manifest.parts),
    "DROP_DUPLICATE_CUE_COUNT_ZERO",
)

same_manifest = build_benchmark_manifest(at_package, at_input)
check(
    same_manifest.to_bytes() == at_manifest.to_bytes(),
    "SAME_INPUT_POLICY_IDENTICAL_MANIFEST",
)
check(
    parse_benchmark_manifest(at_manifest.to_bytes()) == at_manifest,
    "MANIFEST_ROUNDTRIP",
)

changed_input_package = package_for(
    1471,
    generation_key="synthetic-at-099-input-changed",
)
changed_input = serialize_stateful_package(changed_input_package)
changed_input_manifest = build_benchmark_manifest(
    changed_input_package,
    changed_input,
)
check(
    changed_input_manifest.input_sha256 != at_manifest.input_sha256,
    "CHANGED_INPUT_SHA_DETECTED",
)
expect_raises(
    BenchmarkResumeMismatchError,
    lambda: assert_benchmark_resume_compatible(
        at_manifest,
        changed_input_manifest,
    ),
    "CHANGED_INPUT_SHA_FAILS_RESUME_CLOSED",
)

changed_policy_package = package_for(1471, generation_key="synthetic-at-099")
changed_policy_input = serialize_stateful_package(changed_policy_package)
changed_policy_manifest = build_benchmark_manifest(
    changed_policy_package,
    changed_policy_input,
    policy_id="benchmark-stateful-cue64-v2",
)
expect_raises(
    BenchmarkResumeMismatchError,
    lambda: assert_benchmark_resume_compatible(
        at_manifest,
        changed_policy_manifest,
    ),
    "CHANGED_POLICY_ID_FORBIDS_STATE_REUSE",
)

check(
    stateful_session_id_for_package(at_package) != at_manifest.benchmark_session_id,
    "BENCHMARK_SESSION_IS_NOT_PRODUCTION_SESSION",
)
remote_task = benchmark_remote_task_path(at_manifest)
check(remote_task.startswith(BENCHMARK_REMOTE_ROOT + "/"), "REMOTE_ROOT_IS_ISOLATED")
check(at_manifest.benchmark_session_id in remote_task, "REMOTE_SESSION_ID_IS_ISOLATED")

with TemporaryDirectory() as temporary:
    root = Path(temporary) / "stage12-performance-benchmark"
    layout = create_benchmark_layout(
        root,
        dvd_id=at_manifest.dvd_id,
        policy_id=at_manifest.policy_id,
    )
    check(validate_isolated_root(root) == root.resolve(), "ISOLATED_ROOT_VALID")
    install_benchmark_input(layout, at_package, at_input)
    install_benchmark_input(layout, at_package, at_input)
    write_benchmark_manifest(layout, at_manifest)
    write_benchmark_manifest(layout, at_manifest)
    check(layout.input_path.read_bytes() == at_input, "INPUT_BYTES_NOT_OVERWRITTEN")
    check(
        read_benchmark_manifest(layout) == at_manifest,
        "MANIFEST_READBACK_EXACT",
    )
    report_probe = {
        "dvd_id": at_manifest.dvd_id,
        "policy_id": at_manifest.policy_id,
        "semantic_cue_count": at_manifest.semantic_cue_count,
        "planned_parts": at_manifest.part_count,
        "hermes_invocations": 0,
        "retry_count": 0,
        "timeout_count": 0,
        "validation_failure_count": 0,
        "elapsed_seconds": 0.0,
        "cue_coverage_pass": False,
        "cue_order_pass": False,
        "token_usage": None,
    }
    write_benchmark_report(layout, report_probe)
    check(layout.report_path.is_file(), "REPORT_WRITES_ONLY_ISOLATED_ROOT")

    clock_values = iter((100.0, 100.5, 101.25, 102.25))
    telemetry = BenchmarkTelemetryRecorder(
        drop_manifest,
        monotonic=lambda: next(clock_values),
    )
    telemetry.start()
    telemetry.start_part(1)
    telemetry.record_invocation()
    telemetry.finish_part(1)
    telemetry.record_resume_recovery("REMOTE_PENDING_RECOVERY")
    telemetry.record_cue_identity(drop_manifest.cue_ids)
    telemetry.mark_token_usage_unavailable()
    telemetry.finish()
    report = telemetry.build_report()
    required_fields = {
        "dvd_id",
        "policy_id",
        "semantic_cue_count",
        "planned_parts",
        "hermes_invocations",
        "retry_count",
        "timeout_count",
        "validation_failure_count",
        "elapsed_seconds",
        "per_part_elapsed_seconds",
        "resume_recovery_events",
        "cue_coverage_pass",
        "cue_order_pass",
        "token_usage",
        "token_usage_status",
    }
    check(required_fields <= set(report), "TELEMETRY_FIELDS_COMPLETE")
    check(report["planned_parts"] == 3, "TELEMETRY_PART_COUNT")
    check(report["hermes_invocations"] == 1, "TELEMETRY_INVOCATION_COUNT")
    check(report["elapsed_seconds"] == 2.25, "TELEMETRY_MONOTONIC_TOTAL")
    check(
        report["per_part_elapsed_seconds"]
        == [{"part_index": 1, "elapsed_seconds": 0.75}],
        "TELEMETRY_MONOTONIC_PART_TIME",
    )
    check(report["cue_coverage_pass"] is True, "TELEMETRY_CUE_COVERAGE_PASS")
    check(report["cue_order_pass"] is True, "TELEMETRY_CUE_ORDER_PASS")
    check(report["token_usage"] is None, "TOKEN_USAGE_NULL_WHEN_UNAVAILABLE")
    check(
        report["token_usage_status"] == TOKEN_USAGE_UNAVAILABLE,
        "TOKEN_USAGE_UNAVAILABLE_EXPLICIT",
    )
    check(
        serialize_benchmark_report(report),
        "TELEMETRY_REPORT_SERIALIZABLE",
    )

    available_clock_values = iter((200.0, 201.0))
    available_telemetry = BenchmarkTelemetryRecorder(
        drop_manifest,
        monotonic=lambda: next(available_clock_values),
    )
    available_telemetry.start()
    available_telemetry.record_token_usage({"input_tokens": 12, "output_tokens": 7})
    available_telemetry.finish()
    available_report = available_telemetry.build_report()
    check(
        available_report["token_usage"]
        == {"input_tokens": 12, "output_tokens": 7},
        "TOKEN_USAGE_RAW_MAPPING_RECORDED",
    )
    check(
        available_report["token_usage_status"] == TOKEN_USAGE_AVAILABLE,
        "TOKEN_USAGE_AVAILABLE_EXPLICIT",
    )

    coverage, order = evaluate_cue_identity(
        ("a", "b", "c"),
        ("a", "b", "b"),
    )
    check(coverage is False and order is False, "DUPLICATE_CUE_FAIL_CLOSED")

source = Path("teddy_discovery_stage12_performance_benchmark.py").read_text(
    encoding="utf-8",
)
for title_marker in ("AT-099", "BLOR-289", "DROP-141"):
    check(title_marker not in source, "NO_TITLE_SPECIFIC_PRODUCTION_BRANCH_" + title_marker)
check("subprocess" not in source, "NO_LIVE_SUBPROCESS_IN_HARNESS")
check(TOKEN_USAGE_AVAILABLE == "AVAILABLE", "TOKEN_USAGE_AVAILABLE_CONTRACT")

print("SMOKE_PASS_COUNT=" + str(passes))
print("SMOKE_FAIL_COUNT=0")
