from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone
import hashlib
import importlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from dataclasses import replace
from urllib.request import Request

import teddy_discovery_media_only_runner as runner
from teddy_discovery_jellyfin_visibility import (
    VISIBILITY_TABLE_SCHEMA,
    reconcile_jellyfin_visibility,
)
from teddy_discovery_media_jobs import (
    MEDIA_SCHEMA,
    reconcile_media_jobs,
    run_retryable_media_jobs,
)


STAMP = datetime.now(timezone.utc).isoformat(timespec="seconds")
OLD_STAMP = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(timespec="seconds")


class FakeJellyfin:
    def __init__(self, status="VISIBLE"):
        self.status = status
        self.paths = []

    def exact_media_visibility(self, path):
        self.paths.append(path)
        if self.status == "VISIBLE":
            return {"status": "VISIBLE", "item_id": "fake-item-id"}
        if self.status == "ATTENTION":
            return {"status": "ATTENTION", "reason": "AMBIGUOUS"}
        return {"status": "PENDING"}


class FakeGetBudget:
    def __init__(self):
        self.get_requests = 0
        self.post_attempts = 0


def init_discovery(path: Path, dvd_ids):
    db = sqlite3.connect(path)
    db.executescript(
        """CREATE TABLE organizer_jobs (
               job_id INTEGER PRIMARY KEY, dvd_id TEXT, status TEXT NOT NULL
           );
           CREATE TABLE holdings (
               dvd_id TEXT NOT NULL, storage_root TEXT NOT NULL,
               relative_path TEXT NOT NULL, size_bytes INTEGER,
               mtime_ns INTEGER, present INTEGER NOT NULL,
               discovered_by TEXT NOT NULL
           );
           CREATE TABLE titles (
               dvd_id TEXT PRIMARY KEY, title TEXT NOT NULL,
               release_date TEXT, maker TEXT, cover_url TEXT,
               raw_metadata TEXT, metadata_source TEXT
           );
           CREATE TABLE title_genres (dvd_id TEXT, genre_id INTEGER);
           CREATE TABLE genres (genre_id INTEGER PRIMARY KEY, name TEXT);
           CREATE TABLE title_people (dvd_id TEXT, person_id INTEGER, role TEXT);
           CREATE TABLE people (person_id INTEGER PRIMARY KEY, name TEXT);
        """
    )
    for index, dvd_id in enumerate(dvd_ids, 1):
        db.execute(
            "INSERT INTO organizer_jobs(job_id,dvd_id,status) VALUES(?,?,'COMPLETED')",
            (index, dvd_id),
        )
        db.execute(
            """INSERT INTO holdings
               (dvd_id,storage_root,relative_path,size_bytes,mtime_ns,present,discovered_by)
               VALUES(?,'jav',?,123,456,1,'completion-stage9')""",
            (dvd_id, f"A/{dvd_id}/{dvd_id}.mkv"),
        )
        db.execute(
            """INSERT INTO titles
               (dvd_id,title,release_date,maker,cover_url,raw_metadata,metadata_source)
               VALUES(?,?,?,?,'https://poster.example/image.jpg','{}','fixture')""",
            (dvd_id, "Synthetic " + dvd_id, "2026-01-01", "Synthetic Maker"),
        )
    db.commit()
    db.close()


