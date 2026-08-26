from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

from flask import Flask

from teddy_discovery_api import (
    create_discovery_blueprint,
)

from teddy_discovery_ui_data import (
    build_category_facets_view,
    build_category_view,
    build_latest_view,
    build_monthly_view,
    build_weekly_view,
)


EXPECTED_WEEKLY_PERIOD = (
    "2026-W33"
)

TEST_CATEGORY = (
    "Big Tits"
)


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


def file_sha256(
    path: Path,
) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def connect_ro(
    path: Path,
):
    connection = sqlite3.connect(
        "file:"
        + str(path)
        + "?mode=ro",
        uri=True,
    )

    connection.row_factory = (
        sqlite3.Row
    )

    return connection


def make_client(
    db_path: Path,
):
    app = Flask(
        "teddy-discovery-api-smoke"
    )

    app.config[
        "TESTING"
    ] = True

    app.register_blueprint(
        create_discovery_blueprint(
            db_path
        )
    )

    return app.test_client()


def success_data(
    response,
):
    require(
        response.status_code == 200,
        "expected HTTP 200, got "
        + str(
            response.status_code
        ),
    )

    value = response.get_json()

    require(
        isinstance(
            value,
            dict,
        ),
        "API response is not object",
    )

    require(
        value.get(
            "status"
        ) == "success",
        "API success envelope changed",
    )

    require(
        isinstance(
            value.get(
                "data"
            ),
            dict,
        ),
        "API data envelope changed",
    )

    return value[
        "data"
    ]


def error_contract(
    response,
    *,
    status_code,
    code,
):
    require(
        response.status_code
        == status_code,
        "API error status changed",
    )

    value = response.get_json()

    require(
        isinstance(
            value,
            dict,
        ),
        "API error response invalid",
    )

    require(
        value.get(
            "status"
        ) == "error",
        "API error envelope changed",
    )

    error = value.get(
        "error"
    )

    require(
        isinstance(
            error,
            dict,
        ),
        "API error object missing",
    )

    require(
        error.get(
            "code"
        ) == code,
        "API error code changed",
    )

    require(
        isinstance(
            error.get(
                "message"
            ),
            str,
        )
        and bool(
            error[
                "message"
            ]
        ),
        "API error message invalid",
    )

    return value


def assert_browser_safe(
    value,
):
    forbidden = {
        "cover_url",
        "source_url",
        "page_url",
        "raw_metadata",
        "relative_path",
        "storage_root",
    }

    if isinstance(
        value,
        dict,
    ):
        bad = (
            forbidden
            & set(
                value
            )
        )

        require(
            not bad,
            "API exposed upstream/path key: "
            + repr(
                sorted(
                    bad
                )
            ),
        )

        for child in value.values():
            assert_browser_safe(
                child
            )

    elif isinstance(
        value,
        list,
    ):
        for child in value:
            assert_browser_safe(
                child
            )


def canonical_read_models(
    db_path: Path,
):
    connection = connect_ro(
        db_path
    )

    try:
        values = {
            "latest":
                build_latest_view(
                    connection,
                    limit=50,
                ),

            "weekly":
                build_weekly_view(
                    connection,
                    limit=25,
                ),

            "monthly":
                build_monthly_view(
                    connection,
                    limit=25,
                ),

            "categories":
                build_category_facets_view(
                    connection
                ),

            "category":
                build_category_view(
                    connection,
                    TEST_CATEGORY,
                    limit=500,
                ),
        }

        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

    finally:
        connection.close()

    require(
        integrity == "ok",
        "canonical DB integrity failed",
    )

    return values


