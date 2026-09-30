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
from teddy_discovery_completion_metadata import (
    DEFAULT_METADATA_RECOVERY_MAX_ITEMS,
    recover_held_metadata,
)
from teddy_discovery_completion_ssh import (
    CompletionSSH,
)
from teddy_discovery_jellyfin import (
    JellyfinClient,
)
from teddy_discovery_media_jobs import (
    normalize_media_target_dvd_id,
    reconcile_media_jobs,
    run_retryable_media_jobs,
)
from teddy_discovery_media_metadata import (
    make_poster_fetcher,
)
from teddy_discovery_media_pipeline import (
    run_media_pipeline,
)
from teddy_discovery_jellyfin_visibility import (
    reconcile_jellyfin_visibility,
)
from teddy_discovery_media_publish import (
    MediaMetadataSSHMutator,
)
from teddy_discovery_operation_lock import (
    DEFAULT_OPERATION_LOCK_PATH,
    OperationLockError,
)


CONFIRMATION = (
    "APPLY_STAGE9_COMPLETION_PIPELINE"
)


def _make_media_processor(
    *,
    db_path,
    ssh,
    metadata_mutator,
    jellyfin,
    poster_fetcher,
):
    def media_processor(
        dvd_id,
    ):
        return run_media_pipeline(
            db_path=db_path,
            dvd_id=dvd_id,
            ssh=ssh,
            metadata_mutator=
                metadata_mutator,
            jellyfin=jellyfin,
            fetcher=poster_fetcher,
        )

    return media_processor


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
    jellyfin_visibility_reconciler=reconcile_jellyfin_visibility,
    jellyfin_client=None,
    media_max_items=1,
    jellyfin_visibility_max_items=5,
    media_db_path=None,
    media_writer_lock_path=None,
    media_target_dvd_id=None,
    media_only=False,
    operation_lock_path=DEFAULT_OPERATION_LOCK_PATH,
    metadata_recovery_max_items=(
        DEFAULT_METADATA_RECOVERY_MAX_ITEMS
    ),
    metadata_state_path=None,
    metadata_collector=None,
    metadata_applier=None,
):
    target_dvd_id = (
        normalize_media_target_dvd_id(
            media_target_dvd_id
        )
        if media_target_dvd_id is not None
        else None
    )

    if target_dvd_id is not None and not apply:
        raise RuntimeError(
            "exact media target requires apply"
        )
    if target_dvd_id is not None and media_processor is None:
        raise RuntimeError(
            "exact media target requires media processor"
        )

    if media_only:
        if not apply:
            raise RuntimeError(
                "media-only mode requires apply"
            )
        if target_dvd_id is None:
            raise RuntimeError(
                "media-only mode requires exact target DVD-ID"
            )
        if int(media_max_items) != 1:
            raise RuntimeError(
                "media-only mode requires media_max_items=1"
            )
        plans = []
    else:
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
        "operation_lock_skipped": 0,
        "plans": [
            asdict(plan)
            for plan in plans
        ],
    }

    if media_only:
        result["media_only"] = True
        result["organizer_status"] = "SKIPPED_MEDIA_ONLY"
        result["metadata_recovery"] = {
            "status": "SKIPPED_MEDIA_ONLY",
            "attempted": 0,
        }

    if not apply:
        result["metadata_recovery"] = (
            recover_held_metadata(
                plans,
                db_path=db_path,
                writer_lock_path=writer_lock_path,
                apply=False,
                max_items=
                    metadata_recovery_max_items,
                state_path=metadata_state_path,
            )
        )
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
        try:
            processor(
                plan,
                ssh=ssh,
                mutator=mutator,
                db_path=db_path,
                writer_lock_path=
                    writer_lock_path,
                operation_lock_path=
                    operation_lock_path,
            )

        except OperationLockError:
            result["operation_lock"] = "BUSY_OR_UNAVAILABLE"
            result["operation_lock_skipped"] += 1
            break

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

        if media_only:
            reconciled = None
        else:
            reconciled = media_reconciler(
                db_path,
                media_db_path,
                media_writer_lock_path,
            )

        media_runner_kwargs = {
            "db_path": media_db_path,
            "discovery_db_path": db_path,
            "writer_lock_path": media_writer_lock_path,
            "processor": media_processor,
            "max_items": media_max_items,
        }
        if target_dvd_id is not None:
            media_runner_kwargs[
                "target_dvd_id"
            ] = target_dvd_id
        media_result = media_runner(
            **media_runner_kwargs
        )

        visibility_result = None
        if jellyfin_client is not None:
            visibility_result = jellyfin_visibility_reconciler(
                db_path,
                media_db_path,
                media_writer_lock_path,
                jellyfin_client,
                max_items=jellyfin_visibility_max_items,
                target_dvd_id=target_dvd_id,
            )

        result["media"] = {
            "reconciled": reconciled,
            **media_result,
            "jellyfin_visibility": visibility_result,
        }

    if media_only:
        return result

    recovery_kwargs = {}

    if metadata_collector is not None:
        recovery_kwargs[
            "collector"
        ] = metadata_collector

    if metadata_applier is not None:
        recovery_kwargs[
            "applier"
        ] = metadata_applier

    result["metadata_recovery"] = (
        recover_held_metadata(
            plans,
            db_path=db_path,
            writer_lock_path=writer_lock_path,
            apply=True,
            max_items=(
                metadata_recovery_max_items
            ),
            state_path=metadata_state_path,
            **recovery_kwargs,
        )
    )

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
        "--operation-lock",
        type=Path,
        default=DEFAULT_OPERATION_LOCK_PATH,
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
        "--metadata-recovery-max-items",
        type=int,
        default=(
            DEFAULT_METADATA_RECOVERY_MAX_ITEMS
        ),
    )
    parser.add_argument(
        "--metadata-recovery-state-db",
        type=Path,
    )
    parser.add_argument(
        "--media-max-items",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--jellyfin-visibility-max-items",
        type=int,
        default=5,
        help="maximum completed media titles to check by Jellyfin GET per run",
    )
    parser.add_argument(
        "--media-target-dvd-id",
        help="exact canonical DVD-ID for the media job selector",
    )
    parser.add_argument(
        "--media-only",
        action="store_true",
        help=(
            "run only the media job stage; requires --apply "
            "and --media-target-dvd-id"
        ),
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
        "--media-poster-proxy-url",
        help=(
            "optional loopback HTTP proxy used only "
            "for poster fetches"
        ),
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

    try:
        if args.media_target_dvd_id is not None:
            args.media_target_dvd_id = (
                normalize_media_target_dvd_id(
                    args.media_target_dvd_id
                )
            )
    except ValueError as exc:
        parser.error(str(exc))

    if args.media_target_dvd_id is not None and not args.apply:
        parser.error(
            "--media-target-dvd-id requires --apply"
        )
    if not 1 <= args.jellyfin_visibility_max_items <= 1000:
        parser.error(
            "--jellyfin-visibility-max-items must be between 1 and 1000"
        )
    if args.media_only:
        if not args.apply:
            parser.error(
                "--media-only requires --apply"
            )
        if args.media_target_dvd_id is None:
            parser.error(
                "--media-only requires --media-target-dvd-id"
            )
        if args.media_max_items != 1:
            parser.error(
                "--media-only requires --media-max-items 1"
            )
        if args.media_db is None:
            parser.error(
                "--media-only requires --media-db"
            )
        if args.media_writer_lock is None:
            parser.error(
                "--media-only requires --media-writer-lock"
            )
        if not args.media_poster_proxy_url:
            parser.error(
                "--media-only requires --media-poster-proxy-url"
            )
        if not args.jellyfin_base_url or args.jellyfin_key is None:
            parser.error(
                "--media-only requires Jellyfin configuration"
            )

    try:
        poster_fetcher = make_poster_fetcher(
            args.media_poster_proxy_url
        )
    except ValueError as exc:
        parser.error(str(exc))

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

    items = (
        []
        if args.media_only
        else ssh.list_downloads()
    )

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

        media_processor = _make_media_processor(
            db_path=args.db,
            ssh=ssh,
            metadata_mutator=metadata_mutator,
            jellyfin=jellyfin,
            poster_fetcher=poster_fetcher,
        )

    result = run_once(
        items=items,
        db_path=args.db,
        ssh=ssh,
        mutator=(
            None
            if args.media_only
            else CompletionSSHMutator(ssh)
        ),
        writer_lock_path=
            args.writer_lock,
        operation_lock_path=
            args.operation_lock,
        apply=args.apply,
        confirm=args.confirm,
        max_items=args.max_items,
        metadata_recovery_max_items=(
            args.metadata_recovery_max_items
        ),
        metadata_state_path=(
            args.metadata_recovery_state_db
        ),
        media_processor=
            media_processor,
        media_max_items=
            args.media_max_items,
        jellyfin_visibility_max_items=(
            args.jellyfin_visibility_max_items
        ),
        media_db_path=
            args.media_db,
        media_writer_lock_path=
            args.media_writer_lock,
        media_target_dvd_id=
            args.media_target_dvd_id,
        media_only=args.media_only,
        jellyfin_client=(
            jellyfin if args.apply else None
        ),
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
