from __future__ import annotations

import argparse
import json
import os
from typing import Any
from urllib.parse import urlparse

from teddy_discovery_variant_batch import (
    DEFAULT_NEAR_FUTURE_DAYS,
)

from teddy_discovery_variant_job import (
    DEFAULT_DELAY_SECONDS,
    DEFAULT_MAX_ITEMS,
    DEFAULT_RECHECK_AFTER_HOURS,
    DEFAULT_TIMEOUT_SECONDS,
    run_variant_probe_batch,
)


PROXY_ENV = "GLUETUN_PROXY_URL"


def _required_fixed_proxy(
    environ: Any = None,
) -> str:
    if environ is None:
        environ = os.environ

    value = str(
        environ.get(
            PROXY_ENV,
            "",
        )
        or ""
    ).strip()

    if not value:
        raise RuntimeError(
            "fixed VPN proxy is required"
        )

    parsed = urlparse(
        value
    )

    if (
        parsed.scheme != "http"
        or parsed.hostname != "gluetun"
        or parsed.port != 8888
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {
            "",
            "/",
        }
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError(
            "fixed VPN proxy must be "
            "http://gluetun:8888"
        )

    return "http://gluetun:8888"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run bounded Teddy Discovery "
            "MissAV variant probes"
        )
    )

    parser.add_argument(
        "--db",
        required=True,
    )

    parser.add_argument(
        "--max-items",
        type=int,
        default=DEFAULT_MAX_ITEMS,
    )

    parser.add_argument(
        "--recheck-after-hours",
        type=int,
        default=DEFAULT_RECHECK_AFTER_HOURS,
    )

    parser.add_argument(
        "--near-future-days",
        type=int,
        default=DEFAULT_NEAR_FUTURE_DAYS,
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


def run_cli(
    argv=None,
    *,
    environ=None,
    batch_runner=run_variant_probe_batch,
) -> tuple[int, dict]:
    args = _parser().parse_args(
        argv
    )

    proxy_url = _required_fixed_proxy(
        environ
    )

    result = batch_runner(
        args.db,
        max_items=args.max_items,
        recheck_after_hours=(
            args.recheck_after_hours
        ),
        near_future_days=(
            args.near_future_days
        ),
        delay_seconds=(
            args.delay_seconds
        ),
        timeout=args.timeout,
        proxy_url=proxy_url,
    )

    if not isinstance(
        result,
        dict,
    ):
        raise RuntimeError(
            "variant job result invalid"
        )

    code = (
        1
        if result.get(
            "degraded"
        )
        else 0
    )

    return (
        code,
        result,
    )


def main(
    argv=None,
) -> int:
    code, result = run_cli(
        argv
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
        )
    )

    return code


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
