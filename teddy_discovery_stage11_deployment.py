"""Deployment-owned wiring for the generic Stage11 live adapters.

This module owns connection values and the small bridges which connect the
already validated Stage11 components.  It does not add a pipeline, a request
schema, a classifier, or a publication boundary.  Importing it performs no
network, process, media, or database operation; those operations are reached
only through the returned injected callables.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import shlex
import stat
import subprocess
import time
from types import SimpleNamespace
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import quote, urlsplit, urlunsplit

from teddy_discovery_alignment_application import (
    AlignmentAcceptanceApplicationResult,
)
from teddy_discovery_asr_artifact import serialize_asr_result
from teddy_discovery_asr_audio import iter_audio_chunks
from teddy_discovery_asr_source import (
    ASRMediaSourceReader,
    ASR_MEDIA_TEMP_RESERVE_BYTES,
)
from teddy_discovery_quality_review_session import (
    QualityReviewSessionError,
    validate_canonical_review_execution_session_id,
)
from teddy_discovery_stage11_live_adapters import (
    Stage11LiveDependencies,
    build_stage11_live_dependencies,
)
from teddy_discovery_stateful_asr_quality_review_direct_runner import (
    REMOTE_HERMES_PROFILE,
    REMOTE_HERMES_PROFILE_NAME,
    REMOTE_HERMES_PYTHON,
    REMOTE_HERMES_SOURCE,
)
from teddy_discovery_stateful_live_runner import (
    build_stateful_ssh_argv,
    run as native_stateful_run,
    validate_stateful_remote_task_path,
)
from teddy_discovery_stateful_quality_review import (
    QualityReviewRequest,
    build_review_request,
)
from teddy_discovery_stateful_quality_review_runner import (
    QUALITY_REVIEW_INPUT_FILENAME,
    QUALITY_REVIEW_RESULT_FILENAME,
    QUALITY_REVIEW_REMOTE_EXECUTION_TIMEOUT_SECONDS,
    QUALITY_REVIEW_TRANSPORT_TIMEOUT_SECONDS,
    validate_remote_execution_receipt,
)
from teddy_discovery_stateful_hybrid import prepare_stateful_hybrid
from teddy_discovery_stateful_translator import (
    STATEFUL_TRANSLATOR_INPUT_FILENAME,
    STATEFUL_TRANSLATOR_PRIVATE_FILE_MODE,
    STATEFUL_TRANSLATOR_SESSION_SOURCE,
    build_stateful_model_input_package,
    serialize_stateful_model_input,
    stateful_model_input_identity_is_bound,
    stateful_session_id_for_package,
    validate_stateful_result,
)
from teddy_discovery_stage11_hermes_profile import (
    HermesProfileSettingsError,
    REMOTE_PROFILE_SETTINGS_PROBE,
    STAGE11_HERMES_CONFIG_PATH,
    STAGE11_HERMES_PROFILE,
    STAGE11_HERMES_TIMEOUT_ENV,
    STAGE11_HERMES_TIMEOUT_ENV_NAMES,
    settings_from_probe,
    validate_settings_evidence,
)
from teddy_discovery_subtitle_external import (
    ExternalSubtitleTransport,
    ExternalSubtitleTransportError,
    SubtitleCatDetailError,
    SubtitleCatDetailPage,
    SubtitleCatProvider,
    MAX_SUBTITLECAT_DETAIL_HTML_BYTES,
    annotate_external_subtitle_error,
)
from teddy_discovery_subtitle_text import MAX_SUBTITLE_BYTES
from teddy_discovery_subtitle_source_quality import classify_source_document
from teddy_discovery_subtitlecat_discovery import (
    SubtitleCatDiscovery,
    SubtitleCatSearchError,
    validate_subtitlecat_proxy_url,
)
from teddy_discovery_subtitle_v2_orchestrator import (
    V2_READY_FOR_SEMANTIC,
    V2_ROUTE_HYBRID,
    SubtitleV2RouteDecision,
)
from teddy_discovery_targeted_second_evidence_artifact import (
    TargetedSecondEvidenceArtifact,
    targeted_second_evidence_artifact_from_execution,
)


STAGE11_STANDALONE_CANARY_CLAIM_TOKEN = 1
"""The explicit claim token reserved for the first standalone canary."""


class Stage11DeploymentError(RuntimeError):
    """A deployment-owned connection or evidence bridge failed closed."""


class Stage11DeploymentValidationError(Stage11DeploymentError):
    """A deployment value or caller-held evidence is invalid or detached."""


class Stage11DeploymentTransportError(Stage11DeploymentError):
    """A narrow process or network transport boundary failed."""


QUALITY_REVIEW_CLEANUP_GRACE_SECONDS = 30.0
QUALITY_REVIEW_STATUS_POLL_SECONDS = 10
QUALITY_REVIEW_REMOTE_CALL_TIMEOUT_SECONDS = 30


# This standard-library-only program runs on CT120.  A detached supervisor
# owns one review CLI process group, writes an immutable completion receipt,
# and survives loss of the initiating SSH connection.  Its status action is
# strictly read-only.  The script deliberately emits no command, path, or
# Hermes output data.
_REMOTE_QUALITY_REVIEW_EXECUTION_SCRIPT_TEMPLATE = r'''import hashlib, json, os, signal, stat, subprocess, sys, time, uuid
ACTION, TASK, SESSION, REQUEST_SHA = sys.argv[1:5]
COMMAND_SHA = sys.argv[5] if len(sys.argv) > 5 else ""
INPUT_NAME = "stage11-quality-review-input.json"
RESULT_NAME = "stage11-quality-review-result.json"
COMMAND_NAME = ".stage11-quality-review-command-v1.json"
CLAIM_NAME = ".stage11-quality-review-claim-v1.json"
MANAGER_NAME = ".stage11-quality-review-manager-v1.json"
CHILD_NAME = ".stage11-quality-review-child-v1.json"
RECEIPT_NAME = "stage11-quality-review-execution-v1.json"
APPROVED_TIMEOUT_ENV = {
    "HERMES_API_CALL_STALE_TIMEOUT": "480",
    "HERMES_CODEX_TTFB_TIMEOUT_SECONDS": "300",
    "HERMES_CODEX_TTFB_MAX_SECONDS": "300",
    "HERMES_CODEX_EVENT_STALE_TIMEOUT_SECONDS": "300",
}
EXECUTION_LIMIT = __EXECUTION_LIMIT__
CLEANUP_GRACE = __CLEANUP_GRACE__
RECEIPT_SCHEMA = 1

def stop(code):
    raise SystemExit(code)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def encode(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")

def check_identity():
    try:
        uuid.UUID(SESSION)
        if str(uuid.UUID(SESSION)) != SESSION:
            stop(20)
    except (ValueError, AttributeError):
        stop(20)
    if (len(REQUEST_SHA) != 64 or
            any(ch not in "0123456789abcdef" for ch in REQUEST_SHA)):
        stop(21)

def open_task():
    try:
        info = os.lstat(TASK)
        if (stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            stop(22)
        return os.open(TASK, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        stop(22)

def read_private(fd, name, bound):
    try:
        handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
        with os.fdopen(handle, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600
                    or not 0 < info.st_size <= bound):
                stop(23)
            data = stream.read(bound + 1)
            if len(data) != info.st_size or len(data) > bound:
                stop(23)
            return data
    except OSError:
        stop(23)

def read_json(fd, name, bound):
    try:
        value = json.loads(read_private(fd, name, bound).decode("ascii"))
    except (ValueError, UnicodeError):
        stop(24)
    if type(value) is not dict:
        stop(24)
    return value

def absent(fd, name):
    try:
        os.stat(name, dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        return True
    except OSError:
        stop(25)
    return False

def write_once(fd, name, data):
    handle = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=fd)
    try:
        os.fchmod(handle, 0o600)
        with os.fdopen(handle, "wb") as stream:
            handle = None
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if handle is not None:
            os.close(handle)
    os.fsync(fd)

def write_final(fd, receipt):
    data = encode(receipt)
    temporary = ".stage11-review-receipt-" + str(os.getpid()) + "-" + uuid.uuid4().hex + ".tmp"
    write_once(fd, temporary, data)
    try:
        os.link(temporary, RECEIPT_NAME, src_dir_fd=fd, dst_dir_fd=fd,
                follow_symlinks=False)
        os.fsync(fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=fd)
            os.fsync(fd)
        except FileNotFoundError:
            pass

def proc_info(pid):
    base = "/proc/" + str(pid)
    try:
        raw = open(base + "/stat", "rb").read()
        end = raw.rfind(b")")
        if end < 0:
            return None
        fields = raw[end + 2:].split()
        status = open(base + "/status", "rb").read().splitlines()
        uid_line = next(line for line in status if line.startswith(b"Uid:"))
        uid = int(uid_line.split()[2])
        cmdline = open(base + "/cmdline", "rb").read()
        cwd = os.readlink(base + "/cwd")
        return {
            "pid": pid,
            "state": fields[0].decode("ascii"),
            "pgrp": int(fields[2]), "session": int(fields[3]),
            "start_ticks": int(fields[19]), "uid": uid,
            "cmdline_sha256": digest(cmdline), "cwd": cwd,
        }
    except (OSError, StopIteration, ValueError, IndexError):
        return None

def group_members(pgrp, session, uid):
    members = []
    try:
        pids = [int(item) for item in os.listdir("/proc") if item.isdigit()]
    except OSError:
        return None
    for pid in pids:
        info = proc_info(pid)
        if info is None or info["pgrp"] != pgrp:
            continue
        if info["session"] != session or info["uid"] != uid:
            return None
        if info["state"] != "Z":
            members.append({
                "pid": pid, "start_ticks": info["start_ticks"],
                "uid": info["uid"], "pgrp": info["pgrp"],
                "session": info["session"],
            })
    return members

def signal_owned_members(members, pgrp, session, uid, sig):
    if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
        return False
    for member in members:
        pid = member["pid"]
        descriptor = None
        try:
            descriptor = os.pidfd_open(pid, 0)
            current = proc_info(pid)
            if current is None:
                continue
            if any(current.get(key) != member.get(key) for key in
                    ("pid", "start_ticks", "uid", "pgrp", "session")):
                return False
            if (current["pgrp"] != pgrp or current["session"] != session
                    or current["uid"] != uid):
                return False
            signal.pidfd_send_signal(descriptor, sig, None, 0)
        except ProcessLookupError:
            continue
        except OSError:
            return False
        finally:
            if descriptor is not None:
                os.close(descriptor)
    return True

def verify_child(info, expected):
    return bool(info and all(info.get(key) == expected.get(key) for key in
        ("pid", "start_ticks", "uid", "pgrp", "session", "cmdline_sha256", "cwd")))

def cleanup_group(process, identity):
    pid, pgrp, session, uid = (identity["pid"], identity["pgrp"],
                               identity["session"], identity["uid"])
    current = proc_info(pid)
    if current is not None and not verify_child(current, identity):
        return False
    members = group_members(pgrp, session, uid)
    if members is None:
        return False
    if members:
        if not signal_owned_members(members, pgrp, session, uid, signal.SIGTERM):
            return False
    deadline = time.monotonic() + CLEANUP_GRACE
    while time.monotonic() < deadline:
        if process.poll() is None:
            try:
                process.wait(timeout=min(0.1, max(0.01, deadline-time.monotonic())))
            except subprocess.TimeoutExpired:
                pass
        members = group_members(pgrp, session, uid)
        if members == []:
            break
        if members is None:
            return False
        time.sleep(0.05)
    members = group_members(pgrp, session, uid)
    if members is None:
        return False
    if members:
        if not signal_owned_members(members, pgrp, session, uid, signal.SIGKILL):
            return False
        deadline = time.monotonic() + CLEANUP_GRACE
        while time.monotonic() < deadline:
            if process.poll() is None:
                try:
                    process.wait(timeout=min(0.1, max(0.01, deadline-time.monotonic())))
                except subprocess.TimeoutExpired:
                    pass
            members = group_members(pgrp, session, uid)
            if members == []:
                break
            if members is None:
                return False
            time.sleep(0.05)
    try:
        if process.poll() is None:
            process.wait(timeout=max(0.01, CLEANUP_GRACE))
    except subprocess.TimeoutExpired:
        return False
    return group_members(pgrp, session, uid) == [] and process.returncode is not None

def stop_direct_child_without_group_identity(process):
    # Popen owns this exact child even when /proc identity capture fails. Stop
    # that child only, but never claim its whole session was cleaned: without
    # verified pgrp/session identity, descendants cannot be safely enumerated.
    try:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=CLEANUP_GRACE)
        return True
    except subprocess.TimeoutExpired:
        try:
            process.kill()
            process.wait(timeout=CLEANUP_GRACE)
            return True
        except (OSError, subprocess.TimeoutExpired):
            return False
    except OSError:
        return False

def process_identity(pid):
    info = proc_info(pid)
    if info is None:
        stop(26)
    return {
        "pid": pid, "start_ticks": info["start_ticks"],
        "uid": info["uid"], "pgrp": info["pgrp"],
        "session": info["session"],
        "cmdline_sha256": info["cmdline_sha256"], "cwd": info["cwd"],
    }

def expected_command(payload):
    command = payload.get("command")
    if (type(command) is not list or not command
            or any(type(item) is not str or not item or
                   any(ord(ch) < 32 or ord(ch) == 127 for ch in item)
                   for item in command)):
        stop(27)
    settings = payload.get("hermes_execution_settings")
    if type(settings) is not dict:
        stop(28)
    expected_fields = {"profile_name", "hermes_version", "profile_config_sha256",
        "profile_values", "invocation_values", "timeout_environment",
        "timeout_environment_supported"}
    if set(settings) != expected_fields:
        stop(28)
    safe_text = lambda item: type(item) is str and 0 < len(item) <= 256 and all(
        32 < ord(ch) < 127 for ch in item)
    for name in ("profile_name", "hermes_version"):
        if not safe_text(settings.get(name)):
            stop(28)
    if (type(settings.get("profile_config_sha256")) is not str
            or len(settings["profile_config_sha256"]) != 64
            or any(ch not in "0123456789abcdef" for ch in settings["profile_config_sha256"])):
        stop(28)
    values = settings.get("invocation_values")
    if type(values) is not dict or set(values) != {"provider", "model", "reasoning_effort"}:
        stop(28)
    if (settings.get("profile_values") != values
            or settings.get("timeout_environment") != APPROVED_TIMEOUT_ENV
            or settings.get("timeout_environment_supported") != list(APPROVED_TIMEOUT_ENV)):
        stop(28)
    if any(not safe_text(values.get(name)) for name in values):
        stop(28)
    def option(name):
        try:
            index = command.index(name)
            if index + 1 >= len(command) or command.count(name) != 1:
                stop(29)
            return command[index + 1]
        except ValueError:
            stop(29)
    if (option("--profile") != settings.get("profile_name")
            or option("--provider") != values.get("provider")
            or option("--model") != values.get("model")
            or option("--reasoning") != values.get("reasoning_effort")
            or option("--resume") != SESSION):
        stop(29)
    query_indexes = [i for i, item in enumerate(command) if item == "-q"]
    if len(query_indexes) != 1 or query_indexes[0] + 1 >= len(command):
        stop(30)
    query = command[query_indexes[0] + 1]
    if INPUT_NAME not in query or RESULT_NAME not in query or TASK not in query:
        stop(30)
    timeout_env = payload.get("timeout_environment")
    if type(timeout_env) is not dict or timeout_env != APPROVED_TIMEOUT_ENV:
        stop(31)
    timeout = payload.get("timeout_seconds")
    if type(timeout) is not int or timeout != EXECUTION_LIMIT or timeout <= 0:
        stop(32)
    if payload.get("review_execution_session_id") != SESSION:
        stop(33)
    if payload.get("request_sha256") != REQUEST_SHA:
        stop(33)
    command_sha = digest(encode(command))
    if payload.get("command_sha256") != command_sha:
        stop(34)
    return command, command_sha, settings, timeout_env, timeout

def receipt_base(*, state, request_sha, command_sha, settings, timeout,
                 timed_out, reason, exit_code, elapsed, cleanup, manager,
                 child, result_sha):
    return {
        "schema_version": RECEIPT_SCHEMA, "state": state,
        "review_execution_session_id": SESSION,
        "request_sha256": request_sha,
        "hermes_execution_settings": settings,
        "command_sha256": command_sha, "timeout_seconds": timeout,
        "timed_out": timed_out, "termination_reason": reason,
        "exit_code": exit_code, "elapsed_seconds": elapsed,
        "cleanup_confirmed": cleanup,
        "supervisor_pid": manager.get("pid") if manager else None,
        "supervisor_start_ticks": manager.get("start_ticks") if manager else None,
        "child_pid": child.get("pid") if child else None,
        "child_start_ticks": child.get("start_ticks") if child else None,
        "child_process_group_id": child.get("pgrp") if child else None,
        "result_sha256": result_sha,
    }

def start():
    fd = open_task()
    try:
        raw = sys.stdin.buffer.read(1024 * 1024 + 1)
        if not 0 < len(raw) <= 1024 * 1024:
            stop(35)
        try:
            payload = json.loads(raw.decode("ascii"))
        except (ValueError, UnicodeError):
            stop(35)
        if type(payload) is not dict or set(payload) != {
                "command", "command_sha256", "hermes_execution_settings",
                "timeout_environment", "timeout_seconds",
                "review_execution_session_id", "request_sha256",
                "supervisor_script"}:
            stop(35)
        command, command_sha, settings, timeout_env, timeout = expected_command(payload)
        supervisor_script = payload.get("supervisor_script")
        if (type(supervisor_script) is not str or not supervisor_script
                or len(supervisor_script) > 128 * 1024):
            stop(35)
        manager_argv = [sys.executable, "-c", supervisor_script, "supervise",
                        TASK, SESSION, REQUEST_SHA, command_sha]
        manager_argv_sha = digest(b"\0".join(os.fsencode(item) for item in manager_argv) + b"\0")
        source = read_private(fd, INPUT_NAME, 16 * 1024 * 1024)
        if digest(source) != REQUEST_SHA:
            stop(36)
        if not absent(fd, RESULT_NAME):
            stop(37)
        claim = {
            "schema_version": RECEIPT_SCHEMA,
            "review_execution_session_id": SESSION,
            "request_sha256": REQUEST_SHA, "command_sha256": command_sha,
            "hermes_execution_settings": settings,
            "timeout_seconds": timeout,
            "manager_argv_sha256": manager_argv_sha,
        }
        command_record = {
            "review_execution_session_id": SESSION,
            "request_sha256": REQUEST_SHA, "command_sha256": command_sha,
            "command": command, "hermes_execution_settings": settings,
            "timeout_environment": timeout_env, "timeout_seconds": timeout,
        }
        if not absent(fd, CLAIM_NAME):
            prior = read_json(fd, CLAIM_NAME, 1024 * 1024)
            if prior != claim:
                stop(38)
            if absent(fd, COMMAND_NAME):
                stop(38)
            if read_json(fd, COMMAND_NAME, 1024 * 1024) != command_record:
                stop(38)
            print(json.dumps({"state": "CLAIM_EXISTS"}, separators=(",", ":")))
            return
        if not absent(fd, COMMAND_NAME) or not absent(fd, MANAGER_NAME) or not absent(fd, RECEIPT_NAME):
            stop(38)
        write_once(fd, COMMAND_NAME, encode(command_record))
        write_once(fd, CLAIM_NAME, encode(claim))
        argv = [sys.executable, "-c", supervisor_script, "supervise", TASK, SESSION,
                REQUEST_SHA, command_sha]
        try:
            subprocess.Popen(argv, cwd=TASK, env=os.environ.copy(),
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)
        except OSError:
            manager = None
            receipt = receipt_base(state="START_FAILED", request_sha=REQUEST_SHA,
                command_sha=command_sha, settings=settings, timeout=timeout,
                timed_out=False, reason="START_FAILED", exit_code=None,
                elapsed=0.0, cleanup=True, manager=manager, child=None, result_sha=None)
            write_final(fd, receipt)
            print(json.dumps({"state": "START_FAILED"}, separators=(",", ":")))
            return
        print(json.dumps({"state": "START_ACCEPTED"}, separators=(",", ":")))
    finally:
        os.close(fd)

def supervisor():
    fd = open_task()
    started = time.monotonic()
    manager = None
    child = None
    process = None
    claim = {}
    command_record = {}
    returncode = None
    timed_out = False
    cleanup = True
    result_sha = None
    state = "SUPERVISOR_ERROR"
    reason = "SUPERVISOR_ERROR"
    try:
        claim = read_json(fd, CLAIM_NAME, 1024 * 1024)
        command_record = read_json(fd, COMMAND_NAME, 1024 * 1024)
        if (claim.get("review_execution_session_id") != SESSION
                or claim.get("request_sha256") != REQUEST_SHA
                or claim.get("command_sha256") != COMMAND_SHA
                or command_record.get("review_execution_session_id") != SESSION
                or command_record.get("request_sha256") != REQUEST_SHA
                or command_record.get("command_sha256") != COMMAND_SHA):
            stop(39)
        command, command_sha, settings, timeout_env, timeout = expected_command(command_record)
        if command_sha != COMMAND_SHA or claim != {
            "schema_version": RECEIPT_SCHEMA,
            "review_execution_session_id": SESSION,
            "request_sha256": REQUEST_SHA, "command_sha256": command_sha,
            "hermes_execution_settings": settings,
            "timeout_seconds": timeout,
            "manager_argv_sha256": claim.get("manager_argv_sha256"),
        }:
            stop(40)
        source = read_private(fd, INPUT_NAME, 16 * 1024 * 1024)
        if digest(source) != REQUEST_SHA or not absent(fd, RESULT_NAME):
            stop(41)
        manager = process_identity(os.getpid())
        if manager["pgrp"] != manager["pid"] or manager["session"] != manager["pid"] or manager["cwd"] != TASK:
            stop(42)
        manager_record = {
            "pid": manager["pid"], "start_ticks": manager["start_ticks"],
            "uid": manager["uid"], "pgrp": manager["pgrp"],
            "session": manager["session"],
            "cmdline_sha256": manager["cmdline_sha256"],
            "review_execution_session_id": SESSION,
            "request_sha256": REQUEST_SHA, "command_sha256": COMMAND_SHA,
            "manager_argv_sha256": claim.get("manager_argv_sha256"),
        }
        current_cmdline = open("/proc/self/cmdline", "rb").read()
        if digest(current_cmdline) != claim.get("manager_argv_sha256"):
            stop(42)
        write_once(fd, MANAGER_NAME, encode(manager_record))
        env = os.environ.copy()
        env.update(timeout_env)
        try:
            process = subprocess.Popen(command, cwd=TASK, env=env,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)
        except OSError:
            state, reason, cleanup = "START_FAILED", "START_FAILED", True
        else:
            child = process_identity(process.pid)
            if (child["pid"] != child["pgrp"] or child["session"] != child["pid"]
                    or child["cwd"] != TASK):
                cleanup = False
                state, reason = "CLEANUP_UNVERIFIED", "CLEANUP_UNVERIFIED"
            else:
                write_once(fd, CHILD_NAME, encode(child))
                try:
                    process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    reason = "REMOTE_EXECUTION_TIMEOUT"
                returncode = process.returncode
                cleanup = cleanup_group(process, child)
                returncode = process.returncode
                if not cleanup:
                    state, reason = "CLEANUP_UNVERIFIED", (
                        "REMOTE_EXECUTION_TIMEOUT" if timed_out else "CLEANUP_UNVERIFIED")
                elif timed_out:
                    state, reason = "TIMED_OUT", "REMOTE_EXECUTION_TIMEOUT"
                elif returncode != 0:
                    state, reason = "FAILED", "CHILD_EXIT_NONZERO"
                else:
                    try:
                        result = read_private(fd, RESULT_NAME, 16 * 1024 * 1024)
                        result_sha = digest(result)
                        state, reason = "COMPLETED", "NORMAL_EXIT"
                    except SystemExit:
                        state, reason, result_sha = "FAILED", "RESULT_INVALID", None
        if process is not None:
            returncode = process.returncode
    except BaseException:
        if process is not None:
            if child is not None:
                cleanup = cleanup_group(process, child)
            else:
                stop_direct_child_without_group_identity(process)
                # Direct-child reaping does not prove the isolated process
                # group has no descendants; the receipt must remain UNKNOWN.
                cleanup = False
            returncode = process.returncode
        if not cleanup:
            state, reason = "CLEANUP_UNVERIFIED", "CLEANUP_UNVERIFIED"
        else:
            state, reason = "SUPERVISOR_ERROR", "SUPERVISOR_ERROR"
    elapsed = max(0.0, time.monotonic() - started)
    settings = command_record.get("hermes_execution_settings")
    timeout = command_record.get("timeout_seconds")
    if (type(settings) is dict and type(timeout) is int
            and COMMAND_SHA and len(COMMAND_SHA) == 64):
        receipt = receipt_base(state=state, request_sha=REQUEST_SHA,
            command_sha=COMMAND_SHA, settings=settings, timeout=timeout,
            timed_out=timed_out, reason=reason, exit_code=returncode,
            elapsed=elapsed, cleanup=cleanup, manager=manager, child=child,
            result_sha=result_sha if state == "COMPLETED" else None)
        write_final(fd, receipt)
    os.close(fd)

def status():
    fd = open_task()
    try:
        if absent(fd, CLAIM_NAME):
            print(json.dumps({"state": "NOT_STARTED"}, separators=(",", ":")))
            return
        claim = read_json(fd, CLAIM_NAME, 1024 * 1024)
        if (claim.get("review_execution_session_id") != SESSION
                or claim.get("request_sha256") != REQUEST_SHA):
            stop(43)
        command_record = read_json(fd, COMMAND_NAME, 1024 * 1024)
        command, command_sha, settings, timeout_env, timeout = expected_command(command_record)
        if (claim.get("command_sha256") != command_sha
                or command_record.get("command_sha256") != command_sha):
            stop(44)
        if COMMAND_SHA and COMMAND_SHA != command_sha:
            stop(44)
        if not absent(fd, RECEIPT_NAME):
            receipt = read_json(fd, RECEIPT_NAME, 1024 * 1024)
            if (receipt.get("review_execution_session_id") != SESSION
                    or receipt.get("request_sha256") != REQUEST_SHA
                    or receipt.get("command_sha256") != command_sha
                    or receipt.get("hermes_execution_settings") != settings):
                stop(45)
            if receipt.get("state") == "COMPLETED":
                result = read_private(fd, RESULT_NAME, 16 * 1024 * 1024)
                if digest(result) != receipt.get("result_sha256"):
                    stop(46)
            print(json.dumps({"state": receipt.get("state"), "receipt": receipt},
                             ensure_ascii=True, sort_keys=True, separators=(",", ":")))
            return
        if absent(fd, MANAGER_NAME):
            print(json.dumps({"state": "STARTING"}, separators=(",", ":")))
            return
        manager = read_json(fd, MANAGER_NAME, 65536)
        pid = manager.get("pid")
        info = proc_info(pid) if type(pid) is int and pid > 0 else None
        alive = bool(info and info.get("start_ticks") == manager.get("start_ticks")
            and info.get("uid") == manager.get("uid") == os.geteuid()
            and info.get("pgrp") == info.get("session") == pid
            and info.get("cmdline_sha256") == claim.get("manager_argv_sha256")
            and manager.get("cmdline_sha256") == claim.get("manager_argv_sha256")
            and manager.get("review_execution_session_id") == SESSION
            and manager.get("request_sha256") == REQUEST_SHA
            and manager.get("command_sha256") == command_sha
            and manager.get("manager_argv_sha256") == claim.get("manager_argv_sha256"))
        state = "RUNNING" if alive else "SUPERVISOR_LOST"
        print(json.dumps({"state": state}, separators=(",", ":")))
    finally:
        os.close(fd)

check_identity()
if ACTION == "start":
    start()
elif ACTION == "supervise":
    supervisor()
elif ACTION == "status":
    status()
else:
    stop(47)
'''

_REMOTE_QUALITY_REVIEW_EXECUTION_SCRIPT = (
    _REMOTE_QUALITY_REVIEW_EXECUTION_SCRIPT_TEMPLATE
    .replace("__EXECUTION_LIMIT__", str(QUALITY_REVIEW_REMOTE_EXECUTION_TIMEOUT_SECONDS))
    .replace("__CLEANUP_GRACE__", str(QUALITY_REVIEW_CLEANUP_GRACE_SECONDS))
)


def _as_text(value: object, *, field_name: str) -> str:
    if isinstance(value, os.PathLike):
        value = os.fspath(value)
    if type(value) is not str or not value or value != value.strip():
        raise Stage11DeploymentValidationError(
            field_name + " must be a nonempty exact string"
        )
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise Stage11DeploymentValidationError(
            field_name + " contains control data"
        )
    return value


def _absolute_path(value: object, *, field_name: str) -> str:
    value = _as_text(value, field_name=field_name)
    path = PurePosixPath(value)
    if not path.is_absolute() or path == PurePosixPath("/"):
        raise Stage11DeploymentValidationError(
            field_name + " must be a non-root absolute path"
        )
    if str(path) != value or any(part in {".", ".."} for part in path.parts):
        raise Stage11DeploymentValidationError(
            field_name + " must be a normalized absolute path"
        )
    return value


def _host_or_user(value: object, *, field_name: str) -> str:
    value = _as_text(value, field_name=field_name)
    if any(character.isspace() for character in value):
        raise Stage11DeploymentValidationError(
            field_name + " must not contain whitespace"
        )
    if any(character in value for character in "@/\\"):
        raise Stage11DeploymentValidationError(
            field_name + " contains unsafe SSH syntax"
        )
    return value


def _profile_name(value: object) -> str:
    value = _as_text(value, field_name="expected_profile_name")
    if any(character.isspace() for character in value):
        raise Stage11DeploymentValidationError(
            "expected_profile_name contains unsafe whitespace"
        )
    return value


def _positive_number(value: object, *, field_name: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Stage11DeploymentValidationError(
            field_name + " must be a positive finite number"
        )
    try:
        numeric = float(value)
    except OverflowError as error:
        raise Stage11DeploymentValidationError(
            field_name + " must be a positive finite number"
        ) from error
    if not math.isfinite(numeric) or numeric <= 0:
        raise Stage11DeploymentValidationError(
            field_name + " must be a positive finite number"
        )
    return value


@dataclass(frozen=True)
class Stage11DeploymentConfig:
    """Explicit deployment-owned connection values.

    The ASR timeout is deliberately required from the caller.  The value
    ``1200`` is therefore a first-canary choice, not a module production
    default.  SSH keys are retained as paths only; their contents are never
    loaded by this configuration object.
    """

    nas_host: str
    nas_user: str
    nas_key: str
    nas_known_hosts: str
    nas_library_root: str
    asr_base_url: str
    request_timeout_seconds: int | float
    remote_host: str
    remote_user: str
    ssh_key: str
    known_hosts: str
    remote_task_root: str
    expected_profile_name: str = REMOTE_HERMES_PROFILE_NAME
    subtitlecat_timeout_seconds: int | float = 20.0
    subtitlecat_proxy_url: str | None = None
    asr_media_temp_root: str = "/var/tmp/teddy-stage11-asr-production"
    asr_media_temp_reserve_bytes: int = ASR_MEDIA_TEMP_RESERVE_BYTES
    targeted_asr_worker_config_path: str = (
        "/opt/missav-dlp-web/discovery/stage11-normal-deployment/"
        "targeted-asr-worker.json"
    )

    def __post_init__(self):
        for name in ("nas_host", "nas_user", "remote_host", "remote_user"):
            object.__setattr__(
                self,
                name,
                _host_or_user(getattr(self, name), field_name=name),
            )
        for name in (
            "nas_key",
            "nas_known_hosts",
            "nas_library_root",
            "ssh_key",
            "known_hosts",
            "remote_task_root",
        ):
            object.__setattr__(
                self,
                name,
                _absolute_path(getattr(self, name), field_name=name),
            )
        object.__setattr__(
            self,
            "asr_media_temp_root",
            _absolute_path(
                self.asr_media_temp_root,
                field_name="asr_media_temp_root",
            ),
        )
        object.__setattr__(
            self,
            "targeted_asr_worker_config_path",
            _absolute_path(
                self.targeted_asr_worker_config_path,
                field_name="targeted_asr_worker_config_path",
            ),
        )
        if (
            type(self.asr_media_temp_reserve_bytes) is not int
            or self.asr_media_temp_reserve_bytes < 0
        ):
            raise Stage11DeploymentValidationError(
                "asr_media_temp_reserve_bytes must be a nonnegative exact integer"
            )
        object.__setattr__(
            self,
            "asr_base_url",
            _as_text(self.asr_base_url, field_name="asr_base_url"),
        )
        object.__setattr__(
            self,
            "request_timeout_seconds",
            _positive_number(
                self.request_timeout_seconds,
                field_name="request_timeout_seconds",
            ),
        )
        object.__setattr__(
            self,
            "subtitlecat_timeout_seconds",
            _positive_number(
                self.subtitlecat_timeout_seconds,
                field_name="subtitlecat_timeout_seconds",
            ),
        )
        try:
            subtitlecat_proxy_url = validate_subtitlecat_proxy_url(
                self.subtitlecat_proxy_url
            )
        except SubtitleCatSearchError as error:
            raise Stage11DeploymentValidationError(
                "subtitlecat_proxy_url is invalid"
            ) from error
        object.__setattr__(
            self,
            "subtitlecat_proxy_url",
            subtitlecat_proxy_url,
        )
        object.__setattr__(
            self,
            "expected_profile_name",
            _profile_name(self.expected_profile_name),
        )


def _require_session_id(value: object) -> str:
    try:
        return validate_canonical_review_execution_session_id(value)
    except QualityReviewSessionError as error:
        raise Stage11DeploymentValidationError(
            "remote session ID is not canonical"
        ) from error


def _normalized_remote_root(value: str) -> PurePosixPath:
    root = PurePosixPath(_absolute_path(value, field_name="remote_task_root"))
    return root


def _make_remote_task_factory(config: Stage11DeploymentConfig) -> Callable[[str], str]:
    root = _normalized_remote_root(config.remote_task_root)

    def remote_task_for_session(session_id: str) -> str:
        session_id = _require_session_id(session_id)
        task = root / session_id
        if task.parent != root or task.name != session_id:
            raise Stage11DeploymentValidationError(
                "remote session task escaped its configured root"
            )
        return validate_stateful_remote_task_path(task.as_posix())

    return remote_task_for_session


class _NoRedirectHandler(urllib_request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise annotate_external_subtitle_error(
            ExternalSubtitleTransportError("SubtitleCat redirect is not permitted"),
            stage="ja_srt_download",
            reason_code="SRT_REDIRECT",
            http_status=code,
        )


def _http_bytes(
    url: str,
    *,
    timeout: int | float,
    max_bytes: int,
    proxy_url: str | None = None,
) -> bytes:
    try:
        parsed = urlsplit(url)
    except ValueError as error:
        wrapped = ExternalSubtitleTransportError(
            "SubtitleCat URL could not be parsed"
        )
        annotate_external_subtitle_error(
            wrapped, stage="ja_srt_download", reason_code="SRT_URL_INVALID"
        )
        raise wrapped from error
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise annotate_external_subtitle_error(ExternalSubtitleTransportError(
            "SubtitleCat transport requires an HTTP(S) URL"
        ), stage="ja_srt_download", reason_code="SRT_URL_INVALID")
    try:
        # Keep the candidate's Unicode URL as its source identity, but send a
        # standards-compliant ASCII URI to urllib. ``safe`` preserves existing
        # delimiters and percent escapes, so only raw non-ASCII path/query
        # characters are UTF-8 percent-encoded.
        request_url = urlunsplit((
            parsed.scheme,
            parsed.netloc,
            quote(parsed.path, safe="/%:@!$&'()*+,;=-._~%"),
            quote(parsed.query, safe="/?%:@!$&'()*+,;=-._~"),
            parsed.fragment,
        ))
        request_url.encode("ascii")
        request = urllib_request.Request(
            request_url,
            headers={
                "User-Agent": "Mozilla/5.0 Teddy-Downloader-SubtitleDiscovery/1.0",
                "Accept": "text/html,application/x-subrip,text/plain,*/*",
            },
            method="GET",
        )
    except UnicodeError as error:
        wrapped = ExternalSubtitleTransportError(
            "SubtitleCat request URL cannot be encoded safely"
        )
        annotate_external_subtitle_error(
            wrapped, stage="ja_srt_download", reason_code="SRT_URL_ENCODING"
        )
        raise wrapped from error
    handlers = []
    if proxy_url is not None:
        handlers.append(
            urllib_request.ProxyHandler(
                {"http": proxy_url, "https": proxy_url}
            )
        )
    handlers.append(_NoRedirectHandler())
    opener = urllib_request.build_opener(*handlers)
    try:
        with opener.open(request, timeout=timeout) as response:
            status = response.getcode()
            final_url = response.geturl()
            if type(status) is not int or not 200 <= status < 300:
                raise annotate_external_subtitle_error(
                    ExternalSubtitleTransportError(
                        "SubtitleCat HTTP status is not successful"
                    ),
                    stage="ja_srt_download",
                    reason_code="SRT_HTTP_STATUS",
                    http_status=status if type(status) is int else None,
                )
            if final_url != request_url:
                raise annotate_external_subtitle_error(
                    ExternalSubtitleTransportError(
                        "SubtitleCat redirect is not permitted"
                    ),
                    stage="ja_srt_download",
                    reason_code="SRT_REDIRECT",
                    http_status=status,
                )
            payload = response.read(max_bytes + 1)
    except ExternalSubtitleTransportError:
        raise
    except urllib_error.HTTPError as error:
        wrapped = ExternalSubtitleTransportError(
            "SubtitleCat HTTP status is not successful"
        )
        annotate_external_subtitle_error(
            wrapped,
            stage="ja_srt_download",
            reason_code="SRT_HTTP_STATUS",
            http_status=error.code,
        )
        raise wrapped from error
    except (OSError, TimeoutError, urllib_error.URLError) as error:
        wrapped = ExternalSubtitleTransportError("SubtitleCat HTTP transport failed")
        annotate_external_subtitle_error(
            wrapped,
            stage="ja_srt_download",
            reason_code="SRT_TRANSPORT_FAILURE",
        )
        raise wrapped from error
    if type(payload) is not bytes or not 0 < len(payload) <= max_bytes:
        raise annotate_external_subtitle_error(
            ExternalSubtitleTransportError(
                "SubtitleCat response exceeded its bounded byte limit"
            ),
            stage="ja_srt_download",
            reason_code="SRT_RESPONSE_INVALID",
        )
    return payload


class _DetailNoRedirectHandler(urllib_request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        # Expose status/Location as HTTPError; never follow or read its body.
        return None


def _detail_http_bytes(
    url: str,
    *,
    timeout: int | float,
    max_bytes: int,
    proxy_url: str | None = None,
) -> tuple[bytes, str]:
    """Bounded detail GET with only the exact official one-hop 301 exception."""
    def canonical_host(value, host):
        try:
            parsed = urlsplit(value)
            if (type(value) is not str or any(ord(c) <= 32 or ord(c) == 127 for c in value)
                    or "#" in value or parsed.scheme != "https"
                    or parsed.hostname != host or parsed.username is not None
                    or parsed.password is not None or parsed.port not in (None, 443)):
                raise ValueError()
            return parsed
        except (TypeError, ValueError) as error:
            raise ExternalSubtitleTransportError("SubtitleCat canonical detail URL is invalid") from error

    handlers = [_DetailNoRedirectHandler()]
    if proxy_url is not None:
        handlers.append(urllib_request.ProxyHandler({"http": proxy_url, "https": proxy_url}))
    opener = urllib_request.build_opener(*handlers)
    current = url
    try:
        for hop in range(2):
            request = urllib_request.Request(current, headers={
                "User-Agent": "Mozilla/5.0 Teddy-Downloader-SubtitleDiscovery/1.0",
                "Accept": "text/html,application/x-subrip,text/plain,*/*",
            }, method="GET")
            try:
                response = opener.open(request, timeout=timeout)
            except urllib_error.HTTPError as error:
                response = error
            with response:
                status = response.getcode()
                if response.geturl() != current:
                    raise ExternalSubtitleTransportError("SubtitleCat detail response URL is detached")
                if type(status) is int and 200 <= status < 300:
                    payload = response.read(max_bytes + 1)
                    if type(payload) is not bytes or not 0 < len(payload) <= max_bytes:
                        raise annotate_external_subtitle_error(
                            ExternalSubtitleTransportError(
                                "SubtitleCat response exceeded its bounded byte limit"
                            ),
                            stage="detail_http",
                            reason_code="DETAIL_RESPONSE_INVALID",
                        )
                    return payload, current
                if status != 301 or hop != 0:
                    raise annotate_external_subtitle_error(
                        ExternalSubtitleTransportError(
                            "SubtitleCat detail redirect/status is not permitted"
                        ),
                        stage="detail_http",
                        reason_code=(
                            "DETAIL_HTTP_STATUS" if status != 301
                            else "DETAIL_REDIRECT"
                        ),
                        http_status=status if type(status) is int else None,
                    )
                source = canonical_host(current, "subtitlecat.com")
                locations = response.headers.get_all("Location", [])
                if len(locations) != 1:
                    raise annotate_external_subtitle_error(
                        ExternalSubtitleTransportError(
                            "SubtitleCat canonical detail Location is invalid"
                        ),
                        stage="detail_http",
                        reason_code="DETAIL_REDIRECT_INVALID",
                        http_status=status,
                    )
                target_url = locations[0]
                target = canonical_host(target_url, "www.subtitlecat.com")
                if (source.path, source.query) != (target.path, target.query):
                    raise annotate_external_subtitle_error(
                        ExternalSubtitleTransportError(
                            "SubtitleCat canonical detail target is detached"
                        ),
                        stage="detail_http",
                        reason_code="DETAIL_REDIRECT_INVALID",
                        http_status=status,
                    )
                current = target_url
    except ExternalSubtitleTransportError:
        raise
    except urllib_error.HTTPError as error:
        wrapped = ExternalSubtitleTransportError(
            "SubtitleCat detail HTTP status is not successful"
        )
        annotate_external_subtitle_error(
            wrapped,
            stage="detail_http",
            reason_code="DETAIL_HTTP_STATUS",
            http_status=error.code,
        )
        raise wrapped from error
    except (OSError, TimeoutError, urllib_error.URLError, ValueError) as error:
        wrapped = ExternalSubtitleTransportError("SubtitleCat detail HTTP transport failed")
        annotate_external_subtitle_error(
            wrapped, stage="detail_http", reason_code="DETAIL_TRANSPORT_FAILURE"
        )
        raise wrapped from error


def _default_detail_fetcher(
    timeout: int | float,
    *,
    proxy_url: str | None = None,
) -> Callable[[str], SubtitleCatDetailPage]:
    def fetch_detail(url: str) -> SubtitleCatDetailPage:
        raw, final_url = _detail_http_bytes(
            url,
            timeout=timeout,
            max_bytes=MAX_SUBTITLECAT_DETAIL_HTML_BYTES,
            proxy_url=proxy_url,
        )
        try:
            html = raw.decode("utf-8", errors="strict")
            return SubtitleCatDetailPage(final_url=final_url, html=html)
        except (UnicodeError, SubtitleCatDetailError):
            raise
        except (TypeError, ValueError) as error:
            raise SubtitleCatDetailError(
                "SubtitleCat detail HTML is invalid"
            ) from error

    return fetch_detail


def _default_payload_fetcher(
    timeout: int | float,
    *,
    proxy_url: str | None = None,
) -> Callable:
    def fetch_payload(candidate) -> bytes:
        url = getattr(candidate, "external_source_id", None)
        if type(url) is not str:
            raise ExternalSubtitleTransportError(
                "SubtitleCat candidate has no source URL"
            )
        return _http_bytes(
            url,
            timeout=timeout,
            max_bytes=MAX_SUBTITLE_BYTES,
            proxy_url=proxy_url,
        )

    return fetch_payload


def build_subtitlecat_provider(
    *,
    timeout: int | float = 20.0,
    fetch_detail: Callable[[str], object] | None = None,
    payload_fetcher: Callable | None = None,
    proxy_url: str | None = None,
) -> SubtitleCatProvider:
    """Compose the existing provider with bounded GET-only transports."""

    timeout = _positive_number(timeout, field_name="SubtitleCat timeout")
    proxy_url = validate_subtitlecat_proxy_url(proxy_url)
    detail = fetch_detail or _default_detail_fetcher(
        timeout,
        proxy_url=proxy_url,
    )
    payload = payload_fetcher or _default_payload_fetcher(
        timeout,
        proxy_url=proxy_url,
    )
    return SubtitleCatProvider(
        fetch_detail=detail,
        payload_transport=ExternalSubtitleTransport(payload),
    )


def _private_local_read(path: Path, *, max_bytes: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | os.O_NONBLOCK
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise Stage11DeploymentValidationError(
            "private local deployment input cannot be opened"
        ) from error
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != STATEFUL_TRANSLATOR_PRIVATE_FILE_MODE
            or not 0 < info.st_size <= max_bytes
        ):
            raise Stage11DeploymentValidationError(
                "private local deployment input has unsafe identity"
            )
        payload = os.read(descriptor, max_bytes + 1)
        if len(payload) != info.st_size or not 0 < len(payload) <= max_bytes:
            raise Stage11DeploymentValidationError(
                "private local deployment input readback differs"
            )
        return payload
    except OSError as error:
        raise Stage11DeploymentValidationError(
            "private local deployment input could not be read"
        ) from error
    finally:
        os.close(descriptor)


def _private_local_read_at(fd: int, filename: str, *, max_bytes: int) -> bytes:
    try:
        descriptor = os.open(
            filename,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | os.O_NONBLOCK,
            dir_fd=fd,
        )
    except OSError as error:
        raise Stage11DeploymentValidationError(
            "private review input cannot be opened"
        ) from error
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != STATEFUL_TRANSLATOR_PRIVATE_FILE_MODE
            or not 0 < info.st_size <= max_bytes
        ):
            raise Stage11DeploymentValidationError(
                "private review input has unsafe identity"
            )
        payload = os.read(descriptor, max_bytes + 1)
        if len(payload) != info.st_size or not 0 < len(payload) <= max_bytes:
            raise Stage11DeploymentValidationError(
                "private review input readback differs"
            )
        return payload
    except OSError as error:
        raise Stage11DeploymentValidationError(
            "private review input could not be read"
        ) from error
    finally:
        os.close(descriptor)


def _private_local_write_at(fd: int, filename: str, payload: bytes) -> None:
    if type(payload) is not bytes or not payload:
        raise Stage11DeploymentValidationError(
            "private review result must be nonempty bytes"
        )
    try:
        descriptor = os.open(
            filename,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            STATEFUL_TRANSLATOR_PRIVATE_FILE_MODE,
            dir_fd=fd,
        )
    except OSError as error:
        raise Stage11DeploymentValidationError(
            "private review result destination is not absent"
        ) from error
    try:
        os.fchmod(descriptor, STATEFUL_TRANSLATOR_PRIVATE_FILE_MODE)
        written = os.write(descriptor, payload)
        if written != len(payload):
            raise Stage11DeploymentValidationError(
                "private review result write was short"
            )
        os.fsync(descriptor)
    except OSError as error:
        raise Stage11DeploymentValidationError(
            "private review result write failed"
        ) from error
    finally:
        os.close(descriptor)
    try:
        os.fsync(fd)
    except OSError as error:
        raise Stage11DeploymentValidationError(
            "private review task directory sync failed"
        ) from error


def _local_task_from_fd(fd: int) -> Path:
    try:
        value = Path(os.readlink(f"/proc/self/fd/{fd}"))
    except OSError as error:
        raise Stage11DeploymentValidationError(
            "pinned review task directory cannot be resolved"
        ) from error
    if not value.is_absolute() or value == Path("/"):
        raise Stage11DeploymentValidationError(
            "pinned review task directory is not absolute"
        )
    return value


class SSHRemoteHermesBridge:
    """Native CT120 bridge; all state access remains in Hermes' SessionDB API."""

    def __init__(
        self,
        config: Stage11DeploymentConfig,
        *,
        runner: Callable = subprocess.run,
    ):
        if not callable(runner):
            raise Stage11DeploymentValidationError("remote runner must be callable")
        self.config = config
        self.runner = runner

    def _base(self) -> list[str]:
        return build_stateful_ssh_argv(
            f"{self.config.remote_user}@{self.config.remote_host}",
            self.config.ssh_key,
            self.config.known_hosts,
        )

    def _run(
        self,
        command: str,
        *,
        input_payload: bytes | None = None,
        capture: bool = False,
        timeout: int | float | None = None,
    ) -> bytes:
        kwargs = {
            "input": input_payload,
            "stdout": subprocess.PIPE if capture else subprocess.DEVNULL,
            "stderr": subprocess.PIPE,
            "check": False,
        }
        if timeout is not None:
            kwargs["timeout"] = timeout
        try:
            completed = self.runner(self._base() + [command], **kwargs)
        except (OSError, subprocess.SubprocessError) as error:
            raise Stage11DeploymentTransportError(
                "CT120 SSH transport failed"
            ) from error
        if getattr(completed, "returncode", None) != 0:
            raise Stage11DeploymentTransportError(
                "CT120 native command failed"
            )
        output = getattr(completed, "stdout", b"")
        if capture and type(output) is not bytes:
            raise Stage11DeploymentTransportError(
                "CT120 captured output is not bytes"
            )
        return output if capture else b""

    def _python(
        self,
        script: str,
        *arguments: str,
        input_payload: bytes | None = None,
        capture: bool = False,
        timeout: int | float | None = None,
        python_executable: str = "python3",
    ) -> bytes:
        command = " ".join(
            shlex.quote(value)
            for value in (python_executable, "-c", script, *arguments)
        )
        return self._run(
            command,
            input_payload=input_payload,
            capture=capture,
            timeout=timeout,
        )

    def resolve_stage11_hermes_settings(self):
        """Read the active Stage11 profile and runtime timeout support only."""
        try:
            raw = self._python(
                REMOTE_PROFILE_SETTINGS_PROBE,
                STAGE11_HERMES_CONFIG_PATH,
                REMOTE_HERMES_SOURCE,
                STAGE11_HERMES_PROFILE,
                *STAGE11_HERMES_TIMEOUT_ENV_NAMES,
                capture=True,
                timeout=30,
                python_executable=REMOTE_HERMES_PYTHON,
            )
            return settings_from_probe(raw)
        except (HermesProfileSettingsError, Stage11DeploymentError):
            raise
        except Exception as error:
            raise Stage11DeploymentTransportError(
                "Stage11 Hermes profile read-only preflight failed"
            ) from error

    def ensure_task(self, remote_task: str) -> None:
        remote_task = validate_stateful_remote_task_path(remote_task)
        script = """
import os, stat, sys
path = sys.argv[1]
try:
    info = os.lstat(path)
except FileNotFoundError:
    os.mkdir(path, 0o700)
    info = os.lstat(path)
if (stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700):
    raise SystemExit(2)
"""
        self._python(script, remote_task)

    def write_exclusive(self, remote_path: str, payload: bytes) -> None:
        remote_path = validate_stateful_remote_task_path(remote_path)
        if type(payload) is not bytes or not payload:
            raise Stage11DeploymentValidationError(
                "remote payload must be nonempty bytes"
            )
        digest = hashlib.sha256(payload).hexdigest()
        script = """
import hashlib, os, stat, sys
path, expected_size, expected_sha = sys.argv[1], int(sys.argv[2]), sys.argv[3]
payload = sys.stdin.buffer.read(expected_size + 1)
if len(payload) != expected_size or hashlib.sha256(payload).hexdigest() != expected_sha:
    raise SystemExit(2)
if os.path.lexists(path):
    raise SystemExit(3)
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "wb") as stream:
        fd = None
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
finally:
    if fd is not None:
        os.close(fd)
info = os.lstat(path)
if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
        or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_size != expected_size):
    raise SystemExit(4)
"""
        self._python(
            script,
            remote_path,
            str(len(payload)),
            digest,
            input_payload=payload,
        )

    def ensure_file(self, remote_path: str, payload: bytes) -> None:
        """Install exact input once, or reuse an exact existing input."""

        try:
            existing = self.read_regular(remote_path, max_bytes=len(payload))
        except Stage11DeploymentTransportError:
            existing = None
        if existing is not None:
            if existing != payload:
                raise Stage11DeploymentValidationError(
                    "existing remote input is detached"
                )
            return
        self.write_exclusive(remote_path, payload)

    def read_regular(self, remote_path: str, *, max_bytes: int) -> bytes:
        remote_path = validate_stateful_remote_task_path(remote_path)
        if type(max_bytes) is not int or max_bytes <= 0:
            raise Stage11DeploymentValidationError("remote read bound is invalid")
        script = """
import os, stat, sys
path, bound = sys.argv[1], int(sys.argv[2])
fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
try:
    info = os.fstat(fd)
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600
            or not 0 < info.st_size <= bound):
        raise SystemExit(2)
    payload = os.read(fd, bound + 1)
finally:
    os.close(fd)
if len(payload) != info.st_size or not 0 < len(payload) <= bound:
    raise SystemExit(3)
sys.stdout.buffer.write(payload)
"""
        return self._python(script, remote_path, str(max_bytes), capture=True)

    def _native_session(
        self,
        operation: str,
        session_id: str,
        *,
        source: str | None = None,
        profile_name: str | None = None,
        timeout: int | float | None = None,
    ) -> object:
        session_id = _require_session_id(session_id)
        profile_name = self.config.expected_profile_name if profile_name is None else profile_name
        profile_name = _profile_name(profile_name)
        if source is not None:
            source = _as_text(source, field_name="native session source")
        profile_home = str(Path(REMOTE_HERMES_PROFILE).parent)
        script = """
import json, os, sys
from pathlib import Path
profile_home, source_root, operation, session_id, expected_profile, expected_source = sys.argv[1:]
os.environ["HERMES_HOME"] = profile_home
sys.path.insert(0, source_root)
from hermes_cli.profiles import get_active_profile_name
from hermes_state import SessionDB
if get_active_profile_name() != expected_profile:
    raise SystemExit(20)
db = SessionDB(db_path=Path(profile_home) / "state.db")
try:
    if operation == "get":
        row = db.get_session(session_id)
        if row is None:
            print("null")
        else:
            print(json.dumps({
                "id": row.get("id"),
                "source": row.get("source"),
                "profile_name": row.get("profile_name"),
                "parent_session_id": row.get("parent_session_id"),
            }, sort_keys=True, separators=(",", ":")))
    elif operation == "messages":
        messages = db.get_messages(session_id, include_inactive=True)
        if not isinstance(messages, list):
            raise SystemExit(21)
        print(len(messages))
    elif operation in {"ensure", "fresh"}:
        existing = db.get_session(session_id)
        if operation == "fresh" and existing is not None:
            raise SystemExit(22)
        if existing is None:
            returned_id = db.create_session(
                session_id=session_id,
                source=expected_source,
                profile_name=expected_profile,
            )
            if type(returned_id) is not str or returned_id != session_id:
                raise SystemExit(23)
            existing = db.get_session(session_id)
        if existing is None:
            raise SystemExit(24)
        if (existing.get("id") != session_id
                or existing.get("source") != expected_source
                or existing.get("profile_name") != expected_profile
                or existing.get("parent_session_id") is not None):
            raise SystemExit(25)
        if operation == "fresh":
            messages = db.get_messages(session_id, include_inactive=True)
            if type(messages) is not list or messages:
                raise SystemExit(26)
        print(session_id)
    else:
        raise SystemExit(27)
finally:
    close = getattr(db, "close", None)
    if callable(close):
        close()
"""
        output = self._python(
            script,
            profile_home,
            REMOTE_HERMES_SOURCE,
            operation,
            session_id,
            profile_name,
            source or "",
            capture=True,
            timeout=timeout,
            python_executable=REMOTE_HERMES_PYTHON,
        )
        return output.decode("utf-8", errors="strict").strip()

    def get_session(self, session_id: str) -> Mapping[str, object] | None:
        raw = self._native_session("get", session_id)
        if raw == "null":
            return None
        try:
            value = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise Stage11DeploymentTransportError(
                "CT120 SessionDB read-back is malformed"
            ) from error
        if type(value) is not dict:
            raise Stage11DeploymentTransportError(
                "CT120 SessionDB read-back is not a mapping"
            )
        return value

    def create_session(
        self,
        *,
        session_id: str,
        source: str,
        profile_name: str,
    ) -> str:
        raw = self._native_session(
            "fresh",
            session_id,
            source=source,
            profile_name=profile_name,
        )
        if raw != session_id:
            raise Stage11DeploymentTransportError(
                "CT120 SessionDB created a different session ID"
            )
        return session_id

    def ensure_stateful_session(self, session_id: str) -> None:
        raw = self._native_session(
            "ensure",
            session_id,
            source=STATEFUL_TRANSLATOR_SESSION_SOURCE,
            profile_name=self.config.expected_profile_name,
        )
        if raw != session_id:
            raise Stage11DeploymentTransportError(
                "CT120 stateful session read-back differs"
            )

    def get_messages(
        self,
        session_id: str,
        *,
        include_inactive: bool = False,
    ) -> list[object]:
        del include_inactive
        raw = self._native_session("messages", session_id)
        try:
            count = int(raw)
        except (TypeError, ValueError) as error:
            raise Stage11DeploymentTransportError(
                "CT120 SessionDB message count is malformed"
            ) from error
        if count < 0:
            raise Stage11DeploymentTransportError(
                "CT120 SessionDB message count is negative"
            )
        # Only emptiness is needed by the shared validator.  Do not return
        # remote dialogue contents to CT108.
        return [None] * count

    def read_quality_review_execution(
        self,
        *,
        remote_task: str,
        review_execution_session_id: str,
        request_sha256: str,
        hermes_execution_settings: Mapping[str, object],
        command_sha256: str | None = None,
        timeout_seconds: int | float = QUALITY_REVIEW_REMOTE_CALL_TIMEOUT_SECONDS,
    ) -> dict[str, object]:
        """Read the state of one already-claimed remote review; never starts it."""
        remote_task = validate_stateful_remote_task_path(remote_task)
        session_id = _require_session_id(review_execution_session_id)
        if (type(request_sha256) is not str or len(request_sha256) != 64
                or any(item not in "0123456789abcdef" for item in request_sha256)):
            raise Stage11DeploymentValidationError(
                "review request digest is invalid"
            )
        try:
            settings = validate_settings_evidence(dict(hermes_execution_settings))
        except Exception as error:
            raise Stage11DeploymentValidationError(
                "pinned Hermes settings evidence is invalid"
            ) from error
        if command_sha256 is not None and (
            type(command_sha256) is not str or len(command_sha256) != 64
            or any(item not in "0123456789abcdef" for item in command_sha256)
        ):
            raise Stage11DeploymentValidationError(
                "review command digest is invalid"
            )
        if (isinstance(timeout_seconds, bool)
                or not isinstance(timeout_seconds, (int, float))
                or not math.isfinite(timeout_seconds)
                or timeout_seconds <= 0):
            raise Stage11DeploymentValidationError(
                "review status transport timeout is invalid"
            )
        arguments = ["status", remote_task, session_id, request_sha256]
        if command_sha256 is not None:
            arguments.append(command_sha256)
        try:
            raw = self._python(
                _REMOTE_QUALITY_REVIEW_EXECUTION_SCRIPT,
                *arguments,
                capture=True,
                timeout=timeout_seconds,
                python_executable=REMOTE_HERMES_PYTHON,
            )
            value = json.loads(raw.decode("ascii"))
        except (UnicodeError, ValueError, json.JSONDecodeError) as error:
            raise Stage11DeploymentTransportError(
                "CT120 review status response is malformed"
            ) from error
        if type(value) is not dict or value.get("state") not in {
            "NOT_STARTED", "STARTING", "RUNNING", "SUPERVISOR_LOST",
            "COMPLETED", "FAILED", "TIMED_OUT", "CLEANUP_UNVERIFIED",
            "START_FAILED", "SUPERVISOR_ERROR",
        }:
            raise Stage11DeploymentTransportError(
                "CT120 review status is invalid"
            )
        receipt = value.get("receipt")
        if value["state"] in {
            "COMPLETED", "FAILED", "TIMED_OUT", "CLEANUP_UNVERIFIED",
            "START_FAILED", "SUPERVISOR_ERROR",
        }:
            if type(receipt) is not dict:
                raise Stage11DeploymentTransportError(
                    "CT120 terminal review status lacks a receipt"
                )
            try:
                validate_remote_execution_receipt(
                    receipt,
                    review_execution_session_id=session_id,
                    request_sha256=request_sha256,
                    hermes_execution_settings=settings,
                )
            except Exception as error:
                raise Stage11DeploymentTransportError(
                    "CT120 review completion receipt is invalid"
                ) from error
            if receipt["state"] != value["state"]:
                raise Stage11DeploymentTransportError(
                    "CT120 review status and receipt differ"
                )
        elif receipt is not None:
            raise Stage11DeploymentTransportError(
                "nonterminal review status has an unexpected receipt"
            )
        return value

    def launch_quality_review(
        self,
        command: list[str],
        *,
        remote_task: str,
        timeout: int | float,
        execution_timeout: int,
        timeout_env: Mapping[str, str],
        review_execution_session_id: str,
        request_sha256: str,
        hermes_execution_settings: Mapping[str, object],
    ) -> SimpleNamespace:
        remote_task = validate_stateful_remote_task_path(remote_task)
        session_id = _require_session_id(review_execution_session_id)
        if type(command) is not list or not command or not all(
            type(item) is str and item for item in command
        ):
            raise Stage11DeploymentValidationError(
                "native review command is malformed"
            )
        if (type(timeout_env) is not dict
                or timeout_env != dict(STAGE11_HERMES_TIMEOUT_ENV)):
            raise Stage11DeploymentValidationError(
                "Stage11 Hermes timeout environment differs"
            )
        if (type(timeout) is not int
                or timeout != QUALITY_REVIEW_TRANSPORT_TIMEOUT_SECONDS
                or type(execution_timeout) is not int
                or execution_timeout != QUALITY_REVIEW_REMOTE_EXECUTION_TIMEOUT_SECONDS):
            raise Stage11DeploymentValidationError(
                "remote review execution and transport bounds differ"
            )
        if (type(request_sha256) is not str or len(request_sha256) != 64
                or any(item not in "0123456789abcdef" for item in request_sha256)):
            raise Stage11DeploymentValidationError(
                "review request digest is invalid"
            )
        try:
            settings = validate_settings_evidence(dict(hermes_execution_settings))
        except Exception as error:
            raise Stage11DeploymentValidationError(
                "pinned Hermes settings evidence is invalid"
            ) from error
        command_sha = hashlib.sha256(
            json.dumps(command, ensure_ascii=True, sort_keys=True,
                       separators=(",", ":"), allow_nan=False).encode("ascii")
        ).hexdigest()
        intent = {
            "command": command,
            "command_sha256": command_sha,
            "hermes_execution_settings": settings,
            "timeout_environment": dict(timeout_env),
            "timeout_seconds": execution_timeout,
            "review_execution_session_id": session_id,
            "request_sha256": request_sha256,
            "supervisor_script": _REMOTE_QUALITY_REVIEW_EXECUTION_SCRIPT,
        }
        intent_payload = json.dumps(
            intent, ensure_ascii=True, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("ascii")
        if len(intent_payload) > 1024 * 1024:
            raise Stage11DeploymentValidationError(
                "remote review command exceeds the bounded intent size"
            )
        deadline = time.monotonic() + timeout
        start_error = None
        try:
            raw = self._python(
                _REMOTE_QUALITY_REVIEW_EXECUTION_SCRIPT,
                "start", remote_task, session_id, request_sha256,
                input_payload=intent_payload,
                capture=True,
                timeout=QUALITY_REVIEW_REMOTE_CALL_TIMEOUT_SECONDS,
                python_executable=REMOTE_HERMES_PYTHON,
            )
            start = json.loads(raw.decode("ascii"))
            if type(start) is not dict or start.get("state") not in {
                "START_ACCEPTED", "CLAIM_EXISTS", "START_FAILED",
            }:
                raise Stage11DeploymentTransportError(
                    "CT120 review start response is invalid"
                )
        except Exception as error:
            # A lost SSH response is not permission to start a second remote
            # process.  Continue with read-only status checks for this UUID.
            start_error = error

        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                status = self.read_quality_review_execution(
                    remote_task=remote_task,
                    review_execution_session_id=session_id,
                    request_sha256=request_sha256,
                    hermes_execution_settings=settings,
                    command_sha256=command_sha,
                    timeout_seconds=min(
                        QUALITY_REVIEW_REMOTE_CALL_TIMEOUT_SECONDS,
                        remaining,
                    ),
                )
            except Stage11DeploymentTransportError:
                time.sleep(min(
                    QUALITY_REVIEW_STATUS_POLL_SECONDS,
                    max(0.0, deadline - time.monotonic()),
                ))
                continue
            state = status["state"]
            if state in {
                "COMPLETED", "FAILED", "TIMED_OUT", "CLEANUP_UNVERIFIED",
                "START_FAILED", "SUPERVISOR_ERROR",
            }:
                receipt = status["receipt"]
                if state != "COMPLETED":
                    return SimpleNamespace(
                        returncode=receipt["exit_code"],
                        execution_receipt=receipt,
                    )
                result_payload = self.read_regular(
                    remote_task + "/" + QUALITY_REVIEW_RESULT_FILENAME,
                    max_bytes=16 * 1024 * 1024,
                )
                if hashlib.sha256(result_payload).hexdigest() != receipt["result_sha256"]:
                    raise Stage11DeploymentTransportError(
                        "CT120 review result changed after its completion receipt"
                    )
                return SimpleNamespace(
                    returncode=receipt["exit_code"],
                    execution_receipt=receipt,
                    result_payload=result_payload,
                )
            if state in {"NOT_STARTED", "SUPERVISOR_LOST"}:
                raise Stage11DeploymentTransportError(
                    "CT120 review execution state is not owned or verifiable; session="
                    + session_id
                ) from start_error
            time.sleep(min(
                QUALITY_REVIEW_STATUS_POLL_SECONDS,
                max(0.0, deadline - time.monotonic()),
            ))
        raise Stage11DeploymentTransportError(
            "CT120 review completion was not verified before the transport bound; session="
            + session_id
        ) from start_error


class RemoteNativeSessionDB:
    """SessionDB-shaped proxy backed by the native CT120 API bridge."""

    def __init__(self, bridge: object, *, expected_profile_name: str):
        if not callable(getattr(bridge, "get_session", None)) or not callable(
            getattr(bridge, "create_session", None)
        ) or not callable(getattr(bridge, "get_messages", None)):
            raise Stage11DeploymentValidationError(
                "native remote bridge lacks SessionDB methods"
            )
        self.bridge = bridge
        self.expected_profile_name = _profile_name(expected_profile_name)

    def get_session(self, session_id: str):
        return self.bridge.get_session(session_id)

    def create_session(self, *, session_id: str, source: str, profile_name: str):
        if profile_name != self.expected_profile_name:
            raise Stage11DeploymentValidationError(
                "Hybrid requested an unexpected Hermes profile"
            )
        return self.bridge.create_session(
            session_id=session_id,
            source=source,
            profile_name=profile_name,
        )

    def get_messages(self, session_id: str, *, include_inactive: bool = False):
        return self.bridge.get_messages(
            session_id,
            include_inactive=include_inactive,
        )


def _prepare_remote_factory(
    config: Stage11DeploymentConfig,
    bridge: object,
    remote_task_for_session: Callable[[str], str],
) -> Callable:
    ensure_task = getattr(bridge, "ensure_task", None)
    ensure_file = getattr(bridge, "ensure_file", None)
    ensure_session = getattr(bridge, "ensure_stateful_session", None)
    if not callable(ensure_task) or not callable(ensure_file) or not callable(
        ensure_session
    ):
        raise Stage11DeploymentValidationError(
            "remote bridge lacks first-pass preparation methods"
        )

    def prepare_remote(package, paths, *, route: str):
        if route not in {"ASR_ONLY", "HYBRID"}:
            raise Stage11DeploymentValidationError(
                "first-pass route is unsupported"
            )
        try:
            package.__post_init__()
        except AttributeError as error:
            raise Stage11DeploymentValidationError(
                "first-pass package is invalid"
            ) from error
        model_package = build_stateful_model_input_package(package)
        if model_package != package:
            try:
                model_input_identity_bound = stateful_model_input_identity_is_bound(
                    package.generation_key
                )
            except Exception as error:
                raise Stage11DeploymentValidationError(
                    "changed model input has an invalid normalization identity"
                ) from error
            if not model_input_identity_bound:
                raise Stage11DeploymentValidationError(
                    "changed model input requires an explicit normalization identity"
                )
        expected_payload = serialize_stateful_model_input(package)
        if _private_local_read(paths.input_path, max_bytes=len(expected_payload)) != expected_payload:
            raise Stage11DeploymentValidationError(
                "local first-pass input differs from package"
            )
        session_id = stateful_session_id_for_package(package)
        remote_task = remote_task_for_session(session_id)
        ensure_task(remote_task)
        ensure_session(session_id)
        ensure_file(
            remote_task + "/" + STATEFUL_TRANSLATOR_INPUT_FILENAME,
            expected_payload,
        )
        return remote_task

    return prepare_remote


def _hybrid_launcher_factory(
    bridge: object,
    remote_task_for_session: Callable[[str], str],
) -> Callable:
    ensure_task = getattr(bridge, "ensure_task", None)
    ensure_file = getattr(bridge, "ensure_file", None)
    read_regular = getattr(bridge, "read_regular", None)
    launch = getattr(bridge, "launch_quality_review", None)
    if not all(callable(value) for value in (ensure_task, ensure_file, read_regular, launch)):
        raise Stage11DeploymentValidationError(
            "remote bridge lacks Hybrid review methods"
        )

    def launcher(
        command,
        *,
        cwd,
        timeout,
        execution_timeout,
        env,
        review_execution_session_id,
        request_sha256,
        hermes_execution_settings,
    ):
        if type(cwd) is not int or cwd < 0:
            raise Stage11DeploymentValidationError(
                "Hybrid launcher received an invalid pinned directory"
            )
        if not isinstance(env, Mapping) or any(
            env.get(key) != value
            for key, value in STAGE11_HERMES_TIMEOUT_ENV.items()
        ):
            raise Stage11DeploymentValidationError(
                "Hybrid launcher lacks the approved Stage11 timeout values"
            )
        if type(command) is not list or not all(type(item) is str for item in command):
            raise Stage11DeploymentValidationError(
                "Hybrid launcher command is malformed"
            )
        try:
            resume_index = command.index("--resume")
            session_id = _require_session_id(command[resume_index + 1])
        except (ValueError, IndexError) as error:
            raise Stage11DeploymentValidationError(
                "Hybrid launcher command has no canonical session"
            ) from error
        query_indexes = [index for index, value in enumerate(command) if value == "-q"]
        if len(query_indexes) != 1 or query_indexes[0] + 1 >= len(command):
            raise Stage11DeploymentValidationError(
                "Hybrid launcher command has no unique query"
            )
        local_task = _local_task_from_fd(cwd)
        local_input = str(local_task / QUALITY_REVIEW_INPUT_FILENAME)
        local_result = str(local_task / QUALITY_REVIEW_RESULT_FILENAME)
        query_index = query_indexes[0] + 1
        query = command[query_index]
        if local_input not in query or local_result not in query:
            raise Stage11DeploymentValidationError(
                "Hybrid query lacks exact local file authority"
            )
        payload = _private_local_read_at(
            cwd,
            QUALITY_REVIEW_INPUT_FILENAME,
            max_bytes=16 * 1024 * 1024,
        )
        if hashlib.sha256(payload).hexdigest() != request_sha256:
            raise Stage11DeploymentValidationError(
                "Hybrid review request digest differs from staged input"
            )
        if session_id != review_execution_session_id:
            raise Stage11DeploymentValidationError(
                "Hybrid review execution session differs from command"
            )
        try:
            settings = validate_settings_evidence(
                dict(hermes_execution_settings)
            )
        except Exception as error:
            raise Stage11DeploymentValidationError(
                "Hybrid review settings evidence is invalid"
            ) from error
        remote_task = remote_task_for_session(session_id)
        remote_input = remote_task + "/" + QUALITY_REVIEW_INPUT_FILENAME
        remote_result = remote_task + "/" + QUALITY_REVIEW_RESULT_FILENAME
        ensure_task(remote_task)
        ensure_file(remote_input, payload)
        remote_command = list(command)
        remote_command[query_index] = query.replace(str(local_task), remote_task)
        if local_input in remote_command[query_index] or local_result in remote_command[query_index]:
            raise Stage11DeploymentValidationError(
                "Hybrid query retained local file authority"
            )
        completed = launch(
            remote_command,
            remote_task=remote_task,
            timeout=timeout,
            execution_timeout=execution_timeout,
            timeout_env=dict(STAGE11_HERMES_TIMEOUT_ENV),
            review_execution_session_id=session_id,
            request_sha256=request_sha256,
            hermes_execution_settings=settings,
        )
        receipt = getattr(completed, "execution_receipt", None)
        if receipt is None:
            raise Stage11DeploymentTransportError(
                "CT120 review completion receipt is missing"
            )
        try:
            validate_remote_execution_receipt(
                receipt,
                review_execution_session_id=session_id,
                request_sha256=request_sha256,
                hermes_execution_settings=settings,
            )
        except Exception as error:
            raise Stage11DeploymentTransportError(
                "CT120 review completion receipt is invalid"
            ) from error
        if receipt["state"] != "COMPLETED":
            return completed
        result_payload = getattr(completed, "result_payload", None)
        if type(result_payload) is not bytes:
            result_payload = read_regular(
                remote_result, max_bytes=16 * 1024 * 1024
            )
        if hashlib.sha256(result_payload).hexdigest() != receipt["result_sha256"]:
            raise Stage11DeploymentTransportError(
                "CT120 review result differs from completion receipt"
            )
        _private_local_write_at(cwd, QUALITY_REVIEW_RESULT_FILENAME, result_payload)
        return completed

    return launcher


@dataclass
class _HybridOriginalRegistry:
    """One-title caller-held originals; no semantic evidence is synthesized."""

    targeted_artifact_provider: Callable | None = None

    def __post_init__(self):
        self._applications: dict[str, tuple[object, AlignmentAcceptanceApplicationResult]] = {}
        self._first_pass: dict[str, tuple[object, object]] = {}
        self._targeted: dict[str, TargetedSecondEvidenceArtifact] = {}

    def capture_external(self, callback: Callable) -> Callable:
        accepts_diagnostic = bool(
            getattr(callback, "_stage11_accepts_diagnostic", False)
        )

        def wrapped(canonical_video, asr_result, *, diagnostic_out=None):
            if accepts_diagnostic:
                application = callback(
                    canonical_video, asr_result, diagnostic_out=diagnostic_out
                )
            else:
                application = callback(canonical_video, asr_result)
            if application is None:
                return None
            if type(application) is not AlignmentAcceptanceApplicationResult:
                raise Stage11DeploymentValidationError(
                    "external callback returned an invalid application"
                )
            application.__post_init__()
            if (
                application.bundle.dvd_id != canonical_video.dvd_id
                or application.bundle.asr_result != asr_result
            ):
                raise Stage11DeploymentValidationError(
                    "captured external application is detached"
                )
            self._applications[canonical_video.dvd_id] = (
                canonical_video,
                application,
            )
            return application

        if accepts_diagnostic:
            wrapped._stage11_accepts_diagnostic = True
        return wrapped

    def capture_first_pass(self, callback: Callable) -> Callable:
        def wrapped(
            package,
            *,
            route,
            staging_root,
            semantic_policy=None,
            boundary_evidence=None,
            hermes_settings=None,
        ):
            callback_kwargs = {
                "route": route,
                "staging_root": staging_root,
            }
            if semantic_policy is not None:
                callback_kwargs["semantic_policy"] = semantic_policy
            if boundary_evidence is not None:
                callback_kwargs["boundary_evidence"] = boundary_evidence
            if hermes_settings is not None:
                callback_kwargs["hermes_settings"] = hermes_settings
            result = callback(package, **callback_kwargs)
            if route == V2_ROUTE_HYBRID:
                try:
                    result = validate_stateful_result(
                        result, package, boundary_evidence=boundary_evidence
                    )
                    session_id = stateful_session_id_for_package(package)
                    if result.session_id != session_id:
                        raise ValueError("first-pass session differs from package")
                except Exception as error:
                    raise Stage11DeploymentValidationError(
                        "Hybrid package session identity is invalid"
                    ) from error
                self._first_pass[session_id] = (package, result)
            return result

        return wrapped

    def capture_targeted(self, callback: Callable) -> Callable:
        def wrapped(asr_result, decisions):
            execution = callback(asr_result, decisions)
            try:
                execution.__post_init__()
                artifact = targeted_second_evidence_artifact_from_execution(
                    execution,
                    baseline_asr_artifact_sha256=hashlib.sha256(
                        serialize_asr_result(asr_result)
                    ).hexdigest(),
                    runtime_identity=asr_result.runtime_identity,
                    engine_version=asr_result.engine_version,
                )
                artifact.__post_init__()
            except Exception as error:
                raise Stage11DeploymentValidationError(
                    "targeted execution could not be retained for review"
                ) from error
            self._targeted[asr_result.source_snapshot.dvd_id] = artifact
            return execution

        return wrapped

    def originals_provider(self, request: QualityReviewRequest) -> Mapping[str, object]:
        if type(request) is not QualityReviewRequest:
            raise Stage11DeploymentValidationError(
                "Hybrid originals provider received an invalid request"
            )
        request.__post_init__()
        source_session = request.source_translation_session_id
        package_result = self._first_pass.get(source_session)
        if package_result is None:
            raise Stage11DeploymentValidationError(
                "Hybrid first-pass originals are not retained"
            )
        package, result = package_result
        dvd_id = package.dvd_id
        external = self._applications.get(dvd_id)
        if external is None:
            raise Stage11DeploymentValidationError(
                "Hybrid external application is not retained"
            )
        canonical_video, application = external
        if application.decision.verdict != "ACCEPT_HYBRID":
            raise Stage11DeploymentValidationError(
                "Hybrid originals require an accepted external application"
            )
        route = SubtitleV2RouteDecision(
            canonical_video=canonical_video,
            route=V2_ROUTE_HYBRID,
            state=V2_READY_FOR_SEMANTIC,
            alignment_application=application,
        )
        preparation = prepare_stateful_hybrid(
            route,
            generation_key=package.generation_key,
            claim_token=package.claim_token,
        )
        if preparation.package != package:
            raise Stage11DeploymentValidationError(
                "Hybrid package is detached from retained route evidence"
            )
        source_quality = classify_source_document(
            application.bundle.external_ja_document
        )
        targeted = self._targeted.get(dvd_id)
        has_targeted_projection = any(
            cue.targeted_second_evidence is not None for cue in request.cues
        )
        if has_targeted_projection and targeted is None:
            if self.targeted_artifact_provider is None:
                raise Stage11DeploymentValidationError(
                    "Hybrid targeted artifact is not retained"
                )
            targeted = self.targeted_artifact_provider(request, asr_result=application.bundle.asr_result)
            if type(targeted) is not TargetedSecondEvidenceArtifact:
                raise Stage11DeploymentValidationError(
                    "targeted artifact provider returned an invalid artifact"
                )
            targeted.__post_init__()
        originals = {
            "preparation": preparation,
            "package": package,
            "result": result,
            "source_quality": source_quality,
            "targeted_second_evidence_artifact": targeted,
        }
        try:
            expected = build_review_request(**originals)
        except Exception as error:
            raise Stage11DeploymentValidationError(
                "Hybrid originals failed native request revalidation"
            ) from error
        if expected != request:
            raise Stage11DeploymentValidationError(
                "Hybrid review request is detached from retained originals"
            )
        return originals


def _merge_options(
    defaults: Mapping[str, object],
    overrides: Mapping[str, object] | None,
    *,
    field_name: str,
) -> dict[str, object]:
    if overrides is None:
        return dict(defaults)
    if not isinstance(overrides, Mapping):
        raise Stage11DeploymentValidationError(field_name + " must be a mapping")
    result = dict(defaults)
    result.update(overrides)
    return result


def _reject_owned_option_overrides(
    overrides: Mapping[str, object] | None,
    owned: Mapping[str, object],
    *,
    field_name: str,
) -> None:
    if overrides is None:
        return
    for key, expected in owned.items():
        if key not in overrides:
            continue
        actual = overrides[key]
        same = actual is expected if callable(expected) else actual == expected
        if not same:
            raise Stage11DeploymentValidationError(
                field_name + " contains a deployment-owned override"
            )


@dataclass(frozen=True)
class Stage11DeploymentDependencies:
    """Resolved deployment components plus the native live adapter bundle."""

    config: Stage11DeploymentConfig
    source_provider: object
    whisper: object
    targeted_transport: object
    discovery: object
    provider: SubtitleCatProvider
    remote_bridge: object
    remote_task_for_session: Callable
    prepare_remote: Callable
    originals_provider: Callable
    live: Stage11LiveDependencies
    _first_pass_capture: Callable
    _external_capture: Callable

    def resolve_hermes_settings(self):
        """Resolve one read-only profile/runtime snapshot from the Hermes host."""
        resolver = getattr(self.remote_bridge, "resolve_stage11_hermes_settings", None)
        if not callable(resolver):
            raise Stage11DeploymentValidationError(
                "Stage11 Hermes profile resolver is unavailable"
            )
        return resolver()

    def controller_kwargs(self) -> dict[str, Callable]:
        """Return only the existing controller-facing callable contract."""

        return {
            "holding_resolver": self.live.holding_resolver,
            "baseline_transcriber": self.live.baseline_transcriber,
            "external_ja_attempt": self.live.external_ja_attempt,
            "targeted_runner": self.live.targeted_runner,
            "first_pass_runner": self.live.first_pass_runner,
            "asr_review_runner": self.live.asr_review_runner,
            "hybrid_review_runner": self.live.hybrid_review_runner,
            "hybrid_targeted_runner": self.live.hybrid_targeted_runner,
        }

    @property
    def bounded_hybrid_targeted_runner(self) -> Callable | None:
        """Expose only the hybrid callback backed by an owned worker lifecycle."""
        runner = self.live.hybrid_targeted_runner
        if getattr(runner, "bounded_worker_lifecycle", False) is True:
            return runner
        return None

    def capture_first_pass_runner(self, callback: Callable) -> Callable:
        """Retain Normal's native result at the existing HYBRID trust boundary."""
        return self._first_pass_capture(callback)

    def capture_external_ja_attempt(self, callback: Callable) -> Callable:
        """Retain Normal's accepted external JA application for review replay."""
        return self._external_capture(callback)


def _build_targeted_asr_transport(config, override=None):
    if override is not None:
        return override
    from teddy_discovery_asr_bounded_worker import BoundedTargetedASRTransport

    return BoundedTargetedASRTransport(
        config_path=config.targeted_asr_worker_config_path,
        request_timeout_seconds=min(float(config.request_timeout_seconds), 900.0),
    )


def _build_asr_transports(config, *, whisper=None, targeted_transport=None):
    """Share one lazy worker transport for production full-title and targeted ASR."""
    live_whisper = whisper
    if live_whisper is None:
        live_whisper = _build_targeted_asr_transport(config)
    if targeted_transport is not None:
        live_targeted = targeted_transport
    elif (getattr(live_whisper, "bounded_worker_lifecycle", False) is True
          and callable(getattr(live_whisper, "session", None))):
        live_targeted = live_whisper
    else:
        live_targeted = _build_targeted_asr_transport(config)
    return live_whisper, live_targeted


def build_stage11_deployment_dependencies(
    config: Stage11DeploymentConfig,
    *,
    acceptance_policy,
    residual_threshold_ms,
    holding_resolver: Callable | None = None,
    source_provider: object | None = None,
    whisper: object | None = None,
    targeted_transport: object | None = None,
    discovery: object | None = None,
    provider: SubtitleCatProvider | None = None,
    remote_bridge: object | None = None,
    remote_runner: Callable = subprocess.run,
    native_first_pass_run: Callable = native_stateful_run,
    first_pass_options: Mapping[str, object] | None = None,
    asr_review_options: Mapping[str, object] | None = None,
    hybrid_review_options: Mapping[str, object] | None = None,
    targeted_artifact_provider: Callable | None = None,
    audio_chunk_iterator: Callable = iter_audio_chunks,
) -> Stage11DeploymentDependencies:
    """Build deployment values and feed them into the existing live factory."""

    if type(config) is not Stage11DeploymentConfig:
        raise Stage11DeploymentValidationError(
            "deployment config must be Stage11DeploymentConfig"
        )
    if not callable(native_first_pass_run):
        raise Stage11DeploymentValidationError(
            "native_first_pass_run must be callable"
        )
    if targeted_artifact_provider is not None and not callable(
        targeted_artifact_provider
    ):
        raise Stage11DeploymentValidationError(
            "targeted_artifact_provider must be callable"
        )

    resolver = holding_resolver
    if resolver is None:
        from teddy_discovery_stage11_live_adapters import build_holding_resolver

        resolver = build_holding_resolver()
    if not callable(resolver):
        raise Stage11DeploymentValidationError("holding_resolver must be callable")

    source = source_provider
    if source is None:
        source = ASRMediaSourceReader(
            host=config.nas_host,
            user=config.nas_user,
            key=config.nas_key,
            known_hosts=config.nas_known_hosts,
            library_root=config.nas_library_root,
            temp_root=config.asr_media_temp_root,
            require_disk_backed=True,
            reserve_bytes=config.asr_media_temp_reserve_bytes,
        )
    live_whisper, live_targeted = _build_asr_transports(
        config, whisper=whisper, targeted_transport=targeted_transport)
    live_discovery = discovery
    if live_discovery is None:
        live_discovery = SubtitleCatDiscovery(
            timeout=config.subtitlecat_timeout_seconds,
            proxy_url=config.subtitlecat_proxy_url,
        )
    live_provider = provider
    if live_provider is None:
        live_provider = build_subtitlecat_provider(
            timeout=config.subtitlecat_timeout_seconds,
            proxy_url=config.subtitlecat_proxy_url,
        )

    bridge = remote_bridge
    if bridge is None:
        bridge = SSHRemoteHermesBridge(config, runner=remote_runner)
    remote_task_for_session = _make_remote_task_factory(config)
    prepare_remote = _prepare_remote_factory(
        config,
        bridge,
        remote_task_for_session,
    )
    originals_registry = _HybridOriginalRegistry(
        targeted_artifact_provider=targeted_artifact_provider,
    )
    hybrid_launcher = _hybrid_launcher_factory(bridge, remote_task_for_session)

    first_options = _merge_options(
        {
            "remote": f"{config.remote_user}@{config.remote_host}",
            "ssh_key": config.ssh_key,
            "known_hosts": config.known_hosts,
            "prepare_remote": prepare_remote,
            "native_run": native_first_pass_run,
        },
        first_pass_options,
        field_name="first_pass_options",
    )
    for key, expected in {
        "remote": f"{config.remote_user}@{config.remote_host}",
        "ssh_key": config.ssh_key,
        "known_hosts": config.known_hosts,
        "prepare_remote": prepare_remote,
        "native_run": native_first_pass_run,
    }.items():
        if first_options[key] is not expected and key in {
            "prepare_remote",
            "native_run",
        }:
            raise Stage11DeploymentValidationError(
                "first-pass deployment-owned option cannot be replaced"
            )
        if key in {"remote", "ssh_key", "known_hosts"} and first_options[key] != expected:
            raise Stage11DeploymentValidationError(
                "first-pass connection option differs from deployment config"
            )

    asr_native_defaults = {
        "remote_host": config.remote_host,
        "remote_user": config.remote_user,
        "ssh_key": config.ssh_key,
        "known_hosts": config.known_hosts,
    }
    _reject_owned_option_overrides(
        asr_review_options,
        asr_native_defaults,
        field_name="asr_review_options",
    )
    asr_native_options = _merge_options(
        asr_native_defaults,
        asr_review_options,
        field_name="asr_review_options",
    )
    hybrid_native_defaults = {
        "fresh_session_db": RemoteNativeSessionDB(
            bridge,
            expected_profile_name=config.expected_profile_name,
        ),
        "expected_profile_name": config.expected_profile_name,
        "launcher": hybrid_launcher,
    }
    _reject_owned_option_overrides(
        hybrid_review_options,
        hybrid_native_defaults,
        field_name="hybrid_review_options",
    )
    hybrid_native_options = _merge_options(
        hybrid_native_defaults,
        hybrid_review_options,
        field_name="hybrid_review_options",
    )

    live = build_stage11_live_dependencies(
        source_provider=source,
        whisper=live_whisper,
        targeted_transport=live_targeted,
        discovery=live_discovery,
        provider=live_provider,
        acceptance_policy=acceptance_policy,
        residual_threshold_ms=residual_threshold_ms,
        holding_resolver=resolver,
        audio_chunk_iterator=audio_chunk_iterator,
        first_pass_options=first_options,
        asr_review_options={
            "remote_task_for_session": remote_task_for_session,
            "runner_options": asr_native_options,
        },
        hermes_settings_resolver=bridge.resolve_stage11_hermes_settings,
        hybrid_review_options={
            "originals_provider": originals_registry.originals_provider,
            "runner_options": hybrid_native_options,
        },
    )
    live = replace(
        live,
        external_ja_attempt=originals_registry.capture_external(
            live.external_ja_attempt
        ),
        targeted_runner=originals_registry.capture_targeted(live.targeted_runner),
        first_pass_runner=originals_registry.capture_first_pass(
            live.first_pass_runner
        ),
    )
    return Stage11DeploymentDependencies(
        config=config,
        source_provider=source,
        whisper=live_whisper,
        targeted_transport=live_targeted,
        discovery=live_discovery,
        provider=live_provider,
        remote_bridge=bridge,
        remote_task_for_session=remote_task_for_session,
        prepare_remote=prepare_remote,
        originals_provider=originals_registry.originals_provider,
        live=live,
        _first_pass_capture=originals_registry.capture_first_pass,
        _external_capture=originals_registry.capture_external,
    )


__all__ = [
    "SSHRemoteHermesBridge",
    "RemoteNativeSessionDB",
    "Stage11DeploymentConfig",
    "Stage11DeploymentDependencies",
    "Stage11DeploymentError",
    "Stage11DeploymentTransportError",
    "Stage11DeploymentValidationError",
    "STAGE11_STANDALONE_CANARY_CLAIM_TOKEN",
    "build_stage11_deployment_dependencies",
    "build_subtitlecat_provider",
]
