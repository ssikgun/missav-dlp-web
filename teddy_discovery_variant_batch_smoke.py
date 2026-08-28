from __future__ import annotations

from pathlib import Path
import hashlib
import sqlite3
import tempfile

import teddy_discovery_db as db

from teddy_discovery_variant_batch import (
    build_variant_probe_plan,
)

from teddy_discovery_variants import (
    VARIANT_STANDARD,
    VARIANT_UNCENSORED,
    persist_title_variant,
)


NOW = (
    "2026-08-28T12:00:00+00:00"
)


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


def sha256(
    path: Path,
) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def add_title(
    connection,
    dvd_id,
    release_date,
):
    connection.execute(
        """
        INSERT INTO titles(
            dvd_id,
            title,
            release_date,
            first_seen_at,
            last_seen_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            dvd_id,
            dvd_id + " test",
            release_date,
            (
                "2026-08-20"
                "T00:00:00+00:00"
            ),
            (
                "2026-08-28"
                "T00:00:00+00:00"
            ),
        ),
    )


def add_availability(
    connection,
    dvd_id,
    status,
):
    connection.execute(
        """
        INSERT INTO availability(
            dvd_id,
            source,
            status,
            page_url,
            last_checked_at,
            next_check_at,
            fail_count
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            dvd_id,
            "missav",
            status,
            (
                "https://missav123.com/"
                "ko/"
                + dvd_id.lower()
            ),
            (
                "2026-08-28"
                "T11:00:00+00:00"
            ),
            (
                "2026-08-29"
                "T11:00:00+00:00"
            ),
            0,
        ),
    )


def add_standard_watermark(
    connection,
    dvd_id,
    checked_at,
):
    persist_title_variant(
        connection,
        {
            "dvd_id":
                dvd_id,

            "source":
                "missav",

            "variant_kind":
                VARIANT_STANDARD,

            "variant_slug":
                dvd_id.lower(),

            "page_url": (
                "https://missav123.com/"
                "ko/"
                + dvd_id.lower()
            ),

            "confirmed":
                1,
        },
        observed_at=
            checked_at,
        checked_at=
            checked_at,
    )


def add_uncensored(
    connection,
    dvd_id,
):
    slug = (
        dvd_id.lower()
        + "-uncensored-leak"
    )

    persist_title_variant(
        connection,
        {
            "dvd_id":
                dvd_id,

            "source":
                "missav",

            "variant_kind":
                VARIANT_UNCENSORED,

            "variant_slug":
                slug,

            "page_url": (
                "https://missav123.com/"
                "ko/"
                + slug
            ),

            "confirmed":
                1,
        },
        observed_at=NOW,
        checked_at=NOW,
    )


