import json
from pathlib import Path
from teddy_discovery_stage12_bulk_runner import build_deployment_config,build_dependencies
from teddy_discovery_stage11_normal_mode import controller
root=Path('/opt/missav-dlp-web/discovery/stage11-normal-e2e-20261012/artifacts')
d=build_dependencies(build_deployment_config());rows=[]
for title in ('FNS-247','JUR-750'):
 video,snapshot=controller._resolve_holding(title,d.live.holding_resolver)
 baseline=controller.parse_asr_result_bytes((root/title/controller.BASELINE_ASR_FILENAME).read_bytes())
 controller.require_matching_asr_source(baseline,snapshot)
 try:
  app=d.live.external_ja_attempt(video,baseline)
  row={'title':title,'status':'NO_CANDIDATE' if app is None else app.decision.verdict,
      'source':'LIVE_SUBTITLECAT','model_calls':0}
  if app:row.update(external_sha256=app.bundle.external_ja_payload.sha256,external_cue_count=len(app.bundle.external_ja_document.cues))
 except Exception as e:row={'title':title,'status':'FAILED','error_type':type(e).__name__,'reason':str(e),'source':'LIVE_SUBTITLECAT','model_calls':0}
 rows.append(row);print(json.dumps(row),flush=True)
Path('/var/tmp/stage11-normal-mode-20261012/live-acquisition.json').write_text(json.dumps(rows,indent=2)+'\n')
