"""Synthetic offline smoke tests for the stateful semantic-part controller."""

from dataclasses import FrozenInstanceError
import json
import os
from pathlib import Path
import stat
import tempfile
import uuid

from teddy_discovery_hermes_v2 import HermesV2CueInput, HermesV2CueOutput
from teddy_discovery_stateful_translator import (
    StatefulSubtitlePackage,
    create_stateful_staging_directory,
    parse_stateful_package,
    read_stateful_result,
    serialize_stateful_package,
    stateful_staging_paths,
    validate_stateful_result,
)
from teddy_discovery_stateful_parts import (
    ExpectedStatefulPart,
    STATEFUL_PART_BATCH_SIZE,
    STATEFUL_PART_FILE_MODE,
    StatefulPartPlan,
    StatefulPartsAssemblyError,
    StatefulPartsFilenameError,
    StatefulPartsPromotionError,
    StatefulPartsValidationError,
    StatefulSemanticPart,
    assemble_stateful_result,
    plan_stateful_parts,
    promote_pending_part,
    scan_stateful_canonical_parts,
    serialize_stateful_part,
    stateful_part_filename,
    validate_pending_part,
)


def cue(index: int) -> HermesV2CueInput:
    return HermesV2CueInput(
        cue_id=f"asr-{index:04d}",
        external_ja=f"synthetic-ja-{index:04d}",
        stt_ja=None,
        en=None,
        before_context=(),
        after_context=(),
    )


def make_package(count: int = 166) -> StatefulSubtitlePackage:
    return StatefulSubtitlePackage(
        schema_version=1,
        dvd_id="SYNTHETIC-TITLE",
        generation_key="synthetic-generation-001",
        claim_token=7,
        cues=tuple(cue(index) for index in range(1, count + 1)),
    )


def make_part(plan: StatefulPartPlan, part_index: int) -> StatefulSemanticPart:
    expected = plan.parts[part_index - 1]
    return StatefulSemanticPart(
        part_schema_version=1,
        session_id=plan.session_id,
        input_sha256=plan.input_sha256,
        part_index=expected.part_index,
        first_cue_id=expected.first_cue_id,
        last_cue_id=expected.last_cue_id,
        cues=tuple(
            HermesV2CueOutput(
                cue_id=cue_id,
                repaired_ja=None,
                ko=f"synthetic-ko-{cue_id}",
            )
            for cue_id in expected.cue_ids
        ),
    )


def part_wire(part: StatefulSemanticPart) -> dict[str, object]:
    return json.loads(serialize_stateful_part(part).decode("utf-8"))


def mutated_part_payload(
    part: StatefulSemanticPart,
    mutate,
) -> bytes:
    data = part_wire(part)
    mutate(data)
    return json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def write_private(path: Path, payload: bytes, mode: int = STATEFUL_PART_FILE_MODE):
    file_descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        mode,
    )
    try:
        os.fchmod(file_descriptor, mode)
        os.write(file_descriptor, payload)
        os.fsync(file_descriptor)
    finally:
        os.close(file_descriptor)


