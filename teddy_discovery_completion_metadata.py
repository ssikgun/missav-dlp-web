from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
    timezone,
)
from pathlib import Path
import sqlite3

from teddy_discovery_completion import CompletionPlan
from teddy_discovery_held_backfill import (
    apply_held_collected_metadata,
)
from teddy_discovery_ids import parse_dvd_id
from teddy_discovery_organizer_apply import writer_transaction
from teddy_discovery_ownership import (
    has_canonical_present_holding,
)
from teddy_discovery_completion_metadata_docker import (
    collect_metadata_candidate_docker,
)


DEFAULT_METADATA_RECOVERY_MAX_ITEMS = 1
DEFAULT_METADATA_RECOVERY_STATE_NAME = (
    "teddy-discovery-completion-metadata.sqlite3"
)
METADATA_RECOVERY_BACKOFF_SECONDS = (
    15 * 60,
    60 * 60,
    4 * 60 * 60,
    24 * 60 * 60,
)


def default_metadata_recovery_state_path(
    db_path: str | Path,
) -> Path:
    database = (
        Path(db_path)
        .expanduser()
        .resolve()
    )

    return database.parent / (
        DEFAULT_METADATA_RECOVERY_STATE_NAME
    )


def _recovery_candidates(
    plans: list[CompletionPlan],
) -> list[CompletionPlan]:
    return [
        plan
        for plan in plans
        if (
            plan.planned_operation == "HOLD"
            and plan.collision_type == "METADATA_NOT_READY"
            and plan.dvd_id
            and plan.holding_count == 0
        )
    ]


def _empty_result(
    candidate_count: int,
) -> dict:
    return {
        "candidate_count": candidate_count,
        "attempted": 0,
        "recovered": 0,
        "not_found": 0,
        "skipped_ownership": 0,
        "backoff_skipped": 0,
        "failed": 0,
        "results": [],
    }


def _validate_max_items(
    max_items: int,
) -> None:
    if (
        type(max_items) is not int
        or max_items < 1
        or max_items > 50
    ):
        raise ValueError(
            "metadata recovery max_items "
            "must be 1..50"
        )


def _utc_now(
    value=None,
) -> datetime:
    if value is None:
        value = datetime.now(timezone.utc)

    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(
            str(value)
        )

    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
    ):
        raise ValueError(
            "metadata recovery time must be timezone-aware"
        )

    return parsed.astimezone(
        timezone.utc
    ).replace(microsecond=0)


def _format_time(
    value: datetime,
) -> str:
    return value.astimezone(
        timezone.utc
    ).replace(
        microsecond=0
    ).isoformat()


def _parse_state_time(
    value,
) -> datetime:
    parsed = datetime.fromisoformat(
        str(value)
    )

    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
    ):
        raise ValueError(
            "metadata retry time must be timezone-aware"
        )

    return parsed.astimezone(
        timezone.utc
    ).replace(microsecond=0)


