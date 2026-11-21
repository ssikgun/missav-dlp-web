"""Publish one explicitly selected, hash-pinned existing Normal Mode completion."""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import socket
from pathlib import Path

import teddy_discovery_stage12_bulk_runner as bulk
import teddy_discovery_stage12_rollout as rollout
from teddy_discovery_completion_ssh import CompletionSSH
from teddy_discovery_jellyfin import JellyfinClient
from teddy_discovery_stage11_normal_mode import PROOF_NAME, validate_normal_completion
from teddy_discovery_stage12_batch import (
    Stage12BatchRunner, Stage12BatchSelection, recognize_jellyfin_external_subtitle,
)
from teddy_discovery_stage12_inventory import build_subtitle_ssh_reader
from teddy_discovery_subtitle_publish import SubtitleSSHMutator


def checked_completion(root, dvd_id, digests):
    baseline, clean, report = rollout._artifact_bundle_paths(root, dvd_id)
    proof = report.parent / PROOF_NAME

    def check_hashes():
        for path, digest in zip((clean, report, proof), digests, strict=True):
            payload = rollout._read_local_regular(path, max_bytes=16 * 1024 * 1024)
            if hashlib.sha256(payload).hexdigest() != digest:
                raise ValueError("existing completion SHA mismatch: " + path.name)

    check_hashes()
    result = validate_normal_completion(report, clean, baseline, title=dvd_id)
    if (result.clean_sha256, result.report_sha256) != digests[:2]:
        raise ValueError("validated completion differs from approved SHA")
    check_hashes()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("expected-head", "dvd-id", "artifact-root", "srt-sha256",
                 "report-sha256", "proof-sha256"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--execute", action="store_true", required=True)
    args = parser.parse_args()
    if (os.geteuid() != 0 or socket.gethostname().split(".")[0] != "downloader"
            or Path("/proc/1/comm").read_text().strip() != "systemd"):
        raise SystemExit("SAFE_STOP=CT108_IDENTITY")
    digests = (args.srt_sha256, args.report_sha256, args.proof_sha256)
    if any(re.fullmatch(r"[0-9a-f]{64}", value) is None for value in digests):
        raise SystemExit("SAFE_STOP=INVALID_SHA256")
    dvd = rollout._validated_dvd_id(args.dvd_id)
    root = rollout._safe_artifact_root(args.artifact_root)
    if not root.is_dir() or root.resolve(strict=True) != root:
        raise SystemExit("SAFE_STOP=ARTIFACT_ROOT")

    bulk.require_production_interpreter()
    with bulk.RunnerLock(bulk.LOCK_PATH):
        bulk.check_repo(args.expected_head)
        if bulk.git_query("remote", "get-url", "origin") != "https://github.com/ssikgun/missav-dlp-web.git":
            raise SystemExit("SAFE_STOP=ORIGIN")
        bulk.require_regular(bulk.ROLLOUT_DB)
        store = rollout.Stage12RolloutStateStore(bulk.ROLLOUT_DB)
        if bulk.active_rollout_ids(store) or dvd not in bulk.eligible_pending_ids(store):
            raise SystemExit("SAFE_STOP=ROLLOUT_STATE")
        reader = build_subtitle_ssh_reader(**bulk.NAS)
        fs = rollout.build_nas_preflight_filesystem(**bulk.NAS)

        def current_inventory():
            return bulk.read_exact_nas_inventory(bulk.read_discovery_rows((dvd,), store), reader)

        records = current_inventory()

        def load_existing(title):
            if title != dvd or bulk.active_rollout_ids(store) or current_inventory() != records:
                raise ValueError("current publication eligibility changed")
            checked = rollout._preflight_record(records[dvd], artifact_root=root, nas_filesystem=fs)
            if checked.publication_preflight != rollout.PUBLICATION_READY:
                raise ValueError("existing source or completion preflight blocked: " + checked.reason)
            return checked_completion(root, title, digests)

        nas = bulk.NAS
        publisher = SubtitleSSHMutator(CompletionSSH(
            host=nas["nas_host"], user=nas["nas_user"], key=nas["nas_key"],
            known_hosts=nas["nas_known_hosts"], downloads_root="",
            library_root=nas["nas_library_root"],
        ))
        jellyfin = JellyfinClient(
            base_url=bulk.JELLYFIN_BASE_URL, api_key_path=bulk.JELLYFIN_API_KEY, timeout=10,
        )

        def recognize(_title, video, destination):
            return recognize_jellyfin_external_subtitle(
                jellyfin, video_relative=video.relative_path, subtitle_relative=destination,
                poll_interval_seconds=5, max_attempts=30,
                full_refresh_max_attempts=bulk.JELLYFIN_FULL_REFRESH_MAX_ATTEMPTS,
            )

        runner = Stage12BatchRunner(
            store=store, inventory=records, artifact_root=root, nas_filesystem=fs,
            subtitle_reader=reader, publisher=publisher, controller_runner=load_existing,
            jellyfin_recognizer=recognize, reuse_existing_completion=True,
        )
        result = runner.run(Stage12BatchSelection(1, (dvd,))).titles[0]
        bulk.emit("NAS_PUBLICATION", result.publication_result)
        bulk.emit("JELLYFIN_SUBTITLE_RECOGNITION", result.jellyfin_recognition)
        bulk.emit("STAGE12_FINAL_STATUS", result.final_state)
        return 0 if result.final_state == "PUBLISHED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
