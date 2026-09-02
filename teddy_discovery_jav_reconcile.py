from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from pathlib import PurePosixPath
import argparse
import json
import os
import posixpath
import sqlite3
import stat

from teddy_discovery_completion_ssh import (
    CompletionSSH,
)
from teddy_discovery_ids import parse_dvd_id
from teddy_discovery_import import import_inventory
from teddy_discovery_media_publish import (
    is_library_sidecar,
)
from teddy_discovery_organizer import (
    VIDEO_EXTENSIONS,
    canonical_destination,
)


STORAGE_ROOT = "jav"
SYNLOGY_METADATA_DIR = "@eaDir"
REMOTE_LIBRARY_ROOT_ENV = "TEDDY_FINAL_LIBRARY_ROOT"
STAGING_ROOT_ENV = "TEDDY_FINAL_REMOTE_ROOT"


class RemoteLibraryRootError(OSError):
    pass


class RemoteProtocolError(OSError):
    pass


@dataclass(frozen=True)
class _FilesystemStat:
    st_mode: int
    st_size: int
    st_mtime_ns: int


@dataclass(frozen=True)
class _FilesystemEntry:
    name: str
    _stat: _FilesystemStat

    def is_symlink(self):
        return stat.S_ISLNK(
            self._stat.st_mode
        )

    def is_dir(self, follow_symlinks=False):
        return stat.S_ISDIR(
            self._stat.st_mode
        )

    def stat(self, follow_symlinks=False):
        return self._stat


def _filesystem_stat(value):
    return _FilesystemStat(
        st_mode=int(value.st_mode),
        st_size=int(value.st_size),
        st_mtime_ns=int(value.st_mtime_ns),
    )


