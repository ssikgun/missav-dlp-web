"""Offline-only safety tests for the narrow Unix-socket holding writer."""
from __future__ import annotations

import json
import io
import logging
from pathlib import Path
import socket
import sqlite3
import stat
import tempfile
import threading
import time

from teddy_library_delete_commit import DurableDeleteProvenanceStore
from teddy_library_delete_dryrun import canonical_manifest, source_identity_fingerprint
from teddy_discovery_organizer import canonical_destination
from teddy_library_discovery_writer import (
    DiscoveryHoldingWriter, JOURNAL_TABLE, PROTOCOL_VERSION,
    UnixSocketDiscoveryWriterClient, WriterError, _UnixServer,
    _log_safe_writer_error, _prepare_socket_parent,
)


def fixture(tmp):
    dvd = "ABCD-123"
    title = Path(tmp) / "nas" / "ABCD" / dvd
    title.mkdir(parents=True)
    media = title / f"{dvd}.mp4"
    media.write_bytes(b"fixture-media")
    media_stat = media.stat()
    relative = canonical_destination(dvd, ".mp4").as_posix()
    db_path = Path(tmp) / "discovery.sqlite3"
    db = sqlite3.connect(db_path)
    db.execute("CREATE TABLE holdings(holding_id INTEGER PRIMARY KEY,storage_root TEXT,relative_path TEXT,dvd_id TEXT,parse_status TEXT,size_bytes INTEGER,mtime_ns INTEGER,discovered_by TEXT,present INTEGER,first_seen_at TEXT,last_seen_at TEXT)")
    db.execute("INSERT INTO holdings(storage_root,relative_path,dvd_id,parse_status,size_bytes,mtime_ns,discovered_by,present,first_seen_at,last_seen_at) VALUES('jav',?,?,'MATCHED',?,?,'fixture',1,'2026-01-01','2026-01-01')", (relative,dvd,media_stat.st_size,media_stat.st_mtime_ns))
    db.commit(); db.close()
    names = ("holding_id","storage_root","relative_path","dvd_id","parse_status","present","size_bytes","mtime_ns")
    row = dict(zip(names, sqlite3.connect(db_path).execute(
        "SELECT holding_id,storage_root,relative_path,dvd_id,parse_status,present,size_bytes,mtime_ns FROM holdings WHERE dvd_id=?",(dvd,)).fetchone()))
    fingerprint = source_identity_fingerprint(row, relative)
    # Add one unrelated matching holding to prove the writer updates one row.
    db = sqlite3.connect(db_path)
    db.execute("INSERT INTO holdings(storage_root,relative_path,dvd_id,parse_status,size_bytes,mtime_ns,discovered_by,present) VALUES('jav','EFGH/EFGH-777/EFGH-777.mp4','EFGH-777','MATCHED',77,88,'fixture',1)")
    db.execute("CREATE TABLE unrelated(k TEXT PRIMARY KEY,v TEXT)")
    db.execute("INSERT INTO unrelated VALUES('keep','same')")
    db.commit(); db.close()
    provenance_path = Path(tmp) / "provenance.sqlite3"
    store = DurableDeleteProvenanceStore(provenance_path)
    entries = [{"relative_name": media.name, "size_bytes": media.stat().st_size,
                "mtime_ns": media.stat().st_mtime_ns, "inode": media.stat().st_ino,
                "device": media.stat().st_dev, "file_type": "regular"}]
    _norm, manifest_sha, _total = canonical_manifest(entries)
    record = store.begin(operation_id="op-fixture-1", dvd_id=dvd,
        holding_id=int(row["holding_id"]), source_fingerprint=fingerprint,
        manifest_sha256=manifest_sha, entries=entries, created_at="2026-01-01T00:00:00Z",
        validated_at="2026-01-01T00:01:00Z")
    store.finish(record["operation_id"], result_state="RECONCILE_PENDING",
        removed_entries=[media.name], remaining_entries=[], nas_delete_complete=True)
    writer = DiscoveryHoldingWriter(str(db_path), str(provenance_path))
    request = {"protocol_version": PROTOCOL_VERSION, "operation": "preflight_holding",
        "dvd_id": dvd, "holding_id": int(row["holding_id"]),
        "source_identity_fingerprint": fingerprint}
    mark = {"protocol_version": PROTOCOL_VERSION, "operation": "mark_absent",
        "operation_id": record["operation_id"], "dvd_id": dvd,
        "holding_id": int(row["holding_id"]), "source_identity_fingerprint": fingerprint}
    return locals()


def raw_request(path, raw):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(2)
        client.connect(str(path)); client.sendall(raw)
        data = bytearray()
        while b"\n" not in data:
            part = client.recv(1024)
            if not part: break
            data.extend(part)
    return json.loads(bytes(data).split(b"\n", 1)[0])


