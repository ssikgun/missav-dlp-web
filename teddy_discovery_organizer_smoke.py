from __future__ import annotations

from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from teddy_discovery_organizer import (
    canonical_destination,
    family_for_dvd_id,
    plan,
    summary,
)


def require(
    condition: bool,
    marker: str,
):
    if not condition:
        raise AssertionError(marker)

    print(marker + "=PASS")


def write_fake(
    path: Path,
    size: int = 1,
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_bytes(
        b"x" * size
    )


def create_db(
    path: Path,
):
    db = sqlite3.connect(path)

    try:
        db.executescript(
            """
            CREATE TABLE holdings (
                holding_id INTEGER PRIMARY KEY,
                storage_root TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                dvd_id TEXT,
                parse_status TEXT NOT NULL,
                parse_method TEXT,
                size_bytes INTEGER NOT NULL,
                mtime_ns INTEGER NOT NULL,
                present INTEGER NOT NULL
            );

            CREATE TABLE titles (
                dvd_id TEXT PRIMARY KEY,
                title TEXT,
                metadata_source TEXT
            );

            CREATE TABLE organizer_jobs (
                job_id INTEGER PRIMARY KEY,
                dvd_id TEXT,
                source_path TEXT,
                destination_path TEXT,
                status TEXT,
                error TEXT
            );
            """
        )

        db.commit()

    finally:
        db.close()


def add_holding(
    db_path: Path,
    relative: str,
    dvd_id: str,
    size: int,
):
    db = sqlite3.connect(db_path)

    try:
        db.execute(
            """
            INSERT INTO holdings (
                storage_root,
                relative_path,
                dvd_id,
                parse_status,
                parse_method,
                size_bytes,
                mtime_ns,
                present
            )
            VALUES (
                'jav',
                ?,
                ?,
                'MATCHED',
                'standard-leading',
                ?,
                0,
                1
            )
            """,
            (
                relative,
                dvd_id,
                size,
            ),
        )

        db.commit()

    finally:
        db.close()


def add_metadata(
    db_path: Path,
    dvd_id: str,
):
    db = sqlite3.connect(db_path)

    try:
        db.execute(
            """
            INSERT INTO titles (
                dvd_id,
                title,
                metadata_source
            )
            VALUES (?, ?, ?)
            """,
            (
                dvd_id,
                "test title",
                "test-source",
            ),
        )

        db.commit()

    finally:
        db.close()


def run_plan(
    downloads: Path,
    library: Path,
    db_path: Path,
    mode: str,
):
    source = (
        library
        if mode == "library"
        else downloads
    )

    return plan(
        source_root=source,
        library_root=library,
        db_path=db_path,
        mode=mode,
        stability_seconds=0,
    )


def main():
    require(
        family_for_dvd_id(
            "JUR-821"
        )
        == "JUR",
        "FAMILY_STANDARD",
    )

    require(
        family_for_dvd_id(
            "FC2-PPV-4592689"
        )
        == "FC2-PPV",
        "FAMILY_FC2",
    )

    require(
        canonical_destination(
            "JUR-821",
            ".MP4",
        )
        == Path(
            "JUR/JUR-821/"
            "JUR-821.mp4"
        ),
        "CANONICAL_STANDARD",
    )

    require(
        canonical_destination(
            "FC2-PPV-4592689",
            ".mp4",
        )
        == Path(
            "FC2-PPV/"
            "FC2-PPV-4592689/"
            "FC2-PPV-4592689.mp4"
        ),
        "CANONICAL_FC2",
    )

    #
    # Downloads: safe canonical plan.
    #
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        downloads = root / "downloads"
        library = root / "jav"
        db_path = root / "test.sqlite3"

        downloads.mkdir()
        library.mkdir()
        create_db(db_path)

        source = (
            downloads
            / "missav"
            / (
                "[jur-821] "
                "JUR-821 title.mp4"
            )
        )

        write_fake(
            source,
            7,
        )

        add_metadata(
            db_path,
            "JUR-821",
        )

        before = sorted(
            str(path.relative_to(root))
            for path in root.rglob("*")
        )

        plans, diagnostics = run_plan(
            downloads,
            library,
            db_path,
            "downloads",
        )

        after = sorted(
            str(path.relative_to(root))
            for path in root.rglob("*")
        )

        require(
            len(plans) == 1,
            "DOWNLOAD_SINGLE_PLAN",
        )

        require(
            plans[0].planned_operation
            == "PLAN_STAGE7_MOVE",
            "DOWNLOAD_PLAN_STATUS",
        )

        require(
            plans[0].destination_relative
            == (
                "JUR/JUR-821/"
                "JUR-821.mp4"
            ),
            "DOWNLOAD_DESTINATION",
        )

        require(
            plans[0].size_bytes == 7,
            "DOWNLOAD_SIZE",
        )

        require(
            plans[0].metadata_ready,
            "DOWNLOAD_METADATA_READY",
        )

        require(
            diagnostics[
                "holding_contradictions"
            ] == 0,
            "DOWNLOAD_HOLDINGS_CLEAN",
        )

        require(
            before == after,
            "PLANNER_NO_FILESYSTEM_WRITE",
        )

    #
    # Metadata absence alone must not block
    # canonical DVD-ID naming.
    #
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        downloads = root / "downloads"
        library = root / "jav"
        db_path = root / "test.sqlite3"

        downloads.mkdir()
        library.mkdir()
        create_db(db_path)

        write_fake(
            downloads
            / "FNS-235 title.mp4",
            3,
        )

        plans, diagnostics = run_plan(
            downloads,
            library,
            db_path,
            "downloads",
        )

        require(
            plans[0].planned_operation
            == "PLAN_STAGE7_MOVE",
            "METADATA_MISSING_STILL_PLAN",
        )

        require(
            not plans[0].metadata_ready,
            "METADATA_MISSING_REPORTED",
        )

    #
    # Existing flat JAV file:
    # legitimate Stage 7 relayout.
    #
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        downloads = root / "downloads"
        library = root / "jav"
        db_path = root / "test.sqlite3"

        downloads.mkdir()
        library.mkdir()
        create_db(db_path)

        relative = (
            "SONE-978 old title.mp4"
        )

        write_fake(
            library / relative,
            5,
        )

        add_holding(
            db_path,
            relative,
            "SONE-978",
            5,
        )

        plans, diagnostics = run_plan(
            downloads,
            library,
            db_path,
            "library",
        )

        require(
            plans[0].planned_operation
            == "PLAN_STAGE7_RELAYOUT",
            "LIBRARY_RELAYOUT_PLAN",
        )

        require(
            plans[0].destination_relative
            == (
                "SONE/SONE-978/"
                "SONE-978.mp4"
            ),
            "LIBRARY_RELAYOUT_DESTINATION",
        )

        require(
            plans[0].current_holding_state
            == "PRESENT_MATCHED",
            "LIBRARY_HOLDING_MATCHED",
        )

    #
    # Already canonical JAV file.
    #
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        downloads = root / "downloads"
        library = root / "jav"
        db_path = root / "test.sqlite3"

        downloads.mkdir()
        library.mkdir()
        create_db(db_path)

        relative = (
            "SONE/SONE-978/"
            "SONE-978.mp4"
        )

        write_fake(
            library / relative,
            5,
        )

        add_holding(
            db_path,
            relative,
            "SONE-978",
            5,
        )

        plans, diagnostics = run_plan(
            downloads,
            library,
            db_path,
            "library",
        )

        require(
            plans[0].planned_operation
            == "ALREADY_CANONICAL",
            "ALREADY_CANONICAL",
        )

    #
    # Duplicate completed downloads.
    #
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        downloads = root / "downloads"
        library = root / "jav"
        db_path = root / "test.sqlite3"

        downloads.mkdir()
        library.mkdir()
        create_db(db_path)

        write_fake(
            downloads
            / "[jur-821] a.mp4"
        )

        write_fake(
            downloads
            / "JUR-821 b.mp4"
        )

        plans, diagnostics = run_plan(
            downloads,
            library,
            db_path,
            "downloads",
        )

        require(
            all(
                item.planned_operation
                == "HOLD"
                for item in plans
            ),
            "BLOCK_DOWNLOAD_DUPLICATE",
        )

        require(
            all(
                item.collision_type
                == "MULTIPLE_MEDIA"
                for item in plans
            ),
            "DUPLICATE_COLLISION_TYPE",
        )

    #
    # Same DVD-ID already in JAV.
    #
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        downloads = root / "downloads"
        library = root / "jav"
        db_path = root / "test.sqlite3"

        downloads.mkdir()
        library.mkdir()
        create_db(db_path)

        write_fake(
            downloads
            / "JUR-821 new.mp4",
            3,
        )

        relative = (
            "JUR-821 old.mp4"
        )

        write_fake(
            library / relative,
            4,
        )

        add_holding(
            db_path,
            relative,
            "JUR-821",
            4,
        )

        plans, diagnostics = run_plan(
            downloads,
            library,
            db_path,
            "downloads",
        )

        require(
            plans[0].planned_operation
            == "HOLD",
            "BLOCK_LIBRARY_OVERLAP",
        )

        require(
            plans[0].collision_type
            == "ALREADY_IN_LIBRARY",
            "LIBRARY_OVERLAP_REASON",
        )

    #
    # Unmatched filename.
    #
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        downloads = root / "downloads"
        library = root / "jav"
        db_path = root / "test.sqlite3"

        downloads.mkdir()
        library.mkdir()
        create_db(db_path)

        write_fake(
            downloads
            / "no-dvd-id-here.mp4"
        )

        plans, diagnostics = run_plan(
            downloads,
            library,
            db_path,
            "downloads",
        )

        require(
            plans[0].planned_operation
            == "HOLD",
            "BLOCK_UNMATCHED",
        )

        require(
            plans[0].match_state
            == "UNMATCHED",
            "UNMATCHED_REPORTED",
        )

    #
    # holdings/filesystem contradiction:
    # fail closed for all candidates.
    #
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        downloads = root / "downloads"
        library = root / "jav"
        db_path = root / "test.sqlite3"

        downloads.mkdir()
        library.mkdir()
        create_db(db_path)

        write_fake(
            downloads
            / "FNS-247 title.mp4",
            8,
        )

        add_holding(
            db_path,
            "missing-file.mp4",
            "SONE-999",
            10,
        )

        plans, diagnostics = run_plan(
            downloads,
            library,
            db_path,
            "downloads",
        )

        require(
            diagnostics[
                "holding_contradictions"
            ] == 1,
            "HOLDING_CONTRADICTION_DETECTED",
        )

        require(
            plans[0].planned_operation
            == "HOLD",
            "HOLDING_CONTRADICTION_BLOCKS",
        )

        require(
            plans[0].collision_type
            == "HOLDING_STATE_CONTRADICTION",
            "HOLDING_CONTRADICTION_REASON",
        )

    #
    # Required Stage 6 reporting contract.
    #
    required_fields = {
        "source_relative",
        "dvd_id",
        "normalization_result",
        "match_state",
        "metadata_ready",
        "current_holding_state",
        "destination_relative",
        "destination_exists",
        "collision_type",
        "size_bytes",
        "existing_destination_size",
        "duplicate_status",
        "organizer_job_status",
        "planned_operation",
        "reason",
        "parse_method",
    }

    require(
        required_fields.issubset(
            plans[0].__dataclass_fields__
        ),
        "STAGE6_REPORT_FIELDS",
    )

    result = summary(
        plans,
        diagnostics,
    )

    require(
        "diagnostics" in result,
        "STAGE6_SUMMARY_DIAGNOSTICS",
    )

    print(
        "ORGANIZER_STAGE6_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
