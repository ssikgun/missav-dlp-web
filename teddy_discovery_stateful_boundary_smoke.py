"""Offline boundary ownership, identity, private staging and query regression."""

from contextlib import redirect_stdout
from dataclasses import asdict, fields, replace
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import teddy_discovery_stateful_boundary as boundary
import teddy_discovery_stateful_live_runner as native
import teddy_discovery_stage11_controller as controller
from teddy_discovery_stage11_live_adapters import build_first_pass_adapter
from teddy_discovery_stage11_deployment import _HybridOriginalRegistry
from teddy_discovery_stateful_controller import build_stateful_part_query
from teddy_discovery_stateful_hybrid import prepare_stateful_hybrid
from teddy_discovery_stateful_hybrid_smoke import changed, extended_route, semantic_result
from teddy_discovery_stateful_parts import (
    StatefulSemanticPart, build_stateful_part_plan, serialize_stateful_part,
)
from teddy_discovery_stateful_policy import (
    DEFAULT_STATEFUL_SEMANTIC_POLICY, STATEFUL_SEMANTIC_POLICY_16,
    STATEFUL_SEMANTIC_POLICY_128, bind_stateful_policy_generation_key,
)
from teddy_discovery_stateful_translator import (
    bind_stateful_model_input_generation_key, parse_stateful_package,
    parse_stateful_result, serialize_stateful_package, serialize_stateful_model_input,
    serialize_stateful_result, stateful_boundary_digest_from_generation_key,
    stateful_session_id_for_package,
)
from teddy_discovery_hermes_v2 import HermesV2CueInput
import teddy_discovery_stage11_controller_smoke as controller_fixture
import teddy_discovery_subtitle_v2_pipeline_smoke as fixture


def prepared_three(*, gap=0, intercept=100.0, scale=1.25, url="https://source.example.test/boundary.srt"):
    """Three accepted source cues, with a real affine proof and production projection."""
    original = fixture.accepted_hybrid_route()
    intervals = ((900, 1900), (1800, 2300), (2300 + gap, 3300 + gap))
    payload = fixture.external_payload(url, "ja", tuple(
        (start, end, "source " + str(index)) for index, (start, end) in enumerate(intervals)))
    provisional = fixture.affine_fixture(scale, intercept)
    segments = tuple(fixture.ASRSegment(
        fixture.project_affine_timestamp_ms(provisional, start),
        fixture.project_affine_timestamp_ms(provisional, end), "speech " + str(index),
    ) for index, (start, end) in enumerate(intervals))
    residuals = tuple(fixture.AffineAnchorResidual(
        fixture.HybridCueIdentity.for_external_ja(index),
        fixture.HybridCueIdentity.for_asr_segment(index), start + end,
        segment.start_ms + segment.end_ms,
        scale * (start + end) / 2 + intercept,
        (segment.start_ms + segment.end_ms) / 2 - (scale * (start + end) / 2 + intercept),
        abs((segment.start_ms + segment.end_ms) / 2 - (scale * (start + end) / 2 + intercept)), True,
    ) for index, ((start, end), segment) in enumerate(zip(intervals, segments)))
    median = sorted(r.absolute_residual_ms for r in residuals)[1]
    alignment = replace(provisional, residuals=residuals, median_absolute_residual_ms=median)
    old_bundle = original.alignment_application.bundle
    bundle = fixture.HybridEvidenceBundle.from_external_ja_and_asr(
        dvd_id=old_bundle.dvd_id, external_ja_payload=payload, external_ja_document=payload.parse(),
        asr_result=replace(old_bundle.asr_result, segments=segments), alignment=old_bundle.alignment,
    )
    decision = replace(original.alignment_application.decision, scale=scale,
        median_absolute_residual_ms=median,
        external_evidence_span_ms=(residuals[-1].external_midpoint_x2 - residuals[0].external_midpoint_x2) / 2,
        asr_evidence_span_ms=(residuals[-1].asr_midpoint_x2 - residuals[0].asr_midpoint_x2) / 2)
    app = fixture.apply_alignment_acceptance(bundle, decision, alignment=alignment)
    return prepare_stateful_hybrid(replace(original, alignment_application=app),
        generation_key=bind_stateful_policy_generation_key("boundary-fixture", DEFAULT_STATEFUL_SEMANTIC_POLICY),
        claim_token=7)


