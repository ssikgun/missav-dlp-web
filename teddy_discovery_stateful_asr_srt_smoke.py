"""Synthetic smoke tests for the stateful ASR SRT materializer."""

from teddy_discovery_asr_artifact import (
    ASRResult,
    ASRSegment,
    ASRSourceSnapshot,
)
from teddy_discovery_hermes_v2 import (
    HermesV2CueInput,
    HermesV2CueOutput,
)
from teddy_discovery_stateful_asr_srt import (
    StatefulASRSRTValidationError,
    materialize_stateful_asr_srt,
)
from teddy_discovery_stateful_translator import (
    StatefulSubtitlePackage,
    StatefulSubtitleResult,
    stateful_session_id_for_package,
)


def main():
    counts = {"pass": 0, "fail": 0}

    def check(condition: bool, marker: str):
        if not condition:
            counts["fail"] += 1
            raise AssertionError(marker)
        counts["pass"] += 1

    def expect(exception_type, callback, marker: str):
        try:
            callback()
        except exception_type:
            counts["pass"] += 1
            return
        except Exception as error:
            counts["fail"] += 1
            raise AssertionError(
                marker + ": wrong exception " + type(error).__name__
            ) from error

        counts["fail"] += 1
        raise AssertionError(marker)

    kept_ordinals = (
        1,
        2,
        4,
        5,
    )

    package = StatefulSubtitlePackage(
        schema_version=1,
        dvd_id="JUR-750",
        generation_key="filtered-v1",
        claim_token=1,
        cues=tuple(
            HermesV2CueInput(
                cue_id=f"asr-{ordinal:04d}",
                external_ja=None,
                stt_ja=f"ja-{ordinal}",
                en=None,
                before_context=(),
                after_context=(),
            )
            for ordinal in kept_ordinals
        ),
    )

    result = StatefulSubtitleResult(
        schema_version=1,
        dvd_id=package.dvd_id,
        generation_key=package.generation_key,
        claim_token=package.claim_token,
        session_id=stateful_session_id_for_package(package),
        cues=tuple(
            HermesV2CueOutput(
                cue_id=f"asr-{ordinal:04d}",
                repaired_ja=None,
                ko=f"ko-{ordinal}",
            )
            for ordinal in kept_ordinals
        ),
    )

    asr_result = ASRResult(
        source_snapshot=ASRSourceSnapshot(
            dvd_id="JUR-750",
            canonical_video_relative="JUR/JUR-750/JUR-750.mp4",
            source_size=1,
            source_mtime_ns=0,
        ),
        source_language="ja",
        segments=tuple(
            ASRSegment(
                start_ms=index * 1000,
                end_ms=(index * 1000) + 900,
                text=f"ja-{index + 1}",
            )
            for index in range(5)
        ),
        engine_version="synthetic-1",
    )

    materialized = materialize_stateful_asr_srt(
        package,
        result,
        asr_result,
    )

    wrong_title_asr_result = ASRResult(
        source_snapshot=ASRSourceSnapshot(
            dvd_id="ABC-123",
            canonical_video_relative="ABC/ABC-123/ABC-123.mp4",
            source_size=1,
            source_mtime_ns=0,
        ),
        source_language="ja",
        segments=asr_result.segments,
        engine_version="synthetic-1",
    )

    expect(
        StatefulASRSRTValidationError,
        lambda: materialize_stateful_asr_srt(
            package,
            result,
            wrong_title_asr_result,
        ),
        "WRONG_TITLE_ASR_TIMING_REJECTED",
    )


    check(
        materialized.source_indexes
        == (0, 1, 3, 4),
        "FILTERED_SOURCE_INDEX_SUBSET_PRESERVED",
    )

    check(
        materialized.artifact.cue_count == 4,
        "FILTERED_SRT_CUE_COUNT",
    )

    payload = materialized.artifact.payload.decode("utf-8")

    check(
        "00:00:00,000 --> 00:00:00,900" in payload
        and "00:00:01,000 --> 00:00:01,900" in payload
        and "00:00:03,000 --> 00:00:03,900" in payload
        and "00:00:04,000 --> 00:00:04,900" in payload,
        "ORIGINAL_ASR_TIMING_PRESERVED",
    )

    check(
        "ko-3" not in payload,
        "OMITTED_CUE_NOT_MATERIALIZED",
    )

    bad_package = StatefulSubtitlePackage(
        schema_version=1,
        dvd_id="BAD-ID",
        generation_key="filtered-v1",
        claim_token=1,
        cues=(
            HermesV2CueInput(
                cue_id="cue-0001",
                external_ja=None,
                stt_ja="ja",
                en=None,
                before_context=(),
                after_context=(),
            ),
        ),
    )

    bad_result = StatefulSubtitleResult(
        schema_version=1,
        dvd_id=bad_package.dvd_id,
        generation_key=bad_package.generation_key,
        claim_token=bad_package.claim_token,
        session_id=stateful_session_id_for_package(
            bad_package
        ),
        cues=(
            HermesV2CueOutput(
                cue_id="cue-0001",
                repaired_ja=None,
                ko="ko",
            ),
        ),
    )

    expect(
        StatefulASRSRTValidationError,
        lambda: materialize_stateful_asr_srt(
            bad_package,
            bad_result,
            asr_result,
        ),
        "NON_ASR_CUE_ID_REJECTED",
    )

    print("STATEFUL_ASR_SRT_SMOKE_PASS")
    print(
        "SYNTHETIC_TEST_PASS_COUNT="
        + str(counts["pass"])
    )
    print(
        "SYNTHETIC_TEST_FAIL_COUNT="
        + str(counts["fail"])
    )


if __name__ == "__main__":
    main()
