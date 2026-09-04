"""Offline fake-process smoke tests for the Stage11 ASR media source."""

from __future__ import annotations

from io import BytesIO
import ast
import inspect
import json
from pathlib import Path
import subprocess
import tempfile

from teddy_discovery_asr import ASRLimitError, ASRValidationError
from teddy_discovery_asr_source import (
    ASRMediaSourceReader,
    ASRSourceError,
    MEDIA_TRANSFER_CHUNK_BYTES,
    PROCESS_CLEANUP_TIMEOUT_SECONDS,
    REMOTE_STAT_SCRIPT,
    REMOTE_STREAM_SCRIPT,
    _abort_process,
)
from teddy_discovery_subtitle import (
    CanonicalVideoHolding,
    validate_canonical_holding,
)


def expect(error_type, function):
    try:
        function()
    except error_type:
        return
    raise AssertionError("expected " + error_type.__name__)


def video() -> CanonicalVideoHolding:
    return validate_canonical_holding(
        {
            "dvd_id": "JUR-750",
            "storage_root": "jav",
            "relative_path": "JUR/JUR-750/JUR-750.mp4",
            "parse_status": "MATCHED",
            "present": 1,
        },
        "JUR-750",
    )


def make_reader(
    temp_root: str,
    *,
    payload: bytes = b"",
    stat_items=(),
    returncode: int = 0,
    record: dict | None = None,
):
    record = {} if record is None else record
    responses = list(stat_items)

    def runner(command, **kwargs):
        record.setdefault("runner_calls", []).append((command, kwargs))
        if not responses:
            raise AssertionError("unexpected stat call")
        item = responses.pop(0)
        return FakeCompleted(
            returncode=item[0],
            stdout=item[1],
        )

    def popen_factory(command, **kwargs):
        record["popen_command"] = command
        record["popen_kwargs"] = kwargs
        process = FakeProcess(payload=payload, returncode=returncode)
        record["process"] = process
        return process

    return ASRMediaSourceReader(
        host="nas.example",
        user="fake-user",
        key="/keys/fake-stage11",
        known_hosts="/keys/known_hosts",
        library_root="/srv/JAV",
        runner=runner,
        popen_factory=popen_factory,
        temp_root=temp_root,
    ), record


class FakeCompleted:
    def __init__(self, *, returncode, stdout):
        self.returncode = returncode
        self.stdout = stdout


class CapturingStdin:
    def __init__(self):
        self.payload = bytearray()
        self.closed = False

    def write(self, payload):
        self.payload.extend(payload)
        return len(payload)

    def close(self):
        self.closed = True


class FakeProcess:
    def __init__(self, *, payload: bytes, returncode: int):
        self.stdin = CapturingStdin()
        self.stdout = RecordingBytesIO(payload)
        self.stderr = BytesIO()
        self.returncode = returncode
        self.terminated = False
        self.killed = False

    def wait(self, timeout=None):
        self.wait_timeout = timeout
        return self.returncode

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


class AbortProcess:
    def __init__(
        self,
        *,
        poll_value=None,
        terminate_error=None,
        kill_error=None,
        wait_results=(),
    ):
        self.poll_value = poll_value
        self.terminate_error = terminate_error
        self.kill_error = kill_error
        self.wait_results = list(wait_results)
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_timeouts = []

    def poll(self):
        return self.poll_value

    def terminate(self):
        self.terminate_calls += 1
        if self.terminate_error is not None:
            raise self.terminate_error

    def kill(self):
        self.kill_calls += 1
        if self.kill_error is not None:
            raise self.kill_error

    def wait(self, timeout=None):
        self.wait_timeouts.append(timeout)
        if self.wait_results:
            result = self.wait_results.pop(0)
            if isinstance(result, BaseException):
                raise result
            return result
        return 0


class RecordingBytesIO(BytesIO):
    def __init__(self, payload):
        super().__init__(payload)
        self.read_sizes = []

    def read(self, size=-1):
        self.read_sizes.append(size)
        return super().read(size)


def stat_json(size: int, mtime_ns: int) -> str:
    return json.dumps({"size": size, "mtime_ns": mtime_ns})


def successful_reader(temp_root: str, *, payload: bytes, size=None, mtime_ns=7):
    expected_size = len(payload) if size is None else size
    return make_reader(
        temp_root,
        payload=payload,
        stat_items=(
            (0, stat_json(expected_size, mtime_ns)),
            (0, stat_json(expected_size, mtime_ns)),
        ),
    )


def assert_hardened(command):
    assert command[0] == "ssh"
    assert command[1:3] == ["-i", "/keys/fake-stage11"]
    assert "IdentitiesOnly=yes" in command
    assert "BatchMode=yes" in command
    assert "ConnectTimeout=10" in command
    assert "StrictHostKeyChecking=yes" in command
    assert "UserKnownHostsFile=/keys/known_hosts" in command
    assert command[-2] == "fake-user@nas.example"
    assert command[-1].startswith("python3 -")


