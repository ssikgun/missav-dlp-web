#!/usr/bin/env python3
"""Plan or sequentially invoke the installed Stage9 existing-image-only runner.

The default mode only reads the checked-in target manifest. Apply mode is an
explicit future production operation and delegates all image work to the pinned
Stage9 runner, exactly one DVD-ID per subprocess.
"""
from __future__ import annotations

import argparse
import datetime
import fcntl
import hashlib
import json
import os
import re
import shlex
import socket
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST = ROOT / "docs/governance/stage9-media/evidence/2026-11-06-existing-image-targets-54.json"
SERVICE = "teddy-stage9-media.service"
TIMER = "teddy-stage9-media.timer"
SERVICE_FRAGMENT = Path("/etc/systemd/system/teddy-stage9-media.service")
CONFIRMATION = "APPLY_STAGE9_EXISTING_IMAGE_BATCH"
EXPECTED_TARGET_COUNT = 54
MANIFEST_SHA256 = "8f72735b4c8b72315e88e0c881c15f2895b3993dd7177089a0cc88ecc27665dd"
EXPECTED_HOST = "downloader"
EXPECTED_HOST_FINGERPRINT = "7e8e75eb061f614c5f239d9e"
EXPECTED_RELEASE = "81be3d80a991a921ce4c82a42a1556f5956be78c"
# The installed executable has not yet been independently attested.
EXPECTED_RUNNER_SHA256 = "9f482f9d85469f1cc069913a5c8044a596324b3388eca4393ae3117011e2f1ad"
APPROVAL_FILE = Path("/etc/teddy-stage9-media-batch-approval.json")
SAFE_ID = re.compile(r"^[A-Z0-9]+(?:-[A-Z0-9]+)+$")
SAFE_ERROR = re.compile(r"^[A-Z0-9_:-]{1,80}$")
DONE = {"COMPLETE", "SKIPPED", "PENDING"}
STOP = {"ATTENTION", "ERROR"}


class BatchError(RuntimeError):
    pass


def verify_manifest(path: Path) -> tuple[list[str], list[str]]:
    if path != DEFAULT_MANIFEST or path.is_symlink():
        raise BatchError("BLOCKED_MANIFEST_PATH")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise BatchError("BLOCKED_MANIFEST_UNREADABLE") from exc
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
        raise BatchError("BLOCKED_MANIFEST_MISMATCH")
    return _parse_targets(raw)


def verify_host(hostname: str, machine_id: str, uid: int) -> None:
    if not re.fullmatch(r"[0-9a-f]{32}", machine_id):
        raise BatchError("BLOCKED_HOST_IDENTITY")
    fingerprint = hashlib.sha256(("stage9-ct108:" + machine_id).encode()).hexdigest()[:24]
    if uid != 0 or hostname != EXPECTED_HOST or fingerprint != EXPECTED_HOST_FINGERPRINT:
        raise BatchError("BLOCKED_HOST_IDENTITY")


def check_host() -> None:
    try:
        machine_id = Path("/etc/machine-id").read_text(encoding="ascii").strip()
    except (OSError, UnicodeError) as exc:
        raise BatchError("BLOCKED_HOST_IDENTITY") from exc
    verify_host(socket.gethostname(), machine_id, os.geteuid())


def verify_runner(base_argv: list[str], release_id: str) -> str:
    if release_id != EXPECTED_RELEASE or not isinstance(EXPECTED_RUNNER_SHA256, str) or not re.fullmatch(r"[0-9a-f]{64}", EXPECTED_RUNNER_SHA256):
        raise BatchError("BLOCKED_RUNNER_IDENTITY_UNVERIFIED")
    runners = [Path(x) for x in base_argv if x.endswith("/teddy_discovery_media_only_runner.py")]
    if len(runners) != 1 or runners[0].is_symlink() or not runners[0].is_file():
        raise BatchError("BLOCKED_RUNNER_IDENTITY_UNVERIFIED")
    try:
        info = runners[0].stat()
        if info.st_uid != 0 or info.st_mode & 0o022:
            raise BatchError("BLOCKED_RUNNER_IDENTITY_UNVERIFIED")
        digest = hashlib.sha256(runners[0].read_bytes()).hexdigest()
    except OSError as exc:
        raise BatchError("BLOCKED_RUNNER_IDENTITY_UNVERIFIED") from exc
    if digest != EXPECTED_RUNNER_SHA256:
        raise BatchError("BLOCKED_RUNNER_IDENTITY_MISMATCH")
    return digest


