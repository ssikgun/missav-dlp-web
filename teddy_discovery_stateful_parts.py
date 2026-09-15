"""Deterministic stateful subtitle semantic-part controller.

The stateful translator writes only bounded semantic part candidates.  This
module validates those candidates against a deterministic plan, promotes a
validated pending file to one immutable canonical part, resumes from the
first missing canonical part, and assembles the existing Stage11 final result
contract.  It does not invoke Hermes, interpret semantics, own timestamps,
or publish an artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid
from typing import Final

from teddy_discovery_hermes_v2 import HermesV2CueOutput
from teddy_discovery_stateful_translator import (
    StatefulSubtitlePackage,
    StatefulSubtitleResult,
    StatefulTranslatorError,
    StatefulTranslatorStagingError,
    _atomic_private_write,
    _validated_task_directory,
    parse_stateful_package,
    serialize_stateful_package,
    serialize_stateful_result,
    stateful_session_id_for_package,
    stateful_staging_paths,
    validate_stateful_result,
)
from teddy_discovery_stateful_policy import (
    DEFAULT_STATEFUL_SEMANTIC_POLICY,
    STATEFUL_SEMANTIC_POLICIES,
    STATEFUL_SEMANTIC_POLICY_ID_16,
    StatefulSemanticPolicy,
    StatefulSemanticPolicyError,
    resolve_stateful_semantic_policy,
    stateful_policy_id_from_generation_key,
)


STATEFUL_PART_SCHEMA_VERSION: Final[int] = 1
STATEFUL_PART_BATCH_SIZE: Final[int] = 16
STATEFUL_PART_POLICY_ID: Final[str] = STATEFUL_SEMANTIC_POLICY_ID_16
STATEFUL_PART_MAX_BYTES: Final[int] = 16 * 1024 * 1024
STATEFUL_PART_FILE_MODE: Final[int] = 0o600
STATEFUL_PART_FILENAME_PREFIX: Final[str] = "semantic-part-"
STATEFUL_PART_PENDING_SUFFIX: Final[str] = ".pending.json"
STATEFUL_PART_CANONICAL_SUFFIX: Final[str] = ".json"

MAX_STATEFUL_PART_BYTES: Final[int] = STATEFUL_PART_MAX_BYTES

_PART_FILENAME_RE = re.compile(
    r"^semantic-part-(?P<index>[0-9]{4})(?P<pending>\.pending)?\.json$"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

STATEFUL_VALIDATION_REASON_JSON_PARSE_FAILURE: Final[str] = (
    "JSON_PARSE_FAILURE"
)
STATEFUL_VALIDATION_REASON_SCHEMA_FAILURE: Final[str] = "SCHEMA_FAILURE"
STATEFUL_VALIDATION_REASON_SESSION_ID_MISMATCH: Final[str] = (
    "SESSION_ID_MISMATCH"
)
STATEFUL_VALIDATION_REASON_INPUT_SHA256_MISMATCH: Final[str] = (
    "INPUT_SHA256_MISMATCH"
)
STATEFUL_VALIDATION_REASON_PART_INDEX_MISMATCH: Final[str] = (
    "PART_INDEX_MISMATCH"
)
STATEFUL_VALIDATION_REASON_FIRST_CUE_ID_MISMATCH: Final[str] = (
    "FIRST_CUE_ID_MISMATCH"
)
STATEFUL_VALIDATION_REASON_LAST_CUE_ID_MISMATCH: Final[str] = (
    "LAST_CUE_ID_MISMATCH"
)
STATEFUL_VALIDATION_REASON_CUE_COUNT_MISMATCH: Final[str] = (
    "CUE_COUNT_MISMATCH"
)
STATEFUL_VALIDATION_REASON_MISSING_CUE_ID: Final[str] = "MISSING_CUE_ID"
STATEFUL_VALIDATION_REASON_DUPLICATE_CUE_ID: Final[str] = (
    "DUPLICATE_CUE_ID"
)
STATEFUL_VALIDATION_REASON_UNEXPECTED_CUE_ID: Final[str] = (
    "UNEXPECTED_CUE_ID"
)
STATEFUL_VALIDATION_REASON_CUE_ORDER_MISMATCH: Final[str] = (
    "CUE_ORDER_MISMATCH"
)
STATEFUL_VALIDATION_REASON_INVALID_REPAIRED_JA: Final[str] = (
    "INVALID_REPAIRED_JA"
)
STATEFUL_VALIDATION_REASON_INVALID_KO: Final[str] = "INVALID_KO"
STATEFUL_VALIDATION_REASON_INVALID_FIELD: Final[str] = "INVALID_FIELD"
STATEFUL_VALIDATION_REASON_OTHER_VALIDATOR_PREDICATE: Final[str] = (
    "OTHER_VALIDATOR_PREDICATE"
)


class StatefulPartsError(ValueError):
    """Base class for deterministic semantic-part failures."""


class StatefulPartsValidationError(StatefulPartsError):
    """Raised when a semantic part is malformed or detached."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str = STATEFUL_VALIDATION_REASON_OTHER_VALIDATOR_PREDICATE,
    ) -> None:
        self.reason_code = reason_code
        super().__init__(message)


class StatefulPartsLimitError(StatefulPartsValidationError):
    """Raised when a semantic part exceeds a fixed local bound."""


class StatefulPartsFilenameError(StatefulPartsError):
    """Raised when a part path is not an exact safe filename."""


class StatefulPartsPromotionError(StatefulPartsError):
    """Raised when a pending part cannot become canonical."""


class StatefulPartsAssemblyError(StatefulPartsError):
    """Raised when a complete final result cannot be materialized."""


_SUPPORTED_PART_BATCH_SIZES: Final[frozenset[int]] = frozenset(
    policy.max_cues_per_part for policy in STATEFUL_SEMANTIC_POLICIES
)


def _resolve_semantic_policy(
    value: StatefulSemanticPolicy | str,
) -> StatefulSemanticPolicy:
    try:
        return resolve_stateful_semantic_policy(value)
    except StatefulSemanticPolicyError as error:
        raise StatefulPartsValidationError(
            "semantic policy is unsupported or inconsistent"
        ) from error


