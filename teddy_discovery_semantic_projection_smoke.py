"""Offline semantic projection, authoritative proof and diagnostic regression."""
from dataclasses import replace
from pathlib import Path
import tempfile
from unittest.mock import patch

import teddy_discovery_stage11_controller_smoke as controller_fixture
import teddy_discovery_subtitle_v2_pipeline_smoke as fixture
from teddy_discovery_hermes_v2 import HermesV2ValidationError
from teddy_discovery_hybrid_evidence import HybridNeighborReference
from teddy_discovery_semantic_text import project_semantic_text
from teddy_discovery_stateful_hybrid import (
    prepare_stateful_hybrid, materialize_stateful_hybrid_srt,
    StatefulHybridValidationError,
)
from teddy_discovery_stateful_hybrid_smoke import semantic_result
from teddy_discovery_subtitle_v2_pipeline import _semantic_cue_input, _build_hybrid_plan


def multiline_route():
    route = fixture.accepted_hybrid_route()
    bundle = route.alignment_application.bundle
    payloads = {}
    for language, document in (('ja', bundle.external_ja_document),
                               ('en', bundle.external_en_document)):
        payloads[language] = fixture.external_payload(
            'https://source.example.test/' + language + '.srt', language,
            tuple((cue.start_ms, cue.end_ms, cue.text + '\nsecond line')
                  for cue in document.cues),
        )
    bundle = replace(
        bundle,
        external_ja_payload=payloads['ja'], external_ja_document=payloads['ja'].parse(),
        external_en_payload=payloads['en'], external_en_document=payloads['en'].parse(),
        cue_evidence=tuple(replace(
            evidence,
            before_context=(HybridNeighborReference('external_ja', 0),),
            after_context=(HybridNeighborReference('external_en', 0),),
        ) for evidence in bundle.cue_evidence),
    )
    return replace(route, alignment_application=replace(route.alignment_application, bundle=bundle))


def main():
    for raw, expected in (
        ('single  line ', 'single  line '),
        ('a\r\nb', 'a b'), ('a\rb', 'a b'), ('a\nb', 'a b'),
        ('a\r\n\r\nb', 'a  b'), ('a\n\r\r\nb', 'a   b'),
    ):
        assert project_semantic_text(raw) == expected
    assert project_semantic_text(None) is None
    fields = dict(cue_id='ja-000001', external_ja='source', stt_ja='speech',
                  en='support', before_context=('before',), after_context=('after',))
    original = _semantic_cue_input(**fields)
    for field in ('external_ja', 'stt_ja', 'en', 'before_context', 'after_context'):
        value = ('first\r\nsecond\rthird\nfourth',) if field.endswith('context') else 'first\r\nsecond\rthird\nfourth'
        projected = _semantic_cue_input(**{**fields, field: value})
        expected = ('first second third fourth',) if field.endswith('context') else 'first second third fourth'
        assert getattr(projected, field) == expected
        assert original == _semantic_cue_input(**fields)
        for number in (*range(32), *range(127, 160)):
            if number in (10, 13):
                continue
            unsafe = 'a' + chr(number) + 'b'
            assert project_semantic_text(unsafe) == unsafe
            value = (unsafe,) if field.endswith('context') else unsafe
            try:
                _semantic_cue_input(**{**fields, field: value})
            except HermesV2ValidationError:
                pass
            else:
                raise AssertionError('unsafe control admitted')
    print('PASS=CR_LF_projection_all_fields_and_unsafe_control_rejection')

    route = multiline_route()
    bundle = route.alignment_application.bundle
    before = (bundle.external_ja_payload.payload, bundle.external_en_payload.payload,
              bundle.external_ja_document, bundle.external_en_document, bundle.asr_result)
    kwargs = dict(generation_key='semantic-projection-smoke', claim_token=7)
    prepared = prepare_stateful_hybrid(route, **kwargs)
    prepared.__post_init__()
    plan = _build_hybrid_plan(route, targeted_bindings=())
    assert plan.hermes_request.cues == prepared.package.cues
    for cue, source in zip(prepared.package.cues, bundle.external_ja_document.cues, strict=True):
        assert cue.external_ja == source.text.replace('\n', ' ')
        assert '\n' in source.text
        assert cue.before_context == (bundle.external_ja_document.cues[0].text.replace('\n', ' '),)
        assert cue.after_context == (bundle.external_en_document.cues[0].text.replace('\n', ' '),)
        assert cue.en == bundle.external_en_document.cues[0].text.replace('\n', ' ')
    baseline = prepare_stateful_hybrid(fixture.accepted_hybrid_route(), **kwargs)
    assert prepared.semantic_bindings == baseline.semantic_bindings
    assert prepared.route_decision == route
    assert before == (bundle.external_ja_payload.payload, bundle.external_en_payload.payload,
                      bundle.external_ja_document, bundle.external_en_document, bundle.asr_result)
    assert prepared.route_decision.alignment_application.alignment == route.alignment_application.alignment
    final = materialize_stateful_hybrid_srt(prepared.package, semantic_result(prepared.package), route, prepared)
    baseline_final = materialize_stateful_hybrid_srt(baseline.package, semantic_result(baseline.package), baseline.route_decision, baseline)
    assert final == baseline_final
    try:
        replace(prepared, package=replace(prepared.package, cues=(
            replace(prepared.package.cues[0], external_ja='detached'),
        ) + prepared.package.cues[1:]))
    except StatefulHybridValidationError:
        pass
    else:
        raise AssertionError('detached projection accepted')
    print('PASS=authoritative_proof_identity_timing_and_stateful_plan_validation')

    controller = controller_fixture.controller
    for symbol, cause, expected in (
        ('prepare_stateful_hybrid', HermesV2ValidationError('unsafe semantic evidence'), 'semantic preparation/evidence'),
        ('prepare_stateful_hybrid', StatefulHybridValidationError('detached proof'), 'semantic preparation/evidence'),
        ('bind_stateful_policy_generation_key', ValueError('invalid identity'), 'identity binding'),
        ('bind_stateful_model_input_generation_key', ValueError('invalid model-input identity'), 'identity binding'),
    ):
        with tempfile.TemporaryDirectory() as raw:
            artifact_root, staging_root = controller_fixture._roots(Path(raw))
            runtime = controller_fixture.FakeRuntime(controller_fixture.fixture.asr_result(), external='ACCEPT_HYBRID')
            with patch.object(controller, symbol, side_effect=cause):
                try:
                    controller_fixture._run(artifact_root, staging_root, runtime)
                except controller.Stage11ControllerValidationError as error:
                    assert expected in str(error)
                    assert error.__cause__ is cause
                    if symbol == 'prepare_stateful_hybrid':
                        assert 'semantic policy' not in str(error)
                else:
                    raise AssertionError('invalid preparation accepted')
            assert runtime.first_pass_calls == 0
            assert not tuple(staging_root.iterdir())
    print('PASS=controller_diagnostic_separation_and_cause_chain')


if __name__ == '__main__':
    main()
