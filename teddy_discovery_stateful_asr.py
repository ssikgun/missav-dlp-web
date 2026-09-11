"""Pure ASR-only/stateful semantic package bridge.

The bridge owns only the conversion from an already validated ASR-only cue
sequence to the ordinary stateful semantic package. ASR remains the timing
authority in the separate ASR SRT materializer. No model, storage, or
publication I/O is owned here.
"""

from __future__ import annotations

from teddy_discovery_asr import ASRResult
from teddy_discovery_asr_source_quality import (
    ASR_SOURCE_OMIT,
    ASRSourceQualityDecision,
    classify_asr_result_source_quality,
    validate_asr_source_quality_decisions,
)
from teddy_discovery_hermes_v2 import HermesV2CueInput
from teddy_discovery_hybrid_evidence import (
    EVIDENCE_SOURCE_ASR_SEGMENT,
    stable_cue_id,
)
from teddy_discovery_nonlexical import (
    NONLEXICAL_KEEP,
    NONLEXICAL_OMIT,
)
from teddy_discovery_stateful_prepare import (
    StatefulPrepareResult,
    prepare_stateful_package,
)
from teddy_discovery_stateful_asr_srt import source_index_for_asr_cue_id
from teddy_discovery_stateful_translator import (
    STATEFUL_TRANSLATOR_MAX_CUES,
    STATEFUL_TRANSLATOR_SCHEMA_VERSION,
    StatefulSubtitlePackage,
)


class StatefulASRValidationError(ValueError):
    """ASR-only semantic evidence is invalid or detached."""


def _validated_asr_cues(
    value: object,
) -> tuple[HermesV2CueInput, ...]:
    if type(value) is not tuple:
        raise StatefulASRValidationError(
            "ASR-only cues must be an immutable tuple"
        )
    if not value:
        raise StatefulASRValidationError(
            "ASR-only cues must not be empty"
        )
    if len(value) > STATEFUL_TRANSLATOR_MAX_CUES:
        raise StatefulASRValidationError(
            "ASR-only cues exceed the stateful package limit"
        )

    validated: list[HermesV2CueInput] = []
    for index, cue in enumerate(value):
        if type(cue) is not HermesV2CueInput:
            raise StatefulASRValidationError(
                "ASR-only cues must contain exact HermesV2CueInput values"
            )

        try:
            candidate = HermesV2CueInput(
                cue_id=cue.cue_id,
                external_ja=cue.external_ja,
                stt_ja=cue.stt_ja,
                en=cue.en,
                before_context=cue.before_context,
                after_context=cue.after_context,
            )
        except (AttributeError, TypeError, ValueError, OverflowError) as error:
            raise StatefulASRValidationError(
                "ASR-only cue is invalid or detached"
            ) from error

        expected_cue_id = stable_cue_id(
            EVIDENCE_SOURCE_ASR_SEGMENT,
            index,
        )
        if candidate.cue_id != expected_cue_id:
            raise StatefulASRValidationError(
                "ASR-only cue IDs must be contiguous and ordered"
            )
        if candidate.external_ja is not None:
            raise StatefulASRValidationError(
                "ASR-only cue cannot carry external JA evidence"
            )
        if candidate.stt_ja is None:
            raise StatefulASRValidationError(
                "ASR-only cue requires STT evidence"
            )
        if candidate != cue:
            raise StatefulASRValidationError(
                "ASR-only cue identity or evidence is detached"
            )
        validated.append(candidate)

    return tuple(validated)


def build_stateful_asr_package(
    cues: tuple[HermesV2CueInput, ...],
    *,
    dvd_id: str,
    generation_key: str,
    claim_token: int,
) -> StatefulSubtitlePackage:
    """Build one ordinary stateful package from validated ASR-only cues."""

    validated_cues = _validated_asr_cues(cues)
    try:
        return StatefulSubtitlePackage(
            schema_version=STATEFUL_TRANSLATOR_SCHEMA_VERSION,
            dvd_id=dvd_id,
            generation_key=generation_key,
            claim_token=claim_token,
            cues=validated_cues,
        )
    except Exception as error:
        raise StatefulASRValidationError(
            "ASR-only stateful package is invalid"
        ) from error


