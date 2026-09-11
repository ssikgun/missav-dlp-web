"""Durable Stage12 rollout state and read-only publication preflight.

The rollout state is intentionally separate from the Discovery holdings DB.
The preflight consumes the CP1 inventory, validates an existing Stage11
artifact bundle and source snapshot, and checks one exact NAS destination.  It
never publishes, writes NAS media, edits Jellyfin, or runs a Stage11 provider
or model.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import stat

from teddy_discovery_asr import ASRSourceSnapshot
from teddy_discovery_asr_artifact import (
    MAX_ASR_ARTIFACT_BYTES,
    parse_asr_result_bytes,
    require_matching_asr_source,
)
from teddy_discovery_availability import canonical_dvd_id
from teddy_discovery_completion_ssh import CompletionSSH
from teddy_discovery_jav_reconcile import RemoteJAVFilesystem
from teddy_discovery_ko_srt import generate_korean_srt
from teddy_discovery_stage11_controller import (
    BASELINE_ASR_FILENAME,
    CLEAN_SRT_FILENAME,
    MAX_STAGE11_REPORT_BYTES,
    MECHANICAL_REPORT_FILENAME,
    _parse_report,
    _validate_existing_completion,
)
from teddy_discovery_stage12_inventory import (
    ELIGIBLE_NEEDS_KO,
    EXISTING_KO_ABSENT,
    SKIPPED_EXISTING_KO,
    UNRESOLVED,
    Stage12HoldingInventoryRecord,
    Stage12HoldingsInventory,
    Stage12HoldingsInventoryReport,
    Stage12InventoryError,
    build_subtitle_ssh_reader,
)
from teddy_discovery_subtitle import (
    CanonicalVideoHolding,
    derive_target_ko_relative,
    validate_canonical_holding,
)
from teddy_discovery_subtitle_text import (
    MAX_SUBTITLE_BYTES,
    SubtitleTextError,
    parse_subtitle_bytes,
)


STATE_PENDING = "PENDING"
STATE_RUNNING = "RUNNING"
STATE_GENERATED = "GENERATED"
STATE_PUBLISHED = "PUBLISHED"
STATE_SKIPPED_EXISTING_KO = "SKIPPED_EXISTING_KO"
STATE_UNRESOLVED = "UNRESOLVED"
STATE_FAILED_RETRYABLE = "FAILED_RETRYABLE"
STATE_FAILED_TERMINAL = "FAILED_TERMINAL"

STATE_STATUSES = (
    STATE_PENDING,
    STATE_RUNNING,
    STATE_GENERATED,
    STATE_PUBLISHED,
    STATE_SKIPPED_EXISTING_KO,
    STATE_UNRESOLVED,
    STATE_FAILED_RETRYABLE,
    STATE_FAILED_TERMINAL,
)

PUBLICATION_READY = "READY"
PUBLICATION_BLOCKED_EXISTING_KO = "BLOCKED_EXISTING_KO"
PUBLICATION_BLOCKED_INVALID_ARTIFACT = "BLOCKED_INVALID_ARTIFACT"
PUBLICATION_BLOCKED_SOURCE_DRIFT = "BLOCKED_SOURCE_DRIFT"
PUBLICATION_UNRESOLVED = "UNRESOLVED"

_ALLOWED_TRANSITIONS = {
    STATE_PENDING: frozenset(
        {STATE_RUNNING, STATE_FAILED_RETRYABLE, STATE_UNRESOLVED}
    ),
    STATE_RUNNING: frozenset(
        {
            STATE_PENDING,
            STATE_GENERATED,
            STATE_FAILED_RETRYABLE,
            STATE_FAILED_TERMINAL,
            STATE_UNRESOLVED,
        }
    ),
    STATE_GENERATED: frozenset(
        {STATE_PUBLISHED, STATE_FAILED_RETRYABLE, STATE_FAILED_TERMINAL}
    ),
    STATE_PUBLISHED: frozenset(),
    STATE_SKIPPED_EXISTING_KO: frozenset(),
    STATE_UNRESOLVED: frozenset(),
    STATE_FAILED_RETRYABLE: frozenset(
        {STATE_RUNNING, STATE_FAILED_TERMINAL, STATE_UNRESOLVED}
    ),
    STATE_FAILED_TERMINAL: frozenset(),
}

_INITIAL_STATUS = {
    ELIGIBLE_NEEDS_KO: STATE_PENDING,
    SKIPPED_EXISTING_KO: STATE_SKIPPED_EXISTING_KO,
    UNRESOLVED: STATE_UNRESOLVED,
}

_STATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS stage12_rollout_titles (
    dvd_id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (
        status IN (
            'PENDING',
            'RUNNING',
            'GENERATED',
            'PUBLISHED',
            'SKIPPED_EXISTING_KO',
            'UNRESOLVED',
            'FAILED_RETRYABLE',
            'FAILED_TERMINAL'
        )
    ),
    holding_identity TEXT NOT NULL,
    media_path_identity TEXT NOT NULL,
    existing_ko TEXT NOT NULL,
    eligibility TEXT NOT NULL,
    inventory_reason TEXT NOT NULL,
    source_size_bytes INTEGER NOT NULL CHECK (source_size_bytes > 0),
    source_mtime_ns INTEGER NOT NULL CHECK (source_mtime_ns >= 0),
    artifact_path TEXT,
    artifact_sha256 TEXT,
    report_path TEXT,
    report_sha256 TEXT,
    destination_relative TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    transition_sequence INTEGER NOT NULL CHECK (transition_sequence >= 1),
    last_transition_reason TEXT NOT NULL,
    last_transition_provenance_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stage12_rollout_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    dvd_id TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT NOT NULL,
    transition_sequence INTEGER NOT NULL CHECK (transition_sequence >= 1),
    transitioned_at TEXT NOT NULL,
    reason TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    FOREIGN KEY (dvd_id) REFERENCES stage12_rollout_titles(dvd_id)
);

CREATE INDEX IF NOT EXISTS idx_stage12_rollout_status
ON stage12_rollout_titles(status, dvd_id);

CREATE INDEX IF NOT EXISTS idx_stage12_rollout_events_title
ON stage12_rollout_events(dvd_id, transition_sequence);
"""


