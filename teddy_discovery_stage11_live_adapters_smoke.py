"""Offline adapter and controller integration, with network/process tripwires."""
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
import numpy as np

import teddy_discovery_stage11_live_adapters as adapters
import teddy_discovery_stage11_controller_smoke as fixture
from teddy_discovery_stage11_controller import run_one_title_stage11
from teddy_discovery_asr import ASRSegment, REMOTE_GPU_LARGE_V3_RUNTIME_IDENTITY
from teddy_discovery_asr_audio import ASRAudioChunk
from teddy_discovery_asr_source import ASRLocalMediaSource
from teddy_discovery_asr_source_quality import classify_asr_result_source_quality
from teddy_discovery_stateful_translator import (
    parse_stateful_package, serialize_stateful_result, _atomic_private_write,
)
from teddy_discovery_stateful_asr_quality_review import (
    serialize_asr_quality_review_result, asr_quality_review_request_sha256,
)
from teddy_discovery_stateful_quality_review import (
    build_review_request, parse_review_request, serialize_review_result,
    review_request_sha256,
)
from teddy_discovery_stateful_quality_review_runner import (
    QUALITY_REVIEW_INPUT_FILENAME, QUALITY_REVIEW_RESULT_FILENAME,
)
from teddy_discovery_stateful_hybrid import prepare_stateful_hybrid
from teddy_discovery_subtitle_source_quality import classify_source_document
from teddy_discovery_subtitle_v2_orchestrator import SubtitleV2RouteDecision, V2_READY_FOR_SEMANTIC
from teddy_discovery_subtitlecat_discovery import (
    SubtitleCatDiscovery, SubtitleCatSearchResponse,
)
from teddy_discovery_subtitle_external import (
    SubtitleCatProvider, SubtitleCatDetailPage, ExternalSubtitleTransportError,
    ExternalSubtitleValidationError,
)
from teddy_discovery_alignment_acceptance import AlignmentAcceptancePolicy
from teddy_discovery_quality_review_session_smoke import FakeNativeSessionDB
from teddy_discovery_quality_review_session import ensure_fresh_review_execution_session


def expect(error, fn):
    try:
        fn()
    except error:
        return
    raise AssertionError("expected " + error.__name__)


class Source:
    def __init__(self, root, snapshot):
        self.root, self.snapshot = root, snapshot
        self.calls = 0
        self.paths = []

    def copy_to_temp(self, video, *, max_media_bytes, timeout=None):
        self.calls += 1
        directory = tempfile.mkdtemp(dir=self.root)
        path = Path(directory) / "media.mp4"
        path.write_bytes(b"x" * self.snapshot.source_size)
        self.paths.append(path)
        return ASRLocalMediaSource(local_path=str(path),
            source_snapshot=self.snapshot, temp_directory=directory)


def audio(source, *, start_seconds, end_seconds, chunk_seconds):
    start = round(start_seconds * 1000)
    end = 5000 if end_seconds is None else round(end_seconds * 1000)
    yield ASRAudioChunk(source.source_snapshot, start, end, 16000,
                        np.zeros((end-start)*16, dtype=np.float32))


class Transport:
    runtime_identity = REMOTE_GPU_LARGE_V3_RUNTIME_IDENTITY
    engine_version = "offline-adapter"

    def __init__(self, segments):
        self.segments = segments
        self.baseline_calls = self.targeted_calls = 0

    def transcribe_chunk(self, chunk):
        self.baseline_calls += 1
        return self.segments

    def transcribe_targeted_chunk(self, chunk):
        self.targeted_calls += 1
        return (ASRSegment(chunk.start_ms, chunk.start_ms + 100, "独立した証拠"),)


