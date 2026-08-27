from pathlib import Path
import hashlib
import sqlite3
import tempfile

from flask import Flask, jsonify

import teddy_discovery_download_api as api

from teddy_discovery_availability import (
    AVAILABILITY_STATUSES,
    SOURCE_123AV,
    SOURCE_MISSAV,
    STATUS_FOUND,
    canonical_page_url,
)


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha256(path):
    return hashlib.sha256(
        Path(path).read_bytes()
    ).hexdigest()


class Core:
    def __init__(self):
        self.settings = {
            "discovery_download_preference":
                "auto",
        }


def create_db(path):
    connection = sqlite3.connect(path)

    try:
        connection.executescript(
            """
            CREATE TABLE titles (
                dvd_id TEXT PRIMARY KEY
            );

            CREATE TABLE availability (
                dvd_id TEXT NOT NULL,
                source TEXT NOT NULL,
                status TEXT NOT NULL
            );
            """
        )

        non_found = [
            value
            for value in AVAILABILITY_STATUSES
            if value != STATUS_FOUND
        ]

        require(
            len(non_found) >= 2,
            "availability non-FOUND statuses changed",
        )

        rows = (
            ("MIS-101",),
            ("AVX-102",),
            ("BTH-103",),
            ("NON-104",),
        )

        connection.executemany(
            "INSERT INTO titles(dvd_id) VALUES (?)",
            rows,
        )

        connection.executemany(
            """
            INSERT INTO availability(
                dvd_id,
                source,
                status
            )
            VALUES (?, ?, ?)
            """,
            (
                (
                    "MIS-101",
                    SOURCE_MISSAV,
                    STATUS_FOUND,
                ),
                (
                    "MIS-101",
                    SOURCE_123AV,
                    non_found[0],
                ),
                (
                    "AVX-102",
                    SOURCE_MISSAV,
                    non_found[0],
                ),
                (
                    "AVX-102",
                    SOURCE_123AV,
                    STATUS_FOUND,
                ),
                (
                    "BTH-103",
                    SOURCE_MISSAV,
                    STATUS_FOUND,
                ),
                (
                    "BTH-103",
                    SOURCE_123AV,
                    STATUS_FOUND,
                ),
                (
                    "NON-104",
                    SOURCE_MISSAV,
                    non_found[0],
                ),
                (
                    "NON-104",
                    SOURCE_123AV,
                    non_found[1],
                ),
            ),
        )

        connection.commit()

    finally:
        connection.close()


