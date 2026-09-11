"""Offline smoke tests for the reusable targeted-ASR artifact boundary."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import teddy_discovery_targeted_asr_artifact as artifact_module
from teddy_discovery_asr import (
    ASRRuntimeIdentity,
    ASRSegment,
    ASRSourceSnapshot,
    ASRWord,
    REMOTE_GPU_LARGE_V3_RUNTIME_IDENTITY,
)
from teddy_discovery_subtitle import validate_canonical_holding
from teddy_discovery_subtitle_text import SubtitleCue
from teddy_discovery_subtitle_v2_pipeline_smoke import affine_fixture
from teddy_discovery_hybrid_evidence import HybridCueIdentity
from teddy_discovery_targeted_asr_window import plan_targeted_asr_windows
from teddy_discovery_targeted_hybrid_evidence import (
    TargetedASRBinding,
    TargetedASRWindowEvidence,
    TargetedHybridEvidenceError,
    build_targeted_asr_bindings,
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


def snapshot(*, size=123_456, mtime_ns=654_321):
    dvd_id = "GEN-123"
    holding = validate_canonical_holding(
        {
            "dvd_id": dvd_id,
            "storage_root": "jav",
            "relative_path": "GEN/GEN-123/GEN-123.mp4",
            "parse_status": "MATCHED",
            "present": 1,
        },
        dvd_id,
    )
    return ASRSourceSnapshot.from_holding(
        holding,
        source_size=size,
        source_mtime_ns=mtime_ns,
    )


def window(
    source_snapshot: ASRSourceSnapshot,
    start_ms: int,
    end_ms: int,
    external_cue_ids: tuple[str, ...],
    segments: tuple[ASRSegment, ...],
) -> TargetedASRWindowEvidence:
    return TargetedASRWindowEvidence(
        source_snapshot=source_snapshot,
        window_start_ms=start_ms,
        window_end_ms=end_ms,
        external_cue_ids=external_cue_ids,
        segments=segments,
    )


def artifact() -> artifact_module.TargetedASRArtifact:
    source_snapshot = snapshot()
    first = window(
        source_snapshot,
        0,
        1_000,
        ("ja-000001", "ja-000002"),
        (
            ASRSegment(
                100,
                300,
                "第一発話",
                words=(
                    ASRWord(120, 180, "第一"),
                    ASRWord(180, 260, "発話"),
                ),
            ),
            ASRSegment(500, 800, "second segment"),
        ),
    )
    second = window(
        source_snapshot,
        1_200,
        2_200,
        ("ja-000003", "ja-000004"),
        (
            ASRSegment(
                1_300,
                1_600,
                "第三発話",
                words=(ASRWord(1_350, 1_500, "第三"),),
            ),
            ASRSegment(1_800, 2_000, "fourth segment"),
        ),
    )
    return artifact_module.TargetedASRArtifact(
        source_snapshot=source_snapshot,
        runtime_identity=REMOTE_GPU_LARGE_V3_RUNTIME_IDENTITY,
        engine_version="targeted-worker-test-1",
        windows=(first, second),
    )


def compact_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def mutated_payload(mutator, *, raw: bytes):
    value = json.loads(raw.decode("utf-8"))
    mutator(value)
    return compact_json(value)


def main():
    original = artifact()
    raw = artifact_module.serialize_targeted_asr_artifact(original)
    parsed = artifact_module.parse_targeted_asr_artifact_bytes(raw)

    # Padding overlaps, but the maximum duration vetoes merging.  Use the
    # actual planner, including a merged first window, to test cue ownership.
    cues = tuple(
        SubtitleCue(start, end, "synthetic cue")
        for start, end in ((100, 200), (250, 350), (450, 550), (650, 750))
    )
    alignment = affine_fixture(1.0, 0.0)
    planned = plan_targeted_asr_windows(
        cues, alignment,
        padding_before_ms=100,
        padding_after_ms=100,
        merge_gap_ms=0,
        max_window_ms=450,
    )
    check(
        tuple((item.start_ms, item.end_ms) for item in planned)
        == ((0, 450), (350, 650), (550, 850))
        and tuple(cue_id for item in planned for cue_id in item.external_cue_ids)
        == tuple(HybridCueIdentity.for_external_ja(i).cue_id for i in range(4)),
        "PLANNER_OVERLAP_PRESERVES_EACH_CUE_EXACTLY_ONCE",
    )
    planned_artifact = replace(
        original,
        windows=tuple(
            window(
                original.source_snapshot, item.start_ms, item.end_ms,
                item.external_cue_ids,
                (ASRSegment(item.start_ms, item.end_ms, "whole window"),),
            )
            for item in planned
        ),
    )
    planned_raw = artifact_module.serialize_targeted_asr_artifact(planned_artifact)
    check(
        artifact_module.parse_targeted_asr_artifact_bytes(planned_raw)
        == planned_artifact,
        "ACTUAL_PLANNER_OVERLAP_EXACT_ROUNDTRIP",
    )

    # Worker _convert_region_segments accepts an empty iterable, serializes
    # segments=[], and RemoteFasterWhisperASR._decode_response returns ().
    # Preserve every completed window even if some or all contain no speech.
    for empty_indexes in ((1,), (0, 1, 2)):
        empty_artifact = replace(
            planned_artifact,
            windows=tuple(
                replace(item, segments=()) if i in empty_indexes else item
                for i, item in enumerate(planned_artifact.windows)
            ),
        )
        empty_raw = artifact_module.serialize_targeted_asr_artifact(empty_artifact)
        restored = artifact_module.parse_targeted_asr_artifact_bytes(empty_raw)
        check(
            restored == empty_artifact
            and artifact_module.serialize_targeted_asr_artifact(restored) == empty_raw,
            "ZERO_SEGMENT_WINDOWS_ROUNDTRIP_" + str(len(empty_indexes)),
        )
    empty_window = restored.windows[-1]
    check(
        build_targeted_asr_bindings(cues, alignment, empty_window) == (),
        "ZERO_SEGMENT_WINDOW_PRODUCES_NO_BINDINGS",
    )
    expect(
        TargetedHybridEvidenceError,
        lambda: TargetedASRBinding(
            HybridCueIdentity.for_external_ja(3), empty_window, 0,
        ),
        "ZERO_SEGMENT_WINDOW_CANNOT_BIND_INDEX_ZERO",
    )
    expect(
        TargetedHybridEvidenceError,
        lambda: replace(empty_window, segments=[]),
        "EMPTY_SEGMENTS_STILL_REQUIRE_TUPLE",
    )
    expect(
        TargetedHybridEvidenceError,
        lambda: replace(empty_window, window_end_ms=empty_window.window_start_ms),
        "EMPTY_WINDOW_STILL_REQUIRES_POSITIVE_DURATION",
    )

    check(
        parsed == original
        and parsed.windows == original.windows
        and parsed.windows[0].segments[0].words
        == original.windows[0].segments[0].words,
        "MULTI_WINDOW_SEGMENT_WORD_EXACT_ROUNDTRIP",
    )
    check(
        raw == artifact_module.serialize_targeted_asr_artifact(original)
        and not raw.endswith(b"\n")
        and "第一発話".encode("utf-8") in raw,
        "DETERMINISTIC_COMPACT_UTF8_BYTES",
    )

    decoded = json.loads(raw.decode("utf-8"))
    check(
        list(decoded) == [
            "schema_version",
            "source_snapshot",
            "runtime_identity",
            "engine_version",
            "windows",
        ],
        "TOP_LEVEL_EXACT_SERIALIZATION_KEYS",
    )
    check(
        list(decoded["windows"][0]) == [
            "window_start_ms",
            "window_end_ms",
            "external_cue_ids",
            "segments",
        ]
        and list(decoded["windows"][0]["segments"][0])
        == ["start_ms", "end_ms", "text", "words"],
        "WINDOW_AND_SEGMENT_EXACT_SERIALIZATION_KEYS",
    )
    check(
        parsed.runtime_identity == REMOTE_GPU_LARGE_V3_RUNTIME_IDENTITY
        and parsed.engine_version == "targeted-worker-test-1",
        "TARGETED_RUNTIME_METADATA_ROUNDTRIP",
    )

    check(
        artifact_module.require_matching_targeted_asr_source(
            parsed,
            snapshot(),
        )
        == parsed,
        "SOURCE_SNAPSHOT_MATCHES_EXACTLY",
    )
    expect(
        artifact_module.TargetedASRArtifactValidationError,
        lambda: artifact_module.require_matching_targeted_asr_source(
            parsed,
            snapshot(size=123_457),
        ),
        "SOURCE_SNAPSHOT_DETACHED_FAILS_CLOSED",
    )
    expect(
        artifact_module.TargetedASRArtifactValidationError,
        lambda: artifact_module.TargetedASRArtifact(
            source_snapshot=snapshot(),
            runtime_identity=parsed.runtime_identity,
            engine_version=parsed.engine_version,
            windows=(
                parsed.windows[0],
                window(
                    snapshot(size=999),
                    1_200,
                    2_200,
                    ("ja-000003", "ja-000004"),
                    parsed.windows[1].segments,
                ),
            ),
        ),
        "WINDOW_SOURCE_SNAPSHOT_DETACHED_FAILS_CLOSED",
    )

    expect(
        artifact_module.TargetedASRArtifactValidationError,
        lambda: artifact_module.parse_targeted_asr_artifact_bytes(
            b'{"schema_version":1,"schema_version":1}'
        ),
        "DUPLICATE_JSON_KEY_FAILS",
    )
    expect(
        artifact_module.TargetedASRArtifactValidationError,
        lambda: artifact_module.parse_targeted_asr_artifact_bytes(
            mutated_payload(
                lambda value: value.update(unexpected=True),
                raw=raw,
            )
        ),
        "UNKNOWN_TOP_LEVEL_KEY_FAILS",
    )
    expect(
        artifact_module.TargetedASRArtifactValidationError,
        lambda: artifact_module.parse_targeted_asr_artifact_bytes(
            mutated_payload(
                lambda value: value.pop("windows"),
                raw=raw,
            )
        ),
        "MISSING_TOP_LEVEL_KEY_FAILS",
    )
    expect(
        artifact_module.TargetedASRArtifactValidationError,
        lambda: artifact_module.parse_targeted_asr_artifact_bytes(
            mutated_payload(
                lambda value: value["windows"][0]["segments"][0].update(
                    end_ms=1_001,
                ),
                raw=raw,
            )
        ),
        "SEGMENT_OUTSIDE_WINDOW_FAILS",
    )
    expect(
        artifact_module.TargetedASRArtifactValidationError,
        lambda: artifact_module.parse_targeted_asr_artifact_bytes(
            mutated_payload(
                lambda value: value["windows"][0].update(
                    external_cue_ids=["ja-000001", "ja-000001"],
                ),
                raw=raw,
            )
        ),
        "DUPLICATE_EXTERNAL_CUE_ID_FAILS",
    )
    expect(
        artifact_module.TargetedASRArtifactValidationError,
        lambda: artifact_module.parse_targeted_asr_artifact_bytes(
            mutated_payload(
                lambda value: value["windows"][0].update(
                    external_cue_ids=["ja-000002", "ja-000001"],
                ),
                raw=raw,
            )
        ),
        "OUT_OF_ORDER_EXTERNAL_CUE_ID_FAILS",
    )
    expect(
        artifact_module.TargetedASRArtifactValidationError,
        lambda: artifact_module.parse_targeted_asr_artifact_bytes(
            mutated_payload(
                lambda value: value["windows"].reverse(),
                raw=raw,
            )
        ),
        "OUT_OF_ORDER_WINDOWS_FAILS",
    )
    overlapping = replace(
        original,
        windows=(original.windows[0], replace(original.windows[1], window_start_ms=900)),
    )
    check(
        artifact_module.parse_targeted_asr_artifact_bytes(
            artifact_module.serialize_targeted_asr_artifact(overlapping)
        ) == overlapping,
        "OVERLAPPING_WINDOWS_WITH_INCREASING_START_ROUNDTRIP",
    )
    for invalid_start in (0, 100):
        # Both windows remain individually valid; the cue order is unchanged.
        # The first starts at 100, so these isolate decreasing/equal starts.
        expect(
            artifact_module.TargetedASRArtifactValidationError,
            lambda start=invalid_start: artifact_module.parse_targeted_asr_artifact_bytes(
                mutated_payload(
                    lambda value: (
                        value["windows"][0].update(window_start_ms=100),
                        value["windows"][1].update(window_start_ms=start),
                    ),
                    raw=raw,
                )
            ),
            "DECREASING_OR_EQUAL_WINDOW_START_FAILS_" + str(invalid_start),
        )
        expect(
            artifact_module.TargetedASRArtifactValidationError,
            lambda start=invalid_start: replace(
                original,
                windows=(
                    replace(original.windows[0], window_start_ms=100),
                    replace(original.windows[1], window_start_ms=start),
                ),
            ),
            "CONSTRUCTOR_REJECTS_DECREASING_OR_EQUAL_START_" + str(invalid_start),
        )
    expect(
        artifact_module.TargetedASRArtifactValidationError,
        lambda: artifact_module.parse_targeted_asr_artifact_bytes(
            mutated_payload(
                lambda value: value["windows"][1].update(
                    external_cue_ids=["ja-000001", "ja-000004"],
                ),
                raw=raw,
            )
        ),
        "CROSS_WINDOW_EXTERNAL_CUE_REUSE_FAILS",
    )
    expect(
        artifact_module.TargetedASRArtifactValidationError,
        lambda: artifact_module.parse_targeted_asr_artifact_bytes(
            mutated_payload(
                lambda value: value["source_snapshot"].update(source_size=0),
                raw=raw,
            )
        ),
        "MALFORMED_SOURCE_SNAPSHOT_FAILS",
    )
    expect(
        artifact_module.TargetedASRArtifactValidationError,
        lambda: artifact_module.parse_targeted_asr_artifact_bytes(
            mutated_payload(
                lambda value: value["windows"][0]["segments"][0].update(
                    text=" padded "
                ),
                raw=raw,
            )
        ),
        "DIALOGUE_TEXT_IS_NOT_NORMALIZED_ON_PARSE",
    )
    expect(
        artifact_module.TargetedASRArtifactValidationError,
        lambda: artifact_module.parse_targeted_asr_artifact_bytes(
            raw.replace(b'"source_size":123456', b'"source_size":NaN')
        ),
        "NONFINITE_NUMBER_FAILS",
    )

    old_byte_limit = artifact_module.MAX_TARGETED_ASR_ARTIFACT_BYTES
    artifact_module.MAX_TARGETED_ASR_ARTIFACT_BYTES = len(raw) - 1
    try:
        expect(
            artifact_module.TargetedASRArtifactLimitError,
            lambda: artifact_module.serialize_targeted_asr_artifact(original),
            "SERIALIZED_ARTIFACT_OVERSIZED_FAILS",
        )
        expect(
            artifact_module.TargetedASRArtifactLimitError,
            lambda: artifact_module.parse_targeted_asr_artifact_bytes(raw),
            "PARSED_ARTIFACT_OVERSIZED_FAILS",
        )
    finally:
        artifact_module.MAX_TARGETED_ASR_ARTIFACT_BYTES = old_byte_limit

    old_window_limit = artifact_module.MAX_TARGETED_ASR_WINDOWS
    artifact_module.MAX_TARGETED_ASR_WINDOWS = 1
    try:
        expect(
            artifact_module.TargetedASRArtifactLimitError,
            lambda: artifact_module.serialize_targeted_asr_artifact(original),
            "WINDOW_COUNT_BOUND_FAILS",
        )
    finally:
        artifact_module.MAX_TARGETED_ASR_WINDOWS = old_window_limit

    production_source = Path(artifact_module.__file__).read_text(
        encoding="utf-8",
    )
    check(
        all(
            forbidden not in production_source
            for forbidden in (
                "open(",
                "urllib",
                "socket",
                "subprocess",
                "sqlite3",
                "faster_whisper",
                "WhisperModel",
                "Hermes",
                "JUR-750",
            )
        ),
        "ARTIFACT_MODULE_OWNS_NO_EXTERNAL_IO_OR_TITLE_LOGIC",
    )

    print("SMOKE_PASS_COUNT=" + str(passes))
    print("SMOKE_FAIL_COUNT=" + str(fails))


if __name__ == "__main__":
    main()
