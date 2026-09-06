"""Bounded external subtitle transport boundaries for Stage11 v2.

This module intentionally stops at the external-source boundary.  It does
not select a source, modify the existing Stage11 pipeline, inspect NAS
filesystem paths, or make network requests.  A caller supplies the detail
page and payload fetchers explicitly.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from html.parser import HTMLParser
import hashlib
import re
from typing import Protocol, runtime_checkable
from urllib.parse import unquote, urljoin, urlsplit

from teddy_discovery_subtitle import (
    SOURCE_KIND_VALIDATED_EXTERNAL_TEXT,
    SUPPORTED_TEXT_FORMATS,
    SubtitleCandidate,
)
from teddy_discovery_subtitle_text import (
    MAX_SUBTITLE_BYTES,
    SubtitleDocument,
    parse_subtitle_bytes,
)


EXTERNAL_LANGUAGE_JA = "ja"
EXTERNAL_LANGUAGE_EN = "en"
EXTERNAL_LANGUAGE_KO = "ko"

# Japanese is the only external language that can be a v2 translation source.
# English is retained as a possible supporting-evidence payload.  Korean is
# deliberately absent: SubtitleCat-generated Korean is not translation truth.
EXTERNAL_TRANSLATION_SOURCE_LANGUAGES = frozenset({EXTERNAL_LANGUAGE_JA})
EXTERNAL_SUPPORTING_EVIDENCE_LANGUAGES = frozenset({EXTERNAL_LANGUAGE_EN})
SUPPORTED_EXTERNAL_PAYLOAD_LANGUAGES = frozenset(
    {
        *EXTERNAL_TRANSLATION_SOURCE_LANGUAGES,
        *EXTERNAL_SUPPORTING_EVIDENCE_LANGUAGES,
    }
)

SUBTITLECAT_PROVIDER_NAME = "subtitlecat"
MAX_SUBTITLECAT_DETAIL_HTML_BYTES = 4 * 1024 * 1024

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_SRT_SUFFIX_RE = re.compile(r"\.srt$", re.IGNORECASE)
_TERMINAL_LANGUAGE_SUFFIX_RE = re.compile(
    r"(?:^|[._-])(?P<language>[a-z]{2,8})\.srt$",
    re.IGNORECASE,
)
_DOWNLOAD_ID_LANGUAGE_RE = re.compile(
    r"^download_(?P<language>[a-z]{2,8})$",
    re.IGNORECASE,
)
_SHOW_VOTING_LANGUAGE_RE = re.compile(
    r"show_voting\s*\(\s*"
    r"(?P<quote>['\"])(?P<language>[a-z]{2,8})"
    r"(?P=quote)\s*\)",
    re.IGNORECASE,
)
_LOCAL_LANGUAGE_TOKEN_RE = re.compile(
    r"(?i)(?<![a-z0-9])"
    r"(?:ja|jpn|japanese|ko|kor|korean|en|eng|english)"
    r"(?![a-z0-9])"
    r"|日本語|日文|한국어|韓国語|英語"
)
_LOCAL_LANGUAGE_ALIASES = {
    "ja": "ja",
    "jpn": "ja",
    "japanese": "ja",
    "ko": "ko",
    "kor": "ko",
    "korean": "ko",
    "en": "en",
    "eng": "en",
    "english": "en",
    "日本語": "ja",
    "日文": "ja",
    "한국어": "ko",
    "韓国語": "ko",
    "英語": "en",
}
_CONTEXT_EVIDENCE_TAGS = frozenset(
    {
        "article",
        "dd",
        "div",
        "dt",
        "li",
        "p",
        "section",
        "td",
        "th",
        "tr",
    }
)


class ExternalSubtitleError(Exception):
    """Base class for external subtitle boundary failures."""


class ExternalSubtitleValidationError(ValueError, ExternalSubtitleError):
    """Raised when an external candidate or payload violates its contract."""


class ExternalSubtitleTransportError(RuntimeError, ExternalSubtitleError):
    """Raised when an injected external byte/detail transport is unusable."""


class SubtitleCatDetailError(ExternalSubtitleValidationError):
    """Raised when a SubtitleCat detail page has no safe unique JA source."""


def _has_control_or_whitespace(value: str) -> bool:
    return any(
        character.isspace()
        or ord(character) < 32
        or ord(character) == 127
        for character in value
    )


def _validate_dvd_id(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or _has_control_or_whitespace(value)
        or "/" in value
        or "\\" in value
    ):
        raise ExternalSubtitleValidationError(
            "dvd_id must be a nonempty exact safe identifier"
        )

    return value


def _validate_http_url(value: object, *, field_name: str) -> str:
    """Validate a URL without normalizing away unsafe input."""

    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or _has_control_or_whitespace(value)
        or "\\" in value
        or any(character in value for character in '<>"\'')
    ):
        raise SubtitleCatDetailError(
            field_name + " is malformed or unsafe"
        )

    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        parsed_port = parsed.port
    except ValueError as error:
        raise SubtitleCatDetailError(
            field_name + " is malformed or unsafe"
        ) from error

    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.netloc
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise SubtitleCatDetailError(
            field_name + " must be an http(s) URL without credentials"
        )

    if parsed_port is not None and not (1 <= parsed_port <= 65_535):
        raise SubtitleCatDetailError(
            field_name + " has an invalid port"
        )

    if parsed.fragment:
        raise SubtitleCatDetailError(
            field_name + " must not contain a fragment"
        )

    return value


def _validate_href_text(value: object) -> str:
    """Reject unsafe raw href text before URL resolution can repair it."""

    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or _has_control_or_whitespace(value)
        or "\\" in value
        or any(character in value for character in '<>"\'')
    ):
        raise SubtitleCatDetailError(
            "Japanese subtitle href is malformed or unsafe"
        )

    if re.search(r"(?i)%(?:00|0a|0d|7f|5c)", value) is not None:
        raise SubtitleCatDetailError(
            "Japanese subtitle href contains an unsafe escape"
        )

    return value


def _validate_external_candidate(
    candidate: object,
    *,
    dvd_id: object,
) -> SubtitleCandidate:
    expected_dvd_id = _validate_dvd_id(dvd_id)

    if not isinstance(candidate, SubtitleCandidate):
        raise ExternalSubtitleValidationError(
            "candidate must be a SubtitleCandidate"
        )

    if candidate.source_kind != SOURCE_KIND_VALIDATED_EXTERNAL_TEXT:
        raise ExternalSubtitleValidationError(
            "candidate must use the validated external text kind"
        )

    if candidate.validated_for_dvd_id != expected_dvd_id:
        raise ExternalSubtitleValidationError(
            "candidate DVD-ID validation does not exactly match payload DVD-ID"
        )

    if candidate.language not in SUPPORTED_EXTERNAL_PAYLOAD_LANGUAGES:
        if candidate.language == EXTERNAL_LANGUAGE_KO:
            raise ExternalSubtitleValidationError(
                "external Korean is not an accepted v2 translation source"
            )
        raise ExternalSubtitleValidationError(
            "external candidate language is not supported by this boundary"
        )

    if candidate.text_format not in SUPPORTED_TEXT_FORMATS:
        raise ExternalSubtitleValidationError(
            "external candidate text format is unsupported"
        )

    return candidate


def _validate_sha256(value: object, *, field_name: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise ExternalSubtitleValidationError(
            field_name + " must be a lowercase SHA-256 digest"
        )

    return value


@dataclass(frozen=True)
class ExternalSubtitlePayload:
    """One bounded immutable payload tied to one exact external candidate.

    ``candidate.validated_for_dvd_id`` must exactly equal ``dvd_id``.  The
    optional metadata fields make the boundary convenient for a fetcher that
    supplies declared metadata while still computing and checking the digest
    and exact byte count locally.
    """

    dvd_id: str
    candidate: SubtitleCandidate
    payload: bytes
    sha256: str | None = None
    byte_size: int | None = None
    source_url: str | None = None

    def __post_init__(self):
        candidate = _validate_external_candidate(
            self.candidate,
            dvd_id=self.dvd_id,
        )

        if type(self.payload) is not bytes:
            raise ExternalSubtitleValidationError(
                "external subtitle payload must be exact bytes"
            )

        byte_size = len(self.payload)

        if byte_size <= 0:
            raise ExternalSubtitleValidationError(
                "external subtitle payload must not be empty"
            )

        if byte_size > MAX_SUBTITLE_BYTES:
            raise ExternalSubtitleValidationError(
                "external subtitle payload exceeds MAX_SUBTITLE_BYTES"
            )

        if self.byte_size is None:
            declared_byte_size = byte_size
        else:
            if type(self.byte_size) is not int:
                raise ExternalSubtitleValidationError(
                    "byte_size must be an exact integer"
                )
            declared_byte_size = self.byte_size

            if declared_byte_size != byte_size:
                raise ExternalSubtitleValidationError(
                    "byte_size does not equal exact payload length"
                )

        if (
            declared_byte_size <= 0
            or declared_byte_size > MAX_SUBTITLE_BYTES
        ):
            raise ExternalSubtitleValidationError(
                "byte_size is outside the allowed payload bound"
            )

        computed_sha256 = hashlib.sha256(self.payload).hexdigest()

        if self.sha256 is None:
            declared_sha256 = computed_sha256
        else:
            declared_sha256 = _validate_sha256(
                self.sha256,
                field_name="sha256",
            )

            if declared_sha256 != computed_sha256:
                raise ExternalSubtitleValidationError(
                    "sha256 does not match exact payload bytes"
                )

        if self.source_url is not None:
            source_url = _validate_http_url(
                self.source_url,
                field_name="source_url",
            )
            if candidate.external_source_id != source_url:
                raise ExternalSubtitleValidationError(
                    "source_url does not match candidate external identity"
                )

        # Store derived metadata even when the caller omitted it.  This keeps
        # the immutable model identical whether it came from a raw fake fetch
        # or from a transport envelope with declared metadata.
        object.__setattr__(self, "candidate", candidate)
        object.__setattr__(self, "sha256", declared_sha256)
        object.__setattr__(self, "byte_size", declared_byte_size)

    @classmethod
    def from_bytes(
        cls,
        *,
        dvd_id: str,
        candidate: SubtitleCandidate,
        payload: bytes,
        sha256: str | None = None,
        byte_size: int | None = None,
        source_url: str | None = None,
    ) -> "ExternalSubtitlePayload":
        """Construct and validate one payload from raw fetched bytes."""

        return cls(
            dvd_id=dvd_id,
            candidate=candidate,
            payload=payload,
            sha256=sha256,
            byte_size=byte_size,
            source_url=source_url,
        )

    @property
    def raw_bytes(self) -> bytes:
        """The exact fetched bytes, exposed without a filesystem wrapper."""

        return self.payload

    @property
    def is_translation_source(self) -> bool:
        """Whether v2 may use this external language as translation input."""

        return self.candidate.language in EXTERNAL_TRANSLATION_SOURCE_LANGUAGES

    @property
    def is_supporting_evidence(self) -> bool:
        """Whether this payload is reserved for non-translation evidence."""

        return (
            self.candidate.language
            in EXTERNAL_SUPPORTING_EVIDENCE_LANGUAGES
        )

    def parse(self) -> SubtitleDocument:
        """Parse through the existing bounded SRT/VTT parser boundary."""

        document = parse_subtitle_bytes(
            self.payload,
            self.candidate.text_format,
        )

        if (
            not isinstance(document, SubtitleDocument)
            or document.source_sha256 != self.sha256
            or document.byte_size != self.byte_size
        ):
            raise ExternalSubtitleTransportError(
                "subtitle parser returned inconsistent payload metadata"
            )

        return document

    # A descriptive alias keeps the parse boundary easy to discover without
    # introducing another parser or document type.
    parse_subtitle = parse


@runtime_checkable
class ExternalSubtitleProvider(Protocol):
    """Provider abstraction for a bounded external payload source."""

    provider_name: str

    def fetch_payload(
        self,
        *,
        dvd_id: str,
        candidate: SubtitleCandidate,
    ) -> ExternalSubtitlePayload:
        """Fetch and validate bytes for an already validated candidate."""


class ExternalSubtitleTransport:
    """Injectable raw-byte transport with no NAS/filesystem semantics."""

    provider_name = "injected"

    def __init__(self, fetch_bytes: Callable[[SubtitleCandidate], bytes]):
        if not callable(fetch_bytes):
            raise ExternalSubtitleValidationError(
                "fetch_bytes must be callable"
            )

        self.fetch_bytes = fetch_bytes

    def fetch_payload(
        self,
        *,
        dvd_id: str,
        candidate: SubtitleCandidate,
        sha256: str | None = None,
        byte_size: int | None = None,
    ) -> ExternalSubtitlePayload:
        """Fetch exact bytes and turn them into a validated payload."""

        validated_candidate = _validate_external_candidate(
            candidate,
            dvd_id=dvd_id,
        )

        try:
            raw = self.fetch_bytes(validated_candidate)
        except ExternalSubtitleError:
            raise
        except Exception as error:
            raise ExternalSubtitleTransportError(
                "injected external subtitle fetch failed"
            ) from error

        source_url = None
        try:
            source_scheme = urlsplit(
                validated_candidate.external_source_id
            ).scheme.lower()
        except ValueError as error:
            raise ExternalSubtitleValidationError(
                "external candidate identity is malformed"
            ) from error

        if source_scheme in {"http", "https"}:
            source_url = _validate_http_url(
                validated_candidate.external_source_id,
                field_name="external candidate source URL",
            )

        try:
            return ExternalSubtitlePayload.from_bytes(
                dvd_id=dvd_id,
                candidate=validated_candidate,
                payload=raw,
                sha256=sha256,
                byte_size=byte_size,
                source_url=source_url,
            )
        except ExternalSubtitleValidationError:
            raise
        except Exception as error:
            raise ExternalSubtitleTransportError(
                "injected external subtitle payload was unusable"
            ) from error

    # Both names describe the same one-way transport operation.
    fetch = fetch_payload


@dataclass(frozen=True)
class SubtitleCatDetailPage:
    """Fetched SubtitleCat HTML together with its actual final URL."""

    final_url: str
    html: str

    def __post_init__(self):
        _validate_http_url(
            self.final_url,
            field_name="detail page final_url",
        )

        if type(self.html) is not str or not self.html:
            raise SubtitleCatDetailError(
                "detail page html must be nonempty text"
            )

        try:
            html_bytes = len(self.html.encode("utf-8"))
        except UnicodeEncodeError as error:
            raise SubtitleCatDetailError(
                "detail page html is not valid UTF-8 text"
            ) from error

        if html_bytes > MAX_SUBTITLECAT_DETAIL_HTML_BYTES:
            raise SubtitleCatDetailError(
                "detail page html exceeds its bounded size"
            )


@dataclass
class _HTMLContext:
    tag: str
    attribute_parts: list[str]
    text_parts: list[str]


@dataclass
class _AnchorRecord:
    href_values: list[str]
    evidence_parts: list[str]
    text_parts: list[str]
    contexts: tuple[_HTMLContext, ...]
    local_attributes: list[tuple[str, str]]


@dataclass(frozen=True)
class _LocalLanguageSignal:
    source: str
    token: str
    normalized: str | None


class _SubtitleCatAnchorParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.records: list[_AnchorRecord] = []
        self._contexts: list[_HTMLContext] = []
        self._active_anchors: list[_AnchorRecord] = []

    @staticmethod
    def _attribute_parts(attrs) -> list[str]:
        parts: list[str] = []
        for key, value in attrs:
            if key is not None:
                parts.append(str(key))
            if value is not None:
                parts.append(str(value))
        return parts

    @staticmethod
    def _local_attribute_pairs(attrs) -> list[tuple[str, str]]:
        return [
            (str(key).lower(), str(value))
            for key, value in attrs
            if key is not None and value is not None
        ]

    def handle_starttag(self, tag, attrs):
        tag = str(tag).lower()
        attribute_parts = self._attribute_parts(attrs)
        local_attribute_pairs = self._local_attribute_pairs(attrs)

        for anchor in self._active_anchors:
            anchor.evidence_parts.extend(attribute_parts)
            anchor.evidence_parts.append(tag)
            anchor.local_attributes.extend(local_attribute_pairs)

        if tag == "a":
            href_values = [
                str(value)
                for key, value in attrs
                if str(key).lower() == "href" and value is not None
            ]
            anchor = _AnchorRecord(
                href_values=href_values,
                evidence_parts=list(attribute_parts),
                text_parts=[],
                contexts=tuple(
                    context
                    for context in self._contexts
                    if context.tag in _CONTEXT_EVIDENCE_TAGS
                ),
                local_attributes=list(local_attribute_pairs),
            )
            self._active_anchors.append(anchor)

        context = _HTMLContext(
            tag=tag,
            attribute_parts=attribute_parts,
            text_parts=[],
        )
        self._contexts.append(context)

        if tag in _CONTEXT_EVIDENCE_TAGS:
            for anchor in self._active_anchors:
                if not any(
                    existing is context
                    for existing in anchor.contexts
                ):
                    anchor.contexts = (*anchor.contexts, context)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = str(tag).lower()

        if tag == "a" and self._active_anchors:
            self.records.append(self._active_anchors.pop())

        for index in range(len(self._contexts) - 1, -1, -1):
            if self._contexts[index].tag == tag:
                del self._contexts[index:]
                break

    def handle_data(self, data):
        for context in self._contexts:
            context.text_parts.append(data)

        for anchor in self._active_anchors:
            anchor.text_parts.append(data)

    def finish_unclosed_anchors(self):
        while self._active_anchors:
            self.records.append(self._active_anchors.pop())


_GENERATED_EVIDENCE_RE = re.compile(
    r"(?i)(?:machine|automated|auto[- ]?translated|translation|generated|"
    r"ai[- ]?translated)"
)


def _record_evidence(record: _AnchorRecord) -> str:
    """Return only evidence owned by this anchor.

    Ancestor contexts are intentionally excluded.  A SubtitleCat language
    list commonly puts every language name in one shared container, so using
    its text would give every SRT anchor the same JA/KO/EN identity.
    """

    return " ".join(
        [
            *record.evidence_parts,
            *record.text_parts,
        ]
    )


def _normalize_local_language(value: object) -> str | None:
    if not isinstance(value, str):
        return None

    return _LOCAL_LANGUAGE_ALIASES.get(value.strip().lower())


def _local_language_signal(
    source: str,
    value: str,
) -> _LocalLanguageSignal:
    token = value.strip().lower()
    return _LocalLanguageSignal(
        source=source,
        token=token,
        normalized=_normalize_local_language(token),
    )


def _terminal_href_language(
    href: str,
) -> tuple[bool, _LocalLanguageSignal | None]:
    try:
        path = unquote(urlsplit(href).path)
    except ValueError:
        return False, None

    basename = path.rsplit("/", 1)[-1]
    match = _TERMINAL_LANGUAGE_SUFFIX_RE.search(basename)

    if match is None:
        return False, None

    signal = _local_language_signal(
        "terminal href suffix",
        match.group("language"),
    )

    # A generic basename such as ``original.srt`` is not a language suffix.
    # Keep bare language-only names (for example ``ja.srt``) supported, while
    # treating an unknown token after an explicit separator as a real local
    # signal that must not silently override other metadata.
    if match.start() == 0 and signal.normalized is None:
        return False, None

    return True, signal


def _local_attribute_languages(
    record: _AnchorRecord,
) -> list[_LocalLanguageSignal]:
    signals: list[_LocalLanguageSignal] = []

    for name, value in record.local_attributes:
        if name == "id":
            match = _DOWNLOAD_ID_LANGUAGE_RE.fullmatch(value.strip())
            if match is None:
                continue

            signals.append(
                _local_language_signal(
                    "anchor id",
                    match.group("language"),
                )
            )
            continue

        if name == "onclick":
            for match in _SHOW_VOTING_LANGUAGE_RE.finditer(value):
                signals.append(
                    _local_language_signal(
                        "anchor onclick",
                        match.group("language"),
                    )
                )
            continue

        if name not in {
            "data-lang",
            "data-language",
            "hreflang",
            "lang",
        }:
            continue

        if not value.strip():
            continue

        signals.append(
            _local_language_signal(
                "anchor language attribute",
                value,
            )
        )

    return signals


def _local_text_languages(
    record: _AnchorRecord,
) -> list[_LocalLanguageSignal]:
    text = " ".join(record.text_parts)
    return [
        _local_language_signal(
            "anchor-local text",
            match.group(0),
        )
        for match in _LOCAL_LANGUAGE_TOKEN_RE.finditer(text)
    ]


def _resolve_local_target_language(
    record: _AnchorRecord,
    href: str,
) -> str | None:
    terminal_present, terminal_language = _terminal_href_language(href)
    signals: list[_LocalLanguageSignal] = []

    if terminal_present:
        signals.append(terminal_language)

    signals.extend(_local_attribute_languages(record))
    signals.extend(_local_text_languages(record))

    known_languages = {
        signal.normalized
        for signal in signals
        if signal.normalized is not None
    }
    unsupported_tokens = {
        signal.token
        for signal in signals
        if signal.normalized is None
    }

    if (
        len(known_languages) > 1
        or len(unsupported_tokens) > 1
        or (known_languages and unsupported_tokens)
    ):
        raise SubtitleCatDetailError(
            "Japanese subtitle anchor has conflicting local language metadata"
        )

    # A consistently unsupported language is a known non-JA candidate for the
    # purpose of this narrow provider boundary.  It is skipped, not guessed or
    # added to the language map.
    if unsupported_tokens:
        return None

    if len(known_languages) != 1:
        return None

    return next(iter(known_languages))


def _record_href(record: _AnchorRecord) -> str:
    if len(record.href_values) != 1:
        raise SubtitleCatDetailError(
            "Japanese subtitle anchor must contain exactly one href"
        )

    return record.href_values[0]


def _looks_like_srt_href(href: str) -> bool:
    try:
        path = unquote(urlsplit(href).path)
    except ValueError:
        return False

    return _SRT_SUFFIX_RE.search(path) is not None


def find_subtitlecat_original_japanese_srt_url(
    html: object,
    final_detail_url: object,
) -> str:
    """Return the one actual original-Japanese SRT href from detail HTML.

    The returned link is obtained from an ``href`` and resolved with
    ``urljoin`` against the response's actual final detail-page URL.  No
    provider path or numeric directory is inferred or synthesized.
    """

    if type(html) is not str or not html:
        raise SubtitleCatDetailError(
            "detail page html must be nonempty text"
        )

    try:
        html_bytes = len(html.encode("utf-8"))
    except UnicodeEncodeError as error:
        raise SubtitleCatDetailError(
            "detail page html is not valid UTF-8 text"
        ) from error

    if html_bytes > MAX_SUBTITLECAT_DETAIL_HTML_BYTES:
        raise SubtitleCatDetailError(
            "detail page html exceeds its bounded size"
        )

    final_url = _validate_http_url(
        final_detail_url,
        field_name="detail page final_url",
    )

    parser = _SubtitleCatAnchorParser()

    try:
        parser.feed(html)
        parser.close()
        parser.finish_unclosed_anchors()
    except Exception as error:
        if isinstance(error, SubtitleCatDetailError):
            raise
        raise SubtitleCatDetailError(
            "detail page HTML could not be parsed"
        ) from error

    matches: set[str] = set()

    for record in parser.records:
        if not record.href_values:
            continue

        href = _record_href(record)

        if not _looks_like_srt_href(href):
            continue

        _validate_href_text(href)

        target_language = _resolve_local_target_language(
            record,
            href,
        )

        if target_language != "ja":
            continue

        if _GENERATED_EVIDENCE_RE.search(
            _record_evidence(record)
        ) is not None:
            raise SubtitleCatDetailError(
                "Japanese subtitle link is not an unambiguous original"
            )

        try:
            absolute_url = urljoin(final_url, href)
            absolute_url = _validate_http_url(
                absolute_url,
                field_name="Japanese subtitle href",
            )
        except SubtitleCatDetailError:
            raise
        except Exception as error:
            raise SubtitleCatDetailError(
                "Japanese subtitle href is malformed or unsafe"
            ) from error

        matches.add(absolute_url)

    if not matches:
        raise SubtitleCatDetailError(
            "detail page has no safe original Japanese SRT link"
        )

    if len(matches) != 1:
        raise SubtitleCatDetailError(
            "detail page has ambiguous original Japanese SRT links"
        )

    return next(iter(matches))


# Short aliases for callers that describe this operation as parsing rather
# than finding.  They are the same boundary and do not create another parser.
parse_subtitlecat_detail_page = find_subtitlecat_original_japanese_srt_url
find_original_japanese_srt_url = find_subtitlecat_original_japanese_srt_url


def _coerce_detail_page(response: object) -> SubtitleCatDetailPage:
    if isinstance(response, SubtitleCatDetailPage):
        return response

    if isinstance(response, Mapping):
        if set(response) != {"final_url", "html"}:
            raise SubtitleCatDetailError(
                "detail fetch response has an unexpected shape"
            )
        return SubtitleCatDetailPage(
            final_url=response["final_url"],
            html=response["html"],
        )

    final_url = getattr(response, "final_url", None)
    html = getattr(response, "html", None)

    if final_url is None:
        final_url = getattr(response, "url", None)
    if html is None:
        html = getattr(response, "text", None)

    if final_url is None or html is None:
        raise SubtitleCatDetailError(
            "detail fetch response must expose final_url and html"
        )

    return SubtitleCatDetailPage(
        final_url=final_url,
        html=html,
    )


class SubtitleCatProvider:
    """SubtitleCat adapter with both transports supplied by the caller.

    ``fetch_detail`` receives the requested detail URL and must return a
    ``SubtitleCatDetailPage`` (or an object/mapping exposing its final URL and
    HTML).  ``payload_transport`` is an ``ExternalSubtitleProvider``; a raw
    ``payload_fetcher`` may be supplied as a convenience for smoke tests.
    Neither dependency has a network or filesystem default.
    """

    provider_name = SUBTITLECAT_PROVIDER_NAME

    def __init__(
        self,
        *,
        fetch_detail: Callable[[str], object],
        payload_transport: ExternalSubtitleProvider | None = None,
        payload_fetcher: Callable[[SubtitleCandidate], bytes] | None = None,
    ):
        if not callable(fetch_detail):
            raise ExternalSubtitleValidationError(
                "fetch_detail must be callable"
            )

        if payload_transport is not None and payload_fetcher is not None:
            raise ExternalSubtitleValidationError(
                "provide payload_transport or payload_fetcher, not both"
            )

        if payload_transport is None and payload_fetcher is not None:
            payload_transport = ExternalSubtitleTransport(payload_fetcher)

        if payload_transport is not None:
            fetch_payload = getattr(payload_transport, "fetch_payload", None)
            if not callable(fetch_payload):
                raise ExternalSubtitleValidationError(
                    "payload_transport must provide fetch_payload"
                )

        self.fetch_detail = fetch_detail
        self.payload_transport = payload_transport

    def find_original_japanese_candidate(
        self,
        *,
        dvd_id: str,
        detail_url: str,
    ) -> SubtitleCandidate:
        """Fetch a detail page and bind its actual JA SRT URL to the DVD-ID."""

        dvd_id = _validate_dvd_id(dvd_id)
        requested_url = _validate_http_url(
            detail_url,
            field_name="detail page URL",
        )

        try:
            response = self.fetch_detail(requested_url)
        except ExternalSubtitleError:
            raise
        except Exception as error:
            raise ExternalSubtitleTransportError(
                "injected SubtitleCat detail fetch failed"
            ) from error

        page = _coerce_detail_page(response)
        source_url = find_subtitlecat_original_japanese_srt_url(
            page.html,
            page.final_url,
        )

        return SubtitleCandidate.validated_external_text(
            source_url,
            dvd_id=dvd_id,
            language=EXTERNAL_LANGUAGE_JA,
            text_format="srt",
        )

    # Descriptive aliases for provider callers.
    locate_original_japanese_candidate = find_original_japanese_candidate
    discover_original_japanese_candidate = find_original_japanese_candidate

    def fetch_payload(
        self,
        *,
        dvd_id: str,
        candidate: SubtitleCandidate,
    ) -> ExternalSubtitlePayload:
        """Fetch bytes for an already-bound candidate through injected I/O."""

        if self.payload_transport is None:
            raise ExternalSubtitleTransportError(
                "SubtitleCat payload transport is not configured"
            )

        return self.payload_transport.fetch_payload(
            dvd_id=dvd_id,
            candidate=candidate,
        )

    def fetch_original_japanese_payload(
        self,
        *,
        dvd_id: str,
        detail_url: str,
    ) -> ExternalSubtitlePayload:
        """Discover the actual JA link, then fetch its bounded payload."""

        candidate = self.find_original_japanese_candidate(
            dvd_id=dvd_id,
            detail_url=detail_url,
        )
        return self.fetch_payload(
            dvd_id=dvd_id,
            candidate=candidate,
        )

    def fetch_original_japanese_document(
        self,
        *,
        dvd_id: str,
        detail_url: str,
    ) -> SubtitleDocument:
        """Convenience endpoint that retains the existing parser boundary."""

        return self.fetch_original_japanese_payload(
            dvd_id=dvd_id,
            detail_url=detail_url,
        ).parse()


def fetch_external_subtitle_payload(
    *,
    dvd_id: str,
    candidate: SubtitleCandidate,
    fetch_bytes: Callable[[SubtitleCandidate], bytes],
    sha256: str | None = None,
    byte_size: int | None = None,
) -> ExternalSubtitlePayload:
    """Functional form of the injectable external byte transport."""

    return ExternalSubtitleTransport(fetch_bytes).fetch_payload(
        dvd_id=dvd_id,
        candidate=candidate,
        sha256=sha256,
        byte_size=byte_size,
    )


__all__ = [
    "EXTERNAL_LANGUAGE_EN",
    "EXTERNAL_LANGUAGE_JA",
    "EXTERNAL_LANGUAGE_KO",
    "EXTERNAL_SUPPORTING_EVIDENCE_LANGUAGES",
    "EXTERNAL_TRANSLATION_SOURCE_LANGUAGES",
    "ExternalSubtitleError",
    "ExternalSubtitlePayload",
    "ExternalSubtitleProvider",
    "ExternalSubtitleTransport",
    "ExternalSubtitleTransportError",
    "ExternalSubtitleValidationError",
    "MAX_SUBTITLECAT_DETAIL_HTML_BYTES",
    "SUBTITLECAT_PROVIDER_NAME",
    "SUPPORTED_EXTERNAL_PAYLOAD_LANGUAGES",
    "SubtitleCatDetailError",
    "SubtitleCatDetailPage",
    "SubtitleCatProvider",
    "fetch_external_subtitle_payload",
    "find_original_japanese_srt_url",
    "find_subtitlecat_original_japanese_srt_url",
    "parse_subtitlecat_detail_page",
]
