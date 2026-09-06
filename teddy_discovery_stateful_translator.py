"""Deterministic Stage11 stateful translator boundary.

This module owns only the bounded semantic package, deterministic session
identity, native SessionDB pre-mint adapter, command construction, and the
private staging/result boundary for the stateful subtitle translator.

It deliberately does not import the native Hermes runtime, transport, a
database driver, a process launcher, or any subtitle publication boundary.
The existing Hermes v2 one-shot and batching contracts remain separate; in
particular, their 512-cue limit is not inherited here.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat
import tempfile
import uuid
from typing import Final

from teddy_discovery_hermes_v2 import (
    HermesV2CueInput,
    HermesV2CueOutput,
)


STATEFUL_TRANSLATOR_SCHEMA_VERSION: Final[int] = 1
STATEFUL_TRANSLATOR_MAX_CUES: Final[int] = 4_096
STATEFUL_TRANSLATOR_MAX_PACKAGE_BYTES: Final[int] = 16 * 1024 * 1024
STATEFUL_TRANSLATOR_MAX_RESULT_BYTES: Final[int] = 16 * 1024 * 1024
STATEFUL_TRANSLATOR_MAX_IDENTIFIER_CHARS: Final[int] = 256
STATEFUL_TRANSLATOR_MAX_CLAIM_TOKEN: Final[int] = (1 << 63) - 1

# These aliases make the stateful-only resource boundary explicit without
# changing or shadowing MAX_HERMES_V2_REQUEST_CUES.
MAX_STATEFUL_TRANSLATOR_CUES: Final[int] = STATEFUL_TRANSLATOR_MAX_CUES
MAX_STATEFUL_TRANSLATOR_PACKAGE_BYTES: Final[int] = (
    STATEFUL_TRANSLATOR_MAX_PACKAGE_BYTES
)
MAX_STATEFUL_TRANSLATOR_RESULT_BYTES: Final[int] = (
    STATEFUL_TRANSLATOR_MAX_RESULT_BYTES
)

STATEFUL_TRANSLATOR_SESSION_NAMESPACE: Final[uuid.UUID] = uuid.UUID(
    "4d6f4e10-9b8d-5af3-83c0-6c46f7a1e4ab"
)
STATEFUL_TRANSLATOR_SESSION_SOURCE: Final[str] = (
    "stage11-subtitle-translator"
)

STATEFUL_TRANSLATOR_EXECUTABLE: Final[str] = "/home/teddy/.local/bin/hermes"
STATEFUL_TRANSLATOR_PROFILE: Final[str] = "subtitle-translator"
STATEFUL_TRANSLATOR_SUBCOMMAND: Final[str] = "chat"
STATEFUL_TRANSLATOR_QUIET_FLAG: Final[str] = "-Q"
STATEFUL_TRANSLATOR_RESUME_FLAG: Final[str] = "--resume"
STATEFUL_TRANSLATOR_QUERY_FLAG: Final[str] = "-q"
STATEFUL_TRANSLATOR_PROVIDER: Final[str] = "openai-codex"
STATEFUL_TRANSLATOR_MODEL: Final[str] = "gpt-5.6-luna"
STATEFUL_TRANSLATOR_REASONING: Final[str] = "xhigh"

STATEFUL_TRANSLATOR_TASK_DIRECTORY_MODE: Final[int] = 0o700
STATEFUL_TRANSLATOR_PRIVATE_FILE_MODE: Final[int] = 0o600
STATEFUL_TRANSLATOR_INPUT_FILENAME: Final[str] = (
    "stage11-semantic-input.json"
)
STATEFUL_TRANSLATOR_RESULT_FILENAME: Final[str] = (
    "stage11-semantic-result.json"
)
STATEFUL_TRANSLATOR_QUERY: Final[str] = (
    "Read the complete authorized semantic cue evidence from "
    + STATEFUL_TRANSLATOR_INPUT_FILENAME
    + ". Produce one complete stateful semantic result for every cue in its "
    "original order. Preserve every cue_id, use no external Korean source, "
    "create no timestamps, and write only the complete JSON result envelope "
    "to "
    + STATEFUL_TRANSLATOR_RESULT_FILENAME
    + ". Partial output is not a valid result."
)


class StatefulTranslatorError(ValueError):
    """Base class for stateful translator contract failures."""


class StatefulTranslatorValidationError(StatefulTranslatorError):
    """Raised when stateful semantic data or metadata is unsafe."""


class StatefulTranslatorLimitError(StatefulTranslatorValidationError):
    """Raised when a stateful package/result exceeds a fixed bound."""


class StatefulTranslatorSessionError(StatefulTranslatorError):
    """Raised when native SessionDB pre-minting is not exact."""


class StatefulTranslatorStagingError(StatefulTranslatorError):
    """Raised when private staging cannot be consumed safely."""


def _require_exact_string(
    value: object,
    *,
    field_name: str,
    max_chars: int = STATEFUL_TRANSLATOR_MAX_IDENTIFIER_CHARS,
) -> str:
    if type(value) is not str:
        raise StatefulTranslatorValidationError(
            field_name + " must be an exact string"
        )
    if not value or value != value.strip():
        raise StatefulTranslatorValidationError(
            field_name + " must be bounded and nonempty"
        )
    if len(value) > max_chars:
        raise StatefulTranslatorLimitError(
            field_name + " exceeds its bounded identifier length"
        )
    if any(
        ord(character) < 32
        or ord(character) == 127
        or character.isspace()
        for character in value
    ):
        raise StatefulTranslatorValidationError(
            field_name + " contains unsafe whitespace or control data"
        )
    return value


def _validate_claim_token(value: object) -> int:
    if type(value) is not int:
        raise StatefulTranslatorValidationError(
            "claim_token must be an exact integer"
        )
    # The Stage11 job contract makes claim tokens monotonic and SQLite-safe.
    # Zero is representable before the first claim; a claimed package normally
    # carries the positive token created by that claim.
    if value < 0 or value > STATEFUL_TRANSLATOR_MAX_CLAIM_TOKEN:
        raise StatefulTranslatorValidationError(
            "claim_token is outside the Stage11 bounded range"
        )
    return value


def _validate_schema_version(value: object) -> int:
    if type(value) is not int or value != STATEFUL_TRANSLATOR_SCHEMA_VERSION:
        raise StatefulTranslatorValidationError(
            "unsupported stateful translator schema version"
        )
    return value


def _validated_input_cue(value: object) -> HermesV2CueInput:
    if type(value) is not HermesV2CueInput:
        raise StatefulTranslatorValidationError(
            "stateful package cue has the wrong exact type"
        )
    try:
        return HermesV2CueInput(
            cue_id=value.cue_id,
            external_ja=value.external_ja,
            stt_ja=value.stt_ja,
            en=value.en,
            before_context=value.before_context,
            after_context=value.after_context,
        )
    except (AttributeError, TypeError, ValueError, OverflowError) as error:
        raise StatefulTranslatorValidationError(
            "stateful package cue is invalid or detached"
        ) from error


def _validated_output_cue(value: object) -> HermesV2CueOutput:
    if type(value) is not HermesV2CueOutput:
        raise StatefulTranslatorValidationError(
            "stateful result cue has the wrong exact type"
        )
    try:
        return HermesV2CueOutput(
            cue_id=value.cue_id,
            repaired_ja=value.repaired_ja,
            ko=value.ko,
        )
    except (AttributeError, TypeError, ValueError, OverflowError) as error:
        raise StatefulTranslatorValidationError(
            "stateful result cue is invalid or detached"
        ) from error


@dataclass(frozen=True)
class StatefulSubtitlePackage:
    """One immutable title-level semantic package without timing authority."""

    schema_version: int
    dvd_id: str
    generation_key: str
    claim_token: int
    cues: tuple[HermesV2CueInput, ...]

    def __post_init__(self):
        _validate_schema_version(self.schema_version)
        _require_exact_string(self.dvd_id, field_name="dvd_id")
        _require_exact_string(
            self.generation_key,
            field_name="generation_key",
        )
        _validate_claim_token(self.claim_token)
        if type(self.cues) is not tuple:
            raise StatefulTranslatorValidationError(
                "stateful package cues must be an immutable tuple"
            )
        if not self.cues:
            raise StatefulTranslatorValidationError(
                "stateful package cues must not be empty"
            )
        if len(self.cues) > STATEFUL_TRANSLATOR_MAX_CUES:
            raise StatefulTranslatorLimitError(
                "stateful package exceeds its cue limit"
            )

        seen_cue_ids: set[str] = set()
        for cue in self.cues:
            validated = _validated_input_cue(cue)
            if validated.cue_id in seen_cue_ids:
                raise StatefulTranslatorValidationError(
                    "stateful package cue IDs must be unique"
                )
            seen_cue_ids.add(validated.cue_id)


@dataclass(frozen=True)
class StatefulSubtitleResult:
    """One complete semantic result; it contains no timestamp fields."""

    schema_version: int
    dvd_id: str
    generation_key: str
    claim_token: int
    session_id: str
    cues: tuple[HermesV2CueOutput, ...]

    def __post_init__(self):
        _validate_schema_version(self.schema_version)
        _require_exact_string(self.dvd_id, field_name="dvd_id")
        _require_exact_string(
            self.generation_key,
            field_name="generation_key",
        )
        _validate_claim_token(self.claim_token)
        _validate_session_id(self.session_id)
        if type(self.cues) is not tuple:
            raise StatefulTranslatorValidationError(
                "stateful result cues must be an immutable tuple"
            )
        if not self.cues:
            raise StatefulTranslatorValidationError(
                "stateful result cues must not be empty"
            )
        if len(self.cues) > STATEFUL_TRANSLATOR_MAX_CUES:
            raise StatefulTranslatorLimitError(
                "stateful result exceeds its cue limit"
            )

        seen_cue_ids: set[str] = set()
        for cue in self.cues:
            validated = _validated_output_cue(cue)
            if validated.cue_id in seen_cue_ids:
                raise StatefulTranslatorValidationError(
                    "stateful result cue IDs must be unique"
                )
            seen_cue_ids.add(validated.cue_id)


def _validated_package(value: object) -> StatefulSubtitlePackage:
    if type(value) is not StatefulSubtitlePackage:
        raise StatefulTranslatorValidationError(
            "stateful package has the wrong exact type"
        )
    try:
        return StatefulSubtitlePackage(
            schema_version=value.schema_version,
            dvd_id=value.dvd_id,
            generation_key=value.generation_key,
            claim_token=value.claim_token,
            cues=value.cues,
        )
    except (AttributeError, TypeError, ValueError, OverflowError) as error:
        raise StatefulTranslatorValidationError(
            "stateful package is invalid or detached"
        ) from error


def _validated_result(value: object) -> StatefulSubtitleResult:
    if type(value) is not StatefulSubtitleResult:
        raise StatefulTranslatorValidationError(
            "stateful result has the wrong exact type"
        )
    try:
        return StatefulSubtitleResult(
            schema_version=value.schema_version,
            dvd_id=value.dvd_id,
            generation_key=value.generation_key,
            claim_token=value.claim_token,
            session_id=value.session_id,
            cues=value.cues,
        )
    except (AttributeError, TypeError, ValueError, OverflowError) as error:
        raise StatefulTranslatorValidationError(
            "stateful result is invalid or detached"
        ) from error


def _input_cue_json(cue: HermesV2CueInput) -> dict[str, object]:
    return {
        "cue_id": cue.cue_id,
        "external_ja": cue.external_ja,
        "stt_ja": cue.stt_ja,
        "en": cue.en,
        "before_context": list(cue.before_context),
        "after_context": list(cue.after_context),
    }


def _output_cue_json(cue: HermesV2CueOutput) -> dict[str, object]:
    return {
        "cue_id": cue.cue_id,
        "repaired_ja": cue.repaired_ja,
        "ko": cue.ko,
    }


def _encode_json(data: dict[str, object], *, limit: int, label: str) -> bytes:
    try:
        encoded = json.dumps(
            data,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, UnicodeError, ValueError) as error:
        raise StatefulTranslatorValidationError(
            label + " could not be serialized deterministically"
        ) from error
    if len(encoded) > limit:
        raise StatefulTranslatorLimitError(
            label + " exceeds its bounded serialized byte limit"
        )
    return encoded


def serialize_stateful_package(package: StatefulSubtitlePackage) -> bytes:
    """Serialize one validated package as compact deterministic UTF-8 JSON."""

    validated = _validated_package(package)
    return _encode_json(
        {
            "schema_version": validated.schema_version,
            "dvd_id": validated.dvd_id,
            "generation_key": validated.generation_key,
            "claim_token": validated.claim_token,
            "cues": [_input_cue_json(cue) for cue in validated.cues],
        },
        limit=STATEFUL_TRANSLATOR_MAX_PACKAGE_BYTES,
        label="stateful package",
    )


def serialize_stateful_result(result: StatefulSubtitleResult) -> bytes:
    """Serialize one validated result as compact deterministic UTF-8 JSON."""

    validated = _validated_result(result)
    return _encode_json(
        {
            "schema_version": validated.schema_version,
            "dvd_id": validated.dvd_id,
            "generation_key": validated.generation_key,
            "claim_token": validated.claim_token,
            "session_id": validated.session_id,
            "cues": [_output_cue_json(cue) for cue in validated.cues],
        },
        limit=STATEFUL_TRANSLATOR_MAX_RESULT_BYTES,
        label="stateful result",
    )


def _reject_json_constant(value: str):
    raise StatefulTranslatorValidationError(
        "JSON constants are not accepted in stateful data"
    )


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise StatefulTranslatorValidationError(
                "duplicate JSON object keys are not accepted"
            )
        result[key] = value
    return result


def _load_json_object(
    payload: object,
    *,
    limit: int,
    label: str,
) -> dict[str, object]:
    if type(payload) is not bytes:
        raise StatefulTranslatorValidationError(
            label + " must be exact UTF-8 JSON bytes"
        )
    if not payload or len(payload) > limit:
        raise StatefulTranslatorLimitError(
            label + " exceeds its bounded serialized byte limit"
        )
    try:
        parsed = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant,
        )
    except StatefulTranslatorError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise StatefulTranslatorValidationError(
            label + " must be one JSON object without prose"
        ) from error
    if type(parsed) is not dict:
        raise StatefulTranslatorValidationError(
            label + " root must be a JSON object"
        )
    return parsed


def _parse_input_cue(value: object) -> HermesV2CueInput:
    if type(value) is not dict:
        raise StatefulTranslatorValidationError(
            "each stateful package cue must be a JSON object"
        )
    expected_fields = {
        "cue_id",
        "external_ja",
        "stt_ja",
        "en",
        "before_context",
        "after_context",
    }
    if set(value) != expected_fields:
        raise StatefulTranslatorValidationError(
            "stateful package cue fields are not exact"
        )
    if (
        type(value["before_context"]) is not list
        or type(value["after_context"]) is not list
    ):
        raise StatefulTranslatorValidationError(
            "stateful package context must be JSON arrays"
        )
    try:
        return HermesV2CueInput(
            cue_id=value["cue_id"],
            external_ja=value["external_ja"],
            stt_ja=value["stt_ja"],
            en=value["en"],
            before_context=tuple(value["before_context"]),
            after_context=tuple(value["after_context"]),
        )
    except (TypeError, ValueError, OverflowError) as error:
        raise StatefulTranslatorValidationError(
            "stateful package cue is invalid"
        ) from error


def _parse_output_cue(value: object) -> HermesV2CueOutput:
    if type(value) is not dict:
        raise StatefulTranslatorValidationError(
            "each stateful result cue must be a JSON object"
        )
    expected_fields = {"cue_id", "repaired_ja", "ko"}
    if set(value) != expected_fields:
        raise StatefulTranslatorValidationError(
            "stateful result cue fields are not exact"
        )
    try:
        return HermesV2CueOutput(
            cue_id=value["cue_id"],
            repaired_ja=value["repaired_ja"],
            ko=value["ko"],
        )
    except (TypeError, ValueError, OverflowError) as error:
        raise StatefulTranslatorValidationError(
            "stateful result cue is invalid"
        ) from error


def parse_stateful_package(payload: bytes) -> StatefulSubtitlePackage:
    """Strictly parse one complete title-level semantic package."""

    parsed = _load_json_object(
        payload,
        limit=STATEFUL_TRANSLATOR_MAX_PACKAGE_BYTES,
        label="stateful package",
    )
    expected_fields = {
        "schema_version",
        "dvd_id",
        "generation_key",
        "claim_token",
        "cues",
    }
    if set(parsed) != expected_fields:
        raise StatefulTranslatorValidationError(
            "stateful package top-level fields are not exact"
        )
    raw_cues = parsed["cues"]
    if type(raw_cues) is not list:
        raise StatefulTranslatorValidationError(
            "stateful package cues must be a JSON array"
        )
    if len(raw_cues) > STATEFUL_TRANSLATOR_MAX_CUES:
        raise StatefulTranslatorLimitError(
            "stateful package exceeds its cue limit"
        )
    try:
        return StatefulSubtitlePackage(
            schema_version=parsed["schema_version"],
            dvd_id=parsed["dvd_id"],
            generation_key=parsed["generation_key"],
            claim_token=parsed["claim_token"],
            cues=tuple(_parse_input_cue(cue) for cue in raw_cues),
        )
    except StatefulTranslatorError:
        raise
    except (TypeError, ValueError, OverflowError) as error:
        raise StatefulTranslatorValidationError(
            "stateful package is invalid"
        ) from error


def _validate_session_id(value: object) -> str:
    if type(value) is not str:
        raise StatefulTranslatorValidationError(
            "session_id must be an exact string"
        )
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, ValueError, TypeError) as error:
        raise StatefulTranslatorValidationError(
            "session_id must be a canonical UUID"
        ) from error
    if str(parsed) != value:
        raise StatefulTranslatorValidationError(
            "session_id must be a canonical UUID"
        )
    return value


def validate_stateful_result(
    result: StatefulSubtitleResult,
    package: StatefulSubtitlePackage,
) -> StatefulSubtitleResult:
    """Validate exact identity, session, cue set, and cue order."""

    validated_package = _validated_package(package)
    validated_result = _validated_result(result)
    expected_session_id = derive_stateful_session_id(
        validated_package.dvd_id,
        validated_package.generation_key,
        validated_package.claim_token,
    )
    if (
        validated_result.schema_version != validated_package.schema_version
        or validated_result.dvd_id != validated_package.dvd_id
        or validated_result.generation_key != validated_package.generation_key
        or validated_result.claim_token != validated_package.claim_token
        or validated_result.session_id != expected_session_id
    ):
        raise StatefulTranslatorValidationError(
            "stateful result identity does not match its package"
        )
    expected_ids = tuple(cue.cue_id for cue in validated_package.cues)
    actual_ids = tuple(cue.cue_id for cue in validated_result.cues)
    if actual_ids != expected_ids:
        raise StatefulTranslatorValidationError(
            "stateful result cue IDs must exactly match package order"
        )
    return validated_result


def parse_stateful_result(
    payload: bytes,
    package: StatefulSubtitlePackage,
) -> StatefulSubtitleResult:
    """Strictly parse one complete result against one exact package."""

    validated_package = _validated_package(package)
    parsed = _load_json_object(
        payload,
        limit=STATEFUL_TRANSLATOR_MAX_RESULT_BYTES,
        label="stateful result",
    )
    expected_fields = {
        "schema_version",
        "dvd_id",
        "generation_key",
        "claim_token",
        "session_id",
        "cues",
    }
    if set(parsed) != expected_fields:
        raise StatefulTranslatorValidationError(
            "stateful result top-level fields are not exact"
        )
    raw_cues = parsed["cues"]
    if type(raw_cues) is not list:
        raise StatefulTranslatorValidationError(
            "stateful result cues must be a JSON array"
        )
    if len(raw_cues) > STATEFUL_TRANSLATOR_MAX_CUES:
        raise StatefulTranslatorLimitError(
            "stateful result exceeds its cue limit"
        )
    try:
        result = StatefulSubtitleResult(
            schema_version=parsed["schema_version"],
            dvd_id=parsed["dvd_id"],
            generation_key=parsed["generation_key"],
            claim_token=parsed["claim_token"],
            session_id=parsed["session_id"],
            cues=tuple(_parse_output_cue(cue) for cue in raw_cues),
        )
    except StatefulTranslatorError:
        raise
    except (TypeError, ValueError, OverflowError) as error:
        raise StatefulTranslatorValidationError(
            "stateful result is invalid"
        ) from error
    return validate_stateful_result(result, validated_package)


def derive_stateful_session_id(
    dvd_id: str,
    generation_key: str,
    claim_token: int,
) -> str:
    """Derive a stable UUID5 from nondialogue Stage11 identity metadata."""

    dvd_id = _require_exact_string(dvd_id, field_name="dvd_id")
    generation_key = _require_exact_string(
        generation_key,
        field_name="generation_key",
    )
    claim_token = _validate_claim_token(claim_token)
    identity = json.dumps(
        [dvd_id, generation_key, claim_token],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return str(uuid.uuid5(STATEFUL_TRANSLATOR_SESSION_NAMESPACE, identity))


def stateful_session_id_for_package(
    package: StatefulSubtitlePackage,
) -> str:
    """Derive the session identity for one validated package."""

    validated = _validated_package(package)
    return derive_stateful_session_id(
        validated.dvd_id,
        validated.generation_key,
        validated.claim_token,
    )


def premint_stateful_session(
    session_db: object,
    package: StatefulSubtitlePackage,
) -> str:
    """Create the exact caller-supplied ID through an injected native API."""

    validated = _validated_package(package)
    session_id = stateful_session_id_for_package(validated)
    create_session = getattr(session_db, "create_session", None)
    if not callable(create_session):
        raise StatefulTranslatorSessionError(
            "injected session database lacks native create_session"
        )
    try:
        returned_id = create_session(
            session_id=session_id,
            source=STATEFUL_TRANSLATOR_SESSION_SOURCE,
        )
    except Exception as error:
        raise StatefulTranslatorSessionError(
            "native stateful session pre-mint failed"
        ) from error
    if type(returned_id) is not str or returned_id != session_id:
        raise StatefulTranslatorSessionError(
            "native stateful session pre-mint returned a different ID"
        )
    return session_id


class StatefulTranslatorSessionPremintAdapter:
    """Small dependency-injected adapter around native SessionDB creation."""

    def __init__(self, session_db: object):
        if session_db is None:
            raise StatefulTranslatorSessionError(
                "an injected native session database is required"
            )
        self._session_db = session_db

    def premint(self, package: StatefulSubtitlePackage) -> str:
        return premint_stateful_session(self._session_db, package)


def build_stateful_translator_command(session_id: str) -> list[str]:
    """Build the native CT120 command without invoking it."""

    session_id = _validate_session_id(session_id)
    return [
        STATEFUL_TRANSLATOR_EXECUTABLE,
        "--profile",
        STATEFUL_TRANSLATOR_PROFILE,
        STATEFUL_TRANSLATOR_SUBCOMMAND,
        STATEFUL_TRANSLATOR_QUIET_FLAG,
        STATEFUL_TRANSLATOR_RESUME_FLAG,
        session_id,
        "--provider",
        STATEFUL_TRANSLATOR_PROVIDER,
        "--model",
        STATEFUL_TRANSLATOR_MODEL,
        "--reasoning",
        STATEFUL_TRANSLATOR_REASONING,
        STATEFUL_TRANSLATOR_QUERY_FLAG,
        STATEFUL_TRANSLATOR_QUERY,
    ]


def _validate_staging_filename(filename: object) -> str:
    if type(filename) is not str:
        raise StatefulTranslatorStagingError(
            "staging filename must be an exact string"
        )
    if filename not in {
        STATEFUL_TRANSLATOR_INPUT_FILENAME,
        STATEFUL_TRANSLATOR_RESULT_FILENAME,
    }:
        raise StatefulTranslatorStagingError(
            "staging filename is not one of the fixed safe names"
        )
    if (
        not filename
        or filename in {".", ".."}
        or "/" in filename
        or "\\" in filename
    ):
        raise StatefulTranslatorStagingError(
            "staging filename contains an unsafe path component"
        )
    return filename


def _validated_task_directory(task_directory: str | Path) -> Path:
    try:
        path = Path(task_directory)
    except (TypeError, ValueError) as error:
        raise StatefulTranslatorStagingError(
            "staging task directory is invalid"
        ) from error
    try:
        directory_stat = os.stat(path, follow_symlinks=False)
    except OSError as error:
        raise StatefulTranslatorStagingError(
            "staging task directory is unavailable"
        ) from error
    if not stat.S_ISDIR(directory_stat.st_mode):
        raise StatefulTranslatorStagingError(
            "staging task directory is not a directory"
        )
    if stat.S_IMODE(directory_stat.st_mode) != STATEFUL_TRANSLATOR_TASK_DIRECTORY_MODE:
        raise StatefulTranslatorStagingError(
            "staging task directory mode is not private"
        )
    return path


def resolve_stateful_staging_path(
    task_directory: str | Path,
    filename: str,
) -> Path:
    """Resolve only one of the fixed private staging file names."""

    directory = _validated_task_directory(task_directory)
    filename = _validate_staging_filename(filename)
    candidate = directory / filename
    if candidate.parent != directory or candidate.name != filename:
        raise StatefulTranslatorStagingError(
            "staging path escapes its task directory"
        )
    return candidate


@dataclass(frozen=True)
class StatefulTranslatorStagingPaths:
    """Fixed paths inside one private task directory."""

    task_directory: Path
    input_path: Path
    result_path: Path


def stateful_staging_paths(
    task_directory: str | Path,
) -> StatefulTranslatorStagingPaths:
    directory = _validated_task_directory(task_directory)
    return StatefulTranslatorStagingPaths(
        task_directory=directory,
        input_path=resolve_stateful_staging_path(
            directory,
            STATEFUL_TRANSLATOR_INPUT_FILENAME,
        ),
        result_path=resolve_stateful_staging_path(
            directory,
            STATEFUL_TRANSLATOR_RESULT_FILENAME,
        ),
    )


def create_stateful_staging_directory(
    root_directory: str | Path,
    session_id: str,
) -> Path:
    """Create one private task directory named only by the session UUID."""

    session_id = _validate_session_id(session_id)
    try:
        root = Path(root_directory)
        root_stat = os.stat(root, follow_symlinks=False)
    except (OSError, TypeError, ValueError) as error:
        raise StatefulTranslatorStagingError(
            "staging root is unavailable"
        ) from error
    if not stat.S_ISDIR(root_stat.st_mode):
        raise StatefulTranslatorStagingError(
            "staging root is not a directory"
        )
    task_directory = root / session_id
    if task_directory.exists() or task_directory.is_symlink():
        raise StatefulTranslatorStagingError(
            "stateful staging task directory already exists"
        )
    try:
        os.mkdir(task_directory, STATEFUL_TRANSLATOR_TASK_DIRECTORY_MODE)
        os.chmod(task_directory, STATEFUL_TRANSLATOR_TASK_DIRECTORY_MODE)
    except OSError as error:
        raise StatefulTranslatorStagingError(
            "stateful staging task directory could not be created"
        ) from error
    return task_directory


def _fsync_directory(directory: Path) -> None:
    try:
        directory_fd = os.open(
            directory,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
    except OSError as error:
        raise StatefulTranslatorStagingError(
            "staging directory could not be opened for durability"
        ) from error
    try:
        os.fsync(directory_fd)
    except OSError as error:
        raise StatefulTranslatorStagingError(
            "staging directory could not be synchronized"
        ) from error
    finally:
        os.close(directory_fd)


def _atomic_private_write(path: Path, payload: bytes) -> None:
    try:
        existing_stat = os.lstat(path)
    except FileNotFoundError:
        existing_stat = None
    except OSError as error:
        raise StatefulTranslatorStagingError(
            "staging destination could not be inspected"
        ) from error
    if existing_stat is not None:
        raise StatefulTranslatorStagingError(
            "staging destination already exists"
        )

    temporary_path: str | None = None
    file_descriptor: int | None = None
    try:
        file_descriptor, temporary_path = tempfile.mkstemp(
            prefix=".stage11-private-",
            dir=str(path.parent),
        )
        os.fchmod(file_descriptor, STATEFUL_TRANSLATOR_PRIVATE_FILE_MODE)
        with os.fdopen(file_descriptor, "wb") as stream:
            file_descriptor = None
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
        _fsync_directory(path.parent)
        final_stat = os.stat(path, follow_symlinks=False)
        if stat.S_IMODE(final_stat.st_mode) != STATEFUL_TRANSLATOR_PRIVATE_FILE_MODE:
            raise StatefulTranslatorStagingError(
                "staging artifact mode is not private"
            )
    except StatefulTranslatorError:
        raise
    except (OSError, TypeError, ValueError) as error:
        raise StatefulTranslatorStagingError(
            "private staging write failed"
        ) from error
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass
            except OSError:
                pass


def write_stateful_input(
    task_directory: str | Path,
    package: StatefulSubtitlePackage,
) -> Path:
    """Atomically write the bounded dialogue-bearing input artifact."""

    paths = stateful_staging_paths(task_directory)
    payload = serialize_stateful_package(package)
    _atomic_private_write(paths.input_path, payload)
    return paths.input_path


def _read_private_result_bytes(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        file_descriptor = os.open(path, flags)
    except OSError as error:
        raise StatefulTranslatorStagingError(
            "stateful result cannot be opened safely"
        ) from error
    try:
        file_stat = os.fstat(file_descriptor)
        if not stat.S_ISREG(file_stat.st_mode):
            raise StatefulTranslatorStagingError(
                "stateful result is not a regular file"
            )
        if stat.S_IMODE(file_stat.st_mode) != STATEFUL_TRANSLATOR_PRIVATE_FILE_MODE:
            raise StatefulTranslatorStagingError(
                "stateful result mode is not private"
            )
        if (
            file_stat.st_size <= 0
            or file_stat.st_size > STATEFUL_TRANSLATOR_MAX_RESULT_BYTES
        ):
            raise StatefulTranslatorLimitError(
                "stateful result file exceeds its bounded byte limit"
            )
        with os.fdopen(file_descriptor, "rb") as stream:
            file_descriptor = -1
            payload = stream.read(STATEFUL_TRANSLATOR_MAX_RESULT_BYTES + 1)
        if len(payload) == 0 or len(payload) > STATEFUL_TRANSLATOR_MAX_RESULT_BYTES:
            raise StatefulTranslatorLimitError(
                "stateful result read exceeds its bounded byte limit"
            )
        return payload
    except StatefulTranslatorError:
        raise
    except OSError as error:
        raise StatefulTranslatorStagingError(
            "stateful result read failed"
        ) from error
    finally:
        if file_descriptor not in (None, -1):
            os.close(file_descriptor)


def read_stateful_result(
    task_directory: str | Path,
    package: StatefulSubtitlePackage,
    *,
    process_finished: bool,
) -> StatefulSubtitleResult:
    """Consume a result only after the launcher has observed process exit."""

    if type(process_finished) is not bool or not process_finished:
        raise StatefulTranslatorStagingError(
            "stateful result cannot be consumed before process completion"
        )
    paths = stateful_staging_paths(task_directory)
    payload = _read_private_result_bytes(paths.result_path)
    return parse_stateful_result(payload, package)


def consume_stateful_result(
    task_directory: str | Path,
    package: StatefulSubtitlePackage,
    *,
    process_finished: bool,
) -> StatefulSubtitleResult:
    """Explicit alias for the post-process result-consumption boundary."""

    return read_stateful_result(
        task_directory,
        package,
        process_finished=process_finished,
    )


__all__ = [
    "MAX_STATEFUL_TRANSLATOR_CUES",
    "MAX_STATEFUL_TRANSLATOR_PACKAGE_BYTES",
    "MAX_STATEFUL_TRANSLATOR_RESULT_BYTES",
    "STATEFUL_TRANSLATOR_EXECUTABLE",
    "STATEFUL_TRANSLATOR_INPUT_FILENAME",
    "STATEFUL_TRANSLATOR_MAX_CLAIM_TOKEN",
    "STATEFUL_TRANSLATOR_MAX_CUES",
    "STATEFUL_TRANSLATOR_MAX_IDENTIFIER_CHARS",
    "STATEFUL_TRANSLATOR_MAX_PACKAGE_BYTES",
    "STATEFUL_TRANSLATOR_MAX_RESULT_BYTES",
    "STATEFUL_TRANSLATOR_MODEL",
    "STATEFUL_TRANSLATOR_PRIVATE_FILE_MODE",
    "STATEFUL_TRANSLATOR_PROFILE",
    "STATEFUL_TRANSLATOR_PROVIDER",
    "STATEFUL_TRANSLATOR_QUERY",
    "STATEFUL_TRANSLATOR_QUERY_FLAG",
    "STATEFUL_TRANSLATOR_REASONING",
    "STATEFUL_TRANSLATOR_RESULT_FILENAME",
    "STATEFUL_TRANSLATOR_RESUME_FLAG",
    "STATEFUL_TRANSLATOR_SCHEMA_VERSION",
    "STATEFUL_TRANSLATOR_SESSION_NAMESPACE",
    "STATEFUL_TRANSLATOR_SESSION_SOURCE",
    "STATEFUL_TRANSLATOR_SUBCOMMAND",
    "STATEFUL_TRANSLATOR_TASK_DIRECTORY_MODE",
    "STATEFUL_TRANSLATOR_QUIET_FLAG",
    "StatefulSubtitlePackage",
    "StatefulSubtitleResult",
    "StatefulTranslatorError",
    "StatefulTranslatorLimitError",
    "StatefulTranslatorSessionError",
    "StatefulTranslatorSessionPremintAdapter",
    "StatefulTranslatorStagingError",
    "StatefulTranslatorStagingPaths",
    "StatefulTranslatorValidationError",
    "build_stateful_translator_command",
    "consume_stateful_result",
    "create_stateful_staging_directory",
    "derive_stateful_session_id",
    "parse_stateful_package",
    "parse_stateful_result",
    "premint_stateful_session",
    "read_stateful_result",
    "resolve_stateful_staging_path",
    "serialize_stateful_package",
    "serialize_stateful_result",
    "stateful_session_id_for_package",
    "stateful_staging_paths",
    "validate_stateful_result",
    "write_stateful_input",
]
