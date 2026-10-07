"""Offline smoke for the thin generic Stage11 TITLE controller.

Only temporary directories and injected synthetic dependencies are used.  No
Whisper, Hermes, VM122, database, NAS, Jellyfin, or publisher call is made.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
from unittest.mock import patch

from teddy_discovery_alignment_acceptance import (
    ACCEPT_HYBRID,
    REJECT_EXTERNAL,
    UNRESOLVED,
    AlignmentAcceptanceValidationError,
)
from teddy_discovery_alignment_application import apply_alignment_acceptance
from teddy_discovery_asr import ASRSegment
from teddy_discovery_asr_audio import ASRAudioUnsafeTimelineError
from teddy_discovery_asr_artifact import persist_asr_result, serialize_asr_result
from teddy_discovery_asr_transcriber import FullTitleASRNoSpeechError
from teddy_discovery_asr_source_quality import classify_asr_result_source_quality
from teddy_discovery_hermes_v2 import HermesV2CueOutput
from teddy_discovery_hybrid_evidence import (
    ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
    HybridAlignmentProvenance,
    HybridEvidenceBundle,
    NEIGHBOR_SOURCE_ASR_SEGMENT,
    NEIGHBOR_SOURCE_EXTERNAL_EN,
)
from teddy_discovery_stateful_asr_quality_review import (
    ASRQualityReviewRequest,
    asr_quality_review_request_sha256,
)
from teddy_discovery_stateful_quality_review import (
    KEEP,
    QualityReviewRequest,
    QualityReviewResult,
    QualityReviewResultCue,
    QualityReviewError,
    build_review_request,
    review_request_sha256,
)
from teddy_discovery_stateful_translator import (
    StatefulSubtitleResult,
    _atomic_private_write,
    create_stateful_staging_directory,
    serialize_stateful_result,
    stateful_session_id_for_package,
    stateful_staging_paths,
    write_stateful_authoritative_input,
    write_stateful_input,
)
from teddy_discovery_stateful_policy import (
    STATEFUL_SEMANTIC_POLICY_ID_16,
    STATEFUL_SEMANTIC_POLICY_ID_64,
    STATEFUL_SEMANTIC_POLICY_ID_128,
)
from teddy_discovery_subtitle_external import (
    ExternalSubtitleTransportError,
    ExternalSubtitleValidationError,
    SubtitleCatDetailError,
)
from teddy_discovery_subtitle_v2_orchestrator import (
    SubtitleV2OrchestratorValidationError,
    V2_ROUTE_ASR_ONLY,
    V2_ROUTE_HYBRID,
)
from teddy_discovery_subtitle_v2_pipeline import SubtitleV2PipelineError
from teddy_discovery_subtitlecat_discovery import (
    SubtitleCatSearchError,
    SubtitleCatSearchTransportError,
)
from teddy_discovery_targeted_asr_window import (
    STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1,
)
from teddy_discovery_targeted_second_evidence import (
    TargetedSecondEvidenceWindowResult,
    bind_targeted_second_evidence,
    build_targeted_second_evidence_plan_with_policy,
    requires_hybrid_targeted_projection,
)
from teddy_discovery_targeted_second_evidence_artifact import (
    TargetedSecondEvidenceArtifactValidationError,
    parse_targeted_second_evidence_artifact_bytes,
    persist_targeted_second_evidence,
)
from teddy_discovery_targeted_second_evidence_runner import (
    TargetedSecondEvidenceExecution,
)
import teddy_discovery_stage11_controller as controller
import teddy_discovery_subtitle_v2_pipeline_smoke as fixture
from teddy_discovery_stateful_hybrid_smoke import semantic_result
from teddy_discovery_subtitle_source_quality import classify_source_document


TITLE = fixture.DVD_ID


def _holding(asr_result):
    snapshot = asr_result.source_snapshot
    return {
        "holding_id": 1,
        "storage_root": "jav",
        "relative_path": snapshot.canonical_video_relative,
        "dvd_id": snapshot.dvd_id,
        "parse_status": "MATCHED",
        "parse_method": "smoke",
        "size_bytes": snapshot.source_size,
        "mtime_ns": snapshot.source_mtime_ns,
        "present": 1,
    }


def _require_asr():
    base = fixture.asr_result()
    return replace(
        base,
        segments=(
            ASRSegment(1_000, 1_500, "一旦、一旦、一旦、一旦"),
            base.segments[1],
            base.segments[2],
        ),
    )


def _nonresidual_require_asr():
    base = fixture.asr_result()
    return replace(
        base,
        segments=base.segments + (
            ASRSegment(4_000, 4_500, "一旦、一旦、一旦、一旦"),
        ),
    )


def _unprojectable_require_asr():
    base = _nonresidual_require_asr()
    return replace(
        base,
        segments=base.segments[:-1] + (
            ASRSegment(20_000, 20_500, "一旦、一旦、一旦、一旦"),
        ),
    )


def _partially_projectable_require_asr():
    base = _nonresidual_require_asr()
    return replace(
        base,
        segments=base.segments + (
            ASRSegment(30_000, 30_500, "一旦、一旦、一旦、一旦"),
        ),
    )


def _nonresidual_hybrid_application(asr_result):
    ja_payload = fixture.external_payload(
        "https://source.example.test/ja-nonresidual.srt",
        "ja",
        (
            (900, 1_400, "日本語一"),
            (1_500, 2_400, "日本語二"),
            (1_900, 2_400, "日本語三"),
            (2_900, 3_400, "日本語四"),
            (3_900, 4_400, "日本語五"),
        ),
    )
    en_payload = fixture.external_payload(
        "https://source.example.test/en-nonresidual.srt",
        "en",
        (
            (900, 1_400, "support one"),
            (1_500, 2_400, "support two"),
            (1_900, 2_400, "support three"),
            (2_900, 3_400, "support four"),
            (3_900, 4_400, "support five"),
        ),
    )
    bundle = HybridEvidenceBundle.from_external_ja_and_asr(
        dvd_id=TITLE,
        external_ja_payload=ja_payload,
        external_ja_document=ja_payload.parse(),
        asr_result=asr_result,
        alignment=HybridAlignmentProvenance(
            ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
            "stage11_controller_smoke_nonresidual",
            0.8,
        ),
        external_en_payload=en_payload,
        external_en_document=en_payload.parse(),
        before_context=(
            fixture.HybridNeighborReference(NEIGHBOR_SOURCE_ASR_SEGMENT, 0),
        ),
        after_context=(
            fixture.HybridNeighborReference(NEIGHBOR_SOURCE_EXTERNAL_EN, 0),
        ),
    )
    return _application(ACCEPT_HYBRID, asr_result, bundle=bundle)


def _application(verdict: str, asr_result, *, bundle=None):
    if verdict == ACCEPT_HYBRID:
        original = fixture.accepted_hybrid_route().alignment_application
    elif verdict == REJECT_EXTERNAL:
        original = fixture.rejected_asr_route().alignment_application
    elif verdict == UNRESOLVED:
        original = fixture.unresolved_route().alignment_application
    else:
        raise AssertionError("unsupported smoke verdict")
    bundle = replace(
        original.bundle if bundle is None else bundle,
        asr_result=asr_result,
    )
    return apply_alignment_acceptance(
        bundle,
        original.decision,
        alignment=original.alignment,
    )


def _targeted_execution(asr_result, decisions, *, statuses=None):
    plan = build_targeted_second_evidence_plan_with_policy(
        asr_result,
        decisions,
        policy=STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1,
    )
    results = []
    for ordinal, window in enumerate(plan.windows):
        source = asr_result.segments[window.source_indices[0]]
        start_ms = source.start_ms
        end_ms = min(source.end_ms, start_ms + 100)
        if end_ms <= start_ms:
            raise AssertionError("synthetic targeted window has no duration")
        status = statuses[ordinal] if statuses is not None else "PRESENT"
        segments = (() if status == "EMPTY" else (ASRSegment(
            start_ms, end_ms,
            "一旦、" * 64 if status == "NOISY" else "補助証拠"),))
        if status == "NOISY_MIXED":
            segments = (ASRSegment(start_ms, end_ms, "補助証拠"),
                        ASRSegment(source.end_ms + 100, source.end_ms + 200, "一旦、" * 64))
        results.append(
            TargetedSecondEvidenceWindowResult(
                source_snapshot=plan.source_snapshot,
                window_id=window.window_id,
                window_start_ms=window.start_ms,
                window_end_ms=window.end_ms,
                segments=segments,
                plan_binding_sha256=plan.binding_sha256,
            )
        )
    bindings = bind_targeted_second_evidence(plan, tuple(results))
    return TargetedSecondEvidenceExecution(
        plan=plan,
        policy_version=(
            STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1.version
        ),
        bindings=bindings,
    )


class FakeRuntime:
    def __init__(
        self,
        asr_result,
        external=None,
        *,
        stage_first_pass_artifacts=True,
    ):
        self.asr_result = asr_result
        self.external = external
        self.stage_first_pass_artifacts = stage_first_pass_artifacts
        self.baseline_calls = 0
        self.external_calls = 0
        self.targeted_calls = 0
        self.first_pass_calls = 0
        self.first_pass_routes = []
        self.asr_review_calls = 0
        self.hybrid_review_calls = 0
        self.staging_roots = []
        self.last_packages = {}
        self.last_asr_request = None
        self.last_hybrid_request = None

    def holding(self, title):
        assert title == TITLE
        return _holding(self.asr_result)

    def baseline(self, canonical_video):
        self.baseline_calls += 1
        assert canonical_video.dvd_id == TITLE
        return self.asr_result

    def external_attempt(self, canonical_video, asr_result):
        self.external_calls += 1
        assert canonical_video.dvd_id == TITLE
        assert asr_result == self.asr_result
        if isinstance(self.external, BaseException):
            raise self.external
        if self.external in {ACCEPT_HYBRID, REJECT_EXTERNAL, UNRESOLVED}:
            return _application(self.external, asr_result)
        return None

    def targeted(self, asr_result, decisions):
        self.targeted_calls += 1
        return _targeted_execution(asr_result, decisions)

    def first_pass(
        self,
        package,
        *,
        route,
        staging_root,
        semantic_policy=None,
        boundary_evidence=None,
    ):
        self.first_pass_calls += 1
        self.first_pass_routes.append(route)
        self.staging_roots.append(staging_root)
        if semantic_policy is not None:
            self.first_pass_policies = getattr(self, "first_pass_policies", [])
            self.first_pass_policies.append(semantic_policy.policy_id)
        assert route in {V2_ROUTE_ASR_ONLY, V2_ROUTE_HYBRID}
        self.last_packages[route] = package
        if boundary_evidence is not None:
            from teddy_discovery_stateful_boundary import validate_stateful_boundary_evidence
            validate_stateful_boundary_evidence(boundary_evidence, package)
        result = StatefulSubtitleResult(
            schema_version=package.schema_version,
            dvd_id=package.dvd_id,
            generation_key=package.generation_key,
            claim_token=package.claim_token,
            session_id=stateful_session_id_for_package(package),
            cues=tuple(
                HermesV2CueOutput(cue.cue_id, None, "번역 " + cue.cue_id)
                for cue in package.cues
            ),
        )
        if self.stage_first_pass_artifacts:
            session = stateful_session_id_for_package(package)
            directory = Path(staging_root) / session
            if not directory.exists():
                create_stateful_staging_directory(staging_root, session)
            write_stateful_authoritative_input(directory, package)
            write_stateful_input(directory, package)
            if boundary_evidence is not None:
                from teddy_discovery_stateful_boundary import stage_stateful_boundary_evidence
                stage_stateful_boundary_evidence(directory, boundary_evidence, package)
            _atomic_private_write(
                stateful_staging_paths(directory).result_path,
                serialize_stateful_result(result),
            )
        return result

    @staticmethod
    def _review_result(request, request_sha):
        result = QualityReviewResult(
            schema_version=request.schema_version,
            request_sha256=request_sha,
            cues=tuple(
                QualityReviewResultCue(
                    cue.cue_id,
                    KEEP,
                    "DIALOGUE",
                    "Synthetic evidence preserves this cue.",
                    None,
                    None,
                )
                for cue in request.cues
            ),
        )
        return replace(
            result,
            source_translation_session_id=request.source_translation_session_id,
            review_execution_session_id="synthetic-review-execution-session",
        )

    def asr_review(self, request, *, staging_root):
        self.asr_review_calls += 1
        self.staging_roots.append(staging_root)
        assert type(request) is ASRQualityReviewRequest
        self.last_asr_request = request
        return self._review_result(
            request,
            asr_quality_review_request_sha256(request),
        )

    def hybrid_review(self, request, *, staging_root):
        self.hybrid_review_calls += 1
        self.staging_roots.append(staging_root)
        assert type(request) is QualityReviewRequest
        self.last_hybrid_request = request
        return self._review_result(request, review_request_sha256(request))


def _roots(base: Path):
    artifact_root = base / "artifacts"
    staging_root = base / "stateful"
    artifact_root.mkdir(mode=0o700)
    staging_root.mkdir(mode=0o700)
    return artifact_root, staging_root


def _run(
    artifact_root,
    staging_root,
    runtime,
    *,
    targeted_runner=True,
    semantic_policy=None,
):
    kwargs = dict(
        artifact_root=artifact_root,
        stateful_staging_root=staging_root,
        claim_token=7,
        baseline_transcriber=runtime.baseline,
        external_ja_attempt=runtime.external_attempt,
        first_pass_runner=runtime.first_pass,
        asr_review_runner=runtime.asr_review,
        hybrid_review_runner=runtime.hybrid_review,
        targeted_runner=runtime.targeted if targeted_runner else None,
        holding_resolver=runtime.holding,
    )
    if semantic_policy is not None:
        kwargs["semantic_policy"] = semantic_policy
    return controller.run_one_title_stage11(TITLE, **kwargs)


def _prepopulate_baseline(artifact_root: Path, asr_result):
    title_dir = artifact_root / TITLE
    title_dir.mkdir(mode=0o700)
    path = title_dir / controller.BASELINE_ASR_FILENAME
    persist_asr_result(path, asr_result)
    return path


def _prepopulate_targeted(artifact_root: Path, asr_result, *, baseline_sha=None, statuses=None):
    decisions = classify_asr_result_source_quality(asr_result)
    execution = _targeted_execution(asr_result, decisions, statuses=statuses)
    path = artifact_root / TITLE / controller.TARGETED_SECOND_EVIDENCE_FILENAME
    persist_targeted_second_evidence(
        path,
        execution,
        baseline_asr_artifact_sha256=(
            baseline_sha
            if baseline_sha is not None
            else hashlib.sha256(serialize_asr_result(asr_result)).hexdigest()
        ),
        runtime_identity=asr_result.runtime_identity,
        engine_version=asr_result.engine_version,
    )
    return path


def main():
    passed = 0

    def check(name, callback):
        nonlocal passed
        assert callback(), name
        passed += 1
        print("PASS " + name)

    def reject(name, exception_type, callback):
        def rejected():
            try:
                callback()
            except exception_type:
                return True
            return False

        check(name, rejected)

    # Canonical DVD-ID only.
    with tempfile.TemporaryDirectory(prefix="stage11-controller-title-") as raw:
        artifact_root, staging_root = _roots(Path(raw))
        runtime = FakeRuntime(fixture.asr_result())
        reject(
            "canonical DVD-ID spelling enforced",
            controller.Stage11ControllerValidationError,
            lambda: controller.run_one_title_stage11(
                TITLE.lower(),
                artifact_root=artifact_root,
                stateful_staging_root=staging_root,
                claim_token=7,
                baseline_transcriber=runtime.baseline,
                external_ja_attempt=runtime.external_attempt,
                first_pass_runner=runtime.first_pass,
                asr_review_runner=runtime.asr_review,
                hybrid_review_runner=runtime.hybrid_review,
                holding_resolver=runtime.holding,
            ),
        )

    # A valid full-title no-speech outcome stops before external lookup.
    # The external subtitle's possible presence cannot bypass the baseline
    # ASR/alignment invariant; absence also yields no usable subtitle source.
    for external, label in ((None, "ABSENT"), (ACCEPT_HYBRID, "PRESENT")):
        with tempfile.TemporaryDirectory(
            prefix="stage11-controller-no-speech-" + label.lower() + "-"
        ) as raw:
            artifact_root, staging_root = _roots(Path(raw))
            runtime = FakeRuntime(fixture.asr_result(), external=external)

            def no_speech_baseline(_canonical_video):
                runtime.baseline_calls += 1
                raise FullTitleASRNoSpeechError(
                    "full-title ASR produced no speech segments"
                )

            runtime.baseline = no_speech_baseline
            try:
                _run(artifact_root, staging_root, runtime)
            except FullTitleASRNoSpeechError:
                pass
            else:
                raise AssertionError("NO_SPEECH_OUTCOME_MUST_PROPAGATE")
            check(
                "baseline no speech stops before external lookup " + label,
                lambda: runtime.baseline_calls == 1
                and runtime.external_calls == 0
                and runtime.targeted_calls == 0
                and not (
                    artifact_root
                    / TITLE
                    / controller.BASELINE_ASR_FILENAME
                ).exists()
                and not (
                    artifact_root
                    / TITLE
                    / controller.MECHANICAL_REPORT_FILENAME
                ).exists(),
            )

    # A deterministic unsafe baseline timeline also fails before baseline
    # persistence, external subtitle lookup/alignment, or artifact creation.
    with tempfile.TemporaryDirectory(
        prefix="stage11-controller-unsafe-timeline-"
    ) as raw:
        artifact_root, staging_root = _roots(Path(raw))
        runtime = FakeRuntime(fixture.asr_result(), external=ACCEPT_HYBRID)

        def unsafe_timeline_baseline(_canonical_video):
            runtime.baseline_calls += 1
            raise ASRAudioUnsafeTimelineError(
                "peak net sample-clock drift exceeds three decoded frames"
            )

        runtime.baseline = unsafe_timeline_baseline
        try:
            _run(artifact_root, staging_root, runtime)
        except ASRAudioUnsafeTimelineError:
            pass
        else:
            raise AssertionError("UNSAFE_TIMELINE_MUST_PROPAGATE")
        check(
            "unsafe baseline timeline stops before external lookup and artifacts",
            lambda: runtime.baseline_calls == 1
            and runtime.external_calls == 0
            and runtime.targeted_calls == 0
            and not (
                artifact_root / TITLE / controller.BASELINE_ASR_FILENAME
            ).exists()
            and not (
                artifact_root / TITLE / controller.CLEAN_SRT_FILENAME
            ).exists()
            and not (
                artifact_root / TITLE / controller.MECHANICAL_REPORT_FILENAME
            ).exists(),
        )

    # Existing baseline, no external candidate, REQUIRE=0, ASR-only full flow.
    with tempfile.TemporaryDirectory(prefix="stage11-controller-existing-") as raw:
        artifact_root, staging_root = _roots(Path(raw))
        asr_result = fixture.asr_result()
        baseline_path = _prepopulate_baseline(artifact_root, asr_result)
        runtime = FakeRuntime(asr_result)
        result = _run(
            artifact_root,
            staging_root,
            runtime,
            targeted_runner=False,
        )
        report = json.loads(result.report_path.read_text(encoding="utf-8"))
        translation_session_id = stateful_session_id_for_package(
            runtime.last_packages[V2_ROUTE_ASR_ONLY]
        )
        report_bytes = result.report_path.read_bytes()
        check(
            "durable report fingerprints session identity without raw value",
            lambda: set(report["translation_result_identity"])
            == {"session_id_sha256", "sha256"}
            and report["translation_result_identity"]["session_id_sha256"]
            == hashlib.sha256(translation_session_id.encode("utf-8")).hexdigest()
            and "session_id" not in report["translation_result_identity"]
            and translation_session_id.encode("utf-8") not in report_bytes,
        )
        check(
            "durable review identity contains fingerprints only",
            lambda: set(report["review_result_identity"])
            == {
                "request_sha256",
                "result_sha256",
                "source_translation_session_id_sha256",
                "review_execution_session_id_sha256",
            }
            and report["review_result_identity"][
                "source_translation_session_id_sha256"
            ]
            == hashlib.sha256(
                runtime.last_asr_request.source_translation_session_id.encode("utf-8")
            ).hexdigest()
            and report["review_result_identity"][
                "review_execution_session_id_sha256"
            ]
            == hashlib.sha256(
                b"synthetic-review-execution-session"
            ).hexdigest()
            and "source_translation_session_id" not in report["review_result_identity"]
            and "review_execution_session_id" not in report["review_result_identity"],
        )
        check(
            "baseline valid-existing reuse calls transcriber zero times",
            lambda: result.baseline_reused
            and runtime.baseline_calls == 0
            and report["baseline_artifact_path"] == str(baseline_path),
        )
        check(
            "no external candidate selects ASR-only",
            lambda: result.route == V2_ROUTE_ASR_ONLY
            and result.external_ja_outcome == "NO_CANDIDATE",
        )
        check(
            "REQUIRE zero skips targeted transport and artifact",
            lambda: runtime.targeted_calls == 0
            and result.targeted_reused is None
            and not (
                artifact_root
                / TITLE
                / controller.TARGETED_SECOND_EVIDENCE_FILENAME
            ).exists(),
        )
        check(
            "ASR-only first-pass review CLEAN route",
            lambda: runtime.first_pass_calls == 1
            and runtime.asr_review_calls == 1
            and runtime.hybrid_review_calls == 0
            and result.clean_path.is_file()
            and result.report_path.is_file(),
        )
        check(
            "explicit stateful staging root reaches native adapters",
            lambda: runtime.staging_roots
            and all(path == staging_root for path in runtime.staging_roots),
        )
        check(
            "omitted controller policy binds fixed64 package identity",
            lambda: runtime.last_packages[V2_ROUTE_ASR_ONLY].generation_key.endswith(
                "::stage11-policy=" + STATEFUL_SEMANTIC_POLICY_ID_64
            ),
        )
        legacy_result = _run(
            artifact_root,
            staging_root,
            runtime,
            targeted_runner=False,
            semantic_policy=STATEFUL_SEMANTIC_POLICY_ID_16,
        )
        check(
            "explicit legacy16 reuses validated completed artifact",
            lambda: legacy_result.clean_reused
            and legacy_result.report_reused
            and runtime.first_pass_calls == 1,
        )
        reject(
            "non-default policy cannot reuse title completion",
            controller.Stage11ControllerArtifactError,
            lambda: _run(
                artifact_root,
                staging_root,
                runtime,
                targeted_runner=False,
                semantic_policy=STATEFUL_SEMANTIC_POLICY_ID_128,
            ),
        )

    # Absent baseline is generated and persisted.
    with tempfile.TemporaryDirectory(prefix="stage11-controller-generate-") as raw:
        artifact_root, staging_root = _roots(Path(raw))
        runtime = FakeRuntime(fixture.asr_result())
        result = _run(artifact_root, staging_root, runtime, targeted_runner=False)
        check(
            "baseline absent generates and stores",
            lambda: not result.baseline_reused
            and runtime.baseline_calls == 1
            and (
                artifact_root / TITLE / controller.BASELINE_ASR_FILENAME
                ).is_file(),
        )

    # The production 128 candidate is opt-in and must bind its package before
    # the existing ASR/HYBRID review and CLEAN machinery sees it.
    with tempfile.TemporaryDirectory(prefix="stage11-controller-candidate-asr-") as raw:
        artifact_root, staging_root = _roots(Path(raw))
        runtime = FakeRuntime(fixture.asr_result())
        result = _run(
            artifact_root,
            staging_root,
            runtime,
            targeted_runner=False,
            semantic_policy=STATEFUL_SEMANTIC_POLICY_ID_128,
        )
        package = runtime.last_packages[V2_ROUTE_ASR_ONLY]
        check(
            "opt-in 128 ASR candidate binds identity before first pass",
            lambda: result.route == V2_ROUTE_ASR_ONLY
            and package.generation_key.endswith(
                "::stage11-policy=" + STATEFUL_SEMANTIC_POLICY_ID_128
            )
            and runtime.first_pass_policies == [STATEFUL_SEMANTIC_POLICY_ID_128],
        )

    with tempfile.TemporaryDirectory(prefix="stage11-controller-candidate-hybrid-") as raw:
        artifact_root, staging_root = _roots(Path(raw))
        runtime = FakeRuntime(fixture.asr_result(), ACCEPT_HYBRID)
        result = _run(
            artifact_root,
            staging_root,
            runtime,
            targeted_runner=False,
            semantic_policy=STATEFUL_SEMANTIC_POLICY_ID_128,
        )
        package = runtime.last_packages[V2_ROUTE_HYBRID]
        check(
            "opt-in 128 HYBRID candidate retains preparation identity",
            lambda: result.route == V2_ROUTE_HYBRID
            and package.generation_key.endswith(
                "::stage11-policy=" + STATEFUL_SEMANTIC_POLICY_ID_128
            )
            and runtime.first_pass_policies == [STATEFUL_SEMANTIC_POLICY_ID_128]
            and runtime.hybrid_review_calls == 1,
        )

    # Every explicitly permitted external boundary failure falls back narrowly.
    external_errors = (
        SubtitleCatSearchTransportError("search unavailable"),
        ExternalSubtitleTransportError("payload unavailable"),
        ExternalSubtitleValidationError("invalid payload"),
        SubtitleCatDetailError("invalid detail"),
        SubtitleCatSearchError("invalid search result"),
    )
    for error in external_errors:
        with tempfile.TemporaryDirectory(prefix="stage11-controller-external-") as raw:
            artifact_root, staging_root = _roots(Path(raw))
            runtime = FakeRuntime(fixture.asr_result(), error)
            result = _run(
                artifact_root,
                staging_root,
                runtime,
                targeted_runner=False,
            )
            check(
                "typed external fallback " + type(error).__name__,
                lambda result=result, runtime=runtime: (
                    result.route == V2_ROUTE_ASR_ONLY
                    and runtime.asr_review_calls == 1
                    and runtime.hybrid_review_calls == 0
                ),
            )

    # Alignment routing keeps verdict identity intact.
    for verdict, expected_route in (
        (REJECT_EXTERNAL, V2_ROUTE_ASR_ONLY),
        (UNRESOLVED, V2_ROUTE_ASR_ONLY),
        (ACCEPT_HYBRID, V2_ROUTE_HYBRID),
    ):
        with tempfile.TemporaryDirectory(prefix="stage11-controller-route-") as raw:
            artifact_root, staging_root = _roots(Path(raw))
            runtime = FakeRuntime(fixture.asr_result(), verdict)
            application = _application(verdict, runtime.asr_result)

            def exact_application(_canonical, _asr, value=application, owner=runtime):
                owner.external_calls += 1
                return value

            runtime.external_attempt = exact_application
            result = _run(
                artifact_root,
                staging_root,
                runtime,
                targeted_runner=False,
            )
            check(
                "alignment route " + verdict,
                lambda result=result, expected_route=expected_route,
                application=application, verdict=verdict: (
                    result.route == expected_route
                    and result.alignment_outcome == verdict
                    and application.decision.verdict == verdict
                ),
            )
            if verdict == ACCEPT_HYBRID:
                check(
                    "Hybrid first-pass review CLEAN route",
                    lambda runtime=runtime, result=result: (
                        runtime.first_pass_calls == 1
                        and runtime.asr_review_calls == 0
                        and runtime.hybrid_review_calls == 1
                        and result.clean_path.is_file()
                    ),
                )

    # Generic HYBRID targeted evidence wiring: the REQUIRE source is not an
    # alignment residual, so the review request must be attached through the
    # targeted semantic binding rather than a baseline ASR binding.
    with tempfile.TemporaryDirectory(prefix="stage11-controller-hybrid-targeted-") as raw:
        artifact_root, staging_root = _roots(Path(raw))
        asr_result = _nonresidual_require_asr()
        _prepopulate_baseline(artifact_root, asr_result)
        targeted_path = _prepopulate_targeted(artifact_root, asr_result)
        runtime = FakeRuntime(asr_result)

        def exact_application(_canonical, asr, owner=runtime):
            owner.external_calls += 1
            return _nonresidual_hybrid_application(asr)

        runtime.external_attempt = exact_application
        captured = {}
        native_prepare = controller.prepare_stateful_hybrid

        def capture_prepare(route, **kwargs):
            preparation = native_prepare(route, **kwargs)
            captured["preparation"] = preparation
            captured["kwargs"] = kwargs
            return preparation

        with patch.object(
            controller,
            "prepare_stateful_hybrid",
            side_effect=capture_prepare,
        ):
            result = _run(artifact_root, staging_root, runtime)

        artifact = parse_targeted_second_evidence_artifact_bytes(
            targeted_path.read_bytes()
        )
        preparation = captured["preparation"]
        targeted_semantic = tuple(
            binding
            for binding in preparation.semantic_bindings
            if binding.targeted_asr_evidence is not None
        )
        projected = tuple(
            cue.targeted_second_evidence
            for cue in runtime.last_hybrid_request.cues
            if cue.targeted_second_evidence is not None
        )
        expected_projection = projected[0]
        expected_binding = artifact.bindings[0]
        check(
            "HYBRID REQUIRE target binding reaches prepare_stateful_hybrid",
            lambda: len(captured["kwargs"]["targeted_bindings"]) == 1
            and captured["kwargs"]["targeted_bindings"][0].external_identity.cue_id
            == targeted_semantic[0].targeted_asr_evidence.external_identity.cue_id,
        )
        check(
            "HYBRID targeted source identity reaches semantic binding",
            lambda: len(targeted_semantic) == 1
            and preparation.package.cues[targeted_semantic[0].source_index].stt_ja
            == "補助証拠",
        )
        check(
            "HYBRID targeted review projection is attached exactly once",
            lambda: result.route == V2_ROUTE_HYBRID
            and runtime.hybrid_review_calls == 1
            and len(projected) == 1,
        )
        check(
            "HYBRID targeted review projection preserves artifact identity",
            lambda: expected_projection.status == expected_binding.status
            and expected_projection.text_evidence
            == expected_binding.targeted_text_evidence
            and expected_projection.segment_count
            == len(expected_binding.targeted_segments)
            and expected_projection.provenance_digest
            == expected_binding.result.plan_binding_sha256,
        )

    # A valid targeted artifact whose window has no safely associated external
    # cue falls back before either Hybrid semantic runner.  The accepted
    # alignment verdict remains immutable, and ASR-only review still receives
    # the complete targeted artifact projection.
    with tempfile.TemporaryDirectory(prefix="stage11-controller-hybrid-unprojectable-") as raw:
        artifact_root, staging_root = _roots(Path(raw))
        asr_result = _unprojectable_require_asr()
        _prepopulate_baseline(artifact_root, asr_result)
        targeted_path = _prepopulate_targeted(artifact_root, asr_result)
        runtime = FakeRuntime(asr_result)

        def exact_application(_canonical, asr, owner=runtime):
            owner.external_calls += 1
            return _nonresidual_hybrid_application(asr)

        runtime.external_attempt = exact_application
        result = _run(artifact_root, staging_root, runtime)
        artifact = parse_targeted_second_evidence_artifact_bytes(
            targeted_path.read_bytes()
        )
        projected = tuple(
            cue.targeted_second_evidence
            for cue in runtime.last_asr_request.cues
            if cue.targeted_second_evidence is not None
        )
        check(
            "valid unprojectable targeted evidence selects ASR-only",
            lambda: result.route == V2_ROUTE_ASR_ONLY
            and result.external_ja_outcome == "ACCEPTED"
            and result.alignment_outcome == ACCEPT_HYBRID,
        )
        check(
            "unprojectable targeted evidence skips Hybrid runners",
            lambda: V2_ROUTE_HYBRID not in runtime.first_pass_routes
            and runtime.hybrid_review_calls == 0
            and runtime.asr_review_calls == 1,
        )
        check(
            "unprojectable targeted evidence is not dropped on ASR-only review",
            lambda: len(projected) == len(artifact.bindings) == 1
            and projected[0].status == artifact.bindings[0].status
            and projected[0].text_evidence
            == artifact.bindings[0].targeted_text_evidence
            and projected[0].segment_count
            == len(artifact.bindings[0].targeted_segments),
        )

    # When only part of a valid multi-source artifact is projectable, the
    # controller still takes the all-or-nothing ASR-only fallback.
    with tempfile.TemporaryDirectory(prefix="stage11-controller-hybrid-partial-") as raw:
        artifact_root, staging_root = _roots(Path(raw))
        asr_result = _partially_projectable_require_asr()
        _prepopulate_baseline(artifact_root, asr_result)
        targeted_path = _prepopulate_targeted(artifact_root, asr_result)
        runtime = FakeRuntime(asr_result)

        def exact_application(_canonical, asr, owner=runtime):
            owner.external_calls += 1
            return _nonresidual_hybrid_application(asr)

        runtime.external_attempt = exact_application
        result = _run(artifact_root, staging_root, runtime)
        artifact = parse_targeted_second_evidence_artifact_bytes(
            targeted_path.read_bytes()
        )
        projected = tuple(
            cue.targeted_second_evidence
            for cue in runtime.last_asr_request.cues
            if cue.targeted_second_evidence is not None
        )
        check(
            "partially projectable targeted evidence selects ASR-only",
            lambda: result.route == V2_ROUTE_ASR_ONLY
            and V2_ROUTE_HYBRID not in runtime.first_pass_routes
            and runtime.hybrid_review_calls == 0
            and runtime.asr_review_calls == 1,
        )
        check(
            "partial Hybrid projection does not drop any targeted source",
            lambda: len(projected) == len(artifact.bindings) == 2,
        )

    # Missing optional evidence preserves accepted external JA. Source-stable
    # baseline identity safely attaches EMPTY/runaway evidence in review too.
    policy_cases = (
        ("noisy-unprojectable", _unprojectable_require_asr, ("NOISY",), V2_ROUTE_HYBRID, 0),
        ("empty-unprojectable", _unprojectable_require_asr, ("EMPTY",), V2_ROUTE_HYBRID, 0),
        ("noisy-target-only-projectable", _nonresidual_require_asr, ("NOISY_MIXED",), V2_ROUTE_HYBRID, 1),
        ("noisy-ambiguous-provenance", lambda: replace(
            _partially_projectable_require_asr(),
            segments=_partially_projectable_require_asr().segments[:-1] + (
                ASRSegment(6_000, 6_500, "一旦、一旦、一旦、一旦"),
            )), ("NOISY_MIXED",), V2_ROUTE_HYBRID, 0),
        ("noisy-projectable", _require_asr, ("NOISY",), V2_ROUTE_HYBRID, 1),
        ("empty-projectable", _require_asr, ("EMPTY",), V2_ROUTE_HYBRID, 1),
        ("present-plus-noisy", _partially_projectable_require_asr, ("PRESENT", "NOISY"), V2_ROUTE_HYBRID, 1),
        ("present-missing-plus-noisy", lambda: replace(
            _partially_projectable_require_asr(),
            segments=_partially_projectable_require_asr().segments[:3] + (
                ASRSegment(20_000, 20_500, "一旦、一旦、一旦、一旦"),
                ASRSegment(60_000, 60_500, "一旦、一旦、一旦、一旦"),
            )), ("PRESENT", "NOISY"), V2_ROUTE_ASR_ONLY, 2),
    )
    for name, make_asr, statuses, expected_route, expected_attached in policy_cases:
        with tempfile.TemporaryDirectory(prefix="stage11-controller-policy-") as raw:
            artifact_root, staging_root = _roots(Path(raw))
            asr_result = make_asr()
            _prepopulate_baseline(artifact_root, asr_result)
            targeted_path = _prepopulate_targeted(artifact_root, asr_result, statuses=statuses)
            before = targeted_path.read_bytes()
            artifact = parse_targeted_second_evidence_artifact_bytes(before)
            runtime = FakeRuntime(asr_result)

            def exact_application(_canonical, asr, owner=runtime):
                owner.external_calls += 1
                return _nonresidual_hybrid_application(asr)

            runtime.external_attempt = exact_application
            captured = {}
            native_prepare = controller.prepare_stateful_hybrid

            def capture_prepare(*args, **kwargs):
                preparation = native_prepare(*args, **kwargs)
                captured["preparation"] = preparation
                return preparation

            with patch.object(controller, "prepare_stateful_hybrid", side_effect=capture_prepare):
                result = _run(artifact_root, staging_root, runtime)
            request = (runtime.last_hybrid_request if expected_route == V2_ROUTE_HYBRID
                       else runtime.last_asr_request)
            attached = tuple(cue.targeted_second_evidence for cue in request.cues
                             if cue.targeted_second_evidence is not None)
            check(name + " route and first-pass/review", lambda:
                  result.route == expected_route and result.alignment_outcome == ACCEPT_HYBRID
                  and runtime.first_pass_routes == [expected_route]
                  and len(attached) == expected_attached)
            original_projections = controller.project_targeted_second_evidence_artifact(
                artifact, asr_result=asr_result, require_source_indexes=tuple(
                    binding.source.source_index for binding in artifact.bindings))
            check(name + " artifact bytes/status/provenance preserved", lambda:
                  before == targeted_path.read_bytes()
                  and tuple(result.status for result in artifact.results)
                      == tuple(status.split("_MIXED")[0] + "_UNRESOLVED" for status in statuses)
                  and all(any(
                      projection.status == original.status
                      and projection.provenance_digest == original.provenance_digest
                      and projection.text_evidence == original.text_evidence
                      for original in original_projections.values())
                          for projection in attached))
            check(name + " shared completeness predicate", lambda:
                  tuple(requires_hybrid_targeted_projection(binding)
                        for binding in artifact.bindings)
                  == tuple(binding.status == "PRESENT_UNRESOLVED"
                           for binding in artifact.bindings))
            preparation = captured["preparation"]
            originals = dict(
                preparation=preparation, package=preparation.package,
                result=semantic_result(preparation.package),
                source_quality=classify_source_document(
                    preparation.route_decision.alignment_application.bundle.external_ja_document),
                targeted_second_evidence_artifact=artifact,
            )
            if expected_route == V2_ROUTE_ASR_ONLY:
                reject(name + " review independently requires missing PRESENT",
                       QualityReviewError, lambda: build_review_request(**originals))
            else:
                request = build_review_request(**originals)
                check(name + " independent review status policy", lambda:
                      sum(c.targeted_second_evidence is not None for c in request.cues)
                      == expected_attached)
                target_bindings = tuple(binding for binding in preparation.semantic_bindings
                                        if binding.targeted_asr_evidence is not None)
                if target_bindings:
                    changed_result = replace(artifact.results[0], segments=(
                        replace(artifact.results[0].segments[0], text="変更証拠"),
                    ) + artifact.results[0].segments[1:])
                    changed_artifact = replace(artifact, results=(changed_result,) + artifact.results[1:])
                    reject(name + " mismatched attached evidence rejected by review", QualityReviewError,
                           lambda: build_review_request(**dict(
                               originals, targeted_second_evidence_artifact=changed_artifact)))
                    reject(name + " mismatched attached evidence rejected by controller",
                           controller.Stage11ControllerTargetedEvidenceUnprojectable,
                           lambda: controller._validate_complete_hybrid_targeted_projection(
                               changed_artifact, preparation))
                    reject(name + " duplicate semantic source rejected by controller",
                           controller.Stage11ControllerTargetedEvidenceUnprojectable,
                           lambda: controller._validate_complete_hybrid_targeted_projection(
                               artifact, SimpleNamespace(semantic_bindings=(
                                   preparation.semantic_bindings + target_bindings))))
                # The optional-source policy cannot admit tampered provenance.
                detached = replace(artifact)
                object.__setattr__(detached, "sources", artifact.sources + artifact.sources)
                reject(name + " duplicate artifact provenance rejected", QualityReviewError,
                       lambda: build_review_request(**dict(
                           originals, targeted_second_evidence_artifact=detached)))
                bad_result = replace(artifact.bindings[0].result,
                                     plan_binding_sha256="0" * 64)
                detached = replace(artifact)
                object.__setattr__(detached, "results", (bad_result,) + artifact.results[1:])
                reject(name + " detached artifact provenance rejected", QualityReviewError,
                       lambda: build_review_request(**dict(
                           originals, targeted_second_evidence_artifact=detached)))
            if expected_route == V2_ROUTE_HYBRID and expected_attached == 0:
                check(name + " no invented semantic attachment", lambda:
                      all(binding.targeted_asr_evidence is None
                          for binding in captured["preparation"].semantic_bindings))

    # HYBRID without a targeted artifact retains the existing empty-binding
    # path and does not require the targeted runner.
    with tempfile.TemporaryDirectory(prefix="stage11-controller-hybrid-empty-") as raw:
        artifact_root, staging_root = _roots(Path(raw))
        runtime = FakeRuntime(fixture.asr_result(), ACCEPT_HYBRID)
        captured = {}
        native_prepare = controller.prepare_stateful_hybrid

        def capture_empty_prepare(route, **kwargs):
            captured["kwargs"] = kwargs
            return native_prepare(route, **kwargs)

        with patch.object(
            controller,
            "prepare_stateful_hybrid",
            side_effect=capture_empty_prepare,
        ):
            result = _run(
                artifact_root,
                staging_root,
                runtime,
                targeted_runner=False,
            )
        check(
            "HYBRID without targeted evidence preserves empty bindings",
            lambda: result.route == V2_ROUTE_HYBRID
            and captured["kwargs"]["targeted_bindings"] == ()
            and runtime.targeted_calls == 0
            and runtime.hybrid_review_calls == 1,
        )

    # Duplicate semantic ownership remains fail-closed at the existing
    # stateful preparation boundary.
    with tempfile.TemporaryDirectory(prefix="stage11-controller-hybrid-duplicate-") as raw:
        artifact_root, staging_root = _roots(Path(raw))
        asr_result = _nonresidual_require_asr()
        _prepopulate_baseline(artifact_root, asr_result)
        targeted_path = _prepopulate_targeted(artifact_root, asr_result)
        route_application = _nonresidual_hybrid_application(asr_result)
        artifact = parse_targeted_second_evidence_artifact_bytes(
            targeted_path.read_bytes()
        )
        custom_route = fixture.SubtitleV2RouteDecision(
            canonical_video=fixture.holding(),
            route=V2_ROUTE_HYBRID,
            state=fixture.V2_READY_FOR_SEMANTIC,
            alignment_application=route_application,
        )
        bindings = controller._build_hybrid_targeted_bindings(
            custom_route,
            artifact,
        )
        reject(
            "duplicate Hybrid semantic ownership remains rejected",
            (SubtitleV2PipelineError, ValueError),
            lambda: controller.prepare_stateful_hybrid(
                custom_route,
                targeted_bindings=bindings + bindings,
                generation_key="duplicate-smoke",
                claim_token=7,
            ),
        )

    # Unexpected/programmer and alignment contract failures never fallback.
    for error in (
        RuntimeError("unexpected programmer failure"),
        AlignmentAcceptanceValidationError("detached alignment"),
        SubtitleV2OrchestratorValidationError("detached route"),
    ):
        with tempfile.TemporaryDirectory(prefix="stage11-controller-failclosed-") as raw:
            artifact_root, staging_root = _roots(Path(raw))
            runtime = FakeRuntime(fixture.asr_result(), error)
            reject(
                "external non-fallback " + type(error).__name__,
                type(error),
                lambda runtime=runtime, artifact_root=artifact_root,
                staging_root=staging_root: _run(
                    artifact_root,
                    staging_root,
                    runtime,
                    targeted_runner=False,
                ),
            )
            check(
                "non-fallback stops before stateful execution " + type(error).__name__,
                lambda runtime=runtime: runtime.first_pass_calls == 0,
            )

    # Existing targeted evidence is reused without running targeted transport.
    with tempfile.TemporaryDirectory(prefix="stage11-controller-target-reuse-") as raw:
        artifact_root, staging_root = _roots(Path(raw))
        asr_result = _require_asr()
        _prepopulate_baseline(artifact_root, asr_result)
        _prepopulate_targeted(artifact_root, asr_result)
        runtime = FakeRuntime(asr_result)
        result = _run(artifact_root, staging_root, runtime)
        report = json.loads(result.report_path.read_text(encoding="utf-8"))
        check(
            "targeted valid-existing reuse calls transport zero times",
            lambda: result.targeted_reused is True
            and runtime.targeted_calls == 0
            and report["targeted_source_count"] == 1
            and report["targeted_window_count"] >= 1,
        )

    # Missing targeted evidence runs only the injected V1 execution once.
    with tempfile.TemporaryDirectory(prefix="stage11-controller-target-run-") as raw:
        artifact_root, staging_root = _roots(Path(raw))
        asr_result = _require_asr()
        _prepopulate_baseline(artifact_root, asr_result)
        runtime = FakeRuntime(asr_result)
        result = _run(artifact_root, staging_root, runtime)
        check(
            "targeted absent executes and persists",
            lambda: result.targeted_reused is False
            and runtime.targeted_calls == 1
            and (
                artifact_root
                / TITLE
                / controller.TARGETED_SECOND_EVIDENCE_FILENAME
            ).is_file(),
        )

    # Detached targeted evidence fails before stateful/Hermes adapters.
    with tempfile.TemporaryDirectory(prefix="stage11-controller-target-stale-") as raw:
        artifact_root, staging_root = _roots(Path(raw))
        asr_result = _require_asr()
        _prepopulate_baseline(artifact_root, asr_result)
        _prepopulate_targeted(
            artifact_root,
            asr_result,
            baseline_sha="f" * 64,
        )
        runtime = FakeRuntime(asr_result)
        reject(
            "detached targeted artifact fails closed",
            TargetedSecondEvidenceArtifactValidationError,
            lambda: _run(artifact_root, staging_root, runtime),
        )
        check(
            "detached targeted artifact does not execute transport/stateful",
            lambda: runtime.targeted_calls == 0 and runtime.first_pass_calls == 0,
        )

    # Valid completed CLEAN/report replay is read-only and skips all executors.
    with tempfile.TemporaryDirectory(prefix="stage11-controller-complete-") as raw:
        artifact_root, staging_root = _roots(Path(raw))
        first_runtime = FakeRuntime(fixture.asr_result())
        first = _run(
            artifact_root,
            staging_root,
            first_runtime,
            targeted_runner=False,
        )
        clean_before = first.clean_path.read_bytes()
        report_before = first.report_path.read_bytes()
        replay_runtime = FakeRuntime(
            fixture.asr_result(),
            RuntimeError("external must not run during completed replay"),
        )
        replay = _run(
            artifact_root,
            staging_root,
            replay_runtime,
            targeted_runner=False,
        )
        check(
            "valid CLEAN and report replay without overwrite",
            lambda: replay.clean_reused
            and replay.report_reused
            and replay_runtime.baseline_calls == 0
            and replay_runtime.external_calls == 0
            and replay_runtime.first_pass_calls == 0
            and first.clean_path.read_bytes() == clean_before
            and first.report_path.read_bytes() == report_before,
        )

    source = Path(controller.__file__).read_text(encoding="utf-8")
    signature = inspect.signature(controller.run_one_title_stage11)
    check(
        "publisher is absent from controller contract and implementation",
        lambda: "publisher" not in signature.parameters
        and "subtitle_publish" not in source
        and "publish_korean_srt" not in source,
    )
    check(
        "no title-specific production condition",
        lambda: all(
            marker not in source
            for marker in ("ADN-785", "HSODA-104", "DVDMS-117", "/var/tmp")
        ),
    )
    check(
        "explicit artifact and staging roots",
        lambda: signature.parameters["artifact_root"].default
        is inspect.Parameter.empty
        and signature.parameters["stateful_staging_root"].default
        is inspect.Parameter.empty,
    )

    print("PASS_COUNT=" + str(passed))
    print("THIN_GENERIC_STAGE11_CONTROLLER_SMOKE_PASS")


if __name__ == "__main__":
    main()
