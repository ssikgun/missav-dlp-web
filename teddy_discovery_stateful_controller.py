"""Generic resumable controller primitives for Stage11 stateful parts."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from teddy_discovery_stateful_parts import (
    build_stateful_part_plan,
    expected_part_filename,
    scan_stateful_canonical_parts,
)
from teddy_discovery_stateful_policy import (
    DEFAULT_STATEFUL_SEMANTIC_POLICY,
    StatefulSemanticPolicy,
)
from teddy_discovery_stateful_translator import (
    STATEFUL_TRANSLATOR_INPUT_FILENAME,
    StatefulSubtitlePackage,
)


REQUEST_PART = "REQUEST_PART"
PROMOTE_PENDING = "PROMOTE_PENDING"
COMPLETE = "COMPLETE"


class StatefulControllerError(ValueError):
    """Fail-closed controller planning error."""


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
        + semantic_evidence_instruction
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
    "decide_stateful_controller_step",
]
