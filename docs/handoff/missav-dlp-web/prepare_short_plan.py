"""Offline whole-video planner; read preserved PCM/results, never run an STT model."""
import argparse
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import pickle
import shutil
import sys
import tempfile

REPO=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(REPO))
import numpy as np
from teddy_discovery_stateful_short_plan import (
 build_short_plan,attach_reusable_results,offline_client,planned_chunk,encode,digest)
from teddy_discovery_stateful_hybrid import (
 project_affine_timestamp_ms,reconcile_stateful_hybrid_chunks,
 collect_stateful_hybrid_supplemental_candidates,build_supplemental_review_request,
 build_supplemental_cross_evidence,materialize_stateful_hybrid_srt)
from teddy_discovery_stateful_translator import parse_stateful_result
from teddy_discovery_asr_remote import RemoteASRHTTPResponse,REMOTE_ASR_MAX_RESPONSE_BYTES
from teddy_discovery_asr_artifact import serialize_asr_result


def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--config',type=Path,required=True)
 parser.add_argument('--pins',type=Path,required=True)
 parser.add_argument('--cache',type=Path,nargs='*',default=[])
 parser.add_argument('--reazon-result',type=Path,nargs='*',default=[])
 args=parser.parse_args();cfg=json.loads(args.config.read_bytes());pins=json.loads(args.pins.read_bytes())
 seed=Path(pins['trusted_seed']);raw=seed.read_bytes()
 if digest(raw)!=pins['files'][str(seed)]:raise ValueError('trusted preparation SHA mismatch')
 prep,boundary,first,first_raw,srt_raw=pickle.loads(raw)
 app=prep.route_decision.alignment_application;base=app.bundle.asr_result
 if asdict(base.source_snapshot)!=cfg['source_snapshot'] or asdict(base.runtime_identity)!=cfg['runtime_identity']:
  raise ValueError('source/runtime identity detached')
 approved_path=Path(pins['approved_result']);raw=approved_path.read_bytes()
 if digest(raw)!=pins['files'][str(approved_path)]:raise ValueError('approved result changed')
 approved=parse_stateful_result(raw,prep.package,boundary_evidence=boundary)
 srt_path=next(Path(p) for p in pins['files'] if p.endswith('.ko.srt'))
 srt=materialize_stateful_hybrid_srt(prep.package,approved,prep.route_decision,prep)
 assert len(approved.cues)==313 and sum(c.absorbed_into is not None for c in approved.cues)==17
 assert len(srt.playback_cues)==296 and srt.artifact.payload==srt_path.read_bytes()
 pcm_path=Path(cfg['PCM_path']);pcm=np.memmap(pcm_path,dtype='<f4',mode='r')
 if pcm.size!=cfg['PCM_sample_count']:raise ValueError('PCM sample count mismatch')
 external=tuple((c.cue_id,project_affine_timestamp_ms(app.alignment,s.start_ms),
  project_affine_timestamp_ms(app.alignment,s.end_ms)) for c,s in
  zip(prep.package.cues,app.bundle.external_ja_document.cues,strict=True))
 plan=build_short_plan(duration_ms=cfg['duration_ms'],pcm=pcm,
  source_pcm_sha256=cfg['PCM_sha256'],source_video_sha256=cfg['source_video_sha256'],
  snapshot=base.source_snapshot,engine_version=base.engine_version,settings=cfg['settings'],
  external_intervals=external)
 attach_reusable_results(plan,pcm=pcm,snapshot=base.source_snapshot,folders=args.cache)
 out=Path(tempfile.mkdtemp(prefix='stage11-full-short-plan-'))
 client=offline_client(base.engine_version);chunks=[];records=[];artifacts={};audio_windows=[]
 for row in plan['windows']:
  if not row['reusable']:continue
  cached=row['reuse_observations'][0];req=Path(cached['request_path']).read_bytes();wire=Path(cached['response_path']).read_bytes()
  chunks.append(dict(index=row['index'],lo=row['audio_lo'],hi=row['audio_hi'],
   core_lo=row['core_lo'],core_hi=row['core_hi'],request_bytes=req,response_bytes=wire,
   request_sha256=cached['request_sha256'],response_sha256=cached['response_sha256'],evidence_origin=cached['response_path']))
  segments=client._decode_response(RemoteASRHTTPResponse(200,wire),
   chunk=planned_chunk(row,pcm,base.source_snapshot),request_body=req,expected_vad_region_count=0)
  normalized=serialize_asr_result(replace(base,segments=segments))
  name=out/('cached-core-'+str(row['index'])+'.normalized-asr.json');name.write_bytes(normalized);artifacts[digest(normalized)]=normalized
  records.extend(dict(candidate=c,evidence_sources=[c['audio_evidence']]) for c in
   collect_stateful_hybrid_supplemental_candidates(prep,asr_artifact=normalized,
    evidence_origin=str(name),audio_input_sha256=cached['request_sha256'],first_pass=approved))
  audio_windows.append(dict(request_bytes=req,request_sha256=digest(req),lo=row['audio_lo'],hi=row['audio_hi']))
 if not chunks:raise ValueError('no retained short evidence for connection validation')
 rec=reconcile_stateful_hybrid_chunks(prep,source_pcm=pcm,source_pcm_sha256=cfg['PCM_sha256'],chunks=tuple(chunks),first_pass=approved)
 # Existing independent-STT clip contract is provider-neutral; no Gemini input.
 external_stt=[]
 for path in args.reazon_result:
  result=json.loads(path.read_bytes())
  if result['source_pcm_sha256']!=cfg['PCM_sha256']:raise ValueError('Reazon source PCM mismatch')
  if 'case_requests' in result:
   by_id={r['case_id']:r for r in result['case_requests']}
   pairs=[(by_id[o['case_id']],o) for o in result['results']]
  else:pairs=[(o['request'],o) for o in result['results'] if o['request']['kind']=='SUPPLEMENTAL']
  for req,obs in pairs:
   if digest(Path(req['wav_path']).read_bytes())!=req['wav_sha256']:raise ValueError('Reazon WAV changed')
   lo=req.get('clip_start_ms',req.get('lo',0)/16);hi=req.get('clip_end_ms',req.get('hi',0)/16)
   external_stt.append(dict(evidence_id='reazon-'+digest(encode([str(path),req,obs])),
    source_family='ReazonSpeech',clip_start_ms=int(lo),clip_end_ms=int(hi),
    turns=[dict(stt_ja=obs['text'])],source_result=str(path),audio_verification='UNVERIFIED_AUDIO'))
 bounded=tuple(records[:3])
 semantic=build_supplemental_review_request(prep,records=bounded,asr_artifacts=artifacts,first_pass=approved)
 cross=build_supplemental_cross_evidence(prep,records=bounded,asr_artifacts=artifacts,
  first_pass=approved,source_pcm=pcm,source_pcm_sha256=cfg['PCM_sha256'],
  audio_windows=tuple(audio_windows),chunks=tuple(chunks),external_stt=tuple(external_stt))
 observations=[r for row in plan['windows'] for r in row['reuse_observations']]
 rates=[r['wall_seconds'] for r in observations]
 request_total=sum(r['request_bytes'] for r in plan['windows'] if r['requires_new_STT'])
 observed_response_max=max(Path(r['response_path']).stat().st_size for r in observations)
 new=plan['new_STT_count'];mean=sum(rates)/len(rates)
 cost=dict(core_count=len(plan['windows']),audio_seconds_including_padding=sum((r['audio_hi']-r['audio_lo'])/16000 for r in plan['windows']),
  new_audio_seconds=sum((r['audio_hi']-r['audio_lo'])/16000 for r in plan['windows'] if r['requires_new_STT']),
  reused_count=plan['reuse_count'],new_Whisper_requests=new,reusable_observations=len(observations),
  recommended_max_concurrency=1,historical_mean_request_wall_seconds=mean,
  extrapolated_request_wall_seconds=new*mean,observed_rate_range_wall_seconds=[new*min(rates),new*max(rates)],
  estimated_new_NPY_bytes=request_total,empirical_response_budget_bytes=new*observed_response_max,
  protocol_max_response_budget_bytes=new*REMOTE_ASR_MAX_RESPONSE_BYTES,
  shared_PCM_bytes=pcm_path.stat().st_size,PCM_copy_required=False,disk_free_bytes=shutil.disk_usage(out).free,
  estimate_limit='small-sample GPU request time only; load/queue/retries/Reazon/Hermes not included')
 audit=dict(status='PASS_PLAN_AND_OFFLINE_CONNECTION_ONLY',STT_calls=0,Whisper_calls=0,Reazon_calls=0,Hermes_calls=0,Gemini_calls=0,
  canonical_JA=313,canonical_KO_SRT=296,absorption=17,approvals=0,SRT_byte_identical=True,
  whole_Whisper_complete=False,unexecuted_cores=new,reused_connection_records=len(rec['records']),
  Reazon_clip_evidence_count=len(external_stt),Gemini_required=False)
 (out/'whole-short-plan.json').write_bytes(encode(plan));(out/'cost.json').write_text(json.dumps(cost,indent=2)+'\n')
 (out/'audit.json').write_text(json.dumps(audit,indent=2)+'\n');(out/'reused-chunk-reconciliation.json').write_bytes(encode(rec))
 (out/'bounded-Hermes-contract.json').write_bytes(semantic);(out/'Reazon-only-cross-evidence-contract.json').write_bytes(encode(cross))
 protected={str(seed):pins['files'][str(seed)],str(approved_path):pins['files'][str(approved_path)],str(srt_path):pins['files'][str(srt_path)],str(pcm_path):cfg['PCM_sha256']}
 for p in [args.config,args.pins,Path(__file__).resolve(),REPO/'teddy_discovery_stateful_short_plan.py',*args.reazon_result]:protected[str(p.resolve())]=digest(p.read_bytes())
 for module in ('teddy_discovery_asr_audio.py','teddy_discovery_asr_remote.py',
                'teddy_discovery_asr_artifact.py','teddy_discovery_stateful_hybrid.py'):
  p=REPO/module;protected[str(p)]=digest(p.read_bytes())
 for folder in args.cache:
  for name in ('inputs.json','results.json'):
   p=folder/name;protected[str(p.resolve())]=digest(p.read_bytes())
 for row in plan['windows']:
  for observation in row['reuse_observations']:
   protected[observation['request_path']]=observation['request_sha256']
   protected[observation['response_path']]=observation['response_sha256']
 (out/'source-pins.json').write_bytes(encode(protected))
 (out/'SHA256SUMS').write_text(''.join(digest(p.read_bytes())+'  '+p.name+'\n' for p in sorted(out.iterdir()) if p.name!='SHA256SUMS'))
 print('OUTPUT='+str(out));print(json.dumps(cost,indent=2));print(json.dumps(audit,indent=2))


if __name__=='__main__':main()
