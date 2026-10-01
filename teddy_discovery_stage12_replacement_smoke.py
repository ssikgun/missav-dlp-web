"""Private fixture DB/files only. No live NAS/Jellyfin/model/rollout access."""
from dataclasses import replace
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from teddy_discovery_stage12_rollout_smoke import inventory_record, write_valid_bundle
from teddy_discovery_stage12_inventory import Stage12HoldingsInventoryReport
from teddy_discovery_stage12_rollout import Stage12RolloutStateStore
from teddy_discovery_stage12_replacement import (
    Stage12Replacement, ReplacementAuthorization, AUTHORIZATION_MODE,
)
from teddy_discovery_subtitle_replace import replacement_worker, ReplacementWitness, SubtitleReplacementMutator
from teddy_discovery_subtitle_publish import _validated_artifact, SubtitleSSHMutator, SubtitlePublishCollisionError
from teddy_discovery_subtitle_publish_smoke import _ssh, LocalScriptRunner
from teddy_discovery_subtitle import derive_target_ko_relative
from teddy_discovery_ko_srt import generate_korean_srt
from teddy_discovery_subtitle_text import SubtitleCue
from teddy_discovery_stage11_controller import _serialize_report
from teddy_discovery_stage12_batch import Stage12JellyfinRecognition
from teddy_discovery_jellyfin import jellyfin_media_path


class Crash(BaseException):
    pass


class Fixture:
    def __init__(self, root, *, published=True):
        self.record=inventory_record('RPL-101',holding_id=123)
        self.store=Stage12RolloutStateStore(root/'state.sqlite3')
        self.store.initialize_from_inventory(Stage12HoldingsInventoryReport((self.record,)))
        _,old_path,old_report,old=write_valid_bundle(root/'old',self.record)
        self.old_bytes=old_path.read_bytes()
        self.old=old['clean_sha256']
        from teddy_discovery_stage12_rollout import _record_video
        self.video=_record_video(self.record)
        self.destination=derive_target_ko_relative(self.video)
        if published:
            self.store.transition(self.record.dvd_id,'RUNNING',reason='fixture',provenance={})
            self.store.transition(self.record.dvd_id,'GENERATED',reason='fixture',provenance={},
                artifact_path=str(old_path),artifact_sha256=self.old,report_path=str(old_report),
                report_sha256=hashlib.sha256(old_report.read_bytes()).hexdigest())
            self.store.transition(self.record.dvd_id,'PUBLISHED',reason='fixture',provenance={
                'publication_performed':True,'atomic_install':True,'destination_verified':True,
                'destination_relative':self.destination,'destination_sha256':self.old},
                destination_relative=self.destination)
        self.initial_state=self.store.get(self.record.dvd_id)
        self.original_events=self.events()
        self.candidate_root=root/'candidate'
        _,self.clean_path,self.report_path,self.report=write_valid_bundle(self.candidate_root,self.record)
        self.artifact=generate_korean_srt((SubtitleCue(0,1500,'승인된 새 자막'),))
        self.new=self.artifact.sha256
        self.clean_path.write_bytes(self.artifact.payload)
        self.report['clean_sha256']=self.new
        self.report_path.write_bytes(_serialize_report(self.report))
        self.library=root/'library'
        self.target=self.library/self.destination
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(self.old_bytes)
        media=self.library/self.video.relative_path
        media.write_bytes(b'x'*self.record.source_size_bytes)
        os.utime(media,ns=(self.record.source_mtime_ns,self.record.source_mtime_ns))
        self.nas_calls=0
        self.jellyfin_calls=0
        self.jelly_fail=False
        self.corrupt_post=False
        self.nas=SubtitleReplacementMutator(_ssh(self.library,LocalScriptRunner()))
        self.owner=Stage12Replacement(self.store,current_record=lambda dvd:self.record,
                                     nas=self,jellyfin_recognizer=self.recognize)
        self.auth=ReplacementAuthorization(self.record.dvd_id,self.old,self.new,
                                          AUTHORIZATION_MODE,'Operator reviewed playback and approved replacement.')

    def events(self):
        with sqlite3.connect(self.store.state_path.as_uri()+'?mode=ro',uri=True) as conn:
            return tuple(conn.execute('SELECT * FROM stage12_rollout_events ORDER BY event_id').fetchall())

    def inspect(self,*args):
        return self.nas.inspect(*args)

    def replace(self,*args,**kwargs):
        self.nas_calls+=1
        result=self.nas.replace(*args,**kwargs)
        if self.corrupt_post:
            self.target.write_bytes(b'unexpected post-write bytes')
        return result

    def reconcile(self,*args,**kwargs):
        return self.nas.reconcile(*args,**kwargs)

    def recognize(self,dvd,video,destination):
        self.jellyfin_calls+=1
        assert dvd==self.record.dvd_id and video==self.video and destination==self.destination
        if self.jelly_fail:
            raise ValueError('synthetic Jellyfin pending')
        return Stage12JellyfinRecognition('item-fixture',jellyfin_media_path(video.relative_path),
            jellyfin_media_path(destination),'ko','subrip',True,False,'NOT_REQUIRED')

    def run(self,**changes):
        args=dict(expected_old_sha256=self.old,expected_new_sha256=self.new,
                  candidate_root=self.candidate_root,authorization=self.auth)
        args.update(changes)
        return self.owner.run(self.record.dvd_id,**args)

    def history(self):
        return self.store.replacement_history(self.record.dvd_id)


