from __future__ import annotations

from pathlib import Path
import tempfile

from flask import Flask

from teddy_discovery_api import (
    create_discovery_blueprint,
)

from teddy_discovery_db import (
    connect,
    initialize,
)

from teddy_discovery_ui_data import (
    build_release_calendar_view,
)


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


def seed(
    db_path: Path,
):
    con = connect(
        db_path
    )

    try:
        initialize(
            con
        )

        dates = [
            "2026-08-29",
            "2026-08-28",
            "2026-08-27",
            "2026-08-25",
            "2026-08-24",
            "2026-08-22",
            "2026-08-21",
            "2026-08-20",
        ]

        rows = []

        rows.append((
            "TODAY-001",
            "Today title",
            dates[0],
        ))

        for index in range(
            1,
            74,
        ):
            rows.append((
                "BIG-"
                + str(index).zfill(3),
                "Big date "
                + str(index),
                dates[1],
            ))

        for date_value in dates[2:]:
            rows.append((
                "DATE-"
                + date_value.replace(
                    "-",
                    "",
                ),
                "Date "
                + date_value,
                date_value,
            ))

        rows.append((
            "FUTURE-001",
            "Future title",
            "2026-08-30",
        ))

        for dvd_id, title, release_date in rows:
            con.execute(
                """
                INSERT INTO titles (
                    dvd_id,
                    title,
                    release_date,
                    maker,
                    metadata_source,
                    first_seen_at,
                    last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dvd_id,
                    title,
                    release_date,
                    "TEST",
                    "test",
                    "2026-08-20T00:00:00+00:00",
                    "2026-08-29T00:00:00+00:00",
                ),
            )

        con.commit()

    finally:
        con.close()


def main():
    with tempfile.TemporaryDirectory(
        prefix=(
            "teddy-release-calendar-"
        )
    ) as temp_dir:

        db_path = (
            Path(temp_dir)
            / "discovery.sqlite3"
        )

        seed(
            db_path
        )

        con = connect(
            db_path
        )

        try:
            selected = (
                build_release_calendar_view(
                    con,
                    selected_date=
                        "2026-08-28",
                    today=
                        "2026-08-29",
                )
            )

            default = (
                build_release_calendar_view(
                    con,
                    today=
                        "2026-08-29",
                )
            )

        finally:
            con.close()

        require(
            len(
                selected[
                    "release_dates"
                ]
            ) == 7,
            "recent release dates "
            "must contain seven dates",
        )

        require(
            selected[
                "release_dates"
            ][0][
                "date"
            ] == "2026-08-29",
            "newest release date changed",
        )

        require(
            all(
                item[
                    "date"
                ] != "2026-08-30"
                for item
                in selected[
                    "release_dates"
                ]
            ),
            "future date leaked into "
            "released calendar",
        )

        require(
            selected[
                "selected_date"
            ] == "2026-08-28",
            "selected date mismatch",
        )

        require(
            selected[
                "item_count"
            ] == 73,
            "selected date was "
            "truncated",
        )

        require(
            len(
                selected[
                    "items"
                ]
            ) == 73,
            "selected item array "
            "was truncated",
        )

        require(
            default[
                "selected_date"
            ] == "2026-08-29",
            "default date must be "
            "newest released date",
        )

        require(
            default[
                "item_count"
            ] == 1,
            "default date item count "
            "changed",
        )

        app = Flask(
            "release-calendar-smoke"
        )

        app.register_blueprint(
            create_discovery_blueprint(
                db_path
            )
        )

        client = (
            app.test_client()
        )

        response = client.get(
            "/api/discovery/"
            "release-calendar"
            "?date=2026-08-28"
        )

        require(
            response.status_code == 200,
            "calendar API status "
            "must be 200",
        )

        payload = (
            response.get_json()
        )

        data = payload[
            "data"
        ]

        require(
            data[
                "item_count"
            ] == 73,
            "calendar API "
            "truncated selected date",
        )

        invalid = client.get(
            "/api/discovery/"
            "release-calendar"
            "?date=2026-08-20"
        )

        require(
            invalid.status_code == 400,
            "date outside recent seven "
            "must fail closed",
        )

        print(
            "RELEASE_CALENDAR_RECENT7=PASS"
        )

        print(
            "RELEASE_CALENDAR_FUTURE_HIDDEN=PASS"
        )

        print(
            "RELEASE_CALENDAR_SELECTED_73=PASS"
        )

        print(
            "RELEASE_CALENDAR_NO_50_CAP=PASS"
        )

        print(
            "RELEASE_CALENDAR_DEFAULT_DATE=PASS"
        )

        print(
            "RELEASE_CALENDAR_API=PASS"
        )

        print(
            "RELEASE_CALENDAR_INVALID_DATE="
            "PASS"
        )

        print(
            "REAL_NETWORK_REQUESTS=0"
        )

        print(
            "PRODUCTION_DB_WRITES=0"
        )

        print(
            "TEDDY_DISCOVERY_RELEASE_CALENDAR_"
            "SMOKE=PASS"
        )


if __name__ == "__main__":
    main()
