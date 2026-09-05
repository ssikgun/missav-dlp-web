from __future__ import annotations

from dataclasses import FrozenInstanceError
import hashlib
from pathlib import Path

import teddy_discovery_subtitle_pipeline as pipeline_module
from teddy_discovery_asr import (
    ASRResult,
    ASRSegment,
    ASRSourceSnapshot,
)
from teddy_discovery_ko_srt import (
    GENERATED_SRT_READY,
    generate_korean_srt,
)
from teddy_discovery_subtitle import (
    ACTION_TEXT_SOURCE_READY,
    CanonicalVideoHolding,
    SOURCE_KIND_VALIDATED_EXTERNAL_TEXT,
    SubtitleCandidate,
    SubtitleSelectionResult,
    validate_canonical_holding,
)
from teddy_discovery_subtitle_publish import (
    SUBTITLE_PUBLISHED,
    SUBTITLE_SKIPPED_EXISTING_KO,
    SubtitlePublishCollisionError,
    SubtitlePublishResult,
)
from teddy_discovery_subtitle_text import (
    SubtitleCue,
    SubtitleParseError,
)
from teddy_discovery_translation import (
    TRANSLATION_ACCEPTED,
    TRANSLATION_OMITTED,
    TranslationOutcome,
)


def expect(error_type, callback, marker: str):
    try:
        callback()
    except error_type:
        return
    except Exception as error:
        raise AssertionError(
            marker + ": wrong exception " + type(error).__name__
        ) from error
    raise AssertionError(marker)


def require(condition: bool, marker: str):
    if not condition:
        raise AssertionError(marker)


def video(
    dvd_id: str = "JUR-750",
) -> CanonicalVideoHolding:
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


def srt_payload(*cues: tuple[int, int, str]) -> bytes:
    blocks = []
    for index, (start_ms, end_ms, text) in enumerate(cues, start=1):
        start_seconds, start_milliseconds = divmod(start_ms, 1000)
        end_seconds, end_milliseconds = divmod(end_ms, 1000)
        start_hours, start_seconds = divmod(start_seconds, 3600)
        end_hours, end_seconds = divmod(end_seconds, 3600)
        start_minutes, start_seconds = divmod(start_seconds, 60)
        end_minutes, end_seconds = divmod(end_seconds, 60)
        blocks.append(
            "\n".join(
                (
                    str(index),
                    (
                        f"{start_hours:02d}:{start_minutes:02d}:"
                        f"{start_seconds:02d},{start_milliseconds:03d}"
                        " --> "
                        f"{end_hours:02d}:{end_minutes:02d}:"
                        f"{end_seconds:02d},{end_milliseconds:03d}"
                    ),
                    text,
                )
            )
        )
    return ("\n\n".join(blocks) + "\n").encode("utf-8")


def vtt_payload(*cues: tuple[int, int, str]) -> bytes:
    def timestamp(milliseconds: int) -> str:
        seconds, milliseconds = divmod(milliseconds, 1000)
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        return (
            f"{hours:02d}:{minutes:02d}:{seconds:02d}."
            f"{milliseconds:03d}"
        )

    blocks = [
        f"{timestamp(start_ms)} --> {timestamp(end_ms)}\n{text}"
        for start_ms, end_ms, text in cues
    ]
    return ("WEBVTT\n\n" + "\n\n".join(blocks) + "\n").encode(
        "utf-8"
    )


def sibling(path: str) -> SubtitleCandidate:
    return SubtitleCandidate.sibling_text(path)


class FakeSubtitleReader:
    def __init__(self, candidates, payloads=None):
        self.candidates = tuple(candidates)
        self.payloads = {} if payloads is None else dict(payloads)
        self.list_calls = []
        self.read_calls = []

    def list_subtitle_candidates(self, canonical_video):
        self.list_calls.append(canonical_video)
        return self.candidates

    def read_subtitle_bytes(self, canonical_video, candidate):
        self.read_calls.append((canonical_video, candidate))
        return self.payloads[candidate.relative_path]


