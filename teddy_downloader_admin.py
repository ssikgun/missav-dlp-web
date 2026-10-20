"""Authenticated, fail-closed Downloader administrative actions."""

import hmac
import importlib
import os
import secrets
import shutil

from flask import jsonify, request, session


CSRF_SESSION_KEY = "dldws001_action_csrf"
MIN_FREE_INODES_FOR_MANUAL_RETRY = 1024


def _csrf_ok():
    expected = session.get(CSRF_SESSION_KEY)
    supplied = request.headers.get("X-CSRF-Token", "")
    return bool(
        isinstance(expected, str)
        and expected
        and supplied
        and hmac.compare_digest(expected, supplied)
    )


def _storage_capacity(core, safety_module):
    """Read-only byte/inode preflight; missing safety evidence fails closed."""
    if safety_module is None or not callable(getattr(safety_module, "reserve_bytes", None)):
        raise RuntimeError("저장 공간 안전 검사를 사용할 수 없습니다.")
    if not os.path.isdir(core.DOWNLOAD_DIR):
        raise RuntimeError("다운로드 저장 경로를 확인할 수 없습니다.")
    usage = shutil.disk_usage(core.DOWNLOAD_DIR)
    reserve = int(safety_module.reserve_bytes(usage.total))
    if usage.free < reserve:
        raise RuntimeError("다운로드 저장 공간이 안전 여유 기준보다 부족합니다.")
    filesystem = os.statvfs(core.DOWNLOAD_DIR)
    if filesystem.f_favail < MIN_FREE_INODES_FOR_MANUAL_RETRY:
        raise RuntimeError("다운로드 저장소의 여유 inode가 안전 기준보다 부족합니다.")
    return usage.free, filesystem.f_favail


def manual_retry(core, task_id):
    """Keep the existing individual manual-retry policy in one testable path."""
    lock = getattr(core, "queue_admission_lock", None)
    if lock is None:
        return {"status": "error", "message": "다운로드 큐 보호 상태를 확인할 수 없습니다."}, 503
    with lock:
        task = core.tasks.get(task_id)
        if not task:
            return {"status": "error", "message": "작업 없음"}, 404
        current = task.get("status", "")
        if current in ("다운로드 중", "대기 중", "일시정지 요청 중"):
            return {"status": "error", "message": "이미 진행 중인 작업"}, 400
        if current == "일시정지":
            return {"status": "error", "message": "일시정지 작업은 재개 버튼을 사용하세요."}, 400
        task["status"] = "대기 중"
        task["speed_bps"] = 0
        task["retries"] = 0
        core.save_tasks()
        core.download_queue.put(task_id)
        print(f"[Retry] 재시도 큐 추가: {task.get('url')}", flush=True)
        return {"status": "success", "message": "재시도 대기 중"}, 200


def _bulk_retry(core, retry_callback, mp4_queue_module, safety_module):
    lock = getattr(core, "queue_admission_lock", None)
    if lock is None:
        return {"status": "error", "message": "작업 큐 잠금을 확인할 수 없습니다."}, 503

    with lock:
        if not isinstance(core.tasks, dict):
            return {"status": "error", "message": "작업 상태를 확인할 수 없어 재시도를 차단했습니다."}, 503
        candidates = [
            task_id for task_id, task in list(core.tasks.items())
            if isinstance(task, dict)
            and isinstance(task.get("status"), str)
            and task["status"].startswith("에러")
        ]
        if not candidates:
            return {"status": "success", "succeeded": 0, "skipped": 0, "failed": 0, "results": []}, 200
        if mp4_queue_module is None or not callable(getattr(mp4_queue_module, "has_task", None)):
            return {"status": "error", "message": "MP4 작업 상태를 확인할 수 없어 재시도를 차단했습니다."}, 503
        try:
            _storage_capacity(core, safety_module)
        except Exception as exc:
            safe_message = str(exc) if isinstance(exc, RuntimeError) else "저장 공간 및 inode 사전 검증에 실패하여 재시도를 차단했습니다."
            return {"status": "error", "message": safe_message}, 507

        with core.download_queue.mutex:
            queued = set(core.download_queue.queue)
        succeeded = skipped = failed = 0
        outcomes = []
        for task_id in candidates:
            task = core.tasks.get(task_id)
            if not task or not str(task.get("status") or "").startswith("에러"):
                skipped += 1
                outcomes.append({"id": task_id, "result": "skipped"})
                continue
            if task_id in queued:
                skipped += 1
                outcomes.append({"id": task_id, "result": "skipped"})
                continue
            try:
                if mp4_queue_module.has_task(core, task_id):
                    skipped += 1
                    outcomes.append({"id": task_id, "result": "skipped"})
                    continue
                response = retry_callback(task_id)
                body = response[0] if isinstance(response, tuple) else response
                code = response[1] if isinstance(response, tuple) and len(response) > 1 else 200
                data = body.get_json(silent=True) if hasattr(body, "get_json") else None
                if int(code) < 400 and isinstance(data, dict) and data.get("status") == "success":
                    succeeded += 1
                    queued.add(task_id)
                    outcomes.append({"id": task_id, "result": "queued"})
                else:
                    failed += 1
                    outcomes.append({"id": task_id, "result": "failed"})
            except Exception:
                failed += 1
                outcomes.append({"id": task_id, "result": "failed"})

        return {
            "status": "success",
            "succeeded": succeeded,
            "skipped": skipped,
            "failed": failed,
            "results": outcomes[:100],
        }, 200


def install(core, mp4_queue_module=None, safety_module=None):
    if mp4_queue_module is None:
        try:
            mp4_queue_module = importlib.import_module("teddy_mp4_queue")
        except ImportError:
            mp4_queue_module = None
    if safety_module is None:
        try:
            safety_module = importlib.import_module("teddy_download_safety")
        except ImportError:
            safety_module = None
    retry_callback = getattr(core, "_teddy_safe_retry_task", None)

    @core.app.get("/api/downloader/action-token")
    def downloader_action_token():
        token = session.get(CSRF_SESSION_KEY)
        if not isinstance(token, str) or len(token) < 32:
            token = secrets.token_urlsafe(32)
            session[CSRF_SESSION_KEY] = token
        response = jsonify({"token": token})
        response.headers["Cache-Control"] = "no-store"
        return response

    @core.app.post("/api/tasks/retry-failed")
    def retry_failed_tasks():
        if not _csrf_ok():
            return jsonify({"status": "error", "message": "요청 검증에 실패했습니다."}), 403
        if retry_callback is None:
            return jsonify({"status": "error", "message": "안전 재시도 경로를 사용할 수 없습니다."}), 503
        body, code = _bulk_retry(core, retry_callback, mp4_queue_module, safety_module)
        return jsonify(body), code



__all__ = [
    "_bulk_retry",
    "manual_retry",
    "_storage_capacity",
    "install",
]
