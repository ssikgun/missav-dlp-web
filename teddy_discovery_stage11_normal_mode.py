"""Unattended external-JA Normal Mode using existing Stage11 boundaries.

No supplemental candidate can enter playback. Stage12 alone publishes. Native
Hermes runs in a fresh isolated profile with the previously proven zero-tool
configuration; deterministic package IDs are independent of native runtime IDs.
"""
from __future__ import annotations

import argparse
import base64
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import uuid
from collections import Counter

import teddy_discovery_stage11_controller as controller
from teddy_discovery_alignment_acceptance import AlignmentAcceptancePolicy
from teddy_discovery_stage11_deployment import SSHRemoteHermesBridge, Stage11DeploymentTransportError
from teddy_discovery_stage11_deployment import QUALITY_REVIEW_EXECUTION_RECEIPT_MAX_BYTES
from teddy_discovery_asr import ASRError
from teddy_discovery_stage11_live_adapters import _align_external_payload
from teddy_discovery_stateful_boundary import (
    bind_stateful_absorption_preparation, serialize_stateful_boundary_evidence,
    validate_stateful_absorption,
)
from teddy_discovery_stateful_absorption_review import (
    AbsorptionGroupReviewError,
    AbsorptionGroupReviewExecutionEvidence,
    build_absorption_group_review_request,
    serialize_absorption_group_review_request,
    validate_absorption_group_review_execution,
)
from teddy_discovery_stateful_controller import build_stateful_whole_title_query, build_stateful_part_query
from teddy_discovery_stateful_hybrid import prepare_stateful_hybrid
from teddy_discovery_stateful_parts import build_stateful_part_plan, parse_stateful_part, assemble_stateful_result, serialize_stateful_part, _validated_output_cue
from teddy_discovery_stateful_translator import (
    serialize_stateful_package, serialize_stateful_model_input, serialize_stateful_result,
    parse_stateful_result, stateful_session_id_for_package,
    bind_stateful_model_input_generation_key,
    STATEFUL_TRANSLATOR_EXECUTABLE, STATEFUL_TRANSLATOR_PROVIDER,
    STATEFUL_TRANSLATOR_MODEL, STATEFUL_TRANSLATOR_REASONING,
)
from teddy_discovery_subtitle import SubtitleCandidate
from teddy_discovery_subtitle_external import ExternalSubtitlePayload
from teddy_discovery_subtitle_source_quality import classify_source_document, OMIT_METADATA
from teddy_discovery_subtitle_text import SubtitleCue, MAX_SUBTITLE_BYTES

PROOF_NAME = 'normal-mode-proof-v1.json'
SOURCE_NAME = 'normal-mode-source-v1.json'
GROUP_REVIEW_REQUEST_NAME = 'absorption-group-review-request-v1.json'
GROUP_REVIEW_RESULT_NAME = 'absorption-group-review-result-v1.json'
GROUP_REVIEW_RECEIPT_NAME = 'absorption-group-review-receipt-v1.json'
GROUP_REVIEW_PROVENANCE_NAME = 'absorption-group-review-provenance-v1.json'
USER_INTERVENTION = 0
AUTO_INSERT = False
MAX_NATIVE_PROMPT_BYTES = 128000
MAX_VALIDATION_ATTEMPTS = 2  # Existing native semantic validation retry bound.
NATIVE_ABSOLUTE_TIMEOUT = 3600
NATIVE_INACTIVITY_TIMEOUT = 600
TIRITH_WARNING = ('  ⚠ tirith security scanner enabled but not available '
                  '— command scanning will use pattern matching only\r\n').encode()
# Byte-identical to the previously verified canary277 tool-free profile. No auth.
NATIVE_CONFIG = {"agent":{"disabled_toolsets":["all","memory"],"environment_probe":False,
    "intent_ack_continuation":False,"reasoning_effort":"xhigh","tool_use_enforcement":False},
    "compression":{"enabled":False},"context":{"engine":"compressor"},
    "display":{"interface":"cli","streaming":False},"fallback_providers":[],"mcp_servers":{},
    "memory":{"memory_enabled":False,"provider":"","user_profile_enabled":False},
    "model":{"default":"gpt-5.6-luna","provider":"openai-codex"},
    "platform_toolsets":{"cli":[]},"plugins":{"enabled":[]},"terminal":{"cwd":".","env_type":"local"}}


