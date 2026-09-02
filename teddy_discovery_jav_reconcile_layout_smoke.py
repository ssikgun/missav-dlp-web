from pathlib import Path
import inspect
import os
import sqlite3
import stat
import tempfile

from teddy_discovery_db import connect, initialize
from teddy_discovery_media_publish import (
    LIBRARY_SIDECAR_FILENAMES,
    POSTER_FILENAMES,
    is_library_sidecar,
)
from teddy_discovery_organizer import canonical_destination

import teddy_discovery_jav_reconcile as reconcile_mod
import teddy_discovery_jav_reconcile_remote_smoke as remote_smoke


def require(value, message):
    if not value:
        raise RuntimeError(message)


def create_db(path):
    db = connect(path)
    initialize(db)
    db.close()


def scalar(path, sql, params=()):
    db = sqlite3.connect(path)
    try:
        return db.execute(sql, params).fetchone()[0]
    finally:
        db.close()


def make_video(root, dvd_id, suffix=".mp4", data=b"video"):
    relative = canonical_destination(
        dvd_id,
        suffix,
    ).as_posix()
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path, relative


def categories(report):
    return {
        finding.category
        for finding in report.findings
    }


def apply_with_locks(db_path, root):
    base = Path(db_path).parent
    return reconcile_mod.apply_reconciliation(
        db_path,
        root,
        operation_lock_path=base / "operation.lock",
        writer_lock_path=base / "writer.lock",
    )


def test_live_layout_and_sidecars():
    sidecar_sets = (
        ("ADN-785.nfo",),
        ("movie.nfo",),
        ("poster.jpg",),
        ("poster.webp",),
        (
            "ADN-785.nfo",
            "movie.nfo",
            "poster.jpg",
            "poster.webp",
        ),
    )

    require(
        POSTER_FILENAMES == {
            "poster.jpg",
            "poster.png",
            "poster.webp",
        },
        "reconciliation poster policy drifted",
    )
    require(
        LIBRARY_SIDECAR_FILENAMES == {
            "movie.nfo",
            "poster.jpg",
            "poster.png",
            "poster.webp",
        },
        "reconciliation sidecar policy drifted",
    )
    require(
        is_library_sidecar("ADN-785.nfo", "ADN-785"),
        "DVD-ID NFO was not accepted as a sidecar",
    )

    for index, sidecars in enumerate(sidecar_sets):
        with tempfile.TemporaryDirectory(
            prefix="teddy-jav-layout-"
        ) as temp:
            base = Path(temp)
            root = base / "JAV"
            db_path = base / "discovery.sqlite3"
            root.mkdir()
            create_db(db_path)

            _, relative = make_video(
                root,
                "ADN-785",
            )
            dvd_dir = root / "ADN" / "ADN-785"
            for filename in sidecars:
                (dvd_dir / filename).write_text(
                    "sidecar",
                    encoding="utf-8",
                )

            # Synology metadata is bounded-scan noise and must not be opened.
            root_ea_dir = root / "@eaDir" / "payload" / "deep"
            root_ea_dir.mkdir(parents=True)
            (root_ea_dir / "BAD-001.mp4").write_bytes(
                b"must not be traversed"
            )
            dvd_ea_dir = dvd_dir / "@eaDir" / "payload" / "deep"
            dvd_ea_dir.mkdir(parents=True)
            (dvd_ea_dir / "BAD-002.mp4").write_bytes(
                b"must not be traversed"
            )

            seen_scandir_paths = []
            original_scandir = reconcile_mod.os.scandir

            def tracking_scandir(path):
                seen_scandir_paths.append(Path(path))
                return original_scandir(path)

            reconcile_mod.os.scandir = tracking_scandir
            try:
                report = reconcile_mod.reconcile(
                    db_path,
                    root,
                )
            finally:
                reconcile_mod.os.scandir = original_scandir

            require(
                report.scan_complete and report.apply_eligible,
                "live sidecar layout was not clean: "
                + str(index),
            )
            require(
                len(report.canonical_present_files) == 1,
                "sidecars changed canonical media count",
            )
            require(
                all(
                    "@eaDir" not in path.parts
                    for path in seen_scandir_paths
                ),
                "scanner traversed @eaDir",
            )
            require(
                set(seen_scandir_paths) == {
                    root,
                    root / "ADN",
                    dvd_dir,
                },
                "scanner crossed the bounded layout boundary",
            )

            apply_with_locks(
                db_path,
                root,
            )
            require(
                scalar(
                    db_path,
                    "SELECT COUNT(*) FROM holdings",
                ) == 1,
                "sidecar was imported as a holding",
            )
            require(
                scalar(
                    db_path,
                    "SELECT relative_path FROM holdings",
                ) == relative,
                "canonical media path was not imported",
            )


