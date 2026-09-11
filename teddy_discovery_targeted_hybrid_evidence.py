"""Immutable targeted-ASR evidence for external-JA HYBRID semantics.

Targeted evidence is deliberately not a new ``HybridCueIdentity`` source
kind and does not replace baseline ASR residual ownership.  It is a bounded
second-evidence result whose source snapshot, absolute window, selected
segment, and external-JA association must all remain attached.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from teddy_discovery_asr import (
    ASRSegment,
    ASRSourceSnapshot,
    MAX_ASR_SEGMENTS,
)
from teddy_discovery_hybrid_evidence import (
    EVIDENCE_SOURCE_EXTERNAL_JA,
    HybridCueIdentity,
)
from teddy_discovery_subtitle_text import SubtitleCue

if TYPE_CHECKING:
    from teddy_discovery_alignment import RobustAffineAlignment


class TargetedHybridEvidenceError(ValueError):
    """Base class for targeted second-evidence validation failures."""


class TargetedHybridEvidenceLimitError(TargetedHybridEvidenceError):
    """Raised when targeted evidence exceeds the existing ASR bound."""


def _require_exact_nonnegative_int(value: object, *, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise TargetedHybridEvidenceError(
            field_name + " must be an exact nonnegative integer"
        )
    return value


def _require_safe_cue_id(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or any(character.isspace() for character in value)
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise TargetedHybridEvidenceError(
            "targeted external cue identity is unsafe"
        )
    return value


@dataclass(frozen=True)
class TargetedASRWindowEvidence:
    """One bounded targeted result in absolute media-time coordinates.

    An empty segments tuple preserves a completed window with no detected
    speech.  It cannot own a TargetedASRBinding because no segment index exists.
    """

    source_snapshot: ASRSourceSnapshot
    window_start_ms: int
    window_end_ms: int
    external_cue_ids: tuple[str, ...]
    segments: tuple[ASRSegment, ...]

    def __post_init__(self):
        if not isinstance(self.source_snapshot, ASRSourceSnapshot):
            raise TargetedHybridEvidenceError(
                "targeted source snapshot is invalid"
            )
        _require_exact_nonnegative_int(
            self.window_start_ms,
            field_name="targeted window start_ms",
        )
        _require_exact_nonnegative_int(
            self.window_end_ms,
            field_name="targeted window end_ms",
        )
        if self.window_end_ms <= self.window_start_ms:
            raise TargetedHybridEvidenceError(
                "targeted window must have positive duration"
            )

        if type(self.external_cue_ids) is not tuple or not self.external_cue_ids:
            raise TargetedHybridEvidenceError(
                "targeted window cue IDs must be a nonempty tuple"
            )
        validated_ids = tuple(
            _require_safe_cue_id(cue_id)
            for cue_id in self.external_cue_ids
        )
        if validated_ids != self.external_cue_ids:
            raise TargetedHybridEvidenceError(
                "targeted window cue IDs are detached"
            )
        if len(set(validated_ids)) != len(validated_ids):
            raise TargetedHybridEvidenceError(
                "targeted window cue IDs must be unique"
            )

        if type(self.segments) is not tuple:
            raise TargetedHybridEvidenceError(
                "targeted ASR segments must be an immutable tuple"
            )
        if len(self.segments) > MAX_ASR_SEGMENTS:
            raise TargetedHybridEvidenceLimitError(
                "targeted ASR segments exceed MAX_ASR_SEGMENTS"
            )

        previous_start_ms = None
        for segment in self.segments:
            if not isinstance(segment, ASRSegment):
                raise TargetedHybridEvidenceError(
                    "targeted ASR segments contain an invalid value"
                )
            if (
                segment.start_ms < self.window_start_ms
                or segment.end_ms > self.window_end_ms
            ):
                raise TargetedHybridEvidenceError(
                    "targeted ASR segment lies outside its absolute window"
                )
            if (
                previous_start_ms is not None
                and segment.start_ms < previous_start_ms
            ):
                raise TargetedHybridEvidenceError(
                    "targeted ASR segment starts must be nondecreasing"
                )
            previous_start_ms = segment.start_ms


@dataclass(frozen=True)
class TargetedASRBinding:
    """One explicit external-JA cue to one exact targeted ASR segment."""

    external_identity: HybridCueIdentity
    evidence: TargetedASRWindowEvidence
    segment_index: int

    def __post_init__(self):
        if not isinstance(self.external_identity, HybridCueIdentity):
            raise TargetedHybridEvidenceError(
                "targeted external identity is invalid"
            )
        if self.external_identity.source != EVIDENCE_SOURCE_EXTERNAL_JA:
            raise TargetedHybridEvidenceError(
                "targeted binding must identify an external JA cue"
            )
        if not isinstance(self.evidence, TargetedASRWindowEvidence):
            raise TargetedHybridEvidenceError(
                "targeted binding evidence is invalid"
            )
        segment_index = _require_exact_nonnegative_int(
            self.segment_index,
            field_name="targeted segment_index",
        )
        if segment_index >= len(self.evidence.segments):
            raise TargetedHybridEvidenceError(
                "targeted segment_index is outside the result"
            )
        if self.external_identity.cue_id not in self.evidence.external_cue_ids:
            raise TargetedHybridEvidenceError(
                "targeted external cue is not in its window association"
            )

    @property
    def segment(self) -> ASRSegment:
        return self.evidence.segments[self.segment_index]


def validate_targeted_asr_binding(value: object) -> TargetedASRBinding:
    """Reconstruct one targeted binding to reject detached immutable values."""

    if not isinstance(value, TargetedASRBinding):
        raise TargetedHybridEvidenceError(
            "value must be a TargetedASRBinding"
        )
    try:
        evidence = TargetedASRWindowEvidence(
            source_snapshot=value.evidence.source_snapshot,
            window_start_ms=value.evidence.window_start_ms,
            window_end_ms=value.evidence.window_end_ms,
            external_cue_ids=value.evidence.external_cue_ids,
            segments=value.evidence.segments,
        )
        validated = TargetedASRBinding(
            external_identity=value.external_identity,
            evidence=evidence,
            segment_index=value.segment_index,
        )
    except Exception as error:
        raise TargetedHybridEvidenceError(
            "targeted binding is invalid or detached"
        ) from error
    if validated != value:
        raise TargetedHybridEvidenceError(
            "targeted binding identity is detached"
        )
    return validated


def _validated_targeted_window_evidence(
    value: object,
) -> TargetedASRWindowEvidence:
    if not isinstance(value, TargetedASRWindowEvidence):
        raise TargetedHybridEvidenceError(
            "targeted window evidence is invalid"
        )
    try:
        validated = TargetedASRWindowEvidence(
            source_snapshot=value.source_snapshot,
            window_start_ms=value.window_start_ms,
            window_end_ms=value.window_end_ms,
            external_cue_ids=value.external_cue_ids,
            segments=value.segments,
        )
    except Exception as error:
        raise TargetedHybridEvidenceError(
            "targeted window evidence is invalid or detached"
        ) from error
    if validated != value:
        raise TargetedHybridEvidenceError(
            "targeted window evidence identity is detached"
        )
    return validated


def _validated_targeted_alignment(
    value: object,
) -> "RobustAffineAlignment":
    from teddy_discovery_alignment import RobustAffineAlignment

    if not isinstance(value, RobustAffineAlignment):
        raise TargetedHybridEvidenceError(
            "targeted alignment must be a RobustAffineAlignment"
        )
    try:
        validated = RobustAffineAlignment(
            scale=value.scale,
            intercept_ms=value.intercept_ms,
            anchor_count=value.anchor_count,
            inlier_count=value.inlier_count,
            residual_threshold_ms=value.residual_threshold_ms,
            residuals=value.residuals,
            median_absolute_residual_ms=value.median_absolute_residual_ms,
        )
    except Exception as error:
        raise TargetedHybridEvidenceError(
            "targeted alignment is invalid or detached"
        ) from error
    if validated != value:
        raise TargetedHybridEvidenceError(
            "targeted alignment identity is detached"
        )
    return validated


def _validated_targeted_external_cues(
    value: object,
) -> tuple[SubtitleCue, ...]:
    if type(value) is not tuple or not value:
        raise TargetedHybridEvidenceError(
            "targeted external cues must be a nonempty tuple"
        )
    previous_start_ms = None
    for cue in value:
        if not isinstance(cue, SubtitleCue):
            raise TargetedHybridEvidenceError(
                "targeted external cues contain an invalid SubtitleCue"
            )
        if (
            previous_start_ms is not None
            and cue.start_ms < previous_start_ms
        ):
            raise TargetedHybridEvidenceError(
                "targeted external cue starts must be nondecreasing"
            )
        previous_start_ms = cue.start_ms
    return value


def _targeted_window_cue_indexes(
    evidence: TargetedASRWindowEvidence,
    external_cues: tuple[SubtitleCue, ...],
) -> tuple[int, ...]:
    cue_id_to_index = {
        HybridCueIdentity.for_external_ja(index).cue_id: index
        for index in range(len(external_cues))
    }
    indexes = []
    previous_index = None
    for cue_id in evidence.external_cue_ids:
        source_index = cue_id_to_index.get(cue_id)
        if source_index is None:
            raise TargetedHybridEvidenceError(
                "targeted external cue identity is detached"
            )
        if previous_index is not None and source_index <= previous_index:
            raise TargetedHybridEvidenceError(
                "targeted external cue identities are out of source order"
            )
        indexes.append(source_index)
        previous_index = source_index
    return tuple(indexes)


def _targeted_overlap(
    cue_start_ms: int,
    cue_end_ms: int,
    segment: ASRSegment,
) -> bool:
    """Return whether two absolute media-time intervals overlap positively."""

    return (
        segment.start_ms < cue_end_ms
        and cue_start_ms < segment.end_ms
    )


def build_targeted_asr_bindings(
    external_cues: tuple[SubtitleCue, ...],
    alignment: "RobustAffineAlignment",
    evidence: TargetedASRWindowEvidence,
) -> tuple[TargetedASRBinding, ...]:
    """Build only one-to-one targeted bindings proven by absolute timing.

    External cue timestamps are projected with the accepted affine alignment;
    targeted ASR segment timestamps are already absolute media-time values and
    are never transformed.  A positive interval overlap is a candidate.  A
    candidate is materialized only when its cue and segment are each other's
    sole candidate in the window.  Existing alignment residuals own their
    external cues first, so those cues are omitted from targeted matching.

    This function uses no dialogue text and does not choose among competing
    candidates.  Ambiguous or non-overlapping candidates return no binding for
    the affected cue.
    """

    validated_external_cues = _validated_targeted_external_cues(external_cues)
    validated_alignment = _validated_targeted_alignment(alignment)
    validated_evidence = _validated_targeted_window_evidence(evidence)
    window_indexes = _targeted_window_cue_indexes(
        validated_evidence,
        validated_external_cues,
    )

    baseline_external_indexes = set()
    for residual in validated_alignment.residuals:
        source_index = residual.external_identity.source_index
        if source_index >= len(validated_external_cues):
            raise TargetedHybridEvidenceError(
                "targeted alignment external identity is detached"
            )
        if (
            residual.external_identity
            != HybridCueIdentity.for_external_ja(source_index)
        ):
            raise TargetedHybridEvidenceError(
                "targeted alignment external identity is not source-stable"
            )
        baseline_external_indexes.add(source_index)

    from teddy_discovery_subtitle_v2_orchestrator import (
        project_affine_timestamp_ms,
    )

    projected_intervals = {}
    for source_index in window_indexes:
        source_cue = validated_external_cues[source_index]
        try:
            projected_start_ms = project_affine_timestamp_ms(
                validated_alignment,
                source_cue.start_ms,
            )
            projected_end_ms = project_affine_timestamp_ms(
                validated_alignment,
                source_cue.end_ms,
            )
        except Exception as error:
            raise TargetedHybridEvidenceError(
                "targeted external cue affine projection failed"
            ) from error

        if projected_end_ms <= projected_start_ms:
            raise TargetedHybridEvidenceError(
                "targeted projected external cue duration is not positive"
            )
        if (
            projected_start_ms < validated_evidence.window_start_ms
            or projected_end_ms > validated_evidence.window_end_ms
        ):
            raise TargetedHybridEvidenceError(
                "targeted projected external cue lies outside its window"
            )
        projected_intervals[source_index] = (
            projected_start_ms,
            projected_end_ms,
        )

    candidates_by_cue = {}
    candidates_by_segment = {
        segment_index: []
        for segment_index in range(len(validated_evidence.segments))
    }
    for source_index in window_indexes:
        if source_index in baseline_external_indexes:
            continue
        cue_start_ms, cue_end_ms = projected_intervals[source_index]
        matching_segments = []
        for segment_index, segment in enumerate(validated_evidence.segments):
            if _targeted_overlap(cue_start_ms, cue_end_ms, segment):
                matching_segments.append(segment_index)
                candidates_by_segment[segment_index].append(source_index)
        candidates_by_cue[source_index] = tuple(matching_segments)

    bindings = []
    for source_index in window_indexes:
        matching_segments = candidates_by_cue.get(source_index, ())
        if len(matching_segments) != 1:
            continue
        segment_index = matching_segments[0]
        if len(candidates_by_segment[segment_index]) != 1:
            continue
        bindings.append(
            TargetedASRBinding(
                external_identity=HybridCueIdentity.for_external_ja(
                    source_index
                ),
                evidence=validated_evidence,
                segment_index=segment_index,
            )
        )

    return tuple(bindings)


__all__ = [
    "TargetedASRBinding",
    "TargetedASRWindowEvidence",
    "TargetedHybridEvidenceError",
    "TargetedHybridEvidenceLimitError",
    "build_targeted_asr_bindings",
    "validate_targeted_asr_binding",
]
