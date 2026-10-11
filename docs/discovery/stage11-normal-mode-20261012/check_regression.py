import hashlib,json,pickle
from pathlib import Path
from teddy_discovery_stateful_translator import parse_stateful_result
from teddy_discovery_stateful_hybrid import materialize_stateful_hybrid_srt
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
pins=json.loads(Path('/var/tmp/stage11-core-dialogue-stt-evaluation-20261011/protected-before.json').read_bytes())
changed=[name for name,digest in pins.items() if not Path(name).is_file() or sha(name)!=digest]
assert not changed,changed
native=json.loads(Path('/var/tmp/stage11-clip011-boundary-recovery-20261012/native/execution-pins.json').read_bytes())
seed=Path(native['trusted_seed']); prep,boundary,first,first_raw,srt_raw=pickle.loads(seed.read_bytes())
result_path=Path(native['approved_result']);raw=result_path.read_bytes()
result=parse_stateful_result(raw,prep.package,boundary_evidence=boundary)
materialized=materialize_stateful_hybrid_srt(prep.package,result,prep.route_decision,prep)
srt_path=Path('/tmp/stage11-v8-review-srt-lfmnmpwz/FNS-247.stage11-v8.REVIEW-ONLY.ko.srt')
assert len(prep.package.cues)==313 and len(result.cues)==313
assert sum(c.absorbed_into is not None for c in result.cues)==17
assert len(materialized.playback_cues)==296 and materialized.artifact.payload==srt_path.read_bytes()
summary={'status':'PASS','protected_pin_count':len(pins),'changed_count':len(changed),'JA':313,'KO':296,'absorption':17,'source_result_sha256':sha(result_path),'srt_sha256':sha(srt_path),'source_seed_sha256':sha(seed),'original_bytes_unchanged':True}
Path('/var/tmp/stage11-normal-mode-20261012/regression.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary))
