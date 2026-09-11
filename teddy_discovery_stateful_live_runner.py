"""Generic one-invocation live runner for Stage11 stateful translation."""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from teddy_discovery_stateful_controller import (
    COMPLETE,
    PROMOTE_PENDING,
    REQUEST_PART,
    build_stateful_part_query,
    decide_stateful_controller_step,
)
from teddy_discovery_stateful_parts import (
    build_stateful_part_plan,
    parse_stateful_part,
    promote_pending_part,
    assemble_stateful_result,
)
from teddy_discovery_stateful_translator import (
    parse_stateful_package,
    parse_stateful_result,
    serialize_stateful_result,
)


class StatefulLiveRunnerError(RuntimeError):
    pass


def _require_absolute_remote_task(value: str) -> str:
    if (
        type(value) is not str
        or not value.startswith("/")
        or "\x00" in value
        or "\n" in value
        or "\r" in value
    ):
        raise StatefulLiveRunnerError(
            "remote task path must be an absolute safe path"
        )
    return value


def validate_stateful_remote_task_path(value: str) -> str:
    """Expose the native remote-task path validator to deployment adapters."""

    return _require_absolute_remote_task(value)


def _ssh_base(
    remote: str,
    ssh_key: str,
    known_hosts: str,
) -> list[str]:
    return [
        "ssh",
        "-i", ssh_key,
        "-o", "IdentitiesOnly=yes",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "UserKnownHostsFile=" + known_hosts,
        remote,
    ]


def build_stateful_ssh_argv(
    remote: str,
    ssh_key: str,
    known_hosts: str,
) -> list[str]:
    """Expose the native SSH argument construction without changing it."""

    return _ssh_base(remote, ssh_key, known_hosts)


