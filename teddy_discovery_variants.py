from __future__ import annotations

from datetime import (
    datetime,
    timezone,
)
import sqlite3
from typing import Any
from urllib.parse import urlparse

from teddy_discovery_availability import (
    AVAILABILITY_SOURCES,
    SOURCE_123AV,
    SOURCE_MISSAV,
)
from teddy_discovery_ids import (
    parse_dvd_id,
)
from teddy_routing import (
    canonical_site,
)


VARIANT_STANDARD = "standard"
VARIANT_UNCENSORED = "uncensored"

VARIANT_KINDS = (
    VARIANT_STANDARD,
    VARIANT_UNCENSORED,
)


def _text(
    value: Any,
) -> str | None:
    if value is None:
        return None

    value = " ".join(
        str(value).split()
    )

    return value or None


def canonical_variant_dvd_id(
    value: Any,
) -> str:
    raw = _text(
        value
    )

    if not raw:
        raise ValueError(
            "variant DVD ID missing"
        )

    parsed = parse_dvd_id(
        raw
    )

    if parsed is None:
        raise ValueError(
            "invalid variant DVD ID"
        )

    return parsed.dvd_id


def canonical_variant_source(
    value: Any,
) -> str:
    source = _text(
        value
    )

    if source not in AVAILABILITY_SOURCES:
        raise ValueError(
            "unsupported variant source"
        )

    return source


def canonical_variant_kind(
    value: Any,
) -> str:
    kind = _text(
        value
    )

    if kind not in VARIANT_KINDS:
        raise ValueError(
            "unsupported variant kind"
        )

    return kind


def _parse_time(
    value: Any,
    *,
    field: str,
    allow_none: bool = False,
) -> datetime | None:
    raw = _text(
        value
    )

    if not raw:
        if allow_none:
            return None

        raise ValueError(
            field
            + " missing"
        )

    try:
        parsed = datetime.fromisoformat(
            raw
        )

    except ValueError as exc:
        raise ValueError(
            field
            + " must be ISO-8601"
        ) from exc

    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
    ):
        raise ValueError(
            field
            + " must be timezone-aware"
        )

    return parsed.astimezone(
        timezone.utc
    ).replace(
        microsecond=0
    )


