"""Offline smoke for the generic targeted second-evidence execution caller.

The smoke uses the frozen ADN ASR artifact and fake audio/transport
providers.  It never opens media, contacts VM122, invokes Whisper/Hermes, or
writes a targeted artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy

from teddy_discovery_asr import ASRSegment
from teddy_discovery_asr_artifact import parse_asr_result_bytes
from teddy_discovery_asr_audio import ASRAudioChunk
from teddy_discovery_asr_source import ASRLocalMediaSource
from teddy_discovery_asr_source_quality import (
    ASR_SOURCE_KEEP,
    ASR_SOURCE_OMIT,
    ASR_SOURCE_REQUIRE_SECOND_EVIDENCE,
    classify_asr_result_source_quality,
)
from teddy_discovery_targeted_asr_window import (
    STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1,
)
from teddy_discovery_targeted_second_evidence import (
    TargetedSecondEvidenceError,
    TargetedSecondEvidenceWindowResult,
    bind_targeted_second_evidence,
)
from teddy_discovery_targeted_second_evidence_runner import (
    TargetedSecondEvidenceRunnerError,
    run_targeted_second_evidence_v1_from_local_source,
    run_targeted_second_evidence_v1,
)


ADN_ASR_ARTIFACT = Path("/var/tmp/ADN-785.large-v3.stage11-asr-v1.json")
EXPECTED_REQUIRE_IDS = (
    "asr-000262",
    "asr-000473",
    "asr-000503",
    "asr-000511",
)

passes = 0
fails = 0


def check(condition: bool, marker: str):
    global passes, fails
    if not condition:
        fails += 1
        raise AssertionError(marker)
    passes += 1
    print("PASS=" + marker)


def expect(error_type, callback, marker: str):
    global passes, fails
    try:
        callback()
    except error_type:
        passes += 1
        print("PASS=" + marker)
        return
    except Exception as error:
        fails += 1
        raise AssertionError(
            marker + ": wrong exception " + type(error).__name__
        ) from error
    fails += 1
    raise AssertionError(marker)


def fake_provider(asr_result):
    def provide(window):
        return ASRAudioChunk(
            source_snapshot=asr_result.source_snapshot,
            start_ms=window.start_ms,
            end_ms=window.end_ms,
            sample_rate=16_000,
            samples=numpy.zeros(16, dtype=numpy.float32),
        )

    return provide


@dataclass
class FakeTargetedTransport:
    mode: str = "normal"

    def __post_init__(self):
        self.calls = []

    def transcribe_targeted_chunk(self, chunk):
        self.calls.append((chunk.start_ms, chunk.end_ms))
        if self.mode == "transport-failure":
            raise RuntimeError("synthetic transport failure")
        if self.mode == "empty" and len(self.calls) == 1:
            return ()
        if self.mode == "noisy" and len(self.calls) == 1:
            return (
                ASRSegment(
                    chunk.start_ms,
                    chunk.start_ms + 100,
                    "ん" * 64,
                ),
            )
        if self.mode == "out-of-window" and len(self.calls) == 1:
            return (
                ASRSegment(
                    chunk.end_ms,
                    chunk.end_ms + 1,
                    "outside",
                ),
            )
        if self.mode == "wrong-window" and len(self.calls) == 1:
            return (
                ASRSegment(
                    chunk.end_ms + 10,
                    chunk.end_ms + 20,
                    "wrong-window",
                ),
            )
        return (
            ASRSegment(
                chunk.start_ms,
                chunk.start_ms + 100,
                "second evidence",
            ),
        )


def duplicate_response_probe(asr_result, decisions):
    from teddy_discovery_targeted_second_evidence import (
        build_targeted_second_evidence_plan_with_policy,
    )

    plan = build_targeted_second_evidence_plan_with_policy(
        asr_result,
        decisions,
        policy=STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1,
    )
    duplicate = TargetedSecondEvidenceWindowResult(
        source_snapshot=plan.source_snapshot,
        window_id=plan.windows[0].window_id,
        window_start_ms=plan.windows[0].start_ms,
        window_end_ms=plan.windows[0].end_ms,
        segments=(),
        plan_binding_sha256=plan.binding_sha256,
    )
    remaining = tuple(
        TargetedSecondEvidenceWindowResult(
            source_snapshot=plan.source_snapshot,
            window_id=window.window_id,
            window_start_ms=window.start_ms,
            window_end_ms=window.end_ms,
            segments=(),
            plan_binding_sha256=plan.binding_sha256,
        )
        for window in plan.windows[2:]
    )
    bind_targeted_second_evidence(
        plan,
        (duplicate, duplicate, *remaining),
    )


def main():
    asr_result = parse_asr_result_bytes(ADN_ASR_ARTIFACT.read_bytes())
    decisions = classify_asr_result_source_quality(asr_result)
    action_counts = {
        action: sum(item.action == action for item in decisions)
        for action in (
            ASR_SOURCE_KEEP,
            ASR_SOURCE_OMIT,
            ASR_SOURCE_REQUIRE_SECOND_EVIDENCE,
        )
    }
    check(
        action_counts[ASR_SOURCE_REQUIRE_SECOND_EVIDENCE] == 4,
        "ADN_REQUIRE_COUNT_4",
    )

    provider = fake_provider(asr_result)
    normal_transport = FakeTargetedTransport()
    normal = run_targeted_second_evidence_v1(
        asr_result,
        decisions,
        targeted_transport=normal_transport,
        audio_window_provider=provider,
    )
    check(
        tuple(binding.source_id for binding in normal.bindings)
        == EXPECTED_REQUIRE_IDS,
        "REQUIRE_ONLY_SOURCE_SELECTION",
    )
    check(
        normal.policy_version == "v1"
        and normal.source_count == 4
        and normal.window_count == 4
        and len(normal_transport.calls) == 4,
        "V1_PLAN_AND_TRANSPORT_CALL_COUNT",
    )
    check(
        sum(
            binding.window.end_ms - binding.window.start_ms
            for binding in normal.bindings
        )
        == 61_460,
        "ADN_TOTAL_PLANNED_AUDIO_61_460_MS",
    )
    check(
        all(
            binding.source.start_ms != binding.window.start_ms
            or binding.source.end_ms != binding.window.end_ms
            for binding in normal.bindings
        ),
        "BASELINE_SOURCE_TIMING_REMAINS_DISTINCT",
    )

    local_source = ASRLocalMediaSource(
        local_path="/var/tmp/stage11-targeted-second-evidence-smoke.mp4",
        source_snapshot=asr_result.source_snapshot,
        temp_directory="/var/tmp/stage11-targeted-second-evidence-smoke-dir",
    )
    extraction_calls = []

    def fake_audio_chunk_iterator(
        source,
        *,
        chunk_seconds,
        start_seconds,
        end_seconds,
    ):
        extraction_calls.append(
            (chunk_seconds, start_seconds, end_seconds)
        )
        yield ASRAudioChunk(
            source_snapshot=source.source_snapshot,
            start_ms=round(start_seconds * 1_000),
            end_ms=round(end_seconds * 1_000),
            sample_rate=16_000,
            samples=numpy.zeros(16, dtype=numpy.float32),
        )

    local_transport = FakeTargetedTransport()
    local_execution = run_targeted_second_evidence_v1_from_local_source(
        asr_result,
        decisions,
        local_source=local_source,
        targeted_transport=local_transport,
        audio_chunk_iterator=fake_audio_chunk_iterator,
    )
    check(
        local_execution == normal
        and len(extraction_calls) == 4
        and extraction_calls[0][0] == 13.420,
        "EXISTING_AUDIO_EXTRACTION_CONTRACT_ADAPTED",
    )

    empty_transport = FakeTargetedTransport("empty")
    empty = run_targeted_second_evidence_v1(
        asr_result,
        decisions,
        targeted_transport=empty_transport,
        audio_window_provider=provider,
    )
    check(
        empty.bindings[0].status == "EMPTY_UNRESOLVED"
        and len(empty_transport.calls) == 4,
        "EMPTY_RESULT_VALID_UNRESOLVED",
    )

    noisy_transport = FakeTargetedTransport("noisy")
    noisy = run_targeted_second_evidence_v1(
        asr_result,
        decisions,
        targeted_transport=noisy_transport,
        audio_window_provider=provider,
    )
    check(
        noisy.bindings[0].status == "NOISY_UNRESOLVED",
        "NOISY_RESULT_VALID_UNRESOLVED",
    )

    expect(
        TargetedSecondEvidenceRunnerError,
        lambda: run_targeted_second_evidence_v1(
            asr_result,
            decisions,
            targeted_transport=FakeTargetedTransport("out-of-window"),
            audio_window_provider=provider,
        ),
        "OUT_OF_WINDOW_RESPONSE_FAILS_CLOSED",
    )
    expect(
        TargetedSecondEvidenceRunnerError,
        lambda: run_targeted_second_evidence_v1(
            asr_result,
            decisions,
            targeted_transport=FakeTargetedTransport("wrong-window"),
            audio_window_provider=provider,
        ),
        "WRONG_RESPONSE_WINDOW_FAILS_CLOSED",
    )
    expect(
        TargetedSecondEvidenceError,
        lambda: duplicate_response_probe(asr_result, decisions),
        "DUPLICATE_RESPONSE_FAILS_CLOSED",
    )
    expect(
        TargetedSecondEvidenceRunnerError,
        lambda: run_targeted_second_evidence_v1(
            asr_result,
            decisions,
            targeted_transport=FakeTargetedTransport("transport-failure"),
            audio_window_provider=provider,
        ),
        "TRANSPORT_FAILURE_FAILS_CLOSED",
    )

    repeat_transport = FakeTargetedTransport()
    repeated = run_targeted_second_evidence_v1(
        asr_result,
        decisions,
        targeted_transport=repeat_transport,
        audio_window_provider=provider,
    )
    check(
        repeated == normal
        and repeat_transport.calls == normal_transport.calls,
        "DETERMINISTIC_REPEAT_EQUALITY",
    )

    source_text = Path(
        "teddy_discovery_targeted_second_evidence_runner.py"
    ).read_text(encoding="utf-8")
    check(
        "transcribe_targeted_chunk" in source_text
        and "teddy_discovery_asr_remote" not in source_text
        and "urllib" not in source_text,
        "EXISTING_TRANSPORT_METHOD_ONLY",
    )
    check(
        "ASR_SOURCE_OMIT" not in source_text
        and "ASR_SOURCE_KEEP" not in source_text,
        "NO_SEMANTIC_ACTION_POLICY_IN_RUNNER",
    )

    print("ADN_SELECTED_REQUIRE=" + str(normal.source_count))
    print("ADN_DISTINCT_WINDOWS=" + str(normal.window_count))
    print("TRANSPORT_INVOCATIONS=" + str(len(normal_transport.calls)))
    print("BINDING_COUNT=" + str(len(normal.bindings)))
    print("SMOKE_PASS_COUNT=" + str(passes))
    print("SMOKE_FAIL_COUNT=" + str(fails))


if __name__ == "__main__":
    main()
