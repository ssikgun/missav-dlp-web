"""Canonical group-scoped semantic review contracts for absorbed subtitle cues.

The deterministic absorption graph owns cue membership, owner identity and
timing.  This sidecar gives Hermes an explicit semantic decision over only
those groups whose ordinary per-cue review contains an owner REPAIR.  It never
changes the existing V1 review request or result.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import PurePosixPath
import re
import unicodedata

from teddy_discovery_hybrid_evidence import HybridCueIdentity
from teddy_discovery_quality_review_session import (
    validate_canonical_review_execution_session_id,
)
from teddy_discovery_stateful_quality_review import (
    AMBIGUOUS,
    KEEP,
    OMIT,
    REPAIR,
    MAX_CUE_TEXT_CHARS,
    QualityReviewError,
    QualityReviewInputCue,
    QualityReviewRequest,
    QualityReviewResult,
    QualityReviewResultCue,
    _text,
    review_request_sha256,
    serialize_review_result,
    validate_review_request,
    validate_review_result,
)
from teddy_discovery_stateful_translator import (
    StatefulSubtitlePackage,
    StatefulSubtitleResult,
    serialize_stateful_package,
    serialize_stateful_result,
    stateful_absorption_is_enabled,
    validate_stateful_result,
)
from teddy_discovery_stateful_boundary import (
    StatefulAbsorptionChain,
    serialize_stateful_boundary_evidence,
    validate_stateful_absorption,
    validate_stateful_boundary_evidence,
)
from teddy_discovery_subtitle_source_quality import (
    OMIT_METADATA,
    SourceQualityDecision,
)
from teddy_discovery_stateful_parts import has_runaway_repetition


ABSORPTION_GROUP_REVIEW_SCHEMA_VERSION = 1
ABSORPTION_GROUP_REVIEW_INPUT_FILENAME = "stage11-absorption-group-review-input.json"
ABSORPTION_GROUP_REVIEW_RESULT_FILENAME = "stage11-absorption-group-review-result.json"
GROUP_REVIEW_KEEP = "KEEP"
GROUP_REVIEW_REPAIR = "REPAIR"
GROUP_REVIEW_AMBIGUOUS = "AMBIGUOUS"
GROUP_REVIEW_UNSUPPORTED = "UNSUPPORTED"
_GROUP_ACTIONS = frozenset({
    GROUP_REVIEW_KEEP,
    GROUP_REVIEW_REPAIR,
    GROUP_REVIEW_AMBIGUOUS,
    GROUP_REVIEW_UNSUPPORTED,
})
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
ABSORPTION_GROUP_REVIEW_MAX_BYTES = 16 * 1024 * 1024
ABSORPTION_GROUP_REVIEW_QUERY = """Review only the deterministic absorption groups listed in the group request.

The caller-provided group_id, owner_cue_id, cue_ids, source_indexes, order,
timestamps and evidence identities are immutable references. Do not invent or
change membership, timing, source indexes, or owners. The title_context contains
the original full-title Japanese, first-pass and ASR evidence. Each target group
also contains every member's Japanese, the owner's existing Korean translation,
and the original per-cue review decisions. Use adjacent and full-title context
to judge the meaning of the complete absorbed line.

