"""Bounded Stage11 source-language-to-Korean translation adapter.

This module is the E4B boundary only.  It accepts one caller-owned timed cue
and explicitly supplied context, sends only semantic text to an
OpenAI-compatible endpoint, and returns either accepted Korean text or an
explicit omission outcome.  It does not parse subtitles, alter timing, write
files, publish media, or perform ASR.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import socket
import unicodedata
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlsplit, urlunsplit

from teddy_discovery_subtitle_text import MAX_CUE_TEXT_CHARS


E4B_MODEL = "gemma-4-e4b-stage11"
E4B_ROLE = "JA_TO_KO_TRANSLATION_ONLY"
E4B_ROLE_JA = E4B_ROLE
E4B_ROLE_EN = "EN_TO_KO_TRANSLATION_ONLY"
SUPPORTED_SOURCE_LANGUAGES = frozenset({"ja", "en"})
MAX_TRANSLATION_RETRY = 1
INVALID_KO_ACTION = "OMIT_CUE"

TRANSLATION_ACCEPTED = "ACCEPTED"
TRANSLATION_OMITTED = "OMITTED"

# This bound is derived from the existing per-cue text bound.  It leaves room
# for UTF-8/JSON envelope overhead without permitting an unbounded response.
MAX_TRANSLATION_RESPONSE_BYTES = MAX_CUE_TEXT_CHARS * 8
MAX_TRANSLATION_TEXT_CHARS = MAX_CUE_TEXT_CHARS


class TranslationError(Exception):
    """Base class for deterministic Stage11 translation failures."""


class TranslationValidationError(TranslationError):
    """Raised for invalid local configuration or cue identity."""


class TranslationLimitError(TranslationError):
    """Raised when a bounded translation request/response is too large."""


class TranslationTransportError(TranslationError):
    """Raised for bounded HTTP transport or API status failures."""


class TranslationResponseError(TranslationError):
    """Raised for malformed OpenAI-compatible structured responses."""


class TranslationContentError(TranslationError):
    """Raised for invalid Korean content returned by the model."""


SYSTEM_INSTRUCTION = """너는 일본어 영상용 한국어 자막 전문 번역가다.

목표:

* TARGET의 핵심 의미와 말투를 자연스러운 한국어 영상 자막으로 번역한다.
* 일본어 문장 구조를 그대로 옮긴 번역투보다 실제 한국어 대사처럼 자연스럽게 표현한다.
* 짧은 대사는 짧게 유지한다.
* 화자 관계에 맞는 존댓말/반말, 감정, 장난스러운 말투를 가능한 범위에서 유지한다.
* 성적 표현, 은어, 신체 표현을 임의로 순화하거나 검열하지 않는다.
* 원문보다 더 노골적으로 과장하지 않는다.

입력:

* target
* before_context
* after_context

규칙:

1. 오직 target만 번역한다.
2. before_context와 after_context는 의미와 말투 파악용 참고 자료다.
3. context의 내용을 번역 결과에 새로 추가하지 않는다.
4. TARGET에 약간의 STT 오인식이나 어색함이 있어도 핵심 의미가 분명하면 자연스럽게 정리한다.
5. 정확하지 않은 세부사항을 억지로 복원하거나 구체적인 내용을 새로 만들어내지 않는다.
6. 원문에 없는 이름, 숫자, 사건을 만들어내지 않는다.
7. 고유명사는 가능한 자연스러운 한국어 표기로 옮기되 다른 이름으로 바꾸지 않는다.
8. 의미가 불분명한 세부사항은 생략하거나 일반화할 수 있다.
9. ko 필드에는 반드시 자연스러운 한국어 번역문을 넣는다.
10. 일본어 TARGET을 그대로 복사해서는 안 된다.
"""

SYSTEM_INSTRUCTION_JA = SYSTEM_INSTRUCTION

SYSTEM_INSTRUCTION_EN = """너는 영어 영상 대사용 한국어 자막 전문 번역가다.

목표:

* English TARGET의 핵심 의미와 말투를 자연스러운 한국어 영상 자막으로 번역한다.
* 영어 문장 구조를 그대로 옮긴 번역투보다 실제 한국어 대사처럼 자연스럽게 표현한다.
* 짧은 대사는 짧게 유지한다.
* 화자 관계에 맞는 존댓말/반말, 감정, 장난스러운 말투를 가능한 범위에서 유지한다.
* 성적 표현, 은어, 신체 표현을 임의로 순화하거나 검열하지 않는다.
* 원문보다 더 노골적으로 과장하지 않는다.

입력:

* target
* before_context
* after_context

규칙:

