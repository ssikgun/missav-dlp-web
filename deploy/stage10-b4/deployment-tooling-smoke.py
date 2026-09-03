"""Offline smoke tests for the Stage10-B4 install/rollback tooling.

The tests source helper functions only and use temporary files plus a fake
systemctl function.  They never invoke the installer or touch a Production
path.
"""

from __future__ import annotations

from pathlib import Path
import os
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "deploy/stage10-b4/install-stage10-b4-apply-service.sh"
ROLLBACK = ROOT / "deploy/stage10-b4/rollback-stage10-b4-apply-service.sh"
MANIFEST = ROOT / "deploy/stage10-b4/separate-apply-deployment-manifest.md"
EXPECTED_HEAD = "66b13b6bbf9e930e73e7fdff9960581ab7b30a88"


def run_shell(script: Path, body: str, *args: str):
    environment = os.environ.copy()
    environment["STAGE10_B4_LIBRARY_ONLY"] = "1"
    return subprocess.run(
        ["bash", "-c", 'source "$1"; ' + body, "stage10-b4-smoke", str(script), *args],
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def require(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def syntax_smoke():
    for path in (INSTALLER, ROLLBACK):
        result = subprocess.run(
            ["bash", "-n", str(path)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        require(result.returncode == 0, f"bash syntax failed: {path}")
    print("B4_DEPLOYMENT_SHELL_SYNTAX=PASS")


def static_manifest_smoke():
    installer = INSTALLER.read_text()
    rollback = ROLLBACK.read_text()
    manifest = MANIFEST.read_text()

    for text in (installer, rollback):
        require(EXPECTED_HEAD in text, "exact HEAD missing")
        require("/opt/missav-dlp-web" in text and 'RUNTIME_DIR="$PRODUCTION_ROOT/stage9-runtime"' in text, "runtime default missing")
        require("/etc/default/teddy-discovery" in text, "environment file missing")

    require("systemctl enable" not in installer, "installer must not enable timers")
    require("systemctl disable" not in installer, "installer must not disable timers")
    require(
        'atomic_install "$SOURCE_ROOT/deploy/systemd/teddy-discovery-jav-reconcile-report"'
        not in installer,
        "installer must not install report wrapper",
    )
    require("teddy-discovery-jav-reconcile-apply.timer" in installer, "apply timer guard missing")
    require("ONE_APPLY_SERVICE_START" in installer, "single canary marker missing")
    require(
        "--after-cursor=\"$journal_cursor\"" in installer,
        "journal cursor filter missing",
    )
    require(
        "CANARY_JOURNAL_CURSOR_UNAVAILABLE" in installer,
        "journal cursor fail-closed guard missing",
    )
    require(
        "InvocationID" not in installer,
        "legacy InvocationID logic still present",
    )
    require(
        "_SYSTEMD_INVOCATION_ID" not in installer,
        "legacy invocation-id journal filter still present",
    )
    require("systemctl daemon-reload" in installer, "daemon reload missing")
    require("stop_timer_if_active \"$STAGE9_TIMER_NAME\"" in installer, "Stage9 quiesce missing")
    require("stop_timer_if_active \"$REPORT_TIMER_NAME\"" in installer, "report quiesce missing")
    require("TIMER_CLEANUP=FAIL" in installer, "installer finalizer failure output missing")
    require("TIMER_CLEANUP=FAIL" in rollback, "rollback finalizer failure output missing")

    expected_manifest_tokens = (
        "teddy_discovery_jav_reconcile.py",
        "teddy_discovery_organizer_apply.py",
        "teddy_discovery_jav_reconcile_apply.py",
        "teddy-discovery-jav-reconcile-apply",
        "teddy-discovery-jav-reconcile-apply.service",
        "No apply timer",
        "Remove the added apply runtime module",
    )
    for token in expected_manifest_tokens:
        require(token in manifest, f"manifest token missing: {token}")

    service = (ROOT / "deploy/systemd/teddy-discovery-jav-reconcile-apply.service").read_text()
    require("Type=oneshot" in service, "service type")
    require("EnvironmentFile=-/etc/default/teddy-discovery" in service, "service env")
    require("Environment=TEDDY_DISCOVERY_RUNTIME=/opt/missav-dlp-web/stage9-runtime" in service, "service runtime")
    require("Environment=TEDDY_DISCOVERY_DB=/opt/missav-dlp-web/discovery/teddy-discovery.sqlite3" in service, "service DB")
    require("Environment=TEDDY_FINAL_LIBRARY_ROOT=/volume1/video/video2/JAV" in service, "service root")
    require("Restart=" not in service, "service restart policy")
    print("B4_DEPLOYMENT_STATIC_MANIFEST=PASS")


def dirty_allowlist_smoke():
    allowed = "\n".join(
        (
            "?? deploy/stage10-b4/install-stage10-b4-apply-service.sh",
            "?? deploy/stage10-b4/rollback-stage10-b4-apply-service.sh",
        )
    )
    result = run_shell(INSTALLER, "printf '%s\\n' \"$2\" | allowed_source_worktree_status", allowed)
    require(result.returncode == 0 and result.stdout.strip() == "PASS", "exact dirty allowlist rejected")

    result = run_shell(
        INSTALLER,
        "printf '%s\\n' \"$2\" | allowed_source_worktree_status",
        allowed + "\n M unexpected.py",
    )
    require(result.returncode == 0 and result.stdout.strip() == "FAIL", "extra dirty state accepted")
    print("B4_DIRTY_TREE_ALLOWLIST=PASS")


def atomic_and_provenance_smoke():
    with tempfile.TemporaryDirectory(prefix="stage10-b4-tooling-") as temp:
        temp_path = Path(temp)
        source = temp_path / "source"
        target = temp_path / "target"
        marker = temp_path / "marker"
        source.write_text("atomic payload\n")

        result = run_shell(
            INSTALLER,
            'atomic_install "$2" "$3" 0644 && cmp -s "$2" "$3" && verify_metadata "$3" 0644',
            str(source),
            str(target),
        )
        require(result.returncode == 0, f"atomic install failed: {result.stderr}")

        result = run_shell(
            INSTALLER,
            'STAGE10_B4_MARKER="$2"; install_provenance_marker && verify_provenance_marker',
            str(marker),
        )
        require(result.returncode == 0, f"provenance install failed: {result.stderr}")
        require(marker.read_text() == EXPECTED_HEAD + "\n", "provenance content")
        require((marker.stat().st_mode & 0o777) == 0o644, "provenance mode")
    print("B4_ATOMIC_INSTALL_PROVENANCE=PASS")


def finalizer_smoke():
    with tempfile.TemporaryDirectory(prefix="stage10-b4-finalizer-") as temp:
        counter = Path(temp) / "starts"
        body = r'''
stage9_state=inactive
report_state=inactive
counter_path="$2"
systemctl() {
    case "$1:$2" in
        start:teddy-completion-stage9.timer) stage9_state=active; printf 'stage9\n' >> "$counter_path" ;;
        start:teddy-discovery-jav-reconcile.timer) report_state=active; printf 'report\n' >> "$counter_path" ;;
        is-active:teddy-completion-stage9.timer) printf '%s\n' "$stage9_state" ;;
        is-active:teddy-discovery-jav-reconcile.timer) printf '%s\n' "$report_state" ;;
        *) return 1 ;;
    esac
}
STAGE9_TIMER_STOP_ATTEMPTED=1
REPORT_TIMER_STOP_ATTEMPTED=1
STAGE9_TIMER_ACTIVE_BEFORE=active
REPORT_TIMER_ACTIVE_BEFORE=active
STAGE9_TIMER_RESTORED=0
REPORT_TIMER_RESTORED=0
CLEANUP_DONE=0
cleanup_timers
cleanup_timers
[ "$(wc -l < "$2")" = 2 ]
'''
        result = run_shell(INSTALLER, body, str(counter))
        require(result.returncode == 0, f"finalizer simulation failed: {result.stderr}")
        require(counter.read_text().splitlines() == ["stage9", "report"], "duplicate timer restart")
    print("B4_TIMER_FINALIZER_SIMULATION=PASS")


def canary_parser_smoke():
    outputs = {
        "noop": "RESULT=PASS\nACTION=NOOP\nAPPLY=0\nINSERTED=0\nABSENT_MARKED=0\nREVIVED=0\nMETADATA_UPDATED=0\n",
        "applied": "RESULT=PASS\nACTION=APPLIED\nAPPLY=1\n",
        "hold": "RESULT=HOLD\nREASON=UNSAFE\nAPPLY=0\n",
        "skip": "RESULT=SKIP\nREASON=BUSY\nAPPLY=0\n",
        "fail": "RESULT=FAIL\nREASON=ERROR\nAPPLY=0\n",
    }
    with tempfile.TemporaryDirectory(prefix="stage10-b4-canary-") as temp:
        paths = {}
        for name, content in outputs.items():
            path = Path(temp) / name
            path.write_text(content)
            paths[name] = path

        result = run_shell(INSTALLER, 'parse_noop_canary_journal "$2"', str(paths["noop"]))
        require(result.returncode == 0, "valid NOOP rejected")
        for name in ("applied", "hold", "skip", "fail"):
            result = run_shell(INSTALLER, 'parse_noop_canary_journal "$2"', str(paths[name]))
            require(result.returncode != 0, f"{name} accepted as NOOP")
    print("B4_NOOP_CANARY_PARSER=PASS")


def rollback_simulation_smoke():
    with tempfile.TemporaryDirectory(prefix="stage10-b4-rollback-") as temp:
        temp_path = Path(temp)
        runtime = temp_path / "runtime"
        backup = temp_path / "backup"
        runtime.mkdir()
        (backup / "runtime").mkdir(parents=True)

        old_reconcile = "old reconcile\n"
        old_organizer = "old organizer\n"
        (backup / "runtime/teddy_discovery_jav_reconcile.py").write_text(old_reconcile)
        (backup / "runtime/teddy_discovery_organizer_apply.py").write_text(old_organizer)
        (runtime / "teddy_discovery_jav_reconcile.py").write_text("new reconcile\n")
        (runtime / "teddy_discovery_organizer_apply.py").write_text("new organizer\n")
        add = runtime / "teddy_discovery_jav_reconcile_apply.py"
        wrapper = temp_path / "wrapper"
        service = temp_path / "service"
        marker = runtime / ".teddy-stage10-b4-commit"
        for path in (add, wrapper, service):
            path.write_text("B4\n")
        marker.write_text(EXPECTED_HEAD + "\n")

        result = run_shell(
            ROLLBACK,
            'BACKUP_DIR="$2"; RUNTIME_DIR="$3"; APPLY_WRAPPER="$4"; APPLY_SERVICE="$5"; STAGE10_B4_MARKER="$6"; restore_runtime',
            str(backup),
            str(runtime),
            str(wrapper),
            str(service),
            str(marker),
        )
        require(result.returncode == 0, f"rollback simulation failed: {result.stderr}")
        require((runtime / "teddy_discovery_jav_reconcile.py").read_text() == old_reconcile, "reconcile not restored")
        require((runtime / "teddy_discovery_organizer_apply.py").read_text() == old_organizer, "organizer not restored")
        for path in (add, wrapper, service, marker):
            require(not path.exists(), f"B4 artifact remains: {path}")
    print("B4_ROLLBACK_SIMULATION=PASS")


def main():
    syntax_smoke()
    static_manifest_smoke()
    dirty_allowlist_smoke()
    atomic_and_provenance_smoke()
    finalizer_smoke()
    canary_parser_smoke()
    rollback_simulation_smoke()
    print("B4_DEPLOYMENT_TOOLING_SMOKE=PASS")


if __name__ == "__main__":
    main()
