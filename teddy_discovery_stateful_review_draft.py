"""Non-publishable translation drafts, separate from quality-review decisions."""
import hashlib
import json

from teddy_discovery_stateful_hybrid import _supplemental_reading_key
from teddy_discovery_stateful_quality_review import (
    QualityReviewError, QualityReviewResult, QualityReviewResultCue,
    _digest, _load, _parse, _text,
)


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      allow_nan=False, separators=(',', ':')).encode('utf-8')


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def build_review_draft_request(canonical_request, language_response, cross_evidence):
    """Readings remain hypotheses; no selection, audio verification or approval."""
    original = _load(canonical_request)
    decisions = _parse(language_response, QualityReviewResult, QualityReviewResultCue)
    evidence = _load(cross_evidence)
    if (decisions.request_sha256 != sha(canonical_request)
            or [c.cue_id for c in decisions.cues] != [g['cue_id'] for g in original['groups']]
            or [g['cue_id'] for g in evidence['groups']] != [c.cue_id for c in decisions.cues]):
        raise QualityReviewError('draft inputs detached from canonical judgments')
    groups = []
    for group_index, (group, decision, ev) in enumerate(zip(
            original['groups'], decisions.cues, evidence['groups'], strict=True)):
        if (decision.action != 'AMBIGUOUS' or ev['approved'] or ev['srt_eligible']
                or ev['Japanese_accuracy'] != 'UNVERIFIED'
                or (ev['estimated_start_ms'], ev['estimated_end_ms']) != (group['start_ms'], group['end_ms'])):
            raise QualityReviewError('unapproved AMBIGUOUS evidence required')
        readings = {}

        def add(text, family, path):
            _text(text)
            key = _supplemental_reading_key(text)
            if not key:
                return
            reading = readings.setdefault(key, dict(
                reading_id='reading-' + sha(key.encode()), ja_candidate=text, evidence=[],
                alignment_status='UNTIMED_CLIP_TURN_MAY_BE_NEIGHBOR'))
            if family == 'Whisper':
                reading['alignment_status'] = 'ASR_ESTIMATED_TARGET_OVERLAP_NOT_VERIFIED'
            elif family == 'ReazonSpeech' and not reading['evidence']:
                reading['alignment_status'] = 'CLIP_TEXT_ONLY_ALIGNMENT_UNVERIFIED'
            # All observations preserved; their count is not independent support.
            source = evidence
            for key in path:
                source = source[key]
            reading['evidence'].append(dict(source_family=family, original_ja=text,
                source_ref=path, source_sha256=sha(encode(source))))

        for index, obs in enumerate(ev['Whisper_large_v3_observations']):
            add(obs['segment']['text'], 'Whisper', ['groups', group_index, 'Whisper_large_v3_observations', index])
        for index, obs in enumerate(ev['Whisper_medium_observations']):
            if obs['start_ms'] < group['end_ms'] and group['start_ms'] < obs['end_ms']:
                add(obs['text'], 'Whisper', ['groups', group_index, 'Whisper_medium_observations', index])
        add(ev['Reazon_audio_evidence']['observation']['text'], 'ReazonSpeech',
            ['groups', group_index, 'Reazon_audio_evidence'])
        for index, turn in enumerate(ev['Gemini_clip_evidence']['turns']):
            add(turn['stt_ja'], 'Gemini', ['groups', group_index, 'Gemini_clip_evidence', 'turns', index])
        groups.append(dict(
            cue_id=group['cue_id'], original_judgment=json.loads(encode(decision.__dict__)),
            source_pcm_sha256=ev['source_pcm_sha256'],
            estimated_start_ms=group['start_ms'], estimated_end_ms=group['end_ms'],
            timing_status='ASR_ESTIMATED_NOT_AUDIO_VERIFIED',
            utterance_alignment='UNVERIFIED', human_speech_presence=ev['human_speech_presence'],
            Japanese_accuracy='UNVERIFIED', interpretations=list(readings.values()),
            publishable=False))
    request = dict(
        schema_version=1, purpose='supplemental_review_draft_only',
        canonical_request_sha256=sha(canonical_request), language_response_sha256=sha(language_response),
        cross_evidence_sha256=sha(cross_evidence), publishable=False, groups=groups,
        # Retain all adjacent JA/KO, broader readings, unresolved overlaps and control warnings.
        canonical_context=original, cross_evidence_context=evidence,
        instruction=(
            'Generate conditional Korean review drafts for these existing Japanese STT hypotheses. '
            'Do not perform or change KEEP/REPAIR/OMIT/AMBIGUOUS judgments. All original judgments '
            'remain AMBIGUOUS; these drafts are not replacement_ko or publication inputs. '
            'No audio is provided. Do not claim to have listened, verified Japanese, speakers or '
            'timing. Agreement is cross evidence, not accuracy; repeated clips are not independent '
            'utterances. Gemini turns are untimed: they may be neighboring utterances rather than '
            'alternatives for this cue. Explain that uncertainty, and use ko_draft=null if a '
            'conditional translation cannot be supported. Preserve each listed reading_id and '
            'ja_candidate exactly; do not invent, merge or select a Japanese winner. '
            'Keep word/meaning conflicts and original timing uncertainty visible. Negative controls '
            'are defense context only and never draft cues. Do not use tools. '
            'Return only JSON with exactly schema_version=1, purpose=review_draft_only, '
            'request_sha256 (the provided SHA of this exact draft request), publishable=false, '
            'and drafts. One draft per group in original order, with exactly cue_id, '
            'conflict_note, interpretations. Each interpretation in supplied order has exactly '
            'reading_id, ja_candidate, ko_draft (Korean string or null), unresolved_reason. '
            'Never return action, approvals, new timestamps or audio-verification claims.'),
    )
    raw = encode(request)
    _load(raw)
    return raw


