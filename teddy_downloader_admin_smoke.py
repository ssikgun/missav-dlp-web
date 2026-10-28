"""Focused synthetic tests for Downloader administrative safety candidates."""

import hashlib
import importlib.util
import io
import json
import os
import queue
import sys
import tempfile
import threading
import types
from pathlib import Path
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

ADMIN_MODE = os.environ.get("DLDWS_ADMIN_MODE", "root").strip().lower()
if ADMIN_MODE not in {"root", "overlay"}:
    raise RuntimeError(f"unsupported DLDWS_ADMIN_MODE: {ADMIN_MODE}")
ADMIN_MODULE_PATH = Path(
    os.environ.get(
        "DLDWS_ADMIN_MODULE_PATH",
        str(Path(__file__).resolve().with_name("teddy_downloader_admin.py")),
    )
).resolve()
if not ADMIN_MODULE_PATH.is_file():
    raise RuntimeError(f"administrator source does not exist: {ADMIN_MODULE_PATH}")
_admin_spec = importlib.util.spec_from_file_location(
    f"dldws_admin_under_test_{ADMIN_MODE}", ADMIN_MODULE_PATH
)
if _admin_spec is None or _admin_spec.loader is None:
    raise RuntimeError(f"cannot load administrator source: {ADMIN_MODULE_PATH}")
admin = importlib.util.module_from_spec(_admin_spec)
sys.modules[_admin_spec.name] = admin
_admin_spec.loader.exec_module(admin)
ADMIN_MODULE_SHA256 = hashlib.sha256(ADMIN_MODULE_PATH.read_bytes()).hexdigest()
expected_mode = os.environ.get("DLDWS_ADMIN_EXPECTED_MODE")
expected_sha256 = os.environ.get("DLDWS_ADMIN_EXPECTED_SHA256")
expected_path = os.environ.get("DLDWS_ADMIN_EXPECTED_PATH")
if expected_mode and ADMIN_MODE != expected_mode:
    raise AssertionError(f"administrator mode mismatch: {ADMIN_MODE} != {expected_mode}")
if expected_sha256 and ADMIN_MODULE_SHA256 != expected_sha256:
    raise AssertionError(
        f"administrator SHA-256 mismatch: {ADMIN_MODULE_SHA256} != {expected_sha256}"
    )
if expected_path and ADMIN_MODULE_PATH != Path(expected_path).resolve():
    raise AssertionError(
        f"administrator path mismatch: {ADMIN_MODULE_PATH} != {Path(expected_path).resolve()}"
    )
import teddy_spoofdpi


class FakeMp4Queue:
    def __init__(self, module=None):
        self.module = module
        self.active = set()
        self.jobs = []

    def has_task(self, core, task_id):
        if self.module is not None:
            return self.module.has_task(core, task_id)
        return task_id in self.active

    def _job_path(self, root, task_id):
        if self.module is None:
            raise RuntimeError("the root-stage fake has no MP4 job path")
        return self.module._job_path(root, task_id)

    def _job_files(self, root):
        return list(self.jobs)


class FakeSafety:
    def __init__(self, reserve=0, state_lock=None):
        self.reserve = reserve
        self._TASK_STATE_LOCK = state_lock

    def reserve_bytes(self, total):
        return self.reserve


def make_core(tmpdir, tasks=None, queue_lock=None, retry_callback=None):
    app = Flask("admin-smoke")
    app.secret_key = "synthetic-test-session-key"
    core = SimpleNamespace(
        app=app,
        DOWNLOAD_DIR=tmpdir,
        tasks=tasks if tasks is not None else {},
        settings={"max_concurrent": 4},
        download_queue=queue.Queue(),
        queue_admission_lock=queue_lock if queue_lock is not None else threading.RLock(),
        save_tasks=lambda: None,
    )
    def fake_result(value):
        return SimpleNamespace(get_json=lambda silent=False: value)

    def root_safe_retry(task_id):
        body, code = admin.manual_retry(core, task_id)
        return fake_result(body), code

    core._teddy_safe_retry_task = retry_callback if retry_callback is not None else root_safe_retry
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


def load_overlay_modules():
    if ADMIN_MODE != "overlay":
        raise RuntimeError("overlay modules may only be imported in explicit overlay mode")
    import teddy_download_safety
    import teddy_mp4_queue
    return teddy_download_safety, teddy_mp4_queue


