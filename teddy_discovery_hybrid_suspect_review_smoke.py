"""Offline suspect-only HYBRID regression; synthetic models/audio, private temp files."""
from dataclasses import replace
from contextlib import contextmanager
import ast
import inspect
import json
from pathlib import Path
import re
import shlex
from types import SimpleNamespace
import tempfile
import uuid

import numpy as np

import teddy_discovery_stage11_controller as controller
import teddy_discovery_stage11_controller_smoke as fixture
import teddy_discovery_stateful_quality_review as review
import teddy_discovery_stateful_quality_review_runner as runner
from teddy_discovery_stateful_translator import build_stateful_translator_command
from teddy_discovery_stateful_translator import serialize_stateful_model_input
from teddy_discovery_stateful_controller import build_stateful_part_query
from teddy_discovery_stateful_policy import STATEFUL_SEMANTIC_POLICY_16
from teddy_discovery_stateful_live_runner import _invoke_hermes_part
from teddy_discovery_hybrid_suspect_review import (
    select_suspect_cue_ids, merge_target_review_result, validate_suspect_artifact,
)
from teddy_discovery_targeted_asr_window import (
    STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1 as POLICY,
    plan_targeted_asr_windows_with_policy,
)
from teddy_discovery_targeted_asr_artifact import TargetedASRArtifact
from teddy_discovery_targeted_hybrid_evidence import TargetedASRWindowEvidence
from teddy_discovery_subtitle_v2_orchestrator import project_affine_timestamp_ms
from teddy_discovery_subtitle_text import parse_subtitle_bytes
from teddy_discovery_asr import ASRSegment
from teddy_discovery_asr_audio import ASRAudioChunk
from teddy_discovery_asr_source import ASRLocalMediaSource
from teddy_discovery_targeted_second_evidence_runner import run_targeted_hybrid_windows
from teddy_discovery_stage11_live_adapters import build_hybrid_review_adapter, build_targeted_adapter
from teddy_discovery_stage11_live_adapters_smoke import FakeNativeSessionDB
from teddy_discovery_stage11_deployment import _HybridOriginalRegistry
from teddy_discovery_stateful_hybrid import prepare_stateful_hybrid
from teddy_discovery_stateful_hybrid_smoke import semantic_result
from teddy_discovery_subtitle_source_quality import classify_source_document

passed = failed = 0


def check(name, condition):
    global passed, failed
    if not condition:
        failed += 1
        raise AssertionError(name)
    passed += 1
    print('PASS ' + name)


def reject(name, callback):
    try:
        callback()
    except (ValueError, RuntimeError):
        check(name, True)
    else:
        check(name, False)


def decision(cue_id, action):
    return review.QualityReviewResultCue(
        cue_id, action,
        {'KEEP': 'DIALOGUE', 'REPAIR': 'SEMANTIC_REPAIR', 'OMIT': 'METADATA',
         'AMBIGUOUS': 'AMBIGUOUS'}[action],
        'Synthetic independent source/audio/context supports this decision.',
        '待ってください' if action == 'REPAIR' else None,
        '잠깐 기다려 주세요.' if action == 'REPAIR' else None,
    )


class Runtime(fixture.FakeRuntime):
    mode = 'normal'

    def hybrid_review(self, request, *, staging_root, target_cue_ids=None, targeted_asr_artifact=None):
        self.hybrid_review_calls += 1
        self.last_hybrid_request = request
        ids = tuple(c.cue_id for c in request.cues)
        if target_cue_ids is None:
            actions = ('REPAIR', 'OMIT', 'AMBIGUOUS', 'KEEP')
            self.triage_request = request
        else:
            check('final model sees full title with target-only ownership', len(request.cues) == 4
                  and target_cue_ids == ids[:3] and targeted_asr_artifact is not None)
            check('targeted context attached only to suspects', all(c.raw_asr_context for c in request.cues[:3])
                  and request.cues[3].raw_asr_context == ())
            ids = target_cue_ids if self.mode != 'full-output' else ids
            actions = ('REPAIR', 'KEEP', 'AMBIGUOUS', 'OMIT')[:len(ids)]
        result = review.QualityReviewResult(request.schema_version, review.review_request_sha256(request),
            tuple(decision(cue_id, action) for cue_id, action in zip(ids, actions, strict=True)),
            request.source_translation_session_id, str(uuid.uuid4()))
        if target_cue_ids is None:
            self.triage = result
        return result

    def suspects(self, asr_result, windows):
        check('targeted execution follows first-pass and triage', self.first_pass_calls == 1
              and self.hybrid_review_calls == 1)
        self.suspect_windows = windows
        if self.mode == 'transport-failure':
            raise RuntimeError('synthetic targeted failure')
        evidence = TargetedASRArtifact(asr_result.source_snapshot, asr_result.runtime_identity,
            asr_result.engine_version, tuple(TargetedASRWindowEvidence(
                asr_result.source_snapshot, w.start_ms, w.end_ms, w.external_cue_ids,
                (ASRSegment(w.start_ms, w.end_ms, '待ってください'),),
            ) for w in windows))
        if self.mode == 'detached-source':
            snapshot = replace(asr_result.source_snapshot, source_mtime_ns=asr_result.source_snapshot.source_mtime_ns + 1)
            evidence = replace(evidence, source_snapshot=snapshot,
                               windows=tuple(replace(w, source_snapshot=snapshot) for w in evidence.windows))
        return evidence


