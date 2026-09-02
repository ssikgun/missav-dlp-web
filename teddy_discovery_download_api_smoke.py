from pathlib import Path
import hashlib
import tempfile

from flask import (
    Flask,
    jsonify,
)

import teddy_discovery_db as db
import teddy_discovery_download_api as api

from teddy_discovery_variants import (
    persist_title_variant,
)


NOW = "2026-08-28T00:00:00+00:00"


def require(
    value,
    message,
):
    if not value:
        raise RuntimeError(
            message
        )


def sha256(
    path,
):
    return hashlib.sha256(
        Path(path).read_bytes()
    ).hexdigest()


class Core:
    def __init__(
        self,
    ):
        self.settings = {
            "discovery_download_preference":
                "123av",
        }

        self.tasks = {}

        self.jsonify = jsonify


def add_title(
    connection,
    dvd_id,
):
    connection.execute(
        """
        INSERT INTO titles(
            dvd_id,
            title,
            first_seen_at,
            last_seen_at
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            dvd_id,
            dvd_id + " test",
            NOW,
            NOW,
        ),
    )


def add_availability(
    connection,
    dvd_id,
    source,
    status,
):
    connection.execute(
        """
        INSERT INTO availability(
            dvd_id,
            source,
            status,
            last_checked_at,
            next_check_at,
            fail_count
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            dvd_id,
            source,
            status,
            NOW,
            NOW,
            0,
        ),
    )


def create_db(
    path,
):
    connection = db.connect(
        path
    )

    try:
        db.initialize(
            connection
        )

        for dvd_id in (
            "SW-893",
            "BTH-103",
            "AVX-102",
            "NON-104",
            "BAD-105",
            "OWN-106",
        ):
            add_title(
                connection,
                dvd_id,
            )

        add_availability(
            connection,
            "SW-893",
            "missav",
            "FOUND",
        )

        add_availability(
            connection,
            "SW-893",
            "123av",
            "FOUND",
        )

        add_availability(
            connection,
            "BTH-103",
            "missav",
            "FOUND",
        )

        add_availability(
            connection,
            "BTH-103",
            "123av",
            "FOUND",
        )

        add_availability(
            connection,
            "AVX-102",
            "missav",
            "NOT_FOUND",
        )

        add_availability(
            connection,
            "AVX-102",
            "123av",
            "FOUND",
        )

        add_availability(
            connection,
            "NON-104",
            "missav",
            "NOT_FOUND",
        )

        add_availability(
            connection,
            "NON-104",
            "123av",
            "UNKNOWN",
        )

        add_availability(
            connection,
            "BAD-105",
            "missav",
            "FOUND",
        )

        add_availability(
            connection,
            "OWN-106",
            "missav",
            "FOUND",
        )

        connection.execute(
            """
            INSERT INTO holdings(
                storage_root, relative_path, dvd_id,
                parse_status, parse_method,
                parse_candidates_json, size_bytes,
                mtime_ns, discovered_by, present,
                first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "/library", "OWN-106.mp4", "OWN-106",
                "MATCHED", "smoke", "[]", 1, 1,
                "smoke", 1, NOW, NOW,
            ),
        )

        connection.commit()

        persist_title_variant(
            connection,
            {
                "dvd_id":
                    "SW-893",

                "source":
                    "missav",

                "variant_kind":
                    "uncensored",

                "variant_slug":
                    "sw-893-uncensored-leak",

                "page_url":
                    (
                        "https://missav123.com/"
                        "ko/"
                        "sw-893-uncensored-leak"
                    ),

                "confirmed":
                    1,
            },
            observed_at=NOW,
            checked_at=NOW,
        )

        connection.execute(
            """
            INSERT INTO title_variants(
                dvd_id,
                source,
                variant_kind,
                variant_slug,
                page_url,
                confirmed,
                first_seen_at,
                last_seen_at,
                last_checked_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "BAD-105",
                "missav",
                "uncensored",
                "bad-105-uncensored-leak",
                (
                    "https://example.com/"
                    "ko/"
                    "bad-105-uncensored-leak"
                ),
                1,
                NOW,
                NOW,
                NOW,
            ),
        )

        connection.commit()

    finally:
        connection.close()


