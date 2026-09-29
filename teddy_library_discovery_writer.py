"""Narrow host-side Discovery holding writer over a local Unix socket.

The wire protocol can only request health, exact holding preflight, or the
single conditional lifecycle transition ``present=1 -> present=0``.  It does
not accept SQL, paths, table/column names, or update values.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import socket
import socketserver
import sqlite3
import stat
import sys
from urllib.parse import quote

from teddy_library_delete_commit import canonical_media_path
from teddy_library_delete_dryrun import source_identity_fingerprint


PROTOCOL_VERSION = 1
MAX_FRAME_BYTES = 8192
MAX_RESPONSE_BYTES = 4096
DEFAULT_SOCKET_PATH = "/run/teddy-library-discovery-writer/writer.sock"
DVD_ID_RE = re.compile(r"^[A-Z0-9]+(?:-[A-Z0-9]+)+$")
FINGERPRINT_RE = re.compile(r"^[a-f0-9]{64}$")
OPERATION_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")
SAFE_ERROR_CODES = frozenset({
    "PROTOCOL_INVALID", "DB_BUSY", "HOLDING_NOT_FOUND", "HOLDING_CHANGED",
    "PROVENANCE_NOT_FOUND", "PROVENANCE_NOT_READY", "OPERATION_MISMATCH",
    "WRITER_UNAVAILABLE",
})
JOURNAL_TABLE = "library_delete_reconcile_journal"
JOURNAL_COLUMNS = (
    "operation_id", "dvd_id", "holding_id", "source_identity_fingerprint",
    "reconciled_at",
)
_LOG = logging.getLogger("teddy_library_discovery_writer")
_REQUEST_FIELDS = {
    "health": {"protocol_version", "operation"},
    "preflight_holding": {"protocol_version", "operation", "dvd_id", "holding_id", "source_identity_fingerprint"},
    "mark_absent": {"protocol_version", "operation", "operation_id", "dvd_id", "holding_id", "source_identity_fingerprint"},
}
_HOLDING_SELECT = "SELECT holding_id,storage_root,relative_path,dvd_id,parse_status,present,size_bytes,mtime_ns FROM holdings WHERE holding_id=?"


class WriterError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _validate_common(request: object) -> dict:
    if not isinstance(request, dict) or type(request.get("protocol_version")) is not int:
        raise WriterError("PROTOCOL_INVALID")
    operation = request.get("operation")
    if not isinstance(operation, str) or operation not in _REQUEST_FIELDS or set(request) != _REQUEST_FIELDS[operation]:
        raise WriterError("PROTOCOL_INVALID")
    if request["protocol_version"] != PROTOCOL_VERSION:
        raise WriterError("PROTOCOL_INVALID")
    if operation == "health":
        return request
    if (not isinstance(request.get("dvd_id"), str) or not DVD_ID_RE.fullmatch(request["dvd_id"])
            or type(request.get("holding_id")) is not int or request["holding_id"] <= 0
            or not isinstance(request.get("source_identity_fingerprint"), str)
            or not FINGERPRINT_RE.fullmatch(request["source_identity_fingerprint"])):
        raise WriterError("PROTOCOL_INVALID")
    if operation == "mark_absent" and (
            not isinstance(request.get("operation_id"), str)
            or not OPERATION_RE.fullmatch(request["operation_id"])):
        raise WriterError("PROTOCOL_INVALID")
    return request


def _db_uri(path: str, mode: str) -> str:
    return "file:" + quote(str(Path(path).absolute()), safe="/:\\") + "?mode=" + mode


def _connect(path: str, *, readonly: bool) -> sqlite3.Connection:
    try:
        db = sqlite3.connect(_db_uri(path, "ro" if readonly else "rw"), uri=True,
                             timeout=2.0, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=2000")
        if readonly:
            db.execute("PRAGMA query_only=ON")
        return db
    except sqlite3.OperationalError as exc:
        if "locked" in str(exc).lower() or "busy" in str(exc).lower():
            raise WriterError("DB_BUSY") from exc
        raise WriterError("WRITER_UNAVAILABLE") from exc


class DiscoveryHoldingWriter:
    """Bound to two administrator-configured host paths, never request paths."""
    def __init__(self, discovery_db: str, provenance_db: str):
        self.discovery_db = str(Path(discovery_db).absolute())
        self.provenance_db = str(Path(provenance_db).absolute())

    @staticmethod
    def _row(db, request):
        row = db.execute(_HOLDING_SELECT, (request["holding_id"],)).fetchone()
        if row is None:
            raise WriterError("HOLDING_NOT_FOUND")
        value = dict(row)
        if value["dvd_id"] != request["dvd_id"]:
            raise WriterError("HOLDING_CHANGED")
        if value["storage_root"] != "jav" or value["parse_status"] != "MATCHED":
            raise WriterError("HOLDING_CHANGED")
        try:
            relative = canonical_media_path(value, request["dvd_id"])
        except Exception as exc:
            raise WriterError("HOLDING_CHANGED") from exc
        identity = dict(value)
        identity["present"] = 1
        if source_identity_fingerprint(identity, relative) != request["source_identity_fingerprint"]:
            raise WriterError("HOLDING_CHANGED")
        return value, relative

    def preflight(self, request: dict) -> dict:
        db = _connect(self.discovery_db, readonly=False)
        try:
            db.execute("BEGIN IMMEDIATE")
            row, _relative = self._row(db, request)
            if row["present"] != 1:
                raise WriterError("HOLDING_CHANGED")
            db.execute("ROLLBACK")
            return {"protocol_version": PROTOCOL_VERSION, "status": "READY"}
        except sqlite3.OperationalError as exc:
            if db.in_transaction:
                db.execute("ROLLBACK")
            if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                raise WriterError("DB_BUSY") from exc
            raise WriterError("WRITER_UNAVAILABLE") from exc
        except Exception:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def _provenance(self, request: dict) -> dict:
        db = _connect(self.provenance_db, readonly=True)
        try:
            row = db.execute("""SELECT operation_id,dvd_id,holding_id,source_identity_fingerprint,
                file_count,manifest_entries_json,removed_file_count,removed_entries_json,remaining_entries_json,
                nas_delete_complete,result_state,discovery_reconciled FROM library_deletions WHERE operation_id=?""",
                (request["operation_id"],)).fetchone()
            if row is None:
                raise WriterError("PROVENANCE_NOT_FOUND")
            value = dict(row)
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                raise WriterError("DB_BUSY") from exc
            raise WriterError("PROVENANCE_NOT_FOUND") from exc
        finally:
            db.close()
        if (value["dvd_id"] != request["dvd_id"] or int(value["holding_id"]) != request["holding_id"]
                or value["source_identity_fingerprint"] != request["source_identity_fingerprint"]):
            raise WriterError("OPERATION_MISMATCH")
        try:
            manifest = json.loads(value["manifest_entries_json"])
            removed = json.loads(value["removed_entries_json"])
            remaining = json.loads(value["remaining_entries_json"])
        except (TypeError, ValueError):
            raise WriterError("PROVENANCE_NOT_READY")
        manifest_names = [entry.get("relative_name") for entry in manifest if isinstance(entry, dict)] if isinstance(manifest, list) else None
        if (value["nas_delete_complete"] != 1 or remaining != []
                or not isinstance(removed, list) or int(value["removed_file_count"]) != int(value["file_count"])
                or len(removed) != int(value["file_count"])
                or manifest_names is None or len(manifest_names) != int(value["file_count"])
                or not all(isinstance(name, str) for name in removed + manifest_names)
                or len(set(removed)) != len(removed) or set(removed) != set(manifest_names)
                or value["result_state"] not in {"RECONCILE_PENDING", "COMMITTED"}
                or (value["result_state"] == "COMMITTED" and value["discovery_reconciled"] != 1)):
            raise WriterError("PROVENANCE_NOT_READY")
        return value

    @staticmethod
    def _ensure_journal(db):
        # This DDL is called only after BEGIN IMMEDIATE inside mark_absent.
        # SQLite keeps it in the same transaction as the row transition.
        db.execute(f"""CREATE TABLE IF NOT EXISTS {JOURNAL_TABLE} (
            operation_id TEXT PRIMARY KEY,
            dvd_id TEXT NOT NULL,
            holding_id INTEGER NOT NULL,
            source_identity_fingerprint TEXT NOT NULL,
            reconciled_at TEXT NOT NULL
        )""")
        columns = tuple(row[1] for row in db.execute(
            f"PRAGMA table_info({JOURNAL_TABLE})").fetchall())
        if columns != JOURNAL_COLUMNS:
            raise WriterError("WRITER_UNAVAILABLE")

    @staticmethod
    def _journal_matches(row, request):
        return bool(row and row["operation_id"] == request["operation_id"]
                    and row["dvd_id"] == request["dvd_id"]
                    and int(row["holding_id"]) == request["holding_id"]
                    and row["source_identity_fingerprint"] == request["source_identity_fingerprint"])

    def mark_absent(self, request: dict) -> dict:
        # Validate durable evidence before opening the mutable DB transaction.
        provenance = self._provenance(request)
        db = _connect(self.discovery_db, readonly=False)
        try:
            db.execute("BEGIN IMMEDIATE")
            row, relative = self._row(db, request)
            self._ensure_journal(db)
            journal = db.execute(
                f"SELECT operation_id,dvd_id,holding_id,source_identity_fingerprint,reconciled_at "
                f"FROM {JOURNAL_TABLE} WHERE operation_id=?",
                (request["operation_id"],),
            ).fetchone()
            if row["present"] == 0:
                # The journal and row transition commit atomically. This also
                # recovers a crash before the web process updates provenance.
                if not self._journal_matches(journal, request):
                    raise WriterError("OPERATION_MISMATCH")
                db.execute("ROLLBACK")
                return {"protocol_version": PROTOCOL_VERSION, "status": "ALREADY_RECONCILED"}
            if row["present"] != 1:
                raise WriterError("HOLDING_CHANGED")
            if journal is not None:
                # A journal for this operation with present=1, or one with a
                # different identity, cannot be repaired by guessing.
                raise WriterError("OPERATION_MISMATCH")
            competing = db.execute(
                f"SELECT operation_id,dvd_id,holding_id,source_identity_fingerprint "
                f"FROM {JOURNAL_TABLE} WHERE holding_id=? OR dvd_id=? LIMIT 1",
                (request["holding_id"], request["dvd_id"]),
            ).fetchone()
            if competing is not None:
                raise WriterError("OPERATION_MISMATCH")
            db.execute(
                f"INSERT INTO {JOURNAL_TABLE} "
                "(operation_id,dvd_id,holding_id,source_identity_fingerprint,reconciled_at) "
                "VALUES(?,?,?,?,?)",
                (request["operation_id"], request["dvd_id"], request["holding_id"],
                 request["source_identity_fingerprint"],
                 datetime.now(timezone.utc).isoformat(timespec="seconds")),
            )
            cursor = db.execute("""UPDATE holdings SET present=0
                WHERE holding_id=? AND storage_root='jav' AND relative_path=? AND dvd_id=?
                  AND parse_status='MATCHED' AND present=1 AND size_bytes=? AND mtime_ns=?""",
                (request["holding_id"], relative, request["dvd_id"], row["size_bytes"], row["mtime_ns"]))
            if cursor.rowcount != 1:
                raise WriterError("HOLDING_CHANGED")
            db.execute("COMMIT")
            return {"protocol_version": PROTOCOL_VERSION, "status": "RECONCILED"}
        except sqlite3.OperationalError as exc:
            if db.in_transaction:
                db.execute("ROLLBACK")
            if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                raise WriterError("DB_BUSY") from exc
            raise WriterError("WRITER_UNAVAILABLE") from exc
        except sqlite3.IntegrityError as exc:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise WriterError("OPERATION_MISMATCH") from exc
        except sqlite3.DatabaseError as exc:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise WriterError("WRITER_UNAVAILABLE") from exc
        except Exception:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def dispatch(self, value: object) -> dict:
        request = _validate_common(value)
        if request["operation"] == "health":
            # Opening read-only proves path availability without changing DB.
            db = _connect(self.discovery_db, readonly=True)
            try:
                db.execute("SELECT 1 FROM holdings LIMIT 1").fetchone()
            finally:
                db.close()
            return {"protocol_version": PROTOCOL_VERSION, "status": "READY"}
        if request["operation"] == "preflight_holding":
            return self.preflight(request)
        return self.mark_absent(request)


def _read_frame(conn: socket.socket) -> bytes:
    data = bytearray()
    terminated = False
    while len(data) <= MAX_FRAME_BYTES:
        part = conn.recv(min(1024, MAX_FRAME_BYTES + 1 - len(data)))
        if not part:
            break
        newline = part.find(b"\n")
        if newline >= 0:
            data.extend(part[:newline])
            if part[newline + 1:].strip():
                raise WriterError("PROTOCOL_INVALID")
            terminated = True
            break
        data.extend(part)
    if not data or len(data) > MAX_FRAME_BYTES or not terminated:
        raise WriterError("PROTOCOL_INVALID")
    return bytes(data)


class _UnixHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(2.0)
        request = None
        try:
            raw = _read_frame(self.connection)
            def unique_pairs(pairs):
                value = {}
                for key, item in pairs:
                    if key in value:
                        raise ValueError("duplicate key")
                    value[key] = item
                return value
            request = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs)
            response = self.server.writer.dispatch(request)
        except WriterError as exc:
            _log_safe_writer_error(request, exc.code)
            response = {"protocol_version": PROTOCOL_VERSION, "status": "ERROR", "code": exc.code}
        except (UnicodeError, ValueError, TimeoutError, OSError):
            _log_safe_writer_error(request, "PROTOCOL_INVALID")
            response = {"protocol_version": PROTOCOL_VERSION, "status": "ERROR", "code": "PROTOCOL_INVALID"}
        payload = json.dumps(response, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(payload) <= MAX_RESPONSE_BYTES:
            self.wfile.write(payload)


def safe_writer_error_fields(request, code):
    """Return only bounded allowlisted diagnostics; never raw request data."""
    request = request if isinstance(request, dict) else {}
    operation = request.get("operation")
    if not isinstance(operation, str) or operation not in _REQUEST_FIELDS:
        operation = "unknown"
    dvd_id = request.get("dvd_id")
    if not isinstance(dvd_id, str) or not DVD_ID_RE.fullmatch(dvd_id):
        dvd_id = "unknown"
    holding_id = request.get("holding_id")
    if type(holding_id) is not int or holding_id <= 0:
        holding_id = 0
    if not isinstance(code, str) or code not in SAFE_ERROR_CODES:
        code = "WRITER_UNAVAILABLE"
    return {"operation": operation, "dvd_id": dvd_id,
            "holding_id": holding_id, "code": code}


def _log_safe_writer_error(request, code):
    fields = safe_writer_error_fields(request, code)
    _LOG.warning("writer request failed operation=%s dvd_id=%s holding_id=%d code=%s",
                 fields["operation"], fields["dvd_id"], fields["holding_id"], fields["code"])


class _UnixServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address, writer):
        self.writer = writer
        super().__init__(address, _UnixHandler, bind_and_activate=False)
        self.server_bind()
        os.chmod(address, 0o660)
        self.server_activate()


def _prepare_socket_parent(path: str) -> None:
    target = Path(path).absolute()
    parent = target.parent
    try:
        info = parent.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise WriterError("WRITER_UNAVAILABLE")
    except FileNotFoundError:
        parent.mkdir(mode=0o750, parents=True, exist_ok=False)
    try:
        os.chmod(parent, 0o750)
    except OSError as exc:
        raise WriterError("WRITER_UNAVAILABLE") from exc
    try:
        target.lstat()
    except FileNotFoundError:
        return
    # Do not unlink an unexpected/stale path at startup.
    raise WriterError("WRITER_UNAVAILABLE")


def serve(discovery_db: str, provenance_db: str, socket_path: str = DEFAULT_SOCKET_PATH):
    _prepare_socket_parent(socket_path)
    server = _UnixServer(socket_path, DiscoveryHoldingWriter(discovery_db, provenance_db))
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()


class UnixSocketDiscoveryWriterClient:
    """Strict bounded client used by the web app; it never opens Discovery DB."""
    def __init__(self, socket_path: str | None, timeout: float = 2.0):
        self.socket_path = socket_path
        self.timeout = min(max(float(timeout), 0.1), 5.0)

    def request(self, operation: str, **fields) -> dict:
        if not self.socket_path:
            raise WriterError("WRITER_UNAVAILABLE")
        request = {"protocol_version": PROTOCOL_VERSION, "operation": operation, **fields}
        _validate_common(request)
        raw = json.dumps(request, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(raw) > MAX_FRAME_BYTES:
            raise WriterError("PROTOCOL_INVALID")
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
                conn.settimeout(self.timeout)
                conn.connect(self.socket_path)
                conn.sendall(raw)
                response = bytearray()
                while len(response) <= MAX_RESPONSE_BYTES:
                    part = conn.recv(min(1024, MAX_RESPONSE_BYTES + 1 - len(response)))
                    if not part:
                        break
                    response.extend(part)
                    if b"\n" in part:
                        break
            if len(response) > MAX_RESPONSE_BYTES or not response.endswith(b"\n"):
                raise WriterError("WRITER_UNAVAILABLE")
            if response.count(b"\n") != 1:
                raise WriterError("WRITER_UNAVAILABLE")
            value = json.loads(response[:-1].decode("utf-8"))
            if (not isinstance(value, dict) or set(value) - {"protocol_version", "status", "code"}
                    or value.get("protocol_version") != PROTOCOL_VERSION):
                raise WriterError("WRITER_UNAVAILABLE")
            if value.get("status") == "ERROR":
                raise WriterError(value.get("code") if value.get("code") in {
                    "PROTOCOL_INVALID", "DB_BUSY", "HOLDING_NOT_FOUND", "HOLDING_CHANGED",
                    "PROVENANCE_NOT_FOUND", "PROVENANCE_NOT_READY", "OPERATION_MISMATCH",
                    "WRITER_UNAVAILABLE"} else "WRITER_UNAVAILABLE")
            if set(value) != {"protocol_version", "status"} or value["status"] not in {
                    "READY", "RECONCILED", "ALREADY_RECONCILED"}:
                raise WriterError("WRITER_UNAVAILABLE")
            return value
        except WriterError:
            raise
        except (OSError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            raise WriterError("WRITER_UNAVAILABLE") from exc

    def preflight_holding(self, *, dvd_id: str, holding_id: int, source_identity_fingerprint: str):
        return self.request("preflight_holding", dvd_id=dvd_id, holding_id=holding_id,
                            source_identity_fingerprint=source_identity_fingerprint)

    def mark_absent(self, *, operation_id: str, dvd_id: str, holding_id: int,
                    source_identity_fingerprint: str):
        return self.request("mark_absent", operation_id=operation_id, dvd_id=dvd_id,
                            holding_id=holding_id, source_identity_fingerprint=source_identity_fingerprint)


def main(argv=None):
    parser = argparse.ArgumentParser(description="narrow local Discovery reconcile writer")
    parser.add_argument("--discovery-db", required=True, help="administrator-configured canonical host DB path")
    parser.add_argument("--provenance-db", required=True, help="administrator-configured persistent provenance DB path")
    parser.add_argument("--socket", default=DEFAULT_SOCKET_PATH)
    args = parser.parse_args(argv)
    try:
        serve(args.discovery_db, args.provenance_db, args.socket)
    except (OSError, WriterError):
        print("writer startup failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
