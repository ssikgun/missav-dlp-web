"""Deterministic Japanese lexical matching foundations for Stage11 R3.

This module is an analysis-only boundary.  It consumes the immutable R2
hybrid-evidence objects, derives bounded lexical evidence, and selects strict
monotonic anchors.  It does not alter source text, create subtitle output,
change timestamps, call a model, or perform filesystem/network/database
I/O.

``SequenceMatcher`` is used only as reproducible lexical candidate evidence;
its score is not semantic truth.  Source timestamps are retained in
``AnchorTimingEvidence`` solely as source evidence for a later deterministic
stage.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import math
import unicodedata
from typing import Final

from teddy_discovery_asr import ASRResult, MAX_ASR_SEGMENT_TEXT_CHARS
from teddy_discovery_hybrid_evidence import (
    EVIDENCE_SOURCE_ASR_SEGMENT,
    EVIDENCE_SOURCE_EXTERNAL_JA,
    HybridCueIdentity,
    HybridEvidenceBundle,
)
from teddy_discovery_subtitle_text import (
    MAX_CUE_TEXT_CHARS,
    SubtitleDocument,
)


MAX_ALIGNMENT_TEXT_CHARS: Final = min(
    MAX_CUE_TEXT_CHARS,
    MAX_ASR_SEGMENT_TEXT_CHARS,
)
DEFAULT_MINIMUM_LEXICAL_SCORE: Final[float] = 0.80
MAX_ANCHOR_CANDIDATES: Final[int] = 4_096
# This fixed CPU-safety cap is deliberately above the known 661 * 166
# comparison workload (109,726), but it is not a matching-quality threshold.
MAX_LEXICAL_PAIR_COMPARISONS: Final[int] = 256_000


class AlignmentError(ValueError):
    """Base class for deterministic alignment-analysis failures."""


class AlignmentValidationError(AlignmentError):
    """Raised when matching input or immutable evidence is invalid."""


class AlignmentLimitError(AlignmentValidationError):
    """Raised when a bounded matching input or result exceeds its limit."""


class AlignmentAmbiguityError(AlignmentValidationError):
    """Raised when equal-strength monotonic mappings cannot be chosen safely."""


def _require_exact_nonnegative_int(value: object, *, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise AlignmentValidationError(
            field_name + " must be an exact nonnegative integer"
        )
    return value


def _require_bounded_score(value: object, *, field_name: str) -> float:
    if type(value) is not float:
        raise AlignmentValidationError(
            field_name + " must be an exact float"
        )

    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise AlignmentValidationError(
            field_name + " must be finite and within [0.0, 1.0]"
        )

    return value


def _has_control_characters(value: str) -> bool:
    return any(unicodedata.category(character) == "Cc" for character in value)


def normalize_japanese_for_matching(text: str) -> str:
    """Normalize one bounded string for deterministic lexical comparison.

    The function accepts only an exact ``str``.  It applies Unicode NFKC,
    case-folds text for ASCII/Latin case equivalence, and removes Unicode
    whitespace and punctuation.  Japanese lexical characters are otherwise
    preserved; there is no transliteration or kana/kanji rewrite.

    An empty input or a value containing only removed characters returns the
    empty string.  That value is intentionally unusable as lexical evidence;
    callers that require a comparison must reject it.
    """

    if type(text) is not str:
        raise AlignmentValidationError(
            "matching text must be an exact string"
        )

    if len(text) > MAX_ALIGNMENT_TEXT_CHARS:
        raise AlignmentLimitError(
            "matching text exceeds MAX_ALIGNMENT_TEXT_CHARS"
        )

    if _has_control_characters(text):
        raise AlignmentValidationError(
            "matching text contains a control character"
        )

    normalized = unicodedata.normalize("NFKC", text).casefold()

    if len(normalized) > MAX_ALIGNMENT_TEXT_CHARS:
        raise AlignmentLimitError(
            "normalized matching text exceeds MAX_ALIGNMENT_TEXT_CHARS"
        )

    if _has_control_characters(normalized):
        raise AlignmentValidationError(
            "normalized matching text contains a control character"
        )

    comparison_characters = []
    for character in normalized:
        category = unicodedata.category(character)
        if character.isspace() or category.startswith("P"):
            continue
        comparison_characters.append(character)

    comparison = "".join(comparison_characters)
    if len(comparison) > MAX_ALIGNMENT_TEXT_CHARS:
        raise AlignmentLimitError(
            "comparison matching text exceeds MAX_ALIGNMENT_TEXT_CHARS"
        )

    return comparison


def _require_normalized_text(value: object, *, field_name: str) -> str:
    if type(value) is not str:
        raise AlignmentValidationError(field_name + " must be an exact string")

    if not value:
        raise AlignmentValidationError(
            field_name + " must not be empty after normalization"
        )

    if len(value) > MAX_ALIGNMENT_TEXT_CHARS:
        raise AlignmentLimitError(
            field_name + " exceeds MAX_ALIGNMENT_TEXT_CHARS"
        )

    if value != normalize_japanese_for_matching(value):
        raise AlignmentValidationError(
            field_name + " must already be normalized for matching"
        )

    return value


def japanese_lexical_similarity(left: str, right: str) -> float:
    """Return a reproducible lexical score in ``[0.0, 1.0]``.

    Inputs are normalized through :func:`normalize_japanese_for_matching`.
    Empty normalized strings are rejected.  ``autojunk=False`` is explicit so
    the score does not change because of a sequence-frequency heuristic.  The
    result is lexical candidate evidence only, not semantic truth.
    """

    normalized_left = normalize_japanese_for_matching(left)
    normalized_right = normalize_japanese_for_matching(right)

    if not normalized_left or not normalized_right:
        raise AlignmentValidationError(
            "lexical similarity requires nonempty normalized strings"
        )

    score = SequenceMatcher(
        a=normalized_left,
        b=normalized_right,
        autojunk=False,
    ).ratio()

    return _require_bounded_score(score, field_name="lexical similarity")


@dataclass(frozen=True)
class JapaneseComparisonEvidence:
    """Immutable normalized lexical evidence for one source pair."""

    external_normalized: str
    asr_normalized: str

    def __post_init__(self):
        _require_normalized_text(
            self.external_normalized,
            field_name="external_normalized",
        )
        _require_normalized_text(
            self.asr_normalized,
            field_name="asr_normalized",
        )


# This descriptive alias does not create a second ownership type.
NormalizedComparisonEvidence = JapaneseComparisonEvidence


def _require_timing(start_ms: object, end_ms: object, *, field_prefix: str):
    start_ms = _require_exact_nonnegative_int(
        start_ms,
        field_name=field_prefix + " start_ms",
    )
    end_ms = _require_exact_nonnegative_int(
        end_ms,
        field_name=field_prefix + " end_ms",
    )
    if end_ms <= start_ms:
        raise AlignmentValidationError(
            field_prefix + " end_ms must be greater than start_ms"
        )
    return start_ms, end_ms


@dataclass(frozen=True)
class AnchorTimingEvidence:
    """Source-only timestamps for one external/ASR candidate pair."""

    external_start_ms: int
    external_end_ms: int
    asr_start_ms: int
    asr_end_ms: int

    def __post_init__(self):
        _require_timing(
            self.external_start_ms,
            self.external_end_ms,
            field_prefix="external source timing",
        )
        _require_timing(
            self.asr_start_ms,
            self.asr_end_ms,
            field_prefix="ASR source timing",
        )


@dataclass(frozen=True)
class MonotonicAnchorCandidate:
    """One immutable lexical candidate tied to existing R2 source identities."""

    external_identity: HybridCueIdentity
    asr_identity: HybridCueIdentity
    comparison: JapaneseComparisonEvidence
    timing: AnchorTimingEvidence
    score: float

    def __post_init__(self):
        if not isinstance(self.external_identity, HybridCueIdentity):
            raise AlignmentValidationError(
                "external_identity must be a HybridCueIdentity"
            )
        if self.external_identity.source != EVIDENCE_SOURCE_EXTERNAL_JA:
            raise AlignmentValidationError(
                "external_identity must identify an external JA cue"
            )

        if not isinstance(self.asr_identity, HybridCueIdentity):
            raise AlignmentValidationError(
                "asr_identity must be a HybridCueIdentity"
            )
        if self.asr_identity.source != EVIDENCE_SOURCE_ASR_SEGMENT:
            raise AlignmentValidationError(
                "asr_identity must identify an ASR segment"
            )

        if not isinstance(self.comparison, JapaneseComparisonEvidence):
            raise AlignmentValidationError(
                "comparison must be JapaneseComparisonEvidence"
            )
        if not isinstance(self.timing, AnchorTimingEvidence):
            raise AlignmentValidationError(
                "timing must be AnchorTimingEvidence"
            )

        score = _require_bounded_score(self.score, field_name="anchor score")
        expected_score = japanese_lexical_similarity(
            self.comparison.external_normalized,
            self.comparison.asr_normalized,
        )
        if score != expected_score:
            raise AlignmentValidationError(
                "anchor score does not match deterministic lexical evidence"
            )

    @property
    def external_cue_index(self) -> int:
        return self.external_identity.source_index

    @property
    def asr_segment_index(self) -> int:
        return self.asr_identity.source_index


# The name is useful to callers without introducing a separate class.
JapaneseAnchorCandidate = MonotonicAnchorCandidate


def _validate_minimum_score(value: object) -> float:
    return _require_bounded_score(
        value,
        field_name="minimum_score",
    )


def generate_monotonic_anchor_candidates(
    bundle: HybridEvidenceBundle,
    *,
    minimum_score: float = DEFAULT_MINIMUM_LEXICAL_SCORE,
) -> tuple[MonotonicAnchorCandidate, ...]:
    """Generate bounded lexical candidates from one immutable R2 bundle.

    Every external/ASR pair is compared only when their Cartesian product is
    within ``MAX_LEXICAL_PAIR_COMPARISONS``.  There is no ordinal sampling or
    proportional guess.  Candidates are emitted in external-index, ASR-index
    order and the function fails closed if the fixed candidate bound would be
    exceeded.  An ASR-only bundle returns no fabricated external anchors.
    """

    minimum_score = _validate_minimum_score(minimum_score)

    if not isinstance(bundle, HybridEvidenceBundle):
        raise AlignmentValidationError(
            "bundle must be a HybridEvidenceBundle"
        )

    external_document = bundle.external_ja_document
    if external_document is None:
        return ()
    if not isinstance(external_document, SubtitleDocument):
        raise AlignmentValidationError(
            "bundle external JA evidence must be a SubtitleDocument"
        )

    asr_result = bundle.asr_result
    if not isinstance(asr_result, ASRResult):
        raise AlignmentValidationError(
            "bundle ASR evidence must be an ASRResult"
        )

    candidates = []
    asr_segment_count = len(asr_result.segments)
    comparison_count = len(external_document.cues) * asr_segment_count
    if comparison_count > MAX_LEXICAL_PAIR_COMPARISONS:
        raise AlignmentLimitError(
            "lexical pair comparison count exceeds "
            "MAX_LEXICAL_PAIR_COMPARISONS"
        )

    for external_index, external_cue in enumerate(external_document.cues):
        external_normalized = normalize_japanese_for_matching(external_cue.text)
        if not external_normalized:
            continue

        external_identity = bundle.cue_evidence[external_index].identity
        if (
            external_identity.source != EVIDENCE_SOURCE_EXTERNAL_JA
            or external_identity.source_index != external_index
        ):
            raise AlignmentValidationError(
                "bundle external cue identity is not source-ordinal stable"
            )

        for asr_index, asr_segment in enumerate(asr_result.segments):
            asr_normalized = normalize_japanese_for_matching(asr_segment.text)
            if not asr_normalized:
                continue

            score = japanese_lexical_similarity(
                external_normalized,
                asr_normalized,
            )
            if score < minimum_score:
                continue

            if len(candidates) >= MAX_ANCHOR_CANDIDATES:
                raise AlignmentLimitError(
                    "candidate generation exceeds MAX_ANCHOR_CANDIDATES"
                )

            candidates.append(
                MonotonicAnchorCandidate(
                    external_identity=external_identity,
                    asr_identity=HybridCueIdentity.for_asr_segment(asr_index),
                    comparison=JapaneseComparisonEvidence(
                        external_normalized=external_normalized,
                        asr_normalized=asr_normalized,
                    ),
                    timing=AnchorTimingEvidence(
                        external_start_ms=external_cue.start_ms,
                        external_end_ms=external_cue.end_ms,
                        asr_start_ms=asr_segment.start_ms,
                        asr_end_ms=asr_segment.end_ms,
                    ),
                    score=score,
                )
            )

    return tuple(candidates)


# Short descriptive alias for callers that use the noun from the roadmap.
generate_anchor_candidates = generate_monotonic_anchor_candidates


def _candidate_order_key(candidate: MonotonicAnchorCandidate) -> tuple[int, int]:
    return (
        candidate.external_cue_index,
        candidate.asr_segment_index,
    )


def select_monotonic_anchors(
    candidates: tuple[MonotonicAnchorCandidate, ...],
) -> tuple[MonotonicAnchorCandidate, ...]:
    """Select the unique maximum-score strict-monotonic candidate chain.

    Candidate input is canonicalized by source ordinals.  Both ordinals must
    increase strictly, so source reuse is impossible.  If two different
    chains have the same maximum score, selection raises
    ``AlignmentAmbiguityError`` instead of silently choosing one.  Zero-score
    candidates remain unmatched.
    """

    if type(candidates) is not tuple:
        raise AlignmentValidationError(
            "candidates must be an immutable tuple"
        )

    if len(candidates) > MAX_ANCHOR_CANDIDATES:
        raise AlignmentLimitError(
            "candidates exceeds MAX_ANCHOR_CANDIDATES"
        )

    seen_pairs = set()
    validated = []
    for candidate in candidates:
        if not isinstance(candidate, MonotonicAnchorCandidate):
            raise AlignmentValidationError(
                "candidates must contain MonotonicAnchorCandidate values"
            )

        pair = (
            candidate.external_cue_index,
            candidate.asr_segment_index,
        )
        if pair in seen_pairs:
            raise AlignmentValidationError(
                "duplicate external/ASR candidate pair is not allowed"
            )
        seen_pairs.add(pair)
        validated.append(candidate)

    ordered = tuple(sorted(validated, key=_candidate_order_key))
    eligible = tuple(candidate for candidate in ordered if candidate.score > 0.0)
    if not eligible:
        return ()

    # Each state is (best total score ending here, count capped at two,
    # parent state index).  Only scores and parent indexes are retained; no
    # uncontrolled chain copies or text blobs are stored.
    states: list[tuple[float, int, int | None]] = []
    for current_index, current in enumerate(eligible):
        best_previous_score = 0.0
        best_previous_count = 1
        best_parent_index = None

        for previous_index, previous in enumerate(eligible[:current_index]):
            if previous.external_cue_index >= current.external_cue_index:
                continue
            if previous.asr_segment_index >= current.asr_segment_index:
                continue

            previous_score, previous_count, _ = states[previous_index]
            if previous_score > best_previous_score:
                best_previous_score = previous_score
                best_previous_count = previous_count
                best_parent_index = previous_index
            elif previous_score == best_previous_score:
                best_previous_count = min(
                    2,
                    best_previous_count + previous_count,
                )
                if best_parent_index is None or previous_index < best_parent_index:
                    best_parent_index = previous_index

        states.append(
            (
                best_previous_score + current.score,
                best_previous_count,
                best_parent_index,
            )
        )

    best_total = max(state[0] for state in states)
    best_state_count = min(
        2,
        sum(state[1] for state in states if state[0] == best_total),
    )
    if best_state_count > 1:
        raise AlignmentAmbiguityError(
            "equal-strength monotonic anchor chains are ambiguous"
        )

    best_state_index = next(
        index
        for index, state in enumerate(states)
        if state[0] == best_total
    )

    selected_reversed = []
    current_state_index: int | None = best_state_index
    while current_state_index is not None:
        selected_reversed.append(eligible[current_state_index])
        current_state_index = states[current_state_index][2]

    selected_reversed.reverse()
    return tuple(selected_reversed)


select_monotonic_anchor_candidates = select_monotonic_anchors


__all__ = [
    "AlignmentAmbiguityError",
    "AlignmentError",
    "AlignmentLimitError",
    "AlignmentValidationError",
    "AnchorTimingEvidence",
    "DEFAULT_MINIMUM_LEXICAL_SCORE",
    "JapaneseAnchorCandidate",
    "JapaneseComparisonEvidence",
    "MAX_ANCHOR_CANDIDATES",
    "MAX_ALIGNMENT_TEXT_CHARS",
    "MAX_LEXICAL_PAIR_COMPARISONS",
    "MonotonicAnchorCandidate",
    "NormalizedComparisonEvidence",
    "generate_anchor_candidates",
    "generate_monotonic_anchor_candidates",
    "japanese_lexical_similarity",
    "normalize_japanese_for_matching",
    "select_monotonic_anchors",
    "select_monotonic_anchor_candidates",
]
