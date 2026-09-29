"""Fixtureable, read-only prepare/validate contract for future library deletion.

The manifest SHA-256 identifies canonical manifest metadata; it is not a hash
of media contents. This module deliberately contains no filesystem mutator.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import secrets
import threading
import time
import copy
import uuid


MAX_MANIFEST_ENTRIES = 512
TOKEN_TTL_SECONDS = 300
TOKEN_REGISTRY_MAX = 128


class DeleteDryRunError(RuntimeError):
    def __init__(self, code: str, status: int = 409):
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class DeleteProvenance:
    """Non-persistent future provenance schema; never includes paths/secrets."""
    schema_version: int
    dvd_id: str
    manifest_sha256: str
    file_count: int
    total_bytes: int
    phase: str
    source_identity_fingerprint: str
    created_at: str
    validated_at: str | None
    result: str

    def to_dict(self):
        return asdict(self)


def serialize_provenance(value: DeleteProvenance) -> dict:
    return value.to_dict()


def source_identity_fingerprint(row: dict, relative_path: str) -> str:
    identity = {
        "holding_id": row.get("holding_id"),
        "storage_root": row.get("storage_root"),
        "relative_path": relative_path,
        "dvd_id": row.get("dvd_id"),
        "parse_status": row.get("parse_status"),
        "present": row.get("present"),
        "size_bytes": row.get("size_bytes"),
        "mtime_ns": row.get("mtime_ns"),
    }
    raw = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def canonical_manifest(entries: list[dict]) -> tuple[list[dict], str, int]:
    if not isinstance(entries, list) or len(entries) > MAX_MANIFEST_ENTRIES:
        raise DeleteDryRunError("ENTRY_LIMIT")
    normalized = []
    names = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise DeleteDryRunError("MANIFEST_INVALID")
        name = entry.get("relative_name")
        if (not isinstance(name, str) or not name or name in {".", ".."}
                or "/" in name or "\\" in name or "\x00" in name
                or name.startswith("/")):
            raise DeleteDryRunError("MANIFEST_INVALID")
        if name in names:
            raise DeleteDryRunError("MANIFEST_INVALID")
        names.add(name)
        if entry.get("file_type") != "regular":
            raise DeleteDryRunError("UNEXPECTED_TYPE")
        fields = {"size_bytes": entry.get("size_bytes"), "mtime_ns": entry.get("mtime_ns"),
                  "inode": entry.get("inode"), "device": entry.get("device")}
        if type(fields["size_bytes"]) is not int or fields["size_bytes"] < 0:
            raise DeleteDryRunError("MANIFEST_INVALID")
        for key in ("mtime_ns", "inode", "device"):
            if fields[key] is not None and type(fields[key]) is not int:
                raise DeleteDryRunError("MANIFEST_INVALID")
        normalized.append({"relative_name": name, **fields, "file_type": "regular"})
    normalized.sort(key=lambda x: x["relative_name"])
    raw = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return normalized, digest, sum(item["size_bytes"] for item in normalized)


class PrepareTokenRegistry:
    """Bounded process-memory token registry with short TTL and replay rules."""
    def __init__(self, *, ttl_seconds=TOKEN_TTL_SECONDS, max_entries=TOKEN_REGISTRY_MAX,
                 clock=time.monotonic, token_factory=lambda: secrets.token_urlsafe(32)):
        self.ttl_seconds = int(ttl_seconds)
        self.max_entries = int(max_entries)
        self.clock = clock
        self.token_factory = token_factory
        self._entries = OrderedDict()
        self._lock = threading.RLock()

    def _cleanup(self, now):
        for token in list(self._entries):
            if (self._entries[token]["expires_mono"] <= now
                    and self._entries[token]["state"] != "COMMITTING"):
                del self._entries[token]

    def issue(self, *, dvd_id, manifest_sha256, source_fingerprint, manifest_entries=None):
        now = self.clock()
        with self._lock:
            self._cleanup(now)
            while len(self._entries) >= self.max_entries:
                evictable = next((key for key, value in self._entries.items()
                                  if value["state"] != "COMMITTING"), None)
                if evictable is None:
                    raise DeleteDryRunError("TOKEN_REGISTRY_BUSY", 503)
                del self._entries[evictable]
            token = self.token_factory()
            while token in self._entries:
                token = self.token_factory()
            expiry = now + self.ttl_seconds
            self._entries[token] = {
                "dvd_id": dvd_id, "manifest_sha256": manifest_sha256,
                "source_fingerprint": source_fingerprint,
                "manifest_entries": copy.deepcopy(manifest_entries or []),
                "expires_mono": expiry, "expires_at": datetime.fromtimestamp(
                    time.time() + self.ttl_seconds, timezone.utc).isoformat(),
                "state": "PREPARED", "validated": False, "validated_at": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "operation_id": None, "removed_entries": [], "result": None,
                "retryable_partial": False,
            }
            return token, self._entries[token]["expires_at"]

    def precheck(self, token, *, dvd_id):
        """Reject unknown or cross-title tokens before any external lookup."""
        now = self.clock()
        with self._lock:
            self._cleanup(now)
            entry = self._entries.get(token)
            if not entry:
                raise DeleteDryRunError("TOKEN_EXPIRED_OR_INVALID", 410)
            if entry["dvd_id"] != dvd_id:
                raise DeleteDryRunError("TOKEN_DVD_ID_MISMATCH")

    def validate(self, token, *, dvd_id, manifest_sha256, source_fingerprint):
        now = self.clock()
        with self._lock:
            self._cleanup(now)
            entry = self._entries.get(token)
            if not entry:
                raise DeleteDryRunError("TOKEN_EXPIRED_OR_INVALID", 410)
            if entry["dvd_id"] != dvd_id:
                raise DeleteDryRunError("TOKEN_DVD_ID_MISMATCH")
            if (entry["manifest_sha256"] != manifest_sha256
                    or entry["source_fingerprint"] != source_fingerprint):
                del self._entries[token]
                raise DeleteDryRunError("MANIFEST_CHANGED")
            if not entry["validated"]:
                entry["validated"] = True
                entry["validated_at"] = datetime.now(timezone.utc).isoformat()
                entry["state"] = "VALIDATED"
            self._entries.move_to_end(token)
            return entry["validated_at"]

    def snapshot(self, token, *, dvd_id):
        with self._lock:
            now = self.clock()
            self._cleanup(now)
            entry = self._entries.get(token)
            if not entry:
                raise DeleteDryRunError("TOKEN_EXPIRED_OR_INVALID", 410)
            if entry["dvd_id"] != dvd_id:
                raise DeleteDryRunError("TOKEN_DVD_ID_MISMATCH")
            return copy.deepcopy(self._entries[token])

    def begin_commit(self, token, *, dvd_id):
        with self._lock:
            now = self.clock()
            self._cleanup(now)
            entry = self._entries.get(token)
            if not entry:
                raise DeleteDryRunError("TOKEN_EXPIRED_OR_INVALID", 410)
            if entry["dvd_id"] != dvd_id:
                raise DeleteDryRunError("TOKEN_DVD_ID_MISMATCH")
            state = entry["state"]
            if state == "PREPARED":
                raise DeleteDryRunError("TOKEN_NOT_VALIDATED")
            if state == "COMMITTING":
                raise DeleteDryRunError("COMMIT_IN_PROGRESS")
            if state in {"COMMITTED", "RECONCILE_PENDING"}:
                return copy.deepcopy(entry)
            if state == "PARTIAL_DELETE" and not entry.get("retryable_partial"):
                raise DeleteDryRunError("PARTIAL_DELETE_REQUIRES_REVIEW")
            if state not in {"VALIDATED", "PARTIAL_DELETE"}:
                raise DeleteDryRunError("TOKEN_STATE_INVALID")
            previous_state = state
            entry["state"] = "COMMITTING"
            entry["operation_id"] = entry.get("operation_id") or str(uuid.uuid4())
            snapshot = copy.deepcopy(entry)
            snapshot["previous_state"] = previous_state
            return snapshot

    def finish_commit(self, token, *, state, removed_entries=None, result=None,
                      retryable_partial=False):
        with self._lock:
            entry = self._entries.get(token)
            if not entry:
                return
            entry["state"] = state
            if removed_entries is not None:
                entry["removed_entries"] = list(removed_entries)
            if result is not None:
                entry["result"] = copy.deepcopy(result)
            entry["retryable_partial"] = bool(retryable_partial)

# Executed only by the existing hardened CompletionSSH._run_python transport.
# It checks exact components with lstat and inventories direct regular files;
# it does not recurse and does not follow symlinks.
MANIFEST_SCRIPT = r'''import base64,json,os,stat,sys
root=os.path.normpath(sys.argv[1]); rel=sys.argv[2]; media_rel=sys.argv[3]
expected_size=int(sys.argv[4]); expected_mtime=int(sys.argv[5])
if not rel or rel.startswith('/') or '\\' in rel or any(p in ('','.','..') for p in rel.split('/')): raise ValueError('unsafe_relative_path')
if os.path.normpath(rel)!=rel: raise ValueError('unsafe_relative_path')
root_abs=os.path.abspath(root); title=os.path.abspath(os.path.join(root,rel))
if os.path.commonpath((root_abs,title))!=root_abs or title==root_abs: raise SystemExit(32)
def checked_dir(path):
 st=os.lstat(path)
 if stat.S_ISLNK(st.st_mode): raise ValueError('symlink')
 if not stat.S_ISDIR(st.st_mode): raise ValueError('unsafe_component')
 return st
root_st=checked_dir(root_abs)
parts=rel.split('/'); cur=root_abs
for part in parts:
 cur=os.path.join(cur,part); checked_dir(cur)
if os.path.abspath(cur)!=title: raise SystemExit(32)
if os.path.dirname(media_rel)!=rel or media_rel.startswith('/') or '..' in media_rel.split('/'): raise SystemExit(33)
media_name=os.path.basename(media_rel); entries=[]; subtitles=[]; ko=None; total=0
with os.scandir(title) as it:
 for ent in it:
  if len(entries)>=512: raise ValueError('entry_limit')
  st=ent.stat(follow_symlinks=False); mode=st.st_mode
  if stat.S_ISLNK(mode): raise ValueError('symlink')
  if stat.S_ISDIR(mode): raise ValueError('nested_directory')
  if not stat.S_ISREG(mode): raise ValueError('unexpected_type')
  name=ent.name
  if name in ('','.','..') or '/' in name or '\\' in name: raise ValueError('unsafe_name')
  item={'relative_name':name,'size_bytes':int(st.st_size),'mtime_ns':int(st.st_mtime_ns),'inode':int(st.st_ino),'device':int(st.st_dev),'file_type':'regular'}
  entries.append(item); total+=int(st.st_size)
  if name.lower().endswith(('.srt','.vtt')): subtitles.append(name)
  if name==media_name:
   if int(st.st_size)!=expected_size or int(st.st_mtime_ns)!=expected_mtime: raise ValueError('canonical_media_identity_mismatch')
  if name.lower()==(os.path.splitext(media_name)[0]+'.ko.srt').lower():
   if st.st_size>8388608: raise ValueError('subtitle_limit')
   fd=os.open(ent.path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
   try:
    opened=os.fstat(fd)
    if not stat.S_ISREG(opened.st_mode) or (opened.st_dev,opened.st_ino)!=(st.st_dev,st.st_ino): raise ValueError('subtitle_identity_changed')
    with os.fdopen(fd,'rb',closefd=False) as f: ko=base64.b64encode(f.read(8388609)).decode('ascii')
   finally: os.close(fd)
entries.sort(key=lambda x:x['relative_name'])
if not any(e['relative_name']==media_name for e in entries): raise ValueError('canonical_media_missing')
if os.path.commonpath((root_abs,title))!=root_abs: raise ValueError('root_escape')
after=checked_dir(title)
if (after.st_dev,after.st_ino)!=(os.stat(title,follow_symlinks=False).st_dev,os.stat(title,follow_symlinks=False).st_ino): raise ValueError('directory_changed')
print(json.dumps({'status':'ok','entries':entries,'total_bytes':total,'subtitle_names':sorted(subtitles),'ko':ko},separators=(',',':')))
'''


class DeleteManifestReader:
    def __init__(self, ssh, *, library_root, max_response_bytes=12 * 1024 * 1024):
        self.ssh = ssh
        self.library_root = library_root
        self.max_response_bytes = max_response_bytes

    def inspect(self, video, row):
        from pathlib import PurePosixPath
        media = PurePosixPath(video.relative_path)
        directory = media.parent.as_posix()
        size = row.get("size_bytes")
        mtime = row.get("mtime_ns")
        if type(size) is not int or type(mtime) is not int:
            raise DeleteDryRunError("SOURCE_IDENTITY_UNAVAILABLE")
        try:
            raw = self.ssh._run_python(MANIFEST_SCRIPT, self.library_root, directory,
                                       video.relative_path, size, mtime)
            if len(raw.encode("utf-8")) > self.max_response_bytes:
                raise DeleteDryRunError("MANIFEST_RESPONSE_LIMIT")
            payload = json.loads(raw)
            if not isinstance(payload, dict) or payload.get("status") != "ok":
                raise DeleteDryRunError("MANIFEST_INVALID")
            entries, digest, total = canonical_manifest(payload.get("entries"))
            names = payload.get("subtitle_names")
            if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
                raise DeleteDryRunError("MANIFEST_INVALID")
            return {"entries": entries, "manifest_sha256": digest, "total_bytes": total,
                    "subtitle_names": names, "ko": payload.get("ko")}
        except DeleteDryRunError:
            raise
        except Exception as exc:
            message = str(exc)
            for code in ("unsafe_component", "unsafe_relative_path", "symlink", "nested_directory", "unexpected_type",
                         "entry_limit", "canonical_media_identity_mismatch", "canonical_media_missing",
                         "root_escape", "subtitle_limit", "subtitle_identity_changed"):
                if code in message:
                    raise DeleteDryRunError(code.upper()) from exc
            raise DeleteDryRunError("NAS_INSPECTION_FAILED", 503) from exc
