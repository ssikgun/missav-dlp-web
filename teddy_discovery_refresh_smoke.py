from __future__ import annotations

import tempfile
from pathlib import Path

import teddy_discovery_refresh as refresh
from teddy_discovery_db import (
    connect,
    initialize,
)


def require(
    condition,
    message,
):
    if not condition:
        raise AssertionError(
            message
        )


class FakeResponse:
    def __init__(
        self,
        *,
        status,
        url,
        text="",
        content_type="text/html",
    ):
        self.status_code = status
        self.url = url
        self.text = text
        self.headers = {
            "Content-Type":
                content_type
        }
        self.history = []


class FakeSession:
    def __init__(
        self,
        responses,
    ):
        self.responses = list(
            responses
        )
        self.calls = []
        self.closed = False

    def get(
        self,
        url,
        **kwargs,
    ):
        self.calls.append(
            (
                url,
                kwargs,
            )
        )

        if not self.responses:
            raise AssertionError(
                "unexpected network call"
            )

        return self.responses.pop(
            0
        )

    def close(
        self,
    ):
        self.closed = True


def url_smoke():
    require(
        refresh.javdatabase_movie_url(
            "JUR-821"
        )
        == (
            "https://www.javdatabase.com/"
            "movies/jur-821/"
        ),
        "JAV Database URL changed",
    )

    require(
        refresh.missav_en_movie_url(
            "JUR-821"
        )
        == (
            "https://missav.ws/en/"
            "jur-821"
        ),
        "MissAV EN URL changed",
    )


def direct_route_smoke():
    dvd_id = "JUR-821"

    direct_url = (
        refresh.javdatabase_movie_url(
            dvd_id
        )
    )

    session = FakeSession([
        FakeResponse(
            status=200,
            url=direct_url,
            text="<html>direct</html>",
        ),
    ])

    parser_calls = []

    def jav_parser(
        envelope,
        *,
        expected_dvd_id,
    ):
        parser_calls.append(
            (
                "jav",
                expected_dvd_id,
                envelope[
                    "requested_url"
                ],
            )
        )

        return {
            "dvd_id":
                expected_dvd_id
        }

    def missav_parser(
        envelope,
        *,
        expected_dvd_id,
    ):
        raise AssertionError(
            "fallback parser "
            "must not run"
        )

    result = (
        refresh.collect_metadata_candidate(
            dvd_id,
            session=session,
            proxy_url=
                "http://gluetun:8888",
            jav_parser=
                jav_parser,
            missav_parser=
                missav_parser,
        )
    )

    require(
        result["route"]
        == "javdatabase-movie",
        "direct route changed",
    )

    require(
        result["request_count"]
        == 1,
        "direct request count changed",
    )

    require(
        len(session.calls) == 1,
        "direct GET count changed",
    )

    kwargs = session.calls[0][1]

    require(
        kwargs[
            "allow_redirects"
        ] is False,
        "redirect policy changed",
    )

    require(
        kwargs[
            "proxies"
        ][
            "https"
        ]
        == "http://gluetun:8888",
        "fixed VPN proxy changed",
    )

    require(
        parser_calls
        == [
            (
                "jav",
                dvd_id,
                direct_url,
            )
        ],
        "direct parser contract changed",
    )


