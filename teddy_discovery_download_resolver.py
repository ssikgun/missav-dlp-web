from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any

from teddy_discovery_availability import (
    AVAILABILITY_SOURCES,
    AVAILABILITY_STATUSES,
    SOURCE_123AV,
    SOURCE_MISSAV,
    STATUS_FOUND,
    canonical_dvd_id,
    canonical_page_url,
)

from teddy_discovery_variant_classifier import (
    is_owned_uncensored_missav_url,
)

from teddy_discovery_variant_collector import (
    canonical_standard_missav_url,
)

from teddy_discovery_variants import (
    VARIANT_UNCENSORED,
)


class DiscoveryResolveRequestError(
    ValueError
):
    pass


class DiscoveryResolveUnavailable(
    RuntimeError
):
    pass


class DiscoveryResolveTitleNotFound(
    LookupError
):
    pass


def _open_readonly(
    db_path: Any,
) -> sqlite3.Connection:
    database = Path(
        str(
            db_path
            or ""
        ).strip()
    ).expanduser().resolve()

    if not database.is_file():
        raise DiscoveryResolveUnavailable(
            "Discovery database unavailable"
        )

    try:
        connection = sqlite3.connect(
            "file:"
            + str(
                database
            )
            + "?mode=ro",
            uri=True,
        )

    except sqlite3.Error as exc:
        raise DiscoveryResolveUnavailable(
            "Discovery database unavailable"
        ) from exc

    connection.row_factory = (
        sqlite3.Row
    )

    return connection


def _load_availability(
    connection: sqlite3.Connection,
    dvd_id: str,
) -> dict[str, str]:
    rows = connection.execute(
        """
        SELECT
            source,
            status
        FROM availability
        WHERE dvd_id = ?
        ORDER BY source
        """,
        (
            dvd_id,
        ),
    ).fetchall()

    result = {}

    for row in rows:
        source = row[
            "source"
        ]

        status = row[
            "status"
        ]

        if source not in AVAILABILITY_SOURCES:
            raise DiscoveryResolveUnavailable(
                "stored availability source invalid"
            )

        if status not in AVAILABILITY_STATUSES:
            raise DiscoveryResolveUnavailable(
                "stored availability status invalid"
            )

        if source in result:
            raise DiscoveryResolveUnavailable(
                "duplicate availability source"
            )

        result[
            source
        ] = status

    return result


def _load_confirmed_uncensored(
    connection: sqlite3.Connection,
    dvd_id: str,
) -> dict | None:
    rows = connection.execute(
        """
        SELECT
            dvd_id,
            source,
            variant_kind,
            variant_slug,
            page_url,
            confirmed
        FROM title_variants
        WHERE dvd_id = ?
          AND source = ?
          AND variant_kind = ?
          AND confirmed = 1
        """,
        (
            dvd_id,
            SOURCE_MISSAV,
            VARIANT_UNCENSORED,
        ),
    ).fetchall()

    if not rows:
        return None

    if len(rows) != 1:
        raise DiscoveryResolveUnavailable(
            "ambiguous uncensored variant"
        )

    row = dict(
        rows[0]
    )

    if row[
        "dvd_id"
    ] != dvd_id:
        raise DiscoveryResolveUnavailable(
            "variant DVD ID mismatch"
        )

    if row[
        "source"
    ] != SOURCE_MISSAV:
        raise DiscoveryResolveUnavailable(
            "variant source mismatch"
        )

    if row[
        "variant_kind"
    ] != VARIANT_UNCENSORED:
        raise DiscoveryResolveUnavailable(
            "variant kind mismatch"
        )

    if row[
        "confirmed"
    ] != 1:
        raise DiscoveryResolveUnavailable(
            "variant confirmation mismatch"
        )

    if not is_owned_uncensored_missav_url(
        dvd_id=dvd_id,
        page_url=row[
            "page_url"
        ],
    ):
        raise DiscoveryResolveUnavailable(
            "stored uncensored URL invalid"
        )

    return row


def resolve_discovery_download(
    db_path: Any,
    dvd_id: Any,
) -> dict:
    try:
        dvd_id = canonical_dvd_id(
            dvd_id
        )

    except ValueError as exc:
        raise DiscoveryResolveRequestError(
            "invalid DVD ID"
        ) from exc

    connection = _open_readonly(
        db_path
    )

    try:
        title = connection.execute(
            """
            SELECT dvd_id
            FROM titles
            WHERE dvd_id = ?
            LIMIT 1
            """,
            (
                dvd_id,
            ),
        ).fetchone()

        if title is None:
            raise DiscoveryResolveTitleNotFound(
                "Discovery title not found"
            )

        uncensored = (
            _load_confirmed_uncensored(
                connection,
                dvd_id,
            )
        )

        if uncensored is not None:
            return {
                "dvd_id":
                    dvd_id,

                "source":
                    SOURCE_MISSAV,

                "variant_kind":
                    VARIANT_UNCENSORED,

                "page_url":
                    uncensored[
                        "page_url"
                    ],

                "reason":
                    "confirmed-uncensored",
            }

        availability = (
            _load_availability(
                connection,
                dvd_id,
            )
        )

        if (
            availability.get(
                SOURCE_MISSAV
            )
            == STATUS_FOUND
        ):
            return {
                "dvd_id":
                    dvd_id,

                "source":
                    SOURCE_MISSAV,

                "variant_kind":
                    "standard",

                "page_url":
                    canonical_standard_missav_url(
                        dvd_id
                    ),

                "reason":
                    "missav-standard",
            }

        if (
            availability.get(
                SOURCE_123AV
            )
            == STATUS_FOUND
        ):
            return {
                "dvd_id":
                    dvd_id,

                "source":
                    SOURCE_123AV,

                "variant_kind":
                    "standard",

                "page_url":
                    canonical_page_url(
                        SOURCE_123AV,
                        dvd_id,
                    ),

                "reason":
                    "123av-fallback",
            }

        raise DiscoveryResolveUnavailable(
            "no confirmed download target"
        )

    except sqlite3.Error as exc:
        raise DiscoveryResolveUnavailable(
            "Discovery data unavailable"
        ) from exc

    finally:
        connection.close()