def _require_policy_batch_size(value: object) -> int:
    if type(value) is not int or value not in _SUPPORTED_PART_BATCH_SIZES:
        raise StatefulPartsValidationError(
            "semantic policy batch size is unsupported"
        )
    return value


def _require_package_policy_binding(
    package: StatefulSubtitlePackage,
    policy: StatefulSemanticPolicy,
) -> None:
    try:
        bound_policy_id = stateful_policy_id_from_generation_key(
            package.generation_key
        )
    except StatefulSemanticPolicyError as error:
        raise StatefulPartsValidationError(
            "package generation identity has an invalid semantic policy"
        ) from error

    if policy == DEFAULT_STATEFUL_SEMANTIC_POLICY:
        if bound_policy_id not in {None, policy.policy_id}:
            raise StatefulPartsValidationError(
                "package is bound to a different semantic policy"
            )
        return

    if bound_policy_id != policy.policy_id:
        raise StatefulPartsValidationError(
            "candidate package is not bound to its semantic policy"
        )


def _require_exact_string(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise StatefulPartsValidationError(
            field_name + " must be an exact string",
            reason_code=STATEFUL_VALIDATION_REASON_INVALID_FIELD,
        )
    if not value or value != value.strip():
        raise StatefulPartsValidationError(
            field_name + " must be nonempty and bounded",
            reason_code=STATEFUL_VALIDATION_REASON_INVALID_FIELD,
        )
    if any(
        ord(character) < 32
        or ord(character) == 127
        or character.isspace()
        for character in value
    ):
        raise StatefulPartsValidationError(
            field_name + " contains unsafe whitespace or control data",
            reason_code=STATEFUL_VALIDATION_REASON_INVALID_FIELD,
        )
    return value


def _require_sha256(value: object) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise StatefulPartsValidationError(
            "input_sha256 must be lowercase hexadecimal SHA256",
            reason_code=STATEFUL_VALIDATION_REASON_INVALID_FIELD,
        )
    return value


def _require_session_id(value: object) -> str:
    if type(value) is not str:
        raise StatefulPartsValidationError(
            "session_id must be an exact string",
            reason_code=STATEFUL_VALIDATION_REASON_INVALID_FIELD,
        )
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, TypeError, ValueError) as error:
        raise StatefulPartsValidationError(
            "session_id must be a canonical UUID",
            reason_code=STATEFUL_VALIDATION_REASON_INVALID_FIELD,
        ) from error
    if str(parsed) != value:
        raise StatefulPartsValidationError(
            "session_id must be a canonical UUID",
            reason_code=STATEFUL_VALIDATION_REASON_INVALID_FIELD,
        )
    return value


def _require_part_index(value: object) -> int:
    if type(value) is not int or value <= 0:
        raise StatefulPartsValidationError(
            "part_index must be a positive exact integer",
            reason_code=STATEFUL_VALIDATION_REASON_INVALID_FIELD,
        )
    return value


STATEFUL_PART_RUNAWAY_MIN_TEXT_CHARS = 64
STATEFUL_PART_RUNAWAY_MAX_UNIT_CHARS = 4
STATEFUL_PART_RUNAWAY_MIN_REPETITIONS = 16


def _has_runaway_repetition(text: str) -> bool:
    """Detect only an extreme whole-string repeated short-unit pattern."""

    analysis = "".join(text.split())

    if len(analysis) < STATEFUL_PART_RUNAWAY_MIN_TEXT_CHARS:
        return False

    max_unit_chars = min(
        STATEFUL_PART_RUNAWAY_MAX_UNIT_CHARS,
        len(analysis) // STATEFUL_PART_RUNAWAY_MIN_REPETITIONS,
    )

    for unit_chars in range(1, max_unit_chars + 1):
        if len(analysis) % unit_chars != 0:
            continue

        repetitions = len(analysis) // unit_chars

        if repetitions < STATEFUL_PART_RUNAWAY_MIN_REPETITIONS:
            continue

        unit = analysis[:unit_chars]

        if unit * repetitions == analysis:
            return True

    return False


def has_runaway_repetition(text: str) -> bool:
    """Reuse the frozen extreme whole-string repetition detector."""

    if type(text) is not str:
        raise StatefulPartsValidationError(
            "repetition analysis requires an exact string"
        )
    return _has_runaway_repetition(text)


def _validated_output_cue(value: object) -> HermesV2CueOutput:
    if type(value) is not HermesV2CueOutput:
        raise StatefulPartsValidationError(
            "part cue has the wrong exact type",
            reason_code=STATEFUL_VALIDATION_REASON_INVALID_FIELD,
        )
    try:
        validated = HermesV2CueOutput(
            cue_id=value.cue_id,
            repaired_ja=value.repaired_ja,
            ko=value.ko,
        )
    except (AttributeError, TypeError, ValueError, OverflowError) as error:
        raise StatefulPartsValidationError(
            "part cue is invalid or detached",
            reason_code=STATEFUL_VALIDATION_REASON_INVALID_FIELD,
        ) from error

    if has_runaway_repetition(validated.ko):
        raise StatefulPartsValidationError(
            "part cue ko contains an extreme repeated short-unit pattern",
            reason_code=STATEFUL_VALIDATION_REASON_INVALID_KO,
        )

    if (
        validated.repaired_ja is not None
        and has_runaway_repetition(validated.repaired_ja)
    ):
        raise StatefulPartsValidationError(
            "part cue repaired_ja contains an extreme repeated short-unit pattern",
            reason_code=STATEFUL_VALIDATION_REASON_INVALID_REPAIRED_JA,
        )

    if (
        validated.repaired_ja is not None
        and any(
            "\uac00" <= char <= "\ud7a3"
            or "\u1100" <= char <= "\u11ff"
            or "\u3130" <= char <= "\u318f"
            for char in validated.repaired_ja
        )
    ):
        raise StatefulPartsValidationError(
            "part cue repaired_ja must not contain Korean script",
            reason_code=STATEFUL_VALIDATION_REASON_INVALID_REPAIRED_JA,
        )

    return validated


