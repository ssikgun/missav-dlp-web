"""Offline smoke tests for the conservative Stage11 non-lexical filter."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

from teddy_discovery_nonlexical import (
    MAX_NONLEXICAL_TEXT_CHARS,
    MIN_REPEATED_VOCALIC_RUN,
    NONLEXICAL_KEEP,
    NONLEXICAL_OMIT,
    NONLEXICAL_REASON_LEXICAL_OR_AMBIGUOUS,
    NONLEXICAL_REASON_PUNCTUATION_ONLY,
    NONLEXICAL_REASON_REPEATED_PURE_VOCALIC_RUN,
    NonLexicalDecision,
    NonLexicalLimitError,
    NonLexicalValidationError,
    classify_nonlexical,
)


def expect(error_type, function):
    try:
        function()
    except error_type:
        return
    raise AssertionError("expected " + error_type.__name__)


def assert_action(text, action, reason):
    decision = classify_nonlexical(text)
    assert decision.action == action
    assert decision.reason == reason
    return decision


def fake_translation_route(text, translate, calls):
    decision = classify_nonlexical(text)
    if decision.action == NONLEXICAL_KEEP:
        translate(text)
    calls.append(decision)


def main():
    assert MIN_REPEATED_VOCALIC_RUN == 4

    # High-confidence pure repeated vocalic runs only.
    assert_action(
        "ああああ",
        NONLEXICAL_OMIT,
        NONLEXICAL_REASON_REPEATED_PURE_VOCALIC_RUN,
    )
    assert_action(
        "ああああああ",
        NONLEXICAL_OMIT,
        NONLEXICAL_REASON_REPEATED_PURE_VOCALIC_RUN,
    )
    assert_action(
        "オオオオ",
        NONLEXICAL_OMIT,
        NONLEXICAL_REASON_REPEATED_PURE_VOCALIC_RUN,
    )
    assert_action(
        "  …ああああ…  ",
        NONLEXICAL_OMIT,
        NONLEXICAL_REASON_REPEATED_PURE_VOCALIC_RUN,
    )
    assert_action(
        "\tオオオオ！\n",
        NONLEXICAL_OMIT,
        NONLEXICAL_REASON_REPEATED_PURE_VOCALIC_RUN,
    )
    # NFKC is useful for analysis of halfwidth kana, but no source text is
    # returned or rewritten by the classifier.
    source = "ｱｱｱｱ"
    original_source = source
    assert_action(
        source,
        NONLEXICAL_OMIT,
        NONLEXICAL_REASON_REPEATED_PURE_VOCALIC_RUN,
    )
    assert source == original_source
    assert not hasattr(classify_nonlexical(source), "text")

    # Below threshold remains KEEP.
    for text in ("あ", "ああ", "あああ"):
        assert_action(
            text,
            NONLEXICAL_KEEP,
            NONLEXICAL_REASON_LEXICAL_OR_AMBIGUOUS,
        )

    # Meaningful short reactions are not removed.
    for text in (
        "うん",
        "あ？",
        "え？",
        "いや",
        "違う",
        "あ、そうなんだ",
    ):
        assert classify_nonlexical(text).action == NONLEXICAL_KEEP

    # Ambiguous, lexical, mixed, breath-like, and elongated forms stay KEEP.
    for text in (
        "んんんん",
        "あいうえ",
        "ああん",
        "ああっ",
        "はぁ",
        "ふぅ",
        "あぁ",
        "あーーー",
        "あああA",
        "あああ1",
        "今日は雨が降っています。",
    ):
        assert classify_nonlexical(text).action == NONLEXICAL_KEEP

    assert_action(
        "…!?",
        NONLEXICAL_KEEP,
        NONLEXICAL_REASON_PUNCTUATION_ONLY,
    )
    assert_action(
        "ああ！ああ",
        NONLEXICAL_KEEP,
        NONLEXICAL_REASON_LEXICAL_OR_AMBIGUOUS,
    )
    assert_action(
        "あーあーあーあー",
        NONLEXICAL_KEEP,
        NONLEXICAL_REASON_LEXICAL_OR_AMBIGUOUS,
    )

    # Input errors fail closed as validation errors, not OMIT decisions.
    for invalid in (None, 123, b"aaaa"):
        expect(NonLexicalValidationError, lambda invalid=invalid: classify_nonlexical(invalid))
    for invalid in ("", " \t\n"):
        expect(NonLexicalValidationError, lambda invalid=invalid: classify_nonlexical(invalid))
    expect(
        NonLexicalLimitError,
        lambda: classify_nonlexical("あ" * (MAX_NONLEXICAL_TEXT_CHARS + 1)),
    )
    for invalid in ("ああ\x00ああ", "ああ\x01ああ", "ああ\x7fああ"):
        expect(NonLexicalValidationError, lambda invalid=invalid: classify_nonlexical(invalid))
    # Normal cue line breaks/tabs are allowed input but do not form a pure run.
    assert classify_nonlexical("ああ\nああ").action == NONLEXICAL_KEEP

    # The result is immutable and contains only action/reason.
    decision = classify_nonlexical("ああああ")
    try:
        decision.action = NONLEXICAL_KEEP
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError("NonLexicalDecision must be frozen")
    assert set(decision.__dataclass_fields__) == {"action", "reason"}
    expect(
        NonLexicalValidationError,
        lambda: NonLexicalDecision("DROP", "reason"),
    )

    # Determinism and the pre-translation control-flow seam.
    for text in ("ああああ", "うん", "今日は雨が降っています。", "…"):
        assert classify_nonlexical(text) == classify_nonlexical(text)

    translation_calls = []

    def fake_translate(text):
        translation_calls.append(text)

    decisions = []
    fake_translation_route("ああああ", fake_translate, decisions)
    assert translation_calls == []
    fake_translation_route("今日は雨が降っています。", fake_translate, decisions)
    assert translation_calls == ["今日は雨が降っています。"]
    assert [decision.action for decision in decisions] == [
        NONLEXICAL_OMIT,
        NONLEXICAL_KEEP,
    ]

    # Standalone boundary guard: this module has no model/transport dependency.
    module_source = open(__file__.replace("_smoke.py", ".py"), encoding="utf-8").read()
    assert "E4B" not in module_source
    assert "Whisper" not in module_source
    assert "urllib" not in module_source

    print("STAGE11_NONLEXICAL_SMOKE=PASS")


if __name__ == "__main__":
    main()