def _payload_stat(payload):
    try:
        return _FilesystemStat(
            st_mode=int(payload["mode"]),
            st_size=int(payload["size"]),
            st_mtime_ns=int(payload["mtime_ns"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RemoteProtocolError(
            "remote filesystem stat payload is invalid"
        ) from exc


def _payload_entry(payload):
    try:
        name = str(payload["name"])
    except (KeyError, TypeError) as exc:
        raise RemoteProtocolError(
            "remote filesystem entry payload is invalid"
        ) from exc

    if not name or "/" in name or name in (".", ".."):
        raise RemoteProtocolError(
            "remote filesystem entry name is invalid"
        )

    return _FilesystemEntry(
        name=name,
        _stat=_payload_stat(payload),
    )


def remote_library_root(value=None):
    raw = str(
        value
        or os.environ.get(REMOTE_LIBRARY_ROOT_ENV)
        or ""
    ).strip()

    if not raw:
        raise RemoteLibraryRootError(
            REMOTE_LIBRARY_ROOT_ENV
            + " or explicit remote library root is required"
        )

    root = posixpath.normpath(raw)

    if not root.startswith("/") or root == "/":
        raise RemoteLibraryRootError(
            "remote library root must be an absolute non-root path"
        )

    staging = str(
        os.environ.get(STAGING_ROOT_ENV)
        or ""
    ).strip()

    if staging and root == posixpath.normpath(staging):
        raise RemoteLibraryRootError(
            "remote library root must not equal "
            + STAGING_ROOT_ENV
        )

    return root


class LocalJAVFilesystem:
    def __init__(self, root):
        self.root = Path(root)

    def _path(self, relative_path):
        if relative_path in ("", "."):
            return self.root

        return self.root.joinpath(
            *str(relative_path).split("/")
        )

    def lstat(self, relative_path):
        return _filesystem_stat(
            os.lstat(
                self._path(relative_path)
            )
        )

    def listdir(self, relative_path):
        path = self._path(relative_path)

        with os.scandir(path) as iterator:
            entries = []

            for entry in iterator:
                entries.append(
                    _FilesystemEntry(
                        name=entry.name,
                        _stat=_filesystem_stat(
                            entry.stat(
                                follow_symlinks=False
                            )
                        ),
                    )
                )

        return sorted(
            entries,
            key=lambda entry: entry.name,
        )


_REMOTE_LSTAT_SCRIPT = r'''
# TEDDY_REMOTE_JAV_LSTAT_V1
import json
import os
import stat
import sys


def emit(value):
    print(json.dumps(value, ensure_ascii=False))


def error(exc):
    emit({
        "status": "error",
        "kind": (
            "permission"
            if isinstance(exc, PermissionError)
            else "io"
        ),
        "detail": str(exc),
    })


root = os.path.normpath(sys.argv[1])
relative = sys.argv[2]

if not root.startswith("/") or root == "/":
    emit({
        "status": "error",
        "kind": "protocol",
        "detail": "invalid remote library root",
    })
    raise SystemExit(0)

candidate = (
    root
    if relative in ("", ".")
    else os.path.join(root, relative)
)

try:
    value = os.lstat(candidate)
except FileNotFoundError:
    emit({"status": "missing"})
    raise SystemExit(0)
except OSError as exc:
    error(exc)
    raise SystemExit(0)

if stat.S_ISLNK(value.st_mode):
    emit({
        "status": "ok",
        "mode": int(value.st_mode),
        "size": int(value.st_size),
        "mtime_ns": int(value.st_mtime_ns),
    })
    raise SystemExit(0)

root_real = os.path.realpath(root)
candidate_real = os.path.realpath(candidate)

try:
    inside = os.path.commonpath([
        root_real,
        candidate_real,
    ]) == root_real
except ValueError:
    inside = False

if not inside:
    emit({
        "status": "error",
        "kind": "protocol",
        "detail": "remote path escapes library root",
    })
    raise SystemExit(0)

emit({
    "status": "ok",
    "mode": int(value.st_mode),
    "size": int(value.st_size),
    "mtime_ns": int(value.st_mtime_ns),
})
'''


_REMOTE_LISTDIR_SCRIPT = r'''
# TEDDY_REMOTE_JAV_LISTDIR_V1
import json
import os
import stat
import sys


def emit(value):
    print(json.dumps(value, ensure_ascii=False))


def error(exc):
    emit({
        "status": "error",
        "kind": (
            "permission"
            if isinstance(exc, PermissionError)
            else "io"
        ),
        "detail": str(exc),
    })


root = os.path.normpath(sys.argv[1])
relative = sys.argv[2]

if not root.startswith("/") or root == "/":
    emit({
        "status": "error",
        "kind": "protocol",
        "detail": "invalid remote library root",
    })
    raise SystemExit(0)

candidate = (
    root
    if relative in ("", ".")
    else os.path.join(root, relative)
)

try:
    candidate_stat = os.lstat(candidate)
except FileNotFoundError:
    emit({"status": "missing"})
    raise SystemExit(0)
except OSError as exc:
    error(exc)
    raise SystemExit(0)

if stat.S_ISLNK(candidate_stat.st_mode):
    emit({
        "status": "directory_symlink",
    })
    raise SystemExit(0)

root_real = os.path.realpath(root)
candidate_real = os.path.realpath(candidate)

try:
    inside = os.path.commonpath([
        root_real,
        candidate_real,
    ]) == root_real
except ValueError:
    inside = False

if not inside:
    emit({
        "status": "error",
        "kind": "protocol",
        "detail": "remote path escapes library root",
    })
    raise SystemExit(0)

if not stat.S_ISDIR(candidate_stat.st_mode):
    emit({
        "status": "not_directory",
    })
    raise SystemExit(0)

entries = []

try:
    with os.scandir(candidate_real) as iterator:
        for entry in iterator:
            value = entry.stat(
                follow_symlinks=False
            )
            entries.append({
                "name": entry.name,
                "mode": int(value.st_mode),
                "size": int(value.st_size),
                "mtime_ns": int(value.st_mtime_ns),
            })
except OSError as exc:
    error(exc)
    raise SystemExit(0)

entries.sort(key=lambda item: item["name"])
emit({
    "status": "ok",
    "entries": entries,
})
'''


class RemoteJAVFilesystem:
    """Read-only bounded filesystem facade over the Stage9 SSH transport."""

    def __init__(self, ssh, library_root=None):
        self.ssh = ssh
        self.library_root = str(
            library_root
            or os.environ.get(REMOTE_LIBRARY_ROOT_ENV)
            or ""
        ).strip()

        try:
            self.library_root = remote_library_root(
                self.library_root
            )
            self._configuration_error = None
        except RemoteLibraryRootError as exc:
            self._configuration_error = exc

    def _ensure_configured(self):
        if self._configuration_error is not None:
            raise self._configuration_error

    @staticmethod
    def _safe_relative(relative_path):
        raw = str(relative_path or "").strip()

        if raw in ("", "."):
            return "."

        path = PurePosixPath(raw)

        if (
            path.is_absolute()
            or ".." in path.parts
            or any(
                part in ("", ".")
                or "\x00" in part
                or "\n" in part
                or "\r" in part
                for part in path.parts
            )
        ):
            raise RemoteProtocolError(
                "remote filesystem relative path is invalid"
            )

        return path.as_posix()

    def _response(self, script, relative_path):
        self._ensure_configured()
        relative_path = self._safe_relative(
            relative_path
        )

        try:
            raw = self.ssh._run_python(
                script,
                self.library_root,
                relative_path,
            )
        except Exception as exc:
            raise RemoteProtocolError(
                "remote SSH filesystem request failed: "
                + str(exc)
            ) from exc

        try:
            value = json.loads(
                raw or ""
            )
        except json.JSONDecodeError as exc:
            raise RemoteProtocolError(
                "remote filesystem response is not JSON"
            ) from exc

        if not isinstance(value, dict):
            raise RemoteProtocolError(
                "remote filesystem response is not an object"
            )

        status = value.get("status")

        if status == "missing":
            raise FileNotFoundError(
                "remote library path is unavailable: "
                + str(relative_path)
            )

        if status == "error":
            detail = str(
                value.get("detail")
                or "remote filesystem I/O error"
            )

            if value.get("kind") == "permission":
                raise PermissionError(detail)

            raise RemoteProtocolError(detail)

        return value

    def lstat(self, relative_path):
        value = self._response(
            _REMOTE_LSTAT_SCRIPT,
            relative_path,
        )

        if value.get("status") != "ok":
            raise RemoteProtocolError(
                "remote lstat response is invalid"
            )

        return _payload_stat(value)

    def listdir(self, relative_path):
        value = self._response(
            _REMOTE_LISTDIR_SCRIPT,
            relative_path,
        )

        status = value.get("status")

        if status == "directory_symlink":
            raise RemoteProtocolError(
                "remote directory is a symlink"
            )

        if status == "not_directory":
            raise RemoteProtocolError(
                "remote path is not a directory"
            )

        if status != "ok" or not isinstance(
            value.get("entries"),
            list,
        ):
            raise RemoteProtocolError(
                "remote listdir response is invalid"
            )

        return sorted(
            (
                _payload_entry(item)
                for item in value["entries"]
            ),
            key=lambda entry: entry.name,
        )


class ReconciliationUnsafe(RuntimeError):
    def __init__(self, report):
        super().__init__(
            "bounded JAV reconciliation is not apply-eligible"
        )
        self.report = report


@dataclass(frozen=True)
class Finding:
    category: str
    relative_path: str
    dvd_id: str | None
    detail: str
    blocking: bool


@dataclass(frozen=True)
class BoundedScan:
    root_available: bool
    mount_available: bool | None
    root_entry_count: int
    records: tuple[dict, ...]
    findings: tuple[Finding, ...]
    complete: bool


@dataclass(frozen=True)
class ReconciliationReport:
    root: str
    db_available: bool
    root_available: bool
    mount_available: bool | None
    root_entry_count: int
    scan_complete: bool
    apply_eligible: bool
    canonical_present_files: tuple[dict, ...]
    findings: tuple[Finding, ...]

    def to_dict(self):
        findings = [
            asdict(item)
            for item in self.findings
        ]

        return {
            "root": self.root,
            "storage_root": STORAGE_ROOT,
            "db_available": self.db_available,
            "root_available": self.root_available,
            "mount_available": self.mount_available,
            "root_entry_count": self.root_entry_count,
            "scan_complete": self.scan_complete,
            "apply_eligible": self.apply_eligible,
            "canonical_present_files": [
                dict(item)
                for item in self.canonical_present_files
            ],
            "findings": findings,
            "finding_counts": _finding_counts(
                self.findings
            ),
        }


def _finding_counts(findings):
    counts = defaultdict(int)

    for finding in findings:
        counts[finding.category] += 1

    return dict(
        sorted(counts.items())
    )


def _error_category(exc):
    if isinstance(
        exc,
        RemoteLibraryRootError,
    ):
        return "REMOTE_LIBRARY_ROOT_UNAVAILABLE"

    if isinstance(exc, PermissionError):
        return "PERMISSION_ERROR"

    return "IO_ERROR"


def _add_error(
    findings,
    path,
    exc,
):
    findings.append(
        Finding(
            category=_error_category(exc),
            relative_path=str(path),
            dvd_id=None,
            detail=str(exc),
            blocking=True,
        )
    )


def _read_entries(filesystem, relative_path, findings):
    try:
        return filesystem.listdir(
            relative_path
        )

    except OSError as exc:
        _add_error(
            findings,
            relative_path,
            exc,
        )
        return None


def _entry_relative(parent, name):
    if parent == ".":
        return name

    return parent + "/" + name


def _is_synology_metadata(entry):
    return (
        entry.name == SYNLOGY_METADATA_DIR
        and entry.is_dir(
            follow_symlinks=False
        )
    )


def _unexpected(
    findings,
    relative_path,
    detail,
):
    findings.append(
        Finding(
            category="UNEXPECTED_LAYOUT",
            relative_path=relative_path,
            dvd_id=None,
            detail=detail,
            blocking=True,
        )
    )


def _symlink(
    findings,
    relative_path,
):
    findings.append(
        Finding(
            category="SYMLINK",
            relative_path=relative_path,
            dvd_id=None,
            detail="symlink is not an ownership source",
            blocking=True,
        )
    )


def _canonical_record(
    entry,
    relative_path,
    parsed,
    findings,
):
    try:
        file_stat = entry.stat(
            follow_symlinks=False
        )

    except OSError as exc:
        _add_error(
            findings,
            relative_path,
            exc,
        )
        return None

    if not stat.S_ISREG(file_stat.st_mode):
        _unexpected(
            findings,
            relative_path,
            "leaf is not a regular file",
        )
        return None

    if parsed is None:
        findings.append(
            Finding(
                category="UNMATCHED_DVD_ID",
                relative_path=relative_path,
                dvd_id=None,
                detail="supported video filename has no DVD-ID",
                blocking=True,
            )
        )
        return None

    candidates = getattr(
        parsed,
        "candidates",
        None,
    )

    if candidates and len(candidates) > 1:
        findings.append(
            Finding(
                category="AMBIGUOUS_DVD_ID",
                relative_path=relative_path,
                dvd_id=None,
                detail="DVD-ID parser returned multiple candidates",
                blocking=True,
            )
        )
        return None

    dvd_id = parsed.dvd_id
    expected = canonical_destination(
        dvd_id,
        Path(entry.name).suffix,
    ).as_posix()

    if relative_path != expected:
        _unexpected(
            findings,
            relative_path,
            "video is not at PREFIX/DVD-ID/DVD-ID.ext",
        )
        return None

    return {
        "classification": "CANONICAL_PRESENT",
        "relative_path": relative_path,
        "dvd_id": dvd_id,
        "parse_status": "MATCHED",
        "parse_method": parsed.method,
        "parse_candidates_json": json.dumps(
            [dvd_id],
            ensure_ascii=False,
        ),
        "size_bytes": int(file_stat.st_size),
        "mtime_ns": int(file_stat.st_mtime_ns),
    }


def scan_bounded(
    root: Path,
    *,
    expected_mount: Path | None = None,
    filesystem=None,
):
    root_label = str(root)

    if filesystem is None:
        root = Path(root)
        filesystem = LocalJAVFilesystem(root)

    findings = []

    mount_available = None

    if expected_mount is not None:
        try:
            mount_available = os.path.ismount(
                expected_mount
            )

        except OSError as exc:
            _add_error(
                findings,
                expected_mount,
                exc,
            )
            mount_available = False

        if not mount_available:
            findings.append(
                Finding(
                    category="MOUNT_UNAVAILABLE",
                    relative_path=str(expected_mount),
                    dvd_id=None,
                    detail="expected mount is not mounted",
                    blocking=True,
                )
            )

            return BoundedScan(
                root_available=False,
                mount_available=False,
                root_entry_count=0,
                records=(),
                findings=tuple(findings),
                complete=False,
            )

    try:
        root_stat = filesystem.lstat(".")

    except FileNotFoundError as exc:
        findings.append(
            Finding(
                category="ROOT_UNAVAILABLE",
                relative_path=root_label,
                dvd_id=None,
                detail=str(exc),
                blocking=True,
            )
        )
        return BoundedScan(
            root_available=False,
            mount_available=mount_available,
            root_entry_count=0,
            records=(),
            findings=tuple(findings),
            complete=False,
        )

    except OSError as exc:
        _add_error(
            findings,
            root_label,
            exc,
        )
        return BoundedScan(
            root_available=False,
            mount_available=mount_available,
            root_entry_count=0,
            records=(),
            findings=tuple(findings),
            complete=False,
        )

    if stat.S_ISLNK(root_stat.st_mode):
        _symlink(
            findings,
            ".",
        )
        return BoundedScan(
            root_available=False,
            mount_available=mount_available,
            root_entry_count=0,
            records=(),
            findings=tuple(findings),
            complete=False,
        )

    if not stat.S_ISDIR(root_stat.st_mode):
        findings.append(
            Finding(
                category="ROOT_UNAVAILABLE",
                relative_path=root_label,
                dvd_id=None,
                detail="root is not a directory",
                blocking=True,
            )
        )
        return BoundedScan(
            root_available=False,
            mount_available=mount_available,
            root_entry_count=0,
            records=(),
            findings=tuple(findings),
            complete=False,
        )

    root_entries = _read_entries(
        filesystem,
        ".",
        findings,
    )

    if root_entries is None:
        return BoundedScan(
            root_available=True,
            mount_available=mount_available,
            root_entry_count=0,
            records=(),
            findings=tuple(findings),
            complete=False,
        )

    records = []

    for prefix_entry in root_entries:
        prefix_relative = prefix_entry.name

        if _is_synology_metadata(prefix_entry):
            continue

        if prefix_entry.is_symlink():
            _symlink(
                findings,
                prefix_relative,
            )
            continue

        if not prefix_entry.is_dir(
            follow_symlinks=False
        ):
            _unexpected(
                findings,
                prefix_relative,
                "ROOT entry is not a PREFIX directory",
            )
            continue

        dvd_entries = _read_entries(
            filesystem,
            prefix_relative,
            findings,
        )

        if dvd_entries is None:
            continue

        for dvd_entry in dvd_entries:
            dvd_relative = _entry_relative(
                prefix_relative,
                dvd_entry.name,
            )

            if _is_synology_metadata(dvd_entry):
                continue

            if dvd_entry.is_symlink():
                _symlink(
                    findings,
                    dvd_relative,
                )
                continue

            if not dvd_entry.is_dir(
                follow_symlinks=False
            ):
                _unexpected(
                    findings,
                    dvd_relative,
                    "PREFIX entry is not a DVD-ID directory",
                )
                continue

            leaf_entries = _read_entries(
                filesystem,
                dvd_relative,
                findings,
            )

            if leaf_entries is None:
                continue

            records_before = len(records)

            for leaf_entry in leaf_entries:
                relative_path = _entry_relative(
                    dvd_relative,
                    leaf_entry.name,
                )

                if _is_synology_metadata(leaf_entry):
                    continue

                if leaf_entry.is_symlink():
                    _symlink(
                        findings,
                        relative_path,
                    )
                    continue

                if leaf_entry.is_dir(
                    follow_symlinks=False
                ):
                    _unexpected(
                        findings,
                        relative_path,
                        "nested directory exceeds bounded depth",
                    )
                    continue

                suffix = Path(
                    leaf_entry.name
                ).suffix.lower()

                if suffix not in VIDEO_EXTENSIONS:
                    if is_library_sidecar(
                        leaf_entry.name,
                        dvd_entry.name,
                    ):
                        continue

                    _unexpected(
                        findings,
                        relative_path,
                        "unknown file in DVD-ID directory",
                    )
                    continue

                parsed = parse_dvd_id(
                    leaf_entry.name
                )

                record = _canonical_record(
                    leaf_entry,
                    relative_path,
                    parsed,
                    findings,
                )

                if record is not None:
                    records.append(record)

            if len(records) == records_before:
                _unexpected(
                    findings,
                    dvd_relative,
                    "DVD-ID directory has no canonical media file",
                )

    by_dvd_id = defaultdict(list)

    for record in records:
        by_dvd_id[record["dvd_id"]].append(
            record
        )

    for dvd_id, duplicate_records in sorted(
        by_dvd_id.items()
    ):
        if len(duplicate_records) < 2:
            continue

        paths = ", ".join(
            sorted(
                item["relative_path"]
                for item in duplicate_records
            )
        )

        for record in duplicate_records:
            findings.append(
                Finding(
                    category="DUPLICATE_PHYSICAL_MEDIA",
                    relative_path=record[
                        "relative_path"
                    ],
                    dvd_id=dvd_id,
                    detail=(
                        "multiple canonical video files share DVD-ID: "
                        + paths
                    ),
                    blocking=True,
                )
            )

    records.sort(
        key=lambda item: item["relative_path"]
    )

    complete = not any(
        finding.blocking
        for finding in findings
    )

    return BoundedScan(
        root_available=True,
        mount_available=mount_available,
        root_entry_count=len(root_entries),
        records=tuple(records),
        findings=tuple(findings),
        complete=complete,
    )


def _read_holdings(db_path: Path):
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    db = sqlite3.connect(
        uri,
        uri=True,
    )
    db.row_factory = sqlite3.Row

    try:
        integrity = db.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        if integrity != "ok":
            raise RuntimeError(
                "database integrity check failed: "
                + str(integrity)
            )

        rows = [
            dict(row)
            for row in db.execute(
                """
                SELECT
                    holding_id,
                    storage_root,
                    relative_path,
                    dvd_id,
                    parse_status,
                    parse_method,
                    parse_candidates_json,
                    size_bytes,
                    mtime_ns,
                    discovered_by,
                    present,
                    first_seen_at,
                    last_seen_at,
                    last_seen_run_id
                FROM holdings
                WHERE storage_root = ?
                ORDER BY relative_path
                """,
                (STORAGE_ROOT,),
            )
        ]

        return rows

    finally:
        db.close()


def _db_finding(relative_path, detail):
    return Finding(
        category="DB_UNAVAILABLE",
        relative_path=relative_path,
        dvd_id=None,
        detail=detail,
        blocking=True,
    )


def reconcile(
    db_path: Path,
    root: Path,
    *,
    expected_mount: Path | None = None,
    filesystem=None,
):
    scan = scan_bounded(
        root,
        expected_mount=expected_mount,
        filesystem=filesystem,
    )

    findings = list(scan.findings)

    try:
        holdings = _read_holdings(
            db_path
        )
        db_available = True

    except (OSError, sqlite3.Error, RuntimeError) as exc:
        holdings = []
        db_available = False
        findings.append(
            _db_finding(
                str(db_path),
                str(exc),
            )
        )

    present_holdings = {
        row["relative_path"]: row
        for row in holdings
        if int(row.get("present") or 0) == 1
    }

    all_holdings = {
        row["relative_path"]: row
        for row in holdings
    }

    records_by_path = {
        row["relative_path"]: row
        for row in scan.records
    }

    for relative_path, holding in sorted(
        present_holdings.items()
    ):
        record = records_by_path.get(
            relative_path
        )

        if record is None:
            findings.append(
                Finding(
                    category="DB_PRESENT_FILESYSTEM_MISSING",
                    relative_path=relative_path,
                    dvd_id=holding.get("dvd_id"),
                    detail="present=1 holding was not observed",
                    blocking=False,
                )
            )
            continue

        if holding.get("dvd_id") != record["dvd_id"]:
            findings.append(
                Finding(
                    category="DVD_ID_MISMATCH",
                    relative_path=relative_path,
                    dvd_id=record["dvd_id"],
                    detail="DB DVD-ID differs from canonical path",
                    blocking=True,
                )
            )

        if holding.get("parse_status") != "MATCHED":
            findings.append(
                Finding(
                    category="DB_STATUS_MISMATCH",
                    relative_path=relative_path,
                    dvd_id=record["dvd_id"],
                    detail="present holding is not MATCHED",
                    blocking=True,
                )
            )

        if int(holding["size_bytes"]) != int(
            record["size_bytes"]
        ):
            findings.append(
                Finding(
                    category="SIZE_MISMATCH",
                    relative_path=relative_path,
                    dvd_id=record["dvd_id"],
                    detail=(
                        f"DB={holding['size_bytes']} "
                        f"filesystem={record['size_bytes']}"
                    ),
                    blocking=False,
                )
            )

        if int(holding["mtime_ns"]) != int(
            record["mtime_ns"]
        ):
            findings.append(
                Finding(
                    category="MTIME_MISMATCH",
                    relative_path=relative_path,
                    dvd_id=record["dvd_id"],
                    detail=(
                        f"DB={holding['mtime_ns']} "
                        f"filesystem={record['mtime_ns']}"
                    ),
                    blocking=False,
                )
            )

    for relative_path, record in sorted(
        records_by_path.items()
    ):
        holding = all_holdings.get(
            relative_path
        )

        if holding is None:
            findings.append(
                Finding(
                    category="FILESYSTEM_PRESENT_DB_MISSING",
                    relative_path=relative_path,
                    dvd_id=record["dvd_id"],
                    detail="canonical file has no holdings row",
                    blocking=False,
                )
            )

        elif int(holding.get("present") or 0) == 0:
            findings.append(
                Finding(
                    category="ABSENT_HOLDING_REAPPEARED",
                    relative_path=relative_path,
                    dvd_id=record["dvd_id"],
                    detail="present=0 row observed again at same path",
                    blocking=False,
                )
            )

    present_by_dvd_id = defaultdict(list)

    for holding in present_holdings.values():
        dvd_id = holding.get("dvd_id")
        if dvd_id:
            present_by_dvd_id[dvd_id].append(
                holding["relative_path"]
            )

    for dvd_id, paths in sorted(
        present_by_dvd_id.items()
    ):
        if len(paths) < 2:
            continue

        for relative_path in sorted(paths):
            findings.append(
                Finding(
                    category="DB_DUPLICATE_PRESENT",
                    relative_path=relative_path,
                    dvd_id=dvd_id,
                    detail="multiple present holdings share DVD-ID",
                    blocking=True,
                )
            )

    if (
        scan.root_available
        and scan.mount_available is not False
        and not scan.records
        and any(
            int(row.get("present") or 0) == 1
            for row in holdings
        )
    ):
        category = (
            "EMPTY_ROOT_WITH_PRESENT_HOLDINGS"
            if scan.root_entry_count == 0
            else "EMPTY_SCAN_WITH_PRESENT_HOLDINGS"
        )
        findings.append(
            Finding(
                category=category,
                relative_path=".",
                dvd_id=None,
                detail=(
                    "existing present holdings require a non-empty "
                    "canonical scan"
                ),
                blocking=True,
            )
        )

    findings.sort(
        key=lambda item: (
            item.category,
            item.relative_path,
            item.dvd_id or "",
            item.detail,
        )
    )

    apply_eligible = (
        db_available
        and scan.complete
        and not any(
            finding.blocking
            for finding in findings
        )
    )

    return ReconciliationReport(
        root=str(root),
        db_available=db_available,
        root_available=scan.root_available,
        mount_available=scan.mount_available,
        root_entry_count=scan.root_entry_count,
        scan_complete=scan.complete,
        apply_eligible=apply_eligible,
        canonical_present_files=scan.records,
        findings=tuple(findings),
    )


def apply_reconciliation(
    db_path: Path,
    root: Path,
    *,
    expected_mount: Path | None = None,
    filesystem=None,
):
    report = reconcile(
        db_path,
        root,
        expected_mount=expected_mount,
        filesystem=filesystem,
    )

    if not report.apply_eligible:
        raise ReconciliationUnsafe(
            report
        )

    result = import_inventory(
        db_path=db_path,
        root=root,
        storage_root=STORAGE_ROOT,
        scanner=lambda _root: list(
            report.canonical_present_files
        ),
    )

    payload = report.to_dict()
    payload.update(
        {
            "applied": True,
            "run_id": result["run_id"],
            "counts": {
                key: result[key]
                for key in (
                    "MATCHED",
                    "AMBIGUOUS",
                    "UNMATCHED",
                )
            },
        }
    )
    return payload


def reconcile_remote(
    db_path: Path,
    ssh,
    *,
    library_root=None,
):
    filesystem = RemoteJAVFilesystem(
        ssh,
        library_root=library_root,
    )

    return reconcile(
        db_path,
        filesystem.library_root
        or "<remote-library-root>",
        filesystem=filesystem,
    )


def apply_remote_reconciliation(
    db_path: Path,
    ssh,
    *,
    library_root=None,
):
    filesystem = RemoteJAVFilesystem(
        ssh,
        library_root=library_root,
    )

    return apply_reconciliation(
        db_path,
        filesystem.library_root
        or "<remote-library-root>",
        filesystem=filesystem,
    )


def _print_report(report):
    print(
        json.dumps(
            report.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Bounded JAV holdings reconciliation"
        )
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    for command in ("report", "apply"):
        subparser = subparsers.add_parser(
            command
        )
        subparser.add_argument(
            "--db",
            required=True,
            type=Path,
        )
        subparser.add_argument(
            "--root",
            required=True,
            type=Path,
        )
        subparser.add_argument(
            "--expected-mount",
            type=Path,
            help=(
                "mountpoint that must be mounted before scanning"
            ),
        )

    for command in ("remote-report", "remote-apply"):
        subparser = subparsers.add_parser(
            command
        )
        subparser.add_argument(
            "--db",
            required=True,
            type=Path,
        )
        subparser.add_argument(
            "--ssh-host",
            default=os.environ.get(
                "TEDDY_FINAL_SSH_HOST",
                "",
            ),
        )
        subparser.add_argument(
            "--ssh-user",
            default=os.environ.get(
                "TEDDY_FINAL_SSH_USER",
                "",
            ),
        )
        subparser.add_argument(
            "--ssh-key",
            default=os.environ.get(
                "TEDDY_FINAL_SSH_KEY",
                "",
            ),
        )
        subparser.add_argument(
            "--ssh-known-hosts",
            default=os.environ.get(
                "TEDDY_FINAL_SSH_KNOWN_HOSTS",
                "",
            ),
        )
        subparser.add_argument(
            "--remote-library-root",
            default=os.environ.get(
                REMOTE_LIBRARY_ROOT_ENV,
                "",
            ),
        )

    args = parser.parse_args()

    if args.command == "report":
        _print_report(
            reconcile(
                args.db,
                args.root,
                expected_mount=args.expected_mount,
            )
        )
        return

    if args.command in {
        "remote-report",
        "remote-apply",
    }:
        settings = {
            "host": args.ssh_host,
            "user": args.ssh_user,
            "key": args.ssh_key,
            "known_hosts": args.ssh_known_hosts,
        }

        missing = [
            name
            for name, value in settings.items()
            if not str(value or "").strip()
        ]

        if missing:
            parser.error(
                "remote SSH setting missing: "
                + ", ".join(missing)
            )

        try:
            library_root = remote_library_root(
                args.remote_library_root
            )

        except RemoteLibraryRootError as exc:
            parser.error(str(exc))

        ssh = CompletionSSH(
            host=args.ssh_host,
            user=args.ssh_user,
            key=args.ssh_key,
            known_hosts=args.ssh_known_hosts,
            downloads_root="",
            library_root=library_root,
        )

        if args.command == "remote-report":
            _print_report(
                reconcile_remote(
                    args.db,
                    ssh,
                    library_root=library_root,
                )
            )
            return

        try:
            result = apply_remote_reconciliation(
                args.db,
                ssh,
                library_root=library_root,
            )

        except ReconciliationUnsafe as exc:
            _print_report(exc.report)
            raise SystemExit(2)

        print(
            json.dumps(
                result,
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return

    try:
        result = apply_reconciliation(
            args.db,
            args.root,
            expected_mount=args.expected_mount,
        )

    except ReconciliationUnsafe as exc:
        _print_report(exc.report)
        raise SystemExit(2)

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
