from __future__ import annotations

from pathlib import Path

from teddy_discovery_ko_guard import (
    FINAL_CUE_OMITTED,
    FINAL_CUE_READY,
    KoreanCueGuardContractError,
    KoreanCueGuardValidationError,
    KoreanCueResult,
    guard_korean_route_result,
    guard_korean_sequence,
    ready_subtitle_cues,
)
from teddy_discovery_subtitle_text import (
    MAX_CUE_TEXT_CHARS,
    SubtitleCue,
    SubtitleDocument,
    serialize_srt,
)
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
    route_translation_cue,
)


def expect_raises(exception_type, callback, marker: str):
    try:
        callback()
    except exception_type:
        return
    raise AssertionError(marker)


def accepted_route(
    *,
    index: int = 1,
    start_ms: int = 1_000,
    end_ms: int = 2_000,
    ja_text: str = "今日は良い天気ですね。",
    ko_text: str = "오늘은 날씨가 좋네요.",
) -> TranslationRouteResult:
    calls = []

    def translate(cue: TranslationCue) -> TranslationOutcome:
        calls.append(cue)
        return TranslationOutcome(
            cue=cue,
            action=TRANSLATION_ACCEPTED,
            attempts=1,
            ko_text=ko_text,
            reason=None,
        )

    result = route_translation_cue(
        index=index,
        start_ms=start_ms,
        end_ms=end_ms,
        text=ja_text,
        translate_cue=translate,
    )
    assert len(calls) == 1
    return result


def translation_omitted_route(
    *,
    index: int = 1,
    start_ms: int = 1_000,
    end_ms: int = 2_000,
    ja_text: str = "翻訳対象の台詞です。",
) -> TranslationRouteResult:
    calls = []

    def translate(cue: TranslationCue) -> TranslationOutcome:
        calls.append(cue)
        return TranslationOutcome(
            cue=cue,
            action=TRANSLATION_OMITTED,
            attempts=2,
            ko_text=None,
            reason="invalid_ko",
        )

    result = route_translation_cue(
        index=index,
        start_ms=start_ms,
        end_ms=end_ms,
        text=ja_text,
        translate_cue=translate,
    )
    assert len(calls) == 1
    return result


def filter_omitted_route(
    *,
    index: int = 1,
    start_ms: int = 1_000,
    end_ms: int = 2_000,
) -> TranslationRouteResult:
    calls = []

    def forbidden_translate(cue):
        calls.append(cue)
        raise AssertionError("FILTER_OMITTED_REACHED_TRANSLATOR")

    result = route_translation_cue(
        index=index,
        start_ms=start_ms,
        end_ms=end_ms,
        text="ああああ",
        translate_cue=forbidden_translate,
    )
    assert calls == []
    return result


def malformed_copy(route_result: TranslationRouteResult, **changes):
    copied = object.__new__(TranslationRouteResult)
    values = {
        "state": route_result.state,
        "index": route_result.index,
        "start_ms": route_result.start_ms,
        "end_ms": route_result.end_ms,
        "original_ja_text": route_result.original_ja_text,
        "filter_decision": route_result.filter_decision,
        "translation_outcome": route_result.translation_outcome,
    }
    values.update(changes)
    for field_name, value in values.items():
        object.__setattr__(copied, field_name, value)
    return copied


def outcome_with_ko(route_result: TranslationRouteResult, ko_text) -> object:
    outcome = object.__new__(TranslationOutcome)
    original = route_result.translation_outcome
    object.__setattr__(outcome, "cue", original.cue)
    object.__setattr__(outcome, "action", TRANSLATION_ACCEPTED)
    object.__setattr__(outcome, "attempts", 1)
    object.__setattr__(outcome, "ko_text", ko_text)
    object.__setattr__(outcome, "reason", None)
    return outcome


