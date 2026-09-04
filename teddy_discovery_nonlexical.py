"""Conservative, text-only Stage11 non-lexical cue classification.

The classifier is intentionally narrower than Japanese semantic analysis.  It
only omits a highly constrained repeated-vocalic spelling; every other valid
text is kept.  The source text is never rewritten and cue metadata is outside
this module's boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
import unicodedata

from teddy_discovery_subtitle_text import MAX_CUE_TEXT_CHARS


MAX_NONLEXICAL_TEXT_CHARS = MAX_CUE_TEXT_CHARS
MIN_REPEATED_VOCALIC_RUN = 4

NONLEXICAL_KEEP = "KEEP"
NONLEXICAL_OMIT = "OMIT"

NONLEXICAL_REASON_REPEATED_PURE_VOCALIC_RUN = (
    "repeated_pure_vocalic_run"
)
NONLEXICAL_REASON_LEXICAL_OR_AMBIGUOUS = "lexical_or_ambiguous"
NONLEXICAL_REASON_PUNCTUATION_ONLY = "punctuation_only"

# This is a generic language-level spelling primitive, not a dialogue or title
# dictionary.  Excluding nasal/sokuon kana keeps common meaningful reactions
# and ambiguous breath-like text on the KEEP side of the boundary.
_VOWEL_LIKE_KANA = frozenset(
    "あいうえおぁぃぅぇぉアイウエオァィゥェォ"
)

# Only these marks may be ignored at the outside of an analysis view.  Marks
# in the middle are never removed, so punctuation cannot manufacture a run.
_ALLOWED_SURROUNDING_PUNCTUATION = frozenset(".!?！？…⋯")
_ANALYSIS_WHITESPACE = frozenset({" ", "\t", "\n"})


class NonLexicalError(ValueError):
    """Base class for deterministic non-lexical filter failures."""


class NonLexicalValidationError(NonLexicalError):
    """Raised when the classifier input or decision contract is invalid."""


class NonLexicalLimitError(NonLexicalError):
    """Raised when the classifier input exceeds its fixed text bound."""


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


def _validate_text(text: object) -> str:
    if not isinstance(text, str):
        raise NonLexicalValidationError("non-lexical text must be a string")
    if not text.strip():
        raise NonLexicalValidationError(
            "non-lexical text must not be empty or whitespace-only"
        )
    if len(text) > MAX_NONLEXICAL_TEXT_CHARS:
        raise NonLexicalLimitError(
            "non-lexical text exceeds MAX_CUE_TEXT_CHARS"
        )
    if _has_disallowed_control_characters(text):
        raise NonLexicalValidationError(
            "non-lexical text contains a disallowed control character"
        )
    return text


def _validate_reason(reason: object) -> str:
    if (
        not isinstance(reason, str)
        or not reason
        or _has_disallowed_control_characters(reason)
    ):
        raise NonLexicalValidationError("non-lexical decision reason is invalid")
    return reason


@dataclass(frozen=True)
class NonLexicalDecision:
    """Immutable action/reason pair; no replacement text or cue metadata."""

    action: str
    reason: str

    def __post_init__(self):
        if self.action not in {NONLEXICAL_KEEP, NONLEXICAL_OMIT}:
            raise NonLexicalValidationError(
                "non-lexical decision action is invalid"
            )
        _validate_reason(self.reason)


def _analysis_core(text: str) -> str:
    # NFKC is classification-only.  The caller's text is never returned or
    # replaced.  Whitespace and a small punctuation set are removable only at
    # the outside; internal characters remain evidence against omission.
    normalized = unicodedata.normalize("NFKC", text)
    start = 0
    end = len(normalized)

    while start < end and normalized[start] in _ANALYSIS_WHITESPACE:
        start += 1
    while end > start and normalized[end - 1] in _ANALYSIS_WHITESPACE:
        end -= 1

    while start < end and normalized[start] in _ALLOWED_SURROUNDING_PUNCTUATION:
        start += 1
        while start < end and normalized[start] in _ANALYSIS_WHITESPACE:
            start += 1
    while end > start and normalized[end - 1] in _ALLOWED_SURROUNDING_PUNCTUATION:
        end -= 1
        while end > start and normalized[end - 1] in _ANALYSIS_WHITESPACE:
            end -= 1

    return normalized[start:end]


def classify_nonlexical(text: str) -> NonLexicalDecision:
    """Classify one text cue without changing its text or metadata.

    OMIT is returned only for an analysis view containing one identical
    vowel-like Japanese kana codepoint repeated at least four times.  This
    deliberately does not recognize all kana, short text, nasal/sokuon sounds,
    breath-like spellings, or any lexical phrase.
    """

    validated = _validate_text(text)
    core = _analysis_core(validated)

    if not core:
        return NonLexicalDecision(
            action=NONLEXICAL_KEEP,
            reason=NONLEXICAL_REASON_PUNCTUATION_ONLY,
        )

    if (
        len(core) >= MIN_REPEATED_VOCALIC_RUN
        and core[0] in _VOWEL_LIKE_KANA
        and all(character == core[0] for character in core)
    ):
        return NonLexicalDecision(
            action=NONLEXICAL_OMIT,
            reason=NONLEXICAL_REASON_REPEATED_PURE_VOCALIC_RUN,
        )

    return NonLexicalDecision(
        action=NONLEXICAL_KEEP,
        reason=NONLEXICAL_REASON_LEXICAL_OR_AMBIGUOUS,
    )


__all__ = [
    "MAX_NONLEXICAL_TEXT_CHARS",
    "MIN_REPEATED_VOCALIC_RUN",
    "NONLEXICAL_KEEP",
    "NONLEXICAL_OMIT",
    "NONLEXICAL_REASON_LEXICAL_OR_AMBIGUOUS",
    "NONLEXICAL_REASON_PUNCTUATION_ONLY",
    "NONLEXICAL_REASON_REPEATED_PURE_VOCALIC_RUN",
    "NonLexicalDecision",
    "NonLexicalError",
    "NonLexicalLimitError",
    "NonLexicalValidationError",
    "classify_nonlexical",
]
