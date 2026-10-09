"""Whole-timeline short-core planning and read-only cache validation; no ASR calls."""
import hashlib
import json
from pathlib import Path
from dataclasses import asdict

from teddy_discovery_asr_audio import ASRAudioChunk, _sample_index_to_ms
from teddy_discovery_asr_remote import RemoteFasterWhisperASR, RemoteASRHTTPResponse
from teddy_discovery_stateful_quality_review import _digest


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      allow_nan=False, separators=(',', ':')).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def offline_client(engine_version):
    def forbidden(*args, **kwargs):
        raise RuntimeError('planning never permits remote ASR transport')
    return RemoteFasterWhisperASR(base_url='http://offline.invalid',
        request_timeout_seconds=1, engine_version=engine_version, transport=forbidden)


def planned_chunk(row, pcm, snapshot):
    """Use absolute samples, including the fractional-ms terminal audio tail."""
    return ASRAudioChunk(snapshot, row['audio_start_ms'], row['audio_end_ms'], 16000,
                         pcm[row['audio_lo']:row['audio_hi']])


def build_short_plan(*, duration_ms, pcm, source_pcm_sha256, source_video_sha256,
                     snapshot, engine_version, settings, external_intervals,
                     core_ms=20000, padding_ms=5000):
    import numpy as np
    for value in (source_pcm_sha256, source_video_sha256):
        _digest(value)
    if (type(duration_ms) is not int or duration_ms <= 0
            or type(core_ms) is not int or core_ms <= 0
            or type(padding_ms) is not int or padding_ms < 0
            or core_ms + 2*padding_ms > 30000):
        raise ValueError('bounded integer duration/core/padding required')
    if (not isinstance(pcm, np.ndarray) or pcm.dtype != np.dtype('<f4')
            or pcm.ndim != 1 or not pcm.flags.c_contiguous or not pcm.size
            or not 0 <= duration_ms*16-pcm.size < 16
            or digest(memoryview(pcm).cast('B')) != source_pcm_sha256):
        raise ValueError('PCM identity/end differs by more than sub-ms quantization')
    if settings.get('vad_filter') is not False:
        raise ValueError('short no-VAD settings required')
    client = offline_client(engine_version)
    rows = []
    for start in range(0, duration_ms, core_ms):
        end = min(duration_ms, start+core_ms)
        lo, hi = max(0,start-padding_ms)*16, min(pcm.size,(end+padding_ms)*16)
        core_lo, core_hi = start*16, min(pcm.size,end*16)
        if not lo <= core_lo < core_hi <= hi:
            raise ValueError('nonempty absolute core sample range required')
        overlaps = [(cid,max(start,a),min(end,b)) for cid,a,b in external_intervals
                    if start < b and a < end]
        covered, cursor = 0, start
        for _, a, b in sorted(overlaps,key=lambda x:x[1]):
            covered += max(0,b-max(cursor,a));cursor=max(cursor,b)
        row = dict(index=len(rows)+1,core_start_ms=start,core_end_ms=end,
            audio_start_ms=_sample_index_to_ms(lo),
            audio_end_ms=max(_sample_index_to_ms(lo)+1,_sample_index_to_ms(hi)),
            audio_end_ms_exact=hi/16,core_lo=core_lo,core_hi=core_hi,audio_lo=lo,audio_hi=hi,
            source_identity=asdict(snapshot),source_pcm_sha256=source_pcm_sha256,
            runtime_identity=asdict(client.runtime_identity),
            source_video_sha256=source_video_sha256,
            JA_relation='NO_EXTERNAL_JA' if not overlaps else
                'FULL_EXTERNAL_OVERLAP' if covered==end-start else 'PARTIAL_EXTERNAL_OVERLAP',
            overlap_external_cue_ids=[cid for cid,a,b in overlaps],
            JA_covered_core_ms=covered, core_ownership='HALF_OPEN_ABSOLUTE_SAMPLES',
            context_policy='PRESERVE_CONTEXT_AND_CROSSING_EVIDENCE_NOT_NEW_UTTERANCE_COUNT',
            reusable=False,requires_new_STT=True,reuse_observations=[],
            audio_verification='UNVERIFIED_AUDIO',approved=False,publishable=False)
        body = client._serialize_chunk(planned_chunk(row,pcm,snapshot))
        row.update(request_sha256=digest(body),request_bytes=len(body),
            slice_pcm_sha256=digest(memoryview(pcm[lo:hi]).cast('B')))
        row['plan_chunk_id']='short-core-'+digest(encode([
            asdict(snapshot),source_pcm_sha256,core_lo,core_hi,lo,hi,settings]))
        rows.append(row)
    return dict(schema_version=1,purpose='whole_video_short_plan_only',duration_ms=duration_ms,
        core_ms=core_ms,padding_ms=padding_ms,source_pcm_sha256=source_pcm_sha256,
        source_video_sha256=source_video_sha256,source_identity=asdict(snapshot),
        source_sample_count=int(pcm.size),terminal_video_audio_difference_ms=duration_ms-pcm.size/16,
        settings=settings,engine_version=engine_version,windows=rows,
        runtime_identity=asdict(client.runtime_identity),
        Gemini_required=False,STT_calls=0,approved=0,publishable=False)


