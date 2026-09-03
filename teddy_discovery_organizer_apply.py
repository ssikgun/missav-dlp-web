from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import argparse
import errno
import fcntl
import json
import math
import os
import sqlite3
import time
import uuid

from teddy_discovery_ids import parse_dvd_id
from teddy_discovery_organizer import (
    OrganizerPlan,
    plan,
)


CONFIRMATION = (
    "APPLY_STAGE7_MEDIA_MUTATION"
)

COPY_CHUNK = (
    16 * 1024 * 1024
)


class ApplyError(RuntimeError):
    pass


class ExclusiveLockBusy(BlockingIOError):
    """An exclusive lock could not be acquired within its bound."""


@dataclass(frozen=True)
class ApplyResult:
    job_id: int
    dvd_id: str
    source_path: str
    destination_path: str
    status: str


def utc_now() -> str:
    from datetime import (
        datetime,
        timezone,
    )

    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )


def _inside(
    path: Path,
    root: Path,
) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _has_symlink_component(
    path: Path,
    root: Path,
) -> bool:
    current = path

    while True:
        if current.is_symlink():
            return True

        if current == root:
            return False

        if root not in current.parents:
            return True

        current = current.parent


@contextmanager
def exclusive_lock(
    path: Path,
    *,
    blocking: bool = True,
    timeout: float | None = None,
):
    if not blocking and timeout is not None:
        raise ValueError(
            "exclusive lock cannot combine nonblocking and timeout"
        )

    if timeout is not None:
        try:
            timeout = float(timeout)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "exclusive lock timeout must be numeric"
            ) from exc

        if not math.isfinite(timeout) or timeout < 0:
            raise ValueError(
                "exclusive lock timeout must be finite and non-negative"
            )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    handle = path.open(
        "a+",
        encoding="utf-8",
    )

    try:
        try:
            fcntl.flock(
                handle.fileno(),
                fcntl.LOCK_EX
                | (
                    fcntl.LOCK_NB
                    if not blocking or timeout is not None
                    else 0
                ),
            )

        except OSError as exc:
            if exc.errno not in {
                errno.EACCES,
                errno.EAGAIN,
            } or (blocking and timeout is None):
                raise

            deadline = time.monotonic() + float(timeout or 0)

            while True:
                if time.monotonic() >= deadline:
                    raise ExclusiveLockBusy(
                        "exclusive lock is busy: "
                        + str(path)
                    ) from exc

                time.sleep(
                    min(
                        0.05,
                        max(
                            0.0,
                            deadline - time.monotonic(),
                        ),
                    )
                )

                try:
                    fcntl.flock(
                        handle.fileno(),
                        fcntl.LOCK_EX | fcntl.LOCK_NB,
                    )
                    break

                except OSError as retry_exc:
                    if retry_exc.errno not in {
                        errno.EACCES,
                        errno.EAGAIN,
                    }:
                        raise

                    exc = retry_exc

        yield

    finally:
        fcntl.flock(
            handle.fileno(),
            fcntl.LOCK_UN,
        )

        handle.close()


def _connect_rw(
    db_path: Path,
) -> sqlite3.Connection:
    if not db_path.is_file():
        raise ApplyError(
            "database does not exist: "
            + str(db_path)
        )

    db = sqlite3.connect(
        db_path,
        timeout=30,
    )

    db.row_factory = sqlite3.Row

    db.execute(
        "PRAGMA foreign_keys = ON"
    )

    db.execute(
        "PRAGMA busy_timeout = 30000"
    )

    return db


@contextmanager
def writer_transaction(
    db_path: Path,
    writer_lock_path: Path,
):
    with exclusive_lock(
        writer_lock_path
    ):
        db = _connect_rw(
            db_path
        )

        try:
            db.execute(
                "BEGIN IMMEDIATE"
            )

            yield db

            db.commit()

        except Exception:
            db.rollback()
            raise

        finally:
            db.close()


def create_job(
    db_path: Path,
    writer_lock_path: Path,
    *,
    dvd_id: str,
    source_path: Path,
    destination_path: Path,
) -> int:
    now = utc_now()

    with writer_transaction(
        db_path,
        writer_lock_path,
    ) as db:
        cursor = db.execute(
            """
            INSERT INTO organizer_jobs (
                dvd_id,
                source_path,
                destination_path,
                status,
                error,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, NULL, ?, ?)
            """,
            (
                dvd_id,
                str(source_path),
                str(destination_path),
                "RUNNING",
                now,
                now,
            ),
        )

        return int(
            cursor.lastrowid
        )


