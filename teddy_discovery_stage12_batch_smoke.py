"""Offline smoke coverage for the bounded Stage12 rollout owner."""

from __future__ import annotations

from pathlib import Path
import hashlib
import json
from types import SimpleNamespace
from tempfile import TemporaryDirectory

from teddy_discovery_stage11_controller import (
    ALIGNMENT_NOT_ATTEMPTED,
    EXTERNAL_JA_TRANSPORT_FAILURE,
    Stage11ControllerResult,
    V2_ROUTE_ASR_ONLY,
)
from teddy_discovery_stage12_batch import (
    Stage12BatchSelection,
    Stage12BatchRunner,
    Stage12BatchSystemicError,
    Stage12BatchTitleError,
    Stage12JellyfinRecognition,
    recognize_jellyfin_external_subtitle,
    select_pending_batch,
)
from teddy_discovery_stateful_live_runner import (
    StatefulSemanticOutputValidationRetryExhausted,
)
from teddy_discovery_stage12_inventory import (
    ELIGIBLE_NEEDS_KO,
    EXISTING_KO_ABSENT,
    EXISTING_KO_UNRESOLVED,
    Stage12HoldingInventoryRecord,
    Stage12HoldingsInventoryReport,
    UNRESOLVED,
)
from teddy_discovery_stage12_rollout import (
    STATE_FAILED_RETRYABLE,
    STATE_FAILED_TERMINAL,
    STATE_PENDING,
    STATE_PUBLISHED,
    STATE_UNRESOLVED,
    Stage12InvalidTransitionError,
    Stage12RolloutStateStore,
)
from teddy_discovery_stage12_rollout_smoke import write_valid_bundle
from teddy_discovery_subtitle import (
    derive_target_ko_relative,
    validate_canonical_holding,
)
from teddy_discovery_subtitle_publish import (
    SUBTITLE_PUBLISHED,
    SubtitlePublishCollisionError,
    SubtitlePublishResult,
)
from teddy_discovery_subtitle_text import parse_subtitle_bytes
from teddy_discovery_jellyfin import jellyfin_media_path


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


def video_for(record: Stage12HoldingInventoryRecord):
    return validate_canonical_holding(
        {
            "dvd_id": record.dvd_id,
            "storage_root": "jav",
            "relative_path": record.media_path_identity,
            "parse_status": "MATCHED",
            "present": 1,
        },
        record.dvd_id,
    )


class FakeNAS:
    """Exact-path fake that exposes only read/stat plus explicit test publish."""

    def __init__(self, records):
        self.records = {record.dvd_id: record for record in records}
        self.published: dict[str, bytes] = {}
        self.lstat_calls: list[str] = []

    def _by_path(self, relative_path):
        for record in self.records.values():
            if relative_path == record.media_path_identity:
                return record, "source"
            if relative_path == derive_target_ko_relative(video_for(record)):
                return record, "destination"
        raise AssertionError("unexpected NAS path: " + str(relative_path))

    def lstat(self, relative_path):
        self.lstat_calls.append(relative_path)
        record, kind = self._by_path(relative_path)
        if kind == "source":
            return SimpleNamespace(
                st_mode=0o100600,
                st_size=record.source_size_bytes,
                st_mtime_ns=record.source_mtime_ns,
            )
        if relative_path not in self.published:
            raise FileNotFoundError(relative_path)
        payload = self.published[relative_path]
        return SimpleNamespace(
            st_mode=0o100600,
            st_size=len(payload),
            st_mtime_ns=300,
        )


class FakeSubtitleReader:
    def __init__(self, nas: FakeNAS):
        self.nas = nas
        self.read_calls: list[tuple[str, str]] = []

    def read_subtitle_bytes(self, canonical_video, candidate):
        self.read_calls.append(
            (canonical_video.dvd_id, candidate.relative_path)
        )
        return self.nas.published[candidate.relative_path]


