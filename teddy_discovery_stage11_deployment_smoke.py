"""Offline smoke for deployment-owned Stage11 wiring.

All filesystem activity is confined to ``TemporaryDirectory``.  The remote
bridge, ASR review executor, and first-pass native runner are fakes, so this
smoke cannot send Hermes/Whisper requests or create a remote session.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
import uuid

import teddy_discovery_stage11_deployment as deployment
import teddy_discovery_stage11_controller_smoke as controller_fixture
import teddy_discovery_stage11_live_adapters_smoke as live_fixture
import teddy_discovery_subtitle_v2_pipeline_smoke as v2_fixture
import teddy_discovery_stateful_quality_review as review
from teddy_discovery_alignment_acceptance import AlignmentAcceptancePolicy
from teddy_discovery_asr_remote import RemoteFasterWhisperASR
from teddy_discovery_asr_source_quality import classify_asr_result_source_quality
from teddy_discovery_stateful_asr_quality_review import (
    asr_quality_review_request_sha256,
    serialize_asr_quality_review_result,
)
from teddy_discovery_stateful_quality_review_runner import (
    QUALITY_REVIEW_INPUT_FILENAME,
    QUALITY_REVIEW_RESULT_FILENAME,
)
from teddy_discovery_stateful_translator import (
    StatefulSubtitlePackage,
    _atomic_private_write,
    parse_stateful_package,
    serialize_stateful_result,
)
from teddy_discovery_subtitle_external import (
    ExternalSubtitleTransportError,
    SubtitleCatDetailPage,
    SubtitleCatProvider,
)
from teddy_discovery_subtitlecat_discovery import (
    SubtitleCatSearchCandidate,
    SubtitleCatSearchResult,
)
from teddy_discovery_quality_review_session import (
    ensure_fresh_review_execution_session,
)


class FakeRemoteBridge:
    """Deployment bridge double; it stores no state outside this process."""

    def __init__(self):
        self.tasks = set()
        self.files: dict[str, bytes] = {}
        self.session_rows = {}
        self.ensure_task_calls = []
        self.ensure_file_calls = []
        self.stateful_session_calls = []
        self.launch_calls = []
        self.review_payload_to_result = None

    def ensure_task(self, remote_task):
        self.ensure_task_calls.append(remote_task)
        self.tasks.add(remote_task)

    def ensure_file(self, remote_path, payload):
        self.ensure_file_calls.append((remote_path, payload))
        existing = self.files.get(remote_path)
        if existing is not None and existing != payload:
            raise deployment.Stage11DeploymentValidationError(
                "fake remote input conflict"
            )
        self.files.setdefault(remote_path, payload)

    def write_exclusive(self, remote_path, payload):
        if remote_path in self.files:
            raise deployment.Stage11DeploymentTransportError(
                "fake remote destination exists"
            )
        self.files[remote_path] = payload

    def read_regular(self, remote_path, *, max_bytes):
        if remote_path not in self.files:
            raise deployment.Stage11DeploymentTransportError(
                "fake remote file absent"
            )
        payload = self.files[remote_path]
        if not 0 < len(payload) <= max_bytes:
            raise deployment.Stage11DeploymentTransportError(
                "fake remote file exceeds bound"
            )
        return payload

    def ensure_stateful_session(self, session_id):
        self.stateful_session_calls.append(session_id)
        self.session_rows.setdefault(
            session_id,
            {
                "id": session_id,
                "source": "stage11-subtitle-translator",
                "profile_name": "subtitle-translator",
                "parent_session_id": None,
            },
        )

    def get_session(self, session_id):
        return self.session_rows.get(session_id)

    def create_session(self, *, session_id, source, profile_name):
        if session_id in self.session_rows:
            raise deployment.Stage11DeploymentTransportError(
                "fake fresh session already exists"
            )
        self.session_rows[session_id] = {
            "id": session_id,
            "source": source,
            "profile_name": profile_name,
            "parent_session_id": None,
        }
        return session_id

    def get_messages(self, session_id, *, include_inactive=False):
        del include_inactive
        if session_id not in self.session_rows:
            raise deployment.Stage11DeploymentTransportError(
                "fake session absent"
            )
        return []

    def launch_quality_review(self, command, *, remote_task, timeout):
        self.launch_calls.append((command, remote_task, timeout))
        if self.review_payload_to_result is None:
            raise AssertionError("fake Hybrid result callback was not installed")
        input_path = remote_task + "/" + QUALITY_REVIEW_INPUT_FILENAME
        output_path = remote_task + "/" + QUALITY_REVIEW_RESULT_FILENAME
        self.files[output_path] = self.review_payload_to_result(
            self.files[input_path]
        )
        return SimpleNamespace(returncode=0)


class Discovery:
    def __init__(self, *, candidate: bool):
        self.candidate = candidate

    def discover(self, *, dvd_id):
        candidates = ()
        if self.candidate:
            candidates = (
                SubtitleCatSearchCandidate(
                    "https://subtitlecat.com/subs/1/generic.html"
                ),
            )
        return SubtitleCatSearchResult(dvd_id, candidates)


def _config(root: Path, *, timeout=1200):
    return deployment.Stage11DeploymentConfig(
        nas_host="192.0.2.10",
        nas_user="nas-user",
        nas_key=str(root / "nas-key"),
        nas_known_hosts=str(root / "nas-known-hosts"),
        nas_library_root="/volume1/video/video2/JAV",
        asr_base_url="http://192.0.2.20:8091",
        request_timeout_seconds=timeout,
        remote_host="192.0.2.30",
        remote_user="hermes-user",
        ssh_key=str(root / "hermes-key"),
        known_hosts=str(root / "hermes-known-hosts"),
        remote_task_root="/srv/hermes/stage11",
    )


def _holding(asr_result):
    return controller_fixture._holding(asr_result)


def _provider(asr_result):
    payload = v2_fixture.srt_bytes(
        tuple((segment.start_ms, segment.end_ms, segment.text)
              for segment in asr_result.segments)
    )
    return SubtitleCatProvider(
        fetch_detail=lambda url: SubtitleCatDetailPage(
            final_url=url,
            html='<html><a href="test-ja.srt">Japanese</a></html>',
        ),
        payload_fetcher=lambda candidate: payload,
    )


def _asr_executor(runtime):
    def execute(request, payload, digest, remote_task, timeout):
        del payload, digest, remote_task, timeout
        return serialize_asr_quality_review_result(
            runtime._review_result(request, asr_quality_review_request_sha256(request)),
            request,
        )

    return execute


def _native_first_pass(runtime):
    def run(args):
        package = parse_stateful_package(Path(args.package).read_bytes())
        route = (
            "HYBRID"
            if package.generation_key.startswith("stage11-hybrid-")
            else "ASR_ONLY"
        )
        result = runtime.first_pass(
            package,
            route=route,
            staging_root=Path(args.task_directory).parent,
        )
        _atomic_private_write(
            Path(args.final_result),
            serialize_stateful_result(result),
        )
        return 0

    return run


def _install_fake_hybrid_result(bridge, deps, runtime):
    def result_from_payload(payload):
        request = review._parse(
            payload,
            review.QualityReviewRequest,
            review.QualityReviewInputCue,
        )
        originals = deps.originals_provider(request)
        request = review.parse_review_request(payload, **originals)
        result = runtime._review_result(request, review.review_request_sha256(request))
        return review.serialize_review_result(result, request)

    bridge.review_payload_to_result = result_from_payload


class FakeFreshReviewDB:
    def __init__(self):
        self.rows = {}
        self.messages = {}
        self.calls = []

    def get_session(self, session_id):
        return self.rows.get(session_id)

    def create_session(self, *, session_id, source, profile_name):
        self.calls.append((session_id, source, profile_name))
        self.rows[session_id] = {
            "id": session_id,
            "source": source,
            "profile_name": profile_name,
            "parent_session_id": None,
        }
        return session_id

    def get_messages(self, session_id, *, include_inactive=False):
        del include_inactive
        return list(self.messages.get(session_id, ()))


def _build_deps_with_asr_fake(root, *, candidate, bridge=None, baseline=None, runtime=None):
    baseline = v2_fixture.asr_result() if baseline is None else baseline
    runtime = (
        controller_fixture.FakeRuntime(
            baseline,
            stage_first_pass_artifacts=False,
        )
        if runtime is None
        else runtime
    )
    bridge = FakeRemoteBridge() if bridge is None else bridge
    fresh_db = FakeFreshReviewDB()
    provider = _provider(baseline)

    def prepare_review_session(session_id):
        ensure_fresh_review_execution_session(
            fresh_db,
            session_id,
            expected_profile_name="subtitle-translator",
        )

    deps = deployment.build_stage11_deployment_dependencies(
        _config(root),
        acceptance_policy=AlignmentAcceptancePolicy(
            3, 3, 0.8, 100.0, 0, 0.9, 1.1
        ),
        residual_threshold_ms=100,
        holding_resolver=lambda title: _holding(baseline),
        source_provider=live_fixture.Source(root, baseline.source_snapshot),
        whisper=live_fixture.Transport(baseline.segments),
        targeted_transport=live_fixture.Transport(baseline.segments),
        discovery=Discovery(candidate=candidate),
        provider=provider,
        remote_bridge=bridge,
        native_first_pass_run=_native_first_pass(runtime),
        asr_review_options={
            "executor": _asr_executor(runtime),
            "fresh_session_preparer": prepare_review_session,
        },
    )
    return deps, runtime, bridge, fresh_db


def _controller_run(deps, root, baseline):
    root.mkdir(mode=0o700)
    artifact_root = root / "artifacts"
    staging_root = root / "staging"
    artifact_root.mkdir(mode=0o700)
    staging_root.mkdir(mode=0o700)
    controller_fixture._prepopulate_baseline(artifact_root, baseline)
    return controller_fixture.controller.run_one_title_stage11(
        controller_fixture.TITLE,
        artifact_root=artifact_root,
        stateful_staging_root=staging_root,
        claim_token=deployment.STAGE11_STANDALONE_CANARY_CLAIM_TOKEN,
        **deps.controller_kwargs(),
    )


def main():
    passed = 0

    def check(label, value):
        nonlocal passed
        if not value:
            raise AssertionError(label)
        passed += 1
        print("PASS=" + label)

    with tempfile.TemporaryDirectory(prefix="stage11-deployment-smoke-") as raw:
        root = Path(raw)
        check(
            "CONFIG_TIMEOUT_1200_EXPLICIT",
            _config(root).request_timeout_seconds == 1200,
        )
        try:
            deployment.Stage11DeploymentConfig(
                nas_host="host",
                nas_user="user",
                nas_key="relative-key",
                nas_known_hosts="/known",
                nas_library_root="/library",
                asr_base_url="http://asr",
                request_timeout_seconds=0,
                remote_host="remote",
                remote_user="user",
                ssh_key="/key",
                known_hosts="/hosts",
                remote_task_root="/remote/root",
            )
        except deployment.Stage11DeploymentValidationError:
            check("CONFIG_INVALID_TIMEOUT_FAIL_CLOSED", True)
        else:
            check("CONFIG_INVALID_TIMEOUT_FAIL_CLOSED", False)

        bridge = FakeRemoteBridge()
        deps, runtime, bridge, fresh_db = _build_deps_with_asr_fake(
            root,
            candidate=False,
            bridge=bridge,
        )
        session = str(uuid.uuid4())
        check(
            "REMOTE_TASK_DETERMINISTIC",
            deps.remote_task_for_session(session)
            == "/srv/hermes/stage11/" + session,
        )
        try:
            deps.remote_task_for_session("../../escape")
        except deployment.Stage11DeploymentValidationError:
            check("REMOTE_TASK_TRAVERSAL_REJECTED", True)
        else:
            check("REMOTE_TASK_TRAVERSAL_REJECTED", False)

        # Exercise prepare_remote through the actual live adapter.  A package
        # from the canonical stateful smoke is used only as an in-memory fake.
        from teddy_discovery_hermes_v2 import HermesV2CueInput

        package = StatefulSubtitlePackage(
            schema_version=1,
            dvd_id="GENERIC-SMOKE",
            generation_key="generic-deployment-smoke",
            claim_token=1,
            cues=(
                HermesV2CueInput(
                    cue_id="ja-000000",
                    external_ja="テスト",
                    stt_ja=None,
                    en=None,
                    before_context=(),
                    after_context=(),
                ),
            ),
        )
        from teddy_discovery_stateful_translator import (
            stateful_staging_paths,
            write_stateful_input,
        )

        local_task = root / "local-first-pass-task"
        local_task.mkdir(mode=0o700)
        write_stateful_input(local_task, package)
        paths = stateful_staging_paths(local_task)
        prepared_remote = deps.prepare_remote(package, paths, route="ASR_ONLY")
        check(
            "PREPARE_REMOTE_FAKE_SSH_PATH",
            prepared_remote == deps.remote_task_for_session(
                __import__(
                    "teddy_discovery_stateful_translator",
                    fromlist=["stateful_session_id_for_package"],
                ).stateful_session_id_for_package(package)
            )
            and bridge.ensure_task_calls
            and bridge.stateful_session_calls,
        )
        check(
            "FIRST_PASS_NATIVE_RUN_NAMESPACE",
            callable(deps.live.first_pass_runner),
        )

        # Baseline composition and targeted source binding use fake media and
        # fake transport objects, not the configured live endpoints.
        source = live_fixture.Source(root, v2_fixture.asr_result().source_snapshot)
        whisper = live_fixture.Transport(v2_fixture.asr_result().segments)
        target_deps = deployment.build_stage11_deployment_dependencies(
            _config(root),
            acceptance_policy=AlignmentAcceptancePolicy(
                3, 3, 0.8, 100.0, 0, 0.9, 1.1
            ),
            residual_threshold_ms=100,
            holding_resolver=lambda title: _holding(v2_fixture.asr_result()),
            source_provider=source,
            whisper=whisper,
            targeted_transport=whisper,
            discovery=Discovery(candidate=False),
            provider=_provider(v2_fixture.asr_result()),
            remote_bridge=FakeRemoteBridge(),
            native_first_pass_run=lambda args: 1,
            audio_chunk_iterator=live_fixture.audio,
            asr_review_options={
                "executor": _asr_executor(runtime),
                "fresh_session_preparer": lambda sid: None,
            },
        )
        baseline_result = target_deps.live.baseline_transcriber(
            v2_fixture.holding()
        )
        check(
            "BASELINE_ASR_COMPOSITION",
            baseline_result.segments == v2_fixture.asr_result().segments
            and baseline_result.source_snapshot == v2_fixture.asr_result().source_snapshot
            and whisper.baseline_calls > 0,
        )
        required = controller_fixture._require_asr()
        target_execution = target_deps.live.targeted_runner(
            required,
            classify_asr_result_source_quality(required),
        )
        check(
            "TARGETED_SOURCE_SNAPSHOT_BINDING",
            target_execution.source_count > 0
            and target_execution.window_count > 0,
        )

        provider = deployment.build_subtitlecat_provider(
            fetch_detail=lambda url: SubtitleCatDetailPage(
                final_url=url,
                html='<html><a href="generic-ja.srt">Japanese</a></html>',
            ),
            payload_fetcher=lambda candidate: (
                "1\n00:00:00,000 --> 00:00:00,100\n日本語\n".encode("utf-8")
            ),
        )
        payload = provider.fetch_original_japanese_payload(
            dvd_id=v2_fixture.DVD_ID,
            detail_url="https://subtitlecat.com/generic.html",
        )
        check("SUBTITLECAT_PROVIDER_COMPOSITION", payload.parse().cues)

        default_asr = deployment.build_stage11_deployment_dependencies(
            _config(root),
            acceptance_policy=AlignmentAcceptancePolicy(
                3, 3, 0.8, 100.0, 0, 0.9, 1.1
            ),
            residual_threshold_ms=100,
            holding_resolver=lambda title: _holding(v2_fixture.asr_result()),
            source_provider=source,
            remote_bridge=FakeRemoteBridge(),
            native_first_pass_run=lambda args: 1,
            asr_review_options={
                "executor": _asr_executor(runtime),
                "fresh_session_preparer": lambda sid: None,
            },
        )
        check(
            "VM122_TIMEOUT_IS_EXPLICIT",
            isinstance(default_asr.whisper, RemoteFasterWhisperASR)
            and default_asr.whisper.request_timeout_seconds == 1200,
        )

        # ASR-only controller + deployment + live adapter flow.
        asr_deps, asr_runtime, asr_bridge, asr_fresh_db = _build_deps_with_asr_fake(
            root,
            candidate=False,
        )
        asr_result = v2_fixture.asr_result()
        completed_asr = _controller_run(asr_deps, root / "asr-e2e", asr_result)
        check(
            "FAKE_E2E_ASR_ONLY_CLEAN_REPORT",
            completed_asr.route == "ASR_ONLY"
            and completed_asr.clean_path.is_file()
            and completed_asr.report_path.is_file()
            and not asr_bridge.launch_calls,
        )
        check(
            "ASR_REVIEW_FRESH_SESSION_WIRING",
            asr_runtime.first_pass_calls == 1
            and len(asr_fresh_db.calls) == 1,
        )

        # Hybrid controller + deployment + default deployment launcher.  The
        # fake bridge produces a validator-compatible result from exact input.
        hybrid_root = root / "hybrid-e2e"
        hybrid_deps, hybrid_runtime, hybrid_bridge, _hybrid_fresh_db = _build_deps_with_asr_fake(
            hybrid_root,
            candidate=True,
        )
        _install_fake_hybrid_result(hybrid_bridge, hybrid_deps, hybrid_runtime)
        completed_hybrid = _controller_run(
            hybrid_deps,
            hybrid_root,
            v2_fixture.asr_result(),
        )
        check(
            "FAKE_E2E_HYBRID_CLEAN_REPORT",
            completed_hybrid.route == "HYBRID"
            and completed_hybrid.clean_path.is_file()
            and completed_hybrid.report_path.is_file()
            and len(hybrid_bridge.launch_calls) == 1,
        )
        check(
            "HYBRID_FRESH_SESSION_AND_ORIGINALS",
            hybrid_bridge.session_rows
            and hybrid_bridge.launch_calls[0][1].startswith(
                "/srv/hermes/stage11/"
            )
            and any(
                path.endswith("/stage11-quality-review-input.json")
                for path in hybrid_bridge.files
            ),
        )

        # An unexpected external exception is deliberately not converted to
        # ASR-only by this deployment layer.
        failing = deployment.build_stage11_deployment_dependencies(
            _config(root),
            acceptance_policy=AlignmentAcceptancePolicy(
                3, 3, 0.8, 100.0, 0, 0.9, 1.1
            ),
            residual_threshold_ms=100,
            holding_resolver=lambda title: _holding(v2_fixture.asr_result()),
            source_provider=source,
            whisper=whisper,
            targeted_transport=whisper,
            discovery=SimpleNamespace(
                discover=lambda **kwargs: (_ for _ in ()).throw(
                    RuntimeError("unexpected programmer error")
                )
            ),
            provider=_provider(v2_fixture.asr_result()),
            remote_bridge=FakeRemoteBridge(),
            native_first_pass_run=lambda args: 1,
            asr_review_options={
                "executor": _asr_executor(runtime),
                "fresh_session_preparer": lambda sid: None,
            },
        )
        try:
            failing.live.external_ja_attempt(
                v2_fixture.holding(),
                v2_fixture.asr_result(),
            )
        except RuntimeError:
            check("UNEXPECTED_EXTERNAL_EXCEPTION_FAIL_CLOSED", True)
        else:
            check("UNEXPECTED_EXTERNAL_EXCEPTION_FAIL_CLOSED", False)

        typed_failure = ExternalSubtitleTransportError("typed transport failure")
        typed = deployment.build_stage11_deployment_dependencies(
            _config(root),
            acceptance_policy=AlignmentAcceptancePolicy(
                3, 3, 0.8, 100.0, 0, 0.9, 1.1
            ),
            residual_threshold_ms=100,
            holding_resolver=lambda title: _holding(v2_fixture.asr_result()),
            source_provider=source,
            whisper=whisper,
            targeted_transport=whisper,
            discovery=SimpleNamespace(
                discover=lambda **kwargs: (_ for _ in ()).throw(typed_failure)
            ),
            provider=_provider(v2_fixture.asr_result()),
            remote_bridge=FakeRemoteBridge(),
            native_first_pass_run=lambda args: 1,
            asr_review_options={
                "executor": _asr_executor(runtime),
                "fresh_session_preparer": lambda sid: None,
            },
        )
        try:
            typed.live.external_ja_attempt(
                v2_fixture.holding(),
                v2_fixture.asr_result(),
            )
        except ExternalSubtitleTransportError as error:
            check("TYPED_EXTERNAL_ERROR_PROPAGATES", error is typed_failure)
        else:
            check("TYPED_EXTERNAL_ERROR_PROPAGATES", False)

        check(
            "NO_PRODUCTION_NETWORK_OR_PROCESS_COUNTERS",
            not asr_bridge.launch_calls,
        )

    print("DEPLOYMENT_SMOKE_PASS_COUNT=" + str(passed))
    print("DEPLOYMENT_SMOKE_FAIL_COUNT=0")
    print("STAGE11_DEPLOYMENT_SMOKE_PASS")


if __name__ == "__main__":
    with patch(
        "subprocess.run",
        side_effect=AssertionError("actual subprocess forbidden"),
    ), patch(
        "subprocess.Popen",
        side_effect=AssertionError("actual process forbidden"),
    ), patch(
        "socket.socket",
        side_effect=AssertionError("actual network forbidden"),
    ):
        main()
