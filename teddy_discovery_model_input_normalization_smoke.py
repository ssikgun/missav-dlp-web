"""Offline CP7U regression coverage for raw/model source separation."""

from pathlib import Path
import tempfile

from teddy_discovery_asr_source_quality import classify_nonlexical
from teddy_discovery_hermes_v2_batching import invoke_hermes_v2_batched
from teddy_discovery_hermes_v2 import (
    HermesV2CueInput,
    HermesV2CueOutput,
    HermesV2Request,
    HermesV2Result,
)
from teddy_discovery_hermes_v2_transport import build_hermes_v2_prompt
from teddy_discovery_model_input_normalization import (
    MODEL_INPUT_NORMALIZATION_VERSION,
    MODEL_INPUT_PATHOLOGICAL_RUN_FLOOR,
    MODEL_INPUT_PERIODIC_MIN_REPETITIONS,
    MODEL_INPUT_SHORT_UNIT_MAX,
    normalize_model_input_request,
    normalize_model_input_text,
)
from teddy_discovery_stateful_live_runner import build_parser
from teddy_discovery_stateful_parts import (
    StatefulSemanticPart,
    StatefulPartsValidationError,
    build_stateful_part_plan,
    parse_stateful_part,
    periodic_repetition_evidence,
    serialize_stateful_part,
)
from teddy_discovery_stateful_prepare import prepare_stateful_package
from teddy_discovery_subtitle_v2_pipeline import _call_semantic_boundary
from teddy_discovery_stateful_translator import (
    StatefulSubtitlePackage,
    StatefulSubtitleResult,
    _atomic_private_write,
    bind_stateful_model_input_identity,
    bind_stateful_semantic_policy,
    build_stateful_model_input_package,
    derive_stateful_session_id,
    serialize_stateful_model_input,
    serialize_stateful_package,
    serialize_stateful_result,
    parse_stateful_result,
    stateful_session_id_for_package,
    stateful_staging_paths,
)
from teddy_discovery_stateful_policy import (
    DEFAULT_STATEFUL_SEMANTIC_POLICY,
    STATEFUL_SEMANTIC_POLICY_16,
    STATEFUL_SEMANTIC_POLICY_128,
    STATEFUL_SEMANTIC_POLICY_ID_16,
    STATEFUL_SEMANTIC_POLICY_ID_64,
    STATEFUL_SEMANTIC_POLICY_ID_128,
)
from teddy_discovery_stage11_live_adapters import build_first_pass_adapter


def _cue(cue_id: str, *, external: str | None = None, stt: str | None = None):
    return HermesV2CueInput(
        cue_id=cue_id,
        external_ja=external,
        stt_ja=stt,
        en=None,
        before_context=(),
        after_context=(),
    )


def _package(cue: HermesV2CueInput, generation_key: str = "normalization-smoke"):
    return StatefulSubtitlePackage(
        schema_version=1,
        dvd_id="NORMALIZATION-SMOKE",
        generation_key=generation_key,
        claim_token=7,
        cues=(cue,),
    )


