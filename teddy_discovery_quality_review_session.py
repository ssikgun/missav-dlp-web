"""Shared quality-review session identity wire helpers.

Review evidence is produced by a first-pass translation session, while the
review turn may execute in another native Hermes session.  This module keeps
the wire compatibility rule in one place: legacy ``session_id`` is accepted
as source-translation provenance, and new requests use the explicit field.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import uuid


LEGACY_SESSION_ID_FIELD = "session_id"
SOURCE_TRANSLATION_SESSION_ID_FIELD = "source_translation_session_id"
REVIEW_EXECUTION_SESSION_ID_FIELD = "review_execution_session_id"
QUALITY_REVIEW_SESSION_SOURCE = "stage11-quality-review"


class QualityReviewSessionError(RuntimeError):
    """Native review-session preparation failed closed."""


@dataclass(frozen=True)
class FreshReviewExecutionSession:
    """The exact identity and native metadata verified after creation."""

    review_execution_session_id: str
    source: str
    profile_name: str


def validate_canonical_review_execution_session_id(value: object) -> str:
    """Accept only the standard lowercase, hyphenated UUID spelling."""

    if type(value) is not str:
        raise QualityReviewSessionError(
            "review execution session ID must be an exact string"
        )
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, TypeError, ValueError) as error:
        raise QualityReviewSessionError(
            "review execution session ID must be a canonical UUID"
        ) from error
    if str(parsed) != value:
        raise QualityReviewSessionError(
            "review execution session ID must be a canonical UUID"
        )
    return value


def new_review_execution_session_id() -> str:
    """Generate a new canonical review execution identity without persistence."""

    return str(uuid.uuid4())


def _row_value(row: object, key: str) -> object:
    if not isinstance(row, Mapping):
        raise QualityReviewSessionError(
            "native session read-back must be a mapping"
        )
    return row.get(key)


def ensure_fresh_review_execution_session(
    session_db: object,
    review_execution_session_id: object,
    *,
    expected_profile_name: str,
    source: str = QUALITY_REVIEW_SESSION_SOURCE,
) -> FreshReviewExecutionSession:
    """Create exactly one detached empty session through native ``SessionDB``.

    ``session_db`` must be the profile-local native SessionDB object.  This
    helper intentionally has no database-path or SQL fallback: callers must
    provide the native context appropriate to the execution host.
    """

    session_id = validate_canonical_review_execution_session_id(
        review_execution_session_id
    )
    if type(expected_profile_name) is not str or not expected_profile_name:
        raise QualityReviewSessionError("expected profile name is required")
    if any(character in expected_profile_name for character in "\r\n\x00"):
        raise QualityReviewSessionError("expected profile name is malformed")
    if type(source) is not str or not source:
        raise QualityReviewSessionError("native session source is required")

    get_session = getattr(session_db, "get_session", None)
    create_session = getattr(session_db, "create_session", None)
    get_messages = getattr(session_db, "get_messages", None)
    if not callable(get_session) or not callable(create_session):
        raise QualityReviewSessionError(
            "native SessionDB must provide get_session and create_session"
        )
    if not callable(get_messages):
        raise QualityReviewSessionError(
            "native SessionDB must provide get_messages for empty-history verification"
        )

    try:
        existing = get_session(session_id)
    except Exception as error:
        raise QualityReviewSessionError(
            "native review-session existence check failed"
        ) from error
    if existing is not None:
        raise QualityReviewSessionError(
            "fresh review execution session already exists"
        )

    try:
        returned_id = create_session(
            session_id=session_id,
            source=source,
            profile_name=expected_profile_name,
        )
    except Exception as error:
        raise QualityReviewSessionError(
            "native fresh review-session creation failed"
        ) from error
    if type(returned_id) is not str or returned_id != session_id:
        raise QualityReviewSessionError(
            "native fresh review-session creation returned a different ID"
        )

    try:
        persisted = get_session(session_id)
    except Exception as error:
        raise QualityReviewSessionError(
            "native fresh review-session read-back failed"
        ) from error
    if persisted is None or _row_value(persisted, "id") != session_id:
        raise QualityReviewSessionError(
            "fresh review-session ID read-back did not match"
        )
    if _row_value(persisted, "source") != source:
        raise QualityReviewSessionError(
            "fresh review-session source read-back did not match"
        )
    if _row_value(persisted, "profile_name") != expected_profile_name:
        raise QualityReviewSessionError(
            "fresh review-session profile ownership did not match"
        )
    if _row_value(persisted, "parent_session_id") is not None:
        raise QualityReviewSessionError(
            "fresh review-session unexpectedly has a parent"
        )

    try:
        messages = get_messages(session_id, include_inactive=True)
    except Exception as error:
        raise QualityReviewSessionError(
            "native fresh review-session history read failed"
        ) from error
    if type(messages) is not list:
        raise QualityReviewSessionError(
            "native fresh review-session history is not a list"
        )
    if messages:
        raise QualityReviewSessionError(
            "fresh review execution session is not empty"
        )

    return FreshReviewExecutionSession(
        review_execution_session_id=session_id,
        source=source,
        profile_name=expected_profile_name,
    )


def resolve_source_translation_session_id(
    data: dict,
) -> tuple[str, bool]:
    """Return ``(source_session_id, used_legacy_wire_field)``.

    A payload must choose exactly one spelling.  Accepting both would make a
    detached provenance value ambiguous, so it fails closed even when the
    values happen to be equal.
    """

    has_legacy = LEGACY_SESSION_ID_FIELD in data
    has_source = SOURCE_TRANSLATION_SESSION_ID_FIELD in data
    if has_legacy == has_source:
        raise ValueError("review request must contain exactly one session identity field")
    field = LEGACY_SESSION_ID_FIELD if has_legacy else SOURCE_TRANSLATION_SESSION_ID_FIELD
    return data[field], has_legacy


def encode_source_translation_session_id(
    data: dict,
    source_translation_session_id: str,
    *,
    legacy_wire_field: bool,
) -> None:
    """Write the canonical or legacy request identity field into ``data``."""

    data.pop(LEGACY_SESSION_ID_FIELD, None)
    data.pop(SOURCE_TRANSLATION_SESSION_ID_FIELD, None)
    data[
        LEGACY_SESSION_ID_FIELD
        if legacy_wire_field
        else SOURCE_TRANSLATION_SESSION_ID_FIELD
    ] = source_translation_session_id
