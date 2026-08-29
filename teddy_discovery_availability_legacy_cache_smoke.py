from __future__ import annotations

import sqlite3

from teddy_discovery_availability import (
    SOURCE_123AV,
    SOURCE_MISSAV,
    canonical_page_url,
)

from teddy_discovery_availability_store import (
    read_availability_cache,
)


NOW = "2026-08-29T04:55:00+00:00"


def connection_with_row(
    *,
    dvd_id,
    source,
    page_url,
):
    connection = sqlite3.connect(
        ":memory:"
    )

    connection.row_factory = sqlite3.Row

    connection.execute(
        """
        CREATE TABLE availability(
            dvd_id TEXT NOT NULL,
            source TEXT NOT NULL,
            status TEXT NOT NULL,
            page_url TEXT NOT NULL,
            last_checked_at TEXT NOT NULL,
            next_check_at TEXT NOT NULL,
            fail_count INTEGER NOT NULL,
            PRIMARY KEY(
                dvd_id,
                source
            )
        )
        """
    )

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
            source,
            "FOUND",
            page_url,
            "2026-08-28T00:00:00+00:00",
            "2026-09-04T00:00:00+00:00",
            0,
        ),
    )

    connection.commit()

    return connection


def require(
    value,
    message,
):
    if not value:
        raise RuntimeError(
            message
        )


def accepted(
    *,
    dvd_id,
    source,
    page_url,
):
    connection = connection_with_row(
        dvd_id=dvd_id,
        source=source,
        page_url=page_url,
    )

    try:
        result = read_availability_cache(
            connection,
            source=source,
            dvd_id=dvd_id,
            now=NOW,
        )

    finally:
        connection.close()

    require(
        result["known"] is True,
        "compatible row was not known",
    )

    require(
        result["due"] is False,
        "compatible fresh row became due",
    )

    require(
        result["page_url"]
        == canonical_page_url(
            source,
            dvd_id,
        ),
        "cache did not expose current canonical URL",
    )


def rejected(
    *,
    dvd_id,
    source,
    page_url,
):
    connection = connection_with_row(
        dvd_id=dvd_id,
        source=source,
        page_url=page_url,
    )

    try:
        try:
            read_availability_cache(
                connection,
                source=source,
                dvd_id=dvd_id,
                now=NOW,
            )

        except RuntimeError:
            return

        raise RuntimeError(
            "incompatible cached URL was accepted"
        )

    finally:
        connection.close()


def main():
    accepted(
        dvd_id="JUR-821",
        source=SOURCE_MISSAV,
        page_url=(
            "https://missav.ws/ko/"
            "jur-821"
        ),
    )

    accepted(
        dvd_id="JUR-821",
        source=SOURCE_MISSAV,
        page_url=(
            "https://missav01.com/ko/"
            "jur-821"
        ),
    )

    accepted(
        dvd_id="JUR-821",
        source=SOURCE_MISSAV,
        page_url=canonical_page_url(
            SOURCE_MISSAV,
            "JUR-821",
        ),
    )

    rejected(
        dvd_id="JUR-821",
        source=SOURCE_MISSAV,
        page_url=(
            "https://example.com/ko/"
            "jur-821"
        ),
    )

    rejected(
        dvd_id="JUR-821",
        source=SOURCE_MISSAV,
        page_url=(
            "https://missav.ws/ko/"
            "wrong-001"
        ),
    )

    accepted(
        dvd_id="JUR-821",
        source=SOURCE_123AV,
        page_url=canonical_page_url(
            SOURCE_123AV,
            "JUR-821",
        ),
    )

    rejected(
        dvd_id="JUR-821",
        source=SOURCE_123AV,
        page_url=(
            "https://missav.ws/ko/"
            "jur-821"
        ),
    )

    print(
        "AVAILABILITY_LEGACY_MISSAV_WS_CACHE_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_LEGACY_MISSAV01_CACHE_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_PREFERRED_MISSAV123_CACHE_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_ARBITRARY_CACHE_URL_FAIL_CLOSED_SMOKE=PASS"
    )

    print(
        "AVAILABILITY_123AV_CACHE_BOUNDARY_SMOKE=PASS"
    )

    print(
        "TEDDY_AVAILABILITY_LEGACY_CACHE_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
