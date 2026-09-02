from teddy_discovery_completion import (
    plan_remote_downloads,
)


def require(value, message):
    if not value:
        raise RuntimeError(message)


def ready_state():
    return {
        "metadata": {
            "ABC-123": {
                "title": "Test title",
                "metadata_source": "smoke",
            },
        },
        "holdings": [],
        "organizer_jobs": [],
    }


plans = plan_remote_downloads(
    [
        {
            "name": "missav/ABC-123.mp4",
            "size": 123456,
            "modified": 1000,
        },
    ],
    db_state=ready_state(),
)

require(
    len(plans) == 1,
    "ready plan count",
)

plan = plans[0]

require(
    plan.planned_operation
    == "PLAN_STAGE9_SSH_MOVE",
    "ready item not eligible",
)

require(
    plan.destination_relative
    == "ABC/ABC-123/ABC-123.mp4",
    "canonical destination mismatch",
)


state = ready_state()

state["holdings"] = [
    {
        "dvd_id": "ABC-123",
        "present": 1,
    },
]

plan = plan_remote_downloads(
    [
        {
            "name": "missav/ABC-123.mp4",
            "size": 123456,
            "modified": 1000,
        },
    ],
    db_state=state,
)[0]

require(
    plan.collision_type
    == "ALREADY_IN_LIBRARY",
    "holding duplicate not blocked",
)


plans = plan_remote_downloads(
    [
        {
            "name": "missav/ABC-123.mp4",
            "size": 100,
            "modified": 1000,
        },
        {
            "name": "missav/ABC-123.mkv",
            "size": 200,
            "modified": 1000,
        },
    ],
    db_state=ready_state(),
)

require(
    all(
        item.collision_type
        == "MULTIPLE_SOURCE_FILES"
        for item in plans
    ),
    "multiple source files not blocked",
)


plan = plan_remote_downloads(
    [
        {
            "name": "../ABC-123.mp4",
            "size": 100,
            "modified": 1000,
        },
    ],
    db_state=ready_state(),
)[0]

require(
    plan.collision_type
    == "INVALID_SOURCE_PATH",
    "unsafe path not blocked",
)

print(
    "STAGE9_COMPLETION_PLANNER_SMOKE=PASS"
)