class BoundarySmoke(unittest.TestCase):
    def setUp(self):
        self.preparation = prepared_three()
        self.bound, self.evidence = boundary.bind_stateful_boundary_preparation(self.preparation)
        self.package = self.bound.package
        self.wire = boundary.serialize_stateful_boundary_evidence(self.evidence)
        for target in ("subprocess.run", "subprocess.Popen", "socket.socket"):
            tripwire = patch(target, side_effect=AssertionError("live process/network forbidden"))
            tripwire.start()
            self.addCleanup(tripwire.stop)

    def test_exact_projection_overlap_touching_and_gap(self):
        pairs = self.evidence.pairs
        self.assertEqual([p.relation for p in pairs], ["OVERLAP", "TOUCHING"])
        self.assertEqual([p.gap_ms for p in pairs], [-125, 0])
        app = self.preparation.route_decision.alignment_application
        for pair in pairs:
            cues = app.bundle.external_ja_document.cues
            self.assertEqual(pair.gap_ms,
                fixture.project_affine_timestamp_ms(app.alignment, cues[pair.right_source_index].start_ms)
                - fixture.project_affine_timestamp_ms(app.alignment, cues[pair.left_source_index].end_ms))
        positive = boundary.build_stateful_boundary_evidence(prepared_three(gap=1))
        self.assertEqual(positive.pairs[1].relation, "GAP")
        self.assertGreater(positive.pairs[1].gap_ms, 0)

    def test_canonical_roundtrip_and_frozen_pair(self):
        self.assertEqual(boundary.serialize_stateful_boundary_evidence(self.evidence), self.wire)
        self.assertEqual(boundary.parse_stateful_boundary_evidence(self.wire, self.package), self.evidence)
        self.assertEqual(boundary.build_stateful_boundary_evidence(self.bound), self.evidence)
        repeated, evidence = boundary.bind_stateful_boundary_preparation(self.bound)
        self.assertEqual(repeated.package, self.package)
        self.assertEqual(boundary.serialize_stateful_boundary_evidence(evidence), self.wire)
        with self.assertRaises(AttributeError):
            self.evidence.pairs[0].gap_ms = 9

    def test_reordered_package_wrong_cue_and_wrong_source_index_rejected(self):
        package = self.preparation.package
        mutations = (
            changed(self.preparation, package=replace(package, cues=package.cues[::-1])),
            changed(self.preparation, package=replace(package, cues=(
                replace(package.cues[0], cue_id="wrong-cue"),) + package.cues[1:])),
            changed(self.preparation, semantic_bindings=(
                changed(self.preparation.semantic_bindings[0], source_index=1),)
                + self.preparation.semantic_bindings[1:]),
        )
        for mutation in mutations:
            with self.subTest(mutation=type(mutation).__name__), self.assertRaises(ValueError):
                boundary.build_stateful_boundary_evidence(mutation)

    def test_detached_document_and_alignment_rejected(self):
        app = self.preparation.route_decision.alignment_application
        detached = (
            changed(app, alignment=changed(app.alignment, intercept_ms=999.0)),
            changed(app, bundle=changed(app.bundle, external_ja_document=changed(
                app.bundle.external_ja_document, cues=app.bundle.external_ja_document.cues[::-1]))),
        )
        for application in detached:
            with self.assertRaises(boundary.StatefulBoundaryValidationError):
                boundary.build_stateful_boundary_evidence(changed(self.preparation,
                    route_decision=changed(self.preparation.route_decision, alignment_application=application)))

    def test_projection_rejects_boolean_float_negative_and_inverted_interval(self):
        for values in ((True, 2000), (1000.0, 2000), (-1, 2000), (2000, 1000)):
            with patch.object(boundary, "project_affine_timestamp_ms", side_effect=values), \
                 self.assertRaises(boundary.StatefulBoundaryValidationError):
                boundary.build_stateful_boundary_evidence(self.preparation)

    def test_stale_sidecar_cannot_use_existing_identity(self):
        other, evidence = boundary.bind_stateful_boundary_preparation(prepared_three(intercept=200.0))
        self.assertEqual(self.package.cues, other.package.cues)
        self.assertNotEqual(boundary.serialize_stateful_boundary_evidence(evidence), self.wire)
        self.assertNotEqual(stateful_session_id_for_package(other.package), stateful_session_id_for_package(self.package))
        self.assertNotEqual(serialize_stateful_model_input(other.package), serialize_stateful_model_input(self.package))
        with self.assertRaises(ValueError):
            boundary.validate_stateful_boundary_evidence(evidence, self.package)
        with self.assertRaises(ValueError):
            bind_stateful_model_input_generation_key(self.package.generation_key,
                boundary_evidence_sha256=hashlib.sha256(boundary.serialize_stateful_boundary_evidence(evidence)).hexdigest())

    def test_source_origin_changes_identity(self):
        other, evidence = boundary.bind_stateful_boundary_preparation(prepared_three(url="https://other.example.test/source.srt"))
        self.assertEqual(self.evidence.source_sha256, evidence.source_sha256)
        self.assertNotEqual(self.evidence.source_identity_sha256, evidence.source_identity_sha256)
        self.assertNotEqual(stateful_session_id_for_package(self.package), stateful_session_id_for_package(other.package))

    def test_bound_identity_requires_sidecar(self):
        self.assertEqual(stateful_boundary_digest_from_generation_key(self.package.generation_key), hashlib.sha256(self.wire).hexdigest())
        with self.assertRaises(ValueError):
            boundary.validate_stateful_boundary_evidence(None, self.package)
        with self.assertRaises(ValueError):
            build_stateful_part_query(self.package, serialize_stateful_model_input(self.package), 1)

    def test_binding_preserves_legacy_and_candidate_policy_suffixes(self):
        for policy in (STATEFUL_SEMANTIC_POLICY_16, DEFAULT_STATEFUL_SEMANTIC_POLICY,
                       STATEFUL_SEMANTIC_POLICY_128):
            package = replace(self.preparation.package,
                generation_key=bind_stateful_policy_generation_key("policy-fixture", policy))
            bound, evidence = boundary.bind_stateful_boundary_preparation(
                replace(self.preparation, package=package))
            self.assertLessEqual(len(bound.package.generation_key), 256)
            plan = build_stateful_part_plan(bound.package, serialize_stateful_model_input(bound.package),
                                            semantic_policy=policy)
            self.assertEqual(plan.policy_id, policy.policy_id)
            boundary.validate_stateful_boundary_evidence(evidence, bound.package, preparation=bound)
        production_base = "stage11-hybrid-hybrid-suspect-targeted-v1-" + "a" * 64
        key = bind_stateful_model_input_generation_key(bind_stateful_policy_generation_key(
            production_base, STATEFUL_SEMANTIC_POLICY_128), boundary_evidence_sha256="b" * 64)
        self.assertLessEqual(len(key), 256)
        self.assertEqual(stateful_boundary_digest_from_generation_key(key), "b" * 64)

    def test_malformed_boundary_binding_rejected(self):
        marker = "+boundary1="
        normal = bind_stateful_model_input_generation_key("identity-fixture")
        for key in ("identity-fixture" + marker + "a" * 64,
                    normal + marker + "a" * 63, normal + marker + "g" * 64,
                    normal + marker + "a" * 64 + marker + "b" * 64,
                    "prefix" + marker + "a" * 64 + normal):
            with self.subTest(key=key), self.assertRaises(ValueError):
                stateful_boundary_digest_from_generation_key(key)

    def test_tamper_version_fields_count_control_and_noncanonical_rejected(self):
        obj = json.loads(self.wire)
        for data in (
            dict(obj, schema_version=2), dict(obj, schema_version=True), dict(obj, extra=1),
            dict(obj, pairs=obj["pairs"][::-1]), dict(obj, pairs=obj["pairs"][:1]),
            dict(obj, dvd_id="control\x00data"), dict(obj, dvd_id="control\x80data"),
            dict(obj, pairs=[dict(obj["pairs"][0], gap_ms=1, relation="GAP")] + obj["pairs"][1:]),
            dict(obj, pairs=[dict(obj["pairs"][0], right_source_index=2)] + obj["pairs"][1:]),
            dict(obj, pairs=[dict(obj["pairs"][0], gap_ms=True)] + obj["pairs"][1:]),
            dict(obj, pairs=[dict(obj["pairs"][0], raw_start_ms=1)] + obj["pairs"][1:]),
        ):
            with self.subTest(fields=set(data)), self.assertRaises(ValueError):
                boundary.parse_stateful_boundary_evidence(boundary._json(data), self.package)
        for payload in (self.wire + b"\n", b'{"schema_version":1,' + self.wire[1:], self.wire[:-1]):
            with self.assertRaises(ValueError):
                boundary.parse_stateful_boundary_evidence(payload, self.package)
        with patch.object(boundary, "STATEFUL_BOUNDARY_MAX_BYTES", 1), self.assertRaises(ValueError):
            boundary.parse_stateful_boundary_evidence(self.wire, self.package)

    def test_schema_serialization_and_result_contract_unchanged(self):
        names = ("cue_id", "external_ja", "stt_ja", "en", "before_context", "after_context")
        self.assertEqual(tuple(f.name for f in fields(HermesV2CueInput)), names)
        raw = serialize_stateful_package(self.preparation.package)
        self.assertEqual(serialize_stateful_package(parse_stateful_package(raw)), raw)
        self.assertEqual(json.loads(raw)["cues"], json.loads(serialize_stateful_package(self.package))["cues"])
        self.assertEqual(set(json.loads(raw)), {"schema_version", "dvd_id", "generation_key", "claim_token", "cues"})
        self.assertTrue(all(set(cue) == set(names) for cue in json.loads(raw)["cues"]))
        result = semantic_result(self.package)
        self.assertEqual(parse_stateful_result(serialize_stateful_result(result), self.package), result)
        self.assertEqual(DEFAULT_STATEFUL_SEMANTIC_POLICY.max_cues_per_part, 64)

    def test_private_staging_readback_and_reject_unsafe_files(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            root.chmod(0o700)
            path = boundary.stage_stateful_boundary_evidence(root, self.evidence, self.package)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(path.read_bytes(), self.wire)
            self.assertEqual(boundary.stage_stateful_boundary_evidence(root, self.evidence, self.package), path)
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                boundary.read_stateful_boundary_evidence(path, self.package)
            path.unlink()
            path.symlink_to(root / "missing")
            with self.assertRaises(OSError):
                boundary.read_stateful_boundary_evidence(path, self.package)
            path.unlink()
            os.mkfifo(path, 0o600)
            with self.assertRaises(ValueError):
                boundary.read_stateful_boundary_evidence(path, self.package)

    def test_part_internal_previous_next_and_unrelated_filtering(self):
        preparation = prepare_stateful_hybrid(extended_route(140),
            generation_key=bind_stateful_policy_generation_key("cross-part", DEFAULT_STATEFUL_SEMANTIC_POLICY), claim_token=7)
        bound, evidence = boundary.bind_stateful_boundary_preparation(preparation)
        query = build_stateful_part_query(bound.package, serialize_stateful_model_input(bound.package), 2,
                                          boundary_evidence=evidence)
        pairs = json.loads(query.split("ADJACENT_BOUNDARY_EVIDENCE_V1=", 1)[1].split("\n", 1)[0])
        self.assertEqual([p["left_source_index"] for p in pairs], list(range(63, 128)))
        self.assertEqual(pairs[0]["right_cue_id"], bound.package.cues[64].cue_id)
        self.assertEqual(pairs[-1]["left_cue_id"], bound.package.cues[127].cue_id)
        self.assertNotIn(asdict(evidence.pairs[0]), pairs)
        self.assertNotIn(asdict(evidence.pairs[128]), pairs)
        for term in ("TOUCHING is not proof", "GAP is not proof", "auxiliary evidence",
                     "negation", "particles and endings", "Do not steal", "conservatively"):
            self.assertIn(term, query)

    def test_existing_optional_caller_and_default_query_unchanged(self):
        package = self.preparation.package
        wire = serialize_stateful_model_input(package)
        query = build_stateful_part_query(package, wire, 1)
        self.assertEqual(query, build_stateful_part_query(package, wire, 1, boundary_evidence=None))
        self.assertEqual(hashlib.sha256(query.encode()).hexdigest(),
            "89e96e32d23fa573e876cbe834c4f080d2fab9edba70ad8229a12b81c5a0da68")
        self.assertNotIn("ADJACENT_BOUNDARY_EVIDENCE", query)
        observed = []
        def legacy(package, *, route, staging_root):
            observed.append(route)
            return semantic_result(package)
        self.assertEqual(controller._run_first_pass(legacy, package, route="HYBRID", staging_root=Path("/offline")), semantic_result(package))
        self.assertEqual(observed, ["HYBRID"])

    def test_controller_hybrid_and_asr_routing(self):
        class Runtime(controller_fixture.FakeRuntime):
            def first_pass(self, package, **kwargs):
                self.boundary_argument = kwargs.get("boundary_evidence")
                return super().first_pass(package, **kwargs)
        for external, route in ((None, "ASR_ONLY"), (fixture.ACCEPT_HYBRID, "HYBRID")):
            with tempfile.TemporaryDirectory() as raw, redirect_stdout(io.StringIO()):
                artifacts, staging = controller_fixture._roots(Path(raw))
                runtime = Runtime(fixture.asr_result(), external)
                result = controller_fixture._run(artifacts, staging, runtime, targeted_runner=False)
                self.assertEqual(result.route, route)
                if route == "ASR_ONLY":
                    self.assertIsNone(runtime.boundary_argument)
                    self.assertFalse(list(staging.rglob(boundary.STATEFUL_BOUNDARY_FILENAME)))
                else:
                    self.assertIsNotNone(runtime.boundary_argument)
                    boundary.validate_stateful_boundary_evidence(runtime.boundary_argument, runtime.last_packages[route])

    def test_deployment_wrapper_preserves_optional_evidence(self):
        observed = []
        def first(package, **kwargs):
            observed.append(kwargs.get("boundary_evidence"))
            return semantic_result(package)
        wrapped = _HybridOriginalRegistry().capture_first_pass(first)
        wrapped(self.package, route="HYBRID", staging_root=Path("/offline"), boundary_evidence=self.evidence)
        self.assertEqual(observed, [self.evidence])

    def test_adapter_to_native_to_query_offline(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            root.chmod(0o700)
            queries = []
            plan = build_stateful_part_plan(self.package, serialize_stateful_model_input(self.package))
            pending = StatefulSemanticPart(
                1, plan.session_id, plan.input_sha256, 1, plan.parts[0].first_cue_id,
                plan.parts[0].last_cue_id, semantic_result(self.package).cues)
            def invoke(**kwargs):
                queries.append(kwargs["query"])
            def prepare(package, paths, *, route):
                self.assertEqual(route, "HYBRID")
                self.assertEqual(boundary.read_stateful_boundary_evidence(
                    paths.task_directory / boundary.STATEFUL_BOUNDARY_FILENAME, package), self.evidence)
                return "/offline/task"
            adapter = build_first_pass_adapter(remote="offline", ssh_key="/offline/key", known_hosts="/offline/hosts",
                prepare_remote=prepare, native_run=native.run)
            with patch.object(native, "_remote_input_sha256", return_value=plan.input_sha256), \
                 patch.object(native, "_remote_pending_status", return_value=False), \
                 patch.object(native, "_invoke_hermes_part", side_effect=invoke), \
                 patch.object(native, "_read_remote_regular_file", return_value=serialize_stateful_part(pending)), \
                 redirect_stdout(io.StringIO()):
                result = adapter(self.package, route="HYBRID", staging_root=root, boundary_evidence=self.evidence)
                self.assertEqual(result, semantic_result(self.package))
                self.assertEqual(len(queries), 1)
                self.assertIn("ADJACENT_BOUNDARY_EVIDENCE_V1=", queries[0])
                # Completed result reuse must retain and revalidate the sidecar.
                again = adapter(self.package, route="HYBRID", staging_root=root, boundary_evidence=self.evidence)
                self.assertEqual(again, result)
                self.assertEqual(len(queries), 1)
                path = root / plan.session_id / boundary.STATEFUL_BOUNDARY_FILENAME
                path.write_bytes(self.wire + b"\n")
                with self.assertRaises(ValueError):
                    adapter(self.package, route="HYBRID", staging_root=root, boundary_evidence=self.evidence)

    def test_native_missing_or_modified_sidecar_fails_before_transport(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            root.chmod(0o700)
            model = root / "stage11-semantic-input.json"
            original = root / "stage11-semantic-raw-input.json"
            model.write_bytes(serialize_stateful_model_input(self.package))
            original.write_bytes(serialize_stateful_package(self.package))
            args = native.build_parser().parse_args([
                "--package", str(model), "--raw-package", str(original), "--task-directory", str(root),
                "--final-result", str(root / "stage11-semantic-result.json"), "--remote", "offline",
                "--remote-task", "/offline/task", "--ssh-key", "/offline/key", "--known-hosts", "/offline/hosts",
            ])
            with patch.object(native, "_remote_input_sha256", side_effect=AssertionError("transport forbidden")):
                with self.assertRaises(ValueError):
                    native.run(args)
                path = boundary.stage_stateful_boundary_evidence(root, self.evidence, self.package)
                args.boundary_evidence = str(path)
                path.write_bytes(self.wire + b"\n")
                with self.assertRaises(ValueError):
                    native.run(args)

    def test_asr_route_cannot_receive_hybrid_boundary_evidence(self):
        def first(package, **kwargs):
            raise AssertionError("ASR boundary evidence must fail before runner")
        with self.assertRaises(controller.Stage11ControllerValidationError):
            controller._run_first_pass(first, self.package, route="ASR_ONLY", staging_root=Path("/offline"),
                                       boundary_evidence=self.evidence)


if __name__ == "__main__":
    unittest.main(verbosity=2)
