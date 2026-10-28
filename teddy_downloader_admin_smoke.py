"""Synthetic safety checks for the single final Downloader administrator source."""

import hashlib
import io
import json
import os
import queue
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from flask import Flask, jsonify
from werkzeug.security import generate_password_hash

import teddy_auth
import teddy_downloader_admin as admin
import teddy_spoofdpi


ADMIN_MODULE_PATH = Path(admin.__file__).resolve()
ADMIN_MODULE_SHA256 = hashlib.sha256(ADMIN_MODULE_PATH.read_bytes()).hexdigest()
assert ADMIN_MODULE_PATH == Path(__file__).resolve().with_name("teddy_downloader_admin.py")
assert ADMIN_MODULE_SHA256 == "73984205a2340a05a930132bf248bb1a8c07125391167aa9d5e1c072f247cb31"


def make_core(tmpdir, tasks=None, queue_lock=None, retry_callback=None):
    app = Flask("admin-smoke")
    app.secret_key = "synthetic-test-session-key"
    return SimpleNamespace(
        app=app,
        DOWNLOAD_DIR=tmpdir,
        tasks=tasks if tasks is not None else {},
        settings={"max_concurrent": 4},
        download_queue=queue.Queue(),
        queue_admission_lock=queue_lock if queue_lock is not None else threading.RLock(),
        save_tasks=lambda: None,
        _teddy_safe_retry_task=retry_callback,
    )


def load_runtime_modules():
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


def post_admin_retry(core, token="synthetic-csrf-token"):
    client = core.app.test_client()
    assert hasattr(client, "session_transaction"), "administrator route smoke requires Flask's test client"
    with client.session_transaction() as state:
        state[admin.CSRF_SESSION_KEY] = token
    return client.post("/api/tasks/retry-failed", headers={"X-CSRF-Token": token})


def test_bulk_retry_semantics():
    safety, mp4 = load_runtime_modules()
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
            "running": {"status": "다운로드 중", "retries": 2},
        }
        before_tasks = json.dumps(tasks, sort_keys=True)
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
            response = post_admin_retry(core)
        body = response.get_json()
        assert response.status_code == 200
        assert body["succeeded"] == 1 and body["skipped"] == 3 and body["failed"] == 0, body
        assert calls == ["err1"], calls
        assert tasks["err2"]["status"].startswith("에러")
        assert tasks["active_mp4"]["status"].startswith("에러")
        assert tasks["done"]["status"] == "완료" and tasks["paused"]["status"] == "일시정지"
        assert json.dumps(tasks, sort_keys=True) == before_tasks
        assert list(core.download_queue.queue) == ["duplicate"]
        assert hashlib.sha256(Path(chunk).read_bytes()).hexdigest() == before


def test_refuses_missing_or_mismatched_shared_lock():
    safety, mp4 = load_runtime_modules()
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


def test_refuses_uncertain_mp4_queue_state():
    safety, mp4 = load_runtime_modules()
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


def test_install_counts_callback_failure_as_failed():
    safety, mp4 = load_runtime_modules()
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
            response = post_admin_retry(core)
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


def test_storage_inode_and_partial_results():
    safety, mp4 = load_runtime_modules()
    with tempfile.TemporaryDirectory(prefix="dldws-admin-capacity-") as root:
        tasks = {"a": {"status": "에러: disk", "retries": 30}, "b": {"status": "에러: disk", "retries": 30}}
        before = json.dumps(tasks, sort_keys=True)
        calls = []

        def partial(task_id):
            calls.append(task_id)
            value = {"status": "success" if task_id == "a" else "error"}
            return SimpleNamespace(get_json=lambda silent=False: value), 200 if task_id == "a" else 503

        core = make_core(root, tasks, queue_lock=safety._TASK_STATE_LOCK, retry_callback=partial)
        with mock.patch.object(safety, "reserve_bytes", return_value=100), \
             mock.patch.object(admin.shutil, "disk_usage", return_value=SimpleNamespace(total=10000, free=10)):
            body, code = admin._bulk_retry(core, partial, mp4, safety)
        assert code == 507 and calls == [] and core.download_queue.empty()
        assert json.dumps(tasks, sort_keys=True) == before

        with mock.patch.object(safety, "reserve_bytes", return_value=100), \
             mock.patch.object(admin.shutil, "disk_usage", return_value=SimpleNamespace(total=10000, free=9000)), \
             mock.patch.object(admin.os, "statvfs", return_value=SimpleNamespace(f_favail=1023)):
            body, code = admin._bulk_retry(core, partial, mp4, safety)
        assert code == 507 and calls == [] and core.download_queue.empty()
        assert json.dumps(tasks, sort_keys=True) == before

        with mock.patch.object(safety, "reserve_bytes", return_value=100), \
             mock.patch.object(admin.shutil, "disk_usage", return_value=SimpleNamespace(total=10000, free=9000)), \
             mock.patch.object(admin.os, "statvfs", return_value=SimpleNamespace(f_favail=5000)):
            body, code = admin._bulk_retry(core, partial, mp4, safety)
        assert code == 200 and (body["succeeded"], body["skipped"], body["failed"]) == (1, 0, 1), body
        assert {row["id"]: row["result"] for row in body["results"]} == {"a": "queued", "b": "failed"}
        assert calls == ["a", "b"] and core.download_queue.empty()
        # This mocked callback tests accounting; the real callback owns state persistence and admission.
        assert json.dumps(tasks, sort_keys=True) == before


