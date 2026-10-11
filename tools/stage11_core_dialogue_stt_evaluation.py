#!/usr/bin/env python3
"""Evaluate retained STT evidence only; no network, model imports or inference."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import pickle
import unicodedata
import wave


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def norm(text):
    # Only typography; no kana/kanji conversion, semantic equivalence or repair.
    return ''.join(c for c in unicodedata.normalize('NFKC', text)
                   if unicodedata.category(c)[0] not in 'PZ' and not c.isspace())


def overlap(a, b):
    return max(a[0], b[0]) < min(a[1], b[1])


def write(root, name, value):
    (root / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


class SavedRecord:
    """Read historical data attributes without importing operational modules."""
    def __setstate__(self, state):
        for item in (state if isinstance(state, tuple) else (state,)):
            if isinstance(item, dict):
                self.__dict__.update(item)


class SavedDataReader(pickle.Unpickler):
    def find_class(self, module, name):
        if module.startswith('teddy_discovery_'):
            return SavedRecord
        raise ValueError(('Unsupported saved data type', module, name))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('config')
    args = ap.parse_args()
    cfg = read(args.config)
    root = Path(cfg['output_root'])
    root.mkdir(exist_ok=True)
    verified = {}

    def pin(path, expected=None):
        actual = digest(path)
        if expected is not None:
            assert actual == expected, ('SHA mismatch', path, expected, actual)
        verified[str(path)] = actual
        return actual

    for path, expected in read(cfg['protected_pins']).items():
        pin(path, expected)
    pin(args.config)
    for key in ['priority_manifest', 'scope_audit', 'prior_truth', 'old_reazon',
                'new_reazon', 'audio_manifest', 'medium_results', 'ja_source',
                'user_feedback', 'source_alignment', 'protocol']:
        pin(cfg[key])
    groups = read(cfg['priority_manifest'])['groups']
    scopes = {x['group_id']: x for x in read(cfg['scope_audit'])['positives']}
    truth = {x['id']: x for x in read(cfg['prior_truth'])}
    feedback = read(cfg['user_feedback'])
    user = {x['id']: x for x in feedback['judgments']}
    old = read(cfg['old_reazon'])
    new = read(cfg['new_reazon'])
    old_req = {x['group_id']: x for x in old['case_requests']}
    reazon = {x['group_id']: (x, old_req[x['group_id']], cfg['old_reazon'])
              for x in old['results']}
    for x in new['results']:
        q = x['request']
        if q['kind'] == 'SUPPLEMENTAL':
            assert q['group_id'] not in reazon
            reazon[q['group_id']] = (x, q, cfg['new_reazon'])
    observations = {g['cue_id']: g['observations']
                    for g in read(cfg['audio_manifest'])['groups']}
    medium = {}
    for q in read(cfg['medium_results'])['case_requests']:
        f = str(Path(cfg['medium_results']).parent /
                (q['case_id'] + '.absolute-estimates.json'))
        pin(f)
        medium[q['group_id']] = {'input_range_ms': [q['clip_start_ms'], q['clip_end_ms']],
                                  'source_path': f, 'result': read(f)}
        pin(q['npy_path'], q['npy_sha256'])

    ja = read(cfg['ja_source'])
    pin(ja['trusted_seed'], ja['trusted_seed_sha256'])
    with Path(ja['trusted_seed']).open('rb') as f:
        package = SavedDataReader(f).load()[0].package
    saved_ja = {c.cue_id: c.external_ja for c in package.cues}
    assert all(c['external_ja'] == saved_ja[c['cue_id']] for c in ja['cues'])
    aligned = read(cfg['source_alignment'])['external_JA']
    assert [(c['cue_id'], c['start_ms'], c['end_ms']) for c in ja['cues']] == [
        (c['cue_id'], c['start_ms'], c['end_ms']) for c in aligned]
    full_short = []
    # Inspect only saved requests whose audio intersects these thirteen cores.
    for f in sorted(Path(cfg['full_short_root']).glob('core-*.done.json')):
        done = read(f)
        span = [done['audio_start_ms'], done['audio_end_ms']]
        if not any(overlap(span, [g['group_start_ms'], g['group_end_ms']]) for g in groups):
            continue
        pin(f)
        prefix = str(f).removesuffix('.done.json')
        pin(prefix + '.request.npy', done['request_sha256'])
        pin(prefix + '.segments.json', done['segments_sha256'])
        pin(prefix + '.wire.json', done['response_sha256'])
        full_short.append({'input_range_ms': span, 'request_path': prefix + '.request.npy',
                           'request_sha256': done['request_sha256'],
                           'source_path': prefix + '.segments.json',
                           'segments': read(prefix + '.segments.json')})

    rows = []
    for g in groups:
        gid = g['group_id']
        scope = scopes[gid]
        ident = scope['id']
        u = user[ident]
        core = [scope['core_start_ms'], scope['core_end_ms']]
        assert core == [g['group_start_ms'], g['group_end_ms']]
        assert u['core_label'] in ['DIALOGUE_LIKELY', 'DIALOGUE_SHORT_FRAGMENT']
        assert u['japanese_transcript'] == ''
        for kind in ['core', 'context']:
            wav = Path(cfg['scope_audit']).parent / kind / (ident + '.wav')
            pin(wav, scope[kind + '_wav_sha256'])
            with wave.open(str(wav)) as f:
                assert f.getframerate() == 16000 and f.getnchannels() == 1
                if kind == 'core':
                    assert f.getnframes() == (core[1] - core[0]) * 16
        source = g['source_audio']
        pin(source['source_npy'], source['source_sha256'])
        primary = []
        for w in g['AB_readings']:
            e = w['audio_evidence']
            pin(e['evidence_origin'], e['asr_artifact_sha256'])
            assert e['audio_input_sha256'] == source['source_sha256']
            original = read(e['evidence_origin'])['segments'][e['segment_index']]
            assert original == e['segment']
            primary.append({'run': w['run'], 'text': w['stt_ja'],
                            'segment': original,
                            'input_range_ms': [source['start_ms'], source['end_ms']],
                            'input_path': source['source_npy'],
                            'input_sha256': source['source_sha256'],
                            'evidence_origin': e['evidence_origin'],
                            'body_time_overlap': overlap(core, [w['start_ms'], w['end_ms']])})
        alternatives = []
        for o in observations[gid]:
            if o['role'] != 'ORIGINAL_CANDIDATE':
                p = o.get('provenance', {})
                alternatives.append({'role': o['role'], 'segment': o['segment'],
                                     'input_range_ms': [p['request_lo'] / 16, p['request_hi'] / 16],
                                     'evidence_origin': o['evidence_origin'],
                                     'body_time_overlap': overlap(core, [o['segment']['start_ms'],
                                                                        o['segment']['end_ms']])})
        additional = g.get('additional_comparison_evidence', {})
        for x in additional.get('comparison_readings', []):
            pin(x['response_file'], x['response_sha256'])
        retained_short = []
        for x in full_short:
            if overlap(core, x['input_range_ms']):
                segments = [s for s in x['segments'] if overlap(
                    [scope['context_start_ms'], scope['context_end_ms']],
                    [s['start_ms'], s['end_ms']])]
                retained_short.append({**x, 'segments': [{**s, 'body_time_overlap': overlap(
                    core, [s['start_ms'], s['end_ms']])} for s in segments]})
        r_out = {'status': 'NOT_TESTED', 'core_points': [], 'text': ''}
        if gid in reazon:
            r, q, path = reazon[gid]
            is_old = path == cfg['old_reazon']
            lo, hi = (q['clip_lo'], q['clip_hi']) if is_old else (q['lo'], q['hi'])
            pin(q['wav_path'], q['wav_sha256'])
            assert r.get('input_wav_sha256', q['wav_sha256']) == q['wav_sha256']
            with wave.open(q['wav_path']) as f:
                assert f.getframerate() == 16000 and f.getnchannels() == 1
                assert f.getnframes() == hi - lo
            points = r['estimated_token_points']
            padding = old['artificial_padding_seconds'] if is_old else new['padding_seconds']
            for p in points:
                relative = p['raw_padded_seconds'] - padding
                invalid = relative < 0 or relative > (hi - lo) / 16000
                assert p['in_padding'] == invalid
                assert p['end_time'] is None
                if p['absolute_estimated_ms'] is not None:
                    assert abs(p['absolute_estimated_ms'] - (lo / 16 + relative * 1000)) < 1e-6
            core_points = [p for p in points if p['absolute_estimated_ms'] is not None
                           and core[0] <= p['absolute_estimated_ms'] < core[1]]
            r_out = {'status': 'CORE_TOKEN_POINTS_ESTIMATED' if core_points else
                              'CORE_ALIGNMENT_UNRESOLVED',
                     'input_range_ms': [lo / 16, hi / 16],
                     'input_wav_path': q['wav_path'], 'input_wav_sha256': q['wav_sha256'],
                     'input_float32_sha256': r['input_float32_sha256'],
                     'source_path': path, 'text': r['text'],
                     'core_point_tokens': ''.join(p['token'] for p in core_points),
                     'core_points': core_points, 'raw_points': points,
                     'raw_tokens': r['raw_tokens'], 'raw_timestamps': r['raw_timestamps'],
                     'padding_seconds': padding, 'timestamps_are_points_not_ranges': True,
                     'core_recognition_verified': 'UNKNOWN'}
        texts = {norm(w['text']) for w in primary if w['body_time_overlap']}
        rt = norm(r_out['text'])
        lexical = ('NOT_TESTED' if r_out['status'] == 'NOT_TESTED' else
                   'EXACT_TYPOGRAPHIC' if rt in texts else
                   'CONTAINS_PRIMARY' if any(t and t in rt for t in texts) else
                   'DIFFERENT_SURFACE_TEXT')
        core_comparison = (lexical if r_out['core_points'] else
                           'NOT_TESTED' if r_out['status'] == 'NOT_TESTED' else 'SCOPE_UNRESOLVED')
        ja_time = [c for c in ja['cues'] if overlap(core, [c['start_ms'], c['end_ms']])]
        ja_text = [c for c in ja['cues'] if any(t and t in norm(c['external_ja']) for t in texts)]
        rows.append({'id': ident, 'group_id': gid, 'core_range_ms': core,
                     'original_context_range_ms': [scope['context_start_ms'], scope['context_end_ms']],
                     'core_wav_sha256': scope['core_wav_sha256'],
                     'context_wav_sha256': scope['context_wav_sha256'],
                     'user_core_judgment': u, 'prior_context_truth': truth[ident],
                     'prior_user_note': scope['original_user_note'],
                     'speech_presence': u['core_label'], 'japanese_accuracy': 'UNKNOWN',
                     'whisper': {'status': 'CORE_SEGMENT_ESTIMATED' if texts else 'NOT_TESTED',
                                 'primary_AB': primary, 'saved_short_observations': alternatives,
                                 'saved_AB_comparison': additional.get('comparison_readings', []),
                                 'saved_full_short': retained_short,
                                 'saved_medium': medium.get(gid, {'status': 'NOT_TESTED'}),
                                 'core_recognition_verified': 'UNKNOWN'},
                     'reazon': r_out, 'clip_text_relation': lexical,
                     'core_supported_hypothesis_relation': core_comparison,
                     'verified_core_utterance_agreement': 'UNKNOWN',
                     'ja_temporal_overlaps': ja_time, 'ja_elsewhere_text_contains': ja_text,
                     'same_utterance_ja_duplicate': 'UNKNOWN', 'novel_dialogue': 'UNKNOWN',
                     'new_subtitle_evidence': 'FRAGMENT_REVIEW_ONLY' if u['core_label'] ==
                                              'DIALOGUE_SHORT_FRAGMENT' else 'UNVERIFIED_REVIEW_ONLY',
                     'verified_new_recovery': False, 'approved': False, 'srt_eligible': False})
    assert len(rows) == len(user) == 13
    counts = {'user_core_labels': dict(collections.Counter(r['speech_presence'] for r in rows)),
              'whisper_core_estimated_output': sum(r['whisper']['status'] == 'CORE_SEGMENT_ESTIMATED' for r in rows),
              'reazon_core_estimated_output': sum(bool(r['reazon']['core_points']) for r in rows),
              'core_supported_hypothesis_relation': dict(collections.Counter(
                  r['core_supported_hypothesis_relation'] for r in rows)),
              'clip_text_relation': dict(collections.Counter(r['clip_text_relation'] for r in rows)),
              'ja_temporal_duplicate_cases': sum(bool(r['ja_temporal_overlaps']) for r in rows),
              'ja_elsewhere_substring_cases': sum(bool(r['ja_elsewhere_text_contains']) for r in rows),
              'verified_new_recoveries': sum(r['verified_new_recovery'] for r in rows),
              'japanese_truth_needed': sum(r['japanese_accuracy'] == 'UNKNOWN' for r in rows),
              'verified_accurate_core_recognition': {'Whisper': 'UNKNOWN', 'ReazonSpeech': 'UNKNOWN'},
              'same_utterance_duplicate_count': 'UNKNOWN', 'approved': 0,
              'new_calls': {'Whisper': 0, 'ReazonSpeech': 0, 'Hermes': 0, 'Gemini': 0},
              'new_installs_downloads_srt_service_changes': 0}
    write(root, 'evaluation.json', {'protocol': read(cfg['protocol']), 'summary': counts, 'clips': rows})
    write(root, 'source-sha256.json', verified)
    write(root, 'user-core-judgments.json', feedback)
    revised_truth = [dict(x) for x in read(cfg['prior_truth'])]
    for t in revised_truth:
        if t['id'] in user:
            t['prior_core_label'] = t['core_label']
            t['core_label'] = user[t['id']]['core_label']
            t['japanese_accuracy'] = 'UNKNOWN'
            t['core_judgment_source'] = 'USER_CURRENT_CORE_LISTENING_REPORT'
    write(root, 'truth-revision.json', {'previous_truth_path': cfg['prior_truth'],
                                       'previous_truth_sha256': verified[cfg['prior_truth']],
                                       'truth': revised_truth})
    print(json.dumps(counts, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
