from __future__ import annotations

from pathlib import Path
import sqlite3

from teddy_discovery_jellyfin import (
    jellyfin_media_path,
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

    library = (
        jellyfin.resolve_library(
            name="Adult",
            location="/media/adult",
        )
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

    media_path = (
        jellyfin_media_path(
            video_relative
        )
    )

    notify_result = (
        jellyfin.notify_created(
            media_path
        )
    )

    return {
        "status":
            "MEDIA_PIPELINE_COMPLETE",
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
    }
