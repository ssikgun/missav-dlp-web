"""Read-only Stage12 subtitle rollout status for the Downloader UI."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import time


DEFAULT_STATE_PATH = Path(
    os.environ.get(
        "TEDDY_SUBTITLE_STATE_PATH",
        "/opt/missav-dlp-web/discovery/stage12-rollout-state.sqlite3",
    )
)
DEFAULT_HEARTBEAT_PATH = Path(
    os.environ.get(
        "TEDDY_SUBTITLE_HEARTBEAT_PATH",
        "/opt/missav-dlp-web/discovery/stage12-runtime/status.json",
    )
)
HEARTBEAT_FRESH_SECONDS = 120

_STATUSES = (
    "PENDING",
    "RUNNING",
    "GENERATED",
    "PUBLISHED",
    "FAILED_RETRYABLE",
    "FAILED_TERMINAL",
    "UNRESOLVED",
    "SKIPPED_EXISTING_KO",
)
_ACTIVE_STATUSES = ("RUNNING", "GENERATED")


class SubtitleStatusError(RuntimeError):
    pass


def _parse_timestamp(value):
    if type(value) is not str or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _read_heartbeat(path, *, now_epoch):
    heartbeat_path = Path(path)

    if not heartbeat_path.is_file():
        return {
            "present": False,
            "fresh": False,
            "age_seconds": None,
            "payload": None,
        }

    try:
        payload = json.loads(
            heartbeat_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError, UnicodeError):
        return {
            "present": True,
            "fresh": False,
            "age_seconds": None,
            "payload": None,
        }

    if not isinstance(payload, dict):
        return {
            "present": True,
            "fresh": False,
            "age_seconds": None,
            "payload": None,
        }

    updated = _parse_timestamp(payload.get("updated_at"))
    if updated is None:
        return {
            "present": True,
            "fresh": False,
            "age_seconds": None,
            "payload": payload,
        }

    age = max(
        0.0,
        float(now_epoch) - updated.timestamp(),
    )

    return {
        "present": True,
        "fresh": age <= HEARTBEAT_FRESH_SECONDS,
        "age_seconds": round(age, 1),
        "payload": payload,
    }


def build_status_snapshot(
    *,
    state_path=DEFAULT_STATE_PATH,
    heartbeat_path=DEFAULT_HEARTBEAT_PATH,
    now_epoch=None,
):
    now_epoch = (
        time.time()
        if now_epoch is None
        else float(now_epoch)
    )

    state_path = Path(state_path)

    if not state_path.is_file():
        raise SubtitleStatusError(
            "Stage12 rollout state database is unavailable"
        )

    try:
        connection = sqlite3.connect(
            f"file:{state_path}?mode=ro",
            uri=True,
        )
        connection.row_factory = sqlite3.Row
    except sqlite3.Error as error:
        raise SubtitleStatusError(
            "Stage12 rollout state database cannot be opened"
        ) from error

    try:
        counts = {status: 0 for status in _STATUSES}

        for row in connection.execute("""
            SELECT status, COUNT(*) AS count
            FROM stage12_rollout_titles
            GROUP BY status
        """):
            status = str(row["status"])
            if status in counts:
                counts[status] = int(row["count"])

        active_titles = [
            {
                "dvd_id": str(row["dvd_id"]),
                "status": str(row["status"]),
            }
            for row in connection.execute("""
                SELECT dvd_id, status
                FROM stage12_rollout_titles
                WHERE status IN ('RUNNING', 'GENERATED')
                ORDER BY dvd_id
            """)
        ]

        latest_event = connection.execute("""
            SELECT dvd_id, to_status, transitioned_at
            FROM stage12_rollout_events
            ORDER BY event_id DESC
            LIMIT 1
        """).fetchone()
    except sqlite3.Error as error:
        raise SubtitleStatusError(
            "Stage12 rollout status query failed"
        ) from error
    finally:
        connection.close()

    heartbeat = _read_heartbeat(
        heartbeat_path,
        now_epoch=now_epoch,
    )
    heartbeat_payload = heartbeat["payload"] or {}

    runner_state = str(
        heartbeat_payload.get("runner_state") or ""
    ).upper()

    if heartbeat["fresh"] and runner_state == "RUNNING":
        overall_status = "running"
    elif active_titles and not heartbeat["fresh"]:
        overall_status = "stale"
    elif heartbeat["fresh"] and runner_state == "ERROR":
        overall_status = "error"
    elif (
        counts["FAILED_RETRYABLE"] > 0
        or counts["FAILED_TERMINAL"] > 0
    ):
        overall_status = "attention"
    else:
        overall_status = "idle"

    current_dvd_id = None

    if heartbeat["fresh"]:
        value = heartbeat_payload.get("current_dvd_id")
        if type(value) is str and value:
            current_dvd_id = value

    if current_dvd_id is None and active_titles:
        current_dvd_id = active_titles[0]["dvd_id"]

    progress = {
        "stage": None,
        "part_index": None,
        "part_count": None,
    }

    if heartbeat["fresh"]:
        stage = heartbeat_payload.get("stage")
        part_index = heartbeat_payload.get("part_index")
        part_count = heartbeat_payload.get("part_count")

        if type(stage) is str and stage:
            progress["stage"] = stage
        if type(part_index) is int and part_index >= 0:
            progress["part_index"] = part_index
        if type(part_count) is int and part_count >= 0:
            progress["part_count"] = part_count

    last_transition = None

    if latest_event is not None:
        last_transition = {
            "dvd_id": latest_event["dvd_id"],
            "status": latest_event["to_status"],
            "transitioned_at": latest_event["transitioned_at"],
        }

    last_activity_at = (
        heartbeat_payload.get("updated_at")
        if heartbeat["fresh"]
        else (
            latest_event["transitioned_at"]
            if latest_event is not None
            else None
        )
    )

    return {
        "status": overall_status,
        "current_dvd_id": current_dvd_id,
        "progress": progress,
        "counts": counts,
        "remaining": counts["PENDING"],
        "completed": counts["PUBLISHED"],
        "retryable": counts["FAILED_RETRYABLE"],
        "failed_terminal": counts["FAILED_TERMINAL"],
        "unresolved": counts["UNRESOLVED"],
        "active_titles": active_titles,
        "last_activity_at": last_activity_at,
        "last_transition": last_transition,
        "heartbeat": {
            "present": heartbeat["present"],
            "fresh": heartbeat["fresh"],
            "age_seconds": heartbeat["age_seconds"],
        },
    }


def install_routes(app, jsonify):
    @app.route("/api/subtitles/status", methods=["GET"])
    def teddy_subtitle_status():
        try:
            return jsonify(build_status_snapshot())
        except SubtitleStatusError as error:
            return jsonify({
                "status": "unavailable",
                "message": str(error),
            }), 503

    print(
        "[Teddy] subtitle status API enabled",
        flush=True,
    )
