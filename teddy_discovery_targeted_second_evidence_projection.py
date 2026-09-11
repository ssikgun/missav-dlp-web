"""Bounded, timing-free projection of targeted ASR evidence for review.

The durable targeted artifact remains the source of truth for validation.  This
module only projects the already validated result into a small semantic-review
evidence value.  It never exposes targeted timing, chooses a semantic action,
or changes the baseline ASR source.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re

from teddy_discovery_asr import ASRResult, ASRSegment, MAX_ASR_SEGMENTS
from teddy_discovery_asr_artifact import serialize_asr_result
from teddy_discovery_targeted_second_evidence import (
    TARGETED_SECOND_EVIDENCE_STATUS_EMPTY_UNRESOLVED,
    TARGETED_SECOND_EVIDENCE_STATUS_NOISY_UNRESOLVED,
    TARGETED_SECOND_EVIDENCE_STATUS_PRESENT_UNRESOLVED,
    TargetedSecondEvidenceBinding,
)
from teddy_discovery_targeted_second_evidence_artifact import (
    MAX_TARGETED_SECOND_EVIDENCE_ARTIFACT_SEGMENTS,
    TargetedSecondEvidenceArtifact,
    require_matching_targeted_second_evidence_context,
)


TARGETED_SECOND_EVIDENCE_REVIEW_FIELDS = frozenset(
    {
        "status",
        "text_evidence",
        "segment_count",
        "provenance_digest",
    }
)
_TARGETED_SECOND_EVIDENCE_REVIEW_FIELDS_WITHOUT_DIGEST = frozenset(
    {
        "status",
        "text_evidence",
        "segment_count",
    }
)
_VALID_STATUSES = frozenset(
    {
        TARGETED_SECOND_EVIDENCE_STATUS_PRESENT_UNRESOLVED,
        TARGETED_SECOND_EVIDENCE_STATUS_EMPTY_UNRESOLVED,
        TARGETED_SECOND_EVIDENCE_STATUS_NOISY_UNRESOLVED,
    }
)
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


class TargetedSecondEvidenceProjectionError(ValueError):
    """Targeted evidence cannot be projected without losing its binding."""


def _validated_text(value: object) -> str:
    if type(value) is not str:
        raise TargetedSecondEvidenceProjectionError(
            "targeted text evidence must be an exact string"
        )
    try:
        validated = ASRSegment(0, 1, value)
    except Exception as error:
        raise TargetedSecondEvidenceProjectionError(
            "targeted text evidence is invalid"
        ) from error
    if validated.text != value:
        raise TargetedSecondEvidenceProjectionError(
            "targeted text evidence was normalized or detached"
        )
    return value


def _validated_digest(value: object) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise TargetedSecondEvidenceProjectionError(
            "targeted provenance digest is invalid"
        )
    return value


@dataclass(frozen=True)
class TargetedSecondEvidenceReviewProjection:
    """Semantic evidence only; targeted timing is deliberately absent."""

    status: str
    text_evidence: tuple[str, ...]
    segment_count: int
    provenance_digest: str | None = None

    def __post_init__(self):
        if self.status not in _VALID_STATUSES:
            raise TargetedSecondEvidenceProjectionError(
                "targeted review status is invalid"
            )
        if type(self.text_evidence) is not tuple:
            raise TargetedSecondEvidenceProjectionError(
                "targeted text evidence must be immutable"
            )
        if len(self.text_evidence) > MAX_TARGETED_SECOND_EVIDENCE_ARTIFACT_SEGMENTS:
            raise TargetedSecondEvidenceProjectionError(
                "targeted text evidence exceeds its bound"
            )
        for text in self.text_evidence:
            _validated_text(text)
        if (
            type(self.segment_count) is not int
            or not 0 <= self.segment_count
            or self.segment_count > MAX_TARGETED_SECOND_EVIDENCE_ARTIFACT_SEGMENTS
            or self.segment_count != len(self.text_evidence)
        ):
            raise TargetedSecondEvidenceProjectionError(
                "targeted segment count is detached"
            )
        if self.status == TARGETED_SECOND_EVIDENCE_STATUS_EMPTY_UNRESOLVED:
            if self.segment_count != 0:
                raise TargetedSecondEvidenceProjectionError(
                    "empty targeted status has nonempty evidence"
                )
        elif self.segment_count == 0:
            raise TargetedSecondEvidenceProjectionError(
                "nonempty targeted status has no evidence"
            )
        if self.provenance_digest is not None:
            _validated_digest(self.provenance_digest)


def parse_targeted_second_evidence_review_projection(
    value: object,
) -> TargetedSecondEvidenceReviewProjection | None:
    """Parse one exact JSON projection without accepting timing fields."""

    if value is None:
        return None
    if type(value) is not dict or set(value) not in (
        _TARGETED_SECOND_EVIDENCE_REVIEW_FIELDS_WITHOUT_DIGEST,
        TARGETED_SECOND_EVIDENCE_REVIEW_FIELDS,
    ):
        raise TargetedSecondEvidenceProjectionError(
            "targeted review evidence fields are not exact"
        )
    if type(value["text_evidence"]) is not list:
        raise TargetedSecondEvidenceProjectionError(
            "targeted text evidence must be a JSON array"
        )
    return TargetedSecondEvidenceReviewProjection(
        status=value["status"],
        text_evidence=tuple(value["text_evidence"]),
        segment_count=value["segment_count"],
        provenance_digest=value.get("provenance_digest"),
    )


def _project_binding(
    binding: TargetedSecondEvidenceBinding,
) -> TargetedSecondEvidenceReviewProjection:
    if type(binding) is not TargetedSecondEvidenceBinding:
        raise TargetedSecondEvidenceProjectionError(
            "targeted artifact contains an invalid binding"
        )
    binding.__post_init__()
    return TargetedSecondEvidenceReviewProjection(
        status=binding.status,
        text_evidence=binding.targeted_text_evidence,
        segment_count=len(binding.targeted_segments),
        provenance_digest=binding.result.plan_binding_sha256,
    )


def project_targeted_second_evidence_artifact(
    artifact: TargetedSecondEvidenceArtifact | None,
    *,
    asr_result: ASRResult,
    require_source_indexes: tuple[int, ...] | frozenset[int] | set[int],
) -> dict[str, TargetedSecondEvidenceReviewProjection]:
    """Validate and project one caller-held targeted artifact by ASR identity.

    The current ASR result is used to derive the existing canonical artifact
    digest.  No new digest scheme is introduced.  Every targeted source must
    still be a current ``REQUIRE_SECOND_EVIDENCE`` source, and every source
    binding must match its current baseline text/timing before projection.
    """

    if artifact is None:
        return {}
    if type(asr_result) is not ASRResult:
        raise TargetedSecondEvidenceProjectionError(
            "targeted projection requires an exact ASRResult"
        )
    try:
        asr_result.__post_init__()
    except Exception as error:
        raise TargetedSecondEvidenceProjectionError(
            "targeted projection ASRResult is invalid"
        ) from error
    if type(require_source_indexes) not in {tuple, set, frozenset}:
        raise TargetedSecondEvidenceProjectionError(
            "targeted REQUIRE source indexes must be immutable or set-like"
        )
    required = set(require_source_indexes)
    if any(
        type(index) is not int or not 0 <= index < MAX_ASR_SEGMENTS
        for index in required
    ):
        raise TargetedSecondEvidenceProjectionError(
            "targeted REQUIRE source index is invalid"
        )
    if len(required) != len(require_source_indexes):
        raise TargetedSecondEvidenceProjectionError(
            "targeted REQUIRE source indexes contain duplicates"
        )

    baseline_sha = hashlib.sha256(serialize_asr_result(asr_result)).hexdigest()
    try:
        validated_artifact = require_matching_targeted_second_evidence_context(
            artifact,
            source_snapshot=asr_result.source_snapshot,
            baseline_asr_artifact_sha256=baseline_sha,
        )
        bindings = validated_artifact.bindings
    except Exception as error:
        raise TargetedSecondEvidenceProjectionError(
            "targeted artifact is invalid or detached"
        ) from error

    bound_indexes = {binding.source.source_index for binding in bindings}
    if bound_indexes != required:
        raise TargetedSecondEvidenceProjectionError(
            "targeted artifact source coverage differs from REQUIRE sources"
        )

    projected: dict[str, TargetedSecondEvidenceReviewProjection] = {}
    for binding in bindings:
        try:
            source = binding.source
            source_index = source.source_index
            if source_index not in required:
                raise TargetedSecondEvidenceProjectionError(
                    "targeted binding is not a REQUIRE source"
                )
            baseline = asr_result.segments[source_index]
            if (
                source.cue_id in projected
                or source.start_ms != baseline.start_ms
                or source.end_ms != baseline.end_ms
                or source.source_text != baseline.text
            ):
                raise TargetedSecondEvidenceProjectionError(
                    "targeted source binding differs from baseline ASR"
                )
            projected[source.cue_id] = _project_binding(binding)
        except TargetedSecondEvidenceProjectionError:
            raise
        except (AttributeError, IndexError, TypeError, ValueError) as error:
            raise TargetedSecondEvidenceProjectionError(
                "targeted source binding cannot be projected"
            ) from error
    return projected


__all__ = [
    "TARGETED_SECOND_EVIDENCE_REVIEW_FIELDS",
    "TargetedSecondEvidenceProjectionError",
    "TargetedSecondEvidenceReviewProjection",
    "parse_targeted_second_evidence_review_projection",
    "project_targeted_second_evidence_artifact",
]
