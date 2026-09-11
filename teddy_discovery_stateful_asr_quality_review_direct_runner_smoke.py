"""Offline smoke for the ASR-only direct quality-review entry point."""

from dataclasses import replace
import json
from pathlib import Path
import socket
import stat
import subprocess
import tempfile
from unittest.mock import patch
import uuid

from teddy_discovery_asr import ASRSegment
from teddy_discovery_hermes_v2 import HermesV2CueInput, HermesV2CueOutput
from teddy_discovery_stateful_asr import (
    build_stateful_asr_package,
    prepare_stateful_asr_package,
)
from teddy_discovery_stateful_asr_quality_review import (
    AMBIGUOUS,
    KEEP,
    OMIT,
    REPAIR,
    asr_quality_review_request_sha256,
    build_asr_prefilter_provenance,
    build_asr_quality_review_request,
    parse_asr_quality_review_result,
    serialize_asr_quality_review_request,
    serialize_asr_quality_review_result,
)
import teddy_discovery_stateful_asr_quality_review_direct_runner as direct
from teddy_discovery_stateful_quality_review import (
    QualityReviewResult,
    QualityReviewResultCue,
    STATEFUL_QUALITY_REVIEW_SCHEMA_VERSION,
    bind_review_execution_provenance,
)
from teddy_discovery_stateful_translator import (
    StatefulSubtitleResult,
    stateful_session_id_for_package,
)
from teddy_discovery_subtitle_v2_pipeline_smoke import asr_result


def _fixture():
    source = replace(
        asr_result(),
        segments=tuple(
            ASRSegment(index * 1000, index * 1000 + 700, text)
            for index, text in enumerate(
                ("普通の文です", "ああああ", "次の文です", "三番目", "最後です"),
                start=1,
            )
        ),
    )
    source_package = build_stateful_asr_package(
        tuple(
            HermesV2CueInput(
                cue_id=f"asr-{index:06d}",
                external_ja=None,
                stt_ja=segment.text,
                en=None,
                before_context=(),
                after_context=(),
            )
            for index, segment in enumerate(source.segments, start=1)
        ),
        dvd_id=source.source_snapshot.dvd_id,
        generation_key="direct-source",
        claim_token=3,
    )
    prepared = prepare_stateful_asr_package(
        source_package, generation_key="direct-filtered"
    )
    package = prepared.package
    first_pass = StatefulSubtitleResult(
        schema_version=package.schema_version,
        dvd_id=package.dvd_id,
        generation_key=package.generation_key,
        claim_token=package.claim_token,
        session_id=stateful_session_id_for_package(package),
        cues=tuple(
            HermesV2CueOutput(
                cue.cue_id,
                "修正版" if cue.cue_id == "asr-000001" else None,
                "첫 번역 " + cue.cue_id,
            )
            for cue in package.cues
        ),
    )
    provenance = build_asr_prefilter_provenance(
        source, prepared, asr_artifact_sha256="a" * 64
    )
    request = build_asr_quality_review_request(
        asr_result=source,
        package=package,
        result=first_pass,
        prefilter_provenance=provenance,
    )
    categories = {
        KEEP: "DIALOGUE",
        REPAIR: "SEMANTIC_REPAIR",
        OMIT: "SOURCE_NOISE",
        AMBIGUOUS: "AMBIGUOUS",
    }
    result = QualityReviewResult(
        STATEFUL_QUALITY_REVIEW_SCHEMA_VERSION,
        asr_quality_review_request_sha256(request),
        tuple(
            QualityReviewResultCue(
                cue.cue_id,
                action,
                categories[action],
                "synthetic evidence for direct-runner smoke",
                "修正" if action == REPAIR else None,
                "검수 수정" if action == REPAIR else None,
            )
            for cue, action in zip(
                request.cues,
                (KEEP, REPAIR, OMIT, AMBIGUOUS),
                strict=True,
            )
        ),
    )
    return request, serialize_asr_quality_review_request(request), serialize_asr_quality_review_result(result, request)


