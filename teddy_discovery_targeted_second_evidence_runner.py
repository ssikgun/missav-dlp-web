"""Direct, route-neutral execution of targeted ASR second evidence.

This module is deliberately a small orchestration boundary.  It selects the
already-classified ``REQUIRE_SECOND_EVIDENCE`` source segments, builds the
explicit Stage11 V1 window plan, extracts one existing ``ASRAudioChunk`` per
planned window, calls an injected existing targeted-ASR transport, and binds
the validated responses with the existing in-memory binding contract.

The module does not implement HTTP, audio decoding, Whisper, semantic action
selection, subtitle timing changes, or persistence.  The production caller
supplies a ``RemoteFasterWhisperASR`` (or an equivalent already validated
provider) and this runner invokes only its existing
``transcribe_targeted_chunk`` method.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from teddy_discovery_asr import ASRResult, ASRSegment
from teddy_discovery_asr_audio import ASRAudioChunk, iter_audio_chunks
from teddy_discovery_asr_source import ASRLocalMediaSource
from teddy_discovery_asr_source_quality import ASRSourceQualityDecision
from teddy_discovery_targeted_asr_window import (
    STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1,
    TargetedSecondEvidenceWindowPolicy,
    validate_targeted_second_evidence_window_policy,
)
from teddy_discovery_targeted_second_evidence import (
    TargetedSecondEvidenceBinding,
    TargetedSecondEvidenceError,
    TargetedSecondEvidencePlan,
    TargetedSecondEvidenceWindow,
    TargetedSecondEvidenceWindowResult,
    bind_targeted_second_evidence,
    build_targeted_second_evidence_plan_with_policy,
    validate_targeted_second_evidence_binding,
)


class TargetedSecondEvidenceRunnerError(RuntimeError):
    """Raised when targeted second-evidence execution cannot finish safely."""


TargetedAudioWindowProvider = Callable[
    [TargetedSecondEvidenceWindow],
    ASRAudioChunk,
]


@dataclass(frozen=True)
class TargetedSecondEvidenceExecution:
    """Validated in-memory execution result; no persistent schema is added."""

    plan: TargetedSecondEvidencePlan
    policy_version: str
    bindings: tuple[TargetedSecondEvidenceBinding, ...]

    def __post_init__(self):
        if type(self.plan) is not TargetedSecondEvidencePlan:
            raise TargetedSecondEvidenceRunnerError(
                "execution plan has the wrong type"
            )
        try:
            self.plan.__post_init__()
        except Exception as error:
            raise TargetedSecondEvidenceRunnerError(
                "execution plan is invalid or detached"
            ) from error
        if (
            type(self.policy_version) is not str
            or not self.policy_version
            or self.policy_version != self.policy_version.strip()
            or any(character.isspace() for character in self.policy_version)
            or any(
                ord(character) < 32 or ord(character) == 127
                for character in self.policy_version
            )
        ):
            raise TargetedSecondEvidenceRunnerError(
                "execution policy_version is unsafe"
            )
        if type(self.bindings) is not tuple:
            raise TargetedSecondEvidenceRunnerError(
                "execution bindings must be an immutable tuple"
            )
        if len(self.bindings) != len(self.plan.sources):
            raise TargetedSecondEvidenceRunnerError(
                "execution binding coverage differs from the plan"
            )

        expected_source_ids = tuple(
            source.cue_id for source in self.plan.sources
        )
        actual_source_ids = []
        for binding in self.bindings:
            try:
                validated = validate_targeted_second_evidence_binding(binding)
            except Exception as error:
                raise TargetedSecondEvidenceRunnerError(
                    "execution contains an invalid binding"
                ) from error
            if validated != binding:
                raise TargetedSecondEvidenceRunnerError(
                    "execution binding is detached"
                )
            actual_source_ids.append(binding.source_id)
        if tuple(actual_source_ids) != expected_source_ids:
            raise TargetedSecondEvidenceRunnerError(
                "execution bindings are not in source order"
            )

    @property
    def source_count(self) -> int:
        return len(self.plan.sources)

    @property
    def window_count(self) -> int:
        return len(self.plan.windows)


def _require_targeted_transcriber(targeted_transport: object) -> Callable:
    method = getattr(targeted_transport, "transcribe_targeted_chunk", None)
    if not callable(method):
        raise TargetedSecondEvidenceRunnerError(
            "targeted transport must expose transcribe_targeted_chunk"
        )
    return method


def _validate_window_chunk(
    chunk: object,
    *,
    source_snapshot,
    window: TargetedSecondEvidenceWindow,
) -> ASRAudioChunk:
    if type(chunk) is not ASRAudioChunk:
        raise TargetedSecondEvidenceRunnerError(
            "audio window provider returned a non-ASRAudioChunk"
        )
    if chunk.source_snapshot != source_snapshot:
        raise TargetedSecondEvidenceRunnerError(
            "audio window source snapshot does not match the plan"
        )
    if (
        chunk.start_ms != window.start_ms
        or chunk.end_ms != window.end_ms
    ):
        raise TargetedSecondEvidenceRunnerError(
            "audio window timing does not match the requested window"
        )
    try:
        chunk.__post_init__()
    except Exception as error:
        raise TargetedSecondEvidenceRunnerError(
            "audio window is invalid or detached"
        ) from error
    return chunk


def _validated_targeted_segments(value: object) -> tuple[ASRSegment, ...]:
    if type(value) is not tuple:
        raise TargetedSecondEvidenceRunnerError(
            "targeted transport must return an immutable segment tuple"
        )
    for segment in value:
        if type(segment) is not ASRSegment:
            raise TargetedSecondEvidenceRunnerError(
                "targeted transport returned an invalid ASR segment"
            )
    return value


def build_targeted_audio_window_provider(
    local_source: ASRLocalMediaSource,
    *,
    audio_chunk_iterator=iter_audio_chunks,
) -> TargetedAudioWindowProvider:
    """Adapt the existing bounded decoder to the runner's window contract.

    The decoder is called once for each planned window and must yield exactly
    one chunk with the requested absolute bounds.  No media source is copied,
    deleted, or otherwise owned by this adapter; its existing context controls
    lifetime and cleanup.
    """

    if not isinstance(local_source, ASRLocalMediaSource):
        raise TargetedSecondEvidenceRunnerError(
            "local_source must be an ASRLocalMediaSource"
        )
    if not callable(audio_chunk_iterator):
        raise TargetedSecondEvidenceRunnerError(
            "audio_chunk_iterator must be callable"
        )

    def provide(window: TargetedSecondEvidenceWindow) -> ASRAudioChunk:
        if type(window) is not TargetedSecondEvidenceWindow:
            raise TargetedSecondEvidenceRunnerError(
                "audio window provider received an invalid window"
            )
        duration_seconds = (window.end_ms - window.start_ms) / 1_000.0
        start_seconds = window.start_ms / 1_000.0
        end_seconds = window.end_ms / 1_000.0
        try:
            chunks = tuple(
                audio_chunk_iterator(
                    local_source,
                    chunk_seconds=duration_seconds,
                    start_seconds=start_seconds,
                    end_seconds=end_seconds,
                )
            )
        except Exception as error:
            raise TargetedSecondEvidenceRunnerError(
                "targeted audio window extraction failed"
            ) from error
        if len(chunks) != 1:
            raise TargetedSecondEvidenceRunnerError(
                "targeted audio window must yield exactly one chunk"
            )
        return _validate_window_chunk(
            chunks[0],
            source_snapshot=local_source.source_snapshot,
            window=window,
        )

    return provide


def run_targeted_second_evidence(
    asr_result: ASRResult,
    source_quality_decisions: tuple[ASRSourceQualityDecision, ...],
    *,
    policy: TargetedSecondEvidenceWindowPolicy,
    targeted_transport: object,
    audio_window_provider: TargetedAudioWindowProvider,
) -> TargetedSecondEvidenceExecution:
    """Execute only REQUIRE second evidence through an existing transport.

    ``targeted_transport`` must be the existing provider whose
    ``transcribe_targeted_chunk`` method already owns the VM122 endpoint,
    timeout, request serialization, response parsing, SHA checks, and bounds
    checks.  This function never creates a new network client.
    """

    try:
        validated_policy = validate_targeted_second_evidence_window_policy(
            policy
        )
    except Exception as error:
        raise TargetedSecondEvidenceRunnerError(
            "targeted second-evidence policy is invalid"
        ) from error
    if not callable(audio_window_provider):
        raise TargetedSecondEvidenceRunnerError(
            "audio_window_provider must be callable"
        )
    transcribe_targeted_chunk = _require_targeted_transcriber(
        targeted_transport
    )

    try:
        plan = build_targeted_second_evidence_plan_with_policy(
            asr_result,
            source_quality_decisions,
            policy=validated_policy,
        )
    except Exception as error:
        raise TargetedSecondEvidenceRunnerError(
            "targeted second-evidence plan construction failed"
        ) from error

    results = []
    for window in plan.windows:
        try:
            chunk = audio_window_provider(window)
            chunk = _validate_window_chunk(
                chunk,
                source_snapshot=plan.source_snapshot,
                window=window,
            )
            segments = _validated_targeted_segments(
                transcribe_targeted_chunk(chunk)
            )
            results.append(
                TargetedSecondEvidenceWindowResult(
                    source_snapshot=plan.source_snapshot,
                    window_id=window.window_id,
                    window_start_ms=window.start_ms,
                    window_end_ms=window.end_ms,
                    segments=segments,
                    plan_binding_sha256=plan.binding_sha256,
                )
            )
        except TargetedSecondEvidenceRunnerError:
            raise
        except Exception as error:
            raise TargetedSecondEvidenceRunnerError(
                "targeted second-evidence window execution failed"
            ) from error

    try:
        bindings = bind_targeted_second_evidence(plan, tuple(results))
        return TargetedSecondEvidenceExecution(
            plan=plan,
            policy_version=validated_policy.version,
            bindings=tuple(bindings),
        )
    except (TargetedSecondEvidenceError, TargetedSecondEvidenceRunnerError):
        raise
    except Exception as error:
        raise TargetedSecondEvidenceRunnerError(
            "targeted second-evidence binding failed"
        ) from error


def run_targeted_second_evidence_v1(
    asr_result: ASRResult,
    source_quality_decisions: tuple[ASRSourceQualityDecision, ...],
    *,
    targeted_transport: object,
    audio_window_provider: TargetedAudioWindowProvider,
) -> TargetedSecondEvidenceExecution:
    """Run the canonical Stage11 targeted second-evidence V1 policy."""

    return run_targeted_second_evidence(
        asr_result,
        source_quality_decisions,
        policy=STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1,
        targeted_transport=targeted_transport,
        audio_window_provider=audio_window_provider,
    )


def run_targeted_second_evidence_from_local_source(
    asr_result: ASRResult,
    source_quality_decisions: tuple[ASRSourceQualityDecision, ...],
    *,
    policy: TargetedSecondEvidenceWindowPolicy,
    local_source: ASRLocalMediaSource,
    targeted_transport: object,
    audio_chunk_iterator=iter_audio_chunks,
) -> TargetedSecondEvidenceExecution:
    """Run with the existing bounded local-media audio extraction contract."""

    if not isinstance(local_source, ASRLocalMediaSource):
        raise TargetedSecondEvidenceRunnerError(
            "local_source must be an ASRLocalMediaSource"
        )
    if local_source.source_snapshot != asr_result.source_snapshot:
        raise TargetedSecondEvidenceRunnerError(
            "local_source snapshot does not match the ASR result"
        )

    provider = build_targeted_audio_window_provider(
        local_source,
        audio_chunk_iterator=audio_chunk_iterator,
    )

    return run_targeted_second_evidence(
        asr_result,
        source_quality_decisions,
        policy=policy,
        targeted_transport=targeted_transport,
        audio_window_provider=provider,
    )


def run_targeted_second_evidence_v1_from_local_source(
    asr_result: ASRResult,
    source_quality_decisions: tuple[ASRSourceQualityDecision, ...],
    *,
    local_source: ASRLocalMediaSource,
    targeted_transport: object,
    audio_chunk_iterator=iter_audio_chunks,
) -> TargetedSecondEvidenceExecution:
    """Run the canonical V1 policy against an existing local source."""

    return run_targeted_second_evidence_from_local_source(
        asr_result,
        source_quality_decisions,
        policy=STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1,
        local_source=local_source,
        targeted_transport=targeted_transport,
        audio_chunk_iterator=audio_chunk_iterator,
    )


__all__ = [
    "TargetedAudioWindowProvider",
    "TargetedSecondEvidenceExecution",
    "TargetedSecondEvidenceRunnerError",
    "build_targeted_audio_window_provider",
    "run_targeted_second_evidence",
    "run_targeted_second_evidence_from_local_source",
    "run_targeted_second_evidence_v1",
    "run_targeted_second_evidence_v1_from_local_source",
]