class FakePublisher:
    def __init__(self, nas: FakeNAS, *, collision_ids=(), fail_ids=()):
        self.nas = nas
        self.collision_ids = set(collision_ids)
        self.fail_ids = set(fail_ids)
        self.calls: list[str] = []

    def publish_korean_srt(self, *, canonical_video, artifact, target_relative):
        self.calls.append(canonical_video.dvd_id)
        if canonical_video.dvd_id in self.collision_ids:
            raise SubtitlePublishCollisionError("existing destination conflict")
        if canonical_video.dvd_id in self.fail_ids:
            raise OSError("offline publication failure")
        self.nas.published[target_relative] = artifact.payload
        return SubtitlePublishResult(
            state=SUBTITLE_PUBLISHED,
            target_relative=target_relative,
            sha256=artifact.sha256,
            byte_size=artifact.byte_size,
        )


def recognition_for(_dvd_id, video, destination):
    return Stage12JellyfinRecognition(
        item_id="item-" + video.dvd_id,
        item_path=jellyfin_media_path(video.relative_path),
        subtitle_path=jellyfin_media_path(destination),
        subtitle_language="kor",
        external_visible=True,
        refresh_required=False,
        refresh_method="NONE_ALREADY_VISIBLE",
    )


def controller_for(
    root: Path,
    records,
    calls,
    *,
    fail_ids=(),
    systemic_ids=(),
    validation_retry_exhausted_ids=(),
    unexpected_ids=(),
):
    bundles = {}
    for record in records:
        bundles[record.dvd_id] = write_valid_bundle(root, record)

    def run(dvd_id):
        calls.append(dvd_id)
        if dvd_id in systemic_ids:
            raise Stage12BatchSystemicError("shared contract failure")
        if dvd_id in unexpected_ids:
            raise RuntimeError("unexpected programmer failure")
        if dvd_id in validation_retry_exhausted_ids:
            raise StatefulSemanticOutputValidationRetryExhausted(
                part_index=2,
                attempts=2,
                max_attempts=2,
            )
        if dvd_id in fail_ids:
            raise Stage12BatchTitleError("title execution failure")
        _, clean_path, report_path, report = bundles[dvd_id]
        return Stage11ControllerResult(
            title=dvd_id,
            route=V2_ROUTE_ASR_ONLY,
            clean_path=clean_path,
            clean_sha256=report["clean_sha256"],
            report_path=report_path,
            report_sha256=hashlib.sha256(report_path.read_bytes()).hexdigest(),
            baseline_reused=True,
            targeted_reused=None,
            clean_reused=False,
            report_reused=False,
            external_ja_outcome=EXTERNAL_JA_TRANSPORT_FAILURE,
            alignment_outcome=ALIGNMENT_NOT_ATTEMPTED,
        )

    return run


def make_runner(root, records, store, *, controller_calls, nas, publisher,
                fail_ids=(), systemic_ids=(),
                validation_retry_exhausted_ids=(), unexpected_ids=(),
                jellyfin=recognition_for):
    return Stage12BatchRunner(
        store=store,
        inventory=Stage12HoldingsInventoryReport(tuple(records)),
        artifact_root=root,
        nas_filesystem=nas,
        subtitle_reader=FakeSubtitleReader(nas),
        publisher=publisher,
        controller_runner=controller_for(
            root,
            records,
            controller_calls,
            fail_ids=fail_ids,
            systemic_ids=systemic_ids,
            validation_retry_exhausted_ids=validation_retry_exhausted_ids,
            unexpected_ids=unexpected_ids,
        ),
        jellyfin_recognizer=jellyfin,
    )