def main():
    request, request_payload, result_payload = _fixture()
    passed = failed = 0

    def check(name, callback):
        nonlocal passed, failed
        try:
            callback()
        except Exception as error:
            failed += 1
            print(f"FAIL {name}: {type(error).__name__}: {error}")
        else:
            passed += 1
            print("PASS " + name)

    def reject(name, callback):
        def checked():
            try:
                callback()
            except (direct.ASRQualityReviewDirectRunnerError, ValueError):
                return
            raise AssertionError("invalid direct-runner input was accepted")

        check(name, checked)

    source_translation_session_id = request.source_translation_session_id
    review_execution_session_id = str(uuid.uuid4())
    remote_task = "/home/teddy/stage11-quality-review-smoke"
    query = direct.build_direct_asr_quality_review_command(
        review_execution_session_id,
        input_sha256="b" * 64,
        request_sha256=asr_quality_review_request_sha256(request),
        remote_task=remote_task,
    )
    check(
        "pure ASR query has no Hybrid-only evidence wording",
        lambda: (
            "external_ja" not in query[-1]
            and "asr_source_quality" in query[-1]
            and "affine" not in query[-1]
            and "stt_ja" in query[-1]
            and "before_context" in query[-1]
        ),
    )
    check(
        "different-session resume contract",
        lambda: (
            query[query.index("--resume") + 1] == review_execution_session_id
            and query[query.index("--resume") + 1] != source_translation_session_id
            and query[query.index("--pass-session-id")] == "--pass-session-id"
        ),
    )

    argv_script = "import json,sys; print(json.dumps(sys.argv[1:]))"

    def run_argv_probe(*arguments):
        completed = subprocess.run(
            ["bash", "-c", direct._remote_shell_command(argv_script, *arguments)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr.decode()
        return json.loads(completed.stdout.decode())

    check(
        "remote shell argv single argument",
        lambda: run_argv_probe("/tmp/task") == ["/tmp/task"],
    )
    check(
        "remote shell argv multiple arguments",
        lambda: run_argv_probe("arg1", "arg2", "arg3") == ["arg1", "arg2", "arg3"],
    )
    check(
        "remote shell argv quoting regression",
        lambda: run_argv_probe("white space", "single'quote", "-dash")
        == ["white space", "single'quote", "-dash"],
    )

    captured_transport = []

    def fake_ssh(base, shell_command, **kwargs):
        captured_transport.append((base, shell_command, kwargs))
        return b"read-result" if kwargs.get("capture") else b""

    stage_task = "/home/teddy/stage11-direct-runner-smoke"
    with patch.object(direct, "_ssh_run", side_effect=fake_ssh):
        direct._remote_preflight(["ssh"], stage_task, timeout=7)
        direct._remote_create_task(["ssh"], stage_task, timeout=7)
        direct._remote_write_input(
            ["ssh"], stage_task, b"input", "b" * 64, timeout=7
        )
        direct._remote_run_hermes(
            ["ssh"], stage_task, ["/home/teddy/.local/bin/hermes", "-q", "query"],
            timeout=7,
        )
        readback = direct._remote_read_result(["ssh"], stage_task, timeout=7)
    check(
        "injected remote stages preserve task argument",
        lambda: (
            readback == b"read-result"
            and len(captured_transport) == 5
            and all(stage_task in command for _, command, _ in captured_transport)
            and all("/--" not in command and " -- " not in command
                     for _, command, _ in captured_transport)
        ),
    )

    with tempfile.TemporaryDirectory(prefix="asr-preflight-paths-") as temporary:
        fixture = Path(temporary)
        wrapper = fixture / "hermes"
        profile = fixture / "config.yaml"
        source = fixture / "hermes-agent"
        source.mkdir()
        wrapper.write_bytes(b"wrapper")
        profile.write_bytes(b"profile")
        wrapper.chmod(0o600)
        profile.chmod(0o600)
        real_python = fixture / "python-real"
        real_python.write_bytes(b"python")
        real_python.chmod(0o755)
        python_link = fixture / "python"
        task = fixture / "task"

        def run_local_preflight(base, command, **kwargs):
            del base, kwargs
            completed = subprocess.run(
                ["bash", "-c", command],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if completed.returncode != 0:
                raise direct.ASRQualityReviewDirectRunnerError(
                    "local preflight fixture failed: "
                    + completed.stderr.decode("utf-8", "replace")
                )
            return b""

        def preflight():
            with patch.object(direct, "_ssh_run", side_effect=run_local_preflight):
                direct._remote_preflight(["ssh"], str(task), timeout=7)

        with patch.object(direct, "REMOTE_HERMES_HOSTNAME", socket.gethostname()), \
             patch.object(direct, "REMOTE_HERMES_EXECUTABLE", str(wrapper)), \
             patch.object(direct, "REMOTE_HERMES_PROFILE", str(profile)), \
             patch.object(direct, "REMOTE_HERMES_SOURCE", str(source)), \
             patch.object(direct, "REMOTE_HERMES_PYTHON", str(real_python)):
            check("preflight direct regular executable", preflight)
            python_link.symlink_to(real_python)
            with patch.object(direct, "REMOTE_HERMES_PYTHON", str(python_link)):
                check("preflight symlink to regular executable", preflight)
            python_link.unlink()
            python_link.symlink_to(fixture / "missing-python")
            with patch.object(direct, "REMOTE_HERMES_PYTHON", str(python_link)):
                reject("preflight broken symlink", preflight)
            python_link.unlink()
            python_link.symlink_to(source)
            with patch.object(direct, "REMOTE_HERMES_PYTHON", str(python_link)):
                reject("preflight symlink to directory", preflight)
            python_link.unlink()
            non_executable = fixture / "python-non-executable"
            non_executable.write_bytes(b"python")
            non_executable.chmod(0o600)
            with patch.object(direct, "REMOTE_HERMES_PYTHON", str(non_executable)):
                reject("preflight non-executable target", preflight)

    fresh_command_capture = []

    def capture_fresh_command(base, command, **kwargs):
        fresh_command_capture.append((base, command, kwargs))
        return b""

    with patch.object(direct, "_ssh_run", side_effect=capture_fresh_command):
        direct._remote_prepare_fresh_session(
            ["ssh"], review_execution_session_id, timeout=7
        )
    check(
        "fresh native create command is separate from Hermes invocation",
        lambda: (
            len(fresh_command_capture) == 1
            and direct.REMOTE_HERMES_PYTHON in fresh_command_capture[0][1]
            and "SessionDB" in fresh_command_capture[0][1]
            and "create_session" in fresh_command_capture[0][1]
            and review_execution_session_id in fresh_command_capture[0][1]
        ),
    )

    with tempfile.TemporaryDirectory(prefix="asr-quality-direct-smoke-") as temporary:
        root = Path(temporary)
        input_path = root / "input.json"
        input_path.write_bytes(request_payload)
        input_path.chmod(0o600)

        def fake_executor(received, payload, input_sha, task, timeout):
            assert received == request
            assert payload == request_payload
            assert len(input_sha) == 64
            assert task == remote_task
            assert timeout == 31
            return result_payload

        output_path = root / "result.json"
        expected_result = bind_review_execution_provenance(
            parse_asr_quality_review_result(result_payload, request),
            request,
            review_execution_session_id,
        )
        expected_payload = serialize_asr_quality_review_result(
            expected_result, request
        )
        with patch.object(direct.subprocess, "run", side_effect=AssertionError("Hermes/SSH forbidden in smoke")):
            execution = direct.run_asr_quality_review(
                input_path,
                output_path,
                review_execution_session_id,
                remote_task=remote_task,
                timeout=31,
                executor=fake_executor,
            )
        check("valid ASR-only request and all four actions", lambda: (
            execution.cue_count == 4
            and output_path.read_bytes() == expected_payload
            and stat.S_IMODE(output_path.stat().st_mode) == 0o600
            and execution.source_translation_session_id == source_translation_session_id
            and execution.review_execution_session_id == review_execution_session_id
        ))
        check("input SHA and result SHA are reported", lambda: (
            execution.input_sha256 == __import__("hashlib").sha256(request_payload).hexdigest()
            and execution.result_sha256 == __import__("hashlib").sha256(expected_payload).hexdigest()
        ))
        fresh_order = []

        def fresh_session_preparer(session_id):
            fresh_order.append(("prepare", session_id))

        def fresh_executor(received, payload, input_sha, task, timeout):
            fresh_order.append(("execute", review_execution_session_id))
            return fake_executor(received, payload, input_sha, task, timeout)

        fresh_output = root / "fresh-result.json"
        fresh_execution = direct.run_asr_quality_review(
            input_path,
            fresh_output,
            review_execution_session_id,
            remote_task=remote_task,
            timeout=31,
            executor=fresh_executor,
            fresh_review_session=True,
            fresh_session_preparer=fresh_session_preparer,
        )
        check(
            "fresh pre-create precedes same-ID resume command execution",
            lambda: (
                fresh_order == [
                    ("prepare", review_execution_session_id),
                    ("execute", review_execution_session_id),
                ]
                and fresh_execution.review_execution_session_id
                == review_execution_session_id
                and fresh_execution.source_translation_session_id
                == source_translation_session_id
            ),
        )
        reject(
            "output-exists rejection and no overwrite",
            lambda: direct.run_asr_quality_review(
                input_path,
                output_path,
                review_execution_session_id,
                remote_task=remote_task,
                executor=fake_executor,
            ),
        )
        check("existing final artifact remains unchanged", lambda: output_path.read_bytes() == expected_payload)

        bad_input = root / "bad-input.json"
        bad_input.write_bytes(b"{}")
        bad_input.chmod(0o600)
        reject(
            "invalid input rejection",
            lambda: direct.run_asr_quality_review(
                bad_input,
                root / "bad-output.json",
                review_execution_session_id,
                remote_task=remote_task,
                executor=fake_executor,
            ),
        )
        check(
            "different execution session is allowed",
            lambda: direct.run_asr_quality_review(
                input_path,
                root / "mismatch-output.json",
                str(uuid.uuid4()),
                remote_task=remote_task,
                timeout=31,
                executor=fake_executor,
            ),
        )
        check(
            "same execution/provenance session is allowed",
            lambda: direct.run_asr_quality_review(
                input_path,
                root / "same-session-output.json",
                source_translation_session_id,
                remote_task=remote_task,
                timeout=31,
                executor=fake_executor,
            ).source_translation_session_id == source_translation_session_id,
        )
        reject(
            "malformed execution session rejected",
            lambda: direct.run_asr_quality_review(
                input_path,
                root / "malformed-session-output.json",
                "not a session",
                remote_task=remote_task,
                executor=fake_executor,
            ),
        )

        result_object = json.loads(result_payload.decode("utf-8"))
        variants = {}
        duplicate = dict(result_object)
        duplicate["cues"] = list(result_object["cues"])
        duplicate["cues"][0] = dict(duplicate["cues"][0])
        duplicate["cues"][0]["cue_id"] = duplicate["cues"][1]["cue_id"]
        variants["duplicate result cue"] = json.dumps(duplicate).encode()
        missing = dict(result_object)
        missing["cues"] = list(result_object["cues"])[:-1]
        variants["missing result cue"] = json.dumps(missing).encode()
        reordered = dict(result_object)
        reordered["cues"] = list(reversed(result_object["cues"]))
        variants["out-of-order result cue"] = json.dumps(reordered).encode()
        invalid_action = json.loads(result_payload.decode("utf-8"))
        invalid_action["cues"] = list(invalid_action["cues"])
        invalid_action["cues"][0] = dict(invalid_action["cues"][0])
        invalid_action["cues"][0]["action"] = "INVALID_ACTION"
        variants["invalid action"] = json.dumps(invalid_action).encode()
        mismatched_source = dict(result_object)
        mismatched_source["source_translation_session_id"] = str(uuid.uuid4())
        mismatched_source["review_execution_session_id"] = review_execution_session_id
        variants["source provenance mismatch"] = json.dumps(mismatched_source).encode()
        variants["malformed Hermes result"] = b"not-json"
        for name, raw in variants.items():
            target = root / (name.replace(" ", "-") + ".json")
            reject(
                name,
                lambda target=target, raw=raw: direct.run_asr_quality_review(
                    input_path,
                    target,
                    review_execution_session_id,
                    remote_task=remote_task,
                    executor=lambda *args: raw,
                ),
            )
            check(name + " leaves no final artifact", lambda target=target: not target.exists())

    if failed:
        raise SystemExit(f"ASR direct runner smoke failed: {failed}/{passed + failed}")
    print(f"ASR_QUALITY_REVIEW_DIRECT_RUNNER_SMOKE_PASS={passed}")


if __name__ == "__main__":
    main()
