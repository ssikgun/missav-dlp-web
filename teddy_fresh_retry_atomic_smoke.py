"""Offline checks of the real fresh-task persistence helpers without starting app."""
import ast
import json
import os
from pathlib import Path
import queue
import stat
import tempfile
import threading
import uuid
from unittest import mock

source = Path('downloader_runtime_overlay/app.py').read_text(encoding='utf-8')
functions = {'_retry_state_read', '_retry_state_identity', '_retry_state_matches',
             '_retry_state_stage', '_retry_state_fsync_directory', '_retry_state_restore',
             '_retry_queue_put', 'persist_retry_state_and_enqueue', 'persist_fresh_task_and_enqueue'}
tree = ast.parse(source)
module = ast.Module(body=[x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name in functions], type_ignores=[])
ns = dict(os=os, stat=stat, json=json, queue=queue, uuid=uuid, threading=threading, STARTUP_HEALTH_ONLY=False)
exec(compile(module, 'app.py', 'exec'), ns)
with tempfile.TemporaryDirectory(prefix='dlfr-fixture-') as tmp:
    path = os.path.join(tmp, '.tasks.json')
    original = {'original': {'status': '에러: fixture', 'engine': 'custom-hls'}}
    for failure in ('stage', 'queue', 'queue_partial', 'none'):
        ns.update(TASKS_FILE=path, tasks=json.loads(json.dumps(original)), _tasks_lock=threading.Lock(),
                  queue_admission_lock=threading.RLock(), download_queue=queue.Queue())
        Path(path).write_text(json.dumps(original), encoding='utf-8')
        before = Path(path).read_bytes()
        target = '_retry_state_stage' if failure == 'stage' else '_retry_queue_put'
        if failure != 'none':
            try:
                if failure == 'queue_partial':
                    q = ns['download_queue']
                    original_put = q._put
                    def partial_put(value):
                        original_put(value)
                        raise OSError('synthetic partial queue failure')
                    with mock.patch.object(q, '_put', side_effect=partial_put):
                        ns['persist_fresh_task_and_enqueue']('fresh', {'status': '대기 중'})
                else:
                    with mock.patch.dict(ns, {target: mock.Mock(side_effect=OSError('synthetic failure'))}):
                        ns['persist_fresh_task_and_enqueue']('fresh', {'status': '대기 중'})
            except RuntimeError:
                pass
            else:
                raise AssertionError('failure not propagated')
            assert ns['tasks'] == original and Path(path).read_bytes() == before
            assert ns['download_queue'].empty()
        else:
            ns['persist_fresh_task_and_enqueue']('fresh', {'status': '대기 중'})
            assert ns['tasks']['original'] == original['original']
            assert json.loads(Path(path).read_text()) == ns['tasks']
            assert ns['download_queue'].get_nowait() == 'fresh'
print('DLFR fresh task persistence fixture: PASS')
