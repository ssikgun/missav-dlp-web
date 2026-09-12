"""Offline smoke coverage for the Stage12 rollout state and preflight owner."""

from __future__ import annotations

from pathlib import Path
from dataclasses import replace
import hashlib
import json
import sqlite3
import stat
from types import SimpleNamespace
from tempfile import TemporaryDirectory

from teddy_discovery_asr import (
    ASRResult,
    ASRSegment,
    ASRSourceSnapshot,
    LOCAL_CPU_MEDIUM_RUNTIME_IDENTITY,
)
from teddy_discovery_asr_artifact import serialize_asr_result
from teddy_discovery_ko_srt import generate_korean_srt
from teddy_discovery_stage11_controller import (
    ALIGNMENT_NOT_ATTEMPTED,
    EXTERNAL_JA_TRANSPORT_FAILURE,
    V2_ROUTE_ASR_ONLY,
    _serialize_report,
)
from teddy_discovery_stage12_inventory import (
    ELIGIBLE_NEEDS_KO,
    EXISTING_KO_ABSENT,
    EXISTING_KO_UNRESOLVED,
    EXISTING_KO_VALID,
    SKIPPED_EXISTING_KO,
    Stage12HoldingInventoryRecord,
    Stage12HoldingsInventoryReport,
    UNRESOLVED,
)
from teddy_discovery_stage12_rollout import (
    PUBLICATION_BLOCKED_EXISTING_KO,
    PUBLICATION_BLOCKED_INVALID_ARTIFACT,
    PUBLICATION_BLOCKED_SOURCE_DRIFT,
    PUBLICATION_PROOF_BACKFILLED,
    PUBLICATION_READY,
    STATE_GENERATED,
    STATE_FAILED_RETRYABLE,
    STATE_FAILED_TERMINAL,
    STATE_PENDING,
    STATE_PUBLISHED,
    STATE_RUNNING,
    STATE_SKIPPED_EXISTING_KO,
    STATE_STATUSES,
    STATE_UNRESOLVED,
    Stage12InvalidTransitionError,
    Stage12PublicationReconciliationEvidence,
    Stage12RolloutStateStore,
    Stage12RolloutValidationError,
    select_publication_canary,
)
from teddy_discovery_subtitle import (
    derive_target_ko_relative,
    validate_canonical_holding,
)
from teddy_discovery_subtitle_text import SubtitleCue


def require(condition: bool, marker: str):
    if not condition:
        raise AssertionError(marker)


def expect_raises(exception_type, callback, marker: str):
    try:
        callback()
    except exception_type:
        return
    raise AssertionError(marker)


def inventory_record(
    dvd_id: str,
    *,
    holding_id: int,
    eligibility: str = ELIGIBLE_NEEDS_KO,
    existing_ko: str = EXISTING_KO_ABSENT,
    reason: str = "NO_CANONICAL_KO_SRT",
) -> Stage12HoldingInventoryRecord:
    family = dvd_id.rsplit("-", 1)[0]
    relative_path = f"{family}/{dvd_id}/{dvd_id}.mp4"
    return Stage12HoldingInventoryRecord(
        dvd_id=dvd_id,
        holding_id=holding_id,
        holding_identity="jav:" + relative_path,
        media_path_identity=relative_path,
        source_size_bytes=100,
        source_mtime_ns=200,
        existing_ko=existing_ko,
        eligibility=eligibility,
        reason=reason,
    )


class FakeNAS:
    """Read-only exact-path lstat fake; it has no write API by design."""

    def __init__(self, record, *, destination_exists=False, drift=False):
        self.record = record
        self.destination_exists = destination_exists
        self.drift = drift
        self.calls: list[str] = []

    def lstat(self, relative_path):
        self.calls.append(relative_path)
        video = validate_canonical_holding(
            {
                "dvd_id": self.record.dvd_id,
                "storage_root": "jav",
                "relative_path": self.record.media_path_identity,
                "parse_status": "MATCHED",
                "present": 1,
            },
            self.record.dvd_id,
        )
        destination = derive_target_ko_relative(video)
        if relative_path == self.record.media_path_identity:
            return SimpleNamespace(
                st_mode=stat.S_IFREG,
                st_size=(101 if self.drift else self.record.source_size_bytes),
                st_mtime_ns=self.record.source_mtime_ns,
            )
        if relative_path == destination and self.destination_exists:
            return SimpleNamespace(
                st_mode=stat.S_IFREG,
                st_size=1,
                st_mtime_ns=300,
            )
        raise FileNotFoundError(relative_path)


