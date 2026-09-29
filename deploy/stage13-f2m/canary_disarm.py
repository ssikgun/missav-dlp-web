#!/usr/bin/env python3
"""Fail-closed, gate-off disarm for the Stage13 delete canary window.

The production watchdog invokes this helper after its bounded timer expires.
It never sends a delete API request. The global operation freeze is released
only after the gate-off web container has passed its local readiness checks.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Protocol
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener


REQUIRED_MOUNTS = {
    "/discovery/teddy-discovery.sqlite3": False,
    "/run/teddy-library-discovery-writer": False,
    "/run/teddy-title-locks": True,
    "/discovery/stage12-rollout-state.sqlite3": False,
    "/run/secrets/teddy-nas/id_ed25519": False,
    "/run/secrets/teddy-nas/known_hosts": False,
    "/run/secrets/teddy-jellyfin/api_key": False,
}


class DisarmBackend(Protocol):
    def freeze_active(self) -> bool: ...
    def gate_off_configured(self) -> bool: ...
    def recreate_web_gate_off(self) -> bool: ...
    def container_state(self) -> str: ...
    def login_status(self) -> int | None: ...
    def writer_ready(self) -> bool: ...
    def mounts_valid(self) -> bool: ...
    def runtime_gate_off(self) -> bool: ...
    def restart_policy(self) -> str | None: ...
    def stop_web_fail_safe(self) -> None: ...
    def release_freeze(self) -> bool: ...
    def cleanup_watchdog(self) -> bool: ...


@dataclass(frozen=True)
class DisarmResult:
    status: str
    readiness_seconds: float


class DisarmFailure(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def disarm(
    backend: DisarmBackend,
    *,
    timeout_seconds: float = 120.0,
    poll_interval_seconds: float = 2.0,
    require_freeze: bool = False,
    monotonic=time.monotonic,
    sleep=time.sleep,
) -> DisarmResult:
    """Recreate only the web service gate-off and verify before releasing freeze."""
    if timeout_seconds <= 0 or poll_interval_seconds <= 0:
        raise ValueError("positive timeout and poll interval required")
    started = monotonic()
    try:
        if require_freeze and not backend.freeze_active():
            raise DisarmFailure("freeze_required")
        if not backend.gate_off_configured():
            raise DisarmFailure("gate_off_config_invalid")
        if not backend.recreate_web_gate_off():
            raise DisarmFailure("web_recreate_failed")

        deadline = started + timeout_seconds
        while True:
            # Running alone is insufficient: wait for the local application.
            if backend.container_state() == "running" and backend.login_status() == 200:
                break
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise DisarmFailure("readiness_timeout")
            sleep(min(poll_interval_seconds, remaining))

        if not backend.writer_ready():
            raise DisarmFailure("writer_unavailable")
        if not backend.mounts_valid():
            raise DisarmFailure("mount_contract_failed")
        if not backend.runtime_gate_off():
            raise DisarmFailure("runtime_gate_not_false")
        if backend.restart_policy() != "unless-stopped":
            raise DisarmFailure("restart_policy_not_restored")

        # All safety checks are complete. Only now may other host mutators run.
        if not backend.release_freeze():
            raise DisarmFailure("freeze_release_failed")
        if not backend.cleanup_watchdog():
            raise DisarmFailure("watchdog_cleanup_failed")
        return DisarmResult("DISARMED", max(0.0, monotonic() - started))
    except DisarmFailure:
        try:
            backend.stop_web_fail_safe()
        except Exception:
            pass
        raise
    except Exception as exc:
        try:
            backend.stop_web_fail_safe()
        except Exception:
            pass
        # Do not include exception text: subprocess errors can contain config.
        raise DisarmFailure("internal_check_failed") from exc


def _run(argv: list[str], *, timeout: float = 10.0) -> subprocess.CompletedProcess:
    return subprocess.run(argv, check=False, capture_output=True, text=True, timeout=timeout)


class HostDockerBackend:
    def __init__(self, args):
        self.args = args
        self.compose = [
            args.docker, "compose", "--project-directory", args.project_directory,
            "-f", args.compose_file, "--env-file", args.env_file,
        ]

    def _systemd_active(self, unit: str) -> bool:
        return _run([self.args.systemctl, "is-active", "--quiet", unit]).returncode == 0

    def freeze_active(self) -> bool:
        return self._systemd_active(self.args.freeze_unit)

    def gate_off_configured(self) -> bool:
        result = _run(self.compose + ["config", "--format", "json"], timeout=20)
        if result.returncode:
            return False
        try:
            service = json.loads(result.stdout)["services"][self.args.service]
            environment = service["environment"]
            return (environment.get("TEDDY_LIBRARY_DELETE_ENABLED") == "false"
                    and service.get("restart") == "unless-stopped"
                    and service.get("image") == self.args.expected_image)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return False

    def recreate_web_gate_off(self) -> bool:
        result = _run(self.compose + ["up", "-d", "--no-deps", "--force-recreate", self.args.service], timeout=90)
        return result.returncode == 0

    def container_state(self) -> str:
        result = _run([self.args.docker, "inspect", self.args.container,
                       "--format", "{{.State.Status}}"])
        return result.stdout.strip() if result.returncode == 0 else "missing"

    def login_status(self) -> int | None:
        try:
            opener = build_opener(ProxyHandler({}))
            with opener.open(self.args.login_url, timeout=3.0) as response:
                return response.status
        except (URLError, TimeoutError, OSError):
            return None

    def writer_ready(self) -> bool:
        code = (
            "import os; from teddy_library_discovery_writer import "
            "UnixSocketDiscoveryWriterClient; "
            "r=UnixSocketDiscoveryWriterClient(" 
            "os.environ.get('TEDDY_LIBRARY_DELETE_DISCOVERY_WRITER_SOCKET')).request('health'); "
            "print(r.get('status'))"
        )
        result = _run([self.args.docker, "exec", self.args.container,
                       "python3", "-c", code])
        return result.returncode == 0 and result.stdout.strip() == "READY"

    def mounts_valid(self) -> bool:
        result = _run([self.args.docker, "inspect", self.args.container,
                       "--format", "{{json .Mounts}}"])
        if result.returncode:
            return False
        try:
            mounts = {m["Destination"]: m for m in json.loads(result.stdout)}
            return all(
                target in mounts and mounts[target].get("Type") == "bind"
                and mounts[target].get("RW") is writable
                for target, writable in REQUIRED_MOUNTS.items()
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return False

    def runtime_gate_off(self) -> bool:
        result = _run([self.args.docker, "exec", self.args.container, "python3", "-c",
                       "import os; print(os.getenv('TEDDY_LIBRARY_DELETE_ENABLED','missing'))"])
        return result.returncode == 0 and result.stdout.strip() == "false"

    def restart_policy(self) -> str | None:
        result = _run([self.args.docker, "inspect", self.args.container,
                       "--format", "{{.HostConfig.RestartPolicy.Name}}"])
        return result.stdout.strip() if result.returncode == 0 else None

    def stop_web_fail_safe(self) -> None:
        # Disable automatic restart before stopping, so a failed health check
        # cannot silently bring the gate-off web app back without the freeze.
        _run([self.args.docker, "update", "--restart=no", self.args.container])
        _run([self.args.docker, "stop", "--time", "10", self.args.container], timeout=20)

    def release_freeze(self) -> bool:
        if not self.freeze_active():
            return True
        result = _run([self.args.systemctl, "stop", self.args.freeze_unit], timeout=15)
        return result.returncode == 0 and not self.freeze_active()

    def cleanup_watchdog(self) -> bool:
        # A fired transient timer may already have disappeared; that is safe.
        result = _run([self.args.systemctl, "stop", self.args.watchdog_timer], timeout=10)
        if result.returncode == 0:
            return True
        return "not loaded" in (result.stderr + result.stdout).lower() or "not-found" in (result.stderr + result.stdout).lower()


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose-file", default="/opt/missav-dlp-web/compose.yaml")
    parser.add_argument("--env-file", default="/opt/missav-dlp-web/gluetun.env")
    parser.add_argument("--project-directory", default="/opt/missav-dlp-web")
    parser.add_argument("--service", default="missav-dlp-web")
    parser.add_argument("--container", default="missav-dlp-web")
    parser.add_argument("--expected-image", default="missav-dlp-web:stage13f2ma3-3dc801a")
    parser.add_argument("--login-url", default="http://127.0.0.1:58000/login")
    parser.add_argument("--freeze-unit", default="teddy-f2ma6-freeze-holder.service")
    parser.add_argument("--watchdog-timer", default="teddy-f2ma6-watchdog.timer")
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=2.0)
    parser.add_argument("--require-freeze", action="store_true",
                         help="require the supervised freeze-holder before disarming")
    parser.add_argument("--docker", default="/usr/bin/docker")
    parser.add_argument("--systemctl", default="/usr/bin/systemctl")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    backend = HostDockerBackend(args)
    try:
        result = disarm(
            backend,
            timeout_seconds=args.timeout_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
            require_freeze=args.require_freeze,
        )
    except DisarmFailure as exc:
        print(json.dumps({"status": "FAIL_SAFE", "reason": exc.reason}, separators=(",", ":")))
        return 1
    print(json.dumps({"status": result.status,
                      "readiness_seconds": round(result.readiness_seconds, 3)}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
