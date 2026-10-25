from __future__ import annotations

from pathlib import PurePosixPath
import hashlib
import json
import shlex
import struct
import subprocess

from teddy_discovery_media_metadata import (
    MediaBundle,
)


class MediaMetadataPublishError(
    RuntimeError
):
    pass


VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".webm",
    ".m4v",
}

POSTER_FILENAMES = frozenset(
    {
        "poster.jpg",
        "poster.png",
        "poster.webp",
    }
)

LIBRARY_SIDECAR_FILENAMES = frozenset(
    {
        "movie.nfo",
        *POSTER_FILENAMES,
    }
)

CANONICAL_TEXT_SUBTITLE_LANGUAGES = frozenset(
    {
        "ja",
        "jpn",
        "japanese",
        "en",
        "eng",
        "english",
    }
)

CANONICAL_TEXT_SUBTITLE_FORMATS = frozenset(
    {
        "srt",
        "vtt",
    }
)


def canonical_nfo_filename(dvd_id):
    return str(dvd_id).strip().upper() + ".nfo"


def canonical_ko_subtitle_filename(dvd_id):
    return str(dvd_id).strip().upper() + ".ko.srt"


def is_canonical_text_subtitle_filename(filename, dvd_id):
    """Recognize only sibling text names usable by frozen Stage11 Slice 1."""

    if not isinstance(filename, str):
        return False

    canonical_dvd_id = str(dvd_id).strip().upper()
    prefix = canonical_dvd_id + "."

    if not filename.startswith(prefix):
        return False

    parts = filename[len(prefix):].split(".")

    if len(parts) != 2:
        return False

    language, text_format = parts

    return (
        language.lower() in CANONICAL_TEXT_SUBTITLE_LANGUAGES
        and text_format.lower() in CANONICAL_TEXT_SUBTITLE_FORMATS
    )


def is_library_sidecar(filename, dvd_id):
    return (
        filename == canonical_nfo_filename(dvd_id)
        or filename == canonical_ko_subtitle_filename(dvd_id)
        or is_canonical_text_subtitle_filename(
            filename,
            dvd_id,
        )
        or filename in LIBRARY_SIDECAR_FILENAMES
    )