def reject(callback):
    try:
        callback()
    except Exception:
        return
    raise AssertionError('invalid replacement accepted')


def main():
    passed=0
    def check(name,callback):
        nonlocal passed
        callback()
        passed+=1
        print('PASS='+name)

    invalid_cases=('unauthorized','pending','old-sha','candidate-sha','same-sha','malformed',
                   'report-detached','report-published','fingerprint','destination',
                   'absent','symlink','nonregular','third-sha')
    for case in invalid_cases:
        with tempfile.TemporaryDirectory() as raw:
            f=Fixture(Path(raw),published=case!='pending')
            changes={'execute':True}
            if case=='unauthorized': changes['authorization']=None
            elif case=='old-sha':
                changes['expected_old_sha256']='1'*64
                changes['authorization']=replace(f.auth,expected_old_sha256='1'*64)
            elif case=='candidate-sha':
                changes['expected_new_sha256']='1'*64
                changes['authorization']=replace(f.auth,expected_new_sha256='1'*64)
            elif case=='same-sha':
                changes['expected_new_sha256']=f.old
                changes['authorization']=replace(f.auth,expected_new_sha256=f.old)
            elif case=='malformed': f.clean_path.write_bytes(b'not SRT')
            elif case in ('report-detached','report-published'):
                report=json.loads(f.report_path.read_bytes())
                report['clean_sha256' if case=='report-detached' else 'publication_performed']='1'*64 if case=='report-detached' else True
                f.report_path.write_bytes(json.dumps(report).encode())
            elif case=='fingerprint': f.record=replace(f.record,source_size_bytes=101)
            elif case=='destination':
                f.owner.store=SimpleNamespace(read_replacement_original=lambda _:f.initial_state,
                    effective_publication=lambda _:replace(f.initial_state,destination_relative='RPL/RPL-101/other.ko.srt'),
                    replacement_execution_lock=f.store.replacement_execution_lock)
            elif case in ('absent','symlink','nonregular'):
                f.target.unlink()
                if case=='symlink': f.target.symlink_to(f.clean_path)
                if case=='nonregular': f.target.mkdir()
            elif case=='third-sha': f.target.write_bytes(b'third bytes')
            check(case,lambda:reject(lambda:f.run(**changes)))
            assert f.nas_calls==f.jellyfin_calls==0 and f.history()==()
            assert f.events()==f.original_events

    with tempfile.TemporaryDirectory() as raw:
        f=Fixture(Path(raw))
        db_before=f.store.state_path.read_bytes()
        preflight=f.run()
        assert preflight.witness.sha256==f.old and f.history()==()
        assert f.store.state_path.read_bytes()==db_before and f.nas_calls==f.jellyfin_calls==0
        print('PASS=READ_ONLY_DRY_RUN')
        final=f.run(execute=True)
        assert final['phase']=='COMPLETED' and f.nas_calls==f.jellyfin_calls==1
        assert f.target.read_bytes()==f.artifact.payload
        assert f.store.effective_publication(f.record.dvd_id).artifact_sha256==f.new
        assert f.store.get(f.record.dvd_id)==f.initial_state and f.events()==f.original_events
        history=f.history()
        assert [e['phase'] for e in history]==['INTENT_RECORDED','NAS_PENDING','NAS_REPLACED','JELLYFIN_PENDING','COMPLETED']
        assert [e['sequence'] for e in history]==list(range(1,6))
        assert all(e['operator_approved'] and e['plan']['old_sha256']==f.old for e in history)
        assert f.run(execute=True)==final and f.history()==history and f.nas_calls==1 and f.jellyfin_calls==1
        print('PASS=ATOMIC_COMPLETION_HISTORY_AND_IDEMPOTENCE')
        # No weakening of the existing differing-final collision contract.
        reject_normal=SubtitleSSHMutator(_ssh(f.library,LocalScriptRunner()))
        try:
            reject_normal.publish_korean_srt(canonical_video=f.video,artifact=generate_korean_srt((SubtitleCue(0,1000,'다른 자막'),)))
        except SubtitlePublishCollisionError:
            pass
        else: raise AssertionError('normal publisher overwrite allowed')
        print('PASS=NORMAL_PUBLISHER_COLLISION_UNCHANGED')

    for crash_point in ('after_intent','after_nas_replace'):
        with tempfile.TemporaryDirectory() as raw:
            f=Fixture(Path(raw))
            def crash(point):
                if point==crash_point: raise Crash()
            try: f.run(execute=True,checkpoint=crash)
            except Crash: pass
            else: raise AssertionError('crash hook absent')
            writes=f.nas_calls
            if crash_point=='after_nas_replace':
                assert f.target.read_bytes()==f.artifact.payload and writes==1
            f.run(execute=True)
            assert f.nas_calls==1 and (crash_point!='after_nas_replace' or f.nas_calls==writes)
            assert f.events()==f.original_events
            print('PASS=CRASH_RETRY_'+crash_point)

    with tempfile.TemporaryDirectory() as raw:
        f=Fixture(Path(raw)); f.jelly_fail=True
        reject(lambda:f.run(execute=True))
        assert f.history()[-1]['phase']=='FAILED_RETRYABLE'
        assert f.history()[-1]['effective_sha256']==f.new
        assert f.store.effective_publication(f.record.dvd_id).artifact_sha256==f.new
        f.jelly_fail=False
        f.run(execute=True)
        assert f.nas_calls==1 and f.jellyfin_calls==2
        print('PASS=JELLYFIN_PENDING_AND_ONLY_RETRY')
    with tempfile.TemporaryDirectory() as raw:
        f=Fixture(Path(raw)); f.corrupt_post=True
        reject(lambda:f.run(execute=True))
        assert f.history()[-1]['phase']=='FAILED_TERMINAL' and f.jellyfin_calls==0
        reject(lambda:f.run(execute=True))
        assert f.nas_calls==1
        print('PASS=POST_WRITE_MISMATCH_FAIL_CLOSED')

    with tempfile.TemporaryDirectory() as raw:
        f=Fixture(Path(raw)); operation='b'*64
        def crash(point):
            if point=='after_exchange': raise Crash()
        try:
            replacement_worker(str(f.library),f.video.relative_path,f.destination,
                'replace',f.old,f.new,operation,f.artifact.payload,checkpoint=crash)
        except Crash: pass
        else: raise AssertionError('native exchange crash not injected')
        backups=list(f.target.parent.glob('*.replacement-'+operation))
        assert len(backups)==1 and backups[0].read_bytes()==f.old_bytes
        result=replacement_worker(str(f.library),f.video.relative_path,f.destination,
            'reconcile',f.old,f.new,operation,f.artifact.payload)
        assert result=={'sha256':f.new,'replaced':False} and not backups[0].exists()
        assert f.target.read_bytes()==f.artifact.payload
        print('PASS=NATIVE_EXCHANGE_CRASH_BACKUP_RECONCILIATION')
    with tempfile.TemporaryDirectory() as raw:
        f=Fixture(Path(raw))
        def crash(point):
            if point=='after_intent': raise Crash()
        try: f.run(execute=True,checkpoint=crash)
        except Crash: pass
        f.target.write_bytes(b'third state after crash')
        reject(lambda:f.run(execute=True))
        assert f.nas_calls==f.jellyfin_calls==0 and f.history()[-1]['phase']=='FAILED_TERMINAL'
        print('PASS=THIRD_SHA_AFTER_INTENT_NO_OVERWRITE')
    with tempfile.TemporaryDirectory() as raw:
        f=Fixture(Path(raw))
        media=f.library/f.video.relative_path
        os.utime(media,ns=(999,999))
        reject(lambda:f.run(execute=True))
        assert f.nas_calls==f.jellyfin_calls==0 and f.history()==()
        print('PASS=NAS_VIDEO_FINGERPRINT_DRIFT')

    for detached in ('media','subtitle','language'):
        with tempfile.TemporaryDirectory() as raw:
            f=Fixture(Path(raw))
            def recognizer(dvd,video,destination):
                normal=f.recognize(dvd,video,destination)
                field={'media':'item_path','subtitle':'subtitle_path','language':'subtitle_language'}[detached]
                return replace(normal,**{field:'other'})
            f.owner.jellyfin_recognizer=recognizer
            reject(lambda:f.run(execute=True))
            assert f.history()[-1]['phase']=='FAILED_RETRYABLE' and f.nas_calls==1
            f.owner.jellyfin_recognizer=f.recognize
            f.run(execute=True)
            assert f.nas_calls==1
            print('PASS=JELLYFIN_DETACHED_'+detached)
    with tempfile.TemporaryDirectory() as raw:
        f=Fixture(Path(raw))
        checked=f.run()
        reject(lambda:f.store.append_replacement(checked.plan,'INTENT_RECORDED',expected_sequence=0,authorization=None))
        assert f.history()==()
        intent=f.store.append_replacement(checked.plan,'INTENT_RECORDED',expected_sequence=0,authorization=f.auth)
        reject(lambda:f.store.append_replacement(checked.plan,'NAS_PENDING',expected_sequence=0,authorization=f.auth))
        assert f.history()==(intent,)
        f.run(execute=True)
        assert f.history()[0]==intent
        print('PASS=NATIVE_STORE_AUTHORIZATION_CAS_APPEND_ONLY')
    with tempfile.TemporaryDirectory() as raw:
        f=Fixture(Path(raw))
        f.run(execute=True)
        history=f.history()
        # A subsequent replacement binds to the effective new SHA while the
        # original publication row and event history remain byte-for-byte stable.
        old=f.new
        artifact=generate_korean_srt((SubtitleCue(0,2000,'다음 승인 자막'),))
        next_root=Path(raw)/'next-candidate'
        _,next_clean,next_report,report=write_valid_bundle(next_root,f.record)
        next_clean.write_bytes(artifact.payload)
        report['clean_sha256']=artifact.sha256
        next_report.write_bytes(_serialize_report(report))
        authorization=ReplacementAuthorization(f.record.dvd_id,old,artifact.sha256,
            AUTHORIZATION_MODE,'Operator approved subsequent replacement.')
        final=f.run(execute=True,expected_old_sha256=old,expected_new_sha256=artifact.sha256,
                    candidate_root=next_root,authorization=authorization)
        assert final['replacement_sequence']==2 and f.history()[:len(history)]==history
        assert f.store.get(f.record.dvd_id)==f.initial_state and f.events()==f.original_events
        assert f.store.effective_publication(f.record.dvd_id).artifact_sha256==artifact.sha256
        print('PASS=SUBSEQUENT_REPLACEMENT_EFFECTIVE_SHA_HISTORY')

    with tempfile.TemporaryDirectory() as raw:
        f=Fixture(Path(raw))
        import ctypes
        native=ctypes.CDLL(None,use_errno=True)
        calls=[]
        def race_exchange(*args):
            if not calls:
                f.target.write_bytes(b'third value at atomic boundary')
            calls.append(True)
            return native.renameat2(*args)
        with patch('ctypes.CDLL',return_value=SimpleNamespace(renameat2=race_exchange)):
            reject(lambda:replacement_worker(str(f.library),f.video.relative_path,f.destination,
                'replace',f.old,f.new,'c'*64,f.artifact.payload))
        assert f.target.read_bytes()==b'third value at atomic boundary' and len(calls)==2
        assert not list(f.target.parent.glob('*.replacement-'+'c'*64))
        print('PASS=ATOMIC_EDGE_RACE_ROLLBACK_PRESERVES_CONCURRENT_BYTES')

    # Native worker corruption/race tests exercise the exact exchanged bytes.
    for fault in ('temp-corrupt','target-race','post-corrupt','parent-symlink'):
        with tempfile.TemporaryDirectory() as raw:
            f=Fixture(Path(raw))
            operation='a'*64
            def hook(point):
                if fault=='temp-corrupt' and point=='before_exchange':
                    next(f.target.parent.glob('*.replacement-'+operation)).write_bytes(b'bad')
                if fault=='target-race' and point=='before_exchange': f.target.write_bytes(b'raced')
                if fault=='post-corrupt' and point=='after_exchange': f.target.write_bytes(b'bad')
            if fault=='parent-symlink':
                original=f.target.parent
                moved=original.with_name('moved'); original.rename(moved); original.symlink_to(moved,target_is_directory=True)
            reject(lambda:replacement_worker(str(f.library),f.video.relative_path,f.destination,
                'replace',f.old,f.new,operation,f.artifact.payload,checkpoint=hook))
            if fault=='temp-corrupt': assert f.target.read_bytes()==f.old_bytes
            print('PASS=NATIVE_'+fault)
    print('STAGE12_REPLACEMENT_SMOKE=PASS')


if __name__=='__main__':
    main()