@dataclass(frozen=True)
class ExpectedStatefulPart:
    """One deterministic range derived from the frozen package order."""

    part_index: int
    first_cue_id: str
    last_cue_id: str
    cue_ids: tuple[str, ...]
    max_cues_per_part: int = STATEFUL_PART_BATCH_SIZE

    def __post_init__(self):
        _require_part_index(self.part_index)
        _require_policy_batch_size(self.max_cues_per_part)
        _require_exact_string(self.first_cue_id, "first_cue_id")
        _require_exact_string(self.last_cue_id, "last_cue_id")
        if type(self.cue_ids) is not tuple or not self.cue_ids:
            raise StatefulPartsValidationError(
                "expected part cue_ids must be a nonempty tuple"
            )
        if tuple(
            _require_exact_string(cue_id, "cue_id")
            for cue_id in self.cue_ids
        ) != self.cue_ids:
            raise StatefulPartsValidationError(
                "expected part cue IDs are invalid"
            )
        if self.cue_ids[0] != self.first_cue_id:
            raise StatefulPartsValidationError(
                "expected first cue identity is detached"
            )
        if self.cue_ids[-1] != self.last_cue_id:
            raise StatefulPartsValidationError(
                "expected last cue identity is detached"
            )
        if len(set(self.cue_ids)) != len(self.cue_ids):
            raise StatefulPartsValidationError(
                "expected part cue IDs must be unique"
            )
        if len(self.cue_ids) > self.max_cues_per_part:
            raise StatefulPartsLimitError(
                "expected part exceeds the stateful part batch size"
            )

    @property
    def cue_count(self) -> int:
        return len(self.cue_ids)

    @property
    def pending_filename(self) -> str:
        return stateful_part_filename(self.part_index, pending=True)

    @property
    def canonical_filename(self) -> str:
        return stateful_part_filename(self.part_index, pending=False)


@dataclass(frozen=True)
class StatefulPartPlan:
    """Immutable package identity and all expected semantic part ranges."""

    dvd_id: str
    generation_key: str
    claim_token: int
    session_id: str
    input_sha256: str
    parts: tuple[ExpectedStatefulPart, ...]
    policy_id: str = STATEFUL_PART_POLICY_ID
    max_cues_per_part: int = STATEFUL_PART_BATCH_SIZE

    def __post_init__(self):
        if type(self.policy_id) is not str:
            raise StatefulPartsValidationError(
                "part plan policy ID must be an exact string"
            )
        policy = _resolve_semantic_policy(self.policy_id)
        if self.max_cues_per_part != policy.max_cues_per_part:
            raise StatefulPartsValidationError(
                "part plan policy and batch size do not match"
            )
        _require_policy_batch_size(self.max_cues_per_part)
        _require_exact_string(self.dvd_id, "dvd_id")
        _require_exact_string(self.generation_key, "generation_key")
        if type(self.claim_token) is not int or self.claim_token < 0:
            raise StatefulPartsValidationError(
                "claim_token must be a nonnegative exact integer"
            )
        _require_session_id(self.session_id)
        _require_sha256(self.input_sha256)
        if type(self.parts) is not tuple or not self.parts:
            raise StatefulPartsValidationError(
                "part plan must contain an immutable nonempty tuple"
            )
        if any(type(part) is not ExpectedStatefulPart for part in self.parts):
            raise StatefulPartsValidationError(
                "part plan contains a detached expected part"
            )
        if any(
            part.max_cues_per_part != self.max_cues_per_part
            for part in self.parts
        ):
            raise StatefulPartsValidationError(
                "part plan contains a range with a different batch size"
            )
        expected_indices = tuple(range(1, len(self.parts) + 1))
        actual_indices = tuple(part.part_index for part in self.parts)
        if actual_indices != expected_indices:
            raise StatefulPartsValidationError(
                "part plan indices must be contiguous from one"
            )

    @property
    def part_count(self) -> int:
        return len(self.parts)


@dataclass(frozen=True)
class StatefulSemanticPart:
    """Validated pending or canonical semantic part data."""

    part_schema_version: int
    session_id: str
    input_sha256: str
    part_index: int
    first_cue_id: str
    last_cue_id: str
    cues: tuple[HermesV2CueOutput, ...]
    max_cues_per_part: int = STATEFUL_PART_BATCH_SIZE

    def __post_init__(self):
        if type(self.part_schema_version) is not int or self.part_schema_version != STATEFUL_PART_SCHEMA_VERSION:
            raise StatefulPartsValidationError(
                "unsupported stateful part schema version",
                reason_code=STATEFUL_VALIDATION_REASON_SCHEMA_FAILURE,
            )
        _require_policy_batch_size(self.max_cues_per_part)
        _require_session_id(self.session_id)
        _require_sha256(self.input_sha256)
        _require_part_index(self.part_index)
        _require_exact_string(self.first_cue_id, "first_cue_id")
        _require_exact_string(self.last_cue_id, "last_cue_id")
        if type(self.cues) is not tuple or not self.cues:
            raise StatefulPartsValidationError(
                "part cues must be an immutable nonempty tuple",
                reason_code=STATEFUL_VALIDATION_REASON_SCHEMA_FAILURE,
            )
        if len(self.cues) > self.max_cues_per_part:
            raise StatefulPartsLimitError(
                "part exceeds the stateful part batch size",
                reason_code=STATEFUL_VALIDATION_REASON_SCHEMA_FAILURE,
            )
        validated_cues = tuple(
            _validated_output_cue(cue)
            for cue in self.cues
        )
        if validated_cues[0].cue_id != self.first_cue_id:
            raise StatefulPartsValidationError(
                "part first cue identity does not match its cues",
                reason_code=STATEFUL_VALIDATION_REASON_FIRST_CUE_ID_MISMATCH,
            )
        if validated_cues[-1].cue_id != self.last_cue_id:
            raise StatefulPartsValidationError(
                "part last cue identity does not match its cues",
                reason_code=STATEFUL_VALIDATION_REASON_LAST_CUE_ID_MISMATCH,
            )
        cue_ids = tuple(cue.cue_id for cue in validated_cues)
        if len(set(cue_ids)) != len(cue_ids):
            raise StatefulPartsValidationError(
                "part cue IDs must be unique",
                reason_code=STATEFUL_VALIDATION_REASON_DUPLICATE_CUE_ID,
            )


