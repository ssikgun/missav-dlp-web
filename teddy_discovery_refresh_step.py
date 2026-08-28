from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from teddy_discovery_collector import (
    run_release_collection,
)

from teddy_discovery_javdatabase_collector import (
    run_weekly_collection,
)

from teddy_discovery_refresh import (
    DEFAULT_DELAY_SECONDS,
    DEFAULT_METADATA_MAX,
    DEFAULT_TIMEOUT_SECONDS,
    enrich_pending_metadata,
    exit_code_for_result,
    run_locked_refresh,
)


STEP_RELEASE = "release"
STEP_WEEKLY = "weekly"
STEP_METADATA = "metadata"

ALLOWED_STEPS = (
    STEP_RELEASE,
    STEP_WEEKLY,
    STEP_METADATA,
)


def _skipped_core(
    db_path,
    *,
    timeout,
) -> dict:
    return {}


def _skipped_metadata(
    db_path,
    *,
    max_items,
    delay_seconds,
    timeout,
) -> dict:
    return {
        "candidate_count": 0,
        "request_count": 0,
        "direct_count": 0,
        "fallback_count": 0,
        "not_found_count": 0,
        "failed_count": 0,
        "skipped_count": 0,
        "results": [],
    }


def run_refresh_step(
    db_path: str | Path,
    step: str,
    *,
    metadata_max: int = DEFAULT_METADATA_MAX,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    release_runner=run_release_collection,
    weekly_runner=run_weekly_collection,
    metadata_runner=enrich_pending_metadata,
) -> dict:
    step = str(
        step
    ).strip().lower()

    if step not in ALLOWED_STEPS:
        raise ValueError(
            "refresh step must be "
            "release, weekly or metadata"
        )

    selected_release = (
        release_runner
        if step == STEP_RELEASE
        else _skipped_core
    )

    selected_weekly = (
        weekly_runner
        if step == STEP_WEEKLY
        else _skipped_core
    )

    selected_metadata = (
        metadata_runner
        if step == STEP_METADATA
        else _skipped_metadata
    )

    result = run_locked_refresh(
        db_path,
        metadata_max=metadata_max,
        delay_seconds=delay_seconds,
        timeout=timeout,
        release_runner=selected_release,
        weekly_runner=selected_weekly,
        metadata_runner=selected_metadata,
    )

    if not isinstance(
        result,
        dict,
    ):
        raise RuntimeError(
            "refresh step result invalid"
        )

    result = dict(
        result
    )

    result[
        "requested_step"
    ] = step

    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run one Teddy Discovery "
            "refresh step"
        )
    )

    parser.add_argument(
        "--db",
        required=True,
    )

    parser.add_argument(
        "--step",
        required=True,
        choices=ALLOWED_STEPS,
    )

    parser.add_argument(
        "--metadata-max",
        type=int,
        default=DEFAULT_METADATA_MAX,
    )

    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=DEFAULT_DELAY_SECONDS,
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
    )

    return parser


def main(
    argv: Any = None,
) -> int:
    args = _parser().parse_args(
        argv
    )

    result = run_refresh_step(
        args.db,
        args.step,
        metadata_max=args.metadata_max,
        delay_seconds=args.delay_seconds,
        timeout=args.timeout,
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
        )
    )

    return exit_code_for_result(
        result
    )


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
