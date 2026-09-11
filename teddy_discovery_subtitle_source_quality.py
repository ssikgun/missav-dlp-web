"""Deterministic external-JA quality evidence; no repair, timing edits or I/O.

Fragment observations only request second evidence. Neither external text nor
STT is treated as ground truth; accepted STT is support, not a replacement.
"""
from dataclasses import dataclass
import re
from statistics import median
import unicodedata

from teddy_discovery_stateful_parts import has_runaway_repetition
from teddy_discovery_subtitle_text import (
    MAX_CUE_TEXT_CHARS, MAX_SUBTITLE_CUES, SubtitleCue, SubtitleDocument,
)

KEEP = "KEEP"
OMIT_METADATA = "OMIT_METADATA"
REQUIRE_SECOND_EVIDENCE = "REQUIRE_SECOND_EVIDENCE"
KEEP_WITH_SECOND_EVIDENCE = "KEEP_WITH_SECOND_EVIDENCE"
OMIT_FRAGMENT_UNSUPPORTED = "OMIT_FRAGMENT_UNSUPPORTED"

# Limit authoring evidence to a small same-sentence neighborhood.
AUTHORING_MAX_CONTEXT_CHARS = 8
# A single reaction or a brief exchange is not a fragment burst.
FRAGMENT_MIN_RUN = 6
# Most normalized spellings must differ, excluding repeated normal reactions.
FRAGMENT_MIN_UNIQUE_RATIO = 0.75
# Gaps must be no longer than typical cue occupancy to constitute dense timing.
FRAGMENT_MAX_GAP_DURATION_RATIO = 1.0
FRAGMENT_MAX_CORE_KANA = 2

_AUTHORING_CONTEXT = rf"[^\n\r。！？!?]{{0,{AUTHORING_MAX_CONTEXT_CHARS}}}"
_AUTHORING_RE = re.compile(
    rf"字幕{_AUTHORING_CONTEXT}(?:作成|制作|製作)"
    rf"|(?:作成|制作|製作){_AUTHORING_CONTEXT}字幕"
)
_VERSION_RE = re.compile(r"(?<![a-z0-9.])v?\d+(?:\.\d+)+(?![a-z0-9.])", re.I)
_CORE_EDGE_MARKS = " \t\n\r.!?！？…⋯、。「」『』（）()"
_SOURCE_REASONS = {
    "no_quality_objection": KEEP,
    "subtitle_authoring_structure": OMIT_METADATA,
    "ascii_tool_version_structure": OMIT_METADATA,
    "dense_diverse_kana_run": REQUIRE_SECOND_EVIDENCE,
}
_OUTCOME_REASONS = {
    "source_keep": KEEP,
    "metadata_text_only": OMIT_METADATA,
    "second_evidence_present": KEEP_WITH_SECOND_EVIDENCE,
    "second_evidence_missing": OMIT_FRAGMENT_UNSUPPORTED,
    "second_evidence_runaway": OMIT_FRAGMENT_UNSUPPORTED,
}


class SourceQualityError(ValueError):
    """Invalid input or detached decision; never silently accepted."""


def _validate_text(text):
    if (type(text) is not str or not text.strip()
            or len(text) > MAX_CUE_TEXT_CHARS):
        raise SourceQualityError("text must be a bounded nonempty exact string")
    if any(unicodedata.category(c) in {"Cc", "Cs"} and c not in "\n\r\t" for c in text):
        raise SourceQualityError("text contains invalid controls or Unicode")


def _validate_index(index):
    if type(index) is not int or not 0 <= index < MAX_SUBTITLE_CUES:
        raise SourceQualityError("source_index must be an original bounded nonnegative index")


@dataclass(frozen=True)
class SourceQualityCue:
    """Explicit original document index, also for already filtered subsets."""
    source_index: int
    cue: SubtitleCue

    def __post_init__(self):
        _validate_index(self.source_index)
        if type(self.cue) is not SubtitleCue:
            raise SourceQualityError("cue must be an exact SubtitleCue")
        _validate_text(self.cue.text)
        try:
            SubtitleCue(self.cue.start_ms, self.cue.end_ms, self.cue.text)
        except ValueError as error:
            raise SourceQualityError("invalid cue") from error


@dataclass(frozen=True)
class SourceQualityDecision:
    source_index: int
    action: str
    reason: str
    source_text: str

    def __post_init__(self):
        _validate_index(self.source_index)
        _validate_text(self.source_text)
        if (type(self.action) is not str or type(self.reason) is not str
                or self.reason not in _SOURCE_REASONS
                or _SOURCE_REASONS[self.reason] != self.action):
            raise SourceQualityError("invalid source action/reason")


