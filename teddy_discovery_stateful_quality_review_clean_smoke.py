"""Offline synthetic smoke for deterministic FULL plus review CLEAN output."""

import ast
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path
import re
from unittest.mock import patch

from teddy_discovery_hermes_v2 import HermesV2CueOutput
from teddy_discovery_ko_srt import generate_korean_srt
from teddy_discovery_stateful_hybrid import (
    materialize_stateful_hybrid_srt,
    prepare_stateful_hybrid,
)
from teddy_discovery_stateful_boundary import bind_stateful_absorption_preparation
from teddy_discovery_stateful_hybrid_smoke import changed, semantic_result
from teddy_discovery_stateful_translator import StatefulAbsorptionResult, StatefulCueOutput
from teddy_discovery_alignment_application import apply_alignment_acceptance
from teddy_discovery_subtitle_external import ExternalSubtitlePayload
import teddy_discovery_stateful_quality_review as review
import teddy_discovery_stateful_quality_review_clean as clean
from teddy_discovery_stateful_translator import (
    serialize_stateful_package,
    serialize_stateful_result,
)
from teddy_discovery_subtitle_source_quality import classify_source_document
from teddy_discovery_subtitle_text import parse_subtitle_bytes
from teddy_discovery_subtitle_v2_orchestrator import project_affine_timestamp_ms
from teddy_discovery_subtitle_v2_pipeline_smoke import accepted_hybrid_route


