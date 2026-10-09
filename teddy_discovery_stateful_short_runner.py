"""Sequential/resumable short-plan runner; live ASR requires explicit CLI --run."""
import argparse
from dataclasses import asdict
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from urllib.error import HTTPError

import numpy as np
from teddy_discovery_asr import ASRSourceSnapshot
from teddy_discovery_asr_remote import RemoteFasterWhisperASR, RemoteASRHTTPResponse, RemoteASRTransportError, _default_transport
from teddy_discovery_stateful_short_plan import build_short_plan, planned_chunk, offline_client, encode, digest


def file_sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def atomic(path, body):
    """Commit file only after fsync; interrupted .tmp files never signal completion."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix='.'+path.name+'.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(body); stream.flush(); os.fsync(stream.fileno())
        os.replace(tmp, path)
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def prepare(plan_path, expected_sha, pcm_path, config_path, pins_path):
    if file_sha(plan_path) != expected_sha: raise ValueError('plan SHA mismatch')
    pins = json.loads(Path(pins_path).read_bytes())
    for path, expected in pins.items():
        if file_sha(path) != expected: raise ValueError('preserved source SHA mismatch: '+path)
    plan = json.loads(Path(plan_path).read_bytes())
    cfg = json.loads(Path(config_path).read_bytes())
    if str(Path(config_path).resolve()) not in pins: raise ValueError('unpinned runtime config')
    if (cfg['settings'] != plan['settings'] or cfg['runtime_identity'] != plan['runtime_identity']
            or cfg['source_snapshot'] != plan['source_identity']
            or cfg['worker']['engine_version'] != plan['engine_version']):
        raise ValueError('execution settings/source/runtime differ')
    pcm = np.memmap(pcm_path, dtype='<f4', mode='r')
    snapshot = ASRSourceSnapshot(**plan['source_identity'])
    fresh = build_short_plan(duration_ms=plan['duration_ms'], pcm=pcm,
        source_pcm_sha256=plan['source_pcm_sha256'], source_video_sha256=plan['source_video_sha256'],
        snapshot=snapshot, engine_version=plan['engine_version'], settings=plan['settings'],
        external_intervals=(), core_ms=plan['core_ms'], padding_ms=plan['padding_ms'])
    if len(fresh['windows']) != len(plan['windows']): raise ValueError('plan coverage differs')
    fields = ('index','plan_chunk_id','core_start_ms','core_end_ms','audio_start_ms','audio_end_ms',
              'core_lo','core_hi','audio_lo','audio_hi','request_sha256','slice_pcm_sha256')
    decoder = offline_client(plan['engine_version'])
    for old, new in zip(plan['windows'], fresh['windows'], strict=True):
        if any(old[k] != new[k] for k in fields): raise ValueError('window geometry/SHA differs')
        if old['reusable'] != bool(old['reuse_observations']) or old['requires_new_STT'] == old['reusable']:
            raise ValueError('invalid reuse state')
        for obs in old['reuse_observations']:
            req, wire = Path(obs['request_path']).read_bytes(), Path(obs['response_path']).read_bytes()
            if digest(req) != old['request_sha256'] or digest(wire) != obs['response_sha256']:
                raise ValueError('cache SHA mismatch')
            decoder._decode_response(RemoteASRHTTPResponse(200, wire), chunk=planned_chunk(old, pcm, snapshot),
                                     request_body=req, expected_vad_region_count=0)
    if plan['reuse_count'] != sum(r['reusable'] for r in plan['windows']): raise ValueError('reuse count differs')
    return plan, pcm, snapshot, cfg


def worker_preflight(cfg):
    """Read-only check of existing PID, actual import precedence, code and model; no inference."""
    program = '''
import json, pathlib, os, hashlib, importlib.metadata, inspect
c=CONFIG
found=[]
for p in pathlib.Path('/proc').iterdir():
 if not p.name.isdigit(): continue
 try:
  if c['launcher'].encode() in (p/'cmdline').read_bytes().split(b'\\0'): found.append(p)
 except OSError: pass
assert len(found)==1, 'existing Worker identity is not unique'
p=found[0]
env={a.decode():b.decode() for x in (p/'environ').read_bytes().split(b'\\0') if b'=' in x for a,b in [x.split(b'=',1)] if a in (b'PYTHONPATH',b'STAGE11_MODEL_CACHE')}
assert str((p/'exe').resolve()) == str(pathlib.Path(c['python']).resolve()), 'Python executable differs'
roots=[str(pathlib.Path(c['launcher']).parent)]+env.get('PYTHONPATH','').split(':')
for name, expected in c['import_source_sha256'].items():
 path=next(pathlib.Path(root)/name for root in roots if root and (pathlib.Path(root)/name).is_file())
 assert hashlib.sha256(path.read_bytes()).hexdigest()==expected, 'actual import source differs'
assert hashlib.sha256(pathlib.Path(c['launcher']).read_bytes()).hexdigest()==c['launcher_sha256']
assert importlib.metadata.version('faster-whisper')==c['engine_version']
model=pathlib.Path(env['STAGE11_MODEL_CACHE'])/c['model_relative']
assert model.is_file() and model.stat().st_size==c['model_bytes']
from faster_whisper import WhisperModel
sig=inspect.signature(WhisperModel.transcribe)
for k,v in SETTINGS.items():
 if k in ('beam_size','best_of','condition_on_previous_text','no_speech_threshold','log_prob_threshold','compression_ratio_threshold'):
  assert sig.parameters[k].default==v, 'default setting differs'
import ctranslate2
assert ctranslate2.get_cuda_device_count()>=1
print(json.dumps({'status':'PASS_READ_ONLY','PID':int(p.name),'start_tick':(p/'stat').read_text().rsplit(')',1)[1].split()[19],'inference_calls':0}))
'''.replace('CONFIG', repr(cfg['worker'])).replace('SETTINGS', repr(cfg['settings']))
    result = subprocess.run(cfg['worker']['ssh_argv']+[cfg['worker']['python']+' -B -'],
        input=program, text=True, capture_output=True, timeout=30, check=True)
    return json.loads(result.stdout)


class SequentialRunner:
    def __init__(self, *, plan, pcm, snapshot, plan_sha, config, output, transport,
                 stop=None, wait=None, after_commit=None):
        self.plan, self.pcm, self.snapshot = plan, pcm, snapshot
        self.output = Path(output); self.output.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.output.is_symlink() or self.output.stat().st_uid != os.getuid() or self.output.stat().st_mode & 0o077:
            raise ValueError('output must be private and owned by execution user')
        self.stop = stop or threading.Event()
        self.wait = wait or self.stop.wait
        self.after_commit = after_commit or (lambda row: None)
        self.transport = transport
        self.client = RemoteFasterWhisperASR(base_url=config['asr_base_url'], request_timeout_seconds=300,
            engine_version=plan['engine_version'], transport=self.send)
        if asdict(self.client.runtime_identity) != plan['runtime_identity']: raise ValueError('runtime differs')
        self.identity = dict(plan_sha256=plan_sha, settings=plan['settings'], source=plan['source_identity'],
            PCM_sha256=plan['source_pcm_sha256'], video_sha256=plan['source_video_sha256'],
            runtime_identity=plan['runtime_identity'], runner_sha256=file_sha(__file__),
            engine_version=plan['engine_version'],
            endpoint=self.client.targeted_endpoint_url,
            codec_sha256=file_sha(Path(__file__).with_name('teddy_discovery_asr_remote.py')))
        self.current = None

    def send(self, endpoint, body, headers, timeout):
        if endpoint != self.client.targeted_endpoint_url or digest(body) != self.current['request_sha256']:
            raise ValueError('request endpoint/SHA differs')
        atomic(self.prefix.with_suffix('.request.npy'), body)
        for attempt in range(1, 4):
            if self.stop.is_set(): raise InterruptedError('user stop requested')
            self.attempts = attempt
            try:
                response = self.transport(endpoint, body, headers, timeout)
            except RemoteASRTransportError as error:
                cause=error.__cause__
                if not isinstance(cause, HTTPError) or cause.code not in (429,502,503,504): raise
                if attempt==3: raise
                response=RemoteASRHTTPResponse(cause.code,b'')
            # Retry explicit transient HTTP replies only; ambiguous transport/timeouts not auto-replayed.
            if response.status_code not in (429, 502, 503, 504) or attempt == 3: break
            if self.wait(min(attempt, 2)): raise InterruptedError('user stop requested')
        self.wire = response.body
        return response

    def validate_done(self, row, prefix):
        done = json.loads(prefix.with_suffix('.done.json').read_bytes())
        if done.get('approved') is not False or done.get('publishable') is not False:
            raise ValueError('unapproved result boundary changed')
        if done['identity'] != self.identity or done['row_sha256'] != digest(encode(row)):
            raise ValueError('completed identity/settings differ')
        req = prefix.with_suffix('.request.npy').read_bytes()
        wire = prefix.with_suffix('.wire.json').read_bytes()
        segments = prefix.with_suffix('.segments.json').read_bytes()
        if (digest(req) != row['request_sha256'] or digest(wire) != done['response_sha256']
                or digest(segments) != done['segments_sha256']):
            raise ValueError('completed result SHA mismatch')
        decoded = self.client._decode_response(RemoteASRHTTPResponse(200, wire),
            chunk=planned_chunk(row,self.pcm,self.snapshot), request_body=req, expected_vad_region_count=0)
        if encode([asdict(s) for s in decoded]) != segments or len(decoded) != done['segment_count']:
            raise ValueError('completed semantic serialization differs')
        if done['status'] != ('SUCCEEDED' if decoded else 'SUCCEEDED_EMPTY'): raise ValueError('invalid completion')
        return done

    def run(self):
        lock = (self.output/'.runner.lock').open('a+b')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            manifest = self.output/'execution-identity.json'
            if manifest.exists():
                if json.loads(manifest.read_bytes()) != self.identity: raise ValueError('resume identity differs; use a new output directory')
            else: atomic(manifest, encode(self.identity))
            saved_plan=self.output/'whole-short-plan.json'
            if saved_plan.exists() and saved_plan.read_bytes()!=encode(self.plan): raise ValueError('saved plan differs')
            if not saved_plan.exists(): atomic(saved_plan,encode(self.plan))
            # Validate every committed result before scheduling any live request.
            inventory=[]
            for row in self.plan['windows']:
                prefix=self.output/('core-'+str(row['index']).zfill(4))
                if prefix.with_suffix('.done.json').exists():
                    self.validate_done(row,prefix);state='COMPLETED'
                elif prefix.with_suffix('.failed.json').exists():state='FAILED_RETRY_PENDING'
                else:state='INCOMPLETE'
                inventory.append(dict(index=row['index'],state=state))
            atomic(self.output/'resume-inventory.json',encode(inventory))
            summary = dict(status='INCOMPLETE',completed=0,failed=0,remaining=len(self.plan['windows']),
                resumed=0,cached=0,new_requests=0,transport_attempts=0,approvals=0,publishable=False,chunk_statuses=[])
            try:
                for row in self.plan['windows']:
                    if self.stop.is_set(): break
                    self.current=row; self.prefix=self.output/('core-'+str(row['index']).zfill(4))
                    if self.prefix.with_suffix('.done.json').exists():
                        done=self.validate_done(row,self.prefix);summary['resumed']+=1
                        summary['chunk_statuses'].append(done);summary['completed']+=1
                        summary['remaining']-=1
                        continue
                    begin=time.monotonic();self.attempts=0;self.wire=None
                    try:
                        chunk=planned_chunk(row,self.pcm,self.snapshot)
                        if row['reusable']:
                            obs=row['reuse_observations'][0]
                            req=Path(obs['request_path']).read_bytes();self.wire=Path(obs['response_path']).read_bytes()
                            if digest(req)!=row['request_sha256'] or digest(self.wire)!=obs['response_sha256']:
                                raise ValueError('cached SHA changed')
                            decoded=self.client._decode_response(RemoteASRHTTPResponse(200,self.wire),
                                chunk=chunk,request_body=req,expected_vad_region_count=0)
                            atomic(self.prefix.with_suffix('.request.npy'),req);summary['cached']+=1
                        else:
                            summary['new_requests']+=1
                            decoded=self.client.transcribe_targeted_chunk(chunk)
                        segment_raw=encode([asdict(s) for s in decoded])
                        atomic(self.prefix.with_suffix('.wire.json'),self.wire)
                        atomic(self.prefix.with_suffix('.segments.json'),segment_raw)
                        done=dict(index=row['index'],plan_chunk_id=row['plan_chunk_id'],row_sha256=digest(encode(row)),
                            identity=self.identity,status='SUCCEEDED' if decoded else 'SUCCEEDED_EMPTY',
                            request_sha256=row['request_sha256'],response_sha256=digest(self.wire),
                            segments_sha256=digest(segment_raw),segment_count=len(decoded),attempts=self.attempts,
                            origin='VALIDATED_CACHE' if row['reusable'] else 'TARGETED_WHISPER',
                            core_start_ms=row['core_start_ms'],core_end_ms=row['core_end_ms'],
                            audio_start_ms=row['audio_start_ms'],audio_end_ms=row['audio_end_ms'],
                            slice_pcm_sha256=row['slice_pcm_sha256'],
                            audio_lo=row['audio_lo'],audio_hi=row['audio_hi'],wall_seconds=time.monotonic()-begin,
                            approved=False,publishable=False)
                        atomic(self.prefix.with_suffix('.done.json'),encode(done))
                        summary['completed']+=1;summary['remaining']-=1;summary['chunk_statuses'].append(done)
                        self.after_commit(row)
                    except InterruptedError:
                        break
                    except Exception as error:
                        if self.wire is not None:
                            atomic(self.prefix.with_suffix('.failed-wire.json'),self.wire)
                        failed=dict(index=row['index'],status='FAILED',error_type=type(error).__name__,
                            error=str(error),identity=self.identity,attempts=self.attempts,approved=False)
                        atomic(self.prefix.with_suffix('.failed.json'),encode(failed))
                        summary['failed']+=1;summary['chunk_statuses'].append(failed)
                    summary['transport_attempts']+=self.attempts
                    atomic(self.output/'results.json',encode(summary))
                summary['status']='COMPLETE_CANDIDATES_ONLY' if summary['completed']==len(self.plan['windows']) else 'STOPPED' if self.stop.is_set() else 'INCOMPLETE'
            finally:
                atomic(self.output/'results.json',encode(summary))
            return summary
        finally: lock.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ('plan','plan-sha256','pcm','config','source-pins','output'): parser.add_argument('--'+arg,required=True)
    parser.add_argument('--run',action='store_true',help='explicitly authorize direct live targeted requests')
    args=parser.parse_args()
    plan,pcm,snapshot,cfg=prepare(args.plan,args.plan_sha256,args.pcm,args.config,args.source_pins)
    if not args.run:
        print(json.dumps(dict(status='PASS_OFFLINE_PREFLIGHT',cores=len(plan['windows']),reused=plan['reuse_count'],
            new=plan['new_STT_count'],STT_calls=0)));return
    if shutil.disk_usage(Path(args.output).parent).free < sum(r['request_bytes'] for r in plan['windows'])+1024**3:
        raise ValueError('insufficient experiment storage')
    receipt=worker_preflight(cfg)
    stop=threading.Event()
    for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP): signal.signal(sig,lambda *_:stop.set())
    runner=SequentialRunner(plan=plan,pcm=pcm,snapshot=snapshot,plan_sha=args.plan_sha256,
        config=cfg,output=args.output,transport=_default_transport,stop=stop)
    atomic(runner.output/'worker-preflight.json',encode(receipt))
    summary=runner.run();print(json.dumps(summary,ensure_ascii=False))
    raise SystemExit(0 if summary['status']=='COMPLETE_CANDIDATES_ONLY' else 2)


if __name__=='__main__':main()