def main():
    # Safe writer diagnostics preserve the allowlisted error code and never
    # serialize attacker supplied paths, fingerprints, tokens, or raw payload.
    capture = io.StringIO()
    handler = logging.StreamHandler(capture)
    logger = logging.getLogger("teddy_library_discovery_writer")
    logger.addHandler(handler); logger.setLevel(logging.WARNING)
    bad_request = {"operation":"mark_absent", "dvd_id":"ABCD-123", "holding_id":7,
                   "operation_id":"op-fixture-1", "source_identity_fingerprint":"f"*64,
                   "prepare_token":"fixture-secret-token", "path":"/sensitive/nas"}
    expected_codes = ("PROVENANCE_NOT_FOUND", "PROVENANCE_NOT_READY", "OPERATION_MISMATCH",
                      "HOLDING_CHANGED", "DB_BUSY", "WRITER_UNAVAILABLE", "PROTOCOL_INVALID")
    for code in expected_codes:
        _log_safe_writer_error(bad_request, code)
    _log_safe_writer_error({"operation": ["untrusted"], "dvd_id": ["bad"]}, "PROTOCOL_INVALID")
    logger.removeHandler(handler)
    logged = capture.getvalue()
    for code in expected_codes: assert "code=" + code in logged
    assert "fixture-secret-token" not in logged and "/sensitive/nas" not in logged
    assert "f" * 64 not in logged and "prepare_token" not in logged
    assert "operation=unknown dvd_id=unknown holding_id=0 code=PROTOCOL_INVALID" in logged

    with tempfile.TemporaryDirectory(prefix="library-writer-fixture-") as tmp:
        f = fixture(tmp)
        before = sqlite3.connect(f["db_path"]).execute(
            "SELECT holding_id,present FROM holdings ORDER BY holding_id").fetchall()
        health = f["writer"].dispatch({"protocol_version": 1, "operation": "health"})
        assert health["status"] == "READY"
        assert f["writer"].dispatch(f["request"])["status"] == "READY"
        assert sqlite3.connect(f["db_path"]).execute(
            "SELECT holding_id,present FROM holdings ORDER BY holding_id").fetchall() == before
        assert sqlite3.connect(f["db_path"]).execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (JOURNAL_TABLE,)).fetchone() is None

        for altered in (
            dict(f["request"], dvd_id="NO-ROW"),
            dict(f["request"], holding_id=99999),
            dict(f["request"], source_identity_fingerprint="0" * 64),
        ):
            try: f["writer"].dispatch(altered)
            except WriterError: pass
            else: raise AssertionError("identity mismatch accepted")
        for bad in (
            {"protocol_version": 1, "operation": "health", "sql": "DELETE FROM holdings"},
            {"protocol_version": 1, "operation": "unknown"},
            {"protocol_version": 1, "operation": "mark_absent", "path": "/tmp/db"},
            {"protocol_version": 1, "operation": "mark_absent", "operation_id": "x",
             "dvd_id": f["dvd"], "holding_id": 1, "source_identity_fingerprint": "a" * 64,
             "present": 0},
        ):
            try: f["writer"].dispatch(bad)
            except WriterError as exc: assert exc.code == "PROTOCOL_INVALID"
            else: raise AssertionError("unsafe protocol request accepted")

        # Missing and incomplete provenance are rejected before Discovery writes.
        no_prov = dict(f["mark"], operation_id="missing-operation")
        for request in (no_prov,):
            try: f["writer"].dispatch(request)
            except WriterError as exc: assert exc.code == "PROVENANCE_NOT_FOUND"
            else: raise AssertionError("missing provenance accepted")
        store = f["store"]
        store.finish("op-fixture-1", result_state="RECONCILE_PENDING",
            removed_entries=[f["media"].name], remaining_entries=["remaining.mp4"], nas_delete_complete=True)
        try: f["writer"].dispatch(f["mark"])
        except WriterError as exc: assert exc.code == "PROVENANCE_NOT_READY"
        else: raise AssertionError("remaining entries accepted")
        store.finish("op-fixture-1", result_state="RECONCILE_PENDING",
            removed_entries=[], remaining_entries=[], nas_delete_complete=True)
        try: f["writer"].dispatch(f["mark"])
        except WriterError as exc: assert exc.code == "PROVENANCE_NOT_READY"
        else: raise AssertionError("removed count mismatch accepted")
        store.finish("op-fixture-1", result_state="PARTIAL_DELETE",
            removed_entries=[f["media"].name], remaining_entries=[], nas_delete_complete=False)
        try: f["writer"].dispatch(f["mark"])
        except WriterError as exc: assert exc.code == "PROVENANCE_NOT_READY"
        else: raise AssertionError("NAS incomplete evidence accepted")
        store.finish("op-fixture-1", result_state="RECONCILE_PENDING",
            removed_entries=[f["media"].name], remaining_entries=[], nas_delete_complete=True)

        # Strict framing and field allowlist over actual Unix socket.
        sock_path = Path(tmp) / "sock" / "writer.sock"
        _prepare_socket_parent(str(sock_path))
        server = _UnixServer(str(sock_path), f["writer"])
        assert stat.S_IMODE(sock_path.parent.stat().st_mode) == 0o750
        assert stat.S_IMODE(sock_path.stat().st_mode) == 0o660
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        client = UnixSocketDiscoveryWriterClient(str(sock_path))
        assert client.request("health")["status"] == "READY"
        assert client.preflight_holding(dvd_id=f["dvd"], holding_id=f["request"]["holding_id"],
            source_identity_fingerprint=f["fingerprint"])["status"] == "READY"
        bad_extra = raw_request(sock_path, b'{"protocol_version":1,"operation":"health","x":1}\n')
        assert bad_extra["code"] == "PROTOCOL_INVALID"
        assert str(f["db_path"]) not in json.dumps(bad_extra)
        assert "token" not in json.dumps(bad_extra).casefold()
        assert raw_request(sock_path, b"x" * 8193 + b"\n")["code"] == "PROTOCOL_INVALID"
        assert raw_request(sock_path, json.dumps({"protocol_version":1,"operation":"health"}).encode()+b"\nextra\n")["code"] == "PROTOCOL_INVALID"

        result = client.mark_absent(operation_id="op-fixture-1", dvd_id=f["dvd"],
            holding_id=f["request"]["holding_id"], source_identity_fingerprint=f["fingerprint"])
        assert result["status"] == "RECONCILED"
        rows = sqlite3.connect(f["db_path"]).execute(
            "SELECT dvd_id,present FROM holdings ORDER BY holding_id").fetchall()
        assert rows == [(f["dvd"], 0), ("EFGH-777", 1)]
        journal = sqlite3.connect(f["db_path"]).execute(
            f"SELECT operation_id,dvd_id,holding_id,source_identity_fingerprint,reconciled_at FROM {JOURNAL_TABLE}").fetchall()
        assert len(journal) == 1 and journal[0][:4] == (
            "op-fixture-1", f["dvd"], f["request"]["holding_id"], f["fingerprint"])
        assert sqlite3.connect(f["db_path"]).execute("SELECT * FROM unrelated").fetchall() == [("keep", "same")]
        # Simulate web process crash after writer commit, before provenance
        # discovery_reconciled=1. Restart replay is safe for this operation.
        server.shutdown(); server.server_close(); thread.join(timeout=2); sock_path.unlink()
        server2 = _UnixServer(str(sock_path), DiscoveryHoldingWriter(f["db_path"], str(f["provenance_path"])))
        thread2 = threading.Thread(target=server2.serve_forever, daemon=True); thread2.start()
        assert UnixSocketDiscoveryWriterClient(str(sock_path)).mark_absent(
            operation_id="op-fixture-1", dvd_id=f["dvd"], holding_id=f["request"]["holding_id"],
            source_identity_fingerprint=f["fingerprint"])["status"] == "ALREADY_RECONCILED"
        store.finish("op-fixture-1", result_state="RECONCILE_PENDING",
            removed_entries=[f["media"].name], remaining_entries=[], nas_delete_complete=True,
            discovery_reconciled=True)
        assert UnixSocketDiscoveryWriterClient(str(sock_path)).mark_absent(
            operation_id="op-fixture-1", dvd_id=f["dvd"], holding_id=f["request"]["holding_id"],
            source_identity_fingerprint=f["fingerprint"])["status"] == "ALREADY_RECONCILED"
        second_record = store.begin(operation_id="op-fixture-2", dvd_id=f["dvd"],
            holding_id=int(f["request"]["holding_id"]), source_fingerprint=f["fingerprint"],
            manifest_sha256=f["manifest_sha"], entries=f["entries"],
            created_at="2026-01-02T00:00:00Z", validated_at="2026-01-02T00:01:00Z")
        store.finish(second_record["operation_id"], result_state="RECONCILE_PENDING",
            removed_entries=[f["media"].name], remaining_entries=[], nas_delete_complete=True)
        wrong_op = dict(f["mark"], operation_id="op-fixture-2")
        try: server2.writer.dispatch(wrong_op)
        except WriterError as exc: assert exc.code == "OPERATION_MISMATCH"
        else: raise AssertionError("different operation claimed absent holding")
        server2.shutdown(); server2.server_close(); thread2.join(timeout=2); sock_path.unlink()

        # Provenance identity mismatch cannot mutate; DB busy is bounded.
        altered = dict(f["mark"], source_identity_fingerprint="f" * 64)
        try: f["writer"].dispatch(altered)
        except WriterError as exc: assert exc.code == "OPERATION_MISMATCH"
        else: raise AssertionError("provenance mismatch accepted")
        lock = sqlite3.connect(f["db_path"], timeout=0.1, isolation_level=None)
        lock.execute("BEGIN IMMEDIATE")
        started = time.monotonic()
        try:
            f["writer"].dispatch(f["request"])
        except (WriterError, sqlite3.OperationalError):
            assert time.monotonic() - started < 3.0
        else: raise AssertionError("busy database did not fail closed")
        finally:
            lock.execute("ROLLBACK"); lock.close()

        # Socket startup rejects symlink and unexpected pre-existing file.
        unsafe = Path(tmp) / "unsafe"; unsafe.mkdir()
        target = Path(tmp) / "target"; target.touch()
        link = unsafe / "writer.sock"; link.symlink_to(target)
        try: _prepare_socket_parent(str(link))
        except WriterError: pass
        else: raise AssertionError("socket symlink accepted")
        link.unlink(); link.touch()
        try: _prepare_socket_parent(str(link))
        except WriterError: pass
        else: raise AssertionError("existing socket path accepted")
        try:
            UnixSocketDiscoveryWriterClient(str(Path(tmp)/"missing.sock")).request("health")
        except WriterError as exc: assert exc.code == "WRITER_UNAVAILABLE"
        else: raise AssertionError("unavailable client did not fail closed")
        try:
            UnixSocketDiscoveryWriterClient(None).preflight_holding(dvd_id=f["dvd"],
                holding_id=f["request"]["holding_id"], source_identity_fingerprint=f["fingerprint"])
        except WriterError as exc: assert exc.code == "WRITER_UNAVAILABLE"
        else: raise AssertionError("unset client did not fail closed")

    # present=0 without a same-operation journal must never be claimed as
    # reconciled. DDL is rolled back along with the rejected transaction.
    for foreign in (False, True):
        with tempfile.TemporaryDirectory(prefix="library-writer-absent-guard-") as tmp:
            f = fixture(tmp)
            db = sqlite3.connect(f["db_path"])
            db.execute("UPDATE holdings SET present=0 WHERE holding_id=?", (f["mark"]["holding_id"],))
            if foreign:
                db.execute(f"CREATE TABLE {JOURNAL_TABLE}(operation_id TEXT PRIMARY KEY,dvd_id TEXT NOT NULL,holding_id INTEGER NOT NULL,source_identity_fingerprint TEXT NOT NULL,reconciled_at TEXT NOT NULL)")
                db.execute(f"INSERT INTO {JOURNAL_TABLE} VALUES(?,?,?,?,?)",(
                    "op-foreign",f["dvd"],f["mark"]["holding_id"],f["fingerprint"],"2026-01-01T00:00:00Z"))
            db.commit(); db.close()
            try: f["writer"].dispatch(f["mark"])
            except WriterError as exc: assert exc.code == "OPERATION_MISMATCH"
            else: raise AssertionError("present=0 without exact journal accepted")
            db=sqlite3.connect(f["db_path"])
            assert db.execute("SELECT present FROM holdings WHERE holding_id=?",(f["mark"]["holding_id"],)).fetchone()[0] == 0
            assert db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(JOURNAL_TABLE,)).fetchone() is None if not foreign else True
            db.close()

    # Failure after journal insertion but during the exact UPDATE rolls back
    # both DDL/INSERT and leaves the holding present.
    with tempfile.TemporaryDirectory(prefix="library-writer-rollback-") as tmp:
        f=fixture(tmp); db=sqlite3.connect(f["db_path"])
        db.execute("CREATE TRIGGER reject_exact_update BEFORE UPDATE OF present ON holdings WHEN OLD.holding_id=? BEGIN SELECT RAISE(ABORT,'fixture failure'); END".replace("?",str(f["mark"]["holding_id"])))
        db.commit(); db.close()
        try: f["writer"].dispatch(f["mark"])
        except WriterError as exc: assert exc.code == "OPERATION_MISMATCH"
        else: raise AssertionError("fixture update failure was accepted")
        db=sqlite3.connect(f["db_path"])
        assert db.execute("SELECT present FROM holdings WHERE holding_id=?",(f["mark"]["holding_id"],)).fetchone()[0] == 1
        assert db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(JOURNAL_TABLE,)).fetchone() is None
        db.close()

    print("Stage13-F2B offline Discovery writer safety smoke: OK")


if __name__ == "__main__":
    main()