def test_hold_layout_boundaries():
    scenarios = (
        ("sidecar-only", "sidecar"),
        ("unknown-file", "unknown"),
        ("nested-directory", "nested"),
        ("wrong-name-video", "wrong-name"),
        ("duplicate-video", "duplicate"),
        ("symlink", "symlink"),
        ("other-metadata-name", "other-metadata"),
    )

    for name, scenario in scenarios:
        with tempfile.TemporaryDirectory(
            prefix="teddy-jav-layout-hold-"
        ) as temp:
            base = Path(temp)
            root = base / "JAV"
            db_path = base / "discovery.sqlite3"
            root.mkdir()
            create_db(db_path)

            if scenario == "sidecar":
                dvd_dir = root / "SIDE" / "SIDE-001"
                dvd_dir.mkdir(parents=True)
                (dvd_dir / "movie.nfo").write_text(
                    "sidecar",
                    encoding="utf-8",
                )
                (dvd_dir / "poster.jpg").write_bytes(b"poster")
            elif scenario == "unknown":
                _, _ = make_video(root, "EXTRA-001")
                (root / "EXTRA" / "EXTRA-001" / "README.txt").write_text(
                    "unknown",
                    encoding="utf-8",
                )
            elif scenario == "nested":
                make_video(root, "NEST-001")
                nested = root / "NEST" / "NEST-001" / "nested"
                nested.mkdir()
                (nested / "NEST-001.mp4").write_bytes(b"nested")
            elif scenario == "wrong-name":
                dvd_dir = root / "WRONG" / "WRONG-001"
                dvd_dir.mkdir(parents=True)
                (dvd_dir / "OTHER-001.mp4").write_bytes(b"wrong")
            elif scenario == "duplicate":
                make_video(root, "DUP-001", ".mp4")
                make_video(root, "DUP-001", ".mkv")
            elif scenario == "symlink":
                target = base / "target.mp4"
                target.write_bytes(b"target")
                dvd_dir = root / "SYM" / "SYM-001"
                dvd_dir.mkdir(parents=True)
                os.symlink(target, dvd_dir / "SYM-001.mp4")
            else:
                other = root / "@something-else" / "BAD-001"
                other.mkdir(parents=True)
                (other / "BAD-001.mp4").write_bytes(b"not canonical")

            report = reconcile_mod.reconcile(
                db_path,
                root,
            )
            require(
                not report.apply_eligible,
                name + " was unexpectedly apply-eligible",
            )
            require(
                categories(report) & {
                    "UNEXPECTED_LAYOUT",
                    "SYMLINK",
                    "DUPLICATE_PHYSICAL_MEDIA",
                    "UNMATCHED_DVD_ID",
                },
                name + " did not produce a HOLD finding",
            )

            if scenario == "sidecar":
                require(
                    "UNEXPECTED_LAYOUT" in categories(report),
                    "sidecar-only directory was not held",
                )


