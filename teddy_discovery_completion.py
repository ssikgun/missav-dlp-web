from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any

from teddy_discovery_ids import parse_dvd_id
from teddy_discovery_organizer import (
    VIDEO_EXTENSIONS,
    canonical_destination,
    load_db_state,
)
from teddy_discovery_ownership import (
    is_canonical_present_holding,
)


@dataclass(frozen=True)
class CompletionPlan:
    source_relative: str
    dvd_id: str | None
    parse_method: str | None
    size_bytes: int
    mtime_ns: int
    destination_relative: str | None
    metadata_ready: bool
    holding_count: int
    planned_operation: str
    collision_type: str
    reason: str


def _safe_source_relative(value: Any) -> str | None:
    raw = str(value or "").strip()

    if not raw:
        return None

    path = PurePosixPath(raw)

    if path.is_absolute():
        return None

    if any(
        part in ("", ".", "..")
        or part.startswith(".")
        or part == "@eaDir"
        for part in path.parts
    ):
        return None

    return path.as_posix()


def _plan_one(
    item: dict,
    db_state: dict,
) -> CompletionPlan:

    relative = _safe_source_relative(
        item.get("name")
    )

    size = int(
        item.get("size") or 0
    )

    raw_mtime_ns = item.get(
        "mtime_ns"
    )

    if raw_mtime_ns is None:
        modified = float(
            item.get("modified") or 0
        )

        mtime_ns = int(
            modified * 1_000_000_000
        )
    else:
        mtime_ns = int(
            raw_mtime_ns
        )

    if relative is None:
        return CompletionPlan(
            source_relative=str(
                item.get("name") or ""
            ),
            dvd_id=None,
            parse_method=None,
            size_bytes=size,
            mtime_ns=mtime_ns,
            destination_relative=None,
            metadata_ready=False,
            holding_count=0,
            planned_operation="HOLD",
            collision_type="INVALID_SOURCE_PATH",
            reason="unsafe source path",
        )

    source = PurePosixPath(
        relative
    )

    suffix = source.suffix.lower()

    if suffix not in VIDEO_EXTENSIONS:
        return CompletionPlan(
            source_relative=relative,
            dvd_id=None,
            parse_method=None,
            size_bytes=size,
            mtime_ns=mtime_ns,
            destination_relative=None,
            metadata_ready=False,
            holding_count=0,
            planned_operation="HOLD",
            collision_type="NOT_VIDEO",
            reason="source is not supported video",
        )

    parsed = parse_dvd_id(
        source.name
    )

    if parsed is None:
        return CompletionPlan(
            source_relative=relative,
            dvd_id=None,
            parse_method=None,
            size_bytes=size,
            mtime_ns=mtime_ns,
            destination_relative=None,
            metadata_ready=False,
            holding_count=0,
            planned_operation="HOLD",
            collision_type="UNMATCHED",
            reason="canonical DVD-ID parse failed",
        )

    dvd_id = parsed.dvd_id

    metadata = (
        db_state.get("metadata", {})
        .get(dvd_id)
    )

    metadata_ready = bool(
        metadata
        and metadata.get("title")
        and metadata.get(
            "metadata_source"
        )
    )

    holdings = [
        row
        for row in db_state.get(
            "holdings",
            [],
        )
        if row.get("dvd_id") == dvd_id
        and is_canonical_present_holding(
            row
        )
    ]

    holding_count = len(
        holdings
    )

    destination = (
        canonical_destination(
            dvd_id,
            suffix,
        ).as_posix()
    )

    if holding_count:
        return CompletionPlan(
            source_relative=relative,
            dvd_id=dvd_id,
            parse_method=parsed.method,
            size_bytes=size,
            mtime_ns=mtime_ns,
            destination_relative=destination,
            metadata_ready=metadata_ready,
            holding_count=holding_count,
            planned_operation="HOLD",
            collision_type="ALREADY_IN_LIBRARY",
            reason=(
                "same canonical DVD-ID "
                "already exists in holdings"
            ),
        )

    if not metadata_ready:
        return CompletionPlan(
            source_relative=relative,
            dvd_id=dvd_id,
            parse_method=parsed.method,
            size_bytes=size,
            mtime_ns=mtime_ns,
            destination_relative=destination,
            metadata_ready=False,
            holding_count=0,
            planned_operation="HOLD",
            collision_type="METADATA_NOT_READY",
            reason="metadata is not ready",
        )

    return CompletionPlan(
        source_relative=relative,
        dvd_id=dvd_id,
        parse_method=parsed.method,
        size_bytes=size,
        mtime_ns=mtime_ns,
        destination_relative=destination,
        metadata_ready=True,
        holding_count=0,
        planned_operation="PLAN_STAGE9_SSH_MOVE",
        collision_type="NONE",
        reason="remote organizer candidate ready",
    )


def plan_remote_downloads(
    items: list[dict],
    *,
    db_path: Path | None = None,
    db_state: dict | None = None,
) -> list[CompletionPlan]:

    if db_state is None:
        if db_path is None:
            raise ValueError(
                "db_path or db_state required"
            )

        db_state = load_db_state(
            db_path
        )

    plans = [
        _plan_one(
            item,
            db_state,
        )
        for item in items
    ]

    counts = Counter(
        plan.dvd_id
        for plan in plans
        if plan.dvd_id
    )

    result = []

    for plan in plans:
        if (
            plan.dvd_id
            and counts[
                plan.dvd_id
            ] > 1
        ):
            plan = replace(
                plan,
                planned_operation="HOLD",
                collision_type=(
                    "MULTIPLE_SOURCE_FILES"
                ),
                reason=(
                    "multiple download files "
                    "share canonical DVD-ID"
                ),
            )

        result.append(
            plan
        )

    return result