1. 오직 target만 번역한다.
2. before_context와 after_context는 의미와 말투 파악용 참고 자료다.
3. context의 내용을 번역 결과에 새로 추가하지 않는다.
4. TARGET에 구어체, 생략, 어색한 표현이 있어도 핵심 의미가 분명하면 자연스럽게 정리한다.
5. 정확하지 않은 세부사항을 억지로 복원하거나 구체적인 내용을 새로 만들어내지 않는다.
6. 원문에 없는 이름, 숫자, 사건을 만들어내지 않는다.
7. 고유명사는 가능한 자연스러운 한국어 표기로 옮기되 다른 이름으로 바꾸지 않는다.
8. 의미가 불분명한 세부사항은 생략하거나 일반화할 수 있다.
9. ko 필드에는 반드시 자연스러운 한국어 번역문을 넣는다.
10. 정확한 영어 TARGET을 그대로 복사해서는 안 된다.
"""


def _translation_profile(
    source_language: object,
) -> tuple[str, str]:
    if (
        type(source_language) is not str
        or source_language not in SUPPORTED_SOURCE_LANGUAGES
    ):
        raise TranslationValidationError(
            "source_language must be exactly 'ja' or 'en'"
        )

    if source_language == "ja":
        return E4B_ROLE_JA, SYSTEM_INSTRUCTION_JA

    return E4B_ROLE_EN, SYSTEM_INSTRUCTION_EN


def _has_disallowed_control_characters(value: str) -> bool:
    return any(
        character not in {"\n", "\t"}
        and (
            ord(character) < 32
            or ord(character) == 127
            or unicodedata.category(character) == "Cc"
        )
        for character in value
    )


def _validate_text(
    value: object,
    *,
    field_name: str,
    allow_empty: bool,
) -> str:
    if not isinstance(value, str):
        raise TranslationValidationError(field_name + " must be a string")

    if not allow_empty and not value.strip():
        raise TranslationValidationError(field_name + " must not be empty")

    if len(value) > MAX_TRANSLATION_TEXT_CHARS:
        raise TranslationLimitError(
            field_name + " exceeds MAX_TRANSLATION_TEXT_CHARS"
        )

    if _has_disallowed_control_characters(value):
        raise TranslationValidationError(
            field_name + " contains a disallowed control character"
        )

    return value


def _validate_positive_int(value: object, *, field_name: str) -> int:
    if type(value) is not int or value <= 0:
        raise TranslationValidationError(
            field_name + " must be a positive integer"
        )
    return value


def _validate_nonnegative_int(value: object, *, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise TranslationValidationError(
            field_name + " must be a nonnegative integer"
        )
    return value


@dataclass(frozen=True)
class TranslationCue:
    """Caller-owned timing/source identity plus explicit context strings."""

    index: int
    start_ms: int
    end_ms: int
    target: str
    before_context: str = ""
    after_context: str = ""

    def __post_init__(self):
        _validate_positive_int(self.index, field_name="translation cue index")
        _validate_nonnegative_int(
            self.start_ms,
            field_name="translation cue start_ms",
        )
        _validate_positive_int(
            self.end_ms,
            field_name="translation cue end_ms",
        )
        if self.end_ms <= self.start_ms:
            raise TranslationValidationError(
                "translation cue end_ms must be greater than start_ms"
            )

        _validate_text(
            self.target,
            field_name="translation target",
            allow_empty=False,
        )
        _validate_text(
            self.before_context,
            field_name="before_context",
            allow_empty=True,
        )
        _validate_text(
            self.after_context,
            field_name="after_context",
            allow_empty=True,
        )


@dataclass(frozen=True)
class TranslationOutcome:
    """One cue's accepted/omitted result without workflow or publish state."""

    cue: TranslationCue
    action: str
    attempts: int
    ko_text: str | None
    reason: str | None

    def __post_init__(self):
        if not isinstance(self.cue, TranslationCue):
            raise TranslationValidationError("translation outcome cue is invalid")
        if (
            type(self.attempts) is not int
            or not 1 <= self.attempts <= MAX_TRANSLATION_RETRY + 1
        ):
            raise TranslationValidationError(
                "translation outcome attempts must be 1 or 2"
            )

        if self.action == TRANSLATION_ACCEPTED:
            if not isinstance(self.ko_text, str) or not self.ko_text.strip():
                raise TranslationValidationError(
                    "accepted translation must contain ko_text"
                )
            _validate_text(
                self.ko_text,
                field_name="ko_text",
                allow_empty=False,
            )
            if self.ko_text.strip() == self.cue.target.strip():
                raise TranslationValidationError(
                    "accepted translation cannot be an unchanged target"
                )
            if self.reason is not None:
                raise TranslationValidationError(
                    "accepted translation cannot contain a reason"
                )
        elif self.action == TRANSLATION_OMITTED:
            if self.ko_text is not None:
                raise TranslationValidationError(
                    "omitted translation cannot contain ko_text"
                )
            if not isinstance(self.reason, str) or not self.reason:
                raise TranslationValidationError(
                    "omitted translation must contain a reason"
                )
        else:
            raise TranslationValidationError("translation outcome action is invalid")


