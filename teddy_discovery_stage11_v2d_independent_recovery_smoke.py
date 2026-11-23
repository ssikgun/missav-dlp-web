"""Focused synthetic V2-D recovery checks; no media, model, or transport."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import stat
import tempfile

from teddy_discovery_asr import ASRSegment
from teddy_discovery_stage11_v2d import (
    V2DHold,
    _build_targeted_requests,
    _load_or_run_external_targeted_evidence,
    run_v2d_pipeline,
)
from teddy_discovery_stage11_v2d_smoke import OfflineInvoke, _plan, _private_subdir, _settings, require
from teddy_discovery_targeted_asr_artifact import TargetedASRArtifact
from teddy_discovery_targeted_hybrid_evidence import TargetedASRWindowEvidence


class ExternalOnlyTargetedRunner:
    """Returns a deterministic fake artifact for aligned JA-only windows."""

    def __init__(self, snapshot, runtime_identity, *, bad_snapshot=False, empty=False):
        self.source_snapshot = snapshot
        self.runtime_identity = runtime_identity
        self.engine_version = "synthetic-external-targeted-v1"
        self.bad_snapshot = bad_snapshot
        self.empty = empty
        self.calls = 0

    def targeted_external_ja(self, request):
        self.calls += 1
        snapshot = self.source_snapshot
        if self.bad_snapshot:
            snapshot = replace(snapshot, source_mtime_ns=snapshot.source_mtime_ns + 1)
        windows = []
        for window in request.windows:
            segments = ()
            if not self.empty:
                start_ms = window.start_ms + 10
                end_ms = min(window.end_ms, start_ms + 800)
                if end_ms <= start_ms:
                    raise AssertionError("fixture window is unexpectedly short")
                segments = (ASRSegment(start_ms, end_ms, "合成追加音声候補"),)
            windows.append(TargetedASRWindowEvidence(
                source_snapshot=snapshot,
                window_start_ms=window.start_ms,
                window_end_ms=window.end_ms,
                external_cue_ids=window.external_cue_ids,
                segments=segments,
            ))
        return TargetedASRArtifact(
            source_snapshot=snapshot,
            runtime_identity=self.runtime_identity,
            engine_version=self.engine_version,
            windows=tuple(windows),
        )


class InspectingOfflineInvoke(OfflineInvoke):
    def __init__(self):
        super().__init__(needs_audio_evidence=True, reject_asr=True)
        self.targeted_candidate_ids = []
        self.targeted_candidate_identities = []

    def __call__(self, prompt, directory, label, validator, *, hermes_settings, reuse_only=False):
        if label == "ja-master-targeted-readjudication":
            payload = json.loads(prompt.decode().split("SOURCE_BOUND_GROUP=", 1)[1])
            for window in payload["targeted_second_evidence"]["windows"]:
                for segment in window["segments"]:
                    candidate_id = segment.get("targeted_candidate_id")
                    require(type(candidate_id) is str and len(candidate_id) == 64,
                            "TARGETED_CANDIDATE_HAS_STABLE_HASH_ID")
                    self.targeted_candidate_ids.append(candidate_id)
                    self.targeted_candidate_identities.append((
                        candidate_id, window["window_id"], segment["start_ms"],
                        segment["end_ms"], segment["text"],
                    ))
        return super().__call__(
            prompt, directory, label, validator,
            hermes_settings=hermes_settings, reuse_only=reuse_only,
        )


def main():
    settings = _settings()
    plan = _plan(True)
    bundle = plan.review_set._source_bundle
    snapshot = bundle.asr_result.source_snapshot
    runtime = bundle.asr_result.runtime_identity

    # The source decision explicitly rejects baseline ASR. The only accepted
    # JA Master entries are validated, affine-aligned external-JA-only refs.
    with tempfile.TemporaryDirectory(prefix="s11-v2d-external-recovery-") as tmp:
        root = Path(tmp)
        staging = _private_subdir(root, "staging")
        output = _private_subdir(root, "output")
        invoke = InspectingOfflineInvoke()
        runner = ExternalOnlyTargetedRunner(snapshot, runtime)
        result = run_v2d_pipeline(
            plan, invoke=invoke, hermes_settings=settings,
            staging_root=staging, output_directory=output,
            claim_token=71, targeted_runner=runner,
        )
        require(result.state == "CLEAN_SRT_READY", "ALIGNED_EXTERNAL_ONLY_RECOVERY_COMPLETES")
        require(runner.calls == 1, "ONE_BOUNDED_EXTERNAL_TARGETED_CALL")
        require(result.master.targeted_evidence_sha256 is not None,
                "TARGETED_ARTIFACT_LINKED_TO_MASTER")
        require(result.master.cues and all(
            ref.source == "external_ja"
            for cue in result.master.cues for ref in cue.source_references
        ), "NO_BASELINE_ASR_REFERENCE_OR_FAKE_INDEX")
        package_evidence = tuple(cue.stt_ja for cue in result.package.cues if cue.stt_ja)
        require(any("合成追加音声候補" in text for text in package_evidence),
                "TARGETED_ASR_REACHES_TRANSLATION_INPUT")
        require(any(label == "ja-master-targeted-readjudication" for label, _ in invoke.calls),
                "EXTERNAL_ONLY_GROUP_READJUDICATED")
        identities_by_id = {}
        for candidate_id, window_id, start_ms, end_ms, text in invoke.targeted_candidate_identities:
            identity = (window_id, start_ms, end_ms, text)
            previous = identities_by_id.setdefault(candidate_id, identity)
            require(previous == identity, "STABLE_ID_HAS_ONE_SEGMENT_IDENTITY")
        require(invoke.targeted_candidate_ids and identities_by_id
                and len(set(identities_by_id.values())) == len(identities_by_id),
                "TARGETED_CANDIDATE_IDENTITY_AND_DUPLICATE_GUARD")
        proof = json.loads((output / "v2d-proof-v1.json").read_bytes())
        require(proof["targeted_asr_artifact_sha256"] is not None
                and proof["targeted_asr_linkage_sha256"] is not None,
                "TARGETED_ARTIFACT_AND_LINKAGE_IN_FINAL_PROOF")
        require(all(stat.S_IMODE((output / name).stat().st_mode) == 0o600
                    for name in ("ja-master-v1.json", "clean-ja-v1.srt",
                                 "clean-ko-v1.srt", "v2d-proof-v1.json")),
                "PRIVATE_FINAL_ARTIFACT_MODES")
        require((output / "clean-ja-v1.srt").stat().st_size > 0
                and (output / "clean-ko-v1.srt").stat().st_size > 0,
                "PRIVATE_JA_KO_OUTPUTS_PRESENT")

    # Missing originating intervals or a detached source snapshot cannot be
    # converted into an external cue ID, baseline index, or successful result.
    with tempfile.TemporaryDirectory(prefix="s11-v2d-external-hold-") as tmp:
        root = Path(tmp)
        baseline_output = _private_subdir(root, "baseline-output")
        baseline = run_v2d_pipeline(
            plan, invoke=OfflineInvoke(reject_asr=True), hermes_settings=settings,
            staging_root=_private_subdir(root, "baseline-staging"),
            output_directory=baseline_output, claim_token=72,
        )
        require(baseline.state == "CLEAN_SRT_READY", "EXTERNAL_BASELINE_FOR_GUARD_FIXTURE")
        requested_result = replace(
            baseline.translation,
            cues=tuple(replace(cue, needs_audio_evidence=True)
                       for cue in baseline.translation.cues),
        )
        requests = _build_targeted_requests(baseline.master, requested_result)
        require(len(requests) == 1, "EXTERNAL_ONLY_REQUEST_CLASSIFIED")
        bad_runner = ExternalOnlyTargetedRunner(snapshot, runtime, bad_snapshot=True)
        bad_staging = _private_subdir(root, "bad-staging")
        try:
            _load_or_run_external_targeted_evidence(
                requests[0], master=baseline.master, targeted_runner=bad_runner,
                staging_root=bad_staging, reuse_only=False,
            )
        except V2DHold as error:
            require(str(error) == "TARGETED_ASR_EXTERNAL_SOURCE_MISMATCH",
                    "MISMATCHED_SOURCE_SAFE_HOLD")
        else:
            raise AssertionError("MISMATCHED_SOURCE_ACCEPTED")
        require(bad_runner.calls == 1, "MISMATCHED_EVIDENCE_EXECUTED_ONCE_NO_RETRY")

        empty_runner = ExternalOnlyTargetedRunner(snapshot, runtime, empty=True)
        empty_staging = _private_subdir(root, "empty-staging")
        try:
            _load_or_run_external_targeted_evidence(
                requests[0], master=baseline.master, targeted_runner=empty_runner,
                staging_root=empty_staging, reuse_only=False,
            )
        except V2DHold as error:
            require(str(error) == "TARGETED_ASR_EXTERNAL_EVIDENCE_EMPTY",
                    "EMPTY_EVIDENCE_SAFE_HOLD")
        else:
            raise AssertionError("EMPTY_EVIDENCE_ACCEPTED")

        missing_staging = _private_subdir(root, "missing-staging")
        try:
            _load_or_run_external_targeted_evidence(
                requests[0], master=baseline.master, targeted_runner=None,
                staging_root=missing_staging, reuse_only=False,
            )
        except V2DHold as error:
            require(str(error) == "TARGETED_ASR_EXTERNAL_ADAPTER_UNAVAILABLE",
                    "MISSING_EVIDENCE_ADAPTER_SAFE_HOLD")
        else:
            raise AssertionError("MISSING_EVIDENCE_ADAPTER_ACCEPTED")
        require(not list(bad_staging.rglob("*.json"))
                and not list(empty_staging.rglob("*.json"))
                and not list(missing_staging.rglob("*.json")),
                "NO_PARTIAL_EVIDENCE_ARTIFACT_ON_HOLD")

    # The existing baseline-ASR second-evidence branch still dispatches via
    # the original artifact/validator path after the request split.
    from teddy_discovery_stage11_v2d_smoke import OfflineTargetedRunner
    with tempfile.TemporaryDirectory(prefix="s11-v2d-baseline-regression-") as tmp:
        root = Path(tmp)
        baseline_plan = _plan(False)
        baseline_runner = OfflineTargetedRunner(
            baseline_plan.review_set._source_bundle.asr_result.runtime_identity,
        )
        baseline_result = run_v2d_pipeline(
            baseline_plan, invoke=OfflineInvoke(needs_audio_evidence=True),
            hermes_settings=settings,
            staging_root=_private_subdir(root, "staging"),
            output_directory=_private_subdir(root, "output"),
            claim_token=73, targeted_runner=baseline_runner,
        )
        require(baseline_result.state == "CLEAN_SRT_READY"
                and baseline_runner.calls == 1,
                "BASELINE_TARGETED_BRANCH_REGRESSION")

    print("S11_V2D_INDEPENDENT_RECOVERY_SMOKE=PASS")


if __name__ == "__main__":
    main()
