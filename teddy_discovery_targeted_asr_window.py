"""Deterministic bounded audio-window planning for targeted Stage11 ASR.

This module plans only bounded media-time windows.  It does not invoke ASR,
read media, select a provider, or mutate any pipeline state.

External-JA cue identity remains the R2 ordinal identity.  A route-neutral
source-interval planner is also exposed for ASR-first second evidence.  The
low-level geometry keeps its caller-owned parameter API, while the explicit
Stage11 second-evidence V1 policy is owned here and supplied through a
separate adapter.  Cue timestamps are projected with the single R5 affine
materialization helper; no semantic or subtitle-timing decision is made here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from teddy_discovery_alignment import RobustAffineAlignment
from teddy_discovery_asr_audio import MAX_ASR_AUDIO_CHUNK_SECONDS
from teddy_discovery_hybrid_evidence import (
    EVIDENCE_SOURCE_EXTERNAL_JA,
    HybridCueIdentity,
)
from teddy_discovery_subtitle_text import SubtitleCue
from teddy_discovery_subtitle_v2_orchestrator import (
    project_affine_timestamp_ms,
)


class TargetedASRWindowError(ValueError):
    """Raised when targeted ASR window planning cannot be proven safe."""


TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_VERSION_V1: Final[str] = "v1"
MAX_TARGETED_ASR_WINDOW_MS: Final[int] = (
    MAX_ASR_AUDIO_CHUNK_SECONDS * 1_000
)


@dataclass(frozen=True)
class TargetedASRWindow:
    """One bounded media-time window and its external-JA cue identities."""

    start_ms: int
    end_ms: int
    external_cue_ids: tuple[str, ...]

    def __post_init__(self):
        if (
            type(self.start_ms) is not int
            or type(self.end_ms) is not int
            or self.start_ms < 0
            or self.end_ms <= self.start_ms
        ):
            raise TargetedASRWindowError(
                "targeted ASR window timing is invalid"
            )

        if type(self.external_cue_ids) is not tuple:
            raise TargetedASRWindowError(
                "targeted ASR window cue IDs must be an immutable tuple"
            )

        if not self.external_cue_ids:
            raise TargetedASRWindowError(
                "targeted ASR window must contain an external cue"
            )

        if any(
            type(cue_id) is not str
            or not cue_id
            or cue_id != cue_id.strip()
            or any(character.isspace() for character in cue_id)
            or any(ord(character) < 32 or ord(character) == 127 for character in cue_id)
            for cue_id in self.external_cue_ids
        ):
            raise TargetedASRWindowError(
                "targeted ASR window contains an unsafe cue identity"
            )

        if len(set(self.external_cue_ids)) != len(self.external_cue_ids):
            raise TargetedASRWindowError(
                "targeted ASR window contains duplicate cue identities"
            )


@dataclass(frozen=True)
class TargetedASRSourceInterval:
    """One validated source identity and its original media interval."""

    source_id: str
    source_index: int
    start_ms: int
    end_ms: int

    def __post_init__(self):
        if (
            type(self.source_id) is not str
            or not self.source_id
            or self.source_id != self.source_id.strip()
            or any(character.isspace() for character in self.source_id)
            or any(
                ord(character) < 32 or ord(character) == 127
                for character in self.source_id
            )
        ):
            raise TargetedASRWindowError(
                "targeted ASR source identity is unsafe"
            )
        _require_exact_nonnegative_int(
            self.source_index,
            field_name="targeted ASR source_index",
        )
        if (
            type(self.start_ms) is not int
            or type(self.end_ms) is not int
            or self.start_ms < 0
            or self.end_ms <= self.start_ms
        ):
            raise TargetedASRWindowError(
                "targeted ASR source interval is invalid"
            )


@dataclass(frozen=True)
class TargetedASRSourceWindow:
    """One bounded window associated with generic source identities."""

    start_ms: int
    end_ms: int
    source_ids: tuple[str, ...]
    source_indices: tuple[int, ...]

    def __post_init__(self):
        if (
            type(self.start_ms) is not int
            or type(self.end_ms) is not int
            or self.start_ms < 0
            or self.end_ms <= self.start_ms
        ):
            raise TargetedASRWindowError(
                "targeted ASR source window timing is invalid"
            )
        if type(self.source_ids) is not tuple or not self.source_ids:
            raise TargetedASRWindowError(
                "targeted ASR source window IDs must be nonempty tuple"
            )
        if type(self.source_indices) is not tuple:
            raise TargetedASRWindowError(
                "targeted ASR source window indexes must be a tuple"
            )
        if len(self.source_ids) != len(self.source_indices):
            raise TargetedASRWindowError(
                "targeted ASR source window identity coverage differs"
            )
        for source_id in self.source_ids:
            if (
                type(source_id) is not str
                or not source_id
                or source_id != source_id.strip()
                or any(character.isspace() for character in source_id)
                or any(
                    ord(character) < 32 or ord(character) == 127
                    for character in source_id
                )
            ):
                raise TargetedASRWindowError(
                    "targeted ASR source window contains an unsafe identity"
                )
        if len(set(self.source_ids)) != len(self.source_ids):
            raise TargetedASRWindowError(
                "targeted ASR source window contains duplicate IDs"
            )
        previous_index = None
        for source_index in self.source_indices:
            _require_exact_nonnegative_int(
                source_index,
                field_name="targeted ASR source window source_index",
            )
            if previous_index is not None and source_index <= previous_index:
                raise TargetedASRWindowError(
                    "targeted ASR source window indexes must be increasing"
                )
            previous_index = source_index


def _require_exact_nonnegative_int(value: object, *, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise TargetedASRWindowError(
            field_name + " must be an exact nonnegative integer"
        )
    return value


def _require_positive_int(value: object, *, field_name: str) -> int:
    if type(value) is not int or value <= 0:
        raise TargetedASRWindowError(
            field_name + " must be an exact positive integer"
        )
    return value


@dataclass(frozen=True)
class TargetedSecondEvidenceWindowPolicy:
    """Immutable, versioned geometry for ASR-first second evidence.

    The four timing values are intentionally separate from the low-level
    planner's legacy caller-owned arguments.  A caller must explicitly select
    a policy object and use one of the policy adapters below; the planner does
    not silently choose a default.
    """

    pre_padding_ms: int
    post_padding_ms: int
    merge_gap_ms: int
    max_window_ms: int
    version: str

    def __post_init__(self):
        _require_exact_nonnegative_int(
            self.pre_padding_ms,
            field_name="policy pre_padding_ms",
        )
        _require_exact_nonnegative_int(
            self.post_padding_ms,
            field_name="policy post_padding_ms",
        )
        _require_exact_nonnegative_int(
            self.merge_gap_ms,
            field_name="policy merge_gap_ms",
        )
        _require_positive_int(
            self.max_window_ms,
            field_name="policy max_window_ms",
        )
        if any(
            value > MAX_TARGETED_ASR_WINDOW_MS
            for value in (
                self.pre_padding_ms,
                self.post_padding_ms,
                self.merge_gap_ms,
                self.max_window_ms,
            )
        ):
            raise TargetedASRWindowError(
                "policy timing value exceeds the bounded ASR window limit"
            )
        if self.pre_padding_ms + self.post_padding_ms >= self.max_window_ms:
            raise TargetedASRWindowError(
                "policy padding leaves no positive source interval"
            )
        if (
            type(self.version) is not str
            or not self.version
            or self.version != self.version.strip()
            or any(character.isspace() for character in self.version)
            or any(
                ord(character) < 32 or ord(character) == 127
                for character in self.version
            )
        ):
            raise TargetedASRWindowError(
                "policy version must be a safe nonempty token"
            )


STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1: Final[
    TargetedSecondEvidenceWindowPolicy
] = TargetedSecondEvidenceWindowPolicy(
    pre_padding_ms=5_000,
    post_padding_ms=5_000,
    merge_gap_ms=10_000,
    max_window_ms=60_000,
    version=TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_VERSION_V1,
)


def validate_targeted_second_evidence_window_policy(
    value: object,
) -> TargetedSecondEvidenceWindowPolicy:
    """Return a detached-safe policy value or fail closed."""

    if type(value) is not TargetedSecondEvidenceWindowPolicy:
        raise TargetedASRWindowError(
            "targeted second-evidence policy has the wrong type"
        )
    try:
        validated = TargetedSecondEvidenceWindowPolicy(
            pre_padding_ms=value.pre_padding_ms,
            post_padding_ms=value.post_padding_ms,
            merge_gap_ms=value.merge_gap_ms,
            max_window_ms=value.max_window_ms,
            version=value.version,
        )
    except Exception as error:
        raise TargetedASRWindowError(
            "targeted second-evidence policy is invalid"
        ) from error
    if validated != value:
        raise TargetedASRWindowError(
            "targeted second-evidence policy is detached"
        )
    return validated


def plan_targeted_asr_source_windows(
    source_intervals: tuple[TargetedASRSourceInterval, ...],
    *,
    padding_before_ms: int,
    padding_after_ms: int,
    merge_gap_ms: int,
    max_window_ms: int,
) -> tuple[TargetedASRSourceWindow, ...]:
    """Plan bounded windows from caller-owned source intervals.

    This is the generic geometry shared by ASR-first second evidence.  It
    never projects timestamps, assigns semantic truth, or supplies policy
    defaults.  Each source interval belongs to exactly one output window;
    merged membership preserves source order.
    """

    _require_exact_nonnegative_int(
        padding_before_ms,
        field_name="padding_before_ms",
    )
    _require_exact_nonnegative_int(
        padding_after_ms,
        field_name="padding_after_ms",
    )
    _require_exact_nonnegative_int(
        merge_gap_ms,
        field_name="merge_gap_ms",
    )
    _require_positive_int(
        max_window_ms,
        field_name="max_window_ms",
    )

    if type(source_intervals) is not tuple or not source_intervals:
        raise TargetedASRWindowError(
            "source_intervals must be a nonempty immutable tuple"
        )

    validated_intervals = []
    seen_source_ids = set()
    previous_source_index = None
    previous_start_ms = None
    for interval in source_intervals:
        if type(interval) is not TargetedASRSourceInterval:
            raise TargetedASRWindowError(
                "source_intervals contains an invalid source interval"
            )
        try:
            validated = TargetedASRSourceInterval(
                source_id=interval.source_id,
                source_index=interval.source_index,
                start_ms=interval.start_ms,
                end_ms=interval.end_ms,
            )
        except Exception as error:
            raise TargetedASRWindowError(
                "source interval is invalid or detached"
            ) from error
        if validated != interval:
            raise TargetedASRWindowError(
                "source interval identity is detached"
            )
        if validated.source_id in seen_source_ids:
            raise TargetedASRWindowError(
                "source intervals contain a duplicate source ID"
            )
        if (
            previous_source_index is not None
            and validated.source_index <= previous_source_index
        ):
            raise TargetedASRWindowError(
                "source intervals must remain in source order"
            )
        if (
            previous_start_ms is not None
            and validated.start_ms < previous_start_ms
        ):
            raise TargetedASRWindowError(
                "source interval starts must be nondecreasing"
            )
        seen_source_ids.add(validated.source_id)
        previous_source_index = validated.source_index
        previous_start_ms = validated.start_ms
        validated_intervals.append(validated)

    padded_intervals = []
    for interval in validated_intervals:
        padded_start_ms = max(
            0,
            interval.start_ms - padding_before_ms,
        )
        padded_end_ms = interval.end_ms + padding_after_ms
        if padded_end_ms <= padded_start_ms:
            raise TargetedASRWindowError(
                "padded source interval is not positive"
            )
        if padded_end_ms - padded_start_ms > max_window_ms:
            raise TargetedASRWindowError(
                "one source interval exceeds the maximum ASR window"
            )
        padded_intervals.append(
            (
                interval.source_id,
                interval.source_index,
                padded_start_ms,
                padded_end_ms,
            )
        )

    windows = []
    (
        current_source_id,
        current_source_index,
        current_start_ms,
        current_end_ms,
    ) = padded_intervals[0]
    current_source_ids = [current_source_id]
    current_source_indices = [current_source_index]

    for source_id, source_index, start_ms, end_ms in padded_intervals[1:]:
        gap_ms = start_ms - current_end_ms
        merged_start_ms = min(current_start_ms, start_ms)
        merged_end_ms = max(current_end_ms, end_ms)
        merged_duration_ms = merged_end_ms - merged_start_ms
        if (
            gap_ms <= merge_gap_ms
            and merged_duration_ms <= max_window_ms
        ):
            current_start_ms = merged_start_ms
            current_end_ms = merged_end_ms
            current_source_ids.append(source_id)
            current_source_indices.append(source_index)
            continue

        windows.append(
            TargetedASRSourceWindow(
                start_ms=current_start_ms,
                end_ms=current_end_ms,
                source_ids=tuple(current_source_ids),
                source_indices=tuple(current_source_indices),
            )
        )
        current_source_id = source_id
        current_source_index = source_index
        current_start_ms = start_ms
        current_end_ms = end_ms
        current_source_ids = [current_source_id]
        current_source_indices = [current_source_index]

    windows.append(
        TargetedASRSourceWindow(
            start_ms=current_start_ms,
            end_ms=current_end_ms,
            source_ids=tuple(current_source_ids),
            source_indices=tuple(current_source_indices),
        )
    )
    return tuple(windows)


def _project_external_cues(
    external_cues: tuple[SubtitleCue, ...],
    alignment: RobustAffineAlignment,
) -> tuple[tuple[str, int, int], ...]:
    if type(external_cues) is not tuple:
        raise TargetedASRWindowError(
            "external_cues must be an immutable tuple"
        )

    if not external_cues:
        raise TargetedASRWindowError(
            "external_cues must contain at least one cue"
        )

    if not isinstance(alignment, RobustAffineAlignment):
        raise TargetedASRWindowError(
            "alignment must be a RobustAffineAlignment"
        )

    projected = []
    previous_source_start_ms = None
    previous_projected_start_ms = None

    for source_index, source_cue in enumerate(external_cues):
        if not isinstance(source_cue, SubtitleCue):
            raise TargetedASRWindowError(
                "external_cues contains an invalid SubtitleCue"
            )

        if (
            previous_source_start_ms is not None
            and source_cue.start_ms < previous_source_start_ms
        ):
            raise TargetedASRWindowError(
                "external cue starts must be nondecreasing"
            )

        try:
            projected_start_ms = project_affine_timestamp_ms(
                alignment,
                source_cue.start_ms,
            )
            projected_end_ms = project_affine_timestamp_ms(
                alignment,
                source_cue.end_ms,
            )
        except Exception as error:
            raise TargetedASRWindowError(
                "external cue affine projection failed"
            ) from error

        if projected_end_ms <= projected_start_ms:
            raise TargetedASRWindowError(
                "projected external cue duration is not positive"
            )

        if (
            previous_projected_start_ms is not None
            and projected_start_ms < previous_projected_start_ms
        ):
            raise TargetedASRWindowError(
                "projected external cue starts must be nondecreasing"
            )

        cue_identity = HybridCueIdentity.for_external_ja(source_index)
        if cue_identity.source != EVIDENCE_SOURCE_EXTERNAL_JA:
            raise TargetedASRWindowError(
                "external cue identity source is invalid"
            )

        projected.append(
            (
                cue_identity.cue_id,
                projected_start_ms,
                projected_end_ms,
            )
        )
        previous_source_start_ms = source_cue.start_ms
        previous_projected_start_ms = projected_start_ms

    return tuple(projected)


def plan_targeted_asr_windows(
    external_cues: tuple[SubtitleCue, ...],
    alignment: RobustAffineAlignment,
    *,
    padding_before_ms: int,
    padding_after_ms: int,
    merge_gap_ms: int,
    max_window_ms: int,
) -> tuple[TargetedASRWindow, ...]:
    """Plan bounded ASR windows from external-JA source cues.

    ``padding_*``, ``merge_gap_ms``, and ``max_window_ms`` are deliberately
    caller-supplied.  A merge is used only when the resulting window remains
    within ``max_window_ms``; the maximum bound therefore safely vetoes a
    merge without shortening or shifting any cue window.
    """

    projected_cues = _project_external_cues(
        external_cues,
        alignment,
    )

    source_windows = plan_targeted_asr_source_windows(
        tuple(
            TargetedASRSourceInterval(
                source_id=cue_id,
                source_index=source_index,
                start_ms=projected_start_ms,
                end_ms=projected_end_ms,
            )
            for source_index, (cue_id, projected_start_ms, projected_end_ms)
            in enumerate(projected_cues)
        ),
        padding_before_ms=padding_before_ms,
        padding_after_ms=padding_after_ms,
        merge_gap_ms=merge_gap_ms,
        max_window_ms=max_window_ms,
    )
    return tuple(
        TargetedASRWindow(
            start_ms=window.start_ms,
            end_ms=window.end_ms,
            external_cue_ids=window.source_ids,
        )
        for window in source_windows
    )


def plan_targeted_asr_source_windows_with_policy(
    source_intervals: tuple[TargetedASRSourceInterval, ...],
    *,
    policy: TargetedSecondEvidenceWindowPolicy,
) -> tuple[TargetedASRSourceWindow, ...]:
    """Apply an explicitly selected policy through the existing geometry."""

    validated_policy = validate_targeted_second_evidence_window_policy(policy)
    return plan_targeted_asr_source_windows(
        source_intervals,
        padding_before_ms=validated_policy.pre_padding_ms,
        padding_after_ms=validated_policy.post_padding_ms,
        merge_gap_ms=validated_policy.merge_gap_ms,
        max_window_ms=validated_policy.max_window_ms,
    )


def plan_targeted_asr_windows_with_policy(
    external_cues: tuple[SubtitleCue, ...],
    alignment: RobustAffineAlignment,
    *,
    policy: TargetedSecondEvidenceWindowPolicy,
) -> tuple[TargetedASRWindow, ...]:
    """Apply an explicit policy through the existing Hybrid geometry.

    Existing Hybrid callers remain on the original parameterized function;
    this adapter does not change their behavior or identity contract.
    """

    validated_policy = validate_targeted_second_evidence_window_policy(policy)
    return plan_targeted_asr_windows(
        external_cues,
        alignment,
        padding_before_ms=validated_policy.pre_padding_ms,
        padding_after_ms=validated_policy.post_padding_ms,
        merge_gap_ms=validated_policy.merge_gap_ms,
        max_window_ms=validated_policy.max_window_ms,
    )


__all__ = [
    "MAX_TARGETED_ASR_WINDOW_MS",
    "STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1",
    "TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_VERSION_V1",
    "TargetedASRWindow",
    "TargetedASRWindowError",
    "TargetedASRSourceInterval",
    "TargetedASRSourceWindow",
    "TargetedSecondEvidenceWindowPolicy",
    "plan_targeted_asr_windows",
    "plan_targeted_asr_windows_with_policy",
    "plan_targeted_asr_source_windows",
    "plan_targeted_asr_source_windows_with_policy",
    "validate_targeted_second_evidence_window_policy",
]
