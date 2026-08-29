from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
import argparse
import json
import sqlite3
import time
from typing import Iterable

from teddy_discovery_ids import parse_dvd_id


VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".m4v",
    ".ts",
    ".webm",
}

PARTIAL_EXTENSIONS = {
    ".part",
    ".partial",
    ".tmp",
    ".temp",
    ".crdownload",
    ".ytdl",
    ".aria2",
    ".download",
}


@dataclass(frozen=True)
class OrganizerPlan:
    source_relative: str
    dvd_id: str | None
    normalization_result: str
    match_state: str
    metadata_ready: bool
    current_holding_state: str
    destination_relative: str | None
    destination_exists: bool
    collision_type: str
    size_bytes: int
    existing_destination_size: int | None
    duplicate_status: str
    organizer_job_status: str
    planned_operation: str
    reason: str
    parse_method: str | None


def family_for_dvd_id(
    dvd_id: str,
) -> str:
    value = dvd_id.strip().upper()

    if not value:
        raise ValueError(
            "dvd_id must not be empty"
        )

    if "-" not in value:
        raise ValueError(
            "dvd_id must contain '-'"
        )

    family = value.rsplit(
        "-",
        1,
    )[0]

    if not family:
        raise ValueError(
            "dvd_id family must not be empty"
        )

    return family


def canonical_destination(
    dvd_id: str,
    suffix: str,
) -> Path:
    normalized_id = (
        dvd_id.strip().upper()
    )

    normalized_suffix = suffix.lower()

    if (
        not normalized_suffix
        or not normalized_suffix.startswith(".")
    ):
        raise ValueError(
            "video suffix must include leading '.'"
        )

    family = family_for_dvd_id(
        normalized_id
    )

    return (
        Path(family)
        / normalized_id
        / (
            normalized_id
            + normalized_suffix
        )
    )


def iter_video_files(
    root: Path,
) -> Iterable[Path]:
    if not root.is_dir():
        raise RuntimeError(
            "inventory root is not a directory: "
            + str(root)
        )

    for path in sorted(
        root.rglob("*")
    ):
        if "@eaDir" in path.parts:
            continue

        if not path.is_file():
            continue

        if (
            path.suffix.lower()
            not in VIDEO_EXTENSIONS
        ):
            continue

        yield path


def _has_symlink_component(
    path: Path,
    root: Path,
) -> bool:
    current = path

    while True:
        if current.is_symlink():
            return True

        if current == root:
            return False

        if root not in current.parents:
            return True

        current = current.parent


def scan(
    root: Path,
):
    root = root.resolve()

    rows = []

    for path in iter_video_files(
        root
    ):
        stat = path.stat()

        parsed = parse_dvd_id(
            path.name
        )

        symlink = (
            _has_symlink_component(
                path,
                root,
            )
        )

        try:
            resolved = path.resolve(
                strict=True
            )

            resolved.relative_to(root)

            inside_root = True

        except (
            OSError,
            ValueError,
        ):
            inside_root = False

        rows.append({
            "path": path,
            "relative": str(
                path.relative_to(root)
            ),
            "size_bytes": int(
                stat.st_size
            ),
            "mtime_ns": int(
                stat.st_mtime_ns
            ),
            "parsed": parsed,
            "symlink": symlink,
            "inside_root": inside_root,
        })

    return rows


def scan_partial_ids(
    root: Path,
):
    result = defaultdict(list)

    root = root.resolve()

    for path in sorted(
        root.rglob("*")
    ):
        if "@eaDir" in path.parts:
            continue

        if not path.is_file():
            continue

        name = path.name.lower()

        if not any(
            name.endswith(extension)
            for extension
            in PARTIAL_EXTENSIONS
        ):
            continue

        parsed = parse_dvd_id(
            path.name
        )

        if parsed is not None:
            result[
                parsed.dvd_id
            ].append(
                str(
                    path.relative_to(root)
                )
            )

    return result


