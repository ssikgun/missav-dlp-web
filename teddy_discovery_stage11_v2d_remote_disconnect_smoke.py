#!/usr/bin/env python3
"""No-model, isolated parent-loss witness for the real Stage11 REMOTE_NATIVE.

Read only the selected source. Run its literal REMOTE_NATIVE string using a
synthetic Hermes executable, synthetic auth and /tmp paths. SIGKILL simulates
an abruptly lost remote Python parent; no SSH, model, API, NAS or services.
This does not establish CT120 production cancellation guarantees.
"""
import ast
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time


def native_from_source(path):
    raw = path.read_bytes()
    tree = ast.parse(raw, filename=str(path))
    found = [
        node.value for node in tree.body
        if isinstance(node, ast.Assign) and any(
            isinstance(name, ast.Name) and name.id == "REMOTE_NATIVE"
            for name in node.targets
        )
    ]
    if len(found) != 1:
        raise ValueError("REMOTE_NATIVE declaration not unique")
    script = ast.literal_eval(found[0])
    if not isinstance(script, str) or "start_new_session=True" not in script:
        raise ValueError("unexpected REMOTE_NATIVE structure")
    return script, hashlib.sha256(raw).hexdigest()


def living(pid):
    try:
        state = (Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()[0]
        return state != "Z"
    except FileNotFoundError:
        return False


def owned_fake_group(pid, stub, directory):
    if type(pid) is not int or pid <= 1:
        return False
    try:
        proc = Path("/proc") / str(pid)
        uid_line = next(line for line in (proc / "status").read_text().splitlines()
                        if line.startswith("Uid:"))
        command = (proc / "cmdline").read_bytes()
        return (int(uid_line.split()[1]) == os.geteuid()
                and os.getpgid(pid) == pid
                and str(stub).encode() in command
                and stub.is_file() and stub.is_relative_to(directory))
    except (FileNotFoundError, ProcessLookupError, OSError, StopIteration, ValueError):
        return False


def main():
    if len(sys.argv) != 2:
        print("USAGE: python3 -B ...smoke.py /path/to/teddy_discovery_stage11_normal_mode.py")
        return 2
    source = Path(sys.argv[1])
    if not source.is_file() or source.is_symlink():
        print("SOURCE=NOT_VERIFIED")
        return 2
    code, checksum = native_from_source(source)
    print("SOURCE_SHA256=" + checksum, flush=True)
    root = Path(tempfile.mkdtemp(prefix="s11-v2d-disconnect-"))
    stub = root / "fake-hermes"
    parent = None
    child_pid = None
    try:
        profile = root / "synthetic" / "profiles" / "subtitle-translator"
        profile.mkdir(parents=True)
        (profile / "auth.json").write_text('{"synthetic":true}')
        pidfile = root / "remote" / "fake-child-pid"
        stub.write_text("""#!/usr/bin/env python3
import json, os, pathlib, sys, time
if 'prompt-size' in sys.argv:
    print(json.dumps({'tools': {'count': 0}}))
else:
    pathlib.Path(os.environ['HERMES_HOME'], 'fake-child-pid').write_text(str(os.getpid()))
    time.sleep(120)
""")
        stub.chmod(0o700)
        prompt = b"SYNTHETIC-NO-MODEL"
        request = {
            "root": str(root / "remote"), "source_profile": str(profile),
            "config": base64.b64encode(b"{}").decode("ascii"),
            "prompt": base64.b64encode(prompt).decode("ascii"),
            "prompt_sha256": hashlib.sha256(prompt).hexdigest(),
            "executable": str(stub),
            "provider": "synthetic", "model": "synthetic", "reasoning": "synthetic",
            "timeout_env": {
                "HERMES_API_CALL_STALE_TIMEOUT": "480",
                "HERMES_CODEX_TTFB_TIMEOUT_SECONDS": "300",
                "HERMES_CODEX_TTFB_MAX_SECONDS": "300",
                "HERMES_CODEX_EVENT_STALE_TIMEOUT_SECONDS": "300",
            },
        }
        parent = subprocess.Popen(
            [sys.executable, "-B", "-c", code],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True,
        )
        parent.stdin.write(json.dumps(request).encode("ascii"))
        parent.stdin.close()
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline and not pidfile.is_file():
            if parent.poll() is not None:
                raise RuntimeError("remote parent exited before fake child start")
            time.sleep(0.05)
        if not pidfile.is_file():
            raise RuntimeError("fake child did not start")
        child_pid = int(pidfile.read_text())
        if not owned_fake_group(child_pid, stub, root):
            raise RuntimeError("synthetic child ownership not verified")
        print("FAKE_NATIVE_CHILD_STARTED=PASS", flush=True)
        os.kill(parent.pid, signal.SIGKILL)
        parent.wait(timeout=5)
        time.sleep(0.5)
        orphan = living(child_pid)
        print("REMOTE_PARENT_LOSS_SIMULATED=PASS", flush=True)
        print("ORPHAN_CHILD_SURVIVED=" + ("YES" if orphan else "NO"), flush=True)
        print("REMOTE_DISCONNECT_HARD_STOP=" + ("NOT_VERIFIED" if orphan else "PASS"), flush=True)
        print("REAL_MODEL_CALLS=0", flush=True)
        print("PRODUCTION_WRITES=0", flush=True)
        return 0
    except Exception as error:
        print("SYNTHETIC_CHECK=FAILED", flush=True)
        print("ERROR_TYPE=" + type(error).__name__, flush=True)
        return 1
    finally:
        if parent is not None and parent.poll() is None:
            parent.kill()
            parent.wait(timeout=5)
        if child_pid is not None and living(child_pid):
            if owned_fake_group(child_pid, stub, root):
                os.killpg(child_pid, signal.SIGKILL)
                for _ in range(20):
                    if not living(child_pid):
                        break
                    time.sleep(0.05)
                print("SYNTHETIC_CHILD_CLEANUP=" +
                      ("PASS" if not living(child_pid) else "NOT_VERIFIED"),
                      flush=True)
            else:
                print("SYNTHETIC_CHILD_CLEANUP=BLOCKED_IDENTITY", flush=True)
        if child_pid is None or not living(child_pid):
            shutil.rmtree(root)


if __name__ == "__main__":
    raise SystemExit(main())
