"""Offline, no-model smoke for the opt-in Stage11 temporary launcher."""

from __future__ import annotations

from contextlib import redirect_stdout
import io
from pathlib import Path
import signal
import tempfile
from unittest.mock import patch

import teddy_discovery_asr_int8_ephemeral_launcher as launcher


def expect_safety(code, action):
    try:
        action()
    except launcher.LaunchSafetyError as exc:
        assert str(exc) == code, (code, str(exc))
    else:
        raise AssertionError("expected safe stop: " + code)


def main():
    with tempfile.TemporaryDirectory(prefix="stage11-int8-launcher-smoke-") as temp:
        root = Path(temp)
        snapshot = root / launcher.MODEL_REPOSITORY / "snapshots" / ("a" * 40)
        snapshot.mkdir(parents=True)
        (snapshot / "model.bin").write_bytes(b"fake model")
        (snapshot / "config.json").write_bytes(b"{}")
        assert launcher.verified_snapshot(str(root), str(snapshot)) == snapshot
        expect_safety("UNSAFE_PATH", lambda: launcher.verified_snapshot("relative", str(snapshot)))

        other = root / "other"
        other.mkdir()
        (other / "model.bin").write_bytes(b"fake model")
        (other / "config.json").write_bytes(b"{}")
        expect_safety("UNEXPECTED_MODEL_IDENTITY", lambda: launcher.verified_snapshot(str(root), str(other)))

        with patch.object(launcher, "checked_qwen_identity") as qwen, \
                patch.object(launcher, "checked_free_vram", return_value=4096) as gpu:
            output = io.StringIO()
            with redirect_stdout(output):
                assert launcher.main([
                    "check", "--cache-root", str(root), "--snapshot", str(snapshot),
                    "--min-free-vram-mib", "3000",
                ]) == 0
            assert "CHECK=PASS" in output.getvalue()
            qwen.assert_called_once_with()
            gpu.assert_called_once_with(3000)

        with patch.object(launcher, "checked_qwen_identity") as qwen:
            output = io.StringIO()
            with redirect_stdout(output):
                assert launcher.main([
                    "serve", "--cache-root", str(root), "--snapshot", str(snapshot),
                    "--min-free-vram-mib", "3000",
                ]) == 2
            assert "SAFE_STOP_LIVE_NOT_APPROVED" in output.getvalue()
            qwen.assert_not_called()

        with patch.object(launcher, "checked_qwen_identity") as qwen:
            output = io.StringIO()
            with redirect_stdout(output):
                assert launcher.main([
                    "serve", "--cache-root", str(root), "--snapshot", str(snapshot),
                    "--min-free-vram-mib", "3000", "--live-approved",
                ]) == 2
            assert "SAFE_STOP_RUNTIME_VRAM_FLOOR_NOT_SELECTED" in output.getvalue()
            qwen.assert_not_called()

        with patch.object(launcher, "checked_qwen_identity") as qwen:
            output = io.StringIO()
            with redirect_stdout(output):
                assert launcher.main([
                    "serve", "--cache-root", str(root), "--snapshot", str(snapshot),
                    "--min-free-vram-mib", "3000", "--live-approved",
                    "--runtime-min-free-vram-mib", "256",
                ]) == 2
            assert "SAFE_STOP_RUNTIME_LIMIT_NOT_SELECTED" in output.getvalue()
            qwen.assert_not_called()

        class FakeServer:
            def __init__(self):
                self.closed = False
                self.calls = 0
                self.timeout = None
            def handle_request(self):
                self.calls += 1
                handlers[signal.SIGTERM](signal.SIGTERM, None)
            def server_close(self):
                self.closed = True

        handlers = {}
        def fake_signal(sig, handler):
            old = handlers.get(sig, signal.SIG_DFL)
            handlers[sig] = handler
            return old

        server = FakeServer()
        with patch.object(launcher.signal, "signal", side_effect=fake_signal):
            launcher.run_server(server)
        assert server.closed and server.calls == 1 and server.timeout == 1.0
        assert handlers[signal.SIGTERM] == signal.SIG_DFL

        class FakeChild:
            def __init__(self):
                self.pid = None
                self.alive = False
                self.started = False
                self.terminated = False
                self.killed = False
                self.join_calls = 0
            def start(self):
                self.pid = 98765
                self.alive = True
                self.started = True
            def is_alive(self):
                return self.alive
            def terminate(self):
                self.terminated = True
            def join(self, timeout):
                self.join_calls += 1
                if self.join_calls > 1:
                    self.alive = False
            def kill(self):
                self.killed = True
                self.alive = False

        child = FakeChild()
        with patch.object(launcher.multiprocessing, "get_context") as context, \
             patch.object(launcher, "checked_qwen_identity") as qwen, \
             patch.object(launcher, "checked_free_vram", return_value=3000) as gpu, \
             patch.object(launcher.time, "monotonic", side_effect=[0, 1, 5]), \
             patch.object(launcher.time, "sleep"):
            context.return_value.Process.return_value = child
            expect_safety("RUNTIME_LIMIT", lambda: launcher.supervise_worker(
                str(snapshot), runtime_min_free_vram_mib=256,
                max_runtime_seconds=3,
            ))
            context.assert_called_once_with("spawn")
            assert context.return_value.Process.call_args.kwargs["daemon"] is True
            qwen.assert_called_once_with()
            gpu.assert_called_once_with(256)
        assert child.started and child.terminated and child.killed

        child2 = FakeChild()
        with patch.object(launcher.multiprocessing, "get_context") as context, \
             patch.object(launcher, "checked_qwen_identity", side_effect=launcher.LaunchSafetyError("QWEN_IDENTITY_MISMATCH")), \
             patch.object(launcher.time, "monotonic", side_effect=[0, 0.1]):
            context.return_value.Process.return_value = child2
            expect_safety("QWEN_HEALTH_LOST", lambda: launcher.supervise_worker(
                str(snapshot), runtime_min_free_vram_mib=256,
                max_runtime_seconds=3,
            ))
        assert child2.terminated and child2.killed

        child3 = FakeChild()
        with patch.object(launcher.multiprocessing, "get_context") as context, \
             patch.object(launcher, "checked_qwen_identity"), \
             patch.object(launcher, "checked_free_vram", side_effect=launcher.LaunchSafetyError("GPU_HEADROOM_INSUFFICIENT")), \
             patch.object(launcher.time, "monotonic", side_effect=[0, 0.1]):
            context.return_value.Process.return_value = child3
            expect_safety("GPU_HEADROOM_LOST", lambda: launcher.supervise_worker(
                str(snapshot), runtime_min_free_vram_mib=256,
                max_runtime_seconds=3,
            ))
        assert child3.terminated and child3.killed

    print("STAGE11_INT8_EPHEMERAL_LAUNCHER_SMOKE=PASS")
    print("CUDA_MODEL_LOAD=0 NETWORK_REQUESTS=0 PRODUCTION_WRITES=0")


if __name__ == "__main__":
    main()
