"""Small bounded Stage12 rollout orchestration around frozen Stage11 APIs.

This module owns only the bounded batch boundary.  Stage11 remains the owner
of subtitle generation and route/alignment policy; Stage12 owns selection,
durable rollout transitions, publication, and the exact Jellyfin recognition
check.  All operational dependencies are injected so the offline smoke never
contacts a provider, model, NAS, or Jellyfin server.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import hashlib
from pathlib import Path, PurePosixPath
import stat
import time
from urllib.parse import urlencode

from teddy_discovery_jellyfin import (
    JellyfinClient,
    JellyfinError,
    jellyfin_media_path,
)
from teddy_discovery_asr_audio import ASRAudioError
from teddy_discovery_stage11_controller import (
    Stage11ControllerError,
    Stage11ControllerResult,
)
from teddy_discovery_stage11_deployment import (
    Stage11DeploymentError,
)
from teddy_discovery_stateful_live_runner import (
    StatefulLiveRunnerPendingArtifactError,
    StatefulLiveRunnerTimeoutError,
    StatefulSemanticOutputValidationRetryExhausted,
)
from teddy_discovery_stage12_inventory import (
    ELIGIBLE_NEEDS_KO,
    EXISTING_KO_ABSENT,
    Stage12HoldingInventoryRecord,
    Stage12HoldingsInventoryReport,
)
from teddy_discovery_stage12_rollout import (
    STATE_FAILED_RETRYABLE,
    STATE_FAILED_TERMINAL,
    STATE_GENERATED,
    STATE_PENDING,
    STATE_PUBLISHED,
    STATE_RUNNING,
    STATE_UNRESOLVED,
    Stage12RolloutState,
    Stage12RolloutStateStore,
    Stage12RolloutValidationError,
    _preflight_artifact_bundle,
    _record_video,
)
from teddy_discovery_ko_srt import (
    GeneratedKoreanSRT,
    generate_korean_srt,
)
from teddy_discovery_subtitle import (
    CanonicalVideoHolding,
    SubtitleCandidate,
    derive_target_ko_relative,
)
from teddy_discovery_subtitle_publish import (
    SUBTITLE_PUBLISHED,
    SubtitlePublishCollisionError,
    SubtitlePublishError,
    SubtitlePublishResult,
)
from teddy_discovery_subtitle_text import (
    SubtitleTextError,
    parse_subtitle_bytes,
)


class Stage12BatchError(RuntimeError):
    """Base class for bounded Stage12 batch failures."""


class Stage12BatchTitleError(Stage12BatchError):
    """A failure isolated to one selected title."""


class Stage12BatchTerminalTitleError(Stage12BatchTitleError):
    """A title-level conflict or invalid artifact that must not be retried."""


class Stage12BatchSystemicError(Stage12BatchError):
    """A shared contract, safety, or unexpected-program failure."""


@dataclass(frozen=True)
class Stage12BatchSelection:
    """Immutable membership for one bounded serial run."""

    batch_size: int
    dvd_ids: tuple[str, ...]

    def __post_init__(self):
        if type(self.batch_size) is not int or self.batch_size <= 0:
            raise Stage12BatchSystemicError(
                "batch_size must be a positive exact integer"
            )
        if not isinstance(self.dvd_ids, tuple):
            raise Stage12BatchSystemicError(
                "dvd_ids must be an immutable tuple"
            )
        if len(self.dvd_ids) != self.batch_size:
            raise Stage12BatchSystemicError(
                "selection size does not equal requested batch bound"
            )
        if len(set(self.dvd_ids)) != len(self.dvd_ids):
            raise Stage12BatchSystemicError(
                "selection contains duplicate title identity"
            )
        for dvd_id in self.dvd_ids:
            if type(dvd_id) is not str or not dvd_id:
                raise Stage12BatchSystemicError(
                    "selection contains an invalid DVD-ID"
                )


@dataclass(frozen=True)
class Stage12JellyfinRecognition:
    """Exact item/stream proof returned by the bounded Jellyfin check."""

    item_id: str
    item_path: str
    subtitle_path: str
    subtitle_language: str
    external_visible: bool
    refresh_required: bool
    refresh_method: str

    def __post_init__(self):
        for value in (
            self.item_id,
            self.item_path,
            self.subtitle_path,
            self.subtitle_language,
            self.refresh_method,
        ):
            if type(value) is not str or not value:
                raise Stage12BatchSystemicError(
                    "Jellyfin recognition fields must be nonempty strings"
                )
        if self.external_visible is not True:
            raise Stage12BatchTitleError(
                "Jellyfin external subtitle is not visible"
            )
        if type(self.refresh_required) is not bool:
            raise Stage12BatchSystemicError(
                "Jellyfin refresh_required must be boolean"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "item_id": self.item_id,
            "item_path": self.item_path,
            "subtitle_path": self.subtitle_path,
            "subtitle_language": self.subtitle_language,
            "external_visible": self.external_visible,
            "refresh_required": self.refresh_required,
            "refresh_method": self.refresh_method,
        }


@dataclass(frozen=True)
class Stage12BatchTitleResult:
    """Durable-state-backed summary for one selected title."""

    dvd_id: str
    stage11_result: str
    route: str | None
    clean_sha256: str | None
    publication_result: str
    destination: str | None
    jellyfin_recognition: str
    final_state: str
    error: str | None = None
    jellyfin: Stage12JellyfinRecognition | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "dvd_id": self.dvd_id,
            "stage11_result": self.stage11_result,
            "route": self.route,
            "clean_sha256": self.clean_sha256,
            "publication_result": self.publication_result,
            "destination": self.destination,
            "jellyfin_recognition": self.jellyfin_recognition,
            "final_state": self.final_state,
            "error": self.error,
            "jellyfin": (
                None if self.jellyfin is None else self.jellyfin.to_dict()
            ),
        }


@dataclass(frozen=True)
class Stage12BatchResult:
    """Results in immutable selection order."""

    selection: Stage12BatchSelection
    titles: tuple[Stage12BatchTitleResult, ...]

    def __post_init__(self):
        if not isinstance(self.titles, tuple):
            raise Stage12BatchSystemicError(
                "batch titles must be an immutable tuple"
            )
        if tuple(item.dvd_id for item in self.titles) != self.selection.dvd_ids:
            raise Stage12BatchSystemicError(
                "batch result membership differs from immutable selection"
            )

    def summary(self) -> dict[str, int]:
        return {
            "selected": len(self.titles),
            "published": sum(
                item.final_state == STATE_PUBLISHED
                and item.jellyfin_recognition == "PASS"
                for item in self.titles
            ),
            "failed_retryable": sum(
                item.final_state == STATE_FAILED_RETRYABLE
                for item in self.titles
            ),
            "failed_terminal": sum(
                item.final_state == STATE_FAILED_TERMINAL
                for item in self.titles
            ),
            "skipped": sum(
                item.final_state == "SKIPPED_EXISTING_KO"
                for item in self.titles
            ),
            "unresolved": sum(
                item.final_state == "UNRESOLVED"
                for item in self.titles
            ),
        }


def select_pending_batch(
    store: Stage12RolloutStateStore,
    *,
    batch_size: int,
) -> Stage12BatchSelection:
    """Select exactly ``batch_size`` eligible PENDING titles by DVD-ID."""

    if not isinstance(store, Stage12RolloutStateStore):
        raise Stage12BatchSystemicError(
            "batch selector requires Stage12RolloutStateStore"
        )
    if type(batch_size) is not int or batch_size <= 0:
        raise Stage12BatchSystemicError(
            "batch_size must be a positive exact integer"
        )

    selected: list[str] = []
    seen: set[str] = set()
    for state in store.list_states():
        if state.status != STATE_PENDING:
            continue
        if (
            state.eligibility != ELIGIBLE_NEEDS_KO
            or state.existing_ko != EXISTING_KO_ABSENT
        ):
            continue
        if (
            not state.dvd_id
            or not state.holding_identity
            or not state.media_path_identity
            or state.holding_identity != "jav:" + state.media_path_identity
        ):
            raise Stage12BatchSystemicError(
                "PENDING state lacks canonical holding/source identity"
            )
        if state.dvd_id in seen:
            raise Stage12BatchSystemicError(
                "PENDING state contains duplicate DVD-ID"
            )
        seen.add(state.dvd_id)
        selected.append(state.dvd_id)
        if len(selected) == batch_size:
            break

    if len(selected) != batch_size:
        raise Stage12BatchTitleError(
            "fewer than requested eligible PENDING titles remain"
        )
    return Stage12BatchSelection(
        batch_size=batch_size,
        dvd_ids=tuple(selected),
    )


def _subtitle_streams(playback: object) -> list[dict[str, object]]:
    if not isinstance(playback, Mapping):
        raise Stage12BatchSystemicError(
            "Jellyfin PlaybackInfo response is not an object"
        )
    streams: list[dict[str, object]] = []
    sources = playback.get("MediaSources", [])
    if not isinstance(sources, list):
        raise Stage12BatchSystemicError(
            "Jellyfin MediaSources response is not a list"
        )
    for source in sources:
        if not isinstance(source, Mapping):
            raise Stage12BatchSystemicError(
                "Jellyfin media source is not an object"
            )
        source_path = source.get("Path")
        media_streams = source.get("MediaStreams", [])
        if not isinstance(media_streams, list):
            raise Stage12BatchSystemicError(
                "Jellyfin MediaStreams response is not a list"
            )
        for stream in media_streams:
            if not isinstance(stream, Mapping):
                continue
            if not (
                stream.get("Type") == "Subtitle"
                or stream.get("IsTextSubtitleStream")
            ):
                continue
            streams.append(
                {
                    "source_path": source_path,
                    "path": stream.get("Path"),
                    "is_external": stream.get("IsExternal"),
                    "language": stream.get("Language"),
                    "codec": stream.get("Codec"),
                    "display_title": stream.get("DisplayTitle"),
                }
            )
    return streams


def recognize_jellyfin_external_subtitle(
    client: JellyfinClient,
    *,
    video_relative: str,
    subtitle_relative: str,
    poll_interval_seconds: float = 3.0,
    max_attempts: int = 10,
) -> Stage12JellyfinRecognition:
    """Resolve one exact item and verify one exact external Korean stream.

    The initial library query is metadata-only and filters its result by the
    exact container-visible media path.  Refresh is sent only to that item and
    only when the exact subtitle stream is not already visible.
    """

    if not isinstance(client, JellyfinClient) and not callable(
        getattr(client, "_request", None)
    ):
        raise Stage12BatchSystemicError(
            "Jellyfin client lacks the existing request contract"
        )
    if type(video_relative) is not str or type(subtitle_relative) is not str:
        raise Stage12BatchSystemicError(
            "Jellyfin path inputs must be exact strings"
        )
    if type(max_attempts) is not int or max_attempts <= 0:
        raise Stage12BatchSystemicError(
            "max_attempts must be a positive exact integer"
        )
    if (
        isinstance(poll_interval_seconds, bool)
        or not isinstance(poll_interval_seconds, (int, float))
        or poll_interval_seconds < 0
    ):
        raise Stage12BatchSystemicError(
            "poll_interval_seconds must be nonnegative"
        )

    expected_item_path = jellyfin_media_path(video_relative)
    expected_subtitle_path = jellyfin_media_path(subtitle_relative)
    query = urlencode(
        {
            "Recursive": "true",
            "Fields": "Path,MediaSources,MediaStreams,ProviderIds",
            "IncludeItemTypes": "Movie,Video",
            "StartIndex": "0",
            "Limit": "1000",
        }
    )
    try:
        response = client._request("GET", "/Items?" + query)
    except JellyfinError as error:
        raise Stage12BatchSystemicError(
            "Jellyfin exact item query failed"
        ) from error
    if not isinstance(response, Mapping) or not isinstance(
        response.get("Items"), list
    ):
        raise Stage12BatchSystemicError(
            "Jellyfin exact item query response is invalid"
        )
    matches = [
        item
        for item in response["Items"]
        if isinstance(item, Mapping)
        and item.get("Path") == expected_item_path
    ]
    if len(matches) != 1:
        raise Stage12BatchTitleError(
            "Jellyfin exact media path did not resolve to one item"
        )
    item = matches[0]
    item_id = str(item.get("Id") or "").strip()
    if not item_id:
        raise Stage12BatchSystemicError(
            "Jellyfin exact item has no ItemId"
        )

    def playback_streams() -> list[dict[str, object]]:
        try:
            playback = client._request(
                "GET",
                "/Items/" + item_id + "/PlaybackInfo",
            )
        except JellyfinError as error:
            raise Stage12BatchSystemicError(
                "Jellyfin PlaybackInfo request failed"
            ) from error
        return _subtitle_streams(playback)

    def matching_stream() -> dict[str, object] | None:
        for stream in playback_streams():
            language = str(stream.get("language") or "").lower()
            stream_path = str(stream.get("path") or "")
            if (
                stream.get("source_path") == expected_item_path
                and stream.get("is_external") is True
                and language in {"ko", "kor", "korean"}
                and PurePosixPath(stream_path).name
                == PurePosixPath(expected_subtitle_path).name
                and stream_path == expected_subtitle_path
            ):
                return stream
        return None

    stream = matching_stream()
    refresh_required = stream is None
    refresh_method = "NONE_ALREADY_VISIBLE"
    if stream is None:
        refresh_query = urlencode(
            {
                "MetadataRefreshMode": "Default",
                "ImageRefreshMode": "Default",
                "ReplaceAllImages": "false",
                "ReplaceMetadata": "false",
                "RegenerateThumbnail": "false",
            }
        )
        try:
            client._request(
                "POST",
                "/Items/" + item_id + "/Refresh?" + refresh_query,
            )
        except JellyfinError as error:
            raise Stage12BatchSystemicError(
                "Jellyfin item-specific refresh failed"
            ) from error
        refresh_method = "POST /Items/{itemId}/Refresh"
        for attempt in range(max_attempts):
            stream = matching_stream()
            if stream is not None:
                break
            if attempt + 1 < max_attempts:
                time.sleep(float(poll_interval_seconds))

    if stream is None:
        full_refresh_query = urlencode(
            {
                "MetadataRefreshMode": "FullRefresh",
                "ImageRefreshMode": "Default",
                "ReplaceAllImages": "false",
                "ReplaceMetadata": "false",
                "RegenerateThumbnail": "false",
            }
        )
        try:
            client._request(
                "POST",
                "/Items/" + item_id + "/Refresh?" + full_refresh_query,
            )
        except JellyfinError as error:
            raise Stage12BatchSystemicError(
                "Jellyfin item-specific full refresh failed"
            ) from error
        refresh_method = (
            "POST /Items/{itemId}/Refresh Default->FullRefresh"
        )
        for attempt in range(max_attempts):
            stream = matching_stream()
            if stream is not None:
                break
            if attempt + 1 < max_attempts:
                time.sleep(float(poll_interval_seconds))

    if stream is None:
        raise Stage12BatchTitleError(
            "Jellyfin external Korean subtitle not recognized"
        )
    return Stage12JellyfinRecognition(
        item_id=item_id,
        item_path=expected_item_path,
        subtitle_path=str(stream["path"]),
        subtitle_language=str(stream["language"]),
        external_visible=True,
        refresh_required=refresh_required,
        refresh_method=refresh_method,
    )


def _state_record(
    state: Stage12RolloutState,
    records: Mapping[str, Stage12HoldingInventoryRecord],
) -> Stage12HoldingInventoryRecord:
    record = records.get(state.dvd_id)
    if not isinstance(record, Stage12HoldingInventoryRecord):
        raise Stage12BatchSystemicError(
            "selected title is missing from authoritative inventory"
        )
    for field_name in (
        "holding_identity",
        "media_path_identity",
        "existing_ko",
        "eligibility",
        "source_size_bytes",
        "source_mtime_ns",
    ):
        if getattr(state, field_name) != getattr(record, field_name):
            raise Stage12BatchSystemicError(
                "durable state is detached from current inventory: "
                + field_name
            )
    if state.inventory_reason != record.reason:
        raise Stage12BatchSystemicError(
            "durable state is detached from current inventory: reason"
        )
    if (
        record.eligibility != ELIGIBLE_NEEDS_KO
        or record.existing_ko != EXISTING_KO_ABSENT
    ):
        raise Stage12BatchTitleError(
            "selected title is no longer eligible for publication"
        )
    return record


def _artifact(
    clean_path: Path,
) -> GeneratedKoreanSRT:
    try:
        payload = clean_path.read_bytes()
        document = parse_subtitle_bytes(payload, "srt")
        artifact = generate_korean_srt(document.cues)
    except (OSError, SubtitleTextError) as error:
        raise Stage12BatchTitleError(
            "CLEAN artifact cannot be read or parsed"
        ) from error
    if artifact.payload != payload:
        raise Stage12BatchTitleError(
            "CLEAN artifact is not canonical"
        )
    return artifact


class Stage12BatchRunner:
    """Run one immutable selection serially with title-level isolation."""

    def __init__(
        self,
        *,
        store: Stage12RolloutStateStore,
        inventory: Stage12HoldingsInventoryReport | Mapping[str, Stage12HoldingInventoryRecord],
        artifact_root: str | Path,
        nas_filesystem: object,
        subtitle_reader: object,
        publisher: object,
        controller_runner: Callable[[str], Stage11ControllerResult],
        jellyfin_recognizer: Callable[
            [str, CanonicalVideoHolding, str], Stage12JellyfinRecognition
        ],
    ):
        if not isinstance(store, Stage12RolloutStateStore):
            raise Stage12BatchSystemicError("invalid rollout state store")
        if isinstance(inventory, Stage12HoldingsInventoryReport):
            records = {
                record.dvd_id: record
                for record in inventory.records
                if record.dvd_id is not None
            }
            if len(records) != len(inventory.records):
                raise Stage12BatchSystemicError(
                    "inventory contains a missing DVD-ID"
                )
        elif isinstance(inventory, Mapping):
            records = dict(inventory)
        else:
            raise Stage12BatchSystemicError("invalid inventory input")
        for dvd_id, record in records.items():
            if not isinstance(record, Stage12HoldingInventoryRecord):
                raise Stage12BatchSystemicError(
                    "inventory contains an invalid record"
                )
            if dvd_id != record.dvd_id:
                raise Stage12BatchSystemicError(
                    "inventory mapping key is detached from DVD-ID"
                )
        root = Path(artifact_root)
        try:
            info = root.lstat()
        except OSError as error:
            raise Stage12BatchSystemicError(
                "artifact root cannot be inspected"
            ) from error
        if not stat.S_ISDIR(info.st_mode) or root.is_symlink():
            raise Stage12BatchSystemicError(
                "artifact root must be an existing non-symlink directory"
            )
        if not callable(controller_runner):
            raise Stage12BatchSystemicError("controller_runner must be callable")
        if not callable(jellyfin_recognizer):
            raise Stage12BatchSystemicError(
                "jellyfin_recognizer must be callable"
            )
        if not callable(getattr(nas_filesystem, "lstat", None)):
            raise Stage12BatchSystemicError(
                "NAS filesystem must expose exact read-only lstat"
            )
        if not callable(getattr(subtitle_reader, "read_subtitle_bytes", None)):
            raise Stage12BatchSystemicError(
                "subtitle reader must expose exact read-only bytes read"
            )
        if not callable(getattr(publisher, "publish_korean_srt", None)):
            raise Stage12BatchSystemicError(
                "publisher must expose the existing publication API"
            )
        self.store = store
        self.records = records
        self.artifact_root = root
        self.nas_filesystem = nas_filesystem
        self.subtitle_reader = subtitle_reader
        self.publisher = publisher
        self.controller_runner = controller_runner
        self.jellyfin_recognizer = jellyfin_recognizer

    def _fail_title(
        self,
        state: Stage12RolloutState,
        *,
        error: Exception,
        terminal: bool,
        destination: str | None,
        stage11_result: str,
        route: str | None,
        clean_sha256: str | None,
        publication_result: str,
        jellyfin_recognition: str,
    ) -> Stage12BatchTitleResult:
        semantic_retry_exhausted = isinstance(
            error,
            StatefulSemanticOutputValidationRetryExhausted,
        )
        hermes_timeout = isinstance(
            error,
            StatefulLiveRunnerTimeoutError,
        )
        if semantic_retry_exhausted or hermes_timeout:
            terminal = False
        to_status = STATE_FAILED_TERMINAL if terminal else STATE_FAILED_RETRYABLE
        if state.status == STATE_PENDING and terminal:
            # The frozen state machine deliberately has no direct
            # PENDING -> FAILED_TERMINAL edge.  A destination conflict found
            # after selection is a conservative terminal decision, so retain
            # it as durable UNRESOLVED rather than making it retryable.
            to_status = STATE_UNRESOLVED
        failure_provenance = {
            "operation": "STAGE12_SERIAL_BATCH",
            "error_type": type(error).__name__,
            "error": str(error),
            "retry_performed": (
                error.attempts > 1
                if semantic_retry_exhausted
                else False
            ),
            "destination": destination,
        }
        transition_reason = "STAGE12_TITLE_FAILURE"
        if semantic_retry_exhausted:
            transition_reason = (
                "STAGE12_SEMANTIC_OUTPUT_VALIDATION_RETRY_EXHAUSTED"
            )
            failure_provenance[
                "semantic_output_validation_retry"
            ] = {
                "part_index": error.part_index,
                "attempts": error.attempts,
                "max_attempts": error.max_attempts,
            }
        elif hermes_timeout:
            transition_reason = "STAGE12_HERMES_PART_TIMEOUT"
            failure_provenance["hermes_timeout"] = {
                "timeout_seconds": error.timeout_seconds,
                "timeout_reason": error.timeout_reason,
                "configured_inactivity_timeout_seconds": (
                    error.inactivity_timeout_seconds
                ),
                "configured_absolute_timeout_seconds": (
                    error.absolute_timeout_seconds
                ),
                "invocation_elapsed_seconds": (
                    error.invocation_elapsed_seconds
                ),
                "seconds_since_last_output_activity": (
                    error.seconds_since_last_output_activity
                ),
            }
        if publication_result == "PASS":
            if clean_sha256 is None or destination is None:
                raise Stage12BatchSystemicError(
                    "successful publication failure lacks durable identity"
                )
            failure_provenance["publication_provenance"] = {
                "publication_performed": True,
                "atomic_install": True,
                "destination_verified": True,
                "destination_relative": destination,
                "destination_sha256": clean_sha256,
            }
        failure_state = self.store.transition(
            state.dvd_id,
            to_status,
            expected_from=state.status,
            reason=transition_reason,
            provenance=failure_provenance,
            destination_relative=destination,
        )
        return Stage12BatchTitleResult(
            dvd_id=state.dvd_id,
            stage11_result=stage11_result,
            route=route,
            clean_sha256=clean_sha256,
            publication_result=publication_result,
            destination=destination,
            jellyfin_recognition=jellyfin_recognition,
            final_state=failure_state.status,
            error=type(error).__name__ + ": " + str(error),
        )

    @staticmethod
    def _is_title_exception(error: Exception) -> bool:
        return isinstance(
            error,
            (
                Stage12BatchTitleError,
                Stage11ControllerError,
                ASRAudioError,
                StatefulSemanticOutputValidationRetryExhausted,
                StatefulLiveRunnerPendingArtifactError,
                StatefulLiveRunnerTimeoutError,
            ),
        )

    def _run_one(self, dvd_id: str) -> Stage12BatchTitleResult:
        state = self.store.get(dvd_id)
        if state.status != STATE_PENDING:
            raise Stage12BatchSystemicError(
                "immutable batch title is no longer PENDING: " + dvd_id
            )
        record = _state_record(state, self.records)
        video = _record_video(record)
        destination = derive_target_ko_relative(video)

        try:
            source_stat = self.nas_filesystem.lstat(video.relative_path)
            if (
                not stat.S_ISREG(int(getattr(source_stat, "st_mode", 0)))
                or int(getattr(source_stat, "st_size", -1))
                != record.source_size_bytes
                or int(getattr(source_stat, "st_mtime_ns", -1))
                != record.source_mtime_ns
            ):
                raise Stage12BatchTitleError("source snapshot mismatch")
            try:
                self.nas_filesystem.lstat(destination)
            except FileNotFoundError:
                pass
            else:
                raise Stage12BatchTerminalTitleError(
                    "canonical KO destination already exists"
                )
        except Stage12BatchTitleError as error:
            return self._fail_title(
                state,
                error=error,
                terminal=isinstance(error, Stage12BatchTerminalTitleError),
                destination=destination,
                stage11_result="NOT_RUN",
                route=None,
                clean_sha256=None,
                publication_result="BLOCKED",
                jellyfin_recognition="NOT_RUN",
            )
        except (FileNotFoundError, OSError) as error:
            title_error = Stage12BatchTitleError(
                "exact NAS preflight failed: " + type(error).__name__
            )
            return self._fail_title(
                state,
                error=title_error,
                terminal=False,
                destination=destination,
                stage11_result="NOT_RUN",
                route=None,
                clean_sha256=None,
                publication_result="BLOCKED",
                jellyfin_recognition="NOT_RUN",
            )

        running = self.store.transition(
            dvd_id,
            STATE_RUNNING,
            expected_from=STATE_PENDING,
            reason="STAGE12_BATCH_START",
            provenance={
                "operation": "STAGE12_SERIAL_BATCH",
                "batch_membership": "immutable-selection",
                "retry_performed": False,
            },
        )
        try:
            controller_result = self.controller_runner(dvd_id)
        except Stage11DeploymentError as error:
            raise Stage12BatchSystemicError(
                "Stage11 deployment boundary failed: " + str(error)
            ) from error
        except Stage12BatchSystemicError:
            raise
        except Exception as error:
            if not self._is_title_exception(error):
                raise Stage12BatchSystemicError(
                    "unexpected Stage11 title execution exception"
                ) from error
            return self._fail_title(
                running,
                error=error,
                terminal=isinstance(error, Stage11ControllerError),
                destination=destination,
                stage11_result="FAIL",
                route=None,
                clean_sha256=None,
                publication_result="NOT_RUN",
                jellyfin_recognition="NOT_RUN",
            )

        if not isinstance(controller_result, Stage11ControllerResult):
            raise Stage12BatchSystemicError(
                "Stage11 controller returned an invalid result"
            )
        try:
            clean_path, report_path, clean_sha, report_sha = (
                _preflight_artifact_bundle(
                    record,
                    self.artifact_root,
                )
            )
        except Exception as error:
            title_error = Stage12BatchTitleError(
                "Stage11 artifact/report preflight failed: "
                + type(error).__name__
            )
            return self._fail_title(
                running,
                error=title_error,
                terminal=True,
                destination=destination,
                stage11_result="FAIL",
                route=controller_result.route,
                clean_sha256=None,
                publication_result="BLOCKED",
                jellyfin_recognition="NOT_RUN",
            )
        if (
            controller_result.clean_path != clean_path
            or controller_result.clean_sha256 != clean_sha
            or controller_result.report_path != report_path
            or controller_result.report_sha256 != report_sha
        ):
            title_error = Stage12BatchTitleError(
                "Stage11 result is detached from validated artifact/report"
            )
            return self._fail_title(
                running,
                error=title_error,
                terminal=True,
                destination=destination,
                stage11_result="FAIL",
                route=controller_result.route,
                clean_sha256=clean_sha,
                publication_result="BLOCKED",
                jellyfin_recognition="NOT_RUN",
            )

        generated = self.store.transition(
            dvd_id,
            STATE_GENERATED,
            expected_from=STATE_RUNNING,
            reason="STAGE12_ARTIFACTS_VALIDATED",
            provenance={
                "operation": "STAGE12_SERIAL_BATCH",
                "stage11_result": "PASS",
                "route": controller_result.route,
                "external_ja_outcome": controller_result.external_ja_outcome,
                "alignment_outcome": controller_result.alignment_outcome,
                "retry_performed": False,
            },
            artifact_path=str(clean_path),
            artifact_sha256=clean_sha,
            report_path=str(report_path),
            report_sha256=report_sha,
        )
        try:
            artifact = _artifact(clean_path)
            if artifact.sha256 != clean_sha:
                raise Stage12BatchTitleError(
                    "CLEAN artifact SHA changed after preflight"
                )
            try:
                self.nas_filesystem.lstat(destination)
            except FileNotFoundError:
                pass
            else:
                raise Stage12BatchTerminalTitleError(
                    "canonical KO destination appeared before publication"
                )
            publish_result = self.publisher.publish_korean_srt(
                canonical_video=video,
                artifact=artifact,
                target_relative=destination,
            )
            if not isinstance(publish_result, SubtitlePublishResult):
                raise Stage12BatchSystemicError(
                    "publisher returned an invalid result"
                )
            if (
                publish_result.state != SUBTITLE_PUBLISHED
                or publish_result.sha256 != clean_sha
            ):
                raise Stage12BatchTerminalTitleError(
                    "publication did not create the expected artifact"
                )
            destination_payload = self.subtitle_reader.read_subtitle_bytes(
                video,
                SubtitleCandidate.sibling_text(destination),
            )
            destination_document = parse_subtitle_bytes(
                destination_payload,
                "srt",
            )
            if generate_korean_srt(destination_document.cues).payload != destination_payload:
                raise Stage12BatchTitleError(
                    "published destination is not canonical SRT"
                )
            if hashlib.sha256(destination_payload).hexdigest() != clean_sha:
                raise Stage12BatchTitleError(
                    "published destination SHA differs from CLEAN"
                )
            destination_stat = self.nas_filesystem.lstat(destination)
            if (
                not stat.S_ISREG(int(getattr(destination_stat, "st_mode", 0)))
                or int(getattr(destination_stat, "st_size", -1))
                != len(destination_payload)
            ):
                raise Stage12BatchTitleError(
                    "published destination regular-file readback failed"
                )
            source_after = self.nas_filesystem.lstat(video.relative_path)
            if (
                not stat.S_ISREG(int(getattr(source_after, "st_mode", 0)))
                or int(getattr(source_after, "st_size", -1))
                != record.source_size_bytes
                or int(getattr(source_after, "st_mtime_ns", -1))
                != record.source_mtime_ns
            ):
                raise Stage12BatchTitleError(
                    "source snapshot changed during publication"
                )
        except Stage12BatchSystemicError:
            raise
        except SubtitlePublishCollisionError as error:
            return self._fail_title(
                generated,
                error=error,
                terminal=True,
                destination=destination,
                stage11_result="PASS",
                route=controller_result.route,
                clean_sha256=clean_sha,
                publication_result="CONFLICT",
                jellyfin_recognition="NOT_RUN",
            )
        except (SubtitlePublishError, Stage12BatchTitleError, OSError, SubtitleTextError) as error:
            return self._fail_title(
                generated,
                error=error,
                terminal=isinstance(error, Stage12BatchTerminalTitleError),
                destination=destination,
                stage11_result="PASS",
                route=controller_result.route,
                clean_sha256=clean_sha,
                publication_result="FAIL",
                jellyfin_recognition="NOT_RUN",
            )

        try:
            jellyfin = self.jellyfin_recognizer(
                dvd_id,
                video,
                destination,
            )
            if not isinstance(jellyfin, Stage12JellyfinRecognition):
                raise Stage12BatchSystemicError(
                    "Jellyfin recognizer returned an invalid result"
                )
            expected_item_path = jellyfin_media_path(video.relative_path)
            expected_subtitle_path = jellyfin_media_path(destination)
            if (
                jellyfin.item_path != expected_item_path
                or jellyfin.subtitle_path != expected_subtitle_path
                or jellyfin.subtitle_language.lower()
                not in {"ko", "kor", "korean"}
                or jellyfin.external_visible is not True
            ):
                raise Stage12BatchTitleError(
                    "Jellyfin recognition is detached from canonical title paths"
                )
        except Stage12BatchSystemicError:
            raise
        except Exception as error:
            if not self._is_title_exception(error):
                raise Stage12BatchSystemicError(
                    "unexpected Jellyfin title recognition exception"
                ) from error
            return self._fail_title(
                generated,
                error=error,
                terminal=False,
                destination=destination,
                stage11_result="PASS",
                route=controller_result.route,
                clean_sha256=clean_sha,
                publication_result="PASS",
                jellyfin_recognition="FAIL",
            )

        published = self.store.transition(
            dvd_id,
            STATE_PUBLISHED,
            expected_from=STATE_GENERATED,
            reason="STAGE12_PUBLICATION_AND_JELLYFIN_VERIFIED",
            provenance={
                "operation": "STAGE12_SERIAL_BATCH",
                "publication_performed": True,
                "atomic_install": True,
                "destination_verified": True,
                "destination_relative": destination,
                "destination_sha256": clean_sha,
                "jellyfin_recognition": jellyfin.to_dict(),
                "retry_performed": False,
            },
            destination_relative=destination,
        )
        return Stage12BatchTitleResult(
            dvd_id=dvd_id,
            stage11_result="PASS",
            route=controller_result.route,
            clean_sha256=clean_sha,
            publication_result="PASS",
            destination=destination,
            jellyfin_recognition="PASS",
            final_state=published.status,
            jellyfin=jellyfin,
        )

    def run(self, selection: Stage12BatchSelection) -> Stage12BatchResult:
        if not isinstance(selection, Stage12BatchSelection):
            raise Stage12BatchSystemicError("invalid immutable batch selection")
        titles = tuple(
            self._run_one(dvd_id)
            for dvd_id in selection.dvd_ids
        )
        return Stage12BatchResult(selection=selection, titles=titles)


__all__ = [
    "Stage12BatchError",
    "Stage12BatchResult",
    "Stage12BatchRunner",
    "Stage12BatchSelection",
    "Stage12BatchSystemicError",
    "Stage12BatchTerminalTitleError",
    "Stage12BatchTitleError",
    "Stage12BatchTitleResult",
    "Stage12JellyfinRecognition",
    "select_pending_batch",
    "recognize_jellyfin_external_subtitle",
]
