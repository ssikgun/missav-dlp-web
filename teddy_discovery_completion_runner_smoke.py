from pathlib import Path

from teddy_discovery_completion import (
    CompletionPlan,
)
from teddy_discovery_completion_runner import (
    CONFIRMATION,
    run_once,
)


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


def fake_processor(
    plan,
    **kwargs,
):
    calls.append(
        plan.dvd_id
    )


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
        planner=fake_planner,
        processor=fake_processor,
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
    planner=fake_planner,
    processor=fake_processor,
)

assert result["applied"] == 1
assert calls == [
    "ABC-123",
]

print(
    "STAGE9_COMPLETION_RUNNER_SMOKE=PASS"
)
