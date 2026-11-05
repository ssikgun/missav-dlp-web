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


def _metadata_cover_url(db_path, dvd_id):
    """Read the exact title record without changing Discovery."""
    db = sqlite3.connect('file:' + str(Path(db_path).resolve()) + '?mode=ro', uri=True)
    try:
        db.execute('PRAGMA query_only=ON')
        row = db.execute('SELECT cover_url FROM titles WHERE dvd_id=?',
                         (dvd_id,)).fetchone()
    finally:
        db.close()
    if not row:
        raise MediaPipelineError('metadata not found')
    return row[0]


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


def run_existing_image_only(*, db_path, dvd_id, file_station, fetcher, title_lock_dir,
                            path_verifier=None, poster_fetcher=None, max_items=1):
    """Process one known holding without changing or creating a media job.

    The caller must supply a current, trustworthy regular-file/path verifier;
    FileStation's isdir flag alone cannot establish POSIX link safety.
    """
    from teddy_discovery_media_metadata import _normalize_dvd_id
    from teddy_title_exclusion import ACQUIRED, try_acquire_title_lock
    try:
        dvd_id = _normalize_dvd_id(dvd_id)
        if type(max_items) is not int or max_items != 1 or not callable(path_verifier):
            return {'status': 'ATTENTION', 'error': 'PATH_VERIFICATION_REQUIRED'}
        if getattr(file_station, 'image_only', False) is not True:
            return {'status': 'ATTENTION', 'error': 'IMAGE_ONLY_ADAPTER_REQUIRED'}
        lock = try_acquire_title_lock(dvd_id, lock_dir=title_lock_dir)
        if lock.status != ACQUIRED:
            return {'status': 'ATTENTION', 'error': 'TITLE_LOCK_UNAVAILABLE'}
        with lock:
            holding = _present_holding(db_path, dvd_id)
            if path_verifier(dvd_id, dict(holding)) is not True:
                return {'status': 'ATTENTION', 'error': 'PATH_VERIFICATION_REQUIRED'}
            class CheckedStorage:
                def __getattr__(self, name):
                    return getattr(file_station, name)
                def _check(self):
                    if _present_holding(db_path, dvd_id) != holding or path_verifier(dvd_id, dict(holding)) is not True:
                        raise MediaPipelineError('PATH_RECHECK_FAILED')
                def create_poster(self, **kwargs):
                    self._check()
                    return file_station.create_poster(**kwargs)
                def create_thumbnail(self, **kwargs):
                    self._check()
                    return file_station.create_thumbnail(**kwargs)
            return run_thumbnail_processor(db_path=db_path, dvd_id=dvd_id,
                file_station=CheckedStorage(), fetcher=fetcher, poster_fetcher=poster_fetcher)
    except Exception:
        return {'status': 'ATTENTION', 'error': 'THUMBNAIL_TARGET_OR_STORAGE_UNCERTAIN'}


