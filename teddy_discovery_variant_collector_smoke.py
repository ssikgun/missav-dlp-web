from pathlib import Path
import hashlib
import tempfile

import teddy_discovery_db as discovery_db

from teddy_discovery_variant_collector import (
    canonical_standard_missav_url,
    collect_uncensored_missav_variant,
    run_variant_collection,
)

from teddy_discovery_variants import (
    read_title_variants,
)


class FakeResponse:
    def __init__(
        self,
        *,
        status_code,
        url,
        text="",
        content_type="text/html; charset=utf-8",
    ):
        self.status_code = (
            status_code
        )

        self.url = url
        self.text = text

        self.headers = {
            "content-type":
                content_type,
        }


class FakeSession:
    def __init__(
        self,
        response,
    ):
        self.response = response
        self.calls = []

    def get(
        self,
        url,
        **kwargs,
    ):
        self.calls.append(
            (
                url,
                kwargs,
            )
        )

        return self.response


class FailingSession:
    def get(
        self,
        url,
        **kwargs,
    ):
        raise RuntimeError(
            "synthetic network failure"
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
    path,
):
    return hashlib.sha256(
        Path(path).read_bytes()
    ).hexdigest()


def canonical_url_smoke():
    require(
        canonical_standard_missav_url(
            "SW-893"
        )
        == (
            "https://missav123.com/"
            "ko/sw-893"
        ),
        "preferred MissAV URL mismatch",
    )

    print(
        "VARIANT_COLLECTOR_PREFERRED_HOST_SMOKE=PASS"
    )


def page_link_smoke():
    session = FakeSession(
        FakeResponse(
            status_code=200,
            url=(
                "https://missav123.com/"
                "dm13/ko/sw-893"
            ),
            text="""
                <html>
                  <body>

                    <p>
                      uncensored
                    </p>

                    <a href="/ko/adn-785-uncensored-leak">
                      wrong title
                    </a>

                    <a href="/ko/sw-893-leak">
                      leak only
                    </a>

                    <a href="/ko/sw-893-uncensored-leak">
                      correct
                    </a>

                  </body>
                </html>
            """,
        )
    )

    result = (
        collect_uncensored_missav_variant(
            "SW-893",
            session=session,
            proxy_url=(
                "http://vpn.invalid:8888"
            ),
        )
    )

    require(
        result[
            "found"
        ]
        is True,
        "page-link variant missing",
    )

    require(
        result[
            "method"
        ]
        == "page-link",
        "page-link method mismatch",
    )

    require(
        result[
            "variant"
        ][
            "variant_slug"
        ]
        == (
            "sw-893-"
            "uncensored-leak"
        ),
        "page-link slug mismatch",
    )

    require(
        len(
            session.calls
        )
        == 1,
        "collector request count mismatch",
    )

    requested_url, kwargs = (
        session.calls[0]
    )

    require(
        requested_url
        == (
            "https://missav123.com/"
            "ko/sw-893"
        ),
        "collector did not use "
        "preferred host",
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
            "proxies"
        )
        == {
            "http":
                "http://vpn.invalid:8888",

            "https":
                "http://vpn.invalid:8888",
        },
        "VPN proxy propagation mismatch",
    )

    print(
        "VARIANT_COLLECTOR_PAGE_LINK_SMOKE=PASS"
    )


def redirect_target_smoke():
    session = FakeSession(
        FakeResponse(
            status_code=200,
            url=(
                "https://missav123.com/"
                "dm13/ko/"
                "sw-893-uncensored-leak"
            ),
            text="""
                <html>
                  <body>
                    SW-893
                  </body>
                </html>
            """,
        )
    )

    result = (
        collect_uncensored_missav_variant(
            "SW-893",
            session=session,
        )
    )

    require(
        result[
            "found"
        ]
        is True,
        "redirect variant missing",
    )

    require(
        result[
            "method"
        ]
        == "redirect-target",
        "redirect method mismatch",
    )

    require(
        result[
            "variant"
        ][
            "variant_slug"
        ]
        == (
            "sw-893-"
            "uncensored-leak"
        ),
        "redirect slug mismatch",
    )

    print(
        "VARIANT_COLLECTOR_REDIRECT_TARGET_SMOKE=PASS"
    )


def no_variant_smoke():
    session = FakeSession(
        FakeResponse(
            status_code=200,
            url=(
                "https://missav123.com/"
                "dm13/ko/sw-893"
            ),
            text="""
                <html>
                  <body>

                    SW-893 uncensored

                    <a href="/ko/sw-893">
                      standard
                    </a>

                  </body>
                </html>
            """,
        )
    )

    result = (
        collect_uncensored_missav_variant(
            "SW-893",
            session=session,
        )
    )

    require(
        result[
            "found"
        ]
        is False,
        "generic text created variant",
    )

    require(
        result[
            "variant"
        ]
        is None,
        "not-found result "
        "contains variant",
    )

    print(
        "VARIANT_COLLECTOR_GENERIC_TEXT_IGNORED_SMOKE=PASS"
    )


