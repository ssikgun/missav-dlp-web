from pathlib import Path
from contextlib import redirect_stderr
import io
import os
import sys
import tempfile

from teddy_discovery_completion import (
    CompletionPlan,
)
from teddy_discovery_completion_runner import (
    CONFIRMATION,
    _make_media_processor,
    main,
    run_once,
)
import teddy_discovery_completion_runner as completion_runner


ready = CompletionPlan(
    source_relative="missav/ABC-123.mp4",
    dvd_id="ABC-123",
    parse_method="filename",
    size_bytes=123,
    mtime_ns=1000,
    destination_relative=(
        "ABC/ABC-123/ABC-123.mp4"
    ),
    metadata_ready=True,
    holding_count=0,
    planned_operation=(
        "PLAN_STAGE9_SSH_MOVE"
    ),
    collision_type="NONE",
    reason="smoke",
)

held = CompletionPlan(
    source_relative="missav/XYZ-999.mp4",
    dvd_id="XYZ-999",
    parse_method="filename",
    size_bytes=456,
    mtime_ns=2000,
    destination_relative=(
        "XYZ/XYZ-999/XYZ-999.mp4"
    ),
    metadata_ready=False,
    holding_count=0,
    planned_operation="HOLD",
    collision_type="METADATA_NOT_READY",
    reason="smoke",
)


def fake_planner(
    items,
    db_path,
):
    return [
        ready,
        held,
    ]


calls = []
state_temp = tempfile.TemporaryDirectory(
    prefix="teddy-stage9-runner-state-"
)
state_path = Path(state_temp.name) / "metadata.sqlite3"


def fake_processor(
    plan,
    **kwargs,
):
    calls.append(
        plan.dvd_id
    )


def fake_metadata_collector(
    dvd_id,
):
    return {
        "dvd_id": dvd_id,
        "status": "NOT_FOUND",
        "route": None,
        "item": None,
    }


# Dry-run must never mutate.
result = run_once(
    items=[],
    db_path=Path("/fake/db"),
    ssh=object(),
    mutator=object(),
    writer_lock_path=
        Path("/fake/lock"),
    planner=fake_planner,
    processor=fake_processor,
    metadata_collector=
        fake_metadata_collector,
)

assert result["total"] == 2
assert result["eligible"] == 1
assert result["held"] == 1
assert result["applied"] == 0
assert calls == []


# Apply requires exact confirmation.
try:
    run_once(
        items=[],
        db_path=Path("/fake/db"),
        ssh=object(),
        mutator=object(),
        writer_lock_path=
            Path("/fake/lock"),
        apply=True,
        confirm="WRONG",
        metadata_state_path=
            state_path,
        planner=fake_planner,
        processor=fake_processor,
        metadata_collector=
            fake_metadata_collector,
    )
except RuntimeError:
    pass
else:
    raise RuntimeError(
        "confirmation guard failed"
    )

assert calls == []


# Correct confirmation applies only eligible item.
result = run_once(
    items=[],
    db_path=Path("/fake/db"),
    ssh=object(),
    mutator=object(),
    writer_lock_path=
        Path("/fake/lock"),
    apply=True,
    confirm=CONFIRMATION,
    max_items=1,
    metadata_state_path=
        state_path,
    planner=fake_planner,
    processor=fake_processor,
    metadata_collector=
        fake_metadata_collector,
)

assert result["applied"] == 1
assert calls == [
    "ABC-123",
]

pipeline_calls = []
original_run_media_pipeline = (
    completion_runner.run_media_pipeline
)
try:
    completion_runner.run_media_pipeline = (
        lambda **kwargs: pipeline_calls.append(kwargs)
        or {"status": "fixture"}
    )
    fake_ssh = object()
    fake_mutator = object()
    fake_jellyfin = object()
    poster_fetcher = object()
    processor = _make_media_processor(
        db_path="fixture-discovery.db",
        ssh=fake_ssh,
        metadata_mutator=fake_mutator,
        jellyfin=fake_jellyfin,
        poster_fetcher=poster_fetcher,
    )
    assert processor("ABC-123") == {"status": "fixture"}
finally:
    completion_runner.run_media_pipeline = (
        original_run_media_pipeline
    )

assert len(pipeline_calls) == 1
assert pipeline_calls[0] == {
    "db_path": "fixture-discovery.db",
    "dvd_id": "ABC-123",
    "ssh": fake_ssh,
    "metadata_mutator": fake_mutator,
    "jellyfin": fake_jellyfin,
    "fetcher": poster_fetcher,
}

