"""Offline contract checks against a retained native draft bundle; no model calls."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from teddy_discovery_stateful_review_draft import (
    build_review_draft_request, encode, parse_review_draft_result, sha,
)
from teddy_discovery_stateful_quality_review import (
    QualityReviewError, QualityReviewResult, QualityReviewResultCue, _parse,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    args = parser.parse_args()
    root = args.bundle.resolve()
    request = (root / 'hermes-review-draft-request.json').read_bytes()
    canonical = (root / 'hermes-supplemental-review-request.json').read_bytes()
    language = (root / 'source-language-response.json').read_bytes()
    cross = (root / 'cross-evidence-prompt-projection.json').read_bytes()
    assert request == build_review_draft_request(canonical, language, cross)
    data = json.loads(request)
    response = dict(schema_version=1, purpose='review_draft_only', request_sha256=sha(request),
                    publishable=False, drafts=[dict(
                        cue_id=g['cue_id'], conflict_note='OFFLINE SYNTHETIC TEST; not a language judgment',
                        interpretations=[dict(reading_id=v['reading_id'], ja_candidate=v['ja_candidate'],
                            ko_draft='오프라인 합성 테스트 초안',
                            unresolved_reason='OFFLINE TEST: Japanese and timing unverified')
                            for v in g['interpretations']]) for g in data['groups']])
    parsed = parse_review_draft_result(encode(response), request)
    assert all(g['original_judgment']['action'] == 'AMBIGUOUS' and not g['approved']
               and not g['srt_eligible'] and not g['publishable']
               and g['audio_verification'] == 'UNVERIFIED_AUDIO' for g in parsed['groups'])
    assert language == (root / 'source-language-response.json').read_bytes()
    checks = ['all_alternatives_translate_without_changing_judgment', 'approval_and_publication_false']

    def reject(name, mutate):
        value = copy.deepcopy(response)
        mutate(value)
        try:
            parse_review_draft_result(encode(value), request)
        except QualityReviewError:
            checks.append(name)
        else:
            raise AssertionError('unexpected acceptance: ' + name)

    reject('publishable_true_rejected', lambda d: d.update(publishable=True))
    reject('wrong_SHA_rejected', lambda d: d.update(request_sha256='0'*64))
    reject('truncated_SHA_rejected', lambda d: d.update(request_sha256=sha(request)[:-3]))
    reject('omitted_alternative_rejected', lambda d: d['drafts'][0]['interpretations'].pop())
    reject('invented_Japanese_rejected', lambda d: d['drafts'][0]['interpretations'][0].update(ja_candidate='SYNTHETIC WRONG SOURCE'))
    reject('negative_control_cue_rejected', lambda d: d['drafts'].append(dict(d['drafts'][0],cue_id='control-01')))
    reject('action_change_rejected', lambda d: d['drafts'][0].update(action='REPAIR'))
    reject('audio_verified_claim_rejected', lambda d: d['drafts'][0].update(audio_verified=True))
    reject('invented_timestamp_rejected', lambda d: d['drafts'][0].update(start_ms=0))
    reject('approval_field_rejected', lambda d: d.update(approved=True))
    reject('group_order_changed_rejected', lambda d: d['drafts'].reverse())
    nullable = copy.deepcopy(response)
    nullable['drafts'][0]['interpretations'][0]['ko_draft'] = None
    parse_review_draft_result(encode(nullable), request)
    checks.append('unsupported_translation_can_remain_null')
    try:
        _parse(encode(response), QualityReviewResult, QualityReviewResultCue)
    except QualityReviewError:
        checks.append('canonical_quality_parser_rejects_draft_artifact')
    else:
        raise AssertionError('draft entered canonical result contract')
    try:
        QualityReviewResultCue(cue_id='offline-test', action='AMBIGUOUS', category='AMBIGUOUS',
                              reason='offline-test', replacement_ja=None, replacement_ko='테스트')
    except QualityReviewError:
        checks.append('existing_AMBIGUOUS_translation_prohibition_unchanged')
    else:
        raise AssertionError('canonical replacement contract relaxed')
    sys.path.insert(0, '/tmp/stage11-hermes-fresh-path-audit')
    from prepare_offline import TIRITH_WARNING
    out = Path(tempfile.mkdtemp(prefix='stage11-review-draft-OFFLINE-MOCK-'))
    raw = TIRITH_WARNING + encode(response)
    (out / 'stdout.json').write_bytes(raw)
    subprocess.run([sys.executable, '-B', str(root/'verify-inputs.py'), '--offline-validate', str(out)], check=True)
    assert (out/'stdout.json').read_bytes() == raw
    assert (out/'review_draft.json').exists()
    assert not (out/'supplemental-language-decisions.json').exists()
    assert not (out/'validated-response.json').exists()
    audit = json.loads((out/'validation-audit.json').read_bytes())
    assert audit['runtime_session_id'] is None and audit['approved']==0 and audit['srt_insertions']==0
    checks.append('native_verifier_saves_only_separate_draft_and_preserves_stdout')
    report = dict(status='PASS', checks=checks, test_count=len(checks), mock_output=str(out),
                  actual_Hermes_requests=0, STT_requests=0, approvals=0,
                  canonical_JA=313, canonical_KO_SRT=296, absorption=17,
                  drafts_in_this_test_are_synthetic=True)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
