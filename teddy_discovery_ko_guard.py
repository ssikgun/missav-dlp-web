"""Deterministic Stage11 Korean output guard and final cue construction.

This module performs only structural validation between a frozen translation
route result and an immutable final subtitle cue.  It does not translate,
rewrite content, serialize subtitles, or own filesystem, network, database,
model, worker, publish, or completion state.
"""

from __future__ import annotations

from dataclasses import dataclass

from teddy_discovery_nonlexical import (
    NONLEXICAL_KEEP,
    NONLEXICAL_OMIT,
    NonLexicalDecision,
)
from teddy_discovery_subtitle_text import SubtitleCue, SubtitleTextError
from teddy_discovery_translation import (
    TRANSLATION_ACCEPTED,
    TRANSLATION_OMITTED,
    TranslationCue,
    TranslationOutcome,
)
from teddy_discovery_translation_route import (
    ROUTE_FILTER_OMITTED,
    ROUTE_TRANSLATION_ACCEPTED,
    ROUTE_TRANSLATION_OMITTED,
    TranslationRouteResult,
)


FINAL_CUE_READY = "FINAL_CUE_READY"
FINAL_CUE_OMITTED = "FINAL_CUE_OMITTED"


class KoreanCueGuardError(Exception):
    """Base class for deterministic Korean cue guard failures."""


class KoreanCueGuardValidationError(KoreanCueGuardError):
    """Raised for malformed caller-owned guard input or result combinations."""


class KoreanCueGuardContractError(KoreanCueGuardError):
    """Raised when a frozen upstream result violates its observable contract."""


def _require_route_result(value: object) -> TranslationRouteResult:
    if not isinstance(value, TranslationRouteResult):
        raise KoreanCueGuardValidationError(
            "route_result must be a TranslationRouteResult"
        )
    return value


def _require_filter_action(
    route_result: TranslationRouteResult,
    *,
    expected_action: str,
) -> None:
    try:
        decision = route_result.filter_decision
    except AttributeError as error:
        raise KoreanCueGuardContractError(
            "route_result is missing its filter decision"
        ) from error
    if not isinstance(decision, NonLexicalDecision):
        raise KoreanCueGuardContractError(
            "route_result has an invalid filter decision"
        )
    try:
        decision_action = decision.action
    except AttributeError as error:
        raise KoreanCueGuardContractError(
            "filter decision is missing its action"
        ) from error
    if decision_action != expected_action:
        raise KoreanCueGuardContractError(
            "route_result filter action does not match its state"
        )


def _require_translation_outcome(
    route_result: TranslationRouteResult,
    *,
    expected_action: str,
) -> TranslationOutcome:
    _require_filter_action(
        route_result,
        expected_action=NONLEXICAL_KEEP,
    )

    try:
        outcome = route_result.translation_outcome
    except AttributeError as error:
        raise KoreanCueGuardContractError(
            "translation route state is missing its outcome"
        ) from error
    if not isinstance(outcome, TranslationOutcome):
        raise KoreanCueGuardContractError(
            "translation route state requires a TranslationOutcome"
        )
    try:
        outcome_action = outcome.action
        outcome_cue = outcome.cue
    except AttributeError as error:
        raise KoreanCueGuardContractError(
            "translation outcome is missing required fields"
        ) from error
    if outcome_action != expected_action:
        raise KoreanCueGuardContractError(
            "translation outcome action does not match route state"
        )
    if not isinstance(outcome_cue, TranslationCue):
        raise KoreanCueGuardContractError(
            "translation outcome cue is invalid"
        )
    try:
        identity_matches = (
            outcome_cue.index == route_result.index
            and outcome_cue.start_ms == route_result.start_ms
            and outcome_cue.end_ms == route_result.end_ms
            and outcome_cue.target == route_result.original_ja_text
        )
    except AttributeError as error:
        raise KoreanCueGuardContractError(
            "route or outcome cue is missing source identity fields"
        ) from error
    if not identity_matches:
        raise KoreanCueGuardContractError(
            "translation outcome cue does not match route source identity"
        )
    return outcome


def _validate_filter_omitted_route(
    route_result: TranslationRouteResult,
) -> None:
    _require_filter_action(
        route_result,
        expected_action=NONLEXICAL_OMIT,
    )
    try:
        outcome = route_result.translation_outcome
    except AttributeError as error:
        raise KoreanCueGuardContractError(
            "filter-omitted route is missing its outcome field"
        ) from error
    if outcome is not None:
        raise KoreanCueGuardContractError(
            "filter-omitted route cannot contain a translation outcome"
        )


def _validate_translation_omitted_route(
    route_result: TranslationRouteResult,
) -> None:
    outcome = _require_translation_outcome(
        route_result,
        expected_action=TRANSLATION_OMITTED,
    )
    try:
        ko_text = outcome.ko_text
        reason = outcome.reason
    except AttributeError as error:
        raise KoreanCueGuardContractError(
            "translation-omitted outcome is missing required fields"
        ) from error
    if ko_text is not None:
        raise KoreanCueGuardContractError(
            "translation-omitted route cannot contain ko_text"
        )
    if not isinstance(reason, str) or not reason:
        raise KoreanCueGuardContractError(
            "translation-omitted route requires a reason code"
        )


