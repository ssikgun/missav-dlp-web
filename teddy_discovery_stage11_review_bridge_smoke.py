"""Offline receipt, failure-classification, and recovery-eligibility checks."""

from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
import uuid

import teddy_discovery_stage11_deployment as deployment
import teddy_discovery_stateful_quality_review as review
from teddy_discovery_stateful_hybrid import prepare_stateful_hybrid
from teddy_discovery_stateful_hybrid_smoke import semantic_result
from teddy_discovery_subtitle_v2_pipeline_smoke import accepted_hybrid_route
from teddy_discovery_subtitle_source_quality import classify_source_document


SESSION = "12345678-1234-5678-1234-567812345678"
COMMAND = ["/home/teddy/.local/bin/hermes", "--resume", SESSION]


def fixture():
    preparation = prepare_stateful_hybrid(
        accepted_hybrid_route(), generation_key="p2g-review-receipt", claim_token=17
    )
    package = preparation.package
    first_pass = semantic_result(package)
    document = preparation.route_decision.alignment_application.bundle.external_ja_document
    originals = dict(
        preparation=preparation,
        package=package,
        result=first_pass,
        source_quality=classify_source_document(document),
        raw_asr_context={package.cues[0].cue_id: ("reference evidence",)},
    )
    request = review.build_review_request(**originals)
    actions = (
        ("KEEP", "MEANINGFUL_REACTION"),
        ("REPAIR", "SEMANTIC_REPAIR"),
        ("OMIT", "SOURCE_NOISE"),
        ("AMBIGUOUS", "AMBIGUOUS"),
    )
    result = review.QualityReviewResult(
        review.STATEFUL_QUALITY_REVIEW_SCHEMA_VERSION,
        review.review_request_sha256(request),
        tuple(
            review.QualityReviewResultCue(
                cue.cue_id,
                action,
                category,
                "Evidence supports this structured decision.",
                "修正された日本語" if action == "REPAIR" else None,
                "수정된 한국어" if action == "REPAIR" else None,
            )
            for cue, (action, category) in zip(request.cues, actions, strict=True)
        ),
    )
    return request, review.serialize_review_result(result, request), originals


class FakeRemoteBridge(deployment.SSHRemoteHermesBridge):
    def __init__(self, task: Path, result_payload: bytes, mode: str = "success"):
        super().__init__(SimpleNamespace())
        self.task = task
        self.result_payload = result_payload
        self.mode = mode
        self.child_calls = 0
        self.remote_scripts = 0
        self.child_error = None

    def _child_run(self, command, *, cwd, pass_fds, stdin, stdout, stderr, timeout, check):
        assert len(pass_fds) == 1
        del stdin, stdout, stderr, check
        self.child_calls += 1
        if self.mode == "start_failed":
            raise OSError("private child error")
        if self.mode == "timeout":
            raise subprocess.TimeoutExpired(command, timeout)
        if self.mode != "no_result":
            output = Path(cwd) / deployment.QUALITY_REVIEW_RESULT_FILENAME
            try:
                fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except OSError as error:
                self.child_error = type(error).__name__
                raise
            with os.fdopen(fd, "wb") as stream:
                stream.write(self.result_payload)
                stream.flush()
                os.fsync(stream.fileno())
        return SimpleNamespace(returncode=7 if self.mode == "nonzero" else 0)

    def _python(
        self, script, *arguments, input_payload=None, capture=False,
        timeout=None, python_executable="python3",
    ):
        del input_payload, timeout, python_executable
        self.remote_scripts += 1
        is_launch = "receipt_name = \"stage11-quality-review-execution-receipt.json\"" in script
        if is_launch and self.mode == "ssh_before_start":
            raise deployment.Stage11DeploymentTransportError(
                "simulated private transport error",
                diagnostic={"stage": "ssh", "state": "SSH_EXIT_UNKNOWN", "ssh_returncode": 255},
            )
        if is_launch and self.mode == "receipt_missing":
            return b""
        output = io.BytesIO()
        text_output = io.TextIOWrapper(output, encoding="utf-8")
        namespace = {"__name__": "__remote_probe__"}
        try:
            with patch.object(sys, "argv", ["remote-probe", *arguments]):
                if is_launch:
                    fake_subprocess = ModuleType("subprocess")
                    fake_subprocess.DEVNULL = subprocess.DEVNULL
                    fake_subprocess.TimeoutExpired = subprocess.TimeoutExpired
                    fake_subprocess.run = self._child_run
                    with patch.dict(sys.modules, {"subprocess": fake_subprocess}), redirect_stdout(text_output):
                        exec(compile(script, "<fake-ct120-review>", "exec"), namespace)
                else:
                    with redirect_stdout(text_output):
                        exec(compile(script, "<fake-ct120-read>", "exec"), namespace)
        except SystemExit as error:
            raise deployment.Stage11DeploymentTransportError(
                "simulated remote command failure",
                diagnostic={"stage": "ssh", "state": "SSH_EXIT_UNKNOWN", "ssh_returncode": int(error.code or 1)},
            ) from error
        text_output.flush()
        if is_launch and self.mode == "ssh_after_completion":
            raise deployment.Stage11DeploymentTransportError(
                "simulated SSH channel loss after remote completion",
                diagnostic={"stage": "ssh", "state": "SSH_EXIT_UNKNOWN", "ssh_returncode": 255},
            )
        return output.getvalue() if capture else b""


