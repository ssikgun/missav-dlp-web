# Stage11 subtitle workstream — active work

WORKSTREAM: stage11
TASK_ID: S11-WX003
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: stage11

## OBJECTIVE

Build a private WhisperX environment on VM122 that is independent of the operating environment, then compare WhisperX against existing Whisper and ReazonSpeech evidence on only the fixed 27 user-judged FNS-247 samples. This is a bounded experiment, not a production pipeline change or full-title recognition run.

## APPROVED_SCOPE

- Register this task against the verified canonical `teddy-subtitle-stage11` branch. Do not contact VM122 or run a model until the registration commit is confirmed on the remote branch.
- Reuse the existing 27 samples, 13 dialogue / 14 non-dialogue labels, original audio, source identity, timestamps, padding, hashes, prior Whisper/ReazonSpeech results, and user judgments. Perform only the minimum read-only integrity recheck; do not create duplicate audit tooling or reports.
- Use the existing strict VM122 SSH identity for `teddy@192.168.1.134`. Before installation, inspect current Python, driver/CUDA, GPU/VRAM, RAM, disk, running Qwen/Whisper services, installed package versions, model access, and relevant caches.
- Inspect existing target paths before creation. Use only a new dedicated venv at `/home/teddy/stage11-whisperx-ab-venv` and private experiment storage at `/home/teddy/stage11-whisperx-ab-private`, both only if absent or safely owned by this task. Install official packages and required models there only, with bounded downloads. Record package versions, model identifiers/revisions, and sources. Stop on dependency conflicts, system-level requirements, inadequate resources, or path collisions.
- Freeze and retain this evaluation protocol before reading any new WhisperX output: WhisperX `large-v3`, `language=ja`, original audio, GPU-only, `compute_type=float16`, initial `batch_size=1`, `vad_method=silero` with effective settings recorded, no Demucs, sequential samples, and at most 27 total. Preserve source-relative and original absolute timing.
- After the sample identity and host/resource gates pass, run one dialogue sample and one non-dialogue sample first. Review raw output, resource peaks, runtime, and service impact; only then continue the remaining 25 sequentially if safe. Use bounded checkpoints. No automatic CPU fallback, OOM retry, or service intervention.
- Try Japanese forced alignment only on eligible WhisperX speech output and after verifying the exact official alignment model, access/license, and resource conditions. Run pyannote only if its gated-model access/license and resource conditions pass, and only on 2–3 selected continuous scenes with plausible speaker changes after other model loads are released.
- Compare read-only against the existing Whisper and ReazonSpeech results. Record output presence, candidate changes, false-dialogue observations, alignment boundary changes, diarization transitions, runtime, VRAM/RAM, and service impact. Without verified Japanese text or speaker truth, report recognition accuracy and speaker accuracy as UNKNOWN; classify quality as INCONCLUSIVE where evidence cannot decide.
- Store raw outputs and metadata only under the private VM122 experiment directory with directory mode 0700 and file mode 0600. Preserve provenance and result identifiers. Update the canonical handoff after a completed run or safety stop; restore this task and router to INACTIVE/NONE only after no independent execution remains, then validate and verify the final canonical remote state.

## PROHIBITED_SCOPE

- Do not alter the production Whisper venv `/home/teddy/stage11-whisper-v3-venv`, operating models, GPU Worker, Qwen service, system Python/pip, system packages, NVIDIA driver, CUDA Toolkit, or shared model caches.
- Do not change Stage11/Stage12 product code, production databases, queues, timers, NAS, Jellyfin, subtitles, deployment targets, or published artifacts.
- Do not call Hermes or run Demucs. Do not recognize the complete FNS-247 title or exceed the fixed 27 samples.
- Do not stop/restart services, kill processes, reclaim GPU resources, switch to CPU, or retry following OOM or integrity failure.
- Do not alter original audio, sample labels, user judgments, prior Whisper/ReazonSpeech evidence, or their stored outputs.
- Do not bypass SSH host-key/authentication, model access or licensing. Do not create/replace SSH keys or expose credentials.
- Do not add unapproved models, apply compatibility patches, replace environments, or expand experiment scope.
- Do not commit audio, Japanese source/transcript text, raw inference outputs, secrets, tokens, or private experiment artifacts.

## ACCEPTANCE_CRITERIA

- Both required governance commands pass before the registration commit is pushed; that commit is a fast-forward from the live canonical HEAD and is confirmed remotely before VM122 access.
- Existing sample identity checks pass, including all 54 core/context WAV hashes; the fixed 13/14 split and prior evidence remain unchanged.
- Current VM122 host, package, model-access, and resource gates pass before creating the venv or downloading models. Installation is isolated, imports succeed, GPU is actually available, and no operating service is disturbed.
- Run at most the staged 1+1 then remaining 25, reporting the exact number completed and retaining private provenance, raw output, settings, and resource observations.
- Alignment and diarization are reported separately and run only when their gates pass. Do not treat output presence as verified dialogue recovery or generated speaker IDs as speaker accuracy.
- Leave production code unchanged, production writes at zero, and full-title ASR at zero. Update the canonical handoff and return the task to INACTIVE/NONE only when the experiment has ended; rerun governance validation and verify the final remote HEAD.

## EVIDENCE

- The user explicitly approved S11-WX003, its bounded 27-sample scope, isolated installation, staged inference, conditional alignment/diarization, and the listed prohibitions.
- The live canonical branch was fetched and verified at registration base SHA `761fcdce563b32edfa31f5f44f09eb11535e9d8f`.
- S11-WX001/WX002 records show 54/54 source WAV SHA checks passed, 13 dialogue and 14 non-dialogue samples remain fixed, and WhisperX inference was 0/27. Their existing Whisper/ReazonSpeech evidence remains preserved.
- Verified Japanese reference transcripts, exact utterance truth, and speaker ground truth remain unavailable; no WER/CER or diarization accuracy claim is authorized.

## NEXT_DECISION

After the remote registration commit is confirmed, run the strict SSH marker and current read-only host/resource/access gates. Proceed to installation only if every safety gate passes; stop and record the blocking condition otherwise.
