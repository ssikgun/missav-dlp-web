"""Synthetic smoke coverage for bounded invalid semantic-part recovery."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import teddy_discovery_stateful_live_runner as live_runner
from teddy_discovery_hermes_v2 import HermesV2CueInput, HermesV2CueOutput
from teddy_discovery_stateful_parts import (
    STATEFUL_PART_RUNAWAY_MAX_UNIT_CHARS,
    STATEFUL_PART_RUNAWAY_MIN_REPETITIONS,
    STATEFUL_PART_RUNAWAY_MIN_TEXT_CHARS,
    StatefulPartsValidationError,
    StatefulSemanticPart,
    build_stateful_part_plan,
    parse_stateful_part,
    serialize_stateful_part,
)
from teddy_discovery_stateful_translator import (
    StatefulSubtitlePackage,
    serialize_stateful_package,
)


def check(condition: bool, marker: str):
    if not condition:
        raise AssertionError(marker)
    print("PASS=" + marker)


def package_for(count: int) -> StatefulSubtitlePackage:
    return StatefulSubtitlePackage(
        schema_version=1,
        dvd_id="SYNTHETIC-RETRY",
        generation_key="synthetic-retry-generation-001",
        claim_token=1,
        cues=tuple(
            HermesV2CueInput(
                cue_id=f"asr-{index:06d}",
                external_ja=f"テスト-{index:06d}",
                stt_ja=None,
                en=None,
                before_context=(),
                after_context=(),
            )
            for index in range(1, count + 1)
        ),
    )


def valid_part(plan, part_index: int) -> StatefulSemanticPart:
    expected = plan.parts[part_index - 1]
    return StatefulSemanticPart(
        part_schema_version=1,
        session_id=plan.session_id,
        input_sha256=plan.input_sha256,
        part_index=part_index,
        first_cue_id=expected.first_cue_id,
        last_cue_id=expected.last_cue_id,
        cues=tuple(
            HermesV2CueOutput(
                cue_id=cue_id,
                repaired_ja=None,
                ko="valid-ko-" + cue_id,
            )
            for cue_id in expected.cue_ids
        ),
    )


def invalid_payload(part: StatefulSemanticPart) -> bytes:
    data = json.loads(serialize_stateful_part(part).decode("utf-8"))
    data["cues"][0]["ko"] = "반복" * 32
    return json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def write_private(path: Path, payload: bytes) -> None:
    path.write_bytes(payload)
    os.chmod(path, 0o600)


def args_for(package_path: Path, task_directory: Path, final_path: Path):
    return live_runner.build_parser().parse_args(
        [
            "--package",
            str(package_path),
            "--task-directory",
            str(task_directory),
            "--final-result",
            str(final_path),
            "--remote",
            "synthetic@offline",
            "--remote-task",
            "/synthetic/task",
            "--ssh-key",
            "/synthetic/key",
            "--known-hosts",
            "/synthetic/known-hosts",
        ]
    )


def run_synthetic(
    root: Path,
    *,
    cue_count: int,
    invalid_attempts: int,
    prepromote_first: bool,
):
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    package = package_for(cue_count)
    package_bytes = serialize_stateful_package(package)
    package_path = root / "stage11-semantic-input.json"
    package_path.write_bytes(package_bytes)
    task_directory = root / "task"
    task_directory.mkdir(mode=0o700)
    final_path = root / "stage11-semantic-result.json"
    plan = build_stateful_part_plan(package, package_bytes)

    if prepromote_first:
        first = valid_part(plan, 1)
        write_private(
            task_directory / plan.parts[0].canonical_filename,
            serialize_stateful_part(first),
        )
        first_bytes = (
            task_directory / plan.parts[0].canonical_filename
        ).read_bytes()
    else:
        first_bytes = None

    remote = {"pending": False, "payload": None}
    calls = {
        "model": [],
        "read": [],
        "remove": [],
    }
    expected = plan.parts[1 if prepromote_first else 0]
    valid_payload = serialize_stateful_part(
        valid_part(plan, expected.part_index)
    )
    invalid = invalid_payload(valid_part(plan, expected.part_index))

    def remote_sha(**_kwargs):
        return plan.input_sha256

    def remote_status(*, path, **_kwargs):
        calls["read"].append(("status", path))
        return remote["pending"]

    def invoke(*, query, **_kwargs):
        calls["model"].append(query)
        attempt = len(calls["model"])
        remote["pending"] = True
        remote["payload"] = invalid if attempt <= invalid_attempts else valid_payload

    def read_remote(*, path, **_kwargs):
        calls["read"].append(("payload", path))
        if not remote["pending"] or remote["payload"] is None:
            raise AssertionError("synthetic remote pending was not installed")
        return remote["payload"]

    def remove_remote(*, path, **_kwargs):
        calls["remove"].append(path)
        if not remote["pending"]:
            raise AssertionError("invalid pending cleanup was not present")
        remote["pending"] = False
        remote["payload"] = None

    args = args_for(package_path, task_directory, final_path)
    with (
        patch.object(live_runner, "_remote_input_sha256", remote_sha),
        patch.object(live_runner, "_remote_pending_status", remote_status),
        patch.object(live_runner, "_invoke_hermes_part", invoke),
        patch.object(live_runner, "_read_remote_regular_file", read_remote),
        patch.object(live_runner, "_remove_remote_pending", remove_remote),
        patch.object(
            live_runner,
            "promote_pending_part",
            wraps=live_runner.promote_pending_part,
        ) as promote,
    ):
        try:
            result = live_runner.run(args)
        except Exception as error:
            result = error

    return {
        "error_or_result": result,
        "package": package,
        "package_bytes": package_bytes,
        "plan": plan,
        "task": task_directory,
        "final": final_path,
        "expected": expected,
        "calls": calls,
        "promote_calls": promote.call_args_list,
        "first_bytes": first_bytes,
    }


def main():
    check(
        live_runner.STATEFUL_PART_MODEL_MAX_ATTEMPTS == 2,
        "MODEL_MAX_ATTEMPTS_INITIAL_PLUS_ONE_RETRY",
    )
    check(
        (
            STATEFUL_PART_RUNAWAY_MIN_TEXT_CHARS,
            STATEFUL_PART_RUNAWAY_MAX_UNIT_CHARS,
            STATEFUL_PART_RUNAWAY_MIN_REPETITIONS,
        )
        == (64, 4, 16),
        "VALIDATOR_THRESHOLDS_UNCHANGED",
    )

    source = Path("teddy_discovery_stateful_live_runner.py").read_text(
        encoding="utf-8"
    )
    check("AVSA-455" not in source, "NO_TITLE_SPECIFIC_PRODUCTION_ID")
    check("男の" not in source and "남자의" not in source, "NO_TEXT_HARDCODE")

    with TemporaryDirectory(prefix="stateful-retry-smoke-") as raw:
        root = Path(raw)
        recovered = run_synthetic(
            root / "valid-second",
            cue_count=17,
            invalid_attempts=1,
            prepromote_first=True,
        )
        check(
            recovered["error_or_result"] == 0,
            "INVALID_FIRST_VALID_SECOND_COMPLETES",
        )
        check(
            len(recovered["calls"]["model"]) == 2
            and len(recovered["calls"]["remove"]) == 1,
            "INVALID_PART_RETRIED_EXACTLY_ONCE",
        )
        check(
            recovered["calls"]["model"][0]
            == recovered["calls"]["model"][1],
            "RETRY_QUERY_IS_IDENTICAL",
        )
        query = recovered["calls"]["model"][0]
        expected = recovered["expected"]
        plan = recovered["plan"]
        check(
            f"part {expected.part_index} of {plan.part_count}" in query
            and expected.first_cue_id in query
            and expected.last_cue_id in query
            and plan.input_sha256 in query,
            "RETRY_SAME_PART_CUES_AND_INPUT_SHA",
        )
        check(
            len(recovered["promote_calls"]) == 1
            and recovered["promote_calls"][0].args[2]
            == expected.part_index,
            "VALID_PART_PROMOTED_ONCE",
        )
        check(
            recovered["first_bytes"]
            == (
                recovered["task"] / plan.parts[0].canonical_filename
            ).read_bytes()
            and not (
                recovered["task"] / expected.pending_filename
            ).exists(),
            "PREVIOUS_PROMOTED_PART_PRESERVED",
        )
        check(
            parse_stateful_part(
                (
                    recovered["task"] / expected.canonical_filename
                ).read_bytes(),
                expected,
                plan,
            ).part_index
            == expected.part_index,
            "VALID_SECOND_PAYLOAD_CANONICAL",
        )

        exhausted = run_synthetic(
            root / "invalid-twice",
            cue_count=1,
            invalid_attempts=2,
            prepromote_first=False,
        )
        error = exhausted["error_or_result"]
        check(
            isinstance(
                error,
                live_runner.StatefulSemanticOutputValidationRetryExhausted,
            )
            and error.part_index == 1
            and error.attempts == 2
            and error.max_attempts == 2
            and isinstance(error.__cause__, StatefulPartsValidationError),
            "REPEATED_INVALID_EXHAUSTS_TYPED_RETRY",
        )
        check(
            len(exhausted["calls"]["model"]) == 2
            and len(exhausted["calls"]["remove"]) == 2
            and exhausted["promote_calls"] == []
            and not (
                exhausted["task"] / exhausted["expected"].pending_filename
            ).exists()
            and not exhausted["final"].exists(),
            "EXHAUSTED_INVALID_NEVER_PROMOTED",
        )

    print("STATEFUL_LIVE_RUNNER_RETRY_SMOKE=PASS")


if __name__ == "__main__":
    main()
