"""Synthetic in-memory full-window evidence checks; no live model or file output."""
from dataclasses import replace
import inspect
import re
from unittest.mock import patch

import teddy_discovery_stateful_quality_review as review
import teddy_discovery_stateful_quality_review_runner as runner
import teddy_discovery_subtitle_v2_pipeline_smoke as fixture
from teddy_discovery_asr import ASRSegment, REMOTE_GPU_LARGE_V3_RUNTIME_IDENTITY
from teddy_discovery_stateful_hybrid import prepare_stateful_hybrid
from teddy_discovery_stateful_hybrid_smoke import changed, semantic_result
from teddy_discovery_stateful_translator import serialize_stateful_package, serialize_stateful_result
from teddy_discovery_targeted_asr_artifact import (
    TargetedASRArtifact, parse_targeted_asr_artifact_bytes, serialize_targeted_asr_artifact,
)
from teddy_discovery_targeted_hybrid_evidence import TargetedASRWindowEvidence
from teddy_discovery_subtitle_source_quality import classify_source_document, KEEP, OMIT_METADATA


def main():
    passed = failed = 0

    def check(name, callback):
        nonlocal passed, failed
        try:
            assert callback()
        except Exception as error:
            failed += 1
            print(f'FAIL {name}: {type(error).__name__}: {error}')
        else:
            passed += 1
            print('PASS ' + name)

    def reject(name, callback):
        def rejected():
            try:
                callback()
            except review.QualityReviewError:
                return True
            return False
        check(name, rejected)

    # Adapt only synthetic source input, retaining the native evidence builder.
    original_payload = fixture.external_payload
    def metadata_payload(url, language, cues):
        if language == 'ja':
            cues = ((cues[0][0], cues[0][1], 'FixtureTool | v3.2'),) + cues[1:]
        return original_payload(url, language, cues)
    with patch.object(fixture, 'external_payload', metadata_payload):
        route = fixture.accepted_hybrid_route()
    prepared = prepare_stateful_hybrid(route, generation_key='full-window-fixture', claim_token=9)
    package = prepared.package
    first = semantic_result(package)
    bundle = route.alignment_application.bundle
    hints = classify_source_document(bundle.external_ja_document)
    originals = dict(preparation=prepared, package=package, result=first, source_quality=hints)
    ids = tuple(c.cue_id for c in package.cues)
    snapshot = bundle.asr_result.source_snapshot
    before = (serialize_stateful_package(package), serialize_stateful_result(first), prepared.semantic_bindings)

    def window(cue_ids, texts, start=0):
        return TargetedASRWindowEvidence(snapshot, start, start + 100,
            cue_ids, tuple(ASRSegment(start + i, start + i + 1, text)
                           for i, text in enumerate(texts)))

    def artifact(windows):
        return TargetedASRArtifact(snapshot, REMOTE_GPU_LARGE_V3_RUNTIME_IDENTITY,
                                   'context-smoke', windows)

    def context(value, preparation=prepared):
        return review.build_full_window_raw_asr_context(value, preparation=preparation)

    texts = ('spoken first', 'spoken second', 'spoken first', 'spoken  second')
    value = artifact((window(ids[:2], texts), window(ids[2:], ('other window',), 50)))
    wire = serialize_targeted_asr_artifact(value)
    parsed = parse_targeted_asr_artifact_bytes(wire)
    contexts = context(parsed)
    full_text = '\n'.join(texts)
    request = review.build_review_request(**originals, raw_asr_context=contexts)
    request_wire = review.serialize_review_request(request)
    check('ordered segment preservation', lambda: contexts[ids[0]] == (full_text,))
    check('exact duplicates retained without normalization', lambda:
          contexts[ids[0]][0].split('\n') == list(texts))
    check('full window attached to every mapped cue', lambda:
          contexts[ids[0]] == contexts[ids[1]] and contexts[ids[2]] == contexts[ids[3]]
          and contexts[ids[0]] != contexts[ids[2]])
    check('non-suspect KEEP receives context', lambda:
          hints[1].action == KEEP and request.cues[1].raw_asr_context == (full_text,))
    check('metadata receives neighboring speech without accepted STT rewrite', lambda:
          hints[0].action == OMIT_METADATA and request.cues[0].raw_asr_context == (full_text,)
          and request.cues[0].accepted_stt_ja == package.cues[0].stt_ja
          and request.cues[0].external_ja == package.cues[0].external_ja)
    check('one-item case', lambda: all(len(items) == 1 for items in contexts.values()))
    check('overlapping time windows with unique IDs allowed', lambda: context(value) == contexts)
    check('deterministic source order', lambda: tuple(contexts) == ids)
    check('deterministic output and native artifact bytes', lambda:
          context(value) == context(parsed) and serialize_targeted_asr_artifact(parsed) == wire)
    check('deterministic review serialization input', lambda:
          review.serialize_review_request(review.build_review_request(
              **originals, raw_asr_context=context(value))) == request_wire)
    check('existing request parser accepts helper mapping', lambda:
          review.parse_review_request(request_wire, **originals, raw_asr_context=contexts) == request)
    check('cue order and source indexes unchanged', lambda:
          tuple(c.cue_id for c in request.cues) == ids and
          tuple(c.source_index for c in request.cues) == tuple(b.source_index for b in prepared.semantic_bindings))
    check('immutable first pass and timing proof unchanged', lambda:
          before == (serialize_stateful_package(package), serialize_stateful_result(first), prepared.semantic_bindings))
    check('current V2 schema', lambda: request.schema_version == 2)

    limit = review.MAX_CUE_TEXT_CHARS
    large_texts = ('x' * limit, 'tail')
    large = artifact((window(ids, large_texts),))
    large_context = context(large)
    chunks = large_context[ids[0]]
    check('multi-chunk bounded case', lambda: len(chunks) == 2)
    check('lossless chunk reconstruction', lambda: ''.join(chunks) == '\n'.join(large_texts))
    check('every context item within existing char bound', lambda:
          all(0 < len(chunk) <= limit for chunk in chunks))
    check('multi-chunk mapping accepted by review contract', lambda:
          review.build_review_request(**originals, raw_asr_context=large_context).cues[0].raw_asr_context == chunks)
    exact_texts = tuple('z' * (limit - 1) for _ in range(review.MAX_REVIEW_CONTEXT_ITEMS - 1)) + ('y' * limit,)
    at_limit = artifact((window(ids, exact_texts),))
    check('exact maximum capacity lossless', lambda:
          len(context(at_limit)[ids[0]]) == review.MAX_REVIEW_CONTEXT_ITEMS and
          ''.join(context(at_limit)[ids[0]]) == '\n'.join(exact_texts))
    overflow = artifact((window(ids, ('z' * limit,) * review.MAX_REVIEW_CONTEXT_ITEMS),))
    reject('item-count overflow fails without truncation', lambda: context(overflow))
    # Text is retained byte-for-byte even when the ASR is clearly repetitive.
    check('runaway evidence retained only as raw reference', lambda:
          ''.join(context(at_limit)[ids[0]]) == '\n'.join(exact_texts))
    with patch.object(review, 'MAX_CUE_TEXT_CHARS', 3):
        invalid_chunk = artifact((window(ids, ('ab      cd',)),))
        reject('whitespace-only bounded chunk fails without rewrite', lambda: context(invalid_chunk))
    empty = artifact((window(ids[:2], ()),))
    empty_context = context(empty)
    check('empty window explicitly maps to empty tuple', lambda:
          empty_context == {ids[0]: (), ids[1]: ()})
    check('uncovered cues excluded and default to empty context', lambda:
          ids[2] not in empty_context and all(c.raw_asr_context == () for c in
              review.build_review_request(**originals, raw_asr_context=empty_context).cues))
    unknown_id = fixture.HybridCueIdentity.for_external_ja(len(ids)).cue_id
    unknown = artifact((window((unknown_id,), ('unknown',)),))
    reject('unknown cue ID rejects whole mapping', lambda: context(unknown))
    # Simulate detached frozen values; the helper must re-run native validation.
    reused = changed(value, windows=(value.windows[0],
                    replace(value.windows[1], external_cue_ids=(ids[1], ids[2]))))
    reject('multiple-window cue assignment fails via native contract', lambda: context(reused))
    duplicate = changed(value, windows=(changed(value.windows[0], external_cue_ids=(ids[0], ids[0])),))
    reject('duplicate within window fails via native contract', lambda: context(duplicate))
    reversed_windows = changed(value, windows=tuple(reversed(value.windows)))
    reject('window reordering rejected', lambda: context(reversed_windows))
    reject('detached source snapshot rejected', lambda: context(changed(value,
           source_snapshot=replace(snapshot, source_size=snapshot.source_size + 1))))
    reject('detached preparation rejected', lambda: context(value,
           changed(prepared, semantic_bindings=tuple(reversed(prepared.semantic_bindings)))))
    reject('untyped artifact rejected', lambda: context({}))
    reject('untyped preparation rejected', lambda: context(value, None))

    query = ' '.join(runner.QUALITY_REVIEW_QUERY.split())
    for name, terms in [
        ('window-level, not direct transcript', ['raw_asr_context is window-level reference evidence', 'NOT a direct 1:1 transcript']),
        ('neighboring speech warning', ['neighboring cues in that same window', 'Never assign every raw segment to the current cue']),
        ('all evidence together', ['cue-local accepted STT, external JA, first-pass repaired JA, Korean translation, neighboring cues, and whole-title context']),
        ('mismatch alone not deletion evidence', ['mismatch between raw ASR and external JA alone never justifies discarding']),
        ('noisy ASR is not truth', ['Noisy/runaway repeated raw ASR is not semantic truth']),
        ('speech and metadata distinction', ['distinguish spoken dialogue/reaction from subtitle/tool metadata', 'does not automatically turn a metadata cue into dialogue']),
        ('uncertainty preserves', ['False OMIT is worse than uncertain KEEP', 'uncertainty remains AMBIGUOUS', 'preserves it as KEEP']),
        ('lossless context item interpretation', ['ordered items concatenate losslessly']),
    ]:
        check('query ' + name, lambda terms=terms: all(term in query for term in terms))
    source = inspect.getsource(review.build_full_window_raw_asr_context)
    check('no production title/count/cue/UUID/dialogue hardcode', lambda:
          not re.search(r'\b(?:JUR-750|661|118|111|941|285|463)\b|ja-\d{6}|[0-9a-f]{8}-[0-9a-f-]{27,}|[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]', source))
    print(f'Quality review context smoke: PASS={passed} FAIL={failed}')
    return int(failed != 0)


if __name__ == '__main__':
    raise SystemExit(main())
