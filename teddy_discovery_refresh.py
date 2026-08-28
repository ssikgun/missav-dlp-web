from __future__ import annotations

import argparse
import fcntl
import json
import sqlite3
import time
from datetime import (
    datetime,
    timezone,
)
from pathlib import Path
from typing import Any

from teddy_discovery_collector import (
    run_release_collection,
)
from teddy_discovery_db import (
    connect,
    initialize,
)
from teddy_discovery_javdatabase_collector import (
    run_weekly_collection,
    vpn_proxy_url,
)
from teddy_discovery_javdatabase_movie import (
    parse_javdatabase_movie_envelope,
)
from teddy_discovery_javdatabase_movie_writer import (
    apply_direct_movie_metadata,
)
from teddy_discovery_missav_movie import (
    normalize_dvd_id,
    parse_missav_movie_envelope,
)
from teddy_discovery_missav_movie_writer import (
    apply_missav_en_movie_metadata,
)


DEFAULT_TIMEOUT_SECONDS = 45
DEFAULT_IMPERSONATE = "chrome"
DEFAULT_METADATA_MAX = 20
DEFAULT_DELAY_SECONDS = 1.0

JAVDATABASE_MOVIE_SOURCE = (
    "javdatabase-movie"
)

MISSAV_EN_MOVIE_SOURCE = (
    "missav-en-movie"
)

RELEASE_METADATA_SOURCE = (
    "missav-release"
)


def utc_now() -> str:
    return (
        datetime.now(
            timezone.utc
        )
        .replace(
            microsecond=0
        )
        .isoformat()
    )


def javdatabase_movie_url(
    dvd_id: str,
) -> str:
    dvd_id = normalize_dvd_id(
        dvd_id
    )

    return (
        "https://www.javdatabase.com/"
        "movies/"
        + dvd_id.lower()
        + "/"
    )


def missav_en_movie_url(
    dvd_id: str,
) -> str:
    dvd_id = normalize_dvd_id(
        dvd_id
    )

    return (
        "https://missav.ws/en/"
        + dvd_id.lower()
    )


def _new_session():
    from curl_cffi import (
        requests as cffi_requests,
    )

    return cffi_requests.Session()


def _fetch_html_envelope(
    session,
    url: str,
    *,
    proxy_url: str,
    timeout: int,
    impersonate: str,
) -> dict:
    requested_at = utc_now()

    response = session.get(
        url,
        proxies={
            "http":
                proxy_url,

            "https":
                proxy_url,
        },
        impersonate=
            impersonate,
        allow_redirects=False,
        timeout=timeout,
        headers={
            "Accept":
                "text/html,"
                "application/xhtml+xml",

            "Accept-Language":
                "en-US,en;q=0.9",
        },
    )

    status = int(
        response.status_code
    )

    final_url = str(
        response.url
    )

    if status not in (
        200,
        404,
    ):
        raise RuntimeError(
            "metadata HTTP "
            + str(status)
        )

    headers = {
        str(key).lower():
            str(value)

        for key, value
        in (
            getattr(
                response,
                "headers",
                {},
            )
            or {}
        ).items()
    }

    body = str(
        getattr(
            response,
            "text",
            "",
        )
        or ""
    )

    if status == 200:
        content_type = (
            headers.get(
                "content-type",
                ""
            ).lower()
        )

        if (
            content_type
            and "text/html"
            not in content_type
            and "application/xhtml+xml"
            not in content_type
        ):
            raise RuntimeError(
                "metadata response "
                "is not HTML"
            )

        if not body.strip():
            raise RuntimeError(
                "metadata response "
                "body is empty"
            )

    return {
        "requested_at":
            requested_at,

        "requested_url":
            url,

        "status":
            status,

        "final_url":
            final_url,

        "redirect_count":
            len(
                getattr(
                    response,
                    "history",
                    [],
                )
                or []
            ),

        "response_headers":
            headers,

        "body":
            body,
    }