class FakeTranslator:
    def __init__(self, *, ko_text="번역된 한국어", omit=False):
        self.ko_text = ko_text
        self.omit = omit
        self.calls = []

    def __call__(self, cue):
        self.calls.append(cue)
        if self.omit:
            return TranslationOutcome(
                cue=cue,
                action=TRANSLATION_OMITTED,
                attempts=1,
                ko_text=None,
                reason="invalid_ko",
            )
        return TranslationOutcome(
            cue=cue,
            action=TRANSLATION_ACCEPTED,
            attempts=1,
            ko_text=self.ko_text,
            reason=None,
        )


class FakeASRTranscriber:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def __call__(self, canonical_video):
        self.calls.append(canonical_video)
        return self.result


class FakePublisher:
    def __init__(self, *, state=SUBTITLE_PUBLISHED, mismatch=None, error=None):
        self.state = state
        self.mismatch = mismatch
        self.error = error
        self.calls = []

    def publish_korean_srt(
        self,
        *,
        canonical_video,
        artifact,
        target_relative,
    ):
        self.calls.append(
            {
                "canonical_video": canonical_video,
                "artifact": artifact,
                "target_relative": target_relative,
            }
        )
        if self.error is not None:
            raise self.error

        target = target_relative
        sha256 = artifact.sha256
        byte_size = artifact.byte_size
        if self.mismatch == "target":
            target = "JUR/JUR-750/JUR-750.ko.srt"
            if target == target_relative:
                target = "ABC/ABC-123/ABC-123.ko.srt"
        elif self.mismatch == "sha256":
            sha256 = hashlib.sha256(b"different").hexdigest()
        elif self.mismatch == "byte_size":
            byte_size += 1

        return SubtitlePublishResult(
            state=self.state,
            target_relative=target,
            sha256=sha256,
            byte_size=byte_size,
        )


def asr_result(canonical_video: CanonicalVideoHolding) -> ASRResult:
    return ASRResult(
        source_snapshot=ASRSourceSnapshot.from_holding(
            canonical_video,
            source_size=123,
            source_mtime_ns=456,
        ),
        source_language="ja",
        segments=(
            ASRSegment(
                start_ms=4_321,
                end_ms=5_678,
                text="聞こえます",
            ),
        ),
        engine_version="smoke",
    )


def dependencies(
    *,
    reader,
    ja=None,
    en=None,
    asr=None,
    publisher=None,
):
    return dict(
        canonical_video=video(),
        subtitle_reader=reader,
        translate_ja_cue=ja or FakeTranslator(),
        translate_en_cue=en or FakeTranslator(ko_text="영어 번역"),
        asr_transcriber=asr or FakeASRTranscriber(asr_result(video())),
        publisher=publisher or FakePublisher(),
    )


def run(**kwargs):
    return pipeline_module.run_subtitle_pipeline(**kwargs)


