"""Read-only, per-title activity checks before permanent library deletion."""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
import sqlite3
import time

from teddy_discovery_ids import parse_dvd_id
from teddy_subtitle_status import (
    _ACTIVE_STATUSES,
    _STATUSES,
    _read_heartbeat,
)


IDLE = "IDLE"
ACTIVE_ORGANIZER = "ACTIVE_ORGANIZER"
ACTIVE_SUBTITLE = "ACTIVE_SUBTITLE"
ACTIVITY_STATE_UNAVAILABLE = "ACTIVITY_STATE_UNAVAILABLE"

# Source transition evidence: organizer_apply creates RUNNING, records PUBLISHED
# before source cleanup, and only then writes COMPLETED. FAILED is terminal.
_ORGANIZER_ACTIVE = frozenset({"RUNNING", "PUBLISHED"})
_ORGANIZER_TERMINAL = frozenset({"COMPLETED", "FAILED"})
_ORGANIZER_KNOWN = _ORGANIZER_ACTIVE | _ORGANIZER_TERMINAL
_SUBTITLE_ACTIVE = frozenset(_ACTIVE_STATUSES)
_SUBTITLE_KNOWN = frozenset(_STATUSES)
_HEARTBEAT_TERMINAL = frozenset({"COMPLETE", "ERROR"})


@dataclass(frozen=True)
class ActivityDecision:
    status: str
    kind: str | None = None


def _read_only_connection(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    uri = path.resolve().as_uri() + "?mode=ro"
    db = sqlite3.connect(uri, uri=True, timeout=2.0)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=2000")
    db.execute("PRAGMA query_only=ON")
    return db


class OrganizerActivitySource:
    """Reads only status rows for the requested DVD-ID."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path) if db_path else None

    def check(self, dvd_id: str) -> ActivityDecision:
        if self.db_path is None:
            return ActivityDecision(ACTIVITY_STATE_UNAVAILABLE, "organizer")
        try:
            with closing(_read_only_connection(self.db_path)) as db:
                rows = db.execute(
                    "SELECT status FROM organizer_jobs WHERE dvd_id=?",
                    (dvd_id,),
                ).fetchall()
        except (OSError, sqlite3.Error, ValueError):
            return ActivityDecision(ACTIVITY_STATE_UNAVAILABLE, "organizer")

        statuses = [row["status"] for row in rows]
        if any(not isinstance(status, str) or status not in _ORGANIZER_KNOWN
               for status in statuses):
            # Known recovery-incomplete values (e.g. CLEANUP_PENDING) are also
            # intentionally fail-closed until their source contract is handled.
            return ActivityDecision(ACTIVITY_STATE_UNAVAILABLE, "organizer")
        if any(status in _ORGANIZER_ACTIVE for status in statuses):
            return ActivityDecision(ACTIVE_ORGANIZER, "organizer")
        return ActivityDecision(IDLE)


class SubtitleActivitySource:
    """Combines durable per-title rollout state with the shared heartbeat parser."""

    def __init__(self, rollout_db_path: str | Path, heartbeat_path: str | Path,
                 *, now_epoch=None):
        self.rollout_db_path = Path(rollout_db_path) if rollout_db_path else None
        self.heartbeat_path = Path(heartbeat_path) if heartbeat_path else None
        self.now_epoch = now_epoch

    def check(self, dvd_id: str) -> ActivityDecision:
        if self.rollout_db_path is None or self.heartbeat_path is None:
            return ActivityDecision(ACTIVITY_STATE_UNAVAILABLE, "subtitle")
        try:
            with closing(_read_only_connection(self.rollout_db_path)) as db:
                rows = db.execute(
                    "SELECT status FROM stage12_rollout_titles WHERE dvd_id=?",
                    (dvd_id,),
                ).fetchall()
        except (OSError, sqlite3.Error, ValueError):
            return ActivityDecision(ACTIVITY_STATE_UNAVAILABLE, "subtitle")

        statuses = [row["status"] for row in rows]
        if any(not isinstance(status, str) or status not in _SUBTITLE_KNOWN
               for status in statuses):
            return ActivityDecision(ACTIVITY_STATE_UNAVAILABLE, "subtitle")
        if any(status in _SUBTITLE_ACTIVE for status in statuses):
            return ActivityDecision(ACTIVE_SUBTITLE, "subtitle")

        now = time.time() if self.now_epoch is None else float(self.now_epoch)
        try:
            if self.heartbeat_path.exists() and not self.heartbeat_path.is_file():
                return ActivityDecision(ACTIVITY_STATE_UNAVAILABLE, "subtitle")
            heartbeat = _read_heartbeat(self.heartbeat_path, now_epoch=now)
        except (OSError, ValueError, TypeError):
            return ActivityDecision(ACTIVITY_STATE_UNAVAILABLE, "subtitle")
        if not heartbeat["present"]:
            return ActivityDecision(IDLE)
        payload = heartbeat.get("payload")
        if not isinstance(payload, dict):
            return ActivityDecision(ACTIVITY_STATE_UNAVAILABLE, "subtitle")
        if heartbeat.get("age_seconds") is None:
            return ActivityDecision(ACTIVITY_STATE_UNAVAILABLE, "subtitle")
        if not heartbeat.get("fresh"):
            return ActivityDecision(IDLE)

        runner_state = payload.get("runner_state")
        if runner_state == "RUNNING":
            current_dvd_id = payload.get("current_dvd_id")
            if not isinstance(current_dvd_id, str) or not current_dvd_id:
                return ActivityDecision(ACTIVITY_STATE_UNAVAILABLE, "subtitle")
            if current_dvd_id == dvd_id:
                return ActivityDecision(ACTIVE_SUBTITLE, "subtitle")
            return ActivityDecision(IDLE)
        if runner_state in _HEARTBEAT_TERMINAL:
            return ActivityDecision(IDLE)
        return ActivityDecision(ACTIVITY_STATE_UNAVAILABLE, "subtitle")


class DeleteTargetActivityGuard:
    """Fail-closed read model; providers can be extended for future workflows."""

    def __init__(self, organizer: OrganizerActivitySource,
                 subtitle: SubtitleActivitySource):
        self.organizer = organizer
        self.subtitle = subtitle

    def check(self, dvd_id: str) -> ActivityDecision:
        parsed = parse_dvd_id(dvd_id) if isinstance(dvd_id, str) else None
        if parsed is None or parsed.dvd_id != dvd_id:
            return ActivityDecision(ACTIVITY_STATE_UNAVAILABLE)
        organizer = self.organizer.check(dvd_id)
        if organizer.status != IDLE:
            return organizer
        subtitle = self.subtitle.check(dvd_id)
        if subtitle.status != IDLE:
            return subtitle
        return ActivityDecision(IDLE)