def load_db_state(
    db_path: Path,
):
    db = sqlite3.connect(
        "file:"
        + str(db_path)
        + "?mode=ro",
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

        holdings = [
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
                    size_bytes,
                    mtime_ns,
                    present
                FROM holdings
                WHERE storage_root = 'jav'
                  AND present = 1
                ORDER BY relative_path
                """
            )
        ]

        metadata = {
            row["dvd_id"]: dict(row)
            for row in db.execute(
                """
                SELECT
                    dvd_id,
                    title,
                    metadata_source
                FROM titles
                """
            )
        }

        organizer_jobs = [
            dict(row)
            for row in db.execute(
                """
                SELECT
                    job_id,
                    dvd_id,
                    source_path,
                    destination_path,
                    status,
                    error
                FROM organizer_jobs
                ORDER BY job_id
                """
            )
        ]

    finally:
        db.close()

    return {
        "holdings": holdings,
        "metadata": metadata,
        "organizer_jobs":
            organizer_jobs,
    }


def reconcile_holdings(
    library_rows,
    holdings,
):
    library_by_relative = {
        row["relative"]: row
        for row in library_rows
    }

    holding_by_relative = {
        row["relative_path"]: row
        for row in holdings
    }

    contradictions = []

    for relative, holding in (
        holding_by_relative.items()
    ):
        row = library_by_relative.get(
            relative
        )

        if row is None:
            contradictions.append(
                "DB_PRESENT_FILE_MISSING:"
                + relative
            )
            continue

        parsed = row["parsed"]

        dvd_id = (
            None
            if parsed is None
            else parsed.dvd_id
        )

        if dvd_id != holding["dvd_id"]:
            contradictions.append(
                "DVD_ID_MISMATCH:"
                + relative
            )

        if (
            row["size_bytes"]
            != int(
                holding["size_bytes"]
            )
        ):
            contradictions.append(
                "SIZE_MISMATCH:"
                + relative
            )

    for relative in library_by_relative:
        if relative not in holding_by_relative:
            contradictions.append(
                "FILE_PRESENT_DB_MISSING:"
                + relative
            )

    return contradictions


def plan(
    source_root: Path,
    library_root: Path,
    db_path: Path,
    mode: str,
    stability_seconds: float = 3.0,
):
    if mode not in {
        "library",
        "downloads",
    }:
        raise ValueError(
            "mode must be 'library' "
            "or 'downloads'"
        )

    source_root = source_root.resolve()
    library_root = library_root.resolve()

    if (
        mode == "library"
        and source_root != library_root
    ):
        raise ValueError(
            "library mode requires "
            "source_root == library_root"
        )

    source_before = scan(
        source_root
    )

    if stability_seconds > 0:
        time.sleep(
            stability_seconds
        )

    source_rows = scan(
        source_root
    )

    library_rows = scan(
        library_root
    )

    before_by_relative = {
        row["relative"]: row
        for row in source_before
    }

    after_by_relative = {
        row["relative"]: row
        for row in source_rows
    }

    changed_paths = set()
    appeared_paths = set()
    disappeared_paths = set()

    for relative, before in (
        before_by_relative.items()
    ):
        after = after_by_relative.get(
            relative
        )

        if after is None:
            disappeared_paths.add(
                relative
            )
            continue

        if (
            before["size_bytes"]
            != after["size_bytes"]
            or before["mtime_ns"]
            != after["mtime_ns"]
        ):
            changed_paths.add(
                relative
            )

    for relative in after_by_relative:
        if relative not in before_by_relative:
            appeared_paths.add(
                relative
            )

    db_state = load_db_state(
        db_path
    )

    holdings = db_state[
        "holdings"
    ]

    metadata = db_state[
        "metadata"
    ]

    organizer_jobs = db_state[
        "organizer_jobs"
    ]

    holding_contradictions = (
        reconcile_holdings(
            library_rows,
            holdings,
        )
    )

    source_by_id = defaultdict(list)
    library_by_id = defaultdict(list)
    jobs_by_id = defaultdict(list)

    for row in source_rows:
        parsed = row["parsed"]

        if parsed is not None:
            source_by_id[
                parsed.dvd_id
            ].append(row)

    for row in library_rows:
        parsed = row["parsed"]

        if parsed is not None:
            library_by_id[
                parsed.dvd_id
            ].append(row)

    for job in organizer_jobs:
        dvd_id = job.get(
            "dvd_id"
        )

        if dvd_id:
            jobs_by_id[
                dvd_id
            ].append(job)

    partial_ids = (
        scan_partial_ids(
            source_root
        )
        if mode == "downloads"
        else {}
    )

    holding_by_relative = {
        row["relative_path"]: row
        for row in holdings
    }

    source_set_unstable = bool(
        appeared_paths
        or disappeared_paths
    )

    plans = []

    for row in source_rows:
        parsed = row["parsed"]

        dvd_id = (
            None
            if parsed is None
            else parsed.dvd_id
        )

        parse_method = (
            None
            if parsed is None
            else parsed.method
        )

        normalization_result = (
            "NO_CANONICAL_DVD_ID"
            if dvd_id is None
            else (
                dvd_id
                + " via "
                + str(parse_method)
            )
        )

        match_state = (
            "UNMATCHED"
            if dvd_id is None
            else "MATCHED"
        )

        metadata_row = (
            metadata.get(dvd_id)
            if dvd_id
            else None
        )

        metadata_ready = bool(
            metadata_row
            and metadata_row.get("title")
            and metadata_row.get(
                "metadata_source"
            )
        )

        destination = (
            None
            if dvd_id is None
            else canonical_destination(
                dvd_id,
                row["path"].suffix,
            )
        )

        destination_exists = False
        existing_destination_size = None

        duplicate_status = "NONE"
        organizer_job_status = "NONE"

        collision_type = "NONE"

        planned_operation = (
            "PLAN_STAGE7_RELAYOUT"
            if mode == "library"
            else "PLAN_STAGE7_MOVE"
        )

        reason = (
            "canonical DVD-ID path safe"
        )

        if mode == "library":
            holding = (
                holding_by_relative.get(
                    row["relative"]
                )
            )

            if holding is None:
                current_holding_state = (
                    "CONTRADICTION"
                )
            else:
                current_holding_state = (
                    "PRESENT_MATCHED"
                )

        else:
            library_matches = (
                library_by_id.get(
                    dvd_id,
                    [],
                )
                if dvd_id
                else []
            )

            if not library_matches:
                current_holding_state = (
                    "ABSENT"
                )
            elif len(library_matches) == 1:
                current_holding_state = (
                    "PRESENT_MATCHED"
                )
            else:
                current_holding_state = (
                    "PRESENT_MULTIPLE"
                )

        if dvd_id is None:
            planned_operation = "HOLD"
            collision_type = "UNMATCHED"
            reason = (
                "canonical DVD-ID parse failed"
            )

        elif not row["inside_root"]:
            planned_operation = "HOLD"
            collision_type = (
                "SOURCE_ROOT_ESCAPE"
            )
            reason = (
                "source resolves outside "
                "expected root"
            )

        elif row["symlink"]:
            planned_operation = "HOLD"
            collision_type = (
                "SOURCE_SYMLINK"
            )
            reason = (
                "source path contains symlink"
            )

        elif (
            row["relative"]
            in changed_paths
        ):
            planned_operation = "HOLD"
            collision_type = (
                "SOURCE_CHANGED"
            )
            reason = (
                "source size or mtime changed "
                "during stability observation"
            )

        elif source_set_unstable:
            planned_operation = "HOLD"
            collision_type = (
                "SOURCE_SET_CHANGED"
            )
            reason = (
                "source file set changed "
                "during stability observation"
            )

        elif (
            mode == "downloads"
            and dvd_id
            and partial_ids.get(dvd_id)
        ):
            planned_operation = "HOLD"
            collision_type = (
                "ACTIVE_OR_PARTIAL"
            )
            reason = (
                "partial/active file exists "
                "for same DVD-ID"
            )

        if (
            dvd_id
            and len(
                source_by_id.get(
                    dvd_id,
                    [],
                )
            ) > 1
        ):
            duplicate_status = (
                "MULTIPLE_SOURCE_FILES"
            )

            planned_operation = "HOLD"

            collision_type = (
                "MULTIPLE_MEDIA"
            )

            reason = (
                "multiple media files share "
                "canonical DVD-ID"
            )

        if (
            mode == "downloads"
            and dvd_id
            and library_by_id.get(
                dvd_id
            )
        ):
            duplicate_status = (
                "ALREADY_IN_LIBRARY"
            )

            planned_operation = "HOLD"

            collision_type = (
                "ALREADY_IN_LIBRARY"
            )

            reason = (
                "same canonical DVD-ID "
                "already exists in JAV"
            )

        if (
            mode == "library"
            and destination is not None
            and row["relative"]
            == str(destination)
            and planned_operation
            != "HOLD"
        ):
            planned_operation = (
                "ALREADY_CANONICAL"
            )

            reason = (
                "existing JAV file already "
                "uses canonical path"
            )

        if destination is not None:
            destination_path = (
                library_root
                / destination
            )

            try:
                resolved_parent = (
                    destination_path.parent.resolve(
                        strict=False
                    )
                )

                resolved_destination = (
                    resolved_parent
                    / destination_path.name
                )

                resolved_destination.relative_to(
                    library_root
                )

            except ValueError:
                planned_operation = "HOLD"

                collision_type = (
                    "DESTINATION_ROOT_ESCAPE"
                )

                reason = (
                    "destination resolves "
                    "outside JAV root"
                )

            else:
                destination_exists = (
                    destination_path.exists()
                )

                same_current_file = (
                    mode == "library"
                    and row["path"]
                    == destination_path
                )

                if (
                    destination_exists
                    and not same_current_file
                ):
                    try:
                        existing_destination_size = int(
                            destination_path.stat().st_size
                        )

                    except OSError:
                        planned_operation = "HOLD"

                        collision_type = (
                            "DESTINATION_STAT_ERROR"
                        )

                        reason = (
                            "destination exists "
                            "but stat failed"
                        )

                    else:
                        planned_operation = "HOLD"

                        if (
                            existing_destination_size
                            == row["size_bytes"]
                        ):
                            collision_type = (
                                "DEST_EXISTS_SAME_SIZE"
                            )

                            reason = (
                                "canonical destination "
                                "already exists"
                            )

                        else:
                            collision_type = (
                                "DEST_EXISTS_DIFFERENT_SIZE"
                            )

                            reason = (
                                "destination collision "
                                "with different size"
                            )

        candidate_jobs = (
            jobs_by_id.get(
                dvd_id,
                [],
            )
            if dvd_id
            else []
        )

        if candidate_jobs:
            organizer_job_status = ",".join(
                str(
                    job.get("status")
                )
                for job in candidate_jobs
            )

        if holding_contradictions:
            planned_operation = "HOLD"

            collision_type = (
                "HOLDING_STATE_CONTRADICTION"
            )

            reason = (
                "holdings DB and JAV "
                "filesystem disagree"
            )

        plans.append(
            OrganizerPlan(
                source_relative=
                    row["relative"],
                dvd_id=dvd_id,
                normalization_result=
                    normalization_result,
                match_state=match_state,
                metadata_ready=
                    metadata_ready,
                current_holding_state=
                    current_holding_state,
                destination_relative=(
                    None
                    if destination is None
                    else str(destination)
                ),
                destination_exists=
                    destination_exists,
                collision_type=
                    collision_type,
                size_bytes=
                    row["size_bytes"],
                existing_destination_size=
                    existing_destination_size,
                duplicate_status=
                    duplicate_status,
                organizer_job_status=
                    organizer_job_status,
                planned_operation=
                    planned_operation,
                reason=reason,
                parse_method=parse_method,
            )
        )

    diagnostics = {
        "source_changed":
            len(changed_paths),
        "source_appeared":
            len(appeared_paths),
        "source_disappeared":
            len(disappeared_paths),
        "partial_dvd_id_count":
            len(partial_ids),
        "holding_contradictions":
            len(holding_contradictions),
        "holding_contradiction_details":
            holding_contradictions,
        "organizer_job_count":
            len(organizer_jobs),
    }

    return plans, diagnostics


def summary(
    plans,
    diagnostics,
):
    operation_counts = Counter(
        item.planned_operation
        for item in plans
    )

    collision_counts = Counter(
        item.collision_type
        for item in plans
    )

    return {
        "total": len(plans),
        "planned_operation": dict(
            sorted(
                operation_counts.items()
            )
        ),
        "collision_type": dict(
            sorted(
                collision_counts.items()
            )
        ),
        "metadata_ready": sum(
            1
            for item in plans
            if item.metadata_ready
        ),
        "metadata_not_ready": sum(
            1
            for item in plans
            if not item.metadata_ready
        ),
        "diagnostics": diagnostics,
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Teddy Stage 6 Organizer "
            "read-only dry-run planner"
        )
    )

    parser.add_argument(
        "--source-root",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--library-root",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--db",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--mode",
        required=True,
        choices=(
            "library",
            "downloads",
        ),
    )

    parser.add_argument(
        "--stability-seconds",
        type=float,
        default=3.0,
    )

    parser.add_argument(
        "--json",
        action="store_true",
    )

    args = parser.parse_args()

    plans, diagnostics = plan(
        source_root=args.source_root,
        library_root=args.library_root,
        db_path=args.db,
        mode=args.mode,
        stability_seconds=max(
            0.0,
            args.stability_seconds,
        ),
    )

    result = summary(
        plans,
        diagnostics,
    )

    if args.json:
        print(
            json.dumps(
                {
                    "mode": args.mode,
                    "summary": result,
                    "plans": [
                        asdict(item)
                        for item in plans
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )

        return

    print(
        "MODE="
        + args.mode
    )

    print(
        "TOTAL="
        + str(
            result["total"]
        )
    )

    print(
        "SUMMARY="
        + repr(result)
    )

    for item in plans:
        print()
        print(
            "current_path="
            + item.source_relative
        )
        print(
            "dvd_id="
            + str(
                item.dvd_id or "-"
            )
        )
        print(
            "normalization_result="
            + item.normalization_result
        )
        print(
            "match_state="
            + item.match_state
        )
        print(
            "metadata_ready="
            + (
                "YES"
                if item.metadata_ready
                else "NO"
            )
        )
        print(
            "current_holding_state="
            + item.current_holding_state
        )
        print(
            "planned_destination="
            + str(
                item.destination_relative
                or "-"
            )
        )
        print(
            "destination_exists="
            + (
                "YES"
                if item.destination_exists
                else "NO"
            )
        )
        print(
            "collision_type="
            + item.collision_type
        )
        print(
            "source_size="
            + str(
                item.size_bytes
            )
        )
        print(
            "existing_destination_size="
            + (
                str(
                    item.existing_destination_size
                )
                if item.existing_destination_size
                is not None
                else "-"
            )
        )
        print(
            "same_title_duplicate_status="
            + item.duplicate_status
        )
        print(
            "organizer_job_status="
            + item.organizer_job_status
        )
        print(
            "planned_operation="
            + item.planned_operation
        )
        print(
            "reason="
            + item.reason
        )


if __name__ == "__main__":
    main()
