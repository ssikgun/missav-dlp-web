"""Synthetic in-memory parser checks. No model result/output fixture is saved."""
import hashlib,json,pickle,sys
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,'/opt/missav-pwa-subtitle-stage11-boundary')
from teddy_discovery_stateful_hybrid import build_supplemental_review_request,parse_supplemental_review_result
root=Path(__file__).resolve().parent;bundle=root/'native'
load=lambda n:json.loads((bundle/n).read_bytes())
pins=load('execution-pins.json');p,b,first,fr,srt=pickle.loads(Path(pins['trusted_seed']).read_bytes())
records=tuple(load('retained-records.json'));artifacts={}
for r in records:
 for e in r['evidence_sources']:artifacts[e['asr_artifact_sha256']]=Path(e['evidence_origin']).read_bytes()
request=(bundle/'hermes-supplemental-review-request.json').read_bytes()
assert request==build_supplemental_review_request(p,records=records,asr_artifacts=artifacts,first_pass=first)
assert len(json.loads(request)['groups'])==1
results=[]
def parse(data):return parse_supplemental_review_result(json.dumps(data,ensure_ascii=False).encode(),request,preparation=p,records=records,asr_artifacts=artifacts,first_pass=first)
def fixture(action,category):
 return {'schema_version':2,'request_sha256':hashlib.sha256(request).hexdigest(),'cues':[{'cue_id':pins['expected_group_id'],'action':action,'category':category,'reason':'SYNTHETIC CONTRACT TEST ONLY, NOT A HERMES JUDGMENT','replacement_ja':'テスト' if action=='REPAIR' else None,'replacement_ko':'계약 시험 문구' if action=='REPAIR' else None}]}
for action,category in [('KEEP','DIALOGUE'),('REPAIR','SEMANTIC_REPAIR'),('OMIT','NONVERBAL_NOISE'),('AMBIGUOUS','AMBIGUOUS')]:
 states=parse(fixture(action,category));assert len(states)==1 and all(not s['approved'] and not s['srt_eligible'] and s['audio_verification']=='UNVERIFIED_AUDIO' for s in states)
 results.append({'test':action+' remains unapproved and SRT-ineligible','status':'PASS'})
def reject(name,data):
 try:parse(data)
 except Exception:results.append({'test':name,'status':'PASS'});return
 raise AssertionError('unsafe fixture accepted: '+name)
x=fixture('AMBIGUOUS','AMBIGUOUS');x['request_sha256']='0'*64;reject('wrong request SHA rejected',x)
x=fixture('AMBIGUOUS','AMBIGUOUS');x['cues'][0]['cue_id']='extra-candidate';reject('wrong candidate rejected',x)
x=fixture('AMBIGUOUS','AMBIGUOUS');x['cues'].append(dict(x['cues'][0],cue_id='extra-candidate'));reject('second candidate rejected',x)
x=fixture('AMBIGUOUS','AMBIGUOUS');x['cues'][0]['replacement_ko']='미확정 번역';reject('AMBIGUOUS replacement rejected',x)
x=fixture('KEEP','DIALOGUE');x['cues'][0]['publishable']=True;reject('publication field in native response rejected',x)
x=fixture('KEEP','DIALOGUE');x['cues'][0]['decision']=x['cues'][0].pop('action');reject('invented decision alias rejected',x)
x=fixture('OMIT','DIALOGUE');reject('invalid action/category rejected',x)
sys.path.insert(0,'/tmp/stage11-hermes-fresh-path-audit');import prepare_offline as check
raw=b'{"synthetic_contract_test":true}'
clean,warning=check.split_confirmed_warning(check.TIRITH_WARNING+raw);assert clean==raw and warning==check.TIRITH_WARNING
unknown=b'unknown-prefix\n'+raw;clean,warning=check.split_confirmed_warning(unknown);assert clean==unknown and not warning
results.append({'test':'only exact known tirith prefix separated','status':'PASS'})
(root/'offline-contract-audit.json').write_text(json.dumps({'status':'PASS_CONTRACT_ONLY','tests':results,'test_count':len(results),'synthetic_results_persisted':False,'actual_Hermes_calls':0},indent=2)+'\n')
print('PASS',len(results),'synthetic in-memory contract checks; model calls0; no fabricated result files')