def write_synthetic_mp4_job(mp4_module, root, task_id):
    path = mp4_module._job_path(root, task_id)
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    record = mp4_module._seal_job({
        "schema": mp4_module.SCHEMA,
        "task_id": str(task_id),
        "kind": "legacy_ts",
        "stage": "queued",
        "payload": {"source_path": os.path.join(root, "synthetic.ts"), "required_output_bytes": 0},
    })
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(record, handle, sort_keys=True)
        handle.write("\n")
    return path


def post_overlay_retry(core, token="synthetic-csrf-token"):
    client = core.app.test_client()
    assert hasattr(client, "session_transaction"), "overlay route smoke requires Flask's test client"
    with client.session_transaction() as state:
        state["authenticated"] = True
        state[admin.CSRF_SESSION_KEY] = token
    return client.post("/api/tasks/retry-failed", headers={"X-CSRF-Token": token})


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


def test_overlay_bulk_retry_semantics():
    safety, mp4 = load_overlay_modules()
    assert not hasattr(admin, "manual_retry"), "overlay smoke must not depend on root-only manual_retry"
    with tempfile.TemporaryDirectory(prefix="dldws-overlay-admin-") as root:
        parts = os.path.join(root, ".err1.parts")
        os.mkdir(parts)
        chunk = os.path.join(parts, "00000.ts")
        with open(chunk, "wb") as handle:
            handle.write(b"synthetic overlay fragment")
        before = hashlib.sha256(Path(chunk).read_bytes()).hexdigest()
        tasks = {
            "err1": {"status": "에러: ENOSPC", "retries": 30, "url": "https://synthetic.invalid/a"},
            "err2": {"status": "에러: failed", "retries": 7, "mp4_stage": "queued"},
            "duplicate": {"status": "에러: already queued", "retries": 4},
            "active_mp4": {"status": "에러: post-process", "retries": 2, "mp4_stage": "running"},
            "done": {"status": "완료", "retries": 0},
            "paused": {"status": "일시정지", "retries": 4},
        }
        calls = []

        def safe_retry_callback(task_id):
            calls.append(task_id)
            return jsonify({"status": "success", "message": "synthetic callback result"}), 200

        core = make_core(
            root,
            tasks,
            queue_lock=safety._TASK_STATE_LOCK,
            retry_callback=safe_retry_callback,
        )
        core.download_queue.put("duplicate")
        mp4_path = write_synthetic_mp4_job(mp4, root, "err2")
        assert mp4.has_task(core, "err2") and os.path.isfile(mp4_path)
        assert not mp4.has_task(core, "active_mp4")
        admin.install(core, mp4, safety)
        with mock.patch.object(safety, "reserve_bytes", return_value=0):
            response = post_overlay_retry(core)
        body = response.get_json()
        assert response.status_code == 200
        assert body["succeeded"] == 1 and body["skipped"] == 3 and body["failed"] == 0, body
        assert calls == ["err1"], calls
        assert tasks["err2"]["status"].startswith("에러")
        assert tasks["active_mp4"]["status"].startswith("에러")
        assert tasks["done"]["status"] == "완료" and tasks["paused"]["status"] == "일시정지"
        assert list(core.download_queue.queue) == ["duplicate"]
        assert hashlib.sha256(Path(chunk).read_bytes()).hexdigest() == before


def test_overlay_refuses_missing_or_mismatched_shared_lock():
    safety, mp4 = load_overlay_modules()
    callbacks = []
    with tempfile.TemporaryDirectory(prefix="dldws-overlay-lock-") as root:
        core = make_core(root, {"failed": {"status": "에러: synthetic"}}, queue_lock=safety._TASK_STATE_LOCK)
        callback = lambda task_id: (callbacks.append(task_id) or (None, 200))
        mismatched = SimpleNamespace(
            _TASK_STATE_LOCK=threading.RLock(),
            reserve_bytes=lambda total: 0,
        )
        body, code = admin._bulk_retry(core, callback, mp4, mismatched)
        assert code == 503 and callbacks == [] and body["status"] == "error"

        core.queue_admission_lock = None
        body, code = admin._bulk_retry(core, callback, mp4, safety)
        assert code == 503 and callbacks == [] and body["status"] == "error"


