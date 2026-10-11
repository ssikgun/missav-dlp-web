import hashlib,json
from pathlib import Path
from teddy_discovery_stage11_normal_mode import validate_normal_completion,PROOF_NAME,validate_normal_translation,reconstruct
from teddy_discovery_stage11_controller import parse_asr_result_bytes
from teddy_discovery_stage12_bulk_runner import build_deployment_config,build_dependencies,DISCOVERY_DB,NAS,read_exact_nas_inventory
from teddy_discovery_stage12_inventory import build_subtitle_ssh_reader,Stage12HoldingsInventory
from teddy_discovery_stage12_rollout import _preflight_artifact_bundle,build_nas_preflight_filesystem
from teddy_discovery_subtitle_text import parse_subtitle_bytes
from teddy_discovery_ko_srt import generate_korean_srt
root=Path('/opt/missav-dlp-web/discovery/stage11-normal-e2e-20261012');summaries=[]
d=build_dependencies(build_deployment_config());fs=build_nas_preflight_filesystem(**NAS)
for title in ('FNS-247','JUR-750'):
 directory=root/'artifacts'/title
 if not (directory/'stage11-controller-report-v1.json').exists(): continue
 result=validate_normal_completion(directory/'stage11-controller-report-v1.json',directory/'clean-ko-v1.srt',directory/'baseline-asr-v1.json',title=title)
 row=d.live.holding_resolver(title)
 record=Stage12HoldingsInventory(db_path=DISCOVERY_DB,subtitle_reader=build_subtitle_ssh_reader(**NAS),
     holdings_loader=lambda _:dict(holdings=[row])).run().records[0]
 clean,report,clean_sha,report_sha=_preflight_artifact_bundle(record,root/'artifacts')
 baseline=parse_asr_result_bytes((directory/'baseline-asr-v1.json').read_bytes());snapshot=baseline.source_snapshot
 info=fs.lstat(snapshot.canonical_video_relative)
 assert info.st_size==snapshot.source_size and info.st_mtime_ns==snapshot.source_mtime_ns
 doc=parse_subtitle_bytes(clean.read_bytes(),'srt');assert generate_korean_srt(doc.cues).payload==clean.read_bytes()
 assert all(a.start_ms<=b.start_ms for a,b in zip(doc.cues,doc.cues[1:]))
 assert len({(c.start_ms,c.end_ms,c.text) for c in doc.cues})==len(doc.cues)
 proof=json.loads((directory/PROOF_NAME).read_bytes())
 indices=[i for c in proof['playback'] for i in c['source_indexes']]
 prep,_=reconstruct(directory,baseline)
 from teddy_discovery_subtitle_source_quality import classify_source_document,OMIT_METADATA
 metadata={d.source_index for d in classify_source_document(prep.route_decision.alignment_application.bundle.external_ja_document) if d.action==OMIT_METADATA}
 assert len(indices)==len(set(indices)) and set(range(proof['source_count']))-set(indices)==metadata
 receipts=[json.loads(p.read_bytes()) for p in (root/'staging'/title).glob('*.receipt.json')]
 assert receipts and all(r['returncode']==0 and r['tools_count']==0 and r['runtime_session_id'] for r in receipts)
 assert all(r['provider']=='openai-codex' and r['model']=='gpt-5.6-luna' and r['reasoning']=='xhigh' for r in receipts)
 summaries.append({'title':title,'status':'PASS','source_video_present':True,'JA':proof['source_count'],'KO':len(doc.cues),'absorption':proof['absorption_count'],'metadata_omitted':len(metadata),'automatic_insertion':False,'user_intervention':0,'native_hermes_calls':len(receipts),'native_runtime_sessions':[r['runtime_session_id'] for r in receipts],'srt_path':str(clean),'srt_sha256':clean_sha,'stage12_artifact_preflight':'PASS','canonical_existing_ko_protected':record.existing_ko,'time_order':'PASS','cue_identity_unique_coverage':'PASS','exact_duplicate_cues':0,'srt_readback':'PASS','baseline_reused':True,'external_acquisition':'RETAINED_ORIGINAL_JA'})
Path('/var/tmp/stage11-normal-mode-20261012/e2e.json').write_text(json.dumps(summaries,indent=2)+'\n')
for r in summaries:
 r=dict(r);r.pop('native_runtime_sessions');print(json.dumps(r))
