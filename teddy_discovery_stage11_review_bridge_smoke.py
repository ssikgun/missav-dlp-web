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
from types import SimpleNamespace
from unittest.mock import patch
import uuid

import teddy_discovery_stage11_deployment as deployment
import teddy_discovery_stateful_quality_review as review
from teddy_discovery_stateful_hybrid import prepare_stateful_hybrid
from teddy_discovery_stateful_hybrid_smoke import semantic_result
from teddy_discovery_subtitle_v2_pipeline_smoke import accepted_hybrid_route
from teddy_discovery_subtitle_source_quality import classify_source_document


SESSION = "12345678-1234-5678-1234-567812345678"


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
                    self.child_calls += 1
                    with redirect_stdout(text_output):
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
        if is_launch and self.mode == "receipt_mismatch":
            receipt_path = self.task / deployment.QUALITY_REVIEW_EXECUTION_RECEIPT_FILENAME
            receipt = json.loads(receipt_path.read_bytes())
            receipt["request_sha256"] = "0" * 64
            receipt_path.write_text(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
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


def make_command(mode: str, result_payload: bytes):
    if mode == "start_failed":
        return ["/missing/stage11-hermes", "--resume", SESSION]
    encoded = result_payload.hex()
    stderr_value = {
        "cli_error": repr("usage: hermes [options]"),
        "profile_error": repr("session not found in profile"),
        "auth_error": repr("HTTP 401 unauthorized provider"),
        "permission_error": repr("permission denied opening private file"),
        "unknown_nonzero": repr("opaque failure with token=super-secret"),
        "long_stderr": "'x' * 1000000",
        "sensitive_stderr": repr("token=very-secret /root/private user message=do-not-store"),
    }.get(mode, "''")
    child = (
        "import os,sys,time\n"
        f"mode={mode!r}\n"
        f"stderr={stderr_value}\n"
        "sys.stderr.write(stderr); sys.stderr.flush()\n"
        "if mode == 'timeout': time.sleep(2)\n"
        "if mode != 'no_result':\n"
        f" fd=os.open({deployment.QUALITY_REVIEW_RESULT_FILENAME!r}, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)\n"
        f" os.write(fd, bytes.fromhex({encoded!r})); os.fsync(fd); os.close(fd)\n"
        "sys.exit(2 if mode in ('cli_error','profile_error','auth_error','permission_error','unknown_nonzero','long_stderr','sensitive_stderr','nonzero') else 0)\n"
    )
    return [sys.executable, "-c", child, "--resume", SESSION]


def run_bridge(root: Path, request_payload: bytes, result_payload: bytes, mode: str):
    task = make_task(root, request_payload)
    local_task = root / "local-task"
    local_task.mkdir(mode=0o700)
    local_fd = os.open(local_task, os.O_RDONLY | os.O_DIRECTORY)
    bridge = FakeRemoteBridge(task, result_payload, mode)
    bridge.local_fd = local_fd
    bridge.local_task = local_task
    nonce = uuid.uuid4().hex + uuid.uuid4().hex
    request_sha = hashlib.sha256(request_payload).hexdigest()
    try:
        completed = bridge.launch_quality_review(
            make_command(mode, result_payload),
            local_task_fd=local_fd,
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
        self, command, *, local_task_fd, remote_task, timeout, session_id,
        request_sha256, receipt_nonce,
    ):
        del command, timeout
        deployment._private_local_write_at(
            local_task_fd,
            deployment.QUALITY_REVIEW_EXECUTION_INTENT_FILENAME,
            json.dumps({
                "schema_version": 1,
                "session_id": session_id,
                "task_sha256": hashlib.sha256(remote_task.encode()).hexdigest(),
                "request_sha256": request_sha256,
                "receipt_nonce": receipt_nonce,
            }, sort_keys=True, separators=(",", ":")).encode("ascii"),
        )
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
        check(set(receipt) == {
            "schema_version", "session_id", "task_sha256", "request_sha256", "input_sha256",
            "receipt_nonce", "child_outcome", "child_returncode", "result_state",
            "result_sha256", "result_size_bytes",
        }, "RECEIPT_V1_EXACT_FIELDS_UNCHANGED")
        intent_payload = deployment._private_local_read_at(
            bridge.local_fd, deployment.QUALITY_REVIEW_EXECUTION_INTENT_FILENAME,
            max_bytes=deployment.QUALITY_REVIEW_EXECUTION_INTENT_MAX_BYTES,
        )
        diagnostic_payload = (task / deployment.QUALITY_REVIEW_EXECUTION_DIAGNOSTIC_FILENAME).read_bytes()
        validated_diag = deployment.validate_quality_review_execution_diagnostic(
            intent_payload, diagnostic_payload,
            (task / deployment.QUALITY_REVIEW_EXECUTION_RECEIPT_FILENAME).read_bytes(),
            session_id=SESSION, task_sha256=hashlib.sha256(str(task).encode()).hexdigest(),
            request_sha256=request_sha,
        )
        check(validated_diag["phase"] == "RECEIPT_WRITE"
              and validated_diag["execution_phase"] == "RECEIPT_WRITE"
              and validated_diag["error_class"] == "NONE",
              "DIAGNOSTIC_BOUND_TO_LOCAL_INTENT_AND_V1_RECEIPT")
        mismatched_diagnostic = json.loads(diagnostic_payload)
        mismatched_diagnostic["result_sha256"] = (
            "0" * 64 if validated_diag["result_sha256"] != "0" * 64 else "1" * 64)
        try:
            deployment.validate_quality_review_execution_diagnostic(
                intent_payload,
                json.dumps(
                    mismatched_diagnostic, sort_keys=True, separators=(",", ":")
                ).encode("utf-8"),
                (task / deployment.QUALITY_REVIEW_EXECUTION_RECEIPT_FILENAME).read_bytes(),
                session_id=SESSION, task_sha256=hashlib.sha256(str(task).encode()).hexdigest(),
                request_sha256=request_sha,
            )
        except deployment.Stage11DeploymentValidationError:
            diagnostic_mismatch_blocked = True
        else:
            diagnostic_mismatch_blocked = False
        check(diagnostic_mismatch_blocked,
              "DIAGNOSTIC_RESULT_IDENTITY_MUST_MATCH_RECEIPT")
        check(stat_mode(bridge.local_task / deployment.QUALITY_REVIEW_EXECUTION_INTENT_FILENAME) == 0o600
              and nonce not in json.dumps(validated_diag, sort_keys=True)
              and nonce not in diagnostic_payload.decode("ascii"),
              "LOCAL_NONCE_PRIVATE_AND_NOT_IN_DIAGNOSTIC")

        task, bridge, nonce, error = run_bridge(root / "nonzero", request_payload, result_payload, "nonzero")
        check(isinstance(error, deployment.Stage11DeploymentTransportError)
              and error.safe_diagnostic["state"] == "REMOTE_CHILD_NONZERO"
              and error.safe_diagnostic.get("error_class") == "UNKNOWN_NONZERO"
              and error.safe_diagnostic.get("execution_phase") == "CHILD_EXIT"
              and (task / deployment.QUALITY_REVIEW_RESULT_FILENAME).exists(), "NONZERO_CHILD_WITH_RESULT_BLOCKED")

        for mode, classification in (
            ("cli_error", "CLI_ARGUMENT_ERROR"),
            ("profile_error", "PROFILE_SESSION_ERROR"),
            ("auth_error", "AUTH_PROVIDER_ERROR"),
            ("permission_error", "FILE_PERMISSION_ERROR"),
            ("unknown_nonzero", "UNKNOWN_NONZERO"),
        ):
            task, bridge, nonce, error = run_bridge(root / mode, request_payload, result_payload, mode)
            check(isinstance(error, deployment.Stage11DeploymentTransportError)
                  and error.safe_diagnostic.get("error_class") == classification
                  and error.safe_diagnostic.get("execution_phase") == "CHILD_EXIT"
                  and nonce not in json.dumps(error.safe_diagnostic, sort_keys=True),
                  "ERROR_CLASS_" + mode.upper())

        task, bridge, nonce, error = run_bridge(root / "long-stderr", request_payload, result_payload, "long_stderr")
        check(error.safe_diagnostic.get("stderr_bytes_observed") == deployment.QUALITY_REVIEW_EXECUTION_STDERR_MAX_BYTES + 1
              and error.safe_diagnostic.get("stderr_truncated") is True
              and task.joinpath(deployment.QUALITY_REVIEW_EXECUTION_DIAGNOSTIC_FILENAME).stat().st_size < 4096,
              "STDERR_CAPTURE_BOUNDED_AND_DRAINED")

        task, bridge, nonce, error = run_bridge(root / "sensitive-stderr", request_payload, result_payload, "sensitive_stderr")
        diagnostic_bytes = task.joinpath(deployment.QUALITY_REVIEW_EXECUTION_DIAGNOSTIC_FILENAME).read_bytes()
        safe_text = json.dumps(error.safe_diagnostic, sort_keys=True)
        check(b"very-secret" not in diagnostic_bytes and b"/root/private" not in diagnostic_bytes
              and "very-secret" not in safe_text and "do-not-store" not in safe_text,
              "SENSITIVE_STDERR_NOT_STORED_OR_RETURNED")

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
              and error.safe_diagnostic["state"] == "REMOTE_TIMEOUT"
              and error.safe_diagnostic.get("error_class") == "TIMEOUT"
              and error.safe_diagnostic.get("execution_phase") == "CHILD_EXIT", "TIMEOUT_FAILS_CLOSED")

        task, bridge, nonce, error = run_bridge(root / "start", request_payload, result_payload, "start_failed")
        check(isinstance(error, deployment.Stage11DeploymentTransportError)
              and error.safe_diagnostic["state"] == "REMOTE_START_FAILED"
              and error.safe_diagnostic.get("error_class") == "EXECUTABLE_ERROR"
              and error.safe_diagnostic.get("execution_phase") == "CHILD_START", "CHILD_START_FAILURE_DISTINCT")

        task, bridge, nonce, error = run_bridge(root / "absent", request_payload, result_payload, "no_result")
        check(isinstance(error, deployment.Stage11DeploymentTransportError)
              and error.safe_diagnostic["state"] == "REMOTE_RESULT_MISSING"
              and error.safe_diagnostic.get("execution_phase") == "RESULT_CHECK", "RESULT_ABSENCE_BLOCKED")

        task, bridge, nonce, error = run_bridge(root / "no-receipt", request_payload, result_payload, "receipt_missing")
        check(isinstance(error, deployment.Stage11DeploymentTransportError)
              and error.safe_diagnostic["state"] == "RECEIPT_INVALID", "MISSING_COMPLETION_DIAGNOSTIC_BLOCKED")

        task, bridge, nonce, error = run_bridge(root / "receipt-mismatch", request_payload, result_payload, "receipt_mismatch")
        check(isinstance(error, deployment.Stage11DeploymentTransportError)
              and error.safe_diagnostic["state"] == "RECEIPT_INVALID",
              "MISMATCHED_V1_RECEIPT_BLOCKED")

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
        intent_payload = deployment._private_local_read_at(
            bridge.local_fd, deployment.QUALITY_REVIEW_EXECUTION_INTENT_FILENAME,
            max_bytes=deployment.QUALITY_REVIEW_EXECUTION_INTENT_MAX_BYTES,
        )
        diagnostic_payload = (task / deployment.QUALITY_REVIEW_EXECUTION_DIAGNOSTIC_FILENAME).read_bytes()
        bad_intent = json.loads(intent_payload)
        bad_intent["receipt_nonce"] = "0" * 64
        try:
            deployment.validate_quality_review_execution_diagnostic(
                json.dumps(bad_intent, sort_keys=True, separators=(",", ":")).encode(),
                diagnostic_payload, receipt_path.read_bytes(), session_id=SESSION,
                task_sha256=hashlib.sha256(str(task).encode()).hexdigest(),
                request_sha256=request_sha,
            )
        except deployment.Stage11DeploymentValidationError:
            nonce_mismatch_blocked = True
        else:
            nonce_mismatch_blocked = False
        check(nonce_mismatch_blocked, "INDEPENDENT_NONCE_MISMATCH_BLOCKED")
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
                make_command("success", result_payload), local_task_fd=bridge.local_fd,
                remote_task=str(duplicate_task), timeout=1,
                session_id=SESSION, request_sha256=request_sha, receipt_nonce=next_nonce,
            )
        except deployment.Stage11DeploymentError:
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