def main():
    with tempfile.TemporaryDirectory(prefix="stage11-live-smoke-") as raw:
        root = Path(raw)
        baseline = fixture.fixture.asr_result()
        row = fixture._holding(baseline)
        env = {"TEDDY_DISCOVERY_DB": str(root / "unused.sqlite")}
        resolver = adapters.build_holding_resolver(environ=env,
            state_loader=lambda path: {"holdings": [row]})
        assert resolver(fixture.TITLE) == row
        expect(adapters.Stage11LiveAdapterError,
            lambda: adapters.build_holding_resolver(environ={})(fixture.TITLE))
        expect(adapters.Stage11LiveAdapterError, lambda:
            adapters.build_holding_resolver(environ={'TEDDY_DISCOVERY_DB': '  '})(fixture.TITLE))
        expect(adapters.Stage11LiveAdapterError, lambda: resolver(fixture.TITLE.lower()))
        for rows in ([], [row, row]):
            expect(adapters.Stage11LiveAdapterError, lambda rows=rows:
                adapters.build_holding_resolver(environ=env,
                    state_loader=lambda path: {"holdings": rows})(fixture.TITLE))
        print("PASS holding exact/unset/duplicate/not-found; Flask-free")

        source = Source(root, baseline.source_snapshot)
        transport = Transport(baseline.segments)
        baseline_adapter = adapters.build_baseline_adapter(
            holding_resolver=resolver, source_provider=source, whisper=transport,
            audio_chunk_iterator=audio)
        result = baseline_adapter(fixture.fixture.holding())
        assert result.segments == baseline.segments and transport.baseline_calls == 1
        assert not source.paths[-1].exists()
        targeted = adapters.build_targeted_adapter(holding_resolver=resolver,
            source_provider=source, targeted_transport=transport,
            audio_chunk_iterator=audio)
        required = fixture._require_asr()
        execution = targeted(required, classify_asr_result_source_quality(required))
        assert execution.source_count > 0 and transport.targeted_calls > 0
        source.snapshot = replace(source.snapshot, source_mtime_ns=1)
        expect(adapters.Stage11LiveAdapterError,
            lambda: targeted(required, classify_asr_result_source_quality(required)))
        source.snapshot = baseline.source_snapshot
        print("PASS native baseline/targeted composition; snapshot and cleanup")

        policy = AlignmentAcceptancePolicy(3, 3, 0.8, 100.0, 0, 0.9, 1.1)
        candidate_url = "https://subtitlecat.com/subs/1/test.html"
        def discovery(present):
            return SubtitleCatDiscovery(fetch=lambda req, timeout:
                SubtitleCatSearchResponse(200, req.full_url,
                    (f'<html><a href="{candidate_url}">{fixture.TITLE}</a></html>'
                     if present else '<html></html>').encode()))
        provider = SubtitleCatProvider(
            fetch_detail=lambda url: SubtitleCatDetailPage(url,
                '<html><a href="test-ja.srt">Japanese</a></html>'),
            payload_fetcher=lambda candidate: fixture.fixture.srt_bytes(tuple(
                (s.start_ms, s.end_ms, s.text) for s in baseline.segments)))
        external = adapters.build_external_ja_adapter(discovery=discovery(True),
            provider=provider, acceptance_policy=policy, residual_threshold_ms=100)
        accepted = external(fixture.fixture.holding(), baseline)
        assert accepted.decision.verdict == "ACCEPT_HYBRID"
        assert adapters.build_external_ja_adapter(discovery=discovery(False),
            provider=provider, acceptance_policy=policy,
            residual_threshold_ms=100)(fixture.fixture.holding(), baseline) is None
        for changed, verdict in ((replace(policy, minimum_anchor_count=4), "UNRESOLVED"),
                                 (replace(policy, minimum_scale=1.01), "REJECT_EXTERNAL")):
            application = adapters.build_external_ja_adapter(discovery=discovery(True),
                provider=provider, acceptance_policy=changed,
                residual_threshold_ms=100)(fixture.fixture.holding(), baseline)
            assert application.decision.verdict == verdict
        def broken(**kwargs):
            raise ExternalSubtitleTransportError("offline failure")
        expect(ExternalSubtitleTransportError, lambda:
            adapters.build_external_ja_adapter(discovery=SimpleNamespace(discover=broken),
                provider=provider, acceptance_policy=policy,
                residual_threshold_ms=100)(fixture.fixture.holding(), baseline))
        for exception in (ExternalSubtitleValidationError, RuntimeError):
            def fail(**kwargs):
                raise exception('must propagate')
            expect(exception, lambda:
                adapters.build_external_ja_adapter(discovery=discovery(True),
                    provider=SimpleNamespace(fetch_original_japanese_payload=fail),
                    acceptance_policy=policy, residual_threshold_ms=100)(
                        fixture.fixture.holding(), baseline))
        print("PASS native discovery/provider/alignment and verdict propagation")

        for route in ("ASR_ONLY", "HYBRID"):
            artifacts, staging = root / (route+'-artifacts'), root / (route+'-staging')
            artifacts.mkdir(mode=0o700)
            staging.mkdir(mode=0o700)
            state = {}
            sessions = FakeNativeSessionDB()
            calls = []
            fake = fixture.FakeRuntime(baseline)

            def prepare(package, paths, *, route):
                assert paths.input_path.read_bytes()
                calls.append("prepare")
                return "/offline/" + paths.task_directory.name

            def native(args):
                package = parse_stateful_package(Path(args.package).read_bytes())
                first = fake.first_pass(package, route=route, staging_root=staging)
                state.update(package=package, first=first)
                _atomic_private_write(Path(args.final_result), serialize_stateful_result(first))
                calls.append("first")
                return 0

            def originals(request):
                route_decision = SubtitleV2RouteDecision(
                    canonical_video=fixture.fixture.holding(), route="HYBRID",
                    state=V2_READY_FOR_SEMANTIC, alignment_application=accepted)
                preparation = prepare_stateful_hybrid(route_decision,
                    generation_key=state['package'].generation_key, claim_token=7)
                values = dict(preparation=preparation, package=state['package'],
                    result=state['first'], source_quality=classify_source_document(
                        accepted.bundle.external_ja_document))
                assert build_review_request(**values) == request
                return values

            def asr_executor(request, payload, digest, remote_task, timeout):
                calls.append("asr")
                state['asr_request'] = request
                return serialize_asr_quality_review_result(fake._review_result(
                    request, asr_quality_review_request_sha256(request)), request)

            def prepare_asr_session(sid):
                ensure_fresh_review_execution_session(sessions, sid,
                    expected_profile_name='subtitle-translator')
                calls.append(('fresh', sid))

            def launcher(command, *, cwd, timeout):
                directory = Path('/proc/self/fd') / str(cwd)
                payload = (directory / QUALITY_REVIEW_INPUT_FILENAME).read_bytes()
                # Originals captured by the provider are independent of the wire.
                request = build_review_request(**originals(state['request']))
                assert parse_review_request(payload, **originals(request)) == request
                _atomic_private_write(directory / QUALITY_REVIEW_RESULT_FILENAME,
                    serialize_review_result(fake._review_result(request,
                        review_request_sha256(request)), request))
                calls.append("hybrid")
                return SimpleNamespace(returncode=0)

            def get_originals(request):
                state['request'] = request
                return originals(request)

            deps = adapters.build_stage11_live_dependencies(
                holding_resolver=resolver, source_provider=source, whisper=transport,
                targeted_transport=transport, discovery=discovery(route == 'HYBRID'),
                provider=provider, acceptance_policy=policy, residual_threshold_ms=100,
                audio_chunk_iterator=audio,
                first_pass_options=dict(remote='offline', ssh_key='/offline/key',
                    known_hosts='/offline/hosts', prepare_remote=prepare, native_run=native),
                asr_review_options=dict(remote_task_for_session=lambda sid: '/offline/'+sid,
                    runner_options=dict(executor=asr_executor,
                        fresh_session_preparer=prepare_asr_session)),
                hybrid_review_options=dict(originals_provider=get_originals,
                    runner_options=dict(launcher=launcher, fresh_session_db=sessions,
                        expected_profile_name='subtitle-translator')))
            # Existing baseline reuse must not touch the media transport.
            fixture._prepopulate_baseline(artifacts, baseline)
            before = transport.baseline_calls
            completed = run_one_title_stage11(fixture.TITLE,
                artifact_root=artifacts, stateful_staging_root=staging,
                claim_token=7, **asdict(deps))
            assert completed.route == route and completed.clean_path.is_file()
            assert completed.report_path.is_file() and transport.baseline_calls == before
            assert ('asr' if route == 'ASR_ONLY' else 'hybrid') in calls
            if route == 'HYBRID':
                assert len(sessions.create_calls) == 1
            else:
                assert len([c for c in calls if isinstance(c, tuple)]) == 1
            before_calls = list(calls)
            deps.first_pass_runner(state['package'], route=route, staging_root=staging)
            assert calls == before_calls
            if route == 'ASR_ONLY':
                repeated = deps.asr_review_runner(state['asr_request'], staging_root=staging)
                fresh = [c[1] for c in calls if isinstance(c, tuple)]
                assert len(fresh) == 2 and fresh[0] != fresh[1]
                assert repeated.review_execution_session_id == fresh[1]
            else:
                repeated = deps.hybrid_review_runner(state['request'], staging_root=staging)
                assert len(sessions.create_calls) == 2
                assert sessions.create_calls[0][0] != sessions.create_calls[1][0]
                assert repeated.review_execution_session_id == sessions.create_calls[1][0]
            # A native failure is never converted to a successful controller result.
            failure_root = root / (route + '-failure')
            failure_root.mkdir(mode=0o700)
            failed = adapters.build_first_pass_adapter(remote='offline',
                ssh_key='/offline/key', known_hosts='/offline/hosts',
                prepare_remote=prepare, native_run=lambda args: 1)
            expect(adapters.Stage11LiveAdapterError, lambda:
                failed(state['package'], route=route, staging_root=failure_root))
            resumed = deps.first_pass_runner(state['package'], route=route,
                staging_root=failure_root)
            assert resumed.session_id == state['first'].session_id
            print('PASS controller + live adapters ' + route + ' CLEAN/report; first-pass reuse')
        print('STAGE11_LIVE_ADAPTERS_SMOKE_PASS')


if __name__ == '__main__':
    with patch('subprocess.run', side_effect=AssertionError('actual subprocess forbidden')), \
         patch('subprocess.Popen', side_effect=AssertionError('actual process forbidden')), \
         patch('sqlite3.connect', side_effect=AssertionError('actual DB forbidden')), \
         patch('socket.socket', side_effect=AssertionError('actual network forbidden')):
        main()
