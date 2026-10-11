"""Offline revision from retained evidence and separately scoped human feedback."""
import dataclasses,hashlib,importlib.util,json,pickle,sys,wave
from pathlib import Path
import numpy as np
sys.dont_write_bytecode=True
root=Path(__file__).resolve().parent
repo=Path('/opt/missav-pwa-subtitle-stage11')
helper=repo/'tools/stage11_prepare_single_supplemental_pilot.py'
spec=importlib.util.spec_from_file_location('single_preparation',helper)
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
sys.path.insert(0,'/opt/missav-pwa-subtitle-stage11-boundary')
from teddy_discovery_stateful_hybrid import materialize_stateful_hybrid_srt
from teddy_discovery_stateful_translator import parse_stateful_result
load=lambda p:json.loads(Path(p).read_bytes())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
write=lambda p,x:Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
old=Path('/var/tmp/stage11-single-dialogue-pilot-20261011/candidate-evidence.json')
e=load(old);evaluation=Path('/var/tmp/stage11-core-dialogue-stt-evaluation-20261011/evaluation.json')
rows={r['id']:r for r in load(evaluation)['clips']}
main=e['target'];following=rows['clip-012']
assert main==rows['clip-011']
feedback={'source':'USER_DIRECT_AUDIO_LISTENING_CURRENT_REQUEST_20261012','clip_id':main['id'],
 'core':{'range_ms':main['core_range_ms'],'heard_japanese':'いいところ','complete_sentence_heard':False},
 'context':{'range_ms':main['original_context_range_ms'],'heard_japanese':'いいところだね','following_separate_japanese':'はい','text_status':'USER_REPORTED_CONTEXT_TRANSCRIPT'},
 'actual_utterance_boundaries_ms':None,'subtitle_approval':False}
write(root/'user-listening-feedback.json',feedback)
timing={'original_core_range_ms':main['core_range_ms'],'evaluation_path':str(evaluation),
 'main':h.retained_timing_envelope(main),'following_context_only':{'source_clip_id':following['id'],'timing':h.retained_timing_envelope(following),'is_candidate':False},
 'review_candidate_count':1,'actual_audio_boundaries_confirmed':False,
 'ending_cut_status':'USER_REPORTS_CORE_LACKS_SENTENCE_END_CONTEXT_HAS_FULL_SENTENCE',
 'interpretation':'Saved timestamp envelope is a review window, not an exact measured utterance interval. Original ASR timestamps disagree with scoped human listening and remain immutable.'}
e['timing_revision']=timing;e['user_listening_revision']=feedback
cp=e['canonical_protection'];prep,b,first,first_raw,srt_raw=pickle.loads(Path(cp['trusted_seed']).read_bytes())
approved=parse_stateful_result(Path(cp['approved_result']).read_bytes(),prep.package,boundary_evidence=b)
materialized=materialize_stateful_hybrid_srt(prep.package,approved,prep.route_decision,prep)
assert materialized.artifact.payload==Path(cp['KO_SRT']).read_bytes()
assert (len(prep.package.cues),len(materialized.playback_cues),sum(c.absorbed_into is not None for c in approved.cues))==(313,296,17)
alignment=load(e['source_audio']['alignment_path']);times={c['cue_id']:c for c in alignment['external_JA']}
current={c.cue_id:c for c in approved.cues}
def compare(bounds,text):
 a,z=bounds
 overlap=lambda c:max(a,c['start_ms'])<min(z,c['end_ms'])
 prev=max((c for c in times.values() if c['end_ms']<=a),key=lambda c:c['end_ms'])
 nxt=min((c for c in times.values() if c['start_ms']>=z),key=lambda c:c['start_ms'])
 local_ids={c['cue_id'] for c in e['adjacent_existing_subtitles']}
 absorptions=e['absorption_records']
 return {'range_ms':bounds,'JA_temporal_overlaps':[c for c in times.values() if overlap(c)],
  'KO_playback_temporal_overlaps':[dataclasses.asdict(c) for c in materialized.playback_cues if overlap(dataclasses.asdict(c))],
  'local_absorption_records':[c for c in absorptions if c['cue_id'] in local_ids or c['absorbed_into'] in local_ids],
  'absorbed_source_JA_temporal_overlaps':[c for c in absorptions if overlap(times[c['cue_id']])],
  'previous_ja':prev,'next_ja':nxt,'previous_gap_ms':a-prev['end_ms'],'next_gap_ms':nxt['start_ms']-z,
  'same_utterance_duplicate':'UNVERIFIED','time_aligned_JA_inclusion':'NONE_IN_ESTIMATED_RANGE',
  'semantic_note':'Temporal nonoverlap and no local absorption cannot prove semantic novelty; identical short strings elsewhere are not same-utterance evidence.'}
