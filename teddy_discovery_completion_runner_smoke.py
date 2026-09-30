from pathlib import Path
from contextlib import redirect_stderr
import io
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

state_temp.cleanup()

print(
    "STAGE9_COMPLETION_RUNNER_SMOKE=PASS"
)
