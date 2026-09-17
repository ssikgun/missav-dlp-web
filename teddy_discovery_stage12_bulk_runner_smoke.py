from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace

from teddy_discovery_stage12_bulk_runner import (
    HeartbeatWriter,
    Stage12BulkRunnerError,
    configured_batch_size,
    eligible_pending_ids,
)


class FakeStore:
    def __init__(self, states):
        self._states = tuple(states)

    def list_states(self):
        return self._states


def state(
    dvd_id,
    status,
    *,
    eligibility="ELIGIBLE_NEEDS_KO",
    existing_ko="ABSENT",
):
    return SimpleNamespace(
        dvd_id=dvd_id,
        status=status,
        eligibility=eligibility,
        existing_ko=existing_ko,
        media_path_identity=
            f"AAA/{dvd_id}/{dvd_id}.mp4",
        holding_identity=
            "jav:"
            + f"AAA/{dvd_id}/{dvd_id}.mp4",
    )


def main():
    store = FakeStore(
        (
            state("AAA-001", "PENDING"),
            state("AAA-002", "PUBLISHED"),
            state(
                "AAA-003",
                "PENDING",
                existing_ko="PRESENT",
            ),
            state(
                "AAA-004",
                "FAILED_RETRYABLE",
            ),
            state("AAA-005", "PENDING"),
        )
    )

    assert eligible_pending_ids(store) == (
        "AAA-001",
        "AAA-005",
    )

    assert configured_batch_size(
        143,
        4,
        processed=0,
        max_titles=0,
    ) == 4

    assert configured_batch_size(
        3,
        4,
        processed=140,
        max_titles=0,
    ) == 3

    assert configured_batch_size(
        10,
        4,
        processed=3,
        max_titles=5,
    ) == 2

    broken = FakeStore(
        (
            SimpleNamespace(
                dvd_id="AAA-006",
                status="PENDING",
                eligibility=
                    "ELIGIBLE_NEEDS_KO",
                existing_ko="ABSENT",
                media_path_identity=
                    "AAA/AAA-006/AAA-006.mp4",
                holding_identity=
                    "jav:detached/path.mp4",
            ),
        )
    )

    try:
        eligible_pending_ids(broken)
    except Stage12BulkRunnerError:
        pass
    else:
        raise AssertionError(
            "detached durable identity was accepted"
        )

    with TemporaryDirectory(
        prefix="stage12-bulk-heartbeat-smoke-"
    ) as raw:
        root = Path(raw)
        heartbeat_path = root / "status.json"

        writer = HeartbeatWriter(
            heartbeat_path,
            expected_head="a" * 40,
            batch_size=4,
            interval_seconds=0.05,
        )

        writer.start()
        writer.update(
            current_dvd_id="AAA-001",
            stage="STAGE11",
        )

        time.sleep(0.08)

        first = json.loads(
            heartbeat_path.read_text(
                encoding="utf-8"
            )
        )

        assert first["runner_state"] == "RUNNING"
        assert first["current_dvd_id"] == "AAA-001"
        assert first["stage"] == "STAGE11"
        assert first["head_sha"] == "a" * 40
        assert first["batch_size"] == 4

        writer.finish(
            "COMPLETE",
            stage="COMPLETE",
            current_dvd_id=None,
        )

        final = json.loads(
            heartbeat_path.read_text(
                encoding="utf-8"
            )
        )

        assert final["runner_state"] == "COMPLETE"
        assert final["current_dvd_id"] is None
        assert final["stage"] == "COMPLETE"

        leftovers = tuple(
            root.glob("status.json.tmp.*")
        )

        assert leftovers == ()

    source = Path(
        "teddy_discovery_stage12_bulk_runner.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "JUR-750",
        "EYAN-228",
        "FBOS-015",
        "FC2-PPV-4451371",
        "FC2-PPV-4551303",
    ):
        assert forbidden not in source

    print(
        "STAGE12_BULK_RUNNER_SMOKE=PASS"
    )


if __name__ == "__main__":
    main()