@dataclass(frozen=True)
class StatefulPartScan:
    """Canonical completion state for one deterministic part plan."""

    expected_parts: tuple[ExpectedStatefulPart, ...]
    canonical_parts: tuple[StatefulSemanticPart, ...]
    pending_parts: tuple[StatefulSemanticPart, ...]
    first_missing_part: ExpectedStatefulPart | None

    def __post_init__(self):
        if type(self.expected_parts) is not tuple:
            raise StatefulPartsValidationError(
                "scan expected parts must be an immutable tuple"
            )
        if type(self.canonical_parts) is not tuple:
            raise StatefulPartsValidationError(
                "scan canonical parts must be an immutable tuple"
            )
        if type(self.pending_parts) is not tuple:
            raise StatefulPartsValidationError(
                "scan pending parts must be an immutable tuple"
            )
        if self.first_missing_part is not None and type(
            self.first_missing_part
        ) is not ExpectedStatefulPart:
            raise StatefulPartsValidationError(
                "scan missing part is detached"
            )

    @property
    def complete(self) -> bool:
        return self.first_missing_part is None

    @property
    def is_complete(self) -> bool:
        return self.complete


def stateful_part_filename(part_index: int, *, pending: bool) -> str:
    """Return the only filename allowed for one positive part index."""

    part_index = _require_part_index(part_index)
    suffix = (
        STATEFUL_PART_PENDING_SUFFIX
        if pending
        else STATEFUL_PART_CANONICAL_SUFFIX
    )
    return (
        STATEFUL_PART_FILENAME_PREFIX
        + f"{part_index:04d}"
        + suffix
    )


def _parse_part_filename(filename: object) -> tuple[int, bool]:
    if type(filename) is not str:
        raise StatefulPartsFilenameError(
            "part filename must be an exact string"
        )
    if (
        not filename
        or filename != Path(filename).name
        or "/" in filename
        or "\\" in filename
        or filename in {".", ".."}
    ):
        raise StatefulPartsFilenameError(
            "part filename contains an unsafe path component"
        )
    match = _PART_FILENAME_RE.fullmatch(filename)
    if match is None:
        raise StatefulPartsFilenameError(
            "part filename does not match the exact stateful part pattern"
        )
    index_text = match.group("index")
    part_index = int(index_text)
    if stateful_part_filename(
        part_index,
        pending=match.group("pending") is not None,
    ) != filename:
        raise StatefulPartsFilenameError(
            "part filename is not canonically zero-padded"
        )
    return part_index, match.group("pending") is not None


def expected_part_filename(
    part_index: int,
    *,
    pending: bool,
) -> str:
    """Public alias for the exact filename constructor."""

    return stateful_part_filename(part_index, pending=pending)


def _validate_package_for_plan(
    package: StatefulSubtitlePackage,
    semantic_input_bytes: bytes,
) -> StatefulSubtitlePackage:
    if type(semantic_input_bytes) is not bytes or not semantic_input_bytes:
        raise StatefulPartsValidationError(
            "semantic input must be nonempty exact bytes"
        )
    try:
        parsed_package = parse_stateful_package(semantic_input_bytes)
    except StatefulTranslatorError as error:
        raise StatefulPartsValidationError(
            "semantic input package is invalid"
        ) from error
    if type(package) is not StatefulSubtitlePackage:
        raise StatefulPartsValidationError(
            "package must be the exact frozen package type"
        )
    if parsed_package != package:
        raise StatefulPartsValidationError(
            "semantic input package does not match the parsed package"
        )
    return parsed_package


def plan_stateful_parts(
    package: StatefulSubtitlePackage,
    semantic_input_bytes: bytes,
    *,
    semantic_policy: StatefulSemanticPolicy | str = (
        DEFAULT_STATEFUL_SEMANTIC_POLICY
    ),
) -> StatefulPartPlan:
    """Derive immutable ranges and the exact input hash from frozen bytes."""

    policy = _resolve_semantic_policy(semantic_policy)
    validated_package = _validate_package_for_plan(
        package,
        semantic_input_bytes,
    )
    _require_package_policy_binding(validated_package, policy)
    cue_ids = tuple(cue.cue_id for cue in validated_package.cues)
    parts = tuple(
        ExpectedStatefulPart(
            part_index=part_index,
            first_cue_id=cue_ids[start],
            last_cue_id=cue_ids[
                min(start + policy.max_cues_per_part, len(cue_ids)) - 1
            ],
            cue_ids=cue_ids[
                start : start + policy.max_cues_per_part
            ],
            max_cues_per_part=policy.max_cues_per_part,
        )
        for part_index, start in enumerate(
            range(0, len(cue_ids), policy.max_cues_per_part),
            start=1,
        )
    )
    return StatefulPartPlan(
        dvd_id=validated_package.dvd_id,
        generation_key=validated_package.generation_key,
        claim_token=validated_package.claim_token,
        session_id=stateful_session_id_for_package(validated_package),
        input_sha256=hashlib.sha256(semantic_input_bytes).hexdigest(),
        parts=parts,
        policy_id=policy.policy_id,
        max_cues_per_part=policy.max_cues_per_part,
    )


def build_stateful_part_plan(
    package: StatefulSubtitlePackage,
    semantic_input_bytes: bytes,
    *,
    semantic_policy: StatefulSemanticPolicy | str = (
        DEFAULT_STATEFUL_SEMANTIC_POLICY
    ),
) -> StatefulPartPlan:
    """Explicit alias for the deterministic part-plan constructor."""

    return plan_stateful_parts(
        package,
        semantic_input_bytes,
        semantic_policy=semantic_policy,
    )


