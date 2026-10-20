"""Focused synthetic tests for Downloader administrative safety candidates."""

import hashlib
import io
import json
import os
import queue
import sys
import tempfile
import threading
import types
from types import SimpleNamespace
from unittest import mock

try:
    from flask import Flask, jsonify, session
except ModuleNotFoundError:
    class FakeResponse:
        def __init__(self, value=None, status_code=200):
            self.value = value
            self.status_code = status_code
            self.headers = {}

        def get_json(self, silent=False):
            return self.value

    _fake_flask = types.ModuleType("flask")
    _fake_flask.session = {}
    _fake_flask.request = SimpleNamespace(path="", headers={}, method="GET")
    _fake_flask.jsonify = lambda value: FakeResponse(value)

    class FakeFlask:
        def __init__(self, name):
            self.views = {}
            self.before = []

        def get(self, route):
            return self.route(route, methods=["GET"])

        def post(self, route):
            return self.route(route, methods=["POST"])

        def route(self, route, methods=None):
            def decorator(function):
                self.views[(route, tuple(methods or ["GET"]))] = function
                return function
            return decorator

        def before_request(self, function):
            self.before.append(function)
            return function

        def test_client(self):
            app = self
            class Client:
                def open(self, path, method, json=None, headers=None):
                    _fake_flask.request.path = path
                    _fake_flask.request.method = method
                    _fake_flask.request.headers = headers or {}
                    result = None
                    for callback in app.before:
                        result = callback()
                        if result is not None:
                            break
                    if result is None:
                        match = None
                        for (route, methods), function in app.views.items():
                            if method not in methods:
                                continue
                            expected = route.strip("/").split("/")
                            actual = path.strip("/").split("/")
                            if len(expected) != len(actual):
                                continue
                            params = []
                            for left, right in zip(expected, actual):
                                if left.startswith("<") and left.endswith(">"):
                                    params.append(right)
                                elif left != right:
                                    break
                            else:
                                match = (function, params)
                                break
                        if match is None:
                            return FakeResponse({"status": "not-found"}, 404)
                        result = match[0](*match[1])
                    status = 200
                    if isinstance(result, tuple):
                        result, status = result
                    if not isinstance(result, FakeResponse):
                        result = FakeResponse({"body": str(result)})
                    result.status_code = status
                    return result

                def get(self, path, **kwargs):
                    return self.open(path, "GET", **kwargs)

                def post(self, path, **kwargs):
                    return self.open(path, "POST", **kwargs)
            return Client()

    _fake_flask.Flask = FakeFlask
    sys.modules["flask"] = _fake_flask
    from flask import Flask, jsonify, session

import teddy_downloader_admin as admin
import teddy_spoofdpi


class FakeMp4Queue:
    def __init__(self):
        self.active = set()
        self.jobs = []

    def has_task(self, core, task_id):
        return task_id in self.active

    def _job_files(self, root):
        return list(self.jobs)


class FakeSafety:
    def __init__(self, reserve=0):
        self.reserve = reserve

    def reserve_bytes(self, total):
        return self.reserve


def make_core(tmpdir, tasks=None):
    app = Flask("admin-smoke")
    app.secret_key = "synthetic-test-session-key"
    core = SimpleNamespace(
        app=app,
        DOWNLOAD_DIR=tmpdir,
        tasks=tasks or {},
        settings={"max_concurrent": 4},
        download_queue=queue.Queue(),
        queue_admission_lock=threading.RLock(),
        save_tasks=lambda: None,
    )
    def fake_result(value):
        return SimpleNamespace(get_json=lambda silent=False: value)

    def safe_retry(task_id):
        body, code = admin.manual_retry(core, task_id)
        return fake_result(body), code

    core._teddy_safe_retry_task = safe_retry
    @app.before_request
    def auth_gate():
        if request_path := __import__("flask").request.path:
            if request_path.startswith("/api/") and session.get("authenticated") is not True:
                return jsonify({"status": "error"}), 401

    @app.post("/test-login")
    def login_for_test():
        session["authenticated"] = True
        return "ok"

    return core