def test_overlay_refuses_uncertain_mp4_queue_state():
    safety, mp4 = load_overlay_modules()
    callbacks = []
    callback = lambda task_id: (callbacks.append(task_id) or (None, 200))

    with tempfile.TemporaryDirectory(prefix="dldws-overlay-mp4-path-error-") as root:
        core = make_core(root, {"path_error": {"status": "에러: synthetic"}}, queue_lock=safety._TASK_STATE_LOCK)
        with mock.patch.object(mp4, "_job_path", side_effect=OSError("synthetic path inspection failure")):
            body, code = admin._bulk_retry(core, callback, mp4, safety)
        assert code == 503 and body["status"] == "error" and callbacks == []

    with tempfile.TemporaryDirectory(prefix="dldws-overlay-mp4-mismatch-") as root:
        core = make_core(root, {"mismatch": {"status": "에러: synthetic"}}, queue_lock=safety._TASK_STATE_LOCK)
        write_synthetic_mp4_job(mp4, root, "mismatch")
        inconsistent_mp4 = SimpleNamespace(
            _job_path=mp4._job_path,
            has_task=lambda current_core, task_id: False,
        )
        body, code = admin._bulk_retry(core, callback, inconsistent_mp4, safety)
        assert code == 503 and body["status"] == "error" and callbacks == []

    with tempfile.TemporaryDirectory(prefix="dldws-overlay-mp4-symlink-") as root:
        core = make_core(root, {"symlink": {"status": "에러: synthetic"}}, queue_lock=safety._TASK_STATE_LOCK)
        path = mp4._job_path(root, "symlink")
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        target = os.path.join(root, "synthetic-target.json")
        Path(target).write_text("synthetic only\n", encoding="utf-8")
        os.symlink(target, path)
        assert mp4.has_task(core, "symlink")
        body, code = admin._bulk_retry(core, callback, mp4, safety)
        assert code == 503 and body["status"] == "error" and callbacks == []

    with tempfile.TemporaryDirectory(prefix="dldws-overlay-mp4-stage-") as root:
        core = make_core(
            root,
            {"unknown": {"status": "에러: synthetic", "mp4_stage": "unrecognized-stage"}},
            queue_lock=safety._TASK_STATE_LOCK,
        )
        body, code = admin._bulk_retry(core, callback, mp4, safety)
        assert code == 503 and body["status"] == "error" and callbacks == []


def test_overlay_install_counts_callback_failure_as_failed():
    safety, mp4 = load_overlay_modules()
    with tempfile.TemporaryDirectory(prefix="dldws-overlay-admin-failure-") as root:
        tasks = {"failed": {"status": "에러: synthetic save/admission failure", "retries": 3}}
        calls = []

        def rejected_callback(task_id):
            calls.append(task_id)
            return jsonify({"status": "error", "message": "synthetic admission rejected"}), 503

        core = make_core(
            root,
            tasks,
            queue_lock=safety._TASK_STATE_LOCK,
            retry_callback=rejected_callback,
        )
        admin.install(core, mp4, safety)
        with mock.patch.object(safety, "reserve_bytes", return_value=0):
            response = post_overlay_retry(core)
        body = response.get_json()
        assert response.status_code == 200
        assert body["succeeded"] == 0 and body["failed"] == 1, body
        assert calls == ["failed"] and tasks["failed"]["status"].startswith("에러")
        assert core.download_queue.empty()


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
    print(f"ADMIN_MODULE mode={ADMIN_MODE} path={ADMIN_MODULE_PATH} sha256={ADMIN_MODULE_SHA256}")
    if ADMIN_MODE == "root":
        assert callable(getattr(admin, "manual_retry", None)), "root smoke must keep manual_retry coverage"
        cases = [
            ("root bulk retry semantics", test_bulk_retry_semantics),
            ("root storage/inode and partial retry results", test_bulk_retry_enospc_inode_and_partial_results),
            ("SpoofDPI diagnostics redaction", test_spoofdpi_diagnostics),
            ("administrator UI safety markers", test_ui_source_markers),
        ]
    else:
        assert not hasattr(admin, "manual_retry"), "overlay smoke must not require root-only manual_retry"
        print("OVERLAY_CALLBACK=mocked interface only; safe-retry implementation is not claimed as tested")
        cases = [
            ("overlay bulk retry semantics and MP4 protection", test_overlay_bulk_retry_semantics),
            ("overlay shared-lock fail-closed checks", test_overlay_refuses_missing_or_mismatched_shared_lock),
            ("overlay MP4 identity/type/state fail-closed checks", test_overlay_refuses_uncertain_mp4_queue_state),
            ("overlay callback failure accounting", test_overlay_install_counts_callback_failure_as_failed),
            ("SpoofDPI diagnostics redaction", test_spoofdpi_diagnostics),
            ("administrator UI safety markers", test_ui_source_markers),
        ]
    for name, test in cases:
        test()
        print(f"PASS: {name}")
    print(f"downloader admin {ADMIN_MODE} synthetic smoke: {len(cases)} PASS / 0 FAIL")


if __name__ == "__main__":
    main()
