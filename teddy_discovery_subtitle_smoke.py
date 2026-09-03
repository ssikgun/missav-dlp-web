from __future__ import annotations

from copy import deepcopy

from teddy_discovery_subtitle import (
    ACTION_ASR_REQUIRED,
    ACTION_SKIP_EXISTING_KO,
    ACTION_TEXT_SOURCE_READY,
    AmbiguousSubtitleSourceError,
    CanonicalHoldingValidationError,
    SubtitleCandidate,
    SubtitleCandidateValidationError,
    select_subtitle_source,
)


def require(condition: bool, marker: str):
    if not condition:
        raise AssertionError(marker)


def expect_raises(exception_type, callback, marker: str):
    try:
        callback()
    except exception_type:
        return

    raise AssertionError(marker)


def holding(
    *,
    dvd_id: str = "JUR-750",
    relative_path: str = "JUR/JUR-750/JUR-750.mp4",
    storage_root: str = "jav",
    parse_status: str = "MATCHED",
    present: object = 1,
):
    return {
        "dvd_id": dvd_id,
        "storage_root": storage_root,
        "relative_path": relative_path,
        "parse_status": parse_status,
        "present": present,
    }


def sibling(path: str, language=None):
    return SubtitleCandidate.sibling_text(
        path,
        language=language,
    )


def choose(candidates=(), *, metadata=None, expected_dvd_id="JUR-750"):
    return select_subtitle_source(
        holding() if metadata is None else metadata,
        expected_dvd_id,
        candidates,
    )