def set_job_status(
    db_path: Path,
    writer_lock_path: Path,
    job_id: int,
    status: str,
    error: str | None = None,
) -> None:
    now = utc_now()

    if error is not None:
        error = error[:2000]

    with writer_transaction(
        db_path,
        writer_lock_path,
    ) as db:
        cursor = db.execute(
            """
            UPDATE organizer_jobs
            SET
                status = ?,
                error = ?,
                updated_at = ?
            WHERE job_id = ?
            """,
            (
                status,
                error,
                now,
                job_id,
            ),
        )

        if cursor.rowcount != 1:
            raise ApplyError(
                "organizer job disappeared"
            )


def fsync_directory(
    directory: Path,
) -> None:
    flags = os.O_RDONLY

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
        os.fsync(fd)

    finally:
        os.close(fd)


def _validate_relative(
    value: str,
    label: str,
) -> Path:
    path = Path(value)

    if path.is_absolute():
        raise ApplyError(
            label
            + " must be relative"
        )

    if ".." in path.parts:
        raise ApplyError(
            label
            + " contains '..'"
        )

    return path


def validate_source(
    item: OrganizerPlan,
    source_root: Path,
    stability_seconds: float,
) -> tuple[Path, os.stat_result]:

    relative = _validate_relative(
        item.source_relative,
        "source path",
    )

    source = (
        source_root
        / relative
    )

    if not source.is_file():
        raise ApplyError(
            "source is not a file: "
            + str(source)
        )

    if _has_symlink_component(
        source,
        source_root,
    ):
        raise ApplyError(
            "source contains symlink"
        )

    resolved = source.resolve(
        strict=True
    )

    if not _inside(
        resolved,
        source_root,
    ):
        raise ApplyError(
            "source escapes root"
        )

    parsed = parse_dvd_id(
        source.name
    )

    if (
        parsed is None
        or parsed.dvd_id
        != item.dvd_id
    ):
        raise ApplyError(
            "source DVD-ID changed"
        )

    first = source.stat()

    if int(first.st_size) != int(
        item.size_bytes
    ):
        raise ApplyError(
            "source size changed "
            "since planning"
        )

    if stability_seconds > 0:
        time.sleep(
            stability_seconds
        )

    second = source.stat()

    if (
        int(first.st_size)
        != int(second.st_size)
        or int(first.st_mtime_ns)
        != int(second.st_mtime_ns)
    ):
        raise ApplyError(
            "source changed during "
            "stability observation"
        )

    return source, second


def validate_destination(
    item: OrganizerPlan,
    library_root: Path,
) -> Path:

    if (
        item.destination_relative
        is None
    ):
        raise ApplyError(
            "destination is missing"
        )

    relative = _validate_relative(
        item.destination_relative,
        "destination path",
    )

    destination = (
        library_root
        / relative
    )

    resolved_parent = (
        destination.parent.resolve(
            strict=False
        )
    )

    if not _inside(
        resolved_parent,
        library_root,
    ):
        raise ApplyError(
            "destination parent "
            "escapes JAV root"
        )

    if destination.exists():
        raise ApplyError(
            "destination already exists"
        )

    return destination


def publish_copy(
    source: Path,
    destination: Path,
    *,
    expected_size: int,
    expected_mtime_ns: int,
) -> None:

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    resolved_parent = (
        destination.parent.resolve(
            strict=True
        )
    )

    library_candidate = (
        destination
        .parents[
            len(
                destination.parts
            )
            - len(
                destination.parts
            )
        ]
        if False
        else None
    )

    del library_candidate

    partial = (
        destination.parent
        / (
            "."
            + destination.name
            + ".teddy-organizer-"
            + uuid.uuid4().hex
            + ".partial"
        )
    )

    published = False

    try:
        source_before = source.stat()

        if (
            int(source_before.st_size)
            != int(expected_size)
            or int(source_before.st_mtime_ns)
            != int(expected_mtime_ns)
        ):
            raise ApplyError(
                "source changed before copy"
            )

        with source.open(
            "rb"
        ) as src, partial.open(
            "xb"
        ) as dst:

            while True:
                chunk = src.read(
                    COPY_CHUNK
                )

                if not chunk:
                    break

                dst.write(
                    chunk
                )

            dst.flush()

            os.fsync(
                dst.fileno()
            )

        partial_stat = (
            partial.stat()
        )

        if int(
            partial_stat.st_size
        ) != int(expected_size):
            raise ApplyError(
                "partial size mismatch"
            )

        source_after = source.stat()

        if (
            int(source_after.st_size)
            != int(expected_size)
            or int(source_after.st_mtime_ns)
            != int(expected_mtime_ns)
        ):
            raise ApplyError(
                "source changed "
                "during copy"
            )

        if destination.exists():
            raise ApplyError(
                "destination appeared "
                "during copy"
            )

        os.replace(
            partial,
            destination,
        )

        published = True

        with destination.open(
            "rb"
        ) as final_handle:
            os.fsync(
                final_handle.fileno()
            )

        fsync_directory(
            destination.parent
        )

        final_stat = (
            destination.stat()
        )

        if int(
            final_stat.st_size
        ) != int(expected_size):
            raise ApplyError(
                "published size mismatch"
            )

    except Exception:
        if (
            not published
            and partial.exists()
        ):
            try:
                partial.unlink()
            except OSError:
                pass

        raise