def _validate_plan(plan: StatefulPartPlan) -> StatefulPartPlan:
    if type(plan) is not StatefulPartPlan:
        raise StatefulPartsValidationError(
            "part plan must be the exact immutable plan type"
        )
    try:
        return StatefulPartPlan(
            dvd_id=plan.dvd_id,
            generation_key=plan.generation_key,
            claim_token=plan.claim_token,
            session_id=plan.session_id,
            input_sha256=plan.input_sha256,
            parts=plan.parts,
            policy_id=plan.policy_id,
            max_cues_per_part=plan.max_cues_per_part,
        )
    except (AttributeError, TypeError, ValueError, OverflowError) as error:
        raise StatefulPartsValidationError(
            "part plan is invalid or detached"
        ) from error


def _validate_plan_against_package(
    plan: StatefulPartPlan,
    package: StatefulSubtitlePackage,
) -> StatefulPartPlan:
    validated_plan = _validate_plan(plan)
    if type(package) is not StatefulSubtitlePackage:
        raise StatefulPartsAssemblyError(
            "package must be the exact frozen package type"
        )
    try:
        policy = _resolve_semantic_policy(validated_plan.policy_id)
        _require_package_policy_binding(package, policy)
    except StatefulPartsValidationError as error:
        raise StatefulPartsAssemblyError(
            "part plan policy is detached from the frozen package"
        ) from error
    expected_session_id = stateful_session_id_for_package(package)
    expected_ids = tuple(cue.cue_id for cue in package.cues)
    planned_ids = tuple(
        cue_id
        for part in validated_plan.parts
        for cue_id in part.cue_ids
    )
    if (
        validated_plan.dvd_id != package.dvd_id
        or validated_plan.generation_key != package.generation_key
        or validated_plan.claim_token != package.claim_token
        or validated_plan.session_id != expected_session_id
        or planned_ids != expected_ids
    ):
        raise StatefulPartsAssemblyError(
            "part plan is detached from the frozen package"
        )
    return validated_plan


def _validated_part(value: object) -> StatefulSemanticPart:
    if type(value) is not StatefulSemanticPart:
        raise StatefulPartsValidationError(
            "part must be the exact immutable part type"
        )
    try:
        return StatefulSemanticPart(
            part_schema_version=value.part_schema_version,
            session_id=value.session_id,
            input_sha256=value.input_sha256,
            part_index=value.part_index,
            first_cue_id=value.first_cue_id,
            last_cue_id=value.last_cue_id,
            cues=value.cues,
            max_cues_per_part=value.max_cues_per_part,
        )
    except (AttributeError, TypeError, ValueError, OverflowError) as error:
        raise StatefulPartsValidationError(
            "part is invalid or detached"
        ) from error


def serialize_stateful_part(part: StatefulSemanticPart) -> bytes:
    """Serialize a validated part as compact deterministic JSON."""

    validated = _validated_part(part)
    return _encode_part_json(
        {
            "part_schema_version": validated.part_schema_version,
            "session_id": validated.session_id,
            "input_sha256": validated.input_sha256,
            "part_index": validated.part_index,
            "first_cue_id": validated.first_cue_id,
            "last_cue_id": validated.last_cue_id,
            "cues": [
                {
                    "cue_id": cue.cue_id,
                    "repaired_ja": cue.repaired_ja,
                    "ko": cue.ko,
                }
                for cue in validated.cues
            ],
        }
    )


def _encode_part_json(data: dict[str, object]) -> bytes:
    try:
        payload = json.dumps(
            data,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, UnicodeError, ValueError) as error:
        raise StatefulPartsValidationError(
            "part could not be serialized deterministically"
        ) from error
    if len(payload) > STATEFUL_PART_MAX_BYTES:
        raise StatefulPartsLimitError(
            "part exceeds its bounded serialized byte limit"
        )
    return payload


def _reject_json_constant(value: str):
    raise StatefulPartsValidationError(
        "JSON constants are not accepted in stateful parts",
        reason_code=STATEFUL_VALIDATION_REASON_JSON_PARSE_FAILURE,
    )


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise StatefulPartsValidationError(
                "duplicate JSON object keys are not accepted",
                reason_code=STATEFUL_VALIDATION_REASON_JSON_PARSE_FAILURE,
            )
        result[key] = value
    return result


def _load_part_json(payload: bytes) -> dict[str, object]:
    if type(payload) is not bytes or not payload:
        raise StatefulPartsValidationError(
            "part must be nonempty exact UTF-8 JSON bytes",
            reason_code=STATEFUL_VALIDATION_REASON_JSON_PARSE_FAILURE,
        )
    if len(payload) > STATEFUL_PART_MAX_BYTES:
        raise StatefulPartsLimitError(
            "part exceeds its bounded serialized byte limit"
        )
    try:
        parsed = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant,
        )
    except StatefulPartsError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise StatefulPartsValidationError(
            "part must be one JSON object without prose",
            reason_code=STATEFUL_VALIDATION_REASON_JSON_PARSE_FAILURE,
        ) from error
    if type(parsed) is not dict:
        raise StatefulPartsValidationError(
            "part root must be a JSON object",
            reason_code=STATEFUL_VALIDATION_REASON_SCHEMA_FAILURE,
        )
    return parsed


def _output_field_validation_reason(error: BaseException) -> str:
    """Classify an existing Hermes output predicate without revalidating it."""

    message = str(error)
    if message.startswith("repaired_ja"):
        return STATEFUL_VALIDATION_REASON_INVALID_REPAIRED_JA
    if message.startswith("ko "):
        return STATEFUL_VALIDATION_REASON_INVALID_KO
    return STATEFUL_VALIDATION_REASON_INVALID_FIELD


def _parse_part_cue(value: object) -> HermesV2CueOutput:
    if type(value) is not dict:
        raise StatefulPartsValidationError(
            "part cue must be a JSON object",
            reason_code=STATEFUL_VALIDATION_REASON_SCHEMA_FAILURE,
        )
    if set(value) != {"cue_id", "repaired_ja", "ko"}:
        raise StatefulPartsValidationError(
            "part cue fields are not exact",
            reason_code=STATEFUL_VALIDATION_REASON_SCHEMA_FAILURE,
        )
    try:
        return HermesV2CueOutput(
            cue_id=value["cue_id"],
            repaired_ja=value["repaired_ja"],
            ko=value["ko"],
        )
    except (TypeError, ValueError, OverflowError) as error:
        raise StatefulPartsValidationError(
            "part cue is invalid",
            reason_code=_output_field_validation_reason(error),
        ) from error


