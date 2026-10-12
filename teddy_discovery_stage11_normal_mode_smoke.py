"""Offline normal-mode failure, immutable readback and bounded native contracts.

Synthetic transport fixtures are never presented as live translation evidence.
"""
import base64
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import teddy_discovery_stage11_normal_mode as normal
import teddy_discovery_stage11_controller_smoke as fixture
import teddy_discovery_stage11_live_adapters as live_adapters
from teddy_discovery_alignment_acceptance_smoke import policy_with
from teddy_discovery_stateful_translator import StatefulAbsorptionResult, StatefulCueOutput
from teddy_discovery_stage11_deployment import Stage11DeploymentTransportError
from teddy_discovery_subtitle_external import SubtitleCatProvider, SubtitleCatDetailPage
from teddy_discovery_subtitlecat_discovery import SubtitleCatDiscovery, SubtitleCatSearchResponse


class NormalSmoke(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name); self.artifacts=root/'artifacts'; self.staging=root/'staging'
        for p in (self.artifacts,self.staging): p.mkdir(mode=0o700)
        self.route=fixture.fixture.accepted_hybrid_route()
        self.baseline=self.route.alignment_application.bundle.asr_result
        self.align=patch.object(normal,'_align_external_payload',return_value=self.route.alignment_application)
        self.align.start(); self.addCleanup(self.align.stop)
        for target in ('subprocess.run','subprocess.Popen','socket.socket'):
            p=patch(target,side_effect=AssertionError('offline tests forbid network/processes'))
            p.start(); self.addCleanup(p.stop)

    def first(self, package, *, boundary_evidence, **unused):
        return StatefulAbsorptionResult(package.schema_version,package.dvd_id,package.generation_key,
            package.claim_token,normal.stateful_session_id_for_package(package),
            tuple(StatefulCueOutput(c.cue_id,None,'검증용 번역 '+str(i),None) for i,c in enumerate(package.cues)),boundary_evidence)

    def run_title(self, **overrides):
        kwargs=dict(artifact_root=self.artifacts,stateful_staging_root=self.staging,claim_token=1,
            holding_resolver=lambda _:fixture._holding(self.baseline),baseline_transcriber=lambda _:self.baseline,
            external_ja_attempt=lambda *_:self.route.alignment_application,first_pass_runner=self.first,
            acceptance_policy=policy_with(),targeted_runner=lambda *_:self.fail('optional STT ran'),
            hybrid_review_runner=lambda *_:self.fail('optional review ran'))
        kwargs.update(overrides)
        return normal.run_one_title_normal_mode(self.baseline.source_snapshot.dvd_id,**kwargs)

    def test_primary_completes_with_optional_recovery_unavailable(self):
        baseline_formats=[]
        result=self.run_title(baseline_transcriber=lambda video: baseline_formats.append(video.video_format) or self.baseline)
        proof=json.loads((result.report_path.parent/normal.PROOF_NAME).read_bytes())
        report=json.loads(result.report_path.read_bytes())
        self.assertEqual(proof['user_intervention'],0)
        self.assertFalse(proof['automatic_insertion'])
        self.assertEqual(proof['ambiguous_policy'],'SKIP_AND_CONTINUE')
        self.assertTrue(result.clean_path.is_file())
        self.assertEqual(baseline_formats,['mp4'])
        self.assertEqual((result.report_path.parent/'normal-external-ja.srt').read_bytes(),
            self.route.alignment_application.bundle.external_ja_payload.payload)
        baseline_raw=(result.report_path.parent/normal.controller.BASELINE_ASR_FILENAME).read_bytes()
        self.assertEqual(baseline_raw,normal.controller.serialize_asr_result(self.baseline))
        self.assertEqual(report['baseline_sha256'],normal.sha(baseline_raw))
        self.assertIs(report['publication_performed'],False)
        repeated=self.run_title(first_pass_runner=lambda *_a,**_k:self.fail('resume called Hermes'))
        self.assertEqual(repeated.clean_sha256,result.clean_sha256)

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


if __name__=='__main__': unittest.main()