class FakeJellyfinClient:
    def __init__(self, item_path, subtitle_path, *, already_visible=False):
        self.item_path = item_path
        self.subtitle_path = subtitle_path
        self.already_visible = already_visible
        self.calls: list[tuple[str, str]] = []
        self.playback_calls = 0

    def _request(self, method, path):
        self.calls.append((method, path))
        if path.startswith("/Items?"):
            return {"Items": [{"Id": "exact-item", "Path": self.item_path}]}
        if path == "/Items/exact-item/PlaybackInfo":
            self.playback_calls += 1
            visible = self.already_visible or self.playback_calls >= 2
            streams = []
            if visible:
                streams.append(
                    {
                        "Type": "Subtitle",
                        "IsTextSubtitleStream": True,
                        "IsExternal": True,
                        "Language": "kor",
                        "Path": self.subtitle_path,
                    }
                )
            return {
                "MediaSources": [
                    {"Path": self.item_path, "MediaStreams": streams}
                ]
            }
        if path.startswith("/Items/exact-item/Refresh?"):
            return None
        raise AssertionError("unexpected Jellyfin call: " + method + " " + path)


def smoke_jellyfin_exact_refresh():
    item_path = "/media/adult/AAA/AAA-001/AAA-001.mp4"
    subtitle_path = "/media/adult/AAA/AAA-001/AAA-001.ko.srt"
    client = FakeJellyfinClient(item_path, subtitle_path)
    result = recognize_jellyfin_external_subtitle(
        client,
        video_relative="AAA/AAA-001/AAA-001.mp4",
        subtitle_relative="AAA/AAA-001/AAA-001.ko.srt",
        poll_interval_seconds=0,
        max_attempts=2,
    )
    require(result.external_visible is True, "JELLYFIN_REFRESH_RECOGNIZED")
    require(result.refresh_required is True, "JELLYFIN_REFRESH_REQUIRED")
    require(
        sum(path.startswith("/Items/exact-item/Refresh?") for _, path in client.calls)
        == 1,
        "JELLYFIN_ITEM_REFRESH_ONCE",
    )

    already = FakeJellyfinClient(
        item_path,
        subtitle_path,
        already_visible=True,
    )
    result = recognize_jellyfin_external_subtitle(
        already,
        video_relative="AAA/AAA-001/AAA-001.mp4",
        subtitle_relative="AAA/AAA-001/AAA-001.ko.srt",
        poll_interval_seconds=0,
        max_attempts=1,
    )
    require(result.refresh_required is False, "JELLYFIN_NO_REFRESH_VISIBLE")
    require(
        not any(path.startswith("/Items/exact-item/Refresh?") for _, path in already.calls),
        "JELLYFIN_ALREADY_VISIBLE_NO_REFRESH",
    )