def http_404_smoke():
    session = FakeSession(
        FakeResponse(
            status_code=404,
            url=(
                "https://missav123.com/"
                "ko/sw-893"
            ),
            text="not found",
        )
    )

    result = (
        collect_uncensored_missav_variant(
            "SW-893",
            session=session,
        )
    )

    require(
        result[
            "found"
        ]
        is False,
        "404 must not create variant",
    )

    require(
        result[
            "http_status"
        ]
        == 404,
        "404 status mismatch",
    )

    print(
        "VARIANT_COLLECTOR_404_SMOKE=PASS"
    )


def fail_closed_smoke():
    bad_host = FakeSession(
        FakeResponse(
            status_code=200,
            url=(
                "https://example.com/"
                "ko/sw-893"
            ),
            text="<html>SW-893</html>",
        )
    )

    try:
        collect_uncensored_missav_variant(
            "SW-893",
            session=bad_host,
        )

    except RuntimeError:
        pass

    else:
        raise RuntimeError(
            "off-family redirect "
            "must fail closed"
        )

    bad_id = FakeSession(
        FakeResponse(
            status_code=200,
            url=(
                "https://missav123.com/"
                "ko/adn-785"
            ),
            text="<html>ADN-785</html>",
        )
    )

    try:
        collect_uncensored_missav_variant(
            "SW-893",
            session=bad_id,
        )

    except RuntimeError:
        pass

    else:
        raise RuntimeError(
            "wrong-title redirect "
            "must fail closed"
        )

    bad_type = FakeSession(
        FakeResponse(
            status_code=200,
            url=(
                "https://missav123.com/"
                "ko/sw-893"
            ),
            text="binary",
            content_type=(
                "application/octet-stream"
            ),
        )
    )

    try:
        collect_uncensored_missav_variant(
            "SW-893",
            session=bad_type,
        )

    except RuntimeError:
        pass

    else:
        raise RuntimeError(
            "non-HTML response "
            "must fail closed"
        )

    print(
        "VARIANT_COLLECTOR_FAIL_CLOSED_SMOKE=PASS"
    )


def temp_db_storage_smoke():
    session = FakeSession(
        FakeResponse(
            status_code=200,
            url=(
                "https://missav123.com/"
                "dm13/ko/sw-893"
            ),
            text="""
                <html>
                  <body>
                    <a href="/ko/sw-893-uncensored-leak">
                      correct
                    </a>
                  </body>
                </html>
            """,
        )
    )

    with tempfile.TemporaryDirectory(
        prefix="teddy-variant-collector-"
    ) as temp:

        db_path = (
            Path(temp)
            / "collector.sqlite3"
        )

        connection = (
            discovery_db.connect(
                db_path
            )
        )

        try:
            discovery_db.initialize(
                connection
            )

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
                    "SW-893",
                    "SW-893 title",
                    (
                        "2026-08-28"
                        "T00:00:00+00:00"
                    ),
                    (
                        "2026-08-28"
                        "T00:00:00+00:00"
                    ),
                ),
            )

            connection.commit()

        finally:
            connection.close()

        result = run_variant_collection(
            db_path,
            "SW-893",
            session=session,
        )

        require(
            result[
                "stored"
            ]
            is True,
            "variant was not stored",
        )

        require(
            result[
                "db_integrity"
            ]
            == "ok",
            "temp DB integrity failed",
        )

        connection = (
            discovery_db.connect(
                db_path
            )
        )

        try:
            discovery_db.initialize(
                connection
            )

            rows = read_title_variants(
                connection,
                dvd_id="SW-893",
                confirmed_only=True,
            )

        finally:
            connection.close()

        require(
            len(
                rows
            )
            == 1,
            "stored variant count mismatch",
        )

        require(
            rows[0][
                "variant_slug"
            ]
            == (
                "sw-893-"
                "uncensored-leak"
            ),
            "stored variant slug mismatch",
        )

    print(
        "VARIANT_COLLECTOR_TEMP_DB_STORAGE_SMOKE=PASS"
    )


def network_before_db_smoke():
    with tempfile.TemporaryDirectory(
        prefix="teddy-variant-network-first-"
    ) as temp:

        path = (
            Path(temp)
            / "must-not-change.bin"
        )

        path.write_bytes(
            b"TEDDY-NO-DB-OPEN"
        )

        before = sha256(
            path
        )

        try:
            run_variant_collection(
                path,
                "SW-893",
                session=FailingSession(),
            )

        except RuntimeError as exc:
            require(
                "synthetic network failure"
                in str(
                    exc
                ),
                "unexpected network "
                "failure reason",
            )

        else:
            raise RuntimeError(
                "network failure "
                "must propagate"
            )

        after = sha256(
            path
        )

        require(
            after == before,
            "DB path changed before "
            "network validation finished",
        )

    print(
        "VARIANT_COLLECTOR_NETWORK_BEFORE_DB_SMOKE=PASS"
    )


def main():
    canonical_url_smoke()
    page_link_smoke()
    redirect_target_smoke()
    no_variant_smoke()
    http_404_smoke()
    fail_closed_smoke()
    temp_db_storage_smoke()
    network_before_db_smoke()

    print(
        "TEDDY_DISCOVERY_VARIANT_COLLECTOR_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
