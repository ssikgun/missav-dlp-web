from __future__ import annotations

import contextlib
import io

import teddy_discovery_variant_runner as runner


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


calls = []


default_args = runner._parser().parse_args(
    [
        "--db",
        "/tmp/default.sqlite3",
    ]
)

require(
    default_args.max_items == 50,
    "default max items must be 50",
)

print(
    "VARIANT_RUNNER_DEFAULT_MAX_ITEMS_50_PASS=PASS"
)


def fake_batch(
    db_path,
    **kwargs,
):
    calls.append(
        (
            db_path,
            kwargs,
        )
    )

    return {
        "selected_count": 1,
        "completed_count": 1,
        "failed_count": 0,
        "found_uncensored_count": 0,
        "standard_watermark_count": 1,
        "degraded": False,
    }


code, result = runner.run_cli(
    [
        "--db",
        "/tmp/test.sqlite3",
        "--max-items",
        "3",
        "--recheck-after-hours",
        "18",
        "--near-future-days",
        "7",
        "--delay-seconds",
        "2",
        "--timeout",
        "30",
    ],
    environ={
        "GLUETUN_PROXY_URL":
            "http://gluetun:8888",
    },
    batch_runner=fake_batch,
)

require(
    code == 0,
    "success exit code changed",
)

require(
    result[
        "completed_count"
    ] == 1,
    "result changed",
)

require(
    len(calls) == 1,
    "batch call count changed",
)

db_path, kwargs = calls[0]

require(
    db_path == "/tmp/test.sqlite3",
    "DB argument changed",
)

require(
    kwargs[
        "proxy_url"
    ] == "http://gluetun:8888",
    "fixed VPN proxy not passed",
)

require(
    kwargs[
        "max_items"
    ] == 3,
    "max items changed",
)

require(
    kwargs[
        "recheck_after_hours"
    ] == 18,
    "recheck setting changed",
)

require(
    kwargs[
        "near_future_days"
    ] == 7,
    "near-future setting changed",
)

require(
    kwargs[
        "delay_seconds"
    ] == 2.0,
    "delay changed",
)

require(
    kwargs[
        "timeout"
    ] == 30,
    "timeout changed",
)

print(
    "VARIANT_RUNNER_FIXED_VPN_PASS=PASS"
)

print(
    "VARIANT_RUNNER_ARGUMENTS_PASS=PASS"
)


for environ in (
    {},
    {
        "GLUETUN_PROXY_URL":
            "http://example.com:8888",
    },
    {
        "GLUETUN_PROXY_URL":
            "https://gluetun:8888",
    },
):
    try:
        runner.run_cli(
            [
                "--db",
                "/tmp/test.sqlite3",
            ],
            environ=environ,
            batch_runner=fake_batch,
        )

    except RuntimeError:
        pass

    else:
        raise RuntimeError(
            "unsafe proxy accepted"
        )


print(
    "VARIANT_RUNNER_FAIL_CLOSED_PASS=PASS"
)


degraded_calls = []


def degraded_batch(
    db_path,
    **kwargs,
):
    degraded_calls.append(
        db_path
    )

    return {
        "selected_count": 1,
        "completed_count": 0,
        "failed_count": 1,
        "found_uncensored_count": 0,
        "standard_watermark_count": 0,
        "degraded": True,
    }


code, _ = runner.run_cli(
    [
        "--db",
        "/tmp/test.sqlite3",
    ],
    environ={
        "GLUETUN_PROXY_URL":
            "http://gluetun:8888",
    },
    batch_runner=degraded_batch,
)

require(
    code == 1,
    "degraded exit code changed",
)

require(
    degraded_calls
    == [
        "/tmp/test.sqlite3",
    ],
    "degraded runner call changed",
)

print(
    "VARIANT_RUNNER_DEGRADED_PASS=PASS"
)

print(
    "REAL_NETWORK_REQUESTS=0"
)

print(
    "PRODUCTION_DB_WRITES=0"
)

print(
    "TEDDY_DISCOVERY_VARIANT_RUNNER_SMOKE=PASS"
)
