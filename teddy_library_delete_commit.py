"""Exact one-title delete mutation and durable offline-testable provenance."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import stat
from urllib.parse import quote, urlencode
import uuid
from contextlib import closing

from teddy_discovery_ids import parse_dvd_id
from teddy_discovery_jellyfin import JellyfinClient, jellyfin_media_path
from teddy_discovery_organizer import canonical_destination
from teddy_library_delete_dryrun import (
    DeleteDryRunError,
    canonical_manifest,
    source_identity_fingerprint,
)


CONFIRM_PHRASE = "영구 삭제 확인"
PROVENANCE_SCHEMA_VERSION = 1
PROVENANCE_DEFAULT_PATH = "/downloads/teddy-library-delete-provenance.sqlite3"
MAX_JELLYFIN_ITEMS = 10000


class DeleteCommitError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def delete_enabled(value: str | None) -> bool:
    return isinstance(value, str) and value.strip().casefold() == "true"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical_media_path(row: dict, dvd_id: str) -> str:
    relative = row.get("relative_path")
    if (row.get("storage_root") != "jav" or row.get("dvd_id") != dvd_id
            or row.get("parse_status") != "MATCHED" or not isinstance(relative, str)):
        raise DeleteCommitError("HOLDING_IDENTITY_MISMATCH")
    media = PurePosixPath(relative)
    parsed = parse_dvd_id(media.name)
    if parsed is None or parsed.dvd_id != dvd_id or media.is_absolute() or ".." in media.parts:
        raise DeleteCommitError("CANONICAL_PATH_MISMATCH")
    try:
        expected = canonical_destination(dvd_id, media.suffix).as_posix()
    except Exception as exc:
        raise DeleteCommitError("CANONICAL_PATH_MISMATCH") from exc
    if relative != expected:
        raise DeleteCommitError("CANONICAL_PATH_MISMATCH")
    return relative


_DELETE_SCRIPT = r'''import errno,json,os,stat,sys
root=sys.argv[1]; rel=sys.argv[2]; media_name=sys.argv[3]; expected_sha=sys.argv[4]
payload=json.load(sys.stdin); entries=payload.get('entries'); already=payload.get('already_removed') or []; recover_unknown=payload.get('recover_unknown') is True
def result(status,code,removed,remaining,retryable,dir_removed=False):
 print(json.dumps({'status':status,'code':code,'removed_entries':removed,'remaining_entries':remaining,'retryable':retryable,'title_directory_removed':dir_removed},separators=(',',':')))
def safe_rel(value):
 return isinstance(value,str) and value and not value.startswith('/') and '\\' not in value and '\x00' not in value and all(p not in ('','.','..') for p in value.split('/')) and os.path.normpath(value)==value
if not safe_rel(rel) or len(rel.split('/'))!=2 or not safe_rel(media_name) or '/' in media_name:
 result('FAILED_BEFORE_DELETE','UNSAFE_RELATIVE_PATH',already,[],False); raise SystemExit(0)
try:
 normalized=[]; names=set()
 for e in entries:
  if not isinstance(e,dict) or e.get('file_type')!='regular' or not safe_rel(e.get('relative_name')) or '/' in e['relative_name'] or e['relative_name'] in names:
   raise ValueError('manifest_invalid')
  names.add(e['relative_name']); normalized.append(e)
 normalized.sort(key=lambda x:x['relative_name'])
 encoded=json.dumps(normalized,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('utf-8')
 import hashlib
 if hashlib.sha256(encoded).hexdigest()!=expected_sha or media_name not in names or not set(already).issubset(names):
  raise ValueError('manifest_identity_mismatch')
 root_abs=os.path.abspath(root); title=os.path.abspath(os.path.join(root_abs,rel))
 if os.path.commonpath((root_abs,title))!=root_abs or title==root_abs:
  raise ValueError('root_escape')
 def ldir(path):
  st=os.lstat(path)
  if stat.S_ISLNK(st.st_mode): raise ValueError('symlink')
  if not stat.S_ISDIR(st.st_mode): raise ValueError('unsafe_component')
  return st
 root_stat=ldir(root_abs); parts=rel.split('/'); family=os.path.join(root_abs,parts[0]); fam_stat=ldir(family)
 checked=os.path.join(family,parts[1])
 try: title_stat=ldir(checked)
 except FileNotFoundError:
  if not recover_unknown: raise
  result('COMMITTED','RECOVERED_TITLE_ABSENT',sorted(names),[],False,True); raise SystemExit(0)
 if checked!=title or os.path.abspath(checked)!=title: raise ValueError('path_mismatch')
 expected={e['relative_name']:e for e in normalized}
 removed=list(already)
 actual={}
 with os.scandir(title) as listing:
  for ent in listing:
   st=ent.stat(follow_symlinks=False)
   if stat.S_ISLNK(st.st_mode): raise ValueError('symlink')
   if stat.S_ISDIR(st.st_mode): raise ValueError('nested_directory')
   if not stat.S_ISREG(st.st_mode): raise ValueError('unexpected_type')
   if ent.name in actual: raise ValueError('duplicate_name')
   actual[ent.name]=st
 if recover_unknown:
  if not set(actual).issubset(expected): raise ValueError('manifest_entries_changed')
  inferred=sorted(set(expected)-set(actual))
  if not set(already).issubset(inferred): raise ValueError('manifest_entries_changed')
  removed=inferred
  remaining={name:e for name,e in expected.items() if name not in set(removed)}
 else:
  remaining={name:e for name,e in expected.items() if name not in set(removed)}
  if set(actual)!=set(remaining): raise ValueError('manifest_entries_changed')
 def matches(st,e):
  return (stat.S_ISREG(st.st_mode) and int(st.st_size)==e['size_bytes'] and int(st.st_mtime_ns)==e['mtime_ns']
   and (e.get('inode') is None or int(st.st_ino)==e['inode'])
   and (e.get('device') is None or int(st.st_dev)==e['device']))
 for name,e in remaining.items():
  if not matches(actual[name],e): raise ValueError('entry_identity_changed')
 for name in sorted(remaining):
  e=remaining[name]; path=os.path.join(title,name)
  try:
   st=os.lstat(path)
   if not matches(st,e): raise ValueError('entry_identity_changed')
   os.unlink(path)
   removed.append(name)
  except Exception as exc:
   current_removed=set(removed); left=[n for n in sorted(expected) if n not in current_removed]
   retryable=False
   try:
    now_names=set(os.listdir(title))
    retryable=now_names==set(left) and all(matches(os.lstat(os.path.join(title,n)),expected[n]) for n in left)
   except Exception:
    pass
   state='FAILED_BEFORE_DELETE' if not removed else 'PARTIAL_DELETE'
   result(state,str(exc)[:64],removed,left,retryable); raise SystemExit(0)
 try:
  with os.scandir(title) as listing:
   extra=list(listing)
  if extra:
   result('PARTIAL_DELETE','UNEXPECTED_ENTRY_AFTER_DELETE',removed,[],False); raise SystemExit(0)
  os.rmdir(title)
  if os.path.lexists(title): raise ValueError('title_directory_remains')
  if os.path.islink(family) or not os.path.isdir(family): raise ValueError('family_parent_changed')
  fam_after=os.lstat(family)
  if (fam_after.st_dev,fam_after.st_ino)!=(fam_stat.st_dev,fam_stat.st_ino): raise ValueError('family_parent_changed')
  result('COMMITTED','OK',removed,[],False,True)
 except SystemExit:
  raise
 except Exception as exc:
  result('PARTIAL_DELETE',str(exc)[:64],removed,[],False,False)
except Exception as exc:
 state='PARTIAL_DELETE' if already else 'FAILED_BEFORE_DELETE'
 result(state,str(exc)[:64],already,[e.get('relative_name') for e in entries if isinstance(e,dict) and e.get('relative_name') not in set(already)],not bool(already))
'''


class DeleteManifestMutator:
    """Delete only exact manifest entries using the dedicated NAS SSH transport."""
    def __init__(self, ssh, *, library_root: str):
        self.ssh = ssh
        self.library_root = str(library_root)

    def delete(self, *, dvd_id: str, media_relative: str, entries: list[dict],
               manifest_sha256: str, already_removed: list[str] | None = None,
               recover_unknown: bool = False):
        media = PurePosixPath(media_relative)
        if media.is_absolute() or ".." in media.parts or "\\" in media_relative:
            raise DeleteCommitError("CANONICAL_PATH_MISMATCH")
        directory = media.parent.as_posix()
        expected_directory = PurePosixPath(canonical_destination(dvd_id, media.suffix).as_posix()).parent.as_posix()
        if directory != expected_directory:
            raise DeleteCommitError("CANONICAL_PATH_MISMATCH")
        try:
            normalized, digest, _ = canonical_manifest(entries)
            if digest != manifest_sha256:
                raise DeleteCommitError("MANIFEST_CHANGED")
            raw = self.ssh._run_python_json(
                _DELETE_SCRIPT,
                {"entries": normalized, "already_removed": list(already_removed or []),
                 "recover_unknown": bool(recover_unknown)},
                self.library_root, directory, media.name, manifest_sha256,
            )
            response = json.loads(raw)
            if not isinstance(response, dict) or response.get("status") not in {
                "COMMITTED", "PARTIAL_DELETE", "FAILED_BEFORE_DELETE"
            }:
                raise DeleteCommitError("MUTATOR_RESPONSE_INVALID")
            removed = response.get("removed_entries")
            remaining = response.get("remaining_entries")
            names = {item["relative_name"] for item in normalized}
            if (not isinstance(removed, list) or not isinstance(remaining, list)
                    or not set(removed).issubset(names) or not set(remaining).issubset(names)
                    or set(removed).intersection(remaining)):
                raise DeleteCommitError("MUTATOR_RESPONSE_INVALID")
            response["removed_total_bytes"] = sum(
                item["size_bytes"] for item in normalized if item["relative_name"] in set(removed)
            )
            return response
        except DeleteCommitError:
            raise
        except Exception as exc:
            raise DeleteCommitError("MUTATOR_UNAVAILABLE") from exc


class DurableDeleteProvenanceStore:
    """Durable SQLite audit and retry state; stores no raw token or absolute path."""
    def __init__(self, path: str | Path = PROVENANCE_DEFAULT_PATH):
        self.path = str(path)

    def _connect(self):
        p = Path(self.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("""
          CREATE TABLE IF NOT EXISTS library_deletions (
            operation_id TEXT PRIMARY KEY,
            schema_version INTEGER NOT NULL,
            dvd_id TEXT NOT NULL,
            holding_id INTEGER NOT NULL,
            source_identity_fingerprint TEXT NOT NULL,
            manifest_sha256 TEXT NOT NULL,
            file_count INTEGER NOT NULL,
            total_bytes INTEGER NOT NULL,
            manifest_entries_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            validated_at TEXT NOT NULL,
            committing_at TEXT NOT NULL,
            finished_at TEXT,
            removed_entries_json TEXT NOT NULL DEFAULT '[]',
            remaining_entries_json TEXT NOT NULL DEFAULT '[]',
            removed_file_count INTEGER NOT NULL DEFAULT 0,
            removed_total_bytes INTEGER NOT NULL DEFAULT 0,
            nas_delete_complete INTEGER NOT NULL DEFAULT 0,
            discovery_reconciled INTEGER,
            jellyfin_reconciled INTEGER,
            result_state TEXT NOT NULL
          )
        """)
        db.commit()
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass
        return db

    def begin(self, *, operation_id, dvd_id, holding_id, source_fingerprint,
              manifest_sha256, entries, created_at, validated_at):
        _, digest, total = canonical_manifest(entries)
        if digest != manifest_sha256:
            raise DeleteCommitError("MANIFEST_CHANGED")
        now = utc_now()
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""
              INSERT INTO library_deletions(
                operation_id,schema_version,dvd_id,holding_id,source_identity_fingerprint,
                manifest_sha256,file_count,total_bytes,manifest_entries_json,created_at,
                validated_at,committing_at,removed_entries_json,remaining_entries_json,
                result_state
              ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                operation_id, PROVENANCE_SCHEMA_VERSION, dvd_id, int(holding_id),
                source_fingerprint, manifest_sha256, len(entries), total,
                json.dumps(entries, sort_keys=True, separators=(",", ":")),
                created_at, validated_at, now, "[]",
                json.dumps([e["relative_name"] for e in entries]), "COMMITTING",
            ))
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        return self.get(operation_id)

    def get(self, operation_id, *, dvd_id=None):
        db = self._connect()
        try:
            if dvd_id is None:
                row = db.execute("SELECT * FROM library_deletions WHERE operation_id=?", (operation_id,)).fetchone()
            else:
                row = db.execute("SELECT * FROM library_deletions WHERE operation_id=? AND dvd_id=?",
                                 (operation_id, dvd_id)).fetchone()
        finally:
            db.close()
        if row is None:
            return None
        value = dict(row)
        value["manifest_entries"] = json.loads(value.pop("manifest_entries_json"))
        value["removed_entries"] = json.loads(value.pop("removed_entries_json"))
        value["remaining_entries"] = json.loads(value.pop("remaining_entries_json"))
        return value

    def finish(self, operation_id, *, result_state, removed_entries, remaining_entries,
               nas_delete_complete, discovery_reconciled=None, jellyfin_reconciled=None):
        current = self.get(operation_id)
        if not current:
            raise DeleteCommitError("PROVENANCE_NOT_FOUND")
        entries = {e["relative_name"]: e for e in current["manifest_entries"]}
        removed = list(dict.fromkeys(removed_entries))
        remaining = list(dict.fromkeys(remaining_entries))
        db = self._connect()
        try:
            db.execute("""
              UPDATE library_deletions SET
                finished_at=?,removed_entries_json=?,remaining_entries_json=?,
                removed_file_count=?,removed_total_bytes=?,nas_delete_complete=?,
                discovery_reconciled=?,jellyfin_reconciled=?,result_state=?
              WHERE operation_id=?
            """, (
                utc_now(), json.dumps(removed, separators=(",", ":")),
                json.dumps(remaining, separators=(",", ":")), len(removed),
                sum(entries[n]["size_bytes"] for n in removed if n in entries),
                1 if nas_delete_complete else 0,
                None if discovery_reconciled is None else int(bool(discovery_reconciled)),
                None if jellyfin_reconciled is None else int(bool(jellyfin_reconciled)),
                result_state, operation_id,
            ))
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        return self.get(operation_id)

    def resume_partial(self, operation_id):
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            cursor = db.execute(
                "UPDATE library_deletions SET result_state='COMMITTING',committing_at=?,finished_at=NULL WHERE operation_id=? AND result_state='PARTIAL_DELETE' AND nas_delete_complete=0",
                (utc_now(), operation_id),
            )
            if cursor.rowcount != 1:
                raise DeleteCommitError("PARTIAL_OPERATION_NOT_RESUMABLE")
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        return self.get(operation_id)

    def resume_uncertain(self, operation_id):
        """Keep durable in-flight state while a post-restart exact inventory resolves it."""
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            cursor = db.execute(
                "UPDATE library_deletions SET committing_at=?,finished_at=NULL WHERE operation_id=? AND result_state='COMMITTING' AND nas_delete_complete=0",
                (utc_now(), operation_id),
            )
            if cursor.rowcount != 1:
                raise DeleteCommitError("PARTIAL_OPERATION_NOT_RESUMABLE")
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        return self.get(operation_id)


def read_holding_for_reconcile(db_path: str, *, holding_id: int, dvd_id: str) -> dict:
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=5)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        row = db.execute(
            "SELECT holding_id,storage_root,relative_path,dvd_id,parse_status,present,size_bytes,mtime_ns FROM holdings WHERE holding_id=?",
            (int(holding_id),),
        ).fetchone()
    if row is None:
        raise DeleteCommitError("HOLDING_RECONCILE_ROW_MISSING")
    value = dict(row)
    canonical_media_path(value, dvd_id)
    return value


def reconcile_discovery_holding(db_path: str, *, holding_id: int, dvd_id: str,
                               source_fingerprint: str) -> bool:
    """Use the existing holdings lifecycle: mark this exact row present=0."""
    db = None
    try:
        db = sqlite3.connect(f"file:{Path(db_path).resolve()}?mode=rw", uri=True, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT holding_id,storage_root,relative_path,dvd_id,parse_status,present,size_bytes,mtime_ns FROM holdings WHERE holding_id=?",
                         (int(holding_id),)).fetchone()
        if row is None:
            raise DeleteCommitError("HOLDING_RECONCILE_ROW_MISSING")
        value = dict(row)
        relative = canonical_media_path(value, dvd_id)
        identity = dict(value); identity["present"] = 1
        if source_identity_fingerprint(identity, relative) != source_fingerprint:
            raise DeleteCommitError("HOLDING_RECONCILE_IDENTITY_CHANGED")
        if value["present"] == 0:
            db.commit()
            return True
        cursor = db.execute("""
          UPDATE holdings SET present=0
          WHERE holding_id=? AND storage_root='jav' AND relative_path=? AND dvd_id=?
            AND parse_status='MATCHED' AND present=1 AND size_bytes=? AND mtime_ns=?
        """, (int(holding_id), relative, dvd_id, value["size_bytes"], value["mtime_ns"]))
        if cursor.rowcount != 1:
            raise DeleteCommitError("HOLDING_RECONCILE_CONFLICT")
        db.commit()
        return True
    except Exception:
        if db is not None:
            db.rollback()
        raise
    finally:
        if db is not None:
            db.close()


class JellyfinDeleteReconciler:
    """GET exact path inventory, refresh only its item, then verify absence."""
    def __init__(self, client: JellyfinClient):
        self.client = client

    def _matches(self, expected_path):
        query = urlencode({
            "Recursive": "true", "Fields": "Path", "IncludeItemTypes": "Movie,Video",
            "StartIndex": "0", "Limit": str(MAX_JELLYFIN_ITEMS),
        })
        value = self.client._request("GET", "/Items?" + query)
        if not isinstance(value, dict) or not isinstance(value.get("Items"), list):
            raise DeleteCommitError("JELLYFIN_RESPONSE_INVALID")
        total = int(value.get("TotalRecordCount", len(value["Items"])))
        if total > MAX_JELLYFIN_ITEMS or len(value["Items"]) != total:
            raise DeleteCommitError("JELLYFIN_INVENTORY_INCOMPLETE")
        return [item for item in value["Items"] if isinstance(item, dict) and item.get("Path") == expected_path]

    def __call__(self, media_relative: str) -> bool:
        expected = jellyfin_media_path(media_relative)
        matches = self._matches(expected)
        if not matches:
            return True
        if len(matches) != 1:
            raise DeleteCommitError("JELLYFIN_PATH_AMBIGUOUS")
        item_id = str(matches[0].get("Id") or "").strip()
        if not item_id:
            raise DeleteCommitError("JELLYFIN_ITEM_ID_MISSING")
        query = urlencode({
            "MetadataRefreshMode": "Default", "ImageRefreshMode": "Default",
            "ReplaceAllImages": "false", "ReplaceMetadata": "false",
            "RegenerateThumbnail": "false",
        })
        self.client._request("POST", "/Items/" + quote(item_id, safe="") + "/Refresh?" + query)
        return not self._matches(expected)