def _accepted_outcome(
    route_result: TranslationRouteResult,
) -> TranslationOutcome:
    outcome = _require_translation_outcome(
        route_result,
        expected_action=TRANSLATION_ACCEPTED,
    )
    try:
        ko_text = outcome.ko_text
        reason = outcome.reason
    except AttributeError as error:
        raise KoreanCueGuardContractError(
            "accepted translation outcome is missing required fields"
        ) from error
    if not isinstance(ko_text, str):
        raise KoreanCueGuardContractError(
            "accepted translation requires string ko_text"
        )
    if not ko_text.strip():
        raise KoreanCueGuardContractError(
            "accepted translation requires nonempty ko_text"
        )
    if ko_text.startswith("\n") or ko_text.endswith("\n"):
        raise KoreanCueGuardContractError(
            "accepted ko_text cannot start or end with a newline"
        )
    if reason is not None:
        raise KoreanCueGuardContractError(
            "accepted translation cannot contain a reason code"
        )
    return outcome


@dataclass(frozen=True)
class KoreanCueResult:
    """One immutable final-cue or omission result retaining route provenance."""

    state: str
    route_result: TranslationRouteResult
    cue: SubtitleCue | None

    def __post_init__(self):
        route_result = _require_route_result(self.route_result)

        if self.state == FINAL_CUE_READY:
            if route_result.state != ROUTE_TRANSLATION_ACCEPTED:
                raise KoreanCueGuardValidationError(
                    "FINAL_CUE_READY requires a translation-accepted route"
                )
            outcome = _accepted_outcome(route_result)
            if not isinstance(self.cue, SubtitleCue):
                raise KoreanCueGuardValidationError(
                    "FINAL_CUE_READY requires a SubtitleCue"
                )
            if (
                self.cue.start_ms != route_result.start_ms
                or self.cue.end_ms != route_result.end_ms
                or self.cue.text != outcome.ko_text
            ):
                raise KoreanCueGuardValidationError(
                    "final cue does not match its accepted route result"
                )
            return

        if self.state == FINAL_CUE_OMITTED:
            if route_result.state == ROUTE_FILTER_OMITTED:
                _validate_filter_omitted_route(route_result)
            elif route_result.state == ROUTE_TRANSLATION_OMITTED:
                _validate_translation_omitted_route(route_result)
            else:
                raise KoreanCueGuardValidationError(
                    "FINAL_CUE_OMITTED requires an omitted route"
                )
            if self.cue is not None:
                raise KoreanCueGuardValidationError(
                    "FINAL_CUE_OMITTED cannot contain a SubtitleCue"
                )
            return

        raise KoreanCueGuardValidationError(
            "Korean cue result state is invalid"
        )


def guard_korean_route_result(
    route_result: TranslationRouteResult,
) -> KoreanCueResult:
    """Convert one route result into an omission or exact final Korean cue."""

    validated_route = _require_route_result(route_result)

    if validated_route.state == ROUTE_FILTER_OMITTED:
        _validate_filter_omitted_route(validated_route)
        return KoreanCueResult(
            state=FINAL_CUE_OMITTED,
            route_result=validated_route,
            cue=None,
        )

    if validated_route.state == ROUTE_TRANSLATION_OMITTED:
        _validate_translation_omitted_route(validated_route)
        return KoreanCueResult(
            state=FINAL_CUE_OMITTED,
            route_result=validated_route,
            cue=None,
        )

    if validated_route.state != ROUTE_TRANSLATION_ACCEPTED:
        raise KoreanCueGuardContractError(
            "route_result has an unknown state"
        )

    outcome = _accepted_outcome(validated_route)
    try:
        cue = SubtitleCue(
            start_ms=validated_route.start_ms,
            end_ms=validated_route.end_ms,
            text=outcome.ko_text,
        )
    except SubtitleTextError as error:
        raise KoreanCueGuardContractError(
            "accepted translation cannot form a valid SubtitleCue"
        ) from error

    return KoreanCueResult(
        state=FINAL_CUE_READY,
        route_result=validated_route,
        cue=cue,
    )


def guard_korean_sequence(
    route_results: tuple[TranslationRouteResult, ...],
) -> tuple[KoreanCueResult, ...]:
    """Guard a route tuple in place order, allowing an empty tuple."""

    if not isinstance(route_results, tuple):
        raise KoreanCueGuardValidationError(
            "route_results must be an immutable tuple"
        )
    return tuple(
        guard_korean_route_result(route_result)
        for route_result in route_results
    )


def ready_subtitle_cues(
    guarded_results: tuple[KoreanCueResult, ...],
) -> tuple[SubtitleCue, ...]:
    """Project ready cues in guard-result order without numbering or sorting."""

    if not isinstance(guarded_results, tuple):
        raise KoreanCueGuardValidationError(
            "guarded_results must be an immutable tuple"
        )

    cues: list[SubtitleCue] = []
    for guarded_result in guarded_results:
        if not isinstance(guarded_result, KoreanCueResult):
            raise KoreanCueGuardValidationError(
                "guarded_results must contain KoreanCueResult values"
            )
        if guarded_result.state == FINAL_CUE_READY:
            if not isinstance(guarded_result.cue, SubtitleCue):
                raise KoreanCueGuardContractError(
                    "ready guard result has an invalid cue"
                )
            cues.append(guarded_result.cue)
        elif guarded_result.state != FINAL_CUE_OMITTED:
            raise KoreanCueGuardContractError(
                "guarded result has an unknown state"
            )

    return tuple(cues)


__all__ = [
    "FINAL_CUE_OMITTED",
    "FINAL_CUE_READY",
    "KoreanCueGuardContractError",
    "KoreanCueGuardError",
    "KoreanCueGuardValidationError",
    "KoreanCueResult",
    "guard_korean_route_result",
    "guard_korean_sequence",
    "ready_subtitle_cues",
]
