"""Opt-in one-title replacement. Never called by normal bulk publication.

Dependencies own current holding/NAS witnesses and the existing Stage12
Jellyfin recognizer. Dry-run performs reads only; execute is a separate opt-in.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from teddy_discovery_ko_srt import generate_korean_srt
from teddy_discovery_subtitle import derive_target_ko_relative
from teddy_discovery_subtitle_text import parse_subtitle_bytes, MAX_SUBTITLE_BYTES
from teddy_discovery_subtitle_replace import ReplacementWitness
from teddy_discovery_stage12_rollout import (
    _preflight_artifact_bundle, _safe_artifact_root, _record_video,
    _read_local_regular, _validate_reconciliation_evidence,
    Stage12PublicationReconciliationEvidence,
)
from teddy_discovery_stage12_batch import Stage12JellyfinRecognition

AUTHORIZATION_MODE = 'OPERATOR_APPROVED_SINGLE_TITLE_REPLACEMENT'
FINGERPRINT_FIELDS = ('holding_identity','media_path_identity','source_size_bytes','source_mtime_ns')


class ReplacementError(ValueError):
    """Replacement rejected without exposing model or transport output."""


class UnexpectedNASState(ReplacementError):
    """An exact intent encountered neither its old nor its new SHA."""
    def __init__(self, plan, sha256):
        super().__init__('unexpected NAS SHA; operator investigation required')
        self.plan, self.sha256 = plan, sha256


@dataclass(frozen=True)
class ReplacementAuthorization:
    dvd_id: str
    expected_old_sha256: str
    expected_new_sha256: str
    mode: str
    approval_note: str


def validate_authorization(value, dvd_id, old_sha, new_sha):
    if (type(value) is not ReplacementAuthorization or value.mode != AUTHORIZATION_MODE
            or value.dvd_id != dvd_id or value.expected_old_sha256 != old_sha
            or value.expected_new_sha256 != new_sha or type(value.approval_note) is not str
            or not value.approval_note.strip() or len(value.approval_note) > 2048
            or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in value.approval_note)):
        raise ReplacementError('exact one-title operator authorization required')
    if (any(type(v) is not str or re.fullmatch('[0-9a-f]{64}', v) is None for v in (old_sha,new_sha))
            or old_sha == new_sha):
        raise ReplacementError('distinct exact old/new SHA required')


def operation_identity(plan):
    value = {k:v for k,v in plan.items() if k != 'operation_id'}
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def validate_plan(value):
    fields = {'dvd_id','operation_id','destination_relative','old_sha256','new_sha256',
              'artifact_path','report_path','report_sha256','source_fingerprint','approval_note','operator_approved'}
    if type(value) is not dict or set(value) != fields:
        raise ReplacementError('invalid replacement intent')
    plan = json.loads(json.dumps(value,sort_keys=True))
    from teddy_discovery_stage12_rollout import _validated_dvd_id, _canonical_video_for_state
    _validated_dvd_id(plan['dvd_id'])
    fp = plan['source_fingerprint']
    if type(fp) is not dict or set(fp) != set(FINGERPRINT_FIELDS):
        raise ReplacementError('invalid replacement fingerprint')
    if (type(fp['holding_identity']) is not str or not fp['holding_identity']
            or type(fp['source_size_bytes']) is not int or fp['source_size_bytes'] <= 0
            or type(fp['source_mtime_ns']) is not int or fp['source_mtime_ns'] < 0):
        raise ReplacementError('invalid replacement fingerprint values')
    video = _canonical_video_for_state(plan['dvd_id'],fp['media_path_identity'])
    if plan['destination_relative'] != derive_target_ko_relative(video):
        raise ReplacementError('noncanonical replacement destination')
    for field in ('old_sha256','new_sha256','report_sha256','operation_id'):
        if type(plan[field]) is not str or re.fullmatch('[0-9a-f]{64}',plan[field]) is None:
            raise ReplacementError('invalid replacement digest')
    if plan['old_sha256'] == plan['new_sha256'] or plan['operator_approved'] is not True:
        raise ReplacementError('invalid replacement approval')
    for field in ('artifact_path','report_path'):
        if type(plan[field]) is not str or not Path(plan[field]).is_absolute() or '..' in Path(plan[field]).parts:
            raise ReplacementError('invalid replacement candidate path')
    if plan['operation_id'] != operation_identity(plan):
        raise ReplacementError('detached replacement operation identity')
    return plan


@dataclass(frozen=True)
class ReplacementPreflight:
    plan: dict
    artifact: object
    video: object
    witness: ReplacementWitness
    previous_event: dict | None


class Stage12Replacement:
    def __init__(self, store, *, current_record, nas, jellyfin_recognizer):
        self.store, self.current_record, self.nas = store, current_record, nas
        self.jellyfin_recognizer = jellyfin_recognizer

    def preflight(self, dvd_id, *, expected_old_sha256, expected_new_sha256,
                  candidate_root, authorization):
        validate_authorization(authorization,dvd_id,expected_old_sha256,expected_new_sha256)
        original = self.store.read_replacement_original(dvd_id)
        if original.status != 'PUBLISHED':
            raise ReplacementError('replacement requires PUBLISHED')
        state = self.store.effective_publication(dvd_id)
        record = self.current_record(dvd_id)
        record.__post_init__()
        if record.dvd_id != dvd_id or any(getattr(record,k) != getattr(state,k) for k in FINGERPRINT_FIELDS):
            raise ReplacementError('replacement source fingerprint drift')
        video = _record_video(record)
        destination = derive_target_ko_relative(video)
        if state.destination_relative != destination:
            raise ReplacementError('replacement destination is not canonical')
        root = _safe_artifact_root(candidate_root)
        artifact_path,report_path,new_sha,report_sha = _preflight_artifact_bundle(record,root)
        if new_sha != expected_new_sha256:
            raise ReplacementError('candidate SHA differs from authorization')
        payload = _read_local_regular(artifact_path,max_bytes=MAX_SUBTITLE_BYTES)
        artifact = generate_korean_srt(parse_subtitle_bytes(payload,'srt').cues)
        if artifact.sha256 != new_sha:
            raise ReplacementError('candidate changed during preflight')
        plan = dict(dvd_id=dvd_id,destination_relative=destination,old_sha256=expected_old_sha256,
                    new_sha256=new_sha,artifact_path=str(artifact_path),report_path=str(report_path),
                    report_sha256=report_sha,source_fingerprint={k:getattr(record,k) for k in FINGERPRINT_FIELDS},
                    approval_note=authorization.approval_note,operator_approved=True)
        plan['operation_id'] = operation_identity(plan)
        plan = validate_plan(plan)
        history = self.store.replacement_history(dvd_id)
        previous = history[-1] if history and history[-1]['operation_id'] == plan['operation_id'] else None
        if history and previous is None and history[-1]['phase'] != 'COMPLETED':
            raise ReplacementError('another replacement is unresolved')
        if previous is not None and previous['plan'] != plan:
            raise ReplacementError('replacement retry intent differs')
        if previous is not None and previous['phase'] == 'FAILED_TERMINAL':
            raise ReplacementError('replacement requires operator investigation')
        if state.artifact_sha256 != expected_old_sha256 and not (
                previous is not None and state.artifact_sha256 == expected_new_sha256):
            raise ReplacementError('expected old SHA differs from durable effective SHA')
        witness = self.nas.inspect(video,destination)
        if type(witness) is not ReplacementWitness:
            raise ReplacementError('invalid NAS replacement witness')
        witness.__post_init__()
        if (witness.source_size_bytes != record.source_size_bytes
                or witness.source_mtime_ns != record.source_mtime_ns):
            raise ReplacementError('NAS source fingerprint drift')
        # New SHA is accepted only for the exact durable pending operation.
        allowed = {expected_old_sha256}
        if previous is not None:
            allowed.add(expected_new_sha256)
        if witness.sha256 not in allowed:
            raise UnexpectedNASState(plan,witness.sha256)
        if previous is not None and previous['effective_sha256'] == expected_new_sha256 and witness.sha256 != expected_new_sha256:
            raise UnexpectedNASState(plan,witness.sha256)
        return ReplacementPreflight(plan,artifact,video,witness,previous)

    def run(self, dvd_id, *, execute=False, checkpoint=None, **kwargs):
        # Validate before creating any execution lock, journal or NAS/Jellyfin effect.
        validate_authorization(kwargs.get('authorization'),dvd_id,kwargs.get('expected_old_sha256'),kwargs.get('expected_new_sha256'))
        if type(execute) is not bool:
            raise ReplacementError('execute must be an explicit boolean')
        if not execute:
            return self.preflight(dvd_id,**kwargs)
        with self.store.replacement_execution_lock(dvd_id):
            try:
                checked = self.preflight(dvd_id,**kwargs)
            except UnexpectedNASState as error:
                history = self.store.replacement_history(dvd_id)
                if (history and history[-1]['operation_id'] == error.plan['operation_id']
                        and history[-1]['phase'] not in {'COMPLETED','FAILED_TERMINAL'}):
                    self.store.append_replacement(error.plan,'FAILED_TERMINAL',
                        expected_sequence=len(history),nas_sha256=error.sha256,
                        authorization=kwargs['authorization'])
                raise
            plan = checked.plan
            last = checked.previous_event
            if last and last['phase'] == 'COMPLETED':
                return last
            sequence = len(self.store.replacement_history(dvd_id))
            def append(phase, **evidence):
                nonlocal sequence,last
                last = self.store.append_replacement(plan,phase,expected_sequence=sequence,
                                                     authorization=kwargs['authorization'],**evidence)
                sequence += 1
                return last
            if last is None:
                append('INTENT_RECORDED')
            if checkpoint:
                checkpoint('after_intent')
            if last['phase'] in {'INTENT_RECORDED','FAILED_RETRYABLE'} and last['effective_sha256'] != plan['new_sha256']:
                append('NAS_PENDING')
            if last['phase'] == 'NAS_PENDING':
                try:
                    if checked.witness.sha256 == plan['old_sha256']:
                        self.nas.replace(checked.video,checked.artifact,expected_old_sha256=plan['old_sha256'],
                                         expected_new_sha256=plan['new_sha256'],operation_id=plan['operation_id'],
                                         source_witness=checked.witness)
                    else:
                        self.nas.reconcile(checked.video,checked.artifact,expected_old_sha256=plan['old_sha256'],
                                           expected_new_sha256=plan['new_sha256'],operation_id=plan['operation_id'],
                                           source_witness=checked.witness)
                    if checkpoint:
                        checkpoint('after_nas_replace')
                    witness = self.nas.inspect(checked.video,plan['destination_relative'])
                    if type(witness) is not ReplacementWitness:
                        raise ReplacementError('invalid post-replacement NAS witness')
                    witness.__post_init__()
                    if (witness.sha256 != plan['new_sha256'] or witness.source_size_bytes != checked.witness.source_size_bytes
                            or witness.source_mtime_ns != checked.witness.source_mtime_ns):
                        append('FAILED_TERMINAL',nas_sha256=witness.sha256)
                        raise ReplacementError('post-replacement NAS witness differs')
                    append('NAS_REPLACED',nas_sha256=plan['new_sha256'])
                except ReplacementError:
                    raise
                except Exception as error:
                    append('FAILED_RETRYABLE')
                    raise ReplacementError('NAS replacement pending reconciliation') from error
            if last['phase'] in {'NAS_REPLACED','FAILED_RETRYABLE'}:
                append('JELLYFIN_PENDING',nas_sha256=plan['new_sha256'])
            try:
                recognition = self.jellyfin_recognizer(dvd_id,checked.video,plan['destination_relative'])
                if type(recognition) is not Stage12JellyfinRecognition:
                    raise ReplacementError('invalid Jellyfin recognition')
                recognition.__post_init__()
                evidence = Stage12PublicationReconciliationEvidence(
                    plan['destination_relative'],plan['new_sha256'],recognition.item_id,recognition.item_path,
                    recognition.subtitle_path,recognition.subtitle_language,recognition.subtitle_codec,
                    recognition.external_visible,True)
                from dataclasses import replace
                state = self.store.read_replacement_original(dvd_id)
                _validate_reconciliation_evidence(replace(state,artifact_sha256=plan['new_sha256']),evidence)
                final = self.nas.inspect(checked.video,plan['destination_relative'])
                if type(final) is not ReplacementWitness:
                    raise ReplacementError('invalid final NAS witness')
                final.__post_init__()
                current_record = self.current_record(dvd_id)
                current_record.__post_init__()
                if (final.sha256 != plan['new_sha256']
                        or final.source_size_bytes != plan['source_fingerprint']['source_size_bytes']
                        or final.source_mtime_ns != plan['source_fingerprint']['source_mtime_ns']
                        or current_record.dvd_id != dvd_id
                        or any(getattr(current_record, k) != plan['source_fingerprint'][k]
                               for k in FINGERPRINT_FIELDS)):
                    append('FAILED_TERMINAL',nas_sha256=final.sha256)
                    raise ReplacementError('NAS changed during Jellyfin verification')
            except Exception as error:
                if last['phase'] != 'FAILED_TERMINAL':
                    append('FAILED_RETRYABLE',nas_sha256=plan['new_sha256'])
                raise ReplacementError('Jellyfin replacement verification pending') from error
            return append('COMPLETED',nas_sha256=plan['new_sha256'],jellyfin_evidence=evidence)