def collect_metadata_candidate(
    dvd_id: str,
    *,
    session=None,
    proxy_url: str | None = None,
    timeout: int = (
        DEFAULT_TIMEOUT_SECONDS
    ),
    impersonate: str = (
        DEFAULT_IMPERSONATE
    ),
    jav_parser=(
        parse_javdatabase_movie_envelope
    ),
    missav_parser=(
        parse_missav_movie_envelope
    ),
) -> dict:
    dvd_id = normalize_dvd_id(
        dvd_id
    )

    if (
        type(timeout) is not int
        or timeout < 1
        or timeout > 120
    ):
        raise ValueError(
            "timeout must be 1..120"
        )

    if proxy_url is None:
        proxy_url = (
            vpn_proxy_url()
        )

    own_session = (
        session is None
    )

    if own_session:
        session = _new_session()

    request_count = 0

    try:
        direct_url = (
            javdatabase_movie_url(
                dvd_id
            )
        )

        direct = (
            _fetch_html_envelope(
                session,
                direct_url,
                proxy_url=
                    proxy_url,
                timeout=
                    timeout,
                impersonate=
                    impersonate,
            )
        )

        request_count += 1

        if direct["status"] == 200:
            item = jav_parser(
                direct,
                expected_dvd_id=
                    dvd_id,
            )

            return {
                "dvd_id":
                    dvd_id,

                "status":
                    "FOUND",

                "route":
                    JAVDATABASE_MOVIE_SOURCE,

                "request_count":
                    request_count,

                "item":
                    item,
            }

        fallback_url = (
            missav_en_movie_url(
                dvd_id
            )
        )

        fallback = (
            _fetch_html_envelope(
                session,
                fallback_url,
                proxy_url=
                    proxy_url,
                timeout=
                    timeout,
                impersonate=
                    impersonate,
            )
        )

        request_count += 1

        if fallback["status"] == 404:
            return {
                "dvd_id":
                    dvd_id,

                "status":
                    "NOT_FOUND",

                "route":
                    None,

                "request_count":
                    request_count,

                "item":
                    None,
            }

        item = missav_parser(
            fallback,
            expected_dvd_id=
                dvd_id,
        )

        return {
            "dvd_id":
                dvd_id,

            "status":
                "FOUND",

            "route":
                MISSAV_EN_MOVIE_SOURCE,

            "request_count":
                request_count,

            "item":
                item,
        }

    finally:
        if (
            own_session
            and session is not None
            and hasattr(
                session,
                "close",
            )
        ):
            session.close()


def metadata_candidate_ids(
    db_path: str | Path,
    *,
    limit: int = (
        DEFAULT_METADATA_MAX
    ),
) -> list[str]:
    if (
        type(limit) is not int
        or limit < 1
        or limit > 50
    ):
        raise ValueError(
            "metadata limit must "
            "be 1..50"
        )

    database = Path(
        db_path
    ).expanduser().resolve()

    connection = sqlite3.connect(
        "file:"
        + str(database)
        + "?mode=ro",
        uri=True,
    )

    connection.execute(
        "PRAGMA query_only = ON"
    )

    try:
        rows = connection.execute(
            """
            SELECT
                t.dvd_id
            FROM titles AS t
            LEFT JOIN latest_items AS li
              ON li.dvd_id = t.dvd_id
             AND li.source = ?
            WHERE t.metadata_source = ?
            ORDER BY
                CASE
                    WHEN li.dvd_id IS NULL
                    THEN 1
                    ELSE 0
                END,
                li.last_seen_at DESC,
                li.last_position ASC,
                t.dvd_id ASC
            LIMIT ?
            """,
            (
                RELEASE_METADATA_SOURCE,
                RELEASE_METADATA_SOURCE,
                limit,
            ),
        ).fetchall()

        return [
            str(row[0])
            for row in rows
        ]

    finally:
        connection.close()


