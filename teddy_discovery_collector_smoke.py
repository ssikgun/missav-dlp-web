from pathlib import Path
import tempfile

from teddy_discovery_collector import (
    collect_release_pages,
    run_release_collection,
)


PROXY = (
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


def page_url(
    page,
):
    if page == 1:
        return (
            "https://missav.ws/"
            "ko/release"
        )

    return (
        "https://missav.ws/"
        "dm635/ko/release"
        f"?page={page}"
    )


def final_url(
    page,
):
    if page == 1:
        return (
            "https://missav.ws/"
            "dm635/ko/release"
        )

    return page_url(
        page
    )


def page_html(
    page,
    *,
    next_page=None,
):
    first = (
        (page - 1)
        * 12
        + 1
    )

    parts = [
        "<html><body>"
    ]

    for number in range(
        first,
        first + 12,
    ):
        dvd = (
            f"TST-{number:03d}"
        )

        slug = (
            dvd.lower()
        )

        parts.append(
            '<div class="thumbnail group">'
            '<div>'
            f'<a href="/ko/{slug}">'
            '<img '
            f'data-src="https://example.invalid/{slug}.jpg" '
            f'alt="Synthetic {dvd}">'
            '</a>'
            '</div>'
            '</div>'
        )

    if next_page is not None:
        parts.append(
            '<nav>'
            '<a '
            'rel="next" '
            f'href="https://missav.ws/'
            f'dm635/ko/release?page={next_page}"'
            '>'
            'Next'
            '</a>'
            '</nav>'
        )

    parts.append(
        "</body></html>"
    )

    return "".join(
        parts
    )


class FakeResponse:
    def __init__(
        self,
        url,
        body,
    ):
        self.status_code = 200
        self.url = url
        self.text = body

        self.headers = {
            "content-type":
                "text/html; charset=utf-8",
        }

        self.history = []


class FakeSession:
    def __init__(
        self,
        *,
        fail_on_call=None,
        skip_after_page=None,
    ):
        self.calls = []
        self.fail_on_call = (
            fail_on_call
        )

        self.skip_after_page = (
            skip_after_page
        )

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

        call_number = len(
            self.calls
        )

        if (
            self.fail_on_call
            == call_number
        ):
            raise RuntimeError(
                "synthetic transport failure"
            )

        if call_number == 1:
            page = 1
        else:
            page = int(
                url.rsplit(
                    "page=",
                    1,
                )[-1]
            )

        if (
            self.skip_after_page
            == page
        ):
            next_page = (
                page + 2
            )

        elif page < 5:
            next_page = (
                page + 1
            )

        else:
            next_page = None

        return FakeResponse(
            final_url(
                page
            ),
            page_html(
                page,
                next_page=
                    next_page,
            ),
        )


def verify_calls(
    session,
    expected_count,
):
    require(
        len(
            session.calls
        )
        == expected_count,
        "unexpected request count",
    )

    for index, call in enumerate(
        session.calls,
        start=1,
    ):
        kwargs = call[
            "kwargs"
        ]

        proxies = kwargs.get(
            "proxies"
        )

        require(
            proxies
            == {
                "http":
                    PROXY,

                "https":
                    PROXY,
            },
            "request escaped VPN proxy",
        )

        require(
            kwargs.get(
                "allow_redirects"
            )
            is True,
            "redirect handling changed",
        )

        require(
            kwargs.get(
                "impersonate"
            )
            == "chrome",
            "impersonation changed",
        )

        require(
            kwargs.get(
                "timeout"
            )
            == 45,
            "timeout changed",
        )

        expected_url = (
            page_url(
                index
            )
        )

        require(
            call["url"]
            == expected_url,
            (
                "pagination URL mismatch: "
                f"{call['url']!r} "
                f"!= {expected_url!r}"
            ),
        )


def collection_smoke():
    session = FakeSession()

    result = collect_release_pages(
        session=session,
        proxy_url=PROXY,
        limit=50,
        max_pages=5,
    )

    verify_calls(
        session,
        5,
    )

    require(
        result[
            "page_count"
        ]
        == 5,
        "collector page count changed",
    )

    require(
        result[
            "item_count"
        ]
        == 50,
        "collector item count changed",
    )

    ids = [
        item[
            "dvd_id"
        ]
        for item
        in result[
            "items"
        ]
    ]

    require(
        ids
        == [
            f"TST-{number:03d}"
            for number
            in range(
                1,
                51,
            )
        ],
        "collector global order changed",
    )

    require(
        [
            item[
                "position"
            ]
            for item
            in result[
                "items"
            ]
        ]
        == list(
            range(
                1,
                51,
            )
        ),
        "collector global positions changed",
    )

    print(
        "FIXED_VPN_ROUTE_SMOKE=PASS"
    )

    print(
        "FIVE_PAGE_CHAIN_SMOKE=PASS"
    )

    print(
        "LATEST_50_COLLECTION_SMOKE=PASS"
    )


def fail_closed_before_db_smoke():
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-collector-fail-"
    ) as temp:
        db_path = (
            Path(temp)
            / "must-not-exist.sqlite3"
        )

        session = FakeSession(
            fail_on_call=4,
        )

        try:
            run_release_collection(
                db_path,
                session=session,
                proxy_url=PROXY,
                limit=50,
                max_pages=5,
            )

        except RuntimeError as exc:
            require(
                "synthetic transport failure"
                in str(exc),
                "unexpected transport failure",
            )

        else:
            raise RuntimeError(
                "transport failure "
                "must fail collector"
            )

        require(
            not db_path.exists(),
            (
                "DB was opened before "
                "network collection completed"
            ),
        )

    print(
        "NETWORK_FAILURE_BEFORE_DB_SMOKE=PASS"
    )


