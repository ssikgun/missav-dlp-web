"""Offline synthetic smoke for deterministic FULL plus review CLEAN output."""

import ast
from dataclasses import FrozenInstanceError, fields, replace
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import uuid

from teddy_discovery_hermes_v2 import HermesV2CueOutput
from teddy_discovery_ko_srt import generate_korean_srt
from teddy_discovery_stateful_hybrid import (
    materialize_stateful_hybrid_srt,
    prepare_stateful_hybrid,
)
from teddy_discovery_stateful_boundary import bind_stateful_absorption_preparation
from teddy_discovery_stateful_hybrid_smoke import changed, semantic_result
from teddy_discovery_stateful_translator import (
    StatefulAbsorptionResult,
    StatefulCueOutput,
)
from teddy_discovery_alignment_application import apply_alignment_acceptance
from teddy_discovery_subtitle_external import ExternalSubtitlePayload
import teddy_discovery_stateful_quality_review as review
import teddy_discovery_stateful_quality_review_clean as clean
import teddy_discovery_stateful_absorption_review as group_review
import teddy_discovery_stage11_deployment as deployment
import teddy_discovery_stage11_normal_mode as normal_mode
import teddy_discovery_stateful_quality_review_runner as review_runner
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

    def reject_reason(name, expected_reason, callback):
        def rejected():
            try:
                callback()
            except clean.StatefulQualityReviewCleanError as error:
                return str(error) == expected_reason
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

    ambiguous_member_actions = (
        review.AMBIGUOUS, review.KEEP,
        *((review.KEEP,) * (len(absorption_request.cues) - 2)),
    )
    ambiguous_member_result = review.QualityReviewResult(
        review.STATEFUL_QUALITY_REVIEW_SCHEMA_VERSION,
        review.review_request_sha256(absorption_request),
        tuple(review.QualityReviewResultCue(
            cue.cue_id, action,
            {review.KEEP: "DIALOGUE", review.AMBIGUOUS: "AMBIGUOUS"}[action],
            "Uncertainty retains the validated absorption group.", None, None,
        ) for cue, action in zip(
            absorption_request.cues, ambiguous_member_actions, strict=True)))
    ambiguous_member_clean = clean.materialize_stateful_quality_review_clean(
        absorption_package, absorption_first, absorption_preparation,
        absorption_request, ambiguous_member_result,
        source_quality=absorption_quality, preserve_absorption=True,
        omit_metadata=True)
    check("AMBIGUOUS group member preserves owner and union timing", lambda:
          ambiguous_member_clean.cues[0].source_indexes == (0, 1)
          and ambiguous_member_clean.cues[0].original_source_index == 1
          and (ambiguous_member_clean.cues[0].start_ms,
               ambiguous_member_clean.cues[0].end_ms) == expected_absorbed_timing)

    owner_repair_actions = (
        review.KEEP, review.REPAIR,
        *((review.KEEP,) * (len(absorption_request.cues) - 2)),
    )
    owner_repair_result = review.QualityReviewResult(
        review.STATEFUL_QUALITY_REVIEW_SCHEMA_VERSION,
        review.review_request_sha256(absorption_request),
        tuple(review.QualityReviewResultCue(
            cue.cue_id, action,
            {review.KEEP: "DIALOGUE", review.REPAIR: "SEMANTIC_REPAIR"}[action],
            "Owner-only repair lacks explicit group scope in this request.",
            "修正版" if action == review.REPAIR else None,
            "수정 번역" if action == review.REPAIR else None,
        ) for cue, action in zip(
            absorption_request.cues, owner_repair_actions, strict=True)))
    reject_reason(
        "owner-only REPAIR stays blocked without group-scoped review evidence",
        "owner REPAIR lacks validated absorption-group review authority",
        lambda: clean.materialize_stateful_quality_review_clean(
            absorption_package, absorption_first, absorption_preparation,
            absorption_request, owner_repair_result,
            source_quality=absorption_quality,
            preserve_absorption=True, omit_metadata=True),
    )

    parent_review_session = str(uuid.uuid4())
    bound_owner_repair_result = review.bind_review_execution_provenance(
        owner_repair_result, absorption_request, parent_review_session)
    group_request = group_review.build_absorption_group_review_request(
        preparation=absorption_preparation,
        package=absorption_package,
        first_pass_result=absorption_first,
        review_request=absorption_request,
        review_result=bound_owner_repair_result,
        source_quality=absorption_quality,
    )
    check("group scope binds deterministic owner, membership, source and provenance",
          lambda: group_request is not None
          and group_request.title_context == absorption_request.cues
          and len(group_request.groups) == 1
          and group_request.groups[0].scope.owner_cue_id
          == absorption_package.cues[1].cue_id
          and group_request.groups[0].scope.cue_ids
          == (absorption_package.cues[0].cue_id,
              absorption_package.cues[1].cue_id)
          and group_request.groups[0].scope.source_indexes == (0, 1)
          and group_request.groups[0].member_cues[0].first_pass_ko is None
          and group_request.groups[0].member_cues[1].first_pass_ko
          == absorption_first.cues[1].ko
          and group_request.groups[0].member_decisions[-1].action == review.REPAIR)

    group_originals = {
        "preparation": absorption_preparation,
        "package": absorption_package,
        "first_pass_result": absorption_first,
        "review_request": absorption_request,
        "review_result": bound_owner_repair_result,
        "source_quality": absorption_quality,
    }

    def forged_group_request(**updates):
        fields = group_review._scope_fields(group_request.groups[0].scope)
        fields.update(updates)
        scope = group_review.AbsorptionGroupScope(
            group_id=group_review._scope_identity(fields), **fields)
        group = replace(group_request.groups[0], scope=scope)
        return replace(group_request, groups=(group,))

    check("group boundary identity is rebuilt from original evidence", lambda:
          _raises_group_error(lambda:
              group_review.validate_absorption_group_review_request(
                  forged_group_request(boundary_evidence_sha256="0" * 64),
                  **group_originals)))
    check("group owner cannot be reassigned by review evidence", lambda:
          _raises_group_error(lambda:
              forged_group_request(
                  owner_cue_id=absorption_package.cues[0].cue_id)))
    check("group membership cannot be widened beyond its source cues", lambda:
          _raises_group_error(lambda:
              forged_group_request(
                  cue_ids=tuple(c.cue_id for c in absorption_package.cues[:3]),
                  source_indexes=(0, 1, 2))))

    def group_execution(action, *, request_value=group_request,
                        replacement_ja=None, replacement_ko=None,
                        nonce=None, session_id=None, payload_suffix=b""):
        session_id = session_id or str(uuid.uuid4())
        nonce = nonce or uuid.uuid4().hex + uuid.uuid4().hex
        request_payload = group_review.serialize_absorption_group_review_request(
            request_value)
        group_id = request_value.groups[0].scope.group_id
        decision = group_review.AbsorptionGroupReviewDecision(
            group_id, action, "Synthetic full-group semantic decision.",
            replacement_ja, replacement_ko)
        result_value = group_review.AbsorptionGroupReviewResult(
            group_review.ABSORPTION_GROUP_REVIEW_SCHEMA_VERSION,
            group_review.absorption_group_review_request_sha256(request_value),
            (decision,))
        result_payload = group_review.serialize_absorption_group_review_result(
            result_value, request_value,
            review_execution_session_id=session_id) + payload_suffix
        task = "/tmp/stage11-p2l-group-review/" + session_id
        receipt = {
            "schema_version": 1,
            "session_id": session_id,
            "task_sha256": hashlib.sha256(task.encode("utf-8")).hexdigest(),
            "request_sha256": hashlib.sha256(request_payload).hexdigest(),
            "input_sha256": hashlib.sha256(request_payload).hexdigest(),
            "receipt_nonce": nonce,
            "child_outcome": "COMPLETED",
            "child_returncode": 0,
            "result_state": "PRESENT",
            "result_sha256": hashlib.sha256(result_payload).hexdigest(),
            "result_size_bytes": len(result_payload),
        }
        receipt_payload = json.dumps(
            receipt, sort_keys=True, separators=(",", ":")) .encode("ascii")
        return group_review.AbsorptionGroupReviewExecutionEvidence(
            request_payload, result_payload, receipt_payload, task, nonce, session_id)

    def rebind_group_execution_result(execution, payload, *, rebind_receipt=True):
        receipt = json.loads(execution.receipt_payload)
        if rebind_receipt:
            receipt["result_sha256"] = hashlib.sha256(payload).hexdigest()
            receipt["result_size_bytes"] = len(payload)
        receipt_payload = json.dumps(
            receipt, sort_keys=True, separators=(",", ":")).encode("ascii")
        return replace(
            execution, result_payload=payload, receipt_payload=receipt_payload)

    json_variant_base = group_execution(
        group_review.GROUP_REVIEW_REPAIR,
        replacement_ja="グループ全体の修正文",
        replacement_ko="흡수 그룹 전체의 수정 번역",
    )
    json_variant_value = json.loads(json_variant_base.result_payload)

    def accepts_group_result_payload(payload):
        evidence = rebind_group_execution_result(json_variant_base, payload)
        return group_review.validate_absorption_group_review_execution(
            evidence, group_request).decisions[0].action == group_review.GROUP_REVIEW_REPAIR

    pretty_group_result = json.dumps(
        json_variant_value, ensure_ascii=False, indent=2).encode("utf-8")
    check("group parser accepts semantically identical pretty JSON", lambda:
          accepts_group_result_payload(pretty_group_result))

    one_decision = json_variant_value["decisions"][0]
    reordered_group_result = {
        "decisions": [{key: one_decision[key] for key in reversed(tuple(one_decision))}],
        "request_sha256": json_variant_value["request_sha256"],
        "schema_version": json_variant_value["schema_version"],
    }
    reordered_group_payload = json.dumps(
        reordered_group_result, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    check("group parser accepts object field-order differences", lambda:
          accepts_group_result_payload(reordered_group_payload))

    escaped_group_payload = json.dumps(
        json_variant_value, ensure_ascii=True, separators=(",", ":")
    ).encode("ascii")
    check("group parser accepts equivalent Unicode escapes", lambda:
          accepts_group_result_payload(escaped_group_payload))

    def rejects_group_result_payload(payload, *, rebind_receipt=True):
        evidence = rebind_group_execution_result(
            json_variant_base, payload, rebind_receipt=rebind_receipt)
        return _raises_group_error(lambda:
            group_review.validate_absorption_group_review_execution(
                evidence, group_request))

    check("result bytes remain bound to the native receipt SHA", lambda:
          rejects_group_result_payload(pretty_group_result, rebind_receipt=False))
    check("duplicate result JSON keys are rejected", lambda:
          rejects_group_result_payload(
              json_variant_base.result_payload[:-1] + b',"schema_version":1}'))

    missing_group_field = dict(json_variant_value)
    missing_group_field.pop("request_sha256")
    check("missing group result field is rejected", lambda:
          rejects_group_result_payload(json.dumps(
              missing_group_field, sort_keys=True, separators=(",", ":")).encode()))

    extra_group_field = dict(json_variant_value)
    extra_group_field["unexpected"] = True
    check("additional group result field is rejected", lambda:
          rejects_group_result_payload(json.dumps(
              extra_group_field, sort_keys=True, separators=(",", ":")).encode()))

    check("malformed group result JSON is rejected", lambda:
          rejects_group_result_payload(b"{invalid"))
    for constant in (b"NaN", b"Infinity"):
        nonfinite_group_payload = json_variant_base.result_payload.replace(
            b'"schema_version":1', b'"schema_version":' + constant, 1)
        check("non-finite JSON " + constant.decode("ascii") + " is rejected", lambda:
              rejects_group_result_payload(nonfinite_group_payload))

    wrong_group_id_value = json.loads(json_variant_base.result_payload)
    wrong_group_id_value["decisions"][0]["group_id"] = "0" * 64
    check("decision with a different group ID is rejected", lambda:
          rejects_group_result_payload(json.dumps(
              wrong_group_id_value, sort_keys=True, separators=(",", ":")).encode()))

    wrong_group_request_value = dict(json_variant_value)
    wrong_group_request_value["request_sha256"] = "0" * 64
    check("decision with a different request SHA is rejected", lambda:
          rejects_group_result_payload(json.dumps(
              wrong_group_request_value, sort_keys=True, separators=(",", ":")).encode()))

    invalid_repair_value = json.loads(json_variant_base.result_payload)
    invalid_repair_value["decisions"][0]["replacement_ja"] = "한글이 섞인 일본어"
    check("invalid group REPAIR replacement remains rejected", lambda:
          rejects_group_result_payload(json.dumps(
              invalid_repair_value, ensure_ascii=False,
              sort_keys=True, separators=(",", ":")).encode("utf-8")))

    wrong_nonce_value = json.loads(json_variant_base.receipt_payload)
    wrong_nonce_value["receipt_nonce"] = "0" * 64
    wrong_nonce_execution = replace(
        json_variant_base,
        receipt_payload=json.dumps(
            wrong_nonce_value, sort_keys=True, separators=(",", ":")).encode("ascii"))
    check("receipt nonce must match the independent execution nonce", lambda:
          _raises_group_error(lambda:
              group_review.validate_absorption_group_review_execution(
                  wrong_nonce_execution, group_request)))

    missing_receipt_execution = replace(
        json_variant_base, receipt_payload=b"")
    check("missing native receipt blocks a valid group result", lambda:
          _raises_group_error(lambda:
              group_review.validate_absorption_group_review_execution(
                  missing_receipt_execution, group_request)))

    reordered_title = list(group_request.title_context)
    reordered_title[2] = replace(reordered_title[2], first_pass_ko=None)
    second_cues = (reordered_title[2], reordered_title[3])
    second_scope_fields = group_review._scope_fields(group_request.groups[0].scope)
    second_scope_fields.update(
        owner_cue_id=reordered_title[3].cue_id,
        cue_ids=tuple(cue.cue_id for cue in second_cues),
        source_indexes=(2, 3),
        targeted_evidence_sha256=group_review._targeted_evidence_sha256(second_cues),
    )
    second_scope = group_review.AbsorptionGroupScope(
        group_id=group_review._scope_identity(second_scope_fields),
        **second_scope_fields,
    )
    second_group = group_review.AbsorptionGroupReviewGroup(
        second_scope,
        second_cues,
        (
            review.QualityReviewResultCue(
                second_cues[0].cue_id, review.KEEP, "DIALOGUE",
                "Synthetic ordered group context.", None, None),
            review.QualityReviewResultCue(
                second_cues[1].cue_id, review.REPAIR, "SEMANTIC_REPAIR",
                "Synthetic ordered group context.", "修正版", "수정 번역"),
        ),
    )
    two_group_request = group_review.AbsorptionGroupReviewRequest(
        group_request.schema_version,
        group_request.parent_review_request_sha256,
        group_request.parent_review_result_sha256,
        group_request.source_translation_session_id,
        group_request.parent_review_execution_session_id,
        tuple(reordered_title),
        (group_request.groups[0], second_group),
    )
    two_group_session = str(uuid.uuid4())
    two_group_decisions = tuple(
        group_review.AbsorptionGroupReviewDecision(
            group.scope.group_id, group_review.GROUP_REVIEW_KEEP,
            "Synthetic ordered group decision.")
        for group in two_group_request.groups
    )
    two_group_result = group_review.AbsorptionGroupReviewResult(
        group_review.ABSORPTION_GROUP_REVIEW_SCHEMA_VERSION,
        group_review.absorption_group_review_request_sha256(two_group_request),
        two_group_decisions,
    )
    two_group_canonical = group_review.serialize_absorption_group_review_result(
        two_group_result, two_group_request,
        review_execution_session_id=two_group_session)
    two_group_value = json.loads(two_group_canonical)
    two_group_value["decisions"].reverse()
    out_of_order_payload = json.dumps(
        two_group_value, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    two_group_task = "/tmp/stage11-p2l-group-review/" + two_group_session
    two_group_request_payload = group_review.serialize_absorption_group_review_request(
        two_group_request)
    two_group_nonce = uuid.uuid4().hex + uuid.uuid4().hex
    two_group_receipt = {
        "schema_version": 1,
        "session_id": two_group_session,
        "task_sha256": hashlib.sha256(two_group_task.encode("utf-8")).hexdigest(),
        "request_sha256": hashlib.sha256(two_group_request_payload).hexdigest(),
        "input_sha256": hashlib.sha256(two_group_request_payload).hexdigest(),
        "receipt_nonce": two_group_nonce,
        "child_outcome": "COMPLETED",
        "child_returncode": 0,
        "result_state": "PRESENT",
        "result_sha256": hashlib.sha256(out_of_order_payload).hexdigest(),
        "result_size_bytes": len(out_of_order_payload),
    }
    two_group_execution = group_review.AbsorptionGroupReviewExecutionEvidence(
        two_group_request_payload,
        out_of_order_payload,
        json.dumps(two_group_receipt, sort_keys=True, separators=(",", ":")).encode("ascii"),
        two_group_task,
        two_group_nonce,
        two_group_session,
    )
    check("group decision order must match the canonical request order", lambda:
          _raises_group_error(lambda:
              group_review.validate_absorption_group_review_execution(
                  two_group_execution, two_group_request)))

    reverse_first = StatefulAbsorptionResult(
        absorption_first.schema_version, absorption_first.dvd_id,
        absorption_first.generation_key, absorption_first.claim_token,
        absorption_first.session_id,
        tuple(StatefulCueOutput(
            cue.cue_id, None,
            "역방향 owner 번역" if index == 0 else None if index == 1
            else f"다른 번역 {index}",
            absorbed_into=(absorption_package.cues[0].cue_id if index == 1 else None),
        ) for index, cue in enumerate(absorption_package.cues)), boundary)
    reverse_request = review.build_review_request(
        preparation=absorption_preparation, package=absorption_package,
        result=reverse_first, source_quality=absorption_quality)
    reverse_actions = (
        review.REPAIR, review.KEEP,
        *((review.KEEP,) * (len(reverse_request.cues) - 2)),
    )
    reverse_review_result = review.QualityReviewResult(
        review.STATEFUL_QUALITY_REVIEW_SCHEMA_VERSION,
        review.review_request_sha256(reverse_request),
        tuple(review.QualityReviewResultCue(
            cue.cue_id, action,
            "SEMANTIC_REPAIR" if action == review.REPAIR else "DIALOGUE",
            "Synthetic owner-first group decision.",
            "修正版" if action == review.REPAIR else None,
            "역방향 그룹 수정" if action == review.REPAIR else None,
        ) for cue, action in zip(reverse_request.cues, reverse_actions, strict=True)))
    reverse_review_result = review.bind_review_execution_provenance(
        reverse_review_result, reverse_request, str(uuid.uuid4()))
    reverse_group_request = group_review.build_absorption_group_review_request(
        preparation=absorption_preparation,
        package=absorption_package,
        first_pass_result=reverse_first,
        review_request=reverse_request,
        review_result=reverse_review_result,
        source_quality=absorption_quality,
    )
    reverse_execution = group_execution(
        group_review.GROUP_REVIEW_REPAIR,
        request_value=reverse_group_request,
        replacement_ja="逆方向グループ全体の修正文",
        replacement_ko="역방향 그룹 전체의 수정 번역",
    )
    reverse_clean = clean.materialize_stateful_quality_review_clean(
        absorption_package, reverse_first, absorption_preparation,
        reverse_request, reverse_review_result,
        source_quality=absorption_quality,
        absorption_group_review_execution=reverse_execution,
        preserve_absorption=True, omit_metadata=True,
    )
    check("group scope follows the deterministic owner when it is not last", lambda:
          reverse_group_request.groups[0].scope.owner_cue_id
          == absorption_package.cues[0].cue_id
          and reverse_group_request.groups[0].scope.cue_ids
          == (absorption_package.cues[0].cue_id,
              absorption_package.cues[1].cue_id)
          and reverse_clean.cues[0].cue_id == absorption_package.cues[0].cue_id
          and reverse_clean.cues[0].original_source_index == 0
          and reverse_clean.cues[0].source_indexes == (0, 1)
          and reverse_clean.cues[0].ko == "역방향 그룹 전체의 수정 번역")

    repair_execution = group_execution(
        group_review.GROUP_REVIEW_REPAIR,
        replacement_ja="グループ全体の修正文",
        replacement_ko="흡수 그룹 전체의 수정 번역",
    )
    repair_result = group_review.validate_absorption_group_review_execution(
        repair_execution, group_request)
    repaired_group_clean = clean.materialize_stateful_quality_review_clean(
        absorption_package, absorption_first, absorption_preparation,
        absorption_request, bound_owner_repair_result,
        source_quality=absorption_quality,
        absorption_group_review_execution=repair_execution,
        preserve_absorption=True, omit_metadata=True)
    expected_group_timing = (
        min(expected_absorbed_timing[0], expected_absorbed_timing[0]),
        max(expected_absorbed_timing[1], expected_absorbed_timing[1]),
    )
    check("explicit group REPAIR applies both full-group replacements",
          lambda: repair_result.decisions[0].action == group_review.GROUP_REVIEW_REPAIR
          and repaired_group_clean.cues[0].ja == "グループ全体の修正文"
          and repaired_group_clean.cues[0].ko == "흡수 그룹 전체의 수정 번역"
          and repaired_group_clean.cues[0].review_action == review.REPAIR
          and repaired_group_clean.cues[0].cue_id == absorption_package.cues[1].cue_id
          and repaired_group_clean.cues[0].original_source_index == 1
          and repaired_group_clean.cues[0].source_indexes == (0, 1)
          and (repaired_group_clean.cues[0].start_ms,
               repaired_group_clean.cues[0].end_ms) == expected_group_timing)

    class FakeSessionDB:
        def __init__(self):
            self.rows = {}

        def get_session(self, session_id):
            return self.rows.get(session_id)

        def create_session(self, *, session_id, source, profile_name):
            self.rows[session_id] = {
                "id": session_id, "source": source,
                "profile_name": profile_name, "parent_session_id": None,
            }
            return session_id

        def get_messages(self, session_id, *, include_inactive=False):
            return []

    class FakeGroupBridge:
        def __init__(self):
            self.files = {}
            self.group_filenames = None

        def ensure_task(self, remote_task):
            self.remote_task = remote_task

        def ensure_file(self, remote_path, payload):
            self.files[remote_path] = payload

        def launch_quality_review(
            self, command, *, local_task_fd, remote_task, timeout, session_id,
            request_sha256, receipt_nonce, input_filename, result_filename,
        ):
            del local_task_fd
            self.group_filenames = (input_filename, result_filename)
            input_payload = self.files[remote_task + "/" + input_filename]
            result_payload = repair_execution.result_payload
            self.files[remote_task + "/" + result_filename] = result_payload
            return SimpleNamespace(returncode=0, execution_receipt={
                "schema_version": 1,
                "session_id": session_id,
                "task_sha256": hashlib.sha256(remote_task.encode()).hexdigest(),
                "request_sha256": request_sha256,
                "input_sha256": hashlib.sha256(input_payload).hexdigest(),
                "receipt_nonce": receipt_nonce,
                "child_outcome": "COMPLETED",
                "child_returncode": 0,
                "result_state": "PRESENT",
                "result_sha256": hashlib.sha256(result_payload).hexdigest(),
                "result_size_bytes": len(result_payload),
            })

        def read_regular(self, remote_path, *, max_bytes):
            payload = self.files[remote_path]
            assert len(payload) <= max_bytes
            return payload

    bridge = FakeGroupBridge()
    group_launcher = deployment._hybrid_launcher_factory(
        bridge,
        lambda session_id: "/tmp/stage11-p2l-group-review/" + session_id,
    )
    with tempfile.TemporaryDirectory(prefix="stage11-group-review-smoke-") as temporary:
        task_directory = Path(temporary)
        os.chmod(task_directory, 0o700)
        bridged_execution = review_runner.run_absorption_group_review(
            task_directory,
            group_request,
            review_execution_session_id=str(uuid.uuid4()),
            fresh_session_db=FakeSessionDB(),
            expected_profile_name="subtitle-translator",
            launcher=group_launcher,
        )
    bridged_result = group_review.validate_absorption_group_review_execution(
        bridged_execution, group_request)
    check("group runner reuses fresh native session, SSH bridge and receipt",
          lambda: bridge.group_filenames == (
              group_review.ABSORPTION_GROUP_REVIEW_INPUT_FILENAME,
              group_review.ABSORPTION_GROUP_REVIEW_RESULT_FILENAME)
          and bridged_result.decisions[0].action == group_review.GROUP_REVIEW_REPAIR
          and bridged_execution.review_execution_session_id
          != group_request.parent_review_execution_session_id)

    with tempfile.TemporaryDirectory(prefix="stage11-normal-group-proof-") as temporary:
        artifact_directory = Path(temporary)
        os.chmod(artifact_directory, 0o700)
        group_runner_calls = []
        persisted_execution = normal_mode._normal_group_review_execution(
            artifact_directory,
            absorption_preparation,
            absorption_first,
            absorption_request,
            bound_owner_repair_result,
            absorption_quality,
            None,
            group_review_runner=lambda request, *, staging_root: (
                group_runner_calls.append(request) or repair_execution),
            staging_root=artifact_directory,
            create_missing=True,
        )
        replayed_execution = normal_mode._normal_group_review_execution(
            artifact_directory,
            absorption_preparation,
            absorption_first,
            absorption_request,
            bound_owner_repair_result,
            absorption_quality,
            None,
            create_missing=False,
        )
    check("Normal stores and revalidates group receipt without rerunning review",
          lambda: len(group_runner_calls) == 1
          and persisted_execution == repair_execution
          and replayed_execution == repair_execution
          and normal_mode._group_review_proof_identity(replayed_execution)
          == normal_mode._group_review_proof_identity(repair_execution))
    normal_group_artifact, normal_group_playback, _ = normal_mode.normal_materialization(
        absorption_preparation,
        absorption_first,
        absorption_request,
        bound_owner_repair_result,
        absorption_quality,
        absorption_group_review_execution=replayed_execution,
    )
    check("Normal materialization passes validated group evidence into CLEAN",
          lambda: normal_group_artifact.payload is not None
          and normal_group_playback[0].cue_id == absorption_package.cues[1].cue_id
          and normal_group_playback[0].source_indexes == (0, 1)
          and normal_group_playback[0].ko == "흡수 그룹 전체의 수정 번역")

    keep_execution = group_execution(group_review.GROUP_REVIEW_KEEP)
    keep_group_clean = clean.materialize_stateful_quality_review_clean(
        absorption_package, absorption_first, absorption_preparation,
        absorption_request, bound_owner_repair_result,
        source_quality=absorption_quality,
        absorption_group_review_execution=keep_execution,
        preserve_absorption=True, omit_metadata=True)
    check("group KEEP suppresses per-cue repair and retains owner translation",
          lambda: keep_group_clean.cues[0].ko == absorption_first.cues[1].ko
          and keep_group_clean.cues[0].review_action == review.KEEP
          and keep_group_clean.cues[0].source_indexes == (0, 1))
    ambiguous_group_execution = group_execution(
        group_review.GROUP_REVIEW_AMBIGUOUS)
    ambiguous_group_clean = clean.materialize_stateful_quality_review_clean(
        absorption_package, absorption_first, absorption_preparation,
        absorption_request, bound_owner_repair_result,
        source_quality=absorption_quality,
        absorption_group_review_execution=ambiguous_group_execution,
        preserve_absorption=True, omit_metadata=True)
    check("group AMBIGUOUS preserves first-pass Korean and original owner JA",
          lambda: ambiguous_group_clean.cues[0].ko == absorption_first.cues[1].ko
          and ambiguous_group_clean.cues[0].ja
          == absorption_package.cues[1].external_ja
          and ambiguous_group_clean.cues[0].review_action == review.AMBIGUOUS)

    missing_receipt = replace(repair_execution, receipt_payload=b"")
    reject("missing native completion receipt blocks group authority", lambda:
           clean.materialize_stateful_quality_review_clean(
               absorption_package, absorption_first, absorption_preparation,
               absorption_request, bound_owner_repair_result,
               source_quality=absorption_quality,
               absorption_group_review_execution=missing_receipt,
               preserve_absorption=True, omit_metadata=True))
    mismatched_result = replace(
        repair_execution,
        result_payload=repair_execution.result_payload + b" ",
    )
    reject("result SHA mismatch against native receipt blocks group authority", lambda:
           clean.materialize_stateful_quality_review_clean(
               absorption_package, absorption_first, absorption_preparation,
               absorption_request, bound_owner_repair_result,
               source_quality=absorption_quality,
               absorption_group_review_execution=mismatched_result,
               preserve_absorption=True, omit_metadata=True))
    wrong_session = replace(
        repair_execution, review_execution_session_id=str(uuid.uuid4()))
    reject("wrong group review session blocks group authority", lambda:
           clean.materialize_stateful_quality_review_clean(
               absorption_package, absorption_first, absorption_preparation,
               absorption_request, bound_owner_repair_result,
               source_quality=absorption_quality,
               absorption_group_review_execution=wrong_session,
               preserve_absorption=True, omit_metadata=True))
    wrong_parent_result = replace(
        bound_owner_repair_result,
        cues=(replace(bound_owner_repair_result.cues[0], reason="Different review evidence."),)
        + bound_owner_repair_result.cues[1:],
    )
    other_group_request = group_review.build_absorption_group_review_request(
        preparation=absorption_preparation,
        package=absorption_package,
        first_pass_result=absorption_first,
        review_request=absorption_request,
        review_result=wrong_parent_result,
        source_quality=absorption_quality,
    )
    check("approval from a different parent review cannot be reused", lambda:
          other_group_request.groups[0].scope.group_id
          != group_request.groups[0].scope.group_id)
    check("other parent-review group result is rejected", lambda:
          _raises_group_error(lambda:
              group_review.validate_absorption_group_review_execution(
                  repair_execution, other_group_request)))
    unsupported_execution = group_execution(group_review.GROUP_REVIEW_UNSUPPORTED)
    reject("unsupported group decision cannot produce CLEAN", lambda:
           clean.materialize_stateful_quality_review_clean(
               absorption_package, absorption_first, absorption_preparation,
               absorption_request, bound_owner_repair_result,
               source_quality=absorption_quality,
               absorption_group_review_execution=unsupported_execution,
               preserve_absorption=True, omit_metadata=True))

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

    multiple_repair_actions = (
        review.REPAIR, review.REPAIR,
        *((review.KEEP,) * (len(absorption_request.cues) - 2)),
    )
    multiple_repair_result = review.QualityReviewResult(
        review.STATEFUL_QUALITY_REVIEW_SCHEMA_VERSION,
        review.review_request_sha256(absorption_request),
        tuple(review.QualityReviewResultCue(
            cue.cue_id, action,
            {review.KEEP: "DIALOGUE", review.REPAIR: "SEMANTIC_REPAIR"}[action],
            "Conflicting group repairs remain fail-closed.",
            "修正版" if action == review.REPAIR else None,
            "수정 번역" if action == review.REPAIR else None,
        ) for cue, action in zip(
            absorption_request.cues, multiple_repair_actions, strict=True)))
    reject("multiple REPAIR decisions in one absorption group rejected", lambda:
           clean.materialize_stateful_quality_review_clean(
               absorption_package, absorption_first, absorption_preparation,
               absorption_request, multiple_repair_result,
               source_quality=absorption_quality,
               preserve_absorption=True, omit_metadata=True))

    ambiguous_owner_repair_actions = (
        review.AMBIGUOUS, review.REPAIR,
        *((review.KEEP,) * (len(absorption_request.cues) - 2)),
    )
    ambiguous_owner_repair_result = review.QualityReviewResult(
        review.STATEFUL_QUALITY_REVIEW_SCHEMA_VERSION,
        review.review_request_sha256(absorption_request),
        tuple(review.QualityReviewResultCue(
            cue.cue_id, action,
            {review.KEEP: "DIALOGUE", review.REPAIR: "SEMANTIC_REPAIR",
             review.AMBIGUOUS: "AMBIGUOUS"}[action],
            "Uncertain group member cannot authorize an owner repair.",
            "修正版" if action == review.REPAIR else None,
            "수정 번역" if action == review.REPAIR else None,
        ) for cue, action in zip(
            absorption_request.cues, ambiguous_owner_repair_actions, strict=True)))
    reject_reason(
        "AMBIGUOUS member plus owner REPAIR stays blocked",
        "owner REPAIR lacks validated absorption-group review authority",
        lambda: clean.materialize_stateful_quality_review_clean(
            absorption_package, absorption_first, absorption_preparation,
            absorption_request, ambiguous_owner_repair_result,
            source_quality=absorption_quality,
            preserve_absorption=True, omit_metadata=True),
    )

    metadata_cues = list(
        absorption_application.bundle.external_ja_document.cues)
    metadata_cues[0] = replace(metadata_cues[0], text="字幕作成")
    metadata_payload = ExternalSubtitlePayload.from_bytes(
        dvd_id=absorption_bundle.dvd_id,
        candidate=absorption_bundle.external_ja_payload.candidate,
        payload=generate_korean_srt(tuple(metadata_cues)).payload,
    )
    metadata_bundle = replace(
        absorption_application.bundle,
        external_ja_payload=metadata_payload,
        external_ja_document=metadata_payload.parse(),
    )
    metadata_application = apply_alignment_acceptance(
        metadata_bundle, absorption_application.decision,
        alignment=absorption_application.alignment)
    metadata_route = replace(
        absorption_route, alignment_application=metadata_application)
    metadata_preparation = prepare_stateful_hybrid(
        metadata_route, generation_key="clean-absorption-metadata-fixture",
        claim_token=11)
    metadata_preparation, metadata_boundary = bind_stateful_absorption_preparation(
        metadata_preparation)
    metadata_package = metadata_preparation.package
    metadata_ordinary = semantic_result(metadata_package)
    metadata_first = StatefulAbsorptionResult(
        metadata_ordinary.schema_version, metadata_ordinary.dvd_id,
        metadata_ordinary.generation_key, metadata_ordinary.claim_token,
        metadata_ordinary.session_id,
        tuple(StatefulCueOutput(
            cue.cue_id, None,
            None if index == 0 else f"metadata owner translation {index}",
            absorbed_into=(metadata_package.cues[1].cue_id if index == 0 else None),
        ) for index, cue in enumerate(metadata_package.cues)), metadata_boundary)
    metadata_quality = classify_source_document(
        metadata_application.bundle.external_ja_document)
    metadata_request = review.build_review_request(
        preparation=metadata_preparation, package=metadata_package,
        result=metadata_first, source_quality=metadata_quality)
    metadata_keep = review.QualityReviewResult(
        review.STATEFUL_QUALITY_REVIEW_SCHEMA_VERSION,
        review.review_request_sha256(metadata_request),
        tuple(review.QualityReviewResultCue(
            cue.cue_id, review.KEEP, "DIALOGUE",
            "Metadata group remains fail-closed.", None, None,
        ) for cue in metadata_request.cues))
    check("metadata fixture classifies a group member", lambda:
          metadata_quality[0].action == "OMIT_METADATA")
    reject_reason(
        "partial metadata omission in an absorption group rejected",
        "metadata omission intersects a retained absorption group",
        lambda: clean.materialize_stateful_quality_review_clean(
            metadata_package, metadata_first, metadata_preparation,
            metadata_request, metadata_keep,
            source_quality=metadata_quality,
            preserve_absorption=True, omit_metadata=True),
    )

    def owner_without_korean_rejected():
        try:
            StatefulCueOutput(absorption_package.cues[1].cue_id, None, None)
        except ValueError:
            return True
        return False

    check("terminal absorption owner requires Korean translation",
          owner_without_korean_rejected)

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


def _raises_group_error(callback):
    try:
        callback()
    except group_review.AbsorptionGroupReviewError:
        return True
    return False


def _immutable(value, field_name):
    try:
        setattr(value, field_name, None)
    except FrozenInstanceError:
        return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