def main():
    already_exited = AbortProcess(poll_value=0, wait_results=(0,))
    _abort_process(already_exited)
    assert already_exited.terminate_calls == 0
    assert already_exited.kill_calls == 0
    assert already_exited.wait_timeouts == [PROCESS_CLEANUP_TIMEOUT_SECONDS]

    terminate_os_error = AbortProcess(
        terminate_error=OSError("synthetic terminate failure"),
        wait_results=(0,),
    )
    _abort_process(terminate_os_error)
    assert terminate_os_error.terminate_calls == 1
    assert terminate_os_error.kill_calls == 0
    assert terminate_os_error.wait_timeouts == [PROCESS_CLEANUP_TIMEOUT_SECONDS]

    terminate_subprocess_error = AbortProcess(
        terminate_error=subprocess.SubprocessError("synthetic terminate failure"),
        wait_results=(0,),
    )
    _abort_process(terminate_subprocess_error)
    assert terminate_subprocess_error.terminate_calls == 1
    assert terminate_subprocess_error.kill_calls == 0
    assert terminate_subprocess_error.wait_timeouts == [PROCESS_CLEANUP_TIMEOUT_SECONDS]

    terminate_success = AbortProcess(wait_results=(0,))
    _abort_process(terminate_success)
    assert terminate_success.terminate_calls == 1
    assert terminate_success.kill_calls == 0
    assert terminate_success.wait_timeouts == [PROCESS_CLEANUP_TIMEOUT_SECONDS]

    terminate_timeout = AbortProcess(
        wait_results=(
            subprocess.TimeoutExpired(cmd="fake", timeout=1),
            0,
        ),
    )
    _abort_process(terminate_timeout)
    assert terminate_timeout.terminate_calls == 1
    assert terminate_timeout.kill_calls == 1
    assert terminate_timeout.wait_timeouts == [
        PROCESS_CLEANUP_TIMEOUT_SECONDS,
        PROCESS_CLEANUP_TIMEOUT_SECONDS,
    ]

    cleanup_failures = AbortProcess(
        terminate_error=OSError("terminate failed"),
        kill_error=subprocess.SubprocessError("kill failed"),
        wait_results=(
            subprocess.TimeoutExpired(cmd="fake", timeout=1),
            OSError("wait failed"),
        ),
    )
    original_transfer_error = ASRSourceError("original transfer failure")
    try:
        raise original_transfer_error
    except ASRSourceError as observed:
        _abort_process(cleanup_failures)
        assert observed is original_transfer_error
    assert cleanup_failures.terminate_calls == 1
    assert cleanup_failures.kill_calls == 1
    assert cleanup_failures.wait_timeouts == [
        PROCESS_CLEANUP_TIMEOUT_SECONDS,
        PROCESS_CLEANUP_TIMEOUT_SECONDS,
    ]

    source_text = Path(__file__).with_name(
        "teddy_discovery_asr_source.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source_text)
    abort_function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_abort_process"
    )
    for call in ast.walk(abort_function):
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute):
            if call.func.attr == "wait":
                assert any(
                    keyword.arg == "timeout"
                    for keyword in call.keywords
                )

    with tempfile.TemporaryDirectory() as temp_root:
        payload = b"M" * (MEDIA_TRANSFER_CHUNK_BYTES + 123)
        reader, record = successful_reader(temp_root, payload=payload)
        assert inspect.signature(reader.copy_to_temp).parameters["max_media_bytes"].default is inspect.Parameter.empty

        with reader.copy_to_temp(video(), max_media_bytes=len(payload)) as source:
            assert Path(source.local_path).is_file()
            assert Path(source.local_path).read_bytes() == payload
            assert source.snapshot.dvd_id == "JUR-750"
            assert source.snapshot.source_size == len(payload)

        assert not list(Path(temp_root).iterdir())
        assert_hardened(record["runner_calls"][0][0])
        assert record["runner_calls"][0][1]["shell"] is False
        assert record["runner_calls"][0][1]["text"] is True
        assert record["popen_kwargs"]["shell"] is False
        assert record["popen_kwargs"]["text"] is False
        assert record["popen_kwargs"]["stdout"] is not None
        assert record["process"].stdin.closed
        assert all(
            size <= MEDIA_TRANSFER_CHUNK_BYTES
            for size in record["process"].stdout.read_sizes
        )
        assert len(record["runner_calls"]) == 2

        command_text = record["popen_command"][-1]
        assert "JUR/JUR-750/JUR-750.mp4" in command_text
        assert "os.walk" not in REMOTE_STAT_SCRIPT + REMOTE_STREAM_SCRIPT
        assert "rglob" not in REMOTE_STAT_SCRIPT + REMOTE_STREAM_SCRIPT
        assert "glob(" not in REMOTE_STAT_SCRIPT + REMOTE_STREAM_SCRIPT
        assert "os.scandir" not in REMOTE_STAT_SCRIPT + REMOTE_STREAM_SCRIPT
        assert "os.path.islink" in REMOTE_STAT_SCRIPT
        assert 'open(candidate, "rb")' in REMOTE_STREAM_SCRIPT
        assert 'open(candidate, "wb")' not in REMOTE_STAT_SCRIPT + REMOTE_STREAM_SCRIPT
        assert "os.unlink" not in REMOTE_STAT_SCRIPT + REMOTE_STREAM_SCRIPT
        assert "retry" not in (REMOTE_STAT_SCRIPT + REMOTE_STREAM_SCRIPT).lower()

        expect(
            ASRValidationError,
            lambda: reader.copy_to_temp(
                "JUR/JUR-750/JUR-750.mp4",
                max_media_bytes=100,
            ),
        )
        expect(
            ASRValidationError,
            lambda: reader.copy_to_temp(
                CanonicalVideoHolding(
                    dvd_id="JUR-750",
                    relative_path="JUR/JUR-750/JUR-750.mkv",
                    video_format="mkv",
                ),
                max_media_bytes=100,
            ),
        )

        for invalid_limit in (0, -1, True, False):
            expect(
                ASRValidationError,
                lambda invalid_limit=invalid_limit: reader.copy_to_temp(
                    video(),
                    max_media_bytes=invalid_limit,
                ),
            )

        for status in (3, 5):
            failing_reader, failing_record = make_reader(
                temp_root,
                stat_items=((status, ""),),
            )
            expect(
                ASRSourceError,
                lambda failing_reader=failing_reader: failing_reader.copy_to_temp(
                    video(),
                    max_media_bytes=100,
                ),
            )
            assert not list(Path(temp_root).iterdir())
            assert "popen_command" not in failing_record

        zero_reader, _ = make_reader(
            temp_root,
            stat_items=((0, stat_json(0, 1)),),
        )
        expect(
            ASRSourceError,
            lambda: zero_reader.copy_to_temp(video(), max_media_bytes=100),
        )

        large_reader, _ = make_reader(
            temp_root,
            stat_items=((0, stat_json(101, 1)),),
        )
        expect(
            ASRLimitError,
            lambda: large_reader.copy_to_temp(video(), max_media_bytes=100),
        )

        short_reader, _ = make_reader(
            temp_root,
            payload=b"short",
            stat_items=(
                (0, stat_json(10, 1)),
                (0, stat_json(10, 1)),
            ),
        )
        expect(
            ASRSourceError,
            lambda: short_reader.copy_to_temp(video(), max_media_bytes=100),
        )
        assert not list(Path(temp_root).iterdir())

        oversized_reader, oversized_record = make_reader(
            temp_root,
            payload=b"01234567890",
            stat_items=((0, stat_json(10, 1)),),
        )
        expect(
            ASRSourceError,
            lambda: oversized_reader.copy_to_temp(video(), max_media_bytes=100),
        )
        assert oversized_record["process"].terminated
        assert not list(Path(temp_root).iterdir())

        rc_reader, rc_record = make_reader(
            temp_root,
            payload=b"0123456789",
            returncode=9,
            stat_items=((0, stat_json(10, 1)), (0, stat_json(10, 1))),
        )
        expect(
            ASRSourceError,
            lambda: rc_reader.copy_to_temp(video(), max_media_bytes=100),
        )
        assert rc_record["process"].terminated
        assert not list(Path(temp_root).iterdir())

        unstable_size, _ = make_reader(
            temp_root,
            payload=b"0123456789",
            stat_items=((0, stat_json(10, 1)), (0, stat_json(11, 1))),
        )
        expect(
            ASRSourceError,
            lambda: unstable_size.copy_to_temp(video(), max_media_bytes=100),
        )
        assert not list(Path(temp_root).iterdir())

        unstable_mtime, _ = make_reader(
            temp_root,
            payload=b"0123456789",
            stat_items=((0, stat_json(10, 1)), (0, stat_json(10, 2))),
        )
        expect(
            ASRSourceError,
            lambda: unstable_mtime.copy_to_temp(video(), max_media_bytes=100),
        )
        assert not list(Path(temp_root).iterdir())

        source_reader, _ = successful_reader(temp_root, payload=b"abc")
        with source_reader.copy_to_temp(video(), max_media_bytes=3) as source:
            assert Path(source.local_path).exists()
            try:
                source.local_path = "/tmp/redirected.mp4"
            except AttributeError:
                pass
            else:
                raise AssertionError("source local_path must be read-only")
        assert not list(Path(temp_root).iterdir())

    print("STAGE11_ASR_SOURCE_SMOKE=PASS")


if __name__ == "__main__":
    main()