def parse_review_draft_result(payload, request):
    """Strict separate artifact. Never returns a canonical result or approved cue."""
    expected = _load(request)
    result = _load(payload)
    if (set(result) != {'schema_version', 'purpose', 'request_sha256', 'publishable', 'drafts'}
            or type(result['schema_version']) is not int or result['schema_version'] != 1
            or result['purpose'] != 'review_draft_only' or result['publishable'] is not False):
        raise QualityReviewError('exact non-publishable draft result required')
    _digest(result['request_sha256'])
    if result['request_sha256'] != sha(request):
        raise QualityReviewError('draft request SHA mismatch')
    drafts = result['drafts']
    if type(drafts) is not list or len(drafts) != len(expected['groups']):
        raise QualityReviewError('exact draft group count required')
    enriched = []
    for item, group in zip(drafts, expected['groups'], strict=True):
        if (type(item) is not dict or set(item) != {'cue_id', 'conflict_note', 'interpretations'}
                or item['cue_id'] != group['cue_id']):
            raise QualityReviewError('draft group identity/order mismatch')
        _text(item['conflict_note'])
        variants = item['interpretations']
        if type(variants) is not list or len(variants) != len(group['interpretations']):
            raise QualityReviewError('all Japanese alternatives required')
        checked = []
        for variant, source in zip(variants, group['interpretations'], strict=True):
            if (type(variant) is not dict or set(variant) != {
                    'reading_id', 'ja_candidate', 'ko_draft', 'unresolved_reason'}
                    or variant['reading_id'] != source['reading_id']
                    or variant['ja_candidate'] != source['ja_candidate']):
                raise QualityReviewError('draft Japanese hypothesis changed')
            if variant['ko_draft'] is not None:
                _text(variant['ko_draft'])
            _text(variant['unresolved_reason'])
            references = []
            for ref in source['evidence']:
                observation = expected['cross_evidence_context']
                for key in ref['source_ref']:
                    observation = observation[key]
                if sha(encode(observation)) != ref['source_sha256']:
                    raise QualityReviewError('draft STT reference detached')
                references.append(dict(ref, source=observation))
            checked.append(dict(variant, evidence=references,
                                alignment_status=source['alignment_status'], publishable=False))
        enriched.append(dict(
            cue_id=item['cue_id'], conflict_note=item['conflict_note'], interpretations=checked,
            original_judgment=group['original_judgment'],
            source_pcm_sha256=group['source_pcm_sha256'],
            estimated_start_ms=group['estimated_start_ms'], estimated_end_ms=group['estimated_end_ms'],
            timing_status=group['timing_status'], utterance_alignment=group['utterance_alignment'],
            human_speech_presence=group['human_speech_presence'], Japanese_accuracy='UNVERIFIED',
            audio_verification='UNVERIFIED_AUDIO', approved=False, srt_eligible=False, publishable=False))
    return dict(schema_version=1, purpose='review_draft_only', request_sha256=sha(request),
                canonical_request_sha256=expected['canonical_request_sha256'],
                language_response_sha256=expected['language_response_sha256'],
                cross_evidence_sha256=expected['cross_evidence_sha256'],
                publishable=False, approved=False, groups=enriched)
