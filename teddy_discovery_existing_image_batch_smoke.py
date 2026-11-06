#!/usr/bin/env python3
"""Small offline checks for the sequential Stage9 helper."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import teddy_discovery_existing_image_batch as batch


def runner_result(dvd_id: str, image_status: str, *, error: str = ""):
    image = {"status": image_status}
    if error:
        image["error"] = error
    body = {
        "status": "PARTIAL_FAILURE" if image_status == "ATTENTION" else "PENDING" if image_status == "PENDING" else "COMPLETE",
        "stage": "stage9-existing-image-only",
        "target_dvd_id": dvd_id,
        "image": image,
        "non_media_execution": 0,
        "jellyfin_get_requests": 0,
        "jellyfin_post_attempts": 0,
        "media_database_writes": 0,
    }
    return subprocess.CompletedProcess([], 0 if image_status != "ATTENTION" else 1,
                                       json.dumps(body), "")


def identity(targets, base):
    return batch.plan_identity(targets, base, "a" * 64, "b" * 40, "c" * 64)


class BatchSmoke(unittest.TestCase):
    def setUp(self):
        self.targets, self.excluded = batch.load_targets(batch.DEFAULT_MANIFEST)

    @staticmethod
    def write_journal(path: Path, records, targets):
        header = {"plan": identity(targets, ["python", "runner.py"])}
        path.write_text("\n".join(json.dumps(x) for x in (header, *records)) + "\n")
        path.chmod(0o600)

    def test_manifest_exact_count_unique_and_protected_exclusion(self):
        self.assertEqual(len(self.targets), 54)
        self.assertEqual(len(set(self.targets)), 54)
        self.assertEqual(self.excluded, ["MBRBI-015"])
        self.assertNotIn("MBRBI-015", self.targets)
        evidence = (batch.ROOT / "docs/governance/stage9-media/evidence/2026-11-06-all-present-primary-inventory.md").read_text(encoding="utf-8")
        source_ids = re.findall(r"^- `([^`]+)`$", evidence, re.MULTILINE)
        self.assertEqual(len(source_ids), 55)
        self.assertEqual(self.targets, [dvd_id for dvd_id in source_ids if dvd_id not in self.excluded])

    def test_default_plan_does_not_check_systemd_or_invoke_runner(self):
        stdout = io.StringIO()
        with patch.object(batch, "check_stopped_systemd", side_effect=AssertionError("systemd accessed")), contextlib.redirect_stdout(stdout):
            self.assertEqual(batch.main(["--targets-file", str(batch.DEFAULT_MANIFEST)]), 0)
        plan = json.loads(stdout.getvalue())
        self.assertEqual(plan["mode"], "PLAN")
        self.assertEqual(plan["count"], 54)
        self.assertEqual(plan["runner_invocations"], 0)

    def test_apply_is_blocked_before_manifest_or_runner_access(self):
        stdout = io.StringIO()
        with patch.object(batch, "load_targets", side_effect=AssertionError("manifest accessed")), \
             patch.object(batch, "read_approval", side_effect=batch.BatchError("BLOCKED_NO_APPROVAL")), \
             patch.object(batch, "_invoke", side_effect=AssertionError("runner invoked")), \
             contextlib.redirect_stdout(stdout):
            self.assertEqual(batch.main(["--apply", "--confirm", batch.CONFIRMATION,
                                         "--journal", "/tmp/example", "--targets-file", "/tmp/alternate"]), 2)
        self.assertEqual(json.loads(stdout.getvalue())["error"], "BLOCKED_NO_APPROVAL")

    def test_each_runner_command_is_exact_target_with_limit_one(self):
        base = ["/usr/bin/python3", "-B", "/release/teddy_discovery_media_only_runner.py",
                "--max-items", "1", "--apply", "--confirm", "APPLY_STAGE9_MEDIA_ONLY"]
        for dvd_id in self.targets:
            command = batch.target_argv(base, dvd_id)
            self.assertEqual(command[command.index("--target-dvd-id") + 1], dvd_id)
            self.assertEqual(command[command.index("--max-items") + 1], "1")
            self.assertEqual(command.count("--max-items"), 1)
            self.assertIn("--thumbnail-only", command)
            self.assertIn("--existing-image-only", command)

    def test_pending_proceeds_sequentially_and_records_results(self):
        selected = self.targets[:3]
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "run.jsonl"
            calls = []
            preflight_calls = []
            statuses = ["PENDING", "SKIPPED", "COMPLETE"]
            def invoke(command, dvd_id):
                calls.append((dvd_id, command[command.index("--max-items") + 1]))
                return runner_result(dvd_id, statuses[len(calls) - 1])
            result = batch.run_sequential(selected, ["python", "runner.py", "--max-items", "1"], journal,
                                          identity=identity(selected, ["python", "runner.py", "--max-items", "1"]), invoke=invoke, preflight=lambda: preflight_calls.append(True))
            self.assertEqual(result["status"], "COMPLETE_PLAN")
            self.assertEqual(calls, [(x, "1") for x in selected])
            self.assertEqual(len(preflight_calls), 3)
            rows = [json.loads(x) for x in journal.read_text().splitlines()]
            self.assertEqual([x["status"] for x in rows[1:]], ["RUNNING", "PENDING", "RUNNING", "SKIPPED", "RUNNING", "COMPLETE"])

    def test_attention_stops_before_next_target(self):
        selected = self.targets[:3]
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "run.jsonl"
            calls = []
            def invoke(command, dvd_id):
                calls.append(dvd_id)
                return runner_result(dvd_id, "ATTENTION", error="PATH_VERIFICATION_REQUIRED")
            result = batch.run_sequential(selected, ["python", "runner.py"], journal,
                                          identity=identity(selected, ["python", "runner.py"]), invoke=invoke, preflight=lambda: None)
            self.assertEqual(result["status"], "STOPPED")
            self.assertEqual(result["stopped_at"], selected[0])
            self.assertEqual(calls, [selected[0]])

    def test_resume_skips_durable_results_and_never_replays_running_target(self):
        selected = self.targets[:3]
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "run.jsonl"
            self.write_journal(journal, (
                {"dvd_id": selected[0], "status": "RUNNING", "detail": ""},
                {"dvd_id": selected[0], "status": "COMPLETE", "detail": ""},
                {"dvd_id": selected[1], "status": "RUNNING", "detail": ""},
                {"dvd_id": selected[1], "status": "PENDING", "detail": ""},
            ), selected)
            calls = []
            result = batch.run_sequential(selected, ["python", "runner.py"], journal,
                                          identity=identity(selected, ["python", "runner.py"]), invoke=lambda cmd, dvd: (calls.append(dvd), runner_result(dvd, "COMPLETE"))[1],
                                          preflight=lambda: None, resume=True)
            self.assertEqual(result["status"], "COMPLETE_PLAN")
            self.assertEqual(calls, [selected[2]])
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "run.jsonl"
            self.write_journal(journal, ({"dvd_id": selected[0], "status": "RUNNING", "detail": ""},), selected)
            calls = []
            result = batch.run_sequential(selected, ["python", "runner.py"], journal,
                                          identity=identity(selected, ["python", "runner.py"]), invoke=lambda cmd, dvd: calls.append(dvd),
                                          preflight=lambda: None, resume=True)
            self.assertEqual(result["status"], "HOLD")
            self.assertEqual(calls, [])

    def test_resume_hold_on_error_and_invalid_runner_result(self):
        selected = self.targets[:1]
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "run.jsonl"
            self.write_journal(journal, ({"dvd_id": selected[0], "status": "ERROR", "detail": "failed"},), selected)
            result = batch.run_sequential(selected, ["python", "runner.py"], journal,
                                          identity=identity(selected, ["python", "runner.py"]), invoke=lambda *_: self.fail("must not replay"),
                                          preflight=lambda: None, resume=True)
            self.assertEqual(result["status"], "HOLD")
        self.assertEqual(batch._result_status(0, "{}", selected[0]), ("ERROR", "RUNNER_TARGET_RESULT_MISMATCH"))

    def test_runner_attention_and_execution_error_are_classified(self):
        selected_id = self.targets[0]
        attention = runner_result(selected_id, "ATTENTION", error="PATH_VERIFICATION_REQUIRED")
        self.assertEqual(batch._result_status(attention.returncode, attention.stdout, selected_id),
                         ("ATTENTION", "PATH_VERIFICATION_REQUIRED"))
        self.assertEqual(batch._result_status(2, json.dumps({"status": "ERROR", "error": "DB_READ_FAILED"}), selected_id),
                         ("ERROR", "DB_READ_FAILED"))
        self.assertEqual(batch._result_status(0, json.dumps({
            "status": "COMPLETE", "stage": "stage9-existing-image-only", "target_dvd_id": selected_id,
            "image": {"status": "COMPLETE"}, "non_media_execution": 0,
            "jellyfin_get_requests": 0, "jellyfin_post_attempts": 0, "media_database_writes": 0,
        }), selected_id), ("COMPLETE", ""))

    def test_manifest_and_host_guards(self):
        self.assertEqual(batch.verify_manifest(batch.DEFAULT_MANIFEST)[0], self.targets)
        with tempfile.TemporaryDirectory() as tmp:
            other = Path(tmp) / "other.json"
            other.write_bytes(batch.DEFAULT_MANIFEST.read_bytes())
            with self.assertRaises(batch.BatchError):
                batch.verify_manifest(other)
            other.write_bytes(other.read_bytes().replace(b'FC2-PPV-4982148', b'FC2-PPV-4982149'))
            with patch.object(batch, "DEFAULT_MANIFEST", other), self.assertRaises(batch.BatchError):
                batch.verify_manifest(other)
        fake_id = "1" * 32
        fingerprint = hashlib.sha256(("stage9-ct108:" + fake_id).encode()).hexdigest()[:24]
        with patch.object(batch, "EXPECTED_HOST_FINGERPRINT", fingerprint):
            batch.verify_host("downloader", fake_id, 0)
            with self.assertRaises(batch.BatchError):
                batch.verify_host("downloader", "2" * 32, 0)
            with self.assertRaises(batch.BatchError):
                batch.verify_host("other", fake_id, 0)

    def test_journal_rejects_changed_plan(self):
        selected, base = self.targets[:2], ["python", "runner.py"]
        original = identity(selected, base)
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "run.jsonl"
            batch.run_sequential(selected, base, journal, identity=original,
                                 invoke=lambda cmd, dvd: runner_result(dvd, "PENDING"), preflight=lambda: None)
            before = journal.read_bytes()
            for manifest, release, runner, argv in [("d" * 64, "b" * 40, "c" * 64, base),
                                                    ("a" * 64, "e" * 40, "c" * 64, base),
                                                    ("a" * 64, "b" * 40, "f" * 64, base),
                                                    ("a" * 64, "b" * 40, "c" * 64, base + ["--other"])]:
                changed = batch.plan_identity(selected, argv, manifest, release, runner)
                with self.assertRaises(batch.BatchError):
                    batch.run_sequential(selected, argv, journal, identity=changed,
                                         invoke=lambda *_: self.fail("runner invoked"), preflight=lambda: None, resume=True)
                self.assertEqual(journal.read_bytes(), before)
            with self.assertRaises(batch.BatchError):
                batch.run_sequential(selected, base, journal, identity={},
                                     invoke=lambda *_: self.fail("runner invoked"), preflight=lambda: None, resume=True)

    def test_unattested_runner_is_blocked(self):
        with self.assertRaises(batch.BatchError):
            batch.verify_runner(["/release/teddy_discovery_media_only_runner.py"], batch.EXPECTED_RELEASE)

    def test_prepared_fake_plan_runs_in_order(self):
        base = ["python", "runner.py"]
        with patch.object(batch, "check_host"), patch.object(batch, "check_stopped_systemd", return_value=Path("/fake/unit")), \
             patch.object(batch, "pinned_runner_argv", return_value=(base, batch.EXPECTED_RELEASE)), \
             patch.object(batch, "verify_runner", return_value="c" * 64):
            targets, command, plan = batch.prepare_plan(batch.DEFAULT_MANIFEST)
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            result = batch.run_sequential(targets, command, Path(tmp) / "journal", identity=plan,
                preflight=lambda: None,
                invoke=lambda cmd, dvd: (calls.append((dvd, cmd[cmd.index("--max-items") + 1])), runner_result(dvd, "PENDING"))[1])
        self.assertEqual(result["status"], "COMPLETE_PLAN")
        self.assertEqual(calls, [(dvd, "1") for dvd in targets])

    def test_approved_main_uses_fake_runner_and_rejects_mismatch(self):
        base = ["python", "runner.py"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            approval = root / "approval.json"
            journal = root / "journal.jsonl"
            plan = batch.plan_identity(self.targets, base, batch.MANIFEST_SHA256, batch.EXPECTED_RELEASE, batch.EXPECTED_RUNNER_SHA256)
            run_id = "offline_test_run_0001"
            bound = dict(plan, run_id=run_id, journal_path=str(journal))
            record = {"scope": "STG9MEDIA-001-existing-image-54", "authorizer": "Teddy", "host_fingerprint": batch.EXPECTED_HOST_FINGERPRINT, "run_id": run_id, "expires_utc": "2999-01-01T00:00:00Z", "plan": bound}
            approval.write_text(json.dumps(record))
            approval.chmod(0o600)
            calls = []
            with patch.object(batch, "APPROVAL_FILE", approval), patch.object(batch, "check_host"), \
                 patch.object(batch, "check_stopped_systemd", return_value=Path("/fake/unit")), \
                 patch.object(batch, "pinned_runner_argv", return_value=(base, batch.EXPECTED_RELEASE)), \
                 patch.object(batch, "verify_runner", return_value=batch.EXPECTED_RUNNER_SHA256), \
                 patch.object(batch, "_invoke", side_effect=lambda cmd: (calls.append(cmd), runner_result(cmd[cmd.index("--target-dvd-id") + 1], "PENDING"))[1]), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(batch.main(["--apply", "--journal", str(journal)]), 0)
                self.assertEqual(len(calls), 54)
                self.assertTrue(all(cmd[cmd.index("--max-items") + 1] == "1" for cmd in calls))
                record["host_fingerprint"] = "bad"
                approval.write_text(json.dumps(record))
                calls.clear()
                self.assertEqual(batch.main(["--apply", "--journal", str(journal), "--resume"]), 2)
                self.assertEqual(calls, [])
                record["host_fingerprint"] = batch.EXPECTED_HOST_FINGERPRINT
                for key in ("manifest_sha256", "release_id", "runner_sha256", "argv_sha256"):
                    bad = dict(record, plan=dict(bound, **{key: "wrong"}))
                    with self.assertRaises(batch.BatchError):
                        batch.validate_approval(bad, plan, journal)
                approval.write_text(json.dumps(record))
                approval.chmod(0o644)
                with self.assertRaises(batch.BatchError):
                    batch.read_approval(approval)
                record["expires_utc"] = "2000-01-01T00:00:00Z"
                with self.assertRaises(batch.BatchError):
                    batch.validate_approval(record, plan, journal)


if __name__ == "__main__":
    unittest.main(verbosity=2)
