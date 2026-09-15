"""Synthetic smoke coverage for Hermes timeout classification and isolation."""

import io
import os
import subprocess
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest.mock import patch

import teddy_discovery_stateful_live_runner as live_runner
from teddy_discovery_hermes_v2 import HermesV2CueInput, HermesV2CueOutput
from teddy_discovery_stateful_parts import (
    StatefulSemanticPart,
    build_stateful_part_plan,
    serialize_stateful_part,
)
from teddy_discovery_stateful_translator import (
    StatefulSubtitlePackage,
    bind_stateful_semantic_policy,
    serialize_stateful_package,
)


def check(condition: bool, marker: str):
    if not condition:
        raise AssertionError(marker)
    print("PASS=" + marker)


def package_for(count: int = 1) -> StatefulSubtitlePackage:
    return bind_stateful_semantic_policy(StatefulSubtitlePackage(
        schema_version=1,
        dvd_id="SYNTHETIC-TIMEOUT",
        generation_key="synthetic-timeout-generation-001",
        claim_token=1,
        cues=tuple(
            HermesV2CueInput(
                cue_id=f"asr-{index:06d}",
                external_ja="テスト-" + str(index),
                stt_ja=None,
                en=None,
                before_context=(),
                after_context=(),
            )
            for index in range(1, count + 1)
        ),
    ))


def valid_part(plan, part_index: int = 1) -> StatefulSemanticPart:
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


def args_for() -> SimpleNamespace:
    return SimpleNamespace(
        remote="synthetic@offline",
        ssh_key="/synthetic/key",
        known_hosts="/synthetic/known-hosts",
        turn_timeout=600,
    )


