"""Isolated offline + optional live-CT121 synthetic tests for Mozzi translation backend."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace

from teddy_discovery_hermes_v2 import HermesV2CueInput
from teddy_discovery_hybrid_evidence import HybridCueIdentity
from teddy_discovery_mozzi_backend import (
    MOZZI_BACKEND_ID,
    MOZZI_PROFILE_AUTHORITY,
    MOZZI_PROFILE_NAME,
    MOZZI_TARGET_SERVER,
    MOZZI_TRANSPORT_PROTOCOL,
    MozziSubtitleBackend,
    MozziSubtitleBackendError,
    SSH,
    _validate_no_model_overrides,
    sha,
)
import teddy_discovery_stage11_controller as controller
from teddy_discovery_stage11_hermes_profile import (
    HermesExecutionSettings,
    STAGE11_HERMES_TIMEOUT_ENV_NAMES,
)
import teddy_discovery_stage11_normal_mode as normal
from teddy_discovery_stateful_boundary import (
    STATEFUL_BOUNDARY_SCHEMA_VERSION,
    StatefulAdjacentBoundary,
    StatefulBoundaryEvidence,
    serialize_stateful_boundary_evidence,
)
from teddy_discovery_stateful_translator import (
    STATEFUL_BOUNDARY_MODEL_INPUT_MARKER,
    StatefulSubtitlePackage,
    bind_stateful_model_input_generation_key,
    serialize_stateful_model_input,
    serialize_stateful_package,
    stateful_session_id_for_package,
)


def _synthetic_package(dvd_id: str, ja_lines: list[str]) -> tuple[StatefulSubtitlePackage, StatefulBoundaryEvidence]:
    gen_key = controller.bind_stateful_policy_generation_key(
        bind_stateful_model_input_generation_key(f"stage11-normal-v1-synth-{dvd_id}"),
        controller.DEFAULT_STATEFUL_SEMANTIC_POLICY,
    )
    cues = tuple(
        HermesV2CueInput(
            cue_id=HybridCueIdentity.for_external_ja(i).cue_id,
            external_ja=text,
            stt_ja=text,
            en=None,
            before_context=(ja_lines[i - 1],) if i > 0 else (),
            after_context=(ja_lines[i + 1],) if i + 1 < len(ja_lines) else (),
        )
        for i, text in enumerate(ja_lines)
    )
    pkg = StatefulSubtitlePackage(
        schema_version=1,
        dvd_id=dvd_id,
        generation_key=gen_key,
        claim_token=1,
        cues=cues,
    )
    pairs = tuple(
        StatefulAdjacentBoundary(
            left_cue_id=cues[i].cue_id,
            right_cue_id=cues[i + 1].cue_id,
            left_source_index=i,
            right_source_index=i + 1,
            gap_ms=500,
            relation="GAP",
        )
        for i in range(len(cues) - 1)
    )
    boundary = StatefulBoundaryEvidence(
        schema_version=STATEFUL_BOUNDARY_SCHEMA_VERSION,
        dvd_id=dvd_id,
        generation_key=gen_key,
        claim_token=1,
        session_id=stateful_session_id_for_package(pkg),
        package_sha256=sha(serialize_stateful_package(pkg)),
        source_sha256="1" * 64,
        source_identity_sha256="2" * 64,
        alignment_sha256="3" * 64,
        pairs=pairs,
    )
    bound_gen_key = bind_stateful_model_input_generation_key(
        gen_key,
        boundary_evidence_sha256=sha(serialize_stateful_boundary_evidence(boundary)),
    )
    bound_pkg = StatefulSubtitlePackage(
        schema_version=1,
        dvd_id=dvd_id,
        generation_key=bound_gen_key,
        claim_token=1,
        cues=cues,
    )
    return bound_pkg, boundary


def _make_mock_runner(response_fn):
    recorded_requests: list[dict] = []

    def runner(argv, *, input, capture_output, timeout):
        assert tuple(argv) == SSH
        req = json.loads(input.decode("ascii"))
        recorded_requests.append(req)
        out_dict = response_fn(req)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(out_dict, separators=(",", ":")).encode("utf-8"),
            stderr=b"",
        )

    return runner, recorded_requests


def _ok_translate_response(
    req: dict,
    stdout_bytes: bytes,
    *,
    session_id: str = "local-synthsession00001",
    tools_count: int = 0,
    extra: dict | None = None,
) -> dict:
    resp = {
        "status": "ok",
        "profile": MOZZI_PROFILE_NAME,
        "tools_count": tools_count,
        "returncode": 0,
        "timeout_reason": None,
        "prompt_sha256": req["prompt_sha256"],
        "stdout": base64.b64encode(stdout_bytes).decode("ascii"),
        "stdout_sha256": sha(stdout_bytes),
        "stderr": "",
        "runtime_session_id": session_id,
        "elapsed_seconds": 0.12,
    }
    if extra:
        resp.update(extra)
    return resp


def _valid_result_json(package: StatefulSubtitlePackage, cue_ids: list[str] | None = None, *, part_index: int | None = None) -> bytes:
    session_id = stateful_session_id_for_package(package)
    selected = set(cue_ids) if cue_ids is not None else None
    cues_out = [
        {"cue_id": c.cue_id, "repaired_ja": None, "ko": f"합성 자막 한국어 번역 문장 {idx}"}
        for idx, c in enumerate(package.cues, 1)
        if selected is None or c.cue_id in selected
    ]
    if part_index is not None:
        payload = {
            "part_schema_version": 1,
            "session_id": session_id,
            "input_sha256": sha(serialize_stateful_model_input(package)),
            "part_index": part_index,
            "first_cue_id": cues_out[0]["cue_id"],
            "last_cue_id": cues_out[-1]["cue_id"],
            "cues": cues_out,
        }
    else:
        payload = {
            "schema_version": package.schema_version,
            "dvd_id": package.dvd_id,
            "generation_key": package.generation_key,
            "claim_token": package.claim_token,
            "session_id": session_id,
            "cues": cues_out,
        }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _ct120_dummy_settings() -> HermesExecutionSettings:
    return HermesExecutionSettings(
        profile_name="subtitle-translator",
        provider="openai-codex",
        model="gpt-6-luna",
        reasoning_effort="xhigh",
        hermes_version="0.20.0",
        config_sha256="a" * 64,
        timeout_env_supported=STAGE11_HERMES_TIMEOUT_ENV_NAMES,
    )


def test_1_zero_model_overrides_and_guards() -> None:
    for bad_key in ("model", "provider", "reasoning", "reasoning_effort", "config", "timeout_env"):
        try:
            _validate_no_model_overrides({"operation": "translate", bad_key: "x"})
            raise AssertionError(f"failed to reject forbidden key {bad_key}")
        except MozziSubtitleBackendError:
            pass

    backend = MozziSubtitleBackend(runner=lambda *a, **k: None)
    try:
        normal.NativeNormalFirstPass(object(), mozzi_backend=backend)
        raise AssertionError("should forbid mixing CT120 bridge and CT121 Mozzi")
    except controller.Stage11ControllerValidationError:
        pass

    runner = normal.NativeNormalFirstPass(mozzi_backend=backend)
    with tempfile.TemporaryDirectory() as td:
        pkg, boundary = _synthetic_package("SYNTH-GUARD-001", ["おはようございます。"])
        try:
            runner(pkg, route="HYBRID", staging_root=td, boundary_evidence=boundary, hermes_settings=_ct120_dummy_settings())
            raise AssertionError("should forbid passing CT120 HermesExecutionSettings to CT121 Mozzi")
        except controller.Stage11ControllerValidationError:
            pass
    print("TEST1_ZERO_MODEL_OVERRIDES_AND_GUARDS=PASS")


def test_2_whole_title_hashes_zero_tools_and_order() -> None:
    pkg, boundary = _synthetic_package("SYNTH-WHOLE-001", ["おはようございます。", "今日はいい天気ですね。", "また明日会いましょう。"])
    good_out = _valid_result_json(pkg)

    def respond(req):
        if req["operation"] == "health":
            return {"status": "ready", "profile": MOZZI_PROFILE_NAME, "tools_count": 0}
        return _ok_translate_response(req, good_out)

    mock_runner, reqs = _make_mock_runner(respond)
    backend = MozziSubtitleBackend(runner=mock_runner)
    assert backend.health()["tools_count"] == 0

    first_pass = normal.NativeNormalFirstPass(mozzi_backend=backend)
    with tempfile.TemporaryDirectory() as td:
        res = first_pass(pkg, route="HYBRID", staging_root=td, boundary_evidence=boundary)
        assert tuple(c.cue_id for c in res.cues) == tuple(c.cue_id for c in pkg.cues)
        assert len(first_pass._verified_attempts) == 1
        att = first_pass._verified_attempts[0]
        assert att["backend"] == MOZZI_BACKEND_ID
        assert att["target_server"] == MOZZI_TARGET_SERVER
        assert att["transport"] == MOZZI_TRANSPORT_PROTOCOL
        assert att["profile_authority"] == MOZZI_PROFILE_AUTHORITY
        assert att["model_override_count"] == 0
        assert att["tools_count"] == 0
        assert (Path(td) / pkg.dvd_id / normal.MOZZI_BINDING_FILENAME).exists()
        assert not (Path(td) / pkg.dvd_id / normal.NATIVE_SETTINGS_FILENAME).exists()
        # Verify zero forbidden override fields were sent in any request
        for r in reqs:
            _validate_no_model_overrides(r)

        # Tampered tools_count != 0 fails closed
        bad_tools_runner, _ = _make_mock_runner(lambda req: _ok_translate_response(req, good_out, tools_count=1))
        try:
            MozziSubtitleBackend(runner=bad_tools_runner).run_native_candidate(b"hello")
            raise AssertionError("tools_count=1 must fail")
        except MozziSubtitleBackendError:
            pass

        # Tampered stdout_sha256 fails closed
        def bad_sha_resp(req):
            d = _ok_translate_response(req, good_out)
            d["stdout_sha256"] = "0" * 64
            return d
        bad_sha_runner, _ = _make_mock_runner(bad_sha_resp)
        try:
            MozziSubtitleBackend(runner=bad_sha_runner).run_native_candidate(b"hello")
            raise AssertionError("tampered stdout_sha256 must fail")
        except MozziSubtitleBackendError:
            pass
    print("TEST2_WHOLE_TITLE_HASHES_ZERO_TOOLS_AND_ORDER=PASS")


def test_3_partition_fallback_retry_and_resume() -> None:
    lines = [f"テストの発話{i}です。" for i in range(1, 71)]  # 70 cues -> 2 fixed-64 parts (64 + 6)
    pkg, boundary = _synthetic_package("SYNTH-PART-001", lines)
    first_cue_id = pkg.cues[0].cue_id
    call_counter = {"n": 0}

    def respond(req):
        call_counter["n"] += 1
        prompt_text = base64.b64decode(req["prompt"]).decode("utf-8")
        marker = "INLINE_MODEL_INPUT="
        inline = json.loads(prompt_text.split(marker, 1)[1])
        cue_ids = [c["cue_id"] for c in inline["cues"]]
        # Whole-title attempts (1 & 2) fail JSON validation -> triggers bounded retry & partition fallback
        if len(cue_ids) == 70:
            return _ok_translate_response(req, b"{not valid json", session_id=f"local-wtfail{call_counter['n']:04d}")
        part_idx = 1 if cue_ids[0] == first_cue_id else 2
        # Part 1 attempt 1 fails with missing cue -> attempt 2 succeeds (tests retry inside partition)
        if part_idx == 1 and call_counter["n"] == 3:
            return _ok_translate_response(req, _valid_result_json(pkg, cue_ids[:-1], part_index=1), session_id="local-p1fail0001")
        return _ok_translate_response(
            req,
            _valid_result_json(pkg, cue_ids, part_index=part_idx),
            session_id=f"local-part{part_idx}ok{call_counter['n']:04d}",
        )

    mock_runner, reqs = _make_mock_runner(respond)
    backend = MozziSubtitleBackend(runner=mock_runner)
    first_pass = normal.NativeNormalFirstPass(mozzi_backend=backend)
    with tempfile.TemporaryDirectory() as td:
        res = first_pass(pkg, route="HYBRID", staging_root=td, boundary_evidence=boundary)
        assert len(res.cues) == 70
        assert tuple(c.cue_id for c in res.cues) == tuple(c.cue_id for c in pkg.cues)
        assert call_counter["n"] == 5  # 2 whole-title fails + 2 part-1 (retry) + 1 part-2
        assert (Path(td) / pkg.dvd_id / "whole-title-fallback.json").exists()
        assert (Path(td) / pkg.dvd_id / "whole-title-attempt-1.validation-error.json").exists()
        assert (Path(td) / pkg.dvd_id / "part-0001-attempt-1.validation-error.json").exists()

        # Resume-only replay MUST make 0 backend calls
        def forbid_runner(*_args, **_kwargs):
            raise AssertionError("resume_only must not invoke remote backend")
        replay_pass = normal.NativeNormalFirstPass(mozzi_backend=MozziSubtitleBackend(runner=forbid_runner))
        res2 = replay_pass(pkg, route="HYBRID", staging_root=td, boundary_evidence=boundary, resume_only=True)
        assert res2 == res
        assert len(replay_pass._verified_attempts) == 5
    print("TEST3_PARTITION_FALLBACK_RETRY_AND_RESUME=PASS")


def test_4_ct120_ct121_provenance_isolation() -> None:
    pkg, boundary = _synthetic_package("SYNTH-ISO-001", ["こんにちは。"])
    ct120_settings = _ct120_dummy_settings()
    backend = MozziSubtitleBackend(runner=lambda *a, **k: (_ for _ in ()).throw(AssertionError("should fail before call")))

    # Case A: CT120 settings file in staging dir -> CT121 Mozzi MUST reject
    with tempfile.TemporaryDirectory() as td:
        title_dir = controller._title_directory(Path(td), pkg.dvd_id)
        normal._bind_staging_hermes_settings(title_dir, ct120_settings)
        try:
            normal.NativeNormalFirstPass(mozzi_backend=backend)(pkg, route="HYBRID", staging_root=td, boundary_evidence=boundary)
            raise AssertionError("CT121 must reject CT120 staging directory")
        except controller.Stage11ControllerArtifactError:
            pass

    # Case B: CT120 receipt placed into CT121 staging dir -> CT121 Mozzi MUST reject
    with tempfile.TemporaryDirectory() as td:
        title_dir = controller._title_directory(Path(td), pkg.dvd_id)
        normal.store(title_dir / normal.MOZZI_BINDING_FILENAME, normal.wire(backend.backend_identity()))
        fake_ct120_receipt = {
            "provider": "openai-codex",
            "model": "gpt-6-luna",
            "reasoning": "xhigh",
            "hermes_execution_settings": ct120_settings.evidence(),
            "prompt_sha256": "b" * 64,
            "stdout_sha256": "c" * 64,
            "stderr_sha256": sha(b""),
            "runtime_session_id": "20261126_000000_abcdef",
            "returncode": 0,
            "timeout_reason": None,
            "tools_count": 0,
            "attempt": 1,
        }
        normal.store(title_dir / "whole-title-attempt-1.receipt.json", normal.wire(fake_ct120_receipt))
        try:
            normal.NativeNormalFirstPass(mozzi_backend=backend)(pkg, route="HYBRID", staging_root=td, boundary_evidence=boundary)
            raise AssertionError("CT121 must reject CT120 attempt receipt")
        except controller.Stage11ControllerArtifactError:
            pass

    # Case C: CT121 binding file in staging dir -> CT120 MUST reject
    with tempfile.TemporaryDirectory() as td:
        title_dir = controller._title_directory(Path(td), pkg.dvd_id)
        normal.store(title_dir / normal.MOZZI_BINDING_FILENAME, normal.wire(backend.backend_identity()))
        try:
            normal._bind_staging_hermes_settings(title_dir, ct120_settings)
            raise AssertionError("CT120 must reject CT121 staging directory")
        except controller.Stage11ControllerArtifactError:
            pass
    print("TEST4_CT120_CT121_PROVENANCE_ISOLATION=PASS")


def test_5_profile_change_next_call_and_mid_title_guard() -> None:
    prof_v1 = {
        "provider": "openai-codex",
        "model": "profile-model-v1",
        "reasoning_effort": "high",
        "profile_config_sha256": "1" * 64,
    }
    prof_v2 = {
        "provider": "openai-codex",
        "model": "profile-model-v2",
        "reasoning_effort": "xhigh",
        "profile_config_sha256": "2" * 64,
    }
    state = {"active": prof_v1}

    def respond_single(req):
        prompt_text = base64.b64decode(req["prompt"]).decode("utf-8")
        inline = json.loads(prompt_text.split("INLINE_MODEL_INPUT=", 1)[1])
        dvd = inline["dvd_id"]
        pkg, _ = _synthetic_package(dvd, ["おはようございます。"])
        return _ok_translate_response(req, _valid_result_json(pkg), extra=state["active"])

    runner, reqs = _make_mock_runner(respond_single)
    backend = MozziSubtitleBackend(runner=runner)

    with tempfile.TemporaryDirectory() as td:
        pkg_a, b_a = _synthetic_package("SYNTH-PROF-A", ["おはようございます。"])
        fp1 = normal.NativeNormalFirstPass(mozzi_backend=backend)
        fp1(pkg_a, route="HYBRID", staging_root=td, boundary_evidence=b_a)
        assert fp1._verified_attempts[0]["server_reported_profile_evidence"] == prof_v1

        # Simulate server profile change before next fresh title call
        state["active"] = prof_v2
        pkg_b, b_b = _synthetic_package("SYNTH-PROF-B", ["おはようございます。"])
        fp2 = normal.NativeNormalFirstPass(mozzi_backend=backend)
        fp2(pkg_b, route="HYBRID", staging_root=td, boundary_evidence=b_b)
        assert fp2._verified_attempts[0]["server_reported_profile_evidence"] == prof_v2
        for r in reqs:
            _validate_no_model_overrides(r)

    # Mid-title profile change across partitions MUST fail closed (never silently mix)
    pkg_mid, b_mid = _synthetic_package("SYNTH-PROF-MID", [f"発話{i}です。" for i in range(1, 71)])
    mid_first_id = pkg_mid.cues[0].cue_id
    mid_calls = {"n": 0}

    def respond_mid(req):
        mid_calls["n"] += 1
        prompt_text = base64.b64decode(req["prompt"]).decode("utf-8")
        inline = json.loads(prompt_text.split("INLINE_MODEL_INPUT=", 1)[1])
        cue_ids = [c["cue_id"] for c in inline["cues"]]
        if len(cue_ids) == 70:
            return _ok_translate_response(req, b"{bad", extra=prof_v1)
        part_idx = 1 if cue_ids[0] == mid_first_id else 2
        ev = prof_v1 if part_idx == 1 else prof_v2
        return _ok_translate_response(req, _valid_result_json(pkg_mid, cue_ids, part_index=part_idx), extra=ev)

    mid_runner, _ = _make_mock_runner(respond_mid)
    with tempfile.TemporaryDirectory() as td:
        try:
            normal.NativeNormalFirstPass(mozzi_backend=MozziSubtitleBackend(runner=mid_runner))(
                pkg_mid, route="HYBRID", staging_root=td, boundary_evidence=b_mid
            )
            raise AssertionError("mid-title profile change must fail closed")
        except controller.Stage11ControllerArtifactError as exc:
            assert "changed mid-title" in str(exc)
    print("TEST5_PROFILE_CHANGE_NEXT_CALL_AND_MID_TITLE_GUARD=PASS")


def test_6_live_ct121_restricted_ssh_synthetic() -> None:
    # 1. Verify restricted SSH blocks arbitrary remote Python execution
    arbitrary_argv = list(SSH[:-1]) + ["python3 -c 'print(12345)'"]
    arb = subprocess.run(arbitrary_argv, input=b"", capture_output=True, timeout=20)
    assert arb.returncode != 0 and b"12345" not in arb.stdout, f"arbitrary command unexpectedly succeeded: {arb}"
    print("LIVE_CHECK1_ARBITRARY_SSH_BLOCKED=PASS")

    # 2. Verify CT121 health()
    backend = MozziSubtitleBackend()
    h = backend.health()
    assert h["status"] == "ready" and h["profile"] == MOZZI_PROFILE_NAME and h["tools_count"] == 0
    print(f"LIVE_CHECK2_CT121_HEALTH=PASS health={h}")

    # 3. Single live whole-title synthetic translation through NativeNormalFirstPass
    pkg, boundary = _synthetic_package(
        "SYNTH-CT121-LIVE-001",
        ["おはようございます。", "今日はいい天気ですね。", "また明日会いましょう。"],
    )
    first_pass = normal.NativeNormalFirstPass(mozzi_backend=backend)
    with tempfile.TemporaryDirectory() as td:
        res = first_pass(pkg, route="HYBRID", staging_root=td, boundary_evidence=boundary)
        assert tuple(c.cue_id for c in res.cues) == tuple(c.cue_id for c in pkg.cues)
        assert all(isinstance(c.ko, str) and c.ko.strip() for c in res.cues)
        assert len(first_pass._verified_attempts) == 1
        att = first_pass._verified_attempts[0]
        assert att["tools_count"] == 0
        assert att["backend"] == MOZZI_BACKEND_ID
        assert att["target_server"] == MOZZI_TARGET_SERVER
        assert att["transport"] == MOZZI_TRANSPORT_PROTOCOL
        assert att["model_override_count"] == 0
        print(
            "LIVE_CHECK3_WHOLE_TITLE_SYNTHETIC=PASS "
            + json.dumps({
                "cues": [{"cue_id": c.cue_id, "ko": c.ko, "repaired_ja": c.repaired_ja} for c in res.cues],
                "attempt": att,
            }, ensure_ascii=False)
        )

        # 4. Resume replay with zero additional CT121 calls
        def forbid_runner(*_args, **_kwargs):
            raise AssertionError("live resume replay must not call CT121")
        replay = normal.NativeNormalFirstPass(mozzi_backend=MozziSubtitleBackend(runner=forbid_runner))
        res_replayed = replay(pkg, route="HYBRID", staging_root=td, boundary_evidence=boundary, resume_only=True)
        assert res_replayed == res
        print("LIVE_CHECK4_RESUME_REPLAY_ZERO_CALLS=PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-ct121", action="store_true", help="Run 1 live synthetic CT121 restricted-SSH translation check")
    args = parser.parse_args()
    test_1_zero_model_overrides_and_guards()
    test_2_whole_title_hashes_zero_tools_and_order()
    test_3_partition_fallback_retry_and_resume()
    test_4_ct120_ct121_provenance_isolation()
    test_5_profile_change_next_call_and_mid_title_guard()
    if args.live_ct121:
        test_6_live_ct121_restricted_ssh_synthetic()
    print("ALL_MOZZI_BACKEND_SMOKE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
