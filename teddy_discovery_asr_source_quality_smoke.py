"""Offline smoke tests for the route-neutral ASR source-quality layer."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import re

from teddy_discovery_asr import ASRSegment
from teddy_discovery_asr_source_quality import (
    ASR_SOURCE_KEEP,
    ASR_SOURCE_OMIT,
    ASR_SOURCE_REASON_CONSECUTIVE_RUN,
    ASR_SOURCE_REASON_DOCUMENT_RECURRENCE,
    ASR_SOURCE_REASON_EXISTING_RUNAWAY,
    ASR_SOURCE_REASON_INTRA_CUE_REPETITION,
    ASR_SOURCE_REQUIRE_SECOND_EVIDENCE,
    ASRSourceQualityDecision,
    ASRSourceQualityError,
    classify_asr_source_quality,
    retained_asr_source_indexes,
    validate_asr_source_quality_decisions,
)
from teddy_discovery_nonlexical import (
    NONLEXICAL_REASON_REPEATED_PURE_VOCALIC_RUN,
)


def expect(error_type, callback):
    try:
        callback()
    except error_type:
        return
    raise AssertionError("expected " + error_type.__name__)


def segments_for(texts):
    return tuple(
        ASRSegment(
            start_ms=index * 100,
            end_ms=index * 100 + 90,
            text=text,
        )
        for index, text in enumerate(texts)
    )


def main():
    source_texts = (
        "今日は",
        "あ、あ、あ、あ",
        "はい",
        "はい",
        "はい",
        "そう",
        "一旦、一旦、一旦、一旦",
        "今日は",
        "今日は",
        "ああああ",
        "ん" * 64,
        "うん",
    )
    source = segments_for(source_texts)
    fingerprint = tuple(
        (segment.start_ms, segment.end_ms, segment.text)
        for segment in source
    )

    decisions = classify_asr_source_quality(source)
    repeated_again = classify_asr_source_quality(source)
    assert decisions == repeated_again
    assert tuple(
        (segment.start_ms, segment.end_ms, segment.text)
        for segment in source
    ) == fingerprint
    assert len(decisions) == len(source)
    assert tuple(decision.source_index for decision in decisions) == tuple(
        range(len(source))
    )
    assert all(
        decision.source_text == source[decision.source_index].text
        and decision.start_ms == source[decision.source_index].start_ms
        and decision.end_ms == source[decision.source_index].end_ms
        for decision in decisions
    )

    # Existing nonlexical behavior remains the only hard-OMIT path.
    hard_omit = decisions[9]
    assert hard_omit.action == ASR_SOURCE_OMIT
    assert hard_omit.reason == NONLEXICAL_REASON_REPEATED_PURE_VOCALIC_RUN
    assert hard_omit.evidence.nonlexical_reason == (
        NONLEXICAL_REASON_REPEATED_PURE_VOCALIC_RUN
    )
    assert retained_asr_source_indexes(decisions) == (
        0,
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        10,
        11,
    )

    # Normal lexical and meaningful short reaction input is retained.
    assert decisions[5].action == ASR_SOURCE_KEEP
    assert decisions[11].action == ASR_SOURCE_KEEP
    assert decisions[5].features == ()
    assert decisions[0].action == ASR_SOURCE_KEEP
    assert decisions[0].features == (ASR_SOURCE_REASON_DOCUMENT_RECURRENCE,)
    assert decisions[2].action == ASR_SOURCE_KEEP
    assert decisions[2].features == (
        ASR_SOURCE_REASON_CONSECUTIVE_RUN,
        ASR_SOURCE_REASON_DOCUMENT_RECURRENCE,
    )

    # Structural observations are suspicious-only and retain source identity.
    intra = decisions[1]
    assert intra.action == ASR_SOURCE_REQUIRE_SECOND_EVIDENCE
    assert intra.reason == ASR_SOURCE_REASON_INTRA_CUE_REPETITION
    assert intra.evidence.intra_cue_unit == "あ"
    assert intra.evidence.intra_cue_repetitions == 4

    punctuation_whitespace = classify_asr_source_quality(
        segments_for(("一旦、一旦、一旦、一旦", "一旦 一旦 一旦 一旦"))
    )
    assert all(
        decision.action == ASR_SOURCE_REQUIRE_SECOND_EVIDENCE
        and decision.reason == ASR_SOURCE_REASON_INTRA_CUE_REPETITION
        for decision in punctuation_whitespace
    )

    consecutive = decisions[2:5]
    assert all(
        decision.action == ASR_SOURCE_KEEP
        and ASR_SOURCE_REASON_CONSECUTIVE_RUN in decision.features
        and decision.evidence.consecutive_run_length == 3
        for decision in consecutive
    )

    recurrent = decisions[0]
    assert recurrent.action == ASR_SOURCE_KEEP
    assert recurrent.reason == "lexical_or_ambiguous"
    assert recurrent.features == (ASR_SOURCE_REASON_DOCUMENT_RECURRENCE,)
    assert recurrent.evidence.document_frequency == 3
    assert recurrent.evidence.document_first_index == 0
    assert recurrent.evidence.document_last_index == 8
    assert recurrent.evidence.document_span_ms == 890

    existing_runaway = decisions[10]
    assert existing_runaway.action == ASR_SOURCE_REQUIRE_SECOND_EVIDENCE
    assert ASR_SOURCE_REASON_EXISTING_RUNAWAY in existing_runaway.evidence_reasons
    assert existing_runaway.features == (
        ASR_SOURCE_REASON_INTRA_CUE_REPETITION,
        ASR_SOURCE_REASON_EXISTING_RUNAWAY,
    )

    # Feature presence is independent from severity: both diagnostic-only
    # KEEP shapes and actionable REQUIRE/OMIT shapes are representable.
    assert decisions[1].features == (ASR_SOURCE_REASON_INTRA_CUE_REPETITION,)
    assert decisions[9].features == (
        NONLEXICAL_REASON_REPEATED_PURE_VOCALIC_RUN,
        ASR_SOURCE_REASON_INTRA_CUE_REPETITION,
    )
    expect(
        ASRSourceQualityError,
        lambda: replace(
            decisions[0],
            features=(ASR_SOURCE_REASON_DOCUMENT_RECURRENCE,) * 2,
        ),
    )
    expect(
        ASRSourceQualityError,
        lambda: replace(decisions[0], features=("unknown_feature",)),
    )
    expect(
        ASRSourceQualityError,
        lambda: replace(
            decisions[2],
            features=(
                ASR_SOURCE_REASON_DOCUMENT_RECURRENCE,
                ASR_SOURCE_REASON_CONSECUTIVE_RUN,
            ),
        ),
    )

    # Omitting the additive field is a legacy fixture shape.  The default
    # keeps the old positional constructor contract, and validation accepts
    # it before returning the current fully featured decision tuple.
    legacy_first = ASRSourceQualityDecision(
        decisions[0].source_index,
        decisions[0].start_ms,
        decisions[0].end_ms,
        decisions[0].source_text,
        decisions[0].action,
        decisions[0].reason,
        decisions[0].evidence_reasons,
        decisions[0].evidence,
    )
    assert legacy_first.features == ()
    legacy = (legacy_first,) + decisions[1:]
    upgraded = validate_asr_source_quality_decisions(source, legacy)
    assert upgraded == decisions

    # The validation boundary rejects empty, detached, unordered, or altered
    # source material and decisions rather than inventing a fallback.
    expect(ASRSourceQualityError, lambda: classify_asr_source_quality(()))
    expect(ASRSourceQualityError, lambda: classify_asr_source_quality([]))
    expect(ASRSourceQualityError, lambda: classify_asr_source_quality(None))
    expect(
        ASRSourceQualityError,
        lambda: classify_asr_source_quality(("not an ASR segment",)),
    )
    expect(
        ASRSourceQualityError,
        lambda: classify_asr_source_quality(
            (
                ASRSegment(100, 190, "はい"),
                ASRSegment(50, 140, "うん"),
            )
        ),
    )
    validate_asr_source_quality_decisions(source, decisions)
    expect(
        ASRSourceQualityError,
        lambda: validate_asr_source_quality_decisions(
            source,
            decisions[:-1],
        ),
    )
    expect(
        ASRSourceQualityError,
        lambda: validate_asr_source_quality_decisions(
            source,
            decisions[:1]
            + (replace(decisions[1], source_text="다른 원문"),)
            + decisions[2:],
        ),
    )
    frozen = decisions[1]
    expect(
        FrozenInstanceError,
        lambda: setattr(frozen, "source_text", "rewritten"),
    )

    # The core contains no route, title, cue, model, or observed-phrase
    # exception.  Structural classification must be generic and deterministic.
    module_source = Path(__file__.replace("_smoke.py", ".py")).read_text(
        encoding="utf-8"
    )
    assert "Whisper" not in module_source
    assert "Hermes" not in module_source
    assert "ご視聴ありがとうございました" not in module_source
    assert not re.search(r"(?i)ADN|JUR|asr-000", module_source)

    # A recurrent phrase is observed structurally, not by meaning or a
    # hard-coded phrase list; it is never promoted to hard OMIT.
    recurrent_phrase = classify_asr_source_quality(
        segments_for(("再生", "別の文", "再生", "再生"))
    )
    assert recurrent_phrase[0].action == ASR_SOURCE_KEEP
    assert recurrent_phrase[0].features == (ASR_SOURCE_REASON_DOCUMENT_RECURRENCE,)
    assert all(
        decision.action != ASR_SOURCE_OMIT
        for decision in recurrent_phrase
    )

    print("ASR_SOURCE_QUALITY_SMOKE=PASS")


if __name__ == "__main__":
    main()
