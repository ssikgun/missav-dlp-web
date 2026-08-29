from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
    timezone,
)
import sqlite3
from typing import Any


RAPIDAPI_PROVIDER = (
    "rapidapi-javinfo"
)

FANZA_QUERY_ENDPOINT = (
    "/query"
)

RAPIDAPI_WINDOW_DAYS = 30

# Keep normal automated usage below
# approximately 80 requests/month.
RAPIDAPI_AUTO_BUDGET = 79

# Preserve at least roughly 20% of the
# observed 100-request account quota.
RAPIDAPI_QUOTA_MARGIN = 20


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )


def _aware_datetime(
    value: str | datetime | None,
) -> datetime:
    if value is None:
        return datetime.now(
            timezone.utc
        )

    if isinstance(
        value,
        datetime,
    ):
        parsed = value
    elif isinstance(
        value,
        str,
    ):
        parsed = (
            datetime.fromisoformat(
                value
            )
        )
    else:
        raise TypeError(
            "timestamp must be "
            "str/datetime/None"
        )

    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
    ):
        raise ValueError(
            "timestamp must be "
            "timezone-aware"
        )

    return parsed.astimezone(
        timezone.utc
    )


def _optional_int(
    value: Any,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
):
    if value is None:
        return None

    if (
        isinstance(value, bool)
        or not isinstance(value, int)
    ):
        raise TypeError(
            "value must be int or None"
        )

    if (
        minimum is not None
        and value < minimum
    ):
        raise ValueError(
            "integer below minimum"
        )

    if (
        maximum is not None
        and value > maximum
    ):
        raise ValueError(
            "integer above maximum"
        )

    return value


def rolling_rapidapi_usage(
    connection: sqlite3.Connection,
    *,
    now: str | datetime | None = None,
    window_days: int = (
        RAPIDAPI_WINDOW_DAYS
    ),
) -> int:
    if (
        isinstance(
            window_days,
            bool,
        )
        or not isinstance(
            window_days,
            int,
        )
        or window_days < 1
        or window_days > 366
    ):
        raise ValueError(
            "window_days must be 1..366"
        )

    current = _aware_datetime(
        now
    )

    cutoff = (
        current
        - timedelta(
            days=window_days
        )
    ).isoformat(
        timespec="seconds"
    )

    row = connection.execute(
        """
        SELECT COUNT(*)
        FROM api_usage
        WHERE provider = ?
          AND requested_at >= ?
        """,
        (
            RAPIDAPI_PROVIDER,
            cutoff,
        ),
    ).fetchone()

    return int(
        row[0]
    )


def latest_rapidapi_quota(
    connection: sqlite3.Connection,
):
    row = connection.execute(
        """
        SELECT
            quota_limit,
            quota_remaining,
            requested_at
        FROM api_usage
        WHERE provider = ?
          AND quota_remaining IS NOT NULL
        ORDER BY
            requested_at DESC,
            usage_id DESC
        LIMIT 1
        """,
        (
            RAPIDAPI_PROVIDER,
        ),
    ).fetchone()

    if row is None:
        return {
            "quota_limit":
                None,

            "quota_remaining":
                None,

            "requested_at":
                None,
        }

    return {
        "quota_limit":
            row["quota_limit"],

        "quota_remaining":
            row["quota_remaining"],

        "requested_at":
            row["requested_at"],
    }


