from pathlib import Path
import hashlib
import tempfile

import teddy_discovery_db as db

from teddy_discovery_download_resolver import (
    DiscoveryResolveRequestError,
    DiscoveryResolveTitleNotFound,
    DiscoveryResolveUnavailable,
    resolve_discovery_download,
)

from teddy_discovery_variants import (
    persist_title_variant,
)


NOW = (
    "2026-08-28T00:00:00+00:00"
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
        Path(
            path
        ).read_bytes()
    ).hexdigest()


def make_db(
    path,
):
    connection = db.connect(
        path
    )

    db.initialize(
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
            "SW-893 test",
            NOW,
            NOW,
        ),
    )

    connection.commit()

    return connection


def set_availability(
    connection,
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
            "SW-893",
            source,
            status,
            NOW,
            NOW,
            0,
        ),
    )

    connection.commit()


def uncensored_first_smoke():
    with tempfile.TemporaryDirectory(
        prefix="teddy-resolver-uncensored-"
    ) as temp:

        path = (
            Path(temp)
            / "resolver.sqlite3"
        )

        connection = make_db(
            path
        )

        try:
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
                        (
                            "sw-893-"
                            "uncensored-leak"
                        ),

                    "page_url":
                        (
                            "https://missav123.com/"
                            "ko/"
                            "sw-893-"
                            "uncensored-leak"
                        ),

                    "confirmed":
                        1,
                },
                observed_at=NOW,
                checked_at=NOW,
            )

        finally:
            connection.close()

        result = resolve_discovery_download(
            path,
            "SW-893",
        )

        require(
            result[
                "reason"
            ]
            == "confirmed-uncensored",
            "uncensored was not first",
        )

        require(
            result[
                "page_url"
            ]
            == (
                "https://missav123.com/"
                "ko/"
                "sw-893-uncensored-leak"
            ),
            "uncensored URL mismatch",
        )

    print(
        "DOWNLOAD_RESOLVER_UNCENSORED_FIRST_SMOKE=PASS"
    )


def missav_standard_smoke():
    with tempfile.TemporaryDirectory(
        prefix="teddy-resolver-missav-"
    ) as temp:

        path = (
            Path(temp)
            / "resolver.sqlite3"
        )

        connection = make_db(
            path
        )

        try:
            set_availability(
                connection,
                "missav",
                "FOUND",
            )

            set_availability(
                connection,
                "123av",
                "FOUND",
            )

        finally:
            connection.close()

        result = resolve_discovery_download(
            path,
            "SW-893",
        )

        require(
            result[
                "reason"
            ]
            == "missav-standard",
            "MissAV standard not selected",
        )

        require(
            result[
                "page_url"
            ]
            == (
                "https://missav123.com/"
                "ko/sw-893"
            ),
            "preferred MissAV host mismatch",
        )

    print(
        "DOWNLOAD_RESOLVER_MISSAV_STANDARD_SMOKE=PASS"
    )


def fallback_123av_smoke():
    with tempfile.TemporaryDirectory(
        prefix="teddy-resolver-123av-"
    ) as temp:

        path = (
            Path(temp)
            / "resolver.sqlite3"
        )

        connection = make_db(
            path
        )

        try:
            set_availability(
                connection,
                "missav",
                "NOT_FOUND",
            )

            set_availability(
                connection,
                "123av",
                "FOUND",
            )

        finally:
            connection.close()

        result = resolve_discovery_download(
            path,
            "SW-893",
        )

        require(
            result[
                "reason"
            ]
            == "123av-fallback",
            "123AV fallback not selected",
        )

        require(
            result[
                "page_url"
            ]
            == (
                "https://123av.com/"
                "ko/v/sw-893"
            ),
            "123AV URL mismatch",
        )

    print(
        "DOWNLOAD_RESOLVER_123AV_FALLBACK_SMOKE=PASS"
    )


def missav_beats_123av_uncensored_smoke():
    with tempfile.TemporaryDirectory(
        prefix="teddy-resolver-priority-"
    ) as temp:

        path = (
            Path(temp)
            / "resolver.sqlite3"
        )

        connection = make_db(
            path
        )

        try:
            set_availability(
                connection,
                "missav",
                "FOUND",
            )

            set_availability(
                connection,
                "123av",
                "FOUND",
            )

            persist_title_variant(
                connection,
                {
                    "dvd_id":
                        "SW-893",

                    "source":
                        "123av",

                    "variant_kind":
                        "uncensored",

                    "variant_slug":
                        (
                            "sw-893-"
                            "uncensored-leak"
                        ),

                    "page_url":
                        (
                            "https://123av.com/"
                            "ko/v/"
                            "sw-893-"
                            "uncensored-leak"
                        ),

                    "confirmed":
                        1,
                },
                observed_at=NOW,
                checked_at=NOW,
            )

        finally:
            connection.close()

        result = resolve_discovery_download(
            path,
            "SW-893",
        )

        require(
            result[
                "reason"
            ]
            == "missav-standard",
            (
                "123AV uncensored wrongly "
                "beat MissAV standard"
            ),
        )

    print(
        "DOWNLOAD_RESOLVER_MISSAV_BEATS_123AV_UNCENSORED_SMOKE=PASS"
    )


