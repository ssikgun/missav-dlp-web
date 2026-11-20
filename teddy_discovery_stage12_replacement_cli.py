"""Explicit one-title Stage12 subtitle replacement entrypoint.

Preflight is read-only. Actual NAS/Jellyfin effects require both `--execute`
and the separate operator token; normal Stage12 publication never imports this
module and remains no-overwrite.
"""
from __future__ import annotations

import argparse
import os
import re

from teddy_discovery_stage12_replacement import (
    AUTHORIZATION_MODE, ReplacementAuthorization, Stage12Replacement,
)
from teddy_discovery_subtitle_replace import SubtitleReplacementMutator
from teddy_title_exclusion import ACQUIRED, configured_lock_dir, try_acquire_title_lock


EXECUTE_ENV = "TEDDY_STAGE12_REPLACEMENT_EXECUTE"
EXECUTE_VALUE = "YES_I_HAVE_REVIEWED_THIS_ONE_REPLACEMENT"
CANONICAL_ORIGIN = "https://github.com/ssikgun/missav-dlp-web.git"


def _replacement_record(dvd_id, state, bulk):
    from teddy_discovery_stage12_inventory import (
        EXISTING_KO_VALID, SKIPPED_EXISTING_KO, Stage12HoldingInventoryRecord,
    )
    rows = bulk.read_discovery_rows((dvd_id,), state)
    if len(rows) != 1:
        raise ValueError("replacement Discovery row is not unique")
    row = rows[0]
    record = Stage12HoldingInventoryRecord(
        dvd_id=dvd_id,
        holding_id=row["holding_id"],
        holding_identity="jav:" + row["relative_path"],
        media_path_identity=row["relative_path"],
        source_size_bytes=int(row["size_bytes"]),
        source_mtime_ns=int(row["mtime_ns"]),
        existing_ko=EXISTING_KO_VALID,
        eligibility=SKIPPED_EXISTING_KO,
        reason="explicit existing-publication replacement preflight",
    )
    record.__post_init__()
    return record


def build_replacement_owner(*, bulk, candidate_root):
    from teddy_discovery_completion_ssh import CompletionSSH
    from teddy_discovery_jellyfin import JellyfinClient
    from teddy_discovery_stage12_batch import recognize_jellyfin_external_subtitle
    from teddy_discovery_stage12_rollout import Stage12RolloutStateStore

    store = Stage12RolloutStateStore(bulk.ROLLOUT_DB)
    nas = SubtitleReplacementMutator(CompletionSSH(
        host=bulk.NAS["nas_host"], user=bulk.NAS["nas_user"],
        key=bulk.NAS["nas_key"], known_hosts=bulk.NAS["nas_known_hosts"],
        downloads_root="", library_root=bulk.NAS["nas_library_root"]))
    client = JellyfinClient(
        base_url=bulk.JELLYFIN_BASE_URL,
        api_key_path=bulk.JELLYFIN_API_KEY,
        timeout=10,
    )

    def recognize(dvd_id, video, destination):
        return recognize_jellyfin_external_subtitle(
            client,
            video_relative=video.relative_path,
            subtitle_relative=destination,
            full_refresh_max_attempts=bulk.JELLYFIN_FULL_REFRESH_MAX_ATTEMPTS,
        )

    owner = Stage12Replacement(
        store,
        current_record=lambda dvd_id: _replacement_record(dvd_id, store, bulk),
        nas=nas,
        jellyfin_recognizer=recognize,
    )
    return owner


def run_one_replacement(*, dvd_id, expected_old_sha256, expected_new_sha256,
                        candidate_root, approval_note, execute, owner):
    if (type(dvd_id) is not str or not dvd_id
            or any(type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None
                   for value in (expected_old_sha256, expected_new_sha256))
            or expected_old_sha256 == expected_new_sha256
            or type(approval_note) is not str or not approval_note.strip()
            or len(approval_note) > 2048 or type(execute) is not bool):
        raise ValueError("exact one-title replacement identity is required")
    authorization = ReplacementAuthorization(
        dvd_id, expected_old_sha256, expected_new_sha256,
        AUTHORIZATION_MODE, approval_note)
    if not execute:
        checked = owner.run(
            dvd_id, execute=False,
            expected_old_sha256=expected_old_sha256,
            expected_new_sha256=expected_new_sha256,
            candidate_root=candidate_root,
            authorization=authorization,
        )
        return {"phase": "PREFLIGHT", "nas_sha256": checked.witness.sha256}
    attempt = try_acquire_title_lock(dvd_id, configured_lock_dir())
    if attempt.status != ACQUIRED:
        raise ValueError("shared title lock is unavailable or busy")
    with attempt:
        return owner.run(
            dvd_id, execute=True,
            expected_old_sha256=expected_old_sha256,
            expected_new_sha256=expected_new_sha256,
            candidate_root=candidate_root,
            authorization=authorization,
        )


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--dvd-id", required=True)
    parser.add_argument("--expected-old-sha256", required=True)
    parser.add_argument("--expected-new-sha256", required=True)
    parser.add_argument("--candidate-root", required=True)
    parser.add_argument("--approval-note", required=True)
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.execute and os.environ.get(EXECUTE_ENV) != EXECUTE_VALUE:
        print("STAGE12_REPLACEMENT=BLOCKED_EXECUTE_AUTHORIZATION", flush=True)
        return 2
    import teddy_discovery_stage12_bulk_runner as bulk
    bulk.require_production_interpreter()
    bulk.check_repo(args.expected_head)
    if bulk.git_query("remote", "get-url", "origin") != CANONICAL_ORIGIN:
        raise ValueError("canonical repository origin differs")
    owner = build_replacement_owner(bulk=bulk, candidate_root=args.candidate_root)
    result = run_one_replacement(
        dvd_id=args.dvd_id,
        expected_old_sha256=args.expected_old_sha256,
        expected_new_sha256=args.expected_new_sha256,
        candidate_root=args.candidate_root,
        approval_note=args.approval_note,
        execute=args.execute,
        owner=owner,
    )
    phase = result.get("phase", "PREFLIGHT")
    print("STAGE12_REPLACEMENT=" + phase, flush=True)
    for name in ("backup_relative", "backup_sha256", "nas_sha256"):
        if result.get(name) is not None:
            print(name.upper() + "=" + str(result[name]), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
