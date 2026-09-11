"""Read-only Stage12 holdings subtitle inventory.

This module is the first independent Stage12 owner.  It reads the existing
Discovery holdings state through the same read-only loader used by the Stage11
holding resolver, then checks only each exact canonical holding directory
through the existing bounded SSH subtitle reader.  It does not run Stage11,
write a database, write NAS media, publish subtitles, or contact Jellyfin.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import argparse

from teddy_discovery_organizer import load_db_state
from teddy_discovery_subtitle import (
    ACTION_SKIP_EXISTING_KO,
    CanonicalHoldingValidationError,
    CanonicalVideoHolding,
    SOURCE_KIND_SIBLING_TEXT,
    SubtitleCandidate,
    SubtitleDiscoveryError,
    derive_target_ko_relative,
    select_subtitle_source,
    validate_canonical_holding,
)
from teddy_discovery_subtitle_ssh import (
    SubtitleSSHError,
    SubtitleSSHReader,
)
from teddy_discovery_subtitle_text import (
    SubtitleTextError,
    parse_subtitle_bytes,
)


SKIPPED_EXISTING_KO = "SKIPPED_EXISTING_KO"
ELIGIBLE_NEEDS_KO = "ELIGIBLE_NEEDS_KO"
UNRESOLVED = "UNRESOLVED"

EXISTING_KO_VALID = "VALID"
EXISTING_KO_ABSENT = "ABSENT"
EXISTING_KO_UNRESOLVED = "UNRESOLVED"

_RECORD_STATUSES = frozenset(
    {
        SKIPPED_EXISTING_KO,
        ELIGIBLE_NEEDS_KO,
        UNRESOLVED,
    }
)
_EXISTING_KO_STATUSES = frozenset(
    {
        EXISTING_KO_VALID,
        EXISTING_KO_ABSENT,
        EXISTING_KO_UNRESOLVED,
    }
)


class Stage12InventoryError(RuntimeError):
    """Base class for read-only Stage12 inventory failures."""


class Stage12InventoryValidationError(Stage12InventoryError):
    """Raised when the authoritative inventory cannot be trusted safely."""


class DuplicateHoldingIdentityError(Stage12InventoryValidationError):
    """Raised when two holdings could address the same title/source."""


@dataclass(frozen=True)
class Stage12HoldingInventoryRecord:
    """One deterministic per-holding CP1 classification."""

    dvd_id: str | None
    holding_id: int | None
    holding_identity: str | None
    media_path_identity: str | None
    existing_ko: str
    eligibility: str
    reason: str

    def __post_init__(self):
        if self.dvd_id is not None and (
            type(self.dvd_id) is not str or not self.dvd_id
        ):
            raise Stage12InventoryValidationError(
                "record dvd_id must be a non-empty string or None"
            )
        if self.holding_id is not None and (
            type(self.holding_id) is not int or self.holding_id <= 0
        ):
            raise Stage12InventoryValidationError(
                "record holding_id must be a positive integer or None"
            )
        for field_name in (
            "holding_identity",
            "media_path_identity",
            "reason",
        ):
            value = getattr(self, field_name)
            if value is not None and type(value) is not str:
                raise Stage12InventoryValidationError(
                    field_name + " must be a string or None"
                )
        if self.existing_ko not in _EXISTING_KO_STATUSES:
            raise Stage12InventoryValidationError(
                "record existing_ko status is invalid"
            )
        if self.eligibility not in _RECORD_STATUSES:
            raise Stage12InventoryValidationError(
                "record eligibility status is invalid"
            )
        if type(self.reason) is not str or not self.reason:
            raise Stage12InventoryValidationError(
                "record reason must be non-empty"
            )

        if self.eligibility == SKIPPED_EXISTING_KO and (
            self.existing_ko != EXISTING_KO_VALID
        ):
            raise Stage12InventoryValidationError(
                "SKIPPED_EXISTING_KO requires valid existing KO"
            )
        if self.eligibility == ELIGIBLE_NEEDS_KO and (
            self.existing_ko != EXISTING_KO_ABSENT
        ):
            raise Stage12InventoryValidationError(
                "ELIGIBLE_NEEDS_KO requires absent existing KO"
            )
        if self.eligibility == UNRESOLVED and (
            self.existing_ko not in {
                EXISTING_KO_ABSENT,
                EXISTING_KO_UNRESOLVED,
            }
        ):
            raise Stage12InventoryValidationError(
                "UNRESOLVED cannot claim valid existing KO"
            )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class Stage12HoldingsInventoryReport:
    """Immutable result of one complete read-only holdings dry-run."""

    records: tuple[Stage12HoldingInventoryRecord, ...]

    @property
    def total_holdings(self) -> int:
        return len(self.records)

    @property
    def existing_ko_count(self) -> int:
        return sum(
            record.eligibility == SKIPPED_EXISTING_KO
            for record in self.records
        )

    @property
    def eligible_count(self) -> int:
        return sum(
            record.eligibility == ELIGIBLE_NEEDS_KO
            for record in self.records
        )

    @property
    def unresolved_count(self) -> int:
        return sum(
            record.eligibility == UNRESOLVED
            for record in self.records
        )

    def records_for(self, status: str) -> tuple[Stage12HoldingInventoryRecord, ...]:
        if status not in _RECORD_STATUSES:
            raise Stage12InventoryValidationError(
                "unknown inventory status"
            )
        return tuple(
            record
            for record in self.records
            if record.eligibility == status
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "total_holdings": self.total_holdings,
            "existing_ko": self.existing_ko_count,
            "eligible_needs_ko": self.eligible_count,
            "unresolved": self.unresolved_count,
            "records": [record.to_dict() for record in self.records],
        }


def _holding_id(row: Mapping[str, object]) -> int | None:
    value = row.get("holding_id")
    if type(value) is int and value > 0:
        return value
    return None


def _safe_text(row: Mapping[str, object], field_name: str) -> str | None:
    value = row.get(field_name)
    if isinstance(value, str) and value:
        return value
    return None


def _holding_identity(row: Mapping[str, object]) -> str | None:
    storage_root = _safe_text(row, "storage_root")
    relative_path = _safe_text(row, "relative_path")
    if storage_root is None or relative_path is None:
        return None
    return storage_root + ":" + relative_path


def _record(
    row: Mapping[str, object],
    *,
    existing_ko: str,
    eligibility: str,
    reason: str,
) -> Stage12HoldingInventoryRecord:
    return Stage12HoldingInventoryRecord(
        dvd_id=_safe_text(row, "dvd_id"),
        holding_id=_holding_id(row),
        holding_identity=_holding_identity(row),
        media_path_identity=_safe_text(row, "relative_path"),
        existing_ko=existing_ko,
        eligibility=eligibility,
        reason=reason,
    )


def _row_sort_key(row: Mapping[str, object]) -> tuple[str, str, str, str]:
    return (
        str(row.get("relative_path") or ""),
        str(row.get("dvd_id") or ""),
        str(row.get("holding_id") or ""),
        str(row.get("storage_root") or ""),
    )


def _canonical_video(
    row: Mapping[str, object],
) -> CanonicalVideoHolding:
    dvd_id = row.get("dvd_id")
    if type(dvd_id) is not str or not dvd_id:
        raise CanonicalHoldingValidationError(
            "holding dvd_id is missing"
        )

    video = validate_canonical_holding(row, dvd_id)
    source_size = row.get("size_bytes")
    source_mtime_ns = row.get("mtime_ns")
    if type(source_size) is not int or source_size <= 0:
        raise CanonicalHoldingValidationError(
            "holding source size is invalid"
        )
    if type(source_mtime_ns) is not int or source_mtime_ns < 0:
        raise CanonicalHoldingValidationError(
            "holding source mtime is invalid"
        )
    return video


def _holding_mapping(video: CanonicalVideoHolding) -> dict[str, object]:
    return {
        "dvd_id": video.dvd_id,
        "storage_root": "jav",
        "relative_path": video.relative_path,
        "parse_status": "MATCHED",
        "present": 1,
    }


def _is_korean_sibling(candidate: object) -> bool:
    return (
        isinstance(candidate, SubtitleCandidate)
        and candidate.source_kind == SOURCE_KIND_SIBLING_TEXT
        and candidate.language == "ko"
    )


def _unresolved(
    row: Mapping[str, object],
    *,
    reason: str,
    existing_ko: str = EXISTING_KO_UNRESOLVED,
) -> Stage12HoldingInventoryRecord:
    return _record(
        row,
        existing_ko=existing_ko,
        eligibility=UNRESOLVED,
        reason=reason,
    )


def _classify_subtitles(
    row: Mapping[str, object],
    video: CanonicalVideoHolding,
    subtitle_reader: object,
) -> Stage12HoldingInventoryRecord:
    list_candidates = getattr(
        subtitle_reader,
        "list_subtitle_candidates",
        None,
    )
    read_subtitle_bytes = getattr(
        subtitle_reader,
        "read_subtitle_bytes",
        None,
    )
    if not callable(list_candidates) or not callable(read_subtitle_bytes):
        raise Stage12InventoryValidationError(
            "subtitle reader does not implement the existing bounded API"
        )

    try:
        candidates = list_candidates(video)
    except (OSError, SubtitleSSHError):
        return _unresolved(
            row,
            reason="SUBTITLE_DIRECTORY_UNAVAILABLE",
        )
    except SubtitleDiscoveryError:
        return _unresolved(
            row,
            reason="SUBTITLE_INVENTORY_INVALID",
        )

    if not isinstance(candidates, tuple):
        return _unresolved(
            row,
            reason="SUBTITLE_INVENTORY_NOT_IMMUTABLE",
        )

    try:
        selection = select_subtitle_source(
            _holding_mapping(video),
            video.dvd_id,
            candidates,
        )
    except SubtitleDiscoveryError:
        return _unresolved(
            row,
            reason="SUBTITLE_SOURCE_AMBIGUOUS_OR_MALFORMED",
        )

    target_relative = derive_target_ko_relative(video)
    korean_candidates = tuple(
        candidate
        for candidate in candidates
        if _is_korean_sibling(candidate)
    )
    target_candidates = tuple(
        candidate
        for candidate in korean_candidates
        if (
            candidate.relative_path == target_relative
            and candidate.text_format == "srt"
        )
    )

    if target_candidates:
        if (
            len(target_candidates) != 1
            or selection.action != ACTION_SKIP_EXISTING_KO
            or selection.selected_source != target_candidates[0]
        ):
            return _unresolved(
                row,
                reason="CANONICAL_KO_SELECTION_INVALID",
            )

        try:
            raw = read_subtitle_bytes(
                video,
                target_candidates[0],
            )
            if type(raw) is not bytes or not raw:
                raise SubtitleTextError(
                    "existing Korean subtitle bytes are empty or invalid"
                )
            parse_subtitle_bytes(raw, "srt")
        except (
            OSError,
            SubtitleSSHError,
            SubtitleDiscoveryError,
            SubtitleTextError,
        ):
            return _unresolved(
                row,
                reason="CANONICAL_KO_SRT_UNREADABLE_OR_MALFORMED",
            )

        return _record(
            row,
            existing_ko=EXISTING_KO_VALID,
            eligibility=SKIPPED_EXISTING_KO,
            reason="VALID_CANONICAL_KO_SRT",
        )

    if korean_candidates:
        return _unresolved(
            row,
            reason="NONCANONICAL_KO_SUBTITLE_PRESENT",
        )

    return _record(
        row,
        existing_ko=EXISTING_KO_ABSENT,
        eligibility=ELIGIBLE_NEEDS_KO,
        reason="NO_CANONICAL_KO_SRT",
    )


class Stage12HoldingsInventory:
    """Read-only inventory owner using the existing Discovery contracts."""

    def __init__(
        self,
        *,
        db_path: str | Path,
        subtitle_reader: object,
        holdings_loader: Callable = load_db_state,
    ):
        if not isinstance(db_path, (str, Path)) or not str(db_path).strip():
            raise Stage12InventoryValidationError(
                "db_path must be a non-empty path"
            )
        if not callable(holdings_loader):
            raise Stage12InventoryValidationError(
                "holdings_loader must be callable"
            )
        self.db_path = Path(db_path)
        self.subtitle_reader = subtitle_reader
        self.holdings_loader = holdings_loader

    def _load_holdings(self) -> tuple[Mapping[str, object], ...]:
        try:
            state = self.holdings_loader(self.db_path)
        except Exception as error:
            raise Stage12InventoryError(
                "authoritative Discovery holdings could not be read"
            ) from error

        if not isinstance(state, Mapping) or type(state.get("holdings")) is not list:
            raise Stage12InventoryError(
                "authoritative Discovery holdings state is invalid"
            )

        rows = tuple(state["holdings"])
        if not all(isinstance(row, Mapping) for row in rows):
            raise Stage12InventoryError(
                "authoritative Discovery holdings contain a non-mapping row"
            )
        return tuple(row for row in rows if isinstance(row, Mapping))

    @staticmethod
    def _reject_duplicate_identities(
        rows: tuple[Mapping[str, object], ...],
    ) -> None:
        seen_paths: dict[str, int] = {}
        seen_dvd_ids: dict[str, int] = {}
        for row in rows:
            identity = _holding_identity(row)
            if identity is not None:
                previous = seen_paths.get(identity)
                if previous is not None:
                    raise DuplicateHoldingIdentityError(
                        "duplicate holding identity: " + identity
                    )
                seen_paths[identity] = _holding_id(row) or 0

            dvd_id = row.get("dvd_id")
            if (
                row.get("storage_root") == "jav"
                and row.get("parse_status") == "MATCHED"
                and type(row.get("present")) is int
                and row.get("present") == 1
                and isinstance(dvd_id, str)
                and dvd_id
            ):
                previous = seen_dvd_ids.get(dvd_id)
                if previous is not None:
                    raise DuplicateHoldingIdentityError(
                        "duplicate canonical DVD-ID: " + dvd_id
                    )
                seen_dvd_ids[dvd_id] = _holding_id(row) or 0

    def _inventory_row(
        self,
        row: Mapping[str, object],
    ) -> Stage12HoldingInventoryRecord:
        if row.get("storage_root") != "jav":
            return _unresolved(
                row,
                reason="NON_CANONICAL_STORAGE_ROOT",
            )
        if row.get("present") != 1:
            return _unresolved(
                row,
                reason="HOLDING_NOT_PRESENT",
            )
        if row.get("parse_status") != "MATCHED":
            return _unresolved(
                row,
                reason="HOLDING_IDENTITY_NOT_MATCHED",
            )
        if _holding_identity(row) is None:
            return _unresolved(
                row,
                reason="MISSING_HOLDING_SOURCE_IDENTITY",
            )

        try:
            video = _canonical_video(row)
        except (CanonicalHoldingValidationError, TypeError, ValueError):
            return _unresolved(
                row,
                reason="CANONICAL_HOLDING_VALIDATION_FAILED",
            )

        return _classify_subtitles(
            row,
            video,
            self.subtitle_reader,
        )

    def run(self) -> Stage12HoldingsInventoryReport:
        rows = self._load_holdings()
        self._reject_duplicate_identities(rows)
        records = tuple(
            self._inventory_row(row)
            for row in sorted(rows, key=_row_sort_key)
        )
        return Stage12HoldingsInventoryReport(records=records)


def build_subtitle_ssh_reader(
    *,
    nas_host: str,
    nas_user: str,
    nas_key: str,
    nas_known_hosts: str,
    nas_library_root: str,
) -> SubtitleSSHReader:
    """Build the existing bounded read-only NAS subtitle adapter."""

    return SubtitleSSHReader(
        host=nas_host,
        user=nas_user,
        key=nas_key,
        known_hosts=nas_known_hosts,
        library_root=nas_library_root,
    )


def _sample_payload(
    report: Stage12HoldingsInventoryReport,
    status: str,
) -> list[dict[str, object]]:
    return [
        record.to_dict()
        for record in report.records_for(status)[:10]
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a read-only Stage12 holdings subtitle inventory"
    )
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--nas-host", required=True)
    parser.add_argument("--nas-user", required=True)
    parser.add_argument("--nas-key", required=True)
    parser.add_argument("--nas-known-hosts", required=True)
    parser.add_argument("--nas-library-root", required=True)
    args = parser.parse_args(argv)

    reader = build_subtitle_ssh_reader(
        nas_host=args.nas_host,
        nas_user=args.nas_user,
        nas_key=args.nas_key,
        nas_known_hosts=args.nas_known_hosts,
        nas_library_root=args.nas_library_root,
    )
    try:
        report = Stage12HoldingsInventory(
            db_path=args.db_path,
            subtitle_reader=reader,
        ).run()
    except Stage12InventoryError as error:
        print("STAGE12_CP1_HOLDINGS_INVENTORY=FAIL")
        print("REASON=" + type(error).__name__)
        return 1

    print("STAGE12_CP1_HOLDINGS_INVENTORY=PASS")
    print("TOTAL_HOLDINGS=" + str(report.total_holdings))
    print("EXISTING_KO=" + str(report.existing_ko_count))
    print("ELIGIBLE_NEEDS_KO=" + str(report.eligible_count))
    print("UNRESOLVED=" + str(report.unresolved_count))
    for label, status in (
        ("EXISTING_KO_SAMPLE", SKIPPED_EXISTING_KO),
        ("ELIGIBLE_SAMPLE", ELIGIBLE_NEEDS_KO),
        ("UNRESOLVED_SAMPLE", UNRESOLVED),
    ):
        print(
            label
            + "="
            + json.dumps(
                _sample_payload(report, status),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    return 0


__all__ = [
    "ELIGIBLE_NEEDS_KO",
    "EXISTING_KO_ABSENT",
    "EXISTING_KO_UNRESOLVED",
    "EXISTING_KO_VALID",
    "DuplicateHoldingIdentityError",
    "SKIPPED_EXISTING_KO",
    "Stage12HoldingInventoryRecord",
    "Stage12HoldingsInventory",
    "Stage12HoldingsInventoryReport",
    "Stage12InventoryError",
    "Stage12InventoryValidationError",
    "UNRESOLVED",
    "build_subtitle_ssh_reader",
]


if __name__ == "__main__":
    raise SystemExit(main())
