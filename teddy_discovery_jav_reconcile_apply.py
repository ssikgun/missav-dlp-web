"""Strict, separately deployable JAV holdings reconciliation apply service.

The report wrapper intentionally does not import this module.  This entrypoint
is the only Stage10 path that turns a bounded reconciliation into a database
apply, and it accepts only the explicitly repairable drift categories below.
"""

from __future__ import annotations

from pathlib import Path
import argparse
import math
import os
import sqlite3

from teddy_discovery_completion_ssh import CompletionSSH
from teddy_discovery_jav_reconcile import (
    DEFAULT_OPERATION_LOCK_PATH,
    DEFAULT_WRITER_LOCK_PATH,
    ReconciliationDecision,
    ReconciliationUnsafe,
    apply_remote_reconciliation,
)
from teddy_discovery_organizer_apply import ExclusiveLockBusy


CANONICAL_LIBRARY_ROOT = "/volume1/video/video2/JAV"
DISCOVERY_DB_ENV = "TEDDY_DISCOVERY_DB"
LIBRARY_ROOT_ENV = "TEDDY_FINAL_LIBRARY_ROOT"
WRITER_TIMEOUT_ENV = "TEDDY_JAV_RECONCILE_WRITER_LOCK_TIMEOUT"
DEFAULT_WRITER_LOCK_TIMEOUT = 2.0
SSH_ENV = (
    "TEDDY_FINAL_SSH_HOST",
    "TEDDY_FINAL_SSH_USER",
    "TEDDY_FINAL_SSH_KEY",
    "TEDDY_FINAL_SSH_KNOWN_HOSTS",
)


# This is deliberately an allowlist, rather than a list of categories that
# happen to be non-blocking in the report module.  Unknown future categories
# are therefore held by default.
REPAIRABLE_FINDINGS = frozenset(
    {
        "FILESYSTEM_PRESENT_DB_MISSING",
        "DB_PRESENT_FILESYSTEM_MISSING",
        "ABSENT_HOLDING_REAPPEARED",
        "SIZE_MISMATCH",
        "MTIME_MISMATCH",
    }
)