def make_task(root: Path, request_payload: bytes) -> Path:
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    task = root / "task"
    task.mkdir(mode=0o700)
    input_path = task / deployment.QUALITY_REVIEW_INPUT_FILENAME
    fd = os.open(input_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(request_payload)
    os.chmod(task, 0o700)
    return task


def run_bridge(root: Path, request_payload: bytes, result_payload: bytes, mode: str):
    task = make_task(root, request_payload)
    bridge = FakeRemoteBridge(task, result_payload, mode)
    nonce = uuid.uuid4().hex + uuid.uuid4().hex
    request_sha = hashlib.sha256(request_payload).hexdigest()
    try:
        completed = bridge.launch_quality_review(
            COMMAND,
            remote_task=str(task),
            timeout=1,
            session_id=SESSION,
            request_sha256=request_sha,
            receipt_nonce=nonce,
        )
    except deployment.Stage11DeploymentTransportError as error:
        return task, bridge, nonce, error
    return task, bridge, nonce, completed


class ResultReadFailureBridge:
    def __init__(self, result_payload: bytes):
        self.result_payload = result_payload
        self.files = {}

    def ensure_task(self, remote_task):
        self.remote_task = remote_task

    def ensure_file(self, remote_path, payload):
        self.files[remote_path] = payload

    def launch_quality_review(
        self, command, *, remote_task, timeout, session_id,
        request_sha256, receipt_nonce,
    ):
        del command, timeout
        input_payload = self.files[remote_task + "/" + deployment.QUALITY_REVIEW_INPUT_FILENAME]
        self.files[remote_task + "/" + deployment.QUALITY_REVIEW_RESULT_FILENAME] = self.result_payload
        return SimpleNamespace(
            returncode=0,
            execution_receipt={
                "schema_version": 1,
                "session_id": session_id,
                "task_sha256": hashlib.sha256(remote_task.encode()).hexdigest(),
                "request_sha256": request_sha256,
                "input_sha256": hashlib.sha256(input_payload).hexdigest(),
                "receipt_nonce": receipt_nonce,
                "child_outcome": "COMPLETED",
                "child_returncode": 0,
                "result_state": "PRESENT",
                "result_sha256": hashlib.sha256(self.result_payload).hexdigest(),
                "result_size_bytes": len(self.result_payload),
            },
        )

    def read_regular(self, remote_path, *, max_bytes):
        del max_bytes
        if remote_path.endswith(deployment.QUALITY_REVIEW_RESULT_FILENAME):
            raise deployment.Stage11DeploymentTransportError(
                "simulated result read channel failure",
                diagnostic={"stage": "ssh", "state": "SSH_EXIT_UNKNOWN", "ssh_returncode": 255},
            )
        return self.files[remote_path]


def main():
    request, result_payload, originals = fixture()
    request_payload = review.serialize_review_request(request)
    request_sha = review.review_request_sha256(request)
    assert hashlib.sha256(request_payload).hexdigest() == request_sha
    passed = 0

    def check(condition, name):
        nonlocal passed
        assert condition, name
        passed += 1
        print("PASS=" + name)

    with tempfile.TemporaryDirectory(prefix="stage11-p2g-bridge-") as temporary:
        root = Path(temporary)
        task, bridge, nonce, completed = run_bridge(root / "ok", request_payload, result_payload, "success")
        receipt = completed.execution_receipt
        check(completed.returncode == 0 and receipt["child_returncode"] == 0, "NORMAL_COMPLETION_RECEIPT")
        check(bridge.child_calls == 1 and stat_mode(task / deployment.QUALITY_REVIEW_EXECUTION_RECEIPT_FILENAME) == 0o600, "PRIVATE_NO_OVERWRITE_RECEIPT")

        task, bridge, nonce, error = run_bridge(root / "nonzero", request_payload, result_payload, "nonzero")
        check(isinstance(error, deployment.Stage11DeploymentTransportError)
              and error.safe_diagnostic["state"] == "REMOTE_CHILD_NONZERO"
              and (task / deployment.QUALITY_REVIEW_RESULT_FILENAME).exists(), "NONZERO_CHILD_WITH_RESULT_BLOCKED")

        task, bridge, nonce, error = run_bridge(root / "ssh-missing", request_payload, result_payload, "ssh_before_start")
        check(isinstance(error, deployment.Stage11DeploymentTransportError)
              and error.safe_diagnostic.get("state") == "SSH_FAILED_NO_RECEIPT"
              and bridge.child_calls == 0, "SSH_FAILURE_WITHOUT_RECEIPT_UNKNOWN")

        task, bridge, nonce, error = run_bridge(root / "ssh-receipt", request_payload, result_payload, "ssh_after_completion")
        receipt_path = task / deployment.QUALITY_REVIEW_EXECUTION_RECEIPT_FILENAME
        result_path = task / deployment.QUALITY_REVIEW_RESULT_FILENAME
        eligibility = deployment.assess_quality_review_recovery(
            receipt_path.read_bytes(), result_path.read_bytes(), request_payload,
            originals=originals,
            remote_task=str(task),
            source_translation_session_id=request.source_translation_session_id,
            review_execution_session_id=SESSION, receipt_nonce=nonce,
        )
        check(isinstance(error, deployment.Stage11DeploymentTransportError)
              and error.safe_diagnostic["state"] == "SSH_FAILED_RECEIPT_FOUND"
              and eligibility.eligible is True,
              "SSH_FAILURE_RECEIPT_REQUIRES_SEPARATE_CANONICAL_VALIDATION")

        task, bridge, nonce, error = run_bridge(root / "timeout", request_payload, result_payload, "timeout")
        check(isinstance(error, deployment.Stage11DeploymentTransportError)
              and error.safe_diagnostic["state"] == "REMOTE_TIMEOUT", "TIMEOUT_FAILS_CLOSED")

        task, bridge, nonce, error = run_bridge(root / "start", request_payload, result_payload, "start_failed")
        check(isinstance(error, deployment.Stage11DeploymentTransportError)
              and error.safe_diagnostic["state"] == "REMOTE_START_FAILED", "CHILD_START_FAILURE_DISTINCT")

        task, bridge, nonce, error = run_bridge(root / "absent", request_payload, result_payload, "no_result")
        check(isinstance(error, deployment.Stage11DeploymentTransportError)
              and error.safe_diagnostic["state"] == "REMOTE_RESULT_MISSING", "RESULT_ABSENCE_BLOCKED")

        task, bridge, nonce, error = run_bridge(root / "no-receipt", request_payload, result_payload, "receipt_missing")
        check(isinstance(error, deployment.Stage11DeploymentTransportError)
              and error.safe_diagnostic["state"] == "RECEIPT_INVALID", "MISSING_COMPLETION_DIAGNOSTIC_BLOCKED")

        local_task = root / "local-review-task"
        local_task.mkdir(mode=0o700)
        input_path = local_task / deployment.QUALITY_REVIEW_INPUT_FILENAME
        fd = os.open(input_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(request_payload)
        directory_fd = os.open(local_task, os.O_RDONLY | os.O_DIRECTORY)
        result_bridge = ResultReadFailureBridge(result_payload)
        launcher = deployment._hybrid_launcher_factory(
            result_bridge,
            lambda session: "/remote/stage11/" + session,
        )
        query = f"Read {local_task / deployment.QUALITY_REVIEW_INPUT_FILENAME}; write {local_task / deployment.QUALITY_REVIEW_RESULT_FILENAME}"
        try:
            launcher(["hermes", "--resume", SESSION, "-q", query], cwd=directory_fd, timeout=1)
        except deployment.Stage11DeploymentTransportError as error:
            result_confirmation_blocked = error.safe_diagnostic["state"] == "REMOTE_RESULT_CONFIRMATION_FAILED"
        else:
            result_confirmation_blocked = False
        finally:
            os.close(directory_fd)
        check(result_confirmation_blocked, "RESULT_CONFIRMATION_FAILURE_DISTINCT")

        task, bridge, nonce, completed = run_bridge(root / "mismatch", request_payload, result_payload, "success")
        receipt_path = task / deployment.QUALITY_REVIEW_EXECUTION_RECEIPT_FILENAME
        result_path = task / deployment.QUALITY_REVIEW_RESULT_FILENAME
        wrong_result = result_path.read_bytes() + b" "
        rejected = deployment.assess_quality_review_recovery(
            receipt_path.read_bytes(), wrong_result, request_payload,
            originals=originals,
            remote_task=str(task),
            source_translation_session_id=request.source_translation_session_id,
            review_execution_session_id=SESSION, receipt_nonce=nonce,
        )
        check(rejected.eligible is False, "RESULT_SHA_MISMATCH_BLOCKED")
        receipt = json.loads(receipt_path.read_bytes())
        receipt["request_sha256"] = "0" * 64
        try:
            deployment.assess_quality_review_recovery(
                json.dumps(receipt).encode(), result_path.read_bytes(), request_payload,
                originals=originals,
                remote_task=str(task),
                source_translation_session_id=request.source_translation_session_id,
                review_execution_session_id=SESSION, receipt_nonce=nonce,
            )
        except deployment.Stage11DeploymentValidationError:
            mismatch_blocked = True
        else:
            mismatch_blocked = False
        check(mismatch_blocked, "REQUEST_IDENTITY_MISMATCH_BLOCKED")
        try:
            deployment.assess_quality_review_recovery(
                receipt_path.read_bytes(), result_path.read_bytes(), request_payload,
                originals=originals,
                remote_task=str(task),
                source_translation_session_id=request.source_translation_session_id,
                review_execution_session_id="87654321-4321-8765-4321-876543218765",
                receipt_nonce=nonce,
            )
        except deployment.Stage11DeploymentValidationError:
            review_session_blocked = True
        else:
            review_session_blocked = False
        check(review_session_blocked, "REVIEW_EXECUTION_SESSION_MISMATCH_BLOCKED")
        wrong_source = deployment.assess_quality_review_recovery(
            receipt_path.read_bytes(), result_path.read_bytes(), request_payload,
            originals=originals,
            remote_task=str(task),
            source_translation_session_id="87654321-4321-8765-4321-876543218765",
            review_execution_session_id=SESSION, receipt_nonce=nonce,
        )
        check(wrong_source.eligible is False, "SOURCE_TRANSLATION_SESSION_MISMATCH_BLOCKED")
        try:
            deployment.assess_quality_review_recovery(
                receipt_path.read_bytes(), result_path.read_bytes(), request_payload,
                originals=originals,
                remote_task=str(task) + "-wrong-task",
                source_translation_session_id=request.source_translation_session_id,
                review_execution_session_id=SESSION, receipt_nonce=nonce,
            )
        except deployment.Stage11DeploymentValidationError:
            wrong_task_blocked = True
        else:
            wrong_task_blocked = False
        check(wrong_task_blocked, "REMOTE_TASK_IDENTITY_MISMATCH_BLOCKED")
        corrupted = result_path.read_bytes() + b" trailing-corruption"
        receipt = json.loads(receipt_path.read_bytes())
        receipt["result_sha256"] = hashlib.sha256(corrupted).hexdigest()
        receipt["result_size_bytes"] = len(corrupted)
        rejected_schema = deployment.assess_quality_review_recovery(
            json.dumps(receipt).encode(), corrupted, request_payload,
            originals=originals,
            remote_task=str(task),
            source_translation_session_id=request.source_translation_session_id,
            review_execution_session_id=SESSION, receipt_nonce=nonce,
        )
        check(rejected_schema.eligible is False, "CORRUPT_RESULT_CANONICAL_VALIDATION_BLOCKED")

        duplicate_task, bridge, nonce, completed = run_bridge(root / "duplicate", request_payload, result_payload, "success")
        next_nonce = uuid.uuid4().hex + uuid.uuid4().hex
        try:
            bridge.launch_quality_review(
                COMMAND, remote_task=str(duplicate_task), timeout=1,
                session_id=SESSION, request_sha256=request_sha, receipt_nonce=next_nonce,
            )
        except deployment.Stage11DeploymentTransportError:
            duplicate_blocked = True
        else:
            duplicate_blocked = False
        check(duplicate_blocked and bridge.child_calls == 1, "DUPLICATE_EXECUTION_AND_OVERWRITE_BLOCKED")

    runner = lambda *args, **kwargs: SimpleNamespace(returncode=255, stdout=b"", stderr=b"secret")
    bridge = deployment.SSHRemoteHermesBridge(SimpleNamespace(), runner=runner)
    with patch.object(bridge, "_base", return_value=["ssh"]):
        try:
            bridge._run("probe")
        except deployment.Stage11DeploymentTransportError as error:
            ssh_unknown = error.safe_diagnostic["state"] == "SSH_EXIT_UNKNOWN" and "secret" not in str(error.safe_diagnostic)
        else:
            ssh_unknown = False
    check(ssh_unknown, "SSH_EXIT_REMAINS_UNKNOWN_WITHOUT_REMOTE_RECEIPT")
    print(f"REVIEW_BRIDGE_SMOKE_PASS={passed}")
    print("REVIEW_BRIDGE_SMOKE_FAIL=0")


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


if __name__ == "__main__":
    main()
