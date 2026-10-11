# Read-only replay of retained canonical AMBIGUOUS decisions; no model calls.
import json,pickle,hashlib,sys
from pathlib import Path
sys.path.insert(0,'/opt/missav-pwa-subtitle-stage11-boundary')
from teddy_discovery_stateful_hybrid import build_supplemental_review_request,parse_supplemental_review_result
base=Path('/tmp/stage11-supplemental-cross-native-5wr91b_3')
pins=json.loads((base/'execution-pins.json').read_bytes())
prep,boundary,first,first_raw,srt_raw=pickle.loads(Path(pins['trusted_seed']).read_bytes())
records=tuple(json.loads((base/'retained-records.json').read_bytes()));artifacts={}
for r in records:
 for e in r['evidence_sources']:
  raw=Path(e['evidence_origin']).read_bytes();digest=hashlib.sha256(raw).hexdigest()
  assert digest==e['asr_artifact_sha256'];artifacts[digest]=raw
request=(base/'hermes-supplemental-review-request.json').read_bytes()
assert request==build_supplemental_review_request(prep,records=records,asr_artifacts=artifacts,first_pass=first)
response=Path('/tmp/stage11-supplemental13-result-iAqSULRH/validated-response.json').read_bytes()
states=parse_supplemental_review_result(response,request,preparation=prep,records=records,asr_artifacts=artifacts,first_pass=first)
assert len(states)==13 and all(s['language_judgment']['action']=='AMBIGUOUS' and not s['srt_eligible'] and not s['approved'] for s in states)
summary={'status':'PASS','retained_native_ambiguous':13,'automatic_insertions':0,'user_requests':0,'normal_recovery_policy':'DISABLED_UNVERIFIED_ACCURACY','saved_response_sha256':hashlib.sha256(response).hexdigest(),'saved_request_sha256':hashlib.sha256(request).hexdigest(),'new_models_or_listening':0}
Path('/var/tmp/stage11-normal-mode-20261012/ambiguous.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary))
