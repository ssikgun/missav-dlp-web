"""Deterministic Stage11 Slice 1 subtitle inventory and source selection.

This module deliberately operates only on already-inventoried metadata.  It
does not read files, parse subtitle bytes, inspect a filesystem, or contact an
external service.  SRT/VTT content validation belongs to a later bounded-read
slice.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
import unicodedata

from teddy_discovery_ids import parse_dvd_id
from teddy_discovery_organizer import (
    VIDEO_EXTENSIONS,
    canonical_destination,
)
from teddy_discovery_ownership import is_canonical_present_holding


ACTION_SKIP_EXISTING_KO = "SKIP_EXISTING_KO"
ACTION_TEXT_SOURCE_READY = "TEXT_SOURCE_READY"
ACTION_ASR_REQUIRED = "ASR_REQUIRED"

SOURCE_KIND_SIBLING_TEXT = "existing_sibling_text"
SOURCE_KIND_VALIDATED_EXTERNAL_TEXT = "validated_exact_external_text"

SUPPORTED_LANGUAGES = frozenset({"ko", "ja", "en"})
SUPPORTED_TEXT_FORMATS = frozenset({"srt", "vtt"})

_LANGUAGE_ALIASES = {
    "ko": "ko",
    "kor": "ko",
    "korean": "ko",
    "ja": "ja",
    "jpn": "ja",
    "japanese": "ja",
    "en": "en",
    "eng": "en",
    "english": "en",
}


class SubtitleDiscoveryError(ValueError):
    """Base class for deterministic subtitle inventory/selection failures."""


class CanonicalHoldingValidationError(SubtitleDiscoveryError):
    """Raised when a holding is not an exact canonical present video."""


class SubtitleCandidateValidationError(SubtitleDiscoveryError):
    """Raised when a sibling candidate is unsafe or internally inconsistent."""


class AmbiguousSubtitleSourceError(SubtitleDiscoveryError):
    """Raised when equal-priority distinct sources cannot be selected safely."""


def _has_control_characters(value: str) -> bool:
    return any(
        ord(character) < 32
        or ord(character) == 127
        or unicodedata.category(character) == "Cc"
        for character in value
    )


def normalize_language(language: object) -> str | None:
    """Normalize only the small, explicit Stage11 language map.

    Unknown values are preserved in normalized form and are never routable.
    No language is inferred from dialogue content.
    """

    if language is None:
        return None

    if not isinstance(language, str):
        raise SubtitleCandidateValidationError(
            "language must be a string or None"
        )

    value = language.strip().lower()

    if not value:
        return None

    if _has_control_characters(value):
        raise SubtitleCandidateValidationError(
            "language contains a control character"
        )

    return _LANGUAGE_ALIASES.get(value, value)


def _normalize_text_format(text_format: object) -> str:
    if not isinstance(text_format, str):
        raise SubtitleCandidateValidationError(
            "text format must be a string"
        )

    value = text_format.strip().lower()

    if value.startswith("."):
        value = value[1:]

    if value not in SUPPORTED_TEXT_FORMATS:
        raise SubtitleCandidateValidationError(
            "unsupported subtitle text format: " + repr(text_format)
        )

    return value


def _safe_relative_posix_path(
    value: object,
    *,
    field_name: str,
) -> PurePosixPath:
    if not isinstance(value, str):
        raise SubtitleDiscoveryError(
            field_name + " must be a POSIX path string"
        )

    if not value:
        raise SubtitleDiscoveryError(
            field_name + " must not be empty"
        )

    if value.startswith("/"):
        raise SubtitleDiscoveryError(
            field_name + " must be relative"
        )

    if "\\" in value:
        raise SubtitleDiscoveryError(
            field_name + " must not contain backslashes"
        )

    if "\x00" in value or _has_control_characters(value):
        raise SubtitleDiscoveryError(
            field_name + " must not contain control characters"
        )

    components = value.split("/")

    if any(
        not component
        or component in {".", ".."}
        or component.startswith(".")
        for component in components
    ):
        raise SubtitleDiscoveryError(
            field_name + " contains an unsafe path component"
        )

    path = PurePosixPath(value)

    if path.is_absolute() or path.as_posix() != value:
        raise SubtitleDiscoveryError(
            field_name + " is not a normalized relative POSIX path"
        )

    return path


def _format_from_path(
    path: PurePosixPath,
    *,
    field_name: str,
) -> str:
    suffix = path.suffix.lower()

    if suffix not in {".srt", ".vtt"}:
        raise SubtitleCandidateValidationError(
            field_name + " has an unsupported subtitle suffix"
        )

    return suffix[1:]


def _infer_filename_language(
    path: PurePosixPath,
) -> str | None:
    text_format = _format_from_path(
        path,
        field_name="sibling candidate relative_path",
    )
    stem = path.name[: -(len(text_format) + 1)]
    parts = stem.split(".")

    if len(parts) != 2 or not parts[1]:
        return None

    return normalize_language(parts[1])


@dataclass(frozen=True)
class CanonicalVideoHolding:
    """The validated identity needed by Slice 1."""

    dvd_id: str
    relative_path: str
    video_format: str


def validate_canonical_holding(
    holding: Mapping[str, object],
    expected_dvd_id: str,
) -> CanonicalVideoHolding:
    """Validate one exact canonical present holding and return its identity.

    The holding's stored ``dvd_id`` and the caller's expected DVD-ID must both
    exactly equal the canonical ID parsed from the canonical video filename.
    Malformed identity is never repaired or normalized here.
    """

    if not isinstance(holding, Mapping):
        raise CanonicalHoldingValidationError(
            "holding must be a mapping"
        )

    if not isinstance(expected_dvd_id, str) or not expected_dvd_id:
        raise CanonicalHoldingValidationError(
            "expected_dvd_id must be a non-empty string"
        )

    try:
        canonical_present = is_canonical_present_holding(holding)
    except (TypeError, ValueError, OverflowError):
        canonical_present = False

    if not canonical_present:
        raise CanonicalHoldingValidationError(
            "holding is not a canonical present jav MATCHED holding"
        )

    if holding.get("storage_root") != "jav":
        raise CanonicalHoldingValidationError(
            "holding storage_root must be 'jav'"
        )

    if holding.get("parse_status") != "MATCHED":
        raise CanonicalHoldingValidationError(
            "holding parse_status must be 'MATCHED'"
        )

    relative_path_value = holding.get("relative_path")

    try:
        relative_path = _safe_relative_posix_path(
            relative_path_value,
            field_name="holding relative_path",
        )
    except SubtitleDiscoveryError as error:
        raise CanonicalHoldingValidationError(str(error)) from error

    video_format = relative_path.suffix.lower()

    if video_format not in VIDEO_EXTENSIONS:
        raise CanonicalHoldingValidationError(
            "holding relative_path is not a supported video path"
        )

    parsed = parse_dvd_id(relative_path.name)

    if parsed is None:
        raise CanonicalHoldingValidationError(
            "holding video filename has no canonical DVD-ID"
        )

    if holding.get("dvd_id") != parsed.dvd_id:
        raise CanonicalHoldingValidationError(
            "holding dvd_id does not exactly match parsed DVD-ID"
        )

    if expected_dvd_id != parsed.dvd_id:
        raise CanonicalHoldingValidationError(
            "expected_dvd_id does not exactly match parsed DVD-ID"
        )

    try:
        canonical_path = canonical_destination(
            parsed.dvd_id,
            video_format,
        ).as_posix()
    except (TypeError, ValueError) as error:
        raise CanonicalHoldingValidationError(
            "canonical destination could not be derived"
        ) from error

    if relative_path_value != canonical_path:
        raise CanonicalHoldingValidationError(
            "holding relative_path is not the canonical video location"
        )

    return CanonicalVideoHolding(
        dvd_id=parsed.dvd_id,
        relative_path=relative_path_value,
        video_format=video_format[1:],
    )


def derive_target_ko_relative(
    canonical_video: CanonicalVideoHolding,
) -> str:
    """Derive the only Korean output target from validated video identity."""

    if not isinstance(canonical_video, CanonicalVideoHolding):
        raise CanonicalHoldingValidationError(
            "canonical_video must be a validated CanonicalVideoHolding"
        )

    return canonical_destination(
        canonical_video.dvd_id,
        ".ko.srt",
    ).as_posix()


@dataclass(frozen=True)
class SubtitleCandidate:
    """Immutable metadata for one already-inventoried text source.

    Sibling candidates use ``relative_path``.  External candidates use the
    separate opaque ``external_source_id`` and never use a NAS-like path.
    ``validated_for_dvd_id`` is the exact external-validation contract: a
    non-None value must exactly match the canonical video ID before selection.
    A None value is intentionally ignored by the selector.
    """

    source_kind: str
    language: str | None
    text_format: str
    relative_path: str | None = None
    external_source_id: str | None = None
    validated_for_dvd_id: str | None = None

    def __post_init__(self):
        if self.source_kind not in {
            SOURCE_KIND_SIBLING_TEXT,
            SOURCE_KIND_VALIDATED_EXTERNAL_TEXT,
        }:
            raise SubtitleCandidateValidationError(
                "unsupported subtitle candidate kind"
            )

        normalized_language = normalize_language(self.language)
        normalized_format = _normalize_text_format(self.text_format)

        object.__setattr__(self, "language", normalized_language)
        object.__setattr__(self, "text_format", normalized_format)

        if self.source_kind == SOURCE_KIND_SIBLING_TEXT:
            try:
                sibling_path = _safe_relative_posix_path(
                    self.relative_path,
                    field_name="sibling candidate relative_path",
                )
            except SubtitleDiscoveryError as error:
                raise SubtitleCandidateValidationError(
                    str(error)
                ) from error

            path_format = _format_from_path(
                sibling_path,
                field_name="sibling candidate relative_path",
            )

            if normalized_format != path_format:
                raise SubtitleCandidateValidationError(
                    "sibling candidate text_format does not match suffix"
                )

            inferred_language = _infer_filename_language(sibling_path)

            if (
                inferred_language is not None
                and normalized_language is not None
                and inferred_language != normalized_language
            ):
                raise SubtitleCandidateValidationError(
                    "sibling filename language conflicts with metadata"
                )

            if normalized_language is None:
                object.__setattr__(
                    self,
                    "language",
                    inferred_language,
                )

            if self.external_source_id is not None:
                raise SubtitleCandidateValidationError(
                    "sibling candidate must not have an external identity"
                )

            if self.validated_for_dvd_id is not None:
                raise SubtitleCandidateValidationError(
                    "sibling candidate must not have external validation"
                )

            return

        if self.relative_path is not None:
            raise SubtitleCandidateValidationError(
                "external candidate must not have a relative_path"
            )

        if not isinstance(self.external_source_id, str):
            raise SubtitleCandidateValidationError(
                "external candidate requires an external_source_id"
            )

        if (
            not self.external_source_id
            or _has_control_characters(self.external_source_id)
        ):
            raise SubtitleCandidateValidationError(
                "external_source_id must be a non-empty logical identifier"
            )

        if self.validated_for_dvd_id is not None:
            if not isinstance(self.validated_for_dvd_id, str):
                raise SubtitleCandidateValidationError(
                    "validated_for_dvd_id must be a string or None"
                )

            if (
                not self.validated_for_dvd_id
                or _has_control_characters(self.validated_for_dvd_id)
            ):
                raise SubtitleCandidateValidationError(
                    "validated_for_dvd_id must be a non-empty safe ID"
                )

    @classmethod
    def sibling_text(
        cls,
        relative_path: str,
        language: object = None,
    ) -> "SubtitleCandidate":
        """Create an inventoried sibling sidecar candidate.

        The path is checked for safe POSIX syntax and .srt/.vtt format here;
        its exact DVD-ID directory is checked against the canonical holding
        during selection.
        """

        try:
            path = _safe_relative_posix_path(
                relative_path,
                field_name="sibling candidate relative_path",
            )
        except SubtitleDiscoveryError as error:
            raise SubtitleCandidateValidationError(str(error)) from error

        text_format = _format_from_path(
            path,
            field_name="sibling candidate relative_path",
        )

        return cls(
            source_kind=SOURCE_KIND_SIBLING_TEXT,
            language=normalize_language(language),
            text_format=text_format,
            relative_path=relative_path,
        )

    @classmethod
    def external_text(
        cls,
        external_source_id: str,
        *,
        language: object,
        text_format: str,
        validated_for_dvd_id: str | None = None,
    ) -> "SubtitleCandidate":
        """Create an external candidate, possibly not yet validated.

        The selector ignores candidates without exact validation for the
        current DVD-ID.  Use ``validated_external_text`` for a usable source.
        """

        return cls(
            source_kind=SOURCE_KIND_VALIDATED_EXTERNAL_TEXT,
            language=normalize_language(language),
            text_format=text_format,
            external_source_id=external_source_id,
            validated_for_dvd_id=validated_for_dvd_id,
        )

    @classmethod
    def validated_external_text(
        cls,
        external_source_id: str,
        *,
        dvd_id: str,
        language: object,
        text_format: str,
    ) -> "SubtitleCandidate":
        """Create an external candidate with exact per-DVD validation."""

        return cls.external_text(
            external_source_id,
            language=language,
            text_format=text_format,
            validated_for_dvd_id=dvd_id,
        )


@dataclass(frozen=True)
class SubtitleSelectionResult:
    """Small immutable result for the frozen Slice 1 routing policy."""

    action: str
    dvd_id: str
    canonical_video_relative: str
    target_ko_relative: str
    selected_source: SubtitleCandidate | None
    selected_language: str | None


def _validate_sibling_candidate(
    candidate: SubtitleCandidate,
    canonical_video: CanonicalVideoHolding,
) -> None:
    try:
        path = _safe_relative_posix_path(
            candidate.relative_path,
            field_name="sibling candidate relative_path",
        )
    except SubtitleDiscoveryError as error:
        raise SubtitleCandidateValidationError(str(error)) from error

    video_path = PurePosixPath(canonical_video.relative_path)

    if path.parent != video_path.parent:
        raise SubtitleCandidateValidationError(
            "sibling candidate is not in the canonical DVD-ID directory"
        )

    path_format = _format_from_path(
        path,
        field_name="sibling candidate relative_path",
    )

    if candidate.text_format != path_format:
        raise SubtitleCandidateValidationError(
            "sibling candidate text_format does not match suffix"
        )

    parsed = parse_dvd_id(path.name)

    if parsed is None or parsed.dvd_id != canonical_video.dvd_id:
        raise SubtitleCandidateValidationError(
            "sibling candidate does not have the canonical DVD-ID"
        )

    stem = path.name[: -(len(path_format) + 1)]
    parts = stem.split(".")

    if parts[0] != canonical_video.dvd_id or len(parts) not in {1, 2}:
        raise SubtitleCandidateValidationError(
            "sibling candidate filename is not a canonical sidecar name"
        )

    if len(parts) == 2:
        token = parts[1]

        if not token or _has_control_characters(token):
            raise SubtitleCandidateValidationError(
                "sibling candidate language token is malformed"
            )

        filename_language = normalize_language(token)

        if (
            candidate.language is not None
            and candidate.language != filename_language
        ):
            raise SubtitleCandidateValidationError(
                "sibling filename language conflicts with metadata"
            )


def _candidate_identity(candidate: SubtitleCandidate) -> tuple[object, ...]:
    return (
        candidate.source_kind,
        candidate.relative_path,
        candidate.external_source_id,
        candidate.language,
        candidate.text_format,
        candidate.validated_for_dvd_id,
    )


def _choose_unique(
    candidates: Iterable[SubtitleCandidate],
    *,
    language: str,
) -> SubtitleCandidate:
    unique: dict[tuple[object, ...], SubtitleCandidate] = {}

    for candidate in candidates:
        unique[_candidate_identity(candidate)] = candidate

    if len(unique) != 1:
        raise AmbiguousSubtitleSourceError(
            "multiple distinct "
            + language
            + " subtitle sources have equal priority"
        )

    return next(iter(unique.values()))


def select_subtitle_source(
    holding: Mapping[str, object],
    expected_dvd_id: str,
    candidates: Iterable[SubtitleCandidate] = (),
) -> SubtitleSelectionResult:
    """Apply the frozen KO, JA, EN, ASR source-selection policy.

    ``SKIP_EXISTING_KO`` means only that a structurally valid canonical Korean
    sidecar at the derived ``.ko.srt`` target was inventoried.  No subtitle
    bytes are read or parsed in this slice.
    """

    canonical_video = validate_canonical_holding(
        holding,
        expected_dvd_id,
    )
    target_ko_relative = derive_target_ko_relative(canonical_video)

    if candidates is None:
        raise SubtitleCandidateValidationError(
            "candidates must be an iterable, not None"
        )

    sibling_candidates: list[SubtitleCandidate] = []
    external_candidates: list[SubtitleCandidate] = []

    for candidate in candidates:
        if not isinstance(candidate, SubtitleCandidate):
            raise SubtitleCandidateValidationError(
                "candidates must contain SubtitleCandidate values"
            )

        if candidate.source_kind == SOURCE_KIND_SIBLING_TEXT:
            _validate_sibling_candidate(
                candidate,
                canonical_video,
            )
            sibling_candidates.append(candidate)
            continue

        if candidate.source_kind == SOURCE_KIND_VALIDATED_EXTERNAL_TEXT:
            if candidate.validated_for_dvd_id != canonical_video.dvd_id:
                continue

            external_candidates.append(candidate)
            continue

        raise SubtitleCandidateValidationError(
            "unsupported subtitle candidate kind"
        )

    ko_candidates = [
        candidate
        for candidate in sibling_candidates
        if (
            candidate.relative_path == target_ko_relative
            and candidate.language == "ko"
            and candidate.text_format == "srt"
        )
    ]

    if ko_candidates:
        selected = _choose_unique(
            ko_candidates,
            language="ko",
        )
        return SubtitleSelectionResult(
            action=ACTION_SKIP_EXISTING_KO,
            dvd_id=canonical_video.dvd_id,
            canonical_video_relative=canonical_video.relative_path,
            target_ko_relative=target_ko_relative,
            selected_source=selected,
            selected_language="ko",
        )

    usable_ja = [
        candidate
        for candidate in (*sibling_candidates, *external_candidates)
        if candidate.language == "ja"
    ]

    if usable_ja:
        selected = _choose_unique(
            usable_ja,
            language="ja",
        )
        return SubtitleSelectionResult(
            action=ACTION_TEXT_SOURCE_READY,
            dvd_id=canonical_video.dvd_id,
            canonical_video_relative=canonical_video.relative_path,
            target_ko_relative=target_ko_relative,
            selected_source=selected,
            selected_language="ja",
        )

    usable_en = [
        candidate
        for candidate in (*sibling_candidates, *external_candidates)
        if candidate.language == "en"
    ]

    if usable_en:
        selected = _choose_unique(
            usable_en,
            language="en",
        )
        return SubtitleSelectionResult(
            action=ACTION_TEXT_SOURCE_READY,
            dvd_id=canonical_video.dvd_id,
            canonical_video_relative=canonical_video.relative_path,
            target_ko_relative=target_ko_relative,
            selected_source=selected,
            selected_language="en",
        )

    return SubtitleSelectionResult(
        action=ACTION_ASR_REQUIRED,
        dvd_id=canonical_video.dvd_id,
        canonical_video_relative=canonical_video.relative_path,
        target_ko_relative=target_ko_relative,
        selected_source=None,
        selected_language=None,
    )


def inventory_subtitle_sources(
    holding: Mapping[str, object],
    expected_dvd_id: str,
    candidates: Iterable[SubtitleCandidate] = (),
) -> SubtitleSelectionResult:
    """Descriptive alias for the Slice 1 inventory/selection entry point."""

    return select_subtitle_source(
        holding,
        expected_dvd_id,
        candidates,
    )


__all__ = [
    "ACTION_ASR_REQUIRED",
    "ACTION_SKIP_EXISTING_KO",
    "ACTION_TEXT_SOURCE_READY",
    "AmbiguousSubtitleSourceError",
    "CanonicalHoldingValidationError",
    "CanonicalVideoHolding",
    "SOURCE_KIND_SIBLING_TEXT",
    "SOURCE_KIND_VALIDATED_EXTERNAL_TEXT",
    "SUPPORTED_LANGUAGES",
    "SUPPORTED_TEXT_FORMATS",
    "SubtitleCandidate",
    "SubtitleCandidateValidationError",
    "SubtitleDiscoveryError",
    "SubtitleSelectionResult",
    "derive_target_ko_relative",
    "inventory_subtitle_sources",
    "normalize_language",
    "select_subtitle_source",
    "validate_canonical_holding",
]