def rapidapi_budget_state(
    connection: sqlite3.Connection,
    *,
    now: str | datetime | None = None,
    auto_budget: int = (
        RAPIDAPI_AUTO_BUDGET
    ),
    quota_margin: int = (
        RAPIDAPI_QUOTA_MARGIN
    ),
) -> dict:
    if (
        isinstance(auto_budget, bool)
        or not isinstance(
            auto_budget,
            int,
        )
        or auto_budget < 1
        or auto_budget >= 100
    ):
        raise ValueError(
            "auto_budget must be 1..99"
        )

    if (
        isinstance(quota_margin, bool)
        or not isinstance(
            quota_margin,
            int,
        )
        or quota_margin < 0
        or quota_margin >= 100
    ):
        raise ValueError(
            "quota_margin must be 0..99"
        )

    used = rolling_rapidapi_usage(
        connection,
        now=now,
    )

    quota = latest_rapidapi_quota(
        connection
    )

    remaining = quota[
        "quota_remaining"
    ]

    rolling_ok = (
        used < auto_budget
    )

    quota_ok = (
        remaining is None
        or remaining > quota_margin
    )

    allowed = (
        rolling_ok
        and quota_ok
    )

    if not rolling_ok:
        reason = (
            "rolling_budget_exhausted"
        )
    elif not quota_ok:
        reason = (
            "quota_margin_reached"
        )
    else:
        reason = "ok"

    return {
        "provider":
            RAPIDAPI_PROVIDER,

        "window_days":
            RAPIDAPI_WINDOW_DAYS,

        "used":
            used,

        "auto_budget":
            auto_budget,

        "rolling_remaining":
            max(
                0,
                auto_budget - used,
            ),

        "quota_limit":
            quota[
                "quota_limit"
            ],

        "quota_remaining":
            remaining,

        "quota_margin":
            quota_margin,

        "allowed":
            allowed,

        "reason":
            reason,
    }


def require_rapidapi_budget(
    connection: sqlite3.Connection,
    *,
    now: str | datetime | None = None,
) -> dict:
    state = rapidapi_budget_state(
        connection,
        now=now,
    )

    if not state[
        "allowed"
    ]:
        raise RuntimeError(
            "RapidAPI automatic request "
            "blocked: "
            + state["reason"]
        )

    return state


