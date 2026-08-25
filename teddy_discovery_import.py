from __future__ import annotations

from datetime import datetime, timezone
import argparse
import json
from pathlib import Path

from teddy_discovery_db import connect, initialize
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


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat(timespec="seconds")


def scan(root: Path):
    if not root.is_dir():
        raise RuntimeError(
            f"inventory root is not a directory: {root}"
        )

    records = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue

        if "@eaDir" in path.parts:
            continue

        if path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue

        relative = path.relative_to(root).as_posix()
        stat = path.stat()
        parsed = parse_dvd_id(path.name)

        if parsed is None:
            dvd_id = None
            parse_status = "UNMATCHED"
            parse_method = None
            candidates = []
        else:
            dvd_id = parsed.dvd_id
            parse_status = "MATCHED"
            parse_method = parsed.method
            candidates = [parsed.dvd_id]

        records.append({
            "relative_path": relative,
            "dvd_id": dvd_id,
            "parse_status": parse_status,
            "parse_method": parse_method,
            "parse_candidates_json": json.dumps(
                candidates,
                ensure_ascii=False,
            ),
            "size_bytes": int(stat.st_size),
            "mtime_ns": int(stat.st_mtime_ns),
        })

    return records


def import_inventory(
    db_path: Path,
    root: Path,
    storage_root: str,
):
    connection = connect(db_path)
    initialize(connection)

    started = utc_now()

    cursor = connection.execute(
        """
        INSERT INTO inventory_runs(
            storage_root,
            root_path,
            started_at,
            status
        )
        VALUES (?, ?, ?, 'RUNNING')
        """,
        (
            storage_root,
            str(root),
            started,
        ),
    )

    run_id = int(cursor.lastrowid)
    connection.commit()

    try:
        records = scan(root)

        counts = {
            "MATCHED": 0,
            "AMBIGUOUS": 0,
            "UNMATCHED": 0,
        }

        for record in records:
            counts[record["parse_status"]] += 1

        now = utc_now()

        with connection:
            for record in records:
                connection.execute(
                    """
                    INSERT INTO holdings(
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
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?,
                        'library-inventory',
                        1,
                        ?, ?, ?
                    )
                    ON CONFLICT(
                        storage_root,
                        relative_path
                    )
                    DO UPDATE SET
                        dvd_id = excluded.dvd_id,
                        parse_status =
                            excluded.parse_status,
                        parse_method =
                            excluded.parse_method,
                        parse_candidates_json =
                            excluded.parse_candidates_json,
                        size_bytes =
                            excluded.size_bytes,
                        mtime_ns =
                            excluded.mtime_ns,
                        present = 1,
                        last_seen_at =
                            excluded.last_seen_at,
                        last_seen_run_id =
                            excluded.last_seen_run_id
                    """,
                    (
                        storage_root,
                        record["relative_path"],
                        record["dvd_id"],
                        record["parse_status"],
                        record["parse_method"],
                        record[
                            "parse_candidates_json"
                        ],
                        record["size_bytes"],
                        record["mtime_ns"],
                        now,
                        now,
                        run_id,
                    ),
                )

            # Reconciliation happens only after a complete filesystem scan.
            # Holdings from this same storage root that were not observed in
            # the current successful run are retained as history but marked
            # absent. A later run can set present=1 again if the file returns.
            connection.execute(
                """
                UPDATE holdings
                SET present = 0
                WHERE storage_root = ?
                  AND (
                      last_seen_run_id IS NULL
                      OR last_seen_run_id <> ?
                  )
                """,
                (
                    storage_root,
                    run_id,
                ),
            )

            connection.execute(
                """
                UPDATE inventory_runs
                SET
                    finished_at = ?,
                    status = 'COMPLETE',
                    video_files = ?,
                    matched = ?,
                    ambiguous = ?,
                    unmatched = ?
                WHERE run_id = ?
                """,
                (
                    now,
                    len(records),
                    counts["MATCHED"],
                    counts["AMBIGUOUS"],
                    counts["UNMATCHED"],
                    run_id,
                ),
            )

        return {
            "run_id": run_id,
            "video_files": len(records),
            **counts,
        }

    except Exception as exc:
        with connection:
            connection.execute(
                """
                UPDATE inventory_runs
                SET
                    finished_at = ?,
                    status = 'FAILED',
                    error = ?
                WHERE run_id = ?
                """,
                (
                    utc_now(),
                    str(exc),
                    run_id,
                ),
            )
        raise

    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--db",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--root",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--storage-root",
        required=True,
    )

    args = parser.parse_args()

    result = import_inventory(
        db_path=args.db,
        root=args.root,
        storage_root=args.storage_root,
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
