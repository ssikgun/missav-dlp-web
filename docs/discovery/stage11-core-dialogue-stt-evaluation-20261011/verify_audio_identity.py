"""Independent byte/sample identity check. Uses installed numpy only, no models."""
import hashlib,json,wave
from pathlib import Path
import numpy as np
root=Path('/var/tmp/stage11-core-dialogue-stt-evaluation-20261011')
cfg=json.loads((root/'config.json').read_text());ev=json.loads((root/'evaluation.json').read_text())
groups=json.loads(Path(cfg['priority_manifest']).read_text())['groups']
byid={g['group_id']:g for g in groups}
parent=np.memmap('/tmp/stage11-full-no-vad-result-fn0841kg/source-audio.float32.pcm',dtype='<f4',mode='r')
hashbytes=lambda b:hashlib.sha256(b).hexdigest()
def audio(p):
 with wave.open(str(p)) as f:return f.readframes(f.getnframes())
checks=[]
for r in ev['clips']:
 g=byid[r['group_id']];source=g['source_audio'];a,b=r['core_range_ms']
 arr=np.load(source['source_npy'],allow_pickle=False)
 assert len(arr)==(source['end_ms']-source['start_ms'])*16
 assert np.array_equal(arr,parent[source['start_ms']*16:source['end_ms']*16])
 context=audio(Path(cfg['scope_audit']).parent/'context'/(r['id']+'.wav'))
 core=audio(Path(cfg['scope_audit']).parent/'core'/(r['id']+'.wav'))
 offset=round((a-r['original_context_range_ms'][0])*16)
 assert core==context[offset*2:offset*2+(b-a)*32]
 rr=r['reazon'];pcm16=audio(rr['input_wav_path']);f32=np.frombuffer(pcm16,dtype='<i2').astype('<f4')/32768
 assert hashbytes(f32.tobytes())==rr['input_float32_sha256']
 lo,hi=[round(t*16) for t in rr['input_range_ms']]
 expected=np.clip(parent[lo:hi],-1,1)*32767
 # Saved first four use rounded PCM16; remaining nine use truncated PCM16.
 conversion='ROUND' if rr['source_path']==cfg['old_reazon'] else 'TRUNCATE'
 if conversion=='ROUND':expected=np.rint(expected)
 assert pcm16==expected.astype('<i2').tobytes(),r['id']
 for s in r['whisper']['saved_full_short']:
  lo,hi=[round(t*16) for t in s['input_range_ms']]
  assert np.array_equal(np.load(s['request_path'],allow_pickle=False),parent[lo:hi])
 checks.append({'id':r['id'],'whisper_source_float32_exact':True,'core_context_crop_exact':True,'reazon_float32_payload_sha_exact':True,'reazon_parent_conversion_exact':True,'reazon_conversion':conversion,'saved_full_short_input_exact':True})
(root/'audio-identity-audit.json').write_text(json.dumps({'status':'PASS','cases':checks,'new_model_imports_or_calls':0},indent=2)+'\n')
print('PASS: 13 core crops, parent PCM, saved Whisper inputs and actual Reazon float32 input SHA')