def record_rapidapi_usage(
    connection: sqlite3.Connection,
    *,
    endpoint: str,
    requested_at: str,
    success: bool,
    http_status: int | None = None,
    quota_limit: int | None = None,
    quota_remaining: int | None = None,
) -> int:
    if not isinstance(
        endpoint,
        str,
    ):
        raise TypeError(
            "endpoint must be string"
        )

    endpoint = endpoint.strip()

    if (
        not endpoint
        or not endpoint.startswith("/")
    ):
        raise ValueError(
            "endpoint must be "
            "absolute API path"
        )

    parsed_at = _aware_datetime(
        requested_at
    ).isoformat(
        timespec="seconds"
    )

    if type(success) is not bool:
        raise TypeError(
            "success must be bool"
        )

    http_status = _optional_int(
        http_status,
        minimum=100,
        maximum=599,
    )

    quota_limit = _optional_int(
        quota_limit,
        minimum=0,
    )

    quota_remaining = _optional_int(
        quota_remaining,
        minimum=0,
    )

    if (
        quota_limit is not None
        and quota_remaining is not None
        and quota_remaining > quota_limit
    ):
        raise ValueError(
            "quota_remaining exceeds "
            "quota_limit"
        )

    cursor = connection.execute(
        """
        INSERT INTO api_usage(
            provider,
            endpoint,
            requested_at,
            success,
            http_status,
            quota_limit,
            quota_remaining
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            RAPIDAPI_PROVIDER,
            endpoint,
            parsed_at,
            1 if success else 0,
            http_status,
            quota_limit,
            quota_remaining,
        ),
    )

    return int(
        cursor.lastrowid
    )

FANZA_QUERY_URL = (
    "https://javinfo.p.rapidapi.com/query"
)

FANZA_RAPIDAPI_HOST = (
    "javinfo.p.rapidapi.com"
)

FANZA_QUERY_PAGE_SIZE = 50

# Normal automation is intentionally
# shallow. Occasional callers may request
# a few more pages, but a single run can
# never become an unbounded deep sweep.
FANZA_QUERY_DEFAULT_MAX_PAGES = 2
FANZA_QUERY_HARD_MAX_PAGES = 4

FANZA_QUERY_TIMEOUT_SECONDS = 45


def build_fanza_query_payload(
    page: int,
) -> dict:
    if (
        isinstance(page, bool)
        or not isinstance(page, int)
        or page < 1
    ):
        raise ValueError(
            "FANZA query page must "
            "be positive integer"
        )

    return {
        "providers": [
            "fanza"
        ],

        "filter": {
            "censored":
                "censored",
        },

        "sort":
            "release",

        "page":
            page,

        "num":
            FANZA_QUERY_PAGE_SIZE,
    }


def _rapidapi_headers(
    api_key: str,
) -> dict:
    if not isinstance(
        api_key,
        str,
    ):
        raise TypeError(
            "RapidAPI key must "
            "be string"
        )

    api_key = api_key.strip()

    if not api_key:
        raise ValueError(
            "RapidAPI key missing"
        )

    return {
        "Accept":
            "application/json",

        "Content-Type":
            "application/json",

        "X-RapidAPI-Host":
            FANZA_RAPIDAPI_HOST,

        "X-RapidAPI-Key":
            api_key,
    }


def _required_proxy_url(
    proxy_url: str,
) -> str:
    if not isinstance(
        proxy_url,
        str,
    ):
        raise TypeError(
            "proxy URL must be string"
        )

    value = proxy_url.strip()

    if not (
        value.startswith(
            "http://"
        )
        or value.startswith(
            "https://"
        )
    ):
        raise ValueError(
            "FANZA query requires "
            "fixed HTTP(S) proxy"
        )

    return value


def _header_int(
    headers,
    name: str,
):
    if headers is None:
        return None

    values = {
        str(key).lower():
            value
        for key, value
        in dict(headers).items()
    }

    raw = values.get(
        name.lower()
    )

    if raw is None:
        return None

    try:
        value = int(
            str(raw).strip()
        )
    except (TypeError, ValueError):
        return None

    if value < 0:
        return None

    return value


def rapidapi_quota_from_headers(
    headers,
) -> dict:
    quota_limit = _header_int(
        headers,
        (
            "X-RateLimit-"
            "Request-Limit-Limit"
        ),
    )

    quota_remaining = _header_int(
        headers,
        (
            "X-RateLimit-"
            "Request-Limit-Remaining"
        ),
    )

    if quota_limit is None:
        quota_limit = _header_int(
            headers,
            (
                "X-RateLimit-"
                "rapid-free-plans-"
                "hard-limit-Limit"
            ),
        )

    if quota_remaining is None:
        quota_remaining = _header_int(
            headers,
            (
                "X-RateLimit-"
                "rapid-free-plans-"
                "hard-limit-Remaining"
            ),
        )

    return {
        "quota_limit":
            quota_limit,

        "quota_remaining":
            quota_remaining,
    }


def post_fanza_query_page(
    session,
    *,
    api_key: str,
    proxy_url: str,
    page: int,
    timeout: int = (
        FANZA_QUERY_TIMEOUT_SECONDS
    ),
) -> dict:
    if session is None:
        raise ValueError(
            "FANZA query session "
            "is required"
        )

    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, int)
        or timeout < 1
        or timeout > 120
    ):
        raise ValueError(
            "FANZA query timeout "
            "must be 1..120"
        )

    proxy = _required_proxy_url(
        proxy_url
    )

    request_payload = (
        build_fanza_query_payload(
            page
        )
    )

    requested_at = utc_now()

    response = session.post(
        FANZA_QUERY_URL,
        headers=
            _rapidapi_headers(
                api_key
            ),
        json=request_payload,
        timeout=timeout,
        proxies={
            "http":
                proxy,

            "https":
                proxy,
        },
    )

    status = int(
        response.status_code
    )

    quota = (
        rapidapi_quota_from_headers(
            getattr(
                response,
                "headers",
                {},
            )
        )
    )

    body = None

    if status == 200:
        try:
            body = response.json()
        except Exception as exc:
            raise RuntimeError(
                "FANZA query returned "
                "invalid JSON"
            ) from exc

    return {
        "endpoint":
            FANZA_QUERY_ENDPOINT,

        "requested_at":
            requested_at,

        "status":
            status,

        "success":
            status == 200,

        "quota_limit":
            quota[
                "quota_limit"
            ],

        "quota_remaining":
            quota[
                "quota_remaining"
            ],

        "request":
            request_payload,

        "body":
            body,
    }


def collect_fanza_query_pages(
    session,
    *,
    api_key: str,
    proxy_url: str,
    max_pages: int = (
        FANZA_QUERY_DEFAULT_MAX_PAGES
    ),
    timeout: int = (
        FANZA_QUERY_TIMEOUT_SECONDS
    ),
) -> dict:
    if (
        isinstance(max_pages, bool)
        or not isinstance(
            max_pages,
            int,
        )
        or max_pages < 1
        or max_pages
            > FANZA_QUERY_HARD_MAX_PAGES
    ):
        raise ValueError(
            "FANZA max_pages must "
            f"be 1.."
            f"{FANZA_QUERY_HARD_MAX_PAGES}"
        )

    # Import here so the collector core
    # reuses the already-proven canonical
    # query/DVD-ID normalization path.
    from teddy_discovery_javinfo import (
        normalize_query_response,
    )

    items = []
    seen = {}

    usage = []

    data_pages = 0
    provider_boundary = False
    has_more_pages = False

    for page in range(
        1,
        max_pages + 1,
    ):
        fetched = post_fanza_query_page(
            session,
            api_key=api_key,
            proxy_url=proxy_url,
            page=page,
            timeout=timeout,
        )

        usage.append({
            "endpoint":
                fetched[
                    "endpoint"
                ],

            "requested_at":
                fetched[
                    "requested_at"
                ],

            "success":
                fetched[
                    "success"
                ],

            "http_status":
                fetched[
                    "status"
                ],

            "quota_limit":
                fetched[
                    "quota_limit"
                ],

            "quota_remaining":
                fetched[
                    "quota_remaining"
                ],
        })

        status = fetched[
            "status"
        ]

        if status == 404:
            if page == 1:
                raise RuntimeError(
                    "FANZA query page 1 "
                    "returned HTTP 404"
                )

            provider_boundary = True
            has_more_pages = False
            break

        if status != 200:
            raise RuntimeError(
                "FANZA query HTTP "
                + str(status)
            )

        payload = fetched[
            "body"
        ]

        if (
            not isinstance(
                payload,
                dict,
            )
            or payload.get(
                "source"
            )
            != "fanza"
        ):
            raise ValueError(
                "FANZA query response "
                "source mismatch"
            )

        normalized = (
            normalize_query_response(
                payload
            )
        )

        if len(normalized) > (
            FANZA_QUERY_PAGE_SIZE
        ):
            raise ValueError(
                "FANZA query page "
                "exceeded num=50"
            )

        data_pages += 1

        for item in normalized:
            dvd_id = item[
                "dvd_id"
            ]

            previous = seen.get(
                dvd_id
            )

            if previous is not None:
                if (
                    previous.get(
                        "release_date"
                    )
                    != item.get(
                        "release_date"
                    )
                ):
                    raise ValueError(
                        "conflicting FANZA "
                        "duplicate dvd_id: "
                        + dvd_id
                    )

                continue

            value = dict(
                item
            )

            seen[
                dvd_id
            ] = value

            items.append(
                value
            )

        if len(normalized) < (
            FANZA_QUERY_PAGE_SIZE
        ):
            has_more_pages = False
            break

        if page == max_pages:
            has_more_pages = True
            break

    return {
        "source":
            "fanza",

        "items":
            items,

        "item_count":
            len(items),

        "page_count":
            data_pages,

        "request_count":
            len(usage),

        "has_more_pages":
            has_more_pages,

        "provider_boundary":
            provider_boundary,

        "usage":
            usage,
    }

class BudgetedFanzaSession:
    """
    Wrap the proven HTTP transport.

    Every real RapidAPI request:
      1. checks the local budget first,
      2. records the consumed request
         immediately,
      3. commits usage independently
         from later catalog writes.

    Therefore a failed catalog write
    cannot erase already-consumed API
    usage.
    """

    def __init__(
        self,
        connection: sqlite3.Connection,
        transport,
    ):
        if not isinstance(
            connection,
            sqlite3.Connection,
        ):
            raise TypeError(
                "connection must be "
                "sqlite3 connection"
            )

        if transport is None:
            raise ValueError(
                "FANZA HTTP transport "
                "is required"
            )

        self.connection = connection
        self.transport = transport


    def post(
        self,
        url,
        **kwargs,
    ):
        if url != FANZA_QUERY_URL:
            raise ValueError(
                "budgeted FANZA session "
                "refuses unexpected URL"
            )

        # Re-check before every page,
        # not merely once per job.
        require_rapidapi_budget(
            self.connection
        )

        requested_at = utc_now()

        try:
            response = (
                self.transport.post(
                    url,
                    **kwargs,
                )
            )

        except Exception:
            record_rapidapi_usage(
                self.connection,
                endpoint=
                    FANZA_QUERY_ENDPOINT,
                requested_at=
                    requested_at,
                success=False,
                http_status=None,
                quota_limit=None,
                quota_remaining=None,
            )

            # API usage is factual history.
            # It must survive a later job
            # failure.
            self.connection.commit()

            raise

        status = int(
            response.status_code
        )

        quota = (
            rapidapi_quota_from_headers(
                getattr(
                    response,
                    "headers",
                    {},
                )
            )
        )

        record_rapidapi_usage(
            self.connection,
            endpoint=
                FANZA_QUERY_ENDPOINT,
            requested_at=
                requested_at,
            success=
                status == 200,
            http_status=
                status,
            quota_limit=
                quota[
                    "quota_limit"
                ],
            quota_remaining=
                quota[
                    "quota_remaining"
                ],
        )

        self.connection.commit()

        return response


def run_fanza_seed_job(
    connection: sqlite3.Connection,
    *,
    transport,
    api_key: str,
    proxy_url: str,
    max_pages: int = (
        FANZA_QUERY_DEFAULT_MAX_PAGES
    ),
    timeout: int = (
        FANZA_QUERY_TIMEOUT_SECONDS
    ),
) -> dict:
    if not isinstance(
        connection,
        sqlite3.Connection,
    ):
        raise TypeError(
            "connection must be "
            "sqlite3 connection"
        )

    budget_before = (
        rapidapi_budget_state(
            connection
        )
    )

    require_rapidapi_budget(
        connection
    )

    session = BudgetedFanzaSession(
        connection,
        transport,
    )

    collected = (
        collect_fanza_query_pages(
            session,
            api_key=api_key,
            proxy_url=proxy_url,
            max_pages=max_pages,
            timeout=timeout,
        )
    )

    items = collected[
        "items"
    ]

    if not items:
        raise ValueError(
            "refusing empty FANZA "
            "seed job result"
        )

    # Import locally so release discovery
    # remains separate from rich metadata
    # ownership.
    from teddy_discovery_javinfo import (
        upsert_future_release_seeds,
    )

    observed_at = utc_now()

    written = (
        upsert_future_release_seeds(
            connection,
            items,
            observed_at=
                observed_at,
        )
    )

    budget_after = (
        rapidapi_budget_state(
            connection
        )
    )

    return {
        "source":
            "fanza",

        "item_count":
            collected[
                "item_count"
            ],

        "written":
            written,

        "page_count":
            collected[
                "page_count"
            ],

        "request_count":
            collected[
                "request_count"
            ],

        "has_more_pages":
            collected[
                "has_more_pages"
            ],

        "provider_boundary":
            collected[
                "provider_boundary"
            ],

        "observed_at":
            observed_at,

        "budget_before":
            budget_before,

        "budget_after":
            budget_after,
    }