def fallback_route_smoke():
    dvd_id = "JUR-821"

    direct_url = (
        refresh.javdatabase_movie_url(
            dvd_id
        )
    )

    fallback_url = (
        refresh.missav_en_movie_url(
            dvd_id
        )
    )

    session = FakeSession([
        FakeResponse(
            status=404,
            url=direct_url,
        ),
        FakeResponse(
            status=200,
            url=fallback_url,
            text="<html>fallback</html>",
        ),
    ])

    calls = []

    def jav_parser(
        envelope,
        *,
        expected_dvd_id,
    ):
        raise AssertionError(
            "404 direct parser "
            "must not run"
        )

    def missav_parser(
        envelope,
        *,
        expected_dvd_id,
    ):
        calls.append(
            (
                expected_dvd_id,
                envelope[
                    "requested_url"
                ],
            )
        )

        return {
            "dvd_id":
                expected_dvd_id
        }

    result = (
        refresh.collect_metadata_candidate(
            dvd_id,
            session=session,
            proxy_url=
                "http://gluetun:8888",
            jav_parser=
                jav_parser,
            missav_parser=
                missav_parser,
        )
    )

    require(
        result["route"]
        == "missav-en-movie",
        "fallback route changed",
    )

    require(
        result["request_count"]
        == 2,
        "fallback request count changed",
    )

    require(
        [
            call[0]
            for call
            in session.calls
        ]
        == [
            direct_url,
            fallback_url,
        ],
        "fallback URL order changed",
    )

    require(
        calls
        == [
            (
                dvd_id,
                fallback_url,
            )
        ],
        "fallback parser contract changed",
    )


def non404_fail_closed_smoke():
    dvd_id = "JUR-821"

    direct_url = (
        refresh.javdatabase_movie_url(
            dvd_id
        )
    )

    session = FakeSession([
        FakeResponse(
            status=500,
            url=direct_url,
            text="error",
        ),
    ])

    failed = False

    try:
        refresh.collect_metadata_candidate(
            dvd_id,
            session=session,
            proxy_url=
                "http://gluetun:8888",
            jav_parser=lambda *a, **k: {},
            missav_parser=lambda *a, **k: {},
        )

    except RuntimeError:
        failed = True

    require(
        failed,
        "non-404 direct failure "
        "must fail closed",
    )

    require(
        len(session.calls) == 1,
        "non-404 must not "
        "trigger fallback",
    )


def failed_request_telemetry_smoke():
    dvd_id = "JUR-821"

    direct_url = (
        refresh.javdatabase_movie_url(
            dvd_id
        )
    )

    direct_session = FakeSession([
        FakeResponse(
            status=200,
            url=direct_url,
            text="<html>direct</html>",
        ),
    ])

    try:
        refresh.collect_metadata_candidate(
            dvd_id,
            session=
                direct_session,
            proxy_url=
                "http://gluetun:8888",
            jav_parser=
                (
                    lambda *args, **kwargs:
                    (_ for _ in ()).throw(
                        ValueError(
                            "synthetic direct "
                            "parser failure"
                        )
                    )
                ),
            missav_parser=
                lambda *args, **kwargs: {},
        )

    except ValueError as exc:
        require(
            getattr(
                exc,
                "_teddy_request_count",
                None,
            ) == 1,
            "direct failed request "
            "count missing",
        )

    else:
        raise AssertionError(
            "direct parser failure "
            "did not propagate"
        )


    fallback_url = (
        refresh.missav_en_movie_url(
            dvd_id
        )
    )

    fallback_session = FakeSession([
        FakeResponse(
            status=404,
            url=direct_url,
        ),
        FakeResponse(
            status=200,
            url=fallback_url,
            text="<html>fallback</html>",
        ),
    ])

    try:
        refresh.collect_metadata_candidate(
            dvd_id,
            session=
                fallback_session,
            proxy_url=
                "http://gluetun:8888",
            jav_parser=
                lambda *args, **kwargs: {},
            missav_parser=
                (
                    lambda *args, **kwargs:
                    (_ for _ in ()).throw(
                        ValueError(
                            "synthetic fallback "
                            "parser failure"
                        )
                    )
                ),
        )

    except ValueError as exc:
        require(
            getattr(
                exc,
                "_teddy_request_count",
                None,
            ) == 2,
            "fallback failed request "
            "count missing",
        )

    else:
        raise AssertionError(
            "fallback parser failure "
            "did not propagate"
        )


    original_candidates = (
        refresh.metadata_candidate_ids
    )

    try:
        refresh.metadata_candidate_ids = (
            lambda *args, **kwargs:
                [dvd_id]
        )

        def failing_collector(
            *args,
            **kwargs,
        ):
            exc = ValueError(
                "synthetic collected failure"
            )

            setattr(
                exc,
                "_teddy_request_count",
                2,
            )

            raise exc

        result = (
            refresh.enrich_pending_metadata(
                "/tmp/not-used.sqlite3",
                max_items=1,
                delay_seconds=0,
                session=object(),
                proxy_url=
                    "http://gluetun:8888",
                collector=
                    failing_collector,
            )
        )

    finally:
        refresh.metadata_candidate_ids = (
            original_candidates
        )


    require(
        result[
            "candidate_count"
        ] == 1,
        "failed telemetry candidate "
        "count changed",
    )

    require(
        result[
            "failed_count"
        ] == 1,
        "failed telemetry failure "
        "count changed",
    )

    require(
        result[
            "request_count"
        ] == 2,
        "failed telemetry aggregate "
        "request count missing",
    )

    require(
        result[
            "results"
        ][0][
            "request_count"
        ] == 2,
        "failed telemetry per-item "
        "request count missing",
    )