def main():
    target = "JUR/JUR-750/JUR-750.ko.srt"
    ja_path = "JUR/JUR-750/JUR-750.ja.srt"
    ja_vtt_path = "JUR/JUR-750/JUR-750.ja.vtt"
    en_path = "JUR/JUR-750/JUR-750.en.srt"
    en_vtt_path = "JUR/JUR-750/JUR-750.en.vtt"

    # A. Existing KO is parsed and terminates before every downstream call.
    existing_payload = srt_payload((1_000, 2_000, "기존 한국어"))
    existing_reader = FakeSubtitleReader(
        [sibling(target)],
        {target: existing_payload},
    )
    existing_ja = FakeTranslator()
    existing_en = FakeTranslator(ko_text="영어 번역")
    existing_asr = FakeASRTranscriber(asr_result(video()))
    existing_publisher = FakePublisher()
    result = run(
        **dependencies(
            reader=existing_reader,
            ja=existing_ja,
            en=existing_en,
            asr=existing_asr,
            publisher=existing_publisher,
        )
    )
    require(result.state == pipeline_module.PIPELINE_EXISTING_KO, "EXISTING_KO_STATE")
    require(result.source_route == pipeline_module.SOURCE_ROUTE_EXISTING_KO, "EXISTING_KO_ROUTE")
    require(result.source_language == "ko", "EXISTING_KO_LANGUAGE")
    require(result.target_relative == target, "EXISTING_KO_TARGET")
    require(result.cue_count == 1, "EXISTING_KO_CUE_COUNT")
    require(result.sha256 == hashlib.sha256(existing_payload).hexdigest(), "EXISTING_KO_HASH")
    require(result.byte_size == len(existing_payload), "EXISTING_KO_SIZE")
    require(len(existing_reader.list_calls) == 1, "EXISTING_KO_INVENTORY_ONCE")
    require(len(existing_reader.read_calls) == 1, "EXISTING_KO_READ_ONCE")
    require(not existing_ja.calls and not existing_en.calls, "EXISTING_KO_NO_TRANSLATION")
    require(not existing_asr.calls, "EXISTING_KO_NO_ASR")
    require(not existing_publisher.calls, "EXISTING_KO_NO_PUBLISH")

    # B. A malformed selected KO does not fall back to ASR.
    malformed_reader = FakeSubtitleReader([sibling(target)], {target: b"not an srt"})
    malformed_asr = FakeASRTranscriber(asr_result(video()))
    expect(
        SubtitleParseError,
        lambda: run(
            **dependencies(
                reader=malformed_reader,
                asr=malformed_asr,
            )
        ),
        "MALFORMED_EXISTING_KO_FAILS",
    )
    require(not malformed_asr.calls, "MALFORMED_EXISTING_KO_NO_ASR")

    # C/D. JA SRT and VTT use the selected candidate's actual format and the
    # parsed SubtitleCue tuple directly.
    for path, payload, marker in (
        (
            ja_path,
            srt_payload((1_234, 5_678, "こんにちは。")),
            "JA_SRT",
        ),
        (
            ja_vtt_path,
            vtt_payload((1_234, 5_678, "こんにちは。")),
            "JA_VTT",
        ),
    ):
        reader = FakeSubtitleReader([sibling(path)], {path: payload})
        ja = FakeTranslator(ko_text="안녕하세요.")
        publisher = FakePublisher()
        result = run(
            **dependencies(
                reader=reader,
                ja=ja,
                publisher=publisher,
            )
        )
        require(result.state == pipeline_module.PIPELINE_PUBLISHED, marker + "_PUBLISHED")
        require(result.source_route == pipeline_module.SOURCE_ROUTE_TEXT_JA, marker + "_ROUTE")
        require(result.source_language == "ja", marker + "_LANGUAGE")
        require(len(ja.calls) == 1, marker + "_JA_CALL")
        require(not reader.read_calls[0][1].relative_path.endswith(".txt"), marker + "_READ_CANDIDATE")
        require(reader.read_calls[0][1].text_format == path.rsplit(".", 1)[1], marker + "_FORMAT")
        require(len(publisher.calls) == 1, marker + "_PUBLISH_CALL")
        require(publisher.calls[0]["artifact"].state == GENERATED_SRT_READY, marker + "_ARTIFACT")
        require(ja.calls[0].index == 1, marker + "_INDEX")
        require(ja.calls[0].start_ms == 1_234 and ja.calls[0].end_ms == 5_678, marker + "_TIMING")
        require(ja.calls[0].target == "こんにちは。", marker + "_TEXT")

    # E/F. EN SRT and VTT select only the EN translator.
    for path, payload, marker in (
        (
            en_path,
            srt_payload((2_000, 3_000, "It's raining today.")),
            "EN_SRT",
        ),
        (
            en_vtt_path,
            vtt_payload((2_000, 3_000, "It's raining today.")),
            "EN_VTT",
        ),
    ):
        reader = FakeSubtitleReader([sibling(path)], {path: payload})
        ja = FakeTranslator(ko_text="잘못 선택된 일본어 경로")
        en = FakeTranslator(ko_text="오늘은 비가 오네요.")
        publisher = FakePublisher()
        result = run(
            **dependencies(
                reader=reader,
                ja=ja,
                en=en,
                publisher=publisher,
            )
        )
        require(result.state == pipeline_module.PIPELINE_PUBLISHED, marker + "_PUBLISHED")
        require(result.source_route == pipeline_module.SOURCE_ROUTE_TEXT_EN, marker + "_ROUTE")
        require(result.source_language == "en", marker + "_LANGUAGE")
        require(not ja.calls and len(en.calls) == 1, marker + "_TRANSLATOR_SELECTION")
        require(en.calls[0].target == "It's raining today.", marker + "_TARGET")
        require(len(publisher.calls) == 1, marker + "_PUBLISH")

    # O. Selection priority remains owned by the frozen selector.
    priority_reader = FakeSubtitleReader(
        [sibling(en_path), sibling(ja_path)],
        {
            en_path: srt_payload((1_000, 2_000, "English")),
            ja_path: srt_payload((1_000, 2_000, "日本語")),
        },
    )
    priority_ja = FakeTranslator(ko_text="일본어 우선")
    priority_en = FakeTranslator(ko_text="영어 후순위")
    run(
        **dependencies(
            reader=priority_reader,
            ja=priority_ja,
            en=priority_en,
        )
    )
    require(len(priority_ja.calls) == 1 and not priority_en.calls, "JA_PRIORITY_DELEGATED")
    require(priority_reader.read_calls[0][1].relative_path == ja_path, "JA_PRIORITY_READ")

    all_priority_reader = FakeSubtitleReader(
        [sibling(ja_path), sibling(en_path), sibling(target)],
        {
            target: existing_payload,
            ja_path: srt_payload((1_000, 2_000, "日本語")),
            en_path: srt_payload((1_000, 2_000, "English")),
        },
    )
    all_priority_ja = FakeTranslator()
    all_priority_en = FakeTranslator(ko_text="영어")
    all_priority_asr = FakeASRTranscriber(asr_result(video()))
    all_priority_publisher = FakePublisher()
    priority_result = run(
        **dependencies(
            reader=all_priority_reader,
            ja=all_priority_ja,
            en=all_priority_en,
            asr=all_priority_asr,
            publisher=all_priority_publisher,
        )
    )
    require(priority_result.state == pipeline_module.PIPELINE_EXISTING_KO, "KO_PRIORITY_DELEGATED")
    require(not all_priority_ja.calls and not all_priority_en.calls, "KO_PRIORITY_NO_TRANSLATION")
    require(not all_priority_asr.calls and not all_priority_publisher.calls, "KO_PRIORITY_NO_DOWNSTREAM")

    # G. ASR result is checked against exact title identity and its segments
    # are already route-compatible ASRSegment values.
    asr_reader = FakeSubtitleReader([])
    asr = FakeASRTranscriber(asr_result(video()))
    asr_ja = FakeTranslator(ko_text="들립니다.")
    asr_en = FakeTranslator(ko_text="wrong English")
    asr_publisher = FakePublisher()
    asr_pipeline_result = run(
        **dependencies(
            reader=asr_reader,
            ja=asr_ja,
            en=asr_en,
            asr=asr,
            publisher=asr_publisher,
        )
    )
    require(asr_pipeline_result.source_route == pipeline_module.SOURCE_ROUTE_ASR_JA, "ASR_ROUTE")
    require(asr_pipeline_result.source_language == "ja", "ASR_LANGUAGE")
    require(len(asr.calls) == 1 and len(asr_ja.calls) == 1, "ASR_CALLS")
    require(not asr_en.calls and len(asr_publisher.calls) == 1, "ASR_JA_TRANSLATOR_ONLY")
    require((asr_ja.calls[0].start_ms, asr_ja.calls[0].end_ms) == (4_321, 5_678), "ASR_TIMING")
    require(asr_ja.calls[0].target == "聞こえます", "ASR_SEGMENT_DIRECT")

    wrong_title = video("ABC-123")
    wrong_asr = FakeASRTranscriber(asr_result(wrong_title))
    wrong_ja = FakeTranslator()
    wrong_publisher = FakePublisher()
    expect(
        pipeline_module.SubtitlePipelineContractError,
        lambda: run(
            **dependencies(
                reader=FakeSubtitleReader([]),
                ja=wrong_ja,
                asr=wrong_asr,
                publisher=wrong_publisher,
            )
        ),
        "ASR_WRONG_TITLE_REJECTED",
    )
    require(not wrong_ja.calls and not wrong_publisher.calls, "ASR_WRONG_TITLE_NO_DOWNSTREAM")

    # P. An untagged sibling remains non-routable and therefore enters ASR;
    # pipeline never infers its language.
    untagged_path = "JUR/JUR-750/JUR-750.srt"
    untagged_asr = FakeASRTranscriber(asr_result(video()))
    untagged_reader = FakeSubtitleReader(
        [sibling(untagged_path)],
        {untagged_path: srt_payload((1_000, 2_000, "untagged"))},
    )
    untagged_result = run(
        **dependencies(
            reader=untagged_reader,
            asr=untagged_asr,
        )
    )
    require(untagged_result.source_route == pipeline_module.SOURCE_ROUTE_ASR_JA, "UNTAGGED_ASR_ROUTE")
    require(not untagged_reader.read_calls and len(untagged_asr.calls) == 1, "UNTAGGED_NOT_READ")

    # I. All source cues omitted by the frozen route produce no artifact and
    # never invoke the publisher.
    omitted_reader = FakeSubtitleReader(
        [sibling(ja_path)],
        {ja_path: srt_payload((1_000, 2_000, "ああああ"))},
    )
    omitted_ja = FakeTranslator(omit=True)
    omitted_publisher = FakePublisher()
    omitted_result = run(
        **dependencies(
            reader=omitted_reader,
            ja=omitted_ja,
            publisher=omitted_publisher,
        )
    )
    require(omitted_result.state == pipeline_module.PIPELINE_NO_KO_ARTIFACT, "NO_ARTIFACT_STATE")
    require(omitted_result.source_route == pipeline_module.SOURCE_ROUTE_TEXT_JA, "NO_ARTIFACT_ROUTE")
    require(omitted_result.cue_count == 0 and omitted_result.sha256 is None and omitted_result.byte_size == 0, "NO_ARTIFACT_METADATA")
    require(not omitted_ja.calls and not omitted_publisher.calls, "NO_ARTIFACT_NO_PUBLISH")

    # J. Publisher skip retains the actual upstream source route.
    skip_publisher = FakePublisher(state=SUBTITLE_SKIPPED_EXISTING_KO)
    skip_result = run(
        **dependencies(
            reader=FakeSubtitleReader([sibling(ja_path)], {ja_path: srt_payload((1_000, 2_000, "日本語"))}),
            publisher=skip_publisher,
        )
    )
    require(skip_result.state == pipeline_module.PIPELINE_SKIPPED_EXISTING_KO, "PUBLISH_SKIP_STATE")
    require(skip_result.source_route == pipeline_module.SOURCE_ROUTE_TEXT_JA, "PUBLISH_SKIP_ROUTE")

    # K/L. Cross-component publisher mismatches fail explicitly; lower-layer
    # collision errors propagate unchanged.
    mismatch_publisher = FakePublisher(mismatch="sha256")
    expect(
        pipeline_module.SubtitlePipelineContractError,
        lambda: run(
            **dependencies(
                reader=FakeSubtitleReader([sibling(ja_path)], {ja_path: srt_payload((1_000, 2_000, "日本語"))}),
                publisher=mismatch_publisher,
            )
        ),
        "PUBLISH_HASH_MISMATCH",
    )
    collision = SubtitlePublishCollisionError("collision")
    collision_publisher = FakePublisher(error=collision)
    expect(
        SubtitlePublishCollisionError,
        lambda: run(
            **dependencies(
                reader=FakeSubtitleReader([sibling(ja_path)], {ja_path: srt_payload((1_000, 2_000, "日本語"))}),
                publisher=collision_publisher,
            )
        ),
        "PUBLISH_COLLISION_PROPAGATES",
    )

    # Q. A selected external candidate is fail-closed; no invented payload
    # transport and no fallback to ASR.
    external = SubtitleCandidate.validated_external_text(
        "external-ja",
        dvd_id="JUR-750",
        language="ja",
        text_format="srt",
    )
    original_selector = pipeline_module.select_subtitle_source
    pipeline_module.select_subtitle_source = lambda *args, **kwargs: SubtitleSelectionResult(
        action=ACTION_TEXT_SOURCE_READY,
        dvd_id="JUR-750",
        canonical_video_relative="JUR/JUR-750/JUR-750.mp4",
        target_ko_relative=target,
        selected_source=external,
        selected_language="ja",
    )
    external_reader = FakeSubtitleReader([])
    external_asr = FakeASRTranscriber(asr_result(video()))
    try:
        expect(
            pipeline_module.SubtitlePipelineUnsupportedSourceError,
            lambda: run(
                **dependencies(
                    reader=external_reader,
                    asr=external_asr,
                )
            ),
            "EXTERNAL_SOURCE_FAILS_CLOSED",
        )
    finally:
        pipeline_module.select_subtitle_source = original_selector
    require(not external_reader.read_calls and not external_asr.calls, "EXTERNAL_NO_FALLBACK")
    require(external.source_kind == SOURCE_KIND_VALIDATED_EXTERNAL_TEXT, "EXTERNAL_KIND")

    # N. Inventory is exactly once per invocation and invalid dependency
    # contracts fail before any inventory call.
    invalid_reader = FakeSubtitleReader([])
    expect(
        pipeline_module.SubtitlePipelineValidationError,
        lambda: run(
            **dependencies(
                reader=invalid_reader,
            )
            | {"translate_en_cue": None},
        ),
        "INVALID_TRANSLATOR_REJECTED",
    )
    require(not invalid_reader.list_calls, "INVALID_DEP_NO_INVENTORY")

    # Omitted and accepted source-route identity is reflected only in compact
    # metadata; no dialogue/transcript fields exist in the result model.
    fields = set(pipeline_module.SubtitlePipelineResult.__dataclass_fields__)
    require(
        fields
        == {
            "state",
            "dvd_id",
            "source_route",
            "source_language",
            "target_relative",
            "cue_count",
            "sha256",
            "byte_size",
        },
        "RESULT_HAS_ONLY_OPERATIONAL_FIELDS",
    )
    expect(
        FrozenInstanceError,
        lambda: setattr(asr_pipeline_result, "state", "changed"),
        "RESULT_IMMUTABLE",
    )

    # Result invariant matrix.
    valid_result_values = {
        "state": pipeline_module.PIPELINE_PUBLISHED,
        "dvd_id": "JUR-750",
        "source_route": pipeline_module.SOURCE_ROUTE_TEXT_JA,
        "source_language": "ja",
        "target_relative": target,
        "cue_count": 1,
        "sha256": hashlib.sha256(b"artifact").hexdigest(),
        "byte_size": 8,
    }
    invalid_results = (
        {**valid_result_values, "state": "UNKNOWN"},
        {**valid_result_values, "source_route": pipeline_module.SOURCE_ROUTE_EXISTING_KO},
        {**valid_result_values, "state": pipeline_module.PIPELINE_EXISTING_KO, "source_route": pipeline_module.SOURCE_ROUTE_EXISTING_KO, "source_language": "en"},
        {**valid_result_values, "byte_size": 0},
        {**valid_result_values, "state": pipeline_module.PIPELINE_NO_KO_ARTIFACT, "source_route": pipeline_module.SOURCE_ROUTE_TEXT_JA, "source_language": "ja", "cue_count": 0, "sha256": valid_result_values["sha256"], "byte_size": 0},
        {**valid_result_values, "target_relative": "JUR/JUR-750/other.ko.srt"},
        {
            **valid_result_values,
            "dvd_id": "OTHER-ID",
            "target_relative": "OTHER/OTHER-ID/OTHER-ID.ko.srt",
        },
        {
            **valid_result_values,
            "dvd_id": "ABC-123",
            "target_relative": "OTHER/OTHER-ID/OTHER-ID.ko.srt",
        },
        {**valid_result_values, "sha256": "not-a-hash"},
        {**valid_result_values, "cue_count": -1},
    )
    for invalid in invalid_results:
        expect(
            pipeline_module.SubtitlePipelineValidationError,
            lambda invalid=invalid: pipeline_module.SubtitlePipelineResult(**invalid),
            "RESULT_INVARIANT_REJECTED",
        )

    production_source = Path(pipeline_module.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "teddy_discovery_completion_apply",
        "teddy_discovery_completion_runner",
        "sqlite3",
        "jellyfin",
        "os.unlink",
        "Path.unlink",
        "subprocess",
    ):
        require(forbidden not in production_source, "PIPELINE_OWNS_NO_" + forbidden.upper().replace(".", "_"))

    print("STAGE11_SUBTITLE_PIPELINE_SMOKE=PASS")


if __name__ == "__main__":
    main()
