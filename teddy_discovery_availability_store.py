from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
    timezone,
)
import sqlite3
from typing import Any

from teddy_discovery_availability import (
    AVAILABILITY_SOURCES,
    AVAILABILITY_STATUSES,
    STATUS_FOUND,
    STATUS_NOT_FOUND,
    STATUS_UNKNOWN,
    canonical_dvd_id,
    canonical_page_url,
)


SUCCESS_RECHECK_DAYS = 7

UNKNOWN_BACKOFF_DAYS = (
    1,
    2,
    4,
    7,
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


def canonical_source(
    value: Any,
) -> str:
    source = _text(
        value
    )

    if source not in (
        AVAILABILITY_SOURCES
    ):
        raise ValueError(
            "unsupported availability source"
        )

    return source


def _parse_time(
    value: Any,
    *,
    field: str,
) -> datetime:
    raw = _text(
        value
    )

    if not raw:
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
    value: datetime,
) -> str:
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


def _validated_status(
    value: Any,
) -> str:
    status = _text(
        value
    )

    if status not in (
        AVAILABILITY_STATUSES
    ):
        raise ValueError(
            "invalid availability status"
        )

    return status


def _validated_fail_count(
    value: Any,
) -> int:
    if (
        type(value) is not int
        or value < 0
    ):
        raise RuntimeError(
            "stored availability "
            "fail_count is invalid"
        )

    return value


def _next_check(
    *,
    status: str,
    checked_at: datetime,
    fail_count: int,
) -> datetime:
    if status in (
        STATUS_FOUND,
        STATUS_NOT_FOUND,
    ):
        if fail_count != 0:
            raise ValueError(
                "successful availability "
                "status requires fail_count 0"
            )

        delay_days = (
            SUCCESS_RECHECK_DAYS
        )

    elif status == STATUS_UNKNOWN:
        if fail_count < 1:
            raise ValueError(
                "UNKNOWN requires "
                "positive fail_count"
            )

        index = min(
            fail_count,
            len(
                UNKNOWN_BACKOFF_DAYS
            ),
        ) - 1

        delay_days = (
            UNKNOWN_BACKOFF_DAYS[
                index
            ]
        )

    else:
        raise RuntimeError(
            "unreachable availability status"
        )

    return checked_at + timedelta(
        days=delay_days
    )


def _validate_result(
    result: Any,
) -> dict:
    if not isinstance(
        result,
        dict,
    ):
        raise ValueError(
            "availability result "
            "must be an object"
        )

    source = canonical_source(
        result.get(
            "source"
        )
    )

    dvd_id = canonical_dvd_id(
        result.get(
            "dvd_id"
        )
    )

    status = _validated_status(
        result.get(
            "status"
        )
    )

    page_url = _text(
        result.get(
            "page_url"
        )
    )

    expected_url = canonical_page_url(
        source,
        dvd_id,
    )

    if page_url != expected_url:
        raise ValueError(
            "availability page URL "
            "is not canonical"
        )

    return {
        "source":
            source,

        "dvd_id":
            dvd_id,

        "status":
            status,

        "page_url":
            expected_url,
    }