def write_valid_bundle(root: Path, record: Stage12HoldingInventoryRecord):
    title_root = root / record.dvd_id
    title_root.mkdir(parents=True)
    video = validate_canonical_holding(
        {
            "dvd_id": record.dvd_id,
            "storage_root": "jav",
            "relative_path": record.media_path_identity,
            "parse_status": "MATCHED",
            "present": 1,
        },
        record.dvd_id,
    )
    snapshot = ASRSourceSnapshot.from_holding(
        video,
        source_size=record.source_size_bytes,
        source_mtime_ns=record.source_mtime_ns,
    )
    baseline = ASRResult(
        source_snapshot=snapshot,
        source_language="ja",
        segments=(ASRSegment(0, 1_000, "こんにちは"),),
        engine_version="smoke",
        engine=LOCAL_CPU_MEDIUM_RUNTIME_IDENTITY.engine,
        model=LOCAL_CPU_MEDIUM_RUNTIME_IDENTITY.model,
        device=LOCAL_CPU_MEDIUM_RUNTIME_IDENTITY.device,
        compute_type=LOCAL_CPU_MEDIUM_RUNTIME_IDENTITY.compute_type,
        cpu_threads=LOCAL_CPU_MEDIUM_RUNTIME_IDENTITY.cpu_threads,
        num_workers=LOCAL_CPU_MEDIUM_RUNTIME_IDENTITY.num_workers,
    )
    baseline_raw = serialize_asr_result(baseline)
    clean_raw = generate_korean_srt(
        (SubtitleCue(0, 1_000, "안녕하세요"),)
    ).payload
    assert clean_raw is not None
    baseline_path = title_root / "baseline-asr-v1.json"
    clean_path = title_root / "clean-ko-v1.srt"
    report_path = title_root / "stage11-controller-report-v1.json"
    baseline_path.write_bytes(baseline_raw)
    clean_path.write_bytes(clean_raw)
    report = {
        "title": record.dvd_id,
        "route": V2_ROUTE_ASR_ONLY,
        "baseline_artifact_path": str(baseline_path),
        "baseline_sha256": hashlib.sha256(baseline_raw).hexdigest(),
        "baseline_reused": True,
        "external_ja_outcome": EXTERNAL_JA_TRANSPORT_FAILURE,
        "alignment_outcome": ALIGNMENT_NOT_ATTEMPTED,
        "source_quality_counts": {
            "KEEP": 1,
            "OMIT": 0,
            "REQUIRE_SECOND_EVIDENCE": 0,
        },
        "targeted_source_count": 0,
        "targeted_window_count": 0,
        "targeted_reused": "not_applicable",
        "translation_result_identity": {
            "session_id": "translation-smoke",
            "sha256": "1" * 64,
        },
        "review_result_identity": {
            "request_sha256": "2" * 64,
            "result_sha256": "3" * 64,
            "source_translation_session_id": "translation-smoke",
            "review_execution_session_id": "review-smoke",
        },
        "clean_artifact_path": str(clean_path),
        "clean_sha256": hashlib.sha256(clean_raw).hexdigest(),
        "publication_performed": False,
    }
    report_path.write_bytes(_serialize_report(report))
    title_root.chmod(0o700)
    for artifact_path in (baseline_path, clean_path, report_path):
        artifact_path.chmod(0o600)
    return baseline_path, clean_path, report_path, report


def preflight_fixture(root: Path, record, *, destination_exists=False, drift=False):
    write_valid_bundle(root, record)
    return select_publication_canary(
        Stage12HoldingsInventoryReport((record,)),
        artifact_root=root,
        nas_filesystem=FakeNAS(
            record,
            destination_exists=destination_exists,
            drift=drift,
        ),
    )


def reconciliation_evidence(
    record: Stage12HoldingInventoryRecord,
    digest: str,
    destination: str,
) -> Stage12PublicationReconciliationEvidence:
    return Stage12PublicationReconciliationEvidence(
        destination_relative=destination,
        destination_sha256=digest,
        jellyfin_item_id="item-" + record.dvd_id,
        jellyfin_item_path="/media/adult/" + record.media_path_identity,
        jellyfin_subtitle_path="/media/adult/" + destination,
        subtitle_language="kor",
        subtitle_codec="subrip",
        external_visible=True,
        verification_passed=True,
    )


def publication_proof_for(state):
    return {
        "dvd_id": state.dvd_id,
        "artifact_path": state.artifact_path,
        "artifact_sha256": state.artifact_sha256,
        "report_path": state.report_path,
        "report_sha256": state.report_sha256,
        "publication_performed": True,
        "atomic_install": True,
        "destination_verified": True,
        "destination_relative": state.destination_relative,
        "destination_sha256": state.artifact_sha256,
        "publication_event_identity": "legacy-publication-smoke-1",
    }


