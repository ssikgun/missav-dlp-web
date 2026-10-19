"""Offline synthetic test for DWS-001 socket-activated Writer candidate.

No production service, filesystem socket, Docker, or real database is used.
Only children forked by this test may receive SIGKILL.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import socket
import stat
import tempfile
import time
from unittest import mock

from teddy_library_discovery_writer import (
    _take_systemd_listener, _UnixServer, WriterError,
    PROTOCOL_VERSION, UnixSocketDiscoveryWriterClient, serve,
)


class HealthOnlyWriter:
    def dispatch(self, request):
        if request == {"protocol_version": PROTOCOL_VERSION, "operation": "health"}:
            return {"protocol_version": PROTOCOL_VERSION, "status": "READY"}
        raise WriterError("PROTOCOL_INVALID")


def expect_unavailable(call):
    try:
        call()
    except WriterError as exc:
        assert exc.code == "WRITER_UNAVAILABLE"
    else:
        raise AssertionError("invalid activation was accepted")


def child_mode(fd: int, socket_path: str, *, reject: str | None = None):
    # This runs in a forked *test-only* child. Never touch any host service.
    try:
        if fd != 3:
            os.dup2(fd, 3)
        os.environ.update(LISTEN_PID=str(os.getpid()),
                          LISTEN_FDS="1", LISTEN_FDNAMES="writer")
        if reject == "path":
            expect_unavailable(lambda: _take_systemd_listener(socket_path + "-different"))
        elif reject == "fdname":
            os.environ["LISTEN_FDNAMES"] = "unexpected"
            expect_unavailable(lambda: _take_systemd_listener(socket_path))
        elif reject == "count":
            os.environ["LISTEN_FDS"] = "2"
            expect_unavailable(lambda: _take_systemd_listener(socket_path))
        elif reject == "pid":
            os.environ["LISTEN_PID"] = str(os.getpid() + 1)
            expect_unavailable(lambda: _take_systemd_listener(socket_path))
        elif reject == "no-flag":
            expect_unavailable(lambda: serve("synthetic", "synthetic", socket_path))
        else:
            inherited = _take_systemd_listener(socket_path)
            server = _UnixServer(socket_path, HealthOnlyWriter(),
                                 inherited_socket=inherited)
            try:
                server.serve_forever(poll_interval=0.05)
            finally:
                server.server_close()
    except BaseException:
        os._exit(14)
    os._exit(0)


def start_child(fd: int, path: Path, *, reject: str | None = None):
    pid = os.fork()
    if pid == 0:
        child_mode(fd, str(path), reject=reject)
    return pid


def wait_exit(pid, expected=0):
    got, status = os.waitpid(pid, 0)
    assert got == pid
    assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == expected, (pid, status)


def health(path):
    client = UnixSocketDiscoveryWriterClient(str(path), timeout=0.25)
    for _ in range(60):
        try:
            return client.request("health").get("status") == "READY"
        except WriterError:
            time.sleep(0.05)
    return False


def main():
    with tempfile.TemporaryDirectory(prefix="dws001-socket-activation-") as temp:
        path = Path(temp) / "writer.sock"
        owner = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            owner.bind(str(path))
            owner.listen(8)
            original = path.lstat()
            identity = (original.st_dev, original.st_ino)
            assert stat.S_ISSOCK(original.st_mode)

            for mode in ("path", "fdname", "count", "pid", "no-flag"):
                pid = start_child(owner.fileno(), path, reject=mode)
                wait_exit(pid)
                assert path.exists(), mode
            print("INVALID_ACTIVATION_FAIL_CLOSED=PASS")

            for n in range(2):
                pid = start_child(owner.fileno(), path)
                try:
                    assert health(path), "health request failed on run " + str(n)
                finally:
                    os.kill(pid, signal.SIGKILL)
                    got, status = os.waitpid(pid, 0)
                    assert got == pid and os.WIFSIGNALED(status)
                current = path.lstat()
                assert (current.st_dev, current.st_ino) == identity
                print("RESTART_" + str(n + 1) + "_PATH_PRESERVED=PASS")

            # The owner is still listening even though both service children
            # were forcibly killed: the next client can queue and restart.
            assert owner.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) == 1
            assert path.exists()
            print("SYSTEMD_OWNED_PATH_UNLINKED=NO")
            print("SOCKET_ACTIVATION_RESTART=PASS")
        finally:
            owner.close()
    print("OPERATIONAL_WRITER_TOUCHED=NO")
    print("PRODUCT_RELEASE_TOUCHED=NO")


if __name__ == "__main__":
    main()
