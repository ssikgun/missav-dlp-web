"""Offline safety smoke for the explicit one-title Stage12 retry path."""

from __future__ import annotations

from contextlib import redirect_stdout
import io
import inspect
import os
from pathlib import Path
import stat
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from teddy_discovery_stage12_batch import (
    Stage12BatchRunner,
    Stage12BatchSelection,
    Stage12BatchSystemicError,
    Stage12BatchTitleError,
    Stage12ExplicitRetryAuthorization,
)
from teddy_discovery_stage12_batch_smoke import (
    FakeNAS,
    FakePublisher,
    controller_for,
    inventory_record,
    recognition_for,
)
from teddy_discovery_stage12_inventory import (
    ELIGIBLE_NEEDS_KO,
    EXISTING_KO_ABSENT,
    Stage12HoldingsInventoryReport,
    UNRESOLVED,
    EXISTING_KO_UNRESOLVED,
)
from teddy_discovery_stage12_rollout import (
    STATE_FAILED_RETRYABLE,
    STATE_PENDING,
    STATE_PUBLISHED,
    STATE_RUNNING,
    STAGE12_EXPLICIT_RETRY_START,
    STAGE12_EXPLICIT_RETRY_CRASH_RECOVERY,
    Stage12InvalidTransitionError,
    Stage12RolloutIdentityError,
    Stage12RolloutStateStore,
)
from teddy_discovery_stage12_rollout_smoke import write_valid_bundle
from teddy_discovery_stage12_reconcile_smoke import failed_reconciliation_fixture
from teddy_discovery_stage12_bulk_runner import (
    EXPLICIT_RETRY_AUTH_ENV,
    EXPLICIT_RETRY_AUTH_VALUE,
    EXPLICIT_RETRY_RECOVERY_AUTH_ENV,
    EXPLICIT_RETRY_RECOVERY_AUTH_VALUE,
    AUTH_ENV,
    AUTH_VALUE,
    PRODUCTION_STAGE11_PREFIX,
    PRODUCTION_STAGE11_PYTHON,
    Stage12BulkRunnerError,
    contract_check,
    main,
    require_production_interpreter,
    run_explicit_retry_recovery,
    run_preflight,
    run_live,
)
from teddy_discovery_subtitle import derive_target_ko_relative
from teddy_discovery_stage12_batch_smoke import video_for


def require(condition: bool, marker: str):
    if not condition:
        raise AssertionError(marker)


def expect_raises(exception_type, callback, marker: str):
    try:
        callback()
    except exception_type:
        return
    raise AssertionError(marker)


def failed_fixture(root: Path, dvd_id="TRY-001"):
    record = inventory_record(dvd_id, holding_id=1)
    other = inventory_record("OTH-002", holding_id=2)
    store = Stage12RolloutStateStore(root / "state.sqlite3")
    store.initialize_from_inventory(Stage12HoldingsInventoryReport((record, other)))
    store.transition(
        dvd_id,
        STATE_RUNNING,
        reason="STAGE12_BATCH_START",
        provenance={"operation": "STAGE12_SERIAL_BATCH", "retry_performed": False},
    )
    state = store.transition(
        dvd_id,
        STATE_FAILED_RETRYABLE,
        expected_from=STATE_RUNNING,
        reason="STAGE12_TITLE_FAILURE",
        provenance={
            "operation": "STAGE12_SERIAL_BATCH",
            "error_type": "ASRAudioValidationError",
            "retry_performed": False,
            "destination": derive_target_ko_relative(video_for(record)),
        },
        destination_relative=derive_target_ko_relative(video_for(record)),
    )
    return store, record, other, state


def check_identity(store, record, sequence):
    return store.validate_explicit_retry(
        record.dvd_id,
        expected_sequence=sequence,
        media_path_identity=record.media_path_identity,
        holding_identity=record.holding_identity,
        source_size_bytes=record.source_size_bytes,
        source_mtime_ns=record.source_mtime_ns,
    )


