"""Deterministic, route-neutral ASR source-quality evidence.

This module classifies an immutable, already validated ASR segment sequence.
It does not know about external subtitles, alignment, Hybrid, STT-only
translation, models, files, or publication.  The original segment index,
text, and timing remain the identity owned by the caller.

The existing narrow non-lexical classifier is the only hard-OMIT authority.
Feature observations and action severity are separate: the explicit
``features`` tuple records every observation, while only intra-cue structural
repetition is currently actionable as ``REQUIRE_SECOND_EVIDENCE``.  No source
text is rewritten and no cue is removed by this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
import unicodedata

from teddy_discovery_asr import (
    ASRResult,
    ASRSegment,
    MAX_ASR_SEGMENTS,
)
from teddy_discovery_nonlexical import (
    NONLEXICAL_KEEP,
    NONLEXICAL_OMIT,
    NONLEXICAL_REASON_REPEATED_PURE_VOCALIC_RUN,
    NonLexicalDecision,
    classify_nonlexical,
)
from teddy_discovery_stateful_parts import has_runaway_repetition


ASR_SOURCE_KEEP: Final = "KEEP"
ASR_SOURCE_OMIT: Final = "OMIT"
ASR_SOURCE_REQUIRE_SECOND_EVIDENCE: Final = "REQUIRE_SECOND_EVIDENCE"

ASR_SOURCE_REASON_EXISTING_RUNAWAY: Final = "existing_runaway_repetition"
ASR_SOURCE_REASON_INTRA_CUE_REPETITION: Final = (
    "intra_cue_structural_repetition"
)
ASR_SOURCE_REASON_CONSECUTIVE_RUN: Final = (
    "consecutive_identical_segment_run"
)
ASR_SOURCE_REASON_DOCUMENT_RECURRENCE: Final = (
    "document_recurrent_text"
)

ASR_SOURCE_FEATURE_ORDER: Final = (
    NONLEXICAL_REASON_REPEATED_PURE_VOCALIC_RUN,
    ASR_SOURCE_REASON_INTRA_CUE_REPETITION,
    ASR_SOURCE_REASON_CONSECUTIVE_RUN,
    ASR_SOURCE_REASON_DOCUMENT_RECURRENCE,
    ASR_SOURCE_REASON_EXISTING_RUNAWAY,
)
ASR_SOURCE_KNOWN_FEATURES: Final = frozenset(ASR_SOURCE_FEATURE_ORDER)

# These bounds are deliberately suspicious-only.  They never create a new
# destructive action and are kept separate from the frozen whole-string
# result-output validator.
ASR_SOURCE_MAX_INTRA_UNIT_CHARS: Final = 4
ASR_SOURCE_MIN_INTRA_REPETITIONS: Final = 4
ASR_SOURCE_MIN_CONSECUTIVE_IDENTICAL_SEGMENTS: Final = 3
ASR_SOURCE_MIN_DOCUMENT_RECURRENCE_OCCURRENCES: Final = 3


class ASRSourceQualityError(ValueError):
    """Invalid source-quality input or detached decision evidence."""


def _validate_features(features: object) -> tuple[str, ...]:
    if type(features) is not tuple:
        raise ASRSourceQualityError("decision features must be an immutable tuple")
    if any(type(feature) is not str for feature in features):
        raise ASRSourceQualityError("decision feature is not an exact string")
    if any(feature not in ASR_SOURCE_KNOWN_FEATURES for feature in features):
        raise ASRSourceQualityError("decision feature is unknown")
    if len(set(features)) != len(features):
        raise ASRSourceQualityError("decision features must be unique")
    expected_order = tuple(
        feature
        for feature in ASR_SOURCE_FEATURE_ORDER
        if feature in features
    )
    if features != expected_order:
        raise ASRSourceQualityError("decision features are not deterministically ordered")
    return features


def _validate_text(text: object, *, field_name: str) -> str:
    if type(text) is not str or not text.strip():
        raise ASRSourceQualityError(field_name + " must be a nonempty exact string")
    try:
        ASRSegment(0, 1, text)
    except Exception as error:
        raise ASRSourceQualityError(field_name + " is not a valid ASR text") from error
    return text


def _validate_index(index: object, *, field_name: str = "source_index") -> int:
    if type(index) is not int or not 0 <= index < MAX_ASR_SEGMENTS:
        raise ASRSourceQualityError(field_name + " is outside the ASR bound")
    return index


def _validate_timing(
    start_ms: object,
    end_ms: object,
    *,
    field_name: str,
) -> tuple[int, int]:
    if (
        type(start_ms) is not int
        or type(end_ms) is not int
        or start_ms < 0
        or end_ms <= start_ms
    ):
        raise ASRSourceQualityError(field_name + " is not a valid ASR interval")
    return start_ms, end_ms


def _validated_segments(value: object) -> tuple[ASRSegment, ...]:
    if type(value) is not tuple:
        raise ASRSourceQualityError("segments must be an immutable tuple")
    if not value:
        raise ASRSourceQualityError("segments must not be empty")
    if len(value) > MAX_ASR_SEGMENTS:
        raise ASRSourceQualityError("segments exceed MAX_ASR_SEGMENTS")

    validated: list[ASRSegment] = []
    previous_start_ms = None
    for segment in value:
        if type(segment) is not ASRSegment:
            raise ASRSourceQualityError("segments must contain ASRSegment values")
        try:
            candidate = ASRSegment(
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                text=segment.text,
                words=segment.words,
            )
        except Exception as error:
            raise ASRSourceQualityError("segment is invalid or detached") from error
        if candidate != segment:
            raise ASRSourceQualityError("segment identity or text is detached")
        if (
            previous_start_ms is not None
            and segment.start_ms < previous_start_ms
        ):
            raise ASRSourceQualityError("segment order is not source ordered")
        previous_start_ms = segment.start_ms
        validated.append(candidate)
    return tuple(validated)


def _document_key(text: str) -> str:
    """Return a classification-only key preserving punctuation and wording."""

    return " ".join(unicodedata.normalize("NFKC", text).split())


def _structural_analysis_view(text: str) -> str:
    """Remove only Unicode punctuation/separators for a repeat observation."""

    normalized = unicodedata.normalize("NFKC", text)
    return "".join(
        character
        for character in normalized
        if not character.isspace()
        and not unicodedata.category(character).startswith(("P", "Z"))
    )


def _repeated_short_unit(text: str) -> tuple[str, int] | None:
    analysis = _structural_analysis_view(text)
    if not analysis:
        return None

    maximum_unit_chars = min(
        ASR_SOURCE_MAX_INTRA_UNIT_CHARS,
        len(analysis),
    )
    for unit_chars in range(1, maximum_unit_chars + 1):
        if len(analysis) % unit_chars:
            continue
        repetitions = len(analysis) // unit_chars
        if repetitions < ASR_SOURCE_MIN_INTRA_REPETITIONS:
            continue
        unit = analysis[:unit_chars]
        if unit * repetitions == analysis:
            return unit, repetitions
    return None


def _consecutive_run_lengths(keys: tuple[str, ...]) -> tuple[int, ...]:
    lengths = [1] * len(keys)
    start = 0
    while start < len(keys):
        end = start + 1
        while end < len(keys) and keys[end] == keys[start]:
            end += 1
        length = end - start
        if length >= ASR_SOURCE_MIN_CONSECUTIVE_IDENTICAL_SEGMENTS:
            for index in range(start, end):
                lengths[index] = length
        start = end
    return tuple(lengths)


@dataclass(frozen=True)
class ASRSourceQualityEvidence:
    """Bounded, immutable observations for one original ASR segment."""

    source_index: int
    start_ms: int
    end_ms: int
    nonlexical_action: str
    nonlexical_reason: str
    existing_runaway: bool
    intra_cue_unit: str | None
    intra_cue_repetitions: int
    consecutive_run_length: int
    document_frequency: int
    document_first_index: int
    document_last_index: int
    document_span_ms: int

    def __post_init__(self):
        _validate_index(self.source_index)
        _validate_timing(
            self.start_ms,
            self.end_ms,
            field_name="evidence timing",
        )
        if self.nonlexical_action not in {NONLEXICAL_KEEP, NONLEXICAL_OMIT}:
            raise ASRSourceQualityError("evidence nonlexical action is invalid")
        if type(self.nonlexical_reason) is not str or not self.nonlexical_reason:
            raise ASRSourceQualityError("evidence nonlexical reason is invalid")
        if type(self.existing_runaway) is not bool:
            raise ASRSourceQualityError("evidence runaway flag is invalid")
        if self.intra_cue_unit is not None:
            _validate_text(self.intra_cue_unit, field_name="intra cue unit")
            if not 1 <= len(self.intra_cue_unit) <= ASR_SOURCE_MAX_INTRA_UNIT_CHARS:
                raise ASRSourceQualityError("intra cue unit is outside its bound")
        elif self.intra_cue_repetitions != 0:
            raise ASRSourceQualityError("intra cue repetition count is detached")
        if type(self.intra_cue_repetitions) is not int or self.intra_cue_repetitions < 0:
            raise ASRSourceQualityError("intra cue repetition count is invalid")
        if (
            self.intra_cue_unit is not None
            and self.intra_cue_repetitions < ASR_SOURCE_MIN_INTRA_REPETITIONS
        ):
            raise ASRSourceQualityError("intra cue repetition count is too small")
        if type(self.consecutive_run_length) is not int or self.consecutive_run_length < 1:
            raise ASRSourceQualityError("consecutive run length is invalid")
        if type(self.document_frequency) is not int or self.document_frequency < 1:
            raise ASRSourceQualityError("document frequency is invalid")
        _validate_index(self.document_first_index, field_name="document_first_index")
        _validate_index(self.document_last_index, field_name="document_last_index")
        if self.document_first_index > self.document_last_index:
            raise ASRSourceQualityError("document recurrence indexes are unordered")
        if type(self.document_span_ms) is not int or self.document_span_ms < 0:
            raise ASRSourceQualityError("document recurrence span is invalid")


@dataclass(frozen=True)
class ASRSourceQualityDecision:
    """One source-index-bound decision; it never owns a rewritten cue."""

    source_index: int
    start_ms: int
    end_ms: int
    source_text: str
    action: str
    reason: str
    evidence_reasons: tuple[str, ...]
    evidence: ASRSourceQualityEvidence
    features: tuple[str, ...] = ()

    def __post_init__(self):
        _validate_index(self.source_index)
        _validate_timing(
            self.start_ms,
            self.end_ms,
            field_name="decision timing",
        )
        _validate_text(self.source_text, field_name="decision source_text")
        if self.action not in {
            ASR_SOURCE_KEEP,
            ASR_SOURCE_OMIT,
            ASR_SOURCE_REQUIRE_SECOND_EVIDENCE,
        }:
            raise ASRSourceQualityError("decision action is invalid")
        if type(self.reason) is not str or not self.reason:
            raise ASRSourceQualityError("decision reason is invalid")
        if type(self.evidence_reasons) is not tuple:
            raise ASRSourceQualityError("decision evidence reasons must be a tuple")
        if any(type(reason) is not str or not reason for reason in self.evidence_reasons):
            raise ASRSourceQualityError("decision evidence reason is invalid")
        if len(set(self.evidence_reasons)) != len(self.evidence_reasons):
            raise ASRSourceQualityError("decision evidence reasons must be unique")
        _validate_features(self.features)
        if type(self.evidence) is not ASRSourceQualityEvidence:
            raise ASRSourceQualityError("decision evidence has the wrong type")
        self.evidence.__post_init__()
        if (
            self.evidence.source_index != self.source_index
            or self.evidence.start_ms != self.start_ms
            or self.evidence.end_ms != self.end_ms
            or (
                self.evidence.nonlexical_action == NONLEXICAL_OMIT
                and self.action != ASR_SOURCE_OMIT
            )
        ):
            raise ASRSourceQualityError("decision evidence is detached")
        if self.action == ASR_SOURCE_OMIT:
            if self.reason != NONLEXICAL_REASON_REPEATED_PURE_VOCALIC_RUN:
                raise ASRSourceQualityError("new hard OMIT reason is not allowed")
            if self.evidence.nonlexical_action != NONLEXICAL_OMIT:
                raise ASRSourceQualityError("OMIT is detached from nonlexical classifier")
            if self.reason not in self.evidence_reasons:
                raise ASRSourceQualityError("OMIT reason is not in evidence")
        elif self.action == ASR_SOURCE_REQUIRE_SECOND_EVIDENCE:
            if not self.evidence_reasons:
                raise ASRSourceQualityError("suspicious decision lacks evidence")
            if self.reason not in self.evidence_reasons:
                raise ASRSourceQualityError("suspicious primary reason is detached")
        elif self.evidence_reasons:
            raise ASRSourceQualityError("KEEP decision carries suspicious evidence")


@dataclass(frozen=True)
class ASRSourceQualityHint:
    """Compact route-facing provenance without timing authority.

    Full ``ASRSourceQualityDecision`` values remain available to preparation
    callers.  Review requests carry this bounded projection so that a model is
    given the action/reason/evidence-reasons/features observation without being given a second
    timing authority or the full classifier evidence object.
    """

    source_index: int
    action: str
    reason: str
    features: tuple[str, ...] = ()
    evidence_reasons: tuple[str, ...] = ()

    def __post_init__(self):
        _validate_index(self.source_index)
        if self.action not in {
            ASR_SOURCE_KEEP,
            ASR_SOURCE_OMIT,
            ASR_SOURCE_REQUIRE_SECOND_EVIDENCE,
        }:
            raise ASRSourceQualityError("hint action is invalid")
        if type(self.reason) is not str or not self.reason.strip():
            raise ASRSourceQualityError("hint reason is invalid")
        _validate_features(self.features)
        if type(self.evidence_reasons) is not tuple:
            raise ASRSourceQualityError(
                "hint evidence reasons must be an immutable tuple"
            )
        if any(
            type(reason) is not str or not reason.strip()
            for reason in self.evidence_reasons
        ):
            raise ASRSourceQualityError("hint evidence reason is invalid")
        if len(set(self.evidence_reasons)) != len(self.evidence_reasons):
            raise ASRSourceQualityError(
                "hint evidence reasons must be unique"
            )

    @classmethod
    def from_decision(cls, decision: ASRSourceQualityDecision):
        if type(decision) is not ASRSourceQualityDecision:
            raise ASRSourceQualityError("hint requires an exact source-quality decision")
        decision.__post_init__()
        return cls(
            source_index=decision.source_index,
            action=decision.action,
            reason=decision.reason,
            features=decision.features,
            evidence_reasons=decision.evidence_reasons,
        )


def classify_asr_source_quality(
    segments: tuple[ASRSegment, ...],
) -> tuple[ASRSourceQualityDecision, ...]:
    """Classify one complete validated ASR sequence without changing it."""

    validated = _validated_segments(segments)
    document_keys = tuple(_document_key(segment.text) for segment in validated)
    document_groups: dict[str, list[int]] = {}
    for index, key in enumerate(document_keys):
        document_groups.setdefault(key, []).append(index)
    run_lengths = _consecutive_run_lengths(document_keys)

    decisions: list[ASRSourceQualityDecision] = []
    for source_index, segment in enumerate(validated):
        try:
            nonlexical = classify_nonlexical(segment.text)
            if type(nonlexical) is not NonLexicalDecision:
                raise ASRSourceQualityError(
                    "classify_nonlexical returned the wrong decision type"
                )
            existing_runaway = has_runaway_repetition(segment.text)
        except ASRSourceQualityError:
            raise
        except Exception as error:
            raise ASRSourceQualityError(
                "existing ASR source helper failed closed"
            ) from error

        repeated = _repeated_short_unit(segment.text)
        group = document_groups[document_keys[source_index]]
        first_index = group[0]
        last_index = group[-1]
        evidence = ASRSourceQualityEvidence(
            source_index=source_index,
            start_ms=segment.start_ms,
            end_ms=segment.end_ms,
            nonlexical_action=nonlexical.action,
            nonlexical_reason=nonlexical.reason,
            existing_runaway=existing_runaway,
            intra_cue_unit=None if repeated is None else repeated[0],
            intra_cue_repetitions=0 if repeated is None else repeated[1],
            consecutive_run_length=run_lengths[source_index],
            document_frequency=len(group),
            document_first_index=first_index,
            document_last_index=last_index,
            document_span_ms=(
                validated[last_index].end_ms - validated[first_index].start_ms
            ),
        )

        suspicious_reasons: list[str] = []
        if existing_runaway:
            suspicious_reasons.append(ASR_SOURCE_REASON_EXISTING_RUNAWAY)
        if repeated is not None:
            suspicious_reasons.append(ASR_SOURCE_REASON_INTRA_CUE_REPETITION)
        if run_lengths[source_index] >= ASR_SOURCE_MIN_CONSECUTIVE_IDENTICAL_SEGMENTS:
            suspicious_reasons.append(ASR_SOURCE_REASON_CONSECUTIVE_RUN)
        if len(group) >= ASR_SOURCE_MIN_DOCUMENT_RECURRENCE_OCCURRENCES:
            suspicious_reasons.append(ASR_SOURCE_REASON_DOCUMENT_RECURRENCE)

        detected_features = set()
        if nonlexical.reason == NONLEXICAL_REASON_REPEATED_PURE_VOCALIC_RUN:
            detected_features.add(NONLEXICAL_REASON_REPEATED_PURE_VOCALIC_RUN)
        if repeated is not None:
            detected_features.add(ASR_SOURCE_REASON_INTRA_CUE_REPETITION)
        if run_lengths[source_index] >= ASR_SOURCE_MIN_CONSECUTIVE_IDENTICAL_SEGMENTS:
            detected_features.add(ASR_SOURCE_REASON_CONSECUTIVE_RUN)
        if len(group) >= ASR_SOURCE_MIN_DOCUMENT_RECURRENCE_OCCURRENCES:
            detected_features.add(ASR_SOURCE_REASON_DOCUMENT_RECURRENCE)
        if existing_runaway:
            detected_features.add(ASR_SOURCE_REASON_EXISTING_RUNAWAY)
        features = tuple(
            feature
            for feature in ASR_SOURCE_FEATURE_ORDER
            if feature in detected_features
        )

        if nonlexical.action == NONLEXICAL_OMIT:
            action = ASR_SOURCE_OMIT
            reason = nonlexical.reason
            hard_evidence_reasons = [nonlexical.reason]
            for suspicious_reason in suspicious_reasons:
                if suspicious_reason not in hard_evidence_reasons:
                    hard_evidence_reasons.append(suspicious_reason)
            evidence_reasons = tuple(hard_evidence_reasons)
        elif repeated is not None:
            action = ASR_SOURCE_REQUIRE_SECOND_EVIDENCE
            reason = ASR_SOURCE_REASON_INTRA_CUE_REPETITION
            evidence_reasons = tuple(suspicious_reasons)
        else:
            action = ASR_SOURCE_KEEP
            reason = nonlexical.reason
            evidence_reasons = ()

        decisions.append(
            ASRSourceQualityDecision(
                source_index=source_index,
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                source_text=segment.text,
                action=action,
                reason=reason,
                evidence_reasons=evidence_reasons,
                evidence=evidence,
                features=features,
            )
        )

    return tuple(decisions)


def classify_asr_result_source_quality(
    asr_result: ASRResult,
) -> tuple[ASRSourceQualityDecision, ...]:
    """Validate an ASR result and classify its original segment sequence."""

    if type(asr_result) is not ASRResult:
        raise ASRSourceQualityError("asr_result must be an exact ASRResult")
    try:
        asr_result.__post_init__()
    except Exception as error:
        raise ASRSourceQualityError("asr_result is invalid or detached") from error
    return classify_asr_source_quality(asr_result.segments)


def validate_asr_source_quality_decisions(
    segments: tuple[ASRSegment, ...],
    decisions: tuple[ASRSourceQualityDecision, ...],
) -> tuple[ASRSourceQualityDecision, ...]:
    """Re-prove decisions before a route-specific adapter applies them.

    This is the adapter boundary: callers may interpret ``OMIT`` or the
    suspicious-only action, but may not change the source index, text, or
    timing owned by the ASR sequence.
    """

    validated_segments = _validated_segments(segments)
    if type(decisions) is not tuple or len(decisions) != len(validated_segments):
        raise ASRSourceQualityError("decision coverage differs from ASR source")
    expected = classify_asr_source_quality(validated_segments)
    normalized_decisions = []
    for decision, expected_decision in zip(
        decisions,
        expected,
        strict=True,
    ):
        if type(decision) is not ASRSourceQualityDecision:
            raise ASRSourceQualityError("source-quality decision has wrong type")
        if decision.features not in {(), expected_decision.features}:
            raise ASRSourceQualityError("source-quality features differ from source")
        expected_without_features = ASRSourceQualityDecision(
            source_index=expected_decision.source_index,
            start_ms=expected_decision.start_ms,
            end_ms=expected_decision.end_ms,
            source_text=expected_decision.source_text,
            action=expected_decision.action,
            reason=expected_decision.reason,
            evidence_reasons=expected_decision.evidence_reasons,
            evidence=expected_decision.evidence,
            features=decision.features,
        )
        if decision != expected_without_features:
            raise ASRSourceQualityError("source-quality decisions differ from source")
        normalized_decisions.append(expected_decision)
    for source_index, (segment, decision) in enumerate(
        zip(validated_segments, decisions, strict=True)
    ):
        if (
            type(decision) is not ASRSourceQualityDecision
            or decision.source_index != source_index
            or decision.source_text != segment.text
            or decision.start_ms != segment.start_ms
            or decision.end_ms != segment.end_ms
        ):
            raise ASRSourceQualityError("source-quality decision identity is detached")
    return tuple(normalized_decisions)


def retained_asr_source_indexes(
    decisions: tuple[ASRSourceQualityDecision, ...],
) -> tuple[int, ...]:
    """Return original indexes that are not hard-OMIT decisions."""

    if type(decisions) is not tuple:
        raise ASRSourceQualityError("decisions must be an immutable tuple")
    for decision in decisions:
        if type(decision) is not ASRSourceQualityDecision:
            raise ASRSourceQualityError("decisions contain a detached value")
        decision.__post_init__()
    return tuple(
        decision.source_index
        for decision in decisions
        if decision.action != ASR_SOURCE_OMIT
    )


__all__ = [
    "ASR_SOURCE_KEEP",
    "ASR_SOURCE_OMIT",
    "ASR_SOURCE_REQUIRE_SECOND_EVIDENCE",
    "ASR_SOURCE_REASON_CONSECUTIVE_RUN",
    "ASR_SOURCE_REASON_DOCUMENT_RECURRENCE",
    "ASR_SOURCE_REASON_EXISTING_RUNAWAY",
    "ASR_SOURCE_REASON_INTRA_CUE_REPETITION",
    "ASR_SOURCE_FEATURE_ORDER",
    "ASR_SOURCE_KNOWN_FEATURES",
    "ASR_SOURCE_MAX_INTRA_UNIT_CHARS",
    "ASR_SOURCE_MIN_CONSECUTIVE_IDENTICAL_SEGMENTS",
    "ASR_SOURCE_MIN_DOCUMENT_RECURRENCE_OCCURRENCES",
    "ASR_SOURCE_MIN_INTRA_REPETITIONS",
    "ASRSourceQualityDecision",
    "ASRSourceQualityError",
    "ASRSourceQualityEvidence",
    "ASRSourceQualityHint",
    "classify_asr_result_source_quality",
    "classify_asr_source_quality",
    "retained_asr_source_indexes",
    "validate_asr_source_quality_decisions",
]
