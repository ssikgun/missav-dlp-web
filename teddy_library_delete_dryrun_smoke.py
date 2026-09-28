"""Offline fixture safety smoke for Stage13-E1; no production services used."""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile

from flask import Flask

from teddy_discovery_organizer import canonical_destination
from teddy_library_api import _holding_rows, _ko_state, create_library_blueprint
from teddy_discovery_subtitle import validate_canonical_holding
from teddy_library_delete_dryrun import (
    DeleteDryRunError, DeleteManifestReader, DeleteProvenance, MANIFEST_SCRIPT,
    PrepareTokenRegistry, canonical_manifest, serialize_provenance,
    source_identity_fingerprint,
)
from teddy_discovery_jellyfin import jellyfin_media_path


class LocalSSH:
    """Execute only the read-only remote inspector against a local fixture."""
    def _run_python(self, script, *args):
        result = subprocess.run([sys.executable, "-c", script, *map(str, args)],
                                text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr or "fixture inspection failed")
        return result.stdout


def make_fixture(tmp):
    root = Path(tmp) / "nas"
    dvd = "ABCD-123"
    title = root / "ABCD" / dvd
    title.mkdir(parents=True)
    media = title / f"{dvd}.mp4"
    media.write_bytes(b"media-123")
    media_stat = media.stat()
    db_path = Path(tmp) / "discovery.sqlite3"
    db = sqlite3.connect(db_path)
    db.executescript("""
      CREATE TABLE holdings(holding_id INTEGER PRIMARY KEY,storage_root TEXT,relative_path TEXT,dvd_id TEXT,parse_status TEXT,size_bytes INTEGER,mtime_ns INTEGER,discovered_by TEXT,present INTEGER,first_seen_at TEXT,last_seen_at TEXT);
      CREATE TABLE titles(dvd_id TEXT PRIMARY KEY,title TEXT,release_date TEXT,maker TEXT,cover_url TEXT);
      CREATE TABLE organizer_jobs(job_id INTEGER PRIMARY KEY,dvd_id TEXT,source_path TEXT,destination_path TEXT,status TEXT,created_at TEXT,updated_at TEXT);
    """)
    relative = canonical_destination(dvd, ".mp4").as_posix()
    db.execute("INSERT INTO holdings(storage_root,relative_path,dvd_id,parse_status,size_bytes,mtime_ns,discovered_by,present,first_seen_at,last_seen_at) VALUES('jav',?,?, 'MATCHED',?,?, 'completion-stage9',1,'2026-01-01','2026-01-01')",
               (relative, dvd, media_stat.st_size, media_stat.st_mtime_ns))
    db.execute("INSERT INTO titles(dvd_id,title) VALUES(?,?)", (dvd, "Fixture title"))
    db.commit()
    db.close()
    return root, title, media, db_path, relative, dvd


def app_for(db_path, root, jellyfin_calls, *, recognized=False):
    reader = DeleteManifestReader(LocalSSH(), library_root=str(root))
    jf_paths = {"/media/adult/ABCD/ABCD-123/ABCD-123.mp4"} if recognized else set()
    app = Flask("delete-dryrun-fixture")
    app.secret_key = "fixture-only-session-secret"
    app.register_blueprint(create_library_blueprint(
        str(db_path), "", nas_reader=object(),
        delete_manifest_reader=reader,
        jellyfin_loader=lambda: jellyfin_calls.append("GET") or jf_paths,
    ))
    client = app.test_client()
    with client.session_transaction() as session:
        session["teddy_authenticated"] = True
    return app, client


def post(client, path, body, intent):
    return client.post(path, json=body, base_url="http://localhost",
                       headers={"Origin": "http://localhost", "X-Teddy-Delete-Intent": intent})


