#!/usr/bin/env python3
"""Deterministic gate-off disarm readiness and failure fixtures."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

MODULE = Path(__file__).with_name("canary_disarm.py")
spec = importlib.util.spec_from_file_location("canary_disarm", MODULE)
disarm_mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = disarm_mod
spec.loader.exec_module(disarm_mod)


class Fake:
    def __init__(self, *, states=None, logins=None, freeze=True, gate_config=True,
                 writer=True, mounts=True, gate=False, restart="unless-stopped"):
        self.states = list(states or ["running"])
        self.logins = list(logins or [200])
        self.freeze = freeze
        self.gate_config = gate_config
        self.writer = writer
        self.mounts = mounts
        self.gate = gate
        self.restart = restart
        self.events = []

    def freeze_active(self): return self.freeze
    def gate_off_configured(self): self.events.append("check_gate_off"); return self.gate_config
    def recreate_web_gate_off(self): self.events.append("recreate_web"); self.gate = False; return True
    def container_state(self): return self.states.pop(0) if len(self.states) > 1 else self.states[0]
    def login_status(self): return self.logins.pop(0) if len(self.logins) > 1 else self.logins[0]
    def writer_ready(self): self.events.append("writer"); return self.writer
    def mounts_valid(self): self.events.append("mounts"); return self.mounts
    def runtime_gate_off(self): self.events.append("runtime_gate"); return not self.gate
    def restart_policy(self): self.events.append("restart_policy"); return self.restart
    def stop_web_fail_safe(self): self.events.append("stop_web"); self.restart = "no"
    def release_freeze(self): self.events.append("release_freeze"); self.freeze = False; return True
    def cleanup_watchdog(self): self.events.append("cleanup_watchdog"); return True


class Clock:
    def __init__(self): self.now = 0.0
    def monotonic(self): return self.now
    def sleep(self, seconds): self.now += seconds


def expect_failure(fake, reason, *, timeout=6, interval=2):
    clock = Clock()
    try:
        disarm_mod.disarm(fake, timeout_seconds=timeout, poll_interval_seconds=interval,
                          monotonic=clock.monotonic, sleep=clock.sleep)
    except disarm_mod.DisarmFailure as exc:
        assert exc.reason == reason, (exc.reason, reason)
        assert fake.freeze, "freeze must remain held on any failed verification"
        assert fake.events[-1] == "stop_web", fake.events
        assert fake.restart == "no"
        assert "release_freeze" not in fake.events
        return
    raise AssertionError(f"expected {reason}")


# 1. Immediate readiness.
f=Fake(); c=Clock(); r=disarm_mod.disarm(f,monotonic=c.monotonic,sleep=c.sleep)
assert r.status=="DISARMED" and r.readiness_seconds==0 and not f.freeze
assert f.events.index("release_freeze") < f.events.index("cleanup_watchdog")

# 2. Delayed readiness after 24 seconds.
f=Fake(states=["starting"]*12+["running"],logins=[200]); c=Clock()
r=disarm_mod.disarm(f,timeout_seconds=120,monotonic=c.monotonic,sleep=c.sleep)
assert r.status=="DISARMED" and r.readiness_seconds==24

# 3. Connection-refused/502-like non-200 responses followed by 200.
f=Fake(states=["running"]*4,logins=[None,502,503,200]); c=Clock()
r=disarm_mod.disarm(f,monotonic=c.monotonic,sleep=c.sleep)
assert r.readiness_seconds==6 and not f.freeze

# 4. Timeout: web stops, restart disabled, freeze remains held.
expect_failure(Fake(states=["running"],logins=[None]),"readiness_timeout")

# 5. Writer unavailable.
expect_failure(Fake(writer=False),"writer_unavailable")

# The canonical Compose/env gate must already resolve false; otherwise stop.
expect_failure(Fake(gate_config=False),"gate_off_config_invalid")

# 6. Runtime gate did not become false after recreate.
f=Fake(gate=True); f.recreate_web_gate_off=lambda: (f.events.append("recreate_web") or True)
try:
    disarm_mod.disarm(f,monotonic=Clock().monotonic,sleep=lambda _:None)
except disarm_mod.DisarmFailure as exc:
    assert exc.reason=="runtime_gate_not_false" and f.freeze and f.events[-1]=="stop_web"
else: raise AssertionError("runtime gate check must fail closed")

# 7. Restart policy could not be restored.
expect_failure(Fake(restart="no"),"restart_policy_not_restored")

# 8. Any exception before release retains freeze and stops web.
f=Fake(); f.mounts_valid=lambda: (_ for _ in ()).throw(RuntimeError("SECRET_SENTINEL"))
try: disarm_mod.disarm(f,monotonic=Clock().monotonic,sleep=lambda _:None)
except disarm_mod.DisarmFailure as exc:
    assert exc.reason=="internal_check_failed" and f.freeze and f.events[-1]=="stop_web"
    assert "SECRET_SENTINEL" not in str(exc)
else: raise AssertionError("unexpected pass")

# 9. Idempotent gate-off while web is already healthy.
f=Fake(gate=False); c=Clock(); assert disarm_mod.disarm(f,monotonic=c.monotonic,sleep=c.sleep).status=="DISARMED"

# 9a. Gate-on/running is disarmed; gate-off/stopped is safely recreated.
f=Fake(gate=True); c=Clock(); assert disarm_mod.disarm(f,monotonic=c.monotonic,sleep=c.sleep).status=="DISARMED"
f=Fake(gate=False,states=["exited","running"],logins=[200]); c=Clock()
assert disarm_mod.disarm(f,monotonic=c.monotonic,sleep=c.sleep).status=="DISARMED"

# 10. The watchdog may recover gate-off with no freeze unit; release is a no-op.
f=Fake(freeze=False); c=Clock(); assert disarm_mod.disarm(f,monotonic=c.monotonic,sleep=c.sleep).status=="DISARMED"
assert f.events.index("release_freeze") < f.events.index("cleanup_watchdog")

# An operator rehearsal can require the holder explicitly.
f=Fake(freeze=False); c=Clock()
try: disarm_mod.disarm(f,require_freeze=True,monotonic=c.monotonic,sleep=c.sleep)
except disarm_mod.DisarmFailure as exc:
    assert exc.reason=="freeze_required" and not f.freeze and f.events==["stop_web"]
else: raise AssertionError("missing required freeze must fail closed")

# Recreate from gate-true/stopped state is also idempotent.
f=Fake(states=["exited","running"],logins=[None,200],gate=True); c=Clock()
assert disarm_mod.disarm(f,monotonic=c.monotonic,sleep=c.sleep).status=="DISARMED"

# Logs/errors are safe reason codes only, not exception payloads.
assert "SECRET_SENTINEL" not in str(f.events)
print("CANARY_DISARM_READINESS_SMOKE=PASS")
print("IMMEDIATE=PASS DELAYED=PASS TRANSIENT_HTTP=PASS TIMEOUT_FAIL_CLOSED=PASS")
print("WRITER_GATE_RESTART_FAILURES=PASS FREEZE_ORDER=PASS IDEMPOTENT=PASS")
