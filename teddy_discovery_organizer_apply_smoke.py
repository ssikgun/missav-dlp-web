from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3

import teddy_discovery_organizer_apply as apply_mod

from teddy_discovery_db import (
    connect,
    initialize,
)

from teddy_discovery_organizer import (
    plan,
)


def require(
    condition: bool,
    marker: str,
):
    if not condition:
        raise AssertionError(marker)

    print(marker + "=PASS")


def create_db(
    path: Path,
):
    db = connect(path)

    try:
        initialize(db)
    finally:
        db.close()


def write_fake(
    path: Path,
    size: int,
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_bytes(
        b"x" * size
    )


def add_holding(
    db_path: Path,
    relative: str,
    dvd_id: str,
    size: int,
):
    from datetime import (
        datetime,
        timezone,
    )

    now = datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )

    db = sqlite3.connect(
        db_path
    )

    try:
        db.execute(
            """
            INSERT INTO holdings (
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
                'jav',
                ?,
                ?,
                'MATCHED',
                'standard-leading',
                ?,
                ?,
                0,
                'test',
                1,
                ?,
                ?,
                NULL
            )
            """,
            (
                relative,
                dvd_id,
                '["' + dvd_id + '"]',
                size,
                now,
                now,
            ),
        )

        db.commit()

    finally:
        db.close()


