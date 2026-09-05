"""Fail-closed completeness checks for one Stage11 translation route.

This module validates the frozen route topology without changing, filtering,
or rewriting any route result.  Non-lexical filter omissions are deliberately
separate from translation attempts and do not count as translation failures.
"""

from __future__ import annotations

from teddy_discovery_translation_route import (
    ROUTE_FILTER_OMITTED,
    ROUTE_TRANSLATION_ACCEPTED,
    ROUTE_TRANSLATION_OMITTED,
    TranslationRouteResult,
)


MIN_ALL_OMITTED_ATTEMPTS = 5
MIN_OMITTED_RATIO_ATTEMPTS = 20
OMITTED_RATIO_NUMERATOR = 1
OMITTED_RATIO_DENOMINATOR = 2
MAX_CONSECUTIVE_TRANSLATION_OMITTED = 10


class TranslationCompletenessError(Exception):
    """Raised when a route is too incomplete for Korean publication."""


class TranslationCompletenessValidationError(TranslationCompletenessError):
    """Raised when the frozen route-result input is malformed."""


def _route_state(route_result: TranslationRouteResult) -> str:
    if not isinstance(route_result, TranslationRouteResult):
        raise TranslationCompletenessValidationError(
            "route_results must contain TranslationRouteResult values"
        )

    try:
        state = route_result.state
    except AttributeError as error:
        raise TranslationCompletenessValidationError(
            "route result is missing its state"
        ) from error

    if type(state) is not str or state not in {
        ROUTE_FILTER_OMITTED,
        ROUTE_TRANSLATION_ACCEPTED,
        ROUTE_TRANSLATION_OMITTED,
    }:
        raise TranslationCompletenessValidationError(
            "route result has an unknown state"
        )
    return state


def guard_translation_completeness(
    route_results: tuple[TranslationRouteResult, ...],
) -> tuple[TranslationRouteResult, ...]:
    """Validate translation completeness and return the exact input tuple.

    ``FILTER_OMITTED`` results are not attempts and are ignored for both the
    failure ratio and the omission streak.  They do not reset the streak;
    only an accepted lexical translation does that.
    """

    if not isinstance(route_results, tuple):
        raise TranslationCompletenessValidationError(
            "route_results must be an immutable tuple"
        )

    attempts = 0
    accepted = 0
    omitted = 0
    consecutive_omitted = 0

    for route_result in route_results:
        state = _route_state(route_result)
        if state == ROUTE_FILTER_OMITTED:
            continue

        attempts += 1
        if state == ROUTE_TRANSLATION_ACCEPTED:
            accepted += 1
            consecutive_omitted = 0
            continue

        omitted += 1
        consecutive_omitted += 1
        if consecutive_omitted >= MAX_CONSECUTIVE_TRANSLATION_OMITTED:
            raise TranslationCompletenessError(
                "translation omission streak exceeds the frozen bound"
            )

    if (
        attempts >= MIN_ALL_OMITTED_ATTEMPTS
        and accepted == 0
        and omitted == attempts
    ):
        raise TranslationCompletenessError(
            "all translation attempts were omitted"
        )

    if (
        attempts >= MIN_OMITTED_RATIO_ATTEMPTS
        and omitted * OMITTED_RATIO_DENOMINATOR
        >= attempts * OMITTED_RATIO_NUMERATOR
    ):
        raise TranslationCompletenessError(
            "translation omission ratio exceeds the frozen bound"
        )

    return route_results


__all__ = [
    "MAX_CONSECUTIVE_TRANSLATION_OMITTED",
    "MIN_ALL_OMITTED_ATTEMPTS",
    "MIN_OMITTED_RATIO_ATTEMPTS",
    "OMITTED_RATIO_DENOMINATOR",
    "OMITTED_RATIO_NUMERATOR",
    "TranslationCompletenessError",
    "TranslationCompletenessValidationError",
    "guard_translation_completeness",
]
