"""Pure, bounded projection of retained subtitle evidence for Hermes input.

The source objects passed to this module remain the authoritative evidence.
Only a deterministic model-input copy is projected, and only contiguous
pathological repetition is bounded.  This module deliberately does not know
about titles, cue identities, routes, timestamps, or publication.
"""

from __future__ import annotations

from dataclasses import dataclass
import unicodedata
from typing import Final

from teddy_discovery_hermes_v2 import (
    HermesV2CueInput,
    HermesV2Request,
)


MODEL_INPUT_NORMALIZATION_VERSION: Final[str] = (
    "stage11-model-input=repeat-v2"
)
MODEL_INPUT_PATHOLOGICAL_RUN_FLOOR: Final[int] = 64
MODEL_INPUT_SHORT_UNIT_MAX: Final[int] = 4
MODEL_INPUT_PERIODIC_MIN_REPETITIONS: Final[int] = 16
MODEL_INPUT_REPRESENTATIVE_REPETITIONS: Final[int] = 2

# These aliases make the contract easy to discover beside the existing
# stateful-part constants without creating a second policy.
MODEL_INPUT_PATHOLOGICAL_TEXT_FLOOR: Final[int] = (
    MODEL_INPUT_PATHOLOGICAL_RUN_FLOOR
)
MODEL_INPUT_MAX_SHORT_UNIT_CHARS: Final[int] = MODEL_INPUT_SHORT_UNIT_MAX
MODEL_INPUT_MIN_PERIODIC_REPETITIONS: Final[int] = (
    MODEL_INPUT_PERIODIC_MIN_REPETITIONS
)

_PATHOLOGICAL_REPEAT_RULE: Final[str] = "pathological-repeat-v2"
_PUNCTUATION_RUN_FLOOR: Final[int] = MODEL_INPUT_PATHOLOGICAL_RUN_FLOOR
_HORIZONTAL_SEPARATOR_MAX: Final[int] = 4


class ModelInputNormalizationError(ValueError):
    """Raised when a model-input projection receives an invalid object."""


@dataclass(frozen=True)
class ModelInputNormalizationEvent:
    """One bounded source span and its deterministic model replacement."""

    field_name: str
    source_start: int
    source_end: int
    unit_length: int
    separator_length: int
    complete_repetitions: int
    trailing_prefix_length: int
    replacement_length: int

    def __post_init__(self) -> None:
        if type(self.field_name) is not str or not self.field_name:
            raise ModelInputNormalizationError(
                "normalization event field_name must be nonempty"
            )
        if type(self.source_start) is not int or self.source_start < 0:
            raise ModelInputNormalizationError(
                "normalization event source_start is invalid"
            )
        if type(self.source_end) is not int or self.source_end <= self.source_start:
            raise ModelInputNormalizationError(
                "normalization event source_end is invalid"
            )
        if type(self.unit_length) is not int or not (
            1 <= self.unit_length <= MODEL_INPUT_SHORT_UNIT_MAX
        ):
            raise ModelInputNormalizationError(
                "normalization event unit_length is outside its bound"
            )
        if type(self.separator_length) is not int or not (
            0 <= self.separator_length <= _HORIZONTAL_SEPARATOR_MAX
        ):
            raise ModelInputNormalizationError(
                "normalization event separator_length is outside its bound"
            )
        if type(self.complete_repetitions) is not int or self.complete_repetitions < 1:
            raise ModelInputNormalizationError(
                "normalization event repetition count is invalid"
            )
        if type(self.trailing_prefix_length) is not int or not (
            0 <= self.trailing_prefix_length < self.unit_length
        ):
            raise ModelInputNormalizationError(
                "normalization event trailing prefix is invalid"
            )
        expected_source_length = (
            self.unit_length * self.complete_repetitions
            + self.separator_length * max(self.complete_repetitions - 1, 0)
            + self.trailing_prefix_length
        )
        if self.source_end - self.source_start != expected_source_length:
            raise ModelInputNormalizationError(
                "normalization event source span is inconsistent"
            )
        if type(self.replacement_length) is not int or self.replacement_length <= 0:
            raise ModelInputNormalizationError(
                "normalization event replacement length is invalid"
            )


