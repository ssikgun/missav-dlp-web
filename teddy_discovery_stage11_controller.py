"""Thin, generic one-title Stage11 orchestration through CLEAN plus report.

The controller composes existing source, ASR, alignment, source-quality,
targeted-evidence, stateful translation/review, and CLEAN materialization
boundaries.  All model/session transports are injected.  This module has no
publisher dependency and performs no NAS, Jellyfin, or Stage11 job-DB work.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Final

from teddy_discovery_alignment_acceptance import (
    ACCEPT_HYBRID,
    REJECT_EXTERNAL,
    UNRESOLVED,
)
from teddy_discovery_alignment_application import (
    AlignmentAcceptanceApplicationResult,
)
from teddy_discovery_asr import ASRResult, ASRSourceSnapshot
from teddy_discovery_asr_artifact import (
    MAX_ASR_ARTIFACT_BYTES,
    parse_asr_result_bytes,
    persist_asr_result,
    require_matching_asr_source,
    serialize_asr_result,
)
from teddy_discovery_asr_source_quality import (
    ASR_SOURCE_KEEP,
    ASR_SOURCE_OMIT,
    ASR_SOURCE_REQUIRE_SECOND_EVIDENCE,
    classify_asr_result_source_quality,
)
from teddy_discovery_availability import canonical_dvd_id
from teddy_discovery_hybrid_evidence import (
    ALIGNMENT_PROVENANCE_ASR_ONLY,
    HybridCueIdentity,
    HybridAlignmentProvenance,
    HybridEvidenceBundle,
)
from teddy_discovery_ko_srt import (
    GENERATED_SRT_READY,
    GeneratedKoreanSRT,
    generate_korean_srt,
)
from teddy_discovery_organizer import load_db_state
from teddy_discovery_stateful_asr import (
    build_stateful_asr_package,
    prepare_stateful_asr_package,
)
from teddy_discovery_stateful_asr_quality_review import (
    asr_quality_review_request_sha256,
    build_asr_prefilter_provenance,
    build_asr_quality_review_request,
    serialize_asr_quality_review_result,
    validate_asr_quality_review_result,
)
from teddy_discovery_stateful_asr_quality_review_clean import (
    materialize_stateful_asr_quality_review_clean,
)
from teddy_discovery_stateful_hybrid import prepare_stateful_hybrid
from teddy_discovery_stateful_quality_review import (
    build_review_request,
    review_request_sha256,
    serialize_review_result,
    validate_review_result,
)
from teddy_discovery_stateful_quality_review_clean import (
    materialize_stateful_quality_review_clean,
)
from teddy_discovery_stateful_policy import (
    DEFAULT_STATEFUL_SEMANTIC_POLICY,
    STATEFUL_SEMANTIC_POLICY_16,
    StatefulSemanticPolicy,
    StatefulSemanticPolicyError,
    bind_stateful_policy_generation_key,
    resolve_stateful_semantic_policy,
)
from teddy_discovery_stateful_translator import (
    StatefulSubtitleResult,
    serialize_stateful_result,
    validate_stateful_result,
)
from teddy_discovery_subtitle import (
    CanonicalVideoHolding,
    validate_canonical_holding,
)
from teddy_discovery_subtitle_external import (
    ExternalSubtitleTransportError,
    ExternalSubtitleValidationError,
    SubtitleCatDetailError,
)
from teddy_discovery_subtitle_source_quality import classify_source_document
from teddy_discovery_subtitle_text import (
    MAX_SUBTITLE_BYTES,
    parse_subtitle_bytes,
)
from teddy_discovery_subtitle_v2_orchestrator import (
    V2_READY_FOR_SEMANTIC,
    V2_ROUTE_ASR_ONLY,
    V2_ROUTE_HYBRID,
    SubtitleV2RouteDecision,
    project_affine_timestamp_ms,
)
from teddy_discovery_subtitle_v2_pipeline import build_asr_only_cue_sequence
from teddy_discovery_subtitlecat_discovery import (
    SubtitleCatSearchError,
    SubtitleCatSearchTransportError,
)
from teddy_discovery_targeted_asr_window import (
    STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1,
)
from teddy_discovery_targeted_hybrid_evidence import (
    TargetedASRBinding,
    TargetedASRWindowEvidence,
    build_targeted_asr_bindings,
)
from teddy_discovery_targeted_second_evidence import (
    build_targeted_second_evidence_plan_with_policy,
)
from teddy_discovery_targeted_second_evidence_artifact import (
    MAX_TARGETED_SECOND_EVIDENCE_ARTIFACT_BYTES,
    TargetedSecondEvidenceArtifact,
    parse_targeted_second_evidence_artifact_bytes,
    persist_targeted_second_evidence,
    require_matching_targeted_second_evidence_context,
    serialize_targeted_second_evidence_artifact,
)
from teddy_discovery_targeted_second_evidence_projection import (
    project_targeted_second_evidence_artifact,
)
from teddy_discovery_targeted_second_evidence_runner import (
    TargetedSecondEvidenceExecution,
)


BASELINE_ASR_FILENAME: Final[str] = "baseline-asr-v1.json"
TARGETED_SECOND_EVIDENCE_FILENAME: Final[str] = (
    "targeted-second-evidence-v1.json"
)
CLEAN_SRT_FILENAME: Final[str] = "clean-ko-v1.srt"
MECHANICAL_REPORT_FILENAME: Final[str] = "stage11-controller-report-v1.json"
STAGE11_CONTROLLER_FILE_MODE: Final[int] = 0o600
STAGE11_CONTROLLER_DIRECTORY_MODE: Final[int] = 0o700
MAX_STAGE11_REPORT_BYTES: Final[int] = 1024 * 1024

EXTERNAL_JA_NO_CANDIDATE: Final[str] = "NO_CANDIDATE"
EXTERNAL_JA_ACCEPTED: Final[str] = "ACCEPTED"
EXTERNAL_JA_SEARCH_TRANSPORT_FAILURE: Final[str] = (
    "SEARCH_TRANSPORT_FAILURE"
)
EXTERNAL_JA_TRANSPORT_FAILURE: Final[str] = "TRANSPORT_FAILURE"
EXTERNAL_JA_VALIDATION_FAILURE: Final[str] = "VALIDATION_FAILURE"
ALIGNMENT_NOT_ATTEMPTED: Final[str] = "NOT_ATTEMPTED"

_REPORT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "title",
        "route",
        "baseline_artifact_path",
        "baseline_sha256",
        "baseline_reused",
        "external_ja_outcome",
        "alignment_outcome",
        "source_quality_counts",
        "targeted_source_count",
        "targeted_window_count",
        "targeted_reused",
        "translation_result_identity",
        "review_result_identity",
        "clean_artifact_path",
        "clean_sha256",
        "publication_performed",
    }
)
_SOURCE_QUALITY_ACTIONS: Final[tuple[str, ...]] = (
    ASR_SOURCE_KEEP,
    ASR_SOURCE_REQUIRE_SECOND_EVIDENCE,
    ASR_SOURCE_OMIT,
)
_EXTERNAL_OUTCOMES: Final[frozenset[str]] = frozenset(
    {
        EXTERNAL_JA_NO_CANDIDATE,
        EXTERNAL_JA_ACCEPTED,
        EXTERNAL_JA_SEARCH_TRANSPORT_FAILURE,
        EXTERNAL_JA_TRANSPORT_FAILURE,
        EXTERNAL_JA_VALIDATION_FAILURE,
    }
)


class Stage11ControllerError(RuntimeError):
    """Base class for one-title controller failures."""


class Stage11ControllerValidationError(Stage11ControllerError):
    """Caller input or injected component output is invalid."""


class Stage11ControllerArtifactError(Stage11ControllerError):
    """A durable artifact is malformed, detached, or unsafe."""


class Stage11ControllerTargetedEvidenceUnprojectable(Stage11ControllerError):
    """Validated targeted evidence cannot be projected completely into HYBRID."""


@dataclass(frozen=True)
class Stage11ControllerResult:
    """Small completion result; it intentionally contains no publish state."""

    title: str
    route: str
    clean_path: Path
    clean_sha256: str
    report_path: Path
    report_sha256: str
    baseline_reused: bool
    targeted_reused: bool | None
    clean_reused: bool
    report_reused: bool
    external_ja_outcome: str
    alignment_outcome: str

    def __post_init__(self):
        _canonical_title(self.title)
        if self.route not in {V2_ROUTE_ASR_ONLY, V2_ROUTE_HYBRID}:
            raise Stage11ControllerValidationError(
                "controller result route is invalid"
            )
        for path in (self.clean_path, self.report_path):
            if not isinstance(path, Path) or not path.is_absolute():
                raise Stage11ControllerValidationError(
                    "controller result paths must be absolute Path values"
                )
        for digest in (self.clean_sha256, self.report_sha256):
            _require_sha256(digest, field_name="controller result SHA256")
        if type(self.baseline_reused) is not bool:
            raise Stage11ControllerValidationError(
                "baseline_reused must be boolean"
            )
        if self.targeted_reused is not None and type(self.targeted_reused) is not bool:
            raise Stage11ControllerValidationError(
                "targeted_reused must be boolean or None"
            )
        if type(self.clean_reused) is not bool or type(self.report_reused) is not bool:
            raise Stage11ControllerValidationError(
                "CLEAN/report reuse values must be boolean"
            )
        if self.external_ja_outcome not in _EXTERNAL_OUTCOMES:
            raise Stage11ControllerValidationError(
                "external JA outcome is invalid"
            )
        if self.alignment_outcome not in {
            ALIGNMENT_NOT_ATTEMPTED,
            ACCEPT_HYBRID,
            REJECT_EXTERNAL,
            UNRESOLVED,
        }:
            raise Stage11ControllerValidationError(
                "alignment outcome is invalid"
            )
        if (
            self.route == V2_ROUTE_ASR_ONLY
            and self.alignment_outcome == ACCEPT_HYBRID
            and self.external_ja_outcome != EXTERNAL_JA_ACCEPTED
        ):
            raise Stage11ControllerValidationError(
                "ASR-only accepted-alignment result lacks accepted external evidence"
            )


def _canonical_title(value: object) -> str:
    if type(value) is not str:
        raise Stage11ControllerValidationError(
            "TITLE must be an exact canonical DVD-ID string"
        )
    try:
        canonical = canonical_dvd_id(value)
    except ValueError as error:
        raise Stage11ControllerValidationError(
            "TITLE must be a canonical DVD-ID"
        ) from error
    if value != canonical:
        raise Stage11ControllerValidationError(
            "TITLE must use the exact canonical DVD-ID spelling"
        )
    return canonical


def _require_sha256(value: object, *, field_name: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise Stage11ControllerArtifactError(
            field_name + " must be lowercase SHA256"
        )
    return value


def _lstat_or_none(path: Path):
    try:
        return os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise Stage11ControllerArtifactError(
            "artifact path could not be inspected"
        ) from error


def _validate_root(path_value: object, *, field_name: str) -> Path:
    try:
        path = Path(path_value)
    except (TypeError, ValueError) as error:
        raise Stage11ControllerValidationError(
            field_name + " is invalid"
        ) from error
    if not path.is_absolute() or path == Path("/"):
        raise Stage11ControllerValidationError(
            field_name + " must be an explicit absolute directory"
        )
    info = _lstat_or_none(path)
    if info is None or not stat.S_ISDIR(info.st_mode):
        raise Stage11ControllerValidationError(
            field_name + " must already exist as a directory"
        )
    return path


def _title_directory(artifact_root: Path, title: str) -> Path:
    path = artifact_root / title
    info = _lstat_or_none(path)
    if info is None:
        try:
            os.mkdir(path, STAGE11_CONTROLLER_DIRECTORY_MODE)
            os.chmod(path, STAGE11_CONTROLLER_DIRECTORY_MODE)
        except FileExistsError:
            pass
        except OSError as error:
            raise Stage11ControllerArtifactError(
                "title artifact directory could not be created"
            ) from error
        info = _lstat_or_none(path)
    if (
        info is None
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != STAGE11_CONTROLLER_DIRECTORY_MODE
    ):
        raise Stage11ControllerArtifactError(
            "title artifact directory must be owned, regular, and mode 0700"
        )
    return path


def _read_private_file(path: Path, *, max_bytes: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise Stage11ControllerArtifactError(
            "artifact cannot be opened safely"
        ) from error
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != STAGE11_CONTROLLER_FILE_MODE
            or info.st_nlink != 1
            or info.st_size <= 0
            or info.st_size > max_bytes
        ):
            raise Stage11ControllerArtifactError(
                "artifact must be a bounded owned regular 0600 file"
            )
        payload = os.read(descriptor, max_bytes + 1)
        if not payload or len(payload) > max_bytes or len(payload) != info.st_size:
            raise Stage11ControllerArtifactError(
                "artifact read differs from its bounded file identity"
            )
        return payload
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
    except OSError as error:
        raise Stage11ControllerArtifactError(
            "artifact directory could not be opened for durability"
        ) from error
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _install_or_reuse(path: Path, payload: bytes, *, max_bytes: int) -> bool:
    if type(payload) is not bytes or not payload or len(payload) > max_bytes:
        raise Stage11ControllerArtifactError(
            "durable artifact payload is invalid or oversized"
        )
    if _lstat_or_none(path) is not None:
        if _read_private_file(path, max_bytes=max_bytes) != payload:
            raise Stage11ControllerArtifactError(
                "existing artifact conflicts and cannot be overwritten"
            )
        return True

    descriptor: int | None = None
    temporary_name: str | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".stage11-controller-",
            dir=str(path.parent),
        )
        os.fchmod(descriptor, STAGE11_CONTROLLER_FILE_MODE)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary_name, path, follow_symlinks=False)
        except FileExistsError as error:
            raise Stage11ControllerArtifactError(
                "artifact destination appeared and cannot be overwritten"
            ) from error
        _fsync_directory(path.parent)
        os.unlink(temporary_name)
        temporary_name = None
        _fsync_directory(path.parent)
    except Stage11ControllerError:
        raise
    except OSError as error:
        raise Stage11ControllerArtifactError(
            "durable artifact installation failed"
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            except OSError:
                pass

    if _read_private_file(path, max_bytes=max_bytes) != payload:
        raise Stage11ControllerArtifactError(
            "durable artifact readback differs from written bytes"
        )
    return False


def _configured_holding(title: str) -> Mapping[str, object]:
    # The production application remains the config owner.  Import it only
    # when the native resolver is selected so injected offline runs do not
    # acquire the Flask application dependency.
    from teddy_discovery_runtime import configured_db_path

    db_path = configured_db_path()
    if not db_path:
        raise Stage11ControllerValidationError(
            "TEDDY_DISCOVERY_DB is not configured"
        )
    state = load_db_state(Path(db_path))
    holdings = state.get("holdings")
    if type(holdings) is not list:
        raise Stage11ControllerValidationError(
            "Discovery holdings state is invalid"
        )
    matches = [
        holding
        for holding in holdings
        if isinstance(holding, Mapping) and holding.get("dvd_id") == title
    ]
    if len(matches) != 1:
        raise Stage11ControllerValidationError(
            "canonical holding was not found uniquely"
        )
    return matches[0]


def _resolve_holding(
    title: str,
    holding_resolver: Callable[[str], Mapping[str, object]] | None,
) -> tuple[CanonicalVideoHolding, ASRSourceSnapshot]:
    resolver = _configured_holding if holding_resolver is None else holding_resolver
    if not callable(resolver):
        raise Stage11ControllerValidationError(
            "holding_resolver must be callable"
        )
    holding = resolver(title)
    if not isinstance(holding, Mapping):
        raise Stage11ControllerValidationError(
            "holding resolver returned an invalid value"
        )
    canonical = validate_canonical_holding(holding, title)
    source_size = holding.get("size_bytes")
    source_mtime_ns = holding.get("mtime_ns")
    if type(source_size) is not int or source_size <= 0:
        raise Stage11ControllerValidationError(
            "canonical holding source size is invalid"
        )
    if type(source_mtime_ns) is not int or source_mtime_ns < 0:
        raise Stage11ControllerValidationError(
            "canonical holding source mtime is invalid"
        )
    snapshot = ASRSourceSnapshot.from_holding(
        canonical,
        source_size=source_size,
        source_mtime_ns=source_mtime_ns,
    )
    return canonical, snapshot


def _dispatch_baseline(
    path: Path,
    *,
    canonical_video: CanonicalVideoHolding,
    source_snapshot: ASRSourceSnapshot,
    baseline_transcriber: Callable[[CanonicalVideoHolding], ASRResult],
    allow_create: bool,
) -> tuple[ASRResult, bytes, bool]:
    if _lstat_or_none(path) is not None:
        raw = _read_private_file(path, max_bytes=MAX_ASR_ARTIFACT_BYTES)
        result = parse_asr_result_bytes(raw)
        require_matching_asr_source(result, source_snapshot)
        if serialize_asr_result(result) != raw:
            raise Stage11ControllerArtifactError(
                "existing baseline ASR artifact is not canonical"
            )
        return result, raw, True

    if not allow_create:
        raise Stage11ControllerArtifactError(
            "completion report exists but baseline artifact is absent"
        )
    if not callable(baseline_transcriber):
        raise Stage11ControllerValidationError(
            "baseline_transcriber must be callable"
        )
    result = baseline_transcriber(canonical_video)
    if type(result) is not ASRResult:
        raise Stage11ControllerValidationError(
            "baseline transcriber returned an invalid result"
        )
    result.__post_init__()
    if result.source_snapshot != source_snapshot:
        raise Stage11ControllerValidationError(
            "generated baseline ASR source snapshot is detached"
        )
    expected = serialize_asr_result(result)
    persist_asr_result(path, result)
    raw = _read_private_file(path, max_bytes=MAX_ASR_ARTIFACT_BYTES)
    parsed = parse_asr_result_bytes(raw)
    require_matching_asr_source(parsed, source_snapshot)
    if raw != expected or parsed != result:
        raise Stage11ControllerArtifactError(
            "persisted baseline ASR artifact failed exact readback"
        )
    return parsed, raw, False


def _source_quality_counts(decisions) -> dict[str, int]:
    counts = Counter(decision.action for decision in decisions)
    return {action: counts.get(action, 0) for action in _SOURCE_QUALITY_ACTIONS}


def _validate_targeted_artifact(
    artifact: TargetedSecondEvidenceArtifact,
    *,
    asr_result: ASRResult,
    baseline_sha256: str,
    expected_plan,
    require_indexes: tuple[int, ...],
) -> TargetedSecondEvidenceArtifact:
    require_matching_targeted_second_evidence_context(
        artifact,
        source_snapshot=asr_result.source_snapshot,
        baseline_asr_artifact_sha256=baseline_sha256,
        policy_version=(
            STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1.version
        ),
    )
    if artifact.plan != expected_plan:
        raise Stage11ControllerArtifactError(
            "targeted artifact plan differs from current V1 plan"
        )
    project_targeted_second_evidence_artifact(
        artifact,
        asr_result=asr_result,
        require_source_indexes=require_indexes,
    )
    return artifact


def _build_hybrid_targeted_bindings(
    route: SubtitleV2RouteDecision,
    targeted_artifact: TargetedSecondEvidenceArtifact | None,
) -> tuple[TargetedASRBinding, ...]:
    """Attach validated ASR-first windows to generic HYBRID semantics.

    The durable Stage11 artifact is ASR-source-first, while the existing
    Hybrid binding builder consumes external-JA window identities.  This
    adapter only supplies the external cue IDs whose accepted affine intervals
    are fully contained by each already-validated ASR window.  Candidate
    selection, residual ownership, ambiguity, and one-to-one matching remain
    exclusively in ``build_targeted_asr_bindings``.
    """

    if targeted_artifact is None:
        return ()
    if type(targeted_artifact) is not TargetedSecondEvidenceArtifact:
        raise Stage11ControllerArtifactError(
            "HYBRID targeted artifact has an invalid exact type"
        )

    application = route.alignment_application
    if application is None:
        raise Stage11ControllerArtifactError(
            "HYBRID route has no accepted alignment application"
        )
    bundle = application.bundle
    document = bundle.external_ja_document
    if document is None:
        raise Stage11ControllerArtifactError(
            "HYBRID route has no external JA document for targeted evidence"
        )
    if targeted_artifact.source_snapshot != bundle.asr_result.source_snapshot:
        raise Stage11ControllerArtifactError(
            "HYBRID targeted artifact source snapshot is detached"
        )

    try:
        results_by_window_id = {
            result.window_id: result
            for result in targeted_artifact.results
        }
        if len(results_by_window_id) != len(targeted_artifact.results):
            raise Stage11ControllerArtifactError(
                "HYBRID targeted artifact has duplicate window results"
            )

        bindings = []
        external_cues = tuple(document.cues)
        for window in targeted_artifact.windows:
            result = results_by_window_id.get(window.window_id)
            if result is None:
                raise Stage11ControllerArtifactError(
                    "HYBRID targeted artifact is missing a window result"
                )
            external_cue_ids = tuple(
                HybridCueIdentity.for_external_ja(external_index).cue_id
                for external_index, cue in enumerate(external_cues)
                if (
                    window.start_ms
                    <= project_affine_timestamp_ms(
                        application.alignment,
                        cue.start_ms,
                    )
                    and project_affine_timestamp_ms(
                        application.alignment,
                        cue.end_ms,
                    )
                    <= window.end_ms
                )
            )
            if not external_cue_ids:
                continue
            evidence = TargetedASRWindowEvidence(
                source_snapshot=targeted_artifact.source_snapshot,
                window_start_ms=window.start_ms,
                window_end_ms=window.end_ms,
                external_cue_ids=external_cue_ids,
                segments=result.segments,
            )
            bindings.extend(
                build_targeted_asr_bindings(
                    external_cues,
                    application.alignment,
                    evidence,
                )
            )
        return tuple(bindings)
    except Stage11ControllerArtifactError:
        raise
    except Exception as error:
        raise Stage11ControllerArtifactError(
            "HYBRID targeted artifact binding construction failed"
        ) from error


def _validate_complete_hybrid_targeted_projection(
    targeted_artifact: TargetedSecondEvidenceArtifact | None,
    preparation,
) -> None:
    """Require every validated target source to survive Hybrid semantic binding.

    ``build_targeted_asr_bindings`` remains the only timing association
    authority.  This check only compares its resulting semantic evidence with
    the already validated artifact bindings using the same immutable window,
    source-snapshot, and segment identity that the review boundary consumes.
    It therefore rejects an incomplete or ambiguous projection without
    inventing an association or weakening the review guard.
    """

    if targeted_artifact is None:
        return

    artifact_bindings = tuple(targeted_artifact.bindings)
    targeted_semantic_bindings = tuple(
        binding
        for binding in preparation.semantic_bindings
        if binding.targeted_asr_evidence is not None
    )
    mapped_source_ids = []
    for semantic_binding in targeted_semantic_bindings:
        evidence = semantic_binding.targeted_asr_evidence.evidence
        candidates = tuple(
            artifact_binding
            for artifact_binding in artifact_bindings
            if (
                artifact_binding.window.start_ms == evidence.window_start_ms
                and artifact_binding.window.end_ms == evidence.window_end_ms
                and artifact_binding.result.source_snapshot
                == evidence.source_snapshot
                and artifact_binding.result.segments == evidence.segments
            )
        )
        if len(candidates) != 1:
            raise Stage11ControllerTargetedEvidenceUnprojectable(
                "validated targeted evidence is not uniquely projectable into Hybrid"
            )
        mapped_source_ids.append(candidates[0].source_id)

    artifact_source_ids = tuple(
        artifact_binding.source_id for artifact_binding in artifact_bindings
    )
    if (
        len(mapped_source_ids) != len(artifact_source_ids)
        or len(set(mapped_source_ids)) != len(mapped_source_ids)
        or set(mapped_source_ids) != set(artifact_source_ids)
    ):
        raise Stage11ControllerTargetedEvidenceUnprojectable(
            "validated targeted evidence is not completely projectable into Hybrid"
        )


def _dispatch_targeted(
    path: Path,
    *,
    asr_result: ASRResult,
    source_quality_decisions,
    baseline_sha256: str,
    targeted_runner: Callable | None,
    allow_create: bool,
) -> tuple[TargetedSecondEvidenceArtifact | None, bool | None, int, int]:
    plan = build_targeted_second_evidence_plan_with_policy(
        asr_result,
        source_quality_decisions,
        policy=STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1,
    )
    require_indexes = tuple(source.source_index for source in plan.sources)
    if not require_indexes:
        if _lstat_or_none(path) is not None:
            raise Stage11ControllerArtifactError(
                "targeted artifact exists without current REQUIRE sources"
            )
        return None, None, 0, 0

    if _lstat_or_none(path) is not None:
        raw = _read_private_file(
            path,
            max_bytes=MAX_TARGETED_SECOND_EVIDENCE_ARTIFACT_BYTES,
        )
        artifact = parse_targeted_second_evidence_artifact_bytes(raw)
        if serialize_targeted_second_evidence_artifact(artifact) != raw:
            raise Stage11ControllerArtifactError(
                "existing targeted artifact is not canonical"
            )
        artifact = _validate_targeted_artifact(
            artifact,
            asr_result=asr_result,
            baseline_sha256=baseline_sha256,
            expected_plan=plan,
            require_indexes=require_indexes,
        )
        return artifact, True, len(plan.sources), len(plan.windows)

    if not allow_create:
        raise Stage11ControllerArtifactError(
            "completion report exists but targeted artifact is absent"
        )
    if not callable(targeted_runner):
        raise Stage11ControllerValidationError(
            "REQUIRE sources need an injected targeted runner"
        )
    execution = targeted_runner(asr_result, source_quality_decisions)
    if type(execution) is not TargetedSecondEvidenceExecution:
        raise Stage11ControllerValidationError(
            "targeted runner returned an invalid execution"
        )
    execution.__post_init__()
    if (
        execution.plan != plan
        or execution.policy_version
        != STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1.version
    ):
        raise Stage11ControllerValidationError(
            "targeted execution differs from the current V1 plan"
        )
    persist_targeted_second_evidence(
        path,
        execution,
        baseline_asr_artifact_sha256=baseline_sha256,
        runtime_identity=asr_result.runtime_identity,
        engine_version=asr_result.engine_version,
    )
    raw = _read_private_file(
        path,
        max_bytes=MAX_TARGETED_SECOND_EVIDENCE_ARTIFACT_BYTES,
    )
    artifact = parse_targeted_second_evidence_artifact_bytes(raw)
    artifact = _validate_targeted_artifact(
        artifact,
        asr_result=asr_result,
        baseline_sha256=baseline_sha256,
        expected_plan=plan,
        require_indexes=require_indexes,
    )
    return artifact, False, len(plan.sources), len(plan.windows)


def _direct_asr_route(
    canonical_video: CanonicalVideoHolding,
    asr_result: ASRResult,
    *,
    method: str,
    confidence: float | None = None,
) -> SubtitleV2RouteDecision:
    bundle = HybridEvidenceBundle.from_asr_only(
        dvd_id=canonical_video.dvd_id,
        asr_result=asr_result,
        alignment=HybridAlignmentProvenance(
            provenance=ALIGNMENT_PROVENANCE_ASR_ONLY,
            method=method,
            confidence=confidence,
        ),
    )
    return SubtitleV2RouteDecision(
        canonical_video=canonical_video,
        route=V2_ROUTE_ASR_ONLY,
        state=V2_READY_FOR_SEMANTIC,
        evidence_bundle=bundle,
    )


def _select_route(
    canonical_video: CanonicalVideoHolding,
    asr_result: ASRResult,
    external_ja_attempt: Callable,
) -> tuple[SubtitleV2RouteDecision, str, str]:
    if not callable(external_ja_attempt):
        raise Stage11ControllerValidationError(
            "external_ja_attempt must be callable"
        )
    try:
        application = external_ja_attempt(canonical_video, asr_result)
    except SubtitleCatSearchTransportError:
        return (
            _direct_asr_route(
                canonical_video,
                asr_result,
                method="external-ja-search-unavailable",
            ),
            EXTERNAL_JA_SEARCH_TRANSPORT_FAILURE,
            ALIGNMENT_NOT_ATTEMPTED,
        )
    except ExternalSubtitleTransportError:
        return (
            _direct_asr_route(
                canonical_video,
                asr_result,
                method="external-ja-transport-unavailable",
            ),
            EXTERNAL_JA_TRANSPORT_FAILURE,
            ALIGNMENT_NOT_ATTEMPTED,
        )
    except (
        SubtitleCatDetailError,
        SubtitleCatSearchError,
        ExternalSubtitleValidationError,
    ):
        return (
            _direct_asr_route(
                canonical_video,
                asr_result,
                method="external-ja-validation-failed",
            ),
            EXTERNAL_JA_VALIDATION_FAILURE,
            ALIGNMENT_NOT_ATTEMPTED,
        )

    if application is None:
        return (
            _direct_asr_route(
                canonical_video,
                asr_result,
                method="external-ja-no-candidate",
            ),
            EXTERNAL_JA_NO_CANDIDATE,
            ALIGNMENT_NOT_ATTEMPTED,
        )
    if type(application) is not AlignmentAcceptanceApplicationResult:
        raise Stage11ControllerValidationError(
            "external JA attempt returned an invalid application"
        )
    application.__post_init__()
    if (
        application.bundle.dvd_id != canonical_video.dvd_id
        or application.bundle.asr_result != asr_result
    ):
        raise Stage11ControllerValidationError(
            "external alignment application is detached from baseline ASR"
        )

    verdict = application.decision.verdict
    if verdict == ACCEPT_HYBRID:
        return (
            SubtitleV2RouteDecision(
                canonical_video=canonical_video,
                route=V2_ROUTE_HYBRID,
                state=V2_READY_FOR_SEMANTIC,
                alignment_application=application,
            ),
            EXTERNAL_JA_ACCEPTED,
            verdict,
        )
    if verdict == REJECT_EXTERNAL:
        return (
            SubtitleV2RouteDecision(
                canonical_video=canonical_video,
                route=V2_ROUTE_ASR_ONLY,
                state=V2_READY_FOR_SEMANTIC,
                alignment_application=application,
            ),
            EXTERNAL_JA_ACCEPTED,
            verdict,
        )
    if verdict == UNRESOLVED:
        # Preserve the immutable verdict/application for reporting.  Only the
        # controller route falls back to a newly validated ASR-only bundle.
        return (
            _direct_asr_route(
                canonical_video,
                asr_result,
                method=application.bundle.alignment.method,
                confidence=application.bundle.alignment.confidence,
            ),
            EXTERNAL_JA_ACCEPTED,
            verdict,
        )
    raise Stage11ControllerValidationError(
        "external alignment verdict is unsupported"
    )


def _serialize_report(report: Mapping[str, object]) -> bytes:
    if not isinstance(report, Mapping) or set(report) != _REPORT_FIELDS:
        raise Stage11ControllerArtifactError(
            "mechanical report fields are not exact"
        )
    try:
        payload = json.dumps(
            dict(report),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        raise Stage11ControllerArtifactError(
            "mechanical report cannot be serialized"
        ) from error
    if not payload or len(payload) > MAX_STAGE11_REPORT_BYTES:
        raise Stage11ControllerArtifactError(
            "mechanical report exceeds its byte bound"
        )
    return payload


def _parse_report(payload: bytes) -> dict[str, object]:
    try:
        report = json.loads(payload.decode("utf-8"))
    except (UnicodeError, ValueError) as error:
        raise Stage11ControllerArtifactError(
            "mechanical report is not valid UTF-8 JSON"
        ) from error
    if type(report) is not dict or set(report) != _REPORT_FIELDS:
        raise Stage11ControllerArtifactError(
            "mechanical report fields are not exact"
        )
    if _serialize_report(report) != payload:
        raise Stage11ControllerArtifactError(
            "mechanical report is not canonical JSON"
        )
    return report


def _validate_identity(value: object, *, review: bool) -> None:
    expected = (
        {
            "request_sha256",
            "result_sha256",
            "source_translation_session_id",
            "review_execution_session_id",
        }
        if review
        else {"session_id", "sha256"}
    )
    if type(value) is not dict or set(value) != expected:
        raise Stage11ControllerArtifactError(
            "result identity fields are not exact"
        )
    for key, item in value.items():
        if key.endswith("sha256"):
            _require_sha256(item, field_name="result identity SHA256")
        elif item is not None and (type(item) is not str or not item):
            raise Stage11ControllerArtifactError(
                "result session identity is invalid"
            )


def _validate_existing_completion(
    report_path: Path,
    clean_path: Path,
    baseline_path: Path,
    *,
    title: str,
    baseline_sha256: str,
    baseline_reused: bool,
    source_quality_counts: dict[str, int],
    targeted_reused: bool | None,
    targeted_source_count: int,
    targeted_window_count: int,
) -> Stage11ControllerResult:
    report_raw = _read_private_file(
        report_path,
        max_bytes=MAX_STAGE11_REPORT_BYTES,
    )
    report = _parse_report(report_raw)
    if (
        report["title"] != title
        or report["baseline_artifact_path"] != str(baseline_path)
        or report["baseline_sha256"] != baseline_sha256
        or report["source_quality_counts"] != source_quality_counts
        or report["targeted_source_count"] != targeted_source_count
        or report["targeted_window_count"] != targeted_window_count
        or report["clean_artifact_path"] != str(clean_path)
        or report["publication_performed"] is not False
    ):
        raise Stage11ControllerArtifactError(
            "existing completion report is detached from current source"
        )
    if type(report["baseline_reused"]) is not bool:
        raise Stage11ControllerArtifactError(
            "report baseline reuse value is invalid"
        )
    expected_targeted_value = (
        "not_applicable" if targeted_reused is None else report["targeted_reused"]
    )
    if targeted_reused is None:
        if report["targeted_reused"] != expected_targeted_value:
            raise Stage11ControllerArtifactError(
                "report targeted reuse value is invalid"
            )
    elif type(report["targeted_reused"]) is not bool:
        raise Stage11ControllerArtifactError(
            "report targeted reuse value is invalid"
        )
    route = report["route"]
    external_outcome = report["external_ja_outcome"]
    alignment_outcome = report["alignment_outcome"]
    if route not in {V2_ROUTE_ASR_ONLY, V2_ROUTE_HYBRID}:
        raise Stage11ControllerArtifactError("report route is invalid")
    if external_outcome not in _EXTERNAL_OUTCOMES:
        raise Stage11ControllerArtifactError(
            "report external JA outcome is invalid"
        )
    if route == V2_ROUTE_HYBRID:
        if (
            external_outcome != EXTERNAL_JA_ACCEPTED
            or alignment_outcome != ACCEPT_HYBRID
        ):
            raise Stage11ControllerArtifactError(
                "Hybrid report lacks accepted alignment evidence"
            )
    elif alignment_outcome not in {
        ALIGNMENT_NOT_ATTEMPTED,
        ACCEPT_HYBRID,
        REJECT_EXTERNAL,
        UNRESOLVED,
    }:
        raise Stage11ControllerArtifactError(
            "ASR-only report alignment outcome is invalid"
        )
    if (
        alignment_outcome == ACCEPT_HYBRID
        and external_outcome != EXTERNAL_JA_ACCEPTED
    ):
        raise Stage11ControllerArtifactError(
            "ASR-only accepted-alignment report lacks accepted external evidence"
        )
    _validate_identity(report["translation_result_identity"], review=False)
    _validate_identity(report["review_result_identity"], review=True)
    clean_raw = _read_private_file(clean_path, max_bytes=MAX_SUBTITLE_BYTES)
    clean_sha = hashlib.sha256(clean_raw).hexdigest()
    if report["clean_sha256"] != clean_sha:
        raise Stage11ControllerArtifactError(
            "existing CLEAN bytes differ from completion report"
        )
    document = parse_subtitle_bytes(clean_raw, "srt")
    regenerated = generate_korean_srt(document.cues)
    if regenerated.payload != clean_raw:
        raise Stage11ControllerArtifactError(
            "existing CLEAN SRT is not canonical"
        )
    return Stage11ControllerResult(
        title=title,
        route=route,
        clean_path=clean_path,
        clean_sha256=clean_sha,
        report_path=report_path,
        report_sha256=hashlib.sha256(report_raw).hexdigest(),
        baseline_reused=baseline_reused,
        targeted_reused=targeted_reused,
        clean_reused=True,
        report_reused=True,
        external_ja_outcome=external_outcome,
        alignment_outcome=alignment_outcome,
    )


def _run_first_pass(
    runner: Callable,
    package,
    *,
    route: str,
    staging_root: Path,
    semantic_policy: StatefulSemanticPolicy | str = (
        DEFAULT_STATEFUL_SEMANTIC_POLICY
    ),
) -> StatefulSubtitleResult:
    if not callable(runner):
        raise Stage11ControllerValidationError(
            "first_pass_runner must be callable"
        )
    try:
        policy = resolve_stateful_semantic_policy(semantic_policy)
    except StatefulSemanticPolicyError as error:
        raise Stage11ControllerValidationError(
            "first-pass semantic policy is unsupported"
        ) from error
    if policy == DEFAULT_STATEFUL_SEMANTIC_POLICY:
        result = runner(package, route=route, staging_root=staging_root)
    else:
        result = runner(
            package,
            route=route,
            staging_root=staging_root,
            semantic_policy=policy,
        )
    return validate_stateful_result(result, package)


def _require_clean_artifact(value: object) -> GeneratedKoreanSRT:
    artifact = getattr(value, "artifact", None)
    if type(artifact) is not GeneratedKoreanSRT:
        raise Stage11ControllerValidationError(
            "CLEAN materializer returned an invalid artifact"
        )
    artifact.__post_init__()
    if artifact.state != GENERATED_SRT_READY or artifact.payload is None:
        raise Stage11ControllerValidationError(
            "CLEAN materialization produced no durable SRT"
        )
    document = parse_subtitle_bytes(artifact.payload, "srt")
    if generate_korean_srt(document.cues) != artifact:
        raise Stage11ControllerValidationError(
            "CLEAN artifact failed canonical SRT readback validation"
        )
    return artifact


def run_one_title_stage11(
    title: str,
    *,
    artifact_root: str | Path,
    stateful_staging_root: str | Path,
    claim_token: int,
    baseline_transcriber: Callable[[CanonicalVideoHolding], ASRResult],
    external_ja_attempt: Callable,
    first_pass_runner: Callable,
    asr_review_runner: Callable,
    hybrid_review_runner: Callable,
    targeted_runner: Callable | None = None,
    holding_resolver: Callable[[str], Mapping[str, object]] | None = None,
    semantic_policy: StatefulSemanticPolicy | str = (
        DEFAULT_STATEFUL_SEMANTIC_POLICY
    ),
) -> Stage11ControllerResult:
    """Run one exact canonical DVD-ID through deterministic CLEAN and stop.

    Model transports and native session ownership stay inside the injected
    runners.  The controller never accepts or calls a publisher.
    """

    canonical_title = _canonical_title(title)
    artifact_root_path = _validate_root(
        artifact_root,
        field_name="artifact_root",
    )
    staging_root_path = _validate_root(
        stateful_staging_root,
        field_name="stateful_staging_root",
    )
    if type(claim_token) is not int or claim_token < 0:
        raise Stage11ControllerValidationError(
            "claim_token must be a nonnegative exact integer"
        )
    try:
        selected_semantic_policy = resolve_stateful_semantic_policy(
            semantic_policy
        )
    except StatefulSemanticPolicyError as error:
        raise Stage11ControllerValidationError(
            "semantic policy is unsupported"
        ) from error
    canonical_video, source_snapshot = _resolve_holding(
        canonical_title,
        holding_resolver,
    )
    directory = _title_directory(artifact_root_path, canonical_title)
    baseline_path = directory / BASELINE_ASR_FILENAME
    targeted_path = directory / TARGETED_SECOND_EVIDENCE_FILENAME
    clean_path = directory / CLEAN_SRT_FILENAME
    report_path = directory / MECHANICAL_REPORT_FILENAME
    completion_exists = _lstat_or_none(report_path) is not None

    asr_result, baseline_raw, baseline_reused = _dispatch_baseline(
        baseline_path,
        canonical_video=canonical_video,
        source_snapshot=source_snapshot,
        baseline_transcriber=baseline_transcriber,
        allow_create=not completion_exists,
    )
    baseline_sha256 = hashlib.sha256(baseline_raw).hexdigest()
    source_quality_decisions = classify_asr_result_source_quality(asr_result)
    quality_counts = _source_quality_counts(source_quality_decisions)
    targeted_artifact, targeted_reused, targeted_source_count, targeted_window_count = (
        _dispatch_targeted(
            targeted_path,
            asr_result=asr_result,
            source_quality_decisions=source_quality_decisions,
            baseline_sha256=baseline_sha256,
            targeted_runner=targeted_runner,
            allow_create=not completion_exists,
        )
    )

    if completion_exists:
        if selected_semantic_policy not in {
            STATEFUL_SEMANTIC_POLICY_16,
            DEFAULT_STATEFUL_SEMANTIC_POLICY,
        }:
            raise Stage11ControllerArtifactError(
                "candidate semantic policy cannot reuse a title completion"
            )
        return _validate_existing_completion(
            report_path,
            clean_path,
            baseline_path,
            title=canonical_title,
            baseline_sha256=baseline_sha256,
            baseline_reused=baseline_reused,
            source_quality_counts=quality_counts,
            targeted_reused=targeted_reused,
            targeted_source_count=targeted_source_count,
            targeted_window_count=targeted_window_count,
        )

    route, external_outcome, alignment_outcome = _select_route(
        canonical_video,
        asr_result,
        external_ja_attempt,
    )
    generation_suffix = baseline_sha256

    hybrid_preparation = None
    if route.route == V2_ROUTE_HYBRID:
        targeted_bindings = _build_hybrid_targeted_bindings(
            route,
            targeted_artifact,
        )
        try:
            hybrid_generation_key = bind_stateful_policy_generation_key(
                "stage11-hybrid-" + generation_suffix,
                selected_semantic_policy,
            )
            hybrid_preparation = prepare_stateful_hybrid(
                route,
                targeted_bindings=targeted_bindings,
                generation_key=hybrid_generation_key,
                claim_token=claim_token,
            )
        except (StatefulSemanticPolicyError, ValueError) as error:
            raise Stage11ControllerValidationError(
                "HYBRID generation identity could not bind its semantic policy"
            ) from error
        try:
            _validate_complete_hybrid_targeted_projection(
                targeted_artifact,
                hybrid_preparation,
            )
        except Stage11ControllerTargetedEvidenceUnprojectable:
            application = route.alignment_application
            if application is None:
                raise Stage11ControllerArtifactError(
                    "HYBRID fallback has no accepted alignment application"
                )
            route = _direct_asr_route(
                canonical_video,
                asr_result,
                method="accepted-external-unprojectable-targeted-evidence",
                confidence=application.bundle.alignment.confidence,
            )

    if route.route == V2_ROUTE_ASR_ONLY:
        source_package = build_stateful_asr_package(
            build_asr_only_cue_sequence(route),
            dvd_id=canonical_title,
            generation_key="stage11-asr-source-" + generation_suffix,
            claim_token=claim_token,
        )
        try:
            asr_generation_key = bind_stateful_policy_generation_key(
                "stage11-asr-filtered-" + generation_suffix,
                selected_semantic_policy,
            )
            prepared = prepare_stateful_asr_package(
                source_package,
                generation_key=asr_generation_key,
                asr_result=asr_result,
                source_quality_decisions=source_quality_decisions,
            )
        except (StatefulSemanticPolicyError, ValueError) as error:
            raise Stage11ControllerValidationError(
                "ASR generation identity could not bind its semantic policy"
            ) from error
        package = prepared.package
        first_pass = _run_first_pass(
            first_pass_runner,
            package,
            route=route.route,
            staging_root=staging_root_path,
            semantic_policy=selected_semantic_policy,
        )
        provenance = build_asr_prefilter_provenance(
            asr_result,
            prepared,
            asr_artifact_sha256=baseline_sha256,
        )
        review_request = build_asr_quality_review_request(
            asr_result=asr_result,
            package=package,
            result=first_pass,
            prefilter_provenance=provenance,
            targeted_second_evidence_artifact=targeted_artifact,
        )
        if not callable(asr_review_runner):
            raise Stage11ControllerValidationError(
                "asr_review_runner must be callable"
            )
        review_result = asr_review_runner(
            review_request,
            staging_root=staging_root_path,
        )
        validate_asr_quality_review_result(review_result, review_request)
        clean = materialize_stateful_asr_quality_review_clean(
            package,
            first_pass,
            asr_result,
            review_request,
            review_result,
            targeted_second_evidence_artifact=targeted_artifact,
        )
        review_request_digest = asr_quality_review_request_sha256(
            review_request
        )
        review_raw = serialize_asr_quality_review_result(
            review_result,
            review_request,
        )
    elif route.route == V2_ROUTE_HYBRID:
        if hybrid_preparation is None:
            raise Stage11ControllerValidationError(
                "HYBRID route has no prepared semantic evidence"
            )
        preparation = hybrid_preparation
        package = preparation.package
        first_pass = _run_first_pass(
            first_pass_runner,
            package,
            route=route.route,
            staging_root=staging_root_path,
            semantic_policy=selected_semantic_policy,
        )
        document = route.alignment_application.bundle.external_ja_document
        source_quality = classify_source_document(document)
        review_request = build_review_request(
            preparation=preparation,
            package=package,
            result=first_pass,
            source_quality=source_quality,
            targeted_second_evidence_artifact=targeted_artifact,
        )
        if not callable(hybrid_review_runner):
            raise Stage11ControllerValidationError(
                "hybrid_review_runner must be callable"
            )
        review_result = hybrid_review_runner(
            review_request,
            staging_root=staging_root_path,
        )
        validate_review_result(review_result, review_request)
        clean = materialize_stateful_quality_review_clean(
            package,
            first_pass,
            preparation,
            review_request,
            review_result,
            source_quality=source_quality,
            targeted_second_evidence_artifact=targeted_artifact,
        )
        review_request_digest = review_request_sha256(review_request)
        review_raw = serialize_review_result(review_result, review_request)
    else:
        raise Stage11ControllerValidationError(
            "controller selected an unsupported route"
        )

    clean_artifact = _require_clean_artifact(clean)
    clean_reused = _install_or_reuse(
        clean_path,
        clean_artifact.payload,
        max_bytes=MAX_SUBTITLE_BYTES,
    )
    clean_raw = _read_private_file(clean_path, max_bytes=MAX_SUBTITLE_BYTES)
    clean_sha256 = hashlib.sha256(clean_raw).hexdigest()
    if clean_sha256 != clean_artifact.sha256:
        raise Stage11ControllerArtifactError(
            "durable CLEAN SHA256 differs from materialization"
        )

    first_pass_raw = serialize_stateful_result(first_pass)
    report = {
        "title": canonical_title,
        "route": route.route,
        "baseline_artifact_path": str(baseline_path),
        "baseline_sha256": baseline_sha256,
        "baseline_reused": baseline_reused,
        "external_ja_outcome": external_outcome,
        "alignment_outcome": alignment_outcome,
        "source_quality_counts": quality_counts,
        "targeted_source_count": targeted_source_count,
        "targeted_window_count": targeted_window_count,
        "targeted_reused": (
            "not_applicable" if targeted_reused is None else targeted_reused
        ),
        "translation_result_identity": {
            "session_id": first_pass.session_id,
            "sha256": hashlib.sha256(first_pass_raw).hexdigest(),
        },
        "review_result_identity": {
            "request_sha256": review_request_digest,
            "result_sha256": hashlib.sha256(review_raw).hexdigest(),
            "source_translation_session_id": (
                review_result.source_translation_session_id
            ),
            "review_execution_session_id": (
                review_result.review_execution_session_id
            ),
        },
        "clean_artifact_path": str(clean_path),
        "clean_sha256": clean_sha256,
        "publication_performed": False,
    }
    report_raw = _serialize_report(report)
    report_reused = _install_or_reuse(
        report_path,
        report_raw,
        max_bytes=MAX_STAGE11_REPORT_BYTES,
    )
    persisted_report = _read_private_file(
        report_path,
        max_bytes=MAX_STAGE11_REPORT_BYTES,
    )
    _parse_report(persisted_report)

    return Stage11ControllerResult(
        title=canonical_title,
        route=route.route,
        clean_path=clean_path,
        clean_sha256=clean_sha256,
        report_path=report_path,
        report_sha256=hashlib.sha256(persisted_report).hexdigest(),
        baseline_reused=baseline_reused,
        targeted_reused=targeted_reused,
        clean_reused=clean_reused,
        report_reused=report_reused,
        external_ja_outcome=external_outcome,
        alignment_outcome=alignment_outcome,
    )


__all__ = [
    "BASELINE_ASR_FILENAME",
    "CLEAN_SRT_FILENAME",
    "MECHANICAL_REPORT_FILENAME",
    "Stage11ControllerArtifactError",
    "Stage11ControllerError",
    "Stage11ControllerResult",
    "Stage11ControllerTargetedEvidenceUnprojectable",
    "Stage11ControllerValidationError",
    "TARGETED_SECOND_EVIDENCE_FILENAME",
    "run_one_title_stage11",
]