def run_thumbnail_processor(*, db_path, dvd_id, file_station, fetcher, poster_fetcher=None):
    """Thumbnail-only operation for injection into the existing job manager."""
    from teddy_discovery_media_metadata import _normalize_dvd_id
    try:
        dvd_id = _normalize_dvd_id(dvd_id)
        holding = _present_holding(db_path, dvd_id)
        relative = str(holding['relative_path'])
        expected_size = holding.get('size_bytes')
        if type(expected_size) is not int or expected_size <= 0:
            return {'status': 'ATTENTION', 'error': 'HOLDING_SIZE_UNKNOWN'}
        video = file_station.stat_library(relative)
        if not isinstance(video, dict) or video.get('size') != expected_size:
            return {'status': 'ATTENTION', 'error': 'VIDEO_SIZE_OR_IDENTITY_UNCERTAIN'}
        poster_exists = file_station.thumbnail_poster_exists(dvd_id=dvd_id, video_relative=relative)
        if poster_exists is True:
            return {'status': 'SKIPPED'}
        if poster_exists is not False:
            return {'status': 'ATTENTION', 'error': 'POSTER_STATUS_UNKNOWN'}
        cover_url = _metadata_cover_url(db_path, dvd_id)
        if cover_url:
            from teddy_discovery_cover import _validated_cover_url, CoverValidationError
            from teddy_discovery_media_metadata import fetch_poster
            from urllib.error import HTTPError, URLError
            poster = None
            try:
                _validated_cover_url(cover_url)
                if not callable(poster_fetcher):
                    return {'status': 'ATTENTION', 'error': 'THUMBNAIL_TARGET_OR_STORAGE_UNCERTAIN'}
                poster = fetch_poster(cover_url, fetcher=poster_fetcher)
                mime = poster.content_type.split(';', 1)[0].strip().lower()
                body = poster.data
                valid = ((mime == 'image/jpeg' and body.startswith(b'\xff\xd8\xff') and body.endswith(b'\xff\xd9') and poster.filename == 'poster.jpg') or
                         (mime == 'image/png' and body.startswith(b'\x89PNG\r\n\x1a\n') and poster.filename == 'poster.png') or
                         (mime == 'image/webp' and len(body) >= 12 and body[:4] == b'RIFF' and body[8:12] == b'WEBP' and poster.filename == 'poster.webp'))
                if not valid:
                    return {'status': 'ATTENTION', 'error': 'THUMBNAIL_TARGET_OR_STORAGE_UNCERTAIN'}
            except HTTPError as exc:
                if 300 <= exc.code < 400:
                    return {'status': 'ATTENTION', 'error': 'THUMBNAIL_TARGET_OR_STORAGE_UNCERTAIN'}
            except (URLError, TimeoutError, ConnectionError):
                pass
            except (CoverValidationError, ValueError, TypeError):
                return {'status': 'ATTENTION', 'error': 'THUMBNAIL_TARGET_OR_STORAGE_UNCERTAIN'}
            if poster is not None:
                saved = file_station.create_poster(dvd_id=dvd_id, video_relative=relative, poster=poster)
                if saved.get('status') == 'CREATED':
                    return {'status': 'COMPLETE'}
                if saved.get('status') == 'POSTER_PRESENT':
                    return {'status': 'SKIPPED'}
                return {'status': 'ATTENTION', 'error': 'THUMBNAIL_TARGET_OR_STORAGE_UNCERTAIN'}
        from teddy_discovery_media_thumbnail import store_candidate_thumbnail
        try:
            result = store_candidate_thumbnail(dvd_id=dvd_id, video_relative=relative,
                fetcher=fetcher, file_station=file_station,
                official_poster_verified=False)
        except (ValueError, OSError):
            return {'status': 'PENDING', 'error': 'THUMBNAIL_SOURCE_UNVERIFIED'}
        if result.get('status') == 'CREATED':
            return {'status': 'COMPLETE'}
        if result.get('status') == 'POSTER_PRESENT':
            return {'status': 'SKIPPED'}
        if result.get('error') in {'CANDIDATE_RESPONSE_INVALID', 'CANDIDATE_MIME_MISMATCH',
                                   'CANDIDATE_SIZE_MISMATCH', 'CANDIDATE_REDIRECT_REJECTED',
                                   'CANDIDATE_SHA256_MISMATCH', 'CANDIDATE_TARGET_MISMATCH'}:
            return {'status': 'ATTENTION', 'error': result['error']}
        return {'status': 'PENDING', 'error': 'THUMBNAIL_SOURCE_UNVERIFIED'}
    except Exception:
        return {'status': 'ATTENTION', 'error': 'THUMBNAIL_TARGET_OR_STORAGE_UNCERTAIN'}


def run_media_pipeline(
    *,
    db_path,
    dvd_id,
    ssh,
    metadata_mutator,
    jellyfin,
    fetcher=None,
    image_processor=None,
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
        defer_poster=image_processor is not None,
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

    if image_processor is not None:
        nfo_result = publish_result.get('nfo', {})
        if nfo_result.get('status') not in {'CREATED', 'ALREADY_PRESENT'}:
            raise MediaPipelineError('NFO publication was not verified')
        image = image_processor(dvd_id)
        image_status = image.get('status') if isinstance(image, dict) else None
        if image_status == 'COMPLETE':
            publish_result['poster'] = {'status': 'CREATED'}
        elif image_status == 'SKIPPED':
            publish_result['poster'] = {'status': 'ALREADY_PRESENT'}
        elif image_status in {'PENDING', 'ATTENTION'}:
            publish_result['poster'] = {'status': image_status, 'error': image.get('error')}
        else:
            raise MediaPipelineError('invalid image processor response')

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
