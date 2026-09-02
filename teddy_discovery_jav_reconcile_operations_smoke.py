from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import inspect
import tempfile

import teddy_discovery_jav_reconcile as reconcile_mod
import teddy_discovery_jav_reconcile_report as report_mod
from teddy_discovery_operation_lock import OperationLockBusy


ROOT = "/volume1/video/video2/JAV"
STAGING = "/volume1/video/video2/downloads"
DB = "/discovery/teddy-discovery.sqlite3"


def require(value, message):
    if not value:
        raise RuntimeError(message)


def environment(root=ROOT):
    return {
        "TEDDY_DISCOVERY_DB": DB,
        "TEDDY_FINAL_LIBRARY_ROOT": root,
        "TEDDY_FINAL_REMOTE_ROOT": STAGING,
        "TEDDY_FINAL_SSH_HOST": "nas",
        "TEDDY_FINAL_SSH_USER": "tester",
        "TEDDY_FINAL_SSH_KEY": "/key",
        "TEDDY_FINAL_SSH_KNOWN_HOSTS": "/known_hosts",
    }


def fake_report(
    *,
    filesystem_count=143,
    db_available=True,
    root_available=True,
    scan_complete=True,
    apply_eligible=True,
    categories=(),
):
    findings = tuple(
        SimpleNamespace(
            category=category,
            blocking=category not in {
                "FILESYSTEM_PRESENT_DB_MISSING",
                "DB_PRESENT_FILESYSTEM_MISSING",
                "ABSENT_HOLDING_REAPPEARED",
            },
        )
        for category in categories
    )

    return SimpleNamespace(
        db_available=db_available,
        root_available=root_available,
        scan_complete=scan_complete,
        apply_eligible=apply_eligible,
        canonical_present_files=tuple(
            {"relative_path": str(index)}
            for index in range(filesystem_count)
        ),
        findings=findings,
    )


class FakeSSH:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.__class__.instances.append(self)


class FakeLock:
    def __init__(self, events):
        self.events = events

    def __call__(self, path):
        @contextmanager
        def enter():
            self.events.append(("lock-enter", str(path)))
            yield
            self.events.append(("lock-exit", str(path)))

        return enter()


def run_case(report, *, db_count=143, environ=None):
    output = []
    events = []

    result = report_mod.run_report(
        environ=environ or environment(),
        operation_lock_path=Path("/tmp/report-operation.lock"),
        ssh_factory=FakeSSH,
        reconcile_fn=lambda db, ssh, library_root: report,
        holdings_reader=lambda db: [
            {"present": 1}
            for _ in range(db_count)
        ],
        lock_fn=FakeLock(events),
        output=output.append,
    )

    return result, output, events


def require_output(output, key, value):
    require(
        key + "=" + str(value) in output,
        "missing output " + key,
    )


def test_clean_and_drift_reports():
    result, output, events = run_case(
        fake_report(),
    )
    require(result == "PASS", "clean report was not PASS")
    require_output(output, "RESULT", "PASS")
    require_output(output, "SCAN_COMPLETE", 1)
    require_output(output, "FILESYSTEM_COUNT", 143)
    require_output(output, "DB_PRESENT_COUNT", 143)
    require_output(output, "FINDING_TOTAL", 0)
    require_output(output, "APPLY", 0)
    require(
        events == [
            ("lock-enter", "/tmp/report-operation.lock"),
            ("lock-exit", "/tmp/report-operation.lock"),
        ],
        "report did not use the operation lock",
    )

    for category in (
        "FILESYSTEM_PRESENT_DB_MISSING",
        "DB_PRESENT_FILESYSTEM_MISSING",
        "SIZE_MISMATCH",
        "MTIME_MISMATCH",
        "UNMATCHED_DVD_ID",
        "AMBIGUOUS_DVD_ID",
        "DUPLICATE_PHYSICAL_MEDIA",
        "UNEXPECTED_LAYOUT",
        "SYMLINK",
    ):
        result, output, _ = run_case(
            fake_report(
                filesystem_count=2,
                categories=(category,),
            ),
            db_count=1,
        )
        require(
            result == "HOLD",
            category + " did not HOLD",
        )
        require_output(output, "RESULT", "HOLD")
        require_output(output, "FINDING_" + category, 1)
        require_output(output, "APPLY", 0)


def test_fail_closed_and_lock_skip():
    for report in (
        fake_report(
            db_available=False,
            apply_eligible=False,
            categories=("DB_UNAVAILABLE",),
        ),
        fake_report(
            root_available=False,
            scan_complete=False,
            apply_eligible=False,
            categories=("ROOT_UNAVAILABLE",),
        ),
    ):
        result, output, _ = run_case(report)
        require(result == "FAIL", "unavailable state did not FAIL")
        require_output(output, "APPLY", 0)

    calls = []

    @contextmanager
    def busy_lock(path):
        raise OperationLockBusy("smoke busy")
        yield

    def must_not_scan(*args, **kwargs):
        calls.append("scan")
        raise RuntimeError("scan ran while lock was busy")

    output = []
    result = report_mod.run_report(
        environ=environment(),
        operation_lock_path=Path("/tmp/report-operation.lock"),
        ssh_factory=FakeSSH,
        reconcile_fn=must_not_scan,
        holdings_reader=must_not_scan,
        lock_fn=busy_lock,
        output=output.append,
    )
    require(result == "SKIP", "busy report was not SKIP")
    require_output(output, "RESULT", "SKIP")
    require_output(output, "REASON", "OPERATION_LOCK_BUSY")
    require_output(output, "APPLY", 0)
    require(not calls, "busy report performed I/O")


