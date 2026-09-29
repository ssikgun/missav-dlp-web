#!/usr/bin/env python3
"""Offline safety fixtures for exact Discovery recovery apply helper."""
from __future__ import annotations

from contextlib import contextmanager
import importlib.util
from pathlib import Path
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from teddy_discovery_operation_lock import OperationLockBusy
from teddy_library_discovery_writer import WriterError
from teddy_library_discovery_writer_smoke import fixture

_PATH = Path(__file__).with_name("reconcile_discovery_apply.py")
_SPEC = importlib.util.spec_from_file_location("reconcile_discovery_apply", _PATH)
_APPLY = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_APPLY)
ApplyError = _APPLY.ApplyError
apply_operation = _APPLY.apply_operation


def _prepare(tmp):
    f = fixture(tmp)
    f["store"].finish("op-fixture-1", result_state="RECONCILE_PENDING",
        removed_entries=[f["media"].name], remaining_entries=[], nas_delete_complete=True,
        discovery_reconciled=False, jellyfin_reconciled=None)
    db = sqlite3.connect(f["provenance_path"])
    db.execute("UPDATE library_deletions SET discovery_reconciled=0 WHERE operation_id='op-fixture-1'")
    db.commit(); db.close()
    row = sqlite3.connect(f["db_path"]).execute(
        "SELECT relative_path FROM holdings WHERE holding_id=?", (f["mark"]["holding_id"],)
    ).fetchone()
    _norm, digest, total = __import__("teddy_library_delete_dryrun").canonical_manifest(
        [{"relative_name": f["media"].name, "size_bytes": f["media"].stat().st_size,
          "mtime_ns": f["media"].stat().st_mtime_ns, "inode": f["media"].stat().st_ino,
          "device": f["media"].stat().st_dev, "file_type": "regular"}])
    checked = {"status":"RECOVERY_ELIGIBLE", "operation_id":"op-fixture-1",
        "dvd_id":f["dvd"], "holding_id":f["mark"]["holding_id"],
        "manifest_sha256":digest, "file_count":1, "total_bytes":total,
        "relative_path":row[0], "source_identity_fingerprint":f["fingerprint"],
        "recovery_phase":"READY_TO_MARK_ABSENT"}
    return f, checked


class Lock:
    status = "ACQUIRED"
    def __init__(self): self.released = False
    def release(self): self.released = True


class Writer:
    def __init__(self, f, mode="write", hook=None): self.f=f; self.mode=mode; self.calls=0; self.hook=hook
    def mark_absent(self, **_kwargs):
        self.calls += 1
        if self.mode == "error": raise WriterError("DB_BUSY")
        if self.mode == "verify-fail": return {"status":"RECONCILED"}
        result = self.f["writer"].dispatch(self.f["mark"])
        if self.hook: self.hook(self.f)
        return result


@contextmanager
def _global_ok(_path):
    yield


def _run(f, checked, **overrides):
    overrides.setdefault("title_lock_fn", lambda *_a: Lock())
    overrides.setdefault("global_lock_fn", _global_ok)
    return apply_operation("op-fixture-1", f["dvd"], discovery_db=str(f["db_path"]),
        provenance_db=str(f["provenance_path"]), writer_socket="unused",
        title_lock_dir="/tmp/fixture-title-locks",
        check_fn=lambda *_a, **_k:dict(checked), **overrides)


def _assert_flag(f, expected):
    db=sqlite3.connect(f["provenance_path"])
    row=db.execute("SELECT discovery_reconciled,result_state,jellyfin_reconciled FROM library_deletions WHERE operation_id='op-fixture-1'").fetchone()
    db.close()
    assert row == (expected,"RECONCILE_PENDING",None), row


