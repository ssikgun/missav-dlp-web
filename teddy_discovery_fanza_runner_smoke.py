import fcntl
import os
from pathlib import Path
import tempfile

from teddy_discovery_db import (
    connect,
)

from teddy_discovery_fanza_runner import (
    FanzaWriterLockBusy,
    GLUETUN_PROXY_ENV,
    RAPIDAPI_KEY_PATH,
    WRITER_LOCK_PATH,
    required_environment,
    required_secret_file,
    run_locked_fanza_seed,
)


KEY = "offline-test-key"
PROXY = "http://gluetun:8888"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


class FakeResponse:
    status_code = 200

    headers = {
        "X-RateLimit-Request-Limit-Limit":
            "100",

        "X-RateLimit-Request-Limit-Remaining":
            "99",
    }

    def json(self):
        return {
            "source": "fanza",
            "count": 1,
            "q": {},
            "results": [{
                "dvdId": "RUN-001",
                "title": "RUNNER TEST",
                "releaseDate":
                    "2026-09-10",
                "extra": {},
            }],
        }


class FakeTransport:
    def __init__(self):
        self.calls = 0

    def post(
        self,
        url,
        **kwargs,
    ):
        self.calls += 1

        require(
            kwargs["proxies"]
            == {
                "http": PROXY,
                "https": PROXY,
            },
            "runner proxy changed",
        )

        require(
            kwargs["headers"][
                "X-RapidAPI-Key"
            ] == KEY,
            "runner secret changed",
        )

        return FakeResponse()


def success_smoke():
    with tempfile.TemporaryDirectory(
        prefix="teddy-fanza-runner-"
    ) as temp:

        temp = Path(temp)

        db = temp / "discovery.sqlite3"
        lock = temp / "writer.lock"

        transport = FakeTransport()

        result = run_locked_fanza_seed(
            db,
            transport=transport,
            api_key=KEY,
            proxy_url=PROXY,
            max_pages=1,
            lock_path=lock,
        )

        require(
            result["written"] == 1,
            "runner write changed",
        )

        require(
            transport.calls == 1,
            "runner request changed",
        )

        connection = connect(db)

        try:
            require(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM titles
                    """
                ).fetchone()[0] == 1,
                "seed missing",
            )

            require(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM api_usage
                    """
                ).fetchone()[0] == 1,
                "usage missing",
            )

        finally:
            connection.close()

    print(
        "FANZA_RUNNER_SUCCESS_SMOKE=PASS"
    )


def lock_smoke():
    with tempfile.TemporaryDirectory(
        prefix="teddy-fanza-lock-"
    ) as temp:

        temp = Path(temp)

        db = temp / "discovery.sqlite3"
        lock = temp / "writer.lock"

        handle = lock.open(
            "a+",
            encoding="utf-8",
        )

        fcntl.flock(
            handle.fileno(),
            (
                fcntl.LOCK_EX
                | fcntl.LOCK_NB
            ),
        )

        transport = FakeTransport()
        blocked = False

        try:
            try:
                run_locked_fanza_seed(
                    db,
                    transport=transport,
                    api_key=KEY,
                    proxy_url=PROXY,
                    max_pages=1,
                    lock_path=lock,
                )

            except FanzaWriterLockBusy:
                blocked = True

            require(
                blocked,
                "lock did not block",
            )

            require(
                transport.calls == 0,
                "lock performed request",
            )

        finally:
            fcntl.flock(
                handle.fileno(),
                fcntl.LOCK_UN,
            )

            handle.close()

    print(
        "FANZA_SHARED_WRITER_LOCK_SMOKE=PASS"
    )


def secret_file_smoke():
    with tempfile.TemporaryDirectory(
        prefix="teddy-fanza-secret-"
    ) as temp:

        temp = Path(temp)
        secret = temp / "rapidapi_key"

        missing = False

        try:
            required_secret_file(
                secret
            )

        except RuntimeError:
            missing = True

        require(
            missing,
            "missing secret did "
            "not fail",
        )

        secret.write_text(
            "\n",
            encoding="utf-8",
        )

        empty = False

        try:
            required_secret_file(
                secret
            )

        except RuntimeError:
            empty = True

        require(
            empty,
            "empty secret did "
            "not fail",
        )

        secret.write_text(
            KEY + "\n",
            encoding="utf-8",
        )

        require(
            required_secret_file(
                secret
            ) == KEY,
            "secret file read "
            "changed",
        )

    require(
        str(RAPIDAPI_KEY_PATH)
        == "/run/secrets/rapidapi_key",
        "canonical secret path "
        "changed",
    )

    print(
        "FANZA_RUNNER_SECRET_FILE_SMOKE=PASS"
    )


def proxy_environment_smoke():
    old_proxy = os.environ.pop(
        GLUETUN_PROXY_ENV,
        None,
    )

    try:
        missing = False

        try:
            required_environment(
                GLUETUN_PROXY_ENV
            )

        except RuntimeError:
            missing = True

        require(
            missing,
            "missing proxy did "
            "not fail",
        )

        os.environ[
            GLUETUN_PROXY_ENV
        ] = PROXY

        require(
            required_environment(
                GLUETUN_PROXY_ENV
            ) == PROXY,
            "proxy environment "
            "changed",
        )

    finally:
        os.environ.pop(
            GLUETUN_PROXY_ENV,
            None,
        )

        if old_proxy is not None:
            os.environ[
                GLUETUN_PROXY_ENV
            ] = old_proxy

    print(
        "FANZA_RUNNER_PROXY_ENV_SMOKE=PASS"
    )


def constants_smoke():
    require(
        str(WRITER_LOCK_PATH)
        == (
            "/run/lock/"
            "teddy-discovery-r2-writer.lock"
        ),
        "writer lock path changed",
    )

    require(
        GLUETUN_PROXY_ENV
        == "GLUETUN_PROXY_URL",
        "proxy env name changed",
    )

    print(
        "FANZA_RUNNER_FROZEN_BOUNDARY_SMOKE=PASS"
    )


def main():
    success_smoke()
    lock_smoke()
    secret_file_smoke()
    proxy_environment_smoke()
    constants_smoke()

    print(
        "FANZA_REAL_RUNNER_OFFLINE_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