def update_holding_after_publish(
    db: sqlite3.Connection,
    *,
    mode: str,
    item: OrganizerPlan,
    final_path: Path,
) -> None:

    if item.dvd_id is None:
        raise ApplyError(
            "DVD-ID is missing"
        )

    final_stat = final_path.stat()

    now = utc_now()

    parse_candidates = (
        json.dumps(
            [item.dvd_id],
            ensure_ascii=False,
        )
    )

    if mode == "library":

        cursor = db.execute(
            """
            UPDATE holdings
            SET
                relative_path = ?,
                dvd_id = ?,
                parse_status = 'MATCHED',
                parse_method = ?,
                parse_candidates_json = ?,
                size_bytes = ?,
                mtime_ns = ?,
                present = 1,
                last_seen_at = ?,
                last_seen_run_id = NULL
            WHERE storage_root = 'jav'
              AND relative_path = ?
              AND present = 1
              AND dvd_id = ?
            """,
            (
                item.destination_relative,
                item.dvd_id,
                item.parse_method,
                parse_candidates,
                int(final_stat.st_size),
                int(final_stat.st_mtime_ns),
                now,
                item.source_relative,
                item.dvd_id,
            ),
        )

        if cursor.rowcount != 1:
            raise ApplyError(
                "existing holding "
                "did not match source"
            )

    elif mode == "downloads":

        duplicate = db.execute(
            """
            SELECT COUNT(*)
            FROM holdings
            WHERE dvd_id = ?
              AND present = 1
            """,
            (
                item.dvd_id,
            ),
        ).fetchone()[0]

        if int(duplicate) != 0:
            raise ApplyError(
                "holding appeared "
                "before DB publish"
            )

        db.execute(
            """
            INSERT INTO holdings (
                storage_root,
                relative_path,
                dvd_id,
                parse_status,
                parse_method,
                parse_candidates_json,
                size_bytes,
                mtime_ns,
                discovered_by,
                present,
                first_seen_at,
                last_seen_at,
                last_seen_run_id
            )
            VALUES (
                'jav',
                ?,
                ?,
                'MATCHED',
                ?,
                ?,
                ?,
                ?,
                'organizer-apply',
                1,
                ?,
                ?,
                NULL
            )
            """,
            (
                item.destination_relative,
                item.dvd_id,
                item.parse_method,
                parse_candidates,
                int(final_stat.st_size),
                int(final_stat.st_mtime_ns),
                now,
                now,
            ),
        )

    else:
        raise ApplyError(
            "unknown mode"
        )


def commit_publish_state(
    db_path: Path,
    writer_lock_path: Path,
    *,
    mode: str,
    item: OrganizerPlan,
    final_path: Path,
    job_id: int,
) -> None:

    with writer_transaction(
        db_path,
        writer_lock_path,
    ) as db:

        update_holding_after_publish(
            db,
            mode=mode,
            item=item,
            final_path=final_path,
        )

        cursor = db.execute(
            """
            UPDATE organizer_jobs
            SET
                status = 'PUBLISHED',
                error = NULL,
                updated_at = ?
            WHERE job_id = ?
            """,
            (
                utc_now(),
                job_id,
            ),
        )

        if cursor.rowcount != 1:
            raise ApplyError(
                "job missing during "
                "publish commit"
            )


def _cleanup_source(
    source: Path,
) -> None:
    source.unlink()

    fsync_directory(
        source.parent
    )


