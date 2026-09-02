from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import argparse
import json

from teddy_discovery_completion import (
    plan_remote_downloads,
)
from teddy_discovery_completion_apply import (
    CompletionSSHMutator,
)
from teddy_discovery_completion_orchestrator import (
    process_one,
)
from teddy_discovery_completion_ssh import (
    CompletionSSH,
)
from teddy_discovery_jellyfin import (
    JellyfinClient,
)
from teddy_discovery_media_jobs import (
    reconcile_media_jobs,
    run_retryable_media_jobs,
)
from teddy_discovery_media_pipeline import (
    run_media_pipeline,
)
from teddy_discovery_media_publish import (
    MediaMetadataSSHMutator,
)


CONFIRMATION = (
    "APPLY_STAGE9_COMPLETION_PIPELINE"
)


def run_once(
    *,
    items,
    db_path,
    ssh,
    mutator,
    writer_lock_path,
    apply=False,
    confirm="",
    max_items=1,
    planner=plan_remote_downloads,
    processor=process_one,
    media_processor=None,
    media_reconciler=reconcile_media_jobs,
    media_runner=run_retryable_media_jobs,
    media_max_items=1,
    media_db_path=None,
    media_writer_lock_path=None,
):
    plans = planner(
        items,
        db_path=db_path,
    )

    eligible = [
        plan
        for plan in plans
        if plan.planned_operation
        == "PLAN_STAGE9_SSH_MOVE"
    ]

    held = [
        plan
        for plan in plans
        if plan.planned_operation
        == "HOLD"
    ]

    result = {
        "total": len(plans),
        "eligible": len(eligible),
        "held": len(held),
        "applied": 0,
        "plans": [
            asdict(plan)
            for plan in plans
        ],
    }

    if not apply:
        return result

    if confirm != CONFIRMATION:
        raise RuntimeError(
            "exact confirmation required"
        )

    if max_items < 1:
        raise RuntimeError(
            "max_items must be >= 1"
        )

    for plan in eligible[:max_items]:
        processor(
            plan,
            ssh=ssh,
            mutator=mutator,
            db_path=db_path,
            writer_lock_path=
                writer_lock_path,
        )

        result["applied"] += 1

    if media_processor is not None:
        if media_db_path is None:
            raise RuntimeError(
                "media_db_path required"
            )

        if media_writer_lock_path is None:
            raise RuntimeError(
                "media_writer_lock_path required"
            )

        reconciled = media_reconciler(
            db_path,
            media_db_path,
            media_writer_lock_path,
        )

        media_result = media_runner(
            db_path=media_db_path,
            writer_lock_path=
                media_writer_lock_path,
            processor=media_processor,
            max_items=media_max_items,
        )

        result["media"] = {
            "reconciled": reconciled,
            **media_result,
        }

    return result


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--db",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--writer-lock",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--host",
        required=True,
    )
    parser.add_argument(
        "--user",
        required=True,
    )
    parser.add_argument(
        "--key",
        required=True,
    )
    parser.add_argument(
        "--known-hosts",
        required=True,
    )
    parser.add_argument(
        "--downloads-root",
        required=True,
    )
    parser.add_argument(
        "--library-root",
        required=True,
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--media-max-items",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--media-db",
        type=Path,
    )
    parser.add_argument(
        "--media-writer-lock",
        type=Path,
    )
    parser.add_argument(
        "--jellyfin-base-url",
        default="",
    )
    parser.add_argument(
        "--jellyfin-key",
        type=Path,
    )
    parser.add_argument(
        "--apply",
        action="store_true",
    )
    parser.add_argument(
        "--confirm",
        default="",
    )

    args = parser.parse_args()

    ssh = CompletionSSH(
        host=args.host,
        user=args.user,
        key=args.key,
        known_hosts=args.known_hosts,
        downloads_root=
            args.downloads_root,
        library_root=
            args.library_root,
    )

    items = ssh.list_downloads()

    media_processor = None

    if args.apply:
        if not args.jellyfin_base_url:
            parser.error(
                "--jellyfin-base-url is "
                "required with --apply"
            )

        if args.jellyfin_key is None:
            parser.error(
                "--jellyfin-key is "
                "required with --apply"
            )

        if args.media_db is None:
            parser.error(
                "--media-db is "
                "required with --apply"
            )

        if args.media_writer_lock is None:
            parser.error(
                "--media-writer-lock is "
                "required with --apply"
            )

        metadata_mutator = (
            MediaMetadataSSHMutator(
                ssh
            )
        )

        jellyfin = JellyfinClient(
            base_url=
                args.jellyfin_base_url,
            api_key_path=
                args.jellyfin_key,
        )

        def media_processor(
            dvd_id,
        ):
            return run_media_pipeline(
                db_path=args.db,
                dvd_id=dvd_id,
                ssh=ssh,
                metadata_mutator=
                    metadata_mutator,
                jellyfin=jellyfin,
            )

    result = run_once(
        items=items,
        db_path=args.db,
        ssh=ssh,
        mutator=CompletionSSHMutator(
            ssh
        ),
        writer_lock_path=
            args.writer_lock,
        apply=args.apply,
        confirm=args.confirm,
        max_items=args.max_items,
        media_processor=
            media_processor,
        media_max_items=
            args.media_max_items,
        media_db_path=
            args.media_db,
        media_writer_lock_path=
            args.media_writer_lock,
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