def _part_from_payload(
    payload: bytes,
    expected: ExpectedStatefulPart,
    plan: StatefulPartPlan,
) -> StatefulSemanticPart:
    parsed = _load_part_json(payload)
    if set(parsed) != {
        "part_schema_version",
        "session_id",
        "input_sha256",
        "part_index",
        "first_cue_id",
        "last_cue_id",
        "cues",
    }:
        raise StatefulPartsValidationError(
            "part top-level fields are not exact",
            reason_code=STATEFUL_VALIDATION_REASON_SCHEMA_FAILURE,
        )
    raw_cues = parsed["cues"]
    if type(raw_cues) is not list:
        raise StatefulPartsValidationError(
            "part cues must be a JSON array",
            reason_code=STATEFUL_VALIDATION_REASON_SCHEMA_FAILURE,
        )
    if len(raw_cues) != expected.cue_count:
        raise StatefulPartsValidationError(
            "part cue count does not match its deterministic range",
            reason_code=STATEFUL_VALIDATION_REASON_CUE_COUNT_MISMATCH,
        )
    try:
        part = StatefulSemanticPart(
            part_schema_version=parsed["part_schema_version"],
            session_id=parsed["session_id"],
            input_sha256=parsed["input_sha256"],
            part_index=parsed["part_index"],
            first_cue_id=parsed["first_cue_id"],
            last_cue_id=parsed["last_cue_id"],
            cues=tuple(_parse_part_cue(cue) for cue in raw_cues),
            max_cues_per_part=plan.max_cues_per_part,
        )
    except StatefulPartsError:
        raise
    except (TypeError, ValueError, OverflowError) as error:
        raise StatefulPartsValidationError(
            "part is invalid",
            reason_code=STATEFUL_VALIDATION_REASON_INVALID_FIELD,
        ) from error

    if part.part_schema_version != STATEFUL_PART_SCHEMA_VERSION:
        raise StatefulPartsValidationError(
            "part identity or cue order does not match its deterministic plan",
            reason_code=STATEFUL_VALIDATION_REASON_SCHEMA_FAILURE,
        )
    if part.session_id != plan.session_id:
        raise StatefulPartsValidationError(
            "part identity or cue order does not match its deterministic plan",
            reason_code=STATEFUL_VALIDATION_REASON_SESSION_ID_MISMATCH,
        )
    if part.input_sha256 != plan.input_sha256:
        raise StatefulPartsValidationError(
            "part identity or cue order does not match its deterministic plan",
            reason_code=STATEFUL_VALIDATION_REASON_INPUT_SHA256_MISMATCH,
        )
    if part.part_index != expected.part_index:
        raise StatefulPartsValidationError(
            "part identity or cue order does not match its deterministic plan",
            reason_code=STATEFUL_VALIDATION_REASON_PART_INDEX_MISMATCH,
        )
    if part.first_cue_id != expected.first_cue_id:
        raise StatefulPartsValidationError(
            "part identity or cue order does not match its deterministic plan",
            reason_code=STATEFUL_VALIDATION_REASON_FIRST_CUE_ID_MISMATCH,
        )
    if part.last_cue_id != expected.last_cue_id:
        raise StatefulPartsValidationError(
            "part identity or cue order does not match its deterministic plan",
            reason_code=STATEFUL_VALIDATION_REASON_LAST_CUE_ID_MISMATCH,
        )
    if part.max_cues_per_part != expected.max_cues_per_part:
        raise StatefulPartsValidationError(
            "part identity or cue order does not match its deterministic plan",
            reason_code=STATEFUL_VALIDATION_REASON_SCHEMA_FAILURE,
        )

    actual_cue_ids = tuple(cue.cue_id for cue in part.cues)
    if actual_cue_ids != expected.cue_ids:
        expected_ids = set(expected.cue_ids)
        actual_ids = set(actual_cue_ids)
        if any(cue_id not in actual_ids for cue_id in expected.cue_ids):
            reason_code = STATEFUL_VALIDATION_REASON_MISSING_CUE_ID
        elif any(cue_id not in expected_ids for cue_id in actual_cue_ids):
            reason_code = STATEFUL_VALIDATION_REASON_UNEXPECTED_CUE_ID
        else:
            reason_code = STATEFUL_VALIDATION_REASON_CUE_ORDER_MISMATCH
        raise StatefulPartsValidationError(
            "part identity or cue order does not match its deterministic plan",
            reason_code=reason_code,
        )
    return part