class Stage12RolloutError(RuntimeError):
    """Base class for durable Stage12 rollout failures."""


class Stage12RolloutValidationError(Stage12RolloutError):
    """Raised when state input or a transition is unsafe."""


class Stage12RolloutIdentityError(Stage12RolloutValidationError):
    """Raised when current inventory is detached from stored state."""


class Stage12InvalidTransitionError(Stage12RolloutValidationError):
    """Raised when a state transition is not in the frozen transition map."""


class Stage12PublicationPreflightError(Stage12RolloutError):
    """Raised for a malformed preflight dependency or configuration."""


@dataclass(frozen=True)
class Stage12RolloutState:
    dvd_id: str
    status: str
    holding_identity: str
    media_path_identity: str
    existing_ko: str
    eligibility: str
    inventory_reason: str
    source_size_bytes: int
    source_mtime_ns: int
    artifact_path: str | None
    artifact_sha256: str | None
    report_path: str | None
    report_sha256: str | None
    destination_relative: str | None
    created_at: str
    updated_at: str
    transition_sequence: int
    last_transition_reason: str
    last_transition_provenance_json: str


@dataclass(frozen=True)
class Stage12PublicationPreflight:
    """Read-only result for one generic publication canary candidate."""

    canary_dvd_id: str | None
    source_media_path: str | None
    destination_ko_path: str | None
    destination_exists: bool | None
    clean_path: str | None
    clean_sha256: str | None
    report_path: str | None
    report_sha256: str | None
    publication_preflight: str
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "canary_dvd_id": self.canary_dvd_id,
            "source_media_path": self.source_media_path,
            "destination_ko_path": self.destination_ko_path,
            "destination_exists": self.destination_exists,
            "clean_path": self.clean_path,
            "clean_sha256": self.clean_sha256,
            "report_path": self.report_path,
            "report_sha256": self.report_sha256,
            "publication_preflight": self.publication_preflight,
            "reason": self.reason,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _canonical_provenance(value: Mapping[str, object]) -> str:
    if not isinstance(value, Mapping):
        raise Stage12RolloutValidationError(
            "transition provenance must be a mapping"
        )
    try:
        return json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, UnicodeError) as error:
        raise Stage12RolloutValidationError(
            "transition provenance is not canonical JSON"
        ) from error


def _validated_dvd_id(value: object) -> str:
    if type(value) is not str or not value:
        raise Stage12RolloutValidationError(
            "dvd_id must be a non-empty canonical string"
        )
    try:
        canonical = canonical_dvd_id(value)
    except (TypeError, ValueError):
        canonical = None
    if canonical != value:
        raise Stage12RolloutValidationError(
            "dvd_id is not an exact canonical identity"
        )
    return value


def _validated_sha(value: object, *, field_name: str) -> str:
    if (
        type(value) is not str
        or re.fullmatch(r"[0-9a-f]{64}", value) is None
    ):
        raise Stage12RolloutValidationError(
            field_name + " must be a lowercase SHA-256 digest"
        )
    return value


def _validated_metadata_path(value: object, *, field_name: str) -> str:
    if type(value) is not str or not value:
        raise Stage12RolloutValidationError(
            field_name + " must be a non-empty path string"
        )
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise Stage12RolloutValidationError(
            field_name + " must be an absolute path without '..'"
        )
    if any(
        ord(character) < 32 or ord(character) == 127
        for character in value
    ):
        raise Stage12RolloutValidationError(
            field_name + " contains a control character"
        )
    return str(path)


def _validated_destination_relative(value: object) -> str:
    if type(value) is not str or not value:
        raise Stage12RolloutValidationError(
            "destination_relative must be a non-empty relative path"
        )
    path = Path(value)
    if (
        path.is_absolute()
        or ".." in path.parts
        or any(part in {"", "."} for part in path.parts)
    ):
        raise Stage12RolloutValidationError(
            "destination_relative must be a safe relative path"
        )
    if any(
        ord(character) < 32 or ord(character) == 127
        for character in value
    ):
        raise Stage12RolloutValidationError(
            "destination_relative contains a control character"
        )
    return path.as_posix()