@dataclass(frozen=True)
class ModelInputNormalization:
    """Result of normalizing one exact text value."""

    normalized_text: str
    changed: bool
    rule: str | None
    original_length: int
    normalized_length: int
    events: tuple[ModelInputNormalizationEvent, ...]

    def __post_init__(self) -> None:
        if type(self.normalized_text) is not str:
            raise ModelInputNormalizationError(
                "normalized_text must be an exact string"
            )
        if type(self.changed) is not bool:
            raise ModelInputNormalizationError(
                "normalization changed flag must be boolean"
            )
        if self.rule not in {None, _PATHOLOGICAL_REPEAT_RULE}:
            raise ModelInputNormalizationError(
                "normalization rule is unsupported"
            )
        if type(self.original_length) is not int or self.original_length < 0:
            raise ModelInputNormalizationError(
                "normalization original length is invalid"
            )
        if type(self.normalized_length) is not int or self.normalized_length < 0:
            raise ModelInputNormalizationError(
                "normalization normalized length is invalid"
            )
        if self.normalized_length != len(self.normalized_text):
            raise ModelInputNormalizationError(
                "normalization normalized length is detached"
            )
        if type(self.events) is not tuple or any(
            type(event) is not ModelInputNormalizationEvent
            for event in self.events
        ):
            raise ModelInputNormalizationError(
                "normalization events must be an immutable tuple"
            )
        if self.changed != bool(self.events) or (
            self.changed and self.rule is None
        ) or (not self.changed and self.rule is not None):
            raise ModelInputNormalizationError(
                "normalization metadata is inconsistent"
            )


@dataclass(frozen=True)
class ModelInputCueProjection:
    """Raw cue plus its immutable model-input projection."""

    raw_cue: HermesV2CueInput
    model_cue: HermesV2CueInput
    events: tuple[ModelInputNormalizationEvent, ...]

    @property
    def changed(self) -> bool:
        return bool(self.events)


@dataclass(frozen=True)
class ModelInputRequestProjection:
    """Raw Hermes request plus its immutable model-input projection."""

    raw_request: HermesV2Request
    model_request: HermesV2Request
    events: tuple[ModelInputNormalizationEvent, ...]

    @property
    def changed(self) -> bool:
        return bool(self.events)


def _empty_result(text: str) -> ModelInputNormalization:
    return ModelInputNormalization(
        normalized_text=text,
        changed=False,
        rule=None,
        original_length=len(text),
        normalized_length=len(text),
        events=(),
    )


def _safe_unit(unit: str) -> bool:
    """Reject Unicode structures whose codepoints are not safe to split."""

    if not unit:
        return False
    for character in unit:
        category = unicodedata.category(character)
        if character.isspace() or category[0] == "C":
            return False
        # A combining mark or format character can be part of a grapheme or
        # shaping sequence.  Leaving that structure intact is safer than
        # guessing at a codepoint-level replacement.
        if category[0] in {"M", "C"} or unicodedata.combining(character):
            return False
        codepoint = ord(character)
        if 0x1F1E6 <= codepoint <= 0x1F1FF:
            # Two regional indicators form one flag grapheme; a codepoint
            # repetition scan must not split or compress that structure.
            return False
        name = unicodedata.name(character, "")
        if "VARIATION SELECTOR" in name or "EMOJI MODIFIER" in name:
            return False
    return True


def _safe_boundary(text: str, start: int, end: int) -> bool:
    """Do not normalize a run adjacent to a combining/format structure."""

    for position in (start - 1, end):
        if not 0 <= position < len(text):
            continue
        character = text[position]
        category = unicodedata.category(character)
        if category[0] in {"M", "C"} or unicodedata.combining(character):
            return False
        name = unicodedata.name(character, "")
        if (
            "VARIATION SELECTOR" in name
            or "EMOJI MODIFIER" in name
            or 0x1F1E6 <= ord(character) <= 0x1F1FF
        ):
            return False
    return True


def _all_punctuation_or_symbols(unit: str) -> bool:
    return bool(unit) and all(
        unicodedata.category(character)[0] in {"P", "S"}
        for character in unit
    )


@dataclass(frozen=True)
class _RepeatCandidate:
    end: int
    unit: str
    separator: str
    repetitions: int
    trailing_prefix_length: int
    replacement: str


def _repeat_qualifies(
    unit: str,
    repetitions: int,
) -> bool:
    unit_length = len(unit)
    if unit_length == 1:
        return (
            repetitions * unit_length
            >= MODEL_INPUT_PATHOLOGICAL_RUN_FLOOR
        )
    if repetitions < MODEL_INPUT_PERIODIC_MIN_REPETITIONS:
        return False
    if (
        _all_punctuation_or_symbols(unit)
        and repetitions * unit_length < _PUNCTUATION_RUN_FLOOR
    ):
        return False
    return True


