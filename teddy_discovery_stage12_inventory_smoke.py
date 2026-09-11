from __future__ import annotations

from pathlib import Path

from teddy_discovery_subtitle import (
    SubtitleCandidate,
    validate_canonical_holding,
)
from teddy_discovery_stage12_inventory import (
    ELIGIBLE_NEEDS_KO,
    EXISTING_KO_VALID,
    SKIPPED_EXISTING_KO,
    UNRESOLVED,
    DuplicateHoldingIdentityError,
    Stage12HoldingsInventory,
)


def require(condition: bool, marker: str):
    if not condition:
        raise AssertionError(marker)


def expect_raises(exception_type, callback, marker: str):
    try:
        callback()
    except exception_type:
        return
    raise AssertionError(marker)


def holding(dvd_id: str, *, holding_id: int | None = None, **overrides):
    family = dvd_id.rsplit("-", 1)[0]
    row = {
        "holding_id": holding_id or 1,
        "storage_root": "jav",
        "relative_path": f"{family}/{dvd_id}/{dvd_id}.mp4",
        "dvd_id": dvd_id,
        "parse_status": "MATCHED",
        "size_bytes": 100,
        "mtime_ns": 200,
        "present": 1,
    }
    row.update(overrides)
    return row


def video(row):
    return validate_canonical_holding(row, row["dvd_id"])


class FakeSubtitleReader:
    def __init__(self, candidates=None, payloads=None):
        self.candidates = dict(candidates or {})
        self.payloads = dict(payloads or {})
        self.read_calls = []

    def list_subtitle_candidates(self, canonical_video):
        return tuple(self.candidates.get(canonical_video.dvd_id, ()))

    def read_subtitle_bytes(self, canonical_video, candidate):
        self.read_calls.append((canonical_video.dvd_id, candidate.relative_path))
        return self.payloads[(canonical_video.dvd_id, candidate.relative_path)]


def run(rows, reader):
    return Stage12HoldingsInventory(
        db_path=Path("/offline/discovery.sqlite3"),
        subtitle_reader=reader,
        holdings_loader=lambda _path: {"holdings": rows},
    ).run()


def main():
    valid_ko = (
        b"1\n00:00:00,000 --> 00:00:01,000\n"
        b"valid Korean subtitle\n"
    )

    no_ko = holding("AAA-001", holding_id=1)
    report = run([no_ko], FakeSubtitleReader())
    require(
        report.records[0].eligibility == ELIGIBLE_NEEDS_KO
        and report.records[0].existing_ko == "ABSENT"
        and report.records[0].source_size_bytes == 100
        and report.records[0].source_mtime_ns == 200
        and report.records[0].reason == "NO_CANONICAL_KO_SRT",
        "NORMAL_HOLDING_WITHOUT_KO_ELIGIBLE",
    )

    existing = holding("BBB-002", holding_id=2)
    existing_video = video(existing)
    existing_candidate = SubtitleCandidate.sibling_text(
        "BBB/BBB-002/BBB-002.ko.srt"
    )
    existing_reader = FakeSubtitleReader(
        candidates={existing_video.dvd_id: (existing_candidate,)},
        payloads={(existing_video.dvd_id, existing_candidate.relative_path): valid_ko},
    )
    report = run([existing], existing_reader)
    require(
        report.records[0].eligibility == SKIPPED_EXISTING_KO
        and report.records[0].existing_ko == EXISTING_KO_VALID
        and len(existing_reader.read_calls) == 1,
        "VALID_EXISTING_KO_SKIPPED_AFTER_PARSE",
    )

    malformed = holding("CCC-003", holding_id=3)
    malformed_video = video(malformed)
    malformed_candidate = SubtitleCandidate.sibling_text(
        "CCC/CCC-003/CCC-003.ko.srt"
    )
    malformed_reader = FakeSubtitleReader(
        candidates={malformed_video.dvd_id: (malformed_candidate,)},
        payloads={
            (malformed_video.dvd_id, malformed_candidate.relative_path):
            b"not an SRT",
        },
    )
    report = run([malformed], malformed_reader)
    require(
        report.records[0].eligibility == UNRESOLVED
        and report.records[0].reason
        == "CANONICAL_KO_SRT_UNREADABLE_OR_MALFORMED",
        "MALFORMED_KO_UNRESOLVED",
    )

    ambiguous = holding("DDD-004", holding_id=4)
    ambiguous_video = video(ambiguous)
    ambiguous_reader = FakeSubtitleReader(
        candidates={
            ambiguous_video.dvd_id: (
                SubtitleCandidate.sibling_text(
                    "DDD/DDD-004/DDD-004.ja.srt"
                ),
                SubtitleCandidate.sibling_text(
                    "DDD/DDD-004/DDD-004.ja.vtt"
                ),
            )
        }
    )
    report = run([ambiguous], ambiguous_reader)
    require(
        report.records[0].eligibility == UNRESOLVED
        and report.records[0].reason
        == "SUBTITLE_SOURCE_AMBIGUOUS_OR_MALFORMED",
        "AMBIGUOUS_SUBTITLE_UNRESOLVED",
    )

    duplicate_one = holding("EEE-005", holding_id=5)
    duplicate_two = holding("EEE-005", holding_id=6)
    expect_raises(
        DuplicateHoldingIdentityError,
        lambda: run([duplicate_one, duplicate_two], FakeSubtitleReader()),
        "DUPLICATE_HOLDING_IDENTITY_FAIL_CLOSED",
    )

    missing_identity = holding(
        "FFF-006",
        holding_id=7,
        relative_path=None,
    )
    report = run([missing_identity], FakeSubtitleReader())
    require(
        report.records[0].eligibility == UNRESOLVED
        and report.records[0].reason == "MISSING_HOLDING_SOURCE_IDENTITY",
        "MISSING_SOURCE_IDENTITY_UNRESOLVED",
    )

    unordered = [
        holding("ZZZ-010", holding_id=10),
        holding("AAA-009", holding_id=9),
    ]
    first = run(unordered, FakeSubtitleReader())
    second = run(list(reversed(unordered)), FakeSubtitleReader())
    require(
        [record.dvd_id for record in first.records]
        == ["AAA-009", "ZZZ-010"]
        and first.to_dict() == second.to_dict(),
        "DETERMINISTIC_ORDERING",
    )

    source = Path(__file__).with_name(
        "teddy_discovery_stage12_inventory.py"
    ).read_text(encoding="utf-8")
    require("os.walk" not in source, "NO_RECURSIVE_OS_WALK")
    require("rglob" not in source, "NO_RECURSIVE_RGLOB")
    require("sqlite3.connect" not in source, "NO_INVENTORY_DB_WRITER")
    require("publish_korean_srt" not in source, "NO_PUBLICATION_OWNER")
    require("SubtitlePublish" not in source, "NO_PUBLICATION_IMPORT")

    print("STAGE12_HOLDINGS_INVENTORY_SMOKE=PASS")


if __name__ == "__main__":
    main()