def _canonical_video_for_state(
    dvd_id: str,
    media_path_identity: str,
) -> CanonicalVideoHolding:
    try:
        suffix = Path(media_path_identity).suffix
        video = validate_canonical_holding(
            {
                "dvd_id": dvd_id,
                "storage_root": "jav",
                "relative_path": media_path_identity,
                "parse_status": "MATCHED",
                "present": 1,
            },
            dvd_id,
        )
    except Exception as error:
        raise Stage12RolloutValidationError(
            "stored media identity is not canonical"
        ) from error
    if not suffix or video.video_format != suffix[1:]:
        raise Stage12RolloutValidationError(
            "stored media identity has an invalid video suffix"
        )
    return video


def _validated_inventory_record(
    record: Stage12HoldingInventoryRecord,
) -> Stage12HoldingInventoryRecord:
    if not isinstance(record, Stage12HoldingInventoryRecord):
        raise Stage12RolloutValidationError(
            "inventory report contains an invalid record"
        )
    dvd_id = _validated_dvd_id(record.dvd_id)
    if (
        record.holding_identity is None
        or record.media_path_identity is None
        or record.holding_id is None
        or record.source_size_bytes is None
        or record.source_mtime_ns is None
    ):
        raise Stage12RolloutIdentityError(
            "inventory record lacks required canonical source identity"
        )
    if record.holding_identity != "jav:" + record.media_path_identity:
        raise Stage12RolloutIdentityError(
            "inventory holding identity is detached from media identity"
        )
    _canonical_video_for_state(dvd_id, record.media_path_identity)
    return record


def _initial_status_for(record: Stage12HoldingInventoryRecord) -> str:
    try:
        return _INITIAL_STATUS[record.eligibility]
    except KeyError as error:
        raise Stage12RolloutValidationError(
            "inventory eligibility has no initial rollout status"
        ) from error


def _state_from_row(row: sqlite3.Row) -> Stage12RolloutState:
    values = dict(row)
    return Stage12RolloutState(**values)