def test_bulk_retry_semantics():
    with tempfile.TemporaryDirectory(prefix="dldws-admin-") as root:
        parts = os.path.join(root, ".err1.parts")
        os.mkdir(parts)
        chunk = os.path.join(parts, "00000.ts")
        with open(chunk, "wb") as handle:
            handle.write(b"synthetic fragment")
        before = hashlib.sha256(open(chunk, "rb").read()).hexdigest()
        tasks = {
            "err1": {"status": "에러: ENOSPC", "retries": 30, "url": "https://synthetic.invalid/a"},
            "err2": {"status": "에러: failed", "retries": 7, "url": "https://synthetic.invalid/b"},
            "duplicate": {"status": "에러: auto retry queued", "retries": 4},
            "done": {"status": "완료", "retries": 0},
            "paused": {"status": "일시정지", "retries": 4},
        }
        core = make_core(root, tasks)
        core.download_queue.put("duplicate")
        mp4 = FakeMp4Queue()
        mp4.active.add("err2")
        body, code = admin._bulk_retry(core, core._teddy_safe_retry_task, mp4, FakeSafety())
        assert code == 200
        assert body["succeeded"] == 1 and body["skipped"] == 2 and body["failed"] == 0
        assert tasks["err1"]["status"] == "대기 중" and tasks["err1"]["retries"] == 0
        assert tasks["done"]["status"] == "완료" and tasks["paused"]["status"] == "일시정지"
        assert list(core.download_queue.queue) == ["duplicate", "err1"]
        assert hashlib.sha256(open(chunk, "rb").read()).hexdigest() == before


def test_bulk_retry_enospc_inode_and_partial_results():
    with tempfile.TemporaryDirectory(prefix="dldws-admin-") as root:
        tasks = {"a": {"status": "에러: disk", "retries": 30}, "b": {"status": "에러: disk", "retries": 30}}
        core = make_core(root, tasks)
        with mock.patch.object(admin.shutil, "disk_usage", return_value=SimpleNamespace(total=10000, free=10)):
            body, code = admin._bulk_retry(core, core._teddy_safe_retry_task, FakeMp4Queue(), FakeSafety(100))
        assert code == 507 and tasks["a"]["status"].startswith("에러") and core.download_queue.empty()

        with mock.patch.object(admin.shutil, "disk_usage", return_value=SimpleNamespace(total=10000, free=9000)), \
             mock.patch.object(admin.os, "statvfs", return_value=SimpleNamespace(f_favail=1023)):
            body, code = admin._bulk_retry(core, core._teddy_safe_retry_task, FakeMp4Queue(), FakeSafety(100))
        assert code == 507 and core.download_queue.empty()

        with mock.patch.object(admin.shutil, "disk_usage", return_value=SimpleNamespace(total=10000, free=9000)), \
             mock.patch.object(admin.os, "statvfs", return_value=SimpleNamespace(f_favail=5000)):
            def partial(task_id):
                if task_id == "b":
                    return SimpleNamespace(get_json=lambda silent=False: {"status": "error"}), 409
                return core._teddy_safe_retry_task(task_id)
            body, code = admin._bulk_retry(core, partial, FakeMp4Queue(), FakeSafety())
        assert code == 200 and body["succeeded"] == 1 and body["failed"] == 1, (code, body)


def test_spoofdpi_diagnostics():
    messages = []
    class Proc:
        stdout = io.BytesIO(b"exit token=abc Bearer secret http://user:pass@10.1.2.3/proxy\n" + b"x" * 6000)
        def poll(self): return 7
    argv = []
    result = teddy_spoofdpi.start_spoofdpi(
        popen=lambda args, **kwargs: (argv.append((args, kwargs)) or Proc()),
        sleep=lambda seconds: None,
        port=8080,
        log=messages.append,
    )
    assert result is not None and argv[0][0] == ["spoofdpi"]
    diagnostic = messages[-1]
    assert "exit_code=7" in diagnostic and "[url-redacted]" in diagnostic
    assert "abc" not in diagnostic and "secret" not in diagnostic and "10.1.2.3" not in diagnostic and len(diagnostic) < 700

    missing = []
    teddy_spoofdpi.start_spoofdpi(
        popen=lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError()),
        sleep=lambda _: None,
        port=8080,
        log=missing.append,
    )
    assert "FileNotFoundError" in missing[0]

    alive = []
    class Alive(Proc):
        stdout = io.BytesIO(b"")
        def poll(self): return None
    teddy_spoofdpi.start_spoofdpi(
        popen=lambda *a, **kw: Alive(), sleep=lambda _: None, port=8080, log=alive.append,
    )
    assert "가동 성공" in alive[0]


def test_ui_source_markers():
    with open("templates/index.html", encoding="utf-8") as handle:
        html = handle.read()
    with open("templates/teddy-reliability.js", encoding="utf-8") as handle:
        script = handle.read()
    assert 'id="restartDownloader"' not in html
    assert html.count('id="retryFailedTasks"') == 1
    assert html.count('id="retryFailedCount"') == 1
    assert "변경 시 재시작 필요" in html
    assert "@media (max-width: 720px)" in html
    assert "기존 다운로드 조각은 유지됩니다." in script
    assert "X-CSRF-Token" in script
    assert "/api/downloader/restart" not in script
    assert "restartDownloader" not in script


def main():
    test_bulk_retry_semantics()
    test_bulk_retry_enospc_inode_and_partial_results()
    test_spoofdpi_diagnostics()
    test_ui_source_markers()
    print("downloader admin synthetic smoke: OK")


if __name__ == "__main__":
    main()
