"""Offline smoke tests for the generic ASR-only/stateful bridge."""

from dataclasses import replace

import teddy_discovery_subtitle_v2_pipeline_smoke as pipeline_fixture
import teddy_discovery_stateful_asr as asr_module
import teddy_discovery_stateful_prepare as prepare_module
from teddy_discovery_asr import ASRSegment
from teddy_discovery_asr_source_quality import (
    ASR_SOURCE_OMIT,
    ASR_SOURCE_REQUIRE_SECOND_EVIDENCE,
    classify_asr_result_source_quality,
)
from teddy_discovery_hermes_v2 import HermesV2CueInput
from teddy_discovery_stateful_asr import (
    StatefulASRValidationError,
    build_stateful_asr_package,
    prepare_stateful_asr_package,
)
from teddy_discovery_stateful_controller import build_stateful_part_query
from teddy_discovery_stateful_parts import (
    STATEFUL_PART_BATCH_SIZE,
    build_stateful_part_plan,
)
from teddy_discovery_stateful_translator import (
    StatefulSubtitlePackage,
    parse_stateful_package,
    serialize_stateful_package,
)
from teddy_discovery_subtitle_v2_pipeline import build_asr_only_cue_sequence


def asr_cues(count: int) -> tuple[HermesV2CueInput, ...]:
    return tuple(
        HermesV2CueInput(
            cue_id=f"asr-{index:06d}",
            external_ja=None,
            stt_ja=f"音声 {index}",
            en=None,
            before_context=(),
            after_context=(),
        )
        for index in range(1, count + 1)
    )


def asr_package(count: int) -> StatefulSubtitlePackage:
    return build_stateful_asr_package(
        asr_cues(count),
        dvd_id="TEST-001",
        generation_key=f"asr-generation-{count}",
        claim_token=7,
    )


def asr_cues_from_texts(
    texts: tuple[str, ...],
) -> tuple[HermesV2CueInput, ...]:
    return tuple(
        HermesV2CueInput(
            cue_id=f"asr-{index:06d}",
            external_ja=None,
            stt_ja=text,
            en=None,
            before_context=(),
            after_context=(),
        )
        for index, text in enumerate(texts, start=1)
    )


def filtered_package(
    texts: tuple[str, ...],
    *,
    generation_key: str,
):
    source = build_stateful_asr_package(
        asr_cues_from_texts(texts),
        dvd_id="TEST-001",
        generation_key="source-" + generation_key,
        claim_token=7,
    )
    return prepare_stateful_asr_package(
        source,
        generation_key=generation_key,
    )


def matching_asr_result(texts: tuple[str, ...]):
    base = pipeline_fixture.asr_result("TEST-001")
    return replace(
        base,
        segments=tuple(
            ASRSegment(index * 1000, index * 1000 + 700, text)
            for index, text in enumerate(texts, start=1)
        ),
    )


def hybrid_package() -> StatefulSubtitlePackage:
    return StatefulSubtitlePackage(
        schema_version=1,
        dvd_id="TEST-001",
        generation_key="hybrid-generation",
        claim_token=7,
        cues=(
            HermesV2CueInput(
                cue_id="ja-000001",
                external_ja="外部 evidence",
                stt_ja=None,
                en=None,
                before_context=(),
                after_context=(),
            ),
        ),
    )


def mixed_package() -> StatefulSubtitlePackage:
    return StatefulSubtitlePackage(
        schema_version=1,
        dvd_id="TEST-001",
        generation_key="mixed-generation",
        claim_token=7,
        cues=(
            HermesV2CueInput(
                cue_id="ja-000001",
                external_ja="外部 evidence",
                stt_ja=None,
                en=None,
                before_context=(),
                after_context=(),
            ),
            HermesV2CueInput(
                cue_id="asr-000002",
                external_ja=None,
                stt_ja="音声 evidence",
                en=None,
                before_context=(),
                after_context=(),
            ),
        ),
    )


def reject(callback, label: str):
    try:
        callback()
    except StatefulASRValidationError:
        return
    raise AssertionError(label)