def main():
    ko_path = "JUR/JUR-750/JUR-750.ko.srt"
    ja_srt_path = "JUR/JUR-750/JUR-750.ja.srt"
    ja_vtt_path = "JUR/JUR-750/JUR-750.ja.vtt"
    en_srt_path = "JUR/JUR-750/JUR-750.en.srt"

    result = choose()
    require(
        result.target_ko_relative == ko_path,
        "CANONICAL_KO_TARGET",
    )
    require(
        result.dvd_id == "JUR-750",
        "CANONICAL_DVD_ID",
    )

    result = choose([sibling(ko_path)])
    require(
        result.action == ACTION_SKIP_EXISTING_KO
        and result.selected_language == "ko"
        and result.selected_source.relative_path == ko_path,
        "EXISTING_KO_SKIP",
    )

    result = choose([sibling(ja_srt_path)])
    require(
        result.action == ACTION_TEXT_SOURCE_READY
        and result.selected_language == "ja",
        "JA_SRT_READY",
    )

    result = choose([sibling(ja_vtt_path)])
    require(
        result.action == ACTION_TEXT_SOURCE_READY
        and result.selected_language == "ja",
        "JA_VTT_READY",
    )

    result = choose([sibling(en_srt_path)])
    require(
        result.action == ACTION_TEXT_SOURCE_READY
        and result.selected_language == "en",
        "EN_SRT_READY",
    )

    ja = sibling(ja_srt_path)
    en = sibling(en_srt_path)
    require(
        choose([en, ja]).selected_language == "ja"
        and choose([ja, en]).selected_language == "ja",
        "JA_WINS_OVER_EN_INPUT_ORDER",
    )

    require(
        choose([en, ja, sibling(ko_path)]).action
        == ACTION_SKIP_EXISTING_KO
        and choose([sibling(ko_path), ja, en]).action
        == ACTION_SKIP_EXISTING_KO,
        "KO_WINS_OVER_TEXT_INPUT_ORDER",
    )

    require(
        choose().action == ACTION_ASR_REQUIRED,
        "NO_TEXT_REQUIRES_ASR",
    )

    require(
        choose([sibling("JUR/JUR-750/JUR-750.srt", language="xx")]).action
        == ACTION_ASR_REQUIRED,
        "UNKNOWN_LANGUAGE_DOES_NOT_SUPPRESS_ASR",
    )

    expect_raises(
        SubtitleCandidateValidationError,
        lambda: choose([
            sibling("JUR/JUR-751/JUR-751.ja.srt"),
        ]),
        "WRONG_DVD_ID_SIBLING_REJECTED",
    )

    expect_raises(
        SubtitleCandidateValidationError,
        lambda: sibling("JUR/JUR-750/../JUR-750.ja.srt"),
        "PATH_TRAVERSAL_REJECTED",
    )

    expect_raises(
        SubtitleCandidateValidationError,
        lambda: sibling("/JUR/JUR-750/JUR-750.ja.srt"),
        "ABSOLUTE_PATH_REJECTED",
    )

    expect_raises(
        SubtitleCandidateValidationError,
        lambda: sibling(r"JUR\JUR-750\JUR-750.ja.srt"),
        "BACKSLASH_REJECTED",
    )

    expect_raises(
        SubtitleCandidateValidationError,
        lambda: sibling("JUR/JUR-750/.hidden/JUR-750.ja.srt"),
        "HIDDEN_COMPONENT_REJECTED",
    )

    for field, value, marker in (
        ("storage_root", "downloads", "WRONG_STORAGE_ROOT_REJECTED"),
        ("parse_status", "PARSED", "NON_MATCHED_STATUS_REJECTED"),
        ("present", 0, "NON_PRESENT_REJECTED"),
    ):
        invalid = holding()
        invalid[field] = value
        expect_raises(
            CanonicalHoldingValidationError,
            lambda invalid=invalid: choose(metadata=invalid),
            marker,
        )

    expect_raises(
        CanonicalHoldingValidationError,
        lambda: choose(
            metadata=holding(
                relative_path="JUR/JUR-750/not-the-dvd-id.mp4",
            )
        ),
        "NONCANONICAL_VIDEO_PATH_REJECTED",
    )

    expect_raises(
        SubtitleCandidateValidationError,
        lambda: sibling("JUR/JUR-750/JUR-750.ja.txt"),
        "UNSUPPORTED_SUBTITLE_EXTENSION_REJECTED",
    )

    unvalidated_external = SubtitleCandidate.external_text(
        "external://unvalidated/ja",
        language="ja",
        text_format="srt",
    )
    require(
        choose([unvalidated_external]).action == ACTION_ASR_REQUIRED,
        "UNVALIDATED_EXTERNAL_IGNORED",
    )

    validated_external = SubtitleCandidate.validated_external_text(
        "external://validated/ja",
        dvd_id="JUR-750",
        language="ja",
        text_format="vtt",
    )
    result = choose([validated_external])
    require(
        result.action == ACTION_TEXT_SOURCE_READY
        and result.selected_language == "ja"
        and result.selected_source == validated_external
        and result.selected_source.relative_path is None,
        "VALIDATED_EXACT_EXTERNAL_JA_READY",
    )

    expect_raises(
        AmbiguousSubtitleSourceError,
        lambda: choose([sibling(ja_srt_path), sibling(ja_vtt_path)]),
        "EQUAL_PRIORITY_AMBIGUITY_FAILS_CLOSED",
    )

    redirected = deepcopy(holding())
    redirected["target_ko_relative"] = "../../redirected.srt"
    result = choose(metadata=redirected)
    require(
        result.target_ko_relative == ko_path
        and result.action == ACTION_ASR_REQUIRED,
        "CALLER_CANNOT_REDIRECT_KO_TARGET",
    )

    other_title = holding(
        dvd_id="ABC-123",
        relative_path="ABC/ABC-123/ABC-123.mp4",
    )
    other_result = choose(
        [
            sibling("ABC/ABC-123/ABC-123.en.srt"),
        ],
        metadata=other_title,
        expected_dvd_id="ABC-123",
    )
    require(
        other_result.action == ACTION_TEXT_SOURCE_READY
        and other_result.selected_language == "en"
        and other_result.target_ko_relative
        == "ABC/ABC-123/ABC-123.ko.srt",
        "TITLE_INDEPENDENT_ROUTING",
    )

    print("STAGE11_SUBTITLE_SMOKE=PASS")


if __name__ == "__main__":
    main()
