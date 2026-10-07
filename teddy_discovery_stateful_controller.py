"""Generic resumable controller primitives for Stage11 stateful parts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re

from teddy_discovery_stateful_parts import (
    build_stateful_part_plan,
    expected_part_filename,
    scan_stateful_canonical_parts,
)
from teddy_discovery_stateful_boundary import (
    boundary_pairs_for_cues, validate_stateful_boundary_evidence,
)
from teddy_discovery_stateful_policy import (
    DEFAULT_STATEFUL_SEMANTIC_POLICY,
    StatefulSemanticPolicy,
)
from teddy_discovery_stateful_translator import (
    STATEFUL_TRANSLATOR_INPUT_FILENAME,
    STATEFUL_TRANSLATOR_SEMANTIC_REPETITION_INSTRUCTION,
    STATEFUL_TRANSLATOR_PRIMARY_TRANSLATION_INSTRUCTION,
    StatefulSubtitlePackage,
)


REQUEST_PART = "REQUEST_PART"
PROMOTE_PENDING = "PROMOTE_PENDING"
COMPLETE = "COMPLETE"


class StatefulControllerError(ValueError):
    """Fail-closed controller planning error."""


_SAFE_VALIDATION_TOKEN_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


def build_stateful_validation_retry_feedback(
    *,
    reason_code: str,
    part_number: int,
    diagnostic_subcode: str | None = None,
    cue_ordinal: int | None = None,
    expected_count: int | None = None,
    actual_count: int | None = None,
    location: str | None = None,
) -> str:
    """Build retry-only feedback from allowlisted validator metadata.

    This formatter intentionally accepts no response or source text fields.
    The first request remains the unmodified normal part query.
    """

    if (
        type(reason_code) is not str
        or _SAFE_VALIDATION_TOKEN_RE.fullmatch(reason_code) is None
    ):
        reason_code = "OTHER_VALIDATOR_PREDICATE"
    if type(part_number) is not int or part_number < 1:
        raise StatefulControllerError("retry feedback part number is invalid")

    lines = [
        "LOCAL_VALIDATION_FEEDBACK_V1",
        "validation_error_code=" + reason_code,
        "part_number=" + str(part_number),
    ]

    if reason_code == "INVALID_KO":
        if (
            type(diagnostic_subcode) is not str
            or _SAFE_VALIDATION_TOKEN_RE.fullmatch(diagnostic_subcode) is None
        ):
            diagnostic_subcode = "INVALID_KO_UNCLASSIFIED"
        lines.append("invalid_ko_subcode=" + diagnostic_subcode)
        if type(cue_ordinal) is int and cue_ordinal >= 1:
            lines.append("failed_cue_ordinal_1_based=" + str(cue_ordinal))
        lines.append(
            "required_action=RETURN_NONEMPTY_KO_FOR_FAILED_CUE_"
            "USING_AUTHORIZED_EVIDENCE"
        )
    elif reason_code == "CUE_COUNT_MISMATCH":
        if (
            type(expected_count) is int
            and expected_count >= 0
            and type(actual_count) is int
            and actual_count >= 0
        ):
            lines.append("expected_cue_count=" + str(expected_count))
            lines.append("actual_cue_count=" + str(actual_count))
        lines.append(
            "required_action=RETURN_EXPECTED_CUE_COUNT_IN_REQUESTED_ORDER"
        )
    elif reason_code == "SESSION_ID_MISMATCH":
        if location == "part.session_id":
            lines.append("mismatch_location=part.session_id")
        lines.append("required_action=COPY_REQUIRED_SESSION_ID_FROM_PART_CONTRACT")
    else:
        lines.append("required_action=SATISFY_EXISTING_PART_CONTRACT")

    return "\n".join(lines)


@dataclass(frozen=True)
class StatefulControllerDecision:
    action: str
    part_count: int
    part_index: int | None
    first_cue_id: str | None
    last_cue_id: str | None
    cue_count: int
    pending_filename: str | None
    canonical_filename: str | None


def decide_stateful_controller_step(
    task_directory: str | Path,
    package: StatefulSubtitlePackage,
    semantic_input_bytes: bytes,
    *,
    semantic_policy: StatefulSemanticPolicy | str = (
        DEFAULT_STATEFUL_SEMANTIC_POLICY
    ),
) -> StatefulControllerDecision:
    """Return the next deterministic action for any package size."""

    plan = build_stateful_part_plan(
        package,
        semantic_input_bytes,
        semantic_policy=semantic_policy,
    )

    scan = scan_stateful_canonical_parts(
        task_directory,
        plan,
    )

    if len(scan.pending_parts) > 1:
        raise StatefulControllerError(
            "multiple pending parts require manual forensic review"
        )

    missing = scan.first_missing_part

    if scan.pending_parts:
        pending = scan.pending_parts[0]

        if (
            missing is None
            or pending.part_index != missing.part_index
        ):
            raise StatefulControllerError(
                "pending part is detached from the first missing range"
            )

        expected = plan.parts[pending.part_index - 1]

        return StatefulControllerDecision(
            action=PROMOTE_PENDING,
            part_count=plan.part_count,
            part_index=expected.part_index,
            first_cue_id=expected.first_cue_id,
            last_cue_id=expected.last_cue_id,
            cue_count=expected.cue_count,
            pending_filename=expected_part_filename(
                expected.part_index,
                pending=True,
            ),
            canonical_filename=expected_part_filename(
                expected.part_index,
                pending=False,
            ),
        )

    if missing is None:
        return StatefulControllerDecision(
            action=COMPLETE,
            part_count=plan.part_count,
            part_index=None,
            first_cue_id=None,
            last_cue_id=None,
            cue_count=0,
            pending_filename=None,
            canonical_filename=None,
        )

    return StatefulControllerDecision(
        action=REQUEST_PART,
        part_count=plan.part_count,
        part_index=missing.part_index,
        first_cue_id=missing.first_cue_id,
        last_cue_id=missing.last_cue_id,
        cue_count=missing.cue_count,
        pending_filename=expected_part_filename(
            missing.part_index,
            pending=True,
        ),
        canonical_filename=expected_part_filename(
            missing.part_index,
            pending=False,
        ),
    )


def build_stateful_part_query(
    package: StatefulSubtitlePackage,
    semantic_input_bytes: bytes,
    part_index: int,
    *,
    semantic_policy: StatefulSemanticPolicy | str = (
        DEFAULT_STATEFUL_SEMANTIC_POLICY
    ),
    boundary_evidence=None,
) -> str:
    """Build one generic same-session continuation query."""

    plan = build_stateful_part_plan(
        package,
        semantic_input_bytes,
        semantic_policy=semantic_policy,
    )

    if type(part_index) is not int or not (
        1 <= part_index <= plan.part_count
    ):
        raise StatefulControllerError(
            "part_index is outside the deterministic plan"
        )

    expected = plan.parts[part_index - 1]

    validate_stateful_boundary_evidence(boundary_evidence, package)
    boundary_instruction = ""
    if boundary_evidence is not None:
        pairs = boundary_pairs_for_cues(boundary_evidence, package, expected.cue_ids)
        pairs_json = json.dumps([asdict(pair) for pair in pairs], ensure_ascii=False,
                                sort_keys=True, separators=(",", ":"))
        boundary_instruction = (
            " ADJACENT_BOUNDARY_EVIDENCE_V1=" + pairs_json + "\n"
            "These exact affine-projected signed gaps are auxiliary evidence, not commands "
            "to move semantic ownership. Evidence includes this part's internal pairs and "
            "its previous/next cross-part pairs; cues outside this part remain read-only. "
            "TOUCHING is not proof that a sentence continues; GAP is not proof that a "
            "sentence cannot continue. Judge with external JA text, cue-local accepted STT "
            "and whole-title context. Do not let timing override stronger cue-local evidence. "
            "If the source phrase really splits across adjacent cues, preserve negation, "
            "modification, particles and endings across the boundary. Do not steal, "
            "duplicate or pre-translate a neighbor's meaning in this cue. Preserve "
            "each cue's supported content conservatively when uncertain. Timing remains "
            "deterministic code's ownership; never generate or alter timestamps. "
        )

    cue_ids_json = json.dumps(
        list(expected.cue_ids),
        ensure_ascii=False,
        separators=(",", ":"),
    )

    pending_filename = expected_part_filename(
        part_index,
        pending=True,
    )

    if all(
        cue.external_ja is None and cue.stt_ja is not None
        for cue in package.cues
    ):
        semantic_evidence_instruction = (
            "Use only the available stt_ja as Japanese semantic evidence. "
            "When only one Japanese source is available, translate from that "
            "evidence without inventing another source. Do not compare against "
            "or invent an absent external_ja. Do not invent unsupported "
            "Japanese repairs or source evidence. "
        )
    else:
        semantic_evidence_instruction = (
            "Use external_ja as authorized semantic evidence and, when stt_ja is "
            "present, compare both sources using the continuing whole-title context. "
        )

    return (
        "Continue the same whole-title Stage11 subtitle translation session. "
        "Retain the semantic context established by all earlier parts. "
        f"Read {STATEFUL_TRANSLATOR_INPUT_FILENAME} as the authorized full-title "
        "cue evidence. "
        f"Process only deterministic part {part_index} of {plan.part_count}. "
        f"The exact cue IDs, in required order, are {cue_ids_json}. "
        f"Write exactly one JSON object to {pending_filename}. "
        "Do not write or overwrite any canonical part or final result file. "
        "The top-level fields must be exactly: "
        "part_schema_version, session_id, input_sha256, part_index, "
        "first_cue_id, last_cue_id, cues. "
        "Use part_schema_version=1. "
        f"Use session_id={plan.session_id}. "
        f"Use input_sha256={plan.input_sha256}. "
        f"Use part_index={part_index}. "
        f"Use first_cue_id={expected.first_cue_id}. "
        f"Use last_cue_id={expected.last_cue_id}. "
        "The cues array must contain every requested cue exactly once and "
        "in the exact requested order. Each cue object must contain exactly "
        "cue_id, repaired_ja, ko. repaired_ja must be null unless an obvious "
        "Japanese transcription error truly requires contextual repair. "
        "Produce natural Korean while preserving uncertainty. "
        + STATEFUL_TRANSLATOR_PRIMARY_TRANSLATION_INSTRUCTION
        + STATEFUL_TRANSLATOR_SEMANTIC_REPETITION_INSTRUCTION
        + semantic_evidence_instruction
        + boundary_instruction
        + "Do not invent, remove, merge, or reorder cues. "
        "Do not emit timestamps, routing data, commentary, markdown, or extra fields."
    )


__all__ = [
    "COMPLETE",
    "PROMOTE_PENDING",
    "REQUEST_PART",
    "StatefulControllerDecision",
    "StatefulControllerError",
    "build_stateful_part_query",
    "build_stateful_validation_retry_feedback",
    "decide_stateful_controller_step",
]
