"""Deterministic Stage11 Japanese cue translation routing.

This module owns only the control flow between the frozen text-only
non-lexical classifier and an injected single-cue translation callable.  It
does not parse or serialize subtitles, perform ASR, configure model transport,
or own filesystem, database, worker, publish, or completion state.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import unicodedata

from teddy_discovery_nonlexical import (
    NONLEXICAL_KEEP,
    NONLEXICAL_OMIT,
    NonLexicalDecision,
    classify_nonlexical,
)
from teddy_discovery_translation import (
    MAX_TRANSLATION_TEXT_CHARS,
    TRANSLATION_ACCEPTED,
    TRANSLATION_OMITTED,
    TranslationCue,
    TranslationOutcome,
)


ROUTE_FILTER_OMITTED = "FILTER_OMITTED"
ROUTE_TRANSLATION_ACCEPTED = "TRANSLATION_ACCEPTED"
ROUTE_TRANSLATION_OMITTED = "TRANSLATION_OMITTED"


class TranslationRouteError(Exception):
    """Base class for deterministic translation-route failures."""


class TranslationRouteValidationError(TranslationRouteError):
    """Raised for malformed caller-owned route input or configuration."""


class TranslationRouteContractError(TranslationRouteError):
    """Raised when an injected dependency violates its frozen contract."""


def _has_disallowed_control_characters(value: str) -> bool:
    return any(
        character not in {"\n", "\t"}
        and (
            ord(character) < 32
            or ord(character) == 127
            or unicodedata.category(character) == "Cc"
        )
        for character in value
    )


def _validate_text(
    value: object,
    *,
    field_name: str,
    allow_empty: bool,
) -> str:
    if not isinstance(value, str):
        raise TranslationRouteValidationError(
            field_name + " must be a string"
        )
    if not allow_empty and not value.strip():
        raise TranslationRouteValidationError(
            field_name + " must not be empty"
        )
    if len(value) > MAX_TRANSLATION_TEXT_CHARS:
        raise TranslationRouteValidationError(
            field_name + " exceeds MAX_TRANSLATION_TEXT_CHARS"
        )
    if _has_disallowed_control_characters(value):
        raise TranslationRouteValidationError(
            field_name + " contains a disallowed control character"
        )
    return value


def _validate_identity_and_text(
    *,
    index: object,
    start_ms: object,
    end_ms: object,
    text: object,
) -> None:
    if type(index) is not int or index <= 0:
        raise TranslationRouteValidationError(
            "route index must be a positive integer"
        )
    if type(start_ms) is not int or start_ms < 0:
        raise TranslationRouteValidationError(
            "route start_ms must be a nonnegative integer"
        )
    if type(end_ms) is not int or end_ms <= start_ms:
        raise TranslationRouteValidationError(
            "route end_ms must be an integer greater than start_ms"
        )
    _validate_text(
        text,
        field_name="route source text",
        allow_empty=False,
    )


def _validate_route_input(
    *,
    index: object,
    start_ms: object,
    end_ms: object,
    text: object,
    before_context: object,
    after_context: object,
) -> None:
    _validate_identity_and_text(
        index=index,
        start_ms=start_ms,
        end_ms=end_ms,
        text=text,
    )
    _validate_text(
        before_context,
        field_name="before_context",
        allow_empty=True,
    )
    _validate_text(
        after_context,
        field_name="after_context",
        allow_empty=True,
    )


@dataclass(frozen=True)
class TranslationRouteResult:
    """One immutable filter-or-translation result with source identity."""

    state: str
    index: int
    start_ms: int
    end_ms: int
    original_ja_text: str
    filter_decision: NonLexicalDecision
    translation_outcome: TranslationOutcome | None

    def __post_init__(self):
        _validate_identity_and_text(
            index=self.index,
            start_ms=self.start_ms,
            end_ms=self.end_ms,
            text=self.original_ja_text,
        )

        if not isinstance(self.filter_decision, NonLexicalDecision):
            raise TranslationRouteValidationError(
                "filter_decision must be a NonLexicalDecision"
            )

        try:
            filter_action = self.filter_decision.action
        except AttributeError as error:
            raise TranslationRouteValidationError(
                "filter_decision is missing its action"
            ) from error

        if self.state == ROUTE_FILTER_OMITTED:
            if filter_action != NONLEXICAL_OMIT:
                raise TranslationRouteValidationError(
                    "FILTER_OMITTED requires an OMIT filter decision"
                )
            if self.translation_outcome is not None:
                raise TranslationRouteValidationError(
                    "FILTER_OMITTED cannot contain a translation outcome"
                )
            return

        if self.state == ROUTE_TRANSLATION_ACCEPTED:
            expected_translation_action = TRANSLATION_ACCEPTED
        elif self.state == ROUTE_TRANSLATION_OMITTED:
            expected_translation_action = TRANSLATION_OMITTED
        else:
            raise TranslationRouteValidationError(
                "translation route state is invalid"
            )

        if filter_action != NONLEXICAL_KEEP:
            raise TranslationRouteValidationError(
                "translation states require a KEEP filter decision"
            )
        if not isinstance(self.translation_outcome, TranslationOutcome):
            raise TranslationRouteValidationError(
                "translation state requires a TranslationOutcome"
            )

        try:
            outcome_action = self.translation_outcome.action
            outcome_cue = self.translation_outcome.cue
        except AttributeError as error:
            raise TranslationRouteValidationError(
                "translation outcome is missing required fields"
            ) from error

        if outcome_action != expected_translation_action:
            raise TranslationRouteValidationError(
                "translation outcome action does not match route state"
            )
        if not isinstance(outcome_cue, TranslationCue):
            raise TranslationRouteValidationError(
                "translation outcome cue is invalid"
            )
        if (
            outcome_cue.index != self.index
            or outcome_cue.start_ms != self.start_ms
            or outcome_cue.end_ms != self.end_ms
            or outcome_cue.target != self.original_ja_text
        ):
            raise TranslationRouteValidationError(
                "translation outcome cue does not match route source identity"
            )


def _require_translate_callable(
    translate_cue: object,
) -> Callable[[TranslationCue], TranslationOutcome]:
    if not callable(translate_cue):
        raise TranslationRouteValidationError(
            "translate_cue must be callable"
        )
    return translate_cue


def route_translation_cue(
    *,
    index: int,
    start_ms: int,
    end_ms: int,
    text: str,
    before_context: str = "",
    after_context: str = "",
    translate_cue: Callable[[TranslationCue], TranslationOutcome],
) -> TranslationRouteResult:
    """Filter and, only when kept, route one caller-owned Japanese cue."""

    _validate_route_input(
        index=index,
        start_ms=start_ms,
        end_ms=end_ms,
        text=text,
        before_context=before_context,
        after_context=after_context,
    )
    translator = _require_translate_callable(translate_cue)

    decision = classify_nonlexical(text)
    if not isinstance(decision, NonLexicalDecision):
        raise TranslationRouteContractError(
            "classify_nonlexical returned an invalid decision type"
        )

    if decision.action == NONLEXICAL_OMIT:
        return TranslationRouteResult(
            state=ROUTE_FILTER_OMITTED,
            index=index,
            start_ms=start_ms,
            end_ms=end_ms,
            original_ja_text=text,
            filter_decision=decision,
            translation_outcome=None,
        )
    if decision.action != NONLEXICAL_KEEP:
        raise TranslationRouteContractError(
            "classify_nonlexical returned an unknown action"
        )

    translation_cue = TranslationCue(
        index=index,
        start_ms=start_ms,
        end_ms=end_ms,
        target=text,
        before_context=before_context,
        after_context=after_context,
    )
    outcome = translator(translation_cue)

    if not isinstance(outcome, TranslationOutcome):
        raise TranslationRouteContractError(
            "translate_cue returned an invalid outcome type"
        )

    try:
        outcome_cue = outcome.cue
        outcome_action = outcome.action
    except AttributeError as error:
        raise TranslationRouteContractError(
            "translate_cue returned an incomplete outcome"
        ) from error

    if outcome_cue is not translation_cue:
        raise TranslationRouteContractError(
            "translate_cue substituted the caller-owned cue"
        )

    if outcome_action == TRANSLATION_ACCEPTED:
        route_state = ROUTE_TRANSLATION_ACCEPTED
    elif outcome_action == TRANSLATION_OMITTED:
        route_state = ROUTE_TRANSLATION_OMITTED
    else:
        raise TranslationRouteContractError(
            "translate_cue returned an unknown action"
        )

    return TranslationRouteResult(
        state=route_state,
        index=index,
        start_ms=start_ms,
        end_ms=end_ms,
        original_ja_text=text,
        filter_decision=decision,
        translation_outcome=outcome,
    )


def _source_cue_fields(source_cue: object) -> tuple[object, object, object]:
    try:
        start_ms = source_cue.start_ms
        end_ms = source_cue.end_ms
        text = source_cue.text
    except AttributeError as error:
        raise TranslationRouteValidationError(
            "source cue must expose start_ms, end_ms, and text"
        ) from error
    return start_ms, end_ms, text


def route_translation_sequence(
    source_cues: tuple[object, ...],
    *,
    translate_cue: Callable[[TranslationCue], TranslationOutcome],
) -> tuple[TranslationRouteResult, ...]:
    """Route an immutable cue sequence without sorting or changing topology."""

    if not isinstance(source_cues, tuple):
        raise TranslationRouteValidationError(
            "source_cues must be an immutable tuple"
        )
    if not source_cues:
        raise TranslationRouteValidationError(
            "source_cues must not be empty"
        )
    translator = _require_translate_callable(translate_cue)

    source_values: list[tuple[int, int, str]] = []
    for index, source_cue in enumerate(source_cues, start=1):
        start_ms, end_ms, text = _source_cue_fields(source_cue)
        _validate_identity_and_text(
            index=index,
            start_ms=start_ms,
            end_ms=end_ms,
            text=text,
        )
        source_values.append((start_ms, end_ms, text))

    results: list[TranslationRouteResult] = []
    for position, (start_ms, end_ms, text) in enumerate(source_values):
        before_context = (
            source_values[position - 1][2]
            if position > 0
            else ""
        )
        after_context = (
            source_values[position + 1][2]
            if position + 1 < len(source_values)
            else ""
        )
        results.append(
            route_translation_cue(
                index=position + 1,
                start_ms=start_ms,
                end_ms=end_ms,
                text=text,
                before_context=before_context,
                after_context=after_context,
                translate_cue=translator,
            )
        )

    return tuple(results)


__all__ = [
    "ROUTE_FILTER_OMITTED",
    "ROUTE_TRANSLATION_ACCEPTED",
    "ROUTE_TRANSLATION_OMITTED",
    "TranslationRouteContractError",
    "TranslationRouteError",
    "TranslationRouteResult",
    "TranslationRouteValidationError",
    "route_translation_cue",
    "route_translation_sequence",
]
