"""Synthetic smoke coverage for bounded invalid semantic-part recovery."""

import io
import json
import os
from contextlib import redirect_stdout
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
    return mutated_payload(
        part,
        lambda data: data["cues"][0].__setitem__("ko", "반복" * 32),
    )


def mutated_payload(part: StatefulSemanticPart, mutate) -> bytes:
    data = json.loads(serialize_stateful_part(part).decode("utf-8"))
    mutate(data)
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
    invalid_mutator=None,
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
    valid_expected_part = valid_part(plan, expected.part_index)
    invalid = (
        invalid_payload(valid_expected_part)
        if invalid_mutator is None
        else mutated_payload(valid_expected_part, invalid_mutator)
    )

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
    output = io.StringIO()
    with (
        redirect_stdout(output),
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
        "output": output.getvalue(),
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
        recovered_rejection = (
            "SEMANTIC_VALIDATION_REJECTED=INVALID_KO"
            + "|PART_INDEX="
            + str(expected.part_index)
            + "|ATTEMPT=1"
            + "|SESSION_ID="
            + plan.session_id
            + "|INPUT_SHA256="
            + plan.input_sha256
        )
        check(
            recovered_rejection in recovered["output"],
            "EXACT_SEMANTIC_REASON_MARKER_INCLUDES_CONTEXT",
        )
        check(
            sum(
                line.startswith("PENDING_ARTIFACT_PATH=")
                for line in recovered["output"].splitlines()
            )
            == 1
            and "PENDING_ARTIFACT_EXISTS=YES" in recovered["output"]
            and "PENDING_ARTIFACT_SIZE_BYTES=" in recovered["output"]
            and "RESULT_ARTIFACT_EXISTS=NO" in recovered["output"]
            and "RESUME_PROMOTED_ARTIFACT_EXISTS=NO" in recovered["output"],
            "SEMANTIC_FAILURE_ARTIFACT_STATUS_MARKERS",
        )
        check(
            "반복" not in recovered["output"],
            "SEMANTIC_FAILURE_DOES_NOT_DUMP_MODEL_OUTPUT",
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

        diagnostic_cases = (
            (
                "SESSION_ID_MISMATCH",
                lambda data: data.__setitem__(
                    "session_id",
                    "00000000-0000-0000-0000-000000000000",
                ),
            ),
            (
                "INPUT_SHA256_MISMATCH",
                lambda data: data.__setitem__("input_sha256", "0" * 64),
            ),
            (
                "MISSING_CUE_ID",
                lambda data: data["cues"][1].__setitem__(
                    "cue_id",
                    "asr-999999",
                ),
            ),
            (
                "DUPLICATE_CUE_ID",
                lambda data: data["cues"].__setitem__(
                    1,
                    dict(data["cues"][0]),
                ),
            ),
            (
                "CUE_ORDER_MISMATCH",
                lambda data: data["cues"].__setitem__(
                    slice(1, 3),
                    [data["cues"][2], data["cues"][1]],
                ),
            ),
            (
                "INVALID_KO",
                lambda data: data["cues"][0].__setitem__("ko", ""),
            ),
            (
                "INVALID_REPAIRED_JA",
                lambda data: data["cues"][0].__setitem__(
                    "repaired_ja",
                    123,
                ),
            ),
        )
        for reason, mutate in diagnostic_cases:
            diagnostic = run_synthetic(
                root / ("diagnostic-" + reason),
                cue_count=32,
                invalid_attempts=1,
                prepromote_first=True,
                invalid_mutator=mutate,
            )
            expected = diagnostic["expected"]
            plan = diagnostic["plan"]
            expected_marker = (
                "SEMANTIC_VALIDATION_REJECTED="
                + reason
                + "|PART_INDEX="
                + str(expected.part_index)
                + "|ATTEMPT=1|SESSION_ID="
                + plan.session_id
                + "|INPUT_SHA256="
                + plan.input_sha256
            )
            check(
                diagnostic["error_or_result"] == 0
                and expected_marker in diagnostic["output"],
                "DIAGNOSTIC_MARKER_" + reason,
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
        exhausted_rejections = [
            line
            for line in exhausted["output"].splitlines()
            if line.startswith("SEMANTIC_VALIDATION_REJECTED=")
        ]
        check(
            len(exhausted_rejections) == 2
            and all(
                "SEMANTIC_VALIDATION_REJECTED=INVALID_KO"
                in line
                and "|PART_INDEX=1|" in line
                and "|SESSION_ID=" + exhausted["plan"].session_id in line
                and "|INPUT_SHA256=" + exhausted["plan"].input_sha256 in line
                for line in exhausted_rejections
            )
            and "|ATTEMPT=1|" in exhausted_rejections[0]
            and "|ATTEMPT=2|" in exhausted_rejections[1],
            "EVERY_VALIDATION_ATTEMPT_HAS_EXACT_REASON_MARKER",
        )
        check(
            sum(
                line.startswith("PENDING_ARTIFACT_PATH=")
                for line in exhausted["output"].splitlines()
            )
            == 2
            and exhausted["output"].count("RESULT_ARTIFACT_EXISTS=NO") == 2,
            "EVERY_VALIDATION_ATTEMPT_HAS_ARTIFACT_STATUS",
        )

    print("STATEFUL_LIVE_RUNNER_RETRY_SMOKE=PASS")


if __name__ == "__main__":
    main()