def sequential_page_fail_closed_smoke():
    session = FakeSession(
        skip_after_page=2,
    )

    try:
        collect_release_pages(
            session=session,
            proxy_url=PROXY,
            limit=50,
            max_pages=5,
        )

    except RuntimeError as exc:
        require(
            "not sequential"
            in str(exc),
            "unexpected pagination failure",
        )

    else:
        raise RuntimeError(
            "skipped pagination "
            "must fail closed"
        )

    print(
        "SEQUENTIAL_PAGE_FAIL_CLOSED_SMOKE=PASS"
    )


def direct_route_rejected_smoke():
    session = FakeSession()

    try:
        collect_release_pages(
            session=session,
            proxy_url="",
            limit=50,
            max_pages=5,
        )

    except ValueError as exc:
        require(
            "VPN proxy is required"
            in str(exc),
            "unexpected proxy failure",
        )

    else:
        raise RuntimeError(
            "empty VPN proxy "
            "must be rejected"
        )

    require(
        not session.calls,
        "request occurred without VPN",
    )

    print(
        "DIRECT_ROUTE_REJECTED_SMOKE=PASS"
    )


def successful_db_smoke():
    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-collector-db-"
    ) as temp:
        db_path = (
            Path(temp)
            / "discovery.sqlite3"
        )

        session = FakeSession()

        result = (
            run_release_collection(
                db_path,
                session=session,
                proxy_url=PROXY,
                limit=50,
                max_pages=5,
            )
        )

        require(
            result[
                "written"
            ]
            == 50,
            "DB write count changed",
        )

        require(
            result[
                "db_integrity"
            ]
            == "ok",
            "DB integrity changed",
        )

        import sqlite3

        connection = (
            sqlite3.connect(
                db_path
            )
        )

        schema = (
            connection.execute(
                """
                SELECT MAX(version)
                FROM schema_migrations
                """
            ).fetchone()[0]
        )

        latest = (
            connection.execute(
                """
                SELECT COUNT(*)
                FROM latest_items
                WHERE source =
                    'missav-release'
                """
            ).fetchone()[0]
        )

        titles = (
            connection.execute(
                """
                SELECT COUNT(*)
                FROM titles
                """
            ).fetchone()[0]
        )

        connection.close()

        require(
            schema == 3,
            "collector DB schema changed",
        )

        require(
            latest == 50,
            "collector latest count changed",
        )

        require(
            titles == 50,
            "collector title count changed",
        )

    print(
        "ATOMIC_LATEST_DB_WRITE_SMOKE=PASS"
    )


def main():
    collection_smoke()

    fail_closed_before_db_smoke()

    sequential_page_fail_closed_smoke()

    direct_route_rejected_smoke()

    successful_db_smoke()

    print(
        "DISCOVERY_COLLECTOR_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
