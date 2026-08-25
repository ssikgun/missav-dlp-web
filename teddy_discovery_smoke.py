from pathlib import Path
import sqlite3
import tempfile

from teddy_discovery_ids import parse_dvd_id
from teddy_discovery_import import import_inventory


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def scalar(db_path, sql, params=()):
    connection = sqlite3.connect(db_path)
    try:
        return connection.execute(
            sql,
            params,
        ).fetchone()[0]
    finally:
        connection.close()


def parser_smoke():
    cases = {
        "SNOS-334 title.mp4":
            "SNOS-334",

        "snos334 title.mp4":
            "SNOS-334",

        "[snos-334-uncensored-leak] SNOS-334 title.mp4":
            "SNOS-334",

        "FC2-PPV-4555371 title.mp4":
            "FC2-PPV-4555371",

        "[ebwh-350-uncensored-leak] "
        "EBWH-350 Kcup 173cm title.mp4":
            "EBWH-350",
    }

    for filename, expected in cases.items():
        result = parse_dvd_id(filename)
        actual = result.dvd_id if result else None

        require(
            actual == expected,
            f"parser mismatch: {filename!r}: "
            f"expected={expected!r} actual={actual!r}",
        )

    require(
        parse_dvd_id("random movie 173cm.mp4") is None,
        "title prose must not invent a DVD ID",
    )


def reconciliation_smoke():
    with tempfile.TemporaryDirectory(
        prefix="teddy-discovery-stage1-"
    ) as temp:
        base = Path(temp)
        root = base / "library"
        db = base / "inventory.sqlite3"

        root.mkdir()

        a = root / "SNOS-334 title.mp4"
        b = root / "SONE-978 title.mp4"
        c = root / "FC2-PPV-4555371 title.mp4"

        a.write_bytes(b"a")
        b.write_bytes(b"bb")
        c.write_bytes(b"ccc")

        # These must be ignored.
        (root / "notes.txt").write_text(
            "not media",
            encoding="utf-8",
        )

        synology = root / "@eaDir"
        synology.mkdir()
        (synology / "SONE-999 fake.mp4").write_bytes(
            b"ignored"
        )

        first = import_inventory(
            db_path=db,
            root=root,
            storage_root="jav",
        )

        require(
            first["video_files"] == 3,
            f"first scan expected 3 videos: {first}",
        )
        require(
            first["MATCHED"] == 3,
            f"first scan expected 3 matched: {first}",
        )

        require(
            scalar(
                db,
                "SELECT COUNT(*) FROM holdings"
            ) == 3,
            "first scan holdings count must be 3",
        )

        require(
            scalar(
                db,
                """
                SELECT COUNT(*)
                FROM holdings
                WHERE present = 1
                """
            ) == 3,
            "all holdings must initially be present",
        )

        # Simulate a manual NAS deletion.
        b.unlink()

        second = import_inventory(
            db_path=db,
            root=root,
            storage_root="jav",
        )

        require(
            second["video_files"] == 2,
            f"second scan expected 2 videos: {second}",
        )

        require(
            scalar(
                db,
                "SELECT COUNT(*) FROM holdings"
            ) == 3,
            "deleted holding must remain as history",
        )

        require(
            scalar(
                db,
                """
                SELECT COUNT(*)
                FROM holdings
                WHERE present = 1
                """
            ) == 2,
            "second scan must have 2 present holdings",
        )

        require(
            scalar(
                db,
                """
                SELECT COUNT(*)
                FROM holdings
                WHERE present = 0
                """
            ) == 1,
            "second scan must mark one holding absent",
        )

        require(
            scalar(
                db,
                """
                SELECT present
                FROM holdings
                WHERE dvd_id = 'SONE-978'
                """
            ) == 0,
            "SONE-978 must be absent after deletion",
        )

        # Simulate the same file being restored later.
        b.write_bytes(b"restored")

        third = import_inventory(
            db_path=db,
            root=root,
            storage_root="jav",
        )

        require(
            third["video_files"] == 3,
            f"third scan expected 3 videos: {third}",
        )

        require(
            scalar(
                db,
                """
                SELECT COUNT(*)
                FROM holdings
                WHERE present = 1
                """
            ) == 3,
            "restored holding must become present again",
        )

        require(
            scalar(
                db,
                """
                SELECT present
                FROM holdings
                WHERE dvd_id = 'SONE-978'
                """
            ) == 1,
            "SONE-978 must recover to present=1",
        )

        require(
            scalar(
                db,
                """
                SELECT COUNT(*)
                FROM inventory_runs
                WHERE status = 'COMPLETE'
                """
            ) == 3,
            "all three inventory runs must complete",
        )


def empty_scan_fail_closed_smoke():
    with tempfile.TemporaryDirectory(
        prefix="teddy-discovery-empty-"
    ) as temp:
        base = Path(temp)
        root = base / "library"
        db = base / "inventory.sqlite3"

        root.mkdir()

        first = root / "SNOS-334 title.mp4"
        second = root / "SONE-978 title.mp4"

        first.write_bytes(b"a")
        second.write_bytes(b"bb")

        initial = import_inventory(
            db_path=db,
            root=root,
            storage_root="jav",
        )

        require(
            initial["video_files"] == 2,
            "initial empty-scan smoke must see 2 files",
        )

        first.unlink()
        second.unlink()

        failed_closed = False

        try:
            import_inventory(
                db_path=db,
                root=root,
                storage_root="jav",
            )
        except RuntimeError as exc:
            require(
                "refusing empty inventory scan" in str(exc),
                f"unexpected empty-scan error: {exc}",
            )
            failed_closed = True

        require(
            failed_closed,
            "empty scan must fail closed",
        )

        require(
            scalar(
                db,
                """
                SELECT COUNT(*)
                FROM holdings
                WHERE present = 1
                """
            ) == 2,
            "failed empty scan must not mark holdings absent",
        )

        require(
            scalar(
                db,
                """
                SELECT COUNT(*)
                FROM inventory_runs
                WHERE status = 'FAILED'
                """
            ) == 1,
            "failed empty scan must be recorded",
        )

        # Explicit override is reserved for a genuinely emptied library.
        final = import_inventory(
            db_path=db,
            root=root,
            storage_root="jav",
            allow_empty=True,
        )

        require(
            final["video_files"] == 0,
            "explicit empty scan must report 0 files",
        )

        require(
            scalar(
                db,
                """
                SELECT COUNT(*)
                FROM holdings
                WHERE present = 1
                """
            ) == 0,
            "explicit empty scan must mark holdings absent",
        )

        require(
            scalar(
                db,
                """
                SELECT COUNT(*)
                FROM holdings
                WHERE present = 0
                """
            ) == 2,
            "explicit empty scan must retain absent history",
        )


def main():
    parser_smoke()
    reconciliation_smoke()
    empty_scan_fail_closed_smoke()

    print("PARSER_SMOKE=PASS")
    print("RECONCILIATION_SMOKE=PASS")
    print("EMPTY_SCAN_FAIL_CLOSED_SMOKE=PASS")
    print("STAGE1_SMOKE=PASS")


if __name__ == "__main__":
    main()