def main() -> None:
    passed = 0

    def check(value: bool, marker: str) -> None:
        nonlocal passed
        if not value:
            raise AssertionError(marker)
        passed += 1
        print("PASS=" + marker)

    raw_suffix = "あ" + "ー" * 444
    suffix = normalize_model_input_text(raw_suffix)
    check(
        suffix.normalized_text == "あーー"
        and suffix.changed
        and len(suffix.normalized_text) <= 8
        and suffix.events[0].source_start == 1
        and suffix.events[0].source_end == 445,
        "MIXED_SUFFIX_ELONGATION_BOUNDED",
    )
    check(
        raw_suffix == "あ" + "ー" * 444,
        "RAW_SUFFIX_TEXT_UNCHANGED",
    )

    pure_nonlexical = StatefulSubtitlePackage(
        schema_version=1,
        dvd_id="NORMALIZATION-SMOKE",
        generation_key="normalization-smoke",
        claim_token=7,
        cues=(
            _cue("asr-000001", stt="あ" * 400),
            _cue("asr-000002", stt="普通の文です"),
        ),
    )
    prepared = prepare_stateful_package(
        pure_nonlexical,
        generation_key="normalization-smoke-filtered",
    )
    check(
        classify_nonlexical("あ" * 400).action == "OMIT"
        and prepared.omitted_cue_ids == ("asr-000001",)
        and tuple(cue.cue_id for cue in prepared.package.cues)
        == ("asr-000002",),
        "EXISTING_PURE_NONLEXICAL_OMIT_PRESERVED",
    )

    check(
        normalize_model_input_text("すごーーい").normalized_text == "すごーーい"
        and not normalize_model_input_text("すごーーい").changed,
        "ORDINARY_EMPHASIS_UNCHANGED",
    )
    short_normal = "あー" * 8
    check(
        normalize_model_input_text(short_normal).normalized_text == short_normal
        and not normalize_model_input_text(short_normal).changed,
        "SHORT_NORMAL_REPETITION_UNCHANGED",
    )
    punctuation = "!?" * 16
    punctuation_pathological = "!?" * 32
    check(
        normalize_model_input_text(punctuation).normalized_text == punctuation
        and normalize_model_input_text(punctuation_pathological).changed,
        "ORDINARY_PUNCTUATION_BOUNDARY_PRESERVED",
    )

    short_unit_raw = "앞" + ("あー" * 20) + "뒤"
    short_unit = normalize_model_input_text(short_unit_raw)
    check(
        short_unit.changed
        and short_unit.normalized_text == "앞あーあー뒤"
        and len(short_unit.normalized_text) < len(short_unit_raw),
        "INTERNAL_SHORT_UNIT_RUN_BOUNDED",
    )
    check(
        normalize_model_input_text(short_unit.normalized_text).normalized_text
        == short_unit.normalized_text,
        "NORMALIZATION_IDEMPOTENT",
    )

    spaced_token = "え?"
    spaced_raw = "- " + " ".join([spaced_token] * 74)
    spaced = normalize_model_input_text(spaced_raw)
    check(
        spaced.changed
        and spaced.normalized_text == "- え? え?"
        and spaced_raw == "- " + " ".join([spaced_token] * 74)
        and len(spaced.events) == 1
        and spaced.events[0].source_start == 2
        and spaced.events[0].source_end == len(spaced_raw)
        and spaced.events[0].unit_length == 2
        and spaced.events[0].separator_length == 1
        and spaced.events[0].complete_repetitions == 74,
        "SPACED_SHORT_TOKEN_RUN_BOUNDED",
    )
    check(
        normalize_model_input_text(spaced.normalized_text).normalized_text
        == spaced.normalized_text,
        "SPACED_NORMALIZATION_IDEMPOTENT",
    )

    ordinary_spaced = "これは 普通の 日本語です"
    ordinary_spaced_result = normalize_model_input_text(ordinary_spaced)
    check(
        not ordinary_spaced_result.changed
        and ordinary_spaced_result.normalized_text == ordinary_spaced,
        "ORDINARY_SPACED_JAPANESE_UNCHANGED",
    )

    line_broken = ("え?\n" * 74).rstrip("\n")
    line_broken_result = normalize_model_input_text(line_broken)
    check(
        not line_broken_result.changed
        and line_broken_result.normalized_text == line_broken,
        "SEPARATOR_NORMALIZATION_NEVER_CROSSES_LINES",
    )
    ambiguous_unicode = "a\u0301" * 64
    ambiguous_result = normalize_model_input_text(ambiguous_unicode)
    check(
        not ambiguous_result.changed
        and ambiguous_result.normalized_text == ambiguous_unicode,
        "AMBIGUOUS_UNICODE_FAILS_CLOSED",
    )

    request_raw = HermesV2Request(
        cues=(_cue("cue-raw", stt=raw_suffix),)
    )
    request_projection = normalize_model_input_request(request_raw)
    check(
        request_raw.cues[0].stt_ja == raw_suffix
        and request_projection.model_request.cues[0].stt_ja == "あーー"
        and request_projection.raw_request is request_raw,
        "REQUEST_RAW_MODEL_SEPARATION",
    )
    prompt_text = build_hermes_v2_prompt(request_raw).decode("utf-8")
    check(
        raw_suffix not in prompt_text
        and '"stt_ja":"あーー"' in prompt_text,
        "HERMES_PROMPT_RECEIVES_MODEL_PROJECTION",
    )
    seen_batches = []

    def offline_batch_boundary(model_request):
        seen_batches.append(model_request)
        return HermesV2Result(
            cues=(HermesV2CueOutput("cue-raw", None, "정상"),)
        )

    invoke_hermes_v2_batched(request_raw, offline_batch_boundary)
    check(
        len(seen_batches) == 1
        and seen_batches[0].cues[0].stt_ja == "あーー",
        "HERMES_BATCH_RECEIVES_MODEL_PROJECTION",
    )
    seen_model_request = {}

    def offline_semantic_boundary(model_request):
        seen_model_request["value"] = model_request
        return HermesV2Result(
            cues=(HermesV2CueOutput("cue-raw", None, "정상"),)
        )

    _call_semantic_boundary(offline_semantic_boundary, request_raw)
    check(
        seen_model_request["value"].cues[0].stt_ja == "あーー"
        and request_raw.cues[0].stt_ja == raw_suffix,
        "ONE_SHOT_SEMANTIC_BOUNDARY_RECEIVES_MODEL_PROJECTION",
    )

    retained_raw = _package(
        _cue("asr-000002", stt=raw_suffix),
        generation_key="raw-model-separation",
    )
    retained_with_identity = bind_stateful_model_input_identity(retained_raw)
    retained_with_policy = bind_stateful_semantic_policy(
        retained_with_identity,
        DEFAULT_STATEFUL_SEMANTIC_POLICY,
    )
    model_package = build_stateful_model_input_package(retained_with_identity)
    check(
        retained_with_identity.cues[0].stt_ja == raw_suffix
        and model_package.cues[0].stt_ja == "あーー"
        and serialize_stateful_package(retained_with_identity)
        != serialize_stateful_model_input(retained_with_identity),
        "STATEFUL_RAW_PACKAGE_AND_MODEL_PACKAGE_SEPARATE",
    )

    # The exact first-pass result is an output/provenance artifact.  CP7U does
    # not rewrite repaired_ja while projecting a later model input.
    repaired_raw = "あ" + "ー" * 444
    output = StatefulSubtitleResult(
        schema_version=1,
        dvd_id=retained_with_identity.dvd_id,
        generation_key=retained_with_identity.generation_key,
        claim_token=retained_with_identity.claim_token,
        session_id=stateful_session_id_for_package(retained_with_identity),
        cues=(HermesV2CueOutput("asr-000002", repaired_raw, "정상"),),
    )
    repaired_preserved = repaired_raw == output.cues[0].repaired_ja
    check(repaired_preserved, "RAW_REPAIRED_JA_EVIDENCE_UNCHANGED")
    # Keep serialization in the regression so the exact output artifact is
    # also proven not to be replaced by model-input text.
    check(
        parse_stateful_result(
            serialize_stateful_result(output),
            retained_with_identity,
        ).cues[0].repaired_ja == repaired_raw,
        "REPAIRED_JA_SERIALIZATION_HAS_NO_KOREAN_REPLACEMENT",
    )

    source_raw = "かな" * 74 + "か"
    source_package = bind_stateful_semantic_policy(
        bind_stateful_model_input_identity(
            _package(
                _cue("source-0001", external=source_raw),
                "cp7m-raw-source",
            )
        ),
        DEFAULT_STATEFUL_SEMANTIC_POLICY,
    )
    source_model_bytes = serialize_stateful_model_input(source_package)
    source_plan = build_stateful_part_plan(source_package, source_model_bytes)
    source_expected = source_plan.parts[0]
    source_ko = "번역" * 40
    source_part = StatefulSemanticPart(
        part_schema_version=1,
        session_id=source_plan.session_id,
        input_sha256=source_plan.input_sha256,
        part_index=1,
        first_cue_id=source_expected.first_cue_id,
        last_cue_id=source_expected.last_cue_id,
        cues=(HermesV2CueOutput("source-0001", None, source_ko),),
        source_cues=source_plan.source_cues,
    )
    accepted_source_part = parse_stateful_part(
        serialize_stateful_part(source_part),
        source_expected,
        source_plan,
    )
    check(
        source_package.cues[0].external_ja == source_raw
        and model_package.cues[0].stt_ja == "あーー"
        and build_stateful_model_input_package(source_package).cues[0].external_ja
        != source_raw
        and periodic_repetition_evidence(source_raw) is not None
        and accepted_source_part.cues[0].ko == source_ko,
        "CP7M_SOURCE_GROUNDING_USES_RAW_AUTHORITATIVE_SOURCE",
    )

    erofv_package = bind_stateful_semantic_policy(
        bind_stateful_model_input_identity(
            _package(_cue("erofv-source", stt=raw_suffix), "erofv-raw")
        ),
        DEFAULT_STATEFUL_SEMANTIC_POLICY,
    )
    erofv_model_bytes = serialize_stateful_model_input(erofv_package)
    erofv_plan = build_stateful_part_plan(erofv_package, erofv_model_bytes)
    erofv_expected = erofv_plan.parts[0]
    try:
        StatefulSemanticPart(
            part_schema_version=1,
            session_id=erofv_plan.session_id,
            input_sha256=erofv_plan.input_sha256,
            part_index=1,
            first_cue_id=erofv_expected.first_cue_id,
            last_cue_id=erofv_expected.last_cue_id,
            cues=(HermesV2CueOutput("erofv-source", None, "아" * 474),),
            source_cues=erofv_plan.source_cues,
        )
    except StatefulPartsValidationError as error:
        erofv_rejected = error.reason_code == "INVALID_KO"
    else:
        erofv_rejected = False
    check(
        erofv_package.cues[0].stt_ja == raw_suffix
        and parse_package(erofv_model_bytes).cues[0].stt_ja == "あーー"
        and erofv_rejected,
        "CP7M_REJECTS_EROFV_AMPLIFICATION_FROM_RAW_SOURCE",
    )

    old_bytes = serialize_stateful_package(retained_raw)
    new_bytes = serialize_stateful_model_input(retained_with_policy)
    new_plan = build_stateful_part_plan(retained_with_policy, new_bytes)
    check(
        new_plan.input_sha256
        != __import__("hashlib").sha256(old_bytes).hexdigest()
        and stateful_session_id_for_package(retained_raw)
        != stateful_session_id_for_package(retained_with_identity)
        and MODEL_INPUT_NORMALIZATION_VERSION in retained_with_identity.generation_key,
        "NORMALIZED_INPUT_HASH_AND_SESSION_ISOLATED",
    )
    try:
        build_stateful_part_plan(retained_raw, old_bytes)
    except Exception:
        stale_rejected = True
    else:
        stale_rejected = False
    check(stale_rejected, "OLD_UNNORMALIZED_SEMANTIC_INPUT_REJECTED")

    normal_cues = tuple(
        _cue(f"cue-{index:04d}", external="通常の文")
        for index in range(173)
    )
    policy_source = StatefulSubtitlePackage(
        schema_version=1,
        dvd_id="POLICY-NORMALIZATION-SMOKE",
        generation_key="policy-normalization",
        claim_token=1,
        cues=normal_cues,
    )
    policy_packages = {
        STATEFUL_SEMANTIC_POLICY_ID_16: bind_stateful_semantic_policy(
            bind_stateful_model_input_identity(policy_source),
            STATEFUL_SEMANTIC_POLICY_16,
        ),
        STATEFUL_SEMANTIC_POLICY_ID_64: bind_stateful_semantic_policy(
            bind_stateful_model_input_identity(policy_source),
            DEFAULT_STATEFUL_SEMANTIC_POLICY,
        ),
        STATEFUL_SEMANTIC_POLICY_ID_128: bind_stateful_semantic_policy(
            bind_stateful_model_input_identity(policy_source),
            STATEFUL_SEMANTIC_POLICY_128,
        ),
    }
    policy_parts = {
        policy_id: build_stateful_part_plan(
            package,
            serialize_stateful_model_input(package),
            semantic_policy=policy_id,
        ).part_count
        for policy_id, package in policy_packages.items()
    }
    parser_defaults = build_parser().parse_args(
        [
            "--package", "/tmp/input.json",
            "--task-directory", "/tmp/task",
            "--final-result", "/tmp/result.json",
            "--remote", "offline",
            "--remote-task", "/tmp/remote-task",
            "--ssh-key", "/tmp/key",
            "--known-hosts", "/tmp/known",
        ]
    )
    check(
        policy_parts == {
            STATEFUL_SEMANTIC_POLICY_ID_16: 11,
            STATEFUL_SEMANTIC_POLICY_ID_64: 3,
            STATEFUL_SEMANTIC_POLICY_ID_128: 2,
        }
        and parser_defaults.semantic_policy == STATEFUL_SEMANTIC_POLICY_ID_64
        and parser_defaults.turn_timeout == 600,
        "FIXED64_DEFAULT_AND_16_64_128_POLICY_REGRESSION",
    )

    # Exercise the real first-pass adapter's staging split without a remote,
    # native process, or model call.
    with tempfile.TemporaryDirectory(prefix="cp7u-normalization-smoke-") as root:
        staging_root = Path(root)
        observed = {}

        def prepare_remote(package, paths, *, route):
            observed["raw"] = parse_package(paths.raw_input_path.read_bytes())
            observed["model"] = parse_package(paths.input_path.read_bytes())
            return "/offline/" + paths.task_directory.name

        def native_run(args):
            raw = parse_package(Path(args.raw_package).read_bytes())
            model = parse_package(Path(args.package).read_bytes())
            observed["native_raw"] = raw
            observed["native_model"] = model
            result = StatefulSubtitleResult(
                schema_version=raw.schema_version,
                dvd_id=raw.dvd_id,
                generation_key=raw.generation_key,
                claim_token=raw.claim_token,
                session_id=stateful_session_id_for_package(raw),
                cues=tuple(
                    HermesV2CueOutput(cue.cue_id, None, "정상")
                    for cue in raw.cues
                ),
            )
            _atomic_private_write(
                Path(args.final_result),
                serialize_stateful_result(result),
            )
            return 0

        adapter = build_first_pass_adapter(
            remote="offline",
            ssh_key="/offline/key",
            known_hosts="/offline/known-hosts",
            prepare_remote=prepare_remote,
            native_run=native_run,
        )
        result = adapter(
            retained_with_policy,
            route="ASR_ONLY",
            staging_root=staging_root,
        )
        paths = stateful_staging_paths(
            staging_root / stateful_session_id_for_package(retained_with_policy)
        )
        check(
            result.cues[0].ko == "정상"
            and observed["raw"].cues[0].stt_ja == raw_suffix
            and observed["model"].cues[0].stt_ja == "あーー"
            and observed["native_raw"].cues[0].stt_ja == raw_suffix
            and observed["native_model"].cues[0].stt_ja == "あーー"
            and paths.raw_input_path.read_bytes()
            == serialize_stateful_package(retained_with_policy),
            "LIVE_ADAPTER_STAGES_RAW_AND_MODEL_INPUTS",
        )

    source = Path("teddy_discovery_model_input_normalization.py").read_text(
        encoding="utf-8"
    )
    check(
        "EROFV-387" not in source
        and "asr-000333" not in source
        and "EBWH-350" not in source
        and "asr-000624" not in source
        and "え?" not in source
        and "if raw_text ==" not in source,
        "NO_TITLE_CUE_TEXT_SPECIFIC_BRANCHES",
    )
    check(
        MODEL_INPUT_PATHOLOGICAL_RUN_FLOOR == 64
        and MODEL_INPUT_SHORT_UNIT_MAX == 4
        and MODEL_INPUT_PERIODIC_MIN_REPETITIONS == 16
        and MODEL_INPUT_NORMALIZATION_VERSION
        == "stage11-model-input=repeat-v2",
        "EVIDENCE_BASED_NORMALIZATION_BOUNDS",
    )

    print("MODEL_INPUT_NORMALIZATION_SMOKE_PASS_COUNT=" + str(passed))
    print("MODEL_INPUT_NORMALIZATION_SMOKE_FAIL_COUNT=0")
    print("PRODUCTION_CALLS=0")


def parse_package(payload: bytes) -> StatefulSubtitlePackage:
    from teddy_discovery_stateful_translator import parse_stateful_package

    return parse_stateful_package(payload)


if __name__ == "__main__":
    main()
