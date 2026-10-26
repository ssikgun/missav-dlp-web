"""Dedicated Stage9 media-only entry point.

This module deliberately has no product imports at import time. It never calls
the general completion runner, download planner, Organizer, or metadata
recovery path. All writes are gated by an explicit apply flag and confirmation.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlsplit
import argparse
import fcntl
import json
import os
import re
import shutil
import sqlite3
import stat
import sys
import urllib.request


CONFIRMATION = "APPLY_STAGE9_MEDIA_ONLY"
MAX_ITEMS_LIMIT = 100
MAX_VISIBILITY_LIMIT = 100
MAX_JELLYFIN_GET_REQUESTS = 1000
REQUIRED_RUNTIME_MODULES = (
    "teddy_discovery_completion_ssh.py",
    "teddy_discovery_ids.py",
    "teddy_discovery_jellyfin.py",
    "teddy_discovery_jellyfin_visibility.py",
    "teddy_discovery_media_jobs.py",
    "teddy_discovery_media_metadata.py",
    "teddy_discovery_media_pipeline.py",
    "teddy_discovery_media_publish.py",
    "teddy_title_exclusion.py",
)
REQUIRED_MEDIA_JOB_COLUMNS = {
    "media_job_id",
    "dvd_id",
    "status",
    "attempt_count",
    "error",
    "nfo_status",
    "poster_status",
    "poster_error",
    "jellyfin_notification_status",
    "jellyfin_error",
    "jellyfin_recovery_status",
    "jellyfin_next_check_at",
    "created_at",
    "updated_at",
}
REQUIRED_VISIBILITY_COLUMNS = {
    "dvd_id",
    "media_job_id",
    "jellyfin_path",
    "status",
    "check_count",
    "media_completed_at",
    "created_at",
    "updated_at",
    "last_checked_at",
    "visible_at",
    "last_error",
}
REQUIRED_DISCOVERY_COLUMNS = {
    "organizer_jobs": {"job_id", "dvd_id", "status"},
    "holdings": {
        "dvd_id", "storage_root", "relative_path", "size_bytes",
        "mtime_ns", "present", "discovered_by",
    },
    "titles": {
        "dvd_id", "title", "release_date", "maker", "cover_url",
        "raw_metadata", "metadata_source",
    },
    "title_genres": {"dvd_id", "genre_id"},
    "genres": {"genre_id", "name"},
    "title_people": {"dvd_id", "person_id", "role"},
    "people": {"person_id", "name"},
}


class RunnerError(RuntimeError):
    """A sanitized, safe-to-report runner validation error."""

    def __init__(self, code: str):
        self.code = str(code)
        super().__init__(self.code)


@dataclass(frozen=True)
class RunnerConfig:
    discovery_db_path: str | Path
    media_db_path: str | Path
    media_writer_lock_path: str | Path
    run_lock_path: str | Path
    title_lock_dir: str | Path
    max_items: int = 1
    visibility_max_items: int = 1
    visibility_seed_max_items: int = 1
    jellyfin_get_max_requests: int | None = None
    target_dvd_id: str | None = None
    apply: bool = False
    confirm: str = ""
    ssh_host: str = ""
    ssh_user: str = ""
    ssh_key_path: str | Path | None = None
    ssh_known_hosts_path: str | Path | None = None
    library_root: str = ""
    poster_proxy_url: str = ""
    jellyfin_base_url: str = ""
    jellyfin_key_path: str | Path | None = None
    expected_release_id: str | None = None


def _normal_path(raw: str | Path, *, allow_missing: bool, expected: str) -> Path:
    try:
        path = Path(raw)
        text = os.fspath(raw)
    except (TypeError, ValueError, OSError) as exc:
        raise RunnerError("INVALID_PATH") from exc
    if not text or not path.is_absolute() or str(path) != os.path.normpath(str(path)):
        raise RunnerError("INVALID_PATH")

    current = Path(path.anchor)
    if current.is_symlink():
        raise RunnerError("SYMLINK_PATH_COMPONENT")
    parts = path.parts[1:]
    for index, part in enumerate(parts):
        current = current / part
        final = index == len(parts) - 1
        try:
            info = current.lstat()
        except FileNotFoundError as exc:
            if allow_missing and final:
                parent = current.parent
                try:
                    parent_info = parent.lstat()
                except OSError as parent_exc:
                    raise RunnerError("PATH_PARENT_UNAVAILABLE") from parent_exc
                if stat.S_ISLNK(parent_info.st_mode) or not stat.S_ISDIR(parent_info.st_mode):
                    raise RunnerError("INVALID_PATH_PARENT")
                break
            raise RunnerError("PATH_NOT_FOUND") from exc
        except OSError as exc:
            raise RunnerError("PATH_UNAVAILABLE") from exc
        if stat.S_ISLNK(info.st_mode):
            raise RunnerError("SYMLINK_PATH_COMPONENT")
        if not final:
            if not stat.S_ISDIR(info.st_mode):
                raise RunnerError("INVALID_PATH_PARENT")
        elif expected == "file" and not stat.S_ISREG(info.st_mode):
            raise RunnerError("INVALID_FILE_TYPE")
        elif expected == "directory" and not stat.S_ISDIR(info.st_mode):
            raise RunnerError("INVALID_DIRECTORY_TYPE")
        elif expected == "lock" and not stat.S_ISREG(info.st_mode):
            raise RunnerError("INVALID_LOCK_FILE")
        if final and expected == "lock" and info.st_nlink != 1:
            raise RunnerError("INVALID_LOCK_LINK_COUNT")
    return path


def _validate_directory(path: str | Path, *, reject_world_write: bool = False) -> Path:
    value = _normal_path(path, allow_missing=False, expected="directory")
    info = value.lstat()
    if reject_world_write and info.st_mode & stat.S_IWOTH:
        raise RunnerError("WORLD_WRITABLE_LOCK_DIRECTORY")
    return value


def _sqlite_uri(path: Path) -> str:
    return "file:" + quote(path.as_posix(), safe="/:") + "?mode=ro"


def _table_columns(db: sqlite3.Connection, name: str) -> set[str]:
    return {str(row[1]) for row in db.execute("PRAGMA table_info(\"" + name + "\")")}


def _require_index(
    db: sqlite3.Connection,
    table: str,
    index_name: str,
    expected_columns: tuple[str, ...],
    *,
    unique: bool | None = None,
) -> None:
    rows = db.execute("PRAGMA index_list(\"" + table + "\")").fetchall()
    match = next((row for row in rows if str(row[1]) == index_name), None)
    if match is None:
        raise RunnerError("REQUIRED_INDEX_MISSING")
    if unique is not None and bool(match[2]) is not unique:
        raise RunnerError("REQUIRED_INDEX_CONTRACT_MISMATCH")
    escaped = index_name.replace('"', '""')
    columns = tuple(
        str(row[2])
        for row in db.execute("PRAGMA index_info(\"" + escaped + "\")")
    )
    if columns != expected_columns:
        raise RunnerError("REQUIRED_INDEX_CONTRACT_MISMATCH")


def _require_column_contract(
    db: sqlite3.Connection,
    table: str,
    contracts: dict[str, tuple[str, int, int]],
) -> None:
    info = {
        str(row[1]): (str(row[2]).upper(), int(row[3]), int(row[5]))
        for row in db.execute("PRAGMA table_info(\"" + table + "\")")
    }
    for name, expected in contracts.items():
        if info.get(name) != expected:
            raise RunnerError("REQUIRED_COLUMN_CONTRACT_MISMATCH")


def _table_sql(db: sqlite3.Connection, table: str) -> str:
    row = db.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return str(row[0] or "").upper() if row else ""


def _validate_database(path: Path, required_tables: dict[str, set[str]]) -> None:
    try:
        db = sqlite3.connect(_sqlite_uri(path), uri=True, timeout=2)
        db.execute("PRAGMA query_only=ON")
        if db.execute("PRAGMA query_only").fetchone()[0] != 1:
            raise RunnerError("READ_ONLY_GUARD_UNAVAILABLE")
        check = [str(row[0]).lower() for row in db.execute("PRAGMA quick_check")]
        if check != ["ok"]:
            raise RunnerError("DATABASE_INTEGRITY_CHECK_FAILED")
        tables = {
            str(row[0])
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        for table, required_columns in required_tables.items():
            if table not in tables:
                raise RunnerError("REQUIRED_TABLE_MISSING")
            if not required_columns.issubset(_table_columns(db, table)):
                raise RunnerError("REQUIRED_COLUMNS_MISSING")
        if "media_jobs" in required_tables:
            _require_column_contract(
                db,
                "media_jobs",
                {
                    "media_job_id": ("INTEGER", 0, 1),
                    "dvd_id": ("TEXT", 1, 0),
                    "status": ("TEXT", 1, 0),
                    "attempt_count": ("INTEGER", 1, 0),
                    "error": ("TEXT", 0, 0),
                    "nfo_status": ("TEXT", 1, 0),
                    "poster_status": ("TEXT", 1, 0),
                    "poster_error": ("TEXT", 0, 0),
                    "jellyfin_notification_status": ("TEXT", 1, 0),
                    "jellyfin_error": ("TEXT", 0, 0),
                    "jellyfin_recovery_status": ("TEXT", 1, 0),
                    "jellyfin_next_check_at": ("TEXT", 0, 0),
                    "created_at": ("TEXT", 1, 0),
                    "updated_at": ("TEXT", 1, 0),
                },
            )
            if _table_sql(db, "media_jobs").count("CHECK") < 6:
                raise RunnerError("MEDIA_JOB_CHECK_CONSTRAINTS_MISSING")
            _require_index(
                db,
                "media_jobs",
                "idx_media_jobs_status",
                ("status", "media_job_id"),
            )
            _require_index(
                db,
                "media_jobs",
                "idx_media_jobs_poster_retry",
                ("status", "nfo_status", "poster_status", "updated_at"),
            )
            unique_dvd_index = False
            for row in db.execute("PRAGMA index_list(\"media_jobs\")"):
                if int(row[2]) != 1:
                    continue
                name = str(row[1]).replace('"', '""')
                indexed = [str(item[2]) for item in db.execute(
                    "PRAGMA index_info(\"" + name + "\")"
                )]
                if indexed == ["dvd_id"]:
                    unique_dvd_index = True
                    break
            if not unique_dvd_index:
                raise RunnerError("MEDIA_DVD_UNIQUE_INDEX_MISSING")
        if "media_jellyfin_visibility" in required_tables:
            _require_column_contract(
                db,
                "media_jellyfin_visibility",
                {
                    "dvd_id": ("TEXT", 1, 0),
                    "media_job_id": ("INTEGER", 1, 0),
                    "jellyfin_path": ("TEXT", 0, 0),
                    "status": ("TEXT", 1, 0),
                    "check_count": ("INTEGER", 1, 0),
                    "media_completed_at": ("TEXT", 1, 0),
                    "created_at": ("TEXT", 1, 0),
                    "updated_at": ("TEXT", 1, 0),
                    "last_checked_at": ("TEXT", 0, 0),
                    "visible_at": ("TEXT", 0, 0),
                    "last_error": ("TEXT", 0, 0),
                },
            )
            if _table_sql(db, "media_jellyfin_visibility").count("CHECK") < 2:
                raise RunnerError("VISIBILITY_CHECK_CONSTRAINTS_MISSING")
            _require_index(
                db,
                "media_jellyfin_visibility",
                "idx_media_jellyfin_visibility_pending",
                ("status", "updated_at", "dvd_id"),
            )
    except RunnerError:
        raise
    except (sqlite3.Error, OSError, ValueError) as exc:
        raise RunnerError("DATABASE_PREFLIGHT_FAILED") from exc
    finally:
        try:
            db.close()
        except (UnboundLocalError, AttributeError):
            pass


def _validate_runtime(expected_release_id: str | None) -> Path:
    if sys.version_info < (3, 10):
        raise RunnerError("PYTHON_VERSION_UNSUPPORTED")
    runtime = Path(__file__).absolute().parent
    try:
        _validate_directory(runtime)
        _normal_path(Path(__file__).absolute(), allow_missing=False, expected="file")
    except RunnerError:
        raise
    for filename in REQUIRED_RUNTIME_MODULES:
        _normal_path(runtime / filename, allow_missing=False, expected="file")
    if expected_release_id is not None:
        release_id = str(expected_release_id).strip().lower()
        if not re.fullmatch(r"[0-9a-f]{40}", release_id):
            raise RunnerError("INVALID_EXPECTED_RELEASE_ID")
        if runtime.name.lower() != release_id:
            raise RunnerError("RELEASE_ID_MISMATCH")
    return runtime


def _validate_remote_config(config: RunnerConfig) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,254}", config.ssh_host):
        raise RunnerError("INVALID_SSH_HOST")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]{0,63}", config.ssh_user):
        raise RunnerError("INVALID_SSH_USER")
    if shutil.which("ssh") is None:
        raise RunnerError("SSH_CLIENT_UNAVAILABLE")
    for path in (
        config.ssh_key_path,
        config.ssh_known_hosts_path,
        config.jellyfin_key_path,
    ):
        if path is None:
            raise RunnerError("REQUIRED_CREDENTIAL_PATH_MISSING")
        _normal_path(path, allow_missing=False, expected="file")
    remote = PurePosixPath(config.library_root)
    if (
        not config.library_root
        or not remote.is_absolute()
        or ".." in remote.parts
        or remote.as_posix() != config.library_root
    ):
        raise RunnerError("INVALID_LIBRARY_ROOT")
    try:
        base = urlsplit(config.jellyfin_base_url)
        _ = base.port
    except ValueError as exc:
        raise RunnerError("INVALID_JELLYFIN_URL") from exc
    if (
        base.scheme not in {"http", "https"}
        or not base.hostname
        or base.username is not None
        or base.password is not None
        or base.query
        or base.fragment
    ):
        raise RunnerError("INVALID_JELLYFIN_URL")
    if not config.poster_proxy_url:
        raise RunnerError("POSTER_PROXY_REQUIRED")
    try:
        from teddy_discovery_media_metadata import make_poster_fetcher

        make_poster_fetcher(config.poster_proxy_url)
    except (ImportError, TypeError, ValueError) as exc:
        raise RunnerError("INVALID_POSTER_PROXY") from exc


def _validate_config(
    config: RunnerConfig,
    *,
    require_release_id: bool = False,
) -> dict:
    try:
        max_items = int(config.max_items)
        visibility_max = int(config.visibility_max_items)
        visibility_seed_max = int(config.visibility_seed_max_items)
    except (TypeError, ValueError) as exc:
        raise RunnerError("INVALID_ITEM_LIMIT") from exc
    if not 1 <= max_items <= MAX_ITEMS_LIMIT:
        raise RunnerError("MEDIA_ITEM_LIMIT_OUT_OF_RANGE")
    if not 0 <= visibility_max <= MAX_VISIBILITY_LIMIT:
        raise RunnerError("VISIBILITY_ITEM_LIMIT_OUT_OF_RANGE")
    if not 0 <= visibility_seed_max <= MAX_VISIBILITY_LIMIT:
        raise RunnerError("VISIBILITY_SEED_LIMIT_OUT_OF_RANGE")

    required_gets = (5 * max_items) + (4 * visibility_max)
    try:
        get_budget = (
            required_gets
            if config.jellyfin_get_max_requests is None
            else int(config.jellyfin_get_max_requests)
        )
    except (TypeError, ValueError) as exc:
        raise RunnerError("INVALID_JELLYFIN_GET_LIMIT") from exc
    if not required_gets <= get_budget <= MAX_JELLYFIN_GET_REQUESTS:
        raise RunnerError("JELLYFIN_GET_LIMIT_OUT_OF_RANGE")

    discovery_path = _normal_path(
        config.discovery_db_path, allow_missing=False, expected="file"
    )
    media_path = _normal_path(
        config.media_db_path, allow_missing=False, expected="file"
    )
    if os.path.samefile(discovery_path, media_path):
        raise RunnerError("DATABASE_PATHS_MUST_DIFFER")
    for database_path in (discovery_path, media_path):
        for suffix in ("-wal", "-shm"):
            _normal_path(
                Path(str(database_path) + suffix),
                allow_missing=True,
                expected="file",
            )
    writer_lock = _normal_path(
        config.media_writer_lock_path, allow_missing=True, expected="lock"
    )
    run_lock = _normal_path(
        config.run_lock_path, allow_missing=True, expected="lock"
    )
    if writer_lock == run_lock:
        raise RunnerError("LOCK_PATHS_MUST_DIFFER")
    title_lock_dir = _validate_directory(
        config.title_lock_dir, reject_world_write=True
    )
    _validate_runtime(config.expected_release_id)

    _validate_database(
        media_path,
        {
            "media_jobs": REQUIRED_MEDIA_JOB_COLUMNS,
            "media_jellyfin_visibility": REQUIRED_VISIBILITY_COLUMNS,
        },
    )
    _validate_database(discovery_path, REQUIRED_DISCOVERY_COLUMNS)

    target = None
    if config.target_dvd_id is not None:
        try:
            from teddy_discovery_media_jobs import normalize_media_target_dvd_id

            target = normalize_media_target_dvd_id(config.target_dvd_id)
        except (ImportError, ValueError, TypeError) as exc:
            raise RunnerError("INVALID_TARGET_DVD_ID") from exc

    if config.apply:
        if config.confirm != CONFIRMATION:
            raise RunnerError("APPLY_CONFIRMATION_REQUIRED")
        if require_release_id and config.expected_release_id is None:
            raise RunnerError("EXPECTED_RELEASE_ID_REQUIRED")
        _validate_remote_config(config)
    return {
        "discovery_db_path": discovery_path,
        "media_db_path": media_path,
        "media_writer_lock_path": writer_lock,
        "run_lock_path": run_lock,
        "title_lock_dir": title_lock_dir,
        "max_items": max_items,
        "visibility_max_items": visibility_max,
        "visibility_seed_max_items": visibility_seed_max,
        "jellyfin_get_max_requests": get_budget,
        "target_dvd_id": target,
    }


@contextmanager
def _exclusive_run_lock(path: Path):
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = None
    try:
        fd = os.open(path, flags, 0o600)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise RunnerError("RUN_LOCK_FILE_INVALID")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RunnerError("RUN_ALREADY_ACTIVE") from exc
        yield
    except RunnerError:
        raise
    except OSError as exc:
        raise RunnerError("RUN_LOCK_UNAVAILABLE") from exc
    finally:
        if fd is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)


class _LibraryStatOnly:
    """Narrow the pipeline's SSH surface to a read-only video stat."""

    def __init__(self, ssh):
        self.__ssh = ssh

    def stat_library(self, relative_path):
        return self.__ssh.stat_library(relative_path)