def _validate_sparse_asr_package(
    package: StatefulSubtitlePackage,
) -> StatefulSubtitlePackage:
    """Validate the source identity retained across nonlexical filtering."""

    if type(package) is not StatefulSubtitlePackage:
        raise StatefulASRValidationError(
            "ASR-only package must be an exact StatefulSubtitlePackage"
        )

    try:
        validated_package = StatefulSubtitlePackage(
            schema_version=package.schema_version,
            dvd_id=package.dvd_id,
            generation_key=package.generation_key,
            claim_token=package.claim_token,
            cues=package.cues,
        )
    except (AttributeError, TypeError, ValueError, OverflowError) as error:
        raise StatefulASRValidationError(
            "ASR-only package is invalid or detached"
        ) from error

    if validated_package != package:
        raise StatefulASRValidationError(
            "ASR-only package identity or evidence is detached"
        )

    previous_source_index = None
    for cue in validated_package.cues:
        if cue.external_ja is not None:
            raise StatefulASRValidationError(
                "ASR-only package cannot carry external JA evidence"
            )
        if cue.stt_ja is None:
            raise StatefulASRValidationError(
                "ASR-only package requires STT evidence"
            )

        cue_id = cue.cue_id
        if not cue_id.startswith("asr-"):
            raise StatefulASRValidationError(
                "ASR-only package cue identity is not an ASR identity"
            )

        ordinal_text = cue_id[len("asr-"):]
        if not ordinal_text.isdigit():
            raise StatefulASRValidationError(
                "ASR-only package cue identity has an invalid ordinal"
            )

        ordinal = int(ordinal_text)
        if ordinal < 1:
            raise StatefulASRValidationError(
                "ASR-only package cue ordinal must be positive"
            )

        source_index = ordinal - 1
        try:
            expected_cue_id = stable_cue_id(
                EVIDENCE_SOURCE_ASR_SEGMENT,
                source_index,
            )
        except Exception as error:
            raise StatefulASRValidationError(
                "ASR-only package cue identity is outside ASR evidence"
            ) from error

        if cue_id != expected_cue_id:
            raise StatefulASRValidationError(
                "ASR-only package cue identity is not source-stable"
            )

        if (
            previous_source_index is not None
            and source_index <= previous_source_index
        ):
            raise StatefulASRValidationError(
                "ASR-only package cues must remain in source order"
            )
        previous_source_index = source_index

    return validated_package


def _quality_decisions_for_package(
    package: StatefulSubtitlePackage,
    decisions: tuple[ASRSourceQualityDecision, ...],
) -> tuple[ASRSourceQualityDecision, ...]:
    """Bind already classified ASR decisions to this package's sparse IDs."""

    if type(decisions) is not tuple:
        raise StatefulASRValidationError(
            "ASR source-quality decisions must be an immutable tuple"
        )

    by_index = {}
    for decision in decisions:
        if type(decision) is not ASRSourceQualityDecision:
            raise StatefulASRValidationError(
                "ASR source-quality decisions contain an invalid value"
            )
        try:
            decision.__post_init__()
        except Exception as error:
            raise StatefulASRValidationError(
                "ASR source-quality decision is invalid"
            ) from error
        if decision.source_index in by_index:
            raise StatefulASRValidationError(
                "ASR source-quality decisions contain a duplicate index"
            )
        by_index[decision.source_index] = decision

    selected = []
    for cue in package.cues:
        try:
            source_index = source_index_for_asr_cue_id(cue.cue_id)
        except Exception as error:
            raise StatefulASRValidationError(
                "ASR package cue identity cannot resolve source quality"
            ) from error
        decision = by_index.get(source_index)
        if decision is None or decision.source_text != cue.stt_ja:
            raise StatefulASRValidationError(
                "ASR source-quality decision is detached from package text"
            )
        selected.append(decision)
    return tuple(selected)


