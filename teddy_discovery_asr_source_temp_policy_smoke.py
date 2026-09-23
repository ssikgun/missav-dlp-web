"""Tiny-file smoke tests for disk-backed ASR media temp policy and cleanup."""

from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from teddy_discovery_asr import ASRValidationError
from teddy_discovery_asr_source import ASRSourceError
from teddy_discovery_asr_source_smoke import (
    FakeProcess,
    make_reader,
    stat_json,
    video,
)


class RaisingRead:
    def __init__(self, error):
        self.error = error
        self.calls = 0
        self.closed = False

    def read(self, _size=-1):
        self.calls += 1
        if self.calls == 1:
            return b"partial"
        raise self.error

    def close(self):
        self.closed = True


def require(value: bool, marker: str):
    if not value:
        raise AssertionError(marker)


def expect(error_type, callback, marker: str):
    try:
        callback()
    except error_type:
        return
    raise AssertionError(marker)


def temp_dirs(root: Path):
    return tuple(root.glob(".teddy-stage11-asr-*"))


def _stat_pair(size: int, mtime_ns: int = 7):
    item = (0, stat_json(size, mtime_ns))
    return (item, item)


def main():
    with TemporaryDirectory(prefix="asr-prod-temp-smoke-", dir="/var/tmp") as raw:
        base = Path(raw)
        root = base / "production-media"

        # Root creation, private permission validation, and a successful tiny copy.
        reader, _ = make_reader(
            str(root),
            payload=b"tiny-media",
            stat_items=_stat_pair(10),
            require_disk_backed=True,
            reserve_bytes=64,
        )
        with patch(
            "teddy_discovery_asr_source.shutil.disk_usage",
            return_value=SimpleNamespace(free=74, total=1000, used=926),
        ):
            with reader.copy_to_temp(video(), max_media_bytes=10) as source:
                request_dir = Path(source.local_path).parent
                require(request_dir.parent == root, "PRIVATE_REQUEST_DIR_PARENT")
                require(Path(source.local_path).read_bytes() == b"tiny-media",
                        "TINY_COPY_CONTENT")
                require(request_dir.name.startswith(".teddy-stage11-asr-"),
                        "REQUEST_DIR_BASENAME")
        require(root.is_dir() and root.stat().st_mode & 0o077 == 0,
                "PRODUCTION_ROOT_CREATED_PRIVATE")
        require(not temp_dirs(root), "SUCCESS_CLEANUP")

        # Another request-owned directory and its contents must survive cleanup.
        sibling = root / ".teddy-stage11-asr-other-request"
        sibling.mkdir()
        marker = sibling / "keep"
        marker.write_bytes(b"other")
        seq_reader, _ = make_reader(
            str(root),
            payload=b"next",
            stat_items=_stat_pair(4) + _stat_pair(4),
            require_disk_backed=True,
        )
        with patch(
            "teddy_discovery_asr_source.shutil.disk_usage",
            return_value=SimpleNamespace(free=1000, total=2000, used=1000),
        ):
            with seq_reader.copy_to_temp(video(), max_media_bytes=4):
                require(len(temp_dirs(root)) == 2,
                        "SIMULATED_BASELINE_SOURCE_ACTIVE")
            require(len(temp_dirs(root)) == 1 and marker.read_bytes() == b"other",
                    "BASELINE_SOURCE_CLEANED_SIBLING_PRESERVED")
            with seq_reader.copy_to_temp(video(), max_media_bytes=4):
                require(len(temp_dirs(root)) == 2,
                        "SIMULATED_TARGETED_SOURCE_ACTIVE_AFTER_BASELINE")
            require(len(temp_dirs(root)) == 1 and marker.read_bytes() == b"other",
                    "TARGETED_SOURCE_CLEANED_SIBLING_PRESERVED")
        sibling.joinpath("keep").unlink()
        sibling.rmdir()

        # Unavailable and unwritable roots fail before any remote copy starts.
        unavailable = base / "not-a-directory"
        unavailable.write_text("file", encoding="utf-8")
        unavailable_reader, unavailable_record = make_reader(
            str(unavailable / "child"), require_disk_backed=True,
        )
        expect(
            ASRSourceError,
            lambda: unavailable_reader.copy_to_temp(video(), max_media_bytes=1),
            "UNAVAILABLE_ROOT_FAIL_CLOSED",
        )
        require("popen_command" not in unavailable_record,
                "UNAVAILABLE_ROOT_NO_MEDIA_COPY")

        unwritable = base / "unwritable"
        unwritable.mkdir(mode=0o500)
        unwritable.chmod(0o500)
        unwritable_reader, unwritable_record = make_reader(
            str(unwritable), require_disk_backed=True,
        )
        expect(
            ASRSourceError,
            lambda: unwritable_reader.copy_to_temp(video(), max_media_bytes=1),
            "UNWRITABLE_ROOT_FAIL_CLOSED",
        )
        require("popen_command" not in unwritable_record,
                "UNWRITABLE_ROOT_NO_MEDIA_COPY")
        unwritable.chmod(0o700)

        # Space preflight is source_size + reserve and runs before stream creation.
        insufficient, insufficient_record = make_reader(
            str(root),
            payload=b"12345",
            stat_items=_stat_pair(5),
            require_disk_backed=True,
            reserve_bytes=50,
        )
        with patch(
            "teddy_discovery_asr_source.shutil.disk_usage",
            return_value=SimpleNamespace(free=54, total=1000, used=946),
        ):
            expect(
                ASRSourceError,
                lambda: insufficient.copy_to_temp(video(), max_media_bytes=5),
                "INSUFFICIENT_SPACE_FAIL_CLOSED",
            )
        require("popen_command" not in insufficient_record and not temp_dirs(root),
                "SPACE_PREFLIGHT_BEFORE_STREAM")
        enough, _ = make_reader(
            str(root),
            payload=b"12345",
            stat_items=_stat_pair(5),
            require_disk_backed=True,
            reserve_bytes=50,
        )
        with patch(
            "teddy_discovery_asr_source.shutil.disk_usage",
            return_value=SimpleNamespace(free=55, total=1000, used=945),
        ):
            with enough.copy_to_temp(video(), max_media_bytes=5):
                require(len(temp_dirs(root)) == 1, "SPACE_PREFLIGHT_PASS")
        require(not temp_dirs(root), "SPACE_PASS_CLEANUP")

        # Both Exception and BaseException during a partial stream remove only
        # this request directory and preserve the original exception object.
        for error, marker in (
            (RuntimeError("synthetic copy exception"), "PARTIAL_EXCEPTION_CLEANUP"),
            (KeyboardInterrupt("synthetic copy interrupt"), "PARTIAL_INTERRUPT_CLEANUP"),
            (SystemExit("synthetic copy exit"), "PARTIAL_SYSTEMEXIT_CLEANUP"),
        ):
            process_box = {}

            def process_factory(payload, returncode, error=error):
                process = FakeProcess(payload=payload, returncode=returncode)
                process.stdout = RaisingRead(error)
                process_box["process"] = process
                return process

            reader, _ = make_reader(
                str(root),
                payload=b"payload",
                stat_items=_stat_pair(7),
                require_disk_backed=True,
                process_factory=process_factory,
            )
            caught = None
            try:
                with patch(
                    "teddy_discovery_asr_source.shutil.disk_usage",
                    return_value=SimpleNamespace(free=1000, total=2000, used=1000),
                ):
                    reader.copy_to_temp(video(), max_media_bytes=7)
            except BaseException as observed:
                caught = observed
            require(caught is error, marker + "_ORIGINAL_EXCEPTION_PRESERVED")
            require(process_box["process"].terminated,
                    marker + "_CHILD_ABORTED")
            require(not temp_dirs(root), marker + "_NO_PARTIAL_DIR")

        # Production mode cannot fall back to the default tempfile directory.
        tmp_reader, tmp_record = make_reader("/tmp", require_disk_backed=True)
        expect(
            ASRSourceError,
            lambda: tmp_reader.copy_to_temp(video(), max_media_bytes=1),
            "PRODUCTION_TMP_ROOT_REJECTED",
        )
        require("popen_command" not in tmp_record,
                "PRODUCTION_TMP_ROOT_NO_REMOTE_COPY")
        expect(
            ASRValidationError,
            lambda: make_reader(None, require_disk_backed=True),
            "PRODUCTION_TEMP_ROOT_REQUIRED",
        )

    print("ASR_MEDIA_TEMP_POLICY_SMOKE=PASS")
    print("ROOT_SPACE_CLEANUP_AND_SERIAL_LIFECYCLE=PASS")
    print("PARTIAL_EXCEPTION_AND_INTERRUPT_CLEANUP=PASS")


if __name__ == "__main__":
    main()
