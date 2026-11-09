"""Authenticated, fail-closed Downloader administrative actions."""

import hmac
import importlib
import os
import secrets
import shutil
import stat
import json
import uuid
from urllib.parse import urlsplit

import teddy_duplicates
import teddy_ownership
import teddy_routing

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


def _mp4_present(core, module, task_id):
    """Unlike isfile(), distinguish absence from a failed metadata lookup."""
    path = module._job_path(core.DOWNLOAD_DIR, task_id)
    directory = os.path.dirname(path)
    try:
        parent = os.lstat(directory)
    except FileNotFoundError:
        return False
    if not stat.S_ISDIR(parent.st_mode):
        raise RuntimeError("MP4 queue directory is unsafe")
    # Prove the queue can be inspected rather than accepting isfile=False on EACCES.
    with os.scandir(directory):
        pass
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError("MP4 job metadata is unsafe")
    return True


def _bulk_retry(core, retry_callback, mp4_queue_module, safety_module):
    lock = getattr(core, "queue_admission_lock", None)
    if lock is None:
        return {"status": "error", "message": "작업 큐 잠금을 확인할 수 없습니다."}, 503

    if (getattr(safety_module, "_TASK_STATE_LOCK", None) is not lock
            or not callable(getattr(lock, "__enter__", None))
            or not callable(getattr(lock, "__exit__", None))):
        return {"status": "error", "message": "공유 작업 큐 잠금을 확인할 수 없습니다."}, 503
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
        protected_mp4 = {}
        for task_id in candidates:
            stage = core.tasks[task_id].get("mp4_stage")
            if stage not in (None, "", "queued", "running", "failed", "output_ready", "publish_pending"):
                return {"status": "error", "message": "MP4 작업 상태를 확인할 수 없습니다."}, 503
            try:
                occupied = _mp4_present(core, mp4_queue_module, task_id)
                if mp4_queue_module.has_task(core, task_id) is not occupied:
                    raise RuntimeError("MP4 queue state changed")
            except Exception:
                occupied = None
            if type(occupied) is not bool:
                return {"status": "error", "message": "MP4 작업 상태를 확인할 수 없습니다."}, 503
            protected_mp4[task_id] = occupied or bool(stage)
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
                if protected_mp4[task_id] or mp4_queue_module.has_task(core, task_id):
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

    @core.app.post("/api/tasks/<failed_id>/retry-fresh")
    def retry_fresh(failed_id):
        if session.get("teddy_authenticated") is not True:
            return jsonify({"status": "error", "message": "인증이 필요합니다."}), 401
        if not _csrf_ok():
            return jsonify({"status": "error", "message": "요청 검증에 실패했습니다."}), 403
        try:
            if str(uuid.UUID(failed_id)) != failed_id:
                raise ValueError()
        except (ValueError, AttributeError):
            return jsonify({"status": "error", "message": "잘못된 작업 ID입니다."}), 400
        with teddy_duplicates._QUEUE_LOCK:
            with core.queue_admission_lock:
                old = core.tasks.get(failed_id)
                if not isinstance(old, dict):
                    return jsonify({"status": "error", "message": "작업이 없습니다."}), 404
                if not str(old.get("status") or "").startswith("에러") or old.get("engine") != "custom-hls":
                    return jsonify({"status": "error", "message": "실패한 HLS 작업이 아닙니다."}), 409
                url = old.get("url")
                dvd = teddy_ownership.dvd_id_from_supported_url(url) if isinstance(url, str) else None
                try:
                    parsed = urlsplit(url)
                    safe_url = parsed.scheme in ('http', 'https') and parsed.hostname and parsed.username is None and parsed.password is None and parsed.port in (None, 80, 443) and not parsed.fragment
                except (ValueError, TypeError):
                    safe_url = False
                if not dvd or not safe_url or url != url.strip():
                    return jsonify({"status": "error", "message": "원본 식별을 확인할 수 없습니다."}), 409
                try:
                    raw, metadata = core._retry_state_read(core.TASKS_FILE)
                    if metadata is None or json.loads(raw).get(failed_id) != old:
                        raise ValueError("persisted task mismatch")
                    if teddy_ownership.is_owned(dvd):
                        return jsonify({"status": "owned", "message": "이미 보유 중입니다."}), 409
                    key = teddy_duplicates.duplicate_key(url)
                    for tid, other in core.tasks.items():
                        if tid == failed_id:
                            continue
                        if not isinstance(other, dict):
                            raise ValueError("invalid task")
                        if other.get('fresh_retry_of') == failed_id:
                            return jsonify({"status": "duplicate", "message": "새 작업이 이미 있습니다."}), 409
                        if not teddy_duplicates._is_terminal(other) and teddy_duplicates.duplicate_key(other.get('url')) == key:
                            return jsonify({"status": "duplicate", "message": "같은 작품 작업이 있습니다."}), 409
                    _storage_capacity(core, safety_module)
                    safety_module.ensure_download_start_space(core.DOWNLOAD_DIR)
                    new_id = str(uuid.uuid4())
                    if new_id in core.tasks or os.path.lexists(os.path.join(core.DOWNLOAD_DIR, f'.{new_id}.parts')):
                        raise ValueError("new task collision")
                    decision = teddy_routing.resolve(url, override='auto')
                    task = {'url': url, 'status': '대기 중', 'progress': '0%', 'speed_bps': 0,
                            'downloaded_bytes': 0, 'total_bytes_estimate': 0, 'fresh_retry_of': failed_id,
                            'error_kind': 'safety',
                            'network_override': 'auto', 'network_mode': decision['mode'],
                            'network_route_source': decision['source'], 'network_site': decision['site'],
                            'network_fallbacks': 0}
                    core.persist_fresh_task_and_enqueue(new_id, task)
                except Exception:
                    return jsonify({"status": "error", "message": "안전한 작업 등록을 확인할 수 없습니다."}), 503
                return jsonify({"status": "success", "task_id": new_id}), 200

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
    "_storage_capacity",
    "install",
]