def prepare_stateful_asr_package(
    package: StatefulSubtitlePackage,
    *,
    generation_key: str,
    asr_result: ASRResult | None = None,
    source_quality_decisions: tuple[ASRSourceQualityDecision, ...] | None = None,
) -> StatefulPrepareResult:
    """Filter pathological ASR cues while preserving sparse source identity.

    The package must first have passed ``build_stateful_asr_package``.  This
    wrapper adds only the ASR-only identity boundary, then delegates the
    actual decision to the existing generic ``prepare_stateful_package``.
    The returned package is the only package that should be sent to the
    stateful part planner.
    """

    validated_package = _validate_sparse_asr_package(package)

    if asr_result is not None:
        if type(asr_result) is not ASRResult:
            raise StatefulASRValidationError(
                "ASR source-quality input must be an exact ASRResult"
            )
        try:
            asr_result.__post_init__()
        except Exception as error:
            raise StatefulASRValidationError(
                "ASR source-quality ASRResult is invalid"
            ) from error
        if asr_result.source_snapshot.dvd_id != validated_package.dvd_id:
            raise StatefulASRValidationError(
                "ASR source-quality input belongs to another DVD-ID"
            )
        for cue in validated_package.cues:
            source_index = source_index_for_asr_cue_id(cue.cue_id)
            if (
                source_index >= len(asr_result.segments)
                or cue.stt_ja != asr_result.segments[source_index].text
            ):
                raise StatefulASRValidationError(
                    "ASR package text is detached from source-quality ASRResult"
                )
        if source_quality_decisions is None:
            source_quality_decisions = classify_asr_result_source_quality(asr_result)
        else:
            try:
                source_quality_decisions = validate_asr_source_quality_decisions(
                    asr_result.segments,
                    source_quality_decisions,
                )
            except Exception as error:
                raise StatefulASRValidationError(
                    "ASR source-quality decisions differ from ASRResult"
                ) from error

    package_quality_decisions = None
    if source_quality_decisions is not None:
        package_quality_decisions = _quality_decisions_for_package(
            validated_package,
            source_quality_decisions,
        )

    try:
        prepared = prepare_stateful_package(
            validated_package,
            generation_key=generation_key,
            source_quality_decisions=package_quality_decisions,
        )
    except Exception as error:
        raise StatefulASRValidationError(
            "ASR-only nonlexical preparation failed"
        ) from error

    source_by_id = {
        cue.cue_id: cue
        for cue in validated_package.cues
    }
    source_ids = tuple(source_by_id)
    decision_ids = tuple(cue_id for cue_id, _ in prepared.decisions)
    if decision_ids != source_ids:
        raise StatefulASRValidationError(
            "ASR-only classifier decisions do not cover source order"
        )

    if package_quality_decisions is None:
        expected_omitted_ids = tuple(
            cue_id
            for cue_id, decision in prepared.decisions
            if decision.action == NONLEXICAL_OMIT
        )
    else:
        expected_omitted_ids = tuple(
            cue_id
            for cue_id, decision in prepared.source_quality_decisions
            if decision.action == ASR_SOURCE_OMIT
        )
    if prepared.omitted_cue_ids != expected_omitted_ids:
        raise StatefulASRValidationError(
            "ASR-only omitted cue identities are detached"
        )

    if package_quality_decisions is None:
        expected_kept_ids = tuple(
            cue_id
            for cue_id, decision in prepared.decisions
            if decision.action == NONLEXICAL_KEEP
        )
    else:
        expected_kept_ids = tuple(
            cue_id
            for cue_id, decision in prepared.source_quality_decisions
            if decision.action != ASR_SOURCE_OMIT
        )
    actual_kept_ids = tuple(
        cue.cue_id
        for cue in prepared.package.cues
    )
    if actual_kept_ids != expected_kept_ids:
        raise StatefulASRValidationError(
            "ASR-only filtered cue order or coverage is invalid"
        )

    for cue in prepared.package.cues:
        source_cue = source_by_id.get(cue.cue_id)
        if source_cue is None or cue != source_cue:
            raise StatefulASRValidationError(
                "ASR-only retained cue evidence was mutated or detached"
            )
        if cue.external_ja is not None or cue.stt_ja != source_cue.stt_ja:
            raise StatefulASRValidationError(
                "ASR-only retained cue evidence is not exact"
            )

    return prepared


__all__ = [
    "StatefulASRValidationError",
    "build_stateful_asr_package",
    "prepare_stateful_asr_package",
]
