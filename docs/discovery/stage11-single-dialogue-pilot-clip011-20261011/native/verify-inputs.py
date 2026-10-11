"""Reuse existing supplemental parser; no translation merge or publication."""
import hashlib,json,os,pathlib,pickle,re,sys
P=pathlib.Path;root=P(__file__).resolve().parent
sys.path.insert(0,'/opt/missav-pwa-subtitle-stage11-boundary')
from teddy_discovery_stateful_hybrid import build_supplemental_review_request,parse_supplemental_review_result
from teddy_discovery_stateful_translator import parse_stateful_result
sha=lambda b:hashlib.sha256(b).hexdigest()
pins=json.loads((root/'execution-pins.json').read_bytes())
for name,digest in pins['files'].items():assert sha(P(name).read_bytes())==digest,'input/source SHA changed: '+name
preparation,boundary,first,first_raw,srt_raw=pickle.loads(P(pins['trusted_seed']).read_bytes())
records=tuple(json.loads((root/'retained-records.json').read_bytes()));artifacts={}
for r in records:
 for e in r['evidence_sources']:
  raw=P(e['evidence_origin']).read_bytes();assert sha(raw)==e['asr_artifact_sha256'];artifacts[sha(raw)]=raw
request=(root/'hermes-supplemental-review-request.json').read_bytes()
assert request==build_supplemental_review_request(preparation,records=records,asr_artifacts=artifacts,first_pass=first)
assert sha(request)==pins['request_sha256'] and len(json.loads(request)['groups'])==pins['expected_group_count']
approved=parse_stateful_result(P(pins['approved_result']).read_bytes(),preparation.package,boundary_evidence=boundary)
assert len(approved.cues)==313 and sum(c.absorbed_into is not None for c in approved.cues)==17

# Single-candidate data view; canonical request/result contract unchanged.
evidence=json.loads((root/'candidate-evidence.json').read_bytes())
target=evidence['target'];group=json.loads(request)['groups'][0]
assert group['cue_id']==target['group_id']==pins['expected_group_id']
assert group['candidate_ids']==evidence['original_candidate_ids']
assert [group['start_ms'],group['end_ms']]==target['core_range_ms']
assert evidence['assessment']['japanese_accuracy']=='UNVERIFIED'
assert evidence['assessment']['existing_same_utterance_duplicate']=='UNVERIFIED'
assert evidence['assessment']['publishable'] is False
assert evidence['canonical_counts']=={'JA':313,'KO_playback':296,'absorptions':17}
assert len(evidence['absorption_records'])==17
for kind in ('core','context'):
 name=pins[kind+'_wav_path']
 assert sha(P(name).read_bytes())==target[kind+'_wav_sha256']
assert target['user_core_judgment']['core_label']=='DIALOGUE_LIKELY'
prompt=(root/'supplemental13.prompt.txt').read_bytes()
assert len(prompt)<=128000 and sha(prompt)==pins['prompt_sha256']
assert prompt==(root/'hermes-native-review-prompt.txt').read_bytes()
assert b'REQUEST:\n'+request in prompt
assert b'SINGLE_CANDIDATE_EVIDENCE:\n'+json.dumps(evidence,ensure_ascii=False,sort_keys=True,allow_nan=False,separators=(',',':')).encode() in prompt
assert prompt.endswith(b'request_sha256="'+pins['request_sha256'].encode()+b'"\n')
from teddy_discovery_stateful_hybrid import materialize_stateful_hybrid_srt
srt_path=next(name for name in pins['files'] if name.endswith('.ko.srt'))
materialized=materialize_stateful_hybrid_srt(preparation.package,approved,preparation.route_decision,preparation)
assert len(materialized.playback_cues)==296 and materialized.artifact.payload==P(srt_path).read_bytes()

if sys.argv[1:]==['--preflight']:print('PREFLIGHT=PASS; 1 group; evidence pinned; no model called');sys.exit(0)
assert len(sys.argv)==pins['expected_group_count'] and sys.argv[1] in ['--validate','--offline-validate']
out=P(sys.argv[2]);raw=(out/'stdout.json').read_bytes()
sys.path.insert(0,'/tmp/stage11-hermes-fresh-path-audit')
import prepare_offline as check
clean,warning=check.split_confirmed_warning(raw)
states=parse_supplemental_review_result(clean,request,preparation=preparation,records=records,asr_artifacts=artifacts,first_pass=first)
assert len(states)==pins['expected_group_count'] and all(not x['approved'] and not x['srt_eligible'] and x['audio_verification']=='UNVERIFIED_AUDIO' for x in states)
states=tuple(dict(s,publishable=False) for s in states)
runtime_id=None
if sys.argv[1]=='--validate':
 stderr=(out/'stderr.log').read_text();assert stderr.splitlines().count('TOOLS_COUNT=0')==1
 ids=re.findall(r'^session_id: (\d{8}_\d{6}_[a-f0-9]{6})\s*$',stderr,re.MULTILINE);assert len(ids)==1 and ids[0]!=first.session_id
 runtime_id=ids[0]
for name,digest in pins['files'].items():assert sha(P(name).read_bytes())==digest,'input/source changed during review: '+name
assert (out/'stdout.json').read_bytes()==raw
(out/'validated-response.json').write_bytes(clean)
(out/'supplemental-language-decisions.json').write_text(json.dumps(states,ensure_ascii=False,indent=2)+'\n')
if warning:(out/'separated-tirith-warning.txt').write_bytes(warning)
(out/'validation-audit.json').write_text(json.dumps({'status':'PASS_CONTRACT_ONLY','runtime_session_id':runtime_id,'request_sha256':sha(request),'prompt_sha256':pins['prompt_sha256'],'cross_evidence_sha256':sha((root/'candidate-evidence.json').read_bytes()),'stdout_sha256':sha(raw),'group_count':len(states),'Japanese_accuracy':'UNVERIFIED','approved':0,'publishable':False,'srt_insertions':0,'original_sources_unchanged':True},indent=2)+'\n')
print('VALIDATION=PASS_CONTRACT_ONLY; language judgment only; approvals=0; RESULTS='+str(out))
