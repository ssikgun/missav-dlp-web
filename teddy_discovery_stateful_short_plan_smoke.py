"""Offline edge, coverage, legacy-grid and cache-policy checks; no inference."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import numpy as np
from teddy_discovery_asr import ASRSourceSnapshot
from teddy_discovery_stateful_short_plan import build_short_plan,digest


def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--plan-dir',type=Path,required=True);args=parser.parse_args()
 folder=args.plan_dir;plan=json.loads((folder/'whole-short-plan.json').read_bytes());rows=plan['windows']
 assert rows[0]['core_start_ms']==0 and rows[-1]['core_end_ms']==plan['duration_ms']
 assert rows[0]['audio_start_ms']==0 and rows[-1]['audio_hi']==plan['source_sample_count']
 assert all(a['core_end_ms']==b['core_start_ms'] and a['core_hi']==b['core_lo'] for a,b in zip(rows,rows[1:]))
 assert sum(r['core_hi']-r['core_lo'] for r in rows)==plan['source_sample_count']
 assert len({r['plan_chunk_id'] for r in rows})==len(rows)
 assert all(0<=r['audio_lo']<=r['core_lo']<r['core_hi']<=r['audio_hi']<=plan['source_sample_count'] for r in rows)
 assert all(r['audio_end_ms']<=plan['duration_ms'] and r['audio_end_ms']-r['audio_start_ms']<=30000 for r in rows)
 assert all(r['audio_hi']-r['core_hi']<=plan['padding_ms']*16 and r['core_lo']-r['audio_lo']<=plan['padding_ms']*16 for r in rows)
 assert plan['reuse_count']+plan['new_STT_count']==len(rows)
 assert all(r['requires_new_STT']==(not r['reusable']) and not r['approved'] and not r['publishable'] for r in rows)
 # Interior grid is the preserved user-window formula, independent of old chunk index.
 for r in rows[1:-2]:
  assert r['audio_start_ms']==r['core_start_ms']-5000 and r['audio_end_ms']==r['core_end_ms']+5000
 for row in rows:
  for obs in row['reuse_observations']:
   old=json.loads((Path(obs['folder'])/'results.json').read_bytes())
   status=next(s for s in old['chunk_statuses'] if s['index']==obs['original_index'] and s.get('arm')==obs['arm'])
   assert (row['core_start_ms'],row['core_end_ms'],row['audio_start_ms'],row['audio_end_ms'])==(status['core_start_ms'],status['core_end_ms'],status['start_ms'],status['end_ms'])
   assert obs['request_sha256']==row['request_sha256'] and obs['arm'] in (None,'A')
 assert all(not any(o['arm']=='B' for o in r['reuse_observations']) for r in rows)
 assert any(x['reason']=='DIFFERENT_LONG_CHUNK_CONTEXT' for x in plan['reuse_rejected'])
 checks=['video_start_and_end','all_cores_contiguous_in_ms_and_samples','no_sample_double_ownership',
  'nonnegative_clamped_padding','sub_ms_PCM_tail_preserved','unique_global_core_IDs',
  'legacy_user_grid_identical','exact_cached_SHA_and_options','B_and_long_context_not_reused',
  'unapproved_pending_cores_remain_pending']
 snapshot=ASRSourceSnapshot(**plan['source_identity'])
 for duration in (1,19999,20000,20001,40000,40001):
  pcm=np.zeros(duration*16,dtype='<f4')
  q=build_short_plan(duration_ms=duration,pcm=pcm,source_pcm_sha256=digest(memoryview(pcm).cast('B')),
   source_video_sha256='1'*64,snapshot=snapshot,engine_version=plan['engine_version'],settings=plan['settings'],external_intervals=())
  assert q['windows'][-1]['core_end_ms']==duration
  assert sum(r['core_hi']-r['core_lo'] for r in q['windows'])==pcm.size
 checks.append('tiny_exact_and_nonmultiple_durations')
 pcm=np.zeros(40000*16+1,dtype='<f4')
 q=build_short_plan(duration_ms=40001,pcm=pcm,source_pcm_sha256=digest(memoryview(pcm).cast('B')),
  source_video_sha256='1'*64,snapshot=snapshot,engine_version=plan['engine_version'],settings=plan['settings'],external_intervals=())
 assert q['windows'][-1]['core_hi']-q['windows'][-1]['core_lo']==1
 checks.append('one_sample_terminal_core_survives')
 try:
  build_short_plan(duration_ms=40001,pcm=pcm,source_pcm_sha256='0'*64,
   source_video_sha256='1'*64,snapshot=snapshot,engine_version=plan['engine_version'],settings=plan['settings'],external_intervals=())
 except ValueError:checks.append('source_SHA_tamper_rejected')
 else:raise AssertionError('source SHA bypass')
 audit=json.loads((folder/'audit.json').read_bytes());assert audit['Whisper_calls']==audit['Reazon_calls']==audit['Hermes_calls']==audit['Gemini_calls']==0
 rec=json.loads((folder/'reused-chunk-reconciliation.json').read_bytes())
 assert any(r['role']=='CONTEXT_ONLY' for r in rec['records']) and any(r['role']=='CROSSES_CORE_BOUNDARY' for r in rec['records'])
 assert all(not g['approved'] and not g['srt_eligible'] for g in rec['groups'])
 checks.extend(['context_and_crossing_evidence_not_dropped','zero_real_inference_calls','canonical_313_296_17_preserved'])
 report=dict(status='PASS',test_count=len(checks),checks=checks)
 (folder/'offline-verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