def _horizontal_separator_at(
    text: str,
    start: int,
) -> str | None:
    """Return one short horizontal-whitespace separator without crossing lines."""

    if not 0 <= start < len(text):
        return None

    cursor = start
    while cursor < len(text) and text[cursor].isspace():
        character = text[cursor]
        category = unicodedata.category(character)
        if character in {"\r", "\n", "\v", "\f"} or category in {"Zl", "Zp"}:
            return None
        cursor += 1
        if cursor - start > _HORIZONTAL_SEPARATOR_MAX:
            return None

    if cursor == start:
        return None
    return text[start:cursor]


def _candidate_at(text: str, start: int) -> _RepeatCandidate | None:
    remaining = len(text) - start
    max_unit_length = min(MODEL_INPUT_SHORT_UNIT_MAX, remaining)

    # The shortest valid unit wins.  Contiguous repetition remains the first
    # choice.  repeat-v2 additionally accepts one identical, bounded,
    # horizontal-whitespace separator between complete units.  It never spans
    # a line boundary and never rewrites the authoritative source object.
    for unit_length in range(1, max_unit_length + 1):
        unit = text[start : start + unit_length]
        if not _safe_unit(unit):
            continue
        if unit_length > 1 and len(set(unit)) == 1:
            # Do not turn a sub-threshold single-codepoint run into a
            # qualifying two- or three-codepoint unit.
            continue

        repetitions = 0
        cursor = start
        while cursor + unit_length <= len(text):
            if text[cursor : cursor + unit_length] != unit:
                break
            repetitions += 1
            cursor += unit_length

        if _repeat_qualifies(unit, repetitions):
            trailing_prefix_length = 0
            for prefix_length in range(1, unit_length):
                if text[cursor : cursor + prefix_length] == unit[:prefix_length]:
                    trailing_prefix_length = prefix_length

            end = cursor + trailing_prefix_length
            if _safe_boundary(text, start, end):
                replacement = (
                    unit * MODEL_INPUT_REPRESENTATIVE_REPETITIONS
                    + unit[:trailing_prefix_length]
                )
                return _RepeatCandidate(
                    end=end,
                    unit=unit,
                    separator="",
                    repetitions=repetitions,
                    trailing_prefix_length=trailing_prefix_length,
                    replacement=replacement,
                )

        # Separated repetition is deliberately narrower than contiguous
        # repetition: only an identical short horizontal-whitespace separator
        # is accepted, and only complete units are bounded.
        separator_start = start + unit_length
        separator = _horizontal_separator_at(text, separator_start)
        if separator is None:
            continue

        repetitions = 1
        cursor = separator_start
        while True:
            if text[cursor : cursor + len(separator)] != separator:
                break
            next_unit_start = cursor + len(separator)
            if (
                text[next_unit_start : next_unit_start + unit_length]
                != unit
            ):
                break
            repetitions += 1
            cursor = next_unit_start + unit_length

        if not _repeat_qualifies(unit, repetitions):
            continue

        end = cursor
        if not _safe_boundary(text, start, end):
            continue

        replacement = separator.join(
            unit for _ in range(MODEL_INPUT_REPRESENTATIVE_REPETITIONS)
        )
        return _RepeatCandidate(
            end=end,
            unit=unit,
            separator=separator,
            repetitions=repetitions,
            trailing_prefix_length=0,
            replacement=replacement,
        )

    return None


def normalize_model_input_text(
    raw_text: str,
    *,
    field_name: str = "text",
) -> ModelInputNormalization:
    """Bound contiguous pathological repetition in one retained text value.

    No whitespace normalization, punctuation cleanup, Unicode normalization,
    or semantic cleanup is performed.  repeat-v2 may recognize one identical
    bounded horizontal-whitespace separator between repeated short units, but
    preserves that separator in the representative model input.  A
    single-codepoint run needs at least 64 codepoints; a
    distinct short unit of at most four codepoints needs at least 16 complete
    repetitions.  The repeated span is replaced by two representative units,
    plus one existing partial prefix when present.  Unicode combining/format
    structures fail closed and remain byte-for-byte unchanged.
    """

    if type(raw_text) is not str:
        raise ModelInputNormalizationError(
            field_name + " must be an exact string"
        )
    if not raw_text:
        return _empty_result(raw_text)

    output: list[str] = []
    events: list[ModelInputNormalizationEvent] = []
    cursor = 0
    while cursor < len(raw_text):
        candidate = _candidate_at(raw_text, cursor)
        if candidate is None:
            output.append(raw_text[cursor])
            cursor += 1
            continue

        replacement = candidate.replacement
        output.append(replacement)
        events.append(
            ModelInputNormalizationEvent(
                field_name=field_name,
                source_start=cursor,
                source_end=candidate.end,
                unit_length=len(candidate.unit),
                separator_length=len(candidate.separator),
                complete_repetitions=candidate.repetitions,
                trailing_prefix_length=candidate.trailing_prefix_length,
                replacement_length=len(replacement),
            )
        )
        cursor = candidate.end

    normalized_text = "".join(output)
    if not events:
        return _empty_result(raw_text)
    return ModelInputNormalization(
        normalized_text=normalized_text,
        changed=True,
        rule=_PATHOLOGICAL_REPEAT_RULE,
        original_length=len(raw_text),
        normalized_length=len(normalized_text),
        events=tuple(events),
    )