def _read_private_part(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        file_descriptor = os.open(path, flags)
    except OSError as error:
        raise StatefulPartsValidationError(
            "part cannot be opened safely"
        ) from error
    try:
        file_stat = os.fstat(file_descriptor)
        if not stat.S_ISREG(file_stat.st_mode):
            raise StatefulPartsValidationError(
                "part is not a regular file"
            )
        if stat.S_IMODE(file_stat.st_mode) != STATEFUL_PART_FILE_MODE:
            raise StatefulPartsValidationError(
                "part file mode is not private"
            )
        if file_stat.st_size <= 0 or file_stat.st_size > STATEFUL_PART_MAX_BYTES:
            raise StatefulPartsLimitError(
                "part file exceeds its bounded byte limit"
            )
        payload = os.read(file_descriptor, STATEFUL_PART_MAX_BYTES + 1)
        if not payload or len(payload) > STATEFUL_PART_MAX_BYTES:
            raise StatefulPartsLimitError(
                "part read exceeds its bounded byte limit"
            )
        return payload
    except StatefulPartsError:
        raise
    except OSError as error:
        raise StatefulPartsValidationError(
            "part read failed"
        ) from error
    finally:
        os.close(file_descriptor)


def _part_path(
    task_directory: str | Path,
    expected: ExpectedStatefulPart,
    *,
    pending: bool,
) -> Path:
    directory = _validated_task_directory(task_directory)
    filename = expected.pending_filename if pending else expected.canonical_filename
    parsed_index, parsed_pending = _parse_part_filename(filename)
    if parsed_index != expected.part_index or parsed_pending != pending:
        raise StatefulPartsFilenameError(
            "part filename is detached from its expected range"
        )
    path = directory / filename
    if path.parent != directory or path.name != filename:
        raise StatefulPartsFilenameError(
            "part path escapes its task directory"
        )
    return path


def _path_exists_without_following(path: Path) -> bool:
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError as error:
        raise StatefulPartsPromotionError(
            "part destination could not be inspected"
        ) from error
    return True


def validate_stateful_part_file(
    path: str | Path,
    plan: StatefulPartPlan,
    *,
    pending: bool,
) -> StatefulSemanticPart:
    """Validate one exact pending or canonical file against the plan."""

    validated_plan = _validate_plan(plan)
    try:
        candidate_path = Path(path)
    except (TypeError, ValueError) as error:
        raise StatefulPartsFilenameError(
            "part path is invalid"
        ) from error
    directory = _validated_task_directory(candidate_path.parent)
    filename = candidate_path.name
    part_index, parsed_pending = _parse_part_filename(filename)
    if parsed_pending != pending:
        raise StatefulPartsFilenameError(
            "part suffix does not match the requested validation boundary"
        )
    if part_index > validated_plan.part_count:
        raise StatefulPartsFilenameError(
            "part index is outside the deterministic plan"
        )
    expected = validated_plan.parts[part_index - 1]
    expected_path = _part_path(directory, expected, pending=pending)
    if candidate_path != expected_path:
        raise StatefulPartsFilenameError(
            "part path is not the exact expected path"
        )
    payload = _read_private_part(candidate_path)
    return _part_from_payload(payload, expected, validated_plan)


def validate_pending_part(
    path: str | Path,
    plan: StatefulPartPlan,
) -> StatefulSemanticPart:
    return validate_stateful_part_file(path, plan, pending=True)


def validate_canonical_part(
    path: str | Path,
    plan: StatefulPartPlan,
) -> StatefulSemanticPart:
    return validate_stateful_part_file(path, plan, pending=False)


def parse_stateful_part(
    payload: bytes,
    expected: ExpectedStatefulPart,
    plan: StatefulPartPlan,
) -> StatefulSemanticPart:
    """Validate one already-read part payload against one expected range."""

    validated_plan = _validate_plan(plan)
    if type(expected) is not ExpectedStatefulPart:
        raise StatefulPartsValidationError(
            "expected part metadata has the wrong exact type"
        )
    if expected.part_index > validated_plan.part_count:
        raise StatefulPartsValidationError(
            "expected part metadata is outside the deterministic plan"
        )
    if validated_plan.parts[expected.part_index - 1] != expected:
        raise StatefulPartsValidationError(
            "expected part metadata is detached from the deterministic plan"
        )
    return _part_from_payload(payload, expected, validated_plan)


def promote_pending_part(
    task_directory: str | Path,
    plan: StatefulPartPlan,
    part_index: int,
) -> StatefulSemanticPart:
    """Validate and atomically install one pending part without overwrite."""

    validated_plan = _validate_plan(plan)
    part_index = _require_part_index(part_index)
    if part_index > validated_plan.part_count:
        raise StatefulPartsPromotionError(
            "part index is outside the deterministic plan"
        )
    expected = validated_plan.parts[part_index - 1]
    pending_path = _part_path(
        task_directory,
        expected,
        pending=True,
    )
    canonical_path = _part_path(
        task_directory,
        expected,
        pending=False,
    )
    validated_part = validate_pending_part(pending_path, validated_plan)
    if _path_exists_without_following(canonical_path):
        raise StatefulPartsPromotionError(
            "canonical part already exists and cannot be overwritten"
        )
    try:
        # A same-directory hard-link install is atomic and fails with
        # FileExistsError if another controller installs canonical evidence
        # after the precheck.  Removing the original name only happens after
        # the canonical name has been durably installed; a crash in between
        # leaves a visible conflict that the scanner rejects closed.
        os.link(
            pending_path,
            canonical_path,
            follow_symlinks=False,
        )
        _fsync_directory(canonical_path.parent)
        os.unlink(pending_path)
        _fsync_directory(canonical_path.parent)
    except FileExistsError as error:
        raise StatefulPartsPromotionError(
            "canonical part already exists and cannot be overwritten"
        ) from error
    except OSError as error:
        raise StatefulPartsPromotionError(
            "validated pending part could not be promoted"
        ) from error
    try:
        canonical_stat = os.stat(canonical_path, follow_symlinks=False)
    except OSError as error:
        raise StatefulPartsPromotionError(
            "promoted canonical part could not be verified"
        ) from error
    if (
        not stat.S_ISREG(canonical_stat.st_mode)
        or stat.S_IMODE(canonical_stat.st_mode) != STATEFUL_PART_FILE_MODE
    ):
        raise StatefulPartsPromotionError(
            "promoted canonical part is not a private regular file"
        )
    return validated_part


def _fsync_directory(directory: Path) -> None:
    try:
        directory_fd = os.open(
            directory,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
    except OSError as error:
        raise StatefulPartsPromotionError(
            "part directory could not be opened for durability"
        ) from error
    try:
        os.fsync(directory_fd)
    except OSError as error:
        raise StatefulPartsPromotionError(
            "part directory could not be synchronized"
        ) from error
    finally:
        os.close(directory_fd)


def _part_index_from_name(name: str) -> tuple[int, bool]:
    return _parse_part_filename(name)


def scan_stateful_canonical_parts(
    task_directory: str | Path,
    plan: StatefulPartPlan,
) -> StatefulPartScan:
    """Validate all part-like files and report the first missing canonical."""

    validated_plan = _validate_plan(plan)
    directory = _validated_task_directory(task_directory)
    canonical_by_index: dict[int, StatefulSemanticPart] = {}
    pending_by_index: dict[int, StatefulSemanticPart] = {}
    try:
        entries = tuple(directory.iterdir())
    except OSError as error:
        raise StatefulPartsValidationError(
            "part directory cannot be scanned"
        ) from error
    for entry in entries:
        if not entry.name.startswith(STATEFUL_PART_FILENAME_PREFIX):
            continue
        part_index, pending = _part_index_from_name(entry.name)
        if part_index > validated_plan.part_count:
            raise StatefulPartsFilenameError(
                "part filename index is outside the deterministic plan"
            )
        expected = validated_plan.parts[part_index - 1]
        if pending:
            if part_index in pending_by_index:
                raise StatefulPartsFilenameError(
                    "duplicate pending part index"
                )
            pending_part = validate_pending_part(entry, validated_plan)
            pending_by_index[part_index] = pending_part
        else:
            if part_index in canonical_by_index:
                raise StatefulPartsFilenameError(
                    "duplicate canonical part index"
                )
            canonical_part = validate_canonical_part(entry, validated_plan)
            canonical_by_index[part_index] = canonical_part
    for part_index in canonical_by_index:
        if part_index in pending_by_index:
            raise StatefulPartsFilenameError(
                "pending and canonical files conflict for one part index"
            )
    canonical_parts = tuple(
        canonical_by_index[index]
        for index in sorted(canonical_by_index)
    )
    pending_parts = tuple(
        pending_by_index[index]
        for index in sorted(pending_by_index)
    )
    first_missing_part = next(
        (
            expected
            for expected in validated_plan.parts
            if expected.part_index not in canonical_by_index
        ),
        None,
    )
    return StatefulPartScan(
        expected_parts=validated_plan.parts,
        canonical_parts=canonical_parts,
        pending_parts=pending_parts,
        first_missing_part=first_missing_part,
    )


def scan_canonical_parts(
    task_directory: str | Path,
    plan: StatefulPartPlan,
) -> StatefulPartScan:
    """Public short alias for canonical resume scanning."""

    return scan_stateful_canonical_parts(task_directory, plan)


def assemble_stateful_result(
    task_directory: str | Path,
    package: StatefulSubtitlePackage,
    plan: StatefulPartPlan,
) -> StatefulSubtitleResult:
    """Assemble all canonical parts into the existing final result artifact."""

    validated_plan = _validate_plan_against_package(plan, package)
    scan = scan_stateful_canonical_parts(task_directory, validated_plan)
    if not scan.complete:
        raise StatefulPartsAssemblyError(
            "final assembly requires every canonical part"
        )
    output_cues = tuple(
        cue
        for part in scan.canonical_parts
        for cue in part.cues
    )
    try:
        result = StatefulSubtitleResult(
            schema_version=1,
            dvd_id=package.dvd_id,
            generation_key=package.generation_key,
            claim_token=package.claim_token,
            session_id=validated_plan.session_id,
            cues=output_cues,
        )
        validated_result = validate_stateful_result(result, package)
        result_bytes = serialize_stateful_result(validated_result)
    except (StatefulTranslatorError, TypeError, ValueError, OverflowError) as error:
        raise StatefulPartsAssemblyError(
            "final stateful result failed existing validation"
        ) from error
    paths = stateful_staging_paths(task_directory)
    if _path_exists_without_following(paths.result_path):
        raise StatefulPartsAssemblyError(
            "final stateful result already exists and cannot be overwritten"
        )
    try:
        _atomic_private_write(paths.result_path, result_bytes)
    except (StatefulTranslatorError, OSError, TypeError, ValueError) as error:
        raise StatefulPartsAssemblyError(
            "final stateful result could not be written atomically"
        ) from error
    return validated_result


__all__ = [
    "ExpectedStatefulPart",
    "MAX_STATEFUL_PART_BYTES",
    "STATEFUL_VALIDATION_REASON_CUE_COUNT_MISMATCH",
    "STATEFUL_VALIDATION_REASON_CUE_ORDER_MISMATCH",
    "STATEFUL_VALIDATION_REASON_DUPLICATE_CUE_ID",
    "STATEFUL_VALIDATION_REASON_FIRST_CUE_ID_MISMATCH",
    "STATEFUL_VALIDATION_REASON_INPUT_SHA256_MISMATCH",
    "STATEFUL_VALIDATION_REASON_INVALID_FIELD",
    "STATEFUL_VALIDATION_REASON_INVALID_KO",
    "STATEFUL_VALIDATION_REASON_INVALID_REPAIRED_JA",
    "STATEFUL_VALIDATION_REASON_JSON_PARSE_FAILURE",
    "STATEFUL_VALIDATION_REASON_LAST_CUE_ID_MISMATCH",
    "STATEFUL_VALIDATION_REASON_MISSING_CUE_ID",
    "STATEFUL_VALIDATION_REASON_OTHER_VALIDATOR_PREDICATE",
    "STATEFUL_VALIDATION_REASON_PART_INDEX_MISMATCH",
    "STATEFUL_VALIDATION_REASON_SCHEMA_FAILURE",
    "STATEFUL_VALIDATION_REASON_SESSION_ID_MISMATCH",
    "STATEFUL_VALIDATION_REASON_UNEXPECTED_CUE_ID",
    "STATEFUL_PART_BATCH_SIZE",
    "STATEFUL_PART_CANONICAL_SUFFIX",
    "STATEFUL_PART_FILE_MODE",
    "STATEFUL_PART_FILENAME_PREFIX",
    "STATEFUL_PART_MAX_BYTES",
    "STATEFUL_PART_PENDING_SUFFIX",
    "STATEFUL_PART_POLICY_ID",
    "STATEFUL_PART_SCHEMA_VERSION",
    "StatefulPartAssemblyError",
    "StatefulPartFilenameError",
    "StatefulPartPlan",
    "StatefulPartScan",
    "StatefulPartsError",
    "StatefulPartsLimitError",
    "StatefulPartsPromotionError",
    "StatefulPartsValidationError",
    "StatefulSemanticPart",
    "assemble_stateful_result",
    "build_stateful_part_plan",
    "expected_part_filename",
    "has_runaway_repetition",
    "parse_stateful_part",
    "plan_stateful_parts",
    "promote_pending_part",
    "scan_canonical_parts",
    "scan_stateful_canonical_parts",
    "serialize_stateful_part",
    "stateful_part_filename",
    "validate_canonical_part",
    "validate_pending_part",
    "validate_stateful_part_file",
]