INFRASTRUCTURE_FINDINGS = frozenset(
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

BLOCKING_UNSAFE_FINDINGS = frozenset(
    {
        "UNMATCHED_DVD_ID",
        "AMBIGUOUS_DVD_ID",
        "DUPLICATE_PHYSICAL_MEDIA",
        "UNEXPECTED_LAYOUT",
        "SYMLINK",
        "DVD_ID_MISMATCH",
        "DB_STATUS_MISMATCH",
        "DB_DUPLICATE_PRESENT",
        "EMPTY_ROOT_WITH_PRESENT_HOLDINGS",
        "EMPTY_SCAN_WITH_PRESENT_HOLDINGS",
        "STABILITY_CHANGED",
        "DB_STATE_CHANGED_AFTER_PREFLIGHT",
        "AUTO_APPLY_POLICY_HOLD",
    }
)


class ApplyConfigurationError(RuntimeError):
    pass


def _safe_reason(value):
    return str(value).replace(
        " ",
        "_",
    ).replace(
        "\n",
        "_",
    ).replace(
        "\r",
        "_",
    )[:160]


def _required_environment(name, environ):
    value = str(environ.get(name) or "").strip()

    if not value:
        raise ApplyConfigurationError(
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
    library_root = _required_environment(
        LIBRARY_ROOT_ENV,
        environ,
    )

    if library_root != CANONICAL_LIBRARY_ROOT:
        raise ApplyConfigurationError(
            LIBRARY_ROOT_ENV
            + " must be "
            + CANONICAL_LIBRARY_ROOT
        )

    ssh_config = {
        name: _required_environment(
            name,
            environ,
        )
        for name in SSH_ENV
    }

    return db_path, library_root, ssh_config


def writer_lock_timeout(environ):
    raw = str(
        environ.get(WRITER_TIMEOUT_ENV)
        or DEFAULT_WRITER_LOCK_TIMEOUT
    ).strip()

    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ApplyConfigurationError(
            WRITER_TIMEOUT_ENV + " must be numeric"
        ) from exc

    if not math.isfinite(value) or value < 0:
        raise ApplyConfigurationError(
            WRITER_TIMEOUT_ENV + " must be finite and non-negative"
        )

    return value


def evaluate_policy(report):
    """Return the strict Stage10 action for one stable reconciliation."""
    if report.root != CANONICAL_LIBRARY_ROOT:
        return ReconciliationDecision(
            "HOLD",
            "JAV_ROOT_MISMATCH",
        )

    if report.db_available is not True:
        return ReconciliationDecision(
            "HOLD",
            "DB_UNAVAILABLE",
        )

    if not report.root_available:
        return ReconciliationDecision(
            "HOLD",
            "ROOT_UNAVAILABLE",
        )

    if report.mount_available is False:
        return ReconciliationDecision(
            "HOLD",
            "MOUNT_UNAVAILABLE",
        )

    if not report.scan_complete:
        return ReconciliationDecision(
            "HOLD",
            "SCAN_INCOMPLETE",
        )

    if not report.canonical_present_files:
        return ReconciliationDecision(
            "HOLD",
            "CANONICAL_INVENTORY_EMPTY",
        )

    categories = sorted(
        {
            finding.category
            for finding in report.findings
        }
    )
    known_blocking = [
        category
        for category in categories
        if category in BLOCKING_UNSAFE_FINDINGS
    ]
    unknown = [
        category
        for category in categories
        if category not in REPAIRABLE_FINDINGS
        and category not in BLOCKING_UNSAFE_FINDINGS
        and category not in INFRASTRUCTURE_FINDINGS
    ]

    if unknown:
        return ReconciliationDecision(
            "HOLD",
            "BLOCKING_FINDING_" + unknown[0],
        )

    if known_blocking:
        return ReconciliationDecision(
            "HOLD",
            "BLOCKING_FINDING_" + known_blocking[0],
        )

    if categories and any(
        category in INFRASTRUCTURE_FINDINGS
        for category in categories
    ):
        return ReconciliationDecision(
            "HOLD",
            "INFRASTRUCTURE_FINDING_" + categories[0],
        )

    if any(
        finding.blocking
        for finding in report.findings
    ):
        return ReconciliationDecision(
            "HOLD",
            "BLOCKING_FINDING_PRESENT",
        )

    if not report.apply_eligible:
        return ReconciliationDecision(
            "HOLD",
            "RECONCILIATION_NOT_ELIGIBLE",
        )

    if not report.findings:
        return ReconciliationDecision(
            "NOOP",
        )

    return ReconciliationDecision(
        "APPLY",
    )


def _emit_pairs(pairs, output):
    for key, value in pairs:
        output(
            str(key)
            + "="
            + str(value)
        )


def _emit_failure(reason, output):
    _emit_pairs(
        (
            ("RESULT", "FAIL"),
            ("REASON", _safe_reason(reason)),
            ("APPLY", 0),
        ),
        output,
    )
    return "FAIL"


def _finding_categories(report):
    return {
        finding.category
        for finding in report.findings
    }


def _emit_unsafe(report, output):
    categories = _finding_categories(report)

    if "OPERATION_LOCK_BUSY" in categories:
        _emit_pairs(
            (
                ("RESULT", "SKIP"),
                ("REASON", "OPERATION_LOCK_BUSY"),
                ("APPLY", 0),
            ),
            output,
        )
        return "SKIP"

    infrastructure = sorted(
        categories & INFRASTRUCTURE_FINDINGS
    )

    if infrastructure:
        return _emit_failure(
            infrastructure[0],
            output,
        )

    if "STABILITY_CHANGED" in categories:
        reason = "STABILITY_CHANGED"
    else:
        reason = None

    policy_reasons = [
        finding.detail
        for finding in report.findings
        if finding.category == "AUTO_APPLY_POLICY_HOLD"
    ]
    if reason is None:
        reason = (
            policy_reasons[0]
            if policy_reasons
            else "BLOCKING_FINDING_" + sorted(categories)[0]
            if categories
            else "NOT_APPLY_ELIGIBLE"
        )
    _emit_pairs(
        (
            ("RESULT", "HOLD"),
            ("REASON", _safe_reason(reason)),
            ("APPLY", 0),
        ),
        output,
    )
    return "HOLD"


def _emit_result(result, output):
    applied = bool(result.get("applied"))
    counts = result.get("mutation_counts") or {}
    action = "APPLIED" if applied else "NOOP"

    _emit_pairs(
        (
            ("RESULT", "PASS"),
            ("ACTION", action),
            ("APPLY", int(applied)),
            ("INSERTED", int(counts.get("INSERTED") or 0)),
            ("ABSENT_MARKED", int(counts.get("ABSENT_MARKED") or 0)),
            ("REVIVED", int(counts.get("REVIVED") or 0)),
            (
                "METADATA_UPDATED",
                int(counts.get("METADATA_UPDATED") or 0),
            ),
        ),
        output,
    )
    return "PASS"


def run_apply(
    *,
    environ=None,
    operation_lock_path=DEFAULT_OPERATION_LOCK_PATH,
    writer_lock_path=DEFAULT_WRITER_LOCK_PATH,
    writer_timeout=None,
    ssh_factory=CompletionSSH,
    apply_fn=apply_remote_reconciliation,
    policy_fn=evaluate_policy,
    output=print,
):
    if environ is None:
        environ = os.environ

    try:
        db_path, library_root, ssh_config = _configuration(
            environ
        )
        if writer_timeout is None:
            writer_timeout = writer_lock_timeout(environ)

    except ApplyConfigurationError as exc:
        return _emit_failure(
            str(exc),
            output,
        )

    try:
        ssh = ssh_factory(
            host=ssh_config["TEDDY_FINAL_SSH_HOST"],
            user=ssh_config["TEDDY_FINAL_SSH_USER"],
            key=ssh_config["TEDDY_FINAL_SSH_KEY"],
            known_hosts=ssh_config[
                "TEDDY_FINAL_SSH_KNOWN_HOSTS"
            ],
            downloads_root="",
            library_root=library_root,
        )
        result = apply_fn(
            db_path,
            ssh,
            library_root=library_root,
            operation_lock_path=operation_lock_path,
            writer_lock_path=writer_lock_path,
            writer_lock_timeout=writer_timeout,
            policy_fn=policy_fn,
        )

    except ReconciliationUnsafe as exc:
        return _emit_unsafe(
            exc.report,
            output,
        )

    except (ExclusiveLockBusy, BlockingIOError):
        _emit_pairs(
            (
                ("RESULT", "SKIP"),
                ("REASON", "WRITER_LOCK_BUSY"),
                ("APPLY", 0),
            ),
            output,
        )
        return "SKIP"

    except (OSError, sqlite3.Error) as exc:
        return _emit_failure(
            "APPLY_IO_ERROR_" + str(exc),
            output,
        )

    except Exception as exc:
        return _emit_failure(
            "APPLY_ERROR_" + str(exc),
            output,
        )

    return _emit_result(
        result,
        output,
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Strict separate JAV holdings reconciliation apply"
        )
    )
    parser.add_argument(
        "--operation-lock",
        type=Path,
        default=DEFAULT_OPERATION_LOCK_PATH,
    )
    parser.add_argument(
        "--writer-lock",
        type=Path,
        default=DEFAULT_WRITER_LOCK_PATH,
    )
    parser.add_argument(
        "--writer-lock-timeout",
        type=float,
        default=None,
    )
    args = parser.parse_args()
    result = run_apply(
        operation_lock_path=args.operation_lock,
        writer_lock_path=args.writer_lock,
        writer_timeout=args.writer_lock_timeout,
    )
    return 0 if result in {
        "PASS",
        "HOLD",
        "SKIP",
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())
