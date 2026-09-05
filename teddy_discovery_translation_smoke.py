"""Offline fake-transport smoke tests for the Stage11 E4B boundary."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

from teddy_discovery_translation import (
    E4B_MODEL,
    E4B_ROLE,
    E4B_ROLE_EN,
    E4B_ROLE_JA,
    E4BTranslationAdapter,
    INVALID_KO_ACTION,
    MAX_TRANSLATION_RESPONSE_BYTES,
    MAX_TRANSLATION_RETRY,
    SYSTEM_INSTRUCTION,
    SYSTEM_INSTRUCTION_EN,
    SYSTEM_INSTRUCTION_JA,
    SUPPORTED_SOURCE_LANGUAGES,
    TRANSLATION_ACCEPTED,
    TRANSLATION_OMITTED,
    TranslationCue,
    TranslationOutcome,
    TranslationValidationError,
)


def expect(error_type, function):
    try:
        function()
    except error_type:
        return
    raise AssertionError("expected " + error_type.__name__)


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, endpoint, body, headers, timeout):
        assert isinstance(body, bytes)
        assert isinstance(headers, dict)
        self.calls.append(
            {
                "endpoint": endpoint,
                "body": json.loads(body.decode("utf-8")),
                "headers": dict(headers),
                "timeout": timeout,
            }
        )
        if not self.responses:
            raise AssertionError("fake transport called beyond its fixtures")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def response_from_assistant_content(content: str) -> bytes:
    return json.dumps(
        {
            "choices": [
                {
                    "message": {
                        "content": content,
                    },
                },
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")


def response_from_ko(ko: object, *, extra_key: object = None) -> bytes:
    value = {"ko": ko}
    if extra_key is not None:
        value["extra"] = extra_key
    return response_from_assistant_content(
        json.dumps(value, ensure_ascii=False)
    )


_SOURCE_LANGUAGE_UNSET = object()


def cue(
    *,
    target="こんにちは",
    before_context="前の台詞",
    after_context="次の台詞",
):
    return TranslationCue(
        index=17,
        start_ms=12_345,
        end_ms=13_456,
        target=target,
        before_context=before_context,
        after_context=after_context,
    )


def adapter_for(transport, *, source_language=_SOURCE_LANGUAGE_UNSET):
    values = {
        "base_url": "http://e4b.example:8080",
        "request_timeout_seconds": 12.5,
        "transport": transport,
    }
    if source_language is not _SOURCE_LANGUAGE_UNSET:
        values["source_language"] = source_language
    return E4BTranslationAdapter(**values)


def main():
    assert E4B_MODEL == "gemma-4-e4b-stage11"
    assert E4B_ROLE == "JA_TO_KO_TRANSLATION_ONLY"
    assert E4B_ROLE_JA == E4B_ROLE
    assert E4B_ROLE_EN == "EN_TO_KO_TRANSLATION_ONLY"
    assert SUPPORTED_SOURCE_LANGUAGES == frozenset({"ja", "en"})
    assert SYSTEM_INSTRUCTION_JA == SYSTEM_INSTRUCTION
    assert "일본어" in SYSTEM_INSTRUCTION_JA
    assert "STT" in SYSTEM_INSTRUCTION_JA
    assert "일본어" not in SYSTEM_INSTRUCTION_EN
    assert "STT" not in SYSTEM_INSTRUCTION_EN
    assert MAX_TRANSLATION_RETRY == 1
    assert INVALID_KO_ACTION == "OMIT_CUE"

    transport = FakeTransport([response_from_ko("자연스러운 한국어")])
    original = cue()
    default_adapter = adapter_for(transport)
    outcome = default_adapter.translate_cue(original)
    assert outcome.action == TRANSLATION_ACCEPTED
    assert outcome.attempts == 1
    assert outcome.ko_text == "자연스러운 한국어"
    assert outcome.reason is None
    assert outcome.cue is original
    assert default_adapter.source_language == "ja"
    assert default_adapter.role == E4B_ROLE_JA
    assert default_adapter.system_instruction == SYSTEM_INSTRUCTION
    assert (
        outcome.cue.index,
        outcome.cue.start_ms,
        outcome.cue.end_ms,
        outcome.cue.target,
    ) == (17, 12_345, 13_456, "こんにちは")
    assert adapter_for(
        FakeTransport([response_from_ko("한국어")])
    ).endpoint_url == "http://e4b.example:8080/v1/chat/completions"

    explicit_ja_transport = FakeTransport([response_from_ko("자연스러운 한국어")])
    explicit_ja_adapter = adapter_for(
        explicit_ja_transport,
        source_language="ja",
    )
    explicit_ja_outcome = explicit_ja_adapter.translate_cue(original)
    assert explicit_ja_outcome.action == TRANSLATION_ACCEPTED
    assert explicit_ja_adapter.source_language == "ja"
    assert explicit_ja_adapter.role == E4B_ROLE_JA
    assert explicit_ja_adapter.system_instruction == SYSTEM_INSTRUCTION_JA
    assert explicit_ja_transport.calls[0]["body"] == transport.calls[0]["body"]

    request = transport.calls[0]
    assert request["endpoint"] == "http://e4b.example:8080/v1/chat/completions"
    assert request["timeout"] == 12.5
    assert request["headers"]["Content-Type"] == "application/json"
    payload = request["body"]
    assert payload["model"] == "gemma-4-e4b-stage11"
    assert payload["temperature"] == 0
    assert payload["stream"] is False
    assert payload["response_format"]["type"] == "json_object"
    assert payload["response_format"]["schema"] == {
        "type": "object",
        "properties": {
            "ko": {
                "type": "string",
                "minLength": 1,
            },
        },
        "required": ["ko"],
        "additionalProperties": False,
    }
    assert "translation" not in json.dumps(payload, ensure_ascii=False)
    user_input = json.loads(payload["messages"][1]["content"])
    assert user_input == {
        "target": original.target,
        "before_context": original.before_context,
        "after_context": original.after_context,
    }
    assert set(user_input) == {"target", "before_context", "after_context"}
    for forbidden in (
        "index",
        "start_ms",
        "end_ms",
        "output_path",
        "source_language",
    ):
        assert forbidden not in user_input
        assert forbidden not in payload["messages"][1]["content"]
    assert "role" not in user_input

    # EN uses the same cue/result and wire contract with only its explicit
    # source-language system instruction changed.
    en_target = "It's raining today."
    en_transport = FakeTransport([response_from_ko("오늘은 비가 오네요.")])
    en_adapter = adapter_for(en_transport, source_language="en")
    en_cue = cue(
        target=en_target,
        before_context="Yesterday was sunny.",
        after_context="Bring an umbrella.",
    )
    en_outcome = en_adapter.translate_cue(en_cue)
    assert en_outcome.action == TRANSLATION_ACCEPTED
    assert en_outcome.attempts == 1
    assert en_outcome.ko_text == "오늘은 비가 오네요."
    assert en_outcome.cue is en_cue
    assert en_adapter.source_language == "en"
    assert en_adapter.role == E4B_ROLE_EN
    assert en_adapter.system_instruction == SYSTEM_INSTRUCTION_EN

    en_payload = en_transport.calls[0]["body"]
    assert en_payload["model"] == payload["model"] == E4B_MODEL
    assert en_payload["temperature"] == payload["temperature"] == 0
    assert en_payload["stream"] is payload["stream"] is False
    assert en_payload["response_format"] == payload["response_format"]
    assert en_payload["messages"][0]["role"] == payload["messages"][0]["role"] == "system"
    assert en_payload["messages"][0]["content"] == SYSTEM_INSTRUCTION_EN
    assert payload["messages"][0]["content"] == SYSTEM_INSTRUCTION
    assert en_payload["messages"][0]["content"] != payload["messages"][0]["content"]

    en_user_input = json.loads(en_payload["messages"][1]["content"])
    assert set(en_user_input) == {"target", "before_context", "after_context"}
    assert en_user_input == {
        "target": en_cue.target,
        "before_context": en_cue.before_context,
        "after_context": en_cue.after_context,
    }
    for forbidden in (
        "index",
        "start_ms",
        "end_ms",
        "output_path",
        "dvd_id",
        "source_language",
    ):
        encoded_en_payload = json.dumps(en_payload, ensure_ascii=False)
        assert forbidden not in en_user_input
        assert forbidden not in encoded_en_payload
    assert "role" not in en_user_input

    parity_cue = cue(
        target="shared source",
        before_context="shared before",
        after_context="shared after",
    )
    parity_ja_transport = FakeTransport([response_from_ko("공통 한국어")])
    parity_en_transport = FakeTransport([response_from_ko("공통 한국어")])
    adapter_for(parity_ja_transport).translate_cue(parity_cue)
    adapter_for(
        parity_en_transport,
        source_language="en",
    ).translate_cue(parity_cue)
    parity_ja_payload = parity_ja_transport.calls[0]["body"]
    parity_en_payload = parity_en_transport.calls[0]["body"]
    assert set(parity_ja_payload) == set(parity_en_payload)
    for field in ("model", "temperature", "stream", "response_format"):
        assert parity_ja_payload[field] == parity_en_payload[field]
    assert parity_ja_payload["messages"][1] == parity_en_payload["messages"][1]
    assert parity_ja_payload["messages"][0]["role"] == parity_en_payload["messages"][0]["role"]
    assert parity_ja_payload["messages"][0]["content"] == SYSTEM_INSTRUCTION
    assert parity_en_payload["messages"][0]["content"] == SYSTEM_INSTRUCTION_EN
    assert parity_ja_payload["messages"][0]["content"] != parity_en_payload["messages"][0]["content"]

    # Unknown languages, including Slice 1 aliases, fail during construction
    # and never reach the injected transport.
    for invalid_language in ("fr", "", None, "jpn", "japanese", "eng", "english"):
        invalid_language_transport = FakeTransport([])
        expect(
            TranslationValidationError,
            lambda invalid_language=invalid_language,
            invalid_language_transport=invalid_language_transport: adapter_for(
                invalid_language_transport,
                source_language=invalid_language,
            ),
        )
        assert invalid_language_transport.calls == []

    empty_context_transport = FakeTransport([response_from_ko("한국어")])
    empty_context_cue = cue(before_context="", after_context="")
    assert (
        adapter_for(empty_context_transport)
        .translate_cue(empty_context_cue)
        .action
        == TRANSLATION_ACCEPTED
    )

    no_network_transport = FakeTransport([])
    expect(
        TranslationValidationError,
        lambda: TranslationCue(
            index=1,
            start_ms=0,
            end_ms=1,
            target="",
        ),
    )
    assert no_network_transport.calls == []

    # The target/context contract is immutable and the timing owner is not
    # rewritten by translation.
    try:
        original.start_ms = 99
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError("TranslationCue must be frozen")

    first_invalid_then_valid = FakeTransport(
        [
            response_from_ko(""),
            response_from_ko("두 번째 번역"),
        ]
    )
    retry_outcome = adapter_for(first_invalid_then_valid).translate_cue(cue())
    assert retry_outcome.action == TRANSLATION_ACCEPTED
    assert retry_outcome.attempts == 2
    assert retry_outcome.ko_text == "두 번째 번역"
    assert len(first_invalid_then_valid.calls) == 2
    assert first_invalid_then_valid.calls[0]["body"] == first_invalid_then_valid.calls[1]["body"]

    two_invalid = FakeTransport(
        [response_from_ko("   "), response_from_ko("   ")]
    )
    omitted = adapter_for(two_invalid).translate_cue(cue())
    assert omitted.action == TRANSLATION_OMITTED
    assert omitted.attempts == 2
    assert omitted.ko_text is None
    assert omitted.reason == "invalid_ko"
    assert len(two_invalid.calls) == MAX_TRANSLATION_RETRY + 1

    mixed_script = FakeTransport([response_from_ko("日本語の名前을 자연스럽게")])
    mixed_outcome = adapter_for(mixed_script).translate_cue(cue())
    assert mixed_outcome.action == TRANSLATION_ACCEPTED

    exact_copy = FakeTransport(
        [response_from_ko("こんにちは"), response_from_ko("こんにちは")]
    )
    exact_copy_outcome = adapter_for(exact_copy).translate_cue(cue())
    assert exact_copy_outcome.action == TRANSLATION_OMITTED
    assert exact_copy_outcome.reason == "invalid_ko"

    en_retry = FakeTransport(
        [
            b"not-json",
            response_from_ko("두 번째 영어 번역"),
        ]
    )
    en_retry_outcome = adapter_for(
        en_retry,
        source_language="en",
    ).translate_cue(en_cue)
    assert en_retry_outcome.action == TRANSLATION_ACCEPTED
    assert en_retry_outcome.attempts == 2
    assert en_retry_outcome.ko_text == "두 번째 영어 번역"
    assert len(en_retry.calls) == MAX_TRANSLATION_RETRY + 1
    assert en_retry.calls[0]["body"]["messages"][0]["content"] == SYSTEM_INSTRUCTION_EN
    assert en_retry.calls[0]["body"]["messages"][1] == en_retry.calls[1]["body"]["messages"][1]

    en_both_invalid = FakeTransport([b"not-json", b"not-json"])
    en_omitted = adapter_for(
        en_both_invalid,
        source_language="en",
    ).translate_cue(en_cue)
    assert en_omitted.action == TRANSLATION_OMITTED
    assert en_omitted.attempts == MAX_TRANSLATION_RETRY + 1
    assert en_omitted.reason == "malformed_structured_response"

    en_invalid_responses = (
        b"not-json",
        response_from_assistant_content("not-json"),
        response_from_assistant_content(json.dumps({})),
        response_from_ko(""),
    )
    for invalid_response in en_invalid_responses:
        invalid_en_transport = FakeTransport([invalid_response, invalid_response])
        invalid_en_outcome = adapter_for(
            invalid_en_transport,
            source_language="en",
        ).translate_cue(en_cue)
        assert invalid_en_outcome.action == TRANSLATION_OMITTED
        assert invalid_en_outcome.attempts == MAX_TRANSLATION_RETRY + 1

    en_exact_copy = FakeTransport(
        [response_from_ko(en_target), response_from_ko(en_target)]
    )
    en_exact_copy_outcome = adapter_for(
        en_exact_copy,
        source_language="en",
    ).translate_cue(en_cue)
    assert en_exact_copy_outcome.action == TRANSLATION_OMITTED
    assert en_exact_copy_outcome.reason == "invalid_ko"

    invalid_responses = [
        b"not-json",
        response_from_assistant_content("not-json"),
        response_from_assistant_content(json.dumps({})),
        response_from_ko("한국어", extra_key="unexpected"),
        json.dumps({"choices": []}).encode("utf-8"),
        json.dumps({"choices": [{"message": {}}]}).encode("utf-8"),
        json.dumps({"choices": [{"message": {"content": []}}]}).encode("utf-8"),
    ]
    for invalid_response in invalid_responses:
        invalid_transport = FakeTransport([invalid_response, invalid_response])
        invalid_outcome = adapter_for(invalid_transport).translate_cue(cue())
        assert invalid_outcome.action == TRANSLATION_OMITTED
        assert invalid_outcome.attempts == 2

    oversized = b"x" * (MAX_TRANSLATION_RESPONSE_BYTES + 1)
    oversized_transport = FakeTransport([oversized, oversized])
    oversized_outcome = adapter_for(oversized_transport).translate_cue(cue())
    assert oversized_outcome.action == TRANSLATION_OMITTED
    assert oversized_outcome.reason == "response_limit_exceeded"

    transport_failure = FakeTransport(
        [OSError("synthetic transport failure"), response_from_ko("회복 번역")]
    )
    transport_outcome = adapter_for(transport_failure).translate_cue(cue())
    assert transport_outcome.action == TRANSLATION_ACCEPTED
    assert transport_outcome.attempts == 2

    # Directly constructed invalid output models cannot weaken the boundary.
    expect(
        TranslationValidationError,
        lambda: TranslationOutcome(
            cue=cue(),
            action=TRANSLATION_ACCEPTED,
            attempts=1,
            ko_text="",
            reason=None,
        ),
    )

    source_text = Path(__file__).with_name(
        "teddy_discovery_translation.py"
    ).read_text(encoding="utf-8")
    historical_canary_ip = ".".join(("192", "168", "1", "134"))
    assert historical_canary_ip not in source_text
    assert "gemma-4-e4b-stage11" in source_text
    assert "temperature\": 0" in source_text
    assert "stream\": False" in source_text
    assert "np." not in source_text
    assert "JUR-750" not in source_text
    assert "CP15F2AE" not in source_text

    print("STAGE11_TRANSLATION_SMOKE=PASS")


if __name__ == "__main__":
    main()
