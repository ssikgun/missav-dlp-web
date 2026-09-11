"""Offline round-trip smoke for generic targeted second-evidence artifacts.

The smoke constructs typed fake executions only.  It never contacts VM122,
invokes Whisper/Hermes, or writes the proposed ADN artifact path.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import hashlib
import json
import os
import stat
import tempfile

from teddy_discovery_asr import (
    ASRResult,
    ASRSegment,
    ASRSourceSnapshot,
    ASRWord,
    LOCAL_CPU_MEDIUM_RUNTIME_IDENTITY,
)
from teddy_discovery_asr_source_quality import (
    classify_asr_result_source_quality,
)
from teddy_discovery_targeted_asr_window import (
    STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1,
)
from teddy_discovery_targeted_second_evidence import (
    TargetedSecondEvidenceWindowResult,
    bind_targeted_second_evidence,
    build_targeted_second_evidence_plan_with_policy,
)
from teddy_discovery_targeted_second_evidence_artifact import (
    TARGETED_SECOND_EVIDENCE_ARTIFACT_FILE_MODE,
    TargetedSecondEvidenceArtifactPersistenceError,
    TargetedSecondEvidenceArtifactValidationError,
    TargetedSecondEvidenceArtifact,
    parse_targeted_second_evidence_artifact_bytes,
    persist_targeted_second_evidence,
    require_matching_targeted_second_evidence_context,
    serialize_targeted_second_evidence_artifact,
    targeted_second_evidence_artifact_from_execution,
    write_targeted_second_evidence_artifact,
)
from teddy_discovery_targeted_second_evidence_runner import (
    TargetedSecondEvidenceExecution,
)


BASELINE_SHA = "a" * 64
ENGINE_VERSION = "synthetic-targeted-worker-1"

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


def snapshot() -> ASRSourceSnapshot:
    return ASRSourceSnapshot(
        dvd_id="ADN-785",
        canonical_video_relative="ADN/ADN-785/ADN-785.mp4",
        source_size=123_456,
        source_mtime_ns=987_654_321,
    )


def execution_for(segments: tuple[ASRSegment, ...]) -> TargetedSecondEvidenceExecution:
    asr_result = ASRResult(
        source_snapshot=snapshot(),
        source_language="ja",
        segments=(ASRSegment(100, 200, "せいせいせいせい"),),
        engine_version="synthetic-baseline-1",
    )
    decisions = classify_asr_result_source_quality(asr_result)
    plan = build_targeted_second_evidence_plan_with_policy(
        asr_result,
        decisions,
        policy=STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1,
    )
    result = TargetedSecondEvidenceWindowResult(
        source_snapshot=plan.source_snapshot,
        window_id=plan.windows[0].window_id,
        window_start_ms=plan.windows[0].start_ms,
        window_end_ms=plan.windows[0].end_ms,
        segments=segments,
        plan_binding_sha256=plan.binding_sha256,
    )
    bindings = bind_targeted_second_evidence(plan, (result,))
    return TargetedSecondEvidenceExecution(
        plan=plan,
        policy_version=STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1.version,
        bindings=bindings,
    )


def artifact_for(segments: tuple[ASRSegment, ...]) -> TargetedSecondEvidenceArtifact:
    return targeted_second_evidence_artifact_from_execution(
        execution_for(segments),
        baseline_asr_artifact_sha256=BASELINE_SHA,
        runtime_identity=LOCAL_CPU_MEDIUM_RUNTIME_IDENTITY,
        engine_version=ENGINE_VERSION,
    )


def canonical_payload_with_updated_sha(value: dict[str, object]) -> bytes:
    payload = dict(value)
    payload.pop("artifact_sha256", None)
    payload_bytes = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    payload["artifact_sha256"] = hashlib.sha256(payload_bytes).hexdigest()
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def mutated_raw(mutator) -> bytes:
    value = json.loads(
        serialize_targeted_second_evidence_artifact(artifact_for(()))
        .decode("utf-8")
    )
    mutator(value)
    return canonical_payload_with_updated_sha(value)


def main():
    normal_segments = (
        ASRSegment(
            100,
            160,
            "せい、せい",
            words=(
                ASRWord(100, 120, "せい"),
                ASRWord(125, 150, "せい"),
            ),
        ),
        ASRSegment(170, 230, "気持ちいい"),
    )
    normal = artifact_for(normal_segments)
    raw = serialize_targeted_second_evidence_artifact(normal)
    parsed = parse_targeted_second_evidence_artifact_bytes(raw)
    decoded = json.loads(raw.decode("utf-8"))
    check(parsed == normal, "PRESENT_EXACT_ROUND_TRIP")
    check(
        serialize_targeted_second_evidence_artifact(parsed) == raw,
        "SECOND_SERIALIZATION_BYTE_IDENTICAL",
    )
    check(
        decoded["artifact_sha256"] == parsed.artifact_sha256,
        "ARTIFACT_SHA_READBACK",
    )
    check(
        "unresolved" not in decoded
        and parsed.bindings[0].targeted_segments == normal.bindings[0].targeted_segments
        and parsed.bindings[0].targeted_segments[0].words == normal.bindings[0].targeted_segments[0].words,
        "FULL_SEGMENT_TEXT_TIMING_WORD_PRESERVATION",
    )
    check(
        parsed.bindings[0].status == "PRESENT_UNRESOLVED",
        "AUTHORITATIVE_PRESENT_STATUS",
    )

    empty = artifact_for(())
    empty_raw = serialize_targeted_second_evidence_artifact(empty)
    empty_parsed = parse_targeted_second_evidence_artifact_bytes(empty_raw)
    check(
        empty_parsed.bindings[0].status == "EMPTY_UNRESOLVED",
        "EMPTY_UNRESOLVED_ROUND_TRIP",
    )

    noisy = artifact_for((ASRSegment(100, 180, "あ" * 64),))
    noisy_parsed = parse_targeted_second_evidence_artifact_bytes(
        serialize_targeted_second_evidence_artifact(noisy)
    )
    check(
        noisy_parsed.bindings[0].status == "NOISY_UNRESOLVED",
        "NOISY_UNRESOLVED_ROUND_TRIP",
    )

    expect(
        TargetedSecondEvidenceArtifactValidationError,
        lambda: parse_targeted_second_evidence_artifact_bytes(
            mutated_raw(
                lambda value: value["results"][0].update(status="UNKNOWN")
            )
        ),
        "UNKNOWN_STATUS_FAILS_CLOSED",
    )
    expect(
        TargetedSecondEvidenceArtifactValidationError,
        lambda: parse_targeted_second_evidence_artifact_bytes(
            mutated_raw(
                lambda value: value["sources"][0].update(
                    start_ms=value["sources"][0]["start_ms"] + 1
                )
            )
        ),
        "SOURCE_TIMING_MISMATCH_FAILS_CLOSED",
    )
    expect(
        TargetedSecondEvidenceArtifactValidationError,
        lambda: parse_targeted_second_evidence_artifact_bytes(
            mutated_raw(
                lambda value: value.update(binding_sha256="b" * 64)
            )
        ),
        "BINDING_DIGEST_MISMATCH_FAILS_CLOSED",
    )
    expect(
        TargetedSecondEvidenceArtifactValidationError,
        lambda: parse_targeted_second_evidence_artifact_bytes(
            mutated_raw(
                lambda value: value["sources"].append(
                    deepcopy(value["sources"][0])
                )
            )
        ),
        "DUPLICATE_SOURCE_FAILS_CLOSED",
    )
    expect(
        TargetedSecondEvidenceArtifactValidationError,
        lambda: parse_targeted_second_evidence_artifact_bytes(
            mutated_raw(
                lambda value: value["windows"].__setitem__(
                    0,
                    dict(value["windows"][0], window_id="targeted-window-000002"),
                )
            )
        ),
        "DUPLICATE_WINDOW_FAILS_CLOSED",
    )
    expect(
        TargetedSecondEvidenceArtifactValidationError,
        lambda: parse_targeted_second_evidence_artifact_bytes(
            mutated_raw(
                lambda value: value.update(
                    baseline_asr_artifact_sha256="not-a-sha"
                )
            )
        ),
        "MALFORMED_BASELINE_SHA_FAILS_CLOSED",
    )
    expect(
        TargetedSecondEvidenceArtifactValidationError,
        lambda: parse_targeted_second_evidence_artifact_bytes(
            mutated_raw(lambda value: value.update(policy_version="v2"))
        ),
        "POLICY_VERSION_MISMATCH_FAILS_CLOSED",
    )
    expect(
        TargetedSecondEvidenceArtifactValidationError,
        lambda: require_matching_targeted_second_evidence_context(
            normal,
            source_snapshot=normal.source_snapshot,
            baseline_asr_artifact_sha256="b" * 64,
        ),
        "BASELINE_SHA_CONTEXT_MISMATCH_FAILS_CLOSED",
    )
    expect(
        TargetedSecondEvidenceArtifactValidationError,
        lambda: require_matching_targeted_second_evidence_context(
            normal,
            source_snapshot=ASRSourceSnapshot(
                dvd_id="ADN-786",
                canonical_video_relative="ADN/ADN-786/ADN-786.mp4",
                source_size=normal.source_snapshot.source_size,
                source_mtime_ns=normal.source_snapshot.source_mtime_ns,
            ),
            baseline_asr_artifact_sha256=BASELINE_SHA,
        ),
        "SOURCE_SNAPSHOT_CONTEXT_MISMATCH_FAILS_CLOSED",
    )

    with tempfile.TemporaryDirectory(prefix="stage11-targeted-artifact-smoke-") as directory:
        output = Path(directory) / "synthetic-targeted-second-evidence.json"
        written = write_targeted_second_evidence_artifact(output, normal)
        info = os.lstat(written)
        check(
            written == output
            and stat.S_ISREG(info.st_mode)
            and stat.S_IMODE(info.st_mode) == TARGETED_SECOND_EVIDENCE_ARTIFACT_FILE_MODE
            and parse_targeted_second_evidence_artifact_bytes(output.read_bytes()) == normal,
            "PRIVATE_ARTIFACT_WRITE_READBACK",
        )
        expect(
            TargetedSecondEvidenceArtifactPersistenceError,
            lambda: write_targeted_second_evidence_artifact(output, normal),
            "ARTIFACT_OVERWRITE_REJECTED",
        )
        explicit_output = Path(directory) / "synthetic-explicit-persist.json"
        persist_targeted_second_evidence(
            explicit_output,
            execution_for(normal.bindings[0].targeted_segments),
            baseline_asr_artifact_sha256=BASELINE_SHA,
            runtime_identity=LOCAL_CPU_MEDIUM_RUNTIME_IDENTITY,
            engine_version=ENGINE_VERSION,
        )
        check(
            parse_targeted_second_evidence_artifact_bytes(
                explicit_output.read_bytes()
            ).artifact_sha256
            == artifact_for(normal.bindings[0].targeted_segments).artifact_sha256,
            "EXPLICIT_PERSISTENCE_API_READBACK",
        )

    print("SMOKE_PASS_COUNT=" + str(passes))
    print("SMOKE_FAIL_COUNT=" + str(fails))


if __name__ == "__main__":
    main()
