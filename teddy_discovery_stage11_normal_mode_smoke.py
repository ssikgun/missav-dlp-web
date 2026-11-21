"""Offline normal-mode failure, immutable readback and bounded native contracts.

Synthetic transport fixtures are never presented as live translation evidence.
"""
import base64
from dataclasses import replace
from contextlib import contextmanager
import json
from pathlib import Path
import stat
import tempfile
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import teddy_discovery_stage11_normal_mode as normal
import teddy_discovery_stage11_controller_smoke as fixture
import teddy_discovery_stage11_live_adapters as live_adapters
import teddy_discovery_asr_bounded_worker as bounded_worker
import teddy_discovery_stage11_deployment as deployment
import teddy_discovery_stateful_quality_review as review
from teddy_discovery_alignment_acceptance_smoke import policy_with
from teddy_discovery_stateful_translator import StatefulAbsorptionResult, StatefulCueOutput
from teddy_discovery_stage11_deployment import Stage11DeploymentTransportError
from teddy_discovery_subtitle_external import SubtitleCatProvider, SubtitleCatDetailPage
from teddy_discovery_subtitlecat_discovery import SubtitleCatDiscovery, SubtitleCatSearchResponse
from teddy_discovery_asr import ASRSegment
from teddy_discovery_hybrid_evidence import HybridCueIdentity
from teddy_discovery_targeted_asr_artifact import TargetedASRArtifact
from teddy_discovery_targeted_hybrid_evidence import TargetedASRWindowEvidence