def seed_title(
    connection,
    dvd_id,
    metadata_source,
):
    now = (
        "2026-08-28T00:00:00+00:00"
    )

    connection.execute(
        """
        INSERT INTO titles(
            dvd_id,
            title,
            release_date,
            maker,
            cover_url,
            raw_metadata,
            metadata_source,
            first_seen_at,
            last_seen_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            dvd_id,
            dvd_id + " title",
            None,
            None,
            (
                "https://fourhoi.com/"
                + dvd_id.lower()
                + "/cover-t.jpg"
            ),
            "{}",
            metadata_source,
            now,
            now,
        ),
    )


def candidate_and_apply_smoke():
    with tempfile.TemporaryDirectory(
        prefix="teddy-refresh-smoke-"
    ) as temp:
        db = (
            Path(temp)
            / "discovery.sqlite3"
        )

        connection = connect(
            db
        )

        initialize(
            connection
        )

        seed_title(
            connection,
            "JUR-821",
            "missav-release",
        )

        seed_title(
            connection,
            "JUR-822",
            "javdatabase-weekly",
        )

        connection.execute(
            """
            INSERT INTO latest_items(
                source,
                dvd_id,
                source_url,
                title,
                cover_url,
                first_seen_at,
                last_seen_at,
                first_position,
                last_position
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "missav-release",
                "JUR-821",
                "https://missav.ws/ko/jur-821",
                "JUR-821 title",
                (
                    "https://fourhoi.com/"
                    "jur-821/cover-t.jpg"
                ),
                "2026-08-28T00:00:00+00:00",
                "2026-08-28T00:00:00+00:00",
                1,
                1,
            ),
        )

        connection.commit()
        connection.close()

        candidates = (
            refresh.metadata_candidate_ids(
                db,
                limit=20,
            )
        )

        require(
            candidates == [
                "JUR-821"
            ],
            "metadata candidate "
            "selection changed",
        )

        collected = {
            "dvd_id":
                "JUR-821",

            "status":
                "FOUND",

            "route":
                "javdatabase-movie",

            "request_count":
                1,

            "item": {
                "dvd_id":
                    "JUR-821",
            },
        }

        def fake_direct_writer(
            connection,
            item,
        ):
            require(
                item["dvd_id"]
                == "JUR-821",
                "writer item changed",
            )

            connection.execute(
                """
                UPDATE titles
                SET metadata_source = ?
                WHERE dvd_id = ?
                """,
                (
                    "javdatabase-movie",
                    "JUR-821",
                ),
            )

        result = (
            refresh.apply_collected_metadata(
                db,
                collected,
                direct_writer=
                    fake_direct_writer,
            )
        )

        require(
            result["applied"] is True,
            "metadata apply failed",
        )

        require(
            result[
                "metadata_source"
            ]
            == "javdatabase-movie",
            "metadata source "
            "upgrade changed",
        )

        require(
            refresh.metadata_candidate_ids(
                db,
                limit=20,
            )
            == [],
            "upgraded title still "
            "selected",
        )


