from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys
import tempfile

import teddy_discovery_javdatabase_collector as collector

from teddy_discovery_db import (
    SCHEMA_VERSION,
)


FIXED_PROXY = (
    "http://gluetun:8888"
)


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


class FakeResponse:
    def __init__(
        self,
        *,
        status,
        url,
        body,
        content_type="text/html; charset=UTF-8",
    ):
        self.status_code = status
        self.url = url
        self.text = body
        self.headers = {
            "content-type":
                content_type,
        }
        self.history = []


class FakeSession:
    def __init__(
        self,
        responses,
    ):
        self.responses = list(
            responses
        )

        self.calls = []
        self.closed = False

    def get(
        self,
        url,
        **kwargs,
    ):
        self.calls.append({
            "url":
                url,

            "kwargs":
                kwargs,
        })

        if not self.responses:
            raise RuntimeError(
                "unexpected third HTTP GET"
            )

        return self.responses.pop(
            0
        )

    def close(
        self,
    ):
        self.closed = True


def sqlite_backup(
    source_path: Path,
    destination_path: Path,
):
    source = sqlite3.connect(
        "file:"
        + str(source_path)
        + "?mode=ro",
        uri=True,
    )

    target = sqlite3.connect(
        destination_path
    )

    try:
        source.backup(
            target
        )

    finally:
        target.close()
        source.close()


def load_fixture(
    path: Path,
):
    with path.open(
        "r",
        encoding="utf-8",
    ) as fh:
        return json.load(
            fh
        )


def fake_response_from_envelope(
    envelope,
):
    return FakeResponse(
        status=
            envelope[
                "status"
            ],

        url=
            envelope[
                "final_url"
            ],

        body=
            envelope[
                "body"
            ],

        content_type=
            envelope.get(
                "content_type"
            )
            or "text/html; charset=UTF-8",
    )


def with_fixed_route(
    function,
):
    original = (
        collector.teddy_routing
        .proxy_for_mode
    )

    modes = []

    def fake_proxy_for_mode(
        mode,
    ):
        modes.append(
            mode
        )

        if mode != "vpn":
            raise RuntimeError(
                "collector requested "
                "non-VPN route"
            )

        return FIXED_PROXY

    collector.teddy_routing.proxy_for_mode = (
        fake_proxy_for_mode
    )

    try:
        result = function(
            modes
        )

    finally:
        collector.teddy_routing.proxy_for_mode = (
            original
        )

    return result


def category_selector_smoke(
    forensic,
):
    result = (
        collector
        .parse_weekly_category_envelope(
            forensic[
                "category"
            ]
        )
    )

    selected = result[
        "selected"
    ]

    require(
        result[
            "candidate_count"
        ]
        == 18,
        "category candidate count changed",
    )

    require(
        selected[
            "period"
        ]
        == "2026-W33",
        "latest category period changed",
    )

    require(
        selected[
            "title"
        ]
        == forensic[
            "selected_article"
        ][
            "title"
        ],
        "selected category title changed",
    )

    require(
        selected[
            "url"
        ]
        == forensic[
            "selected_article"
        ][
            "url"
        ],
        "selected category URL changed",
    )

    print(
        "CATEGORY_WEEK33_SELECTOR_SMOKE=PASS"
    )


def period_primary_smoke():
    category = """
    <html><body>

    <a href="
      https://www.javdatabase.com/
      2026/08/30/
      top-jav-movies-2026-week-32-old-correction/
    ">
      Top JAV Movies – 2026 – Week 32
      (6th – 12th August 2026)
    </a>

    <a href="
      https://www.javdatabase.com/
      2026/08/25/
      top-jav-movies-2026-week-33-current/
    ">
      Top JAV Movies – 2026 – Week 33
      (13th – 19th August 2026)
    </a>

    </body></html>
    """.replace(
        "\n      ",
        ""
    )

    result = (
        collector
        .parse_weekly_category_html(
            category,
            collector.DEFAULT_CATEGORY_URL,
        )
    )

    require(
        result[
            "selected"
        ][
            "period"
        ]
        == "2026-W33",
        (
            "newer publication date "
            "incorrectly outranked "
            "newer chart period"
        ),
    )

    print(
        "CATEGORY_PERIOD_PRIMARY_SMOKE=PASS"
    )


def duplicate_period_fail_closed_smoke():
    category = """
    <html><body>

    <a href="
      https://www.javdatabase.com/
      2026/08/25/
      top-jav-movies-2026-week-33-a/
    ">
      Top JAV Movies – 2026 – Week 33
      (13th – 19th August 2026)
    </a>

    <a href="
      https://www.javdatabase.com/
      2026/08/26/
      top-jav-movies-2026-week-33-b/
    ">
      Top JAV Movies – 2026 – Week 33
      (13th – 19th August 2026)
    </a>

    </body></html>
    """.replace(
        "\n      ",
        ""
    )

    try:
        collector.parse_weekly_category_html(
            category,
            collector.DEFAULT_CATEGORY_URL,
        )

    except ValueError as exc:
        require(
            "duplicate Weekly period"
            in str(exc),
            "unexpected duplicate-period failure",
        )

    else:
        raise RuntimeError(
            "duplicate Weekly period "
            "must fail closed"
        )

    print(
        "CATEGORY_DUPLICATE_PERIOD_FAIL_CLOSED_SMOKE=PASS"
    )