def _format_time(
    value: datetime | None,
) -> str | None:
    if value is None:
        return None

    if (
        value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(
            "timestamp must be timezone-aware"
        )

    return (
        value.astimezone(
            timezone.utc
        )
        .replace(
            microsecond=0
        )
        .isoformat()
    )


def _validated_confirmed(
    value: Any,
) -> int:
    if isinstance(
        value,
        bool,
    ):
        return int(
            value
        )

    if (
        type(value) is int
        and value in (0, 1)
    ):
        return value

    raise ValueError(
        "confirmed must be 0 or 1"
    )


def _validate_page_url(
    *,
    source: str,
    dvd_id: str,
    page_url: Any,
) -> str:
    page_url = _text(
        page_url
    )

    if not page_url:
        raise ValueError(
            "variant page URL missing"
        )

    parsed = urlparse(
        page_url
    )

    if (
        parsed.scheme.lower()
        not in (
            "http",
            "https",
        )
        or not parsed.hostname
    ):
        raise ValueError(
            "variant page URL invalid"
        )

    owned_dvd_id = (
        canonical_variant_dvd_id(
            page_url
        )
    )

    if owned_dvd_id != dvd_id:
        raise ValueError(
            "variant page URL DVD ID mismatch"
        )

    host = (
        parsed.hostname
        or ""
    ).lower().rstrip(".")

    if host.startswith(
        "www."
    ):
        host = host[4:]

    if source == SOURCE_MISSAV:
        if canonical_site(
            page_url
        ) != SOURCE_MISSAV:
            raise ValueError(
                "MissAV variant URL "
                "is outside MissAV family"
            )

    elif source == SOURCE_123AV:
        if not (
            host == "123av.com"
            or host.endswith(
                ".123av.com"
            )
        ):
            raise ValueError(
                "123AV variant URL "
                "is outside 123AV family"
            )

    else:
        raise RuntimeError(
            "unreachable variant source"
        )

    return page_url


def _validate_variant(
    value: Any,
) -> dict:
    if not isinstance(
        value,
        dict,
    ):
        raise ValueError(
            "variant must be an object"
        )

    dvd_id = (
        canonical_variant_dvd_id(
            value.get(
                "dvd_id"
            )
        )
    )

    source = (
        canonical_variant_source(
            value.get(
                "source"
            )
        )
    )

    variant_kind = (
        canonical_variant_kind(
            value.get(
                "variant_kind"
            )
        )
    )

    variant_slug = _text(
        value.get(
            "variant_slug"
        )
    )

    if not variant_slug:
        raise ValueError(
            "variant slug missing"
        )

    if "/" in variant_slug:
        raise ValueError(
            "variant slug must not contain slash"
        )

    slug_dvd_id = (
        canonical_variant_dvd_id(
            variant_slug
        )
    )

    if slug_dvd_id != dvd_id:
        raise ValueError(
            "variant slug DVD ID mismatch"
        )

    page_url = _validate_page_url(
        source=source,
        dvd_id=dvd_id,
        page_url=value.get(
            "page_url"
        ),
    )

    confirmed = (
        _validated_confirmed(
            value.get(
                "confirmed"
            )
        )
    )

    return {
        "dvd_id":
            dvd_id,

        "source":
            source,

        "variant_kind":
            variant_kind,

        "variant_slug":
            variant_slug,

        "page_url":
            page_url,

        "confirmed":
            confirmed,
    }


def persist_title_variant(
    connection: sqlite3.Connection,
    variant: Any,
    *,
    observed_at: Any,
    checked_at: Any = None,
) -> dict:
    value = _validate_variant(
        variant
    )

    observed = _parse_time(
        observed_at,
        field="observed_at",
    )

    checked = _parse_time(
        checked_at,
        field="checked_at",
        allow_none=True,
    )

    observed_text = (
        _format_time(
            observed
        )
    )

    checked_text = (
        _format_time(
            checked
        )
    )

    if connection.in_transaction:
        raise RuntimeError(
            "variant persistence "
            "requires transaction-free "
            "connection"
        )

    connection.execute(
        "BEGIN IMMEDIATE"
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
            VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?
            )

            ON CONFLICT(
                dvd_id,
                source,
                variant_kind
            )
            DO UPDATE SET
                variant_slug =
                    excluded.variant_slug,

                page_url =
                    excluded.page_url,

                confirmed =
                    excluded.confirmed,

                last_seen_at =
                    CASE
                        WHEN (
                            excluded.last_seen_at
                            > title_variants.last_seen_at
                        )
                        THEN excluded.last_seen_at
                        ELSE title_variants.last_seen_at
                    END,

                last_checked_at =
                    CASE
                        WHEN excluded.last_checked_at IS NULL
                        THEN title_variants.last_checked_at

                        WHEN title_variants.last_checked_at IS NULL
                        THEN excluded.last_checked_at

                        WHEN (
                            excluded.last_checked_at
                            > title_variants.last_checked_at
                        )
                        THEN excluded.last_checked_at

                        ELSE title_variants.last_checked_at
                    END
            """,
            (
                value[
                    "dvd_id"
                ],
                value[
                    "source"
                ],
                value[
                    "variant_kind"
                ],
                value[
                    "variant_slug"
                ],
                value[
                    "page_url"
                ],
                value[
                    "confirmed"
                ],
                observed_text,
                observed_text,
                checked_text,
            ),
        )

        row = connection.execute(
            """
            SELECT
                dvd_id,
                source,
                variant_kind,
                variant_slug,
                page_url,
                confirmed,
                first_seen_at,
                last_seen_at,
                last_checked_at
            FROM title_variants
            WHERE dvd_id = ?
              AND source = ?
              AND variant_kind = ?
            """,
            (
                value[
                    "dvd_id"
                ],
                value[
                    "source"
                ],
                value[
                    "variant_kind"
                ],
            ),
        ).fetchone()

        if row is None:
            raise RuntimeError(
                "variant write readback missing"
            )

        readback = dict(
            row
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    return readback


def read_title_variants(
    connection: sqlite3.Connection,
    *,
    dvd_id: Any,
    source: Any = None,
    confirmed_only: bool = False,
) -> list[dict]:
    dvd_id = (
        canonical_variant_dvd_id(
            dvd_id
        )
    )

    clauses = [
        "dvd_id = ?",
    ]

    params: list[Any] = [
        dvd_id,
    ]

    if source is not None:
        source = (
            canonical_variant_source(
                source
            )
        )

        clauses.append(
            "source = ?"
        )

        params.append(
            source
        )

    if confirmed_only:
        clauses.append(
            "confirmed = 1"
        )

    sql = """
        SELECT
            dvd_id,
            source,
            variant_kind,
            variant_slug,
            page_url,
            confirmed,
            first_seen_at,
            last_seen_at,
            last_checked_at
        FROM title_variants
        WHERE
    """

    sql += (
        " AND ".join(
            clauses
        )
    )

    sql += """
        ORDER BY
            source ASC,
            variant_kind ASC
    """

    rows = connection.execute(
        sql,
        tuple(
            params
        ),
    ).fetchall()

    return [
        dict(
            row
        )
        for row in rows
    ]
