"""Fixture-only contract smoke for the read-only Library API."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from flask import Flask
from werkzeug.security import generate_password_hash

from teddy_discovery_organizer import canonical_destination
from teddy_discovery_subtitle import derive_target_ko_relative
from teddy_library_api import create_library_blueprint, _INVENTORY_SCRIPT, _is_canonical_dvd_id, _reason
import teddy_auth
import teddy_discovery_runtime
import teddy_storage


class FixtureNAS:
    def __init__(self, fixture): self.fixture=fixture; self.calls=0
    def inventory(self, relatives):
        self.calls+=1
        return {path:self.fixture.get(path, {"status":"ok","bytes":100,"ko":None,"subtitle_names":[]}) for path in relatives}


def add_holding(db, dvd, title, *, parse="MATCHED", created="2026-01-02T00:00:00Z", updated="2026-01-02T01:00:00Z"):
    path=canonical_destination(dvd,".mp4").as_posix()
    db.execute("INSERT INTO holdings(storage_root,relative_path,dvd_id,parse_status,size_bytes,mtime_ns,discovered_by,present,first_seen_at,last_seen_at) VALUES('jav',?,?,?,100,1,'completion-stage9',1,'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')",(path,dvd,parse))
    db.execute("INSERT INTO titles(dvd_id,title,release_date,maker) VALUES(?,?,?,?)",(dvd,title,"2024-01-01","Maker"))
    db.execute("INSERT INTO organizer_jobs(dvd_id,source_path,destination_path,status,created_at,updated_at) VALUES(?,?,?,'COMPLETED',?,?)",(dvd,"source",path,created,updated))
    return path


def main():
    assert _reason({
        "status":"UNRESOLVED",
        "inventory_reason":"NO_CANONICAL_KO_SRT",
        "last_transition_reason":"STAGE12_UNSAFE_AUDIO_TIMELINE",
    }) == ("STAGE12_UNSAFE_AUDIO_TIMELINE","오디오 타임라인 이상")
    assert _reason({
        "status":"UNRESOLVED",
        "inventory_reason":"NO_CANONICAL_KO_SRT",
        "last_transition_reason":"STAGE12_BASELINE_ASR_NO_SPEECH",
    }) == ("STAGE12_BASELINE_ASR_NO_SPEECH","음성 대사 없음")
    assert _reason({
        "status":"UNRESOLVED",
        "inventory_reason":"SUBTITLE_INVENTORY_INVALID",
        "last_transition_reason":"INITIALIZE_FROM_INVENTORY",
    }) == ("SUBTITLE_INVENTORY_INVALID","기존 자막 상태 확인 필요")
    assert _reason({
        "status":"UNRESOLVED",
        "inventory_reason":"NO_CANONICAL_KO_SRT",
        "last_transition_reason":"INITIALIZE_FROM_INVENTORY",
    }) == ("STAGE12_UNRESOLVED","자막 상태 확인 필요")
    # Preserve the inventory-only helper contract used by local KO classification.
    assert _reason({"inventory_reason":"SUBTITLE_INVENTORY_INVALID"}) == (
        "SUBTITLE_INVENTORY_INVALID","기존 자막 상태 확인 필요")

    with tempfile.TemporaryDirectory(prefix="library-nas-fixture-") as nas_root:
        title=Path(nas_root)/"ABCD"/"ABCD-123"; title.mkdir(parents=True)
        (title/"ABCD-123.mp4").write_bytes(b"12345")
        (title/".ignored").write_bytes(b"x")
        (title/"@eaDir").mkdir()
        (title/"@eaDir"/"ignored").write_bytes(b"xx")
        def remote(relative):
            proc=subprocess.run([sys.executable,"-c",_INVENTORY_SCRIPT,nas_root,json.dumps([relative])],capture_output=True,text=True,check=True)
            return json.loads(proc.stdout)[relative]
        first=remote("ABCD/ABCD-123")
        assert first["status"]=="ok" and first["bytes"]==5
        (title/"link").symlink_to(title/"ABCD-123.mp4")
        assert remote("ABCD/ABCD-123").get("error")=="symlink"
        (title/"link").unlink()
        deep=title
        for _ in range(6): deep=deep/"d"; deep.mkdir()
        (deep/"x").write_bytes(b"1")
        assert remote("ABCD/ABCD-123").get("error")=="depth_limit"
        for child in title.iterdir():
            if child.is_dir() and child.name=="d":
                import shutil
                shutil.rmtree(child)
        for index in range(513): (title/ f"f{index:03d}.bin").touch()
        assert remote("ABCD/ABCD-123").get("error")=="entry_limit"
    with tempfile.TemporaryDirectory(prefix="library-api-smoke-") as tmp:
        db_path=Path(tmp)/"discovery.sqlite3"; rollout_path=Path(tmp)/"rollout.sqlite3"
        db=sqlite3.connect(db_path)
        db.executescript("""
          CREATE TABLE holdings(holding_id INTEGER PRIMARY KEY,storage_root TEXT,relative_path TEXT,dvd_id TEXT,parse_status TEXT,size_bytes INTEGER,mtime_ns INTEGER,discovered_by TEXT,present INTEGER,first_seen_at TEXT,last_seen_at TEXT);
          CREATE TABLE titles(dvd_id TEXT PRIMARY KEY,title TEXT,release_date TEXT,maker TEXT,cover_url TEXT);
          CREATE TABLE organizer_jobs(job_id INTEGER PRIMARY KEY,dvd_id TEXT,source_path TEXT,destination_path TEXT,status TEXT,created_at TEXT,updated_at TEXT);
        """)
        ids=["EBWH-296","MIAD-866","MIRD-258","SKMJ-774","TEST-123"]
        paths=[]
        for i,dvd in enumerate(ids):
            paths.append(add_holding(db,dvd,"Test title "+dvd,parse="UNMATCHED" if dvd=="TEST-123" else "MATCHED",created="2026-01-02T00:00:00Z" if dvd!="MIAD-866" else "2026-01-02T12:00:00Z",updated="2026-01-02T01:00:00Z" if dvd!="MIAD-866" else "2026-01-02T16:00:00Z"))
        db.commit(); db.close()
        state=sqlite3.connect(rollout_path)
        state.execute("CREATE TABLE stage12_rollout_titles(dvd_id TEXT,status TEXT,existing_ko TEXT,eligibility TEXT,inventory_reason TEXT,last_transition_reason TEXT)")
        state.execute("INSERT INTO stage12_rollout_titles VALUES('MIAD-866','UNRESOLVED','UNRESOLVED','UNRESOLVED','UNSAFE_AUDIO_TIMELINE','UNRESOLVED')")
        state.commit(); state.close()
        before=(hashlib.sha256(db_path.read_bytes()).digest(),hashlib.sha256(rollout_path.read_bytes()).digest())
        target=canonical_destination("MIRD-258",".ko.srt").name
        good=b"1\n00:00:00,000 --> 00:00:01,000\n\xed\x95\x9c\xea\xb8\x80\n"
        inv={}
        for path in paths:
            rel=Path(path).parent.as_posix()
            inv[rel]={"status":"ok","bytes":1000,"ko":None,"subtitle_names":[]}
        inv[Path(paths[2]).parent.as_posix()]["ko"]=base64.b64encode(good).decode("ascii")
        inv[Path(paths[2]).parent.as_posix()]["subtitle_names"]=[target]
        inv[Path(paths[3]).parent.as_posix()]["subtitle_names"]=["SKMJ-774.kor.srt"]
        nas=FixtureNAS(inv)
        app=Flask(__name__)
        streamed=[]
        expected_jf="/media/adult/"+paths[0]
        app.register_blueprint(create_library_blueprint(str(db_path),str(rollout_path),nas_reader=nas,jellyfin_loader=lambda:{expected_jf},stream_response=lambda path: streamed.append(path) or ("stream",206)))
        client=app.test_client()
        assert _is_canonical_dvd_id("FC2-PPV-1234567") and not _is_canonical_dvd_id("../EBWH-296")
        storage_env={key:os.environ.get(key) for key in ("TEDDY_NAS_HOST","TEDDY_NAS_USER","TEDDY_NAS_KEY","TEDDY_NAS_KNOWN_HOSTS")}
        os.environ.update({"TEDDY_NAS_HOST":"nas.invalid","TEDDY_NAS_USER":"fixture","TEDDY_NAS_KEY":"/fixture/key","TEDDY_NAS_KNOWN_HOSTS":"/fixture/known_hosts"})
        try:
            nas_config=teddy_storage._ssh_storage_config("/volume1/video/video2/JAV")
            assert teddy_storage._ssh_remote_path(paths[0],config=nas_config)=="/volume1/video/video2/JAV/"+paths[0]
            try: teddy_storage._ssh_remote_path("../etc/passwd",config=nas_config)
            except teddy_storage.PublishError: pass
            else: raise AssertionError("NAS path traversal was accepted")
        finally:
            for key,value in storage_env.items():
                if value is None: os.environ.pop(key,None)
                else: os.environ[key]=value
        listed=client.get("/api/library")
        assert listed.status_code==200
        data=listed.get_json(); assert data["summary"]["total_titles"]==5
        assert len(data["items"])==5 # list derives from holdings, not rollout count
        by_id={x["dvd_id"]:x for x in data["items"]}
        assert all(x in by_id for x in ids[:4])
        assert by_id["MIRD-258"]["ko_status"]=="VALID"
        assert by_id["EBWH-296"]["ko_status"]=="ABSENT"
        assert by_id["MIAD-866"]["ko_status"]=="UNRESOLVED"
        assert by_id["MIAD-866"]["unresolved_reason_code"]=="STAGE12_UNSAFE_AUDIO_TIMELINE"
        assert by_id["SKMJ-774"]["ko_status"]=="UNRESOLVED" and by_id["SKMJ-774"]["unresolved_reason_code"]=="NONCANONICAL_KO_SUBTITLE_PRESENT"
        assert by_id["TEST-123"]["ko_status"]=="INVALID/MISMATCH" and by_id["TEST-123"]["mismatch"]
        assert by_id["EBWH-296"]["nas_added_date"]=="2026-01-02"
        assert by_id["MIAD-866"]["nas_added_date"] is None and by_id["MIAD-866"]["nas_added_date_status"]=="UNKNOWN"
        assert by_id["EBWH-296"]["nas_added_at"] is None
        assert not data["summary"]["size_complete"] and data["summary"]["library_known_total_bytes"]==4000 and data["summary"]["size_unknown_count"]==1
        assert by_id["EBWH-296"]["jellyfin_state"]=="RECOGNIZED"
        assert by_id["SKMJ-774"]["jellyfin_state"]=="ABSENT"
        assert client.get("/api/library?q=ebwh-296").get_json()["items"][0]["dvd_id"]=="EBWH-296"
        assert client.get("/api/library?q=test+title+miad").get_json()["items"][0]["dvd_id"]=="MIAD-866"
        assert len(client.get("/api/library?ko=present").get_json()["items"])==1
        assert len(client.get("/api/library?ko=absent").get_json()["items"])==1
        assert len(client.get("/api/library?unresolved=true").get_json()["items"])==2
        assert len(client.get("/api/library?mismatch=true").get_json()["items"])==1
        for mode in ("nas_added","release_date","dvd_id","title","size","subtitle_status"):
            assert client.get("/api/library?sort="+mode+"&order=desc").status_code==200
        for direction in ("asc","desc"):
            ordered=client.get("/api/library?sort=nas_added&order="+direction).get_json()["items"]
            assert all(x["nas_added_date"] is not None for x in ordered[:-2])
            assert all(x["nas_added_date"] is None for x in ordered[-2:])
        assert client.get("/api/library?sort=bogus").status_code==400
        assert client.get("/api/library?ko=maybe").status_code==400
        assert client.get("/api/library?order=sideways").status_code==400
        assert client.get("/api/library?path=/etc/passwd").status_code==400
        assert client.get("/api/library/EBWH-296").status_code==200
        assert client.get("/api/library/../etc/passwd").status_code in (404,308)
        response=client.get("/api/library/EBWH-296/stream")
        assert response.status_code==206 and streamed==[paths[0]]
        assert client.get("/api/library/NOT_AN_ID/stream").status_code==400
        # A Jellyfin transport error must be UNKNOWN rather than ABSENT.
        app2=Flask("jellyfin-error")
        app2.register_blueprint(create_library_blueprint(str(db_path),str(rollout_path),nas_reader=nas,jellyfin_loader=lambda:(_ for _ in ()).throw(OSError("fixture"))))
        jf=app2.test_client().get("/api/library").get_json()["items"]
        assert all(x["jellyfin_state"]=="UNKNOWN" for x in jf)
        bad_inventory={path:{"status":"unknown","error":"symlink"} for path in inv}
        app3=Flask("unsafe-size")
        app3.register_blueprint(create_library_blueprint(str(db_path),str(rollout_path),nas_reader=FixtureNAS(bad_inventory),jellyfin_loader=lambda:set()))
        unsafe=app3.test_client().get("/api/library").get_json()
        assert unsafe["summary"]["size_unknown_count"]==5 and not unsafe["summary"]["size_complete"]
        assert all(x["managed_size_bytes"] is None and x["size_status"]=="UNKNOWN" for x in unsafe["items"])
        assert all(x["size_error_code"]==("CANONICAL_PATH_INVALID" if x["mismatch"] else "SYMLINK") for x in unsafe["items"])
        # Runtime installation and the existing global auth guard cover the new namespace.
        auth_dir=Path(tmp)/"auth"; auth_dir.mkdir()
        (auth_dir/"username").write_text("fixture",encoding="utf-8")
        (auth_dir/"password_hash").write_text(generate_password_hash("fixture-password"),encoding="utf-8")
        (auth_dir/"session_secret").write_text("fixture-session-secret",encoding="utf-8")
        prior={key:os.environ.get(key) for key in ("TEDDY_DISCOVERY_DB","TEDDY_STAGE12_ROLLOUT_DB","TEDDY_AUTH_DIR")}
        os.environ.update({"TEDDY_DISCOVERY_DB":str(db_path),"TEDDY_STAGE12_ROLLOUT_DB":str(rollout_path),"TEDDY_AUTH_DIR":str(auth_dir)})
        try:
            class Core: pass
            core=Core(); core.app=Flask("runtime-auth")
            teddy_discovery_runtime.install(core)
            teddy_auth.install(core)
            guarded=core.app.test_client().get("/api/library")
            assert guarded.status_code==401 and guarded.get_json()["status"]=="error"
            assert "teddy_library_api" in core.app.blueprints
            methods=next(rule.methods for rule in core.app.url_map.iter_rules() if rule.rule=="/api/library")
            assert "GET" in methods and "POST" not in methods
        finally:
            for key,value in prior.items():
                if value is None: os.environ.pop(key,None)
                else: os.environ[key]=value
        after=(hashlib.sha256(db_path.read_bytes()).digest(),hashlib.sha256(rollout_path.read_bytes()).digest())
        assert after==before # fixture databases remain byte-for-byte read-only
        print("Stage13-B fixture library API smoke: PASS")


if __name__=="__main__": main()