def _validate_timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TranslationValidationError(
            "request_timeout_seconds must be a positive finite number"
        )

    timeout = float(value)
    if not math.isfinite(timeout) or timeout <= 0:
        raise TranslationValidationError(
            "request_timeout_seconds must be a positive finite number"
        )
    return timeout


def _endpoint_from_base_url(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TranslationValidationError("base_url must be a nonempty URL")
    if _has_disallowed_control_characters(value):
        raise TranslationValidationError("base_url contains a control character")

    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise TranslationValidationError(
            "base_url must use an explicit HTTP or HTTPS host"
        )
    if parsed.username is not None or parsed.password is not None:
        raise TranslationValidationError(
            "base_url must not contain credentials"
        )
    if parsed.query or parsed.fragment:
        raise TranslationValidationError(
            "base_url must not contain a query or fragment"
        )

    path = parsed.path.rstrip("/")
    if not path.endswith("/v1/chat/completions"):
        # A trusted service base path is allowed; the API route is fixed here.
        path += "/v1/chat/completions"

    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _response_format() -> dict[str, object]:
    return {
        "type": "json_object",
        "schema": {
            "type": "object",
            "properties": {
                "ko": {
                    "type": "string",
                    "minLength": 1,
                },
            },
            "required": ["ko"],
            "additionalProperties": False,
        },
    }


def _request_payload(
    cue: TranslationCue,
    *,
    system_instruction: str = SYSTEM_INSTRUCTION,
) -> dict[str, object]:
    # Timing/index/source-path data intentionally never enters this payload.
    semantic_input = {
        "target": cue.target,
        "before_context": cue.before_context,
        "after_context": cue.after_context,
    }
    return {
        "model": E4B_MODEL,
        "temperature": 0,
        "stream": False,
        "response_format": _response_format(),
        "messages": [
            {
                "role": "system",
                "content": system_instruction,
            },
            {
                "role": "user",
                "content": json.dumps(
                    semantic_input,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
        ],
    }


class _NoRedirectHandler(urllib_request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise TranslationTransportError("HTTP redirect is not permitted")


def _default_transport(
    endpoint_url: str,
    body: bytes,
    headers: dict[str, str],
    timeout: float,
) -> bytes:
    request = urllib_request.Request(
        endpoint_url,
        data=body,
        headers=headers,
        method="POST",
    )
    opener = urllib_request.build_opener(_NoRedirectHandler())

    try:
        with opener.open(request, timeout=timeout) as response:
            status = response.getcode()
            if type(status) is not int or not 200 <= status < 300:
                raise TranslationTransportError(
                    "translation API returned a non-success status"
                )

            payload = response.read(MAX_TRANSLATION_RESPONSE_BYTES + 1)
    except TranslationError:
        raise
    except (
        OSError,
        ValueError,
        TimeoutError,
        socket.timeout,
        urllib_error.URLError,
    ) as error:
        raise TranslationTransportError(
            "translation API request failed"
        ) from error

    if not isinstance(payload, bytes):
        raise TranslationTransportError(
            "translation API response body must be bytes"
        )
    if len(payload) > MAX_TRANSLATION_RESPONSE_BYTES:
        raise TranslationLimitError(
            "translation API response exceeds its byte bound"
        )
    return payload


def _decode_response_body(raw_body: object) -> object:
    if not isinstance(raw_body, bytes):
        raise TranslationResponseError("translation response body must be bytes")
    if len(raw_body) > MAX_TRANSLATION_RESPONSE_BYTES:
        raise TranslationLimitError(
            "translation response exceeds its byte bound"
        )
    try:
        return json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise TranslationResponseError(
            "translation response is not valid UTF-8 JSON"
        ) from error


def _extract_assistant_content(raw_body: object) -> str:
    decoded = _decode_response_body(raw_body)
    if not isinstance(decoded, dict):
        raise TranslationResponseError("translation response must be an object")

    choices = decoded.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise TranslationResponseError(
            "translation response must contain exactly one choice"
        )

    choice = choices[0]
    if not isinstance(choice, dict):
        raise TranslationResponseError("translation choice must be an object")
    message = choice.get("message")
    if not isinstance(message, dict):
        raise TranslationResponseError("translation message is missing")
    content = message.get("content")
    if not isinstance(content, str) or not content:
        raise TranslationResponseError(
            "translation assistant content is missing"
        )
    return content


def _validate_ko_content(content: str, *, target: str) -> str:
    try:
        decoded = json.loads(content)
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise TranslationResponseError(
            "assistant content is not valid JSON"
        ) from error

    if not isinstance(decoded, dict) or set(decoded) != {"ko"}:
        raise TranslationResponseError(
            "assistant JSON must contain exactly the ko field"
        )

    ko = decoded["ko"]
    if not isinstance(ko, str):
        raise TranslationContentError("ko must be a string")

    normalized = ko.strip()
    if not normalized:
        raise TranslationContentError("ko must not be empty")
    if len(normalized) > MAX_TRANSLATION_TEXT_CHARS:
        raise TranslationLimitError("ko exceeds its text bound")
    if _has_disallowed_control_characters(normalized):
        raise TranslationContentError("ko contains a disallowed control character")

    # This is intentionally an exact-copy guard, not a script/language heuristic.
    if normalized == target.strip():
        raise TranslationContentError("ko is an unchanged source target")

    return normalized


def _reason_code(error: TranslationError) -> str:
    if isinstance(error, TranslationTransportError):
        return "transport_or_api_failure"
    if isinstance(error, TranslationLimitError):
        return "response_limit_exceeded"
    if isinstance(error, TranslationContentError):
        return "invalid_ko"
    if isinstance(error, TranslationResponseError):
        return "malformed_structured_response"
    return "translation_failed"


class E4BTranslationAdapter:
    """One bounded E4B request with a maximum of one retry."""

    def __init__(
        self,
        *,
        base_url: str,
        request_timeout_seconds: int | float,
        transport=None,
        source_language: str = "ja",
    ):
        role, system_instruction = _translation_profile(source_language)

        if transport is not None and not callable(transport):
            raise TranslationValidationError("transport must be callable")

        self.endpoint_url = _endpoint_from_base_url(base_url)
        self.request_timeout_seconds = _validate_timeout(
            request_timeout_seconds
        )
        self._transport = transport or _default_transport
        self.source_language = source_language
        self.role = role
        self.system_instruction = system_instruction

    def translate_cue(self, cue: TranslationCue) -> TranslationOutcome:
        """Translate only cue.target and return an explicit cue outcome."""

        if not isinstance(cue, TranslationCue):
            raise TranslationValidationError(
                "translate_cue requires a TranslationCue"
            )

        payload = _request_payload(
            cue,
            system_instruction=self.system_instruction,
        )
        try:
            body = json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, UnicodeError) as error:
            raise TranslationValidationError(
                "translation request could not be encoded"
            ) from error

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        last_error: TranslationError | None = None
        max_attempts = MAX_TRANSLATION_RETRY + 1
        for attempt in range(1, max_attempts + 1):
            try:
                raw_response = self._transport(
                    self.endpoint_url,
                    body,
                    headers,
                    self.request_timeout_seconds,
                )
                content = _extract_assistant_content(raw_response)
                ko_text = _validate_ko_content(
                    content,
                    target=cue.target,
                )
            except TranslationContentError as error:
                last_error = error
            except TranslationResponseError as error:
                last_error = error
            except TranslationLimitError as error:
                last_error = error
            except TranslationTransportError as error:
                last_error = error
            except (OSError, TimeoutError, urllib_error.URLError) as error:
                last_error = TranslationTransportError(
                    "translation API request failed"
                )
                last_error.__cause__ = error
            else:
                return TranslationOutcome(
                    cue=cue,
                    action=TRANSLATION_ACCEPTED,
                    attempts=attempt,
                    ko_text=ko_text,
                    reason=None,
                )

            if attempt == max_attempts:
                break

        if last_error is None:
            raise TranslationValidationError(
                "translation attempt ended without a result"
            )

        return TranslationOutcome(
            cue=cue,
            action=TRANSLATION_OMITTED,
            attempts=max_attempts,
            ko_text=None,
            reason=_reason_code(last_error),
        )


__all__ = [
    "E4B_MODEL",
    "E4B_ROLE",
    "E4B_ROLE_EN",
    "E4B_ROLE_JA",
    "E4BTranslationAdapter",
    "INVALID_KO_ACTION",
    "MAX_TRANSLATION_RESPONSE_BYTES",
    "MAX_TRANSLATION_RETRY",
    "MAX_TRANSLATION_TEXT_CHARS",
    "SYSTEM_INSTRUCTION",
    "SYSTEM_INSTRUCTION_EN",
    "SYSTEM_INSTRUCTION_JA",
    "SUPPORTED_SOURCE_LANGUAGES",
    "TRANSLATION_ACCEPTED",
    "TRANSLATION_OMITTED",
    "TranslationContentError",
    "TranslationCue",
    "TranslationError",
    "TranslationLimitError",
    "TranslationOutcome",
    "TranslationResponseError",
    "TranslationTransportError",
    "TranslationValidationError",
]