def main():
    # A: phase A exact writer mutation, journal verification, narrow provenance flag.
    with tempfile.TemporaryDirectory(prefix="reconcile-apply-a-") as tmp:
        f,c=_prepare(tmp); writer=Writer(f); lock=Lock()
        result=_run(f,c,writer_client=writer,title_lock_fn=lambda *_a:lock)
        assert result["writer_result"] == "RECONCILED" and result["recovery_phase"] == "READY_TO_MARK_ABSENT"
        assert writer.calls == 1 and lock.released
        assert sqlite3.connect(f["db_path"]).execute("SELECT present FROM holdings WHERE holding_id=1").fetchone()[0] == 0
        _assert_flag(f,1)

    # B: simulate crash after writer commit but before provenance update; phase B retries idempotently.
    with tempfile.TemporaryDirectory(prefix="reconcile-apply-b-") as tmp:
        f,c=_prepare(tmp); f["writer"].dispatch(f["mark"])
        c["recovery_phase"]="WRITER_DONE_PROVENANCE_PENDING"
        writer=Writer(f); result=_run(f,c,writer_client=writer)
        assert result["writer_result"] == "ALREADY_RECONCILED" and writer.calls == 1
        _assert_flag(f,1)

    # E: per-title lock busy and F: global lock busy both avoid the writer.
    with tempfile.TemporaryDirectory(prefix="reconcile-apply-busy-") as tmp:
        f,c=_prepare(tmp); writer=Writer(f)
        class Busy: status="BUSY"
        try: _run(f,c,writer_client=writer,title_lock_fn=lambda *_a:Busy())
        except ApplyError as exc: assert exc.code == "TITLE_LOCK_BUSY"
        else: raise AssertionError("title lock busy accepted")
        assert writer.calls == 0; _assert_flag(f,0)

    with tempfile.TemporaryDirectory(prefix="reconcile-apply-global-busy-") as tmp:
        f,c=_prepare(tmp); writer=Writer(f)
        @contextmanager
        def busy(_path): raise OperationLockBusy("fixture"); yield
        try: _run(f,c,writer_client=writer,global_lock_fn=busy)
        except ApplyError as exc: assert exc.code == "GLOBAL_LOCK_BUSY"
        else: raise AssertionError("global lock busy accepted")
        assert writer.calls == 0; _assert_flag(f,0)

    # G: writer failure leaves provenance untouched.
    with tempfile.TemporaryDirectory(prefix="reconcile-apply-writer-fail-") as tmp:
        f,c=_prepare(tmp); writer=Writer(f,"error")
        try: _run(f,c,writer_client=writer)
        except ApplyError as exc: assert exc.code == "DB_BUSY"
        else: raise AssertionError("writer failure ignored")
        _assert_flag(f,0)

    # H: failed post-writer identity verification must not flag provenance.
    with tempfile.TemporaryDirectory(prefix="reconcile-apply-verify-fail-") as tmp:
        f,c=_prepare(tmp); writer=Writer(f,"verify-fail")
        try: _run(f,c,writer_client=writer)
        except ApplyError as exc: assert exc.code == "DISCOVERY_VERIFY_FAILED"
        else: raise AssertionError("missing writer mutation accepted")
        _assert_flag(f,0)

    # I: concurrent provenance state change is never blindly overwritten.
    with tempfile.TemporaryDirectory(prefix="reconcile-apply-conflict-") as tmp:
        f,c=_prepare(tmp)
        def conflict(fixture):
            db=sqlite3.connect(fixture["provenance_path"])
            db.execute("UPDATE library_deletions SET discovery_reconciled=1 WHERE operation_id='op-fixture-1'")
            db.commit(); db.close()
        writer=Writer(f,hook=conflict)
        try: _run(f,c,writer_client=writer)
        except ApplyError as exc: assert exc.code == "PROVENANCE_CONFLICT"
        else: raise AssertionError("conditional provenance conflict ignored")
        _assert_flag(f,1)

    print("Stage13-F2M-C3 exact Discovery apply helper smoke: OK")


if __name__ == "__main__":
    main()