def _remote_input_sha256(
    *,
    remote: str,
    ssh_key: str,
    known_hosts: str,
    remote_input: str,
) -> str:
    script = (
        "import hashlib,os,stat,sys;"
        "p=sys.argv[1];"
        "s=os.lstat(p);"
        "assert stat.S_ISREG(s.st_mode) and not stat.S_ISLNK(s.st_mode);"
        "print(hashlib.sha256(open(p,'rb').read()).hexdigest())"
    )

    command = (
        "python3 -c "
        + shlex.quote(script)
        + " "
        + shlex.quote(remote_input)
    )

    result = subprocess.run(
        _ssh_base(
            remote,
            ssh_key,
            known_hosts,
        ) + [command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise StatefulLiveRunnerError(
            "remote semantic input could not be verified: "
            + result.stderr.strip()
        )

    value = result.stdout.strip()

    if len(value) != 64:
        raise StatefulLiveRunnerError(
            "remote semantic input hash is invalid"
        )

    return value


def _remote_pending_status(
    *,
    remote: str,
    ssh_key: str,
    known_hosts: str,
    path: str,
) -> bool:
    script = """
import os
import stat
import sys

path = sys.argv[1]

try:
    value = os.lstat(path)
except FileNotFoundError:
    print("MISSING")
else:
    if stat.S_ISLNK(value.st_mode):
        raise SystemExit("REMOTE_PENDING_IS_SYMLINK")
    if not stat.S_ISREG(value.st_mode):
        raise SystemExit("REMOTE_PENDING_NOT_REGULAR")
    print("PRESENT")
"""

    command = (
        "python3 -c "
        + shlex.quote(script)
        + " "
        + shlex.quote(path)
    )

    result = subprocess.run(
        _ssh_base(
            remote,
            ssh_key,
            known_hosts,
        ) + [command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise StatefulLiveRunnerError(
            "remote pending status failed: "
            + result.stderr.strip()
        )

    value = result.stdout.strip()

    if value == "PRESENT":
        return True

    if value == "MISSING":
        return False

    raise StatefulLiveRunnerError(
        "unexpected remote pending status"
    )


def _read_remote_regular_file(
    *,
    remote: str,
    ssh_key: str,
    known_hosts: str,
    path: str,
) -> bytes:
    script = """
import os
import stat
import sys

path = sys.argv[1]
value = os.lstat(path)

if stat.S_ISLNK(value.st_mode):
    raise SystemExit("REMOTE_FILE_IS_SYMLINK")

if not stat.S_ISREG(value.st_mode):
    raise SystemExit("REMOTE_FILE_NOT_REGULAR")

with open(path, "rb") as handle:
    sys.stdout.buffer.write(handle.read())
"""

    command = (
        "python3 -c "
        + shlex.quote(script)
        + " "
        + shlex.quote(path)
    )

    result = subprocess.run(
        _ssh_base(
            remote,
            ssh_key,
            known_hosts,
        ) + [command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    if result.returncode != 0:
        raise StatefulLiveRunnerError(
            "remote part read failed: "
            + result.stderr.decode(
                "utf-8",
                errors="replace",
            ).strip()
        )

    return result.stdout


def _invoke_hermes_part(
    *,
    remote: str,
    ssh_key: str,
    known_hosts: str,
    remote_task: str,
    session_id: str,
    query: str,
    turn_timeout: int,
) -> None:
    encoded_query = base64.b64encode(
        query.encode("utf-8")
    ).decode("ascii")

    remote_script = """
SID="$1"
TASK="$2"
QUERY_B64="$3"

rok=1

if [ "$(hostname)" != "hermes-lxc-slack" ]; then
  echo "WRONG_REMOTE_HOST=$(hostname)"
  rok=0
fi

if [ "$rok" -eq 1 ]; then
  QUERY="$(
    printf '%s' "$QUERY_B64" |
      base64 -d
  )"

  DECODE_RC=$?

  if [ "$DECODE_RC" -ne 0 ]; then
    echo "QUERY_DECODE_FAILED=YES"
    rok=0
  fi
fi

if [ "$rok" -eq 1 ]; then
  if [ ! -d "$TASK" ]; then
    echo "REMOTE_TASK_MISSING=YES"
    rok=0
  fi
fi

if [ "$rok" -eq 1 ]; then
  cd "$TASK" || rok=0
fi

if [ "$rok" -eq 1 ]; then
  "$HOME/.local/bin/hermes" \
    --profile subtitle-translator \
    chat \
    -Q \
    --pass-session-id \
    --resume "$SID" \
    --provider openai-codex \
    --model gpt-5.6-luna \
    --reasoning xhigh \
    -q "$QUERY"

  MODEL_RC=$?

  echo
  echo "MODEL_RC=$MODEL_RC"

  [ "$MODEL_RC" -eq 0 ] || rok=0
fi

echo "REMOTE_MODEL_STEP_RESULT=$rok"
test "$rok" -eq 1
"""

    command = _ssh_base(
        remote,
        ssh_key,
        known_hosts,
    ) + [
        "bash",
        "-s",
        "--",
        session_id,
        remote_task,
        encoded_query,
    ]

    try:
        result = subprocess.run(
            command,
            input=remote_script.encode("utf-8"),
            check=False,
            timeout=turn_timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise StatefulLiveRunnerError(
            "Hermes part invocation exceeded controller timeout"
        ) from error

    if result.returncode != 0:
        raise StatefulLiveRunnerError(
            "Hermes part invocation failed"
        )


def _install_validated_pending(
    *,
    task_directory: Path,
    payload: bytes,
    plan,
    expected,
) -> None:
    parse_stateful_part(
        payload,
        expected,
        plan,
    )

    pending_path = (
        task_directory
        / expected.pending_filename
    )

    if pending_path.exists() or pending_path.is_symlink():
        raise StatefulLiveRunnerError(
            "local pending target already exists"
        )

    fd, temporary_name = tempfile.mkstemp(
        dir=task_directory,
        prefix=".stage11-part-incoming-",
    )

    temporary = Path(temporary_name)

    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

        os.chmod(temporary, 0o600)

        try:
            os.link(
                temporary,
                pending_path,
                follow_symlinks=False,
            )
        except FileExistsError as error:
            raise StatefulLiveRunnerError(
                "pending target appeared during atomic install"
            ) from error

        directory_fd = os.open(
            task_directory,
            os.O_RDONLY,
        )

        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _write_final_result(
    *,
    final_path: Path,
    payload: bytes,
) -> None:
    if final_path.exists() or final_path.is_symlink():
        raise StatefulLiveRunnerError(
            "final result already exists"
        )

    final_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fd, temporary_name = tempfile.mkstemp(
        dir=final_path.parent,
        prefix=".stage11-final-incoming-",
    )

    temporary = Path(temporary_name)

    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

        os.chmod(temporary, 0o600)

        try:
            os.link(
                temporary,
                final_path,
                follow_symlinks=False,
            )
        except FileExistsError as error:
            raise StatefulLiveRunnerError(
                "final result appeared during atomic install"
            ) from error

    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def run(args: argparse.Namespace) -> int:
    package_path = Path(args.package)
    task_directory = Path(args.task_directory)
    final_path = Path(args.final_result)

    remote_task = _require_absolute_remote_task(
        args.remote_task
    )

    semantic_input_bytes = package_path.read_bytes()

    package = parse_stateful_package(
        semantic_input_bytes
    )

    plan = build_stateful_part_plan(
        package,
        semantic_input_bytes,
    )

    if not task_directory.exists():
        task_directory.mkdir(
            parents=True,
            mode=0o700,
        )

    os.chmod(
        task_directory,
        0o700,
    )

    remote_input = (
        remote_task
        + "/stage11-semantic-input.json"
    )

    remote_sha = _remote_input_sha256(
        remote=args.remote,
        ssh_key=args.ssh_key,
        known_hosts=args.known_hosts,
        remote_input=remote_input,
    )

    if remote_sha != plan.input_sha256:
        raise StatefulLiveRunnerError(
            "remote semantic input hash does not match deterministic plan"
        )

    print("DVD_ID=" + package.dvd_id)
    print("SESSION_ID=" + plan.session_id)
    print("CUE_COUNT=" + str(len(package.cues)))
    print("PART_COUNT=" + str(plan.part_count))
    print("INPUT_SHA256=" + plan.input_sha256)
    print()

    while True:
        decision = decide_stateful_controller_step(
            task_directory,
            package,
            semantic_input_bytes,
        )

        print(
            "CONTROLLER_ACTION="
            + decision.action
        )

        if decision.action == COMPLETE:
            result = assemble_stateful_result(
                task_directory,
                package,
                plan,
            )

            payload = serialize_stateful_result(
                result
            )

            parse_stateful_result(
                payload,
                package,
            )

            if final_path.exists():
                existing = final_path.read_bytes()

                parsed = parse_stateful_result(
                    existing,
                    package,
                )

                existing_canonical = (
                    serialize_stateful_result(
                        parsed
                    )
                )

                if existing_canonical != payload:
                    raise StatefulLiveRunnerError(
                        "existing final result conflicts with assembled result"
                    )

                print(
                    "FINAL_RESULT_ALREADY_VALID=YES"
                )

            else:
                _write_final_result(
                    final_path=final_path,
                    payload=payload,
                )

                print(
                    "FINAL_RESULT_WRITTEN=YES"
                )

            print(
                "FINAL_RESULT_SHA256="
                + hashlib.sha256(
                    payload
                ).hexdigest()
            )

            print(
                "FINAL_CUE_COUNT="
                + str(len(result.cues))
            )

            print(
                "STATEFUL_LIVE_RUN_COMPLETE=YES"
            )

            return 0

        if decision.part_index is None:
            raise StatefulLiveRunnerError(
                "controller returned an action without a part index"
            )

        expected = plan.parts[
            decision.part_index - 1
        ]

        if decision.action == PROMOTE_PENDING:
            promoted = promote_pending_part(
                task_directory,
                plan,
                decision.part_index,
            )

            print(
                "PROMOTED_PART="
                + str(promoted.part_index)
                + "/"
                + str(plan.part_count)
            )

            continue

        if decision.action != REQUEST_PART:
            raise StatefulLiveRunnerError(
                "unknown controller action"
            )

        remote_pending = (
            remote_task
            + "/"
            + expected.pending_filename
        )

        remote_has_pending = (
            _remote_pending_status(
                remote=args.remote,
                ssh_key=args.ssh_key,
                known_hosts=args.known_hosts,
                path=remote_pending,
            )
        )

        if remote_has_pending:
            print(
                "REMOTE_PENDING_RECOVERY="
                + str(expected.part_index)
            )

        else:
            query = build_stateful_part_query(
                package,
                semantic_input_bytes,
                expected.part_index,
            )

            print(
                "REQUESTING_PART="
                + str(expected.part_index)
                + "/"
                + str(plan.part_count)
                + "|FIRST="
                + expected.first_cue_id
                + "|LAST="
                + expected.last_cue_id
            )

            _invoke_hermes_part(
                remote=args.remote,
                ssh_key=args.ssh_key,
                known_hosts=args.known_hosts,
                remote_task=remote_task,
                session_id=plan.session_id,
                query=query,
                turn_timeout=args.turn_timeout,
            )

        payload = _read_remote_regular_file(
            remote=args.remote,
            ssh_key=args.ssh_key,
            known_hosts=args.known_hosts,
            path=remote_pending,
        )

        _install_validated_pending(
            task_directory=task_directory,
            payload=payload,
            plan=plan,
            expected=expected,
        )

        print(
            "VALIDATED_PENDING_PART="
            + str(expected.part_index)
        )

        promoted = promote_pending_part(
            task_directory,
            plan,
            expected.part_index,
        )

        print(
            "PROMOTED_PART="
            + str(promoted.part_index)
            + "/"
            + str(plan.part_count)
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--package",
        required=True,
    )

    parser.add_argument(
        "--task-directory",
        required=True,
    )

    parser.add_argument(
        "--final-result",
        required=True,
    )

    parser.add_argument(
        "--remote",
        required=True,
    )

    parser.add_argument(
        "--remote-task",
        required=True,
    )

    parser.add_argument(
        "--ssh-key",
        required=True,
    )

    parser.add_argument(
        "--known-hosts",
        required=True,
    )

    parser.add_argument(
        "--turn-timeout",
        type=int,
        default=600,
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.turn_timeout <= 0:
        raise StatefulLiveRunnerError(
            "turn timeout must be positive"
        )

    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