def failed_reconciliation_fixture(
    root: Path,
    *,
    publication_provenance: bool = True,
    terminal: bool = False,
):
    record = inventory_record("REC-001", holding_id=900)
    artifact_root = root / "artifacts"
    _, clean_path, report_path, report = write_valid_bundle(
        artifact_root,
        record,
    )
    store = Stage12RolloutStateStore(root / "state.sqlite3")
    store.initialize_from_inventory(
        Stage12HoldingsInventoryReport((record,))
    )
    store.transition(
        record.dvd_id,
        STATE_RUNNING,
        reason="START_RECONCILIATION_FIXTURE",
        provenance={"operation": "SMOKE"},
    )
    digest = report["clean_sha256"]
    store.transition(
        record.dvd_id,
        STATE_GENERATED,
        reason="GENERATED_RECONCILIATION_FIXTURE",
        provenance={"operation": "SMOKE"},
        artifact_path=str(clean_path),
        artifact_sha256=digest,
        report_path=str(report_path),
        report_sha256=hashlib.sha256(
            report_path.read_bytes()
        ).hexdigest(),
    )
    video = validate_canonical_holding(
        {
            "dvd_id": record.dvd_id,
            "storage_root": "jav",
            "relative_path": record.media_path_identity,
            "parse_status": "MATCHED",
            "present": 1,
        },
        record.dvd_id,
    )
    destination = derive_target_ko_relative(video)
    provenance = {
        "operation": "SMOKE_PUBLICATION",
        "publication_performed": True,
        "atomic_install": True,
        "destination_verified": True,
        "destination_relative": destination,
        "destination_sha256": digest,
        "publication_event_identity": "smoke-publication-1",
    }
    failure_provenance = {
        "operation": "SMOKE_RECOGNITION_FAILURE",
        "error": "Jellyfin external Korean subtitle not recognized",
        "error_type": "Stage12BatchTitleError",
        "retry_performed": False,
        "destination": destination,
    }
    if publication_provenance:
        failure_provenance["publication_provenance"] = provenance
    failed_status = (
        STATE_FAILED_TERMINAL if terminal else STATE_FAILED_RETRYABLE
    )
    store.transition(
        record.dvd_id,
        failed_status,
        expected_from=STATE_GENERATED,
        reason="SMOKE_TITLE_FAILURE",
        provenance=failure_provenance,
        destination_relative=destination,
    )
    return (
        store,
        record,
        digest,
        destination,
        reconciliation_evidence(record, digest, destination),
    )