def attach_reusable_results(plan, *, pcm, snapshot, folders):
    """Preserve every eligible observation; cached output is not speech truth."""
    client=offline_client(plan['engine_version'])
    by_window={(r['core_start_ms'],r['core_end_ms'],r['audio_start_ms'],r['audio_end_ms']):r
               for r in plan['windows']}
    rejected=[]
    for folder in folders:
        folder=Path(folder);cfg=json.loads((folder/'inputs.json').read_bytes())
        result=json.loads((folder/'results.json').read_bytes())
        source_ok=(cfg.get('source_snapshot')==plan['source_identity']
            and cfg.get('runtime_identity')==plan['runtime_identity']
            and cfg.get('PCM_sha256',result.get('full_PCM_sha256'))==plan['source_pcm_sha256']
            and cfg.get('PCM_sample_count',result.get('decoded_sample_count'))==plan['source_sample_count']
            and cfg.get('source_video_sha256')==plan['source_video_sha256']
            and cfg.get('settings')==plan['settings'] and result.get('settings')==plan['settings'])
        for status in result['chunk_statuses']:
            record=dict(folder=str(folder),original_index=status['index'],arm=status.get('arm'))
            if (not source_ok or status.get('hallucination_silence_threshold') is not None
                    or status.get('arm','A')!='A'
                    or status['status'] not in ('SUCCEEDED','SUCCEEDED_EMPTY')):
                rejected.append(dict(record,reason='SOURCE_SETTINGS_OR_STATUS_NOT_IDENTICAL'));continue
            if 'core_start_ms' not in status:
                rejected.append(dict(record,reason='DIFFERENT_LONG_CHUNK_CONTEXT'));continue
            key=(status['core_start_ms'],status['core_end_ms'],status['start_ms'],status['end_ms'])
            row=by_window.get(key)
            if row is None:
                rejected.append(dict(record,reason='WINDOW_NOT_IDENTICAL'));continue
            stem=(status['arm']+'-' if 'arm' in status else '')+'chunk-'+str(status['index']).zfill(2)
            try:
                req_path=folder/(stem+'.request.npy');wire_path=folder/(stem+'.wire.json')
                req=req_path.read_bytes();wire=wire_path.read_bytes()
                if (digest(req)!=row['request_sha256'] or digest(req)!=status['request_sha256']
                        or digest(wire)!=status['response_sha256']):
                    raise ValueError('cached SHA mismatch')
                metadata_path=folder/(stem+'.request-metadata.json')
                if metadata_path.exists():
                    metadata=json.loads(metadata_path.read_bytes())
                    if (not metadata['endpoint'].endswith('/v1/asr/transcribe-targeted')
                            or metadata['settings']!=plan['settings']
                            or metadata['hallucination_silence_threshold'] is not None):
                        raise ValueError('cached endpoint/options differ')
                segments=client._decode_response(RemoteASRHTTPResponse(200,wire),
                    chunk=planned_chunk(row,pcm,snapshot),request_body=req,expected_vad_region_count=0)
                if len(segments)!=status['segment_count']:
                    raise ValueError('cached segment count differs')
            except Exception as error:
                rejected.append(dict(record,reason='INVALID_CACHED_EVIDENCE',error_type=type(error).__name__));continue
            row['reuse_observations'].append(dict(record,request_path=str(req_path),response_path=str(wire_path),
                request_sha256=digest(req),response_sha256=digest(wire),segment_count=len(segments),
                wall_seconds=status['wall_seconds'],independent_speech_verification=False))
            row.update(reusable=True,requires_new_STT=False)
    plan['reuse_rejected']=rejected
    plan['reuse_count']=sum(r['reusable'] for r in plan['windows'])
    plan['new_STT_count']=sum(r['requires_new_STT'] for r in plan['windows'])
    return plan