e['revised_time_comparison']=compare(timing['main']['range_ms'],timing['main']['text'])
timing['following_context_only']['subtitle_comparison']=compare(timing['following_context_only']['timing']['range_ms'],timing['following_context_only']['timing']['text'])
timing['following_context_only']['JA_literal_matches_elsewhere']=following['ja_elsewhere_text_contains']
e['assessment']['context_japanese_reading']='USER_REPORTED_MATCH_WITH_STT'
e['assessment']['core_complete_sentence_verified']=False
e['assessment']['precise_audio_timing']='UNVERIFIED'
e['assessment']['ending_cut']='USER_REPORTED_CORE_TRUNCATION'
e['assessment']['japanese_accuracy_scope_note']='Human confirms lexical reading in CONTEXT, not complete original CORE or exact time correspondence. Original UNVERIFIED retained as alignment/independent verification status.'
e['unresolved_issues']=['Actual start/end require manual phonetic alignment in existing context WAV; saved ASR timing disagreement is not resolved by matching text.',
 'Human core reading lacks the sentence ending; original core cannot be counted as full-sentence STT recovery.',
 'JA/KO temporal nonoverlap and no local absorption do not independently prove same-utterance novelty; affine local residual remains unverified.',
 'Hermes text context review cannot determine waveform timing or approve subtitles.']
e['provenance'][str(old)]=sha(old)
e['provenance'][str(root/'user-listening-feedback.json')]=sha(root/'user-listening-feedback.json')
for row in (main,following):
 for item in h.retained_timing_envelope(row)['observations']:
  e['provenance'][item['source']]=sha(item['source'])
 for src in row['whisper']['saved_full_short']:
  assert sha(src['request_path'])==src['request_sha256']
  e['provenance'][src['request_path']]=src['request_sha256']
 e['provenance'][row['reazon']['source_path']]=sha(row['reazon']['source_path'])
 e['provenance'][row['reazon']['input_wav_path']]=row['reazon']['input_wav_sha256']
h.validate_timing_revision(e)
# Verify old core is still the exact sample crop of retained context, not a
# recreated clip. All review/following ranges fall inside that same context.
scope=Path(e['waveform_scope_pack']);audio_audit=[]
for row in (main,following):
 values={}
 for kind in ('core','context'):
  p=scope/kind/(row['id']+'.wav');assert sha(p)==row[kind+'_wav_sha256']
  e['provenance'][str(p)]=sha(p)
  with wave.open(str(p)) as wav:
   assert wav.getframerate()==16000 and wav.getnchannels()==1 and wav.getsampwidth()==2
   values[kind]=np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2')
 offset=round((row['core_range_ms'][0]-row['original_context_range_ms'][0])*16)
 assert np.array_equal(values['core'],values['context'][offset:offset+len(values['core'])])
 audio_audit.append({'id':row['id'],'sha_preserved':True,'core_is_exact_context_sample_crop':True})
write(root/'candidate-evidence.json',e)
write(root/'boundary-audit.json',{'status':'INCOMPLETE_ESTIMATED_BOUNDARIES','main_review_range_ms':timing['main']['range_ms'],
 'following_context_range_ms':timing['following_context_only']['timing']['range_ms'],'core_crop_audit':audio_audit,
 'main_vs_following_gap_ms':timing['following_context_only']['timing']['range_ms'][0]-timing['main']['range_ms'][1],
 'canonical_counts':e['canonical_counts'],'canonical_SRT_byte_identical':True,
 'human_audio_boundaries_confirmed':False,'core_complete_sentence_detected':False,'actual_model_calls':0,'new_audio_files':0})
print('main',timing['main']['range_ms'],'following',timing['following_context_only']['timing']['range_ms'],'one candidate; ESTIMATED')
