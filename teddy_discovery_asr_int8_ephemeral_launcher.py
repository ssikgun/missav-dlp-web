"""Opt-in, localhost-only Stage11 int8 ASR worker; never autostarts.

Candidate only. Live use requires separate approval and explicitly selected
start/runtime VRAM floors and time limit. No downloads or local LLM control.
"""

from __future__ import annotations

import argparse
from http.client import HTTPException
import json
import multiprocessing
from pathlib import Path
import re
import signal
import subprocess
import time
import urllib.request


MODEL_REPOSITORY = "models--Systran--faster-whisper-large-v3"
WHISPER_PORT = 8091
MAX_RUNTIME_SECONDS = 900
MONITOR_INTERVAL_SECONDS = 2
STOP_GRACE_SECONDS = 5


class LaunchSafetyError(Exception):
    """Fail-closed launch gate with no private paths in messages."""


def verified_snapshot(cache_root: str, snapshot: str) -> Path:
    root = Path(cache_root)
    target = Path(snapshot)
    if not root.is_absolute() or not target.is_absolute() or root.is_symlink():
        raise LaunchSafetyError("UNSAFE_PATH")
    try:
        base = root.resolve(strict=True)
        model = target.resolve(strict=True)
        parts = model.relative_to(base).parts
        if (len(parts) != 3 or parts[0] != MODEL_REPOSITORY
                or parts[1] != "snapshots"
                or re.fullmatch(r"[0-9a-f]{40}", parts[2]) is None):
            raise LaunchSafetyError("UNEXPECTED_MODEL_IDENTITY")
        for name in ("model.bin", "config.json"):
            file = (model / name).resolve(strict=True)
            if not file.is_file() or not file.is_relative_to(base) or file.stat().st_size == 0:
                raise LaunchSafetyError("MODEL_FILES_INVALID")
    except (OSError, ValueError) as exc:
        raise LaunchSafetyError("MODEL_PATH_NOT_VERIFIED") from exc
    return model


def checked_local_llm_identity() -> str:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8082/v1/models", timeout=5) as response:
            models = json.load(response)["data"]
        if not isinstance(models, list) or len(models) != 1 or not isinstance(models[0], dict):
            raise ValueError("expected exactly one model")
        model_id = models[0].get("id")
        if (not isinstance(model_id, str) or not model_id.strip()
                or model_id != model_id.strip() or not model_id.isprintable()):
            raise ValueError("invalid model ID")
        return model_id
    except (OSError, HTTPException, ValueError, KeyError, TypeError) as exc:
        raise LaunchSafetyError("LOCAL_LLM_API_UNVERIFIED") from exc


def checked_free_vram(required_mib: int) -> int:
    if type(required_mib) is not int or required_mib <= 0:
        raise LaunchSafetyError("VRAM_FLOOR_NOT_SELECTED")
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            check=True, capture_output=True, text=True, timeout=5,
        )
        lines = result.stdout.strip().splitlines()
        if len(lines) != 1:
            raise LaunchSafetyError("GPU_COUNT_UNEXPECTED")
        free_mib = int(lines[0].strip())
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise LaunchSafetyError("GPU_STATUS_UNVERIFIED") from exc
    if free_mib < required_mib:
        raise LaunchSafetyError("GPU_HEADROOM_INSUFFICIENT")
    return free_mib


def run_server(server) -> None:
    """Allow SIGINT/SIGTERM to close only this temporary server."""
    stopping = False

    def request_stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    previous_int = signal.signal(signal.SIGINT, request_stop)
    previous_term = signal.signal(signal.SIGTERM, request_stop)
    try:
        server.timeout = 1.0
        try:
            while not stopping:
                server.handle_request()
        finally:
            server.server_close()
    finally:
        signal.signal(signal.SIGINT, previous_int)
        signal.signal(signal.SIGTERM, previous_term)


def _serve_child(model_path: str) -> None:
    """Private child only. Parent owns local LLM/VRAM monitoring and termination."""
    from teddy_discovery_asr import REMOTE_GPU_LARGE_V3_INT8_FLOAT16_RUNTIME_IDENTITY
    from teddy_discovery_asr_gpu_worker import (
        FasterWhisperGPUWorker, Stage11ASRHTTPServer,
    )

    worker = FasterWhisperGPUWorker(
        runtime_identity=REMOTE_GPU_LARGE_V3_INT8_FLOAT16_RUNTIME_IDENTITY,
        model_path=model_path,
    )
    server = Stage11ASRHTTPServer(("127.0.0.1", WHISPER_PORT), worker)
    print("WORKER=LISTENING_LOOPBACK INT8_FLOAT16=OPT_IN", flush=True)
    run_server(server)
    print("WORKER=STOPPED", flush=True)