def main():
    passed = 0

    def check(condition: bool, label: str):
        nonlocal passed
        if not condition:
            raise AssertionError(label)
        passed += 1
        print("PASS=" + label)

    for count in (1, 16, 17, 512, 921, 4096):
        package = asr_package(count)
        check(
            len(package.cues) == count
            and all(cue.external_ja is None for cue in package.cues)
            and tuple(cue.cue_id for cue in package.cues)
            == tuple(f"asr-{index:06d}" for index in range(1, count + 1))
            and tuple(cue.stt_ja for cue in package.cues)
            == tuple(f"音声 {index}" for index in range(1, count + 1)),
            f"ASR_PACKAGE_{count}",
        )
        wire = serialize_stateful_package(package)
        check(
            parse_stateful_package(wire) == package,
            f"ASR_PACKAGE_{count}_SERIALIZATION",
        )
        plan = build_stateful_part_plan(package, wire)
        expected_part_count = (
            count + STATEFUL_PART_BATCH_SIZE - 1
        ) // STATEFUL_PART_BATCH_SIZE
        check(
            plan.part_count == expected_part_count
            and plan.parts[0].first_cue_id == "asr-000001"
            and plan.parts[-1].last_cue_id == f"asr-{count:06d}"
            and tuple(cue_id for part in plan.parts for cue_id in part.cue_ids)
            == tuple(cue.cue_id for cue in package.cues),
            f"ASR_PART_PLAN_{count}",
        )

    package_921 = asr_package(921)
    plan_921 = build_stateful_part_plan(
        package_921,
        serialize_stateful_package(package_921),
    )
    check(
        plan_921.part_count == 58
        and tuple(len(part.cue_ids) for part in plan_921.parts[:-1])
        == (16,) * 57
        and len(plan_921.parts[-1].cue_ids) == 9,
        "ADN_921_PART_DISTRIBUTION",
    )

    generic_texts = ("普通一", "はい", "はい", "一旦、一旦、一旦、一旦", "普通五")
    generic_asr = matching_asr_result(generic_texts)
    generic_source = build_stateful_asr_package(
        asr_cues_from_texts(generic_texts),
        dvd_id="TEST-001",
        generation_key="generic-source",
        claim_token=7,
    )
    generic_decisions = classify_asr_result_source_quality(generic_asr)
    generic_prepared = prepare_stateful_asr_package(
        generic_source,
        generation_key="generic-filtered",
        asr_result=generic_asr,
    )
    check(
        tuple(decision.action for _, decision in generic_prepared.source_quality_decisions)
        == tuple(decision.action for decision in generic_decisions)
        and any(
            decision.action == ASR_SOURCE_REQUIRE_SECOND_EVIDENCE
            for decision in generic_decisions
        )
        and all(
            decision.action != ASR_SOURCE_OMIT
            for cue in generic_prepared.package.cues
            for decision in (generic_decisions[int(cue.cue_id[4:]) - 1],)
        )
        and generic_prepared.package.cues[1].stt_ja == generic_texts[1]
        and generic_prepared.package.cues[2].stt_ja == generic_texts[2],
        "GENERIC_SOURCE_QUALITY_BOUNDARY",
    )

    filter_cases = (
        (
            "FILTER_ALL_KEEP",
            ("普通一", "普通二"),
            ("asr-000001", "asr-000002"),
            (),
        ),
        (
            "FILTER_ONE_MIDDLE",
            ("普通一", "ああああ", "普通三"),
            ("asr-000001", "asr-000003"),
            ("asr-000002",),
        ),
        (
            "FILTER_MULTIPLE",
            ("ああああ", "普通二", "ああああ", "普通四"),
            ("asr-000002", "asr-000004"),
            ("asr-000001", "asr-000003"),
        ),
        (
            "FILTER_FIRST_OMIT",
            ("ああああ", "普通二"),
            ("asr-000002",),
            ("asr-000001",),
        ),
        (
            "FILTER_LAST_OMIT",
            ("普通一", "ああああ"),
            ("asr-000001",),
            ("asr-000002",),
        ),
        (
            "FILTER_ADJACENT_OMIT",
            ("普通一", "ああああ", "ああああ", "普通四"),
            ("asr-000001", "asr-000004"),
            ("asr-000002", "asr-000003"),
        ),
    )
    for label, texts, expected_kept, expected_omitted in filter_cases:
        prepared = filtered_package(
            texts,
            generation_key=label.lower(),
        )
        check(
            tuple(cue.cue_id for cue in prepared.package.cues)
            == expected_kept
            and prepared.omitted_cue_ids == expected_omitted
            and tuple(
                cue.stt_ja
                for cue in prepared.package.cues
            ) == tuple(
                texts[int(cue_id[4:]) - 1]
                for cue_id in expected_kept
            )
            and all(cue.external_ja is None for cue in prepared.package.cues),
            label,
        )

    max_filtered = filtered_package(
        ("보존 cue",) * 4096,
        generation_key="filtered-4096",
    )
    check(
        len(max_filtered.package.cues) == 4096
        and max_filtered.omitted_cue_ids == ()
        and max_filtered.package.cues[0].cue_id == "asr-000001"
        and max_filtered.package.cues[-1].cue_id == "asr-004096",
        "FILTERED_PACKAGE_4096_BOUNDARY",
    )

    sparse_source = StatefulSubtitlePackage(
        schema_version=1,
        dvd_id="TEST-001",
        generation_key="sparse-source",
        claim_token=7,
        cues=asr_cues_from_texts(("첫 cue", "둘 cue")),
    )
    sparse_source = StatefulSubtitlePackage(
        schema_version=sparse_source.schema_version,
        dvd_id=sparse_source.dvd_id,
        generation_key=sparse_source.generation_key,
        claim_token=sparse_source.claim_token,
        cues=(
            replace(sparse_source.cues[0], cue_id="asr-000001"),
            replace(sparse_source.cues[1], cue_id="asr-000003"),
        ),
    )
    sparse_prepared = prepare_stateful_asr_package(
        sparse_source,
        generation_key="sparse-filtered",
    )
    sparse_wire = serialize_stateful_package(sparse_prepared.package)
    sparse_plan = build_stateful_part_plan(
        sparse_prepared.package,
        sparse_wire,
    )
    check(
        tuple(cue.cue_id for cue in sparse_prepared.package.cues)
        == ("asr-000001", "asr-000003")
        and tuple(
            cue_id
            for part in sparse_plan.parts
            for cue_id in part.cue_ids
        ) == ("asr-000001", "asr-000003"),
        "SPARSE_IDS_AND_PART_ORDER_PRESERVED",
    )

    reversed_sparse = StatefulSubtitlePackage(
        schema_version=1,
        dvd_id="TEST-001",
        generation_key="reversed-source",
        claim_token=7,
        cues=(
            asr_cues(3)[2],
            asr_cues(3)[0],
        ),
    )
    reject(
        lambda: prepare_stateful_asr_package(
            reversed_sparse,
            generation_key="reversed-filtered",
        ),
        "SPARSE_REVERSE_ORDER_REJECTED",
    )

    noncanonical_sparse = StatefulSubtitlePackage(
        schema_version=1,
        dvd_id="TEST-001",
        generation_key="noncanonical-source",
        claim_token=7,
        cues=(
            replace(asr_cues(1)[0], cue_id="asr-0001"),
        ),
    )
    reject(
        lambda: prepare_stateful_asr_package(
            noncanonical_sparse,
            generation_key="noncanonical-filtered",
        ),
        "NONCANONICAL_ASR_ID_REJECTED",
    )

    injected_external = StatefulSubtitlePackage(
        schema_version=1,
        dvd_id="TEST-001",
        generation_key="external-source",
        claim_token=7,
        cues=(
            replace(
                asr_cues(1)[0],
                external_ja="fabricated external",
            ),
        ),
    )
    reject(
        lambda: prepare_stateful_asr_package(
            injected_external,
            generation_key="external-filtered",
        ),
        "EXTERNAL_JA_INJECTION_REJECTED",
    )

    original_classifier = prepare_module.classify_nonlexical

    def failing_classifier(_text):
        raise RuntimeError("synthetic classifier failure")

    prepare_module.classify_nonlexical = failing_classifier
    try:
        reject(
            lambda: prepare_stateful_asr_package(
                asr_package(1),
                generation_key="classifier-failure-filtered",
            ),
            "CLASSIFIER_FAILURE_PROPAGATED",
        )
    finally:
        prepare_module.classify_nonlexical = original_classifier

    original_prepare = asr_module.prepare_stateful_package

    def mutating_prepare(package, *, generation_key):
        prepared = original_prepare(
            package,
            generation_key=generation_key,
        )
        mutated_cue = replace(
            prepared.package.cues[0],
            stt_ja="mutated retained source",
        )
        mutated_package = StatefulSubtitlePackage(
            schema_version=prepared.package.schema_version,
            dvd_id=prepared.package.dvd_id,
            generation_key=prepared.package.generation_key,
            claim_token=prepared.package.claim_token,
            cues=(mutated_cue,) + prepared.package.cues[1:],
        )
        return replace(prepared, package=mutated_package)

    asr_module.prepare_stateful_package = mutating_prepare
    try:
        reject(
            lambda: prepare_stateful_asr_package(
                asr_package(1),
                generation_key="mutation-filtered",
            ),
            "RETAINED_TEXT_MUTATION_REJECTED",
        )
    finally:
        asr_module.prepare_stateful_package = original_prepare

    duplicate = list(asr_cues(2))
    duplicate[1] = replace(duplicate[1], cue_id=duplicate[0].cue_id)
    reject(
        lambda: build_stateful_asr_package(
            tuple(duplicate),
            dvd_id="TEST-001",
            generation_key="bad-duplicate",
            claim_token=7,
        ),
        "DUPLICATE_ID_REJECTED",
    )

    missing = list(asr_cues(2))
    missing[1] = replace(missing[1], cue_id="asr-000003")
    reject(
        lambda: build_stateful_asr_package(
            tuple(missing),
            dvd_id="TEST-001",
            generation_key="bad-missing",
            claim_token=7,
        ),
        "MISSING_ID_REJECTED",
    )

    bad_stt = list(asr_cues(1))
    object.__setattr__(bad_stt[0], "stt_ja", None)
    reject(
        lambda: build_stateful_asr_package(
            tuple(bad_stt),
            dvd_id="TEST-001",
            generation_key="bad-stt",
            claim_token=7,
        ),
        "MISSING_STT_REJECTED",
    )

    bad_external = list(asr_cues(1))
    object.__setattr__(bad_external[0], "external_ja", "fabricated external")
    reject(
        lambda: build_stateful_asr_package(
            tuple(bad_external),
            dvd_id="TEST-001",
            generation_key="bad-external",
            claim_token=7,
        ),
        "EXTERNAL_JA_REJECTED",
    )

    reject(
        lambda: build_stateful_asr_package(
            asr_cues(4096 + 1),
            dvd_id="TEST-001",
            generation_key="over-limit",
            claim_token=7,
        ),
        "ASR_PACKAGE_4097_REJECTED",
    )

    direct_cues = build_asr_only_cue_sequence(
        pipeline_fixture.direct_asr_route()
    )
    check(
        tuple(cue.cue_id for cue in direct_cues)
        == ("asr-000001", "asr-000002", "asr-000003")
        and all(cue.external_ja is None for cue in direct_cues)
        and tuple(cue.stt_ja for cue in direct_cues)
        == ("音声一", "音声二", "音声三"),
        "EXISTING_ASR_PLAN_SEQUENCE_REUSED",
    )

    pure_query = build_stateful_part_query(
        package_921,
        serialize_stateful_package(package_921),
        1,
    )
    check(
        "Use only the available stt_ja as Japanese semantic evidence." in pure_query
        and "When only one Japanese source is available" in pure_query
        and "Use external_ja as authorized semantic evidence" not in pure_query
        and "compare both sources" not in pure_query
        and "cue_id, repaired_ja, ko" in pure_query
        and "Do not emit timestamps" in pure_query,
        "PURE_ASR_PROMPT_BRANCH",
    )

    hybrid_query = build_stateful_part_query(
        hybrid_package(),
        serialize_stateful_package(hybrid_package()),
        1,
    )
    check(
        "Use external_ja as authorized semantic evidence" in hybrid_query
        and "compare both sources" in hybrid_query
        and "Use only the available stt_ja" not in hybrid_query,
        "HYBRID_PROMPT_UNCHANGED",
    )

    mixed_query = build_stateful_part_query(
        mixed_package(),
        serialize_stateful_package(mixed_package()),
        1,
    )
    check(
        "Use external_ja as authorized semantic evidence" in mixed_query
        and "compare both sources" in mixed_query
        and "Use only the available stt_ja" not in mixed_query,
        "MIXED_PROMPT_EXISTING_BEHAVIOR",
    )

    print(f"STATEFUL_ASR_SMOKE_PASS={passed}")
    print("STATEFUL_ASR_SMOKE_FAIL=0")


if __name__ == "__main__":
    main()