def main():
    assert FINAL_CUE_READY == "FINAL_CUE_READY"
    assert FINAL_CUE_OMITTED == "FINAL_CUE_OMITTED"

    # A. Accepted text and timing are propagated exactly.
    accepted = accepted_route()
    ready = guard_korean_route_result(accepted)
    assert ready.state == FINAL_CUE_READY
    assert ready.route_result is accepted
    assert isinstance(ready.cue, SubtitleCue)
    assert ready.cue.start_ms == accepted.start_ms == 1_000
    assert ready.cue.end_ms == accepted.end_ms == 2_000
    assert ready.cue.text == accepted.translation_outcome.ko_text

    # B/C. Both omissions produce no cue while retaining distinct provenance.
    filter_omitted = filter_omitted_route(index=2)
    filter_result = guard_korean_route_result(filter_omitted)
    assert filter_result.state == FINAL_CUE_OMITTED
    assert filter_result.cue is None
    assert filter_result.route_result is filter_omitted
    assert filter_result.route_result.state == ROUTE_FILTER_OMITTED

    translation_omitted = translation_omitted_route(index=3)
    translation_result = guard_korean_route_result(translation_omitted)
    assert translation_result.state == FINAL_CUE_OMITTED
    assert translation_result.cue is None
    assert translation_result.route_result is translation_omitted
    assert translation_result.route_result.state == ROUTE_TRANSLATION_OMITTED
    assert filter_result.route_result.state != translation_result.route_result.state

    # D. Mixed scripts, names, Latin letters, and numbers are not heuristics.
    mixed_text = "Sony α7 모델과東京 이름을 확인했어."
    mixed = guard_korean_route_result(
        accepted_route(
            ja_text="製品名を確認した。",
            ko_text=mixed_text,
        )
    )
    assert mixed.state == FINAL_CUE_READY
    assert mixed.cue.text == mixed_text

    # E. Internal newlines remain valid and unchanged.
    multiline_text = "첫 번째 줄\n두 번째 줄"
    multiline = guard_korean_route_result(
        accepted_route(ko_text=multiline_text)
    )
    assert multiline.cue.text == multiline_text

    # F. Outer newlines are rejected, never stripped.
    for outer_newline in ("\n한국어", "한국어\n"):
        expect_raises(
            KoreanCueGuardContractError,
            lambda value=outer_newline: guard_korean_route_result(
                accepted_route(ko_text=value)
            ),
            "OUTER_NEWLINE_REJECTED",
        )

    # G. Ordinary outer spaces are preserved under the frozen outcome contract.
    spaced_text = "  여백을 그대로 둬.  "
    spaced = guard_korean_route_result(
        accepted_route(ko_text=spaced_text)
    )
    assert spaced.cue.text == spaced_text

    # H. Invalid accepted content forced past the frozen constructor fails here.
    for malformed_text in (
        None,
        "",
        "   ",
        "잘못된\x00텍스트",
        "잘못된\x1f텍스트",
        "x" * (MAX_CUE_TEXT_CHARS + 1),
    ):
        base = accepted_route()
        malformed = malformed_copy(
            base,
            translation_outcome=outcome_with_ko(base, malformed_text),
        )
        expect_raises(
            KoreanCueGuardContractError,
            lambda value=malformed: guard_korean_route_result(value),
            "MALFORMED_ACCEPTED_TEXT_REJECTED",
        )

    # I. Observable source/timing substitutions are rejected by the guard.
    for substitute_cue in (
        TranslationCue(
            index=9,
            start_ms=accepted.start_ms,
            end_ms=accepted.end_ms,
            target=accepted.original_ja_text,
        ),
        TranslationCue(
            index=accepted.index,
            start_ms=accepted.start_ms + 1,
            end_ms=accepted.end_ms,
            target=accepted.original_ja_text,
        ),
        TranslationCue(
            index=accepted.index,
            start_ms=accepted.start_ms,
            end_ms=accepted.end_ms + 1,
            target=accepted.original_ja_text,
        ),
        TranslationCue(
            index=accepted.index,
            start_ms=accepted.start_ms,
            end_ms=accepted.end_ms,
            target="異なる原文",
        ),
    ):
        bad_outcome = TranslationOutcome(
            cue=substitute_cue,
            action=TRANSLATION_ACCEPTED,
            attempts=1,
            ko_text="유효한 번역",
            reason=None,
        )
        mismatch = malformed_copy(
            accepted,
            translation_outcome=bad_outcome,
        )
        expect_raises(
            KoreanCueGuardContractError,
            lambda value=mismatch: guard_korean_route_result(value),
            "OBSERVABLE_ROUTE_IDENTITY_MISMATCH_REJECTED",
        )

    # Other malformed upstream state/action combinations fail explicitly.
    expect_raises(
        KoreanCueGuardValidationError,
        lambda: guard_korean_route_result("not a route"),
        "WRONG_ROUTE_TYPE_REJECTED",
    )
    expect_raises(
        KoreanCueGuardContractError,
        lambda: guard_korean_route_result(
            malformed_copy(accepted, state="UNKNOWN_ROUTE_STATE")
        ),
        "UNKNOWN_ROUTE_STATE_REJECTED",
    )
    expect_raises(
        KoreanCueGuardContractError,
        lambda: guard_korean_route_result(
            malformed_copy(accepted, translation_outcome=None)
        ),
        "ACCEPTED_WITHOUT_OUTCOME_REJECTED",
    )
    wrong_action = object.__new__(TranslationOutcome)
    for field_name, value in (
        ("cue", accepted.translation_outcome.cue),
        ("action", TRANSLATION_OMITTED),
        ("attempts", 1),
        ("ko_text", None),
        ("reason", "invalid_ko"),
    ):
        object.__setattr__(wrong_action, field_name, value)
    expect_raises(
        KoreanCueGuardContractError,
        lambda: guard_korean_route_result(
            malformed_copy(accepted, translation_outcome=wrong_action)
        ),
        "WRONG_TRANSLATION_ACTION_REJECTED",
    )

    # J. Sequence routing preserves result count/order and route indices.
    first_route = accepted_route(
        index=1,
        start_ms=100,
        end_ms=400,
        ja_text="最初の台詞です。",
        ko_text="첫 번째 대사야.",
    )
    middle_route = filter_omitted_route(
        index=2,
        start_ms=500,
        end_ms=700,
    )
    third_route = accepted_route(
        index=3,
        start_ms=800,
        end_ms=1_200,
        ja_text="最後の台詞です。",
        ko_text="마지막 대사야.",
    )
    routes = (first_route, middle_route, third_route)
    guarded = guard_korean_sequence(routes)
    assert len(guarded) == 3
    assert tuple(result.route_result for result in guarded) == routes
    assert all(
        result.route_result is routes[position]
        for position, result in enumerate(guarded)
    )
    assert [result.route_result.index for result in guarded] == [1, 2, 3]
    ready_cues = ready_subtitle_cues(guarded)
    assert len(ready_cues) == 2
    assert ready_cues[0] is guarded[0].cue
    assert ready_cues[1] is guarded[2].cue
    assert [cue.text for cue in ready_cues] == [
        "첫 번째 대사야.",
        "마지막 대사야.",
    ]

    # K. Empty and all-omitted tuples remain representable without a document.
    assert guard_korean_sequence(()) == ()
    assert ready_subtitle_cues(()) == ()
    all_omitted = guard_korean_sequence(
        (
            filter_omitted_route(index=1),
            translation_omitted_route(index=2),
        )
    )
    assert len(all_omitted) == 2
    assert ready_subtitle_cues(all_omitted) == ()

    # L. Serialization remains downstream and numbers surviving cues 1..N.
    document = SubtitleDocument(
        format="srt",
        cues=ready_cues,
        source_sha256="0" * 64,
        byte_size=1,
    )
    serialized = serialize_srt(document).decode("utf-8")
    blocks = serialized.rstrip("\n").split("\n\n")
    assert len(blocks) == 2
    assert blocks[0].split("\n")[0] == "1"
    assert blocks[1].split("\n")[0] == "2"
    assert "00:00:00,100 --> 00:00:00,400" in blocks[0]
    assert "00:00:00,800 --> 00:00:01,200" in blocks[1]
    assert blocks[0].endswith("첫 번째 대사야.")
    assert blocks[1].endswith("마지막 대사야.")
    assert [result.route_result.index for result in guarded] == [1, 2, 3]

    # Result and sequence/projection inputs enforce immutable typed contracts.
    expect_raises(
        KoreanCueGuardValidationError,
        lambda: KoreanCueResult(
            state=FINAL_CUE_READY,
            route_result=filter_omitted,
            cue=ready.cue,
        ),
        "MALFORMED_READY_RESULT_REJECTED",
    )
    expect_raises(
        KoreanCueGuardValidationError,
        lambda: KoreanCueResult(
            state=FINAL_CUE_OMITTED,
            route_result=accepted,
            cue=None,
        ),
        "MALFORMED_OMITTED_RESULT_REJECTED",
    )
    expect_raises(
        KoreanCueGuardValidationError,
        lambda: KoreanCueResult(
            state="UNKNOWN_FINAL_STATE",
            route_result=accepted,
            cue=ready.cue,
        ),
        "UNKNOWN_FINAL_STATE_REJECTED",
    )
    expect_raises(
        KoreanCueGuardValidationError,
        lambda: guard_korean_sequence([]),
        "MUTABLE_ROUTE_SEQUENCE_REJECTED",
    )
    expect_raises(
        KoreanCueGuardValidationError,
        lambda: ready_subtitle_cues([]),
        "MUTABLE_GUARD_SEQUENCE_REJECTED",
    )
    expect_raises(
        KoreanCueGuardValidationError,
        lambda: ready_subtitle_cues(("not a guard result",)),
        "INVALID_GUARD_SEQUENCE_MEMBER_REJECTED",
    )

    try:
        ready.state = FINAL_CUE_OMITTED
    except (AttributeError, TypeError):
        pass
    else:
        raise AssertionError("KoreanCueResult must be frozen")

    production_source = Path("teddy_discovery_ko_guard.py").read_text(
        encoding="utf-8"
    )
    assert "serialize_srt" not in production_source
    assert "urllib" not in production_source
    assert "requests" not in production_source

    print("STAGE11_KO_GUARD_SMOKE=PASS")


if __name__ == "__main__":
    main()