def main():
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-variant-batch-"
    ) as temp:

        path = (
            Path(temp)
            / "discovery.sqlite3"
        )

        connection = db.connect(
            path
        )

        try:
            db.initialize(
                connection
            )

            fixtures = (
                (
                    "TOD-001",
                    "2026-08-28",
                    "FOUND",
                ),
                (
                    "REC-002",
                    "2026-08-27",
                    "FOUND",
                ),
                (
                    "FUT-003",
                    "2026-08-30",
                    "FOUND",
                ),
                (
                    "OLD-004",
                    "2026-07-01",
                    "FOUND",
                ),
                (
                    "FRS-005",
                    "2026-08-26",
                    "FOUND",
                ),
                (
                    "UNC-006",
                    "2026-08-28",
                    "FOUND",
                ),
                (
                    "NFA-007",
                    "2026-08-28",
                    "NOT_FOUND",
                ),
                (
                    "FAR-008",
                    "2026-09-15",
                    "FOUND",
                ),
                (
                    "UNK-009",
                    None,
                    "FOUND",
                ),
            )

            for (
                dvd_id,
                release_date,
                status,
            ) in fixtures:
                add_title(
                    connection,
                    dvd_id,
                    release_date,
                )

                add_availability(
                    connection,
                    dvd_id,
                    status,
                )

            connection.commit()

            add_standard_watermark(
                connection,
                "OLD-004",
                (
                    "2026-08-27"
                    "T00:00:00+00:00"
                ),
            )

            add_standard_watermark(
                connection,
                "FRS-005",
                (
                    "2026-08-28"
                    "T10:00:00+00:00"
                ),
            )

            add_uncensored(
                connection,
                "UNC-006",
            )

            integrity = connection.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]

        finally:
            connection.close()

        require(
            integrity == "ok",
            "fixture DB integrity failed",
        )

        before = sha256(
            path
        )

        connection = sqlite3.connect(
            "file:"
            + str(path)
            + "?mode=ro",
            uri=True,
        )

        connection.row_factory = (
            sqlite3.Row
        )

        try:
            plan = (
                build_variant_probe_plan(
                    connection,
                    now=NOW,
                    max_items=10,
                    recheck_after_hours=6,
                    near_future_days=7,
                )
            )

            limited = (
                build_variant_probe_plan(
                    connection,
                    now=NOW,
                    max_items=2,
                    recheck_after_hours=6,
                    near_future_days=7,
                )
            )

            long_recheck = (
                build_variant_probe_plan(
                    connection,
                    now=NOW,
                    max_items=10,
                    recheck_after_hours=48,
                    near_future_days=7,
                )
            )

        finally:
            connection.close()

        after = sha256(
            path
        )

        selected_ids = [
            item[
                "dvd_id"
            ]
            for item
            in plan[
                "selected"
            ]
        ]

        require(
            selected_ids
            == [
                "TOD-001",
                "REC-002",
                "FUT-003",
                "UNK-009",
                "OLD-004",
            ],
            (
                "variant probe priority "
                "order mismatch: "
                + repr(
                    selected_ids
                )
            ),
        )

        require(
            [
                item[
                    "priority_name"
                ]
                for item
                in plan[
                    "selected"
                ][:3]
            ]
            == [
                "today",
                "recent7",
                "near-future",
            ],
            "release priority changed",
        )

        require(
            plan[
                "missav_found_count"
            ]
            == 8,
            "MissAV FOUND universe changed",
        )

        require(
            plan[
                "uncensored_confirmed_count"
            ]
            == 1,
            (
                "confirmed uncensored "
                "skip count changed"
            ),
        )

        require(
            plan[
                "fresh_watermark_count"
            ]
            == 1,
            "fresh watermark skip changed",
        )

        require(
            plan[
                "far_future_count"
            ]
            == 1,
            "far future skip changed",
        )

        require(
            plan[
                "due_count"
            ]
            == 5,
            "due count changed",
        )

        require(
            plan[
                "selected_count"
            ]
            == 5,
            "selected count changed",
        )

        require(
            limited[
                "selected_count"
            ]
            == 2,
            "batch ceiling changed",
        )

        require(
            [
                item[
                    "dvd_id"
                ]
                for item
                in limited[
                    "selected"
                ]
            ]
            == [
                "TOD-001",
                "REC-002",
            ],
            "bounded selection changed",
        )

        require(
            "FRS-005"
            not in selected_ids,
            (
                "fresh watermark title "
                "was selected"
            ),
        )

        require(
            "UNC-006"
            not in selected_ids,
            (
                "confirmed uncensored title "
                "was selected"
            ),
        )

        require(
            "NFA-007"
            not in selected_ids,
            (
                "MissAV NOT_FOUND title "
                "was selected"
            ),
        )

        require(
            "FAR-008"
            not in selected_ids,
            (
                "far-future title "
                "was selected"
            ),
        )

        long_ids = [
            item[
                "dvd_id"
            ]
            for item
            in long_recheck[
                "selected"
            ]
        ]

        require(
            "OLD-004"
            not in long_ids,
            (
                "48-hour recheck policy "
                "ignored watermark age"
            ),
        )

        for invalid_max in (
            0,
            -1,
            101,
            True,
            "10",
        ):
            try:
                build_variant_probe_plan(
                    sqlite3.connect(
                        ":memory:"
                    ),
                    now=NOW,
                    max_items=
                        invalid_max,
                    recheck_after_hours=6,
                )

            except ValueError:
                pass

            else:
                raise RuntimeError(
                    (
                        "invalid max_items "
                        "must fail closed"
                    )
                )

        require(
            after == before,
            "planner changed DB bytes",
        )

        print(
            "VARIANT_PROBE_TODAY_FIRST_SMOKE=PASS"
        )

        print(
            "VARIANT_PROBE_RECENT7_SECOND_SMOKE=PASS"
        )

        print(
            "VARIANT_PROBE_NEAR_FUTURE_THIRD_SMOKE=PASS"
        )

        print(
            "VARIANT_PROBE_FRESH_WATERMARK_SKIP_SMOKE=PASS"
        )

        print(
            "VARIANT_PROBE_CONFIRMED_UNCENSORED_SKIP_SMOKE=PASS"
        )

        print(
            "VARIANT_PROBE_MISSAV_FOUND_ONLY_SMOKE=PASS"
        )

        print(
            "VARIANT_PROBE_FAR_FUTURE_SKIP_SMOKE=PASS"
        )

        print(
            "VARIANT_PROBE_RECHECK_INTERVAL_SMOKE=PASS"
        )

        print(
            "VARIANT_PROBE_BATCH_LIMIT_SMOKE=PASS"
        )

        print(
            "VARIANT_PROBE_DB_BYTE_UNCHANGED_SMOKE=PASS"
        )

        print(
            "TEDDY_DISCOVERY_VARIANT_BATCH_OFFLINE_SMOKE=PASS"
        )


if __name__ == "__main__":
    main()
