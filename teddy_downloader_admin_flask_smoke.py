"""Real Flask test_client integration checks for isolated Downloader admin routes.

Run with an existing dependency-complete isolated Python environment. This test
never imports app.py, starts a worker, connects to a Unix socket, or uses
production data/services.
"""

import hashlib
import json
import os
import queue
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest import mock

import flask
from flask import Flask, jsonify
from werkzeug.security import generate_password_hash

import teddy_auth
import teddy_downloader_admin as admin


assert hasattr(Flask("flask-smoke"), "test_client")
assert "site-packages/flask/" in flask.__file__.replace("\\", "/")


class FakeMp4Queue:
    def __init__(self):
        self.active = set()
        self.jobs = []

    def has_task(self, core, task_id):
        return task_id in self.active

    def _job_files(self, root):
        return list(self.jobs)


class FakeSafety:
    def __init__(self, reserve=100):
        self.reserve = reserve

    def reserve_bytes(self, total):
        return self.reserve


class Fixture:
    def __init__(self, tasks=None, failed_retries=()):
        self.temp = tempfile.TemporaryDirectory(prefix="dldws001-flask-")
        self.root = self.temp.name
        self.auth_dir = os.path.join(self.root, "auth")
        self.download_dir = os.path.join(self.root, "downloads")
        os.mkdir(self.auth_dir)
        os.mkdir(self.download_dir)
        with open(os.path.join(self.auth_dir, "username"), "w", encoding="utf-8") as f:
            f.write("synthetic-user")
        with open(os.path.join(self.auth_dir, "password_hash"), "w", encoding="utf-8") as f:
            f.write(generate_password_hash("synthetic-password", method="pbkdf2:sha256:1000"))
        with open(os.path.join(self.auth_dir, "session_secret"), "w", encoding="utf-8") as f:
            f.write("synthetic-session-secret-only-for-test")

        self.app = Flask("dldws001-real-flask-test")
        self.app.config.update(TESTING=True, SERVER_NAME="downloader.ssikgun.com")
        self.mp4 = FakeMp4Queue()
        self.safety = FakeSafety()
        self.save_count = 0
        self.tasks = tasks if tasks is not None else {
            "retained": {"status": "에러: ENOSPC", "retries": 30},
            "done": {"status": "완료", "retries": 0},
            "paused": {"status": "일시정지", "retries": 8},
        }
        self.core = SimpleNamespace(
            app=self.app,
            DOWNLOAD_DIR=self.download_dir,
            tasks=self.tasks,
            settings={"auto_retry": True, "auto_retry_max": 30, "max_concurrent": 4},
            download_queue=queue.Queue(),
            queue_admission_lock=threading.RLock(),
        )

        def save_tasks():
            self.save_count += 1
            with open(os.path.join(self.download_dir, ".synthetic-state.json"), "w", encoding="utf-8") as f:
                json.dump(self.tasks, f, ensure_ascii=False, sort_keys=True)

        self.core.save_tasks = save_tasks

        def safe_retry(task_id):
            if task_id in failed_retries:
                response = jsonify({"status": "error", "message": "synthetic refusal"})
                return response, 409
            body, code = admin.manual_retry(self.core, task_id)
            return jsonify(body), code

        self.core._teddy_safe_retry_task = safe_retry
        previous_env = {
            name: os.environ.get(name)
            for name in ("TEDDY_AUTH_DIR", "TEDDY_AUTH_COOKIE_DOMAIN")
        }
        os.environ["TEDDY_AUTH_DIR"] = self.auth_dir
        os.environ["TEDDY_AUTH_COOKIE_DOMAIN"] = ".ssikgun.com"
        try:
            teddy_auth.install(self.core)
            admin.install(self.core, self.mp4, self.safety)
        finally:
            for name, value in previous_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

        self.client = self.app.test_client()
        self.base = "https://downloader.ssikgun.com"

    def open(self, method, path, **kwargs):
        return self.client.open(path, method=method, base_url=self.base, **kwargs)

    def login(self, client=None):
        client = client or self.client
        response = client.post(
            "/login", base_url=self.base,
            data={"username": "synthetic-user", "password": "synthetic-password"},
        )
        assert response.status_code == 302, response.status_code
        response = client.get("/api/downloader/action-token", base_url=self.base)
        assert response.status_code == 200, response.status_code
        self.token = response.get_json()["token"]
        assert len(self.token) >= 32
        assert response.headers.get("Cache-Control") == "no-store"
        return client

    def headers(self, token=None):
        return {"X-CSRF-Token": token if token is not None else self.token}