def fanza_metadata_handoff_smoke():
    with tempfile.TemporaryDirectory(
        prefix="teddy-fanza-metadata-"
    ) as temp:
        db = (
            Path(temp)
            / "discovery.sqlite3"
        )

        connection = connect(
            db
        )

        initialize(
            connection
        )

        observed = (
            "2026-08-29T00:00:00+00:00"
        )

        connection.executemany(
            """
            INSERT INTO titles(
                dvd_id,
                release_date,
                first_seen_at,
                last_seen_at
            )
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    "FAN-001",
                    "2026-08-29",
                    observed,
                    observed,
                ),
                (
                    "FAN-002",
                    "2026-08-30",
                    observed,
                    observed,
                ),
            ],
        )

        connection.commit()
        connection.close()

        candidates = (
            refresh.metadata_candidate_ids(
                db,
                limit=20,
                today="2026-08-29",
            )
        )

        require(
            "FAN-001" in candidates,
            "released FANZA seed "
            "not selected",
        )

        require(
            "FAN-002" not in candidates,
            "future FANZA seed "
            "selected too early",
        )

        collected = {
            "dvd_id":
                "FAN-001",

            "status":
                "FOUND",

            "route":
                "javdatabase-movie",

            "request_count":
                1,

            "item": {
                "dvd_id":
                    "FAN-001",
            },
        }

        def writer(
            connection,
            item,
        ):
            connection.execute(
                """
                UPDATE titles
                SET metadata_source = ?
                WHERE dvd_id = ?
                """,
                (
                    "javdatabase-movie",
                    item[
                        "dvd_id"
                    ],
                ),
            )

        result = (
            refresh.apply_collected_metadata(
                db,
                collected,
                direct_writer=writer,
            )
        )

        require(
            result[
                "applied"
            ] is True,
            "released FANZA seed "
            "metadata apply failed",
        )

        require(
            result[
                "metadata_source"
            ]
            == "javdatabase-movie",
            "released FANZA metadata "
            "source wrong",
        )

        remaining = (
            refresh.metadata_candidate_ids(
                db,
                limit=20,
                today="2026-08-29",
            )
        )

        require(
            "FAN-001" not in remaining,
            "upgraded FANZA seed "
            "still selected",
        )

        require(
            "FAN-002" not in remaining,
            "future FANZA seed "
            "entered metadata early",
        )

    print(
        "FANZA_RELEASE_DAY_METADATA_HANDOFF_SMOKE=PASS"
    )

    print(
        "FANZA_FUTURE_METADATA_DEFERRED_SMOKE=PASS"
    )

    print(
        "FANZA_METADATA_SOURCE_SEPARATION_SMOKE=PASS"
    )


def orchestration_smoke():
    calls = []

    def release_runner(
        db_path,
        **kwargs,
    ):
        calls.append(
            "release"
        )

        return {
            "item_count":
                50,

            "written":
                50,

            "observed_at":
                "2026-08-28T00:00:00+00:00",

            "page_count":
                5,

            "has_more_pages":
                False,

            "db_integrity":
                "ok",
        }

    def weekly_runner(
        db_path,
        **kwargs,
    ):
        calls.append(
            "weekly"
        )

        return {
            "period":
                "2026-W34",

            "written":
                25,

            "metadata_updated":
                1,

            "metadata_preserved":
                24,

            "observed_at":
                "2026-08-28T00:01:00+00:00",

            "request_count":
                2,

            "db_integrity":
                "ok",
        }

    def metadata_runner(
        db_path,
        **kwargs,
    ):
        calls.append(
            "metadata"
        )

        return {
            "candidate_count":
                1,

            "request_count":
                1,

            "direct_count":
                1,

            "fallback_count":
                0,

            "not_found_count":
                0,

            "failed_count":
                0,

            "skipped_count":
                0,

            "results":
                [],
        }

    result = refresh.run_refresh(
        "/tmp/not-used.sqlite3",
        metadata_max=20,
        delay_seconds=0,
        release_runner=
            release_runner,
        weekly_runner=
            weekly_runner,
        metadata_runner=
            metadata_runner,
    )

    require(
        calls == [
            "release",
            "weekly",
            "metadata",
        ],
        "refresh execution "
        "order changed",
    )

    require(
        result["core_ok"] is True,
        "successful core marked failed",
    )

    require(
        result[
            "release"
        ][
            "has_more_pages"
        ] is False,
        "release page-window state "
        "was not preserved",
    )

    require(
        result["metadata_ok"] is True,
        "successful metadata "
        "marked failed",
    )

    calls.clear()

    def failed_release(
        db_path,
        **kwargs,
    ):
        calls.append(
            "release"
        )

        raise RuntimeError(
            "synthetic release failure"
        )

    result = refresh.run_refresh(
        "/tmp/not-used.sqlite3",
        metadata_max=20,
        delay_seconds=0,
        release_runner=
            failed_release,
        weekly_runner=
            weekly_runner,
        metadata_runner=
            metadata_runner,
    )

    require(
        calls == [
            "release",
            "weekly",
            "metadata",
        ],
        "core failure incorrectly "
        "blocked later steps",
    )

    require(
        result["core_ok"] is False,
        "core failure not surfaced",
    )

    require(
        result["degraded"] is True,
        "core failure must mark "
        "refresh degraded",
    )

    require(
        refresh.exit_code_for_result(
            result
        )
        == 1,
        "core failure exit code changed",
    )

    calls.clear()

    def partial_metadata_failure(
        db_path,
        **kwargs,
    ):
        calls.append(
            "metadata"
        )

        return {
            "candidate_count":
                1,

            "request_count":
                1,

            "direct_count":
                0,

            "fallback_count":
                0,

            "not_found_count":
                0,

            "failed_count":
                1,

            "skipped_count":
                0,

            "results": [{
                "dvd_id":
                    "JUR-821",

                "ok":
                    False,
            }],
        }

    result = refresh.run_refresh(
        "/tmp/not-used.sqlite3",
        metadata_max=20,
        delay_seconds=0,
        release_runner=
            release_runner,
        weekly_runner=
            weekly_runner,
        metadata_runner=
            partial_metadata_failure,
    )

    require(
        result["core_ok"] is True,
        "successful core changed",
    )

    require(
        result["metadata_ok"] is False,
        "per-item metadata failure "
        "not surfaced",
    )

    require(
        result["degraded"] is True,
        "metadata failure must mark "
        "refresh degraded",
    )

    require(
        refresh.exit_code_for_result(
            result
        )
        == 2,
        "metadata failure exit code changed",
    )

    require(
        refresh.exit_code_for_result({
            "lock_busy":
                True,

            "core_ok":
                False,

            "metadata_ok":
                False,
        })
        == 75,
        "lock busy exit code changed",
    )

    require(
        refresh.exit_code_for_result({
            "core_ok":
                True,

            "metadata_ok":
                True,
        })
        == 0,
        "success exit code changed",
    )


def main():
    url_smoke()
    direct_route_smoke()
    fallback_route_smoke()
    non404_fail_closed_smoke()
    failed_request_telemetry_smoke()
    candidate_and_apply_smoke()

    fanza_metadata_handoff_smoke()
    orchestration_smoke()

    print(
        "DISCOVERY_REFRESH_URL_POLICY=PASS"
    )

    print(
        "DISCOVERY_REFRESH_FIXED_VPN_POLICY=PASS"
    )

    print(
        "DISCOVERY_REFRESH_404_FALLBACK_ONLY=PASS"
    )

    print(
        "DISCOVERY_REFRESH_METADATA_CANDIDATE=PASS"
    )

    print(
        "DISCOVERY_REFRESH_ORDER=PASS"
    )

    print(
        "DISCOVERY_REFRESH_FAILURE_ISOLATION=PASS"
    )

    print(
        "DISCOVERY_REFRESH_FAILED_REQUEST_TELEMETRY=PASS"
    )

    print(
        "DISCOVERY_REFRESH_DEGRADED_SEMANTICS=PASS"
    )

    print(
        "DISCOVERY_REFRESH_EXIT_CODE_SEMANTICS=PASS"
    )

    print(
        "DISCOVERY_REFRESH_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
