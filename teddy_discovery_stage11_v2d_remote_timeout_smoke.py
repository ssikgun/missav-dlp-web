#!/usr/bin/env python3
"""No-model timeout check for V2-D-only REMOTE_NATIVE guard.

Shortens the guarded inactivity threshold IN MEMORY to one second. Does not
modify repository source, run Hermes, open SSH, or touch production resources.
"""
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

from teddy_discovery_stage11_v2d_remote_disconnect_smoke import (
    native_from_source,
    living,
    owned_fake_group,
)

def main():
    if len(sys.argv) != 2:
        print("USAGE: timeout-smoke.py /path/to/teddy_discovery_stage11_normal_mode.py")
        return 2
    path = Path(sys.argv[1])
    if not path.is_file() or path.is_symlink():
        print("SOURCE=NOT_VERIFIED")
        return 2
    raw, source_sha = native_from_source(path)
    needle = "if now-started>=3600 or now-last>=600:"
    if raw.count(needle) != 2 or "if v2d_guard:" not in raw:
        print("ISOLATED_TIMEOUT_ADAPTATION=BLOCKED")
        return 2
    # First occurrence is guarded V2-D, second is untouched legacy Normal.
    code = raw.replace(needle, "if now-started>=3 or now-last>=1:", 1)
    compile(code, "SYNTHETIC_NATIVE_TIMEOUT", "exec")
    print("SOURCE_SHA256=" + source_sha, flush=True)
    print("SYNTHETIC_INACTIVITY_SECONDS=1", flush=True)
    root = Path(tempfile.mkdtemp(prefix="s11-v2d-timeout-"))
    stub = root / "fake-hermes"
    parent = None
    child = None
    descendant = None
    try:
        profile = root / "synthetic" / "profiles" / "subtitle-translator"
        profile.mkdir(parents=True)
        (profile / "auth.json").write_text('{"fake":true}')
        stub.write_text("""#!/usr/bin/env python3
import json, os, pathlib, subprocess, sys, time
if 'prompt-size' in sys.argv:
    print(json.dumps({'tools': {'count': 0}}))
else:
    descendant=subprocess.Popen([sys.executable, '-B', '-c', 'import time;time.sleep(120)'])
    root=pathlib.Path(os.environ['HERMES_HOME'])
    (root/'fake-descendant-pid').write_text(str(descendant.pid))
    (root/'fake-child-pid').write_text(str(os.getpid()))
    time.sleep(120)
""")
        stub.chmod(0o700)
        prompt = b"NO-MODEL-TIMEOUT-FIXTURE"
        request = {
            "root": str(root / "remote"), "source_profile": str(profile),
            "config": base64.b64encode(b"{}").decode(),
            "prompt": base64.b64encode(prompt).decode(),
            "prompt_sha256": hashlib.sha256(prompt).hexdigest(),
            "executable": str(stub), "v2d_guard": True,
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
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, start_new_session=True,
        )
        parent.stdin.write(json.dumps(request).encode("ascii"))
        parent.stdin.close()
        parent.stdin = None
        out, err = parent.communicate(timeout=12)
        pidpath = root / "remote" / "fake-child-pid"
        descendant_path = root / "remote" / "fake-descendant-pid"
        if not pidpath.is_file() or not descendant_path.is_file():
            raise RuntimeError("synthetic child or descendant did not launch")
        child, descendant = int(pidpath.read_text()), int(descendant_path.read_text())
        if parent.returncode != 0:
            raise RuntimeError("synthetic remote transport exited nonzero")
        try:
            receipt = json.loads(out.decode("ascii"))
        except (ValueError, UnicodeError):
            raise RuntimeError("synthetic timeout receipt is invalid")
        print("INACTIVITY_REASON=" + str(receipt.get("timeout_reason")), flush=True)
        print("CHILD_RETURN_CODE=" + str(receipt.get("returncode")), flush=True)
        print("CHILD_ALIVE=" + str(living(child)), flush=True)
        print("DESCENDANT_ALIVE=" + str(living(descendant)), flush=True)
        passed = (
            receipt.get("timeout_reason") == "INACTIVITY_TIMEOUT"
            and type(receipt.get("returncode")) is int
            and receipt.get("returncode") != 0
            and receipt.get("tools_count") == 0
            and not living(child)
            and not living(descendant)
        )
        print("SYNTHETIC_TIMEOUT_CLEANUP=" + ("PASS" if passed else "NOT_VERIFIED"), flush=True)
        print("REAL_MODEL_CALLS=0", flush=True)
        print("PRODUCTION_WRITES=0", flush=True)
        return 0 if passed else 1
    except Exception as error:
        print("SYNTHETIC_TIMEOUT_CLEANUP=NOT_VERIFIED", flush=True)
        print("ERROR_TYPE=" + type(error).__name__, flush=True)
        return 1
    finally:
        if parent is not None and parent.poll() is None:
            parent.kill()
            parent.wait(timeout=5)
        if child is not None and living(child) and owned_fake_group(child, stub, root):
            os.killpg(child, signal.SIGKILL)
        if descendant is not None and living(descendant):
            try:
                proc = Path("/proc") / str(descendant)
                uid = next(x for x in (proc / "status").read_text().splitlines()
                           if x.startswith("Uid:"))
                cmdline = (proc / "cmdline").read_bytes()
                if (child is not None and os.getpgid(descendant) == child
                        and int(uid.split()[1]) == os.geteuid()
                        and b"time.sleep(120)" in cmdline):
                    os.kill(descendant, signal.SIGKILL)
            except (FileNotFoundError, ProcessLookupError, OSError, StopIteration):
                pass
        if (child is None or not living(child)) and (descendant is None or not living(descendant)):
            shutil.rmtree(root)

if __name__ == "__main__":
    raise SystemExit(main())
