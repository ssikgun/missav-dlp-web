"""Read-only, bounded SSH subtitle inventory/read adapter for Stage11.

The adapter performs no local filesystem inspection.  It sends one-level
remote Python programs through a hardened SSH argv and consumes only bounded
JSON metadata or raw bytes.  It never writes remote content.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import PurePosixPath
import shlex
import subprocess
import unicodedata

from teddy_discovery_subtitle import (
    CanonicalHoldingValidationError,
    CanonicalVideoHolding,
    SOURCE_KIND_SIBLING_TEXT,
    SubtitleCandidate,
    SubtitleCandidateValidationError,
    select_subtitle_source,
    validate_canonical_holding,
)
from teddy_discovery_subtitle_text import MAX_SUBTITLE_BYTES


MAX_SUBTITLE_DIRECTORY_ENTRIES = 256


class SubtitleSSHError(RuntimeError):
    """Raised for Stage11 SSH transport, remote, and protocol failures."""


@dataclass(frozen=True)
class SubtitleInventoryEntry:
    """Bounded metadata for one remote regular subtitle file."""

    filename: str
    size: int
    mtime_ns: int


def _has_control_characters(value: str) -> bool:
    return any(
        ord(character) < 32
        or ord(character) == 127
        or unicodedata.category(character) == "Cc"
        for character in value
    )


def _synthetic_holding(
    canonical_video: CanonicalVideoHolding,
) -> CanonicalVideoHolding:
    """Revalidate an immutable Slice 1 identity without accepting a path."""

    if not isinstance(canonical_video, CanonicalVideoHolding):
        raise CanonicalHoldingValidationError(
            "canonical_video must be a CanonicalVideoHolding"
        )

    row = {
        "dvd_id": canonical_video.dvd_id,
        "storage_root": "jav",
        "relative_path": canonical_video.relative_path,
        "parse_status": "MATCHED",
        "present": 1,
    }

    return validate_canonical_holding(
        row,
        canonical_video.dvd_id,
    )


def _canonical_directory_relative(
    canonical_video: CanonicalVideoHolding,
) -> str:
    validated = _synthetic_holding(canonical_video)
    return PurePosixPath(validated.relative_path).parent.as_posix()


def _validate_candidate_for_video(
    canonical_video: CanonicalVideoHolding,
    candidate: SubtitleCandidate,
) -> None:
    if not isinstance(candidate, SubtitleCandidate):
        raise SubtitleCandidateValidationError(
            "candidate must be a SubtitleCandidate"
        )

    if candidate.source_kind != SOURCE_KIND_SIBLING_TEXT:
        raise SubtitleCandidateValidationError(
            "SSH subtitle reads accept sibling text candidates only"
        )

    validated_video = _synthetic_holding(canonical_video)
    holding = {
        "dvd_id": validated_video.dvd_id,
        "storage_root": "jav",
        "relative_path": validated_video.relative_path,
        "parse_status": "MATCHED",
        "present": 1,
    }

    # Slice 1 owns the exact sibling directory/DVD-ID/filename contract.
    select_subtitle_source(
        holding,
        validated_video.dvd_id,
        (candidate,),
    )


class SubtitleSSHReader:
    """Bounded read-only SSH access to one canonical JAV DVD directory."""

    def __init__(
        self,
        *,
        host,
        user,
        key,
        known_hosts,
        library_root,
        runner=subprocess.run,
    ):
        self.host = str(host)
        self.user = str(user)
        self.key = str(key)
        self.known_hosts = str(known_hosts)
        self.library_root = str(library_root)
        self.runner = runner

    def _base_argv(self) -> list[str]:
        return [
            "ssh",
            "-i",
            self.key,
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "UserKnownHostsFile=" + self.known_hosts,
            self.user + "@" + self.host,
        ]

    def _run_python(
        self,
        script: str,
        *args: str,
        binary_output: bool,
    ):
        remote_command = "python3 -"

        if args:
            remote_command += " " + " ".join(
                shlex.quote(str(argument))
                for argument in args
            )

        command = self._base_argv() + [remote_command]
        input_payload = (
            script.encode("utf-8")
            if binary_output
            else script
        )

        try:
            result = self.runner(
                command,
                input=input_payload,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=not binary_output,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise SubtitleSSHError(
                "remote SSH command could not be started"
            ) from error

        if getattr(result, "returncode", None) != 0:
            raise SubtitleSSHError(
                "remote SSH command failed"
            )

        return getattr(result, "stdout", None)

    @staticmethod
    def _decode_json_output(raw) -> object:
        if isinstance(raw, bytes):
            try:
                raw = raw.decode("utf-8")
            except UnicodeDecodeError as error:
                raise SubtitleSSHError(
                    "remote inventory JSON is not UTF-8"
                ) from error

        if not isinstance(raw, str) or not raw:
            raise SubtitleSSHError(
                "remote inventory JSON output is malformed"
            )

        try:
            return json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise SubtitleSSHError(
                "remote inventory JSON could not be decoded"
            ) from error

    @staticmethod
    def _validate_inventory_filename(filename: object) -> str:
        if not isinstance(filename, str):
            raise SubtitleSSHError(
                "remote inventory filename must be a string"
            )

        if (
            not filename
            or filename in {".", ".."}
            or "/" in filename
            or "\\" in filename
            or _has_control_characters(filename)
            or filename.startswith(".")
            or filename == "@eaDir"
        ):
            raise SubtitleSSHError(
                "remote inventory filename is unsafe"
            )

        if not filename.lower().endswith((".srt", ".vtt")):
            raise SubtitleSSHError(
                "remote inventory returned an unexpected suffix"
            )

        return filename

    @classmethod
    def _validate_inventory_items(
        cls,
        data: object,
    ) -> tuple[SubtitleInventoryEntry, ...]:
        if not isinstance(data, list):
            raise SubtitleSSHError(
                "remote subtitle inventory must be a JSON list"
            )

        if len(data) > MAX_SUBTITLE_DIRECTORY_ENTRIES:
            raise SubtitleSSHError(
                "remote subtitle inventory exceeds directory-entry bound"
            )

        entries: list[SubtitleInventoryEntry] = []
        seen_filenames: set[str] = set()

        for item in data:
            if not isinstance(item, dict):
                raise SubtitleSSHError(
                    "remote inventory item must be a JSON object"
                )

            if set(item) != {"filename", "size", "mtime_ns"}:
                raise SubtitleSSHError(
                    "remote inventory item has an unexpected shape"
                )

            filename = cls._validate_inventory_filename(
                item["filename"]
            )
            size = item["size"]
            mtime_ns = item["mtime_ns"]

            if type(size) is not int or size < 0:
                raise SubtitleSSHError(
                    "remote inventory size must be a nonnegative integer"
                )

            if type(mtime_ns) is not int or mtime_ns < 0:
                raise SubtitleSSHError(
                    "remote inventory mtime_ns must be a nonnegative integer"
                )

            if filename in seen_filenames:
                raise SubtitleSSHError(
                    "remote inventory contains duplicate filenames"
                )

            seen_filenames.add(filename)
            entries.append(
                SubtitleInventoryEntry(
                    filename=filename,
                    size=size,
                    mtime_ns=mtime_ns,
                )
            )

        return tuple(
            sorted(
                entries,
                key=lambda entry: entry.filename,
            )
        )

    def list_subtitle_inventory(
        self,
        canonical_video: CanonicalVideoHolding,
    ) -> tuple[SubtitleInventoryEntry, ...]:
        """Return sorted bounded metadata from exactly one DVD directory."""

        directory_relative = _canonical_directory_relative(
            canonical_video
        )

        script = r'''
import json
import os
import sys

MAX_SUBTITLE_DIRECTORY_ENTRIES = 256

root = os.path.realpath(sys.argv[1])
relative = sys.argv[2]
candidate = os.path.join(root, relative)
resolved = os.path.realpath(candidate)

if (
    resolved == root
    or os.path.commonpath((root, resolved)) != root
):
    raise SystemExit(2)

current = root
for component in relative.split(os.sep):
    current = os.path.join(current, component)
    if os.path.islink(current):
        raise SystemExit(3)

if not os.path.lexists(candidate):
    raise SystemExit(4)

if os.path.islink(candidate) or not os.path.isdir(candidate):
    raise SystemExit(5)

items = []
visible_entries = 0

with os.scandir(resolved) as entries:
    for entry in entries:
        if entry.name.startswith(".") or entry.name == "@eaDir":
            continue

        visible_entries += 1
        if visible_entries > MAX_SUBTITLE_DIRECTORY_ENTRIES:
            raise SystemExit(6)

        if entry.is_symlink():
            continue

        if not entry.is_file(follow_symlinks=False):
            continue

        if not entry.name.lower().endswith((".srt", ".vtt")):
            continue

        entry_stat = entry.stat(follow_symlinks=False)
        items.append({
            "filename": entry.name,
            "size": entry_stat.st_size,
            "mtime_ns": entry_stat.st_mtime_ns,
        })

print(json.dumps(items, ensure_ascii=False, separators=(",", ":")))
'''

        raw = self._run_python(
            script,
            self.library_root,
            directory_relative,
            binary_output=False,
        )
        data = self._decode_json_output(raw)
        return self._validate_inventory_items(data)

    def list_subtitle_candidates(
        self,
        canonical_video: CanonicalVideoHolding,
    ) -> tuple[SubtitleCandidate, ...]:
        """Inventory and convert every safe remote sidecar to Slice 1 data."""

        validated_video = _synthetic_holding(canonical_video)
        directory_relative = PurePosixPath(
            validated_video.relative_path
        ).parent.as_posix()
        inventory = self.list_subtitle_inventory(validated_video)
        candidates: list[SubtitleCandidate] = []

        for entry in inventory:
            relative_path = PurePosixPath(
                directory_relative,
                entry.filename,
            ).as_posix()
            candidate = SubtitleCandidate.sibling_text(
                relative_path,
            )

            # This also enforces the current canonical DVD-ID directory and
            # Slice 1's exact sidecar filename contract.
            _validate_candidate_for_video(
                validated_video,
                candidate,
            )
            candidates.append(candidate)

        return tuple(candidates)

    def read_subtitle_bytes(
        self,
        canonical_video: CanonicalVideoHolding,
        candidate: SubtitleCandidate,
    ) -> bytes:
        """Read one stable, bounded sibling sidecar as raw bytes only."""

        validated_video = _synthetic_holding(canonical_video)
        _validate_candidate_for_video(
            validated_video,
            candidate,
        )

        script = r'''
import os
import stat
import sys

MAX_SUBTITLE_BYTES = 8 * 1024 * 1024

root = os.path.realpath(sys.argv[1])
relative = sys.argv[2]
candidate = os.path.join(root, relative)
resolved = os.path.realpath(candidate)

if (
    resolved == root
    or os.path.commonpath((root, resolved)) != root
):
    raise SystemExit(2)

current = root
for component in relative.split(os.sep):
    current = os.path.join(current, component)
    if os.path.islink(current):
        raise SystemExit(3)

if not os.path.lexists(candidate) or os.path.islink(candidate):
    raise SystemExit(4)

def regular_stat(path):
    value = os.lstat(path)
    if stat.S_ISLNK(value.st_mode) or not stat.S_ISREG(value.st_mode):
        raise SystemExit(5)
    return value

before = regular_stat(candidate)

if before.st_size <= 0 or before.st_size > MAX_SUBTITLE_BYTES:
    raise SystemExit(6)

flags = os.O_RDONLY
if hasattr(os, "O_NOFOLLOW"):
    flags |= os.O_NOFOLLOW

try:
    descriptor = os.open(candidate, flags)
except OSError:
    raise SystemExit(7)

try:
    with os.fdopen(descriptor, "rb") as handle:
        data = handle.read(MAX_SUBTITLE_BYTES + 1)
except OSError:
    raise SystemExit(8)

after = regular_stat(candidate)

if (
    after.st_size != before.st_size
    or after.st_mtime_ns != before.st_mtime_ns
    or len(data) != before.st_size
    or len(data) > MAX_SUBTITLE_BYTES
):
    raise SystemExit(9)

sys.stdout.buffer.write(data)
'''

        raw = self._run_python(
            script,
            self.library_root,
            candidate.relative_path,
            binary_output=True,
        )

        if not isinstance(raw, bytes):
            raise SubtitleSSHError(
                "remote subtitle read did not return bytes"
            )

        if not raw:
            raise SubtitleSSHError(
                "remote subtitle read returned empty bytes"
            )

        if len(raw) > MAX_SUBTITLE_BYTES:
            raise SubtitleSSHError(
                "remote subtitle read exceeded MAX_SUBTITLE_BYTES"
            )

        return raw


__all__ = [
    "MAX_SUBTITLE_DIRECTORY_ENTRIES",
    "SubtitleInventoryEntry",
    "SubtitleSSHError",
    "SubtitleSSHReader",
]