Return one decision for every listed group, in the same order, with exactly
group_id, action, reason, replacement_ja and replacement_ko. action is KEEP to
retain the current first-pass group translation, REPAIR to replace the entire
group with one complete Japanese and Korean line, AMBIGUOUS when evidence does
not support a confident choice, or UNSUPPORTED when the supplied evidence or
conflicting prior decisions cannot be handled safely. Never turn uncertainty
into repair. A REPAIR replacement must cover the entire group; never copy the
owner's per-cue replacement as a group replacement without independently
judging the whole group. Do not create standalone translations for absorbed
non-owner cues. Output JSON only and preserve every group_id exactly. The
top-level object must have exactly schema_version, request_sha256 and
decisions. Use schema_version 1 and the exact Caller group request SHA appended
by the caller.
"""


class AbsorptionGroupReviewError(ValueError):
    """Malformed, detached or incomplete group-review evidence."""


def _digest(value: object) -> None:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise AbsorptionGroupReviewError("expected SHA256 digest")


def _identifier(value: object) -> None:
    if (type(value) is not str or not value or len(value) > 256
            or value != value.strip() or any(c.isspace() for c in value)
            or any(unicodedata.category(c) in {"Cc", "Cs"} for c in value)):
        raise AbsorptionGroupReviewError("invalid group-review identifier")


def _json(value: object) -> bytes:
    try:
        payload = json.dumps(
            value, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        raise AbsorptionGroupReviewError("group review is not canonical JSON") from error
    if not 0 < len(payload) <= ABSORPTION_GROUP_REVIEW_MAX_BYTES:
        raise AbsorptionGroupReviewError("group review exceeds byte bound")
    return payload


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _scope_identity(scope_fields: dict) -> str:
    return _sha(_json(scope_fields))


def _targeted_evidence_sha256(cues: tuple[QualityReviewInputCue, ...]) -> str | None:
    projections = tuple(cue.targeted_second_evidence for cue in cues)
    if not any(value is not None for value in projections):
        return None
    return _sha(_json([asdict(value) if value is not None else None for value in projections]))


@dataclass(frozen=True)
class AbsorptionGroupScope:
    """Original, deterministic identity of one complete absorption chain."""

    group_id: str
    owner_cue_id: str
    cue_ids: tuple[str, ...]
    source_indexes: tuple[int, ...]
    package_sha256: str
    first_pass_sha256: str
    source_sha256: str
    boundary_evidence_sha256: str
    source_translation_session_id: str
    parent_review_execution_session_id: str
    parent_review_request_sha256: str
    parent_review_result_sha256: str
    targeted_evidence_sha256: str | None

    def __post_init__(self):
        _identifier(self.owner_cue_id)
        _identifier(self.source_translation_session_id)
        _identifier(self.parent_review_execution_session_id)
        if (type(self.cue_ids) is not tuple or type(self.source_indexes) is not tuple
                or len(self.cue_ids) < 2 or len(self.cue_ids) != len(self.source_indexes)):
            raise AbsorptionGroupReviewError("group membership is not a multi-cue tuple")
        if (len(set(self.cue_ids)) != len(self.cue_ids)
                or any(type(index) is not int or index < 0 for index in self.source_indexes)
                or self.source_indexes != tuple(range(self.source_indexes[0], self.source_indexes[0] + len(self.source_indexes)))):
            raise AbsorptionGroupReviewError("group membership is not contiguous and unique")
        if any(type(cue_id) is not str for cue_id in self.cue_ids):
            raise AbsorptionGroupReviewError("group cue IDs are malformed")
        if self.owner_cue_id not in self.cue_ids:
            raise AbsorptionGroupReviewError("group owner is outside its membership")
        if any(
            cue_id != HybridCueIdentity.for_external_ja(index).cue_id
            for cue_id, index in zip(self.cue_ids, self.source_indexes, strict=True)
        ):
            raise AbsorptionGroupReviewError("group cue IDs differ from source indexes")
        for digest in (
            self.package_sha256,
            self.first_pass_sha256,
            self.source_sha256,
            self.boundary_evidence_sha256,
            self.parent_review_request_sha256,
            self.parent_review_result_sha256,
        ):
            _digest(digest)
        if self.targeted_evidence_sha256 is not None:
            _digest(self.targeted_evidence_sha256)
        expected = _scope_identity(_scope_fields(self))
        if self.group_id != expected:
            raise AbsorptionGroupReviewError("group scope identity differs")


def _scope_fields(scope: AbsorptionGroupScope) -> dict:
    return {
        "owner_cue_id": scope.owner_cue_id,
        "cue_ids": scope.cue_ids,
        "source_indexes": scope.source_indexes,
        "package_sha256": scope.package_sha256,
        "first_pass_sha256": scope.first_pass_sha256,
        "source_sha256": scope.source_sha256,
        "boundary_evidence_sha256": scope.boundary_evidence_sha256,
        "source_translation_session_id": scope.source_translation_session_id,
        "parent_review_execution_session_id": scope.parent_review_execution_session_id,
        "parent_review_request_sha256": scope.parent_review_request_sha256,
        "parent_review_result_sha256": scope.parent_review_result_sha256,
        "targeted_evidence_sha256": scope.targeted_evidence_sha256,
    }


def _make_scope(*, chain: StatefulAbsorptionChain, package_sha256: str,
                first_pass_sha256: str, source_sha256: str,
                boundary_evidence_sha256: str, source_translation_session_id: str,
                parent_review_execution_session_id: str,
                parent_review_request_sha256: str,
                parent_review_result_sha256: str,
                targeted_evidence_sha256: str) -> AbsorptionGroupScope:
    fields = {
        "owner_cue_id": chain.owner_cue_id,
        "cue_ids": chain.cue_ids,
        "source_indexes": chain.source_indexes,
        "package_sha256": package_sha256,
        "first_pass_sha256": first_pass_sha256,
        "source_sha256": source_sha256,
        "boundary_evidence_sha256": boundary_evidence_sha256,
        "source_translation_session_id": source_translation_session_id,
        "parent_review_execution_session_id": parent_review_execution_session_id,
        "parent_review_request_sha256": parent_review_request_sha256,
        "parent_review_result_sha256": parent_review_result_sha256,
        "targeted_evidence_sha256": targeted_evidence_sha256,
    }
    return AbsorptionGroupScope(group_id=_scope_identity(fields), **fields)


@dataclass(frozen=True)
class AbsorptionGroupReviewGroup:
    scope: AbsorptionGroupScope
    member_cues: tuple[QualityReviewInputCue, ...]
    member_decisions: tuple[QualityReviewResultCue, ...]

    def __post_init__(self):
        if type(self.scope) is not AbsorptionGroupScope:
            raise AbsorptionGroupReviewError("invalid group scope type")
        self.scope.__post_init__()
        if (type(self.member_cues) is not tuple or type(self.member_decisions) is not tuple
                or len(self.member_cues) != len(self.scope.cue_ids)
                or len(self.member_decisions) != len(self.scope.cue_ids)):
            raise AbsorptionGroupReviewError("group member evidence is incomplete")
        for cue, decision, cue_id, source_index in zip(
            self.member_cues, self.member_decisions,
            self.scope.cue_ids, self.scope.source_indexes, strict=True,
        ):
            if type(cue) is not QualityReviewInputCue or type(decision) is not QualityReviewResultCue:
                raise AbsorptionGroupReviewError("invalid group member evidence type")
            cue.__post_init__()
            decision.__post_init__()
            if (cue.cue_id != cue_id or cue.source_index != source_index
                    or decision.cue_id != cue_id):
                raise AbsorptionGroupReviewError("group member identity or order differs")
            if cue_id != self.scope.owner_cue_id and cue.first_pass_ko is not None:
                raise AbsorptionGroupReviewError("non-owner has an independent Korean translation")
        if _targeted_evidence_sha256(self.member_cues) != self.scope.targeted_evidence_sha256:
            raise AbsorptionGroupReviewError("group targeted evidence identity differs")
        owner_index = self.scope.cue_ids.index(self.scope.owner_cue_id)
        owner = self.member_cues[owner_index]
        if owner.first_pass_ko is None:
            raise AbsorptionGroupReviewError("group owner does not own a Korean translation")
        if self.member_decisions[owner_index].action != REPAIR:
            raise AbsorptionGroupReviewError("group review is not required by owner REPAIR")
        if any(
            decision.action not in {KEEP, AMBIGUOUS}
            for index, decision in enumerate(self.member_decisions)
            if index != owner_index
        ):
            raise AbsorptionGroupReviewError("group contains an unsupported prior review action")


@dataclass(frozen=True)
class AbsorptionGroupReviewRequest:
    schema_version: int
    parent_review_request_sha256: str
    parent_review_result_sha256: str
    source_translation_session_id: str
    parent_review_execution_session_id: str
    title_context: tuple[QualityReviewInputCue, ...]
    groups: tuple[AbsorptionGroupReviewGroup, ...]

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != ABSORPTION_GROUP_REVIEW_SCHEMA_VERSION:
            raise AbsorptionGroupReviewError("unsupported absorption group review schema")
        for digest in (self.parent_review_request_sha256, self.parent_review_result_sha256):
            _digest(digest)
        _identifier(self.source_translation_session_id)
        _identifier(self.parent_review_execution_session_id)
        if type(self.title_context) is not tuple or not self.title_context:
            raise AbsorptionGroupReviewError("full-title context is required")
        if tuple(c.source_index for c in self.title_context) != tuple(range(len(self.title_context))):
            raise AbsorptionGroupReviewError("full-title context order differs")
        for cue in self.title_context:
            if type(cue) is not QualityReviewInputCue:
                raise AbsorptionGroupReviewError("invalid full-title context cue")
            cue.__post_init__()
        if any(
            cue.cue_id != HybridCueIdentity.for_external_ja(cue.source_index).cue_id
            for cue in self.title_context
        ):
            raise AbsorptionGroupReviewError("full-title cue identity differs from source index")
        if type(self.groups) is not tuple or not self.groups:
            raise AbsorptionGroupReviewError("at least one repair group is required")
        if len({group.scope.group_id for group in self.groups}) != len(self.groups):
            raise AbsorptionGroupReviewError("duplicate group scope")
        if tuple(group.scope.source_indexes[0] for group in self.groups) != tuple(sorted(
            group.scope.source_indexes[0] for group in self.groups
        )):
            raise AbsorptionGroupReviewError("groups are not in source order")
        for group in self.groups:
            if type(group) is not AbsorptionGroupReviewGroup:
                raise AbsorptionGroupReviewError("invalid absorption group type")
            group.__post_init__()
            expected_cues = tuple(
                self.title_context[index] for index in group.scope.source_indexes
            )
            if group.member_cues != expected_cues:
                raise AbsorptionGroupReviewError("group members differ from full-title context")
            if (
                group.scope.parent_review_request_sha256 != self.parent_review_request_sha256
                or group.scope.parent_review_result_sha256 != self.parent_review_result_sha256
                or group.scope.source_translation_session_id != self.source_translation_session_id
                or group.scope.parent_review_execution_session_id != self.parent_review_execution_session_id
            ):
                raise AbsorptionGroupReviewError("group scope is detached from parent review")


def serialize_absorption_group_review_request(
    request: AbsorptionGroupReviewRequest,
) -> bytes:
    if type(request) is not AbsorptionGroupReviewRequest:
        raise AbsorptionGroupReviewError("wrong group review request type")
    request.__post_init__()
    return _json(asdict(request))


def absorption_group_review_request_sha256(
    request: AbsorptionGroupReviewRequest,
) -> str:
    return _sha(serialize_absorption_group_review_request(request))


def build_absorption_group_review_request(
    *, preparation, package: StatefulSubtitlePackage,
    first_pass_result: StatefulSubtitleResult,
    review_request: QualityReviewRequest,
    review_result: QualityReviewResult,
    source_quality: tuple[SourceQualityDecision, ...],
    raw_asr_context=None,
    proximity_asr_artifact=None,
    targeted_second_evidence_artifact=None,
) -> AbsorptionGroupReviewRequest | None:
    """Build a sidecar only for validated groups requiring owner-REPAIR scope.

    ``None`` means there is no absorption group whose owner has a per-cue
    REPAIR. Unsupported group actions fail closed before a model request exists.
    """
    from teddy_discovery_stateful_hybrid import StatefulHybridPreparation

    if type(preparation) is not StatefulHybridPreparation:
        raise AbsorptionGroupReviewError("original HYBRID preparation is required")
    if type(package) is not StatefulSubtitlePackage or package != preparation.package:
        raise AbsorptionGroupReviewError("package differs from original preparation")
    try:
        preparation.__post_init__()
        first_pass = validate_stateful_result(first_pass_result, package)
        validated_request = validate_review_request(
            review_request,
            preparation=preparation,
            package=package,
            result=first_pass,
            source_quality=source_quality,
            raw_asr_context=raw_asr_context,
            proximity_asr_artifact=proximity_asr_artifact,
            targeted_second_evidence_artifact=targeted_second_evidence_artifact,
        )
        validated_result = validate_review_result(review_result, validated_request)
        if (validated_result.source_translation_session_id is not None
                and validated_result.source_translation_session_id
                != validated_request.source_translation_session_id):
            raise AbsorptionGroupReviewError("parent review source provenance differs")
        if validated_result.review_execution_session_id is not None:
            validate_canonical_review_execution_session_id(
                validated_result.review_execution_session_id
            )
        if type(source_quality) is not tuple or len(source_quality) != len(package.cues):
            raise AbsorptionGroupReviewError("source quality evidence is incomplete")
        if not stateful_absorption_is_enabled(package.generation_key):
            return None
        boundary = getattr(first_pass, "boundary_evidence", None)
        if boundary is None:
            raise AbsorptionGroupReviewError("canonical absorption boundary is missing")
        validate_stateful_boundary_evidence(boundary, package, preparation=preparation)
        chains = validate_stateful_absorption(
            first_pass.cues, package, boundary
        )
    except AbsorptionGroupReviewError:
        raise
    except (QualityReviewError, TypeError, ValueError) as error:
        raise AbsorptionGroupReviewError("parent or absorption evidence is invalid") from error

    parent_request_sha = review_request_sha256(validated_request)
    parent_result_sha = _sha(serialize_review_result(validated_result, validated_request))
    package_sha = _sha(serialize_stateful_package(package))
    first_pass_sha = _sha(serialize_stateful_result(first_pass))
    boundary_sha = _sha(serialize_stateful_boundary_evidence(boundary))
    source_sha = validated_request.source_sha256
    positions = {cue.cue_id: index for index, cue in enumerate(package.cues)}
    groups = []
    for chain in chains:
        if len(chain.cue_ids) < 2:
            continue
        indexes = chain.source_indexes
        if any(source_quality[index].action == OMIT_METADATA for index in indexes):
            if any(validated_result.cues[index].action == REPAIR for index in indexes):
                raise AbsorptionGroupReviewError("metadata omission conflicts with group repair")
            continue
        owner_index = positions.get(chain.owner_cue_id)
        if owner_index is None or chain.owner_cue_id not in chain.cue_ids:
            raise AbsorptionGroupReviewError("absorption owner differs from source order")
        actions = tuple(validated_result.cues[index].action for index in indexes)
        repairs = tuple(index for index in indexes if validated_result.cues[index].action == REPAIR)
        if not repairs:
            continue
        if validated_result.review_execution_session_id is None:
            raise AbsorptionGroupReviewError("parent review execution provenance is missing")
        if repairs != (owner_index,) or any(
            validated_result.cues[index].action not in {KEEP, AMBIGUOUS}
            for index in indexes if index != owner_index
        ):
            raise AbsorptionGroupReviewError("absorption group has unsupported repair or omission conflict")
        if any(first_pass.cues[index].ko is not None
               for index in indexes if index != owner_index):
            raise AbsorptionGroupReviewError("non-owner has an independent Korean translation")
        if first_pass.cues[owner_index].ko is None:
            raise AbsorptionGroupReviewError("group owner has no Korean translation")
        member_cues = tuple(validated_request.cues[index] for index in indexes)
        member_decisions = tuple(validated_result.cues[index] for index in indexes)
        if validated_result.cues[owner_index].action != REPAIR:
            raise AbsorptionGroupReviewError("owner REPAIR is not present")
        scope = _make_scope(
            chain=chain,
            package_sha256=package_sha,
            first_pass_sha256=first_pass_sha,
            source_sha256=source_sha,
            boundary_evidence_sha256=boundary_sha,
            source_translation_session_id=validated_request.source_translation_session_id,
            parent_review_execution_session_id=validated_result.review_execution_session_id,
            parent_review_request_sha256=parent_request_sha,
            parent_review_result_sha256=parent_result_sha,
            targeted_evidence_sha256=_targeted_evidence_sha256(member_cues),
        )
        groups.append(AbsorptionGroupReviewGroup(scope, member_cues, member_decisions))
    if not groups:
        return None
    request = AbsorptionGroupReviewRequest(
        ABSORPTION_GROUP_REVIEW_SCHEMA_VERSION,
        parent_request_sha,
        parent_result_sha,
        validated_request.source_translation_session_id,
        validated_result.review_execution_session_id,
        validated_request.cues,
        tuple(groups),
    )
    serialize_absorption_group_review_request(request)
    return request


def validate_absorption_group_review_request(
    request: AbsorptionGroupReviewRequest,
    **originals,
) -> AbsorptionGroupReviewRequest:
    """Rebuild group scope from caller-held originals at each trust boundary."""
    if type(request) is not AbsorptionGroupReviewRequest:
        raise AbsorptionGroupReviewError("exact group review request required")
    expected = build_absorption_group_review_request(**originals)
    if expected is None or expected != request:
        raise AbsorptionGroupReviewError("group request differs from original absorption evidence")
    serialize_absorption_group_review_request(request)
    return request


def parse_absorption_group_review_request(
    payload: bytes,
    **originals,
) -> AbsorptionGroupReviewRequest:
    if type(payload) is not bytes or not 0 < len(payload) <= ABSORPTION_GROUP_REVIEW_MAX_BYTES:
        raise AbsorptionGroupReviewError("group request is outside byte bound")
    expected = build_absorption_group_review_request(**originals)
    if expected is None or serialize_absorption_group_review_request(expected) != payload:
        raise AbsorptionGroupReviewError("group request payload differs from original evidence")
    return expected


@dataclass(frozen=True)
class AbsorptionGroupReviewDecision:
    group_id: str
    action: str
    reason: str
    replacement_ja: str | None = None
    replacement_ko: str | None = None

    def __post_init__(self):
        _digest(self.group_id)
        if type(self.action) is not str or self.action not in _GROUP_ACTIONS:
            raise AbsorptionGroupReviewError("unsupported group review action")
        try:
            _text(self.reason, limit=1024)
        except QualityReviewError as error:
            raise AbsorptionGroupReviewError("invalid group review reason") from error
        if self.action == GROUP_REVIEW_REPAIR:
            try:
                _text(self.replacement_ja, limit=MAX_CUE_TEXT_CHARS)
                _text(self.replacement_ko, limit=MAX_CUE_TEXT_CHARS)
            except QualityReviewError as error:
                raise AbsorptionGroupReviewError("group REPAIR needs bounded JA and KO") from error
            if any("HANGUL" in unicodedata.name(char, "") for char in self.replacement_ja):
                raise AbsorptionGroupReviewError("group replacement Japanese contains Hangul")
            if has_runaway_repetition(self.replacement_ja) or has_runaway_repetition(self.replacement_ko):
                raise AbsorptionGroupReviewError("group replacement has runaway repetition")
        elif self.replacement_ja is not None or self.replacement_ko is not None:
            raise AbsorptionGroupReviewError("only group REPAIR permits replacement text")


@dataclass(frozen=True)
class AbsorptionGroupReviewResult:
    schema_version: int
    request_sha256: str
    decisions: tuple[AbsorptionGroupReviewDecision, ...]
    source_translation_session_id: str | None = None
    parent_review_execution_session_id: str | None = None
    review_execution_session_id: str | None = None

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != ABSORPTION_GROUP_REVIEW_SCHEMA_VERSION:
            raise AbsorptionGroupReviewError("unsupported group result schema")
        _digest(self.request_sha256)
        provenance = (
            self.source_translation_session_id,
            self.parent_review_execution_session_id,
            self.review_execution_session_id,
        )
        if all(value is None for value in provenance):
            pass
        elif any(value is None for value in provenance):
            raise AbsorptionGroupReviewError("group result provenance is incomplete")
        else:
            _identifier(self.source_translation_session_id)
            _identifier(self.parent_review_execution_session_id)
            try:
                validate_canonical_review_execution_session_id(self.review_execution_session_id)
            except Exception as error:
                raise AbsorptionGroupReviewError("group execution session is not canonical") from error
        if type(self.decisions) is not tuple or not self.decisions:
            raise AbsorptionGroupReviewError("group result decisions are empty")
        if len({decision.group_id for decision in self.decisions}) != len(self.decisions):
            raise AbsorptionGroupReviewError("duplicate group review decision")
        for decision in self.decisions:
            if type(decision) is not AbsorptionGroupReviewDecision:
                raise AbsorptionGroupReviewError("invalid group result decision type")
            decision.__post_init__()


def validate_absorption_group_review_result(
    result: AbsorptionGroupReviewResult,
    request: AbsorptionGroupReviewRequest,
    *, review_execution_session_id: str,
) -> AbsorptionGroupReviewResult:
    if type(request) is not AbsorptionGroupReviewRequest:
        raise AbsorptionGroupReviewError("exact group review request required")
    request.__post_init__()
    if type(result) is not AbsorptionGroupReviewResult:
        raise AbsorptionGroupReviewError("exact group review result required")
    result.__post_init__()
    expected_session = validate_canonical_review_execution_session_id(review_execution_session_id)
    if (
        result.request_sha256 != absorption_group_review_request_sha256(request)
        or result.source_translation_session_id not in {None, request.source_translation_session_id}
        or result.parent_review_execution_session_id not in {None, request.parent_review_execution_session_id}
        or result.review_execution_session_id not in {None, expected_session}
        or tuple(decision.group_id for decision in result.decisions)
        != tuple(group.scope.group_id for group in request.groups)
    ):
        raise AbsorptionGroupReviewError("group result differs from exact request or session")
    from dataclasses import replace

    return replace(
        result,
        source_translation_session_id=request.source_translation_session_id,
        parent_review_execution_session_id=request.parent_review_execution_session_id,
        review_execution_session_id=expected_session,
    )


def serialize_absorption_group_review_result(
    result: AbsorptionGroupReviewResult,
    request: AbsorptionGroupReviewRequest,
    *, review_execution_session_id: str,
) -> bytes:
    validated = validate_absorption_group_review_result(
        result, request, review_execution_session_id=review_execution_session_id
    )
    return _json({
        "schema_version": validated.schema_version,
        "request_sha256": validated.request_sha256,
        "decisions": [asdict(decision) for decision in validated.decisions],
    })


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise AbsorptionGroupReviewError("duplicate JSON field")
        value[key] = item
    return value


def parse_absorption_group_review_result(
    payload: bytes,
    request: AbsorptionGroupReviewRequest,
    *, review_execution_session_id: str,
) -> AbsorptionGroupReviewResult:
    if type(payload) is not bytes or not 0 < len(payload) <= ABSORPTION_GROUP_REVIEW_MAX_BYTES:
        raise AbsorptionGroupReviewError("group result is outside byte bound")
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_object,
        )
        if type(value) is not dict or set(value) != {
            "schema_version", "request_sha256", "decisions",
        }:
            raise AbsorptionGroupReviewError("group result fields are invalid")
        decisions = value["decisions"]
        if type(decisions) is not list:
            raise AbsorptionGroupReviewError("group result decisions are malformed")
        parsed_decisions = []
        for item in decisions:
            if type(item) is not dict or set(item) != {
                "group_id", "action", "reason", "replacement_ja", "replacement_ko",
            }:
                raise AbsorptionGroupReviewError("group decision fields are invalid")
            parsed_decisions.append(AbsorptionGroupReviewDecision(**item))
        result = AbsorptionGroupReviewResult(
            value["schema_version"],
            value["request_sha256"],
            tuple(parsed_decisions),
        )
    except AbsorptionGroupReviewError:
        raise
    except (KeyError, TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise AbsorptionGroupReviewError("group result is malformed") from error
    canonical = serialize_absorption_group_review_result(
        result, request, review_execution_session_id=review_execution_session_id
    )
    if canonical != payload:
        raise AbsorptionGroupReviewError("group result is not canonical JSON")
    return result


@dataclass(frozen=True)
class AbsorptionGroupReviewExecutionEvidence:
    """Raw caller-held receipt bundle returned by the existing native bridge."""

    request_payload: bytes
    result_payload: bytes
    receipt_payload: bytes
    remote_task: str
    receipt_nonce: str
    review_execution_session_id: str


def validate_absorption_group_review_execution(
    evidence: AbsorptionGroupReviewExecutionEvidence,
    request: AbsorptionGroupReviewRequest,
) -> AbsorptionGroupReviewResult:
    if type(evidence) is not AbsorptionGroupReviewExecutionEvidence:
        raise AbsorptionGroupReviewError("group completion receipt evidence is required")
    request_payload = serialize_absorption_group_review_request(request)
    if evidence.request_payload != request_payload:
        raise AbsorptionGroupReviewError("group request payload differs from original scope")
    session_id = validate_canonical_review_execution_session_id(
        evidence.review_execution_session_id
    )
    try:
        from teddy_discovery_stateful_live_runner import validate_stateful_remote_task_path
        from teddy_discovery_stage11_deployment import _parse_review_execution_receipt

        task = validate_stateful_remote_task_path(evidence.remote_task)
        if PurePosixPath(task).name != session_id:
            raise AbsorptionGroupReviewError(
                "remote review task does not belong to its execution session"
            )
        request_sha = _sha(request_payload)
        receipt = _parse_review_execution_receipt(
            evidence.receipt_payload,
            session_id=session_id,
            task_sha256=_sha(task.encode("utf-8")),
            request_sha256=request_sha,
            input_sha256=request_sha,
            receipt_nonce=evidence.receipt_nonce,
        )
    except Exception as error:
        raise AbsorptionGroupReviewError("native review completion receipt is invalid") from error
    if (
        receipt["child_outcome"] != "COMPLETED"
        or receipt["child_returncode"] != 0
        or receipt["result_state"] != "PRESENT"
        or type(evidence.result_payload) is not bytes
        or len(evidence.result_payload) != receipt["result_size_bytes"]
        or _sha(evidence.result_payload) != receipt["result_sha256"]
    ):
        raise AbsorptionGroupReviewError("group review result is not receipt-verified")
    try:
        return parse_absorption_group_review_result(
            evidence.result_payload,
            request,
            review_execution_session_id=session_id,
        )
    except AbsorptionGroupReviewError:
        raise


__all__ = [
    "ABSORPTION_GROUP_REVIEW_SCHEMA_VERSION",
    "ABSORPTION_GROUP_REVIEW_INPUT_FILENAME",
    "ABSORPTION_GROUP_REVIEW_RESULT_FILENAME",
    "ABSORPTION_GROUP_REVIEW_QUERY",
    "AbsorptionGroupReviewDecision",
    "AbsorptionGroupReviewError",
    "AbsorptionGroupReviewExecutionEvidence",
    "AbsorptionGroupReviewGroup",
    "AbsorptionGroupReviewRequest",
    "AbsorptionGroupReviewResult",
    "AbsorptionGroupScope",
    "GROUP_REVIEW_AMBIGUOUS",
    "GROUP_REVIEW_KEEP",
    "GROUP_REVIEW_REPAIR",
    "GROUP_REVIEW_UNSUPPORTED",
    "absorption_group_review_request_sha256",
    "build_absorption_group_review_request",
    "parse_absorption_group_review_request",
    "parse_absorption_group_review_result",
    "serialize_absorption_group_review_request",
    "serialize_absorption_group_review_result",
    "validate_absorption_group_review_execution",
    "validate_absorption_group_review_request",
    "validate_absorption_group_review_result",
]
