"""Read-only, privacy-safe summaries for subtitle-bearing JSON artifacts.

The inspector never serializes artifact contents or filesystem paths. Output is
restricted to hashes, byte/count metadata, canonical identifiers, and fixed
status/error enums so it is safe to use in preflight tool output.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Final


MAX_INSPECTED_ARTIFACT_BYTES: Final[int] = 64 * 1024 * 1024
ARTIFACT_KINDS: Final[tuple[str, ...]] = (
    "asr",
    "targeted_evidence",
    "semantic_input",
    "semantic_output",
    "review",
    "controller_report",
)
_SAFE_TARGETED_STATUSES: Final[frozenset[str]] = frozenset(
    {
        "PRESENT_UNRESOLVED",
        "EMPTY_UNRESOLVED",
        "NOISY_UNRESOLVED",
    }
)
_SAFE_ROUTES: Final[frozenset[str]] = frozenset({"ASR_ONLY", "HYBRID"})
_SHA256_CHARS: Final[frozenset[str]] = frozenset("0123456789abcdef")
_SAFE_DVD_ID_RE: Final[re.Pattern[str]] = re.compile(
    r"[A-Z0-9]+(?:-[A-Z0-9]+)+\Z"
)


def _is_sha256(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(char in _SHA256_CHARS for char in value)
    )


def _list_count(value: object) -> int | None:
    return len(value) if type(value) is list else None


def _source_snapshot(document: dict[str, object]) -> object:
    snapshot = document.get("source_snapshot")
    if type(snapshot) is dict:
        return snapshot
    source = document.get("source")
    if type(source) is dict and type(source.get("source_snapshot")) is dict:
        return source["source_snapshot"]
    return None


def _source_match(
    snapshot: object,
    *,
    expected_dvd_id: str | None,
    expected_source_size: int | None,
    expected_source_mtime_ns: int | None,
    expected_baseline_sha256: str | None,
    document: dict[str, object],
) -> str:
    expected = (
        expected_dvd_id is not None
        or expected_source_size is not None
        or expected_source_mtime_ns is not None
        or expected_baseline_sha256 is not None
    )
    if not expected:
        return "NOT_CHECKED"
    if type(snapshot) is not dict:
        return "NO"
    checks: list[bool] = []
    if expected_dvd_id is not None:
        checks.append(snapshot.get("dvd_id") == expected_dvd_id)
    if expected_source_size is not None:
        checks.append(snapshot.get("source_size") == expected_source_size)
    if expected_source_mtime_ns is not None:
        checks.append(snapshot.get("source_mtime_ns") == expected_source_mtime_ns)
    if expected_baseline_sha256 is not None:
        checks.append(
            document.get("baseline_asr_artifact_sha256")
            == expected_baseline_sha256
        )
    return "YES" if checks and all(checks) else "NO"


def _safe_document_summary(
    document: dict[str, object],
    *,
    kind: str,
    expected_dvd_id: str | None,
    expected_source_size: int | None,
    expected_source_mtime_ns: int | None,
    expected_baseline_sha256: str | None,
) -> dict[str, object]:
    summary: dict[str, object] = {
        "artifact_kind": kind,
        "schema_version": (
            document.get("schema_version")
            if type(document.get("schema_version")) is int
            else None
        ),
    }
    dvd_id = document.get("dvd_id")
    snapshot = _source_snapshot(document)
    if type(snapshot) is dict:
        dvd_id = snapshot.get("dvd_id", dvd_id)
    if (
        type(dvd_id) is str
        and len(dvd_id) <= 64
        and _SAFE_DVD_ID_RE.fullmatch(dvd_id) is not None
    ):
        summary["dvd_id"] = dvd_id
    summary["source_fingerprint_match"] = _source_match(
        snapshot,
        expected_dvd_id=expected_dvd_id,
        expected_source_size=expected_source_size,
        expected_source_mtime_ns=expected_source_mtime_ns,
        expected_baseline_sha256=expected_baseline_sha256,
        document=document,
    )

    if kind == "asr":
        summary["segment_count"] = _list_count(document.get("segments"))
    elif kind == "targeted_evidence":
        sources = _list_count(document.get("sources"))
        windows = _list_count(document.get("windows"))
        results = _list_count(document.get("results"))
        bindings = document.get("bindings")
        summary["source_count"] = sources
        summary["window_count"] = windows
        summary["result_count"] = results
        if type(bindings) is list:
            counts: Counter[str] = Counter()
            for binding in bindings:
                status = binding.get("status") if type(binding) is dict else None
                if type(status) is str and status in _SAFE_TARGETED_STATUSES:
                    counts[status] += 1
                else:
                    counts["OTHER"] += 1
            summary["binding_status_counts"] = dict(sorted(counts.items()))
        else:
            summary["binding_status_counts"] = None
    elif kind in {"semantic_input", "semantic_output", "review"}:
        summary["cue_count"] = _list_count(document.get("cues"))
        session_keys = {
            "session_id",
            "source_translation_session_id",
            "review_execution_session_id",
        }
        summary["session_identity_field_count"] = sum(
            1 for key in session_keys if key in document
        )
        for key in ("part_number", "part", "part_count"):
            value = document.get(key)
            if type(value) is int and 0 <= value <= 1_000_000:
                summary[key] = value
    elif kind == "controller_report":
        route = document.get("route")
        summary["route"] = route if route in _SAFE_ROUTES else "OTHER"
        translation = document.get("translation_result_identity")
        review = document.get("review_result_identity")
        identity_objects = [
            value for value in (translation, review) if type(value) is dict
        ]
        raw_fields = {
            "session_id",
            "source_translation_session_id",
            "review_execution_session_id",
        }
        summary["raw_session_identity_field_count"] = sum(
            1 for identity in identity_objects for key in raw_fields if key in identity
        )
        summary["session_fingerprint_field_count"] = sum(
            1
            for identity in identity_objects
            for key in identity
            if key.endswith("session_id_sha256") and _is_sha256(identity[key])
        )
        summary["report_field_count"] = len(document)
    return summary


def inspect_artifact(
    path: str | os.PathLike[str],
    *,
    kind: str,
    expected_dvd_id: str | None = None,
    expected_source_size: int | None = None,
    expected_source_mtime_ns: int | None = None,
    expected_baseline_sha256: str | None = None,
) -> dict[str, object]:
    """Return only allowlisted metadata; never include a path or body value."""

    if kind not in ARTIFACT_KINDS:
        return {"exists": False, "error_code": "UNSUPPORTED_ARTIFACT_KIND"}
    try:
        file_path = Path(path)
        metadata = file_path.lstat()
    except FileNotFoundError:
        return {"artifact_kind": kind, "exists": False, "error_code": "NOT_FOUND"}
    except OSError:
        return {"artifact_kind": kind, "exists": False, "error_code": "READ_ERROR"}

    base: dict[str, object] = {"artifact_kind": kind, "exists": True}
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        base["error_code"] = "UNSAFE_FILE_TYPE"
        return base
    base["byte_size"] = metadata.st_size
    if metadata.st_size < 0 or metadata.st_size > MAX_INSPECTED_ARTIFACT_BYTES:
        base["error_code"] = "ARTIFACT_TOO_LARGE"
        return base
    try:
        payload = file_path.read_bytes()
    except OSError:
        base["error_code"] = "READ_ERROR"
        return base
    base["byte_size"] = len(payload)
    base["sha256"] = hashlib.sha256(payload).hexdigest()
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeError, ValueError):
        base["error_code"] = "INVALID_JSON"
        return base
    if type(document) is not dict:
        base["error_code"] = "UNSUPPORTED_SHAPE"
        return base
    try:
        summary = _safe_document_summary(
            document,
            kind=kind,
            expected_dvd_id=expected_dvd_id,
            expected_source_size=expected_source_size,
            expected_source_mtime_ns=expected_source_mtime_ns,
            expected_baseline_sha256=expected_baseline_sha256,
        )
    except Exception:
        base["error_code"] = "UNSUPPORTED_SHAPE"
        return base
    base.update(summary)
    return base


def render_safe_summary(summary: dict[str, object]) -> str:
    """Serialize only the internal allowlist summary mapping."""

    safe_keys = {
        "artifact_kind",
        "exists",
        "error_code",
        "byte_size",
        "sha256",
        "schema_version",
        "dvd_id",
        "source_fingerprint_match",
        "segment_count",
        "source_count",
        "window_count",
        "result_count",
        "binding_status_counts",
        "cue_count",
        "session_identity_field_count",
        "part_number",
        "part",
        "part_count",
        "route",
        "raw_session_identity_field_count",
        "session_fingerprint_field_count",
        "report_field_count",
    }
    if type(summary) is not dict or not set(summary).issubset(safe_keys):
        return json.dumps(
            {"error_code": "UNSUPPORTED_SUMMARY"},
            sort_keys=True,
            separators=(",", ":"),
        )
    return json.dumps(
        summary,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=ARTIFACT_KINDS, required=True)
    parser.add_argument("--path", required=True, help="never emitted in output")
    parser.add_argument(
        "--expected-dvd-id",
        help="optional source identity comparison; output is the canonical ID only",
    )
    parser.add_argument("--expected-source-size", type=int)
    parser.add_argument("--expected-source-mtime-ns", type=int)
    parser.add_argument("--expected-baseline-sha256")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = inspect_artifact(
        args.path,
        kind=args.kind,
        expected_dvd_id=args.expected_dvd_id,
        expected_source_size=args.expected_source_size,
        expected_source_mtime_ns=args.expected_source_mtime_ns,
        expected_baseline_sha256=args.expected_baseline_sha256,
    )
    print(render_safe_summary(summary))
    return 0 if "error_code" not in summary else 1


if __name__ == "__main__":
    raise SystemExit(main())
