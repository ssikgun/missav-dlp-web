"""Stateless per-title Stage11 subtitle orchestration.

This module connects the already-frozen subtitle inventory/selection,
translation route, Korean guard, generated-SRT, and publication boundaries for
one validated canonical video.  It owns no persistent state, media I/O,
filesystem cleanup, scheduling, or Stage9 completion behavior.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import re
import unicodedata

from teddy_discovery_asr import ASRResult
from teddy_discovery_ko_guard import (
    guard_korean_sequence,
    ready_subtitle_cues,
)
from teddy_discovery_ko_srt import (
    GENERATED_SRT_NO_ARTIFACT,
    GENERATED_SRT_READY,
    GeneratedKoreanSRT,
    generate_korean_srt,
)
from teddy_discovery_ids import parse_dvd_id
from teddy_discovery_subtitle import (
    ACTION_ASR_REQUIRED,
    ACTION_SKIP_EXISTING_KO,
    ACTION_TEXT_SOURCE_READY,
    CanonicalHoldingValidationError,
    CanonicalVideoHolding,
    SOURCE_KIND_SIBLING_TEXT,
    SubtitleCandidate,
    SubtitleSelectionResult,
    derive_target_ko_relative,
    select_subtitle_source,
    validate_canonical_holding,
)
from teddy_discovery_subtitle_publish import (
    SUBTITLE_NO_ARTIFACT,
    SUBTITLE_PUBLISHED,
    SUBTITLE_SKIPPED_EXISTING_KO,
    SubtitlePublishResult,
)
from teddy_discovery_subtitle_text import (
    MAX_SUBTITLE_BYTES,
    MAX_SUBTITLE_CUES,
    parse_subtitle_bytes,
)


PIPELINE_EXISTING_KO = "EXISTING_KO"
PIPELINE_PUBLISHED = "PUBLISHED"
PIPELINE_SKIPPED_EXISTING_KO = "SKIPPED_EXISTING_KO"
PIPELINE_NO_KO_ARTIFACT = "NO_KO_ARTIFACT"

SOURCE_ROUTE_EXISTING_KO = "EXISTING_KO"
SOURCE_ROUTE_TEXT_JA = "TEXT_JA"
SOURCE_ROUTE_TEXT_EN = "TEXT_EN"
SOURCE_ROUTE_ASR_JA = "ASR_JA"


class SubtitlePipelineError(Exception):
    """Base class for deterministic per-title pipeline failures."""


class SubtitlePipelineValidationError(SubtitlePipelineError):
    """Raised for malformed pipeline inputs or result values."""


class SubtitlePipelineContractError(SubtitlePipelineError):
    """Raised when an injected or frozen boundary violates its contract."""


class SubtitlePipelineUnsupportedSourceError(SubtitlePipelineError):
    """Raised when selection returns a source this pipeline cannot retrieve."""


def _has_control_characters(value: str) -> bool:
    return any(
        ord(character) < 32
        or ord(character) == 127
        or unicodedata.category(character) == "Cc"
        for character in value
    )


def _expected_target_relative(dvd_id: object) -> str:
    if (
        type(dvd_id) is not str
        or not dvd_id
        or dvd_id != dvd_id.strip()
        or "\\" in dvd_id
        or "/" in dvd_id
        or _has_control_characters(dvd_id)
        or "-" not in dvd_id
    ):
        raise SubtitlePipelineValidationError(
            "dvd_id is not a safe canonical identifier"
        )

    family = dvd_id.rsplit("-", 1)[0]
    if not family:
        raise SubtitlePipelineValidationError(
            "dvd_id has no canonical family"
        )

    parsed = parse_dvd_id(dvd_id + ".mp4")
    if parsed is None or parsed.dvd_id != dvd_id:
        raise SubtitlePipelineValidationError(
            "dvd_id is not a frozen canonical identifier"
        )

    return derive_target_ko_relative(
        CanonicalVideoHolding(
            dvd_id=dvd_id,
            relative_path=f"{family}/{dvd_id}/{dvd_id}.mp4",
            video_format="mp4",
        )
    )


def _validate_sha256(value: object, *, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or re.fullmatch(r"[0-9a-f]{64}", value) is None
    ):
        raise SubtitlePipelineValidationError(
            field_name + " must be a lowercase SHA-256 digest"
        )
    return value


def _validate_positive_bounded(value: object, *, field_name: str) -> int:
    if (
        type(value) is not int
        or value <= 0
        or value > MAX_SUBTITLE_BYTES
    ):
        raise SubtitlePipelineValidationError(
            field_name + " is outside the allowed payload bound"
        )
    return value


def _validate_result_target(
    *,
    dvd_id: object,
    target_relative: object,
) -> tuple[str, str]:
    if type(target_relative) is not str:
        raise SubtitlePipelineValidationError(
            "target_relative must be a string"
        )

    expected = _expected_target_relative(dvd_id)
    if target_relative != expected:
        raise SubtitlePipelineValidationError(
            "target_relative is not the canonical Korean target"
        )

    return dvd_id, expected


def _validate_source_route_pair(
    *,
    state: str,
    source_route: str,
    source_language: str | None,
) -> None:
    if state == PIPELINE_EXISTING_KO:
        expected = (SOURCE_ROUTE_EXISTING_KO, "ko")
    elif state in {
        PIPELINE_PUBLISHED,
        PIPELINE_SKIPPED_EXISTING_KO,
        PIPELINE_NO_KO_ARTIFACT,
    }:
        if source_route == SOURCE_ROUTE_TEXT_JA:
            expected = (SOURCE_ROUTE_TEXT_JA, "ja")
        elif source_route == SOURCE_ROUTE_TEXT_EN:
            expected = (SOURCE_ROUTE_TEXT_EN, "en")
        elif source_route == SOURCE_ROUTE_ASR_JA:
            expected = (SOURCE_ROUTE_ASR_JA, "ja")
        else:
            raise SubtitlePipelineValidationError(
                "pipeline state has an invalid source route"
            )
    else:
        raise SubtitlePipelineValidationError(
            "pipeline result state is invalid"
        )

    if (source_route, source_language) != expected:
        raise SubtitlePipelineValidationError(
            "pipeline state and source language do not match"
        )


@dataclass(frozen=True)
class SubtitlePipelineResult:
    """Compact terminal metadata for one per-title Stage11 invocation."""

    state: str
    dvd_id: str
    source_route: str
    source_language: str | None
    target_relative: str
    cue_count: int
    sha256: str | None
    byte_size: int

    def __post_init__(self):
        dvd_id, _expected_target = _validate_result_target(
            dvd_id=self.dvd_id,
            target_relative=self.target_relative,
        )
        if type(dvd_id) is not str:
            raise SubtitlePipelineValidationError(
                "dvd_id must be a string"
            )

        _validate_source_route_pair(
            state=self.state,
            source_route=self.source_route,
            source_language=self.source_language,
        )

        if type(self.cue_count) is not int or self.cue_count < 0:
            raise SubtitlePipelineValidationError(
                "cue_count must be a nonnegative integer"
            )

        if self.state == PIPELINE_NO_KO_ARTIFACT:
            if (
                self.cue_count != 0
                or self.sha256 is not None
                or type(self.byte_size) is not int
                or self.byte_size != 0
            ):
                raise SubtitlePipelineValidationError(
                    "NO_KO_ARTIFACT contains artifact metadata"
                )
            return

        if self.cue_count <= 0 or self.cue_count > MAX_SUBTITLE_CUES:
            raise SubtitlePipelineValidationError(
                "pipeline cue_count is outside the allowed bound"
            )
        _validate_sha256(self.sha256, field_name="sha256")
        _validate_positive_bounded(
            self.byte_size,
            field_name="byte_size",
        )


def _validated_canonical_video(
    canonical_video: object,
) -> CanonicalVideoHolding:
    if not isinstance(canonical_video, CanonicalVideoHolding):
        raise SubtitlePipelineValidationError(
            "canonical_video must be a CanonicalVideoHolding"
        )

    holding = {
        "dvd_id": canonical_video.dvd_id,
        "storage_root": "jav",
        "relative_path": canonical_video.relative_path,
        "parse_status": "MATCHED",
        "present": 1,
    }

    try:
        validated = validate_canonical_holding(
            holding,
            canonical_video.dvd_id,
        )
    except (CanonicalHoldingValidationError, TypeError, ValueError) as error:
        raise SubtitlePipelineValidationError(
            "canonical_video does not satisfy the frozen holding contract"
        ) from error

    if validated != canonical_video:
        raise SubtitlePipelineValidationError(
            "canonical_video identity changed during validation"
        )

    return validated


def _holding_mapping(
    canonical_video: CanonicalVideoHolding,
) -> dict[str, object]:
    return {
        "dvd_id": canonical_video.dvd_id,
        "storage_root": "jav",
        "relative_path": canonical_video.relative_path,
        "parse_status": "MATCHED",
        "present": 1,
    }


def _require_callable(value: object, *, field_name: str) -> Callable:
    if not callable(value):
        raise SubtitlePipelineValidationError(
            field_name + " must be callable"
        )
    return value


def _dependency_methods(
    *,
    subtitle_reader: object,
    publisher: object,
) -> tuple[Callable, Callable, Callable]:
    list_candidates = getattr(
        subtitle_reader,
        "list_subtitle_candidates",
        None,
    )
    read_subtitle_bytes = getattr(
        subtitle_reader,
        "read_subtitle_bytes",
        None,
    )
    publish_korean_srt = getattr(
        publisher,
        "publish_korean_srt",
        None,
    )

    return (
        _require_callable(
            list_candidates,
            field_name="subtitle_reader.list_subtitle_candidates",
        ),
        _require_callable(
            read_subtitle_bytes,
            field_name="subtitle_reader.read_subtitle_bytes",
        ),
        _require_callable(
            publish_korean_srt,
            field_name="publisher.publish_korean_srt",
        ),
    )


def _validated_candidates(value: object) -> tuple[SubtitleCandidate, ...]:
    if not isinstance(value, tuple):
        raise SubtitlePipelineContractError(
            "subtitle inventory must be an immutable tuple"
        )

    for candidate in value:
        if not isinstance(candidate, SubtitleCandidate):
            raise SubtitlePipelineContractError(
                "subtitle inventory contains an invalid candidate"
            )

    return value


def _validated_selection(
    selection: object,
    *,
    canonical_video: CanonicalVideoHolding,
    target_relative: str,
) -> SubtitleSelectionResult:
    if not isinstance(selection, SubtitleSelectionResult):
        raise SubtitlePipelineContractError(
            "source selector returned an invalid result"
        )

    if (
        selection.dvd_id != canonical_video.dvd_id
        or selection.canonical_video_relative != canonical_video.relative_path
        or selection.target_ko_relative != target_relative
    ):
        raise SubtitlePipelineContractError(
            "source selection identity does not match canonical video"
        )

    if selection.action == ACTION_SKIP_EXISTING_KO:
        if (
            not isinstance(selection.selected_source, SubtitleCandidate)
            or selection.selected_language != "ko"
            or selection.selected_source.source_kind != SOURCE_KIND_SIBLING_TEXT
            or selection.selected_source.relative_path != target_relative
            or selection.selected_source.text_format != "srt"
        ):
            raise SubtitlePipelineContractError(
                "existing KO selection is not the canonical sibling"
            )
        return selection

    if selection.action == ACTION_TEXT_SOURCE_READY:
        if (
            not isinstance(selection.selected_source, SubtitleCandidate)
            or selection.selected_language not in {"ja", "en"}
        ):
            raise SubtitlePipelineContractError(
                "text selection is missing a supported source"
            )
        return selection

    if selection.action == ACTION_ASR_REQUIRED:
        if (
            selection.selected_source is not None
            or selection.selected_language is not None
        ):
            raise SubtitlePipelineContractError(
                "ASR selection contains a text source"
            )
        return selection

    raise SubtitlePipelineContractError(
        "source selector returned an unknown action"
    )


def _read_and_parse(
    read_subtitle_bytes: Callable,
    *,
    canonical_video: CanonicalVideoHolding,
    candidate: SubtitleCandidate,
):
    raw = read_subtitle_bytes(canonical_video, candidate)
    if type(raw) is not bytes or not raw or len(raw) > MAX_SUBTITLE_BYTES:
        raise SubtitlePipelineContractError(
            "subtitle reader returned invalid bounded bytes"
        )
    return raw, parse_subtitle_bytes(raw, candidate.text_format)


def _route_to_artifact(
    source_cues: tuple[object, ...],
    *,
    translator: Callable,
) -> GeneratedKoreanSRT:
    from teddy_discovery_translation_route import route_translation_sequence

    route_results = route_translation_sequence(
        source_cues,
        translate_cue=translator,
    )
    guarded_results = guard_korean_sequence(route_results)
    ready_cues = ready_subtitle_cues(guarded_results)
    artifact = generate_korean_srt(ready_cues)

    if not isinstance(artifact, GeneratedKoreanSRT):
        raise SubtitlePipelineContractError(
            "generated SRT boundary returned an invalid artifact"
        )

    if artifact.state == GENERATED_SRT_NO_ARTIFACT:
        if (
            artifact.payload is not None
            or artifact.cue_count != 0
            or artifact.sha256 is not None
            or artifact.byte_size != 0
        ):
            raise SubtitlePipelineContractError(
                "generated SRT no-artifact result is malformed"
            )
        return artifact

    if artifact.state != GENERATED_SRT_READY:
        raise SubtitlePipelineContractError(
            "generated SRT boundary returned an unknown state"
        )
    if (
        type(artifact.payload) is not bytes
        or not artifact.payload
        or type(artifact.cue_count) is not int
        or artifact.cue_count <= 0
        or artifact.cue_count > MAX_SUBTITLE_CUES
        or type(artifact.byte_size) is not int
        or artifact.byte_size != len(artifact.payload)
        or artifact.byte_size <= 0
        or artifact.byte_size > MAX_SUBTITLE_BYTES
        or not isinstance(artifact.sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", artifact.sha256) is None
        or artifact.sha256 != hashlib.sha256(artifact.payload).hexdigest()
    ):
        raise SubtitlePipelineContractError(
            "generated SRT ready result is malformed"
        )
    return artifact


def _existing_ko_result(
    *,
    canonical_video: CanonicalVideoHolding,
    target_relative: str,
    raw: bytes,
    document,
) -> SubtitlePipelineResult:
    return SubtitlePipelineResult(
        state=PIPELINE_EXISTING_KO,
        dvd_id=canonical_video.dvd_id,
        source_route=SOURCE_ROUTE_EXISTING_KO,
        source_language="ko",
        target_relative=target_relative,
        cue_count=len(document.cues),
        sha256=hashlib.sha256(raw).hexdigest(),
        byte_size=len(raw),
    )


def _published_result(
    *,
    canonical_video: CanonicalVideoHolding,
    target_relative: str,
    source_route: str,
    source_language: str,
    artifact: GeneratedKoreanSRT,
    publish_result: object,
) -> SubtitlePipelineResult:
    if not isinstance(publish_result, SubtitlePublishResult):
        raise SubtitlePipelineContractError(
            "publisher returned an invalid result"
        )

    if (
        publish_result.target_relative != target_relative
        or publish_result.sha256 != artifact.sha256
        or publish_result.byte_size != artifact.byte_size
    ):
        raise SubtitlePipelineContractError(
            "publisher result does not match generated artifact"
        )

    if publish_result.state == SUBTITLE_PUBLISHED:
        pipeline_state = PIPELINE_PUBLISHED
    elif publish_result.state == SUBTITLE_SKIPPED_EXISTING_KO:
        pipeline_state = PIPELINE_SKIPPED_EXISTING_KO
    elif publish_result.state == SUBTITLE_NO_ARTIFACT:
        raise SubtitlePipelineContractError(
            "publisher returned NO_ARTIFACT for a ready artifact"
        )
    else:
        raise SubtitlePipelineContractError(
            "publisher returned an unknown state"
        )

    return SubtitlePipelineResult(
        state=pipeline_state,
        dvd_id=canonical_video.dvd_id,
        source_route=source_route,
        source_language=source_language,
        target_relative=target_relative,
        cue_count=artifact.cue_count,
        sha256=artifact.sha256,
        byte_size=artifact.byte_size,
    )


def run_subtitle_pipeline(
    *,
    canonical_video: CanonicalVideoHolding,
    subtitle_reader: object,
    translate_ja_cue: Callable,
    translate_en_cue: Callable,
    asr_transcriber: Callable,
    publisher: object,
) -> SubtitlePipelineResult:
    """Process exactly one validated canonical title to a terminal result."""

    validated_video = _validated_canonical_video(canonical_video)
    target_relative = derive_target_ko_relative(validated_video)
    _validate_result_target(
        dvd_id=validated_video.dvd_id,
        target_relative=target_relative,
    )

    list_candidates, read_subtitle_bytes, publish_korean_srt = (
        _dependency_methods(
            subtitle_reader=subtitle_reader,
            publisher=publisher,
        )
    )
    ja_translator = _require_callable(
        translate_ja_cue,
        field_name="translate_ja_cue",
    )
    en_translator = _require_callable(
        translate_en_cue,
        field_name="translate_en_cue",
    )
    asr_call = _require_callable(
        asr_transcriber,
        field_name="asr_transcriber",
    )

    candidates = _validated_candidates(
        list_candidates(validated_video)
    )
    selection = _validated_selection(
        select_subtitle_source(
            _holding_mapping(validated_video),
            validated_video.dvd_id,
            candidates,
        ),
        canonical_video=validated_video,
        target_relative=target_relative,
    )

    if selection.action == ACTION_SKIP_EXISTING_KO:
        raw, document = _read_and_parse(
            read_subtitle_bytes,
            canonical_video=validated_video,
            candidate=selection.selected_source,
        )
        return _existing_ko_result(
            canonical_video=validated_video,
            target_relative=target_relative,
            raw=raw,
            document=document,
        )

    if selection.action == ACTION_TEXT_SOURCE_READY:
        selected_source = selection.selected_source
        if selected_source.source_kind != SOURCE_KIND_SIBLING_TEXT:
            raise SubtitlePipelineUnsupportedSourceError(
                "selected text source has no implemented sibling payload transport"
            )

        _raw, document = _read_and_parse(
            read_subtitle_bytes,
            canonical_video=validated_video,
            candidate=selected_source,
        )
        if selection.selected_language == "ja":
            source_route = SOURCE_ROUTE_TEXT_JA
            source_language = "ja"
            translator = ja_translator
        elif selection.selected_language == "en":
            source_route = SOURCE_ROUTE_TEXT_EN
            source_language = "en"
            translator = en_translator
        else:
            raise SubtitlePipelineContractError(
                "text selection language is not routable"
            )

        artifact = _route_to_artifact(
            document.cues,
            translator=translator,
        )

    else:
        asr_result = asr_call(validated_video)
        if not isinstance(asr_result, ASRResult):
            raise SubtitlePipelineContractError(
                "asr_transcriber returned an invalid result"
            )

        if (
            asr_result.source_language != "ja"
            or asr_result.source_snapshot.dvd_id != validated_video.dvd_id
            or asr_result.source_snapshot.canonical_video_relative
            != validated_video.relative_path
        ):
            raise SubtitlePipelineContractError(
                "ASR result source identity does not match canonical video"
            )

        source_route = SOURCE_ROUTE_ASR_JA
        source_language = "ja"
        artifact = _route_to_artifact(
            asr_result.segments,
            translator=ja_translator,
        )

    if artifact.state == GENERATED_SRT_NO_ARTIFACT:
        return SubtitlePipelineResult(
            state=PIPELINE_NO_KO_ARTIFACT,
            dvd_id=validated_video.dvd_id,
            source_route=source_route,
            source_language=source_language,
            target_relative=target_relative,
            cue_count=0,
            sha256=None,
            byte_size=0,
        )

    publish_result = publish_korean_srt(
        canonical_video=validated_video,
        artifact=artifact,
        target_relative=target_relative,
    )
    return _published_result(
        canonical_video=validated_video,
        target_relative=target_relative,
        source_route=source_route,
        source_language=source_language,
        artifact=artifact,
        publish_result=publish_result,
    )


__all__ = [
    "PIPELINE_EXISTING_KO",
    "PIPELINE_NO_KO_ARTIFACT",
    "PIPELINE_PUBLISHED",
    "PIPELINE_SKIPPED_EXISTING_KO",
    "SOURCE_ROUTE_ASR_JA",
    "SOURCE_ROUTE_EXISTING_KO",
    "SOURCE_ROUTE_TEXT_EN",
    "SOURCE_ROUTE_TEXT_JA",
    "SubtitlePipelineContractError",
    "SubtitlePipelineError",
    "SubtitlePipelineResult",
    "SubtitlePipelineUnsupportedSourceError",
    "SubtitlePipelineValidationError",
    "run_subtitle_pipeline",
]
