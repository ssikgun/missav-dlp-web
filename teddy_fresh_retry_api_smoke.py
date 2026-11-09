"""Offline Flask route integration; no workers, remote services or media writes."""
import ast
import copy
import json
import os
from pathlib import Path
import queue
import stat
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

import teddy_downloader_admin_flask_smoke as fixture_module
import teddy_downloader_admin as admin
import teddy_duplicates
import teddy_routing

source = Path('downloader_runtime_overlay/app.py').read_text()
tree = ast.parse(source)
names = {'_retry_state_read','_retry_state_identity','_retry_state_matches','_retry_state_stage',
         '_retry_state_fsync_directory','_retry_state_restore','_retry_queue_put',
         'persist_retry_state_and_enqueue','persist_fresh_task_and_enqueue'}
module = ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names], type_ignores=[])
old_id = str(uuid.uuid4())
old = {'status':'에러: fixture', 'engine':'custom-hls', 'url':'https://missav123.com/ko/abcd-123'}
with fixture_module._fixture_context(tasks={old_id: copy.deepcopy(old)}) as fixture:
    core = fixture.core
    from flask import jsonify
    core.jsonify = jsonify
    core.TASKS_FILE = os.path.join(core.DOWNLOAD_DIR, '.tasks.json')
    Path(core.TASKS_FILE).write_text(json.dumps(core.tasks))
    ns = dict(os=os, stat=stat, json=json, queue=queue, uuid=uuid, threading=threading,
              STARTUP_HEALTH_ONLY=False, TASKS_FILE=core.TASKS_FILE, tasks=core.tasks,
              _tasks_lock=threading.Lock(), queue_admission_lock=core.queue_admission_lock,
              download_queue=core.download_queue)
    exec(compile(module, 'app.py', 'exec'), ns)
    core._retry_state_read = ns['_retry_state_read']
    core.persist_fresh_task_and_enqueue = ns['persist_fresh_task_and_enqueue']
    parts = Path(core.DOWNLOAD_DIR) / ('.' + old_id + '.parts'); parts.mkdir()
    (parts / 'resume-plan.json').write_text('preserved')
    (parts / '00000.ts').write_bytes(b'fixture')
    client = fixture.client
    assert fixture.open('POST', f'/api/tasks/{old_id}/retry-fresh').status_code == 401
    fixture.login()
    assert fixture.open('POST', f'/api/tasks/{old_id}/retry-fresh').status_code == 403
    assert fixture.open('POST', f'/api/tasks/{old_id}/retry-fresh', headers={'X-CSRF-Token':'wrong'}).status_code == 403
    decision = {'mode':'vpn', 'source':'fixture', 'site':'missav'}
    with mock.patch.object(admin.teddy_ownership, 'is_owned', return_value=False), \
         mock.patch.object(teddy_routing, 'resolve', return_value=decision), \
         mock.patch.object(admin, '_storage_capacity'), \
         mock.patch.object(fixture.safety, 'ensure_download_start_space'):
        def call():
            with fixture.app.test_client() as c:
                with c.session_transaction(base_url=fixture.base) as sess:
                    sess['teddy_authenticated']=True
                    sess[admin.CSRF_SESSION_KEY]='fixture-token'
                return c.post(f'/api/tasks/{old_id}/retry-fresh', base_url=fixture.base,
                              headers={'X-CSRF-Token':'fixture-token'})
        before=Path(core.TASKS_FILE).read_bytes()
        with mock.patch.dict(ns, {'_retry_queue_put': mock.Mock(side_effect=OSError('fixture'))}):
            assert call().status_code == 503
        assert core.tasks == {old_id:old} and core.download_queue.empty()
        assert Path(core.TASKS_FILE).read_bytes() == before
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses=list(pool.map(lambda _: call(), range(2)))
        assert sorted(r.status_code for r in responses)==[200,409]
        fresh=next(r.get_json()['task_id'] for r in responses if r.status_code==200)
        assert fresh != old_id and core.tasks[fresh]['fresh_retry_of']==old_id
        assert core.tasks[old_id]==old and (parts/'resume-plan.json').read_text()=='preserved'
        assert (parts/'00000.ts').read_bytes()==b'fixture'
        assert core.download_queue.get_nowait()==fresh and core.download_queue.empty()
        with fixture.app.test_request_context('/'):
            result=teddy_duplicates.guarded_enqueue(core, old['url'], lambda: (_ for _ in ()).throw(AssertionError()))
            assert result[1]==409
print('DLFR fresh retry API smoke: PASS')

# Exercise the actual filename guard without importing the runtime application.
import teddy_download_safety as safety
import teddy_storage as storage
import shlex
from types import SimpleNamespace
entry = ast.parse(Path('downloader_runtime_overlay/teddy_entrypoint.py').read_text())
guard_tree = ast.Module(body=[n for n in entry.body if isinstance(n, ast.FunctionDef) and n.name == '_fresh_output_collision_guard'], type_ignores=[])
with fixture_module._fixture_context(tasks={}) as fixture:
    scope = {'os':os, 'core':fixture.core, 'teddy_download_safety':safety, 'teddy_storage':storage, 'shlex':shlex}
    exec(compile(guard_tree, 'teddy_entrypoint.py', 'exec'), scope)
    guard=scope['_fresh_output_collision_guard']
    local=Path(fixture.core.DOWNLOAD_DIR)/'sample.mp4'; local.write_bytes(b'existing')
    try: guard('sample.mp4')
    except safety.OutputCollision: pass
    else: raise AssertionError('local collision admitted')
    local.unlink()
    with mock.patch.object(storage, '_final_backend', return_value='ssh'), \
         mock.patch.object(storage, '_ssh_remote_path', return_value='/fixture/missav'), \
         mock.patch.object(storage, '_ssh_run'), \
         mock.patch.object(storage, '_ssh_remote_stat', return_value={'size':1}):
        try: guard('sample.mp4')
        except safety.OutputCollision: pass
        else: raise AssertionError('remote collision admitted')
    # Exercise the real _ssh_remote_stat parser; no SSH process is started.
    with mock.patch.object(storage, '_final_backend', return_value='ssh'), \
         mock.patch.object(storage, '_ssh_remote_path', return_value='/fixture/missav/file'):
        response = SimpleNamespace(stdout='__MISSING__')
        with mock.patch.object(storage, '_ssh_run', return_value=response):
            guard('sample.mp4')
        for failure in (storage.PublishError('ssh failed'), None):
            if failure is None:
                patched = mock.patch.object(storage, '_ssh_run', return_value=SimpleNamespace(stdout='__INVALID__'))
            else:
                patched = mock.patch.object(storage, '_ssh_run', side_effect=failure)
            with patched:
                try: guard('sample.mp4')
                except safety.DownloadSafetyError: pass
                else: raise AssertionError('uncertain SSH result admitted')
        with mock.patch.object(storage, '_ssh_run', return_value=SimpleNamespace(stdout='123 456')):
            try: guard('sample.mp4')
            except safety.OutputCollision: pass
            else: raise AssertionError('existing remote file admitted')
print('DLFR local and remote collision fixtures: PASS')
