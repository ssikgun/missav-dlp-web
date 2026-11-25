"""Small synthetic V2-D integration checks. No media or models are used."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import stat
import tempfile

from teddy_discovery_stage11_hermes_profile import (
    HermesExecutionSettings,
    STAGE11_HERMES_TIMEOUT_ENV_NAMES,
)
from teddy_discovery_alignment_acceptance import (
    AlignmentAcceptancePolicy,
    REJECT_EXTERNAL,
    decide_alignment_acceptance,
)
from teddy_discovery_alignment_application import apply_alignment_acceptance
from teddy_discovery_stage11_ja_master import build_ja_master_review_set
from teddy_discovery_stage11_ja_master_smoke import (
    _accepted_application,
    _bundle,
    _external_payload,
)
from teddy_discovery_stage11_utterance_groups import build_utterance_review_plan
from teddy_discovery_stage11_utterance_groups_smoke import _review_set as _group_fixture
from teddy_discovery_stage11_controller import Stage11ControllerError
from teddy_discovery_asr import ASRSegment
from teddy_discovery_targeted_second_evidence import (
    TargetedSecondEvidenceWindowResult,
    bind_targeted_second_evidence,
)
from teddy_discovery_targeted_second_evidence_runner import TargetedSecondEvidenceExecution
from teddy_discovery_stateful_parts import build_stateful_part_plan
from teddy_discovery_stateful_translator import (
    StatefulSubtitlePackage,
    derive_stateful_session_id,
    serialize_stateful_model_input,
    stateful_session_id_for_package,
)
from teddy_discovery_stateful_quality_review import REPAIR
from teddy_discovery_subtitle_text import parse_subtitle_bytes
from teddy_discovery_stage11_v2d import (
    GroupAdjudication,
    CandidateDecision,
    MasterOutputProposal,
    SourceDecision,
    SourceSpan,
    V2DAdjudication,
    V2DError,
    V2DHold,
    _build_translation_package,
    _load_json,
    _materialized_cues,
    _round_ms,
    _parse_group_response,
    _source_fingerprint,
    _stage_bound_native_invoke,
    materialize_ja_master,
    run_v2d_pipeline,
    translate_ja_master,
    validate_adjudication,
)


def require(value, marker):
    if not value:
        raise AssertionError(marker)


def expect_raises(kind, callback, marker):
    try:
        callback()
    except kind:
        return
    except Exception as error:
        raise AssertionError(marker + ":" + type(error).__name__) from error
    raise AssertionError(marker)


def _settings():
    return HermesExecutionSettings(
        profile_name="subtitle-translator",
        provider="openai-codex",
        model="synthetic-model",
        reasoning_effort="max",
        hermes_version="synthetic-offline",
        config_sha256="a" * 64,
        timeout_env_supported=STAGE11_HERMES_TIMEOUT_ENV_NAMES,
    )


def _package_from_inline(prompt):
    marker = "INLINE_MODEL_INPUT="
    data = json.loads(prompt.decode("utf-8").rsplit(marker, 1)[1])
    cues = tuple(data["cues"])
    return data, cues


class OfflineInvoke:
    def __init__(self, *, triage_repair=False, whole_fails=False, uncertain=False,
                 needs_audio_evidence=False, reject_asr=False):
        self.triage_repair = triage_repair
        self.whole_fails = whole_fails
        self.uncertain = uncertain
        self.needs_audio_evidence = needs_audio_evidence
        self.reject_asr = reject_asr
        self.calls = []
        self.translation_generations = []
        self.settings_seen = []

    def __call__(self, prompt, directory, label, validator, *, hermes_settings, reuse_only=False):
        self.calls.append((label, reuse_only))
        self.settings_seen.append(hermes_settings.evidence())
        if label in {"ja-master-adjudication", "ja-master-targeted-readjudication"}:
            payload = json.loads(prompt.decode().split("SOURCE_BOUND_GROUP=", 1)[1])
            group = payload["group"]
            if label == "ja-master-targeted-readjudication":
                require("targeted_second_evidence" in payload, "TARGETED_EVIDENCE_IN_READJUDICATION_PROMPT")
            source_decisions = []
            outputs = []
            accepted = []
            for member in group["members"]:
                status = "ACCEPTED" if member["aligned_start_ms"] is not None else "REJECTED"
                if self.reject_asr and member["source_kind"] == "asr_segment":
                    status = "REJECTED"
                source_decisions.append({
                    "source_key": member["source_key"],
                    "status": "UNCERTAIN" if self.uncertain else status,
                    "rationale": "synthetic explicit source judgment",
                })
                if status == "ACCEPTED":
                    accepted.append(member)
            if accepted:
                if len(accepted) > 1:
                    outputs.append({
                            "japanese_text": "補足確認済み日本語" if label == "ja-master-targeted-readjudication" else "合成統合発話",
                        "source_spans": [{"source_key": item["source_key"],
                                          "word_start_index": None, "word_end_index": None}
                                         for item in accepted],
                        "rationale": "synthetic merge fixture",
                    })
                else:
                    for item in accepted:
                        outputs.append({
                            "japanese_text": "補足確認済み日本語" if label == "ja-master-targeted-readjudication" else item["text"],
                            "source_spans": [{"source_key": item["source_key"],
                                              "word_start_index": None, "word_end_index": None}],
                            "rationale": "synthetic single-source fixture",
                        })
            response = {
                "group_id": group["group_id"],
                "candidate_decisions": [{
                    "candidate_id": candidate["candidate_id"],
                    "status": "ACCEPTED",
                    "rationale": "synthetic relation judgment",
                } for candidate in group["candidate_relations"]],
                "source_decisions": source_decisions,
                "outputs": outputs,
            }
            return validator(json.dumps(response, ensure_ascii=False).encode())

        if label == "whole-title":
            if self.whole_fails:
                raise Stage11ControllerError("synthetic whole-title failure")
            data, cues = _package_from_inline(prompt)
            self.translation_generations.append(data["generation_key"])
            session = derive_stateful_session_id(data["dvd_id"], data["generation_key"], data["claim_token"])
            response = {
                "schema_version": data["schema_version"],
                "dvd_id": data["dvd_id"],
                "generation_key": data["generation_key"],
                "claim_token": data["claim_token"],
                "session_id": session,
                "cues": [{"cue_id": cue["cue_id"], "repaired_ja": None,
                          "ko": "합성 한국어 번역",
                          "needs_audio_evidence": (self.needs_audio_evidence
                                                   and ":targeted-" not in data["generation_key"])}
                         for cue in cues],
            }
            return validator(json.dumps(response, ensure_ascii=False).encode())

        if label.startswith("part-"):
            data, cues = _package_from_inline(prompt)
            package = StatefulSubtitlePackage(
                data["schema_version"], data["dvd_id"], data["generation_key"],
                data["claim_token"], tuple(
                    __import__("teddy_discovery_hermes_v2").HermesV2CueInput(
                        cue_id=cue["cue_id"], external_ja=cue["external_ja"],
                        stt_ja=cue["stt_ja"], en=cue["en"],
                        before_context=tuple(cue["before_context"]),
                        after_context=tuple(cue["after_context"]),
                    )
                    for cue in cues
                ),
            )
            plan = build_stateful_part_plan(package, serialize_stateful_model_input(package))
            expected = plan.parts[0]
            response = {
                "part_schema_version": 1,
                "session_id": plan.session_id,
                "input_sha256": plan.input_sha256,
                "part_index": expected.part_index,
                "first_cue_id": expected.first_cue_id,
                "last_cue_id": expected.last_cue_id,
                "cues": [{"cue_id": cue["cue_id"], "repaired_ja": None,
                          "ko": "합성 한국어 번역",
                          "needs_audio_evidence": (self.needs_audio_evidence
                                                   and ":targeted-" not in data["generation_key"])}
                         for cue in cues],
            }
            return validator(json.dumps(response, ensure_ascii=False).encode())

        if label in {"v2d-triage", "v2d-targeted-final-review"}:
            payload = json.loads(prompt.decode().rsplit("V2D_SOURCE_BOUND_INPUT=", 1)[1])
            request = payload["request"]
            target_ids = payload["target_cue_ids"]
            cue_ids = ([cue["cue_id"] for cue in request["cues"]]
                       if target_ids is None else target_ids)
            cues = []
            for index, cue_id in enumerate(cue_ids):
                repair = self.triage_repair and label == "v2d-triage" and index == 0
                repair = repair or (self.triage_repair and label == "v2d-targeted-final-review")
                cues.append({
                    "cue_id": cue_id,
                    "action": REPAIR if repair else "KEEP",
                    "category": "SEMANTIC_REPAIR" if repair else "DIALOGUE",
                    "reason": "synthetic evidence-supported fixture",
                    "replacement_ja": "修正日本語" if repair else None,
                    "replacement_ko": "수정 한국어" if repair else None,
                })
            response = {
                "schema_version": request["schema_version"],
                "request_sha256": payload["request_sha256"],
                "cues": cues,
            }
            return validator(json.dumps(response, ensure_ascii=False).encode())

        raise AssertionError("unexpected offline executor stage: " + label)


class OfflineTargetedRunner:
    """Synthetic response source; no PyAV, transport, worker, or model is used."""
    def __init__(self, runtime_identity):
        self.runtime_identity = runtime_identity
        self.engine_version = "synthetic-targeted-offline"
        self.calls = 0

    def __call__(self, asr_result, plan):
        self.calls += 1
        results = tuple(TargetedSecondEvidenceWindowResult(
            source_snapshot=plan.source_snapshot,
            window_id=window.window_id,
            window_start_ms=window.start_ms,
            window_end_ms=window.end_ms,
            segments=(ASRSegment(window.start_ms, window.end_ms, "合成追加音声根拠"),),
            plan_binding_sha256=plan.binding_sha256,
        ) for window in plan.windows)
        return TargetedSecondEvidenceExecution(
            plan=plan,
            policy_version="v1",
            bindings=tuple(bind_targeted_second_evidence(plan, results)),
        )


class InvalidOfflineTargetedRunner(OfflineTargetedRunner):
    def __call__(self, asr_result, plan):
        self.calls += 1
        return object()


class FakeNativeInvokeOwner:
    def __init__(self):
        self._verified_attempts = []
        self.settings_seen = []

    def invoke(self, prompt, directory, label, validator, *, hermes_settings, reuse_only=False):
        self.settings_seen.append((label, hermes_settings, reuse_only))
        self._verified_attempts.append({"label": label, "attempt": 1})
        return "synthetic-stage-result"


def _plan(with_external=True):
    review_set = (
        _group_fixture()
        if with_external
        else build_ja_master_review_set(_bundle(payload=None))
    )
    return build_utterance_review_plan(review_set)


def _private_subdir(root, name):
    path = Path(root) / name
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


def main():
    settings = _settings()
    require(_round_ms(__import__("fractions").Fraction(1, 2)) == 1, "HALF_UP_EXACT_TIE")
    require(_round_ms(__import__("fractions").Fraction(1499, 1000)) == 1, "HALF_UP_BELOW")
    require(_round_ms(__import__("fractions").Fraction(1501, 1000)) == 2, "HALF_UP_ABOVE")
    require({group.source_cardinality for group in _plan(True).groups} >= {
        "ASR_TO_JA_ONE_TO_MANY", "ASR_TO_JA_MANY_TO_ONE"
    }, "MERGE_SPLIT_SOURCE_FIXTURES_PRESENT")
    # Existing Native receipt settings remain attached to their exact prompt
    # stage, while a stage with no receipt starts under the current profile.
    with tempfile.TemporaryDirectory(prefix="s11-v2d-profile-stage-") as tmp:
        base = Path(tmp)
        owner = FakeNativeInvokeOwner()
        current = settings
        previous = replace(settings, model="previous-synthetic-model")
        bound, bound_owner = _stage_bound_native_invoke(owner.invoke, current)
        require(bound_owner is owner, "NATIVE_STAGE_OWNER_PRESERVED")
        prior_dir = _private_subdir(base, "completed-stage")
        prompt = b"synthetic completed stage prompt"
        prefix = prior_dir / "ja-master-attempt-1"
        prefix.with_suffix(".prompt.txt").write_bytes(prompt)
        prefix.with_suffix(".prompt.txt").chmod(0o600)
        prefix.with_suffix(".receipt.json").write_text(json.dumps({
            "hermes_execution_settings": previous.evidence(),
        }, sort_keys=True), encoding="utf-8")
        prefix.with_suffix(".receipt.json").chmod(0o600)
        require(bound(prompt, prior_dir, "ja-master", lambda raw: raw,
                      hermes_settings=current, reuse_only=False) == "synthetic-stage-result",
                "COMPLETED_STAGE_INVOKED")
        require(owner.settings_seen[-1][1] == previous,
                "COMPLETED_STAGE_KEEPS_ORIGINAL_PROFILE")
        require(owner._verified_attempts[-1]["hermes_execution_settings"] == previous.evidence(),
                "STAGE_ATTEMPT_PROOF_RECORDS_ACTUAL_PROFILE")
        expect_raises(V2DHold, lambda: bound(
            b"changed source-bound prompt", prior_dir, "ja-master", lambda raw: raw,
            hermes_settings=current, reuse_only=False,
        ), "CHANGED_INPUT_CANNOT_REUSE_OLD_NATIVE_RECEIPT")
        fresh_dir = _private_subdir(base, "unstarted-stage")
        bound(prompt, fresh_dir, "ja-master-new", lambda raw: raw,
              hermes_settings=current, reuse_only=False)
        require(owner.settings_seen[-1][1] == current,
                "UNSTARTED_STAGE_USES_CURRENT_PROFILE")
    with tempfile.TemporaryDirectory(prefix="s11-v2d-smoke-") as tmp:
        base = Path(tmp)
        staging = _private_subdir(base, "staging")
        output = _private_subdir(base, "output")
        invoke = OfflineInvoke(triage_repair=True)
        def _smoke_outside_runner():
            pass
        def _smoke_outside_span(recovery_plan):
            return {
                "schema_version": 1,
                "verified_container_duration_ms": 60_000,
                "runtime_identity": {
                    "engine": "faster-whisper", "model": "large-v3", "device": "cuda",
                    "compute_type": "int8_float16", "cpu_threads": None, "num_workers": 1,
                },
                "engine_version": "1.2.1",
                "windows": [{
                    "window_id": w.window_id, "start_ms": w.start_ms, "end_ms": w.end_ms,
                    "external_source_keys": list(w.external_source_keys),
                    "outcome": "SPEECH_CANDIDATE_FOUND",
                    "segments": [{
                        "start_ms": w.start_ms + 100, "end_ms": w.start_ms + 900,
                        "text": "補完音声テスト",
                        "words": [{"start_ms": w.start_ms + 100, "end_ms": w.start_ms + 900, "text": "補完音声テスト"}],
                    }],
                } for w in recovery_plan.windows],
            }
        _smoke_outside_runner.targeted_outside_span = _smoke_outside_span
        result = run_v2d_pipeline(
            _plan(True), invoke=invoke, hermes_settings=settings,
            staging_root=staging, output_directory=output, claim_token=1,
            targeted_runner=_smoke_outside_runner,
        )
        require(result.state == "CLEAN_SRT_READY", "CONNECTED_PIPELINE_READY")
        require(result.master is not None and len(result.master.cues) > 0, "JA_MASTER_MATERIALIZED")
        require(any(label == "v2d-targeted-final-review" for label, _ in invoke.calls), "TARGETED_REVIEW_REUSED")
        require(all(not reuse for _, reuse in invoke.calls), "SYNTHETIC_FIRST_EXECUTION")
        files = {name: (output / name).read_bytes() for name in (
            "ja-master-v1.json", "clean-ja-v1.srt", "clean-ko-v1.srt", "v2d-proof-v1.json"
        )}
        require(stat.S_IMODE(output.stat().st_mode) == 0o700, "PRIVATE_OUTPUT_DIRECTORY_MODE")
        require(all(stat.S_IMODE((output / name).stat().st_mode) == 0o600 for name in files),
                "PRIVATE_OUTPUT_FILE_MODES")
        ja = parse_subtitle_bytes(files["clean-ja-v1.srt"], "srt")
        ko = parse_subtitle_bytes(files["clean-ko-v1.srt"], "srt")
        require(len(ja.cues) == len(ko.cues) == result.review.final.cues.__len__(), "JA_KO_OUTPUT_STRUCTURE")
        require(ja.cues[0].text == "修正日本語" and ko.cues[0].text == "수정 한국어", "TARGETED_REPAIR_APPLIED")
        require(len(result.review.targeted_cue_ids) > 0, "TRIAGE_SUSPECTS_SELECTED")
        from fractions import Fraction
        fractional_master = replace(
            result.master,
            cues=(replace(result.master.cues[0], start_ms=Fraction(1, 10), end_ms=Fraction(4, 10)),)
                 + result.master.cues[1:],
        )
        expect_raises(V2DError, lambda: _materialized_cues(
            fractional_master, result.translation, result.review
        ), "ZERO_LENGTH_AFTER_FINAL_ROUNDING_REJECTED")
        expect_raises(V2DError, lambda: run_v2d_pipeline(
            _plan(True), invoke=OfflineInvoke(), hermes_settings=settings,
            staging_root=staging, output_directory=output, claim_token=1,
        ), "EXISTING_OUTPUT_COLLISION")

    # ASR-first route without any external JA remains usable.
    with tempfile.TemporaryDirectory(prefix="s11-v2d-asr-only-") as tmp:
        base = Path(tmp)
        result = run_v2d_pipeline(
            _plan(False), invoke=OfflineInvoke(), hermes_settings=settings,
            staging_root=_private_subdir(base, "staging"),
            output_directory=_private_subdir(base, "output"), claim_token=2,
        )
        require(result.state == "CLEAN_SRT_READY", "ASR_ONLY_ROUTE_READY")
        require(result.master.review_set.external_ja_sha256 is None, "NO_EXTERNAL_SOURCE_CLAIMED")

    # Rejected alignment remains an explicit ASR-first route; unprojected JA is
    # preserved in the decision ledger but is not assigned invented timing.
    from teddy_discovery_stage11_ja_master import ROUTE_EXTERNAL_ALIGNMENT_REJECTED
    with tempfile.TemporaryDirectory(prefix="s11-v2d-rejected-alignment-") as tmp:
        base = Path(tmp)
        bundle = _bundle(payload=_external_payload())
        accepted_application, _ = _accepted_application(bundle)
        rejected = decide_alignment_acceptance(
            accepted_application.alignment,
            AlignmentAcceptancePolicy(3, 3, 1.0, 1.0, 1_000, 1.1, 1.2),
        )
        require(rejected.verdict == REJECT_EXTERNAL, "REJECTED_ALIGNMENT_FIXTURE")
        application = apply_alignment_acceptance(bundle, rejected)
        plan = build_utterance_review_plan(
            build_ja_master_review_set(bundle, alignment_application=application)
        )
        rejected_invoke = OfflineInvoke(needs_audio_evidence=True)
        rejected_runner = OfflineTargetedRunner(bundle.asr_result.runtime_identity)
        result = run_v2d_pipeline(
            plan, invoke=rejected_invoke, hermes_settings=settings,
            staging_root=_private_subdir(base, "staging"),
            output_directory=_private_subdir(base, "output"), claim_token=7,
            targeted_runner=rejected_runner,
        )
        require(result.state == "CLEAN_SRT_READY", "REJECTED_ALIGNMENT_ASR_FIRST_READY")
        require(result.master.review_set.route == ROUTE_EXTERNAL_ALIGNMENT_REJECTED, "REJECTED_ROUTE_RETAINED")
        require(rejected_runner.calls == 1 and result.master.targeted_evidence_sha256 is not None,
                "REJECTED_ALIGNMENT_TARGETED_ASR_CONNECTED")
        require(all(ref.source == "asr_segment" for cue in result.master.cues
                    for ref in cue.source_references), "UNALIGNED_EXTERNAL_JA_NOT_MATERIALIZED")

    # UNCERTAIN is preserved as HOLD and cannot run translation or emit files.
    with tempfile.TemporaryDirectory(prefix="s11-v2d-hold-") as tmp:
        base = Path(tmp)
        invoke = OfflineInvoke(uncertain=True)
        output = _private_subdir(base, "output")
        result = run_v2d_pipeline(
            _plan(False), invoke=invoke, hermes_settings=settings,
            staging_root=_private_subdir(base, "staging"), output_directory=output,
            claim_token=3,
        )
        require(result.state == "HOLD" and result.reason_code == "JA_MASTER_UNRESOLVED", "UNCERTAINTY_HOLDS")
        require(not any(output.iterdir()), "HOLD_HAS_NO_OUTPUT")
        require(not any(label == "whole-title" for label, _ in invoke.calls), "HOLD_BEFORE_TRANSLATION")

    # Without an injected source-bound targeted adapter, an audio request
    # remains a HOLD and never emits an SRT.
    with tempfile.TemporaryDirectory(prefix="s11-v2d-audio-hold-") as tmp:
        base = Path(tmp)
        output = _private_subdir(base, "output")
        result = run_v2d_pipeline(
            _plan(False), invoke=OfflineInvoke(needs_audio_evidence=True),
            hermes_settings=settings, staging_root=_private_subdir(base, "staging"),
            output_directory=output, claim_token=8,
        )
        require(result.state == "HOLD" and result.reason_code ==
                "TARGETED_ASR_ADAPTER_UNAVAILABLE", "TARGETED_ASR_NEEDS_HOLD")
        require(not any(output.iterdir()), "TARGETED_ASR_HOLD_NO_SRT")

    # ASR-only target route: one synthetic additional-evidence execution is
    # validated by the existing controller artifact validator/projection,
    # re-adjudicated, included in a new translator generation, reviewed, and
    # materialized into private JA/KO SRTs.
    with tempfile.TemporaryDirectory(prefix="s11-v2d-targeted-") as tmp:
        base = Path(tmp)
        staging = _private_subdir(base, "staging")
        output = _private_subdir(base, "output")
        plan = _plan(False)
        invoke = OfflineInvoke(needs_audio_evidence=True)
        asr_result = plan.review_set._source_bundle.asr_result
        targeted_runner = OfflineTargetedRunner(asr_result.runtime_identity)
        requested = run_v2d_pipeline(
            plan, invoke=invoke, hermes_settings=settings,
            staging_root=staging, output_directory=output, claim_token=11,
            targeted_runner=targeted_runner,
        )
        require(requested.state == "CLEAN_SRT_READY", "TARGETED_ASR_CONNECTED_PIPELINE_READY")
        require(targeted_runner.calls == 1, "TARGETED_ASR_REQUESTED_ONCE")
        require(requested.master.targeted_evidence_sha256 is not None,
                "TARGETED_EVIDENCE_BOUND_TO_MASTER_ARTIFACT")
        require(any(label == "ja-master-targeted-readjudication" for label, _ in invoke.calls),
                "TARGETED_GROUP_READJUDICATED")
        require(len(invoke.translation_generations) == 2
                and ":targeted-" not in invoke.translation_generations[0]
                and ":targeted-" in invoke.translation_generations[1],
                "TARGETED_EVIDENCE_GETS_DISTINCT_TRANSLATION_SESSION")
        targeted_proof = json.loads((output / "v2d-proof-v1.json").read_bytes())
        require(targeted_proof["targeted_asr_artifact_sha256"] is not None,
                "TARGETED_ARTIFACT_SHA_IN_FINAL_PROOF")
        require(targeted_proof["targeted_readjudicated_group_count"] > 0,
                "TARGETED_GROUP_COUNT_IN_FINAL_PROOF")
        updated_packages = [
            cue for cue in requested.package.cues
            if "合成追加音声根拠" in (cue.stt_ja or "")
        ]
        require(updated_packages, "TARGETED_ASR_REACHES_TRANSLATION_INPUT")
        require(any(label == "whole-title" for label, _ in invoke.calls)
                and any(label == "v2d-triage" for label, _ in invoke.calls),
                "UPDATED_TRANSLATION_AND_REVIEW_RAN")
        require(set(json.dumps(item, sort_keys=True) for item in invoke.settings_seen)
                == {json.dumps(settings.evidence(), sort_keys=True)},
                "INCOMPLETE_STAGES_SHARE_ONE_PINNED_PROFILE")
        ja = parse_subtitle_bytes((output / "clean-ja-v1.srt").read_bytes(), "srt")
        ko = parse_subtitle_bytes((output / "clean-ko-v1.srt").read_bytes(), "srt")
        require(len(ja.cues) == len(ko.cues) > 0, "TARGETED_JA_KO_SRT_STRUCTURE")
        require(ja.cues[0].text == "補足確認済み日本語", "TARGETED_READJUDICATION_MATERIALIZED")
        require(all(stat.S_IMODE(path.stat().st_mode) == 0o600
                    for path in (output / "clean-ja-v1.srt", output / "clean-ko-v1.srt",
                                 output / "v2d-proof-v1.json")),
                "TARGETED_OUTPUTS_PRIVATE")

        # A second offline resume consumes the validated private artifact and
        # linkage only; it must not request another ASR execution.
        resume_output = _private_subdir(base, "resume-output")
        resumed = run_v2d_pipeline(
            plan, invoke=OfflineInvoke(needs_audio_evidence=True),
            hermes_settings=settings, staging_root=staging,
            output_directory=resume_output, claim_token=11, reuse_only=True,
            targeted_runner=InvalidOfflineTargetedRunner(asr_result.runtime_identity),
        )
        require(resumed.state == "CLEAN_SRT_READY", "TARGETED_ARTIFACT_RESUMED")

        artifact_path = next(staging.glob("targeted-second-evidence/*/targeted-second-evidence-v1.json"))
        tampered = json.loads(artifact_path.read_bytes())
        tampered["baseline_asr_artifact_sha256"] = "0" * 64
        artifact_path.write_text(json.dumps(tampered, ensure_ascii=False), encoding="utf-8")
        corrupt_output = _private_subdir(base, "corrupt-output")
        never_run = InvalidOfflineTargetedRunner(asr_result.runtime_identity)
        corrupt_resume = run_v2d_pipeline(
            plan, invoke=OfflineInvoke(needs_audio_evidence=True),
            hermes_settings=settings, staging_root=staging,
            output_directory=corrupt_output, claim_token=11, reuse_only=True,
            targeted_runner=never_run,
        )
        require(corrupt_resume.state == "HOLD" and corrupt_resume.reason_code ==
                "TARGETED_ASR_ARTIFACT_OR_LINKAGE_INVALID",
                "TAMPERED_TARGETED_ARTIFACT_HOLDS")
        require(never_run.calls == 0 and not any(corrupt_output.iterdir()),
                "TAMPERED_ARTIFACT_NO_RETRY_OR_OUTPUT")

    # Invalid runner output and an external-only cue cannot be converted into
    # a synthetic ASR index/time; both stop before final files.
    with tempfile.TemporaryDirectory(prefix="s11-v2d-targeted-invalid-") as tmp:
        base = Path(tmp)
        plan = _plan(False)
        invoke = OfflineInvoke(needs_audio_evidence=True)
        output = _private_subdir(base, "output")
        invalid_runner = InvalidOfflineTargetedRunner(plan.review_set._source_bundle.asr_result.runtime_identity)
        result = run_v2d_pipeline(
            plan, invoke=invoke, hermes_settings=settings,
            staging_root=_private_subdir(base, "staging"), output_directory=output,
            claim_token=12, targeted_runner=invalid_runner,
        )
        require(result.state == "HOLD" and result.reason_code ==
                "TARGETED_ASR_ADAPTER_VALIDATION_OR_PERSISTENCE_FAILED",
                "INVALID_TARGETED_EXECUTION_HOLDS")
        require(not any(output.iterdir()), "INVALID_TARGETED_EXECUTION_NO_OUTPUT")

    with tempfile.TemporaryDirectory(prefix="s11-v2d-targeted-external-only-") as tmp:
        base = Path(tmp)
        plan = _plan(True)
        invoke = OfflineInvoke(needs_audio_evidence=True, reject_asr=True)
        output = _private_subdir(base, "output")
        runner = OfflineTargetedRunner(plan.review_set._source_bundle.asr_result.runtime_identity)
        runner.targeted_outside_span = _smoke_outside_span
        result = run_v2d_pipeline(
            plan, invoke=invoke, hermes_settings=settings,
            staging_root=_private_subdir(base, "staging"), output_directory=output,
            claim_token=13, targeted_runner=runner,
        )
        require(result.state == "HOLD" and result.reason_code ==
                "TARGETED_ASR_NO_SOURCE_BOUND_BASELINE_SEGMENT",
                "EXTERNAL_ONLY_NO_FAKE_ASR_REFERENCE")
        require(runner.calls == 0 and not any(output.iterdir()),
                "EXTERNAL_ONLY_HOLD_BEFORE_ASR_AND_OUTPUT")

    # Coverage omission is rejected even when the response object is otherwise well typed.
    plan = _plan(False)
    group = plan.groups[0]
    fingerprint = _source_fingerprint(plan)
    bad_group = GroupAdjudication(
        group.group_id,
        (),
        (),
        (),
    )
    expect_raises(V2DError, lambda: validate_adjudication(
        plan, V2DAdjudication(fingerprint, (bad_group,) + tuple(
            GroupAdjudication(item.group_id, (), (), ()) for item in plan.groups[1:]
        ))
    ), "MISSING_CANDIDATE_AND_SOURCE_DECISION_REJECTED")

    # A single ASR segment may split only along its complete existing word
    # references; resulting times stay exact Fractions from those words.
    plan = _plan(True)
    split_group = next(
        group for group in plan.groups
        if group.source_cardinality == "ASR_TO_JA_ONE_TO_MANY"
        and any(len(member.word_references) >= 2 for member in group.members
                if member.source_reference.source == "asr_segment")
    )
    asr_member = next(member for member in split_group.members
                      if member.source_reference.source == "asr_segment"
                      and len(member.word_references) >= 2)
    split_key = asr_member.source_reference.key
    midpoint = len(asr_member.word_references) // 2
    split_decisions = []
    split_groups = []
    for group in plan.groups:
        candidates = tuple(CandidateDecision(cid, "ACCEPTED", "synthetic relation reviewed")
                           for cid in group.candidate_ids)
        if group.group_id == split_group.group_id:
            sources = tuple(SourceDecision(
                member.source_reference.key,
                "ACCEPTED" if member.source_reference.key == split_key else "REJECTED",
                "synthetic split source decision",
            ) for member in group.members)
            outputs = (
                MasterOutputProposal("前半の日本語", (SourceSpan(split_key, 0, midpoint),), "word-bound split"),
                MasterOutputProposal("後半の日本語", (
                    SourceSpan(split_key, midpoint, len(asr_member.word_references)),
                ), "word-bound split"),
            )
        else:
            sources = tuple(SourceDecision(
                member.source_reference.key,
                "ACCEPTED" if member.source_reference.aligned_start_ms is not None else "REJECTED",
                "synthetic source decision",
            ) for member in group.members)
            outputs = tuple(MasterOutputProposal(
                member.text, (SourceSpan(member.source_reference.key),), "synthetic source output"
            ) for member in group.members
                if member.source_reference.aligned_start_ms is not None)
        split_groups.append(GroupAdjudication(group.group_id, candidates, sources, outputs))
    split_master = materialize_ja_master(
        plan, V2DAdjudication(_source_fingerprint(plan), tuple(split_groups))
    )
    split_cues = [cue for cue in split_master.cues
                  if any(ref.key == split_key for ref in cue.source_references)]
    require(len(split_cues) == 2, "ASR_WORD_SEGMENT_SPLIT")
    require(split_cues[0].start_ms == asr_member.word_references[0].start_ms
            and split_cues[1].end_ms == asr_member.word_references[-1].end_ms,
            "ASR_SPLIT_EXACT_WORD_TIMES")

    # Changed semantic master content gets a distinct existing translator session.
    plan = _plan(False)
    temp = tempfile.TemporaryDirectory(prefix="s11-v2d-identity-")
    try:
        base = Path(temp.name)
        staging = _private_subdir(base, "staging")
        invoke = OfflineInvoke()
        first_run = run_v2d_pipeline(
            plan, invoke=invoke, hermes_settings=settings, staging_root=staging,
            output_directory=_private_subdir(base, "output"), claim_token=4,
        )
        require(first_run.state == "CLEAN_SRT_READY", "IDENTITY_BASELINE_READY")
        old_group = first_run.master.adjudication.groups[0]
        changed_output = replace(old_group.outputs[0], japanese_text="異なるマスター")
        changed_group = replace(old_group, outputs=(changed_output,) + old_group.outputs[1:])
        changed_adjudication = replace(
            first_run.master.adjudication,
            groups=(changed_group,) + first_run.master.adjudication.groups[1:],
        )
        changed_master = materialize_ja_master(first_run.master.utterance_plan, changed_adjudication)
        first_package = _build_translation_package(first_run.master, 5)
        second_package = _build_translation_package(changed_master, 5)
        require(first_package.generation_key != second_package.generation_key, "CHANGED_INPUT_NEW_GENERATION")
        require(derive_stateful_session_id(first_package.dvd_id, first_package.generation_key, first_package.claim_token)
                != derive_stateful_session_id(second_package.dvd_id, second_package.generation_key, second_package.claim_token),
                "CHANGED_INPUT_NEW_SESSION")
    finally:
        temp.cleanup()

    # A receipt-validated whole-title response can reconstruct a missing local
    # result cache without another model call. The callback stands in for the
    # existing NativeNormalFirstPass receipt validator; it refuses live mode.
    with tempfile.TemporaryDirectory(prefix="s11-v2d-resume-cache-") as tmp:
        base = Path(tmp)
        staging = _private_subdir(base, "staging")
        first_invoke = OfflineInvoke()
        first_run = run_v2d_pipeline(
            _plan(False), invoke=first_invoke, hermes_settings=settings,
            staging_root=staging, output_directory=_private_subdir(base, "output-1"),
            claim_token=9,
        )
        require(first_run.state == "CLEAN_SRT_READY", "RESUME_CACHE_BASELINE_READY")
        package = _build_translation_package(first_run.master, 9)
        stage = staging / stateful_session_id_for_package(package)
        result_path = stage / "stage11-semantic-result.json"
        expected_raw = result_path.read_bytes()
        result_path.unlink()

        class ReceiptReplayOnly:
            def __init__(self):
                self.calls = []

            def __call__(self, prompt, directory, label, validator, *, hermes_settings, reuse_only=False):
                self.calls.append((label, reuse_only))
                require(reuse_only, "RESUME_CACHE_LIVE_CALL_FORBIDDEN")
                return first_invoke(
                    prompt, directory, label, validator,
                    hermes_settings=hermes_settings, reuse_only=True,
                )

        replay = ReceiptReplayOnly()
        _, resumed = translate_ja_master(
            first_run.master, invoke=replay, hermes_settings=settings,
            staging_root=staging, claim_token=9, reuse_only=True,
        )
        require(result_path.read_bytes() == expected_raw, "VERIFIED_RESULT_CACHE_REBUILT")
        require(resumed.session_id == stateful_session_id_for_package(package),
                "RESUME_SESSION_PRESERVED")
        require(replay.calls == [("whole-title", True)], "RESUME_USED_VALIDATED_EXECUTOR_ONLY")

    # The existing whole-title -> fixed-64 fallback path is exercised with a stub failure.
    with tempfile.TemporaryDirectory(prefix="s11-v2d-parts-") as tmp:
        base = Path(tmp)
        staging = _private_subdir(base, "staging")
        plan = _plan(False)
        invoke = OfflineInvoke(whole_fails=True)
        result = run_v2d_pipeline(
            plan, invoke=invoke, hermes_settings=settings,
            staging_root=staging, output_directory=_private_subdir(base, "output"), claim_token=6,
        )
        require(result.state == "CLEAN_SRT_READY", "FIXED_64_FALLBACK_READY")
        require(any(label.startswith("part-") for label, _ in invoke.calls), "FIXED_64_PART_EXECUTED")
    print("S11_V2D_OFFLINE_SMOKE=PASS")


if __name__ == "__main__":
    main()