def _stop_owned_child(child) -> None:
    """Never signal any process other than the exact child we started."""
    if child.pid is None:
        return
    if child.is_alive():
        child.terminate()
    child.join(timeout=STOP_GRACE_SECONDS)
    if child.is_alive():
        child.kill()
        child.join(timeout=STOP_GRACE_SECONDS)
    if child.is_alive():
        raise LaunchSafetyError("WORKER_STOP_UNVERIFIED")


def supervise_worker(model_path: str, *, runtime_min_free_vram_mib: int,
                     max_runtime_seconds: int, initial_model_id: str) -> None:
    """Monitor local LLM/VRAM/time while ASR runs in its own stoppable process."""
    context = multiprocessing.get_context("spawn")
    child = context.Process(target=_serve_child, args=(model_path,), daemon=True)

    def request_stop(_signum, _frame):
        raise LaunchSafetyError("OPERATOR_STOP")

    previous_int = signal.signal(signal.SIGINT, request_stop)
    previous_term = signal.signal(signal.SIGTERM, request_stop)
    try:
        try:
            child.start()
        except (OSError, RuntimeError) as exc:
            raise LaunchSafetyError("WORKER_START_FAILED") from exc
        started_at = time.monotonic()
        while True:
            if not child.is_alive():
                raise LaunchSafetyError("WORKER_EXITED")
            if time.monotonic() - started_at >= max_runtime_seconds:
                raise LaunchSafetyError("RUNTIME_LIMIT")
            if checked_local_llm_identity() != initial_model_id:
                raise LaunchSafetyError("LOCAL_LLM_MODEL_CHANGED")
            try:
                checked_free_vram(runtime_min_free_vram_mib)
            except LaunchSafetyError as exc:
                raise LaunchSafetyError("GPU_HEADROOM_LOST") from exc
            time.sleep(MONITOR_INTERVAL_SECONDS)
    finally:
        try:
            _stop_owned_child(child)
        finally:
            signal.signal(signal.SIGINT, previous_int)
            signal.signal(signal.SIGTERM, previous_term)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage11 isolated int8 worker candidate")
    parser.add_argument("mode", choices=("check", "serve"))
    parser.add_argument("--cache-root", required=True)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--min-free-vram-mib", type=int, required=True)
    parser.add_argument("--runtime-min-free-vram-mib", type=int)
    parser.add_argument("--max-runtime-seconds", type=int)
    parser.add_argument("--live-approved", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.mode == "serve":
            if not args.live_approved:
                raise LaunchSafetyError("LIVE_NOT_APPROVED")
            if (args.runtime_min_free_vram_mib is None
                    or args.runtime_min_free_vram_mib <= 0):
                raise LaunchSafetyError("RUNTIME_VRAM_FLOOR_NOT_SELECTED")
            if (args.max_runtime_seconds is None
                    or not 1 <= args.max_runtime_seconds <= MAX_RUNTIME_SECONDS):
                raise LaunchSafetyError("RUNTIME_LIMIT_NOT_SELECTED")
        model = verified_snapshot(args.cache_root, args.snapshot)
        initial_model_id = checked_local_llm_identity()
        free_mib = checked_free_vram(args.min_free_vram_mib)
        if args.mode == "check":
            print(f"CHECK=PASS FREE_VRAM_MIB={free_mib}")
            print("LOCAL_LLM_MODEL_ID=" + json.dumps(initial_model_id))
            print("MODEL_LOADS=0 SERVICE_CHANGES=0")
            return 0

        supervise_worker(
            str(model),
            runtime_min_free_vram_mib=args.runtime_min_free_vram_mib,
            max_runtime_seconds=args.max_runtime_seconds,
            initial_model_id=initial_model_id,
        )
        return 0
    except (LaunchSafetyError, OSError) as exc:
        reason = str(exc) if isinstance(exc, LaunchSafetyError) else "WORKER_UNAVAILABLE"
        print(f"RESULT=SAFE_STOP_{reason}", flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
