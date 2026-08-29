from __future__ import annotations

from datetime import (
    datetime,
    timezone,
)
from pathlib import Path
import sqlite3
import time
from typing import Any

from teddy_discovery_variant_batch import (
    DEFAULT_NEAR_FUTURE_DAYS,
    build_variant_probe_plan,
)

from teddy_discovery_variant_collector import (
    run_variant_collection,
)


DEFAULT_MAX_ITEMS = 50
DEFAULT_RECHECK_AFTER_HOURS = 24
DEFAULT_DELAY_SECONDS = 1.0
DEFAULT_TIMEOUT_SECONDS = 45


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )


def _validate_delay(
    value: Any,
) -> float:
    if (
        isinstance(
            value,
            bool,
        )
        or not isinstance(
            value,
            (
                int,
                float,
            ),
        )
    ):
        raise ValueError(
            "delay_seconds must be numeric"
        )

    value = float(
        value
    )

    if (
        value < 0
        or value > 30
    ):
        raise ValueError(
            "delay_seconds must be 0..30"
        )

    return value


def _open_ro(
    db_path: str | Path,
) -> sqlite3.Connection:
    path = Path(
        db_path
    ).expanduser().resolve()

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


def run_variant_probe_batch(
    db_path: str | Path,
    *,
    now: Any = None,
    max_items: int = DEFAULT_MAX_ITEMS,
    recheck_after_hours: int = (
        DEFAULT_RECHECK_AFTER_HOURS
    ),
    near_future_days: int = (
        DEFAULT_NEAR_FUTURE_DAYS
    ),
    delay_seconds: float = (
        DEFAULT_DELAY_SECONDS
    ),
    timeout: int = (
        DEFAULT_TIMEOUT_SECONDS
    ),
    session=None,
    proxy_url: Any = None,
    collector_runner=(
        run_variant_collection
    ),
    sleeper=time.sleep,
) -> dict:
    delay_seconds = _validate_delay(
        delay_seconds
    )

    if (
        type(timeout) is not int
        or timeout < 1
        or timeout > 120
    ):
        raise ValueError(
            "timeout must be 1..120"
        )

    if now is None:
        now = utc_now()

    connection = _open_ro(
        db_path
    )

    try:
        plan = build_variant_probe_plan(
            connection,
            now=now,
            max_items=max_items,
            recheck_after_hours=
                recheck_after_hours,
            near_future_days=
                near_future_days,
        )

    finally:
        connection.close()

    selected = list(
        plan[
            "selected"
        ]
    )

    completed = []
    failures = []

    found_uncensored_count = 0
    standard_watermark_count = 0

    for index, item in enumerate(
        selected
    ):
        dvd_id = item[
            "dvd_id"
        ]

        try:
            result = collector_runner(
                db_path,
                dvd_id,
                session=session,
                proxy_url=proxy_url,
                timeout=timeout,
            )

        except Exception as exc:
            failures.append({
                "dvd_id":
                    dvd_id,

                "error_type":
                    type(
                        exc
                    ).__name__,

                "error":
                    str(
                        exc
                    ),
            })

        else:
            completed.append({
                "dvd_id":
                    dvd_id,

                "found":
                    result.get(
                        "found"
                    ),

                "method":
                    result.get(
                        "method"
                    ),

                "stored":
                    result.get(
                        "stored"
                    ),

                "standard_observation_stored":
                    result.get(
                        "standard_observation_stored",
                        False,
                    ),
            })

            if result.get(
                "found"
            ) is True:
                found_uncensored_count += 1

            if result.get(
                "standard_observation_stored"
            ) is True:
                standard_watermark_count += 1

        if (
            index
            < len(
                selected
            )
            - 1
            and delay_seconds > 0
        ):
            sleeper(
                delay_seconds
            )

    return {
        "generated_at":
            plan[
                "generated_at"
            ],

        "plan":
            plan,

        "selected_count":
            len(
                selected
            ),

        "completed_count":
            len(
                completed
            ),

        "failed_count":
            len(
                failures
            ),

        "found_uncensored_count":
            found_uncensored_count,

        "standard_watermark_count":
            standard_watermark_count,

        "completed":
            completed,

        "failures":
            failures,

        "degraded":
            bool(
                failures
            ),
    }