class _RejectJellyfinRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


class _JellyfinRequestBudget:
    def __init__(
        self,
        max_get_requests: int,
        max_post_requests: int,
        *,
        opener=None,
    ):
        self.max_get_requests = int(max_get_requests)
        self.max_post_requests = int(max_post_requests)
        self.get_requests = 0
        self.post_attempts = 0
        self.opener = opener or urllib.request.build_opener(_RejectJellyfinRedirects())

    def __call__(self, request, *, timeout=10):
        method = request.get_method().upper()
        if method == "GET":
            if self.get_requests >= self.max_get_requests:
                raise RuntimeError("Jellyfin GET request budget exhausted")
            self.get_requests += 1
        elif method == "POST":
            path = urlsplit(request.full_url).path
            if not path.rstrip("/").endswith("/Library/Media/Updated"):
                raise RuntimeError("Jellyfin POST endpoint not allowed")
            if self.post_attempts >= self.max_post_requests:
                raise RuntimeError("Jellyfin POST request budget exhausted")
            self.post_attempts += 1
        else:
            raise RuntimeError("Jellyfin HTTP method not allowed")
        return self.opener.open(request, timeout=timeout)


def _build_services(config: RunnerConfig, normalized: dict) -> dict:
    from teddy_discovery_completion_ssh import CompletionSSH
    from teddy_discovery_jellyfin import JellyfinClient
    from teddy_discovery_jellyfin_visibility import reconcile_jellyfin_visibility
    from teddy_discovery_media_jobs import reconcile_media_jobs, run_retryable_media_jobs
    from teddy_discovery_media_metadata import make_poster_fetcher
    from teddy_discovery_media_pipeline import run_media_pipeline
    from teddy_discovery_media_publish import MediaMetadataSSHMutator

    get_budget = _JellyfinRequestBudget(
        normalized["jellyfin_get_max_requests"],
        normalized["max_items"],
    )
    ssh = CompletionSSH(
        host=config.ssh_host,
        user=config.ssh_user,
        key=os.fspath(config.ssh_key_path),
        known_hosts=os.fspath(config.ssh_known_hosts_path),
        downloads_root=config.library_root,
        library_root=config.library_root,
    )
    jellyfin = JellyfinClient(
        base_url=config.jellyfin_base_url,
        api_key_path=config.jellyfin_key_path,
        opener=get_budget,
    )
    fetcher = make_poster_fetcher(config.poster_proxy_url)
    mutator = MediaMetadataSSHMutator(ssh)
    readonly_ssh = _LibraryStatOnly(ssh)

    def processor(dvd_id):
        return run_media_pipeline(
            db_path=normalized["discovery_db_path"],
            dvd_id=dvd_id,
            ssh=readonly_ssh,
            metadata_mutator=mutator,
            jellyfin=jellyfin,
            fetcher=fetcher,
        )

    return {
        "reconcile": reconcile_media_jobs,
        "run_jobs": run_retryable_media_jobs,
        "visibility": reconcile_jellyfin_visibility,
        "processor": processor,
        "jellyfin": jellyfin,
        "get_budget": get_budget,
    }