def test_fail_closed_and_no_recursive_source():
    with tempfile.TemporaryDirectory(
        prefix="teddy-jav-layout-incomplete-"
    ) as temp:
        base = Path(temp)
        root = base / "JAV"
        db_path = base / "discovery.sqlite3"
        root.mkdir()
        create_db(db_path)

        # A partial scan must not make the existing holding absent.
        db = sqlite3.connect(db_path)
        db.execute(
            """
            INSERT INTO holdings(
                storage_root, relative_path, dvd_id, parse_status,
                parse_method, parse_candidates_json, size_bytes,
                mtime_ns, discovered_by, present, first_seen_at,
                last_seen_at, last_seen_run_id
            ) VALUES (
                'jav', 'OLD/OLD-001/OLD-001.mp4', 'OLD-001', 'MATCHED',
                'smoke', '[\"OLD-001\"]', 1, 1, 'smoke', 1,
                'now', 'now', NULL
            )
            """
        )
        db.commit()
        db.close()

        (root / "NEW" / "NEW-001" / "nested").mkdir(parents=True)
        before_runs = scalar(
            db_path,
            "SELECT COUNT(*) FROM inventory_runs",
        )
        try:
            apply_with_locks(
                db_path,
                root,
            )
        except reconcile_mod.ReconciliationUnsafe:
            pass
        else:
            raise RuntimeError(
                "incomplete layout unexpectedly applied"
            )

        require(
            scalar(
                db_path,
                "SELECT present FROM holdings WHERE dvd_id = 'OLD-001'",
            ) == 1,
            "incomplete scan marked an old holding absent",
        )
        require(
            scalar(
                db_path,
                "SELECT COUNT(*) FROM inventory_runs",
            ) == before_runs,
            "incomplete scan wrote an inventory run",
        )

    source = inspect.getsource(reconcile_mod.scan_bounded)
    for forbidden in (
        "rglob(",
        "os.walk(",
        "find(",
        "du(",
    ):
        require(
            forbidden not in source,
            "bounded scanner contains recursive traversal: " + forbidden,
        )


def test_remote_live_layout_without_eadir_traversal():
    tree = {}
    relative = remote_smoke.add_video(
        tree,
        "AKDL-312",
    )
    parent = "AKDL/AKDL-312"
    remote_smoke._add_file(
        tree,
        parent,
        "movie.nfo",
        7,
        7000,
    )
    remote_smoke._add_file(
        tree,
        parent,
        "poster.webp",
        7,
        7000,
    )
    remote_smoke._add_dir(tree, ".", "@eaDir")
    remote_smoke._add_dir(tree, "@eaDir", "payload")
    remote_smoke._add_dir(tree, parent, "@eaDir")
    remote_smoke._add_dir(tree, parent + "/@eaDir", "payload")

    with tempfile.TemporaryDirectory(
        prefix="teddy-jav-remote-layout-"
    ) as temp:
        db_path = Path(temp) / "discovery.sqlite3"
        create_db(db_path)
        runner = remote_smoke.FakeRemoteRunner(tree)
        ssh = remote_smoke.make_ssh(runner)
        report = reconcile_mod.reconcile_remote(
            db_path,
            ssh,
            library_root="/remote/JAV",
        )

        require(
            report.scan_complete and report.apply_eligible,
            "remote live layout was not clean",
        )
        require(
            [
                row["relative_path"]
                for row in report.canonical_present_files
            ] == [relative],
            "remote sidecars changed canonical media records",
        )
        require(
            all(
                "@eaDir" not in path
                for path in runner.relative_calls
            ),
            "remote scanner traversed @eaDir",
        )


def main():
    test_live_layout_and_sidecars()
    test_hold_layout_boundaries()
    test_fail_closed_and_no_recursive_source()
    test_remote_live_layout_without_eadir_traversal()

    print("JAV_RECONCILIATION_LAYOUT_SIDECAR=PASS")
    print("JAV_RECONCILIATION_LAYOUT_EADIR=PASS")
    print("JAV_RECONCILIATION_LAYOUT_HOLD=PASS")
    print("JAV_RECONCILIATION_LAYOUT_SMOKE=PASS")


if __name__ == "__main__":
    main()