def test_ssh_io_and_config_fail_closed():
    def raise_io(*args, **kwargs):
        raise OSError("fake SSH I/O")

    result, output, _ = run_case(
        fake_report(),
    )
    require(result == "PASS", "control case failed")

    output = []
    result = report_mod.run_report(
        environ=environment(),
        ssh_factory=FakeSSH,
        reconcile_fn=raise_io,
        holdings_reader=lambda db: [],
        lock_fn=FakeLock([]),
        output=output.append,
    )
    require(result == "FAIL", "SSH I/O did not fail closed")
    require_output(output, "REASON", "REMOTE_IO_ERROR")
    require_output(output, "APPLY", 0)

    for env in (
        {
            **environment(),
            "TEDDY_FINAL_LIBRARY_ROOT": STAGING,
        },
        {
            key: value
            for key, value in environment().items()
            if key != "TEDDY_FINAL_LIBRARY_ROOT"
        },
    ):
        output = []
        result = report_mod.run_report(
            environ=env,
            output=output.append,
        )
        require(result == "FAIL", "invalid library config applied")
        require_output(
            output,
            "REASON",
            "REMOTE_LIBRARY_ROOT_UNAVAILABLE",
        )
        require_output(output, "APPLY", 0)


def test_report_only_and_bounds_are_static():
    source = inspect.getsource(report_mod)
    for forbidden in (
        "apply_reconciliation",
        "remote-apply",
        "--apply",
        "import_inventory",
    ):
        require(
            forbidden not in source,
            "report wrapper contains " + forbidden,
        )

    reconcile_source = inspect.getsource(
        reconcile_mod
    )
    for forbidden in (
        ".rglob(",
        "os.walk(",
        "find ",
    ):
        require(
            forbidden not in reconcile_source,
            "recursive traversal token found",
        )

    service = Path(
        "deploy/systemd/"
        "teddy-discovery-jav-reconcile.service"
    ).read_text(encoding="utf-8")
    timer = Path(
        "deploy/systemd/"
        "teddy-discovery-jav-reconcile.timer"
    ).read_text(encoding="utf-8")
    launcher = Path(
        "deploy/systemd/"
        "teddy-discovery-jav-reconcile-report"
    ).read_text(encoding="utf-8")

    require("Type=oneshot" in service, "service is not oneshot")
    require("--apply" not in service, "service exposes apply")
    require(
        "ExecStart=/usr/local/sbin/"
        "teddy-discovery-jav-reconcile-report"
        in service,
        "service wrapper changed",
    )
    require(
        "TEDDY_FINAL_LIBRARY_ROOT=/volume1/video/video2/JAV"
        in service,
        "service library root changed",
    )
    require(
        "TEDDY_FINAL_REMOTE_ROOT" not in launcher,
        "launcher uses staging root",
    )
    require(
        "OnCalendar=*-*-* 00,06,12,18:35:00 Asia/Seoul"
        in timer,
        "timer cadence changed",
    )
    require("Persistent=false" in timer, "timer is persistent")
    require("Restart=" not in service, "service restart loop enabled")
    require("apply" not in launcher.lower(), "launcher is not report-only")


def test_no_db_write_control():
    with tempfile.TemporaryDirectory(
        prefix="teddy-jav-report-smoke-"
    ) as temp:
        db_path = Path(temp) / "discovery.sqlite3"
        db_path.write_bytes(b"read-only-db-fixture")
        before = db_path.read_bytes()

        output = []
        result = report_mod.run_report(
            environ={
                **environment(),
                "TEDDY_DISCOVERY_DB": str(db_path),
            },
            ssh_factory=FakeSSH,
            reconcile_fn=lambda *args, **kwargs: fake_report(),
            holdings_reader=lambda db: [
                {"present": 1}
                for _ in range(143)
            ],
            lock_fn=FakeLock([]),
            output=output.append,
        )

        require(result == "PASS", "control report failed")
        require(
            db_path.read_bytes() == before,
            "report-only wrapper wrote the DB",
        )
        require_output(output, "APPLY", 0)


if __name__ == "__main__":
    test_clean_and_drift_reports()
    test_fail_closed_and_lock_skip()
    test_ssh_io_and_config_fail_closed()
    test_report_only_and_bounds_are_static()
    test_no_db_write_control()
    print("STAGE10_B2_OPERATIONS_SMOKE=PASS")