def persist_availability_result(
    connection: sqlite3.Connection,
    result: Any,
    *,
    checked_at: Any,
) -> dict:
    value = _validate_result(
        result
    )

    checked = _parse_time(
        checked_at,
        field="checked_at",
    )

    if connection.in_transaction:
        raise RuntimeError(
            "availability persistence "
            "requires transaction-free "
            "connection"
        )

    connection.execute(
        "BEGIN IMMEDIATE"
    )

    try:
        existing = connection.execute(
            """
            SELECT
                fail_count
            FROM availability
            WHERE dvd_id = ?
              AND source = ?
            """,
            (
                value[
                    "dvd_id"
                ],
                value[
                    "source"
                ],
            ),
        ).fetchone()

        previous_fail_count = (
            0
            if existing is None
            else _validated_fail_count(
                existing[
                    "fail_count"
                ]
            )
        )

        if value[
            "status"
        ] == STATUS_UNKNOWN:
            fail_count = (
                previous_fail_count
                + 1
            )

        else:
            fail_count = 0

        next_check = _next_check(
            status=value[
                "status"
            ],
            checked_at=checked,
            fail_count=fail_count,
        )

        checked_text = _format_time(
            checked
        )

        next_text = _format_time(
            next_check
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

            ON CONFLICT(
                dvd_id,
                source
            )
            DO UPDATE SET
                status =
                    excluded.status,

                page_url =
                    excluded.page_url,

                last_checked_at =
                    excluded.last_checked_at,

                next_check_at =
                    excluded.next_check_at,

                fail_count =
                    excluded.fail_count
            """,
            (
                value[
                    "dvd_id"
                ],
                value[
                    "source"
                ],
                value[
                    "status"
                ],
                value[
                    "page_url"
                ],
                checked_text,
                next_text,
                fail_count,
            ),
        )

        row = connection.execute(
            """
            SELECT
                dvd_id,
                source,
                status,
                page_url,
                last_checked_at,
                next_check_at,
                fail_count
            FROM availability
            WHERE dvd_id = ?
              AND source = ?
            """,
            (
                value[
                    "dvd_id"
                ],
                value[
                    "source"
                ],
            ),
        ).fetchone()

        if row is None:
            raise RuntimeError(
                "availability write "
                "readback missing"
            )

        readback = dict(
            row
        )

        expected = {
            "dvd_id":
                value[
                    "dvd_id"
                ],

            "source":
                value[
                    "source"
                ],

            "status":
                value[
                    "status"
                ],

            "page_url":
                value[
                    "page_url"
                ],

            "last_checked_at":
                checked_text,

            "next_check_at":
                next_text,

            "fail_count":
                fail_count,
        }

        if readback != expected:
            raise RuntimeError(
                "availability write "
                "readback mismatch"
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    return readback


def read_availability_cache(
    connection: sqlite3.Connection,
    *,
    source: Any,
    dvd_id: Any,
    now: Any,
) -> dict:
    source = canonical_source(
        source
    )

    dvd_id = canonical_dvd_id(
        dvd_id
    )

    now_value = _parse_time(
        now,
        field="now",
    )

    page_url = canonical_page_url(
        source,
        dvd_id,
    )

    row = connection.execute(
        """
        SELECT
            dvd_id,
            source,
            status,
            page_url,
            last_checked_at,
            next_check_at,
            fail_count
        FROM availability
        WHERE dvd_id = ?
          AND source = ?
        """,
        (
            dvd_id,
            source,
        ),
    ).fetchone()

    if row is None:
        return {
            "known":
                False,

            "due":
                True,

            "dvd_id":
                dvd_id,

            "source":
                source,

            "status":
                STATUS_UNKNOWN,

            "page_url":
                page_url,

            "last_checked_at":
                None,

            "next_check_at":
                None,

            "fail_count":
                0,
        }

    value = dict(
        row
    )

    if value[
        "dvd_id"
    ] != dvd_id:
        raise RuntimeError(
            "cached DVD ID mismatch"
        )

    if value[
        "source"
    ] != source:
        raise RuntimeError(
            "cached source mismatch"
        )

    status = _validated_status(
        value[
            "status"
        ]
    )

    if value[
        "page_url"
    ] != page_url:
        raise RuntimeError(
            "cached page URL "
            "is not canonical"
        )

    fail_count = _validated_fail_count(
        value[
            "fail_count"
        ]
    )

    if (
        status
        in (
            STATUS_FOUND,
            STATUS_NOT_FOUND,
        )
        and fail_count != 0
    ):
        raise RuntimeError(
            "cached successful status "
            "has nonzero fail_count"
        )

    if (
        status == STATUS_UNKNOWN
        and fail_count < 1
    ):
        raise RuntimeError(
            "cached UNKNOWN has "
            "invalid fail_count"
        )

    last_checked = _parse_time(
        value[
            "last_checked_at"
        ],
        field="last_checked_at",
    )

    next_check = _parse_time(
        value[
            "next_check_at"
        ],
        field="next_check_at",
    )

    if next_check <= last_checked:
        raise RuntimeError(
            "cached next_check_at "
            "must follow last_checked_at"
        )

    return {
        "known":
            True,

        "due":
            now_value >= next_check,

        "dvd_id":
            dvd_id,

        "source":
            source,

        "status":
            status,

        "page_url":
            page_url,

        "last_checked_at":
            _format_time(
                last_checked
            ),

        "next_check_at":
            _format_time(
                next_check
            ),

        "fail_count":
            fail_count,
    }
