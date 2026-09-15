"""Synthetic offline smoke tests for the stateful semantic-part controller."""

from dataclasses import FrozenInstanceError, replace
import json
import os
from pathlib import Path
import stat
import tempfile
import uuid

from teddy_discovery_hermes_v2 import HermesV2CueInput, HermesV2CueOutput
from teddy_discovery_stateful_translator import (
    StatefulSubtitlePackage,
    bind_stateful_semantic_policy,
    bind_stateful_model_input_identity,
    create_stateful_staging_directory,
    parse_stateful_package,
    read_stateful_result,
    serialize_stateful_model_input,
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
    STATEFUL_VALIDATION_REASON_CUE_COUNT_MISMATCH,
    STATEFUL_VALIDATION_REASON_CUE_ORDER_MISMATCH,
    STATEFUL_VALIDATION_REASON_DUPLICATE_CUE_ID,
    STATEFUL_VALIDATION_REASON_FIRST_CUE_ID_MISMATCH,
    STATEFUL_VALIDATION_REASON_INPUT_SHA256_MISMATCH,
    STATEFUL_VALIDATION_REASON_INVALID_KO,
    STATEFUL_VALIDATION_REASON_INVALID_REPAIRED_JA,
    STATEFUL_VALIDATION_REASON_JSON_PARSE_FAILURE,
    STATEFUL_VALIDATION_REASON_LAST_CUE_ID_MISMATCH,
    STATEFUL_VALIDATION_REASON_MISSING_CUE_ID,
    STATEFUL_VALIDATION_REASON_PART_INDEX_MISMATCH,
    STATEFUL_VALIDATION_REASON_SCHEMA_FAILURE,
    STATEFUL_VALIDATION_REASON_SESSION_ID_MISMATCH,
    assemble_stateful_result,
    plan_stateful_parts,
    parse_stateful_part,
    periodic_repetition_evidence,
    promote_pending_part,
    runaway_repetition_evidence,
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
    return bind_stateful_semantic_policy(StatefulSubtitlePackage(
        schema_version=1,
        dvd_id="SYNTHETIC-TITLE",
        generation_key="synthetic-generation-001",
        claim_token=7,
        cues=tuple(cue(index) for index in range(1, count + 1)),
    ))


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


def generic_source_case(
    source_text: str,
    ko_text: str,
    *,
    stt_text: str | None = None,
):
    package = bind_stateful_model_input_identity(StatefulSubtitlePackage(
        schema_version=1,
        dvd_id="GENERIC-SOURCE-GUARD",
        generation_key="generic-source-guard-generation",
        claim_token=1,
        cues=(
            HermesV2CueInput(
                cue_id="generic-source-0001",
                external_ja=source_text,
                stt_ja=stt_text,
                en=None,
                before_context=(),
                after_context=(),
            ),
        ),
    ))
    package = bind_stateful_semantic_policy(package)
    # Hash the Hermes projection while keeping the raw package in
    # ``StatefulPartPlan.source_cues`` for CP7M source evidence.
    input_bytes = serialize_stateful_model_input(package)
    plan = plan_stateful_parts(package, input_bytes)
    baseline = make_part(plan, 1)
    payload = mutated_part_payload(
        baseline,
        lambda data: data["cues"][0].__setitem__("ko", ko_text),
    )
    return package, plan, payload


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
        plan.part_count == 3
        and plan.parts[0].cue_ids == tuple(
            f"asr-{index:04d}" for index in range(1, 65)
        )
        and plan.parts[1].first_cue_id == "asr-0065"
        and plan.parts[1].last_cue_id == "asr-0128"
        and plan.parts[2].cue_count == 38
        and plan.parts[2].first_cue_id == "asr-0129"
        and plan.parts[2].last_cue_id == "asr-0166"
        and all(
            part.cue_count <= STATEFUL_PART_BATCH_SIZE
            for part in plan.parts
        ),
        "PLAN_166_CUES_3_FIXED64_RANGES_WITH_SHORT_FINAL_PART",
    )
    check(
        stateful_part_filename(1, pending=True)
        == "semantic-part-0001.pending.json"
        and stateful_part_filename(3, pending=False)
        == "semantic-part-0003.json",
        "EXACT_PART_FILENAME_CONTRACT",
    )
    expect(
        FrozenInstanceError,
        lambda: setattr(plan.parts[0], "part_index", 2),
        "EXPECTED_PART_METADATA_IMMUTABLE",
    )

    def reject_source_aware_runaway(
        candidate_plan: StatefulPartPlan,
        payload: bytes,
        marker: str,
    ):
        try:
            parse_stateful_part(
                payload,
                candidate_plan.parts[0],
                candidate_plan,
            )
        except StatefulPartsValidationError as error:
            check(
                error.reason_code == STATEFUL_VALIDATION_REASON_INVALID_KO,
                marker,
            )
            return
        counts["fail"] += 1
        raise AssertionError(marker)

    source_evidence = periodic_repetition_evidence("かな" * 74 + "か")
    ko_evidence = runaway_repetition_evidence("번역" * 40)
    check(
        source_evidence is not None
        and source_evidence.normalized_length == 149
        and source_evidence.unit_length == 2
        and source_evidence.complete_repetitions == 74
        and source_evidence.trailing_prefix_length == 1
        and ko_evidence is not None
        and ko_evidence.complete_repetitions == 40
        and ko_evidence.trailing_prefix_length == 0,
        "GENERIC_PERIODIC_EVIDENCE_COUNTS",
    )
    check(
        periodic_repetition_evidence("かな" * 13) is None,
        "SOURCE_13_REPEATS_HAVE_NO_EXCEPTION_EVIDENCE",
    )

    _, source_13_plan, source_13_payload = generic_source_case(
        "かな" * 13,
        "번역" * 72,
    )
    reject_source_aware_runaway(
        source_13_plan,
        source_13_payload,
        "CASE_A_SOURCE_13_KO_72_REJECTED",
    )

    _, source_74_plan, source_74_payload = generic_source_case(
        "かな" * 74 + "か",
        "번역" * 40,
    )
    accepted = parse_stateful_part(
        source_74_payload,
        source_74_plan.parts[0],
        source_74_plan,
    )
    check(
        accepted.cues[0].ko == "번역" * 40
        and serialize_stateful_part(accepted) == source_74_payload,
        "CASE_B_SOURCE_74_PLUS_PREFIX_KO_40_ACCEPTED",
    )

    _, nonperiodic_plan, nonperiodic_payload = generic_source_case(
        "これは通常の日本語の文章です",
        "번역" * 40,
    )
    reject_source_aware_runaway(
        nonperiodic_plan,
        nonperiodic_payload,
        "NONPERIODIC_SOURCE_KO_RUNAWAY_REJECTED",
    )

    _, larger_ko_plan, larger_ko_payload = generic_source_case(
        "かな" * 74 + "か",
        "번역" * 75,
    )
    reject_source_aware_runaway(
        larger_ko_plan,
        larger_ko_payload,
        "PERIODIC_SOURCE_KO_LARGER_REJECTED",
    )

    _, equal_ko_plan, equal_ko_payload = generic_source_case(
        "かな" * 74 + "か",
        "번역" * 74,
    )
    check(
        parse_stateful_part(
            equal_ko_payload,
            equal_ko_plan.parts[0],
            equal_ko_plan,
        ).cues[0].ko == "번역" * 74,
        "PERIODIC_SOURCE_KO_EQUAL_ACCEPTED",
    )

    _, smaller_ko_plan, smaller_ko_payload = generic_source_case(
        "かな" * 74 + "か",
        "번역" * 72,
    )
    check(
        parse_stateful_part(
            smaller_ko_payload,
            smaller_ko_plan.parts[0],
            smaller_ko_plan,
        ).cues[0].ko == "번역" * 72,
        "PERIODIC_SOURCE_KO_SMALLER_ACCEPTED",
    )

    source_absent_plan = replace(source_74_plan, source_cues=())
    reject_source_aware_runaway(
        source_absent_plan,
        source_74_payload,
        "SOURCE_ABSENT_FAILS_CLOSED",
    )
    expect(
        StatefulPartsValidationError,
        lambda: replace(source_74_plan, source_cues=(object(),)),
        "MALFORMED_SOURCE_FAILS_CLOSED",
    )

    _, precedence_plan, precedence_payload = generic_source_case(
        "これは通常の日本語の文章です",
        "번역" * 40,
        stt_text="かな" * 74 + "か",
    )
    reject_source_aware_runaway(
        precedence_plan,
        precedence_payload,
        "EXTERNAL_JA_PRECEDENCE_REUSED",
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
            "VALID_64_CUE_PENDING_VALIDATES",
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

        def validation_case(
            payload: bytes,
            marker: str,
            *,
            mode: int = 0o600,
            reason_code: str | None = None,
        ):
            case_task = new_task()
            case_path = case_task / first_expected.pending_filename
            write_private(case_path, payload, mode=mode)
            try:
                validate_pending_part(case_path, plan)
            except StatefulPartsValidationError as error:
                if reason_code is not None:
                    check(
                        error.reason_code == reason_code,
                        marker + "_EXACT_REASON",
                    )
                else:
                    counts["pass"] += 1
                return
            counts["fail"] += 1
            raise AssertionError(marker)

        validation_case(
            mutated_part_payload(
                first_part,
                lambda data: data.__setitem__(
                    "session_id",
                    "00000000-0000-0000-0000-000000000000",
                ),
            ),
            "WRONG_SESSION_REJECTED",
            reason_code=STATEFUL_VALIDATION_REASON_SESSION_ID_MISMATCH,
        )
        validation_case(
            mutated_part_payload(
                first_part,
                lambda data: data.__setitem__("input_sha256", "0" * 64),
            ),
            "WRONG_INPUT_HASH_REJECTED",
            reason_code=STATEFUL_VALIDATION_REASON_INPUT_SHA256_MISMATCH,
        )
        validation_case(
            mutated_part_payload(
                first_part,
                lambda data: data.__setitem__("part_index", 2),
            ),
            "WRONG_PART_INDEX_REJECTED",
            reason_code=STATEFUL_VALIDATION_REASON_PART_INDEX_MISMATCH,
        )
        validation_case(
            mutated_part_payload(
                first_part,
                lambda data: data.__setitem__("first_cue_id", "asr-0002"),
            ),
            "WRONG_FIRST_CUE_REJECTED",
            reason_code=STATEFUL_VALIDATION_REASON_FIRST_CUE_ID_MISMATCH,
        )
        validation_case(
            mutated_part_payload(
                first_part,
                lambda data: data.__setitem__("last_cue_id", "asr-0015"),
            ),
            "WRONG_LAST_CUE_REJECTED",
            reason_code=STATEFUL_VALIDATION_REASON_LAST_CUE_ID_MISMATCH,
        )
        validation_case(
            mutated_part_payload(
                first_part,
                lambda data: data["cues"].pop(),
            ),
            "MISSING_CUE_REJECTED",
            reason_code=STATEFUL_VALIDATION_REASON_CUE_COUNT_MISMATCH,
        )
        validation_case(
            mutated_part_payload(
                first_part,
                lambda data: data["cues"][1].__setitem__(
                    "cue_id",
                    "asr-9999",
                ),
            ),
            "MISSING_CUE_ID_REJECTED",
            reason_code=STATEFUL_VALIDATION_REASON_MISSING_CUE_ID,
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
            reason_code=STATEFUL_VALIDATION_REASON_DUPLICATE_CUE_ID,
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
            reason_code=STATEFUL_VALIDATION_REASON_FIRST_CUE_ID_MISMATCH,
        )
        validation_case(
            mutated_part_payload(
                first_part,
                lambda data: data["cues"].__setitem__(
                    slice(1, 3),
                    [data["cues"][2], data["cues"][1]],
                ),
            ),
            "CUE_ORDER_REJECTED",
            reason_code=STATEFUL_VALIDATION_REASON_CUE_ORDER_MISMATCH,
        )
        validation_case(
            mutated_part_payload(
                first_part,
                lambda data: data.__setitem__("extra", "not allowed"),
            ),
            "EXTRA_TOP_LEVEL_FIELD_REJECTED",
            reason_code=STATEFUL_VALIDATION_REASON_SCHEMA_FAILURE,
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
            reason_code=STATEFUL_VALIDATION_REASON_SCHEMA_FAILURE,
        )
        validation_case(
            mutated_part_payload(
                first_part,
                lambda data: data["cues"][0].__setitem__("ko", ""),
            ),
            "EMPTY_KO_REJECTED",
            reason_code=STATEFUL_VALIDATION_REASON_INVALID_KO,
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
            reason_code=STATEFUL_VALIDATION_REASON_INVALID_REPAIRED_JA,
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
            reason_code=STATEFUL_VALIDATION_REASON_INVALID_REPAIRED_JA,
        )
        validation_case(
            b"not json",
            "MALFORMED_JSON_REJECTED",
            reason_code=STATEFUL_VALIDATION_REASON_JSON_PARSE_FAILURE,
        )
        duplicate_json = (
            b'{"part_schema_version":1,"part_schema_version":1}'
        )
        validation_case(
            duplicate_json,
            "DUPLICATE_JSON_KEY_REJECTED",
            reason_code=STATEFUL_VALIDATION_REASON_JSON_PARSE_FAILURE,
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