def main():
    smoke_jellyfin_exact_refresh()

    records = (
        inventory_record("AAA-001", holding_id=1),
        inventory_record("AAA-002", holding_id=2),
        inventory_record("AAA-003", holding_id=3),
        inventory_record("AAA-004", holding_id=4),
        inventory_record(
            "ZZZ-999",
            holding_id=5,
            eligibility=UNRESOLVED,
            existing_ko=EXISTING_KO_UNRESOLVED,
            reason="SUBTITLE_INVENTORY_INVALID",
        ),
    )
    report = Stage12HoldingsInventoryReport(records)

    with TemporaryDirectory(prefix="stage12-batch-smoke-") as temp:
        root = Path(temp) / "artifacts"
        root.mkdir()
        store = Stage12RolloutStateStore(Path(temp) / "state.sqlite3")
        store.initialize_from_inventory(report)

        selection = select_pending_batch(store, batch_size=3)
        require(
            selection.dvd_ids == ("AAA-001", "AAA-002", "AAA-003"),
            "SELECTOR_EXACT_LIMIT_AND_ORDER",
        )
        expect_raises(
            Stage12BatchSystemicError,
            lambda: Stage12BatchSelection(
                batch_size=4,
                dvd_ids=selection.dvd_ids,
            ),
            "BATCH_BOUND_REJECTED",
        )

        nas = FakeNAS(records)
        publisher = FakePublisher(nas)
        controller_calls: list[str] = []
        runner = make_runner(
            root,
            records[:4],
            store,
            controller_calls=controller_calls,
            nas=nas,
            publisher=publisher,
        )
        result = runner.run(selection)
        require(
            result.summary()["published"] == 3
            and controller_calls == list(selection.dvd_ids)
            and publisher.calls == list(selection.dvd_ids),
            "SUCCESSFUL_SERIAL_FULL_PATH",
        )
        require(
            all(store.get(dvd_id).status == STATE_PUBLISHED for dvd_id in selection.dvd_ids),
            "SUCCESSFUL_STATE_PUBLISHED",
        )
        next_selection = select_pending_batch(store, batch_size=1)
        require(next_selection.dvd_ids == ("AAA-004",), "RERUN_SKIPS_COMPLETED")
        require(
            store.status_counts()[STATE_PUBLISHED] == 3,
            "NO_DUPLICATE_PUBLISHED_STATE",
        )

        # A title error is isolated and the next selected title still runs.
        isolated_root = Path(temp) / "isolated-artifacts"
        isolated_root.mkdir()
        isolated_store = Stage12RolloutStateStore(Path(temp) / "isolated.sqlite3")
        isolated_report = Stage12HoldingsInventoryReport(records[:3])
        isolated_store.initialize_from_inventory(isolated_report)
        isolated_nas = FakeNAS(records[:3])
        isolated_publisher = FakePublisher(isolated_nas)
        isolated_calls: list[str] = []
        isolated_runner = make_runner(
            isolated_root,
            records[:3],
            isolated_store,
            controller_calls=isolated_calls,
            nas=isolated_nas,
            publisher=isolated_publisher,
            fail_ids={"AAA-002"},
        )
        isolated_result = isolated_runner.run(
            Stage12BatchSelection(3, ("AAA-001", "AAA-002", "AAA-003"))
        )
        require(
            isolated_calls == ["AAA-001", "AAA-002", "AAA-003"]
            and isolated_result.titles[1].final_state == STATE_FAILED_RETRYABLE
            and isolated_result.titles[0].final_state == STATE_PUBLISHED
            and isolated_result.titles[2].final_state == STATE_PUBLISHED,
            "TITLE_FAILURE_ISOLATION",
        )

        # Bounded semantic-output retry exhaustion is a title-level retryable
        # result, and the next immutable selection member still runs.
        retry_root = Path(temp) / "semantic-retry-artifacts"
        retry_root.mkdir()
        retry_store = Stage12RolloutStateStore(Path(temp) / "semantic-retry.sqlite3")
        retry_store.initialize_from_inventory(
            Stage12HoldingsInventoryReport(records[:3])
        )
        retry_nas = FakeNAS(records[:3])
        retry_publisher = FakePublisher(retry_nas)
        retry_calls: list[str] = []
        retry_runner = make_runner(
            retry_root,
            records[:3],
            retry_store,
            controller_calls=retry_calls,
            nas=retry_nas,
            publisher=retry_publisher,
            validation_retry_exhausted_ids={"AAA-002"},
        )
        retry_result = retry_runner.run(
            Stage12BatchSelection(3, ("AAA-001", "AAA-002", "AAA-003"))
        )
        retry_state = retry_store.get("AAA-002")
        retry_provenance = json.loads(
            retry_state.last_transition_provenance_json
        )
        require(
            retry_calls == ["AAA-001", "AAA-002", "AAA-003"]
            and retry_result.titles[1].final_state == STATE_FAILED_RETRYABLE
            and retry_state.last_transition_reason
            == "STAGE12_SEMANTIC_OUTPUT_VALIDATION_RETRY_EXHAUSTED"
            and retry_provenance["retry_performed"] is True
            and retry_provenance["semantic_output_validation_retry"]
            == {"attempts": 2, "max_attempts": 2, "part_index": 2}
            and retry_result.titles[0].final_state == STATE_PUBLISHED
            and retry_result.titles[2].final_state == STATE_PUBLISHED,
            "SEMANTIC_RETRY_EXHAUSTION_TITLE_ISOLATION",
        )

        # An unrelated programmer exception remains systemic and stops the
        # immutable serial batch.
        unexpected_root = Path(temp) / "unexpected-artifacts"
        unexpected_root.mkdir()
        unexpected_store = Stage12RolloutStateStore(
            Path(temp) / "unexpected.sqlite3"
        )
        unexpected_store.initialize_from_inventory(
            Stage12HoldingsInventoryReport(records[:3])
        )
        unexpected_nas = FakeNAS(records[:3])
        unexpected_publisher = FakePublisher(unexpected_nas)
        unexpected_calls: list[str] = []
        unexpected_runner = make_runner(
            unexpected_root,
            records[:3],
            unexpected_store,
            controller_calls=unexpected_calls,
            nas=unexpected_nas,
            publisher=unexpected_publisher,
            unexpected_ids={"AAA-002"},
        )
        expect_raises(
            Stage12BatchSystemicError,
            lambda: unexpected_runner.run(
                Stage12BatchSelection(3, ("AAA-001", "AAA-002", "AAA-003"))
            ),
            "UNEXPECTED_PROGRAMMER_ERROR_REMAINS_SYSTEMIC",
        )
        require(
            unexpected_calls == ["AAA-001", "AAA-002"]
            and unexpected_store.get("AAA-002").status == "RUNNING"
            and unexpected_store.get("AAA-003").status == STATE_PENDING,
            "UNEXPECTED_ERROR_DOES_NOT_CONTINUE_BATCH",
        )

        # A systemic error stops the immutable serial batch immediately.
        systemic_root = Path(temp) / "systemic-artifacts"
        systemic_root.mkdir()
        systemic_store = Stage12RolloutStateStore(Path(temp) / "systemic.sqlite3")
        systemic_store.initialize_from_inventory(
            Stage12HoldingsInventoryReport(records[:3])
        )
        systemic_nas = FakeNAS(records[:3])
        systemic_publisher = FakePublisher(systemic_nas)
        systemic_calls: list[str] = []
        systemic_runner = make_runner(
            systemic_root,
            records[:3],
            systemic_store,
            controller_calls=systemic_calls,
            nas=systemic_nas,
            publisher=systemic_publisher,
            systemic_ids={"AAA-002"},
        )
        expect_raises(
            Stage12BatchSystemicError,
            lambda: systemic_runner.run(
                Stage12BatchSelection(3, ("AAA-001", "AAA-002", "AAA-003"))
            ),
            "SYSTEMIC_FAILURE_STOPS_BATCH",
        )
        require(
            systemic_calls == ["AAA-001", "AAA-002"]
            and systemic_store.get("AAA-002").status == "RUNNING"
            and systemic_store.get("AAA-003").status == STATE_PENDING,
            "SYSTEMIC_FAILURE_NOT_SILENTLY_CONTINUED",
        )

        # Existing destination and publication failure never become PUBLISHED.
        conflict_root = Path(temp) / "conflict-artifacts"
        conflict_root.mkdir()
        conflict_store = Stage12RolloutStateStore(Path(temp) / "conflict.sqlite3")
        conflict_record = records[0]
        conflict_store.initialize_from_inventory(
            Stage12HoldingsInventoryReport((conflict_record,))
        )
        conflict_nas = FakeNAS((conflict_record,))
        conflict_nas.published[derive_target_ko_relative(video_for(conflict_record))] = b"old"
        conflict_publisher = FakePublisher(conflict_nas)
        conflict_calls: list[str] = []
        conflict_runner = make_runner(
            conflict_root,
            (conflict_record,),
            conflict_store,
            controller_calls=conflict_calls,
            nas=conflict_nas,
            publisher=conflict_publisher,
        )
        conflict_result = conflict_runner.run(
            Stage12BatchSelection(1, (conflict_record.dvd_id,))
        )
        require(
            conflict_result.titles[0].final_state == STATE_UNRESOLVED
            and conflict_calls == []
            and conflict_publisher.calls == [],
            "EXISTING_DESTINATION_NO_OVERWRITE",
        )

        publish_fail_root = Path(temp) / "publish-fail-artifacts"
        publish_fail_root.mkdir()
        publish_fail_store = Stage12RolloutStateStore(
            Path(temp) / "publish-fail.sqlite3"
        )
        publish_fail_store.initialize_from_inventory(
            Stage12HoldingsInventoryReport((conflict_record,))
        )
        publish_fail_nas = FakeNAS((conflict_record,))
        publish_fail_publisher = FakePublisher(
            publish_fail_nas,
            fail_ids={conflict_record.dvd_id},
        )
        publish_fail_calls: list[str] = []
        publish_fail_runner = make_runner(
            publish_fail_root,
            (conflict_record,),
            publish_fail_store,
            controller_calls=publish_fail_calls,
            nas=publish_fail_nas,
            publisher=publish_fail_publisher,
        )
        publish_fail_result = publish_fail_runner.run(
            Stage12BatchSelection(1, (conflict_record.dvd_id,))
        )
        require(
            publish_fail_result.titles[0].final_state == STATE_FAILED_RETRYABLE
            and publish_fail_store.get(conflict_record.dvd_id).status
            != STATE_PUBLISHED
            and publish_fail_nas.published == {},
            "PUBLICATION_FAILURE_NOT_PUBLISHED",
        )

        # Jellyfin recognition is a title-level result after publication.
        jellyfin_root = Path(temp) / "jellyfin-fail-artifacts"
        jellyfin_root.mkdir()
        jellyfin_store = Stage12RolloutStateStore(Path(temp) / "jellyfin.sqlite3")
        jellyfin_store.initialize_from_inventory(
            Stage12HoldingsInventoryReport((conflict_record,))
        )
        jellyfin_nas = FakeNAS((conflict_record,))
        jellyfin_publisher = FakePublisher(jellyfin_nas)
        jellyfin_calls: list[str] = []

        def jellyfin_fail(_dvd_id, _video, _destination):
            raise Stage12BatchTitleError("external subtitle not visible")

        jellyfin_runner = make_runner(
            jellyfin_root,
            (conflict_record,),
            jellyfin_store,
            controller_calls=jellyfin_calls,
            nas=jellyfin_nas,
            publisher=jellyfin_publisher,
            jellyfin=jellyfin_fail,
        )
        jellyfin_result = jellyfin_runner.run(
            Stage12BatchSelection(1, (conflict_record.dvd_id,))
        )
        jellyfin_failure_state = jellyfin_store.get(
            conflict_record.dvd_id
        )
        jellyfin_failure_provenance = json.loads(
            jellyfin_failure_state.last_transition_provenance_json
        )
        require(
            jellyfin_result.titles[0].jellyfin_recognition == "FAIL"
            and jellyfin_failure_state.status == STATE_FAILED_RETRYABLE
            and jellyfin_failure_provenance[
                "publication_provenance"
            ]["publication_performed"] is True
            and jellyfin_failure_provenance[
                "publication_provenance"
            ]["destination_sha256"]
            == jellyfin_failure_state.artifact_sha256,
            "JELLYFIN_FAILURE_RECORDED",
        )

        expect_raises(
            Stage12InvalidTransitionError,
            lambda: store.transition(
                "AAA-001",
                STATE_PENDING,
                reason="UNSAFE_RERUN",
                provenance={"test": True},
            ),
            "PUBLISHED_RERUN_REJECTED",
        )

    print("STAGE12_BATCH_SMOKE=PASS")


if __name__ == "__main__":
    main()
