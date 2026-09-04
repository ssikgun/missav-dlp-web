"""Bounded Stage11 Korean subtitle publication over hardened SSH.

This module owns only the generated Korean subtitle publication boundary.  It
validates an already-generated canonical SRT artifact, sends bounded bytes to
one exact canonical holding, and uses same-directory hard-link promotion so a
final ``.ko.srt`` is never replaced.  It owns no database, job, media, model,
Jellyfin, or Stage9 completion state.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from pathlib import PurePosixPath
import shlex
import subprocess
import unicodedata

from teddy_discovery_ko_srt import (
    GENERATED_SRT_NO_ARTIFACT,
    GENERATED_SRT_READY,
    GeneratedKoreanSRT,
)
from teddy_discovery_subtitle import (
    CanonicalHoldingValidationError,
    CanonicalVideoHolding,
    derive_target_ko_relative,
    validate_canonical_holding,
)
from teddy_discovery_subtitle_text import (
    MAX_SUBTITLE_BYTES,
    MAX_SUBTITLE_CUES,
    SubtitleTextError,
    parse_subtitle_bytes,
    serialize_srt,
)


SUBTITLE_PUBLISHED = "PUBLISHED"
SUBTITLE_SKIPPED_EXISTING_KO = "SKIPPED_EXISTING_KO"
SUBTITLE_NO_ARTIFACT = "NO_ARTIFACT"


class SubtitlePublishError(RuntimeError):
    """Base class for deterministic Korean subtitle publication failures."""


class SubtitlePublishValidationError(SubtitlePublishError):
    """Raised for invalid local or remote publication contract data."""


class SubtitlePublishCollisionError(SubtitlePublishError):
    """Raised when an existing final differs from the incoming artifact."""


class SubtitlePublishTransportError(SubtitlePublishError):
    """Raised for SSH execution or remote protocol failures."""


class SubtitlePublishVerificationError(SubtitlePublishError):
    """Raised when a published object cannot be verified exactly."""


@dataclass(frozen=True)
class SubtitlePublishResult:
    """Immutable publication outcome and generated-payload identity."""

    state: str
    target_relative: str
    sha256: str | None
    byte_size: int

    def __post_init__(self):
        _validate_result_target(self.target_relative)

        if self.state == SUBTITLE_NO_ARTIFACT:
            if (
                self.sha256 is not None
                or type(self.byte_size) is not int
                or self.byte_size != 0
            ):
                raise SubtitlePublishValidationError(
                    "no-artifact result contains payload metadata"
                )
            return

        if self.state not in {
            SUBTITLE_PUBLISHED,
            SUBTITLE_SKIPPED_EXISTING_KO,
        }:
            raise SubtitlePublishValidationError(
                "publication result state is invalid"
            )

        if (
            not isinstance(self.sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", self.sha256) is None
        ):
            raise SubtitlePublishValidationError(
                "publication result sha256 is invalid"
            )

        if (
            type(self.byte_size) is not int
            or self.byte_size <= 0
            or self.byte_size > MAX_SUBTITLE_BYTES
        ):
            raise SubtitlePublishValidationError(
                "publication result byte_size is invalid"
            )


def _validate_result_target(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise SubtitlePublishValidationError(
            "target_relative must be a non-empty string"
        )

    if "\\" in value or "\x00" in value:
        raise SubtitlePublishValidationError(
            "target_relative contains an unsafe character"
        )

    if any(
        ord(character) < 32
        or ord(character) == 127
        or unicodedata.category(character) == "Cc"
        for character in value
    ):
        raise SubtitlePublishValidationError(
            "target_relative contains a control character"
        )

    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or len(path.parts) != 3
        or any(
            not part
            or part in {".", ".."}
            or part.startswith(".")
            for part in path.parts
        )
        or not value.endswith(".ko.srt")
    ):
        raise SubtitlePublishValidationError(
            "target_relative is not a canonical Korean subtitle path"
        )

    dvd_id = path.name[: -len(".ko.srt")]
    if (
        not dvd_id
        or path.parts[1] != dvd_id
        or "-" not in dvd_id
        or path.parts[0] != dvd_id.rsplit("-", 1)[0]
    ):
        raise SubtitlePublishValidationError(
            "target_relative does not match DVD-ID.ko.srt"
        )

    return value


def _validated_canonical_video(
    canonical_video: CanonicalVideoHolding,
) -> CanonicalVideoHolding:
    if not isinstance(canonical_video, CanonicalVideoHolding):
        raise SubtitlePublishValidationError(
            "canonical_video must be a CanonicalVideoHolding"
        )

    holding = {
        "dvd_id": canonical_video.dvd_id,
        "storage_root": "jav",
        "relative_path": canonical_video.relative_path,
        "parse_status": "MATCHED",
        "present": 1,
    }

    try:
        return validate_canonical_holding(
            holding,
            canonical_video.dvd_id,
        )
    except (CanonicalHoldingValidationError, TypeError, ValueError) as error:
        raise SubtitlePublishValidationError(
            "canonical_video does not satisfy the frozen holding contract"
        ) from error


def _validated_library_root(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise SubtitlePublishValidationError(
            "SSH library_root must be a non-empty string"
        )

    if "\\" in value or "\x00" in value:
        raise SubtitlePublishValidationError(
            "SSH library_root contains an unsafe character"
        )

    if any(
        ord(character) < 32
        or ord(character) == 127
        or unicodedata.category(character) == "Cc"
        for character in value
    ):
        raise SubtitlePublishValidationError(
            "SSH library_root contains a control character"
        )

    path = PurePosixPath(value)
    if (
        not path.is_absolute()
        or path == PurePosixPath("/")
        or ".." in path.parts
    ):
        raise SubtitlePublishValidationError(
            "SSH library_root must be a normalized absolute non-root path"
        )

    return path.as_posix()


def _validated_artifact(
    artifact: object,
) -> tuple[bytes, int, str, int] | None:
    if not isinstance(artifact, GeneratedKoreanSRT):
        raise SubtitlePublishValidationError(
            "artifact must be a GeneratedKoreanSRT"
        )

    if artifact.state == GENERATED_SRT_NO_ARTIFACT:
        if (
            artifact.payload is not None
            or type(artifact.cue_count) is not int
            or artifact.cue_count != 0
            or artifact.sha256 is not None
            or type(artifact.byte_size) is not int
            or artifact.byte_size != 0
        ):
            raise SubtitlePublishValidationError(
                "no-artifact value violates its frozen contract"
            )
        return None

    if artifact.state != GENERATED_SRT_READY:
        raise SubtitlePublishValidationError(
            "artifact state is not publishable"
        )

    if type(artifact.payload) is not bytes or not artifact.payload:
        raise SubtitlePublishValidationError(
            "ready artifact requires a nonempty bytes payload"
        )

    if (
        type(artifact.cue_count) is not int
        or artifact.cue_count <= 0
        or artifact.cue_count > MAX_SUBTITLE_CUES
    ):
        raise SubtitlePublishValidationError(
            "ready artifact cue_count is invalid"
        )

    if (
        type(artifact.byte_size) is not int
        or artifact.byte_size != len(artifact.payload)
        or artifact.byte_size <= 0
        or artifact.byte_size > MAX_SUBTITLE_BYTES
    ):
        raise SubtitlePublishValidationError(
            "ready artifact byte_size is invalid"
        )

    if (
        not isinstance(artifact.sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", artifact.sha256) is None
        or artifact.sha256
        != hashlib.sha256(artifact.payload).hexdigest()
    ):
        raise SubtitlePublishValidationError(
            "ready artifact sha256 is invalid"
        )

    try:
        parsed = parse_subtitle_bytes(
            artifact.payload,
            "srt",
        )
        canonical_payload = serialize_srt(parsed)
    except SubtitleTextError as error:
        raise SubtitlePublishValidationError(
            "ready artifact is not a valid canonical SRT"
        ) from error

    if canonical_payload != artifact.payload:
        raise SubtitlePublishValidationError(
            "ready artifact is not canonically serialized"
        )

    if len(parsed.cues) != artifact.cue_count:
        raise SubtitlePublishValidationError(
            "ready artifact cue_count does not match its SRT payload"
        )

    return (
        artifact.payload,
        artifact.cue_count,
        artifact.sha256,
        artifact.byte_size,
    )


REMOTE_SUBTITLE_PUBLISH_SCRIPT = r'''
import hashlib
import json
import os
import re
import stat
import sys
import unicodedata
import uuid


MAX_SUBTITLE_BYTES = 8 * 1024 * 1024
VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".m4v",
    ".ts",
    ".webm",
}


def protocol_failure(status):
    print(
        json.dumps(
            {"status": status},
            separators=(",", ":"),
        )
    )
    raise SystemExit(0)


def safe_relative_parts(value):
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or "\\" in value
        or any(
            ord(character) < 32
            or ord(character) == 127
            or unicodedata.category(character) == "Cc"
            for character in value
        )
    ):
        protocol_failure("INVALID_TARGET")

    parts = value.split("/")
    if (
        any(
            not part
            or part in (".", "..")
            or part.startswith(".")
            for part in parts
        )
        or "/".join(parts) != value
    ):
        protocol_failure("INVALID_TARGET")

    return parts


def component_snapshot(path, unsafe_status):
    value = os.lstat(path)
    if stat.S_ISLNK(value.st_mode) or not stat.S_ISDIR(value.st_mode):
        protocol_failure(unsafe_status)
    return value


def check_absolute_components(path, unsafe_status):
    current = os.sep
    for component in path.split(os.sep):
        if not component:
            continue
        current = os.path.join(current, component)
        component_snapshot(current, unsafe_status)


def check_relative_directory(root, parts, unsafe_status):
    current = root
    for part in parts:
        current = os.path.join(current, part)
        component_snapshot(current, unsafe_status)


def regular_snapshot(path, unsafe_status):
    value = os.lstat(path)
    if stat.S_ISLNK(value.st_mode) or not stat.S_ISREG(value.st_mode):
        protocol_failure(unsafe_status)
    return value


def snapshot_key(value):
    return (
        int(value.st_dev),
        int(value.st_ino),
        int(value.st_size),
        int(value.st_mtime_ns),
    )


def read_bounded(path, expected_size, unsafe_status):
    before = regular_snapshot(path, unsafe_status)
    if not hasattr(os, "O_NOFOLLOW"):
        protocol_failure(unsafe_status)

    flags = os.O_RDONLY
    flags |= os.O_NOFOLLOW

    try:
        descriptor = os.open(path, flags)
    except OSError:
        protocol_failure("VERIFICATION_FAILED")

    try:
        with os.fdopen(descriptor, "rb") as handle:
            data = handle.read(expected_size + 1)
    except OSError:
        protocol_failure("VERIFICATION_FAILED")

    after = regular_snapshot(path, unsafe_status)
    if (
        snapshot_key(before) != snapshot_key(after)
        or len(data) > expected_size + 1
        or (
            before.st_size <= expected_size + 1
            and len(data) != before.st_size
        )
    ):
        protocol_failure("VERIFICATION_FAILED")

    return data


def verify_payload(data, expected_data, expected_size, expected_sha):
    if (
        len(data) != expected_size
        or data != expected_data
        or hashlib.sha256(data).hexdigest() != expected_sha
    ):
        protocol_failure("VERIFICATION_FAILED")


root_argument = sys.argv[1]
video_relative = sys.argv[2]
target_relative = sys.argv[3]

try:
    expected_size = int(sys.argv[4])
except (IndexError, TypeError, ValueError):
    protocol_failure("INVALID_ARTIFACT")

expected_sha = sys.argv[5]

if (
    expected_size <= 0
    or expected_size > MAX_SUBTITLE_BYTES
    or re.fullmatch(r"[0-9a-f]{64}", expected_sha or "") is None
):
    protocol_failure("INVALID_ARTIFACT")

payload = sys.stdin.buffer.read(expected_size + 1)
if len(payload) != expected_size or sys.stdin.buffer.read(1):
    protocol_failure("INVALID_ARTIFACT")

video_parts = safe_relative_parts(video_relative)
target_parts = safe_relative_parts(target_relative)

if len(video_parts) != 3 or len(target_parts) != 3:
    protocol_failure("INVALID_TARGET")

dvd_id = video_parts[1]
if not dvd_id or "-" not in dvd_id:
    protocol_failure("INVALID_TARGET")

family = dvd_id.rsplit("-", 1)[0]

if (
    not family
    or video_parts != [family, dvd_id, video_parts[-1]]
    or video_parts[-1][:-len(os.path.splitext(video_parts[-1])[1])]
    != dvd_id
    or os.path.splitext(video_parts[-1])[1].lower() not in VIDEO_EXTENSIONS
    or target_parts != [family, dvd_id, dvd_id + ".ko.srt"]
):
    protocol_failure("INVALID_TARGET")

root = os.path.normpath(root_argument)
if (
    not root.startswith(os.sep)
    or root == os.sep
    or root_argument != root
):
    protocol_failure("INVALID_TARGET")

root_real = os.path.realpath(root)
if root_real != root:
    protocol_failure("UNSAFE_TARGET")

check_absolute_components(root, "UNSAFE_TARGET")
component_snapshot(root, "UNSAFE_TARGET")

video = os.path.join(root, *video_parts)
check_relative_directory(root, video_parts[:-1], "UNSAFE_TARGET")
video_real = os.path.realpath(video)

try:
    inside = os.path.commonpath((root_real, video_real)) == root_real
except ValueError:
    inside = False

if not inside:
    protocol_failure("UNSAFE_TARGET")

video_stat = os.lstat(video)
if stat.S_ISLNK(video_stat.st_mode) or not stat.S_ISREG(video_stat.st_mode):
    protocol_failure("UNSAFE_TARGET")

parent = os.path.dirname(video)
target = os.path.join(parent, target_parts[-1])

if os.path.lexists(target):
    existing = read_bounded(
        target,
        expected_size,
        "UNSAFE_TARGET",
    )
    if (
        len(existing) == expected_size
        and existing == payload
        and hashlib.sha256(existing).hexdigest() == expected_sha
    ):
        print(
            json.dumps(
                {
                    "status": "ALREADY_PRESENT",
                    "size": expected_size,
                    "sha256": expected_sha,
                },
                separators=(",", ":"),
            )
        )
        raise SystemExit(0)

    protocol_failure("COLLISION")

partial = None
partial_identity = None

try:
    for attempt in range(3):
        candidate = os.path.join(
            parent,
            "."
            + target_parts[-1]
            + ".stage11-partial."
            + uuid.uuid4().hex,
        )
        try:
            with open(candidate, "xb") as handle:
                partial = candidate
                value = os.fstat(handle.fileno())
                partial_identity = (
                    int(value.st_dev),
                    int(value.st_ino),
                )
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            break
        except FileExistsError:
            continue

    if partial is None:
        protocol_failure("PARTIAL_COLLISION")

    partial_stat = regular_snapshot(partial, "VERIFICATION_FAILED")
    if partial_stat.st_size != expected_size:
        protocol_failure("VERIFICATION_FAILED")

    partial_data = read_bounded(
        partial,
        expected_size,
        "VERIFICATION_FAILED",
    )
    verify_payload(
        partial_data,
        payload,
        expected_size,
        expected_sha,
    )

    try:
        os.link(partial, target)
    except FileExistsError:
        existing = read_bounded(
            target,
            expected_size,
            "UNSAFE_TARGET",
        )
        if (
            len(existing) == expected_size
            and existing == payload
            and hashlib.sha256(existing).hexdigest() == expected_sha
        ):
            print(
                json.dumps(
                    {
                        "status": "ALREADY_PRESENT",
                        "size": expected_size,
                        "sha256": expected_sha,
                    },
                    separators=(",", ":"),
                )
            )
            raise SystemExit(0)

        protocol_failure("COLLISION")

    os.unlink(partial)
    partial = None

    directory_fd = os.open(parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)

    final_data = read_bounded(
        target,
        expected_size,
        "UNSAFE_TARGET",
    )
    verify_payload(
        final_data,
        payload,
        expected_size,
        expected_sha,
    )

    print(
        json.dumps(
            {
                "status": "CREATED",
                "size": expected_size,
                "sha256": expected_sha,
            },
            separators=(",", ":"),
        )
    )

finally:
    if partial is not None and partial_identity is not None:
        try:
            value = os.lstat(partial)
            identity = (
                int(value.st_dev),
                int(value.st_ino),
            )
            if identity == partial_identity:
                os.unlink(partial)
        except FileNotFoundError:
            pass
        except OSError:
            pass
'''


def _decode_remote_output(value: object) -> object:
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SubtitlePublishTransportError(
                "remote subtitle response is not UTF-8"
            ) from error

    if not isinstance(value, str) or not value:
        raise SubtitlePublishTransportError(
            "remote subtitle response is malformed"
        )

    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise SubtitlePublishTransportError(
            "remote subtitle response is not valid JSON"
        ) from error


def _parse_remote_response(
    value: object,
    *,
    expected_sha: str,
    expected_size: int,
) -> str:
    if not isinstance(value, dict):
        raise SubtitlePublishTransportError(
            "remote subtitle response must be an object"
        )

    status = value.get("status")
    if not isinstance(status, str):
        raise SubtitlePublishTransportError(
            "remote subtitle response status is invalid"
        )

    if status in {"CREATED", "ALREADY_PRESENT"}:
        if set(value) != {"status", "size", "sha256"}:
            raise SubtitlePublishTransportError(
                "remote subtitle success response has an invalid shape"
            )

        if (
            type(value["size"]) is not int
            or value["size"] != expected_size
            or value["sha256"] != expected_sha
        ):
            raise SubtitlePublishVerificationError(
                "remote subtitle success response does not match the artifact"
            )

        return status

    if status in {
        "COLLISION",
        "UNSAFE_TARGET",
        "INVALID_TARGET",
        "INVALID_ARTIFACT",
        "PARTIAL_COLLISION",
        "VERIFICATION_FAILED",
    }:
        if set(value) != {"status"}:
            raise SubtitlePublishTransportError(
                "remote subtitle failure response has an invalid shape"
            )

        if status == "COLLISION":
            raise SubtitlePublishCollisionError(
                "remote subtitle target collision"
            )

        if status == "VERIFICATION_FAILED":
            raise SubtitlePublishVerificationError(
                "remote subtitle verification failed"
            )

        raise SubtitlePublishValidationError(
            "remote subtitle publication contract was rejected"
        )

    raise SubtitlePublishTransportError(
        "remote subtitle response status is invalid"
    )


class SubtitleSSHMutator:
    """Publish one generated Korean SRT through an existing SSH object."""

    def __init__(self, ssh):
        self.ssh = ssh

    def _transport_details(self):
        base_method = getattr(self.ssh, "_base", None)
        runner = getattr(self.ssh, "runner", None)
        library_root = getattr(self.ssh, "library_root", None)

        if not callable(base_method) or not callable(runner):
            raise SubtitlePublishValidationError(
                "SSH object must expose a hardened base and callable runner"
            )

        base = base_method()
        if (
            not isinstance(base, list)
            or not base
            or not all(isinstance(item, str) for item in base)
        ):
            raise SubtitlePublishValidationError(
                "SSH hardened base is invalid"
            )

        return (
            base,
            runner,
            _validated_library_root(library_root),
        )

    def publish_korean_srt(
        self,
        *,
        canonical_video: CanonicalVideoHolding,
        artifact: GeneratedKoreanSRT,
        target_relative: str | None = None,
    ) -> SubtitlePublishResult:
        validated_video = _validated_canonical_video(canonical_video)
        expected_target = derive_target_ko_relative(validated_video)
        _validate_result_target(expected_target)

        if target_relative is not None:
            if not isinstance(target_relative, str):
                raise SubtitlePublishValidationError(
                    "target_relative must be a string or None"
                )
            if target_relative != expected_target:
                raise SubtitlePublishValidationError(
                    "target_relative does not equal the frozen KO target"
                )

        validated = _validated_artifact(artifact)
        if validated is None:
            return SubtitlePublishResult(
                state=SUBTITLE_NO_ARTIFACT,
                target_relative=expected_target,
                sha256=None,
                byte_size=0,
            )

        payload, _cue_count, expected_sha, expected_size = validated
        base, runner, library_root = self._transport_details()

        remote_command = (
            "python3 -c "
            + shlex.quote(REMOTE_SUBTITLE_PUBLISH_SCRIPT)
            + " "
            + " ".join(
                shlex.quote(str(argument))
                for argument in (
                    library_root,
                    validated_video.relative_path,
                    expected_target,
                    expected_size,
                    expected_sha,
                )
            )
        )

        try:
            response = runner(
                base + [remote_command],
                input=payload,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise SubtitlePublishTransportError(
                "remote subtitle publish command could not be started"
            ) from error

        if getattr(response, "returncode", None) != 0:
            raise SubtitlePublishTransportError(
                "remote subtitle publish command failed"
            )

        status = _parse_remote_response(
            _decode_remote_output(
                getattr(response, "stdout", None)
            ),
            expected_sha=expected_sha,
            expected_size=expected_size,
        )

        result_state = (
            SUBTITLE_PUBLISHED
            if status == "CREATED"
            else SUBTITLE_SKIPPED_EXISTING_KO
        )

        return SubtitlePublishResult(
            state=result_state,
            target_relative=expected_target,
            sha256=expected_sha,
            byte_size=expected_size,
        )


__all__ = [
    "REMOTE_SUBTITLE_PUBLISH_SCRIPT",
    "SUBTITLE_NO_ARTIFACT",
    "SUBTITLE_PUBLISHED",
    "SUBTITLE_SKIPPED_EXISTING_KO",
    "SubtitlePublishCollisionError",
    "SubtitlePublishError",
    "SubtitlePublishTransportError",
    "SubtitlePublishValidationError",
    "SubtitlePublishVerificationError",
    "SubtitlePublishResult",
    "SubtitleSSHMutator",
]