def main():
    with tempfile.TemporaryDirectory(
        prefix="teddy-discovery-download-r2-"
    ) as temp:

        db_path = (
            Path(temp)
            / "discovery.sqlite3"
        )

        create_db(
            db_path
        )

        before = sha256(
            db_path
        )

        core = Core()

        app = Flask(
            "teddy-discovery-download-r2-smoke"
        )

        app.register_blueprint(
            api.create_discovery_download_blueprint(
                core,
                db_path,
            )
        )

        calls = []

        original_enqueue = (
            api.teddy_routing.enqueue_download
        )

        def fake_enqueue(
            received_core,
            url,
            override,
        ):
            calls.append(
                (
                    "enqueue",
                    url,
                    override,
                )
            )

            return jsonify({
                "status": "success",
                "task_id": "smoke-task",
            })

        api.teddy_routing.enqueue_download = (
            fake_enqueue
        )

        try:
            client = app.test_client()

            require(
                client.get(
                    "/api/discovery/download"
                ).status_code
                == 405,
                "download route must remain POST-only",
            )

            require(
                client.post(
                    "/api/discovery/download",
                    data="not-json",
                ).status_code
                == 400,
                "non-JSON must fail closed",
            )

            require(
                client.post(
                    "/api/discovery/download",
                    json={
                        "dvd_id": "SW-893",
                        "page_url": "forbidden",
                    },
                ).status_code
                == 400,
                "browser-controlled URL was accepted",
            )

            require(
                client.post(
                    "/api/discovery/download",
                    json={
                        "dvd_id":
                            "sw-893-uncensored-leak",
                    },
                ).status_code
                == 400,
                "variant slug accepted as DVD ID",
            )

            require(
                client.post(
                    "/api/discovery/download",
                    json={
                        "dvd_id":
                            "UNKNOWN-404",
                    },
                ).status_code
                == 404,
                "missing title must return 404",
            )

            require(
                client.post(
                    "/api/discovery/download",
                    json={
                        "dvd_id":
                            "NON-104",
                    },
                ).status_code
                == 409,
                "no target must return 409",
            )

            require(
                client.post(
                    "/api/discovery/download",
                    json={
                        "dvd_id":
                            "BAD-105",
                    },
                ).status_code
                == 503,
                "bad stored variant must fail closed",
            )

            calls.clear()
            core.tasks = {
                "already-active": {
                    "status": "대기 중",
                    "url": "https://missav123.com/ko/own-106",
                },
            }
            owned_response = client.post(
                "/api/discovery/download",
                json={"dvd_id": "OWN-106"},
            )
            require(
                owned_response.status_code == 409
                and owned_response.get_json().get("status") == "owned"
                and calls == [],
                "owned Discovery item was not blocked before duplicate/enqueue",
            )
            print("DISCOVERY_DOWNLOAD_OWNED_PRIORITY_SMOKE=PASS")

            cases = (
                (
                    "SW-893",
                    (
                        "https://missav123.com/"
                        "ko/"
                        "sw-893-uncensored-leak"
                    ),
                ),
                (
                    "BTH-103",
                    (
                        "https://missav123.com/"
                        "ko/bth-103"
                    ),
                ),
                (
                    "AVX-102",
                    (
                        "https://123av.com/"
                        "ko/v/avx-102"
                    ),
                ),
            )

            for dvd_id, expected_url in cases:
                calls.clear()
                core.tasks = {}

                response = client.post(
                    "/api/discovery/download",
                    json={
                        "dvd_id":
                            dvd_id,
                    },
                )

                require(
                    response.status_code
                    == 200,
                    (
                        "valid R2 download failed: "
                        + dvd_id
                    ),
                )

                require(
                    calls
                    == [
                        (
                            "enqueue",
                            expected_url,
                            "auto",
                        ),
                    ],
                    (
                        "resolved URL mismatch: "
                        + dvd_id
                    ),
                )

            print(
                "DISCOVERY_DOWNLOAD_R2_RESOLVER_WIRING_SMOKE=PASS"
            )

            print(
                "DISCOVERY_DOWNLOAD_R2_FIXED_PRIORITY_SMOKE=PASS"
            )

            calls.clear()

            core.tasks = {
                "existing-standard": {
                    "status":
                        "다운로드 중",

                    "url":
                        (
                            "https://missav123.com/"
                            "ko/sw-893"
                        ),
                },
            }

            response = client.post(
                "/api/discovery/download",
                json={
                    "dvd_id":
                        "SW-893",
                },
            )

            require(
                response.status_code
                == 409,
                (
                    "standard task did not block "
                    "uncensored duplicate"
                ),
            )

            require(
                calls == [],
                "duplicate reached enqueue",
            )

            print(
                "DISCOVERY_DOWNLOAD_STANDARD_BLOCKS_UNCENSORED_SMOKE=PASS"
            )

            calls.clear()

            core.tasks = {
                "existing-uncensored": {
                    "status":
                        "대기 중",

                    "url":
                        (
                            "https://missav123.com/"
                            "ko/"
                            "bth-103-uncensored-leak"
                        ),
                },
            }

            response = client.post(
                "/api/discovery/download",
                json={
                    "dvd_id":
                        "BTH-103",
                },
            )

            require(
                response.status_code
                == 409,
                (
                    "uncensored task did not block "
                    "standard duplicate"
                ),
            )

            require(
                calls == [],
                "reverse duplicate reached enqueue",
            )

            print(
                "DISCOVERY_DOWNLOAD_UNCENSORED_BLOCKS_STANDARD_SMOKE=PASS"
            )

            calls.clear()

            core.tasks = {
                "existing-123av": {
                    "status":
                        "다운로드 중",

                    "url":
                        (
                            "https://123av.com/"
                            "ko/v/bth-103"
                        ),
                },
            }

            response = client.post(
                "/api/discovery/download",
                json={
                    "dvd_id":
                        "BTH-103",
                },
            )

            require(
                response.status_code
                == 409,
                "123AV same-title duplicate escaped",
            )

            require(
                calls == [],
                "123AV duplicate reached enqueue",
            )

            print(
                "DISCOVERY_DOWNLOAD_CROSS_SOURCE_DUPLICATE_SMOKE=PASS"
            )

            calls.clear()

            core.tasks = {
                "completed-same-title": {
                    "status":
                        "완료",

                    "url":
                        (
                            "https://missav123.com/"
                            "ko/bth-103"
                        ),
                },
            }

            response = client.post(
                "/api/discovery/download",
                json={
                    "dvd_id":
                        "BTH-103",
                },
            )

            require(
                response.status_code
                == 200,
                "completed task incorrectly blocked retry",
            )

            require(
                len(calls)
                == 1,
                "completed retry did not enqueue",
            )

            print(
                "DISCOVERY_DOWNLOAD_TERMINAL_TASK_RETRY_SMOKE=PASS"
            )

            standard_key = (
                api.teddy_duplicates.duplicate_key(
                    (
                        "https://missav123.com/"
                        "ko/sw-893"
                    )
                )
            )

            variant_key = (
                api.teddy_duplicates.duplicate_key(
                    (
                        "https://missav123.com/"
                        "ko/"
                        "sw-893-uncensored-leak"
                    )
                )
            )

            require(
                standard_key
                != variant_key,
                (
                    "generic duplicate behavior "
                    "was globally rewritten"
                ),
            )

            print(
                "GENERIC_DUPLICATE_BEHAVIOR_UNCHANGED_SMOKE=PASS"
            )

        finally:
            api.teddy_routing.enqueue_download = (
                original_enqueue
            )

        after = sha256(
            db_path
        )

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
            "DISCOVERY_DOWNLOAD_DB_BYTE_UNCHANGED_SMOKE=PASS"
        )

        print(
            "TEDDY_DISCOVERY_DOWNLOAD_API_OFFLINE_SMOKE=PASS"
        )


if __name__ == "__main__":
    main()
