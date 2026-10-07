"""Deterministic HYBRID adjacent-boundary evidence, separate from semantic JSON.

The canonical sidecar names the pre-binding package/session to avoid a digest
cycle. Its SHA lives in the final package's existing model-input generation
marker and therefore in the existing deterministic session derivation.
"""

from dataclasses import asdict, dataclass, fields, replace
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import unicodedata

from teddy_discovery_hybrid_evidence import HybridCueIdentity
from teddy_discovery_stateful_hybrid import StatefulHybridPreparation
from teddy_discovery_stateful_translator import (
    STATEFUL_BOUNDARY_MODEL_INPUT_MARKER, STATEFUL_TRANSLATOR_MAX_CUES,
    StatefulSubtitlePackage, _atomic_private_write, _load_json_object,
    _require_exact_string, _validated_package, _validated_task_directory,
    bind_stateful_model_input_generation_key, derive_stateful_session_id,
    serialize_stateful_package, stateful_boundary_digest_from_generation_key,
    stateful_session_id_for_package,
)
from teddy_discovery_subtitle_v2_orchestrator import project_affine_timestamp_ms


STATEFUL_BOUNDARY_FILENAME = "stage11-boundary-evidence-v1.json"
STATEFUL_BOUNDARY_SCHEMA_VERSION = 1
STATEFUL_BOUNDARY_MAX_BYTES = 1024 * 1024


class StatefulBoundaryValidationError(ValueError):
    """Boundary evidence or its model-input binding is detached."""


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise StatefulBoundaryValidationError("invalid boundary identity digest")


def _identifier(value, *, name, max_chars=256):
    _require_exact_string(value, field_name=name, max_chars=max_chars)
    if any(unicodedata.category(char) == "Cc" for char in value):
        raise StatefulBoundaryValidationError("boundary identity contains control data")


@dataclass(frozen=True)
class StatefulAdjacentBoundary:
    left_cue_id: str
    right_cue_id: str
    left_source_index: int
    right_source_index: int
    gap_ms: int
    relation: str

    def __post_init__(self):
        for cue_id in (self.left_cue_id, self.right_cue_id):
            _identifier(cue_id, name="boundary cue_id", max_chars=128)
        if (type(self.left_source_index) is not int
                or type(self.right_source_index) is not int
                or not 0 <= self.left_source_index < self.right_source_index < STATEFUL_TRANSLATOR_MAX_CUES
                or self.right_source_index != self.left_source_index + 1
                or self.left_cue_id != HybridCueIdentity.for_external_ja(self.left_source_index).cue_id
                or self.right_cue_id != HybridCueIdentity.for_external_ja(self.right_source_index).cue_id):
            raise StatefulBoundaryValidationError("boundary source identities are not adjacent")
        if type(self.gap_ms) is not int:
            raise StatefulBoundaryValidationError("boundary gap must be an exact signed integer")
        expected = "OVERLAP" if self.gap_ms < 0 else "TOUCHING" if self.gap_ms == 0 else "GAP"
        if type(self.relation) is not str or self.relation != expected:
            raise StatefulBoundaryValidationError("boundary relation differs from exact gap")


@dataclass(frozen=True)
class StatefulBoundaryEvidence:
    schema_version: int
    dvd_id: str
    generation_key: str
    claim_token: int
    session_id: str
    package_sha256: str
    source_sha256: str
    source_identity_sha256: str
    alignment_sha256: str
    pairs: tuple[StatefulAdjacentBoundary, ...]

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != STATEFUL_BOUNDARY_SCHEMA_VERSION:
            raise StatefulBoundaryValidationError("unsupported boundary schema")
        for name in ("dvd_id", "generation_key", "session_id"):
            _identifier(getattr(self, name), name=name)
        if (type(self.claim_token) is not int or self.claim_token <= 0
                or self.session_id != derive_stateful_session_id(
                    self.dvd_id, self.generation_key, self.claim_token)
                or stateful_boundary_digest_from_generation_key(self.generation_key) is not None):
            raise StatefulBoundaryValidationError("invalid pre-binding boundary package/session identity")
        for digest in (self.package_sha256, self.source_sha256,
                       self.source_identity_sha256, self.alignment_sha256):
            _digest(digest)
        if type(self.pairs) is not tuple or len(self.pairs) >= STATEFUL_TRANSLATOR_MAX_CUES:
            raise StatefulBoundaryValidationError("boundary pairs must be bounded and immutable")
        for index, pair in enumerate(self.pairs):
            if type(pair) is not StatefulAdjacentBoundary:
                raise StatefulBoundaryValidationError("invalid boundary pair type")
            pair.__post_init__()
            if pair.left_source_index != index:
                raise StatefulBoundaryValidationError("boundary pair order is not contiguous")


