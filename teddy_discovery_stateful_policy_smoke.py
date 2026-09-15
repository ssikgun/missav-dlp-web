"""Offline smoke for the explicit production 16/64/128 semantic policies."""

from pathlib import Path
import json
import tempfile

from teddy_discovery_hermes_v2 import HermesV2CueInput, HermesV2CueOutput
from teddy_discovery_stateful_controller import (
    REQUEST_PART,
    build_stateful_part_query,
    decide_stateful_controller_step,
)
from teddy_discovery_stateful_live_runner import build_parser
from teddy_discovery_stateful_parts import (
    StatefulPartsValidationError,
    StatefulSemanticPart,
    build_stateful_part_plan,
    parse_stateful_part,
    serialize_stateful_part,
)
from teddy_discovery_stateful_policy import (
    DEFAULT_STATEFUL_SEMANTIC_POLICY,
    STATEFUL_SEMANTIC_POLICY_64,
    STATEFUL_SEMANTIC_POLICY_128,
    STATEFUL_SEMANTIC_POLICY_ID_16,
    STATEFUL_SEMANTIC_POLICY_ID_64,
    STATEFUL_SEMANTIC_POLICY_ID_128,
    StatefulSemanticPolicy,
    StatefulSemanticPolicyError,
    bind_stateful_policy_generation_key,
    resolve_stateful_semantic_policy,
)
from teddy_discovery_stateful_translator import (
    StatefulSubtitlePackage,
    StatefulSubtitleResult,
    _atomic_private_write,
    bind_stateful_semantic_policy,
    create_stateful_staging_directory,
    parse_stateful_package,
    serialize_stateful_package,
    serialize_stateful_result,
    stateful_session_id_for_package,
)
from teddy_discovery_stage11_live_adapters import (
    Stage11LiveAdapterError,
    build_first_pass_adapter,
)


def make_package(count: int, *, dvd_id: str) -> StatefulSubtitlePackage:
    return StatefulSubtitlePackage(
        schema_version=1,
        dvd_id=dvd_id,
        generation_key="stage11-policy-smoke-generation-001",
        claim_token=17,
        cues=tuple(
            HermesV2CueInput(
                cue_id=f"cue-{index:04d}",
                external_ja=f"日本語-{index:04d}",
                stt_ja=None,
                en=None,
                before_context=(),
                after_context=(),
            )
            for index in range(1, count + 1)
        ),
    )


def make_part(plan, part_index: int) -> StatefulSemanticPart:
    expected = plan.parts[part_index - 1]
    return StatefulSemanticPart(
        part_schema_version=1,
        session_id=plan.session_id,
        input_sha256=plan.input_sha256,
        part_index=expected.part_index,
        first_cue_id=expected.first_cue_id,
        last_cue_id=expected.last_cue_id,
        cues=tuple(
            HermesV2CueOutput(
                cue_id=cue_id,
                repaired_ja=None,
                ko="합성",
            )
            for cue_id in expected.cue_ids
        ),
        max_cues_per_part=plan.max_cues_per_part,
    )


def expect(exception_type, callback, marker: str) -> None:
    try:
        callback()
    except exception_type:
        return
    raise AssertionError(marker)


def parser_args(*extra: str) -> list[str]:
    return [
        "--package", "/tmp/input.json",
        "--task-directory", "/tmp/task",
        "--final-result", "/tmp/result.json",
        "--remote", "offline",
        "--remote-task", "/tmp/remote-task",
        "--ssh-key", "/tmp/key",
        "--known-hosts", "/tmp/known-hosts",
        *extra,
    ]


