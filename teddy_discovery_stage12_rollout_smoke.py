"""Offline smoke coverage for the Stage12 rollout state and preflight owner."""

from __future__ import annotations

from pathlib import Path
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
    PUBLICATION_READY,
    STATE_GENERATED,
    STATE_PENDING,
    STATE_PUBLISHED,
    STATE_RUNNING,
    STATE_SKIPPED_EXISTING_KO,
    STATE_STATUSES,
    STATE_UNRESOLVED,
    Stage12InvalidTransitionError,
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
