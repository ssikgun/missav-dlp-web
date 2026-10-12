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
    SubtitleCatDiscovery, SubtitleCatSearchError, SubtitleCatSearchResponse,
    SubtitleCatSearchTransportError,
)
from teddy_discovery_subtitle_external import (
    SubtitleCatProvider, SubtitleCatDetailPage, ExternalSubtitleTransportError,
    ExternalSubtitleValidationError, SubtitleCatDetailError,
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


def multicandidate_smoke(baseline, policy):
    from teddy_discovery_subtitlecat_discovery import SubtitleCatSearchCandidate, SubtitleCatSearchResult
    from teddy_discovery_subtitle_external import SubtitleCatDetailError
    from teddy_discovery_alignment import AlignmentLimitError, AlignmentAmbiguityError

    video = fixture.fixture.holding()
    original = fixture.fixture.srt_bytes(tuple((s.start_ms, s.end_ms, s.text)
                                               for s in baseline.segments))
    variants = {
        'accept': original,
        'duplicate': original,
        'distinct': original + b'\n',
        'unresolved': fixture.fixture.srt_bytes(tuple((s.start_ms, s.end_ms, s.text)
                                                     for s in baseline.segments[:2])),
        'reject': fixture.fixture.srt_bytes(tuple((s.start_ms, s.end_ms, s.text)
                                                 for s in baseline.segments)),
        'invalid': b'not an SRT',
        'no-consensus': fixture.fixture.srt_bytes(((0, 100, 'unrelated phrase'),)),
        'limit': original + b'\n',
        'ambiguity': original + b'\n',
        'identity': original,
        'malformed-state': original,
    }
    errors = {'detail-invalid': SubtitleCatDetailError,
              'transport': ExternalSubtitleTransportError, 'incomplete': RuntimeError}

    def execute(names, changed_policy=policy):
        calls = []
        urls = ['https://subtitlecat.com/subs/1/' + name + '.html' for name in names]
        discovery = SimpleNamespace(discover=lambda **kwargs: SubtitleCatSearchResult(
            fixture.TITLE, tuple(SubtitleCatSearchCandidate(url) for url in urls)))
        actual_provider = SubtitleCatProvider(
            fetch_detail=lambda url: SubtitleCatDetailPage(url,
                '<html><a href="' + url.rsplit('/', 1)[1].replace('.html', '-ja.srt')
                + '">Japanese</a></html>'),
            payload_fetcher=lambda candidate: original)
        def fetch(**kwargs):
            name = kwargs['detail_url'].rsplit('/', 1)[1][:-5]
            calls.append(name)
            if name in errors: raise errors[name]('offline synthetic failure')
            if name == 'malformed-state': return object()
            payload = actual_provider.fetch_original_japanese_payload(**kwargs)
            if name == 'identity':
                object.__setattr__(payload, 'dvd_id', 'OTHER-001')
                return payload
            return replace(payload, payload=variants[name], sha256=None, byte_size=None)
        generate = adapters.generate_monotonic_anchor_candidates
        def anchors(bundle):
            if bundle.external_ja_payload.payload == original + b'\n':
                if 'limit' in names: raise AlignmentLimitError('offline fixed cap')
                if 'ambiguity' in names: raise AlignmentAmbiguityError('offline ambiguity')
            return generate(bundle)
        adapter = adapters.build_external_ja_adapter(discovery=discovery,
            provider=SimpleNamespace(fetch_original_japanese_payload=fetch),
            acceptance_policy=changed_policy, residual_threshold_ms=100)
        diagnostic = {}
        with patch.object(adapters, 'generate_monotonic_anchor_candidates', side_effect=anchors):
            try:
                result = adapter(video, baseline, diagnostic_out=diagnostic)
            except Exception:
                assert diagnostic['candidate_count'] == len(names)
                if 'distinct' in names:
                    assert diagnostic['reason_code'] == 'ACCEPTED_CANDIDATE_CONFLICT'
                    assert diagnostic['accepted_candidate_count'] == 2
                elif any(name in names for name in
                         ('limit', 'ambiguity', 'transport', 'incomplete',
                          'identity', 'malformed-state')):
                    assert diagnostic['reason_code'] == 'CANDIDATE_EVALUATION_INDETERMINATE'
                    assert diagnostic['candidate_failures']
                raise
            finally:
                assert calls == (names if len(names) == 1 else sorted(names))
        assert diagnostic['candidate_count'] == len(names)
        if result is None:
            assert diagnostic['reason_code'] == 'NO_ACCEPTED_CANDIDATE'
            assert sum(item['count'] for item in diagnostic['candidate_failures']) <= len(names)
        elif result.decision.verdict == 'UNRESOLVED':
            assert diagnostic['reason_code'] == 'HYBRID_UNRESOLVED'
            assert diagnostic['accepted_candidate_count'] == 0
        elif result.decision.verdict == 'REJECT_EXTERNAL':
            assert diagnostic['reason_code'] == 'HYBRID_REJECTED'
            assert diagnostic['accepted_candidate_count'] == 0
        else:
            assert diagnostic['reason_code'] == 'HYBRID_ACCEPTED'
            assert diagnostic['accepted_candidate_count'] >= 1
        return result

    assert execute(['accept']).decision.verdict == 'ACCEPT_HYBRID'
    assert execute(['reject'], replace(policy, minimum_scale=1.01)).decision.verdict == 'REJECT_EXTERNAL'
    for other in ('detail-invalid', 'unresolved', 'invalid', 'no-consensus', 'duplicate'):
        assert execute(['accept', other]).decision.verdict == 'ACCEPT_HYBRID'
        print('PASS multi accept plus ' + other)
    for other in ('distinct', 'limit', 'ambiguity', 'transport', 'incomplete',
                  'identity', 'malformed-state'):
        expect(ExternalSubtitleValidationError, lambda: execute(['accept', other]))
        print('PASS multi fail closed ' + other)
    assert execute(['reject', 'duplicate'], replace(policy, minimum_scale=1.01)) is None
    assert execute(['invalid', 'detail-invalid']) is None
    assert execute(['unresolved', 'no-consensus']) is None
    left, right = execute(['duplicate', 'accept']), execute(['accept', 'duplicate'])
    assert left == right
    assert left.bundle.external_ja_payload.source_url.endswith('/accept-ja.srt')
    # An indeterminate early candidate never prevents evaluation of later ones.
    expect(ExternalSubtitleValidationError, lambda: execute(['transport', 'accept', 'unresolved']))
    print('PASS multi all nonaccept fallback, deterministic permutation, complete evaluation')


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
        multicandidate_smoke(baseline, policy)
        external_diagnostic = {}
        accepted = external(fixture.fixture.holding(), baseline,
                            diagnostic_out=external_diagnostic)
        assert accepted.decision.verdict == "ACCEPT_HYBRID"
        assert external_diagnostic == {
            'schema_version': 1, 'stage': 'hybrid', 'reason_code': 'HYBRID_ACCEPTED',
            'candidate_count': 1, 'http_status': None,
            'accepted_candidate_count': 1, 'candidate_failures': []}
        route_diagnostic = {}
        routed = fixture.controller._select_route(
            fixture.fixture.holding(), baseline, external,
            diagnostic_out=route_diagnostic)
        assert routed[0].route == 'HYBRID'
        assert route_diagnostic['reason_code'] == 'HYBRID_ACCEPTED'
        print("PASS safe external JA diagnostic through normal route selection")

        # A candidate whose URL passed the page parser but fails the stricter
        # candidate identity contract is a conclusive per-candidate rejection.
        # It must not block a separate candidate accepted by the existing
        # alignment policy.
        from teddy_discovery_subtitlecat_discovery import (
            SubtitleCatSearchCandidate,
            SubtitleCatSearchResult,
        )
        bad_detail_url = "https://subtitlecat.com/subs/1/a-invalid.html"
        good_detail_url = "https://subtitlecat.com/subs/1/z-valid.html"
        mixed_detail_calls = []
        mixed_payload_calls = []
        mixed_discovery = SimpleNamespace(discover=lambda **kwargs:
            SubtitleCatSearchResult(
                fixture.TITLE,
                (
                    SubtitleCatSearchCandidate(good_detail_url),
                    SubtitleCatSearchCandidate(bad_detail_url),
                ),
            )
        )

        def mixed_detail_fetch(url):
            mixed_detail_calls.append(url)
            if url == bad_detail_url:
                html = '<a href="/subs/1/original\u0080-ja.srt">Japanese</a>'
            else:
                html = '<a href="test-ja.srt">Japanese</a>'
            return SubtitleCatDetailPage(url, html)

        mixed_provider = SubtitleCatProvider(
            fetch_detail=mixed_detail_fetch,
            payload_fetcher=lambda candidate: mixed_payload_calls.append(candidate)
            or fixture.fixture.srt_bytes(tuple(
                (segment.start_ms, segment.end_ms, segment.text)
                for segment in baseline.segments
            )),
        )
        mixed_adapter = adapters.build_external_ja_adapter(
            discovery=mixed_discovery,
            provider=mixed_provider,
            acceptance_policy=policy,
            residual_threshold_ms=100,
        )
        mixed_diagnostic = {}
        mixed_result = mixed_adapter(
            fixture.fixture.holding(),
            baseline,
            diagnostic_out=mixed_diagnostic,
        )
        assert mixed_result.decision.verdict == "ACCEPT_HYBRID"
        assert mixed_diagnostic["candidate_failures"] == [{
            "stage": "detail_ja_link",
            "reason_code": "JA_LINK_INVALID",
            "http_status": None,
            "count": 1,
        }]
        assert mixed_diagnostic["accepted_candidate_count"] == 1
        assert mixed_detail_calls == [bad_detail_url, good_detail_url]
        assert len(mixed_payload_calls) == 1
        assert "detail_url" not in mixed_diagnostic
        print("PASS C1 candidate conclusive rejection preserves accepted HYBRID choice")

        malformed_provider = SubtitleCatProvider(
            fetch_detail=lambda url: SubtitleCatDetailPage(
                url,
                '<html><a href="test-ja.srt">Japanese</a></html>',
            ),
            payload_fetcher=lambda candidate: (
                b"0\n"
                b"00:00:00,000 --> 00:00:01,000\n"
                b"broken\n"
            ),
        )
        expect(
            ExternalSubtitleValidationError,
            lambda: adapters.build_external_ja_adapter(
                discovery=discovery(True),
                provider=malformed_provider,
                acceptance_policy=policy,
                residual_threshold_ms=100,
            )(fixture.fixture.holding(), baseline),
        )
        invalid_adapter = adapters.build_external_ja_adapter(
            discovery=discovery(True), provider=malformed_provider,
            acceptance_policy=policy, residual_threshold_ms=100)
        invalid_diagnostic = {}
        expect(ExternalSubtitleValidationError,
            lambda: invalid_adapter(fixture.fixture.holding(), baseline,
                                    diagnostic_out=invalid_diagnostic))
        assert invalid_diagnostic['stage'] == 'ja_srt_content'
        assert invalid_diagnostic['reason_code'] == 'SRT_CONTENT_INVALID'
        print("PASS malformed immutable external payload maps to validation failure")
        empty_adapter = adapters.build_external_ja_adapter(discovery=discovery(False),
            provider=provider, acceptance_policy=policy,
            residual_threshold_ms=100)
        empty_diagnostic = {}
        assert empty_adapter(fixture.fixture.holding(), baseline,
                             diagnostic_out=empty_diagnostic) is None
        assert empty_diagnostic['reason_code'] == 'SEARCH_NO_CANDIDATES'
        challenged = adapters.build_external_ja_adapter(
            discovery=SubtitleCatDiscovery(fetch=lambda req, timeout:
                SubtitleCatSearchResponse(200, req.full_url,
                    b'<html>Verify you are human</html>')),
            provider=provider, acceptance_policy=policy,
            residual_threshold_ms=100)
        challenged_diagnostic = {}
        assert challenged(fixture.fixture.holding(), baseline,
                          diagnostic_out=challenged_diagnostic) is None
        assert challenged_diagnostic['reason_code'] == 'SEARCH_BLOCK_PAGE'
        assert challenged_diagnostic['http_status'] == 200
        denied = adapters.build_external_ja_adapter(
            discovery=SubtitleCatDiscovery(fetch=lambda req, timeout:
                SubtitleCatSearchResponse(403, req.full_url, b'')),
            provider=provider, acceptance_policy=policy,
            residual_threshold_ms=100)
        denied_diagnostic = {}
        expect(SubtitleCatSearchTransportError,
            lambda: denied(fixture.fixture.holding(), baseline,
                           diagnostic_out=denied_diagnostic))
        assert denied_diagnostic['reason_code'] == 'SEARCH_HTTP_STATUS'
        assert denied_diagnostic['http_status'] == 403
        print("PASS empty, blocked and HTTP-error search diagnostics")
        missing_detail_provider = SubtitleCatProvider(
            fetch_detail=lambda url: SubtitleCatDetailPage(url, '<html></html>'),
            payload_fetcher=lambda candidate: b'not reached')
        missing_detail = adapters.build_external_ja_adapter(
            discovery=discovery(True), provider=missing_detail_provider,
            acceptance_policy=policy, residual_threshold_ms=100)
        missing_detail_diagnostic = {}
        expect(SubtitleCatDetailError,
            lambda: missing_detail(fixture.fixture.holding(), baseline,
                                   diagnostic_out=missing_detail_diagnostic))
        assert missing_detail_diagnostic['reason_code'] == 'JA_LINK_MISSING'
        failed_payload_provider = SubtitleCatProvider(
            fetch_detail=lambda url: SubtitleCatDetailPage(
                url, '<html><a href="test-ja.srt">Japanese</a></html>'),
            payload_fetcher=lambda candidate: (_ for _ in ()).throw(
                ExternalSubtitleTransportError('synthetic download failure')))
        failed_payload = adapters.build_external_ja_adapter(
            discovery=discovery(True), provider=failed_payload_provider,
            acceptance_policy=policy, residual_threshold_ms=100)
        failed_payload_diagnostic = {}
        expect(ExternalSubtitleTransportError,
            lambda: failed_payload(fixture.fixture.holding(), baseline,
                                   diagnostic_out=failed_payload_diagnostic))
        assert failed_payload_diagnostic['stage'] == 'ja_srt_download'
        print("PASS detail JA-link and SRT-download stage diagnostics")
        for changed, verdict in ((replace(policy, minimum_anchor_count=4), "UNRESOLVED"),
                                 (replace(policy, minimum_scale=1.01), "REJECT_EXTERNAL")):
            verdict_adapter = adapters.build_external_ja_adapter(discovery=discovery(True),
                provider=provider, acceptance_policy=changed,
                residual_threshold_ms=100)
            verdict_diagnostic = {}
            application = verdict_adapter(fixture.fixture.holding(), baseline,
                                          diagnostic_out=verdict_diagnostic)
            assert application.decision.verdict == verdict
            assert verdict_diagnostic['reason_code'] == (
                'HYBRID_UNRESOLVED' if verdict == 'UNRESOLVED' else 'HYBRID_REJECTED')
        def broken(**kwargs):
            raise ExternalSubtitleTransportError("offline failure")
        expect(ExternalSubtitleTransportError, lambda:
            adapters.build_external_ja_adapter(discovery=SimpleNamespace(discover=broken),
                provider=provider, acceptance_policy=policy,
                residual_threshold_ms=100)(fixture.fixture.holding(), baseline))
        def systemic(**kwargs):
            raise RuntimeError('offline synthetic configuration failure')
        systemic_adapter=adapters.build_external_ja_adapter(
            discovery=SimpleNamespace(discover=systemic),provider=provider,
            acceptance_policy=policy,residual_threshold_ms=100)
        systemic_diagnostic={}
        expect(RuntimeError,lambda:fixture.controller._select_route(
            fixture.fixture.holding(),baseline,systemic_adapter,
            diagnostic_out=systemic_diagnostic))
        assert systemic_diagnostic['stage']=='system'
        assert systemic_diagnostic['reason_code']=='SYSTEMIC_FAILURE'
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
            fake = fixture.FakeRuntime(
                baseline,
                stage_first_pass_artifacts=False,
            )

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
                result = replace(
                    fake._review_result(
                        request,
                        asr_quality_review_request_sha256(request),
                    ),
                    review_execution_session_id=state['fresh_asr_session_id'],
                )
                return serialize_asr_quality_review_result(result, request)

            def prepare_asr_session(sid):
                ensure_fresh_review_execution_session(sessions, sid,
                    expected_profile_name='subtitle-translator')
                state['fresh_asr_session_id'] = sid
                calls.append(('fresh', sid))

            def launcher(command, *, cwd, timeout):
                directory = Path('/proc/self/fd') / str(cwd)
                payload = (directory / QUALITY_REVIEW_INPUT_FILENAME).read_bytes()
                # Originals captured by the provider are independent of the wire.
                request = build_review_request(**originals(state['request']))
                assert parse_review_request(payload, **originals(request)) == request
                result = replace(
                    fake._review_result(request, review_request_sha256(request)),
                    review_execution_session_id=sessions.create_calls[-1][0],
                )
                _atomic_private_write(directory / QUALITY_REVIEW_RESULT_FILENAME,
                    serialize_review_result(result, request))
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
            diagnostic_files = list((artifacts / fixture.TITLE).glob(
                'external-ja-diagnostic-*.json'))
            assert len(diagnostic_files) == 1
            diagnostic_raw = diagnostic_files[0].read_bytes()
            diagnostic = __import__('json').loads(diagnostic_raw)
            assert diagnostic['reason_code'] == (
                'HYBRID_ACCEPTED' if route == 'HYBRID' else 'SEARCH_NO_CANDIDATES')
            assert candidate_url.encode() not in diagnostic_raw
            assert fixture.TITLE.encode() not in diagnostic_raw
            assert not any(segment.text.encode() in diagnostic_raw
                           for segment in baseline.segments)
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
