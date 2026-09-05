"""Offline smoke tests for the deterministic Stage11 ASR artifact."""

from __future__ import annotations

import json
from pathlib import Path

import teddy_discovery_asr_artifact as artifact_module
from teddy_discovery_asr import (
    ASRResult,
    ASRRuntimeIdentity,
    ASRSegment,
    ASRSourceSnapshot,
    ASRWord,
    LOCAL_CPU_MEDIUM_RUNTIME_IDENTITY,
    REMOTE_GPU_LARGE_V3_RUNTIME_IDENTITY,
)
from teddy_discovery_subtitle import validate_canonical_holding


def expect(error_type, callback, marker):
    try:
        callback()
    except error_type:
        return
    except Exception as error:
        raise AssertionError(
            marker + ": wrong exception " + type(error).__name__
        ) from error
    raise AssertionError(marker)


def video(dvd_id="JUR-750"):
    return validate_canonical_holding(
        {
            "dvd_id": dvd_id,
            "storage_root": "jav",
            "relative_path": f"{dvd_id.split('-', 1)[0]}/{dvd_id}/{dvd_id}.mp4",
            "parse_status": "MATCHED",
            "present": 1,
        },
        dvd_id,
    )


def snapshot(canonical_video, *, size=123, mtime_ns=456):
    return ASRSourceSnapshot.from_holding(
        canonical_video,
        source_size=size,
        source_mtime_ns=mtime_ns,
    )


def result_for(
    canonical_video,
    runtime_identity,
    *,
    two_segments=False,
):
    first_words = (
        ASRWord(100, 300, "こ"),
        ASRWord(300, 700, "んにちは世界"),
    )
    segments = [
        ASRSegment(
            0,
            1_000,
            "こんにちは世界",
            words=first_words,
        ),
    ]
    if two_segments:
        segments.append(ASRSegment(2_000, 3_000, "次の発話"))
    return ASRResult(
        source_snapshot=snapshot(canonical_video),
        source_language="ja",
        segments=tuple(segments),
        engine_version="1.2.1",
        engine=runtime_identity.engine,
        model=runtime_identity.model,
        device=runtime_identity.device,
        compute_type=runtime_identity.compute_type,
        cpu_threads=runtime_identity.cpu_threads,
        num_workers=runtime_identity.num_workers,
    )


