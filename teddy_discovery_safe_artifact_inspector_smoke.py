"""Offline privacy smoke for the Stage11/Stage12 safe artifact inspector."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile

from teddy_discovery_safe_artifact_inspector import main, inspect_artifact


SUBTITLE_SENTINEL = "SUBTITLE-BODY-SENTINEL-NEVER-EMIT"
SESSION_SENTINEL = "SESSION-ID-SENTINEL-NEVER-EMIT"
PATH_SENTINEL = "PATH-SESSION-SENTINEL"


def _write(path: Path, value: object) -> tuple[bytes, str]:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    path.write_bytes(payload)
    return payload, hashlib.sha256(payload).hexdigest()


def _run_cli(path: Path, kind: str, *extra: str) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(["--kind", kind, "--path", str(path), *extra])
    return code, stdout.getvalue(), stderr.getvalue()


def main_smoke() -> int:
    checks = 0
    failures = 0

    def check(name: str, condition: bool) -> None:
        nonlocal checks, failures
        checks += 1
        if condition:
            print("PASS " + name)
        else:
            failures += 1
            print("FAIL " + name)

    with tempfile.TemporaryDirectory(prefix="safe-artifact-inspector-") as raw:
        root = Path(raw) / PATH_SENTINEL
        root.mkdir()

        targeted_path = root / "targeted.json"
        targeted_payload, targeted_sha = _write(
            targeted_path,
            {
                "schema_version": 1,
                "source_snapshot": {
                    "dvd_id": "HMN-896",
                    "canonical_video_relative": "HMN/HMN-896.mp4",
                    "source_size": 9876,
                    "source_mtime_ns": 12345,
                },
                "baseline_asr_artifact_sha256": "a" * 64,
                "sources": [{"source_text": SUBTITLE_SENTINEL}],
                "windows": [{}, {}],
                "results": [
                    {"status": "PRESENT_UNRESOLVED", "text": SUBTITLE_SENTINEL},
                    {"status": "PRESENT_UNRESOLVED", "text": SUBTITLE_SENTINEL},
                    {"status": "EMPTY_UNRESOLVED", "text": SUBTITLE_SENTINEL},
                ],
                "bindings": [
                    {"status": "PRESENT_UNRESOLVED", "text": SUBTITLE_SENTINEL},
                    {"status": "PRESENT_UNRESOLVED", "text": SUBTITLE_SENTINEL},
                    {"status": "EMPTY_UNRESOLVED", "text": SUBTITLE_SENTINEL},
                    {"status": "NOISY_UNRESOLVED", "text": SUBTITLE_SENTINEL},
                ],
            },
        )
        code, out, err = _run_cli(
            targeted_path,
            "targeted_evidence",
            "--expected-dvd-id",
            "HMN-896",
            "--expected-source-size",
            "9876",
            "--expected-source-mtime-ns",
            "12345",
            "--expected-baseline-sha256",
            "a" * 64,
        )
        decoded = json.loads(out)
        check(
            "targeted evidence summary counts and source identity exact",
            code == 0
            and decoded["byte_size"] == len(targeted_payload)
            and decoded["sha256"] == targeted_sha
            and decoded["schema_version"] == 1
            and decoded["source_fingerprint_match"] == "YES"
            and decoded["result_count"] == 3
            and decoded["window_count"] == 2
            and decoded["source_count"] == 1
            and decoded["binding_status_counts"]
            == {
                "EMPTY_UNRESOLVED": 1,
                "NOISY_UNRESOLVED": 1,
                "PRESENT_UNRESOLVED": 2,
            },
        )
        check(
            "targeted stdout and stderr redact text session and path",
            SUBTITLE_SENTINEL not in out + err
            and SESSION_SENTINEL not in out + err
            and PATH_SENTINEL not in out + err
            and str(targeted_path) not in out + err,
        )

        fixtures = {
            "asr": {
                "schema_version": 1,
                "source_snapshot": {"dvd_id": "HMN-896"},
                "segments": [{"text": SUBTITLE_SENTINEL}],
            },
            "semantic_input": {
                "schema_version": 1,
                "dvd_id": "HMN-896",
                "cues": [{"stt_ja": SUBTITLE_SENTINEL}],
            },
            "semantic_output": {
                "schema_version": 1,
                "dvd_id": "HMN-896",
                "session_id": SESSION_SENTINEL,
                "cues": [{"ko": SUBTITLE_SENTINEL}],
            },
            "review": {
                "schema_version": 2,
                "source_translation_session_id": SESSION_SENTINEL,
                "cues": [{"repaired_ja": SUBTITLE_SENTINEL}],
            },
            "controller_report": {
                "route": "ASR_ONLY",
                "translation_result_identity": {
                    "session_id": SESSION_SENTINEL,
                    "sha256": "b" * 64,
                },
                "review_result_identity": {
                    "source_translation_session_id": SESSION_SENTINEL,
                    "review_execution_session_id": SESSION_SENTINEL,
                },
                "subtitle": SUBTITLE_SENTINEL,
            },
        }
        for kind, document in fixtures.items():
            artifact_path = root / (kind + ".json")
            payload, expected_sha = _write(artifact_path, document)
            code, fixture_out, fixture_err = _run_cli(
                artifact_path, kind
            )
            safe = json.loads(fixture_out)
            check(
                kind + " body and path never appear in output",
                code == 0
                and len(payload) == safe["byte_size"]
                and safe["sha256"] == expected_sha
                and SUBTITLE_SENTINEL not in fixture_out + fixture_err
                and SESSION_SENTINEL not in fixture_out + fixture_err
                and PATH_SENTINEL not in fixture_out + fixture_err
                and str(artifact_path) not in fixture_out + fixture_err,
            )

        mismatch = inspect_artifact(
            targeted_path,
            kind="targeted_evidence",
            expected_dvd_id="HMN-896",
            expected_source_size=1,
            expected_source_mtime_ns=12345,
        )
        check("source fingerprint mismatch is a safe NO", mismatch["source_fingerprint_match"] == "NO")

        malformed_path = root / "malformed.json"
        malformed_path.write_text(
            '{"body":"' + SUBTITLE_SENTINEL,
            encoding="utf-8",
        )
        code, malformed_out, malformed_err = _run_cli(
            malformed_path, "targeted_evidence"
        )
        malformed_summary = json.loads(malformed_out)
        check(
            "malformed JSON exposes only safe error metadata",
            code == 1
            and malformed_summary["error_code"] == "INVALID_JSON"
            and SUBTITLE_SENTINEL not in malformed_out + malformed_err
            and str(malformed_path) not in malformed_out + malformed_err,
        )

    print(f"PASS_COUNT={checks - failures}")
    print(f"FAIL_COUNT={failures}")
    print("SAFE_ARTIFACT_INSPECTOR_SMOKE=" + ("PASS" if failures == 0 else "FAIL"))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main_smoke())