def wire(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def store(path, raw):
    return controller._install_or_reuse(path, raw, max_bytes=16 * 1024 * 1024)


# Reuses the established fresh chat -Q/stdout transport and isolated config/auth
# lifecycle. Unlike the obsolete UUID --resume path, no session DB is preminted.
REMOTE_NATIVE = r'''
import base64, hashlib, json, os, selectors, signal, subprocess, sys, time
from pathlib import Path
req=json.load(sys.stdin)
root=Path(req['root']); root.mkdir(mode=0o700)
profile=root/'profiles'/'subtitle-translator'; profile.mkdir(parents=True,mode=0o700)
task=root/'work'; task.mkdir(mode=0o700)
for p in (root,profile):
    (p/'.no-bundled-skills').write_text(''); (p/'skills').mkdir(mode=0o500)
source=Path(req['source_profile']); copied=False
for src,dst in ((source.parent.parent,root),(source,profile)):
    p=src/'auth.json'
    if p.exists():
        assert p.is_file() and not p.is_symlink()
        fd=os.open(dst/'auth.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as f: f.write(p.read_bytes())
        copied=True
assert copied,'Hermes authentication unavailable'
(profile/'config.yaml').write_bytes(base64.b64decode(req['config']))
prompt=base64.b64decode(req['prompt']); assert len(prompt)<=128000
(task/'prompt.txt').write_bytes(prompt)
os.umask(0o077)
env={'HOME':str(Path.home()),'PATH':'/home/teddy/.hermes/hermes-agent/venv/bin:/usr/local/bin:/usr/bin:/bin',
     'LANG':'C.UTF-8','HERMES_HOME':str(root),'PYTHONDONTWRITEBYTECODE':'1'}
base=[req['executable'],'--profile','subtitle-translator']
check=subprocess.run(base+['prompt-size','--json'],cwd=task,env=env,capture_output=True,timeout=30)
(task/'tools-check.stdout').write_bytes(check.stdout); (task/'tools-check.stderr').write_bytes(check.stderr)
assert check.returncode==0 and json.loads(check.stdout)['tools']['count']==0,'native tools must be zero'
command=base+['chat','-Q','--ignore-rules','--provider',req['provider'],'--model',req['model'],
              '--reasoning',req['reasoning'],'--max-turns','1','-q',prompt.decode()]
started=time.monotonic(); last=started; reason=None
proc=subprocess.Popen(command,cwd=task,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
streams={'stdout':bytearray(),'stderr':bytearray()}
selector=selectors.DefaultSelector()
for name,s in (('stdout',proc.stdout),('stderr',proc.stderr)):
    os.set_blocking(s.fileno(),False); selector.register(s,selectors.EVENT_READ,name)
while selector.get_map() or proc.poll() is None:
    now=time.monotonic()
    if now-started>=3600 or now-last>=600:
        reason='ABSOLUTE_TIMEOUT' if now-started>=3600 else 'INACTIVITY_TIMEOUT'; break
    for key,_ in selector.select(timeout=1):
        chunk=os.read(key.fileobj.fileno(),65536)
        if not chunk: selector.unregister(key.fileobj)
        else:
            streams[key.data].extend(chunk); last=time.monotonic()
            if sum(map(len,streams.values()))>16*1024*1024: reason='OUTPUT_LIMIT'; break
    if reason: break
if reason:
    os.killpg(proc.pid,signal.SIGTERM)
    try: proc.wait(timeout=5)
    except subprocess.TimeoutExpired: os.killpg(proc.pid,signal.SIGKILL); proc.wait(timeout=5)
rc=proc.wait(timeout=5)
for name,b in streams.items(): (task/(name+'.log')).write_bytes(b)
assert hashlib.sha256((task/'prompt.txt').read_bytes()).hexdigest()==req['prompt_sha256']
for p in (root,profile): assert not any((p/'skills').iterdir())
print(json.dumps({'stdout':base64.b64encode(streams['stdout']).decode(),
    'stderr':base64.b64encode(streams['stderr']).decode(),'returncode':rc,
    'timeout_reason':reason,'tools_count':0,'elapsed_seconds':time.monotonic()-started,'remote_root':str(root)}))
'''


def native_prompt(query, package, *, part_ids=None):
    # Keep the same canonical semantic query and explicit identity contract.
    # Inline the deterministic model-input projection for the zero-tool CLI.
    data = json.loads(serialize_stateful_model_input(package))
    if part_ids is not None:
        selected = set(part_ids)
        # Whole-title external text remains read-only context in bounded fallback.
        data['whole_title_ja_context'] = [{'cue_id':c['cue_id'],'external_ja':c['external_ja']} for c in data['cues']]
        data['cues'] = [c for c in data['cues'] if c['cue_id'] in selected]
    def encode(data):
        return (query + '\nNATIVE_STDOUT_CONTRACT: This tool-free execution supplies the input inline. '
        'Do not read or write files or call tools. Return only the required JSON envelope on stdout; '
        'the external controller validates and saves it. The embedded input replaces any file-reading '
        'instruction above. External JA is the text backbone. Never overwrite coherent external JA '
        'with uncertain STT. Preserve supported dialogue when uncertain. Do not add missing dialogue. '
        'No user questions or approval requests.\nINLINE_MODEL_INPUT=' + wire(data).decode()).encode()
    prompt=encode(data)
    if part_ids is not None and len(prompt)>MAX_NATIVE_PROMPT_BYTES:
        # Fall back to the existing cue-local/neighbor context already carried
        # by each semantic input cue; never drop any requested source/output ID.
        data.pop('whole_title_ja_context')
        data['context_scope']='PART_AND_RETAINED_ORIGINAL_NEIGHBORS'
        prompt=encode(data)
    return prompt


class NativeNormalFirstPass:
    def __init__(self, bridge):
        self.bridge = bridge

    def invoke(self, prompt, directory, label, validator):
        if len(prompt) > MAX_NATIVE_PROMPT_BYTES:
            raise controller.Stage11ControllerValidationError('native prompt exceeds established byte bound')
        last_error = None
        for attempt in range(1, MAX_VALIDATION_ATTEMPTS + 1):
            prefix = directory / f'{label}-attempt-{attempt}'
            receipt_path = prefix.with_suffix('.receipt.json')
            if receipt_path.exists():
                receipt = json.loads(controller._read_private_file(receipt_path,max_bytes=1024*1024))
                stdout = controller._read_private_file(prefix.with_suffix('.stdout'),max_bytes=16*1024*1024)
            else:
                request = {'root':'/tmp/stage11-normal-hermes-'+uuid.uuid4().hex,
                    'source_profile':'/home/teddy/.hermes/profiles/subtitle-translator',
                    'config':base64.b64encode(wire(NATIVE_CONFIG)).decode(),
                    'prompt':base64.b64encode(prompt).decode(),'prompt_sha256':sha(prompt),
                    'executable':STATEFUL_TRANSLATOR_EXECUTABLE,'provider':STATEFUL_TRANSLATOR_PROVIDER,
                    'model':STATEFUL_TRANSLATOR_MODEL,'reasoning':STATEFUL_TRANSLATOR_REASONING}
                store(prefix.with_suffix('.prompt.txt'),prompt)
                raw = self.bridge._python(REMOTE_NATIVE,input_payload=wire(request),capture=True,timeout=NATIVE_ABSOLUTE_TIMEOUT+90)
                receipt=json.loads(raw)
                stdout=base64.b64decode(receipt.pop('stdout'),validate=True)
                stderr=base64.b64decode(receipt.pop('stderr'),validate=True)
                store(prefix.with_suffix('.stdout'),stdout or b'\n')
                store(prefix.with_suffix('.stderr'),stderr or b'\n')
                runtime=re.findall(rb'^session_id: (\d{8}_\d{6}_[a-f0-9]{6})\s*$',stderr,re.M)
                receipt.update(prompt_sha256=sha(prompt),stdout_sha256=sha(stdout),stderr_sha256=sha(stderr),
                    runtime_session_id=runtime[0].decode() if len(runtime)==1 else None,
                    provider=STATEFUL_TRANSLATOR_PROVIDER,model=STATEFUL_TRANSLATOR_MODEL,
                    reasoning=STATEFUL_TRANSLATOR_REASONING,attempt=attempt)
                store(receipt_path,wire(receipt))
            if receipt['prompt_sha256']!=sha(prompt) or receipt['stdout_sha256']!=sha(stdout):
                raise controller.Stage11ControllerArtifactError('native receipt detached from prompt/output')
            if receipt['returncode']!=0 or receipt['timeout_reason'] is not None:
                raise controller.Stage11ControllerError('native Hermes execution failed: '+str(receipt['timeout_reason'] or receipt['returncode']))
            if receipt['tools_count']!=0 or receipt['runtime_session_id'] is None:
                raise controller.Stage11ControllerArtifactError('native execution provenance invalid')
            clean=stdout[len(TIRITH_WARNING):] if stdout.startswith(TIRITH_WARNING) else stdout
            try:
                return validator(clean)
            except ValueError as error:
                last_error=error
                store(prefix.with_suffix('.validation-error.json'),wire({'error_type':type(error).__name__,
                    'reason':str(error),'attempt':attempt,'user_intervention':0}))
        raise controller.Stage11ControllerValidationError('bounded native output validation retries exhausted') from last_error

    def __call__(self, package, *, route, staging_root, boundary_evidence, **unused):
        directory=controller._title_directory(Path(staging_root),package.dvd_id)
        raw=serialize_stateful_package(package)
        store(directory/'stage11-authoritative-input.json',raw)
        store(directory/'stage11-semantic-input.json',serialize_stateful_model_input(package))
        store(directory/'stage11-boundary-evidence-v1.json',serialize_stateful_boundary_evidence(boundary_evidence))
        result_path=directory/'stage11-semantic-result.json'
        validator=lambda data:validate_normal_translation(data,package,boundary_evidence)
        if result_path.exists():
            return validator(controller._read_private_file(result_path,max_bytes=16*1024*1024))
        prompt=native_prompt(build_stateful_whole_title_query(package,boundary_evidence=boundary_evidence),package)
        result=None
        if len(prompt)<=MAX_NATIVE_PROMPT_BYTES:
            try:
                result=self.invoke(prompt,directory,'whole-title',validator)
            except controller.Stage11ControllerError as error:
                store(directory/'whole-title-fallback.json',wire({'policy':'EXISTING_FIXED_64',
                    'reason':str(error),'error_type':type(error).__name__,'user_intervention':0}))
        if result is None:
            model=serialize_stateful_model_input(package)
            plan=build_stateful_part_plan(package,model,boundary_evidence=boundary_evidence)
            parts=[]
            for part in plan.parts:
                query=build_stateful_part_query(package,model,part.part_index,boundary_evidence=boundary_evidence)
                prompt=native_prompt(query,package,part_ids=part.cue_ids)
                validated=self.invoke(prompt,directory,f'part-{part.part_index:04d}',
                    lambda data,part=part:parse_stateful_part(data,part,plan))
                store(directory/part.canonical_filename,serialize_stateful_part(validated))
                parts.append(validated)
            result=assemble_stateful_result(directory,package,plan)
        store(result_path,serialize_stateful_result(result))
        return validator(serialize_stateful_result(result))


def prepare_normal(route, baseline_sha, claim_token):
    key=controller.bind_stateful_policy_generation_key(
        bind_stateful_model_input_generation_key('stage11-normal-v1-'+baseline_sha),
        controller.DEFAULT_STATEFUL_SEMANTIC_POLICY)
    return bind_stateful_absorption_preparation(prepare_stateful_hybrid(route,generation_key=key,claim_token=claim_token))


def validate_normal_translation(raw, package, boundary):
    result=parse_stateful_result(raw,package,boundary_evidence=boundary)
    # Reuse fixed-part source-aware text guards for the whole-title envelope.
    for i,(cue,source) in enumerate(zip(result.cues,package.cues,strict=True),1):
        _validated_output_cue(cue,source_cue=source,cue_ordinal=i)
    return result


def _require_review_provenance(result, *, source_session_id, label):
    if (result.source_translation_session_id != source_session_id
            or not result.review_execution_session_id):
        raise controller.Stage11ControllerArtifactError(
            label + ' lacks source or execution session provenance')
    try:
        from teddy_discovery_quality_review_session import (
            validate_canonical_review_execution_session_id,
        )
        validate_canonical_review_execution_session_id(
            result.review_execution_session_id)
    except Exception as error:
        raise controller.Stage11ControllerArtifactError(
            label + ' execution session ID is invalid') from error


def _normal_review_evidence(directory, preparation, first, baseline, baseline_sha256,
                            staging_root, *, hybrid_review_runner=None,
                            hybrid_targeted_runner=None, create_missing=True,
                            targeted_reused_hint=None):
    document = preparation.route_decision.alignment_application.bundle.external_ja_document
    source_quality = classify_source_document(document)
    originals = dict(preparation=preparation, package=preparation.package,
                     result=first, source_quality=source_quality)
    triage_request = controller.build_review_request(**originals)
    targeted_path = directory / 'hybrid-suspect-asr-v1.json'
    targeted_existed = targeted_path.exists() or targeted_path.is_symlink()
    request, merged, context = controller._run_hybrid_suspect_review(
        directory=directory, preparation=preparation, first_pass=first,
        source_quality=source_quality, targeted_artifact=None,
        asr_result=baseline, baseline_sha256=baseline_sha256,
        hybrid_review_runner=hybrid_review_runner,
        hybrid_targeted_runner=hybrid_targeted_runner,
        staging_root=staging_root, create_missing=create_missing,
    )

    triage_raw = controller._read_private_file(
        directory / 'hybrid-triage-v1.json', max_bytes=controller.MAX_REVIEW_BYTES)
    triage = controller.parse_review_result(triage_raw, triage_request)
    _require_review_provenance(
        triage, source_session_id=first.session_id, label='HYBRID triage')
    targets = controller.select_suspect_cue_ids(triage_request, triage)
    targeted = None
    if targets:
        targeted_raw = controller._read_private_file(
            targeted_path, max_bytes=controller.MAX_TARGETED_ASR_ARTIFACT_BYTES)
        targeted = controller.parse_targeted_asr_artifact_bytes(targeted_raw)
        target_raw = controller._read_private_file(
            directory / 'hybrid-final-target-v1.json',
            max_bytes=controller.MAX_REVIEW_BYTES)
        target_result = controller.parse_review_result(
            target_raw, request, target_cue_ids=targets)
        _require_review_provenance(
            target_result, source_session_id=first.session_id,
            label='HYBRID targeted review')
        target_execution_session_id = target_result.review_execution_session_id
    else:
        target_execution_session_id = triage.review_execution_session_id

    final_request_raw = controller._read_private_file(
        directory / 'hybrid-final-request-v1.json',
        max_bytes=controller.MAX_REVIEW_BYTES)
    final_result_raw = controller._read_private_file(
        directory / 'hybrid-final-review-v1.json',
        max_bytes=controller.MAX_REVIEW_BYTES)
    if (final_request_raw != controller.serialize_review_request(request)
            or final_result_raw != controller.serialize_review_result(merged, request)):
        raise controller.Stage11ControllerArtifactError(
            'HYBRID review composition differs from validated evidence')
    controller.validate_review_result(merged, request)
    if targets:
        from teddy_discovery_targeted_asr_window import (
            plan_targeted_asr_windows_with_policy,
        )
        application = preparation.route_decision.alignment_application
        windows = plan_targeted_asr_windows_with_policy(
            document.cues, application.alignment,
            policy=controller.STAGE11_TARGETED_SECOND_EVIDENCE_WINDOW_POLICY_V1,
            target_cue_ids=targets,
        )
        targeted_provenance_raw = controller._read_private_file(
            directory / 'hybrid-suspect-context-v1.json',
            max_bytes=controller.MAX_REVIEW_BYTES)
        target_count = len(targets)
        window_count = len(windows)
        targeted_sha256 = sha(targeted_raw)
        targeted_provenance_sha256 = sha(targeted_provenance_raw)
        targeted_reused = (targeted_reused_hint if not create_missing
                            else targeted_existed)
        if type(targeted_reused) is not bool:
            raise controller.Stage11ControllerArtifactError(
                'targeted ASR reuse provenance is invalid')
    else:
        target_count = 0
        window_count = 0
        targeted_sha256 = None
        targeted_provenance_sha256 = None
        targeted_reused = None

    evidence = {
        'translation_result_sha256': sha(serialize_stateful_result(first)),
        'source_translation_session_id_sha256': sha(first.session_id.encode()),
        'triage_request_sha256': controller.review_request_sha256(triage_request),
        'triage_result_sha256': sha(triage_raw),
        'triage_review_execution_session_id_sha256': sha(
            triage.review_execution_session_id.encode()),
        'review_request_sha256': sha(final_request_raw),
        'review_result_sha256': sha(final_result_raw),
        'review_execution_session_id_sha256': sha(
            target_execution_session_id.encode()),
        'targeted_artifact_sha256': targeted_sha256,
        'targeted_provenance_sha256': targeted_provenance_sha256,
        'targeted_source_count': target_count,
        'targeted_window_count': window_count,
        'targeted_reused': targeted_reused,
        'reviewed_action_counts': dict(sorted(Counter(
            cue.action for cue in merged.cues).items())),
    }
    return source_quality, request, merged, context, evidence


def _normal_group_review_execution(directory, preparation, first, review_request,
                                  review_result, source_quality, raw_asr_context,
                                  *, group_review_runner=None, staging_root=None,
                                  create_missing):
    """Create or replay only the explicit group-review sidecar, never V1."""
    try:
        request = build_absorption_group_review_request(
            preparation=preparation,
            package=preparation.package,
            first_pass_result=first,
            review_request=review_request,
            review_result=review_result,
            source_quality=source_quality,
            raw_asr_context=raw_asr_context,
        )
    except AbsorptionGroupReviewError as error:
        raise controller.Stage11ControllerArtifactError(
            'absorption group review scope is invalid') from error

    paths = {
        'request': directory / GROUP_REVIEW_REQUEST_NAME,
        'result': directory / GROUP_REVIEW_RESULT_NAME,
        'receipt': directory / GROUP_REVIEW_RECEIPT_NAME,
        'provenance': directory / GROUP_REVIEW_PROVENANCE_NAME,
    }
    present = {
        key: path.exists() or path.is_symlink()
        for key, path in paths.items()
    }
    if request is None:
        if any(present.values()):
            raise controller.Stage11ControllerArtifactError(
                'unexpected absorption group review artifacts without repair scope')
        return None

    if any(present.values()):
        if not all(present.values()):
            raise controller.Stage11ControllerArtifactError(
                'absorption group review evidence is incomplete')
        request_raw = controller._read_private_file(
            paths['request'], max_bytes=16 * 1024 * 1024)
        result_raw = controller._read_private_file(
            paths['result'], max_bytes=16 * 1024 * 1024)
        receipt_raw = controller._read_private_file(
            paths['receipt'], max_bytes=QUALITY_REVIEW_EXECUTION_RECEIPT_MAX_BYTES)
        metadata_raw = controller._read_private_file(
            paths['provenance'], max_bytes=64 * 1024)
        try:
            metadata = json.loads(metadata_raw.decode('utf-8'))
        except (UnicodeError, ValueError) as error:
            raise controller.Stage11ControllerArtifactError(
                'absorption group review provenance is malformed') from error
        if (type(metadata) is not dict or set(metadata) != {
                'schema_version', 'remote_task', 'receipt_nonce',
                'review_execution_session_id'}
                or metadata.get('schema_version') != 1
                or wire(metadata) != metadata_raw):
            raise controller.Stage11ControllerArtifactError(
                'absorption group review provenance is noncanonical')
        execution = AbsorptionGroupReviewExecutionEvidence(
            request_payload=request_raw,
            result_payload=result_raw,
            receipt_payload=receipt_raw,
            remote_task=metadata.get('remote_task'),
            receipt_nonce=metadata.get('receipt_nonce'),
            review_execution_session_id=metadata.get(
                'review_execution_session_id'),
        )
    else:
        if not create_missing:
            raise controller.Stage11ControllerArtifactError(
                'completed owner REPAIR lacks group review evidence')
        if not callable(group_review_runner):
            raise controller.Stage11ControllerValidationError(
                'owner REPAIR requires a group review runner')
        execution = group_review_runner(request, staging_root=staging_root)
        if type(execution) is not AbsorptionGroupReviewExecutionEvidence:
            raise controller.Stage11ControllerValidationError(
                'group review runner returned invalid evidence')

    try:
        validate_absorption_group_review_execution(execution, request)
    except AbsorptionGroupReviewError as error:
        raise controller.Stage11ControllerArtifactError(
            'absorption group review receipt or result is invalid') from error

    metadata = {
        'schema_version': 1,
        'remote_task': execution.remote_task,
        'receipt_nonce': execution.receipt_nonce,
        'review_execution_session_id': execution.review_execution_session_id,
    }
    store(paths['request'], execution.request_payload)
    store(paths['result'], execution.result_payload)
    store(paths['receipt'], execution.receipt_payload)
    store(paths['provenance'], wire(metadata))
    return execution


def _group_review_proof_identity(execution):
    if execution is None:
        return None
    return {
        'request_sha256': sha(execution.request_payload),
        'result_sha256': sha(execution.result_payload),
        'receipt_sha256': sha(execution.receipt_payload),
        'review_execution_session_id_sha256': sha(
            execution.review_execution_session_id.encode('utf-8')),
    }


def normal_materialization(preparation, result, review_request, review_result,
                           source_quality, *, raw_asr_context=None,
                           absorption_group_review_execution=None):
    validate_normal_translation(serialize_stateful_result(result),
                                preparation.package, result.boundary_evidence)
    clean = controller.materialize_stateful_quality_review_clean(
        preparation.package, result, preparation, review_request, review_result,
        source_quality=source_quality, raw_asr_context=raw_asr_context,
        absorption_group_review_execution=absorption_group_review_execution,
        preserve_absorption=True, omit_metadata=True,
    )
    playback = clean.cues
    rendered = tuple(SubtitleCue(c.start_ms, c.end_ms, c.ko) for c in playback)
    if len({(c.start_ms, c.end_ms, c.text) for c in rendered}) != len(rendered):
        raise controller.Stage11ControllerValidationError(
            'duplicate Korean cue interval/text')
    artifact = controller._require_clean_artifact(clean)
    if artifact.payload is None:
        raise controller.Stage11ControllerValidationError(
            'no translated dialogue remains')
    return artifact, playback, clean


def _normal_proof(package_raw, result_raw, first, source_quality, playback,
                  review_evidence, clean_sha256):
    covered = {index for cue in playback for index in cue.source_indexes}
    # Source quality carries exact source text; omitted indexes are sufficient
    # proof for the established metadata omission report.
    metadata_omissions = [asdict(decision) for decision in source_quality
                          if decision.action == OMIT_METADATA
                          and decision.source_index not in covered]
    proof = {
        'mode': 'NORMAL', 'user_intervention': USER_INTERVENTION,
        'automatic_insertion': AUTO_INSERT,
        'supplemental_status': 'DISABLED_UNVERIFIED_ACCURACY',
        'ambiguous_policy': 'EXTERNAL_JA_AND_PRIMARY_KO',
        'quality_review': 'HYBRID_REVIEWED_CLEAN_V1',
        'package_sha256': sha(package_raw), 'result_sha256': sha(result_raw),
        'clean_sha256': clean_sha256,
        'source_count': len(first.cues),
        'absorption_count': sum(c.absorbed_into is not None for c in first.cues),
        'review_evidence': review_evidence,
        'metadata_omissions': metadata_omissions,
        'playback': [asdict(cue) for cue in playback],
    }
    return proof


def _normal_report(title, baseline_path, baseline_raw, baseline_reused,
                   outcome, alignment, baseline, clean_path, artifact,
                   review_evidence):
    return {
        'title': title, 'route': 'HYBRID',
        'baseline_artifact_path': str(baseline_path),
        'baseline_sha256': sha(baseline_raw),
        'baseline_reused': baseline_reused,
        'external_ja_outcome': outcome,
        'alignment_outcome': alignment,
        'source_quality_counts': controller._source_quality_counts(
            controller.classify_asr_result_source_quality(baseline)),
        'targeted_source_count': review_evidence['targeted_source_count'],
        'targeted_window_count': review_evidence['targeted_window_count'],
        'targeted_reused': ('not_applicable'
                            if review_evidence['targeted_reused'] is None
                            else review_evidence['targeted_reused']),
        'translation_result_identity': {
            'session_id_sha256': review_evidence[
                'source_translation_session_id_sha256'],
            'sha256': review_evidence['translation_result_sha256'],
        },
        'review_result_identity': {
            'request_sha256': review_evidence['review_request_sha256'],
            'result_sha256': review_evidence['review_result_sha256'],
            'source_translation_session_id_sha256': review_evidence[
                'source_translation_session_id_sha256'],
            'review_execution_session_id_sha256': review_evidence[
                'review_execution_session_id_sha256'],
        },
        'clean_artifact_path': str(clean_path),
        'clean_sha256': artifact.sha256,
        'publication_performed': False,
    }


def reconstruct(directory, baseline):
    source=json.loads(controller._read_private_file(directory/SOURCE_NAME,max_bytes=16*1024*1024))
    raw=controller._read_private_file(directory/'normal-external-ja.srt',max_bytes=MAX_SUBTITLE_BYTES)
    if sha(raw)!=source['external_sha256']: raise controller.Stage11ControllerArtifactError('external JA changed')
    candidate=SubtitleCandidate.validated_external_text(source['source_id'],dvd_id=baseline.source_snapshot.dvd_id,language='ja',text_format='srt')
    payload=ExternalSubtitlePayload.from_bytes(dvd_id=baseline.source_snapshot.dvd_id,candidate=candidate,payload=raw)
    app=_align_external_payload(payload,baseline.source_snapshot.dvd_id,baseline,AlignmentAcceptancePolicy(**source['acceptance_policy']),1000)
    if app.decision.verdict!='ACCEPT_HYBRID' or wire(asdict(app.alignment))!=wire(source['alignment']):
        raise controller.Stage11ControllerArtifactError('accepted alignment changed')
    from teddy_discovery_subtitle_v2_orchestrator import SubtitleV2RouteDecision
    video=controller.validate_canonical_holding({'dvd_id':baseline.source_snapshot.dvd_id,'relative_path':baseline.source_snapshot.canonical_video_relative,
        'storage_root':'jav','present':1,'parse_status':'MATCHED'},baseline.source_snapshot.dvd_id)
    route=SubtitleV2RouteDecision(canonical_video=video,route='HYBRID',state='READY_FOR_SEMANTIC',alignment_application=app)
    return prepare_normal(route,sha(controller.serialize_asr_result(baseline)),source['claim_token'])


def validate_normal_completion(report_path, clean_path, baseline_path, *, title,
                               staging_root=None, **unused):
    directory=report_path.parent
    report_raw=controller._read_private_file(report_path,max_bytes=controller.MAX_STAGE11_REPORT_BYTES)
    report=controller._parse_report(report_raw)
    proof_raw=controller._read_private_file(directory/PROOF_NAME,max_bytes=16*1024*1024)
    proof=json.loads(proof_raw)
    targeted_reused_hint=None
    if proof.get('quality_review')=='HYBRID_REVIEWED_CLEAN_V1':
        review_evidence=proof.get('review_evidence')
        if type(review_evidence) is not dict:
            raise controller.Stage11ControllerArtifactError(
                'normal proof review evidence is invalid')
        targeted_reused_hint=review_evidence.get('targeted_reused')
        if targeted_reused_hint is not None and type(targeted_reused_hint) is not bool:
            raise controller.Stage11ControllerArtifactError(
                'normal proof targeted reuse value is invalid')
    baseline_raw=controller._read_private_file(baseline_path,max_bytes=controller.MAX_ASR_ARTIFACT_BYTES)
    baseline=controller.parse_asr_result_bytes(baseline_raw)
    preparation,boundary=reconstruct(directory,baseline)
    package=preparation.package
    package_raw=controller._read_private_file(directory/'normal-package.json',max_bytes=16*1024*1024)
    result_raw=controller._read_private_file(directory/'normal-result.json',max_bytes=16*1024*1024)
    if package_raw!=serialize_stateful_package(package): raise controller.Stage11ControllerArtifactError('normal package detached')
    result=validate_normal_translation(result_raw,package,boundary)
    source_quality, review_request, review_result, raw_asr_context, evidence = _normal_review_evidence(
        directory, preparation, result, baseline, sha(baseline_raw),
        staging_root or directory, create_missing=False,
        targeted_reused_hint=targeted_reused_hint)
    group_review_execution = _normal_group_review_execution(
        directory, preparation, result, review_request, review_result,
        source_quality, raw_asr_context, staging_root=staging_root,
        create_missing=False)
    if group_review_execution is not None:
        evidence['absorption_group_review'] = _group_review_proof_identity(
            group_review_execution)
    artifact,playback,clean=normal_materialization(
        preparation,result,review_request,review_result,source_quality,
        raw_asr_context=raw_asr_context,
        absorption_group_review_execution=group_review_execution)
    clean_raw=controller._read_private_file(clean_path,max_bytes=MAX_SUBTITLE_BYTES)
    expected_proof=_normal_proof(package_raw,result_raw,result,source_quality,
                                  playback,evidence,artifact.sha256)
    expected_proof_raw=wire(expected_proof)
    expected_report=_normal_report(
        title,baseline_path,baseline_raw,report.get('baseline_reused'),
        'ACCEPTED','ACCEPT_HYBRID',baseline,clean_path,artifact,evidence)
    expected_report_raw=controller._serialize_report(expected_report)
    if (report['title']!=title or baseline.source_snapshot.dvd_id!=title
        or report['route']!='HYBRID' or report['external_ja_outcome']!='ACCEPTED' or report['alignment_outcome']!='ACCEPT_HYBRID'
        or report['publication_performed'] is not False or report['baseline_artifact_path']!=str(baseline_path)
        or report['baseline_sha256']!=sha(baseline_raw) or report['clean_artifact_path']!=str(clean_path)
        or report['clean_sha256']!=sha(clean_raw) or clean_raw!=artifact.payload
        or type(report['baseline_reused']) is not bool
        or report_raw!=expected_report_raw
        or proof_raw!=expected_proof_raw
        or proof['quality_review']!='HYBRID_REVIEWED_CLEAN_V1'
        or clean.artifact!=artifact):
        raise controller.Stage11ControllerArtifactError('normal completion proof invalid')
    targeted_reused=(report['targeted_reused']
                     if type(report['targeted_reused']) is bool else None)
    return controller.Stage11ControllerResult(title,'HYBRID',clean_path,sha(clean_raw),report_path,sha(report_raw),
        report['baseline_reused'],targeted_reused,True,True,'ACCEPTED','ACCEPT_HYBRID')


def run_one_title_normal_mode(title, *, artifact_root, stateful_staging_root, claim_token,
                             baseline_transcriber, external_ja_attempt, first_pass_runner,
                             acceptance_policy, holding_resolver=None,
                             hybrid_review_runner=None, hybrid_targeted_runner=None,
                             hybrid_absorption_group_review_runner=None,
                             **unused):
    title=controller._canonical_title(title)
    root=controller._validate_root(artifact_root,field_name='artifact_root')
    staging=controller._validate_root(stateful_staging_root,field_name='stateful_staging_root')
    directory=controller._title_directory(root,title)
    try:
        video,snapshot=controller._resolve_holding(title,holding_resolver)
        if video.video_format != 'mp4':
            raise controller.Stage11ControllerValidationError('normal mode requires canonical MP4 input')
        baseline_path=directory/controller.BASELINE_ASR_FILENAME
        baseline,raw,reused=controller._dispatch_baseline(baseline_path,canonical_video=video,source_snapshot=snapshot,
            baseline_transcriber=baseline_transcriber,allow_create=not (directory/controller.MECHANICAL_REPORT_FILENAME).exists())
        report_path=directory/controller.MECHANICAL_REPORT_FILENAME; clean_path=directory/controller.CLEAN_SRT_FILENAME
        if report_path.exists():
            if not (directory/PROOF_NAME).exists(): raise controller.Stage11ControllerArtifactError('legacy completion requires separate normal artifact root')
            return validate_normal_completion(report_path,clean_path,baseline_path,title=title)
        external_diagnostic={}
        try:
            route,outcome,alignment=controller._select_route(
                video,baseline,external_ja_attempt,
                diagnostic_out=external_diagnostic)
        finally:
            if external_diagnostic:
                controller._persist_external_ja_diagnostic(
                    directory,external_diagnostic)
        if route.route!='HYBRID':
            raise controller.Stage11ControllerValidationError('normal mode requires accepted external JA; outcome='+outcome+'; alignment='+alignment)
        app=route.alignment_application; payload=app.bundle.external_ja_payload
        source={'external_sha256':payload.sha256,'source_id':payload.candidate.external_source_id,
            'acceptance_policy':asdict(acceptance_policy),'alignment':asdict(app.alignment),'claim_token':claim_token}
        store(directory/'normal-external-ja.srt',payload.payload)
        source_raw=wire(source); store(directory/SOURCE_NAME,source_raw)
        preparation,boundary=prepare_normal(route,sha(raw),claim_token)
        package=preparation.package; package_raw=serialize_stateful_package(package)
        store(directory/'normal-package.json',package_raw)
        first=first_pass_runner(package,route='HYBRID',staging_root=staging,boundary_evidence=boundary)
        first=validate_normal_translation(serialize_stateful_result(first),package,boundary)
        result_raw=serialize_stateful_result(first); store(directory/'normal-result.json',result_raw)
        source_quality,review_request,review_result,raw_asr_context,evidence = _normal_review_evidence(
            directory,preparation,first,baseline,sha(raw),staging,
            hybrid_review_runner=hybrid_review_runner,
            hybrid_targeted_runner=hybrid_targeted_runner,
            create_missing=True)
        group_review_execution = _normal_group_review_execution(
            directory, preparation, first, review_request, review_result,
            source_quality, raw_asr_context,
            group_review_runner=hybrid_absorption_group_review_runner,
            staging_root=staging,
            create_missing=True)
        if group_review_execution is not None:
            evidence['absorption_group_review'] = _group_review_proof_identity(
                group_review_execution)
        artifact,playback,clean=normal_materialization(
            preparation,first,review_request,review_result,source_quality,
            raw_asr_context=raw_asr_context,
            absorption_group_review_execution=group_review_execution)
        proof=_normal_proof(package_raw,result_raw,first,source_quality,
                            playback,evidence,artifact.sha256)
        proof_raw=wire(proof)
        store(clean_path,artifact.payload)
        store(directory/PROOF_NAME,proof_raw)
        report=_normal_report(title,baseline_path,raw,reused,outcome,alignment,
                              baseline,clean_path,artifact,evidence)
        store(report_path,controller._serialize_report(report))
        return validate_normal_completion(report_path,clean_path,baseline_path,
                                          title=title,staging_root=staging)
    except Exception as error:
        # Every failed invocation terminates, with an immutable reason; no user-wait state.
        failure={'status':'FAILED','title':title,'error_type':type(error).__name__,
            'reason':str(error),'user_intervention':0,'automatic_insertion':False}
        diagnostic=getattr(error,'safe_diagnostic',None)
        if isinstance(error,Stage11DeploymentTransportError) and diagnostic:
            failure['execution_diagnostic']=diagnostic
        store(directory/('normal-failure-'+uuid.uuid4().hex+'.json'),wire(failure))
        if isinstance(error,(controller.Stage11ControllerError,Stage11DeploymentTransportError,ASRError)):
            raise
        raise controller.Stage11ControllerValidationError('normal core failed: '+type(error).__name__+': '+str(error)) from error


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dvd-id',action='append',required=True)
    parser.add_argument('--run-root',type=Path,required=True)
    parser.add_argument('--external-ja',type=Path,action='append',help='Optional retained JA, in DVD-ID order; generic local acquisition only')
    parser.add_argument('--baseline-root',type=Path,help='Optional existing source-bound baseline cache')
    args=parser.parse_args()
    if args.external_ja and len(args.external_ja)!=len(args.dvd_id): parser.error('one JA input per title required')
    from teddy_discovery_stage12_bulk_runner import build_deployment_config, build_dependencies, acceptance_policy
    config=build_deployment_config(); dependencies=build_dependencies(config)
    first_pass=NativeNormalFirstPass(dependencies.remote_bridge)
    root=args.run_root.absolute(); root.mkdir(mode=0o700,parents=True,exist_ok=True)
    artifacts=root/'artifacts'; staging=root/'staging'
    for p in (artifacts,staging): p.mkdir(mode=0o700,exist_ok=True)
    failed=False
    for index,title in enumerate(args.dvd_id):
        kwargs=dependencies.controller_kwargs()
        kwargs['first_pass_runner']=dependencies.capture_first_pass_runner(first_pass)
        if args.baseline_root:
            def cached(video):
                _,snapshot=controller._resolve_holding(video.dvd_id,kwargs['holding_resolver'])
                return controller._dispatch_baseline(args.baseline_root/video.dvd_id/controller.BASELINE_ASR_FILENAME,
                    canonical_video=video,source_snapshot=snapshot,baseline_transcriber=lambda _:None,allow_create=False)[0]
            kwargs['baseline_transcriber']=cached
        if args.external_ja:
            raw=args.external_ja[index].read_bytes()
            def local_external(video,baseline,raw=raw):
                candidate=SubtitleCandidate.validated_external_text('local-sha256-'+sha(raw),dvd_id=video.dvd_id,language='ja',text_format='srt')
                payload=ExternalSubtitlePayload.from_bytes(dvd_id=video.dvd_id,candidate=candidate,payload=raw)
                return _align_external_payload(payload,video.dvd_id,baseline,acceptance_policy(),1000)
            kwargs['external_ja_attempt']=dependencies.capture_external_ja_attempt(
                local_external
            )
        try:
            from teddy_discovery_stage12_rollout import build_nas_preflight_filesystem
            from teddy_discovery_stage12_bulk_runner import NAS
            video,snapshot=controller._resolve_holding(title,kwargs['holding_resolver'])
            info=build_nas_preflight_filesystem(**NAS).lstat(video.relative_path)
            if (not stat.S_ISREG(info.st_mode) or info.st_size!=snapshot.source_size
                or info.st_mtime_ns!=snapshot.source_mtime_ns):
                raise controller.Stage11ControllerValidationError('input video snapshot mismatch')
            result=run_one_title_normal_mode(title,artifact_root=artifacts,stateful_staging_root=staging,
                claim_token=1,acceptance_policy=acceptance_policy(),**kwargs)
            print(json.dumps({'title':title,'status':'GENERATED','srt_path':str(result.clean_path),
                'srt_sha256':result.clean_sha256,'user_intervention':0,'auto_insert':False}),flush=True)
        except Exception as error:
            failed=True
            print(json.dumps({'title':title,'status':'FAILED','error_type':type(error).__name__,
                'reason':str(error),'user_intervention':0}),flush=True)
    return int(failed)


if __name__=='__main__': raise SystemExit(main())
