"""Immutable Stage11 v2 hybrid-evidence contract.

This module is deliberately a data and validation boundary only.  It keeps
validated external Japanese subtitle bytes/documents and an existing ASR
result together without selecting a subtitle source, performing alignment,
calling a model, or doing filesystem/network/database I/O.

The source objects remain owned by their existing contracts:

* :class:`ExternalSubtitlePayload` owns external bytes and candidate identity.
* :class:`SubtitleDocument` and :class:`SubtitleCue` own parsed subtitle
  structure and deterministic source timestamps.
* :class:`ASRResult`, :class:`ASRSegment`, and :class:`ASRWord` own Whisper
  output and source timestamps.

Only references are stored for neighboring context.  Context references never
copy dialogue text, and no field in this contract gives an LLM ownership of
timestamps.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from typing import Final

from teddy_discovery_asr import (
    ASRResult,
    ASRSourceSnapshot,
    MAX_ASR_SEGMENTS,
)
from teddy_discovery_subtitle import (
    SOURCE_KIND_VALIDATED_EXTERNAL_TEXT,
    SubtitleCandidate,
)
from teddy_discovery_subtitle_external import ExternalSubtitlePayload
from teddy_discovery_subtitle_text import (
    MAX_SUBTITLE_BYTES,
    MAX_SUBTITLE_CUES,
    SubtitleDocument,
)


# These names describe stored evidence state, not an alignment result.  The
# first state is what a later deterministic alignment step may consume; this
# checkpoint does not calculate it.
ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID: Final = "EXTERNAL_ASR_HYBRID"
ALIGNMENT_PROVENANCE_ASR_ONLY: Final = "ASR_ONLY"
ALIGNMENT_PROVENANCE_UNRESOLVED: Final = "UNRESOLVED"
ALIGNMENT_PROVENANCES: Final = frozenset(
    {
        ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID,
        ALIGNMENT_PROVENANCE_ASR_ONLY,
        ALIGNMENT_PROVENANCE_UNRESOLVED,
    }
)

EVIDENCE_SOURCE_EXTERNAL_JA: Final = "external_ja"
EVIDENCE_SOURCE_ASR_SEGMENT: Final = "asr_segment"

NEIGHBOR_SOURCE_EXTERNAL_JA: Final = EVIDENCE_SOURCE_EXTERNAL_JA
NEIGHBOR_SOURCE_ASR_SEGMENT: Final = EVIDENCE_SOURCE_ASR_SEGMENT
NEIGHBOR_SOURCE_ASR_WORD: Final = "asr_word"
NEIGHBOR_SOURCE_EXTERNAL_EN: Final = "external_en"

MAX_HYBRID_CUE_EVIDENCE: Final = min(MAX_SUBTITLE_CUES, MAX_ASR_SEGMENTS)
MAX_NEIGHBOR_REFERENCES_PER_SIDE: Final = 4
MAX_PROVENANCE_METHOD_CHARS: Final = 128

_CUE_SOURCE_PREFIXES = {
    EVIDENCE_SOURCE_EXTERNAL_JA: "ja",
    EVIDENCE_SOURCE_ASR_SEGMENT: "asr",
}
_NEIGHBOR_SOURCE_ORDER = {
    NEIGHBOR_SOURCE_EXTERNAL_JA: 0,
    NEIGHBOR_SOURCE_ASR_SEGMENT: 1,
    NEIGHBOR_SOURCE_ASR_WORD: 2,
    NEIGHBOR_SOURCE_EXTERNAL_EN: 3,
}
_NEIGHBOR_SOURCE_PREFIXES = {
    NEIGHBOR_SOURCE_EXTERNAL_JA: "ja",
    NEIGHBOR_SOURCE_ASR_SEGMENT: "asr-segment",
    NEIGHBOR_SOURCE_ASR_WORD: "asr-word",
    NEIGHBOR_SOURCE_EXTERNAL_EN: "en",
}


class HybridEvidenceError(ValueError):
    """Base class for deterministic hybrid-evidence failures."""


class HybridEvidenceValidationError(HybridEvidenceError):
    """Raised when an immutable hybrid-evidence value is unsafe or detached."""


class HybridEvidenceLimitError(HybridEvidenceValidationError):
    """Raised when a bounded context or evidence collection is too large."""


def _require_exact_nonnegative_int(value: object, *, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise HybridEvidenceValidationError(
            field_name + " must be an exact nonnegative integer"
        )
    return value


def _require_safe_token(
    value: object,
    *,
    field_name: str,
    max_length: int,
) -> str:
    if type(value) is not str:
        raise HybridEvidenceValidationError(field_name + " must be a string")

    if not value or value != value.strip():
        raise HybridEvidenceValidationError(
            field_name + " must be nonempty and trimmed"
        )

    if len(value) > max_length:
        raise HybridEvidenceLimitError(
            field_name + " exceeds its bounded length"
        )

    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise HybridEvidenceValidationError(
            field_name + " contains a control character"
        )

    return value


def _validate_dvd_id(value: object) -> str:
    return _require_safe_token(
        value,
        field_name="dvd_id",
        max_length=256,
    )


def _validate_context_tuple(
    value: object,
    *,
    field_name: str,
) -> tuple["HybridNeighborReference", ...]:
    if type(value) is not tuple:
        raise HybridEvidenceValidationError(
            field_name + " must be an immutable tuple"
        )

    if len(value) > MAX_NEIGHBOR_REFERENCES_PER_SIDE:
        raise HybridEvidenceLimitError(
            field_name + " exceeds MAX_NEIGHBOR_REFERENCES_PER_SIDE"
        )

    for reference in value:
        if not isinstance(reference, HybridNeighborReference):
            raise HybridEvidenceValidationError(
                field_name + " must contain HybridNeighborReference values"
            )

    previous_key = None
    seen = set()
    for reference in value:
        key = reference.sort_key
        if previous_key is not None and key < previous_key:
            raise HybridEvidenceValidationError(
                field_name + " must use deterministic reference ordering"
            )
        previous_key = key

        if reference in seen:
            raise HybridEvidenceValidationError(
                field_name + " must not contain duplicate references"
            )
        seen.add(reference)

    return value


def stable_cue_id(source: str, source_index: int) -> str:
    """Return the title-independent ID for one source ordinal.

    The ID is based only on the bounded source kind and zero-based source
    ordinal.  Dialogue text, title text, URLs, and timestamps are not inputs.
    """

    if type(source) is not str or source not in _CUE_SOURCE_PREFIXES:
        raise HybridEvidenceValidationError(
            "cue identity source is unsupported"
        )

    source_index = _require_exact_nonnegative_int(
        source_index,
        field_name="cue identity source_index",
    )

    if source_index >= MAX_HYBRID_CUE_EVIDENCE:
        raise HybridEvidenceLimitError(
            "cue identity source_index exceeds the bounded evidence limit"
        )

    return f"{_CUE_SOURCE_PREFIXES[source]}-{source_index + 1:06d}"


@dataclass(frozen=True)
class HybridCueIdentity:
    """A deterministic cue identity owned by source kind and ordinal only."""

    cue_id: str
    source: str
    source_index: int

    def __post_init__(self):
        if type(self.source) is not str or self.source not in _CUE_SOURCE_PREFIXES:
            raise HybridEvidenceValidationError(
                "cue identity source is unsupported"
            )

        _require_exact_nonnegative_int(
            self.source_index,
            field_name="cue identity source_index",
        )

        expected_cue_id = stable_cue_id(self.source, self.source_index)
        if type(self.cue_id) is not str or self.cue_id != expected_cue_id:
            raise HybridEvidenceValidationError(
                "cue_id is not the deterministic identity for its source"
            )

    @classmethod
    def for_external_ja(cls, source_index: int) -> "HybridCueIdentity":
        return cls(
            cue_id=stable_cue_id(EVIDENCE_SOURCE_EXTERNAL_JA, source_index),
            source=EVIDENCE_SOURCE_EXTERNAL_JA,
            source_index=source_index,
        )

    @classmethod
    def for_asr_segment(cls, source_index: int) -> "HybridCueIdentity":
        return cls(
            cue_id=stable_cue_id(EVIDENCE_SOURCE_ASR_SEGMENT, source_index),
            source=EVIDENCE_SOURCE_ASR_SEGMENT,
            source_index=source_index,
        )


@dataclass(frozen=True)
class HybridNeighborReference:
    """A bounded reference to existing source evidence, never copied text."""

    source: str
    index: int
    subindex: int | None = None

    def __post_init__(self):
        if type(self.source) is not str or self.source not in _NEIGHBOR_SOURCE_ORDER:
            raise HybridEvidenceValidationError(
                "neighbor reference source is unsupported"
            )

        _require_exact_nonnegative_int(
            self.index,
            field_name="neighbor reference index",
        )

        if self.source == NEIGHBOR_SOURCE_ASR_WORD:
            _require_exact_nonnegative_int(
                self.subindex,
                field_name="ASR word reference subindex",
            )
        elif self.subindex is not None:
            raise HybridEvidenceValidationError(
                "subindex is only valid for ASR word references"
            )

    @property
    def reference_id(self) -> str:
        """Return a deterministic ID without dialogue or title material."""

        prefix = _NEIGHBOR_SOURCE_PREFIXES[self.source]
        if self.source == NEIGHBOR_SOURCE_ASR_WORD:
            return f"{prefix}-{self.index + 1:06d}-{self.subindex + 1:04d}"
        return f"{prefix}-{self.index + 1:06d}"

    @property
    def sort_key(self) -> tuple[int, int, int]:
        return (
            _NEIGHBOR_SOURCE_ORDER[self.source],
            self.index,
            -1 if self.subindex is None else self.subindex,
        )


@dataclass(frozen=True)
class HybridCueEvidence:
    """One cue identity plus bounded references for future deterministic work."""

    identity: HybridCueIdentity
    before_context: tuple[HybridNeighborReference, ...] = ()
    after_context: tuple[HybridNeighborReference, ...] = ()

    def __post_init__(self):
        if not isinstance(self.identity, HybridCueIdentity):
            raise HybridEvidenceValidationError(
                "cue evidence identity must be a HybridCueIdentity"
            )

        _validate_context_tuple(
            self.before_context,
            field_name="before_context",
        )
        _validate_context_tuple(
            self.after_context,
            field_name="after_context",
        )

        if set(self.before_context).intersection(self.after_context):
            raise HybridEvidenceValidationError(
                "before_context and after_context must not overlap"
            )

    @property
    def cue_id(self) -> str:
        return self.identity.cue_id

    @property
    def source(self) -> str:
        return self.identity.source

    @property
    def source_index(self) -> int:
        return self.identity.source_index


@dataclass(frozen=True)
class HybridAlignmentProvenance:
    """Immutable later-alignment state; no alignment is calculated here."""

    provenance: str
    method: str
    confidence: float | None = None

    def __post_init__(self):
        if type(self.provenance) is not str or self.provenance not in ALIGNMENT_PROVENANCES:
            raise HybridEvidenceValidationError(
                "alignment provenance is unsupported"
            )

        _require_safe_token(
            self.method,
            field_name="alignment method",
            max_length=MAX_PROVENANCE_METHOD_CHARS,
        )

        if self.confidence is not None:
            if type(self.confidence) is not float:
                raise HybridEvidenceValidationError(
                    "alignment confidence must be an exact float or None"
                )
            if not math.isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
                raise HybridEvidenceValidationError(
                    "alignment confidence must be finite and within [0.0, 1.0]"
                )

    @property
    def state(self) -> str:
        return self.provenance


def _validate_payload_integrity(
    payload: ExternalSubtitlePayload,
    *,
    field_name: str,
) -> None:
    if not isinstance(payload, ExternalSubtitlePayload):
        raise HybridEvidenceValidationError(
            field_name + " must be an ExternalSubtitlePayload"
        )

    if type(payload.payload) is not bytes:
        raise HybridEvidenceValidationError(
            field_name + " payload must remain exact bytes"
        )

    byte_size = len(payload.payload)
    if byte_size <= 0 or byte_size > MAX_SUBTITLE_BYTES:
        raise HybridEvidenceValidationError(
            field_name + " payload is outside MAX_SUBTITLE_BYTES"
        )

    if type(payload.byte_size) is not int or payload.byte_size != byte_size:
        raise HybridEvidenceValidationError(
            field_name + " byte_size does not match its immutable bytes"
        )

    computed_sha256 = hashlib.sha256(payload.payload).hexdigest()
    if type(payload.sha256) is not str or payload.sha256 != computed_sha256:
        raise HybridEvidenceValidationError(
            field_name + " sha256 does not match its immutable bytes"
        )

    if not isinstance(payload.candidate, SubtitleCandidate):
        raise HybridEvidenceValidationError(
            field_name + " candidate is not a SubtitleCandidate"
        )

    candidate = payload.candidate
    if candidate.source_kind != SOURCE_KIND_VALIDATED_EXTERNAL_TEXT:
        raise HybridEvidenceValidationError(
            field_name + " candidate kind is not validated external text"
        )


def _validate_external_payload(
    payload: object,
    *,
    dvd_id: str,
    expected_language: str,
    field_name: str,
) -> ExternalSubtitlePayload:
    _validate_payload_integrity(payload, field_name=field_name)
    if not isinstance(payload, ExternalSubtitlePayload):
        raise HybridEvidenceValidationError(
            field_name + " must be an ExternalSubtitlePayload"
        )

    candidate = payload.candidate
    if payload.dvd_id != dvd_id:
        raise HybridEvidenceValidationError(
            field_name + " dvd_id does not exactly match bundle dvd_id"
        )

    if candidate.validated_for_dvd_id != dvd_id:
        raise HybridEvidenceValidationError(
            field_name + " candidate DVD identity does not match bundle"
        )

    if candidate.language != expected_language:
        raise HybridEvidenceValidationError(
            field_name + " language must be exactly " + repr(expected_language)
        )

    if expected_language == "ja" and not payload.is_translation_source:
        raise HybridEvidenceValidationError(
            field_name + " is not an accepted Japanese translation source"
        )

    if expected_language == "en" and not payload.is_supporting_evidence:
        raise HybridEvidenceValidationError(
            field_name + " is not an accepted English supporting source"
        )

    return payload


def _validate_parsed_document(
    payload: ExternalSubtitlePayload,
    document: object,
    *,
    field_name: str,
) -> SubtitleDocument:
    if not isinstance(document, SubtitleDocument):
        raise HybridEvidenceValidationError(
            field_name + " must be a SubtitleDocument"
        )

    if document.format != payload.candidate.text_format:
        raise HybridEvidenceValidationError(
            field_name + " format does not match its external candidate"
        )

    if document.byte_size != payload.byte_size:
        raise HybridEvidenceValidationError(
            field_name + " byte_size does not match the immutable payload"
        )

    if document.source_sha256 != payload.sha256:
        raise HybridEvidenceValidationError(
            field_name + " source_sha256 does not match the immutable payload"
        )

    try:
        parsed_document = payload.parse()
    except Exception as error:  # Existing parser errors become this boundary's error.
        raise HybridEvidenceValidationError(
            field_name + " could not be parsed from its immutable payload"
        ) from error

    if document != parsed_document:
        raise HybridEvidenceValidationError(
            field_name + " is detached from the validated payload bytes"
        )

    return document


def _parse_payload_document(
    payload: object,
    *,
    field_name: str,
) -> SubtitleDocument:
    if not isinstance(payload, ExternalSubtitlePayload):
        raise HybridEvidenceValidationError(
            field_name + " requires an ExternalSubtitlePayload"
        )

    try:
        return payload.parse()
    except Exception as error:  # Existing parser errors become this boundary's error.
        raise HybridEvidenceValidationError(
            field_name + " could not be parsed from its immutable payload"
        ) from error


def _validate_asr_result(asr_result: object, *, dvd_id: str) -> ASRResult:
    if not isinstance(asr_result, ASRResult):
        raise HybridEvidenceValidationError(
            "asr_result must be an ASRResult"
        )

    if not isinstance(asr_result.source_snapshot, ASRSourceSnapshot):
        raise HybridEvidenceValidationError(
            "ASR source snapshot must be an ASRSourceSnapshot"
        )

    if asr_result.source_snapshot.dvd_id != dvd_id:
        raise HybridEvidenceValidationError(
            "ASR source snapshot dvd_id does not exactly match bundle dvd_id"
        )

    if asr_result.source_language != "ja":
        raise HybridEvidenceValidationError(
            "ASR source language must be exactly 'ja'"
        )

    if type(asr_result.segments) is not tuple:
        raise HybridEvidenceValidationError(
            "ASR segments must remain an immutable tuple"
        )

    return asr_result


def _validate_neighbor_reference(
    reference: HybridNeighborReference,
    *,
    external_ja_document: SubtitleDocument | None,
    external_en_document: SubtitleDocument | None,
    asr_result: ASRResult,
) -> None:
    if reference.source == NEIGHBOR_SOURCE_EXTERNAL_JA:
        if external_ja_document is None or reference.index >= len(external_ja_document.cues):
            raise HybridEvidenceValidationError(
                "neighbor reference points outside external JA cues"
            )
        return

    if reference.source == NEIGHBOR_SOURCE_EXTERNAL_EN:
        if external_en_document is None or reference.index >= len(external_en_document.cues):
            raise HybridEvidenceValidationError(
                "neighbor reference points outside external EN cues"
            )
        return

    if reference.source == NEIGHBOR_SOURCE_ASR_SEGMENT:
        if reference.index >= len(asr_result.segments):
            raise HybridEvidenceValidationError(
                "neighbor reference points outside ASR segments"
            )
        return

    # HybridNeighborReference validates that ASR word references have a
    # subindex.  The source index is the segment ordinal and the subindex is
    # the word ordinal, so both are checked against the existing ASR object.
    if reference.index >= len(asr_result.segments):
        raise HybridEvidenceValidationError(
            "ASR word reference points outside ASR segments"
        )
    if reference.subindex >= len(asr_result.segments[reference.index].words):
        raise HybridEvidenceValidationError(
            "ASR word reference points outside ASR words"
        )


@dataclass(frozen=True)
class HybridEvidenceBundle:
    """Immutable Stage11 v2 external-JA/Whisper evidence snapshot.

    ``external_ja_payload`` and ``external_ja_document`` may both be absent
    only for the explicit ASR-only representation.  When present, the
    document must be exactly the document reparsed from that payload; callers
    cannot attach arbitrary cue tuples with matching metadata.

    ``external_en_payload``/``external_en_document`` are optional supporting
    evidence.  They are never exposed as a translation source by this
    contract.  ``alignment`` records a later-stage state supplied by a caller;
    this module does not infer or calculate alignment.
    """

    dvd_id: str
    asr_result: ASRResult
    cue_evidence: tuple[HybridCueEvidence, ...]
    alignment: HybridAlignmentProvenance
    external_ja_payload: ExternalSubtitlePayload | None = None
    external_ja_document: SubtitleDocument | None = None
    external_en_payload: ExternalSubtitlePayload | None = None
    external_en_document: SubtitleDocument | None = None

    def __post_init__(self):
        dvd_id = _validate_dvd_id(self.dvd_id)
        asr_result = _validate_asr_result(
            self.asr_result,
            dvd_id=dvd_id,
        )

        external_ja_payload = None
        if self.external_ja_payload is None:
            if self.external_ja_document is not None:
                raise HybridEvidenceValidationError(
                    "external JA document requires an external JA payload"
                )
            external_ja_document = None
        else:
            external_ja_payload = _validate_external_payload(
                self.external_ja_payload,
                dvd_id=dvd_id,
                expected_language="ja",
                field_name="external_ja_payload",
            )
            ja_document = self.external_ja_document
            if ja_document is None:
                ja_document = _parse_payload_document(
                    external_ja_payload,
                    field_name="external_ja_document",
                )
            external_ja_document = _validate_parsed_document(
                external_ja_payload,
                ja_document,
                field_name="external_ja_document",
            )
            if self.external_ja_document is None:
                object.__setattr__(self, "external_ja_document", external_ja_document)

        if self.external_en_payload is None:
            if self.external_en_document is not None:
                raise HybridEvidenceValidationError(
                    "external EN document requires an external EN payload"
                )
            external_en_document = None
        else:
            external_en_payload = _validate_external_payload(
                self.external_en_payload,
                dvd_id=dvd_id,
                expected_language="en",
                field_name="external_en_payload",
            )
            en_document = self.external_en_document
            if en_document is None:
                en_document = _parse_payload_document(
                    external_en_payload,
                    field_name="external_en_document",
                )
            external_en_document = _validate_parsed_document(
                external_en_payload,
                en_document,
                field_name="external_en_document",
            )
            if self.external_en_document is None:
                object.__setattr__(self, "external_en_document", external_en_document)

        if not isinstance(self.alignment, HybridAlignmentProvenance):
            raise HybridEvidenceValidationError(
                "alignment must be a HybridAlignmentProvenance"
            )

        if external_ja_payload is None:
            if self.alignment.provenance == ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID:
                raise HybridEvidenceValidationError(
                    "hybrid alignment provenance requires external JA evidence"
                )
            expected_source = EVIDENCE_SOURCE_ASR_SEGMENT
            expected_count = len(asr_result.segments)
        else:
            if self.alignment.provenance == ALIGNMENT_PROVENANCE_ASR_ONLY:
                raise HybridEvidenceValidationError(
                    "ASR-only provenance cannot carry external JA evidence"
                )
            expected_source = EVIDENCE_SOURCE_EXTERNAL_JA
            if external_ja_document is None:
                raise HybridEvidenceValidationError(
                    "external JA evidence requires a parsed document"
                )
            expected_count = len(external_ja_document.cues)

        if type(self.cue_evidence) is not tuple:
            raise HybridEvidenceValidationError(
                "cue_evidence must be an immutable tuple"
            )

        if not self.cue_evidence:
            raise HybridEvidenceValidationError(
                "cue_evidence must contain at least one source identity"
            )

        if len(self.cue_evidence) > MAX_HYBRID_CUE_EVIDENCE:
            raise HybridEvidenceLimitError(
                "cue_evidence exceeds MAX_HYBRID_CUE_EVIDENCE"
            )

        if len(self.cue_evidence) != expected_count:
            raise HybridEvidenceValidationError(
                "cue_evidence must represent every source cue in deterministic order"
            )

        seen_cue_ids = set()
        for expected_index, cue in enumerate(self.cue_evidence):
            if not isinstance(cue, HybridCueEvidence):
                raise HybridEvidenceValidationError(
                    "cue_evidence must contain HybridCueEvidence values"
                )

            if cue.cue_id in seen_cue_ids:
                raise HybridEvidenceValidationError(
                    "cue_evidence must not contain duplicate cue IDs"
                )
            seen_cue_ids.add(cue.cue_id)

            if cue.source != expected_source:
                raise HybridEvidenceValidationError(
                    "cue evidence source does not match bundle evidence mode"
                )
            if cue.source_index != expected_index:
                raise HybridEvidenceValidationError(
                    "cue identities must be stable and in deterministic source order"
                )
            if cue.cue_id != stable_cue_id(expected_source, expected_index):
                raise HybridEvidenceValidationError(
                    "cue identity is not stable for its source ordinal"
                )

            for reference in cue.before_context + cue.after_context:
                _validate_neighbor_reference(
                    reference,
                    external_ja_document=external_ja_document,
                    external_en_document=external_en_document,
                    asr_result=asr_result,
                )

        if self.external_ja_payload is not None:
            if external_ja_document is None:
                raise HybridEvidenceValidationError(
                    "external JA evidence requires a parsed document"
                )
            if external_ja_document.format != self.external_ja_payload.candidate.text_format:
                raise HybridEvidenceValidationError(
                    "external JA document format is inconsistent"
                )

    @classmethod
    def from_external_ja_and_asr(
        cls,
        *,
        dvd_id: str,
        external_ja_payload: ExternalSubtitlePayload,
        asr_result: ASRResult,
        alignment: HybridAlignmentProvenance,
        external_ja_document: SubtitleDocument | None = None,
        external_en_payload: ExternalSubtitlePayload | None = None,
        external_en_document: SubtitleDocument | None = None,
        before_context: tuple[HybridNeighborReference, ...] = (),
        after_context: tuple[HybridNeighborReference, ...] = (),
    ) -> "HybridEvidenceBundle":
        """Build the full external-JA representation with stable cue IDs.

        The optional document is checked if supplied; otherwise it is derived
        by the existing external payload parser.  Context references are
        copied as tuple references for every JA cue, without copying text.
        """

        validated_dvd_id = _validate_dvd_id(dvd_id)
        validated_ja_payload = _validate_external_payload(
            external_ja_payload,
            dvd_id=validated_dvd_id,
            expected_language="ja",
            field_name="external_ja_payload",
        )
        _validate_asr_result(asr_result, dvd_id=validated_dvd_id)

        if external_ja_document is None:
            external_ja_document = _parse_payload_document(
                validated_ja_payload,
                field_name="external_ja_document",
            )
        else:
            external_ja_document = _validate_parsed_document(
                validated_ja_payload,
                external_ja_document,
                field_name="external_ja_document",
            )

        if external_en_payload is not None and external_en_document is None:
            external_en_document = _parse_payload_document(
                external_en_payload,
                field_name="external_en_document",
            )

        cue_evidence = tuple(
            HybridCueEvidence(
                identity=HybridCueIdentity.for_external_ja(index),
                before_context=before_context,
                after_context=after_context,
            )
            for index in range(len(external_ja_document.cues))
        )

        return cls(
            dvd_id=validated_dvd_id,
            asr_result=asr_result,
            cue_evidence=cue_evidence,
            alignment=alignment,
            external_ja_payload=validated_ja_payload,
            external_ja_document=external_ja_document,
            external_en_payload=external_en_payload,
            external_en_document=external_en_document,
        )

    @classmethod
    def from_asr_only(
        cls,
        *,
        dvd_id: str,
        asr_result: ASRResult,
        alignment: HybridAlignmentProvenance,
        external_en_payload: ExternalSubtitlePayload | None = None,
        external_en_document: SubtitleDocument | None = None,
        before_context: tuple[HybridNeighborReference, ...] = (),
        after_context: tuple[HybridNeighborReference, ...] = (),
    ) -> "HybridEvidenceBundle":
        """Build the explicit ASR-only representation with stable cue IDs."""

        validated_dvd_id = _validate_dvd_id(dvd_id)
        _validate_asr_result(asr_result, dvd_id=validated_dvd_id)

        if external_en_payload is not None and external_en_document is None:
            external_en_document = _parse_payload_document(
                external_en_payload,
                field_name="external_en_document",
            )

        cue_evidence = tuple(
            HybridCueEvidence(
                identity=HybridCueIdentity.for_asr_segment(index),
                before_context=before_context,
                after_context=after_context,
            )
            for index in range(len(asr_result.segments))
        )

        return cls(
            dvd_id=validated_dvd_id,
            asr_result=asr_result,
            cue_evidence=cue_evidence,
            alignment=alignment,
            external_en_payload=external_en_payload,
            external_en_document=external_en_document,
        )

    @property
    def asr_source_snapshot(self):
        """Return the exact source snapshot owned by the ASR result."""

        return self.asr_result.source_snapshot

    @property
    def external_ja_cues(self):
        """Return parsed JA cues without creating a competing cue type."""

        if self.external_ja_document is None:
            return ()
        return self.external_ja_document.cues

    @property
    def external_en_cues(self):
        """Return optional parsed EN cues as supporting evidence only."""

        if self.external_en_document is None:
            return ()
        return self.external_en_document.cues

    @property
    def alignment_provenance(self) -> HybridAlignmentProvenance:
        return self.alignment

    @property
    def evidence_mode(self) -> str:
        return self.alignment.provenance

    # Short read-only aliases make the source roles explicit without adding
    # another ownership type or mutable view.
    @property
    def ja_payload(self) -> ExternalSubtitlePayload | None:
        return self.external_ja_payload

    @property
    def ja_document(self) -> SubtitleDocument | None:
        return self.external_ja_document

    @property
    def en_payload(self) -> ExternalSubtitlePayload | None:
        return self.external_en_payload

    @property
    def en_document(self) -> SubtitleDocument | None:
        return self.external_en_document


__all__ = [
    "ALIGNMENT_PROVENANCE_ASR_ONLY",
    "ALIGNMENT_PROVENANCE_EXTERNAL_ASR_HYBRID",
    "ALIGNMENT_PROVENANCE_UNRESOLVED",
    "ALIGNMENT_PROVENANCES",
    "EVIDENCE_SOURCE_ASR_SEGMENT",
    "EVIDENCE_SOURCE_EXTERNAL_JA",
    "HybridAlignmentProvenance",
    "HybridCueEvidence",
    "HybridCueIdentity",
    "HybridEvidenceBundle",
    "HybridEvidenceError",
    "HybridEvidenceLimitError",
    "HybridEvidenceValidationError",
    "HybridNeighborReference",
    "MAX_HYBRID_CUE_EVIDENCE",
    "MAX_NEIGHBOR_REFERENCES_PER_SIDE",
    "NEIGHBOR_SOURCE_ASR_SEGMENT",
    "NEIGHBOR_SOURCE_ASR_WORD",
    "NEIGHBOR_SOURCE_EXTERNAL_EN",
    "NEIGHBOR_SOURCE_EXTERNAL_JA",
    "stable_cue_id",
]