def test_real_bulk_retry_auth_and_csrf():
    with _fixture_context(tasks={}) as fixture:
        assert fixture.open("POST", "/api/tasks/retry-failed").status_code == 401
        assert fixture.open("GET", "/api/downloader/action-token").status_code == 401
        fixture.login()
        assert fixture.open("POST", "/api/tasks/retry-failed").status_code == 403
        assert fixture.open(
            "POST", "/api/tasks/retry-failed", headers=fixture.headers("wrong-token"),
        ).status_code == 403
        response = fixture.open("POST", "/api/tasks/retry-failed", headers=fixture.headers())
        assert response.status_code == 200, response.get_json()
        assert response.get_json() == {
            "status": "success", "succeeded": 0, "skipped": 0, "failed": 0, "results": [],
        }


def test_real_bulk_retry_selection_capacity_parts_and_records():
    tasks = {
        "e1": {"status": "에러: ENOSPC", "retries": 30},
        "e2": {"status": "에러: synthetic failure", "retries": 7},
        "queued": {"status": "에러: already auto-retry queued", "retries": 12},
        "mp4": {"status": "에러: mp4 pending", "retries": 6},
        "done": {"status": "완료", "retries": 0},
        "paused": {"status": "일시정지", "retries": 4},
        "running": {"status": "다운로드 중", "retries": 2},
    }
    with _fixture_context(tasks=tasks) as fixture:
        fixture.login()
        parts_hashes = {}
        for task_id in ("e1", "e2", "queued", "mp4"):
            parts = os.path.join(fixture.core.DOWNLOAD_DIR, f".{task_id}.parts")
            os.mkdir(parts)
            fragment = os.path.join(parts, "synthetic.ts")
            with open(fragment, "wb") as f:
                f.write(("fragment:" + task_id).encode())
            with open(fragment, "rb") as f:
                parts_hashes[task_id] = hashlib.sha256(f.read()).hexdigest()
        fixture.core.download_queue.put("queued")
        fixture.mp4.active.add("mp4")
        enough_disk = SimpleNamespace(total=10_000_000, free=9_000_000)
        enough_inodes = SimpleNamespace(f_favail=50_000)
        with mock.patch.object(admin.shutil, "disk_usage", return_value=enough_disk), \
             mock.patch.object(admin.os, "statvfs", return_value=enough_inodes):
            result = fixture.open("POST", "/api/tasks/retry-failed", headers=fixture.headers())
        assert result.status_code == 200, result.get_json()
        body = result.get_json()
        assert (body["succeeded"], body["skipped"], body["failed"]) == (2, 2, 0), body
        assert {row["id"]: row["result"] for row in body["results"]} == {
            "e1": "queued", "e2": "queued", "queued": "skipped", "mp4": "skipped",
        }
        assert fixture.core.settings["max_concurrent"] == 4
        assert tasks["e1"]["retries"] == tasks["e2"]["retries"] == 0
        assert tasks["done"]["status"] == "완료" and tasks["paused"]["status"] == "일시정지"
        assert tasks["running"]["status"] == "다운로드 중"
        assert list(fixture.core.download_queue.queue) == ["queued", "e1", "e2"]
        for task_id, original_hash in parts_hashes.items():
            with open(os.path.join(fixture.core.DOWNLOAD_DIR, f".{task_id}.parts", "synthetic.ts"), "rb") as f:
                assert hashlib.sha256(f.read()).hexdigest() == original_hash
        assert tasks["queued"]["retries"] == 12 and tasks["mp4"]["retries"] == 6