def apply_one(
    item: OrganizerPlan,
    *,
    mode: str,
    source_root: Path,
    library_root: Path,
    db_path: Path,
    apply_lock_path: Path,
    writer_lock_path: Path,
    stability_seconds: float = 3.0,
) -> ApplyResult:

    expected_operation = (
        "PLAN_STAGE7_RELAYOUT"
        if mode == "library"
        else "PLAN_STAGE7_MOVE"
    )

    if (
        item.planned_operation
        != expected_operation
    ):
        raise ApplyError(
            "plan is not apply-eligible: "
            + item.planned_operation
        )

    if item.dvd_id is None:
        raise ApplyError(
            "plan has no DVD-ID"
        )

    source_root = (
        source_root.resolve(
            strict=True
        )
    )

    library_root = (
        library_root.resolve(
            strict=True
        )
    )

    with exclusive_lock(
        apply_lock_path
    ):

        source, source_stat = (
            validate_source(
                item,
                source_root,
                stability_seconds,
            )
        )

        destination = (
            validate_destination(
                item,
                library_root,
            )
        )

        if source == destination:
            raise ApplyError(
                "source and destination "
                "are identical"
            )

        job_id = create_job(
            db_path,
            writer_lock_path,
            dvd_id=item.dvd_id,
            source_path=source,
            destination_path=
                destination,
        )

        try:
            publish_copy(
                source,
                destination,
                expected_size=int(
                    source_stat.st_size
                ),
                expected_mtime_ns=int(
                    source_stat.st_mtime_ns
                ),
            )

        except Exception as exc:
            try:
                set_job_status(
                    db_path,
                    writer_lock_path,
                    job_id,
                    "FAILED",
                    str(exc),
                )
            finally:
                pass

            raise

        try:
            commit_publish_state(
                db_path,
                writer_lock_path,
                mode=mode,
                item=item,
                final_path=
                    destination,
                job_id=job_id,
            )

        except Exception as exc:
            try:
                set_job_status(
                    db_path,
                    writer_lock_path,
                    job_id,
                    "DB_FAILED_AFTER_PUBLISH",
                    str(exc),
                )
            finally:
                pass

            raise

        try:
            _cleanup_source(
                source
            )

        except Exception as exc:
            set_job_status(
                db_path,
                writer_lock_path,
                job_id,
                "CLEANUP_PENDING",
                str(exc),
            )

            raise

        set_job_status(
            db_path,
            writer_lock_path,
            job_id,
            "COMPLETED",
            None,
        )

        return ApplyResult(
            job_id=job_id,
            dvd_id=item.dvd_id,
            source_path=str(source),
            destination_path=
                str(destination),
            status="COMPLETED",
        )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Teddy Stage 7 Organizer "
            "safe-publish apply"
        )
    )

    parser.add_argument(
        "--source-root",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--library-root",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--db",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--mode",
        required=True,
        choices=(
            "library",
            "downloads",
        ),
    )

    parser.add_argument(
        "--apply-lock",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--writer-lock",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--max-items",
        required=True,
        type=int,
    )

    parser.add_argument(
        "--stability-seconds",
        type=float,
        default=3.0,
    )

    parser.add_argument(
        "--apply",
        action="store_true",
    )

    parser.add_argument(
        "--confirm",
        default="",
    )

    args = parser.parse_args()

    if not args.apply:
        raise SystemExit(
            "refusing: --apply required"
        )

    if (
        args.confirm
        != CONFIRMATION
    ):
        raise SystemExit(
            "refusing: exact confirmation "
            "string required"
        )

    if args.max_items < 1:
        raise SystemExit(
            "refusing: --max-items "
            "must be >= 1"
        )

    source_root = (
        args.source_root.resolve(
            strict=True
        )
    )

    library_root = (
        args.library_root.resolve(
            strict=True
        )
    )

    plans, diagnostics = plan(
        source_root=source_root,
        library_root=library_root,
        db_path=args.db,
        mode=args.mode,
        stability_seconds=max(
            0.0,
            args.stability_seconds,
        ),
    )

    expected_operation = (
        "PLAN_STAGE7_RELAYOUT"
        if args.mode == "library"
        else "PLAN_STAGE7_MOVE"
    )

    eligible = [
        item
        for item in plans
        if item.planned_operation
        == expected_operation
    ]

    held = [
        item
        for item in plans
        if item.planned_operation
        == "HOLD"
    ]

    print(
        "PLAN_TOTAL="
        + str(len(plans))
    )

    print(
        "PLAN_ELIGIBLE="
        + str(len(eligible))
    )

    print(
        "PLAN_HOLD="
        + str(len(held))
    )

    if diagnostics[
        "holding_contradictions"
    ] != 0:
        raise SystemExit(
            "refusing: holding "
            "contradictions present"
        )

    selected = eligible[
        : args.max_items
    ]

    for item in selected:
        result = apply_one(
            item,
            mode=args.mode,
            source_root=source_root,
            library_root=library_root,
            db_path=args.db,
            apply_lock_path=
                args.apply_lock,
            writer_lock_path=
                args.writer_lock,
            stability_seconds=max(
                0.0,
                args.stability_seconds,
            ),
        )

        print(
            "APPLIED="
            + result.dvd_id
            + "|job_id="
            + str(result.job_id)
            + "|status="
            + result.status
        )

    print(
        "APPLY_COUNT="
        + str(len(selected))
    )


if __name__ == "__main__":
    main()
