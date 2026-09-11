"""Synthetic review-only proximity selection and exact V2 wire checks."""
from dataclasses import FrozenInstanceError, replace
import inspect
import json
import re

import teddy_discovery_stateful_quality_review as review
from teddy_discovery_stateful_quality_review_runner import QUALITY_REVIEW_QUERY
from teddy_discovery_stateful_hybrid import prepare_stateful_hybrid
from teddy_discovery_stateful_hybrid_smoke import changed, semantic_result
from teddy_discovery_subtitle_v2_pipeline_smoke import accepted_hybrid_route
from teddy_discovery_asr import ASRSegment, REMOTE_GPU_LARGE_V3_RUNTIME_IDENTITY
from teddy_discovery_targeted_asr_artifact import TargetedASRArtifact, serialize_targeted_asr_artifact
from teddy_discovery_targeted_hybrid_evidence import TargetedASRWindowEvidence, build_targeted_asr_bindings
from teddy_discovery_stateful_translator import serialize_stateful_package, serialize_stateful_result
from teddy_discovery_subtitle_source_quality import classify_source_document


def main():
    passed = failed = 0
    def check(name, call):
        nonlocal passed, failed
        try:
            assert call()
        except Exception as error:
            failed += 1
            print(f'FAIL {name}: {type(error).__name__}: {error}')
        else:
            passed += 1
            print('PASS ' + name)
    def reject(name, call):
        def run():
            try:
                call()
            except review.QualityReviewError:
                return True
            return False
        check(name, run)

    prepared = prepare_stateful_hybrid(accepted_hybrid_route(), generation_key='proximity-fixture', claim_token=9)
    package = prepared.package
    first = semantic_result(package)
    app = prepared.route_decision.alignment_application
    bundle = app.bundle
    snapshot = bundle.asr_result.source_snapshot
    ids = tuple(c.cue_id for c in package.cues)
    originals = dict(preparation=prepared, package=package, result=first,
                    source_quality=classify_source_document(bundle.external_ja_document))
    def artifact(cue_ids, segments, start=0, end=2_000_000):
        return TargetedASRArtifact(snapshot, REMOTE_GPU_LARGE_V3_RUNTIME_IDENTITY,
            'proximity-test', (TargetedASRWindowEvidence(snapshot, start, end, cue_ids,
                tuple(ASRSegment(a, b, text) for a, b, text in segments)),))
    def evidence(value):
        return review.build_review_proximity_asr_evidence(value, preparation=prepared)

    # Native accepted affine projection is +100 ms: first cue [1000, 1500].
    overlap = artifact(ids[:1], [(1100, 1200, 'overlap')])
    check('direct overlap never selected', lambda: evidence(overlap) == {})
    after = artifact(ids[:1], [(1600, 1700, 'nearby speech')])
    selected = evidence(after)[ids[0]]
    check('unique mutual non-overlap creates candidate', lambda: selected.mutual_nearest is True)
    check('AFTER and accepted affine distance', lambda: selected.relation == 'AFTER' and selected.distance_ms == 100)
    before = artifact(ids[:1], [(800, 900, 'before speech')])
    check('BEFORE relation and distance', lambda:
          evidence(before)[ids[0]].relation == 'BEFORE' and evidence(before)[ids[0]].distance_ms == 100)
    touching = artifact(ids[:1], [(1500, 1501, 'endpoint contact')])
    check('endpoint contact non-overlap distance zero', lambda: evidence(touching)[ids[0]].distance_ms == 0)
    tied = artifact(ids[:1], [(800, 900, 'first'), (1600, 1700, 'second')])
    check('cue nearest tie gives none', lambda: evidence(tied) == {})
    segment_tie = artifact(ids[1:3], [(2600, 2700, 'equidistant')])
    check('segment nearest tie gives none', lambda: evidence(segment_tie) == {})
    nonmutual = artifact(ids[:2], [(2600, 2700, 'nearest only to later cue')])
    check('non-mutual cue omitted', lambda: ids[0] not in evidence(nonmutual) and ids[1] in evidence(nonmutual))
    far = artifact(ids[:1], [(1_000_000, 1_000_001, 'far speech')])
    check('large distance no threshold removal', lambda: evidence(far)[ids[0]].distance_ms == 998500)
    matching = artifact(ids[:1], [(1600, 1700, 'unrelated text'), (1800, 1900, package.cues[0].external_ja)])
    check('text matching never chooses more distant candidate', lambda: evidence(matching)[ids[0]].text == 'unrelated text')
    swapped = artifact(ids[:1], [(1600, 1700, package.cues[0].external_ja), (1800, 1900, 'unrelated text')])
    check('selection text independent', lambda: replace(evidence(swapped)[ids[0]], text='unrelated text') == evidence(matching)[ids[0]])
    runaway = artifact(ids[:1], [(1600, 1700, 'あ' * 64)])
    check('runaway preserved as true hint', lambda: evidence(runaway)[ids[0]].runaway is True)
    check('ordinary runaway hint false', lambda: selected.runaway is False)
    check('empty window no evidence', lambda: evidence(artifact(ids, [])) == {})
    overlap_owner = artifact(ids[:2], [(1100, 1200, 'owned by first cue')])
    check('segment overlapping cue A cannot be proximity for nearby cue B', lambda:
          evidence(overlap_owner) == {})
    target = artifact(ids[1:2], [(1700, 1800, 'direct overlap'), (2600, 2700, 'nearby')])
    bindings_before = build_targeted_asr_bindings(bundle.external_ja_document.cues, app.alignment, target.windows[0])
    state_before = (serialize_stateful_package(package), serialize_stateful_result(first), prepared.semantic_bindings)
    wire_before = serialize_targeted_asr_artifact(target)
    target_context = evidence(target)
    check('strict targeted binding exists independently', lambda: len(bindings_before) == 1)
    check('overlap competes before nearby candidate is rejected', lambda: target_context == {})
    check('targeted binding before/after unchanged', lambda: bindings_before ==
          build_targeted_asr_bindings(bundle.external_ja_document.cues, app.alignment, target.windows[0]))
    check('baseline cue may get reference without binding promotion', lambda:
          package.cues[0].stt_ja is not None and ids[0] in evidence(after) and
          build_targeted_asr_bindings(bundle.external_ja_document.cues, app.alignment, after.windows[0]) == ())
    check('first pass accepted STT timing and segment order immutable', lambda:
          state_before == (serialize_stateful_package(package), serialize_stateful_result(first), prepared.semantic_bindings)
          and wire_before == serialize_targeted_asr_artifact(target))

    request = review.build_review_request(**originals, proximity_asr_artifact=after)
    wire = review.serialize_review_request(request)
    def parse(data):
        return review.parse_review_request(data, **originals, proximity_asr_artifact=after)
    check('V2 exact request roundtrip', lambda: parse(wire) == request)
    check('V2 version bump', lambda: request.schema_version == review.STATEFUL_QUALITY_REVIEW_SCHEMA_VERSION == 2)
    check('deterministic serialization and input order', lambda:
          review.serialize_review_request(parse(wire)) == wire and tuple(c.cue_id for c in request.cues) == ids)
    check('zero or one immutable object', lambda:
          request.cues[0].proximity_asr_evidence == selected and
          all(c.proximity_asr_evidence is None for c in request.cues[1:]))
    check('optional artifact means null exact field', lambda:
          all(c.proximity_asr_evidence is None for c in review.build_review_request(**originals).cues))
    obj = json.loads(wire)
    check('exact nested field set', lambda: set(obj['cues'][0]['proximity_asr_evidence']) ==
          {'text', 'relation', 'distance_ms', 'mutual_nearest', 'runaway'})
    def encode(obj):
        return json.dumps(obj, ensure_ascii=False).encode()
    for key, val in [('distance_ms', -1), ('distance_ms', True), ('distance_ms', 1.0),
                     ('distance_ms', float('nan')), ('distance_ms', float('inf')),
                     ('relation', 'DURING'), ('mutual_nearest', False), ('mutual_nearest', 1),
                     ('runaway', True), ('runaway', 0), ('text', ''), ('text', 'x' * (review.MAX_CUE_TEXT_CHARS + 1))]:
        changed_obj = json.loads(wire)
        changed_obj['cues'][0]['proximity_asr_evidence'][key] = val
        reject('invalid nested ' + key, lambda obj=changed_obj: parse(encode(obj)))
    for variant in ['extra', 'missing', 'list', 'detached_text', 'detached_distance', 'missing_cue_field']:
        obj = json.loads(wire)
        nested = obj['cues'][0]['proximity_asr_evidence']
        if variant == 'extra': nested['timestamp'] = 0
        elif variant == 'missing': nested.pop('relation')
        elif variant == 'list': obj['cues'][0]['proximity_asr_evidence'] = [nested]
        elif variant == 'detached_text': nested['text'] = 'different text'
        elif variant == 'detached_distance': nested['distance_ms'] += 1
        else: obj['cues'][0].pop('proximity_asr_evidence')
        reject('exact provenance ' + variant, lambda obj=obj: parse(encode(obj)))
    reject('artifact required to re-prove proximity', lambda: review.parse_review_request(wire, **originals))
    old = json.loads(wire)
    old['schema_version'] = 1
    for cue in old['cues']: cue.pop('proximity_asr_evidence')
    frozen_v1 = encode(old)
    reject('V1 request explicitly rejected', lambda: parse(frozen_v1))
    check('V1 bytes unmodified', lambda: frozen_v1 == encode(old))
    result = review.QualityReviewResult(2, review.review_request_sha256(request), tuple(
        review.QualityReviewResultCue(c.cue_id, 'KEEP', 'DIALOGUE', 'preserve evidence', None, None) for c in request.cues))
    result_wire = review.serialize_review_result(result, request)
    check('V2 result exact roundtrip', lambda: review.parse_review_result(result_wire, request) == result)
    old_result = json.loads(result_wire)
    old_result['schema_version'] = 1
    reject('V1 result explicitly rejected', lambda: review.parse_review_result(encode(old_result), request))
    try:
        selected.distance_ms = 0
    except FrozenInstanceError:
        immutable = True
    else:
        immutable = False
    check('evidence frozen', lambda: immutable)
    unknown = artifact((f'ja-{len(ids) + 1:06d}',), [])
    reject('unknown cue even in empty window', lambda: evidence(unknown))
    duplicate = changed(after, windows=(changed(after.windows[0], external_cue_ids=(ids[0], ids[0])),))
    reject('duplicate cue identity', lambda: evidence(duplicate))
    multiple = changed(after, windows=(after.windows[0], replace(after.windows[0], window_start_ms=1)))
    reject('multiple window assignment', lambda: evidence(multiple))
    reject('detached window source', lambda: evidence(changed(after,
           source_snapshot=replace(snapshot, source_size=snapshot.source_size + 1))))
    reject('cue outside window', lambda: evidence(artifact(ids[:1], [], start=1100)))
    reject('detached preparation', lambda: review.build_review_proximity_asr_evidence(after,
           preparation=changed(prepared, semantic_bindings=tuple(reversed(prepared.semantic_bindings)))))
    query = ' '.join(QUALITY_REVIEW_QUERY.split())
    for term in ['unique mutual nearest non-overlap', 'NOT a direct binding or accepted STT',
                 'Distance alone never proves identity', 'Semantic mismatch means do not force-match',
                 'remains metadata despite nearby speech', 'against an unsupported metadata/noise deletion',
                 'False OMIT is worse than uncertain KEEP', 'preserves the first pass through deterministic KEEP',
                 'never generate or modify timing']:
        check('query ' + term, lambda term=term: term in query)
    source = inspect.getsource(review.build_review_proximity_asr_evidence)
    check('no title/cue/dialogue hardcode', lambda:
          not re.search(r'\b[A-Z]{2,10}-\d{2,8}\b|ja-\d{6}|\b(?:661|118|111|941|285|463)\b|[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]', source))
    print(f'Quality review proximity smoke: PASS={passed} FAIL={failed}')
    return int(failed != 0)


if __name__ == '__main__':
    raise SystemExit(main())