def main() -> None:
    counts = {"pass": 0, "fail": 0}

    def check(condition: bool, marker: str) -> None:
        if not condition:
            counts["fail"] += 1
            raise AssertionError(marker)
        counts["pass"] += 1

    legacy_package = make_package(173, dvd_id="POLICY-SMOKE")
    legacy_bytes = serialize_stateful_package(legacy_package)
    legacy_plan = build_stateful_part_plan(
        legacy_package,
        legacy_bytes,
    )

    candidate_package = bind_stateful_semantic_policy(
        legacy_package,
        STATEFUL_SEMANTIC_POLICY_128,
    )
    candidate_bytes = serialize_stateful_package(candidate_package)
    candidate_plan = build_stateful_part_plan(
        candidate_package,
        candidate_bytes,
        semantic_policy=STATEFUL_SEMANTIC_POLICY_128,
    )

    fixed64_package = bind_stateful_semantic_policy(
        legacy_package,
        STATEFUL_SEMANTIC_POLICY_64,
    )
    fixed64_bytes = serialize_stateful_package(fixed64_package)
    fixed64_plan = build_stateful_part_plan(
        fixed64_package,
        fixed64_bytes,
        semantic_policy=STATEFUL_SEMANTIC_POLICY_64,
    )

    check(
        legacy_plan.policy_id == STATEFUL_SEMANTIC_POLICY_ID_16
        and legacy_plan.max_cues_per_part == 16
        and legacy_plan.part_count == 11
        and all(part.cue_count <= 16 for part in legacy_plan.parts),
        "LEGACY_DEFAULT_16_PRESERVED",
    )
    check(
        candidate_plan.policy_id == STATEFUL_SEMANTIC_POLICY_ID_128
        and candidate_plan.max_cues_per_part == 128
        and candidate_plan.part_count == 2
        and candidate_plan.parts[0].cue_count == 128
        and candidate_plan.parts[1].cue_count == 45,
        "CANDIDATE_173_CUES_2_PARTS",
    )
    check(
        fixed64_plan.policy_id == STATEFUL_SEMANTIC_POLICY_ID_64
        and fixed64_plan.max_cues_per_part == 64
        and fixed64_plan.part_count == 3
        and fixed64_plan.parts[0].cue_count == 64
        and fixed64_plan.parts[1].cue_count == 64
        and fixed64_plan.parts[2].cue_count == 45,
        "CANDIDATE_173_CUES_3_FIXED64_PARTS",
    )
    expected_candidate_parts = {1471: 12, 830: 7, 173: 2}
    for cue_count, expected_part_count in expected_candidate_parts.items():
        title_package = make_package(
            cue_count,
            dvd_id="POLICY-SMOKE-" + str(cue_count),
        )
        title_package = bind_stateful_semantic_policy(
            title_package,
            STATEFUL_SEMANTIC_POLICY_128,
        )
        title_bytes = serialize_stateful_package(title_package)
        title_plan = build_stateful_part_plan(
            title_package,
            title_bytes,
            semantic_policy=STATEFUL_SEMANTIC_POLICY_128,
        )
        check(
            title_plan.part_count == expected_part_count
            and tuple(
                cue_id
                for expected in title_plan.parts
                for cue_id in expected.cue_ids
            ) == tuple(cue.cue_id for cue in title_package.cues),
            "CANDIDATE_" + str(cue_count) + "_CUES_" + str(expected_part_count) + "_PARTS",
        )
    check(
        parse_stateful_package(candidate_bytes) == candidate_package
        and set(json.loads(candidate_bytes))
        == {"schema_version", "dvd_id", "generation_key", "claim_token", "cues"},
        "PACKAGE_WIRE_ENVELOPE_UNCHANGED",
    )

    candidate_ids = tuple(
        cue_id
        for expected in candidate_plan.parts
        for cue_id in expected.cue_ids
    )
    check(
        candidate_ids == tuple(cue.cue_id for cue in candidate_package.cues),
        "CANDIDATE_CUE_COMPLETENESS_AND_ORDER",
    )
    candidate_part = make_part(candidate_plan, 1)
    candidate_part_wire = json.loads(
        serialize_stateful_part(candidate_part).decode("utf-8")
    )
    check(
        parse_stateful_part(
            serialize_stateful_part(candidate_part),
            candidate_plan.parts[0],
            candidate_plan,
        ) == candidate_part
        and len(candidate_part.cues) == 128
        and set(candidate_part_wire)
        == {
            "part_schema_version",
            "session_id",
            "input_sha256",
            "part_index",
            "first_cue_id",
            "last_cue_id",
            "cues",
        },
        "CANDIDATE_128_CUE_PART_VALIDATES_WITH_FROZEN_CONTRACT",
    )

    legacy_session = stateful_session_id_for_package(legacy_package)
    candidate_session = stateful_session_id_for_package(candidate_package)
    check(
        candidate_package.generation_key != legacy_package.generation_key
        and candidate_session != legacy_session
        and candidate_plan.input_sha256 != legacy_plan.input_sha256,
        "SESSION_AND_INPUT_IDENTITY_ISOLATED",
    )
    check(
        (legacy_session, legacy_plan.input_sha256, 1)
        != (candidate_session, candidate_plan.input_sha256, 1)
        and candidate_session in build_stateful_part_query(
            candidate_package,
            candidate_bytes,
            1,
            semantic_policy=STATEFUL_SEMANTIC_POLICY_128,
        )
        and candidate_plan.input_sha256 in build_stateful_part_query(
            candidate_package,
            candidate_bytes,
            1,
            semantic_policy=STATEFUL_SEMANTIC_POLICY_128,
        ),
        "RESUME_KEY_AND_QUERY_IDENTITY_ISOLATED",
    )

    parser = build_parser()
    legacy_args = parser.parse_args(parser_args())
    candidate_args = parser.parse_args(
        parser_args("--semantic-policy", STATEFUL_SEMANTIC_POLICY_ID_128)
    )
    fixed64_args = parser.parse_args(
        parser_args("--semantic-policy", STATEFUL_SEMANTIC_POLICY_ID_64)
    )
    check(
        legacy_args.semantic_policy == STATEFUL_SEMANTIC_POLICY_ID_16
        and candidate_args.semantic_policy == STATEFUL_SEMANTIC_POLICY_ID_128
        and fixed64_args.semantic_policy == STATEFUL_SEMANTIC_POLICY_ID_64
        and legacy_args.turn_timeout == 600
        and candidate_args.turn_timeout == 600,
        "POLICY_CONFIG_DEFAULT_AND_TIMEOUT_600",
    )

    expect(
        StatefulSemanticPolicyError,
        lambda: resolve_stateful_semantic_policy("stage11-stateful-missing-v1"),
        "MISSING_POLICY_FAILS_CLOSED",
    )
    expect(
        StatefulSemanticPolicyError,
        lambda: StatefulSemanticPolicy(
            policy_id=STATEFUL_SEMANTIC_POLICY_ID_128,
            max_cues_per_part=16,
        ),
        "MALFORMED_POLICY_BATCH_FAILS_CLOSED",
    )
    expect(
        StatefulSemanticPolicyError,
        lambda: bind_stateful_policy_generation_key(
            candidate_package.generation_key,
            DEFAULT_STATEFUL_SEMANTIC_POLICY,
        ),
        "CROSS_POLICY_BINDING_FAILS_CLOSED",
    )
    expect(
        StatefulPartsValidationError,
        lambda: build_stateful_part_plan(
            legacy_package,
            legacy_bytes,
            semantic_policy=STATEFUL_SEMANTIC_POLICY_128,
        ),
        "UNBOUND_128_PACKAGE_FAILS_CLOSED",
    )
    expect(
        StatefulPartsValidationError,
        lambda: build_stateful_part_plan(
            candidate_package,
            candidate_bytes,
            semantic_policy=DEFAULT_STATEFUL_SEMANTIC_POLICY,
        ),
        "128_PACKAGE_CANNOT_RESUME_AS_16",
    )

    with tempfile.TemporaryDirectory(prefix="stage11-policy-smoke-") as raw:
        root = Path(raw)
        task = root / "candidate-task"
        task.mkdir(mode=0o700)
        decision = decide_stateful_controller_step(
            task,
            candidate_package,
            candidate_bytes,
            semantic_policy=STATEFUL_SEMANTIC_POLICY_128,
        )
        check(
            decision.action == REQUEST_PART
            and decision.part_count == 2
            and decision.part_index == 1
            and decision.cue_count == 128,
            "CANDIDATE_CONTROLLER_128_PART_PLAN",
        )

        legacy_root = root / "legacy-local"
        candidate_root = root / "candidate-local"
        legacy_root.mkdir(mode=0o700)
        candidate_root.mkdir(mode=0o700)
        observed: list[dict[str, object]] = []

        def prepare_remote(package, paths, *, route):
            session = stateful_session_id_for_package(package)
            observed.append(
                {
                    "session": session,
                    "local": str(paths.task_directory),
                    "remote": "/offline/stage11/" + session,
                    "route": route,
                }
            )
            return "/offline/stage11/" + session

        def native_run(args):
            package = parse_stateful_package(Path(args.package).read_bytes())
            result = StatefulSubtitleResult(
                schema_version=1,
                dvd_id=package.dvd_id,
                generation_key=package.generation_key,
                claim_token=package.claim_token,
                session_id=stateful_session_id_for_package(package),
                cues=tuple(
                    HermesV2CueOutput(
                        cue_id=cue.cue_id,
                        repaired_ja=None,
                        ko="합성",
                    )
                    for cue in package.cues
                ),
            )
            _atomic_private_write(
                Path(args.final_result),
                serialize_stateful_result(result),
            )
            observed[-1]["policy"] = args.semantic_policy
            observed[-1]["parser_timeout"] = args.turn_timeout
            return 0

        adapter = build_first_pass_adapter(
            remote="offline",
            ssh_key="/offline/key",
            known_hosts="/offline/known-hosts",
            prepare_remote=prepare_remote,
            native_run=native_run,
        )
        legacy_result = adapter(
            legacy_package,
            route="ASR_ONLY",
            staging_root=legacy_root,
        )
        candidate_result = adapter(
            candidate_package,
            route="ASR_ONLY",
            staging_root=candidate_root,
            semantic_policy=STATEFUL_SEMANTIC_POLICY_128,
        )
        check(
            legacy_result.session_id == legacy_session
            and candidate_result.session_id == candidate_session
            and observed[0]["session"] != observed[1]["session"]
            and observed[0]["local"] != observed[1]["local"]
            and observed[0]["remote"] != observed[1]["remote"]
            and observed[0]["policy"] == STATEFUL_SEMANTIC_POLICY_ID_16
            and observed[1]["policy"] == STATEFUL_SEMANTIC_POLICY_ID_128
            and observed[0]["parser_timeout"] == 600
            and observed[1]["parser_timeout"] == 600,
            "LOCAL_REMOTE_TASK_PATH_AND_SESSION_ISOLATION",
        )
        expect(
            Stage11LiveAdapterError,
            lambda: adapter(
                legacy_package,
                route="ASR_ONLY",
                staging_root=root / "unbound-candidate",
                semantic_policy=STATEFUL_SEMANTIC_POLICY_128,
            ),
            "ADAPTER_REJECTS_UNBOUND_CANDIDATE_PACKAGE",
        )

    print("STATEFUL_POLICY_SMOKE_PASS")
    print("EXPECTED_PARTS_1471_830_173=12/7/2")
    print("LIVE_HERMES_CALLS=0")
    print("PRODUCTION_WRITES=0")
    print("SMOKE_PASS_COUNT=" + str(counts["pass"]))
    print("SMOKE_FAIL_COUNT=" + str(counts["fail"]))


if __name__ == "__main__":
    main()