def _normalize_field(
    value: str | None,
    *,
    field_name: str,
) -> tuple[str | None, tuple[ModelInputNormalizationEvent, ...]]:
    if value is None:
        return None, ()
    result = normalize_model_input_text(value, field_name=field_name)
    return result.normalized_text, result.events


def normalize_model_input_cue(
    raw_cue: HermesV2CueInput,
) -> ModelInputCueProjection:
    """Project one cue while retaining the exact raw cue object separately."""

    if type(raw_cue) is not HermesV2CueInput:
        raise ModelInputNormalizationError(
            "raw_cue must be an exact HermesV2CueInput"
        )

    external_ja, external_events = _normalize_field(
        raw_cue.external_ja,
        field_name="external_ja",
    )
    stt_ja, stt_events = _normalize_field(
        raw_cue.stt_ja,
        field_name="stt_ja",
    )
    en, en_events = _normalize_field(raw_cue.en, field_name="en")

    before_values: list[str] = []
    before_events: list[ModelInputNormalizationEvent] = []
    for index, value in enumerate(raw_cue.before_context):
        normalized, events = _normalize_field(
            value,
            field_name="before_context[" + str(index) + "]",
        )
        assert normalized is not None
        before_values.append(normalized)
        before_events.extend(events)

    after_values: list[str] = []
    after_events: list[ModelInputNormalizationEvent] = []
    for index, value in enumerate(raw_cue.after_context):
        normalized, events = _normalize_field(
            value,
            field_name="after_context[" + str(index) + "]",
        )
        assert normalized is not None
        after_values.append(normalized)
        after_events.extend(events)

    events = tuple(
        external_events
        + stt_events
        + en_events
        + tuple(before_events)
        + tuple(after_events)
    )
    if not events:
        model_cue = raw_cue
    else:
        model_cue = HermesV2CueInput(
            cue_id=raw_cue.cue_id,
            external_ja=external_ja,
            stt_ja=stt_ja,
            en=en,
            before_context=tuple(before_values),
            after_context=tuple(after_values),
        )
    return ModelInputCueProjection(
        raw_cue=raw_cue,
        model_cue=model_cue,
        events=events,
    )


def normalize_model_input_request(
    raw_request: HermesV2Request,
) -> ModelInputRequestProjection:
    """Project every retained text field in one Hermes request."""

    if type(raw_request) is not HermesV2Request:
        raise ModelInputNormalizationError(
            "raw_request must be an exact HermesV2Request"
        )
    projections = tuple(
        normalize_model_input_cue(cue)
        for cue in raw_request.cues
    )
    events: list[ModelInputNormalizationEvent] = []
    for projection in projections:
        events.extend(projection.events)
    if not events:
        model_request = raw_request
    else:
        model_request = HermesV2Request(
            cues=tuple(projection.model_cue for projection in projections)
        )
    return ModelInputRequestProjection(
        raw_request=raw_request,
        model_request=model_request,
        events=tuple(events),
    )


__all__ = [
    "MODEL_INPUT_MAX_SHORT_UNIT_CHARS",
    "MODEL_INPUT_MIN_PERIODIC_REPETITIONS",
    "MODEL_INPUT_NORMALIZATION_VERSION",
    "MODEL_INPUT_PATHOLOGICAL_RUN_FLOOR",
    "MODEL_INPUT_PATHOLOGICAL_TEXT_FLOOR",
    "MODEL_INPUT_PERIODIC_MIN_REPETITIONS",
    "MODEL_INPUT_REPRESENTATIVE_REPETITIONS",
    "MODEL_INPUT_SHORT_UNIT_MAX",
    "ModelInputCueProjection",
    "ModelInputNormalization",
    "ModelInputNormalizationError",
    "ModelInputNormalizationEvent",
    "ModelInputRequestProjection",
    "normalize_model_input_cue",
    "normalize_model_input_request",
    "normalize_model_input_text",
]
