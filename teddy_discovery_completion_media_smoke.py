from dataclasses import dataclass

from teddy_discovery_completion_runner import (
    CONFIRMATION,
    run_once,
)


@dataclass
class FakePlan:
    dvd_id: str
    planned_operation: str
    source_relative: str
    destination_relative: str


def main():
    calls = []

    plan = FakePlan(
        dvd_id="ABC-123",
        planned_operation=
            "PLAN_STAGE9_SSH_MOVE",
        source_relative=
            "missav/ABC-123.mp4",
        destination_relative=
            "ABC/ABC-123/ABC-123.mp4",
    )

    def planner(items, *, db_path):
        return [plan]

    def processor(
        plan,
        *,
        ssh,
        mutator,
        db_path,
        writer_lock_path,
    ):
        calls.append(
            "organizer"
        )

        return 1

    def reconciler(
        db_path,
        media_db_path,
        media_writer_lock_path,
    ):
        calls.append(
            "reconcile"
        )

        return 1

    def media_processor(
        dvd_id,
    ):
        calls.append(
            "media:" + dvd_id
        )

        return {
            "status":
                "MEDIA_PIPELINE_COMPLETE",
        }

    def media_runner(
        *,
        db_path,
        writer_lock_path,
        processor,
        max_items,
    ):
        calls.append(
            "media-runner"
        )

        processor(
            "ABC-123"
        )

        return {
            "retryable": 1,
            "attempted": 1,
            "completed": 1,
            "failed": 0,
            "jobs": [],
        }

    dry = run_once(
        items=[],
        db_path="fake.db",
        ssh=object(),
        mutator=object(),
        writer_lock_path="fake.lock",
        apply=False,
        planner=planner,
        processor=processor,
        media_processor=
            media_processor,
        media_reconciler=
            reconciler,
        media_runner=
            media_runner,
    )

    assert dry["applied"] == 0
    assert calls == []

    applied = run_once(
        items=[],
        db_path="fake.db",
        ssh=object(),
        mutator=object(),
        writer_lock_path="fake.lock",
        apply=True,
        confirm=CONFIRMATION,
        max_items=1,
        planner=planner,
        processor=processor,
        media_processor=
            media_processor,
        media_reconciler=
            reconciler,
        media_runner=
            media_runner,
        media_max_items=1,
        media_db_path="media.db",
        media_writer_lock_path=
            "media.lock",
    )

    assert applied["applied"] == 1
    assert applied["media"]["reconciled"] == 1
    assert applied["media"]["completed"] == 1

    assert calls == [
        "organizer",
        "reconcile",
        "media-runner",
        "media:ABC-123",
    ]

    print(
        "STAGE9_COMPLETION_MEDIA_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