def test_authentication_csrf_and_missing_callback():
    safety, mp4 = load_runtime_modules()
    with tempfile.TemporaryDirectory(prefix="dldws-admin-auth-") as root:
        core = make_core(root, queue_lock=safety._TASK_STATE_LOCK, retry_callback=lambda task_id: None)
        auth_dir = Path(root) / "auth"
        auth_dir.mkdir(mode=0o700)
        secrets = {
            "username": "synthetic-user",
            "password_hash": generate_password_hash("synthetic-password", method="pbkdf2:sha256:1000"),
            "session_secret": "synthetic-test-session-secret",
        }
        for name, value in secrets.items():
            (auth_dir / name).write_text(value, encoding="utf-8")
        with mock.patch.dict(os.environ, {"TEDDY_AUTH_DIR": str(auth_dir), "TEDDY_AUTH_COOKIE_DOMAIN": ".ssikgun.com"}):
            teddy_auth.install(core)
        admin.install(core, mp4, safety)
        client = core.app.test_client()
        base = "https://downloader.ssikgun.com"
        assert client.post("/api/tasks/retry-failed", base_url=base).status_code == 401
        assert client.get("/api/downloader/action-token", base_url=base).status_code == 401
        assert client.post("/login", base_url=base, data={"username": "synthetic-user", "password": "synthetic-password"}).status_code == 302
        response = client.get("/api/downloader/action-token", base_url=base)
        assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
        token = response.get_json()["token"]
        assert isinstance(token, str) and len(token) >= 32
        assert client.post("/api/tasks/retry-failed", base_url=base).status_code == 403
        assert client.post("/api/tasks/retry-failed", base_url=base, headers={"X-CSRF-Token": "wrong-token"}).status_code == 403
        response = client.post("/api/tasks/retry-failed", base_url=base, headers={"X-CSRF-Token": token})
        assert response.status_code == 200
        assert response.get_json() == {"status": "success", "succeeded": 0, "skipped": 0, "failed": 0, "results": []}

    with tempfile.TemporaryDirectory(prefix="dldws-admin-no-callback-") as root:
        core = make_core(root, queue_lock=safety._TASK_STATE_LOCK)
        admin.install(core, mp4, safety)
        response = post_admin_retry(core)
        assert response.status_code == 503 and response.get_json()["status"] == "error"


def main():
    print(f"ADMIN_MODULE path={ADMIN_MODULE_PATH} sha256={ADMIN_MODULE_SHA256}")
    assert not hasattr(admin, "manual_retry"), "the single final administrator has no legacy manual_retry API"
    print("RETRY_CALLBACK=mocked interface only; actual safe-retry implementation is not tested")
    cases = [
        test_bulk_retry_semantics,
        test_refuses_missing_or_mismatched_shared_lock,
        test_refuses_uncertain_mp4_queue_state,
        test_install_counts_callback_failure_as_failed,
        test_storage_inode_and_partial_results,
        test_authentication_csrf_and_missing_callback,
        test_spoofdpi_diagnostics,
        test_ui_source_markers,
    ]
    for test in cases:
        test()
        print(f"PASS: {test.__name__}")
    print(f"downloader admin final synthetic smoke: {len(cases)} PASS / 0 FAIL")


if __name__ == "__main__":
    main()
