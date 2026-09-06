from __future__ import annotations

import hashlib
from pathlib import Path

import teddy_discovery_subtitle_external as external_module
from teddy_discovery_subtitle import (
    SubtitleCandidate,
)
from teddy_discovery_subtitle_text import MAX_SUBTITLE_BYTES


def require(condition: bool, marker: str):
    if not condition:
        raise AssertionError(marker)


def expect_raises(exception_type, callback, marker: str):
    try:
        callback()
    except exception_type:
        return

    raise AssertionError(marker)


DVD_ID = "ABC-123"
SOURCE_URL = "https://cdn.example.test/subs/888/original.srt"
SRT_PAYLOAD = (
    "1\n"
    "00:00:01,000 --> 00:00:02,500\n"
    "source subtitle\n"
).encode("utf-8")


def external_candidate(
    *,
    source_url: str = SOURCE_URL,
    language: str = "ja",
    text_format: str = "srt",
    dvd_id: str = DVD_ID,
) -> SubtitleCandidate:
    return SubtitleCandidate.validated_external_text(
        source_url,
        dvd_id=dvd_id,
        language=language,
        text_format=text_format,
    )


def main():
    candidate = external_candidate()
    expected_sha256 = hashlib.sha256(SRT_PAYLOAD).hexdigest()

    # A raw fake fetch is the complete payload transport.  No filesystem or
    # network object is involved, and the candidate remains the existing
    # SubtitleCandidate identity.
    fetched_candidates = []

    def fake_payload_fetch(current_candidate):
        fetched_candidates.append(current_candidate)
        return SRT_PAYLOAD

    transport = external_module.ExternalSubtitleTransport(
        fake_payload_fetch,
    )
    fetched = transport.fetch_payload(
        dvd_id=DVD_ID,
        candidate=candidate,
    )
    require(
        fetched.candidate is candidate
        and fetched.dvd_id == DVD_ID
        and fetched.payload is SRT_PAYLOAD
        and fetched.byte_size == len(SRT_PAYLOAD)
        and fetched.sha256 == expected_sha256
        and fetched.is_translation_source
        and not fetched.is_supporting_evidence,
        "VALID_EXACT_JA_EXTERNAL_PAYLOAD",
    )
    require(
        fetched_candidates == [candidate],
        "INJECTED_PAYLOAD_FETCH_CALLED_ONCE",
    )

    parsed = fetched.parse()
    require(
        parsed.format == "srt"
        and len(parsed.cues) == 1
        and parsed.cues[0].text == "source subtitle"
        and parsed.source_sha256 == expected_sha256,
        "EXISTING_SUBTITLE_PARSER_BOUNDARY",
    )

    same_payload = external_module.ExternalSubtitlePayload.from_bytes(
        dvd_id=DVD_ID,
        candidate=candidate,
        payload=SRT_PAYLOAD,
    )
    require(
        same_payload.sha256 == fetched.sha256
        and same_payload.byte_size == fetched.byte_size,
        "PAYLOAD_SHA_STABLE",
    )

    expect_raises(
        external_module.ExternalSubtitleValidationError,
        lambda: external_module.ExternalSubtitlePayload(
            dvd_id="OTHER-456",
            candidate=candidate,
            payload=SRT_PAYLOAD,
        ),
        "EXACT_DVD_ID_MISMATCH_REJECTED",
    )
    expect_raises(
        external_module.ExternalSubtitleValidationError,
        lambda: external_module.ExternalSubtitlePayload(
            dvd_id=DVD_ID,
            candidate=SubtitleCandidate.sibling_text(
                "ABC/ABC-123/ABC-123.ja.srt",
            ),
            payload=SRT_PAYLOAD,
        ),
        "EXTERNAL_KIND_REQUIRED",
    )
    expect_raises(
        external_module.ExternalSubtitleValidationError,
        lambda: external_module.ExternalSubtitlePayload(
            dvd_id=DVD_ID,
            candidate=external_candidate(language="ko"),
            payload=SRT_PAYLOAD,
        ),
        "EXTERNAL_KO_REJECTED_AS_TRANSLATION_SOURCE",
    )
    expect_raises(
        external_module.ExternalSubtitleValidationError,
        lambda: external_module.ExternalSubtitlePayload(
            dvd_id=DVD_ID,
            candidate=candidate,
            payload=b"",
        ),
        "EMPTY_BYTES_REJECTED",
    )
    expect_raises(
        external_module.ExternalSubtitleValidationError,
        lambda: external_module.ExternalSubtitlePayload(
            dvd_id=DVD_ID,
            candidate=candidate,
            payload=b"x" * (MAX_SUBTITLE_BYTES + 1),
        ),
        "OVERSIZED_BYTES_REJECTED",
    )
    expect_raises(
        external_module.ExternalSubtitleValidationError,
        lambda: external_module.ExternalSubtitlePayload(
            dvd_id=DVD_ID,
            candidate=candidate,
            payload=SRT_PAYLOAD,
            sha256="0" * 64,
        ),
        "PAYLOAD_SHA_MISMATCH_REJECTED",
    )
    expect_raises(
        external_module.ExternalSubtitleValidationError,
        lambda: external_module.ExternalSubtitlePayload(
            dvd_id=DVD_ID,
            candidate=candidate,
            payload=bytearray(SRT_PAYLOAD),
        ),
        "NON_BYTES_REJECTED",
    )

    evidence_candidate = external_candidate(
        source_url="https://cdn.example.test/evidence/en.srt",
        language="en",
    )
    evidence_payload = external_module.ExternalSubtitlePayload(
        dvd_id=DVD_ID,
        candidate=evidence_candidate,
        payload=SRT_PAYLOAD,
    )
    require(
        not evidence_payload.is_translation_source
        and evidence_payload.is_supporting_evidence,
        "EN_IS_SUPPORTING_EVIDENCE_ONLY",
    )

    # The response's final URL is intentionally different from the requested
    # URL.  The source href's numeric directory is also intentionally
    # different from the detail-page numeric directory.
    requested_detail_url = "https://request.example/detail/111"
    final_detail_url = "https://final.example/detail/777/"
    detail_html = """
    <html><body>
      <table>
        <tr>
          <td>Japanese original</td>
          <td><a class="download" data-language="ja"
                 href="../../subs/888/original.srt">Download</a></td>
        </tr>
        <tr>
          <td>Korean generated</td>
          <td><a href="../../subs/999/generated.ko.srt">Korean</a></td>
        </tr>
      </table>
    </body></html>
    """
    detail_calls = []
    provider_payload_candidates = []

    def fake_detail_fetch(url):
        detail_calls.append(url)
        return external_module.SubtitleCatDetailPage(
            final_url=final_detail_url,
            html=detail_html,
        )

    def provider_payload_fetch(current_candidate):
        provider_payload_candidates.append(current_candidate)
        return SRT_PAYLOAD

    provider = external_module.SubtitleCatProvider(
        fetch_detail=fake_detail_fetch,
        payload_fetcher=provider_payload_fetch,
    )
    require(
        isinstance(provider, external_module.ExternalSubtitleProvider),
        "PROVIDER_ABSTRACTION_IMPLEMENTED",
    )
    provider_payload = provider.fetch_original_japanese_payload(
        dvd_id=DVD_ID,
        detail_url=requested_detail_url,
    )
    require(
        detail_calls == [requested_detail_url]
        and len(provider_payload_candidates) == 1,
        "INJECTED_DETAIL_AND_PAYLOAD_FETCHERS",
    )
    require(
        provider_payload.candidate.external_source_id
        == "https://final.example/subs/888/original.srt"
        and provider_payload.candidate.validated_for_dvd_id == DVD_ID
        and provider_payload.source_url
        == "https://final.example/subs/888/original.srt"
        and "111" not in provider_payload.candidate.external_source_id
        and "777" not in provider_payload.candidate.external_source_id
        and "888" in provider_payload.candidate.external_source_id,
        "ACTUAL_RELATIVE_HREF_RESOLVED_AGAINST_FINAL_URL",
    )
    require(
        provider_payload.parse().cues[0].text == "source subtitle",
        "PROVIDER_PAYLOAD_PASSES_EXISTING_PARSER",
    )

    # Regression: all language labels live in one shared container, while
    # language identity is available only from each anchor's local metadata.
    shared_language_html = """
    <section id="all-language-subtitles">
      All language subtitles: Japanese Korean English
      <a id="download_ja" onclick="show_voting('ja')"
         href="/subs/1528/TITLE.ja.whisperjav-ja.srt">Download</a>
      <a id="download_ko" onclick="show_voting('ko')"
         href="/subs/1528/TITLE.ja.whisperjav-ko.srt">Download</a>
      <a id="download_en" onclick="show_voting('en')"
         href="/subs/1528/TITLE.ja.whisperjav-en.srt">Download</a>
    </section>
    """
    shared_ja_url = external_module.find_subtitlecat_original_japanese_srt_url(
        shared_language_html,
        final_detail_url,
    )
    require(
        shared_ja_url
        == "https://final.example/subs/1528/TITLE.ja.whisperjav-ja.srt",
        "SHARED_LANGUAGE_CONTAINER_LOCAL_JA_ONLY",
    )
    require(
        "whisperjav-ko.srt" not in shared_ja_url
        and "whisperjav-en.srt" not in shared_ja_url,
        "SHARED_CONTAINER_KO_EN_NOT_CLASSIFIED_AS_JA",
    )

    unsupported_ar_with_ja_html = """
    <div id="all-language-subtitles">
      All language subtitles: Japanese Arabic
      <a id="download_ar" onclick="show_voting('ar')"
         href="/subs/1528/TITLE.ja.whisperjav-ar.srt">Download</a>
      <a id="download_ja" onclick="show_voting('ja')"
         href="/subs/1528/TITLE.ja.whisperjav-ja.srt">Download</a>
    </div>
    """
    require(
        external_module.find_subtitlecat_original_japanese_srt_url(
            unsupported_ar_with_ja_html,
            final_detail_url,
        )
        == "https://final.example/subs/1528/TITLE.ja.whisperjav-ja.srt",
        "UNSUPPORTED_AR_CONSISTENT_SIGNAL_SKIPPED",
    )

    unsupported_fr_with_ja_html = """
    <div id="all-language-subtitles">
      All language subtitles: Japanese French
      <a id="download_fr" onclick="show_voting('fr')"
         href="/subs/1528/TITLE.ja.whisperjav-fr.srt">Download</a>
      <a id="download_ja" onclick="show_voting('ja')"
         href="/subs/1528/TITLE.ja.whisperjav-ja.srt">Download</a>
    </div>
    """
    require(
        external_module.find_subtitlecat_original_japanese_srt_url(
            unsupported_fr_with_ja_html,
            final_detail_url,
        )
        == "https://final.example/subs/1528/TITLE.ja.whisperjav-ja.srt",
        "UNSUPPORTED_FR_CONSISTENT_SIGNAL_SKIPPED",
    )

    conflicting_local_html = """
    <div id="all-language-subtitles">
      Japanese Korean English
      <a id="download_ko" onclick="show_voting('ko')"
         href="/subs/1528/TITLE.ja.whisperjav-ja.srt">Download</a>
      <a id="download_ko" onclick="show_voting('ko')"
         href="/subs/1528/TITLE.ja.whisperjav-ko.srt">Download</a>
    </div>
    """
    expect_raises(
        external_module.SubtitleCatDetailError,
        lambda: external_module.find_subtitlecat_original_japanese_srt_url(
            conflicting_local_html,
            final_detail_url,
        ),
        "CONFLICTING_LOCAL_LANGUAGE_METADATA_FAILS_CLOSED",
    )

    id_href_conflict_html = """
    <div id="all-language-subtitles">
      Japanese Korean English
      <a id="download_ja" onclick="show_voting('ja')"
         href="/subs/1528/TITLE.ja.whisperjav-en.srt">Download</a>
    </div>
    """
    expect_raises(
        external_module.SubtitleCatDetailError,
        lambda: external_module.find_subtitlecat_original_japanese_srt_url(
            id_href_conflict_html,
            final_detail_url,
        ),
        "ID_JA_HREF_EN_CONFLICT_FAILS_CLOSED",
    )

    unsupported_href_ja_id_html = """
    <div id="all-language-subtitles">
      All language subtitles: Japanese Arabic
      <a id="download_ja" onclick="show_voting('ja')"
         href="/subs/1528/TITLE.ja.whisperjav-ar.srt">Download</a>
    </div>
    """
    expect_raises(
        external_module.SubtitleCatDetailError,
        lambda: external_module.find_subtitlecat_original_japanese_srt_url(
            unsupported_href_ja_id_html,
            final_detail_url,
        ),
        "UNSUPPORTED_HREF_JA_ID_CONFLICT_FAILS_CLOSED",
    )

    ja_href_unsupported_id_html = """
    <div id="all-language-subtitles">
      All language subtitles: Japanese Arabic
      <a id="download_ar" onclick="show_voting('ar')"
         href="/subs/1528/TITLE.ja.whisperjav-ja.srt">Download</a>
    </div>
    """
    expect_raises(
        external_module.SubtitleCatDetailError,
        lambda: external_module.find_subtitlecat_original_japanese_srt_url(
            ja_href_unsupported_id_html,
            final_detail_url,
        ),
        "JA_HREF_UNSUPPORTED_ID_CONFLICT_FAILS_CLOSED",
    )

    ambiguous_shared_html = """
    <div id="all-language-subtitles">
      Japanese Korean English
      <a id="download_ja" onclick="show_voting('ja')"
         href="/subs/1528/FIRST.ja.whisperjav-ja.srt">One</a>
      <a id="download_ja" onclick="show_voting('ja')"
         href="/subs/1528/SECOND.ja.whisperjav-ja.srt">Two</a>
      <a id="download_ko" onclick="show_voting('ko')"
         href="/subs/1528/TITLE.ja.whisperjav-ko.srt">Korean</a>
      <a id="download_en" onclick="show_voting('en')"
         href="/subs/1528/TITLE.ja.whisperjav-en.srt">English</a>
    </div>
    """
    expect_raises(
        external_module.SubtitleCatDetailError,
        lambda: external_module.find_subtitlecat_original_japanese_srt_url(
            ambiguous_shared_html,
            final_detail_url,
        ),
        "SHARED_CONTAINER_AMBIGUOUS_JA_FAILS_CLOSED",
    )

    relative_url = external_module.find_subtitlecat_original_japanese_srt_url(
        '<a data-language="ja" href="../files/42/original.srt">Original</a>',
        "https://final.example/detail/300/",
    )
    require(
        relative_url == "https://final.example/detail/files/42/original.srt",
        "RELATIVE_JA_HREF_RESOLUTION",
    )

    for html, marker in (
        (
            '<a data-language="en" href="/subs/1/english.srt">English</a>',
            "MISSING_JA_LINK_FAILS_CLOSED",
        ),
        (
            '<a data-language="ko" href="/subs/1/korean.srt">Korean</a>',
            "KO_ONLY_LINK_NOT_JA_SOURCE",
        ),
        (
            "".join(
                (
                    '<a data-language="ja" href="/subs/1/one.srt">One</a>',
                    '<a data-language="ja" href="/subs/2/two.srt">Two</a>',
                )
            ),
            "AMBIGUOUS_JA_LINKS_FAIL_CLOSED",
        ),
        (
            '<a data-language="ja" href="javascript:subtitle.ja.srt">Japanese</a>',
            "MALFORMED_NON_HTTP_URL_REJECTED",
        ),
        (
            '<a data-language="ja" href="file:///tmp/subtitle.ja.srt">Japanese</a>',
            "FILE_URL_REJECTED",
        ),
        (
            '<a data-language="ja" href="https://user:pass@example.test/ja.srt">Japanese</a>',
            "CREDENTIAL_URL_REJECTED",
        ),
    ):
        expect_raises(
            external_module.SubtitleCatDetailError,
            lambda html=html: external_module.find_subtitlecat_original_japanese_srt_url(
                html,
                final_detail_url,
            ),
            marker,
        )

    production_source = Path(external_module.__file__).read_text(
        encoding="utf-8",
    )
    require(
        "JUR-750" not in production_source
        and "parse_subtitle_bytes" in production_source
        and "urllib.request" not in production_source
        and "subprocess" not in production_source
        and "os." not in production_source,
        "GENERIC_OFFLINE_EXTERNAL_BOUNDARY",
    )

    print("STAGE11_SUBTITLE_EXTERNAL_SMOKE=PASS")


if __name__ == "__main__":
    main()
