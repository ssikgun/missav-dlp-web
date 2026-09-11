"""Stage11 stateful semantic input preparation.

This module owns only deterministic pre-translation filtering and generation
identity rebinding. It does not translate, write files, create sessions,
publish subtitles, or mutate Stage11 job state.
"""

from __future__ import annotations

from dataclasses import dataclass

from teddy_discovery_asr_source_quality import (
    ASR_SOURCE_KEEP,
    ASR_SOURCE_OMIT,
    ASR_SOURCE_REQUIRE_SECOND_EVIDENCE,
    ASRSourceQualityDecision,
)
from teddy_discovery_nonlexical import (
    NONLEXICAL_KEEP,
    NONLEXICAL_OMIT,
    NonLexicalDecision,
    classify_nonlexical,
)
from teddy_discovery_stateful_translator import (
    StatefulSubtitlePackage,
)


class StatefulPrepareError(ValueError):
    """Base error for deterministic stateful input preparation."""


class StatefulPrepareValidationError(StatefulPrepareError):
    """Raised when preparation input violates its contract."""


@dataclass(frozen=True)
class StatefulPrepareResult:
    package: StatefulSubtitlePackage
    omitted_cue_ids: tuple[str, ...]
    decisions: tuple[tuple[str, NonLexicalDecision], ...]
    source_quality_decisions: tuple[tuple[str, ASRSourceQualityDecision], ...] = ()


def _source_text_for_nonlexical(cue) -> str:
    if cue.external_ja is not None:
        return cue.external_ja

    if cue.stt_ja is not None:
        return cue.stt_ja

    raise StatefulPrepareValidationError(
        "stateful cue lacks Japanese evidence"
    )


def prepare_stateful_package(
    package: StatefulSubtitlePackage,
    *,
    generation_key: str,
    source_quality_decisions: tuple[ASRSourceQualityDecision, ...] | None = None,
) -> StatefulPrepareResult:
    """Filter deterministic cues and bind a new generation key.

    The legacy call without ``source_quality_decisions`` retains the original
    nonlexical-only contract.  ASR production callers pass the already
    validated generic decisions so the ASR classifier is not applied a second
    time at this package boundary.
    """

    if type(package) is not StatefulSubtitlePackage:
        raise StatefulPrepareValidationError(
            "package must be an exact StatefulSubtitlePackage"
        )

    if type(generation_key) is not str or not generation_key.strip():
        raise StatefulPrepareValidationError(
            "generation_key must be a nonempty exact string"
        )

    if generation_key == package.generation_key:
        raise StatefulPrepareValidationError(
            "filtered package requires a new generation_key"
        )

    kept = []
    omitted = []
    decisions = []
    retained_source_quality = []

    if source_quality_decisions is not None:
        if type(source_quality_decisions) is not tuple:
            raise StatefulPrepareValidationError(
                "source-quality decisions must be an immutable tuple"
            )
        if len(source_quality_decisions) != len(package.cues):
            raise StatefulPrepareValidationError(
                "source-quality decisions must cover the package"
            )

    for index, cue in enumerate(package.cues):
        if source_quality_decisions is None:
            source_text = _source_text_for_nonlexical(cue)
            decision = classify_nonlexical(source_text)
        else:
            quality = source_quality_decisions[index]
            if type(quality) is not ASRSourceQualityDecision:
                raise StatefulPrepareValidationError(
                    "source-quality decisions contain an invalid value"
                )
            try:
                quality.__post_init__()
            except Exception as error:
                raise StatefulPrepareValidationError(
                    "source-quality decision is invalid"
                ) from error
            expected_cue_id = f"asr-{quality.source_index + 1:06d}"
            if (
                cue.cue_id != expected_cue_id
                or cue.external_ja is not None
                or cue.stt_ja != quality.source_text
            ):
                raise StatefulPrepareValidationError(
                    "source-quality decision is detached from ASR package"
                )
            decision = NonLexicalDecision(
                quality.evidence.nonlexical_action,
                quality.evidence.nonlexical_reason,
            )
            retained_source_quality.append((cue.cue_id, quality))

        decisions.append((cue.cue_id, decision))

        action = (
            decision.action
            if source_quality_decisions is None
            else source_quality_decisions[index].action
        )
        if action in {NONLEXICAL_OMIT, ASR_SOURCE_OMIT}:
            omitted.append(cue.cue_id)
            continue

        if action not in {
            NONLEXICAL_KEEP,
            ASR_SOURCE_KEEP,
            ASR_SOURCE_REQUIRE_SECOND_EVIDENCE,
        }:
            raise StatefulPrepareValidationError(
                "source-quality classifier returned an unknown action"
            )

        kept.append(cue)

    if not kept:
        raise StatefulPrepareValidationError(
            "nonlexical filtering removed every cue"
        )

    filtered = StatefulSubtitlePackage(
        schema_version=package.schema_version,
        dvd_id=package.dvd_id,
        generation_key=generation_key,
        claim_token=package.claim_token,
        cues=tuple(kept),
    )

    return StatefulPrepareResult(
        package=filtered,
        omitted_cue_ids=tuple(omitted),
        decisions=tuple(decisions),
        source_quality_decisions=tuple(retained_source_quality),
    )


__all__ = [
    "StatefulPrepareError",
    "StatefulPrepareResult",
    "StatefulPrepareValidationError",
    "prepare_stateful_package",
]
