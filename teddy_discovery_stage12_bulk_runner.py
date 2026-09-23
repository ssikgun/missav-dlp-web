#!/usr/bin/env python3
"""Durable serial Stage12 bulk subtitle runner with UI heartbeat.

The runner reuses the frozen Stage11 controller and Stage12 publication
contracts.  It selects only ordinary eligible PENDING titles, processes them
serially with title-level isolation, and writes a small atomic heartbeat for
the Downloader read-only status panel.

Preflight is read-only: no rollout DB writes, Hermes calls, ASR calls,
publication, or Jellyfin mutations.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import inspect
import json
import os
from pathlib import Path
import socket
import sqlite3
import stat
import subprocess
import sys
import threading
import time
import uuid
from urllib.parse import urlsplit


REPO = Path("/opt/missav-pwa-subtitle-stage11")
DISCOVERY_DB = Path(
    "/opt/missav-dlp-web/discovery/teddy-discovery.sqlite3"
)
ROLLOUT_DB = Path(
    "/opt/missav-dlp-web/discovery/stage12-rollout-state.sqlite3"
)

RUNTIME_STATUS_DIR = Path(
    "/opt/missav-dlp-web/discovery/stage12-runtime"
)
HEARTBEAT_PATH = RUNTIME_STATUS_DIR / "status.json"
LOCK_PATH = RUNTIME_STATUS_DIR / "bulk-runner.lock"

RUN_ROOT = Path(
    "/opt/missav-dlp-web/discovery/stage12-bulk-runtime-v1"
)
ARTIFACT_ROOT = RUN_ROOT / "artifacts"
STAGING_ROOT = RUN_ROOT / "staging"

REMOTE_TASK_ROOT = (
    "/home/teddy/.hermes/profiles/subtitle-translator/"
    "stage12-bulk-runtime-v1"
)

POLICY_ID = "stage11-stateful-cue64-v1"
MODEL_INPUT = "stage11-model-input=repeat-v2"
CLAIM_TOKEN = 2026091801

HEARTBEAT_INTERVAL_SECONDS = 30.0
DEFAULT_BATCH_SIZE = 4
JELLYFIN_FULL_REFRESH_MAX_ATTEMPTS = 42

AUTH_ENV = "TEDDY_STAGE12_BULK_ALLOW_LIVE"
AUTH_VALUE = "TEDDY_STAGE12_BULK_AUTHORIZED"
EXPLICIT_RETRY_AUTH_ENV = "TEDDY_STAGE12_EXPLICIT_RETRY_AUTHORIZED"
EXPLICIT_RETRY_AUTH_VALUE = "YES_I_HAVE_REVIEWED_THE_SINGLE_TITLE"
RECONCILE_AUTH_ENV = "TEDDY_STAGE12_PUBLICATION_RECONCILE_AUTHORIZED"
RECONCILE_AUTH_VALUE = "YES_I_HAVE_REVIEWED_THE_TITLE_EVIDENCE"

NAS = {
    "nas_host": "192.168.1.201",
    "nas_user": "ssikgun",
    "nas_key": "/opt/missav-dlp-web/teddy-nas-transfer/id_ed25519",
    "nas_known_hosts":
        "/opt/missav-dlp-web/teddy-nas-transfer/known_hosts",
    "nas_library_root": "/volume1/video/video2/JAV",
}

VM122_ASR_BASE_URL = "http://192.168.1.134:8091"
VM122_REQUEST_TIMEOUT_SECONDS = 1200

CT120_HOST = "192.168.1.230"
CT120_USER = "teddy"
CT120_SSH_KEY = "/root/.ssh/id_ed25519_stage11_hermes"
CT120_KNOWN_HOSTS = "/root/.ssh/known_hosts_stage11_hermes"

JELLYFIN_BASE_URL = "http://192.168.1.205:8096"
JELLYFIN_API_KEY = Path(
    "/opt/missav-dlp-web/teddy-jellyfin/jellyfin_api_key"
)


class Stage12BulkRunnerError(RuntimeError):
    pass


def emit(name: str, value: object) -> None:
    if isinstance(value, str):
        print(f"{name}={value}", flush=True)
        return

    print(
        name
        + "="
        + json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        flush=True,
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def git_query(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise Stage12BulkRunnerError(
            "git query failed: " + result.stderr.strip()
        )

    return result.stdout.strip()


def check_repo(expected_head: str) -> None:
    head = git_query("rev-parse", "HEAD")
    branch = git_query("branch", "--show-current")
    status = git_query(
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )

    emit("HEAD", head)
    emit("BRANCH", branch)

    if head != expected_head:
        raise Stage12BulkRunnerError(
            "repository HEAD differs from authorized HEAD"
        )

    if branch != "teddy-subtitle-stage11":
        raise Stage12BulkRunnerError(
            "unexpected repository branch"
        )

    if status:
        raise Stage12BulkRunnerError(
            "bulk runner requires a clean worktree"
        )

    emit("WORKTREE_CLEAN", "YES")


def require_regular(
    path: Path,
    *,
    mode: int | None = None,
) -> None:
    try:
        info = path.lstat()
    except OSError as error:
        raise Stage12BulkRunnerError(
            "required file unavailable: " + str(path)
        ) from error

    if path.is_symlink() or not stat.S_ISREG(info.st_mode):
        raise Stage12BulkRunnerError(
            "required path is not a regular file: " + str(path)
        )

    if (
        mode is not None
        and stat.S_IMODE(info.st_mode) != mode
    ):
        raise Stage12BulkRunnerError(
            "unexpected file mode: " + str(path)
        )


def inspect_runtime_directories() -> None:
    paths = (
        RUNTIME_STATUS_DIR,
        RUN_ROOT,
        ARTIFACT_ROOT,
        STAGING_ROOT,
    )

    for path in paths:
        try:
            info = path.lstat()
        except FileNotFoundError:
            emit(
                "LOCAL_RUNTIME_PATH",
                {
                    "path": str(path),
                    "status": "ABSENT",
                },
            )
            continue

        if path.is_symlink() or not stat.S_ISDIR(info.st_mode):
            raise Stage12BulkRunnerError(
                "runtime path is not a safe directory: "
                + str(path)
            )

        emit(
            "LOCAL_RUNTIME_PATH",
            {
                "path": str(path),
                "status": "DIRECTORY",
            },
        )


def ensure_runtime_directories() -> None:
    if (
        not RUNTIME_STATUS_DIR.is_dir()
        or RUNTIME_STATUS_DIR.is_symlink()
    ):
        raise Stage12BulkRunnerError(
            "heartbeat directory is unavailable or unsafe"
        )

    for path in (
        RUN_ROOT,
        ARTIFACT_ROOT,
        STAGING_ROOT,
    ):
        if path.exists() or path.is_symlink():
            info = path.lstat()

            if (
                path.is_symlink()
                or not stat.S_ISDIR(info.st_mode)
            ):
                raise Stage12BulkRunnerError(
                    "runtime path is unsafe: " + str(path)
                )
        else:
            path.mkdir(mode=0o700)

        os.chmod(path, 0o700)


def ssh_command(script: str, *args: str):
    return subprocess.run(
        [
            "ssh",
            "-i",
            CT120_SSH_KEY,
            "-o",
            "BatchMode=yes",
            "-o",
            "UserKnownHostsFile=" + CT120_KNOWN_HOSTS,
            f"{CT120_USER}@{CT120_HOST}",
            "bash",
            "-s",
            "--",
            *args,
        ],
        input=script.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )


def inspect_remote_root() -> None:
    script = r'''
ROOT="$1"

if [ -L "$ROOT" ]; then
  echo "STATUS=SYMLINK"
elif [ -e "$ROOT" ]; then
  if [ -d "$ROOT" ]; then
    echo "STATUS=DIRECTORY"
    echo "MODE=$(stat -c '%a' "$ROOT")"
    echo "OWNER=$(stat -c '%U' "$ROOT")"
  else
    echo "STATUS=NON_DIRECTORY"
  fi
else
  echo "STATUS=ABSENT"
fi
'''

    result = ssh_command(
        script,
        REMOTE_TASK_ROOT,
    )

    output = result.stdout.decode(
        "utf-8",
        errors="replace",
    ).strip()

    emit("REMOTE_RUNTIME_PREFLIGHT", output)

    if result.returncode != 0:
        raise Stage12BulkRunnerError(
            "CT120 remote-root preflight failed"
        )

    if "STATUS=ABSENT" in output:
        return

    if (
        "STATUS=DIRECTORY" not in output
        or "MODE=700" not in output
        or "OWNER=teddy" not in output
    ):
        raise Stage12BulkRunnerError(
            "existing CT120 runtime root is unsafe"
        )


def ensure_remote_root() -> None:
    script = r'''
ROOT="$1"

if [ -L "$ROOT" ]; then
  echo "RESULT=SYMLINK"
elif [ -e "$ROOT" ]; then
  if [ -d "$ROOT" ]; then
    echo "RESULT=EXISTING"
  else
    echo "RESULT=NON_DIRECTORY"
  fi
else
  umask 077
  if mkdir -- "$ROOT"; then
    echo "RESULT=CREATED"
  else
    echo "RESULT=CREATE_FAILED"
  fi
fi

if [ -d "$ROOT" ] && [ ! -L "$ROOT" ]; then
  echo "MODE=$(stat -c '%a' "$ROOT")"
  echo "OWNER=$(stat -c '%U' "$ROOT")"
fi
'''

    result = ssh_command(
        script,
        REMOTE_TASK_ROOT,
    )

    output = result.stdout.decode(
        "utf-8",
        errors="replace",
    ).strip()

    emit("REMOTE_RUNTIME_PROVISION", output)

    if result.returncode != 0:
        raise Stage12BulkRunnerError(
            "CT120 runtime-root provisioning failed"
        )

    if not (
        (
            "RESULT=CREATED" in output
            or "RESULT=EXISTING" in output
        )
        and "MODE=700" in output
        and "OWNER=teddy" in output
    ):
        raise Stage12BulkRunnerError(
            "CT120 runtime root failed verification"
        )


def network_probe() -> None:
    endpoints = (
        ("CT120", CT120_HOST, 22),
        ("VM122", "192.168.1.134", 8091),
        ("NAS", NAS["nas_host"], 22),
        ("JELLYFIN", "192.168.1.205", 8096),
        ("SUBTITLECAT_PROXY", "127.0.0.1", 58888),
    )

    failures: list[str] = []

    for label, host, port in endpoints:
        try:
            with socket.create_connection(
                (host, port),
                timeout=3.0,
            ):
                pass
        except OSError as error:
            value = "FAIL_" + type(error).__name__
            failures.append(label)
        else:
            value = "PASS_TCP_CONNECT"

        emit("CONNECTIVITY_" + label, value)

    if failures:
        raise Stage12BulkRunnerError(
            "required connectivity failed: "
            + ",".join(failures)
        )


def contract_check() -> None:
    from teddy_discovery_model_input_normalization import (
        MODEL_INPUT_NORMALIZATION_VERSION,
    )
    from teddy_discovery_stage11_controller import (
        run_one_title_stage11,
    )
    from teddy_discovery_stage11_live_adapters import (
        build_external_ja_adapter,
    )
    from teddy_discovery_stage12_batch import (
        Stage12BatchRunner,
        _jellyfin_external_subtitle_probe,
        recognize_jellyfin_external_subtitle,
    )
    from teddy_discovery_stateful_live_runner import (
        CANDIDATE_HERMES_ABSOLUTE_TIMEOUT_SECONDS,
        DEFAULT_HERMES_INACTIVITY_TIMEOUT_SECONDS,
        STATEFUL_PART_MODEL_MAX_ATTEMPTS,
        _cleanup_timed_out_remote_hermes,
        _invoke_hermes_part,
    )
    from teddy_discovery_stateful_parts import (
        STATEFUL_PART_BATCH_SIZE,
        STATEFUL_PART_POLICY_ID,
    )
    from teddy_discovery_stateful_policy import (
        DEFAULT_STATEFUL_SEMANTIC_POLICY,
        STATEFUL_SEMANTIC_POLICY_ID_64,
        resolve_stateful_semantic_policy,
    )
    from teddy_discovery_subtitle_publish import (
        REMOTE_SUBTITLE_PUBLISH_SCRIPT,
    )

    policy = resolve_stateful_semantic_policy(
        STATEFUL_SEMANTIC_POLICY_ID_64
    )

    if (
        policy.policy_id != POLICY_ID
        or policy.max_cues_per_part != 64
        or DEFAULT_STATEFUL_SEMANTIC_POLICY.policy_id
        != POLICY_ID
        or DEFAULT_STATEFUL_SEMANTIC_POLICY.max_cues_per_part
        != 64
        or STATEFUL_PART_POLICY_ID != POLICY_ID
        or STATEFUL_PART_BATCH_SIZE != 64
    ):
        raise Stage12BulkRunnerError(
            "current cue64 production policy contract changed"
        )

    if MODEL_INPUT_NORMALIZATION_VERSION != MODEL_INPUT:
        raise Stage12BulkRunnerError(
            "model input contract is not repeat-v2"
        )

    if DEFAULT_HERMES_INACTIVITY_TIMEOUT_SECONDS != 600:
        raise Stage12BulkRunnerError(
            "Hermes inactivity timeout changed"
        )

    if CANDIDATE_HERMES_ABSOLUTE_TIMEOUT_SECONDS != 3600:
        raise Stage12BulkRunnerError(
            "Hermes absolute timeout changed"
        )

    if STATEFUL_PART_MODEL_MAX_ATTEMPTS != 2:
        raise Stage12BulkRunnerError(
            "Hermes validation retry contract changed"
        )

    controller_parameters = inspect.signature(
        run_one_title_stage11
    ).parameters

    if "semantic_policy" not in controller_parameters:
        raise Stage12BulkRunnerError(
            "Stage11 semantic-policy wiring is missing"
        )

    invoke_source = inspect.getsource(
        _invoke_hermes_part
    )
    cleanup_source = inspect.getsource(
        _cleanup_timed_out_remote_hermes
    )

    for token in (
        "setsid",
        ".stage11-hermes-runtime.pid",
        ".stage11-hermes-runtime.meta",
    ):
        if token not in invoke_source:
            raise Stage12BulkRunnerError(
                "exact-process Hermes runtime contract changed"
            )

    for token in (
        "session_id=$SID",
        "CMDLINE_MISMATCH",
        "PGID_MISMATCH",
        "kill -TERM",
        "kill -KILL",
    ):
        if token not in cleanup_source:
            raise Stage12BulkRunnerError(
                "exact-process Hermes cleanup contract changed"
            )

    batch_source = inspect.getsource(
        Stage12BatchRunner._run_one
    )
    serial_source = inspect.getsource(
        Stage12BatchRunner.run
    )

    for token in (
        "self.nas_filesystem.lstat(destination)",
        "self.publisher.publish_korean_srt(",
        "self.jellyfin_recognizer(",
        "self.store.transition(",
    ):
        if token not in batch_source:
            raise Stage12BulkRunnerError(
                "Stage12 batch contract changed"
            )

    if (
        "self._run_one(dvd_id)" not in serial_source
        or "selection.dvd_ids" not in serial_source
    ):
        raise Stage12BulkRunnerError(
            "Stage12 serial isolation contract changed"
        )

    if "os.link(partial, target)" not in (
        REMOTE_SUBTITLE_PUBLISH_SCRIPT
    ):
        raise Stage12BulkRunnerError(
            "atomic publication contract changed"
        )

    jellyfin_source = inspect.getsource(
        recognize_jellyfin_external_subtitle
    )
    jellyfin_probe_source = inspect.getsource(
        _jellyfin_external_subtitle_probe
    )

    for token in (
        '"/Items/" + item_id + "/Refresh?"',
        '"MetadataRefreshMode": "FullRefresh"',
        "full_refresh_max_attempts",
        "expected_item_path",
        "expected_subtitle_path",
    ):
        if token not in jellyfin_source:
            raise Stage12BulkRunnerError(
                "Jellyfin recognition/fallback contract changed"
            )

    if '"/Items/" + item_id + "/PlaybackInfo"' not in (
        jellyfin_probe_source
    ):
        raise Stage12BulkRunnerError(
            "Jellyfin recognition/fallback contract changed"
        )

    external_source = inspect.getsource(
        build_external_ja_adapter
    )

    for token in (
        "AlignmentValidationError",
        "ExternalSubtitleValidationError",
        "external subtitle alignment validation failed",
    ):
        if token not in external_source:
            raise Stage12BulkRunnerError(
                "external-JA fallback contract changed"
            )

    emit("SEMANTIC_POLICY", POLICY_ID)
    emit("MODEL_INPUT", MODEL_INPUT)
    emit("HERMES_INACTIVITY_TIMEOUT", 600)
    emit("HERMES_ABSOLUTE_TIMEOUT", 3600)
    emit("MODEL_RETRIES", 2)
    emit("CONTRACT_CHECK", "PASS")


def open_discovery_read_only() -> sqlite3.Connection:
    require_regular(DISCOVERY_DB)

    connection = sqlite3.connect(
        DISCOVERY_DB.resolve().as_uri() + "?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")

    return connection


def eligible_pending_ids(store) -> tuple[str, ...]:
    result: list[str] = []

    for state in store.list_states():
        if state.status != "PENDING":
            continue

        if (
            state.eligibility != "ELIGIBLE_NEEDS_KO"
            or state.existing_ko != "ABSENT"
        ):
            continue

        if (
            not state.dvd_id
            or not state.media_path_identity
            or not state.holding_identity
            or state.holding_identity
            != "jav:" + state.media_path_identity
        ):
            raise Stage12BulkRunnerError(
                "PENDING title has invalid durable identity"
            )

        result.append(state.dvd_id)

    return tuple(result)


def active_rollout_ids(store) -> tuple[str, ...]:
    return tuple(
        state.dvd_id
        for state in store.list_states()
        if state.status in {"RUNNING", "GENERATED"}
    )


def read_discovery_rows(
    dvd_ids: tuple[str, ...],
    store,
) -> tuple[dict[str, object], ...]:
    connection = open_discovery_read_only()

    try:
        result: list[dict[str, object]] = []

        for dvd_id in dvd_ids:
            state = store.get(dvd_id)

            rows = tuple(
                connection.execute(
                    """
                    SELECT holding_id, storage_root,
                           relative_path, dvd_id,
                           parse_status, parse_method,
                           size_bytes, mtime_ns, present
                    FROM holdings
                    WHERE dvd_id = ?
                    ORDER BY holding_id
                    """,
                    (dvd_id,),
                ).fetchall()
            )

            canonical = tuple(
                row
                for row in rows
                if (
                    row["storage_root"] == "jav"
                    and row["present"] == 1
                )
            )

            if len(canonical) != 1:
                raise Stage12BulkRunnerError(
                    "canonical Discovery holding is not unique: "
                    + dvd_id
                )

            row = dict(canonical[0])

            if row["parse_status"] != "MATCHED":
                raise Stage12BulkRunnerError(
                    "Discovery holding is not MATCHED: "
                    + dvd_id
                )

            if (
                row["relative_path"]
                != state.media_path_identity
                or "jav:" + str(row["relative_path"])
                != state.holding_identity
                or int(row["size_bytes"])
                != state.source_size_bytes
                or int(row["mtime_ns"])
                != state.source_mtime_ns
            ):
                raise Stage12BulkRunnerError(
                    "Discovery source snapshot drift: "
                    + dvd_id
                )

            result.append(row)

        return tuple(result)
    finally:
        connection.close()


def acceptance_policy():
    from teddy_discovery_alignment_acceptance import (
        AlignmentAcceptancePolicy,
    )

    return AlignmentAcceptancePolicy(
        minimum_anchor_count=40,
        minimum_inlier_count=40,
        minimum_inlier_ratio=0.90,
        maximum_median_absolute_residual_ms=250.0,
        minimum_evidence_span_ms=1800000,
        minimum_scale=0.95,
        maximum_scale=1.05,
    )


def build_deployment_config():
    from teddy_discovery_stage11_deployment import (
        Stage11DeploymentConfig,
    )

    require_regular(
        Path(NAS["nas_key"]),
        mode=0o600,
    )
    require_regular(
        Path(NAS["nas_known_hosts"]),
        mode=0o644,
    )
    require_regular(
        Path(CT120_SSH_KEY),
        mode=0o600,
    )
    require_regular(
        Path(CT120_KNOWN_HOSTS),
        mode=0o600,
    )
    require_regular(
        JELLYFIN_API_KEY,
        mode=0o600,
    )

    for value in (
        VM122_ASR_BASE_URL,
        JELLYFIN_BASE_URL,
    ):
        parsed = urlsplit(value)

        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
        ):
            raise Stage12BulkRunnerError(
                "invalid production endpoint"
            )

    return Stage11DeploymentConfig(
        **NAS,
        asr_base_url=VM122_ASR_BASE_URL,
        request_timeout_seconds=
            VM122_REQUEST_TIMEOUT_SECONDS,
        remote_host=CT120_HOST,
        remote_user=CT120_USER,
        ssh_key=CT120_SSH_KEY,
        known_hosts=CT120_KNOWN_HOSTS,
        remote_task_root=REMOTE_TASK_ROOT,
        expected_profile_name="subtitle-translator",
        subtitlecat_timeout_seconds=20.0,
        subtitlecat_proxy_url=
            "http://127.0.0.1:58888",
    )


def build_dependencies(config):
    from teddy_discovery_stage11_deployment import (
        build_stage11_deployment_dependencies,
    )
    from teddy_discovery_stage11_live_adapters import (
        build_holding_resolver,
    )
    from teddy_discovery_stateful_live_runner import (
        run as native_live_run,
    )

    return build_stage11_deployment_dependencies(
        config,
        acceptance_policy=acceptance_policy(),
        residual_threshold_ms=1000,
        holding_resolver=build_holding_resolver(
            environ={
                "TEDDY_DISCOVERY_DB":
                    str(DISCOVERY_DB)
            }
        ),
        native_first_pass_run=native_live_run,
    )


def read_exact_nas_inventory(
    discovery_rows: tuple[dict[str, object], ...],
    subtitle_reader,
):
    from teddy_discovery_stage12_inventory import (
        ELIGIBLE_NEEDS_KO,
        EXISTING_KO_ABSENT,
        Stage12HoldingsInventory,
    )

    def selected_loader(_path):
        return {
            "holdings": list(discovery_rows),
        }

    report = Stage12HoldingsInventory(
        db_path=DISCOVERY_DB,
        subtitle_reader=subtitle_reader,
        holdings_loader=selected_loader,
    ).run()

    selected = {
        record.dvd_id: record
        for record in report.records
    }

    expected = {
        str(row["dvd_id"])
        for row in discovery_rows
    }

    if set(selected) != expected:
        raise Stage12BulkRunnerError(
            "exact NAS inventory membership mismatch"
        )

    for dvd_id, record in selected.items():
        if (
            record.eligibility
            != ELIGIBLE_NEEDS_KO
            or record.existing_ko
            != EXISTING_KO_ABSENT
        ):
            raise Stage12BulkRunnerError(
                "current NAS eligibility changed: "
                + dvd_id
            )

    return selected


def explicit_retry_inventory(
    *,
    dvd_id: str,
    expected_sequence: int,
    store,
    subtitle_reader,
    nas_filesystem,
):
    """Bind one retry to current Discovery, NAS, and durable rollout identity."""

    from teddy_discovery_stage12_rollout import (
        Stage12RolloutStateStore,
        _record_video,
    )

    if not isinstance(store, Stage12RolloutStateStore):
        raise Stage12BulkRunnerError("invalid explicit retry state store")
    state = store.get(dvd_id)
    rows = read_discovery_rows((dvd_id,), store)
    if len(rows) != 1:
        raise Stage12BulkRunnerError("explicit retry Discovery row is not unique")
    row = rows[0]
    validated = store.validate_explicit_retry(
        dvd_id,
        expected_sequence=expected_sequence,
        media_path_identity=str(row["relative_path"]),
        holding_identity="jav:" + str(row["relative_path"]),
        source_size_bytes=int(row["size_bytes"]),
        source_mtime_ns=int(row["mtime_ns"]),
    )
    if validated != state:
        raise Stage12BulkRunnerError(
            "explicit retry state changed during identity preflight"
        )
    records = read_exact_nas_inventory(rows, subtitle_reader)
    if set(records) != {dvd_id}:
        raise Stage12BulkRunnerError(
            "explicit retry NAS inventory membership mismatch"
        )
    record = records[dvd_id]
    video = _record_video(record)
    if (
        record.source_size_bytes != state.source_size_bytes
        or record.source_mtime_ns != state.source_mtime_ns
        or record.media_path_identity != state.media_path_identity
    ):
        raise Stage12BulkRunnerError(
            "explicit retry NAS inventory differs from rollout fingerprint"
        )
    source_stat = nas_filesystem.lstat(video.relative_path)
    if (
        not stat.S_ISREG(int(getattr(source_stat, "st_mode", 0)))
        or int(getattr(source_stat, "st_size", -1))
        != state.source_size_bytes
        or int(getattr(source_stat, "st_mtime_ns", -1))
        != state.source_mtime_ns
    ):
        raise Stage12BulkRunnerError(
            "explicit retry NAS source fingerprint drift"
        )
    destination = state.destination_relative
    if destination is None:
        from teddy_discovery_subtitle import derive_target_ko_relative

        destination = derive_target_ko_relative(video)
    try:
        nas_filesystem.lstat(destination)
    except FileNotFoundError:
        pass
    else:
        raise Stage12BulkRunnerError(
            "explicit retry destination already exists"
        )
    return records


def atomic_write_json(
    path: Path,
    payload: dict[str, object],
) -> None:
    parent = path.parent
    info = parent.lstat()

    if (
        parent.is_symlink()
        or not stat.S_ISDIR(info.st_mode)
    ):
        raise Stage12BulkRunnerError(
            "heartbeat parent directory is unsafe"
        )

    temporary = parent / (
        path.name
        + ".tmp."
        + str(os.getpid())
        + "."
        + uuid.uuid4().hex
    )

    fd = None

    try:
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
        )

        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW

        fd = os.open(
            temporary,
            flags,
            0o644,
        )

        raw = (
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")

        with os.fdopen(fd, "wb") as handle:
            fd = None
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(
            temporary,
            path,
        )

        directory_fd = os.open(
            parent,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0),
        )

        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if fd is not None:
            os.close(fd)

        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


class HeartbeatWriter:
    def __init__(
        self,
        path: Path,
        *,
        expected_head: str,
        batch_size: int,
        interval_seconds: float =
            HEARTBEAT_INTERVAL_SECONDS,
    ):
        self.path = Path(path)
        self.interval_seconds = float(
            interval_seconds
        )
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._started_at = utc_now()

        self._payload: dict[str, object] = {
            "schema_version": 1,
            "runner_state": "RUNNING",
            "current_dvd_id": None,
            "stage": "STARTING",
            "part_index": None,
            "part_count": None,
            "pid": os.getpid(),
            "started_at": self._started_at,
            "updated_at": self._started_at,
            "head_sha": expected_head,
            "batch_size": batch_size,
        }

    def _write(self) -> None:
        with self._lock:
            payload = dict(self._payload)
            payload["updated_at"] = utc_now()
            self._payload["updated_at"] = (
                payload["updated_at"]
            )

        atomic_write_json(
            self.path,
            payload,
        )

    def _loop(self) -> None:
        while not self._stop.wait(
            self.interval_seconds
        ):
            self._write()

    def start(self) -> None:
        self._write()

        self._thread = threading.Thread(
            target=self._loop,
            name="stage12-heartbeat",
            daemon=True,
        )
        self._thread.start()

    def update(self, **fields) -> None:
        with self._lock:
            self._payload.update(fields)

        self._write()

    def finish(
        self,
        runner_state: str,
        *,
        stage: str,
        current_dvd_id=None,
        error: str | None = None,
    ) -> None:
        self._stop.set()

        if self._thread is not None:
            self._thread.join(timeout=5)

        fields = {
            "runner_state": runner_state,
            "stage": stage,
            "current_dvd_id":
                current_dvd_id,
            "part_index": None,
            "part_count": None,
        }

        if error is not None:
            fields["error"] = error[:500]

        with self._lock:
            self._payload.update(fields)

        self._write()


class RunnerLock:
    def __init__(self, path: Path):
        self.path = path
        self.handle = None

    def __enter__(self):
        self.handle = open(
            self.path,
            "a+",
            encoding="utf-8",
        )

        try:
            fcntl.flock(
                self.handle.fileno(),
                fcntl.LOCK_EX
                | fcntl.LOCK_NB,
            )
        except BlockingIOError as error:
            self.handle.close()
            self.handle = None

            raise Stage12BulkRunnerError(
                "another Stage12 bulk runner holds the lock"
            ) from error

        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(str(os.getpid()) + "\n")
        self.handle.flush()
        os.fsync(self.handle.fileno())

        return self

    def __exit__(self, exc_type, exc, tb):
        if self.handle is not None:
            fcntl.flock(
                self.handle.fileno(),
                fcntl.LOCK_UN,
            )
            self.handle.close()
            self.handle = None


def configured_batch_size(
    pending_count: int,
    batch_size: int,
    *,
    processed: int,
    max_titles: int,
) -> int:
    if pending_count <= 0:
        return 0

    limit = min(
        pending_count,
        batch_size,
    )

    if max_titles > 0:
        remaining = max_titles - processed

        if remaining <= 0:
            return 0

        limit = min(
            limit,
            remaining,
        )

    return limit


def rollout_counts(store) -> dict[str, int]:
    counts: dict[str, int] = {}

    for state in store.list_states():
        counts[state.status] = (
            counts.get(state.status, 0)
            + 1
        )

    return counts


def run_preflight(
    *,
    expected_head: str,
    batch_size: int,
) -> int:
    from teddy_discovery_stage12_batch import (
        select_pending_batch,
    )
    from teddy_discovery_stage12_inventory import (
        build_subtitle_ssh_reader,
    )
    from teddy_discovery_stage12_rollout import (
        Stage12RolloutStateStore,
    )

    emit("STAGE12_BULK_PREFLIGHT", "START")
    emit("LIVE_EXECUTED", "NO")

    check_repo(expected_head)
    contract_check()
    inspect_runtime_directories()
    inspect_remote_root()
    network_probe()

    store = Stage12RolloutStateStore(
        ROLLOUT_DB
    )

    active = active_rollout_ids(store)

    emit("ACTIVE_ROLLOUT_IDS", active)

    if active:
        raise Stage12BulkRunnerError(
            "active RUNNING/GENERATED state exists; "
            "no implicit recovery"
        )

    pending = eligible_pending_ids(store)
    counts = rollout_counts(store)

    emit("ROLLOUT_COUNTS", counts)
    emit("ELIGIBLE_PENDING_COUNT", len(pending))

    if pending:
        size = min(
            batch_size,
            len(pending),
        )

        selection = select_pending_batch(
            store,
            batch_size=size,
        )

        emit(
            "FIRST_SELECTION",
            selection.dvd_ids,
        )

        discovery_rows = read_discovery_rows(
            selection.dvd_ids,
            store,
        )

        subtitle_reader = (
            build_subtitle_ssh_reader(**NAS)
        )

        selected_records = (
            read_exact_nas_inventory(
                discovery_rows,
                subtitle_reader,
            )
        )

        if set(selected_records) != set(
            selection.dvd_ids
        ):
            raise Stage12BulkRunnerError(
                "first exact NAS selection mismatch"
            )

        emit(
            "FIRST_SELECTION_NAS_PREFLIGHT",
            "PASS",
        )

    emit("PRODUCTION_WRITES_TOTAL", 0)
    emit("STAGE12_BULK_PREFLIGHT", "PASS")
    emit("READY_FOR_BULK_LIVE", "YES")

    return 0


def run_explicit_retry_preflight(
    *,
    expected_head: str,
    dvd_id: str,
    expected_sequence: int,
) -> int:
    """Read-only preflight for one explicitly authorized retry title."""

    from teddy_discovery_stage12_inventory import build_subtitle_ssh_reader
    from teddy_discovery_stage12_rollout import Stage12RolloutStateStore
    from teddy_discovery_stage12_rollout import build_nas_preflight_filesystem

    emit("STAGE12_EXPLICIT_RETRY_PREFLIGHT", "START")
    emit("LIVE_EXECUTED", "NO")
    check_repo(expected_head)
    contract_check()
    inspect_runtime_directories()
    inspect_remote_root()
    network_probe()

    store = Stage12RolloutStateStore(ROLLOUT_DB)
    active = active_rollout_ids(store)
    emit("ACTIVE_ROLLOUT_IDS", active)
    if active:
        raise Stage12BulkRunnerError(
            "active RUNNING/GENERATED state exists; explicit retry is blocked"
        )
    state = store.get(dvd_id)
    emit("RETRY_TARGET", {"dvd_id": dvd_id, "status": state.status,
                           "sequence": state.transition_sequence})
    records = explicit_retry_inventory(
        dvd_id=dvd_id,
        expected_sequence=expected_sequence,
        store=store,
        subtitle_reader=build_subtitle_ssh_reader(**NAS),
        nas_filesystem=build_nas_preflight_filesystem(**NAS),
    )
    if set(records) != {dvd_id}:
        raise Stage12BulkRunnerError(
            "explicit retry preflight did not resolve exactly one title"
        )
    emit("EXPLICIT_RETRY_IDENTITY", "PASS")
    emit("PRODUCTION_WRITES_TOTAL", 0)
    emit("STAGE12_EXPLICIT_RETRY_PREFLIGHT", "PASS")
    return 0


def run_live(
    *,
    expected_head: str,
    batch_size: int,
    max_titles: int,
    retry_dvd_id: str | None = None,
    retry_expected_sequence: int | None = None,
) -> int:
    from teddy_discovery_completion_ssh import (
        CompletionSSH,
    )
    from teddy_discovery_jellyfin import (
        JellyfinClient,
    )
    from teddy_discovery_stage11_controller import (
        run_one_title_stage11,
    )
    from teddy_discovery_stage12_batch import (
        Stage12BatchRunner,
        Stage12BatchSelection,
        Stage12ExplicitRetryAuthorization,
        recognize_jellyfin_external_subtitle,
        select_pending_batch,
    )
    from teddy_discovery_stage12_inventory import (
        build_subtitle_ssh_reader,
    )
    from teddy_discovery_stage12_rollout import (
        Stage12RolloutStateStore,
        build_nas_preflight_filesystem,
    )
    from teddy_discovery_subtitle_publish import (
        SubtitleSSHMutator,
    )

    explicit_retry = retry_dvd_id is not None
    if explicit_retry:
        if (
            type(retry_dvd_id) is not str
            or not retry_dvd_id
            or type(retry_expected_sequence) is not int
            or retry_expected_sequence < 1
            or batch_size != 1
            or max_titles not in (0, 1)
        ):
            raise Stage12BulkRunnerError(
                "explicit retry requires one DVD-ID, one expected sequence, and a one-title bound"
            )
        if os.environ.get(EXPLICIT_RETRY_AUTH_ENV) != EXPLICIT_RETRY_AUTH_VALUE:
            emit("EXPLICIT_RETRY_AUTHORIZATION", "BLOCKED")
            emit("LIVE_EXECUTED", "NO")
            return 2
        run_explicit_retry_preflight(
            expected_head=expected_head,
            dvd_id=retry_dvd_id,
            expected_sequence=retry_expected_sequence,
        )
    else:
        if retry_expected_sequence is not None:
            raise Stage12BulkRunnerError(
                "expected sequence is valid only for explicit retry"
            )
        if os.environ.get(AUTH_ENV) != AUTH_VALUE:
            emit("LIVE_AUTHORIZATION", "BLOCKED")
            emit("LIVE_EXECUTED", "NO")
            return 2
        run_preflight(
            expected_head=expected_head,
            batch_size=batch_size,
        )

    with RunnerLock(LOCK_PATH):
        # Revalidate repo and durable active state after
        # acquiring the singleton runner lock.
        check_repo(expected_head)

        store = Stage12RolloutStateStore(
            ROLLOUT_DB
        )

        active = active_rollout_ids(store)

        if active:
            raise Stage12BulkRunnerError(
                "active rollout state appeared before live start"
            )

        retry_records = None
        if explicit_retry:
            subtitle_reader_for_retry = build_subtitle_ssh_reader(**NAS)
            nas_filesystem_for_retry = build_nas_preflight_filesystem(**NAS)
            retry_records = explicit_retry_inventory(
                dvd_id=retry_dvd_id,
                expected_sequence=retry_expected_sequence,
                store=store,
                subtitle_reader=subtitle_reader_for_retry,
                nas_filesystem=nas_filesystem_for_retry,
            )

        ensure_runtime_directories()
        ensure_remote_root()

        heartbeat = HeartbeatWriter(
            HEARTBEAT_PATH,
            expected_head=expected_head,
            batch_size=batch_size,
        )

        heartbeat.start()

        try:
            heartbeat.update(
                stage="BUILD_DEPENDENCIES",
                current_dvd_id=None,
            )

            config = build_deployment_config()
            dependencies = build_dependencies(config)
            controller_kwargs = (
                dependencies.controller_kwargs()
            )

            subtitle_reader = (
                build_subtitle_ssh_reader(**NAS)
            )

            nas_filesystem = (
                build_nas_preflight_filesystem(
                    **NAS
                )
            )

            publisher = SubtitleSSHMutator(
                CompletionSSH(
                    host=NAS["nas_host"],
                    user=NAS["nas_user"],
                    key=NAS["nas_key"],
                    known_hosts=
                        NAS["nas_known_hosts"],
                    downloads_root="",
                    library_root=
                        NAS["nas_library_root"],
                )
            )

            jellyfin_client = JellyfinClient(
                base_url=JELLYFIN_BASE_URL,
                api_key_path=JELLYFIN_API_KEY,
                timeout=10,
            )

            processed = 0
            batch_number = 0

            while True:
                if explicit_retry:
                    if processed:
                        break
                    size = 1
                else:
                    pending = eligible_pending_ids(store)
                    size = configured_batch_size(
                        len(pending),
                        batch_size,
                        processed=processed,
                        max_titles=max_titles,
                    )

                if size == 0:
                    break

                batch_number += 1

                selection = (
                    Stage12BatchSelection(1, (retry_dvd_id,))
                    if explicit_retry
                    else select_pending_batch(store, batch_size=size)
                )

                heartbeat.update(
                    stage="BATCH_PREFLIGHT",
                    current_dvd_id=
                        selection.dvd_ids[0],
                    batch_number=batch_number,
                    processed_titles=processed,
                )

                if explicit_retry:
                    selected_records = retry_records
                else:
                    discovery_rows = read_discovery_rows(
                        selection.dvd_ids,
                        store,
                    )
                    selected_records = read_exact_nas_inventory(
                        discovery_rows,
                        subtitle_reader,
                    )

                if explicit_retry:
                    selected_records = explicit_retry_inventory(
                        dvd_id=retry_dvd_id,
                        expected_sequence=retry_expected_sequence,
                        store=store,
                        subtitle_reader=subtitle_reader,
                        nas_filesystem=nas_filesystem,
                    )

                emit(
                    "BATCH_SELECTION",
                    {
                        "batch_number":
                            batch_number,
                        "dvd_ids":
                            selection.dvd_ids,
                    },
                )

                heartbeat_ref = heartbeat

                class HeartbeatStage12BatchRunner(
                    Stage12BatchRunner
                ):
                    def _run_one(
                        self,
                        dvd_id: str,
                    ):
                        heartbeat_ref.update(
                            runner_state="RUNNING",
                            current_dvd_id=dvd_id,
                            stage="STAGE12",
                            batch_number=
                                batch_number,
                            processed_titles=
                                processed,
                        )

                        return super()._run_one(
                            dvd_id
                        )

                def controller_runner(
                    dvd_id: str,
                ):
                    heartbeat.update(
                        current_dvd_id=dvd_id,
                        stage="STAGE11",
                    )

                    try:
                        result = (
                            run_one_title_stage11(
                                dvd_id,
                                artifact_root=
                                    ARTIFACT_ROOT,
                                stateful_staging_root=
                                    STAGING_ROOT,
                                claim_token=
                                    CLAIM_TOKEN,
                                semantic_policy=
                                    POLICY_ID,
                                **controller_kwargs,
                            )
                        )
                    except Exception:
                        heartbeat.update(
                            current_dvd_id=
                                dvd_id,
                            stage=
                                "STAGE11_ERROR",
                        )
                        raise

                    heartbeat.update(
                        current_dvd_id=dvd_id,
                        stage="PUBLICATION",
                    )

                    return result

                def jellyfin_recognizer(
                    dvd_id,
                    video,
                    destination,
                ):
                    heartbeat.update(
                        current_dvd_id=dvd_id,
                        stage="JELLYFIN",
                    )

                    return (
                        recognize_jellyfin_external_subtitle(
                            jellyfin_client,
                            video_relative=
                                video.relative_path,
                            subtitle_relative=
                                destination,
                            poll_interval_seconds=
                                5.0,
                            max_attempts=30,
                            full_refresh_max_attempts=(
                                JELLYFIN_FULL_REFRESH_MAX_ATTEMPTS
                            ),
                        )
                    )

                runner = (
                    HeartbeatStage12BatchRunner(
                        store=store,
                        inventory=
                            selected_records,
                        artifact_root=
                            ARTIFACT_ROOT,
                        nas_filesystem=
                            nas_filesystem,
                        subtitle_reader=
                            subtitle_reader,
                        publisher=publisher,
                        controller_runner=
                            controller_runner,
                        jellyfin_recognizer=
                            jellyfin_recognizer,
                        retry_authorization=(
                            Stage12ExplicitRetryAuthorization(
                                retry_dvd_id,
                                retry_expected_sequence,
                            )
                            if explicit_retry
                            else None
                        ),
                    )
                )

                result = runner.run(
                    selection
                )

                processed += len(
                    result.titles
                )

                emit(
                    "BATCH_RESULT",
                    {
                        "batch_number":
                            batch_number,
                        "summary":
                            result.summary(),
                        "processed_titles":
                            processed,
                    },
                )

                if explicit_retry:
                    break

                heartbeat.update(
                    current_dvd_id=None,
                    stage="BETWEEN_BATCHES",
                    batch_number=batch_number,
                    processed_titles=processed,
                )

            final_counts = rollout_counts(
                store
            )

            heartbeat.finish(
                "COMPLETE",
                stage="COMPLETE",
                current_dvd_id=None,
            )

            emit(
                "FINAL_COUNTS",
                final_counts,
            )
            emit(
                "PROCESSED_THIS_RUN",
                processed,
            )
            emit(
                "STAGE12_BULK_LIVE",
                "COMPLETE",
            )

            return 0

        except BaseException as error:
            try:
                heartbeat.finish(
                    "ERROR",
                    stage="ERROR",
                    current_dvd_id=None,
                    error=(
                        type(error).__name__
                        + ": "
                        + str(error)
                    ),
                )
            except Exception as heartbeat_error:
                emit(
                    "HEARTBEAT_FINALIZATION_ERROR",
                    type(heartbeat_error).__name__,
                )

            raise


def run_reconciliation(
    *,
    expected_head: str,
    dvd_id: str,
) -> int:
    """Explicit one-title path; no Stage11, publisher, or refresh calls."""

    from teddy_discovery_jellyfin import JellyfinClient
    from teddy_discovery_stage12_inventory import (
        build_subtitle_ssh_reader,
    )
    from teddy_discovery_stage12_reconcile import (
        reconcile_failed_publication,
    )
    from teddy_discovery_stage12_rollout import (
        Stage12RolloutStateStore,
        build_nas_preflight_filesystem,
    )

    if os.environ.get(RECONCILE_AUTH_ENV) != RECONCILE_AUTH_VALUE:
        emit("RECONCILIATION_AUTHORIZATION", "BLOCKED")
        emit("RECONCILIATION_EXECUTED", "NO")
        return 2

    check_repo(expected_head)
    if type(dvd_id) is not str or not dvd_id:
        raise Stage12BulkRunnerError(
            "one exact --dvd-id is required for reconciliation"
        )
    store = Stage12RolloutStateStore(ROLLOUT_DB)
    state = store.get(dvd_id)
    if state.status != "FAILED_RETRYABLE":
        raise Stage12BulkRunnerError(
            "only FAILED_RETRYABLE titles can be reconciled"
        )
    discovery_row = read_discovery_rows((dvd_id,), store)[0]

    for key in (NAS["nas_key"], NAS["nas_known_hosts"], JELLYFIN_API_KEY):
        require_regular(Path(key))
    nas_filesystem = build_nas_preflight_filesystem(**NAS)
    subtitle_reader = build_subtitle_ssh_reader(**NAS)
    jellyfin_client = JellyfinClient(
        base_url=JELLYFIN_BASE_URL,
        api_key_path=JELLYFIN_API_KEY,
        timeout=10,
    )

    reconciled = reconcile_failed_publication(
        dvd_id=dvd_id,
        store=store,
        discovery_row=discovery_row,
        artifact_root=ARTIFACT_ROOT,
        nas_filesystem=nas_filesystem,
        subtitle_reader=subtitle_reader,
        jellyfin_client=jellyfin_client,
    )
    emit("RECONCILIATION_RESULT", reconciled.status)
    emit("RECONCILIATION_DVD_ID", dvd_id)
    emit("RECONCILIATION_REASON", reconciled.last_transition_reason)
    return 0


def build_parser():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--mode",
        choices=("preflight", "live", "retry", "reconcile"),
        default="preflight",
    )

    parser.add_argument(
        "--expected-head",
        required=True,
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
    )

    parser.add_argument(
        "--max-titles",
        type=int,
        default=0,
        help=(
            "0 means process all ordinary PENDING titles"
        ),
    )

    parser.add_argument(
        "--dvd-id",
        action="append",
        help=(
            "one exact title for explicit retry or publication reconciliation; "
            "may be supplied exactly once"
        ),
    )
    parser.add_argument(
        "--expected-sequence",
        type=int,
        help="durable rollout event sequence required for explicit retry",
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    if (
        args.batch_size < 1
        or args.batch_size > 8
    ):
        emit(
            "STAGE12_BULK",
            "FAIL_INVALID_BATCH_SIZE",
        )
        return 2

    if args.max_titles < 0:
        emit(
            "STAGE12_BULK",
            "FAIL_INVALID_MAX_TITLES",
        )
        return 2

    dvd_ids = args.dvd_id or []
    if args.mode == "reconcile":
        if len(dvd_ids) != 1:
            emit("STAGE12_RECONCILIATION", "FAIL_DVD_ID_REQUIRED")
            return 2
        if args.expected_sequence is not None:
            emit("STAGE12_RECONCILIATION", "FAIL_UNEXPECTED_SEQUENCE")
            return 2
        try:
            return run_reconciliation(
                expected_head=args.expected_head,
                dvd_id=dvd_ids[0],
            )
        except KeyboardInterrupt:
            emit("STAGE12_RECONCILIATION", "INTERRUPTED")
            return 130
        except Exception as error:
            emit(
                "STAGE12_RECONCILIATION",
                "FAIL_" + type(error).__name__,
            )
            emit("ERROR", str(error))
            return 1

    if args.mode == "retry":
        if len(dvd_ids) != 1:
            emit("STAGE12_EXPLICIT_RETRY", "FAIL_EXACTLY_ONE_DVD_ID_REQUIRED")
            return 2
        if type(args.expected_sequence) is not int or args.expected_sequence < 1:
            emit("STAGE12_EXPLICIT_RETRY", "FAIL_EXPECTED_SEQUENCE_REQUIRED")
            return 2
        if args.batch_size != 1 or args.max_titles not in (0, 1):
            emit("STAGE12_EXPLICIT_RETRY", "FAIL_SINGLE_TITLE_BOUND_REQUIRED")
            return 2
        try:
            return run_live(
                expected_head=args.expected_head,
                batch_size=1,
                max_titles=1,
                retry_dvd_id=dvd_ids[0],
                retry_expected_sequence=args.expected_sequence,
            )
        except KeyboardInterrupt:
            emit("STAGE12_EXPLICIT_RETRY", "INTERRUPTED")
            return 130
        except Exception as error:
            emit("STAGE12_EXPLICIT_RETRY", "FAIL_" + type(error).__name__)
            emit("ERROR", str(error))
            return 1

    if dvd_ids or args.expected_sequence is not None:
        emit("STAGE12_BULK", "FAIL_SELECTOR_ONLY_VALID_FOR_RETRY_OR_RECONCILE")
        return 2

    try:
        if args.mode == "live":
            return run_live(
                expected_head=
                    args.expected_head,
                batch_size=
                    args.batch_size,
                max_titles=
                    args.max_titles,
            )

        return run_preflight(
            expected_head=args.expected_head,
            batch_size=args.batch_size,
        )

    except KeyboardInterrupt:
        emit(
            "STAGE12_BULK",
            "INTERRUPTED",
        )
        return 130

    except Exception as error:
        emit(
            "STAGE12_BULK",
            "FAIL_"
            + type(error).__name__,
        )
        emit(
            "ERROR",
            str(error),
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