def fixed_vpn_two_get_smoke(
    forensic,
):
    category = forensic[
        "category"
    ]

    article = forensic[
        "article"
    ]

    session = FakeSession([
        fake_response_from_envelope(
            category
        ),
        fake_response_from_envelope(
            article
        ),
    ])

    def run(
        modes,
    ):
        result = (
            collector
            .collect_weekly_snapshot(
                session=session
            )
        )

        require(
            modes == [
                "vpn",
            ],
            "collector did not request "
            "fixed VPN route exactly once",
        )

        return result

    result = with_fixed_route(
        run
    )

    require(
        result[
            "request_count"
        ]
        == 2,
        "successful collection "
        "must use exactly two GETs",
    )

    require(
        len(
            session.calls
        )
        == 2,
        "fake session GET count changed",
    )

    expected_urls = [
        category[
            "requested_url"
        ],
        forensic[
            "selected_article"
        ][
            "url"
        ],
    ]

    require(
        [
            call[
                "url"
            ]
            for call
            in session.calls
        ]
        == expected_urls,
        "category/article GET order changed",
    )

    for call in session.calls:
        proxies = call[
            "kwargs"
        ].get(
            "proxies"
        )

        require(
            proxies
            == {
                "http":
                    FIXED_PROXY,

                "https":
                    FIXED_PROXY,
            },
            "collector proxy changed",
        )

    require(
        result[
            "snapshot"
        ][
            "period"
        ]
        == "2026-W33",
        "collected period changed",
    )

    require(
        result[
            "snapshot"
        ][
            "item_count"
        ]
        == 25,
        "collected item count changed",
    )

    print(
        "FIXED_VPN_ROUTE_SMOKE=PASS"
    )

    print(
        "EXACT_TWO_HTML_GET_SMOKE=PASS"
    )

    print(
        "CATEGORY_THEN_ARTICLE_ORDER_SMOKE=PASS"
    )


def failure_before_db_smoke(
    forensic,
):
    original_connect = (
        collector.connect
    )

    connect_calls = []

    def forbidden_connect(
        *args,
        **kwargs,
    ):
        connect_calls.append(
            (
                args,
                kwargs,
            )
        )

        raise RuntimeError(
            "DB must not open "
            "before collection succeeds"
        )

    collector.connect = (
        forbidden_connect
    )

    try:
        #
        # Category HTTP failure.
        #
        bad_category = (
            FakeResponse(
                status=503,
                url=collector.DEFAULT_CATEGORY_URL,
                body="temporary failure",
            )
        )

        session = FakeSession([
            bad_category,
        ])

        def run_category_failure(
            modes,
        ):
            try:
                collector.run_weekly_collection(
                    "/tmp/should-not-open.sqlite3",
                    session=session,
                )

            except RuntimeError as exc:
                require(
                    "HTTP 503"
                    in str(exc),
                    "unexpected category "
                    "network failure",
                )

            else:
                raise RuntimeError(
                    "category HTTP failure "
                    "must fail closed"
                )

        with_fixed_route(
            run_category_failure
        )

        require(
            not connect_calls,
            "DB opened after category failure",
        )

        #
        # Article parse failure.
        #
        category_response = (
            fake_response_from_envelope(
                forensic[
                    "category"
                ]
            )
        )

        bad_article = FakeResponse(
            status=200,
            url=forensic[
                "selected_article"
            ][
                "url"
            ],
            body=(
                "<html><body>"
                "<h1>broken</h1>"
                "</body></html>"
            ),
        )

        session = FakeSession([
            category_response,
            bad_article,
        ])

        def run_article_failure(
            modes,
        ):
            try:
                collector.run_weekly_collection(
                    "/tmp/should-not-open.sqlite3",
                    session=session,
                )

            except (
                ValueError,
                RuntimeError,
            ):
                pass

            else:
                raise RuntimeError(
                    "article parse failure "
                    "must fail closed"
                )

        with_fixed_route(
            run_article_failure
        )

        require(
            not connect_calls,
            "DB opened after article "
            "parse failure",
        )

    finally:
        collector.connect = (
            original_connect
        )

    print(
        "CATEGORY_FAILURE_BEFORE_DB_SMOKE=PASS"
    )

    print(
        "ARTICLE_FAILURE_BEFORE_DB_SMOKE=PASS"
    )