def _state_connection(
    state_path: Path,
) -> sqlite3.Connection:
    state_path = (
        Path(state_path)
        .expanduser()
        .resolve()
    )
    state_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = sqlite3.connect(
        state_path,
        timeout=30,
    )
    connection.row_factory = sqlite3.Row
    connection.execute(
        "PRAGMA busy_timeout = 30000"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS metadata_recovery_retry (
            dvd_id TEXT PRIMARY KEY,
            failure_count INTEGER NOT NULL
                CHECK (failure_count >= 1),
            last_status TEXT NOT NULL
                CHECK (last_status IN ('NOT_FOUND', 'FAILED')),
            next_attempt_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.commit()
    return connection


def _load_retry_state(
    state_path: Path,
    dvd_ids: list[str],
) -> dict[str, dict]:
    if not dvd_ids:
        return {}

    connection = _state_connection(
        state_path
    )

    try:
        placeholders = ", ".join(
            "?" for _ in dvd_ids
        )
        rows = connection.execute(
            """
            SELECT dvd_id, failure_count,
                   last_status, next_attempt_at,
                   updated_at
            FROM metadata_recovery_retry
            WHERE dvd_id IN ("""
            + placeholders
            + ")",
            tuple(dvd_ids),
        ).fetchall()

        return {
            str(row["dvd_id"]): {
                "failure_count": int(
                    row["failure_count"]
                ),
                "last_status": str(
                    row["last_status"]
                ),
                "next_attempt_at": _parse_state_time(
                    row["next_attempt_at"]
                ),
                "updated_at": str(
                    row["updated_at"]
                ),
            }
            for row in rows
        }

    finally:
        connection.close()


def _backoff_seconds(
    failure_count: int,
) -> int:
    index = min(
        failure_count,
        len(
            METADATA_RECOVERY_BACKOFF_SECONDS
        ),
    ) - 1
    return METADATA_RECOVERY_BACKOFF_SECONDS[
        index
    ]


def _record_retry_failure(
    state_path: Path,
    dvd_id: str,
    status: str,
    now: datetime,
) -> dict:
    if status not in {
        "NOT_FOUND",
        "FAILED",
    }:
        raise ValueError(
            "invalid metadata recovery retry status"
        )

    connection = _state_connection(
        state_path
    )

    try:
        with connection:
            row = connection.execute(
                """
                SELECT failure_count
                FROM metadata_recovery_retry
                WHERE dvd_id = ?
                """,
                (dvd_id,),
            ).fetchone()

            failure_count = (
                1
                if row is None
                else int(row["failure_count"]) + 1
            )
            next_attempt = now + timedelta(
                seconds=_backoff_seconds(
                    failure_count
                )
            )
            now_text = _format_time(now)
            next_text = _format_time(
                next_attempt
            )

            connection.execute(
                """
                INSERT INTO metadata_recovery_retry(
                    dvd_id, failure_count, last_status,
                    next_attempt_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(dvd_id)
                DO UPDATE SET
                    failure_count = excluded.failure_count,
                    last_status = excluded.last_status,
                    next_attempt_at = excluded.next_attempt_at,
                    updated_at = excluded.updated_at
                """,
                (
                    dvd_id,
                    failure_count,
                    status,
                    next_text,
                    now_text,
                ),
            )

            return {
                "failure_count": failure_count,
                "last_status": status,
                "next_attempt_at": next_text,
                "updated_at": now_text,
            }

    finally:
        connection.close()


def _clear_retry_state(
    state_path: Path,
    dvd_id: str,
) -> None:
    connection = _state_connection(
        state_path
    )

    try:
        with connection:
            connection.execute(
                """
                DELETE FROM metadata_recovery_retry
                WHERE dvd_id = ?
                """,
                (dvd_id,),
            )

    finally:
        connection.close()


def _has_canonical_ownership(
    database: Path,
    dvd_id: str,
) -> bool:
    connection = sqlite3.connect(
        "file:"
        + str(
            database.expanduser().resolve()
        )
        + "?mode=ro",
        uri=True,
    )

    try:
        return has_canonical_present_holding(
            connection,
            dvd_id,
        )

    finally:
        connection.close()


def _validate_collected_identity(
    collected: dict,
    expected_dvd_id: str,
) -> str:
    if not isinstance(collected, dict):
        raise ValueError(
            "collected metadata must be object"
        )

    parsed = parse_dvd_id(
        str(collected.get("dvd_id") or "")
    )

    if (
        parsed is None
        or parsed.dvd_id != expected_dvd_id
    ):
        raise ValueError(
            "collected metadata DVD-ID mismatch"
        )

    return parsed.dvd_id


def recover_held_metadata(
    plans: list[CompletionPlan],
    *,
    db_path: str | Path,
    writer_lock_path: str | Path,
    apply: bool = True,
    max_items: int = (
        DEFAULT_METADATA_RECOVERY_MAX_ITEMS
    ),
    state_path: str | Path | None = None,
    now=None,
    collector=collect_metadata_candidate_docker,
    applier=apply_held_collected_metadata,
) -> dict:
    """Best-effort, bounded metadata recovery for held downloads.

    This function deliberately does not alter a completion plan. A successful
    write is consumed by the planner on the next runner cycle.
    """
    _validate_max_items(max_items)

    candidates = _recovery_candidates(
        plans
    )

    result = _empty_result(
        len(candidates)
    )

    if not apply:
        result["skipped"] = "DRY_RUN"
        return result

    database = Path(db_path)
    writer_lock = Path(writer_lock_path)
    retry_state_path = (
        default_metadata_recovery_state_path(
            database
        )
        if state_path is None
        else Path(state_path)
    )
    now_value = _utc_now(now)

    try:
        retry_state = _load_retry_state(
            retry_state_path,
            [
                plan.dvd_id
                for plan in candidates
            ],
        )

    except Exception as exc:
        result["state_error"] = {
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        return result

    due_candidates = []

    for plan in candidates:
        state = retry_state.get(
            plan.dvd_id
        )

        if (
            state is not None
            and now_value
            < state["next_attempt_at"]
        ):
            result.setdefault(
                "backoff_skipped",
                0,
            )
            result["backoff_skipped"] += 1
            result["results"].append({
                "dvd_id": plan.dvd_id,
                "status": "SKIPPED_BACKOFF",
                "next_attempt_at": _format_time(
                    state["next_attempt_at"]
                ),
            })
            continue

        due_candidates.append(plan)

    for plan in due_candidates[:max_items]:
        dvd_id = plan.dvd_id

        try:
            if _has_canonical_ownership(
                database,
                dvd_id,
            ):
                result[
                    "skipped_ownership"
                ] += 1
                result["results"].append({
                    "dvd_id": dvd_id,
                    "status":
                        "SKIPPED_OWNERSHIP",
                })
                continue

            result["attempted"] += 1

            collected = collector(
                dvd_id
            )

            collected_dvd_id = (
                _validate_collected_identity(
                    collected,
                    dvd_id,
                )
            )

            status = collected.get(
                "status"
            )

            if status == "NOT_FOUND":
                retry = _record_retry_failure(
                    retry_state_path,
                    dvd_id,
                    "NOT_FOUND",
                    now_value,
                )
                result["not_found"] += 1
                result["results"].append({
                    "dvd_id":
                        collected_dvd_id,
                    "status": "NOT_FOUND",
                    "next_attempt_at": retry[
                        "next_attempt_at"
                    ],
                })
                continue

            if status != "FOUND":
                raise ValueError(
                    "unknown collected metadata "
                    "status"
                )

            with writer_transaction(
                database,
                writer_lock,
            ) as connection:
                if has_canonical_present_holding(
                    connection,
                    dvd_id,
                ):
                    result[
                        "skipped_ownership"
                    ] += 1
                    result["results"].append({
                        "dvd_id": dvd_id,
                        "status":
                            "SKIPPED_OWNERSHIP",
                    })
                    continue

                written_dvd_id = applier(
                    connection,
                    collected,
                )

                if written_dvd_id != dvd_id:
                    raise ValueError(
                        "metadata writer DVD-ID mismatch"
                    )

            result["recovered"] += 1
            try:
                _clear_retry_state(
                    retry_state_path,
                    dvd_id,
                )
            except Exception as exc:
                result.setdefault(
                    "state_warnings",
                    [],
                ).append({
                    "dvd_id": dvd_id,
                    "error_type": type(
                        exc
                    ).__name__,
                    "error": str(exc),
                })
            result["results"].append({
                "dvd_id": dvd_id,
                "status": "RECOVERED",
                "route": collected.get(
                    "route"
                ),
            })

        except Exception as exc:
            result["failed"] += 1
            retry = None
            try:
                retry = _record_retry_failure(
                    retry_state_path,
                    dvd_id,
                    "FAILED",
                    now_value,
                )
            except Exception as retry_exc:
                result.setdefault(
                    "state_warnings",
                    [],
                ).append({
                    "dvd_id": dvd_id,
                    "error_type": type(
                        retry_exc
                    ).__name__,
                    "error": str(retry_exc),
                })
            result["results"].append({
                "dvd_id": dvd_id,
                "status": "FAILED",
                "error_type": type(
                    exc
                ).__name__,
                "error": str(exc),
                **(
                    {
                        "next_attempt_at": retry[
                            "next_attempt_at"
                        ]
                    }
                    if retry is not None
                    else {}
                ),
            })

    return result