def assert_inspection_error(root, relative, media_relative, size, mtime, code):
    try:
        DeleteManifestReader(LocalSSH(), library_root=str(root)).inspect(
            type("Video", (), {"relative_path": media_relative})(),
            {"size_bytes": size, "mtime_ns": mtime},
        )
    except DeleteDryRunError as exc:
        assert exc.code == code, (exc.code, code)
    else:
        raise AssertionError(f"unsafe fixture accepted: {code}")


def main():
    with tempfile.TemporaryDirectory(prefix="delete-dryrun-fixture-") as tmp:
        root, title, media, db_path, relative, dvd = make_fixture(tmp)
        calls = []
        app, client = app_for(db_path, root, calls)
        diagnostic_output = io.StringIO()
        diagnostic_handler = logging.StreamHandler(diagnostic_output)
        app.logger.addHandler(diagnostic_handler)
        rows, terminal = _holding_rows(str(db_path), "", dvd)
        fixture_row = dict(rows[0])
        fixture_video = validate_canonical_holding(fixture_row, dvd)
        fixture_manifest = DeleteManifestReader(LocalSSH(), library_root=str(root)).inspect(fixture_video, fixture_row)
        fixture_inventory = {"status": "ok", "bytes": fixture_manifest["total_bytes"], "subtitle_names": fixture_manifest["subtitle_names"], "ko": fixture_manifest["ko"]}
        assert _ko_state(fixture_row, fixture_video, fixture_inventory, terminal.get(dvd, {}))[0] == "ABSENT"
        assert jellyfin_media_path(fixture_video.relative_path).startswith("/media/adult/")
        fixture_fingerprint = source_identity_fingerprint(fixture_row, fixture_video.relative_path)
        PrepareTokenRegistry().issue(dvd_id=dvd, manifest_sha256=fixture_manifest["manifest_sha256"], source_fingerprint=fixture_fingerprint)
        url = f"/api/library/{dvd}/delete/prepare"
        client.set_cookie("diagnostic_marker", "COOKIE_SECRET_MARKER")
        unauth = app.test_client().post(url, json={}, base_url="http://localhost",
                                       headers={"Origin": "http://localhost", "X-Teddy-Delete-Intent": "prepare"})
        assert unauth.status_code == 401

        invalid_mimetype = client.post(url, data="{}", base_url="http://localhost",
                                       content_type="text/plain",
                                       headers={"Origin": "http://localhost", "X-Teddy-Delete-Intent": "prepare"})
        assert invalid_mimetype.status_code == 403
        wrong_intent = client.post(url, json={"prepare_token": "TOKEN_SECRET_MARKER"}, base_url="http://localhost",
                                   headers={"Origin": "http://localhost", "X-Teddy-Delete-Intent": "wrong"})
        assert wrong_intent.status_code == 403
        missing_origin = client.post(url, json={}, base_url="http://localhost",
                                     headers={"X-Teddy-Delete-Intent": "prepare"})
        assert missing_origin.status_code == 403
        scheme_mismatch = client.post(url, json={}, base_url="http://localhost",
                                      headers={"Origin": "https://localhost", "X-Teddy-Delete-Intent": "prepare"})
        assert scheme_mismatch.status_code == 403
        host_mismatch = client.post(url, json={}, base_url="http://localhost",
                                    headers={"Origin": "http://evil.invalid", "X-Teddy-Delete-Intent": "prepare",
                                             "X-Forwarded-Proto": "https", "X-Forwarded-Host": "downloader.example"})
        assert host_mismatch.status_code == 403
        cross_site = client.post(url, json={}, base_url="http://localhost",
                                 headers={"Origin": "http://localhost", "X-Teddy-Delete-Intent": "prepare",
                                          "Sec-Fetch-Site": "cross-site"})
        assert cross_site.status_code == 403
        diagnostics = diagnostic_output.getvalue()
        for expected in (
            "reject=invalid_request_boundary subreason=mimetype",
            "reject=invalid_request_boundary subreason=intent_header",
            "reject=invalid_request_origin subreason=origin_missing",
            "reject=invalid_request_origin subreason=scheme_mismatch",
            "reject=invalid_request_origin subreason=host_mismatch",
            "reject=invalid_request_origin subreason=cross_site",
            "x_forwarded_proto=https", "x_forwarded_host=downloader.example",
        ):
            assert expected in diagnostics, expected
        assert diagnostics.count("library_delete_guard reject=") == 6
        assert "COOKIE_SECRET_MARKER" not in diagnostics
        assert "TOKEN_SECRET_MARKER" not in diagnostics
        assert "diagnostic_marker" not in diagnostics and "session" not in diagnostics.lower()

        bad_origin = client.post(url, json={}, base_url="http://localhost",
                                 headers={"Origin": "http://evil.invalid", "X-Teddy-Delete-Intent": "prepare"})
        assert bad_origin.status_code == 403
        prepared = post(client, url, {}, "prepare")
        assert prepared.status_code == 200, (prepared.status_code, prepared.get_json())
        payload = prepared.get_json()
        assert payload["status"] == "PREPARED" and payload["actual_delete_performed"] is False
        assert payload["dvd_id"] == dvd and payload["title"] == "Fixture title"
        assert payload["files"] == [media.name] and payload["file_count"] == 1
        assert payload["total_bytes"] == media.stat().st_size
        assert len(payload["manifest_sha256"]) == 64 and payload["jellyfin_state"] == "ABSENT"
        token = payload["prepare_token"]
        assert token and token not in json.dumps({k:v for k,v in payload.items() if k != "prepare_token"})
        assert post(client, "/api/library/NOT_AN_ID/delete/prepare", {}, "prepare").status_code == 400
        assert post(client, url, {"path": "/etc/passwd"}, "prepare").status_code == 400
        assert post(client, f"/api/library/{dvd}/delete/validate",
                    {"prepare_token": token, "typed_dvd_id": dvd, "acknowledge": True, "path": relative}, "validate").status_code == 400
        valid_body = {"prepare_token": token, "typed_dvd_id": dvd, "acknowledge": True}
        wrong = dict(valid_body, typed_dvd_id="WXYZ-9")
        assert post(client, f"/api/library/{dvd}/delete/validate", wrong, "validate").status_code == 400
        no_ack = dict(valid_body, acknowledge=False)
        assert post(client, f"/api/library/{dvd}/delete/validate", no_ack, "validate").status_code == 400
        unknown_token = dict(valid_body, prepare_token="x" * 40)
        assert post(client, f"/api/library/{dvd}/delete/validate", unknown_token, "validate").status_code == 410
        validated = post(client, f"/api/library/{dvd}/delete/validate", valid_body, "validate")
        assert validated.status_code == 200 and validated.get_json()["status"] == "READY_FOR_COMMIT"
        assert validated.get_json()["actual_delete_performed"] is False
        replay = post(client, f"/api/library/{dvd}/delete/validate", valid_body, "validate")
        assert replay.status_code == 200 and replay.get_json()["validated_at"] == validated.get_json()["validated_at"]
        assert calls == ["GET", "GET", "GET"]  # prepare + validate + identical replay; GET-only
        assert client.get(f"/api/library/{dvd}/stream").status_code == 503  # existing route still installed

        # A newly appeared direct file changes deterministic manifest identity.
        again = post(client, url, {}, "prepare").get_json()
        (title / "new.txt").write_text("fixture", encoding="utf-8")
        drift = post(client, f"/api/library/{dvd}/delete/validate",
                     {"prepare_token": again["prepare_token"], "typed_dvd_id": dvd, "acknowledge": True}, "validate")
        assert drift.status_code == 409 and drift.get_json()["error"]["code"] == "manifest_changed"

        # Confirm DB bytes remain unchanged by API prepare/validate reads.
        before = hashlib.sha256(db_path.read_bytes()).digest()
        post(client, url, {}, "prepare")
        assert hashlib.sha256(db_path.read_bytes()).digest() == before

    with tempfile.TemporaryDirectory(prefix="delete-subtitle-readonly-") as tmp:
        root, title, media, db_path, _relative, dvd = make_fixture(tmp)
        (title / f"{dvd}.ko.srt").write_text(
            "1\n00:00:00,000 --> 00:00:01,000\n한글\n", encoding="utf-8")
        calls = []
        _app, client = app_for(db_path, root, calls, recognized=True)
        response = post(client, f"/api/library/{dvd}/delete/prepare", {}, "prepare")
        assert response.status_code == 200
        data = response.get_json()
        assert data["ko_state"] == "VALID" and data["jellyfin_state"] == "RECOGNIZED"
        assert "한글" not in response.get_data(as_text=True) and calls == ["GET"]

    # Deterministic canonical order/hash, field validation, future provenance shape.
    rows = [
        {"relative_name": "z.mkv", "size_bytes": 8, "mtime_ns": 2, "inode": 4, "device": 1, "file_type": "regular"},
        {"relative_name": "a.srt", "size_bytes": 2, "mtime_ns": 1, "inode": 3, "device": 1, "file_type": "regular"},
    ]
    first, sha1, total = canonical_manifest(rows)
    second, sha2, _ = canonical_manifest(list(reversed(rows)))
    assert first == second and sha1 == sha2 and total == 10
    try:
        canonical_manifest([dict(rows[0], relative_name="../escape")])
    except DeleteDryRunError as exc:
        assert exc.code == "MANIFEST_INVALID"
    else:
        raise AssertionError("path traversal manifest accepted")
    provenance = serialize_provenance(DeleteProvenance(
        1, "ABCD-123", sha1, 2, total, "VALIDATE", "a" * 64,
        "2026-01-01T00:00:00+00:00", "2026-01-01T00:01:00+00:00", "READY_FOR_COMMIT"))
    assert set(provenance) == {"schema_version", "dvd_id", "manifest_sha256", "file_count", "total_bytes", "phase", "source_identity_fingerprint", "created_at", "validated_at", "result"}
    assert not any("path" in key or "token" in key or "session" in key for key in provenance)

    now = [0.0]
    registry = PrepareTokenRegistry(ttl_seconds=5, max_entries=2, clock=lambda: now[0], token_factory=iter(["opaque-token-a", "opaque-token-b", "opaque-token-c"]).__next__)
    token, _ = registry.issue(dvd_id="ABCD-123", manifest_sha256=sha1, source_fingerprint="source")
    try:
        registry.validate(token, dvd_id="EFGH-1", manifest_sha256=sha1, source_fingerprint="source")
    except DeleteDryRunError as exc:
        assert exc.code == "TOKEN_DVD_ID_MISMATCH"
    else:
        raise AssertionError("token DVD binding absent")
    try:
        registry.validate(token, dvd_id="ABCD-123", manifest_sha256="0" * 64, source_fingerprint="source")
    except DeleteDryRunError as exc:
        assert exc.code == "MANIFEST_CHANGED"
    else:
        raise AssertionError("token manifest binding absent")
    other_source, _ = registry.issue(dvd_id="ABCD-123", manifest_sha256=sha1, source_fingerprint="original")
    try:
        registry.validate(other_source, dvd_id="ABCD-123", manifest_sha256=sha1, source_fingerprint="changed")
    except DeleteDryRunError as exc:
        assert exc.code == "MANIFEST_CHANGED"
    else:
        raise AssertionError("token source identity binding absent")
    expiring, _ = registry.issue(dvd_id="ABCD-123", manifest_sha256=sha1, source_fingerprint="source")
    now[0] = 6.0
    try:
        registry.validate(expiring, dvd_id="ABCD-123", manifest_sha256=sha1, source_fingerprint="source")
    except DeleteDryRunError as exc:
        assert exc.code == "TOKEN_EXPIRED_OR_INVALID"
    else:
        raise AssertionError("expired token accepted")

    # Exercise exact remote inspector safety against isolated local directories.
    with tempfile.TemporaryDirectory(prefix="delete-manifest-safety-") as tmp:
        root = Path(tmp); title = root / "ABCD" / "ABCD-123"; title.mkdir(parents=True)
        media = title / "ABCD-123.mp4"; media.write_bytes(b"ok"); st = media.stat()
        reader = DeleteManifestReader(LocalSSH(), library_root=str(root))
        video = type("Video", (), {"relative_path": "ABCD/ABCD-123/ABCD-123.mp4"})()
        row = {"size_bytes": st.st_size, "mtime_ns": st.st_mtime_ns}
        good = reader.inspect(video, row)
        assert good["entries"][0]["relative_name"] == media.name
        assert reader.inspect(video, row)["manifest_sha256"] == good["manifest_sha256"]
        (title / "nested").mkdir()
        assert_inspection_error(root, "ABCD/ABCD-123", video.relative_path, st.st_size, st.st_mtime_ns, "NESTED_DIRECTORY")
        assert_inspection_error(root, "../escape", "../escape/ABCD-123.mp4", st.st_size, st.st_mtime_ns, "UNSAFE_RELATIVE_PATH")
    for unsafe in ("parent_symlink", "child_symlink", "fifo", "entry_limit", "media_missing", "size_drift", "mtime_drift"):
        with tempfile.TemporaryDirectory(prefix="delete-manifest-" + unsafe + "-") as tmp:
            root = Path(tmp); family = root / "ABCD"; title = family / "ABCD-123"
            if unsafe == "parent_symlink":
                target = root / "real-family"; target.mkdir(); (target / "ABCD-123").mkdir()
                family.symlink_to(target, target_is_directory=True)
            else:
                family.mkdir(); title.mkdir()
            media = title / "ABCD-123.mp4"
            if unsafe == "child_symlink":
                target_file = root / "target.mp4"; target_file.write_bytes(b"ok")
                media.symlink_to(target_file)
            elif unsafe not in {"media_missing", "parent_symlink"}:
                media.write_bytes(b"ok")
            st = media.stat() if media.exists() else type("Stat", (), {"st_size": 2, "st_mtime_ns": 1})()
            rel = "ABCD/ABCD-123/ABCD-123.mp4"
            expected = "SYMLINK" if unsafe in {"parent_symlink", "child_symlink"} else "UNEXPECTED_TYPE" if unsafe == "fifo" else "ENTRY_LIMIT" if unsafe == "entry_limit" else "CANONICAL_MEDIA_MISSING" if unsafe == "media_missing" else "CANONICAL_MEDIA_IDENTITY_MISMATCH"
            if unsafe == "fifo":
                os.mkfifo(title / "pipe")
            elif unsafe == "entry_limit":
                for i in range(512): (title / f"{i:04d}.dat").touch()
            elif unsafe == "size_drift": expected = "CANONICAL_MEDIA_IDENTITY_MISMATCH"
            elif unsafe == "mtime_drift": expected = "CANONICAL_MEDIA_IDENTITY_MISMATCH"
            expected_size = st.st_size + (1 if unsafe == "size_drift" else 0)
            expected_mtime = st.st_mtime_ns + (1 if unsafe == "mtime_drift" else 0)
            assert_inspection_error(root, "ABCD/ABCD-123", rel, expected_size, expected_mtime, expected)
    with tempfile.TemporaryDirectory(prefix="delete-manifest-root-symlink-") as tmp:
        real_root = Path(tmp) / "real-root"
        title = real_root / "ABCD" / "ABCD-123"; title.mkdir(parents=True)
        media = title / "ABCD-123.mp4"; media.write_bytes(b"ok"); st = media.stat()
        root_link = Path(tmp) / "root-link"; root_link.symlink_to(real_root, target_is_directory=True)
        assert_inspection_error(root_link, "ABCD/ABCD-123", "ABCD/ABCD-123/ABCD-123.mp4", st.st_size, st.st_mtime_ns, "SYMLINK")

    # Missing/duplicate/canonical mismatch remain fail-closed at the current DB boundary.
    with tempfile.TemporaryDirectory(prefix="delete-holding-boundary-") as tmp:
        root, _title, _media, db_path, relative, dvd = make_fixture(tmp)
        calls=[]; _app, client=app_for(db_path, root, calls)
        db=sqlite3.connect(db_path)
        db.execute("UPDATE holdings SET present=0 WHERE dvd_id=?", (dvd,)); db.commit()
        assert post(client, f"/api/library/{dvd}/delete/prepare", {}, "prepare").status_code == 404
        db.execute("UPDATE holdings SET present=1,relative_path='BAD/WRONG.mp4' WHERE dvd_id=?", (dvd,)); db.commit()
        assert post(client, f"/api/library/{dvd}/delete/prepare", {}, "prepare").status_code == 409
        db.execute("UPDATE holdings SET relative_path=? WHERE dvd_id=?", (relative, dvd))
        db.execute("INSERT INTO holdings(storage_root,relative_path,dvd_id,parse_status,size_bytes,mtime_ns,discovered_by,present) SELECT storage_root,relative_path,dvd_id,parse_status,size_bytes,mtime_ns,discovered_by,present FROM holdings WHERE dvd_id=?", (dvd,)); db.commit(); db.close()
        assert post(client, f"/api/library/{dvd}/delete/prepare", {}, "prepare").status_code == 409

    # Static client contract: prepare exists only in expanded detail; both
    # acknowledgement and exact identity gate validation; token is never rendered.
    js = Path("templates/teddy-library.js").read_text(encoding="utf-8")
    assert 'data-delete-prepare="${dvd}"' in js and "data-delete-ack" in js and "data-delete-typed" in js
    assert "ack.checked && typed.value === dvd" in js and "disabled>삭제 준비 확인" in js
    assert "/delete/prepare" in js and "/delete/validate" in js and "actual_delete_performed !== false" in js
    assert "prepare_token</code>" not in js and "absolute" not in js.lower()
    assert "bulk" not in js.lower() and "data-delete-prepare" in js
    assert "data-delete-select" not in js and 'type="file"' not in js
    assert "activeDeleteToken = null" in js and "function clearDeleteDialog()" in js
    assert "dialog.addEventListener('cancel'" in js and "ack.checked && typed.value === dvd" in js
    for code in ("invalid_request_boundary", "invalid_request_origin", "authentication_required",
                 "nas_inventory_unavailable", "prepare_unavailable", "manifest_changed",
                 "validation_unavailable"):
        assert code in js
    assert "function safeDeleteErrorCode(payload)" in js
    assert "payload.error && payload.error.code" in js
    assert "SAFE_DELETE_ERROR_CODES.has(code) ? code : null" in js
    assert "const code = _.safeCode ? ` (${_.safeCode})` : '';" in js
    assert "삭제 준비 정보를 확인하지 못했습니다.${code}" in js
    assert "준비 상태를 확인하지 못했습니다. 창을 닫고 다시 준비해 주세요.${code}" in js
    assert "payload.error.message" not in js and "response.text()" not in js
    module_source = Path("teddy_library_delete_dryrun.py").read_text(encoding="utf-8")
    assert not re.search(r"\b(?:os\.)?(?:unlink|remove|rmdir)\s*\(|\.unlink\s*\(|\.rmdir\s*\(|\brm\s+-", module_source)
    assert "os.open(ent.path,os.O_RDONLY" in module_source and "follow_symlinks=False" in module_source
    print("Stage13-E1 fixture delete prepare/validate safety smoke: PASS")


if __name__ == "__main__":
    main()