def article_identity_fail_closed_smoke(
    forensic,
):
    category_html = """
    <html><body>
    <a href="
      https://www.javdatabase.com/
      2026/08/18/
      top-jav-movies-2026-week-32-test/
    ">
      Top JAV Movies – 2026 – Week 32
      (6th – 12th August 2026)
    </a>
    </body></html>
    """.replace(
        "\n      ",
        ""
    )

    category = FakeResponse(
        status=200,
        url=collector.DEFAULT_CATEGORY_URL,
        body=category_html,
    )

    #
    # Return the real Week 33 body under
    # the selected Week 32 URL.
    #
    article = FakeResponse(
        status=200,
        url=(
            "https://www.javdatabase.com/"
            "2026/08/18/"
            "top-jav-movies-2026-week-32-test/"
        ),
        body=forensic[
            "article"
        ][
            "body"
        ],
    )

    session = FakeSession([
        category,
        article,
    ])

    def run(
        modes,
    ):
        try:
            collector.collect_weekly_snapshot(
                session=session
            )

        except RuntimeError as exc:
            require(
                (
                    "period mismatch"
                    in str(exc)
                    or "title mismatch"
                    in str(exc)
                ),
                "unexpected article identity failure",
            )

        else:
            raise RuntimeError(
                "category/article identity "
                "mismatch must fail closed"
            )

    with_fixed_route(
        run
    )

    print(
        "CATEGORY_ARTICLE_IDENTITY_FAIL_CLOSED_SMOKE=PASS"
    )


def temp_db_end_to_end_smoke(
    base_db: Path,
    forensic,
):
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-javdatabase-collector-"
    ) as temp:
        db_path = (
            Path(temp)
            / "collector.sqlite3"
        )

        sqlite_backup(
            base_db,
            db_path,
        )

        session = FakeSession([
            fake_response_from_envelope(
                forensic[
                    "category"
                ]
            ),
            fake_response_from_envelope(
                forensic[
                    "article"
                ]
            ),
        ])

        def run(
            modes,
        ):
            return (
                collector.run_weekly_collection(
                    db_path,
                    session=session,
                )
            )

        result = with_fixed_route(
            run
        )

        require(
            result[
                "period"
            ]
            == "2026-W33",
            "E2E period changed",
        )

        require(
            result[
                "request_count"
            ]
            == 2,
            "E2E request count changed",
        )

        require(
            result[
                "written"
            ]
            == 25,
            "E2E ranking write changed",
        )

        require(
            result[
                "db_integrity"
            ]
            == "ok",
            "E2E DB integrity changed",
        )

        connection = sqlite3.connect(
            db_path
        )

        connection.row_factory = (
            sqlite3.Row
        )

        try:
            schema = connection.execute(
                """
                SELECT MAX(version)
                FROM schema_migrations
                """
            ).fetchone()[0]

            ranking_count = (
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM ranking_snapshots
                    WHERE chart_type =
                        'javdatabase-weekly'
                      AND period =
                        '2026-W33'
                    """
                ).fetchone()[0]
            )

            latest_count = (
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM latest_items
                    WHERE source =
                        'missav-release'
                    """
                ).fetchone()[0]
            )

            holdings_count = (
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM holdings
                    """
                ).fetchone()[0]
            )

            top = connection.execute(
                """
                SELECT dvd_id
                FROM ranking_snapshots
                WHERE chart_type =
                    'javdatabase-weekly'
                  AND period =
                    '2026-W33'
                ORDER BY rank
                LIMIT 1
                """
            ).fetchone()

            integrity = connection.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]

        finally:
            connection.close()

        require(
            schema == SCHEMA_VERSION,
            "collector schema changed",
        )

        require(
            ranking_count == 25,
            "collector ranking count changed",
        )

        require(
            latest_count == 50,
            "collector changed Latest",
        )

        require(
            holdings_count == 69,
            "collector changed holdings",
        )

        require(
            top[
                "dvd_id"
            ]
            == "JUR-786",
            "collector rank 1 changed",
        )

        require(
            integrity == "ok",
            "collector DB integrity failed",
        )

    print(
        "WEEKLY_COLLECTOR_TEMP_DB_E2E_SMOKE=PASS"
    )

    print(
        "WEEKLY_COLLECTOR_LATEST_UNCHANGED_SMOKE=PASS"
    )

    print(
        "WEEKLY_COLLECTOR_HOLDINGS_UNCHANGED_SMOKE=PASS"
    )


def main():
    if len(
        sys.argv
    ) != 3:
        raise RuntimeError(
            "usage: "
            "teddy_discovery_"
            "javdatabase_collector_smoke.py "
            "<stage2-v3-db> "
            "<javdatabase-forensic-json>"
        )

    base_db = Path(
        sys.argv[1]
    )

    fixture = Path(
        sys.argv[2]
    )

    forensic = load_fixture(
        fixture
    )

    category_selector_smoke(
        forensic
    )

    period_primary_smoke()

    duplicate_period_fail_closed_smoke()

    fixed_vpn_two_get_smoke(
        forensic
    )

    failure_before_db_smoke(
        forensic
    )

    article_identity_fail_closed_smoke(
        forensic
    )

    temp_db_end_to_end_smoke(
        base_db,
        forensic,
    )

    print(
        "JAVDATABASE_WEEKLY_COLLECTOR_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
