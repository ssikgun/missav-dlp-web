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
from teddy_discovery_asr_artifact import persist_asr_result, serialize_asr_result
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
    review_request_sha256,
)
from teddy_discovery_stateful_translator import (
    StatefulSubtitleResult,
    stateful_session_id_for_package,
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


def _targeted_execution(asr_result, decisions):
    plan = build_targeted_second_evidence_plan_with_policy(
        asr_result,
        decisions,
        policy=STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1,
    )
    results = []
    for window in plan.windows:
        source = asr_result.segments[window.source_indices[0]]
        start_ms = source.start_ms
        end_ms = min(source.end_ms, start_ms + 100)
        if end_ms <= start_ms:
            raise AssertionError("synthetic targeted window has no duration")
        results.append(
            TargetedSecondEvidenceWindowResult(
                source_snapshot=plan.source_snapshot,
                window_id=window.window_id,
                window_start_ms=window.start_ms,
                window_end_ms=window.end_ms,
                segments=(ASRSegment(start_ms, end_ms, "補助証拠"),),
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
    def __init__(self, asr_result, external=None):
        self.asr_result = asr_result
        self.external = external
        self.baseline_calls = 0
        self.external_calls = 0
        self.targeted_calls = 0
        self.first_pass_calls = 0
        self.asr_review_calls = 0
        self.hybrid_review_calls = 0
        self.staging_roots = []
        self.last_packages = {}
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

    def first_pass(self, package, *, route, staging_root):
        self.first_pass_calls += 1
        self.staging_roots.append(staging_root)
        assert route in {V2_ROUTE_ASR_ONLY, V2_ROUTE_HYBRID}
        self.last_packages[route] = package
        return StatefulSubtitleResult(
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

    @staticmethod
    def _review_result(request, request_sha):
        return QualityReviewResult(
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

    def asr_review(self, request, *, staging_root):
        self.asr_review_calls += 1
        self.staging_roots.append(staging_root)
        assert type(request) is ASRQualityReviewRequest
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


def _run(artifact_root, staging_root, runtime, *, targeted_runner=True):
    return controller.run_one_title_stage11(
        TITLE,
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


def _prepopulate_baseline(artifact_root: Path, asr_result):
    title_dir = artifact_root / TITLE
    title_dir.mkdir(mode=0o700)
    path = title_dir / controller.BASELINE_ASR_FILENAME
    persist_asr_result(path, asr_result)
    return path


def _prepopulate_targeted(artifact_root: Path, asr_result, *, baseline_sha=None):
    decisions = classify_asr_result_source_quality(asr_result)
    execution = _targeted_execution(asr_result, decisions)
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
