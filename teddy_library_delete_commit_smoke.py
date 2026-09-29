"""Offline-only Stage13-F1 exact deletion and reconciliation safety smoke."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading

from flask import Flask

from teddy_discovery_organizer import canonical_destination
from teddy_library_api import _holding_rows, create_library_blueprint
from teddy_library_delete_commit import (
    CONFIRM_PHRASE, DeleteManifestMutator, DurableDeleteProvenanceStore,
    reconcile_discovery_holding,
)
from teddy_library_delete_dryrun import (DeleteManifestReader, PrepareTokenRegistry,
    source_identity_fingerprint)
from teddy_library_discovery_writer import WriterError
from teddy_library_discovery_writer import (
    DiscoveryHoldingWriter, UnixSocketDiscoveryWriterClient, _UnixServer, _prepare_socket_parent,
)
from teddy_library_delete_activity import (
    ACTIVITY_STATE_UNAVAILABLE, ACTIVE_ORGANIZER, ACTIVE_SUBTITLE, IDLE,
    ActivityDecision,
)
from teddy_library_delete_dryrun_smoke import make_fixture
from teddy_discovery_jellyfin import jellyfin_media_path
from teddy_discovery_subtitle import validate_canonical_holding


class FixtureSSH:
    def __init__(self):
        self.calls = 0

    def _run_python(self, script, *args):
        result = subprocess.run([sys.executable, "-c", script, *map(str, args)],
                                text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr or "fixture read failed")
        return result.stdout

    def _run_python_json(self, script, payload, *args):
        self.calls += 1
        result = subprocess.run([sys.executable, "-c", script, *map(str, args)],
                                input=json.dumps(payload), text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr or "fixture mutator failed")
        return result.stdout


def setup_app(tmp, *, gate="true", discovery_ok=True, jellyfin_ok=True, partial_once=False,
              discovery_writer_client=None, activity_decisions=None):
    root, title, media, db_path, relative, dvd = make_fixture(tmp)
    (title / f"{dvd}.ko.srt").write_text("fixture subtitle", encoding="utf-8")
    sibling = title.parent / "SIBL-456"
    sibling.mkdir()
    (sibling / "preserve.txt").write_text("keep", encoding="utf-8")
    ssh = FixtureSSH()
    reader = DeleteManifestReader(ssh, library_root=str(root))
    mutator = DeleteManifestMutator(ssh, library_root=str(root))
    provenance_path = Path(tmp) / "provenance.sqlite3"
    registry = PrepareTokenRegistry()
    flags = {"discovery_ok": discovery_ok, "jellyfin_ok": jellyfin_ok}
    expected_media = jellyfin_media_path(relative)
    jf_paths = {expected_media}
    jellyfin_reads = []
    jellyfin_refreshes = []

    def loader():
        jellyfin_reads.append("GET")
        return jf_paths

    def reconcile_discovery(path, **kwargs):
        if not flags["discovery_ok"]:
            raise RuntimeError("fixture reconcile failure")
        return reconcile_discovery_holding(path, **kwargs)

    def reconcile_jellyfin(media_relative):
        assert media_relative == relative
        jellyfin_refreshes.append("refresh-exact-item")
        if not flags["jellyfin_ok"]:
            raise RuntimeError("fixture refresh failure")
        jf_paths.discard(expected_media)
        return True

    class PartialOnce:
        def __init__(self, delegate):
            self.delegate = delegate
            self.failed = False

        def delete(self, **kwargs):
            if partial_once and not self.failed:
                self.failed = True
                entries = kwargs["entries"]
                first = entries[0]
                (title / first["relative_name"]).unlink()
                return {"status": "PARTIAL_DELETE", "removed_entries": [first["relative_name"]],
                        "remaining_entries": [e["relative_name"] for e in entries[1:]],
                        "retryable": True, "removed_total_bytes": first["size_bytes"]}
            return self.delegate.delete(**kwargs)

    class FixtureActivityGuard:
        def __init__(self, decisions):
            self.decisions = list(decisions or [IDLE])
            self.calls = []

        def check(self, dvd_id):
            self.calls.append(dvd_id)
            value = self.decisions.pop(0) if len(self.decisions) > 1 else self.decisions[0]
            return ActivityDecision(value)

    activity_guard = FixtureActivityGuard(activity_decisions)

    app = Flask("delete-commit-fixture")
    app.secret_key = "fixture-only-key"
    blueprint_kwargs = dict(
        db_path=str(db_path), rollout_path="", nas_reader=object(), delete_manifest_reader=reader,
        delete_token_registry=registry, delete_mutator=PartialOnce(mutator),
        provenance_store_factory=lambda: DurableDeleteProvenanceStore(provenance_path),
        jellyfin_delete_reconciler=reconcile_jellyfin, jellyfin_loader=loader,
        delete_activity_guard=activity_guard,
    )
    if discovery_writer_client is None:
        blueprint_kwargs["discovery_reconciler"] = reconcile_discovery
    else:
        blueprint_kwargs["discovery_writer_client"] = discovery_writer_client
    app.register_blueprint(create_library_blueprint(**blueprint_kwargs))
    client = app.test_client()
    with client.session_transaction() as session:
        session["teddy_authenticated"] = True
    previous = os.environ.get("TEDDY_PUBLIC_ORIGIN")
    os.environ["TEDDY_PUBLIC_ORIGIN"] = "http://localhost"
    if gate is None:
        os.environ.pop("TEDDY_LIBRARY_DELETE_ENABLED", None)
    else:
        os.environ["TEDDY_LIBRARY_DELETE_ENABLED"] = gate
    return locals()


def post(ctx, action, body, *, authenticated=True, origin="http://localhost", intent=None):
    client = ctx["client"]
    path = f"/api/library/{ctx['dvd']}/delete/{action}"
    headers = {"Origin": origin, "X-Teddy-Delete-Intent": intent or action}
    if not authenticated:
        client = ctx["app"].test_client()
    return client.post(path, json=body, base_url="http://localhost", headers=headers)


def prepared_validated(ctx):
    prepared = post(ctx, "prepare", {})
    assert prepared.status_code == 200, prepared.get_json()
    data = prepared.get_json()
    validated = post(ctx, "validate", {"prepare_token": data["prepare_token"],
        "typed_dvd_id": ctx["dvd"], "acknowledge": True})
    assert validated.status_code == 200 and validated.get_json()["status"] == "READY_FOR_COMMIT"
    return data["prepare_token"], data


def commit_body(ctx, token):
    return {"prepare_token": token, "typed_dvd_id": ctx["dvd"],
            "acknowledge_permanent_delete": True, "confirm_phrase": CONFIRM_PHRASE}


class UnavailableWriter:
    def preflight_holding(self, **_kwargs):
        raise WriterError("WRITER_UNAVAILABLE")

    def mark_absent(self, **_kwargs):
        raise AssertionError("writer reconcile must not be reached")


class CountingPreflightWriter:
    def __init__(self):
        self.preflight_calls = 0

    def preflight_holding(self, **_kwargs):
        self.preflight_calls += 1
        return {"status": "READY"}

    def mark_absent(self, **_kwargs):
        raise AssertionError("activity rejection must occur before reconcile")


def main():
    # A target already active fails before writer preflight and before NAS.
    with tempfile.TemporaryDirectory(prefix="delete-activity-early-") as tmp:
        writer = CountingPreflightWriter()
        ctx = setup_app(tmp, discovery_writer_client=writer,
                        activity_decisions=[ACTIVE_ORGANIZER])
        token, _ = prepared_validated(ctx)
        response = post(ctx, "commit", commit_body(ctx, token))
        assert response.status_code == 409
        assert response.get_json()["error"]["code"] == "delete_target_active"
        assert "job_id" not in response.get_data(as_text=True)
        assert writer.preflight_calls == 0 and ctx["ssh"].calls == 0
        assert not Path(ctx["provenance_path"]).exists()
        assert ctx["registry"].snapshot(token, dvd_id=ctx["dvd"])["state"] == "VALIDATED"

    # If activity appears across the writer preflight, the second exact check
    # still prevents provenance COMMITTING and NAS mutation.
    with tempfile.TemporaryDirectory(prefix="delete-activity-race-") as tmp:
        writer = CountingPreflightWriter()
        ctx = setup_app(tmp, discovery_writer_client=writer,
                        activity_decisions=[IDLE, ACTIVE_SUBTITLE])
        token, _ = prepared_validated(ctx)
        response = post(ctx, "commit", commit_body(ctx, token))
        assert response.status_code == 409
        assert response.get_json()["error"]["code"] == "delete_target_active"
        assert writer.preflight_calls == 1 and ctx["ssh"].calls == 0
        assert not Path(ctx["provenance_path"]).exists()
        assert ctx["registry"].snapshot(token, dvd_id=ctx["dvd"])["state"] == "VALIDATED"

    # An unavailable source is not treated as idle.
    with tempfile.TemporaryDirectory(prefix="delete-activity-unavailable-") as tmp:
        ctx = setup_app(tmp, activity_decisions=[ACTIVITY_STATE_UNAVAILABLE])
        token, _ = prepared_validated(ctx)
        response = post(ctx, "commit", commit_body(ctx, token))
        assert response.status_code == 503
        assert response.get_json()["error"]["code"] == "delete_activity_unavailable"
        assert ctx["ssh"].calls == 0 and not Path(ctx["provenance_path"]).exists()

    # Production default uses a configured writer client; failure before
    # provenance COMMITTING guarantees the NAS mutator is never entered.
    with tempfile.TemporaryDirectory(prefix="delete-writer-preflight-") as tmp:
        ctx = setup_app(tmp, discovery_writer_client=UnavailableWriter())
        token, _ = prepared_validated(ctx)
        response = post(ctx, "commit", commit_body(ctx, token))
        assert response.status_code == 503
        assert response.get_json()["error"]["code"] == "discovery_writer_unavailable"
        assert ctx["media"].exists() and ctx["ssh"].calls == 0
        assert not Path(ctx["provenance_path"]).exists()

    # Full offline path: host socket preflight precedes the fixture NAS
    # mutator, then the writer performs exactly one Discovery transition.
    with tempfile.TemporaryDirectory(prefix="delete-writer-integration-") as tmp:
        socket_path = Path(tmp) / "run" / "writer.sock"
        _prepare_socket_parent(str(socket_path))
        server = _UnixServer(str(socket_path), DiscoveryHoldingWriter(
            str(Path(tmp) / "discovery.sqlite3"), str(Path(tmp) / "provenance.sqlite3")))
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            ctx = setup_app(tmp, discovery_writer_client=UnixSocketDiscoveryWriterClient(str(socket_path)))
            token, _ = prepared_validated(ctx)
            response = post(ctx, "commit", commit_body(ctx, token))
            assert response.status_code == 200, response.get_json()
            operation_id = response.get_json()["operation_id"]
            assert response.get_json()["status"] == "COMMITTED"
            assert sqlite3.connect(ctx["db_path"]).execute(
                "SELECT present FROM holdings WHERE dvd_id=?", (ctx["dvd"],)).fetchone() == (0,)
            assert DurableDeleteProvenanceStore(ctx["provenance_path"]).get(
                operation_id)["discovery_reconciled"] == 1
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)
            socket_path.unlink(missing_ok=True)

    with tempfile.TemporaryDirectory(prefix="delete-commit-fixture-") as tmp:
        ctx = setup_app(tmp, gate=None)
        dvd, title, media, db_path = ctx["dvd"], ctx["title"], ctx["media"], ctx["db_path"]
        token, _ = prepared_validated(ctx)
        denied = post(ctx, "commit", commit_body(ctx, token))
        assert denied.status_code == 403 and denied.get_json()["error"]["code"] == "delete_disabled"
        assert media.exists() and ctx["ssh"].calls == 0

        os.environ["TEDDY_LIBRARY_DELETE_ENABLED"] = "false"
        denied_false = post(ctx, "commit", commit_body(ctx, token))
        assert denied_false.status_code == 403 and media.exists()
        os.environ["TEDDY_LIBRARY_DELETE_ENABLED"] = "true"

        # Authentication, origin and intent remain independent gates.
        assert post(ctx, "commit", commit_body(ctx, token), authenticated=False).status_code == 401
        assert post(ctx, "commit", commit_body(ctx, token), origin="http://evil.test").status_code == 403
        assert post(ctx, "commit", commit_body(ctx, token), intent="validate").status_code == 403
        assert media.exists() and ctx["ssh"].calls == 0

        # PREPARED-only, wrong DVD, and missing final confirmation never invoke the mutator.
        only_prepared = post(ctx, "prepare", {}).get_json()["prepare_token"]
        assert post(ctx, "commit", commit_body(ctx, only_prepared)).status_code == 409
        token2, _ = prepared_validated(ctx)
        assert post(ctx, "commit", dict(commit_body(ctx, token2), typed_dvd_id="OTHER-1")).status_code == 400
        assert post(ctx, "commit", dict(commit_body(ctx, token2), confirm_phrase="")).status_code == 400
        assert media.exists() and ctx["ssh"].calls == 0

        # Manifest/source drift after validation fails closed before mutation.
        token3, _ = prepared_validated(ctx)
        (title / "unexpected.txt").write_text("unexpected", encoding="utf-8")
        drift = post(ctx, "commit", commit_body(ctx, token3))
        assert drift.status_code in (409, 503) and media.exists() and ctx["ssh"].calls == 0
        (title / "unexpected.txt").unlink()

        # A symlink, special object, and inventory drift are rejected by lstat-based read.
        token4, _ = prepared_validated(ctx)
        (title / "link.srt").symlink_to(media)
        symlink_commit = post(ctx, "commit", commit_body(ctx, token4))
        assert symlink_commit.status_code in (409, 503) and media.exists()
        assert ctx["ssh"].calls == 0
        (title / "link.srt").unlink()

        token_nested, _ = prepared_validated(ctx)
        (title / "nested").mkdir()
        nested = post(ctx, "commit", commit_body(ctx, token_nested))
        assert nested.status_code in (409, 503) and media.exists() and ctx["ssh"].calls == 0
        (title / "nested").rmdir()

        token_special, _ = prepared_validated(ctx)
        fifo = title / "unexpected.fifo"
        os.mkfifo(fifo)
        special = post(ctx, "commit", commit_body(ctx, token_special))
        assert special.status_code in (409, 503) and media.exists() and ctx["ssh"].calls == 0
        fifo.unlink()

        token5, payload = prepared_validated(ctx)
        assert payload["file_count"] == 2 and payload["total_bytes"] > 0
        assert payload["commit_enabled"] is True
        manifest_hash = payload["manifest_sha256"]
        old_mtime = media.stat().st_mtime_ns
        os.utime(media, ns=(media.stat().st_atime_ns, old_mtime + 5_000_000))
        mutation = post(ctx, "commit", commit_body(ctx, token5))
        assert mutation.status_code == 409 and media.exists() and ctx["ssh"].calls == 0
        os.utime(media, ns=(media.stat().st_atime_ns, old_mtime))

        # Exact manifest mutation deletes only direct manifest files and title directory.
        token6, _ = prepared_validated(ctx)
        before_names = sorted(p.name for p in title.iterdir())
        success = post(ctx, "commit", commit_body(ctx, token6))
        assert success.status_code == 200, success.get_json()
        result = success.get_json()
        assert result["status"] == "COMMITTED" and result["removed_file_count"] == 2
        assert result["actual_delete_performed"] is True
        assert token6 not in json.dumps(result) and str(ctx["root"]) not in json.dumps(result)
        assert not title.exists() and (ctx["root"] / "ABCD").is_dir()
        assert (ctx["root"] / "ABCD" / "SIBL-456" / "preserve.txt").read_text() == "keep"
        assert sorted(before_names) == sorted([ctx["media"].name, f"{dvd}.ko.srt"])
        row = sqlite3.connect(db_path).execute("SELECT present FROM holdings WHERE dvd_id=?", (dvd,)).fetchone()
        assert row == (0,)
        stored = DurableDeleteProvenanceStore(ctx["provenance_path"]).get(result["operation_id"])
        assert stored["result_state"] == "COMMITTED" and stored["nas_delete_complete"] == 1
        assert stored["removed_file_count"] == 2 and stored["validated_at"]
        assert ctx["jellyfin_refreshes"] == ["refresh-exact-item"]
        replay = post(ctx, "commit", commit_body(ctx, token6))
        assert replay.status_code == 200 and replay.get_json()["operation_id"] == result["operation_id"]
        assert ctx["ssh"].calls == 1

        # The implementation has no shell recursive-delete/glob primitive.
        source = Path(__file__).with_name("teddy_library_delete_commit.py").read_text()
        helper = source.split("_DELETE_SCRIPT = r'''", 1)[1].split("'''", 1)[0]
        assert "os.unlink(path)" in helper and "os.rmdir(title)" in helper
        assert "rm -rf" not in helper and "glob(" not in helper and "rmtree" not in helper

    # Partial delete is recorded durably and retry removes only remaining exact entries.
    with tempfile.TemporaryDirectory(prefix="delete-partial-fixture-") as tmp:
        ctx = setup_app(tmp, partial_once=True)
        token, _ = prepared_validated(ctx)
        first = post(ctx, "commit", commit_body(ctx, token))
        assert first.status_code == 409 and first.get_json()["status"] == "PARTIAL_DELETE"
        operation_id = first.get_json()["operation_id"]
        record = DurableDeleteProvenanceStore(ctx["provenance_path"]).get(operation_id)
        assert record["removed_file_count"] == 1 and record["result_state"] == "PARTIAL_DELETE"
        calls_before_resume = ctx["ssh"].calls
        ctx["activity_guard"].decisions = [ACTIVE_SUBTITLE]
        blocked = ctx["client"].post(f"/api/library/{dvd}/delete/resume", json={
            "operation_id": operation_id, "typed_dvd_id": dvd,
            "acknowledge_permanent_delete": True, "confirm_phrase": CONFIRM_PHRASE,
        }, base_url="http://localhost", headers={
            "Origin": "http://localhost", "X-Teddy-Delete-Intent": "resume"})
        assert blocked.status_code == 409
        assert blocked.get_json()["error"]["code"] == "delete_target_active"
        assert ctx["ssh"].calls == calls_before_resume
        # Simulate a web process restart: the durable operation survives while
        # the in-memory prepare-token registry is irrelevant to recovery.
        ctx["registry"] = PrepareTokenRegistry()
        ctx["activity_guard"].decisions = [IDLE]
        second = ctx["client"].post(f"/api/library/{dvd}/delete/resume", json={
            "operation_id": operation_id, "typed_dvd_id": dvd,
            "acknowledge_permanent_delete": True, "confirm_phrase": CONFIRM_PHRASE,
        }, base_url="http://localhost", headers={
            "Origin": "http://localhost", "X-Teddy-Delete-Intent": "resume"})
        assert second.status_code == 200 and second.get_json()["status"] == "COMMITTED"
        assert not ctx["title"].exists()
        assert DurableDeleteProvenanceStore(ctx["provenance_path"]).get(operation_id)["removed_file_count"] == 2

    # Recover a process crash while the durable record is still COMMITTING.
    with tempfile.TemporaryDirectory(prefix="delete-crash-recovery-fixture-") as tmp:
        ctx = setup_app(tmp)
        token, _payload = prepared_validated(ctx)
        entry = ctx["registry"].snapshot(token, dvd_id=ctx["dvd"])
        rows, _ = _holding_rows(str(ctx["db_path"]), "", ctx["dvd"])
        row = dict(rows[0])
        video = validate_canonical_holding(row, ctx["dvd"])
        manifest = ctx["reader"].inspect(video, row)
        record = DurableDeleteProvenanceStore(ctx["provenance_path"]).begin(
            operation_id=entry["operation_id"] or "00000000-0000-4000-8000-000000000001",
            dvd_id=ctx["dvd"], holding_id=row["holding_id"],
            source_fingerprint=source_identity_fingerprint(row, video.relative_path),
            manifest_sha256=manifest["manifest_sha256"], entries=manifest["entries"],
            created_at=entry["created_at"], validated_at=entry["validated_at"])
        # Simulate a crash after one exact unlink, before provenance was updated.
        (ctx["title"] / f"{ctx['dvd']}.ko.srt").unlink()
        recovered = ctx["client"].post(f"/api/library/{ctx['dvd']}/delete/resume", json={
            "operation_id": record["operation_id"], "typed_dvd_id": ctx["dvd"],
            "acknowledge_permanent_delete": True, "confirm_phrase": CONFIRM_PHRASE,
        }, base_url="http://localhost", headers={
            "Origin": "http://localhost", "X-Teddy-Delete-Intent": "resume"})
        assert recovered.status_code == 200 and recovered.get_json()["status"] == "COMMITTED"
        assert not ctx["title"].exists()
        assert DurableDeleteProvenanceStore(ctx["provenance_path"]).get(record["operation_id"])["removed_file_count"] == 2

    # Discovery failure stays RECONCILE_PENDING and a later retry is deterministic.
    with tempfile.TemporaryDirectory(prefix="delete-reconcile-fixture-") as tmp:
        ctx = setup_app(tmp, discovery_ok=False)
        token, _ = prepared_validated(ctx)
        response = post(ctx, "commit", commit_body(ctx, token))
        assert response.status_code == 202 and response.get_json()["status"] == "RECONCILE_PENDING"
        assert response.get_json()["actual_delete_performed"] is True
        activity_checks_before_reconcile = len(ctx["activity_guard"].calls)
        ctx["flags"]["discovery_ok"] = True
        retry = ctx["client"].post(f"/api/library/{ctx['dvd']}/delete/reconcile",
            json={"operation_id": response.get_json()["operation_id"], "typed_dvd_id": ctx["dvd"]},
            base_url="http://localhost", headers={"Origin":"http://localhost", "X-Teddy-Delete-Intent":"reconcile"})
        assert retry.status_code == 200 and retry.get_json()["status"] == "COMMITTED"
        assert len(ctx["activity_guard"].calls) == activity_checks_before_reconcile

    # Jellyfin failure records pending without reversing NAS or Discovery result.
    with tempfile.TemporaryDirectory(prefix="delete-jellyfin-fixture-") as tmp:
        ctx = setup_app(tmp, jellyfin_ok=False)
        token, _ = prepared_validated(ctx)
        response = post(ctx, "commit", commit_body(ctx, token))
        assert response.status_code == 202 and response.get_json()["status"] == "RECONCILE_PENDING"
        assert response.get_json()["discovery_reconciled"] is True
        record = DurableDeleteProvenanceStore(ctx["provenance_path"]).get(response.get_json()["operation_id"])
        assert record["jellyfin_reconciled"] == 0 and record["nas_delete_complete"] == 1

    print("Stage13-F1 offline delete commit safety smoke: OK")


if __name__ == "__main__":
    main()