def init_media(path: Path, *, jobs=()):
    db = sqlite3.connect(path)
    db.executescript(MEDIA_SCHEMA)
    db.execute(
        """CREATE INDEX IF NOT EXISTS idx_media_jobs_poster_retry
           ON media_jobs(status,nfo_status,poster_status,updated_at)"""
    )
    db.executescript(VISIBILITY_TABLE_SCHEMA)
    db.execute(
        """CREATE INDEX IF NOT EXISTS idx_media_jellyfin_visibility_pending
           ON media_jellyfin_visibility(status,updated_at,dvd_id)"""
    )
    for row in jobs:
        db.execute(
            """INSERT INTO media_jobs
               (dvd_id,status,attempt_count,error,nfo_status,poster_status,
                jellyfin_notification_status,jellyfin_recovery_status,
                jellyfin_next_check_at,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                row.get("dvd_id"), row.get("status", "PENDING"),
                row.get("attempt_count", 0), row.get("error"),
                row.get("nfo_status", "PENDING"), row.get("poster_status", "PENDING"),
                row.get("jellyfin_notification_status", "UNKNOWN"),
                row.get("jellyfin_recovery_status", "UNKNOWN"),
                row.get("jellyfin_next_check_at"),
                row.get("created_at", STAMP), row.get("updated_at", STAMP),
            ),
        )
    db.commit()
    db.close()


def read_rows(path: Path, sql: str):
    db = sqlite3.connect(path)
    rows = db.execute(sql).fetchall()
    db.close()
    return rows


def make_config(root: Path, *, apply=False, target=None, **overrides):
    root.mkdir(parents=True, exist_ok=True)
    discovery = root / "discovery.sqlite3"
    media = root / "media.sqlite3"
    writer_lock = root / "media-writer.lock"
    run_lock = root / "runner.lock"
    title_locks = root / "title-locks"
    title_locks.mkdir(exist_ok=True)
    config = runner.RunnerConfig(
        discovery_db_path=discovery,
        media_db_path=media,
        media_writer_lock_path=writer_lock,
        run_lock_path=run_lock,
        title_lock_dir=title_locks,
        target_dvd_id=target,
        apply=apply,
        confirm=runner.CONFIRMATION if apply else "",
        filestation_password_path=root / "filestation-password" if apply else None,
        filestation_ca_path=root / "filestation-ca.pem" if apply else None,
        library_root="/volume1/video/video2/JAV" if apply else "",
        poster_proxy_url="http://127.0.0.1:8123" if apply else "",
        jellyfin_base_url="http://127.0.0.1:8096" if apply else "",
        jellyfin_key_path=root / "jellyfin-key" if apply else None,
        **overrides,
    )
    if apply:
        (root / "filestation-password").write_text("synthetic-password\n", encoding="utf-8")
        os.chmod(root / "filestation-password", 0o600)
        (root / "filestation-ca.pem").write_text("synthetic CA fixture", encoding="utf-8")
        (root / "jellyfin-key").write_text("synthetic", encoding="utf-8")
    return config


def init_pair(root: Path, dvd_ids):
    init_discovery(root / "discovery.sqlite3", dvd_ids)
    init_media(root / "media.sqlite3")


def services(processed, *, jellyfin=None):
    return {
        "reconcile": reconcile_media_jobs,
        "run_jobs": run_retryable_media_jobs,
        "visibility": reconcile_jellyfin_visibility,
        "processor": lambda dvd_id: (
            processed.append(dvd_id)
            or {"nfo_status": "COMPLETE", "poster_status": "COMPLETE"}
        ),
        "jellyfin": jellyfin or FakeJellyfin(),
        "get_budget": FakeGetBudget(),
    }


def import_is_side_effect_free():
    module = importlib.reload(runner)
    forbidden = {
        "teddy_discovery_completion_runner",
        "teddy_discovery_completion_orchestrator",
        "teddy_discovery_completion_metadata",
        "teddy_discovery_completion_apply",
    }
    assert forbidden.isdisjoint(module.__dict__)
    source = Path(module.__file__).read_text(encoding="utf-8")
    for forbidden_text in (
        "teddy_discovery_completion_runner",
        "teddy_discovery_completion_ssh",
        "MediaMetadataSSHMutator",
        "plan_remote_downloads",
        "recover_held_metadata",
        "process_one(",
        ".list_downloads(",
    ):
        assert forbidden_text not in source


def dry_run_is_read_only(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    ids = ["ABC-123"]
    init_pair(root, ids)
    before = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in ("discovery.sqlite3", "media.sqlite3")
    }
    config = make_config(root)
    result = runner.run_stage9_media_once(config)
    assert result["status"] == "DRY_RUN"
    assert not config.run_lock_path.exists()
    assert not config.media_writer_lock_path.exists()
    after = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in before
    }
    assert after == before


def registration_processing_and_visibility_are_bounded(root: Path):
    ids = ["ABC-123", "DEF-456", "GHI-789", "JKL-321"]
    init_pair(root, ids)
    processed = []
    fake = FakeJellyfin("VISIBLE")
    svc = services(processed, jellyfin=fake)
    config = make_config(root, apply=True, max_items=1,
                         visibility_max_items=1, visibility_seed_max_items=1)

    first = runner.run_stage9_media_once(config, services=svc)
    assert first["registered"] == 1
    assert first["media"]["attempted"] == 1
    assert first["media"]["completed"] == 1
    assert first["jellyfin_visibility"]["seeded"] == 1
    assert first["jellyfin_visibility"]["checked"] == 1
    assert len(processed) == 1 and len(fake.paths) == 1

    second = runner.run_stage9_media_once(config, services=svc)
    assert second["registered"] == 1
    assert second["media"]["attempted"] == 1
    assert len(processed) == 2 and len(fake.paths) == 2
    assert read_rows(
        root / "media.sqlite3",
        "SELECT count(*) FROM media_jobs",
    )[0][0] == 2
    assert read_rows(
        root / "media.sqlite3",
        "SELECT count(*) FROM media_jellyfin_visibility",
    )[0][0] == 2

    # Reconciliation is idempotent once all organizer inputs already exist.
    assert reconcile_media_jobs(
        root / "discovery.sqlite3",
        root / "media.sqlite3",
        root / "media-writer.lock",
        max_items=1,
    ) == 1
    assert reconcile_media_jobs(
        root / "discovery.sqlite3",
        root / "media.sqlite3",
        root / "media-writer.lock",
        max_items=1,
    ) == 1
    assert reconcile_media_jobs(
        root / "discovery.sqlite3",
        root / "media.sqlite3",
        root / "media-writer.lock",
        max_items=1,
    ) == 0


def visibility_seed_limit_and_target_filter(root: Path):
    ids = ["ABC-123", "DEF-456", "GHI-789"]
    init_pair(root, ids)
    for dvd_id in ids:
        db = sqlite3.connect(root / "media.sqlite3")
        db.execute(
            """INSERT INTO media_jobs
               (dvd_id,status,attempt_count,created_at,updated_at)
               VALUES(?,'COMPLETED',1,?,?)""",
            (dvd_id, STAMP, STAMP),
        )
        db.commit()
        db.close()
    fake = FakeJellyfin("PENDING")
    result = reconcile_jellyfin_visibility(
        root / "discovery.sqlite3",
        root / "media.sqlite3",
        root / "media-writer.lock",
        fake,
        max_items=1,
        max_seed_items=1,
    )
    assert result["seeded"] == 1
    assert result["checked"] == 1
    assert len(fake.paths) == 1
    assert read_rows(
        root / "media.sqlite3",
        "SELECT count(*) FROM media_jellyfin_visibility",
    )[0][0] == 1

    # A distinct isolated fixture proves exact target registration and processing.
    target_root = root / "target-case"
    target_root.mkdir()
    target_ids = ["ABC-123", "DEF-456", "GHI-789"]
    init_pair(target_root, target_ids)
    target_processed = []
    target_config = make_config(target_root, apply=True, target="DEF-456",
                                visibility_max_items=0,
                                visibility_seed_max_items=0)
    target_result = runner.run_stage9_media_once(
        target_config, services=services(target_processed)
    )
    assert target_result["registered"] == 1
    assert target_processed == ["DEF-456"]
    assert read_rows(
        target_root / "media.sqlite3",
        "SELECT dvd_id FROM media_jobs ORDER BY dvd_id",
    ) == [("DEF-456",)]


def exhausted_state_updates_are_bounded(root: Path):
    ids = ["ABC-123", "DEF-456", "GHI-789"]
    init_discovery(root / "discovery.sqlite3", ids)
    init_media(
        root / "media.sqlite3",
        jobs=[
            {
                "dvd_id": dvd_id,
                "status": "FAILED",
                "attempt_count": 5,
                "error": "prior-error-" + dvd_id,
                "jellyfin_notification_status": "ATTEMPTED",
                "updated_at": OLD_STAMP,
            }
            for dvd_id in ids
        ],
    )
    title_dir = root / "title-locks"
    title_dir.mkdir()
    result = run_retryable_media_jobs(
        db_path=root / "media.sqlite3",
        writer_lock_path=root / "media-writer.lock",
        processor=lambda _dvd_id: (_ for _ in ()).throw(AssertionError("must not run")),
        max_items=1,
        max_manual_action_updates=1,
        title_lock_dir=title_dir,
    )
    assert result["attempted"] == 0
    assert result["manual_action_updates"] == 1
    assert result["manual_action_updates_deferred"] == 2
    rows = read_rows(
        root / "media.sqlite3",
        "SELECT dvd_id,attempt_count,error,jellyfin_error FROM media_jobs ORDER BY media_job_id",
    )
    assert all(row[1] == 5 and row[2] == "prior-error-" + row[0] for row in rows)
    assert sum(row[3] is not None for row in rows) == 1


def fail_closed_and_locks(root: Path):
    ids = ["ABC-123"]
    init_pair(root, ids)
    config = make_config(root)
    bad_config = runner.RunnerConfig(
        **{**config.__dict__, "max_items": 0}
    )
    try:
        runner.run_stage9_media_once(bad_config)
    except runner.RunnerError as exc:
        assert exc.code == "MEDIA_ITEM_LIMIT_OUT_OF_RANGE"
    else:
        raise AssertionError("invalid limit must fail closed")

    no_confirmation = runner.RunnerConfig(
        **{**make_config(root, apply=True).__dict__, "confirm": ""}
    )
    try:
        runner.run_stage9_media_once(no_confirmation, services={})
    except runner.RunnerError as exc:
        assert exc.code == "APPLY_CONFIRMATION_REQUIRED"
    else:
        raise AssertionError("missing confirmation must fail closed")
    assert not no_confirmation.run_lock_path.exists()

    with runner._exclusive_run_lock(config.run_lock_path):
        try:
            with runner._exclusive_run_lock(config.run_lock_path):
                raise AssertionError("second run lock must fail")
        except runner.RunnerError as exc:
            assert exc.code == "RUN_ALREADY_ACTIVE"

        child_code = """
import sys
from pathlib import Path
import teddy_discovery_media_only_runner as runner
try:
    with runner._exclusive_run_lock(Path(sys.argv[1])):
        print('UNEXPECTED_ACQUIRE')
        raise SystemExit(3)
except runner.RunnerError as exc:
    print(exc.code)
"""
        result = subprocess.run(
            [sys.executable, "-B", "-c", child_code, str(config.run_lock_path)],
            cwd=Path(__file__).absolute().parent,
            env={"PATH": "/usr/bin:/bin"},
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "RUN_ALREADY_ACTIVE"

    corrupt_root = root / "corrupt"
    corrupt_root.mkdir()
    init_discovery(corrupt_root / "discovery.sqlite3", ["ABC-123"])
    (corrupt_root / "media.sqlite3").write_bytes(b"not sqlite")
    corrupt_config = make_config(corrupt_root)
    try:
        runner.run_stage9_media_once(corrupt_config)
    except runner.RunnerError as exc:
        assert exc.code == "DATABASE_PREFLIGHT_FAILED"
    else:
        raise AssertionError("corrupt DB must fail closed")
    assert not corrupt_config.run_lock_path.exists()

    symlink_path = corrupt_root / "discovery-link.sqlite3"
    symlink_path.symlink_to(corrupt_root / "discovery.sqlite3")
    symlink_config = replace(corrupt_config, discovery_db_path=symlink_path)
    try:
        runner.run_stage9_media_once(symlink_config)
    except runner.RunnerError as exc:
        assert exc.code == "SYMLINK_PATH_COMPONENT"
    else:
        raise AssertionError("symlink DB path must fail closed")

    budget_config = replace(config, jellyfin_get_max_requests=1)
    try:
        runner.run_stage9_media_once(budget_config)
    except runner.RunnerError as exc:
        assert exc.code == "JELLYFIN_GET_LIMIT_OUT_OF_RANGE"
    else:
        raise AssertionError("undersized GET budget must fail closed")


def failed_job_stops_later_visibility(root: Path):
    init_pair(root, ["ABC-123"])
    processed = []
    visibility_calls = []
    fake_services = {
        "reconcile": reconcile_media_jobs,
        "run_jobs": lambda **_kwargs: {"attempted": 1, "failed": 1},
        "visibility": lambda *args, **kwargs: visibility_calls.append(True),
        "processor": lambda dvd_id: processed.append(dvd_id),
        "jellyfin": FakeJellyfin(),
        "get_budget": FakeGetBudget(),
    }
    config = make_config(root, apply=True)
    result = runner.run_stage9_media_once(config, services=fake_services)
    assert result["status"] == "PARTIAL_FAILURE"
    assert result["jellyfin_visibility"] is None
    assert not visibility_calls


def jellyfin_request_budget_is_bounded():
    calls = []
    class FakeOpener:
        def open(self, request, timeout=10):
            calls.append((request.get_method(), request.full_url, timeout))
            return object()

    budget = runner._JellyfinRequestBudget(
        max_get_requests=2,
        max_post_requests=1,
        opener=FakeOpener(),
    )
    budget(Request("http://jellyfin.test/System/Info", method="GET"))
    budget(Request("http://jellyfin.test/Items", method="GET"))
    try:
        budget(Request("http://jellyfin.test/Items", method="GET"))
    except RuntimeError as exc:
        assert "budget" in str(exc)
    else:
        raise AssertionError("GET budget must stop additional requests")
    budget(Request(
        "http://jellyfin.test/Library/Media/Updated",
        data=b"{}",
        method="POST",
    ))
    try:
        budget(Request(
            "http://jellyfin.test/Library/Media/Updated",
            data=b"{}",
            method="POST",
        ))
    except RuntimeError as exc:
        assert "budget" in str(exc)
    else:
        raise AssertionError("POST budget must stop additional requests")
    try:
        budget(Request("http://jellyfin.test/Items", data=b"{}", method="PUT"))
    except RuntimeError as exc:
        assert "method" in str(exc)
    else:
        raise AssertionError("unexpected write method must fail closed")
    assert budget.get_requests == 2
    assert budget.post_attempts == 1
    assert len(calls) == 3
    assert runner._RejectJellyfinRedirects().redirect_request(
        Request("http://jellyfin.test/Items"), None, 302, "redirect", {},
        "http://other.test/Items",
    ) is None


def thumbnail_runner_integration(root: Path):
    from teddy_discovery_media_jobs import run_thumbnail_jobs
    from teddy_discovery_media_pipeline import run_thumbnail_processor
    from teddy_discovery_media_filestation_smoke import FakeFileStation, _adapter, API_LIBRARY_ROOT, VIDEO_BYTES
    root.mkdir()
    ids = ['ABC-123', 'XYZ-456']
    init_discovery(root / 'discovery.sqlite3', ids)
    init_media(root / 'media.sqlite3', jobs=[dict(dvd_id=d, status='COMPLETED', nfo_status='COMPLETE', poster_status='PENDING', jellyfin_notification_status='VISIBLE', jellyfin_recovery_status='VISIBLE') for d in ids])
    with sqlite3.connect(root / 'discovery.sqlite3') as db:
        for dvd in ids:
            db.execute('UPDATE holdings SET size_bytes=?, relative_path=? WHERE dvd_id=?', (len(VIDEO_BYTES), dvd.split('-')[0] + '/' + dvd + '/' + dvd + '.mkv', dvd))
            db.execute('UPDATE titles SET cover_url=? WHERE dvd_id=?', ('', dvd))
    fake = FakeFileStation()
    for dvd in ids:
        family = dvd.split('-')[0]
        fake.directories.add(API_LIBRARY_ROOT + '/' + family)
        folder = API_LIBRARY_ROOT + '/' + family + '/' + dvd
        fake.directories.add(folder); fake.files[folder + '/' + dvd + '.mkv'] = VIDEO_BYTES
        fake.files[folder + '/' + dvd + '.nfo'] = b'original nfo'
    image = b'\xff\xd8\xfffixture\xff\xd9'; calls = []
    def fetch(url, maximum):
        calls.append(url); return 200, url, 'image/jpeg', image
    def process(dvd):
        with _adapter(root, fake) as adapter:
            return run_thumbnail_processor(db_path=root / 'discovery.sqlite3', dvd_id=dvd, file_station=adapter, fetcher=fetch)
    svc = {'reconcile': lambda *a, **k: 0, 'run_jobs': lambda **k: {'attempted':0,'failed':0},
           'visibility': lambda *a, **k: None, 'processor': lambda d: None,
           'jellyfin': FakeJellyfin(), 'run_thumbnail_jobs':run_thumbnail_jobs, 'thumbnail_processor':process}
    default = make_config(root, apply=True, max_items=2)
    result = runner.run_stage9_media_once(default, services=svc)
    assert result['status'] == 'COMPLETE' and result['thumbnail'] is None and not calls and not fake.uploads
    enabled = replace(default, thumbnail_enabled=True)
    result = runner.run_stage9_media_once(enabled, services=svc)
    assert result['status']=='COMPLETE' and result['thumbnail']['complete']==2
    assert len(calls)==2 and len(fake.uploads)==2
    again = runner.run_stage9_media_once(enabled, services=svc)
    assert again['thumbnail']['attempted']==0 and len(calls)==2
    rows = read_rows(root / 'media.sqlite3', 'SELECT nfo_status,poster_status,jellyfin_notification_status FROM media_jobs')
    assert rows == [('COMPLETE','PENDING','VISIBLE')] * 2
    with sqlite3.connect(root / 'media.sqlite3') as db:
        db.execute("UPDATE media_jobs SET thumbnail_status='PENDING',thumbnail_attempt_count=0,thumbnail_updated_at=NULL WHERE dvd_id=?", (ids[0],))
    target_cover = API_LIBRARY_ROOT + '/' + ids[0].split('-')[0] + '/' + ids[0] + '/cover.jpg'
    fake.files[target_cover] = image
    skipped = runner.run_stage9_media_once(enabled, services=svc)
    assert skipped['status']=='COMPLETE' and skipped['thumbnail']['skipped']==1
    assert fake.files[target_cover]==image and len(calls)==2 and len(fake.uploads)==2
    svc['run_jobs'] = lambda **k: {'attempted': 1, 'failed': 1}
    failed = runner.run_stage9_media_once(enabled, services=svc)
    assert failed['status'] == 'PARTIAL_FAILURE' and failed['thumbnail']['held_reasons'] == {'MEDIA_FAILURE': 1}
    print('THUMBNAIL_RUNNER_INTEGRATION=PASS')


def thumbnail_only_guards(root: Path):
    from contextlib import ExitStack, redirect_stdout
    from io import StringIO
    from unittest.mock import patch
    root.mkdir()
    ids = ['ABC-123', 'XYZ-456']
    init_discovery(root / 'discovery.sqlite3', ids)
    init_media(root / 'media.sqlite3', jobs=[dict(dvd_id=d, status='COMPLETED', nfo_status='COMPLETE') for d in ids] + [dict(dvd_id='NFO-000')])
    config = make_config(root, thumbnail_only=True, target=ids[0])
    checks = 0

    def snapshot():
        return {p.name: (p.stat().st_size, p.stat().st_mtime_ns, p.stat().st_ctime_ns,
                         hashlib.sha256(p.read_bytes()).hexdigest())
                for p in root.iterdir() if p.is_file()}

    def expect_error(candidate, code):
        try:
            runner.run_stage9_media_once(candidate, services={})
        except runner.RunnerError as exc:
            assert exc.code == code, exc.code
        else:
            raise AssertionError('expected ' + code)

    with sqlite3.connect(config.media_db_path) as db:
        db.execute("UPDATE media_jobs SET status='FAILED', error='kept' WHERE dvd_id=?", (ids[0],))
    expect_error(config, 'THUMBNAIL_TARGET_NOT_READY')
    with sqlite3.connect(config.media_db_path) as db:
        assert db.execute('SELECT status,error FROM media_jobs WHERE dvd_id=?', (ids[0],)).fetchone()==('FAILED','kept')
        db.execute("UPDATE media_jobs SET status='COMPLETED',error=NULL WHERE dvd_id=?", (ids[0],))
    checks += 1
    before = snapshot()
    with ExitStack() as stack:
        for name in ('_build_services', '_build_thumbnail_services', '_exclusive_run_lock'):
            stack.enter_context(patch.object(runner, name, side_effect=AssertionError('dry-run execution')))
        for name in ('_connect_media', '_migrate_media_artifact_columns'):
            stack.enter_context(patch('teddy_discovery_media_jobs.' + name, side_effect=AssertionError('migration')))
        result = runner.run_stage9_media_once(config)
        assert result['status'] == 'DRY_RUN' and result['stage'] == 'stage9-thumbnail-only'
        assert result['external_calls'] == result['database_writes'] == 0
        assert not config.run_lock_path.exists() and not config.media_writer_lock_path.exists()
        checks += 1
        args = ['--thumbnail-only', '--target-dvd-id', ids[1], '--max-items', '1',
                '--discovery-db', str(config.discovery_db_path), '--media-db', str(config.media_db_path),
                '--media-writer-lock', str(config.media_writer_lock_path), '--run-lock', str(config.run_lock_path),
                '--title-lock-dir', str(config.title_lock_dir)]
        args += ['--expected-thumbnail-attempt-count', '2']
        out = StringIO()
        with redirect_stdout(out):
            assert runner.main(args) == 0
        assert json.loads(out.getvalue())['target_dvd_id'] == ids[1]
        checks += 1
    assert snapshot() == before
    checks += 1
    for candidate, code in (
        (replace(config, expected_thumbnail_attempt_count=-1), 'INVALID_EXPECTED_THUMBNAIL_ATTEMPT_COUNT'),
        (replace(config, expected_thumbnail_attempt_count=True), 'INVALID_EXPECTED_THUMBNAIL_ATTEMPT_COUNT'),
        (replace(config, thumbnail_only=False, expected_thumbnail_attempt_count=2), 'INVALID_EXPECTED_THUMBNAIL_ATTEMPT_COUNT'),
        (replace(config, target_dvd_id=None, expected_thumbnail_attempt_count=2), 'INVALID_EXPECTED_THUMBNAIL_ATTEMPT_COUNT'),
        (replace(config, target_dvd_id=None), 'THUMBNAIL_TARGET_REQUIRED'),
        (replace(config, target_dvd_id=''), 'INVALID_TARGET_DVD_ID'),
        (replace(config, max_items=2), 'THUMBNAIL_SINGLE_ITEM_REQUIRED'),
        (replace(config, thumbnail_enabled=True), 'CONFLICTING_THUMBNAIL_MODES'),
        (replace(config, target_dvd_id='MISSING-789'), 'THUMBNAIL_TARGET_NOT_FOUND'),
        (replace(config, target_dvd_id='NFO-000'), 'THUMBNAIL_TARGET_NOT_READY'),
    ):
        expect_error(candidate, code)
        checks += 1

    apply_config = make_config(root, apply=True, thumbnail_only=True, target=ids[0])
    expect_error(replace(apply_config, confirm=''), 'APPLY_CONFIRMATION_REQUIRED')
    checks += 1
    # Each missing column independently blocks both dry-run and apply before
    # any service construction or migration-capable application initialization.
    for column in sorted(runner.REQUIRED_THUMBNAIL_COLUMNS):
        missing_root = root / column
        missing_root.mkdir()
        init_discovery(missing_root / 'discovery.sqlite3', ids)
        init_media(missing_root / 'media.sqlite3', jobs=[dict(dvd_id=ids[0], status='COMPLETED', nfo_status='COMPLETE')])
        missing = make_config(missing_root, thumbnail_only=True, target=ids[0])
        with sqlite3.connect(missing.media_db_path) as db:
            db.execute('ALTER TABLE media_jobs DROP COLUMN ' + column)
        content = Path(missing.media_db_path).read_bytes()
        with patch('teddy_discovery_media_jobs._connect_media', side_effect=AssertionError('initialization')), \
             patch('teddy_discovery_media_jobs._migrate_media_artifact_columns', side_effect=AssertionError('migration')), \
             patch.object(runner, '_build_thumbnail_services', side_effect=AssertionError('service')):
            expect_error(missing, 'THUMBNAIL_SCHEMA_MIGRATION_REQUIRED')
            expect_error(replace(missing, apply=True, confirm=runner.CONFIRMATION), 'THUMBNAIL_SCHEMA_MIGRATION_REQUIRED')
        assert Path(missing.media_db_path).read_bytes() == content
        assert not missing.run_lock_path.exists() and not missing.media_writer_lock_path.exists()
        checks += 1
    # An uncheckpointed DB cannot be assumed immutable or read without side effects.
    wal = Path(str(config.media_db_path) + '-wal')
    wal.write_bytes(b'active WAL fixture')
    expect_error(config, 'THUMBNAIL_PREFLIGHT_ACTIVE_WAL')
    wal.unlink()
    checks += 1
    print(f'THUMBNAIL_ONLY_GUARDS={checks} PASS / 0 FAIL')


def thumbnail_only_processing(root: Path):
    from contextlib import ExitStack
    from unittest.mock import patch
    from teddy_discovery_media_jobs import run_thumbnail_jobs
    root.mkdir()
    ids = ['ABC-123', 'XYZ-456']
    init_discovery(root / 'discovery.sqlite3', ids)
    init_media(root / 'media.sqlite3', jobs=[dict(dvd_id=d, status='COMPLETED', nfo_status='COMPLETE',
               poster_status='PENDING', jellyfin_notification_status='VISIBLE', jellyfin_recovery_status='VISIBLE') for d in ids])
    config = make_config(root, apply=True, thumbnail_only=True, target=ids[0])
    # A thumbnail-only mode has no dependency on visibility state or Jellyfin credentials.
    with sqlite3.connect(config.media_db_path) as db:
        db.execute('DROP TABLE media_jellyfin_visibility')
    db.close()
    config = replace(config, jellyfin_base_url='', jellyfin_key_path=None)
    calls = []
    outcome = {'status': 'COMPLETE'}
    def processor(dvd):
        calls.append(dvd)
        return outcome
    def fields():
        return read_rows(config.media_db_path, 'SELECT dvd_id,status,attempt_count,nfo_status,poster_status,jellyfin_notification_status,jellyfin_recovery_status,created_at,updated_at FROM media_jobs ORDER BY dvd_id')
    before = fields()
    services = {'run_thumbnail_jobs': run_thumbnail_jobs, 'thumbnail_processor': processor}
    checks = 0
    mismatch = runner.run_stage9_media_once(replace(config, expected_thumbnail_attempt_count=2), services=services)
    assert mismatch['thumbnail']['held_reasons'] == {'HELD_CONFLICT': 1} and not calls
    checks += 1
    config = replace(config, expected_thumbnail_attempt_count=0)
    with ExitStack() as stack:
        for name in ('teddy_discovery_media_jobs.reconcile_media_jobs',
                     'teddy_discovery_media_jobs.run_retryable_media_jobs',
                     'teddy_discovery_media_pipeline.run_media_pipeline',
                     'teddy_discovery_media_metadata.build_media_bundle',
                     'teddy_discovery_jellyfin.JellyfinClient',
                     'teddy_discovery_jellyfin_visibility.reconcile_jellyfin_visibility'):
            stack.enter_context(patch(name, side_effect=AssertionError('non-thumbnail execution')))
        stack.enter_context(patch.object(runner, '_build_services', side_effect=AssertionError('normal services')))
        first = runner.run_stage9_media_once(config, services=services)
        assert first['status'] == 'COMPLETE' and first['thumbnail']['complete'] == 1 and calls == [ids[0]]
        assert first['non_thumbnail_execution'] == first['registered'] == first['jellyfin_get_requests'] == first['jellyfin_post_attempts'] == 0
        assert first['jellyfin_visibility'] is None
        checks += 1
        assert read_rows(config.media_db_path, "SELECT thumbnail_attempt_count FROM media_jobs WHERE dvd_id='XYZ-456'") == [(0,)]
        checks += 1
        again = runner.run_stage9_media_once(config, services=services)
        assert again['thumbnail']['attempted'] == 0 and calls == [ids[0]]
        checks += 1
        second_config = replace(config, target_dvd_id=ids[1], expected_thumbnail_attempt_count=None)
        outcome = {'status': 'PENDING', 'error': 'candidate unavailable'}
        pending = runner.run_stage9_media_once(second_config, services=services)
        assert pending['status'] == 'PENDING' and pending['thumbnail']['pending'] == 1 and calls == ids
        delayed = runner.run_stage9_media_once(second_config, services=services)
        assert delayed['status'] == 'PENDING' and delayed['thumbnail']['held_reasons'] == {'HELD_BACKOFF': 1} and calls == ids
        checks += 1
        # Explicit fixture reset to examine the other processor outcomes.
        for expected, status in (('FAILED', 'PENDING'), ('ATTENTION', 'PARTIAL_FAILURE'), ('SKIPPED', 'COMPLETE')):
            with sqlite3.connect(config.media_db_path) as db:
                db.execute("UPDATE media_jobs SET thumbnail_status='PENDING',thumbnail_attempt_count=0,thumbnail_updated_at=NULL WHERE dvd_id=?", (ids[1],))
            db.close()
            outcome = {'status': expected}
            result = runner.run_stage9_media_once(second_config, services=services)
            assert result['status'] == status
            checks += 1
    assert fields() == before
    checks += 1
    print(f'THUMBNAIL_ONLY_PROCESSING={checks} PASS / 0 FAIL')



def thumbnail_only_service_boundary(root: Path):
    from contextlib import ExitStack
    from unittest.mock import patch
    from teddy_discovery_media_filestation_smoke import FakeFileStation, _adapter, API_LIBRARY_ROOT, VIDEO_BYTES
    from teddy_discovery_media_filestation import SynologyFileStationMediaAdapter
    root.mkdir()
    ids = ['ABC-123', 'XYZ-456']
    init_discovery(root / 'discovery.sqlite3', ids)
    init_media(root / 'media.sqlite3', jobs=[dict(dvd_id=d, status='COMPLETED', nfo_status='COMPLETE',
        poster_status='PENDING', jellyfin_notification_status='VISIBLE', jellyfin_recovery_status='VISIBLE') for d in ids])
    with sqlite3.connect(root / 'discovery.sqlite3') as db:
        for dvd in ids:
            db.execute('UPDATE holdings SET size_bytes=?,relative_path=? WHERE dvd_id=?',
                       (len(VIDEO_BYTES), dvd.split('-')[0] + '/' + dvd + '/' + dvd + '.mp4', dvd))
            db.execute('UPDATE titles SET cover_url=? WHERE dvd_id=?', ('', dvd))
    db.close()
    fake = FakeFileStation()
    for dvd in ids:
        family = dvd.split('-')[0]
        folder = API_LIBRARY_ROOT + '/' + family + '/' + dvd
        fake.directories.update({API_LIBRARY_ROOT + '/' + family, folder})
        fake.files[folder + '/' + dvd + '.mp4'] = VIDEO_BYTES
        fake.files[folder + '/' + dvd + '.nfo'] = b'original nfo'
    before = dict(fake.files)
    config = make_config(root, apply=True, thumbnail_only=True, target=ids[0])
    config = replace(config, expected_release_id='a' * 40, jellyfin_base_url='', jellyfin_key_path=None)
    image = b'\xff\xd8\xffoffline candidate\xff\xd9'
    config = replace(config, canary_image_size=len(image), canary_image_sha256=hashlib.sha256(image).hexdigest())
    requests = []
    def fetch(url, maximum):
        requests.append(url)
        return 200, url, 'image/jpeg', image
    with ExitStack() as stack:
        stack.enter_context(patch.object(runner, '_validate_runtime', return_value=Path(runner.__file__).parent))
        stack.enter_context(patch.object(runner, '_build_services', side_effect=AssertionError('normal services')))
        for name in ('teddy_discovery_jellyfin.JellyfinClient',
                     'teddy_discovery_media_jobs.reconcile_media_jobs',
                     'teddy_discovery_media_jobs.run_retryable_media_jobs',
                     'teddy_discovery_media_pipeline.run_media_pipeline',
                     'teddy_discovery_media_metadata.build_nfo_bytes',
                     'teddy_discovery_jellyfin_visibility.reconcile_jellyfin_visibility'):
            stack.enter_context(patch(name, side_effect=AssertionError('forbidden general execution')))
        publish = stack.enter_context(patch.object(SynologyFileStationMediaAdapter, 'publish_bundle', side_effect=AssertionError('NFO publication')))
        tls = stack.enter_context(patch('teddy_discovery_media_filestation.make_tls_context', return_value=object()))
        adapter = stack.enter_context(patch('teddy_discovery_media_filestation.SynologyFileStationMediaAdapter', side_effect=lambda **kw: _adapter(root, fake)))
        proxy = stack.enter_context(patch('teddy_discovery_media_thumbnail.make_candidate_proxy_fetcher', return_value=fetch))
        for dvd in ids:
            result = runner.run_stage9_media_once(replace(config, target_dvd_id=dvd))
            assert result['thumbnail']['complete']==1 and result['status']=='COMPLETE'
            assert result['jellyfin_get_requests']==result['jellyfin_post_attempts']==0
        assert tls.call_count == adapter.call_count == 2 and publish.call_count == 0
        assert all(call.args == (config.poster_proxy_url,) for call in proxy.call_args_list)
    assert len(requests) == 2 and len(fake.uploads) == 2
    assert all(fake.files[k] == v for k, v in before.items())
    print('THUMBNAIL_ONLY_SERVICE_BOUNDARY=2 PASS / 0 FAIL')


def new_media_actual_runner_boundary(root: Path):
    from contextlib import ExitStack
    from unittest.mock import patch
    from teddy_discovery_media_filestation_smoke import FakeFileStation, _adapter, API_LIBRARY_ROOT, VIDEO_BYTES
    from teddy_discovery_media_pipeline_smoke import FakeJellyfin as PipelineJellyfin
    root.mkdir()
    init_discovery(root / 'discovery.sqlite3', ['ABC-123'])
    init_media(root / 'media.sqlite3')
    with sqlite3.connect(root / 'discovery.sqlite3') as db:
        db.execute('UPDATE holdings SET relative_path=?, size_bytes=?', ('ABC/ABC-123/ABC-123.mp4', len(VIDEO_BYTES)))
        db.execute("UPDATE titles SET cover_url=''")
    fake = FakeFileStation()
    jpeg = b'\xff\xd8\xfffixture\xff\xd9'
    calls = []
    def fetch(url, maximum):
        calls.append(url)
        return (200, url, 'image/jpeg', jpeg)
    config = make_config(root, apply=True, target='ABC-123', visibility_max_items=0, visibility_seed_max_items=0,
        expected_release_id='a' * 40)
    with ExitStack() as stack:
        stack.enter_context(patch.object(runner, '_validate_runtime', return_value=Path(runner.__file__).parent))
        stack.enter_context(patch('teddy_discovery_media_filestation.make_tls_context', return_value=object()))
        stack.enter_context(patch('teddy_discovery_media_filestation.SynologyFileStationMediaAdapter', side_effect=lambda **kw: _adapter(root, fake)))
        stack.enter_context(patch('teddy_discovery_jellyfin.JellyfinClient', return_value=PipelineJellyfin([{'status':'VISIBLE'}])))
        stack.enter_context(patch('teddy_discovery_media_metadata.make_poster_fetcher', return_value=lambda url: (_ for _ in ()).throw(AssertionError('no poster URL'))))
        stack.enter_context(patch('teddy_discovery_media_thumbnail.make_candidate_proxy_fetcher', return_value=fetch))
        result = runner.run_stage9_media_once(config)
    assert result['media']['completed'] == 1, result
    assert calls == ['https://fourhoi.com/abc-123/cover-n.jpg']
    assert fake.files[API_LIBRARY_ROOT + '/ABC/ABC-123/cover.jpg'] == jpeg
    assert fake.files[API_LIBRARY_ROOT + '/ABC/ABC-123/ABC-123.mp4'] == VIDEO_BYTES
    print('NEW_MEDIA_ACTUAL_RUNNER_BOUNDARY=PASS')


def existing_image_actual_runner_boundary(root: Path):
    from contextlib import ExitStack
    from unittest.mock import patch
    from teddy_discovery_media_filestation_smoke import FakeFileStation, _adapter, API_LIBRARY_ROOT, VIDEO_PATH, VIDEO_BYTES
    root.mkdir()
    init_discovery(root / 'discovery.sqlite3', ['ABC-123'])
    init_media(root / 'media.sqlite3', jobs=[dict(dvd_id='OTHER-123', status='FAILED', nfo_status='UNKNOWN', error='prior', attempt_count=3)])
    with sqlite3.connect(root / 'discovery.sqlite3') as db:
        db.execute('UPDATE holdings SET relative_path=?, size_bytes=?', ('ABC/ABC-123/ABC-123.ts', len(VIDEO_BYTES)))
        db.execute("UPDATE titles SET cover_url=''")
    before = read_rows(root / 'media.sqlite3', 'SELECT * FROM media_jobs')
    fake = FakeFileStation()
    ts = API_LIBRARY_ROOT + '/ABC/ABC-123/ABC-123.ts'
    fake.files[ts] = fake.files.pop(VIDEO_PATH)
    fake.owners[ts] = fake.owners.pop(VIDEO_PATH)
    jpeg = b'\xff\xd8\xfffixture\xff\xd9'
    requests=[]
    def fetch(url, maximum):
        requests.append(url)
        return (200,url,'image/jpeg',jpeg)
    config = make_config(root, apply=True, thumbnail_only=True, existing_image_only=True,
                         target='ABC-123', expected_release_id='a'*40)
    with patch.object(runner, '_validate_runtime', return_value=Path(runner.__file__).parent), patch('teddy_discovery_media_nas_verify.verify_existing_path', side_effect=AssertionError('dry run must not contact NAS')):
        dry = runner.run_stage9_media_once(replace(config, apply=False, confirm=''))
        assert dry['status'] == 'DRY_RUN' and dry['database_writes'] == 0 and dry['external_calls'] == 0
    assert read_rows(root / 'media.sqlite3', 'SELECT * FROM media_jobs') == before
    with ExitStack() as stack:
        stack.enter_context(patch.object(runner, '_validate_runtime', return_value=Path(runner.__file__).parent))
        stack.enter_context(patch('teddy_discovery_media_filestation.make_tls_context', return_value=object()))
        stack.enter_context(patch('teddy_discovery_media_filestation.SynologyFileStationMediaAdapter', side_effect=lambda **kw: _adapter(root, fake, image_only=True)))
        stack.enter_context(patch('teddy_discovery_media_nas_verify.verify_existing_path', return_value=True))
        stack.enter_context(patch('teddy_discovery_media_metadata.make_poster_fetcher', return_value=lambda url: (_ for _ in ()).throw(AssertionError('no poster URL'))))
        stack.enter_context(patch('teddy_discovery_media_thumbnail.make_candidate_proxy_fetcher', return_value=fetch))
        result = runner.run_stage9_media_once(config)
        assert result['image']['status']=='COMPLETE' and result['media_database_writes']==0, result
        with sqlite3.connect(root / 'media.sqlite3') as db:
            db.execute("INSERT INTO media_jobs(dvd_id,status,nfo_status,error,attempt_count,created_at,updated_at) VALUES('ABC-123','FAILED','UNKNOWN','prior-target-error',3,?,?)", (STAMP, STAMP))
        preserved = read_rows(root / 'media.sqlite3', 'SELECT * FROM media_jobs')
        skipped = runner.run_stage9_media_once(config)
        assert skipped['image']['status'] == 'SKIPPED', skipped
        assert read_rows(root / 'media.sqlite3', 'SELECT * FROM media_jobs') == preserved
        with sqlite3.connect(root / 'media.sqlite3') as db:
            db.execute("UPDATE media_jobs SET status='COMPLETED', nfo_status='COMPLETE' WHERE dvd_id='ABC-123'")
        completed_before = read_rows(root / 'media.sqlite3', 'SELECT * FROM media_jobs')
        completed_result = runner.run_stage9_media_once(config)
        assert completed_result['image']['status'] == 'SKIPPED', completed_result
        assert read_rows(root / 'media.sqlite3', 'SELECT * FROM media_jobs') == completed_before
    assert requests == ['https://fourhoi.com/abc-123/cover-n.jpg']
    assert fake.files[API_LIBRARY_ROOT + '/ABC/ABC-123/cover.jpg'] == jpeg and fake.files[ts] == VIDEO_BYTES
    assert preserved[:len(before)] == before
    print('EXISTING_IMAGE_ACTUAL_RUNNER_BOUNDARY=PASS')



def main():
    import_is_side_effect_free()
    with tempfile.TemporaryDirectory(prefix="stage9-media-runner-") as raw:
        root = Path(raw)
        dry_run_is_read_only(root / "dry")
        thumbnail_only_guards(root / "thumb-only-guards")
        thumbnail_only_processing(root / "thumb-only-processing")
        thumbnail_only_service_boundary(root / "thumb-only-services")
        new_media_actual_runner_boundary(root / "new-media-runner")
        existing_image_actual_runner_boundary(root / "existing-image-runner")
        thumbnail_runner_integration(root / "thumb-integration")
        bounded_root = root / "bounded"
        bounded_root.mkdir()
        registration_processing_and_visibility_are_bounded(bounded_root)
        visibility_root = root / "visibility"
        visibility_root.mkdir()
        visibility_seed_limit_and_target_filter(visibility_root)
        exhausted_root = root / "exhausted"
        exhausted_root.mkdir()
        exhausted_state_updates_are_bounded(exhausted_root)
        fail_root = root / "fail-closed"
        fail_root.mkdir()
        fail_closed_and_locks(fail_root)
        jellyfin_request_budget_is_bounded()
        failed_root = root / "failed-job"
        failed_root.mkdir()
        failed_job_stops_later_visibility(failed_root)
    print("stage9 media-only runner smoke: ok")


if __name__ == "__main__":
    main()