def main():
    counts = {"pass": 0, "fail": 0, "next_task": 0}

    def check(condition: bool, marker: str):
        if not condition:
            counts["fail"] += 1
            raise AssertionError(marker)
        counts["pass"] += 1

    def expect(exception_type, callback, marker: str):
        try:
            callback()
        except exception_type:
            counts["pass"] += 1
            return
        except Exception as error:
            counts["fail"] += 1
            raise AssertionError(
                marker + ": wrong exception " + type(error).__name__
            ) from error
        counts["fail"] += 1
        raise AssertionError(marker)

    package = make_package()
    input_bytes = serialize_stateful_package(package)
    parsed_package = parse_stateful_package(input_bytes)
    plan = plan_stateful_parts(parsed_package, input_bytes)
    check(
        plan.part_count == 11
        and plan.parts[0].cue_ids == tuple(
            f"asr-{index:04d}" for index in range(1, 17)
        )
        and plan.parts[9].first_cue_id == "asr-0145"
        and plan.parts[9].last_cue_id == "asr-0160"
        and plan.parts[10].cue_count == 6
        and plan.parts[10].first_cue_id == "asr-0161"
        and plan.parts[10].last_cue_id == "asr-0166"
        and all(
            part.cue_count <= STATEFUL_PART_BATCH_SIZE
            for part in plan.parts
        ),
        "PLAN_166_CUES_11_RANGES_WITH_SHORT_FINAL_PART",
    )
    check(
        stateful_part_filename(1, pending=True)
        == "semantic-part-0001.pending.json"
        and stateful_part_filename(11, pending=False)
        == "semantic-part-0011.json",
        "EXACT_PART_FILENAME_CONTRACT",
    )
    expect(
        FrozenInstanceError,
        lambda: setattr(plan.parts[0], "part_index", 2),
        "EXPECTED_PART_METADATA_IMMUTABLE",
    )

    with tempfile.TemporaryDirectory(prefix="stage11-parts-smoke-") as root:
        task_counter = {"value": 0}

        def new_task() -> Path:
            task_counter["value"] += 1
            session_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    "stage11-parts-smoke-" + str(task_counter["value"]),
                )
            )
            return create_stateful_staging_directory(root, session_id)

        task = new_task()
        first_expected = plan.parts[0]
        first_part = make_part(plan, 1)
        pending_path = task / first_expected.pending_filename
        write_private(pending_path, serialize_stateful_part(first_part))
        validated_pending = validate_pending_part(pending_path, plan)
        check(
            validated_pending == first_part
            and stat.S_IMODE(os.stat(pending_path).st_mode) == 0o600,
            "VALID_16_CUE_PENDING_VALIDATES",
        )
        promoted = promote_pending_part(task, plan, 1)
        canonical_path = task / first_expected.canonical_filename
        check(
            promoted == first_part
            and canonical_path.exists()
            and not pending_path.exists()
            and stat.S_IMODE(os.stat(canonical_path).st_mode)
            == STATEFUL_PART_FILE_MODE,
            "VALID_PENDING_PROMOTES_TO_PRIVATE_CANONICAL",
        )
        write_private(pending_path, serialize_stateful_part(first_part))
        original_canonical = canonical_path.read_bytes()
        expect(
            StatefulPartsPromotionError,
            lambda: promote_pending_part(task, plan, 1),
            "CANONICAL_CANNOT_BE_OVERWRITTEN",
        )
        check(
            canonical_path.read_bytes() == original_canonical,
            "CANONICAL_BYTES_REMAIN_UNCHANGED",
        )

        pending_path.unlink()

        def validation_case(payload: bytes, marker: str, *, mode: int = 0o600):
            case_task = new_task()
            case_path = case_task / first_expected.pending_filename
            write_private(case_path, payload, mode=mode)
            expect(
                StatefulPartsValidationError,
                lambda: validate_pending_part(case_path, plan),
                marker,
            )

        validation_case(
            mutated_part_payload(
                first_part,
                lambda data: data.__setitem__("session_id", "0" * 36),
            ),
            "WRONG_SESSION_REJECTED",
        )
        validation_case(
            mutated_part_payload(
                first_part,
                lambda data: data.__setitem__("input_sha256", "0" * 64),
            ),
            "WRONG_INPUT_HASH_REJECTED",
        )
        validation_case(
            mutated_part_payload(
                first_part,
                lambda data: data.__setitem__("part_index", 2),
            ),
            "WRONG_PART_INDEX_REJECTED",
        )
        validation_case(
            mutated_part_payload(
                first_part,
                lambda data: data.__setitem__("first_cue_id", "asr-0002"),
            ),
            "WRONG_FIRST_CUE_REJECTED",
        )
        validation_case(
            mutated_part_payload(
                first_part,
                lambda data: data.__setitem__("last_cue_id", "asr-0015"),
            ),
            "WRONG_LAST_CUE_REJECTED",
        )
        validation_case(
            mutated_part_payload(
                first_part,
                lambda data: data["cues"].pop(),
            ),
            "MISSING_CUE_REJECTED",
        )
        validation_case(
            mutated_part_payload(
                first_part,
                lambda data: data["cues"].__setitem__(
                    1,
                    dict(data["cues"][0]),
                ),
            ),
            "DUPLICATE_CUE_REJECTED",
        )
        validation_case(
            mutated_part_payload(
                first_part,
                lambda data: data["cues"].__setitem__(
                    0,
                    data["cues"][1],
                ),
            ),
            "WRONG_CUE_ORDER_REJECTED",
        )
        validation_case(
            mutated_part_payload(
                first_part,
                lambda data: data.__setitem__("extra", "not allowed"),
            ),
            "EXTRA_TOP_LEVEL_FIELD_REJECTED",
        )
        validation_case(
            mutated_part_payload(
                first_part,
                lambda data: data["cues"][0].__setitem__(
                    "extra",
                    "not allowed",
                ),
            ),
            "EXTRA_CUE_FIELD_REJECTED",
        )
        validation_case(
            mutated_part_payload(
                first_part,
                lambda data: data["cues"][0].__setitem__("ko", ""),
            ),
            "EMPTY_KO_REJECTED",
        )
        validation_case(
            mutated_part_payload(
                first_part,
                lambda data: data["cues"][0].__setitem__(
                    "repaired_ja",
                    123,
                ),
            ),
            "INVALID_REPAIRED_JA_REJECTED",
        )
        validation_case(
            mutated_part_payload(
                first_part,
                lambda data: data["cues"][0].__setitem__(
                    "repaired_ja",
                    "아오이さん、急にどうしたの?",
                ),
            ),
            "KOREAN_SCRIPT_IN_REPAIRED_JA_REJECTED",
        )
        validation_case(
            b"not json",
            "MALFORMED_JSON_REJECTED",
        )
        duplicate_json = (
            b'{"part_schema_version":1,"part_schema_version":1}'
        )
        validation_case(
            duplicate_json,
            "DUPLICATE_JSON_KEY_REJECTED",
        )
        validation_case(
            serialize_stateful_part(first_part),
            "BAD_PRIVATE_FILE_MODE_REJECTED",
            mode=0o644,
        )

        symlink_task = new_task()
        symlink_path = symlink_task / first_expected.pending_filename
        target_path = symlink_task.parent / "synthetic-target.json"
        write_private(target_path, serialize_stateful_part(first_part))
        os.symlink(target_path, symlink_path)
        expect(
            StatefulPartsValidationError,
            lambda: validate_pending_part(symlink_path, plan),
            "SYMLINK_PENDING_REJECTED",
        )

        resume_task = new_task()
        resume_canonical = resume_task / first_expected.canonical_filename
        write_private(resume_canonical, serialize_stateful_part(first_part))
        second_expected = plan.parts[1]
        second_pending = resume_task / second_expected.pending_filename
        write_private(second_pending, serialize_stateful_part(make_part(plan, 2)))
        resume_scan = scan_stateful_canonical_parts(resume_task, plan)
        check(
            not resume_scan.complete
            and resume_scan.first_missing_part == second_expected
            and len(resume_scan.canonical_parts) == 1
            and len(resume_scan.pending_parts) == 1,
            "RESUME_RETURNS_FIRST_MISSING_CANONICAL_PART",
        )
        check(
            scan_stateful_canonical_parts(resume_task, plan).first_missing_part
            is second_expected,
            "PENDING_IS_NOT_COMPLETION",
        )

        out_of_range_task = new_task()
        out_of_range_path = out_of_range_task / "semantic-part-0012.json"
        write_private(out_of_range_path, b"{}")
        expect(
            StatefulPartsFilenameError,
            lambda: scan_stateful_canonical_parts(out_of_range_task, plan),
            "OUT_OF_RANGE_FILENAME_REJECTED",
        )

        conflict_task = new_task()
        conflict_canonical = conflict_task / first_expected.canonical_filename
        conflict_pending = conflict_task / first_expected.pending_filename
        write_private(conflict_canonical, serialize_stateful_part(first_part))
        write_private(conflict_pending, serialize_stateful_part(first_part))
        expect(
            StatefulPartsFilenameError,
            lambda: scan_stateful_canonical_parts(conflict_task, plan),
            "PENDING_CANONICAL_CONFLICT_REJECTED",
        )

        complete_task = new_task()
        for expected in plan.parts:
            write_private(
                complete_task / expected.canonical_filename,
                serialize_stateful_part(make_part(plan, expected.part_index)),
            )
        complete_scan = scan_stateful_canonical_parts(complete_task, plan)
        check(
            complete_scan.complete
            and complete_scan.first_missing_part is None
            and len(complete_scan.canonical_parts) == plan.part_count,
            "ALL_CANONICAL_PARTS_SCAN_COMPLETE",
        )
        assembled = assemble_stateful_result(
            complete_task,
            package,
            plan,
        )
        final_paths = stateful_staging_paths(complete_task)
        final_from_disk = read_stateful_result(
            complete_task,
            package,
            process_finished=True,
        )
        check(
            validate_stateful_result(assembled, package) == assembled
            and final_from_disk == assembled
            and tuple(cue.cue_id for cue in assembled.cues)
            == tuple(cue.cue_id for cue in package.cues)
            and stat.S_IMODE(os.stat(final_paths.result_path).st_mode) == 0o600,
            "FINAL_ASSEMBLY_PASSES_EXISTING_RESULT_VALIDATION",
        )
        final_bytes = final_paths.result_path.read_bytes()
        expect(
            StatefulPartsAssemblyError,
            lambda: assemble_stateful_result(complete_task, package, plan),
            "FINAL_RESULT_CANNOT_BE_OVERWRITTEN",
        )
        check(
            final_paths.result_path.read_bytes() == final_bytes,
            "FINAL_RESULT_BYTES_REMAIN_UNCHANGED",
        )

    print("STATEFUL_PARTS_SMOKE_PASS")
    print("SYNTHETIC_TEST_PASS_COUNT=" + str(counts["pass"]))
    print("SYNTHETIC_TEST_FAIL_COUNT=" + str(counts["fail"]))


if __name__ == "__main__":
    main()