def apply_collected_metadata(
    db_path: str | Path,
    collected: dict,
    *,
    direct_writer=(
        apply_direct_movie_metadata
    ),
    missav_writer=(
        apply_missav_en_movie_metadata
    ),
) -> dict:
    if not isinstance(
        collected,
        dict,
    ):
        raise TypeError(
            "collected metadata "
            "must be object"
        )

    dvd_id = normalize_dvd_id(
        collected.get(
            "dvd_id"
        )
    )

    status = collected.get(
        "status"
    )

    route = collected.get(
        "route"
    )

    item = collected.get(
        "item"
    )

    if status == "NOT_FOUND":
        return {
            "dvd_id":
                dvd_id,

            "applied":
                False,

            "reason":
                "not_found",

            "metadata_source":
                None,
        }

    if status != "FOUND":
        raise ValueError(
            "unknown collected "
            "metadata status"
        )

    if route not in (
        JAVDATABASE_MOVIE_SOURCE,
        MISSAV_EN_MOVIE_SOURCE,
    ):
        raise ValueError(
            "unknown metadata route"
        )

    if not isinstance(
        item,
        dict,
    ):
        raise ValueError(
            "metadata item missing"
        )

    connection = connect(
        db_path
    )

    try:
        initialize(
            connection
        )

        row = connection.execute(
            """
            SELECT metadata_source
            FROM titles
            WHERE dvd_id = ?
            """,
            (
                dvd_id,
            ),
        ).fetchone()

        if row is None:
            raise RuntimeError(
                "metadata candidate "
                "title disappeared"
            )

        current_source = row[0]

        if (
            current_source
            != RELEASE_METADATA_SOURCE
        ):
            return {
                "dvd_id":
                    dvd_id,

                "applied":
                    False,

                "reason":
                    "source_already_upgraded",

                "metadata_source":
                    current_source,
            }

        if route == (
            JAVDATABASE_MOVIE_SOURCE
        ):
            direct_writer(
                connection,
                item,
            )

            expected_source = (
                JAVDATABASE_MOVIE_SOURCE
            )

        else:
            missav_writer(
                connection,
                item,
            )

            expected_source = (
                MISSAV_EN_MOVIE_SOURCE
            )

        connection.commit()

        final = connection.execute(
            """
            SELECT metadata_source
            FROM titles
            WHERE dvd_id = ?
            """,
            (
                dvd_id,
            ),
        ).fetchone()

        if final is None:
            raise RuntimeError(
                "metadata title missing "
                "after write"
            )

        final_source = final[0]

        if final_source != expected_source:
            raise RuntimeError(
                "metadata source "
                "did not upgrade"
            )

        return {
            "dvd_id":
                dvd_id,

            "applied":
                True,

            "reason":
                "updated",

            "metadata_source":
                final_source,
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def enrich_pending_metadata(
    db_path: str | Path,
    *,
    max_items: int = (
        DEFAULT_METADATA_MAX
    ),
    delay_seconds: float = (
        DEFAULT_DELAY_SECONDS
    ),
    timeout: int = (
        DEFAULT_TIMEOUT_SECONDS
    ),
    session=None,
    proxy_url: str | None = None,
    collector=(
        collect_metadata_candidate
    ),
    applier=(
        apply_collected_metadata
    ),
) -> dict:
    if (
        type(max_items) is not int
        or max_items < 1
        or max_items > 50
    ):
        raise ValueError(
            "metadata max_items "
            "must be 1..50"
        )

    if (
        isinstance(
            delay_seconds,
            bool,
        )
        or not isinstance(
            delay_seconds,
            (
                int,
                float,
            ),
        )
        or delay_seconds < 0
        or delay_seconds > 10
    ):
        raise ValueError(
            "metadata delay_seconds "
            "must be 0..10"
        )

    candidates = metadata_candidate_ids(
        db_path,
        limit=max_items,
    )

    results = []

    request_count = 0
    direct_count = 0
    fallback_count = 0
    not_found_count = 0
    failed_count = 0
    skipped_count = 0

    own_session = (
        session is None
    )

    if (
        candidates
        and own_session
    ):
        session = _new_session()

    if (
        candidates
        and proxy_url is None
    ):
        proxy_url = (
            vpn_proxy_url()
        )

    try:
        for index, dvd_id in enumerate(
            candidates
        ):
            try:
                collected = collector(
                    dvd_id,
                    session=session,
                    proxy_url=
                        proxy_url,
                    timeout=timeout,
                )

                request_count += int(
                    collected.get(
                        "request_count",
                        0,
                    )
                )

                route = collected.get(
                    "route"
                )

                if route == (
                    JAVDATABASE_MOVIE_SOURCE
                ):
                    direct_count += 1

                elif route == (
                    MISSAV_EN_MOVIE_SOURCE
                ):
                    fallback_count += 1

                elif (
                    collected.get(
                        "status"
                    )
                    == "NOT_FOUND"
                ):
                    not_found_count += 1

                applied = applier(
                    db_path,
                    collected,
                )

                if (
                    not applied.get(
                        "applied"
                    )
                    and applied.get(
                        "reason"
                    )
                    == "source_already_upgraded"
                ):
                    skipped_count += 1

                results.append({
                    "dvd_id":
                        dvd_id,

                    "ok":
                        True,

                    "route":
                        route,

                    "status":
                        collected.get(
                            "status"
                        ),

                    "applied":
                        bool(
                            applied.get(
                                "applied"
                            )
                        ),

                    "reason":
                        applied.get(
                            "reason"
                        ),
                })

            except Exception as exc:
                failed_count += 1

                results.append({
                    "dvd_id":
                        dvd_id,

                    "ok":
                        False,

                    "error_type":
                        type(
                            exc
                        ).__name__,

                    "error":
                        str(exc),
                })

            if (
                delay_seconds
                and index
                < len(candidates) - 1
            ):
                time.sleep(
                    float(
                        delay_seconds
                    )
                )

    finally:
        if (
            own_session
            and session is not None
            and hasattr(
                session,
                "close",
            )
        ):
            session.close()

    return {
        "candidate_count":
            len(candidates),

        "request_count":
            request_count,

        "direct_count":
            direct_count,

        "fallback_count":
            fallback_count,

        "not_found_count":
            not_found_count,

        "failed_count":
            failed_count,

        "skipped_count":
            skipped_count,

        "results":
            results,
    }


def _safe_release_result(
    result: dict,
) -> dict:
    keys = (
        "item_count",
        "written",
        "observed_at",
        "page_count",
        "request_count",
        "db_integrity",
    )

    return {
        key:
            result[key]

        for key in keys
        if key in result
    }


def _safe_weekly_result(
    result: dict,
) -> dict:
    keys = (
        "period",
        "written",
        "metadata_updated",
        "metadata_preserved",
        "observed_at",
        "request_count",
        "db_integrity",
    )

    return {
        key:
            result[key]

        for key in keys
        if key in result
    }


def run_refresh(
    db_path: str | Path,
    *,
    metadata_max: int = (
        DEFAULT_METADATA_MAX
    ),
    delay_seconds: float = (
        DEFAULT_DELAY_SECONDS
    ),
    timeout: int = (
        DEFAULT_TIMEOUT_SECONDS
    ),
    release_runner=(
        run_release_collection
    ),
    weekly_runner=(
        run_weekly_collection
    ),
    metadata_runner=(
        enrich_pending_metadata
    ),
) -> dict:
    result = {
        "started_at":
            utc_now(),

        "release":
            None,

        "weekly":
            None,

        "metadata":
            None,

        "core_errors":
            [],

        "metadata_error":
            None,
    }

    try:
        release = release_runner(
            db_path,
            timeout=timeout,
        )

        result["release"] = (
            _safe_release_result(
                release
            )
        )

    except Exception as exc:
        result[
            "core_errors"
        ].append({
            "step":
                "release",

            "error_type":
                type(
                    exc
                ).__name__,

            "error":
                str(exc),
        })

    try:
        weekly = weekly_runner(
            db_path,
            timeout=timeout,
        )

        result["weekly"] = (
            _safe_weekly_result(
                weekly
            )
        )

    except Exception as exc:
        result[
            "core_errors"
        ].append({
            "step":
                "weekly",

            "error_type":
                type(
                    exc
                ).__name__,

            "error":
                str(exc),
        })

    try:
        result["metadata"] = (
            metadata_runner(
                db_path,
                max_items=
                    metadata_max,
                delay_seconds=
                    delay_seconds,
                timeout=
                    timeout,
            )
        )

    except Exception as exc:
        result["metadata_error"] = {
            "error_type":
                type(
                    exc
                ).__name__,

            "error":
                str(exc),
        }

    result["core_ok"] = (
        len(
            result[
                "core_errors"
            ]
        )
        == 0
    )

    result["metadata_ok"] = (
        result[
            "metadata_error"
        ]
        is None
    )

    if isinstance(
        result.get(
            "metadata"
        ),
        dict,
    ):
        result["metadata_ok"] = (
            result["metadata_ok"]
            and result[
                "metadata"
            ].get(
                "failed_count",
                0,
            )
            == 0
        )

    result["degraded"] = (
        not result[
            "core_ok"
        ]
        or not result[
            "metadata_ok"
        ]
    )

    result["finished_at"] = (
        utc_now()
    )

    return result


def _lock_path_for_db(
    db_path: str | Path,
) -> Path:
    database = Path(
        db_path
    ).expanduser().resolve()

    return (
        database.parent
        / "teddy-discovery-refresh.lock"
    )


def run_locked_refresh(
    db_path: str | Path,
    **kwargs,
) -> dict:
    lock_path = (
        _lock_path_for_db(
            db_path
        )
    )

    lock_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with lock_path.open(
        "a+",
        encoding="utf-8",
    ) as lock_file:
        try:
            fcntl.flock(
                lock_file.fileno(),
                (
                    fcntl.LOCK_EX
                    | fcntl.LOCK_NB
                ),
            )

        except BlockingIOError:
            return {
                "started_at":
                    utc_now(),

                "finished_at":
                    utc_now(),

                "core_ok":
                    False,

                "metadata_ok":
                    False,

                "degraded":
                    True,

                "lock_busy":
                    True,

                "core_errors": [{
                    "step":
                        "lock",

                    "error_type":
                        "LockBusy",

                    "error":
                        "Discovery refresh "
                        "already running",
                }],
            }

        return run_refresh(
            db_path,
            **kwargs,
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh Teddy Discovery "
            "Latest, Weekly and "
            "missing rich metadata"
        )
    )

    parser.add_argument(
        "--db",
        required=True,
    )

    parser.add_argument(
        "--metadata-max",
        type=int,
        default=
            DEFAULT_METADATA_MAX,
    )

    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=
            DEFAULT_DELAY_SECONDS,
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=
            DEFAULT_TIMEOUT_SECONDS,
    )

    return parser


def exit_code_for_result(
    result: dict,
) -> int:
    if not isinstance(
        result,
        dict,
    ):
        raise TypeError(
            "refresh result must "
            "be object"
        )

    if result.get(
        "lock_busy"
    ):
        return 75

    if not result.get(
        "core_ok"
    ):
        return 1

    if not result.get(
        "metadata_ok"
    ):
        return 2

    return 0


def main() -> int:
    args = _parser().parse_args()

    result = run_locked_refresh(
        args.db,
        metadata_max=
            args.metadata_max,
        delay_seconds=
            args.delay_seconds,
        timeout=
            args.timeout,
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