def execute(artifacts, staging, runtime):
    return controller.run_one_title_stage11(fixture.TITLE, artifact_root=artifacts,
        stateful_staging_root=staging, claim_token=7, baseline_transcriber=runtime.baseline,
        external_ja_attempt=runtime.external_attempt, first_pass_runner=runtime.first_pass,
        asr_review_runner=runtime.asr_review, hybrid_review_runner=runtime.hybrid_review,
        targeted_runner=runtime.targeted, hybrid_targeted_runner=runtime.suspects,
        holding_resolver=runtime.holding)


def main():
    sid = str(uuid.uuid4())
    command = build_stateful_translator_command(sid)
    check('primary exact file,terminal toolset; skill tools inaccessible', command.count('-t') == 1
          and command[command.index('-t') + 1] == 'file,terminal'
          and set(command[command.index('-t') + 1].split(',')) == {'file', 'terminal'})
    tree = ast.parse(inspect.getsource(_invoke_hermes_part))
    script = next(node.value.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == 'remote_script' for t in node.targets))
    invocation = script.split('setsid ', 1)[1].split(' &', 1)[0]
    tokens = shlex.split(invocation.replace('\\\n', ' '))
    check('native SSH first-pass invocation also exact -t file,terminal', tokens.count('-t') == 1
          and tokens[tokens.index('-t') + 1] == 'file,terminal')
    check('primary prompt preserves conversational meaning and forbids skills',
          all(s in command[-1] for s in ('natural conversational Korean', 'speaker relationships',
              'Do not add meaning', 'Do not load or use skills', 'materially justified')))

    with tempfile.TemporaryDirectory() as root:
        artifacts, staging = fixture._roots(Path(root))
        runtime = Runtime(fixture.fixture.asr_result(), external=fixture.ACCEPT_HYBRID)
        result = execute(artifacts, staging, runtime)
        directory = artifacts / fixture.TITLE
        targets = select_suspect_cue_ids(runtime.triage_request, runtime.triage)
        ids = tuple(c.cue_id for c in runtime.triage_request.cues)
        check('suspect selection deterministic action != KEEP including AMBIGUOUS', targets == ids[:3]
              and select_suspect_cue_ids(runtime.triage_request, runtime.triage) == targets)
        merged = review.parse_review_result((directory / 'hybrid-final-review-v1.json').read_bytes(),
                                           runtime.last_hybrid_request)
        raw_target = review.parse_review_result((directory / 'hybrid-final-target-v1.json').read_bytes(),
                                               runtime.last_hybrid_request, target_cue_ids=targets)
        check('raw final target-only result contains exactly targets', tuple(c.cue_id for c in raw_target.cues) == targets)
        check('merge full ID/count/order exactly original', tuple(c.cue_id for c in merged.cues) == ids
              and len(merged.cues) == len(runtime.triage_request.cues))
        check('non-target deterministic KEEP and no replacements', merged.cues[3].action == review.KEEP
              and merged.cues[3].replacement_ja is None and merged.cues[3].replacement_ko is None)
        clean = parse_subtitle_bytes(result.clean_path.read_bytes(), 'srt')
        check('triage OMIT never directly alters CLEAN', len(clean.cues) == len(ids)
              and clean.cues[1].text == runtime.last_hybrid_request.cues[1].first_pass_ko)
        check('REPAIR alone applies replacement Korean', clean.cues[0].text == raw_target.cues[0].replacement_ko)
        check('AMBIGUOUS deterministic KEEP and non-target first-pass preserved',
              all(clean.cues[i].text == runtime.last_hybrid_request.cues[i].first_pass_ko for i in (1, 2, 3)))
        reject('target parser rejects model ownership of non-target cue', lambda: review.validate_review_result(
            merged, runtime.last_hybrid_request, target_cue_ids=targets))
        reject('target parser rejects reordered targets', lambda: review.validate_review_result(
            replace(raw_target, cues=tuple(reversed(raw_target.cues))), runtime.last_hybrid_request, target_cue_ids=targets))
        reject('target result rejects wrong request provenance', lambda: review.validate_review_result(
            replace(raw_target, request_sha256='0' * 64), runtime.last_hybrid_request, target_cue_ids=targets))
        reject('target result rejects wrong translation session', lambda: review.validate_review_result(
            replace(raw_target, source_translation_session_id='wrong-session'), runtime.last_hybrid_request, target_cue_ids=targets))
        reject('non-REPAIR replacement prohibited', lambda: replace(raw_target.cues[1], replacement_ko='추가'))
        query = runner.build_quality_review_command(sid, target_cue_ids=targets)[-1]
        check('final prompt requires full context but only target decisions and conservative evidence',
              'Read the entire title' in query and 'decisions ONLY' in query
              and 'OMIT requires sufficient proof' in query and 'Empty,' in query
              and 'Review EVERY cue in source order' not in query
              and 'Return exactly the same cue IDs' not in query)

        application = fixture.fixture.accepted_hybrid_route().alignment_application
        alignment = replace(application.alignment,
            intercept_ms=application.alignment.intercept_ms + 20_000.0,
            residuals=tuple(replace(residual,
                asr_midpoint_x2=residual.asr_midpoint_x2 + 40_000,
                predicted_asr_midpoint_ms=residual.predicted_asr_midpoint_ms + 20_000.0,
            ) for residual in application.alignment.residuals))
        external = application.bundle.external_ja_document.cues
        windows = plan_targeted_asr_windows_with_policy(external, alignment, policy=POLICY, target_cue_ids=targets)
        check('suspect windows use affine media timing, never raw external',
              windows[0].start_ms == project_affine_timestamp_ms(alignment, external[0].start_ms) - POLICY.pre_padding_ms
              and windows[0].start_ms != max(0, external[0].start_ms - POLICY.pre_padding_ms))
        check('existing generic policy and target membership preserved',
              (POLICY.pre_padding_ms, POLICY.post_padding_ms, POLICY.merge_gap_ms, POLICY.max_window_ms)
              == (5000, 5000, 10000, 60000)
              and tuple(cid for w in windows for cid in w.external_cue_ids) == targets
              and all(w.end_ms - w.start_ms <= POLICY.max_window_ms for w in windows))

        calls = []
        snapshot = runtime.asr_result.source_snapshot
        local = ASRLocalMediaSource(source_snapshot=snapshot,
            local_path=str(Path(root) / 'synthetic-media'), temp_directory=root)
        def audio(source, **kwargs):
            calls.append(('decode', kwargs))
            yield ASRAudioChunk(snapshot, round(kwargs['start_seconds'] * 1000),
                round(kwargs['end_seconds'] * 1000), 16000, np.zeros(16, dtype=np.float32))
        def transcribe(chunk):
            calls.append(('targeted', chunk.start_ms))
            return (ASRSegment(chunk.start_ms, chunk.end_ms, '待ってください'),)
        transport = SimpleNamespace(transcribe_targeted_chunk=transcribe,
            runtime_identity=runtime.asr_result.runtime_identity, engine_version=runtime.asr_result.engine_version)
        artifact = run_targeted_hybrid_windows(windows, local_source=local, targeted_transport=transport,
                                              audio_chunk_iterator=audio)
        check('shared targeted no-VAD method and bounded decoder reused', len(calls) == 2 * len(windows)
              and validate_suspect_artifact(artifact, source_snapshot=snapshot, windows=windows) == artifact)
        reject('raw-timeline or changed-window evidence rejected', lambda: validate_suspect_artifact(
            artifact, source_snapshot=snapshot, windows=runtime.suspect_windows))
        # Exercise the real native review runner and adapter with a fake launcher.
        prepared = prepare_stateful_hybrid(fixture.fixture.accepted_hybrid_route(), generation_key='suspect-fixture', claim_token=7)
        first = semantic_result(prepared.package)
        part_query = build_stateful_part_query(prepared.package, serialize_stateful_model_input(prepared.package), 1,
                                              semantic_policy=STATEFUL_SEMANTIC_POLICY_16)
        check('native part prompt shares natural translation and no-skill policy',
              all(s in part_query for s in ('natural conversational Korean', 'speaker relationships',
                  'Do not load or use skills', 'materially justified')))
        originals = dict(preparation=prepared, package=prepared.package, result=first,
                        source_quality=classify_source_document(prepared.route_decision.alignment_application.bundle.external_ja_document))
        request = review.build_review_request(**originals)
        one = (request.cues[0].cue_id,)
        target_result = review.QualityReviewResult(request.schema_version, review.review_request_sha256(request),
                                                   (decision(one[0], 'KEEP'),))
        native_dir = Path(root) / 'target-native'; native_dir.mkdir(mode=0o700)
        def launch(command, *, cwd, timeout):
            path = Path('/proc/self/fd/' + str(cwd)).resolve() / runner.QUALITY_REVIEW_RESULT_FILENAME
            path.write_bytes(review.serialize_review_result(target_result, request, target_cue_ids=one))
            path.chmod(0o600)
            return SimpleNamespace(returncode=0)
        native = runner.run_quality_review(native_dir, review.serialize_review_request(request),
            review_execution_session_id=sid, launcher=launch, target_cue_ids=one, **originals)
        check('native target-only runner binds fresh execution/source provenance', len(native.cues) == 1
              and native.source_translation_session_id == request.source_translation_session_id
              and native.review_execution_session_id == sid)
        baseline_request = request
        context = review.build_full_window_raw_asr_context(artifact, preparation=prepared)
        request = review.build_review_request(**originals, raw_asr_context=context)
        target_result = replace(target_result, request_sha256=review.review_request_sha256(request),
                                cues=tuple(decision(cue_id, 'KEEP') for cue_id in targets))
        one = targets
        registry = _HybridOriginalRegistry()
        route = prepared.route_decision
        registry.capture_external(lambda video, asr: route.alignment_application)(
            route.canonical_video, route.alignment_application.bundle.asr_result)
        registry.capture_first_pass(lambda package, **kwargs: first)(
            prepared.package, route='HYBRID', staging_root=staging)
        def provide_originals(value):
            assert value == baseline_request
            return registry.originals_provider(value)
        native_adapter = build_hybrid_review_adapter(originals_provider=provide_originals,
            runner_options=dict(launcher=launch, fresh_session_db=FakeNativeSessionDB(),
                                expected_profile_name='subtitle-translator'))
        native = native_adapter(request, staging_root=staging, target_cue_ids=targets,
                                targeted_asr_artifact=artifact)
        check('live final review adapter rebuilds evidence from artifact and binds native session',
              tuple(c.cue_id for c in native.cues) == targets
              and native.source_translation_session_id == request.source_translation_session_id)
        @contextmanager
        def copy_source(video, **kwargs):
            yield local
        source_adapter = build_targeted_adapter(holding_resolver=runtime.holding,
            source_provider=SimpleNamespace(copy_to_temp=copy_source), targeted_transport=transport,
            audio_chunk_iterator=audio, hybrid_suspects=True)
        adapter_artifact = source_adapter(runtime.asr_result, windows)
        check('live suspect adapter checks holding and local snapshots and shares targeted transport',
              adapter_artifact == artifact)
        replay = execute(artifacts, staging, runtime)
        check('completed HYBRID replay reuses validated CLEAN and evidence', replay.clean_reused and runtime.hybrid_review_calls == 2)
        provenance = directory / 'hybrid-suspect-context-v1.json'
        data = json.loads(provenance.read_bytes()); data['baseline_sha256'] = '0' * 64
        provenance.write_text(json.dumps(data)); provenance.chmod(0o600)
        reject('completed provenance mismatch fails closed', lambda: execute(artifacts, staging, runtime))

    for mode in ('transport-failure', 'detached-source', 'full-output'):
        with tempfile.TemporaryDirectory() as root:
            artifacts, staging = fixture._roots(Path(root))
            runtime = Runtime(fixture.fixture.asr_result(), external=fixture.ACCEPT_HYBRID); runtime.mode = mode
            reject(mode + ' fails closed before CLEAN', lambda: execute(artifacts, staging, runtime))
            check(mode + ' no CLEAN or completion report', not (artifacts / fixture.TITLE / controller.CLEAN_SRT_FILENAME).exists()
                  and not (artifacts / fixture.TITLE / controller.MECHANICAL_REPORT_FILENAME).exists())

    # Existing all-KEEP fixture proves empty triage scope needs no target runner.
    with tempfile.TemporaryDirectory() as root:
        artifacts, staging = fixture._roots(Path(root))
        runtime = fixture.FakeRuntime(fixture.fixture.asr_result(), fixture.ACCEPT_HYBRID)
        result = fixture._run(artifacts, staging, runtime)
        check('empty suspect scope skips targeted and final model; full deterministic KEEP',
              result.route == 'HYBRID' and runtime.hybrid_review_calls == 1
              and not (artifacts / fixture.TITLE / 'hybrid-suspect-asr-v1.json').exists())
    sources = [controller, runner]
    import teddy_discovery_hybrid_suspect_review as scope
    sources.append(scope)
    check('production source has no title/DVD/specific cue/dialogue hardcode',
          all(not re.search(r'\b[A-Z]{2,10}-\d{2,8}\b|(?:ja|asr)-\d{6}|[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]',
                            Path(module.__file__).read_text()) for module in sources))
    from teddy_discovery_stage12_bulk_runner import acceptance_policy
    check('production acceptance minimum remains 1800000ms',
          acceptance_policy().minimum_evidence_span_ms == 1_800_000)
    print(f'SUSPECT_SMOKE_PASS_COUNT={passed}')
    print(f'SUSPECT_SMOKE_FAIL_COUNT={failed}')


if __name__ == '__main__':
    main()