class Stage12RolloutStateStore:
    """SQLite-backed Stage12 title state with atomic audited transitions."""

    def __init__(
        self,
        state_path: str | Path,
        *,
        writer_lock_path: str | Path | None = None,
    ):
        path = Path(state_path).expanduser()
        if not path.is_absolute() or path == Path("/") or ".." in path.parts:
            raise Stage12RolloutValidationError(
                "state_path must be an absolute non-root path"
            )
        if path.exists() and path.is_symlink():
            raise Stage12RolloutValidationError(
                "state_path must not be a symlink"
            )
        self.state_path = path
        self.writer_lock_path = Path(
            writer_lock_path
            or str(path) + ".lock"
        )
        if (
            not self.writer_lock_path.is_absolute()
            or ".." in self.writer_lock_path.parts
        ):
            raise Stage12RolloutValidationError(
                "writer_lock_path must be an absolute safe path"
            )

    def _connect(self) -> sqlite3.Connection:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.state_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.executescript(_STATE_SCHEMA)
        connection.commit()
        return connection

    @contextmanager
    def _transaction(self):
        self.writer_lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.writer_lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _get_in_transaction(
        self,
        connection: sqlite3.Connection,
        dvd_id: str,
    ) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT * FROM stage12_rollout_titles WHERE dvd_id = ?",
            (dvd_id,),
        ).fetchone()

    @staticmethod
    def _assert_identity_matches(
        row: sqlite3.Row,
        record: Stage12HoldingInventoryRecord,
    ) -> None:
        for field_name in (
            "holding_identity",
            "media_path_identity",
            "existing_ko",
            "eligibility",
            "inventory_reason",
            "source_size_bytes",
            "source_mtime_ns",
        ):
            expected = (
                record.reason
                if field_name == "inventory_reason"
                else getattr(record, field_name)
            )
            if row[field_name] != expected:
                raise Stage12RolloutIdentityError(
                    "stored state is detached from current inventory: "
                    + field_name
                )

    @staticmethod
    def _assert_reinitialization_compatible(
        row: sqlite3.Row,
        desired_status: str,
    ) -> None:
        current_status = row["status"]
        if current_status == desired_status:
            return
        if desired_status == STATE_PENDING and current_status in {
            STATE_RUNNING,
            STATE_GENERATED,
            STATE_PUBLISHED,
            STATE_FAILED_RETRYABLE,
            STATE_FAILED_TERMINAL,
        }:
            return
        raise Stage12RolloutIdentityError(
            "reinitialization would change a durable rollout decision"
        )

    def initialize_from_inventory(
        self,
        report: Stage12HoldingsInventoryReport,
    ) -> dict[str, int]:
        if not isinstance(report, Stage12HoldingsInventoryReport):
            raise Stage12RolloutValidationError(
                "inventory report has an invalid type"
            )
        records = tuple(
            _validated_inventory_record(record)
            for record in report.records
        )
        seen: set[str] = set()
        for record in records:
            if record.dvd_id in seen:
                raise Stage12RolloutIdentityError(
                    "inventory contains duplicate DVD-ID state"
                )
            seen.add(record.dvd_id)

        now = _utc_now()
        with self._transaction() as connection:
            for record in sorted(records, key=lambda item: item.dvd_id):
                desired_status = _initial_status_for(record)
                existing = self._get_in_transaction(connection, record.dvd_id)
                if existing is not None:
                    self._assert_identity_matches(existing, record)
                    self._assert_reinitialization_compatible(
                        existing,
                        desired_status,
                    )
                    continue

                provenance = _canonical_provenance(
                    {
                        "operation": "INITIALIZE_FROM_INVENTORY",
                        "inventory_reason": record.reason,
                        "inventory_eligibility": record.eligibility,
                        "source": "Stage12HoldingsInventory",
                    }
                )
                connection.execute(
                    """
                    INSERT INTO stage12_rollout_titles(
                        dvd_id, status, holding_identity,
                        media_path_identity, existing_ko, eligibility,
                        inventory_reason, source_size_bytes,
                        source_mtime_ns, artifact_path, artifact_sha256,
                        report_path, report_sha256, destination_relative,
                        created_at, updated_at, transition_sequence,
                        last_transition_reason,
                        last_transition_provenance_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL,
                              NULL, NULL, NULL, ?, ?, 1, ?, ?)
                    """,
                    (
                        record.dvd_id,
                        desired_status,
                        record.holding_identity,
                        record.media_path_identity,
                        record.existing_ko,
                        record.eligibility,
                        record.reason,
                        record.source_size_bytes,
                        record.source_mtime_ns,
                        now,
                        now,
                        "INITIALIZE_FROM_INVENTORY",
                        provenance,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO stage12_rollout_events(
                        dvd_id, from_status, to_status,
                        transition_sequence, transitioned_at,
                        reason, provenance_json
                    ) VALUES (?, NULL, ?, 1, ?, ?, ?)
                    """,
                    (
                        record.dvd_id,
                        desired_status,
                        now,
                        "INITIALIZE_FROM_INVENTORY",
                        provenance,
                    ),
                )

        return self.status_counts()

    def status_counts(self) -> dict[str, int]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM stage12_rollout_titles
                GROUP BY status
                """
            ).fetchall()
            counts = {status: 0 for status in STATE_STATUSES}
            for row in rows:
                if row["status"] not in counts:
                    raise Stage12RolloutValidationError(
                        "state store contains an unknown status"
                    )
                counts[row["status"]] = int(row["count"])
            return counts
        finally:
            connection.close()

    def get(self, dvd_id: str) -> Stage12RolloutState:
        dvd_id = _validated_dvd_id(dvd_id)
        connection = self._connect()
        try:
            row = self._get_in_transaction(connection, dvd_id)
            if row is None:
                raise Stage12RolloutValidationError(
                    "rollout state title does not exist"
                )
            return _state_from_row(row)
        finally:
            connection.close()

    def list_states(self) -> tuple[Stage12RolloutState, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM stage12_rollout_titles ORDER BY dvd_id"
            ).fetchall()
            return tuple(_state_from_row(row) for row in rows)
        finally:
            connection.close()

    def transition(
        self,
        dvd_id: str,
        to_status: str,
        *,
        reason: str,
        provenance: Mapping[str, object],
        expected_from: str | None = None,
        artifact_path: str | None = None,
        artifact_sha256: str | None = None,
        report_path: str | None = None,
        report_sha256: str | None = None,
        destination_relative: str | None = None,
    ) -> Stage12RolloutState:
        dvd_id = _validated_dvd_id(dvd_id)
        if to_status not in STATE_STATUSES:
            raise Stage12InvalidTransitionError(
                "unknown target rollout status"
            )
        if type(reason) is not str or not reason:
            raise Stage12RolloutValidationError(
                "transition reason must be non-empty"
            )
        provenance_json = _canonical_provenance(provenance)
        with self._transaction() as connection:
            row = self._get_in_transaction(connection, dvd_id)
            if row is None:
                raise Stage12RolloutValidationError(
                    "cannot transition a missing rollout state"
                )
            current_status = row["status"]
            if expected_from is not None and expected_from != current_status:
                raise Stage12InvalidTransitionError(
                    "transition source status does not match"
                )
            if to_status not in _ALLOWED_TRANSITIONS[current_status]:
                raise Stage12InvalidTransitionError(
                    current_status + " cannot transition to " + to_status
                )
            if (
                current_status == STATE_RUNNING
                and to_status == STATE_PENDING
                and reason != "CRASH_RECOVERY"
            ):
                raise Stage12InvalidTransitionError(
                    "RUNNING to PENDING requires crash recovery"
                )

            metadata = {
                "artifact_path": row["artifact_path"],
                "artifact_sha256": row["artifact_sha256"],
                "report_path": row["report_path"],
                "report_sha256": row["report_sha256"],
                "destination_relative": row["destination_relative"],
            }
            supplied = {
                "artifact_path": artifact_path,
                "artifact_sha256": artifact_sha256,
                "report_path": report_path,
                "report_sha256": report_sha256,
                "destination_relative": destination_relative,
            }
            for field_name, value in supplied.items():
                if value is None:
                    continue
                if field_name.endswith("sha256"):
                    value = _validated_sha(value, field_name=field_name)
                elif field_name.endswith("path"):
                    value = _validated_metadata_path(value, field_name=field_name)
                elif field_name == "destination_relative":
                    value = _validated_destination_relative(value)
                if (
                    metadata[field_name] is not None
                    and metadata[field_name] != value
                ):
                    raise Stage12RolloutIdentityError(
                        field_name + " cannot be replaced after recording"
                    )
                metadata[field_name] = value

            if to_status in {STATE_GENERATED, STATE_PUBLISHED}:
                for field_name in (
                    "artifact_path",
                    "artifact_sha256",
                    "report_path",
                    "report_sha256",
                ):
                    if metadata[field_name] is None:
                        raise Stage12RolloutValidationError(
                            to_status
                            + " requires complete artifact/report provenance"
                        )
            if to_status == STATE_PUBLISHED:
                if metadata["destination_relative"] is None:
                    raise Stage12RolloutValidationError(
                        "PUBLISHED requires destination identity"
                    )
                video = _canonical_video_for_state(
                    dvd_id,
                    row["media_path_identity"],
                )
                if metadata["destination_relative"] != derive_target_ko_relative(video):
                    raise Stage12RolloutIdentityError(
                        "PUBLISHED destination is not canonical"
                    )
                if (
                    provenance.get("publication_performed") is not True
                    or provenance.get("atomic_install") is not True
                    or provenance.get("destination_verified") is not True
                    or provenance.get("destination_relative")
                    != metadata["destination_relative"]
                ):
                    raise Stage12RolloutValidationError(
                        "PUBLISHED requires verified atomic publication provenance"
                    )
                destination_sha256 = provenance.get("destination_sha256")
                _validated_sha(
                    destination_sha256,
                    field_name="destination_sha256",
                )
                if destination_sha256 != metadata["artifact_sha256"]:
                    raise Stage12RolloutIdentityError(
                        "published destination SHA differs from CLEAN artifact"
                    )

            now = _utc_now()
            sequence = int(row["transition_sequence"]) + 1
            cursor = connection.execute(
                """
                UPDATE stage12_rollout_titles
                SET status = ?, artifact_path = ?, artifact_sha256 = ?,
                    report_path = ?, report_sha256 = ?,
                    destination_relative = ?, updated_at = ?,
                    transition_sequence = ?, last_transition_reason = ?,
                    last_transition_provenance_json = ?
                WHERE dvd_id = ? AND status = ?
                """,
                (
                    to_status,
                    metadata["artifact_path"],
                    metadata["artifact_sha256"],
                    metadata["report_path"],
                    metadata["report_sha256"],
                    metadata["destination_relative"],
                    now,
                    sequence,
                    reason,
                    provenance_json,
                    dvd_id,
                    current_status,
                ),
            )
            if cursor.rowcount != 1:
                raise Stage12InvalidTransitionError(
                    "rollout state changed during transition"
                )
            connection.execute(
                """
                INSERT INTO stage12_rollout_events(
                    dvd_id, from_status, to_status,
                    transition_sequence, transitioned_at,
                    reason, provenance_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dvd_id,
                    current_status,
                    to_status,
                    sequence,
                    now,
                    reason,
                    provenance_json,
                ),
            )
            updated = self._get_in_transaction(connection, dvd_id)
            return _state_from_row(updated)

    def recover_running(self, dvd_id: str) -> Stage12RolloutState:
        return self.transition(
            dvd_id,
            STATE_PENDING,
            expected_from=STATE_RUNNING,
            reason="CRASH_RECOVERY",
            provenance={
                "operation": "RECOVER_RUNNING",
                "from": STATE_RUNNING,
                "to": STATE_PENDING,
            },
        )


def _safe_artifact_root(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute() or path == Path("/") or ".." in path.parts:
        raise Stage12PublicationPreflightError(
            "artifact_root must be an absolute non-root path"
        )
    if Path("/var/tmp") == path or Path("/var/tmp") in path.parents:
        raise Stage12PublicationPreflightError(
            "calibration artifacts under /var/tmp are forbidden"
        )
    if path.exists() and path.is_symlink():
        raise Stage12PublicationPreflightError(
            "artifact_root must not be a symlink"
        )
    return path


def _artifact_path(root: Path, dvd_id: str, filename: str) -> Path:
    directory = root / dvd_id
    path = directory / filename
    if path.parent != directory or path.name != filename:
        raise Stage12PublicationPreflightError(
            "artifact path is not bounded to the title directory"
        )
    return path


def _read_local_regular(path: Path, *, max_bytes: int) -> bytes:
    try:
        before = path.stat()
        info = path.lstat()
    except OSError as error:
        raise Stage12PublicationPreflightError(
            "artifact file cannot be inspected"
        ) from error
    if not stat.S_ISREG(info.st_mode) or path.is_symlink():
        raise Stage12PublicationPreflightError(
            "artifact file is not a regular non-symlink file"
        )
    if before.st_size <= 0 or before.st_size > max_bytes:
        raise Stage12PublicationPreflightError(
            "artifact file is outside its bounded size"
        )
    try:
        payload = path.read_bytes()
        after = path.stat()
    except OSError as error:
        raise Stage12PublicationPreflightError(
            "artifact file cannot be read"
        ) from error
    if (
        len(payload) != before.st_size
        or after.st_size != before.st_size
        or after.st_mtime_ns != before.st_mtime_ns
    ):
        raise Stage12PublicationPreflightError(
            "artifact file changed during read"
        )
    return payload


def _record_video(record: Stage12HoldingInventoryRecord) -> CanonicalVideoHolding:
    if record.dvd_id is None or record.media_path_identity is None:
        raise Stage12PublicationPreflightError(
            "canary record lacks source identity"
        )
    return _canonical_video_for_state(
        record.dvd_id,
        record.media_path_identity,
    )


def _artifact_bundle_paths(
    artifact_root: Path,
    dvd_id: str,
) -> tuple[Path, Path, Path]:
    return (
        _artifact_path(artifact_root, dvd_id, BASELINE_ASR_FILENAME),
        _artifact_path(artifact_root, dvd_id, CLEAN_SRT_FILENAME),
        _artifact_path(artifact_root, dvd_id, MECHANICAL_REPORT_FILENAME),
    )


def _path_presence(path: Path) -> str:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return "ABSENT"
    except OSError:
        return "INVALID"
    if not stat.S_ISREG(info.st_mode) or path.is_symlink():
        return "INVALID"
    return "PRESENT"


def _preflight_artifact_bundle(
    record: Stage12HoldingInventoryRecord,
    artifact_root: Path,
) -> tuple[Path, Path, str, str]:
    baseline_path, clean_path, report_path = _artifact_bundle_paths(
        artifact_root,
        record.dvd_id,
    )
    presence = tuple(
        _path_presence(path)
        for path in (baseline_path, clean_path, report_path)
    )
    if presence != ("PRESENT", "PRESENT", "PRESENT"):
        raise Stage12PublicationPreflightError(
            "artifact bundle is incomplete or unsafe"
        )

    clean_raw = _read_local_regular(
        clean_path,
        max_bytes=MAX_SUBTITLE_BYTES,
    )
    clean_sha = hashlib.sha256(clean_raw).hexdigest()
    try:
        document = parse_subtitle_bytes(clean_raw, "srt")
        canonical = generate_korean_srt(document.cues)
    except SubtitleTextError as error:
        raise Stage12PublicationPreflightError(
            "CLEAN SRT is malformed"
        ) from error
    if canonical.payload != clean_raw or canonical.sha256 != clean_sha:
        raise Stage12PublicationPreflightError(
            "CLEAN SRT is not canonical"
        )

    report_raw = _read_local_regular(
        report_path,
        max_bytes=MAX_STAGE11_REPORT_BYTES,
    )
    report_sha = hashlib.sha256(report_raw).hexdigest()
    try:
        report = _parse_report(report_raw)
    except Exception as error:
        raise Stage12PublicationPreflightError(
            "mechanical report is invalid"
        ) from error
    if (
        report["title"] != record.dvd_id
        or report["clean_artifact_path"] != str(clean_path)
        or report["clean_sha256"] != clean_sha
        or report["baseline_artifact_path"] != str(baseline_path)
        or report["publication_performed"] is not False
    ):
        raise Stage12PublicationPreflightError(
            "mechanical report is detached from CLEAN artifact"
        )

    quality_counts = report["source_quality_counts"]
    if (
        type(quality_counts) is not dict
        or set(quality_counts)
        != {"KEEP", "REQUIRE_SECOND_EVIDENCE", "OMIT"}
        or any(
            type(value) is not int or value < 0
            for value in quality_counts.values()
        )
        or sum(quality_counts.values()) <= 0
    ):
        raise Stage12PublicationPreflightError(
            "mechanical report source-quality counts are invalid"
        )
    for field_name in ("targeted_source_count", "targeted_window_count"):
        value = report[field_name]
        if type(value) is not int or value < 0:
            raise Stage12PublicationPreflightError(
                "mechanical report " + field_name + " is invalid"
            )
    targeted_reused = (
        None
        if report["targeted_reused"] == "not_applicable"
        else report["targeted_reused"]
    )
    try:
        _validate_existing_completion(
            report_path,
            clean_path,
            baseline_path,
            title=record.dvd_id,
            baseline_sha256=report["baseline_sha256"],
            baseline_reused=report["baseline_reused"],
            source_quality_counts=quality_counts,
            targeted_reused=targeted_reused,
            targeted_source_count=report["targeted_source_count"],
            targeted_window_count=report["targeted_window_count"],
        )
    except Exception as error:
        raise Stage12PublicationPreflightError(
            "mechanical report completion contract is invalid"
        ) from error

    baseline_raw = _read_local_regular(
        baseline_path,
        max_bytes=MAX_ASR_ARTIFACT_BYTES,
    )
    baseline_sha = hashlib.sha256(baseline_raw).hexdigest()
    if report["baseline_sha256"] != baseline_sha:
        raise Stage12PublicationPreflightError(
            "mechanical report is detached from baseline artifact"
        )
    try:
        baseline_result = parse_asr_result_bytes(baseline_raw)
        video = _record_video(record)
        snapshot = ASRSourceSnapshot.from_holding(
            video,
            source_size=record.source_size_bytes,
            source_mtime_ns=record.source_mtime_ns,
        )
        require_matching_asr_source(baseline_result, snapshot)
    except Exception as error:
        raise Stage12PublicationPreflightError(
            "baseline artifact source snapshot is detached"
        ) from error

    return clean_path, report_path, clean_sha, report_sha


def _preflight_record(
    record: Stage12HoldingInventoryRecord,
    *,
    artifact_root: Path,
    nas_filesystem: object,
) -> Stage12PublicationPreflight:
    video = _record_video(record)
    source_path = record.media_path_identity
    destination_path = derive_target_ko_relative(video)
    clean_path = _artifact_path(artifact_root, record.dvd_id, CLEAN_SRT_FILENAME)
    report_path = _artifact_path(
        artifact_root,
        record.dvd_id,
        MECHANICAL_REPORT_FILENAME,
    )
    try:
        clean_path, report_path, clean_sha, report_sha = _preflight_artifact_bundle(
            record,
            artifact_root,
        )
    except Stage12PublicationPreflightError as error:
        return Stage12PublicationPreflight(
            canary_dvd_id=record.dvd_id,
            source_media_path=source_path,
            destination_ko_path=destination_path,
            destination_exists=None,
            clean_path=str(clean_path),
            clean_sha256=None,
            report_path=str(report_path),
            report_sha256=None,
            publication_preflight=PUBLICATION_BLOCKED_INVALID_ARTIFACT,
            reason=type(error).__name__,
        )

    lstat = getattr(nas_filesystem, "lstat", None)
    if not callable(lstat):
        raise Stage12PublicationPreflightError(
            "NAS preflight filesystem lacks read-only lstat"
        )
    try:
        source_stat = lstat(source_path)
    except FileNotFoundError:
        return Stage12PublicationPreflight(
            canary_dvd_id=record.dvd_id,
            source_media_path=source_path,
            destination_ko_path=destination_path,
            destination_exists=None,
            clean_path=str(clean_path),
            clean_sha256=clean_sha,
            report_path=str(report_path),
            report_sha256=report_sha,
            publication_preflight=PUBLICATION_BLOCKED_SOURCE_DRIFT,
            reason="SOURCE_MEDIA_MISSING",
        )
    except OSError:
        return Stage12PublicationPreflight(
            canary_dvd_id=record.dvd_id,
            source_media_path=source_path,
            destination_ko_path=destination_path,
            destination_exists=None,
            clean_path=str(clean_path),
            clean_sha256=clean_sha,
            report_path=str(report_path),
            report_sha256=report_sha,
            publication_preflight=PUBLICATION_UNRESOLVED,
            reason="SOURCE_MEDIA_READ_FAILED",
        )

    if (
        not stat.S_ISREG(int(getattr(source_stat, "st_mode", 0)))
        or int(getattr(source_stat, "st_size", -1)) != record.source_size_bytes
        or int(getattr(source_stat, "st_mtime_ns", -1)) != record.source_mtime_ns
    ):
        return Stage12PublicationPreflight(
            canary_dvd_id=record.dvd_id,
            source_media_path=source_path,
            destination_ko_path=destination_path,
            destination_exists=None,
            clean_path=str(clean_path),
            clean_sha256=clean_sha,
            report_path=str(report_path),
            report_sha256=report_sha,
            publication_preflight=PUBLICATION_BLOCKED_SOURCE_DRIFT,
            reason="SOURCE_SNAPSHOT_MISMATCH",
        )

    try:
        lstat(destination_path)
    except FileNotFoundError:
        return Stage12PublicationPreflight(
            canary_dvd_id=record.dvd_id,
            source_media_path=source_path,
            destination_ko_path=destination_path,
            destination_exists=False,
            clean_path=str(clean_path),
            clean_sha256=clean_sha,
            report_path=str(report_path),
            report_sha256=report_sha,
            publication_preflight=PUBLICATION_READY,
            reason="VALID_ARTIFACT_SOURCE_AND_EMPTY_DESTINATION",
        )
    except OSError:
        return Stage12PublicationPreflight(
            canary_dvd_id=record.dvd_id,
            source_media_path=source_path,
            destination_ko_path=destination_path,
            destination_exists=None,
            clean_path=str(clean_path),
            clean_sha256=clean_sha,
            report_path=str(report_path),
            report_sha256=report_sha,
            publication_preflight=PUBLICATION_UNRESOLVED,
            reason="DESTINATION_READ_FAILED",
        )

    return Stage12PublicationPreflight(
        canary_dvd_id=record.dvd_id,
        source_media_path=source_path,
        destination_ko_path=destination_path,
        destination_exists=True,
        clean_path=str(clean_path),
        clean_sha256=clean_sha,
        report_path=str(report_path),
        report_sha256=report_sha,
        publication_preflight=PUBLICATION_BLOCKED_EXISTING_KO,
        reason="CANONICAL_DESTINATION_EXISTS",
    )


def _empty_preflight(reason: str) -> Stage12PublicationPreflight:
    return Stage12PublicationPreflight(
        canary_dvd_id=None,
        source_media_path=None,
        destination_ko_path=None,
        destination_exists=None,
        clean_path=None,
        clean_sha256=None,
        report_path=None,
        report_sha256=None,
        publication_preflight=PUBLICATION_UNRESOLVED,
        reason=reason,
    )


def select_publication_canary(
    report: Stage12HoldingsInventoryReport,
    *,
    artifact_root: str | Path,
    nas_filesystem: object,
    operator_selected_dvd_id: str | None = None,
) -> Stage12PublicationPreflight:
    """Select the first artifact-backed eligible title deterministically."""

    if not isinstance(report, Stage12HoldingsInventoryReport):
        raise Stage12PublicationPreflightError(
            "inventory report has an invalid type"
        )
    root = _safe_artifact_root(artifact_root)
    eligible = tuple(
        record
        for record in sorted(
            report.records,
            key=lambda item: (item.dvd_id or "", item.media_path_identity or ""),
        )
        if (
            record.eligibility == ELIGIBLE_NEEDS_KO
            and record.existing_ko == EXISTING_KO_ABSENT
        )
    )
    if operator_selected_dvd_id is not None:
        selected_id = _validated_dvd_id(operator_selected_dvd_id)
        eligible = tuple(
            record for record in eligible if record.dvd_id == selected_id
        )
        if not eligible:
            return _empty_preflight("OPERATOR_SELECTED_TITLE_NOT_ELIGIBLE")

    saw_artifact = False
    for record in eligible:
        _validated_inventory_record(record)
        baseline_path, clean_path, report_path = _artifact_bundle_paths(
            root,
            record.dvd_id,
        )
        presence = tuple(
            _path_presence(path)
            for path in (baseline_path, clean_path, report_path)
        )
        if presence == ("ABSENT", "ABSENT", "ABSENT"):
            continue
        saw_artifact = True
        return _preflight_record(
            record,
            artifact_root=root,
            nas_filesystem=nas_filesystem,
        )

    if saw_artifact:
        return _empty_preflight("NO_VALID_ARTIFACT_BACKED_CANDIDATE")
    return _empty_preflight("NO_EXISTING_STAGE11_ARTIFACT_FOR_ELIGIBLE_TITLE")


def build_nas_preflight_filesystem(
    *,
    nas_host: str,
    nas_user: str,
    nas_key: str,
    nas_known_hosts: str,
    nas_library_root: str,
) -> RemoteJAVFilesystem:
    ssh = CompletionSSH(
        host=nas_host,
        user=nas_user,
        key=nas_key,
        known_hosts=nas_known_hosts,
        downloads_root="",
        library_root=nas_library_root,
    )
    return RemoteJAVFilesystem(
        ssh,
        library_root=nas_library_root,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Materialize Stage12 state and run publication preflight"
    )
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--state-path", required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--nas-host", required=True)
    parser.add_argument("--nas-user", required=True)
    parser.add_argument("--nas-key", required=True)
    parser.add_argument("--nas-known-hosts", required=True)
    parser.add_argument("--nas-library-root", required=True)
    args = parser.parse_args(argv)

    try:
        subtitle_reader = build_subtitle_ssh_reader(
            nas_host=args.nas_host,
            nas_user=args.nas_user,
            nas_key=args.nas_key,
            nas_known_hosts=args.nas_known_hosts,
            nas_library_root=args.nas_library_root,
        )
        inventory = Stage12HoldingsInventory(
            db_path=args.db_path,
            subtitle_reader=subtitle_reader,
        ).run()
        store = Stage12RolloutStateStore(args.state_path)
        counts = store.initialize_from_inventory(inventory)
        nas_filesystem = build_nas_preflight_filesystem(
            nas_host=args.nas_host,
            nas_user=args.nas_user,
            nas_key=args.nas_key,
            nas_known_hosts=args.nas_known_hosts,
            nas_library_root=args.nas_library_root,
        )
        preflight = select_publication_canary(
            inventory,
            artifact_root=args.artifact_root,
            nas_filesystem=nas_filesystem,
        )
    except (Stage12InventoryError, Stage12RolloutError) as error:
        print("STAGE12_CP2=FAIL")
        print("REASON=" + type(error).__name__)
        return 1

    print("STAGE12_CP2=PASS")
    print("TOTAL_STATE_RECORDS=" + str(sum(counts.values())))
    for status in STATE_STATUSES:
        print(status + "=" + str(counts[status]))
    for key, value in preflight.to_dict().items():
        if isinstance(value, bool):
            value = int(value)
        print(key.upper() + "=" + str(value))
    return 0


__all__ = [
    "PUBLICATION_BLOCKED_EXISTING_KO",
    "PUBLICATION_BLOCKED_INVALID_ARTIFACT",
    "PUBLICATION_BLOCKED_SOURCE_DRIFT",
    "PUBLICATION_READY",
    "PUBLICATION_UNRESOLVED",
    "STATE_FAILED_RETRYABLE",
    "STATE_FAILED_TERMINAL",
    "STATE_GENERATED",
    "STATE_PENDING",
    "STATE_PUBLISHED",
    "STATE_RUNNING",
    "STATE_SKIPPED_EXISTING_KO",
    "STATE_STATUSES",
    "STATE_UNRESOLVED",
    "Stage12InvalidTransitionError",
    "Stage12PublicationPreflight",
    "Stage12PublicationPreflightError",
    "Stage12RolloutError",
    "Stage12RolloutIdentityError",
    "Stage12RolloutState",
    "Stage12RolloutStateStore",
    "Stage12RolloutValidationError",
    "build_nas_preflight_filesystem",
    "select_publication_canary",
]


if __name__ == "__main__":
    raise SystemExit(main())
