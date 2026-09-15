"""Explicit production policies for the Stage11 semantic-part path.

The fixed-64 policy is the production default.  Explicit legacy 16-cue use
keeps its historical package, session, and resume identity, while fixed-64
and fixed-128 state are bound into the package generation identity before the
existing session/staging machinery is used.  The semantic package/result/part
JSON envelopes remain unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Final


STATEFUL_SEMANTIC_POLICY_ID_16: Final[str] = "stage11-stateful-cue16-v1"
STATEFUL_SEMANTIC_POLICY_ID_64: Final[str] = "stage11-stateful-cue64-v1"
STATEFUL_SEMANTIC_POLICY_ID_128: Final[str] = "stage11-stateful-cue128-v1"
STATEFUL_SEMANTIC_POLICY_TIMEOUT_SECONDS: Final[int] = 600
STATEFUL_SEMANTIC_POLICY_GENERATION_KEY_MARKER: Final[str] = (
    "::stage11-policy="
)
STATEFUL_SEMANTIC_POLICY_MAX_IDENTIFIER_CHARS: Final[int] = 256

_POLICY_ID_RE = re.compile(r"^stage11-stateful-cue(?:16|64|128)-v1$")
_POLICY_PART_SIZES: Final[dict[str, int]] = {
    STATEFUL_SEMANTIC_POLICY_ID_16: 16,
    STATEFUL_SEMANTIC_POLICY_ID_64: 64,
    STATEFUL_SEMANTIC_POLICY_ID_128: 128,
}


class StatefulSemanticPolicyError(ValueError):
    """Raised when a semantic policy is unknown or internally inconsistent."""


def _require_generation_key(value: object) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise StatefulSemanticPolicyError(
            "generation_key must be a nonempty exact string"
        )
    if len(value) > STATEFUL_SEMANTIC_POLICY_MAX_IDENTIFIER_CHARS:
        raise StatefulSemanticPolicyError(
            "generation_key exceeds its bounded identifier length"
        )
    if any(
        ord(character) < 32
        or ord(character) == 127
        or character.isspace()
        for character in value
    ):
        raise StatefulSemanticPolicyError(
            "generation_key contains unsafe whitespace or control data"
        )
    return value


@dataclass(frozen=True)
class StatefulSemanticPolicy:
    """One supported production semantic partition policy."""

    policy_id: str
    max_cues_per_part: int
    turn_timeout_seconds: int = STATEFUL_SEMANTIC_POLICY_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        if type(self.policy_id) is not str or _POLICY_ID_RE.fullmatch(
            self.policy_id
        ) is None:
            raise StatefulSemanticPolicyError("unknown semantic policy ID")
        expected_size = _POLICY_PART_SIZES.get(self.policy_id)
        if self.max_cues_per_part != expected_size:
            raise StatefulSemanticPolicyError(
                "semantic policy batch size does not match its policy ID"
            )
        if type(self.turn_timeout_seconds) is not int or (
            self.turn_timeout_seconds != STATEFUL_SEMANTIC_POLICY_TIMEOUT_SECONDS
        ):
            raise StatefulSemanticPolicyError(
                "semantic policy timeout must remain 600 seconds"
            )


STATEFUL_SEMANTIC_POLICY_16: Final[StatefulSemanticPolicy] = (
    StatefulSemanticPolicy(
        policy_id=STATEFUL_SEMANTIC_POLICY_ID_16,
        max_cues_per_part=16,
    )
)
STATEFUL_SEMANTIC_POLICY_64: Final[StatefulSemanticPolicy] = (
    StatefulSemanticPolicy(
        policy_id=STATEFUL_SEMANTIC_POLICY_ID_64,
        max_cues_per_part=64,
    )
)
STATEFUL_SEMANTIC_POLICY_128: Final[StatefulSemanticPolicy] = (
    StatefulSemanticPolicy(
        policy_id=STATEFUL_SEMANTIC_POLICY_ID_128,
        max_cues_per_part=128,
    )
)
DEFAULT_STATEFUL_SEMANTIC_POLICY: Final[StatefulSemanticPolicy] = (
    STATEFUL_SEMANTIC_POLICY_64
)
STATEFUL_SEMANTIC_POLICIES: Final[tuple[StatefulSemanticPolicy, ...]] = (
    STATEFUL_SEMANTIC_POLICY_16,
    STATEFUL_SEMANTIC_POLICY_64,
    STATEFUL_SEMANTIC_POLICY_128,
)


def resolve_stateful_semantic_policy(
    value: StatefulSemanticPolicy | str,
) -> StatefulSemanticPolicy:
    """Resolve only an exact supported policy object or policy ID."""

    if type(value) is StatefulSemanticPolicy:
        value.__post_init__()
        return value
    if type(value) is str:
        for policy in STATEFUL_SEMANTIC_POLICIES:
            if value == policy.policy_id:
                return policy
    raise StatefulSemanticPolicyError("unsupported semantic policy")


def stateful_policy_id_from_generation_key(
    generation_key: str,
) -> str | None:
    """Return the reserved policy suffix, rejecting ambiguous identities."""

    generation_key = _require_generation_key(generation_key)
    marker_count = generation_key.count(
        STATEFUL_SEMANTIC_POLICY_GENERATION_KEY_MARKER
    )
    if marker_count == 0:
        return None
    if marker_count != 1:
        raise StatefulSemanticPolicyError(
            "generation_key contains multiple policy identities"
        )
    policy_id = generation_key.rsplit(
        STATEFUL_SEMANTIC_POLICY_GENERATION_KEY_MARKER,
        1,
    )[1]
    resolve_stateful_semantic_policy(policy_id)
    return policy_id


def bind_stateful_policy_generation_key(
    generation_key: str,
    semantic_policy: StatefulSemanticPolicy | str,
) -> str:
    """Bind a policy to a generation identity without changing cue evidence."""

    generation_key = _require_generation_key(generation_key)
    policy = resolve_stateful_semantic_policy(semantic_policy)
    bound_policy_id = stateful_policy_id_from_generation_key(generation_key)
    if bound_policy_id is not None:
        if bound_policy_id != policy.policy_id:
            raise StatefulSemanticPolicyError(
                "generation_key is bound to a different semantic policy"
            )
        return generation_key
    # Historical 16-cue packages predate policy binding.  Keep that explicit
    # compatibility path only for legacy-16; every new/default policy must
    # carry its policy identity so incompatible partial state cannot collide.
    if policy == STATEFUL_SEMANTIC_POLICY_16:
        return generation_key
    bound = (
        generation_key
        + STATEFUL_SEMANTIC_POLICY_GENERATION_KEY_MARKER
        + policy.policy_id
    )
    return _require_generation_key(bound)


__all__ = [
    "DEFAULT_STATEFUL_SEMANTIC_POLICY",
    "STATEFUL_SEMANTIC_POLICIES",
    "STATEFUL_SEMANTIC_POLICY_16",
    "STATEFUL_SEMANTIC_POLICY_64",
    "STATEFUL_SEMANTIC_POLICY_128",
    "STATEFUL_SEMANTIC_POLICY_GENERATION_KEY_MARKER",
    "STATEFUL_SEMANTIC_POLICY_ID_16",
    "STATEFUL_SEMANTIC_POLICY_ID_64",
    "STATEFUL_SEMANTIC_POLICY_ID_128",
    "STATEFUL_SEMANTIC_POLICY_TIMEOUT_SECONDS",
    "StatefulSemanticPolicy",
    "StatefulSemanticPolicyError",
    "bind_stateful_policy_generation_key",
    "resolve_stateful_semantic_policy",
    "stateful_policy_id_from_generation_key",
]
