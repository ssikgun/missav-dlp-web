from datetime import (
    datetime,
    timedelta,
)
from dataclasses import replace
from pathlib import Path
import importlib
import sqlite3
import tempfile

from teddy_discovery_completion import (
    plan_remote_downloads,
)
from teddy_discovery_completion_metadata import (
    recover_held_metadata,
)
import teddy_discovery_completion_metadata as metadata_module
from teddy_discovery_completion_runner import (
    CONFIRMATION,
    run_once,
)
from teddy_discovery_db import (
    connect,
    initialize,
)


def require(
    condition,
    message,
):
    if not condition:
        raise AssertionError(message)


def new_db(root: Path) -> Path:
    path = root / "discovery.sqlite3"
    connection = connect(path)
    initialize(connection)
    connection.close()
    return path


def item(dvd_id: str) -> dict:
    return {
        "name": "missav/" + dvd_id + ".mp4",
        "size": 123,
        "modified": 1000,
    }


def found(dvd_id: str, *, item_dvd_id=None, title=None) -> dict:
    return {
        "dvd_id": dvd_id,
        "status": "FOUND",
        "route": "javdatabase-movie",
        "request_count": 1,
        "item": {
            "dvd_id": item_dvd_id or dvd_id,
            "title": title if title is not None else dvd_id + " title",
            "release_date": "2026-08-01",
            "studio": "Test Studio",
            "idols": [],
            "genres": [],
            "source_url": "https://example.invalid/" + dvd_id.lower(),
            "cover_url": "https://example.invalid/" + dvd_id.lower() + ".jpg",
        },
    }


def not_found(dvd_id: str) -> dict:
    return {
        "dvd_id": dvd_id,
        "status": "NOT_FOUND",
        "route": None,
        "request_count": 2,
        "item": None,
    }


def plan_for(db_path: Path, dvd_id: str):
    return plan_remote_downloads(
        [item(dvd_id)],
        db_path=db_path,
    )[0]


def insert_holding(
    db_path: Path,
    dvd_id: str,
    *,
    parse_status: str,
    present: int = 1,
):
    connection = connect(db_path)
    connection.execute(
        """
        INSERT INTO holdings(
            storage_root, relative_path, dvd_id, parse_status,
            size_bytes, mtime_ns, discovered_by, present,
            first_seen_at, last_seen_at
        )
        VALUES ('jav', ?, ?, ?, 123, 1000, 'smoke', ?, ?, ?)
        """,
        (
            "library/" + dvd_id + ".mp4",
            dvd_id,
            parse_status,
            present,
            "2026-09-03",
            "2026-09-03",
        ),
    )
    connection.commit()
    connection.close()


def run_stage9(
    db_path: Path,
    items,
    collector,
    *,
    processor=None,
    max_recovery=1,
):
    if processor is None:
        processor = lambda plan, **kwargs: (_ for _ in ()).throw(
            AssertionError("held item was moved")
        )

    return run_once(
        items=items,
        db_path=db_path,
        ssh=object(),
        mutator=object(),
        writer_lock_path=db_path.parent / "writer.lock",
        operation_lock_path=db_path.parent / "operation.lock",
        apply=True,
        confirm=CONFIRMATION,
        processor=processor,
        metadata_collector=collector,
        metadata_recovery_max_items=max_recovery,
        metadata_state_path=db_path.parent / "metadata-state.sqlite3",
    )