def stranded_retry_fixture(root: Path, dvd_id="TRY-901"):
    store, record, other, failed = failed_fixture(root, dvd_id)
    stranded = store.transition(
        dvd_id,
        STATE_RUNNING,
        expected_from=STATE_FAILED_RETRYABLE,
        expected_sequence=failed.transition_sequence,
        reason=STAGE12_EXPLICIT_RETRY_START,
        provenance={
            "operation": "STAGE12_EXPLICIT_RETRY",
            "retry_performed": True,
        },
    )
    return store, record, other, stranded


def build_runner(root, store, record, *, fail=False):
    artifact_root = root / "artifacts"
    artifact_root.mkdir(exist_ok=True)
    nas = FakeNAS((record,))
    publisher = FakePublisher(nas)
    calls = []
    controller = (
        _failing_controller(calls)
        if fail
        else controller_for(artifact_root, (record,), calls)
    )
    from teddy_discovery_stage12_batch_smoke import FakeSubtitleReader

    runner = Stage12BatchRunner(
        store=store,
        inventory=Stage12HoldingsInventoryReport((record,)),
        artifact_root=artifact_root,
        nas_filesystem=nas,
        subtitle_reader=FakeSubtitleReader(nas),
        publisher=publisher,
        controller_runner=controller,
        jellyfin_recognizer=recognition_for,
        retry_authorization=Stage12ExplicitRetryAuthorization(
            record.dvd_id,
            store.get(record.dvd_id).transition_sequence,
        ),
    )
    return runner, nas, publisher, calls


def _failing_controller(calls):
    def run(dvd_id):
        calls.append(dvd_id)
        raise Stage12BatchTitleError("synthetic retry failure")

    return run


def _systemic_controller(calls):
    def run(dvd_id):
        calls.append(dvd_id)
        raise RuntimeError("synthetic shared adapter failure")

    return run