def _base_package(package):
    package = _validated_package(package)
    digest = stateful_boundary_digest_from_generation_key(package.generation_key)
    if digest is None:
        return package
    return replace(package, generation_key=package.generation_key.replace(
        STATEFUL_BOUNDARY_MODEL_INPUT_MARKER + digest, "", 1))


def build_stateful_boundary_evidence(preparation):
    """Re-prove caller-held HYBRID originals before projecting any boundary."""
    try:
        if type(preparation) is not StatefulHybridPreparation:
            raise StatefulBoundaryValidationError("original HYBRID preparation required")
        preparation.__post_init__()
        package = _base_package(preparation.package)
        application = preparation.route_decision.alignment_application
        document = application.bundle.external_ja_document
        if len(package.cues) != len(document.cues):
            raise StatefulBoundaryValidationError("boundary document count differs from package")
        projected = []
        for index, (cue, binding, external) in enumerate(zip(
            package.cues, preparation.semantic_bindings, document.cues, strict=True,
        )):
            identity = HybridCueIdentity.for_external_ja(index)
            if (cue.cue_id != identity.cue_id or binding.request_cue_id != cue.cue_id
                    or binding.external_ja_identity != identity or binding.source_index != index):
                raise StatefulBoundaryValidationError("boundary package/binding/source order differs")
            start = project_affine_timestamp_ms(application.alignment, external.start_ms)
            end = project_affine_timestamp_ms(application.alignment, external.end_ms)
            if (type(start) is not int or type(end) is not int or start < 0 or start >= end
                    or (projected and start < projected[-1][0])):
                raise StatefulBoundaryValidationError("invalid projected boundary interval")
            projected.append((start, end))
        pairs = []
        for index in range(len(package.cues) - 1):
            gap = projected[index + 1][0] - projected[index][1]
            pairs.append(StatefulAdjacentBoundary(
                package.cues[index].cue_id, package.cues[index + 1].cue_id,
                index, index + 1, gap,
                "OVERLAP" if gap < 0 else "TOUCHING" if gap == 0 else "GAP",
            ))
        payload = application.bundle.external_ja_payload
        return StatefulBoundaryEvidence(
            STATEFUL_BOUNDARY_SCHEMA_VERSION, package.dvd_id, package.generation_key,
            package.claim_token, stateful_session_id_for_package(package),
            _sha(serialize_stateful_package(package)), payload.sha256,
            _sha(_json({"source_url": payload.candidate.external_source_id, "dvd_id": payload.dvd_id,
                        "source_sha256": payload.sha256})),
            _sha(_json(asdict(application.alignment))), tuple(pairs),
        )
    except StatefulBoundaryValidationError:
        raise
    except Exception as error:
        raise StatefulBoundaryValidationError("invalid or detached HYBRID boundary originals") from error


def serialize_stateful_boundary_evidence(evidence):
    if type(evidence) is not StatefulBoundaryEvidence:
        raise StatefulBoundaryValidationError("exact boundary evidence type required")
    evidence.__post_init__()
    payload = _json(asdict(evidence))
    if len(payload) > STATEFUL_BOUNDARY_MAX_BYTES:
        raise StatefulBoundaryValidationError("boundary evidence exceeds byte bound")
    return payload


def validate_stateful_boundary_evidence(evidence, package, *, preparation=None):
    """Native readers trust the canonical SHA bound by the original controller."""
    expected_digest = stateful_boundary_digest_from_generation_key(package.generation_key)
    if evidence is None:
        if expected_digest is not None:
            raise StatefulBoundaryValidationError("bound model input requires boundary evidence")
        return None
    wire = serialize_stateful_boundary_evidence(evidence)
    if expected_digest != _sha(wire):
        raise StatefulBoundaryValidationError("boundary canonical SHA differs from model-input identity")
    base = _base_package(package)
    if (evidence.package_sha256 != _sha(serialize_stateful_package(base))
            or evidence.dvd_id != base.dvd_id or evidence.generation_key != base.generation_key
            or evidence.claim_token != base.claim_token
            or evidence.session_id != stateful_session_id_for_package(base)
            or len(evidence.pairs) != len(base.cues) - 1
            or any(c.external_ja is None for c in base.cues)):
        raise StatefulBoundaryValidationError("boundary evidence is detached from package/session")
    for pair in evidence.pairs:
        if (base.cues[pair.left_source_index].cue_id != pair.left_cue_id
                or base.cues[pair.right_source_index].cue_id != pair.right_cue_id):
            raise StatefulBoundaryValidationError("boundary pair is not package-adjacent")
    if preparation is not None and (preparation.package != package
            or evidence != build_stateful_boundary_evidence(preparation)):
        raise StatefulBoundaryValidationError("boundary evidence differs from accepted source/alignment")
    return evidence


