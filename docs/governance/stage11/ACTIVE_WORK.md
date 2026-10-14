# Stage11 subtitle workstream — active work

WORKSTREAM: stage11
TASK_ID: S11-WX002
STATUS: IN_PROGRESS
CONTRACT_VERSION: 1.0.0
REQUIRES_WORKSTREAMS: stage11

## OBJECTIVE

Resume the bounded, independent FNS-247 WhisperX Japanese ASR experiment blocked under S11-WX001. Compare only the fixed 27 existing samples. This is an isolated evaluation, not a Stage11/Stage12 product-pipeline change or full-title ASR.

## APPROVED_SCOPE

- Register this task on the verified canonical `teddy-subtitle-stage11` branch after the required governance checks. Do not run any model until that metadata commit is confirmed on the remote branch.
- Reuse the existing 27 samples, labels, timing, padding, Whisper/ReazonSpeech outputs, and evaluation evidence. Recheck the existing manifest and source SHA map read-only; do not create a duplicate audit report or validator.
- Use the verified VM122 identity for `teddy@192.168.1.134`, with the existing private key, known_hosts file, and strict noninteractive SSH options. Confirm `VM122_SSH_OK`; classify sandbox denial separately from VM122 authentication failure.
- Inspect current GPU/VRAM, RAM, disk, running llama-server and Whisper Worker, Python/CUDA/cuDNN/CTranslate2, WhisperX installation/cache, Japanese alignment-model availability, and pyannote access before inference. Use an isolated venv and private artifact directory only.
- Freeze the A/B evaluation protocol before examining new WhisperX outputs. Run one dialogue sample and one non-dialogue sample first; inspect outputs, resources, and service impact before running the remaining 25. Do not rerun existing Whisper or ReazonSpeech jobs.
- Run Japanese `large-v3` WhisperX with `language=ja`, original audio, no Demucs, and recorded VAD/batch settings. Preserve original absolute times and record runtime and resource use.
- Run Japanese forced alignment only when the sample inference and alignment-model/resource gates pass. If all 27 trials proceed normally and pyannote access, license, and resource conditions pass, diarize only 2–3 selected continuous scenes with plausible speaker changes.
- Compare outputs read-only against existing Whisper and ReazonSpeech evidence. Keep ASR, alignment, and diarization evidence distinct; preserve unresolved truth and speaker identity.
- Record material results in the canonical handoff, then return the Stage11 router and active-work file to `INACTIVE/NONE` after remote verification.

## PROHIBITED_SCOPE

- Do not run full-title FNS-247 ASR, expand beyond the fixed 27 samples, change Stage11/Stage12 product code or production pipelines, or add FNS-247-specific production exceptions.
- Do not alter sample labels, original audio, existing Whisper/ReazonSpeech outputs, source evidence, or user judgments. Do not rerun those existing recognizers.
- Do not stop or restart production services, kill processes to free memory, alter production venvs/models/CUDA settings, fall back to CPU, or retry after OOM or integrity failure.
- Do not bypass SSH/model authentication, host-key checks, model access, or license requirements; do not create SSH keys or expose credentials.
- Do not run Demucs or Hermes. Do not write to production databases, queues, timers, NAS, Jellyfin, subtitle paths, deployment targets, or publish output.
- Do not commit audio, Japanese text/transcripts, raw model outputs, tokens, or private experiment artifacts.
- Do not claim dialogue recovery from output presence or model agreement. Do not report WER/CER without verified Japanese references or diarization accuracy without speaker ground truth.

## ACCEPTANCE_CRITERIA

- Both required governance commands pass before remote registration; the remote update is a fast-forward from the live canonical branch SHA and is verified before SSH or model execution.
- The existing manifest, 54 core/context WAV files, and source SHA map match; preserve the 13 dialogue / 14 non-dialogue split and all prior labels/evidence.
- VM122 SSH success, current resource safety, model access/license, and private artifact isolation are verified before inference. If a gate fails, stop without installing, freeing memory, falling back, or retrying.
- Run at most the staged 1+1 then remaining 25 samples. Report actual run count, output presence, false-dialogue observations, disagreements, runtime, memory/VRAM use, and GPU/service impact.
- Distinguish execution success from quality improvement. Without transcript truth, Japanese accuracy remains INCONCLUSIVE; without speaker truth, diarization quality remains INCONCLUSIVE.
- Run alignment and diarization only when their separate conditions pass. If diarization runs, preserve uncertainty and do not compare SPEAKER IDs across independent clips.
- Leave production code/state untouched, with `PRODUCTION_WRITES=0` and `FULL_TITLE_ASR=0`; preserve all raw private artifacts outside Git and production paths.
- Update the canonical handoff, return Stage11 to `INACTIVE/NONE`, rerun both governance checks, and verify the final canonical remote HEAD. Do not report cleanup or remote completion if those steps fail.

## EVIDENCE

- User explicitly approved S11-WX002 scope and safety boundaries in this request; Stage11 contract remains approved at v1.0.0.
- The live canonical `teddy-subtitle-stage11` HEAD was verified as `34f340b7e345cf1be3e4ed12c558f18c01ef6d91`, matching the clean task worktree. S11-WX001 registration `3811d802` and blocked closure `34f340b7` were inspected.
- S11-WX001 ran no WhisperX inference. Its saved sample identity audit was PASS; current read-only recheck matched the existing manifest and source SHA map for all 54 core/context WAVs.
- Existing evidence retains 27 samples: 13 dialogue and 14 non-dialogue. Japanese reference transcripts and exact utterance boundaries are not established for the 13 dialogue samples.

## NEXT_DECISION

After the validated S11-WX002 metadata commit is confirmed on the canonical remote branch, run the specified VM122 SSH marker check and current resource/access gates. Only then begin the staged WhisperX experiment.