def main_smoke():
    contract_check()
    import teddy_discovery_stage12_bulk_runner as bulk_runner

    require_production_interpreter(
        executable=str(PRODUCTION_STAGE11_PYTHON),
        prefix=str(PRODUCTION_STAGE11_PREFIX),
        importer=lambda name: object(),
    )
    expect_raises(
        Stage12BulkRunnerError,
        lambda: require_production_interpreter(
            executable="/usr/bin/python3",
            prefix="/usr",
            importer=lambda name: object(),
        ),
        "SYSTEM_PYTHON_REJECTED",
    )

    def missing_audio_dependency(name):
        if name == "numpy":
            raise ModuleNotFoundError(name)
        return object()

    expect_raises(
        Stage12BulkRunnerError,
        lambda: require_production_interpreter(
            executable=str(PRODUCTION_STAGE11_PYTHON),
            prefix=str(PRODUCTION_STAGE11_PREFIX),
            importer=missing_audio_dependency,
        ),
        "MISSING_AUDIO_DEPENDENCY_REJECTED",
    )

    with TemporaryDirectory(prefix="stage12-interpreter-preflight-smoke-") as raw:
        root = Path(raw)
        state_store, record, other, failed = failed_fixture(root)
        before = state_store.list_states()
        with (
            patch.object(sys, "executable", "/usr/bin/python3"),
            patch.object(sys, "prefix", "/usr"),
            patch.dict(os.environ, {AUTH_ENV: AUTH_VALUE}),
        ):
            expect_raises(
                Stage12BulkRunnerError,
                lambda: run_preflight(
                    expected_head="0" * 40,
                    batch_size=1,
                ),
                "PENDING_PREFLIGHT_REJECTS_WRONG_INTERPRETER",
            )
            with patch.dict(
                os.environ,
                {EXPLICIT_RETRY_AUTH_ENV: EXPLICIT_RETRY_AUTH_VALUE},
            ):
                expect_raises(
                    Stage12BulkRunnerError,
                    lambda: run_live(
                        expected_head="0" * 40,
                        batch_size=1,
                        max_titles=1,
                        retry_dvd_id=record.dvd_id,
                        retry_expected_sequence=failed.transition_sequence,
                    ),
                    "EXPLICIT_RETRY_PREFLIGHT_REJECTS_WRONG_INTERPRETER",
                )
        require(state_store.list_states() == before,
                "INTERPRETER_PREFLIGHT_FAILURE_PRESERVES_ROLLOUT_STATE")

    # This smoke is run by the Stage11 venv in validation; confirm its real
    # interpreter and installed audio dependencies as well as the injectable
    # guard behavior above.
    require_production_interpreter()

    from teddy_discovery_stage12_batch import (
        _jellyfin_external_subtitle_probe,
    )

    original_getsource = inspect.getsource

    def without_playback_probe_contract(value):
        source = original_getsource(value)
        if value is _jellyfin_external_subtitle_probe:
            return source.replace(
                '"/Items/" + item_id + "/PlaybackInfo"',
                '"/Items/" + item_id + "/PlaybackInfo_REMOVED"',
            )
        return source

    with patch(
        "teddy_discovery_stage12_bulk_runner.inspect.getsource",
        side_effect=without_playback_probe_contract,
    ):
        expect_raises(
            Stage12BulkRunnerError,
            contract_check,
            "JELLYFIN_RECOGNITION_CONTRACT_MUTATION_REJECTED",
        )

    with TemporaryDirectory(prefix="stage12-retry-smoke-") as raw:
        root = Path(raw)
        store, record, other, failed = failed_fixture(root)
        before_other = store.get(other.dvd_id)
        require(check_identity(store, record, failed.transition_sequence) == failed,
                "EXPLICIT_FAILED_RETRYABLE_PREFLIGHT_PASS")
        expect_raises(
            Stage12InvalidTransitionError,
            lambda: check_identity(store, record, failed.transition_sequence - 1),
            "EXPECTED_SEQUENCE_MISMATCH_REJECTED",
        )
        before_sequence_race = store.get(record.dvd_id)
        expect_raises(
            Stage12InvalidTransitionError,
            lambda: store.transition(
                record.dvd_id,
                STATE_RUNNING,
                expected_from=STATE_FAILED_RETRYABLE,
                expected_sequence=failed.transition_sequence - 1,
                reason="STAGE12_EXPLICIT_RETRY_START",
                provenance={"operation": "STAGE12_EXPLICIT_RETRY"},
            ),
            "TRANSITION_SEQUENCE_CAS_REJECTED",
        )
        require(store.get(record.dvd_id) == before_sequence_race,
                "SEQUENCE_RACE_STATE_UNCHANGED")
        expect_raises(
            Stage12RolloutIdentityError,
            lambda: store.validate_explicit_retry(
                record.dvd_id,
                expected_sequence=failed.transition_sequence,
                media_path_identity=record.media_path_identity,
                holding_identity=record.holding_identity,
                source_size_bytes=record.source_size_bytes + 1,
                source_mtime_ns=record.source_mtime_ns,
            ),
            "FINGERPRINT_DRIFT_REJECTED",
        )
        # Status guards cover ordinary pending/unresolved and completed states.
        expect_raises(
            Stage12InvalidTransitionError,
            lambda: check_identity(store, other, store.get(other.dvd_id).transition_sequence),
            "PENDING_TARGET_REJECTED",
        )
        unresolved = inventory_record(
            "ZZZ-003", holding_id=3, eligibility=UNRESOLVED,
            existing_ko=EXISTING_KO_UNRESOLVED,
        )
        store.initialize_from_inventory(Stage12HoldingsInventoryReport((unresolved,)))
        expect_raises(
            Stage12InvalidTransitionError,
            lambda: store.validate_explicit_retry(
                unresolved.dvd_id,
                expected_sequence=store.get(unresolved.dvd_id).transition_sequence,
                media_path_identity=unresolved.media_path_identity,
                holding_identity=unresolved.holding_identity,
                source_size_bytes=unresolved.source_size_bytes,
                source_mtime_ns=unresolved.source_mtime_ns,
            ),
            "UNRESOLVED_TARGET_REJECTED",
        )

        conflict_store, conflict_record, *_ = failed_reconciliation_fixture(
            root / "publication-conflict"
        )
        conflict_state = conflict_store.get(conflict_record.dvd_id)
        expect_raises(
            Stage12RolloutIdentityError,
            lambda: check_identity(
                conflict_store,
                conflict_record,
                conflict_state.transition_sequence,
            ),
            "RECORDED_ARTIFACT_PUBLICATION_CONFLICT_REJECTED",
        )

        # Missing auth returns before preflight, NAS, or state mutation.
        before_target = store.get(record.dvd_id)
        with patch.dict(os.environ, {}, clear=True):
            code = run_live(
                expected_head="0" * 40,
                batch_size=1,
                max_titles=1,
                retry_dvd_id=record.dvd_id,
                retry_expected_sequence=failed.transition_sequence,
            )
        require(code == 2 and store.get(record.dvd_id) == before_target,
                "EXPLICIT_AUTHORIZATION_REQUIRED")

        # Duplicate selector and missing selector are rejected before live I/O.
        for argv, marker in (
            (["runner", "--mode", "retry", "--expected-head", "0" * 40,
              "--expected-sequence", str(failed.transition_sequence)],
             "NO_DVD_ID_REJECTED"),
            (["runner", "--mode", "retry", "--expected-head", "0" * 40,
              "--expected-sequence", str(failed.transition_sequence),
              "--dvd-id", record.dvd_id, "--dvd-id", other.dvd_id],
             "MULTIPLE_DVD_IDS_REJECTED"),
        ):
            with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
                require(main() == 2, marker)

        recovery_argv_base = [
            "runner",
            "--mode",
            "recover-retry",
            "--expected-head",
            "0" * 40,
            "--expected-sequence",
            str(failed.transition_sequence),
            "--batch-size",
            "1",
            "--max-titles",
            "1",
        ]
        for argv, marker in (
            (recovery_argv_base, "RECOVERY_DVD_ID_REQUIRED"),
            (
                recovery_argv_base
                + ["--dvd-id", record.dvd_id, "--dvd-id", other.dvd_id],
                "RECOVERY_MULTIPLE_TITLES_REJECTED",
            ),
        ):
            with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
                require(main() == 2, marker)

        # The shared Stage12 runner consumes exactly one retry authorization.
        runner, nas, publisher, calls = build_runner(root, store, record, fail=True)
        expect_raises(
            Stage12BatchSystemicError,
            lambda: runner.run(Stage12BatchSelection(2, (record.dvd_id, other.dvd_id))),
            "MULTI_TITLE_SELECTION_REJECTED",
        )
        pre_retry_states = store.list_states()
        failure_result = runner.run(Stage12BatchSelection(1, (record.dvd_id,)))
        require(failure_result.titles[0].final_state == STATE_FAILED_RETRYABLE,
                "RETRY_FAILURE_REISOLATED")
        require(calls == [record.dvd_id], "STAGE11_FAILURE_PATH_CALLED_ONCE")
        require(store.get(other.dvd_id) == before_other,
                "OTHER_TITLE_STATE_UNCHANGED_ON_FAILURE")
        event = store.get(record.dvd_id)
        require(event.transition_sequence == failed.transition_sequence + 2,
                "RETRY_START_AND_FAILURE_EVENTS_RECORDED")

    with TemporaryDirectory(prefix="stage12-retry-systemic-smoke-") as raw:
        root = Path(raw)
        store, record, other, failed = failed_fixture(root, "TRY-002")
        other_before = store.get(other.dvd_id)
        runner, nas, publisher, calls = build_runner(
            root, store, record, fail=True
        )
        runner.controller_runner = _systemic_controller(calls)
        try:
            runner.run(Stage12BatchSelection(1, (record.dvd_id,)))
        except Stage12BatchSystemicError as error:
            require(
                "RuntimeError @" in str(error)
                and "synthetic shared adapter failure" not in str(error),
                "EXPLICIT_RETRY_ORIGINAL_EXCEPTION_DIAGNOSTIC",
            )
            require(
                isinstance(error.__cause__, RuntimeError),
                "EXPLICIT_RETRY_SYSTEMIC_CAUSE_RETAINED",
            )
            require(
                str(error.__cause__) == "synthetic shared adapter failure",
                "EXPLICIT_RETRY_SYSTEMIC_ORIGINAL_CONTEXT_RETAINED",
            )
        else:
            raise AssertionError("EXPLICIT_RETRY_SYSTEMIC_REMAINS_SYSTEMIC")
        current = store.get(record.dvd_id)
        require(
            current.status == STATE_RUNNING
            and current.transition_sequence == failed.transition_sequence + 1
            and current.last_transition_reason == "STAGE12_EXPLICIT_RETRY_START",
            "EXPLICIT_RETRY_SYSTEMIC_DOES_NOT_DOWNGRADE_OR_FAKE_FAILURE",
        )
        require(
            store.get(other.dvd_id) == other_before
            and publisher.calls == []
            and calls == [record.dvd_id],
            "EXPLICIT_RETRY_SYSTEMIC_SINGLE_TITLE_BOUND",
        )

    with TemporaryDirectory(prefix="stage12-retry-recovery-smoke-") as raw:
        root = Path(raw)
        store, record, other, stranded = stranded_retry_fixture(root)
        other_before = store.get(other.dvd_id)
        require(
            store.validate_explicit_retry_recovery(
                record.dvd_id,
                expected_sequence=stranded.transition_sequence,
                media_path_identity=record.media_path_identity,
                holding_identity=record.holding_identity,
                source_size_bytes=record.source_size_bytes,
                source_mtime_ns=record.source_mtime_ns,
            ) == stranded,
            "STRANDED_EXPLICIT_RETRY_RECOVERY_PREFLIGHT_PASS",
        )
        expect_raises(
            Stage12InvalidTransitionError,
            lambda: store.validate_explicit_retry_recovery(
                record.dvd_id,
                expected_sequence=stranded.transition_sequence - 1,
                media_path_identity=record.media_path_identity,
                holding_identity=record.holding_identity,
                source_size_bytes=record.source_size_bytes,
                source_mtime_ns=record.source_mtime_ns,
            ),
            "STRANDED_RECOVERY_SEQUENCE_MISMATCH_REJECTED",
        )
        expect_raises(
            Stage12RolloutIdentityError,
            lambda: store.validate_explicit_retry_recovery(
                record.dvd_id,
                expected_sequence=stranded.transition_sequence,
                media_path_identity=record.media_path_identity,
                holding_identity=record.holding_identity,
                source_size_bytes=record.source_size_bytes + 1,
                source_mtime_ns=record.source_mtime_ns,
            ),
            "STRANDED_RECOVERY_SOURCE_DRIFT_REJECTED",
        )
        expect_raises(
            Stage12InvalidTransitionError,
            lambda: store.validate_explicit_retry_recovery(
                other.dvd_id,
                expected_sequence=store.get(other.dvd_id).transition_sequence,
                media_path_identity=other.media_path_identity,
                holding_identity=other.holding_identity,
                source_size_bytes=other.source_size_bytes,
                source_mtime_ns=other.source_mtime_ns,
            ),
            "STRANDED_RECOVERY_WRONG_STATUS_REJECTED",
        )

        # A RUNNING title from ordinary bulk is not eligible for this recovery.
        wrong_event = store.transition(
            other.dvd_id,
            STATE_RUNNING,
            expected_from="PENDING",
            reason="STAGE12_BATCH_START",
            provenance={"operation": "STAGE12_SERIAL_BATCH"},
        )
        expect_raises(
            Stage12RolloutIdentityError,
            lambda: store.validate_explicit_retry_recovery(
                other.dvd_id,
                expected_sequence=wrong_event.transition_sequence,
                media_path_identity=other.media_path_identity,
                holding_identity=other.holding_identity,
                source_size_bytes=other.source_size_bytes,
                source_mtime_ns=other.source_mtime_ns,
            ),
            "STRANDED_RECOVERY_WRONG_START_EVENT_REJECTED",
        )

    with TemporaryDirectory(prefix="stage12-retry-recovery-entrypoint-smoke-") as raw:
        root = Path(raw)
        store, record, other, stranded = stranded_retry_fixture(root)
        other_before = store.get(other.dvd_id)
        before = store.list_states()
        lock_path = root / "runtime" / "bulk-runner.lock"
        lock_path.parent.mkdir()

        class FakeNASFilesystem:
            def lstat(self, relative):
                if relative == record.media_path_identity:
                    return SimpleNamespace(
                        st_mode=stat.S_IFREG | 0o644,
                        st_size=record.source_size_bytes,
                        st_mtime_ns=record.source_mtime_ns,
                    )
                raise FileNotFoundError(relative)

        discovery_row = {
            "relative_path": record.media_path_identity,
            "size_bytes": record.source_size_bytes,
            "mtime_ns": record.source_mtime_ns,
        }
        inventory_records = {record.dvd_id: record}
        with patch.dict(os.environ, {}, clear=True):
            require(
                run_explicit_retry_recovery(
                    expected_head="a" * 40,
                    dvd_id=record.dvd_id,
                    expected_sequence=stranded.transition_sequence,
                ) == 2,
                "STRANDED_RECOVERY_AUTH_REQUIRED",
            )
        require(store.list_states() == before,
                "STRANDED_RECOVERY_NO_AUTH_STATE_INVARIANT")

        with (
            patch.dict(
                os.environ,
                {
                    EXPLICIT_RETRY_RECOVERY_AUTH_ENV:
                        EXPLICIT_RETRY_RECOVERY_AUTH_VALUE,
                },
            ),
            patch.object(bulk_runner, "ROLLOUT_DB", store.state_path),
            patch.object(bulk_runner, "LOCK_PATH", lock_path),
            patch.object(bulk_runner, "check_repo", lambda expected: None),
            patch.object(
                bulk_runner,
                "read_discovery_rows",
                lambda dvd_ids, state_store: (discovery_row,),
            ),
            patch.object(
                bulk_runner,
                "read_exact_nas_inventory",
                lambda rows, reader: inventory_records,
            ),
            patch(
                "teddy_discovery_stage12_inventory.build_subtitle_ssh_reader",
                lambda **kwargs: object(),
            ),
            patch(
                "teddy_discovery_stage12_rollout.build_nas_preflight_filesystem",
                lambda **kwargs: FakeNASFilesystem(),
            ),
            redirect_stdout(io.StringIO()),
        ):
            require(
                run_explicit_retry_recovery(
                    expected_head="a" * 40,
                    dvd_id=record.dvd_id,
                    expected_sequence=stranded.transition_sequence,
                ) == 0,
                "STRANDED_EXPLICIT_RETRY_RECOVERY_ENTRYPOINT_PASS",
            )
        recovered = store.get(record.dvd_id)
        require(
            recovered.status == STATE_FAILED_RETRYABLE
            and recovered.transition_sequence == stranded.transition_sequence + 1
            and recovered.last_transition_reason
                == STAGE12_EXPLICIT_RETRY_CRASH_RECOVERY,
            "STRANDED_RECOVERY_AUDITED_TRANSITION",
        )
        require(
            store.get(other.dvd_id) == other_before,
            "STRANDED_RECOVERY_OTHER_TITLE_UNCHANGED",
        )

    with TemporaryDirectory(prefix="stage12-retry-recovery-active-smoke-") as raw:
        root = Path(raw)
        store, record, other, stranded = stranded_retry_fixture(root)
        other_running = store.transition(
            other.dvd_id,
            STATE_RUNNING,
            expected_from=STATE_PENDING,
            reason="STAGE12_BATCH_START",
            provenance={"operation": "STAGE12_SERIAL_BATCH"},
        )
        before = store.list_states()
        lock_path = root / "runtime" / "bulk-runner.lock"
        lock_path.parent.mkdir()
        with (
            patch.dict(
                os.environ,
                {
                    EXPLICIT_RETRY_RECOVERY_AUTH_ENV:
                        EXPLICIT_RETRY_RECOVERY_AUTH_VALUE,
                },
            ),
            patch.object(bulk_runner, "ROLLOUT_DB", store.state_path),
            patch.object(bulk_runner, "LOCK_PATH", lock_path),
            patch.object(bulk_runner, "check_repo", lambda expected: None),
            redirect_stdout(io.StringIO()),
        ):
            expect_raises(
                Stage12BulkRunnerError,
                lambda: run_explicit_retry_recovery(
                    expected_head="a" * 40,
                    dvd_id=record.dvd_id,
                    expected_sequence=stranded.transition_sequence,
                ),
                "RECOVERY_BLOCKS_OTHER_ACTIVE_TITLE",
            )
        require(store.list_states() == before and other_running.status == STATE_RUNNING,
                "RECOVERY_ACTIVE_GUARD_STATE_INVARIANT")

    with TemporaryDirectory(prefix="stage12-retry-recovery-race-smoke-") as raw:
        store, record, _other, stranded = stranded_retry_fixture(Path(raw))
        expect_raises(
            Stage12InvalidTransitionError,
            lambda: store.transition(
                record.dvd_id,
                STATE_FAILED_RETRYABLE,
                reason=STAGE12_EXPLICIT_RETRY_CRASH_RECOVERY,
                provenance={"operation": "RECOVER_EXPLICIT_RETRY"},
                expected_from=STATE_RUNNING,
                expected_sequence=stranded.transition_sequence,
                expected_previous_event=(
                    "PENDING",
                    STATE_RUNNING,
                    "STAGE12_BATCH_START",
                ),
            ),
            "STRANDED_RECOVERY_LAST_EVENT_CAS_REJECTED",
        )

    with TemporaryDirectory(prefix="stage12-retry-success-smoke-") as raw:
        root = Path(raw)
        store, record, other, failed = failed_fixture(root, "TRY-101")
        other_before = store.get(other.dvd_id)
        runner, nas, publisher, calls = build_runner(root, store, record)
        result = runner.run(Stage12BatchSelection(1, (record.dvd_id,)))
        require(result.titles[0].final_state == STATE_PUBLISHED,
                "EXPLICIT_RETRY_REUSES_PUBLICATION_PATH")
        require(calls == [record.dvd_id], "EXPLICIT_RETRY_REUSES_STAGE11_PATH")
        require(publisher.calls == [record.dvd_id], "EXPLICIT_RETRY_PUBLISH_ONCE")
        require(store.get(other.dvd_id) == other_before,
                "OTHER_TITLE_STATE_UNCHANGED_ON_SUCCESS")
        published = store.get(record.dvd_id)
        require(published.status == STATE_PUBLISHED, "PUBLISHED_STATE")
        expect_raises(
            Stage12InvalidTransitionError,
            lambda: store.validate_explicit_retry(
                record.dvd_id,
                expected_sequence=published.transition_sequence,
                media_path_identity=record.media_path_identity,
                holding_identity=record.holding_identity,
                source_size_bytes=record.source_size_bytes,
                source_mtime_ns=record.source_mtime_ns,
            ),
            "PUBLISHED_TARGET_REJECTED",
        )

    print("STAGE12_EXPLICIT_RETRY_SMOKE=PASS")
    print("JELLYFIN_CONTRACT_MUTATION_GUARD=PASS")
    print("PREFLIGHT_AUTH_SEQUENCE_FINGERPRINT=PASS")
    print("FAILURE_ISOLATION_AND_SINGLE_TITLE_BOUND=PASS")
    print("EXPLICIT_RETRY_SYSTEMIC_CAUSE_REMAINS_SYSTEMIC=PASS")
    print("PRODUCTION_INTERPRETER_PREFLIGHT=PASS")
    print("STRANDED_EXPLICIT_RETRY_RECOVERY=PASS")
    print("STAGE11_PUBLICATION_PATH_REUSE=PASS")
    print("OTHER_TITLE_STATE_INVARIANT=PASS")


if __name__ == "__main__":
    main_smoke()
