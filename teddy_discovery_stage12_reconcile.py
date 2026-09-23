"""Explicit read-only preflight and audited Stage12 publication reconcile."""

from __future__ import annotations

import hashlib
import sqlite3
import stat
from pathlib import Path

from teddy_discovery_stage12_batch import (
    Stage12JellyfinRecognition,
    inspect_jellyfin_external_subtitle,
)
from teddy_discovery_stage12_inventory import (
    Stage12HoldingInventoryRecord,
)
from teddy_discovery_stage12_rollout import (
    STATE_FAILED_RETRYABLE,
    Stage12PublicationReconciliationEvidence,
    Stage12RolloutStateStore,
    Stage12RolloutValidationError,
    _artifact_bundle_paths,
    _preflight_artifact_bundle,
    _publication_provenance_from_events,
    _record_video,
    _safe_artifact_root,
    _validate_publication_provenance,
)
from teddy_discovery_subtitle import (
    SubtitleCandidate,
    derive_target_ko_relative,
    validate_canonical_holding,
)


class Stage12ReconciliationError(RuntimeError):
    """Raised when current witnesses do not authorize reconciliation."""


def reconcile_failed_publication(
    *,
    dvd_id: str,
    store: Stage12RolloutStateStore,
    discovery_row,
    artifact_root: str | Path,
    nas_filesystem,
    subtitle_reader,
    jellyfin_client,
):
    """Reconcile one failed publication only after fresh exact verification.

    This explicit operation never runs Stage11, writes NAS, or refreshes
    Jellyfin.  Its only write is the final audited rollout reconciliation.
    """

    if not isinstance(store, Stage12RolloutStateStore):
        raise Stage12ReconciliationError(
            "reconciliation requires Stage12RolloutStateStore"
        )
    state = store.get(dvd_id)
    if state.dvd_id != dvd_id or state.status != STATE_FAILED_RETRYABLE:
        raise Stage12ReconciliationError(
            "only the exact FAILED_RETRYABLE title can be reconciled"
        )
    if not isinstance(discovery_row, dict):
        raise Stage12ReconciliationError(
            "current Discovery source row is required"
        )
    try:
        video = validate_canonical_holding(
            discovery_row,
            dvd_id,
        )
    except Exception as error:
        raise Stage12ReconciliationError(
            "current Discovery holding identity is invalid"
        ) from error

    if (
        discovery_row.get("storage_root") != "jav"
        or discovery_row.get("parse_status") != "MATCHED"
        or discovery_row.get("present") != 1
        or discovery_row.get("relative_path") != state.media_path_identity
        or "jav:" + video.relative_path != state.holding_identity
        or discovery_row.get("size_bytes") != state.source_size_bytes
        or discovery_row.get("mtime_ns") != state.source_mtime_ns
    ):
        raise Stage12ReconciliationError(
            "current Discovery source identity differs from rollout state"
        )

    try:
        source_stat = nas_filesystem.lstat(video.relative_path)
    except Exception as error:
        raise Stage12ReconciliationError(
            "exact NAS source identity could not be verified"
        ) from error
    if (
        not stat.S_ISREG(int(getattr(source_stat, "st_mode", 0)))
        or int(getattr(source_stat, "st_size", -1))
        != state.source_size_bytes
        or int(getattr(source_stat, "st_mtime_ns", -1))
        != state.source_mtime_ns
    ):
        raise Stage12ReconciliationError(
            "current NAS source fingerprint differs from rollout state"
        )

    record = Stage12HoldingInventoryRecord(
        dvd_id=state.dvd_id,
        holding_id=int(discovery_row["holding_id"]),
        holding_identity=state.holding_identity,
        media_path_identity=state.media_path_identity,
        source_size_bytes=state.source_size_bytes,
        source_mtime_ns=state.source_mtime_ns,
        existing_ko=state.existing_ko,
        eligibility=state.eligibility,
        reason=state.inventory_reason,
    )
    artifact_directory = _safe_artifact_root(artifact_root)
    baseline_path, clean_path, report_path = _artifact_bundle_paths(
        artifact_directory,
        dvd_id,
    )
    if (
        state.artifact_path != str(clean_path)
        or state.report_path != str(report_path)
        or state.destination_relative
        != derive_target_ko_relative(video)
    ):
        raise Stage12ReconciliationError(
            "recorded artifact/report/destination identity is not canonical"
        )
    try:
        checked_clean, checked_report, clean_sha, report_sha = (
            _preflight_artifact_bundle(record, artifact_directory)
        )
    except Exception as error:
        raise Stage12ReconciliationError(
            "existing Stage11 artifact/report provenance is invalid"
        ) from error
    if (
        checked_clean != clean_path
        or checked_report != report_path
        or clean_sha != state.artifact_sha256
        or report_sha != state.report_sha256
    ):
        raise Stage12ReconciliationError(
            "existing Stage11 artifact/report SHA differs from rollout state"
        )

    # Validate the immutable publication witness before consulting Jellyfin.
    state_path = Path(store.state_path).resolve(strict=True)
    try:
        connection = sqlite3.connect(
            state_path.as_uri() + "?mode=ro",
            uri=True,
        )
        connection.row_factory = sqlite3.Row
        try:
            events = tuple(
                connection.execute(
                    """
                    SELECT * FROM stage12_rollout_events
                    WHERE dvd_id = ?
                    ORDER BY event_id
                    """,
                    (dvd_id,),
                ).fetchall()
            )
        finally:
            connection.close()
        publication = _publication_provenance_from_events(events)
        publication = _validate_publication_provenance(
            state,
            publication,
        )
    except Exception as error:
        raise Stage12ReconciliationError(
            "immutable verified publication provenance is unavailable"
        ) from error

    destination = state.destination_relative
    try:
        destination_stat = nas_filesystem.lstat(destination)
        if not stat.S_ISREG(
            int(getattr(destination_stat, "st_mode", 0))
        ):
            raise Stage12ReconciliationError(
                "NAS destination is not a regular file"
            )
        candidate = SubtitleCandidate.sibling_text(destination)
        current_destination = subtitle_reader.read_subtitle_bytes(
            _record_video(record),
            candidate,
        )
    except Stage12ReconciliationError:
        raise
    except Exception as error:
        raise Stage12ReconciliationError(
            "exact NAS Korean sidecar could not be read safely"
        ) from error
    destination_sha = hashlib.sha256(current_destination).hexdigest()
    if (
        int(getattr(destination_stat, "st_size", -1))
        != len(current_destination)
        or destination_sha != state.artifact_sha256
        or destination_sha != publication.get("destination_sha256")
    ):
        raise Stage12ReconciliationError(
            "current NAS destination SHA differs from verified publication"
        )

    try:
        jellyfin = inspect_jellyfin_external_subtitle(
            jellyfin_client,
            video_relative=video.relative_path,
            subtitle_relative=destination,
        )
    except Exception as error:
        raise Stage12ReconciliationError(
            "exact Jellyfin item/stream could not be verified by GET"
        ) from error
    if not isinstance(jellyfin, Stage12JellyfinRecognition):
        raise Stage12ReconciliationError(
            "exact external Korean sidecar stream is not currently visible"
        )

    evidence = Stage12PublicationReconciliationEvidence(
        destination_relative=destination,
        destination_sha256=destination_sha,
        jellyfin_item_id=jellyfin.item_id,
        jellyfin_item_path=jellyfin.item_path,
        jellyfin_subtitle_path=jellyfin.subtitle_path,
        subtitle_language=jellyfin.subtitle_language,
        subtitle_codec=jellyfin.subtitle_codec,
        external_visible=jellyfin.external_visible,
        verification_passed=True,
    )
    try:
        return store.reconcile_published(
            dvd_id,
            evidence=evidence,
        )
    except Stage12RolloutValidationError as error:
        raise Stage12ReconciliationError(
            "rollout store rejected verified publication reconciliation"
        ) from error


__all__ = [
    "Stage12ReconciliationError",
    "reconcile_failed_publication",
]
