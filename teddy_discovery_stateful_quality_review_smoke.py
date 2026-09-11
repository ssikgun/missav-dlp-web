"""Synthetic contract checks only; no live models or review artifact writes."""
import ast
from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import re
from unittest.mock import patch

import teddy_discovery_stateful_quality_review as review
from teddy_discovery_stateful_hybrid import prepare_stateful_hybrid
from teddy_discovery_stateful_hybrid_smoke import semantic_result, changed
from teddy_discovery_subtitle_v2_pipeline_smoke import accepted_hybrid_route
from teddy_discovery_subtitle_source_quality import classify_source_document
from teddy_discovery_stateful_translator import serialize_stateful_package, serialize_stateful_result
from teddy_discovery_stateful_parts import has_runaway_repetition


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()


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
            print(f'PASS {name}')

    def reject(name, callback):
        def rejected():
            try:
                callback()
            except review.QualityReviewError:
                return True
            return False
        check(name, rejected)

    preparation = prepare_stateful_hybrid(accepted_hybrid_route(), generation_key='review-fixture', claim_token=7)
    package = preparation.package
    first_pass = semantic_result(package)
    before = (serialize_stateful_package(package), serialize_stateful_result(first_pass))
    document = preparation.route_decision.alignment_application.bundle.external_ja_document
    hints = classify_source_document(document)
    originals = dict(preparation=preparation, package=package, result=first_pass,
                     source_quality=hints, raw_asr_context={package.cues[0].cue_id: ('参考音声',)})
    request = review.build_review_request(**originals)
    pairs = [('KEEP', 'MEANINGFUL_REACTION'), ('REPAIR', 'SEMANTIC_REPAIR'),
             ('OMIT', 'SOURCE_NOISE'), ('AMBIGUOUS', 'AMBIGUOUS')]
    result = review.QualityReviewResult(review.STATEFUL_QUALITY_REVIEW_SCHEMA_VERSION,
        review.review_request_sha256(request), tuple(
            review.QualityReviewResultCue(c.cue_id, action, category,
                'Source and accepted evidence support this decision.' if action != 'AMBIGUOUS' else 'Evidence is uncertain; preserve dialogue.',
                '少し待ってください' if action == 'REPAIR' else None,
                '잠시 기다려 주세요' if action == 'REPAIR' else None)
            for c, (action, category) in zip(request.cues, pairs, strict=True)))
    request_bytes = review.serialize_review_request(request)
    result_bytes = review.serialize_review_result(result, request)
    check('full-title request roundtrip', lambda: review.parse_review_request(request_bytes, **originals) == request)
    check('full-title result roundtrip', lambda: review.parse_review_result(result_bytes, request) == result)
    check('deterministic request bytes', lambda: review.serialize_review_request(review.parse_review_request(request_bytes, **originals)) == request_bytes)
    check('deterministic result bytes', lambda: review.serialize_review_result(review.parse_review_result(result_bytes, request), request) == result_bytes)
    legacy_request_object = json.loads(request_bytes)
    legacy_request_object['session_id'] = legacy_request_object.pop(
        'source_translation_session_id'
    )
    legacy_request_bytes = json.dumps(
        legacy_request_object, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'),
    ).encode()
    legacy_request = review.parse_review_request(legacy_request_bytes, **originals)
    check('legacy session_id is source provenance', lambda:
          legacy_request == request
          and review.serialize_review_request(legacy_request) == legacy_request_bytes
          and legacy_request.session_id == request.source_translation_session_id)
    execution_session_id = '12345678-1234-5678-1234-567812345678'
    bound_result = review.bind_review_execution_provenance(
        result, request, execution_session_id
    )
    bound_result_bytes = review.serialize_review_result(bound_result, request)
    check('result keeps source and execution identities', lambda:
          review.parse_review_result(bound_result_bytes, request)
          == bound_result
          and bound_result.source_translation_session_id
          == request.source_translation_session_id
          and bound_result.review_execution_session_id == execution_session_id)
    check('all first-pass Korean retained', lambda: tuple(c.first_pass_ko for c in request.cues) == tuple(c.ko for c in first_pass.cues))
    check('all source and accepted STT retained', lambda: all(c.external_ja == p.external_ja and c.accepted_stt_ja == p.stt_ja for c, p in zip(request.cues, package.cues)))
    check('all source-quality KEEP cues still reviewed', lambda: len(request.cues) == len(hints) and len(result.cues) == len(package.cues))
    check('ASR source-quality hints remain separate', lambda:
          all((cue.accepted_stt_ja is None) == (cue.asr_source_quality is None)
              for cue in request.cues)
          and all(cue.asr_source_quality is None or
                  cue.asr_source_quality.source_index >= 0
                  for cue in request.cues))
    check('request source binding retained', lambda: tuple(c.source_index for c in request.cues) == tuple(b.source_index for b in preparation.semantic_bindings))
    check('original package/result unmodified', lambda: before == (serialize_stateful_package(package), serialize_stateful_result(first_pass)))
    check('immutable tuple reconstruction', lambda: type(review.parse_review_request(request_bytes, **originals).cues) is tuple and type(request.cues[0].raw_asr_context) is tuple)
    check('canonical repetition validator reused', lambda: review.has_runaway_repetition is has_runaway_repetition)

    def immutable(value, key, replacement):
        try:
            setattr(value, key, replacement)
        except FrozenInstanceError:
            return True
        return False

    for value, key in [(request, 'cues'), (request.cues[0], 'source_index'), (result, 'cues'), (result.cues[0], 'action')]:
        check('immutable review model', lambda value=value, key=key: immutable(value, key, None))
    for request_cue, cue, expected in zip(
        request.cues, result.cues, ['KEEP', 'REPAIR', 'OMIT', 'KEEP']
    ):
        check(
            'effective action ' + cue.action,
            lambda request_cue=request_cue, cue=cue, expected=expected:
            review.effective_review_action(request_cue, cue) == expected,
        )

    keep, repair, omit, ambiguous = result.cues
    identity_request_cue = replace(
        request.cues[0], first_pass_repaired_ja='初回修正版'
    )
    identity_repair = replace(
        keep,
        action=review.REPAIR,
        category='SEMANTIC_REPAIR',
        replacement_ja=identity_request_cue.first_pass_repaired_ja,
        replacement_ko=identity_request_cue.first_pass_ko,
    )
    check(
        'exact identity REPAIR becomes KEEP',
        lambda: review.effective_review_action(
            identity_request_cue, identity_repair
        ) == review.KEEP,
    )
    check(
        'KO-only change remains REPAIR',
        lambda: review.effective_review_action(
            identity_request_cue,
            replace(identity_repair, replacement_ko='다른 번역'),
        ) == review.REPAIR,
    )
    check(
        'JA-only change remains REPAIR',
        lambda: review.effective_review_action(
            identity_request_cue,
            replace(identity_repair, replacement_ja='別の修正版'),
        ) == review.REPAIR,
    )
    check(
        'JA-and-KO change remains REPAIR',
        lambda: review.effective_review_action(
            identity_request_cue,
            replace(
                identity_repair,
                replacement_ja='別の修正版',
                replacement_ko='다른 번역',
            ),
        ) == review.REPAIR,
    )
    # The replacement Japanese is intentionally valid non-empty Japanese only;
    # its first-pass JA counterpart is None, so this is not an identity repair.
    none_repair = replace(
        repair,
        replacement_ja='初回修正版なし',
        replacement_ko=request.cues[1].first_pass_ko,
    )
    check(
        'missing first-pass JA remains REPAIR',
        lambda: review.effective_review_action(
            request.cues[1], none_repair
        ) == review.REPAIR,
    )
    identity_snapshot = (identity_request_cue, identity_repair)
    check(
        'normalization does not mutate raw models',
        lambda: review.effective_review_action(
            identity_request_cue, identity_repair
        ) == review.KEEP
        and identity_snapshot == (identity_request_cue, identity_repair),
    )

    def parse_request_obj(obj):
        return review.parse_review_request(encoded(obj), **originals)
    def parse_result_obj(obj):
        return review.parse_review_result(encoded(obj), request)
    for payload, parser in [(request_bytes, parse_request_obj), (result_bytes, parse_result_obj)]:
        for where in ['top', 'cue']:
            for change in ['extra', 'missing']:
                obj = json.loads(payload)
                target = obj if where == 'top' else obj['cues'][0]
                if change == 'extra':
                    target['timestamp'] = 0
                else:
                    target.pop(next(iter(target)))
                reject('exact fields ' + where + ' ' + change, lambda obj=obj, parser=parser: parser(obj))
        for variant in ['duplicate', 'missing', 'extra', 'reorder']:
            obj = json.loads(payload)
            if variant == 'duplicate':
                obj['cues'][1] = obj['cues'][0]
            elif variant == 'missing':
                obj['cues'].pop()
            elif variant == 'extra':
                cue = dict(obj['cues'][-1], cue_id='unknown-cue')
                if 'source_index' in cue:
                    cue['source_index'] += 1
                obj['cues'].append(cue)
            else:
                obj['cues'].reverse()
            reject('cue identity ' + variant, lambda obj=obj, parser=parser: parser(obj))
    for payload, parser in [(request_bytes, lambda p: review.parse_review_request(p, **originals)),
                            (result_bytes, lambda p: review.parse_review_result(p, request))]:
        reject('duplicate top JSON key', lambda payload=payload, parser=parser: parser(b'{"schema_version":1,' + payload[1:]))
        reject('duplicate nested JSON key', lambda payload=payload, parser=parser: parser(payload.replace(b'"cue_id":', b'"cue_id":"duplicate","cue_id":', 1)))
        for token in [b'NaN', b'Infinity', b'-Infinity']:
            reject('nonfinite JSON', lambda token=token, payload=payload, parser=parser: parser(payload.replace(b'"schema_version":2', b'"schema_version":' + token)))
        for invalid in [b'\xff', b'', b'[]', b'{', 'not bytes', b'[' * 2000]:
            reject('invalid bytes/JSON', lambda invalid=invalid, parser=parser: parser(invalid))
        reject('oversized wire payload', lambda parser=parser: parser(b' ' * (review.MAX_REVIEW_BYTES + 1)))

    for field, value in [('source_index', True), ('source_index', 3), ('external_ja', '別の発言'),
                         ('first_pass_ko', '다른 번역'), ('accepted_stt_ja', '違う音声')]:
        obj = json.loads(request_bytes)
        obj['cues'][0][field] = value
        reject('request detachment ' + field, lambda obj=obj: parse_request_obj(obj))
    for field in ['package_sha256', 'first_pass_sha256', 'source_sha256',
                  'source_translation_session_id']:
        obj = json.loads(request_bytes)
        obj[field] = '0' * 64
        reject('original identity ' + field, lambda obj=obj: parse_request_obj(obj))
    reject('result request hash mismatch', lambda: review.validate_review_result(replace(result, request_sha256='0' * 64), request))
    reject('wrong original package', lambda: review.build_review_request(**dict(originals, package=replace(package, generation_key='other'))))
    reject('wrong first-pass session', lambda: review.build_review_request(**dict(originals, result=changed(first_pass, session_id='other'))))
    reject('source quality index detached', lambda: review.build_review_request(**dict(originals, source_quality=(replace(hints[0], source_index=1),) + hints[1:])))
    reject('source quality text detached', lambda: review.build_review_request(**dict(originals, source_quality=(replace(hints[0], source_text='別の発言'),) + hints[1:])))
    reject('preparation binding detached', lambda: review.build_review_request(**dict(originals, preparation=changed(preparation, semantic_bindings=tuple(reversed(preparation.semantic_bindings))))))
    reject('unknown raw context identity', lambda: review.build_review_request(**dict(originals, raw_asr_context={'unknown': ('参考',)})))
    for context in [[], ('x',) * (review.MAX_REVIEW_CONTEXT_ITEMS + 1), ('',), (False,)]:
        reject('invalid raw context', lambda context=context: review.build_review_request(**dict(originals, raw_asr_context={package.cues[0].cue_id: context})))
    check('empty raw context allowed', lambda: review.build_review_request(**dict(originals, raw_asr_context=None)).cues[0].raw_asr_context == ())

    keep, repair, omit, ambiguous = result.cues
    for fields in [dict(action='UNKNOWN'), dict(category='UNKNOWN'), dict(action='OMIT'), dict(category='SEMANTIC_REPAIR')]:
        reject('unknown/invalid action category', lambda fields=fields: replace(keep, **fields))
    for cue in [keep, omit, ambiguous]:
        for field in ['replacement_ja', 'replacement_ko']:
            reject('non-repair replacement rejected', lambda cue=cue, field=field: replace(cue, **{field: 'text'}))
    for field in ['replacement_ja', 'replacement_ko']:
        for value in [None, '', '  ', 7, False, 'x' * (review.MAX_CUE_TEXT_CHARS + 1), '\ud800', '\x00']:
            reject('invalid REPAIR text', lambda field=field, value=value: replace(repair, **{field: value}))
        reject('runaway REPAIR text', lambda field=field: replace(repair, **{field: 'あ' * 64}))
    for text in ['한국어', 'ᄀ', 'ㄱ', 'ꥠ', 'ﾡ']:
        reject('Korean script in replacement JA', lambda text=text: replace(repair, replacement_ja=text))
    reject('oversized reason', lambda: replace(keep, reason='x' * (review.MAX_REVIEW_REASON_CHARS + 1)))
    reject('boolean schema', lambda: replace(request, schema_version=True))
    reject('unknown schema', lambda: replace(result, schema_version=3))
    reject('wrong model type', lambda: review.effective_review_action('AMBIGUOUS'))
    with patch.object(review, 'MAX_REVIEW_CUES', len(request.cues) - 1):
        reject('bounded request cue count', lambda: review.serialize_review_request(request))
        reject('bounded result cue count', lambda: review.validate_review_result(result, request))
    with patch.object(review, 'MAX_REVIEW_BYTES', len(request_bytes) - 1):
        reject('bounded serialization', lambda: review.serialize_review_request(request))

    def keys(value):
        if isinstance(value, dict):
            return set(value).union(*(keys(v) for v in value.values()))
        if isinstance(value, list):
            return set().union(*(keys(v) for v in value))
        return set()
    forbidden = {'start', 'end', 'start_ms', 'end_ms', 'timestamp', 'duration', 'sequence', 'srt_sequence'}
    check('no timing or SRT fields', lambda: not (keys(json.loads(request_bytes)) | keys(json.loads(result_bytes))) & forbidden)
    check('no LLM source index output', lambda: 'source_index' not in keys(json.loads(result_bytes)))
    source = Path(review.__file__).read_text()
    check('no title/path/count hardcode', lambda: not re.search(r'(?i)\b[A-Z]{2,10}-\d{2,8}\b|/subs/\d+|\b661\b', source))
    check('no Japanese phrase rules', lambda: not re.search(r'[\u3040-\u30ff\u3400-\u9fff]', source))
    doc = ast.get_docstring(ast.parse(source))
    check('semantic preservation contract', lambda: all(term in doc for term in ['not automatically deleted', 'evidence-based repair', 'never hallucinated dialogue', 'meaningful reactions can KEEP', 'AMBIGUOUS with KEEP', 'neither timing, source identity nor publication', 'KEEP never exempts']))
    print(f'Quality review smoke: PASS={passed} FAIL={failed}')
    return int(failed != 0)


if __name__ == '__main__':
    raise SystemExit(main())
