from datetime import (
    datetime,
    timedelta,
    timezone,
)
from pathlib import Path
import tempfile

from teddy_discovery_db import (
    connect,
    initialize,
)

from teddy_discovery_fanza import (
    FANZA_QUERY_ENDPOINT,
    RAPIDAPI_AUTO_BUDGET,
    RAPIDAPI_PROVIDER,
    rapidapi_budget_state,
    record_rapidapi_usage,
    require_rapidapi_budget,
    rolling_rapidapi_usage,
)


def require(
    condition,
    message,
):
    if not condition:
        raise RuntimeError(
            message
        )


def stamp(
    value,
):
    return value.isoformat(
        timespec="seconds"
    )


def main():
    now = datetime(
        2026,
        8,
        29,
        0,
        0,
        0,
        tzinfo=timezone.utc,
    )

    with tempfile.TemporaryDirectory(
        prefix=
            "teddy-fanza-budget-smoke-"
    ) as temp:
        path = (
            Path(temp)
            / "discovery.sqlite3"
        )

        connection = connect(
            path
        )

        initialize(
            connection
        )

        # Old forensic request outside the
        # rolling window must not consume
        # the current automatic budget.
        record_rapidapi_usage(
            connection,
            endpoint="/movie",
            requested_at=stamp(
                now
                - timedelta(days=31)
            ),
            success=True,
            http_status=200,
            quota_limit=100,
            quota_remaining=99,
        )

        require(
            rolling_rapidapi_usage(
                connection,
                now=now,
            ) == 0,
            "old request consumed "
            "rolling budget",
        )

        # /movie and /query share the same
        # RapidAPI account budget.
        record_rapidapi_usage(
            connection,
            endpoint="/movie",
            requested_at=stamp(
                now
                - timedelta(days=1)
            ),
            success=True,
            http_status=200,
            quota_limit=100,
            quota_remaining=99,
        )

        require(
            rolling_rapidapi_usage(
                connection,
                now=now,
            ) == 1,
            "/movie did not count "
            "toward shared budget",
        )

        state = rapidapi_budget_state(
            connection,
            now=now,
        )

        require(
            state["allowed"] is True,
            "fresh budget unexpectedly "
            "blocked",
        )

        require(
            state["used"] == 1,
            "budget used count changed",
        )

        # Fill to one below the automatic
        # ceiling. Keep quota telemetry
        # above the safety margin.
        for offset in range(
            2,
            RAPIDAPI_AUTO_BUDGET,
        ):
            record_rapidapi_usage(
                connection,
                endpoint=
                    FANZA_QUERY_ENDPOINT,
                requested_at=stamp(
                    now
                    - timedelta(
                        minutes=offset
                    )
                ),
                success=True,
                http_status=200,
                quota_limit=100,
                quota_remaining=50,
            )

        state = rapidapi_budget_state(
            connection,
            now=now,
        )

        require(
            state["used"]
            == (
                RAPIDAPI_AUTO_BUDGET
                - 1
            ),
            "pre-ceiling usage "
            "count changed",
        )

        require(
            state["allowed"] is True,
            "request below ceiling "
            "was blocked",
        )

        require_rapidapi_budget(
            connection,
            now=now,
        )

        # One more accounted request
        # reaches the automatic stop
        # boundary. Future automatic
        # requests must be blocked.
        record_rapidapi_usage(
            connection,
            endpoint=
                FANZA_QUERY_ENDPOINT,
            requested_at=stamp(
                now
            ),
            success=True,
            http_status=200,
            quota_limit=100,
            quota_remaining=49,
        )

        state = rapidapi_budget_state(
            connection,
            now=now,
        )

        require(
            state["used"]
            == RAPIDAPI_AUTO_BUDGET,
            "ceiling usage changed",
        )

        require(
            state["allowed"] is False,
            "rolling ceiling did "
            "not block",
        )

        require(
            state["reason"]
            == (
                "rolling_budget_exhausted"
            ),
            "rolling block reason "
            "changed",
        )

        blocked = False

        try:
            require_rapidapi_budget(
                connection,
                now=now,
            )
        except RuntimeError:
            blocked = True

        require(
            blocked,
            "budget exhaustion "
            "did not fail closed",
        )

        # Separate DB proves the upstream
        # quota margin blocks even when
        # local rolling usage is low.
        path2 = (
            Path(temp)
            / "quota.sqlite3"
        )

        connection2 = connect(
            path2
        )

        initialize(
            connection2
        )

        record_rapidapi_usage(
            connection2,
            endpoint=
                FANZA_QUERY_ENDPOINT,
            requested_at=stamp(
                now
            ),
            success=True,
            http_status=200,
            quota_limit=100,
            quota_remaining=20,
        )

        state2 = rapidapi_budget_state(
            connection2,
            now=now,
        )

        require(
            state2["allowed"] is False,
            "quota margin did not "
            "block",
        )

        require(
            state2["reason"]
            == "quota_margin_reached",
            "quota margin block "
            "reason changed",
        )

        row = connection2.execute(
            """
            SELECT
                provider,
                endpoint,
                success,
                http_status,
                quota_limit,
                quota_remaining
            FROM api_usage
            ORDER BY usage_id DESC
            LIMIT 1
            """
        ).fetchone()

        require(
            row["provider"]
            == RAPIDAPI_PROVIDER,
            "provider identity changed",
        )

        require(
            row["endpoint"]
            == FANZA_QUERY_ENDPOINT,
            "endpoint identity changed",
        )

        require(
            row["success"] == 1,
            "success telemetry changed",
        )

        require(
            row["http_status"] == 200,
            "HTTP telemetry changed",
        )

        require(
            row["quota_limit"] == 100,
            "quota limit telemetry "
            "changed",
        )

        require(
            row["quota_remaining"] == 20,
            "quota remaining telemetry "
            "changed",
        )

        # Budget bookkeeping must not
        # touch catalog rows.
        require(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM titles
                """
            ).fetchone()[0]
            == 0,
            "budget ledger changed "
            "titles",
        )

        require(
            connection2.execute(
                """
                SELECT COUNT(*)
                FROM titles
                """
            ).fetchone()[0]
            == 0,
            "quota ledger changed "
            "titles",
        )

        connection.close()
        connection2.close()

    print(
        "FANZA_RAPIDAPI_PROVIDER_IDENTITY_SMOKE=PASS"
    )

    print(
        "FANZA_ROLLING_30D_BUDGET_SMOKE=PASS"
    )

    print(
        "FANZA_SHARED_MOVIE_QUERY_BUDGET_SMOKE=PASS"
    )

    print(
        "FANZA_AUTO_BUDGET_FAIL_CLOSED_SMOKE=PASS"
    )

    print(
        "FANZA_QUOTA_MARGIN_FAIL_CLOSED_SMOKE=PASS"
    )

    print(
        "FANZA_API_USAGE_TELEMETRY_SMOKE=PASS"
    )

    print(
        "FANZA_BUDGET_NO_CATALOG_WRITE_SMOKE=PASS"
    )

    print(
        "FANZA_BUDGET_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