def bind_stateful_boundary_preparation(preparation):
    # The pre-binding identity already carries the existing normalization
    # marker; adding boundary evidence must not implicitly change that base.
    if type(preparation) is not StatefulHybridPreparation:
        raise StatefulBoundaryValidationError("original HYBRID preparation required")
    preparation = replace(preparation, package=replace(preparation.package,
        generation_key=bind_stateful_model_input_generation_key(preparation.package.generation_key)))
    evidence = build_stateful_boundary_evidence(preparation)
    generation_key = bind_stateful_model_input_generation_key(
        preparation.package.generation_key,
        boundary_evidence_sha256=_sha(serialize_stateful_boundary_evidence(evidence)),
    )
    bound = replace(preparation, package=replace(preparation.package, generation_key=generation_key))
    validate_stateful_boundary_evidence(evidence, bound.package, preparation=bound)
    return bound, evidence


def parse_stateful_boundary_evidence(payload, package):
    try:
        data = _load_json_object(payload, limit=STATEFUL_BOUNDARY_MAX_BYTES, label="boundary evidence")
        if set(data) != {f.name for f in fields(StatefulBoundaryEvidence)} or type(data["pairs"]) is not list:
            raise StatefulBoundaryValidationError("boundary wire fields are not exact")
        if len(data["pairs"]) >= STATEFUL_TRANSLATOR_MAX_CUES:
            raise StatefulBoundaryValidationError("boundary wire pair count exceeds bound")
        pairs = []
        for pair in data["pairs"]:
            if type(pair) is not dict or set(pair) != {f.name for f in fields(StatefulAdjacentBoundary)}:
                raise StatefulBoundaryValidationError("boundary pair wire fields are not exact")
            pairs.append(StatefulAdjacentBoundary(**pair))
        evidence = StatefulBoundaryEvidence(**dict(data, pairs=tuple(pairs)))
        if serialize_stateful_boundary_evidence(evidence) != payload:
            raise StatefulBoundaryValidationError("boundary wire is not canonical")
        return validate_stateful_boundary_evidence(evidence, package)
    except StatefulBoundaryValidationError:
        raise
    except Exception as error:
        raise StatefulBoundaryValidationError("invalid boundary wire") from error


def read_stateful_boundary_evidence(path, package):
    path = Path(path)
    _validated_task_directory(path.parent)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600
                or not 0 < info.st_size <= STATEFUL_BOUNDARY_MAX_BYTES):
            raise StatefulBoundaryValidationError("boundary sidecar is not private/bounded/regular")
        with os.fdopen(fd, "rb") as stream:
            fd = None
            payload = stream.read(STATEFUL_BOUNDARY_MAX_BYTES + 1)
        return parse_stateful_boundary_evidence(payload, package)
    finally:
        if fd is not None:
            os.close(fd)


def stage_stateful_boundary_evidence(directory, evidence, package):
    validate_stateful_boundary_evidence(evidence, package)
    path = _validated_task_directory(directory) / STATEFUL_BOUNDARY_FILENAME
    if path.exists() or path.is_symlink():
        if read_stateful_boundary_evidence(path, package) != evidence:
            raise StatefulBoundaryValidationError("existing boundary sidecar differs")
    else:
        _atomic_private_write(path, serialize_stateful_boundary_evidence(evidence))
    if read_stateful_boundary_evidence(path, package) != evidence:
        raise StatefulBoundaryValidationError("boundary sidecar readback differs")
    return path


def boundary_pairs_for_cues(evidence, package, cue_ids):
    validate_stateful_boundary_evidence(evidence, package)
    selected = set(cue_ids)
    return tuple(pair for pair in evidence.pairs
                 if pair.left_cue_id in selected or pair.right_cue_id in selected)
