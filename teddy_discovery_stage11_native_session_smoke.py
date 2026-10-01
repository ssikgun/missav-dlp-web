"""Execute the production native-session script with an in-memory SessionDB.

No SSH, native state.db, model, subtitle, or publication I/O is performed.
"""
import contextlib
import io
import os
import sys
from types import SimpleNamespace, ModuleType
from unittest.mock import patch

from teddy_discovery_stage11_deployment import (
    SSHRemoteHermesBridge, Stage11DeploymentTransportError,
)
from teddy_discovery_quality_review_session import (
    QUALITY_REVIEW_SESSION_SOURCE, ensure_fresh_review_execution_session,
)

SESSION = '12345678-1234-5678-1234-567812345678'
PROFILE = 'subtitle-translator'


class NativeDB:
    def __init__(self, *, existing=False, returned_id=SESSION, missing=False,
                 changes=None, messages=None):
        self.row = self.exact_row() if existing else None
        self.returned_id = returned_id
        self.missing = missing
        self.changes = changes or {}
        if existing:
            self.row.update(self.changes)
        self.messages = [] if messages is None else messages
        self.creations = []
        self.history_calls = []
        self.closes = 0

    @staticmethod
    def exact_row():
        return dict(id=SESSION, source=QUALITY_REVIEW_SESSION_SOURCE,
                    profile_name=PROFILE, parent_session_id=None)

    def get_session(self, session_id):
        assert session_id == SESSION
        return self.row

    def create_session(self, **kwargs):
        assert kwargs == dict(session_id=SESSION, source=QUALITY_REVIEW_SESSION_SOURCE,
                              profile_name=PROFILE)
        self.creations.append(kwargs)
        if not self.missing:
            self.row = dict(self.exact_row(), **self.changes)
        return self.returned_id

    def get_messages(self, session_id, *, include_inactive):
        assert session_id == SESSION and include_inactive is True
        self.history_calls.append(include_inactive)
        return self.messages

    def close(self):
        self.closes += 1


class InMemoryBridge(SSHRemoteHermesBridge):
    def __init__(self, db):
        super().__init__(SimpleNamespace(expected_profile_name=PROFILE))
        self.db = db

    def _python(self, script, *args, **kwargs):
        profiles = ModuleType('hermes_cli.profiles')
        profiles.get_active_profile_name = lambda: PROFILE
        state = ModuleType('hermes_state')
        state.SessionDB = lambda **_kwargs: self.db
        output = io.StringIO()
        with patch.dict(sys.modules, {'hermes_cli': ModuleType('hermes_cli'),
                                     'hermes_cli.profiles': profiles, 'hermes_state': state}), \
             patch.object(sys, 'argv', ['native-probe', *args]), \
             patch.dict(os.environ), contextlib.redirect_stdout(output):
            try:
                exec(compile(script, '<native-session-smoke>', 'exec'), {})
            except SystemExit as error:
                assert output.getvalue() == ''
                raise Stage11DeploymentTransportError('CT120 native command failed') from error
        return output.getvalue().encode()


def exercise(operation, *, expected_exit=None, creates=0, **kwargs):
    db = NativeDB(**kwargs)
    bridge = InMemoryBridge(db)
    try:
        result = bridge._native_session(operation, SESSION,
                                        source=QUALITY_REVIEW_SESSION_SOURCE,
                                        profile_name=PROFILE)
    except Stage11DeploymentTransportError as error:
        assert expected_exit is not None and error.__cause__.code == expected_exit
        assert str(error) == 'CT120 native command failed' and SESSION not in str(error)
    else:
        assert expected_exit is None and result == SESSION
        assert db.row == db.exact_row()
        if operation == 'fresh':
            assert db.history_calls == [True] and db.messages == []
    assert len(db.creations) == creates and db.closes == 1


def main():
    exercise('fresh', creates=1)
    exercise('fresh', existing=True, expected_exit=22)
    exercise('fresh', returned_id='wrong-id', creates=1, expected_exit=23)
    exercise('fresh', returned_id=None, creates=1, expected_exit=23)
    exercise('fresh', missing=True, creates=1, expected_exit=24)
    for field, value in (('id', 'wrong-id'), ('source', 'other'),
                         ('profile_name', 'other'), ('parent_session_id', 'parent')):
        exercise('fresh', changes={field: value}, creates=1, expected_exit=25)
        exercise('ensure', existing=True, changes={field: value}, expected_exit=25)
    for messages in ([{'private': 'history'}], (), {}):
        exercise('fresh', messages=messages, creates=1, expected_exit=26)
    exercise('ensure', creates=1)
    exercise('ensure', existing=True)
    db = NativeDB()
    proof = ensure_fresh_review_execution_session(
        InMemoryBridge(db), SESSION, expected_profile_name=PROFILE)
    assert proof.review_execution_session_id == SESSION and len(db.creations) == 1
    # Exercise the SSH failure surface without displaying private output.
    bridge = SSHRemoteHermesBridge(SimpleNamespace(), runner=lambda *a, **kw:
                                  SimpleNamespace(returncode=1, stdout=SESSION.encode(), stderr=b'private'))
    with patch.object(bridge, '_base', return_value=['ssh']):
        try:
            bridge._run('mock', capture=True)
        except Stage11DeploymentTransportError as error:
            assert str(error) == 'CT120 native command failed'
        else:
            raise AssertionError('failed native command accepted')
    print('NATIVE_FRESH_ENSURE_IDENTITY_HISTORY_PRIVACY_SMOKE=PASS')


if __name__ == '__main__':
    main()