def get_one_plan(
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

    plans, diagnostics = plan(
        source_root=source,
        library_root=library,
        db_path=db_path,
        mode=mode,
        stability_seconds=0,
    )

    require(
        diagnostics[
            "holding_contradictions"
        ] == 0,
        "PLAN_HOLDINGS_CLEAN",
    )

    require(
        len(plans) == 1,
        "PLAN_SINGLE",
    )

    return plans[0]


def job_statuses(
    db_path: Path,
):
    db = sqlite3.connect(
        db_path
    )

    try:
        return [
            row[0]
            for row in db.execute(
                """
                SELECT status
                FROM organizer_jobs
                ORDER BY job_id
                """
            )
        ]

    finally:
        db.close()


def holding_rows(
    db_path: Path,
):
    db = sqlite3.connect(
        db_path
    )

    try:
        return db.execute(
            """
            SELECT
                relative_path,
                dvd_id,
                present,
                size_bytes
            FROM holdings
            ORDER BY holding_id
            """
        ).fetchall()

    finally:
        db.close()


def partial_files(
    root: Path,
):
    return [
        path
        for path in root.rglob(
            "*.partial"
        )
    ]


def main():

    #
    # 1. Downloads -> JAV safe publish.
    #
    with TemporaryDirectory() as tmp:
        root = Path(tmp)

        downloads = (
            root / "downloads"
        )

        library = (
            root / "jav"
        )

        db_path = (
            root / "db.sqlite3"
        )

        apply_lock = (
            root / "apply.lock"
        )

        writer_lock = (
            root / "writer.lock"
        )

        downloads.mkdir()
        library.mkdir()

        create_db(
            db_path
        )

        source = (
            downloads
            / "missav"
            / "JUR-821 title.mp4"
        )

        write_fake(
            source,
            1024 * 1024 + 7,
        )

        item = get_one_plan(
            downloads,
            library,
            db_path,
            "downloads",
        )

        result = apply_mod.apply_one(
            item,
            mode="downloads",
            source_root=downloads,
            library_root=library,
            db_path=db_path,
            apply_lock_path=
                apply_lock,
            writer_lock_path=
                writer_lock,
            stability_seconds=0,
        )

        final = (
            library
            / "JUR"
            / "JUR-821"
            / "JUR-821.mp4"
        )

        require(
            result.status
            == "COMPLETED",
            "DOWNLOAD_APPLY_COMPLETED",
        )

        require(
            final.is_file(),
            "DOWNLOAD_FINAL_EXISTS",
        )

        require(
            final.stat().st_size
            == 1024 * 1024 + 7,
            "DOWNLOAD_FINAL_SIZE",
        )

        require(
            not source.exists(),
            "DOWNLOAD_SOURCE_CLEANED",
        )

        require(
            not partial_files(
                library
            ),
            "DOWNLOAD_NO_PARTIAL_LEFT",
        )

        rows = holding_rows(
            db_path
        )

        require(
            len(rows) == 1,
            "DOWNLOAD_HOLDING_INSERTED",
        )

        require(
            rows[0][0]
            == "JUR/JUR-821/JUR-821.mp4",
            "DOWNLOAD_HOLDING_PATH",
        )

        require(
            job_statuses(
                db_path
            )
            == ["COMPLETED"],
            "DOWNLOAD_JOB_COMPLETED",
        )

    #
    # 2. Existing JAV relayout.
    #
    with TemporaryDirectory() as tmp:
        root = Path(tmp)

        downloads = (
            root / "downloads"
        )

        library = (
            root / "jav"
        )

        db_path = (
            root / "db.sqlite3"
        )

        apply_lock = (
            root / "apply.lock"
        )

        writer_lock = (
            root / "writer.lock"
        )

        downloads.mkdir()
        library.mkdir()

        create_db(
            db_path
        )

        relative = (
            "SONE-978 old title.mp4"
        )

        source = (
            library
            / relative
        )

        write_fake(
            source,
            2222,
        )

        add_holding(
            db_path,
            relative,
            "SONE-978",
            2222,
        )

        item = get_one_plan(
            downloads,
            library,
            db_path,
            "library",
        )

        result = apply_mod.apply_one(
            item,
            mode="library",
            source_root=library,
            library_root=library,
            db_path=db_path,
            apply_lock_path=
                apply_lock,
            writer_lock_path=
                writer_lock,
            stability_seconds=0,
        )

        final = (
            library
            / "SONE"
            / "SONE-978"
            / "SONE-978.mp4"
        )

        require(
            result.status
            == "COMPLETED",
            "LIBRARY_RELAYOUT_COMPLETED",
        )

        require(
            final.is_file(),
            "LIBRARY_FINAL_EXISTS",
        )

        require(
            not source.exists(),
            "LIBRARY_OLD_SOURCE_CLEANED",
        )

        rows = holding_rows(
            db_path
        )

        require(
            len(rows) == 1,
            "LIBRARY_HOLDING_SINGLE",
        )

        require(
            rows[0][0]
            == "SONE/SONE-978/SONE-978.mp4",
            "LIBRARY_HOLDING_UPDATED",
        )

        require(
            job_statuses(
                db_path
            )
            == ["COMPLETED"],
            "LIBRARY_JOB_COMPLETED",
        )

    #
    # 3. Destination collision after plan:
    # source must remain.
    #
    with TemporaryDirectory() as tmp:
        root = Path(tmp)

        downloads = (
            root / "downloads"
        )

        library = (
            root / "jav"
        )

        db_path = (
            root / "db.sqlite3"
        )

        downloads.mkdir()
        library.mkdir()

        create_db(
            db_path
        )

        source = (
            downloads
            / "FNS-247 title.mp4"
        )

        write_fake(
            source,
            3333,
        )

        item = get_one_plan(
            downloads,
            library,
            db_path,
            "downloads",
        )

        final = (
            library
            / "FNS"
            / "FNS-247"
            / "FNS-247.mp4"
        )

        write_fake(
            final,
            9999,
        )

        failed = False

        try:
            apply_mod.apply_one(
                item,
                mode="downloads",
                source_root=downloads,
                library_root=library,
                db_path=db_path,
                apply_lock_path=
                    root / "apply.lock",
                writer_lock_path=
                    root / "writer.lock",
                stability_seconds=0,
            )

        except apply_mod.ApplyError:
            failed = True

        require(
            failed,
            "DEST_COLLISION_FAILS_CLOSED",
        )

        require(
            source.is_file(),
            "DEST_COLLISION_SOURCE_PRESERVED",
        )

        require(
            final.stat().st_size
            == 9999,
            "DEST_COLLISION_FINAL_NOT_OVERWRITTEN",
        )

        require(
            job_statuses(
                db_path
            ) == [],
            "DEST_COLLISION_NO_JOB_CREATED",
        )

    #
    # 4. Source changed after plan:
    # fail before publish.
    #
    with TemporaryDirectory() as tmp:
        root = Path(tmp)

        downloads = (
            root / "downloads"
        )

        library = (
            root / "jav"
        )

        db_path = (
            root / "db.sqlite3"
        )

        downloads.mkdir()
        library.mkdir()

        create_db(
            db_path
        )

        source = (
            downloads
            / "SNOS-334 title.mp4"
        )

        write_fake(
            source,
            4444,
        )

        item = get_one_plan(
            downloads,
            library,
            db_path,
            "downloads",
        )

        with source.open(
            "ab"
        ) as handle:
            handle.write(
                b"changed"
            )

        failed = False

        try:
            apply_mod.apply_one(
                item,
                mode="downloads",
                source_root=downloads,
                library_root=library,
                db_path=db_path,
                apply_lock_path=
                    root / "apply.lock",
                writer_lock_path=
                    root / "writer.lock",
                stability_seconds=0,
            )

        except apply_mod.ApplyError:
            failed = True

        require(
            failed,
            "SOURCE_CHANGE_FAILS_CLOSED",
        )

        require(
            source.is_file(),
            "SOURCE_CHANGE_SOURCE_PRESERVED",
        )

        require(
            not (
                library
                / "SNOS"
                / "SNOS-334"
                / "SNOS-334.mp4"
            ).exists(),
            "SOURCE_CHANGE_NO_FINAL",
        )

    #
    # 5. Cleanup failure:
    # destination and holding survive,
    # source also survives, job tells us
    # cleanup is pending.
    #
    with TemporaryDirectory() as tmp:
        root = Path(tmp)

        downloads = (
            root / "downloads"
        )

        library = (
            root / "jav"
        )

        db_path = (
            root / "db.sqlite3"
        )

        downloads.mkdir()
        library.mkdir()

        create_db(
            db_path
        )

        source = (
            downloads
            / "DLDSS-543 title.mp4"
        )

        write_fake(
            source,
            5555,
        )

        item = get_one_plan(
            downloads,
            library,
            db_path,
            "downloads",
        )

        original_cleanup = (
            apply_mod._cleanup_source
        )

        def fail_cleanup(_source):
            raise OSError(
                "simulated cleanup failure"
            )

        apply_mod._cleanup_source = (
            fail_cleanup
        )

        failed = False

        try:
            apply_mod.apply_one(
                item,
                mode="downloads",
                source_root=downloads,
                library_root=library,
                db_path=db_path,
                apply_lock_path=
                    root / "apply.lock",
                writer_lock_path=
                    root / "writer.lock",
                stability_seconds=0,
            )

        except OSError:
            failed = True

        finally:
            apply_mod._cleanup_source = (
                original_cleanup
            )

        final = (
            library
            / "DLDSS"
            / "DLDSS-543"
            / "DLDSS-543.mp4"
        )

        require(
            failed,
            "CLEANUP_FAILURE_REPORTED",
        )

        require(
            final.is_file(),
            "CLEANUP_FAILURE_FINAL_PRESERVED",
        )

        require(
            source.is_file(),
            "CLEANUP_FAILURE_SOURCE_PRESERVED",
        )

        require(
            job_statuses(
                db_path
            )
            == ["CLEANUP_PENDING"],
            "CLEANUP_FAILURE_JOB_STATE",
        )

        rows = holding_rows(
            db_path
        )

        require(
            len(rows) == 1,
            "CLEANUP_FAILURE_HOLDING_PRESERVED",
        )

    print(
        "STAGE7_SAFE_PUBLISH_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
