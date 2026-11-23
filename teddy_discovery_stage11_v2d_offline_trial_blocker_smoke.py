"""Focused V2-E blocker checks. Synthetic fixtures only; no media/model calls."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile

from teddy_discovery_stage11_v2d import (
    V2DExecutionLimits,
    V2DError,
    V2DLimitStop,
    _adjudicate_group_batches,
    _make_batch_material,
    _pack_group_batches,
    _source_fingerprint,
    run_v2d_pipeline,
)
from teddy_discovery_stage11_v2d_smoke import (
    OfflineInvoke,
    OfflineTargetedRunner,
    _plan,
    _private_subdir,
    _settings,
    require,
)


class BatchedInvoke(OfflineInvoke):
    _v2d_batch_groups = True

    def __init__(self, *, mark_audio_uncertain=False, missing_target_flag=False):
        super().__init__()
        self.mark_audio_uncertain = mark_audio_uncertain
        self.missing_target_flag = missing_target_flag
        self.batch_calls = 0
        self.targeted_group_ids = []
        self.uncertain_marked = False

    @staticmethod
    def _group_result(payload, *, uncertain=False, include_audio_flag=True):
        group = payload["group"]
        sources = []
        accepted = []
        for index, member in enumerate(group["members"]):
            status = "UNCERTAIN" if uncertain and index == 0 else (
                "ACCEPTED" if member["aligned_start_ms"] is not None else "REJECTED")
            sources.append({"source_key": member["source_key"], "status": status,
                            "rationale": "synthetic source-bound judgment"})
            if status == "ACCEPTED":
                accepted.append(member)
        outputs = [{
            "japanese_text": member["text"],
            "source_spans": [{"source_key": member["source_key"],
                               "word_start_index": None, "word_end_index": None}],
            "rationale": "synthetic source-supported output",
        } for member in accepted]
        row = {
            "group_id": group["group_id"],
            "candidate_decisions": [{"candidate_id": candidate["candidate_id"], "status": "ACCEPTED",
                                     "rationale": "synthetic relation evidence"}
                                    for candidate in group["candidate_relations"]],
            "source_decisions": sources,
            "outputs": outputs,
        }
        if include_audio_flag:
            row["audio_evidence_needed"] = bool(uncertain)
        return row

    def __call__(self, prompt, directory, label, validator, *, hermes_settings, reuse_only=False):
        if label in {"ja-master-adjudication-batch", "ja-master-targeted-readjudication-batch"}:
            self.batch_calls += 1
            envelope = json.loads(prompt.decode().split("SOURCE_BOUND_BATCH=", 1)[1])
            rows = []
            for group_payload in envelope["groups"]:
                group_id = group_payload["group"]["group_id"]
                targeted = label.startswith("ja-master-targeted")
                if targeted:
                    self.targeted_group_ids.append(group_id)
                    require("targeted_second_evidence" in group_payload,
                            "TARGETED_EVIDENCE_BOUND_TO_GROUP")
                uncertain = (self.mark_audio_uncertain and not targeted and self.batch_calls == 1
                             and not self.uncertain_marked)
                if uncertain:
                    self.uncertain_marked = True
                include_flag = not (targeted and self.missing_target_flag)
                rows.append(self._group_result(group_payload, uncertain=uncertain,
                                               include_audio_flag=include_flag))
            response = {
                "batch_id": envelope["batch_id"],
                "source_fingerprint": envelope["source_fingerprint"],
                "groups": rows,
            }
            return validator(json.dumps(response, ensure_ascii=False).encode())
        return super().__call__(prompt, directory, label, validator,
                                hermes_settings=hermes_settings, reuse_only=reuse_only)


class MissingBatchGroup(BatchedInvoke):
    def __call__(self, prompt, directory, label, validator, *, hermes_settings, reuse_only=False):
        if label == "ja-master-adjudication-batch":
            envelope = json.loads(prompt.decode().split("SOURCE_BOUND_BATCH=", 1)[1])
            response = {"batch_id": envelope["batch_id"],
                        "source_fingerprint": envelope["source_fingerprint"],
                        "groups": []}
            return validator(json.dumps(response).encode())
        return super().__call__(prompt, directory, label, validator,
                                hermes_settings=hermes_settings, reuse_only=reuse_only)


class DuplicateBatchGroup(BatchedInvoke):
    def __call__(self, prompt, directory, label, validator, *, hermes_settings, reuse_only=False):
        if label == "ja-master-adjudication-batch":
            envelope = json.loads(prompt.decode().split("SOURCE_BOUND_BATCH=", 1)[1])
            first = envelope["groups"][0]
            row = self._group_result(first)
            response = {"batch_id": envelope["batch_id"],
                        "source_fingerprint": envelope["source_fingerprint"],
                        "groups": [row, row]}
            return validator(json.dumps(response).encode())
        return super().__call__(prompt, directory, label, validator,
                                hermes_settings=hermes_settings, reuse_only=reuse_only)


def main():
    plan = _plan(False)
    settings = _settings()
    fingerprint = _source_fingerprint(plan)
    payloads = tuple((group.group_id, __import__("teddy_discovery_stage11_v2d")._group_payload(plan, group))
                     for group in plan.groups)
    packed = _pack_group_batches(fingerprint, payloads)
    require(len(packed) >= 1, "BOUNDED_BATCHES_CREATED")
    all_ids = tuple(group_id for batch, *_ in packed for group_id, _ in batch)
    require(all_ids == tuple(group.group_id for group in plan.groups),
            "ALL_GROUPS_AND_ORDER_PRESERVED")
    first_id = packed[0][1]
    changed_group = (payloads[0][0], {**payloads[0][1], "changed_fixture": True})
    changed_id = _make_batch_material(fingerprint, (changed_group,))[0]
    require(first_id != changed_id, "BATCH_ID_BINDS_EXACT_INPUT")

    with tempfile.TemporaryDirectory(prefix="s11-v2e-batch-coverage-") as tmp:
        root = Path(tmp)
        task = _private_subdir(root, "task")
        invoke = MissingBatchGroup()
        try:
            _adjudicate_group_batches(
                payloads, expected_groups={g.group_id: g for g in plan.groups},
                source_fingerprint=fingerprint, invoke=invoke,
                hermes_settings=settings, task=task,
                label="ja-master-adjudication-batch", reuse_only=False,
            )
        except V2DError:
            pass
        else:
            raise AssertionError("MISSING_GROUP_RESPONSE_ACCEPTED")

    with tempfile.TemporaryDirectory(prefix="s11-v2e-batch-duplicate-") as tmp:
        root = Path(tmp)
        try:
            _adjudicate_group_batches(
                payloads[:1], expected_groups={g.group_id: g for g in plan.groups},
                source_fingerprint=fingerprint, invoke=DuplicateBatchGroup(),
                hermes_settings=settings, task=_private_subdir(root, "task"),
                label="ja-master-adjudication-batch", reuse_only=False,
            )
        except V2DError:
            pass
        else:
            raise AssertionError("DUPLICATE_GROUP_RESPONSE_ACCEPTED")

    # A changed batch input cannot reuse an older stage receipt directory.
    with tempfile.TemporaryDirectory(prefix="s11-v2e-batch-resume-identity-") as tmp:
        root = Path(tmp)
        task = _private_subdir(root, "task")
        invoke = BatchedInvoke()
        _adjudicate_group_batches(
            payloads, expected_groups={g.group_id: g for g in plan.groups},
            source_fingerprint=fingerprint, invoke=invoke,
            hermes_settings=settings, task=task,
            label="ja-master-adjudication-batch", reuse_only=False,
        )
        changed_payloads = ((payloads[0][0], {**payloads[0][1], "changed_fixture": True}),)
        try:
            _adjudicate_group_batches(
                changed_payloads, expected_groups={g.group_id: g for g in plan.groups},
                source_fingerprint=fingerprint, invoke=invoke,
                hermes_settings=settings, task=task,
                label="ja-master-adjudication-batch", reuse_only=True,
            )
        except V2DError:
            pass
        else:
            raise AssertionError("CHANGED_BATCH_REUSED_OLD_STAGE")

    # Initial UNCERTAIN can reach one source-bound Targeted ASR pass, then only
    # the owning group is adjudicated again before JA Master materialization.
    with tempfile.TemporaryDirectory(prefix="s11-v2e-early-targeted-") as tmp:
        root = Path(tmp)
        invoke = BatchedInvoke(mark_audio_uncertain=True)
        runner = OfflineTargetedRunner(plan.review_set._source_bundle.asr_result.runtime_identity)
        staging = _private_subdir(root, "staging")
        output = _private_subdir(root, "output")
        result = run_v2d_pipeline(
            plan, invoke=invoke, hermes_settings=settings,
            staging_root=staging, output_directory=output, claim_token=101,
            targeted_runner=runner,
            execution_limits=V2DExecutionLimits(max_hermes_attempts=20, max_wall_seconds=120),
        )
        require(result.state == "CLEAN_SRT_READY", "EARLY_TARGETED_RECOVERY_COMPLETES")
        require(runner.calls == 1, "ONE_SYNTHETIC_TARGETED_PASS")
        require(len(set(invoke.targeted_group_ids)) == len(invoke.targeted_group_ids) == 1,
                "ONLY_AFFECTED_GROUP_READJUDICATED")
        require(result.master.targeted_evidence_sha256 is not None,
                "TARGETED_EVIDENCE_BOUND_TO_MASTER")
        proof = json.loads((output / "v2d-proof-v1.json").read_bytes())
        require(proof["semantic_batches"] and
                all(item["input_sha256"] and item["prompt_sha256"] for item in proof["semantic_batches"]),
                "BATCH_INPUT_AND_PROMPT_HASHES_RECORDED")

    # Missing/invalid source interval or unavailable adapter remains HOLD and
    # never materializes final files.
    with tempfile.TemporaryDirectory(prefix="s11-v2e-early-hold-") as tmp:
        root = Path(tmp)
        invoke = BatchedInvoke(mark_audio_uncertain=True)
        output = _private_subdir(root, "output")
        result = run_v2d_pipeline(
            plan, invoke=invoke, hermes_settings=settings,
            staging_root=_private_subdir(root, "staging"),
            output_directory=output, claim_token=102,
            targeted_runner=None,
            execution_limits=V2DExecutionLimits(max_hermes_attempts=20, max_wall_seconds=120),
        )
        require(result.state == "HOLD" and result.reason_code == "TARGETED_ASR_ADAPTER_UNAVAILABLE",
                "MISSING_TARGETED_EVIDENCE_HOLDS")
        require(not any((output / name).exists() for name in (
            "ja-master-v1.json", "clean-ja-v1.srt", "clean-ko-v1.srt", "v2d-proof-v1.json")),
            "NO_FINAL_OUTPUT_ON_HOLD")

    # A limit thrown by the targeted adapter must survive artifact handling as
    # LIMIT_STOP, not be normalized into an evidence HOLD.
    with tempfile.TemporaryDirectory(prefix="s11-v2e-asr-limit-stop-") as tmp:
        root = Path(tmp)
        invoke = BatchedInvoke(mark_audio_uncertain=True)
        class LimitTargetedRunner(OfflineTargetedRunner):
            def __call__(self, *_args, **_kwargs):
                raise V2DLimitStop("WALL_TIME_LIMIT_BEFORE_TARGETED_ASR")
        runner = LimitTargetedRunner(plan.review_set._source_bundle.asr_result.runtime_identity)
        output = _private_subdir(root, "output")
        result = run_v2d_pipeline(
            plan, invoke=invoke, hermes_settings=settings,
            staging_root=_private_subdir(root, "staging"), output_directory=output,
            claim_token=106, targeted_runner=runner,
            execution_limits=V2DExecutionLimits(max_hermes_attempts=20, max_wall_seconds=120),
        )
        require(result.state == "LIMIT_STOP"
                and result.reason_code == "WALL_TIME_LIMIT_BEFORE_TARGETED_ASR",
                "TARGETED_ASR_LIMIT_STOP_REMAINS_EXPLICIT")
        require(not any((output / name).exists() for name in (
            "ja-master-v1.json", "clean-ja-v1.srt", "clean-ko-v1.srt", "v2d-proof-v1.json")),
            "TARGETED_ASR_LIMIT_STOP_HAS_NO_FINAL_OUTPUT")

    # A scope-wide attempt limit halts before the next stage and leaves the
    # first stage directory intact; output remains absent.
    with tempfile.TemporaryDirectory(prefix="s11-v2e-limit-stop-") as tmp:
        root = Path(tmp)
        invoke = BatchedInvoke()
        staging = _private_subdir(root, "staging")
        output = _private_subdir(root, "output")
        result = run_v2d_pipeline(
            plan, invoke=invoke, hermes_settings=settings,
            staging_root=staging, output_directory=output, claim_token=103,
            execution_limits=V2DExecutionLimits(max_hermes_attempts=1, max_wall_seconds=120),
        )
        require(result.state == "LIMIT_STOP" and result.reason_code == "HERMES_ATTEMPT_LIMIT",
                "ATTEMPT_BUDGET_STOPS_PIPELINE")
        require(result.hermes_attempts_started == 1, "ATTEMPT_COUNT_REPORTED")
        require(any(staging.rglob("batch-*")), "COMPLETED_STAGE_EVIDENCE_RETAINED")
        require(not any((output / name).exists() for name in (
            "ja-master-v1.json", "clean-ja-v1.srt", "clean-ko-v1.srt", "v2d-proof-v1.json")),
            "LIMIT_STOP_HAS_NO_FINAL_ARTIFACTS")

    # Wall clock limit is checked at every stage boundary; no second call is started.
    with tempfile.TemporaryDirectory(prefix="s11-v2e-wall-stop-") as tmp:
        root = Path(tmp)
        invoke = BatchedInvoke()
        # Use a regular callable carrying the explicit batch marker.
        class Slow:
            _v2d_batch_groups = True
            def __call__(self, *args, **kwargs):
                import time
                time.sleep(0.02)
                return invoke(*args, **kwargs)
        output = _private_subdir(root, "output")
        result = run_v2d_pipeline(
            plan, invoke=Slow(), hermes_settings=settings,
            staging_root=_private_subdir(root, "staging"), output_directory=output,
            claim_token=104,
            execution_limits=V2DExecutionLimits(max_hermes_attempts=10, max_wall_seconds=0.005),
        )
        require(result.state == "LIMIT_STOP" and result.reason_code == "WALL_TIME_LIMIT_AFTER_STAGE",
                "WALL_BUDGET_STOPS_AFTER_INFLIGHT_BOUNDED_STAGE")
        require(result.hermes_attempts_started == 1, "WALL_STOP_CALL_COUNT")
        require(not any((output / name).exists() for name in (
            "ja-master-v1.json", "clean-ja-v1.srt", "clean-ko-v1.srt", "v2d-proof-v1.json")),
            "WALL_STOP_HAS_NO_FINAL_ARTIFACTS")

    # Native-backed work cannot begin unless both cumulative limits are set.
    with tempfile.TemporaryDirectory(prefix="s11-v2e-native-limits-required-") as tmp:
        class NativeLike:
            def __init__(self):
                self.calls = 0
                self._verified_attempts = []
                class Bridge:
                    @staticmethod
                    def _python(*_args, **_kwargs):
                        return b"unused"
                self.bridge = Bridge()
            def invoke(self, prompt, directory, label, validator, *, hermes_settings, reuse_only=False):
                self.calls += 1
                raise AssertionError("native model callback must not run without limits")
        native = NativeLike()
        output = _private_subdir(Path(tmp), "output")
        result = run_v2d_pipeline(
            plan, invoke=native.invoke, hermes_settings=settings,
            staging_root=_private_subdir(Path(tmp), "staging"),
            output_directory=output, claim_token=105,
        )
        require(result.state == "LIMIT_STOP" and result.reason_code == "EXECUTION_LIMITS_REQUIRED",
                "NATIVE_RUN_REQUIRES_EXPLICIT_CUMULATIVE_LIMITS")
        require(native.calls == 0, "NO_NATIVE_CALL_WITHOUT_LIMITS")
        require(not any((output / name).exists() for name in (
            "ja-master-v1.json", "clean-ja-v1.srt", "clean-ko-v1.srt", "v2d-proof-v1.json")),
            "NO_OUTPUT_WITHOUT_LIMITS")

    print("S11_V2E_TRIAL_BLOCKER_OFFLINE=PASS")


if __name__ == "__main__":
    main()