def main():
    # H. CP1 materialization: exactly 172 eligible records plus one unresolved.
    records = tuple(
        inventory_record(
            f"AAA-{index:03d}",
            holding_id=index,
        )
        for index in range(1, 173)
    ) + (
        inventory_record(
            "ZZZ-999",
            holding_id=173,
            eligibility=UNRESOLVED,
            existing_ko=EXISTING_KO_UNRESOLVED,
            reason="SUBTITLE_INVENTORY_INVALID",
        ),
    )
    report = Stage12HoldingsInventoryReport(records)

    with TemporaryDirectory(prefix="stage12-rollout-smoke-") as temp:
        root = Path(temp)
        store = Stage12RolloutStateStore(root / "state.sqlite3")
        counts = store.initialize_from_inventory(report)
        require(sum(counts.values()) == 173, "INITIAL_TOTAL_173")
        require(counts[STATE_PENDING] == 172, "INITIAL_PENDING_172")
        require(counts[STATE_UNRESOLVED] == 1, "INITIAL_UNRESOLVED_1")
        require(
            counts[STATE_SKIPPED_EXISTING_KO] == 0,
            "INITIAL_SKIPPED_EXISTING_KO_0",
        )

        second_counts = store.initialize_from_inventory(report)
        require(second_counts == counts, "IDEMPOTENT_SECOND_INITIALIZE")
        with sqlite3.connect(root / "state.sqlite3") as connection:
            title_count = connection.execute(
                "SELECT COUNT(*) FROM stage12_rollout_titles"
            ).fetchone()[0]
            event_count = connection.execute(
                "SELECT COUNT(*) FROM stage12_rollout_events"
            ).fetchone()[0]
        require(title_count == 173, "NO_DUPLICATE_TITLE_STATE")
        require(event_count == 173, "NO_DUPLICATE_INITIAL_EVENTS")

        first = records[0]
        expect_raises(
            Stage12InvalidTransitionError,
            lambda: store.transition(
                first.dvd_id,
                STATE_PUBLISHED,
                reason="INVALID_DIRECT_PUBLISH",
                provenance={"test": "invalid"},
            ),
            "INVALID_TRANSITION_FAIL_CLOSED",
        )
        store.transition(
            first.dvd_id,
            STATE_RUNNING,
            reason="START_TITLE",
            provenance={"test": "running"},
        )
        recovered = store.recover_running(first.dvd_id)
        require(
            recovered.status == STATE_PENDING
            and recovered.last_transition_reason == "CRASH_RECOVERY",
            "RUNNING_CRASH_RECOVERY",
        )

        second = records[1]
        artifact_path = str(root / "artifact.json")
        report_path = str(root / "report.json")
        digest = "a" * 64
        store.transition(
            second.dvd_id,
            STATE_RUNNING,
            reason="START_TITLE",
            provenance={"test": "generated"},
        )
        store.transition(
            second.dvd_id,
            STATE_GENERATED,
            reason="GENERATED_ARTIFACTS",
            provenance={"test": "generated"},
            artifact_path=artifact_path,
            artifact_sha256=digest,
            report_path=report_path,
            report_sha256=digest,
        )
        expected_destination = derive_target_ko_relative(
            validate_canonical_holding(
                {
                    "dvd_id": second.dvd_id,
                    "storage_root": "jav",
                    "relative_path": second.media_path_identity,
                    "parse_status": "MATCHED",
                    "present": 1,
                },
                second.dvd_id,
            )
        )
        expect_raises(
            Stage12RolloutValidationError,
            lambda: store.transition(
                second.dvd_id,
                STATE_PUBLISHED,
                reason="PUBLISH",
                provenance={"test": "escape"},
                destination_relative="../escape.ko.srt",
            ),
            "DESTINATION_PATH_ESCAPE_REJECTED",
        )
        expect_raises(
            Stage12RolloutValidationError,
            lambda: store.transition(
                second.dvd_id,
                STATE_PUBLISHED,
                reason="PUBLISH",
                provenance={"test": "missing-proof"},
                destination_relative=expected_destination,
            ),
            "PUBLISHED_REQUIRES_ATOMIC_PROOF",
        )
        published = store.transition(
            second.dvd_id,
            STATE_PUBLISHED,
            reason="PUBLISH",
            provenance={
                "test": "publish",
                "publication_performed": True,
                "atomic_install": True,
                "destination_verified": True,
                "destination_relative": expected_destination,
                "destination_sha256": digest,
            },
            destination_relative=expected_destination,
        )
        require(published.status == STATE_PUBLISHED, "PUBLISHED_TRANSITION")
        expect_raises(
            Stage12InvalidTransitionError,
            lambda: store.transition(
                second.dvd_id,
                STATE_RUNNING,
                reason="RERUN",
                provenance={"test": "rerun"},
            ),
            "PUBLISHED_NOT_RERUN",
        )

        # CP5R2: audited post-publication Jellyfin reconciliation.  The
        # fixture contains an explicit successful publication witness in the
        # durable failure event; no NAS, controller, or Jellyfin dependency is
        # provided to this state-only API.
        (
            reconcile_store,
            reconcile_record,
            _reconcile_digest,
            _reconcile_destination,
            reconcile_evidence,
        ) = failed_reconciliation_fixture(
            root / "reconciliation-valid"
        )
        with sqlite3.connect(
            root / "reconciliation-valid" / "state.sqlite3"
        ) as connection:
            before_reconcile_events = connection.execute(
                "SELECT * FROM stage12_rollout_events"
            ).fetchall()
        before_reconcile_events = len(before_reconcile_events)
        reconciled = reconcile_store.reconcile_published(
            reconcile_record.dvd_id,
            evidence=reconcile_evidence,
        )
        require(
            reconciled.status == STATE_PUBLISHED,
            "RECONCILIATION_PUBLISHED",
        )
        with sqlite3.connect(
            root / "reconciliation-valid" / "state.sqlite3"
        ) as connection:
            reconciliation_events = connection.execute(
                """
                SELECT reason, provenance_json
                FROM stage12_rollout_events
                WHERE dvd_id = ?
                ORDER BY event_id
                """,
                (reconcile_record.dvd_id,),
            ).fetchall()
        require(
            len(reconciliation_events) == before_reconcile_events + 1,
            "RECONCILIATION_ONE_EVENT",
        )
        require(
            reconciliation_events[-1][0] == "PUBLICATION_RECONCILED",
            "RECONCILIATION_EVENT_REASON",
        )
        require(
            any(
                row[0] == "SMOKE_TITLE_FAILURE"
                for row in reconciliation_events
            ),
            "ORIGINAL_FAILURE_HISTORY_PRESERVED",
        )
        first_reconcile_sequence = reconciled.transition_sequence
        second_reconciled = reconcile_store.reconcile_published(
            reconcile_record.dvd_id,
            evidence=reconcile_evidence,
        )
        require(
            second_reconciled.status == STATE_PUBLISHED
            and second_reconciled.transition_sequence
            == first_reconcile_sequence,
            "RECONCILIATION_IDEMPOTENT_NOOP",
        )
        with sqlite3.connect(
            root / "reconciliation-valid" / "state.sqlite3"
        ) as connection:
            require(
                connection.execute(
                    "SELECT COUNT(*) FROM stage12_rollout_events"
                ).fetchone()[0]
                == before_reconcile_events + 1,
                "RECONCILIATION_NO_DUPLICATE_EVENT",
            )

        (
            legacy_store,
            legacy_record,
            legacy_digest,
            legacy_destination,
            legacy_evidence,
        ) = failed_reconciliation_fixture(
            root / "legacy-proof-backfill-valid",
            publication_provenance=False,
        )
        legacy_state_before = legacy_store.get(legacy_record.dvd_id)
        legacy_proof = publication_proof_for(legacy_state_before)
        with sqlite3.connect(
            root / "legacy-proof-backfill-valid" / "state.sqlite3"
        ) as connection:
            legacy_event_count_before = connection.execute(
                "SELECT COUNT(*) FROM stage12_rollout_events"
            ).fetchone()[0]
        backfilled = legacy_store.record_verified_publication_proof(
            legacy_record.dvd_id,
            publication_provenance=legacy_proof,
            evidence=legacy_evidence,
        )
        require(
            backfilled.status == STATE_FAILED_RETRYABLE
            and backfilled.transition_sequence
            == legacy_state_before.transition_sequence + 1,
            "LEGACY_BACKFILL_REMAINS_RETRYABLE",
        )
        with sqlite3.connect(
            root / "legacy-proof-backfill-valid" / "state.sqlite3"
        ) as connection:
            legacy_events = connection.execute(
                """
                SELECT from_status, to_status, reason, provenance_json
                FROM stage12_rollout_events
                WHERE dvd_id = ?
                ORDER BY event_id
                """,
                (legacy_record.dvd_id,),
            ).fetchall()
        require(
            len(legacy_events) == legacy_event_count_before + 1,
            "LEGACY_BACKFILL_ONE_EVENT",
        )
        require(
            legacy_events[-1][0] == STATE_FAILED_RETRYABLE
            and legacy_events[-1][1] == STATE_FAILED_RETRYABLE
            and legacy_events[-1][2] == PUBLICATION_PROOF_BACKFILLED,
            "LEGACY_BACKFILL_EVENT_IDENTITY",
        )
        require(
            any(row[2] == "SMOKE_TITLE_FAILURE" for row in legacy_events),
            "LEGACY_FAILURE_HISTORY_PRESERVED",
        )
        backfill_event = json.loads(legacy_events[-1][3])
        require(
            backfill_event["legacy"] is True
            and backfill_event["nas_write_performed"] is False
            and backfill_event["controller_call_performed"] is False,
            "LEGACY_BACKFILL_NO_EXTERNAL_MUTATION",
        )
        second_backfilled = legacy_store.record_verified_publication_proof(
            legacy_record.dvd_id,
            publication_provenance=legacy_proof,
            evidence=legacy_evidence,
        )
        require(
            second_backfilled.status == STATE_FAILED_RETRYABLE
            and second_backfilled.transition_sequence
            == backfilled.transition_sequence,
            "LEGACY_BACKFILL_IDEMPOTENT_NOOP",
        )
        with sqlite3.connect(
            root / "legacy-proof-backfill-valid" / "state.sqlite3"
        ) as connection:
            require(
                connection.execute(
                    "SELECT COUNT(*) FROM stage12_rollout_events"
                ).fetchone()[0]
                == legacy_event_count_before + 1,
                "LEGACY_BACKFILL_NO_DUPLICATE_EVENT",
            )
        reconciled_legacy = legacy_store.reconcile_published(
            legacy_record.dvd_id,
            evidence=legacy_evidence,
        )
        require(
            reconciled_legacy.status == STATE_PUBLISHED,
            "LEGACY_BACKFILL_RECONCILES_TO_PUBLISHED",
        )
        with sqlite3.connect(
            root / "legacy-proof-backfill-valid" / "state.sqlite3"
        ) as connection:
            legacy_reconciled_events = connection.execute(
                """
                SELECT reason
                FROM stage12_rollout_events
                WHERE dvd_id = ?
                ORDER BY event_id
                """,
                (legacy_record.dvd_id,),
            ).fetchall()
        require(
            sum(
                row[0] == PUBLICATION_PROOF_BACKFILLED
                for row in legacy_reconciled_events
            )
            == 1
            and sum(
                row[0] == "PUBLICATION_RECONCILED"
                for row in legacy_reconciled_events
            )
            == 1
            and sum(row[0] == "PUBLISH" for row in legacy_reconciled_events)
            == 0,
            "LEGACY_BACKFILL_NO_DUPLICATE_PUBLICATION_EVENT",
        )

        def rejected_backfill(
            fixture_root: Path,
            *,
            mutate_proof=None,
            mutate_evidence=None,
            publication_provenance=True,
            terminal=False,
        ):
            (
                rejected_store,
                rejected_record,
                _rejected_digest,
                _rejected_destination,
                rejected_evidence,
            ) = failed_reconciliation_fixture(
                fixture_root,
                publication_provenance=publication_provenance,
                terminal=terminal,
            )
            rejected_state = rejected_store.get(rejected_record.dvd_id)
            rejected_proof = publication_proof_for(rejected_state)
            if mutate_proof is not None:
                mutate_proof(rejected_proof)
            if mutate_evidence is not None:
                rejected_evidence = mutate_evidence(rejected_evidence)
            expect_raises(
                Stage12RolloutValidationError,
                lambda: rejected_store.record_verified_publication_proof(
                    rejected_record.dvd_id,
                    publication_provenance=rejected_proof,
                    evidence=rejected_evidence,
                ),
                fixture_root.name + "_FAIL_CLOSED",
            )
            require(
                rejected_store.get(rejected_record.dvd_id).status
                == (
                    STATE_FAILED_TERMINAL
                    if terminal
                    else STATE_FAILED_RETRYABLE
                ),
                fixture_root.name + "_STATE_PRESERVED",
            )

        rejected_backfill(
            root / "legacy-backfill-sha-mismatch",
            mutate_proof=lambda value: value.update(
                destination_sha256="0" * 64
            ),
            publication_provenance=False,
        )
        rejected_backfill(
            root / "legacy-backfill-destination-mismatch",
            mutate_proof=lambda value: value.update(
                destination_relative="OTHER/OTHER-001/OTHER-001.ko.srt"
            ),
            publication_provenance=False,
        )
        rejected_backfill(
            root / "legacy-backfill-artifact-mismatch",
            mutate_proof=lambda value: value.update(
                artifact_sha256="0" * 64
            ),
            publication_provenance=False,
        )
        rejected_backfill(
            root / "legacy-backfill-report-mismatch",
            mutate_proof=lambda value: value.update(
                report_sha256="0" * 64
            ),
            publication_provenance=False,
        )
        rejected_backfill(
            root / "legacy-backfill-item-mismatch",
            mutate_evidence=lambda value: replace(
                value,
                jellyfin_item_path="/media/adult/OTHER/OTHER-001/OTHER-001.mp4",
            ),
            publication_provenance=False,
        )
        rejected_backfill(
            root / "legacy-backfill-not-external",
            mutate_evidence=lambda value: replace(
                value,
                external_visible=False,
            ),
            publication_provenance=False,
        )
        rejected_backfill(
            root / "legacy-backfill-non-korean",
            mutate_evidence=lambda value: replace(
                value,
                subtitle_language="eng",
            ),
            publication_provenance=False,
        )
        rejected_backfill(
            root / "legacy-backfill-wrong-codec",
            mutate_evidence=lambda value: replace(
                value,
                subtitle_codec="webvtt",
            ),
            publication_provenance=False,
        )
        rejected_backfill(
            root / "legacy-backfill-missing-proof-field",
            mutate_proof=lambda value: value.pop("publication_performed"),
            publication_provenance=False,
        )
        rejected_backfill(
            root / "legacy-backfill-conflicting-proof",
            mutate_proof=lambda value: value.update(
                publication_event_identity="conflict"
            ),
            publication_provenance=True,
        )
        rejected_backfill(
            root / "legacy-backfill-terminal",
            publication_provenance=False,
            terminal=True,
        )

        def rejected_reconciliation(
            fixture_root: Path,
            *,
            mutate=None,
            publication_provenance=True,
            terminal=False,
        ):
            (
                rejected_store,
                rejected_record,
                rejected_digest,
                rejected_destination,
                rejected_evidence,
            ) = failed_reconciliation_fixture(
                fixture_root,
                publication_provenance=publication_provenance,
                terminal=terminal,
            )
            if mutate is not None:
                rejected_evidence = mutate(rejected_evidence)
            expect_raises(
                Stage12RolloutValidationError,
                lambda: rejected_store.reconcile_published(
                    rejected_record.dvd_id,
                    evidence=rejected_evidence,
                ),
                fixture_root.name + "_FAIL_CLOSED",
            )
            require(
                rejected_store.get(rejected_record.dvd_id).status
                == (STATE_FAILED_TERMINAL if terminal else STATE_FAILED_RETRYABLE),
                fixture_root.name + "_STATE_PRESERVED",
            )

        rejected_reconciliation(
            root / "reconciliation-sha-mismatch",
            mutate=lambda value: replace(
                value,
                destination_sha256="0" * 64,
            ),
        )
        rejected_reconciliation(
            root / "reconciliation-destination-mismatch",
            mutate=lambda value: replace(
                value,
                destination_relative="OTHER/OTHER-001/OTHER-001.ko.srt",
            ),
        )
        rejected_reconciliation(
            root / "reconciliation-item-mismatch",
            mutate=lambda value: replace(
                value,
                jellyfin_item_path="/media/adult/OTHER/OTHER-001/OTHER-001.mp4",
            ),
        )
        rejected_reconciliation(
            root / "reconciliation-not-external",
            mutate=lambda value: replace(
                value,
                external_visible=False,
            ),
        )
        rejected_reconciliation(
            root / "reconciliation-non-korean",
            mutate=lambda value: replace(
                value,
                subtitle_language="eng",
            ),
        )
        rejected_reconciliation(
            root / "reconciliation-wrong-codec",
            mutate=lambda value: replace(
                value,
                subtitle_codec="webvtt",
            ),
        )
        rejected_reconciliation(
            root / "reconciliation-unverified",
            mutate=lambda value: replace(
                value,
                verification_passed=False,
            ),
        )
        rejected_reconciliation(
            root / "reconciliation-missing-publication",
            publication_provenance=False,
        )
        rejected_reconciliation(
            root / "reconciliation-terminal",
            terminal=True,
        )

        pending_reconcile_store = Stage12RolloutStateStore(
            root / "reconciliation-pending.sqlite3"
        )
        pending_record = inventory_record("REC-002", holding_id=901)
        pending_reconcile_store.initialize_from_inventory(
            Stage12HoldingsInventoryReport((pending_record,))
        )
        expect_raises(
            Stage12InvalidTransitionError,
            lambda: pending_reconcile_store.reconcile_published(
                pending_record.dvd_id,
                evidence=reconcile_evidence,
            ),
            "RECONCILIATION_PENDING_REJECTED",
        )

        running_reconcile_store = Stage12RolloutStateStore(
            root / "reconciliation-running.sqlite3"
        )
        running_record = inventory_record("REC-003", holding_id=902)
        running_reconcile_store.initialize_from_inventory(
            Stage12HoldingsInventoryReport((running_record,))
        )
        running_reconcile_store.transition(
            running_record.dvd_id,
            STATE_RUNNING,
            reason="START_RECONCILIATION_RUNNING",
            provenance={"operation": "SMOKE"},
        )
        expect_raises(
            Stage12InvalidTransitionError,
            lambda: running_reconcile_store.reconcile_published(
                running_record.dvd_id,
                evidence=reconcile_evidence,
            ),
            "RECONCILIATION_RUNNING_REJECTED",
        )

        unresolved_reconcile_store = Stage12RolloutStateStore(
            root / "reconciliation-unresolved.sqlite3"
        )
        unresolved_record = inventory_record(
            "REC-004",
            holding_id=903,
            eligibility=UNRESOLVED,
            existing_ko=EXISTING_KO_UNRESOLVED,
            reason="SUBTITLE_INVENTORY_INVALID",
        )
        unresolved_reconcile_store.initialize_from_inventory(
            Stage12HoldingsInventoryReport((unresolved_record,))
        )
        expect_raises(
            Stage12InvalidTransitionError,
            lambda: unresolved_reconcile_store.reconcile_published(
                unresolved_record.dvd_id,
                evidence=reconcile_evidence,
            ),
            "RECONCILIATION_UNRESOLVED_REJECTED",
        )

        expect_raises(
            Stage12RolloutValidationError,
            lambda: reconcile_store.reconcile_published(
                reconcile_record.dvd_id,
                evidence=replace(
                    reconcile_evidence,
                    jellyfin_item_id="conflicting-item",
                ),
            ),
            "PUBLISHED_CONFLICTING_EVIDENCE_REJECTED",
        )
        require(
            reconcile_store.get(reconcile_record.dvd_id).status
            == STATE_PUBLISHED,
            "PUBLISHED_CONFLICT_DOES_NOT_MUTATE",
        )

        skipped = inventory_record(
            "BBB-001",
            holding_id=200,
            eligibility=SKIPPED_EXISTING_KO,
            existing_ko=EXISTING_KO_VALID,
            reason="CANONICAL_KO_SRT_VALID",
        )
        skipped_store = Stage12RolloutStateStore(root / "skipped.sqlite3")
        skipped_store.initialize_from_inventory(
            Stage12HoldingsInventoryReport((skipped,))
        )
        expect_raises(
            Stage12InvalidTransitionError,
            lambda: skipped_store.transition(
                skipped.dvd_id,
                STATE_RUNNING,
                reason="RERUN",
                provenance={"test": "skip"},
            ),
            "SKIPPED_EXISTING_KO_NOT_RERUN",
        )

        # I. Generic artifact-backed preflight and all fail-closed branches.
        canary = inventory_record("CAN-001", holding_id=300)
        valid_root = root / "valid-artifacts"
        valid_nas = FakeNAS(canary)
        write_valid_bundle(valid_root, canary)
        valid = select_publication_canary(
            Stage12HoldingsInventoryReport((canary,)),
            artifact_root=valid_root,
            nas_filesystem=valid_nas,
        )
        require(valid.publication_preflight == PUBLICATION_READY, "VALID_READY")
        require(valid.destination_exists is False, "DESTINATION_ABSENT_READY")
        require(
            valid_nas.calls
            == [
                canary.media_path_identity,
                valid.destination_ko_path,
            ],
            "EXACT_NAS_LSTAT_ONLY",
        )
        valid_again = select_publication_canary(
            Stage12HoldingsInventoryReport((canary,)),
            artifact_root=valid_root,
            nas_filesystem=FakeNAS(canary),
        )
        require(valid.to_dict() == valid_again.to_dict(), "DETERMINISTIC_PREFLIGHT")

        blocked_existing = preflight_fixture(
            root / "existing-artifacts",
            canary,
            destination_exists=True,
        )
        require(
            blocked_existing.publication_preflight
            == PUBLICATION_BLOCKED_EXISTING_KO,
            "EXISTING_DESTINATION_BLOCKED",
        )

        mismatch_root = root / "clean-mismatch"
        _, _, mismatch_report_path, mismatch_report = write_valid_bundle(
            mismatch_root,
            canary,
        )
        mismatch_report["clean_sha256"] = "0" * 64
        mismatch_report_path.write_bytes(_serialize_report(mismatch_report))
        mismatch = select_publication_canary(
            Stage12HoldingsInventoryReport((canary,)),
            artifact_root=mismatch_root,
            nas_filesystem=FakeNAS(canary),
        )
        require(
            mismatch.publication_preflight == PUBLICATION_BLOCKED_INVALID_ARTIFACT,
            "CLEAN_SHA_MISMATCH_BLOCKED",
        )

        report_mismatch_root = root / "report-mismatch"
        _, _, report_mismatch_path, report_mismatch = write_valid_bundle(
            report_mismatch_root,
            canary,
        )
        report_mismatch["title"] = "OTHER-001"
        report_mismatch_path.write_bytes(_serialize_report(report_mismatch))
        report_mismatch_result = select_publication_canary(
            Stage12HoldingsInventoryReport((canary,)),
            artifact_root=report_mismatch_root,
            nas_filesystem=FakeNAS(canary),
        )
        require(
            report_mismatch_result.publication_preflight
            == PUBLICATION_BLOCKED_INVALID_ARTIFACT,
            "REPORT_MISMATCH_BLOCKED",
        )

        drift = preflight_fixture(root / "drift-artifacts", canary, drift=True)
        require(
            drift.publication_preflight == PUBLICATION_BLOCKED_SOURCE_DRIFT,
            "SOURCE_DRIFT_BLOCKED",
        )

        incomplete_root = root / "incomplete-artifacts"
        incomplete_root.mkdir()
        title_root = incomplete_root / canary.dvd_id
        title_root.mkdir()
        (title_root / "clean-ko-v1.srt").write_bytes(b"partial")
        incomplete = select_publication_canary(
            Stage12HoldingsInventoryReport((canary,)),
            artifact_root=incomplete_root,
            nas_filesystem=FakeNAS(canary),
        )
        require(
            incomplete.publication_preflight
            == PUBLICATION_BLOCKED_INVALID_ARTIFACT,
            "INCOMPLETE_ARTIFACT_BLOCKED",
        )

        source = Path(__file__).with_name("teddy_discovery_stage12_rollout.py")
        source_text = source.read_text(encoding="utf-8")
        for forbidden in (
            "SubtitleSSHMutator",
            "publish_korean_srt",
            "os.walk",
            "rglob",
            "HSODA-104",
        ):
            require(forbidden not in source_text, "SAFE_GENERIC_SOURCE_" + forbidden)

    require(
        set(STATE_STATUSES)
        == {
            "PENDING",
            "RUNNING",
            "GENERATED",
            "PUBLISHED",
            "SKIPPED_EXISTING_KO",
            "UNRESOLVED",
            "FAILED_RETRYABLE",
            "FAILED_TERMINAL",
        },
        "STATE_STATUS_SET_EXACT",
    )
    print("STAGE12_ROLLOUT_SMOKE=PASS")


if __name__ == "__main__":
    main()
