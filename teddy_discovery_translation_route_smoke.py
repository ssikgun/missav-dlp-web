"""Offline fake-callable smoke tests for Stage11 translation routing."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import teddy_discovery_translation_route as route_module
from teddy_discovery_asr import ASRSegment, ASRWord
from teddy_discovery_nonlexical import NONLEXICAL_KEEP, NONLEXICAL_OMIT
from teddy_discovery_subtitle_text import SubtitleCue
from teddy_discovery_translation import (
    MAX_TRANSLATION_TEXT_CHARS,
    TRANSLATION_ACCEPTED,
    TRANSLATION_OMITTED,
    TranslationCue,
    TranslationOutcome,
)
from teddy_discovery_translation_route import (
    ROUTE_FILTER_OMITTED,
    ROUTE_TRANSLATION_ACCEPTED,
    ROUTE_TRANSLATION_OMITTED,
    TranslationRouteContractError,
    TranslationRouteResult,
    TranslationRouteValidationError,
    route_translation_cue,
    route_translation_sequence,
)


def expect(error_type, function):
    try:
        function()
    except error_type:
        return
    raise AssertionError("expected " + error_type.__name__)


class FakeTranslator:
    def __init__(self, action=TRANSLATION_ACCEPTED):
        self.action = action
        self.calls = []

    def __call__(self, cue):
        self.calls.append(cue)
        if self.action == TRANSLATION_ACCEPTED:
            return TranslationOutcome(
                cue=cue,
                action=TRANSLATION_ACCEPTED,
                attempts=1,
                ko_text="가짜 번역 결과",
                reason=None,
            )
        if self.action == TRANSLATION_OMITTED:
            return TranslationOutcome(
                cue=cue,
                action=TRANSLATION_OMITTED,
                attempts=2,
                ko_text=None,
                reason="synthetic_translation_omitted",
            )
        raise AssertionError("unsupported fake translator action")


def route_one(source_text, translator, **overrides):
    values = {
        "index": 7,
        "start_ms": 12_345,
        "end_ms": 13_456,
        "text": source_text,
        "before_context": "前の文",
        "after_context": "次の文",
        "translate_cue": translator,
    }
    values.update(overrides)
    return route_translation_cue(**values)


def synthetic_unknown_outcome(cue):
    outcome = object.__new__(TranslationOutcome)
    object.__setattr__(outcome, "cue", cue)
    object.__setattr__(outcome, "action", "UNKNOWN")
    object.__setattr__(outcome, "attempts", 1)
    object.__setattr__(outcome, "ko_text", None)
    object.__setattr__(outcome, "reason", "synthetic_unknown_action")
    return outcome


def main():
    assert ROUTE_FILTER_OMITTED == "FILTER_OMITTED"
    assert ROUTE_TRANSLATION_ACCEPTED == "TRANSLATION_ACCEPTED"
    assert ROUTE_TRANSLATION_OMITTED == "TRANSLATION_OMITTED"

    # A. Filter omission validates local input, but creates no TranslationCue
    # and never invokes the injected translator.
    omitted_translator = FakeTranslator()
    original_translation_cue = route_module.TranslationCue
    constructed = []

    def forbidden_translation_cue(*args, **kwargs):
        constructed.append((args, kwargs))
        raise AssertionError("TranslationCue constructed for filter omission")

    route_module.TranslationCue = forbidden_translation_cue
    try:
        filter_omitted = route_one("ああああ", omitted_translator)
    finally:
        route_module.TranslationCue = original_translation_cue

    assert filter_omitted.state == ROUTE_FILTER_OMITTED
    assert filter_omitted.filter_decision.action == NONLEXICAL_OMIT
    assert filter_omitted.translation_outcome is None
    assert omitted_translator.calls == []
    assert constructed == []

    # B/C. A kept cue creates exactly one cue, invokes translation once, and
    # retains exact caller-owned source identity and object identity.
    accepted_translator = FakeTranslator()
    accepted = route_one("今日は雨です。", accepted_translator)
    assert accepted.state == ROUTE_TRANSLATION_ACCEPTED
    assert accepted.filter_decision.action == NONLEXICAL_KEEP
    assert len(accepted_translator.calls) == 1
    translated_cue = accepted_translator.calls[0]
    assert isinstance(translated_cue, TranslationCue)
    assert accepted.translation_outcome.cue is translated_cue
    assert (
        accepted.index,
        accepted.start_ms,
        accepted.end_ms,
        accepted.original_ja_text,
    ) == (7, 12_345, 13_456, "今日は雨です。")
    assert (
        translated_cue.index,
        translated_cue.start_ms,
        translated_cue.end_ms,
        translated_cue.target,
        translated_cue.before_context,
        translated_cue.after_context,
    ) == (
        7,
        12_345,
        13_456,
        "今日は雨です。",
        "前の文",
        "次の文",
    )

    # The classifier seam receives exactly the source text and no timing.
    classifier_calls = []
    original_classifier = route_module.classify_nonlexical

    def classifier_spy(text):
        classifier_calls.append(text)
        return original_classifier(text)

    route_module.classify_nonlexical = classifier_spy
    try:
        spy_translator = FakeTranslator()
        route_one("分類対象", spy_translator)
    finally:
        route_module.classify_nonlexical = original_classifier
    assert classifier_calls == ["分類対象"]
    assert len(spy_translator.calls) == 1

    # D/K. Translation omission is distinct from filter omission, and the
    # route does not retry either accepted or omitted translation outcomes.
    translation_omit_translator = FakeTranslator(TRANSLATION_OMITTED)
    translation_omitted = route_one(
        "翻訳可能な文",
        translation_omit_translator,
    )
    assert translation_omitted.state == ROUTE_TRANSLATION_OMITTED
    assert translation_omitted.state != filter_omitted.state
    assert translation_omitted.filter_decision.action == NONLEXICAL_KEEP
    assert isinstance(
        translation_omitted.translation_outcome,
        TranslationOutcome,
    )
    assert (
        translation_omitted.translation_outcome.action
        == TRANSLATION_OMITTED
    )
    assert len(translation_omit_translator.calls) == 1
    assert len(accepted_translator.calls) == 1

    # E. Meaningful short reactions remain translatable.
    reaction_translator = FakeTranslator()
    reaction = route_one("うん", reaction_translator)
    assert reaction.state == ROUTE_TRANSLATION_ACCEPTED
    assert reaction.filter_decision.action == NONLEXICAL_KEEP
    assert len(reaction_translator.calls) == 1

    # F. Ordered source topology, source indices, and exact timing survive a
    # filtered middle cue without sorting or compressed numbering.
    sources = (
        SubtitleCue(start_ms=900, end_ms=1_500, text="最初の文"),
        SubtitleCue(start_ms=1_600, end_ms=1_900, text="ああああ"),
        SubtitleCue(start_ms=2_000, end_ms=3_250, text="最後の文"),
    )
    source_snapshot = tuple(
        (cue.start_ms, cue.end_ms, cue.text)
        for cue in sources
    )
    sequence_translator = FakeTranslator()
    sequence = route_translation_sequence(
        sources,
        translate_cue=sequence_translator,
    )
    assert [result.state for result in sequence] == [
        ROUTE_TRANSLATION_ACCEPTED,
        ROUTE_FILTER_OMITTED,
        ROUTE_TRANSLATION_ACCEPTED,
    ]
    assert [result.index for result in sequence] == [1, 2, 3]
    assert [result.original_ja_text for result in sequence] == [
        cue.text for cue in sources
    ]
    assert [
        (result.start_ms, result.end_ms)
        for result in sequence
    ] == [
        (cue.start_ms, cue.end_ms)
        for cue in sources
    ]
    assert [cue.index for cue in sequence_translator.calls] == [1, 3]
    assert sequence_translator.calls[0].after_context == sources[1].text
    assert sequence_translator.calls[1].before_context == sources[1].text
    assert tuple(
        (cue.start_ms, cue.end_ms, cue.text)
        for cue in sources
    ) == source_snapshot

    # G. Context always comes from the immediate original neighbors, even
    # when both neighbors are themselves filter-omitted.
    context_sources = (
        SubtitleCue(start_ms=0, end_ms=500, text="ああああ"),
        SubtitleCue(start_ms=500, end_ms=1_000, text="中央の文"),
        SubtitleCue(start_ms=1_000, end_ms=1_500, text="オオオオ"),
    )
    context_translator = FakeTranslator()
    context_results = route_translation_sequence(
        context_sources,
        translate_cue=context_translator,
    )
    assert [result.state for result in context_results] == [
        ROUTE_FILTER_OMITTED,
        ROUTE_TRANSLATION_ACCEPTED,
        ROUTE_FILTER_OMITTED,
    ]
    assert len(context_translator.calls) == 1
    middle_cue = context_translator.calls[0]
    assert middle_cue.index == 2
    assert middle_cue.before_context == context_sources[0].text
    assert middle_cue.after_context == context_sources[2].text

    # The same structural sequence helper accepts immutable ASRSegment values
    # without importing either source model into the routing module.
    asr_word = ASRWord(start_ms=10, end_ms=20, text="短")
    asr_sources = (
        ASRSegment(
            start_ms=0,
            end_ms=100,
            text="短い文",
            words=(asr_word,),
        ),
    )
    asr_translator = FakeTranslator()
    asr_results = route_translation_sequence(
        asr_sources,
        translate_cue=asr_translator,
    )
    assert asr_results[0].index == 1
    assert asr_translator.calls[0].start_ms == 0
    assert asr_translator.calls[0].end_ms == 100
    assert asr_sources[0].words == (asr_word,)

    # I. Malformed caller input fails before classification can become an
    # omission and before any translation call.
    invalid_translator = FakeTranslator()
    invalid_cases = (
        {"index": 0},
        {"index": True},
        {"start_ms": -1},
        {"start_ms": False},
        {"end_ms": 12_345},
        {"end_ms": 12_344},
        {"text": None},
        {"text": ""},
        {"text": " \t\n "},
        {"text": "bad\x00text"},
        {"text": "x" * (MAX_TRANSLATION_TEXT_CHARS + 1)},
        {"before_context": None},
        {"after_context": "x" * (MAX_TRANSLATION_TEXT_CHARS + 1)},
    )
    for overrides in invalid_cases:
        expect(
            TranslationRouteValidationError,
            lambda overrides=overrides: route_one(
                "有効な文",
                invalid_translator,
                **overrides,
            ),
        )
    expect(
        TranslationRouteValidationError,
        lambda: route_one(
            "有効な文",
            None,
        ),
    )
    expect(
        TranslationRouteValidationError,
        lambda: route_one(
            "ああああ",
            invalid_translator,
            index=0,
        ),
    )
    expect(
        TranslationRouteValidationError,
        lambda: route_one(
            "ああああ",
            invalid_translator,
            before_context=None,
        ),
    )
    assert invalid_translator.calls == []

    expect(
        TranslationRouteValidationError,
        lambda: route_translation_sequence(
            list(sources),
            translate_cue=FakeTranslator(),
        ),
    )
    expect(
        TranslationRouteValidationError,
        lambda: route_translation_sequence(
            (),
            translate_cue=FakeTranslator(),
        ),
    )
    expect(
        TranslationRouteValidationError,
        lambda: route_translation_sequence(
            (object(),),
            translate_cue=FakeTranslator(),
        ),
    )

    # J. Wrong return type, substituted cue identity, and unknown action are
    # explicit translator contract failures.
    wrong_type_calls = []

    def wrong_type(cue):
        wrong_type_calls.append(cue)
        return None

    expect(
        TranslationRouteContractError,
        lambda: route_one("契約確認", wrong_type),
    )
    assert len(wrong_type_calls) == 1

    substitute_calls = []

    def substitute_cue(cue):
        substitute_calls.append(cue)
        substitute = TranslationCue(
            index=cue.index,
            start_ms=cue.start_ms,
            end_ms=cue.end_ms,
            target=cue.target,
            before_context=cue.before_context,
            after_context=cue.after_context,
        )
        assert substitute == cue and substitute is not cue
        return TranslationOutcome(
            cue=substitute,
            action=TRANSLATION_ACCEPTED,
            attempts=1,
            ko_text="대체 객체",
            reason=None,
        )

    expect(
        TranslationRouteContractError,
        lambda: route_one("同一性確認", substitute_cue),
    )
    assert len(substitute_calls) == 1

    unknown_action_calls = []

    def unknown_action(cue):
        unknown_action_calls.append(cue)
        return synthetic_unknown_outcome(cue)

    expect(
        TranslationRouteContractError,
        lambda: route_one("動作確認", unknown_action),
    )
    assert len(unknown_action_calls) == 1

    class SyntheticProgrammingError(Exception):
        pass

    programming_error_calls = []

    def programming_error(cue):
        programming_error_calls.append(cue)
        raise SyntheticProgrammingError("synthetic programming failure")

    expect(
        SyntheticProgrammingError,
        lambda: route_one("例外確認", programming_error),
    )
    assert len(programming_error_calls) == 1

    # TranslationRouteResult independently enforces state and source identity.
    expect(
        TranslationRouteValidationError,
        lambda: TranslationRouteResult(
            state=ROUTE_FILTER_OMITTED,
            index=accepted.index,
            start_ms=accepted.start_ms,
            end_ms=accepted.end_ms,
            original_ja_text=accepted.original_ja_text,
            filter_decision=accepted.filter_decision,
            translation_outcome=None,
        ),
    )
    expect(
        TranslationRouteValidationError,
        lambda: TranslationRouteResult(
            state=ROUTE_TRANSLATION_ACCEPTED,
            index=translation_omitted.index,
            start_ms=translation_omitted.start_ms,
            end_ms=translation_omitted.end_ms,
            original_ja_text=translation_omitted.original_ja_text,
            filter_decision=translation_omitted.filter_decision,
            translation_outcome=translation_omitted.translation_outcome,
        ),
    )
    expect(
        TranslationRouteValidationError,
        lambda: TranslationRouteResult(
            state=accepted.state,
            index=accepted.index + 1,
            start_ms=accepted.start_ms,
            end_ms=accepted.end_ms,
            original_ja_text=accepted.original_ja_text,
            filter_decision=accepted.filter_decision,
            translation_outcome=accepted.translation_outcome,
        ),
    )

    try:
        accepted.state = ROUTE_TRANSLATION_OMITTED
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError("TranslationRouteResult must be frozen")

    module_source = Path(__file__).with_name(
        "teddy_discovery_translation_route.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "urllib",
        "requests",
        "sqlite3",
        "subprocess",
        "ffmpeg",
        "WhisperModel",
        "E4BTranslationAdapter(",
        "serialize_srt",
        "parse_subtitle_bytes",
    ):
        assert forbidden not in module_source

    print("STAGE11_TRANSLATION_ROUTE_SMOKE=PASS")


if __name__ == "__main__":
    main()