@dataclass(frozen=True)
class SecondEvidenceOutcome:
    source_decision: SourceQualityDecision
    action: str
    reason: str

    def __post_init__(self):
        if type(self.source_decision) is not SourceQualityDecision:
            raise SourceQualityError("invalid source decision")
        self.source_decision.__post_init__()
        if (type(self.action) is not str or type(self.reason) is not str
                or self.reason not in _OUTCOME_REASONS
                or _OUTCOME_REASONS[self.reason] != self.action):
            raise SourceQualityError("invalid second-evidence action/reason")
        expected = {KEEP: {KEEP}, OMIT_METADATA: {OMIT_METADATA},
                    REQUIRE_SECOND_EVIDENCE: {KEEP_WITH_SECOND_EVIDENCE, OMIT_FRAGMENT_UNSUPPORTED}}
        if self.action not in expected[self.source_decision.action]:
            raise SourceQualityError("outcome is detached from source decision")

    @property
    def source_index(self):
        return self.source_decision.source_index

    @property
    def source_text(self):
        return self.source_decision.source_text


def _metadata_reason(text):
    if _AUTHORING_RE.search(text):
        return "subtitle_authoring_structure"
    if (text.isascii() and re.search(r"[A-Za-z]", text)
            and _VERSION_RE.search(text) and ("|" in text or "/" in text)):
        return "ascii_tool_version_structure"
    return "no_quality_objection"


def _kana_core(text):
    core = unicodedata.normalize("NFKC", text).strip(_CORE_EDGE_MARKS)
    # Hiragana/katakana variants count as the same spelling for diversity.
    core = "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in core)
    if (1 <= len(core) <= FRAGMENT_MAX_CORE_KANA
            and all("ぁ" <= c <= "ゖ" or c == "ー" for c in core)
            and any(c != "ー" for c in core)):
        return core
    return None


def classify_source_quality(cues: tuple[SourceQualityCue, ...]) -> tuple[SourceQualityDecision, ...]:
    """Classify explicit original-index cues; gaps in indexes break runs.

    Observes maximal consecutive short-kana runs, not selected subwindows.
    Overlap contributes zero gap. Input must retain original index/time order.
    No result is filtered or reindexed, and original text is retained verbatim.
    """
    if type(cues) is not tuple or len(cues) > MAX_SUBTITLE_CUES:
        raise SourceQualityError("cues must be a bounded immutable tuple")
    previous = None
    for item in cues:
        if type(item) is not SourceQualityCue:
            raise SourceQualityError("expected indexed source cue")
        item.__post_init__()
        if previous is not None and (item.source_index <= previous.source_index
                                    or item.cue.start_ms < previous.cue.start_ms):
            raise SourceQualityError("source indexes and cue times must retain original order")
        previous = item
    reasons = [_metadata_reason(item.cue.text) for item in cues]
    cores = [_kana_core(item.cue.text) if reasons[i] == "no_quality_objection" else None
             for i, item in enumerate(cues)]

    def observe(start, end):
        count = end - start
        if count < FRAGMENT_MIN_RUN or len(set(cores[start:end])) / count < FRAGMENT_MIN_UNIQUE_RATIO:
            return
        durations = [item.cue.end_ms - item.cue.start_ms for item in cues[start:end]]
        gaps = [max(0, cues[i].cue.start_ms - cues[i - 1].cue.end_ms)
                for i in range(start + 1, end)]
        if median(gaps) <= median(durations) * FRAGMENT_MAX_GAP_DURATION_RATIO:
            reasons[start:end] = ["dense_diverse_kana_run"] * count

    start = None
    for i, core in enumerate(cores):
        if start is not None and (core is None or cues[i].source_index != cues[i - 1].source_index + 1):
            observe(start, i)
            start = None
        if core is not None and start is None:
            start = i
    if start is not None:
        observe(start, len(cues))
    return tuple(SourceQualityDecision(item.source_index, _SOURCE_REASONS[reason], reason, item.cue.text)
                 for item, reason in zip(cues, reasons))


def classify_source_document(document: SubtitleDocument) -> tuple[SourceQualityDecision, ...]:
    """For a complete original external-JA document only, never a filtered copy."""
    if type(document) is not SubtitleDocument:
        raise SourceQualityError("expected original SubtitleDocument")
    try:
        document.__post_init__()
    except (TypeError, ValueError) as error:
        raise SourceQualityError("invalid source document") from error
    return classify_source_quality(tuple(SourceQualityCue(i, cue) for i, cue in enumerate(document.cues)))


def resolve_second_evidence(decision: SourceQualityDecision, second_stt: str | None) -> SecondEvidenceOutcome:
    """Resolve quality policy only; STT identity/timing binding stays caller-owned.

    KEEP and metadata ignore STT. Suspects require a valid exact string and the
    canonical one-string repetition check. Invalid evidence raises; missing or
    runaway evidence yields an explicit unsupported-fragment omission.
    """
    if type(decision) is not SourceQualityDecision:
        raise SourceQualityError("expected source-quality decision")
    decision.__post_init__()
    if decision.action == KEEP:
        reason = "source_keep"
    elif decision.action == OMIT_METADATA:
        reason = "metadata_text_only"
    elif second_stt is None:
        reason = "second_evidence_missing"
    else:
        _validate_text(second_stt)
        reason = "second_evidence_runaway" if has_runaway_repetition(second_stt) else "second_evidence_present"
    return SecondEvidenceOutcome(decision, _OUTCOME_REASONS[reason], reason)
