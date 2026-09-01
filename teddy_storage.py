import os
import json
import mimetypes
import posixpath
import shlex
import subprocess
import re
import shutil
import uuid
from urllib.parse import urlparse, quote


_SITE_ALIASES = {
    'youtube.com': 'youtube',
    'youtu.be': 'youtube',
    'youtube-nocookie.com': 'youtube',
    'x.com': 'twitter',
    'twitter.com': 'twitter',
    'vimeo.com': 'vimeo',
    'tiktok.com': 'tiktok',
    'instagram.com': 'instagram',
    'facebook.com': 'facebook',
    'fb.watch': 'facebook',
    'twitch.tv': 'twitch',
    'soundcloud.com': 'soundcloud',
    'dailymotion.com': 'dailymotion',
    'bilibili.com': 'bilibili',
}


class PublishError(RuntimeError):
    pass


def _sanitize_folder(value):
    value = re.sub(r'[^a-z0-9._-]+', '-', str(value or '').lower()).strip('.-_')
    return value[:64] or 'other'


def site_key_for_url(url, custom=False):
    """Return a stable, human-readable site folder for a download URL."""
    if custom:
        return 'missav'

    try:
        host = (urlparse(url).hostname or '').lower().rstrip('.')
    except Exception:
        host = ''
    if host.startswith('www.'):
        host = host[4:]

    if re.search(r'(^|\.)missav\d*\.', host):
        return 'missav'

    for domain, key in _SITE_ALIASES.items():
        if host == domain or host.endswith('.' + domain):
            return key

    parts = [part for part in host.split('.') if part]
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in {'co', 'com', 'net', 'org', 'ac', 'go'}:
        return _sanitize_folder(parts[-3])
    if len(parts) >= 2:
        return _sanitize_folder(parts[-2])
    if parts:
        return _sanitize_folder(parts[0])
    return 'other'


def work_root(core):
    return os.path.realpath(core.DOWNLOAD_DIR)


def public_root(core):
    """Return the user-visible completed-file root.

    Legacy/NAS deployments keep the old single-root behavior when
    TEDDY_FINAL_DIR is unset.  The LXC deployment sets TEDDY_FINAL_DIR=/final,
    while /downloads remains local NVMe work/state storage.
    """
    configured = str(os.environ.get('TEDDY_FINAL_DIR') or '').strip()
    return os.path.realpath(configured or core.DOWNLOAD_DIR)


def ensure_site_dir(core, url, custom=False):
    """Return a local work directory for a site (legacy helper)."""
    key = site_key_for_url(url, custom=custom)
    path = os.path.join(work_root(core), key)
    os.makedirs(path, exist_ok=True)
    return key, path


def ensure_public_site_dir(core, site_key):
    key = _sanitize_folder(site_key)
    root = public_root(core)
    if not os.path.isdir(root):
        raise PublishError(f'완료 저장소가 없습니다: {root}')
    path = os.path.join(root, key)
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as exc:
        raise PublishError(f'완료 저장소 폴더 생성 실패: {exc}') from exc
    return key, path


def relative_public_path(core, path):
    return os.path.relpath(path, public_root(core)).replace(os.sep, '/')


def relative_work_path(core, path):
    root = work_root(core)
    real = os.path.realpath(path)
    try:
        if os.path.commonpath([root, real]) != root:
            raise PublishError('로컬 완료 파일이 작업 디렉터리 밖에 있습니다.')
    except ValueError as exc:
        raise PublishError('로컬 완료 파일 경로를 확인할 수 없습니다.') from exc
    return os.path.relpath(real, root).replace(os.sep, '/')


def _safe_under(root, relative, allow_hidden=False):
    relative = str(relative or '').replace('\\', '/')
    if not relative or relative.startswith('/'):
        return None
    parts = [part for part in relative.split('/') if part not in ('', '.')]
    if not parts or any(part == '..' for part in parts):
        return None
    if not allow_hidden and any(part.startswith('.') for part in parts):
        return None
    root = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(root, *parts))
    try:
        if os.path.commonpath([root, candidate]) != root:
            return None
    except ValueError:
        return None
    return candidate


def _safe_work_path(core, relative):
    return _safe_under(work_root(core), relative, allow_hidden=True)


def _safe_public_path(core, relative):
    return _safe_under(public_root(core), relative, allow_hidden=False)


