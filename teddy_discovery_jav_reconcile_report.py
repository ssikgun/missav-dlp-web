from __future__ import annotations

from collections import Counter
from pathlib import Path
import os
import sqlite3

from teddy_discovery_completion_ssh import CompletionSSH
from teddy_discovery_jav_reconcile import (
    DEFAULT_OPERATION_LOCK_PATH,
    RemoteLibraryRootError,
    _read_holdings,
    reconcile_remote,
    remote_library_root,
)
from teddy_discovery_operation_lock import (
    OperationLockBusy,
    OperationLockError,
    operation_lock,
)


CANONICAL_LIBRARY_ROOT = "/volume1/video/video2/JAV"
DISCOVERY_DB_ENV = "TEDDY_DISCOVERY_DB"
LIBRARY_ROOT_ENV = "TEDDY_FINAL_LIBRARY_ROOT"
SSH_ENV = (
    "TEDDY_FINAL_SSH_HOST",
    "TEDDY_FINAL_SSH_USER",
    "TEDDY_FINAL_SSH_KEY",
    "TEDDY_FINAL_SSH_KNOWN_HOSTS",
)

FAILURE_CATEGORIES = frozenset(
    {
        "DB_UNAVAILABLE",
        "MOUNT_UNAVAILABLE",
        "OPERATION_LOCK_ERROR",
        "REMOTE_LIBRARY_ROOT_UNAVAILABLE",
        "ROOT_UNAVAILABLE",
        "PERMISSION_ERROR",
        "IO_ERROR",
    }
)


class ReportConfigurationError(RuntimeError):
    pass


def _required_environment(name, environ):
    value = str(environ.get(name) or "").strip()

    if not value:
        raise ReportConfigurationError(
            name + " is required"
        )

    return value


def _configuration(environ):
    db_path = Path(
        _required_environment(
            DISCOVERY_DB_ENV,
            environ,
        )
    )

    raw_library_root = _required_environment(
        LIBRARY_ROOT_ENV,
        environ,
    )

    try:
        library_root = remote_library_root(
            raw_library_root
        )

    except RemoteLibraryRootError as exc:
        raise ReportConfigurationError(
            str(exc)
        ) from exc

    if library_root != CANONICAL_LIBRARY_ROOT:
        raise ReportConfigurationError(
            LIBRARY_ROOT_ENV
            + " must be "
            + CANONICAL_LIBRARY_ROOT
        )

    ssh = {
        name: _required_environment(
            name,
            environ,
        )
        for name in SSH_ENV
    }

    return db_path, library_root, ssh


def _present_count(rows):
    return sum(
        int(row.get("present") or 0) == 1
        for row in rows
    )


def _safe_reason(value):
    return str(value).replace(
        " ",
        "_",
    ).replace(
        "\n",
        "_",
    )[:120]


def _finding_counts(report):
    return dict(
        sorted(
            Counter(
                finding.category
                for finding in report.findings
            ).items()
        )
    )


def _report_reason(report, counts):
    for category in sorted(counts):
        if category in FAILURE_CATEGORIES:
            return category

    if not report.root_available:
        return "ROOT_UNAVAILABLE"

    if not report.scan_complete:
        return "SCAN_INCOMPLETE"

    if report.db_available is not True:
        return "DB_UNAVAILABLE"

    if not report.apply_eligible:
        return "NOT_APPLY_ELIGIBLE"

    return "FINDINGS_PRESENT"


def _emit_report(report, db_present_count, output):
    counts = _finding_counts(report)

    if (
        report.db_available is True
        and report.root_available
        and report.scan_complete
        and not counts
        and report.apply_eligible
    ):
        result = "PASS"
        reason = None

    elif (
        report.db_available is not True
        or not report.root_available
        or not report.scan_complete
        or any(
            category in FAILURE_CATEGORIES
            for category in counts
        )
    ):
        result = "FAIL"
        reason = _report_reason(
            report,
            counts,
        )

    else:
        result = "HOLD"
        reason = _report_reason(
            report,
            counts,
        )

    output(
        "RESULT="
        + result
    )

    if reason:
        output(
            "REASON="
            + _safe_reason(reason)
        )

    output(
        "SCAN_COMPLETE="
        + str(int(bool(report.scan_complete)))
    )
    output(
        "ROOT_AVAILABLE="
        + str(int(bool(report.root_available)))
    )
    output(
        "DB_AVAILABLE="
        + str(int(report.db_available is True))
    )
    output(
        "FILESYSTEM_COUNT="
        + str(len(report.canonical_present_files))
    )
    output(
        "DB_PRESENT_COUNT="
        + str(db_present_count)
    )
    output(
        "FINDING_TOTAL="
        + str(len(report.findings))
    )

    for category, count in counts.items():
        output(
            "FINDING_"
            + category
            + "="
            + str(count)
        )

    output("APPLY=0")

    return result


def _emit_failure(reason, output):
    output(
        "RESULT=FAIL"
    )
    output(
        "REASON="
        + _safe_reason(reason)
    )
    output("APPLY=0")
    return "FAIL"


def run_report(
    *,
    environ=None,
    operation_lock_path=DEFAULT_OPERATION_LOCK_PATH,
    ssh_factory=CompletionSSH,
    reconcile_fn=reconcile_remote,
    holdings_reader=_read_holdings,
    lock_fn=operation_lock,
    output=print,
):
    if environ is None:
        environ = os.environ

    try:
        db_path, library_root, ssh_config = _configuration(
            environ
        )

    except ReportConfigurationError:
        return _emit_failure(
            "REMOTE_LIBRARY_ROOT_UNAVAILABLE",
            output,
        )

    try:
        with lock_fn(operation_lock_path):
            ssh = ssh_factory(
                host=ssh_config[
                    "TEDDY_FINAL_SSH_HOST"
                ],
                user=ssh_config[
                    "TEDDY_FINAL_SSH_USER"
                ],
                key=ssh_config[
                    "TEDDY_FINAL_SSH_KEY"
                ],
                known_hosts=ssh_config[
                    "TEDDY_FINAL_SSH_KNOWN_HOSTS"
                ],
                downloads_root="",
                library_root=library_root,
            )

            report = reconcile_fn(
                db_path,
                ssh,
                library_root=library_root,
            )

            db_present_count = 0

            if report.db_available is True:
                db_present_count = _present_count(
                    holdings_reader(db_path)
                )

    except OperationLockBusy:
        output("RESULT=SKIP")
        output("REASON=OPERATION_LOCK_BUSY")
        output("APPLY=0")
        return "SKIP"

    except OperationLockError:
        return _emit_failure(
            "OPERATION_LOCK_ERROR",
            output,
        )

    except (OSError, sqlite3.Error):
        return _emit_failure(
            "REMOTE_IO_ERROR",
            output,
        )

    except Exception:
        return _emit_failure(
            "RECONCILIATION_ERROR",
            output,
        )

    _emit_report(
        report,
        db_present_count,
        output,
    )

    return (
        "PASS"
        if (
            report.db_available is True
            and report.root_available
            and report.scan_complete
            and not report.findings
            and report.apply_eligible
        )
        else "HOLD"
        if report.db_available is True
        and report.root_available
        and report.scan_complete
        else "FAIL"
    )


def main():
    result = run_report()

    return 0 if result in {
        "PASS",
        "HOLD",
        "SKIP",
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())