def _summarize_jobs(result: dict) -> dict:
    fields = (
        "retryable", "attempted", "completed", "failed", "held_busy",
        "held_lock_unavailable", "held_backoff", "held_fresh_running",
        "held_invalid_timestamp", "held_conflict", "held_invalid_state",
        "held_metadata_not_found", "held_cover_url_missing",
        "held_cover_url_invalid", "poster_pending", "poster_attention",
        "exhausted", "manual_action_updates", "manual_action_updates_deferred",
    )
    return {name: int(result.get(name, 0) or 0) for name in fields}


def _summarize_visibility(result: dict | None) -> dict | None:
    if result is None:
        return None
    fields = (
        "seeded", "checked", "visible", "pending", "attention",
        "skipped_no_present_holding", "jellyfin_mutations",
    )
    return {name: int(result.get(name, 0) or 0) for name in fields}


def run_stage9_media_once(
    config: RunnerConfig,
    *,
    services: dict | None = None,
) -> dict:
    """Validate, then run one bounded Stage9 Media cycle."""
    normalized = _validate_config(
        config,
        require_release_id=(config.apply and services is None),
    )
    if not config.apply:
        return {
            "status": "DRY_RUN",
            "stage": "stage9-media-only",
            "non_media_execution": 0,
            "media_max_items": normalized["max_items"],
            "visibility_max_items": normalized["visibility_max_items"],
            "visibility_seed_max_items": normalized["visibility_seed_max_items"],
            "jellyfin_get_max_requests": normalized["jellyfin_get_max_requests"],
            "database_writes": 0,
            "external_calls": 0,
        }

    with _exclusive_run_lock(normalized["run_lock_path"]):
        active = services if services is not None else _build_services(config, normalized)
        target = normalized["target_dvd_id"]
        registration = active["reconcile"](
            normalized["discovery_db_path"],
            normalized["media_db_path"],
            normalized["media_writer_lock_path"],
            max_items=normalized["max_items"],
            target_dvd_id=target,
        )
        job_result = active["run_jobs"](
            db_path=normalized["media_db_path"],
            discovery_db_path=normalized["discovery_db_path"],
            writer_lock_path=normalized["media_writer_lock_path"],
            processor=active["processor"],
            max_items=normalized["max_items"],
            max_manual_action_updates=normalized["max_items"],
            title_lock_dir=normalized["title_lock_dir"],
            target_dvd_id=target,
        )
        jobs = _summarize_jobs(job_result)
        visibility_result = None
        if not jobs["failed"]:
            visibility_result = active["visibility"](
                normalized["discovery_db_path"],
                normalized["media_db_path"],
                normalized["media_writer_lock_path"],
                active["jellyfin"],
                max_items=normalized["visibility_max_items"],
                max_seed_items=normalized["visibility_seed_max_items"],
                target_dvd_id=target,
            )
        status = "PARTIAL_FAILURE" if jobs["failed"] else "COMPLETE"
        budget = active.get("get_budget")
        return {
            "status": status,
            "stage": "stage9-media-only",
            "non_media_execution": 0,
            "registered": int(registration),
            "media": jobs,
            "jellyfin_visibility": _summarize_visibility(visibility_result),
            "jellyfin_get_requests": int(getattr(budget, "get_requests", 0)),
            "jellyfin_post_attempts": int(getattr(budget, "post_attempts", 0)),
            "media_max_items": normalized["max_items"],
            "visibility_max_items": normalized["visibility_max_items"],
            "visibility_seed_max_items": normalized["visibility_seed_max_items"],
            "jellyfin_get_max_requests": normalized["jellyfin_get_max_requests"],
        }


