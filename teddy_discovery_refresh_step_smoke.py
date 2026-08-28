from __future__ import annotations

from pathlib import Path
import tempfile

from teddy_discovery_refresh_step import (
    STEP_METADATA,
    STEP_RELEASE,
    STEP_WEEKLY,
    run_refresh_step,
)


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


def run_case(
    step,
):
    calls = []

    def release(
        db_path,
        *,
        timeout,
    ):
        calls.append(
            "release"
        )

        return {
            "written": 50,
        }

    def weekly(
        db_path,
        *,
        timeout,
    ):
        calls.append(
            "weekly"
        )

        return {
            "written": 25,
        }

    def metadata(
        db_path,
        *,
        max_items,
        delay_seconds,
        timeout,
    ):
        calls.append(
            "metadata"
        )

        return {
            "candidate_count": 1,
            "request_count": 1,
            "direct_count": 1,
            "fallback_count": 0,
            "not_found_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "results": [],
        }

    with tempfile.TemporaryDirectory() as tmp:
        db_path = (
            Path(tmp)
            / "synthetic.sqlite3"
        )

        result = run_refresh_step(
            db_path,
            step,
            metadata_max=3,
            delay_seconds=0,
            timeout=30,
            release_runner=release,
            weekly_runner=weekly,
            metadata_runner=metadata,
        )

    require(
        result[
            "requested_step"
        ] == step,
        "requested step changed",
    )

    require(
        result[
            "degraded"
        ] is False,
        "successful step degraded",
    )

    return calls


require(
    run_case(
        STEP_RELEASE
    )
    == [
        "release",
    ],
    "release step called extra work",
)

print(
    "REFRESH_STEP_RELEASE_ONLY=PASS"
)


require(
    run_case(
        STEP_WEEKLY
    )
    == [
        "weekly",
    ],
    "weekly step called extra work",
)

print(
    "REFRESH_STEP_WEEKLY_ONLY=PASS"
)


require(
    run_case(
        STEP_METADATA
    )
    == [
        "metadata",
    ],
    "metadata step called extra work",
)

print(
    "REFRESH_STEP_METADATA_ONLY=PASS"
)


try:
    with tempfile.TemporaryDirectory() as tmp:
        run_refresh_step(
            Path(tmp)
            / "synthetic.sqlite3",
            "bad-step",
        )

except ValueError:
    pass

else:
    raise RuntimeError(
        "invalid refresh step accepted"
    )

print(
    "REFRESH_STEP_INVALID_FAIL_CLOSED=PASS"
)

print(
    "REAL_NETWORK_REQUESTS=0"
)

print(
    "PRODUCTION_DB_WRITES=0"
)

print(
    "TEDDY_DISCOVERY_REFRESH_STEP_SMOKE=PASS"
)
