"""Offline smoke for deployment-owned Stage11 wiring.

All filesystem activity is confined to ``TemporaryDirectory``.  The remote
bridge, ASR review executor, and first-pass native runner are fakes, so this
smoke cannot send Hermes/Whisper requests or create a remote session.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
import uuid

import teddy_discovery_stage11_deployment as deployment
import teddy_discovery_stage11_controller_smoke as controller_fixture
import teddy_discovery_stage11_live_adapters_smoke as live_fixture
import teddy_discovery_subtitle_v2_pipeline_smoke as v2_fixture
import teddy_discovery_stateful_quality_review as review
from teddy_discovery_alignment_acceptance import AlignmentAcceptancePolicy
from teddy_discovery_asr_bounded_worker import BoundedTargetedASRTransport
from teddy_discovery_asr_source import ASRMediaSourceReader
from teddy_discovery_asr_source_quality import classify_asr_result_source_quality
from teddy_discovery_stateful_asr_quality_review import (
    asr_quality_review_request_sha256,
    serialize_asr_quality_review_result,
)
from teddy_discovery_stateful_quality_review_runner import (
    QUALITY_REVIEW_INPUT_FILENAME,
    QUALITY_REVIEW_RESULT_FILENAME,
    QUALITY_REVIEW_EXECUTION_RECEIPT_SCHEMA_VERSION,
)
from teddy_discovery_stateful_translator import (
    StatefulSubtitlePackage,
    _atomic_private_write,
    parse_stateful_package,
    serialize_stateful_result,
)
from teddy_discovery_subtitle_external import (
    ExternalSubtitleTransportError,
    SubtitleCatDetailPage,
    SubtitleCatProvider,
)
from teddy_discovery_subtitlecat_discovery import (
    SubtitleCatSearchCandidate,
    SubtitleCatSearchResult,
)
from teddy_discovery_quality_review_session import (
    ensure_fresh_review_execution_session,
)
from teddy_discovery_stage11_hermes_profile import (
    HermesExecutionSettings,
    STAGE11_HERMES_TIMEOUT_ENV,
    STAGE11_HERMES_TIMEOUT_ENV_NAMES,
)

_REAL_SUBPROCESS_RUN = subprocess.run
_REAL_SUBPROCESS_POPEN = subprocess.Popen


class _LocalRemotePythonRunner:
    """Execute only the bridge's stdlib remote scripts against local temp files."""

    def __init__(self):
        self.calls = []
        self.executables = []
        self.lose_next_start_response = False

    def __call__(self, argv, **kwargs):
        remote_command = argv[-1]
        parts = shlex.split(remote_command)
        if len(parts) < 3 or parts[1] != "-c":
            raise AssertionError("unexpected synthetic SSH command")
        self.calls.append(parts[3] if len(parts) > 3 else "probe")
        self.executables.append(parts[0])
        with patch.object(subprocess, "Popen", _REAL_SUBPROCESS_POPEN):
            completed = _REAL_SUBPROCESS_RUN(
                [sys.executable, *parts[1:]],
                input=kwargs.get("input"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=kwargs.get("timeout"),
            )
        if parts[3] == "start" and self.lose_next_start_response:
            self.lose_next_start_response = False
            raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"))
        return completed


def _remote_review_supervisor_smoke():
    """Exercise one normal and one short-timeout synthetic remote child."""
    with tempfile.TemporaryDirectory(prefix="stage11-review-supervisor-") as temp:
        root = Path(temp)
        remote_root = root / "remote"
        remote_root.mkdir(mode=0o700)
        settings = _synthetic_hermes_settings()
        fake_ssh = _LocalRemotePythonRunner()
        # The remote claim/manager starts, then the initiating SSH response is
        # lost. The bridge must recover the same execution by read-only status.
        fake_ssh.lose_next_start_response = True
        config = replace(_config(root), remote_task_root=str(remote_root))
        bridge = deployment.SSHRemoteHermesBridge(config, runner=fake_ssh)

        def run_case(*, session_id, child_code, expect_state, extra_args=()):
            task = remote_root / session_id
            task.mkdir(mode=0o700)
            request_bytes = b'{"synthetic":"review-request"}'
            request_sha = hashlib.sha256(request_bytes).hexdigest()
            input_path = task / QUALITY_REVIEW_INPUT_FILENAME
            fd = os.open(input_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(request_bytes)
            result_path = task / QUALITY_REVIEW_RESULT_FILENAME
            query = ("Read " + str(input_path) + " and write " + str(result_path))
            command = [
                sys.executable, "-c", child_code, str(result_path), *extra_args,
                "--profile", settings.profile_name,
                "--provider", settings.provider,
                "--model", settings.model,
                "--reasoning", settings.reasoning_effort,
                "--resume", session_id,
                "-q", query,
            ]
            completed = bridge.launch_quality_review(
                command,
                remote_task=str(task),
                timeout=deployment.QUALITY_REVIEW_TRANSPORT_TIMEOUT_SECONDS,
                execution_timeout=deployment.QUALITY_REVIEW_REMOTE_EXECUTION_TIMEOUT_SECONDS,
                timeout_env=dict(STAGE11_HERMES_TIMEOUT_ENV),
                review_execution_session_id=session_id,
                request_sha256=request_sha,
                hermes_execution_settings=settings.evidence(),
            )
            receipt = completed.execution_receipt
            assert receipt["state"] == expect_state, receipt
            after = bridge.read_quality_review_execution(
                remote_task=str(task),
                review_execution_session_id=session_id,
                request_sha256=request_sha,
                hermes_execution_settings=settings.evidence(),
            )
            assert after["state"] == expect_state
            assert after["receipt"] == receipt
            before_pid = receipt["child_pid"]
            # A second start call with this execution identity may only read
            # the existing claim/receipt; it must not launch another child.
            again = bridge.launch_quality_review(
                command,
                remote_task=str(task),
                timeout=deployment.QUALITY_REVIEW_TRANSPORT_TIMEOUT_SECONDS,
                execution_timeout=deployment.QUALITY_REVIEW_REMOTE_EXECUTION_TIMEOUT_SECONDS,
                timeout_env=dict(STAGE11_HERMES_TIMEOUT_ENV),
                review_execution_session_id=session_id,
                request_sha256=request_sha,
                hermes_execution_settings=settings.evidence(),
            )
            assert again.execution_receipt["child_pid"] == before_pid
            assert again.execution_receipt == receipt
            if expect_state == "COMPLETED":
                assert hashlib.sha256(completed.result_payload).hexdigest() == receipt["result_sha256"]
                assert result_path.stat().st_mode & 0o777 == 0o600
            else:
                assert not result_path.exists()
                assert type(receipt["exit_code"]) is int
                if expect_state == "TIMED_OUT":
                    assert receipt["timed_out"] and receipt["cleanup_confirmed"]
                elif expect_state == "CLEANUP_UNVERIFIED":
                    assert not receipt["timed_out"] and not receipt["cleanup_confirmed"]
                    assert receipt["child_pid"] is None
            return receipt

        normal_id = "d3514846-64a1-4438-9e9d-0e34e6d7bc31"
        normal_code = (
            "import os,sys; fd=os.open(sys.argv[1], os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600); "
            "os.write(fd,b'{\\\"synthetic\\\":true}'); os.fsync(fd); os.close(fd)"
        )
        normal = run_case(session_id=normal_id, child_code=normal_code,
                          expect_state="COMPLETED")
        assert fake_ssh.calls[:2] == ["preflight", "start"]
        assert all(
            executable == deployment.REMOTE_STAGE11_SUPERVISOR_PYTHON
            for action, executable in zip(fake_ssh.calls, fake_ssh.executables)
            if action in {"preflight", "start", "status"}
        )
        assert deployment.REMOTE_STAGE11_SUPERVISOR_PYTHON == "/usr/bin/python3"
        assert deployment.REMOTE_HERMES_PYTHON != deployment.REMOTE_STAGE11_SUPERVISOR_PYTHON

        sleeper = _REAL_SUBPROCESS_POPEN(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            timeout_id = "26365df8-1224-45bc-81cb-8d01a240d07c"
            timeout_code = (
                "import subprocess,sys,time; "
                "subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']); "
                "time.sleep(30)"
            )
            with patch.object(deployment, "_REMOTE_QUALITY_REVIEW_EXECUTION_SCRIPT",
                    deployment._REMOTE_QUALITY_REVIEW_EXECUTION_SCRIPT.replace(
                        "EXECUTION_LIMIT = 3600", "EXECUTION_LIMIT = 1"
                    ).replace("CLEANUP_GRACE = 30.0", "CLEANUP_GRACE = 0.2")), \
                 patch.object(deployment, "QUALITY_REVIEW_REMOTE_EXECUTION_TIMEOUT_SECONDS", 1), \
                 patch.object(deployment, "QUALITY_REVIEW_TRANSPORT_TIMEOUT_SECONDS", 8), \
                 patch.object(deployment, "QUALITY_REVIEW_STATUS_POLL_SECONDS", 0.02), \
                 patch("teddy_discovery_stateful_quality_review_runner.QUALITY_REVIEW_REMOTE_EXECUTION_TIMEOUT_SECONDS", 1):
                timed = run_case(session_id=timeout_id, child_code=timeout_code,
                                 expect_state="TIMED_OUT")
            assert sleeper.poll() is None

            identity_id = "4cf55c2c-a39a-4e70-8df2-4e3c330840b8"
            pid_path = root / "unidentified-child.pid"
            identity_code = (
                "import os,sys,time; "
                "open(sys.argv[2],'w').write(str(os.getpid())); time.sleep(30)"
            )
            wait_for_pidfile = (
                "child = None\n            deadline = time.monotonic() + 3\n"
                "            while not os.path.exists(" + repr(str(pid_path)) + ") and time.monotonic() < deadline:\n"
                "                time.sleep(0.01)\n            stop(26)"
            )
            fail_identity_script = deployment._REMOTE_QUALITY_REVIEW_EXECUTION_SCRIPT.replace(
                "child = process_identity(process.pid)",
                wait_for_pidfile,
            )
            with patch.object(deployment, "_REMOTE_QUALITY_REVIEW_EXECUTION_SCRIPT",
                              fail_identity_script):
                unidentified = run_case(
                    session_id=identity_id,
                    child_code=identity_code,
                    extra_args=(str(pid_path),),
                    expect_state="CLEANUP_UNVERIFIED",
                )
            child_pid = int(pid_path.read_text(encoding="ascii"))
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                pass
            else:
                raise AssertionError("unidentified owned child was not reaped")
        finally:
            sleeper.terminate()
            sleeper.wait(timeout=5)
        return (normal["cleanup_confirmed"] and timed["cleanup_confirmed"]
                and not unidentified["cleanup_confirmed"])


def _remote_review_pidfd_fail_closed_smoke():
    with tempfile.TemporaryDirectory(prefix="stage11-review-pidfd-") as temp:
        root = Path(temp)
        remote_root = root / "remote"
        remote_root.mkdir(mode=0o700)
        fake_ssh = _LocalRemotePythonRunner()
        bridge = deployment.SSHRemoteHermesBridge(
            replace(_config(root), remote_task_root=str(remote_root)),
            runner=fake_ssh,
        )
        unsupported_script = deployment._REMOTE_QUALITY_REVIEW_EXECUTION_SCRIPT.replace(
            "def pidfd_supported():\n",
            "def pidfd_supported():\n    return False\n",
            1,
        )
        session_id = "c5181944-bceb-4cf5-9c8b-a8d4ed73881a"
        with patch.object(
            deployment,
            "_REMOTE_QUALITY_REVIEW_EXECUTION_SCRIPT",
            unsupported_script,
        ):
            try:
                bridge._require_remote_supervisor_pidfd(
                    remote_task=str(remote_root / session_id),
                    session_id=session_id,
                    request_sha256="a" * 64,
                )
            except deployment.Stage11DeploymentValidationError as error:
                assert "pidfd_open/pidfd_send_signal" in str(error)
            else:
                raise AssertionError("unsupported supervisor pidfd was accepted")
        assert fake_ssh.calls == ["preflight"]
        assert fake_ssh.executables == [deployment.REMOTE_STAGE11_SUPERVISOR_PYTHON]
        return True


def _synthetic_hermes_settings():
    return HermesExecutionSettings(
        profile_name="subtitle-translator", provider="synthetic-provider",
        model="synthetic-model", reasoning_effort="high",
        hermes_version="synthetic-1", config_sha256="0" * 64,
        timeout_env_supported=STAGE11_HERMES_TIMEOUT_ENV_NAMES,
    )


class FakeRemoteBridge:
    """Deployment bridge double; it stores no state outside this process."""

    def __init__(self):
        self.tasks = set()
        self.files: dict[str, bytes] = {}
        self.session_rows = {}
        self.ensure_task_calls = []
        self.ensure_file_calls = []
        self.stateful_session_calls = []
        self.launch_calls = []
        self.review_payload_to_result = None

    def resolve_stage11_hermes_settings(self):
        return _synthetic_hermes_settings()

    def ensure_task(self, remote_task):
        self.ensure_task_calls.append(remote_task)
        self.tasks.add(remote_task)

    def ensure_file(self, remote_path, payload):
        self.ensure_file_calls.append((remote_path, payload))
        existing = self.files.get(remote_path)
        if existing is not None and existing != payload:
            raise deployment.Stage11DeploymentValidationError(
                "fake remote input conflict"
            )
        self.files.setdefault(remote_path, payload)

    def write_exclusive(self, remote_path, payload):
        if remote_path in self.files:
            raise deployment.Stage11DeploymentTransportError(
                "fake remote destination exists"
            )
        self.files[remote_path] = payload

    def read_regular(self, remote_path, *, max_bytes):
        if remote_path not in self.files:
            raise deployment.Stage11DeploymentTransportError(
                "fake remote file absent"
            )
        payload = self.files[remote_path]
        if not 0 < len(payload) <= max_bytes:
            raise deployment.Stage11DeploymentTransportError(
                "fake remote file exceeds bound"
            )
        return payload

    def ensure_stateful_session(self, session_id):
        self.stateful_session_calls.append(session_id)
        self.session_rows.setdefault(
            session_id,
            {
                "id": session_id,
                "source": "stage11-subtitle-translator",
                "profile_name": "subtitle-translator",
                "parent_session_id": None,
            },
        )

    def get_session(self, session_id):
        return self.session_rows.get(session_id)

    def create_session(self, *, session_id, source, profile_name):
        if session_id in self.session_rows:
            raise deployment.Stage11DeploymentTransportError(
                "fake fresh session already exists"
            )
        self.session_rows[session_id] = {
            "id": session_id,
            "source": source,
            "profile_name": profile_name,
            "parent_session_id": None,
        }
        return session_id

    def get_messages(self, session_id, *, include_inactive=False):
        del include_inactive
        if session_id not in self.session_rows:
            raise deployment.Stage11DeploymentTransportError(
                "fake session absent"
            )
        return []

    def launch_quality_review(
        self, command, *, remote_task, timeout, execution_timeout,
        timeout_env, review_execution_session_id, request_sha256,
        hermes_execution_settings,
    ):
        self.launch_calls.append((
            command, remote_task, timeout, execution_timeout, timeout_env,
            review_execution_session_id, request_sha256,
            hermes_execution_settings,
        ))
        if self.review_payload_to_result is None:
            raise AssertionError("fake Hybrid result callback was not installed")
        input_path = remote_task + "/" + QUALITY_REVIEW_INPUT_FILENAME
        output_path = remote_task + "/" + QUALITY_REVIEW_RESULT_FILENAME
        result_payload = self.review_payload_to_result(
            self.files[input_path],
            review_session=review_execution_session_id,
        )
        self.files[output_path] = result_payload
        command_sha = hashlib.sha256(
            json.dumps(command, ensure_ascii=True, sort_keys=True,
                       separators=(",", ":")).encode("ascii")
        ).hexdigest()
        receipt = {
            "schema_version": QUALITY_REVIEW_EXECUTION_RECEIPT_SCHEMA_VERSION,
            "state": "COMPLETED",
            "review_execution_session_id": review_execution_session_id,
            "request_sha256": request_sha256,
            "hermes_execution_settings": hermes_execution_settings,
            "command_sha256": command_sha,
            "timeout_seconds": execution_timeout,
            "timed_out": False, "termination_reason": "NORMAL_EXIT",
            "exit_code": 0, "elapsed_seconds": 0.25,
            "cleanup_confirmed": True,
            "supervisor_pid": 101, "supervisor_start_ticks": 1001,
            "child_pid": 102, "child_start_ticks": 1002,
            "child_process_group_id": 102,
            "result_sha256": hashlib.sha256(result_payload).hexdigest(),
        }
        return SimpleNamespace(returncode=0, execution_receipt=receipt,
                               result_payload=result_payload)


class Discovery:
    def __init__(self, *, candidate: bool):
        self.candidate = candidate

    def discover(self, *, dvd_id):
        candidates = ()
        if self.candidate:
            candidates = (
                SubtitleCatSearchCandidate(
                    "https://subtitlecat.com/subs/1/generic.html"
                ),
            )
        return SubtitleCatSearchResult(dvd_id, candidates)


def _config(root: Path, *, timeout=1200):
    return deployment.Stage11DeploymentConfig(
        nas_host="192.0.2.10",
        nas_user="nas-user",
        nas_key=str(root / "nas-key"),
        nas_known_hosts=str(root / "nas-known-hosts"),
        nas_library_root="/volume1/video/video2/JAV",
        asr_base_url="http://192.0.2.20:8091",
        request_timeout_seconds=timeout,
        remote_host="192.0.2.30",
        remote_user="hermes-user",
        ssh_key=str(root / "hermes-key"),
        known_hosts=str(root / "hermes-known-hosts"),
        remote_task_root="/srv/hermes/stage11",
    )


def _holding(asr_result):
    return controller_fixture._holding(asr_result)


def _provider(asr_result):
    payload = v2_fixture.srt_bytes(
        tuple((segment.start_ms, segment.end_ms, segment.text)
              for segment in asr_result.segments)
    )
    return SubtitleCatProvider(
        fetch_detail=lambda url: SubtitleCatDetailPage(
            final_url=url,
            html='<html><a href="test-ja.srt">Japanese</a></html>',
        ),
        payload_fetcher=lambda candidate: payload,
    )


def _asr_executor(runtime, fresh_db):
    def execute(request, payload, digest, remote_task, timeout):
        del payload, digest, remote_task, timeout
        return serialize_asr_quality_review_result(
            replace(
                runtime._review_result(request, asr_quality_review_request_sha256(request)),
                review_execution_session_id=fresh_db.calls[-1][0],
            ),
            request,
        )

    return execute


def _native_first_pass(runtime):
    def run(args):
        package = parse_stateful_package(Path(args.package).read_bytes())
        route = (
            "HYBRID"
            if package.generation_key.startswith("stage11-hybrid-")
            else "ASR_ONLY"
        )
        result = runtime.first_pass(
            package,
            route=route,
            staging_root=Path(args.task_directory).parent,
        )
        _atomic_private_write(
            Path(args.final_result),
            serialize_stateful_result(result),
        )
        return 0

    return run


def _install_fake_hybrid_result(bridge, deps, runtime):
    def result_from_payload(payload, *, review_session):
        request = review._parse(
            payload,
            review.QualityReviewRequest,
            review.QualityReviewInputCue,
        )
        originals = deps.originals_provider(request)
        request = review.parse_review_request(payload, **originals)
        result = replace(
            runtime._review_result(request, review.review_request_sha256(request)),
            review_execution_session_id=review_session,
        )
        return review.serialize_review_result(result, request)

    bridge.review_payload_to_result = result_from_payload


class FakeFreshReviewDB:
    def __init__(self):
        self.rows = {}
        self.messages = {}
        self.calls = []

    def get_session(self, session_id):
        return self.rows.get(session_id)

    def create_session(self, *, session_id, source, profile_name):
        self.calls.append((session_id, source, profile_name))
        self.rows[session_id] = {
            "id": session_id,
            "source": source,
            "profile_name": profile_name,
            "parent_session_id": None,
        }
        return session_id

    def get_messages(self, session_id, *, include_inactive=False):
        del include_inactive
        return list(self.messages.get(session_id, ()))


def _build_deps_with_asr_fake(root, *, candidate, bridge=None, baseline=None, runtime=None):
    baseline = v2_fixture.asr_result() if baseline is None else baseline
    runtime = (
        controller_fixture.FakeRuntime(
            baseline,
            stage_first_pass_artifacts=False,
        )
        if runtime is None
        else runtime
    )
    bridge = FakeRemoteBridge() if bridge is None else bridge
    fresh_db = FakeFreshReviewDB()
    provider = _provider(baseline)

    def prepare_review_session(session_id):
        ensure_fresh_review_execution_session(
            fresh_db,
            session_id,
            expected_profile_name="subtitle-translator",
        )

    deps = deployment.build_stage11_deployment_dependencies(
        _config(root),
        acceptance_policy=AlignmentAcceptancePolicy(
            3, 3, 0.8, 100.0, 0, 0.9, 1.1
        ),
        residual_threshold_ms=100,
        holding_resolver=lambda title: _holding(baseline),
        source_provider=live_fixture.Source(root, baseline.source_snapshot),
        whisper=live_fixture.Transport(baseline.segments),
        targeted_transport=live_fixture.Transport(baseline.segments),
        discovery=Discovery(candidate=candidate),
        provider=provider,
        remote_bridge=bridge,
        native_first_pass_run=_native_first_pass(runtime),
        asr_review_options={
            "executor": _asr_executor(runtime, fresh_db),
            "fresh_session_preparer": prepare_review_session,
        },
    )
    return deps, runtime, bridge, fresh_db


def _controller_run(deps, root, baseline):
    root.mkdir(mode=0o700)
    artifact_root = root / "artifacts"
    staging_root = root / "staging"
    artifact_root.mkdir(mode=0o700)
    staging_root.mkdir(mode=0o700)
    controller_fixture._prepopulate_baseline(artifact_root, baseline)
    return controller_fixture.controller.run_one_title_stage11(
        controller_fixture.TITLE,
        artifact_root=artifact_root,
        stateful_staging_root=staging_root,
        claim_token=deployment.STAGE11_STANDALONE_CANARY_CLAIM_TOKEN,
        **deps.controller_kwargs(),
    )


def detail_redirect_smoke(check):
    from email.message import Message
    from io import BytesIO
    from urllib.error import HTTPError
    from teddy_discovery_subtitle_external import find_subtitlecat_original_japanese_srt_url
    import teddy_discovery_subtitlecat_discovery as discovery

    original = "https://subtitlecat.com/subs/1/generic.html?q=1"
    canonical = "https://www.subtitlecat.com/subs/1/generic.html?q=1"
    body = b'<html><a href="generic-ja.srt">Japanese</a></html>'

    class Response:
        def __init__(self, url, status=200, payload=body, location=None):
            self.url, self.status, self.payload = url, status, payload
            self.reads = []
            self.headers = Message()
            if location is not None:
                self.headers['Location'] = location
        def geturl(self): return self.url
        def getcode(self): return self.status
        def read(self, limit):
            self.reads.append(limit)
            return self.payload[:limit]
        def __enter__(self): return self
        def __exit__(self, *args): pass

    def run(responses, url=original):
        calls = []
        def opened(request, **kwargs):
            calls.append(request.full_url)
            response = responses[len(calls)-1]
            if isinstance(response, Exception): raise response
            return response
        with patch.object(deployment.urllib_request, 'build_opener',
                          return_value=SimpleNamespace(open=opened)):
            page = deployment._default_detail_fetcher(1)(url)
        return page, calls

    direct = Response(original)
    page, calls = run([direct])
    check('DETAIL_DIRECT_200_EXACT', page.final_url == original and calls == [original])
    first, final = Response(original, 301, location=canonical), Response(canonical)
    page, calls = run([first, final])
    check('DETAIL_CANONICAL_ONE_HOP_FINAL_URL', page.final_url == canonical
          and calls == [original, canonical] and not first.reads)
    check('DETAIL_RELATIVE_JA_CANONICAL_BASE',
          find_subtitlecat_original_japanese_srt_url(page.html, page.final_url)
          == 'https://www.subtitlecat.com/subs/1/generic-ja.srt')
    headers = Message(); headers['Location'] = canonical
    redirect_error = HTTPError(original, 301, 'Moved', headers, BytesIO(b'ignored'))
    page, calls = run([redirect_error, Response(canonical)])
    check('DETAIL_URLLIB_HTTPERROR_301', page.final_url == canonical)

    cases = {
        'CROSS_SITE': ('https://example.org/subs/1/generic.html?q=1', original),
        'WWW_SOURCE': ('https://example.org/subs/1/generic.html?q=1', canonical),
        'PATH': (canonical.replace('generic.html', 'other.html'), original),
        'QUERY': (canonical.replace('q=1', 'q=2'), original),
        'DOWNGRADE': (canonical.replace('https:', 'http:'), original),
        'CREDENTIALS': (canonical.replace('www.', 'user@www.'), original),
        'FRAGMENT': (canonical + '#part', original),
        'EMPTY_FRAGMENT': (canonical + '#', original),
        'PORT': (canonical.replace('.com/', '.com:444/'), original),
        'MISSING_LOCATION': (None, original),
        'SOURCE_CREDENTIALS': (canonical, original.replace('subtitlecat.com', 'user@subtitlecat.com')),
        'SOURCE_FRAGMENT': (canonical, original + '#part'),
        'SOURCE_HTTP': (canonical, original.replace('https:', 'http:')),
    }
    for name, (target, source) in cases.items():
        first = Response(source, 301, location=target)
        try: run([first], source)
        except ExternalSubtitleTransportError: pass
        else: raise AssertionError(name)
        check('DETAIL_REJECT_' + name, not first.reads)
    for status in (302, 303, 307, 308):
        first = Response(original, status, location=canonical)
        try: run([first])
        except ExternalSubtitleTransportError: pass
        else: raise AssertionError(status)
        check('DETAIL_REJECT_STATUS_' + str(status), not first.reads)
    for name, final in (
        ('SECOND_REDIRECT', Response(canonical, 301, location=canonical)),
        ('NON_2XX', Response(canonical, 404)),
        ('FINAL_URL_DETACHED', Response(original)),
        ('OVERSIZED', Response(canonical, payload=b'x'*(deployment.MAX_SUBTITLECAT_DETAIL_HTML_BYTES+1))),
    ):
        first = Response(original, 301, location=canonical)
        try: run([first, final])
        except ExternalSubtitleTransportError: pass
        else: raise AssertionError(name)
        check('DETAIL_REJECT_' + name, not first.reads)
    # Generic transports still reject redirects; the detail handler never follows.
    check('DETAIL_AUTOFOLLOW_DISABLED', deployment._DetailNoRedirectHandler().redirect_request(
        None, None, 301, '', Message(), canonical) is None)
    for name, handler, error_type in (
        ('PAYLOAD', deployment._NoRedirectHandler(), ExternalSubtitleTransportError),
        ('SEARCH', discovery._NoRedirectHandler(), discovery.SubtitleCatSearchTransportError),
    ):
        try: handler.redirect_request(None, None, 301, '', Message(), canonical)
        except error_type: pass
        else: raise AssertionError(name)
        check(name + '_REDIRECT_POLICY_UNCHANGED', True)
    with patch.object(deployment.urllib_request, 'build_opener',
                      return_value=SimpleNamespace(open=lambda *a, **k: Response(canonical))):
        try: deployment._default_payload_fetcher(1)(SimpleNamespace(external_source_id=original))
        except ExternalSubtitleTransportError: pass
        else: raise AssertionError('payload response URL')
    check('PAYLOAD_FINAL_URL_EXACT_REQUIRED', True)

    # A valid original-JA href can be an IRI. Send its UTF-8 URI form while
    # retaining the exact Unicode source identity in the accepted payload.
    raw_source_url = 'https://www.subtitlecat.com/subs/1/日本語-ja.srt'
    encoded_source_url = (
        'https://www.subtitlecat.com/subs/1/'
        '%E6%97%A5%E6%9C%AC%E8%AA%9E-ja.srt'
    )
    detail_url = 'https://www.subtitlecat.com/subs/1/generic.html'
    srt_bytes = '1\n00:00:00,000 --> 00:00:00,100\n日本語\n'.encode('utf-8')
    sent_urls = []
    provider = deployment.build_subtitlecat_provider(
        fetch_detail=lambda _url: SubtitleCatDetailPage(
            final_url=detail_url,
            html='<html><a href="日本語-ja.srt">Japanese</a></html>',
        ),
        timeout=1,
    )
    def open_payload(request, **_kwargs):
        sent_urls.append(request.full_url)
        return Response(request.full_url, payload=srt_bytes)
    with patch.object(deployment.urllib_request, 'build_opener',
                      return_value=SimpleNamespace(open=open_payload)):
        payload = provider.fetch_original_japanese_payload(
            dvd_id='GEN-123', detail_url=detail_url,
        )
    check('PAYLOAD_UNICODE_PATH_IS_UTF8_PERCENT_ENCODED',
          sent_urls == [encoded_source_url])
    check('PAYLOAD_UNICODE_SOURCE_ID_AND_SRT_VALIDATION_PRESERVED',
          payload.source_url == raw_source_url
          and payload.candidate.external_source_id == raw_source_url
          and payload.payload == srt_bytes
          and len(payload.parse().cues) == 1)

def main():
    passed = 0

    def check(label, value):
        nonlocal passed
        if not value:
            raise AssertionError(label)
        passed += 1
        print("PASS=" + label)

    check("REMOTE_REVIEW_SUPERVISOR_NORMAL_AND_TIMEOUT_CLEANUP",
          _remote_review_supervisor_smoke())
    check("REMOTE_REVIEW_PIDFD_PREFLIGHT_FAIL_CLOSED",
          _remote_review_pidfd_fail_closed_smoke())

    detail_redirect_smoke(check)

    with tempfile.TemporaryDirectory(prefix="stage11-deployment-smoke-") as raw:
        root = Path(raw)
        check(
            "CONFIG_TIMEOUT_1200_EXPLICIT",
            _config(root).request_timeout_seconds == 1200,
        )
        try:
            deployment.Stage11DeploymentConfig(
                nas_host="host",
                nas_user="user",
                nas_key="relative-key",
                nas_known_hosts="/known",
                nas_library_root="/library",
                asr_base_url="http://asr",
                request_timeout_seconds=0,
                remote_host="remote",
                remote_user="user",
                ssh_key="/key",
                known_hosts="/hosts",
                remote_task_root="/remote/root",
            )
        except deployment.Stage11DeploymentValidationError:
            check("CONFIG_INVALID_TIMEOUT_FAIL_CLOSED", True)
        else:
            check("CONFIG_INVALID_TIMEOUT_FAIL_CLOSED", False)

        bridge = FakeRemoteBridge()
        deps, runtime, bridge, fresh_db = _build_deps_with_asr_fake(
            root,
            candidate=False,
            bridge=bridge,
        )
        session = str(uuid.uuid4())
        check(
            "REMOTE_TASK_DETERMINISTIC",
            deps.remote_task_for_session(session)
            == "/srv/hermes/stage11/" + session,
        )
        try:
            deps.remote_task_for_session("../../escape")
        except deployment.Stage11DeploymentValidationError:
            check("REMOTE_TASK_TRAVERSAL_REJECTED", True)
        else:
            check("REMOTE_TASK_TRAVERSAL_REJECTED", False)

        # Exercise prepare_remote through the actual live adapter.  A package
        # from the canonical stateful smoke is used only as an in-memory fake.
        from teddy_discovery_hermes_v2 import HermesV2CueInput

        package = StatefulSubtitlePackage(
            schema_version=1,
            dvd_id="GENERIC-SMOKE",
            generation_key="generic-deployment-smoke",
            claim_token=1,
            cues=(
                HermesV2CueInput(
                    cue_id="ja-000000",
                    external_ja="テスト",
                    stt_ja=None,
                    en=None,
                    before_context=(),
                    after_context=(),
                ),
            ),
        )
        from teddy_discovery_stateful_translator import (
            stateful_staging_paths,
            write_stateful_input,
        )

        local_task = root / "local-first-pass-task"
        local_task.mkdir(mode=0o700)
        write_stateful_input(local_task, package)
        paths = stateful_staging_paths(local_task)
        prepared_remote = deps.prepare_remote(package, paths, route="ASR_ONLY")
        check(
            "PREPARE_REMOTE_FAKE_SSH_PATH",
            prepared_remote == deps.remote_task_for_session(
                __import__(
                    "teddy_discovery_stateful_translator",
                    fromlist=["stateful_session_id_for_package"],
                ).stateful_session_id_for_package(package)
            )
            and bridge.ensure_task_calls
            and bridge.stateful_session_calls,
        )
        check(
            "FIRST_PASS_NATIVE_RUN_NAMESPACE",
            callable(deps.live.first_pass_runner),
        )

        # Baseline composition and targeted source binding use fake media and
        # fake transport objects, not the configured live endpoints.
        source = live_fixture.Source(root, v2_fixture.asr_result().source_snapshot)
        whisper = live_fixture.Transport(v2_fixture.asr_result().segments)
        target_deps = deployment.build_stage11_deployment_dependencies(
            _config(root),
            acceptance_policy=AlignmentAcceptancePolicy(
                3, 3, 0.8, 100.0, 0, 0.9, 1.1
            ),
            residual_threshold_ms=100,
            holding_resolver=lambda title: _holding(v2_fixture.asr_result()),
            source_provider=source,
            whisper=whisper,
            targeted_transport=whisper,
            discovery=Discovery(candidate=False),
            provider=_provider(v2_fixture.asr_result()),
            remote_bridge=FakeRemoteBridge(),
            native_first_pass_run=lambda args: 1,
            audio_chunk_iterator=live_fixture.audio,
            asr_review_options={
                "executor": _asr_executor(runtime, fresh_db),
                "fresh_session_preparer": lambda sid: None,
            },
        )
        baseline_result = target_deps.live.baseline_transcriber(
            v2_fixture.holding()
        )
        check(
            "BASELINE_ASR_COMPOSITION",
            baseline_result.segments == v2_fixture.asr_result().segments
            and baseline_result.source_snapshot == v2_fixture.asr_result().source_snapshot
            and whisper.baseline_calls > 0,
        )
        required = controller_fixture._require_asr()
        target_execution = target_deps.live.targeted_runner(
            required,
            classify_asr_result_source_quality(required),
        )
        check(
            "TARGETED_SOURCE_SNAPSHOT_BINDING",
            target_execution.source_count > 0
            and target_execution.window_count > 0,
        )

        provider = deployment.build_subtitlecat_provider(
            fetch_detail=lambda url: SubtitleCatDetailPage(
                final_url=url,
                html='<html><a href="generic-ja.srt">Japanese</a></html>',
            ),
            payload_fetcher=lambda candidate: (
                "1\n00:00:00,000 --> 00:00:00,100\n日本語\n".encode("utf-8")
            ),
        )
        payload = provider.fetch_original_japanese_payload(
            dvd_id=v2_fixture.DVD_ID,
            detail_url="https://subtitlecat.com/generic.html",
        )
        check("SUBTITLECAT_PROVIDER_COMPOSITION", payload.parse().cues)

        default_asr = deployment.build_stage11_deployment_dependencies(
            _config(root),
            acceptance_policy=AlignmentAcceptancePolicy(
                3, 3, 0.8, 100.0, 0, 0.9, 1.1
            ),
            residual_threshold_ms=100,
            holding_resolver=lambda title: _holding(v2_fixture.asr_result()),
            source_provider=source,
            remote_bridge=FakeRemoteBridge(),
            native_first_pass_run=lambda args: 1,
            asr_review_options={
                "executor": _asr_executor(runtime, fresh_db),
                "fresh_session_preparer": lambda sid: None,
            },
        )
        check(
            "VM122_REQUEST_TIMEOUT_RETAINS_900S_CAP",
            isinstance(default_asr.whisper, BoundedTargetedASRTransport)
            and default_asr.whisper.request_timeout_seconds == 900,
        )
        production_source_deps = deployment.build_stage11_deployment_dependencies(
            _config(root),
            acceptance_policy=AlignmentAcceptancePolicy(
                3, 3, 0.8, 100.0, 0, 0.9, 1.1
            ),
            residual_threshold_ms=100,
            holding_resolver=lambda title: _holding(v2_fixture.asr_result()),
            remote_bridge=FakeRemoteBridge(),
            native_first_pass_run=lambda args: 1,
            asr_review_options={
                "executor": _asr_executor(runtime, fresh_db),
                "fresh_session_preparer": lambda sid: None,
            },
        )
        check(
            "PRODUCTION_ASR_SOURCE_USES_DISK_TEMP_POLICY",
            isinstance(production_source_deps.source_provider, ASRMediaSourceReader)
            and production_source_deps.source_provider.temp_root
            == "/var/tmp/teddy-stage11-asr-production"
            and production_source_deps.source_provider.require_disk_backed
            and production_source_deps.source_provider.reserve_bytes
            == 4 * 1024**3,
        )

        # ASR-only controller + deployment + live adapter flow.
        asr_deps, asr_runtime, asr_bridge, asr_fresh_db = _build_deps_with_asr_fake(
            root,
            candidate=False,
        )
        asr_result = v2_fixture.asr_result()
        completed_asr = _controller_run(asr_deps, root / "asr-e2e", asr_result)
        check(
            "FAKE_E2E_ASR_ONLY_CLEAN_REPORT",
            completed_asr.route == "ASR_ONLY"
            and completed_asr.clean_path.is_file()
            and completed_asr.report_path.is_file()
            and not asr_bridge.launch_calls,
        )
        asr_diagnostics = list((root / "asr-e2e" / "artifacts" /
            controller_fixture.TITLE).glob("external-ja-diagnostic-*.json"))
        check(
            "ASR_ONLY_EXTERNAL_DIAGNOSTIC_REACHES_DEPLOYMENT_WRAPPER",
            len(asr_diagnostics) == 1
            and json.loads(asr_diagnostics[0].read_bytes())["reason_code"]
            == "SEARCH_NO_CANDIDATES",
        )
        check(
            "ASR_REVIEW_FRESH_SESSION_WIRING",
            asr_runtime.first_pass_calls == 1
            and len(asr_fresh_db.calls) == 1,
        )

        # Hybrid controller + deployment + default deployment launcher.  The
        # fake bridge produces a validator-compatible result from exact input.
        hybrid_root = root / "hybrid-e2e"
        hybrid_deps, hybrid_runtime, hybrid_bridge, _hybrid_fresh_db = _build_deps_with_asr_fake(
            hybrid_root,
            candidate=True,
        )
        _install_fake_hybrid_result(hybrid_bridge, hybrid_deps, hybrid_runtime)
        completed_hybrid = _controller_run(
            hybrid_deps,
            hybrid_root,
            v2_fixture.asr_result(),
        )
        check(
            "FAKE_E2E_HYBRID_CLEAN_REPORT",
            completed_hybrid.route == "HYBRID"
            and completed_hybrid.clean_path.is_file()
            and completed_hybrid.report_path.is_file()
            and len(hybrid_bridge.launch_calls) == 1,
        )
        hybrid_diagnostics = list((hybrid_root / "artifacts" /
            controller_fixture.TITLE).glob("external-ja-diagnostic-*.json"))
        check(
            "HYBRID_EXTERNAL_DIAGNOSTIC_REACHES_DEPLOYMENT_WRAPPER",
            len(hybrid_diagnostics) == 1
            and json.loads(hybrid_diagnostics[0].read_bytes())["reason_code"]
            == "HYBRID_ACCEPTED",
        )
        check(
            "HYBRID_FRESH_SESSION_AND_ORIGINALS",
            hybrid_bridge.session_rows
            and hybrid_bridge.launch_calls[0][1].startswith(
                "/srv/hermes/stage11/"
            )
            and hybrid_bridge.launch_calls[0][4]
            == dict(STAGE11_HERMES_TIMEOUT_ENV)
            and hybrid_bridge.launch_calls[0][2]
            == deployment.QUALITY_REVIEW_TRANSPORT_TIMEOUT_SECONDS
            and hybrid_bridge.launch_calls[0][3]
            == deployment.QUALITY_REVIEW_REMOTE_EXECUTION_TIMEOUT_SECONDS
            and hybrid_bridge.launch_calls[0][5]
            == hybrid_bridge.launch_calls[0][0][hybrid_bridge.launch_calls[0][0].index("--resume") + 1]
            and any(
                path.endswith("/stage11-quality-review-input.json")
                for path in hybrid_bridge.files
            ),
        )

        # An unexpected external exception is deliberately not converted to
        # ASR-only by this deployment layer.
        failing = deployment.build_stage11_deployment_dependencies(
            _config(root),
            acceptance_policy=AlignmentAcceptancePolicy(
                3, 3, 0.8, 100.0, 0, 0.9, 1.1
            ),
            residual_threshold_ms=100,
            holding_resolver=lambda title: _holding(v2_fixture.asr_result()),
            source_provider=source,
            whisper=whisper,
            targeted_transport=whisper,
            discovery=SimpleNamespace(
                discover=lambda **kwargs: (_ for _ in ()).throw(
                    RuntimeError("unexpected programmer error")
                )
            ),
            provider=_provider(v2_fixture.asr_result()),
            remote_bridge=FakeRemoteBridge(),
            native_first_pass_run=lambda args: 1,
            asr_review_options={
                "executor": _asr_executor(runtime, fresh_db),
                "fresh_session_preparer": lambda sid: None,
            },
        )
        try:
            failing.live.external_ja_attempt(
                v2_fixture.holding(),
                v2_fixture.asr_result(),
            )
        except RuntimeError:
            check("UNEXPECTED_EXTERNAL_EXCEPTION_FAIL_CLOSED", True)
        else:
            check("UNEXPECTED_EXTERNAL_EXCEPTION_FAIL_CLOSED", False)

        typed_failure = ExternalSubtitleTransportError("typed transport failure")
        typed = deployment.build_stage11_deployment_dependencies(
            _config(root),
            acceptance_policy=AlignmentAcceptancePolicy(
                3, 3, 0.8, 100.0, 0, 0.9, 1.1
            ),
            residual_threshold_ms=100,
            holding_resolver=lambda title: _holding(v2_fixture.asr_result()),
            source_provider=source,
            whisper=whisper,
            targeted_transport=whisper,
            discovery=SimpleNamespace(
                discover=lambda **kwargs: (_ for _ in ()).throw(typed_failure)
            ),
            provider=_provider(v2_fixture.asr_result()),
            remote_bridge=FakeRemoteBridge(),
            native_first_pass_run=lambda args: 1,
            asr_review_options={
                "executor": _asr_executor(runtime, fresh_db),
                "fresh_session_preparer": lambda sid: None,
            },
        )
        try:
            typed.live.external_ja_attempt(
                v2_fixture.holding(),
                v2_fixture.asr_result(),
            )
        except ExternalSubtitleTransportError as error:
            check("TYPED_EXTERNAL_ERROR_PROPAGATES", error is typed_failure)
        else:
            check("TYPED_EXTERNAL_ERROR_PROPAGATES", False)

        check(
            "NO_PRODUCTION_NETWORK_OR_PROCESS_COUNTERS",
            not asr_bridge.launch_calls,
        )

    print("DEPLOYMENT_SMOKE_PASS_COUNT=" + str(passed))
    print("DEPLOYMENT_SMOKE_FAIL_COUNT=0")
    print("STAGE11_DEPLOYMENT_SMOKE_PASS")


if __name__ == "__main__":
    with patch(
        "subprocess.run",
        side_effect=AssertionError("actual subprocess forbidden"),
    ), patch(
        "subprocess.Popen",
        side_effect=AssertionError("actual process forbidden"),
    ), patch(
        "socket.socket",
        side_effect=AssertionError("actual network forbidden"),
    ):
        main()