def _config_from_args(args) -> RunnerConfig:
    return RunnerConfig(
        discovery_db_path=args.discovery_db,
        media_db_path=args.media_db,
        media_writer_lock_path=args.media_writer_lock,
        run_lock_path=args.run_lock,
        title_lock_dir=args.title_lock_dir,
        max_items=args.max_items,
        visibility_max_items=args.visibility_max_items,
        visibility_seed_max_items=args.visibility_seed_max_items,
        jellyfin_get_max_requests=args.jellyfin_get_max_requests,
        target_dvd_id=args.target_dvd_id,
        apply=args.apply,
        confirm=args.confirm,
        ssh_host=args.ssh_host or "",
        ssh_user=args.ssh_user or "",
        ssh_key_path=args.ssh_key,
        ssh_known_hosts_path=args.ssh_known_hosts,
        library_root=args.library_root or "",
        poster_proxy_url=args.poster_proxy_url or "",
        jellyfin_base_url=args.jellyfin_base_url or "",
        jellyfin_key_path=args.jellyfin_key,
        expected_release_id=args.expected_release_id,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Run only bounded Stage9 media metadata jobs."
    )
    parser.add_argument("--discovery-db", required=True, type=Path)
    parser.add_argument("--media-db", required=True, type=Path)
    parser.add_argument("--media-writer-lock", required=True, type=Path)
    parser.add_argument("--run-lock", required=True, type=Path)
    parser.add_argument("--title-lock-dir", required=True, type=Path)
    parser.add_argument("--max-items", type=int, default=1)
    parser.add_argument("--visibility-max-items", type=int, default=1)
    parser.add_argument("--visibility-seed-max-items", type=int, default=1)
    parser.add_argument("--jellyfin-get-max-requests", type=int)
    parser.add_argument("--target-dvd-id")
    parser.add_argument("--expected-release-id")
    parser.add_argument("--ssh-host")
    parser.add_argument("--ssh-user")
    parser.add_argument("--ssh-key", type=Path)
    parser.add_argument("--ssh-known-hosts", type=Path)
    parser.add_argument("--library-root")
    parser.add_argument("--poster-proxy-url")
    parser.add_argument("--jellyfin-base-url")
    parser.add_argument("--jellyfin-key", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)
    try:
        result = run_stage9_media_once(_config_from_args(args))
    except RunnerError as exc:
        print(json.dumps({"status": "ERROR", "error": exc.code}, sort_keys=True))
        return 2
    except Exception:
        print(json.dumps({"status": "ERROR", "error": "STAGE9_MEDIA_RUN_FAILED"}, sort_keys=True))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 1 if result.get("status") == "PARTIAL_FAILURE" else 0


if __name__ == "__main__":
    raise SystemExit(main())
