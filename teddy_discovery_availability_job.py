from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import (
    datetime,
    timezone,
)
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Any

import teddy_discovery_availability_runner as runner_module

from teddy_discovery_availability_runner import (
    collect_batch_artifact,
    replay_batch_artifact,
    validate_batch_artifact,
)


JOB_VERSION = (
    "stage4-availability-job-v1"
)

PENDING_SUFFIX = (
    ".pending.json"
)

APPLIED_SUFFIX = (
    ".applied.json"
)

LOCK_FILENAME = (
    ".availability-runner.lock"
)


def _utc_now_text() -> str:
    return (
        datetime.now(
            timezone.utc
        )
        .replace(
            microsecond=0
        )
        .isoformat()
    )


def _sha256_file(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open(
        "rb"
    ) as fh:
        while True:
            chunk = fh.read(
                1024 * 1024
            )

            if not chunk:
                break

            digest.update(
                chunk
            )

    return digest.hexdigest()


def _source_provenance() -> dict:
    job_path = Path(
        __file__
    ).resolve()

    runner_path = Path(
        runner_module.__file__
    ).resolve()

    return {
        "job_source_sha256":
            _sha256_file(
                job_path
            ),

        "runner_module_sha256":
            _sha256_file(
                runner_path
            ),
    }


def _fsync_directory(
    directory: Path,
) -> None:
    flags = (
        os.O_RDONLY
    )

    if hasattr(
        os,
        "O_DIRECTORY",
    ):
        flags |= os.O_DIRECTORY

    fd = os.open(
        directory,
        flags,
    )

    try:
        os.fsync(
            fd
        )

    finally:
        os.close(
            fd
        )


def _ensure_artifact_directory(
    value: Any,
) -> Path:
    directory = Path(
        value
    )

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not directory.is_dir():
        raise ValueError(
            "artifact directory invalid"
        )

    return directory.resolve()


@contextmanager
def runner_lock(
    artifact_directory: Any,
):
    directory = (
        _ensure_artifact_directory(
            artifact_directory
        )
    )

    lock_path = (
        directory
        / LOCK_FILENAME
    )

    handle = lock_path.open(
        "a+",
        encoding="utf-8",
    )

    os.chmod(
        lock_path,
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
            raise RuntimeError(
                "availability job "
                "already running"
            ) from exc

        acquired = True

        yield lock_path

    finally:
        if acquired:
            fcntl.flock(
                handle.fileno(),
                fcntl.LOCK_UN,
            )

        handle.close()


def _artifact_timestamp_token(
    artifact: dict,
) -> str:
    raw = artifact[
        "observed_at"
    ]

    parsed = datetime.fromisoformat(
        raw
    )

    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
    ):
        raise ValueError(
            "artifact observed_at "
            "must be timezone-aware"
        )

    return (
        parsed.astimezone(
            timezone.utc
        )
        .replace(
            microsecond=0
        )
        .strftime(
            "%Y%m%dT%H%M%SZ"
        )
    )


def _pending_name(
    artifact: dict,
) -> str:
    value = validate_batch_artifact(
        artifact
    )

    oracle = value[
        "oracle_sha256"
    ]

    if (
        not isinstance(
            oracle,
            str,
        )
        or len(
            oracle
        ) != 64
    ):
        raise ValueError(
            "artifact oracle invalid"
        )

    return (
        "availability-runner-"
        + _artifact_timestamp_token(
            value
        )
        + "-"
        + oracle[
            :16
        ]
        + PENDING_SUFFIX
    )


def find_pending_artifacts(
    artifact_directory: Any,
) -> list[Path]:
    directory = (
        _ensure_artifact_directory(
            artifact_directory
        )
    )

    return sorted(
        path
        for path
        in directory.glob(
            "availability-runner-*"
            + PENDING_SUFFIX
        )
        if path.is_file()
    )


def write_pending_artifact(
    artifact_directory: Any,
    artifact: Any,
) -> Path:
    directory = (
        _ensure_artifact_directory(
            artifact_directory
        )
    )

    value = validate_batch_artifact(
        artifact
    )

    final_path = (
        directory
        / _pending_name(
            value
        )
    )

    applied_path = Path(
        str(
            final_path
        )[
            :-len(
                PENDING_SUFFIX
            )
        ]
        + APPLIED_SUFFIX
    )

    if (
        final_path.exists()
        or applied_path.exists()
    ):
        raise RuntimeError(
            "availability artifact "
            "identity already exists"
        )

    fd, temp_name = tempfile.mkstemp(
        prefix=
            ".availability-artifact-",
        suffix=".tmp",
        dir=directory,
    )

    temp_path = Path(
        temp_name
    )

    try:
        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as fh:
            json.dump(
                artifact,
                fh,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )

            fh.write(
                "\n"
            )

            fh.flush()

            os.fsync(
                fh.fileno()
            )

        os.chmod(
            temp_path,
            0o600,
        )

        os.replace(
            temp_path,
            final_path,
        )

        _fsync_directory(
            directory
        )

    except Exception:
        if temp_path.exists():
            temp_path.unlink()

        raise

    return final_path


def load_artifact(
    path: Any,
) -> dict:
    artifact_path = Path(
        path
    )

    with artifact_path.open(
        "r",
        encoding="utf-8",
    ) as fh:
        artifact = json.load(
            fh
        )

    return validate_batch_artifact(
        artifact
    )


def mark_artifact_applied(
    pending_path: Any,
) -> Path:
    pending = Path(
        pending_path
    )

    if not pending.name.endswith(
        PENDING_SUFFIX
    ):
        raise ValueError(
            "pending artifact "
            "suffix invalid"
        )

    applied = Path(
        str(
            pending
        )[
            :-len(
                PENDING_SUFFIX
            )
        ]
        + APPLIED_SUFFIX
    )

    if applied.exists():
        raise RuntimeError(
            "applied artifact "
            "already exists"
        )

    os.replace(
        pending,
        applied,
    )

    os.chmod(
        applied,
        0o600,
    )

    _fsync_directory(
        applied.parent
    )

    return applied


def _recover_pending_locked(
    db_path: Path,
    artifact_directory: Path,
) -> dict | None:
    pending = find_pending_artifacts(
        artifact_directory
    )

    if len(
        pending
    ) > 1:
        raise RuntimeError(
            "multiple pending "
            "availability artifacts"
        )

    if not pending:
        return None

    pending_path = pending[0]

    artifact = load_artifact(
        pending_path
    )

    replay = replay_batch_artifact(
        db_path,
        artifact,
    )

    applied_path = (
        mark_artifact_applied(
            pending_path
        )
    )

    return {
        "job_version":
            JOB_VERSION,

        "mode":
            "recovered-pending",

        "artifact":
            str(
                applied_path
            ),

        "completed_count":
            replay[
                "completed_count"
            ],

        "applied_count":
            replay[
                "applied_count"
            ],

        "already_applied_count":
            replay[
                "already_applied_count"
            ],

        "aborted_on_unknown":
            artifact[
                "aborted_on_unknown"
            ],

        "status_counts":
            artifact[
                "status_counts"
            ],

        "network_collection_performed":
            False,

        "network_requests":
            0,

        "integrity":
            replay[
                "integrity"
            ],
    }


def run_cycle(
    db_path: Any,
    artifact_directory: Any,
    *,
    now: Any = None,
    observed_at: Any = None,
    max_requests: int = 20,
    inter_request_delay_seconds: Any = 1.0,
    collector=None,
    sleeper=None,
) -> dict:
    database = Path(
        db_path
    )

    if not database.is_file():
        raise ValueError(
            "availability DB missing"
        )

    directory = (
        _ensure_artifact_directory(
            artifact_directory
        )
    )

    with runner_lock(
        directory
    ):
        recovered = (
            _recover_pending_locked(
                database,
                directory,
            )
        )

        if recovered is not None:
            return recovered

        plan_now = (
            _utc_now_text()
            if now is None
            else now
        )

        connection = sqlite3.connect(
            "file:"
            + str(
                database
            )
            + "?mode=ro",
            uri=True,
        )

        connection.row_factory = (
            sqlite3.Row
        )

        kwargs = {
            "now":
                plan_now,

            "observed_at":
                observed_at,

            "max_requests":
                max_requests,

            "inter_request_delay_seconds":
                inter_request_delay_seconds,

            "stop_on_unknown":
                True,
        }

        if collector is not None:
            kwargs[
                "collector"
            ] = collector

        if sleeper is not None:
            kwargs[
                "sleeper"
            ] = sleeper

        try:
            artifact = (
                collect_batch_artifact(
                    connection,
                    **kwargs,
                )
            )

        finally:
            connection.close()

        artifact.update(
            {
                "job_version":
                    JOB_VERSION,

                **_source_provenance(),
            }
        )

        validate_batch_artifact(
            artifact
        )

        pending_path = (
            write_pending_artifact(
                directory,
                artifact,
            )
        )

        #
        # If replay raises, pending remains.
        # The next run recovers it before
        # issuing any new network request.
        #
        replay = replay_batch_artifact(
            database,
            artifact,
        )

        applied_path = (
            mark_artifact_applied(
                pending_path
            )
        )

        return {
            "job_version":
                JOB_VERSION,

            "mode":
                "collected-and-replayed",

            "artifact":
                str(
                    applied_path
                ),

            "completed_count":
                replay[
                    "completed_count"
                ],

            "applied_count":
                replay[
                    "applied_count"
                ],

            "already_applied_count":
                replay[
                    "already_applied_count"
                ],

            "aborted_on_unknown":
                artifact[
                    "aborted_on_unknown"
                ],

            "status_counts":
                artifact[
                    "status_counts"
                ],

            "network_collection_performed":
                True,

            "network_requests":
                artifact[
                    "request_attempts"
                ],

            "integrity":
                replay[
                    "integrity"
                ],
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run one bounded Teddy "
            "availability background cycle."
        )
    )

    parser.add_argument(
        "--db",
        required=True,
    )

    parser.add_argument(
        "--artifact-dir",
        required=True,
    )

    parser.add_argument(
        "--max-requests",
        type=int,
        default=20,
    )

    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=1.0,
    )

    return parser


def main(
    argv=None,
) -> None:
    args = build_parser().parse_args(
        argv
    )

    result = run_cycle(
        args.db,
        args.artifact_dir,
        max_requests=
            args.max_requests,
        inter_request_delay_seconds=
            args.delay_seconds,
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