def unavailable_smoke():
    with tempfile.TemporaryDirectory(
        prefix="teddy-resolver-none-"
    ) as temp:

        path = (
            Path(temp)
            / "resolver.sqlite3"
        )

        connection = make_db(
            path
        )

        try:
            set_availability(
                connection,
                "missav",
                "NOT_FOUND",
            )

            set_availability(
                connection,
                "123av",
                "UNKNOWN",
            )

        finally:
            connection.close()

        try:
            resolve_discovery_download(
                path,
                "SW-893",
            )

        except DiscoveryResolveUnavailable:
            pass

        else:
            raise RuntimeError(
                "missing sources did not fail"
            )

    print(
        "DOWNLOAD_RESOLVER_UNAVAILABLE_SMOKE=PASS"
    )


def bad_stored_variant_smoke():
    with tempfile.TemporaryDirectory(
        prefix="teddy-resolver-bad-variant-"
    ) as temp:

        path = (
            Path(temp)
            / "resolver.sqlite3"
        )

        connection = make_db(
            path
        )

        try:
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
                    "SW-893",
                    "missav",
                    "uncensored",
                    (
                        "sw-893-"
                        "uncensored-leak"
                    ),
                    (
                        "https://example.com/"
                        "ko/"
                        "sw-893-"
                        "uncensored-leak"
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

        try:
            resolve_discovery_download(
                path,
                "SW-893",
            )

        except DiscoveryResolveUnavailable:
            pass

        else:
            raise RuntimeError(
                "bad stored variant "
                "did not fail closed"
            )

    print(
        "DOWNLOAD_RESOLVER_BAD_VARIANT_FAIL_CLOSED_SMOKE=PASS"
    )


def strict_input_smoke():
    with tempfile.TemporaryDirectory(
        prefix="teddy-resolver-input-"
    ) as temp:

        path = (
            Path(temp)
            / "resolver.sqlite3"
        )

        connection = make_db(
            path
        )

        connection.close()

        try:
            resolve_discovery_download(
                path,
                "sw-893-uncensored-leak",
            )

        except DiscoveryResolveRequestError:
            pass

        else:
            raise RuntimeError(
                "variant slug accepted "
                "as browser DVD ID"
            )

    print(
        "DOWNLOAD_RESOLVER_STRICT_DVD_ID_SMOKE=PASS"
    )


def title_not_found_smoke():
    with tempfile.TemporaryDirectory(
        prefix="teddy-resolver-title-"
    ) as temp:

        path = (
            Path(temp)
            / "resolver.sqlite3"
        )

        connection = db.connect(
            path
        )

        db.initialize(
            connection
        )

        connection.close()

        try:
            resolve_discovery_download(
                path,
                "SW-893",
            )

        except DiscoveryResolveTitleNotFound:
            pass

        else:
            raise RuntimeError(
                "missing title did not fail"
            )

    print(
        "DOWNLOAD_RESOLVER_TITLE_NOT_FOUND_SMOKE=PASS"
    )


def readonly_smoke():
    with tempfile.TemporaryDirectory(
        prefix="teddy-resolver-readonly-"
    ) as temp:

        path = (
            Path(temp)
            / "resolver.sqlite3"
        )

        connection = make_db(
            path
        )

        try:
            set_availability(
                connection,
                "missav",
                "FOUND",
            )

        finally:
            connection.close()

        before = sha256(
            path
        )

        result = resolve_discovery_download(
            path,
            "SW-893",
        )

        after = sha256(
            path
        )

        require(
            result[
                "reason"
            ]
            == "missav-standard",
            "readonly result mismatch",
        )

        require(
            before == after,
            "resolver changed DB bytes",
        )

    print(
        "DOWNLOAD_RESOLVER_DB_BYTE_UNCHANGED_SMOKE=PASS"
    )


def main():
    uncensored_first_smoke()
    missav_standard_smoke()
    fallback_123av_smoke()
    missav_beats_123av_uncensored_smoke()
    unavailable_smoke()
    bad_stored_variant_smoke()
    strict_input_smoke()
    title_not_found_smoke()
    readonly_smoke()

    print(
        "TEDDY_DISCOVERY_DOWNLOAD_RESOLVER_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