class NormalSmoke(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name); self.artifacts=root/'artifacts'; self.staging=root/'staging'
        for p in (self.artifacts,self.staging): p.mkdir(mode=0o700)
        self.route=fixture.fixture.accepted_hybrid_route()
        self.baseline=self.route.alignment_application.bundle.asr_result
        self.first_calls=0; self.review_calls=0; self.targeted_calls=0
        self.triage_actions=None
        self.align=patch.object(normal,'_align_external_payload',return_value=self.route.alignment_application)
        self.align.start(); self.addCleanup(self.align.stop)
        for target in ('subprocess.run','subprocess.Popen','socket.socket'):
            p=patch(target,side_effect=AssertionError('offline tests forbid network/processes'))
            p.start(); self.addCleanup(p.stop)

    def first(self, package, *, boundary_evidence, **unused):
        self.first_calls+=1
        return StatefulAbsorptionResult(package.schema_version,package.dvd_id,package.generation_key,
            package.claim_token,normal.stateful_session_id_for_package(package),
            tuple(StatefulCueOutput(c.cue_id,None,'검증용 번역 '+str(i),None) for i,c in enumerate(package.cues)),boundary_evidence)

    def review(self, request, *, staging_root, target_cue_ids=None,
               targeted_asr_artifact=None):
        self.review_calls+=1
        ids=(tuple(c.cue_id for c in request.cues) if target_cue_ids is None
             else target_cue_ids)
        if target_cue_ids is None:
            actions=(self.triage_actions if self.triage_actions is not None
                     else (review.KEEP,)*len(ids))
            if targeted_asr_artifact is not None:
                self.fail('triage must not receive targeted evidence')
        else:
            if targeted_asr_artifact is None:
                self.fail('target review requires exact targeted artifact')
            actions=(review.REPAIR,)*len(ids)
        categories={review.KEEP:'DIALOGUE',review.REPAIR:'SEMANTIC_REPAIR',
                    review.OMIT:'SOURCE_NOISE',review.AMBIGUOUS:'AMBIGUOUS'}
        cues=tuple(review.QualityReviewResultCue(
            cue_id,action,categories[action],'Synthetic offline evidence supports the decision.',
            '修正版' if action==review.REPAIR else None,
            '검수 수정본' if action==review.REPAIR else None)
            for cue_id,action in zip(ids,actions,strict=True))
        return review.QualityReviewResult(
            review.STATEFUL_QUALITY_REVIEW_SCHEMA_VERSION,
            review.review_request_sha256(request),cues,
            request.source_translation_session_id,str(uuid.uuid4()))

    def targeted(self, asr_result, windows):
        self.targeted_calls+=1
        return TargetedASRArtifact(
            asr_result.source_snapshot,asr_result.runtime_identity,asr_result.engine_version,
            tuple(TargetedASRWindowEvidence(
                asr_result.source_snapshot,window.start_ms,window.end_ms,
                window.external_cue_ids,
                (ASRSegment(window.start_ms,window.end_ms,'補助音声'),))
                for window in windows))

    def run_title(self, **overrides):
        kwargs=dict(artifact_root=self.artifacts,stateful_staging_root=self.staging,claim_token=1,
            holding_resolver=lambda _:fixture._holding(self.baseline),baseline_transcriber=lambda _:self.baseline,
            external_ja_attempt=lambda *_:self.route.alignment_application,first_pass_runner=self.first,
            acceptance_policy=policy_with(),targeted_runner=lambda *_:self.fail('optional STT ran'),
            hybrid_review_runner=self.review,hybrid_targeted_runner=self.targeted)
        kwargs.update(overrides)
        return normal.run_one_title_normal_mode(self.baseline.source_snapshot.dvd_id,**kwargs)

    def test_hybrid_reviewed_clean_completes_and_replays_without_models(self):
        baseline_formats=[]
        result=self.run_title(baseline_transcriber=lambda video: baseline_formats.append(video.video_format) or self.baseline)
        proof=json.loads((result.report_path.parent/normal.PROOF_NAME).read_bytes())
        report=json.loads(result.report_path.read_bytes())
        self.assertEqual(proof['user_intervention'],0)
        self.assertFalse(proof['automatic_insertion'])
        self.assertEqual(proof['ambiguous_policy'],'EXTERNAL_JA_AND_PRIMARY_KO')
        self.assertEqual(proof['quality_review'],'HYBRID_REVIEWED_CLEAN_V1')
        evidence=proof['review_evidence']
        self.assertEqual(evidence['targeted_source_count'],0)
        self.assertEqual(evidence['targeted_window_count'],0)
        self.assertEqual(evidence['review_result_sha256'],report['review_result_identity']['result_sha256'])
        self.assertIsNotNone(evidence['source_translation_session_id_sha256'])
        self.assertIsNotNone(evidence['review_execution_session_id_sha256'])
        self.assertTrue(result.clean_path.is_file())
        self.assertEqual(baseline_formats,['mp4'])
        self.assertEqual((result.report_path.parent/'normal-external-ja.srt').read_bytes(),
            self.route.alignment_application.bundle.external_ja_payload.payload)
        baseline_raw=(result.report_path.parent/normal.controller.BASELINE_ASR_FILENAME).read_bytes()
        self.assertEqual(baseline_raw,normal.controller.serialize_asr_result(self.baseline))
        self.assertEqual(report['baseline_sha256'],normal.sha(baseline_raw))
        self.assertIs(report['publication_performed'],False)
        self.assertEqual((self.first_calls,self.review_calls,self.targeted_calls),(1,1,0))
        repeated=self.run_title(first_pass_runner=lambda *_a,**_k:self.fail('resume called Hermes'))
        self.assertEqual(repeated.clean_sha256,result.clean_sha256)
        self.assertEqual((self.review_calls,self.targeted_calls),(1,0))

    def test_suspect_only_targeted_asr_is_bound_to_original_and_repair(self):
        self.triage_actions=(review.REPAIR,review.KEEP,review.KEEP,review.KEEP)
        result=self.run_title()
        directory=result.report_path.parent
        proof=json.loads((directory/normal.PROOF_NAME).read_bytes())
        evidence=proof['review_evidence']
        report=json.loads(result.report_path.read_bytes())
        clean=normal.controller.parse_subtitle_bytes(result.clean_path.read_bytes(),'srt')
        self.assertEqual(self.targeted_calls,1)
        self.assertEqual(self.review_calls,2)
        self.assertEqual(evidence['targeted_source_count'],1)
        self.assertEqual(evidence['targeted_window_count'],1)
        self.assertEqual(report['targeted_source_count'],1)
        self.assertIs(report['targeted_reused'],False)
        self.assertIs(result.targeted_reused,False)
        self.assertEqual(clean.cues[0].text,'검수 수정본')
        self.assertEqual(proof['playback'][0]['ja'],'修正版')
        targeted=normal.controller.parse_targeted_asr_artifact_bytes(
            (directory/'hybrid-suspect-asr-v1.json').read_bytes())
        self.assertEqual(targeted.source_snapshot,self.baseline.source_snapshot)
        self.assertEqual(targeted.windows[0].external_cue_ids,
                         (HybridCueIdentity.for_external_ja(0).cue_id,))
        validated=normal.controller._validate_existing_completion(
            result.report_path,result.clean_path,
            directory/normal.controller.BASELINE_ASR_FILENAME,title=result.title,
            baseline_sha256=report['baseline_sha256'],baseline_reused=False,
            source_quality_counts=report['source_quality_counts'],targeted_reused=False,
            targeted_source_count=1,targeted_window_count=1)
        self.assertEqual(validated.clean_sha256,result.clean_sha256)

    def test_deployment_registry_captures_native_normal_boundary_evidence(self):
        from teddy_discovery_stage11_deployment import _HybridOriginalRegistry
        preparation,boundary=normal.prepare_normal(
            self.route,normal.sha(normal.controller.serialize_asr_result(self.baseline)),1)
        registry=_HybridOriginalRegistry()
        registry.capture_external(lambda _video,_asr:self.route.alignment_application)(
            self.route.canonical_video,self.baseline)
        callback=registry.capture_first_pass(self.first)
        first=callback(preparation.package,route='HYBRID',staging_root=self.staging,
                       boundary_evidence=boundary)
        source_quality=normal.classify_source_document(
            self.route.alignment_application.bundle.external_ja_document)
        request=review.build_review_request(
            preparation=preparation,package=preparation.package,result=first,
            source_quality=source_quality)
        retained=registry.originals_provider(request)
        self.assertEqual(retained['package'],preparation.package)
        self.assertEqual(retained['result'],first)
        self.assertEqual(retained['preparation'].package,preparation.package)

    def test_normal_cli_captures_native_and_local_ja_for_review(self):
        from teddy_discovery_stage11_deployment import (
            Stage11DeploymentDependencies, _HybridOriginalRegistry,
        )
        import teddy_discovery_stage12_bulk_runner as bulk
        import teddy_discovery_stage12_rollout as rollout

        # Exercise the real local parser callback. A synthetic approved affine
        # alignment is rebound to the CLI's local bytes by the existing pure
        # application boundary, so no model or network is involved.
        from teddy_discovery_alignment_application import apply_alignment_acceptance
        from teddy_discovery_hybrid_evidence import (
            ALIGNMENT_PROVENANCE_UNRESOLVED, HybridAlignmentProvenance,
            HybridEvidenceBundle,
        )
        def align_local_payload(payload, title, baseline, _policy, _threshold):
            bundle=HybridEvidenceBundle.from_external_ja_and_asr(
                dvd_id=title,external_ja_payload=payload,asr_result=baseline,
                alignment=HybridAlignmentProvenance(
                    ALIGNMENT_PROVENANCE_UNRESOLVED,'lexical-affine'))
            accepted=self.route.alignment_application
            return apply_alignment_acceptance(
                bundle,accepted.decision,alignment=accepted.alignment)
        registry=_HybridOriginalRegistry()
        retained={}
        first_boundary={}
        def cli_first_pass(package, **kwargs):
            first_boundary['value']=kwargs.get('boundary_evidence')
            return self.first(package,**kwargs)
        def review_with_retained_originals(request, *, staging_root,
                                           target_cue_ids=None,
                                           targeted_asr_artifact=None):
            retained.update(registry.originals_provider(request))
            return self.review(request,staging_root=staging_root,
                target_cue_ids=target_cue_ids,
                targeted_asr_artifact=targeted_asr_artifact)
        live=SimpleNamespace(
            holding_resolver=lambda _title:fixture._holding(self.baseline),
            baseline_transcriber=lambda _video:self.baseline,
            external_ja_attempt=registry.capture_external(lambda *_args:None),
            targeted_runner=lambda *_args:self.fail('unused targeted runner'),
            first_pass_runner=lambda *_args,**_kwargs:self.fail('CLI must inject native first pass'),
            asr_review_runner=lambda *_args:self.fail('unused ASR review runner'),
            hybrid_review_runner=review_with_retained_originals,
            hybrid_targeted_runner=self.targeted,
        )
        dependencies=Stage11DeploymentDependencies(
            config=object(),source_provider=None,whisper=None,targeted_transport=None,
            discovery=None,provider=None,remote_bridge=object(),
            remote_task_for_session=lambda *_args:None,prepare_remote=lambda *_args:None,
            originals_provider=registry.originals_provider,live=live,
            _first_pass_capture=registry.capture_first_pass,
            _external_capture=registry.capture_external)
        local_ja=self.artifacts.parent/'cli-local-ja.srt'
        local_raw=self.route.alignment_application.bundle.external_ja_payload.payload
        local_ja.write_bytes(local_raw)
        snapshot=self.baseline.source_snapshot
        fs=SimpleNamespace(lstat=lambda _path:SimpleNamespace(
            st_mode=stat.S_IFREG|0o600,st_size=snapshot.source_size,
            st_mtime_ns=snapshot.source_mtime_ns))
        run_root=self.artifacts.parent/'cli-run'
        with patch.object(bulk,'build_deployment_config',return_value=object()), \
             patch.object(bulk,'build_dependencies',return_value=dependencies), \
             patch.object(bulk,'acceptance_policy',return_value=policy_with()), \
             patch.object(rollout,'build_nas_preflight_filesystem',return_value=fs), \
             patch.object(bulk,'NAS',{}), \
             patch.object(normal,'_align_external_payload',side_effect=align_local_payload), \
             patch.object(normal,'NativeNormalFirstPass',side_effect=lambda _bridge:cli_first_pass), \
             patch('sys.argv',['stage11-normal','--dvd-id',self.baseline.source_snapshot.dvd_id,
                               '--run-root',str(run_root),'--external-ja',str(local_ja)]):
            self.assertEqual(normal.main(),0)

        self.assertEqual((self.first_calls,self.review_calls,self.targeted_calls),(1,1,0))
        self.assertEqual(retained['package'].dvd_id,self.baseline.source_snapshot.dvd_id)
        self.assertEqual(retained['result'].session_id,
                         normal.stateful_session_id_for_package(retained['package']))
        self.assertEqual(retained['result'].boundary_evidence,first_boundary['value'])
        application=retained['preparation'].route_decision.alignment_application
        self.assertEqual(application.bundle.external_ja_payload.payload,local_raw)
        self.assertTrue(application.bundle.external_ja_payload.candidate.external_source_id.startswith(
            'local-sha256-'))
        self.assertEqual(application.decision.verdict,'ACCEPT_HYBRID')
        generated=run_root/'artifacts'/self.baseline.source_snapshot.dvd_id
        self.assertTrue((generated/'clean-ko-v1.srt').is_file())
        self.assertEqual((generated/'normal-external-ja.srt').read_bytes(),local_raw)

    def test_review_failure_or_missing_review_sidecar_blocks_completion(self):
        with self.assertRaisesRegex(RuntimeError,'review transport failed'):
            self.run_title(hybrid_review_runner=lambda *_a,**_k:
                           (_ for _ in ()).throw(RuntimeError('review transport failed')))
        directory=next(self.artifacts.iterdir())
        self.assertFalse((directory/'clean-ko-v1.srt').exists())
        self.assertFalse((directory/'stage11-controller-report-v1.json').exists())
        successful=self.run_title()
        (successful.report_path.parent/'hybrid-final-review-v1.json').unlink()
        with self.assertRaises(normal.controller.Stage11ControllerArtifactError):
            self.run_title()

    def test_review_sha_and_primary_only_proof_cannot_be_promoted(self):
        result=self.run_title(); directory=result.report_path.parent
        triage=directory/'hybrid-triage-v1.json'
        triage.write_bytes(triage.read_bytes()+b' ')
        with self.assertRaises(normal.controller.Stage11ControllerArtifactError):
            self.run_title()
        triage.write_bytes(normal.wire(json.loads(triage.read_bytes())))
        proof_path=directory/normal.PROOF_NAME
        proof=json.loads(proof_path.read_bytes()); proof['quality_review']='PRIMARY_TRANSLATION_ONLY'
        proof_path.write_bytes(normal.wire(proof))
        with self.assertRaises(normal.controller.Stage11ControllerArtifactError):
            self.run_title()

    def test_non_mp4_fails_before_baseline_or_model_calls(self):
        holding=fixture._holding(self.baseline)
        holding['relative_path']=holding['relative_path'][:-4]+'.ts'
        calls=[]
        def forbidden(name):
            def invoke(*_args,**_kwargs):
                calls.append(name)
                self.fail(name+' must not run for a non-MP4 input')
            return invoke
        with self.assertRaises(normal.controller.Stage11ControllerValidationError) as raised:
            self.run_title(holding_resolver=lambda _title:holding,
                baseline_transcriber=forbidden('whisper'),
                external_ja_attempt=forbidden('external_ja'),
                first_pass_runner=forbidden('hermes'))
        self.assertIn('normal mode requires canonical MP4 input',str(raised.exception))
        self.assertEqual(calls,[])
        failure=json.loads(next(self.artifacts.glob('*/normal-failure-*.json')).read_bytes())
        self.assertEqual(failure['error_type'],'Stage11ControllerValidationError')
        self.assertFalse(list(self.artifacts.glob('*/normal-external-ja.srt')))
        self.assertFalse(list(self.artifacts.glob('*/clean-ko-v1.srt')))

    def test_missing_ja_fails_and_saves_reason(self):
        with self.assertRaises(normal.controller.Stage11ControllerValidationError):
            self.run_title(external_ja_attempt=lambda *_:None)
        self.assertEqual(len(list(self.artifacts.glob('*/normal-failure-*.json'))),1)
        self.assertFalse(list(self.artifacts.glob('*/clean-ko-v1.srt')))

    def test_safe_hybrid_diagnostic_sidecar_is_written(self):
        detail_url='https://subtitlecat.com/subs/1/diagnostic-test.html'
        discovery=SubtitleCatDiscovery(fetch=lambda request,timeout: SubtitleCatSearchResponse(
            200,request.full_url,('<html><a href="'+detail_url+'">'
                +fixture.TITLE+'</a></html>').encode()))
        provider=SubtitleCatProvider(
            fetch_detail=lambda url:SubtitleCatDetailPage(url,
                '<html><a href="diagnostic-ja.srt">Japanese</a></html>'),
            payload_fetcher=lambda candidate:fixture.fixture.srt_bytes(tuple(
                (segment.start_ms,segment.end_ms,segment.text)
                for segment in self.baseline.segments)))
        attempt=live_adapters.build_external_ja_adapter(discovery=discovery,
            provider=provider,acceptance_policy=policy_with(),residual_threshold_ms=100)
        with patch.object(live_adapters,'_align_external_payload',
                return_value=self.route.alignment_application):
            result=self.run_title(external_ja_attempt=attempt)
        self.assertTrue(result.clean_path.is_file())
        sidecars=list(result.report_path.parent.glob('external-ja-diagnostic-*.json'))
        self.assertEqual(len(sidecars),1)
        raw=sidecars[0].read_bytes(); diagnostic=json.loads(raw)
        self.assertEqual(diagnostic['reason_code'],'HYBRID_ACCEPTED')
        self.assertNotIn(detail_url.encode(),raw)
        self.assertNotIn(fixture.TITLE.encode(),raw)
        self.assertNotIn(self.baseline.segments[0].text.encode(),raw)

    def test_detail_failure_diagnostic_sidecar_preserves_normal_gate(self):
        detail_url='https://subtitlecat.com/subs/1/missing-ja.html'
        discovery=SubtitleCatDiscovery(fetch=lambda request,timeout: SubtitleCatSearchResponse(
            200,request.full_url,('<html><a href="'+detail_url+'">'
                +fixture.TITLE+'</a></html>').encode()))
        provider=SubtitleCatProvider(
            fetch_detail=lambda url:SubtitleCatDetailPage(url,'<html></html>'),
            payload_fetcher=lambda candidate:self.fail('payload must not run'))
        attempt=live_adapters.build_external_ja_adapter(discovery=discovery,
            provider=provider,acceptance_policy=policy_with(),residual_threshold_ms=100)
        with self.assertRaises(normal.controller.Stage11ControllerValidationError):
            self.run_title(external_ja_attempt=attempt)
        directory=next(self.artifacts.iterdir())
        sidecars=list(directory.glob('external-ja-diagnostic-*.json'))
        self.assertEqual(len(sidecars),1)
        diagnostic=json.loads(sidecars[0].read_bytes())
        self.assertEqual(diagnostic['stage'],'detail_ja_link')
        self.assertEqual(diagnostic['reason_code'],'JA_LINK_MISSING')
        self.assertFalse(list(directory.glob('normal-external-ja.srt')))
        self.assertFalse(list(directory.glob('clean-ko-v1.srt')))

    def test_transport_failure_is_terminal_without_user_wait(self):
        def fail(*_a,**_k): raise Stage11DeploymentTransportError('offline Hermes outage')
        with self.assertRaises(Stage11DeploymentTransportError): self.run_title(first_pass_runner=fail)
        state=json.loads(next(self.artifacts.glob('*/normal-failure-*.json')).read_bytes())
        self.assertEqual(state['status'],'FAILED'); self.assertEqual(state['user_intervention'],0)

    def test_identity_or_format_mismatch_cannot_generate_srt(self):
        def wrong(package,**kwargs): return replace(self.first(package,**kwargs),claim_token=2)
        with self.assertRaises(normal.controller.Stage11ControllerValidationError): self.run_title(first_pass_runner=wrong)
        self.assertFalse(list(self.artifacts.glob('*/clean-ko-v1.srt')))

    def test_changed_original_or_output_rejected_on_readback(self):
        result=self.run_title(); directory=result.report_path.parent
        original=(directory/'normal-external-ja.srt').read_bytes()
        (directory/'normal-external-ja.srt').write_bytes(original+b'\n')
        with self.assertRaises(normal.controller.Stage11ControllerArtifactError): self.run_title()
        (directory/'normal-external-ja.srt').write_bytes(original)
        result.clean_path.write_bytes(result.clean_path.read_bytes()+b'\n')
        with self.assertRaises(normal.controller.Stage11ControllerArtifactError): self.run_title()

    def test_stage12_completion_contract_accepts_normal_proof(self):
        result=self.run_title(); report=json.loads(result.report_path.read_bytes())
        validated=normal.controller._validate_existing_completion(result.report_path,result.clean_path,
            result.report_path.parent/normal.controller.BASELINE_ASR_FILENAME,title=result.title,
            baseline_sha256=report['baseline_sha256'],baseline_reused=False,
            source_quality_counts=report['source_quality_counts'],targeted_reused=None,
            targeted_source_count=0,targeted_window_count=0)
        self.assertEqual(validated.clean_sha256,result.clean_sha256)

    def test_dual_budget_proof_is_opt_in_and_source_bound(self):
        callback=lambda *_args:self.route.alignment_application
        callback._stage11_alignment_budget_profile=normal.DUAL_BUDGET_PROVENANCE['mode']
        result=self.run_title(
            external_ja_attempt=callback,
            alignment_budget_profile=normal.DUAL_BUDGET_PROVENANCE['mode'])
        directory=result.report_path.parent
        source_path=directory/normal.SOURCE_NAME
        proof_path=directory/normal.PROOF_NAME
        source=json.loads(source_path.read_bytes())
        proof=json.loads(proof_path.read_bytes())
        self.assertEqual(source['alignment_budget'],normal.DUAL_BUDGET_PROVENANCE)
        self.assertEqual(proof['alignment_budget'],normal.DUAL_BUDGET_PROVENANCE)
        self.assertEqual(result.clean_sha256,normal.validate_normal_completion(
            result.report_path,result.clean_path,
            directory/normal.controller.BASELINE_ASR_FILENAME,
            title=result.title).clean_sha256)
        source['alignment_budget']['new_exact_slopes']+=1
        source_path.write_bytes(normal.wire(source))
        with self.assertRaises(normal.controller.Stage11ControllerArtifactError):
            normal.validate_normal_completion(
                result.report_path,result.clean_path,
                directory/normal.controller.BASELINE_ASR_FILENAME,
                title=result.title)

    def test_explicit_single_title_regeneration_reuses_bound_inputs(self):
        import teddy_discovery_stage11_regeneration as regeneration
        root=Path(self.temp.name)/'regen'
        root.mkdir(mode=0o700)
        baseline_path=root/'baseline-asr-v1.json'
        baseline_raw=normal.controller.serialize_asr_result(self.baseline)
        baseline_path.write_bytes(baseline_raw); baseline_path.chmod(0o600)
        ja_path=root/'retained-ja.srt'
        ja_raw=self.route.alignment_application.bundle.external_ja_payload.payload
        ja_path.write_bytes(ja_raw); ja_path.chmod(0o600)
        verified=[]

        class Dependencies:
            remote_bridge=object()
            def controller_kwargs(_self):
                return {
                    'holding_resolver':lambda _title:fixture._holding(self.baseline),
                    'targeted_runner':lambda *_args:self.fail('unexpected targeted runner'),
                    'asr_review_runner':lambda *_args:self.fail('unexpected ASR review'),
                    'hybrid_review_runner':self.review,
                    'hybrid_targeted_runner':self.targeted,
                }
            def capture_external_ja_attempt(_self,callback): return callback
            def capture_first_pass_runner(_self,_callback): return self.first

        class AcquiredLock:
            status=regeneration.ACQUIRED
            def __enter__(self): return self
            def __exit__(self,*_args): return False

        dependencies=Dependencies()
        with patch.object(regeneration,'configured_lock_dir',return_value=root/'locks'), \
             patch.object(regeneration,'try_acquire_title_lock',return_value=AcquiredLock()):
            result=regeneration.regenerate_one_title(
                self.baseline.source_snapshot.dvd_id,
                run_root=root/'new-private-output',
                baseline_path=baseline_path,
                baseline_sha256=normal.sha(baseline_raw),
                japanese_srt_path=ja_path,
                japanese_srt_sha256=normal.sha(ja_raw),
                japanese_srt_source_id=(
                    self.route.alignment_application.bundle.external_ja_payload
                    .candidate.external_source_id),
                dependencies=dependencies,
                acceptance_policy=policy_with(),
                source_verifier=lambda video,snapshot:verified.append((video,snapshot)),
                claim_token=1)
        self.assertEqual(len(verified),2)
        self.assertEqual(result.title,self.baseline.source_snapshot.dvd_id)
        self.assertIs(json.loads(result.report_path.read_bytes())['publication_performed'],False)
        self.assertEqual(result.route,'HYBRID')
        self.assertEqual(json.loads((result.report_path.parent/normal.SOURCE_NAME).read_bytes())['source_id'],
            self.route.alignment_application.bundle.external_ja_payload.candidate.external_source_id)
        self.assertTrue(result.clean_path.is_file())
        self.assertEqual((self.first_calls,self.review_calls,self.targeted_calls),(1,1,0))
        self.assertTrue((root/'new-private-output'/'artifacts'/result.title/
                         normal.controller.CLEAN_SRT_FILENAME).is_file())

        self.triage_actions=(review.REPAIR,review.KEEP,review.KEEP,review.KEEP)
        with patch.object(regeneration,'configured_lock_dir',return_value=root/'locks'), \
             patch.object(regeneration,'try_acquire_title_lock',return_value=AcquiredLock()):
            with self.assertRaises(normal.controller.Stage11ControllerValidationError):
                regeneration.regenerate_one_title(
                    self.baseline.source_snapshot.dvd_id,
                    run_root=root/'targeted-needed-output',
                    baseline_path=baseline_path,
                    baseline_sha256=normal.sha(baseline_raw),
                    japanese_srt_path=ja_path,
                    japanese_srt_sha256=normal.sha(ja_raw),
                    japanese_srt_source_id=(
                        self.route.alignment_application.bundle.external_ja_payload
                        .candidate.external_source_id),
                    dependencies=dependencies,
                    acceptance_policy=policy_with(),
                    source_verifier=lambda video,snapshot:verified.append((video,snapshot)),
                    claim_token=2)
        self.assertEqual(self.targeted_calls,0)
        self.assertFalse((root/'targeted-needed-output'/'artifacts'/result.title/
                          normal.controller.CLEAN_SRT_FILENAME).exists())

    def test_regeneration_reacquires_missing_or_detached_historical_inputs(self):
        import teddy_discovery_stage11_regeneration as regeneration
        root=Path(self.temp.name)/'regen-acquire'
        root.mkdir(mode=0o700)
        acquired={'baseline':0,'japanese':0}
        verified=[]

        class Dependencies:
            remote_bridge=object()
            fail_external=False
            def controller_kwargs(_self):
                def baseline(_video):
                    acquired['baseline']+=1
                    return self.baseline
                def external(_video,_baseline):
                    acquired['japanese']+=1
                    if _self.fail_external:
                        raise RuntimeError('synthetic subtitle acquisition failure')
                    return self.route.alignment_application
                return {
                    'holding_resolver':lambda _title:fixture._holding(self.baseline),
                    'baseline_transcriber':baseline,
                    'external_ja_attempt':external,
                    'targeted_runner':lambda *_args:self.fail('unbounded targeted ASR used'),
                    'asr_review_runner':lambda *_args:self.fail('unexpected ASR review'),
                    'hybrid_review_runner':self.review,
                    'hybrid_targeted_runner':self.targeted,
                }
            def capture_external_ja_attempt(_self,callback): return callback
            def capture_first_pass_runner(_self,_callback): return self.first

        class AcquiredLock:
            status=regeneration.ACQUIRED
            def __enter__(self): return self
            def __exit__(self,*_args): return False

        old_ko=root/'existing-ko.srt'
        old_ko.write_bytes(b'preserved-existing-korean')
        old_ko.chmod(0o600)
        rollout=root/'rollout-state.sqlite3'
        rollout.write_bytes(b'unchanged-state')
        rollout.chmod(0o600)
        old_ko_before=old_ko.read_bytes(); rollout_before=rollout.read_bytes()
        stale=replace(self.baseline,source_snapshot=replace(
            self.baseline.source_snapshot,
            source_size=self.baseline.source_snapshot.source_size+1))
        stale_raw=normal.controller.serialize_asr_result(stale)
        stale_path=root/'stale-baseline.json'
        stale_path.write_bytes(stale_raw); stale_path.chmod(0o600)
        absent_ja=root/'missing-ja.srt'
        ja_raw=self.route.alignment_application.bundle.external_ja_payload.payload
        with patch.object(regeneration,'configured_lock_dir',return_value=root/'locks'), \
             patch.object(regeneration,'try_acquire_title_lock',return_value=AcquiredLock()):
            result=regeneration.regenerate_one_title(
                self.baseline.source_snapshot.dvd_id,
                run_root=root/'private-run',
                baseline_path=stale_path,
                baseline_sha256=normal.sha(stale_raw),
                japanese_srt_path=absent_ja,
                japanese_srt_sha256=normal.sha(ja_raw),
                japanese_srt_source_id=(
                    self.route.alignment_application.bundle.external_ja_payload
                    .candidate.external_source_id),
                dependencies=Dependencies(),
                acceptance_policy=policy_with(),
                source_verifier=lambda video,snapshot:verified.append((video,snapshot)),
                claim_token=11)
        self.assertEqual(acquired,{'baseline':1,'japanese':1})
        self.assertEqual(result.route,'HYBRID')
        self.assertTrue(result.clean_path.is_file())
        self.assertEqual(len(verified),2)
        self.assertEqual(old_ko.read_bytes(),old_ko_before)
        self.assertEqual(rollout.read_bytes(),rollout_before)
        self.assertEqual((self.first_calls,self.review_calls,self.targeted_calls),(1,1,0))
        dependencies=Dependencies(); dependencies.fail_external=True
        with patch.object(regeneration,'configured_lock_dir',return_value=root/'locks'), \
             patch.object(regeneration,'try_acquire_title_lock',return_value=AcquiredLock()):
            with self.assertRaises(normal.controller.Stage11ControllerValidationError):
                regeneration.regenerate_one_title(
                    self.baseline.source_snapshot.dvd_id,
                    run_root=root/'failed-private-run',
                    dependencies=dependencies,
                    acceptance_policy=policy_with(),
                    source_verifier=lambda video,snapshot:verified.append((video,snapshot)),
                    claim_token=12)
        self.assertEqual(old_ko.read_bytes(),old_ko_before)
        self.assertEqual(rollout.read_bytes(),rollout_before)

    def test_native_validation_is_bounded_and_preserves_raw_evidence(self):
        calls=[]
        class Bridge:
            def _python(self,*_a,**kwargs):
                calls.append(kwargs)
                return normal.wire({'stdout':base64.b64encode(b'bad JSON').decode(),
                    'stderr':base64.b64encode(b'session_id: 20261012_120000_abcdef\n').decode(),
                    'returncode':0,'timeout_reason':None,'tools_count':0,'elapsed_seconds':1,'remote_root':'test'})
        directory=self.staging/'fixture'; directory.mkdir(mode=0o700)
        runner=normal.NativeNormalFirstPass(Bridge())
        with self.assertRaises(normal.controller.Stage11ControllerValidationError):
            runner.invoke(b'test',directory,'bad',lambda raw:json.loads(raw))
        self.assertEqual(len(calls),normal.MAX_VALIDATION_ATTEMPTS)
        self.assertEqual(len(list(directory.glob('*.validation-error.json'))),2)

    def test_queue_reuses_inventory_and_never_requeues_existing_state(self):
        from teddy_discovery_stage11_normal_queue import seed_new_holdings
        from teddy_discovery_stage12_rollout import Stage12RolloutStateStore
        store=Stage12RolloutStateStore(Path(self.temp.name)/'queue.sqlite3')
        row=fixture._holding(self.baseline)
        class Reader:
            def list_subtitle_candidates(self,video): return ()
            def read_subtitle_bytes(self,*_a,**_k): raise AssertionError('no subtitle exists')
        loader=lambda _:dict(holdings=[row])
        first=seed_new_holdings(store,loader=loader,subtitle_reader=Reader())
        self.assertEqual(first['new_holdings'],1)
        state=store.get(row['dvd_id']); self.assertEqual(state.status,'PENDING')
        repeated=seed_new_holdings(store,loader=loader,subtitle_reader=Reader())
        self.assertEqual(repeated['new_holdings'],0)
        self.assertEqual(store.get(row['dvd_id']),state)

    def test_fixed64_fallback_uses_canonical_parts_and_source_identity(self):
        from teddy_discovery_stateful_parts import StatefulSemanticPart, serialize_stateful_part
        prep,boundary=normal.prepare_normal(self.route,normal.sha(normal.controller.serialize_asr_result(self.baseline)),1)
        package=prep.package
        plan=normal.build_stateful_part_plan(package,normal.serialize_stateful_model_input(package),boundary_evidence=boundary)
        class Native(normal.NativeNormalFirstPass):
            def invoke(self,prompt,directory,label,validator):
                if label=='whole-title': raise normal.controller.Stage11ControllerValidationError('synthetic truncated response')
                expected=plan.parts[0]
                output=StatefulSemanticPart(part_schema_version=1,session_id=plan.session_id,
                    input_sha256=plan.input_sha256,part_index=expected.part_index,
                    first_cue_id=expected.first_cue_id,last_cue_id=expected.last_cue_id,
                    cues=tuple(StatefulCueOutput(c.cue_id,None,'부분 번역',None) for c in package.cues),
                    max_cues_per_part=plan.max_cues_per_part,source_cues=package.cues)
                return validator(serialize_stateful_part(output))
        first=Native(None)(package,route='HYBRID',staging_root=self.staging,boundary_evidence=boundary)
        self.assertEqual(tuple(c.cue_id for c in first.cues),tuple(c.cue_id for c in package.cues))
        self.assertEqual(first.session_id,normal.stateful_session_id_for_package(package))
        self.assertTrue((self.staging/package.dvd_id/'whole-title-fallback.json').is_file())

    def test_whole_title_reuses_source_aware_runaway_guard(self):
        def runaway(package,**kwargs):
            first=self.first(package,**kwargs)
            return replace(first,cues=(replace(first.cues[0],ko='아 '*100),)+first.cues[1:])
        with self.assertRaises(normal.controller.Stage11ControllerValidationError):
            self.run_title(first_pass_runner=runaway)
        self.assertFalse(list(self.artifacts.glob('*/clean-ko-v1.srt')))

    def test_native_execution_error_is_not_success(self):
        class Bridge:
            def _python(self,*_a,**_k):
                return normal.wire({'stdout':base64.b64encode(b'failure').decode(),
                    'stderr':base64.b64encode(b'session_id: 20261012_120000_abcdef\n').decode(),
                    'returncode':1,'timeout_reason':'INACTIVITY_TIMEOUT','tools_count':0,'elapsed_seconds':600,'remote_root':'test'})
        directory=self.staging/'fixture'; directory.mkdir(mode=0o700)
        with self.assertRaises(normal.controller.Stage11ControllerError):
            normal.NativeNormalFirstPass(Bridge()).invoke(b'test',directory,'timeout',lambda raw:json.loads(raw))
        self.assertEqual(len(list(directory.glob('*.receipt.json'))),1)

    def test_targeted_worker_starts_only_after_local_media_is_ready(self):
        events=[]
        config=SimpleNamespace(ssh_key='/unused/key',known_hosts='/unused/hosts')
        class Client:
            runtime_identity=self.baseline.runtime_identity
            engine_version=self.baseline.engine_version
            def transcribe_targeted_chunk(_self,_chunk):
                events.append('http_request')
                return 'synthetic-response'
        class Worker:
            def stop(_self):
                events.append('worker_stop')
                return True
        class Lifecycle:
            def __init__(_self,_config): pass
            def start_tunnel(_self):
                events.append('tunnel_start')
                return object()
            def start_worker(_self):
                events.append('worker_start')
                return Worker()
            def _stop_process(_self,_process):
                events.append('tunnel_stop')
                return True
        transport=bounded_worker.BoundedTargetedASRTransport(
            client_factory=lambda _config:Client(), lifecycle_factory=Lifecycle)
        snapshot=self.baseline.source_snapshot
        video=SimpleNamespace(video_format='mp4')
        local=SimpleNamespace(source_snapshot=snapshot)
        class Source:
            @contextmanager
            def copy_to_temp(_self,*_args,**_kwargs):
                events.append('media_copy_start')
                events.append('media_copy_complete')
                try:
                    yield local
                finally:
                    events.append('media_temp_cleanup')
        def fake_hybrid(_decisions,*,local_source,targeted_transport,**_kwargs):
            self.assertIs(local_source,local)
            return targeted_transport.transcribe_targeted_chunk(object())
        with patch.object(bounded_worker.BoundedASRWorkerConfig,'load',
                          side_effect=lambda *_a,**_k:events.append('config_read') or config), \
             patch.object(bounded_worker,'_validate_local_ssh_file'), \
             patch.object(live_adapters,'_snapshot',return_value=(video,snapshot)), \
             patch.object(live_adapters,'run_targeted_hybrid_windows',side_effect=fake_hybrid):
            runner=live_adapters.build_targeted_adapter(
                holding_resolver=lambda _title:None,source_provider=Source(),
                targeted_transport=transport,hybrid_suspects=True)
            self.assertEqual(runner(self.baseline,()),'synthetic-response')
        self.assertLess(events.index('media_copy_complete'),events.index('tunnel_start'))
        self.assertLess(events.index('tunnel_start'),events.index('worker_start'))
        self.assertLess(events.index('worker_start'),events.index('http_request'))
        self.assertLess(events.index('media_temp_cleanup'),events.index('worker_stop'))
        self.assertLess(events.index('worker_stop'),events.index('tunnel_stop'))

    def test_full_title_worker_is_lazy_and_stops_after_copy_on_success_and_failure(self):
        snapshot=self.baseline.source_snapshot
        video=SimpleNamespace(video_format='mp4',dvd_id=snapshot.dvd_id)
        config=SimpleNamespace(ssh_key='/unused/key',known_hosts='/unused/hosts')

        def execute(*,fail=False):
            events=[]
            class Client:
                runtime_identity=self.baseline.runtime_identity
                engine_version=self.baseline.engine_version
                def transcribe_chunk(_self,_chunk):
                    events.append('asr_request')
                    if fail: raise RuntimeError('synthetic request failure')
                    return self.baseline.segments
            class Worker:
                def stop(_self):
                    events.append('worker_stop')
                    return True
            class Lifecycle:
                def __init__(_self,_config): pass
                def start_tunnel(_self):
                    events.append('tunnel_start')
                    return object()
                def start_worker(_self):
                    events.append('worker_start')
                    return Worker()
                def _stop_process(_self,_process):
                    events.append('tunnel_stop')
                    return True
            class Source:
                @contextmanager
                def copy_to_temp(_self,*_args,**_kwargs):
                    events.append('media_copy_start')
                    events.append('media_copy_complete')
                    try:
                        yield object()
                    finally:
                        events.append('media_cleanup')
            class FakeFullTitleTranscriber:
                def __init__(_self,*,source_provider,whisper,**_kwargs):
                    _self.source_provider=source_provider
                    _self.whisper=whisper
                def __call__(_self,_video):
                    with _self.source_provider.copy_to_temp(_video):
                        _self.whisper.transcribe_chunk(object())
                    return self.baseline

            transport=bounded_worker.BoundedTargetedASRTransport(
                client_factory=lambda _config:Client(), lifecycle_factory=Lifecycle)
            with patch.object(bounded_worker.BoundedASRWorkerConfig,'load',return_value=config), \
                 patch.object(bounded_worker,'_validate_local_ssh_file'), \
                 patch.object(live_adapters,'_snapshot',return_value=(video,snapshot)), \
                 patch.object(live_adapters,'FullTitleASRTranscriber',FakeFullTitleTranscriber):
                adapter=live_adapters.build_baseline_adapter(
                    holding_resolver=lambda _title:None,source_provider=Source(),
                    whisper=transport)
                if fail:
                    with self.assertRaisesRegex(RuntimeError,'synthetic request failure'):
                        adapter(video)
                else:
                    self.assertEqual(adapter(video),self.baseline)
            self.assertLess(events.index('media_copy_complete'),events.index('tunnel_start'))
            self.assertLess(events.index('tunnel_start'),events.index('worker_start'))
            self.assertLess(events.index('worker_start'),events.index('asr_request'))
            self.assertLess(events.index('media_cleanup'),events.index('worker_stop'))
            self.assertLess(events.index('worker_stop'),events.index('tunnel_stop'))
            return events

        execute()
        execute(fail=True)

    def test_idle_worker_preflight_is_read_only_and_checks_source_snapshot(self):
        config=SimpleNamespace(
            remote_repo_root='/home/teddy/stage11-worker',
            remote_source_sha='1e7d8fa4f40c8cdb37a6fdc65c58b9f3163a7602',
            ssh_key='/root/.ssh/stage11',
            known_hosts='/root/.ssh/known_hosts-stage11',
            remote_python='/opt/stage11-venv/bin/python',
            model_cache_root='/home/teddy/.cache/huggingface/hub',
            model_snapshot='/home/teddy/.cache/huggingface/hub/models--Systran--faster-whisper-large-v3/snapshots/'+'a'*40,
        )
        calls=[]
        def runner(command,**kwargs):
            calls.append((command,kwargs))
            return SimpleNamespace(returncode=0,stdout='STAGE11_ASR_PREFLIGHT=PASS\n',stderr='private synthetic detail')
        def forbidden_popen(*_args,**_kwargs):
            raise AssertionError('read-only preflight must not start a worker')
        lifecycle=lambda value:bounded_worker.BoundedASRWorkerLifecycle(
            value,runner=runner,popen=forbidden_popen)
        transport=bounded_worker.BoundedTargetedASRTransport(
            client_factory=lambda _config:None,lifecycle_factory=lifecycle)
        with patch.object(bounded_worker.BoundedASRWorkerConfig,'load',return_value=config), \
             patch.object(bounded_worker,'_validate_local_ssh_file'), \
             patch.object(bounded_worker.shutil,'which',return_value='/usr/bin/ssh'):
            transport.read_only_preflight()
        self.assertEqual(len(calls),1)
        command,kwargs=calls[0]
        remote=command[-1]
        self.assertEqual(kwargs['timeout'],30)
        self.assertIn('git status --porcelain',remote)
        self.assertIn(config.remote_source_sha,remote)
        self.assertIn("-B -c",remote)
        self.assertIn('verified_snapshot',remote)
        self.assertNotIn(' serve ',remote)
        self.assertNotIn('8091',remote)

    def test_targeted_worker_failures_cleanup_only_owned_sessions(self):
        config=SimpleNamespace(ssh_key='/unused/key',known_hosts='/unused/hosts')
        events=[]
        class Client:
            runtime_identity=self.baseline.runtime_identity
            engine_version=self.baseline.engine_version
            def transcribe_targeted_chunk(_self,_chunk):
                raise RuntimeError('synthetic HTTP failure')
        class Worker:
            def __init__(_self,ok): _self.ok=ok
            def stop(_self):
                events.append('worker_stop')
                return _self.ok
        class Lifecycle:
            fail_start=False
            stop_worker_ok=True
            def __init__(_self,_config): pass
            def start_tunnel(_self):
                events.append('tunnel_start')
                return object()
            def start_worker(_self):
                events.append('worker_start')
                if _self.fail_start:
                    raise bounded_worker.BoundedASRWorkerError('VM122_WORKER_START_FAILED')
                return Worker(_self.stop_worker_ok)
            def _stop_process(_self,_process):
                events.append('tunnel_stop')
                return True
        lifecycle_holder=[]
        def lifecycle_factory(config_value):
            value=Lifecycle(config_value); lifecycle_holder.append(value); return value
        with patch.object(bounded_worker.BoundedASRWorkerConfig,'load',return_value=config), \
             patch.object(bounded_worker,'_validate_local_ssh_file'):
            transport=bounded_worker.BoundedTargetedASRTransport(
                client_factory=lambda _config:Client(),lifecycle_factory=lifecycle_factory)
            lifecycle_holder.clear()
            failed_start=lifecycle_factory(config); failed_start.fail_start=True
            transport._lifecycle_factory=lambda _config:failed_start
            with transport.session() as active:
                with self.assertRaises(bounded_worker.BoundedASRWorkerError):
                    active.transcribe_targeted_chunk(object())
            self.assertIn('tunnel_stop',events)
            self.assertNotIn('worker_stop',events)

            events.clear()
            failed_cleanup=lifecycle_factory(config); failed_cleanup.stop_worker_ok=False
            transport._lifecycle_factory=lambda _config:failed_cleanup
            with self.assertRaisesRegex(bounded_worker.BoundedASRWorkerError,
                                        'WORKER_OR_TUNNEL_CLEANUP_UNVERIFIED'):
                with transport.session() as active:
                    active.transcribe_targeted_chunk(object())
            self.assertIn('worker_stop',events)
            self.assertIn('tunnel_stop',events)

    def test_normal_dependency_uses_bounded_targeted_transport_by_default(self):
        config=SimpleNamespace(
            targeted_asr_worker_config_path=bounded_worker.CONFIG_PATH,
            request_timeout_seconds=1200,
        )
        transport=deployment._build_targeted_asr_transport(config)
        self.assertIsInstance(transport,bounded_worker.BoundedTargetedASRTransport)
        self.assertEqual(transport.request_timeout_seconds,900)
        explicit=object()
        self.assertIs(deployment._build_targeted_asr_transport(config,explicit),explicit)
        full_title, targeted=deployment._build_asr_transports(config)
        self.assertIs(full_title,targeted)
        self.assertIsInstance(full_title,bounded_worker.BoundedTargetedASRTransport)

    def test_regeneration_exposes_only_bounded_hybrid_targeted_runner(self):
        class Live:
            def __init__(self,runner): self.hybrid_targeted_runner=runner
        runner=lambda *_args,**_kwargs: None
        runner.bounded_worker_lifecycle=True
        values=dict(
            config=object(),source_provider=object(),whisper=object(),
            targeted_transport=object(),discovery=object(),provider=object(),
            remote_bridge=object(),remote_task_for_session=lambda *_a:None,
            prepare_remote=lambda *_a:None,originals_provider=lambda *_a:None,
            live=Live(runner),_first_pass_capture=lambda value:value,
            _external_capture=lambda value:value,
        )
        dependencies=deployment.Stage11DeploymentDependencies(**values)
        self.assertIs(dependencies.bounded_hybrid_targeted_runner,runner)
        unbounded=lambda *_args,**_kwargs: None
        dependencies=deployment.Stage11DeploymentDependencies(
            **dict(values,live=Live(unbounded)))
        self.assertIsNone(dependencies.bounded_hybrid_targeted_runner)


if __name__=='__main__': unittest.main()
