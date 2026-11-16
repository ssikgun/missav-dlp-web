"""Opt-in, localhost-only Stage11 int8 ASR worker; never autostarts.

Candidate only. Live use requires separate user authorization and an explicitly
chosen free-VRAM floor. No model downloads, Qwen control, or media operations.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import signal
import subprocess
import urllib.request


MODEL_REPOSITORY = "models--Systran--faster-whisper-large-v3"
EXPECTED_QWEN_ID = "qwen3.6-35b-a3b"
WHISPER_PORT = 8091


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


def checked_qwen_identity() -> None:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8082/v1/models", timeout=5) as response:
            models = json.load(response)["data"]
        if len(models) != 1 or models[0].get("id") != EXPECTED_QWEN_ID:
            raise LaunchSafetyError("QWEN_IDENTITY_MISMATCH")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise LaunchSafetyError("QWEN_API_UNVERIFIED") from exc


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage11 isolated int8 worker candidate")
    parser.add_argument("mode", choices=("check", "serve"))
    parser.add_argument("--cache-root", required=True)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--min-free-vram-mib", type=int, required=True)
    parser.add_argument("--live-approved", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.mode == "serve" and not args.live_approved:
            raise LaunchSafetyError("LIVE_NOT_APPROVED")
        model = verified_snapshot(args.cache_root, args.snapshot)
        checked_qwen_identity()
        free_mib = checked_free_vram(args.min_free_vram_mib)
        if args.mode == "check":
            print(f"CHECK=PASS FREE_VRAM_MIB={free_mib}")
            print("MODEL_LOADS=0 SERVICE_CHANGES=0")
            return 0

        # No import or CUDA initialization occurs in check mode. The actual
        # Whisper weights are still loaded lazily on the first ASR request.
        from teddy_discovery_asr import REMOTE_GPU_LARGE_V3_INT8_FLOAT16_RUNTIME_IDENTITY
        from teddy_discovery_asr_gpu_worker import (
            FasterWhisperGPUWorker, Stage11ASRHTTPServer,
        )

        worker = FasterWhisperGPUWorker(
            runtime_identity=REMOTE_GPU_LARGE_V3_INT8_FLOAT16_RUNTIME_IDENTITY,
            model_path=str(model),
        )
        server = Stage11ASRHTTPServer(("127.0.0.1", WHISPER_PORT), worker)
        print("WORKER=LISTENING_LOOPBACK INT8_FLOAT16=OPT_IN", flush=True)
        run_server(server)
        print("WORKER=STOPPED", flush=True)
        return 0
    except (LaunchSafetyError, OSError) as exc:
        reason = str(exc) if isinstance(exc, LaunchSafetyError) else "LISTENER_UNAVAILABLE"
        print(f"RESULT=SAFE_STOP_{reason}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
