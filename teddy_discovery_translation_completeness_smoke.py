"""Offline smoke tests for the Stage11 translation completeness guard."""

from __future__ import annotations

from teddy_discovery_subtitle_text import SubtitleCue
from teddy_discovery_translation import (
    TRANSLATION_ACCEPTED,
    TRANSLATION_OMITTED,
    TranslationOutcome,
)
from teddy_discovery_translation_completeness import (
    TranslationCompletenessError,
    TranslationCompletenessValidationError,
    guard_translation_completeness,
)
from teddy_discovery_translation_route import (
    ROUTE_FILTER_OMITTED,
    ROUTE_TRANSLATION_ACCEPTED,
    ROUTE_TRANSLATION_OMITTED,
    route_translation_sequence,
)


def expect(error_type, callback, marker):
    try:
        callback()
    except error_type:
        return
    except Exception as error:
        raise AssertionError(
            marker + ": wrong exception " + type(error).__name__
        ) from error
    raise AssertionError(marker)


class PatternTranslator:
    def __init__(self, actions):
        self.actions = iter(actions)
        self.calls = []

    def __call__(self, cue):
        self.calls.append(cue)
        try:
            action = next(self.actions)
        except StopIteration as error:
            raise AssertionError("translator action fixture exhausted") from error

        if action == TRANSLATION_ACCEPTED:
            return TranslationOutcome(
                cue=cue,
                action=TRANSLATION_ACCEPTED,
                attempts=1,
                ko_text="한국어 " + str(cue.index),
                reason=None,
            )
        if action == TRANSLATION_OMITTED:
            return TranslationOutcome(
                cue=cue,
                action=TRANSLATION_OMITTED,
                attempts=2,
                ko_text=None,
                reason="synthetic_translation_omitted",
            )
        raise AssertionError("unknown translator fixture action")


def routes(pattern):
    sources = []
    translation_actions = []
    for index, marker in enumerate(pattern, start=1):
        if marker == "F":
            text = "ああああ"
        elif marker in {"A", "O"}:
            text = "translation target " + str(index)
            translation_actions.append(
                TRANSLATION_ACCEPTED if marker == "A" else TRANSLATION_OMITTED
            )
        else:
            raise AssertionError("unknown route fixture marker")
        sources.append(
            SubtitleCue(
                start_ms=index * 1_000,
                end_ms=index * 1_000 + 500,
                text=text,
            )
        )

    translator = PatternTranslator(translation_actions)
    route_results = route_translation_sequence(
        tuple(sources),
        translate_cue=translator,
    )
    expected_states = tuple(
        {
            "F": ROUTE_FILTER_OMITTED,
            "A": ROUTE_TRANSLATION_ACCEPTED,
            "O": ROUTE_TRANSLATION_OMITTED,
        }[marker]
        for marker in pattern
    )
    assert tuple(result.state for result in route_results) == expected_states
    return route_results


def main():
    # A. A healthy route passes and the exact tuple is retained.
    accepted = routes(["A", "A", "A"])
    assert guard_translation_completeness(accepted) is accepted

    # B. Filter omissions are not attempts and do not prevent a healthy
    # accepted result from passing.
    filter_heavy = routes(["F"] * 30 + ["A", "A"])
    assert guard_translation_completeness(filter_heavy) is filter_heavy
    filter_only = routes(["F"] * 50)
    assert guard_translation_completeness(filter_only) is filter_only

    # C. Rule A keeps the minimum at five attempts.
    four_omitted = routes(["O"] * 4)
    assert guard_translation_completeness(four_omitted) is four_omitted
    expect(
        TranslationCompletenessError,
        lambda: guard_translation_completeness(routes(["O"] * 5)),
        "RULE_A_FIVE_ALL_OMITTED",
    )

    # D. Rule B uses integer arithmetic at the exact 50 percent boundary.
    nine_of_twenty = routes(["O"] * 9 + ["A"] * 11)
    assert guard_translation_completeness(nine_of_twenty) is nine_of_twenty
    alternating_twenty = routes(["O", "A"] * 10)
    expect(
        TranslationCompletenessError,
        lambda: guard_translation_completeness(alternating_twenty),
        "RULE_B_TWENTY_HALF_OMITTED",
    )

    # Nineteen attempts are below Rule B's denominator even with a high
    # omission ratio; alternating order avoids the separate streak rule.
    nineteen_high_ratio = ["O", "A"] * 9 + ["O"]
    nineteen_results = routes(nineteen_high_ratio)
    assert guard_translation_completeness(nineteen_results) is nineteen_results

    # E. Rule C is ten omitted lexical attempts in a row.  An accepted cue
    # resets the streak; a filter omission does not.
    nine_then_accepted = routes(["A"] + ["O"] * 9)
    assert guard_translation_completeness(nine_then_accepted) is nine_then_accepted
    accepted_resets = routes(["A"] + ["O"] * 9 + ["A"] + ["O"] * 5)
    assert guard_translation_completeness(accepted_resets) is accepted_resets
    expect(
        TranslationCompletenessError,
        lambda: guard_translation_completeness(["unrelated"]),
        "RULE_C_BAD_FIXTURE_TYPE",
    )
    expect(
        TranslationCompletenessError,
        lambda: guard_translation_completeness(
            routes(["A"] + ["O"] * 10)
        ),
        "RULE_C_TEN_CONSECUTIVE",
    )
    filter_does_not_reset = routes(["A"] + ["O"] * 5 + ["F"] + ["O"] * 5)
    expect(
        TranslationCompletenessError,
        lambda: guard_translation_completeness(filter_does_not_reset),
        "RULE_C_FILTER_DOES_NOT_RESET",
    )

    # F. A synthetic form of the historical 191/191 lexical omission fails.
    all_191_omitted = routes(["O"] * 191)
    expect(
        TranslationCompletenessError,
        lambda: guard_translation_completeness(all_191_omitted),
        "HISTORICAL_191_ALL_OMITTED",
    )

    # G. Input shape/state errors fail closed, while successful validation
    # preserves route order, timing, and source text exactly.
    expect(
        TranslationCompletenessValidationError,
        lambda: guard_translation_completeness([accepted[0]]),
        "LIST_INPUT_REJECTED",
    )
    expect(
        TranslationCompletenessValidationError,
        lambda: guard_translation_completeness(("not-a-route-result",)),
        "MEMBER_TYPE_REJECTED",
    )
    malformed = routes(["A"])[0]
    object.__setattr__(malformed, "state", "MALFORMED_STATE")
    expect(
        TranslationCompletenessValidationError,
        lambda: guard_translation_completeness((malformed,)),
        "UNKNOWN_STATE_REJECTED",
    )
    topology_input = routes(["A", "F", "O", "A"])
    topology_before = tuple(
        (item.index, item.start_ms, item.end_ms, item.original_ja_text)
        for item in topology_input
    )
    topology_output = guard_translation_completeness(topology_input)
    assert topology_output is topology_input
    assert topology_before == tuple(
        (item.index, item.start_ms, item.end_ms, item.original_ja_text)
        for item in topology_output
    )

    print("STAGE11_TRANSLATION_COMPLETENESS_SMOKE=PASS")


if __name__ == "__main__":
    main()
