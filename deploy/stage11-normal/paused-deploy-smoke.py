#!/usr/bin/env python3
"""Offline integration checks for the paused Stage11 deploy/rollback mode."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


SOURCE_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_DIR = SOURCE_ROOT / "deploy" / "stage11-normal"
CANDIDATE_SHA = "f89bd92b4f769a62622d9ed2b0fd7650f1912fc8"
OLD_SHA = "e4e0b05bee3550b0ba2734e71ccccb319e802864"


SYSTEMCTL = r'''#!/bin/bash
set -euo pipefail
root="$STAGE11_TEST_ROOT"
printf 'systemctl %s\n' "$*" >> "$root/events.log"
command="$1"
shift
case "$command" in
  is-enabled)
    cat "$root/timer-enabled"
    ;;
  is-active)
    quiet=0
    if [[ "${1:-}" == --quiet ]]; then quiet=1; shift; fi
    unit="${1:?unit required}"
    if [[ "$unit" == teddy-subtitle-normal.timer ]]; then
      value="$(cat "$root/timer-active")"
    else
      value="$(cat "$root/service-active")"
    fi
    if (( quiet )); then
      [[ "$value" == active ]]
    else
      printf '%s\n' "$value"
      [[ "$value" == active ]]
    fi
    ;;
  disable)
    [[ "${1:-}" == --now ]]
    [[ "${2:-}" == teddy-subtitle-normal.timer ]]
    printf 'disabled\n' > "$root/timer-enabled"
    printf 'inactive\n' > "$root/timer-active"
    ;;
  enable)
    now=0
    if [[ "${1:-}" == --now ]]; then now=1; shift; fi
    [[ "${1:-}" == teddy-subtitle-normal.timer ]]
    printf 'enabled\n' > "$root/timer-enabled"
    if (( now )); then printf 'active\n' > "$root/timer-active"; fi
    ;;
  start)
    [[ "${1:-}" == teddy-subtitle-normal.timer ]]
    printf 'active\n' > "$root/timer-active"
    ;;
  restart)
    exit 88
    ;;
  daemon-reload)
    if [[ "${FAKE_FAIL_DAEMON_RELOAD:-}" == once \
        && ! -e "$root/daemon-reload-failed" ]]; then
      touch "$root/daemon-reload-failed"
      exit 87
    fi
    ;;
  show)
    printf 'ActiveState=%s\nSubState=%s\n' \
      "$(cat "$root/timer-active")" "$(cat "$root/timer-active")"
    ;;
  *)
    printf 'unexpected systemctl command: %s\n' "$command" >&2
    exit 89
    ;;
esac
'''


GIT = r'''#!/bin/bash
set -euo pipefail
if [[ "${1:-}" == -C ]]; then source_path="$2"; shift 2; else source_path=""; fi
printf 'git %s %s\n' "$source_path" "$*" >> "$STAGE11_TEST_ROOT/events.log"
case "${1:-}" in
  rev-parse)
    shift
    if [[ "${1:-}" == HEAD ]]; then
      resolved="$(realpath -m -- "$source_path")"
      case "$resolved" in
        */releases/$STAGE11_CANDIDATE_SHA) printf '%s\n' "$STAGE11_CANDIDATE_SHA" ;;
        */releases/$STAGE11_OLD_SHA) printf '%s\n' "$STAGE11_OLD_SHA" ;;
        *) exit 1 ;;
      esac
    elif [[ "${1:-}" == "$STAGE11_CANDIDATE_SHA" ]]; then
      printf '%s\n' "$STAGE11_CANDIDATE_SHA"
    else
      exit 1
    fi
    ;;
  status)
    if [[ "${FAKE_RELEASE_DIRTY:-}" == yes \
        && "$(realpath -m -- "$source_path")" == */releases/$STAGE11_CANDIDATE_SHA ]]; then
      printf ' M dirty-fixture\n'
    fi
    ;;
  worktree)
    [[ "${2:-}" == add && "${3:-}" == --detach ]]
    release="$4"
    revision="$5"
    [[ "$revision" == "$STAGE11_CANDIDATE_SHA" ]]
    mkdir -p "$release/deploy/stage11-normal"
    cp "$STAGE11_TEST_SOURCE/deploy/stage11-normal/teddy-subtitle-normal.service" \
      "$release/deploy/stage11-normal/"
    cp "$STAGE11_TEST_SOURCE/deploy/stage11-normal/teddy-subtitle-normal.timer" \
      "$release/deploy/stage11-normal/"
    : > "$release/teddy_discovery_stage12_bulk_runner.py"
    ;;
  *)
    printf 'unexpected git arguments: %s\n' "$*" >&2
    exit 90
    ;;
esac
'''


PYTHON = r'''#!/bin/bash
set -euo pipefail
printf 'PREFLIGHT %s\n' "$*" >> "$STAGE11_TEST_ROOT/events.log"
[[ "${1:-}" == -u ]]
[[ "${2:-}" == */teddy_discovery_stage12_bulk_runner.py ]]
[[ "$*" == *"--mode preflight"* ]]
[[ "$*" == *"--expected-head $STAGE11_CANDIDATE_SHA"* ]]
if [[ "${FAKE_ACTIVATE_TIMER_AFTER_PREFLIGHT:-}" == yes ]]; then
  printf 'enabled\n' > "$STAGE11_TEST_ROOT/timer-enabled"
  printf 'active\n' > "$STAGE11_TEST_ROOT/timer-active"
fi
exit "${FAKE_PREFLIGHT_STATUS:-0}"
'''


MV = r'''#!/bin/bash
set -euo pipefail
destination="${@: -1}"
base="$(basename -- "$destination")"
root="$STAGE11_TEST_ROOT"
printf 'mv %s\n' "$*" >> "$root/events.log"
if [[ "${FAKE_FAIL_MV_DEST:-}" == "$base" \
    && ! -e "$root/mv-failed-$base" ]]; then
  touch "$root/mv-failed-$base"
  exit 91
fi
/bin/mv "$@"
if [[ "${FAKE_ACTIVATE_TIMER_AFTER_MV_DEST:-}" == "$base" \
    && ! -e "$root/timer-activated-after-$base" ]]; then
  touch "$root/timer-activated-after-$base"
  printf 'enabled\n' > "$root/timer-enabled"
  printf 'active\n' > "$root/timer-active"
fi
'''


INSTALL = r'''#!/bin/bash
set -euo pipefail
source="$3"
base="$(basename -- "$source")"
root="$STAGE11_TEST_ROOT"
printf 'install %s\n' "$*" >> "$root/events.log"
if [[ "${FAKE_FAIL_INSTALL_BASENAME:-}" == "$base" \
    && ! -e "$root/install-failed-$base" ]]; then
  touch "$root/install-failed-$base"
  exit 92
fi
/usr/bin/install "$@"
'''


FORBIDDEN_SYSTEMCTL = re.compile(r"(?:^|\s)(?:enable|start|restart)(?:\s|$)")


class Fixture:
    def __init__(self, *, timer_enabled="disabled", timer_active="inactive",
                 service_active="inactive", **injections):
        self.temp = tempfile.TemporaryDirectory(prefix="stage11-paused-deploy-")
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.deployment = self.root / "deployment"
        self.units = self.root / "systemd"
        self.bin = self.root / "bin"
        self.old_release = self.deployment / "releases" / OLD_SHA
        self.candidate_release = self.deployment / "releases" / CANDIDATE_SHA
        self.units.mkdir(parents=True)
        self.bin.mkdir()
        (self.deployment / "backups").mkdir(parents=True)
        self.old_release.mkdir(parents=True)
        (self.old_release / "fixture-head").write_text(OLD_SHA)
        self.source_deploy = self.source / "deploy" / "stage11-normal"
        self.source_deploy.mkdir(parents=True)
        for name in ("deploy.sh", "rollback.sh", "paused-common.sh",
                     "teddy-subtitle-normal.service", "teddy-subtitle-normal.timer"):
            shutil.copy2(DEPLOY_DIR / name, self.source_deploy / name)
        (self.deployment / "current").symlink_to(self.old_release)
        (self.deployment / "runtime.env").write_text(f"STAGE11_NORMAL_HEAD={OLD_SHA}\n")
        shutil.copy2(self.source_deploy / "teddy-subtitle-normal.service", self.units)
        shutil.copy2(self.source_deploy / "teddy-subtitle-normal.timer", self.units)

        replacements = {
            "/opt/missav-dlp-web/discovery/stage11-normal-deployment": str(self.deployment),
            "/etc/systemd/system": str(self.units),
            "/opt/stage11-stt-venv/bin/python": str(self.bin / "python"),
            "/opt/missav-dlp-web/title-locks": str(self.root / "title-locks"),
        }
        for name in ("deploy.sh", "rollback.sh"):
            path = self.source_deploy / name
            contents = path.read_text()
            for old, new in replacements.items():
                contents = contents.replace(old, new)
            path.write_text(contents)

        for name, contents in (("systemctl", SYSTEMCTL), ("git", GIT),
                               ("python", PYTHON), ("mv", MV), ("install", INSTALL)):
            path = self.bin / name
            path.write_text(contents)
            path.chmod(0o755)

        for name, value in (("timer-enabled", timer_enabled), ("timer-active", timer_active),
                            ("service-active", service_active)):
            (self.root / name).write_text(value + "\n")
        self.injections = injections
        self.env = os.environ.copy()
        self.env.update({
            "PATH": str(self.bin) + os.pathsep + self.env.get("PATH", ""),
            "STAGE11_TEST_ROOT": str(self.root),
            "STAGE11_TEST_SOURCE": str(self.source),
            "STAGE11_CANDIDATE_SHA": CANDIDATE_SHA,
            "STAGE11_OLD_SHA": OLD_SHA,
        })
        self.env.update({key: str(value) for key, value in injections.items()})

    def close(self):
        self.temp.cleanup()

    def run(self, script, *args):
        return subprocess.run(
            ["bash", str(self.source_deploy / script), *args],
            env=self.env,
            cwd=self.source,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=15,
        )

    def event_lines(self):
        path = self.root / "events.log"
        return path.read_text().splitlines() if path.exists() else []

    def assert_no_paused_activation(self, testcase):
        calls = [line for line in self.event_lines() if line.startswith("systemctl ")]
        testcase.assertFalse([line for line in calls if FORBIDDEN_SYSTEMCTL.search(line)], calls)

    def assert_old_operational_state(self, testcase):
        testcase.assertEqual((self.deployment / "current").resolve(), self.old_release,
                             "events=" + "\\n".join(self.event_lines()))
        testcase.assertEqual((self.deployment / "runtime.env").read_text(),
                             f"STAGE11_NORMAL_HEAD={OLD_SHA}\n")
        testcase.assertEqual((self.units / "teddy-subtitle-normal.service").read_bytes(),
                             (self.source_deploy / "teddy-subtitle-normal.service").read_bytes())
        testcase.assertEqual((self.units / "teddy-subtitle-normal.timer").read_bytes(),
                             (self.source_deploy / "teddy-subtitle-normal.timer").read_bytes())

    def assert_no_restore_temporaries(self, testcase):
        testcase.assertFalse(list(self.deployment.glob(".runtime.env.next.*")))
        testcase.assertFalse(list(self.deployment.glob(".current.rollback.*")))


class PausedDeploySmoke(unittest.TestCase):
    def fixture(self, **kwargs):
        item = Fixture(**kwargs)
        self.addCleanup(item.close)
        return item

    def test_success_is_paused_and_checks_after_preflight(self):
        item = self.fixture()
        result = item.run("deploy.sh", "--paused", CANDIDATE_SHA)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual((item.deployment / "current").resolve(), item.candidate_release)
        self.assertEqual((item.deployment / "runtime.env").read_text(),
                         f"STAGE11_NORMAL_HEAD={CANDIDATE_SHA}\n")
        self.assertEqual((item.root / "timer-enabled").read_text(), "disabled\n")
        self.assertEqual((item.root / "timer-active").read_text(), "inactive\n")
        self.assertEqual((item.root / "service-active").read_text(), "inactive\n")
        self.assertIn("DEPLOY_MODE=PAUSED_TIMER_REMAINS_DISABLED", result.stdout)
        events = item.event_lines()
        preflight_index = next(i for i, line in enumerate(events) if line.startswith("PREFLIGHT "))
        pointer_index = next(
            i for i, line in enumerate(events)
            if line.startswith("mv -Tf ") and line.endswith("/current.next " + str(item.deployment / "current"))
        )
        after_preflight = events[preflight_index + 1:pointer_index]
        self.assertGreaterEqual(after_preflight.count(
            "systemctl is-enabled teddy-subtitle-normal.timer"), 2)
        self.assertGreaterEqual(after_preflight.count(
            "systemctl is-active teddy-subtitle-normal.timer"), 2)
        self.assertGreaterEqual(after_preflight.count(
            "systemctl is-active teddy-subtitle-normal.service"), 2)
        self.assertEqual(events[pointer_index - 3:pointer_index], [
            "systemctl is-enabled teddy-subtitle-normal.timer",
            "systemctl is-active teddy-subtitle-normal.timer",
            "systemctl is-active teddy-subtitle-normal.service",
        ])
        item.assert_no_paused_activation(self)
        item.assert_no_restore_temporaries(self)

    def test_active_timer_and_active_service_block_before_backup(self):
        for kwargs in (
            {"timer_enabled": "enabled", "timer_active": "active"},
            {"service_active": "active"},
        ):
            with self.subTest(kwargs=kwargs):
                item = self.fixture(**kwargs)
                result = item.run("deploy.sh", "--paused", CANDIDATE_SHA)
                self.assertNotEqual(result.returncode, 0)
                item.assert_old_operational_state(self)
                self.assertFalse(list((item.deployment / "backups").iterdir()))
                item.assert_no_paused_activation(self)

    def test_invalid_sha_and_dirty_candidate_block(self):
        item = self.fixture()
        bad = item.run("deploy.sh", "--paused", "not-a-commit")
        self.assertNotEqual(bad.returncode, 0)
        self.assertFalse(item.event_lines())
        unknown = item.run("deploy.sh", "--paused", "0" * 40)
        self.assertNotEqual(unknown.returncode, 0)
        item.assert_no_paused_activation(self)
        self.assertFalse(any(line.startswith("PREFLIGHT ") for line in item.event_lines()))

        dirty = self.fixture(FAKE_RELEASE_DIRTY="yes")
        result = dirty.run("deploy.sh", "--paused", CANDIDATE_SHA)
        self.assertNotEqual(result.returncode, 0)
        dirty.assert_old_operational_state(self)
        dirty.assert_no_paused_activation(self)

    def test_preflight_failure_keeps_current_config_units_and_timer(self):
        item = self.fixture(FAKE_PREFLIGHT_STATUS="17")
        result = item.run("deploy.sh", "--paused", CANDIDATE_SHA)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DEPLOY=PREFLIGHT_FAILED", result.stdout)
        item.assert_old_operational_state(self)
        self.assertEqual((item.root / "timer-enabled").read_text(), "disabled\n")
        self.assertEqual((item.root / "timer-active").read_text(), "inactive\n")
        item.assert_no_paused_activation(self)

        raced = self.fixture(FAKE_ACTIVATE_TIMER_AFTER_PREFLIGHT="yes")
        result = raced.run("deploy.sh", "--paused", CANDIDATE_SHA)
        self.assertNotEqual(result.returncode, 0)
        raced.assert_old_operational_state(self)
        self.assertEqual((raced.root / "timer-enabled").read_text(), "disabled\n")
        self.assertEqual((raced.root / "timer-active").read_text(), "inactive\n")
        raced.assert_no_paused_activation(self)

    def test_pointer_runtime_unit_and_daemon_reload_failures_restore(self):
        injections = (
            {"FAKE_FAIL_MV_DEST": "current"},
            {"FAKE_FAIL_MV_DEST": "runtime.env"},
            {"FAKE_FAIL_INSTALL_BASENAME": "teddy-subtitle-normal.service"},
            {"FAKE_FAIL_INSTALL_BASENAME": "teddy-subtitle-normal.timer"},
            {"FAKE_FAIL_DAEMON_RELOAD": "once"},
        )
        for failure in injections:
            with self.subTest(failure=failure):
                item = self.fixture(**failure)
                result = item.run("deploy.sh", "--paused", CANDIDATE_SHA)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("DEPLOY=PAUSED_FAILURE_ROLLED_BACK", result.stdout)
                item.assert_old_operational_state(self)
                self.assertEqual((item.root / "timer-enabled").read_text(), "disabled\n")
                self.assertEqual((item.root / "timer-active").read_text(), "inactive\n")
                self.assertFalse((item.deployment / "current.next").exists()
                                 or (item.deployment / "current.next").is_symlink())
                item.assert_no_paused_activation(self)
                item.assert_no_restore_temporaries(self)

    def test_state_race_after_switch_disables_timer_and_restores(self):
        item = self.fixture(FAKE_ACTIVATE_TIMER_AFTER_MV_DEST="current")
        result = item.run("deploy.sh", "--paused", CANDIDATE_SHA)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("DEPLOY=PAUSED_FAILURE_ROLLED_BACK", result.stdout)
        item.assert_old_operational_state(self)
        self.assertEqual((item.root / "timer-enabled").read_text(), "disabled\n")
        self.assertEqual((item.root / "timer-active").read_text(), "inactive\n")
        item.assert_no_paused_activation(self)

    def test_paused_rollback_restores_exact_state_and_rejects_corrupt_backup(self):
        item = self.fixture()
        deployed = item.run("deploy.sh", "--paused", CANDIDATE_SHA)
        self.assertEqual(deployed.returncode, 0, deployed.stdout)
        backup_match = re.search(r"ROLLBACK_BACKUP=(\S+)", deployed.stdout)
        self.assertIsNotNone(backup_match, deployed.stdout)
        backup = backup_match.group(1)
        rollback = item.run("rollback.sh", "--paused", backup)
        self.assertEqual(rollback.returncode, 0, rollback.stdout)
        self.assertIn("PAUSED_ROLLBACK=COMPLETE", rollback.stdout)
        item.assert_old_operational_state(self)
        self.assertEqual((item.root / "timer-enabled").read_text(), "disabled\n")
        self.assertEqual((item.root / "timer-active").read_text(), "inactive\n")
        item.assert_no_paused_activation(self)

        corrupt = self.fixture()
        deployed = corrupt.run("deploy.sh", "--paused", CANDIDATE_SHA)
        self.assertEqual(deployed.returncode, 0, deployed.stdout)
        backup = re.search(r"ROLLBACK_BACKUP=(\S+)", deployed.stdout).group(1)
        Path(backup, "runtime.env").write_text("tampered\n")
        before_current = (corrupt.deployment / "current").resolve()
        before_runtime = (corrupt.deployment / "runtime.env").read_bytes()
        before_service = (corrupt.units / "teddy-subtitle-normal.service").read_bytes()
        before_timer = (corrupt.units / "teddy-subtitle-normal.timer").read_bytes()
        (corrupt.root / "timer-enabled").write_text("enabled\n")
        (corrupt.root / "timer-active").write_text("active\n")
        rejected = corrupt.run("rollback.sh", "--paused", backup)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual((corrupt.deployment / "current").resolve(), before_current)
        self.assertEqual((corrupt.deployment / "runtime.env").read_bytes(), before_runtime)
        self.assertEqual((corrupt.units / "teddy-subtitle-normal.service").read_bytes(), before_service)
        self.assertEqual((corrupt.units / "teddy-subtitle-normal.timer").read_bytes(), before_timer)
        self.assertEqual((corrupt.root / "timer-enabled").read_text(), "disabled\n")
        self.assertEqual((corrupt.root / "timer-active").read_text(), "inactive\n")
        corrupt.assert_no_paused_activation(self)

        missing = self.fixture()
        deployed = missing.run("deploy.sh", "--paused", CANDIDATE_SHA)
        self.assertEqual(deployed.returncode, 0, deployed.stdout)
        missing_backup = str(missing.deployment / "backups" / "missing-backup")
        before_current = (missing.deployment / "current").resolve()
        (missing.root / "timer-enabled").write_text("enabled\n")
        (missing.root / "timer-active").write_text("active\n")
        rejected = missing.run("rollback.sh", "--paused", missing_backup)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual((missing.deployment / "current").resolve(), before_current)
        self.assertEqual((missing.root / "timer-enabled").read_text(), "disabled\n")
        self.assertEqual((missing.root / "timer-active").read_text(), "inactive\n")
        missing.assert_no_paused_activation(self)

        active_service = self.fixture()
        deployed = active_service.run("deploy.sh", "--paused", CANDIDATE_SHA)
        self.assertEqual(deployed.returncode, 0, deployed.stdout)
        backup = re.search(r"ROLLBACK_BACKUP=(\S+)", deployed.stdout).group(1)
        (active_service.root / "service-active").write_text("active\n")
        before_current = (active_service.deployment / "current").resolve()
        rejected = active_service.run("rollback.sh", "--paused", backup)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual((active_service.deployment / "current").resolve(), before_current)
        self.assertEqual((active_service.root / "service-active").read_text(), "active\n")
        self.assertEqual((active_service.root / "timer-enabled").read_text(), "disabled\n")
        self.assertEqual((active_service.root / "timer-active").read_text(), "inactive\n")
        active_service.assert_no_paused_activation(self)

        active_timer = self.fixture()
        deployed = active_timer.run("deploy.sh", "--paused", CANDIDATE_SHA)
        self.assertEqual(deployed.returncode, 0, deployed.stdout)
        backup = re.search(r"ROLLBACK_BACKUP=(\S+)", deployed.stdout).group(1)
        (active_timer.root / "timer-enabled").write_text("enabled\n")
        (active_timer.root / "timer-active").write_text("active\n")
        rolled = active_timer.run("rollback.sh", "--paused", backup)
        self.assertEqual(rolled.returncode, 0, rolled.stdout)
        active_timer.assert_old_operational_state(self)
        self.assertEqual((active_timer.root / "timer-enabled").read_text(), "disabled\n")
        self.assertEqual((active_timer.root / "timer-active").read_text(), "inactive\n")
        active_timer.assert_no_paused_activation(self)

    def test_general_deploy_and_rollback_keep_live_contract(self):
        item = self.fixture(timer_enabled="enabled", timer_active="active")
        deployed = item.run("deploy.sh", CANDIDATE_SHA)
        self.assertEqual(deployed.returncode, 0, deployed.stdout)
        self.assertEqual((item.deployment / "current").resolve(), item.candidate_release)
        self.assertTrue(any(line == "systemctl enable --now teddy-subtitle-normal.timer"
                            for line in item.event_lines()))
        backup = re.search(r"ROLLBACK_BACKUP=(\S+)", deployed.stdout).group(1)
        rolled = item.run("rollback.sh", backup)
        self.assertEqual(rolled.returncode, 0, rolled.stdout)
        item.assert_old_operational_state(self)
        self.assertEqual((item.root / "timer-enabled").read_text(), "enabled\n")
        self.assertEqual((item.root / "timer-active").read_text(), "active\n")
        calls = [line for line in item.event_lines() if line.startswith("systemctl ")]
        self.assertIn("systemctl start teddy-subtitle-normal.timer", calls)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PausedDeploySmoke)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(f"PAUSED_DEPLOY_SMOKE={result.testsRun - len(result.failures) - len(result.errors)}/{result.testsRun}")
    raise SystemExit(0 if result.wasSuccessful() else 1)
