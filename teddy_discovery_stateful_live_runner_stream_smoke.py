"""Offline stream-suppression tests for the Hermes live subprocess boundary."""

import hashlib
import io
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import tempfile
import textwrap
from types import SimpleNamespace
from unittest.mock import patch

import teddy_discovery_stateful_live_runner as live_runner


SUBTITLE_SENTINEL = "PRIVATE_SUBTITLE_BODY_STREAM_SENTINEL"
RAW_DIFF_SENTINEL = "RAW_HERMES_DIFF_SENTINEL"


def check(condition: bool, marker: str) -> None:
    if not condition:
        raise AssertionError(marker)
    print("PASS=" + marker)


def fixture_ssh(bin_dir: Path) -> Path:
    path = bin_dir / "ssh"
    path.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import os
            import sys
            import time

            sys.stdin.buffer.read()
            mode = os.environ["FAKE_HERMES_MODE"]
            token = sys.argv[-1]
            with open(os.environ["FAKE_TOKEN_PATH"], "w", encoding="ascii") as handle:
                handle.write(token)
            if mode == "success":
                sys.stdout.buffer.write(
                    (
                        f"STAGE11_SAFE_DIAGNOSTIC:{token}:MODEL_RC=0\\n"
                        f"STAGE11_SAFE_DIAGNOSTIC:{token}:REMOTE_MODEL_STEP_RESULT=1\\n"
                        "--- review diff\\n+PRIVATE_SUBTITLE_BODY_STREAM_SENTINEL\\n"
                    ).encode("ascii")
                )
                sys.stderr.buffer.write(b"RAW_HERMES_DIFF_SENTINEL\\n")
                sys.stdout.flush()
                sys.stderr.flush()
                raise SystemExit(0)
            if mode == "error":
                sys.stdout.buffer.write(
                    (
                        f"STAGE11_SAFE_DIAGNOSTIC:{token}:MODEL_RC=23\\n"
                        f"STAGE11_SAFE_DIAGNOSTIC:{token}:REMOTE_MODEL_STEP_RESULT=0\\n"
                        "--- review diff\\n+PRIVATE_SUBTITLE_BODY_STREAM_SENTINEL\\n"
                    ).encode("ascii")
                )
                sys.stderr.buffer.write(b"RAW_HERMES_DIFF_SENTINEL\\n")
                sys.stdout.flush()
                sys.stderr.flush()
                raise SystemExit(1)
            if mode == "timeout":
                sys.stdout.buffer.write(
                    b"--- review diff\\n+PRIVATE_SUBTITLE_BODY_STREAM_SENTINEL\\n"
                )
                sys.stderr.buffer.write(b"RAW_HERMES_DIFF_SENTINEL\\n")
                sys.stdout.flush()
                sys.stderr.flush()
                time.sleep(3)
                raise SystemExit(0)
            raise SystemExit(99)
            """
        ),
        encoding="utf-8",
    )
    path.chmod(0o700)
    return path


def invoke_fixture(
    mode: str,
    bin_dir: Path,
    *,
    timeout: float = 2.0,
) -> tuple[str, Exception | None]:
    out = io.StringIO()
    err = io.StringIO()
    caught = None
    with (
        patch.dict(
            os.environ,
            {
                "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
                "FAKE_HERMES_MODE": mode,
                "FAKE_TOKEN_PATH": str(
                    bin_dir.parent / "diagnostic-token.txt"
                ),
            },
        ),
        redirect_stdout(out),
        redirect_stderr(err),
    ):
        try:
            live_runner._invoke_hermes_part(
                remote="fixture@offline",
                ssh_key="/fixture/key",
                known_hosts="/fixture/known-hosts",
                remote_task="/fixture/task",
                session_id="00000000-0000-0000-0000-000000000001",
                query="synthetic query containing no subtitle body",
                turn_timeout=timeout,
                absolute_timeout=2.0,
            )
        except Exception as error:
            caught = error
    return out.getvalue() + err.getvalue(), caught


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="stage11-hermes-stream-") as temp:
        bin_dir = Path(temp) / "bin"
        bin_dir.mkdir()
        fixture_ssh(bin_dir)

        success_log, success_error = invoke_fixture("success", bin_dir)
        check(success_error is None, "SUCCESS_EXIT_CODE_ZERO_ACCEPTED")
        token = (bin_dir.parent / "diagnostic-token.txt").read_text(
            encoding="ascii"
        )
        expected_stdout = (
            f"STAGE11_SAFE_DIAGNOSTIC:{token}:MODEL_RC=0\n"
            f"STAGE11_SAFE_DIAGNOSTIC:{token}:REMOTE_MODEL_STEP_RESULT=1\n"
        ).encode("ascii") + (
            b"--- review diff\n+PRIVATE_SUBTITLE_BODY_STREAM_SENTINEL\n"
        )
        expected_stderr = b"RAW_HERMES_DIFF_SENTINEL\n"
        check(
            SUBTITLE_SENTINEL not in success_log
            and RAW_DIFF_SENTINEL not in success_log,
            "SUCCESS_RAW_DIFF_ABSENT_FROM_STDOUT_STDERR_AND_EXECUTION_LOG",
        )
        check(
            "HERMES_SAFE_DIAGNOSTIC=MODEL_RC=0" in success_log
            and "HERMES_SAFE_DIAGNOSTIC=REMOTE_MODEL_STEP_RESULT=1"
            in success_log,
            "SUCCESS_SAFE_REMOTE_DIAGNOSTICS_PRESERVED",
        )
        check(
            "HERMES_REMOTE_STDOUT_BYTES=" + str(len(expected_stdout))
            in success_log
            and "HERMES_REMOTE_STDOUT_SHA256="
            + hashlib.sha256(expected_stdout).hexdigest()
            in success_log
            and "HERMES_REMOTE_STDERR_BYTES=" + str(len(expected_stderr))
            in success_log
            and "HERMES_REMOTE_STDERR_SHA256="
            + hashlib.sha256(expected_stderr).hexdigest()
            in success_log,
            "SUCCESS_STREAM_LENGTHS_AND_HASHES_RETAINED",
        )

        error_log, error = invoke_fixture("error", bin_dir)
        if error is not None:
            # The exception is diagnostic output too, so include it in the
            # sentinel assertion without exposing the synthetic response.
            error_log += str(error)
        check(
            error is not None
            and "SSH_EXIT_CODE=1" in str(error)
            and "MODEL_RC=23" in str(error)
            and "REMOTE_MODEL_STEP_RESULT=0" in str(error),
            "ERROR_EXIT_CODE_AND_SAFE_MODEL_ERROR_PROPAGATED",
        )
        check(
            SUBTITLE_SENTINEL not in error_log
            and RAW_DIFF_SENTINEL not in error_log,
            "ERROR_RAW_DIFF_ABSENT_FROM_LOG_AND_EXCEPTION",
        )

        timeout_out = io.StringIO()
        timeout_err = io.StringIO()
        timeout_error = None
        with (
            patch.dict(
                os.environ,
            {
                "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
                "FAKE_HERMES_MODE": "timeout",
                "FAKE_TOKEN_PATH": str(bin_dir.parent / "diagnostic-token.txt"),
            },
            ),
            redirect_stdout(timeout_out),
            redirect_stderr(timeout_err),
            patch.object(
                live_runner,
                "_cleanup_timed_out_remote_hermes",
                lambda **_kwargs: None,
            ),
        ):
            try:
                live_runner._invoke_hermes_part(
                    remote="fixture@offline",
                    ssh_key="/fixture/key",
                    known_hosts="/fixture/known-hosts",
                    remote_task="/fixture/task",
                    session_id="00000000-0000-0000-0000-000000000001",
                    query="synthetic query containing no subtitle body",
                    turn_timeout=0.2,
                    absolute_timeout=2.0,
                )
            except live_runner.StatefulLiveRunnerTimeoutError as caught:
                timeout_error = caught
        timeout_log = timeout_out.getvalue() + timeout_err.getvalue()
        check(
            timeout_error is not None
            and timeout_error.timeout_reason == "INACTIVITY_TIMEOUT",
            "TIMEOUT_DETECTION_REMAINS_ACTIVE",
        )
        check(
            SUBTITLE_SENTINEL not in timeout_log
            and RAW_DIFF_SENTINEL not in timeout_log,
            "TIMEOUT_DRAIN_DOES_NOT_FORWARD_RAW_OUTPUT",
        )

        cleanup_out = io.StringIO()
        cleanup_err = io.StringIO()
        with (
            redirect_stdout(cleanup_out),
            redirect_stderr(cleanup_err),
            patch.object(
                live_runner.subprocess,
                "run",
                return_value=SimpleNamespace(
                    returncode=0,
                    stdout=(
                        b"REMOTE_TIMEOUT_CLEANUP_RESULT=PASS\n"
                        + SUBTITLE_SENTINEL.encode("ascii")
                    ),
                    stderr=RAW_DIFF_SENTINEL.encode("ascii"),
                ),
            ),
        ):
            live_runner._cleanup_timed_out_remote_hermes(
                remote="fixture@offline",
                ssh_key="/fixture/key",
                known_hosts="/fixture/known-hosts",
                remote_task="/fixture/task",
                session_id="00000000-0000-0000-0000-000000000001",
            )
        cleanup_log = cleanup_out.getvalue() + cleanup_err.getvalue()
        check(
            SUBTITLE_SENTINEL not in cleanup_log
            and RAW_DIFF_SENTINEL not in cleanup_log
            and "REMOTE_TIMEOUT_CLEANUP_RESULT=PASS" in cleanup_log,
            "CLEANUP_STREAMS_REDACTED_WITH_SAFE_STATUS",
        )

    print("STATEFUL_LIVE_RUNNER_STREAM_SMOKE=PASS")


if __name__ == "__main__":
    main()
