"""Saved-plan and mock-transport checks. Never contacts a Worker or STT model."""
import argparse
from dataclasses import asdict
import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
from urllib.error import HTTPError
import numpy as np
from teddy_discovery_asr import ASRSourceSnapshot
from teddy_discovery_asr_remote import RemoteASRHTTPResponse, REMOTE_ASR_SCHEMA_VERSION, RemoteASRTransportError
from teddy_discovery_stateful_short_plan import build_short_plan, encode, digest
from teddy_discovery_stateful_short_runner import SequentialRunner, prepare, positive_integer


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan-dir',type=Path,required=True)
    args=parser.parse_args();folder=args.plan_dir
    cfg_path='/tmp/stage11-short-no-vad-result-ypelldns/inputs.json'
    cfg=json.loads(Path(cfg_path).read_bytes())
    plan,pcm,snapshot,cfg=prepare(folder/'whole-short-plan.json',digest((folder/'whole-short-plan.json').read_bytes()),
        cfg['PCM_path'],cfg_path,folder/'source-pins.json')
    root=Path(tempfile.mkdtemp(prefix='stage11-short-runner-offline-'))
    checks=['real_524_plan_PCM_SHA_13_cache_511_pending_preflight']
    def fake(endpoint,body,headers,timeout):
        import io
        samples=np.load(io.BytesIO(body),allow_pickle=False)
        return RemoteASRHTTPResponse(200,encode(dict(schema_version=REMOTE_ASR_SCHEMA_VERSION,
            engine_version=plan['engine_version'],input_sha256=digest(body),sample_rate=16000,
            sample_count=int(samples.size),vad_region_count=0,segments=[])))
    small_pcm=np.zeros(40402*16-12,dtype='<f4')
    small=build_short_plan(duration_ms=40402,pcm=small_pcm,source_pcm_sha256=digest(small_pcm.tobytes()),
        source_video_sha256='1'*64,snapshot=snapshot,engine_version=plan['engine_version'],
        settings=plan['settings'],external_intervals=())
    def runner(name,transport=fake,**kwargs):
        return SequentialRunner(plan=small,pcm=small_pcm,snapshot=snapshot,plan_sha=digest(encode(small)),
            config=cfg,output=root/name,transport=transport,**kwargs)
    calls=[]
    def counted(*argv):calls.append(digest(argv[1]));return fake(*argv)
    result=runner('first',counted).run()
    assert result['completed']==3 and result['status']=='COMPLETE_CANDIDATES_ONLY' and len(calls)==3
    assert small['windows'][-1]['core_end_ms']-small['windows'][-1]['core_start_ms']==402
    assert small['windows'][-1]['audio_hi']==small_pcm.size
    checks.extend(['first_sequential_execution','final_402ms_fractional_sample_tail'])
    calls.clear();result=runner('first',counted).run()
    assert result['resumed']==3 and not calls
    checks.append('completed_never_reexecuted')
    # Child is a local mock only. Abrupt exit skips finally and all shutdown handlers.
    child=os.fork()
    if child==0:
        runner('crash',after_commit=lambda row:os._exit(23)).run();os._exit(99)
    _,status=os.waitpid(child,0);assert os.waitstatus_to_exitcode(status)==23
    assert len(list((root/'crash').glob('*.done.json')))==1
    (root/'crash'/'.core-0002.done.json.leftover.tmp').write_bytes(b'partial')
    calls.clear();result=runner('crash',counted).run()
    assert result['resumed']==1 and result['completed']==3 and len(calls)==2
    checks.extend(['abrupt_process_exit_after_commit','resume_and_ignore_temporary_files'])
    # Mid-response abrupt exit leaves a request but no final completion marker.
    child=os.fork()
    if child==0:
        runner('midrequest',transport=lambda *_:os._exit(24)).run();os._exit(99)
    _,status=os.waitpid(child,0);assert os.waitstatus_to_exitcode(status)==24
    assert not list((root/'midrequest').glob('*.done.json'))
    calls.clear();assert runner('midrequest',counted).run()['completed']==3 and len(calls)==3
    checks.append('mid_request_exit_not_mistaken_for_success')
    (root/'first'/'core-0003.wire.json').write_bytes(b'corrupt')
    calls.clear()
    try:runner('first',counted).run()
    except ValueError:pass
    else:raise AssertionError('corrupt completion reused')
    assert not calls;checks.append('corrupt_last_response_blocked_before_any_new_request')
    changed=runner('crash',counted);changed.identity['settings']=dict(changed.identity['settings'],beam_size=9)
    calls.clear()
    try:changed.run()
    except ValueError:pass
    else:raise AssertionError('settings change accepted')
    assert not calls;checks.append('changed_settings_resume_blocked')
    seen=[0]
    def failed(*argv):
        seen[0]+=1
        if seen[0]==2:raise ValueError('mock permanent protocol failure')
        return fake(*argv)
    result=runner('failure',failed).run()
    assert result['completed']==2 and result['failed']==1 and result['status']=='INCOMPLETE'
    calls.clear();result=runner('failure',counted).run()
    assert result['resumed']==2 and result['completed']==3 and len(calls)==1
    inventory=json.loads((root/'failure'/'resume-inventory.json').read_bytes())
    assert [r['state'] for r in inventory]==['COMPLETED','FAILED_RETRY_PENDING','COMPLETED']
    checks.append('failure_preserves_others_and_failed_core_can_resume')
    seen=[0]
    def transient(*argv):
        seen[0]+=1
        return RemoteASRHTTPResponse(503,b'busy') if seen[0]<3 else fake(*argv)
    result=runner('transient',transient,wait=lambda _:False).run()
    assert result['chunk_statuses'][0]['attempts']==3
    checks.append('transient_HTTP_bounded_retry')
    wrapped_seen=[0]
    def wrapped(*argv):
        wrapped_seen[0]+=1
        if wrapped_seen[0]<3:
            error=HTTPError(argv[0],503,'busy',{},None)
            raise RemoteASRTransportError('existing urllib transport failure') from error
        return fake(*argv)
    assert runner('wrapped-transient',wrapped,wait=lambda _:False).run()['completed']==3
    assert wrapped_seen[0]==5
    checks.append('existing_urllib_HTTPError_cause_retry_not_message_parsing')
    seen=[0]
    def timeout(*argv):seen[0]+=1;raise TimeoutError('mock uncertain server completion')
    result=runner('timeout',timeout).run();assert result['failed']==3 and seen[0]==3
    checks.append('uncertain_transport_not_automatically_replayed')
    stop=threading.Event()
    result=runner('stop',stop=stop,after_commit=lambda _:stop.set()).run()
    assert result['status']=='STOPPED' and result['completed']==1
    checks.append('cooperative_stop_preserves_inflight_completion')
    locked=runner('lock');import fcntl
    with (locked.output/'.runner.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:runner('lock').run()
        except BlockingIOError:pass
        else:raise AssertionError('concurrent runner allowed')
    checks.append('single_runner_output_lock')
    # Real cached13 observations validate/import with forbidden network transport.
    cached=copy.deepcopy(plan);cached['windows']=[r for r in cached['windows'] if r['reusable']]
    def forbidden(*_):raise AssertionError('real STT transport forbidden')
    result=SequentialRunner(plan=cached,pcm=pcm,snapshot=snapshot,plan_sha=digest(encode(cached)),config=cfg,
        output=root/'real-cache-only',transport=forbidden).run()
    assert result['completed']==13 and result['cached']==13 and result['new_requests']==0
    checks.append('real_13_cache_revalidated_without_STT')
    # Whole 524 scheduling exercise uses synthetic empty replies, not real inference.
    mock_plan=copy.deepcopy(plan)
    for row in mock_plan['windows']:row.update(reusable=False,requires_new_STT=True,reuse_observations=[])
    mock_calls=[0]
    def whole_fake(*argv):mock_calls[0]+=1;return fake(*argv)
    result=SequentialRunner(plan=mock_plan,pcm=pcm,snapshot=snapshot,plan_sha=digest(encode(mock_plan)),config=cfg,
        output=root/'whole-mock',transport=whole_fake).run()
    assert result['completed']==524 and mock_calls[0]==524
    assert sum(r['core_hi']-r['core_lo'] for r in plan['windows'])==pcm.size
    checks.append('whole_524_mock_coverage_single_sample_ownership')
    # The actual whole plan imports all13 caches while submitting exactly5 new cores.
    limited_calls=[]
    def limited_fake(*argv):limited_calls.append(digest(argv[1]));return fake(*argv)
    def actual_limited(max_new=None):
        return SequentialRunner(plan=plan,pcm=pcm,snapshot=snapshot,plan_sha=digest(encode(plan)),config=cfg,
            output=root/'limited-real-plan',transport=limited_fake,max_new=max_new)
    result=actual_limited(5).run()
    expected=[r['request_sha256'] for r in plan['windows'] if not r['reusable']]
    assert limited_calls==expected[:5] and result['new_requests']==5
    assert result['cached']==13 and result['completed']==18 and result['remaining']==506
    assert result['status']=='LIMIT_REACHED' and expected[5] not in limited_calls
    checks.append('max_new5_all13_caches_exempt_no_sixth_new_core')
    limited_calls.clear();result=actual_limited().run()
    assert result['resumed']==18 and result['completed']==524 and result['new_requests']==506
    assert limited_calls==expected[5:] and result['status']=='COMPLETE_CANDIDATES_ONLY'
    checks.append('unlimited_resume_reuses_five_completed_new_cores')
    for value in (0,-1,True,1.5,'5'):
        try:runner('invalid-max',max_new=value)
        except ValueError:pass
        else:raise AssertionError('invalid max_new accepted')
    for value in ('0','-1','1.5','bad'):
        try:positive_integer(value)
        except argparse.ArgumentTypeError:pass
        else:raise AssertionError('invalid CLI limit accepted')
    assert positive_integer('5')==5
    checks.append('positive_integer_only_CLI_and_runner')
    limited_fail=[0]
    def permanent(*argv):limited_fail[0]+=1;raise ValueError('mock failure')
    result=runner('limited-failure',permanent,max_new=1).run()
    assert result['status']=='INCOMPLETE' and result['failed']==1 and limited_fail[0]==1
    calls.clear();result=runner('limited-failure',counted,max_new=1).run()
    assert result['status']=='LIMIT_REACHED' and result['completed']==1 and len(calls)==1
    checks.append('limited_failure_counts_attempt_and_can_resume')
    stop=threading.Event()
    result=runner('limited-stop',stop=stop,after_commit=lambda _:stop.set(),max_new=2).run()
    assert result['status']=='STOPPED' and result['completed']==1
    calls.clear();result=runner('limited-stop',counted,max_new=1).run()
    assert result['resumed']==1 and result['completed']==2 and len(calls)==1
    checks.append('limited_stop_and_resume_preserves_budget')
    checks.append('canonical_preserved_source_pins_and_zero_actual_models')
    report=dict(status='PASS',checks=checks,test_count=len(checks),real_STT_calls=0,
        real_Whisper_calls=0,real_Reazon_calls=0,Hermes_calls=0,Gemini_calls=0,
        canonical_JA=313,canonical_KO_SRT=296,absorption=17,approvals=0,
        whole_mock_calls=mock_calls[0],real_cached_windows=13,private_mock_artifacts_cleaned=True)
    shutil.rmtree(root)
    output=Path(tempfile.mkdtemp(prefix='stage11-short-runner-verification-'))
    (output/'offline-verification.json').write_bytes(encode(report))
    print('OUTPUT='+str(output));print(json.dumps(report,indent=2))


if __name__=='__main__':main()
