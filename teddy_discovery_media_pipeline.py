from __future__ import annotations

from pathlib import Path
import sqlite3

from teddy_discovery_jellyfin import (
    jellyfin_media_path,
    validate_adult_media_path,
)
from teddy_discovery_media_jobs import (
    claim_jellyfin_created_notification,
    current_media_job_context,
    record_jellyfin_notification_status,
    record_jellyfin_visibility_pending,
)
from teddy_discovery_media_metadata import (
    build_media_bundle,
)


class MediaPipelineError(
    RuntimeError
):
    pass


def _present_holding(
    db_path: str | Path,
    dvd_id: str,
) -> dict:
    dvd_id = str(
        dvd_id or ""
    ).strip().upper()

    db = sqlite3.connect(
        "file:"
        + str(Path(db_path))
        + "?mode=ro",
        uri=True,
    )

    db.row_factory = sqlite3.Row

    try:
        rows = db.execute(
            """
            SELECT
                storage_root,
                relative_path,
                dvd_id,
                size_bytes,
                mtime_ns,
                present
            FROM holdings
            WHERE dvd_id = ?
              AND storage_root = 'jav'
              AND present = 1
            """,
            (dvd_id,),
        ).fetchall()

    finally:
        db.close()

    if len(rows) != 1:
        raise MediaPipelineError(
            "present JAV holding count != 1"
        )

    row = dict(
        rows[0]
    )

    relative = str(
        row.get(
            "relative_path"
        )
        or ""
    ).strip()

    if not relative:
        raise MediaPipelineError(
            "holding relative_path missing"
        )

    return row


def run_media_pipeline(
    *,
    db_path,
    dvd_id,
    ssh,
    metadata_mutator,
    jellyfin,
    fetcher=None,
):
    holding = _present_holding(
        db_path,
        dvd_id,
    )

    video_relative = str(
        holding["relative_path"]
    )

    remote_video = (
        ssh.stat_library(
            video_relative
        )
    )

    if remote_video is None:
        raise MediaPipelineError(
            "library video missing"
        )

    expected_size = holding.get(
        "size_bytes"
    )

    if (
        expected_size is not None
        and int(expected_size)
        != int(
            remote_video.get(
                "size",
                -1,
            )
        )
    ):
        raise MediaPipelineError(
            "holding/video size mismatch"
        )

    bundle = build_media_bundle(
        db_path,
        dvd_id,
        fetcher=fetcher,
    )

    publish_result = (
        metadata_mutator
        .publish_bundle(
            video_relative=(
                video_relative
            ),
            bundle=bundle,
        )
    )

    library = jellyfin.resolve_library(
            name="Adult",
            location="/media/adult",
        )

    item_id = str(
        library.get(
            "ItemId"
        )
        or ""
    ).strip()

    if not item_id:
        raise MediaPipelineError(
            "Adult library ItemId missing"
        )

    media_path = validate_adult_media_path(
        jellyfin_media_path(video_relative)
    ).as_posix()
    visibility = jellyfin.exact_media_visibility(media_path)
    if not isinstance(visibility, dict):
        raise MediaPipelineError("invalid Jellyfin visibility response")

    visibility_status = visibility.get("status")
    if visibility_status == "VISIBLE":
        record_jellyfin_notification_status("VISIBLE")
        notify_result = {
            "status": "JELLYFIN_ALREADY_VISIBLE",
            "item_id": visibility.get("item_id"),
        }
    elif visibility_status == "ATTENTION":
        reason = str(visibility.get("reason") or "UNKNOWN")[:500]
        record_jellyfin_notification_status("ATTENTION", reason)
        notify_result = {
            "status": "JELLYFIN_ATTENTION",
            "reason": reason,
        }
    elif visibility_status == "PENDING":
        context = current_media_job_context()
        prior_state = (
            context.get("jellyfin_notification_status", "UNKNOWN")
            if context is not None
            else "UNKNOWN"
        )
        recovery_state = (
            context.get("jellyfin_recovery_status", "UNKNOWN")
            if context is not None
            else "UNKNOWN"
        )
        if prior_state == "UNKNOWN" and recovery_state == "UNKNOWN":
            if not claim_jellyfin_created_notification():
                recovery_state = record_jellyfin_visibility_pending(
                    "CLAIM_ALREADY_CHANGED"
                )
                notify_result = {
                    "status": "JELLYFIN_RECOVERY_PENDING",
                    "recovery_status": recovery_state,
                }
            else:
                notify_result = jellyfin.notify_created(media_path)
                record_jellyfin_notification_status("NOTIFIED")
        elif prior_state in {"ATTEMPTED", "NOTIFIED"} and recovery_state in {
            "UNKNOWN", "CHECK_PENDING"
        }:
            recovery_state = record_jellyfin_visibility_pending()
            notify_result = {
                "status": (
                    "JELLYFIN_MANUAL_ACTION_REQUIRED"
                    if recovery_state == "MANUAL_ACTION_REQUIRED"
                    else "JELLYFIN_RECOVERY_PENDING"
                ),
                "recovery_status": recovery_state,
            }
        elif recovery_state == "MANUAL_ACTION_REQUIRED":
            notify_result = {
                "status": "JELLYFIN_MANUAL_ACTION_REQUIRED",
                "recovery_status": recovery_state,
            }
        elif prior_state in {"VISIBLE", "ATTENTION"} or recovery_state in {
            "VISIBLE", "ATTENTION"
        }:
            record_jellyfin_notification_status(
                "ATTENTION",
                "VISIBILITY_STATE_REGRESSION",
            )
            notify_result = {
                "status": "JELLYFIN_ATTENTION",
                "reason": "VISIBILITY_STATE_REGRESSION",
            }
        else:
            raise MediaPipelineError("inconsistent Jellyfin recovery state")
    else:
        raise MediaPipelineError("unknown Jellyfin visibility state")

    poster_result = publish_result.get("poster", {})
    poster_status = poster_result.get("status")
    if poster_status in {"CREATED", "ALREADY_PRESENT"}:
        poster_state = "COMPLETE"
        poster_error = None
    elif poster_status in {"PENDING", "FAILED", "ATTENTION"}:
        poster_state = poster_status
        poster_error = poster_result.get("error")
    elif poster_status == "NOT_ATTEMPTED":
        poster_state = bundle.poster_status
        poster_error = bundle.poster_error
    else:
        raise MediaPipelineError("invalid poster publication response")

    return {
        "status": (
            "MEDIA_PIPELINE_COMPLETE"
            if poster_state == "COMPLETE"
            else "MEDIA_PIPELINE_NFO_COMPLETE"
        ),
        "nfo_status": "COMPLETE",
        "poster_status": poster_state,
        "poster_error": poster_error,
        "dvd_id":
            str(dvd_id).upper(),
        "video_relative":
            video_relative,
        "jellyfin_path":
            media_path,
        "library_item_id":
            item_id,
        "metadata":
            publish_result,
        "jellyfin":
            notify_result,
        "jellyfin_visibility": visibility,
    }
