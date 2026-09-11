"""Deterministic per-cue ASR neighbor selection for Stage11 HYBRID evidence."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import math


class HybridNeighborError(ValueError):
    pass


@dataclass(frozen=True)
class ASRTimingEvidence:
    source_index: int
    start_ms: int
    end_ms: int

    def __post_init__(self):
        if type(self.source_index) is not int or self.source_index < 0:
            raise HybridNeighborError(
                "ASR source_index must be a nonnegative exact int"
            )

        if (
            type(self.start_ms) is not int
            or type(self.end_ms) is not int
            or self.start_ms < 0
            or self.end_ms <= self.start_ms
        ):
            raise HybridNeighborError(
                "ASR timing must be a valid positive interval"
            )


@dataclass(frozen=True)
class ProjectedExternalInterval:
    start_ms: int
    end_ms: int

    def __post_init__(self):
        if (
            type(self.start_ms) is not int
            or type(self.end_ms) is not int
            or self.start_ms < 0
            or self.end_ms <= self.start_ms
        ):
            raise HybridNeighborError(
                "projected external timing is invalid"
            )


@dataclass(frozen=True)
class ASRNeighborSelection:
    overlapping_indices: tuple[int, ...]
    before_indices: tuple[int, ...]
    after_indices: tuple[int, ...]

    @property
    def all_indices(self) -> tuple[int, ...]:
        return (
            self.before_indices
            + self.overlapping_indices
            + self.after_indices
        )


def _require_finite_number(value: object, field_name: str) -> float:
    if type(value) not in (int, float):
        raise HybridNeighborError(
            field_name + " must be an exact int or float"
        )

    converted = float(value)

    if not math.isfinite(converted):
        raise HybridNeighborError(
            field_name + " must be finite"
        )

    return converted


def _round_half_up(value: Decimal) -> int:
    return int(
        value.quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )


def project_external_interval(
    external_start_ms: int,
    external_end_ms: int,
    *,
    scale: float,
    intercept_ms: float,
) -> ProjectedExternalInterval:
    """Project one external-JA interval onto ASR/video time."""

    if (
        type(external_start_ms) is not int
        or type(external_end_ms) is not int
        or external_start_ms < 0
        or external_end_ms <= external_start_ms
    ):
        raise HybridNeighborError(
            "external timing must be a valid positive interval"
        )

    scale_value = _require_finite_number(
        scale,
        "scale",
    )

    intercept_value = _require_finite_number(
        intercept_ms,
        "intercept_ms",
    )

    if scale_value <= 0:
        raise HybridNeighborError(
            "scale must be strictly positive"
        )

    scale_decimal = Decimal(str(scale_value))
    intercept_decimal = Decimal(str(intercept_value))

    start = _round_half_up(
        scale_decimal * Decimal(external_start_ms)
        + intercept_decimal
    )

    end = _round_half_up(
        scale_decimal * Decimal(external_end_ms)
        + intercept_decimal
    )

    if start < 0 or end <= start:
        raise HybridNeighborError(
            "affine projection produced invalid timing"
        )

    return ProjectedExternalInterval(
        start_ms=start,
        end_ms=end,
    )


def select_asr_neighbors(
    projected: ProjectedExternalInterval,
    asr_segments: tuple[ASRTimingEvidence, ...],
    *,
    maximum_distance_ms: int,
    maximum_before: int = 1,
    maximum_after: int = 1,
    maximum_overlapping: int = 8,
) -> ASRNeighborSelection:
    """Select bounded ASR evidence around one projected external cue.

    Text is never copied here. Only stable ASR source indexes are returned.
    """

    if not isinstance(
        projected,
        ProjectedExternalInterval,
    ):
        raise HybridNeighborError(
            "projected must be ProjectedExternalInterval"
        )

    if type(asr_segments) is not tuple:
        raise HybridNeighborError(
            "asr_segments must be an immutable tuple"
        )

    for field_name, value, allow_zero in (
        ("maximum_distance_ms", maximum_distance_ms, True),
        ("maximum_before", maximum_before, True),
        ("maximum_after", maximum_after, True),
        ("maximum_overlapping", maximum_overlapping, False),
    ):
        if type(value) is not int:
            raise HybridNeighborError(
                field_name + " must be an exact int"
            )

        minimum = 0 if allow_zero else 1

        if value < minimum:
            raise HybridNeighborError(
                field_name + " is outside its valid range"
            )

    validated = []

    previous_index = None
    previous_start = None

    for segment in asr_segments:
        if not isinstance(segment, ASRTimingEvidence):
            raise HybridNeighborError(
                "asr_segments contains an invalid value"
            )

        if (
            previous_index is not None
            and segment.source_index <= previous_index
        ):
            raise HybridNeighborError(
                "ASR source indexes must increase strictly"
            )

        if (
            previous_start is not None
            and segment.start_ms < previous_start
        ):
            raise HybridNeighborError(
                "ASR segments must be time ordered"
            )

        validated.append(segment)
        previous_index = segment.source_index
        previous_start = segment.start_ms

    overlapping = []

    for segment in validated:
        if (
            segment.end_ms > projected.start_ms
            and segment.start_ms < projected.end_ms
        ):
            overlapping.append(segment)

    if len(overlapping) > maximum_overlapping:
        raise HybridNeighborError(
            "overlapping ASR evidence exceeds the configured bound"
        )

    overlapping_ids = {
        segment.source_index
        for segment in overlapping
    }

    before_candidates = []

    for segment in validated:
        if segment.source_index in overlapping_ids:
            continue

        if segment.end_ms <= projected.start_ms:
            distance = (
                projected.start_ms
                - segment.end_ms
            )

            if distance <= maximum_distance_ms:
                before_candidates.append(
                    (
                        distance,
                        -segment.end_ms,
                        segment.source_index,
                    )
                )

    before_candidates.sort()

    selected_before = sorted(
        (
            source_index
            for _, _, source_index
            in before_candidates[:maximum_before]
        )
    )

    after_candidates = []

    for segment in validated:
        if segment.source_index in overlapping_ids:
            continue

        if segment.start_ms >= projected.end_ms:
            distance = (
                segment.start_ms
                - projected.end_ms
            )

            if distance <= maximum_distance_ms:
                after_candidates.append(
                    (
                        distance,
                        segment.start_ms,
                        segment.source_index,
                    )
                )

    after_candidates.sort()

    selected_after = sorted(
        (
            source_index
            for _, _, source_index
            in after_candidates[:maximum_after]
        )
    )

    selected_overlap = tuple(
        segment.source_index
        for segment in overlapping
    )

    all_ids = (
        tuple(selected_before)
        + selected_overlap
        + tuple(selected_after)
    )

    if len(set(all_ids)) != len(all_ids):
        raise HybridNeighborError(
            "neighbor selection produced duplicate ASR indexes"
        )

    return ASRNeighborSelection(
        overlapping_indices=selected_overlap,
        before_indices=tuple(selected_before),
        after_indices=tuple(selected_after),
    )


__all__ = [
    "ASRNeighborSelection",
    "ASRTimingEvidence",
    "HybridNeighborError",
    "ProjectedExternalInterval",
    "project_external_interval",
    "select_asr_neighbors",
]
