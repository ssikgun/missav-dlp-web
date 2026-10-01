"""Offline CLEAN projection and detached-evidence regression; no model/I/O."""
from teddy_discovery_semantic_projection_smoke import multiline_route
from teddy_discovery_semantic_text import project_semantic_text
from teddy_discovery_stateful_hybrid import prepare_stateful_hybrid
from teddy_discovery_stateful_hybrid_smoke import semantic_result, changed
from teddy_discovery_stateful_quality_review import (
    KEEP, QualityReviewResult, QualityReviewResultCue, build_review_request,
    review_request_sha256,
)
from teddy_discovery_stateful_quality_review_clean import (
    materialize_stateful_quality_review_clean, StatefulQualityReviewCleanError,
)
from teddy_discovery_subtitle_source_quality import classify_source_document
from teddy_discovery_subtitle_v2_pipeline_smoke import accepted_hybrid_route
from teddy_discovery_hermes_v2 import HermesV2ValidationError
from teddy_discovery_subtitle_v2_pipeline import _semantic_cue_input


def main():
    for label, route in [('single', accepted_hybrid_route()),
                         ('LF', multiline_route('\n')),
                         ('CRLF', multiline_route('\r\n')),
                         ('CR', multiline_route('\r'))]:
        preparation = prepare_stateful_hybrid(route, generation_key='clean-projection', claim_token=7)
        package = preparation.package
        first = semantic_result(package)
        bundle = route.alignment_application.bundle
        document = bundle.external_ja_document
        source_quality = classify_source_document(document)
        before = (bundle.external_ja_payload.payload,
                  tuple((c.start_ms, c.end_ms, c.text) for c in document.cues), package, first)
        request = build_review_request(preparation=preparation, package=package,
                                       result=first, source_quality=source_quality)
        result = QualityReviewResult(request.schema_version, review_request_sha256(request),
            tuple(QualityReviewResultCue(c.cue_id, KEEP, 'DIALOGUE', 'Evidence retained.', None, None)
                  for c in request.cues))
        originals = dict(package=package, first_pass_result=first, preparation=preparation,
                         review_request=request, review_result=result, source_quality=source_quality)
        clean = materialize_stateful_quality_review_clean(**originals)
        assert len(clean.cues) == len(document.cues)
        assert before == (bundle.external_ja_payload.payload,
                          tuple((c.start_ms, c.end_ms, c.text) for c in document.cues), package, first)
        assert all(c.ja == project_semantic_text(e.text)
                   for c,e in zip(clean.cues, document.cues, strict=True))
        assert clean.source_indexes == tuple(range(len(document.cues)))
        if label != 'single':
            assert all('\n' in e.text for e in document.cues)

        def tampered(obj, field, value):
            return changed(obj, cues=(changed(obj.cues[0], **{field:value}),) + obj.cues[1:])

        cases = [
            dict(package=tampered(package, 'external_ja', 'detached')),
            dict(package=tampered(package, 'cue_id', 'ja-999999')),
            dict(first_pass_result=tampered(first, 'cue_id', 'ja-999999')),
            dict(review_request=tampered(request, 'cue_id', 'ja-999999')),
            dict(review_request=tampered(request, 'source_index', 999)),
            dict(review_result=tampered(result, 'cue_id', 'ja-999999')),
            dict(review_request=tampered(request, 'external_ja', 'detached')),
            dict(review_request=tampered(request, 'accepted_stt_ja', 'detached')),
            dict(review_request=tampered(request, 'first_pass_repaired_ja', 'detached')),
            dict(review_request=tampered(request, 'first_pass_ko', 'detached')),
        ]
        for field,value in [('request_cue_id','ja-999999'), ('source_index',999),
                            ('external_ja_identity',preparation.semantic_bindings[1].external_ja_identity)]:
            binding = changed(preparation.semantic_bindings[0], **{field:value})
            cases.append(dict(preparation=changed(preparation,
                semantic_bindings=(binding,) + preparation.semantic_bindings[1:])))
        for edits in cases:
            try:
                materialize_stateful_quality_review_clean(**dict(originals, **edits))
            except StatefulQualityReviewCleanError:
                pass
            else:
                raise AssertionError('detached CLEAN evidence accepted')
        print('CLEAN_PROJECTION_'+label+'_AND_DETACHED_EVIDENCE=PASS')
    for code in (*range(32), *range(127,160)):
        if code in (10,13): continue
        try:
            _semantic_cue_input(cue_id='ja-000001',external_ja='a'+chr(code)+'b',
                                stt_ja=None,en=None,before_context=(),after_context=())
        except HermesV2ValidationError:
            pass
        else:
            raise AssertionError('unsafe control accepted')
    print('CLEAN_UNSAFE_CONTROLS_REJECTED=PASS')


if __name__ == '__main__':
    main()