def plan_identity(targets: list[str], base_argv: list[str], manifest_sha256: str,
                  release_id: str, runner_sha256: str, run_id=None, journal_path=None) -> dict:
    if not re.fullmatch(r"[0-9a-f]{64}", manifest_sha256 or "") or not re.fullmatch(r"[0-9a-f]{40}", release_id or "") or not re.fullmatch(r"[0-9a-f]{64}", runner_sha256 or ""):
        raise BatchError("BLOCKED_PLAN_IDENTITY_MISSING")
    commands = [target_argv(base_argv, dvd_id) for dvd_id in targets]
    argv_hash = hashlib.sha256(json.dumps(commands, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()
    return {"version": 1, "manifest_sha256": manifest_sha256, "targets": targets,
            "release_id": release_id, "runner_sha256": runner_sha256,
            "mode": "thumbnail-only existing-image-only max-items=1", "argv_sha256": argv_hash,
            "run_id": run_id, "journal_path": journal_path}


def load_targets(path: Path) -> tuple[list[str], list[str]]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise BatchError("TARGET_MANIFEST_UNREADABLE") from exc
    return _parse_targets(raw)


def _parse_targets(raw: bytes) -> tuple[list[str], list[str]]:
    try:
        data = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BatchError("TARGET_MANIFEST_UNREADABLE") from exc
    if not isinstance(data, dict) or not isinstance(data.get("target_ids"), list) or not isinstance(data.get("protected_exclusions"), list):
        raise BatchError("TARGET_MANIFEST_INVALID")
    targets, excluded = data["target_ids"], data["protected_exclusions"]
    if any(not isinstance(x, str) or not SAFE_ID.fullmatch(x) for x in targets + excluded):
        raise BatchError("TARGET_ID_INVALID")
    if len(set(targets)) != len(targets) or len(set(excluded)) != len(excluded) or set(targets) & set(excluded):
        raise BatchError("TARGET_MANIFEST_DUPLICATE_OR_PROTECTED")
    if len(targets) != EXPECTED_TARGET_COUNT or not excluded:
        raise BatchError("TARGET_MANIFEST_SCOPE_MISMATCH")
    return targets, excluded


def _systemd_value(unit: str, prop: str, *, run=subprocess.run) -> str:
    result = run(["systemctl", "show", unit, f"--property={prop}", "--value"],
                 stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                 text=True, timeout=10, check=False)
    if result.returncode != 0:
        raise BatchError("SYSTEMD_QUERY_FAILED")
    return result.stdout.strip()


def check_stopped_systemd(*, run=subprocess.run) -> Path:
    if os.geteuid() != 0:
        raise BatchError("ROOT_REQUIRED")
    for unit in (SERVICE, TIMER):
        if _systemd_value(unit, "ActiveState", run=run) != "inactive":
            raise BatchError("STAGE9_UNIT_ACTIVE")
        if _systemd_value(unit, "SubState", run=run) != "dead":
            raise BatchError("STAGE9_UNIT_NOT_DEAD")
    if _systemd_value(SERVICE, "MainPID", run=run) != "0":
        raise BatchError("STAGE9_MAINPID_NONZERO")
    if _systemd_value(SERVICE, "NeedDaemonReload", run=run) != "no":
        raise BatchError("STAGE9_UNIT_RELOAD_PENDING")
    if _systemd_value(SERVICE, "DropInPaths", run=run):
        raise BatchError("STAGE9_UNIT_DROPIN_UNSUPPORTED")
    fragment = Path(_systemd_value(SERVICE, "FragmentPath", run=run))
    if fragment != SERVICE_FRAGMENT or fragment.is_symlink() or not fragment.is_file():
        raise BatchError("STAGE9_UNIT_FRAGMENT_INVALID")
    return fragment


def _service_values(unit_file: Path) -> tuple[Path, list[str]]:
    try:
        raw = unit_file.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise BatchError("STAGE9_UNIT_UNREADABLE") from exc
    logical: list[str] = []
    pending = ""
    for line in raw.splitlines():
        line = pending + line.strip()
        if line.endswith("\\"):
            pending = line[:-1] + " "
            continue
        logical.append(line)
        pending = ""
    if pending:
        raise BatchError("STAGE9_UNIT_CONTINUATION_INVALID")
    section = ""
    workdir = None
    starts = []
    for line in logical:
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
        elif section == "Service" and "=" in line:
            key, value = line.split("=", 1)
            if key == "WorkingDirectory":
                workdir = value.strip()
            elif key == "ExecStart":
                starts.append(value.strip())
    if not workdir or len(starts) != 1:
        raise BatchError("STAGE9_UNIT_EXECSTART_INVALID")
    try:
        argv = shlex.split(starts[0], posix=True)
    except ValueError as exc:
        raise BatchError("STAGE9_UNIT_EXECSTART_INVALID") from exc
    return Path(workdir), argv


def pinned_runner_argv(unit_file: Path, *, run=subprocess.run) -> tuple[list[str], str]:
    workdir, argv = _service_values(unit_file)
    runner = next((Path(x) for x in argv if x.endswith("/teddy_discovery_media_only_runner.py")), None)
    if runner is None or runner.parent != workdir or not runner.is_absolute():
        raise BatchError("STAGE9_RUNNER_PATH_MISMATCH")
    release_id = workdir.name
    if not re.fullmatch(r"[0-9a-f]{40}", release_id):
        raise BatchError("STAGE9_RELEASE_ID_INVALID")
    try:
        if workdir.is_symlink() or not workdir.is_dir() or runner.is_symlink() or not runner.is_file():
            raise BatchError("STAGE9_RELEASE_PATH_INVALID")
        st = workdir.stat()
        if st.st_uid != 0 or st.st_mode & 0o022:
            raise BatchError("STAGE9_RELEASE_OWNERSHIP_INVALID")
    except OSError as exc:
        raise BatchError("STAGE9_RELEASE_PATH_INVALID") from exc
    if _systemd_value(SERVICE, "WorkingDirectory", run=run) != str(workdir):
        raise BatchError("STAGE9_EFFECTIVE_WORKDIR_MISMATCH")
    if "--expected-release-id" not in argv:
        raise BatchError("STAGE9_EXPECTED_RELEASE_MISSING")
    index = argv.index("--expected-release-id")
    if index + 1 >= len(argv) or argv[index + 1] != release_id:
        raise BatchError("STAGE9_EXPECTED_RELEASE_MISMATCH")
    if argv.count("--apply") != 1 or argv.count("--confirm") != 1:
        raise BatchError("STAGE9_APPLY_UNIT_INVALID")
    ci = argv.index("--confirm")
    if ci + 1 >= len(argv) or argv[ci + 1] != "APPLY_STAGE9_MEDIA_ONLY":
        raise BatchError("STAGE9_CONFIRMATION_MISMATCH")
    if "--skip-media" in argv or "--media-only" in argv:
        raise BatchError("STAGE9_UNIT_MODE_UNSUPPORTED")
    if any(x in argv for x in ("--expected-thumbnail-attempt-count", "--canary-image-size", "--canary-image-sha256")):
        raise BatchError("STAGE9_UNIT_THUMBNAIL_GUARD_UNSUPPORTED")
    if argv.count("--expected-release-id") != 1:
        raise BatchError("STAGE9_EXPECTED_RELEASE_INVALID")
    if "--max-items" in argv:
        mi = argv.index("--max-items")
        if mi + 1 >= len(argv) or argv[mi + 1] != "1":
            raise BatchError("STAGE9_UNIT_ITEM_LIMIT_UNSAFE")
    return argv, release_id


def target_argv(base: list[str], dvd_id: str) -> list[str]:
    """Derive one exact-target invocation from the pinned service command."""
    out: list[str] = []
    i = 0
    while i < len(base):
        arg = base[i]
        if arg in {"--target-dvd-id", "--max-items"}:
            i += 2
            continue
        if arg in {"--thumbnail-only", "--existing-image-only"}:
            i += 1
            continue
        out.append(arg)
        i += 1
    out.extend(["--target-dvd-id", dvd_id, "--max-items", "1", "--thumbnail-only", "--existing-image-only"])
    if out.count("--max-items") != 1 or out[out.index("--max-items") + 1] != "1":
        raise BatchError("RUNNER_ITEM_LIMIT_UNSAFE")
    if out.count("--target-dvd-id") != 1 or out[out.index("--target-dvd-id") + 1] != dvd_id:
        raise BatchError("RUNNER_TARGET_MISMATCH")
    return out


def prepare_plan(manifest_path: Path) -> tuple[list[str], list[str], dict]:
    """Validate future run inputs; this function does not grant approval."""
    targets, _ = verify_manifest(manifest_path)
    check_host()
    unit = check_stopped_systemd()
    base, release = pinned_runner_argv(unit)
    runner_hash = verify_runner(base, release)
    return targets, base, plan_identity(targets, base, MANIFEST_SHA256, release, runner_hash)


def read_approval(path: Path) -> dict:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise BatchError("BLOCKED_NO_APPROVAL") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1 or info.st_size > 8192:
            raise BatchError("BLOCKED_APPROVAL_UNSAFE")
        with os.fdopen(os.dup(fd), "r", encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BatchError("BLOCKED_APPROVAL_INVALID") from exc
    finally:
        os.close(fd)


def validate_approval(record: dict, plan: dict, journal: Path) -> dict:
    if not isinstance(record, dict) or not isinstance(record.get("run_id"), str) or not re.fullmatch(r"[a-zA-Z0-9_-]{16,64}", record["run_id"]):
        raise BatchError("BLOCKED_APPROVAL_INVALID")
    if not journal.is_absolute() or str(journal) != str(journal.resolve()):
        raise BatchError("BLOCKED_JOURNAL_PATH")
    try:
        expires = datetime.datetime.fromisoformat(record["expires_utc"].replace("Z", "+00:00"))
        if expires.tzinfo is None or expires <= datetime.datetime.now(datetime.timezone.utc):
            raise ValueError("expired")
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise BatchError("BLOCKED_APPROVAL_EXPIRED") from exc
    bound = dict(plan, run_id=record["run_id"], journal_path=str(journal))
    if record != {"scope": "STG9MEDIA-001-existing-image-54", "authorizer": "Teddy", "host_fingerprint": EXPECTED_HOST_FINGERPRINT, "run_id": record["run_id"], "expires_utc": record["expires_utc"], "plan": bound}:
        raise BatchError("BLOCKED_APPROVAL_MISMATCH")
    return bound


def _result_status(returncode: int, stdout: str, expected_id: str) -> tuple[str, str]:
    try:
        result = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return "ERROR", "RUNNER_OUTPUT_INVALID"
    if isinstance(result, dict) and result.get("status") == "ERROR":
        error = result.get("error")
        return "ERROR", error if isinstance(error, str) and SAFE_ERROR.fullmatch(error) else "RUNNER_FAILED"
    if not isinstance(result, dict) or result.get("target_dvd_id") != expected_id:
        return "ERROR", "RUNNER_TARGET_RESULT_MISMATCH"
    if result.get("stage") != "stage9-existing-image-only":
        return "ERROR", "RUNNER_STAGE_MISMATCH"
    if any(result.get(k) != 0 for k in ("non_media_execution", "jellyfin_get_requests", "jellyfin_post_attempts", "media_database_writes")):
        return "ERROR", "RUNNER_SCOPE_MISMATCH"
    image = result.get("image")
    image_status = image.get("status") if isinstance(image, dict) else None
    if image_status == "ATTENTION":
        if result.get("status") != "PARTIAL_FAILURE":
            return "ERROR", "RUNNER_STATUS_MISMATCH"
        error = image.get("error", "IMAGE_ATTENTION")
        return "ATTENTION", error if isinstance(error, str) and SAFE_ERROR.fullmatch(error) else "IMAGE_ATTENTION"
    expected_status = "PENDING" if image_status == "PENDING" else "COMPLETE"
    if result.get("status") != expected_status:
        return "ERROR", "RUNNER_STATUS_MISMATCH"
    if returncode != 0:
        return "ERROR", "RUNNER_EXIT_NONZERO"
    if image_status not in {"COMPLETE", "SKIPPED", "PENDING", "ATTENTION"}:
        return "ERROR", "RUNNER_IMAGE_STATUS_INVALID"
    return image_status, ""


def _append_journal(fd: int, dvd_id: str, status: str, detail: str = "") -> None:
    line = json.dumps({"dvd_id": dvd_id, "status": status, "detail": detail[:100]}, separators=(",", ":")) + "\n"
    os.write(fd, line.encode("utf-8"))
    os.fsync(fd)


def _journal_state(path: Path, targets: list[str], identity: dict, *, resume: bool) -> tuple[int, dict[str, str]]:
    states: dict[str, str] = {}
    if not identity or identity.get("version") != 1 or identity.get("targets") != targets:
        raise BatchError("BLOCKED_PLAN_IDENTITY_MISSING")
    if path.parent.is_symlink() or not path.parent.is_dir() or path.parent.resolve() != path.parent.absolute():
        raise BatchError("JOURNAL_PARENT_INVALID")
    if resume:
        if path.is_symlink() or not path.is_file():
            raise BatchError("RESUME_JOURNAL_INVALID")
        try:
            fd = os.open(path, os.O_RDWR | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0))
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                os.close(fd)
                raise BatchError("RESUME_JOURNAL_UNSAFE")
        except OSError as exc:
            raise BatchError("RESUME_JOURNAL_INVALID") from exc
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            raise BatchError("JOURNAL_LOCK_UNAVAILABLE") from exc
        try:
            with os.fdopen(os.dup(fd), "r", encoding="utf-8") as stream:
                lines = stream.read().splitlines()
            if not lines or json.loads(lines[0]) != {"plan": identity}:
                raise BatchError("BLOCKED_JOURNAL_PLAN_MISMATCH")
            for line in lines[1:]:
                row = json.loads(line)
                dvd_id, status = row["dvd_id"], row["status"]
                if dvd_id not in targets or status not in DONE | STOP | {"RUNNING"}:
                    raise BatchError("RESUME_JOURNAL_INVALID")
                states[dvd_id] = status
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, BatchError) as exc:
            os.close(fd)
            if isinstance(exc, BatchError):
                raise
            raise BatchError("RESUME_JOURNAL_INVALID") from exc
        return fd, states
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except OSError as exc:
        raise BatchError("JOURNAL_CREATE_FAILED") from exc
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        os.close(fd)
        raise BatchError("JOURNAL_UNSAFE")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        os.close(fd)
        raise BatchError("JOURNAL_LOCK_UNAVAILABLE") from exc
    try:
        header = json.dumps({"plan": identity}, separators=(",", ":")) + "\n"
        with os.fdopen(os.dup(fd), "w", encoding="utf-8") as stream:
            stream.write(header)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError:
        os.close(fd)
        raise
    return fd, states


def run_sequential(targets: list[str], base_argv: list[str], journal: Path, *, identity: dict, invoke, preflight, resume=False) -> dict:
    try:
        expected = plan_identity(targets, base_argv, identity["manifest_sha256"], identity["release_id"], identity["runner_sha256"], identity.get("run_id"), identity.get("journal_path"))
    except (KeyError, TypeError) as exc:
        raise BatchError("BLOCKED_PLAN_IDENTITY_MISSING") from exc
    if identity != expected:
        raise BatchError("BLOCKED_PLAN_IDENTITY_MISMATCH")
    fd, states = _journal_state(journal, targets, identity, resume=resume)
    attempted = []
    try:
        for dvd_id in targets:
            previous = states.get(dvd_id)
            if previous in DONE:
                continue
            if previous is not None:
                return {"status": "HOLD", "stopped_at": dvd_id, "reason": "JOURNAL_REQUIRES_REVIEW", "attempted": attempted}
            preflight()
            _append_journal(fd, dvd_id, "RUNNING")
            states[dvd_id] = "RUNNING"
            attempted.append(dvd_id)
            try:
                completed = invoke(target_argv(base_argv, dvd_id), dvd_id)
                status, detail = _result_status(completed.returncode, completed.stdout, dvd_id)
            except (OSError, subprocess.TimeoutExpired, BatchError):
                status, detail = "ERROR", "RUNNER_EXECUTION_FAILED"
            _append_journal(fd, dvd_id, status, detail)
            states[dvd_id] = status
            if status in STOP:
                return {"status": "STOPPED", "stopped_at": dvd_id, "reason": status, "attempted": attempted}
        return {"status": "COMPLETE_PLAN", "attempted": attempted, "resumed_skipped": [x for x in targets if states.get(x) in DONE and x not in attempted]}
    finally:
        os.close(fd)


def _invoke(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, text=True, timeout=240, check=False)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets-file", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--apply", action="store_true", help="Run exact-target existing-image-only operations; requires explicit confirmation.")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--journal", type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.apply:
            approval = read_approval(APPROVAL_FILE)
            if args.journal is None:
                raise BatchError("BLOCKED_JOURNAL_PATH")
            targets, base, plan = prepare_plan(args.targets_file)
            bound = validate_approval(approval, plan, args.journal)
            def preflight():
                current_targets, current_base, current_plan = prepare_plan(args.targets_file)
                current_approval = read_approval(APPROVAL_FILE)
                if current_targets != targets or current_base != base or validate_approval(current_approval, current_plan, args.journal) != bound:
                    raise BatchError("BLOCKED_PLAN_CHANGED")
            result = run_sequential(targets, base, args.journal, identity=bound,
                                    invoke=lambda command, _dvd: _invoke(command),
                                    preflight=preflight, resume=args.resume)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0 if result["status"] == "COMPLETE_PLAN" else 2
        targets, exclusions = load_targets(args.targets_file)
        if not args.apply:
            print(json.dumps({"mode": "PLAN", "count": len(targets), "protected_exclusions": exclusions,
                              "targets": targets, "runner_invocations": 0}, ensure_ascii=False, sort_keys=True))
            return 0
    except BatchError as exc:
        print(json.dumps({"status": "HOLD", "error": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
