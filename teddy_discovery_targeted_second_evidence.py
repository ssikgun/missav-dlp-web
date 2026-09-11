"""Route-neutral in-memory targeted ASR second-evidence bindings.

This module adapts the existing bounded targeted-ASR window and remote-result
contracts to ASR-first source identities.  It owns provenance and transport
binding only; it does not call Whisper, decide KEEP/REPAIR/OMIT/AMBIGUOUS, or
change baseline subtitle timing.

The persistent Hybrid artifact remains external-JA compatible and is not
changed here.  A future persistent generic artifact can be added around these
typed values without pretending that ``ja-*`` identities are ASR identities.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re

from teddy_discovery_asr import (
    ASRResult,
    ASRSegment,
    ASRSourceSnapshot,
    MAX_ASR_SEGMENTS,
)
from teddy_discovery_asr_source_quality import (
    ASR_SOURCE_REQUIRE_SECOND_EVIDENCE,
    ASRSourceQualityDecision,
    validate_asr_source_quality_decisions,
)
from teddy_discovery_hybrid_evidence import (
    EVIDENCE_SOURCE_ASR_SEGMENT,
    stable_cue_id,
)
from teddy_discovery_stateful_parts import has_runaway_repetition
from teddy_discovery_targeted_asr_window import (
    TargetedSecondEvidenceWindowPolicy,
    TargetedASRSourceInterval,
    TargetedASRSourceWindow,
    plan_targeted_asr_source_windows,
    validate_targeted_second_evidence_window_policy,
)


MAX_TARGETED_SECOND_EVIDENCE_WINDOWS = 512
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_WINDOW_ID_RE = re.compile(r"^targeted-window-[0-9]{6}$")

TARGETED_SECOND_EVIDENCE_STATUS_PRESENT_UNRESOLVED = (
    "PRESENT_UNRESOLVED"
)
TARGETED_SECOND_EVIDENCE_STATUS_EMPTY_UNRESOLVED = "EMPTY_UNRESOLVED"
TARGETED_SECOND_EVIDENCE_STATUS_NOISY_UNRESOLVED = "NOISY_UNRESOLVED"


class TargetedSecondEvidenceError(ValueError):
    """Raised when targeted ASR evidence cannot be bound safely."""


class TargetedSecondEvidenceLimitError(TargetedSecondEvidenceError):
    """Raised when a bounded targeted second-evidence value is too large."""


def _require_exact_nonnegative_int(value: object, *, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise TargetedSecondEvidenceError(
            field_name + " must be an exact nonnegative integer"
        )
    return value


def _require_safe_token(value: object, *, field_name: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or any(character.isspace() for character in value)
        or any(
            ord(character) < 32 or ord(character) == 127
            for character in value
        )
    ):
        raise TargetedSecondEvidenceError(field_name + " is unsafe")
    return value


def _validated_snapshot(value: object) -> ASRSourceSnapshot:
    if type(value) is not ASRSourceSnapshot:
        raise TargetedSecondEvidenceError(
            "targeted source snapshot has the wrong type"
        )
    try:
        validated = ASRSourceSnapshot(
            dvd_id=value.dvd_id,
            canonical_video_relative=value.canonical_video_relative,
            source_size=value.source_size,
            source_mtime_ns=value.source_mtime_ns,
        )
    except Exception as error:
        raise TargetedSecondEvidenceError(
            "targeted source snapshot is invalid"
        ) from error
    if validated != value:
        raise TargetedSecondEvidenceError(
            "targeted source snapshot is detached"
        )
    return validated


def _validated_segment(value: object, *, field_name: str) -> ASRSegment:
    if type(value) is not ASRSegment:
        raise TargetedSecondEvidenceError(
            field_name + " has the wrong type"
        )
    try:
        validated = ASRSegment(
            start_ms=value.start_ms,
            end_ms=value.end_ms,
            text=value.text,
            words=value.words,
        )
    except Exception as error:
        raise TargetedSecondEvidenceError(
            field_name + " is invalid"
        ) from error
    if validated != value:
        raise TargetedSecondEvidenceError(
            field_name + " is detached"
        )
    return validated


def _validated_segments(value: object) -> tuple[ASRSegment, ...]:
    if type(value) is not tuple:
        raise TargetedSecondEvidenceError(
            "targeted segments must be an immutable tuple"
        )
    if len(value) > MAX_ASR_SEGMENTS:
        raise TargetedSecondEvidenceLimitError(
            "targeted segments exceed MAX_ASR_SEGMENTS"
        )
    validated = tuple(
        _validated_segment(segment, field_name="targeted segment")
        for segment in value
    )
    previous_start_ms = None
    for segment in validated:
        if (
            previous_start_ms is not None
            and segment.start_ms < previous_start_ms
        ):
            raise TargetedSecondEvidenceError(
                "targeted segment starts must be nondecreasing"
            )
        previous_start_ms = segment.start_ms
    return validated


def _require_sha256(value: object, *, field_name: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise TargetedSecondEvidenceError(
            field_name + " must be lowercase SHA-256"
        )
    return value


def _validate_window_parameters(
    *,
    padding_before_ms: object,
    padding_after_ms: object,
    merge_gap_ms: object,
    max_window_ms: object,
) -> None:
    _require_exact_nonnegative_int(
        padding_before_ms,
        field_name="padding_before_ms",
    )
    _require_exact_nonnegative_int(
        padding_after_ms,
        field_name="padding_after_ms",
    )
    _require_exact_nonnegative_int(
        merge_gap_ms,
        field_name="merge_gap_ms",
    )
    if type(max_window_ms) is not int or max_window_ms <= 0:
        raise TargetedSecondEvidenceError(
            "max_window_ms must be an exact positive integer"
        )


def _binding_digest(
    source_snapshot: ASRSourceSnapshot,
    sources: tuple["TargetedSecondEvidenceSource", ...],
    windows: tuple["TargetedSecondEvidenceWindow", ...],
) -> str:
    payload = {
        "source_snapshot": {
            "dvd_id": source_snapshot.dvd_id,
            "canonical_video_relative": source_snapshot.canonical_video_relative,
            "source_size": source_snapshot.source_size,
            "source_mtime_ns": source_snapshot.source_mtime_ns,
        },
        "sources": [
            {
                "source_index": source.source_index,
                "cue_id": source.cue_id,
                "start_ms": source.start_ms,
                "end_ms": source.end_ms,
                "source_text": source.source_text,
            }
            for source in sources
        ],
        "windows": [
            {
                "window_id": window.window_id,
                "start_ms": window.start_ms,
                "end_ms": window.end_ms,
                "source_ids": list(window.source_ids),
                "source_indices": list(window.source_indices),
            }
            for window in windows
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class TargetedSecondEvidenceSource:
    """One baseline ASR source segment selected for second evidence."""

    source_index: int
    cue_id: str
    start_ms: int
    end_ms: int
    source_text: str

    def __post_init__(self):
        _require_exact_nonnegative_int(
            self.source_index,
            field_name="targeted source_index",
        )
        if self.source_index >= MAX_ASR_SEGMENTS:
            raise TargetedSecondEvidenceLimitError(
                "targeted source_index exceeds MAX_ASR_SEGMENTS"
            )
        expected_cue_id = stable_cue_id(
            EVIDENCE_SOURCE_ASR_SEGMENT,
            self.source_index,
        )
        if type(self.cue_id) is not str or self.cue_id != expected_cue_id:
            raise TargetedSecondEvidenceError(
                "targeted source must use its canonical asr-* identity"
            )
        if (
            type(self.start_ms) is not int
            or type(self.end_ms) is not int
            or self.start_ms < 0
            or self.end_ms <= self.start_ms
        ):
            raise TargetedSecondEvidenceError(
                "targeted source timing is invalid"
            )
        if type(self.source_text) is not str:
            raise TargetedSecondEvidenceError(
                "targeted source text must be an exact string"
            )
        try:
            normalized = ASRSegment(0, 1, self.source_text).text
        except Exception as error:
            raise TargetedSecondEvidenceError(
                "targeted source text is invalid"
            ) from error
        if normalized != self.source_text:
            raise TargetedSecondEvidenceError(
                "targeted source text was normalized or detached"
            )


@dataclass(frozen=True)
class TargetedSecondEvidenceWindow:
    """One deterministic requested window and its baseline source members."""

    window_id: str
    start_ms: int
    end_ms: int
    source_ids: tuple[str, ...]
    source_indices: tuple[int, ...]

    def __post_init__(self):
        if (
            type(self.window_id) is not str
            or _WINDOW_ID_RE.fullmatch(self.window_id) is None
            or int(self.window_id.rsplit("-", 1)[1]) < 1
        ):
            raise TargetedSecondEvidenceError(
                "targeted window_id is not deterministic"
            )
        if (
            type(self.start_ms) is not int
            or type(self.end_ms) is not int
            or self.start_ms < 0
            or self.end_ms <= self.start_ms
        ):
            raise TargetedSecondEvidenceError(
                "targeted window timing is invalid"
            )
        if type(self.source_ids) is not tuple or not self.source_ids:
            raise TargetedSecondEvidenceError(
                "targeted window source_ids must be nonempty"
            )
        if type(self.source_indices) is not tuple:
            raise TargetedSecondEvidenceError(
                "targeted window source_indices must be a tuple"
            )
        if len(self.source_ids) != len(self.source_indices):
            raise TargetedSecondEvidenceError(
                "targeted window source identity coverage differs"
            )
        if len(set(self.source_ids)) != len(self.source_ids):
            raise TargetedSecondEvidenceError(
                "targeted window contains duplicate source IDs"
            )
        previous_index = None
        for source_id, source_index in zip(
            self.source_ids,
            self.source_indices,
            strict=True,
        ):
            _require_safe_token(source_id, field_name="targeted source ID")
            _require_exact_nonnegative_int(
                source_index,
                field_name="targeted source index",
            )
            if source_index >= MAX_ASR_SEGMENTS:
                raise TargetedSecondEvidenceLimitError(
                    "targeted source index exceeds MAX_ASR_SEGMENTS"
                )
            expected = stable_cue_id(
                EVIDENCE_SOURCE_ASR_SEGMENT,
                source_index,
            )
            if source_id != expected:
                raise TargetedSecondEvidenceError(
                    "targeted window contains a non-ASR source identity"
                )
            if previous_index is not None and source_index <= previous_index:
                raise TargetedSecondEvidenceError(
                    "targeted window source indexes must be increasing"
                )
            previous_index = source_index


@dataclass(frozen=True)
class TargetedSecondEvidencePlan:
    """Validated source/window plan with an in-memory provenance digest."""

    source_snapshot: ASRSourceSnapshot
    sources: tuple[TargetedSecondEvidenceSource, ...]
    windows: tuple[TargetedSecondEvidenceWindow, ...]
    binding_sha256: str

    def __post_init__(self):
        _validated_snapshot(self.source_snapshot)
        if type(self.sources) is not tuple:
            raise TargetedSecondEvidenceError(
                "targeted plan sources must be an immutable tuple"
            )
        if type(self.windows) is not tuple:
            raise TargetedSecondEvidenceError(
                "targeted plan windows must be an immutable tuple"
            )
        if len(self.windows) > MAX_TARGETED_SECOND_EVIDENCE_WINDOWS:
            raise TargetedSecondEvidenceLimitError(
                "targeted plan exceeds the window bound"
            )

        validated_sources = []
        previous_index = None
        source_by_id = {}
        source_by_index = {}
        for source in self.sources:
            if type(source) is not TargetedSecondEvidenceSource:
                raise TargetedSecondEvidenceError(
                    "targeted plan contains an invalid source"
                )
            try:
                source.__post_init__()
            except Exception as error:
                raise TargetedSecondEvidenceError(
                    "targeted plan source is invalid"
                ) from error
            if source.cue_id in source_by_id or source.source_index in source_by_index:
                raise TargetedSecondEvidenceError(
                    "targeted plan contains duplicate source identity"
                )
            if previous_index is not None and source.source_index <= previous_index:
                raise TargetedSecondEvidenceError(
                    "targeted plan sources must remain in source order"
                )
            previous_index = source.source_index
            source_by_id[source.cue_id] = source
            source_by_index[source.source_index] = source
            validated_sources.append(source)

        validated_windows = []
        seen_window_ids = set()
        seen_source_ids = set()
        previous_window_start = None
        for window in self.windows:
            if type(window) is not TargetedSecondEvidenceWindow:
                raise TargetedSecondEvidenceError(
                    "targeted plan contains an invalid window"
                )
            try:
                window.__post_init__()
            except Exception as error:
                raise TargetedSecondEvidenceError(
                    "targeted plan window is invalid"
                ) from error
            if window.window_id in seen_window_ids:
                raise TargetedSecondEvidenceError(
                    "targeted plan contains duplicate window identity"
                )
            if (
                previous_window_start is not None
                and window.start_ms < previous_window_start
            ):
                raise TargetedSecondEvidenceError(
                    "targeted plan windows must remain ordered"
                )
            for source_id, source_index in zip(
                window.source_ids,
                window.source_indices,
                strict=True,
            ):
                source = source_by_id.get(source_id)
                if (
                    source is None
                    or source.source_index != source_index
                    or source_id in seen_source_ids
                    or source.start_ms < window.start_ms
                    or source.end_ms > window.end_ms
                ):
                    raise TargetedSecondEvidenceError(
                        "targeted plan window/source membership is detached"
                    )
                seen_source_ids.add(source_id)
            seen_window_ids.add(window.window_id)
            previous_window_start = window.start_ms
            validated_windows.append(window)

        if seen_source_ids != set(source_by_id):
            raise TargetedSecondEvidenceError(
                "targeted plan does not cover each source exactly once"
            )
        _require_sha256(
            self.binding_sha256,
            field_name="targeted plan binding_sha256",
        )
        expected_digest = _binding_digest(
            self.source_snapshot,
            tuple(validated_sources),
            tuple(validated_windows),
        )
        if self.binding_sha256 != expected_digest:
            raise TargetedSecondEvidenceError(
                "targeted plan provenance digest mismatch"
            )


@dataclass(frozen=True)
class TargetedSecondEvidenceWindowResult:
    """One already-validated targeted response, still semantically unresolved."""

    source_snapshot: ASRSourceSnapshot
    window_id: str
    window_start_ms: int
    window_end_ms: int
    segments: tuple[ASRSegment, ...]
    plan_binding_sha256: str

    def __post_init__(self):
        _validated_snapshot(self.source_snapshot)
        if (
            type(self.window_id) is not str
            or _WINDOW_ID_RE.fullmatch(self.window_id) is None
            or int(self.window_id.rsplit("-", 1)[1]) < 1
        ):
            raise TargetedSecondEvidenceError(
                "targeted result window_id is invalid"
            )
        if (
            type(self.window_start_ms) is not int
            or type(self.window_end_ms) is not int
            or self.window_start_ms < 0
            or self.window_end_ms <= self.window_start_ms
        ):
            raise TargetedSecondEvidenceError(
                "targeted result window timing is invalid"
            )
        segments = _validated_segments(self.segments)
        for segment in segments:
            if (
                segment.start_ms < self.window_start_ms
                or segment.end_ms > self.window_end_ms
            ):
                raise TargetedSecondEvidenceError(
                    "targeted result segment lies outside its window"
                )
        _require_sha256(
            self.plan_binding_sha256,
            field_name="targeted result plan_binding_sha256",
        )

    @property
    def status(self) -> str:
        if not self.segments:
            return TARGETED_SECOND_EVIDENCE_STATUS_EMPTY_UNRESOLVED
        if any(has_runaway_repetition(segment.text) for segment in self.segments):
            return TARGETED_SECOND_EVIDENCE_STATUS_NOISY_UNRESOLVED
        return TARGETED_SECOND_EVIDENCE_STATUS_PRESENT_UNRESOLVED

    @property
    def targeted_text_evidence(self) -> tuple[str, ...]:
        return tuple(segment.text for segment in self.segments)


@dataclass(frozen=True)
class TargetedSecondEvidenceBinding:
    """One source segment bound to one requested window/result."""

    source: TargetedSecondEvidenceSource
    window: TargetedSecondEvidenceWindow
    result: TargetedSecondEvidenceWindowResult

    def __post_init__(self):
        if type(self.source) is not TargetedSecondEvidenceSource:
            raise TargetedSecondEvidenceError("binding source is invalid")
        if type(self.window) is not TargetedSecondEvidenceWindow:
            raise TargetedSecondEvidenceError("binding window is invalid")
        if type(self.result) is not TargetedSecondEvidenceWindowResult:
            raise TargetedSecondEvidenceError("binding result is invalid")
        self.source.__post_init__()
        self.window.__post_init__()
        self.result.__post_init__()
        if self.source.cue_id not in self.window.source_ids:
            raise TargetedSecondEvidenceError(
                "binding source is not a member of its window"
            )
        if self.result.window_id != self.window.window_id:
            raise TargetedSecondEvidenceError(
                "binding result window identity is detached"
            )
        if (
            self.result.window_start_ms != self.window.start_ms
            or self.result.window_end_ms != self.window.end_ms
        ):
            raise TargetedSecondEvidenceError(
                "binding result window timing is detached"
            )
        if (
            self.source.start_ms < self.window.start_ms
            or self.source.end_ms > self.window.end_ms
        ):
            raise TargetedSecondEvidenceError(
                "binding source timing is outside its target window"
            )

    @property
    def source_id(self) -> str:
        return self.source.cue_id

    @property
    def targeted_segments(self) -> tuple[ASRSegment, ...]:
        return self.result.segments

    @property
    def targeted_text_evidence(self) -> tuple[str, ...]:
        return self.result.targeted_text_evidence

    @property
    def status(self) -> str:
        return self.result.status


def _make_plan(
    source_snapshot: ASRSourceSnapshot,
    sources: tuple[TargetedSecondEvidenceSource, ...],
    windows: tuple[TargetedSecondEvidenceWindow, ...],
) -> TargetedSecondEvidencePlan:
    return TargetedSecondEvidencePlan(
        source_snapshot=source_snapshot,
        sources=sources,
        windows=windows,
        binding_sha256=_binding_digest(source_snapshot, sources, windows),
    )


def build_targeted_second_evidence_plan(
    asr_result: ASRResult,
    source_quality_decisions: tuple[ASRSourceQualityDecision, ...],
    *,
    padding_before_ms: int,
    padding_after_ms: int,
    merge_gap_ms: int,
    max_window_ms: int,
) -> TargetedSecondEvidencePlan:
    """Select REQUIRE sources and plan their caller-owned target windows."""

    if type(asr_result) is not ASRResult:
        raise TargetedSecondEvidenceError(
            "asr_result must be an exact ASRResult"
        )
    try:
        asr_result.__post_init__()
        decisions = validate_asr_source_quality_decisions(
            asr_result.segments,
            source_quality_decisions,
        )
    except Exception as error:
        raise TargetedSecondEvidenceError(
            "ASR source-quality input is invalid or detached"
        ) from error
    _validate_window_parameters(
        padding_before_ms=padding_before_ms,
        padding_after_ms=padding_after_ms,
        merge_gap_ms=merge_gap_ms,
        max_window_ms=max_window_ms,
    )

    sources = []
    intervals = []
    for decision in decisions:
        if decision.action != ASR_SOURCE_REQUIRE_SECOND_EVIDENCE:
            continue
        segment = asr_result.segments[decision.source_index]
        if (
            segment.start_ms != decision.start_ms
            or segment.end_ms != decision.end_ms
            or segment.text != decision.source_text
        ):
            raise TargetedSecondEvidenceError(
                "REQUIRE source timing or text is detached"
            )
        cue_id = stable_cue_id(
            EVIDENCE_SOURCE_ASR_SEGMENT,
            decision.source_index,
        )
        source = TargetedSecondEvidenceSource(
            source_index=decision.source_index,
            cue_id=cue_id,
            start_ms=segment.start_ms,
            end_ms=segment.end_ms,
            source_text=segment.text,
        )
        sources.append(source)
        intervals.append(
            TargetedASRSourceInterval(
                source_id=cue_id,
                source_index=decision.source_index,
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
            )
        )

    sources_tuple = tuple(sources)
    if not intervals:
        return _make_plan(
            asr_result.source_snapshot,
            sources_tuple,
            (),
        )

    try:
        planned = plan_targeted_asr_source_windows(
            tuple(intervals),
            padding_before_ms=padding_before_ms,
            padding_after_ms=padding_after_ms,
            merge_gap_ms=merge_gap_ms,
            max_window_ms=max_window_ms,
        )
    except Exception as error:
        raise TargetedSecondEvidenceError(
            "targeted second-evidence window planning failed"
        ) from error

    windows = tuple(
        TargetedSecondEvidenceWindow(
            window_id="targeted-window-" + f"{index + 1:06d}",
            start_ms=window.start_ms,
            end_ms=window.end_ms,
            source_ids=window.source_ids,
            source_indices=window.source_indices,
        )
        for index, window in enumerate(planned)
    )
    return _make_plan(
        asr_result.source_snapshot,
        sources_tuple,
        windows,
    )


def build_targeted_second_evidence_plan_with_policy(
    asr_result: ASRResult,
    source_quality_decisions: tuple[ASRSourceQualityDecision, ...],
    *,
    policy: TargetedSecondEvidenceWindowPolicy,
) -> TargetedSecondEvidencePlan:
    """Build a plan from an explicitly selected versioned window policy.

    The existing parameterized builder remains available for tests and
    callers that own an explicit geometry.  This adapter is the generic
    Stage11 bridge for a canonical policy: it validates the immutable policy
    and then supplies its four values to the unchanged builder.
    """

    validated_policy = validate_targeted_second_evidence_window_policy(policy)
    return build_targeted_second_evidence_plan(
        asr_result,
        source_quality_decisions,
        padding_before_ms=validated_policy.pre_padding_ms,
        padding_after_ms=validated_policy.post_padding_ms,
        merge_gap_ms=validated_policy.merge_gap_ms,
        max_window_ms=validated_policy.max_window_ms,
    )


def bind_targeted_second_evidence(
    plan: TargetedSecondEvidencePlan,
    results: tuple[TargetedSecondEvidenceWindowResult, ...],
) -> tuple[TargetedSecondEvidenceBinding, ...]:
    """Bind validated targeted responses without assigning semantic actions."""

    if type(plan) is not TargetedSecondEvidencePlan:
        raise TargetedSecondEvidenceError("plan has the wrong type")
    try:
        plan.__post_init__()
    except Exception as error:
        raise TargetedSecondEvidenceError(
            "plan is invalid or detached"
        ) from error
    if type(results) is not tuple:
        raise TargetedSecondEvidenceError(
            "targeted results must be an immutable tuple"
        )
    if len(results) != len(plan.windows):
        raise TargetedSecondEvidenceError(
            "targeted result coverage differs from the planned windows"
        )

    window_by_id = {window.window_id: window for window in plan.windows}
    result_by_id = {}
    for result in results:
        if type(result) is not TargetedSecondEvidenceWindowResult:
            raise TargetedSecondEvidenceError(
                "targeted result has the wrong type"
            )
        try:
            result.__post_init__()
        except Exception as error:
            raise TargetedSecondEvidenceError(
                "targeted result is invalid"
            ) from error
        if result.source_snapshot != plan.source_snapshot:
            raise TargetedSecondEvidenceError(
                "targeted result source snapshot does not match the plan"
            )
        if result.window_id not in window_by_id:
            raise TargetedSecondEvidenceError(
                "targeted result names an unknown window"
            )
        if result.window_id in result_by_id:
            raise TargetedSecondEvidenceError(
                "targeted results contain a duplicate window identity"
            )
        window = window_by_id[result.window_id]
        if (
            result.window_start_ms != window.start_ms
            or result.window_end_ms != window.end_ms
        ):
            raise TargetedSecondEvidenceError(
                "targeted result window timing does not match the plan"
            )
        if result.plan_binding_sha256 != plan.binding_sha256:
            raise TargetedSecondEvidenceError(
                "targeted result provenance digest does not match the plan"
            )
        result_by_id[result.window_id] = result

    source_to_window = {}
    for window in plan.windows:
        result = result_by_id.get(window.window_id)
        if result is None:
            raise TargetedSecondEvidenceError(
                "targeted result is missing a planned window"
            )
        for source_id in window.source_ids:
            if source_id in source_to_window:
                raise TargetedSecondEvidenceError(
                    "targeted source has duplicate window membership"
                )
            source_to_window[source_id] = (window, result)

    bindings = []
    for source in plan.sources:
        window_result = source_to_window.get(source.cue_id)
        if window_result is None:
            raise TargetedSecondEvidenceError(
                "targeted source is not bound to a window"
            )
        window, result = window_result
        bindings.append(
            TargetedSecondEvidenceBinding(
                source=source,
                window=window,
                result=result,
            )
        )
    return tuple(bindings)


def validate_targeted_second_evidence_binding(
    value: object,
) -> TargetedSecondEvidenceBinding:
    """Reconstruct one binding to reject detached immutable values."""

    if type(value) is not TargetedSecondEvidenceBinding:
        raise TargetedSecondEvidenceError(
            "value must be a TargetedSecondEvidenceBinding"
        )
    try:
        validated = TargetedSecondEvidenceBinding(
            source=value.source,
            window=value.window,
            result=value.result,
        )
    except Exception as error:
        raise TargetedSecondEvidenceError(
            "targeted second-evidence binding is invalid"
        ) from error
    if validated != value:
        raise TargetedSecondEvidenceError(
            "targeted second-evidence binding is detached"
        )
    return validated


__all__ = [
    "MAX_TARGETED_SECOND_EVIDENCE_WINDOWS",
    "TARGETED_SECOND_EVIDENCE_STATUS_EMPTY_UNRESOLVED",
    "TARGETED_SECOND_EVIDENCE_STATUS_NOISY_UNRESOLVED",
    "TARGETED_SECOND_EVIDENCE_STATUS_PRESENT_UNRESOLVED",
    "TargetedSecondEvidenceBinding",
    "TargetedSecondEvidenceError",
    "TargetedSecondEvidenceLimitError",
    "TargetedSecondEvidencePlan",
    "TargetedSecondEvidenceSource",
    "TargetedSecondEvidenceWindow",
    "TargetedSecondEvidenceWindowResult",
    "bind_targeted_second_evidence",
    "build_targeted_second_evidence_plan",
    "build_targeted_second_evidence_plan_with_policy",
    "validate_targeted_second_evidence_binding",
]