def test_real_bulk_retry_fails_closed_on_bytes_and_inodes():
    for mode in ("bytes", "inodes"):
        tasks = {"error": {"status": "에러: ENOSPC", "retries": 30}}
        with _fixture_context(tasks=tasks) as fixture:
            fixture.login()
            parts = os.path.join(fixture.core.DOWNLOAD_DIR, ".error.parts")
            os.mkdir(parts)
            fragment = os.path.join(parts, "keep.ts")
            with open(fragment, "wb") as f:
                f.write(b"synthetic-recovery-fragment")
            before = hashlib.sha256(open(fragment, "rb").read()).hexdigest()
            disk = SimpleNamespace(total=10000, free=10 if mode == "bytes" else 9000)
            inodes = SimpleNamespace(f_favail=50000 if mode == "bytes" else 10)
            with mock.patch.object(admin.shutil, "disk_usage", return_value=disk), \
                 mock.patch.object(admin.os, "statvfs", return_value=inodes):
                response = fixture.open("POST", "/api/tasks/retry-failed", headers=fixture.headers())
            assert response.status_code == 507, (mode, response.status_code, response.get_json())
            assert tasks["error"]["status"] == "에러: ENOSPC" and tasks["error"]["retries"] == 30
            assert fixture.core.download_queue.empty()
            with open(fragment, "rb") as f:
                assert hashlib.sha256(f.read()).hexdigest() == before


def test_real_bulk_retry_partial_result_and_auto_retry_race():
    tasks = {
        "ok": {"status": "에러: retryable", "retries": 30},
        "fail": {"status": "에러: retryable", "retries": 30},
    }
    with _fixture_context(tasks=tasks, failed_retries={"fail"}) as fixture:
        fixture.login()
        with mock.patch.object(admin.shutil, "disk_usage", return_value=SimpleNamespace(total=10000, free=9000)), \
             mock.patch.object(admin.os, "statvfs", return_value=SimpleNamespace(f_favail=5000)):
            response = fixture.open("POST", "/api/tasks/retry-failed", headers=fixture.headers())
        body = response.get_json()
        assert response.status_code == 200
        assert (body["succeeded"], body["skipped"], body["failed"]) == (1, 0, 1)
        assert {row["id"]: row["result"] for row in body["results"]} == {"ok": "queued", "fail": "failed"}
        assert tasks["ok"]["status"] == "대기 중" and tasks["fail"]["status"].startswith("에러")

    # Controlled race: an auto-retry producer owns the same admission lock,
    # changes the task to queued, and enqueues it before the HTTP handler enters.
    tasks = {"race": {"status": "에러: retryable", "retries": 30}}
    with _fixture_context(tasks=tasks) as fixture:
        fixture.login()
        second_client = fixture.app.test_client()
        fixture.login(second_client)
        fixture.core.queue_admission_lock.acquire()
        finished = threading.Event()
        outcome = {}

        def request_bulk():
            try:
                outcome["response"] = second_client.post(
                    "/api/tasks/retry-failed", base_url=fixture.base,
                    headers={"X-CSRF-Token": fixture.token},
                )
            finally:
                finished.set()

        worker = threading.Thread(target=request_bulk, daemon=True)
        worker.start()
        time.sleep(0.05)
        was_blocked = not finished.is_set()
        try:
            tasks["race"]["status"] = "대기 중"
            fixture.core.download_queue.put("race")
        finally:
            fixture.core.queue_admission_lock.release()
        worker.join(timeout=3)
        assert was_blocked
        assert finished.is_set()
        response = outcome["response"]
        assert response.status_code == 200
        assert response.get_json()["succeeded"] == 0
        assert response.get_json()["skipped"] == 0
        assert fixture.core.download_queue.qsize() == 1


class _fixture_context:
    def __init__(self, tasks=None, failed_retries=()):
        self.fixture = Fixture(tasks=tasks, failed_retries=failed_retries)

    def __enter__(self):
        return self.fixture

    def __exit__(self, exc_type, exc, tb):
        self.fixture.temp.cleanup()
        return False


def main():
    test_real_bulk_retry_auth_and_csrf()
    test_real_bulk_retry_selection_capacity_parts_and_records()
    test_real_bulk_retry_fails_closed_on_bytes_and_inodes()
    test_real_bulk_retry_partial_result_and_auto_retry_race()
    print("real Flask test_client admin route integration: PASS (actual Flask + teddy_auth + installed routes)")


if __name__ == "__main__":
    main()