def main():
    passed = failed = 0

    def check(name, callback):
        nonlocal passed, failed
        try:
            assert callback()
        except Exception as error:
            failed += 1
            print(f"FAIL {name}: {type(error).__name__}: {error}")
        else:
            passed += 1
            print("PASS " + name)

    def reject(name, callback):
        def rejected():
            try:
                callback()
            except clean.StatefulQualityReviewCleanError:
                return True
            return False

        check(name, rejected)

    preparation = prepare_stateful_hybrid(
        accepted_hybrid_route(),
        generation_key="clean-fixture",
        claim_token=11,
    )
    package = preparation.package
    base_first_pass = semantic_result(package)
    repaired_by_index = {0: "保持修正版", 3: "保留修正版"}
    first_pass = replace(
        base_first_pass,
        cues=tuple(
            HermesV2CueOutput(
                cue.cue_id,
                repaired_by_index.get(index),
                f"첫 번역 {index}",
            )
            for index, cue in enumerate(package.cues)
        ),
    )
    document = (
        preparation.route_decision.alignment_application.bundle
        .external_ja_document
    )
    source_quality = classify_source_document(document)
    originals = dict(
        preparation=preparation,
        package=package,
        result=first_pass,
        source_quality=source_quality,
    )
    request = review.build_review_request(**originals)

    categories = {
        review.KEEP: "DIALOGUE",
        review.REPAIR: "SEMANTIC_REPAIR",
        review.OMIT: "SOURCE_NOISE",
        review.AMBIGUOUS: "AMBIGUOUS",
    }

    def result_for(actions):
        return review.QualityReviewResult(
            review.STATEFUL_QUALITY_REVIEW_SCHEMA_VERSION,
            review.review_request_sha256(request),
            tuple(
                review.QualityReviewResultCue(
                    cue.cue_id,
                    action,
                    categories[action],
                    "Synthetic evidence supports this deterministic action.",
                    "審査修正版" if action == review.REPAIR else None,
                    "검수 수정본" if action == review.REPAIR else None,
                )
                for cue, action in zip(request.cues, actions, strict=True)
            ),
        )

    main_result = result_for(
        (review.KEEP, review.REPAIR, review.OMIT, review.AMBIGUOUS)
    )

    def materialize(
        *,
        package_value=package,
        first_pass_value=first_pass,
        preparation_value=preparation,
        request_value=request,
        result_value=main_result,
        preserve_absorption=False,
        omit_metadata=False,
    ):
        return clean.materialize_stateful_quality_review_clean(
            package_value,
            first_pass_value,
            preparation_value,
            request_value,
            result_value,
            source_quality=source_quality,
            preserve_absorption=preserve_absorption,
            omit_metadata=omit_metadata,
        )

    full_before = (
        serialize_stateful_package(package),
        serialize_stateful_result(first_pass),
        preparation.semantic_bindings,
    )
    sidecar_before = (
        review.serialize_review_request(request),
        review.serialize_review_result(main_result, request),
    )
    application = preparation.route_decision.alignment_application
    expected_timing = tuple(
        (
            project_affine_timestamp_ms(application.alignment, cue.start_ms),
            project_affine_timestamp_ms(application.alignment, cue.end_ms),
        )
        for cue in document.cues
    )
    output = materialize()

    null_nonabsorbed = review.QualityReviewRequest(
        request.schema_version, request.package_sha256, request.first_pass_sha256,
        request.source_sha256, request.source_translation_session_id,
        (replace(request.cues[0], first_pass_ko=None),) + request.cues[1:])
    try:
        review.validate_review_request(null_nonabsorbed, **originals)
        null_nonabsorbed_rejected = False
    except review.QualityReviewError:
        null_nonabsorbed_rejected = True
    check("null first-pass Korean remains bound to validated absorption only",
          lambda: null_nonabsorbed_rejected)

    check("KEEP preserves first-pass repaired JA and Korean", lambda:
          output.cues[0].ja == first_pass.cues[0].repaired_ja
          and output.cues[0].ko == first_pass.cues[0].ko
          and output.cues[0].review_action == review.KEEP)
    check("KEEP preserves original identity and timing", lambda:
          output.cues[0].cue_id == package.cues[0].cue_id
          and output.cues[0].original_source_index == 0
          and (output.cues[0].start_ms, output.cues[0].end_ms)
          == expected_timing[0])
    check("REPAIR uses only replacement JA and Korean", lambda:
          output.cues[1].ja == main_result.cues[1].replacement_ja
          and output.cues[1].ko == main_result.cues[1].replacement_ko
          and output.cues[1].ja != package.cues[1].external_ja
          and output.cues[1].ko != first_pass.cues[1].ko)
    check("REPAIR preserves original identity and timing", lambda:
          output.cues[1].cue_id == package.cues[1].cue_id
          and output.cues[1].original_source_index == 1
          and (output.cues[1].start_ms, output.cues[1].end_ms)
          == expected_timing[1])
    identity_result = replace(
        main_result,
        cues=(
            replace(
                main_result.cues[0],
                action=review.REPAIR,
                category="SEMANTIC_REPAIR",
                replacement_ja=first_pass.cues[0].repaired_ja,
                replacement_ko=first_pass.cues[0].ko,
            ),
        ) + main_result.cues[1:],
    )
    identity_output = materialize(result_value=identity_result)
    check("identity REPAIR uses first-pass semantics", lambda:
          identity_output.artifact == output.artifact
          and identity_output.cues[0].ja == output.cues[0].ja
          and identity_output.cues[0].ko == output.cues[0].ko
          and identity_output.cues[0].review_action == review.REPAIR)
    check("OMIT disappears only from CLEAN", lambda:
          output.source_indexes == (0, 1, 3)
          and len(package.cues) == len(first_pass.cues) == len(request.cues)
          == len(main_result.cues) == 4
          and main_result.cues[2].action == review.OMIT)
    check("AMBIGUOUS preserves original JA and first-pass Korean", lambda:
          output.cues[2].original_source_index == 3
          and output.cues[2].ja == package.cues[3].external_ja
          and output.cues[2].ko == first_pass.cues[3].ko
          and output.cues[2].review_action == review.AMBIGUOUS)
    check("source order survives omissions", lambda:
          output.source_indexes == tuple(sorted(output.source_indexes)))

    parsed_srt = parse_subtitle_bytes(output.artifact.payload, "srt")
    blocks = output.artifact.payload.decode("utf-8").strip().split("\n\n")
    check("existing renderer makes contiguous CLEAN numbering", lambda:
          tuple(block.splitlines()[0] for block in blocks) == ("1", "2", "3"))
    check("CLEAN SRT contains retained Korean and original timing", lambda:
          tuple(cue.text for cue in parsed_srt.cues)
          == tuple(cue.ko for cue in output.cues)
          and tuple((cue.start_ms, cue.end_ms) for cue in parsed_srt.cues)
          == tuple((cue.start_ms, cue.end_ms) for cue in output.cues))

    multiple_omit = materialize(
        result_value=result_for(
            (review.OMIT, review.KEEP, review.OMIT, review.KEEP)
        )
    )
    check("multiple OMIT decisions work", lambda:
          multiple_omit.source_indexes == (1, 3)
          and tuple(
              block.splitlines()[0]
              for block in multiple_omit.artifact.payload.decode("utf-8")
              .strip().split("\n\n")
          ) == ("1", "2"))
    edge_omit = materialize(
        result_value=result_for(
            (review.OMIT, review.KEEP, review.KEEP, review.OMIT)
        )
    )
    check("first and last cue OMIT work", lambda:
          edge_omit.source_indexes == (1, 2))
    all_keep_result = result_for((review.KEEP,) * len(package.cues))
    all_keep = materialize(result_value=all_keep_result)
    full_materialization = materialize_stateful_hybrid_srt(
        package,
        first_pass,
        preparation.route_decision,
        preparation,
    )
    check("all KEEP preserves every FULL cue", lambda:
          all_keep.source_indexes == tuple(range(len(package.cues)))
          and tuple(cue.ko for cue in all_keep.cues)
          == tuple(cue.ko for cue in first_pass.cues))
    check("all KEEP matches frozen HYBRID timing materializer bytes", lambda:
          all_keep.artifact == full_materialization.artifact)
    all_omit = materialize(
        result_value=result_for((review.OMIT,) * len(package.cues))
    )
    check("all OMIT uses existing explicit no-artifact result", lambda:
          all_omit.cues == () and all_omit.artifact.payload is None
          and all_omit.artifact.cue_count == 0)

    repeated = materialize()
    check("repeated materialization is byte-identical", lambda:
          repeated == output and repeated.artifact.payload == output.artifact.payload)
    check("FULL artifact remains byte-identical", lambda:
          full_before == (
              serialize_stateful_package(package),
              serialize_stateful_result(first_pass),
              preparation.semantic_bindings,
          ))
    check("review sidecar remains byte-identical", lambda:
          sidecar_before == (
              review.serialize_review_request(request),
              review.serialize_review_result(main_result, request),
          ))
    check("CLEAN models are immutable", lambda:
          _immutable(output, "cues") and _immutable(output.cues[0], "ko"))

    # Opt in the existing absorption contract and make only source 0/1 touch.
    # Their midpoints remain unchanged, so the accepted alignment witness stays exact.
    absorption_route = accepted_hybrid_route()
    absorption_application = absorption_route.alignment_application
    absorption_bundle = absorption_application.bundle
    external_cues = list(absorption_bundle.external_ja_document.cues)
    external_cues[1] = replace(external_cues[1], start_ms=1400, end_ms=2500)
    external_cues[2] = replace(external_cues[2], text="字幕作成")
    external_payload = ExternalSubtitlePayload.from_bytes(
        dvd_id=absorption_bundle.dvd_id,
        candidate=absorption_bundle.external_ja_payload.candidate,
        payload=generate_korean_srt(tuple(external_cues)).payload,
    )
    absorption_bundle = replace(
        absorption_bundle, external_ja_payload=external_payload,
        external_ja_document=external_payload.parse())
    absorption_application = apply_alignment_acceptance(
        absorption_bundle, absorption_application.decision,
        alignment=absorption_application.alignment)
    absorption_route = replace(absorption_route,
                               alignment_application=absorption_application)
    absorption_preparation = prepare_stateful_hybrid(
        absorption_route, generation_key="clean-absorption-fixture", claim_token=11)
    absorption_preparation, boundary = bind_stateful_absorption_preparation(
        absorption_preparation)
    absorption_package = absorption_preparation.package
    ordinary = semantic_result(absorption_package)
    absorption_first = StatefulAbsorptionResult(
        ordinary.schema_version, ordinary.dvd_id, ordinary.generation_key,
        ordinary.claim_token, ordinary.session_id,
        tuple(StatefulCueOutput(
            cue.cue_id, None,
            None if index == 0 else f"흡수 번역 {index}",
            absorbed_into=(absorption_package.cues[1].cue_id if index == 0 else None),
        ) for index, cue in enumerate(absorption_package.cues)), boundary)
    absorption_quality = classify_source_document(
        absorption_application.bundle.external_ja_document)
    absorption_request = review.build_review_request(
        preparation=absorption_preparation, package=absorption_package,
        result=absorption_first, source_quality=absorption_quality)
    absorption_keep = review.QualityReviewResult(
        review.STATEFUL_QUALITY_REVIEW_SCHEMA_VERSION,
        review.review_request_sha256(absorption_request),
        tuple(review.QualityReviewResultCue(
            cue.cue_id, review.KEEP, "DIALOGUE", "Retain validated absorption.",
            None, None)
              for cue in absorption_request.cues))
    absorbed_clean = clean.materialize_stateful_quality_review_clean(
        absorption_package, absorption_first, absorption_preparation,
        absorption_request, absorption_keep, source_quality=absorption_quality,
        preserve_absorption=True, omit_metadata=True)
    check("absorption review input records no standalone member translation",
          lambda: absorption_request.cues[0].first_pass_ko is None)
    check("metadata source remains a deterministic CLEAN omission",
          lambda: absorption_quality[2].action == "OMIT_METADATA"
          and absorbed_clean.source_indexes == (0, 1, 3))
    expected_absorbed_timing = (
        project_affine_timestamp_ms(absorption_application.alignment,
                                    absorption_application.bundle.external_ja_document.cues[0].start_ms),
        project_affine_timestamp_ms(absorption_application.alignment,
                                    absorption_application.bundle.external_ja_document.cues[1].end_ms),
    )
    check("CLEAN preserves absorption owner, source indexes and union timing", lambda:
          absorbed_clean.cues[0].original_source_index == 1
          and absorbed_clean.cues[0].source_indexes == (0, 1)
          and (absorbed_clean.cues[0].start_ms, absorbed_clean.cues[0].end_ms)
          == expected_absorbed_timing
          and absorbed_clean.source_indexes[:2] == (0, 1))

    for action in (review.REPAIR, review.OMIT):
        actions = (action,) + (review.KEEP,) * (len(absorption_request.cues) - 1)
        conflict_result = review.QualityReviewResult(
            review.STATEFUL_QUALITY_REVIEW_SCHEMA_VERSION,
            review.review_request_sha256(absorption_request),
            tuple(review.QualityReviewResultCue(
                cue.cue_id, item,
                {review.KEEP: "DIALOGUE", review.REPAIR: "SEMANTIC_REPAIR",
                 review.OMIT: "SOURCE_NOISE"}[item],
                "Synthetic conflict must fail closed.",
                "修正版" if item == review.REPAIR else None,
                "수정 번역" if item == review.REPAIR else None,
            ) for cue, item in zip(absorption_request.cues, actions, strict=True)))
        reject("absorption group rejects partial " + action, lambda conflict_result=conflict_result:
               clean.materialize_stateful_quality_review_clean(
                   absorption_package, absorption_first, absorption_preparation,
                   absorption_request, conflict_result,
                   source_quality=absorption_quality,
                   preserve_absorption=True, omit_metadata=True))

    reject("detached package rejected", lambda: materialize(
        package_value=changed(package, generation_key="detached")))
    detached_first_cues = (
        HermesV2CueOutput(
            first_pass.cues[0].cue_id,
            first_pass.cues[0].repaired_ja,
            "detached translation",
        ),
    ) + first_pass.cues[1:]
    reject("detached first-pass result rejected", lambda: materialize(
        first_pass_value=changed(first_pass, cues=detached_first_cues)))
    reject("detached review request rejected", lambda: materialize(
        request_value=changed(request, package_sha256="0" * 64)))
    reject("wrong review-result request SHA rejected", lambda: materialize(
        result_value=replace(main_result, request_sha256="0" * 64)))
    reject("review cue order mismatch rejected", lambda: materialize(
        result_value=replace(main_result, cues=tuple(reversed(main_result.cues)))))
    malformed_action = changed(main_result.cues[0], action="DELETE")
    reject("unsupported review action uses canonical validator", lambda: materialize(
        result_value=changed(
            main_result,
            cues=(malformed_action,) + main_result.cues[1:],
        )))
    malformed_repair = changed(main_result.cues[1], replacement_ko=None)
    reject("malformed REPAIR uses canonical validator", lambda: materialize(
        result_value=changed(
            main_result,
            cues=(main_result.cues[0], malformed_repair)
            + main_result.cues[2:],
        )))

    bundle = application.bundle
    detached_document = changed(
        document,
        cues=(
            changed(document.cues[0], start_ms=document.cues[0].start_ms + 1),
        ) + document.cues[1:],
    )
    detached_preparation = changed(
        preparation,
        route_decision=changed(
            preparation.route_decision,
            alignment_application=changed(
                application,
                bundle=changed(bundle, external_ja_document=detached_document),
            ),
        ),
    )
    reject("detached timing source rejected", lambda: materialize(
        preparation_value=detached_preparation))

    with patch.object(
        clean, "generate_korean_srt", wraps=generate_korean_srt
    ) as existing_renderer:
        renderer_output = materialize()
        check("existing SRT renderer reused", lambda:
              existing_renderer.call_count >= 1
              and renderer_output.artifact == output.artifact)

    result_fields = {field.name for field in fields(review.QualityReviewResultCue)}
    check("review result owns no timing or source index", lambda:
          not {"start_ms", "end_ms", "source_index"} & result_fields)
    source = Path(clean.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    check("no timing inference", lambda:
          "infer_robust_affine_alignment" not in source
          and "generate_monotonic_anchor_candidates" not in source
          and "project_affine_timestamp_ms" in source)
    check("no model filesystem database NAS or publication behavior", lambda:
          not imported_roots & {"os", "pathlib", "subprocess", "sqlite3"}
          and not any(
              isinstance(node, ast.Call)
              and isinstance(node.func, ast.Name)
              and node.func.id in {"open", "exec", "eval"}
              for node in ast.walk(tree)
          ))
    check("no title cue or dialogue hardcode", lambda:
          not re.search(
              r"\b[A-Z]{2,10}-\d{2,8}\b|ja-\d{6}|"
              r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]",
              source,
          ))

    print(f"Quality review CLEAN smoke: PASS={passed} FAIL={failed}")
    return int(failed != 0)


def _immutable(value, field_name):
    try:
        setattr(value, field_name, None)
    except FrozenInstanceError:
        return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