def _fsync_directory(path):
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _copy_to_partial(source, partial):
    with open(source, 'rb') as src, open(partial, 'wb') as dst:
        shutil.copyfileobj(src, dst, length=8 * 1024 * 1024)
        dst.flush()
        os.fsync(dst.fileno())
    try:
        shutil.copystat(source, partial)
    except OSError:
        pass



def _final_backend():
    raw = str(
        os.environ.get("TEDDY_FINAL_BACKEND")
        or "local"
    ).strip().lower()

    if raw in ("", "local", "filesystem", "fs"):
        return "local"

    if raw == "ssh":
        return "ssh"

    raise PublishError(
        f"지원하지 않는 완료 저장소 방식입니다: {raw}"
    )


def _ssh_storage_config():
    config = {
        "host": str(
            os.environ.get("TEDDY_FINAL_SSH_HOST")
            or ""
        ).strip(),
        "user": str(
            os.environ.get("TEDDY_FINAL_SSH_USER")
            or ""
        ).strip(),
        "key": str(
            os.environ.get("TEDDY_FINAL_SSH_KEY")
            or ""
        ).strip(),
        "known_hosts": str(
            os.environ.get(
                "TEDDY_FINAL_SSH_KNOWN_HOSTS"
            )
            or ""
        ).strip(),
        "root": str(
            os.environ.get("TEDDY_FINAL_REMOTE_ROOT")
            or ""
        ).strip(),
    }

    missing = [
        key
        for key, value in config.items()
        if not value
    ]

    if missing:
        raise PublishError(
            "SSH 완료 저장소 설정 누락: "
            + ", ".join(missing)
        )

    root = posixpath.normpath(
        config["root"]
    )

    if not root.startswith("/") or root == "/":
        raise PublishError(
            "SSH 완료 저장소 root 경로가 잘못되었습니다."
        )

    config["root"] = root
    return config


def _ssh_base_command(config=None):
    config = config or _ssh_storage_config()

    return [
        "ssh",
        "-i",
        config["key"],
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=3",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        (
            "UserKnownHostsFile="
            + config["known_hosts"]
        ),
    ]


def _ssh_target(config=None):
    config = config or _ssh_storage_config()

    return (
        config["user"]
        + "@"
        + config["host"]
    )


def _safe_remote_relative(relative):
    raw = str(
        relative or ""
    ).replace("\\", "/")

    if (
        not raw
        or raw.startswith("/")
        or "\x00" in raw
        or "\n" in raw
        or "\r" in raw
    ):
        return None

    parts = [
        part
        for part in raw.split("/")
        if part not in ("", ".")
    ]

    if (
        not parts
        or any(
            part == ".."
            for part in parts
        )
    ):
        return None

    return "/".join(parts)


def _ssh_remote_path(relative):
    relative = _safe_remote_relative(
        relative
    )

    if not relative:
        raise PublishError(
            "잘못된 원격 완료 파일 경로입니다."
        )

    config = _ssh_storage_config()

    path = posixpath.normpath(
        posixpath.join(
            config["root"],
            relative,
        )
    )

    prefix = (
        config["root"].rstrip("/")
        + "/"
    )

    if not path.startswith(prefix):
        raise PublishError(
            "원격 완료 파일이 저장소 밖을 가리킵니다."
        )

    return path


def _ssh_run(remote_command):
    config = _ssh_storage_config()

    command = (
        _ssh_base_command(config)
        + [
            _ssh_target(config),
            remote_command,
        ]
    )

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        detail = str(
            result.stderr or ""
        ).strip()

        raise PublishError(
            "SSH 완료 저장소 명령 실패"
            + (
                ": " + detail[-500:]
                if detail
                else ""
            )
        )

    return result


def _ssh_remote_stat(relative):
    path = _ssh_remote_path(
        relative
    )
    quoted = shlex.quote(path)

    command = (
        "if [ -f "
        + quoted
        + " ] && [ ! -L "
        + quoted
        + " ]; then "
        + "stat -c "
        + shlex.quote("%s %Y")
        + " "
        + quoted
        + "; "
        + "elif [ -e "
        + quoted
        + " ] || [ -L "
        + quoted
        + " ]; then "
        + "printf "
        + shlex.quote("__INVALID__")
        + "; "
        + "else printf "
        + shlex.quote("__MISSING__")
        + "; fi"
    )

    result = _ssh_run(command)

    raw = str(
        result.stdout or ""
    ).strip()

    if raw == "__MISSING__":
        return None

    if raw == "__INVALID__":
        raise PublishError(
            "원격 완료 경로가 일반 파일이 아닙니다."
        )

    parts = raw.split()

    if len(parts) != 2:
        raise PublishError(
            "원격 완료 파일 상태를 해석할 수 없습니다."
        )

    try:
        return {
            "size": int(parts[0]),
            "modified": int(parts[1]),
        }
    except ValueError as exc:
        raise PublishError(
            "원격 완료 파일 상태 값이 잘못되었습니다."
        ) from exc