REMOTE_PUBLISH_SCRIPT = r'''
import hashlib
import json
import os
import stat
import struct
import sys
import uuid


MAX_NFO = 2 * 1024 * 1024
MAX_POSTER = 25 * 1024 * 1024

root = os.path.realpath(
    sys.argv[1]
)

video_relative = sys.argv[2]
nfo_name = sys.argv[3]
poster_name = sys.argv[4]
expected_nfo_sha = sys.argv[5]
expected_poster_sha = sys.argv[6]


def inside(path, root):
    prefix = (
        root.rstrip(os.sep)
        + os.sep
    )

    return (
        path == root
        or path.startswith(prefix)
    )


header = sys.stdin.buffer.read(16)

if len(header) != 16:
    raise SystemExit(
        "invalid metadata payload header"
    )

nfo_size, poster_size = (
    struct.unpack(
        ">QQ",
        header,
    )
)

if (
    nfo_size < 1
    or nfo_size > MAX_NFO
):
    raise SystemExit(
        "invalid nfo size"
    )

if poster_size > MAX_POSTER:
    raise SystemExit(
        "invalid poster size"
    )

payload = sys.stdin.buffer.read(
    nfo_size + poster_size
)

if len(payload) != (
    nfo_size + poster_size
):
    raise SystemExit(
        "truncated metadata payload"
    )

if sys.stdin.buffer.read(1):
    raise SystemExit(
        "unexpected trailing payload"
    )

nfo_data = payload[:nfo_size]
poster_data = payload[nfo_size:]

if (
    hashlib.sha256(
        nfo_data
    ).hexdigest()
    != expected_nfo_sha
):
    raise SystemExit(
        "nfo payload hash mismatch"
    )

if poster_size and (
    hashlib.sha256(poster_data).hexdigest()
    != expected_poster_sha
):
    raise SystemExit(
        "poster payload hash mismatch"
    )


video_parts = video_relative.split("/")
if (
    not video_relative
    or video_relative.startswith("/")
    or "\\" in video_relative
    or any(part in {"", ".", ".."} for part in video_parts)
):
    raise SystemExit(
        "invalid video relative path"
    )

video = os.path.join(
    root,
    *video_parts,
)
video_real = os.path.realpath(video)
if not inside(video_real, root) or video_real != video:
    raise SystemExit(
        "video path is unsafe"
    )

current = root
for index, part in enumerate(video_parts):
    current = os.path.join(current, part)
    try:
        component_stat = os.stat(
            current,
            follow_symlinks=False,
        )
    except OSError as exc:
        raise SystemExit(
            "video path component is unavailable"
        ) from exc

    if stat.S_ISLNK(component_stat.st_mode):
        raise SystemExit(
            "video path contains a symlink"
        )

    is_video = index == len(video_parts) - 1
    if is_video and not stat.S_ISREG(component_stat.st_mode):
        raise SystemExit(
            "video is not a regular file"
        )
    if not is_video and not stat.S_ISDIR(component_stat.st_mode):
        raise SystemExit(
            "video parent is not a directory"
        )

video_stat = os.stat(
    video,
    follow_symlinks=False,
)

if (
    not stat.S_ISREG(video_stat.st_mode)
    or video_stat.st_uid != os.geteuid()
):
    raise SystemExit(
        "video ownership or file type mismatch"
    )

parent = os.path.dirname(
    video_real
)


def publish_one(
    name,
    data,
    expected_sha,
):
    if (
        not name
        or os.path.basename(name)
        != name
        or name.startswith(".")
    ):
        raise RuntimeError(
            "invalid metadata filename"
        )

    target = os.path.join(
        parent,
        name,
    )

    if os.path.lexists(target):
        if os.path.islink(target):
            raise RuntimeError(
                "metadata target is unsafe"
            )

        target_stat = os.stat(target, follow_symlinks=False)
        if (
            not stat.S_ISREG(target_stat.st_mode)
            or target_stat.st_uid != video_stat.st_uid
        ):
            raise RuntimeError(
                "metadata ownership or file type mismatch"
            )

        with open(
            target,
            "rb",
        ) as handle:
            existing = handle.read(
                len(data) + 1
            )

        if (
            len(existing) == len(data)
            and hashlib.sha256(
                existing
            ).hexdigest()
            == expected_sha
        ):
            return {
                "status":
                    "ALREADY_PRESENT",
                "size":
                    len(existing),
                "sha256":
                    expected_sha,
            }

        raise RuntimeError(
            "metadata collision"
        )

    partial = os.path.join(
        parent,
        "."
        + name
        + ".teddy-stage9-meta-"
        + uuid.uuid4().hex
        + ".partial",
    )

    linked = False

    try:
        with open(
            partial,
            "xb",
        ) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(
                handle.fileno()
            )

        partial_stat = os.stat(
            partial,
            follow_symlinks=False,
        )

        if (
            not stat.S_ISREG(partial_stat.st_mode)
            or partial_stat.st_uid != video_stat.st_uid
            or int(partial_stat.st_size) != len(data)
        ):
            raise RuntimeError(
                "partial ownership, file type, or size mismatch"
            )

        with open(
            partial,
            "rb",
        ) as handle:
            written_sha = (
                hashlib.sha256(
                    handle.read()
                ).hexdigest()
            )

        if written_sha != expected_sha:
            raise RuntimeError(
                "partial hash mismatch"
            )

        try:
            os.link(
                partial,
                target,
            )

            linked = True

        except FileExistsError:
            if os.path.islink(target):
                raise RuntimeError(
                    "metadata target appeared unsafe"
                )

            target_stat = os.stat(target, follow_symlinks=False)
            if (
                not stat.S_ISREG(target_stat.st_mode)
                or target_stat.st_uid != video_stat.st_uid
            ):
                raise RuntimeError(
                    "metadata target ownership or file type mismatch"
                )

            with open(
                target,
                "rb",
            ) as handle:
                existing = handle.read(
                    len(data) + 1
                )

            if (
                len(existing) == len(data)
                and hashlib.sha256(
                    existing
                ).hexdigest()
                == expected_sha
            ):
                return {
                    "status":
                        "ALREADY_PRESENT",
                    "size":
                        len(existing),
                    "sha256":
                        expected_sha,
                }

            raise RuntimeError(
                "metadata target appeared"
            )

        os.unlink(
            partial
        )

        directory_fd = os.open(
            parent,
            os.O_RDONLY,
        )

        try:
            os.fsync(
                directory_fd
            )
        finally:
            os.close(
                directory_fd
            )

        with open(
            target,
            "rb",
        ) as handle:
            final_data = handle.read()

        if (
            os.stat(target, follow_symlinks=False).st_uid != video_stat.st_uid
            or len(final_data) != len(data)
            or hashlib.sha256(
                final_data
            ).hexdigest()
            != expected_sha
        ):
            raise RuntimeError(
                "published metadata verification failed"
            )

        return {
            "status": "CREATED",
            "size": len(final_data),
            "sha256": expected_sha,
        }

    finally:
        if os.path.exists(
            partial
        ):
            try:
                os.unlink(
                    partial
                )
            except OSError:
                pass


nfo_result = publish_one(
    nfo_name,
    nfo_data,
    expected_nfo_sha,
)

if poster_size:
    try:
        poster_result = publish_one(
            poster_name,
            poster_data,
            expected_poster_sha,
        )
        result_status = "METADATA_READY"
    except Exception as exc:
        poster_result = {
            "status": "ATTENTION",
            "error": str(exc)[:500],
        }
        result_status = "METADATA_PARTIAL"
else:
    poster_result = {
        "status": "NOT_ATTEMPTED",
    }
    result_status = "NFO_READY"

print(
    json.dumps(
        {
            "status": result_status,
            "nfo":
                nfo_result,
            "poster":
                poster_result,
        }
    )
)
'''


