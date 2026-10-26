from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone
import hashlib
import importlib
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
        ssh_host="localhost" if apply else "",
        ssh_user="tester" if apply else "",
        ssh_key_path=root / "ssh-key" if apply else None,
        ssh_known_hosts_path=root / "known-hosts" if apply else None,
        library_root="/volume/adult" if apply else "",
        poster_proxy_url="http://127.0.0.1:8123" if apply else "",
        jellyfin_base_url="http://127.0.0.1:8096" if apply else "",
        jellyfin_key_path=root / "jellyfin-key" if apply else None,
        **overrides,
    )
    if apply:
        (root / "ssh-key").write_text("synthetic", encoding="utf-8")
        (root / "known-hosts").write_text("synthetic", encoding="utf-8")
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


def main():
    import_is_side_effect_free()
    with tempfile.TemporaryDirectory(prefix="stage9-media-runner-") as raw:
        root = Path(raw)
        dry_run_is_read_only(root / "dry")
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
