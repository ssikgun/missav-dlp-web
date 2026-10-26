"""Offline checks for the generic runner's Stage9 Media opt-out."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

from teddy_discovery_completion import CompletionPlan
import teddy_discovery_completion_runner as runner
from teddy_discovery_jellyfin_visibility import VISIBILITY_TABLE_SCHEMA
from teddy_discovery_media_jobs import MEDIA_SCHEMA
from teddy_discovery_media_only_runner import (
    CONFIRMATION as MEDIA_CONFIRMATION,
    RunnerConfig,
    run_stage9_media_once,
)


ready = CompletionPlan(
    source_relative="missav/ABC-123.mp4",
    dvd_id="ABC-123",
    parse_method="filename",
    size_bytes=123,
    mtime_ns=1000,
    destination_relative="ABC/ABC-123/ABC-123.mp4",
    metadata_ready=True,
    holding_count=0,
    planned_operation="PLAN_STAGE9_SSH_MOVE",
    collision_type="NONE",
    reason="smoke",
)


def fail_if_called(*_args, **_kwargs):
    raise AssertionError("Stage9 Media function was called in opt-out mode")


# The generic download/Organizer processor and held-metadata recovery remain active.
events = []
original_recovery = runner.recover_held_metadata
try:
    runner.recover_held_metadata = lambda plans, **kwargs: events.append(
        ("metadata-recovery", len(plans), kwargs["apply"])
    ) or {"attempted": 1, "status": "CHECKED"}
    result = runner.run_once(
        items=["download.mp4"],
        db_path=Path("/offline/discovery.sqlite3"),
        ssh=object(),
        mutator=object(),
        writer_lock_path=Path("/offline/writer.lock"),
        apply=True,
        confirm=runner.CONFIRMATION,
        planner=lambda items, db_path: [ready],
        processor=lambda plan, **kwargs: events.append(("organizer", plan.dvd_id)),
        media_processor=fail_if_called,
        media_reconciler=fail_if_called,
        media_runner=fail_if_called,
        jellyfin_visibility_reconciler=fail_if_called,
        jellyfin_client=object(),
        media_db_path=Path("/offline/media.sqlite3"),
        media_writer_lock_path=Path("/offline/media.lock"),
        skip_media=True,
    )
finally:
    runner.recover_held_metadata = original_recovery

assert result["applied"] == 1
assert result["media"]["status"] == "SKIPPED_BY_EXPLICIT_OPT_OUT"
assert result["media"]["attempted"] == 0
assert result["media"]["reconciled"] == "SKIPPED"
assert result["media"]["jellyfin_visibility"] == "SKIPPED"
assert result["metadata_recovery"]["status"] == "CHECKED"
assert events == [
    ("organizer", "ABC-123"),
    ("metadata-recovery", 1, True),
]


# CLI apply mode needs no Stage9 DB, poster proxy, or Jellyfin configuration.
class FakeSSH:
    def __init__(self, **_kwargs):
        self.listed = 0

    def list_downloads(self):
        self.listed += 1
        return ["download.mp4"]


captured = []
fake_ssh_instances = []
originals = {}
for name in (
    "CompletionSSH",
    "CompletionSSHMutator",
    "MediaMetadataSSHMutator",
    "JellyfinClient",
    "make_poster_fetcher",
    "run_once",
):
    originals[name] = getattr(runner, name)


def make_fake_ssh(**kwargs):
    instance = FakeSSH(**kwargs)
    fake_ssh_instances.append(instance)
    return instance


try:
    runner.CompletionSSH = make_fake_ssh
    runner.CompletionSSHMutator = lambda ssh: ("generic-mutator", ssh)
    runner.MediaMetadataSSHMutator = fail_if_called
    runner.JellyfinClient = fail_if_called
    runner.make_poster_fetcher = fail_if_called
    runner.run_once = lambda **kwargs: captured.append(kwargs) or {"ok": True}
    argv = [
        "teddy_discovery_completion_runner.py",
        "--db", "/offline/discovery.sqlite3",
        "--writer-lock", "/offline/discovery.lock",
        "--host", "fake",
        "--user", "fake",
        "--key", "/offline/fake-key",
        "--known-hosts", "/offline/known-hosts",
        "--downloads-root", "/downloads",
        "--library-root", "/library",
        "--apply",
        "--confirm", runner.CONFIRMATION,
        "--skip-media",
    ]
    original_argv = sys.argv
    sys.argv = argv
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        runner.main()
    sys.argv = original_argv
finally:
    for name, value in originals.items():
        setattr(runner, name, value)
    if "original_argv" in locals():
        sys.argv = original_argv

assert len(captured) == 1
assert captured[0]["skip_media"] is True
assert captured[0]["apply"] is True
assert captured[0]["media_processor"] is None
assert captured[0]["jellyfin_client"] is None
assert captured[0]["items"] == ["download.mp4"]
assert fake_ssh_instances[0].listed == 1
assert json.loads(stdout.getvalue()) == {"ok": True}


# A target-forced or media-only request cannot override the explicit opt-out.
base_argv = [
    "teddy_discovery_completion_runner.py",
    "--db", "/offline/discovery.sqlite3",
    "--writer-lock", "/offline/discovery.lock",
    "--host", "fake",
    "--user", "fake",
    "--key", "/offline/fake-key",
    "--known-hosts", "/offline/known-hosts",
    "--downloads-root", "/downloads",
    "--library-root", "/library",
    "--apply",
    "--skip-media",
]
original_argv = sys.argv
for extra in (["--media-only"], ["--media-target-dvd-id", "ABC-123"]):
    sys.argv = base_argv + list(extra)
    stderr = io.StringIO()
    try:
        with redirect_stderr(stderr):
            runner.main()
    except SystemExit as exc:
        assert exc.code == 2
        assert "--skip-media cannot be combined" in stderr.getvalue()
    else:
        raise AssertionError("conflicting media scope was accepted")
sys.argv = original_argv

# Running the generic opt-out followed by the dedicated runner leaves exactly
# one Stage9 execution owner for the cycle: the generic path calls no media
# service, and the dedicated path performs one bounded registration/job check.
with tempfile.TemporaryDirectory(prefix="stg9media-runner-pair-") as temp:
    root = Path(temp)
    os.chmod(root, 0o700)
    title_locks = root / "title-locks"
    title_locks.mkdir(mode=0o700)
    discovery_db = root / "discovery.sqlite3"
    media_db = root / "media.sqlite3"

    db = sqlite3.connect(discovery_db)
    db.executescript(
        """CREATE TABLE organizer_jobs (job_id INTEGER, dvd_id TEXT, status TEXT);
           CREATE TABLE holdings (dvd_id TEXT, storage_root TEXT, relative_path TEXT,
               size_bytes INTEGER, mtime_ns INTEGER, present INTEGER, discovered_by TEXT);
           CREATE TABLE titles (dvd_id TEXT, title TEXT, release_date TEXT, maker TEXT,
               cover_url TEXT, raw_metadata TEXT, metadata_source TEXT);
           CREATE TABLE title_genres (dvd_id TEXT, genre_id INTEGER);
           CREATE TABLE genres (genre_id INTEGER, name TEXT);
           CREATE TABLE title_people (dvd_id TEXT, person_id INTEGER, role TEXT);
           CREATE TABLE people (person_id INTEGER, name TEXT);"""
    )
    db.close()
    db = sqlite3.connect(media_db)
    db.executescript(MEDIA_SCHEMA)
    db.executescript(VISIBILITY_TABLE_SCHEMA)
    db.executescript(
        """CREATE INDEX IF NOT EXISTS idx_media_jobs_status
               ON media_jobs(status, media_job_id);
           CREATE INDEX IF NOT EXISTS idx_media_jobs_poster_retry
               ON media_jobs(status, nfo_status, poster_status, updated_at);
           CREATE UNIQUE INDEX IF NOT EXISTS idx_media_jobs_dvd_id
               ON media_jobs(dvd_id);
           CREATE INDEX IF NOT EXISTS idx_media_jellyfin_visibility_pending
               ON media_jellyfin_visibility(status, updated_at, dvd_id);"""
    )
    db.close()

    ssh_key = root / "fake-key"
    known_hosts = root / "fake-known-hosts"
    jellyfin_key = root / "fake-jellyfin-key"
    for path in (ssh_key, known_hosts, jellyfin_key):
        path.write_text("offline fixture\n", encoding="utf-8")

    generic_media_calls = []
    generic_result = runner.run_once(
        items=["download.mp4"],
        db_path=discovery_db,
        ssh=object(),
        mutator=object(),
        writer_lock_path=root / "generic-writer.lock",
        apply=True,
        confirm=runner.CONFIRMATION,
        planner=lambda items, db_path: [ready],
        processor=lambda plan, **kwargs: None,
        media_processor=lambda *_args, **_kwargs: generic_media_calls.append("processor"),
        media_reconciler=lambda *_args, **_kwargs: generic_media_calls.append("reconcile"),
        media_runner=lambda **_kwargs: generic_media_calls.append("jobs"),
        jellyfin_visibility_reconciler=lambda *_args, **_kwargs: generic_media_calls.append("visibility"),
        skip_media=True,
    )
    assert generic_result["applied"] == 1
    assert generic_media_calls == []

    dedicated_calls = []
    services = {
        "reconcile": lambda *_args, **_kwargs: dedicated_calls.append("reconcile") or 1,
        "run_jobs": lambda **_kwargs: dedicated_calls.append("jobs") or {"attempted": 1, "completed": 1, "failed": 0},
        "visibility": lambda *_args, **_kwargs: dedicated_calls.append("visibility") or {"checked": 1, "visible": 1},
        "processor": lambda _dvd_id: dedicated_calls.append("processor"),
        "jellyfin": object(),
    }
    config = RunnerConfig(
        discovery_db_path=discovery_db,
        media_db_path=media_db,
        media_writer_lock_path=root / "media-writer.lock",
        run_lock_path=root / "dedicated-run.lock",
        title_lock_dir=title_locks,
        max_items=1,
        visibility_max_items=1,
        visibility_seed_max_items=1,
        apply=True,
        confirm=MEDIA_CONFIRMATION,
        ssh_host="127.0.0.1",
        ssh_user="fixture",
        ssh_key_path=ssh_key,
        ssh_known_hosts_path=known_hosts,
        library_root="/library",
        poster_proxy_url="http://127.0.0.1:9",
        jellyfin_base_url="http://127.0.0.1:9",
        jellyfin_key_path=jellyfin_key,
    )
    dedicated_result = run_stage9_media_once(config, services=services)
    assert dedicated_result["non_media_execution"] == 0
    assert dedicated_result["registered"] == 1
    assert dedicated_result["media"]["attempted"] == 1
    assert dedicated_calls == ["reconcile", "jobs", "visibility"]

print("PASS: generic processing and metadata recovery remain active; Stage9 calls are zero")
print("PASS: CLI opt-out requires no Stage9 runtime configuration and preserves download listing")
print("PASS: exact-target and media-only combinations fail closed")
print("PASS: paired generic opt-out and dedicated runner execute Stage9 work once, within a one-item bound")