def compact_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def main():
    title = video()
    cpu_result = result_for(title, LOCAL_CPU_MEDIUM_RUNTIME_IDENTITY)
    gpu_result = result_for(title, REMOTE_GPU_LARGE_V3_RUNTIME_IDENTITY)

    # A/B. Both approved runtime profiles round-trip through the same schema.
    cpu_raw = artifact_module.serialize_asr_result(cpu_result)
    gpu_raw = artifact_module.serialize_asr_result(gpu_result)
    assert isinstance(cpu_raw, bytes)
    assert artifact_module.parse_asr_result_bytes(cpu_raw) == cpu_result
    assert artifact_module.parse_asr_result_bytes(gpu_raw) == gpu_result
    parsed_gpu = artifact_module.parse_asr_result_bytes(gpu_raw)
    assert parsed_gpu.runtime_identity == REMOTE_GPU_LARGE_V3_RUNTIME_IDENTITY
    assert parsed_gpu.model == "large-v3"
    assert parsed_gpu.device == "cuda"
    assert parsed_gpu.compute_type == "float16"
    assert parsed_gpu.cpu_threads is None
    assert parsed_gpu.num_workers == 1
    parsed_cpu = artifact_module.parse_asr_result_bytes(cpu_raw)
    assert parsed_cpu.runtime_identity == LOCAL_CPU_MEDIUM_RUNTIME_IDENTITY
    assert parsed_cpu.model == "medium"
    assert parsed_cpu.device == "cpu"
    assert parsed_cpu.compute_type == "int8"
    assert parsed_cpu.cpu_threads == 8
    assert parsed_cpu.num_workers == 1

    # C/D. Serialization is byte deterministic, UTF-8, compact, and has no
    # wall-clock or host-specific metadata.
    assert cpu_raw == artifact_module.serialize_asr_result(cpu_result)
    assert gpu_raw == artifact_module.serialize_asr_result(gpu_result)
    assert not cpu_raw.endswith(b"\n")
    assert "こんにちは世界".encode("utf-8") in cpu_raw
    assert b"hostname" not in cpu_raw
    assert b"timestamp" not in cpu_raw

    decoded = json.loads(cpu_raw.decode("utf-8"))
    assert list(decoded) == [
        "schema_version",
        "source_snapshot",
        "source_language",
        "engine_version",
        "runtime_identity",
        "segments",
    ]
    assert decoded["source_snapshot"] == {
        "dvd_id": "JUR-750",
        "canonical_video_relative": "JUR/JUR-750/JUR-750.mp4",
        "source_size": 123,
        "source_mtime_ns": 456,
    }
    assert decoded["segments"][0]["words"] == [
        {"start_ms": 100, "end_ms": 300, "text": "こ"},
        {"start_ms": 300, "end_ms": 700, "text": "んにちは世界"},
    ]

    # E/F. Exact source snapshot matching succeeds; any provenance drift fails.
    assert artifact_module.require_matching_asr_source(
        cpu_result,
        snapshot(title),
    ) is cpu_result
    expect(
        artifact_module.ASRArtifactValidationError,
        lambda: artifact_module.require_matching_asr_source(
            cpu_result,
            snapshot(title, size=124),
        ),
        "SOURCE_SIZE_MISMATCH",
    )
    expect(
        artifact_module.ASRArtifactValidationError,
        lambda: artifact_module.require_matching_asr_source(
            cpu_result,
            snapshot(video("ABC-123")),
        ),
        "SOURCE_ID_MISMATCH",
    )

    # G. Input type, empty/oversized input, encoding, JSON, schema, and exact
    # key-set failures are all fail-closed.
    expect(
        artifact_module.ASRArtifactValidationError,
        lambda: artifact_module.parse_asr_result_bytes(bytearray(cpu_raw)),
        "NON_BYTES",
    )
    expect(
        artifact_module.ASRArtifactValidationError,
        lambda: artifact_module.parse_asr_result_bytes(b""),
        "EMPTY",
    )
    old_limit = artifact_module.MAX_ASR_ARTIFACT_BYTES
    artifact_module.MAX_ASR_ARTIFACT_BYTES = 8
    try:
        expect(
            artifact_module.ASRArtifactLimitError,
            lambda: artifact_module.parse_asr_result_bytes(cpu_raw),
            "OVERSIZED",
        )
        expect(
            artifact_module.ASRArtifactLimitError,
            lambda: artifact_module.serialize_asr_result(cpu_result),
            "SERIALIZED_OVERSIZED",
        )
    finally:
        artifact_module.MAX_ASR_ARTIFACT_BYTES = old_limit
    expect(
        artifact_module.ASRArtifactValidationError,
        lambda: artifact_module.parse_asr_result_bytes(b"\xff"),
        "INVALID_UTF8",
    )
    expect(
        artifact_module.ASRArtifactValidationError,
        lambda: artifact_module.parse_asr_result_bytes(b"{not-json"),
        "MALFORMED_JSON",
    )

    def mutated_payload(mutator, *, raw=cpu_raw):
        value = json.loads(raw.decode("utf-8"))
        mutator(value)
        return compact_json(value)

    expect(
        artifact_module.ASRArtifactValidationError,
        lambda: artifact_module.parse_asr_result_bytes(
            mutated_payload(lambda value: value.update(schema_version=2))
        ),
        "SCHEMA_MISMATCH",
    )
    expect(
        artifact_module.ASRArtifactValidationError,
        lambda: artifact_module.parse_asr_result_bytes(
            mutated_payload(lambda value: value.pop("segments"))
        ),
        "MISSING_TOP_LEVEL_KEY",
    )
    expect(
        artifact_module.ASRArtifactValidationError,
        lambda: artifact_module.parse_asr_result_bytes(
            mutated_payload(lambda value: value.update(extra=True))
        ),
        "EXTRA_TOP_LEVEL_KEY",
    )
    expect(
        artifact_module.ASRArtifactValidationError,
        lambda: artifact_module.parse_asr_result_bytes(
            mutated_payload(
                lambda value: value["runtime_identity"].update(model="small")
            )
        ),
        "UNKNOWN_RUNTIME_PROFILE",
    )
    expect(
        artifact_module.ASRArtifactValidationError,
        lambda: artifact_module.parse_asr_result_bytes(
            mutated_payload(
                lambda value: value["segments"][0].update(start_ms="zero")
            )
        ),
        "MALFORMED_TIMESTAMP",
    )

    # H. Existing ASR constructors reapply nonmonotonic, word-boundary, text,
    # and zero-segment invariants during artifact parsing.
    nonmonotonic = ASRResult(
        source_snapshot=snapshot(title),
        source_language="ja",
        segments=(
            ASRSegment(1_000, 2_000, "첫 번째"),
            ASRSegment(3_000, 4_000, "두 번째"),
        ),
        engine_version="1.2.1",
    )
    nonmonotonic_raw = artifact_module.serialize_asr_result(nonmonotonic)
    expect(
        artifact_module.ASRArtifactValidationError,
        lambda: artifact_module.parse_asr_result_bytes(
            mutated_payload(
                lambda value: value["segments"][1].update(start_ms=500),
                raw=nonmonotonic_raw,
            )
        ),
        "NONMONOTONIC_SEGMENTS",
    )
    assert nonmonotonic_raw
    expect(
        artifact_module.ASRArtifactValidationError,
        lambda: artifact_module.parse_asr_result_bytes(
            mutated_payload(
                lambda value: value["segments"][0]["words"][0].update(end_ms=1_001)
            )
        ),
        "WORD_OUTSIDE_SEGMENT",
    )
    expect(
        artifact_module.ASRArtifactValidationError,
        lambda: artifact_module.parse_asr_result_bytes(
            mutated_payload(
                lambda value: value["segments"][0].update(text="bad\u0000text")
            )
        ),
        "CONTROL_CHARACTER",
    )
    expect(
        artifact_module.ASRArtifactValidationError,
        lambda: artifact_module.parse_asr_result_bytes(
            mutated_payload(
                lambda value: value["segments"][0].update(text=" padded ")
            )
        ),
        "NORMALIZATION_NOT_REPAIR",
    )
    expect(
        artifact_module.ASRArtifactValidationError,
        lambda: artifact_module.parse_asr_result_bytes(
            mutated_payload(lambda value: value.update(source_language="en"))
        ),
        "NON_JAPANESE_SOURCE",
    )
    expect(
        artifact_module.ASRArtifactValidationError,
        lambda: artifact_module.parse_asr_result_bytes(
            mutated_payload(
                lambda value: value["source_snapshot"].update(source_size=0)
            )
        ),
        "MALFORMED_SOURCE_SNAPSHOT",
    )

    old_segment_limit = artifact_module.MAX_ASR_SEGMENTS
    artifact_module.MAX_ASR_SEGMENTS = 1
    try:
        expect(
            artifact_module.ASRArtifactLimitError,
            lambda: artifact_module.parse_asr_result_bytes(
                mutated_payload(
                    lambda value: value["segments"].append(
                        value["segments"][0].copy()
                    )
                )
            ),
            "TOO_MANY_SEGMENTS",
        )
    finally:
        artifact_module.MAX_ASR_SEGMENTS = old_segment_limit

    empty_segments = mutated_payload(lambda value: value.update(segments=[]))
    expect(
        artifact_module.ASRArtifactValidationError,
        lambda: artifact_module.parse_asr_result_bytes(empty_segments),
        "ZERO_SEGMENTS",
    )

    # I. The parser is pure: no filesystem/network/model ownership appears in
    # its production source, and the source snapshot helper performs equality
    # only.
    production_source = Path(artifact_module.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "open(",
        "urllib",
        "socket",
        "faster_whisper",
        "WhisperModel",
        "subprocess",
        "sqlite3",
        "jellyfin",
    ):
        assert forbidden not in production_source, "FORBIDDEN_" + forbidden

    # The parser uses the approved runtime constructor rather than arbitrary
    # profile strings; this also keeps the import surface explicit in smoke.
    assert isinstance(cpu_result.runtime_identity, ASRRuntimeIdentity)
    assert isinstance(gpu_result.runtime_identity, ASRRuntimeIdentity)
    print("STAGE11_ASR_ARTIFACT_SMOKE=PASS")


if __name__ == "__main__":
    main()
