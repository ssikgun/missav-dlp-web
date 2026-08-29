from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path

from teddy_discovery_db import (
    connect,
    initialize,
)

from teddy_discovery_fanza import (
    FANZA_QUERY_DEFAULT_MAX_PAGES,
    FANZA_QUERY_HARD_MAX_PAGES,
    FANZA_QUERY_TIMEOUT_SECONDS,
    run_fanza_seed_job,
)


WRITER_LOCK_PATH = Path(
    "/run/lock/"
    "teddy-discovery-r2-writer.lock"
)

RAPIDAPI_KEY_PATH = Path(
    "/run/secrets/rapidapi_key"
)

GLUETUN_PROXY_ENV = (
    "GLUETUN_PROXY_URL"
)


class FanzaWriterLockBusy(
    RuntimeError
):
    pass


def required_environment(
    name: str,
) -> str:
    value = os.environ.get(
        name,
        "",
    ).strip()

    if not value:
        raise RuntimeError(
            "required environment "
            "variable missing: "
            + name
        )

    return value


def required_secret_file(
    path=RAPIDAPI_KEY_PATH,
) -> str:
    secret_path = Path(
        path
    )

    if not secret_path.is_file():
        raise RuntimeError(
            "required secret file "
            "missing: "
            + str(secret_path)
        )

    value = secret_path.read_text(
        encoding="utf-8"
    ).strip()

    if not value:
        raise RuntimeError(
            "required secret file "
            "is empty: "
            + str(secret_path)
        )

    return value


@contextmanager
def writer_lock(
    lock_path=WRITER_LOCK_PATH,
):
    path = Path(
        lock_path
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    handle = path.open(
        "a+",
        encoding="utf-8",
    )

    os.chmod(
        path,
        0o600,
    )

    acquired = False

    try:
        try:
            fcntl.flock(
                handle.fileno(),
                (
                    fcntl.LOCK_EX
                    | fcntl.LOCK_NB
                ),
            )

        except BlockingIOError as exc:
            raise FanzaWriterLockBusy(
                "Discovery R2 writer "
                "lock is busy"
            ) from exc

        acquired = True

        yield path

    finally:
        if acquired:
            fcntl.flock(
                handle.fileno(),
                fcntl.LOCK_UN,
            )

        handle.close()


def run_locked_fanza_seed(
    db_path,
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
    lock_path=WRITER_LOCK_PATH,
) -> dict:
    with writer_lock(
        lock_path
    ):
        connection = connect(
            db_path
        )

        try:
            initialize(
                connection
            )

            result = run_fanza_seed_job(
                connection,
                transport=transport,
                api_key=api_key,
                proxy_url=proxy_url,
                max_pages=max_pages,
                timeout=timeout,
            )

            return result

        finally:
            connection.close()


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Run bounded FANZA "
            "future-release seed job"
        )
    )

    parser.add_argument(
        "--db",
        required=True,
    )

    parser.add_argument(
        "--max-pages",
        type=int,
        default=
            FANZA_QUERY_DEFAULT_MAX_PAGES,
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=
            FANZA_QUERY_TIMEOUT_SECONDS,
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    if (
        args.max_pages < 1
        or args.max_pages
            > FANZA_QUERY_HARD_MAX_PAGES
    ):
        print(
            json.dumps({
                "ok": False,
                "error":
                    "invalid max-pages",
            }),
        )
        return 2

    try:
        api_key = (
            required_secret_file(
                RAPIDAPI_KEY_PATH
            )
        )

        proxy_url = (
            required_environment(
                GLUETUN_PROXY_ENV
            )
        )

        from curl_cffi import (
            requests,
        )

        result = (
            run_locked_fanza_seed(
                args.db,
                transport=requests,
                api_key=api_key,
                proxy_url=proxy_url,
                max_pages=
                    args.max_pages,
                timeout=
                    args.timeout,
            )
        )

    except FanzaWriterLockBusy:
        print(
            json.dumps({
                "ok": False,
                "lock_busy": True,
            }),
        )
        return 75

    except Exception as exc:
        print(
            json.dumps({
                "ok": False,
                "error_type":
                    type(exc).__name__,
                "error":
                    str(exc)[:300],
            }),
            ensure_ascii=False,
            sort_keys=True,
        )
        return 1

    safe = {
        "ok":
            True,

        "source":
            result[
                "source"
            ],

        "item_count":
            result[
                "item_count"
            ],

        "written":
            result[
                "written"
            ],

        "page_count":
            result[
                "page_count"
            ],

        "request_count":
            result[
                "request_count"
            ],

        "has_more_pages":
            result[
                "has_more_pages"
            ],

        "provider_boundary":
            result[
                "provider_boundary"
            ],

        "observed_at":
            result[
                "observed_at"
            ],

        "budget_after":
            result[
                "budget_after"
            ],
    }

    print(
        json.dumps(
            safe,
            ensure_ascii=False,
            sort_keys=True,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