# 1. Metadata-ready remains immediately eligible and does not recover.
with tempfile.TemporaryDirectory(prefix="teddy-stage9-metadata-") as temp:
    root = Path(temp)
    db_path = new_db(root)

    connection = connect(db_path)
    connection.execute(
        """
        INSERT INTO titles(
            dvd_id, title, cover_url, metadata_source,
            first_seen_at, last_seen_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "READY-001",
            "Ready title",
            "https://example.invalid/ready.jpg",
            "smoke",
            "2026-09-03T00:00:00+00:00",
            "2026-09-03T00:00:00+00:00",
        ),
    )
    connection.commit()
    connection.close()

    collector_calls = []
    processed = []

    def must_not_collect(dvd_id):
        collector_calls.append(dvd_id)
        raise AssertionError("ready item entered recovery")

    def processor(plan, **kwargs):
        processed.append(plan.dvd_id)

    result = run_stage9(
        db_path,
        [item("READY-001")],
        must_not_collect,
        processor=processor,
    )

    require(result["eligible"] == 1, "ready item lost eligibility")
    require(result["applied"] == 1, "ready item was not processed")
    require(processed == ["READY-001"], "ready processor mismatch")
    require(collector_calls == [], "ready item invoked recovery")


# 2. FOUND creates a title, and the next planner cycle can move it.
with tempfile.TemporaryDirectory(prefix="teddy-stage9-metadata-") as temp:
    root = Path(temp)
    db_path = new_db(root)
    calls = []

    def found_collector(dvd_id):
        calls.append(dvd_id)
        return found(dvd_id)

    result = run_stage9(
        db_path,
        [item("JUR-750")],
        found_collector,
    )

    require(result["eligible"] == 0, "recovery moved in same cycle")
    require(result["applied"] == 0, "held item moved in recovery cycle")
    require(result["metadata_recovery"]["recovered"] == 1, "FOUND was not recovered")
    require(calls == ["JUR-750"], "FOUND collector call mismatch")

    connection = connect(db_path)
    row = connection.execute(
        """
        SELECT title, metadata_source, cover_url
        FROM titles
        WHERE dvd_id = 'JUR-750'
        """
    ).fetchone()
    connection.close()

    require(row["title"] == "JUR-750 title", "recovered title missing")
    require(
        row["metadata_source"] == "javdatabase-movie",
        "recovered metadata source missing",
    )
    require(row["cover_url"], "recovered cover URL missing")

    replanned = plan_for(db_path, "JUR-750")
    require(
        replanned.planned_operation == "PLAN_STAGE9_SSH_MOVE",
        "recovered item was not eligible on re-plan",
    )


# 3. NOT_FOUND remains held and does not invoke a processor.
with tempfile.TemporaryDirectory(prefix="teddy-stage9-metadata-") as temp:
    root = Path(temp)
    db_path = new_db(root)
    processed = []

    result = run_stage9(
        db_path,
        [item("MSFH-048")],
        not_found,
        processor=lambda plan, **kwargs: processed.append(plan.dvd_id),
    )

    require(result["held"] == 1, "NOT_FOUND item stopped being held")
    require(result["applied"] == 0, "NOT_FOUND item was moved")
    require(result["metadata_recovery"]["not_found"] == 1, "NOT_FOUND not recorded")
    require(result["metadata_recovery"]["failed"] == 0, "NOT_FOUND crashed recovery")
    require(processed == [], "NOT_FOUND invoked NAS processor")

    connection = connect(db_path)
    require(
        connection.execute(
            "SELECT COUNT(*) FROM titles WHERE dvd_id = 'MSFH-048'"
        ).fetchone()[0]
        == 0,
        "NOT_FOUND wrote a title",
    )
    connection.close()


# 4. Collector failure is isolated; ready completion still proceeds.
with tempfile.TemporaryDirectory(prefix="teddy-stage9-metadata-") as temp:
    root = Path(temp)
    db_path = new_db(root)
    connection = connect(db_path)
    connection.execute(
        """
        INSERT INTO titles(
            dvd_id, title, metadata_source,
            first_seen_at, last_seen_at
        )
        VALUES ('READY-002', 'Ready', 'smoke', ?, ?)
        """,
        ("2026-09-03", "2026-09-03"),
    )
    connection.commit()
    connection.close()

    events = []

    def failing_collector(dvd_id):
        events.append("collector:" + dvd_id)
        raise OSError("synthetic network failure")

    processed = []

    def ready_processor(plan, **kwargs):
        events.append("processor:" + plan.dvd_id)
        processed.append(plan.dvd_id)

    result = run_stage9(
        db_path,
        [item("READY-002"), item("PRED-451")],
        failing_collector,
        processor=ready_processor,
    )

    require(result["applied"] == 1, "collector failure stopped completion")
    require(processed == ["READY-002"], "ready completion was not isolated")
    require(
        events == ["processor:READY-002", "collector:PRED-451"],
        "eligible completion did not precede recovery",
    )
    require(result["metadata_recovery"]["failed"] == 1, "collector failure not recorded")


# 5. Malformed metadata and DVD-ID mismatch fail closed without a title write.
with tempfile.TemporaryDirectory(prefix="teddy-stage9-metadata-") as temp:
    root = Path(temp)
    db_path = new_db(root)
    plans = [
        plan_for(db_path, "BAD-001"),
        plan_for(db_path, "BAD-002"),
    ]

    def malformed_collector(dvd_id):
        if dvd_id == "BAD-001":
            return found(dvd_id, item_dvd_id="BAD-999")
        return found(dvd_id, title="")

    result = recover_held_metadata(
        plans,
        db_path=db_path,
        writer_lock_path=root / "writer.lock",
        collector=malformed_collector,
        max_items=2,
    )

    require(result["failed"] == 2, "malformed metadata was accepted")
    require(result["recovered"] == 0, "malformed metadata was written")
    require(
        plan_for(db_path, "BAD-001").collision_type
        == "METADATA_NOT_READY",
        "mismatch did not remain held",
    )

    connection = connect(db_path)
    require(
        connection.execute(
            "SELECT COUNT(*) FROM titles"
        ).fetchone()[0]
        == 0,
        "malformed metadata created titles",
    )
    connection.close()


# 6. Only canonical MATCHED ownership blocks recovery.
with tempfile.TemporaryDirectory(prefix="teddy-stage9-metadata-") as temp:
    root = Path(temp)
    db_path = new_db(root)

    insert_holding(
        db_path,
        "PRED-054",
        parse_status="AMBIGUOUS",
    )
    unowned = plan_for(db_path, "PRED-054")
    require(
        unowned.holding_count == 0,
        "non-MATCHED holding was treated as canonical owned",
    )
    require(
        unowned.collision_type == "METADATA_NOT_READY",
        "non-MATCHED holding changed metadata guard",
    )

    result = run_stage9(
        db_path,
        [item("PRED-054")],
        lambda dvd_id: found(dvd_id),
    )
    require(
        result["metadata_recovery"]["recovered"] == 1,
        "non-MATCHED holding blocked recovery",
    )

    insert_holding(
        db_path,
        "PRED-055",
        parse_status="MATCHED",
    )
    owned = plan_for(db_path, "PRED-055")
    require(
        owned.holding_count == 1,
        "MATCHED holding was not canonical owned",
    )
    calls = []

    def ownership_collector(dvd_id):
        calls.append(dvd_id)
        return found(dvd_id)

    result = run_stage9(
        db_path,
        [item("PRED-055")],
        ownership_collector,
        processor=lambda plan, **kwargs: calls.append(
            "processor:" + plan.dvd_id
        ),
    )

    require(
        result["metadata_recovery"]["candidate_count"] == 0,
        "MATCHED holding entered recovery",
    )
    require(calls == [], "MATCHED owned item invoked a processor")

    stale = plan_for(db_path, "PRED-056")
    insert_holding(
        db_path,
        "PRED-056",
        parse_status="MATCHED",
    )
    stale = replace(stale, holding_count=0)
    result = recover_held_metadata(
        [stale],
        db_path=db_path,
        writer_lock_path=root / "writer.lock",
        collector=ownership_collector,
        state_path=root / "metadata-state-race.sqlite3",
    )

    require(result["skipped_ownership"] == 1, "race ownership was bypassed")
    require(calls == [], "race-owned item entered collector")

    race_plan = plan_for(db_path, "PRED-057")
    race_calls = []

    def writer_race_collector(dvd_id):
        race_calls.append(dvd_id)
        insert_holding(
            db_path,
            dvd_id,
            parse_status="MATCHED",
        )
        return found(dvd_id)

    result = recover_held_metadata(
        [race_plan],
        db_path=db_path,
        writer_lock_path=root / "writer.lock",
        collector=writer_race_collector,
        state_path=root / "metadata-state-writer-race.sqlite3",
    )

    require(
        result["skipped_ownership"] == 1,
        "writer ownership re-check was bypassed",
    )
    require(race_calls == ["PRED-057"], "writer race collector was not called")
    connection = connect(db_path)
    require(
        connection.execute(
            "SELECT COUNT(*) FROM titles WHERE dvd_id = 'PRED-057'"
        ).fetchone()[0]
        == 0,
        "writer race created metadata after ownership appeared",
    )
    connection.close()

    require(
        plan_for(db_path, "PRED-055").collision_type
        == "ALREADY_IN_LIBRARY",
        "ownership plan guard changed",
    )


# 7. Recovery is bounded to one target per cycle.
with tempfile.TemporaryDirectory(prefix="teddy-stage9-metadata-") as temp:
    root = Path(temp)
    db_path = new_db(root)
    plans = [
        plan_for(db_path, "BOUND-001"),
        plan_for(db_path, "BOUND-002"),
    ]
    calls = []

    def bounded_collector(dvd_id):
        calls.append(dvd_id)
        return found(dvd_id)

    result = recover_held_metadata(
        plans,
        db_path=db_path,
        writer_lock_path=root / "writer.lock",
        collector=bounded_collector,
        max_items=1,
    )

    require(result["candidate_count"] == 2, "bounded candidates not counted")
    require(result["attempted"] == 1, "recovery exceeded bound")
    require(result["recovered"] == 1, "bounded recovery did not recover")
    require(len(calls) == 1, "bounded collector called more than once")


# 8. Repeating the same recovery is safe and leaves one title row.
with tempfile.TemporaryDirectory(prefix="teddy-stage9-metadata-") as temp:
    root = Path(temp)
    db_path = new_db(root)
    plan = plan_for(db_path, "IDEM-001")

    def idempotent_collector(dvd_id):
        return found(dvd_id)

    first = recover_held_metadata(
        [plan],
        db_path=db_path,
        writer_lock_path=root / "writer.lock",
        collector=idempotent_collector,
    )
    second = recover_held_metadata(
        [plan],
        db_path=db_path,
        writer_lock_path=root / "writer.lock",
        collector=idempotent_collector,
    )

    require(first["recovered"] == 1, "first idempotent recovery failed")
    require(second["recovered"] == 1, "repeat idempotent recovery failed")

    connection = connect(db_path)
    require(
        connection.execute(
            "SELECT COUNT(*) FROM titles WHERE dvd_id = 'IDEM-001'"
        ).fetchone()[0]
        == 1,
        "repeat recovery duplicated title",
    )
    connection.close()


# 9. Durable backoff rotates past NOT_FOUND/FAILED candidates and retries later.
with tempfile.TemporaryDirectory(prefix="teddy-stage9-metadata-") as temp:
    root = Path(temp)
    db_path = new_db(root)
    state_path = root / "metadata-retry.sqlite3"
    plans = [
        plan_for(db_path, "STARVE-001"),
        plan_for(db_path, "STARVE-002"),
        plan_for(db_path, "STARVE-003"),
    ]
    base = datetime.fromisoformat("2026-09-03T00:00:00+00:00")
    calls = []
    attempts = {}

    def rotating_collector(dvd_id):
        calls.append(dvd_id)
        attempts[dvd_id] = attempts.get(dvd_id, 0) + 1

        if dvd_id == "STARVE-001":
            if attempts[dvd_id] == 1:
                return not_found(dvd_id)
            return found(dvd_id)

        if dvd_id == "STARVE-002":
            raise OSError("synthetic retryable failure")

        return found(dvd_id)

    first = metadata_module.recover_held_metadata(
        plans,
        db_path=db_path,
        writer_lock_path=root / "writer.lock",
        state_path=state_path,
        now=base,
        collector=rotating_collector,
        max_items=1,
    )
    require(calls == ["STARVE-001"], "first candidate was not attempted")
    require(first["not_found"] == 1, "A NOT_FOUND was not recorded")

    state_connection = sqlite3.connect(state_path)
    state_row = state_connection.execute(
        """
        SELECT failure_count, last_status, next_attempt_at
        FROM metadata_recovery_retry
        WHERE dvd_id = 'STARVE-001'
        """
    ).fetchone()
    state_connection.close()
    require(state_row[0] == 1, "A retry count was not durable")
    require(state_row[1] == "NOT_FOUND", "A retry status was not durable")
    require(
        state_row[2] == "2026-09-03T00:15:00+00:00",
        "A backoff interval was not durable",
    )

    # Simulate a new process/module and a new state DB connection.
    importlib.reload(metadata_module)
    second = metadata_module.recover_held_metadata(
        plans,
        db_path=db_path,
        writer_lock_path=root / "writer.lock",
        state_path=state_path,
        now=base + timedelta(minutes=1),
        collector=rotating_collector,
        max_items=1,
    )
    require(
        calls == ["STARVE-001", "STARVE-002"],
        "B did not rotate past backed-off A",
    )
    require(second["failed"] == 1, "B FAILED was not recorded")
    require(second["backoff_skipped"] == 1, "A was retried before backoff")

    third = metadata_module.recover_held_metadata(
        plans,
        db_path=db_path,
        writer_lock_path=root / "writer.lock",
        state_path=state_path,
        now=base + timedelta(minutes=2),
        collector=rotating_collector,
        max_items=1,
    )
    require(
        calls == ["STARVE-001", "STARVE-002", "STARVE-003"],
        "C did not progress past backed-off A/B",
    )
    require(third["recovered"] == 1, "C did not recover")
    require(third["backoff_skipped"] == 2, "A/B backoff was not honored")

    fourth = metadata_module.recover_held_metadata(
        plans,
        db_path=db_path,
        writer_lock_path=root / "writer.lock",
        state_path=state_path,
        now=base + timedelta(minutes=15),
        collector=rotating_collector,
        max_items=1,
    )
    require(
        calls == [
            "STARVE-001",
            "STARVE-002",
            "STARVE-003",
            "STARVE-001",
        ],
        "A was not retryable after backoff expiry",
    )
    require(fourth["recovered"] == 1, "A did not recover after expiry")

    state_connection = sqlite3.connect(state_path)
    require(
        state_connection.execute(
            "SELECT COUNT(*) FROM metadata_recovery_retry "
            "WHERE dvd_id = 'STARVE-001'"
        ).fetchone()[0]
        == 0,
        "successful recovery did not clear retry state",
    )
    state_connection.close()


print("STAGE9_HELD_METADATA_RECOVERY_SMOKE=PASS")
