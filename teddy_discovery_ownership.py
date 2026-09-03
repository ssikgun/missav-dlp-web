from __future__ import annotations

import sqlite3


CANONICAL_STORAGE_ROOT = "jav"
CANONICAL_PARSE_STATUS = "MATCHED"


def is_canonical_present_holding(
    row: dict,
) -> bool:
    return (
        row.get("storage_root")
        == CANONICAL_STORAGE_ROOT
        and row.get("parse_status")
        == CANONICAL_PARSE_STATUS
        and int(row.get("present") or 0)
        == 1
    )


def has_canonical_present_holding(
    connection: sqlite3.Connection,
    dvd_id: str,
) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM holdings
        WHERE storage_root = ?
          AND dvd_id = ?
          AND parse_status = ?
          AND present = 1
        LIMIT 1
        """,
        (
            CANONICAL_STORAGE_ROOT,
            dvd_id,
            CANONICAL_PARSE_STATUS,
        ),
    ).fetchone()

    return row is not None