def main():
    parser_args = live_runner.build_parser().parse_args(
        [
            "--package",
            "/synthetic/package.json",
            "--task-directory",
            "/synthetic/task",
            "--final-result",
            "/synthetic/result.json",
            "--remote",
            "synthetic@offline",
            "--remote-task",
            "/synthetic/remote-task",
            "--ssh-key",
            "/synthetic/key",
            "--known-hosts",
            "/synthetic/known-hosts",
        ]
    )
    check(
        parser_args.turn_timeout == 600,
        "HERMES_TIMEOUT_DEFAULT_REMAINS_600",
    )

    source = Path("teddy_discovery_stateful_live_runner.py").read_text(
        encoding="utf-8"
    )
    check("DASS-884" not in source, "NO_TITLE_SPECIFIC_PRODUCTION_ID")
    check("asr-000001" not in source, "NO_CUE_SPECIFIC_PRODUCTION_ID")

    timeout_calls = []

    def timeout_process(command, **kwargs):
        timeout_calls.append((command, kwargs["timeout"]))
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    timeout_output = io.StringIO()
    try:
        with redirect_stdout(timeout_output), patch.object(
            live_runner.subprocess,
            "run",
            side_effect=timeout_process,
        ):
            live_runner._invoke_hermes_part(
                remote="synthetic@offline",
                ssh_key="/synthetic/key",
                known_hosts="/synthetic/known-hosts",
                remote_task="/synthetic/remote-task",
                session_id="00000000-0000-4000-8000-000000000001",
                query="synthetic part query",
                turn_timeout=600,
            )
    except live_runner.StatefulLiveRunnerTimeoutError as error:
        timeout_error = error
    else:
        raise AssertionError("timeout was not typed")

    check(
        isinstance(timeout_error.__cause__, subprocess.TimeoutExpired)
        and timeout_error.timeout_seconds == 600
        and timeout_error.invocation_start_epoch is not None
        and timeout_error.invocation_end_epoch is not None
        and timeout_error.invocation_elapsed_seconds is not None
        and timeout_error.invocation_end_epoch
        >= timeout_error.invocation_start_epoch
        and str(timeout_error)
        == "Hermes part invocation exceeded controller timeout"
        and len(timeout_calls) == 1,
        "SUBPROCESS_TIMEOUT_TYPED_EXACTLY_ONCE",
    )
    check(
        "HERMES_INVOCATION_START_EPOCH=" in timeout_output.getvalue()
        and "HERMES_INVOCATION_END_EPOCH=" in timeout_output.getvalue()
        and "HERMES_INVOCATION_ELAPSED_SECONDS=" in timeout_output.getvalue()
        and "HERMES_INVOCATION_TIMEOUT_SECONDS=600"
        in timeout_output.getvalue()
        and "HERMES_INVOCATION_RESULT=TIMEOUT"
        in timeout_output.getvalue(),
        "TIMEOUT_EMITS_COMPLETE_TIMING_DIAGNOSTICS",
    )

    pass_output = io.StringIO()
    with redirect_stdout(pass_output), patch.object(
        live_runner.subprocess,
        "run",
        return_value=subprocess.CompletedProcess([], 0),
    ):
        live_runner._invoke_hermes_part(
            remote="synthetic@offline",
            ssh_key="/synthetic/key",
            known_hosts="/synthetic/known-hosts",
            remote_task="/synthetic/remote-task",
            session_id="00000000-0000-4000-8000-000000000001",
            query="synthetic part query",
            turn_timeout=600,
        )
    check(
        "HERMES_INVOCATION_RESULT=PASS" in pass_output.getvalue(),
        "PASS_INVOCATION_EMITS_PASS_RESULT",
    )

    fail_output = io.StringIO()
    try:
        with redirect_stdout(fail_output), patch.object(
            live_runner.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 1),
        ):
            live_runner._invoke_hermes_part(
                remote="synthetic@offline",
                ssh_key="/synthetic/key",
                known_hosts="/synthetic/known-hosts",
                remote_task="/synthetic/remote-task",
                session_id="00000000-0000-4000-8000-000000000001",
                query="synthetic part query",
                turn_timeout=600,
            )
    except live_runner.StatefulLiveRunnerError:
        failed_invocation = True
    else:
        failed_invocation = False
    check(
        failed_invocation
        and "HERMES_INVOCATION_RESULT=FAIL" in fail_output.getvalue(),
        "FAIL_INVOCATION_EMITS_FAIL_RESULT",
    )

    package = package_for(65)
    package_bytes = serialize_stateful_package(package)
    plan = build_stateful_part_plan(package, package_bytes)
    expected = plan.parts[1]

    with TemporaryDirectory(prefix="stateful-timeout-smoke-") as raw:
        task_directory = Path(raw)
        previous_part = valid_part(plan, 1)
        previous_path = task_directory / plan.parts[0].canonical_filename
        previous_path.write_bytes(serialize_stateful_part(previous_part))
        os.chmod(previous_path, 0o600)
        previous_bytes = previous_path.read_bytes()
        remote_status_calls = []
        hermes_calls = []
        cleanup_calls = []
        part_timeout_output = io.StringIO()

        def missing_remote_pending(*, path, **_kwargs):
            remote_status_calls.append(path)
            return False

        def timed_out_hermes(**_kwargs):
            hermes_calls.append(True)
            raise live_runner.StatefulLiveRunnerTimeoutError(
                timeout_seconds=600
            )

        with (
            redirect_stdout(part_timeout_output),
            patch.object(
                live_runner,
                "_remote_pending_status",
                missing_remote_pending,
            ),
            patch.object(
                live_runner,
                "_invoke_hermes_part",
                timed_out_hermes,
            ),
            patch.object(
                live_runner,
                "_remove_remote_pending",
                lambda **kwargs: cleanup_calls.append(kwargs["path"]),
            ),
        ):
            try:
                live_runner._request_and_install_part(
                    args=args_for(),
                    package=package,
                    semantic_input_bytes=package_bytes,
                    task_directory=task_directory,
                    remote_task="/synthetic/remote-task",
                    plan=plan,
                    expected=expected,
                    final_path=task_directory / "final.json",
                )
            except live_runner.StatefulLiveRunnerTimeoutError:
                pass
            else:
                raise AssertionError("same-part timeout unexpectedly recovered")

        check(
            len(hermes_calls) == 1
            and len(remote_status_calls) == 1
            and cleanup_calls == []
            and previous_path.read_bytes() == previous_bytes
            and not (
                task_directory / expected.canonical_filename
            ).exists()
            and not (
                task_directory / expected.pending_filename
            ).exists(),
            "TIMEOUT_HAS_ZERO_IMMEDIATE_RETRY_AND_PRESERVES_PROMOTED",
        )
        check(
            "PENDING_ARTIFACT_PATH=/synthetic/remote-task/"
            in part_timeout_output.getvalue()
            and "PENDING_ARTIFACT_EXISTS=UNKNOWN"
            in part_timeout_output.getvalue()
            and "PENDING_ARTIFACT_SIZE_BYTES=UNAVAILABLE"
            in part_timeout_output.getvalue()
            and "RESULT_ARTIFACT_EXISTS=NO"
            in part_timeout_output.getvalue()
            and "RESUME_PROMOTED_ARTIFACT_EXISTS=NO"
            in part_timeout_output.getvalue(),
            "TIMEOUT_ARTIFACT_STATUS_MARKERS",
        )

        pending_payload = serialize_stateful_part(valid_part(plan, 2))
        recovery_task = task_directory / "recovery"
        recovery_task.mkdir(mode=0o700)
        recovery_status_calls = []
        recovery_hermes_calls = []
        recovery_cleanup_calls = []

        def present_remote_pending(*, path, **_kwargs):
            recovery_status_calls.append(path)
            return True

        with (
            patch.object(
                live_runner,
                "_remote_pending_status",
                present_remote_pending,
            ),
            patch.object(
                live_runner,
                "_invoke_hermes_part",
                lambda **_kwargs: recovery_hermes_calls.append(True),
            ),
            patch.object(
                live_runner,
                "_read_remote_regular_file",
                lambda **_kwargs: pending_payload,
            ),
            patch.object(
                live_runner,
                "_remove_remote_pending",
                lambda **kwargs: recovery_cleanup_calls.append(
                    kwargs["path"]
                ),
            ),
        ):
            live_runner._request_and_install_part(
                args=args_for(),
                package=package,
                semantic_input_bytes=package_bytes,
                task_directory=recovery_task,
                remote_task="/synthetic/remote-task",
                plan=plan,
                expected=expected,
            )

        check(
            len(recovery_status_calls) == 1
            and recovery_hermes_calls == []
            and recovery_cleanup_calls == []
            and (recovery_task / expected.pending_filename).exists(),
            "REMOTE_PENDING_RECOVERY_CONTRACT_PRESERVED",
        )

    print("STATEFUL_LIVE_RUNNER_TIMEOUT_SMOKE=PASS")


if __name__ == "__main__":
    main()