def _ssh_ensure_site_dir(site_key):
    key = _sanitize_folder(
        site_key
    )

    config = _ssh_storage_config()

    root = shlex.quote(
        config["root"]
    )

    path = _ssh_remote_path(
        key
    )
    quoted = shlex.quote(
        path
    )

    _ssh_run(
        "test -d "
        + root
        + " && "
        + "test ! -L "
        + root
        + " && "
        + "mkdir -p "
        + quoted
        + " && "
        + "test -d "
        + quoted
        + " && "
        + "test ! -L "
        + quoted
    )

    return key


def _ssh_publish_completed_file(
    core,
    source_path,
    site_key,
):
    source = os.path.realpath(
        source_path
    )
    work = work_root(core)

    try:
        if (
            os.path.commonpath(
                [work, source]
            )
            != work
        ):
            raise PublishError(
                "게시 원본이 로컬 작업 디렉터리 밖에 있습니다."
            )
    except ValueError as exc:
        raise PublishError(
            "게시 원본 경로를 확인할 수 없습니다."
        ) from exc

    if not os.path.isfile(source):
        raise PublishError(
            f"로컬 완료 파일이 없습니다: {source}"
        )

    key = _ssh_ensure_site_dir(
        site_key
    )

    filename = os.path.basename(
        source
    )

    if (
        not filename
        or filename.startswith(".")
        or filename in (".", "..")
    ):
        raise PublishError(
            "완료 파일 이름이 잘못되었습니다."
        )

    relative = (
        key
        + "/"
        + filename
    )

    partial_relative = (
        key
        + "/."
        + filename
        + ".teddy-partial"
    )

    final_path = _ssh_remote_path(
        relative
    )

    partial_path = _ssh_remote_path(
        partial_relative
    )

    config = _ssh_storage_config()

    ssh_shell = shlex.join(
        _ssh_base_command(config)
    )

    remote_target = (
        _ssh_target(config)
        + ":"
        + partial_path
    )

    source_size = os.path.getsize(
        source
    )

    command = [
        "rsync",
        "--partial",
        "--append-verify",
        "--protect-args",
        "-e",
        ssh_shell,
        source,
        remote_target,
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        detail = str(
            result.stderr or ""
        ).strip()

        # Keep the hidden partial file so a later retry
        # can resume rather than restarting a large copy.
        raise PublishError(
            "rsync 완료 파일 전송 실패"
            + (
                ": " + detail[-500:]
                if detail
                else ""
            )
        )

    partial_stat = _ssh_remote_stat(
        partial_relative
    )

    if (
        not partial_stat
        or partial_stat["size"]
        != source_size
    ):
        raise PublishError(
            "rsync 후 원격 파일 크기 검증에 실패했습니다."
        )

    _ssh_run(
        "mv -f "
        + shlex.quote(partial_path)
        + " "
        + shlex.quote(final_path)
    )

    final_stat = _ssh_remote_stat(
        relative
    )

    if (
        not final_stat
        or final_stat["size"]
        != source_size
    ):
        raise PublishError(
            "원격 최종 파일 크기 검증에 실패했습니다."
        )

    # Local source is removed only after remote
    # transfer, size verification and final rename.
    os.remove(source)

    return (
        relative,
        final_stat["size"],
    )


def publish_completed_file(core, source_path, site_key):
    """Publish one fully finished local file to the completed-file root.

    Same-filesystem deployments use os.replace directly.  Cross-filesystem
    deployments (local NVMe -> NAS NFS) copy to a hidden partial file first and
    only then rename inside the final filesystem.  The local source is removed
    only after the final rename succeeds.
    """
    source = os.path.realpath(source_path)
    root = work_root(core)
    try:
        if os.path.commonpath([root, source]) != root:
            raise PublishError('게시 원본이 로컬 작업 디렉터리 밖에 있습니다.')
    except ValueError as exc:
        raise PublishError('게시 원본 경로를 확인할 수 없습니다.') from exc
    if not os.path.isfile(source):
        raise PublishError(f'로컬 완료 파일이 없습니다: {source}')

    _key, final_dir = ensure_public_site_dir(core, site_key)
    destination = os.path.join(final_dir, os.path.basename(source))
    if os.path.realpath(destination) == source:
        return destination

    try:
        same_filesystem = os.stat(source).st_dev == os.stat(final_dir).st_dev
    except OSError as exc:
        raise PublishError(f'저장소 상태 확인 실패: {exc}') from exc

    if same_filesystem:
        try:
            os.replace(source, destination)
            return destination
        except OSError as exc:
            raise PublishError(f'완료 파일 이동 실패: {exc}') from exc

    partial = os.path.join(
        final_dir,
        f'.{os.path.basename(source)}.{uuid.uuid4().hex}.partial',
    )
    try:
        _copy_to_partial(source, partial)
        if os.path.getsize(partial) != os.path.getsize(source):
            raise PublishError('NAS 복사 후 파일 크기 검증에 실패했습니다.')
        os.replace(partial, destination)
        _fsync_directory(final_dir)
        os.remove(source)
        return destination
    except PublishError:
        try:
            os.remove(partial)
        except OSError:
            pass
        raise
    except OSError as exc:
        try:
            os.remove(partial)
        except OSError:
            pass
        raise PublishError(f'NAS 완료 파일 게시 실패: {exc}') from exc


def has_pending_result(core, task_id):
    task = core.tasks.get(task_id) or {}
    return bool(task.get('local_result_path'))


def _pending_paths(task):
    main = str(task.get('local_result_path') or '').strip()
    raw = task.get('local_result_paths')
    paths = []
    if isinstance(raw, list):
        for value in raw:
            value = str(value or '').strip()
            if value and value not in paths:
                paths.append(value)
    if main and main not in paths:
        paths.append(main)
    if main in paths:
        paths = [value for value in paths if value != main] + [main]
    return main, paths


def publish_pending_task(core, task_id):
    # Downloads may run concurrently, but final-storage publication is serialized.
    # The lock file is local to the container and never lives on NAS.
    import fcntl

    lock_path = str(
        os.environ.get("TEDDY_PUBLISH_LOCK_PATH")
        or "/tmp/teddy-nas-publish.lock"
    )
    lock_fd = None

    print(f"[Storage] NAS 게시 대기: {task_id}", flush=True)

    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
    except OSError as exc:
        if lock_fd is not None:
            try:
                os.close(lock_fd)
            except OSError:
                pass
        raise PublishError(f"NAS 게시 직렬화 잠금 실패: {exc}") from exc

    try:
        print(f"[Storage] NAS 게시 시작: {task_id}", flush=True)
        return _publish_pending_task_unlocked(core, task_id)
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(lock_fd)
        except OSError:
            pass



def _publish_pending_task_ssh(core, task_id):
    """Publish completed task outputs through rsync over SSH."""
    task = core.tasks.get(task_id)

    if not task:
        raise PublishError(
            "작업이 없습니다."
        )

    main_rel, paths = _pending_paths(
        task
    )

    if not main_rel or not paths:
        raise PublishError(
            "게시할 로컬 완료 결과가 없습니다."
        )

    site_key = _sanitize_folder(
        str(
            task.get("storage_folder")
            or "other"
        )
    )

    published_main = ""
    published_main_size = 0
    local_parents = set()

    for relative in paths:
        source = _safe_work_path(
            core,
            relative,
        )

        if not source:
            raise PublishError(
                "잘못된 로컬 완료 경로입니다: "
                + str(relative)
            )

        local_parents.add(
            os.path.dirname(source)
        )

        remote_relative = (
            site_key
            + "/"
            + os.path.basename(source)
        )

        if os.path.isfile(source):
            (
                published_relative,
                published_size,
            ) = _ssh_publish_completed_file(
                core,
                source,
                site_key,
            )
        else:
            # Crash recovery:
            # remote final rename may have completed
            # just before task state was saved.
            remote_stat = _ssh_remote_stat(
                remote_relative
            )

            if not remote_stat:
                raise PublishError(
                    "로컬/원격 완료 파일을 찾을 수 없습니다: "
                    + str(relative)
                )

            published_relative = (
                remote_relative
            )
            published_size = (
                remote_stat["size"]
            )

        if relative == main_rel:
            published_main = (
                published_relative
            )
            published_main_size = (
                published_size
            )

    if not published_main:
        raise PublishError(
            "주 완료 파일 게시 결과를 확인하지 못했습니다."
        )

    task["status"] = "완료"
    task["progress"] = "100%"
    task["speed_bps"] = 0
    task["filename"] = published_main
    task["filesize"] = published_main_size
    task["downloaded_bytes"] = (
        published_main_size
    )
    task["total_bytes_estimate"] = (
        published_main_size
    )

    task.pop(
        "local_result_path",
        None,
    )
    task.pop(
        "local_result_paths",
        None,
    )
    task.pop(
        "last_error_detail",
        None,
    )

    core.save_tasks()

    work = work_root(core)

    for parent in sorted(
        local_parents,
        key=len,
        reverse=True,
    ):
        if parent == work:
            continue

        try:
            if (
                os.path.commonpath(
                    [work, parent]
                )
                == work
                and os.path.basename(
                    parent
                ).startswith(".")
            ):
                os.rmdir(parent)
        except (OSError, ValueError):
            pass

    return published_main


def _publish_pending_task_unlocked(core, task_id):
    """Publish every completed local output for a task, main media last."""
    if _final_backend() == "ssh":
        return _publish_pending_task_ssh(
            core,
            task_id,
        )

    task = core.tasks.get(task_id)
    if not task:
        raise PublishError('작업이 없습니다.')
    main_rel, paths = _pending_paths(task)
    if not main_rel or not paths:
        raise PublishError('게시할 로컬 완료 결과가 없습니다.')

    site_key = str(task.get('storage_folder') or 'other')
    _key, final_dir = ensure_public_site_dir(core, site_key)
    published_main = ''
    local_parents = set()

    for relative in paths:
        source = _safe_work_path(core, relative)
        if not source:
            raise PublishError(f'잘못된 로컬 완료 경로입니다: {relative}')
        local_parents.add(os.path.dirname(source))
        destination = os.path.join(final_dir, os.path.basename(source))
        if os.path.isfile(source):
            published = publish_completed_file(core, source, site_key)
        elif os.path.isfile(destination):
            # Crash recovery: the NAS rename may have completed just before the
            # task state was persisted.  Treat the already-present final file as
            # published instead of downloading it again.
            published = destination
        else:
            raise PublishError(f'로컬/최종 완료 파일을 찾을 수 없습니다: {relative}')
        if relative == main_rel:
            published_main = published

    if not published_main:
        raise PublishError('주 완료 파일 게시 결과를 확인하지 못했습니다.')

    final_size = os.path.getsize(published_main)
    task['status'] = '완료'
    task['progress'] = '100%'
    task['speed_bps'] = 0
    task['filename'] = relative_public_path(core, published_main)
    task['filesize'] = final_size
    task['downloaded_bytes'] = final_size
    task['total_bytes_estimate'] = final_size
    task.pop('local_result_path', None)
    task.pop('local_result_paths', None)
    task.pop('last_error_detail', None)
    core.save_tasks()

    work = work_root(core)
    for parent in sorted(local_parents, key=len, reverse=True):
        if parent == work:
            continue
        try:
            if os.path.commonpath([work, parent]) == work and os.path.basename(parent).startswith('.'):
                os.rmdir(parent)
        except (OSError, ValueError):
            pass
    return published_main


def mark_publish_error(core, task_id, exc):
    message = str(exc or 'unknown storage error')
    task = core.tasks.get(task_id)
    if task:
        task['status'] = f'에러: NAS 저장 실패: {message[:80]}'
        task['progress'] = '99%'
        task['speed_bps'] = 0
        task['last_error_detail'] = f'완료 파일 게시 실패: {message}'[:1000]
        core.save_tasks()
    print(f'[Storage] 완료 파일 게시 실패: {message}', flush=True)
    return {
        'status': 'error',
        'error': f'완료 저장소 게시 실패: {message}',
        'error_kind': 'storage',
    }


def cleanup_local_results(core, task):
    _main, paths = _pending_paths(task or {})
    for relative in paths:
        path = _safe_work_path(core, relative)
        if not path or not os.path.isfile(path):
            continue
        try:
            os.remove(path)
        except OSError:
            pass



def _ssh_list_files():
    config = _ssh_storage_config()

    script = r"""
import json
import os
import sys

root = sys.argv[1]
items = []

def ignored(name):
    return (
        name.startswith(".")
        or name == "@eaDir"
    )

with os.scandir(root) as entries:
    for entry in entries:
        name = entry.name

        if ignored(name):
            continue

        if entry.is_symlink():
            continue

        if entry.is_file(follow_symlinks=False):
            stat = entry.stat(follow_symlinks=False)
            items.append({
                "name": name,
                "size": stat.st_size,
                "modified": stat.st_mtime,
            })
            continue

        if not entry.is_dir(follow_symlinks=False):
            continue

        site = name

        with os.scandir(entry.path) as children:
            for child in children:
                child_name = child.name

                if ignored(child_name):
                    continue

                if child.is_symlink():
                    continue

                if not child.is_file(follow_symlinks=False):
                    continue

                stat = child.stat(follow_symlinks=False)

                items.append({
                    "name": site + "/" + child_name,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                })

items.sort(
    key=lambda item: item["modified"],
    reverse=True,
)

print(
    json.dumps(
        items,
        ensure_ascii=False,
        separators=(",", ":"),
    )
)
"""

    command = (
        _ssh_base_command(config)
        + [
            _ssh_target(config),
            (
                "python3 - "
                + shlex.quote(config["root"])
            ),
        ]
    )

    result = subprocess.run(
        command,
        input=script,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        detail = str(
            result.stderr or ""
        ).strip()

        raise PublishError(
            "SSH 완료 파일 목록 조회 실패"
            + (
                ": " + detail[-500:]
                if detail
                else ""
            )
        )

    try:
        items = json.loads(
            result.stdout or "[]"
        )
    except json.JSONDecodeError as exc:
        raise PublishError(
            "SSH 완료 파일 목록을 해석할 수 없습니다."
        ) from exc

    if not isinstance(items, list):
        raise PublishError(
            "SSH 완료 파일 목록 형식이 잘못되었습니다."
        )

    return items



def _safe_remote_public_relative(relative):
    safe = _safe_remote_relative(
        relative
    )

    if not safe:
        return None

    parts = safe.split("/")

    if any(
        part.startswith(".")
        or part == "@eaDir"
        for part in parts
    ):
        return None

    return safe


def _ssh_delete_file(relative):
    relative = _safe_remote_public_relative(
        relative
    )

    if not relative:
        raise ValueError(
            "잘못된 파일 경로입니다."
        )

    stat = _ssh_remote_stat(
        relative
    )

    if stat is None:
        return False

    path = _ssh_remote_path(
        relative
    )

    config = _ssh_storage_config()
    root = config["root"]

    parent = posixpath.dirname(
        path
    )

    command = (
        "rm -f "
        + shlex.quote(path)
    )

    if parent != root:
        command += (
            "; rmdir "
            + shlex.quote(parent)
            + " 2>/dev/null || true"
        )

    _ssh_run(command)

    if _ssh_remote_stat(relative) is not None:
        raise PublishError(
            "원격 완료 파일 삭제 확인에 실패했습니다."
        )

    return True



def _parse_single_byte_range(value, size):
    size = int(size)

    if value is None:
        return None

    raw = str(value).strip()

    if not raw:
        return None

    if not raw.lower().startswith("bytes="):
        raise ValueError(
            "unsupported range unit"
        )

    spec = raw[len("bytes="):].strip()

    if (
        not spec
        or "," in spec
        or "-" not in spec
    ):
        raise ValueError(
            "invalid range"
        )

    if size <= 0:
        raise ValueError(
            "range on empty file"
        )

    first, last = spec.split("-", 1)

    first = first.strip()
    last = last.strip()

    if not first:
        if (
            not last.isdigit()
            or int(last) <= 0
        ):
            raise ValueError(
                "invalid suffix range"
            )

        suffix = int(last)
        length = min(suffix, size)

        return (
            size - length,
            size - 1,
        )

    if not first.isdigit():
        raise ValueError(
            "invalid range start"
        )

    start = int(first)

    if start >= size:
        raise ValueError(
            "range start beyond body"
        )

    if not last:
        return (
            start,
            size - 1,
        )

    if not last.isdigit():
        raise ValueError(
            "invalid range end"
        )

    end = int(last)

    if end < start:
        raise ValueError(
            "range end before start"
        )

    return (
        start,
        min(end, size - 1),
    )


def _ssh_media_process(
    relative,
    start,
    length,
):
    relative = _safe_remote_public_relative(
        relative
    )

    if not relative:
        raise ValueError(
            "잘못된 파일 경로입니다."
        )

    start = int(start)

    if start < 0:
        raise ValueError(
            "잘못된 스트림 시작 위치입니다."
        )

    if length is not None:
        length = int(length)

        if length < 0:
            raise ValueError(
                "잘못된 스트림 길이입니다."
            )

    path = _ssh_remote_path(
        relative
    )

    remote_command = (
        "tail -c +"
        + str(start + 1)
        + " "
        + shlex.quote(path)
    )

    if length is not None:
        remote_command += (
            " | head -c "
            + str(length)
        )

    config = _ssh_storage_config()

    command = (
        _ssh_base_command(config)
        + [
            _ssh_target(config),
            remote_command,
        ]
    )

    try:
        return subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
    except OSError as exc:
        raise PublishError(
            "SSH 완료 파일 스트림 시작 실패: "
            + str(exc)
        ) from exc


def _ssh_media_chunks(
    process,
    expected_length,
):
    remaining = int(
        expected_length
    )

    if remaining < 0:
        raise ValueError(
            "잘못된 예상 스트림 길이입니다."
        )

    completed = False

    try:
        while remaining > 0:
            if process.stdout is None:
                break

            chunk = process.stdout.read(
                min(
                    1024 * 1024,
                    remaining,
                )
            )

            if not chunk:
                break

            remaining -= len(chunk)
            yield chunk

        completed = (
            remaining == 0
        )

    finally:
        if process.stdout is not None:
            try:
                process.stdout.close()
            except OSError:
                pass

        if process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass

        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except OSError:
                pass

            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass

    if not completed:
        raise PublishError(
            "SSH 완료 파일 스트림 길이가 예상보다 짧습니다."
        )



def _ssh_file_response(
    core,
    filename,
    *,
    as_attachment=False,
):
    relative = _safe_remote_public_relative(
        filename
    )

    if not relative:
        return core.Response(
            status=400
        )

    try:
        stat = _ssh_remote_stat(
            relative
        )
    except PublishError:
        return core.Response(
            status=503
        )

    if stat is None:
        return core.Response(
            status=404
        )

    size = int(
        stat["size"]
    )

    range_value = core.request.headers.get(
        "Range"
    )

    try:
        byte_range = _parse_single_byte_range(
            range_value,
            size,
        )
    except ValueError:
        response = core.Response(
            b"",
            status=416,
        )

        response.headers[
            "Accept-Ranges"
        ] = "bytes"

        response.headers[
            "Content-Range"
        ] = (
            "bytes */"
            + str(size)
        )

        response.headers[
            "Content-Length"
        ] = "0"

        return response

    if byte_range is None:
        start = 0
        end = (
            size - 1
            if size > 0
            else -1
        )
        length = size
        status = 200
    else:
        start, end = byte_range
        length = end - start + 1
        status = 206

    content_type = (
        mimetypes.guess_type(
            relative
        )[0]
        or "application/octet-stream"
    )

    method = str(
        core.request.method or "GET"
    ).upper()

    if (
        method == "HEAD"
        or length == 0
    ):
        body = b""
    else:
        try:
            process = _ssh_media_process(
                relative,
                start,
                length,
            )
        except (
            PublishError,
            ValueError,
        ):
            return core.Response(
                status=503
            )

        body = _ssh_media_chunks(
            process,
            length,
        )

    response = core.Response(
        body,
        status=status,
        content_type=content_type,
    )

    response.headers[
        "Accept-Ranges"
    ] = "bytes"

    response.headers[
        "Content-Length"
    ] = str(length)

    response.headers[
        "Cache-Control"
    ] = "private, no-cache"

    response.headers[
        "X-Content-Type-Options"
    ] = "nosniff"

    if status == 206:
        response.headers[
            "Content-Range"
        ] = (
            "bytes "
            + str(start)
            + "-"
            + str(end)
            + "/"
            + str(size)
        )

    if as_attachment:
        basename = posixpath.basename(
            relative
        )

        encoded = quote(
            basename,
            safe="",
        )

        response.headers[
            "Content-Disposition"
        ] = (
            "attachment; "
            "filename*=UTF-8''"
            + encoded
        )

    return response


def _recursive_files(core):
    items = []
    root = public_root(core)
    if not os.path.isdir(root):
        return items

    for current, dirs, files in os.walk(root):
        dirs[:] = [name for name in dirs if not name.startswith('.')]
        for name in files:
            if name.startswith('.'):
                continue
            path = os.path.join(current, name)
            if not os.path.isfile(path):
                continue
            try:
                stat = os.stat(path)
            except OSError:
                continue
            items.append({
                'name': relative_public_path(core, path),
                'size': stat.st_size,
                'modified': stat.st_mtime,
            })
    items.sort(key=lambda item: item['modified'], reverse=True)
    return items


def install_file_routes(core):
    """Make the existing file manager recursive and safe for site subfolders."""
    def list_files_recursive():
        try:
            if _final_backend() == "ssh":
                return core.jsonify(_ssh_list_files())
            return core.jsonify(_recursive_files(core))
        except PublishError as exc:
            return core.jsonify({
                "status": "error",
                "message": str(exc),
            }), 503

    if 'list_files' in core.app.view_functions:
        core.app.view_functions['list_files'] = list_files_recursive

    def delete_file_nested(filename):
        if _final_backend() == "ssh":
            try:
                relative = _safe_remote_public_relative(filename)
                if not relative:
                    return core.jsonify({
                        "status": "error",
                        "message": "잘못된 파일 경로입니다.",
                    }), 400

                deleted = _ssh_delete_file(relative)

                if not deleted:
                    return core.jsonify({
                        "status": "error",
                        "message": "파일이 없습니다.",
                    }), 404

                return core.jsonify({
                    "status": "success",
                    "message": "파일을 삭제했습니다.",
                })
            except PublishError as exc:
                return core.jsonify({
                    "status": "error",
                    "message": f"파일 삭제 실패: {exc}",
                }), 503

        path = _safe_public_path(core, filename)
        if not path:
            return core.jsonify({'status': 'error', 'message': '잘못된 파일 경로입니다.'}), 400
        if not os.path.isfile(path):
            return core.jsonify({'status': 'error', 'message': '파일이 없습니다.'}), 404
        try:
            os.remove(path)
            parent = os.path.dirname(path)
            root = public_root(core)
            while parent != root and os.path.commonpath([root, parent]) == root:
                try:
                    os.rmdir(parent)
                except OSError:
                    break
                parent = os.path.dirname(parent)
            return core.jsonify({'status': 'success', 'message': '파일을 삭제했습니다.'})
        except OSError as exc:
            return core.jsonify({'status': 'error', 'message': f'파일 삭제 실패: {exc}'}), 500

    if 'delete_file' in core.app.view_functions:
        core.app.view_functions['delete_file'] = delete_file_nested

    def download_file_nested(filename):
        if _final_backend() == "ssh":
            return _ssh_file_response(
                core,
                filename,
                as_attachment=True,
            )

        path = _safe_public_path(core, filename)
        if not path:
            return core.Response(status=400)
        if not os.path.isfile(path):
            return core.Response(status=404)
        return core.send_file(path, as_attachment=True, download_name=os.path.basename(path), conditional=True)

    def stream_file_nested(filename):
        if _final_backend() == "ssh":
            return _ssh_file_response(
                core,
                filename,
                as_attachment=False,
            )

        path = _safe_public_path(core, filename)
        if not path:
            return core.Response(status=400)
        if not os.path.isfile(path):
            return core.Response(status=404)
        return core.send_file(path, conditional=True)

    existing_rules = {rule.rule for rule in core.app.url_map.iter_rules()}
    if '/api/files/<path:filename>/download' not in existing_rules:
        core.app.add_url_rule(
            '/api/files/<path:filename>/download',
            endpoint='teddy_download_file',
            view_func=download_file_nested,
            methods=['GET'],
        )
    if '/api/files/<path:filename>/stream' not in existing_rules:
        core.app.add_url_rule(
            '/api/files/<path:filename>/stream',
            endpoint='teddy_stream_file',
            view_func=stream_file_nested,
            methods=['GET'],
        )

    original_delete_task = core.app.view_functions.get('delete_task')
    if original_delete_task:
        def delete_task_with_local_cleanup(task_id):
            task = core.tasks.get(task_id)
            active = task and task.get('status') in ('다운로드 중', '일시정지 요청 중', '대기 중')
            if task and not active:
                cleanup_local_results(core, task)
            return original_delete_task(task_id)
        core.app.view_functions['delete_task'] = delete_task_with_local_cleanup

    print(
        f'[Teddy] site-aware storage enabled: work={work_root(core)} '
        f'final={public_root(core)}',
        flush=True,
    )