# media-only mode skips the planner, organizer, discovery-to-media reconcile,
# and metadata recovery while passing the exact target into the media selector.
media_only_events = []
media_only_pipeline_calls = []
original_run_media_pipeline = (
    completion_runner.run_media_pipeline
)
original_recover_held_metadata = (
    completion_runner.recover_held_metadata
)
proxy_environment_before = {
    name: os.environ.get(name)
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")
}
try:
    completion_runner.run_media_pipeline = (
        lambda **kwargs: media_only_pipeline_calls.append(kwargs)
        or {"status": "fixture"}
    )
    completion_runner.recover_held_metadata = (
        lambda *_args, **_kwargs: media_only_events.append("metadata-recovery")
    )
    proxy_fetcher = object()
    media_processor = _make_media_processor(
        db_path="fixture-discovery.db",
        ssh=fake_ssh,
        metadata_mutator=fake_mutator,
        jellyfin=fake_jellyfin,
        poster_fetcher=proxy_fetcher,
    )

    def media_runner_fixture(**kwargs):
        media_only_events.append(
            ("target", kwargs["target_dvd_id"])
        )
        kwargs["processor"](kwargs["target_dvd_id"])
        return {
            "target_dvd_id": kwargs["target_dvd_id"],
            "attempted": 1,
            "completed": 1,
            "failed": 0,
        }

    def visibility_fixture(
        discovery_db,
        media_db,
        writer_lock,
        jellyfin_client,
        *,
        max_items,
        target_dvd_id=None,
    ):
        media_only_events.append((
            "visibility",
            discovery_db,
            media_db,
            writer_lock,
            jellyfin_client,
            max_items,
            target_dvd_id,
        ))
        return {"seeded": 1, "checked": 1, "visible": 0, "pending": 1, "attention": 0}

    media_only_result = run_once(
        items=None,
        db_path="fixture-discovery.db",
        ssh=fake_ssh,
        mutator=None,
        writer_lock_path="fixture-writer.lock",
        apply=True,
        confirm=CONFIRMATION,
        media_processor=media_processor,
        media_runner=media_runner_fixture,
        jellyfin_visibility_reconciler=visibility_fixture,
        jellyfin_client=fake_jellyfin,
        jellyfin_visibility_max_items=7,
        media_db_path="fixture-media.db",
        media_writer_lock_path="fixture-media.lock",
        media_target_dvd_id="hmn-904",
        media_only=True,
        planner=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("media-only invoked planner")
        ),
        processor=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("media-only invoked organizer")
        ),
        media_reconciler=lambda *_args: (_ for _ in ()).throw(
            AssertionError("media-only reconciled/created jobs")
        ),
    )
finally:
    completion_runner.run_media_pipeline = (
        original_run_media_pipeline
    )
    completion_runner.recover_held_metadata = (
        original_recover_held_metadata
    )

assert media_only_result["applied"] == 0
assert media_only_result["organizer_status"] == "SKIPPED_MEDIA_ONLY"
assert media_only_result["metadata_recovery"]["attempted"] == 0
assert media_only_result["media"]["target_dvd_id"] == "HMN-904"
assert media_only_events == [
    ("target", "HMN-904"),
    (
        "visibility",
        "fixture-discovery.db",
        "fixture-media.db",
        "fixture-media.lock",
        fake_jellyfin,
        7,
        "HMN-904",
    ),
]
assert media_only_result["media"]["jellyfin_visibility"]["pending"] == 1
assert len(media_only_pipeline_calls) == 1
assert media_only_pipeline_calls[0]["dvd_id"] == "HMN-904"
assert media_only_pipeline_calls[0]["fetcher"] is proxy_fetcher
assert media_only_pipeline_calls[0]["jellyfin"] is fake_jellyfin
assert media_only_pipeline_calls[0]["ssh"] is fake_ssh
assert {
    name: os.environ.get(name)
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")
} == proxy_environment_before

# The CLI validates proxy configuration before constructing the SSH client or
# listing downloads, so malformed admin input fails before external I/O.
main_calls = []
original_argv = sys.argv
original_completion_ssh = completion_runner.CompletionSSH
try:
    sys.argv = [
        "teddy_discovery_completion_runner.py",
        "--db", "fixture.db",
        "--writer-lock", "fixture.lock",
        "--host", "host.invalid",
        "--user", "fixture",
        "--key", "fixture.key",
        "--known-hosts", "fixture.known_hosts",
        "--downloads-root", "/downloads",
        "--library-root", "/library",
        "--media-poster-proxy-url",
        "http://proxy.invalid:8888",
    ]
    completion_runner.CompletionSSH = (
        lambda **_kwargs: main_calls.append("ssh-created")
    )
    with redirect_stderr(io.StringIO()):
        try:
            main()
        except SystemExit as exc:
            assert exc.code == 2
        else:
            raise AssertionError("malformed CLI proxy was accepted")
finally:
    sys.argv = original_argv
    completion_runner.CompletionSSH = original_completion_ssh

assert main_calls == []

# The future exact media-only CLI must require the poster proxy before it
# creates SSH/network clients.
try:
    sys.argv = [
        "teddy_discovery_completion_runner.py",
        "--db", "fixture.db",
        "--writer-lock", "fixture.lock",
        "--host", "host.invalid",
        "--user", "fixture",
        "--key", "fixture.key",
        "--known-hosts", "fixture.known_hosts",
        "--downloads-root", "/downloads",
        "--library-root", "/library",
        "--media-db", "fixture-media.db",
        "--media-writer-lock", "fixture-media.lock",
        "--jellyfin-base-url", "http://jellyfin.invalid",
        "--jellyfin-key", "fixture-jellyfin.key",
        "--media-target-dvd-id", "HMN-904",
        "--media-only",
        "--apply",
        "--confirm", CONFIRMATION,
    ]
    with redirect_stderr(io.StringIO()):
        try:
            main()
        except SystemExit as exc:
            assert exc.code == 2
        else:
            raise AssertionError("media-only without proxy was accepted")
finally:
    sys.argv = original_argv

assert main_calls == []

state_temp.cleanup()

print(
    "STAGE9_COMPLETION_RUNNER_SMOKE=PASS"
)