def api_success_smoke(
    db_path: Path,
):
    client = make_client(
        db_path
    )

    latest = success_data(
        client.get(
            "/api/discovery/latest"
        )
    )

    weekly = success_data(
        client.get(
            "/api/discovery/weekly"
        )
    )

    weekly_explicit = success_data(
        client.get(
            "/api/discovery/weekly",
            query_string={
                "period":
                    EXPECTED_WEEKLY_PERIOD,
                "limit":
                    "25",
            },
        )
    )

    monthly = success_data(
        client.get(
            "/api/discovery/monthly"
        )
    )

    monthly_full = success_data(
        client.get(
            "/api/discovery/monthly",
            query_string={
                "limit":
                    "500",
            },
        )
    )

    categories = success_data(
        client.get(
            "/api/discovery/categories"
        )
    )

    category = success_data(
        client.get(
            "/api/discovery/category",
            query_string={
                "name":
                    TEST_CATEGORY,

                "limit":
                    "500",
            },
        )
    )

    direct = canonical_read_models(
        db_path
    )

    require(
        latest
        == direct[
            "latest"
        ],
        "Latest API changed "
        "canonical read model",
    )

    require(
        weekly
        == direct[
            "weekly"
        ],
        "Weekly API changed "
        "canonical read model",
    )

    require(
        weekly_explicit
        == direct[
            "weekly"
        ],
        "explicit Weekly API changed "
        "canonical read model",
    )

    require(
        monthly
        == direct[
            "monthly"
        ],
        "Monthly API changed "
        "canonical read model",
    )

    require(
        categories
        == direct[
            "categories"
        ],
        "Categories API changed "
        "canonical read model",
    )

    require(
        category
        == direct[
            "category"
        ],
        "Category API changed "
        "canonical read model",
    )

    require(
        latest[
            "item_count"
        ] == 50,
        "Latest API count changed",
    )

    require(
        weekly[
            "period"
        ] == EXPECTED_WEEKLY_PERIOD,
        "Weekly API period changed",
    )

    require(
        weekly[
            "item_count"
        ] == 25,
        "Weekly API count changed",
    )

    require(
        monthly[
            "item_count"
        ] == 25,
        "Monthly API count changed",
    )

    require(
        monthly_full[
            "item_count"
        ] == 68,
        "full Monthly API count changed",
    )

    require(
        categories[
            "category_count"
        ] == 96,
        "Categories API count changed",
    )

    require(
        category[
            "category"
        ] == TEST_CATEGORY,
        "Category API canonical "
        "name changed",
    )

    for value in (
        latest,
        weekly,
        monthly,
        monthly_full,
        categories,
        category,
    ):
        assert_browser_safe(
            value
        )

    oracle_payload = {
        "latest":
            latest,

        "weekly":
            weekly,

        "monthly":
            monthly,

        "categories":
            categories,

        "category":
            category,
    }

    oracle = hashlib.sha256(
        json.dumps(
            oracle_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
        ).encode(
            "utf-8"
        )
    ).hexdigest()

    print(
        "DISCOVERY_API_ORACLE_SHA256="
        + oracle
    )

    print(
        "DISCOVERY_API_LATEST_CONTRACT_SMOKE=PASS"
    )

    print(
        "DISCOVERY_API_WEEKLY_CONTRACT_SMOKE=PASS"
    )

    print(
        "DISCOVERY_API_MONTHLY_CONTRACT_SMOKE=PASS"
    )

    print(
        "DISCOVERY_API_CATEGORIES_CONTRACT_SMOKE=PASS"
    )

    print(
        "DISCOVERY_API_CATEGORY_CONTRACT_SMOKE=PASS"
    )

    print(
        "DISCOVERY_API_CANONICAL_DATA_EQUALITY_SMOKE=PASS"
    )

    print(
        "DISCOVERY_API_BROWSER_SAFE_SMOKE=PASS"
    )

    return oracle


def api_error_smoke(
    db_path: Path,
):
    client = make_client(
        db_path
    )

    error_contract(
        client.get(
            "/api/discovery/latest",
            query_string={
                "limit":
                    "0",
            },
        ),
        status_code=400,
        code="invalid_request",
    )

    error_contract(
        client.get(
            "/api/discovery/weekly",
            query_string={
                "limit":
                    "26",
            },
        ),
        status_code=400,
        code="invalid_request",
    )

    error_contract(
        client.get(
            "/api/discovery/monthly",
            query_string={
                "limit":
                    "abc",
            },
        ),
        status_code=400,
        code="invalid_request",
    )

    error_contract(
        client.get(
            "/api/discovery/weekly",
            query_string={
                "period":
                    "week33",
            },
        ),
        status_code=400,
        code="invalid_request",
    )

    error_contract(
        client.get(
            "/api/discovery/category"
        ),
        status_code=400,
        code="invalid_request",
    )

    error_contract(
        client.get(
            "/api/discovery/category",
            query_string={
                "name":
                    "Definitely Not A Genre",
            },
        ),
        status_code=404,
        code="category_not_found",
    )

    post = client.post(
        "/api/discovery/latest"
    )

    require(
        post.status_code == 405,
        "Discovery API must remain "
        "GET-only",
    )

    print(
        "DISCOVERY_API_INVALID_INPUT_FAIL_CLOSED_SMOKE=PASS"
    )

    print(
        "DISCOVERY_API_UNKNOWN_CATEGORY_404_SMOKE=PASS"
    )

    print(
        "DISCOVERY_API_GET_ONLY_SMOKE=PASS"
    )


def missing_db_smoke():
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-discovery-api-missing-"
    ) as temp:
        missing = (
            Path(temp)
            / "missing.sqlite3"
        )

        client = make_client(
            missing
        )

        value = error_contract(
            client.get(
                "/api/discovery/latest"
            ),
            status_code=503,
            code="discovery_unavailable",
        )

        serialized = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
        )

        require(
            str(
                missing
            )
            not in serialized,
            "API leaked DB path",
        )

    print(
        "DISCOVERY_API_MISSING_DB_FAIL_CLOSED_SMOKE=PASS"
    )

    print(
        "DISCOVERY_API_INTERNAL_PATH_NOT_LEAKED_SMOKE=PASS"
    )


def main():
    if len(
        sys.argv
    ) != 2:
        raise RuntimeError(
            "usage: "
            "teddy_discovery_api_smoke.py "
            "<stage5-db>"
        )

    db_path = Path(
        sys.argv[1]
    )

    before = file_sha256(
        db_path
    )

    api_success_smoke(
        db_path
    )

    api_error_smoke(
        db_path
    )

    missing_db_smoke()

    after = file_sha256(
        db_path
    )

    require(
        after == before,
        "API smoke changed "
        "real Stage 5 DB bytes",
    )

    print(
        "DISCOVERY_API_REAL_DB_BYTE_UNCHANGED_SMOKE=PASS"
    )

    print(
        "TEDDY_DISCOVERY_API_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
