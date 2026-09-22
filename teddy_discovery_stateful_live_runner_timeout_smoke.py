"""Synthetic smoke coverage for Hermes timeout classification and isolation."""

import io
import os
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
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


def diagnostic_value(output: str, key: str) -> str:
    prefix = key + "="
    for line in output.splitlines():
        if line.startswith(prefix):
            return line[len(prefix):]
    raise AssertionError("missing diagnostic " + key)


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
        absolute_timeout=live_runner.CANDIDATE_HERMES_ABSOLUTE_TIMEOUT_SECONDS,
    )


def invoke_synthetic(
    script: str,
    *,
    inactivity_timeout: float,
    absolute_timeout: float,
) -> None:
    with (
        patch.object(
            live_runner,
            "_ssh_base",
            return_value=[sys.executable, "-u", "-c", script],
        ),
        patch.object(
            live_runner,
            "_cleanup_timed_out_remote_hermes",
            return_value=None,
        ),
    ):
        live_runner._invoke_hermes_part(
            remote="synthetic@offline",
            ssh_key="/synthetic/key",
            known_hosts="/synthetic/known-hosts",
            remote_task="/synthetic/remote-task",
            session_id="00000000-0000-4000-8000-000000000001",
            query="synthetic part query",
            turn_timeout=inactivity_timeout,
            absolute_timeout=absolute_timeout,
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
    check(
        parser_args.absolute_timeout
        == live_runner.CANDIDATE_HERMES_ABSOLUTE_TIMEOUT_SECONDS
        == 3600,
        "ABSOLUTE_TIMEOUT_HAS_EXPLICIT_REVIEW_CANDIDATE_DEFAULT",
    )
    configured_args = live_runner.build_parser().parse_args(
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
            "--inactivity-timeout",
            "123",
            "--absolute-timeout",
            "4567",
        ]
    )
    check(
        configured_args.turn_timeout == 123
        and configured_args.absolute_timeout == 4567,
        "BOTH_TIMEOUT_BOUNDS_ARE_CONFIGURABLE",
    )

    source = Path("teddy_discovery_stateful_live_runner.py").read_text(
        encoding="utf-8"
    )
    check("DASS-884" not in source, "NO_TITLE_SPECIFIC_PRODUCTION_ID")
    check("asr-000001" not in source, "NO_CUE_SPECIFIC_PRODUCTION_ID")

    timeout_output = io.StringIO()
    try:
        with redirect_stdout(timeout_output):
            invoke_synthetic(
                "import time; time.sleep(2)",
                inactivity_timeout=0.25,
                absolute_timeout=1.0,
            )
    except live_runner.StatefulLiveRunnerTimeoutError as error:
        timeout_error = error
    else:
        raise AssertionError("timeout was not typed")

    check(
        isinstance(timeout_error.__cause__, TimeoutError)
        and timeout_error.timeout_reason == "INACTIVITY_TIMEOUT"
        and timeout_error.timeout_seconds == 0.25
        and timeout_error.inactivity_timeout_seconds == 0.25
        and timeout_error.absolute_timeout_seconds == 1.0
        and timeout_error.invocation_start_epoch is not None
        and timeout_error.invocation_end_epoch is not None
        and timeout_error.invocation_elapsed_seconds is not None
        and timeout_error.invocation_end_epoch
            >= timeout_error.invocation_start_epoch
        and 0.20 <= timeout_error.invocation_elapsed_seconds < 1.0
        and timeout_error.seconds_since_last_output_activity is None
        and str(timeout_error)
        == "Hermes part invocation exceeded controller timeout",
        "NO_OUTPUT_CLASSIFIED_AS_INACTIVITY_TIMEOUT",
    )
    check(
        "HERMES_INVOCATION_START_EPOCH=" in timeout_output.getvalue()
        and "HERMES_INVOCATION_END_EPOCH=" in timeout_output.getvalue()
        and "HERMES_INVOCATION_ELAPSED_SECONDS=" in timeout_output.getvalue()
        and "HERMES_INVOCATION_CONFIGURED_INACTIVITY_TIMEOUT_SECONDS=0.25"
        in timeout_output.getvalue()
        and "HERMES_INVOCATION_CONFIGURED_ABSOLUTE_TIMEOUT_SECONDS=1.0"
        in timeout_output.getvalue()
        and "HERMES_INVOCATION_TIMEOUT_REASON=INACTIVITY_TIMEOUT"
        in timeout_output.getvalue()
        and "HERMES_INVOCATION_SECONDS_SINCE_LAST_OUTPUT_ACTIVITY=UNAVAILABLE"
        in timeout_output.getvalue()
        and "HERMES_INVOCATION_RESULT=TIMEOUT"
        in timeout_output.getvalue(),
        "TIMEOUT_EMITS_COMPLETE_TIMING_DIAGNOSTICS",
    )

    mismatch_output = io.StringIO()
    cleanup_failure = live_runner.StatefulLiveRunnerError(
        "remote Hermes timeout cleanup failed"
    )
    with (
        patch.object(
            live_runner,
            "_ssh_base",
            return_value=[sys.executable, "-u", "-c", "import time; time.sleep(2)"],
        ),
        patch.object(
            live_runner,
            "_cleanup_timed_out_remote_hermes",
            side_effect=cleanup_failure,
        ),
        redirect_stdout(mismatch_output),
    ):
        try:
            live_runner._invoke_hermes_part(
                remote="synthetic@offline",
                ssh_key="/synthetic/key",
                known_hosts="/synthetic/known-hosts",
                remote_task="/synthetic/remote-task",
                session_id="00000000-0000-4000-8000-000000000001",
                query="synthetic part query",
                turn_timeout=0.25,
                absolute_timeout=1.0,
            )
        except live_runner.StatefulLiveRunnerTimeoutError as error:
            mismatch_error = error
        else:
            raise AssertionError("cleanup failure covered the timeout")
    check(
        mismatch_error.timeout_reason == "INACTIVITY_TIMEOUT"
        and mismatch_error.__cause__ is cleanup_failure
        and mismatch_error.__context__ is None
        and "HERMES_INVOCATION_TIMEOUT_REASON=INACTIVITY_TIMEOUT"
        in mismatch_output.getvalue()
        and "HERMES_INVOCATION_RESULT=TIMEOUT" in mismatch_output.getvalue(),
        "TIMEOUT_CLEANUP_FAILURE_PRESERVES_PRIMARY_EXCEPTION",
    )

    mismatch_marker_output = io.StringIO()
    with (
        patch.object(live_runner, "_ssh_base", return_value=["synthetic-ssh"]),
        patch.object(
            live_runner.subprocess,
            "run",
            return_value=SimpleNamespace(
                returncode=26,
                stdout=b"REMOTE_TIMEOUT_CLEANUP_RESULT=CMDLINE_MISMATCH\n",
                stderr=b"",
            ),
        ),
        redirect_stdout(mismatch_marker_output),
    ):
        try:
            live_runner._cleanup_timed_out_remote_hermes(
                remote="synthetic@offline",
                ssh_key="/synthetic/key",
                known_hosts="/synthetic/known-hosts",
                remote_task="/synthetic/remote-task",
                session_id="00000000-0000-4000-8000-000000000001",
            )
        except live_runner.StatefulLiveRunnerError as error:
            check(
                type(error) is live_runner.StatefulLiveRunnerError
                and error.__cause__ is None
                and error.__context__ is None
                and "REMOTE_TIMEOUT_CLEANUP_RESULT=CMDLINE_MISMATCH"
                in mismatch_marker_output.getvalue(),
                "CMDLINE_MISMATCH_CLEANUP_EXACT_EXCEPTION",
            )
        else:
            raise AssertionError("cmdline mismatch cleanup unexpectedly passed")

    stdout_activity_output = io.StringIO()
    with redirect_stdout(stdout_activity_output), redirect_stderr(io.StringIO()):
        invoke_synthetic(
            "import sys,time\n"
            "for _ in range(12):\n"
            " sys.stdout.write('STDOUT_ACTIVITY_TICK\\n'); sys.stdout.flush(); time.sleep(0.08)\n",
            inactivity_timeout=0.4,
            absolute_timeout=2.0,
        )
    check(
        "STDOUT_ACTIVITY_TICK" in stdout_activity_output.getvalue()
        and "HERMES_INVOCATION_RESULT=PASS" in stdout_activity_output.getvalue()
        and float(
            diagnostic_value(
                stdout_activity_output.getvalue(),
                "HERMES_INVOCATION_ELAPSED_SECONDS",
            )
        ) > 0.4,
        "PERIODIC_STDOUT_RESETS_SCALED_INACTIVITY_TIMEOUT",
    )

    class ChildAwareOutput(io.StringIO):
        def __init__(self, child_processes):
            super().__init__()
            self.child_processes = child_processes
            self.child_was_running_at_output = False

        def write(self, value):
            if (
                "LIVE_CHILD_OUTPUT" in value
                and self.child_processes
                and self.child_processes[0].poll() is None
            ):
                self.child_was_running_at_output = True
            return super().write(value)

    child_processes = []
    live_output = ChildAwareOutput(child_processes)
    real_popen = subprocess.Popen

    def capture_child(*args, **kwargs):
        child = real_popen(*args, **kwargs)
        child_processes.append(child)
        return child

    with (
        redirect_stdout(live_output),
        redirect_stderr(io.StringIO()),
        patch.object(
            live_runner,
            "_ssh_base",
            return_value=[
                sys.executable,
                "-u",
                "-c",
                "import time; print('LIVE_CHILD_OUTPUT',flush=True); time.sleep(0.25)",
            ],
        ),
        patch.object(
            live_runner.subprocess,
            "Popen",
            side_effect=capture_child,
        ),
    ):
        live_runner._invoke_hermes_part(
            remote="synthetic@offline",
            ssh_key="/synthetic/key",
            known_hosts="/synthetic/known-hosts",
            remote_task="/synthetic/remote-task",
            session_id="00000000-0000-4000-8000-000000000001",
            query="synthetic part query",
            turn_timeout=1.0,
            absolute_timeout=2.0,
        )
    check(
        live_output.child_was_running_at_output
        and "LIVE_CHILD_OUTPUT" in live_output.getvalue(),
        "CHILD_OUTPUT_IS_FORWARDED_BEFORE_INVOCATION_COMPLETES",
    )

    stderr_activity_output = io.StringIO()
    stderr_activity_log = io.StringIO()
    with redirect_stdout(stderr_activity_log), redirect_stderr(stderr_activity_output):
        invoke_synthetic(
            "import sys,time\n"
            "for _ in range(12):\n"
            " sys.stderr.write('STDERR_ACTIVITY_TICK\\n'); sys.stderr.flush(); time.sleep(0.08)\n",
            inactivity_timeout=0.4,
            absolute_timeout=2.0,
        )
    check(
        "STDERR_ACTIVITY_TICK" in stderr_activity_output.getvalue()
        and "HERMES_INVOCATION_RESULT=PASS" in stderr_activity_log.getvalue()
        and float(
            diagnostic_value(
                stderr_activity_log.getvalue(),
                "HERMES_INVOCATION_ELAPSED_SECONDS",
            )
        ) > 0.4,
        "PERIODIC_STDERR_RESETS_SCALED_INACTIVITY_TIMEOUT",
    )

    absolute_timeout_output = io.StringIO()
    try:
        with redirect_stdout(absolute_timeout_output), redirect_stderr(io.StringIO()):
            invoke_synthetic(
                "import os,time\n"
                "while True:\n"
                " os.write(1,b'ABSOLUTE_CAP_ACTIVITY\\n'); time.sleep(0.025)\n",
                inactivity_timeout=0.8,
                absolute_timeout=0.35,
            )
    except live_runner.StatefulLiveRunnerTimeoutError as error:
        absolute_error = error
    else:
        raise AssertionError("absolute timeout was not typed")
    check(
        absolute_error.timeout_reason == "ABSOLUTE_TIMEOUT"
        and absolute_error.timeout_seconds == 0.35
        and absolute_error.inactivity_timeout_seconds == 0.8
        and absolute_error.absolute_timeout_seconds == 0.35
        and absolute_error.seconds_since_last_output_activity is not None
        and absolute_error.seconds_since_last_output_activity < 0.2
        and "ABSOLUTE_CAP_ACTIVITY" in absolute_timeout_output.getvalue()
        and "HERMES_INVOCATION_TIMEOUT_REASON=ABSOLUTE_TIMEOUT"
        in absolute_timeout_output.getvalue(),
        "ENDLESS_ACTIVITY_IS_STOPPED_BY_NONRESETTING_ABSOLUTE_CAP",
    )
    check(
        diagnostic_value(
            absolute_timeout_output.getvalue(),
            "HERMES_INVOCATION_CONFIGURED_INACTIVITY_TIMEOUT_SECONDS",
        ) == "0.8"
        and diagnostic_value(
            absolute_timeout_output.getvalue(),
            "HERMES_INVOCATION_CONFIGURED_ABSOLUTE_TIMEOUT_SECONDS",
        ) == "0.35"
        and float(
            diagnostic_value(
                absolute_timeout_output.getvalue(),
                "HERMES_INVOCATION_SECONDS_SINCE_LAST_OUTPUT_ACTIVITY",
            )
        ) < 0.2,
        "ABSOLUTE_TIMEOUT_DIAGNOSTICS_INCLUDE_BOTH_LIMITS_AND_ACTIVITY_AGE",
    )

    pass_output = io.StringIO()
    with redirect_stdout(pass_output), redirect_stderr(io.StringIO()):
        invoke_synthetic(
            "print('SYNTHETIC_SUCCESS',flush=True)",
            inactivity_timeout=1.0,
            absolute_timeout=2.0,
        )
    check(
        "SYNTHETIC_SUCCESS" in pass_output.getvalue()
        and "HERMES_INVOCATION_RESULT=PASS" in pass_output.getvalue(),
        "PASS_INVOCATION_EMITS_PASS_RESULT",
    )

    fail_output = io.StringIO()
    try:
        with redirect_stdout(fail_output), redirect_stderr(io.StringIO()):
            invoke_synthetic(
                "import sys; sys.exit(7)",
                inactivity_timeout=1.0,
                absolute_timeout=2.0,
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
        temp_root = Path(raw)
        for timeout_reason, timeout_seconds in (
            ("INACTIVITY_TIMEOUT", 600),
            ("ABSOLUTE_TIMEOUT", 3600),
        ):
            task_directory = temp_root / timeout_reason.lower()
            task_directory.mkdir(mode=0o700)
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
                    timeout_seconds=timeout_seconds,
                    timeout_reason=timeout_reason,
                    inactivity_timeout_seconds=600,
                    absolute_timeout_seconds=3600,
                    invocation_elapsed_seconds=timeout_seconds,
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
                    raise AssertionError(
                        "same-part timeout unexpectedly recovered"
                    )

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
                timeout_reason
                + "_HAS_ZERO_IMMEDIATE_RETRY_AND_PRESERVES_PROMOTED",
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
                timeout_reason + "_PRESERVES_TIMEOUT_ARTIFACT_DIAGNOSTICS",
            )

        pending_payload = serialize_stateful_part(valid_part(plan, 2))
        recovery_task = temp_root / "recovery"
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


    # End-to-end synthetic proof for the remote timeout lifecycle.
    #
    # This runs the real _invoke_hermes_part() remote shell locally with:
    # - a fake hermes executable,
    # - a fake hostname reporting the expected CT120 hostname,
    # - one target Hermes process group that must be cleaned,
    # - one unrelated Hermes process group that must remain alive.
    check(
        ".stage11-hermes-runtime.pid" in source
        and ".stage11-hermes-runtime.meta" in source
        and "setsid" in source
        and "_cleanup_timed_out_remote_hermes" in source,
        "REMOTE_TIMEOUT_RUNTIME_MARKER_AND_CLEANUP_WIRING_PRESENT",
    )

    check(
        "pkill" not in source
        and "killall" not in source
        and "pgrep" not in source,
        "REMOTE_TIMEOUT_CLEANUP_HAS_NO_BROAD_PROCESS_KILL",
    )

    with TemporaryDirectory(prefix="stateful-remote-cleanup-smoke-") as raw:
        synthetic_root = Path(raw)
        synthetic_home = synthetic_root / "home"
        synthetic_bin = synthetic_root / "bin"
        target_task = synthetic_root / "target-task"
        unrelated_task = synthetic_root / "unrelated-task"

        (synthetic_home / ".local" / "bin").mkdir(parents=True)
        synthetic_bin.mkdir()
        target_task.mkdir()
        unrelated_task.mkdir()

        fake_hostname = synthetic_bin / "hostname"
        fake_hostname.write_text(
            "#!/bin/sh\nprintf '%s\\n' 'hermes-lxc-slack'\n",
            encoding="utf-8",
        )
        fake_hostname.chmod(0o755)

        fake_hermes = synthetic_home / ".local" / "bin" / "hermes"
        fake_hermes.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$$\" > synthetic-hermes.pid\n"
            "while :; do\n"
            "  sleep 1\n"
            "done\n",
            encoding="utf-8",
        )
        fake_hermes.chmod(0o755)

        synthetic_env = os.environ.copy()
        synthetic_env["HOME"] = str(synthetic_home)
        synthetic_env["PATH"] = (
            str(synthetic_bin)
            + os.pathsep
            + synthetic_env.get("PATH", "")
        )

        target_session = "00000000-0000-4000-8000-000000000111"
        unrelated_session = "00000000-0000-4000-8000-000000000222"

        unrelated = subprocess.Popen(
            [
                str(fake_hermes),
                "--profile",
                "subtitle-translator",
                "chat",
                "--resume",
                unrelated_session,
            ],
            cwd=unrelated_task,
            env=synthetic_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        ssh_prefix = [
            "env",
            "HOME=" + str(synthetic_home),
            "PATH=" + synthetic_env["PATH"],
        ]

        cleanup_output = io.StringIO()
        cleanup_error = None

        try:
            with (
                patch.object(
                    live_runner,
                    "_ssh_base",
                    return_value=ssh_prefix,
                ),
                redirect_stdout(cleanup_output),
                redirect_stderr(io.StringIO()),
            ):
                try:
                    live_runner._invoke_hermes_part(
                        remote="synthetic@offline",
                        ssh_key="/synthetic/key",
                        known_hosts="/synthetic/known-hosts",
                        remote_task=str(target_task),
                        session_id=target_session,
                        query="synthetic timeout cleanup query",
                        turn_timeout=0.5,
                        absolute_timeout=2.0,
                    )
                except live_runner.StatefulLiveRunnerTimeoutError as error:
                    cleanup_error = error
                else:
                    raise AssertionError(
                        "synthetic remote cleanup invocation did not time out"
                    )

            target_pid_path = target_task / "synthetic-hermes.pid"
            check(
                cleanup_error is not None
                and cleanup_error.timeout_reason == "INACTIVITY_TIMEOUT"
                and "REMOTE_TIMEOUT_CLEANUP_RESULT=PASS"
                in cleanup_output.getvalue(),
                "REMOTE_TIMEOUT_EXACT_PROCESS_GROUP_CLEANUP",
            )

            check(
                target_pid_path.exists(),
                "REMOTE_TIMEOUT_TARGET_PROCESS_STARTED",
            )

            target_pid = int(
                target_pid_path.read_text(encoding="utf-8").strip()
            )

            check(
                not Path("/proc/" + str(target_pid)).exists(),
                "REMOTE_TIMEOUT_TARGET_PROCESS_IS_REAPED",
            )

            check(
                not (
                    target_task / ".stage11-hermes-runtime.pid"
                ).exists()
                and not (
                    target_task / ".stage11-hermes-runtime.meta"
                ).exists(),
                "REMOTE_TIMEOUT_RUNTIME_MARKERS_REMOVED",
            )

            check(
                unrelated.poll() is None,
                "REMOTE_TIMEOUT_UNRELATED_HERMES_SURVIVES",
            )

        finally:
            if unrelated.poll() is None:
                try:
                    os.killpg(unrelated.pid, 15)
                except ProcessLookupError:
                    pass

                try:
                    unrelated.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(unrelated.pid, 9)
                    except ProcessLookupError:
                        pass
                    unrelated.wait(timeout=3)


    print("STATEFUL_LIVE_RUNNER_TIMEOUT_SMOKE=PASS")


if __name__ == "__main__":
    main()