def _safe_video_relative(
    value: str,
    dvd_id: str,
) -> str:
    raw = str(value or "")

    if "\\" in raw:
        raise MediaMetadataPublishError(
            "invalid video relative path"
        )

    path = PurePosixPath(
        raw
    )

    if (
        path.is_absolute()
        or not path.parts
        or ".." in path.parts
    ):
        raise MediaMetadataPublishError(
            "invalid video relative path"
        )

    if (
        path.suffix.lower()
        not in VIDEO_EXTENSIONS
    ):
        raise MediaMetadataPublishError(
            "unsupported video extension"
        )

    dvd_id = str(
        dvd_id
    ).upper()

    family = dvd_id.rsplit(
        "-",
        1,
    )[0]

    expected_parent = (
        PurePosixPath(
            family,
            dvd_id,
        )
    )

    if (
        path.parent
        != expected_parent
        or path.stem.upper()
        != dvd_id
    ):
        raise MediaMetadataPublishError(
            "video path does not match dvd_id"
        )

    return path.as_posix()


def _decode(value) -> str:
    if isinstance(
        value,
        bytes,
    ):
        return value.decode(
            "utf-8",
            errors="replace",
        )

    return str(
        value or ""
    )


class MediaMetadataSSHMutator:
    def __init__(
        self,
        ssh,
    ):
        self.ssh = ssh

    def publish_bundle(
        self,
        *,
        video_relative: str,
        bundle: MediaBundle,
    ) -> dict:

        dvd_id = str(
            bundle.dvd_id
        ).strip().upper()

        video_relative = (
            _safe_video_relative(
                video_relative,
                dvd_id,
            )
        )

        if (
            bundle.nfo_filename
            != canonical_nfo_filename(dvd_id)
        ):
            raise MediaMetadataPublishError(
                "invalid nfo filename"
            )

        if bundle.poster is not None:
            if bundle.poster.filename not in POSTER_FILENAMES:
                raise MediaMetadataPublishError(
                    "invalid poster filename"
                )
        elif bundle.poster_status not in {
            "PENDING",
            "FAILED",
            "ATTENTION",
        }:
            raise MediaMetadataPublishError(
                "invalid missing poster status"
            )

        nfo_data = bytes(
            bundle.nfo_data
        )

        poster_data = (
            bytes(bundle.poster.data)
            if bundle.poster is not None
            else b""
        )

        if not nfo_data:
            raise MediaMetadataPublishError(
                "empty nfo"
            )

        if bundle.poster is not None and not poster_data:
            raise MediaMetadataPublishError(
                "empty poster"
            )

        nfo_sha = hashlib.sha256(
            nfo_data
        ).hexdigest()

        poster_sha = (
            hashlib.sha256(poster_data).hexdigest()
            if poster_data
            else ""
        )

        payload = (
            struct.pack(
                ">QQ",
                len(nfo_data),
                len(poster_data),
            )
            + nfo_data
            + poster_data
        )

        remote_command = (
            "python3 -c "
            + shlex.quote(
                REMOTE_PUBLISH_SCRIPT
            )
            + " "
            + " ".join(
                shlex.quote(
                    str(arg)
                )
                for arg in (
                    self.ssh.library_root,
                    video_relative,
                    bundle.nfo_filename,
                    bundle.poster.filename if bundle.poster is not None else "",
                    nfo_sha,
                    poster_sha,
                )
            )
        )

        command = (
            self.ssh._base()
            + [
                remote_command
            ]
        )

        result = self.ssh.runner(
            command,
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        if result.returncode != 0:
            raise MediaMetadataPublishError(
                _decode(
                    result.stderr
                ).strip()
                or "metadata publish failed"
            )

        try:
            value = json.loads(
                _decode(
                    result.stdout
                )
                or "{}"
            )
        except json.JSONDecodeError as exc:
            raise MediaMetadataPublishError(
                "invalid metadata publish response"
            ) from exc

        if value.get("status") not in {
            "METADATA_READY",
            "METADATA_PARTIAL",
            "NFO_READY",
        }:
            raise MediaMetadataPublishError(
                "metadata publish verification failed"
            )

        if value.get("nfo", {}).get("status") not in {
            "CREATED",
            "ALREADY_PRESENT",
        }:
            raise MediaMetadataPublishError(
                "nfo publish verification failed"
            )

        if bundle.poster is None:
            value["poster"] = {
                "status": bundle.poster_status,
                "error": bundle.poster_error,
            }

        return value
