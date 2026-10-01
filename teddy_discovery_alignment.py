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

from bisect import bisect_left
from dataclasses import dataclass
from difflib import SequenceMatcher
from fractions import Fraction
import math
import unicodedata
from typing import Final, Iterator

from teddy_discovery_asr import ASRResult, MAX_ASR_SEGMENT_TEXT_CHARS
from teddy_discovery_hybrid_evidence import (
    EVIDENCE_SOURCE_ASR_SEGMENT,
    EVIDENCE_SOURCE_EXTERNAL_JA,
    HybridCueIdentity,
    HybridEvidenceBundle,
    stable_cue_id,
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
MIN_AFFINE_CONSENSUS_SCALE: Final[float] = 0.95
MAX_AFFINE_CONSENSUS_SCALE: Final[float] = 1.05
MAX_ANCHOR_CANDIDATES: Final[int] = 4_096
# This fixed CPU-safety cap is a generic power-of-two bound, not a
# matching-quality threshold.
MAX_LEXICAL_PAIR_COMPARISONS: Final[int] = 1_048_576
MIN_AFFINE_ANCHORS: Final[int] = 3
# Pairwise slope generation is quadratic; this fixed bound protects CPU and
# memory while still covering ordinary selected-anchor evidence sets.
MAX_AFFINE_ANCHORS: Final[int] = 512
# Consensus search considers every valid lexical-candidate pair, then uses
# fixed work caps for hypothesis evaluation and tied-path reconstruction.
MAX_AFFINE_CONSENSUS_HYPOTHESES: Final[int] = 65_536
MAX_AFFINE_CONSENSUS_CANDIDATE_EVALUATIONS: Final[int] = 16_777_216
MAX_AFFINE_CONSENSUS_DP_OPERATIONS: Final[int] = 16_777_216
MAX_AFFINE_CONSENSUS_CHAINS_PER_HYPOTHESIS: Final[int] = 64
MAX_AFFINE_CONSENSUS_PATHS_EVALUATED: Final[int] = 65_536
# Full-chain storage contract for the legacy tuple API only. Streaming
# identity storage and computation remain bounded by the work caps above/below.
MAX_AFFINE_CONSENSUS_UNIQUE_CHAINS: Final[int] = 2_048
MAX_AFFINE_CONSENSUS_FIT_PAIR_EVALUATIONS: Final[int] = 16_777_216
MAX_AFFINE_CONSENSUS_PAIR_COMPARISONS: Final[int] = (
    MAX_ANCHOR_CANDIDATES * (MAX_ANCHOR_CANDIDATES - 1) // 2
)


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

    # Parsed subtitle cue text can contain intentional line breaks. Convert
    # only CR/LF in this derived comparison value; the cue's source text is
    # immutable and every other control character remains rejected below.
    text = text.replace("\r", " ").replace("\n", " ")

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


def _require_exact_positive_int(value: object, *, field_name: str) -> int:
    if type(value) is not int or value <= 0:
        raise AlignmentValidationError(
            field_name + " must be an exact positive integer"
        )
    return value


def _require_finite_float(
    value: object,
    *,
    field_name: str,
    strictly_positive: bool = False,
) -> float:
    if type(value) is not float or not math.isfinite(value):
        raise AlignmentValidationError(field_name + " must be a finite float")
    if strictly_positive and value <= 0.0:
        raise AlignmentValidationError(
            field_name + " must be strictly positive"
        )
    return value


def _fraction_to_finite_float(value: Fraction, *, field_name: str) -> float:
    try:
        converted = float(value)
    except (OverflowError, ValueError) as error:
        raise AlignmentValidationError(
            field_name + " cannot be represented as a finite float"
        ) from error
    return _require_finite_float(converted, field_name=field_name)


def _median_fraction(values: list[Fraction]) -> Fraction:
    if not values:
        raise AlignmentValidationError("median requires at least one value")

    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _validate_affine_identity(
    identity: object,
    *,
    expected_source: str,
    field_name: str,
) -> HybridCueIdentity:
    if not isinstance(identity, HybridCueIdentity):
        raise AlignmentValidationError(
            field_name + " must be a HybridCueIdentity"
        )
    if identity.source != expected_source:
        raise AlignmentValidationError(
            field_name + " has an invalid source kind"
        )

    _require_exact_nonnegative_int(
        identity.source_index,
        field_name=field_name + " source_index",
    )
    try:
        expected_cue_id = stable_cue_id(
            expected_source,
            identity.source_index,
        )
    except (TypeError, ValueError) as error:
        raise AlignmentValidationError(
            field_name + " source_index is outside the source identity bound"
        ) from error

    if type(identity.cue_id) is not str or identity.cue_id != expected_cue_id:
        raise AlignmentValidationError(
            field_name + " is not a stable source identity"
        )
    return identity


def _validate_affine_timing(
    timing: object,
    *,
    field_name: str,
) -> AnchorTimingEvidence:
    if not isinstance(timing, AnchorTimingEvidence):
        raise AlignmentValidationError(
            field_name + " must be AnchorTimingEvidence"
        )

    _require_timing(
        timing.external_start_ms,
        timing.external_end_ms,
        field_prefix=field_name + " external source timing",
    )
    _require_timing(
        timing.asr_start_ms,
        timing.asr_end_ms,
        field_prefix=field_name + " ASR source timing",
    )
    return timing


def _validate_affine_anchors(
    anchors: object,
) -> tuple[MonotonicAnchorCandidate, ...]:
    if type(anchors) is not tuple:
        raise AlignmentValidationError(
            "anchors must be an immutable tuple"
        )
    if len(anchors) < MIN_AFFINE_ANCHORS:
        raise AlignmentValidationError(
            "anchors must contain at least MIN_AFFINE_ANCHORS values"
        )
    if len(anchors) > MAX_AFFINE_ANCHORS:
        raise AlignmentLimitError(
            "anchors exceeds MAX_AFFINE_ANCHORS"
        )

    seen_external = set()
    seen_asr = set()
    previous_external_index = None
    previous_asr_index = None

    for position, anchor in enumerate(anchors):
        if not isinstance(anchor, MonotonicAnchorCandidate):
            raise AlignmentValidationError(
                "anchors must contain MonotonicAnchorCandidate values"
            )

        external_identity = _validate_affine_identity(
            anchor.external_identity,
            expected_source=EVIDENCE_SOURCE_EXTERNAL_JA,
            field_name="anchor " + str(position) + " external_identity",
        )
        asr_identity = _validate_affine_identity(
            anchor.asr_identity,
            expected_source=EVIDENCE_SOURCE_ASR_SEGMENT,
            field_name="anchor " + str(position) + " asr_identity",
        )
        _validate_affine_timing(
            anchor.timing,
            field_name="anchor " + str(position),
        )

        external_index = external_identity.source_index
        asr_index = asr_identity.source_index
        if external_identity.cue_id in seen_external:
            raise AlignmentValidationError(
                "anchors contain a duplicate external source identity"
            )
        if asr_identity.cue_id in seen_asr:
            raise AlignmentValidationError(
                "anchors contain a duplicate ASR source identity"
            )
        if (
            previous_external_index is not None
            and external_index <= previous_external_index
        ):
            raise AlignmentValidationError(
                "external anchor indexes must increase strictly"
            )
        if (
            previous_asr_index is not None
            and asr_index <= previous_asr_index
        ):
            raise AlignmentValidationError(
                "ASR anchor indexes must increase strictly"
            )

        seen_external.add(external_identity.cue_id)
        seen_asr.add(asr_identity.cue_id)
        previous_external_index = external_index
        previous_asr_index = asr_index

    return anchors


def _midpoint_x2(timing: AnchorTimingEvidence, *, source: str) -> int:
    if source == EVIDENCE_SOURCE_EXTERNAL_JA:
        start_ms = timing.external_start_ms
        end_ms = timing.external_end_ms
    elif source == EVIDENCE_SOURCE_ASR_SEGMENT:
        start_ms = timing.asr_start_ms
        end_ms = timing.asr_end_ms
    else:
        raise AlignmentValidationError("unsupported midpoint source")

    _require_exact_nonnegative_int(
        start_ms,
        field_name=source + " midpoint start_ms",
    )
    _require_exact_nonnegative_int(
        end_ms,
        field_name=source + " midpoint end_ms",
    )
    if end_ms <= start_ms:
        raise AlignmentValidationError(
            source + " midpoint interval must have positive duration"
        )
    midpoint_x2 = start_ms + end_ms
    _require_exact_nonnegative_int(
        midpoint_x2,
        field_name=source + " midpoint_x2",
    )
    return midpoint_x2


@dataclass(frozen=True)
class AffineAnchorResidual:
    """Immutable midpoint/residual evidence for one selected anchor."""

    external_identity: HybridCueIdentity
    asr_identity: HybridCueIdentity
    external_midpoint_x2: int
    asr_midpoint_x2: int
    predicted_asr_midpoint_ms: float
    signed_residual_ms: float
    absolute_residual_ms: float
    is_inlier: bool

    def __post_init__(self):
        _validate_affine_identity(
            self.external_identity,
            expected_source=EVIDENCE_SOURCE_EXTERNAL_JA,
            field_name="residual external_identity",
        )
        _validate_affine_identity(
            self.asr_identity,
            expected_source=EVIDENCE_SOURCE_ASR_SEGMENT,
            field_name="residual asr_identity",
        )
        _require_exact_nonnegative_int(
            self.external_midpoint_x2,
            field_name="external_midpoint_x2",
        )
        _require_exact_nonnegative_int(
            self.asr_midpoint_x2,
            field_name="asr_midpoint_x2",
        )
        _fraction_to_finite_float(
            Fraction(self.external_midpoint_x2, 2),
            field_name="external midpoint",
        )
        _fraction_to_finite_float(
            Fraction(self.asr_midpoint_x2, 2),
            field_name="ASR midpoint",
        )
        _require_finite_float(
            self.predicted_asr_midpoint_ms,
            field_name="predicted_asr_midpoint_ms",
        )
        signed_residual_ms = _require_finite_float(
            self.signed_residual_ms,
            field_name="signed_residual_ms",
        )
        absolute_residual_ms = _require_finite_float(
            self.absolute_residual_ms,
            field_name="absolute_residual_ms",
        )
        if absolute_residual_ms < 0.0:
            raise AlignmentValidationError(
                "absolute_residual_ms must be nonnegative"
            )
        if absolute_residual_ms != abs(signed_residual_ms):
            raise AlignmentValidationError(
                "absolute_residual_ms must equal the signed residual magnitude"
            )
        if type(self.is_inlier) is not bool:
            raise AlignmentValidationError("is_inlier must be an exact bool")

    @property
    def external_midpoint_ms(self) -> float:
        """Return external midpoint evidence without changing source timing."""

        return _fraction_to_finite_float(
            Fraction(self.external_midpoint_x2, 2),
            field_name="external midpoint",
        )

    @property
    def asr_midpoint_ms(self) -> float:
        """Return ASR midpoint evidence without changing source timing."""

        return _fraction_to_finite_float(
            Fraction(self.asr_midpoint_x2, 2),
            field_name="ASR midpoint",
        )


@dataclass(frozen=True)
class RobustAffineAlignment:
    """Immutable analysis-only Theil-Sen midpoint alignment evidence."""

    scale: float
    intercept_ms: float
    anchor_count: int
    inlier_count: int
    residual_threshold_ms: int
    residuals: tuple[AffineAnchorResidual, ...]
    median_absolute_residual_ms: float

    def __post_init__(self):
        _require_finite_float(
            self.scale,
            field_name="scale",
            strictly_positive=True,
        )
        _require_finite_float(
            self.intercept_ms,
            field_name="intercept_ms",
        )
        anchor_count = _require_exact_nonnegative_int(
            self.anchor_count,
            field_name="anchor_count",
        )
        if not MIN_AFFINE_ANCHORS <= anchor_count <= MAX_AFFINE_ANCHORS:
            raise AlignmentValidationError(
                "anchor_count is outside the affine anchor bounds"
            )
        inlier_count = _require_exact_nonnegative_int(
            self.inlier_count,
            field_name="inlier_count",
        )
        if inlier_count > anchor_count:
            raise AlignmentValidationError(
                "inlier_count cannot exceed anchor_count"
            )
        residual_threshold_ms = _require_exact_positive_int(
            self.residual_threshold_ms,
            field_name="residual_threshold_ms",
        )
        if type(self.residuals) is not tuple:
            raise AlignmentValidationError(
                "residuals must be an immutable tuple"
            )
        if len(self.residuals) != anchor_count:
            raise AlignmentValidationError(
                "residual count must equal anchor_count"
            )
        _require_finite_float(
            self.median_absolute_residual_ms,
            field_name="median_absolute_residual_ms",
        )
        if self.median_absolute_residual_ms < 0.0:
            raise AlignmentValidationError(
                "median_absolute_residual_ms must be nonnegative"
            )

        seen_external = set()
        seen_asr = set()
        previous_external_index = None
        previous_asr_index = None
        absolute_residuals = []
        actual_inlier_count = 0
        canonical_scale = Fraction.from_float(self.scale)
        canonical_intercept = Fraction.from_float(self.intercept_ms)
        for position, residual in enumerate(self.residuals):
            if not isinstance(residual, AffineAnchorResidual):
                raise AlignmentValidationError(
                    "residuals must contain AffineAnchorResidual values"
                )

            external_identity = residual.external_identity
            asr_identity = residual.asr_identity
            if external_identity.cue_id in seen_external:
                raise AlignmentValidationError(
                    "residuals contain a duplicate external source identity"
                )
            if asr_identity.cue_id in seen_asr:
                raise AlignmentValidationError(
                    "residuals contain a duplicate ASR source identity"
                )
            if (
                previous_external_index is not None
                and external_identity.source_index <= previous_external_index
            ):
                raise AlignmentValidationError(
                    "residual external indexes must increase strictly"
                )
            if (
                previous_asr_index is not None
                and asr_identity.source_index <= previous_asr_index
            ):
                raise AlignmentValidationError(
                    "residual ASR indexes must increase strictly"
                )

            external_midpoint = Fraction(residual.external_midpoint_x2, 2)
            asr_midpoint = Fraction(residual.asr_midpoint_x2, 2)
            expected_predicted_fraction = (
                canonical_scale * external_midpoint
                + canonical_intercept
            )
            expected_signed_fraction = (
                asr_midpoint - expected_predicted_fraction
            )
            expected_absolute_fraction = abs(expected_signed_fraction)
            expected_predicted = _fraction_to_finite_float(
                expected_predicted_fraction,
                field_name="predicted_asr_midpoint_ms",
            )
            expected_signed = _fraction_to_finite_float(
                expected_signed_fraction,
                field_name="signed_residual_ms",
            )
            expected_absolute = _fraction_to_finite_float(
                expected_absolute_fraction,
                field_name="absolute_residual_ms",
            )
            if not all(
                math.isfinite(value)
                for value in (
                    expected_predicted,
                    expected_signed,
                    expected_absolute,
                )
            ):
                raise AlignmentValidationError(
                    "residual validation produced a nonfinite value"
                )
            if residual.predicted_asr_midpoint_ms != expected_predicted:
                raise AlignmentValidationError(
                    "residual predicted midpoint is detached from fit"
                )
            if (
                residual.signed_residual_ms != expected_signed
                or residual.absolute_residual_ms != expected_absolute
            ):
                raise AlignmentValidationError(
                    "residual values are detached from fit"
                )
            expected_inlier = (
                expected_absolute_fraction <= residual_threshold_ms
            )
            if residual.is_inlier != expected_inlier:
                raise AlignmentValidationError(
                    "residual inlier classification is detached from threshold"
                )

            seen_external.add(external_identity.cue_id)
            seen_asr.add(asr_identity.cue_id)
            previous_external_index = external_identity.source_index
            previous_asr_index = asr_identity.source_index
            absolute_residuals.append(expected_absolute_fraction)
            if residual.is_inlier:
                actual_inlier_count += 1

        if actual_inlier_count != inlier_count:
            raise AlignmentValidationError(
                "inlier_count does not match residual classifications"
            )
        median_absolute_residual = _median_fraction(absolute_residuals)
        median_absolute_residual_float = _fraction_to_finite_float(
            median_absolute_residual,
            field_name="median_absolute_residual_ms",
        )
        if self.median_absolute_residual_ms != median_absolute_residual_float:
            raise AlignmentValidationError(
                "median_absolute_residual_ms does not match residuals"
            )

    @property
    def anchor_residuals(self) -> tuple[AffineAnchorResidual, ...]:
        """Return the immutable residual evidence in selected-anchor order."""

        return self.residuals


def infer_robust_affine_alignment(
    anchors: tuple[MonotonicAnchorCandidate, ...],
    *,
    residual_threshold_ms: int,
) -> RobustAffineAlignment:
    """Infer midpoint evidence with a deterministic Theil-Sen-style fit.

    Pairwise slopes and per-anchor intercepts use exact ``Fraction`` values;
    only the immutable public analysis result is converted to finite floats.
    This function consumes selected lexical anchors and never projects or
    rewrites subtitle cue timestamps.
    """

    residual_threshold_ms = _require_exact_positive_int(
        residual_threshold_ms,
        field_name="residual_threshold_ms",
    )
    validated_anchors = _validate_affine_anchors(anchors)

    midpoint_pairs: list[tuple[int, int]] = []
    for anchor in validated_anchors:
        midpoint_pairs.append(
            (
                _midpoint_x2(
                    anchor.timing,
                    source=EVIDENCE_SOURCE_EXTERNAL_JA,
                ),
                _midpoint_x2(
                    anchor.timing,
                    source=EVIDENCE_SOURCE_ASR_SEGMENT,
                ),
            )
        )

    if len({external_x2 for external_x2, _ in midpoint_pairs}) < 2:
        raise AlignmentValidationError(
            "affine inference requires distinct external midpoint evidence"
        )

    pairwise_slopes: list[Fraction] = []
    for left_index, (left_external_x2, left_asr_x2) in enumerate(
        midpoint_pairs
    ):
        for right_external_x2, right_asr_x2 in midpoint_pairs[left_index + 1:]:
            external_delta_x2 = right_external_x2 - left_external_x2
            if external_delta_x2 == 0:
                continue
            asr_delta_x2 = right_asr_x2 - left_asr_x2
            pairwise_slopes.append(
                Fraction(asr_delta_x2, external_delta_x2)
            )

    if not pairwise_slopes:
        raise AlignmentValidationError(
            "affine inference has no valid pairwise slopes"
        )

    scale_fraction = _median_fraction(pairwise_slopes)
    if scale_fraction <= 0:
        raise AlignmentValidationError(
            "affine scale must be strictly positive"
        )

    intercepts = []
    for external_x2, asr_x2 in midpoint_pairs:
        intercepts.append(
            Fraction(asr_x2, 2)
            - scale_fraction * Fraction(external_x2, 2)
        )
    intercept_fraction = _median_fraction(intercepts)

    scale = _fraction_to_finite_float(scale_fraction, field_name="scale")
    _require_finite_float(scale, field_name="scale", strictly_positive=True)
    intercept_ms = _fraction_to_finite_float(
        intercept_fraction,
        field_name="intercept_ms",
    )

    # The float conversion above is the single exact-fit-to-public boundary.
    # Rehydrate those binary float values as exact Fractions and use that same
    # canonical line for residuals and validator checks.
    canonical_scale = Fraction.from_float(scale)
    canonical_intercept = Fraction.from_float(intercept_ms)
    residuals = []
    absolute_residuals: list[Fraction] = []
    inlier_count = 0
    for anchor, (external_x2, asr_x2) in zip(
        validated_anchors,
        midpoint_pairs,
    ):
        external_midpoint = Fraction(external_x2, 2)
        asr_midpoint = Fraction(asr_x2, 2)
        predicted_fraction = (
            canonical_scale * external_midpoint
            + canonical_intercept
        )
        signed_fraction = asr_midpoint - predicted_fraction
        absolute_fraction = abs(signed_fraction)
        predicted = _fraction_to_finite_float(
            predicted_fraction,
            field_name="predicted_asr_midpoint_ms",
        )
        signed = _fraction_to_finite_float(
            signed_fraction,
            field_name="signed_residual_ms",
        )
        absolute = _fraction_to_finite_float(
            absolute_fraction,
            field_name="absolute_residual_ms",
        )
        is_inlier = absolute_fraction <= residual_threshold_ms
        if is_inlier:
            inlier_count += 1
        absolute_residuals.append(absolute_fraction)
        residuals.append(
            AffineAnchorResidual(
                external_identity=anchor.external_identity,
                asr_identity=anchor.asr_identity,
                external_midpoint_x2=external_x2,
                asr_midpoint_x2=asr_x2,
                predicted_asr_midpoint_ms=predicted,
                signed_residual_ms=signed,
                absolute_residual_ms=absolute,
                is_inlier=is_inlier,
            )
        )

    median_absolute_residual_ms = _fraction_to_finite_float(
        _median_fraction(absolute_residuals),
        field_name="median_absolute_residual_ms",
    )
    return RobustAffineAlignment(
        scale=scale,
        intercept_ms=intercept_ms,
        anchor_count=len(validated_anchors),
        inlier_count=inlier_count,
        residual_threshold_ms=residual_threshold_ms,
        residuals=tuple(residuals),
        median_absolute_residual_ms=median_absolute_residual_ms,
    )


@dataclass(frozen=True)
class AffineConsensusAlignment:
    """One bounded affine-consistent monotonic candidate chain and its fit."""

    anchors: tuple[MonotonicAnchorCandidate, ...]
    alignment: RobustAffineAlignment

    def __post_init__(self):
        validated = _validate_affine_anchors(self.anchors)
        if not isinstance(self.alignment, RobustAffineAlignment):
            raise AlignmentValidationError(
                "alignment must be a RobustAffineAlignment"
            )
        if self.alignment.anchor_count != len(validated):
            raise AlignmentValidationError(
                "alignment anchor count does not match consensus anchors"
            )
        if tuple(
            (anchor.external_identity, anchor.asr_identity)
            for anchor in validated
        ) != tuple(
            (residual.external_identity, residual.asr_identity)
            for residual in self.alignment.residuals
        ):
            raise AlignmentValidationError(
                "alignment residual identities do not match consensus anchors"
            )


def _merge_chain_states(left, right, *, path_limit: int):
    """Merge Fenwick states as (length, endpoints, path_count)."""

    if left[0] > right[0]:
        return left
    if right[0] > left[0]:
        return right
    if left[0] == 0:
        return (0, (), 1)
    endpoints = tuple(sorted(set(left[1]).union(right[1])))
    path_count = min(path_limit + 1, left[2] + right[2])
    if len(endpoints) > path_limit + 1:
        endpoints = endpoints[:path_limit + 1]
    return (left[0], endpoints, path_count)


def _maximum_monotonic_consensus_paths(
    candidates: tuple[MonotonicAnchorCandidate, ...],
    *,
    work_counter: list[int],
) -> tuple[tuple[MonotonicAnchorCandidate, ...], ...]:
    """Return all maximum-cardinality strict chains, within a fixed path cap."""

    if not candidates:
        return ()
    ordered = tuple(sorted(candidates, key=_candidate_order_key))
    asr_ordinals = sorted({item.asr_segment_index for item in ordered})
    fenwick = [(0, (), 1) for _ in range(len(asr_ordinals) + 1)]
    chain_lengths: list[int] = [0] * len(ordered)
    chain_counts: list[int] = [0] * len(ordered)
    parents: list[tuple[int, ...]] = [()] * len(ordered)
    path_limit = MAX_AFFINE_CONSENSUS_CHAINS_PER_HYPOTHESIS

    def merge(left, right):
        work_counter[0] += 1 + len(left[1]) + len(right[1])
        if work_counter[0] > MAX_AFFINE_CONSENSUS_DP_OPERATIONS:
            raise AlignmentLimitError(
                "affine-consensus dynamic-program work exceeds its fixed bound"
            )
        return _merge_chain_states(
            left,
            right,
            path_limit=path_limit,
        )

    def query(exclusive_rank: int):
        result = (0, (), 1)
        position = exclusive_rank
        while position > 0:
            result = merge(result, fenwick[position])
            position -= position & -position
        return result

    def update(rank: int, endpoint: int):
        position = rank + 1
        state = (
            chain_lengths[endpoint],
            (endpoint,),
            chain_counts[endpoint],
        )
        while position < len(fenwick):
            fenwick[position] = merge(fenwick[position], state)
            position += position & -position

    start = 0
    while start < len(ordered):
        external_ordinal = ordered[start].external_cue_index
        end = start + 1
        while (
            end < len(ordered)
            and ordered[end].external_cue_index == external_ordinal
        ):
            end += 1

        # Query the whole external-ordinal group before updates so external
        # identities also increase strictly.
        for candidate_index in range(start, end):
            candidate = ordered[candidate_index]
            asr_rank = bisect_left(asr_ordinals, candidate.asr_segment_index)
            (
                previous_length,
                previous_endpoints,
                previous_count,
            ) = query(asr_rank)
            if previous_length == 0:
                chain_lengths[candidate_index] = 1
                chain_counts[candidate_index] = 1
                parents[candidate_index] = ()
            else:
                chain_lengths[candidate_index] = previous_length + 1
                chain_counts[candidate_index] = min(
                    path_limit + 1,
                    previous_count,
                )
                parents[candidate_index] = previous_endpoints

        for candidate_index in range(start, end):
            candidate = ordered[candidate_index]
            asr_rank = bisect_left(asr_ordinals, candidate.asr_segment_index)
            update(asr_rank, candidate_index)
        start = end

    best_length, best_endpoints, best_path_count = query(len(asr_ordinals))
    if best_length == 0:
        return ()
    if best_path_count > path_limit:
        raise AlignmentLimitError(
            "maximum affine-consensus chain ambiguity exceeds its bounded path limit"
        )

    paths: list[tuple[int, ...]] = []

    def append_paths(endpoint: int, suffix: tuple[int, ...]):
        if len(paths) > path_limit:
            return
        parent_endpoints = parents[endpoint]
        if not parent_endpoints:
            paths.append((endpoint,) + suffix)
            return
        for parent in parent_endpoints:
            append_paths(parent, (endpoint,) + suffix)
            if len(paths) > path_limit:
                return

    for endpoint in best_endpoints:
        append_paths(endpoint, ())
        if len(paths) > path_limit:
            break
    if len(paths) != best_path_count:
        raise AlignmentValidationError(
            "bounded monotonic path reconstruction detached from dynamic program"
        )
    return tuple(
        tuple(ordered[index] for index in path)
        for path in paths
    )


def iter_unique_affine_consensus_anchor_chains(
    candidates: tuple[MonotonicAnchorCandidate, ...],
    *,
    residual_threshold_ms: int,
    minimum_scale: float,
    maximum_scale: float,
) -> Iterator[tuple[MonotonicAnchorCandidate, ...]]:
    """Yield unique maximum consensus chains within the existing work bounds.

    Each hypothesis admits candidates whose exact midpoint residual is within
    ``residual_threshold_ms``. A Fenwick dynamic program then enumerates every
    maximum-cardinality strict monotonic chain up to a fixed ambiguity cap.
    Only compact source-ordinal identity keys persist across hypotheses.
    Fit pair work is charged before each unique chain is yielded. Consumers
    must exhaust the iterator before returning any selection; later work-limit
    failures invalidate earlier provisional results. No candidate is synthesized.
    """

    residual_threshold_ms = _require_exact_positive_int(
        residual_threshold_ms,
        field_name="residual_threshold_ms",
    )
    minimum_scale = _require_finite_float(
        minimum_scale,
        field_name="minimum_scale",
        strictly_positive=True,
    )
    maximum_scale = _require_finite_float(
        maximum_scale,
        field_name="maximum_scale",
        strictly_positive=True,
    )
    if minimum_scale > maximum_scale:
        raise AlignmentValidationError(
            "minimum_scale cannot exceed maximum_scale"
        )
    if type(candidates) is not tuple:
        raise AlignmentValidationError(
            "candidates must be an immutable tuple"
        )
    if len(candidates) > MAX_ANCHOR_CANDIDATES:
        raise AlignmentLimitError(
            "candidates exceeds MAX_ANCHOR_CANDIDATES"
        )

    seen_pairs = set()
    candidate_points = []
    for candidate in candidates:
        if not isinstance(candidate, MonotonicAnchorCandidate):
            raise AlignmentValidationError(
                "candidates must contain MonotonicAnchorCandidate values"
            )
        pair = (candidate.external_cue_index, candidate.asr_segment_index)
        if pair in seen_pairs:
            raise AlignmentValidationError(
                "duplicate external/ASR candidate pair is not allowed"
            )
        seen_pairs.add(pair)
        candidate_points.append(
            (
                candidate,
                _midpoint_x2(
                    candidate.timing,
                    source=EVIDENCE_SOURCE_EXTERNAL_JA,
                ),
                _midpoint_x2(
                    candidate.timing,
                    source=EVIDENCE_SOURCE_ASR_SEGMENT,
                ),
            )
        )

    if len(candidate_points) < 2:
        return

    minimum_scale_fraction = Fraction(str(minimum_scale))
    maximum_scale_fraction = Fraction(str(maximum_scale))
    hypotheses = set()
    ordered_points = sorted(
        candidate_points,
        key=lambda item: _candidate_order_key(item[0]),
    )
    pair_comparisons = len(ordered_points) * (len(ordered_points) - 1) // 2
    if pair_comparisons > MAX_AFFINE_CONSENSUS_PAIR_COMPARISONS:
        raise AlignmentLimitError(
            "affine-consensus pair count exceeds its fixed bound"
        )
    for left_index, (left, left_external_x2, left_asr_x2) in enumerate(
        ordered_points
    ):
        for right_index in range(left_index + 1, len(ordered_points)):
            (
                right,
                right_external_x2,
                right_asr_x2,
            ) = ordered_points[right_index]
            if left.external_cue_index >= right.external_cue_index:
                continue
            if left.asr_segment_index >= right.asr_segment_index:
                continue
            external_delta_x2 = right_external_x2 - left_external_x2
            if external_delta_x2 <= 0:
                continue
            scale = Fraction(
                right_asr_x2 - left_asr_x2,
                external_delta_x2,
            )
            if not minimum_scale_fraction <= scale <= maximum_scale_fraction:
                continue
            intercept = (
                Fraction(left_asr_x2, 2)
                - scale * Fraction(left_external_x2, 2)
            )
            hypotheses.add((scale, intercept))
            if len(hypotheses) > MAX_AFFINE_CONSENSUS_HYPOTHESES:
                raise AlignmentLimitError(
                    "affine-consensus hypothesis count exceeds its fixed bound"
                )

    if not hypotheses:
        return
    work = len(hypotheses) * len(candidate_points)
    if work > MAX_AFFINE_CONSENSUS_CANDIDATE_EVALUATIONS:
        raise AlignmentLimitError(
            "affine-consensus candidate evaluation exceeds its fixed work bound"
        )

    seen_chains: set[tuple[tuple[int, int], ...]] = set()
    fit_pair_evaluations = 0
    dynamic_program_work = [0]
    paths_evaluated = 0
    for scale, intercept in sorted(hypotheses):
        affine_candidates = []
        for candidate, external_x2, asr_x2 in ordered_points:
            residual = abs(
                Fraction(asr_x2, 2)
                - (scale * Fraction(external_x2, 2) + intercept)
            )
            if residual <= residual_threshold_ms:
                affine_candidates.append(candidate)
        paths = _maximum_monotonic_consensus_paths(
            tuple(affine_candidates),
            work_counter=dynamic_program_work,
        )
        paths_evaluated += len(paths)
        if paths_evaluated > MAX_AFFINE_CONSENSUS_PATHS_EVALUATED:
            raise AlignmentLimitError(
                "affine-consensus path evaluation exceeds its fixed bound"
            )
        for anchors in paths:
            if len(anchors) < MIN_AFFINE_ANCHORS:
                continue
            if len(anchors) > MAX_AFFINE_ANCHORS:
                raise AlignmentLimitError(
                    "affine-consensus chain exceeds MAX_AFFINE_ANCHORS"
                )
            identity_key = tuple(_candidate_order_key(anchor) for anchor in anchors)
            if identity_key in seen_chains:
                continue
            # Every key accounts for at least one already-counted path, so
            # this set can never exceed MAX_AFFINE_CONSENSUS_PATHS_EVALUATED.
            seen_chains.add(identity_key)
            fit_pair_evaluations += len(anchors) * (len(anchors) - 1) // 2
            if fit_pair_evaluations > MAX_AFFINE_CONSENSUS_FIT_PAIR_EVALUATIONS:
                raise AlignmentLimitError(
                    "affine-consensus fit work exceeds its fixed pairwise bound"
                )
            yield anchors


def infer_affine_consensus_alignments(
    candidates: tuple[MonotonicAnchorCandidate, ...],
    *,
    residual_threshold_ms: int,
    minimum_scale: float,
    maximum_scale: float,
) -> tuple[AffineConsensusAlignment, ...]:
    """Legacy tuple API with its original 2048 full-chain storage contract."""

    chains = []
    for anchors in iter_unique_affine_consensus_anchor_chains(
        candidates,
        residual_threshold_ms=residual_threshold_ms,
        minimum_scale=minimum_scale,
        maximum_scale=maximum_scale,
    ):
        chains.append(anchors)
        if len(chains) > MAX_AFFINE_CONSENSUS_UNIQUE_CHAINS:
            raise AlignmentLimitError(
                "unique affine-consensus chain count exceeds its fixed bound"
            )
    # Preserve the legacy tuple ordering by stable cue ID, independently of
    # hypothesis traversal and production selection ranking.
    chains.sort(key=lambda anchors: tuple(
        (anchor.external_identity.cue_id, anchor.asr_identity.cue_id)
        for anchor in anchors
    ))
    return tuple(
        AffineConsensusAlignment(
            anchors=anchors,
            alignment=infer_robust_affine_alignment(
                anchors, residual_threshold_ms=residual_threshold_ms,
            ),
        )
        for anchors in chains
    )


__all__ = [
    "AffineConsensusAlignment",
    "AlignmentAmbiguityError",
    "AlignmentError",
    "AlignmentLimitError",
    "AlignmentValidationError",
    "AnchorTimingEvidence",
    "DEFAULT_MINIMUM_LEXICAL_SCORE",
    "AffineAnchorResidual",
    "JapaneseAnchorCandidate",
    "JapaneseComparisonEvidence",
    "MAX_ANCHOR_CANDIDATES",
    "MAX_ALIGNMENT_TEXT_CHARS",
    "MAX_AFFINE_CONSENSUS_SCALE",
    "MAX_AFFINE_ANCHORS",
    "MAX_AFFINE_CONSENSUS_CANDIDATE_EVALUATIONS",
    "MAX_AFFINE_CONSENSUS_CHAINS_PER_HYPOTHESIS",
    "MAX_AFFINE_CONSENSUS_DP_OPERATIONS",
    "MAX_AFFINE_CONSENSUS_FIT_PAIR_EVALUATIONS",
    "MAX_AFFINE_CONSENSUS_HYPOTHESES",
    "MAX_AFFINE_CONSENSUS_PAIR_COMPARISONS",
    "MAX_AFFINE_CONSENSUS_PATHS_EVALUATED",
    "MAX_AFFINE_CONSENSUS_UNIQUE_CHAINS",
    "MIN_AFFINE_CONSENSUS_SCALE",
    "MAX_LEXICAL_PAIR_COMPARISONS",
    "MIN_AFFINE_ANCHORS",
    "MonotonicAnchorCandidate",
    "NormalizedComparisonEvidence",
    "generate_anchor_candidates",
    "generate_monotonic_anchor_candidates",
    "RobustAffineAlignment",
    "infer_robust_affine_alignment",
    "infer_affine_consensus_alignments",
    "iter_unique_affine_consensus_anchor_chains",
    "japanese_lexical_similarity",
    "normalize_japanese_for_matching",
    "select_monotonic_anchors",
    "select_monotonic_anchor_candidates",
]
