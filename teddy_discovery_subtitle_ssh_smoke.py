from __future__ import annotations

import json
from types import SimpleNamespace

from teddy_discovery_subtitle import (
    CanonicalHoldingValidationError,
    CanonicalVideoHolding,
    SOURCE_KIND_VALIDATED_EXTERNAL_TEXT,
    SubtitleCandidate,
    SubtitleCandidateValidationError,
    validate_canonical_holding,
)
from teddy_discovery_subtitle_ssh import (
    MAX_SUBTITLE_DIRECTORY_ENTRIES,
    SubtitleSSHError,
    SubtitleSSHReader,
)
from teddy_discovery_subtitle_text import (
    MAX_SUBTITLE_BYTES,
    SubtitleParseError,
    parse_subtitle_bytes,
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


class FakeRunner:
    def __init__(self):
        self.calls = []
        self.responses = []

    def queue(self, *, stdout, returncode=0, stderr=""):
        self.responses.append(
            SimpleNamespace(
                returncode=returncode,
                stdout=stdout,
                stderr=stderr,
            )
        )

    def __call__(
        self,
        command,
        *,
        input,
        stdout,
        stderr,
        text,
        **kwargs,
    ):
        self.calls.append(
            {
                "command": command,
                "input": input,
                "stdout": stdout,
                "stderr": stderr,
                "text": text,
                "kwargs": kwargs,
            }
        )

        if not self.responses:
            raise AssertionError("fake runner response queue exhausted")

        return self.responses.pop(0)


def video() -> CanonicalVideoHolding:
    return validate_canonical_holding(
        {
            "dvd_id": "JUR-750",
            "storage_root": "jav",
            "relative_path": "JUR/JUR-750/JUR-750.mp4",
            "parse_status": "MATCHED",
            "present": 1,
        },
        "JUR-750",
    )


def reader(runner: FakeRunner) -> SubtitleSSHReader:
    return SubtitleSSHReader(
        host="nas.example",
        user="subtitle-reader",
        key="/keys/stage11",
        known_hosts="/keys/known_hosts",
        library_root="/srv/JAV",
        runner=runner,
    )


def inventory_json():
    return (
        "["
        '{"filename":"JUR-750.en.vtt","size":30,"mtime_ns":20},'
        '{"filename":"JUR-750.ja.srt","size":31,"mtime_ns":21},'
        '{"filename":"JUR-750.ko.srt","size":32,"mtime_ns":22}'
        "]"
    )


def assert_hardened_call(call, *, binary: bool):
    require(
        call["command"]
        == [
            "ssh",
            "-i",
            "/keys/stage11",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "UserKnownHostsFile=/keys/known_hosts",
            "subtitle-reader@nas.example",
            call["command"][-1],
        ],
        "SSH_HARDENED_ARGV",
    )
    require(
        call["command"][-1].startswith("python3 - "),
        "SSH_REMOTE_PYTHON_ARGV",
    )
    require(
        call["kwargs"].get("shell", False) is False,
        "SSH_SHELL_FALSE",
    )
    require(call["text"] is (not binary), "SSH_TEXT_MODE_CONTRACT")


def main():
    current_video = video()
    normal_inventory = inventory_json()

    runner = FakeRunner()
    runner.queue(stdout=normal_inventory)
    entries = reader(runner).list_subtitle_inventory(current_video)
    require(
        [entry.filename for entry in entries]
        == [
            "JUR-750.en.vtt",
            "JUR-750.ja.srt",
            "JUR-750.ko.srt",
        ]
        and entries[0].size == 30
        and entries[0].mtime_ns == 20,
        "INVENTORY_METADATA_SORTED",
    )
    assert_hardened_call(runner.calls[0], binary=False)
    inventory_script = runner.calls[0]["input"]
    require(
        "JUR/JUR-750" in runner.calls[0]["command"][-1]
        and "os.walk" not in inventory_script
        and "rglob" not in inventory_script
        and "glob(" not in inventory_script
        and inventory_script.count("os.scandir(") == 1
        and "entry.is_symlink()" in inventory_script
        and "follow_symlinks=False" in inventory_script
        and 'entry.name == "@eaDir"' in inventory_script,
        "INVENTORY_REMOTE_STATIC_SAFETY",
    )

    runner = FakeRunner()
    runner.queue(stdout=normal_inventory)
    candidates = reader(runner).list_subtitle_candidates(current_video)
    require(
        [candidate.relative_path for candidate in candidates]
        == [
            "JUR/JUR-750/JUR-750.en.vtt",
            "JUR/JUR-750/JUR-750.ja.srt",
            "JUR/JUR-750/JUR-750.ko.srt",
        ],
        "INVENTORY_TO_SLICE1_CANDIDATES",
    )
    require(
        ".startswith(\".\")" not in inventory_script
        or "entry.name.startswith(\".\")" in inventory_script,
        "INVENTORY_HIDDEN_ENTRIES_OMITTED",
    )

    for stdout, marker in (
        ("not json", "INVENTORY_MALFORMED_JSON_REJECTED"),
        ('{"filename":"x.srt"}', "INVENTORY_NON_LIST_REJECTED"),
        ('[{"filename":"x.srt"}]', "INVENTORY_MALFORMED_ITEM_REJECTED"),
        (
            '[{"filename":"x.srt","size":1,"mtime_ns":1},'
            '{"filename":"x.srt","size":2,"mtime_ns":2}]',
            "INVENTORY_DUPLICATE_FILENAME_REJECTED",
        ),
        (
            '[{"filename":"dir/x.srt","size":1,"mtime_ns":1}]',
            "INVENTORY_SLASH_FILENAME_REJECTED",
        ),
        (
            '[{"filename":"x\\\\y.srt","size":1,"mtime_ns":1}]',
            "INVENTORY_BACKSLASH_FILENAME_REJECTED",
        ),
        (
            '[{"filename":"x.txt","size":1,"mtime_ns":1}]',
            "INVENTORY_SUFFIX_REJECTED",
        ),
    ):
        failing_runner = FakeRunner()
        failing_runner.queue(stdout=stdout)
        expect_raises(
            SubtitleSSHError,
            lambda runner=failing_runner: reader(runner).list_subtitle_inventory(
                current_video
            ),
            marker,
        )

    failing_runner = FakeRunner()
    failing_runner.queue(stdout="[]", returncode=1, stderr="too many entries")
    expect_raises(
        SubtitleSSHError,
        lambda: reader(failing_runner).list_subtitle_inventory(current_video),
        "INVENTORY_REMOTE_BOUND_FAILURE",
    )
    require(
        MAX_SUBTITLE_DIRECTORY_ENTRIES == 256,
        "INVENTORY_256_ENTRY_BOUND",
    )

    bounded_items = [
        {
            "filename": f"JUR-750.{index:03d}.srt",
            "size": index,
            "mtime_ns": index,
        }
        for index in range(MAX_SUBTITLE_DIRECTORY_ENTRIES)
    ]
    bounded_runner = FakeRunner()
    bounded_runner.queue(stdout=json.dumps(bounded_items))
    bounded_entries = reader(bounded_runner).list_subtitle_inventory(
        current_video
    )
    require(
        len(bounded_entries) == MAX_SUBTITLE_DIRECTORY_ENTRIES,
        "INVENTORY_HOST_ACCEPTS_EXACT_BOUND",
    )

    oversized_items = bounded_items + [
        {
            "filename": "JUR-750.256.srt",
            "size": 256,
            "mtime_ns": 256,
        },
    ]
    oversized_runner = FakeRunner()
    oversized_runner.queue(stdout=json.dumps(oversized_items))
    expect_raises(
        SubtitleSSHError,
        lambda: reader(oversized_runner).list_subtitle_inventory(
            current_video
        ),
        "INVENTORY_HOST_REJECTS_OVER_BOUND",
    )

    wrong_dvd_runner = FakeRunner()
    wrong_dvd_runner.queue(
        stdout=(
            '[{"filename":"JUR-751.ja.srt",'
            '"size":1,"mtime_ns":1}]'
        )
    )
    expect_raises(
        SubtitleCandidateValidationError,
        lambda: reader(wrong_dvd_runner).list_subtitle_candidates(
            current_video
        ),
        "INVENTORY_WRONG_DVD_ID_FAIL_CLOSED",
    )

    expect_raises(
        CanonicalHoldingValidationError,
        lambda: reader(FakeRunner()).list_subtitle_candidates(
            "JUR/JUR-750"
        ),
        "INVENTORY_ARBITRARY_DIRECTORY_REJECTED",
    )

    ja_candidate = SubtitleCandidate.sibling_text(
        "JUR/JUR-750/JUR-750.ja.srt"
    )
    vtt_candidate = SubtitleCandidate.sibling_text(
        "JUR/JUR-750/JUR-750.en.vtt"
    )
    external_candidate = SubtitleCandidate.validated_external_text(
        "external://ja",
        dvd_id="JUR-750",
        language="ja",
        text_format="srt",
    )
    require(
        external_candidate.source_kind == SOURCE_KIND_VALIDATED_EXTERNAL_TEXT,
        "EXTERNAL_CANDIDATE_KIND",
    )

    raw_bytes = b"\xff\x00raw subtitle bytes"
    runner = FakeRunner()
    runner.queue(stdout=raw_bytes)
    returned = reader(runner).read_subtitle_bytes(
        current_video,
        ja_candidate,
    )
    require(
        returned == raw_bytes,
        "BINARY_READ_UNCHANGED",
    )
    assert_hardened_call(runner.calls[0], binary=True)
    read_script = runner.calls[0]["input"].decode("utf-8")
    require(
        "os.walk" not in read_script
        and "read(MAX_SUBTITLE_BYTES + 1)" in read_script
        and "os.lstat" in read_script
        and "st_mtime_ns" in read_script
        and "len(data) != before.st_size" in read_script,
        "BINARY_READ_REMOTE_STABILITY_GUARD",
    )

    for candidate, exception_type, marker in (
        (
            external_candidate,
            SubtitleCandidateValidationError,
            "BINARY_EXTERNAL_REJECTED",
        ),
        (
            SubtitleCandidate.sibling_text(
                "JUR/JUR-751/JUR-751.ja.srt"
            ),
            SubtitleCandidateValidationError,
            "BINARY_WRONG_DVD_REJECTED",
        ),
    ):
        expect_raises(
            exception_type,
            lambda candidate=candidate: reader(FakeRunner()).read_subtitle_bytes(
                current_video,
                candidate,
            ),
            marker,
        )

    for stdout, marker in (
        (b"", "BINARY_EMPTY_REJECTED"),
        (b"x" * (MAX_SUBTITLE_BYTES + 1), "BINARY_OVERSIZE_REJECTED"),
        ("text output", "BINARY_TEXT_OUTPUT_REJECTED"),
    ):
        failing_runner = FakeRunner()
        failing_runner.queue(stdout=stdout)
        expect_raises(
            SubtitleSSHError,
            lambda runner=failing_runner: reader(runner).read_subtitle_bytes(
                current_video,
                ja_candidate,
            ),
            marker,
        )

    for stderr, marker in (
        ("empty remote file", "BINARY_REMOTE_EMPTY_FAILURE"),
        ("oversize remote file", "BINARY_REMOTE_OVERSIZE_FAILURE"),
        ("unstable size or mtime", "BINARY_UNSTABLE_STAT_FAILURE"),
        ("short read", "BINARY_SHORT_READ_FAILURE"),
    ):
        failing_runner = FakeRunner()
        failing_runner.queue(
            stdout=b"ignored",
            returncode=1,
            stderr=stderr,
        )
        expect_raises(
            SubtitleSSHError,
            lambda runner=failing_runner: reader(runner).read_subtitle_bytes(
                current_video,
                ja_candidate,
            ),
            marker,
        )

    valid_srt = (
        b"1\n00:00:00,000 --> 00:00:01,000\n"
        b"ja source\n"
    )
    runner = FakeRunner()
    runner.queue(stdout=valid_srt)
    parsed_srt = parse_subtitle_bytes(
        reader(runner).read_subtitle_bytes(current_video, ja_candidate),
        "srt",
    )
    require(
        parsed_srt.cues[0].text == "ja source",
        "SLICE2_SRT_INTEGRATION",
    )

    valid_vtt = (
        "WEBVTT\n\n"
        "00:00.000 --> 00:01.000\n"
        "en source\n"
    ).encode("utf-8")
    runner = FakeRunner()
    runner.queue(stdout=valid_vtt)
    parsed_vtt = parse_subtitle_bytes(
        reader(runner).read_subtitle_bytes(current_video, vtt_candidate),
        "vtt",
    )
    require(
        parsed_vtt.cues[0].text == "en source",
        "SLICE2_VTT_INTEGRATION",
    )

    malformed = b"not an SRT document"
    runner = FakeRunner()
    runner.queue(stdout=malformed)
    malformed_bytes = reader(runner).read_subtitle_bytes(
        current_video,
        ja_candidate,
    )
    require(
        malformed_bytes == malformed,
        "SSH_ADAPTER_DOES_NOT_PRETEND_CONTENT_VALIDATION",
    )
    expect_raises(
        SubtitleParseError,
        lambda: parse_subtitle_bytes(malformed_bytes, "srt"),
        "SLICE2_REJECTS_MALFORMED_BYTES",
    )

    require(
        reader(FakeRunner()).runner is not None,
        "INJECTED_FAKE_RUNNER",
    )

    print("STAGE11_SUBTITLE_SSH_SMOKE=PASS")


if __name__ == "__main__":
    main()