def main():
    with tempfile.TemporaryDirectory(
        prefix="teddy-discovery-download-"
    ) as temp:
        db_path = Path(temp) / "discovery.sqlite3"

        create_db(db_path)

        before = sha256(db_path)

        core = Core()
        app = Flask(
            "teddy-discovery-download-smoke"
        )

        app.register_blueprint(
            api.create_discovery_download_blueprint(
                core,
                db_path,
            )
        )

        calls = []

        original_guard = (
            api.teddy_duplicates.guarded_enqueue
        )
        original_enqueue = (
            api.teddy_routing.enqueue_download
        )

        def fake_enqueue(
            received_core,
            url,
            override,
        ):
            calls.append(
                ("enqueue", url, override)
            )

            return jsonify({
                "status": "success",
                "task_id": "smoke-task",
            })

        def fake_guard(
            received_core,
            url,
            creator,
        ):
            calls.append(
                ("guard", url)
            )

            return creator()

        api.teddy_duplicates.guarded_enqueue = (
            fake_guard
        )
        api.teddy_routing.enqueue_download = (
            fake_enqueue
        )

        try:
            client = app.test_client()

            require(
                client.get(
                    "/api/discovery/download"
                ).status_code == 405,
                "download route must be POST-only",
            )

            require(
                client.post(
                    "/api/discovery/download",
                    data="not-json",
                ).status_code == 400,
                "non-JSON request must fail closed",
            )

            require(
                client.post(
                    "/api/discovery/download",
                    json={
                        "dvd_id": "BTH-103",
                        "page_url": "ignored",
                    },
                ).status_code == 400,
                "extra JSON key must fail closed",
            )

            require(
                client.post(
                    "/api/discovery/download",
                    json={"dvd_id": "???"},
                ).status_code == 400,
                "invalid DVD ID must return 400",
            )

            require(
                client.post(
                    "/api/discovery/download",
                    json={"dvd_id": "UNKNOWN-404"},
                ).status_code == 404,
                "unknown title must return 404",
            )

            require(
                client.post(
                    "/api/discovery/download",
                    json={"dvd_id": "NON-104"},
                ).status_code == 409,
                "no FOUND source must return 409",
            )

            cases = (
                (
                    "MIS-101",
                    SOURCE_123AV,
                    SOURCE_MISSAV,
                ),
                (
                    "AVX-102",
                    SOURCE_MISSAV,
                    SOURCE_123AV,
                ),
                (
                    "BTH-103",
                    "auto",
                    SOURCE_MISSAV,
                ),
                (
                    "BTH-103",
                    SOURCE_MISSAV,
                    SOURCE_MISSAV,
                ),
                (
                    "BTH-103",
                    SOURCE_123AV,
                    SOURCE_123AV,
                ),
            )

            for dvd_id, preference, expected in cases:
                calls.clear()

                core.settings[
                    "discovery_download_preference"
                ] = preference

                response = client.post(
                    "/api/discovery/download",
                    json={"dvd_id": dvd_id},
                )

                require(
                    response.status_code == 200,
                    "valid download action failed: "
                    + dvd_id,
                )

                expected_url = canonical_page_url(
                    expected,
                    dvd_id,
                )

                require(
                    calls == [
                        ("guard", expected_url),
                        (
                            "enqueue",
                            expected_url,
                            "auto",
                        ),
                    ],
                    "download boundary changed: "
                    + dvd_id
                    + " / "
                    + preference,
                )

            calls.clear()

            def duplicate_guard(
                received_core,
                url,
                creator,
            ):
                calls.append(
                    ("duplicate", url)
                )

                return jsonify({
                    "status": "duplicate",
                    "task_id": "existing",
                }), 409

            api.teddy_duplicates.guarded_enqueue = (
                duplicate_guard
            )

            response = client.post(
                "/api/discovery/download",
                json={"dvd_id": "BTH-103"},
            )

            require(
                response.status_code == 409,
                "duplicate response changed",
            )

            require(
                not any(
                    call[0] == "enqueue"
                    for call in calls
                ),
                "duplicate path reached enqueue",
            )

        finally:
            api.teddy_duplicates.guarded_enqueue = (
                original_guard
            )
            api.teddy_routing.enqueue_download = (
                original_enqueue
            )

        after = sha256(db_path)

        require(
            before == after,
            "download API changed DB bytes",
        )

        print(
            "DISCOVERY_DOWNLOAD_POST_ONLY_SMOKE=PASS"
        )
        print(
            "DISCOVERY_DOWNLOAD_STRICT_PAYLOAD_SMOKE=PASS"
        )
        print(
            "DISCOVERY_DOWNLOAD_FOUND_ONLY_SMOKE=PASS"
        )
        print(
            "DISCOVERY_DOWNLOAD_SOURCE_PREFERENCE_SMOKE=PASS"
        )
        print(
            "DISCOVERY_DOWNLOAD_FRONTDOOR_BOUNDARY_SMOKE=PASS"
        )
        print(
            "DISCOVERY_DOWNLOAD_DUPLICATE_BOUNDARY_SMOKE=PASS"
        )
        print(
            "DISCOVERY_DOWNLOAD_DB_BYTE_UNCHANGED_SMOKE=PASS"
        )
        print(
            "TEDDY_DISCOVERY_DOWNLOAD_API_OFFLINE_SMOKE=PASS"
        )


if __name__ == "__main__":
    main()
